#!/usr/bin/env python3
"""Inspect a package without installing, executing it or extracting its paths.

Metadata describes the build; it is not a signature or an independent attestation.
Only an exact driver hash AND source pin link supplied historical hardware evidence.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import subprocess
import sys
import tarfile
import tempfile

DRIVER = 'usr/lib/dri/v4l2_request_drv_video.so'
ALIAS = 'usr/lib/dri/asahi_drv_video.so'
PACKAGE_NAME = 'libva-v4l2_request-avd'
HASH = re.compile(r'[0-9a-f]{64}')
COMMIT = re.compile(r'[0-9a-f]{40}')


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def command(*args, cwd=None):
    return subprocess.run(args, cwd=cwd, check=True, text=True, capture_output=True,
                          env={**os.environ, 'LC_ALL': 'C'}, timeout=30).stdout.strip()


def optional_command(*args):
    try:
        return command(*args) or None
    except (OSError, subprocess.SubprocessError):
        return None


def metadata(data):
    result = {}
    for line in data.decode('utf-8').splitlines():
        if not line or line.startswith('#'):
            continue
        key, separator, value = line.partition(' = ')
        if not separator or not key or not value:
            raise ValueError('malformed package metadata')
        result.setdefault(key, []).append(value)
    return result


def one(values, key):
    found = values.get(key, [])
    if len(found) != 1:
        raise ValueError('expected one metadata field: ' + key)
    return found[0]


def recipe(repo):
    path = repo / 'libva/PKGBUILD'
    data = path.read_bytes()
    text = data.decode('utf-8')
    result = {}
    # Deliberately do not source a PKGBUILD: inspecting evidence must not run it.
    for name in ('pkgname', 'pkgver', 'pkgrel', '_commit'):
        matches = re.findall(r'^' + name + r"=['\"]?([a-zA-Z0-9._+-]+)['\"]?\s*$", text, re.M)
        if len(matches) != 1:
            raise ValueError('expected one literal PKGBUILD value: ' + name)
        result[name] = matches[0]
    if result['pkgname'] != PACKAGE_NAME or not COMMIT.fullmatch(result['_commit']):
        raise ValueError('unexpected PKGBUILD package name or source commit')
    result['sha256'] = sha256(data)
    return result


def inspect_archive(package):
    contents = {}
    members = []
    seen = set()
    # tarfile supports makepkg .tar.xz and .tar.gz without external commands.
    # We never extract paths from the archive, including links.
    with tarfile.open(package, 'r:*') as archive:
        for item in archive:
            path = PurePosixPath(item.name)
            if path.is_absolute() or '..' in path.parts or not path.parts:
                raise ValueError('unsafe archive path: ' + item.name)
            name = str(path)
            if name in seen:
                raise ValueError('duplicate archive path: ' + name)
            seen.add(name)
            if item.uid != 0 or item.gid != 0:
                raise ValueError('package member lacks root ownership: ' + name)
            if not (item.isfile() or item.isdir() or item.issym()):
                raise ValueError('unsupported archive member type: ' + name)
            if item.issym() and (name != ALIAS or item.linkname != 'v4l2_request_drv_video.so'):
                raise ValueError('unexpected package alias: ' + name)
            members.append({'path': name, 'uid': item.uid, 'gid': item.gid,
                            'mode': oct(item.mode), 'size': item.size,
                            'type': 'file' if item.isfile() else 'directory' if item.isdir() else 'symlink',
                            'link': item.linkname if item.issym() else None})
            if name in ('.PKGINFO', '.BUILDINFO', DRIVER):
                if not item.isfile() or item.size > 64 * 1024 * 1024:
                    raise ValueError('invalid or oversized required package member: ' + name)
                contents[name] = archive.extractfile(item).read()
    for name in ('.PKGINFO', '.BUILDINFO', DRIVER):
        if name not in contents:
            raise ValueError('missing package member: ' + name)
    aliases = [member for member in members if member['path'] == ALIAS]
    if len(aliases) != 1 or aliases[0]['type'] != 'symlink':
        raise ValueError('missing driver alias')
    return contents, members


def inspect_driver(data, marker):
    if len(data) < 20 or data[:6] != b'\x7fELF\x02\x01':
        raise ValueError('driver must be a little-endian 64-bit ELF')
    if int.from_bytes(data[16:18], 'little') != 3:
        raise ValueError('driver ELF must be a shared object')
    if int.from_bytes(data[18:20], 'little') != 183:
        raise ValueError('driver ELF machine must be AArch64')
    if marker.encode() + b'\0' not in data:
        raise ValueError('driver marker does not match package version')
    with tempfile.TemporaryDirectory(prefix='package-provenance-') as directory:
        path = Path(directory) / 'driver.so'
        path.write_bytes(data)
        inspection = command('readelf', '--dyn-syms', '--sections', '--wide', str(path))
    entrypoints = set()
    for line in inspection.splitlines():
        fields = line.split()
        if len(fields) != 8:
            continue
        _, _, _, kind, binding, visibility, index, name = fields
        if (kind == 'FUNC' and binding in ('GLOBAL', 'WEAK') and visibility in ('DEFAULT', 'PROTECTED')
                and index != 'UND' and re.fullmatch(r'__vaDriverInit_1_(0|[1-9][0-9]*)', name)):
            entrypoints.add(name)
    if len(entrypoints) != 1:
        raise ValueError('expected one defined exported VA ABI 1 entrypoint')
    if re.search(r'\s(?:\.symtab|\.debug_\S*)\s', inspection):
        raise ValueError('packaged driver is not stripped')
    return {'path': DRIVER, 'sha256': sha256(data), 'stripped': True,
            'marker': marker, 'entrypoints': sorted(entrypoints), 'elf_machine': 'AArch64'}


def validate_metadata(pkginfo, buildinfo, expected, driver):
    version = expected['pkgver'] + '-' + expected['pkgrel']
    for key, value in (('pkgname', PACKAGE_NAME), ('pkgver', version), ('arch', 'aarch64')):
        if one(pkginfo, key) != value:
            raise ValueError('unexpected package metadata: ' + key)
    for key, value in (('format', '2'), ('pkgname', PACKAGE_NAME), ('pkgver', version), ('pkgarch', 'aarch64')):
        if one(buildinfo, key) != value:
            raise ValueError('unexpected build metadata: ' + key)
    if one(buildinfo, 'pkgbuild_sha256sum') != expected['sha256']:
        raise ValueError('PKGBUILD hash does not match .BUILDINFO')
    for field in ('installed', 'options', 'buildenv', 'builddir', 'builddate'):
        if not buildinfo.get(field):
            raise ValueError('missing build metadata: ' + field)
    dependencies = pkginfo.get('depend', [])
    minor = int(driver['entrypoints'][0].rsplit('_', 1)[1])
    lower_bounds = [int(match.group(1)) for dependency in dependencies
                    if (match := re.fullmatch(r'libva>=2\.(\d+)', dependency))]
    if ('glibc' not in dependencies or 'libva<3' not in dependencies
            or len(lower_bounds) != 1 or lower_bounds[0] < minor):
        raise ValueError('dependencies must include glibc, libva>=2.<VA minor> and libva<3')
    for field in ('provides', 'conflict'):
        if pkginfo.get(field) != ['libva-v4l2_request']:
            raise ValueError('unexpected package metadata: ' + field)


def unknown_kernel():
    return {'observation': 'not_observed', 'running_release': None, 'kernel_package': None,
            'headers_package': None, 'package_versions_match': None,
            'selected_module': {'path': None, 'sha256': None, 'identity': 'unknown'},
            'loaded_module': {'present': None, 'identity': 'unknown',
                              'reason': 'A file selected for the next load does not identify an already loaded binary.'}}


def host_kernel():
    result = unknown_kernel()
    result.update(observation='read_only_build_host', running_release=platform.release(),
                  kernel_package=optional_command('pacman', '-Q', 'linux-asahi'),
                  headers_package=optional_command('pacman', '-Q', 'linux-asahi-headers'))
    if result['kernel_package'] and result['headers_package']:
        result['package_versions_match'] = result['kernel_package'].split()[-1] == result['headers_package'].split()[-1]
    path = optional_command('modinfo', '-k', result['running_release'], '-n', 'apple_avd')
    if path and Path(path).is_file():
        try:
            result['selected_module'] = {'path': path, 'sha256': file_hash(path), 'identity': 'on_disk_only'}
        except OSError:
            result['selected_module']['path'] = path
    result['loaded_module']['present'] = Path('/sys/module/apple_avd').is_dir()
    return result


def evidence_link(path, driver_hash, source_commit):
    if path is None:
        return {'status': 'not_provided', 'path': None, 'sha256': None,
                'driver_hash_matches': None, 'source_commit_matches': None,
                'scope': 'No hardware validation performed by this tool.'}
    record = json.loads(Path(path).read_text())
    if not isinstance(record, dict) or not isinstance(record.get('package'), dict):
        raise ValueError('hardware evidence must contain a package object')
    recorded_hash = record.get('package', {}).get('driver_sha256')
    recorded_commit = record.get('driver_commit')
    hash_matches = bool(isinstance(recorded_hash, str) and HASH.fullmatch(recorded_hash)
                        and recorded_hash == driver_hash)
    source_matches = bool(isinstance(recorded_commit, str) and COMMIT.fullmatch(recorded_commit)
                          and recorded_commit == source_commit)
    return {'status': 'matched_driver_and_source' if hash_matches and source_matches else 'not_matched',
            'path': str(path), 'sha256': file_hash(path), 'driver_hash_matches': hash_matches,
            'source_commit_matches': source_matches,
            'scope': 'Identity link to the supplied record only; its tests, limitations and trust remain those of that record.'}


def generate(repo, package, hardware_evidence=None, *, observe_host=True, build_config=None):
    repo, package = Path(repo).resolve(), Path(package).resolve()
    expected = recipe(repo)
    contents, members = inspect_archive(package)
    pkginfo, buildinfo = metadata(contents['.PKGINFO']), metadata(contents['.BUILDINFO'])
    marker = 'v4l2-request (omarchy-m1-video ' + expected['pkgver'] + ')'
    driver = inspect_driver(contents[DRIVER], marker)
    validate_metadata(pkginfo, buildinfo, expected, driver)
    dirty = command('git', 'status', '--porcelain=v1', '--untracked-files=all', cwd=repo).splitlines()
    return {'schema_version': 1, 'kind': 'package_inspection',
            'source': {'repository_commit': command('git', 'rev-parse', 'HEAD', cwd=repo),
                       'dirty': bool(dirty), 'dirty_paths': dirty,
                       'driver_commit': expected['_commit'], 'pkgbuild_sha256': expected['sha256'],
                       'identity_scope': 'Declared source pin in recipe matched by .BUILDINFO hash; build metadata is not authenticated.'},
            'patches': [{'path': str(path.relative_to(repo)), 'sha256': file_hash(path)}
                        for path in sorted((repo / 'patches').glob('*.patch'))],
            'package': {'file': package.name, 'sha256': file_hash(package), 'metadata': pkginfo,
                        'root_ownership_verified': True, 'members': members},
            'build': {'metadata': buildinfo,
                      'makepkg_config': {'path': str(build_config), 'sha256': file_hash(build_config)} if build_config else None,
                      'pkginfo_sha256': sha256(contents['.PKGINFO']),
                      'buildinfo_sha256': sha256(contents['.BUILDINFO']),
                      'inspection_tools': {'python': platform.python_version(),
                                           'script_sha256': file_hash(__file__),
                                           'readelf': command('readelf', '--version').splitlines()[0]}},
            'driver': driver, 'kernel': host_kernel() if observe_host else unknown_kernel(),
            'hardware_evidence': evidence_link(hardware_evidence, driver['sha256'], expected['_commit']),
            'limitations': ['No installation, module load or hardware test performed.',
                            'Patch hashes describe this checkout; patches are not shipped in the VA driver package.',
                            'Build dependencies and options are recorded from .BUILDINFO; they are not independently attested.']}


def normalize_historical(path):
    """Retain known r11 identities without inventing missing modern build evidence."""
    path = Path(path)
    record = json.loads(path.read_text())
    package = record['package']
    kernel = unknown_kernel()
    kernel['observation'] = 'historical_record'
    kernel['kernel_package'] = record.get('kernel_package')
    return {'schema_version': 1, 'kind': 'historical_record',
            'source': {'repository_commit': None, 'dirty': None, 'dirty_paths': None,
                       'driver_commit': record.get('driver_commit'), 'pkgbuild_sha256': None,
                       'identity_scope': 'Copied from historical record; original source tree and package not inspected.'},
            'patches': None,
            'package': {'file': package.get('file'), 'sha256': package.get('sha256'),
                        'metadata': None, 'root_ownership_verified': None, 'members': None},
            'build': None,
            'driver': {'path': DRIVER, 'sha256': package.get('driver_sha256'), 'stripped': None,
                       'marker': package.get('marker'), 'entrypoints': None, 'elf_machine': None},
            'kernel': kernel,
            'hardware_evidence': {'status': 'historical_record', 'path': str(path), 'sha256': file_hash(path),
                                  'driver_hash_matches': None, 'source_commit_matches': None,
                                  'scope': record.get('scope', 'Historical record; no new validation performed.')},
            'limitations': ['Missing fields are null, not inferred from the current host or recipe.',
                            'Historical ownership/test claims remain in the original record; this tool has not repeated them.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--package', type=Path, help='makepkg .pkg.tar.xz or .pkg.tar.gz archive')
    inputs.add_argument('--normalize-evidence', type=Path, help='normalize historical r11 evidence without inspecting a package')
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--hardware-evidence', type=Path)
    parser.add_argument('--build-config', type=Path, help='effective makepkg configuration file; recorded by path and SHA-256')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.normalize_evidence and (args.hardware_evidence or args.build_config):
        parser.error('--hardware-evidence and --build-config require --package')
    try:
        if os.path.lexists(args.output):
            raise ValueError('output already exists; choose a new filename: ' + str(args.output))
        manifest = (normalize_historical(args.normalize_evidence) if args.normalize_evidence
                    else generate(args.repo, args.package, args.hardware_evidence, build_config=args.build_config))
        # An atomic exclusive link prevents partial output and never overwrites existing evidence.
        with tempfile.NamedTemporaryFile(mode='w', dir=args.output.parent, prefix='.provenance-', delete=False) as output:
            temporary = Path(output.name)
            try:
                json.dump(manifest, output, indent=2, sort_keys=True)
                output.write('\n')
                output.close()
                os.link(temporary, args.output)
            finally:
                temporary.unlink(missing_ok=True)
    except (OSError, ValueError, KeyError, TypeError, tarfile.TarError, subprocess.SubprocessError) as error:
        print('package provenance: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
