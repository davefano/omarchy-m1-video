#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Offline H.264 interlace-feature scanner for omarchy-m1-video#10.

Read-only: parses Annex-B elementary streams (SPS/PPS prefixes; slice headers up to
field_pic_flag/bottom_field_flag) and reports per-vector interlaced-coding
features. Evidence tool for docs/plans/issue-10-h264-field-mbaff.md; it
changes nothing and performs no network access.

Usage: tests/h264-interlace-scan.py <fluster-cache>/JVT-AVC_V1 > report.json
"""
import argparse, json
from pathlib import Path

class BitReader:
    def __init__(self, data):
        self.data, self.pos = data, 0
    def bit(self):
        b = (self.data[self.pos >> 3] >> (7 - (self.pos & 7))) & 1
        self.pos += 1
        return b
    def bits(self, n):
        v = 0
        for _ in range(n):
            v = (v << 1) | self.bit()
        return v
    def ue(self):
        z = 0
        while self.bit() == 0:
            z += 1
            if z > 32:
                raise ValueError('bad ue')
        return (1 << z) - 1 + (self.bits(z) if z else 0)
    def se(self):
        k = self.ue()
        return (k + 1) // 2 if k & 1 else -(k // 2)

def strip_epb(p):
    out = bytearray()
    for i in range(len(p)):
        if (i >= 2 and p[i - 1] == 0 and p[i - 2] == 0 and p[i] == 3
                and i + 1 < len(p) and p[i + 1] <= 3):
            continue  # emulation prevention byte
        out.append(p[i])
    return bytes(out)

def nals(data):
    starts = []
    i, n = 0, len(data)
    while i + 3 <= n:
        if data[i] == 0 and data[i + 1] == 0 and data[i + 2] == 1:
            starts.append((i, 3)); i += 3
        elif i + 4 <= n and data[i] == 0 and data[i + 1] == 0 and data[i + 2] == 0 and data[i + 3] == 1:
            starts.append((i, 4)); i += 4
        else:
            i += 1
    for idx, (off, sclen) in enumerate(starts):
        end = starts[idx + 1][0] if idx + 1 < len(starts) else n
        payload = data[off + sclen:end]
        if not payload:
            continue
        yield payload[0] & 0x1f, payload[0], strip_epb(payload)

def skip_scaling_list(b, size):
    last, nxt = 8, 8
    for _ in range(size):
        if nxt != 0:
            delta = b.se()
            nxt = (last + delta + 256) % 256
        if nxt != 0:
            last = nxt

HIGH_PROFILES = {100, 110, 122, 244, 44, 83, 86, 118, 128, 138, 139, 134, 135}

def parse_sps(rbsp):
    b = BitReader(rbsp[1:])
    d = {'profile_idc': b.bits(8), 'constraint_flags': b.bits(8),
         'level_idc': b.bits(8), 'sps_id': b.ue()}
    p = d['profile_idc']
    if p in HIGH_PROFILES:
        d['chroma_format_idc'] = b.ue()
        if d['chroma_format_idc'] == 3:
            d['separate_colour_plane_flag'] = b.bit()
        d['bit_depth_luma_minus8'] = b.ue()
        d['bit_depth_chroma_minus8'] = b.ue()
        b.bit()
        if b.bit():
            cnt = 8 if d['chroma_format_idc'] != 3 else 12
            for i in range(cnt):
                if b.bit():
                    skip_scaling_list(b, 16 if i < 6 else 64)
    else:
        d['chroma_format_idc'] = 1
        d['bit_depth_luma_minus8'] = 0
        d['bit_depth_chroma_minus8'] = 0
    d['log2_max_frame_num_minus4'] = b.ue()
    d['poc_type'] = b.ue()
    if d['poc_type'] == 0:
        d['log2_max_poc_lsb_minus4'] = b.ue()
    elif d['poc_type'] == 1:
        d['delta_poc_always_zero'] = b.bit()
        b.se(); b.se()
        for _ in range(b.ue()):
            b.se()
    d['max_num_ref_frames'] = b.ue()
    d['gaps_in_frame_num_allowed'] = b.bit()
    d['pic_width_in_mbs'] = b.ue() + 1
    d['pic_height_in_map_units'] = b.ue() + 1
    d['frame_mbs_only'] = b.bit()
    d['mb_adaptive_frame_field'] = 0 if d['frame_mbs_only'] else b.bit()
    d['direct_8x8_inference'] = b.bit()
    return d

PROFILES = {66: 'Baseline', 77: 'Main', 88: 'Extended'}

def parse_pps(rbsp):
    """Parse PPS far enough to record slice-group (FMO) configuration."""
    b = BitReader(rbsp[1:])
    pps_id = b.ue()
    sps_id = b.ue()
    entropy_coding = b.bit()
    b.bit()  # bottom_field_pic_order_in_frame_present
    num_slice_groups_minus1 = b.ue()
    return {'pps_id': pps_id, 'sps_id': sps_id,
            'entropy_coding_mode': entropy_coding,
            'num_slice_groups_minus1': num_slice_groups_minus1}

def classify_data(data):
    # Resolve parameter sets in stream order, including replacement of an ID.
    sps_list, pps_list = [], []
    sps_by_id, pps_by_id = {}, {}
    errors = []
    st = {'slice_nals': 0, 'idr_slices': 0, 'parsed': 0,
          'field_slices': 0, 'bottom_field_slices': 0, 'parse_errors': 0}
    for nt, hdr, rbsp in nals(data):
        try:
            if hdr & 0x80:
                raise ValueError('forbidden_zero_bit is set')
            if nt == 7:
                s = parse_sps(rbsp)
                sps_by_id[s['sps_id']] = s
                sps_list.append(s)
            elif nt == 8:
                p = parse_pps(rbsp)
                pps_by_id[p['pps_id']] = p
                pps_list.append(p)
            elif nt in (1, 5):
                st['slice_nals'] += 1
                st['idr_slices'] += nt == 5
                b = BitReader(rbsp[1:])
                b.ue()  # first_mb_in_slice
                b.ue()  # slice_type
                pps_id = b.ue()
                sps = sps_by_id[pps_by_id[pps_id]['sps_id']]
                if sps.get('separate_colour_plane_flag'):
                    b.bits(2)
                b.bits(sps['log2_max_frame_num_minus4'] + 4)
                field = 0 if sps['frame_mbs_only'] else b.bit()
                bottom = b.bit() if field else 0
                st['field_slices'] += field
                st['bottom_field_slices'] += bottom
                st['parsed'] += 1
        except (IndexError, KeyError, ValueError) as e:
            errors.append({'nal_type': nt, 'error': str(e) or type(e).__name__})
            if nt in (1, 5):
                st['parse_errors'] += 1
            # A malformed replacement must not leave stale state usable.
            elif nt == 7:
                sps_by_id.clear()
            elif nt == 8:
                pps_by_id.clear()
    if not sps_list:
        return {'error': 'no parsable SPS', 'complete': False, 'errors': errors}
    sps = sps_list[0]
    return {'sps': sps, 'sps_count': len(sps_list), 'sps_all_agree':
            all(s['frame_mbs_only'] == sps['frame_mbs_only'] and
                s.get('mb_adaptive_frame_field', 0) == sps.get('mb_adaptive_frame_field', 0)
                for s in sps_list),
            'parameter_sets': {'sps': sps_list, 'pps': pps_list},
            'complete': not errors and st['parsed'] > 0, 'errors': errors,
            'pps_count': len(pps_list),
            'max_slice_groups_minus1': max((p['num_slice_groups_minus1']
                                            for p in pps_list), default=0),
            'entropy_coding': max((p['entropy_coding_mode'] for p in pps_list),
                                  default=0), 'slices': st}

STREAM_SUFFIXES = ('.264', '.h264', '.jsv', '.jvt', '.26l', '.avc')

def classify(path):
    return classify_data(Path(path).read_bytes())

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    root = parser.parse_args().root
    out = {}
    for vecdir in sorted(p for p in root.iterdir() if p.is_dir()):
        cands = sorted(f for f in vecdir.iterdir()
                       if f.is_file() and f.suffix in STREAM_SUFFIXES)
        if not cands:
            # Some vectors nest the elementary stream one level down
            # (e.g. sp2_bt_b/H26L/BitstreamExchange/sp2_bt_b.h264).
            cands = sorted(f for f in vecdir.rglob('*')
                           if f.is_file() and f.suffix in STREAM_SUFFIXES)
        if len(cands) != 1:
            out[vecdir.name] = {'error': 'expected exactly one elementary-stream input',
                                'files': [f.name for f in vecdir.iterdir()]}
            continue
        r = classify(cands[0])
        out[vecdir.name] = r if r else {'error': 'no parsable SPS'}
    print(json.dumps(out, indent=1))
    return 0 if out and all(r.get('complete') for r in out.values()) else 1

if __name__ == '__main__':
    raise SystemExit(main())
