# ATLAS Report Card G2 decision readiness

Candidate source: `109eb9b10b5d7e29259c88d97726df8dfd2b83ce`

Decision state: **owner review required; not executable**.

The machine-readable decision draft is
`config/report_card_g2_decision_draft_20261014.json`. It preserves the last
verified protected identities only as prior evidence. They are not represented
as current-candidate certification.

The entitlement workflow uses the canonical-JSON digest `161b2799…`; the
repository file's byte digest is `a270da1…`. The decision draft records both so
an owner cannot accidentally substitute one hash convention for the other.

## Why a fresh package is required

The only live G2 attempt, run `38628414964`, failed during acquisition and did
not retain a certified market-evidence artifact. The one-shot claim is therefore
treated as consumed. The current acquisition workflow and protected transition
constants remain bound to source `fae6a94f96f8f7ed6b24a96a8cdd2fe21ffa703a`,
not candidate `109eb9b`. Reusing the old token or claim would violate the source
and one-shot boundaries.

Before an executable authorization can exist, a provider-free protected
validation at the exact frozen candidate must re-read the ledger, independent
backup, CLOSED sentinel and finalized XNYS calendar and emit a fresh canonical
plan. No provider request or ledger write is needed for that validation.

## Proposed owner decision boundary

- Cohort: the 20 original immutable signals, plus SPY as benchmark.
- Provider capabilities: historical daily OHLCV, splits and dividends only.
- Ceiling: 61 total provider requests, zero retries.
- Raw responses must be durably retained before normalization.
- The protected signal ledger and backup are read-only throughout G2.
- No customer publication, observation append, schedule activation or public
  performance claim is authorized.
- The acquisition sentinel must start and finish `CLOSED`, including every
  failure or interruption path.

G3 bundle production, G3 append, G4 scheduling, public Report Card activation
and production deployment are separate decisions.

## Owner email and monitoring readiness

The candidate code has an allowlisted, sanitized Cronitor adapter and G2/G3
workflows require `ATLAS_REPORT_CARD_CRONITOR_URL`. However, repository evidence
does not prove that the external monitor routes to the owner's email or that
success, failure and missing-heartbeat delivery have been received. G2 emits
only a terminal `complete` or `fail` event; it does not emit a `run` event. G4 is
not scheduled, so missed-start monitoring cannot yet be certified.

Required evidence before authorization:

1. A sanitized Cronitor test receipt bound to the exact monitor.
2. Owner confirmation of received success and failure email messages.
3. An independent missed-heartbeat test, after a schedule is separately
   approved.
4. Recovery instructions that keep the sentinel `CLOSED` and prohibit an
   automatic provider retry.

## Durable storage readiness

Protected validation run `38629818807` succeeded on `atlas-worker-1` and bound
the prior ledger, backup and CLOSED sentinel identities recorded in the decision
draft. Earlier internal Report Card workflow runs also demonstrated the storage
validation path. The code requires disjoint persistent ext4 mounts, UUID entries
in `/etc/fstab`, runner ownership, SQLite WAL with FULL synchronous mode,
append-only triggers, writer locking, backup SHA-256 and a restored hash-chain
match.

This is credible prior readiness evidence, not a current-candidate storage
certification. A fresh provider-free protected validation must prove the current
ledger and backup identities, verify restore, and confirm that the failed G2
claim has been retired rather than reused.

## Known registration defect

The stable protected gateway's `plan` path still expects execution-package hash
`c0ee01e3ba62dc9c586bded0f2afa4cf018bf201c72cdfd2fcc88f7e4b3a8493`, while
the current package's canonical digest is
`219c5453b58bfe838a58f73a666a630637747f67fa5cf419526f4a3a9908764a`.
That path is stale and must not be used to authorize the candidate until the
binding is reconciled and tested.
