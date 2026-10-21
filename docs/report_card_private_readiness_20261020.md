# Private Report Card readiness — October 20, 2026

## Missing chart diagnosis and repair

Durable read-only run `39520043865` reached the selected signal detail and then
timed out waiting for `report-card-price-chart`. The renderer deliberately emits
`report-card-chart-unavailable` when no verified history exists. The selector is
correct; the original failure was an evidence wiring error, not a chart drawn
from zero observations or a lost selection.

The original capture run is `37721927398`. It consumed publication artifact
`atlas-finnhub-full-universe-final-37553164176` from run `37553164176` and closure
run `37698025363`. The source archive SHA-256 is
`ecf66bcd49a72bbd85f76365b9005a43622f87494b2aa4468f3a1ef3c0bcf4f1`.
Its `market_full_scan.json` has all 20 exact original candidate/snapshot matches.
The existing acquisition shards hold their completed daily bars. The current
repository sample pool contains none of these exact original snapshots.

The read-only repair restores these retained artifacts, checks pinned file
hashes and source identities, matches each immutable signal snapshot, and joins
its historical OHLCV evidence ID to the corresponding certified shard. It writes
only an ephemeral display projection under the QA workspace. Original decisions,
scores, certified evaluations, production ledgers and public gates are unchanged.
All existing chart availability, provenance, freshness and non-scoring QA
assertions remain required. DOM, selected-signal facts and a screenshot are now
saved before the chart assertion, so a future failure is diagnosable.

Historical charts are educational context, not prospective performance.
Recovered bars end October 6. They cannot manufacture observations after the
October 8 activation. An operational historical chart does not prove that an
observation has been recorded.

## First genuine observation: separate data and authorization gates

1. **G1: current read-only validation.** Bind the exact reviewed release source,
   ledger checksum/tip, isolated primary and backup mounts, verified backup,
   owner-controlled CLOSED sentinel and current governed XNYS calendar/cutoff.
   Historical chart lineage and customer-publication proof are distinct. The
   recovered source bundle proves the original chart snapshot bindings; it does
   not prove a contemporaneous October 8 customer-visible publication. The G1
   customer-publication reconciliation remains UNPROVEN for all 20 signals until
   authentic exact-identity publication evidence is supplied. This does not block
   internal observation eligibility and must not be relabeled as publication proof.
2. **Certified market evidence.** The first registered one-session target is
   October 9 for this cohort; the five-session target is October 15. Required
   evidence includes the exact due ticker closes, SPY reference and horizon
   closes, explicit split/dividend treatment, finalized regular-session timing,
   provider/instrument/as-of/retrieved-at/currency provenance, and calendar
   identity. Existing October 6 history is insufficient. Missing securities must
   remain explicit unavailable records; neither prices nor observations may be
   inferred from charts or historical indicators.
3. **G2: acquisition only if separately authorized.** If the required later
   evidence is not already retained, build a fresh release binding from current
   G1 facts and the approved entitlement configuration. The bounded plan has
   20 due tickers plus SPY, at most 61 provider requests, zero automatic retries,
   no ledger writes and no customer publication. The exact one-use token is
   `REPORT_CARD_ACQUIRE_ONCE:<authorization_package_sha256>`. The package must
   quote the reviewed source, approved validation run/artifact, calendar, ledger
   tip, entitlement hash and claim. An old package from another source cannot
   authorize this release. G2 opens/closes the sentinel only inside its authorized
   execution and does not append observations.
4. **Produce the bundle without providers.** Dispatch the observation producer
   with the exact governed market-evidence run/artifact, registered horizon and
   explicit `authorize_bundle_production=true`. It produces a deterministic
   bundle covering every signal and binds activation time and prior ledger tip.
5. **G3: separately authorize the actual ledger append.** Review the produced
   bundle and its canonical SHA-256, then use the exact token
   `REPORT_CARD_APPEND_ONCE:<bundle_sha256>` with its source run/artifact. The
   sentinel must be CLOSED before and after append. The append must verify
   all-signal coverage, immutable signal identity, mature finalized sessions,
   idempotency, zero provider calls, atomic append and independent backup/restore.
   Re-run read-only UI/ledger QA afterward to prove real observations and returns.

The entitlement file is `config/report_card_g2_entitlement_20261014.json`; its
canonical approved SHA-256 is
`161b2799b0ea935185d5fddcd53ffbf3fdd755d6a939d3898e0effe58c8c83d4`.
Its existing owner attestation and endpoint permissions must still be valid at
execution. Workflow environment review is an additional gate, not a substitute
for the exact one-use authorization token.

G2, bundle production, G3, scheduling and public publication are separate
authorizations. None is granted by the current diagnostic/repair request.
Public Report Card activation remains OFF throughout.

## Deployment boundary

The durable workflow exercises the real production ledger **read-only** through
a runner-local authenticated private UI. Streamlit production screenshot QA
separately checks customer isolation and the OFF preview. This does not deploy
the private durable ledger or retained licensed data into the public Streamlit
filesystem. Any separate hosting, durable mount, credential or network change
needed for a permanently reachable private UI requires owner authorization.
