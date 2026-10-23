# Certified data: Claude review reconciliation and executed boundary repair

Review baseline: `d2dd0f9` (PR119). Rechecked code baseline:
[`d5ae98242ef64743149b218e0ba12b8965713b97`](https://github.com/abandukda/stock-ai-dashboard/commit/d5ae98242ef64743149b218e0ba12b8965713b97)
(PR137). This report contains hashes and counts, not a licensed feed. No
acquisition, original-ledger access, archive download, configuration change,
certification, promotion or publication was performed.

## Finding-by-finding reconciliation

| Claude ID | Classification at current baseline | Source / demonstrated property | Tests and production evidence | Remaining correction / owner |
|---|---|---|---|---|
| P0-1: no successful unattended refresh | Confirmed unresolved operationally | [`run_daily_buy_now_post_close.py`](../scripts/run_daily_buy_now_post_close.py) requires a certified boundary before planning. [`atlas_daily_incremental_buy_now.yml`](../.github/workflows/atlas_daily_incremental_buy_now.yml) reads the manifest's finalized session, then the repository variable. Neither generation time nor latest row price is a continuity proof. | `test_daily_coordinator_receipts.py` exercises missing/bad boundaries and unchanged inputs. [Actual run39878684720](https://github.com/abandukda/stock-ai-dashboard/actions/runs/39878684720) failed `DAILY_BUY_NOW_CONTIGUOUS_BOUNDARY_REQUIRED`, zero provider calls/writes, protected jobs skipped. | Verify retained archives, authoritative history/checkpoints/actions and independent backups; certify a real boundary before separately approving its configuration and live operation. Data owner. |
| P0-2: four manifest hashes do not match 35-row customer files | Arithmetic confirmed; wrong-namespace inference is superseded by the explicit runtime binding | [`runtime_projection_contract.py`](../services/runtime_projection_contract.py) preserves the full executor digests under source certification and separately hashes the exact deployed projection. All eight deployed files match the latter. The 35 rows are explicitly `RELEASE_SMOKE_BOUNDED_UI`, not 6,033 freshly certified securities. | Executed `PYTHONPATH=. python scripts/audit_runtime_projection.py --root .`: eight PASS, no failures. `test_bounded_projection_is_distinct_and_valid` proves different source/runtime digests are intentional; mutation regression proves customer loading fails closed on altered projection. | Full executor digest/content, all41 shards and source-to-projection ancestry still need independent retained-artifact verification. Local binding PASS is not full-source certification. Data owner. |
| P1-6: production snapshot in Git | Confirmed architecture remains | [`app.py`](../app.py) reads `market_full_scan.json`, `full_evaluation_pool.json` and `publication_manifest.json`; [`runtime_projection_loader.py`](../services/runtime_projection_loader.py) verifies the exact retained customer projection. | Actual production QA39878126614 confirms expected source SHA, not a new financial snapshot. No private versioned snapshot store is proven operational. | Prepare content-addressed private snapshots with atomic pointer and rollback; infrastructure/storage and promotion need approval. Do not delete Git history or redirect production during this repair. Release/data owners. |
| P1-7: cron admission/recovery | Partially superseded; operation unresolved | Current [`daily_buy_now_post_close.py`](../services/daily_buy_now_post_close.py) uses 18:00–18:30 America/New_York, not the review's18:00–18:59. Duplicate/finalized-session guards remain. | `test_daily_buy_now_post_close.py` checks exchange calendar, Eastern window and duplicate behavior. Actual8:32PM ET run above stopped on absent boundary before eligibility; this does not prove an on-time scheduled success, Cronitor delivery or recovery. | After continuity and explicit execution approval, record an admitted daily cycle, independently inspect alert receipts and deliberately verify last-known-good failure behavior. Scheduler changes need separate review. Operations owner. |
| P1-8: 1,298/6,033 coverage | Counts confirmed; customer success-rate inference unsupported | Source contract records6,033 universe,1,298 customer allowed,4,735 withheld. Deployed projection has35 rows,15 customer allowed and11 published BUY_NOW. | Inventory regression checks21 source BUY_NOW =11 publishable+10 withheld, no withheld leakage; actual runtime inventory reproduced below. | Reconcile source reason/security types and set an explicit product coverage target. Do not interpret21.5% as beta ticker success rate or claim that all1,298 are deployed. Product/data owners. |

## Exact source and customer projection reconciliation

Candidate `64c0a00a2805fc8c0378c8a701b8362963e689e22715c39da26e8df7e0fd5a67`;
publication `72b37697b2f4fc5dabd5438c1a3bb7c068cd12e86253b64e37b8a642c310bf17`;
analytical source `aa12ff9e89c1ac72e20aadad41decfba9a3d774d`;
evidence snapshot `2026-10-04T12:21:38-04:00`. These are retained identities,
not a current acquisition receipt.

| Exact deployed file | Records | Matches full-source digest? | Matches deployed-projection digest? |
|---|---:|---|---|
| market_full_scan.json |35|No|Yes|
| full_evaluation_pool.json |35|No|Yes|
| market_prescreen.json |0|No|Yes|
| discovery_candidate_pool.json |0|No|Yes|
| recovery_scan.json |0|Yes|Yes|
| etf_scan.json |0|Yes|Yes|
| total_market_universe.json |1 object|Yes|Yes|
| market_scan_state.json |1 object|Yes|Yes|

Both35-row files have semantic SHA256
`115bf251f313fd2a53c0edcdeef68a1808fecbcee7843861f2e491e87392e97a`.
The retained full-source scan digest is
`c8b02f6a5939bf389f64fea99f3bba633170146007e67d5535edf16bcdf8d30e`;
full-source evaluation/prescreen/discovery digest is
`e5d43607bf1fbc68cc1075914b665fecd9b47242ee6e00a985a153f1442368fe`.
The empty deployed arrays hash to
`4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`.
Replacing the source digests with customer digests would erase the distinction,
not repair certification. No manifest or financial artifact was modified.

## Source-to-production path and exact gates

| Step | Existing code / authority | Current evidence and missing dependency |
|---|---|---|
| Contract endpoint | [`finnhub_enterprise_display_contract.py`](../services/finnhub_enterprise_display_contract.py), signed endpoint inventory | Website/mobile display and permitted local processing are distinct from raw redistribution. Contract rights do not issue one-run execution approval. |
| Bounded hosted transport | [`atlas_stable_research_gateway.yml`](../.github/workflows/atlas_stable_research_gateway.yml) | Already uses hosted Ubuntu24.04 and `atlas-licensed-research-acquisition`; does not require worker21. Default-branch code is frozen, scope hash/review token/call cap independently verified, provider credential step-scoped. No new infrastructure or protected migration needed to use this existing route, but real acquisition remains separately gated. |
| Scope conversion | [`research_gateway_scope.py`](../services/research_gateway_scope.py) | Tested exact four-ticker plan, request budget, endpoint/parameter/source binding, no silent unsupported-family filtering, no issued authority. Parent plan/source/scope artifact must be reviewed and pinned. |
| Raw evidence | [`run_licensed_research_gateway.py`](../scripts/run_licensed_research_gateway.py) | Exact response-byte and attempt receipts are required. No actual current authorized raw NVDA/MSFT/META/SPY capture was supplied or fetched in this execution. |
| Normalize and adjustments | [`research_history_ingestion.py`](../services/research_history_ingestion.py) | Requires explicit adjustment basis/evidence, finite OHLCV, complete finalized XNYS sessions and raw capture binding. Numeric candles alone cannot prove split/dividend treatment. |
| Certification / review | `build_history_review_from_gateway_capture` | Produces `OWNER_REVIEW_ONLY_NOT_PUBLISHED`; wrapper is deliberately not an admissible read-model document. Hash agreement is not financial certification or promotion approval. |
| Private admission/store | [`research_market_read_model.py`](../services/research_market_read_model.py) | Checks ticker, rights, source/bundle pins, payload/record/lineage hashes and independent-backup declaration. Real private roots/pins and independent physical copy are not verified. This branch repairs a consumer continuity bypass below. |
| Renderer | [`customer_research_v2.py`](../services/customer_research_v2.py), [`research_runtime.py`](../ui/research_runtime.py) | Expected source/auth passed production39878126614, required NVDA historical chart failed. Receipt `NOT_RECORDED` cannot normally be emitted by current cold reader path. Loaded financial module/worker identity remains unavailable; no financial reload/restart performed. |

The hosted gateway is a possible **bounded individual-ticker acquisition route**,
not authorization to migrate full-universe certification or the Report Card
ledger. It does not by itself install an admitted bundle into Streamlit.

## Actual engineering correction: enforce continuity at the read boundary

Baseline reproducer supplied valid completed Oct19 and Oct21 candles with Oct20
missing. `_market_identity` returned `CURRENT_FINALIZED_SESSION` because it
checked session membership but not continuity. The producer already rejected
this gap, but a fully hashed retained/legacy document could bypass that producer.

The reader now requires exactly the XNYS sessions within the **supplied first to
last session interval**. It does not require stale retained history to reach
today; weekends/holidays are not fabricated gaps. Bad history is rejected while
unrelated verified families remain available. No payload, financial value,
rating, source hash, feature flag or QA assertion is rewritten.

New properties demonstrated by actual tests:

- A resealed current-last-candle bundle missing an intervening trading session
  cannot be admitted; receipt is PARTIAL/history REJECTED.
- Friday→Monday complete history remains admissible, and is explicitly stale
  when reviewed after the next finalized session.
- Existing raw-response binding, producer continuity, reader rights/identity,
  runtime hash mutation, gateway budget and daily-boundary tests still pass.

Executed selection: **164 tests PASS in5.20s**; repeated **164 PASS in4.73s**
with socket connection creation/connect/connect_ex blocked: **zero network
attempts**. Generated input only; no current-data
or production acceptance claim.

## Required next decisions

1. Approve the separately pinned retained-archive integrity run at current main;
   recheck exact source before dispatch. Then certify continuity from actual
   history/checkpoints/actions and authoritative independent backup evidence.
2. If current licensed capture is still required, approve a separate bounded
   hosted gateway scope for NVDA/MSFT/META/SPY with exact endpoint/parameter,
   call/time budget and raw-evidence retention. No implicit provider call.
3. Approve source-to-private-store admission/promotion and runtime configuration
   separately after evidence passes. An acquisition receipt cannot approve its
   own customer publication.
4. Obtain read-only deployed module identity or separately approve a clean
   worker restart; retain the unchanged authenticated historical-chart gate.

BUILT/TESTED applies only to the new provider-free reader repair. MERGED,
DEPLOYED and LIVE VERIFIED are **NO** for this candidate. Public Report Card
remains OFF and no genuine observation is appended.
