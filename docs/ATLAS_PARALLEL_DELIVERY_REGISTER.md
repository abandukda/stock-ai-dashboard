# ATLAS integrated delivery register

Baseline: `f00634e7a83264b99b6ddf4c2d3644a6cd10084d`. This register coordinates engineering; it does not authorize acquisition, deployment, infrastructure, financial publication or ledger operations.

## Ownership and contracts

| Workstream | Development owner | Integration contract | Independent next acceptance |
|---|---|---|---|
| Certified data / daily refresh | data_cycle | Finite valid OHLCV, source lineage, corporate-action state; no inferred contiguous session | Invalid observations rejected before COMPLETE; retained archives require separate one-run owner approval |
| Home / BUY NOW | home_design_delivery | Existing financial authority, stale-data gates and investor exclusions | Responsive source-dated opportunities and navigation; real production acceptance separate |
| Research | research_delivery | Admitted history only; missing admission receipt is not configuration proof | Preserve chart assertions; no financial-module reload |
| AI summaries | research_delivery | Cited evidence IDs, valid nonempty response, cache revalidation | Invalid/empty model output fails closed; paid production calls separate |
| EarningsCall | earnings_delivery | Entitlement failures cannot become a different quarter; transcript and summary states distinct | Mock HTTP/error/cache pipeline; no subscription calls |
| Report Card | report_card_delivery | Immutable envelope registration distinct from reference/publication timing | Synthetic-ledger timing regression; original ledger untouched |
| Beta identity / watchlists | beta_delivery | Trusted server identity, isolated approved store, deny shared credentials | Isolation/revocation/expiry tests; production IdP/store activation separate |
| Original design / Claude review | home_design_delivery | Original references primary; no illustrative figures reused | Inspected renders at desktop/tablet/mobile; no inferred parity |

## Shared dependencies and approval boundaries

| Dependency | Affected capabilities | Engineering can proceed | Required owner action |
|---|---|---|---|
| Retained archive contents not verified | Data certification, Research history, Report Card evidence | Streaming verifier and malformed-data regressions | Exact-main one-run retained-archive verification approval |
| Original host and independent backup authority unavailable | Genuine certification, ledger audit/recovery | Provider-free validation and observation simulation | Sanitized host diagnostics, authoritative paths/digests and recovery approval |
| No certified contiguous-session boundary | Daily refresh | Scheduler/reconciliation/fail-closed testing | Establish session from certified evidence, then approve configuration |
| Research runtime admission receipt unavailable | Production charts | Grounded-analysis tests and unchanged chart assertions | Inspect authorized runtime authority; no assumed source pins |
| Live licensed acquisition / external AI | Current financial/transcript/genuine AI intelligence | Mock transport, normalization, source/cache contracts | Scoped one-use execution package, budget/expiry and explicit approval |
| Trusted individual IdP and personal store unbound | Individual beta login/watchlists | Opt-in adapter and ownership tests | Approve production identity/store configuration |
| Real observation timing and SPY evidence unresolved | Internal Report Card launch | Honest UI, bundle methodology, synthetic checks | Approve defensible methodology, missing acquisition and append separately |
| Production acceptance | All customer-facing features | Candidate renders and offline/governed CI | Exact-head merge/deployment approval, then authenticated live verification |

Public Report Card remains OFF. Historical 20 signals / zero observations is not a fresh ledger audit. Fixture renders are not production screenshots. Build/test completion never implies merge, deployment or live verification.

## Current execution receipts

All six isolated track owners produced local commits from the baseline; the integrator cherry-picked them into one candidate. No track commit is a production release.

| Track | Local source commit | Executed validation | Remaining product acceptance |
|---|---|---|---|
| Data | eaa21b2675eb3ce65c5017b80a06a90da45dba48 | 121 tests, zero network attempts; baseline accepted NaN as COMPLETE | Genuine retained certification/current refresh not executed |
| Home + design | e5edf62f43b9c8defff802f36a8d923dcd4bda65 | 114 offline tests; three-viewport actual generated browser run | Original parity and deployed full journey open |
| Research + AI | c7d44c36e0be2af9f9331a402bfc15f918582721 | 166 tests, zero network attempts; baseline accepted empty reply | Production chart discrepancy unresolved; external AI inactive |
| Earnings | fee5f3e48f891282f5fb920cf0a169f474e07fb1 | 75 targeted;891 tests+8 subtests full pre-integration selection, zero network attempts | Production cache/entitled fetch/genuine analysis open |
| Report Card | ec41359e2453dd7bc9f68271be2043412655ac09 | 105 scoped tests, zero network attempts; integrated generated registration renders360/768/1440 PASS | No fresh original-ledger audit or observation append |
| Beta | 212e2ef095e0c54b649aa9f1379301175cb075bb | 71 tests, zero network attempts; real UserInfoProxy and isolated widget/store journeys | Actual production IdP/store provisioning unbound |

Counts overlap and must not be added. Integrator additionally ran116 cross-track tests with zero network attempts; final governed-selection and exact-head remote CI are separate receipts. Generated images are review evidence only. Current production remainsf00634e; latest completed production39866994486 passed authentication/Home but failed required NVDA history,34/36 required. Earnings/private Report Card not visited. No change in this candidate is MERGED, DEPLOYED or LIVE VERIFIED.
