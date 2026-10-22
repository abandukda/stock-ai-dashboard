# Personal watchlist integration candidate

## Built, intentionally unwired

`PersonalWatchlistController` resolves an injected trusted server verifier on every public operation, before database access. It checks expiry and revocation, resolves an already registered subject to its account, rejects disabled accounts, then performs ownership-checked operations within the same SQLite transaction. It never registers users, accepts client user IDs, selects a database path, or fetches provider data. Existing service quotas remain authoritative.

The `VerifiedWatchlistSubject` dataclass is a typed verifier result, **not authentication proof**. A production binding must actually validate issuer, audience, signature, expiry, membership and revocation using an approved identity system. The callback contract and test revocation flag do not implement an identity provider or real session revocation.

The opaque `view_key` only rejects stale forms when an account changes. It grants no access: each operation still resolves the current account and checks list ownership. Saved membership and mutation use the same account and transaction. The controller accepts tickers from a supplied catalog and exposes Research only when the existing customer-authority projection admits that supplied record; it never certifies or publishes financial data.

`render_personal_watchlists` supports create, rename, default, confirmed delete, search, persistent add/remove and optional Research navigation. Missing trusted injection produces an honest pending state. On account switch or denial it clears its widget namespace. The UI contains no factory based on query or session identity, and is **not wired into shared-password production navigation**. Existing shared-watchlist admin containment is unchanged.

## Acceptance evidence and limitations

Focused offline tests exercise Alice/Bob forged list IDs across all operations, stale forms, disabled/unknown accounts, expiry/revocation before I/O, persisted restart, catalog-only search and certified Research membership. Actual Streamlit AppTest interacts with create, search, add, restart, rename, remove and delete against temporary SQLite. A forged browser identity cannot enable the default pending surface.

These are generated local applications, not production screenshots or identity-provider acceptance. Desktop/tablet/mobile browser review, exact-head CI, production deployment and authenticated live verification remain separate gates. SQLite persistence is neither an independent backup nor encryption/cryptographic authenticity.

## Required future owner decisions

Approve the individual identity-provider/session verifier and account provisioning/revocation policy; approve private storage, recovery and operational configuration; then review an explicit route binding and test real two-account sessions, revocation and responsive renders before beta enablement. No credentials, accounts, infrastructure, production records or provider calls are created by this candidate.
