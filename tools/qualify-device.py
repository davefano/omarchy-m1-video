#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Read-only Apple device inventory, never a hardware qualification verdict.

Only reads proc/sys metadata, installed files and package metadata. Does not open
video devices, run vainfo, install software, load modules or collect user logs.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import sys

REQUIRED_PACKAGES = ('linux-asahi', 'linux-asahi-headers', 'libva-v4l2_request-avd', 'libva')
PACKAGES = REQUIRED_PACKAGES + ('linux-api-headers', 'ffmpeg', 'mpv', 'mesa')
TOOLS = ('python3', 'git', 'pkg-config', 'cc', 'ffmpeg', 'vainfo', 'journalctl')


def command(*args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=10,
                                env={**os.environ, 'LC_ALL': 'C'}, check=True)
        return result.stdout.strip() or None
    except (OSError, subprocess.SubprocessError, UnicodeError):
        # Do not copy stderr: it can contain local paths or other private data.
        return None


def read_text(path):
    try:
        return path.read_text().replace('\0', '\n').strip()
    except (OSError, UnicodeError):
        return None


def file_hash(path):
    try:
        if not stat.S_ISREG(path.stat().st_mode):
            return None
        with path.open('rb') as stream:
            return hashlib.file_digest(stream, 'sha256').hexdigest()
    except OSError:
        return None


def collect(device_id, *, root=Path('/'), command=command, machine=None,
            release=None, available=shutil.which):
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}', device_id):
        raise ValueError('device-id must be a public pseudonym: 1-64 letters, digits, _ or -')
    machine = machine or platform.machine()
    release = release or platform.release()
    compatible = (read_text(root / 'proc/device-tree/compatible') or '').splitlines()
    packages = {}
    for name in PACKAGES:
        value = command('pacman', '-Q', name)
        match = re.fullmatch(re.escape(name) + r' ([A-Za-z0-9.+:_~-]+)', value or '')
        packages[name] = match.group(1) if match else None
    devices = []
    for node in sorted((root / 'sys/class/video4linux').glob('video*')):
        try:
            module = (node / 'device/driver/module').readlink().name
        except OSError:
            module = None
        devices.append({'node': node.name, 'name': read_text(node / 'name'),
                        'module': module, 'apple_avd': module == 'apple_avd'})
    selected = command('modinfo', '-n', 'apple_avd')
    # Only hash a selected module from the system module tree. Never treat its
    # hash as the binary already loaded in the kernel.
    selected_path = Path(selected) if selected else None
    if (selected_path is None or '..' in selected_path.parts or
            not any(selected_path.is_relative_to(prefix)
                    for prefix in ('/lib/modules', '/usr/lib/modules'))):
        selected = None
    selected_hash = file_hash(root / selected.lstrip('/')) if selected else None
    loaded = (root / 'sys/module/apple_avd').is_dir()
    memory = read_text(root / 'proc/meminfo') or ''
    memory_match = re.search(r'^MemTotal:\s+(\d+) kB$', memory, re.M)
    tools = {name: bool(available(name)) for name in TOOLS}
    driver_hash = file_hash(root / 'usr/lib/dri/v4l2_request_drv_video.so')
    uapi = {name: file_hash(root / 'usr/include/linux' / name)
            for name in ('videodev2.h', 'v4l2-controls.h')}
    blockers = []
    if machine != 'aarch64':
        blockers.append('architecture_not_aarch64')
    if not any(value.startswith('apple,') for value in compatible):
        blockers.append('not_apple_device')
    blockers.extend('missing_package:' + name for name in REQUIRED_PACKAGES if not packages[name])
    blockers.extend('missing_tool:' + name for name in TOOLS if not tools[name])
    if not loaded:
        blockers.append('apple_avd_not_loaded')
    if selected_hash is None:
        blockers.append('module_file_identity_unavailable')
    if not any(node['apple_avd'] for node in devices):
        blockers.append('no_apple_avd_video_node')
    if not driver_hash:
        blockers.append('installed_driver_hash_unavailable')
    if any(value is None for value in uapi.values()):
        blockers.append('userspace_uapi_headers_unavailable')
    return {
        'schema_version': 1,
        'record_kind': 'read_only_inventory',
        'device_id': device_id,
        'collected_at': datetime.now(timezone.utc).isoformat(),
        'hardware_qualified': False,
        'support_status': 'experimental',
        'host': {'architecture': machine, 'compatible': compatible,
                 'model': read_text(root / 'proc/device-tree/model'),
                 'memory_total_kib': int(memory_match.group(1)) if memory_match else None},
        'kernel': {'release': release, 'firmware_identity': 'unknown',
                   'userspace_uapi_headers_sha256': uapi,
                   'uapi_note': 'Installed userspace headers, not proof of running kernel features.'},
        'packages': packages,
        'installed_driver': {'sha256': driver_hash, 'source_commit': 'unknown',
                             'note': 'Installed file only; no driver was loaded by this collector.'},
        'module': {'loaded': loaded, 'loaded_binary_identity': 'unknown',
                   'loaded_binary_sha256': None, 'selected_file': selected,
                   'selected_file_sha256': selected_hash,
                   'note': 'Selected file is for next load; loaded file identity needs separate evidence.'},
        'devices': devices,
        'tools_available': tools,
        'capabilities': {codec: {'status': 'not_probed', 'profiles': None}
                         for codec in ('h264', 'hevc', 'vp9', 'av1')},
        'preflight': {'status': 'blocked' if blockers else 'inventory_complete',
                      'blockers': blockers,
                      'note': 'Inventory only. Does not check idle state, journal faults or acquire a lease.'},
        'tests': {name: {'status': 'not_run', 'reason': 'inventory_only'} for name in
                  ('capabilities', 'smoke', 'conformance', 'export', 'lifecycle', 'clients', 'boot')},
        'qualification_gates': ['guarded_idle_and_fault_preflight', 'exact_candidate_provenance',
                                'capability_query', 'full_applicable_suites_and_exact_pass_sets',
                                'export_lifecycle_client_evidence', 'unresolved_reset_corruption_review'],
    }


def write_record(path, record):
    # Exclusive create also refuses symlinks and preserves previous evidence.
    with path.open('x') as stream:
        json.dump(record, stream, indent=2, sort_keys=True)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device-id', required=True, help='public pseudonym, never a serial number')
    parser.add_argument('--output', type=Path, required=True, help='new JSON file; existing files refused')
    args = parser.parse_args()
    try:
        record = collect(args.device_id)
        script = Path(__file__).resolve()
        revision = command('git', '-C', str(script.parents[1]), 'rev-parse', 'HEAD')
        record['collector'] = {'git_commit': revision if re.fullmatch(r'[0-9a-f]{40}', revision or '') else None,
                               'script_sha256': file_hash(script), 'python_version': platform.python_version()}
        write_record(args.output, record)
    except (OSError, ValueError) as error:
        print('Inventory not written: ' + str(error), file=sys.stderr)
        return 1
    print('Inventory recorded; hardware remains unqualified.')
    for blocker in record['preflight']['blockers']:
        print('Blocked: ' + blocker)
    return 2 if record['preflight']['blockers'] else 0


if __name__ == '__main__':
    sys.exit(main())
