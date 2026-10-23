# Explicit individual-workspace composition

Base source: `8d42d762e78dba4441f7645eaeb3b4ce331d37ee`. This is code and generated acceptance evidence, not production account activation, source certification or genuine transcript/AI evidence.

## End-to-end gap and resulting behavior

The active app dispatched shared Watchlist storage and Earnings without injecting the already-built individual-account controller or read-only transcript cache. The isolated account shell could not reach actual app routing. A registered FREE account also lacked FULL_RESEARCH capability while its watchlist callback could open an admitted full Research ticker.

The final `main` now accepts an explicitly supplied `CustomerRuntimeBindings`. With no argument (including the existing production entry point), password authentication, navigation and source behavior remain on the existing path. The optional path composes the existing native-account shell, private controller, actual customer Research renderer and actual Earnings renderer. No identity provider, account, credential, private root, cache, provider transport or refresh job is constructed by it.

Bindings contain an existing `PersonalAccountBindings`, an optional existing `ReadOnlyTranscriptCache`, and supplied retained Earnings/Research rows. The server must supply these dependencies; browser/session/query fields and environment values do not construct them. Native `is_logged_in` controls presentation only: current identity, expiry, revocation, registered membership, disabled status, ownership and service capabilities remain independently checked by the controller.

## Authority and privacy boundaries

- Native identities receive only Account, Watchlist, Research and Earnings routes. No identity-provider role claim or stale password alias grants an internal/admin route.
- The presentation-only authority primitive lives in `services/personal_request_authority.py`, outside the provider-independent customer domain. Its standard-library-only dependency assertion excludes Streamlit, customer services, providers and dynamic imports; the original foundational app/domain isolation assertion remains unchanged.
- A request-local ContextVar restricts legacy role helpers to viewer and independently denies shared workspace watchlist storage. It can only narrow authority, resets in `finally`, and does not alter password aliases or another request/thread.
- FULL_RESEARCH and FULL_EARNINGS_INTELLIGENCE are checked against the registered service account. Watchlist ownership is not module entitlement. The source's Research availability remains separate from account entitlement; a FREE user sees the admitted-source status plus the precise disabled-account-feature explanation.
- An owner marker discards presentation only; it never grants access. Logout, unavailable/revoked/expired identity and account changes clear individual watchlist widgets and the bounded set of Research/Ask/Earnings selections, handoffs and report/cache keys. Password credentials/role aliases and unrelated session state are preserved.
- Personal Research selects exactly one supplied, publication-admitted retained record for the ticker and renders its existing customer projection. Missing, ambiguous or withheld records remain unavailable. It does not call the legacy refresh form, cross-surface bootstrap, licensed acquisition or external AI. Ask ATLAS is explicitly unavailable in this slice. Financial currentness and historical-chart admission remain the existing independent gates.
- Earnings receives the explicitly supplied read-only cache and retained quarterly rows. Source-period, transcript availability, summary availability, retention, account/license identity and evidence lineage are checked by the existing reader. A cached quarter is not proof of the latest release; no raw transcript, provider credential or cache MAC becomes a customer projection.

## Executed acceptance and limits

Offline selection: 118 tests passed in 72.16 seconds across account/controller/isolation/OIDC/private SQLite/Earnings modules. A separate 71-test route/source-selector regression selection passed in 20.62 seconds (overlapping selections; counts are not additive). Existing source selectors now inspect the actual final AST function rather than assuming a parameterless `main` signature.

The composition fixture extracts and executes the actual final `main`, effective navigation alias, Research handoff and role helpers. It uses actual account/controller/private SQLite and actual Research/Earnings renderers, with generated native identities and preseeded synthetic transcript evidence. Shared bootstrap, provider/model APIs and transcript writers are forbidden during customer interaction. This is actual extracted app composition, not whole-app startup or production/native-IdP acceptance.

AppTest covers two-account private-list persistence and navigation, a supplied admitted report, read-only cached Earnings summary/lineage, logout, direct account switch, legacy report-state cleanup, revocation/expiry, unknown invitations, FREE capability denial, and missing/duplicate/withheld Research records. Request authority is checked through actual role helpers and thread/nested/exception cleanup regressions. The unchanged no-bindings path still reaches the original password gate before any new bootstrap.

Actual Chromium composition test passed in 281.064 seconds: two cached-summary states (AVAILABLE/PENDING) × 360/768/1440 widths, each through invited login, persistent private list, saved-ticker handoff into the actual Research report, actual read-only Earnings status/source/lineage, logout, Bob isolation and revocation. Zero external browser requests, zero final Streamlit exceptions; all widths fit the viewport. Twelve complete generated Research/Earnings captures were produced under `audit_results/premium_home/extracted_composition`; mobile Research and Earnings evidence was inspected. The initial browser attempts exposed fixture-control issues (native radio inputs are hidden; existing-account Create-list disclosure is collapsed); the fixture now operates visible radio labels and opens that actual disclosure, retaining all authority/status/isolation assertions.


Review of the generated composed mobile Earnings capture exposed a real textual-state clipping defect: a narrow `st.metric` truncated the unavailable financial recommendation. Reported/upcoming ATLAS state and the expanded Recommendation now use escaped wrapping state cards; all numeric financial metrics and decision text remain unchanged. The 281.064-second full composition pass preceded this final presentation-only repair. After it, 27 Earnings regressions passed in 1.66 seconds and the existing five-mode/three-width Earnings browser test passed in 31.528 seconds, including full visible state text and geometry checks. Final composed available-summary Earnings screenshots were regenerated at all three widths with complete unavailable state, source lineage and zero external requests. Fresh full governed CI must pin the final integrated tree.

Screenshot and CI results must be pinned to the final integrated head; none of these generated images constitute production login, market-data or transcript intelligence verification.

## Separate owner-controlled activation

Before supplying production bindings, approve the IdP/issuer/audience/redirect configuration, invited account and plan provisioning, current revocation authority, private persistence location and backup/retention policy, existing transcript-cache binding/license/deadline/summary revision, and the admitted retained source inventory. Production settings, account grants, data acquisition, external AI and publication each keep their own required approval.

Then verify two real invited accounts through login, owned persistent lists, correct ticker Research, permitted retained Earnings, reload/logout/revocation and desktop/tablet/mobile isolation. Confirm deployed SHA and actual source freshness separately. Current main's parameterless startup remains unchanged and unconfigured; this review does not enable beta access or make a production launch claim. Report Card public activation remains OFF, and original ledgers are untouched.
