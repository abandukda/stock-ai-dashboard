
from adapters.institutional_adapter_v2 import (
    normalize_institutional_data,
)
from adapters.political_adapter_v2 import (
    normalize_political_data,
)
from adapters.research_data_adapter_v2 import (
    enrich_supporting_research_data,
)
from agents.supporting_data_audit_v2 import (
    audit_supporting_data,
)
from core.pipeline_v104 import build_v104_pipeline
from engines.atlas_research_builder_v2 import (
    build_atlas_research_v2,
)


def rich_row():
    return {
        "Ticker": "INTU",
        "Company": "Intuit",
        "Sector": "Technology",
        "Price": 650,
        "Analyst Target": 720,
        "Final Conviction": 75,
        "Technical Score": 74,
        "Finance Agent Score": 82,
        "Analyst Support Score": 80,
        "heldPercentInstitutions": 0.86,
        "institutional_ownership_change": 1.5,
        "topInstitutionalHolders": [
            {
                "name": "Fund A",
                "shares": 1000000,
                "percentage": 0.08,
            }
        ],
        "congressional_trades": [
            {
                "representative": "Sample Member",
                "transactionType": "Purchase",
                "transactionDate": "2026-07-01",
                "amountRange": "$15,001–$50,000",
            }
        ],
        "political_source": "Test political provider",
    }


def test_institutional_normalization():
    data = normalize_institutional_data(rich_row())
    assert data["status"] == "available"
    assert data["institutional_ownership_pct"] == 86.0
    assert data["institutional_score"] is not None
    assert len(data["major_holders"]) == 1


def test_political_normalization():
    data = normalize_political_data(rich_row())
    assert data["status"] == "available"
    assert data["retrieval_status"] == "scanner_payload"
    assert data["buyers"] == 1
    assert len(data["transactions"]) == 1


def test_enrichment_places_scores_before_scoring():
    data = enrich_supporting_research_data(rich_row())
    assert data["institutional_score"] is not None
    assert data["political_score"] is not None
    assert data["ownership"]["institutional_ownership_pct"] == 86.0


def test_pipeline_preserves_supporting_sections():
    result = build_v104_pipeline([rich_row()])
    row = result["ranked_candidates"][0]
    assert row["components"]["institutional"] is not None
    assert row["components"]["political"] is not None
    assert row["ownership"]["status"] == "available"
    assert row["political"]["status"] == "available"


def test_v2_builder_uses_normalized_sections():
    report = build_atlas_research_v2(rich_row())
    assert report["sections"]["ownership"]["status"] == "available"
    assert report["sections"]["political"]["status"] == "available"


def test_audit_distinguishes_not_loaded():
    result = audit_supporting_data({"Ticker": "EMPTY"})
    diagnoses = {
        item["diagnosis"]
        for item in result["findings"]
    }
    assert "not_loaded_or_unmapped" in diagnoses
    assert "not_loaded" in diagnoses
