# Qualifying an Apple Silicon device

[Issue #18](https://github.com/iconidentify/omarchy-m1-video/issues/18) requires
independent device evidence. This workflow supplies inventory and preparation; it
has **not qualified an M2 or M2 Max** or completed the issue. Read [AGENTS.md](../AGENTS.md),
[the recovery notes](../README.md#if-the-mac-freezes-or-resets) and the
[claim/lease workflow](AGENT_WORKFLOW.md) first. Installation, module operations,
reboot and suspend are separate activities with their own authorization gates.

## Current evidence, 2026-09-17

| Device | Exact evidence scope | Qualification |
| --- | --- | --- |
| M1 / T8103, MacBookPro17,1 | Historical r11 userspace tests on `linux-asahi 7.1.13.asahi3-1`; [record](codec-validation-r11-2026-09-15.json) | Experimental; HEVC 144/147, AVC 73/135, opt-in High 10 FRExt 27/69, VP9 216/305; boot/display/codec gaps remain |
| M2 / `apple,j413`, `apple,t8112` | Inventory only; kernel `7.1.13-3-1-ARCH`, package `linux-asahi 7.1.13.asahi3-1`, installed VA driver `1.3.r5-1` | Experimental; capabilities unknown, no decode attempted; `apple_avd` absent from loaded-module sysfs, `video0` is `apple-isp` / `apple_isp` |
| M2 Max / `apple,j416c`, `apple,t6021` | Inventory only; kernel `7.1.13-3-1-ARCH`, package `linux-asahi 7.1.13.asahi3-1`, installed VA driver `1.3-1`; [record](evidence/issue18/m2-j416c-inventory.json) | Experimental; capabilities unknown, no decode attempted; `apple_avd` is loaded and `video0` is `avd` / `apple_avd`, but inventory is blocked on missing `linux-asahi-headers` and `vainfo`; selected module is the in-tree kernel file, not an `updates/` rebuild; loaded-binary identity remains unknown |
| Other Apple Silicon devices | No record in this workflow | Untested; do not inherit these rows |

The M1 record used an isolated r11 library while its installed package was r5.
Its driver source is `db3014f9499694c6f186af7e023de07bd5bc3564`, with stripped-library
SHA-256 `a9d6225e0fd348ca22fd738cb2367d7835d7cda1f789ba7b5aae278b32b6729b`.
It does not certify a new build, newer driver HEAD, or another machine. Its Fluster
checkout was unpinned; retain that historical limitation when comparing new runs.
The M2 j413 on-disk module selected for a future load does not establish a loaded
binary identity. A camera device named `video0` is not an AVD decoder.
This M2 also has an existing `blacklist apple_avd` directive in
`/etc/modprobe.d/apple-avd-manual-test.conf`, whose comment reserves loading for a
manual trial. Preserve that configuration; issue selection does not approve
overriding the existing trial boundary.
The M2 Max j416c inventory found a loaded in-tree `apple_avd` on `video0` and the
FaceTime camera on `video1`. That is not a hardware lease, a capability query, or
qualification: codecs remain `not_probed`, the selected file is
`/lib/modules/7.1.13-3-1-ARCH/kernel/drivers/media/platform/apple/avd/apple-avd.ko`,
the loaded-binary hash is unknown, and the installed userspace driver is stock
`1.3-1`, not an isolated r11+ candidate. Missing `linux-asahi-headers` and `vainfo`
are inventory blockers, not permission to install those packages.

## Inventory without opening a decoder

From this repository, use a new filename and a pseudonymous device label:

```sh
python3 tools/qualify-device.py --device-id contributor-m2 --output NEW.json
```

This collects allowlisted machine/package/tool/sysfs identities and file hashes.
It does not install, load modules, run `vainfo`, query decoder capabilities, or
play video. A report is always experimental inventory: capabilities are unknown,
missing prerequisites remain explicit, and loaded-module binary identity remains
unknown. Review the JSON before publishing; use neither a serial number nor a
personal name for the device label. Keep inventories from separate machines separate.
A successful inventory command is not a successful hardware preflight.
The collector records its script SHA-256. Its Git commit is recorded only when
that commit contains the exact script bytes; standalone/untracked copies and
locally modified scripts report a null commit instead of borrowing another
checkout's identity. The script hash remains available in those cases.
Python 3.11 or newer is required. Exit 0 means the inventory prerequisites were
found; exit 2 writes the inventory with explicit blockers; exit 1 means the record
could not be written. None of these states certifies hardware. AV1 and all other
codec capabilities stay `not_probed` until a guarded query supplies evidence;
absence cannot be inferred just from a model name or installed package.

## Pin and prepare the tools without hardware

Continue from this repository's root after inventory. Use fresh directories beside
this checkout; the following paths are ordinary relative workspace paths.
Tools are pinned independently from the installed r5
package and the historical r11 candidate. Record the candidate source, build options,
actual library hash and dependencies separately before testing it.

```sh
cd ..
git clone https://github.com/iconidentify/libva-v4l2_request qualification-driver
git -C qualification-driver checkout --detach b775d9b2d657f04daba3e3bd19dd570130dc7e7d
git clone https://github.com/fluendo/fluster qualification-fluster
git -C qualification-fluster checkout --detach f3ad284a9e6cac70dc01b02e0de71c2994181d34
cd qualification-driver
```

SHA-256 pins at that driver revision (the commit also pins helper dependencies):

| File | SHA-256 |
| --- | --- |
| `tests/corpus/manifest.json` | `8dd958cd4d1c05ba225253773b80e7a3cd37853c9207a49177793717b074883e` |
| `tests/corpus.py` | `0f8112c0daed216cf720a4c744f6eb0b4ef963946f5358cda9729093b9b6c12e` |
| `tests/conformance.py` | `67cfcb738b1977c01a49a8c02921c2cea4c816b5dcd648320aa71ace48ad7e74` |
| `tests/compare-results.py` | `c481824861764edb78b89d09235e277ec47b7740e2ba02c0860af3ab670dfe52` |
| `tests/hwguard.py` | `45d65351b33b13dbdd2145b3d37a83bf48c27cc08f1df08c5f37b196d7643d60` |
| `docs/r11-pass-sets.json` | `66bc47b2511dfdd8d5d270be028124c343fa00ded6523035598a785b95ad5583` |

Check these with `sha256sum` before using them; stop on any difference. Then:

```sh
python3 tests/corpus.py validate --fluster ../qualification-fluster
python3 tests/hwguard.py --self-test
python3 tests/compare-results.py --self-test
python3 tests/corpus.py fetch --fluster ../qualification-fluster --cache ../qualification-cache --smoke
python3 tests/corpus.py verify --fluster ../qualification-fluster --cache ../qualification-cache --require smoke
```

The fetch downloads public inputs; it does not decode. The manifest pins suite
hashes, smoke input hashes and expected failures. Official media usage terms are
not established; publish hashes and results, not the downloaded media. Full suites
need separate acquisition and `verify --require all`; inspect `fetch --all --dry-run`
first, then explicitly select `--all --confirm-large-corpus` for the large download.
Retain `qualification-cache/corpus-lock.json` with the result identities.
Missing tools, inputs or failed integrity checks block the affected stage.

## Hardware stage: blocked on the inventoried devices

Do not run the commands below on either inventoried M-series host as part of
inventory. The j413 M2 has no identified, loaded AVD decoder. The j416c M2 Max
has a loaded in-tree `apple_avd` node, which still does not authorize a decode
campaign, module reload, or package install. Do not load a module or change the
kernel to remove these gates as part of inventory. First obtain a separately
approved preparation plan and a scheduled idle hardware window; identify the real
decoder, selected userspace library, kernel/UAPI and any remaining uncertainty
about the running module.
Close video clients with the owner's agreement. An issue claim is not a hardware
lease: every command must acquire `hwguard.py`'s exclusive host lock and pass its
idle/fault preflight. Never fabricate its lease variable or use fake mode.

For a device that has passed those gates, build an unsanitized candidate in
`build-qualification` (Meson/Ninja and development headers must already be present).
Prepare it with `meson setup build-qualification` and `meson compile -C build-qualification`.
Use a new results directory per attempt. These are individual run templates,
not an automatic campaign. Review the guard result after each before continuing:

```sh
python3 tests/hwguard.py --deadline 180 --log ../smoke-guard.jsonl -- \
  python3 tests/conformance.py ../qualification-fluster/test_suites/h.265/JCT-VC-HEVC_V1.json \
  ../qualification-cache --driver "$PWD/build-qualification/src" \
  --vectors AMP_A_Samsung_7 --output ../hevc-smoke-new
python3 tests/hwguard.py --deadline 600 --log ../hevc-guard.jsonl -- \
  python3 tests/conformance.py ../qualification-fluster/test_suites/h.265/JCT-VC-HEVC_V1.json \
  ../qualification-cache --driver "$PWD/build-qualification/src" --output ../hevc-full-new
python3 tests/compare-results.py --baseline docs/r11-pass-sets.json \
  --candidate ../hevc-full-new/summary.json --suite hevc
python3 tests/hwguard.py --deadline 240 --log ../export-guard.jsonl -- \
  sh tests/early-export.sh "$PWD/build-qualification/src"
python3 tests/hwguard.py --deadline 240 --log ../lifecycle-guard.jsonl -- \
  sh tests/shared-contexts.sh "$PWD/build-qualification/src"
```

Use the same guarded runner for each applicable full suite; compare exact pass
sets with `--suite avc`, `frext`, or `vp9` as appropriate:

| Suite path below Fluster `test_suites/` | Required treatment |
| --- | --- |
| `h.264/JVT-AVC_V1.json` | 135-vector denominator; profile-override subset reported separately |
| `h.264/JVT-FR-EXT.json` | 69-vector denominator; comparator baseline uses explicit `LIBVA_V4L2_H264_HIGH10=ffmpeg` mode |
| `vp9/VP9-TEST-VECTORS.json` | 305-vector denominator; known resize/dimension failures remain visible |
| `vp9/VP9-TEST-VECTORS-HIGH.json` | Six-vector suite; 10-bit 4:2:0 subset is one vector, never six supported vectors |

Include guarded `hwdownload.sh`, `h264-high10.sh` and `vp9-matrix.sh` for applicable
8/10-bit and normal/early-export paths. Their prerequisites and invocations are in
the pinned driver's `tests/README.md`. Record absent codecs as unsupported or
untested with the observed reason, never silently omit them. Do not knowingly
replay firmware-fault vectors on an older candidate lacking the relevant guards.
A timeout, new kernel/decoder fault, foreign client, stuck task or failed final
idle check stops the campaign. Preserve the partial run; no automatic retry,
module reload, reboot or recovery is permitted. A nonzero suite result may include
known rejections; it must be explained, not converted into a blanket pass.

## Evidence required before changing a support claim

Attach the device inventory, exact tool/corpus/candidate identities, build and UAPI
records, guard logs, redacted kernel window, raw suite summaries/denominators,
exact comparator output and export/lifecycle results. A strict VA hardware-frame
check must exclude software fallback. Review client playback separately: mpv keeps
`gpu-api=opengl`; record browser/version/sandbox and visible output evidence when
tested. Pixel equality does not establish display, suspend or boot reliability.

Issue #18 remains open until at least two independent device records have the
applicable smoke, full conformance, export, lifecycle and client evidence reviewed
and merged. This tooling work uses `Refs #18`, not a closing keyword. Unresolved
reset or corruption findings keep the affected device experimental and link to
follow-up issues; missing hardware evidence is a blocker, not an implied pass.
