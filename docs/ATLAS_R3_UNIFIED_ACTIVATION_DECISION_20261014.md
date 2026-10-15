# ATLAS R3 unified activation decision

Status date: 2026-10-14 (America/New_York)

This package consolidates product release, external synthesis, incremental
BUY NOW refresh, Report Card G2, monitoring, and durable evidence decisions.
It does not authorize a provider call, customer publication, ledger write,
schedule activation, secret change, or production deployment.

## Release evidence

- Integration base: `0a8ee5bf8137378a2d8e10ccd0c4f78a5a0830ed`.
- Governed product predecessor: `109eb9b10b5d7e29259c88d97726df8dfd2b83ce`.
- Governed predecessor run: `38666664312` (`PASS`, provider calls `0`).
- Governed artifact: `atlas-customer-experience-qa-109eb9b10b5d7e29259c88d97726df8dfd2b83ce`.
- Artifact ID: `11943043316`.
- Artifact SHA-256: `ddbd3e58baa8b047587f0bd9d3621a2ef139e8bee52369b4529227c74f69d0f6`.
- Final integrated SHA: recorded in the release report after these controls are committed and recertified.
- Main is an ancestor of the review branch; no force update is required.
- Rollback identity for any later deployment is the then-current production
  `main` SHA captured immediately before promotion.

The governed archive is the original-resolution desktop/mobile visual evidence.
Automated certification does not replace independent visual review or real-user
beginner comprehension testing.

## External AI synthesis decision

External inference remains OFF. The implementation requires two activation
gates, provider `openai`, an exact model, privacy redaction, input/output/request
and latency limits, structured output, and ATLAS contradiction/grounding
validation. Credential presence alone cannot activate inference.

Proposed initial model: `gpt-5.4-mini-2026-03-17`.

Proposed ceilings: 12 seconds/request; 48,000 sanitized input bytes; 900 output
tokens/request; four requests/generated narrative; estimated $0.06/narrative,
$10/day and $200/month. Provider-project aggregate budget enforcement and alert
delivery must be proven before activation. No paid tools are permitted.

Required decision: approve the named OpenAI project/model, transmitted certified
data classes, processing region/retention, and the ceilings; then authorize a
non-production governed fixture run. Production activation remains a later
exact-SHA decision.

## Incremental BUY NOW decision

The provider-free planner binds one finalized XNYS session to the exact 1,298
customer-publication population and deduplicates by session, ticker, and family.

First-live ceiling: **2,746 HTTP attempts, zero automatic retries**:

- 1,298 completed-session price requests;
- 1,298 filing-change probes;
- at most 50 changed tickers x three deep fundamental families = 150 requests.

Unknown symbols, a 51st changed ticker, missing or duplicate receipts, stale
sessions, and unplanned response identities fail closed. The plan does not
change scoring, withholding, Fair Value, or certification. The existing atomic
publisher remains the only publication boundary and retains the last valid
snapshot on failure.

Checkpoint recovery is provider-free certified: atomic checksum-bound progress
files bind plan and session identity; only committed receipts resume; missing
request keys are deterministically derived; exact duplicates are idempotent and
conflicting duplicates fail closed. Corrupt checkpoints, process interruption,
storage replacement failure, telemetry tampering, and partial publication were
fault-injected. Automatic provider retries remain zero.

Required decision: approve this ceiling and an exact deployed source SHA through
`DAILY_BUY_NOW_LIVE:<SHA>` only after the transport adapter is bound to the
immutable plan keys and protected Finnhub/Cronitor configuration passes preflight.

## Report Card G2 decision

The fresh decision draft is intentionally non-executable. Scope remains the 20
original immutable signals plus SPY, historical OHLCV/splits/dividends, maximum
61 calls, retries zero, raw-before-normalization, and no ledger write or customer
publication.

Before owner authorization, a provider-free protected validation at the final
source SHA must refresh the primary ledger hash/tip, independent backup hash and
restore proof, CLOSED sentinel identity, finalized XNYS calendar, entitlement,
and canonical plan hash. The failed run `38628414964` claim is consumed and may
not be reused. Stable Gateway package constants must be reconciled before use.

G3 append, G4 scheduling, and public Report Card visibility remain separate.

## Monitoring and durable evidence

Existing code provides sanitized Cronitor event delivery and append-only,
locked SQLite/backup controls. Current evidence does not prove that owner-email
routing received success, failure, and deliberately missed-heartbeat messages.
Those three receipts, plus a fresh backup restore test at the final source SHA,
are required before unattended operation.

Provider-free closure now records redacted completion/failure request hashes,
requires owner email only from a repository variable and persists only its
SHA-256, specifies the independent missed-heartbeat contract, restores the
last-known-good publication byte-for-byte after an injected mid-promotion
failure, and verifies durable bundle copy/restore hashes. External delivery is
still unproven because neither an owner address nor Cronitor URL is hardcoded.

## Exact outstanding approvals

1. External AI non-production fixture authorization after privacy/legal and
   aggregate budget controls are approved.
2. Incremental daily BUY NOW live authorization for the exact 2,746-attempt plan
   and exact deployed SHA.
3. Fresh provider-free G2 protected validation; then a new one-shot G2 acquisition
   authorization for the resulting 61-call plan hash.
4. G3, G4, public Report Card, and R3 deployment approvals remain distinct.
5. Independent visual acceptance and genuine beginner sessions remain human gates.
