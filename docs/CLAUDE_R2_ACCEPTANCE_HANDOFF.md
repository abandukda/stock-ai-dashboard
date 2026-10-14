# Claude R2 acceptance handoff

## Candidate identity

- Repository: `abandukda/stock-ai-dashboard`
- Branch: `codex/premium-r2-complete-customer-product`
- Candidate SHA: `934a06a4ba0d9cb691a627678762f985aff44fbd`
- Governed QA run: `38292622116`
- Governed workflow result: `PASS`
- Required customer assertions: `118/118 PASS`
- Required screenshots: `167/167`
- Supplementary findings: `26/36 PASS`; 10 non-blocking failures remain across the legacy Earnings Intelligence, Full Ranked Scan and Recovery surfaces
- Evidence artifact: `11767750308`
- Uploaded artifact SHA-256: `3dddf698d8fcbcc830a1a58b83f578f460d0014a24e97482e0e08688027bd914`
- Production: unchanged

## Independent review contract

Review this candidate critically against the approved Premium R2 requirements. Automated checks are evidence of contract conformance, not proof of premium visual quality. Do not award a 10/10 result unless the original-resolution customer screenshots independently justify it.

Evaluate:

1. Desktop and mobile first-screen hierarchy.
2. Home opportunity discovery before secondary context.
3. Five-section Research completeness and information density.
4. Exact numerical consistency for Action, Fair Value, Opportunity, Confidence, six pillars, charts, Research and Ask.
5. Retained financial evidence depth, units, fiscal periods, dates, provenance and honest unavailable states.
6. Ticker-specific investment reasoning and conceptual accuracy.
7. Price, SPY, technical, valuation and financial-chart readability.
8. Personal Watchlist behavior, persistence and unsupported-security handling.
9. Customer/admin isolation, sparse-data states, CRC withholding and absence of internal language.
10. Comparison with premium investor products without assuming feature parity from headings alone.

For every finding provide severity (`P0`, `P1`, `P2`), screenshot/page reference, expected behavior, actual behavior, category (data/UI/functionality/methodology restriction), and a concrete recommendation.

## Engineering changes under review

- Added a read-only shared customer Research view used by Research and Ask.
- Made the Watchlist personal and editable; missing prices never render as `$0.00`.
- Preserved unsupported saved symbols with explicit security-type states.
- Added deterministic certified-close freshness states and dated warnings.
- Projected retained field-level financial evidence only when exact lineage exists.
- Split financial charts by compatible units.
- Prioritized retained ticker-specific financial facts in the investment brief.
- Reordered Home so certified Action Summary and opportunities precede secondary market context.
- Improved chart legends, Fair Value labels and Confidence formatting.

## Known evidence limitations

- Multi-period financial series remain unavailable when the retained certified bundle has only a latest-period value. No history was fabricated.
- “Live” legacy copy remains in non-primary legacy renderers and is tracked as D-23 until browser routing proves it unreachable or it is removed.
- D-01 through D-23 are not closed merely because implementation exists; see the closure matrix for proof state.
- The governed run and its real screenshots are the controlling visual evidence. If they fail or omit a required state, acceptance is blocked.
- The exact-SHA required suite is green, but the independent premium-design score is intentionally unclaimed. The supplementary findings and D-01–D-23 matrix must be considered in any acceptance decision.

## Independent acceptance question

Does this exact candidate provide a coherent premium investor experience, with trustworthy evidence hierarchy and responsive behavior, strongly enough to merit a 10/10 visual acceptance score? If not, identify each shortfall by page and original screenshot filename, severity, expected versus actual behavior, and whether it is a data, UI, functionality, or methodology limitation.
