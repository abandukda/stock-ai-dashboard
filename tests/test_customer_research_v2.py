from copy import deepcopy
import ast
import json
from pathlib import Path

import pytest

from services.customer_authority import bind_report_to_customer_authority, bind_runtime_publication_identity
from services.customer_research_v2 import FactCard, build_customer_research_v2, validate_grounded_text
from services.customer_metric_format import customer_confidence, customer_money, customer_percent, customer_score
from engines.ask_atlas_engine import _compact_context
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
            "price": {**_envelope(186.09, name="price", unit="PER_SHARE"), "period": "Oct 8, 2026 close"},
            "atlas_fair_value": {**_envelope(346.05, name="atlas_fair_value", unit="PER_SHARE"), "period": "Oct 8, 2026 snapshot"},
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


def runtime_source():
    return {
        "candidate_digest": "candidate", "publication_digest": "publication",
        "analytical_source_sha": "source",
        "inventory": {"publishable_buy_now": ["NVDA", "MSFT", "AVT"]},
    }


def test_runtime_publication_identity_binds_exact_certified_bundle_authority():
    source = report()
    source.pop("candidate_digest")
    source.pop("publication_digest")
    source.pop("source_sha")

    bound = bind_runtime_publication_identity(source, runtime_source())

    identity = bound["customer_authority_identity"]
    assert identity["ticker"] == "NVDA"
    assert identity["evaluation_snapshot"] == "snapshot-nvda"
    assert identity["candidate_digest"] == "candidate"
    assert identity["publication_digest"] == "publication"
    assert identity["source_sha"] == "source"


def test_runtime_publication_identity_fails_closed_for_missing_mismatch_stale_or_withheld():
    source = report()
    source.pop("candidate_digest")
    source.pop("publication_digest")
    source.pop("source_sha")
    assert "customer_authority_identity" not in bind_runtime_publication_identity(
        source, {**runtime_source(), "publication_digest": ""}
    )

    source["customer_authority_identity"] = {
        "ticker": "NVDA", "evaluation_snapshot": "snapshot-nvda",
        "publication_digest": "stale-publication",
    }
    assert bind_runtime_publication_identity(source, runtime_source())["customer_authority_identity"][
        "publication_digest"
    ] == "stale-publication"

    withheld = report()
    withheld["certified_customer_evaluation"]["customer_publication_allowed"] = False
    assert "customer_authority_identity" not in bind_runtime_publication_identity(withheld, runtime_source())


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


def test_plain_english_views_answer_eight_questions_without_external_model_or_new_authority():
    source = report()
    source["guidance_summary"]["thesis_change_conditions"] = {
        "strengthen": ["Revenue growth remains supported."],
        "weaken": ["Margins contract materially."],
        "invalidate": ["Certified evidence deteriorates."],
    }
    views = build_customer_research_v2(source)["reading_views"]
    assert views["mode"] == "DETERMINISTIC_GROUNDED_FALLBACK"
    assert views["external_model_active"] is False
    assert views["classification"] == "CONTEXTUAL_NON_SCORING"
    assert views["evidence_ids"] == ("evidence:decision",)
    assert len(views["simple_view"]["questions"]) == 8
    assert views["simple_view"]["questions"][0] == {
        "question": "What does this company do?",
        "answer": "NVIDIA Corporation is classified in Technology. A verified plain-English business description is not available in this evidence bundle.",
    }
    assert "not a promise" in views["simple_view"]["questions"][4]["answer"]
    assert "does not change the certified recommendation" in views["simple_view"]["intro"]


def test_plain_english_views_label_stale_context_and_missing_events_honestly(monkeypatch):
    source = report()
    context = {
        "__atlas_ticker__": "NVDA",
        "__read_model__": {
            "freshness_status": "STALE_RETAINED",
            "market_identity": {"latest_completed_session": "2026-10-02"},
        },
    }
    monkeypatch.setattr("services.customer_research_v2.load_research_market_context", lambda *_args, **_kwargs: context)
    simple = build_customer_research_v2(source)["reading_views"]["simple_view"]
    assert "2026-10-02" in simple["data_notice"]
    assert "not presented as freshly acquired" in simple["data_notice"]
    assert simple["questions"][6]["answer"] == "No verified upcoming company event is available in this evidence bundle."


def test_research_renderer_exposes_simple_and_detailed_reading_levels():
    source = Path("ui/customer_research_v2.py").read_text(encoding="utf-8")
    assert '["Simple View · 2 min", "Detailed View"]' in source
    assert "External AI synthesis is not active" in source
    assert '"plain-english-summary"' in source


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
    assert set(chart["ownership"].values()) == {"NVDA"}


def test_report_and_certified_authority_ticker_mismatch_fails_closed():
    source = report()
    source["ticker"] = "AVT"
    result = build_customer_research_v2(source)
    assert result == {
        "version": "ATLAS_CUSTOMER_RESEARCH_V2_P0",
        "status": "RATING_NOT_PUBLISHED",
        "ticker": "AVT",
        "reason": "RESEARCH_AUTHORITY_TICKER_MISMATCH",
    }


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


def test_six_pillars_use_bound_customer_authority_evidence_when_wrapper_is_absent():
    source = report()
    bound = bind_report_to_customer_authority({}, source)
    assert "canonical_investment_evaluation" not in bound
    assert bound["customer_authority_identity"]["evidence_ids"] == ["evidence:decision"]

    result = build_customer_research_v2(bound)

    assert result["status"] == "AVAILABLE"
    assert result["identity"]["evaluation_snapshot"] == "snapshot-nvda"
    assert [(item["pillar"], item["certified_score"], item["weight"]) for item in result["six_pillars"]["items"]] == [
        ("fundamental_quality", 84, None), ("valuation_quality", 91, None),
    ]
    assert all(item["evidence_ids"] == ("evidence:decision",) for item in result["six_pillars"]["items"])


def test_six_pillars_prefer_wrapper_evidence_over_bound_authority_fallback():
    source = report()
    source["customer_authority_identity"] = {
        **source.get("customer_authority_identity", {}),
        "evidence_ids": ["evidence:fallback"],
    }
    result = build_customer_research_v2(source)["six_pillars"]
    assert all(item["evidence_ids"] == ("evidence:decision",) for item in result["items"])


def test_six_pillars_fail_closed_when_wrapper_and_authority_evidence_are_absent():
    source = report()
    source["canonical_investment_evaluation"]["evidence_ids"] = []
    source["customer_authority_identity"] = {
        **source.get("customer_authority_identity", {}), "evidence_ids": [],
    }
    result = build_customer_research_v2(source)["six_pillars"]
    assert result["status"] == "UNAVAILABLE"
    assert {item["reason"] for item in result["unavailable"]} == {"EVIDENCE_IDENTITY_UNAVAILABLE"}


def test_retained_certified_publication_preserves_all_six_pillars_after_authority_binding():
    rows = json.loads((Path(__file__).parents[1] / "market_full_scan.json").read_text(encoding="utf-8"))
    if isinstance(rows, dict):
        rows = rows.get("rows", [])
    by_ticker = {str(row.get("ticker") or row.get("Ticker") or "").upper(): row for row in rows}

    for ticker in ("NVDA", "MSFT", "AVT"):
        source = by_ticker[ticker]
        certified = source["certified_customer_evaluation"]
        original_decision = deepcopy(certified["decision"])
        original_snapshot = certified["digests"]["evaluation_snapshot_id"]
        original_evidence = tuple(sorted(source["canonical_investment_evaluation"]["evidence_ids"]))
        bound = bind_report_to_customer_authority({}, source)

        result = build_customer_research_v2(bound)

        assert result["status"] == "AVAILABLE"
        assert result["six_pillars"]["status"] == "AVAILABLE"
        assert len(result["six_pillars"]["items"]) == 6
        assert {item["pillar"] for item in result["six_pillars"]["items"]} == set(original_decision["six_pillars"])
        for item in result["six_pillars"]["items"]:
            original = original_decision["six_pillars"][item["pillar"]]
            assert item["certified_score"] == original["score"]
            assert item["weight"] == original["pillar_weight"]
            assert item["evidence_ids"] == tuple(sorted(original.get("evidence_ids") or original_evidence))
            assert item["snapshot_identity"] == original_snapshot
        assert bound["certified_customer_evaluation"]["decision"] == original_decision

    assert "CRC" not in by_ticker


def test_retained_cross_ticker_navigation_never_reuses_chart_or_authority_payload():
    rows = json.loads((Path(__file__).parents[1] / "market_full_scan.json").read_text(encoding="utf-8"))
    if isinstance(rows, dict):
        rows = rows.get("rows", [])
    by_ticker = {str(row.get("ticker") or row.get("Ticker") or "").upper(): row for row in rows}

    for sequence in (("NVDA", "MSFT", "AVT", "NVDA"), ("AVT", "MSFT", "AAC", "AVT")):
        prior_published = None
        for ticker in sequence:
            page = build_customer_research_v2(bind_report_to_customer_authority({}, by_ticker[ticker]))
            if ticker == "AAC":
                assert page["status"] == "RATING_NOT_PUBLISHED"
                continue
            certified = by_ticker[ticker]["certified_customer_evaluation"]
            decision = certified["decision"]
            assert page["status"] == "AVAILABLE"
            assert page["ticker"] == ticker
            assert set(page["chart"]["ownership"].values()) == {ticker}
            assert page["identity"]["evaluation_snapshot"] == certified["digests"]["evaluation_snapshot_id"]
            assert page["header"]["fair_value"] == certified["fields"]["atlas_fair_value"]["value"]
            assert {
                item["pillar"]: (item["certified_score"], item["weight"])
                for item in page["six_pillars"]["items"]
            } == {
                name: (payload["score"], payload["pillar_weight"])
                for name, payload in decision["six_pillars"].items()
            }
            if prior_published and prior_published != ticker:
                assert page["chart"]["ownership"]["chart_payload_ticker"] != prior_published
            prior_published = ticker


def test_r1_brief_uses_distinct_period_labeled_certified_facts_and_no_boilerplate():
    result = build_customer_research_v2(report())
    brief = result["summary"]
    assert tuple(brief) == (
        "verdict", "why_rating", "risks", "watch_next",
        "watch_conditions", "weakest_pillar",
    )
    assert brief["verdict"].startswith("ATLAS rates NVDA BUY NOW.")
    assert len(brief["why_rating"]) >= 2
    assert "Oct 8, 2026 close" in brief["why_rating"][0]
    assert "Oct 8, 2026 snapshot" in brief["why_rating"][1]
    assert len(set(brief["why_rating"])) == len(brief["why_rating"])
    assert all("Why ATLAS Likes It" not in value for value in brief["why_rating"])
    assert brief["weakest_pillar"] == {"name": "Fundamental Quality", "score": 84.0}


def test_brief_deduplicates_cross_category_conditions_without_inventing_copy():
    source = report()
    source["guidance_summary"] = {"thesis_change_conditions": {
        "strengthen": ["Margins expand", "Margins expand"],
        "weaken": ["Margins expand", "Revenue slows"],
        "invalidate": ["Balance-sheet evidence fails"],
    }}
    conditions = build_customer_research_v2(source)["summary"]["watch_conditions"]
    assert conditions == {
        "strengthen": ["Margins expand"],
        "weaken": ["Revenue slows"],
        "invalidate": ["Balance-sheet evidence fails"],
    }


def test_dollar_denominated_fcf_conversion_risk_fails_closed():
    source = report()
    source["intelligence"] = {"key_risks": [
        "FCF conversion is $0.72.",
        "Customer concentration remains elevated.",
    ]}
    assert build_customer_research_v2(source)["summary"]["risks"] == [
        "Customer concentration remains elevated."
    ]


def test_r1_six_pillar_frame_renders_fractional_weights_as_percent():
    frame = _six_pillar_frame(build_customer_research_v2(report())["six_pillars"])
    assert frame["Governed weight (%)"].tolist() == [60.0, 40.0]


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


def test_read_only_market_context_enriches_chart_without_changing_certified_close(monkeypatch):
    source = report(); before = deepcopy(source)
    context = {
        "__atlas_ticker__": "NVDA",
        "__read_model__": {"provider_calls": 0, "serving_request_budget": 0,
                           "rating_authority": "UNCHANGED"},
        "historical_ohlcv": {
            "payload": {
                "timestamps": list(range(1, 24)),
                "open": [190.0] * 23, "high": [195.0] * 23, "low": [185.0] * 23,
                "close": [191.0 + index / 10 for index in range(23)],
                "volume": [1000 + index for index in range(23)],
                "completed_session_flags": [True] * 23,
            },
            "provenance": {
                "provider": "FINNHUB", "raw_evidence_id": "history:evidence",
                "capture_timestamp": "2026-10-16T21:00:00Z",
                "corporate_action_adjustment_provenance": "SPLIT_ADJUSTED",
            },
            "cache_status": "STALE_RETAINED",
        },
    }
    monkeypatch.delenv("ATLAS_QA_MODE", raising=False)
    monkeypatch.setenv("ATLAS_RESEARCH_MARKET_DATA_ROOT", "/unused")
    monkeypatch.setattr("services.customer_research_v2.load_research_market_context", lambda *_args, **_kwargs: context)
    result = build_customer_research_v2(source)
    assert result["header"]["price"] == 186.09
    assert result["chart"]["status"] == "AVAILABLE"
    assert result["chart"]["freshness_status"] == "STALE_RETAINED"
    assert result["chart"]["context_classification"] == "CONTEXTUAL_NON_SCORING"
    assert result["chart"]["series"][-1]["volume"] == 1022
    assert result["market_context"]["provider_calls"] == 0
    assert result["market_context"]["rating_authority"] == "UNCHANGED"
    assert source == before


def test_research_and_ask_share_customer_wall_street_and_valuation_contract(monkeypatch, tmp_path):
    source = report()
    # These legacy fields intentionally disagree. A published customer report
    # must use the same final customer projection in both Research and Ask.
    source["valuation_families"] = {
        "atlas_valuation_status": "LEGACY_STALE",
        "atlas_fv_upside_pct": -99,
        "analyst_target_mean": 999,
        "analyst_target_low": 998,
        "analyst_target_high": 1000,
        "analyst_upside_pct": 400,
    }
    bundle = {"tickers": {"NVDA": {
        "recommendations": {"payload": {"periods": [{
            "period": "2026-10-01", "strong_buy": 10, "buy": 8,
            "hold": 3, "sell": 1, "strong_sell": 0,
        }]}, "provenance": {"raw_evidence_id": "rec:1"}},
        "price_targets": {"payload": {
            "target_low": 180, "target_mean": 240, "target_high": 300,
            "last_updated": "2026-10-08",
        }, "provenance": {"raw_evidence_id": "target:1"}},
    }}}
    path = tmp_path / "qa.json"
    path.write_text(json.dumps(bundle))
    monkeypatch.setenv("ATLAS_QA_MODE", "1")
    monkeypatch.setenv("ATLAS_RESEARCH_V2_QA_ENRICHMENT", str(path))
    monkeypatch.setenv("ATLAS_WALL_STREET_CONTEXT_ENABLED", "true")

    research = build_customer_research_v2(source)
    ask = _compact_context(source)
    assert ask["atlas_fair_value"] == research["header"]["fair_value"]
    assert ask["atlas_fv_upside_pct"] == research["header"]["fair_value_gap_pct"]
    assert ask["analyst_consensus"] == research["wall_street"]["target_average"] == 240
    assert ask["analyst_low"] == research["wall_street"]["target_low"] == 180
    assert ask["analyst_high"] == research["wall_street"]["target_high"] == 300
    assert ask["wall_street_implied_upside_pct"] is None
    assert ask["atlas_valuation_status"] == research["valuation_chart"]["status"]


def test_customer_metric_formatting_is_identical_and_presentation_only():
    assert customer_money(346.05) == "$346.05"
    assert customer_score(85.96) == "85.96"
    assert customer_percent(85.96, signed=True) == "+85.96%"
    assert customer_confidence(87.46) == "87.46/100"
    assert customer_money(None) == "Unavailable"


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
    assert "last certified close" in result["summary"]["verdict"]


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
    assert '<small>Evidence Confidence</small>' in source
    assert 'metric("Confidence", _pct' not in source
    assert '("TTM P/E", fundamentals.get("pe_ttm")' in source
    assert "_escape_markdown_currency(item)" in source
    assert "**Why the stock may be attractive**" in source
    assert "**Biggest verified risks**" in source
    assert "Strengthens the case" in source
    assert "Weakens the case" in source
    assert "General monitoring conditions — not certified invalidation triggers" in source
    assert "Weakest certified pillar" in source


def test_verified_profile_name_replaces_ticker_only_company_label(monkeypatch, tmp_path):
    source = report()
    source["company"] = "NVDA"
    bundle = {"tickers": {"NVDA": {"company_profile": {
        "payload": {"name": "NVIDIA Corp", "industry": "Semiconductors"},
        "provenance": {"raw_evidence_id": "profile:nvda"},
    }}}}
    path = tmp_path / "qa.json"; path.write_text(json.dumps(bundle))
    monkeypatch.setenv("ATLAS_QA_MODE", "1")
    monkeypatch.setenv("ATLAS_RESEARCH_V2_QA_ENRICHMENT", str(path))

    projected = build_customer_research_v2(source)

    assert projected["company"] == "NVIDIA Corp"
    assert projected["about"]["company"] == "NVIDIA Corp"


def test_retained_contract_financial_series_projects_only_registered_evidence(monkeypatch, tmp_path):
    source = report()
    bundle = {"tickers": {"NVDA": {"basic_financials": {
        "payload": {
            "series": {"annual": {
                "ebitda": [{"period": "2024-01-01", "v": 10}, {"period": "2025-01-01", "v": 20}],
                "grossMargin": [{"period": "2024-01-01", "v": .50}, {"period": "2025-01-01", "v": .55}],
                "unregistered": [{"period": "2024-01-01", "v": 999}, {"period": "2025-01-01", "v": 1000}],
            }},
            "provider_contract_series": {
                "annual.ebitda": {"status": "CERTIFIED_PROVIDER_CONTRACT", "conversion": "MULTIPLY_BY_1E6", "evidence_reference": "series:ebitda"},
                "annual.grossMargin": {"status": "CERTIFIED_PROVIDER_CONTRACT", "canonical_unit": "RATIO_DECIMAL", "evidence_reference": "series:gross-margin"},
            },
        },
        "provenance": {"raw_evidence_id": "financials:nvda"},
    }}}}
    path = tmp_path / "qa.json"; path.write_text(json.dumps(bundle))
    monkeypatch.setenv("ATLAS_QA_MODE", "1")
    monkeypatch.setenv("ATLAS_RESEARCH_V2_QA_ENRICHMENT", str(path))

    trend = build_customer_research_v2(source)["financial_trend"]

    assert trend["status"] == "AVAILABLE"
    assert trend["periods"] == ("2024-01-01", "2025-01-01")
    assert trend["series"]["EBITDA"] == (10_000_000.0, 20_000_000.0)
    assert trend["series"]["Gross Margin"] == pytest.approx((50.0, 55.0))
    assert trend["units"] == {"EBITDA": "USD", "Gross Margin": "PERCENT"}
    assert trend["periodicity"] == "ANNUAL"
    assert set(trend["provenance"]["evidence_ids"]) == {"series:ebitda", "series:gross-margin"}
    reasons = build_customer_research_v2(source)["summary"]["why_rating"]
    assert "EBITDA was $20.0M for Jan 1, 2025." in reasons
    assert "Gross Margin was 55.0% for Jan 1, 2025." in reasons


def test_premium_financial_depth_groups_only_lineage_complete_facts_and_certified_models():
    source = report()
    source.update({"net_income": 10, "operating_cash_flow": 12, "cash_and_equivalents": 8})
    source["professional_evidence_lineage"] = {"fields": {
        key: {"evidence_id": f"e:{key}", "period": "FY2025", "unit": "USD", "provider": "FINNHUB"}
        for key in ("net_income", "operating_cash_flow", "cash_and_equivalents")
    }}
    evaluation = source.setdefault("canonical_investment_evaluation", {})
    evaluation["atlas_valuation"] = {"professional_valuation_v2": {
        "model_weights": {"VAL_FORWARD_PE_V1": .6},
        "models": [
            {"methodology_id": "VAL_FORWARD_PE_V1", "name": "Forward earnings", "status": "PUBLISHED",
             "value": 346.05, "confidence": 80, "fiscal_period": "FY2026", "key_assumptions": {"forward_eps": 8}},
            {"methodology_id": "VAL_FCFF_DCF_V1", "name": "DCF", "status": "INSUFFICIENT_INPUTS", "value": None},
        ],
    }}

    depth = build_customer_research_v2(source)["financial_depth"]

    assert depth["status"] == "LIMITED"
    assert depth["statement_depth"] == "LATEST_PERIOD_ONLY"
    assert depth["statements"]["income_statement"][0]["evidence_id"] == "e:net_income"
    assert depth["statements"]["cash_flow"][0]["field"] == "operating_cash_flow"
    assert depth["statements"]["balance_sheet"][0]["field"] == "cash_and_equivalents"
    assert depth["valuation_models"] == ({
        "methodology_id": "VAL_FORWARD_PE_V1", "name": "Forward earnings", "value": 346.05,
        "unit": "USD_PER_SHARE", "fiscal_period": "FY2026", "confidence": 80, "weight": .6,
        "assumptions": {"forward_eps": 8}, "source": "CERTIFIED_ATLAS_VALUATION",
    },)
    assert depth["company_case"]["invalidation"] == ("Certified evidence deteriorates.",)
    assert "no multi-period trend is claimed" in depth["limitation"]


def test_financial_depth_renderer_preserves_lineage_and_uses_typed_unavailable_states():
    from ui.customer_research_v2 import (
        _financial_depth_status_markup, _financial_depth_status_rows, _financial_statement_rows,
    )

    rows = _financial_statement_rows(({
        "field": "net_income", "label": "Net income", "value": 1_250_000_000,
        "unit": "USD", "period": "2025-12-31", "provider": "FINNHUB",
        "evidence_id": "statement:net-income:2025",
    },))
    assert rows == [{
        "Line item": "Net income", "Certified value": "$1.25B",
        "Fiscal period": "Dec 31, 2025", "Source": "FINNHUB",
        "Evidence ID": "statement:net-income:2025",
    }]
    ui_source = __import__("pathlib").Path("ui/customer_research_v2.py").read_text(encoding="utf-8")
    assert 'data-atlas-qa="research-101"' in ui_source
    assert '"Income statement"' in ui_source
    assert '"Cash flow"' in ui_source
    assert '"Balance sheet"' in ui_source
    assert "Reporting frequency is unavailable" in ui_source
    assert "not relabeled as annual or quarterly" in ui_source
    coverage = _financial_depth_status_rows({
        "statement_depth": "LATEST_PERIOD_ONLY",
        "statements": {
            "income_statement": ({"field": "net_income", "period": "2025-12-31"},),
            "cash_flow": (), "balance_sheet": (),
        },
    })
    assert coverage == [
        {"Statement": "Income statement", "Coverage": "Available", "Certified line items": "1", "Period depth": "1 retained period"},
        {"Statement": "Cash flow", "Coverage": "Unavailable", "Certified line items": "0", "Period depth": "No retained periods"},
        {"Statement": "Balance sheet", "Coverage": "Unavailable", "Certified line items": "0", "Period depth": "No retained periods"},
    ]
    markup = _financial_depth_status_markup(coverage, ticker='A&<')
    assert markup.count('data-atlas-qa="research-v2-financial-coverage-card"') == 3
    assert 'data-atlas-ticker="A&amp;&lt;"' in markup
    assert 'data-atlas-state="unavailable"' in markup
    assert "@media(max-width:700px)" in markup


def test_financial_depth_period_counts_are_lane_specific_and_do_not_infer_depth():
    from ui.customer_research_v2 import _financial_depth_status_rows

    rows = _financial_depth_status_rows({
        "statement_depth": "MULTI_PERIOD",
        "statements": {
            "income_statement": (
                {"field": "revenue", "period": "2024-12-31"},
                {"field": "operating_income", "period": "2024-12-31"},
                {"field": "revenue", "period": "2025-12-31"},
            ),
            "cash_flow": ({"field": "free_cash_flow"},),
            "balance_sheet": (),
        },
    })

    assert [row["Period depth"] for row in rows] == [
        "2 retained periods", "Period unavailable", "No retained periods",
    ]


def test_technical_presentation_separates_price_overlays_from_rsi():
    from ui.customer_research_v2 import _technical_chart_frames
    import pandas as pd

    rows = pd.DataFrame({
        "date": pd.to_datetime(["2026-10-01", "2026-10-02"], utc=True),
        "close": [100.0, 101.0], "sma20": [98.0, 99.0], "rsi": [55.0, 57.0],
    })
    prices, oscillators = _technical_chart_frames(
        rows, date_key="date", ticker="NVDA", close_key="close",
        indicator_keys=["sma20", "rsi"],
    )

    assert list(prices.columns) == ["NVDA", "sma20"]
    assert prices.iloc[-1].to_dict() == {"NVDA": 101.0, "sma20": 99.0}
    assert list(oscillators.columns) == ["RSI (0-100)"]
    assert oscillators.iloc[-1, 0] == 57.0
    ui_source = __import__("pathlib").Path("ui/customer_research_v2.py").read_text(encoding="utf-8")
    assert 'unit="TYPED_SEPARATE_AXES"' in ui_source
    assert 'y_title="RSI (0-100)"' in ui_source
    assert 'key=f"research-technical-price-chart-{ticker}"' in ui_source


def test_untyped_trend_frequency_is_not_inferred_as_quarterly(monkeypatch, tmp_path):
    source = report()
    bundle = {"tickers": {"NVDA": {"basic_financials": {
        "payload": {
            "periods": ["2025-03-31", "2025-06-30"],
            "revenue_history": [10, 12],
        },
        "provenance": {"raw_evidence_id": "financials:nvda"},
    }}}}
    path = tmp_path / "qa.json"; path.write_text(json.dumps(bundle))
    monkeypatch.setenv("ATLAS_QA_MODE", "1")
    monkeypatch.setenv("ATLAS_RESEARCH_V2_QA_ENRICHMENT", str(path))

    trend = build_customer_research_v2(source)["financial_trend"]

    assert trend["status"] == "AVAILABLE"
    assert trend["periodicity"] == "UNAVAILABLE"


def test_snapshot_recovers_only_exact_value_matched_publication_lineage():
    source = report()
    source.update({"net_income": 10, "operating_cash_flow": 12})
    source["professional_evidence_lineage"] = {"fields": {}}
    source["publication_certification"] = {"components": {"valuation": {"lineage": {"inputs": {
        "net_income": {"canonical_value": 10, "evidence_id": "statement:1", "period": "FY2025",
                       "unit": "USD", "source": "FINNHUB", "as_of": "2026-10-04"},
        "operating_cash_flow": {"canonical_value": 999, "evidence_id": "statement:1", "period": "FY2025",
                                "unit": "USD", "source": "FINNHUB", "as_of": "2026-10-04"},
    }}}}}

    snapshot = build_customer_research_v2(source)["financial_snapshot"]

    by_field = {item["field"]: item for item in snapshot["items"]}
    assert by_field["net_income"]["evidence_id"] == "statement:1"
    assert by_field["net_income"]["provider"] == "FINNHUB"
    assert "operating_cash_flow" not in by_field


def test_research_first_screen_is_rendered_before_search_and_market_context():
    app_source = __import__("pathlib").Path("app.py").read_text(encoding="utf-8")
    route = app_source.split("def render_research_any_ticker(full_df,recovery_df,watch_df,prescreen_df,etf_df=None):", 1)[1]
    assert route.index("_research_first_screen_slot = st.empty()") < route.index('with st.form("research_ticker_form"')
    assert "Live Atlas Research" not in route.split("def ", 1)[0]
    assert 'selected_route not in {"Home", "Research Any Ticker"}' in app_source
    assert 'with st.expander("Market context", expanded=False)' in app_source


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
    assert 'y_title="Normalized performance (start = 100)"' in source
    assert 'key=f"research-price-chart-{ticker}"' in source
    assert 'key=f"research-spy-chart-{ticker}"' in source
    assert 'data-atlas-qa="research-v2-pillar-chart-row"' in source
    assert 'data-atlas-qa="research-v2-pillar-table-row"' in source
    assert "display_rows = _six_pillar_display_rows" in source
    assert 'key=f"research-valuation-chart-{ticker}"' in source
    assert '"chart-ownership", ticker' in source


def test_real_renderer_binds_certified_fair_value_to_each_ticker_chart(monkeypatch):
    """Exercise the renderer through its real chart construction boundary."""
    import ui.customer_research_v2 as renderer

    class StopAfterPriceChart(RuntimeError):
        pass

    class Column:
        def metric(self, *_args, **_kwargs):
            return None

    class Tab:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class StreamlitStub:
        session_state = {}

        @staticmethod
        def markdown(*_args, **_kwargs):
            return None

        @staticmethod
        def caption(*_args, **_kwargs):
            return None

        @staticmethod
        def write(*_args, **_kwargs):
            return None

        @staticmethod
        def columns(count):
            return [Column() for _ in range(count)]

        @staticmethod
        def tabs(labels):
            return [Tab() for _ in labels]

        @staticmethod
        def expander(*_args, **_kwargs):
            return Tab()

        @staticmethod
        def code(*_args, **_kwargs):
            return None

        @staticmethod
        def selectbox(*_args, **_kwargs):
            return "1Y"

        @staticmethod
        def info(*_args, **_kwargs):
            return None

        @staticmethod
        def warning(*_args, **_kwargs):
            return None

        @staticmethod
        def error(*_args, **_kwargs):
            return None

    monkeypatch.setattr(renderer, "st", StreamlitStub())

    cases = (("NVDA", 346.05), ("MSFT", 704.48), ("AVT", 130.97))
    for ticker, fair_value in cases:
        source = report()
        source["ticker"] = ticker
        source["company"] = f"{ticker} Company"
        source["certified_customer_evaluation"]["ticker"] = ticker
        source["certified_customer_evaluation"]["fields"]["atlas_fair_value"]["value"] = fair_value
        source["certified_customer_evaluation"]["digests"]["evaluation_snapshot_id"] = f"snapshot-{ticker.lower()}"
        source["sections"]["technical"] = {
            "history": [
                {"date": "2026-10-07", "adjusted_close": 100.0},
                {"date": "2026-10-08", "adjusted_close": 101.0},
            ],
            "history_provenance": {"source": "CERTIFIED_ARCHIVE", "evidence_ids": [f"bar:{ticker}"]},
        }
        captured = {}

        def capture_chart(frame, **kwargs):
            captured["frame"] = frame.copy()
            captured["key"] = kwargs["key"]
            raise StopAfterPriceChart

        monkeypatch.setattr(renderer, "_dark_line_chart", capture_chart)
        with __import__("pytest").raises(StopAfterPriceChart):
            renderer.render_customer_research_v2(source, ask_cta=lambda _report: None)

        assert captured["key"] == f"research-price-chart-{ticker}"
        assert list(captured["frame"].columns) == [ticker]
        assert captured["frame"][ticker].tolist() == [100.0, 101.0]


def test_customer_trust_content_contracts_are_not_presence_only():
    source = __import__("pathlib").Path("ui/customer_research_v2.py").read_text(encoding="utf-8")
    assert 'st.markdown("## Decision")' not in source
    assert 'data-atlas-qa="research-v2-risk-content"' in source
    assert "Company-specific measured risks" in source
    assert "not certified invalidation triggers" in source
    assert 'if summary["risks"] or conditions_present:' in source
    assert "_friendly_time(wall.get(\"as_of\"))" in source
    assert 'Signal date: {_friendly_time(signal.get("signal_date"))}' in source
    assert 'Signal date: {signal.get("signal_date")' not in source
    assert 'st.markdown("### Price history")' in source
    assert 'st.markdown("### Stock performance compared with SPY")' in source
    assert 'price_frame["ATLAS Fair Value"]' not in source
    assert "This security requires additional review" not in source


def test_withheld_projection_preserves_verified_identity_without_financial_values():
    source = report()
    source.update({"ticker": "CRC", "company": "California Resources Corp", "sector": "Energy"})
    source["certified_customer_evaluation"]["ticker"] = "CRC"
    source["certified_customer_evaluation"]["customer_publication_allowed"] = False
    result = build_customer_research_v2(source)
    assert result == {
        "version": result["version"],
        "status": "RATING_NOT_PUBLISHED",
        "ticker": "CRC",
        "company": "California Resources Corp",
        "sector": "Energy",
        "withheld_disposition": "RATING_NOT_PUBLISHED",
    }


def test_real_renderer_withheld_terminal_does_not_enter_chart_path(monkeypatch):
    import ui.customer_research_v2 as renderer

    class StreamlitStub:
        session_state = {}

        @staticmethod
        def markdown(*_args, **_kwargs):
            return None

    source = report()
    source["ticker"] = "CRC"
    source["certified_customer_evaluation"]["ticker"] = "CRC"
    source["certified_customer_evaluation"]["customer_publication_allowed"] = False
    monkeypatch.setattr(renderer, "st", StreamlitStub())
    monkeypatch.setattr(
        renderer,
        "_dark_line_chart",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("withheld Research rendered a chart")),
    )

    renderer.render_customer_research_v2(source, ask_cta=lambda _report: None)


def test_final_renderer_authority_marker_uses_exact_bound_snapshot_and_fails_closed(monkeypatch):
    import ui.customer_research_v2 as renderer

    captured = []

    class StreamlitStub:
        @staticmethod
        def markdown(value, **_kwargs):
            captured.append(value)

    monkeypatch.setattr(renderer, "st", StreamlitStub())
    page = build_customer_research_v2(report())
    assert renderer._render_production_authority_marker(page) is True
    marker = captured[-1]
    assert 'data-atlas-ticker="NVDA"' in marker
    assert 'data-atlas-evaluation-snapshot="snapshot-nvda"' in marker
    assert 'data-atlas-action="BUY_NOW"' in marker
    assert 'data-atlas-fair-value="346.05"' in marker

    missing = __import__("copy").deepcopy(page)
    missing["identity"]["evaluation_snapshot"] = ""
    assert renderer._render_production_authority_marker(missing) is False

    mismatched = __import__("copy").deepcopy(page)
    mismatched["identity"]["evaluation_snapshot"] = "snapshot-msft-stale"
    assert renderer._render_production_authority_marker(mismatched) is False

    wrong_ticker = __import__("copy").deepcopy(page)
    wrong_ticker["identity"]["ticker"] = "MSFT"
    assert renderer._render_production_authority_marker(wrong_ticker) is False


def test_research_renderer_has_no_reference_to_first_screen_local_header_alias():
    """Guard the exact F821 regression that escaped projection-only tests."""
    source = Path("ui/customer_research_v2.py").read_text(encoding="utf-8")
    module = ast.parse(source)
    renderer = next(
        node for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "render_customer_research_v2"
    )
    undefined_header_aliases = [
        node for node in ast.walk(renderer)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id == "h"
    ]
    assert undefined_header_aliases == []


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


def test_retained_field_level_financial_evidence_is_projected_with_exact_lineage():
    source = report()
    source.update({
        "free_cash_flow": 96_676_000_000,
        "cash_and_equivalents": 10_605_000_000,
        "total_debt": 8_468_000_000,
        "forward_eps": 9.4699146,
        "professional_evidence_as_of": "2026-10-04T21:03:54Z",
        "professional_evidence_lineage": {
            "provider": "FINNHUB",
            "fields": {
                "free_cash_flow": {"unit": "USD", "period": "2026-01-25", "provider": "FINNHUB", "evidence_id": "fin:fcf"},
                "cash_and_equivalents": {"unit": "USD", "period": "2026-01-25", "provider": "FINNHUB", "evidence_id": "fin:cash"},
                "total_debt": {"unit": "USD", "period": "2026-01-25", "provider": "FINNHUB", "evidence_id": "fin:debt"},
                "forward_eps": {"unit": "USD_PER_SHARE", "period": "2027-03-31", "provider": "FINNHUB", "evidence_id": "fin:eps", "analyst_count": 68},
            },
        },
    })

    page = build_customer_research_v2(source)
    snapshot = page["financial_snapshot"]
    assert snapshot["status"] == "AVAILABLE"
    assert [(item["field"], item["value"], item["evidence_id"]) for item in snapshot["items"]] == [
        ("free_cash_flow", 96_676_000_000.0, "fin:fcf"),
        ("cash_and_equivalents", 10_605_000_000.0, "fin:cash"),
        ("total_debt", 8_468_000_000.0, "fin:debt"),
        ("forward_eps", 9.4699146, "fin:eps"),
    ]
    assert page["summary"]["why_rating"][0] == "Free cash flow is $96.7B for Jan 25, 2026."


def test_unlined_financial_values_are_not_projected_or_used_in_brief():
    source = report()
    source["free_cash_flow"] = 999_000_000
    page = build_customer_research_v2(source)
    assert page["financial_snapshot"]["status"] == "UNAVAILABLE"
    assert all("999" not in reason for reason in page["summary"]["why_rating"])
