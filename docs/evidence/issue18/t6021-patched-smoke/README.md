# t6021 hand-loaded patched AVD smoke, 2026-09-17

Bounded campaign 2 for [issue 18](https://github.com/iconidentify/omarchy-m1-video/issues/18).
This is **not** hardware qualification and is **not** a boot-enabled install.

The contributor reports that 15 omarchy-m1-video patches were applied to
AsahiLinux/linux tag `asahi-7.1.13-3`
and built against matching `linux-asahi-headers`. The resulting `apple-avd.ko` was
loaded with `insmod` after `v4l2_mem2mem` / `v4l2_h264` / `v4l2_vp9` helpers.
It was **not** installed into `updates/`, no systemd boot service was enabled, and
`install.sh` was not run. After the smokes, the in-tree module was restored with
`rmmod` + `modprobe apple_avd`, according to that report. These claims describe
this historical smoke campaign only, not the later boot-qualification work.

The same session also reports installing `linux-asahi-headers 7.1.13.asahi3-1`,
`libva-utils 2.24.0-1` and `pahole 1:1.32-1`. The earlier read-only inventory's
missing-package status must not be presented as the later host state.

The resolved kernel commit, patchset revision/hash list, build command/compiler,
original load/restore logs and saved-work/operation authorization record are
absent from this contribution. A reported local `.ko` hash alone does not prove
which binary or patches executed. Exact module/patch attribution remains
**unverified**; see the [maintainer assessment](../t6021-review.md).

Reported userspace was the same isolated `27da69dd5fcb438deab970061a2edcc68a9e1d93` library
as campaign 1. Taint while the patched module was loaded: `O`.

| Run | Published result |
| --- | --- |
| Guarded idle preflight | pass |
| HEVC `AMP_A_Samsung_7` | `hardware_pass`, 17 frames, 2560x1600, bit-exact |
| AVC `AUD_MW_E` | `hardware_pass`, 100 frames, 176x144, bit-exact |
| VP9 `vp90-2-00-quantizer-00.webm` | `hardware_pass`, 2 frames, 352x288, bit-exact |
| Restored in-tree idle preflight | pass |

The contributor reports that the first `insmod` failed with unknown symbols
because `modprobe -r apple_avd`
had also removed the helper modules. They attribute this to missing helpers
rather than a firmware fault. The second
`insmod` after `modprobe v4l2_mem2mem v4l2_h264 v4l2_vp9` succeeded and the
firmware logged `booting hw version: 30010`, according to the same account.
The original failed/successful load logs are not available to verify that diagnosis.

Not run: full suites, export, lifecycle, clients, boot-enabled loading.
Known firmware-fault vectors were not decoded.

All five published guards report successful, idle final states. All 119 published
frame hashes match the same vectors in an independent M1 run. Neither comparison
establishes the loaded kernel stack or demonstrates a benefit from the patches.
The original [provenance.json](provenance.json), summaries and guards are preserved
unchanged as contributor records; the assessment records the narrower acceptance.
