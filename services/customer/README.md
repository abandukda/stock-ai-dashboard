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
