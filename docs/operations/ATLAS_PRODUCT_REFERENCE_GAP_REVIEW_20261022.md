# Product reference and production gap review — October 22, 2026

## Authority and limits

Current inspected source: `da55afc86056fbf1c0bca1f8e5538208ee477187`.
Authenticated production run **39821816991**, customer job **119974763064**.
Artifact **12444594784**, 13,160,894 bytes, SHA-256
`95bde6f9644634b3b7167c2452fe49a142579cea2f6c689eb1cc68cfcb830331` was downloaded and verified.
Authentication succeeded; the required NVDA four-panel chart failed. Source identity,
authentication, financial authority and chart admission are separate gates.
The summary reports 34/36 required checks passed, 2 failed, and 27/27 screenshots.
This is **FAIL**, not 94% product acceptance: required journeys remain incomplete.
Mobile/tablet captures explicitly carry `diagnostic-only-not-acceptance`.

Recovered originals were inspected from the existing reference pack: primary Home/Research/Report Card concept,
two Research compositions, and original Report Card. Illustrative figures are not financial authority.
The complete text of three actual consultant source documents was read, rather than substituting repository inventories:

- `ATLAS Design and UX Review (09ff6be).docx` (October 18): original recovered pack.
- `ATLAS Premium R2 Review (59834a4).docx` (October 14): recovered original, Library ID `libfile_caf3f04357e4819197db998aeb47c166`.
- `ATLAS R2 Acceptance Review (368f5ed)(1).docx` (October 12): recovered original, Library ID `libfile_94e6dfd95f888191966eff73bb4096eb`.

`Project Atlas Issues.docx` complete 25-page extracted text was also read (Library ID
`libfile_9b0405599510819199c7624c614fb3f0`). Its embedded historical screenshots were not all re-reviewed this session.
These are the identified recovered critiques, not proof that no further consultant correspondence exists.
Their scores are historical, frozen-SHA, screenshot-based judgments; they do not certify current production.
Standalone Robinhood references and the separately annotated technical chart remain unconfirmed; do not claim parity.

## Direct comparison and executable acceptance

| Requirement / source | Actual da55 production evidence | Current status / next acceptance |
|---|---|---|
| Original Home command-center hierarchy | Desktop Home and diagnostic 360/768 renders exist; dated lead idea and Top Ideas are visible. Market context is unavailable. | Built/merged/deployed existing layout; premium parity OPEN. No invented market readings. Recheck distinct ideas above fold after integrated release. |
| Research company header and verdict first | Actual desktop NVDA/MSFT full reports and NVDA first-screen frame exist. Existing source-backed digest is an intermediate capability. | Rendered evidence exists; full Research acceptance OPEN. No genuine external AI claim. |
| Research chart, volume, RSI/MACD and benchmark | Required NVDA check reports `four_panels=False; actual_chart_screenshot=False`. | FAIL. Loaded/admitted history is missing; successful authentication is not a remedy. Retained source admission work remains independent. Assertions stay unchanged. |
| Original module navigation | Long actual Research captures: 12,767px at 360; 10,090px at 768. Five old links omit direct statements/earnings/company/news destinations. | Provider-free review-branch repair adds nine accessible module links with named anchors and honest pending bodies. Must pass real browser and production QA before acceptance. |
| Full financial depth, statements and availability consistency (Claude T-1, W1/W5) | Statement sections are below summary; raw white table islands remain visible on dark page. | Partial; do not infer complete financial reconciliation from visual presence. Field/period authority tests and source certification required separately. |
| Cohesive dark palette and controls (Claude E-11/W9) | Dark cards improved; white table islands remain; some default control styling remains. | Material visual gap OPEN. No visual-completion claim. |
| Company-specific catalysts and risk explanations (Claude T-6/W2) | Missing evidence is disclosed; source-grounded narrative remains limited. | Partial; no fabricated business drivers. Require per-ticker dated evidence on NVDA/MSFT/META/ANET. |
| Simple/Detailed authority and AI meaning | Both modes are implemented; deterministic explanation does not establish genuine AI capability. | Independent UI, certified-current-data, grounded-AI gates remain OPEN. |
| Report Card original premium dashboard (Claude W8) | Current customer run does not certify private Report Card; public OFF is preserved. | No live verification claim. Protected private QA, immutable original 20 signals, valid timing/entry/SPY and zero-observation audit remain separate gates. |
| Watchlist persistence and role separation (owner issues; Claude E-9) | This failed run did not complete Watchlist journeys. | Beta candidate must pass add/remove/persistence/account-isolation and actual customer screenshots independently. |
| All responsive journeys and evidence quality (Claude T-7/T-8/W10) | Actual 360/768 diagnostics are genuine renders, explicitly not completed acceptance. | OPEN. Require desktop/tablet/mobile full journeys and distinct content-bearing screenshots on exact deployed release. |
| Beginner comprehension (Claude P1-18) | No five-person study evidence recovered. | Owner/user-research dependency; no invented comprehension score. |

## Review-branch change and test receipt

Presentation-only change: a single nine-section navigation component, minimum 44px link targets,
keyboard-visible focus, scroll offsets, unique anchors for news/statements/earnings/company,
and visible honest empty states where those linked sections lack data. The missing-chart copy
now says history has not been loaded, avoiding an unsupported claim that the commercial license forbids display.
No financial calculations, ticker ownership, provider access, chart acceptance assertions, or public Report Card controls change.

Offline regression: **85 passed + 8 subtests passed** using section navigation, customer Research,
Research learning and chart integration tests. `git diff --check` passed.
Real Playwright component regression is added for **360/768/1440**, keyboard traversal,
minimum target size, no document overflow and functional anchor scrolling. It has not run locally
because Chromium is absent. Hosted CI should install its existing pinned Chromium and run:

```sh
python -m unittest discover -s tests -p test_research_section_navigation_browser.py -v
```

Save `audit_results/research_section_navigation/GENERATED_SECTION_NAV_*.png` as CI artifacts.
Those are generated component screenshots, never production acceptance or evidence of financial correctness.

| Stage | Navigation candidate |
|---|---|
| BUILT | Yes, bounded review branch |
| TESTED | Offline pass; actual browser regression pending hosted CI |
| MERGED | No |
| DEPLOYED | No |
| LIVE VERIFIED | No |

Approval and release remain coordinator-owned. Required outcome: exact-head governed CI, owner-approved merge,
expected deployed SHA, authenticated full production journeys, before/after screenshot inspection,
no material unresolved discrepancy falsely classified as accepted.
