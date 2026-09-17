# t6021 hand-loaded patched AVD smoke, 2026-09-17

Bounded campaign 2 for [issue 18](https://github.com/iconidentify/omarchy-m1-video/issues/18).
This is **not** hardware qualification and is **not** a boot-enabled install.

The 15 omarchy-m1-video patches were applied to AsahiLinux/linux tag `asahi-7.1.13-3`
and built against matching `linux-asahi-headers`. The resulting `apple-avd.ko` was
loaded with `insmod` after `v4l2_mem2mem` / `v4l2_h264` / `v4l2_vp9` helpers.
It was **not** installed into `updates/`, no systemd boot service was enabled, and
`install.sh` was not run. After the smokes, the in-tree module was restored with
`rmmod` + `modprobe apple_avd`.

Userspace was the same isolated `27da69dd5fcb438deab970061a2edcc68a9e1d93` library
as campaign 1. Taint while the patched module was loaded: `O`.

| Run | Result |
| --- | --- |
| Guarded idle preflight | pass |
| HEVC `AMP_A_Samsung_7` | `hardware_pass`, 17 frames, 2560x1600, bit-exact |
| AVC `AUD_MW_E` | `hardware_pass`, 100 frames, 176x144, bit-exact |
| VP9 `vp90-2-00-quantizer-00.webm` | `hardware_pass`, 2 frames, 352x288, bit-exact |
| Restored in-tree idle preflight | pass |

The first `insmod` failed with unknown symbols because `modprobe -r apple_avd`
had also removed the helper modules. That is not a firmware fault. The second
`insmod` after `modprobe v4l2_mem2mem v4l2_h264 v4l2_vp9` succeeded and the
firmware logged `booting hw version: 30010`.

Not run: full suites, export, lifecycle, clients, boot-enabled loading.
Known firmware-fault vectors were not decoded.

See [provenance.json](provenance.json).
