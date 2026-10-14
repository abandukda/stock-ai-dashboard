# ATLAS R2 Retained Data Coverage

Source: `/private/tmp/atlas-exact-shards-37216506983`  
Retained security records inspected: **6,033**
Expected source population: **6,033**
Population completeness: **COMPLETE**
Provider calls: **0**

This audit counts values already retained in the customer publication. A value is called certified here only when its field-level evidence identity is also present. It does not treat QA enrichment as production authority.

## Financial fields

| Field | Value rows | Evidence-bound rows | Period-bound rows | Coverage | Retained period examples |
|---|---:|---:|---:|---:|---|
| latest_revenue | 2,885 | 0 | 0 | 0.00% | None |
| net_income | 3,805 | 0 | 0 | 0.00% | None |
| operating_cash_flow | 3,723 | 0 | 0 | 0.00% | None |
| free_cash_flow | 3,037 | 3,037 | 3,850 | 50.34% | 2012-12-31 00:00:00, 2021-12-31 00:00:00, 2024-12-31 00:00:00, 2025-06-30 00:00:00, 2025-09-27 00:00:00, 2025-10-31 00:00:00, 2025-12-31 00:00:00, 2026-01-03 00:00:00 |
| capex | 3,105 | 0 | 0 | 0.00% | None |
| capital_expenditures | 3,105 | 0 | 0 | 0.00% | None |
| cash_and_equivalents | 3,412 | 3,412 | 3,412 | 56.56% | 2012-12-31 00:00:00, 2021-12-31 00:00:00, 2024-12-31 00:00:00, 2025-06-30 00:00:00, 2025-09-27 00:00:00, 2025-10-31 00:00:00, 2025-12-31 00:00:00, 2026-01-03 00:00:00 |
| total_debt | 1,964 | 1,964 | 1,964 | 32.55% | 2021-12-31 00:00:00, 2024-12-31 00:00:00, 2025-09-27 00:00:00, 2025-09-30 00:00:00, 2025-10-31 00:00:00, 2025-12-31 00:00:00, 2026-01-03 00:00:00, 2026-02-28 00:00:00 |
| forward_eps | 3,377 | 3,377 | 3,377 | 55.98% | 2026-12-31, 2027-03-31, 2027-06-30, 2027-09-30, 2027-12-31 |
| forward_ebitda | 2,809 | 2,809 | 2,809 | 46.56% | 2026-12-31, 2027-03-31, 2027-06-30, 2027-09-30, 2027-12-31, 2028-12-31 |
| revenue_growth_pct | 3,328 | 0 | 0 | 0.00% | None |
| gross_margin_pct | 2,927 | 0 | 0 | 0.00% | None |
| operating_margin_pct | 3,520 | 0 | 0 | 0.00% | None |
| net_margin_pct | 3,527 | 0 | 0 | 0.00% | None |
| net_debt_to_ebitda | 0 | 0 | 0 | 0.00% | None |

## Other retained identities

- Price History Identity: 3,850 of 6,033
- Forward Estimates: 3,850 of 6,033
- Company Name: 3,849 of 6,033
- Sector: 3,850 of 6,033
- Industry: 3,850 of 6,033
- Security Type: 3,850 of 6,033

## Conservation and terminal rows

- Rows: 2,183 terminal + 3,850 nonterminal = 6,033
- Field cells: 90,495 classified = 90,495 expected
- Terminal retained rows: 2,183, classified as `TERMINAL_BLOCKED_RETAINED_ROW`
- Terminal blocker combinations:
  - 1,059: LATEST_FY_FINANCIAL_REPORT_MISSING
  - 362: LATEST_FY_FINANCIAL_REPORT_MISSING, COMPLETED_TECHNICAL_HISTORY_INSUFFICIENT
  - 267: LATEST_FY_FINANCIAL_REPORT_MISSING, COMPLETED_TECHNICAL_HISTORY_INSUFFICIENT, GOVERNED_CLASSIFICATION_UNRESOLVED
  - 223: COMPLETED_TECHNICAL_HISTORY_INSUFFICIENT, GOVERNED_CLASSIFICATION_UNRESOLVED
  - 214: COMPLETED_TECHNICAL_HISTORY_INSUFFICIENT
  - 39: GOVERNED_CLASSIFICATION_UNRESOLVED
  - 18: LATEST_FY_FINANCIAL_REPORT_MISSING, GOVERNED_CLASSIFICATION_UNRESOLVED
  - 1: HISTORICAL_OHLCV_NOT_CANONICAL_CERTIFIED, COMPLETED_TECHNICAL_HISTORY_INSUFFICIENT

## Decision

The customer publication retains latest-period financial evidence where the field rows above prove a value, period and evidence identity. This audit does not claim complete annual or quarterly depth when the accessible source population is partial. Existing evidence-bound facts and explicitly retained series may be projected now; missing periods must remain Not reported.

SPY history, analyst modules, earnings calendars, and licensed news used in governed QA reside in a QA-scoped contextual bundle and are not production authority. They must not be promoted to customer production merely because the QA bundle contains them.
