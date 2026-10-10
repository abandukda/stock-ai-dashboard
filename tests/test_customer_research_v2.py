from copy import deepcopy

from services.customer_research_v2 import FactCard, build_customer_research_v2, validate_grounded_text
from ui.customer_research_v2 import _six_pillar_frame


def _envelope(value, *, name, unit=None):
    return {
        "name": name, "value": value, "certification_status": "CERTIFIED",
        "source": "GOVERNED_FIXTURE", "as_of": "2026-10-08T20:00:00Z",
        "evidence_ids": [f"evidence:{name}"], "unit": unit,
    }


def report():
    certified = {
        "ticker": "NVDA", "customer_publication_allowed": True,
        "decision": {"action": "BUY_NOW", "opportunity": 85.96, "decision_confidence": 87.46,
                     "six_pillars": {"valuation_quality": 91, "fundamental_quality": 84}},
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
        "six_pillar_weights": {"valuation_quality": 0.6, "fundamental_quality": 0.4},
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
        "price_label": "Last Certified Close",
        "evidence_as_of": "Oct 8, 2026",
        "action": "BUY NOW", "fair_value": 346.05,
        "fair_value_gap_pct": (346.05 / 186.09 - 1) * 100,
        "opportunity": 85.96, "confidence": 87.46,
        "confidence_band": "High",
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


def test_retained_artifact_bars_require_lineage_and_never_claim_live_price():
    source = report()
    source["bars"] = [{"timestamp": 1, "close": 185.0}, {"timestamp": 2, "close": 186.09}]
    source["evidence_ids"] = ["FINNHUB:HISTORICAL_OHLCV:NVDA:abc"]
    source["run_identity"] = {"source_sha": "aa12ff9", "evidence_snapshot_at": "2026-10-04T20:00:00Z"}
    result = build_customer_research_v2(source)
    assert result["chart"]["status"] == "AVAILABLE"
    assert result["chart"]["provenance"]["contracted_endpoint"] == "/stock/candle"
    assert result["chart"]["provenance"]["raw_machine_readable_redistribution_allowed"] is False
    assert result["chart"]["corporate_action_status"] == "UNADJUSTED_CLOSE_NO_RETURN_CLAIM"
    assert result["header"]["price_label"] == "Last Certified Close"


def test_six_pillars_are_projected_without_recalculation_and_sorted_by_weight():
    result = build_customer_research_v2(report())["six_pillars"]
    assert result["status"] == "AVAILABLE"
    assert [(item["pillar"], item["certified_score"], item["weight"]) for item in result["items"]] == [
        ("valuation_quality", 91, 0.6), ("fundamental_quality", 84, 0.4),
    ]
    assert all(item["evidence_ids"] == ("evidence:decision",) for item in result["items"])


def _retained_structured_pillars():
    return {
        "entry_quality": {"score": 100, "pillar_weight": 10.0, "effective_weight": 10.0, "coverage_fraction": 1.0, "status": "AVAILABLE", "evidence_ids": []},
        "fundamental_quality": {"score": 93.0, "pillar_weight": 20.0, "effective_weight": 16.0, "coverage_fraction": 0.8, "status": "PARTIAL", "evidence_ids": ["fundamental:1"]},
        "risk_quality": {"score": 80.0, "pillar_weight": 15.0, "effective_weight": 10.5, "coverage_fraction": 0.7, "status": "PARTIAL", "evidence_ids": []},
        "technical_quality": {"score": 76.85, "pillar_weight": 25.0, "effective_weight": 25.0, "coverage_fraction": 1.0, "status": "AVAILABLE", "evidence_ids": ["technical:1"]},
        "valuation_quality": {"score": 98.32, "pillar_weight": 20.0, "effective_weight": 20.0, "coverage_fraction": 1.0, "status": "AVAILABLE", "evidence_ids": []},
        "volume_quality": {"score": 65, "pillar_weight": 10.0, "effective_weight": 10.0, "coverage_fraction": 1.0, "status": "AVAILABLE", "evidence_ids": ["volume:1"]},
    }


def test_exact_retained_structured_pillar_shape_projects_numeric_chart_contract():
    source = report()
    source["certified_customer_evaluation"]["decision"]["six_pillars"] = _retained_structured_pillars()
    before = deepcopy(source)
    result = build_customer_research_v2(source)["six_pillars"]
    assert result["status"] == "AVAILABLE"
    assert len(result["items"]) == 6
    assert result["items"][0]["pillar"] == "technical_quality"
    assert result["items"][0]["certified_score"] == 76.85
    assert result["items"][0]["score_scale"] == "0_TO_100"
    assert result["items"][0]["score_unit"] == "POINTS"
    frame = _six_pillar_frame(result)
    assert frame["Certified score"].map(lambda value: isinstance(value, float)).all()
    assert frame["Certified score"].notna().all()
    assert source == before


def test_invalid_partial_and_unavailable_pillars_never_coerce_to_zero():
    source = report()
    source["certified_customer_evaluation"]["decision"]["six_pillars"] = {
        "valid": {"score": 72.5, "pillar_weight": None, "evidence_ids": ["valid:1"]},
        "invalid_string": {"score": "81", "pillar_weight": 20, "evidence_ids": ["invalid:1"]},
        "missing": {"pillar_weight": 15, "evidence_ids": ["missing:1"]},
        "malformed": {"score": {"value": 88}, "pillar_weight": 15, "evidence_ids": ["malformed:1"]},
    }
    result = build_customer_research_v2(source)["six_pillars"]
    assert result["status"] == "PARTIAL"
    assert [(item["pillar"], item["certified_score"], item["weight"]) for item in result["items"]] == [("valid", 72.5, None)]
    assert {item["pillar"] for item in result["unavailable"]} == {"invalid_string", "missing", "malformed"}
    assert 0.0 not in _six_pillar_frame(result)["Certified score"].tolist()


def test_structured_weight_requires_explicit_weight_key_and_missing_evidence_fails_closed():
    source = report()
    source["canonical_investment_evaluation"]["evidence_ids"] = []
    source["certified_customer_evaluation"]["decision"]["six_pillars"] = {
        "valid_weight": {"score": 71, "evidence_ids": ["pillar:1"]},
        "missing_evidence": {"score": 70, "pillar_weight": 12},
    }
    source["six_pillar_weights"] = {"valid_weight": {"weight": 0.25}}
    result = build_customer_research_v2(source)["six_pillars"]
    assert result["status"] == "PARTIAL"
    assert result["items"][0]["weight"] == 0.25
    assert result["items"][0]["weight_unit"] == "FRACTION"
    assert result["unavailable"] == ({"pillar": "missing_evidence", "reason": "EVIDENCE_IDENTITY_UNAVAILABLE"},)


def test_nonpublishable_and_completely_unavailable_pillars_fail_closed():
    source = report()
    source["certified_customer_evaluation"]["decision"]["six_pillars"] = {
        "private": {"score": 88, "publication_permission": "PROHIBITED", "evidence_ids": ["private:1"]},
        "invalid": {"score": float("nan"), "evidence_ids": ["invalid:1"]},
    }
    result = build_customer_research_v2(source)["six_pillars"]
    assert result["status"] == "UNAVAILABLE"
    assert result["items"] == ()
    assert _six_pillar_frame(result).empty


def test_missing_snapshot_identity_makes_pillar_unavailable():
    source = report()
    source["certified_customer_evaluation"]["digests"].pop("evaluation_snapshot_id")
    result = build_customer_research_v2(source)["six_pillars"]
    assert result["status"] == "UNAVAILABLE"
    assert {item["reason"] for item in result["unavailable"]} == {"SNAPSHOT_IDENTITY_UNAVAILABLE"}


def test_incomplete_retained_bar_is_not_customer_projected():
    source = report()
    source["bars"] = [
        {"timestamp": "2026-10-07T20:00:00Z", "close": 185.0, "completed": True},
        {"timestamp": "2026-10-08T18:00:00Z", "close": 999.0, "completed": False},
    ]
    source["evidence_ids"] = ["FINNHUB:HISTORICAL_OHLCV:NVDA:abc"]
    source["run_identity"] = {"source_sha": "aa12ff9", "evidence_snapshot_at": "2026-10-08T18:00:00Z"}
    assert build_customer_research_v2(source)["chart"]["series"] == [source["bars"][0]]


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


def test_qa_enrichment_renders_partial_modules_without_changing_authority(monkeypatch, tmp_path):
    source = report(); before = deepcopy(source)
    def record(payload, family):
        return {"payload": payload, "provenance": {"provider": "FINNHUB", "raw_evidence_id": f"evidence:{family}", "capture_timestamp": "2026-10-09T15:00:00Z"}}
    bundle = {"tickers": {"NVDA": {
        "recommendations": record({"periods": [{"period": "2026-10-01", "strong_buy": 10, "buy": 8, "hold": 3, "sell": 1, "strong_sell": 0}]}, "recommendations"),
        "price_targets": record({"target_low": 180, "target_mean": 240, "target_high": 300, "last_updated": "2026-10-08"}, "targets"),
        "company_profile": record({"name": "NVIDIA Corporation", "industry": "Semiconductors", "country": "US"}, "profile"),
        "basic_financials": record({"revenue_growth_ttm_yoy": 83, "operating_margin_ttm": 61}, "fundamentals"),
        "company_news": record({"articles": [{"headline": "NVIDIA reports results", "article_publisher": "Issuer", "article_timestamp": 1,
                                                   "commercial_display_allowed": True, "ticker": "NVDA"}]}, "news"),
        "historical_ohlcv": record({"timestamps": [1], "close": [186.09], "completed_session_flags": [True]}, "history"),
        "spy_historical_ohlcv": record({"timestamps": [1], "close": [600], "completed_session_flags": [True]}, "spy"),
    }}}
    path = tmp_path / "qa.json"; path.write_text(__import__("json").dumps(bundle))
    monkeypatch.setenv("ATLAS_QA_MODE", "1")
    monkeypatch.setenv("ATLAS_RESEARCH_V2_QA_ENRICHMENT", str(path))
    monkeypatch.setenv("ATLAS_WALL_STREET_CONTEXT_ENABLED", "true")
    result = build_customer_research_v2(source)
    assert result["header"]["fair_value"] == 346.05
    assert result["header"]["opportunity"] == 85.96
    assert result["wall_street"]["status"] == "AVAILABLE"
    assert result["wall_street"]["analyst_count"] == 22
    assert result["chart"]["status"] == "AVAILABLE"
    assert result["chart"]["spy_comparison"]["status"] == "AVAILABLE"
    assert result["chart"]["spy_comparison"]["series"] == [{"timestamp": 1, "close": 600}]
    assert result["valuation_chart"]["status"] == "AVAILABLE"
    assert result["valuation_chart"]["unit"] == "USD_PER_SHARE"
    assert result["financial_trend"]["status"] == "UNAVAILABLE"
    assert result["about"]["status"] == "AVAILABLE"
    assert result["recent_changes"]["status"] == "AVAILABLE"
    assert source == before


def test_missing_rsi_zero_is_not_presented_as_real_risk():
    source = report()
    source["intelligence"]["key_risks"] = ["RSI is weak at 0.0.", "Execution risk."]
    result = build_customer_research_v2(source)
    assert result["summary"]["risks"] == ["Execution risk."]
    assert result["header"]["opportunity"] == 85.96
    assert result["header"]["confidence"] == 87.46


def test_news_requires_identity_publisher_timestamp_and_display_rights(monkeypatch, tmp_path):
    source = report()
    def record(payload, family):
        return {"payload": payload, "provenance": {"provider": "LICENSED", "raw_evidence_id": family}}
    bundle = {"tickers": {"NVDA": {"company_news": record({"articles": [
        {"headline": "Unrelated market story", "article_publisher": "Wire", "article_timestamp": "2026-10-09T12:00:00Z", "commercial_display_allowed": True},
        {"headline": "NVIDIA announces platform update", "article_publisher": "Wire", "article_timestamp": "2026-10-09T12:00:00Z", "commercial_display_allowed": False},
        {"headline": "NVIDIA announces governed platform update", "article_publisher": "Licensed Wire", "article_timestamp": "2026-10-09T12:00:00Z", "commercial_display_allowed": True, "ticker": "NVDA"},
    ]}, "news")}}}
    path = tmp_path / "qa.json"; path.write_text(__import__("json").dumps(bundle))
    monkeypatch.setenv("ATLAS_QA_MODE", "1")
    monkeypatch.setenv("ATLAS_RESEARCH_V2_QA_ENRICHMENT", str(path))
    items = build_customer_research_v2(source)["recent_changes"]["items"]
    assert [item["headline"] for item in items] == ["NVIDIA announces governed platform update"]
    assert items[0]["article_timestamp"] == "2026-10-09T12:00:00Z"


def test_past_earnings_events_are_not_future_catalysts(monkeypatch, tmp_path):
    source = report()
    bundle = {"tickers": {"NVDA": {"earnings_calendar": {
        "payload": {"events": [{"date": "2026-10-07"}, {"date": "2026-10-20"}]},
        "provenance": {"raw_evidence_id": "earnings:1"},
    }}}}
    path = tmp_path / "qa.json"; path.write_text(__import__("json").dumps(bundle))
    monkeypatch.setenv("ATLAS_QA_MODE", "1")
    monkeypatch.setenv("ATLAS_RESEARCH_V2_QA_ENRICHMENT", str(path))
    result = build_customer_research_v2(source)
    assert result["catalysts"]["events"] == [{"date": "2026-10-20"}]


def test_research_copy_calls_certified_price_a_close_not_live_quote():
    result = build_customer_research_v2(report())
    assert result["header"]["price_label"] == "Last Certified Close"
    assert "last certified close" in result["summary"]["bottom_line"]


def test_shared_customer_evidence_header_uses_score_not_percentage():
    result = build_customer_research_v2(report())
    assert result["header"]["confidence"] == 87.46
    assert result["header"]["confidence_band"] == "High"
    assert result["header"]["evidence_as_of"] == "Oct 8, 2026"


def test_available_balance_sheet_facts_are_used_as_risk(monkeypatch, tmp_path):
    source = report()
    bundle = {"tickers": {"NVDA": {"basic_financials": {
        "payload": {"total_debt": 2_680_000_000, "cash": 192_000_000},
        "provenance": {"raw_evidence_id": "financials:balance"},
    }}}}
    path = tmp_path / "qa.json"; path.write_text(__import__("json").dumps(bundle))
    monkeypatch.setenv("ATLAS_QA_MODE", "1")
    monkeypatch.setenv("ATLAS_RESEARCH_V2_QA_ENRICHMENT", str(path))
    risks = build_customer_research_v2(source)["summary"]["risks"]
    assert risks[0] == "Total debt is $2.68B versus cash of $192M."


def test_renderer_uses_customer_safe_labels_and_escapes_currency():
    source = __import__("pathlib").Path("ui/customer_research_v2.py").read_text(encoding="utf-8")
    assert 'metric("Evidence confidence"' in source
    assert 'metric("Confidence", _pct' not in source
    assert '("TTM P/E", fundamentals.get("pe_ttm")' in source
    assert "_escape_markdown_currency(item)" in source
    assert "**Why this rating**" in source
    assert "**What could go wrong**" in source


def test_markdown_currency_escape_preserves_governed_debt_cash_text(monkeypatch):
    from ui.customer_research_v2 import _escape_markdown_currency, _list

    rendered: list[str] = []
    monkeypatch.setattr("ui.customer_research_v2.st.markdown", rendered.append)
    risk = "Total debt is $2.68B versus cash of $192M."

    assert _escape_markdown_currency(risk) == r"Total debt is \$2.68B versus cash of \$192M."
    _list([risk])
    assert rendered == [r"- Total debt is \$2.68B versus cash of \$192M."]


def test_qa_enrichment_is_never_loaded_outside_qa(monkeypatch, tmp_path):
    path = tmp_path / "qa.json"
    path.write_text('{"tickers":{"NVDA":{"company_profile":{"payload":{"name":"Wrong"},"provenance":{"raw_evidence_id":"x"}}}}}')
    monkeypatch.delenv("ATLAS_QA_MODE", raising=False)
    monkeypatch.setenv("ATLAS_RESEARCH_V2_QA_ENRICHMENT", str(path))
    assert build_customer_research_v2(report())["about"]["status"] == "UNAVAILABLE"


def test_renderer_exposes_certified_header_fields_for_structured_browser_qa():
    source = __import__("pathlib").Path("ui/customer_research_v2.py").read_text(encoding="utf-8")
    assert '"stock-header", ticker' in source
    assert 'fair_value=h["fair_value"]' in source
    assert 'opportunity=h["opportunity"]' in source
    assert 'confidence=h["confidence"]' in source
    assert '"spy-comparison-chart"' in source
    assert '"technical-indicators-chart"' in source
    assert '"financial-trend-chart"' in source
    assert '"valuation-comparison-chart"' in source
    assert 'y_label="Normalized performance (start = 100)"' in source


def test_financial_trend_requires_periods_provenance_and_equal_length(monkeypatch, tmp_path):
    source = report()
    bundle = {"tickers": {"NVDA": {"basic_financials": {
        "payload": {
            "periods": ["FY2024", "FY2025"],
            "revenue_history": [60.9, 130.5],
            "eps_history": [1.19, 2.94],
        },
        "provenance": {"raw_evidence_id": "financials:1", "capture_timestamp": "2026-10-09T15:00:00Z"},
    }}}}
    path = tmp_path / "qa.json"; path.write_text(__import__("json").dumps(bundle))
    monkeypatch.setenv("ATLAS_QA_MODE", "1")
    monkeypatch.setenv("ATLAS_RESEARCH_V2_QA_ENRICHMENT", str(path))
    trend = build_customer_research_v2(source)["financial_trend"]
    assert trend["status"] == "AVAILABLE"
    assert trend["periods"] == ("FY2024", "FY2025")
    assert trend["series"] == {"Revenue": [60.9, 130.5], "EPS": [1.19, 2.94]}
