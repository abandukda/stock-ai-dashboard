# Premium R2 supplementary finding review

## Evidence identity

- Governed run: `38448142193`
- Exact tested SHA: `8e4c465bf3ad2d65ae4557a02670448b73f40936`
- Artifact: `atlas-customer-experience-qa-8e4c465bf3ad2d65ae4557a02670448b73f40936`
- Artifact ID: `11839947327`
- Artifact digest: `sha256:44521bd220d39cd75abcb993d70ae2246f11e178055ac6fdc71bff2498a59d1d`
- Required customer QA: `144/144 PASS`
- Required screenshots: `178/178`
- Provider calls: `0`

The ten findings below came only from the explicitly non-blocking supplementary
pass. No finding is an active customer-route defect.

## Classification of all ten findings

| # | Viewport | Finding | Classification | Current-route and rendered evidence |
|---|---|---|---|---|
| 1 | Desktop | Earnings navigation | Retired route | `services/customer_navigation_contract.py` registers exactly Home, Research, Watchlist, and Ask ATLAS. `app.py` does not add Earnings to `internal_pages`. The stale supplementary inventory still requests `Earnings Intelligence`. Screenshot: `browser/supplementary/screenshots/0004_internal_admin_desktop_Earnings_Intelligence_page_rendered.png`. |
| 2 | Desktop | Earnings VNext story | Obsolete test contract | Derivative of #1: the crawler evaluated an unselected retired route. Screenshot: `browser/supplementary/screenshots/0005_internal_admin_desktop_Earnings_Intelligence_vnext-contract_evidence.png`. |
| 3 | Desktop | Full Scan high-evidence archetype | Obsolete data-contingent test contract | Internal-only Full Scan rendered all 36 persisted rows, ordered ranks, filtered positions, partial-evidence state, authority separation, and visible content. It failed solely because the retained population contained no row satisfying the crawler's synthetic `high` archetype. Screenshot: `browser/supplementary/screenshots/0007_internal_admin_desktop_Full_Ranked_Scan_vnext-contract_evidence.png`. |
| 4 | Desktop | Recovery populated story | Obsolete data-contingent test contract | Internal-only Recovery rendered its governed empty state; `ui/recovery_vnext.py` explicitly treats no persisted candidates as valid and emits PAGE_INTERACTIVE. The crawler incorrectly required twelve populated sections, a ticker, and CTA. Screenshot: `browser/supplementary/screenshots/0029_internal_admin_desktop_Recovery_vnext-contract_evidence.png`. |
| 5 | Desktop | Recovery journey timeout | Derivative obsolete contract | Candidate traversal followed #4 even though no candidates existed. No customer route was involved and no rendered exception was reported. |
| 6 | Mobile 390 | Earnings navigation | Retired route | Mobile duplicate of #1. Screenshot: `browser/supplementary/screenshots/0086_internal_admin_mobile_Earnings_Intelligence_page_rendered.png`. |
| 7 | Mobile 390 | Earnings VNext story | Obsolete test contract | Mobile derivative of #6. Screenshot: `browser/supplementary/screenshots/0087_internal_admin_mobile_Earnings_Intelligence_vnext-contract_evidence.png`. |
| 8 | Mobile 390 | Full Scan high-evidence archetype | Obsolete data-contingent test contract | Mobile duplicate of #3; all 36 rows and authority/rank assertions passed. Screenshot: `browser/supplementary/screenshots/0089_internal_admin_mobile_Full_Ranked_Scan_vnext-contract_evidence.png`. |
| 9 | Mobile 390 | Recovery populated story | Obsolete data-contingent test contract | Mobile duplicate of #4. Screenshot: `browser/supplementary/screenshots/0104_internal_admin_mobile_Recovery_vnext-contract_evidence.png`. |
| 10 | Mobile 390 | Recovery journey timeout | Derivative obsolete contract | Mobile duplicate of #5. No customer route or rendered application exception was implicated. |

Historical inventory evidence explains the mismatch: `agents/product_hardening_certification.py`
still carries the pre-consolidation `Earnings Intelligence` page in `ACTIVE_PAGES`, while
the registered current navigation authority is `CUSTOMER_NAV_CONTRACT_VERSION =
"ATLAS_CUSTOMER_NAV_R1_1"` with the four routes above. This review does not change
either contract because the requested task forbids weakening QA after the safety rejection.

## Requested customer evidence inventory

### Present

- **Summary 101 / first-screen decision context:** 8 customer-viewer frames. Representative files:
  - `0100_customer_viewer_desktop_Research_Any_Ticker_first-screen-NVDA_scroll-zero.png`
  - `0131_customer_viewer_mobile_Research_Any_Ticker_first-screen-NVDA_scroll-zero.png`
  - `0162_customer_viewer_mobile_360_Research_Any_Ticker_first-screen-NVDA_scroll-zero.png`
- **Financial/fundamental evidence:** 5 customer-viewer focused frames (NVDA/AVT across desktop and 390, plus NVDA at 360). Representative files:
  - `0106_customer_viewer_desktop_Research_Any_Ticker_v2-NVDA-fundamentals_visible.png`
  - `0137_customer_viewer_mobile_Research_Any_Ticker_v2-NVDA-fundamentals_visible.png`
  - `0168_customer_viewer_mobile_360_Research_Any_Ticker_v2-NVDA-fundamentals_visible.png`
- **Certified charts:** 10 focused six-pillar and Wall Street/valuation frames, plus full stitched Research captures. Representative files:
  - `0103_customer_viewer_desktop_Research_Any_Ticker_v2-NVDA-six-pillars_visible.png`
  - `0104_customer_viewer_desktop_Research_Any_Ticker_v2-NVDA-wall-street_visible.png`
  - `0165_customer_viewer_mobile_360_Research_Any_Ticker_v2-NVDA-six-pillars_visible.png`
  - `0166_customer_viewer_mobile_360_Research_Any_Ticker_v2-NVDA-wall-street_visible.png`
- **Populated Watchlist:** 3 customer-role viewport frames, including:
  - `0123_customer_viewer_desktop_Watchlist_Intelligence_customer-role-evidence_visible.png`
  - `0154_customer_viewer_mobile_Watchlist_Intelligence_customer-role-evidence_visible.png`
  - `0175_customer_viewer_mobile_360_Watchlist_Intelligence_customer-role-evidence_visible.png`
- **Grounded Ask:** 3 completed customer-role answer frames:
  - `0126_customer_viewer_desktop_Ask_AI_grounded-question_answer-and-evidence.png`
  - `0157_customer_viewer_mobile_Ask_AI_grounded-question_answer-and-evidence.png`
  - `0178_customer_viewer_mobile_360_Ask_AI_grounded-question_answer-and-evidence.png`
- **390px customer navigation:** Home, Research, Watchlist, and Ask all have rendered and interaction frames; 31 customer-viewer frames total at the governed `mobile` viewport.
- **360px customer navigation:** Home, Research, Watchlist, and Ask all have rendered and interaction frames; 21 customer-viewer frames total at `mobile_360`.

### Absent as dedicated focused frames

- No screenshot interaction is named specifically `financial-statements`; the financial statement/detail content is contained in full stitched Research captures and the focused `fundamentals` frames.
- No screenshot interaction is named specifically `summary-101`; its disclosure is present in the Research rendering, while the focused proxy is `first-screen-*`.
- No dedicated screenshot interactions separately isolate price/SPY, technical-indicator, and financial-trend charts. They are contained in stitched Research captures, while the manifest provides focused six-pillar and Wall Street/valuation chart frames.

These are screenshot-granularity gaps, not proof that the underlying features are absent.
They require a future explicitly authorized crawler-evidence enhancement if separately
framed images are mandatory.

## Protected state

No product code, crawler contract, provider behavior, production data, ledger state,
investment methodology, deployment, or workflow execution was changed by this review.

