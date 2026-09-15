# Instructions for coding agents

This repository sets up hardware video decoding on Apple Silicon Macs running Omarchy with the
`linux-asahi` kernel. Read `README.md` fully before acting.

1. **Check the machine first.** `uname -m` must be `aarch64`, `/proc/device-tree/compatible` must
   contain `apple,`, and `pacman -Q linux-asahi` must succeed. Otherwise stop and tell the user
   this repository does not apply.
2. **Ask the user to save their work** before `install.sh` finishes building the kernel module and
   before any `modprobe -r apple_avd`: reloading the decoder module can crash the machine.
3. **Install** by running `./install.sh` as the normal user (it calls sudo itself). Do not edit
   the patches.
4. **Activate** with a reboot, or with every video closed:
   `sudo modprobe -r apple_avd && sudo modprobe apple_avd`.
5. **Verify** with `sudo apple-avd-rebuild --status`, `vainfo --display drm` (H264 and HEVC
   profiles listed) and `mpv -v --hwdec=vaapi <video> | grep -i 'hardware decoding'`.
6. **mpv output:** keep `gpu-api=opengl`; Vulkan output shows a green/pink ghost picture.
7. **If the machine freezes or resets**, follow "If the Mac freezes or resets" in `README.md`.
8. **Do not report problems** with this setup to Asahi Linux or other upstream projects. Report
   them as issues in this repository.
9. **To undo**, run `./uninstall.sh` and reboot.
