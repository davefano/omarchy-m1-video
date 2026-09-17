# t6021 in-tree AVD userspace smoke, 2026-09-17

Bounded campaign 1 for [issue 18](https://github.com/iconidentify/omarchy-m1-video/issues/18).
This is **not** hardware qualification and does **not** transfer the M1 r11 pass sets
onto `apple,t6021`.

Selected userspace library: detached `avd-fixes`
`27da69dd5fcb438deab970061a2edcc68a9e1d93`, loaded via `LIBVA_DRIVERS_PATH` from
`build-qualification/src`. The installed package remained `libva-v4l2_request-avd 1.3-1`.
The kernel module was the already-loaded in-tree
`/lib/modules/7.1.13-3-1-ARCH/kernel/drivers/media/platform/apple/avd/apple-avd.ko`.
No `install.sh`, package install, module unload/reload or reboot.

Helper SHA-256 values at that driver commit match
[DEVICE_QUALIFICATION.md](../../../DEVICE_QUALIFICATION.md). Fluster
`f3ad284a9e6cac70dc01b02e0de71c2994181d34`. Smoke corpus `fetch --smoke` /
`verify --require smoke` passed before any decode.

| Run | Result |
| --- | --- |
| Guarded `/usr/bin/true` idle preflight | pass, idle, no holders |
| HEVC `AMP_A_Samsung_7` | `hardware_pass`, 17 frames, 2560x1600, bit-exact |
| AVC `AUD_MW_E` | `hardware_pass`, 100 frames, 176x144, bit-exact |
| VP9 `vp90-2-00-quantizer-00.webm` | `hardware_pass`, 2 frames, 352x288, bit-exact |

Each decode used `tests/hwguard.py --deadline 180`. Final status was idle after
every run. Known firmware-fault / capability-boundary smoke assets were fetched
but **not decoded**: `RPS_E_qualcomm_5`, `TSUNEQBD_A_MAIN10_Technicolor_2`,
`cabac_mot_fld0_full`, VP9 resize vectors.

Not run: `vainfo` (package absent), full suites, export, lifecycle, clients, boot.
`loaded_binary_sha256` remains unknown.

See [provenance.json](provenance.json) and the adjacent summary/guard files.
