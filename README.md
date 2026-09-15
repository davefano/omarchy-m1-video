# omarchy-m1-video

Hardware video decoding (H.264 and HEVC) for [Omarchy](https://omarchy.org) on Apple Silicon
Macs running the Asahi Linux kernel. mpv, Chrome and Chromium decode video on the Mac's built-in
video decoder (AVD) instead of the CPU.

> [!IMPORTANT]
> **Unofficial.** Not affiliated with or endorsed by Asahi Linux, Omarchy, or the authors of
> the code it patches. Please don't report problems with this setup to Asahi Linux or other
> upstream projects: open an issue here instead.

## What it fixes

With the stock `linux-asahi` 7.1.13 AVD driver and `libva-v4l2_request-avd` 1.3:

| Problem | Fixed by |
|---|---|
| H.264 streams are rejected after 4096 slices, so longer videos stop decoding | kernel patch 0004 |
| A 16 MiB contiguous allocation per frame that fails once memory is fragmented | kernel patch 0003 |
| A job-completion race that can oops the kernel and lock `/dev/video0` until reboot | kernel patch 0005 |
| HEVC wavefront streams fail with firmware "H0 error", much more often with several HEVC videos at once | kernel patch 0006 |
| Monochrome (4:0:0) H.264 video shows green | kernel patches 0008, 0014 |
| An HEVC stream with different luma and chroma bit depths crashes the decoder firmware and resets it, disturbing other videos | kernel patches 0009, 0015 |
| 8-bit 4:2:2 H.264 with P or B frames decodes wrongly (affects apps that use V4L2 directly, such as GStreamer) | kernel patch 0007 |
| Memory-safety and robustness bugs in the driver: a use-after-free window, out-of-bounds writes and reads, a leaked 8 MiB job table, requests that never complete after an error | kernel patches 0010-0013 |
| Chrome shows solid green video | VA-API driver |
| H.264 videos with several CAVLC slices per picture hang | VA-API driver |
| HEVC streams with tiles or wavefront parallel processing hang | VA-API driver |
| 10-bit HEVC decodes to blank (all-zero) frames | VA-API driver |
| A crafted HEVC video can crash the process decoding it (stack overflow in the slice header parser) | VA-API driver |

Conformance on an M1 (bit-exact against the reference decoders):

| Suite | Through VA-API (FFmpeg) | Through V4L2 (GStreamer) |
|---|---|---|
| HEVC `JCT-VC-HEVC_V1` (147 streams) | 143 one at a time, 141-143 with four at once | 143 |
| H.264 `JVT-AVC_V1` (135 streams) | 73 | 77 |
| H.264 FRExt `JVT-FR-EXT` (69 streams) | not run | 35 |

Software FFmpeg also passes 143 of the HEVC streams, a different set. The H.264 streams that fail
through VA-API are interlaced (not supported by the kernel driver) or Baseline/Extended profile
features FFmpeg does not hand to VA-API. The first 1200 frames of four real H.264 recordings, up to
2560x1600, decoded bit-exact.

## Tested on

- MacBook Pro 13" M1 (T8103), Omarchy (omarchy-mac), `linux-asahi` 7.1.13.asahi3-1
  (AsahiLinux/linux tag `asahi-7.1.13-3`)
- mpv with `vo=gpu-next`, `gpu-api=opengl`; Google Chrome 152

Other Apple Silicon Macs use the same driver and may work, but have not been tested. Reports
(working or not) are welcome as issues.

## Before you install

This installs an **out-of-tree kernel module** that loads **at every boot** and taints the
kernel. It is not reviewed or supported by Asahi Linux.

On the test Mac, the machine **hard-reset twice within about a minute of boot** while kernel
patches 0001-0005 (unchanged since) were the module loaded at boot. The cause was not found and
may not be the module. Since then the patches passed parallel decode stress tests, 30-minute idle
soaks and device probe soaks with the module loaded by hand. With all 15 patches, loading at boot
has been retested **once** so far: the test Mac booted normally, decoded bit-exact and ran without
kernel or decoder errors for the following 10 minutes. That is one boot, not proof. Read
[If the Mac freezes or resets](#if-the-mac-freezes-or-resets) before installing, and test with
`modprobe` before you reboot (below).

## Install

Save your work first.

```sh
git clone https://github.com/iconidentify/omarchy-m1-video
cd omarchy-m1-video
./install.sh --i-accept-boot-risk
```

`install.sh` refuses to run without `--i-accept-boot-risk`. It:
1. checks for an Apple Silicon Mac with the `linux-asahi` kernel, and that `linux-asahi-headers`
   matches the installed kernel (if not, update the whole system with `omarchy update`, reboot, and
   run it again);
2. installs build dependencies (`base-devel git meson libdrm libva libva-utils patch` and the
   headers);
3. builds and installs `libva-v4l2_request-avd` from
   [iconidentify/libva-v4l2_request](https://github.com/iconidentify/libva-v4l2_request)
   (`libva/PKGBUILD`, pinned to a commit);
4. copies the kernel patches to `/usr/local/share/apple-avd-patched/patches`, the rebuild script
   to `/usr/local/sbin/apple-avd-rebuild`, two pacman hooks to `/etc/pacman.d/hooks` and a boot
   service to `/etc/systemd/system/apple-avd-rebuild.service` (enabled);
5. builds the patched `apple_avd` module into `/usr/lib/modules/<kernel>/updates/`;
6. adds `vo=gpu-next`, `gpu-api=opengl`, `hwdec=vaapi` at the top of `~/.config/mpv/mpv.conf`
   (keeping a backup) unless mpv already sets any of them.

Then, **before rebooting**, test the module: save your work, close every video (browser tabs too)
and run

```sh
sudo modprobe -r apple_avd && sudo modprobe apple_avd
```

Play a few videos. If everything works, the module will also load at the next boot.

## Check that it works

```sh
sudo apple-avd-rebuild --status          # patched module installed for your kernel(s)
vainfo --display drm                     # lists H264 and HEVC profiles
mpv -v --hwdec=vaapi video.mp4 | grep -i 'hardware decoding'
```

In Chrome or Chromium, open `chrome://media-internals` while a video plays: the decoder should be
`VaapiVideoDecoder`. Restart the browser if it was open before the module was loaded.

## Kernel updates

A pacman hook rebuilds the module whenever `linux-asahi` or its headers change: it fetches that
kernel's AVD driver source, applies the patches and installs the result. Leading patches that
upstream has already merged are skipped; if upstream has all of them, the stock module is used.
If the patches do not apply, or the source cannot be fetched (offline during the update), the
hook says so and installs nothing for that kernel; the boot service retries at the next boot
while the module is missing. A new kernel then boots with the stock driver and its bugs above
until the build succeeds (`sudo apple-avd-rebuild` retries by hand).

A second hook warns when a package update replaces the VA-API driver or a `libva` update needs it
rebuilt. Omarchy ships its own `libva-v4l2_request-avd`; if a newer version of that package is
published, a system update replaces this build. Run `./install.sh --i-accept-boot-risk` again
afterwards, or add `IgnorePkg = libva-v4l2_request-avd` to `/etc/pacman.conf`.

## Known issues

- **Vulkan output in mpv** (`gpu-api=vulkan`, and `vo=gpu`) shows a green/pink ghost picture: Mesa's
  Vulkan driver for Apple GPUs ignores the plane offsets of imported video frames. Use OpenGL.
- **Washed-out video in Chrome** for full-range H.264 files without a colour description (common for
  screen recordings). That is a Chromium bug. Adding the colour description fixes a file without
  re-encoding:
  ```sh
  ffmpeg -i in.mp4 -c copy -bsf:v h264_metadata=video_full_range_flag=1:colour_primaries=6:transfer_characteristics=6:matrix_coefficients=6 out.mp4
  ```
- **Interlaced H.264 is not supported** by the kernel driver: decoding fails, and players may or may
  not fall back to software. H.264 4:2:2 and 10-bit play in software, because the VA-API driver
  offers only Constrained Baseline, Main and High.
- **A few HEVC conformance streams** decode some pictures wrongly: `RPS_B_qualcomm_5` and
  `RPS_E_qualcomm_5` always, and `SLIST_B_Sony_9`, `SLIST_D_Sony_9` or `RAP_B_Bossen_2` now and
  then when four streams decode at once. Not seen in real videos so far.
- **Firefox** (untested) likely needs `MOZ_DISABLE_RDD_SANDBOX=1`, because its media sandbox blocks
  `/dev/video*` access (this weakens the sandbox).

## If the Mac freezes or resets

If it resets or freezes shortly after boot:

1. **Before you can log in:** boot once with `module_blacklist=apple_avd` added to the kernel
   command line (in your boot loader's entry editor, append it to the line that starts the kernel).
2. **Once logged in:** keep the module from loading at boot and reboot:
   ```sh
   echo 'blacklist apple_avd' | sudo tee /etc/modprobe.d/apple-avd-noboot.conf
   ```
   You can still load it by hand after login with `sudo modprobe apple_avd` (restart the browser
   afterwards). Delete that file to load it at boot again.
3. Open an issue with `journalctl -k -b -1` from the boot that failed.

To remove everything instead, run `./uninstall.sh`.

## Uninstall

```sh
./uninstall.sh
```

Removes the boot service, hooks, script, patches and patched modules (the stock module is used
after a reboot). It leaves the VA-API driver package and mpv settings; the script prints how to
change those.

## Kernel patches

Applied in order to `drivers/media/platform/apple/avd` of the matching AsahiLinux/linux tag.

| Patch | Author | Change |
|---|---|---|
| 0001 | Aaron (aquarat) | allow cacheable (non-coherent) MMAP buffers |
| 0002 | Aaron (aquarat) | H.264: reject slices that reference invalid DPB entries |
| 0003 | Aaron (aquarat) | allocate the per-frame job table with `kvcalloc` |
| 0004 | Aaron (aquarat) | H.264: reset `slice_num` after each frame |
| 0005 | iconidentify | track the running job's state so a completion IRQ or the watchdog cannot finish a job that is still being built or submitted |
| 0006 | iconidentify | HEVC: read controls after applying the request, so a queued-ahead next picture cannot change the current picture's slice count |
| 0007 | iconidentify | size the compressed reference chroma plane for 4:2:2 (it was sized for 4:2:0) |
| 0008 | iconidentify | H.264: fill chroma with grey for monochrome (4:0:0) pictures, which the firmware leaves at zero |
| 0009 | iconidentify | HEVC: reject streams with unequal luma/chroma bit depth before they reach the firmware (narrowed by 0015) |
| 0010 | iconidentify | HEVC: copy the slice and entry point arrays for the run, so userspace cannot free them while the job is built |
| 0011 | iconidentify | HEVC: bound entry points to the array userspace sent; complete the request on every error path |
| 0012 | iconidentify | free job tables that were built but never submitted |
| 0013 | iconidentify | H.264: room for the header plus 4096 slices in the job table; stop the emulation-byte scan at the end of the slice |
| 0014 | iconidentify | H.264: correct grey value for 10-bit 4:0:0 |
| 0015 | iconidentify | accept HEVC 4:2:2 again; reject only bit depths other than 8 and 10, and 4:2:2 at 10 bit (no capture format) |

## Credits

- The AVD driver: The Asahi Linux Contributors ([AsahiLinux/linux](https://github.com/AsahiLinux/linux));
  original reverse engineering in [eiln/avd](https://github.com/eiln/avd).
- Patches 0001-0004: Aaron, [aquarat/apple-avd-driver](https://github.com/aquarat/apple-avd-driver)
  (commit `2d05f4f`, `notes/patches/final-7.1.13`).
- VA-API driver: Ondřej Jirman (megi, libva-v4l2_request); AVD support by
  [sofus13](https://github.com/sofus13/libva-v4l2_request); Chrome early-export fix by Igor Ryzhkov
  and [Ante042](https://github.com/Ante042/libva-v4l2_request).
- `libva/PKGBUILD` and `libva/libva-v4l2_request-avd.install` are based on the
  `libva-v4l2_request-avd` package in
  [omarchy-mac/omarchy-pkgs-aarch64](https://github.com/omarchy-mac/omarchy-pkgs-aarch64).

## License

The kernel patches modify files of the Linux kernel's AVD driver, which are GPL-2.0-only, and are
distributed under GPL-2.0-only; that includes patches 0001-0004 by Aaron (aquarat). The scripts,
hooks and service are GPL-2.0-only as well. See `LICENSE`. The VA-API driver is GPL-3.0-or-later,
in its own repository.
