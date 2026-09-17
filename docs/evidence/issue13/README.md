# Issue 13: M2 read-only evidence

The boot-reset cause remains unknown. This record is a read-only investigation on an
M2 MacBook Air J413/T8112, not a reproduction of the two M1 resets in the repository history.
No boot, module operation, installation, decoder workload or system configuration change
was performed. No hardware lease was acquired.

## Sources and identity

Repository base: `f50a4a4c88b03ea1e10acf734a53c3a0ee9b2519`.
The collector and its reused inventory helper are identified by hashes in
[m2-boot-evidence.json](m2-boot-evidence.json).
Current host: `7.1.13-3-1-ARCH`, `linux-asahi 7.1.13.asahi3-1`, Python 3.14.7,
systemd 261.3-1-arch, installed `libva-v4l2_request-avd 1.3.r5-1`.
These current versions do not identify previous boots' installed or loaded software.

At collection, `apple_avd` was absent from sysfs and the existing manual-trial blacklist
remained in place. `/dev/video0` was the `apple-isp` camera, not the decoder.
The file selected for a future module load was
`/lib/modules/7.1.13-3-1-ARCH/updates/apple-avd.ko`, SHA256
`6ae27cea2faa4b394ac38cb4516cbe6e16dc579864da5f84f6401aefdbb2ffc1`.
No loaded or historical module hash is established by that file.

## Observed evidence

Six retained boot journals were inspected. The journal timestamps are retained-message
bounds, not measured boot durations. Original messages and boot identifiers remain private.

| Retained boot slot at collection | Observation | What it establishes |
| --- | --- | --- |
| -5, -4, -3 | Each contains a failed direct load of `apple/avd-fw-v3-t1.bin` with error -2 | Firmware availability failed at those probes; no reset cause established |
| -4 | Retained messages span roughly 11.3 seconds on 2026-09-12 | A short retained journal, not proof of a crash or total uptime |
| -2 | Ten allocation-failure records and 30 AVD stack-frame records (ten contain `avd_init_job`) | A historical decoder allocation failure path worth preserving |
| -2 | Eight `slice_num > 4096` rejection records | Historical H.264 decode rejection, not eight independent crashes |
| -1, 0 | AVD platform/IOMMU and power-controller references | Those references alone do not prove a loaded decoder |
| Current pstore | Live directory inaccessible; archive readable and empty | Live crash-record contents unknown |

The first inspected allocation trace on boot -2 reports kernel `7.1.13-2-1-ARCH` and
passes through `warn_alloc`, the large `kmalloc` path, `avd_init_job`, `avd_h264_run`
and `avd_device_run`. Allocation records range from 2026-09-12 22:05:59.828833 UTC to
2026-09-15 02:21:49.259680 UTC; slice-limit records range from 2026-09-12 22:11:48.781426 UTC
to 2026-09-15 02:21:55.777980 UTC. This is consistent with the symptom classes described
by existing patches 0003 and 0004. It does not prove the historical patchset or establish
that those failures reset the machine. No patch was edited or tested here.

A separate `atcphy_mux_set` warning appears in that boot's kernel journal at monotonic
42299192311 microseconds. It is a different subsystem lead, not an AVD causal trace.
Broad searches for PMU or warning text also match ordinary initialization and unrelated
messages; only the collector's documented categories are counted in the JSON.

No panic/oops or power-PMU reset-reason pattern was identified in the inspected records.
Incomplete retention, permission limits and pattern coverage prevent interpreting that as
proof no panic or reset occurred. The collector records its precise coverage and gaps.

## Historical report and competing explanations

The [M1 gap record](../../GAP_STATUS.md#h1--unexplained-resets-shortly-after-boot-high-priority)
says two boots on 2026-09-14 reset with patches 0001-0005 loaded; the journals ended without
a saved AVD panic/oops. It reports one boot error and zero panics in the second boot's PMU
report, empty pstore on 2026-09-15, and one later successful boot with all 15 patches.
Those are repository reports from a different device. Their original raw journals and
exact loaded binaries were not available on this M2 for independent verification.

An AVD boot-load interaction remains a candidate because of the reported timing, but there
is no demonstrated trigger-to-reset chain. A power/peripheral or other kernel cause is
also possible; the M2's separate PHY warning does not explain the M1 history. Missing
journal tails can conceal a cause under either explanation. The evidence does not support
ranking these candidates or writing a kernel fix.

Use the [proposed comparison and recovery procedure](../../BOOT_RESET_INVESTIGATION.md)
for the next discriminating experiment. It requires a reviewed build/configuration and
explicit approval per operation. A repeat on this M2 would remain additional-device
research. The separate M2 Max campaign under issue 18 is not evidence collected by this run.

## Acceptance and remaining work

| Issue criterion | Contribution | Remaining work |
| --- | --- | --- |
| Separate evidence, gaps and explanations | Current summaries and this assessment | Recover/review original M1 artifacts if available |
| Approved cold/warm matrix | Proposed four-cell matrix and per-attempt fields | Approval and execution; all eight proposed attempts not run |
| Reproduced cause or bounded non-reproduction | Neither claimed | Controlled comparison and discriminating evidence |
| Reviewable recovery and consent | Linked procedure, explicit stop rules | Confirm actual bootloader recovery on the trial device |
| Linked evidence | Scoped tooling/research PR | Maintainer acceptance |
| Merged work and complete criteria | Partial contribution only | Issue 13 stays open; issue 17 stays blocked |

## Validation

Collector source: `485d5a51558351b0ef64692476d1b6c5a7ffba5d`. The command below returned
2, as expected: all six kernel queries succeeded, but the recent-boot window was full
and live pstore was inaccessible. A full window does not prove older boots exist.
The per-boot kernel record counts were 984, 885, 1631, 11937, 2636 and 3643; none reached
the 30,000-entry limit. Collection time is in the JSON.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tools/collect-boot-evidence.py --device-id m2-j413-issue13 --output docs/evidence/issue13/m2-boot-evidence.json
```

The first collection at `37ef042` used an unsupported `journalctl --kernel` option.
It returned 2 and marked every journal query failed/empty, rather than treating missing
logs as clean. The successful capture above uses `--dmesg`; a regression assertion was
observed failing before the correction and passing afterward. No firmware or hardware
operation was involved in either collection.

The full offline suite passed in a Bubblewrap sandbox with a read-only host filesystem,
private temporary directory and networking disabled. The JSON-schema dependency was
installed only in a temporary Python environment.

| Check | Result |
| --- | --- |
| Shell syntax for installer, uninstaller, rebuild/test helpers, package recipe and reproduce helper | Pass |
| `bash tests/rebuild.sh` | Pass |
| `bash tests/installer.sh` | Pass; synthetic command shims only |
| `python3 tests/boot-evidence-test.py` | 14 passed; repeated after command-option correction |
| `python3 tests/qualify-device-test.py` | 15 passed |
| `python3 tests/h264-interlace-scan-test.py` | 12 passed |
| `python3 tests/vp9-sub64-scan-test.py` | 22 passed |
| `python3 tests/package-provenance-test.py` | 19 passed with jsonschema 4.25.1 |

Documentation links and committed JSON were checked locally. No raw journal message,
stderr, hostname, boot ID or pstore content is included in the captured JSON. The source
of the selected-module hash remains distinct from loaded identity.

Hardware and boot experiments are not run because this contribution is limited to
read-only investigation.
