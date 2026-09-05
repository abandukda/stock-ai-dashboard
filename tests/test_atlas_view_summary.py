from services.atlas_view_summary import (
    _valuation_comparison, audit_summary_differentiation, build_summary_payload,
    generate_summaries, validate_summary,
)


def test_summary_service_supports_streamlit_secret_key_without_changing_secrets():
    import inspect
    import services.atlas_view_summary as summary

    source = inspect.getsource(summary._openai_key)
    assert 'st.secrets.get("OPENAI_API_KEY", "")' in source


def _card():
    return {
        "ticker": "NVDA", "company": "NVIDIA", "production_rank": 2, "scan_conviction": 97,
        "display_price": 229.5, "display_price_label": "Last-known Price",
        "market_evidence": {"market_session": "AFTER_HOURS", "status": "LAST_KNOWN", "provider_timestamp": "2026-09-04T23:59:00+00:00"},
        "technical_state": "NEAR_BREAKOUT", "technical_status": "AVAILABLE",
        "technical_evidence": {"sma20": 220, "sma50": 210, "sma200": 190, "rsi": 54.9},
        "entry_relationship": "WITHIN_ENTRY_RANGE", "trade_plan": {"entry_low": 228.45, "entry_high": 234.16},
        "recovery": {"score": 69, "state": "Recovery Watchlist"},
        "volume_evidence": {"relative_volume": .45}, "volume_status": "DATA_UNAVAILABLE",
        "completed_bar_quality": {"status": "AVAILABLE"},
        "fundamentals_status": "AVAILABLE", "risk_status": "AVAILABLE",
        "guidance": "WAIT_FOR_CONFIRMATION", "actionability": "NOT_ACTIONABLE",
        "reason_codes": ("NEAR_BREAKOUT_NOT_CONFIRMED",),
        "what_changes_guidance": ("Approved confirmation evidence",),
    }


def test_validated_llm_summary_accepts_only_structured_facts():
    payload = build_summary_payload(_card())
    text = "NVDA has a technical setup approaching breakout and remains near the preferred entry zone. The price structure could improve if the breakout confirms. Participation is still too weak for confirmation, so ATLAS rates it WAIT FOR CONFIRMATION."
    result = generate_summaries([payload], llm=lambda _: [text])[0]
    assert result["accepted"] is True
    assert result["source"] == "LLM_VALIDATED"
    assert result["text"] == text


def test_raw_recovery_or_rvol_recitation_is_rejected():
    payload = build_summary_payload(_card())
    validation = validate_summary("NVDA has a Recovery Score of 69 and 0.45× contextual volume.", payload)
    assert validation["valid"] is False
    assert "RAW_DASHBOARD_METRIC_RECITATION" in validation["violations"]


def test_unsourced_number_or_guidance_is_rejected_to_ticker_fallback():
    payload = build_summary_payload(_card())
    invented = "NVDA has 88% upside and should buy now. Guidance is BUY NOW."
    validation = validate_summary(invented, payload)
    assert validation["valid"] is False
    result = generate_summaries([payload], llm=lambda _: [invented])[0]
    assert result["accepted"] is False
    assert result["source"] == "DETERMINISTIC_FALLBACK"
    assert "NVIDIA" in result["text"] and "WAIT FOR CONFIRMATION" in result["text"]


def test_missing_llm_uses_deterministic_ticker_specific_fallback():
    result = generate_summaries([build_summary_payload(_card())], llm=lambda _: None)[0]
    assert result["source"] == "DETERMINISTIC_FALLBACK"
    assert "market-setup thesis" in result["text"]
    assert "Recovery Score" not in result["text"]
    assert "0.45×" not in result["text"]
    assert "WAIT FOR CONFIRMATION" in result["text"]


def test_dossier_carries_approved_company_earnings_valuation_and_risk_lanes():
    card = _card()
    card.update({
        "fundamentals_evidence": {"revenue": 10_000, "revenue_growth": .2, "free_cash_flow": 500},
        "company_evidence": {
            "business_summary": "NVIDIA designs accelerated computing platforms.",
            "latest_earnings_date": "2026-08-01", "reported_eps": 1.2, "eps_estimate": 1.0,
            "eps_surprise_pct": 20, "forward_eps": 5.0, "estimate_revision": "UP",
            "primary_risk": "Demand could slow.",
        },
        "atlas_valuation_status": "PUBLISHED", "atlas_fair_value": 250, "atlas_expected_return": 8.9,
        "valuation_driver_evidence": {"method": "Growth-adjusted forward earnings multiple", "growth_input_pct": 20, "justified_pe": 24},
        "wall_street": {"commercial_display_status": "COMMERCIAL_LICENSE_UNCONFIRMED"},
    })
    payload = build_summary_payload(card)
    assert payload["latest_earnings"]["reported_eps"] == 1.2
    assert payload["forward_outlook"]["estimate_revision"] == "UP"
    assert payload["atlas_valuation"]["target"] == 250
    assert payload["atlas_valuation"]["driver_evidence"]["justified_pe"] == 24
    assert payload["valuation_comparison"]["state"] == "WALL_STREET_UNAVAILABLE"
    assert payload["risk_evidence"]["strongest_fundamental_risk"] == "Demand could slow."
    assert "growth-adjusted forward earnings framework" in generate_summaries([payload], llm=lambda _: None)[0]["text"]


def test_fallback_changes_with_company_specific_evidence():
    first = _card()
    first["company_evidence"] = {"business_summary": "NVIDIA designs accelerated computing platforms."}
    second = {**_card(), "ticker": "BALL", "company": "Ball Corporation"}
    second["company_evidence"] = {"business_summary": "Ball supplies aluminum packaging to beverage producers."}
    texts = [generate_summaries([build_summary_payload(card)], llm=lambda _: None)[0]["text"] for card in (first, second)]
    assert texts[0] != texts[1]
    assert "accelerated computing" in texts[0]
    assert "aluminum packaging" in texts[1]


def test_unlicensed_wall_street_claim_is_rejected():
    payload = build_summary_payload(_card())
    text = "NVDA has a constructive market setup. Wall Street analysts expect material upside. ATLAS rates it WAIT FOR CONFIRMATION while confirmation develops."
    validation = validate_summary(text, payload)
    assert "UNSUPPORTED_ANALYST_CLAIM" in validation["violations"]


def test_duplication_audit_flags_name_only_rewrites():
    payloads = [build_summary_payload(_card()), build_summary_payload({**_card(), "ticker": "AMD", "company": "AMD"})]
    results = [
        {"text": "NVDA has a constructive setup. Its evidence needs confirmation. ATLAS rates it WAIT."},
        {"text": "AMD has a constructive setup. Its evidence needs confirmation. ATLAS rates it WAIT."},
    ]
    audit = audit_summary_differentiation(payloads, results)
    assert audit["passed"] is False
    assert audit["flagged_pairs"][0]["left"] == "NVDA"


def test_trade_target_cannot_be_substituted_for_atlas_fair_value():
    card = _card()
    card.update({"atlas_valuation_status": "PUBLISHED", "atlas_fair_value": 250, "atlas_expected_return": 8.9})
    payload = build_summary_payload(card)
    text = "NVDA has a constructive setup. Its earnings evidence supports the case. The ATLAS target is $120, so ATLAS rates it WAIT FOR CONFIRMATION."
    validation = validate_summary(text, payload)
    assert "TARGET_SUBSTITUTION" in validation["violations"]


def test_target_divergence_uses_governed_fifteen_percent_boundary():
    base = _card()
    base.update({
        "atlas_valuation_status": "PUBLISHED", "atlas_fair_value": 115,
        "wall_street": {"mean_target": 100, "display_scope": "INTERNAL_TRIAL"},
    })
    assert _valuation_comparison(base)["state"] == "ALIGNED"
    assert _valuation_comparison({**base, "atlas_fair_value": 115.01})["state"] == "ATLAS_MORE_BULLISH"
    assert _valuation_comparison({**base, "atlas_fair_value": 84.99})["state"] == "WALL_STREET_MORE_BULLISH"
    assert _valuation_comparison(base)["target_gap_pct"] == 15.0


def test_summary_dossier_carries_all_six_locked_pillars():
    card = _card()
    card["evaluation"] = {
        "decision_metrics_methodology": "ATLAS_DECISION_METRICS_V1",
        "component_coverage": 95.5, "opportunity": 72.4, "decision_confidence": 87.2,
        **{key: {"status": "AVAILABLE", "score": score, "evidence_ids": (key,)} for key, score in (
            ("technical_quality", 70), ("fundamental_quality", 60), ("valuation_quality", 80),
            ("risk_quality", 75), ("entry_quality", 100), ("volume_quality", 50),
        )},
    }
    payload = build_summary_payload(card)
    assert payload["decision_metrics_methodology"] == "ATLAS_DECISION_METRICS_V1"
    assert tuple(payload["six_pillars"]) == (
        "technical_quality", "fundamental_quality", "valuation_quality",
        "risk_quality", "entry_quality", "volume_quality",
    )
    assert payload["component_coverage"] == 95.5
