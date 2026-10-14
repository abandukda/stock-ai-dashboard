# ATLAS daily BUY NOW post-close operation

The existing Finnhub full-universe certification workflow is the sole daily
investment engine. It wakes at 22:05 and 23:05 UTC on weekdays; an XNYS and
`America/New_York` gate admits only 18:00–18:59 Eastern on a finalized session.
Holidays, the wrong DST wakeup, duplicate sessions, and an advanced `main`
branch fail closed.

Live execution additionally requires all of:

- repository variable `ATLAS_DAILY_BUY_NOW_LIVE_ENABLED=true`;
- protected `FINNHUB_API_KEY` access;
- secret `ATLAS_DAILY_BUY_NOW_AUTHORIZATION=DAILY_BUY_NOW_LIVE:<source-sha>`;
- an approved `ATLAS_DAILY_BUY_NOW_ALERT_WEBHOOK` destination.

The provider-free mode uses retained certified artifacts, performs no provider
calls or production writes, and exercises the same calendar, source identity,
certification, methodology-version, publication and Report Card-OFF gates.

## Failure and recovery

The last valid customer snapshot remains in the repository unless every shard,
deterministic replay and publication gate passes. Promotion stages candidates,
retains last-known-good files, and atomically replaces the governed set. A
failed write restores the prior set. Every run retains a heartbeat; successful
live publication retains a 365-day publication receipt containing source,
session, prior and resulting hashes.

For a missed or failed refresh, keep live enablement unchanged, diagnose the
heartbeat and final artifact, and use a manual `live` dispatch only with the
same source-bound authorization. Never reuse an artifact from another session,
mark stale values fresh, or bypass the coverage gate. Late finalized earnings
are `NEWLY_UPDATED` evidence and require a separately authorized incremental
recertification; they do not rewrite the original post-close snapshot.
