# ATLAS Live Operations Status

**Authoritative as of:** 2026-10-16
**Repository main:** `c038e31d0e055a0569e8fa05e0ae2f11203c5c9a`

**Verified deployed runtime:** `e838d05b3c92563c514d4d185365b4c8e97bfdba`
**Production:** [stock-ai-dashboard.streamlit.app](https://stock-ai-dashboard.streamlit.app/)  
**Production-truth correction merged:** [PR #35](https://github.com/abandukda/stock-ai-dashboard/pull/35)

Evidence policy: a merge is not deployment; a provider-free run is not acquisition; a monitor ping is not publication; and repository data is not customer-visible until authenticated production evidence proves it.

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
