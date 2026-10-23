# Independent-review reconciliation and integrated recovery

Review authority: owner-provided *ATLAS Independent Architecture, Product and Release Review*, October22, all15pages read. Its inspected source was `d2dd0f9` (PR119), not the current release. This reconciliation starts at `d5ae98242ef64743149b218e0ba12b8965713b97` (PR137). Findings below distinguish code properties, retained evidence and operational proof. A test name alone does not close a finding.

This review authorizes no acquisition, paid generation, deployment, protected operation, publication, ledger append, repository visibility change or destructive cleanup. Public Report Card stays OFF.

## Findings against current main

Relative links identify current source; the baseline above fixes their meaning. Track documents carry detailed executed reproductions and correction receipts. Candidate changes are not live acceptance.

| Finding | Original location / current implementation | Reconciled classification and concrete evidence | Remaining correction / owner |
|---|---|---|---|
| P0-1 unattended refresh | [daily workflow](../.github/workflows/atlas_daily_incremental_buy_now.yml), [coordinator](../scripts/run_daily_buy_now_post_close.py) | Confirmed unresolved. Actual39878684720 at d5 failed CONTIGUOUS_BOUNDARY_REQUIRED with0provider_calls/0production_writes; protected jobs skipped. Empty manifest session and configured fallback, not a measured provider-connectivity failure | A: certify retained continuity, then separately approve configuration/acquisition/promotion. Five successful unattended days remain proposed acceptance, not achieved |
| P0-2 four hashes /35vs6033 | [runtime projection contract](../services/runtime_projection_contract.py), [loader](../services/runtime_projection_loader.py), [manifest](../publication_manifest.json) | Partial/assumption corrected: source/executor hashes and bounded runtime-projection hashes describe different objects. Four source hashes differ from local projection; all8 runtime files match their separately bound projection digests.35rows/15allowed/11BUY_NOW are not6033certified rows or1298servable rows | A: verify pinned executor archives and41shards before closing full-source reconciliation; retain explicit coverage distinction |
| P0-3 stock/SPY starting prices | [activation](../services/report_card_observation_activation.py), [acquisition](../services/report_card_market_evidence_acquisition.py) | Confirmed unresolved V1 methodology: stock immutable reference base differs from registration-linked benchmark base. PR137 provenance safeguards do not repair this conceptual mismatch | F: versioned write-disabled aligned-entry rehearsal and known-answer proof; owner approves methodology before operational adoption |
| P0-4 one cohort | same acquisition and [producer](../services/report_card_observation_producer.py) | Confirmed unresolved V1 MIXED_SIGNAL_MATURITY/PARTIAL_HORIZON_STATE. Strict whole-bundle safety is not a scalable per-signal maturity model | F: independently eligible signals in inert V2 rehearsal; no silent V1 append changes |
| P0-5 public machine-readable data | [statement histories](../data/customer_research/statement_histories/manifest.json), [annual bundle](../data/customer_research/annual_financials/manifest.json), [normalizer](../services/g6_annual_financial_normalization.py) | Exposure confirmed; contractual consequence needs owner/legal decision. Provider-derived filing facts remain machine-readable despite read_only/provider_calls0 metadata.11ticker annual bundle declares13201accepted facts/147filings. Permitted commercial display does not itself authorize raw-feed redistribution | Coordinator: exact path/lineage inventory and rights decision; no visibility/history/data deletion performed |
| P1-1 off-host backup | [ledger](../services/prospective_report_card.py) | Partly repaired software, operational evidence unavailable. PR137 fixed delayed SQLite connections changing backup bytes after checksum; synthetic GC regression proves software property only | F/A: original primary/WAL, independently controlled backup and restore evidence; not proof of worker shutdown cause |
| P1-2 finite evidence retention | current workflow retention declarations; pinned artifacts11318542723/11456584757 | Confirmed. Both artifacts freshly reported unexpired, hashes match package, expiry Jan2/Jan5 2027 respectively. Metadata availability is not downloaded-content verification | A: approve bounded archive verification; separately approve durable-storage architecture/transfer, no automatic copies |
| P1-3 original publication unproven | [private readiness](report_card_private_readiness_20261020.md), [ledger](../services/prospective_report_card.py) | Still unverified. Registration/reference/publication are separate; historical20signals/0observations is not a fresh primary-ledger audit | F: immutable source/registration/publication evidence; honest registered wording; F1 must not depend on successful observation writes |
| P1-4 sample warning counts signals | [Report Card](../services/report_card.py) | Still unresolved in baseline.20signals from one scan are not20matured independent observations | F: matured-checkpoint counts/cohort concentration and suppressed unsupported aggregate claims; proposed30threshold requires owner methodology approval |
| P1-5 per-horizon human token | protected acquisition/append workflows | Current operational design confirmed. Tokens preserve authorization but ongoing automation policy has not been granted | F/coordinator: consolidate approval packages; proposed standing policy is a separate decision, not removal of gates |
| P1-6 git publication | [publication governance](../services/publication_governance.py), publication workflows | Confirmed current delivery architecture. Atomic staging/rollback code exists but git/deployment propagation remains separate | A/H: propose content-addressed private evidence + atomic admitted pointer; no migration or infrastructure change |
| P1-7 cron window/recovery | daily workflow and [operations](ATLAS_DAILY_BUY_NOW_OPERATIONS.md) | Current window is18:00–18:30ET, superseding the review’s18:00–18:59. No evidence all missed starts recover.39878684720 proves a new coordinator execution, not successful daily publication | A/H: authorized schedule/alert receipts and last-known-good failure rehearsal; don't broaden window blindly |
| P1-8 universe coverage | publication manifest | Counts confirmed; inference “4in5queriesfail” overstates unknown investor-query distribution and universe composition. Current35-row runtime is narrower still | A/B/C: explicit eligible/withheld/unretained disclosures, cause-based coverage audit; no invented evaluations |
| P1-9 shared passwords | app role login; [OIDC binding](../services/customer/streamlit_identity.py), watchlist controller | Partially addressed. Native identity/controller foundations tested; production shared-password sessions cannot access personal lists (actual39878126614 screenshots). Individual IdP/store remains unbound | G: usable opt-in account shell and concurrency/session isolation proof; separately approve real provisioning/configuration |
| P1-10 public self-hosted runners |54workflows,32self-hosted job declarations | Old count superseded. No self-hosted pull_request trigger;4push jobs remain on closure-temp branch across3workflows. Runner identity/labels guard newer workloads but do not prove all runner-group/branch controls | H/owner: review routing/branch protection/environment settings; no runner start/reinstall/routing change |
| P1-11 statements/uncertain share basis | statement-history bundles and annual financial projection | Coverage limitation remains. Retained11ticker statements are not current full-universe fundamentals; uncertain per-share basis must stay disclosed | A/C: retain basis warnings, verify source/action history before new multi-year inference |
| AI lexical vs semantic grounding | [grounded synthesis](../services/grounded_research_synthesis.py), transcript validation | Partly repaired137: extractive Research intermediate, ordered transcript traceability rejects demonstrated reversals; semantic_entailment_verified false. No genuine production AI acceptance | D/E: typed evidence interpretation, adversarial examples, numerical/source validation; do not claim general semantic verifier |
| AI aggregate budget | [external adapter](../services/external_ai_adapter.py) | Confirmed gap: per-generation ceiling is not monthly aggregate cost control. Paid production generation inactive | D/owner: approve aggregate reservation/cache policy before paid execution; no new paid call |
| Autopilot permissions/cost | [Autopilot](../.github/workflows/atlas_codex_autopilot.yml) | Existing scheduled16weekday opportunities and paid-key scope remain.39858851846 develop/validate succeeded; draft creation failed repository policy. Broader permissions are not a safe implied repair | H/owner: decide schedule/budget/draft publishing policy; do not expand token permission or invoke external AI |
| Streamlit complexity | app.py/UI generations/backups | Structural concern confirmed, exact old counts not acceptance criteria. Runtime source identity differs from loaded dependency identity under warm imports. Actual39878126614 source/auth passed while historicalNVDAchart failed | H/C: test warm/cold interface contracts; read-only loaded-module evidence or separately approved clean restart; no financial reload expansion or rewrite |
| Old fixture-only UX evidence | review pages6/11; current production artifact12469458144 | Superseded for existence of real screenshots, not product completeness.51actual production PNGs,12independent viewer route/viewport diagnostics inspected; original chart failure remains fatal. No private Report Card/Earnings viewer-scope acceptance | B/C/F/H: primary-reference gap review and actual role-correct journeys; generated renders remain explicitly nonproduction |

## Operational receipts reused, not inferred

- Main/source production: d5; QA39878126614 failed requiredNVDAhistory,66/68required,12/12supplemental,51screens. New repeated guards change denominator; not comparable with older34/36.
- Actual artifact12469458144: SHA256 `856ad7c355c4ceaf7586edef7f4c052816cef0ae587b74ae0fbe3d52f74cc8ec`.
- Smoke39647746218 freshly rechecked SUCCESS at877bf2fd; proves that historical one-job execution, not current runner readiness. Runner21/23 last direct observation Offline Oct22 7:55PM ET; no start operation.
- Historical candidate37216506983 SUCCESS ataa12ff9e; aggregate37553164176 FAILURE at1e57ec65. A successful candidate run does not close full replay/currentness.
- Original-worker39544587581 failure confirmed, but shutdown initiator remains unproven. Earlier OOM and later backup software bug are not evidence of this shutdown cause.

## Simpler target without an unauthorized migration

Preserve nine interfaces: licensed transport; normalized versioned private evidence; deterministic certification; read-only admitted customer projection; premium UI; separate immutable Report Card service; grounded AI/transcript cache; trusted individual identity/watchlists; scheduler/alerts/recovery. Code stays in git; proposed durable evidence/snapshot storage is a separately approved change. A bounded valid ticker can be admitted under its own certified source contract without asserting full-universe certification or changing BUY NOW ranking authority.

Consolidate repeated workflows only after dependency/secret/role/routing/rollback inventory. Retire no workflow, backup or data file in this candidate. Do not change provider sourcing or revive Twelve Data implicitly. No new general operational gate is introduced by this reconciliation.

## Separate owner decisions

1. One retained-archive verification at exact current main d5 with existing reviewed scope/token; not a licensed acquisition or certification authorization.
2. Sanitized original-host/module identity and independent backup authority; a clean Streamlit restart, if chosen, needs explicit separate approval.
3. Bounded Finnhub and EarningsCall acquisition scopes/requests/entitlements; separate paid-model budget/privacy/model scope.
4. F1 read-only private Report Card source/role configuration and verification; separate F2 methodology adoption, acquisition, append and publication decisions.
5. Real beta identity/store provisioning; repository rights/visibility; storage/protected migration changes, each independently approved.
6. Exact integrated candidate merge/deployment after required CI and owner approval. No previous generic resume approves these operations.

## Integrated track evidence

- [Data/hash/admission reconciliation](ATLAS_REFOCUS_DATA_RECONCILIATION.md)
- [Home/original-design comparison and render evidence](ATLAS_REFOCUS_HOME_DESIGN.md)
- [Research/AI interpretation and remaining semantic limits](ATLAS_REFOCUS_RESEARCH_AI.md)
- [EarningsCall correction/revision pipeline](ATLAS_REFOCUS_EARNINGS.md)
- [Beta account/session isolation journey](ATLAS_REFOCUS_BETA.md)
- [Report Card F1/F2 reconciliation](ATLAS_REFOCUS_REPORT_CARD.md)

Each candidate improvement is BUILT/TESTED only until exact-head remote CI, owner merge/deployment approval and independent live QA. No track's fixture evidence closes another track's live gate.

## Integrated execution receipt

Coordinator ran78selected files (governed customer selection plus all ReportCard tests and cross-track additions): **1228tests +8subtests PASS48.98s**, all socketcreate/connect/connect_ex denied,0networkattempts. Discovery completeness now tests actual3featured/fullinventory/lasttickerResearch navigation rather than obsolete source-code shape; actual registration field is asserted explicitly. Independent adversarial review separately ran120tests then156ReportCard tests with0networkattempts, found/fixed candidate arithmetic overflow and F1 return-authority leakage before integration. Counts overlap and are not additive.

The all-render browser sweep exposed an existing generated Earnings fixed-reader/wall-clock-capture mismatch. Mock capture time is now pinned to the fixture reader's exact clock; the unchanged available/pending assertions pass in a focused actual Chromium rerun (1PASS24.91s). No production timestamp/freshness guard was relaxed. Full integrated render/governed-CI receipts are recorded in the PR/Issue78 after execution.
