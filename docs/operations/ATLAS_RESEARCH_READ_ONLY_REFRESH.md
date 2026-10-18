# ATLAS Research read-only refresh contract

## Current operating state

Research rendering is independent of full-universe BUY NOW certification. It
reads only self-hashed retained bundles through
`services/research_market_read_model.py`. Serving a page has a request budget
of zero and cannot change certified recommendations, publication state, or the
Report Card ledger.

`services/research_refresh_readiness.py` adds a planning boundary for a future
authorized refresh. It is cache-first, deterministic, and transport-free. The
default scope is at most 25 tickers and 225 request intents, concurrency one,
and zero retries. A plan is not an acquisition authorization.

## Signed Finnhub display coverage

The repository's signed Appendix A display contract covers the following
Research families used by the planner:

| Evidence family | Registered endpoint | Display use | Important limitation |
|---|---|---|---|
| Completed-session OHLCV | `/stock/candle` | Historical price/volume charts | End-of-day evidence only; completed XNYS sessions must be validated. Not real-time. |
| Financial statements | `/stock/financials-reported` | Reported financial history | Missing periods remain unavailable; statement depth varies by issuer. |
| Basic financials | `/stock/metric` | Ratios and summary metrics | Point-in-time metric set; freshness must be disclosed. |
| Earnings history | `/stock/earnings` | Reported earnings evidence | Does not establish future results. |
| Earnings calendar | `/calendar/earnings` | Dated upcoming/recent events | Calendar records may change and require capture dates. |
| Recommendations | `/stock/recommendation` | Aggregated analyst trend | Not an ATLAS recommendation. |
| Price targets | `/stock/price-target` | Licensed target range/consensus | Institution-specific coverage is not assumed. |
| Analyst revisions | `/stock/upgrade-downgrade` | Dated rating actions | Only named/licensed records may be attributed. |
| Company news | `/company-news` | Company-linked context | Relevance, publication time, and source links must validate. |

Commercial website/mobile display and derived display are permitted only when
the retained envelope matches the signed contract identity and marks display
as allowed. Raw machine-readable redistribution is not permitted. Retention is
limited to the contract period, with deletion required on termination. Endpoint
availability, entitlement, quota, and reasonable-use limits must be revalidated
inside a protected acquisition job before any network request.

## Freshness and fallback

- Cache freshness is family-specific; stale retained evidence is labeled
  `STALE_RETAINED`, never freshly acquired.
- Historical OHLCV must be ordered, unique, complete, numerically valid, and
  exchange-finalized before its last close is displayed.
- Backup bundles require an independent-copy assertion, matching lineage hash,
  and valid bundle self-hash. UI metadata continues to identify `BACKUP`.
- Missing or unentitled families are explicit unavailable records. They are not
  silently replaced or inferred.

## Protected acquisition boundary

Before a future acquisition can run, a protected workflow must bind the plan
and its SHA-256 identities to an exact source, entitlement snapshot, request
ceiling, credential, durable raw-first storage, and consume-once authorization.
This release neither registers nor consumes such authority and makes zero
provider calls.
