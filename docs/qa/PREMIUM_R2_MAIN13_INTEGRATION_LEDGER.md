# Premium R2 + post-PR13 integration ledger and handoff

## Candidate construction

- Certified Premium R2 parent: `0ae854ed3dc1c50acd891d8454dba4577e97b50a`
- Post-PR13 main parent: `5c76b87e624da37e2b67ae2475978fc60d5f0137`
- Main merge: PR #13, `Merge pull request #13 from abandukda/codex/report-card-g2-activation-artifact`
- Review branch: `codex/premium-r2-main13-integration`
- Production/deployment: unchanged
- Provider calls: none
- G8: closed

The exact candidate SHA is the branch tip that contains this ledger. Its two-parent merge commit is the integration boundary; exact-SHA governed QA must report the same `source_sha` before this candidate can supersede the prior visual evidence.

## Reconciliation result

The merge was conflict-free. PR #13 adds Report Card operational controls, protected transition and read-only contracts, stable operations/customer/research gateways, and their offline tests. It does not modify the Premium R2 correction files introduced by `0ae854e`, including shared customer Research authority, Ask parity, financial/EPS presentation, governed visual assertions, or embedded certified statement histories.

No compatibility rewrite, certified score change, methodology change, data regeneration, provider acquisition, deployment, or G8 action was performed.

## Preserved Premium R2 authority

The integrated candidate retains the six correction contracts:

1. Research and Ask resolve availability from the authoritative shared customer view.
2. NVDA filing-reported diluted EPS remains source-linked, with 17 annual records, three unverified share-basis discontinuities, and no split-adjusted reconciliation claim.
3. Desktop and mobile identity use the same ticker/company/sector authority.
4. Company-specific measured risks remain separate from general monitoring conditions and honest unavailable states.
5. Primary customer price references remain dated `Last Certified Close` or `Signal Reference Price`, not live/current prices.
6. Governed risk capture requires substantive risk content and retains its negative heading-only/blank fixture.

Certified Action, Fair Value, Opportunity, Confidence, six-pillar values, publication authority, and methodology remain unchanged.

## Preserved Report Card operations

The post-PR13 merge retains:

- protected G2 transition and read-only Report Card access contracts;
- closed-sentinel creation/verification and exchange-calendar boundaries;
- fail-closed licensed acquisition and operational-control services;
- stable registered operations, Report Card, customer QA, and Research gateways;
- provider-free offline validation paths and immutable execution identities.

These operational additions do not broaden customer visibility or authorize a protected run, provider call, deployment, or schedule activation.

## Verification ledger

- Focused combined Premium R2 + Report Card suite: `245 passed`.
- Test duration: `11.60s` in the isolated integration worktree.
- Complete offline `tests/` inventory: `2830 passed`, `1 skipped`, `103 failed` in `88.00s`. The failures are pre-existing cross-era contracts and environment assumptions (including Python 3.11-only browser tests running under 3.14); none touch the conflict-free PR13 merge surface. They are disclosed, not represented as green.
- Repository-root collection: blocked by legacy `test_alerts.py`, which calls Yahoo during import. It was not retried with network access because this integration forbids provider calls.
- Object identity check: all 26 files introduced by the frozen Premium R2 correction are byte-identical to `0ae854e`; all 11 files changed by PR #13 are byte-identical to post-merge main `5c76b87`.
- Merge conflicts: zero.
- Exact-SHA governed customer QA: required because the Git tree changed after the prior certified run.
- Prior Premium R2 governed evidence (pre-integration): run `38592139855`, artifact `11909881038`, digest `cb1a29258d71aa7684b108b570ec9f667b0234709124e19852cbbd816119a8d6`, required `126/126`, all `144/144`, screenshots `200/200`, defects `0`.

The prior run proves the certified Premium R2 parent only. It must not be represented as exact-SHA evidence for this integrated branch tip.

## Exact-SHA acceptance contract

The new governed run must:

1. Resolve its candidate to the pushed branch tip and report the identical 40-character `source_sha`.
2. Use `certify_only` with zero repair attempts.
3. Preserve required desktop 1440, mobile 390, and mobile 360 customer captures for Home, Research, Watchlist, Ask, financial statements, Research 101, risks, SPY and technical context.
4. Pass customer/admin isolation, Research/Ask parity, identity, dated-price, risk-content positive/negative, statement-history and unavailable-state predicates.
5. Produce a complete artifact with immutable artifact ID and SHA-256 digest.

Failure or incomplete screenshot coverage blocks promotion. A harness failure is not silently relabelled as product success.

## Independent review handoff

Reviewers must assess the new exact-SHA artifact, not the pre-integration screenshots alone. Validate both customer trust/presentation and the absence of newly exposed Report Card/internal operations. Cite exact screenshot filenames for every finding and classify it as product, data, harness, operations, or methodology-bound.

Automated acceptance does not fabricate Claude/ChatGPT acceptance or five beginner participants. Independent commercial review and the genuine five-person beginner-comprehension protocol remain separate human decisions.
