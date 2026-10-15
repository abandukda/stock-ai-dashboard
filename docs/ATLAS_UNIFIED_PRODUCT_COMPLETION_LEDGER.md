# ATLAS unified product completion ledger

Status date: 2026-10-14 (America/New_York)

This is the single release ledger for Premium R3, daily BUY NOW operations,
Research evidence, Report Card observations, monitoring, and commercial
acceptance. A green component test does not change an operational state in this
ledger without the corresponding immutable runtime evidence.

## Frozen engineering candidate

- Base: `0a8ee5bf8137378a2d8e10ccd0c4f78a5a0830ed`
- Branch: `codex/premium-r3-integration`
- Governed predecessor: `4e18a46514ef19ae6533c935a7a8a1403740fefc`
- Governed predecessor run: `38663987517` (`144/144`, screenshots `200/200`, provider calls `0`)
- Current candidate: recorded by the release report after the truthful-source correction.
- Production deployment: not authorized by this ledger.

## Product state

| Capability | Actual state | Evidence / next gate |
|---|---|---|
| Premium Home | Implemented on the R3 review branch | Exact-SHA browser recertification is required after the truthful-source correction. |
| Certified Research authority | Preserved | The governed predecessor passed ticker, six-pillar, authority, and withheld-state checks. |
| Grounded model synthesis | Provider-gated implementation only | It is not called by Home, Research, Watchlist, or Ask. Activation and route integration remain blocked pending stronger semantic grounding and protected model approval. |
| Daily BUY NOW | Scheduled workflow registered; live cycle not active/proven | Latest current-main run `38662537315` was provider-free. The retained customer publication is still run `37216506983`, generated 2026-10-04. |
| Report Card G2 | Failed one-shot; no certified acquisition artifact | Run `38628414964` failed. A fresh source/ledger-bound one-shot package is required; the previous claim must not be reused. |
| Report Card G3 | Not executed | Observation count is zero. Customer outcomes must remain pending. |
| Report Card G4 | Not active | Registration and external dead-man monitoring require separate approval after a successful G2/G3 cycle. |
| Public Report Card | OFF | Must remain OFF until separately authorized. |
| Human commercial acceptance | Not performed | Five genuine participant sessions and independent visual review remain required. |

## Truth and safety invariants

1. Deterministic retained-evidence text must never be labelled model-generated.
2. Model output cannot set or modify Action, Fair Value, Opportunity,
   Confidence, six-pillar values, publication eligibility, or historical
   signals.
3. A retained snapshot is never labelled as a new daily refresh.
4. Report Card returns and success rates remain unavailable until a deterministic
   observation bundle has been durably appended and independently verified.
5. External provider acquisition, protected-ledger mutation, recurring
   scheduling, and production deployment retain separate exact-scope approvals.

## Consolidated protected decisions still required

### Daily BUY NOW live refresh

Approve one exact-source eligible-session execution only after confirming:

- `ATLAS_DAILY_BUY_NOW_LIVE_ENABLED=true`;
- `ATLAS_DAILY_BUY_NOW_AUTHORIZATION=DAILY_BUY_NOW_LIVE:<exact-main-sha>`;
- protected `FINNHUB_API_KEY` and Cronitor URL are present;
- the 6,033-security, six-family plan and its worst-case HTTP-attempt ceiling
  are accepted;
- atomic publication retains the last known-good snapshot on any failure.

### Report Card G2

Issue a fresh one-shot package bound to current source SHA, protected ledger
hash/tip, backup hash, finalized XNYS calendar, entitlement, and scope:

- 20 due tickers plus SPY;
- OHLCV, split, and dividend evidence only;
- maximum 61 calls; retries `0`;
- raw evidence only; no ledger append, customer publication, or schedule;
- sentinel returns unconditionally to `CLOSED`.

The consumed/failed package from run `38628414964` must not be reused.

### Model-backed intelligence

Approve a protected model adapter only after provider, privacy, retention,
cost, and latency review. The production call remains separately gated per
request and cached by evidence/model/schema identity. Route integration must
first add semantic entailment tests beyond citation, number, entity, and
direction checks.

### G3, G4, and production release

- G3: approve only an exact deterministic bundle SHA after successful G2.
- G4: approve only after one G2/G3 cycle, backup restore, and Cronitor success,
  failure, and missed-heartbeat delivery are proven.
- Production: approve only a newly governed exact SHA after all integration
  changes and independent commercial acceptance evidence are frozen.

