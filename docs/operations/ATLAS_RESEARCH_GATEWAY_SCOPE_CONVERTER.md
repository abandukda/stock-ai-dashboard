# Research cache-plan to existing gateway scope — review only

Base: `1b19b3f3f0e43aeb6423e384d174cc93c0bb49b3` (PR129/130 externally merged). This change converts compatible plans; it does not issue an authorization, change the endpoint allowlist or workflow routing, expose credentials, acquire data, certify financial inputs, or publish/append anything.

## Concrete integration

`services/research_gateway_scope.py:build_research_gateway_scope()` accepts the whole compiled cache-first Research plan, an exact expected source SHA and an explicit bounded requests-per-minute policy. It uses the extracted pure `validate_execution_plan()` checks already used by rehearsal, then verifies source, budgets, request schema, endpoint/capability mapping and parameter identity.

The converter returns a **review wrapper** containing `scope` and its separately calculated `scope_sha256`. Only the `scope` object belongs in the immutable gateway artifact. Submitting the wrapper itself fails the existing gateway digest check. There is no embedded self-hash inside the scope that could conflict with `services/operations_gateway.py:verify_scope()`.

- Original ordinal, ticker, capability, endpoint, parameters and request digest identity are preserved; `method=GET` is added. Original request hash is explicitly named `source_request_sha256` because adding a method changes the request representation.
- Source/upstream/package/scope digests are bound; narrower caller ticker/request budgets are preserved. Concurrency1/retries0 are required; RPM must be an integer1–500. Raw token/header fields, unexpected request/limit fields and malformed retained/unavailable/deferred record schemas are rejected.
- Every selected request must be supported by the **existing** gateway allowlist and the repository's signed-contract mapping. Unsupported endpoints cause a failure for the whole plan. No unsupported request is removed, renamed or silently substituted.
- Retained, unavailable and deferred records remain visible; conversion does not declare them current or invent missing evidence.
- No transport client, network call, filesystem write, live-enablement switch or token generation is part of this service. The existing unavailable cache-first LIVE interface is unchanged.

## Real compatible example and explicit gaps

A freshly compiled four-ticker plan for **ANET, META, MSFT, NVDA** can explicitly select these eight families:

| Selected family | Existing gateway endpoint |
|---|---|
| historical_ohlcv | `/stock/candle` |
| financial_statements | `/stock/financials-reported` |
| stock_earnings | `/stock/earnings` |
| earnings_calendar | `/calendar/earnings` |
| recommendations | `/stock/recommendation` |
| price_targets | `/stock/price-target` |
| company_news | `/company-news` |
| company_profile | `/stock/profile2` |

The existing compiler also includes split/dividend evidence because historical OHLCV was selected: `/stock/split`, `/stock/dividend`. This is **10 families ×4 tickers =40 logical requests**, with caller limit40, concurrency1, retries0 and chosen60RPM. This is a new scope, not a filtered copy of the60-request review.

The previously reviewed extended60-request scope is rejected because it contains these five families absent from `operations_gateway.RESEARCH_ENDPOINTS`:

| Rejected family | Endpoint |
|---|---|
| live_quote | `/quote` |
| basic_financials | `/stock/metric` |
| analyst_actions | `/stock/upgrade-downgrade` |
| revenue_estimates | `/stock/revenue-estimate` |
| eps_estimates | `/stock/eps-estimate` |

All five endpoints exist in the repository contract inventory; gateway rejection means the registered execution scope does not yet admit them. It is not a claim that Finnhub commercial display is prohibited. This converter does not widen security-sensitive acquisition scope.

Actual provider-free example generated at the stated base with a22:05UTC planning clock (not a capture time), October22 session and40-request ceiling:

- Compiled package: `b17cde6dd5226f4da2c8a1b4557231ed863bc96bdae326980cada14173196aa5`.
- Original refresh scope: `8002f3c2d7fa470489cceb0b293295347bbaafd0c637f91b15f1c102babfedfd`.
- Converted gateway scope: `d721570dc7da84592c89d3b9cd30a1cc180baf54ba6717accd565c3950164fb2`.
- Authorization issued/provider calls/publication writes/Report Card writes: **false/0/0/0**.

The planning entitlement input was a mock approved fixture. The result is not account-entitlement proof, current source evidence, a one-use claim, or an execution approval. Recompile/rebind at the actual approved merged SHA before requesting any real scope approval.

## Existing execution path and remaining blockers

The registered `atlas_stable_research_gateway.yml` already provides a hosted `ubuntu-24.04` acquire job behind `atlas-licensed-research-acquisition`. It freezes default-branch code, verifies the immutable scope artifact and approval envelope, re-verifies it before acquisition, and invokes `scripts/run_licensed_research_gateway.py`. It is distinct from worker21's protected incremental/backfill/ledger routes. This change moves none of those workloads.

**Compatibility is not execution readiness.** In particular, the existing gateway authorization string is deterministic and the current generic raw gateway does not establish durable one-use claim/idempotency proof. A rerun must not be assumed safe merely because conversion and scope verification pass. No token is emitted here.

Next owner/execution package must separately establish:

1. Exact reviewed merged code SHA, immutable artifact/run/path/digest, explicit40-request scope or another newly reviewed scope, live account entitlement/retention, rate/attempt ceiling, expiration and separate acquisition authorization.
2. Proven one-use claim/durable response/resume semantics or an independently reviewed bounded recovery procedure before executing/rerunning acquisition. Do not silently borrow worker21 claim state or move protected data.
3. Source/backup authority, source timestamps, XNYS completed-session continuity, adjustment evidence and response hashes. Raw-first acquisition is not financial certification.
4. A normalized, verified Research admission bundle and approved private delivery with exact source/bundle pins. Existing `research_history_ingestion.build_history_bundle()` may be reused for complete current candles with explicit adjustment proof; it does not install production files.
5. Separate promotion/publication authority, rollback/alerts and authenticated production acceptance. Report Card observations/ledger writes/public activation remain separate and OFF.

Research presently consumes admitted history, recommendations/targets, profile, metrics, news and calendar. Adding quote/EPS/revenue-estimate requests to planning does not wire those families into customer Research or alter its Last Certified Close/Fair Value authority. Those UI/normalization integrations remain distinct follow-up work.

## Validation and stage

The converter's tests exercise the existing gateway verifier using **mock plan-mode approval only**, unchanged scope/budget/source preservation, unsupported endpoints, complete60-request rejection, stale/mismatched hashes, secret/parameter/schema injection, duplicate requests, rate limits and absence of mutation. Existing rehearsal regressions preserve valid lifecycle behavior.

Executed validation: **92 tests passed** with sockets denied and0 network attempts (1.43seconds; peak process RSS143,580KiB, not a financial-data-cycle memory measurement). `py_compile` and `git diff --check` passed.

BUILT/TESTED in review only. Not merged, deployed or live verified by this change. No original ledger, source archive or production data was accessed or modified.
