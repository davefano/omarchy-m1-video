#!/usr/bin/env python3
"""Offline device fixtures: never open a video node or load a module."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('qualification', ROOT / 'tools/qualify-device.py')
qualification = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qualification)


class QualificationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.write('proc/device-tree/compatible', b'apple,j413\0apple,t8112\0apple,arm-platform\0')
        self.write('proc/device-tree/model', b'Apple MacBook Air (13-inch, M2, 2022)\0')
        self.write('proc/meminfo', b'MemTotal:       8000000 kB\n')
        self.write('usr/lib/dri/v4l2_request_drv_video.so', b'fixture driver')
        self.write('usr/include/linux/videodev2.h', b'fixture uapi')
        self.write('usr/include/linux/v4l2-controls.h', b'fixture controls')
        self.write('usr/lib/modules/test/updates/apple-avd.ko', b'next-load module')
        self.commands = []

    def write(self, path, data):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def command(self, *args):
        self.commands.append(args)
        if args[0] == 'pacman':
            return args[-1] + ' 1.0-1'
        if args == ('modinfo', '-n', 'apple_avd'):
            return '/usr/lib/modules/test/updates/apple-avd.ko'
        raise AssertionError('unexpected command: ' + repr(args))

    def node(self, name, driver):
        self.write(f'sys/class/video4linux/{name}/name', driver.encode())
        directory = self.root / f'sys/class/video4linux/{name}/device/driver'
        directory.mkdir(parents=True)
        (directory / 'module').symlink_to('/sys/module/' + driver)

    def collect(self, machine='aarch64'):
        return qualification.collect('fixture-m2', root=self.root, command=self.command,
                                     machine=machine, release='test',
                                     available=lambda name: True)

    def test_camera_is_not_a_decoder(self):
        self.node('video0', 'apple_isp')
        result = self.collect()
        self.assertEqual(result['preflight']['status'], 'blocked')
        self.assertIn('no_apple_avd_video_node', result['preflight']['blockers'])
        self.assertFalse(result['devices'][0]['apple_avd'])
        self.assertFalse(result['hardware_qualified'])

    def test_loaded_module_never_inherits_selected_file_hash(self):
        (self.root / 'sys/module/apple_avd').mkdir(parents=True)
        self.node('video2', 'apple_avd')
        result = self.collect()
        self.assertIsNotNone(result['module']['selected_file_sha256'])
        self.assertIsNone(result['module']['loaded_binary_sha256'])
        self.assertEqual(result['module']['loaded_binary_identity'], 'unknown')
        self.assertEqual(result['preflight']['status'], 'inventory_complete')
        self.assertFalse(result['hardware_qualified'])
        self.assertEqual(result['capabilities']['av1']['status'], 'not_probed')

    def test_missing_package_and_tool_block_claims(self):
        result = qualification.collect('fixture', root=self.root, command=lambda *args: None,
                                       machine='aarch64', release='test', available=lambda _: False)
        self.assertIn('missing_package:linux-asahi', result['preflight']['blockers'])
        self.assertIn('missing_tool:vainfo', result['preflight']['blockers'])
        self.assertFalse(result['hardware_qualified'])

    def test_loaded_decoder_with_failed_modinfo_is_blocked(self):
        (self.root / 'sys/module/apple_avd').mkdir(parents=True)
        self.node('video2', 'apple_avd')
        original = self.command
        self.command = lambda *args: None if args[0] == 'modinfo' else original(*args)
        result = self.collect()
        self.assertEqual(result['preflight']['status'], 'blocked')
        self.assertEqual(result['preflight']['blockers'], ['module_file_identity_unavailable'])
        self.assertIsNone(result['module']['selected_file'])
        self.assertIsNone(result['module']['selected_file_sha256'])
        self.assertIsNone(result['module']['loaded_binary_sha256'])
        self.assertEqual(result['module']['loaded_binary_identity'], 'unknown')
        self.assertFalse(result['hardware_qualified'])

    def test_loaded_decoder_with_missing_selected_file_is_blocked(self):
        (self.root / 'sys/module/apple_avd').mkdir(parents=True)
        self.node('video2', 'apple_avd')
        (self.root / 'usr/lib/modules/test/updates/apple-avd.ko').unlink()
        result = self.collect()
        self.assertEqual(result['preflight']['status'], 'blocked')
        self.assertEqual(result['preflight']['blockers'], ['module_file_identity_unavailable'])
        self.assertEqual(result['module']['selected_file'], '/usr/lib/modules/test/updates/apple-avd.ko')
        self.assertIsNone(result['module']['selected_file_sha256'])
        self.assertIsNone(result['module']['loaded_binary_sha256'])
        self.assertEqual(result['module']['loaded_binary_identity'], 'unknown')
        self.assertFalse(result['hardware_qualified'])

    def test_wrong_platform_is_blocked(self):
        self.assertIn('architecture_not_aarch64', self.collect(machine='x86_64')['preflight']['blockers'])
        self.write('proc/device-tree/compatible', b'other,machine\0')
        self.assertIn('not_apple_device', self.collect()['preflight']['blockers'])

    def test_private_identity_is_not_collected(self):
        self.write('etc/machine-id', b'SECRET-MACHINE-ID')
        self.write('proc/device-tree/serial-number', b'SECRET-SERIAL')
        self.write('proc/cmdline', b'SECRET-CMDLINE')
        encoded = json.dumps(self.collect())
        self.assertNotIn('SECRET', encoded)
        self.assertNotIn(str(self.root), encoded)
        self.assertTrue(all(args[0] in ('pacman', 'modinfo') for args in self.commands))

    def test_unsafe_device_id_is_rejected(self):
        for name in ('/home/person', 'person@example.com', '../escape', '', 'a' * 65):
            with self.subTest(name=name), self.assertRaises(ValueError):
                qualification.collect(name, root=self.root, command=self.command,
                                      machine='aarch64', release='test', available=lambda _: True)

    def test_output_cannot_overwrite_existing_evidence(self):
        target = self.root / 'record.json'
        qualification.write_record(target, {'first': True})
        with self.assertRaises(FileExistsError):
            qualification.write_record(target, {'second': True})
        self.assertEqual(json.loads(target.read_text()), {'first': True})

    def test_cli_creates_inventory_and_refuses_overwrite(self):
        target = self.root / 'cli.json'
        args = [sys.executable, str(ROOT / 'tools/qualify-device.py'),
                '--device-id', 'cli-fixture', '--output', str(target)]
        result = subprocess.run(args, capture_output=True, text=True, timeout=120)
        self.assertIn(result.returncode, (0, 2), result.stderr)
        report = json.loads(target.read_text())
        self.assertFalse(report['hardware_qualified'])
        self.assertEqual(report['record_kind'], 'read_only_inventory')
        self.assertEqual(len(report['collector']['script_sha256']), 64)
        before = target.read_bytes()
        result = subprocess.run(args, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(target.read_bytes(), before)

    def test_unexpected_module_path_is_not_read(self):
        self.write('private/module.ko', b'SECRET')
        original = self.command
        self.command = lambda *args: '/private/module.ko' if args[0] == 'modinfo' else original(*args)
        self.assertIsNone(self.collect()['module']['selected_file_sha256'])


if __name__ == '__main__':
    unittest.main()
