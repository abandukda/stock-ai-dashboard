import copy

import pytest

from scripts.plan_ws3_published_acquisition import build_plan, digest, recover_membership


def source():
    tickers = [f"X{i:04d}" for i in range(1298)]
    records = [{"ticker": t, "source_sha": "s", "candidate_digest": "c", "publication_certification": {"ticker": t, "customer_publication_allowed": True}} for t in tickers]
    manifest = {"workflow_run_id": "37216506983", "customer_publication_count": 1298, "source_commit_sha": "s", "executor_candidate_identity": {"candidate_digest": "c"}, "artifact_hashes": {"full_evaluation_pool.json": "e"}, "artifact_lineage": {"full_evaluation_pool.json": {"semantic_sha256": "e"}}}
    return tickers, records, manifest


def membership_fixture():
    tickers, records, manifest = source()
    import scripts.plan_ws3_published_acquisition as module
    old = module.EXPECTED_MEMBERSHIP_SHA256; module.EXPECTED_MEMBERSHIP_SHA256 = digest(tickers)
    try: return recover_membership(records, manifest, source_file_sha256="f"*64)
    finally: module.EXPECTED_MEMBERSHIP_SHA256 = old


def test_membership_is_exact_source_bound_and_immutable():
    m = membership_fixture()
    assert m["membership_count"] == 1298 and m["immutable"] is True
    assert m["membership_sha256"] == digest(m["tickers"])
    assert m["artifact_sha256"] == digest({k:v for k,v in m.items() if k != "artifact_sha256"})


def test_plan_preserves_existing_11_and_has_exact_deduplicated_budgets():
    m = membership_fixture(); plan = build_plan(m, m["tickers"][:11])
    assert plan["request_counts"] == {"annual_statements":1287,"quarterly_statements":1287,"earnings_actuals":1298,"eps_estimates":1298,"revenue_estimates":1298,"price_history":1298,"company_profile":1298,"sec_filings":1298,"company_catalysts":1298}
    assert plan["total_call_budget"] == 11660 and plan["batch_count"] == 467
    assert plan["provider_calls_performed"] == 0
    keys=[(r["dataset"],r["ticker"]) for b in plan["batches"] for r in b["manifest"]["requests"]]
    assert len(keys)==len(set(keys))==11660


def test_every_batch_is_hash_bound_zero_retry_and_separately_authorized():
    m=membership_fixture(); plan=build_plan(m,m["tickers"][:11])
    for b in plan["batches"]:
        assert b["manifest_sha256"]==digest(b["manifest"])
        assert b["manifest"]["pacing"]["retry_count"]==0
        assert b["required_authorization_token"].endswith(b["manifest_sha256"])
        assert b["manifest"]["state"]=="AWAITING_EXACT_OWNER_AUTHORIZATION"


def test_lineage_membership_and_existing_scope_drift_fail_closed():
    _,records,manifest=source(); bad=copy.deepcopy(manifest);bad["artifact_lineage"]["full_evaluation_pool.json"]["semantic_sha256"]="x"
    with pytest.raises(ValueError,match="LINEAGE_MISMATCH"):recover_membership(records,bad,source_file_sha256="f"*64)
    m=membership_fixture()
    with pytest.raises(ValueError,match="PRESERVED_SCOPE_INVALID"):build_plan(m,m["tickers"][:10])


def test_stop_rules_are_conservative_and_no_authority_changes():
    m=membership_fixture();p=build_plan(m,m["tickers"][:11])
    assert {"HTTP_429","AUTH_OR_ENTITLEMENT_FAILURE","RAW_PERSISTENCE_FAILURE","MEMBERSHIP_OR_MANIFEST_DRIFT"} <= set(p["execution_policy"]["stop_conditions"])
    assert p["rating_authority"]==p["publication_authority"]=="UNCHANGED"
