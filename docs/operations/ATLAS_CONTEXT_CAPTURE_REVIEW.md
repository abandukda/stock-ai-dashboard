# Retained non-history gateway capture review

Base: `25934c1a12b2256b1459dc78ad25915029ea5a3f`. This is provider-free review
engineering, not licensed acquisition, financial certification, promotion or
publication. It does not widen the gateway allowlist or any workflow privilege.

## Concrete source-to-customer gap

The gateway persisted exact raw bytes and execution receipts, but only candle
responses had a receipt-bound conversion into the customer Research read model.
The separate shadow adapter's normalizer could transform other response shapes,
but constructing/fetching through that adapter was neither required nor allowed
by this slice. News also retained native epoch timestamps and lacked item-level
verified ticker/display attribution, so the actual customer news filter withheld
it even when the enclosing family had display authority.

`build_context_review_from_gateway_capture()` now accepts already-retained raw
bytes, their metadata and complete run receipt. It invokes only the existing
static normalizer, never a provider client constructor, transport or secret.

| Explicit family | Existing gateway and signed-inventory endpoint |
|---|---|
| company_profile | `/stock/profile2` |
| recommendations | `/stock/recommendation` |
| price_targets | `/stock/price-target` |
| earnings_calendar | `/calendar/earnings` |
| company_news | `/company-news` |
| stock_earnings | `/stock/earnings` |
| financial_statements | `/stock/financials-reported` |

The existing candle/adjustment path remains separate. Quote, basic financials,
analyst actions, EPS/revenue estimates and every unknown capability stay rejected
here. Contractual endpoint coverage does not expand registered execution scope.

## Evidence boundaries

- A complete successful run, source/scope SHA, consecutive ordinal, actual attempt
  count, zero retries/redirects, exact selected metadata and raw size/SHA256 must
  agree. Versioned UTC request/run windows reuse the history producer's checks.
  Caller-supplied capture time must match run completion; legacy time-unattested
  receipts remain rejected without modification.
- Family freshness uses its **own response completion**, not a later ancillary
  request/run completion. Both clocks, source/scope/ordinal, exact raw hash and
  separately normalized response hash remain in provenance. This is executor
  clock consistency, not independent clock/provider authenticity certification.
- Duplicate JSON keys, invalid UTF-8, scalar/empty or malformed structures,
  excessive nesting, nonfinite/overflow values and cross-ticker records are
  rejected before a permissive normalizer could discard them. Analyst periods,
  counts, targets and update dates use the shared analyst semantic validator.
  Price Target documents native `lastUpdated` values such as
  `2023-04-06 00:00:00`. Fully valid native calendar/clock strings are bounded
  only by the response capture **day**, retained verbatim as `source_update_value`
  and normalized `last_updated`, and marked timezone-unattested. Their local
  clock is never converted to a UTC source instant; even a later native clock
  on the same day cannot claim precise-instant freshness. ISO date-only values
  remain calendar-only; explicitly timezone-aware values retain instant-bound
  validation. Undocumented ambiguous datetime formats remain rejected.
  Official target shape: https://finnhub.io/docs/api/price-target .
  Financials As Reported separately documents native `endDate` and
  `filedDate` values such as `2019-10-31 00:00:00`. These are fully validated
  calendar/clock strings, bounded by capture **day**, retained verbatim and
  marked timezone-unattested; they are never converted to UTC source instants.
  Official shape reference: https://finnhub.io/docs/api/financials-reported .
  Missing native response identity is not inferred from query alone.
- News native epochs become explicit UTC instants after source identity/date
  validation; original epochs are retained. Display attribution is attached
  only inside the inert review candidate, using the existing contract inventory.
  URLs are validated as HTTPS without user-info and never fetched by conversion.
- The return value is `OWNER_REVIEW_ONLY_NOT_PUBLISHED`. It cannot be installed
  directly as a read-model document. There is no filesystem API, merge/promotion,
  scoring, acquisition or Report Card append in this module. It does not claim
  that every normalized statement field is wired into customer Research.

## Executed provider-free acceptance

Synthetic tests cover all seven supported families, malformed/cross-ticker
records, raw/run/source/scope/hash/ordinal/time inconsistencies, unsupported
capabilities, individual response freshness and a nonfinite normalizer result.
An actual mocked streaming gateway run persists raw metadata/summary, then feeds
this converter and the existing read model; the existing Research projection's
certified price/Fair Value remain unchanged. A separate generated news bundle
reaches actual customer news projection with dated attribution. Test-only nested
bundle extraction is explicit and is not production promotion. No original data,
credential or ledger is read, modified or certified by these fixtures.

Real retained source/backup authority, exact entitlement and acquisition approval,
source certification, independent backups, deployment and authenticated live QA
remain separate. Original Report Card identities and observations are untouched;
public activation stays OFF.
