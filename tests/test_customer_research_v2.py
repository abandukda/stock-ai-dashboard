from copy import deepcopy

from services.customer_research_v2 import FactCard, build_customer_research_v2, validate_grounded_text


def _envelope(value, *, name, unit=None):
    return {
        "name": name, "value": value, "certification_status": "CERTIFIED",
        "source": "GOVERNED_FIXTURE", "as_of": "2026-10-08T20:00:00Z",
        "evidence_ids": [f"evidence:{name}"], "unit": unit,
    }


def report():
    certified = {
        "ticker": "NVDA", "customer_publication_allowed": True,
        "decision": {"action": "BUY_NOW", "opportunity": 85.96, "decision_confidence": 87.46},
        "fields": {
            "price": _envelope(186.09, name="price", unit="PER_SHARE"),
            "atlas_fair_value": _envelope(346.05, name="atlas_fair_value", unit="PER_SHARE"),
        },
        "digests": {"evaluation_snapshot_id": "snapshot-nvda"},
    }
    return {
        "ticker": "NVDA", "company": "NVIDIA Corporation", "sector": "Technology",
        "candidate_digest": "candidate", "publication_digest": "publication", "source_sha": "source",
        "certified_customer_evaluation": certified,
        "publication_certification": {"publication_digest": "publication", "source_sha": "source"},
        "canonical_investment_evaluation": {"evidence_ids": ["evidence:decision"]},
        "intelligence": {"why_atlas_supports_it": ["Certified valuation support."], "key_risks": ["Execution risk."]},
        "guidance_summary": {"thesis_change_conditions": {"invalidate": ["Certified evidence deteriorates."]}},
        "sections": {"technical": {"history": [], "history_provenance": {}}},
    }


def test_protected_authority_is_projected_exactly_without_recomputation(monkeypatch):
    monkeypatch.delenv("ATLAS_WALL_STREET_CONTEXT_ENABLED", raising=False)
    source = report(); before = deepcopy(source)
    result = build_customer_research_v2(source)
    assert result["status"] == "AVAILABLE"
    assert result["header"] == {
        "price": 186.09, "price_timestamp": "2026-10-08T20:00:00Z",
        "price_source": "GOVERNED_FIXTURE", "market_freshness": "CERTIFIED",
        "action": "BUY NOW", "fair_value": 346.05,
        "fair_value_gap_pct": (346.05 / 186.09 - 1) * 100,
        "opportunity": 85.96, "confidence": 87.46,
    }
    assert source == before


def test_withheld_authority_fails_closed():
    source = report()
    source["certified_customer_evaluation"]["customer_publication_allowed"] = False
    assert build_customer_research_v2(source)["status"] == "RATING_NOT_PUBLISHED"


def test_signal_performance_pending_is_never_rendered_as_zero():
    source = report()
    source["prospective_signal"] = {
        "signal_id": "sig-1", "canonical_recommendation": "BUY_NOW",
        "customer_publication_eligible_at_issuance": True,
        "first_seen_at": "2026-10-08T03:20:17Z", "reference_price": 186.09,
    }
    signal = build_customer_research_v2(source)["signal"]
    assert signal["observation_status"] == "PENDING"
    assert signal["stock_return"] is None
    assert signal["spy_return"] is None
    assert signal["excess_return"] is None


def test_chart_fails_closed_without_governed_provenance():
    assert build_customer_research_v2(report())["chart"]["status"] == "UNAVAILABLE"


def test_chart_accepts_only_persisted_rows_with_source_and_evidence():
    source = report()
    source["sections"]["technical"] = {
        "history": [{"date": "2026-10-08", "adjusted_close": 186.09}],
        "history_provenance": {"source": "CERTIFIED_ARCHIVE", "evidence_ids": ["bar:1"]},
    }
    chart = build_customer_research_v2(source)["chart"]
    assert chart["status"] == "AVAILABLE"
    assert chart["spy_comparison"]["status"] == "DISABLED"


def test_wall_street_is_disabled_by_default_and_contextual(monkeypatch):
    monkeypatch.delenv("ATLAS_WALL_STREET_CONTEXT_ENABLED", raising=False)
    module = build_customer_research_v2(report())["wall_street"]
    assert module == {
        "status": "DISABLED", "classification": "CONTEXTUAL_NON_SCORING",
        "reason": "COMMERCIAL_DISPLAY_RIGHTS_UNCONFIRMED",
    }


def test_grounded_validator_rejects_unsupported_number_causality_and_strengthening():
    fact = FactCard("Revenue growth", 83, "83%", "FY2026", "CERTIFIED", "2026-10-08", ("rev:1",), "CERTIFIED_ATLAS", "PERCENTAGE_POINTS")
    errors = validate_grounded_text(
        "NVDA is a strong buy because revenue rose 99%.", facts=[fact], ticker="NVDA", company="NVIDIA Corporation"
    )
    assert "UNSUPPORTED_NUMERIC_VALUE:99%" in errors
    assert "UNSUPPORTED_CAUSAL_LANGUAGE" in errors
    assert "PROHIBITED_ACTION_STRENGTHENING" in errors


def test_grounded_validator_accepts_supported_noncausal_language():
    fact = FactCard("Revenue growth", 83, "83%", "FY2026", "CERTIFIED", "2026-10-08", ("rev:1",), "CERTIFIED_ATLAS", "PERCENTAGE_POINTS")
    assert validate_grounded_text(
        "NVDA reported revenue growth of 83% during the governed period.",
        facts=[fact], ticker="NVDA", company="NVIDIA Corporation",
    ) == ()


def test_customer_flags_remain_off():
    flags = build_customer_research_v2(report())["feature_flags"]
    assert flags["customer_report_card"] is False
    assert flags["customer_position_management"] is False
    assert flags["trim_exit"] is False


def test_renderer_exposes_certified_header_fields_for_structured_browser_qa():
    source = __import__("pathlib").Path("ui/customer_research_v2.py").read_text(encoding="utf-8")
    assert '"stock-header", ticker' in source
    assert 'fair_value=h["fair_value"]' in source
    assert 'opportunity=h["opportunity"]' in source
    assert 'confidence=h["confidence"]' in source
