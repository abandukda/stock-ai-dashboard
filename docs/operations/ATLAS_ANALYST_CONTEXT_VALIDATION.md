# Analyst context meaning and customer projection

Base source: `25934c1a12b2256b1459dc78ad25915029ea5a3f`.
Provider-free code and generated evidence only; no acquisition, promotion,
publication, source/ledger mutation, runtime reload or production activation.

## Actual baseline failures

The current reader checked family hashes, provenance and commercial display
mapping but did not validate normalized recommendation count semantics. Actual
customer projection with generated count `"unknown"` raised `ValueError` at
`int(...)`, including before the Wall Street display gate. A valid all-zero
period produced `analyst_count=0` and a misleading `Strong Buy` consensus because
`max` selected the first zero-count category. Both baseline behaviors were
executed against the pristine base source with network denied.

## Resulting boundary

The pure `ATLAS_NORMALIZED_ANALYST_CONTEXT_V1` helper validates recommendations
and price targets before retained admission and again at customer projection
(including explicit QA/injected enrichment). It performs no I/O or coercion.

- All five recommendation counts must be actual nonnegative integers, not
  booleans, numeric strings, fractions, absent fields or nonfinite values.
  Each count and its aggregate must fit the exact JSON/JavaScript integer
  interval `0..2**53-1`. Larger values are withheld, never clipped or rounded;
  this is a serialization safeguard, not a financial coverage assumption.
- Recommendation periods are real ISO dates, unique and strictly descending;
  supplied ticker/symbol identities match the requested company. A source date
  cannot postdate its recorded capture or the current check time.
- Supplied targets are finite positive numbers with consistent ranges. Missing
  targets remain missing; no average or median is invented. A valid source
  update date is required; partial targets can remain contextual evidence.
  The documented native `YYYY-MM-DD HH:MM:SS` target clock is fully validated
  but timezone-unattested: only its calendar date is compared with the individual
  response capture date. It is preserved verbatim, never assigned UTC. Date-only
  updates retain calendar precision; offset-aware updates retain exact-instant
  checks. A native clock later on the same day is not represented as a future
  UTC instant. Invalid clocks and future source days remain rejected.
- A malformed family is withheld without discarding independently valid
  families. Read-only admission receipts add fixed-code `family_rejections`;
  provider payloads, values and private paths never enter those rejection codes.
- A known zero analyst count stays zero, but consensus is absent and reason
  `NO_ANALYST_COVERAGE`. Valid price targets remain independently visible.
- Display remains disabled by default. Its reason is now
  `CONTEXT_DISPLAY_NOT_ENABLED`, distinguishing configuration from the signed
  contract's permitted commercial display. This does not enable the flag.

Certified price, ATLAS Fair Value, decision/scoring authority, source hashes,
retained stale-date disclosures and Report Card gates are unchanged. The helper
is normalized-context validation, not certification of provider truth, source
host/backup authority, publication or execution approval. Root-provided browser
and exact-head CI evidence must be attached separately; fixture success is not
production acceptance.
