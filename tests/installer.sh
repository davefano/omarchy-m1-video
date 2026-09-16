#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-only
# Hermetic installer scenarios. All privileged/package/service commands are shims.
set -euo pipefail

repo=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d)
work=$(cd "$work" && pwd -P)
trap 'rm -rf "$work"' EXIT
real_path=$PATH

fail() { echo "FAIL: $*" >&2; exit 1; }
expect_status() {
	local want=$1; shift
	set +e
	"$@"
	local got=$?
	set -e
	[[ $got -eq $want ]] || fail "expected status $want, got $got: $*"
}
contains() {
	grep -Fq -- "$2" "$1" && return 0
	echo "--- $1" >&2
	cat "$1" >&2
	fail "$1 does not contain: $2"
}
absent() { [[ ! -e $1 && ! -L $1 ]] || fail "unexpected path remains: $1"; }
same() { [[ $1 == "$2" ]] || fail "expected '$2', got '$1'"; }

make_shims() {
	mkdir -p "$work/bin"
	cat >"$work/bin/uname" <<'EOF'
#!/bin/bash
case "${1:-}" in
	-m) echo aarch64 ;;
	-r) echo 7.1.13-asahi-test ;;
	*) echo Linux ;;
esac
EOF
	cat >"$work/bin/pacman" <<'EOF'
#!/bin/bash
printf 'pacman %s\n' "$*" >>"$TEST_COMMAND_LOG"
case "$*" in
	'-Q linux-asahi') echo 'linux-asahi 7.1.13.asahi3-1' ;;
	'-Q linux-asahi-headers')
		[[ ${TEST_HEADERS:-match} != missing ]] || exit 1
		echo "linux-asahi-headers ${TEST_HEADER_VERSION:-7.1.13.asahi3-1}" ;;
	'-Si linux-asahi-headers') echo "Version : ${TEST_REPO_HEADER_VERSION:-7.1.13.asahi3-1}" ;;
	-Qqo*) echo linux-asahi ;;
	-S*) exit 0 ;;
	*) exit 1 ;;
esac
EOF
	cat >"$work/bin/makepkg" <<'EOF'
#!/bin/bash
printf 'makepkg %s\n' "$*" >>"$TEST_COMMAND_LOG"
[[ ${TEST_MAKEPKG_FAIL:-0} -eq 0 ]]
EOF
	cat >"$work/bin/sudo" <<'EOF'
#!/bin/bash
set -euo pipefail
printf 'sudo %s\n' "$*" >>"$TEST_COMMAND_LOG"
guard_path() {
    case "$1" in
        "$TEST_ROOT"|"$TEST_ROOT"/*) ;;
        *) echo "test command escaped disposable root: $1" >&2; exit 99 ;;
    esac
    case "$1/" in
        */../*|*/./*) echo "test command contains path traversal: $1" >&2; exit 99 ;;
    esac
    local parent=$1
    while [[ $parent != "$TEST_ROOT" ]]; do
        [[ ! -L $parent ]] || { echo "test command follows a symlink: $1" >&2; exit 99; }
        parent=${parent%/*}
    done
}
case "${1:-}" in
	pacman)
		[[ ${TEST_PACMAN_FAIL:-0} -eq 0 ]] || exit 1
		exec pacman "${@:2}" ;;
	install)
		[[ ${TEST_INSTALL_FAIL:-0} -eq 0 ]] || exit 1
		shift
		case "${1:-}" in
			-d)
				shift; for dest in "$@"; do guard_path "$dest"; done; mkdir -p "$@" ;;
			-m644)
				shift; dest=${!#}; guard_path "$dest"; mkdir -p "$dest"
				for src in "${@:1:$#-1}"; do cp "$src" "$dest/"; chmod 0644 "$dest/$(basename "$src")"; done ;;
			-Dm755)
				src=$2; dest=$3; guard_path "$dest"; mkdir -p "$(dirname "$dest")"; cp "$src" "$dest"; chmod 0755 "$dest" ;;
			-Dm644)
				shift
				if [[ ${1:-} == -t ]]; then
					dest=$2; guard_path "$dest"; shift 2; mkdir -p "$dest"
					for src in "$@"; do cp "$src" "$dest/"; chmod 0644 "$dest/$(basename "$src")"; done
				else
					src=$1; dest=$2; guard_path "$dest"; mkdir -p "$(dirname "$dest")"; cp "$src" "$dest"; chmod 0644 "$dest"
				fi ;;
			*) echo "unsupported fake install: $*" >&2; exit 97 ;;
		esac ;;
	find)
		shift; guard_path "$1"; find "$@" ;;
	systemctl)
		[[ ${TEST_SYSTEMCTL_FAIL:-0} -eq 0 ]] || exit 1
		exit 0 ;;
	rm)
		shift; for dest in "$@"; do [[ $dest == -* ]] || guard_path "$dest"; done; rm "$@" ;;
	rmdir)
		shift; for dest in "$@"; do [[ $dest == -* ]] || guard_path "$dest"; done; rmdir "$@" ;;
	depmod)
		exit 0 ;;
	*/usr/local/sbin/apple-avd-rebuild)
		[[ ${TEST_REBUILD_FAIL:-0} -eq 0 ]] || exit 1
		dest="$TEST_ROOT/usr/lib/modules/$TEST_KVER/updates"
		mkdir -p "$dest"
		printf 'new module\n' >"$dest/apple-avd.ko"
		printf 'test stamp\n' >"$dest/apple-avd.ko.patched-stamp" ;;
	*)
		echo "forbidden fake sudo command: $*" >&2
		exit 98 ;;
esac
EOF
	cat >"$work/bin/timeout" <<'EOF'
#!/bin/bash
shift
exec "$@"
EOF
	cat >"$work/bin/git" <<'EOF'
#!/bin/bash
printf 'git %s\n' "$*" >>"$TEST_COMMAND_LOG"
[[ ${TEST_GIT_FAIL:-0} -eq 0 ]] || exit 1
echo 'unexpected successful git shim' >&2
exit 96
EOF
	export TEST_REAL_SHA256SUM=$(command -v sha256sum || true)
	cat >"$work/bin/sha256sum" <<'EOF'
#!/bin/bash
if [[ -n ${TEST_REAL_SHA256SUM:-} ]]; then
	exec "$TEST_REAL_SHA256SUM" "$@"
fi
shasum -a 256 "$@"
EOF
	cat >"$work/bin/flock" <<'EOF'
#!/bin/bash
exit 0
EOF
	chmod +x "$work/bin/uname" "$work/bin/pacman" "$work/bin/makepkg" "$work/bin/sudo" \
		"$work/bin/timeout" "$work/bin/git" "$work/bin/sha256sum" "$work/bin/flock"
}

reset_fixture() {
	local name=$1
	export TEST_ROOT="$work/$name/root"
	export TEST_HOME="$work/$name/home"
	export TEST_KVER=7.1.13-asahi-test
	export TEST_COMMAND_LOG="$work/$name/commands.log"
	export OMARCHY_M1_VIDEO_SYSROOT=$TEST_ROOT
	export OMARCHY_M1_VIDEO_TEST_MODE=1
	export HOME=$TEST_HOME
	export XDG_CONFIG_HOME=$TEST_HOME/.config
	export PATH="$work/bin:$real_path"
	unset TEST_HEADERS TEST_HEADER_VERSION TEST_REPO_HEADER_VERSION TEST_PACMAN_FAIL TEST_MAKEPKG_FAIL \
		TEST_INSTALL_FAIL TEST_SYSTEMCTL_FAIL TEST_REBUILD_FAIL TEST_GIT_FAIL
	mkdir -p "$TEST_ROOT/proc/device-tree" "$TEST_ROOT/usr/lib/modules/$TEST_KVER" \
		"$TEST_ROOT/etc/modprobe.d" "$TEST_ROOT/usr/lib/modprobe.d" "$TEST_ROOT/run/modprobe.d" \
		"$TEST_HOME/.config/mpv"
	: >"$TEST_ROOT/.omarchy-m1-video-test-root"
	printf 'apple,t8103\0' >"$TEST_ROOT/proc/device-tree/compatible"
	printf 'quiet\n' >"$TEST_ROOT/proc/cmdline"
	printf 'kernel\n' >"$TEST_ROOT/usr/lib/modules/$TEST_KVER/vmlinuz"
	: >"$TEST_COMMAND_LOG"
}

run_install() {
	(cd "$repo" && bash ./install.sh --i-accept-boot-risk) >"$1" 2>&1
}
run_uninstall() {
	(cd "$repo" && bash ./uninstall.sh) >"$1" 2>&1
}

make_shims

# Every no-consent entry exits before machine checks and before a command shim.
reset_fixture consent
expect_status 2 bash "$repo/install.sh" >"$work/consent/install.log" 2>&1
contains "$work/consent/install.log" '--i-accept-boot-risk'
[[ ! -s $TEST_COMMAND_LOG ]] || fail "consent gate executed external commands"

# A first install writes only into the disposable root and preserves prior mpv content.
reset_fixture first
printf 'volume=75\n' >"$XDG_CONFIG_HOME/mpv/mpv.conf"
run_install "$work/first/install.log"
[[ -f $TEST_ROOT/etc/pacman.d/hooks/65-apple-avd-rebuild.hook ]] || fail "rebuild hook missing"
[[ -f $TEST_ROOT/etc/systemd/system/apple-avd-rebuild.service ]] || fail "service missing"
[[ -f $TEST_ROOT/usr/local/sbin/apple-avd-rebuild ]] || fail "rebuild helper missing"
[[ -f $TEST_ROOT/usr/lib/modules/$TEST_KVER/updates/apple-avd.ko ]] || fail "module result missing"
contains "$XDG_CONFIG_HOME/mpv/mpv.conf" 'gpu-api=opengl'
contains "$XDG_CONFIG_HOME/mpv/mpv.conf" 'volume=75'
same "$(cat "$XDG_CONFIG_HOME/mpv/mpv.conf.before-omarchy-m1-video")" 'volume=75'

# Rerunning is idempotent: existing settings and the original backup are unchanged.
before=$(cksum "$XDG_CONFIG_HOME/mpv/mpv.conf" "$XDG_CONFIG_HOME/mpv/mpv.conf.before-omarchy-m1-video")
run_install "$work/first/rerun.log"
after=$(cksum "$XDG_CONFIG_HOME/mpv/mpv.conf" "$XDG_CONFIG_HOME/mpv/mpv.conf.before-omarchy-m1-video")
same "$after" "$before"

# Header mismatch stops before sudo/package/build work and preserves an installed module.
reset_fixture headers
export TEST_HEADER_VERSION=7.2.asahi1-1
mkdir -p "$TEST_ROOT/usr/lib/modules/$TEST_KVER/updates"
printf 'working module\n' >"$TEST_ROOT/usr/lib/modules/$TEST_KVER/updates/apple-avd.ko"
expect_status 1 run_install "$work/headers/install.log"
contains "$work/headers/install.log" 'update the whole system'
same "$(cat "$TEST_ROOT/usr/lib/modules/$TEST_KVER/updates/apple-avd.ko")" 'working module'
! grep -q '^sudo ' "$TEST_COMMAND_LOG" || fail "header mismatch reached sudo"

# Dependency installation failure is explicit and preserves existing working artifacts.
reset_fixture dependency-fail
export TEST_PACMAN_FAIL=1
mkdir -p "$TEST_ROOT/usr/lib/modules/$TEST_KVER/updates"
printf 'working module\n' >"$TEST_ROOT/usr/lib/modules/$TEST_KVER/updates/apple-avd.ko"
expect_status 1 run_install "$work/dependency-fail/install.log"
same "$(cat "$TEST_ROOT/usr/lib/modules/$TEST_KVER/updates/apple-avd.ko")" 'working module'
contains "$work/dependency-fail/install.log" 'fix the package error and rerun this installer'

# A userspace package build failure leaves prior module/system artifacts untouched.
reset_fixture package-fail
export TEST_MAKEPKG_FAIL=1
mkdir -p "$TEST_ROOT/usr/lib/modules/$TEST_KVER/updates"
printf 'working module\n' >"$TEST_ROOT/usr/lib/modules/$TEST_KVER/updates/apple-avd.ko"
expect_status 1 run_install "$work/package-fail/install.log"
same "$(cat "$TEST_ROOT/usr/lib/modules/$TEST_KVER/updates/apple-avd.ko")" 'working module'
absent "$TEST_ROOT/etc/systemd/system/apple-avd-rebuild.service"

# Failure while installing managed system files leaves the old module and a rerun instruction.
reset_fixture system-files-fail
export TEST_INSTALL_FAIL=1
mkdir -p "$TEST_ROOT/usr/lib/modules/$TEST_KVER/updates"
printf 'working module\n' >"$TEST_ROOT/usr/lib/modules/$TEST_KVER/updates/apple-avd.ko"
expect_status 1 run_install "$work/system-files-fail/install.log"
same "$(cat "$TEST_ROOT/usr/lib/modules/$TEST_KVER/updates/apple-avd.ko")" 'working module'
contains "$work/system-files-fail/install.log" 'fix the error and rerun this installer'

# Service setup failure is also recoverable by rerunning; no module rebuild has occurred.
reset_fixture service-fail
export TEST_SYSTEMCTL_FAIL=1
mkdir -p "$TEST_ROOT/usr/lib/modules/$TEST_KVER/updates"
printf 'working module\n' >"$TEST_ROOT/usr/lib/modules/$TEST_KVER/updates/apple-avd.ko"
expect_status 1 run_install "$work/service-fail/install.log"
same "$(cat "$TEST_ROOT/usr/lib/modules/$TEST_KVER/updates/apple-avd.ko")" 'working module'
contains "$work/service-fail/install.log" 'installed files are retained; fix the error and rerun this installer'

# A rebuild failure keeps the old module and leaves an explicit recoverable rerun state.
reset_fixture rebuild-fail
export TEST_REBUILD_FAIL=1
mkdir -p "$TEST_ROOT/usr/lib/modules/$TEST_KVER/updates"
printf 'working module\n' >"$TEST_ROOT/usr/lib/modules/$TEST_KVER/updates/apple-avd.ko"
expect_status 1 run_install "$work/rebuild-fail/install.log"
same "$(cat "$TEST_ROOT/usr/lib/modules/$TEST_KVER/updates/apple-avd.ko")" 'working module'
contains "$work/rebuild-fail/install.log" 'fix the problem and run ./install.sh --i-accept-boot-risk again'
[[ -f $TEST_ROOT/etc/systemd/system/apple-avd-rebuild.service ]] || fail "recoverable service state missing"

# The actual rebuild helper reports an offline fetch and preserves the working module/stamp.
reset_fixture offline-fetch
export OMARCHY_M1_VIDEO_TEST_MODE=1 TEST_GIT_FAIL=1 TMPDIR="$work/offline-fetch/tmp"
mkdir -p "$TMPDIR" "$TEST_ROOT/usr/local/share/apple-avd-patched/patches" \
	"$TEST_ROOT/usr/lib/modules/$TEST_KVER/build" "$TEST_ROOT/usr/lib/modules/$TEST_KVER/updates"
cp "$repo"/patches/*.patch "$TEST_ROOT/usr/local/share/apple-avd-patched/patches/"
printf 'makefile\n' >"$TEST_ROOT/usr/lib/modules/$TEST_KVER/build/Makefile"
printf 'working module\n' >"$TEST_ROOT/usr/lib/modules/$TEST_KVER/updates/apple-avd.ko"
printf 'old stamp\n' >"$TEST_ROOT/usr/lib/modules/$TEST_KVER/updates/apple-avd.ko.patched-stamp"
expect_status 1 bash "$repo/bin/apple-avd-rebuild" --force >"$work/offline-fetch/rebuild.log" 2>&1
contains "$work/offline-fetch/rebuild.log" 'could not fetch'
same "$(cat "$TEST_ROOT/usr/lib/modules/$TEST_KVER/updates/apple-avd.ko")" 'working module'
same "$(cat "$TEST_ROOT/usr/lib/modules/$TEST_KVER/updates/apple-avd.ko.patched-stamp")" 'old stamp'

# Refuse user-controlled mpv symlinks instead of following them.
reset_fixture symlink
outside="$work/symlink/outside"
printf 'do not touch\n' >"$outside"
ln -s "$outside" "$XDG_CONFIG_HOME/mpv/mpv.conf"
expect_status 1 run_install "$work/symlink/install.log"
same "$(cat "$outside")" 'do not touch'
contains "$work/symlink/install.log" 'refusing to follow a symbolic link'

# Uninstall removes owned artifacts, preserves unrelated files/settings, and is repeatable.
reset_fixture uninstall
printf 'volume=60\n' >"$XDG_CONFIG_HOME/mpv/mpv.conf"
run_install "$work/uninstall/install.log"
printf 'keep\n' >"$TEST_ROOT/etc/pacman.d/hooks/unrelated.hook"
printf 'keep\n' >"$TEST_ROOT/usr/local/share/apple-avd-patched/unrelated"
run_uninstall "$work/uninstall/first.log"
run_uninstall "$work/uninstall/second.log"
absent "$TEST_ROOT/etc/pacman.d/hooks/65-apple-avd-rebuild.hook"
absent "$TEST_ROOT/usr/local/sbin/apple-avd-rebuild"
absent "$TEST_ROOT/usr/lib/modules/$TEST_KVER/updates/apple-avd.ko"
[[ -f $TEST_ROOT/etc/pacman.d/hooks/unrelated.hook ]] || fail "unrelated hook removed"
[[ -f $TEST_ROOT/usr/local/share/apple-avd-patched/unrelated ]] || fail "unrelated share file removed"
contains "$XDG_CONFIG_HOME/mpv/mpv.conf" 'gpu-api=opengl'
contains "$work/uninstall/second.log" 'VA-API driver package is left installed'
contains "$work/uninstall/second.log" 'mpv settings'

# A sysroot without the explicit test-mode gate is rejected before any mutation.
reset_fixture sysroot-gate
unset OMARCHY_M1_VIDEO_TEST_MODE
expect_status 1 run_install "$work/sysroot-gate/install.log"
[[ ! -s $TEST_COMMAND_LOG ]] || fail "ungated sysroot executed external commands"

# A relative sysroot is rejected before any mutation.
reset_fixture relative-root
export OMARCHY_M1_VIDEO_SYSROOT=relative
expect_status 1 run_install "$work/relative-root/install.log"
[[ ! -s $TEST_COMMAND_LOG ]] || fail "invalid sysroot executed external commands"

# The host root can never be used as a test sysroot, even with the gate enabled.
reset_fixture host-root
export OMARCHY_M1_VIDEO_SYSROOT=/
expect_status 1 run_install "$work/host-root/install.log"
[[ ! -s $TEST_COMMAND_LOG ]] || fail "host-root sysroot executed external commands"

# Test mode must never weaken the production rebuild without a disposable root.
for script in install.sh uninstall.sh bin/apple-avd-rebuild; do
    reset_fixture mode-without-root
    unset OMARCHY_M1_VIDEO_SYSROOT
    expect_status 1 bash "$repo/$script" --i-accept-boot-risk >"$work/mode-without-root/invalid.log" 2>&1
    contains "$work/mode-without-root/invalid.log" 'test mode requires a disposable sysroot'
    [[ ! -s $TEST_COMMAND_LOG ]] || fail "invalid test mode executed external commands"
done

# Reject missing markers and symlink aliases before any command shim, in every entrypoint.
for script in install.sh uninstall.sh bin/apple-avd-rebuild; do
    reset_fixture missing-marker
    rm "$TEST_ROOT/.omarchy-m1-video-test-root"
    expect_status 1 bash "$repo/$script" >"$work/missing-marker/invalid.log" 2>&1
    contains "$work/missing-marker/invalid.log" 'test sysroot is missing'
    [[ ! -s $TEST_COMMAND_LOG ]] || fail "missing marker executed external commands"

    reset_fixture aliased-root
    rm -f "$work/aliased-root/link"
    ln -s "$TEST_ROOT" "$work/aliased-root/link"
    export OMARCHY_M1_VIDEO_SYSROOT="$work/aliased-root/link"
    expect_status 1 bash "$repo/$script" >"$work/aliased-root/invalid.log" 2>&1
    contains "$work/aliased-root/invalid.log" 'canonical physical directory'
    [[ ! -s $TEST_COMMAND_LOG ]] || fail "aliased root executed external commands"
done

printf 'PASS: consent, install/rerun, header/dependency/package/system/service/rebuild/offline failures, symlink/sysroot safety, uninstall idempotence\n'
