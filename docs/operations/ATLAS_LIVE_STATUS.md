# ATLAS Live Operations Status

**Authoritative as of:** 2026-10-15  
**Repository main:** `6ce1efe2bf3551623d297f6985c65416a4ebefb3`
**Production:** [stock-ai-dashboard.streamlit.app](https://stock-ai-dashboard.streamlit.app/)  
**Production-truth correction merged:** [PR #35](https://github.com/abandukda/stock-ai-dashboard/pull/35)

Evidence policy: a merge is not deployment; a provider-free run is not acquisition; a monitor ping is not publication; and repository data is not customer-visible until authenticated production evidence proves it.

## Release scoreboard

| Classification | Component | Current evidence |
|---|---|---|
| **VERIFIED LIVE** | Streamlit service, customer role, Home and navigation | Authenticated production inspection on 2026-10-15 rendered the Premium dark Home and all four customer navigation labels. The hidden contract reported role `customer_viewer`, active route `Home`, and routes `Home|Research|Watchlist|Ask ATLAS`. |
| **NOT LIVE** | Fresh daily BUY NOW | Latest retained certified session is **2026-10-02**, published **2026-10-04T12:21:38-04:00**. No later live acquisition/publication is verified. |
| **NOT LIVE** | Report Card G2/G3/G4 | Public Report Card remains off; no live G2 acquisition, G3 durable append, or active G4 cycle is recorded. |
| **NOT LIVE** | WS3 expansion | Annual/quarterly pilots exist; broader WS3 acquisition is not operational. |
| **UNKNOWN** | Current deployed Streamlit SHA | Production's live `customer-navigation-contract` does **not** contain `data-atlas-source-sha`; therefore the newly merged `225491ff…` tree is not proven deployed. The most recent exact runtime evidence remains `0582396c…`. |
| **VERIFIED LIVE** | Current customer-visible Home snapshot | Authenticated Home displayed `As of Oct 4, 2026 · 12:21 PM ET` and `BUY NOW INVENTORY 10`. It did not expose a publication digest or finalized-session marker in the visible Home DOM. This differs from the retained 11-name authority and must not be silently reconciled. |

PR #35 is merged repository evidence, not deployment evidence. Its source
marker is absent from the currently rendered production contract, so deployment
and exact-SHA smoke remain open.

## Component ledger

| Component | BUILT | CERTIFIED | DEPLOYED | OPERATIONAL | CUSTOMER VERIFIED | Latest evidence | Blocker / next action |
|---|---|---|---|---|---|---|---|
| Premium UI | YES | YES — R3 candidate `490eae05…`, governed run `38672677869` | PARTIAL/UNKNOWN SHA | YES | PARTIAL | Authenticated dark Home and four customer routes rendered on 2026-10-15; live SHA marker was absent. | Deploy `225491ff…`, then run authenticated exact-SHA route smoke. |
| Home | YES | YES | YES/UNKNOWN SHA | YES | YES | Authenticated Home displayed Oct 4 freshness and 10 BUY NOW records. | Reconcile the visible count with retained authority; capture exact publication digest after deployment. |
| Research | YES | YES | UNKNOWN | UNKNOWN | NO | Retained NVDA/MSFT/AVT/CRC authority exists. | Capture authenticated authority and financial evidence. |
| Watchlist | YES | YES | UNKNOWN | UNKNOWN | NO | No current production interaction proof. | Run add/search/sort/remove/reload smoke. |
| Ask ATLAS | YES | YES | UNKNOWN | UNKNOWN | NO | No current grounded production response proof. | Capture settled response and authority metadata. |
| BUY NOW | YES | Retained snapshot certified | YES/UNKNOWN SHA | STALE | PARTIAL | Production Home shows Oct 4 timestamp and 10 BUY NOW; retained authority has 11 BUY NOW for session `2026-10-02`, digest `72b37697…`. | Explain count divergence and expose exact digest/session; fresh live acquisition and promotion remain gated. |
| Incremental acquisition | YES | Provider-free PASS | Workflow registered | NO | N/A | PR #37 merged as `6ce1efe2bf3551623d297f6985c65416a4ebefb3`. Protected [run 38829162008](https://github.com/abandukda/stock-ai-dashboard/actions/runs/38829162008) passed the exact-source plan and durable consume-once rehearsal: 1,298 symbols, 2,596 planned requests, 2,746 ceiling, plan `df03707da00c253cf089596e72515f5ceeb2d53b6ed46dd50155bfa59f9fa187`, zero calls and zero writes. | Requires separate exact owner authorization for the new unique live claim. No October 15 evidence has been acquired and no customer publication changed. |
| Daily 6:05 PM ET | YES | Provider-free controls tested | Registered | NO | NO | Dual UTC wakeups, XNYS gate, non-cancelling session lock and incremental-only path are registered. It still stops before acquisition/certification/promotion. | Register and certify the successor publication bridge, then obtain exact live acquisition/publication authorization. |
| Finnhub acquisition | YES | Bounded plan certified | Registered | NO | N/A | Last real retained evidence belongs to the October 2 snapshot. | Do not describe planning run as provider refresh. |
| Report Card G2 | YES | Provider-free only | Registered | NO | NO | 20-signal/SPY architecture; 61-call ceiling; CLOSED sentinel. | Fresh source-bound package and separate live authorization. |
| Report Card G3 | YES | Offline only | Registered/unknown | NO | NO | No durable observation append verified. | Requires successful G2 and separate append authorization. |
| Report Card G4 | YES | Provider-free only | Registered/unknown | NO | NO | No unattended cycle verified. | Requires G2/G3, backup/restore, alert proof, and scheduling authorization. |
| WS3 Research | YES | Pilot evidence only | Registered | NO | NO | 147 annual filings; 447 reconciled quarterly periods. | Prove customer projection lineage; authorize later batches separately. |
| Cronitor/email | YES | PARTIAL | YES | PARTIAL | N/A | Test run `38785238561`; owner confirmed Report Card failure email. | BUY NOW completion and missed-heartbeat delivery remain unconfirmed. |
| Commercial acceptance | YES | Automated QA only | N/A | NO | NO | Machine certification passed. | Independent frame review and real five-person beginner study remain open. |

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
