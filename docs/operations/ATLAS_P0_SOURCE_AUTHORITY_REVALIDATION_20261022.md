# Source authority revalidation — 2026-10-22

This is read-only evidence, not authorization to restart a host, migrate a workload, acquire data, append observations or publish. Public Report Card remains OFF.

## Actual interrupted execution

Run `39544587581`, source `0dba8841d53f30236aaff42f967f9475362b1a3d`, job `119039757269` executed on runner21 `atlas-worker-1`. All41 technical-history artifacts downloaded successfully by04:37:59UTC onOctober21. Certification then ran until04:57:30.7245467UTC, when the runner logged: “The runner has received a shutdown signal.” Cancellation followed04:57:31.3545908UTC; artifact upload was skipped. The run has zero final artifacts.

The decoded job log is68,529UTF-8 bytes, SHA256 `b520707954b7d9d399e38357e6fcb750b251cfff8375b2023fad5c3f78632448`. Executing the existing shutdown classifier on that log returns `SHUTDOWN_INITIATOR_UNPROVEN`, shutdown=true, OOM=false. This does not prove no host OOM occurred: kernel/service/reboot logs remain unavailable. The separately recordedOctober16 OOM must not be assigned to thisOctober21 shutdown.

## Retained metadata revalidation

Fresh GitHub metadata matched all42 entries in `ATLAS_CONTABO_RETAINED_INVENTORY_20261021.json`: exact IDs, names, byte sizes, registered SHA256 digests and unexpired status. Run37216506983 exposes45 artifacts including41 shards; chart-source run37553164176 exposes45 including41 shards. This revalidates metadata, not archive contents or current financial correctness.

| Final artifact | Bytes | Registered archive SHA256 | Expiry |
|---|---:|---|---|
|11318542723 / run37216506983|1316392491|9612c6b9fa02c74de710c7af0c9e644c5976392e2e9efa0c47b20522316d7c1e|2027-01-02T16:22:09Z|
|11456584757 / run37553164176|740189265|ecf66bcd49a72bbd85f76365b9005a43622f87494b2aa4468f3a1ef3c0bcf4f1|2027-01-05T00:40:07Z|

No archive bytes were downloaded or rehashed in this revalidation. Both oversized final archives still require separately authorized execution of `ATLAS_AGGREGATE_INTEGRITY_REVIEW.md`. Config pins require full_evaluation_pool hash `c0f04aaccfd93154f4b69e240db9817e0bf7f84da143356142c4b07a066f2ca0`; chart market_full_scan `50f1f3c7d82c7cf802aa32f8204a849ed7e0dbbf26fd17e5d263f8fb98ce96c8`; publication_manifest `36a525e06bca8c0b3b2b8c59b99eead0ac4560eff4c38cb8e858361f7b0c1dee`.

## Runner isolation

Parent agent directly inspected GitHub runner settings: runner23 `atlas-contabo-1` Offline, labels self-hosted/Linux/X64/atlas-contabo-staging, no active jobs; runner21 `atlas-worker-1` Offline. No settings changed. The connector cannot read runner administration endpoints; browser evidence is required for current status.

Workflow inspection at main `da55afc86056fbf1c0bca1f8e5538208ee477187` finds Contabo routed only to owner/manual/main generated-fixture smoke/rehearsal jobs with permissions empty and no protected environment. Protected certification/acquisition/ledger workflows retain atlas-worker-1 routing and their named protected environments. No protected migration occurred.

## Exact next owner actions

1. Original-host operator: collect existing read-only service status/show and service/kernel journals forOctober21 04:20–05:10UTC; boot list, reboot/shutdown history, relevant runner diagnostic logs and provider control-plane power/reboot events. Discover service unit first. Preserve evidence before any restart; identify initiator/boot ID/exit signal/OOM PID rather than infer from cancellation.
2. Data/backup owner: identify exact source, WAL/checkpoint and independent-backup paths and expected immutable digests for `verify_source_backup_readonly.py`. Prove coherent ledger/WAL state and chain integrity separately; file hashing cannot prove transaction coherence or physical backup independence. Do not transfer ledgers to this workspace or Contabo.
3. Repository owner: separately approve hosted two-archive integrity verification at an exact reviewed merged SHA using the existing runbook. Acceptance requires both matrix jobs success, exact archive/inner hashes and resource receipts. This grants no financial certification, data publication, Contabo transfer or observation authority.
4. After those gates: separately approve a stable protected execution environment and bounded retained-evidence certification run. Source continuity, adjustments, SPY and observation methodology remain independent acceptance gates.
