#!/bin/bash
# Hardware video decoding (H.264/HEVC) for Omarchy on Apple Silicon Macs with the Asahi kernel.
# Run as your normal user; it uses sudo where needed. See README.md.
set -euo pipefail
cd "$(dirname "$0")"

SHARE=/usr/local/share/apple-avd-patched

say() { echo "==> $*"; }
die() { echo "==> ERROR: $*" >&2; exit 1; }

[[ $EUID -ne 0 ]] || die "run this as your normal user, not root"
[[ $(uname -m) == aarch64 ]] || die "this is for aarch64 Apple Silicon Macs"
compat=$(tr '\0' ' ' < /proc/device-tree/compatible 2>/dev/null || true)
[[ $compat == *apple,* ]] || die "not an Apple Silicon Mac (device tree: ${compat:-none})"
pacman -Q linux-asahi >/dev/null 2>&1 || die "needs the linux-asahi kernel package"
say "machine: $compat"
[[ $compat == *t8103* ]] || say "NOTE: only tested on the M1 (t8103). Other chips use the same driver but are untested."

if grep -rqs 'apple_avd' /etc/modprobe.d/; then
	say "WARNING: /etc/modprobe.d blocks apple_avd:"
	grep -rs 'apple_avd' /etc/modprobe.d/
	say "Remove that line if you want hardware decoding; this script does not touch it."
fi

say "installing build dependencies"
sudo pacman -S --needed --noconfirm base-devel git meson libdrm libva patch linux-asahi-headers

say "building and installing the VA-API driver (libva-v4l2_request-avd)"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cp libva/PKGBUILD libva/libva-v4l2_request-avd.install "$work/"
(cd "$work" && makepkg -si --noconfirm)

say "installing kernel driver patches, rebuild script and pacman hooks"
sudo install -d "$SHARE/patches"
sudo rm -f "$SHARE"/patches/0*.patch
sudo install -m644 patches/*.patch "$SHARE/patches/"
sudo install -Dm755 bin/apple-avd-rebuild /usr/local/sbin/apple-avd-rebuild
sudo install -Dm644 -t /etc/pacman.d/hooks hooks/*.hook

say "building the patched apple_avd module for the installed kernel(s)"
sudo /usr/local/sbin/apple-avd-rebuild --force

conf=${XDG_CONFIG_HOME:-$HOME/.config}/mpv/mpv.conf
mkdir -p "$(dirname "$conf")"
touch "$conf"
if grep -qE '^\s*(hwdec|vo|gpu-api)\s*=' "$conf"; then
	say "mpv: $conf already sets hwdec/vo/gpu-api; make sure it has:"
	printf '       vo=gpu-next\n       gpu-api=opengl\n       hwdec=vaapi\n'
else
	printf '\n# omarchy-m1-video: hardware decoding; OpenGL output (Vulkan shows a green/pink ghost)\nvo=gpu-next\ngpu-api=opengl\nhwdec=vaapi\n' >> "$conf"
	say "mpv: added vo=gpu-next, gpu-api=opengl, hwdec=vaapi to $conf"
fi

cat <<'EOF'
==> Done. The patched module loads on the next boot.
    To load it now instead, close every video (browser tabs too) and run:
        sudo modprobe -r apple_avd && sudo modprobe apple_avd
==> Check:  vainfo --display drm              (lists H264 and HEVC profiles)
            mpv -v --hwdec=vaapi video.mp4 | grep -i 'hardware decoding'
EOF
