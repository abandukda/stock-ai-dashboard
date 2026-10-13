from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import pytest

from services.report_card_operational_controls import (
    classify_unavailable, compare_entry_prices, deliver_heartbeat_alert, detect_restatement,
    heartbeat_contract, heartbeat_decision,
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


def test_reviewed_entitlement_fixtures_and_dispatch_package(tmp_path):
    root = Path(__file__).parent / "fixtures/report_card"
    assert validate_entitlement(json.loads((root / "entitlement_valid.json").read_text()))["status"] == "ENTITLEMENT_EVIDENCE_VALID"
    with pytest.raises(PermissionError, match="ENTITLEMENT"):
        validate_entitlement(json.loads((root / "entitlement_missing_dividends.json").read_text()))
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    command = ["python3", "scripts/build_report_card_protected_dispatch.py", "--source-sha", "a" * 40,
               "--start-date", "2026-10-08", "--as-of", "2026-10-09T21:00:00+00:00"]
    subprocess.run([*command, "--output", str(first)], check=True)
    subprocess.run([*command, "--output", str(second)], check=True)
    package = json.loads(first.read_text())
    assert first.read_bytes() == second.read_bytes()
    assert package["dispatch_performed"] is False and package["gates_opened"] == []


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


def test_alert_adapter_requires_health_and_confirmed_delivery():
    class Adapter:
        healthy = True
        delivery = "delivery-1"
        def healthcheck(self): return self.healthy
        def send(self, payload):
            assert payload == {"event": "REPORT_CARD_DEAD_MAN", "state": "NEVER_STARTED"}
            return self.delivery
    adapter = Adapter()
    decision = {"status": "NEVER_STARTED", "alert_required": True}
    assert deliver_heartbeat_alert(decision=decision, adapter=adapter)["delivery_id"] == "delivery-1"
    adapter.healthy = False
    with pytest.raises(RuntimeError, match="DESTINATION_UNHEALTHY"):
        deliver_heartbeat_alert(decision=decision, adapter=adapter)


def test_heartbeat_contract_is_run_bound_monotonic_and_deterministic():
    decision={"status":"NEVER_STARTED","alert_required":True}
    heartbeat={"run_id":"run-1","sequence":0,"source":"EXTERNAL_SYSTEMD_MONITOR"}
    first=heartbeat_contract(heartbeat=heartbeat,expected_run_id="run-1",decision=decision)
    assert first==heartbeat_contract(heartbeat=heartbeat,expected_run_id="run-1",decision=decision)
    assert first["event_id"] and first["independent_source"]=="EXTERNAL_SYSTEMD_MONITOR"
    with pytest.raises(ValueError,match="RUN_ID"):
        heartbeat_contract(heartbeat=heartbeat,expected_run_id="run-2",decision=decision)
    with pytest.raises(ValueError,match="INDEPENDENT"):
        heartbeat_contract(heartbeat={**heartbeat,"source":"GITHUB_ACTIONS_NOTIFICATION"},
                           expected_run_id="run-1",decision=decision)
