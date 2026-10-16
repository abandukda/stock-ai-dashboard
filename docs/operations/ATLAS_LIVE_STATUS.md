# ATLAS Live Operations Status

**Authoritative as of:** 2026-10-15
**Repository main / deployed runtime:** `b7b53b93c8f13a65b766a23e1db10df148293e3e`
**Production:** [stock-ai-dashboard.streamlit.app](https://stock-ai-dashboard.streamlit.app/)  
**Production-truth correction merged:** [PR #35](https://github.com/abandukda/stock-ai-dashboard/pull/35)

Evidence policy: a merge is not deployment; a provider-free run is not acquisition; a monitor ping is not publication; and repository data is not customer-visible until authenticated production evidence proves it.

## Release scoreboard

| Classification | Component | Current evidence |
|---|---|---|
| **VERIFIED LIVE** | Streamlit service and deployment identity | Direct live inspection on 2026-10-16 found `data-atlas-health="APP_READY"` and exact `data-atlas-source-sha="b7b53b93c8f13a65b766a23e1db10df148293e3e"`. The login surface rendered `V104 Research Candidate & Investment Committee`. |
| **NOT LIVE** | Fresh daily BUY NOW | Latest retained certified session is **2026-10-02**, published **2026-10-04T12:21:38-04:00**. No later live acquisition/publication is verified. |
| **NOT LIVE** | Report Card G2/G3/G4 | Public Report Card remains off; no live G2 acquisition, G3 durable append, or active G4 cycle is recorded. |
| **NOT LIVE** | WS3 expansion | Annual/quarterly pilots exist; broader WS3 acquisition is not operational. |
| **PARTIAL** | Current authenticated customer routes | Runtime QA `38835863054` authenticated `customer_viewer` at exact deployed SHA `b7b53b93…` and proved the four-route navigation contract. Home was captured; Research, Watchlist and Ask content, mobile frames and independent admin isolation remain unproven. |
| **VERIFIED LIVE** | Current customer-visible Home snapshot | Authenticated Home displayed `As of Oct 4, 2026 · 12:21 PM ET` and `BUY NOW INVENTORY 10`. It did not expose a publication digest or finalized-session marker in the visible Home DOM. This differs from the retained 11-name authority and must not be silently reconciled. |

PR #35 is merged repository evidence, not deployment evidence. Its source
marker is absent from the currently rendered production contract, so deployment
and exact-SHA smoke remain open.

## Component ledger

| Component | BUILT | CERTIFIED | DEPLOYED | OPERATIONAL | CUSTOMER VERIFIED | Latest evidence | Blocker / next action |
|---|---|---|---|---|---|---|---|
| Premium UI | YES | YES — R3 candidate `490eae05…`, governed run `38672677869` | YES — `b7b53b93…` | PARTIAL | PARTIAL | Runtime QA `38835863054`, artifact `12019645648`, authenticated `customer_viewer`, exact source and four-route contract. | Capture Research, Watchlist, Ask, mobile frames and a separate `internal_admin` session. |
| Home | YES | YES | YES/UNKNOWN SHA | YES | YES | Authenticated Home displayed Oct 4 freshness and 10 BUY NOW records. | Reconcile the visible count with retained authority; capture exact publication digest after deployment. |
| Research | YES | YES | UNKNOWN | UNKNOWN | NO | Retained NVDA/MSFT/AVT/CRC authority exists. | Capture authenticated authority and financial evidence. |
| Watchlist | YES | YES | UNKNOWN | UNKNOWN | NO | No current production interaction proof. | Run add/search/sort/remove/reload smoke. |
| Ask ATLAS | YES | YES | UNKNOWN | UNKNOWN | NO | No current grounded production response proof. | Capture settled response and authority metadata. |
| BUY NOW | YES | Retained snapshot certified | YES/UNKNOWN SHA | STALE | PARTIAL | Production Home shows Oct 4 timestamp and 10 BUY NOW; retained authority has 11 BUY NOW for session `2026-10-02`, digest `72b37697…`. | Explain count divergence and expose exact digest/session; fresh live acquisition and promotion remain gated. |
| Incremental acquisition | YES | Provider-free PASS | Workflow registered | FAILED CLOSED | N/A | Live [run 38836052667](https://github.com/abandukda/stock-ai-dashboard/actions/runs/38836052667) consumed the approved claim and stopped on request 1 (`A`, completed-session price) with `DATA_UNAVAILABLE`. Attempts: 1; retries: 0; publication writes: 0. | Diagnose the provider-record boundary before preparing a fresh claim. The consumed claim cannot be reused. |
| Daily 6:05 PM ET | YES | Provider-free controls tested | Registered | NO | NO | Dual UTC wakeups, XNYS gate, non-cancelling session lock and incremental-only path are registered. It still stops before acquisition/certification/promotion. | Register and certify the successor publication bridge, then obtain exact live acquisition/publication authorization. |
| Finnhub acquisition | YES | Bounded plan certified | Registered | NO | N/A | Last real retained evidence belongs to the October 2 snapshot. | Do not describe planning run as provider refresh. |
| Report Card G2 | YES | Provider-free only | Registered | NO | NO | Acquisition workflow history contains one failed live run (`38628414964`) at an older source; no successful G2 acquisition exists. | Fresh source-bound validation/package and separate exact live authorization. |
| Report Card G3 | YES | Offline only | Registered | NO | NO | Producer and append workflows each have zero runs; no durable observation append or backup result exists. | Requires successful G2, deterministic bundle validation and separate append authorization. |
| Report Card G4 | Controls only | NO | No active schedule | NO | NO | Report Card workflows remain dispatch-only. | Requires successful G2/G3, restore proof, monitoring proof and schedule authorization. |
| Research financial history | YES | Bounded 11-ticker artifact tests | Deployed projection not customer-verified | Retained/read-only | NO | AVT, BKTI, CODA, CSCO, CTS, DIOD, EXTR, GNE, MSFT and NVDA expose 5 annual/8 quarterly periods; SBC exposes 2/6. Focused suite: 59 passed. | Add source/generation identity to customer manifests; broader 1,298-security coverage requires a separately authorized acquisition. |
| Market Intelligence | YES — compact Market Read | Local evidence/empty-state tests | Present in deployed tree, not authenticated | UNKNOWN | NO | Non-scoring four-index tape and rights-checked headlines; refuses inference when evidence is absent. | A governed official macro-series/calendar contract is required before adding economic claims. |
| Cronitor/email | YES | PARTIAL | YES | PARTIAL | N/A | Test run `38785238561`; owner confirmed Report Card failure email. | BUY NOW completion and missed-heartbeat delivery remain unconfirmed. |
| Commercial acceptance | YES | Automated QA only | N/A | NO | NO | Machine certification passed. | Independent frame review and real five-person beginner study remain open. |

## Consolidated recovery candidate

- Live acquisition run `38836052667` passed all protected identity, storage,
  entitlement-presence and consume-once checks, then failed closed on its first
  transport call. The registered request sent ISO date strings (`2026-10-15`)
  to Finnhub `/stock/candle`; that endpoint's official client contract uses
  Unix timestamps for `from` and `to`.
- The recovery candidate converts only completed-session candle parameters to
  UTC day-start/day-end Unix seconds, rejects session or resolution drift, and
  leaves filing endpoints date-based. A provider-free durable-record diagnostic
  classifies no-data, entitlement, HTTP, schema and normalization failures
  without exposing credentials or making a provider call.
- Stable Customer QA run `38836725643` exposed a separate gateway defect before
  child QA dispatch: `verify_artifact_tree.py` could not import the repository
  `services` package. The candidate invokes it with repository-root
  `PYTHONPATH` and `python3`; no customer assertion is weakened.
- WS3 archive manifests now fsync immutable raw/metadata/summary files and bind
  per-file digests, batch identity, evidence source and execution source. This
  improves runner-local durability but does not yet prove an independent
  off-runner archive for the 1,298-security expansion.
- Home Market Read accepts only explicitly supplied, non-scoring official macro
  evidence from BLS, BEA, Federal Reserve and Treasury contracts. It performs no
  live fetching and makes no unsupported forecast.

## Authoritative retained publication

- Finalized session: `2026-10-02`
- Publication timestamp: `2026-10-04T12:21:38-04:00`
- Publication population: `1,298`
- BUY NOW: `11` — AVT, BKTI, CODA, CSCO, CTS, DIOD, EXTR, GNE, MSFT, NVDA, SBC
- Source: `aa12ff9e89c1ac72e20aadad41decfba9a3d774d`
- Candidate run: `37216506983`
- Publication digest: `72b37697b2f4fc5dabd5438c1a3bb7c068cd12e86253b64e37b8a642c310bf17`

## Pending correction outcome

### Consume-once acquisition claim repair — registered and rehearsed

- PR #37 merged at `6ce1efe2bf3551623d297f6985c65416a4ebefb3` and adds an atomic `O_EXCL` claim ledger under the durable protected
  checkpoint root. A claim is persisted and directory-fsynced before the first
  provider request; it is never removed, including after crashes or failures.
- Each claim binds claim ID, registered source SHA, plan SHA-256, finalized
  session, 1,298-member scope, 2,746 maximum requests, and zero retries.
- Manual execution uses a dispatch-scoped enablement value. It does not set the
  repository/environment daily-live variable; the 6:05 PM scheduler continues
  to require that global variable to remain `false`.
- Protected run `38829162008` completed successfully. The acquire job was
  skipped; the protected runner verified source binding, distinct durable roots,
  claim persistence, duplicate rejection and the cleanup/finalization entrypoint.
  It made zero provider calls and zero production writes. Plan artifact digest:
  `7d5c032d434ad9e5ff900e854cb53fe4d3379cdb2d4a3e8f67d67f029a9d06cc`;
  rehearsal artifact digest:
  `1522da8b998f3d4347817d4e0182ec30ea3d8f66bb4956fa682c0ddffbbc98bd`.
- The prepared live claim `oct15-2026-live-38829162008-01` is bound to source
  `6ce1efe2bf3551623d297f6985c65416a4ebefb3`, plan
  `df03707da00c253cf089596e72515f5ceeb2d53b6ed46dd50155bfa59f9fa187`,
  finalized session `2026-10-15`, 1,298 members, maximum 2,746 requests and
  zero retries. Preparing the claim does not consume it or authorize execution.

### First live acquisition attempt — failed safely before transport

- Owner-authorized run `38830427157` used the exact source, session, plan,
  membership, manual-enablement and claim inputs approved for
  `oct15-2026-live-38829162008-01`.
- Protected checkout, credential presence, storage variables, membership and
  plan validation succeeded. The transport entrypoint then rejected execution
  with `INCREMENTAL_LIVE_OPERATION_DISABLED`: the workflow correctly supplied
  `ENABLE_ATLAS_INCREMENTAL_ONCE:<claim-id>`, while the Python entrypoint still
  compared the value with the obsolete literal `true`.
- The rejection occurred before durable claim consumption and before provider
  adapter construction. Actual Finnhub calls: `0`; successful securities: `0`;
  unsuccessful securities: `0`; raw provider records: `0`; ledger writes: `0`;
  customer publication writes: `0`. The claim will not be reused.
- Diagnostic artifact: `atlas-incremental-buy-now-acquisition-38830427157`,
  artifact ID `12016798109`, archive SHA-256
  `b4140d7e33dc6c906a3a5ff4136fad6ab1b398f11a44142b68e612401905ccd9`.
- October 15 acquisition and certification remain **NOT LIVE**. A corrected
  exact-source rehearsal and a fresh claim-specific owner authorization are
  required before another licensed attempt.

### Corrected exact-source protected rehearsal — PASS

- PR #38 merged as `b7b53b93c8f13a65b766a23e1db10df148293e3e`.
- Protected run `38832122252` passed against that exact source. The plan job
  verified the immutable 1,298-security membership, 2,596 planned requests,
  2,746 ceiling, October 15 finalized session and zero-provider plan. The live
  acquire job was skipped.
- On `atlas-worker-1`, the protected rehearsal verified distinct configured
  raw/checkpoint roots, imported the registered transport entrypoint, atomically
  persisted a rehearsal claim, rejected its duplicate, finalized it without
  reopening it, and confirmed that no Finnhub credential was exposed.
- Provider calls: `0`; production writes: `0`; customer publication writes:
  `0`. The unattended scheduler remained disabled and was not dispatched.
- Plan artifact: `atlas-incremental-buy-now-plan-38832122252`, ID
  `12018320286`, archive SHA-256
  `fd8d95a57abc2be875de7e3b24d8939bb92d2c6e59c8e63867b5786bb887e23b`.
  Rehearsal artifact: `atlas-incremental-buy-now-rehearsal-38832122252`, ID
  `12018170803`, archive SHA-256
  `cdf6587287cf3f34fb46c845311ccbf7d189065cc2720ea21bcb483a608d36dc`.
- Fresh unconsumed claim ID: `oct15-2026-live-38832122252-01`; source
  `b7b53b93c8f13a65b766a23e1db10df148293e3e`; plan
  `df03707da00c253cf089596e72515f5ceeb2d53b6ed46dd50155bfa59f9fa187`;
  scope SHA-256
  `e78d56f93569115413c90d30a0707aa632ecc1a631c8cd7fdad15cce365ab326`.
  Preparation does not consume or authorize this claim.

### Approved October 15 live acquisition — failed closed on first record

- Owner-approved protected run `38836052667` executed at exact source
  `b7b53b93c8f13a65b766a23e1db10df148293e3e` with claim
  `oct15-2026-live-38832122252-01`. Source, session, plan, 1,298-member
  population, 2,596 planned requests, 2,746 ceiling, credential presence,
  durable roots and claim scope all passed before transport.
- The consume-once claim was atomically persisted and finalized; it cannot be
  reused. The run stopped on the first request, ticker `A`, family
  `completed_session_price`, because the canonical adapter returned
  `DATA_UNAVAILABLE`. Actual attempts: `1`; successful securities: `0`;
  unsuccessful securities: `1`; retries: `0`.
- The unavailable provider record was persisted raw-first on protected durable
  storage. No certification handoff ran and no customer publication, ledger or
  production data was written. The retained October 2 customer snapshot is
  unchanged.
- Diagnostic artifact `atlas-incremental-buy-now-acquisition-38836052667`, ID
  `12019665699`, archive SHA-256
  `593350303da0cd4164ba9861f035a722be3f885ea9937103aefc321c7915ff61`.
- A new exact claim and owner decision are required only after the provider
  `DATA_UNAVAILABLE` boundary is diagnosed; this failed claim must not be
  retried.

- PR #35 removes scheduled triggers from the obsolete full-universe workflow.
- Its replacement coordinator exclusively builds the governed 1,298-security
  incremental plan under a non-cancelling concurrency lock and runs the
  protected provider-free rehearsal.
- It intentionally cannot acquire or publish. The current incremental executor
  ends at `ACQUISITION_COMPLETE_PUBLICATION_NOT_PERFORMED`; the unchanged
  scoring/certification and atomic-promoter bridge remains a real blocker.
- Local verification: 131 focused tests passed, both workflow files parsed as
  YAML, Python compilation passed, and `git diff --check` passed.

## PR #36 publication-integrity reconciliation

- Retained provider-free replay input: all 41 immutable acquisition shards from
  governed run `37216506983`; governed customer membership `1,298/1,298`;
  missing acquisition records `0`; provider calls `0`; production writes `0`.
- Evaluation result: `FULL_UNIVERSE_CERTIFIED`; forward/reverse candidate
  digest `e3cf999be9984aebbef5072884f7a79fd6e377b50dd9a295670c109fd7c6e935`;
  all 1,298 records compared with zero analytical, numerical, action, order, or
  provenance differences.
- Publication population: `1,298` expected, `1,298` observed, `1,223`
  publishable, `75` explicitly withheld, `0` missing, `0` duplicate, `0`
  unexpected, and `0` unexplained. Reconciliation digest:
  `f1a1d53b65dd2880142f6363cb118f3bd1bb0f88a1d33a9c03e7b5b05cfcc7b0`.
- Withheld certification states: `47 REVIEW_REQUIRED`; `28
  INSUFFICIENT_INPUTS`. The complete withheld ticker inventory is: AENT, ALTG,
  AMGN, ARAY, ASPS, AXR, BLFS, BNL, BWXT, C, CARG, CBFV, CBRE, CELH, COST,
  CPSS, CSX, CTRI, CURI, CWCO, CYH, EXPO, EXTR, FHN, FTDR, FTEK, HAE, HDSN,
  HTLD, JOB, KEY, KRO, LFCR, LGCY, LSTR, MGRC, MHH, MTZ, NAII, NTRB, NXT,
  OOMA, OSPN, PAMT, PEP, PGR, PLAY, PPIH, RMD, ROOT, RSG, SFST, SIEB, SKYW,
  SLP, SNPS, SON, SPOK, SWAG, TJX, TRNS, TRS, TSLA, UCB, UHAL, ULH, UTHR,
  VIRC, VLTO, WBD, WDAY, WERN, WHR, WTFC, WYY.
- The reconciliation contract now rejects any missing, duplicate, unexpected,
  or unexplained-withholding row before a certification handoff is staged.
- Home now presents the governed publishable BUY NOW inventory independently
  from its maximum ten featured cards. The retained snapshot therefore reports
  inventory `11` while continuing to render at most ten featured opportunities.
- The protected daily workflow registers the incremental certification bridge
  and existing atomic promoter contracts while keeping live acquisition and
  publication disabled.

## Required handoff update

Every future operational handoff must update this file with the exact source SHA, run timestamp, run ID, artifact ID/digest, provider-call count, finalized session, publication result, and authenticated customer result. Lifecycle states may advance only from direct evidence.
