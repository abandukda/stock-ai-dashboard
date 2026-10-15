import pytest
import json
import subprocess
import sys

from services.finnhub_incremental_post_close import (
    FUNDAMENTAL_FAMILIES,
    IncrementalCeiling,
    build_incremental_plan,
    validate_incremental_receipts,
)


def symbols(count=1298):
    return [f"S{index:04d}" for index in range(count)]


def test_first_live_plan_has_exact_bounded_ceiling_and_zero_provider_calls():
    plan = build_incremental_plan(
        session="2026-10-14", customer_symbols=symbols(),
        changed_fundamental_symbols=symbols(50),
    )
    assert plan["provider_calls"] == 0
    assert plan["request_count"] == plan["exact_max_requests"] == 2746
    assert plan["request_ceiling"] == {
        "completed_session_price": 1298,
        "filing_change_probe": 1298,
        "changed_fundamentals": 150,
    }
    assert len(plan["request_keys"]) == len(set(plan["request_keys"]))
    assert plan["methodology_mutation"] == "NONE"
    assert plan["publication_mode"] == "EXISTING_ATOMIC_PROMOTER"


def test_changed_fundamentals_are_the_only_deep_fundamental_requests():
    changed = ["S0002", "S0001"]
    plan = build_incremental_plan(
        session="2026-10-14", customer_symbols=symbols(),
        changed_fundamental_symbols=changed,
    )
    assert plan["request_count"] == 1298 * 2 + len(changed) * len(FUNDAMENTAL_FAMILIES)
    for family in FUNDAMENTAL_FAMILIES:
        assert plan["family_counts"][family] == 2


def test_scope_and_change_ceiling_fail_closed():
    with pytest.raises(ValueError, match="CUSTOMER_SCOPE_MISMATCH"):
        build_incremental_plan(session="2026-10-14", customer_symbols=symbols(1297))
    with pytest.raises(ValueError, match="CHANGE_CEILING_EXCEEDED"):
        build_incremental_plan(
            session="2026-10-14", customer_symbols=symbols(),
            changed_fundamental_symbols=symbols(51),
        )
    with pytest.raises(ValueError, match="OUTSIDE_SCOPE"):
        build_incremental_plan(
            session="2026-10-14", customer_symbols=symbols(),
            changed_fundamental_symbols=["OTHER"],
        )


def test_receipts_require_exact_fresh_complete_deduplicated_plan_ownership():
    ceiling = IncrementalCeiling(customer_symbols=2, changed_fundamental_symbols=0)
    plan = build_incremental_plan(
        session="2026-10-14", customer_symbols=["A", "B"], ceiling=ceiling,
    )
    receipts = [
        {"request_key": key, "session": "2026-10-14", "status": "AVAILABLE"}
        for key in plan["request_keys"]
    ]
    assert validate_incremental_receipts(plan=plan, receipts=receipts)["status"] == "PASS"
    with pytest.raises(ValueError, match="INCOMPLETE"):
        validate_incremental_receipts(plan=plan, receipts=receipts[:-1])
    with pytest.raises(ValueError, match="DUPLICATE"):
        validate_incremental_receipts(plan=plan, receipts=[*receipts, receipts[0]])
    stale = [dict(item) for item in receipts]
    stale[0]["session"] = "2026-10-13"
    with pytest.raises(ValueError, match="STALE_SESSION"):
        validate_incremental_receipts(plan=plan, receipts=stale)


def test_cli_reads_only_customer_publication_scope_and_writes_plan_atomically(tmp_path):
    rows = [
        {"ticker": ticker, "publication_certification": {"customer_publication_allowed": True}}
        for ticker in symbols()
    ]
    rows.append({"ticker": "INTERNAL", "publication_certification": {"customer_publication_allowed": False}})
    publication = tmp_path / "market_full_scan.json"
    output = tmp_path / "plan.json"
    publication.write_text(json.dumps(rows))
    subprocess.run([
        sys.executable, "scripts/plan_finnhub_incremental_post_close.py",
        "--session", "2026-10-14", "--publication", str(publication),
        "--output", str(output),
    ], check=True)
    plan = json.loads(output.read_text())
    assert plan["customer_symbol_count"] == 1298
    assert plan["request_count"] == 2596
    assert plan["provider_calls"] == 0
