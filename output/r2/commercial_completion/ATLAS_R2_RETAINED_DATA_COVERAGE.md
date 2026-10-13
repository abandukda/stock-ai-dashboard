# ATLAS R2 Retained Data Coverage

Source: `market_full_scan.json`  
Customer-published records inspected: **35**  
Provider calls: **0**

This audit counts values already retained in the customer publication. A value is called certified here only when its field-level evidence identity is also present. It does not treat QA enrichment as production authority.

## Financial fields

| Field | Value rows | Evidence-bound rows | Period-bound rows | Coverage | Retained period examples |
|---|---:|---:|---:|---:|---|
| latest_revenue | 17 | 0 | 0 | 0.00% | None |
| net_income | 21 | 0 | 0 | 0.00% | None |
| operating_cash_flow | 21 | 0 | 0 | 0.00% | None |
| free_cash_flow | 20 | 20 | 21 | 57.14% | 2024-12-31 00:00:00, 2025-06-28 00:00:00, 2025-06-30 00:00:00, 2025-07-26 00:00:00, 2025-09-27 00:00:00, 2025-10-31 00:00:00, 2025-12-31 00:00:00, 2026-01-03 00:00:00 |
| capex | 20 | 0 | 0 | 0.00% | None |
| capital_expenditures | 20 | 0 | 0 | 0.00% | None |
| cash_and_equivalents | 20 | 20 | 20 | 57.14% | 2024-12-31 00:00:00, 2025-06-28 00:00:00, 2025-06-30 00:00:00, 2025-07-26 00:00:00, 2025-09-27 00:00:00, 2025-10-31 00:00:00, 2025-12-31 00:00:00, 2026-01-03 00:00:00 |
| total_debt | 13 | 13 | 13 | 37.14% | 2025-06-28 00:00:00, 2025-06-30 00:00:00, 2025-07-26 00:00:00, 2025-09-27 00:00:00, 2025-10-31 00:00:00, 2025-12-31 00:00:00, 2026-01-03 00:00:00, 2026-01-25 00:00:00 |
| forward_eps | 20 | 20 | 20 | 57.14% | 2026-12-31, 2027-03-31, 2027-06-30, 2027-09-30 |
| forward_ebitda | 20 | 20 | 20 | 57.14% | 2026-12-31, 2027-03-31, 2027-06-30, 2027-09-30 |
| revenue_growth_pct | 20 | 0 | 0 | 0.00% | None |
| gross_margin_pct | 18 | 0 | 0 | 0.00% | None |
| operating_margin_pct | 20 | 0 | 0 | 0.00% | None |
| net_margin_pct | 20 | 0 | 0 | 0.00% | None |
| net_debt_to_ebitda | 0 | 0 | 0 | 0.00% | None |

## Other retained identities

- Price History Identity: 21 of 35
- Forward Estimates: 21 of 35
- Company Name: 21 of 35
- Sector: 21 of 35
- Industry: 21 of 35
- Security Type: 21 of 35

## Decision

The customer publication retains broad latest-period financial coverage with field-level evidence, but it does not contain complete annual and quarterly statement tables. Multi-period statement acquisition is therefore not authorized by this audit. The existing latest-period facts and any explicitly retained historical series may be projected now; missing periods must remain Not reported.

SPY history, analyst modules, earnings calendars, and licensed news used in governed QA reside in a QA-scoped contextual bundle and are not production authority. They must not be promoted to customer production merely because the QA bundle contains them.
