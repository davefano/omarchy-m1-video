#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Summarize retained kernel journals read-only; never a boot-reliability verdict.

Raw messages, journal identifiers and stderr remain private. No video device,
module operation, privileged command or system configuration is accessed.
"""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import selectors
import signal
import stat
import subprocess
import sys
import time

HELPER_PATH = Path(__file__).resolve().with_name('qualify-device.py')
SPEC = importlib.util.spec_from_file_location('qualification_helpers', HELPER_PATH)
helpers = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helpers)
write_record = helpers.write_record

EVENTS = ('avd_activity', 'avd_error', 'avd_timeout', 'avd_stack', 'allocation_failure',
          'slice_limit', 'firmware_missing', 'reset_reason', 'pmu_boot_report', 'panic', 'oops',
          'warning', 'watchdog', 'shutdown')


def run_command(*args, timeout=10, byte_limit=16 * 1024 * 1024):
    """Drain both pipes within one combined byte budget and wall-clock deadline."""
    output = bytearray()
    stderr_present = False
    status = 'complete'
    try:
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   env={**os.environ, 'LC_ALL': 'C'}, start_new_session=True)
    except FileNotFoundError:
        return {'stdout': '', 'status': 'missing', 'stderr_present': False}
    except OSError:
        return {'stdout': '', 'status': 'failed', 'stderr_present': False}
    total = 0
    deadline = time.monotonic() + timeout
    try:
        with selectors.DefaultSelector() as selector:
            for stream in (process.stdout, process.stderr):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    status = 'timeout'
                    break
                for key, _ in selector.select(remaining):
                    chunk = os.read(key.fd, min(65536, byte_limit - total))
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    total += len(chunk)
                    if key.fileobj is process.stdout:
                        output.extend(chunk)
                    else:
                        stderr_present = True
                    if total >= byte_limit:
                        status = 'byte_limit'
                        break
                if status != 'complete':
                    break
            if status == 'complete':
                try:
                    if process.wait(timeout=max(0.001, deadline - time.monotonic())):
                        status = 'failed'
                except subprocess.TimeoutExpired:
                    status = 'timeout'
    except OSError:
        status = 'failed'
    finally:
        if status in ('timeout', 'byte_limit', 'failed'):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.stdout.close()
        process.stderr.close()
        process.wait()
    return {'stdout': output.decode('utf-8', errors='replace'), 'status': status,
            'stderr_present': stderr_present}


def timestamp(value):
    if isinstance(value, bool) or not re.fullmatch(r'[0-9]{1,18}', str(value)):
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000000, timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
        return None


def command_gaps(result):
    gaps = [] if result['status'] == 'complete' else [result['status']]
    if result['stderr_present']:
        gaps.append('stderr_present')
    return gaps


def categories(message):
    """Conservative fixed patterns, not proof that an AVD binary was loaded."""
    lower = message.lower()
    avd = bool(re.search(r'\b(?:apple[-_]avd|avd)\b', lower))
    if any(word in lower for word in ('command line:', 'cmdline', 'blacklist')):
        avd = False
    found = set()
    if avd:
        found.add('avd_activity')
        if re.search(r'\b(?:failed|failure|error|rejected)\b', lower):
            found.add('avd_error')
        if re.search(r'\b(?:timeout|timed out)\b', lower):
            found.add('avd_timeout')
        if re.search(r'\bavd_\w+\+0x[0-9a-f]+/', lower) or '[apple_avd]' in lower:
            found.add('avd_stack')
        if re.search(r'slice_num\s*>|too many slices|slice.{0,20}limit', lower):
            found.add('slice_limit')
        if ('direct firmware load' in lower and 'failed' in lower) or 'firmware missing' in lower:
            found.add('firmware_missing')
    if 'page allocation failure:' in lower or 'out of memory:' in lower:
        found.add('allocation_failure')
    if re.search(r'\b(?:reset|reboot) (?:reason|cause)\b', lower):
        found.add('reset_reason')
    if re.search(r'\bpmu\b', lower) and re.search(r'\b(?:boot error|panics?)\b', lower):
        found.add('pmu_boot_report')
    if re.match(r'\s*(?:kernel panic\b|panic:)', lower):
        found.add('panic')
    if re.match(r'\s*(?:oops:|bug:|internal error:|unable to handle kernel)', lower):
        found.add('oops')
    if re.match(r'\s*WARNING:', message):
        found.add('warning')
    if re.search(r'\b(?:soft lockup|hard lockup|watchdog.{0,20}(?:lockup|bite|timeout))', lower):
        found.add('watchdog')
    if re.match(r'\s*(?:reboot: (?:restarting system|power down)|systemd-shutdown\[)', lower):
        found.add('shutdown')
    return found


def summarize(result, entry_limit):
    gaps = command_gaps(result)
    events = {name: {'count': 0, 'first_at': None, 'last_at': None} for name in EVENTS}
    count = 0
    for line in result['stdout'].splitlines():
        if not line.strip():
            continue
        count += 1
        if count > entry_limit:
            break
        try:
            record = json.loads(line)
        except (ValueError, TypeError):
            gaps.append('malformed_json')
            continue
        if not isinstance(record, dict):
            gaps.append('invalid_record')
            continue
        at = timestamp(record.get('__REALTIME_TIMESTAMP'))
        message = record.get('MESSAGE')
        if at is None or not isinstance(message, str):
            gaps.append('invalid_record')
            continue
        for category in categories(message):
            event = events[category]
            event['count'] += 1
            event['first_at'] = min(event['first_at'], at) if event['first_at'] else at
            event['last_at'] = max(event['last_at'], at) if event['last_at'] else at
    if not count:
        gaps.append('empty')
    if count >= entry_limit:
        gaps.append('entry_limit')
    return {'status': 'partial' if gaps else 'complete', 'entries_seen': min(count, entry_limit),
            'gaps': sorted(set(gaps)), 'events': events}


def scan_directory(path, limit):
    count = 0
    with os.scandir(path) as entries:
        for _ in entries:
            count += 1
            if count >= limit:
                break
    return count


def pstore_state(path, scan):
    try:
        count = scan(path, 256)
    except FileNotFoundError:
        return {'status': 'missing', 'entries': None}
    except PermissionError:
        return {'status': 'inaccessible', 'entries': None}
    except OSError:
        return {'status': 'failed', 'entries': None}
    return {'status': 'truncated' if count >= 256 else ('present' if count else 'empty'),
            'entries': count}


def collect(device_id, *, root=Path('/'), run=run_command, scan=scan_directory,
            release=None, boot_limit=6, entry_limit=30000):
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}', device_id):
        raise ValueError('invalid public device pseudonym')
    if not 1 <= boot_limit <= 16 or not 1 <= entry_limit <= 30000:
        raise ValueError('invalid collection limits')
    release = release or platform.release()
    gaps = []
    packages = {}
    for name in ('linux-asahi', 'linux-asahi-headers', 'libva-v4l2_request-avd'):
        result = run('pacman', '-Q', name)
        match = re.fullmatch(re.escape(name) + r' ([A-Za-z0-9.+:_~-]+)', result['stdout'].strip())
        packages[name] = match.group(1) if match and not command_gaps(result) else None
        if packages[name] is None:
            gaps.append('package_identity_unavailable')
    selected = run('modinfo', '-n', 'apple_avd')
    selected_path = Path(selected['stdout'].strip())
    valid = (not command_gaps(selected) and '..' not in selected_path.parts and
             any(selected_path.is_relative_to(prefix) for prefix in ('/lib/modules', '/usr/lib/modules')))
    selected_hash = helpers.file_hash(root / str(selected_path).lstrip('/')) if valid else None
    if selected_hash is None:
        gaps.append('selected_module_identity_unavailable')
    try:
        loaded = stat.S_ISDIR((root / 'sys/module/apple_avd').stat().st_mode)
    except FileNotFoundError:
        loaded = False
    except OSError:
        loaded = None
        gaps.append('module_presence_unavailable')
    module = {'loaded': loaded, 'loaded_binary_identity': 'unknown',
              'loaded_binary_sha256': None, 'selected_file_sha256': selected_hash,
              'note': 'Selected file is for a future load, not the loaded binary.'}
    listed = run('journalctl', '--list-boots', '--output=json', '--lines=' + str(boot_limit),
                 '--no-pager', byte_limit=65536)
    list_gaps = command_gaps(listed)
    try:
        boot_rows = json.loads(listed['stdout'])
        if not isinstance(boot_rows, list):
            raise ValueError()
    except ValueError:
        boot_rows = []
        list_gaps.append('malformed_json')
    if not boot_rows:
        list_gaps.append('empty')
    if len(boot_rows) >= boot_limit:
        list_gaps.append('window_limit')
    boots = []
    seen = set()
    for row in boot_rows[-boot_limit:]:
        if (not isinstance(row, dict) or type(row.get('index')) is not int or
                not -1000000 <= row['index'] <= 0 or
                not re.fullmatch('[0-9a-f]{32}', str(row.get('boot_id', ''))) or
                row['index'] in seen):
            list_gaps.append('invalid_record')
            continue
        seen.add(row['index'])
        first, last = timestamp(row.get('first_entry')), timestamp(row.get('last_entry'))
        if first is None or last is None:
            list_gaps.append('invalid_record')
        journal = run('journalctl', '--dmesg', '--boot', row['boot_id'], '--output=json',
                      '--output-fields=MESSAGE,__REALTIME_TIMESTAMP',
                      '--lines=' + str(entry_limit), '--no-pager')
        summary = summarize(journal, entry_limit)
        summary.update(slot=row['index'], retained_first_at=first, retained_last_at=last)
        boots.append(summary)
    pstore = {name: pstore_state(root / path, scan) for name, path in
              (('live', 'sys/fs/pstore'), ('archive', 'var/lib/systemd/pstore'))}
    if list_gaps:
        gaps.append('boot_list_incomplete')
    if any(boot['gaps'] for boot in boots):
        gaps.append('journal_incomplete')
    if any(state['status'] not in ('empty', 'present') for state in pstore.values()):
        gaps.append('pstore_incomplete')
    return {'schema_version': 1, 'record_kind': 'read_only_boot_evidence',
            'device_id': device_id, 'collected_at': datetime.now(timezone.utc).isoformat(),
            'hardware_qualified': False, 'support_status': 'experimental',
            'kernel': {'release': release}, 'packages': packages, 'module': module,
            'boot_list': {'gaps': sorted(set(list_gaps)), 'requested_window': boot_limit},
            'boots': boots, 'pstore': pstore,
            'collection': {'status': 'partial' if gaps else 'complete', 'gaps': sorted(set(gaps)),
                           'entry_limit_per_boot': entry_limit, 'byte_limit_per_boot': 16777216,
                           'timeout_seconds_per_command': 10},
            'interpretation': 'Counts are pattern matches, not proof of cause, loaded module identity, '
                              'a complete journal, a clean boot or boot reliability. Empty pstore '
                              'does not exclude a reset. No hardware experiment was run.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device-id', required=True, help='public pseudonym, never a serial number')
    parser.add_argument('--output', type=Path, required=True, help='new JSON file; existing paths refused')
    parser.add_argument('--boots', type=int, default=6, choices=range(1, 17), metavar='1..16')
    args = parser.parse_args()
    try:
        record = collect(args.device_id, boot_limit=args.boots)
        script = Path(__file__).resolve()
        record['collector'] = {'git_commit': helpers.collector_revision(script),
                               'script_sha256': helpers.file_hash(script),
                               'helper_git_commit': helpers.collector_revision(HELPER_PATH),
                               'helper_sha256': helpers.file_hash(HELPER_PATH),
                               'python_version': platform.python_version()}
        write_record(args.output, record)
    except (OSError, ValueError):
        print('Boot evidence not written; check the pseudonym and use a new writable output path.',
              file=sys.stderr)
        return 1
    print('Boot evidence recorded; no boot-reliability or hardware qualification verdict.')
    return 2 if record['collection']['gaps'] else 0


if __name__ == '__main__':
    sys.exit(main())
