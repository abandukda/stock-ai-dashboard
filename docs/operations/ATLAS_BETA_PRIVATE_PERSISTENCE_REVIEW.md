# Beta private persistence — opt-in provider-free review

Base: `da55afc86056fbf1c0bca1f8e5538208ee477187`.

This release supplies a durable adapter for the existing `CustomerRepository` contract. It is not a login implementation, production storage installation, or permission to enable the customer portal.

## Built and tested

`PrivateSQLiteCustomerRepository(root)` stores the existing account/profile, watchlist, preferences, saved research, entitlement overrides and notification records in an explicitly selected private directory. It uses the existing in-memory repository's ownership checks, a versioned JSON encoding of allowlisted model types, and a SHA-256 integrity check. No pickle, passwords, provider keys, raw licensed market data or model credentials are part of the customer schema.

- Watchlist add/remove, personal saved research and preferences survive adapter close/reopen.
- Cross-user watchlist reads, edits/deletes and saved-research deletion fail closed.
- Existing user authentication subjects are immutable. Rebinding an existing user ID without clearing its old alias is rejected.
- A colliding saved-research ID cannot overwrite another user's record. These two identity/ownership guards apply to both the in-memory and persistent implementations.
- Optional repository transactions wrap compound `CustomerService` operations. Concurrent registration is idempotent and Free-plan watchlist quota checks are atomic across independent adapter instances. Failed multi-step default changes roll back.
- Read operations do not rewrite the persisted state.
- The root and file require owner-only 0700/0600 permissions; wrong-owner, symlink, non-regular or group/world-accessible storage fails closed. SQLite uses rollback journaling, not WAL. Connections close after each operation; busy operations have a bounded 30-second timeout.
- Records are limited to 16 MiB. Unknown schema or mismatching digest blocks access instead of silently replacing customer state.

No default production directory, environment switch, database migration, UI route or external service is added. Tests use temporary local storage only.

## Limits and required acceptance gates

1. External identity must be verified by an approved identity/session layer. The existing `auth_subject` is an identity boundary, not proof of a valid login. A web handler must derive the account from that verified subject; arbitrary user-supplied IDs and caller-selected plans must not become authorization.
2. Service operations reject disabled accounts, including registration reuse, private reads and mutation; active administrators can disable/re-enable targets without deleting their private state. Disabled accounts do not contribute watchlist demand. This is a backend authorization guard, not browser-session revocation. Individual login, secure/revocable browser sessions, password recovery and onboarding remain unimplemented/unverified in production. This persistence adapter does not claim to provide them.
3. The existing private portal renderer remains unwired. Deployment, path/ownership, backup/restore, retention, encryption at rest if required and multi-host database selection require separate review/approval. The local database is plaintext under owner-only filesystem controls; hashes detect corruption and are not signatures or independent backup proof.
4. Snapshot serialization is deliberately bounded local-beta storage, not a scalable managed PostgreSQL adapter. No public customer data export or provider feed is introduced. Run concurrency and cross-user browser acceptance against the actual selected production identity/storage stack before beta admission.
5. Complete individual Admin/beta/viewer role separation and test two simultaneous real users' add/remove/reload/logout/revocation journeys at desktop/tablet/mobile. Provider credentials must remain server-side. Real production screenshots and functional isolation are required; fixtures are not beta launch acceptance.

Financial methodology, provider acquisition, scanner source, publication, original Report Card ledger, public activation and infrastructure routing remain unchanged.
