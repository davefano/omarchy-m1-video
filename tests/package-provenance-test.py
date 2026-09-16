#!/usr/bin/env python3
"""Offline archive fixtures; never install or load the generated test ELF."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import subprocess
import tarfile
import tempfile
import unittest

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
