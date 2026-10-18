# ATLAS daily-operation readiness

## What is registered

The daily coordinator has two UTC wakeups (`22:05` and `23:05`, weekdays) so
the exchange-calendar gate can admit exactly 6:05 PM America/New_York across
daylight-saving changes. It selects the latest finalized XNYS session and:

1. rejects an absent certified continuity boundary;
2. plans one daily append only when exactly one session is missing;
3. routes multiple missing sessions to the separately authorized bounded
   backfill path;
4. uses non-cancelling concurrency to avoid overlapping session work;
5. retains acquisition, certification, and publication as ordered boundaries.

## What is not operational

Unattended licensed acquisition and customer publication remain disabled. The
registered scheduled path performs provider-free planning and then fails closed
at `live-operation-disabled`. A successful wakeup or plan artifact is therefore
not evidence of acquisition, certification, or publication.

## Activation gates

Activation requires all of the following for the exact release SHA:

- verified runner health, durable raw/checkpoint storage, and restart recovery;
- one active scheduler path with duplicate/competing-worker rejection;
- provider entitlement, quota, hard request ceiling, pacing, and zero-retry
  controls;
- raw-first evidence persistence and explicit indeterminate-request treatment;
- terminal memory-bounded certification with no partial candidate;
- atomic publisher simulation, rollback proof, and last-known-good retention;
- Cronitor success, failure, and missed-session delivery evidence;
- separate owner authorization for unattended acquisition and publication.

Until these gates pass, `ATLAS_DAILY_BUY_NOW_LIVE_ENABLED` must remain false.
