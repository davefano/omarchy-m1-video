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
libva_version=2.24.1-1
pacman() {
    case "$*" in
        '-Q libva') [[ -n $libva_version ]] && echo "libva $libva_version" ;;
        '-Q libva-v4l2_request-avd') echo 'libva-v4l2_request-avd 1.3.r11-1' ;;
        *) return 1 ;;
    esac
}
# Compile real ELF fixtures: a string or undefined symbol is not an entry point.
# Set the target machine for static inspection on non-AArch64 test hosts too.
# These synthetic objects must never be loaded or executed.
make_driver() {
    printf 'const char marker[] = "%s";\n%s\n' "$LIBVA_MARKER" "$1" >"$work/driver.c"
    cc -shared -fPIC -o "$LIBVA_SO" "$work/driver.c"
    printf '\267\000' | dd of="$LIBVA_SO" bs=1 seek=18 conv=notrunc status=none
}
reject_driver() {
    if check_libva >"$work/check.log" 2>&1; then
        echo "broken driver reported healthy: $1" >&2; exit 1
    fi
    grep -Fq -- "$2" "$work/check.log" || {
        cat "$work/check.log" >&2; echo "missing recovery message: $2" >&2; exit 1;
    }
}
printf '%s\n__vaDriverInit_1_24\n' "$LIBVA_MARKER" >"$LIBVA_SO"
reject_driver 'text masquerading as ELF' 'cannot inspect VA-API dynamic symbols'
rm "$LIBVA_SO"
reject_driver 'missing file' 'Run install.sh from omarchy-m1-video again'
make_driver 'int __vaDriverInit_1_24(void) { return 0; }'
check_libva >"$work/check.log" 2>&1
# A matching marker and export cannot make an incompatible ELF loadable.
for header in machine unknown-machine type unknown-type class unknown-class endian unknown-endian; do
    make_driver 'int __vaDriverInit_1_24(void) { return 0; }'
    case "$header" in
        machine) offset=18; bytes='\076\000' ;;
        unknown-machine) offset=18; bytes='\000\000' ;;
        type) offset=16; bytes='\002\000' ;;
        unknown-type) offset=16; bytes='\000\000' ;;
        class) offset=4; bytes='\001' ;;
        unknown-class) offset=4; bytes='\000' ;;
        endian) offset=5; bytes='\002' ;;
        unknown-endian) offset=5; bytes='\000' ;;
    esac
    printf '%b' "$bytes" | dd of="$LIBVA_SO" bs=1 seek="$offset" conv=notrunc status=none
    reject_driver "incompatible ELF $header" 'Run install.sh from omarchy-m1-video again'
done
make_driver 'int __vaDriverInit_1_23(void) { return 0; }'
check_libva >"$work/check.log" 2>&1
make_driver 'int __vaDriverInit_1_25(void) { return 0; }'
reject_driver 'newer ABI' 'newer libva'
make_driver 'const char text[] = "__vaDriverInit_1_24";'
reject_driver 'entry point only in data' 'no supported VA-API entry point'
make_driver 'int __vaDriverInit_1_24 = 0;'
reject_driver 'entry point is not a function' 'no supported VA-API entry point'
make_driver 'int __vaDriverInit_1_024(void) { return 0; }'
reject_driver 'noncanonical entry point name' 'no supported VA-API entry point'
make_driver 'extern int __vaDriverInit_1_24(void); int call(void) { return __vaDriverInit_1_24(); }'
reject_driver 'undefined entry point' 'no supported VA-API entry point'
make_driver '__attribute__((visibility("hidden"))) int __vaDriverInit_1_24(void) { return 0; }'
reject_driver 'hidden entry point' 'no supported VA-API entry point'
make_driver 'int __vaDriverInit_2_24(void) { return 0; }'
reject_driver 'unknown ABI major' 'no supported VA-API entry point'
# libva searches older versions too, independent of symbol-table order.
make_driver 'int __vaDriverInit_1_25(void) { return 0; } int __vaDriverInit_1_23(void) { return 0; }'
check_libva >"$work/check.log" 2>&1
saved_marker=$LIBVA_MARKER
LIBVA_MARKER='wrong build'
make_driver 'int __vaDriverInit_1_24(void) { return 0; }'
LIBVA_MARKER=$saved_marker
reject_driver 'wrong marker' 'Run install.sh from omarchy-m1-video again'
make_driver 'int __vaDriverInit_1_24(void) { return 0; }'
for libva_version in '' unknown 3.24.1-1 2.bad.1-1; do
    reject_driver "unknown libva $libva_version" 'cannot determine a supported installed libva ABI'
done
libva_version=2:2.24.1-1
check_libva >"$work/check.log" 2>&1
# Inspector failure must fail closed instead of treating arbitrary strings as ELF.
readelf() { return 127; }
reject_driver 'unavailable inspector' 'cannot inspect VA-API dynamic symbols'
unset -f readelf

# An update changes the next-load module on disk, never proves the loaded binary.
SYSROOT=$work/status-root
mkdir -p "$SYSROOT/sys/module/apple_avd"
echo O >"$SYSROOT/sys/module/apple_avd/taint"
asahi_kernels() { :; }
selected_module=/old/apple-avd.ko
modinfo() { echo "$selected_module"; }
status >"$work/status-before.log" 2>&1
selected_module=/new/apple-avd.ko
status >"$work/status-after.log" 2>&1
grep -Fq 'module selected for the next load: /old/apple-avd.ko' "$work/status-before.log"
grep -Fq 'module selected for the next load: /new/apple-avd.ko' "$work/status-after.log"
for log in "$work/status-before.log" "$work/status-after.log"; do
    grep -Fq 'loaded module binary identity: unknown' "$log"
done
rm -r "$SYSROOT/sys/module/apple_avd"
status >"$work/status-unloaded.log" 2>&1
grep -Fq 'loaded module binary identity: not loaded' "$work/status-unloaded.log"
SYSROOT=
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
printf 'PASS: version tags, patch prefixes 0/4/9/15, incompatible upstream, ELF driver/ABI checks, loaded/next-load status, consent gate, CLI arguments\n'
