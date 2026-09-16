#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Offline VP9 sub-64 dimension scanner for omarchy-m1-video#12.

Read-only: extracts the first VP9 frame of each vector from its container
(WebM/Matroska, IVF or a raw frame), parses the uncompressed header (VP9
specification 6.2) and reports the *coded* frame size, the *displayed* render
size, profile, bit depth, chroma subsampling and the derived superblock/tile
geometry.  It classifies each vector against the AVD minimum coded dimension
so the support decision rests on parsed bitstream fields rather than on a
filename or an assumed global hardware limit.

Evidence tool for docs/plans/issue-12-vp9-sub64.md.  It changes nothing, downloads nothing
and never opens a decoder device; vectors must already be present in a local
fluster cache (see the corpus acquisition path in the driver repository's
docs/CORPUS.md).  The official vectors are download-on-demand only and are
never redistributed in this repository.

Usage:
  tests/vp9-sub64-scan.py <fluster-cache>/VP9-TEST-VECTORS > report.json
  tests/vp9-sub64-scan.py --pass-sets r11-pass-sets.json <cache>/VP9-TEST-VECTORS
"""
import argparse, json, sys
from pathlib import Path

# drivers/media/platform/apple/avd/avd-vp9.c:632-634 (kernel tag asahi-7.1.13-3,
# commit 94fb23346d522edf53722357c426a3e58030beea) rejects a decode whose
# bitstream-declared frame size is below this value, before firmware submission.
AVD_MIN_CODED = 64
# avd-v4l2.c:424-432 declares the same minimum, plus the alignment the kernel
# applies to the negotiated decoded format (round_up(w,64) x round_up(h,16)).
AVD_ALIGN_W, AVD_ALIGN_H = 64, 16

CS_RGB = 7
SYNC_CODE = 0x498342


class BitReader:
    """MSB-first reader over the uncompressed header."""

    def __init__(self, data):
        self.data, self.pos = data, 0

    def bits(self, n):
        v = 0
        for _ in range(n):
            if self.pos >= len(self.data) * 8:
                raise ValueError('uncompressed header truncated')
            v = (v << 1) | ((self.data[self.pos >> 3] >> (7 - (self.pos & 7))) & 1)
            self.pos += 1
        return v


def _color_config(b, profile):
    """VP9 6.2.2. Returns (bit_depth, subsampling_x, subsampling_y, color_space)."""
    bit_depth = 8
    if profile >= 2:
        bit_depth = 12 if b.bits(1) else 10
    color_space = b.bits(3)
    if color_space != CS_RGB:
        b.bits(1)  # color_range
        if profile in (1, 3):
            ssx, ssy = b.bits(1), b.bits(1)
            if b.bits(1):
                raise ValueError('reserved_zero set in color_config')
        else:
            ssx = ssy = 1
    else:
        if profile in (1, 3):
            if b.bits(1):
                raise ValueError('reserved_zero set in color_config')
        ssx = ssy = 0
    return bit_depth, ssx, ssy, color_space


def _tile_geometry(frame_width):
    """VP9 6.2.14 / 6.4: superblock columns and the legal tile_cols_log2 range.

    The range is a pure function of Sb64Cols, so a frame narrow enough to fit a
    single 64-pixel superblock column can only ever carry one tile column; no
    encoder choice can widen it.
    """
    mi_cols = (frame_width + 7) >> 3
    sb64_cols = (mi_cols + 7) >> 3
    min_log2 = 0
    while (64 << min_log2) < sb64_cols:
        min_log2 += 1
    max_log2 = 0
    while (sb64_cols >> (max_log2 + 1)) >= 4:
        max_log2 += 1
    return mi_cols, sb64_cols, min_log2, max_log2


def classify_frame(data):
    """Parse one VP9 frame's uncompressed header. Never raises."""
    r = {'parsed': False, 'error': None}
    try:
        b = BitReader(data)
        if b.bits(2) != 2:
            raise ValueError('bad frame_marker')
        low, high = b.bits(1), b.bits(1)
        profile = (high << 1) | low
        if profile == 3 and b.bits(1):
            raise ValueError('reserved_zero set after profile')
        r['profile'] = profile
        if b.bits(1):
            r['error'] = 'show_existing_frame carries no frame size'
            r['show_existing_frame'] = True
            return r
        r['show_existing_frame'] = False
        key_frame = b.bits(1) == 0
        r['frame_type'] = 'key' if key_frame else 'inter'
        r['show_frame'] = bool(b.bits(1))
        b.bits(1)  # error_resilient_mode
        if not key_frame:
            # Only a key frame (or an intra-only frame) carries a sync code and a
            # frame size; an inter frame may inherit its size from a reference.
            r['error'] = 'first frame is not a key frame'
            return r
        if b.bits(24) != SYNC_CODE:
            raise ValueError('bad frame_sync_code')
        bit_depth, ssx, ssy, cs = _color_config(b, profile)
        frame_w = b.bits(16) + 1
        frame_h = b.bits(16) + 1
        if b.bits(1):
            render_w, render_h = b.bits(16) + 1, b.bits(16) + 1
        else:
            render_w, render_h = frame_w, frame_h
        mi_cols, sb64_cols, min_log2, max_log2 = _tile_geometry(frame_w)
        r.update({
            'parsed': True,
            'bit_depth': bit_depth,
            'chroma': {(1, 1): '4:2:0', (1, 0): '4:2:2', (0, 1): '4:4:0',
                       (0, 0): '4:4:4'}[(ssx, ssy)],
            'color_space': cs,
            'coded_width': frame_w, 'coded_height': frame_h,
            'render_width': render_w, 'render_height': render_h,
            'render_differs': (render_w, render_h) != (frame_w, frame_h),
            'mi_cols': mi_cols, 'sb64_cols': sb64_cols,
            'tile_cols_log2_min': min_log2, 'tile_cols_log2_max': max_log2,
            'single_tile_column_forced': max_log2 == 0,
        })
    except (ValueError, KeyError, IndexError) as exc:
        r['error'] = str(exc)
    return r


def verdict(info):
    """Classify a parsed frame against the AVD coded-dimension minimum."""
    if not info.get('parsed'):
        return {'classification': 'unparsed', 'reason': info.get('error')}
    w, h = info['coded_width'], info['coded_height']
    below = [n for n, v in (('width', w), ('height', h)) if v < AVD_MIN_CODED]
    if not below:
        return {'classification': 'within_avd_minimum'}
    return {
        'classification': 'below_avd_minimum',
        'below': below,
        # The negotiated decoded format is already padded past the frame size,
        # so the rejection is about the declared frame size, not the allocation.
        'aligned_decoded_format': [
            -(-w // AVD_ALIGN_W) * AVD_ALIGN_W, -(-h // AVD_ALIGN_H) * AVD_ALIGN_H],
        'enforced_by': 'kernel avd-vp9.c:632-634 validate_dec_params (-EINVAL, '
                       'before firmware submission)',
    }


def _vint(data, pos, keep_marker):
    """EBML variable-size integer."""
    if pos >= len(data):
        raise ValueError('truncated EBML id/size')
    first = data[pos]
    if first == 0:
        raise ValueError('invalid EBML width')
    length = 1
    while not (first & (0x80 >> (length - 1))):
        length += 1
        if length > 8:
            raise ValueError('invalid EBML width')
    if pos + length > len(data):
        raise ValueError('truncated EBML value')
    value = first if keep_marker else first & (0x7F >> (length - 1))
    for i in range(1, length):
        value = (value << 8) | data[pos + i]
    return value, pos + length


MASTER = {0x18538067, 0x1F43B675, 0xA0}  # Segment, Cluster, BlockGroup
BLOCK = {0xA3, 0xA1}                     # SimpleBlock, Block


def _webm_first_frame(data):
    """First (Simple)Block payload; assumes no lacing, which the vectors do not use."""
    stack = [(0, len(data))]
    while stack:
        pos, end = stack.pop(0)
        while pos < end:
            eid, pos = _vint(data, pos, True)
            size, pos = _vint(data, pos, False)
            if size > end - pos:
                raise ValueError('EBML element overruns its parent')
            if eid in BLOCK:
                _, bp = _vint(data, pos, False)   # track number
                bp += 2                            # timecode (int16)
                flags = data[bp]
                bp += 1
                if flags & 0x06:
                    raise ValueError('laced block is not supported')
                return data[bp:pos + size]
            if eid in MASTER:
                stack.insert(0, (pos, pos + size))
                break
            pos += size
    raise ValueError('no block found')


def _ivf_first_frame(data):
    if len(data) < 32:
        raise ValueError('truncated IVF header')
    hdr = int.from_bytes(data[6:8], 'little')
    if len(data) < hdr + 12:
        raise ValueError('truncated IVF frame header')
    size = int.from_bytes(data[hdr:hdr + 4], 'little')
    frame = data[hdr + 12:hdr + 12 + size]
    if len(frame) != size:
        raise ValueError('truncated IVF frame')
    return frame


def first_frame(data):
    if data[:4] == b'\x1a\x45\xdf\xa3':
        return _webm_first_frame(data)
    if data[:4] == b'DKIF':
        return _ivf_first_frame(data)
    return data  # raw frame


def classify_path(path):
    path = Path(path)
    try:
        frame = first_frame(path.read_bytes())
    except (ValueError, OSError) as exc:
        return {'vector': path.name, 'parsed': False, 'error': f'container: {exc}',
                'classification': 'unparsed'}
    info = classify_frame(frame)
    info['vector'] = path.name
    info.update(verdict(info))
    return info


def collect(root):
    """Fluster cache layout <cache>/<vector-name>/<input-file>, or a flat directory."""
    root = Path(root)
    if root.is_file():
        return [root]
    files = [p for p in sorted(root.rglob('*'))
             if p.is_file() and p.suffix.lower() in ('.webm', '.ivf', '.vp9')]
    return files


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('path', help='fluster cache suite directory, or a single vector')
    ap.add_argument('--pass-sets', help='r11 pass-sets JSON to cross-check against')
    ap.add_argument('--suite-key', default='vp9')
    args = ap.parse_args()

    files = collect(args.path)
    if not files:
        print(f'no vectors found under {args.path}', file=sys.stderr)
        return 2
    results = [classify_path(p) for p in files]

    report = {
        'tool': 'tests/vp9-sub64-scan.py',
        'avd_minimum_coded_dimension': AVD_MIN_CODED,
        'kernel_reference': 'avd-vp9.c:632-634 @ asahi-7.1.13-3 '
                            '(94fb23346d522edf53722357c426a3e58030beea)',
        'scanned': len(results),
        'counts': {},
        'vectors': results,
    }
    for r in results:
        k = r['classification']
        report['counts'][k] = report['counts'].get(k, 0) + 1

    if args.pass_sets:
        sets = json.loads(Path(args.pass_sets).read_text())['suites'][args.suite_key]
        failing, passing = set(sets['failing_vectors']), set(sets['passing_vectors'])
        below = {r['vector'] for r in results if r['classification'] == 'below_avd_minimum'}
        within = {r['vector'] for r in results if r['classification'] == 'within_avd_minimum'}
        report['cross_check'] = {
            'below_minimum_and_recorded_failing': sorted(below & failing),
            'below_minimum_but_recorded_passing': sorted(below & passing),
            'within_minimum_but_recorded_failing': sorted(within & failing),
            'consistent': not (below & passing),
        }
        # A vector below the minimum that the baseline records as passing would
        # contradict the kernel check and must be investigated, not smoothed over.
        if below & passing:
            json.dump(report, sys.stdout, indent=2)
            print(file=sys.stdout)
            return 1

    json.dump(report, sys.stdout, indent=2)
    print()
    return 0


if __name__ == '__main__':
    sys.exit(main())
