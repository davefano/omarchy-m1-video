# Testing and release checks

## Offline installer checks

```sh
bash -n install.sh uninstall.sh bin/apple-avd-rebuild tests/rebuild.sh tests/installer.sh
bash tests/rebuild.sh
bash tests/installer.sh
```

These need Bash, Git's usual Unix utilities and `patch`; they make no package, module or
system configuration changes. `tests/installer.sh` uses a disposable sysroot and command
shims to run the real installer and uninstaller through consent, first-install, rerun,
header-mismatch, dependency/package/system-file/service/rebuild failures, symlink safety and
repeated uninstall. It also runs the actual rebuild helper through an offline fetch failure.
The shims reject unexpected privileged commands, and the test asserts that existing modules,
stamps, unrelated hooks/files and mpv content survive the applicable failure or removal paths.

`OMARCHY_M1_VIDEO_SYSROOT`, gated by `OMARCHY_M1_VIDEO_TEST_MODE=1`, is an integration-test
seam for system filesystem paths. It must be absolute and is not an installation prefix or a
supported user option. The root must contain `.omarchy-m1-video-test-root`, and `/` is always
rejected. Normal runs leave both variables unset and retain the production paths.
The actual patch-preparation helper runs on synthetic
ordered patches with upstream prefixes 0, 4, 9 and 15, then an incompatible tree. Mock
package/driver data exercises build-marker and ABI failures. The installer is invoked
without the risk flag to verify it exits before installing anything.

The workflow in `.github/workflows/checks.yml` runs these checks on pushes and pull requests.
It does not install or load an out-of-tree module on CI runners.

## Userspace driver

The companion fork contains `tests/README.md`, a 35-case Meson sanitizer suite and hardware
pixel-comparison scripts. Build and test the candidate there before updating
`libva/PKGBUILD`. Use a commit available from the configured Git source and update the
package version and `LIBVA_MARKER` together. A release tag is optional; the source commit
is the reproducibility anchor.

`makepkg` builds the package and runs its `check()` function without installing it.
Inspect its file list and metadata. Installation is a separate operation requiring the
informed consent described in [AGENTS.md](../AGENTS.md).

## Initial hardware validation record (M1, 2026-09-15, driver 1.3.r6)

Kernel package: `linux-asahi 7.1.13.asahi3-1`; installed patch files match 0001–0015 in this
repository. Tests use the candidate userspace library via `LIBVA_DRIVERS_PATH`, on the
existing boot; no kernel patch edits, module reloads, installations or reboots occurred.

Final checks: 20/20 offline sanitizer cases and all 18 hardware pixel comparisons passed
(540 output frames; H.264, HEVC Main/Main10 and VP9 profile 0). The final four-process HEVC run passed
143/147; H.264 passed 73/135. Neither run logged kernel messages. Ubuntu x86_64 sanitizer CI
also passed. The exact nonpassing vectors and profile totals are in [validation-2026-09-15.json](validation-2026-09-15.json).

Track commands, results and limitations in [GAP_STATUS.md](GAP_STATUS.md). Each conformance
run must record vector names as well as its total: software FFmpeg and hardware both
passing 143/147 does not mean they fail the same four vectors. Full-range display tests
must compare rendered frames, not only decoded checksums.

## Health-check semantics

`apple-avd-rebuild --check-libva` and `--status` return nonzero when the expected userspace
driver is missing or replaced, or its libva ABI cannot be established or is too new.
An older driver entry point may load with a newer libva. The exact `1.3.r11` vendor marker
is also visible through `vainfo --display drm`; a generic early-export log string is
insufficient to identify these fixes.

`--status` prints installed kernel build stamps and the module selected on disk for the
next load. It cannot certify which binary was loaded earlier, verify every patch is active,
or prove hardware/boot stability. Use a documented load/boot record for that provenance.

## Codec follow-up (driver 1.3.r7)

The strict native-size checksum runner in the companion fork verifies VA-API frames before
counting hardware passes. Fluster's FFmpeg VA-API FRExt decoder counts 21 software-decoded
4:2:2 streams as successes, so use `tests/conformance.py` for that comparison. It also handles
resolution changes and exact crop windows. See [CODEC_STATUS.md](CODEC_STATUS.md) and
[codec-validation-2026-09-15.json](codec-validation-2026-09-15.json) for the new results.

The 22-case sanitizer suite adds H.264 malformed-input and High 10 capability/quantizer tests.
Software CI validates the checksum helper with generated resolution/crop changes and truncated
input. `LIBVA_V4L2_H264_HIGH10=ffmpeg` is an explicit compatibility mode, not an installer default.

## HEVC reference-order follow-up (driver 1.3.r8)

The strict serial HEVC suite passes 144/147 after the AVD-specific DPB ordering change.
`RPS_B_qualcomm_5` now matches every frame; `RPS_E` remains wrong. The driver adds reference
mapping and failed-picture sanitizer regressions, including unused unavailable references
around random-access points. All 22 Meson cases pass.

Run `sh tests/h264-high10.sh /path/to/build/src` from the driver checkout through the lab
guard. It compares 144 hardware frames with software and checks stable early-export storage
across six High 10 coding/quantizer combinations. See [codec status](CODEC_STATUS.md) and
[the r8 record](codec-validation-r8-2026-09-15.json).

## H.264 submission follow-up (driver 1.3.r9)

Three new Meson cases intercept codec submissions in-process, without opening a device.
They reproduce incomplete-picture acceptance, invalid reference mapping and slice-count
overflow before the fixes, then verify rejection and recovery. All 25 sanitizer cases pass.
The boundary test sets the accumulated count directly; it checks arithmetic without a
multi-terabyte allocation. Full AVC and FRExt results retain 73/135 and 27/69 respectively
(High 10 enabled for FRExt), with all five explicit profile overrides still passing.
See [the r9 record](codec-validation-r9-2026-09-15.json).

## VP9 follow-up (driver 1.3.r10)

Run `sh tests/vp9-matrix.sh /path/to/build/src` from the driver checkout through the lab
guard. It requires 8/10-bit libvpx-vp9 encoding and FFmpeg development libraries. Eight clips,
two export paths and 24 output frames per path produce 384 comparisons. Full-range metadata
and actual 10-bit pixel formats are verified before decoding; software fallback is rejected.

Use `tests/conformance.py` with Fluster's `test_suites/vp9/VP9-TEST-VECTORS.json` for the
305-vector suite. The `VP9-TEST-VECTORS-HIGH.json` result here selects only
`--vectors vp92-2-20-10bit-yuv420.webm`; it does not represent all six high-bit-depth vectors.
Preserve per-vector results and baseline failures, even when rerunning only known passes.

The baseline exposed two firmware timeouts that returned before the outer child deadline.
In addition to `wedge_monitor`, monitor the kernel journal during each run and abort on new
AVD errors/timeouts. Check the final journal window too, since a short-lived child can exit
between monitor polls. The r10 reference fix lets both triggering resize streams reject
without reaching the bad hardware submission. See [codec status](CODEC_STATUS.md) and
[the r10 record](codec-validation-r10-2026-09-15.json).

## Shared picture lifecycle follow-up (driver 1.3.r11)

Six new cases bring the sanitizer suite to 35. `picture.c` calls the real public picture
entrypoints with an intercepted codec; it covers failed/nested BeginPicture, failed
RenderPicture, active-target destruction, reference ownership and invalid context arguments.
The completion regression checks that an earlier slice finishing does not erase the failure
of the picture as a whole, and that a later valid submission can reuse the surface.

The r10 active-target sequence produces an ASan heap-use-after-free. This is a malformed
VA-API sequence in an offline test, not evidence that a crafted media file can trigger it.
No real hardware or kernel module is opened by these tests. Existing codec fixtures now
model both sides of the surface-to-capture-buffer ownership relationship.

The full packaged-driver rerun preserves the exact HEVC/AVC/FRExt/VP9 pass sets, all five
H.264 profile overrides and the official VP9 10-bit 4:2:0 vector. High 10 and VP9 export
matrices match 144 and 384 hardware frames respectively.

Run `sh tests/shared-contexts.sh /path/to/build/src` through the lab guard from the driver
checkout. It interleaves H.264, HEVC and 8/10-bit VP9 using one VA display; the four streams
contain 24, 36, 48 and 60 frames so contexts close at different times. Both normal and
early-export runs match independent software checksums, totaling 336 hardware frames.
Work is interleaved in one thread, so this does not test concurrent API calls. Omitting
the driver-directory argument exercises the helper in software, as CI does.

The final package adds only this test, its documentation and CI to the implementation
package used for the full suites. Both stripped driver binaries compare byte-for-byte
identical; the shared-display hardware test uses the final package. All 35 package checks
pass. Completed hardware runs have no new AVD kernel messages and end with an idle decoder.
The first run, interrupted when mpv acquired the decoder after three HEVC passes, remains
separate from this completed evidence.

See [the r11 validation record](codec-validation-r11-2026-09-15.json) for source/package
identity, commands, per-vector results and offline evidence.
