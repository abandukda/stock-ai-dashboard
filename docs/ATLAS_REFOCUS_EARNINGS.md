# EarningsCall reconciliation and source-correction delivery

Baseline: `d5ae98242ef64743149b218e0ba12b8965713b97` (merged PR137). Independent review: October22,2026 review of older `d2dd0f9`/PR119, full15pages read. This work is provider-free development, not acquisition or production activation.

## Findings reconciled against current implementation

| Review finding | Current source and demonstrated property | Classification | Remaining risk / correction / owner |
|---|---|---|---|
| Research has no production transcript context; genuine AI unexercised (Research/AI review pages10–11) | [transcript_provider](../services/transcript_provider.py), [durable evidence store](../services/transcript_evidence_store.py), [read-only reader](../services/transcript_cache_reader.py), [Earnings presentation](../ui/earnings_vnext.py) implement a separate EarningsCall adapter, explicit acquisition/summary gates, exact-quarter private cache, current account/license revalidation and separate transcript/summary availability | Partially addressed in engineering; production acceptance remains unproven | Actual approved account entitlement, private production cache/retention binding, separately authorized acquisition and model generation, then dedicated authenticated Earnings QA. Viewer-only run39878126614 did not visit Earnings; it cannot prove transcript availability |
| AI grounding designed rather than demonstrated (pages10–11) | PR137 ordered-term/scope/negation guards reject demonstrated attribution/negation reversals; metadata explicitly declares `semantic_entailment_verified=False`. [Runtime tests](../tests/test_transcript_intelligence_runtime.py) | Partially repaired; not a general semantic guarantee | Independent semantic/financial correctness acceptance still required; no paid call or semantic entailment claim here |
| Durable backups/finite retention (P1-1/P1-2) | Cache storage is explicit private SQLite with retention deadline/account authentication. This differs from the protected Report Card ledger and is not a verified independent backup | Unverifiable operational durability | Owner-approved storage/backup/restore plan needed. Temporary tests do not establish off-host durability |
| Potential raw machine-readable exposure (P0-5) | Raw transcript is private evidence; customer reader strips raw content/grounding excerpts and only permits licensed derived summaries. [Reader tests](../tests/test_transcript_cache_reader.py) | Boundary implemented for transcript path; public existing data decision remains separate | Signed EarningsCall terms/retention must be applied to actual account before production. Finnhub commercial display entitlement does not supply transcript rights |
| Stale or misleading intelligence (pages10–11) | Exact-quarter summaries are content/version keyed, but baseline store always reused the first transcript for a quarter. No explicit correction check existed | Confirmed engineering gap repaired in this candidate | New source checks remain explicit one-operation acquisition approvals. No automatic refresh or customer-triggered transport |
| Earnings beat does not guarantee price appreciation (owner TrackE/D) | Generated mock revision scenario contains an earnings beat, deteriorating margin and a falling share price. Revised source invalidates the earlier positive-revenue summary; separately approved exact-source mock analysis retains all contradictory observations | Demonstrated cache/grounding property, not real financial intelligence | This tests source fidelity and cache invalidation only. It does not establish causal explanation, real market reaction or production summary acceptance |

## Actual correction implemented

The durable store now accepts `refresh_authorized=True` only together with `acquisition_authorized=True`. Its ordinary `run` remains cache-first and makes no implicit correction requests. A changed exact-quarter source is retained under a content-derived `transcript_revision` identity; the initial `transcript` record and all old versioned summaries remain unchanged. A private authenticated `transcript_head` selects the active revision in the same SQLite transaction.

The reader follows that verified pointer using read-only SQLite. The existing source, exact-period, account, permission, content-hash and generation identity checks remain in place. A new source hash cannot reuse the prior source's summary. Its summary stays pending until separately approved generation succeeds. An unchanged check reuses the existing source and summary without another model call. Denied/unavailable checks preserve the last verified call; wrong-quarter corrections roll back. An authenticated pointer is not a financial certification or source-entitlement receipt.

No existing schema/table migration is needed; the existing records table gains two opt-in record kinds only when the protected caller explicitly checks a correction. Older readers cannot consume a newer head, so a writer/reader version pair must be deployed coherently before this opt-in is used. Default old cache records remain readable. Rollback before any correction execution is code-only; after corrections, reverting to an older reader would show the original call rather than the active correction and must not be treated as equivalent authority.

## Executed provider-free evidence

`tests/test_transcript_source_revisions.py` uses only a generated mock transport/model and disposable private SQLite. It verifies changed margin commentary invalidates old analysis, preserves original and old summary bytes, returns pending after correction, exposes only licensed derived output after separate mock generation, and never infers a price gain from an earnings beat. Additional cases cover separately required acquisition, unchanged-check reuse, denied-check preservation, wrong-quarter rollback and head tamper rejection.

The existing reader tests used a fixed midnight reader clock with live wall-clock capture timestamps, so they failed after UTC midnight even on valid fixture sources. Their mock capture clock now matches the existing fixed test clock. Production future-timestamp rejection is unchanged.

Executed scoped suite: **87 tests PASS in1.41s** (revision/store/reader/runtime/provider contract/cached UI). Calls in tests are mock transport/model invocations; no licensed API or paid AI request was executed. A final post-review repeat is recorded in the integration handoff.

## Stage and next acceptance

| BUILT | TESTED | MERGED | DEPLOYED | LIVE VERIFIED |
|---|---|---|---|---|
| Revision-aware source/cache path implemented | Scoped mock pipeline and security regressions pass | No (review candidate) | No | No |

This removes a concrete cache-correction limitation; it does not finish guidance comparison against certified results/estimates, aggregate AI budget enforcement, semantic validation or durable production operations. Separate owner decisions remain acquisition scope, permitted transcript retention/private storage, exact paid-model budget/version and customer publication. No provider credentials, transcript contents or ledgers were transferred.
