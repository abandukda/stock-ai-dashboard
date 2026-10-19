# ATLAS access-controlled preview activation checklist

This checklist creates a second Streamlit app for owner review. It must never
replace or reconfigure the customer production application.

Before use, replace `<REVIEWED_SHA>` and `<IMMUTABLE_PREVIEW_BRANCH>` with the
exact reviewed candidate identities. Record both values in the visual-review
manifest. Never infer them from `main`, a PR number, or a successful CI run.

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
11. Confirm the preview secrets inventory contains no Finnhub key, external-AI
   key, publication credential, Report Card mutation authority, runner SSH key,
   or production storage path. Record secret *names and presence only*; never
   export values into logs or artifacts.
12. Before browser QA, observe the hosted `ATLAS_SOURCE_SHA` marker and require
   exact equality with `<REVIEWED_SHA>`. A branch configuration page is not
   runtime identity evidence.

## Required verification before acceptance

- Running source marker equals the exact reviewed PR head.
- Production source marker and customer snapshot remain unchanged.
- Customer/admin role isolation passes.
- Home, BUY NOW, Research, Charts, Report Card, Recovery Radar, ETF Analysis,
  and Watchlist show their `ATLAS_EXPLAINS_V1` contract.
- Each explanation exposes a 30-second takeaway, Simple View, Detailed View,
  evidence date, non-scoring marker, and external-model-inactive disclosure.
- Original-resolution screenshots pass at 1440, 1024, 768, 390, and 360 pixels.
- Customer login cannot open admin-only operations, evidence identities, raw
  paths, or Report Card ledger controls; admin login retains read-only QA access.
- Report Card public state remains OFF. The pending customer design contains no
  invented returns, win rate, SPY comparison, or recommendation history.
- Screenshot evidence is packaged into separate `before` and `after` folders,
  individually hashed, and bound to their respective source SHAs. Pass the
  baseline SHA separately; never bind old screenshots to the new candidate. If no trustworthy
  baseline exists, the package says `NOT_SUPPLIED` instead of inventing parity.
- Browser console errors, provider calls, publication writes, and Report Card
  ledger mutations are all zero.
- Material navigation, contrast, overflow, keyboard, and source-date defects
  are corrected and recertified before promotion is recommended.

## Promotion boundary

A successful preview is review evidence only. Merging the consolidated release
candidate and promoting its exact resulting source to production each require
their own owner authorization.
