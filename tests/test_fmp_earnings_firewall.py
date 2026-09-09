from services.evidence_lineage_governance import (
    fmp_quantitative_lineage_paths, provider_lineage_counters,
)
from services.fmp_earnings_evidence import validate_earnings_evidence
from services.publication_governance import build_manifest


def test_fmp_is_rejected_from_quantitative_lineage():
    payload = {"valuation": {"revenue_source": "FMP_INCOME_STATEMENT"}}
    assert fmp_quantitative_lineage_paths(payload) == ["$.valuation.revenue_source"]
    assert provider_lineage_counters(payload)["PUBLISHED_FMP_QUANTITATIVE_LINEAGE_COUNT"] == 1


def test_fmp_is_allowed_only_inside_earnings_context():
    payload = validate_earnings_evidence({
        "provider": "FMP", "summary": "Management discussed demand.",
        "revenue": 100, "eps": 2.0,
    })
    assert not fmp_quantitative_lineage_paths(payload)
    assert "revenue" not in payload["earnings_evidence"]
    counters = provider_lineage_counters(payload)
    assert counters["PUBLISHED_FMP_QUANTITATIVE_LINEAGE_COUNT"] == 0
    assert counters["FMP_EARNINGS_CONTEXT_REFERENCE_COUNT"] > 0


def test_optional_earnings_context_cannot_change_decision_fields():
    row = {"action": "BUY_NOW", "opportunity": 81, "decision_confidence": 84}
    row.update(validate_earnings_evidence({"provider": "FMP", "summary": "Optional context"}))
    assert (row["action"], row["opportunity"], row["decision_confidence"]) == ("BUY_NOW", 81, 84)


def test_publication_fails_on_fmp_quantitative_lineage_but_allows_earnings_context():
    certification = {"certification_state": "CERTIFIED", "customer_publication_allowed": True}
    bad = {"ticker": "BAD", "publication_certification": certification, "revenue_source": "FMP"}
    manifest = build_manifest([bad], run_id="test", generated_at="now", artifact_payloads={})
    assert manifest["publication_gate_status"] == "FAIL"
    assert manifest["PUBLISHED_FMP_QUANTITATIVE_LINEAGE_COUNT"] == 1
    good = {"ticker": "GOOD", "publication_certification": certification,
            **validate_earnings_evidence({"provider": "FMP", "summary": "Context"})}
    manifest = build_manifest([good], run_id="test", generated_at="now", artifact_payloads={})
    assert manifest["PUBLISHED_FMP_QUANTITATIVE_LINEAGE_COUNT"] == 0
