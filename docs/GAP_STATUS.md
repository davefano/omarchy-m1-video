# Gap status — 2026-09-15

Scope: the Omarchy installer and `iconidentify/libva-v4l2_request` fork, their tests/docs,
and investigation of remaining hardware/display failures. The initial fixes were merged
in PR #1 in both repositories. Kernel patches 0001–0015 are unchanged.
This is a development validation record, not a claim that every video or boot is safe.

The codec follow-up adds opt-in High 10 and stronger conformance checks. See
[CODEC_STATUS.md](CODEC_STATUS.md) for the verified gains, workarounds and remaining causes.


Implementation planning, ownership and blockers live in the [roadmap and ticket index](ROADMAP.md).
The evidence and limitations below remain the criteria for support claims; opening or closing a
research ticket does not itself fix a codec or prove boot stability.

## Closed in the userspace driver and installer

| Gap | Change | Verification |
|---|---|---|
| CAPTURE errors reported as success | Preserve `V4L2_BUF_FLAG_ERROR` as a VA decoding error, including sync, export and image reads; successful reuse clears it | Fake-device error/recovery tests |
| Reusing buffers after failed waits | Propagate CAPTURE, reference, converter, request and dma-buf reader wait failures; reject invalid poll events | Timeout tests verify no new queue submission |
| FFmpeg `hwdownload` crash | Serialize surface operations against context destruction; transfer MMAP storage to surviving surfaces; give derived images independent mappings; drain pending frames and retain errors before teardown | Reproduced core, lifetime/error/timeout regressions, hardware pixel comparisons |
| Image and buffer memory safety | Validate image dimensions and plane spans, copy complete odd-width UV pairs, reject truncated derived storage, zero-element resize and bitstream-size overflow | NV12/P010 tests under ASan/UBSan |
| HEVC entry-point handling | Accept exactly full arrays, reject excessive counts/offset lengths, reset between request batches, reject invalid headers | Parser regressions, 24,000 deterministic random inputs, HEVC conformance |
| No durable regression suite | Add Meson tests, hardware scripts and CI to the fork; offline Bash tests and CI to the installer | See [TESTING.md](TESTING.md) |
| Health check silently successful | Nonzero exit on missing/wrong driver or incompatible/unknown libva ABI; identify the expected `1.3.r11` binary by its version marker | Mock driver/package tests |
| Loaded-module provenance overstated | Label `modinfo` as the on-disk module selected for the next load | Read-only inspection: no loaded `srcversion` or build-ID note available on this Mac |
| Unsupported test/documentation claims | Retain tested VP9 coverage; enforce actual Main10 input; stop treating Firefox sandbox changes as a validated setup; distinguish mpv output API from renderer | Script and README review |
| H.264 incomplete-picture submission and invalid reference mapping | Reject EndPicture with unconsumed slice parameters; validate active references and slice type before flushing a pending slice; prevent missing surfaces matching through timestamp zero | Three new fake-submission cases fail before the fix and pass afterward; AVC/FRExt and High 10 hardware checks |
| H.264 slice-count overflow | Reject wrapped counts before allocation or copying | ASan reproduces an out-of-bounds write with the counter boundary injected; fixed case rejects it without submitting hardware work |
| VP9 malformed/incomplete submission | Validate both headers and declared boundaries; reject absent tile data and failed pictures | Malformed-input regression and sanitizer parser coverage |
| VP9 colour range and persistent state | Inherit range on inter frames; commit range/filter/segmentation state only after successful submission | State inheritance and parse/append/submission-failure tests |
| VP9 references from a replaced context reach firmware | Require reference buffers in the current decoder context | Missing/detached/cross-context regressions; both observed resize timeout paths now reject in userspace with a clean kernel-log window |

### r11: shared picture lifetime and references

Version r11 reserves a fresh target at BeginPicture and rejects destruction while an
active picture still holds it. Previously, destroying that target left EndPicture with a
freed pointer; the offline probe reproduces the use-after-free under ASan. Context creation
also stops replacing the owner of surfaces supplied as render-target hints.

The first RenderPicture failure is retained through EndPicture and surface readback; a
later buffer completion cannot turn an incomplete picture into success. Nested begins
cannot replace staged work, and failed begins clear the active picture. Shared reference
lookup rejects foreign, detached, mismatched and known-failed capture buffers, extending
the ownership protection beyond VP9. All 35 sanitizer cases pass. Complete packaged-driver
HEVC/AVC/FRExt/VP9 runs preserve the exact preceding pass sets. High 10 and VP9 export
matrices plus a new mixed-codec shared-display check match all 864 generated hardware
frames against software. The shared-display check interleaves work in one thread and
closes shorter contexts while longer streams continue; threaded API stress remains outside
its scope. No new AVD kernel messages occur, and the decoder is idle after every run.
See [the r11 validation record](codec-validation-r11-2026-09-15.json).

### FFmpeg crash evidence

At 13:30:44 on 2026-09-15, a generated 30-frame H.264 640x360 clip crashed FFmpeg during
hardware download. The core showed its filter thread copying from an unmapped frame in
`vaGetImage`, while the decoder thread was in `capture_buffer_cleanup` → `munmap` during
`vaDestroyContext`. This was a frame-lifetime race, not a failure to allocate memory.
The same workload passes after the fix. No extracted raw core is retained with the project.

The per-display API mutex can serialize separate contexts in the same process. Different
processes remain concurrent. Rockchip conversion/VPP and other decoder hardware were not
validated on the M1.

## Open investigations

### H1 — unexplained resets shortly after boot (high priority)

Tracked work: [Investigate unexplained boot resets with a consented, reproducible test matrix](https://github.com/iconidentify/omarchy-m1-video/issues/13), [Correct the identified reset cause before qualifying boot-enabled installation](https://github.com/iconidentify/omarchy-m1-video/issues/17).

Two boots on 2026-09-14 reset with patches 0001–0005 loaded at boot. Their journals record
module loading but no saved AVD panic/oops before ending. The second boot's PMU report says
one boot error and zero panics. `/sys/fs/pstore` was empty when inspected on 2026-09-15.
One subsequent boot with all 15 patches succeeded. This does not establish the cause or
prove reliable booting; decoding tests do not close this issue.

Next: an explicitly approved cold/warm boot matrix, with timestamps, power state, kernel
and patch identity, previous-boot journal and any persistent crash record. A reproducible
failure needs comparison with the module blacklisted. Save work before every reboot or
module unload. Follow [recovery instructions](../README.md#if-the-mac-freezes-or-resets).
No automatic reboot or module reload is part of this audit.

### H2 — remaining HEVC reference-picture corruption (high priority)

Tracked work: [Isolate the HEVC RPS_E reference corruption with frame and command evidence](https://github.com/iconidentify/libva-v4l2_request/issues/38), [Correct HEVC long-term reference handling for RPS_E without regressions](https://github.com/iconidentify/libva-v4l2_request/issues/42).

**RPS_B is corrected in r8 through VA-API.** Reordering the DPB into decode order, with
all slice/RPS indices remapped, makes all 300 frames match. The complete serial suite rises
to 144/147. This workaround applies only to AVD streams without long-term references.
Earlier POC-normalized comparisons missed this ordering dependence; rotating more physical
buffers did not correct it.

**RPS_E remains open** through both VA-API and direct V4L2. The unrestricted ordering
experiment increased its wrong-frame count, so r8 preserves the original VA order for
streams permitting long-term references. The firmware's reference
metadata and command interpretation need investigation. See [codec evidence](CODEC_STATUS.md).
Any kernel instrumentation belongs in a separate experimental branch, subject to AGENTS.md;
the shipped patches remain unchanged. Close RPS_E only after repeatable reference matches
on both paths and no regressions in the complete suites.

### H3 — intermittent HEVC mismatches with concurrent streams

Tracked work: [Make intermittent multi-process HEVC corruption reproducible](https://github.com/iconidentify/libva-v4l2_request/issues/39), [Fix the isolated HEVC concurrency defect and lock in its regression](https://github.com/iconidentify/libva-v4l2_request/issues/43).

Historical four-process runs sometimes fail `SLIST_B_Sony_9`, `SLIST_D_Sony_9` or
`RAP_B_Bossen_2` without a firmware error; full-suite results vary between 141 and 143/147.
The r8 four-process run passes 144/147, but Chrome holds the decoder at completion.
A passing four-process run is insufficient to close this. The known next-request control
race is already fixed by kernel patch 0006; remaining pixel mismatches need separate proof.

The r9 package passes three consecutive complete four-process suites at 144/147, with
no unrelated browser/player decoder clients observed by the half-second monitor and an
idle decoder after every run. All three retain exactly the known serial failures. No AVD
kernel messages occur. This improves the isolated evidence but does not establish the cause
of the earlier intermittent failures or close the investigation.

Next: repeat fixed vector pairs and full suites with no unrelated decoder clients; record
first differing pictures and correlate command/reference metadata as in H2. Acceptance:
repeatable bit-exact results under the same parallel schedule, with no new kernel errors.

### D1 — Vulkan imports the wrong chroma offset

Tracked work: [Validate and package a scoped Mesa Vulkan dma-buf plane-offset correction](https://github.com/iconidentify/omarchy-m1-video/issues/24).

Local Mesa 26.1.8 Honeykrisp source and existing frame comparisons identify ignored
`VkImageDrmFormatModifierExplicitCreateInfoEXT.pPlaneLayouts[].offset` during dma-buf import.
A local experimental Mesa fix improved the recorded Vulkan comparison from 13.4 to 58.1 dB
PSNR against software; OpenGL matched. This fix is not packaged by either repository.

Keep `vo=gpu-next`, `gpu-api=opengl`. `vo=gpu` is a renderer choice, not synonymous with
Vulkan. Next: validate the Mesa fix across NV12/P010, padded resolutions and import layouts
before considering a separately reviewed Mesa package. Do not change the shipped mpv
output setting based on a single successful sample.

### D2 — Chrome full-range H.264 without colour description

Tracked work: [Fix Chrome full-range H.264 colour handling when the colour description is absent](https://github.com/iconidentify/omarchy-m1-video/issues/26).

The local Chromium parser investigation found `H264SPS::GetColorSpace()` dropping the
full-range flag when `colour_description_present_flag` is absent. Prior Chrome 152 frame
comparisons improved from 29.7 to 67.3 dB after remuxing the test recording with a colour
description; decoded pixels were unchanged. This is outside the VA-API driver.

The README's remux example uses BT.601 metadata (code 6) for the diagnosed recording;
it is not a universal colour-space correction. Preserve the actual primaries, transfer
and matrix of other files. Next: validate a Chromium parser fix with and without colour
description, checking hardware and software output. Do not disable the GPU sandbox as a
workaround; the recorded test worsened the output.

### C1 — unsupported H.264 formats

Tracked work: [Expand and qualify H.264 profiles and coding features](https://github.com/iconidentify/libva-v4l2_request/issues/11), [Design and establish feasibility of H.264 field and MBAFF decoding on AVD](https://github.com/iconidentify/omarchy-m1-video/issues/10), [Implement and qualify AVD interlaced H.264 from the approved field-decoding design](https://github.com/iconidentify/omarchy-m1-video/issues/14).

Interlaced H.264 requires further AVD firmware/driver work: all 49 failing Main vectors
declare non-frame-only SPSs. The VA-API fork exposes Constrained Baseline, Main and High
by default. Version r7 adds opt-in High 10 with a separate FFmpeg quantizer compatibility
mode; both High 10 conformance streams (718 frames) match the reference. H.264 4:2:2 still
uses software through VA-API. Five progressive Baseline/Extended streams also pass with an
explicit FFmpeg profile override. See [codec details](CODEC_STATUS.md).

FMO/ASO and Extended features remain incomplete. Use software for affected files. Expanding
profiles requires verified kernel formats, capability negotiation and bit-exact format-specific
suites. The new checksum runner rejects software fallback, which inflated Fluster's FRExt total.

### C2 — VP9 resize and format gaps

Tracked work: [Complete VP9 state, resizing and format coverage](https://github.com/iconidentify/libva-v4l2_request/issues/13), [Design preservation of AVD VP9 reference metadata across size changes](https://github.com/iconidentify/omarchy-m1-video/issues/11), [Implement the approved AVD VP9 state-preserving resize contract](https://github.com/iconidentify/omarchy-m1-video/issues/16), [Decode VP9 inter-frame resize streams correctly through VA-API](https://github.com/iconidentify/libva-v4l2_request/issues/44).

r10 adds strict header/submission/reference validation and persistent-state fixes, with four
new Meson cases. The 216 baseline passing official vectors still pass, as does the official
10-bit 4:2:0 vector. Eight generated clips pass all 384 ordinary/early-export comparisons,
covering 8/10-bit and full/limited range. These results replace the earlier profile-0 smoke
coverage claim; they do not establish full VP9 support.

The baseline's two context-changing resize streams caused firmware H3/timeouts. r10 rejects
their cross-context references before hardware submission, with no new kernel messages in
the guarded rerun. The final package also rejects the
24 previously wrong-output inter-frame-resize streams and one scalable-video stream for
unavailable references. Correct decoding remains open for all 27 streams. Sixty sub-64-dimension streams hit the
kernel's minimum; two profile-1 streams are outside advertised formats. Software passes
88 of the 89 baseline failures; the scalable stream also misses its software checksum.

Next: preserve/reconstruct the reference pictures needed across size changes, investigate
reference scaling against software, then repeat the exact failing vectors and complete
suite. Keep firmware-error monitoring enabled and stop on the first new fault. See
[codec details](CODEC_STATUS.md#vp9-validation-and-remaining-gaps).

The preservation design now exists and is awaiting review:
[VP9 resize state-preservation design (V1)](plans/issue-11-vp9-resize-state.md)
([omarchy-m1-video#11](https://github.com/iconidentify/omarchy-m1-video/issues/11)).
It specifies the kernel reconfiguration contract (V2,
[omarchy-m1-video#16](https://github.com/iconify/omarchy-m1-video/issues/16), needs
kernel approval) and the VA-driver decoder-session change (V3,
[libva-v4l2_request#44](https://github.com/iconidentify/libva-v4l2_request/issues/44)),
with the guarded hardware experiments that gate them. Until those land, the current
userspace rejection stays in place unchanged.

#### Why simply re-importing VP9 reference pixels is insufficient

The kernel's [capture-format setter](https://github.com/AsahiLinux/linux/blob/asahi-7.1.13-3/drivers/media/platform/apple/avd/avd-v4l2.c)
rejects format changes while capture buffers remain allocated. Freeing that queue loses
the per-buffer reference metadata: dimensions, bit depth and compressed-reference offsets.
The [VP9 backend](https://github.com/AsahiLinux/linux/blob/asahi-7.1.13-3/drivers/media/platform/apple/avd/avd-vp9.c)
also holds probability contexts and previous-frame state. Re-importing the surviving dma-buf
into a new context only restores memory; it does not reconstruct these kernel data structures.

A complete fix needs a verified way to retain or restore this state across size changes,
including scratch-buffer resizing and reference scaling. The current userspace guard stays
in place. These observations come from the matching kernel-tag source and local code, not
from proof of the exact module binary currently loaded. No kernel patches were edited.

### C3 — Firefox and other machines remain unvalidated

Tracked work: [Validate Firefox hardware decoding inside its normal sandbox](https://github.com/iconidentify/omarchy-m1-video/issues/23), [Establish repeatable qualification for additional Apple Silicon machines](https://github.com/iconidentify/omarchy-m1-video/issues/18), [Qualify a non-AVD V4L2 backend and isolate Apple-specific behavior](https://github.com/iconidentify/libva-v4l2_request/issues/46).

No Firefox hardware/rendering run was performed. The old package message stated that
disabling the RDD sandbox was required; this is now described as unvalidated rather than
an installation step. Next: test the normal sandbox first, capture decoder selection and
rendered output, and investigate device-access mediation if blocked. Other Apple Silicon
models and non-AVD users of the generic fork need their own hardware validation.

## Reproduction records

Local evidence is in the companion `avd-lab/results` tree (ignored by Git):

- `gaps-hwdownload/backtrace.txt`: the confirmed teardown/read race.
- `gaps-final`: normal and forced-GetImage frame comparisons.
- `gaps-vp9-export`: ordinary and export-before-decode comparisons, including VP9.
- `builds/gaps-sanitize/meson-logs/testlog.txt`: offline sanitizer results.
- Dated `conformance-*` directories: per-vector JSON, complete logs and kernel-log windows.
- The lab's `FINDINGS.md`: earlier HEVC control/reference comparisons and display experiments.

The data supports the stated fixes and open questions; local result directories are not
required to build or run the published tests. Report setup problems in this repository,
not to Asahi Linux or other upstream projects.
