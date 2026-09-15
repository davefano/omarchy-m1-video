# H.264 and HEVC follow-up — 2026-09-15

Driver candidate: `1.3.r9`. Testing uses a local userspace build on the existing M1 boot,
with `linux-asahi 7.1.13.asahi3-1` and the same 15 kernel patches. No installation, module
reload or reboot is part of this follow-up.

## H.264: verified progress

### r9: reject incomplete pictures and invalid references before submission

EndPicture previously accepted a picture with additional slice parameters whose data had
never arrived. H.264 also allowed invalid active reference indices through to the kernel;
two unavailable surfaces could match because both resolved to timestamp zero. Version r9
rejects these inputs, checks that the VA slice type agrees with the parsed NAL, and validates
the next slice's references before flushing the preceding slice. Unavailable references
that no active slice list uses remain allowed.

A third fix rejects overflow when accumulating slice-parameter counts. The offline test
injects the counter boundary and reproduces an out-of-bounds write in the old copy operation.
It does not allocate billions of slices or establish a practical malicious-video exploit.

All three new regression cases fail against the preceding implementation and pass after
the fixes. The complete ASan/UBSan suite now contains 25 cases. Full hardware conformance
retains AVC 73/135 and FRExt 27/69 with High 10 enabled, and all five profile-override streams
still pass. All 144 generated High 10 comparisons match, including early export. These
are input-validation fixes; they add no interlacing, FMO or 4:2:2 support.

The pinned, stripped r9 package also passes strict HEVC at 144/147 and all 144 High 10
comparisons. Three consecutive full HEVC suites with four processes each pass 144/147,
with exactly the known serial failures. A half-second monitor observes no unrelated
browser/player decoder clients, and the decoder is idle after each run. No AVD messages
appear in the kernel log (one unrelated firewall message occurs). The historical concurrent
corruption remains open because its cause and triggering schedule are still unknown.

See [the r9 validation record](codec-validation-r9-2026-09-15.json) for commands, checksums,
per-vector results and package identity.

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

A further generated matrix passes 144 frame comparisons: six clips covering CABAC/CAVLC
at QP 1, 21 and 51, four slices, B pictures and 640x360 cropping, each decoded normally
and with export before decoding. Exported dma-buf identity and layout stay stable.
The repeatable check is `tests/h264-high10.sh` in the driver fork.

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
the current FFmpeg/VA path does not implement. A complete header scan confirms
`FM1_FT_E` changes from one slice group to FMO later in the stream; inspecting only its
first packet missed that feature. H.264 4:2:2 is still unavailable through
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

### RPS_B: reference ordering corrects every picture

A controlled userspace experiment changed only DPB ordering and remapped every dependent
slice/RPS index. The original VA order, POC order and CAPTURE-buffer order all failed.
Decode order matched all 300 frames and the complete reference checksum
`6d1ed392b067050ebd3a24a37281da03`. The full serial HEVC suite improves from 143 to **144/147**. A four-process run also
passes 144/147; Chrome held the decoder by completion, so this does not establish an
isolated concurrency result or close the historical intermittent issue.

Version r8 applies this workaround only when the selected V4L2 driver identifies itself as
`avd` and the SPS disallows long-term references. It retains the preceding full DPB plus its current picture, preserving old long-term
references without an expiring history ring. Surface ID and POC both identify a picture.
All VA slice and RPS indices are translated to the reordered DPB; other decoders retain
VA ordering. The underlying firmware ordering sensitivity remains unexplained.

The earlier 19/32-buffer rotation experiments did not correct the pictures. Reference
ordering is a distinct variable: comparisons normalized by POC had hidden it. No buffer
rotation, kernel change or per-stream recognition is shipped.

The unrestricted ordering experiment changed `RPS_E_qualcomm_5` from 26 wrong frames to
30, with checksum `7cf27c519b9740be6867e41bf1ab9ff5`. Therefore r8 leaves VA ordering
unchanged whenever the SPS permits long-term references. `RPS_E` keeps its baseline
26 wrong frames and checksum `b09ac8e0bd31a96d8354505d7c2ebdd5`. It remains a kernel/firmware
investigation alongside the intermittent concurrent failures.

### Reject invalid HEVC references and incomplete pictures

An invalid active reference previously became slot zero. The driver now rejects invalid
indices, missing active reference storage and out-of-range collocated references. Random-access
pictures may carry unavailable references that they never use; those are omitted, preserving
`RAP_A_docomo_6` and `RAP_B_Bossen_2` compatibility.

Malformed NAL headers, oversized/truncated slice data and invalid counts fail before a
preceding full batch is submitted. A failed RenderPicture blocks EndPicture from submitting
an incomplete picture. The sanitizer regressions cover these paths, index remapping, and
long-term references retained across 200 picture updates.

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
- `codec-dpb-valid` and `codec-dpb-full`: controlled ordering experiment.
- `codec-r8-final`: unrestricted ordering and High 10/export checks.
- `codec-r8-scoped`: short-term-only ordering validation before the final history check.
- `codec-r8-package`: final pinned, stripped package: 144/147 HEVC and 144 High 10 comparisons.

The r7 baseline is [codec-validation-2026-09-15.json](codec-validation-2026-09-15.json);
the r8 results are [codec-validation-r8-2026-09-15.json](codec-validation-r8-2026-09-15.json).
