# Finnhub Full-Core Activation Runbook

This runbook prepares a credential for shadow certification only. Passing any
step does **not** grant Finnhub production authority, alter ATLAS methodology,
or authorize a provider cutover.

## Activation checklist

1. Install the full-Core credential in the GitHub repository secret named
   `FINNHUB_API_KEY`. The workflow binds that secret to the environment variable
   `FINNHUB_API_KEY`; the value must never be printed, placed in an artifact, or
   committed.
2. Only after paid Core activation is contractually confirmed, set
   `ATLAS_FINNHUB_LICENSE_CLASS=PAID_CORE_CERTIFICATION` for the bounded
   certification workflow. Demo remains the fail-closed default.
3. Confirm credential detection only with a non-empty assertion. Do not log the
   value or a reversible derivative.
4. Dispatch `ATLAS Finnhub Provider-Only Certification` on
   `codex/home-promotion-market-today-release` with `run_broad_p_fcf=true`.
5. The workflow first runs the four-symbol entitlement smoke. It requests
   `company_profile`, `financial_statements`, and `basic_financials` for ORCL,
   COST, GM, and AMGN. Under demo credentials these symbols are intentionally
   outside the documented whitelist, so HTTP 403 is classified as
   `EXPECTED_DEMO_SYMBOL_RESTRICTION` and the state remains
   `PAID_CORE_BREADTH_UNTESTED`. This is informational, not a negative finding
   about paid Core. It stops before the 152-symbol run.
6. Only after paid activation and `ENTITLEMENT_SMOKE_PASS`, acquire the governed 152-symbol universe,
   certify classification and historical evidence, construct provider-neutral
   P/FCF peers, and invoke the existing Professional V2 route.
7. Retain these immutable review artifacts:
   `finnhub_provider_only_certification.json`,
   `finnhub_core_entitlement_smoke.json`, and
   `finnhub_p_fcf_peer_certification.json`.

## Success criteria

- Smoke: all 12 symbol/family checks are contract-complete; entitlement,
  provider-data, contract, and integration failure counts are zero.
- Broad acquisition: universe identity matches; all three required families and
  sector/industry/security-type classification are recorded; entitlement and
  ATLAS integration failures are zero.
- Peer evidence: each target has at least three certified, comparable peers under
  the existing rules.
- Valuation: all eight fixed targets publish the unchanged Professional V2 P/FCF
  route. Downstream FV, Opportunity, Confidence, and Action reachability is
  reported, not forced.
- Report state: `FINNHUB_CORE_READY_FOR_FINAL_CERTIFICATION`. This state still
  does not grant production authority.

## Failure classification

- `ENTITLEMENT_SMOKE_FAIL`: at least one required family is blocked by the
  paid-Core credential. Stop before broad acquisition.
- `EXPECTED_DEMO_SYMBOL_RESTRICTION`: contractual demo behavior for an
  outside-whitelist symbol. Report `PAID_CORE_BREADTH_UNTESTED`; do not infer
  paid-Core coverage failure and do not run broad acquisition.
- `PROVIDER_DATA_UNAVAILABLE`: the credential is entitled but the provider has no
  company data. Do not treat this as entitlement failure.
- `PROVIDER_CONTRACT_UNRESOLVED`: returned data lacks required explicit period,
  currency, unit, lineage, or classification semantics.
- `ATLAS_INTEGRATION_FAILURE`: adapter/runtime/mapping failed despite usable
  provider evidence.

No failure permits a fallback, synthetic fact, altered peer minimum, or relaxed
certification rule.

## State machine

```text
CURRENT_DEMO_ENTITLEMENT
  -> FULL_CORE_CREDENTIAL_INSTALLED
  -> ENTITLEMENT_SMOKE_PASS
  -> BROAD_PEER_CERTIFICATION_PASS
  -> FINNHUB_CORE_READY_FOR_FINAL_CERTIFICATION

Failure exits:
  ENTITLEMENT_SMOKE_FAIL
  PROVIDER_DATA_UNAVAILABLE
  PROVIDER_CONTRACT_UNRESOLVED
  ATLAS_INTEGRATION_FAILURE
```

Provider certification and production authority are separate state machines.
None of these states changes production acquisition or permits promotion.

## Rollback / no-authority behavior

If smoke or broad certification fails, revoke or replace the repository secret,
retain the audit artifact, and leave the current production authority unchanged.
Do not publish, promote, or restore data from the shadow run. A previous
credential may be restored only as a credential operation; it does not change
the certification result.

## Forward valuation hold

`FORWARD_VALUATION_CONTRACT_PENDING` remains in force. The unresolved external
documentation is limited to:

- estimate currency;
- EPS currency compatibility;
- revenue, EBIT, EBITDA, and FCF estimate units and scale;
- revision/vintage semantics when historical revisions are claimed.

Forward P/E, EV/EBITDA, and forecast-FCF methods remain unavailable where these
contracts are required. They are not prerequisites for certifying historical
P/FCF.

The genuine unresolved Finnhub items are limited to EPS currency compatibility;
revenue, EBIT, EBITDA, and FCF estimate unit/scale/currency contracts; revision
and vintage semantics when historical revisions are claimed; beta methodology
limitations; and paid-Core breadth until commercial activation.

## Release-preparation partition

Work that can proceed under demo access: deterministic provider-boundary and
presentation tests, methodology-invariance checks, exact-candidate lineage
harness maintenance, narrative fixture review, mobile/desktop fixture QA, and
commercial-authority package preparation without claiming breadth.

Work that must wait for paid Core: the outside-whitelist entitlement smoke, the
152-symbol acquisition, live peer-coverage certification, eight-target P/FCF
certification, and any authority proposal relying on those results.

Work that must wait for estimate documentation: canonical forward P/E,
forward-EV/EBITDA, forward-FCF/DCF inputs, and historical estimate-revision
analytics. Historical P/FCF remains independent of these forward contracts.
