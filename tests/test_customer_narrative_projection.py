from pathlib import Path

from services.customer_narrative_projection import customer_narrative_projection, retained_customer_evidence


class ExactAdapter:
    provider = "test"
    model = "exact-v1"
    def __init__(self): self.calls = 0
    def summarize(self, packet):
        self.calls += 1
        fact = packet["evidence"][0]
        return {"thesis": [{"text": fact["fact"], "evidence_ids": [fact["evidence_id"]]}],
                "support": [], "risks": [], "watch_items": []}


def test_report_and_card_shapes_share_projection_and_remain_distinct():
    records = {
        "NVDA": {"ticker": "NVDA", "investment_thesis": "Accelerator demand supports growth."},
        "MSFT": {"ticker": "MSFT", "executive_summary": "Cloud demand supports recurring revenue."},
        "AVT": {"Ticker": "AVT", "certified_summary_facts": {"business_driver": "Inventory normalization supports distribution margins."}},
        "CRC": {"ticker": "CRC", "certified_summary_facts": {"primary_driver": "California production supports cash generation."}},
    }
    outputs = {ticker: customer_narrative_projection(row)["sections"]["thesis"][0]["text"] for ticker, row in records.items()}
    assert len(set(outputs.values())) == 4


def test_provider_is_not_invoked_without_both_gates(monkeypatch):
    adapter = ExactAdapter(); row = {"ticker": "NVDA", "investment_thesis": "Accelerator demand supports growth."}
    monkeypatch.delenv("ATLAS_RESEARCH_MODEL_ENABLED", raising=False)
    result = customer_narrative_projection(row, adapter=adapter, provider_authorized=True)
    assert adapter.calls == 0 and result["provider_invoked"] is False
    assert result["source"] == "DETERMINISTIC_RETAINED_EVIDENCE"


def test_cache_reuses_validated_model_projection(monkeypatch, tmp_path):
    monkeypatch.setenv("ATLAS_RESEARCH_MODEL_ENABLED", "true")
    adapter = ExactAdapter(); row = {"ticker": "MSFT", "executive_summary": "Cloud demand supports recurring revenue."}
    first = customer_narrative_projection(row, adapter=adapter, provider_authorized=True, cache_root=tmp_path)
    second = customer_narrative_projection(row, adapter=adapter, provider_authorized=True, cache_root=tmp_path)
    assert first["status"] == "AVAILABLE" and second["cache_status"] == "HIT" and adapter.calls == 1


def test_private_values_never_enter_evidence_and_empty_state_fails_closed():
    row = {"ticker": "CRC", "api_key": "sk-private", "token": "bearer-private", "Raw": {"password": "private"}}
    assert retained_customer_evidence(row) == []
    result = customer_narrative_projection(row)
    assert result["status"] == "DATA_UNAVAILABLE" and "private" not in str(result).lower()


def test_all_customer_routes_reference_shared_projection():
    root = Path(__file__).parents[1]
    for relative in ("ui/home_guidance_vnext.py", "ui/research_vnext.py", "ui/watchlist_vnext.py", "engines/ask_atlas_engine.py"):
        assert "customer_narrative_projection" in (root / relative).read_text(encoding="utf-8")
