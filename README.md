# omarchy-m1-video

Hardware video decoding (H.264 and HEVC) for [Omarchy](https://omarchy.org) on Apple Silicon
Macs running the Asahi Linux kernel. mpv and Chrome decode video on the Mac's built-in video
decoder (AVD) instead of the CPU.

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
| Several HEVC videos at once (and some single HEVC streams) fail with firmware "H0 error" | kernel patch 0006 |
| Chrome shows solid green video | VA-API driver |
| H.264 videos with several CAVLC slices per picture hang | VA-API driver |
| HEVC streams with tiles or wavefront parallel processing hang | VA-API driver |
| 10-bit HEVC decodes to black | VA-API driver |

Conformance results on an M1 through VA-API: HEVC 143 of 147 streams bit-exact
(`JCT-VC-HEVC_V1`; software FFmpeg gets 143 too), H.264 73 of 135 (`JVT-AVC_V1`; the rest are
interlaced or profiles FFmpeg does not hand to VA-API). Real recordings up to 2560x1600 decode
bit-exact.

## Tested on

- MacBook Pro 13" M1 (T8103), Omarchy (omarchy-mac), `linux-asahi` 7.1.13-3
- mpv with `vo=gpu-next`, `gpu-api=opengl`; Google Chrome 152

Other Apple Silicon Macs use the same driver and should work, but have not been tested.
Reports (working or not) are welcome as issues.

## Install

Save your work first: reloading a video decoder kernel module can crash the machine if something
is wrong.

```sh
git clone https://github.com/iconidentify/omarchy-m1-video
cd omarchy-m1-video
./install.sh
```

Then reboot (or close every video and run `sudo modprobe -r apple_avd && sudo modprobe apple_avd`).

`install.sh`:
1. checks for an Apple Silicon Mac with the `linux-asahi` kernel;
2. installs build dependencies (`base-devel git meson libdrm libva patch linux-asahi-headers`);
3. builds and installs `libva-v4l2_request-avd` from
   [iconidentify/libva-v4l2_request](https://github.com/iconidentify/libva-v4l2_request)
   (`libva/PKGBUILD`);
4. copies the kernel patches to `/usr/local/share/apple-avd-patched/patches`, the rebuild script to
   `/usr/local/sbin/apple-avd-rebuild` and two pacman hooks to `/etc/pacman.d/hooks`;
5. builds the patched `apple_avd` module into `/usr/lib/modules/<kernel>/updates/`;
6. adds `vo=gpu-next`, `gpu-api=opengl`, `hwdec=vaapi` to `~/.config/mpv/mpv.conf` unless mpv
   is already configured.

## Check that it works

```sh
sudo apple-avd-rebuild --status          # patched module installed for your kernel(s)
vainfo --display drm                     # lists H264 and HEVC profiles
mpv -v --hwdec=vaapi video.mp4 | grep -i 'hardware decoding'
```

In Chrome, open `chrome://media-internals` while a video plays: the decoder should be
`VaapiVideoDecoder`.

## Kernel updates

A pacman hook rebuilds the module whenever `linux-asahi` or its headers change: it fetches that
kernel's AVD driver source, applies the patches and installs the result. If a patch no longer
applies, it says so and leaves the stock module in place (the stock bugs above come back until
the patches are updated here). Patches that upstream has already merged are skipped.

A second hook warns when a package update replaces the VA-API driver or a `libva` update needs it
rebuilt. Rebuild by running `./install.sh` again.

## Known issues

- **Vulkan output in mpv** (`gpu-api=vulkan`, and `vo=gpu`) shows a green/pink ghost picture: Mesa's
  Vulkan driver for Apple GPUs ignores the plane offsets of imported video frames. Use OpenGL.
- **Washed-out video in Chrome** for full-range H.264 files without a colour description (common for
  screen recordings). That is a Chromium bug. Adding the colour description fixes a file without
  re-encoding:
  ```sh
  ffmpeg -i in.mp4 -c copy -bsf:v h264_metadata=video_full_range_flag=1:colour_primaries=6:transfer_characteristics=6:matrix_coefficients=6 out.mp4
  ```
- **Software decoding still used** for interlaced H.264, H.264 4:2:2 and 10-bit H.264: the driver
  offers VA-API only Baseline, Main and High.
- **A few HEVC conformance streams** (`RPS_B_qualcomm_5`, `RPS_E_qualcomm_5`) decode some pictures
  wrongly. Not seen in real videos so far.
- **Firefox** needs `MOZ_DISABLE_RDD_SANDBOX=1`, because its media sandbox blocks `/dev/video*`
  access (this weakens the sandbox).

## If the Mac freezes or resets

During development an earlier version of the race fix coincided with two idle hard resets right
after boot. It was not reproduced afterwards (parallel decode stress tests, 30-minute idle soaks,
device probe soaks), and the cause was not found. If it happens to you, stop the module from
loading and reboot:

```sh
echo 'install apple_avd /bin/false' | sudo tee /etc/modprobe.d/apple-avd-disabled.conf
```

Then open an issue with `journalctl -k -b -1` from the boot that failed. Remove that file to turn
hardware decoding back on.

## Uninstall

```sh
./uninstall.sh
```

Removes the hooks, script, patches and patched modules (the stock module is used after a reboot).
It leaves the VA-API driver package and mpv settings; the script prints how to change those.

## Kernel patches

Applied to `drivers/media/platform/apple/avd` of the matching AsahiLinux/linux tag.

| Patch | Author | Change |
|---|---|---|
| 0001 | Aaron (aquarat) | allow cacheable (non-coherent) MMAP buffers |
| 0002 | Aaron (aquarat) | H.264: reject slices that reference invalid DPB entries |
| 0003 | Aaron (aquarat) | allocate the per-frame job table with `kvcalloc` |
| 0004 | Aaron (aquarat) | H.264: reset `slice_num` after each frame |
| 0005 | iconidentify | track the running job's state so a completion IRQ or the watchdog cannot finish a job that is still being built or submitted |
| 0006 | iconidentify | HEVC: read controls after applying the request, so a queued-ahead next picture cannot change the current picture's slice count |

## Credits

- The AVD driver: The Asahi Linux Contributors ([AsahiLinux/linux](https://github.com/AsahiLinux/linux));
  original reverse engineering in [eiln/avd](https://github.com/eiln/avd).
- Patches 0001-0004: Aaron, [aquarat/apple-avd-driver](https://github.com/aquarat/apple-avd-driver).
- VA-API driver: Ondřej Jirman (megi, libva-v4l2_request); AVD support by
  [sofus13](https://github.com/sofus13/libva-v4l2_request); Chrome early-export fix by Igor Ryzhkov
  and [Ante042](https://github.com/Ante042/libva-v4l2_request).

## License

Kernel patches and scripts: GPL-2.0 (see `LICENSE`). The VA-API driver keeps its own license in
its repository.
