# ATLAS automated market-data operations

## Current safety state

The daily workflow is registered as an inert scheduler design. It cannot call
Finnhub or mutate the ledger: the repository enable flag is unset, the kill
switch defaults closed, five certification flags are required, and the final
live-orchestration step intentionally exits. Customer Report Card visibility
remains off.

## Schedule and calendar authority

GitHub wakes at both `22:30 UTC` and `23:30 UTC` on weekdays. Exactly one wake
can equal 18:30 in `America/New_York`, covering daylight-saving transitions
without treating UTC as the market timezone. The application gate rejects the
other wake. A generated and replay-verified XNYS calendar—not the cron weekday—
determines whether a finalized session or catch-up work exists. Early closes
come from the same XNYS schedule.

Ledger mutation uses the global `atlas-report-card-daily-ledger-mutation`
concurrency group with cancellation disabled. Ordered catch-up processes the
oldest due target session first. Every append is idempotent, followed by
SQLite integrity verification, atomic backup, SHA-256 verification, a restored
copy verification, and a session checkpoint. Restart derives remaining work
from the ledger rather than trusting a mutable checkpoint.

## Activation gates

All must be evidenced before live orchestration can replace the deliberate
failure step:

1. `PROVIDER_FREE_PLAN_PASS`
2. `LIVE_ACQUISITION_PASS`
3. `DETERMINISTIC_PRODUCER_PASS`
4. `APPEND_BACKUP_RESTORE_PASS`
5. `SECOND_CYCLE_RELIABILITY_PASS`

The environment must then set `ATLAS_REPORT_CARD_AUTOMATION_ENABLED=true`,
`ATLAS_REPORT_CARD_KILL_SWITCH=false`, and provide the exact protected
automation token. Re-enabling after a failure requires reviewed evidence; it is
not an automatic retry.

The emergency stop is either:

- set `ATLAS_REPORT_CARD_KILL_SWITCH=true`; or
- set `ATLAS_REPORT_CARD_AUTOMATION_ENABLED=false`.

Both prevent acquisition and append before credentials are used.

## Acquisition and retry budget

For `N` unique due tickers and one or more due horizons, the distinct zero-retry
ceiling is `3N + 1`: daily price history for each ticker plus SPY, and split and
dividend evidence for each ticker. Successful retained responses are shared
across horizons. A maximum of one retry may later be approved for retryable
transport/5xx failures, making the conservative ceiling `2 × (3N + 1)`.
Missing, stale, provider-empty, partial, entitlement-rejected, or inconsistent
evidence is never retried automatically and fails closed or receives an
explicit unavailable state according to the certified producer contract.

## Alerts and telemetry

Every run artifact must include source SHA, XNYS identity, ledger tips before
and after, due tickers/horizons, target sessions, call ceiling, actual calls,
attempt number, endpoint family, sanitized response state, evidence digest,
bundle digest, append/idempotency counts, SQLite result, backup digest and
restore result. GitHub environment reviewers and Actions failure notifications
are the initial channel. A production notification destination must be approved
and tested before unattended activation; alert delivery failure is itself a
failed run and leaves the kill switch closed.

## Separate Research refresh lanes

Research refresh never republishes Fair Values or recommendations. Each lane
stores retained evidence for a separately governed reevaluation:

| Lane | Trigger | Default scope | Cache/event rule |
|---|---|---|---|
| Prices and technical history | finalized XNYS session | active customer universe | append one finalized session; corporate-action reconciliation |
| Financial filings | filing event plus daily discovery | covered companies | refetch only on new accession/period identity |
| Analyst recommendations/targets | daily changed-record check | Top Ideas, Watchlist, recently researched | retain provider timestamp; no decision publication |
| Earnings results/calendar | event window and calendar changes | upcoming/recent earnings | event-driven, with bounded reconciliation |
| News/catalysts | bounded intraday or post-close window | Top Ideas, Watchlist, recently researched | deduplicate by licensed article identity and expiry |
| Company profiles | weekly plus corporate-action event | active universe | refresh only stale or identity-changed profiles |

Every lane requires its own entitlement map, call ceiling, freshness policy,
artifact identity, negative tests, and reevaluation handoff. Acquired evidence
cannot directly update customer authority.

## First eligible unattended execution

No date is currently scheduled because the certification and owner-authorization
gates are incomplete. Once all five flags are independently proven and the live
orchestrator has an exact-SHA certification, the first eligible execution is the
next finalized XNYS session at 18:30 America/New_York after activation. The
activation record must state that date explicitly before the kill switch is
released.
