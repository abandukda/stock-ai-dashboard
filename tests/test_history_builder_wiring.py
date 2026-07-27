
from engines.atlas_research_builder_v2 import build_atlas_research_v2


def test_existing_history_reaches_technical_section():
    row = {
        "ticker": "TEST",
        "company": "Test",
        "sector": "Technology",
        "current_price": 100,
        "price_history": [
            {
                "date": "2026-07-01",
                "close": 100,
                "volume": 1000,
            }
        ],
        "history_provenance": {
            "status": "AVAILABLE",
            "records_found": 1,
            "source": "Test",
        },
        "components": {
            "fundamentals": 70,
            "valuation": 70,
            "technical": 70,
            "analyst": 70,
            "risk": 70,
        },
        "component_coverage_pct": 80,
        "freshness_score": 80,
    }

    report = build_atlas_research_v2(row)
    technical = report["sections"]["technical"]
    assert len(technical["history"]) == 1
    assert technical["history_provenance"]["status"] == "AVAILABLE"
