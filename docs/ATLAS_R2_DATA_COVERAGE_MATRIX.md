# ATLAS Premium R2 data coverage contract

The shared customer view reports evidence availability separately from investment authority. Absence is never converted to zero and external context cannot alter certified Action, Fair Value, Opportunity, Confidence, pillars, or publication eligibility.

| Dataset | Customer state | Authority | UI rule |
|---|---|---|---|
| Certified publication | `CERTIFIED_CURRENT` or `PUBLICATION_WITHHELD` | Persisted certified customer evaluation | Withheld pages render no decision metrics |
| Certified close | `CERTIFIED_CURRENT`, `CERTIFIED_DATED`, or `MISSING_RETAINED_EVIDENCE` | Certified field envelope | Dated evidence receives an explicit warning |
| Analyst context | `EXTERNAL_CONTEXT` or `MISSING_RETAINED_EVIDENCE` | Retained licensed context | Must be labeled context, never authority |
| News | `EXTERNAL_CONTEXT` or `MISSING_RETAINED_EVIDENCE` | Retained licensed context | Missing news yields an honest empty state |
| Earnings | `EXTERNAL_CONTEXT` or `MISSING_RETAINED_EVIDENCE` | Retained licensed context | Only retained future catalysts may render |
| Financial snapshot | available per field or unavailable | Retained professional evidence lineage | Each displayed value requires an exact evidence ID, fiscal period/as-of date, unit, and provider |
| Financial history | available or unavailable | Provenance-bearing multi-period retained series | Period/value lengths must match; currencies, per-share values, and percentages render separately |
| Saved security identity | supported type or explanatory unsupported state | Security master / retained row | Saved symbols remain owned; no fabricated profile |
| Price/SPY history | available with provenance or unavailable | Retained certified series | No provider retrieval and no fabricated series |

## Fail-closed rules

1. No customer route may recompute protected investment values.
2. Missing/nonpositive prices render `Unavailable`, never `$0.00`.
3. A saved symbol absent from the current universe remains saved with an explanatory state.
4. A withheld publication cannot expose Action, Fair Value, Opportunity, Confidence, or pillars.
5. A governed browser PASS requires component, lifecycle, ticker, authority, role, and viewport predicates together.
