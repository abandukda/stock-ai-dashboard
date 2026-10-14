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
- an approved `ATLAS_DAILY_BUY_NOW_CRONITOR_URL` telemetry-only URL. Cronitor
  owns email recipients, delivery rules, and the independent missing-heartbeat
  deadline; ATLAS does not store email addresses or SMTP credentials.

The provider-free mode uses retained certified artifacts, performs no provider
calls or production writes, and exercises the same calendar, source identity,
certification, methodology-version, publication and Report Card-OFF gates.

Every live shard receives a partition of the 500-RPM global allowance and may
have only one request in flight per worker. A second control counts every HTTP
attempt, including retries, and caps a shard at `symbols × six registered
families × three attempts`. Exceeding that ceiling stops acquisition before the
next request. The six families also produce explicit freshness receipts:
profiles and basic/forward metrics must be captured in the current run;
financial statements must additionally have non-future fiscal periods; and
OHLCV must contain a recent completed session. Missing evidence is recorded as
`UNAVAILABLE`; stale, future-dated, or malformed temporal evidence stops the
certification run.

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

Cronitor must be configured for a 6 PM America/New_York job with a completion
grace period long enough for the certified full-universe run. The workflow emits
`run`, `complete`, and `fail` lifecycle events. Email rules must send the owner a
completion confirmation and immediate failure/recovery notices. Cronitor's
independent overdue-job alert supplies `NEVER_STARTED`/`DID_NOT_COMPLETE`
coverage even when GitHub never starts the workflow. Verify one test event and
one intentionally overdue test check before enabling live acquisition.

The same sanitized adapter is wired to authorized Report Card G2 acquisition
and G3 append outcomes through the protected `atlas-internal-report-card`
environment. G4 remains disabled; its eventual scheduled workflow must use a
separate Cronitor monitor and pass both delivery and deliberately overdue
heartbeat tests before unattended activation.
