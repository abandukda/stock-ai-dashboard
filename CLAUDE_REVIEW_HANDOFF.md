# ATLAS R1 deployment and Report Card acquisition handoff

## Release identity

- Certified R1 candidate: `1cfc27ee9f52a22bd4917c64db95fc2883ccdeed`
- Governed certification: `38267208505` (`PASS`)
- Rollback point: `01705ea9b65a2a3ee5a1e474fb9cac93697a0893`
- Promotion: exact fast-forward only; no integration tree was created.
- Live identity proof: the deployed Streamlit `data-atlas-source-sha` marker must equal the certified candidate. GitHub branch identity alone is insufficient.

## Report Card evidence acquisition

The new acquisition path is deliberately inert. It has no schedule and accepts only the explicit one-run token `REPORT_CARD_ACQUIRE_ONCE`. It reads the protected append-only ledger, verifies the ledger chain, derives due signals and horizons from that ledger, and verifies the ledger file hash did not change.

Bounded provider scope:

- one daily adjusted OHLCV request for each unique due ticker;
- one daily adjusted OHLCV request for SPY;
- one split request and one dividend request for each unique due ticker;
- governed XNYS calendar supplied as an exact external artifact, not reacquired by this workflow.

Base call budget is therefore `3N + 1`, where `N` is the number of unique due tickers. Transient retries are bounded, telemetered, and remain subject to the existing 500-RPM governor.

The internal evidence bundle distinguishes `AVAILABLE`, `STALE_PRICE`, and `MISSING_PRICE`, rejects partial time series and missing corporate-action evidence, binds benchmark references to SPY closes at or before each immutable signal timestamp, records provenance and hashes, and remains explicitly non-customer-visible. It performs no observation append.

## Independent authorization gates

1. `REPORT_CARD_ACQUIRE_ONCE`: dispatch the inert acquisition workflow with the exact governed calendar run/artifact and protected environment. Require ledger hash invariance, bounded telemetry, finalized session, and a verified artifact digest.
2. `REPORT_CARD_APPEND_ONCE`: after two offline producer replays have identical digests and a non-mutating consumer dry run passes, separately authorize one append against the exact acquisition artifact. Require atomic primary/backup verification and idempotency.
3. `REPORT_CARD_ENABLE_DAILY`: only after the first append is certified, separately register/enable a post-close weekday schedule with XNYS holiday validation, retry/alert handling, and catch-up controls.

Public Report Card visibility remains OFF throughout these gates.

## Claude review questions

- Does the acquisition boundary derive every ticker and horizon solely from verified immutable ledger state?
- Are stale, absent, partial, and immature evidence states fail-closed without fabricated values?
- Is the separation between retained provider evidence, observation production, durable append, and customer publication operationally unambiguous?
- Are the three authorization gates sufficiently independent to prevent acquisition from implying append or public activation?
