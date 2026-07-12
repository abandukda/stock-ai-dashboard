from engines.discovery_engine import select_deep_research_candidates
from engines.monitoring_engine import material_changes


def test_discovery_selects_highest_conviction():
    rows = [{"Ticker": "A", "conviction": 60}, {"Ticker": "B", "conviction": 90}]
    assert select_deep_research_candidates(rows, 1)[0]["Ticker"] == "B"


def test_monitoring_detects_fair_value_change():
    changes = material_changes({"atlas_fair_value": 100}, {"atlas_fair_value": 115})
    assert any("Fair Value" in item for item in changes)
