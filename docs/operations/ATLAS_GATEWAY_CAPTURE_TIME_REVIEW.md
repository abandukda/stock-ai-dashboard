# Gateway capture-time evidence review

Baseline: `8d42d762e78dba4441f7645eaeb3b4ce331d37ee`.
Provider-free engineering only; no acquisition, ledger access, archive dispatch,
promotion, publication, runtime configuration or infrastructure change.

## Demonstrated gap

The prior raw gateway receipt bound response bytes, request identity and attempt
counts but recorded no UTC capture time. The same raw bytes, metadata and summary
could produce a review candidate with either 21:10Z or 22:10Z supplied by the
caller. That candidate remained review-only; this was not a demonstrated live
publication bypass. It nevertheless left future source-currentness review
without executor-recorded capture-time evidence.

## New bounded contract

`ATLAS_GATEWAY_CAPTURE_TIME_V1` is an independent receipt extension; the existing
run contract, request scope, call ceiling, response hashes, zero retries,
redaction and monotonic transport latency remain unchanged.

- Each attempted request records canonical UTC `attempt_started_at` and, only
  after a complete stream with a valid non-reversing clock,
  `response_completed_at`. Incomplete or invalid-clock receipts remain
  explicitly time-unattested; no completion timestamp is invented. An HTTP or
  schema failure can retain its observed response window, but the failed run
  still cannot enter history review.
- The summary records the first request start and final response completion.
  Sequential windows must not overlap or run backward. An invalid start clock
  stops before transport. An invalid completion clock retains safe raw bytes,
  their actual hash and the attempted-call count, then stops without retry.
- The clock is the internal executor UTC clock, injectable through the Python
  function for tests only. No workflow input, provider response, scope artifact
  or customer value supplies it.
- Gateway-to-history conversion requires versioned receipt windows, matching
  summary bounds, caller `captured_at` equal to the summary completion, and no
  window later than `checked_at`. A later ancillary response cannot make an
  earlier pre-close candle response appear finalized.
- The family retains both its individual request window and the run capture
  completion. Capture time is separate from the provider price/session as-of
  timestamp. `GATEWAY_RECEIPT_BOUND_NOT_CLOCK_CERTIFICATION` is deliberately not
  independent wall-clock, contractual, data-quality or financial certification.
- Legacy raw receipts remain unchanged. Gateway conversion rejects them as
  `HISTORY_GATEWAY_CAPTURE_TIME_UNATTESTED`; it does not infer a timestamp from
  a run ID, file time or caller argument. No legacy Report Card evidence is
  rewritten or reacquired.

## Acceptance and remaining gates

Actual mock transport -> persisted raw/metadata/summary -> provider-free history
review is tested, including distinct request/run completion times. Regressions
cover raw hash preservation, caller-time substitution, missing/invalid/non-UTC,
reversed/future/overlapping windows, incomplete responses, start/end clock
failures, clock exceptions, redaction, request budgets and unchanged zero-retry
behavior. Generated candles are test evidence, not financial observations.

The returned history wrapper remains `OWNER_REVIEW_ONLY_NOT_PUBLISHED` and cannot
be installed directly as an admitted read-model document. Real account
entitlement, exact immutable scope approval, source authority, adjustment
evidence, independent backups, source certification, promotion and actual
authenticated production QA remain separate gates. Public Report Card stays
OFF. This review creates no acquire token or standing execution authorization.
