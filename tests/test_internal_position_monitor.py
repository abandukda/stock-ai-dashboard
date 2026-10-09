from pathlib import Path

import pytest

from services.position_management_dashboard import build_shadow_position_dashboard
from services.position_management_ledgers import ShadowPositionLedger


ACTIVATION = "2026-10-08T20:00:00+00:00"
SCAN = "2026-10-08T21:00:00+00:00"


def payload(signal_id="signal-1", ticker="NVDA"):
    return {
        "signal_id": signal_id, "ticker": ticker, "scan_timestamp": SCAN,
        "methodology_version": "ATLAS_POSITION_MANAGEMENT_SHADOW_V1",
        "candidate_digest": "candidate", "publication_digest": "publication",
        "evaluation_snapshot": "snapshot", "source_sha": "source", "thesis_state": "INTACT",
        "valuation_state": "FAIR", "technical_state": "HEALTHY", "data_certainty": "CERTIFIED",
        "position_instruction": "HOLD", "add_eligible": True, "review_required": False,
        "review_reason_codes": [], "reason_codes": ["THESIS_INTACT", "VALUATION_FAIR"],
        "price": 100.0, "certified_fair_value": 110.0, "valuation_confidence": 80.0,
        "fair_value_band": {"lower": 90, "base": 110, "upper": 125}, "inputs_digest": "inputs",
        "rule_table_version": "ATLAS_POSITION_RULE_TABLE_V1", "customer_visible": False,
    }


def test_dashboard_is_authorized_read_only_and_internal(tmp_path):
    ledger = ShadowPositionLedger(tmp_path / "shadow.sqlite3", activation_timestamp=ACTIVATION)
    ledger.append_evaluation(payload())
    before = ledger.path.read_bytes()
    with pytest.raises(PermissionError, match="INTERNAL_POSITION_MONITOR_ACCESS_REQUIRED"):
        build_shadow_position_dashboard(ledger.path, authorized=False)
    report = build_shadow_position_dashboard(ledger.path, authorized=True)
    assert report["classification"] == "INTERNAL_SHADOW_POSITION_MONITOR"
    assert report["customer_visible"] is False
    assert report["integrity"] == "PASS"
    assert report["positions"][0]["position_instruction"] == "HOLD"
    assert ledger.path.read_bytes() == before


def test_signal_digest_integration_is_descriptive_only():
    source = Path("ui/internal_position_monitor.py").read_text(encoding="utf-8")
    function = source[source.index("def render_signal_shadow_context"):]
    assert "thesis_state" in function and "valuation_state" in function and "technical_state" in function
    assert 'position_instruction' not in function
    assert "NOT CUSTOMER VISIBLE" in source


def test_customer_report_card_visibility_remains_off():
    source = Path("ui/internal_report_card.py").read_text(encoding="utf-8")
    assert 'data-atlas-customer-visible="false"' in source
    assert "render_shadow_position_monitor" in source
