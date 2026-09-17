# t6021 in-tree AVD userspace smoke, 2026-09-17

Bounded campaign 1 for [issue 18](https://github.com/iconidentify/omarchy-m1-video/issues/18).
This is **not** hardware qualification and does **not** transfer the M1 r11 pass sets
onto `apple,t6021`.

Contributor-reported userspace library: detached `avd-fixes`
`27da69dd5fcb438deab970061a2edcc68a9e1d93`, loaded via `LIBVA_DRIVERS_PATH` from
`build-qualification/src`. The installed package remained `libva-v4l2_request-avd 1.3-1`.
The inventory found an already-loaded `apple_avd` and selected the in-tree file
`/lib/modules/7.1.13-3-1-ARCH/kernel/drivers/media/platform/apple/avd/apple-avd.ko`.
The selected file does not establish the loaded binary's identity. The contributor
reports no `install.sh`, package install, module unload/reload or reboot in this
first campaign; the second campaign reports later package/module operations.

Helper SHA-256 values at that driver commit match
[DEVICE_QUALIFICATION.md](../../../DEVICE_QUALIFICATION.md). Fluster
`f3ad284a9e6cac70dc01b02e0de71c2994181d34`. Smoke corpus `fetch --smoke` /
`verify --require smoke` reportedly passed before decode; the original lock and
verification output were not included.

| Run | Published result |
| --- | --- |
| Guarded `/usr/bin/true` idle preflight | pass, idle, no holders |
| HEVC `AMP_A_Samsung_7` | `hardware_pass`, 17 frames, 2560x1600, bit-exact |
| AVC `AUD_MW_E` | `hardware_pass`, 100 frames, 176x144, bit-exact |
| VP9 `vp90-2-00-quantizer-00.webm` | `hardware_pass`, 2 frames, 352x288, bit-exact |

The contributor reports `tests/hwguard.py --deadline 180` for each decode.
All four published guards report successful, idle final states. Exact guard
arguments and the journal boundary are not retained. Known firmware-fault /
capability-boundary smoke assets were reportedly fetched but **not decoded**:
`RPS_E_qualcomm_5`, `TSUNEQBD_A_MAIN10_Technicolor_2`,
`cabac_mot_fld0_full`, VP9 resize vectors.

Not run: `vainfo` (package absent), full suites, export, lifecycle, clients, boot.
`loaded_binary_sha256` remains unknown.

All 119 published frame hashes match the same vectors in an independent M1 run;
this checks output consistency, not execution on the contributor's host. See the
[maintainer assessment](../t6021-review.md) for the unknowns and acceptance limits.
The original [provenance.json](provenance.json) and adjacent summary/guard files
are preserved unchanged as contributor records.
