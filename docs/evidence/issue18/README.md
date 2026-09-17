# Issue 18: device inventories and qualification gates

This is a partial, no-install contribution to [issue 18](https://github.com/iconidentify/omarchy-m1-video/issues/18).
The original [M2 j413 inventory](m2-inventory.json) was collected with the committed tool at
`819d9e132fde09ba2ffe2076dded3f92f6da2fce`. The later [M2 Max j416c inventory](m2-j416c-inventory.json)
was collected with the merged collector at `9cbaa55718e54f6833f1f38f265c293c33daf9e6`.
Each JSON includes its script hash. No serial number, hostname, machine ID, media,
user process arguments or journal contents were collected. Device labels are public
pseudonyms. Neither inventory is hardware qualification.

## M2 j413 inventory, 2026-09-17

```sh
python3 tools/qualify-device.py --device-id contributor-m2-j413 --output docs/evidence/issue18/m2-inventory.json
```

Observed exit: **2**, with `apple_avd_not_loaded` and `no_apple_avd_video_node`.
`video0` belongs to `apple_isp`. Installed VA driver: `1.3.r5-1`.
The selected on-disk AVD module hash is only a next-load identity.
Read-only supplemental inspection found the T8112 AVD device-tree compatible and
matching `modinfo` alias/vermagic; this is not runtime validation. An existing
`blacklist apple_avd` in `/etc/modprobe.d/apple-avd-manual-test.conf` reserves module
loading for manual trial. It was preserved.

## Acceptance status

| Issue criterion | Evidence / remaining work |
| --- | --- |
| Portable no-install collection and refusal of unsupported claims | Tool, 11 offline/CLI tests, this blocked M2 record; no hardware claim is emitted |
| Two independent qualified Apple devices | **Not met**: [historical M1 r11 record](../../codec-validation-r11-2026-09-15.json) plus j413 and j416c inventories exist; neither additional machine has hardware qualification |
| Per-device codec/profile and software identity | Inventory explicitly records all codecs, including AV1, as not probed; actual capability and codec tests remain blocked |
| Reset/corruption remains experimental; no automatic install/load | All matrix rows remain experimental; no install, module load/unload, reboot, suspend or decoder access performed |
| Scoped evidence and tests not run | This record and [workflow](../../DEVICE_QUALIFICATION.md); hardware smoke, conformance, export, lifecycle, client and boot tests all not run |
| Merged changes and completion protocol | Pending review/merge; use Refs, keep issue open |

## Verification

- Eleven qualification tests pass, including camera/decoder separation, failed prerequisites,
  wrong platform, privacy allowlist, unknown loaded-module identity, actual CLI execution,
  and preservation of existing output. The initial regression run failed because the new
  collector did not yet exist.
- Existing 12 H.264 scanner, 22 VP9 scanner and 19 package-provenance tests pass.
- Bash syntax, rebuild and installer regression suites pass; `git diff --check` passes.
- Three simplification reviewers checked reuse, quality and efficiency. Applied two quality
  changes (explicit required-package list and explicit fixture argument); no reuse changes.
  Two efficiency suggestions deferred: batching pacman changes partial-failure semantics,
  and reserving output early changes failure side effects. Inventory completed in under a
  second on this host; neither change is needed for this bounded collector.

The [review receipt](review.json) records a focused correctness review and an
independent Claude Opus 5 review. Both actionable findings were applied: missing
selected-module identity now blocks inventory completeness (two new regressions
failed before the fix), and tool clones explicitly start in the parent directory.
The original inventory remains pinned to its original collector commit; it already
contains the selected module hash, so this correction does not change its blockers.
A standalone copy of the collector also returned the same M2 blockers outside Git.

A failed/interrupted output write can leave a partial file; the command fails.
Use a new output filename on retry and do not treat partial JSON as evidence.
Historical M1 corpus pinning and all missing M2 hardware evidence remain limitations.

## Maintainer review correction, 2026-09-17

An independent maintainer review reproduced two collector-provenance failures:
an untracked standalone copy inside another Git repository inherited that
repository's commit, and a modified tracked collector retained its old commit.
The collector now records a commit only when the committed blob matches its
actual bytes. Both regressions failed before the fix; all 13 qualification tests
pass afterward. The script SHA-256 remains available when the commit is unknown.
The maintainer correction was self-reviewed; the original contribution received
the independent review. The historical M2 inventory and its original collector
hash are preserved, and all six runbook tool hashes were checked at their pinned
driver revision. No hardware evidence was added by this review.

No hardware lease or decoder process was acquired. Next action is a separately approved
manual setup/test plan that respects the existing blacklist, followed by guarded device
qualification. Missing hardware evidence is not replaced by CI or the M1 pass sets.

## M2 Max j416c inventory, 2026-09-17

A second no-install inventory was collected on a different AVD generation:

```sh
python3 tools/qualify-device.py --device-id contributor-m2-j416c --output docs/evidence/issue18/m2-j416c-inventory.json
```

Observed exit: **2**, with `missing_package:linux-asahi-headers` and `missing_tool:vainfo`.
`apple_avd` is loaded. `video0` is `avd` / `apple_avd`; `video1` is `apple-isp` / `apple_isp`.
Installed VA driver: `1.3-1` (SHA-256
`614fcf7f273e3f81ca101c233374a1b3e395f85a328aefb010477db4fb50b6b9`).
Selected on-disk module:
`/lib/modules/7.1.13-3-1-ARCH/kernel/drivers/media/platform/apple/avd/apple-avd.ko`
(SHA-256 `4864d0dd4f733522da4ec13bba40ae90b3b0441add3a189136bc1a0866dbf6e5`).
That hash is a next-load identity only; `loaded_binary_sha256` remains null.
Collector commit `9cbaa55718e54f6833f1f38f265c293c33daf9e6`, script SHA-256
`8f4ed1f665e60bff50a926631bb93eae4d9fe5a87ff62fa9c89660a267cd0eda`.
No packages were installed to clear the recorded blockers. H.264, HEVC, VP9 and AV1
remain `not_probed`. A loaded in-tree decoder node does not transfer the M1 r11
pass sets onto `t6021`.

Verification for this inventory: 15 qualification tests, 12 H.264 scanner tests,
22 VP9 scanner tests, 19 package-provenance tests, bash syntax, rebuild and
installer suites, and `git diff --check`. At inventory time, hardware smoke,
conformance, export, lifecycle, client and boot tests were not run.

## t6021 in-tree userspace smoke, 2026-09-17

A later bounded campaign on this same host decoded three known-pass vectors
through an isolated `27da69dd5fcb438deab970061a2edcc68a9e1d93` library against
the already-loaded in-tree module. See
[t6021-in-tree-smoke](t6021-in-tree-smoke/README.md). The same three vectors then
passed on a hand-loaded 15-patch module that was never installed into `updates/`;
the in-tree module was restored afterward. See
[t6021-patched-smoke](t6021-patched-smoke/README.md). Full suites, export,
lifecycle, client and boot tests remain not run. The device stays experimental.
