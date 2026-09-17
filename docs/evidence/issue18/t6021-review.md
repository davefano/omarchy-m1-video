# M2 Max smoke evidence review, 2026-09-17

PR [#40](https://github.com/iconidentify/omarchy-m1-video/pull/40) contributes a
read-only `apple,j416c` / `apple,t6021` inventory and two reported three-vector
smoke campaigns. Acceptance is limited to that inventory and the published
output observations. **The device remains experimental and unqualified.**
This contribution does not establish the exact loaded kernel stack or qualify
the 15-patch module, full codec suites, clients, export/lifetime handling or boot.

The reviewed contributor head is
`a88d45cc74ec41d0e95ace3763900137d2ce9b19`; z23's three original commits and raw
JSON/JSONL records are retained. The accompanying [machine-readable assessment](t6021-review.json)
hashes all 18 original records and records comparisons and unknowns separately.
Raw `hardware_pass` labels describe the contributor's selected smoke vectors;
they are not a device support or full-suite claim.

## What the review verifies

Each campaign selects one vector from each suite, not the full denominator.
The six summaries contain 238 frame records in total (119 per campaign).
Their aggregate digests, ordered per-frame digests, dimensions and pixel formats
match the same vectors from the independent
[M1 resource acceptance run](https://github.com/iconidentify/libva-v4l2_request/blob/b9803ed5290ecb4b48c09482cbc6e943aee08b63/docs/resource-churn-2026-09-17/README.md).
That immutable report's `raw-evidence.tar.xz` contains the reference summaries;
its SHA-256 and member paths are recorded in the assessment.

The paired campaign summaries are byte-for-byte identical and contain no guard
run ID. The guard files have distinct run IDs/times, but the summaries cannot be
independently linked to those runs. Thus 238 means published frame records across
two reported campaigns, not 238 distinct frames or independently attested decodes.

| Codec / vector | Frames per campaign | Dimensions | Published selection |
| --- | ---: | --- | --- |
| AVC / `AUD_MW_E` | 100 | 176x144 | 1/135 full-suite vectors |
| HEVC / `AMP_A_Samsung_7` | 17 | 2560x1600 | 1/147 full-suite vectors |
| VP9 / `vp90-2-00-quantizer-00.webm` | 2 | 352x288 | 1/305 full-suite vectors |

All nine published guards contain consistent preflight/start/final run IDs and
report successful, idle exits with no remaining holders, timeout, wedge or abort.
The six helper hashes in campaign 1 match the declared driver source commit
`27da69dd5fcb438deab970061a2edcc68a9e1d93`. The inventory collector hash matches
its declared companion commit. These are offline consistency checks, not an
independent observation of execution on the M2 Max host.

## Corrected operation history

1. The read-only inventory reported missing headers and `vainfo`, a loaded
   `apple_avd`, a selected in-tree module file and a separate camera. The actual
   loaded-module hash was unknown; inventory codec capabilities remain `not_probed`.
2. Campaign 1 reports an isolated userspace build with no package/module changes.
   Selecting an in-tree `.ko` file does not identify a previously loaded binary.
3. Campaign 2 reports installation of headers, libva-utils and pahole; building a
   local module; unloading the prior module; an initial failed `insmod`; helper
   loading and a successful retry; smoke tests; and restoration of the in-tree
   module. It reports no `updates/` installation, boot service or reboot during
   that campaign. These actions are contributor assertions with the original
   operation records missing, not independently verified maintainer actions.

The later
[boot-qualification claim](https://github.com/iconidentify/omarchy-m1-video/issues/18#issuecomment-5708140991)
is separate work. Its later installed-stack results, module hash, authorization
and eventual boot outcome cannot be applied retroactively to these smoke records.

## Provenance still unknown

The original records do not supply the resolved kernel source commit, exact
patchset revision and patch hashes, build command/compiler, original failed and
successful module-load/restoration logs, or the contemporaneous saved-work and
module-operation authorization record. The reported local module hash is kept
as a reported file identity, not certification of the binary loaded during decode.

Neither campaign supplies the original corpus lock and verification output,
complete decode/guard arguments and environment, or the guard's journal boundary.
The summaries redact the selected driver and most command arguments; the guard's
recorded library path is empty. The reported isolated library identity therefore
cannot be independently tied to the execution from these files alone. Matching
output hashes do not fill any of these provenance gaps or attest to the host that
produced the files. No missing records have been reconstructed or invented.

## Review decision and remaining work

The stale inventory-only description and overly strong patch attribution are
corrected in the surrounding documentation. Original raw records remain intact,
including the failed-load account and explicit subset denominators. Maintainer
review is independent of z23's contribution; the maintainer's documentation and
assessment corrections are self-reviewed. No maintainer hardware test, package
installation or module operation was performed for this review.

Existing offline qualification, scanner, installer/rebuild and package-provenance
checks validate the tooling. They do not provide missing hardware evidence.
[Issue #18](https://github.com/iconidentify/omarchy-m1-video/issues/18) remains
open for independently qualified devices and the full per-device capability,
conformance, export, lifecycle and client evidence. Installation and boot gates
remain separate. Future evidence should preserve original build/load records,
corpus identities and guarded command history from the actual campaign.
