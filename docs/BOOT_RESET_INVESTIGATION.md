# Investigating boot resets

[Issue #13](https://github.com/iconidentify/omarchy-m1-video/issues/13) remains open:
the cause of the historical resets is unknown. This procedure gathers existing evidence
and proposes a boot comparison; it does not qualify boot-enabled installation.

## Collect existing evidence

From the repository root, with Python 3.11 or newer:

```sh
python3 tools/collect-boot-evidence.py --device-id m2-j413-lab --output boot-evidence.json
```

Choose a public pseudonym, not a serial number. The output file must not already exist.
The collector reads retained kernel journals, current module metadata and pstore directory
availability. It does not open the decoder or change configuration. It does not invoke sudo.

The JSON contains fixed event categories, counts and timestamps. It omits journal messages,
boot IDs, hostnames, process arguments, stderr text and pstore contents. Review timestamps
and the device pseudonym before publishing: those can still identify a test session.
Keep original logs private; the summary is a triage aid, not a substitute for a redacted
crash trace when one is available.

Exit 0 means collection completed within its limits; exit 2 means evidence has gaps;
exit 1 means no usable record was written. None means a healthy boot or a safe installation.
Each journal query has time, byte and entry limits. A full recent-boot window is also a
bounded selection, not the complete machine history. A reached limit, access warning,
missing journal or malformed record must remain visible when interpreting zero matches.

Journal first/last timestamps are the bounds of retained messages, not verified boot or
shutdown times. A short journal does not distinguish reset, manual power-off and missing
logs. Event counts count matching records, not independent failures. An AVD platform or
blacklist mention does not prove that the decoder module loaded. ARM performance-counter
PMU initialization is not a power-management reset report.

The selected module file/hash describes a possible future load. Neither it nor today's
installed packages identify a previous boot's loaded binary. Preserve original build,
installation and load records before attributing a patchset to an attempt.

The collector distinguishes live `/sys/fs/pstore` and archived `/var/lib/systemd/pstore`.
The systemd pstore service can archive and clear live records; an empty directory alone
cannot establish that no crash occurred. An inaccessible directory is unknown, not empty.
See the [systemd journal documentation](https://github.com/systemd/systemd/blob/v261/man/journalctl.xml)
and [pstore service documentation](https://github.com/systemd/systemd/blob/v261/man/systemd-pstore.service.xml).
No journal retention or pstore setting is changed by this procedure.

## Evidence so far

The [M2 read-only assessment](evidence/issue13/README.md) separates current observations
from the M1 history in [gap status](GAP_STATUS.md#h1--unexplained-resets-shortly-after-boot-high-priority).
It records earlier firmware and decode failures on the M2, but establishes no link between
those failures and the historical M1 resets. Zero new boots were attempted for this assessment.

## Proposed comparison — not approved or run

The first campaign should use the affected M1 if available. An M2 campaign would produce
additional-device evidence, not reproduce the original M1 result. Keep device results separate.

Proposed initial scope: two attempts in each cell below, with a ten-minute observation
window after login. This is an eight-attempt screening campaign, not a reliability claim.
Approve individual attempts and configurations before execution; stop the campaign at the
first new reset, freeze, panic, AVD fault or unexpected recovery requirement.

| Cell | Boot transition | Decoder configuration | Planned attempts | Executed |
| --- | --- | --- | --- | --- |
| C1 | Graceful shutdown, 30 seconds powered off, power on | Verified blacklisted control; decoder absent | 2 | 0 — not run |
| C2 | Graceful warm reboot | Same verified blacklisted control | 2 | 0 — not run |
| P1 | Same cold transition as C1 | Exact proposed patched build loading at boot, pending approval | 2 | 0 — not run |
| P2 | Same warm transition as C2 | Same proposed patched build, pending approval | 2 | 0 — not run |

These operational definitions of cold/warm do not prove any particular firmware or power-rail
reset state. Record the actual transition and any departure from the definition.

Before approving an attempt, fill in a single device's fixed conditions: kernel release,
module source/tag/patch manifest/build and file hashes, userspace package versions, AC or
battery state and charge range, lid/display state, attached peripherals, login procedure,
and applications started. Hold these conditions constant across the comparison. Record
unexpected application or playback activity as a confounder. Do not run decode stress,
suspend or other agents' decoder workloads during this boot-only comparison.

Run one control attempt of each transition first; review their evidence before proposing
a patched attempt. Start no patched cell without a concrete, reviewed build/load plan
and the repository's installation consent. Preserve the existing blacklist until the
specific configuration change has been approved. A control is valid only when the intended
blacklisting policy is recorded and the decoder is confirmed absent; do not assume a
modprobe blacklist alone prevents every explicit load path.

### Per-attempt record

Use one record for every attempted transition, including failures and aborted attempts.
A skipped or unapproved cell is `not_run`, never a pass.

- Attempt ID, device pseudonym, cell, planned order and actual order.
- Explicit approval reference for this operation; saved-work confirmation; operator;
  reviewed recovery path; consent for configuration or installation changes if needed.
- Pre-transition and post-login UTC timestamps, available monotonic timestamps, private
  boot-ID mapping, and any uncertainty in the wall clock.
- Fixed conditions above and deviations, selected module hash before the transition,
  load evidence afterward, and unresolved loaded-binary or patchset identity.
- Whether shutdown/reboot was requested, login was reached, the ten-minute window completed,
  or reset/freeze/recovery occurred; mark interrupted observations with duration.
- Pre/post collection files and hashes; corresponding previous-boot journal availability;
  pstore access/archive state; retained redacted crash/PMU evidence where available.
- All commands/actions actually performed, first new fault timestamp, stopping decision
  and final module/configuration state. Record any recovery separately from test outcomes.

After a failed boot, preserve its evidence before additional attempts can change the
previous-boot selection. Match journals by the private boot-ID record rather than assuming
`-1` always refers to the intended attempt. Do not clear pstore or rotate journals.

### Recovery and consent boundary

Review [If the Mac freezes or resets](../README.md#if-the-mac-freezes-or-resets) before
any attempt. The documented rescue path is a one-time boot with
`module_blacklist=apple_avd`, followed by persistent blacklisting after login when needed.
Confirm the actual boot loader provides a usable rescue path before authorizing the trial;
do not discover that during a failure. A freeze may require manual power cycling and can
lose unsaved work.

[AGENTS.md](../AGENTS.md) requires informed installation consent and saved work before
module unload or reboot. Installation adds an out-of-tree module loaded at boot, hooks,
a boot service, a replacement VA-API package and mpv settings. The test Mac previously
hard-reset twice shortly after boot with these patches; the cause remains unknown.
No command in the collector bypasses these gates. No automatic module reload, reboot,
installation or recovery loop belongs in this campaign. Shipped patches remain unchanged.

### How outcomes guide the next step

- Failure only in a patched cell: preserve both cells' exact identities and the earliest
  fault. This strengthens an AVD/load-path hypothesis; it still needs a discriminating
  trace or controlled, separately approved comparison before a causal claim.
- Failure also in a verified control: investigate the first fault and power/peripheral or
  other kernel evidence. That weakens a patched-module-only explanation for that campaign;
  it does not establish that the module is harmless in every configuration.
- No failure: report the completed count and observation duration per cell. Do not call
  the boot path reliable or close the original report on this sample.
- Missing logs, failed provenance checks or changed conditions: mark the comparison
  inconclusive. Improve capture/provenance before proposing a further approved attempt.

A confirmed cause and before/after reproducer are inputs to
[issue #17](https://github.com/iconidentify/omarchy-m1-video/issues/17). It remains blocked
until that evidence exists; decode conformance or CI passing cannot substitute for it.
