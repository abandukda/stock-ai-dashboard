# ATLAS Live Operations Status

**Authoritative as of:** 2026-10-18
**Repository main:** `0758fac72209ab0642e9f1a431db092d1a699119`

**Verified deployed runtime:** `e838d05b3c92563c514d4d185365b4c8e97bfdba`
**Production:** [stock-ai-dashboard.streamlit.app](https://stock-ai-dashboard.streamlit.app/)  
**Production-truth correction merged:** [PR #35](https://github.com/abandukda/stock-ai-dashboard/pull/35)

Evidence policy: a merge is not deployment; a provider-free run is not acquisition; a monitor ping is not publication; and repository data is not customer-visible until authenticated production evidence proves it.

## Milestone 4 integrated candidate — 2026-10-18

- Branch `codex/milestone4-integrated` is stacked on the unmerged PR #73 head
  `d8cfeda5ad9592a51c0c18211de645c44148f051`. It is a review candidate only:
  not merged, deployed, operational, or customer verified.
- Research V2 now builds an evidence-bound five-minute dossier covering the
  business, financial direction and meaning, valuation, licensed Wall Street
  context, catalysts, risks, conditional bull/base/bear scenarios, thesis-change
  conditions, and explicit limitations. Missing inputs remain unavailable;
  deterministic synthesis is labelled non-scoring and external AI stays off.
- Home now has a source-bound market-intelligence contract for verified index,
  sector, event, reproducible-analogue, and conditional-watchpoint evidence.
  It discloses unavailable evidence instead of inventing current conditions.
- The independent Research refresh implementation is cache-first and fully
  separated from BUY NOW, publication, and Report Card authority. Its maximum
  cold-cache plan is 25 tickers x nine evidence families = 225 intents,
  concurrency one, zero retries. PLAN/REHEARSAL are provider-free and durable;
  LIVE is implemented but fail-closed and disabled pending endpoint entitlement,
  display-rights, quota, credentials, and exact owner authorization.
- Provider-free rehearsal completed all 225 simulated receipts and resumed all
  225 without duplication. Package SHA-256 is
  `ced7df0b3eea75e0f4a29f59f6abfed3f8bfb29cf186bd06ca0142d67233cbd9`;
  scope SHA-256 is
  `a5bbe20e9818f0dd71ba3fb262383ed3c0225bb3f17cc228a49515d108d19d39`.
- Governed run `39138060207` failed first because the Streamlit script could not
  import `exchange_calendars`; its Playwright timeout and missing screenshot
  coverage were downstream. The integrated correction pins the dependency,
  requires the real authentication boundary, checks the exact source marker in
  a browser before crawling, and compares resolved archive paths. Mandatory
  coverage is unchanged. A fresh exact-head governed run is still required.
- Hosted preview remains **NOT DEPLOYED**. Customer production remains unchanged.
  Preview creation and production promotion require separate owner approval.
- Contabo hardware and root SSH access are verified only through owner-supplied
  terminal evidence. Non-root key-only access, independent host identity,
  migration, runner registration, and certification remain pending.

## 2026-10-17 weekend UI and read-only Research engineering

- PR #71 head `29dcb294ec644fee6f5eb20d4bb5f1e3f193b2b3` implements the
  internal, gated Report Card evidence chart. It is deterministic,
  educational/non-scoring, and uses only source-bound retained OHLCV evidence.
  Local authenticated QA passed at 1440px, 390px and 360px with zero provider
  calls, no ledger mutation, public Report Card OFF and role isolation intact.
- The same branch adds `ATLAS_RESEARCH_MARKET_READ_MODEL_V1`, an independent
  cache-first, read-only Research context. It accepts only self-hashed,
  ticker-bound retained families with signed Finnhub display authority,
  payload digests, capture timestamps and explicit no-raw-redistribution
  provenance. It has no provider adapter and cannot alter certified price,
  Action, Fair Value, ranking, publication or Report Card observations.
- The read path has a hard provider-request budget of zero, identifies pricing
  as completed-session end-of-day rather than real-time/delayed intraday, and
  exposes the verified close plus market-session identity. A separately
  self-hashed backup bundle may be used only when the primary bundle cannot be
  verified; no cache read mutates or refreshes either copy.
- Retained Research histories disclose `FRESH_CACHE` or `STALE_RETAINED`; a
  stale retained history is never presented as a newly refreshed customer
  snapshot. OHLCV, volume, corporate-action provenance, fundamentals and
  earnings-family timestamps can be projected when their individual evidence
  envelopes pass validation. Missing or corrupted families fail closed.
- This is **BUILT/TESTED, NOT DEPLOYED OR LIVE**. No production retained bundle
  has been registered under `ATLAS_RESEARCH_MARKET_DATA_ROOT`, and no licensed
  provider acquisition was performed.

## 2026-10-16 protected backfill plan

- PR #58 merged as `2b95d4fdc03d56a22b341ef5cdc1648333eab04b`;
  registration CI run `38951956274` passed.
- Corrected provider-free planning run `38952832134` succeeded. Artifact
  `atlas-buy-now-history-backfill-plan-38952832134` has ID `12069093114`, ZIP
  SHA-256 `c898793aeb379bb5aad1a2b1fdc568692d8562f96d53a20c081f4dd3243135dd`
  and package-file SHA-256
  `594b4c45ce98b8466e742343d3c45a271cdf66dda68c8c07355ff46b801a8ee6`.
- The plan self-hash is
  `f59c6af515f9004be1de10d48998f26fba9a4972feef9e75582a67ff66b2a258`;
  canonical full-plan/scope SHA-256 is
  `2059e22e81e47111ba14507c77828a5a54e6931ec1ab50fc4cc56b60b5cc6739`.
- It proves 1,298 governed members (membership SHA-256
  `d6be219fdb882bb451f604b23d93f6eb2856a370140e70e895edfc0f2c2327f9`),
  nine finalized XNYS sessions from October 5 through October 15, and exactly
  3,894 unique range requests. The allowlist now exactly matches the signed
  entitlement: `/stock/candle`, `/stock/split`, `/stock/dividend`.
- Execution is bounded to concurrency one, initial 60 RPM, zero retries and a
  3,894 absolute ceiling. Planning made zero provider calls and zero production
  writes. Exact-source recovery, normalization, durable duplicate/restart claim
  rejection and fail-closed publication tests passed 82/82.
- The run binds the previously verified 41-shard aggregate identity
  `2d166790b8855a72621cbce34bf70425197c2aae3ff73bfb4b231f753223ab82`.
  It does not redownload or individually re-audit the 41 large shards.
- Live licensed backfill remains **NOT RUN**. Provider-free planning cannot
  observe current provider quota headers. Live transport must stop on HTTP 429,
  entitlement or schema errors, persist raw responses before inspection and
  consume a separately approved durable one-time claim before request one.

## 2026-10-16 provider-free history-backfill planning

- PR #56 is merged on `main` at `a6995fc9aad38268011ff0b6fd5781af3f6606a6`.
- Registered plan-only run `38950023873` (job `117138772061`) checked out that
  exact source and accepted `ATLAS_BUY_NOW_BACKFILL_PLAN_ONCE`. It failed before
  planning while downloading the 1,316,392,491-byte retained-universe artifact;
  `gh run download` exited `1`. No provider acquisition or publication step ran.
- The failed source artifact remains valid and unexpired: artifact ID
  `11318542723`, digest
  `9612c6b9fa02c74de710c7af0c9e644c5976392e2e9efa0c47b20522316d7c1e`.
- The existing governed incremental-plan artifact provides the same immutable
  1,298-member identity without transferring the full retained dataset: run
  `38829162008`, artifact ID `12016416900`, archive digest
  `7d5c032d434ad9e5ff900e854cb53fe4d3379cdb2d4a3e8f67d67f029a9d06cc`.
  A narrowly scoped review change validates that plan's self-hash, membership
  count and membership digest before using its request keys as the ticker set.
- Local deterministic verification on the merged source recomputed nine missing
  finalized XNYS sessions (`2026-10-05` through `2026-10-15`), 1,298 members,
  3,894 range-deduplicated requests (OHLCV, splits and dividends), concurrency
  `1`, initial pacing `60 RPM`, zero retries and a 3,894 hard ceiling. This is
  local engineering evidence, not a successful protected workflow or live
  acquisition authorization.
- A new live backfill claim is **not ready** until the workflow correction is
  reviewed, merged and a fresh protected plan run succeeds. Customer-visible
  data remains the retained October 2 session published October 4.

## Iteration 1 integration audit — 2026-10-16

- PR #52 merged normally as `9be9e0f2464e11a5047479c4c798cef301739809`
  after exact-head customer QA run `38854049606` passed. The retained technical
  source contract is now explicit: 6,033 source records project to 1,298
  governed members and 4,735 excluded records, with an exclusion digest and
  fail-closed duplicate/missing handling.
- Protected replay run `38907237708` is bound to that merge SHA and plan
  artifact `12048198353` (archive SHA-256
  `40b3e267ce224f4b32001242d18b2e79a66d6bb8c3ffce64a819978dbd50b6cf`).
  The `diagnose` and `acquire` jobs are skipped. The protected rehearsal is the
  only allowed continuation and has no Finnhub credential, provider call, or
  production publication authority.
- Integration inspection found the daily coordinator's scheduled path stopped
  after bounded planning plus file-presence checks. It did not execute the
  retained-evidence certification or prove the promoter rejection. The
  coordinated Iteration 1 change makes the registered bounded acquisition
  workflow reusable and calls it in `plan` mode from the daily coordinator,
  so the scheduled provider-free path exercises the same entrypoint,
  consume-once claim, 2,596 receipts, retained shards, deterministic
  certification, and fail-closed publisher boundary. Live acquisition and
  publication remain disabled.
- Focused downstream regression evidence: 107 BUY NOW, publication,
  freshness, heartbeat, and Report Card tests pass. Workflow YAML parsing and
  diff checks also pass.

## 2026-10-16 protected replay continuation

Runs `38849621878`, `38850874170` and `38851875272` exercised the complete
provider-free protected entrypoint on the real retained artifacts. Each kept
the live acquisition and diagnose jobs skipped, produced 2,596 durable replay
receipts, verified consume-once duplicate rejection, and made zero provider
calls and zero production writes. They successively exposed three authentic
retained-data conditions: a short history (`AAC`), an empty history (`AAC.UN`),
and members omitted from the technical shard. Merged PRs #48–#51 preserve all
such members and route them to explicit terminal withholding without changing
the 200-bar scoring minimum or fabricating evidence.

Run `38852953602` then proved the retained technical artifact is the governed
6,033-security source rather than a prefiltered 1,298-member shard. PR #52 at
`71870473686982d20f9929213712be9d5fe0f1f6` implements the exact projection:
validate the immutable source, select the 1,298 plan members, and report the
4,735 excluded records and their digest. Its 59 focused tests pass. Until PR
#52 is merged and its protected replay reaches terminal success, no new live
acquisition claim is valid and customer-visible data remains unchanged.

## Release scoreboard

| Classification | Component | Current evidence |
|---|---|---|
| **VERIFIED LIVE** | Streamlit service and deployment identity | Fresh production inspection found exact `data-atlas-source-sha="e838d05b3c92563c514d4d185365b4c8e97bfdba"`, matching `origin/main`; the login boundary is healthy. |
| **NOT LIVE** | Fresh daily BUY NOW | Latest retained certified session is **2026-10-02**, published **2026-10-04T12:21:38-04:00**. No later live acquisition/publication is verified. |
| **NOT LIVE** | Report Card G2/G3/G4 | Public Report Card remains off; no live G2 acquisition, G3 durable append, or active G4 cycle is recorded. |
| **NOT LIVE** | WS3 expansion | Annual/quarterly pilots exist; broader WS3 acquisition is not operational. |
| **INHERITED CERTIFICATION** | Authenticated customer routes | Governed run `38838300289` on prior deployed source `7d353c1…` passed 144/144 checks and generated all 200/200 required screenshots for desktop and mobile. Artifact `12020755751`, SHA-256 `2a13d533ca87e4400fd7343af0deccfcbef14d895be0c8bb47ec6703530db3ac`. The route evidence is inherited; authenticated routes were not freshly exercised on `731457ec…`. |
| **VERIFIED LIVE** | Current customer-visible Home snapshot | Production still exposes the retained October 2 session, published October 4, with governed BUY NOW inventory `11` and digest `72b37697…`. Full authenticated-route behavior was not freshly exercised on `731457ec…`. |

The production source marker proves deployment of `e838d05b…`. The latest full
customer/admin route and mobile certification remains governed run
`38838300289` on prior source `7d353c1…`; those authenticated routes were not
freshly exercised after the deployment change. Customer data remains the
retained October 2 session, published October 4, with BUY NOW inventory `11`
and publication digest `72b37697b2f4fc5dabd5438c1a3bb7c068cd12e86253b64e37b8a642c310bf17`.

## Current-source collective closeout evidence

Lifecycle labels below are deliberately independent. `CERTIFIED` does not mean
`OPERATIONAL`, and a successful provider-free run does not mean customer data
was refreshed.

- **Premium UI — DEPLOYED; certification inherited, not current-source.**
  Production exposes source `e838d05b3c92563c514d4d185365b4c8e97bfdba`.
  Customer QA run
  `38838300289` passed 144/144 checks, including all 126 mandatory checks and
  18 supplementary checks, and produced all 200/200 screenshots. It covered
  Home, Research, Watchlist and Ask at desktop/mobile viewports, NVDA/MSFT/AVT/
  CRC, the authenticated role/navigation contract, and customer Report Card
  OFF. Artifact `12020755751`, digest
  `2a13d533ca87e4400fd7343af0deccfcbef14d895be0c8bb47ec6703530db3ac`.
- **BUY NOW acquisition — BUILT and provider-free verified; NOT LIVE.** Durable
  diagnostic run `38837665553` classified the retained first-request failure as
  `INCORRECT_STOCK_CANDLE_DATE_PARAMETERS`, not a valid no-data, entitlement,
  schema or normalization outcome. Artifact `12020051392`, archive SHA-256
  `f9dee5ea291bc07aabc3988b861678055479379e5186709fcc57894b99ec16b5`.
  Corrected plan/rehearsal run `38837725214` was provider-free and successful
  for 1,298 members, 2,596 planned requests, a 2,746 ceiling and zero retries.
  Plan artifact `12018984013`, digest
  `c12aefd02b1f0b3c25b07ef3bdab9204551410450e897bb69acd7c2e008be052`;
  rehearsal artifact `12020036929`, digest
  `cb22dc3495813275f48136d1f2fb9e14f401ecb657bee182c349df6b12381760`.
  Merged PR #41 adds a true provider-free execution of the same
  acquisition entrypoint: 2,596 attempts/receipts, 2,596 durable raw-first
  records, consume-once duplicate rejection, zero provider calls and zero
  production writes. Certification reconciled all 1,298 records with zero
  unaccounted, and the promoter rejected the replay-tagged bundle. The replay
  also exposed and PR #41 repairs a material data-shape gap: the bridge had
  supplied only the new completed-session bar. It now requires the original
  governed shard artifacts, verifies every shard digest, run/source identity,
  exact 1,298 membership and at least 200 ordered pre-session bars per ticker,
  then merges exactly one new completed-session bar. Publication-row-only
  fallback is rejected. The implementation and protected workflow registration
  are now on `main` at merge SHA `8ff3086d0569c3243fdabdc0ac89133edff33810`.
  Protected run `38841054213` successfully built the exact-source plan and
  downloaded the governed membership plus all 41 retained shard artifacts, but
  the protected rehearsal failed closed at the exact entrypoint with
  `INCREMENTAL_PROVIDER_FREE_RETAINED_SCOPE_INVALID` before certification.
  The plan artifact is `12021248101`, digest
  `9d2d7bc5f8e5b8be5a2e974e3c346c77c4db814e8e256b4fe9e5655abb33cea3`.
  Provider calls and production writes remained zero; acquire and diagnose were
  skipped. Therefore the expected 1,223 publishable/75 withheld outcome remains
  unproved. PR #43 is now merged on `main` at `01a921c…`; it resolves the exact
  retained replay projection by the governed plan digest and adds schema-bound
  fail-closed handling. Protected run `38843374435` tested the merged repair:
  its plan succeeded and membership plus all 41 shards downloaded, but the
  exact entrypoint failed closed with
  `INCREMENTAL_PROVIDER_FREE_RETAINED_MEMBERSHIP_MISMATCH:6033:1298` before
  certification. Plan artifact `12021813420`, digest
  `b5d5bb2f18b8c143ade542df200d3669e8cf0c92b9024e22f2f4ec6c303f96ac`.
  Acquire and diagnose were skipped; provider calls and production writes were
  zero. The expected 1,223/75 outcome therefore remains unproved.
  PR #44 is now merged on `main` at `cf0d1a26…`; it projects the exact customer
  replay membership from the governed source and adds fail-closed tests for the
  prior `6033:1298` boundary. Protected run `38844493989` built its plan
  successfully and proved that repair: exact reconciliation passed with source
  `6,033`, selected `1,298`, excluded
  `4,735`, missing `0` and duplicate `0`; resolution SHA-256
  `29b940e3c23bf477cfdf6c7bf7e47a32733a1dd78d1a8a16a2a5343c519b1ee5`.
  Expected consume-once duplicate-claim rejection also passed. Certification
  then failed closed on the protected runner before evaluation because Python
  dependency `ijson` was absent (`ModuleNotFoundError`). Acquire and diagnose
  were skipped; provider calls and production writes were zero. The required
  1,223 publishable/75 withheld result therefore remains unproved.
  PR #45 is now merged on `main` at `731457ec…`; it installs the pinned replay
  certification dependency in the protected workflow and adds fail-closed
  coverage for that setup. Protected run `38846139148` built its plan
  successfully but failed closed during dependency preflight because the
  protected `/usr/bin/python3` has no `pip`. The failure occurred before
  artifact download or claim handling; acquire and diagnose were skipped, and
  provider calls and production writes were zero.
  PR #46 is now merged on `main` at `ade1382…`; it binds protected replay setup
  and execution to the managed Python runtime instead of `/usr/bin/python3`.
  Protected run `38846888234` built its plan successfully and advanced through
  managed Python 3.11, pinned `ijson`, governed membership download, all
  retained-shard downloads and graph proof. The resolver again proved source
  `6,033`, selected `1,298`, excluded `4,735`, missing `0` and duplicate `0`,
  with source-file-digest prefix `c0f04a…` and resolution SHA-256
  `29b940e3c23bf477cfdf6c7bf7e47a32733a1dd78d1a8a16a2a5343c519b1ee5`.
  The protected rehearsal then failed in step 9 inside the full acquisition
  entrypoint, before artifact upload. The acquire job was skipped, no provider
  acquisition ran and no production writes occurred. Certification did not
  complete, so the required 1,223 publishable/75 withheld result remains
  unproved.
  PR #47 merged on `main` at `e838d05b…` and corrected the false duplicate-
  claim assertion while retaining failure evidence. Protected run
  `38848397513` proved the complete provider-free acquisition entrypoint:
  2,596 attempts and receipts, consume-once duplicate rejection, zero provider
  calls, zero production writes, source `6,033`, selected `1,298`, excluded
  `4,735`, missing `0`, duplicates `0`. Plan artifact `12024322460`, archive
  digest `be7921e6fe683474b09355f99c382fb1c099f9911e69eb52964b748870b94424`;
  rehearsal artifact `12024736683`, digest
  `e37a38d38d506dbb3826704f76bc5f8b00ce5c2bbd7ca014613bcc5242abf609`.
  Certification then failed closed at `AAC` because its source-bound retained
  technical series has fewer than the unchanged 200-bar scoring minimum. The
  replay did not yet produce the required 1,223 publishable/75 withheld result.
  The coordinated successor change preserves `AAC` in the 1,298 population and
  routes insufficient history to an explicit governed withholding; it does not
  lower the 200-bar requirement or fabricate history.
  The retained October 2 publication remains customer-visible.
- **Report Card G2 — exact-current provider-free CERTIFIED; NOT OPERATIONAL.**
  Protected validation `38846172970` succeeded on `731457ec…` with artifact
  `12022384661`, archive-digest prefix `7f7f9f…`, plan-digest prefix `9fd124…`
  and package-digest prefix `cb4096…`. Stable Gateway binding `38846333719`
  succeeded with artifact `12023396704`, archive-digest prefix `ac96a…` and
  binding-package-digest prefix `e430f…`. Both preserved the CLOSED sentinel,
  ledger and independent backup, with zero provider calls and zero ledger
  writes.
  The bounded scope remains 20 original signals plus SPY, maximum 61 calls and
  zero retries.
- **Report Card G3 — BUILT/OFFLINE TESTED; NOT RUN.** No governed observation
  bundle has been produced from successful live G2 evidence and no append run
  exists. The durable ledger is unchanged.
- **Report Card G4 — CONTROLS BUILT; NOT SCHEDULED.** Report Card operational
  workflows remain dispatch-only. Public Report Card remains OFF.
- **Daily 6:05 PM ET — scheduler wake verified; NOT OPERATIONAL.** Scheduled
  run `38833620230` succeeded only in its coordinator job; plan, protected
  rehearsal and live operation jobs were skipped. This is not acquisition,
  certification or publication proof.
- **Monitoring — transport verified; email confirmation partial.** Provider-free
  run `38838256221` delivered five sanitized Cronitor events with HTTP 2xx;
  artifact `12019784116`, digest
  `79df1c583472231b4358ea4b8234721ea52e34d52f27a50c63eb6259b636758e`.
  The owner previously confirmed a Report Card failure email. BUY NOW
  completion and missed-heartbeat email delivery are not yet confirmed.
- **WS3 Research expansion — runner-local archive contract BUILT; NOT
  OPERATIONAL.** No WS3 workflow run exists. `WS3-B0001` remains a separately
  gated 25-call annual batch. The registered job uses a GitHub-hosted runner
  and a 30-day Actions artifact; no independent durable archive destination,
  restore test or off-runner backup has been proven. Existing verified pilot
  coverage remains ten securities with 5 annual/8 quarterly periods and SBC
  with 2 annual/6 quarterly periods.
- **Provider-free regression evidence.** On exact source `7d353c1…`, the
  combined Report Card G2/G3/G4, daily coordinator, WS3 and macro-contract test
  selection completed with `97 passed`; this is engineering evidence, not live
  operational evidence.

Open PR #39 is a superseded documentation-only branch based on the prior main;
its rehearsal and failed-acquisition facts are already represented here through
the merged PR #40 history. It must not be merged over this ledger without a
fresh reconciliation.

## Component ledger

| Component | BUILT | CERTIFIED | DEPLOYED | OPERATIONAL | CUSTOMER VERIFIED | Latest evidence | Blocker / next action |
|---|---|---|---|---|---|---|---|
| Premium UI | YES | YES — prior-source run `38838300289`, 144/144 checks and 200/200 screenshots | YES — `731457ec…` marker freshly verified | YES for retained-data customer runtime | INHERITED; not freshly exercised on `731457ec…` | Artifact `12020755751`, digest `2a13d533…`; prior-source customer Report Card OFF and provider calls 0. | Repeat authenticated route/mobile certification on current deployed source; independent commercial review and real beginner testing remain open. |
| Home | YES | YES on prior source | YES — `731457ec…` | YES for retained snapshot | YES/PARTIAL | Production snapshot remains finalized session `2026-10-02`, publication `2026-10-04T12:21:38-04:00`, inventory 11 and digest `72b37697…`; full authenticated routes were not freshly exercised. | Capture the exact publication digest/session in authenticated current-source evidence. |
| Research | YES | YES on prior source | YES | YES for retained evidence | INHERITED from governed QA | Run `38838300289` on `7d353c1…` covers NVDA/MSFT/AVT/CRC at desktop/mobile with retained certified authority; not freshly exercised on `731457ec…`. | Repeat current-source authenticated checks; fresh evidence and broader histories remain separate data operations. |
| Watchlist | YES | YES on prior source | YES | YES for previously tested interactions | INHERITED from governed QA | Prior-source add/search/sort/remove/persistence evidence passed; not freshly exercised on `731457ec…`. | Repeat current-source interaction checks; real-user acceptance remains open. |
| Ask ATLAS | YES | YES on prior source | YES | YES for previously tested grounded retained answers | INHERITED from governed QA | Prior-source grounded Ask checks and desktop/mobile captures passed; not freshly exercised on `731457ec…`. | Repeat current-source grounded-answer checks; external model synthesis is not active. |
| BUY NOW | YES | Retained snapshot certified | YES — `731457ec…` | STALE | PARTIAL | Production remains Oct 2/Oct 4 with 11 BUY NOW; retained digest `72b37697…`. | Expose exact digest/session in authenticated current-source evidence; fresh live acquisition, certification and promotion remain separately gated. |
| Incremental acquisition | YES; replay/history binding in PR #41, projection repairs in PRs #43/#44, pinned dependency setup in PR #45 and managed-Python binding in PR #46 | Membership reconciliation PASS; protected full-entrypoint replay still fails before certification | YES on `main` at `ade1382…`; deployed marker remains `731457ec…` pending fresh verification | FAILED CLOSED | N/A | Run `38846888234`: plan, Python 3.11, pinned `ijson`, membership/shard downloads and graph proof passed; exact `6033/1298/4735` resolution with `0/0` missing/duplicates passed; full entrypoint failed in step 9 before artifact upload; acquire skipped and no production writes. | Diagnose the step-9 full-entrypoint failure, then repeat provider-free protected replay and require exactly 1,223 publishable/75 withheld before any fresh live claim. |
| Daily 6:05 PM ET | YES | Provider-free controls tested | Registered | NO | NO | Dual UTC wakeups, XNYS gate, non-cancelling session lock and incremental-only path are registered. It still stops before acquisition/certification/promotion. | Register and certify the successor publication bridge, then obtain exact live acquisition/publication authorization. |
| Finnhub acquisition | YES | Bounded plan certified | Registered | NO | N/A | Last real retained evidence belongs to the October 2 snapshot. | Do not describe planning run as provider refresh. |
| Report Card G2 | YES | Exact-current provider-free validation `38846172970` and binding `38846333719` | Registered | NO | NO | Artifacts `12022384661`/`12023396704`; exact 20-signal plus SPY scope; 61-call ceiling; zero retries/calls/writes; CLOSED sentinel and storage integrity verified. | Separate exact live G2 authorization is required; certification alone does not authorize acquisition. |
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

## Iteration 1 protected replay on merged PR #52

- PR #52 merged to `main` at `9be9e0f2464e11a5047479c4c798cef301739809`.
- Protected provider-free run `38907237708` proved the exact retained projection:
  `6,033` source rows, `1,298` governed members, `4,735` excluded, zero
  missing plan tickers and zero duplicate source tickers. Resolution SHA-256:
  `29b940e3c23bf477cfdf6c7bf7e47a32733a1dd78d1a8a16a2a5343c519b1ee5`.
- It also proved `2,596` durable provider-free receipts and duplicate-claim
  rejection. Live acquisition jobs were skipped; provider calls and production
  publication writes were both zero.
- The job did not reach the final `1,223/75` certification assertion. The
  self-hosted runner received a shutdown signal at 29m37s while executing the
  second, CPU-bound certification phase. This is an observed runner-lifecycle
  boundary, not evidence of a scoring or reconciliation failure.
- PR #54 now separates transport/claim proof from deterministic certification
  into two protected jobs, preserving all assertions while keeping each below
  the observed runner lifecycle. It also routes the daily coordinator through
  the same full provider-free workflow rather than its previous shallow
  file-presence check. Live acquisition and publication remain disabled.

## Outstanding protected decisions

These decisions remain independent. Authorization for one does not authorize
any other item.

### BUY NOW

1. Diagnose the step-9 full acquisition-entrypoint failure from protected run
   `38846888234`, then repeat the provider-free retained-shard replay on exact
   source `ade1382becab446cb7d47b26998df709948bd358`. Require exactly `1,223`
   publishable plus `75` explicitly withheld, with zero provider calls and zero
   production writes.
2. Only after that proof, prepare and separately authorize one fresh
   consume-once Finnhub acquisition claim with an exact source, finalized
   session, membership digest, request ceiling and zero-retry contract.
3. Keep certification and customer publication fail-closed. Customer
   publication requires a separate authorization after acquisition evidence is
   certified; no acquisition approval implies publication approval.

### Report Card

1. Decide whether to authorize the bounded G2 live acquisition for the 20
   original signals plus SPY, maximum 61 calls and zero retries.
2. If and only if G2 succeeds, separately authorize G3 deterministic bundle
   validation and durable ledger append.
3. Consider G4 scheduling only after G2/G3, restore and monitoring evidence are
   complete. Public Report Card remains OFF until separately authorized.

### Research, intelligence and commercial operations

1. Decide whether to authorize WS3-B0001's 25-call financial-history batch.
   Broader financial Research acquisition remains separately bounded and must
   include an independent durable archive, restore proof and off-runner backup.
2. Decide whether to activate an official macro-data feed and external
   model-backed synthesis. Neither is verified active, and neither may alter
   scoring without a separately governed contract.
3. Activate unattended 6:05 PM operation only after the acquisition,
   certification, publication and alert paths are independently proven.
4. Complete BUY NOW completion and missed-heartbeat email confirmation,
   independent commercial-frame review and real beginner acceptance testing.

## Iteration 2 terminal-certification status — 2026-10-16

- Current registered `main` source is
  `7feb7aeff2ad335712e8ce46bf412eeb96e5f4e7` (merged PR #54).
- Provider-free protected replay `38920625431` validated the exact source and
  completed its plan job successfully in 1m22s. Plan artifact
  `12054970081` has archive digest
  `6491f1cd863733fc11bc3089a36af9d8a7c91689ffbefe990ff8d1d61763445c`.
  The acquire and diagnose jobs were skipped, so provider calls and customer
  publication writes remain zero.
- Protected environment approval was granted for provider-free replay only.
  The terminal-certification job `117039980916` is queued because the sole
  matching self-hosted runner, `atlas-worker-1`, is **offline**. No terminal
  `1,223 publishable / 75 withheld` result exists from this run yet. Do not
  classify the replay as complete until the same queued job reaches a terminal
  successful conclusion.
- PR #55 at `48c0d5063ceb7d983586d32906b21dff28038af6` contains the
  Iteration 2 source-current Report Card binding, strict explicit-UTC cutoff
  validation, exact checkout-source verification, and BUY NOW certification
  resource/exit telemetry. Relevant consolidated tests: `246 passed`.
  Required GitHub runs `38921322366` and `38921322381` both completed
  successfully. PR #55 is not merged and does not authorize any protected
  operation.
- The currently queued replay was dispatched from merged PR #54 and therefore
  can establish terminal reconciliation and wall-clock runner outcome, but it
  cannot emit PR #55's new `/usr/bin/time -v` CPU/max-RSS artifact. After PR
  #55 receives exact-head merge authorization and registration, one fresh
  provider-free replay is required for the requested CPU, memory and explicit
  exit-condition measurements.
- Production/customer truth is unchanged pending direct evidence: deployed
  runtime source `e838d05b3c92563c514d4d185365b4c8e97bfdba`; certified
  market session `2026-10-02`; publication
  `2026-10-04T12:21:38-04:00`; governed BUY NOW inventory `11`; publication
  digest `72b37697b2f4fc5dabd5438c1a3bb7c068cd12e86253b64e37b8a642c310bf17`.

### Iteration 2B runner investigation

- GitHub still lists runner registration `21` as `atlas-worker-1`, Linux x64,
  with labels `self-hosted`, `Linux`, `X64`, and `atlas-worker-1`; these labels
  exactly match queued protected job `117039980916`. GitHub reports the runner
  `Offline` and no active job. Registration or label drift is therefore not
  the observed blocker.
- The runner is hosted by DigitalOcean as Droplet `605142688`. The available
  DigitalOcean control-plane session expired before host power, service, or
  system-log state could be inspected, so no unsupported restart was attempted.
  The existing runner was not removed, replaced, or re-registered.
- Owner recovery must use the DigitalOcean Droplet console and first inspect
  host and service state. Discover the installed unit instead of guessing its
  name: `systemctl list-units --type=service --all 'actions.runner*'`; then run
  `systemctl status <discovered-unit> --no-pager -l` and
  `journalctl -u <discovered-unit> --since '2026-10-16 00:00:00 UTC' --no-pager`.
  Also collect `uptime`, `free -h`, `df -h`, `df -i`, `dmesg -T | tail -200`,
  and `journalctl -k --since '2026-10-16 00:00:00 UTC' --no-pager` before any
  service change. If the host is running and the discovered unit is inactive,
  the supported recovery is `systemctl restart <discovered-unit>` followed by
  `systemctl is-active <discovered-unit>` and GitHub runner-status verification.
  These commands do not expose or rotate registration credentials.
- Source-current combined verification on PR #55 now covers Report Card,
  incremental BUY NOW, daily coordinator, customer Research, Home and Ask
  contracts: `493 passed`. One obsolete Home assertion was corrected to target
  the last (active) renderer definition and its multiline render call; no
  runtime behavior or investment output changed.

### Confirmed OOM and bounded-certification repair — 2026-10-16

- Protected run `38920625431` completed plan, protected registration rehearsal,
  exact retained-artifact download, 2,596 provider-free receipt generation and
  duplicate-claim rejection. Certification job `117059234617` then failed with
  exit 137 at 22m14s. The DigitalOcean kernel recorded an OOM kill of PID
  `393777` (`python3`) at `anon-rss:7633808kB` on the 8 GiB host. This supersedes
  the earlier runner-lifecycle hypothesis.
- The allocation was caused by overlapping full-population object graphs:
  retained multi-year histories, merged histories, shard acquisition records,
  two complete evaluation passes, and two immutable candidate graphs. The
  repaired path consumes retained histories as each symbol is materialized,
  prepares peer evidence once, evaluates deterministic batches of 64, writes
  atomic per-symbol terminal checkpoints, releases bars before candidate
  construction, and garbage-collects batch intermediates. Scoring algorithms,
  the 200-bar minimum, ordering, withholding rules and publication gate are
  unchanged.
- Durable resume is fail-closed and binds the checkpoint directory to source,
  plan, receipt set, session, exact membership, batch size and run identity.
  A mismatched or partial checkpoint cannot be used for certification or
  publication.
- The registered workflow now captures `/proc/meminfo`, GNU-time CPU/wall/RSS
  evidence even when the certification child exits nonzero, and rejects a
  successful run unless measured peak RSS is below 5 GiB. No identical replay
  of the OOM implementation will be dispatched.
- Provider calls and production writes remain zero. Terminal protected proof
  of `1,223 publishable / 75 withheld` remains pending registration of this
  repair and one fresh provider-free protected replay.
- A local exact-artifact execution used plan artifact `12054970081`, transport
  artifact `12057435684`, all 41 retained shard artifacts from run
  `37216506983`, 1,298 governed rows and 2,596 receipts. It completed in
  `491.53s` with `465.05s` user CPU, `15.07s` system CPU and peak RSS
  `3,484,631,040` bytes (3.25 GiB), below the 5 GiB target and 54% below the
  killed process's recorded anonymous RSS. It produced 2,596 terminal
  checkpoints, zero unexplained members, zero provider calls and zero
  production writes.
- That exact retained replay did **not** support the historical `1,223/75`
  publication split: all 1,298 members were explicitly withheld. The retained
  technical shards end at the October 2 certified snapshot, while the
  provider-free October 15 receipt supplies only one terminal bar. The
  unchanged evaluator correctly reports `UNREPAIRABLE_BAR_GAP`, missing
  technical-method evidence and unavailable volume for that discontinuous
  series. This is a distinct evidence-continuity blocker, not an OOM or
  unexplained-population defect. No scoring or withholding rule was relaxed to
  manufacture the expected split. A protected terminal replay must therefore
  either use an ordered completed-session catch-up evidence set or remain
  fail-closed; it must not assert `1,223/75` against unsupported retained data.
## Iteration 3 — data continuity gate (2026-10-16)

- **BUY NOW certification:** OOM is resolved on the exact retained workload
  (peak RSS 3.25 GiB; 491.527 seconds), but terminal customer certification is
  intentionally blocked by evidence continuity, not compute. The retained
  governed technical histories end at `2026-10-02`. For the approved
  `2026-10-15` target, the verified XNYS calendar identifies nine ordered
  missing sessions: `2026-10-05` through `2026-10-09` and `2026-10-12`
  through `2026-10-15`.
- **Retained evidence:** all 41 exact technical-history shard archives from run
  `37216506983` remain reusable. Their locally verified canonical archive-set
  digest is `2d166790b8855a72621cbce34bf70425197c2aae3ff73bfb4b231f753223ab82`.
  The provider-free Oct. 15 receipt is simulated validation evidence and is not
  licensed market evidence; it cannot close the nine-session gap.
- **Backfill contract:** the provider-free planner binds the exact 1,298-member
  governed population, retained artifact-set identity, source SHA, and ordered
  XNYS gap. It deduplicates all missing sessions into one range request per
  ticker for each licensed capability: `/stock/candle`, `/stock/split`, and
  `/stock/dividend2`. This is **3,894 maximum attempts**, concurrency and pacing
  still subject to the protected executor, and **zero automatic retries**.
  It requires complete OHLCV plus volume for every ticker/session and explicit
  corporate-action consistency; partial, duplicate, missing, unexpected, or
  out-of-order evidence fails closed.
- **Daily continuity:** the 6:05 PM coordinator now distinguishes `CURRENT`,
  one-session `DAILY_APPEND`, and multi-session `BOUNDED_BACKFILL`. It will not
  jump from an old retained boundary directly to the newest session. Live
  acquisition/publication and unattended operation remain disabled.
- **Customer state:** no new provider data was acquired and no customer snapshot
  was written. The retained customer publication remains the prior October 2
  market session / October 4 publication with 11 governed BUY NOW names.

### Historical backfill consume-once safety gate — 2026-10-16

- Provider-free plan run `38952832134` remains the immutable acquisition basis:
  source `2b95d4fdc03d56a22b341ef5cdc1648333eab04b`, artifact `12069093114`,
  artifact ZIP SHA-256 `c898793aeb379bb5aad1a2b1fdc568692d8562f96d53a20c081f4dd3243135dd`,
  package SHA-256 `594b4c45ce98b8466e742343d3c45a271cdf66dda68c8c07355ff46b801a8ee6`,
  plan self-hash `f59c6af515f9004be1de10d48998f26fba9a4972feef9e75582a67ff66b2a258`,
  and canonical scope SHA-256 `2059e22e81e47111ba14507c77828a5a54e6931ec1ab50fc4cc56b60b5cc6739`.
- The proposed protected executor durably consumes a claim before transport,
  atomically records each request intent before its call, and atomically stores
  a status/body envelope before inspection. A committed response can be
  recovered without another call. An intent without a response is classified
  `INDETERMINATE` and cannot be retried under the consumed claim. A different
  execution ID, changed scope, concurrent worker, corrupt receipt, 429,
  entitlement failure, HTTP failure, response-schema failure, missing volume,
  and unordered or duplicate sessions all fail closed.
- A local exact-artifact provider-free rehearsal exercised all 3,894 request
  records and normalized 11,682 observations (1,298 securities x nine XNYS
  sessions). It completed in 2.77 seconds with provider calls `0`, publication
  writes `0`, result digest
  `5e70a592fb97536377b4aad43a323de2d94bcfa9fdb3e8d1a8c0850f1fcadbc0`,
  and normalized-observation digest
  `85558a864372656f6fe8b4e01ea14ae8afb30772a5ee0df296e7771d89f2702d`.
  This is fixture evidence, not licensed market evidence.
- Live execution remains **NOT AUTHORIZED**. Registration and a protected
  provider-free rehearsal on `atlas-worker-1` are still required. At 60 RPM,
  3,894 attempts have a theoretical pacing floor of 64.9 minutes, plus provider
  latency and integrity processing. Certification and customer publication
  remain distinct downstream gates; no customer-visible state changed.
- Protected rehearsal run `38959022723` reached `atlas-worker-1` and passed
  exact source, authorization, protected durable-storage, managed Python 3.11,
  and zero-provider-credential checks. It failed before claim creation or any
  request simulation because the host does not install the optional `unzip`
  executable. No claim, provider call, publication write, or Report Card
  mutation occurred. The correction replaces that host dependency with
  Python's standard-library `zipfile` extraction, including traversal checks,
  and records GNU-time plus claim-specific durable disk consumption.

### Consumed live-backfill forensic inspection — 2026-10-16

- PR #62 is registered on main at `393de1bbec2d45bc1ddf822a4f0774cb2eb44b70`.
  Protected provider-free inspection run `38983380052`, job `117249159603`,
  completed successfully on `atlas-worker-1`. Its artifact is
  `atlas-buy-now-history-backfill-forensics-38983380052` (artifact ID
  `12082151953`, ZIP SHA-256
  `199b7dc59f14173c2b8a9720cd4b704178b5870e16d925075a9e980aeace7211`).
- The consumed claim is `oct02-oct15-2026-backfill-38962431540-01`, bound to
  scope `37de17d0217483bcba4046d381c811faa84f33227237b468e705f5e9bbf77b3d`.
  The first failure was request ordinal `2848`, ticker `QRVO`, endpoint
  `/stock/candle`. Finnhub returned HTTP 200 and the exact terminal shape
  `{"s":"no_data"}`. The raw-body SHA-256 is
  `4bc31a65f0aefa9b37dfa85119ff889f4c9dd2cdd5933b4af564f0ddff0766ab`;
  the persisted envelope SHA-256 is
  `4b06a585c41cbda8ef486301131d9dacde41f61e4340e054aa61a61529d75bbb`.
- Accounting is exact: 3,894 authorized slots, 2,848 durable intents and raw
  envelopes, 2,847 completed receipts, one failed response, zero indeterminate
  requests, and 1,046 unattempted slots. Intent, envelope and receipt manifest
  SHA-256 values are respectively
  `668f0bbb916e4911ceeedc829032f1e27694af36c3f2c45cc692651d2720aa20`,
  `ac7df389d9d505dbd623160773f5fed9b334a5bb8a6bef0599e2d38bbde7a987`,
  and `bbf45e05d7086ea5acdb569b1a883c6ebec9c87b90878f918d505924b4e18903`.
- The cause was a contract-classification defect: a genuine Finnhub `no_data`
  response was routed through the generic candle-schema error. It was not
  malformed JSON, an array-length/volume error, an entitlement failure, or an
  indeterminate request. No new provider call, publication write, or Report
  Card mutation occurred during inspection.
- The correction preserves `no_data` as immutable unavailable evidence. It
  writes a terminal receipt, never creates an OHLCV row or numeric zero, and
  requires the affected ticker to appear in a complete, source-hashed
  unavailable inventory. Any non-exact `no_data` shape, corrupt payload,
  missing array, invalid volume, or population-partition mismatch still fails
  closed. A fresh licensed acquisition is not yet authorized; the consumed
  claim cannot be reused.
- PR #63 merged at `1a432bcdf3caceaf9acb5d140061c6127a1c811b` after the
  earlier local remote-tracking ref was observed before GitHub completed the
  merge. The corrected classifier is now registered. The merged workflow has
  forensic inspection but no operation that can derive a new authority limited
  to never-attempted slots; a provider-free recovery registration is therefore
  required before a protected 1,046-slot rehearsal or live decision package.

### Efficiency and fail-before-claim hardening — 2026-10-16

- PR #64 consolidates the preserved-evidence recovery operation with an
  immutable, content-addressed market-evidence cache, minimal-session request
  planning, explicit ticker/systemic failure disposition, and a no-claim
  runner/storage/credential/budget preflight. Existing evidence is verified on
  reuse and cannot be overwritten under the same request identity.
- The daily planning contract requests no data for already-current tickers,
  requests only the missing candle range for contiguous lagging tickers, and
  refreshes splits/dividends only when their independent cache status is not
  fresh. Tickers without a provable contiguous boundary are explicitly
  withheld rather than silently dropped.
- On a representative 1,298-member, one-session update with fresh corporate
  actions, the deterministic plan contains 1,298 requests versus the 3,894
  three-family historical repair scope: 2,596 fewer requests (66.7%). This is
  provider-free planning evidence, not a newly authorized call budget.
- Terminal no-data and per-ticker integrity failures are isolated as explicit
  withholding. Rate limiting, entitlement failure, shared integrity failure,
  and indeterminate transport outcomes stop the operation globally. Automatic
  retries remain zero.
- The protected recovery and incremental-acquisition jobs now run source,
  labels, Python, durable-root separation/write access, disk, memory, timeout,
  endpoint allowlist, pacing and request-ceiling checks before any claim can be
  consumed. The live path checks credential presence without outputting it.
- Focused and cross-module provider-free verification completed with `93
  passed` in 11.04 seconds. Workflow YAML parsing, Python compilation and diff
  checks passed. No Finnhub request, publication write, or Report Card mutation
  occurred.

### Preserved-evidence recovery rehearsal — 2026-10-16

- PR #64 is registered on main at
  `d52974ad79ce49ff4986d149a3d9c0e5a215e0d8`. Protected provider-free
  recovery run `38987831148`, job `117263311859`, completed successfully on
  `atlas-worker-1` after the required `atlas-licensed-research-acquisition`
  environment review. Every acquisition, publication, and unrelated workflow
  job was skipped.
- The immutable artifact is
  `atlas-buy-now-history-backfill-recovery-38987831148` (artifact ID
  `12083244989`, ZIP SHA-256
  `997a9395cdbb3f4c7eb208fcfb45bdd331daee1953baef0fa2726a85f05b69f9`).
  The verified recovery-package SHA-256 is
  `ed079c74ab79f030a7078b8cd8ed9672856a438ffaa8988592cc99502edeeff9`.
- Recovery accounting is exact: 3,894 original request slots; 2,847 preserved
  completed receipts; QRVO ordinal 2,848 preserved as terminal
  `FINNHUB_NO_DATA`; zero indeterminate, duplicate, unexpected, or corrupted
  evidence; and exactly 1,046 never-attempted ordinals 2,849 through 3,894.
  The remaining set comprises 348 candle, 349 split, and 349 dividend requests
  across 349 tickers.
- The recovery plan SHA-256 is
  `f996189b53d661c2af984214f6a0b530fb99a06c4c468f55ab4ca9d092e44970`;
  request-ordinal SHA-256 is
  `e8c3ebae1d5eba9876899604399c1065e5975404d31ff86602fd4e9212bd21a7`;
  and the unconsumed recovery claim scope SHA-256 is
  `4d2edddf98d1f6edb56f54d82f382d9df8f70b430f7355d9d40c524b8cbbe577`.
  The claim ID is
  `oct02-oct15-2026-backfill-recovery-38987831148-01`; the complete proposed
  live token is retained only in the protected artifact, not copied into this
  repository ledger.
- Fail-before-claim preflight status is `PASS_BEFORE_CLAIM`: concurrency one,
  60 RPM initial pacing, zero retries, 1,046 maximum requests, separated
  durable raw/checkpoint roots, and 7,687,991,296 bytes available memory. The
  theoretical pacing floor is 17.433 minutes. The protected job ran from
  00:45:49 to 00:45:55 UTC (approximately six seconds wall time); the workflow
  did not instrument process-level CPU or peak RSS, so those values are not
  claimed.
- Provider calls, customer-publication writes, and Report Card mutations were
  all zero. The live recovery is **READY FOR A DISTINCT OWNER DECISION**, not
  operational: approve at most one consume-once acquisition using the exact
  protected claim and 1,046-request scope. Publication, daily activation, and
  Report Card mutations remain separately gated.

### Licensed recovery dispatch gate — 2026-10-16

- Owner approval is recorded in Issue #53 comment `6228009434`, but the
  authorized recovery could not be dispatched. Main at
  `d52974ad79ce49ff4986d149a3d9c0e5a215e0d8` registers the provider-free
  recovery-package operation only; it has no live job or workflow input that
  accepts the `ATLAS_BACKFILL_RECOVERY_CLAIM_V1` claim.
- The existing live backfill job is not a safe substitute. It is hard-bound to
  source `2b95d4fdc03d56a22b341ef5cdc1648333eab04b`, artifact `12069093114`,
  the original 3,894-request package, and the older
  `AUTHORIZE_ATLAS_BACKFILL_CLAIM` contract. Dispatching it would violate the
  approved source, artifact, token, and 1,046-request boundary.
- The recovery therefore failed closed before dispatch: no provider call, claim
  consumption, publication write, or Report Card mutation occurred. The exact
  2,847 completed receipts, QRVO terminal-unavailable receipt, and 1,046
  unattempted ordinals remain unchanged.
- Required registration is narrowly scoped: one protected live-recovery job
  must retrieve and verify artifact `12083244989`, accept only recovery claim
  `oct02-oct15-2026-backfill-recovery-38987831148-01` with scope
  `4d2edddf98d1f6edb56f54d82f382d9df8f70b430f7355d9d40c524b8cbbe577`,
  and make ordinals outside 2,849 through 3,894 unreachable. The existing owner
  acquisition approval cannot be exercised until that workflow is separately
  reviewed and registered.
- The consolidated registration candidate is commit
  `896ceb11b23b0a56591c60888f1f2fe931bab2ff` on PR #65. It adds a distinct
  protected live-recovery job and executor, hard-binds artifact `12083244989`
  and the verified package/plan/claim identities, requires explicit manual
  enablement plus the exact recovery authorization, runs credential and durable
  storage preflight before claim consumption, and uploads sanitized evidence
  even after a failed execution. The executor can address only ordinals 2,849
  through 3,894 and writes to separate recovery claim/raw namespaces; it has no
  publication path. Focused recovery, durability, duplicate/indeterminate,
  authorization, preflight, and original-backfill tests report `20 passed` in
  11.52 seconds; YAML parsing, Python compilation, and diff checks pass.
- This candidate is **BUILT AND TESTED, NOT REGISTERED**. Because registration
  changes the workflow source SHA, both its merge and a fresh exact-source live
  recovery decision remain protected gates. The earlier acquisition approval
  is not treated as authority to run newly registered code at a different SHA.

### Registered licensed-recovery approval gate — 2026-10-16

- PR #65 is merged and the authoritative remote `main` is
  `c038e31d0e055a0569e8fa05e0ae2f11203c5c9a`. The registered workflow contains
  the dedicated `protected-history-backfill-recovery-acquisition` job on the
  `atlas-licensed-research-acquisition` environment and
  `atlas-worker-1`. Repository permissions are read-only (`actions: read`,
  `contents: read`); the Finnhub credential and durable raw/checkpoint roots are
  supplied only by that protected environment.
- The immutable recovery evidence remains artifact `12083244989`, ZIP SHA-256
  `997a9395cdbb3f4c7eb208fcfb45bdd331daee1953baef0fa2726a85f05b69f9`,
  package-file SHA-256
  `2663fd9e6e7edf8553c8383c26cd8af8c392fa23c4920e60da4a23ad4d7f93b3`,
  package identity
  `ed079c74ab79f030a7078b8cd8ed9672856a438ffaa8988592cc99502edeeff9`,
  plan SHA-256
  `f996189b53d661c2af984214f6a0b530fb99a06c4c468f55ab4ca9d092e44970`
  and claim-scope SHA-256
  `4d2edddf98d1f6edb56f54d82f382d9df8f70b430f7355d9d40c524b8cbbe577`.
- The executable recovery scope is unchanged: exactly 1,046 original ordinals
  2,849 through 3,894; 348 candles, 349 splits and 349 dividends; concurrency
  one; initial 60 RPM pacing; zero automatic retries. Scope validation requires
  that exact consecutive ordinal list, unique request digests and the signed
  three-endpoint allowlist before the durable claim can be consumed.
- The original 2,847 completed receipts and QRVO ordinal 2,848 terminal
  `FINNHUB_NO_DATA` evidence are inputs to forensic reconciliation and are not
  executable by the recovery plan. Protected rehearsal run `38987831148`, job
  `117263311859`, established zero indeterminate requests and left recovery
  claim `oct02-oct15-2026-backfill-recovery-38987831148-01` unconsumed.
- No licensed recovery dispatch or matching acquisition artifact is recorded
  after that rehearsal. The job itself performs exact checkout, credential,
  durable-storage and request-budget preflight before atomically consuming the
  claim. Current quota and credential validity therefore remain a protected
  execution-time check, not a provider-free claim.
- The remaining decision is one explicit owner authorization bound to workflow
  source `c038e31d0e055a0569e8fa05e0ae2f11203c5c9a`, the existing immutable claim
  and scope above. Approval authorizes acquisition only. Customer publication,
  Report Card mutation and unattended scheduling remain disabled and require
  separate decisions.

### Registered-source authorization reconciliation — 2026-10-16

- Issue #53 comment `6228009434` authorizes acquisition only against the older
  workflow source `d52974ad79ce49ff4986d149a3d9c0e5a215e0d8`. Comment
  `6228569074` authorizes only PR #65's merge and explicitly excludes Finnhub
  calls. No owner comment currently authorizes acquisition using registered
  source `c038e31d0e055a0569e8fa05e0ae2f11203c5c9a`.
- The execution request expressly stated it was not independent authorization.
  The dispatch therefore failed closed at the approval check: no workflow was
  dispatched; the recovery claim was not consumed; and provider calls,
  publication writes and Report Card mutations remained `0 / 0 / 0`.

### Licensed recovery acquisition — 2026-10-16

- Issue #53 comment `6228610074` supplied the distinct exact-source owner
  authorization for registered workflow source
  `c038e31d0e055a0569e8fa05e0ae2f11203c5c9a`. The protected workflow was
  dispatched exactly once as run `38995851425`; protected job
  `117288139034` completed successfully on `atlas-worker-1` in 17m37s. All
  unrelated workflow jobs were skipped.
- The protected preflight passed before claim consumption with the Finnhub
  credential present, concurrency one, initial 60 RPM pacing, zero automatic
  retries, a 1,046-request ceiling, durable raw root
  `/mnt/atlas_incremental_raw`, durable checkpoint root
  `/mnt/atlas_incremental_checkpoints`, and 7,653,285,888 bytes available
  memory. The successful execution consumed the unique recovery claim; the
  preflight artifact's `claim_consumed: false` describes only its state before
  transport and must not be interpreted as reusable authority.
- Actual licensed accounting is exact: 1,046 attempts, 1,046 provider calls,
  1,046 `AVAILABLE` durable receipts, zero new terminal-unavailable responses,
  zero indeterminate requests, and zero unattempted recovery slots. Combined
  with the preserved 2,847 receipts and QRVO ordinal 2,848 terminal
  `FINNHUB_NO_DATA`, all 3,894 original request slots are now accounted for.
  No completed or terminal-unavailable request was reacquired.
- Sanitized evidence is retained as
  `atlas-buy-now-history-backfill-recovery-acquisition-38995851425` (artifact
  ID `12087173200`, ZIP SHA-256
  `4afde02d80a1a27e942d66391e1dd25f03559a5d40ea431ada599b7e24096ec8`).
  The raw-envelope manifest SHA-256 is
  `a0b7f906ba0d89c3cb5283cc395a3a9e1df35e5a6368cda8946be654fcf1b7c5`
  and the normalized-receipt manifest SHA-256 is
  `43b1a35d61a6db20f75b0f35a2d97bf955155de37dcbd386caf58995145630c7`.
  The execution reverified recovery artifact `12083244989` at ZIP SHA-256
  `997a9395cdbb3f4c7eb208fcfb45bdd331daee1953baef0fa2726a85f05b69f9`
  and plan SHA-256
  `f996189b53d661c2af984214f6a0b530fb99a06c4c468f55ab4ca9d092e44970`.
- The artifact classifies the evidence as
  `LIVE_FINNHUB_RECOVERY_RAW_EVIDENCE` and the handoff as
  `RECOVERY_EVIDENCE_READY_FOR_COMBINATION`. This proves acquisition and
  request-ledger continuity, not terminal BUY NOW certification or customer
  publication. QRVO remains explicitly unavailable for the affected evidence;
  the memory-bounded certification must apply the existing withholding rules.
- Customer publication writes and Report Card mutations remained `0 / 0`.
  The customer-visible snapshot therefore remains the October 2, 2026 market
  session published October 4, 2026 with 11 governed BUY NOW names and digest
  `72b37697b2f4fc5dabd5438c1a3bb7c068cd12e86253b64e37b8a642c310bf17`.
- XNYS calendar `exchange_calendars==4.13.2` confirms October 16, 2026 is the
  next trading session after the backfill boundary and closed at 20:00 UTC.
  It is not covered by this authorization and requires a distinct bounded
  acquisition before it may be represented as current.
- **Next protected step:** run the provider-free, memory-bounded combination
  and certification over the preserved original and recovery evidence. Only a
  terminal certification artifact may support a separate atomic-publication
  decision. No additional Finnhub acquisition, publication, Report Card
  mutation, or unattended activation is implied by this completed run.

### Real-evidence certification bridge candidate — 2026-10-16

- PR #66 now contains the smallest downstream bridge from the two durable raw
  namespaces into the existing memory-bounded incremental certifier. It does
  not implement scoring, thresholds, or an alternative publisher. The bridge
  verifies exactly one raw envelope for every original ordinal, rechecks each
  request and body digest, validates the Finnhub response contract, joins the
  nine completed XNYS sessions to the source-bound retained 41-shard technical
  history, and preserves QRVO as terminal unavailable.
- The protected workflow candidate downloads and verifies the immutable
  original, recovery-package, and successful-recovery artifacts; retrieves the
  exact governed 6,033-row membership source plus 41 retained technical
  shards; runs the existing deterministic evaluator in 64-symbol bounded
  batches with durable checkpoints; measures peak RSS against the 5-GiB
  ceiling; and writes only certification artifacts. `FINNHUB_API_KEY` must be
  absent from this job.
- A publication simulation promotes the certified bundle only into an isolated
  runner-temporary copy of the current snapshot, verifies prior and published
  digests plus rollback inventory, and asserts that repository production
  files remain unchanged. Real publication remains impossible from this job.
- Focused bridge, recovery, incremental-certification and scheduler regression
  coverage reports `46 passed` in 9.31 seconds; workflow YAML parsing and
  Python compilation pass. These are engineering results, not terminal
  real-data certification.
- Status is **BUILT AND LOCALLY VERIFIED, NOT REGISTERED**. PR #66 head must be
  reviewed and explicitly approved for merge before the protected runner can
  execute this new workflow source. After registration, the provider-free
  dispatch input is `certify_completed_history_backfill=true` with authority
  `ATLAS_BUY_NOW_BACKFILL_CERTIFY_ONCE:38995851425`. It performs zero provider
  calls, customer-publication writes, and Report Card mutations.

### First protected real-evidence certification — 2026-10-16

- PR #66 merged as source `887fe8c2de6f688f718f00f91aa6de043617f68e`.
  Protected run `38998598401`, job `117296526496`, passed exact-source and
  provider-free authority enforcement, verified artifacts `12069093114`,
  `12083244989`, and `12087173200`, restored the governed membership plus all
  41 retained-history shards, and then failed closed before scoring at
  `BACKFILL_COMBINED_SESSION_SET_INVALID:BLFS`.
- The failed pre-scoring process ran for 3.20 seconds at 87% CPU and peaked at
  134,008 KiB RSS (about 131 MiB), comfortably below the 5-GiB ceiling. This
  measurement does not certify full scoring memory because execution stopped
  at the session-integrity boundary.
- The failed run made zero Finnhub calls, zero production-publication writes,
  and zero Report Card mutations. Its sanitized failure artifact is
  `atlas-buy-now-backfill-certification-38998598401` (artifact ID
  `12087987362`, ZIP SHA-256
  `682b5b55b34f77d7d458e904951e389e77fa2e43cc05ddec0d9e78f43e7711e6`).
  No certified candidate or publication digest was produced, and the current
  customer snapshot remains October 2 / October 4.
- The narrow correction preserves strict rejection for duplicate, unordered,
  or out-of-scope candle sessions, but treats a valid ordered strict subset of
  the nine requested sessions as explicit
  `FINNHUB_PARTIAL_SESSION_COVERAGE`. The affected security is withheld with
  its raw-response digest and missing-session inventory; no bar is fabricated
  and no scoring rule changes. Focused continuity, bridge, execution, and
  publication regressions pass `40/40`.
- **Next protected step:** merge the exact reviewed correction, then rerun the
  same provider-free certification authority against the new source. Customer
  publication remains separately gated and is not ready unless that run emits
  a terminal candidate and publication digest under the sub-5-GiB contract.

### Weekend Report Card and automation engineering — 2026-10-17

- Branch `codex/weekend-report-card-automation` is based on registered main
  `71362fb4a0fe4bf79478600ba0d7a1b2697b9c30`. It adds a read-only,
  source-bound Report Card chart projection and responsive internal detail
  renderer. It accepts only persisted verified OHLCV with evidence identity
  and corporate-action adjustment provenance; duplicate sessions, incomplete
  histories, and unhandled split discontinuities fail visibly closed.
- Support/resistance zones and OLS trendlines are deterministic and marked
  `EDUCATIONAL_NON_SCORING`. Supported 1M/3M/6M/1Y/5Y controls, the original
  signal marker, latest verified close/as-of, labeled encodings, and an
  accessible table fallback are present. No provider fallback was added.
- Daily scheduling permits a delayed GitHub start through 23:59:59 ET on the
  same finalized XNYS session, while retaining holiday and duplicate-session
  rejection. Focused Report Card, G2/G3, navigation, and daily tests pass
  `92/92`; changed-module compilation passes with an isolated bytecode cache.
- G2/G3 provider-free primitives remain ready, but G4 and unattended BUY NOW
  are **NOT OPERATIONAL**: the registered daily graph remains plan-only, has no
  live acquire→certify→promote jobs, and emits no coordinator Cronitor events.
  Public Report Card remains OFF.
- Full certification run `39043009760`, job `117426122707`, completed authority
  and retained-evidence downloads, but scoring was cancelled and emitted no
  artifact. It is not certification evidence and produced no candidate. The
  pending 16-GB runner resize remains the production-scale blocker; this
  iteration did not restart or modify the worker.

### Major-release preview candidate — 2026-10-17

- PR #71 now includes an evidence-grounded beginner **Simple View** and an
  evidence-dense **Detailed View** for Research. The simple projection answers
  the eight owner-required investment questions from the same governed facts,
  labels stale or unavailable context, identifies itself as a deterministic
  grounded fallback, and explicitly states that no external model is active.
- Report Card completed-session selection now additionally requires explicit
  finalization, finite OHLCV values, nonnegative finite volume, strict ordering,
  unique sessions, and durable source identity. Backup evidence keeps its
  backup provenance and freshness status; it cannot be labeled newly acquired.
- Provider-free responsive QA covered 1440, 1024, 390, and 360 widths with 20
  screenshots, zero browser errors, zero provider calls, zero ledger mutations,
  and passing customer/admin isolation. The checksum-manifest digest is
  `e65478976ff673537c76e939be26fcf9e4d8eff9b5f5c12c99a16c0f93f00ac4`.
  Production remains independently unchanged at
  `71362fb4a0fe4bf79478600ba0d7a1b2697b9c30`.
- A separate access-controlled hosted preview is **NOT DEPLOYED**. Streamlit
  Community Cloud is signed out and no GitHub preview deployment exposes an
  environment URL. Owner sign-in and creation of a second branch-bound app are
  required; the existing production app must not be reused. Until then, hosted
  exact-SHA browser certification and owner visual acceptance remain blocked.
- The autonomous browser workflow is now internally consistent with its
  zero-provider contract: it creates an honest retained-evidence-only sidecar
  instead of making 22 licensed QA calls. Missing enrichment remains visibly
  unavailable rather than being replaced with synthetic market facts.

### Page-wide ATLAS Explains cohesion — 2026-10-17

- PR #71 adds one shared `ATLAS_EXPLAINS_V1` contract across Home, BUY NOW,
  Research, Charts, Report Card, Recovery Radar, ETF Analysis, and Watchlist.
  Every supported surface answers six beginner questions through a 30-second
  takeaway, two-minute Simple View, and evidence-bound Detailed View.
- Explanations label source facts, calculations, interpretations, limitations,
  and monitoring scenarios separately. They are non-scoring and cannot change
  certified recommendations, Report Card observations, customer publication,
  or production state.
- The synthesis interface fails closed when external-model execution is
  requested. Current copy is explicitly labeled
  `DETERMINISTIC_GROUNDED_FALLBACK`; it is never presented as externally
  AI-generated.
- Hosted preview activation remains owner-controlled. The exact safe setup and
  browser-acceptance gates are recorded in
  `docs/operations/ATLAS_PREVIEW_ACTIVATION_CHECKLIST.md`. No hosted preview URL
  exists yet, and production remains unchanged.
- Independent application QA exercised Home, BUY NOW, Research, Recovery,
  ETFs, Watchlist, and internal Report Card at 1440, 1024, 390, and 360 px.
  Research reached its terminal NVDA surface at every width after detaching the
  immutable canonical decision only at the Streamlit cache boundary. The
  canonical decision values and authority remain unchanged.
- The compact 360-px Home view now keeps the 30-second takeaway above the fold
  and exposes Simple/Detailed reading levels through one accessible expander.
  Report Card 360/390 chart QA verified all 1M/3M/6M/1Y controls, unified
  hover, zero horizontal overflow, and no toolbar overlap. Final chart-evidence
  checksum-manifest SHA-256:
  `5085d00a44cb807894b2883fce0efcadf8cf58886b073b102e17781ebbf57cab`.
- These were provider-free preview checks: provider calls, publication writes,
  and ledger mutations were all zero. They do not establish a hosted preview
  or production deployment.

### Consolidated customer-intelligence candidate — 2026-10-18

- Authoritative `main` is `0c99148b177f9891550a90ae3b8dd934bff67d66`,
  the merge commit for PR #71. Development continues on the isolated
  `codex/consolidated-release` branch; this candidate is **NOT DEPLOYED**.
- ATLAS Explains now accepts only provenance-bearing page evidence for
  company-specific claims, includes Ask ATLAS, and exposes source identities
  without exposing raw licensed payloads. Deterministic fallback remains
  explicitly labeled and external-model execution remains disabled.
- Home's brief is bound to the actual lead company, governed thesis, primary
  risk, market interpretation, and certified timestamp when those fields are
  present. Unsupported current news or macro context remains unavailable.
- The internal Report Card chart adds retained-evidence candlesticks, volume,
  SMA20/50, RSI14, MACD(12/26/9), SPY comparison, original-signal and measured
  outcome markers. All indicators are educational/non-scoring and fail closed
  when required bars are incomplete. Public Report Card remains OFF.
- A bounded Research refresh planner is built with transport disabled. Its
  immutable maximum is 25 tickers / 225 request intents, concurrency one,
  zero retries, signed entitlement checks, cache-first family TTLs, and a
  zero-call/no-authority preflight. This is readiness evidence, not acquisition.
- The daily 6:05 PM ET coordinator remains disabled/plan-only and is not an
  unattended acquisition→certification→publication operation. Production
  BUY NOW data and Report Card ledgers were not changed.
- Combined provider-free regression at this stage passes `329/329`; changed
  modules compile, workflow YAML parses, and diff integrity passes. Independent
  exact-candidate browser QA and GitHub exact-head CI remain required before a
  merge decision.

### Consolidated release acceptance — 2026-10-18

- PR #72 (`codex/consolidated-release`) is the integrated review candidate.
  Exact application head `8c15eb281a215d2c40e8aed9ff996734fd13e990`
  passed both exact-head GitHub checks: Customer Experience Autonomous QA run
  `39099596357` and Report Card Registration CI run `39099596366`.
- Independent provider-free QA on that exact head passed `125/125` focused
  tests and rendered 68 screenshots covering 1440, 1024, 390, and 360 px.
  It exercised 32 admin route renders plus four viewer-isolation cases with
  zero browser-console errors and zero horizontal-overflow findings. The
  Claude-ready visual ZIP is `visual-review.zip`, SHA-256
  `469c3c3258d6a8d76b63fb47eb0d963dda5367a4b8a3e0ce554b36b53b6b63ca`;
  its checksum manifest digest is
  `4456d1e73fd5a992b72999c85506e8a9a8c30a82ad6830438cf7ff8eb175a2f8`.
- The exact-head acceptance covers Home, BUY NOW, Research, Charts, Recovery
  Radar, ETF Analysis, Watchlist, Ask ATLAS, and gated Report Card. NVDA and
  MSFT identities were reconciled against coherent retained evidence; BLFS
  remained explicitly withheld/incomplete. Simple and Detailed views,
  financial/valuation/technical content, mobile navigation, and customer/admin
  isolation passed. Provider calls, publication writes, and ledger mutations
  were all zero.
- One governed workflow dispatch against the earlier `dd3a288...` candidate
  (run `39099253550`) passed protected source/runtime materialization and route
  execution but failed its legacy screenshot-name/coverage contract. Its
  visual artifact is `12126465309` (digest
  `10e38f414220e179812021dcb3ad1c53aca376f814e1fdc3a053051b67f66626`)
  and QA artifact is `12126216456` (digest
  `bb2467ffa97c81dcc98c87b58494afe58613bf05692aeccb5507dd2cd10dfd68`).
  This run is retained as workflow-diagnostic evidence, not a passing governed
  certification and not evidence for the final head.
- The hosted preview is still **NOT DEPLOYED** and no URL is claimed. A
  dedicated access-controlled Streamlit preview must be separately authorized
  and bound to the exact reviewed SHA; production must remain unchanged.
- Customer market truth is unchanged: certified session `2026-10-02`,
  publication `2026-10-04T12:21:38-04:00`, governed BUY NOW inventory `11`,
  publication digest
  `72b37697b2f4fc5dabd5438c1a3bb7c068cd12e86253b64e37b8a642c310bf17`.
  No candidate UI test is represented as a data refresh or deployment.

### Milestone 3 infrastructure and preview readiness — 2026-10-18

- PRs #71 and #72 are integrated on authoritative `main` at
  `0758fac72209ab0642e9f1a431db092d1a699119`. Its application tree is identical
  to reviewed PR #72 head `391d0f1b377e1fa0681498f412f4f6782d8c76f6`.
- No hosted preview URL exists and no preview deployment approval is recorded.
  Streamlit Community Cloud cannot pin a commit directly, so acceptance requires
  a dedicated immutable preview branch pointing to `0758fac...`, a separate
  private app, preview-only passwords, and observation of that exact runtime
  source marker. Customer production is unchanged.
- Local provider-free acceptance evidence remains 68 screenshots at 1440,
  1024, 390, and 360 px with zero browser errors, overflow findings, provider
  calls, production writes, or ledger mutations. This is exact-tree local QA,
  not hosted-preview evidence.
- Contabo VPS specifications (Ubuntu 24.04, 12 vCPU, 48 GB RAM, 400 GB SSD) and
  root SSH reachability are verified through owner-supplied terminal evidence.
  Non-root key-only access, independent host-key identity, firewall, update,
  service, encryption, and runner state have not been independently verified.
- No protected evidence was transferred. The DigitalOcean roots
  `/mnt/atlas_incremental_raw` and `/mnt/atlas_incremental_checkpoints` remain
  authoritative. Actual file/byte counts and a current SHA-256 manifest require
  a protected source inventory. Finnhub licensing evidence in the repository
  does not establish permission to move raw licensed payloads to Contabo or an
  independent backup; provider/owner confirmation is required first.
- The existing protected certification workflow remains routed to
  `atlas-worker-1`, uses 64-security batches and a 5-GiB RSS ceiling, and has no
  Contabo runner registration. Registering another runner with the same labels
  while DigitalOcean remains online would make protected routing ambiguous.
  Contabo validation, a unique staging label, exact manifest migration,
  controlled cutover, and full certification each remain separately gated.
- The Milestone 3 review change adds the missing `SOURCE_IDENTITY.md` to visual
  bundles plus fail-closed Contabo migration and 48-GB certification runbooks.
  It does not deploy, migrate, certify, publish, acquire, or activate anything.
- PR #73 (`codex/milestone3-readiness`) latest reviewed head
  `d8cfeda5ad9592a51c0c18211de645c44148f051` passed exact-head CI run
  `39138711019`. Earlier manual run `39138060207` produced QA artifact
  `12140463847` and visual-review artifact `12140314381`, but its final green
  certification and visual-package build steps failed because the app lacked a
  runtime calendar dependency; browser and screenshot failures cascaded from
  that crash. These artifacts remain diagnostic evidence, not a hosted-preview
  pass or production acceptance. A malformed-candidate probe (`39137894185`)
  was correctly rejected before governed browser execution.
- The 48-GB readiness contract was tightened: certification retains its 5-GiB
  operating target and must checkpoint/fail closed at an 8-GiB job-scoped hard
  stop. Additional host RAM is recovery headroom, not permission for unbounded
  scoring memory.

### Milestone 5 premium closeout candidate — 2026-10-18

- **BUILT, NOT DEPLOYED:** branch `codex/milestone5-premium-closeout` starts
  from production-main source `b72fb12a5806d71087ece7837d5e7a6422dfe7e6`
  and preserves PR #75's unified Research financial-availability contract.
- Home now distinguishes the governed inventory from the maximum ten featured
  cards, removes duplicated story/metric treatment, suppresses fragmentary
  classifier prose, and omits empty narrative modules rather than filling them
  with generic copy.
- Research keeps verified facts separate from interpretation, presents newest
  periods first, deduplicates accession-bound concepts, fixes negative-currency
  and share units, moves raw fact IDs into provenance detail, and adds beginner
  explanations for price history, SPY comparison, reported trends, moving
  averages, and RSI. Ask ATLAS now presents its primary input before examples.
- The gated Report Card now distinguishes pending, measured-successful,
  measured-unsuccessful, and still-pending observations without inventing
  returns or exposing internal ledger identifiers. Public access remains OFF.
- Governed evidence packaging requires 1440, 1024, 768, 390, and 360 px after
  captures and includes exact-source before captures whenever the registered
  semantic baseline is supplied. Missing baseline evidence is labeled rather
  than synthesized.
- Current test and screenshot evidence for this branch is recorded only after
  exact-head CI/governed QA completes. No hosted preview URL exists; preview
  deployment remains a separate owner-authorized operation. Customer data,
  production deployment, external AI, provider acquisition, certification,
  publication, Report Card ledgers, and unattended operations are unchanged.
