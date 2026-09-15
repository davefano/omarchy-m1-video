#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-only
# Offline regression tests: no sudo, network, package or module changes.
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
source "$repo/bin/apple-avd-rebuild"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
expect() { [[ $1 == "$2" ]] || { echo "expected '$2', got '$1'" >&2; exit 1; }; }
expect "$(tag_for_pkgver 7.1.13.asahi3-1)" asahi-7.1.13-3
expect "$(tag_for_pkgver 2:7.2rc4.asahi1-2)" asahi-7.2-rc4-1

mkdir -p "$work/patches" "$work/pristine" "$work/build"
B=$work/build
PATCHES=()
# Same path depth and ordered dependencies as the real kernel patch series.
for ((i=1; i<=15; i++)); do
    file=$(printf '%s/patches/%04d.patch' "$work" "$i")
    cat >"$file" <<EOF
--- a/drivers/media/platform/apple/avd/state
+++ b/drivers/media/platform/apple/avd/state
@@ -1 +1 @@
-state=$((i-1))
+state=$i
EOF
    PATCHES+=("$file")
done
# The real helper's patch/copy logic runs as the normal test user.
nob() { "$@"; }
for prefix in 0 4 9 15; do
    echo "state=$prefix" >"$work/pristine/state"
    prepare_tree "$work/pristine"
    expect "$SKIPPED" "$prefix"
    expect "$(cat "$B/avd/state")" state=15
    expect "$(cat "$work/pristine/state")" "state=$prefix"
done
echo 'upstream changed this code' >"$work/pristine/state"
if prepare_tree "$work/pristine"; then
    echo 'incompatible upstream accepted' >&2
    exit 1
else
    expect "$?" 1
fi

LIBVA_SO=$work/driver.so
pacman() {
    case "$*" in
        '-Q libva') echo 'libva 2.24.1-1' ;;
        '-Q libva-v4l2_request-avd') echo 'libva-v4l2_request-avd 1.3.r10-1' ;;
        *) return 1 ;;
    esac
}
if check_libva >"$work/check.log" 2>&1; then
    echo 'missing driver reported healthy' >&2; exit 1
fi
printf '%s\n__vaDriverInit_1_24\n' "$LIBVA_MARKER" >"$LIBVA_SO"
check_libva >"$work/check.log" 2>&1
printf '%s\n__vaDriverInit_1_23\n' "$LIBVA_MARKER" >"$LIBVA_SO"
check_libva >"$work/check.log" 2>&1
for contents in '__vaDriverInit_1_24' "$LIBVA_MARKER" "$LIBVA_MARKER __vaDriverInit_1_25" \
    'exported before its first decode __vaDriverInit_1_24'; do
    echo "$contents" >"$LIBVA_SO"
    if check_libva >"$work/check.log" 2>&1; then
        echo "broken driver reported healthy: $contents" >&2; exit 1
    fi
done
# The installer's consent gate must exit before machine checks or sudo.
if bash "$repo/install.sh" >"$work/consent.log" 2>&1; then
    echo 'installer accepted missing boot-risk consent' >&2; exit 1
else
    expect "$?" 2
fi
grep -q -- '--i-accept-boot-risk' "$work/consent.log"
if bash "$repo/bin/apple-avd-rebuild" --status unexpected >"$work/cli.log" 2>&1; then
    echo 'unexpected CLI argument accepted' >&2; exit 1
else
    expect "$?" 2
fi
printf 'PASS: version tags, patch prefixes 0/4/9/15, incompatible upstream, driver/ABI checks, consent gate, CLI arguments\n'
