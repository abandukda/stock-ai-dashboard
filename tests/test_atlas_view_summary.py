from services.atlas_view_summary import build_summary_payload, generate_summaries, validate_summary


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
    text = "NVDA has a technical setup approaching breakout and remains near the preferred entry zone. Participation is still too weak for confirmation, so ATLAS rates it WAIT FOR CONFIRMATION."
    result = generate_summaries([payload], llm=lambda _: [text])[0]
    assert result["accepted"] is True
    assert result["source"] == "VALIDATED_LLM"
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
    assert "NVDA" in result["text"] and "WAIT FOR CONFIRMATION" in result["text"]


def test_missing_llm_uses_deterministic_ticker_specific_fallback():
    result = generate_summaries([build_summary_payload(_card())], llm=lambda _: None)[0]
    assert result["source"] == "DETERMINISTIC_FALLBACK"
    assert "may outperform if" in result["text"]
    assert "Recovery Score" not in result["text"]
    assert "0.45×" not in result["text"]
    assert "WAIT FOR CONFIRMATION" in result["text"]
