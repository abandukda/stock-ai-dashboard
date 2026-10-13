from datetime import datetime, timedelta, timezone
import pytest

from services.report_card_operational_controls import (
    classify_unavailable, compare_entry_prices, detect_restatement, heartbeat_decision,
    reconcile_publication, validate_entitlement,
)


UTC = timezone.utc


def identity(signal_id="s1"):
    return {"signal_id": signal_id, "candidate_digest": "c", "publication_digest": "p",
            "evaluation_snapshot_id": "e", "decision_digest": "d"}


def test_publication_reconciliation_never_infers_customer_replicability():
    signals = [identity("published"), identity("withheld"), identity("unknown")]
    evidence = [{**identity("published"), "customer_visible_artifact": True, "evidence_id": "a"},
                {**identity("withheld"), "withheld_certification": True, "evidence_id": "b"}]
    result = reconcile_publication(signals=signals, publication_rows=evidence)
    assert result["counts"] == {"PROVEN_PUBLISHED": 1, "PROVEN_WITHHELD": 1, "UNPROVEN": 1}
    assert result["customer_replicable_count"] == 1


def test_entry_comparison_does_not_change_method():
    rows = compare_entry_prices(signals=[{**identity(), "ticker": "NVDA", "reference_price": 100,
        "publication_timestamp": "2026-10-08T15:00:00+00:00"}],
        closes={"NVDA": {"2026-10-09": 101}}, sessions=["2026-10-08", "2026-10-09"])["rows"]
    assert rows[0]["absolute_difference"] == 1
    assert rows[0]["method_changed"] is False and rows[0]["owner_decision_required"] is True


def test_restatement_delisting_and_entitlement_fail_closed():
    assert detect_restatement(prior={"2026-10-09": 10}, current={"2026-10-09": 11})["fail_closed"]
    assert classify_unavailable(price_status="MISSING", delisting_evidence={}) == "TEMPORARILY_UNAVAILABLE"
    assert classify_unavailable(price_status="MISSING", delisting_evidence={"certification_status":"CERTIFIED", "delisted":True, "evidence_id":"x"}) == "DELISTED"
    with pytest.raises(PermissionError, match="ENTITLEMENT"):
        validate_entitlement({"status":"APPROVED", "contract_id":"x", "effective_at":"now", "capabilities":["historical_ohlcv"]})
    assert validate_entitlement({"status":"APPROVED", "contract_id":"x", "effective_at":"now",
        "capabilities":["historical_ohlcv","splits","dividends"]})["provider_calls"] == 0


@pytest.mark.parametrize("started,completed,status,expected", [
    (None,None,None,"NEVER_STARTED"),
    (datetime(2026,10,9,20,tzinfo=UTC),None,None,"DID_NOT_COMPLETE"),
    (datetime(2026,10,9,20,tzinfo=UTC),datetime(2026,10,9,20,1,tzinfo=UTC),"FAILURE","FAILED"),
])
def test_independent_dead_man_states(started, completed, status, expected):
    result = heartbeat_decision(now=datetime(2026,10,9,22,tzinfo=UTC),
        expected_start=datetime(2026,10,9,20,tzinfo=UTC), started_at=started,
        completed_at=completed, completion_status=status, grace=timedelta(minutes=30))
    assert result == {"status": expected, "alert_required": True, "independent_of_github_actions": True}
