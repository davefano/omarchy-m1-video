#!/usr/bin/env python3
"""Offline archive fixtures; never install or load the generated test ELF."""
import hashlib
from contextlib import contextmanager
import importlib.util
import io
import json
from pathlib import Path
import struct
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('provenance', ROOT / 'tools/package-provenance.py')
provenance = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(provenance)


class ProvenanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='package-provenance-test-')
        cls.root = Path(cls.temp.name)
        cls.repo = cls.root / 'repo'
        (cls.repo / 'libva').mkdir(parents=True)
        (cls.repo / 'patches').mkdir()
        (cls.repo / 'libva/PKGBUILD').write_text("pkgname=libva-v4l2_request-avd\npkgver=1.3.r11\npkgrel=1\n_commit=" + 'd' * 40 + "\n")
        (cls.repo / 'patches/0001-test.patch').write_text('fixture patch\n')
        subprocess.run(['git', 'init', '-q', str(cls.repo)], check=True)
        subprocess.run(['git', '-C', str(cls.repo), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(cls.repo), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture'], check=True)
        source = cls.root / 'driver.c'
        source.write_text('const char marker[] = "v4l2-request (omarchy-m1-video 1.3.r11)";\nint __vaDriverInit_1_24(void) { return 0; }\n')
        binary = cls.root / 'driver.so'
        subprocess.run(['cc', '-shared', '-fPIC', '-o', str(binary), str(source)], check=True)
        subprocess.run(['strip', '--strip-unneeded', str(binary)], check=True)
        # Synthetic fixture is only inspected, never executed. CI can run on x86_64.
        elf = bytearray(binary.read_bytes())
        elf[18:20] = struct.pack('<H', 183)  # EM_AARCH64
        cls.driver = bytes(elf)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def package(self, *, uid=0, alias='v4l2_request_drv_video.so', depends=None,
                extra=None, driver=None, recipe_hash=None, duplicate=False):
        path = self.root / 'fixture.pkg.tar.xz'
        dependency_lines = depends if depends is not None else ['glibc', 'libva>=2.24', 'libva<3']
        pkginfo = ('pkgname = libva-v4l2_request-avd\npkgver = 1.3.r11-1\narch = aarch64\n'
                   'provides = libva-v4l2_request\nconflict = libva-v4l2_request\n' +
                   ''.join('depend = ' + dep + '\n' for dep in dependency_lines))
        recipe_hash = recipe_hash or hashlib.sha256((self.repo / 'libva/PKGBUILD').read_bytes()).hexdigest()
        buildinfo = ('format = 2\npkgname = libva-v4l2_request-avd\npkgver = 1.3.r11-1\npkgarch = aarch64\n'
                     'pkgbuild_sha256sum = ' + recipe_hash + '\n'
                     'builddate = 1\nbuilddir = /build\nbuildenv = !distcc\noptions = strip\n'
                     'installed = gcc-16.1.1-1-aarch64\ninstalled = libva-2.24.1-1-aarch64\n')
        members = [('.PKGINFO', pkginfo.encode()), ('.BUILDINFO', buildinfo.encode()),
                   ('usr/lib/dri/v4l2_request_drv_video.so', self.driver if driver is None else driver)]
        if extra:
            members.append(extra)
        if duplicate:
            members.append(members[0])
        with tarfile.open(path, 'w:xz') as archive:
            for name, data in members:
                member = tarfile.TarInfo(name)
                member.size = len(data)
                member.uid = uid
                archive.addfile(member, io.BytesIO(data))
            member = tarfile.TarInfo('usr/lib/dri/asahi_drv_video.so')
            member.type = tarfile.SYMTYPE
            member.linkname = alias
            archive.addfile(member)
        return path

    def manifest(self, **kwargs):
        return provenance.generate(self.repo, self.package(**kwargs), observe_host=False)

    def test_valid_archive_and_schema(self):
        doc = self.manifest()
        self.assertEqual(doc['driver']['entrypoints'], ['__vaDriverInit_1_24'])
        self.assertEqual(doc['source']['driver_commit'], 'd' * 40)
        self.assertEqual(doc['driver']['sha256'], hashlib.sha256(self.driver).hexdigest())
        self.assertEqual(doc['kernel']['loaded_module']['identity'], 'unknown')
        self.assertEqual(doc['hardware_evidence']['status'], 'not_provided')
        self.assertEqual(len(doc['patches']), 1)
        self.validate_schema(doc)

    def validate_schema(self, doc):
        import jsonschema
        schema = json.loads((ROOT / 'docs/package-provenance.schema.json').read_text())
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.validate(doc, schema)

    def test_root_ownership(self):
        with self.assertRaisesRegex(ValueError, 'root ownership'):
            self.manifest(uid=1000)

    def test_wrong_alias(self):
        with self.assertRaisesRegex(ValueError, 'alias'):
            self.manifest(alias='../../../../tmp/driver.so')

    def test_dependency_bounds(self):
        for deps in (['glibc', 'libva'], ['glibc', 'libva>=2.23', 'libva<3'],
                     ['glibc', 'libva>=3', 'libva<3'], ['libva>=2.24', 'libva<3']):
            with self.subTest(depends=deps), self.assertRaisesRegex(ValueError, 'depend'):
                self.manifest(depends=deps)
        self.manifest(depends=['glibc', 'libva>=2.25', 'libva<3'])

    def test_recipe_hash_binding(self):
        with self.assertRaisesRegex(ValueError, 'PKGBUILD hash'):
            self.manifest(recipe_hash='0' * 64)

    def test_traversal_and_duplicate(self):
        for path in ('../escape', '/tmp/escape', 'usr/../escape'):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'unsafe archive'):
                self.manifest(extra=(path, b'bad'))
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.manifest(duplicate=True)

    def test_marker_and_entrypoint_must_be_real(self):
        with self.assertRaisesRegex(ValueError, 'ELF'):
            self.manifest(driver=b'v4l2-request (omarchy-m1-video 1.3.r11) __vaDriverInit_1_24')
        with self.assertRaisesRegex(ValueError, 'marker'):
            self.manifest(driver=self.driver.replace(b'1.3.r11', b'1.3.r10'))
        with self.assertRaisesRegex(ValueError, 'entrypoint'):
            self.manifest(driver=self.driver.replace(b'__vaDriverInit_1_24', b'__vaDriverGone_1_24'))

    def test_undefined_symbol_and_embedded_string_are_not_entrypoints(self):
        source = self.root / 'undefined.c'
        source.write_text('const char marker[] = "v4l2-request (omarchy-m1-video 1.3.r11)";\n'
                          'extern int __vaDriverInit_1_24(void);\n'
                          'int call(void) { return __vaDriverInit_1_24(); }\n')
        binary = self.root / 'undefined.so'
        subprocess.run(['cc', '-shared', '-fPIC', '-o', str(binary), str(source)], check=True)
        subprocess.run(['strip', '--strip-unneeded', str(binary)], check=True)
        elf = bytearray(binary.read_bytes())
        elf[18:20] = struct.pack('<H', 183)
        with self.assertRaisesRegex(ValueError, 'entrypoint'):
            self.manifest(driver=bytes(elf))

    def test_noncanonical_entrypoint_is_rejected(self):
        source = self.root / 'noncanonical.c'
        source.write_text('const char marker[] = "v4l2-request (omarchy-m1-video 1.3.r11)";\n'
                          'int __vaDriverInit_1_024(void) { return 0; }\n')
        binary = self.root / 'noncanonical.so'
        subprocess.run(['cc', '-shared', '-fPIC', '-o', str(binary), str(source)], check=True)
        subprocess.run(['strip', '--strip-unneeded', str(binary)], check=True)
        elf = bytearray(binary.read_bytes())
        elf[18:20] = struct.pack('<H', 183)
        with self.assertRaisesRegex(ValueError, 'entrypoint'):
            self.manifest(driver=bytes(elf))

    def test_schema_requires_canonical_entrypoints(self):
        import jsonschema
        doc = self.manifest()
        for suffix in ('0', '24'):
            with self.subTest(suffix=suffix):
                doc['driver']['entrypoints'] = ['__vaDriverInit_1_' + suffix]
                self.validate_schema(doc)
        for suffix in ('00', '024'):
            with self.subTest(suffix=suffix):
                doc['driver']['entrypoints'] = ['__vaDriverInit_1_' + suffix]
                with self.assertRaises(jsonschema.ValidationError):
                    self.validate_schema(doc)

    @contextmanager
    def host_environment(self, *, kernel='linux-asahi 7.1.13-1',
                         headers='linux-asahi-headers 7.1.13-1', module=None, loaded=False):
        responses = {('pacman', '-Q', 'linux-asahi'): kernel,
                     ('pacman', '-Q', 'linux-asahi-headers'): headers,
                     ('modinfo', '-k', 'fixture-release', '-n', 'apple_avd'): module}
        real_is_dir = Path.is_dir

        def loaded_module_present(path):
            if path == Path('/sys/module/apple_avd'):
                return loaded
            return real_is_dir(path)

        with mock.patch.object(provenance.platform, 'release', return_value='fixture-release'), \
                mock.patch.object(provenance, 'optional_command', side_effect=lambda *args: responses[args]), \
                mock.patch.object(Path, 'is_dir', autospec=True, side_effect=loaded_module_present):
            yield

    def test_host_kernel_package_versions(self):
        cases = [('linux-asahi 7.1.13-1', 'linux-asahi-headers 7.1.13-1', True),
                 ('linux-asahi 7.1.13-1', 'linux-asahi-headers 7.1.14-1', False),
                 (None, 'linux-asahi-headers 7.1.13-1', None),
                 ('linux-asahi 7.1.13-1', None, None),
                 (None, None, None)]
        for kernel, headers, matches in cases:
            with self.subTest(kernel=kernel, headers=headers), \
                    self.host_environment(kernel=kernel, headers=headers):
                observed = provenance.host_kernel()
                self.assertEqual(observed['observation'], 'read_only_build_host')
                self.assertEqual(observed['running_release'], 'fixture-release')
                self.assertEqual(observed['kernel_package'], kernel)
                self.assertEqual(observed['headers_package'], headers)
                self.assertIs(observed['package_versions_match'], matches)

    def test_host_kernel_selected_module_hash(self):
        module = self.root / 'apple_avd.ko'
        module.write_bytes(b'selected on-disk module fixture')
        with self.host_environment(module=str(module)):
            observed = provenance.host_kernel()
        self.assertEqual(observed['selected_module'], {
            'path': str(module), 'sha256': hashlib.sha256(module.read_bytes()).hexdigest(),
            'identity': 'on_disk_only'})
        self.assertEqual(observed['loaded_module']['identity'], 'unknown')

    def test_host_kernel_selected_module_hash_failure(self):
        module = self.root / 'unreadable.ko'
        module.write_bytes(b'fixture')
        with self.host_environment(module=str(module)), \
                mock.patch.object(provenance, 'file_hash', side_effect=PermissionError('unreadable')) as digest:
            observed = provenance.host_kernel()
        digest.assert_called_once_with(str(module))
        self.assertEqual(observed['selected_module'], {
            'path': str(module), 'sha256': None, 'identity': 'unknown'})

    def test_host_kernel_missing_selected_module(self):
        for module in (None, str(self.root / 'missing.ko')):
            with self.subTest(module=module), self.host_environment(module=module), \
                    mock.patch.object(provenance, 'file_hash') as digest:
                observed = provenance.host_kernel()
            digest.assert_not_called()
            self.assertEqual(observed['selected_module'], {
                'path': None, 'sha256': None, 'identity': 'unknown'})

    def test_generate_observes_host_without_claiming_loaded_identity(self):
        module = self.root / 'integration.ko'
        module.write_bytes(b'integration module fixture')
        package = self.package()
        for loaded in (True, False):
            with self.subTest(loaded=loaded), self.host_environment(module=str(module), loaded=loaded):
                # Older pathlib glob implementations inspect this directory
                # through is_dir; sysfs mocking must preserve that behavior.
                self.assertTrue((self.repo / 'patches').is_dir())
                self.assertFalse((self.repo / 'missing-directory').is_dir())
                doc = provenance.generate(self.repo, package, observe_host=True)
                self.assertEqual(doc['kernel']['observation'], 'read_only_build_host')
                self.assertEqual(doc['kernel']['running_release'], 'fixture-release')
                self.assertTrue(doc['kernel']['package_versions_match'])
                self.assertEqual(doc['kernel']['selected_module']['sha256'], hashlib.sha256(module.read_bytes()).hexdigest())
                self.assertEqual(doc['kernel']['selected_module']['identity'], 'on_disk_only')
                self.assertIs(doc['kernel']['loaded_module']['present'], loaded)
                self.assertEqual(doc['kernel']['loaded_module']['identity'], 'unknown')
                self.validate_schema(doc)

    def test_hardware_hash_and_source_link(self):
        path = self.package()
        evidence = self.root / 'evidence.json'
        record = {'driver_commit': 'd' * 40, 'package': {'driver_sha256': hashlib.sha256(self.driver).hexdigest()}}
        evidence.write_text(json.dumps(record))
        doc = provenance.generate(self.repo, path, evidence, observe_host=False)
        self.assertEqual(doc['hardware_evidence']['status'], 'matched_driver_and_source')
        record['package']['driver_sha256'] = '0' * 64
        evidence.write_text(json.dumps(record))
        doc = provenance.generate(self.repo, path, evidence, observe_host=False)
        self.assertEqual(doc['hardware_evidence']['status'], 'not_matched')
        self.assertFalse(doc['hardware_evidence']['driver_hash_matches'])
        record['package']['driver_sha256'] = hashlib.sha256(self.driver).hexdigest()
        record['driver_commit'] = 'a' * 40
        evidence.write_text(json.dumps(record))
        doc = provenance.generate(self.repo, path, evidence, observe_host=False)
        self.assertEqual(doc['hardware_evidence']['status'], 'not_matched')

    def test_historical_r11_preserves_unknowns(self):
        fixture = ROOT / 'docs/codec-validation-r11-2026-09-15.json'
        doc = provenance.normalize_historical(fixture)
        self.assertEqual(doc['kind'], 'historical_record')
        self.assertEqual(doc['driver']['sha256'], 'a9d6225e0fd348ca22fd738cb2367d7835d7cda1f789ba7b5aae278b32b6729b')
        self.assertIsNone(doc['source']['repository_commit'])
        self.assertIsNone(doc['driver']['entrypoints'])
        self.assertIsNone(doc['build'])
        self.assertEqual(doc['kernel']['loaded_module']['identity'], 'unknown')
        self.validate_schema(doc)

    def test_cli_rejection_does_not_write_manifest(self):
        output = self.root / 'invalid.json'
        output.unlink(missing_ok=True)
        result = subprocess.run(['python3', str(ROOT / 'tools/package-provenance.py'), '--repo', str(self.repo),
                                 '--package', str(self.package(uid=1000)), '--output', str(output)], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())

    def test_cli_never_overwrites_existing_evidence(self):
        output = self.root / 'existing.json'
        output.write_text('existing evidence\n')
        result = subprocess.run(['python3', str(ROOT / 'tools/package-provenance.py'), '--repo', str(self.repo),
                                 '--package', str(self.package()), '--output', str(output)], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'output already exists', result.stderr)
        self.assertEqual(output.read_text(), 'existing evidence\n')


if __name__ == '__main__':
    unittest.main()
