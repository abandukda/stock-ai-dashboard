from __future__ import annotations

from dataclasses import dataclass

import pytest

from services.grounded_research_synthesis import (
    SynthesisCache, build_evidence_packet, provider_activation_status,
    synthesize_research, validate_synthesis,
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


def test_rejects_unsupported_nonnumeric_financial_prose():
    packet = build_evidence_packet("NVDA", [{"evidence_id": "ev-1", "fact": "Revenue increased."}])
    candidate = {"thesis": [{"text": "Revenue increased and margins expanded.", "evidence_ids": ["ev-1"]}],
                 "support": [], "risks": [], "watch_items": []}
    validation = validate_synthesis(candidate, packet)
    assert validation["valid"] is False
    assert "UNSUPPORTED_PROSE:thesis:0" in validation["violations"]


@pytest.mark.parametrize('candidate', [{}, {'thesis': [], 'support': [], 'risks': [], 'watch_items': []}])
def test_empty_model_response_is_not_available(candidate, monkeypatch):
    monkeypatch.setenv('ATLAS_RESEARCH_MODEL_ENABLED', 'true')
    class Empty(FakeAdapter):
        def summarize(self, packet):
            return candidate
    result = synthesize_research('NVDA', RETAINED['NVDA'], adapter=Empty(), provider_authorized=True)
    assert result['status'] == 'MODEL_SYNTHESIS_UNAVAILABLE'
    assert 'EMPTY_SYNTHESIS' in result['validation']['violations']


@pytest.mark.parametrize('citations', ['nvda-revenue', 42, {'nvda-revenue': True}, [42]])
def test_malformed_model_citations_are_rejected_without_exception(citations):
    packet = build_evidence_packet('NVDA', RETAINED['NVDA'])
    candidate = {'thesis': [{'text': RETAINED['NVDA'][0]['fact'], 'evidence_ids': citations}],
                 'support': [], 'risks': [], 'watch_items': []}
    assert not validate_synthesis(candidate, packet)['valid']


@pytest.mark.parametrize('mutation', ['text', 'ticker', 'evidence', 'status', 'sections'])
def test_cached_model_output_revalidated_without_provider_retry(tmp_path, monkeypatch, mutation):
    import json
    monkeypatch.setenv('ATLAS_RESEARCH_MODEL_ENABLED', 'true')
    adapter = FakeAdapter()
    cache = SynthesisCache(tmp_path)
    result = synthesize_research('NVDA', RETAINED['NVDA'], adapter=adapter, provider_authorized=True, cache=cache)
    path = tmp_path / (result['identity'] + '.json')
    stored = json.loads(path.read_text())
    if mutation == 'text':
        stored['sections']['thesis'][0]['text'] = 'Guaranteed profit of 999%.'
    elif mutation == 'ticker':
        stored['ticker'] = 'MSFT'
    elif mutation == 'evidence':
        stored['evidence_identity'] = '0' * 64
    elif mutation == 'status':
        stored['status'] = 'UNAVAILABLE'
    else:
        stored['sections'] = []
    stored['validation'] = {'valid': True}  # Stored flags never grant authority.
    path.write_text(json.dumps(stored))
    before = path.read_bytes()
    rejected = synthesize_research('NVDA', RETAINED['NVDA'], adapter=adapter, provider_authorized=True, cache=cache)
    assert rejected['status'] == 'MODEL_SYNTHESIS_UNAVAILABLE'
    assert rejected['reason'] == 'CACHED_MODEL_OUTPUT_REJECTED'
    assert adapter.calls == 1 and path.read_bytes() == before


def test_nonobject_cache_file_does_not_crash(tmp_path):
    (tmp_path / 'example.json').write_text('[]')
    assert SynthesisCache(tmp_path).read('example') is None


@pytest.mark.parametrize('fact,claim', [
    ('NVDA did not increase revenue.', 'NVDA did increase revenue.'),
    ('NVDA acquired ARM.', 'ARM acquired NVDA.'),
    ('Revenue rose 10% while margin fell 2%.', 'Margin rose 10% while revenue fell 2%.'),
    ('NVDA expects growth if demand improves.', 'NVDA expects growth.'),
])
def test_source_word_reuse_does_not_authorize_reversed_or_unqualified_meaning(fact, claim):
    packet = build_evidence_packet('NVDA', [{'evidence_id': 'ev', 'fact': fact}])
    candidate = {'thesis': [{'text': claim, 'evidence_ids': ['ev']}],
                 'support': [], 'risks': [], 'watch_items': []}
    result = validate_synthesis(candidate, packet)
    assert not result['valid']
    assert 'NON_EXTRACTIVE_ASSERTION:thesis:0' in result['violations']
    assert result['grounding_policy'] == 'ATLAS_RETAINED_FACT_SELECTION_V1'


def test_complete_fact_selection_allows_whitespace_without_claiming_semantic_entailment():
    packet = build_evidence_packet('NVDA', [{'evidence_id': 'ev',
        'fact': 'NVDA did not increase revenue.'}])
    candidate = {'thesis': [{'text': ' NVDA  did not\n increase revenue. ', 'evidence_ids': ['ev']}],
                 'support': [], 'risks': [], 'watch_items': []}
    result = validate_synthesis(candidate, packet)
    assert result['valid']
    assert result['assertions'][0]['text'] == 'NVDA did not increase revenue.'


def test_grounding_policy_separates_legacy_cache_and_rejects_unversioned_cached_authority(tmp_path, monkeypatch):
    import hashlib, json
    from services.grounded_research_synthesis import SCHEMA_VERSION, GROUNDING_POLICY
    monkeypatch.setenv('ATLAS_RESEARCH_MODEL_ENABLED', 'true')
    adapter = FakeAdapter()
    cache = SynthesisCache(tmp_path)
    packet = build_evidence_packet('NVDA', RETAINED['NVDA'])
    old_key = hashlib.sha256(json.dumps({'evidence': packet['evidence_identity'],
        'model': 'approved-test:grounded-v1', 'schema': SCHEMA_VERSION},
        sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()
    # No provider call is authorized, even if a legacy cache advertises authority.
    (tmp_path / (old_key + '.json')).write_text(json.dumps({'schema_version': SCHEMA_VERSION,
        'identity': old_key, 'status': 'AVAILABLE'}))
    result = synthesize_research('NVDA', RETAINED['NVDA'], adapter=adapter,
        provider_authorized=False, cache=cache)
    assert result['status'] == 'MODEL_SYNTHESIS_UNAVAILABLE' and adapter.calls == 0
    fresh = synthesize_research('NVDA', RETAINED['NVDA'], adapter=adapter,
        provider_authorized=True, cache=cache)
    assert fresh['grounding_policy'] == GROUNDING_POLICY and fresh['identity'] != old_key
    assert 'not comprehensive AI investment analysis' in fresh['analysis_scope']
    path = tmp_path / (fresh['identity'] + '.json')
    corrupted = json.loads(path.read_text())
    corrupted.pop('grounding_policy')
    path.write_text(json.dumps(corrupted))
    before = path.read_bytes()
    result = synthesize_research('NVDA', RETAINED['NVDA'], adapter=adapter,
        provider_authorized=True, cache=cache)
    assert result['reason'] == 'CACHED_MODEL_OUTPUT_REJECTED'
    assert path.read_bytes() == before and adapter.calls == 1


def test_cached_word_reordering_cannot_restore_model_authority(tmp_path, monkeypatch):
    import json
    monkeypatch.setenv('ATLAS_RESEARCH_MODEL_ENABLED', 'true')
    evidence = [{'evidence_id': 'acquisition', 'fact': 'NVDA acquired ARM.'}]
    adapter = FakeAdapter()
    cache = SynthesisCache(tmp_path)
    first = synthesize_research('NVDA', evidence, adapter=adapter, provider_authorized=True, cache=cache)
    path = tmp_path / (first['identity'] + '.json')
    value = json.loads(path.read_text())
    value['sections']['thesis'][0]['text'] = 'ARM acquired NVDA.'
    value['validation'] = {'valid': True}
    path.write_text(json.dumps(value))
    before = path.read_bytes()
    result = synthesize_research('NVDA', evidence, adapter=adapter, provider_authorized=True, cache=cache)
    assert result['reason'] == 'CACHED_MODEL_OUTPUT_REJECTED'
    assert result['status'] == 'MODEL_SYNTHESIS_UNAVAILABLE'
    assert adapter.calls == 1 and path.read_bytes() == before
