# Finnhub parallel full-universe certification

This is a non-publishing execution contract. It changes scheduling only; it
does not change the frozen universe, provider authority, evidence, analysis,
certification, or publication semantics.

## Audited baseline

The certified 6,033-symbol run uses a deterministic 41-shard manifest (40
shards of 150 symbols and one shard of 33). Contract tests, 50- and 250-symbol
canaries, manifest construction, shard acquisition, and aggregation execute in
that order. The acquisition matrix currently schedules at most two GitHub-hosted
runners. Each symbol makes six authorized Finnhub requests. Every request is
followed by a 1.05-second delay; retryable 429/5xx responses receive up to three
attempts with exponential backoff and deterministic jitter. Aggregation starts
only after the matrix reports success.

Run `37216506983` took about 7h31m: canaries consumed about 38m, acquisition was
the roughly 6h18m critical path, and aggregation consumed about 33m. The current
fixed delay caps two workers near 114 requests/minute before request latency.

## Opt-in five-worker contract

Workflow-dispatch runs may select exactly five workers. They must also supply a
positive governed aggregate Finnhub requests-per-minute allowance. The value is
never inferred. Each independent matrix job receives one fifth of the global
allowance, permits one request in flight, and spaces request starts accordingly.
The explicit cross-runner burst ceiling is therefore five requests. Missing or
invalid configuration fails before acquisition. HTTP 429 responses preserve
`Retry-After`; retry wait is the greater of that value and deterministic
exponential backoff. Telemetry includes calls, retries, 429s, provider errors,
rate wait, duration, and the applied rate contract.

The sequential 50- and 250-symbol canaries use the same explicit allowance in
workflow-dispatch mode (with one active worker), so certification does not keep
the legacy 1.05-second delay on the critical path. Scheduled legacy runs retain
their existing pacing.

Six workers remain unavailable until a complete five-worker governed run shows
zero unsafe rate behavior and the contracted allowance explicitly supports it.

## Completeness and recovery

Aggregation requires the exact deterministic shard-ID set, identical immutable
run identity, correct per-shard symbol digest, no duplicates, and exact expected
symbol membership. Partial results cannot aggregate or publish. Per-symbol
checkpoints and immutable per-shard artifacts remain reusable for a governed
retry with the same identity.

## Same-snapshot meaning

`same snapshot` identifies one immutable evidence-snapshot timestamp, source
SHA, universe digest, methodology/authority versions, and deterministic shard
manifest. It does not claim simultaneous wall-clock capture. Concurrent workers
collect within that governed run envelope; deterministic aggregation and replay
operate only on its complete immutable artifacts.

## Performance feasibility

The historical 36,198 calls require about 402 requests/minute if all work fit in
90 minutes. With the observed 33-minute aggregation, acquisition has roughly 57
minutes and therefore needs about 635 aggregate requests/minute before allowing
for transport latency and retries. Five workers at the legacy 1.05-second pace
cannot meet the target. A live benchmark is permitted only after the contracted
global allowance is supplied; this repository deliberately does not guess it.

## Schedule preparation

The existing production schedules are unchanged. After a complete governed
five-worker certification finishes within target, a separate authorization may
replace them with one non-overlapping nightly schedule near 18:30 America/New_York
(23:30 UTC during standard time, 22:30 UTC during daylight time). DST handling
must be explicit; a single fixed UTC cron does not represent 18:30 ET year-round.
