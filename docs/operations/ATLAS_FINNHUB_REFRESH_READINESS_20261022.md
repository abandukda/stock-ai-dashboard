# Finnhub refresh readiness — provider-free review, October 22

Base source: `190f1307444c6f17efb059c8b108e561f15ece3d` (PR128 merged externally). This review changes code/tests only. It does not authorize or execute licensed requests, paid AI, promotion, publication, ledger writes, runner recovery or protected migration.

## Actual repairs

- The compiler previously enlarged narrower caller request limits to225. It now preserves the caller's maximum ticker/request limits; capability-major selection defers lower-priority families within that bound.
- Rehearsal previously trusted its package-derived directory and request identities, and treated a receipt as resumable without proving its raw intent/envelope still existed. Package/scope/request consistency is now checked before any directory write; resume requires the original intent, terminal receipt and matching simulated-envelope hash. Hashes prove consistency, not owner authorization or authenticity.
- Valid JSON arrays/null and non-object `families` previously crashed the read model. It now rejects them and can use the already-verified backup. OHLCV NaN/infinite/overflow timestamps, boolean price/timestamp/volume values and malformed array containers fail closed; valid remaining families stay available. Family keys must match the envelope capability, preventing relabelled payloads from entering a different display family.
- Quotes, company profiles and revenue/EPS estimates can now be explicitly selected in the provider-free plan. They require repository contract coverage plus the entitlement input; they are never added to the default nine-family scope. Quote-only selection does not acquire historical adjustments. Unknown, duplicate, empty or non-string selections fail closed. Planning clocks must be timezone-aware.

The default nine-family planner,25-ticker/225-request absolute ceiling, concurrency1/retries0 and unavailable LIVE executor are preserved. A smaller caller ceiling is now authoritative. The legacy compiler's split/dividend requests remain coupled to selected historical OHLCV, not to quote-only selection.

## Endpoint evidence and scope

Authoritative repository inventory inspected: `services/finnhub_enterprise_display_contract.py`, `ENTERPRISE_DISPLAY_MATRIX`, contract ID `FINNHUB_MARKET_DATA_AGREEMENT_SIGNED_APPENDIX_A`. This execution inspected that code inventory; it does not claim to have independently reread the signed Appendix or revalidated the account entitlement. The existing distinction between commercial website/mobile display and prohibited raw machine-readable redistribution remains intact. Transcripts are the separate EarningsCall service, not Finnhub.

New opt-in inventory mappings:

| Capability | Existing contracted endpoint | Request parameters | Cache reuse ceiling |
|---|---|---|---|
| live_quote | `/quote` | symbol |60seconds |
| company_profile | `/stock/profile2` | symbol |7days |
| revenue_estimates | `/stock/revenue-estimate` | symbol, freq=quarterly |8hours |
| eps_estimates | `/stock/eps-estimate` | symbol, freq=quarterly |8hours |

Parameters are compiled in `services/research_refresh_execution.py`; cache-age policy resides in `services/research_market_read_model.py`. TTL is a cache-reuse policy, **not** proof that provider observation timestamps, finalized sessions or production snapshots are current. These new families are not wired into a live transport or financial-scoring authority by this change.

## Exact review package

`ATLAS_FINNHUB_REFRESH_REVIEW_PACKAGE_20261022.json` contains actual provider-free compiled requests and source-code hashes. The entitlement input is explicitly a simulated approved fixture; it is not an execution entitlement receipt.

- Scope: **ANET, META, MSFT, NVDA**,13 explicitly selected data families plus splits/dividends =15 families ×4 tickers = **60 logical requests maximum**, concurrency1, automatic retries0.
- Session:2026-10-22; requested execution window18:00–18:30 Eastern (22:00–22:30UTC). The22:05UTC planning clock is not an actual capture timestamp.
- Compiled package hash: `7c1dfacd840f00389451d8372cdd539f2c2900afda1c40595225c9c90b9128fe`.
- Compiled scope hash: `4ebf11ed2252155ef135df7e6e2b6b40464b4fd56d287e1ee0594eda0380b67a`.
- Review receipt hash: `97eabc03edaef7908c058e67e20b45249403c858949c95033b577d2b7397708a`.
- Actual provider requests/publication/ledger writes: **0/0/0**. No acquisition token issued or authorization consumed.

These hashes are review evidence at the stated base with the included code hashes. **Recompile and rebind at the actual approved merged source SHA before any execution approval.** Do not use this review package as a live token or substitute another source silently. The default four-ticker scope remains44 requests;60 applies only to the explicit extended scope.

## Acquisition approval prerequisites — not execution instructions

1. Approve the exact code head after governed CI; preserve existing worker21 routing and named protected environment. Both worker21 and staging23 being Offline does not authorize migration or service recovery.
2. Prove original-host/current source authority and independent backup integrity; execute separately authorized retained-archive verification. Freeze approved cache/source digests so verified cache hits remove duplicate requests rather than manufacture availability.
3. Revalidate the signed endpoint entitlement/account and retention obligations; bind the actual merged source SHA, exact ticker/endpoint/parameter scope,60 maximum logical requests, retries0, expiration and request accounting. Credentials stay in the protected environment; never enter the review JSON, artifacts or frontend.
4. Review/register the protected acquisition executor and its one-use claim/idempotency mechanism before approving a real run. `execute_live()` intentionally still returns `RESEARCH_REFRESH_LIVE_WORKFLOW_NOT_REGISTERED`; this **new cache-first contract** has no registered live executor. Existing hosted `atlas_stable_research_gateway.yml` and Finnhub full-core/incremental/backfill transports already implement separately gated acquisition; they are not authorized by this review. Compatible hosted raw Research acquisition does not require worker21 migration, but needs an exact immutable gateway scope and subsequent independent normalization/certification/admission. The new extended60-request plan is not directly gateway-compatible, and quote/metrics/estimate/upgrades endpoints remain outside its existing allowlist. HTTP request accounting and one-use authorization must be reviewed for the selected path; logical requests are not actual HTTP receipts.
5. Capture source responses once into approved private storage with sanitized request/source/capture/hash receipts. Empty, partial, non-entitled, rate-limited or stale responses remain failures or explicit gaps; no automatic provider switch/backfill/retry beyond approval.

## Separate promotion/publication acceptance

Acquisition approval does not grant promotion. A later independently reviewed promotion bundle must prove all of the following:

- Correct ticker/source identity, complete expected-family inventory, response hashes, licensed-use flags and no raw-feed customer export.
- XNYS October22 finalized-session membership, continuity across required history, actual provider observation times, no future/incomplete bars, OHLCV geometry and certified corporate-action/adjustment convention.
- Source-backed fundamentals/estimates/earnings interpretation with dated disclosures. A quote TTL or successful render is not certified current financial information; Research context cannot replace governed BUY NOW/Top15 ranking authority.
- A content-addressed candidate manifest, exact source and artifact hashes, current-versus-withheld decisions and a read-only preview. No incomplete input is labelled current to fill Top15.
- A separately authorized atomic publication/delivery operation with a prevalidated prior pointer/manifest for rollback, independent backup/restore evidence and alerts. No production target/path or infrastructure changes are authorized by this document.
- Actual deployed SHA, secure read-model source/bundle pins, Home and NVDA/MSFT/META/ANET Research screenshots at desktop/tablet/mobile, role isolation and source-current chart admission. Rollback must restore the prior approved pointer/hash and reverify runtime source; never mutate original source archives or Report Card ledgers.

Any failed financial/source/security gate means no promotion; keep the prior admitted snapshot with honest date/missing-data disclosures. A failure alert must contain stage/run/source hashes and sanitized recovery action, not provider credentials/raw data.

## Independent Report Card boundary

This4-ticker Research scope is not a Report Card acquisition package. Original20 identities/current ledger+WAL and backup authority,17 retained tickers' governed certification, AMZN/MPC/VLO/SPY coverage, adjusted entry/horizon prices, registration timing and SPY alignment remain separate. Customer publication proof cannot be inferred from internal registration. No observation bundle or append authorization is issued; public activation remains OFF.

## Acceptance state

Executed validation: **66 regressions passed** with socket connections denied and0 attempts (2.21seconds; peak process RSS227,788KiB for the test process, not a full retained-data cycle). The actual review package rehearsed60 simulated intents/envelopes/receipts and resumed60/60 from temporary storage, with0 provider calls/network attempts; all4 pinned code-file hashes and review-file hash remained equal. `py_compile` and `git diff --check` passed. No actual archive, original ledger or production data was modified.

BUILT: bounded opt-in planning and integrity/admission repairs. TESTED: provider-free regressions and generated-package durability as above. MERGED/DEPLOYED/LIVE VERIFIED: not by this review. Current refresh readiness remains **NO-GO for real acquisition/promotion** until the operational/source/executor/authorization gates above pass. No promise of a18:00 refresh is made from mock plans.
