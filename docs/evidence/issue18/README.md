# Issue 18: M2 inventory and qualification gates

This is a partial, no-install contribution to [issue 18](https://github.com/iconidentify/omarchy-m1-video/issues/18).
The [M2 inventory](m2-inventory.json) was collected with the committed tool at
`819d9e132fde09ba2ffe2076dded3f92f6da2fce`. The JSON includes its script hash.
No serial number, hostname, machine ID, media, user process arguments or journal
contents were collected. The device label is a public pseudonym.

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
| Two independent qualified Apple devices | **Not met**: [historical M1 r11 record](../../codec-validation-r11-2026-09-15.json) and M2 inventory exist, but the M2 has no hardware qualification |
| Per-device codec/profile and software identity | Inventory explicitly records all codecs, including AV1, as not probed; actual capability and codec tests remain blocked |
| Reset/corruption remains experimental; no automatic install/load | Both matrix rows remain experimental; no install, module load/unload, reboot, suspend or decoder access performed |
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

No hardware lease or decoder process was acquired. Next action is a separately approved
manual setup/test plan that respects the existing blacklist, followed by guarded device
qualification. Missing hardware evidence is not replaced by CI or the M1 pass sets.
