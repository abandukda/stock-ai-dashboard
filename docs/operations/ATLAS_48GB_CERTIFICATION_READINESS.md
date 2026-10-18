# ATLAS 48 GB certification readiness

This contract prepares the existing evidence-bound BUY NOW certifier for the
Contabo host. It does not run certification or authorize provider/publication
operations.

## Immutable certification inputs

- exact registered repository source SHA;
- original and recovery raw-envelope manifests and request accounting;
- exactly 1,298 governed customer securities;
- all 41 retained technical-history shards and their aggregate digest;
- QRVO terminal-unavailable evidence and every justified withholding;
- immutable checkpoints whose source, session, population, phase, and batch
  identities match the registered run.

No Finnhub calls are permitted. Scoring rules, thresholds, 200-bar minimum,
ordering, withholding, forward/reverse comparison, and publication gates remain
unchanged.

## Resource contract

- Start with the existing deterministic 64-security batches.
- Preserve the existing **5 GiB RSS operating target** and add a job-scoped
  **8 GiB hard stop** (for example, a systemd/cgroup limit or an equivalent
  watchdog). The additional host memory is recovery headroom, not permission
  for the scoring graph to grow without bound.
- Sample process and cgroup RSS at every load, forward, release, reverse,
  checkpoint reload, aggregation, candidate, and simulation boundary.
- Persist and fsync a valid checkpoint before beginning the next batch.
- On threshold approach, stop closed after the last valid checkpoint. Never
  emit a partial candidate or attempt production publication.
- Record wall time, CPU time, peak RSS, free disk, checkpoint bytes, batch
  throughput, and exit condition even on failure.

The 5 GiB target remains the production acceptance contract. Crossing 8 GiB
must checkpoint and fail closed before host-wide pressure develops. A
provider-free representative check must establish the actual peak before
either limit can be revised.

## Preflight on the secured target

1. Verify Ubuntu, CPU, usable RAM, filesystem type/free space, Python 3.11,
   pinned dependencies, clock synchronization, and network health.
2. Verify protected directories, ownership, `fsync`, atomic rename, readback,
   and process-restart durability.
3. Verify all manifests before parsing retained evidence.
4. Run focused deterministic fixtures, checkpoint corruption/restart tests, and
   a representative provider-free batch with telemetry.
5. Verify the protected job has no Finnhub credential and cannot access the
   production publisher or Report Card mutation entrypoint.

## Activation boundary

The full 1,298-security certification requires separate owner authorization
bound to the secured runner identity, exact source SHA, evidence manifests,
checkpoint namespace, 5 GiB target, 8 GiB hard stop, batch size, and
provider-free operation.
Terminal certification does not authorize production publication. Publication,
unattended scheduling, further acquisition, and Report Card mutation each retain
their own gates.
