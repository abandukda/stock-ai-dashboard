# ATLAS Product Recovery Source Coverage

Date: 2026-10-19  
Source baseline: `daae4f0e1033c1456694d1e20dfd2575d9305738`

This inventory separates presentation work from data that must be acquired and
licensed before ATLAS can make a stronger customer claim. Missing evidence is
never replaced with a sector label, a score explanation, or generated prose.

## NVIDIA vertical slice

| Evidence family | Retained, customer-usable state | Presentation rule | Required refresh or acquisition |
|---|---|---|---|
| Certified decision | Available: BUY NOW, certified close, Fair Value, opportunity and confidence | Show the certified close and its session date; never label it current or live | A separately authorized market-data acquisition and certification is required for a newer decision |
| Financial statements | Available: five annual and eight quarterly periods with filing lineage | Show income statement, balance sheet and cash-flow coverage, periods, partial cells and provenance | Normal governed statement refresh when a new filing becomes available |
| Business and revenue model | No renderable verified business-description or revenue-segment payload in the customer bundle | Say that the description is unavailable; use a retained business summary only when its evidence identity is present | Bounded company-profile/filing evidence acquisition with a customer-display license and source timestamp |
| Analyst research | Forward estimate facts are retained; consensus and institution targets are not licensed for customer display | Show only retained field-level estimates and counts; keep Wall Street target module unavailable | Licensed recommendation/target package with institution identity, period, analyst count and commercial-display rights |
| Earnings, news and catalysts | No retained customer-renderable NVIDIA bundle | Render an honest unavailable state; do not infer catalysts from scores | Bounded earnings-calendar and news acquisition with deduplication, timestamps, citations and display rights |
| Price chart | Price evidence identity is retained, but the customer bundle does not embed a validated OHLCV series | Keep the interactive chart unavailable; the certified close remains authoritative | Read-only OHLCV projection containing strictly ordered completed sessions, corporate-action provenance and source digests |
| External AI synthesis | Disabled | Label the deterministic ATLAS explanation accurately | Separate provider, privacy, billing and grounded-output approval |

## Cross-page authority

- Home reads the certified customer publication. It may compact or reorder the
  *presentation* only by the already-published rank; it must not rerank.
- Research reads the same ticker-bound certified evaluation and may add only
  contextual evidence with its own provenance and freshness label.
- Report Card remains customer-disabled. Missing or immature observations stay
  pending; no return is represented as zero.
- The production customer snapshot remains session `2026-10-02`, published
  `2026-10-04T12:21:38-04:00`, with 11 BUY NOW opportunities and publication
  digest `72b37697b2f4fc5dabd5438c1a3bb7c068cd12e86253b64e37b8a642c310bf17`.

## Visual acceptance boundary

The repository does not contain the owner's approved Home, Research and Report
Card mockup images. Governed application screenshots can prove responsive
behavior and source truth, but pixel/visual parity cannot be certified until
those exact references are supplied and included in the comparison artifact.
