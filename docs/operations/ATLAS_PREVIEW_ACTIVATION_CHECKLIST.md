# ATLAS access-controlled preview activation checklist

This checklist creates a second Streamlit app for owner review. It must never
replace or reconfigure the customer production application.

## Owner-controlled setup

1. Sign in to Streamlit Community Cloud with the authorized GitHub account.
2. Create a **new private preview app** from repository
   `abandukda/stock-ai-dashboard`, branch
   `codex/weekend-report-card-automation`, entrypoint `app.py`.
3. Record the generated preview URL; do not reuse the production URL.
4. Configure distinct preview-only `APP_PASSWORD`, `ATLAS_AUDIT_PASSWORD`,
   `ATLAS_INTERNAL_QA_PASSWORD`, and `ATLAS_VIEWER_QA_PASSWORD` values.
5. Bind `ATLAS_SOURCE_SHA` and `ATLAS_BUILD_SHA` to the exact reviewed PR head,
   and set `ATLAS_DEPLOY_BRANCH=codex/weekend-report-card-automation`.
6. Keep `ATLAS_CUSTOMER_REPORT_CARD_ENABLED=false`,
   `ATLAS_REPORT_CARD_CUSTOMER_VISIBLE=false`, live acquisition/publication
   flags false, and all unattended-operation flags false.
7. Do not install Finnhub or external-model credentials in the preview. Use
   retained evidence already permitted for display; unavailable context must
   stay visibly unavailable.

## Required verification before acceptance

- Running source marker equals the exact reviewed PR head.
- Production source marker and customer snapshot remain unchanged.
- Customer/admin role isolation passes.
- Home, BUY NOW, Research, Charts, Report Card, Recovery Radar, ETF Analysis,
  and Watchlist show their `ATLAS_EXPLAINS_V1` contract.
- Each explanation exposes a 30-second takeaway, Simple View, Detailed View,
  evidence date, non-scoring marker, and external-model-inactive disclosure.
- Original-resolution screenshots pass at 1440, 1024, 390, and 360 pixels.
- Browser console errors, provider calls, publication writes, and Report Card
  ledger mutations are all zero.
- Material navigation, contrast, overflow, keyboard, and source-date defects
  are corrected and recertified before promotion is recommended.

## Promotion boundary

A successful preview is review evidence only. Merging PR #71 and promoting its
exact resulting source to production each require their own owner authorization.
