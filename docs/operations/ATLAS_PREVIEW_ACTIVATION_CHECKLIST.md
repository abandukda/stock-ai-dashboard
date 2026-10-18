# ATLAS access-controlled preview activation checklist

This checklist creates a second Streamlit app for owner review. It must never
replace or reconfigure the customer production application.

## Owner-controlled setup

1. Sign in to Streamlit Community Cloud with the authorized GitHub account.
2. Create a dedicated immutable deploy branch, for example
   `codex/preview-milestone3-0758fac`, pointing exactly to merge commit
   `0758fac72209ab0642e9f1a431db092d1a699119`. Do not advance this branch during
   acceptance. Streamlit Community Cloud deploys branches rather than pinning a
   commit directly.
3. Create a **new private preview app** from repository
   `abandukda/stock-ai-dashboard`, branch
   `codex/preview-milestone3-0758fac`, entrypoint `app.py`.
4. Record the generated preview URL; do not reuse the production URL.
5. Configure distinct preview-only `APP_PASSWORD` (admin) and
   `GUEST_PASSWORD` or `VIEWER_PASSWORD` (customer/viewer) values. The hosted
   login reads these names; `ATLAS_VIEWER_QA_PASSWORD` alone does not create a
   viewer login. `ATLAS_AUDIT_PASSWORD` and `ATLAS_INTERNAL_QA_PASSWORD` may be
   added for QA tooling but do not replace the application login secrets. Both
   roles must be exercised. If neither an admin nor viewer password is present,
   the current application auto-authenticates as admin, which is unacceptable
   for a hosted preview.
   Set `ATLAS_REQUIRE_AUTH=true`; this makes the preview fail closed if the
   required passwords are absent or misconfigured.
6. Bind `ATLAS_SOURCE_SHA` and `ATLAS_BUILD_SHA` to
   `0758fac72209ab0642e9f1a431db092d1a699119`, and set
   `ATLAS_DEPLOY_BRANCH=codex/preview-milestone3-0758fac`.
7. Keep `ATLAS_CUSTOMER_REPORT_CARD_ENABLED=false`,
   `ATLAS_REPORT_CARD_CUSTOMER_VISIBLE=false`, live acquisition/publication
   flags false, and all unattended-operation flags false.
8. Do not install Finnhub or external-model credentials in the preview. Use
   retained evidence already permitted for display; unavailable context must
   stay visibly unavailable.
9. Set `ATLAS_RESEARCH_MARKET_CACHE_DIR` only to the preview's read-only,
   permitted retained-data location. If no permitted cache is installed, omit
   it and accept the explicit unavailable state. Never mount production raw or
   checkpoint storage into the preview.
10. Pin Python 3.11 and deploy from the immutable
   candidate commit, not a moving branch after acceptance begins.

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

A successful preview is review evidence only. Merging the consolidated release
candidate and promoting its exact resulting source to production each require
their own owner authorization.
