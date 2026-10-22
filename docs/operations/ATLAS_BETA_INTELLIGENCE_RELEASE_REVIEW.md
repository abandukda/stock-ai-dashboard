# Integrated beta-intelligence release review

Review date: 2026-10-22. Base: `f9555667edd42da6959983543b7a716b85504356`.
This is a provider-free review candidate, not an approved production release.
Pin final approval and all CI/screenshot evidence to the final integrated head after
remaining review changes are committed; constituent commit hashes are not that head.

## Customer problem and resulting behavior

The retained-data Home experience over-emphasized empty market space and left the
actual opportunity inventory and source age less prominent. This candidate compacts
the unavailable-market hero, groups action counts, foregrounds admitted opportunities
and their dates, and renders mobile comparison cards. It shows the actual admitted
inventory rather than padding the Top 15 target. Supplied governed market interpretation
and company thesis/risk text remain intact; no new financial narrative, ranking, price,
exclusion, sizing or certified decision is created.

Customer earnings-call buttons previously could invoke a configured transcript provider.
They now read only an explicitly injected, existing approved private cache. Transcript
availability and AI-summary availability are separate states; a retained call may be
available while its separately approved summary remains pending. This candidate also
adds an isolated personal watchlist controller and UI with ownership checks at every
operation, instead of treating a shared viewer session as individual account authority.

## Included slices and evidence boundaries

| Slice | Built behavior | Validation available or required | Remaining boundary |
|---|---|---|---|
| Home / BUY NOW | Adaptive retained-data command center, dated inventory, fair-value comparison, responsive cards and existing Research drill-down | Affected offline regressions and generated AppTest exist; generated real-browser review at 360/768/1440 is required on final head | Original-design parity and current financial freshness need actual production comparison; no deployment acceptance yet |
| Personal watchlists | Create/rename/default/delete, catalog search, persistent add/remove, owned Research navigation, account-switch stale-form guards | Offline two-account/forged-ID/expiry/revocation tests and temporary SQLite AppTest; generated responsive browser journey added | Disconnected by default; no identity provider, production route, provisioning or storage configuration is enabled |
| Earnings | Read-only private cache index and exact-quarter derived projection; pending/missing/disconnected states | Earnings receipt records 88 offline passes with sockets denied and zero attempted connections; responsive generated browser test added | Disconnected by default; no production cache is selected, no call acquired and no genuine model output generated |
| Research history | Exact captured-byte digest distinguished from normalized-object digest; gateway receipt/telemetry consistency checked | Negative tests cover incomplete/tampered captures, telemetry, call accounting, invalid JSON and review-wrapper admission refusal | Returns `OWNER_REVIEW_ONLY_NOT_PUBLISHED`; no promotion or financial certification |
| Report Card / certified source data | Existing authority, source and publication boundaries retained | No new observation or retained-host certification proof is produced here | Original ledger, backup/source authority, adjustments, entry methodology and benchmark evidence remain independent P0 gates |

The parent integrated validation reports 876 offline passes plus 8 subtests, 215
targeted passes, zero network attempts, unchanged guarded source hashes, and clean
compile/YAML/diff checks for the reviewed 25-file inventory (including this review). Final exact-head governed
CI and hosted browser evidence remain required. An earlier component receipt is
evidence only for its listed files/tests, not for the final release.
No green-CI result proves deployment, authenticated live behavior or current licensed data.

## Trusted backend dependencies

Personal watchlists require an injected server resolver that genuinely verifies issuer,
audience, signature, expiry, membership and revocation for an already provisioned account.
`VerifiedWatchlistSubject` is a typed result, not authentication proof. A view key only
rejects stale forms; every read/write still resolves current identity and ownership.
The production shared-password navigation does not create this resolver or enable the
personal route. Private persistence, backup and real two-account acceptance require an
explicit reviewed binding and owner decisions.

Earnings requires an explicitly injected `ReadOnlyTranscriptCache` with an approved
private root, account configuration, license/display permission, retention deadline and
summary policy revision. `render_earnings_vnext(..., transcript_cache_reader=None)` stays
unconnected by default. The reader does not create a directory/database, acquire a
transcript, generate a summary, repair source records or choose a production path. It
uses SQLite `mode=ro`, query-only and read transactions, refuses existing sidecars/WAL
headers, and validates account/period/license/source/summary lineage before projection.
The private writer MAC prevents copied/rekeyed records crossing account identity.
Unsigned legacy records require offline revalidation; there is no automatic rewrite,
refetch or inferred entitlement. Raw text, excerpts, credentials, account namespace and
MACs are not customer projections. A retained quarter is not proof of the latest release.

## Raw-history review and promotion gates

`build_history_review_from_gateway_capture` checks exact complete raw bytes against
receipt hashes, run/source/scope identifiers, ordinal telemetry and bounded successful
call accounting before building an in-memory review candidate. Normalized-only callers
now explicitly report `raw_capture_binding=NOT_SUPPLIED`; a normalized digest no longer
masquerades as the captured response digest. The review wrapper itself is refused by
the market read-model loader.

Hash consistency does not establish provider authenticity, licensed entitlement,
trusted capture time, adjustment authority or publication approval. Capture/check times,
raw evidence identity and verified adjustment evidence remain supplied by the governed
caller. Gateway telemetry currently does not independently attest capture timestamps.
Receipt scope-hash agreement must be reconciled to the separately approved immutable
scope and its actual request parameters. Original raw archives, independent backup
integrity, session continuity and corporate actions still require separate evidence.
The nested bundle must not be extracted and promoted merely because this review passes.
There is no transport, artifact write, read-model installation, ledger mutation or
production promotion in this pure adapter.

## Acceptance sequence

1. Record final exact head and pass its fresh required offline and governed checks.
2. Run and inspect generated actual-browser Home, Earnings and personal journeys at
   desktop/tablet/mobile widths. Earnings screenshots are labelled
   `GENERATED_NOT_PRODUCTION` under `audit_results/premium_home/earnings_cache`; they
   use temporary mock evidence and are never production or real-transcript acceptance.
3. Review original references against actual rendered Home/Research/Report Card, keeping
   confirmed parity separate from proposed improvements and unavailable assets.
4. Obtain exact-head owner merge/release approval. A merge does not authorize new
   acquisition, paid AI, identity/storage configuration or financial publication.
5. After approved deployment, verify deployed source SHA and authenticated production
   screenshots/customer journeys. Keep BUILT, TESTED, MERGED, DEPLOYED and LIVE VERIFIED
   distinct; this document asserts only implemented review-branch behavior.
6. Approve trusted identity/cache bindings separately, then test real account isolation
   and retained-evidence permissions before beta enablement. First licensed acquisition,
   AI generation, certified publication and prospective observation append each retain
   their separate scoped execution approvals.

## Unchanged P0 decisions

This release does not recover either protected host, attest original ledger/WAL or
independent backups, certify all retained shards, acquire missing AMZN/MPC/VLO/SPY
prices, prove current market data or append genuine prospective observations. It does
not enable a daily refresh or establish its operational execution receipt. Report Card
public activation remains OFF. No licensed provider call, paid external model call,
production ledger write, financial publication, protected migration, routing change or
infrastructure operation is authorized or executed by this review candidate.

## Browser-discovered repairs before readiness

Initial exact-head Home run `39846567296` failed: 113 offline checks passed,
13 render tests ran with two errors; only 39 raw PNGs were produced. Saved DOM
proved Home selected the correct ticker but the test's empty marker had no visible
box. The fixture now displays and asserts the selected Research ticker explicitly.
Watchlist creation also succeeded; Streamlit's accessible name included the selected
list, so the browser now locates the labelled combobox and asserts the owned name.
Actual screenshots exposed a real hero defect: indented HTML became a Markdown code
block. The heading markup is now unindented and browser QA requires the real visible
heading and absence of a code block. No financial or isolation assertion was removed.

The original nine Earnings captures correctly covered disconnected, uncached and
cached-transcript/summary-pending states. An additional generated cached-summary mode
now exercises a mock-grounded analysis through the real read-only reader at all three
widths; it is explicitly not external AI or real transcript evidence. A local actual
Streamlit interaction verified its displayed claim, availability and private-source
exclusion. The 27 affected personal/Home offline tests passed after these repairs;
fresh exact-head hosted browser/CI acceptance is still required.
