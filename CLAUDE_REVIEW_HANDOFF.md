# ATLAS production stabilization and Report Card activation handoff

## Executive decision

- Production customer smoke: **BLOCKED by external secret configuration**. The workflow now requires independent `ATLAS_INTERNAL_QA_PASSWORD` and viewer credentials and fails before browser startup if either is absent or equal.
- Report Card calendar/acquisition/producer/consumer path: **OFFLINE CERTIFIED**. It remains manual-only and cannot append or publish during acquisition.
- Live acquisition, durable append, recurring schedule, and public Report Card: **NOT ACTIVE**.

## Dependency architecture

```text
Streamlit production SHA
  -> independent admin/viewer environment secrets
  -> frame-aware browser crawler
  -> role/ticker/authority/component/lifecycle predicates
  -> screenshots + final mandatory aggregation

exchange_calendars 4.13.2 (XNYS)
  -> manual governed calendar artifact + SHA-256
  -> protected ledger scope + verified timestamped backup
  -> manual Finnhub acquisition (61 base calls for current N=20)
  -> deterministic zero-provider observation producer
  -> disposable consumer validation
  -> separately authorized atomic append
  -> timestamped backup + restore verification
  -> only then, separately authorized daily scheduling
```

## Implemented controls

- Pinned XNYS implementation with holidays, DST, early closes, a 30-minute close-finalization guard, provenance, canonical digest, and deterministic replay.
- Manual calendar workflow with exact token `REPORT_CARD_CALENDAR_PRODUCE_ONCE`.
- Manual acquisition workflow with exact token `REPORT_CARD_ACQUIRE_ONCE`, read-only Actions/content permissions, protected runner/environment, 500-RPM governor, bounded retries, provider telemetry, and no append path.
- Backup discovery requires exactly one timestamped SQLite backup with a valid SHA-256 sidecar and the same logical ledger tip as primary.
- End-to-end offline test covers calendar -> acquisition -> producer -> disposable ledger -> idempotent replay -> backup restore.
- Production browser workflow uses a dedicated admin secret and distinct viewer secret; equality or absence fails with actionable diagnostics.

## Protected-runner evidence

- Primary: `/mnt/atlas_report_card_primary/report-card.sqlite3` on `/dev/sda`.
- Backup: timestamped SQLite plus SHA-256 sidecar under `/mnt/atlas_report_card_backup` on `/dev/sdb`.
- Both hash chains pass with ledger tip `c503983257261e202b3ffc87d1f08ac1b1ea1753cae34319d8171f4c09e2a54a`.
- Activation: `2026-10-08T03:20:17+00:00`; signals: 20; unique tickers: 20; observations: 0.
- Current base provider budget: `3N + 1 = 61` for the documented 20-ticker ledger. Live acquisition performs zero automatic retries; any retry requires separate G5 authorization and a newly stated ceiling.

## Activation sequence

1. Owner configures `ATLAS_INTERNAL_QA_PASSWORD` in the protected GitHub environment with the same value as the production Streamlit admin credential. Do not reuse the viewer password.
2. Run the full production smoke and require all mandatory desktop/mobile customer/admin evidence.
3. Merge the reviewed workflow PR only after CI and owner approval.
4. Dispatch the calendar workflow after the finalized XNYS close and retain its exact run ID, artifact name, and digest.
5. Separately authorize one acquisition; verify ledger hashes remain unchanged and provider telemetry stays within budget.
6. Produce twice from the same evidence and require identical canonical digests.
7. Apply to a disposable ledger; verify idempotency, atomic backup, and restoration.
8. Obtain separate authorization for one protected append.
9. Verify the new primary and backup tips and restore result.
10. Only then authorize a weekday post-close schedule with calendar gating and ordered catch-up. Public Report Card remains OFF.

## Remaining external requirements

- Independent production admin secret is absent.
- PR merge approval is absent.
- Live provider acquisition authorization is absent.
- Protected append authorization is absent.
- Recurring schedule authorization is absent.

## Comprehensive customer-suite differential

The same broad customer/research/navigation suite was executed on both production main
`1cfc27ee9f52a22bd4917c64db95fc2883ccdeed` and this PR. Results were identical:

- Production main: 245 passed, 24 failed.
- PR plus Report Card tests: 276 passed, 24 failed in the broad sweep; the focused release and Report Card gate separately passed 115/115.
- New regressions introduced by this PR: **zero**.

Failure classification:

- 15 missing-fixture failures: retained `CXT`, `SD`, and CRC rows are absent from the local checkout. These are inherited fixture/environment failures, not evidence that the rendered product changed.
- 4 retired source-shape assertions: tests search for superseded literal route/container/banner strings rather than exercising the current contract.
- 2 inherited legacy renderer-fixture failures: synthetic VNext fixtures do not contain the certified authority needed by the current fail-closed renderer, so Ask/AI Brief elements are intentionally not emitted.
- 2 inherited copy-expectation failures: current plain-English MONITOR copy differs from an older unavailable-copy assertion without changing authority.
- 1 inherited authority-precedence contract conflict: a legacy test expects nested certified fields to override an incomplete current evaluation; current fail-closed code retains the incomplete current evaluation. This needs an owner-approved contract reconciliation and must not be silently changed as UI polish.

No product code was changed to conceal these inherited failures. They remain release evidence debt and must be reported independently from the already-certified R1 run `38267208505`.

## Premium-product evidence matrix

| Workstream | State | Evidence boundary |
|---|---|---|
| Home premium hierarchy | VERIFIED BY EXISTING R1 CERTIFICATION; NEW PRODUCTION VISUAL PROOF BLOCKED | Exact production admin secret absent |
| Five-section Research | VERIFIED BY EXISTING R1 CERTIFICATION; NEW PRODUCTION VISUAL PROOF BLOCKED | Exact production admin secret absent |
| Watchlist and Ask | VERIFIED BY EXISTING R1 CERTIFICATION; NEW PRODUCTION VISUAL PROOF BLOCKED | Exact production admin secret absent |
| Customer/admin isolation | IMPLEMENTED — AWAITING CONFIGURATION | Dedicated secret wiring and inequality preflight added |
| Desktop/mobile production screenshots | NOT PROVEN FOR THIS PR | No authenticated production run permitted |
| Calendar and acquisition | OFFLINE CERTIFIED | 115-test gate and deterministic end-to-end replay |
| First live Report Card run | READY — AWAITING AUTHORIZATION | Calendar, provider, and append gates remain separate |
| Public Report Card | OFF | No automatic activation path added |

Route quality scores are intentionally withheld: without a fresh authenticated original-resolution
production capture, assigning 1–10 visual scores would be unsupported.

## Claude review question

Do the independent credential preflight, deterministic calendar identity, ledger-derived acquisition scope, zero-provider producer separation, idempotent append contract, and verified backup restore collectively prevent a false production PASS or an unauthorized/fabricated Report Card observation under every mandatory failure mode represented by the test suite?
