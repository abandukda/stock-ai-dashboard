# ATLAS Live Operations Status

**Authoritative as of:** 2026-10-15  
**Repository main:** `225491ff82138b95840e75149fad2137c22716a8`
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
| Incremental acquisition | YES | Provider-free PASS | Workflow registered | NO | N/A | [Run 38785971147](https://github.com/abandukda/stock-ai-dashboard/actions/runs/38785971147): protected rehearsal succeeded, acquisition skipped, 1,298 symbols, 2,596 planned requests, 2,746 ceiling, plan `8aa6a83b5a6eaf14f61f4d99b82657d1a1040b131fdf2bfc8eaae127a5a25b2e`, zero calls. | Requires a fresh current-source one-time authorization; executor currently stops at non-publishing certification handoff. |
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

- PR #35 removes scheduled triggers from the obsolete full-universe workflow.
- Its replacement coordinator exclusively builds the governed 1,298-security
  incremental plan under a non-cancelling concurrency lock and runs the
  protected provider-free rehearsal.
- It intentionally cannot acquire or publish. The current incremental executor
  ends at `ACQUISITION_COMPLETE_PUBLICATION_NOT_PERFORMED`; the unchanged
  scoring/certification and atomic-promoter bridge remains a real blocker.
- Local verification: 131 focused tests passed, both workflow files parsed as
  YAML, Python compilation passed, and `git diff --check` passed.

## Required handoff update

Every future operational handoff must update this file with the exact source SHA, run timestamp, run ID, artifact ID/digest, provider-call count, finalized session, publication result, and authenticated customer result. Lifecycle states may advance only from direct evidence.
