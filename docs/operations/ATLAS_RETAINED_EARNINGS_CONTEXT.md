# Retained reported EPS context

`build_retained_earnings_context` projects only an already admitted retained
`stock_earnings` family. Its contract is
`ATLAS_RETAINED_REPORTED_EPS_CONTEXT_V1`; the customer page key is
`retained_reported_earnings`. This pure function performs no acquisition,
refresh, file write, scoring, publication or ledger operation.

All source rows must pass ticker, period, numeric and capture checks before any
of the newest eight periods are displayed. Zero and negative EPS are valid;
missing actual/estimate stays missing. A malformed row withholds the entire
family. Source lineage includes the retained raw evidence ID/hash, own-family
capture time, read-model source SHA, bundle ID and record hash. Serving later
cannot admit a period after the original response capture date.

The display presents actual and estimate independently. Their currency,
basic/diluted basis, adjustments and frequency remain unverified. Period end
is not an announcement or publication date. No quarter/year inference,
surprise/beat arithmetic, earnings rating, transcript availability or external
AI analysis is derived. Retained evidence does not prove the latest release.
Generic reported financial statements remain behind the existing independent
G6 annual-financial admission gates.

Tests use generated capture bytes and a temporary, explicitly assembled
review fixture. They demonstrate converter → retained reader → EPS projection
without representing fixture values as market evidence. Production acceptance
still requires governed evidence admission and actual rendered/live QA.
