# Private Report Card immutable binding

This optional read contract is OFF and unbound by default. It does not enable the
internal route: existing authenticated admin access and
`ATLAS_INTERNAL_REPORT_CARD_UI_ENABLED` remain required. Viewer access and public
visibility are unchanged. With the new switch OFF, the existing legacy route is
unchanged. With it ON, a failure blocks rendering; it never falls back to the
legacy durable root or chart evidence root.

All six settings must be deliberately supplied for the new mode:

| Setting | Contract |
| --- | --- |
| `ATLAS_REPORT_CARD_SNAPSHOT_ENABLED` | Explicit `true` (also accepts `1`, `on`, `yes`) |
| `ATLAS_REPORT_CARD_SNAPSHOT_PATH` | Absolute path to reviewed consolidated SQLite snapshot |
| `ATLAS_REPORT_CARD_SNAPSHOT_SHA256` | Independently verified lowercase 64-hex byte digest |
| `ATLAS_REPORT_CARD_SNAPSHOT_TIP` | Independently verified lowercase 64-hex ledger chain tip |
| `ATLAS_REPORT_CARD_SNAPSHOT_CHART_PATH` | Absolute path to reviewed retained chart authority JSON array |
| `ATLAS_REPORT_CARD_SNAPSHOT_CHART_SHA256` | Independently verified lowercase 64-hex chart byte digest |

No settings or real paths are installed by this change. Paths must be distinct,
regular non-symlink files, at most 64 MiB each. Any ledger WAL, SHM or journal
sidecar, including empty sidecars, rejects the binding. The existing immutable
reader verifies bytes before/after reading and verifies the chain tip; the chart
reader verifies bytes and renders that in-memory payload. These checks assume an
independently preserved immutable snapshot, not an actively written source.
They do not establish original-host quiescence or independent backup custody.

Chart rows must match the entire ledger signal cohort by ticker, candidate and
evaluation snapshot, with exactly one authority match per signal. The retained
acquisition provenance must include source run/commit, run identity, shard and
publication hashes, price evidence ID, completed bars and adjustment evidence.
Effective chart bars/provenance must agree with the checked payload, and chart
history cannot extend past the technical evidence timestamp. Nested overrides
cannot supply different data. This contract does not authorize a separately
unproven SPY history series; a nonempty `spy_history` is rejected until separately
reviewed provenance is supported. Existing unavailable SPY disclosures remain.

Hash pins bind reviewed evidence; format checks alone do not certify its truth.
Original source/WAL reconciliation, independent backup verification, retained
chart lineage and owner approval of the exact bundle must precede binding.
Snapshot visibility grants no performance-return authority, publication,
registration, observation generation, provider acquisition or ledger mutation.

Tests use synthetic fixtures only. Before live acceptance, separately approve
transfer/preservation and destination verification, configuration/activation and
any necessary service operation; then run the approved authenticated read-only
original-cohort checks. Merge/deployment still require exact-head approval and
passing release gates. Original visual reference acceptance remains separate.
