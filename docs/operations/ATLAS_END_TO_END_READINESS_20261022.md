# October 22 end-to-end readiness — review branch

Base main: `1e9b53a5060f3a35e68c089f5b5df911370ea8ab`.
This change is a provider-free integration increment, not a completed live release.
No acquisition, model call, original-host access, ledger write, deployment or publication is authorized by this document.

## Contract and configured transcript authority

The uploaded `Finnhub_Signed (1)(1).pdf` was read in full, including Appendix A.
The Data Feeds clause permits commercial website/mobile display, internal derived analysis and contract-period local storage. Raw API/machine-readable redistribution is restricted. Beta display is not categorically prohibited. Credentials must remain server-side. Contract scope and execution approval are separate.

Appendix A has 51 REST endpoints. The existing display matrix represents 41. Its ten unrepresented endpoints are `/search`, `/stock/symbol`, `/stock/market-status`, `/stock/market-holiday`, `/stock/profile`, `/news`, `/stock/financials`, `/calendar/ipo`, `/stock/historical-employee-count`, `/bulk-download2`. Their presence in the contract does not automatically register acquisition or display adapters. Two WebSocket connections are described in Data Feeds; they are not a transcript entitlement.

The matrix already covers requested quote/candle, profile, ratios, reported financials, recommendation/target, estimate, earnings/calendar, news/filings and split/dividend families. Coverage is not proof of endpoint entitlement responses, normalization completeness, current production ingestion, or certification. Do not label split-adjusted price returns total returns without dividend treatment.

Transcript vendor configuration is **EarningsCall**: `https://v2.api.earningscall.biz`, provider `earningscall`, repository secret reference `EARNINGSCALL_API_KEY` in earnings QA, provider-shadow and Finnhub-certification workflows. These are public mapping names, not credential values. Secret existence/value/current entitlement cannot be established through these repository reads. No retrieved payment receipt substantiates the approximately $80 subscription; do not substitute FMP or Quartr. Finnhub Appendix A does not include transcripts.

## Code and integration result

- New pure producer `research_history_ingestion.build_history_bundle` admits Finnhub candle arrays into the existing source/hash-bound Research read model. It validates numeric OHLCV, order/duplicates, XNYS continuity, finalized-session currentness and explicit adjustment-evidence identity; it returns a bundle without any filesystem or network operation. Adjustment declarations require independent verification by the authorized caller; a nonempty evidence ID alone does not certify the adjustment.
- Mock round-trip proves the actual read model consumes the result and retains contextual/non-scoring authority. No real provider acquisition or approved private delivery has occurred.
- Transcript cache partitions include endpoint, account, license and adapter identity using an opaque process-local keyed digest. Missing/denied transcripts are not indefinitely cached. Transcript availability is now separately recorded from summary status.
- Earnings QA separates credential-free PR/offline tests from owner/manual/main/exact-SHA acquisition. External AI requires a second exact-SHA authorization input and receives no key when disabled. The cache probe no longer repeats paid AI generation.
- Daily coordinator acceptance is narrowed to 18:00–18:30 America/New_York. Existing dual UTC wakeups remain unchanged. No schedule is enabled or infrastructure changed by execution of this review branch. Missed deadlines must fail closed and alert rather than publish late.
- Persistent transcript/summary storage, cross-process deduplication, bounded correction/revision refresh, certified-results/estimate/historical-guidance comparison and full Research/BUY NOW delivery remain incomplete. The current transcript cache is in-memory; do not claim fetch-once across restarts.

## Production truth and blockers

Latest run `39811948257` deployed exact base main, authenticated the viewer, saved 27 screenshots, and failed `REQUIRED_RESEARCH_FAILED_NVDA`. Required checks: 34/36; supplemental diagnostic captures: 4/4, not acceptance.

| Category | Exact evidence / blocker | Next action / owner |
|---|---|---|
| Code | Research loader only reads retained bundles; `research_refresh_execution.execute_live` always rejects, even with live flag | Review this admission producer, then implement/register protected acquisition-to-delivery orchestration under separate review; engineering |
| Configuration | No admitted production NVDA history; missing root vs missing files vs pins is not distinguished by QA | Read-only production root/pin and retained-file integrity inspection; deployment owner |
| Infrastructure | Original shutdown initiator unproven; no fresh kernel/service/reboot or independent backup receipt | Execute existing read-only collector on original host; owner with host access |
| Provider entitlement | Signed Finnhub display authority confirmed; current endpoint responses not probed | Approve bounded exact-source endpoint acquisition separately; owner |
| Data integrity | 35-row retained projection reproduces 15 historical admissions but zero current; not full 6,033 inputs | Approve already-reviewed two-archive hosted hash verification, then real retained certification; owner/engineering |
| Authorization | No approved current acquisition, production bundle delivery/promotion, ledger append or publication | Separate scope/SHA/hash packages; owner |
| Autopilot | Run 39802739094 saved branch `codex/autopilot-39802739094`, head `fd47469907917701d7f96802109f8c3da29ddf00`; PR creation denied by Actions policy | Review/reuse patch through connector/manual PR; do not expand Actions permissions |

## Six workstreams and beta acceptance

These stages describe the overall capability, not just a green helper test.

| Workstream | BUILT | TESTED | MERGED | DEPLOYED | LIVE VERIFIED |
|---|---|---|---|---|---|
| Home | Premium layout/digest exists | Prior offline and production journeys partial | Through base main | Exact base source verified | Partial; current data and full visual parity open |
| Research | Simple/detailed UI; new admission bridge on review branch | Mock source-to-read-model integration and existing regressions | Existing UI yes; new bridge no | Existing UI yes | FAIL NVDA chart; META/ANET full coverage open |
| Certified data | Planning, normalization/certification tools; retained evidence | Historical 15 admissions / current 0 on 35-row projection | Existing tools yes; window change pending | No current snapshot | NO current full-universe cycle |
| AI summarization | Deterministic intermediate; source-span grounded transcript runtime | Provider-free grounding/adversarial checks | Existing runtime yes; cache repair pending | Genuine external synthesis unverified | NO genuine production AI milestone |
| Earnings/transcripts | EarningsCall adapter/index/derived projection | Mock integration; separate authorization gates on branch | Existing adapter yes; repairs pending | Current provider/summary delivery unverified | NO production transcript intelligence proof |
| Report Card | Private dashboard/gated tooling | Historical 20 signals / 0 observations, not fresh ledger proof | Existing code yes | Public OFF | NO certified first observation cycle |
| Beta separately | Viewer/admin isolation, editable Watchlist surfaces exist | Prior customer isolation checks | Existing code yes | Viewer surface yes | Unique individual accounts, revocation, cross-user persistence/isolation NOT certified |

## Tonight's decision and ordered approvals

**Internal Report Card evidence launch: NO-GO. Public activation remains OFF.**
Need fresh immutable ledger/WAL and independent-backup verification, genuine approved price evidence including AMZN/MPC/VLO/SPY, actual registration/publication timing, reviewed prospective entry/horizon/benchmark methodology, and separately approved observation bundle/append. Never rewrite original signal timing.

1. Merge: review exact PR head only after governed CI passes; this document does not grant merge authority.
2. Retained evidence: separately authorize reviewed two-archive verification at exact main; existing runbook explicitly requires separate execution approval. This is provider-free and hosted, not Contabo migration.
3. Finnhub acquisition: exact code/package/scope, ticker/family/session ranges, adjustment basis, request cap, reasonable-use rate, no implicit retries, immutable cache receipts. No raw-feed customer export. Current protected environment and source/backup integrity must be proven before selecting an execution host.
4. Private Research delivery: separately approve installation/path/pins and deployment; read-only QA must observe admitted current payload and chart at desktop/tablet/mobile. Code-only mock tests cannot approve this.
5. Transcript acquisition and external AI: separate inputs/approvals; confirm actual subscription entitlement and allowed model processing; scope AAPL/MSFT/NVDA metadata-first, no automatic pricing inference. Persistent cache/versioning and comparison pipeline still need implementation.
6. Publication and Report Card append: separate later approvals, backup/idempotency/rollback evidence and financial acceptance. No activation based on CI alone.

Original Home and two Research concepts were recovered in the existing visual evidence pack; Report Card references and prior UX documents were also recovered. Repository Claude inventory and R2 handoff are historical acceptance inputs, not proof all consultant findings were supplied or closed. Latest real screenshots remain controlling. No new before/after UI claim is made by this backend release.
