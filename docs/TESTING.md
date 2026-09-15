# Testing and release checks

## Offline installer checks

```sh
bash -n install.sh uninstall.sh bin/apple-avd-rebuild tests/rebuild.sh
bash tests/rebuild.sh
```

These need Bash, Git's usual Unix utilities and `patch`; they make no package, module or
system configuration changes. The actual patch-preparation helper runs on synthetic
ordered patches with upstream prefixes 0, 4, 9 and 15, then an incompatible tree. Mock
package/driver data exercises build-marker and ABI failures. The installer is invoked
without the risk flag to verify it exits before installing anything.

The workflow in `.github/workflows/checks.yml` runs these checks on pushes and pull requests.
It does not install or load an out-of-tree module on CI runners.

## Userspace driver

The companion fork contains `tests/README.md`, a 22-case Meson sanitizer suite and hardware
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
An older driver entry point may load with a newer libva. The exact `1.3.r8` vendor marker
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
