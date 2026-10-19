# Milestone 4 bounded Research refresh

## Status

This release provides **provider-free PLAN and REHEARSAL only**. `LIVE` is an
explicit fail-closed interface and has no registered workflow, credential, or
transport. It cannot call Finnhub, update the customer publication, alter
certified BUY NOW/Fair Value/ranks, or mutate the Report Card ledger.

## Initial scope and exact budget

The initial scope accepts at most 25 explicitly supplied tickers. A cold-cache
plan is capped at nine requests per ticker and 225 total requests:

| Priority | Family | Finnhub endpoint | Cold-cache maximum |
|---:|---|---|---:|
| 1 | Completed-session OHLCV/volume | `/stock/candle` | 25 |
| 2 | Splits | `/stock/split` | 25 |
| 3 | Dividends | `/stock/dividend` | 25 |
| 4 | Financial statements | `/stock/financials-reported` | 25 |
| 5 | Basic financials | `/stock/metric` | 25 |
| 6 | Earnings history | `/stock/earnings` | 25 |
| 7 | Analyst consensus | `/stock/recommendation` | 25 |
| 8 | Analyst targets | `/stock/price-target` | 25 |
| 9 | Company news | `/company-news` | 25 |

The hard total is **225**, concurrency **1**, retries **0**. Cache entries are
retained only when their family-specific freshness and integrity checks pass.
Unused budget may admit lower-priority analyst-revision or earnings-calendar
intents if present in the upstream signed plan. Anything beyond the ceiling is
explicitly `DEFERRED_REQUEST_BUDGET`; it is not silently described as fresh.
The plan never assumes all 225 calls are necessary or currently entitled.

## Entitlement and commercial assumptions

Every planned family must appear in signed Appendix A through
`finnhub_enterprise_display_contract.py`. The signed contract permits covered
commercial website/mobile and derived display, forbids raw machine-readable
redistribution, and limits retention to the contract period. These repository
facts do **not** prove current account endpoint access, remaining quota,
reasonable-use permission, or current commercial terms. A future protected
job must revalidate those facts before consuming an authorization or sending a
request. Market/economic-event feeds are not included in this initial bounded
ticker package and remain unavailable until separately contracted and scoped.

## Deterministic request contract

- OHLCV requests use daily resolution and UTC Unix timestamps over a bounded
  five-year window ending at the requested completed-session date.
- Split/dividend requests use ISO date ranges over the same bounded window.
- Company news uses a one-year ISO window.
- Financial statements request annual periods; metrics request `all`.
- All other request parameters are ticker-bound and canonicalized.
- Every request, scope, upstream plan, and package has a SHA-256 identity.

Completed-session eligibility and response validation remain responsibilities
of the existing canonical adapter/read model. A successful request does not by
itself make a close current or displayable.

## Rehearsal and recovery

Rehearsal writes source-bound request intents atomically before sanitized
simulated envelopes, then terminal receipts. Directory fsync and atomic rename
come from the existing durable backfill primitives. Restart skips only receipts
whose request hash matches; mismatches fail closed. Rehearsal makes zero
provider calls and writes no licensed values.

Durable Research roots must be distinct from:

- certified BUY NOW raw/checkpoint roots,
- customer-publication storage,
- Report Card ledger and backup roots, and
- temporary/checkout directories.

## Existing 8 GB worker

The plan and rehearsal retain only compact request metadata, execute serially,
and never load full-universe technical histories or invoke scoring. The
225-intent maximum is therefore independent of the 1,298-security BUY NOW
certification workload. A later LIVE workflow still needs measured disk/RAM
preflight and protected durable paths before approval.

## Required future owner decision

Before LIVE can exist, register a protected workflow bound to an exact source,
plan/package/scope digests, explicit ticker list and completed session; prove
current entitlement/quota; configure isolated raw/checkpoint roots; and issue a
consume-once authorization with an attempt ceiling no greater than the planned
request count. No such authorization is created by this milestone.
