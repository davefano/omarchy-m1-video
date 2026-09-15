# H.264 and HEVC follow-up — 2026-09-15

Driver candidate: `1.3.r7`. Testing uses a local userspace build on the existing M1 boot,
with `linux-asahi 7.1.13.asahi3-1` and the same 15 kernel patches. No installation, module
reload or reboot is part of this follow-up.

## H.264: verified progress

### High 10: 718 frames now match with an explicit compatibility mode

`FREH10-1` contains 360 frames; `FREH10-2` contains 358. Advertising High 10 alone produced
wrong pictures. FFmpeg 9.0.1 passes its internal quantizer bit-depth bias through VA-API:
the test stream's QP 21 arrives as 33. Removing the 12-step bias made every frame and both
complete reference checksums match:

| Vector | Frames | Reference and corrected hardware MD5 |
|---|---:|---|
| FREH10-1 | 360 | `87071917ba18e58e314e40e76fecafa4` |
| FREH10-2 | 358 | `853ed99f2badd6a8daea0c687e0c9e31` |

A generated 30-frame 640x360 High 10 clip with CAVLC, four slices and B pictures also
matched software through the packaged driver, including its cropped bottom edge.

The fork offers `LIBVA_V4L2_H264_HIGH10=ffmpeg` for affected FFmpeg-based clients and
`native` for clients that already submit the PPS syntax values. It stays disabled by
default. Both modes require a successful 10-bit H.264 SPS probe and usable 10-bit 4:2:0
CAPTURE output; context creation selects a capable decoder. The native mode preserves
the supplied quantizers. The compatibility mode subtracts the bit-depth bias, leaving
8-bit pictures unchanged.

With the new package installed, the tested copying path is:

```sh
LIBVA_V4L2_H264_HIGH10=ffmpeg mpv --gpu-api=opengl --hwdec=vaapi-copy high10.mkv
```

For development, also set `LIBVA_DRIVERS_PATH=/path/to/build/src` and
`LIBVA_DRIVER_NAME=v4l2_request`. This does not install the build. These two streams
establish progressive 10-bit decoding on this M1, not every High 10 coding feature or
other machines. Use the compatibility mode only with affected clients.

Primary-source context: FFmpeg's [PPS parser](https://github.com/FFmpeg/FFmpeg/blob/n8.0/libavcodec/h264_ps.c)
adds the bit-depth offset; its [VA parameter construction](https://github.com/FFmpeg/FFmpeg/blob/n8.0/libavcodec/vaapi_h264.c)
does not remove it. The experiment confirms the effect in the installed FFmpeg 9.0.1.

### Five Baseline/Extended streams already work when FFmpeg permits them

These original bitstreams decoded through VA-API and matched their complete reference
checksums with `-hwaccel_flags allow_profile_mismatch`:

- `BA3_SVA_C`
- `MR2_TANDBERG_E`
- `MR3_TANDBERG_B`
- `MR4_TANDBERG_C`
- `MR5_TANDBERG_C`

This is a per-file workaround for a profile-selection restriction. It does not implement
FMO, data partitions or all Extended-profile features. The default AVC result stays 73/135;
the five override passes are recorded separately.

### What still fails

All 49 failing Main-profile vectors in `JVT-AVC_V1` declare `frame_mbs_only_flag=0`.
The kernel explicitly rejects such SPSs. Even names containing `FRM` are not evidence
of a progressive-only stream. Interlacing needs kernel/firmware work.

The other 13 default AVC failures are seven Baseline and six Extended streams. Five
have the verified override above; the others include FMO, field coding and features
the current FFmpeg/VA path does not implement. H.264 4:2:2 is still unavailable through
the VA fork. Direct GStreamer V4L2 has separate 4:2:2 coverage.

Malformed H.264 headers now fail before submission. Slice-group parameters are rejected
instead of being silently discarded. A failed RenderPicture also prevents EndPicture
from submitting a partially assembled frame. Regression tests cover these cases and
24,000 deterministic parser inputs under ASan/UBSan.

## Test totals must require hardware frames

Fluster's FFmpeg VA-API FRExt run reports 48/69 with High 10 enabled, but 21 of those
are 4:2:2 streams decoded in software. Checking only process success or the absence of
`Failed setup for format` is insufficient.

The new `tests/conformance.py` runner requires every output frame to originate from
VA-API, downloads it, applies the exact conformance crop, and hashes pixels at that
frame's native size. It records per-frame hashes, per-vector logs and fsynced JSON.
The strict FRExt result is **25/69 before, 27/69 with High 10 enabled**.

Its software CI test covers resolution changes, unaligned top/left cropping and truncated
input. The same generated resolution/crop checks also run on hardware. Hardware commands
remain wrapped by the lab's decoder preflight, finite deadline and wedge monitor.

## HEVC: narrowed causes, unresolved decoder failures

### RPS_B / RPS_E: retaining more buffers did not fix corruption

A separate diagnostic userspace build forced private MMAP capture buffers and rotated
them through pools of 19 and 32. Both vectors retained the same whole-output mismatches
as the control run. A requested pool of 64 hit the kernel's 32-buffer allocation limit;
that run is invalid for pixel comparison and is not evidence of a decoder fix.

The rotation experiment is not shipped: display clients require stable exported storage.
It weakens the hypothesis that simply retaining older physical buffers will fix the
problem. Firmware reference metadata, command interpretation and the differing direct
V4L2 paths still need investigation. `RPS_B` passes direct V4L2; `RPS_E` does not.

### VPSSPSPPS_A_MainConcept_1: FFmpeg parser and output handling

Direct GStreamer V4L2 passes the reference checksum. FFmpeg discards parameter sets whose
dependencies have not yet been seen, then loses pictures that refer to them. Its normal
output command also resizes later frames to the first output size. A tolerant FFmpeg
native-size decode retains only two frames (352x288 and 1280x720) and hashes to
`ec9f5857591ac4c215d194deaf52167c`, not the reference `1ddf74263cb4953cfdfcf99c563d88ea`.

Passing the stream through `h265parse config-interval=-1` recovers five frames but still
misses the reference checksum. That experiment does not close the case. A client parser
fix must preserve valid parameter sets until their dependencies are available and emit
every picture; the checksum tool must preserve each picture's dimensions as well.

### Other HEVC limits

`TSUNEQBD_A_MAIN10_Technicolor_2` uses unequal luma/chroma bit depths. The kernel rejects
it deliberately because this format previously reset the firmware. Concurrent HEVC
pixel mismatches remain open; a successful individual run does not prove them resolved.
See [GAP_STATUS.md](GAP_STATUS.md) for boot and display investigations.

## Local evidence

Under the companion `avd-lab/results` directory:

- `codec-triage/h264-headers.json`: SPS classification and profile-override logs.
- `codec-rotation`: buffer-retention experiment, including the invalid 64-buffer run.
- `codec-frames`: full High 10 software/hardware frame hashes from the QP experiment.
- `codec-verified`: strict High 10/FRExt and five profile-override checks.
- `codec-strict/baseline-frext`: exact r6 baseline through the strict runner.
- `codec-final`: final native-size/crop-aware conformance and hardware crop checks.
- `builds/codec-sanitize/meson-logs/testlog.txt`: 22 passing sanitizer tests.

The portable per-vector result summary is [codec-validation-2026-09-15.json](codec-validation-2026-09-15.json).
