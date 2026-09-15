# Instructions for coding agents

This repository sets up hardware video decoding on Apple Silicon Macs running Omarchy with the
`linux-asahi` kernel. Read `README.md` fully before acting.

1. **Check the machine first.** `uname -m` must be `aarch64`, `/proc/device-tree/compatible` must
   contain `apple,`, and `pacman -Q linux-asahi` must succeed. Otherwise stop and tell the user
   this repository does not apply.
2. **Get the user's explicit consent before installing.** Explain in your own words that this
   installs an out-of-tree kernel module that loads at every boot, that the test Mac hard-reset
   twice shortly after boot with these patches loaded at boot (cause unknown, not retested at boot),
   and summarize "If the Mac freezes or resets" from `README.md`. Also say it installs pacman hooks,
   a boot service, a replacement VA-API driver package and mpv settings. Only continue after the
   user clearly agrees; do not pass `--i-accept-boot-risk` on your own.
3. **Ask the user to save their work** before any `modprobe -r apple_avd` and before rebooting.
4. **Install** by running `./install.sh --i-accept-boot-risk` as the normal user (it calls sudo
   itself). Do not edit the patches. If it stops with an error about headers not matching the
   kernel, the system needs a full update and a reboot first; tell the user instead of forcing it.
5. **Test before rebooting:** with every video closed,
   `sudo modprobe -r apple_avd && sudo modprobe apple_avd`, then have the user play a video.
6. **Verify** with `sudo apple-avd-rebuild --status`, `vainfo --display drm` (H264 and HEVC
   profiles listed) and `mpv -v --hwdec=vaapi <video> | grep -i 'hardware decoding'`.
7. **mpv output:** keep `gpu-api=opengl`; Vulkan output shows a green/pink ghost picture.
8. **If the machine freezes or resets**, follow "If the Mac freezes or resets" in `README.md`.
9. **Do not report problems** with this setup to Asahi Linux or other upstream projects. Report
   them as issues in this repository.
10. **To undo**, run `./uninstall.sh` and reboot.
