#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Synthetic VP9 headers and containers; no corpus download or decoder access.

Every fixture is built here, so the scanner's behaviour is tested rather than
its output being compared against a recorded run.
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCAN = Path(__file__).with_name('vp9-sub64-scan.py')
spec = importlib.util.spec_from_file_location('scan', SCAN)
scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan)


def frame(width, height, profile=0, render=None, key=True, ten_bit=False,
          marker=2, sync=scan.SYNC_CODE, show_existing=False, subsampling=(1, 0)):
    """Build a VP9 uncompressed header prefix (not a decodable frame)."""
    b = f'{marker:02b}'
    b += f'{profile & 1:01b}{(profile >> 1) & 1:01b}'
    if profile == 3:
        b += '0'
    b += '1' if show_existing else '0'
    if show_existing:
        b += '000'
        return _pad(b)
    b += '0' if key else '1'      # frame_type
    b += '1'                      # show_frame
    b += '0'                      # error_resilient_mode
    if not key:
        return _pad(b)
    b += f'{sync:024b}'
    if profile >= 2:
        b += '1' if ten_bit else '0'
    b += '000'                    # color_space (not CS_RGB)
    b += '0'                      # color_range
    if profile in (1, 3):
        b += f'{subsampling[0]:01b}{subsampling[1]:01b}0'  # ssx, ssy, reserved
    b += f'{width - 1:016b}{height - 1:016b}'
    if render and render != (width, height):
        b += '1' + f'{render[0] - 1:016b}{render[1] - 1:016b}'
    else:
        b += '0'
    return _pad(b)


def _pad(bits):
    bits += '0' * (-len(bits) % 8)
    return int(bits, 2).to_bytes(len(bits) // 8, 'big')


def ivf(payload):
    hdr = bytearray(b'DKIF' + (0).to_bytes(2, 'little') + (32).to_bytes(2, 'little'))
    hdr += b'VP90' + (0).to_bytes(2, 'little') * 2
    hdr += bytes(32 - len(hdr))
    return bytes(hdr) + len(payload).to_bytes(4, 'little') + bytes(8) + payload


def _elem(eid, payload):
    eid_b = eid.to_bytes((eid.bit_length() + 7) // 8, 'big')
    size = len(payload)
    return eid_b + (0x80 | size).to_bytes(1, 'big') + payload if size < 0x7F else \
        eid_b + (0x4000 | size).to_bytes(2, 'big') + payload


def webm(payload, flags=0x80, track=1):
    block = bytes([0x80 | track]) + (0).to_bytes(2, 'big') + bytes([flags]) + payload
    cluster = _elem(0x1F43B675, _elem(0xA3, block))
    segment = _elem(0x18538067, cluster)
    return b'\x1a\x45\xdf\xa3\x84\x00\x00\x00\x00' + segment


class Header(unittest.TestCase):
    def test_sub64_is_classified_below_the_minimum(self):
        for w, h in ((8, 8), (8, 34), (34, 8), (63, 63), (66, 32), (32, 66)):
            info = scan.classify_frame(frame(w, h))
            info.update(scan.verdict(info))
            self.assertTrue(info['parsed'], (w, h))
            self.assertEqual((info['coded_width'], info['coded_height']), (w, h))
            self.assertEqual(info['classification'], 'below_avd_minimum', (w, h))

    def test_at_and_above_the_minimum_is_within(self):
        for w, h in ((64, 64), (64, 66), (66, 64), (1920, 1080)):
            info = scan.classify_frame(frame(w, h))
            info.update(scan.verdict(info))
            self.assertEqual(info['classification'], 'within_avd_minimum', (w, h))

    def test_which_dimension_is_below_is_reported(self):
        info = scan.classify_frame(frame(8, 128))
        self.assertEqual(scan.verdict(info)['below'], ['width'])
        info = scan.classify_frame(frame(128, 8))
        self.assertEqual(scan.verdict(info)['below'], ['height'])
        info = scan.classify_frame(frame(8, 8))
        self.assertEqual(scan.verdict(info)['below'], ['width', 'height'])

    def test_decoded_format_padding_does_not_change_the_verdict(self):
        # The negotiated format is already padded past the frame size; a padded
        # allocation is therefore not evidence that the frame size is accepted.
        v = scan.verdict(scan.classify_frame(frame(8, 8)))
        self.assertEqual(v['aligned_decoded_format'], [64, 16])
        self.assertEqual(v['classification'], 'below_avd_minimum')

    def test_render_size_is_read_separately_from_the_coded_size(self):
        info = scan.classify_frame(frame(64, 64, render=(40, 40)))
        self.assertEqual((info['render_width'], info['render_height']), (40, 40))
        self.assertTrue(info['render_differs'])
        # A small *display* size on a >=64 coded frame is supported; it is the
        # coded size that the kernel checks.
        self.assertEqual(scan.verdict(info)['classification'], 'within_avd_minimum')

    def test_bit_depth_and_chroma(self):
        self.assertEqual(scan.classify_frame(frame(64, 64))['bit_depth'], 8)
        self.assertEqual(scan.classify_frame(frame(64, 64, profile=2, ten_bit=True))['bit_depth'], 12)
        self.assertEqual(scan.classify_frame(frame(64, 64, profile=2))['bit_depth'], 10)
        # Profile 0/2 imply 4:2:0; profiles 1/3 code the subsampling explicitly,
        # which is how the suite's two profile-1 vectors differ from the rest.
        self.assertEqual(scan.classify_frame(frame(64, 64))['chroma'], '4:2:0')
        self.assertEqual(scan.classify_frame(frame(64, 64, profile=1,
                                                   subsampling=(1, 0)))['chroma'], '4:2:2')
        self.assertEqual(scan.classify_frame(frame(64, 64, profile=1,
                                                   subsampling=(0, 0)))['chroma'], '4:4:4')

    def test_tile_geometry_forces_one_column_below_64(self):
        for w in (8, 10, 16, 18, 32, 34, 63, 64, 66):
            info = scan.classify_frame(frame(w, 64))
            self.assertTrue(info['single_tile_column_forced'], w)
            self.assertEqual(info['tile_cols_log2_max'], 0, w)
        # A wide frame can legally carry more than one tile column.
        self.assertFalse(scan.classify_frame(frame(4096, 64))['single_tile_column_forced'])

    def test_mi_cols_differ_between_a_sub64_frame_and_a_padded_claim(self):
        # The basis of the decision: declaring 64 for an 8-pixel-wide frame
        # changes MiCols, which drives partition availability during decode.
        self.assertEqual(scan.classify_frame(frame(8, 8))['mi_cols'], 1)
        self.assertEqual(scan.classify_frame(frame(64, 64))['mi_cols'], 8)


class Malformed(unittest.TestCase):
    def test_bad_marker_sync_and_truncation_are_reported_not_raised(self):
        for data in (frame(8, 8, marker=0), frame(8, 8, sync=0x123456),
                     frame(8, 8)[:3], b'', b'\xff'):
            info = scan.classify_frame(data)
            self.assertFalse(info['parsed'])
            self.assertTrue(info['error'])
            self.assertEqual(scan.verdict(info)['classification'], 'unparsed')

    def test_show_existing_and_inter_frames_are_not_guessed(self):
        self.assertFalse(scan.classify_frame(frame(8, 8, show_existing=True))['parsed'])
        self.assertFalse(scan.classify_frame(frame(8, 8, key=False))['parsed'])

    def test_reserved_zero_must_be_clear(self):
        bits = '10' + '11' + '1'          # marker, profile 3, reserved_zero set
        self.assertFalse(scan.classify_frame(_pad(bits))['parsed'])


class Containers(unittest.TestCase):
    def test_ivf_and_webm_yield_the_same_header(self):
        payload = frame(8, 8)
        for blob in (ivf(payload), webm(payload), payload):
            self.assertEqual(scan.first_frame(blob)[:len(payload)], payload)

    def test_laced_blocks_are_rejected_rather_than_misparsed(self):
        with self.assertRaises(ValueError):
            scan.first_frame(webm(frame(8, 8), flags=0x82))

    def test_truncated_containers_are_rejected(self):
        for blob in (ivf(frame(8, 8))[:20], b'DKIF' + bytes(28),
                     b'\x1a\x45\xdf\xa3\x84\x00\x00\x00\x00'):
            with self.assertRaises(ValueError):
                scan.first_frame(blob)

    def test_element_overrunning_its_parent_is_rejected(self):
        bad = b'\x1a\x45\xdf\xa3\x84\x00\x00\x00\x00' + b'\x18\x53\x80\x67\x84\xa3\xff\xff\xff'
        with self.assertRaises(ValueError):
            scan.first_frame(bad)


class CrossCheck(unittest.TestCase):
    """The scanner must refuse to smooth over a contradiction with the baseline."""

    def _run(self, name, payload, failing, passing):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / 'vectors').mkdir()
            (d / 'vectors' / name).write_bytes(payload)
            (d / 'sets.json').write_text(json.dumps(
                {'suites': {'vp9': {'failing_vectors': failing,
                                    'passing_vectors': passing}}}))
            p = subprocess.run([sys.executable, str(SCAN), '--pass-sets',
                                str(d / 'sets.json'), str(d / 'vectors')],
                               capture_output=True, text=True)
            return p.returncode, json.loads(p.stdout)

    def test_consistent_baseline_passes(self):
        rc, rep = self._run('a.ivf', ivf(frame(8, 8)), ['a.ivf'], [])
        self.assertEqual(rc, 0)
        self.assertTrue(rep['cross_check']['consistent'])
        self.assertEqual(rep['counts']['below_avd_minimum'], 1)

    def test_below_minimum_recorded_as_passing_is_an_error(self):
        rc, rep = self._run('a.ivf', ivf(frame(8, 8)), [], ['a.ivf'])
        self.assertEqual(rc, 1)
        self.assertFalse(rep['cross_check']['consistent'])
        self.assertEqual(rep['cross_check']['below_minimum_but_recorded_passing'], ['a.ivf'])

    def test_unreadable_vector_is_reported_not_counted_as_supported(self):
        rc, rep = self._run('a.ivf', b'DKIF' + bytes(28), [], [])
        self.assertEqual(rc, 0)
        self.assertEqual(rep['counts'].get('unparsed'), 1)
        self.assertNotIn('within_avd_minimum', rep['counts'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
