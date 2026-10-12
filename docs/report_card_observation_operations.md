# Report Card observation operations

## Separation of duties

1. An explicitly authorized acquisition job retrieves finalized daily closes,
   SPY closes, the governed XNYS calendar, and split/dividend evidence through
   the existing Finnhub adapter and 500-RPM governor.
2. That job publishes exactly one `report_card_market_evidence.json` artifact.
3. `ATLAS Report Card Observation Producer` converts the evidence artifact to
   `report_card_observations.json` without provider calls or ledger mutation.
4. `ATLAS Internal Report Card Observation` applies that exact bundle atomically
   and verifies a backup restore. Public Report Card visibility remains OFF.

## Proposed schedule (not enabled)

Weekdays at 22:30 UTC (`30 22 * * 1-5`). The producer must still consult the
governed XNYS calendar, require a finalized regular close, and exit successfully
with no bundle on holidays or before a registered horizon matures. Cron is only
a wake-up time; it is not evidence that a market session occurred.

## First authorized production observation

1. Confirm the immutable primary ledger and separately mounted backup root.
2. Record the ledger tip and signal count; do not reset or migrate it.
3. Authorize one bounded market-evidence acquisition for the due horizon.
4. Verify the evidence artifact identity, provider telemetry, calendar version,
   finalized-close timestamps, SPY alignment, and corporate-action status.
5. Dispatch `ATLAS Report Card Observation Producer` with the exact evidence
   run/artifact, registered horizon, and `authorize_bundle_production=true`.
6. Inspect the output bundle and offline certification; do not edit it.
7. Dispatch `ATLAS Internal Report Card Observation` with the exact producer
   run/artifact and `activate_observation=true`.
8. Verify append/idempotent counts, ledger hash tip, backup SHA-256 and restore.
9. Keep customer/public Report Card visibility OFF.

No schedule or provider acquisition is enabled by the reviewed workflow.

