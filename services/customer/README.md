# ATLAS Customer Foundation V1

This package is the provider-independent customer/account boundary for ATLAS.
Authentication is represented by an external `auth_subject`; it does not store
passwords. Durable persistence is abstracted behind `CustomerRepository`, with
an in-memory implementation for tests and a relational reference schema in
`storage.sql` for a future managed PostgreSQL adapter.

The provisional `CUSTOMER_ENTITLEMENTS_V1_BETA` matrix centralizes feature and
limit decisions for Free, Premium, reserved Pro, and Admin plans. Entitlements
control visibility and customer actions only. They never alter investment
calculations or scanner output.

Customer watchlists contribute one deduplicated symbol set to the existing
Phase 8A `SubscriptionManager` under the `customer-watchlists` demand source.
This package does not open a provider connection or create a second live-market
subscription system.

The Streamlit renderer in `ui/customer_portal.py` is deliberately not wired to
current navigation in Phase 9D. External email/push delivery, billing, auth,
PostgreSQL deployment, and production portal wiring remain future work.

## Opt-in native OIDC binding (inactive by default)

`streamlit_identity.bind_personal_watchlists` connects the existing personal UI
controller to Streamlit's server-verified `st.user`. It does not configure or
launch login, open persistence, register users, issue roles or activate navigation.
The application owner must approve the OIDC issuer/client configuration, private
store binding, provisioning and current revocation authority before wiring it.

Supply `read_server_user=lambda: st.user` only from trusted server code. Never
supply browser/query/widget/session-state claims. Streamlit owns the OIDC token
signature/authentication verification. This adapter pins issuer/audience and
checks expiration (which Streamlit does not implicitly enforce), future `iat`/
`nbf`, authorized party, and revocation on every controller operation. Missing
claims or unavailable revocation fail closed; no raw tokens are read or stored.
The customer repository remains the role/entitlement authority, irrespective of
identity-provider role claims. Provision the stable `oidc_account_subject(iss,
sub)` identity explicitly; the adapter does not auto-register unknown subjects.

Provider-free validation uses actual `UserInfoProxy` semantics plus isolated
SQLite accounts. This proves the adapter/controller contract, not production
login, a configured identity provider or a production persistence deployment.
