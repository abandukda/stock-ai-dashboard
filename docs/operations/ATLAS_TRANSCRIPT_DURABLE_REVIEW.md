# Durable transcript evidence and summaries — provider-free review

Base: main `da55afc86056fbf1c0bca1f8e5538208ee477187`, externally merged PR #125. No automatic acquisition, model invocation, production storage or UI wiring is introduced.

`TranscriptEvidenceStore` adds an explicit private SQLite cache around the existing EarningsCall adapter and source-grounded transcript runtime. The caller must provide a private directory and timezone-aware retention deadline from the actual transcript entitlement. There is no default production directory or guessed contract expiry.

## Tested behavior

- Successful transcript evidence persists across process-cache clearing/reopening and preserves provider ID, capture/source timestamps, exact quarter, original content hash and license class. Requests for a different resolved quarter fail closed rather than silently aliasing the selected historical call.
- Stable account/endpoint/license/adapter namespaces use a credential-keyed HMAC. Credentials and namespace tokens are never projected to customers; API keys are not stored in the database. Account/key/license changes cause a miss and require fresh acquisition authority.
- `BEGIN IMMEDIATE` serializes committed cache misses across independent SQLite connections. Committed source evidence is reused; failures are not cached. A crash between external retrieval and commit can require a new separately authorized request: this is **not exactly-once external acquisition** and is not a provider idempotency guarantee.
- Summary cache identities include source content hash, caller-supplied immutable model/policy revision, prompt version and schema version. Only successfully grounded insights are stored. Version changes do not silently reuse an older summary. Cached summaries retain their original generation timestamp and evidence identity and are re-projected through existing license/display filtering.
- Acquisition and summary-generation permissions are independent explicit inputs. Cache reads do not grant permission for another acquisition or model call. No default external model call exists in this wrapper; approved future callers must explicitly supply their summarizer and model-policy revision. Supplying a callback alone does not invoke it without summary authorization.
- Raw transcripts stay internal. The only customer output is the existing redacted derived projection. Records are plaintext inside owner-only directory/file permissions (0700/0600), **not encrypted storage**. Symlink, non-regular, wrong-owner and group/world-accessible storage fail closed. SQLite record length is capped at 16 MiB. There is no WAL or production ledger access.
- Retention expiry blocks new storage and cached serving. It does not automatically delete contracted material or provide written deletion confirmation; the owner-controlled purge/termination procedure remains required. The reviewed deadline must not be arbitrarily extended.
- Record hashes detect corruption. They are not signatures or independent backup proof; a principal controlling the cache can rewrite it. Production storage hardening and backup/restore approval remain separate.

## Limits and remaining end-to-end work

This release does not discover new quarters automatically, reconcile transcript revisions/corrections, establish current endpoint entitlement, compare claims to certified financial/estimate/historical-guidance evidence, wire customer UI, grant external-model processing rights, or deploy durable storage. Existing period discovery remains a separately authorized metadata call. A retained exact-quarter hit does not prove the latest quarterly transcript is available; freshness is explicitly labeled accordingly.

Adapter `transcript()` may perform several HTTP requests (including metadata/fallback). The reported provider invocation count is a logical adapter invocation, **not an instrumented HTTP count**. No retries, provider calls or external AI were executed in this review's tests. A future protected execution package must budget the actual transport requests, select exact quarter, declare expiry, and obtain separate acquisition and AI approvals.

## Release acceptance gates

1. Exact-head offline CI (including security/grounding tests and workflow actionlint) passes; owner reviews exact changed-file inventory and SHA for merge.
2. Separately approve private storage installation, directory/ownership, retention policy, encryption if required, backup/restore and approved display scope. No infrastructure changes occur as a side effect of this PR.
3. Separately approve narrowly bounded EarningsCall discovery/acquisition with actual entitlement proof. Persist one authentic source, close/reopen the process, and prove the same hash is reused with instrumented zero transport calls on the hit.
4. Separately approve source/model/privacy/cost scope for genuine AI. Prove citations/numbers and retained summary version reuse; compare to certified financial evidence before financial interpretation.
5. Wire and verify transcript availability independently from summary availability in desktop/tablet/mobile Research/BUY NOW. Do not declare genuine live transcript intelligence from mocks or fixture screenshots.

All prior six-workstream gates remain independent. Deterministic Research digest is intermediate. Public Report Card stays OFF; original ledger/WAL/backup authority and prospective methodology are not altered.
