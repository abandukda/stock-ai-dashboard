# Beta account / watchlist reconciliation

Baseline: `d5ae98242ef64743149b218e0ba12b8965713b97` (PR137 merged). Review input: *ATLAS Independent Architecture, Product and Release Review*, Oct22, inspected at the older `d2dd0f9`/PR119. This document records code and disposable execution evidence, not production activation or authentication proof.

## Finding-by-finding reconciliation

| Finding | Current implementation | Demonstrated property / remaining risk | Status / owner |
|---|---|---|---|
| P1-9 / security3: shared role passwords are not individual accounts | `app.py` shared-password routing remains; `services/customer/streamlit_identity.py` adds opt-in native OIDC claim binding; `watchlist_controller.py` resolves every operation against registered server subject | Existing actual Streamlit UserInfoProxy, issuer/audience/authorized-party/expiry/revocation tests; no role granted from a token claim. Current production39878126614 explicitly denies personal lists to shared-password users. No production IdP/private-store binding exists | Partially addressed in code, unresolved in production; Beta track / owner configuration approval |
| Missing usable individual onboarding/login/logout → watchlists composition | New `ui/personal_account.py` composes server-owned sign-in/logout callbacks with trusted controller and existing private-list renderer | Actual AppTest sign-in→create/search/add→Research callback→reopen→logout→Bob isolation; unprovisioned accounts denied with no registration. UI login-state boolean never grants data access; controller independently verifies current session | Built/tested candidate, not wired/deployed |
| Stale identity under concurrent storage contention | Baseline `PersonalWatchlistController._account` verified before waiting for SQLite BEGIN IMMEDIATE, then used that identity after waiting | New real SQLite contention regression failed baseline: a revoked request still read a private list. Candidate re-verifies after lock admission and requires same subject. Six cases cover read/write × revocation/expiry/account switch; no unauthorized read result or write | Confirmed defect repaired in candidate; security review gate remains |
| Cross-user watchlist access / unsafe shared state | Controller ownership from repository user, never user_id widget/query fields; private SQLite adapter serializes transactions and owner-scoped access; UI clears owner-specific widgets | Alice/Bob forged IDs rejected; quota/default operations atomic; account switch/logout/revocation clears private widgets; stored strings rendered as escaped literal text (PR137) | Built/tested; real individual account journey still not live verified |
| Account revocation/disabled status | OIDC resolver requires mandatory current revocation authority returning exactly False; service rejects disabled users | Missing/throwing revocation authority, expiry, unregistered account, disabled account denied. Race correction covers revocation while waiting for lock. External revocation service availability/latency remains a production prerequisite | Code validated, operational binding open |
| Streamlit fit / responsive onboarding | New shell stays within existing framework and existing private-list component | Actual Chromium generated sign-in→list→logout at360/768/1440; six screenshots inspected; no horizontal overflow and no external browser requests. Generated synthetic server identity is explicitly labeled and is not real OIDC authentication | Responsive fixture evidence only; original design parity and production UX open |

## Candidate changes and evidence

- Controller verifies session both before repository I/O and after transaction admission. Same-subject binding prevents a queued request from switching accounts. No new identity, role, account, entitlement, database root or provider connection is created.
- The new account shell is **unwired**. With no server bindings it displays configuration pending and exposes no sign-in/list controls. Unknown users are not auto-provisioned. Logout clears personal widget state before calling the native server dependency and never renders private lists on a logout failure.
- Production integration must inject `is_logged_in=lambda: st.user.is_logged_in`, native `st.login`/`st.logout` callbacks, and a controller bound through `bind_personal_watchlists` from server code. The UI state callback is presentation only; native verified identity and current revocation checks remain the controller authority. Never construct these dependencies from session/query/widget fields.

Executed in isolated `/workspace/atlas-refocus-beta`:

1. Baseline newly added lock-contention test: **FAIL**, `read-revoked` did not raise access denial.
2. Candidate79 offline tests PASS1.61s; network-denied repeat79PASS1.38s with0network attempts: `test_personal_account_ui.py`, `test_personal_watchlist_controller.py`, `test_streamlit_oidc_identity.py`, `test_customer_sqlite_repository.py`, `test_personal_watchlists_ui.py`, `test_beta_product_foundation.py`.
3. Actual generated Chromium: `test_premium_personal_account_render.py`, **1PASS6.89s**, all3viewport journeys, **zero external browser requests**. Six PNGs under `audit_results/premium_home/personal_account/`, plus inspected contact sheet. Synthetic authentication callbacks and temporary private SQLite only; no production credentials, identity-provider calls, account grants or storage changes.

## Production owner package / acceptance

Engineering candidate: BUILT/TESTED; MERGED/DEPLOYED/LIVE VERIFIED **NO**. Existing PR137 beta foundation is merged/source-deployed, but that is not individual-account acceptance.

Before activation the owner must approve: chosen IdP and pinned issuer/audience; secure server credentials/redirect configuration; invited account/role provisioning and disabled-account administration; current revocation authority; durable private store location/backup/restore/retention and concurrent-session policy. These are configuration/infrastructure decisions, not implied by this candidate. No secret values belong in code or user-facing receipts.

Then prove with two real invited test accounts: native login→own persistent list→add/remove/search→correct ticker Research→new session/reopen→logout/revocation→denial; Alice cannot read/edit Bob or old session widgets. Verify disabled/expired sessions, concurrent limits/default updates, mobile onboarding, role separation, missing-source states, permitted display and no provider credential exposure. Real Research content still depends on its own admitted-data gate; successful callback routing alone cannot close that gate.
