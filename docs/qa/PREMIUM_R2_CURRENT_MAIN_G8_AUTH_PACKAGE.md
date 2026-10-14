# Premium R2 current-main release and G8 authorization package

## Frozen source boundary

- Review branch: `codex/premium-r2-current-main-integration`
- Current-main parent / rollback target: `fae6a94f96f8f7ed6b24a96a8cdd2fe21ffa703a`
- Frozen Premium UI parent: `246120be073bbc2342fc08f1930d88e7bcf79d15`
- Candidate: the exact branch-tip merge commit containing this package
- Construction: conflict-free two-parent merge; zero automatic or manual product repair
- Deployment: not performed
- Provider calls: zero
- G8: not authorized by this document

The candidate is deployable only if its pushed branch tip, governed run source SHA, downloaded artifact source SHA, and proposed deployment source are identical. Any mismatch is a hard stop.

## Preserved contracts

The merge retains the Premium shared customer Research/Ask authority, certified values, statement history, Research 101, dated-close language, risk/invalidation content, mobile presentation, Watchlist behavior, and governed visual predicates. It also retains current-main PR #18/#19 protected WS3 execution, Report Card gateway, immutable batch planning, fail-closed controls, and methodology. No acquisition, rating, publication, or methodology logic was changed during integration.

## Offline verification

- Release-focused customer + protected-operations suite: `199 passed`.
- Broader changed-surface suite: `438 passed`, `3 failed`.
- The three failures are inherited frozen-candidate assertions in `tests/test_atlas_vnext_ux2_research.py`; both that test file and `ui/customer_research_v2.py` are byte-identical to parent `246120be`. They assert the pre-tab renderer (`not app.tabs`, `AI Investment Brief`, and old confidence copy) against the already-certified tabbed Premium experience. They are disclosed and were not weakened or rewritten during integration.
- Workflow Python compilation and YAML parsing: pass.
- Merge conflicts: zero.

## Governed release certification gate

Dispatch `.github/workflows/atlas_customer_experience_autonomous_qa.yml` for the exact pushed candidate using `mode=certify_only` and `max_repair_attempts=0`. Promotion requires terminal success, exact source identity, required checks, desktop 1440 plus mobile 390/360 coverage, and original screenshots spanning Home, Research, Watchlist, Ask, statements, Research 101, risks, SPY, and technicals. Record run ID, artifact ID/name/digest, check counts, screenshot counts, and any first failing predicate here before requesting G8.

## Deployment identity verification

Immediately before any separately authorized deployment:

1. Resolve the review branch and proposed deployment reference to a full 40-character SHA.
2. Confirm it equals the governed artifact `source_sha` and this package's candidate SHA.
3. Confirm both parents remain reachable and the first parent is rollback target `fae6a94f96f8f7ed6b24a96a8cdd2fe21ffa703a`.
4. Confirm the worktree is clean and no generated/runtime files are included.
5. Reconfirm no rating, methodology, publication-authority, provider, secret, schedule, or environment change is bundled.
6. Record deployer, approver, UTC time, environment, source SHA, artifact digest, and rollback owner.

Any failed identity check stops deployment. This package does not itself grant deployment authority.

## Rollback contract

Rollback target is exact SHA `fae6a94f96f8f7ed6b24a96a8cdd2fe21ffa703a`. The authorized operator must use the platform's normal immutable release/rollback mechanism, verify the resulting deployed identity equals that SHA, and run the customer smoke plan. Do not rewrite shared Git history or alter certified data to simulate rollback.

## Post-deployment customer smoke plan

Using customer-viewer role and no provider acquisition:

1. Verify deployed source identity first.
2. At desktop 1440, mobile 390, and mobile 360, open Home, Research, Watchlist, and Ask.
3. For NVDA, verify identity, Action, Fair Value, Opportunity, Confidence, dated certified close, risks/invalidation, Research 101, annual/quarterly statements with units/source disclosure, SPY/technical context, and Ask evidence/limitations parity.
4. Verify Watchlist add/inspect/remove/persistence and no navigation clipping.
5. Verify CRC renders typed unavailable/withheld evidence without substituted values.
6. Verify internal Report Card/operations surfaces are not exposed to the customer role.
7. Capture source identity and original-resolution screenshots; classify any issue as product, data, harness, operations, or methodology-bound.

Stop and roll back for an identity mismatch, route failure, authority contradiction, unavailable-as-zero presentation, customer exposure of internal operations, blocking mobile clipping, or a P0/P1 trust defect.

## Remaining authorization boundary

Even after green governed certification, G8 remains a human authorization decision. Required human inputs are the exact candidate SHA, terminal run and artifact identities, screenshot review, named deployer/approver, environment, maintenance window, smoke owner, rollback owner, and explicit authorization token or recorded approval under the governing release process.
