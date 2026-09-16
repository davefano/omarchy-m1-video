#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-only
# Hardware video decoding (H.264/HEVC) for Omarchy on Apple Silicon Macs with the Asahi kernel.
# Run as your normal user; it uses sudo where needed. Read README.md first.
set -euo pipefail
export LC_ALL=C
cd "$(dirname "$0")"

say() { echo "==> $*"; }
die() { echo "==> ERROR: $*" >&2; exit 1; }

SYSROOT=${OMARCHY_M1_VIDEO_SYSROOT:-}
[[ -z $SYSROOT || $SYSROOT == /* ]] || die "OMARCHY_M1_VIDEO_SYSROOT must be an absolute path"
[[ -z $SYSROOT || ${OMARCHY_M1_VIDEO_TEST_MODE:-0} == 1 ]] || \
	die "OMARCHY_M1_VIDEO_SYSROOT is only available with OMARCHY_M1_VIDEO_TEST_MODE=1"
[[ -z $SYSROOT || $SYSROOT != / ]] || die "refusing to use / as a test sysroot"
[[ -z $SYSROOT || -f $SYSROOT/.omarchy-m1-video-test-root ]] || \
	die "test sysroot is missing .omarchy-m1-video-test-root"
sys() { printf '%s%s' "$SYSROOT" "$1"; }

SHARE=$(sys /usr/local/share/apple-avd-patched)
KVER=$(uname -r)

accept=0
for arg in "$@"; do
	case $arg in
		--i-accept-boot-risk) accept=1 ;;
		*) die "unknown option '$arg' (usage: ./install.sh --i-accept-boot-risk)" ;;
	esac
done
if [[ $accept -ne 1 ]]; then
	cat <<'EOF'
This installs an out-of-tree kernel module for the Mac's video decoder that loads at every
boot. It is not reviewed or supported by Asahi Linux. On the test Mac, the machine hard-reset
twice within about a minute of boot while these patches (0001-0005, unchanged since) were the
module loaded at boot. The cause was not found. With all patches, loading at boot has been
retested once so far (a normal boot and 10 minutes without errors). Read "Before you install"
and "If the Mac freezes or resets" in README.md.

If you accept that risk, run:  ./install.sh --i-accept-boot-risk
EOF
	exit 2
fi

[[ $EUID -ne 0 ]] || die "run this as your normal user, not root"
[[ $(uname -m) == aarch64 ]] || die "this is for aarch64 Apple Silicon Macs"
compat=$(tr '\0' ' ' < "$(sys /proc/device-tree/compatible)" 2>/dev/null || true)
[[ $compat == *apple,* ]] || die "not an Apple Silicon Mac (device tree: ${compat:-none})"
kpkg=$(pacman -Q linux-asahi 2>/dev/null | awk '{print $2}') || true
[[ -n $kpkg ]] || die "needs the linux-asahi kernel package"
say "machine: $compat"
[[ $compat == *t8103* ]] || say "NOTE: only tested on the M1 (t8103). Other chips use the same driver but are untested."

running_asahi=0
[[ $(pacman -Qqo "$(sys "/usr/lib/modules/$KVER/vmlinuz")" 2>/dev/null || true) == linux-asahi ]] && running_asahi=1
[[ $running_asahi -eq 1 ]] || say "NOTE: the running kernel $KVER is not the installed linux-asahi $kpkg (reboot pending after a kernel update?)"

# Headers must match the installed kernel exactly; installing them from a newer
# sync database would be a partial upgrade and cannot build for this kernel.
if hpkg=$(pacman -Q linux-asahi-headers 2>/dev/null | awk '{print $2}') && [[ -n $hpkg ]]; then
	[[ $hpkg == "$kpkg" ]] || die "linux-asahi is $kpkg but linux-asahi-headers is $hpkg: update the whole system (omarchy update, or sudo pacman -Syu), reboot, and run this again"
	need_headers=
else
	repo=$(pacman -Si linux-asahi-headers 2>/dev/null | awk '/^Version/{print $3; exit}') || true
	[[ $repo == "$kpkg" ]] || die "the package database offers linux-asahi-headers ${repo:-(none)} but linux-asahi $kpkg is installed: update the whole system, reboot, and run this again"
	need_headers=linux-asahi-headers
fi

blocked=$(grep -rsE '^[[:space:]]*(blacklist|install)[[:space:]]+apple[-_]avd([[:space:]]|$)' \
	"$(sys /etc/modprobe.d)" "$(sys /usr/lib/modprobe.d)" "$(sys /run/modprobe.d)" || true)
cmdline_block=$(grep -oE '(module_blacklist|modprobe\.blacklist)=[^ ]*apple[-_]avd' "$(sys /proc/cmdline)" || true)
if [[ -n $blocked || -n $cmdline_block ]]; then
	say "NOTE: apple_avd is currently blocked from loading:"
	[[ -n $blocked ]] && printf '       %s\n' "$blocked"
	[[ -n $cmdline_block ]] && echo "       kernel command line: $cmdline_block"
	say "This script does not change that. Hardware decoding stays off until you remove it."
fi

say "installing build dependencies"
# shellcheck disable=SC2086
sudo pacman -S --needed --noconfirm base-devel git meson libdrm libva libva-utils patch $need_headers || \
	die "installing build dependencies failed; fix the package error and rerun this installer"

say "building and installing the VA-API driver (libva-v4l2_request-avd)"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cp libva/PKGBUILD libva/libva-v4l2_request-avd.install "$work/"
(cd "$work" && makepkg -si --noconfirm) || \
	die "building or installing the VA-API package failed; existing kernel modules were not changed; fix the error and rerun this installer"

say "installing kernel driver patches, rebuild script, pacman hooks and boot service"
sudo install -d "$SHARE/patches" || die "creating the managed patch directory failed; fix the error and rerun this installer"
sudo find "$SHARE/patches" -maxdepth 1 -name '*.patch' -delete || die "cleaning the managed patch directory failed; fix the error and rerun this installer"
sudo install -m644 patches/*.patch "$SHARE/patches/" || die "installing the managed patch set failed; fix the error and rerun this installer"
sudo install -Dm755 bin/apple-avd-rebuild "$(sys /usr/local/sbin/apple-avd-rebuild)" || die "installing apple-avd-rebuild failed; fix the error and rerun this installer"
sudo install -Dm644 -t "$(sys /etc/pacman.d/hooks)" hooks/*.hook || die "installing pacman hooks failed; fix the error and rerun this installer"
sudo install -Dm644 systemd/apple-avd-rebuild.service "$(sys /etc/systemd/system/apple-avd-rebuild.service)" || die "installing the boot service failed; fix the error and rerun this installer"
sudo systemctl daemon-reload || die "reloading systemd failed; installed files are retained; fix the error and rerun this installer"
sudo systemctl enable apple-avd-rebuild.service || die "enabling the boot service failed; installed files are retained; fix the error and rerun this installer"

say "building the patched apple_avd module for the installed kernel(s)"
if ! sudo "$(sys /usr/local/sbin/apple-avd-rebuild)" --force; then
	die "building the patched module failed (messages above). The VA-API driver, hooks and boot service are installed; fix the problem and run ./install.sh --i-accept-boot-risk again"
fi

conf=${XDG_CONFIG_HOME:-$HOME/.config}/mpv/mpv.conf
[[ ! -L $conf && ! -L $conf.before-omarchy-m1-video ]] || \
	die "refusing to follow a symbolic link for $conf or its backup"
mkdir -p "$(dirname "$conf")"
touch "$conf"
if grep -qE '^[[:space:]]*(hwdec|vo|gpu-api)[[:space:]]*=' "$conf"; then
	say "mpv: $conf already sets hwdec, vo or gpu-api; make sure the top of the file (before any [profile]) has:"
	printf '       vo=gpu-next\n       gpu-api=opengl\n       hwdec=vaapi\n'
else
	# At the top: options after a [profile] header would only apply to that profile.
	cp -p "$conf" "$conf.before-omarchy-m1-video"
	{
		printf '# omarchy-m1-video: hardware decoding; OpenGL output (Vulkan shows a green/pink ghost)\n'
		printf 'vo=gpu-next\ngpu-api=opengl\nhwdec=vaapi\n\n'
		cat "$conf.before-omarchy-m1-video"
	} >"$conf"
	say "mpv: added vo=gpu-next, gpu-api=opengl, hwdec=vaapi at the top of $conf (backup: $conf.before-omarchy-m1-video)"
fi

echo
if [[ $running_asahi -ne 1 || ! -f $(sys "/usr/lib/modules/$KVER/updates/apple-avd.ko") ]]; then
	say "Done. Reboot into the installed kernel; the patched module is built for it and loads at boot."
elif [[ -n $blocked || -n $cmdline_block ]]; then
	say "Done, but apple_avd is blocked from loading (see above)."
else
	cat <<'EOF'
==> Done. The patched module loads at the next boot.
    Test it before rebooting: save your work, close every video (browser tabs too), then run
        sudo modprobe -r apple_avd && sudo modprobe apple_avd
    and play a video. If the Mac misbehaves, see "If the Mac freezes or resets" in README.md.
EOF
fi
cat <<'EOF'
==> Check:  sudo apple-avd-rebuild --status
            vainfo --display drm                  (lists H264 and HEVC profiles)
            mpv -v --hwdec=vaapi video.mp4 | grep -i 'hardware decoding'
EOF
