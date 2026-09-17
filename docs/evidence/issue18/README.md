# Issue 18: device inventories and qualification gates

This directory contains historical read-only inventories and separately reported
hardware smoke campaigns for [issue 18](https://github.com/iconidentify/omarchy-m1-video/issues/18).
The M2 Max smoke contribution includes reported package/module operations; the
no-install description applies only to its inventory and first smoke phase.
See the [maintainer review and provenance limits](t6021-review.md) for the accepted scope.
The original [M2 j413 inventory](m2-inventory.json) was collected with the committed tool at
`819d9e132fde09ba2ffe2076dded3f92f6da2fce`. The later [M2 Max j416c inventory](m2-j416c-inventory.json)
was collected with the merged collector at `9cbaa55718e54f6833f1f38f265c293c33daf9e6`.
Each inventory JSON includes its script hash. No serial number, hostname, machine ID, media,
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

## Current acceptance status

| Issue criterion | Evidence / remaining work |
| --- | --- |
| Portable no-install collection and refusal of unsupported claims | Collector and 15 offline/CLI tests; both historical inventories remain unqualified |
| Two independent qualified Apple devices | **Not met**: [historical M1 r11 record](../../codec-validation-r11-2026-09-15.json) plus j413 and j416c inventories exist; neither additional machine has hardware qualification |
| Per-device codec/profile and software identity | Inventories retain `not_probed`; separate M2 Max reports cover three smoke vectors only. Exact loaded-module/patch attribution is unverified; full qualification remains open |
| Reset/corruption remains experimental; no automatic install/load | Collector performs no system changes. Later contributor-reported manual package/module operations are recorded separately; all device rows remain experimental |
| Scoped evidence and tests not run | Inventories, limited smoke reports and [review assessment](t6021-review.md); full conformance, export, lifecycle, client and boot qualification are not supplied by this contribution |
| Merged changes and completion protocol | This is a partial contribution; issue #18 stays open until its remaining qualification evidence is reviewed and merged |

## Historical j413 tooling verification

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

## Historical j413 maintainer correction, 2026-09-17

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
No packages were installed during this inventory phase. Its H.264, HEVC, VP9 and
AV1 capability fields remain `not_probed`; the immutable snapshot is not a claim
about later campaigns. Campaign 2 reports later package installation and module
operations. A loaded decoder node does not transfer the M1 r11 pass sets to `t6021`.

Verification for this inventory: 15 qualification tests, 12 H.264 scanner tests,
22 VP9 scanner tests, 19 package-provenance tests, bash syntax, rebuild and
installer suites, and `git diff --check`. At inventory time, hardware smoke,
conformance, export, lifecycle, client and boot tests were not run.

## t6021 reported smoke campaigns, 2026-09-17

The contributor supplied two three-vector summaries through an isolated
`27da69dd5fcb438deab970061a2edcc68a9e1d93` library. Campaign 1 reports testing the
already-loaded module with an in-tree file selected; campaign 2 reports a manual
15-patch module trial followed by restoration. Their 238 frame hashes agree with
independent reference output, and the published guards report healthy idle exits.

See [campaign 1](t6021-in-tree-smoke/README.md),
[campaign 2](t6021-patched-smoke/README.md), and the
[review assessment](t6021-review.md). Original summaries, provenance JSON and guards
are preserved byte-for-byte. Exact kernel/patch attribution and parts of the
execution/authorization history remain unverified; this contribution accepts
reported output, not a reproducible qualification of either kernel stack.
Full suites, export, lifecycle, client and boot evidence are outside these records.
Later work under the contributor's separate boot-qualification claim is not
accepted by this merge. The device remains experimental and issue #18 stays open.
