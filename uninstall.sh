#!/bin/bash
# Remove what install.sh added. The stock apple_avd module is used again after a reboot.
set -euo pipefail

say() { echo "==> $*"; }

say "removing pacman hooks, rebuild script and patches"
sudo rm -f /etc/pacman.d/hooks/65-apple-avd-rebuild.hook /etc/pacman.d/hooks/65-apple-avd-libva-check.hook
sudo rm -f /usr/local/sbin/apple-avd-rebuild
sudo rm -rf /usr/local/share/apple-avd-patched/patches

say "removing patched apple_avd modules"
for stamp in /usr/lib/modules/*/updates/apple-avd.ko.patched-stamp; do
	[[ -e $stamp ]] || continue
	dir=${stamp%/*}
	kver=$(basename "$(dirname "$dir")")
	sudo rm -f "$dir/apple-avd.ko" "$stamp"
	sudo rmdir "$dir" 2>/dev/null || true
	sudo depmod -a "$kver"
	say "  $kver: stock module restored (takes effect after reboot)"
done

cat <<'EOF'
==> The VA-API driver package is left installed. To go back to your distribution's build:
        sudo pacman -S libva-v4l2_request-avd
    (or remove it: sudo pacman -R libva-v4l2_request-avd)
==> mpv settings in ~/.config/mpv/mpv.conf are left as they are.
EOF
