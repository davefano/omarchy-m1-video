#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Synthetic prefix fixtures; no corpus download or decoder access."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('scan', Path(__file__).with_name('h264-interlace-scan.py'))
scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan)


def ue(v):
    bits = f'{v + 1:b}'
    return '0' * (len(bits) - 1) + bits


def nal(kind, bits):
    # Terminate/pad synthetic prefixes; these are not full decodable pictures.
    bits += '1'
    bits += '0' * (-len(bits) % 8)
    raw = bytes([kind]) + int(bits, 2).to_bytes(len(bits) // 8, 'big')
    out = bytearray()
    zeros = 0
    for b in raw:
        if zeros == 2 and b <= 3:
            out.append(3)
            zeros = 0
        out.append(b)
        zeros = zeros + 1 if b == 0 else 0
    return b'\x00\x00\x00\x01' + out


def sps(sid=0, framebits=4, frameonly=0, separate=False, mbaff=0):
    bits = f'{244 if separate else 77:08b}' + '00000000' + '00011110' + ue(sid)
    if separate:
        bits += ue(3) + '1' + ue(0) + ue(0) + '00'
    bits += ue(framebits - 4) + ue(0) + ue(0) + ue(1) + '0' + ue(1) + ue(1)
    bits += str(frameonly) + (str(mbaff) if not frameonly else '') + '1'
    return nal(7, bits)


def pps(pid=0, sid=0):
    return nal(8, ue(pid) + ue(sid) + '00' + ue(0))


def picture(pid=0, framebits=4, field=1, bottom=0, separate=False, frameonly=False):
    return nal(1, ue(0) + ue(0) + ue(pid) + ('10' if separate else '') +
               '0' * framebits + ('' if frameonly else str(field) + (str(bottom) if field else '')))


class ScannerTests(unittest.TestCase):
    def test_epb_preserves_literal_03(self):
        self.assertEqual(scan.strip_epb(bytes.fromhex('0000030300')), bytes.fromhex('00000300'))

    def test_epb_zero_runs(self):
        self.assertEqual(scan.strip_epb(bytes.fromhex('00000300000301')), bytes.fromhex('0000000001'))

    def test_epb_literal_and_boundary(self):
        for text in ('03', '000003', '00000304', '010203'):
            with self.subTest(text=text):
                self.assertEqual(scan.strip_epb(bytes.fromhex(text)), bytes.fromhex(text))

    def test_pps_selects_sps(self):
        r = scan.classify_data(sps() + sps(1, 8) + pps(2, 1) + picture(2, 8, bottom=1))
        self.assertTrue(r['complete'])
        self.assertEqual(r['slices']['bottom_field_slices'], 1)

    def test_replaced_sps_takes_effect_in_order(self):
        r = scan.classify_data(sps() + pps() + picture(bottom=1) + sps(framebits=8) + picture(framebits=8, bottom=1))
        self.assertEqual(r['slices']['bottom_field_slices'], 2)
        self.assertTrue(r['complete'])

    def test_replaced_pps_takes_effect_in_order(self):
        r = scan.classify_data(sps() + sps(1, 8) + pps() + picture() + pps(sid=1) + picture(framebits=8))
        self.assertEqual(r['slices']['field_slices'], 2)
        self.assertTrue(r['complete'])

    def test_separate_colour_plane(self):
        r = scan.classify_data(sps(separate=True) + pps() + picture(separate=True, bottom=1))
        self.assertEqual(r['slices']['bottom_field_slices'], 1)
        self.assertTrue(r['complete'])

    def test_progressive_and_mbaff_enabled_frame(self):
        for frameonly, mbaff in ((1, 0), (0, 1)):
            r = scan.classify_data(sps(frameonly=frameonly, mbaff=mbaff) + pps() + picture(field=0, frameonly=frameonly))
            self.assertTrue(r['complete'])
            self.assertEqual(r['slices']['field_slices'], 0)

    def test_unknown_parameter_sets(self):
        for data in (sps() + picture(), sps() + pps(sid=1) + picture()):
            r = scan.classify_data(data)
            self.assertFalse(r['complete'])
            self.assertEqual(r['slices']['parse_errors'], 1)

    def test_truncated_replacements_invalidate_stale_state(self):
        for kind in (7, 8):
            r = scan.classify_data(sps() + pps() + b'\x00\x00\x01' + bytes([kind]) + picture())
            self.assertFalse(r['complete'])
            self.assertEqual(len(r['errors']), 2)

    def test_missing_slice_and_sps(self):
        self.assertFalse(scan.classify_data(b'')['complete'])
        self.assertFalse(scan.classify_data(sps() + pps())['complete'])

    def test_forbidden_bit(self):
        r = scan.classify_data(sps() + pps() + b'\x00\x00\x01\x81\xff')
        self.assertFalse(r['complete'])
        self.assertEqual(r['slices']['parse_errors'], 1)


if __name__ == '__main__':
    unittest.main()
