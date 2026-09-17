#!/usr/bin/env python3
"""Synthetic, offline tests: no decoder or module operations."""
import importlib.util
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('boot_evidence', ROOT / 'tools/collect-boot-evidence.py')
evidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evidence)


def result(stdout='', status='complete', stderr_present=False):
    return {'stdout': stdout, 'status': status, 'stderr_present': stderr_present}


def entry(message, time=1000000):
    return json.dumps({'MESSAGE': message, '__REALTIME_TIMESTAMP': str(time),
                       '_HOSTNAME': 'SECRET-HOST', '_BOOT_ID': 'SECRET-BOOT',
                       '__CURSOR': 'SECRET-CURSOR'})


class BootEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for directory in ('sys/fs/pstore', 'var/lib/systemd/pstore', 'sys/module'):
            (self.root / directory).mkdir(parents=True)
        module = self.root / 'usr/lib/modules/test/updates/apple-avd.ko'
        module.parent.mkdir(parents=True)
        module.write_bytes(b'module')
        self.boots = result(json.dumps([
            {'index': -1, 'boot_id': 'a' * 32, 'first_entry': 1000000, 'last_entry': 3000000},
            {'index': 0, 'boot_id': 'b' * 32, 'first_entry': 4000000, 'last_entry': 5000000}]))
        self.journals = {'a' * 32: result(entry('apple-avd 268000000.avd: firmware missing SECRET', 1000000)),
                         'b' * 32: result(entry('ordinary message SECRET', 4000000))}
        self.calls = []

    def command(self, *args, **kwargs):
        self.calls.append(args)
        if args[0] == 'pacman':
            return result(args[-1] + ' 1.0-1\n')
        if args[0] == 'modinfo':
            return result('/usr/lib/modules/test/updates/apple-avd.ko\n')
        if '--list-boots' in args:
            return self.boots
        if args[0] == 'journalctl':
            return self.journals[args[args.index('--boot') + 1]]
        raise AssertionError(args)

    def collect(self, **kwargs):
        return evidence.collect('fixture-m2', root=self.root, run=self.command,
                                release='test', **kwargs)

    def test_multi_boot_counts_and_private_fields(self):
        self.journals['a' * 32] = result('\n'.join([
            entry('apple-avd 268000000.avd: timeout SECRET', 1000000),
            entry('apple-avd 268000000.avd: firmware missing SECRET', 3000000)]))
        report = self.collect()
        self.assertEqual([b['slot'] for b in report['boots']], [-1, 0])
        event = report['boots'][0]['events']['avd_activity']
        self.assertEqual(event, {'count': 2, 'first_at': '1970-01-01T00:00:01+00:00',
                                 'last_at': '1970-01-01T00:00:03+00:00'})
        self.assertEqual(report['boots'][1]['events']['avd_activity']['count'], 0)
        self.assertNotIn('SECRET', json.dumps(report))
        self.assertNotIn(str(self.root), json.dumps(report))
        self.assertFalse(report['hardware_qualified'])
        self.assertEqual(report['collection']['status'], 'complete')
        self.assertTrue(all(a[0] in ('journalctl', 'pacman', 'modinfo') for a in self.calls))
        self.assertFalse(any('--quiet' in a for a in self.calls))

    def test_command_and_parse_gaps(self):
        for sample, gap in [(result('', 'missing'), 'missing'), (result('', 'failed'), 'failed'),
                            (result('', 'timeout'), 'timeout'), (result('', 'byte_limit'), 'byte_limit'),
                            (result('not json'), 'malformed_json'),
                            (result(entry('SECRET'), stderr_present=True), 'stderr_present'),
                            (result(''), 'empty')]:
            with self.subTest(gap=gap):
                self.journals['a' * 32] = sample
                report = self.collect()
                self.assertIn(gap, report['boots'][0]['gaps'])
                self.assertEqual(report['collection']['status'], 'partial')
                self.assertNotIn('SECRET', json.dumps(report))

    def test_bad_boot_list_and_empty_list_are_explicit(self):
        for sample, gap in [(result('bad'), 'malformed_json'), (result('[]'), 'empty'),
                            (result('', 'missing'), 'missing'),
                            (result(self.boots['stdout'], stderr_present=True), 'stderr_present')]:
            self.boots = sample
            report = self.collect()
            self.assertIn(gap, report['boot_list']['gaps'])
            self.assertEqual(report['collection']['status'], 'partial')

    def test_saturation_and_invalid_timestamp(self):
        self.journals['a' * 32] = result(entry('apple_avd timeout', 'SECRET'))
        report = self.collect(entry_limit=1, boot_limit=2)
        self.assertIn('entry_limit', report['boots'][0]['gaps'])
        self.assertIn('invalid_record', report['boots'][0]['gaps'])
        self.assertIn('window_limit', report['boot_list']['gaps'])
        self.assertNotIn('SECRET', json.dumps(report))

    def test_event_categories_and_false_positives(self):
        messages = [
            'Kernel command line: module_blacklist=apple_avd SECRET',
            'blacklist apple_avd SECRET',
            'hw perfevents: enabled with apple_m1_pmu PMU driver',
            'random warning about unrelated setup',
            'WARNING: drivers/phy/apple/atc.c:2328 at atcphy_mux_set+0x1010/0x1260 [phy_apple_atc], CPU#0: SECRET',
            ' avd_init_job+0x2c/0x54 [apple_avd]',
            'Internal error: Oops: 0000000096000004 [#1] PREEMPT SMP',
            'PMU: boot error: previous panic',
            'apple-avd 268000000.avd: page allocation failure: order:12',
            'avd 269080000.avd: slice_num > 4096, stream was rejected!',
            'avd 269080000.avd: Direct firmware load for apple/avd-fw-v3-t1.bin failed with error -2',
            'Kernel panic - not syncing: SECRET',
            'watchdog: BUG: soft lockup - CPU#0 stuck!',
            'reboot: Restarting system',
            'apple-pmu: reset reason: watchdog',
        ]
        self.journals['a' * 32] = result('\n'.join(entry(m) for m in messages))
        events = self.collect()['boots'][0]['events']
        for category in ('warning', 'avd_stack', 'allocation_failure', 'slice_limit',
                         'firmware_missing', 'panic', 'oops', 'pmu_boot_report', 'shutdown', 'reset_reason'):
            self.assertEqual(events[category]['count'], 1, category)
        self.assertEqual(events['avd_activity']['count'], 4)

    def test_pstore_states_contents_never_read(self):
        (self.root / 'sys/fs/pstore').rmdir()
        report = self.collect()
        self.assertEqual(report['pstore']['live']['status'], 'missing')
        self.assertEqual(report['pstore']['archive']['status'], 'empty')
        (self.root / 'var/lib/systemd/pstore/SECRET-name').write_text('SECRET-content')
        report = self.collect()
        self.assertEqual(report['pstore']['archive']['entries'], 1)
        self.assertNotIn('SECRET', json.dumps(report))
        def denied(path, limit):
            raise PermissionError('SECRET-private-path')
        report = self.collect(scan=denied)
        self.assertEqual(report['pstore']['live']['status'], 'inaccessible')
        self.assertNotIn('SECRET', json.dumps(report))

    def test_observed_stack_allocation_and_firmware_counts(self):
        messages = [
            ' avd_init_job+0x2c/0x54 [apple_avd]',
            'ThreadPoolSingl: page allocation failure: order:10, mode:0x40dc0',
            'avd 269080000.avd: Direct firmware load for apple/avd-fw-v3-t1.bin failed with error -2',
            'avd 269080000.avd: failed to load firmware: -2',
            'avd 269080000.avd: probe with driver avd failed with error -2',
        ]
        self.journals['a' * 32] = result('\n'.join(entry(m) for m in messages))
        events = self.collect()['boots'][0]['events']
        for category in ('avd_stack', 'allocation_failure', 'firmware_missing'):
            self.assertEqual(events[category]['count'], 1, category)
        self.assertEqual(events['avd_error']['count'], 3)

    def test_pstore_entry_limit_and_failure(self):
        report = self.collect(scan=lambda path, limit: limit)
        self.assertEqual(report['pstore']['live']['status'], 'truncated')
        self.assertIn('pstore_incomplete', report['collection']['gaps'])
        def failed(path, limit):
            raise OSError('SECRET')
        self.assertEqual(self.collect(scan=failed)['pstore']['archive']['status'], 'failed')

    def test_invalid_boot_records_are_not_queried(self):
        self.boots = result(json.dumps([{'index': 'SECRET', 'boot_id': 'SECRET'}]))
        report = self.collect()
        self.assertEqual(report['boots'], [])
        self.assertIn('invalid_record', report['boot_list']['gaps'])
        self.assertNotIn('SECRET', json.dumps(report))

    def test_module_identity_is_never_loaded_identity(self):
        for loaded in (False, True):
            if loaded:
                (self.root / 'sys/module/apple_avd').mkdir()
            report = self.collect()
            self.assertEqual(report['module']['loaded'], loaded)
            self.assertEqual(len(report['module']['selected_file_sha256']), 64)
            self.assertIsNone(report['module']['loaded_binary_sha256'])
            self.assertEqual(report['module']['loaded_binary_identity'], 'unknown')

    def test_module_permission_failure_is_unknown(self):
        original = Path.stat
        def stat_fixture(path, **kwargs):
            if path == self.root / 'sys/module/apple_avd':
                raise PermissionError('SECRET')
            return original(path, **kwargs)
        with patch.object(Path, 'stat', stat_fixture):
            report = self.collect()
        self.assertIsNone(report['module']['loaded'])
        self.assertIn('module_presence_unavailable', report['collection']['gaps'])
        self.assertNotIn('SECRET', json.dumps(report))

    def test_output_and_identifier(self):
        path = self.root / 'output.json'
        evidence.write_record(path, {'original': True})
        with self.assertRaises(FileExistsError):
            evidence.write_record(path, {'replacement': True})
        link = self.root / 'link.json'
        link.symlink_to(self.root / 'absent.json')
        with self.assertRaises(FileExistsError):
            evidence.write_record(link, {})
        for value in ('', '../escape', 'a@b', 'x' * 65):
            with self.assertRaises(ValueError):
                evidence.collect(value)
        self.assertEqual(json.loads(path.read_text()), {'original': True})

    def test_cli_exit_status_and_exclusive_output_without_host_reads(self):
        script = ROOT / 'tools/collect-boot-evidence.py'
        code = ("import importlib.util, sys; "
                "s=importlib.util.spec_from_file_location('collector', sys.argv[1]); "
                "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
                "gaps=[] if sys.argv[2]=='complete' else ['fixture_gap']; "
                "m.collect=lambda *a, **kw: {'collection': {'gaps': gaps}}; "
                "sys.argv=sys.argv[2:]; sys.exit(m.main())")
        for status, expected in (('complete', 0), ('partial', 2)):
            path = self.root / (status + '.json')
            args = [sys.executable, '-c', code, str(script), status,
                    '--device-id', 'fixture', '--output', str(path)]
            first = subprocess.run(args, capture_output=True, text=True, timeout=10)
            self.assertEqual(first.returncode, expected, first.stderr)
            record = json.loads(path.read_text())
            self.assertEqual(len(record['collector']['helper_sha256']), 64)
            second = subprocess.run(args, capture_output=True, text=True, timeout=10)
            self.assertEqual(second.returncode, 1)
            self.assertNotIn(str(path), second.stderr)

    def test_real_subprocess_bounds_both_streams_and_timeout(self):
        for stream in ('stdout', 'stderr'):
            output = evidence.run_command(sys.executable, '-c',
                f'import sys; sys.{stream}.write("SECRET" * 100000)', byte_limit=512, timeout=2)
            self.assertEqual(output['status'], 'byte_limit')
            self.assertLessEqual(len(output['stdout'].encode()), 512)
        output = evidence.run_command(sys.executable, '-c', 'import time; time.sleep(5)',
                                      timeout=0.05, byte_limit=512)
        self.assertEqual(output['status'], 'timeout')
        output = evidence.run_command(sys.executable, '-c',
                                      'import sys; print("ok"); print("SECRET", file=sys.stderr)')
        self.assertEqual(output, result('ok\n', stderr_present=True))
        self.assertNotIn('SECRET', json.dumps(output))
        self.assertEqual(evidence.run_command('/nonexistent/fixture-command')['status'], 'missing')
        self.assertEqual(evidence.run_command(sys.executable, '-c', 'raise SystemExit(3)')['status'], 'failed')


if __name__ == '__main__':
    unittest.main()
