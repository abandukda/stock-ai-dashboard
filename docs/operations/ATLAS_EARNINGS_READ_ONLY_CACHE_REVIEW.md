# Earnings retained-evidence customer bridge

This review branch removes acquisition from both customer earnings-call buttons.
`render_earnings_vnext(..., transcript_cache_reader=None)` is disconnected by default.
A trusted backend may explicitly inject `ReadOnlyTranscriptCache` for an existing,
separately approved private cache, account, retention deadline and summary policy
revision. This patch supplies no production path, credentials, enable flag, acquisition
approval, model approval or automatic storage discovery.

## Evidence and availability

The period picker probes at most 444 exact account-bound quarter identities instead
of scanning other accounts' records. Available retained transcripts and available AI
summaries have separate states. Exact-quarter cache availability does not prove the
latest earnings release is present. Missing summaries remain pending and never trigger
a provider or model. Existing deterministic earnings explanations remain intermediate,
contextual and non-scoring; this patch does not certify current financial intelligence.

The reader verifies private owner/mode, retention, storage schema, body digest,
account/provider/license namespace, exact fiscal/requested/resolved period, raw source
hash, capture times and summary source/prompt/schema/grounding lineage before display.
The customer projection contains allowed derived claims and attribution only. Raw text,
source excerpts, credentials, private namespace and authentication tags are not returned.
Changing backend account forces revalidation on every render; session state stores only
selection state, not source or derived projections.

## Private cache authentication

The existing writer now adds a private record MAC binding kind, identity and canonical
body to the credential-derived account namespace. It uses the same records table;
there is no schema migration. This prevents copying/rekeying another account's cache
body with a recomputed unkeyed digest. Unsigned legacy rows fail closed with explicit
pending offline account-binding revalidation. No legacy row is rewritten, refetched or
relicensed automatically. Any approved revalidation must inspect original provenance
and rights outside the customer UI. Account credential rotation intentionally invalidates
reuse until separately reviewed. The namespace is private key material; filesystem
permissions remain essential, and this is not encryption at rest.

## Read-only storage behavior

Construction neither opens nor creates a database or directory. Reads use SQLite
`mode=ro`, `query_only=ON`, a bounded record size and a read transaction. Existing
journal/WAL/SHM sidecars and WAL-mode file headers are refused. `immutable=1` is not
used. Ordinary SQLite read locking coordinates a DELETE-journal writer; this is not a
claim of exclusive writer control or globally immutable storage. A writer or storage
error fails closed; no read callback repairs, creates sidecars or falls back to network.

## Acceptance and remaining owner gates

Provider-free regression tests inspect real temporary SQLite bytes across restart,
missing paths, sidecars, read-only SQL, retention, source/period/license tampering,
unsigned/cross-account rekeyed records, summary lineage and customer callbacks with
provider/model entry points forbidden. These are offline fixture results, not production
screenshots or real transcript acquisition evidence.

Before production connection, approve the exact cache location, current account and
contract-specific display permission, retention deadline and model-policy revision;
verify private storage and any unsigned retained evidence through a separately governed
offline process. Approve acquisition and external model execution separately, and then
inspect real authenticated desktop/tablet/mobile production results. No public Report
Card activation, ledger writes, licensed acquisition or paid AI occurs in this change.
