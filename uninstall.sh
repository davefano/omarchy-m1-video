#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-only
# Remove what install.sh added. The stock apple_avd module is used again after a reboot.
set -euo pipefail
export LC_ALL=C
shopt -s nullglob

say() { echo "==> $*"; }

SYSROOT=${OMARCHY_M1_VIDEO_SYSROOT:-}
TEST_MODE=${OMARCHY_M1_VIDEO_TEST_MODE:-0}
test_root_error() { echo "invalid test environment: $*" >&2; exit 1; }
[[ $TEST_MODE == 0 || $TEST_MODE == 1 ]] || test_root_error "unknown test mode"
if [[ $TEST_MODE == 1 ]]; then
	[[ -n $SYSROOT ]] || test_root_error "test mode requires a disposable sysroot"
	[[ $EUID -ne 0 ]] || test_root_error "test mode must run as an unprivileged user"
fi
[[ -z $SYSROOT || $TEST_MODE == 1 ]] || \
	test_root_error "OMARCHY_M1_VIDEO_SYSROOT is only available with OMARCHY_M1_VIDEO_TEST_MODE=1"
if [[ -n $SYSROOT ]]; then
	[[ $SYSROOT == /* ]] || test_root_error "OMARCHY_M1_VIDEO_SYSROOT must be an absolute path"
	[[ $SYSROOT != / ]] || test_root_error "refusing to use / as a test sysroot"
	physical_root=$(cd -- "$SYSROOT" 2>/dev/null && pwd -P) || test_root_error "sysroot does not exist"
	[[ $SYSROOT == "$physical_root" ]] || test_root_error "sysroot must be a canonical physical directory"
	[[ -f $SYSROOT/.omarchy-m1-video-test-root && ! -L $SYSROOT/.omarchy-m1-video-test-root ]] || \
		test_root_error "test sysroot is missing .omarchy-m1-video-test-root"
fi
sys() { printf '%s%s' "$SYSROOT" "$1"; }

say "removing the boot service, pacman hooks, rebuild script and patches"
sudo systemctl disable apple-avd-rebuild.service 2>/dev/null || true
sudo rm -f "$(sys /etc/systemd/system/apple-avd-rebuild.service)"
sudo systemctl daemon-reload
sudo rm -f "$(sys /etc/pacman.d/hooks/65-apple-avd-rebuild.hook)" "$(sys /etc/pacman.d/hooks/65-apple-avd-libva-check.hook)"
sudo rm -f "$(sys /usr/local/sbin/apple-avd-rebuild)"
sudo rm -rf "$(sys /usr/local/share/apple-avd-patched/patches)"
sudo rmdir "$(sys /usr/local/share/apple-avd-patched)" 2>/dev/null || true

say "removing patched apple_avd modules"
for stamp in "$(sys /usr/lib/modules)"/*/updates/apple-avd.ko.patched-stamp; do
	dir=${stamp%/*}
	kver=$(basename "$(dirname "$dir")")
	sudo rm -f "$dir/apple-avd.ko" "$stamp"
	sudo rmdir "$dir" 2>/dev/null || true
	sudo depmod -a "$kver"
	say "  $kver: stock module restored (takes effect after reboot)"
done

cat <<'EOF'
==> After a reboot the stock driver is back, and it stops every H.264 stream after 4096 slices.
    If videos stop or freeze, turn hardware decoding off: set hwdec=no in ~/.config/mpv/mpv.conf.
==> The VA-API driver package is left installed. To go back to your distribution's build:
        sudo pacman -S libva-v4l2_request-avd
    (or remove it: sudo pacman -R libva-v4l2_request-avd)
==> mpv settings in ~/.config/mpv/mpv.conf are left as they are.
EOF
