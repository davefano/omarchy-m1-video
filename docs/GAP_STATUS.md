# Gap status — 2026-09-15

Scope: the Omarchy installer and `iconidentify/libva-v4l2_request` fork, their tests/docs,
and investigation of remaining hardware/display failures. The fixes below are on
`fix/playback-gaps` in both repositories. Kernel patches 0001–0015 are unchanged.
This is a development validation record, not a claim that every video or boot is safe.

## Closed in the userspace driver and installer

| Gap | Change | Verification |
|---|---|---|
| CAPTURE errors reported as success | Preserve `V4L2_BUF_FLAG_ERROR` as a VA decoding error, including sync, export and image reads; successful reuse clears it | Fake-device error/recovery tests |
| Reusing buffers after failed waits | Propagate CAPTURE, reference, converter, request and dma-buf reader wait failures; reject invalid poll events | Timeout tests verify no new queue submission |
| FFmpeg `hwdownload` crash | Serialize surface operations against context destruction; transfer MMAP storage to surviving surfaces; give derived images independent mappings; drain pending frames and retain errors before teardown | Reproduced core, lifetime/error/timeout regressions, hardware pixel comparisons |
| Image and buffer memory safety | Validate image dimensions and plane spans, copy complete odd-width UV pairs, reject truncated derived storage, zero-element resize and bitstream-size overflow | NV12/P010 tests under ASan/UBSan |
| HEVC entry-point handling | Accept exactly full arrays, reject excessive counts/offset lengths, reset between request batches, reject invalid headers | Parser regressions, 24,000 deterministic random inputs, HEVC conformance |
| No durable regression suite | Add Meson tests, hardware scripts and CI to the fork; offline Bash tests and CI to the installer | See [TESTING.md](TESTING.md) |
| Health check silently successful | Nonzero exit on missing/wrong driver or incompatible/unknown libva ABI; identify the expected `1.3.r6` binary by its version marker | Mock driver/package tests |
| Loaded-module provenance overstated | Label `modinfo` as the on-disk module selected for the next load | Read-only inspection: no loaded `srcversion` or build-ID note available on this Mac |
| Unsupported test/documentation claims | Retain tested VP9 coverage; enforce actual Main10 input; stop treating Firefox sandbox changes as a validated setup; distinguish mpv output API from renderer | Script and README review |

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

### H2 — wrong HEVC reference pictures (high priority)

`RPS_B_qualcomm_5` fails through VA-API; `RPS_E_qualcomm_5` fails through VA-API and direct
V4L2. Prior traces matched the controls, bitstream bytes and reference pictures by POC
between stacks. `RPS_B` produced 10 wrong pictures out of 300, all B pictures using temporal
motion-vector prediction. Several command streams matched apart from addresses and job
IDs. Stale visible reference pixels, early export and DPB slot order did not explain it.
The unresolved area includes firmware reference metadata and buffer lifetime/reuse.
That is a hypothesis, not an established cause.

Next: trace the first differing picture with compressed-reference and motion-vector tail
contents as well as visible pixels, and compare buffer-allocation/reuse schedules. Any
kernel instrumentation belongs in a separate experimental branch, with the module-loading
consent required by AGENTS.md. Close only after both vectors match the reference decoder
repeatedly on both paths and the complete suites retain their existing passes.

### H3 — intermittent HEVC mismatches with concurrent streams

Historical four-process runs sometimes fail `SLIST_B_Sony_9`, `SLIST_D_Sony_9` or
`RAP_B_Bossen_2` without a firmware error; full-suite results vary between 141 and 143/147.
A passing four-process run is insufficient to close this. The known next-request control
race is already fixed by kernel patch 0006; remaining pixel mismatches need separate proof.

Next: repeat fixed vector pairs and full suites with no unrelated decoder clients; record
first differing pictures and correlate command/reference metadata as in H2. Acceptance:
repeatable bit-exact results under the same parallel schedule, with no new kernel errors.

### D1 — Vulkan imports the wrong chroma offset

Local Mesa 26.1.8 Honeykrisp source and existing frame comparisons identify ignored
`VkImageDrmFormatModifierExplicitCreateInfoEXT.pPlaneLayouts[].offset` during dma-buf import.
A local experimental Mesa fix improved the recorded Vulkan comparison from 13.4 to 58.1 dB
PSNR against software; OpenGL matched. This fix is not packaged by either repository.

Keep `vo=gpu-next`, `gpu-api=opengl`. `vo=gpu` is a renderer choice, not synonymous with
Vulkan. Next: validate the Mesa fix across NV12/P010, padded resolutions and import layouts
before considering a separately reviewed Mesa package. Do not change the shipped mpv
output setting based on a single successful sample.

### D2 — Chrome full-range H.264 without colour description

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

Interlaced H.264 requires further AVD firmware/driver work. The VA-API fork exposes only
Constrained Baseline, Main and High; H.264 10-bit/4:2:2 therefore uses software. Baseline
FMO/ASO and Extended features are not fully covered by FFmpeg's VA-API path. This explains
much of the 73/135 suite result; it is not an all-profile success claim.

Use software decoding for affected files. Expanding advertised profiles requires verified
kernel formats, capability negotiation and bit-exact format-specific suites. Do not merely
add profile names or send unsupported streams to firmware.

### C2 — VP9 coverage is limited

The packaged-driver probe lists VP9 profiles 0 and 2 on the M1. Both ordinary and early-export
readbacks of a generated 30-frame VP9 profile-0 clip match software byte for byte. Full VP9
conformance and profile-2 (10-bit) output have not been validated in this audit. Those require
separate bit-exact suites before extending the advertised test claims beyond this smoke test.

### C3 — Firefox and other machines remain unvalidated

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
