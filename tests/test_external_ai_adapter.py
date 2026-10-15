import json

from services.external_ai_adapter import ExternalAIConfig, activation_preflight, configuration, invoke_grounded_json, sanitize_payload


def _config(**updates):
    values = dict(provider="openai", model="named-test-model", enabled=True,
                  privacy_approved=True, billing_approved=True, provider_access_verified=True,
                  timeout_seconds=3.5,
                  max_input_bytes=1_000, max_output_tokens=77,
                  max_requests_per_generation=2, max_generation_cost_microusd=30_000)
    values.update(updates)
    return ExternalAIConfig(**values)


def _valid(text):
    return {"valid": "contradiction" not in text, "violations": [] if "contradiction" not in text else ["CONTRADICTION"]}


def test_both_activation_gates_and_named_provider_model_are_required():
    calls = []
    transport = lambda **kwargs: calls.append(kwargs) or '{"summary":"ok"}'
    for config in (
        _config(enabled=False), _config(privacy_approved=False), _config(billing_approved=False),
        _config(provider_access_verified=False),
        _config(provider=""), _config(model=""), _config(provider="unknown"),
    ):
        result = invoke_grounded_json(payload={"ticker": "NVDA"}, system_prompt="grounded",
                                      fallback={"summary": "fallback"}, validator=_valid,
                                      transport=transport, config=config)
        assert result["status"] == "DETERMINISTIC_FALLBACK"
        assert result["reason"] == "ACTIVATION_GATES_CLOSED"
    assert calls == []


def test_credential_or_legacy_model_setting_alone_cannot_activate(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "present-but-insufficient")
    monkeypatch.setenv("ATLAS_LLM_MODEL", "legacy-implicit-model")
    for name in ("ATLAS_EXTERNAL_AI_ENABLED", "ATLAS_EXTERNAL_AI_PRIVACY_APPROVED",
                 "ATLAS_EXTERNAL_AI_PROVIDER", "ATLAS_EXTERNAL_AI_MODEL"):
        monkeypatch.delenv(name, raising=False)
    config = configuration()
    assert config.active is False
    assert config.provider == "" and config.model == ""


def test_privacy_redaction_happens_before_transport():
    captured = {}
    def transport(**kwargs):
        captured.update(kwargs)
        return '{"summary":"grounded"}'
    result = invoke_grounded_json(
        payload={"ticker": "NVDA", "api_key": "never-send", "analyst_email": "a@example.com",
                 "note": "Bearer top-secret"}, system_prompt="grounded", fallback={},
        validator=_valid, transport=transport, config=_config(),
    )
    sent = json.loads(captured["payload_json"])
    assert "api_key" not in sent and "analyst_email" not in sent
    assert sent["note"] == "[REDACTED_AUTHORIZATION]"
    assert result["redaction_count"] == 3


def test_input_budget_fails_closed_without_calling_transport():
    calls = []
    result = invoke_grounded_json(payload={"text": "x" * 500}, system_prompt="grounded",
                                  fallback="safe", validator=_valid,
                                  transport=lambda **kwargs: calls.append(kwargs),
                                  config=_config(max_input_bytes=20))
    assert result["reason"] == "INPUT_BUDGET_EXCEEDED"
    assert result["value"] == "safe"
    assert calls == []


def test_named_model_latency_and_output_budget_reach_transport():
    captured = {}
    result = invoke_grounded_json(
        payload={"ticker": "AVT"}, system_prompt="facts only", fallback="fallback",
        validator=_valid, transport=lambda **kwargs: captured.update(kwargs) or "grounded",
        config=_config(),
    )
    assert result["status"] == "EXTERNAL_AI_VALIDATED"
    assert captured["provider"] == "openai"
    assert captured["model"] == "named-test-model"
    assert captured["timeout_seconds"] == 3.5
    assert captured["max_output_tokens"] == 77
    assert result["budget"]["max_requests_per_generation"] == 2
    assert result["budget"]["max_generation_cost_microusd"] == 30_000


def test_provider_free_preflight_never_infers_billing_or_model_availability(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "configured-but-never-returned")
    result = activation_preflight(_config())
    assert result["provider_calls"] == 0
    assert result["checks"]["credential_configured"] is True
    assert result["provider_account"]["credential_validity"] == "UNVERIFIED_NO_PROVIDER_CALL"
    assert result["provider_account"]["model_availability"] == "UNVERIFIED_NO_PROVIDER_CALL"
    assert result["provider_account"]["billing_status"] == "OWNER_OR_PROVIDER_ATTESTATION_REQUIRED"
    assert "configured-but-never-returned" not in json.dumps(result)


def test_secret_and_all_other_gates_cannot_replace_provider_access_verification(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "configured")
    config = _config(provider_access_verified=False)
    assert config.active is False
    result = activation_preflight(config)
    assert result["checks"]["provider_access_verified"] is False
    assert result["ready_for_live_inference"] is False


def test_cost_or_resource_ceiling_above_approved_bound_fails_preflight(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "present")
    result = activation_preflight(_config(max_generation_cost_microusd=60_001))
    assert result["ready_for_live_inference"] is False
    assert result["checks"]["generation_cost_limit_bounded"] is False


def test_grounding_or_contradiction_failure_uses_deterministic_fallback():
    result = invoke_grounded_json(
        payload={"ticker": "NVDA"}, system_prompt="facts only", fallback="deterministic",
        validator=_valid, transport=lambda **kwargs: "contradiction",
        config=_config(),
    )
    assert result["status"] == "DETERMINISTIC_FALLBACK"
    assert result["reason"] == "GROUNDING_OR_CONTRADICTION_FAILURE"
    assert result["value"] == "deterministic"
    assert result["validation"]["violations"] == ["CONTRADICTION"]


def test_transport_error_never_escapes_or_replaces_fallback():
    def broken(**kwargs):
        raise TimeoutError("do not expose provider detail")
    result = invoke_grounded_json(payload={}, system_prompt="facts only", fallback={"safe": True},
                                  validator=_valid, transport=broken, config=_config())
    assert result["status"] == "DETERMINISTIC_FALLBACK"
    assert result["reason"] == "TIMEOUTERROR"
    assert result["value"] == {"safe": True}


def test_sanitizer_is_recursive_and_preserves_non_private_evidence():
    clean, count = sanitize_payload({"evidence": [{"id": "ev-1", "session_token": "bad"}],
                                     "market_session": "CLOSED",
                                     "company": "Example"})
    assert clean == {"evidence": [{"id": "ev-1"}], "market_session": "CLOSED", "company": "Example"}
    assert count == 1


def test_r3_summary_generation_enforces_total_request_budget(monkeypatch):
    import services.atlas_view_summary as summary
    monkeypatch.setattr(summary, "external_ai_configuration", lambda: _config(max_requests_per_generation=2))
    monkeypatch.setattr(summary, "invoke_grounded_json", lambda **kwargs: (_ for _ in ()).throw(AssertionError("must not call")))
    assert summary._default_llm([{"ticker": f"T{i}"} for i in range(11)]) is None
