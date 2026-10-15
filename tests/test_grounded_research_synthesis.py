from __future__ import annotations

from dataclasses import dataclass

import pytest

from services.grounded_research_synthesis import (
    SynthesisCache, provider_activation_status, synthesize_research,
)


RETAINED = {
    "NVDA": [
        {"evidence_id": "nvda-revenue", "family": "financials", "fact": "NVDA revenue grew 122% in the retained annual period.", "as_of": "2025-01-26"},
        {"evidence_id": "nvda-risk", "family": "risk", "fact": "NVDA reported customer concentration as a retained risk.", "as_of": "2025-01-26"},
    ],
    "MSFT": [
        {"evidence_id": "msft-cloud", "family": "segments", "fact": "MSFT Azure revenue grew 33% in the retained quarter.", "as_of": "2025-06-30"},
        {"evidence_id": "msft-capex", "family": "risk", "fact": "MSFT capital expenditure was $24.2 billion in the retained quarter.", "as_of": "2025-06-30"},
    ],
    "AVT": [
        {"evidence_id": "avt-sales", "family": "financials", "fact": "AVT sales declined 12% in the retained fiscal year.", "as_of": "2025-06-28"},
        {"evidence_id": "avt-cash", "family": "cash_flow", "fact": "AVT generated $487 million of retained operating cash flow.", "as_of": "2025-06-28"},
    ],
    "CRC": [
        {"evidence_id": "crc-production", "family": "operations", "fact": "CRC retained production was 136 thousand barrels of oil equivalent per day.", "as_of": "2025-12-31"},
        {"evidence_id": "crc-risk", "family": "risk", "fact": "CRC identified commodity prices as a retained risk.", "as_of": "2025-12-31"},
    ],
}


@dataclass
class FakeAdapter:
    provider: str = "approved-test"
    model: str = "grounded-v1"
    calls: int = 0

    def summarize(self, packet):
        self.calls += 1
        first = packet["evidence"][0]
        return {
            "thesis": [{"text": first["fact"], "evidence_ids": [first["evidence_id"]]}],
            "support": [], "risks": [], "watch_items": [],
        }


@pytest.mark.parametrize("ticker", ["NVDA", "MSFT", "AVT", "CRC"])
def test_distinct_retained_evidence_has_distinct_identity_and_fallback(ticker, monkeypatch):
    monkeypatch.delenv("ATLAS_RESEARCH_MODEL_ENABLED", raising=False)
    result = synthesize_research(ticker, RETAINED[ticker])
    assert result["ticker"] == ticker
    assert result["status"] == "MODEL_SYNTHESIS_UNAVAILABLE"
    assert {item["text"] for item in result["sections"]["thesis"]} == {
        item["fact"] for item in RETAINED[ticker]
    }


def test_adapter_is_never_called_without_both_activation_gates(monkeypatch):
    adapter = FakeAdapter()
    monkeypatch.setenv("ATLAS_RESEARCH_MODEL_ENABLED", "true")
    synthesize_research("NVDA", RETAINED["NVDA"], adapter=adapter, provider_authorized=False)
    monkeypatch.setenv("ATLAS_RESEARCH_MODEL_ENABLED", "false")
    synthesize_research("NVDA", RETAINED["NVDA"], adapter=adapter, provider_authorized=True)
    assert adapter.calls == 0


def test_activation_status_discloses_no_secret_and_bounds_cost(monkeypatch):
    monkeypatch.setenv("ATLAS_RESEARCH_MODEL_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "not-returned")
    status = provider_activation_status()
    assert status["ready_for_authorized_call"] is True
    assert status["max_output_tokens_per_cache_miss"] == 900
    assert status["automatic_retries"] == 0
    assert "not-returned" not in repr(status)


def test_valid_grounded_model_result_is_cached_by_evidence_and_model_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_RESEARCH_MODEL_ENABLED", "true")
    adapter = FakeAdapter()
    cache = SynthesisCache(tmp_path)
    first = synthesize_research("MSFT", RETAINED["MSFT"], adapter=adapter, provider_authorized=True, cache=cache)
    second = synthesize_research("MSFT", list(reversed(RETAINED["MSFT"])), adapter=adapter, provider_authorized=True, cache=cache)
    assert first["status"] == "AVAILABLE" and first["cache_status"] == "MISS"
    assert second["cache_status"] == "HIT" and adapter.calls == 1


def test_unknown_citation_and_hallucinated_number_fail_closed(monkeypatch):
    monkeypatch.setenv("ATLAS_RESEARCH_MODEL_ENABLED", "true")

    class Bad(FakeAdapter):
        def summarize(self, packet):
            self.calls += 1
            return {"thesis": [{"text": "NVDA revenue grew 999%.", "evidence_ids": ["nvda-revenue"]}],
                    "support": [{"text": "Unsupported claim.", "evidence_ids": ["missing"]}],
                    "risks": [], "watch_items": []}

    result = synthesize_research("NVDA", RETAINED["NVDA"], adapter=Bad(), provider_authorized=True)
    assert result["status"] == "MODEL_SYNTHESIS_UNAVAILABLE"
    assert result["reason"] == "MODEL_OUTPUT_REJECTED"
    assert set(result["validation"]["violations"]) >= {"UNSUPPORTED_NUMBER:thesis:0", "UNKNOWN_EVIDENCE:support:0"}


def test_contradictory_directional_claims_fail_closed(monkeypatch):
    monkeypatch.setenv("ATLAS_RESEARCH_MODEL_ENABLED", "true")

    class Contradictory(FakeAdapter):
        def summarize(self, packet):
            return {"thesis": [{"text": "AVT sales declined 12%.", "evidence_ids": ["avt-sales"]}],
                    "support": [{"text": "AVT sales grew 12%.", "evidence_ids": ["avt-sales"]}],
                    "risks": [], "watch_items": []}

    result = synthesize_research("AVT", RETAINED["AVT"], adapter=Contradictory(), provider_authorized=True)
    assert "CONTRADICTORY_ASSERTIONS" in result["validation"]["violations"]


def test_evidence_identity_rejects_duplicate_or_missing_ids():
    bad = [{"evidence_id": "same", "fact": "One."}, {"evidence_id": "same", "fact": "Two."}]
    with pytest.raises(ValueError, match="RETAINED_EVIDENCE_ID_AND_FACT_REQUIRED"):
        synthesize_research("NVDA", bad)
