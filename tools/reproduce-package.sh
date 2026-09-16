#!/usr/bin/env bash
# Build twice without installing anything. The host toolchain is read-only.
set -euo pipefail
if (( $# != 1 )) || [[ -e $1 ]]; then
  echo "Usage: $0 NEW_OUTPUT_DIRECTORY" >&2
  exit 2
fi
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
for command in bwrap makepkg git python3; do
  command -v "$command" >/dev/null || { echo "Missing: $command" >&2; exit 1; }
done
[[ $(uname -m) == aarch64 && $EUID != 0 ]] || {
  echo 'Run as an unprivileged user on aarch64 Arch Linux.' >&2; exit 1;
}
mkdir -p -- "$1"
out=$(cd -- "$1" && pwd -P)
# SOURCE_DATE_EPOCH fixes archive timestamps; the toolchain and recipe are recorded.
epoch=$(git -C "$repo" log -1 --format=%ct)
git clone --mirror https://github.com/iconidentify/libva-v4l2_request.git "$out/source.git"
for run in one two; do
  build="$out/$run"
  mkdir -p "$build/home"
  cp "$repo/libva/PKGBUILD" "$repo/libva/libva-v4l2_request-avd.install" "$build/"
  cp -a "$out/source.git" "$build/libva-v4l2_request"
  cp /etc/makepkg.conf "$build/makepkg.conf"
  cat >> "$build/makepkg.conf" <<'CONFIG'
# Fixed paths/environment shared by the two isolated builds.
BUILDDIR=/build
PKGDEST=/build
SRCDEST=/build
LOGDEST=/build
PACKAGER='omarchy-m1-video reproducibility check'
PKGEXT='.pkg.tar.xz'
OPTIONS=(strip docs !libtool !staticlibs emptydirs zipman purge !debug !lto)
CONFIG
  bwrap --ro-bind /usr /usr --symlink usr/bin /bin --symlink usr/lib /lib \
    --symlink usr/lib /lib64 --ro-bind /etc /etc --ro-bind /var/lib/pacman /var/lib/pacman \
    --dev /dev --proc /proc --tmpfs /tmp \
    --bind "$build" /build --chdir /build --unshare-net \
    --clearenv --setenv PATH /usr/bin --setenv HOME /build/home \
    --setenv LANG C.UTF-8 --setenv LC_ALL C.UTF-8 --setenv TZ UTC \
    --setenv SOURCE_DATE_EPOCH "$epoch" \
    /usr/bin/makepkg --holdver --config /build/makepkg.conf --noconfirm \
    > "$out/$run.log" 2>&1
  packages=("$build"/*.pkg.tar.xz)
  [[ ${#packages[@]} == 1 && -f ${packages[0]} ]]
  python3 "$repo/tools/package-provenance.py" --repo "$repo" \
    --package "${packages[0]}" --output "$out/$run.json" \
    --build-config "$build/makepkg.conf" \
    --hardware-evidence "$repo/docs/codec-validation-r11-2026-09-15.json"
done
python3 - "$out" "$epoch" <<'PY'
import hashlib, json, pathlib, sys, tarfile
root = pathlib.Path(sys.argv[1])
def identity(run):
    package, = (root / run).glob('*.pkg.tar.xz')
    with tarfile.open(package) as archive:
        driver = archive.extractfile('usr/lib/dri/v4l2_request_drv_video.so').read()
    with package.open('rb') as stream:
        package_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'package_sha256': package_hash,
            'stripped_driver_sha256': hashlib.sha256(driver).hexdigest()}
one, two = identity('one'), identity('two')
result = {'schema_version': 1, 'source_date_epoch': int(sys.argv[2]),
          'environment': 'same read-only host toolchain; separate writable /build trees; network disabled',
          'one': one, 'two': two,
          'package_bytes_identical': one['package_sha256'] == two['package_sha256'],
          'stripped_driver_bytes_identical': one['stripped_driver_sha256'] == two['stripped_driver_sha256']}
(root / 'comparison.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
if not result['package_bytes_identical']:
    print('Packages differ: compare .PKGINFO/.BUILDINFO/.MTREE and member bytes; do not claim reproducibility.', file=sys.stderr)
    sys.exit(1)
PY
