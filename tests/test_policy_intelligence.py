from __future__ import annotations

from datetime import date
import inspect

import pytest
from engines.ask_atlas_engine import ask_atlas
from engines.policy_intelligence import (
    build_policy_intelligence, deduplicate_evidence, normalize_evidence,
    relevance_status,
)
from services.policy_data import USAspendingClient, enrich_policy_for_research
from services import ai_synthesis
from ui import home_v104, research_report_v2
import overnight_market_scan


TODAY = date(2026, 8, 15)


def _evidence(**updates):
    item = {
        "domain": "REGULATORY", "fact": "Agency issued a company-specific final rule.",
        "why_it_matters": "The rule changes the company's compliance obligations.",
        "direction": "HEADWIND", "event_date": "2026-08-01",
        "authority": "Federal Agency", "document_id": "RULE-1",
        "company_match": "DIRECT_VERIFIED_EXPOSURE", "match_confidence": "HIGH",
        "materiality": "HIGH",
    }
    item.update(updates)
    return item


def test_missing_and_numeric_score_only_remain_insufficient():
    assert build_policy_intelligence({}, today=TODAY)["policy_overall_status"] == "INSUFFICIENT_VERIFIED_EVIDENCE"
    model = build_policy_intelligence({"political_score": 99}, today=TODAY)
    assert model["policy_overall_status"] == "INSUFFICIENT_VERIFIED_EVIDENCE"
    assert model["evidence_count"] == 0


def test_deterministic_tailwind_headwind_and_mixed_classification():
    tail = _evidence(direction="TAILWIND", document_id="A")
    risk = _evidence(direction="HEADWIND", document_id="B")
    assert build_policy_intelligence({"policy_evidence": [tail]}, today=TODAY)["policy_overall_status"] == "POLICY_TAILWIND"
    assert build_policy_intelligence({"policy_evidence": [risk]}, today=TODAY)["policy_overall_status"] == "POLICY_HEADWIND"
    assert build_policy_intelligence({"policy_evidence": [tail, risk]}, today=TODAY)["policy_overall_status"] == "MIXED_POLICY_EXPOSURE"
    assert build_policy_intelligence({"policy_evidence": [_evidence(direction="MIXED")]}, today=TODAY)["policy_overall_status"] == "MIXED_POLICY_EXPOSURE"


def test_sector_context_cannot_create_company_classification():
    item = _evidence(company_match="GENERAL_SECTOR_CONTEXT", direction="HEADWIND")
    model = build_policy_intelligence({"policy_evidence": [item]}, today=TODAY)
    assert model["policy_overall_status"] == "INSUFFICIENT_VERIFIED_EVIDENCE"
    assert model["evidence_count"] == 1
    assert model["classification_evidence_count"] == 0


def test_regulatory_tariff_export_and_sanctions_domains_stay_isolated():
    items = [
        _evidence(domain="REGULATORY", document_id="R"),
        _evidence(domain="TRADE_TARIFF", document_id="T"),
        _evidence(domain="EXPORT_CONTROL_SANCTIONS", document_id="E"),
    ]
    model = build_policy_intelligence({"policy_evidence": items}, today=TODAY)
    assert len(model["regulatory_evidence"]) == 1
    assert len(model["trade_tariff_evidence"]) == 1
    assert len(model["export_control_evidence"]) == 1


def test_existing_exposure_requires_authority_before_classification():
    unverified = build_policy_intelligence({"regulatory_exposure": "Company faces a named rule."}, today=TODAY)
    assert unverified["evidence_count"] == 1
    assert unverified["policy_overall_status"] == "INSUFFICIENT_VERIFIED_EVIDENCE"
    verified = build_policy_intelligence({
        "regulatory_exposure": "Company faces a named rule.",
        "policy_authority": "Federal Trade Commission",
    }, today=TODAY)
    assert verified["policy_overall_status"] == "LIMITED_MATERIAL_EXPOSURE"


def test_existing_company_news_requires_entity_match_source_and_date():
    good = {"headline": "Company receives federal contract", "publisher": "U.S. Department of Defense", "date": "2026-08-01", "relevance": "Accepted company/ticker match"}
    bad = {"headline": "Sector receives federal contract", "publisher": "Newswire", "date": "2026-08-01"}
    model = build_policy_intelligence({"news": [good, bad]}, today=TODAY)
    assert len(model["policy_news"]) == 1
    assert model["policy_overall_status"] == "POLICY_TAILWIND"


def test_lobbying_never_implies_policy_support():
    lobbying = _evidence(domain="LOBBYING", direction="TAILWIND", document_id="LD2", lobbying_amount=100000)
    model = build_policy_intelligence({"lobbying_evidence": [lobbying]}, today=TODAY)
    assert model["policy_overall_status"] == "INSUFFICIENT_VERIFIED_EVIDENCE"
    assert model["material_policy_tailwinds"] == []


@pytest.mark.parametrize(("event", "end", "active", "expected"), [
    ("2026-08-01", None, None, "CURRENT"),
    ("2026-06-01", None, None, "RECENT"),
    ("2025-01-01", "2027-01-01", True, "ONGOING"),
    ("2025-01-01", "2026-01-01", True, "HISTORICAL"),
    (None, None, None, "UNKNOWN"),
])
def test_recency_logic(event, end, active, expected):
    item = {"domain": "GOVERNMENT_CONTRACT", "event_date": event, "period_of_performance_end": end, "is_active": active}
    assert relevance_status(item, today=TODAY) == expected


def test_active_contract_remains_ongoing_beyond_90_days():
    item = normalize_evidence(_evidence(
        domain="GOVERNMENT_CONTRACT", event_date="2025-01-01",
        period_of_performance_end="2027-12-31", document_id="AWARD-1",
    ), today=TODAY)
    assert item["relevance_status"] == "ONGOING"


def test_duplicate_action_prefers_authoritative_record_and_preserves_identity():
    article = _evidence(authority="News Publisher", document_id="AWARD-1", materiality="MEDIUM")
    authority = _evidence(authority="U.S. Department of Defense", document_id="AWARD-1", materiality="HIGH")
    result = deduplicate_evidence([article, authority], today=TODAY)
    assert len(result) == 1
    assert result[0]["authority"] == "U.S. Department of Defense"
    assert result[0]["document_id"] == "AWARD-1"


def test_contract_modifications_with_same_award_id_are_one_evidence_record():
    original = _evidence(
        domain="GOVERNMENT_CONTRACT", document_id="AWARD-2",
        award_action="AWARD", authority="USAspending.gov", event_date="2026-07-01",
    )
    modification = _evidence(
        domain="GOVERNMENT_CONTRACT", document_id="AWARD-2",
        award_action="MODIFICATION", authority="Department of Defense", event_date="2026-08-01",
    )
    result = deduplicate_evidence([original, modification], today=TODAY)
    assert len(result) == 1
    assert result[0]["authority"] == "Department of Defense"


class _Response:
    def __init__(self, payload): self.payload = payload
    def raise_for_status(self): return None
    def json(self): return self.payload


def _requester(method, url, json, timeout):
    if url.endswith("/autocomplete/recipient/"):
        return _Response({"results": [{"recipient_name": "Exact Company Inc", "uei": "UEI1"}]})
    return _Response({"results": [{
        "Award ID": "A1", "Recipient Name": "Exact Company Inc",
        "Award Amount": 1000, "Total Obligated Amount": 250,
        "Awarding Agency": "Department of Defense", "Awarding Sub Agency": "Navy",
        "Start Date": "2025-01-01", "End Date": "2027-01-01",
        "Description": "Prime research contract", "Award Type": "Definitive Contract",
    }]})


def test_usaspending_exact_entity_award_semantics_and_cache(tmp_path):
    client = USAspendingClient(requester=_requester, cache_dir=tmp_path)
    first = client.fetch_contract_evidence("EXACT", "Exact Company Inc")
    item = first["government_contract_evidence"][0]
    assert first["metrics"]["provider_call_count"] == 2
    assert item["company_match"] == "DIRECT_ENTITY"
    assert item["award_type"] == "PRIME"
    assert item["award_ceiling"] == 1000
    assert item["obligated_amount"] == 250
    assert item["awarding_agency"] == "Department of Defense"
    assert item["awarding_subagency"] == "Navy"
    assert item["document_id"] == "A1"
    assert "not recognized revenue" in item["why_it_matters"]
    second = client.fetch_contract_evidence("EXACT", "Exact Company Inc")
    assert second["metrics"]["award_cache_hit"] is True
    assert second["metrics"]["provider_call_count"] == 0
    assert second["metrics"]["provider_seconds"] == 0.0


def test_usaspending_requests_prime_awards_not_subawards(tmp_path):
    payloads = []
    def requester(method, url, json, timeout):
        payloads.append(json)
        return _requester(method, url, json, timeout)
    USAspendingClient(requester=requester, cache_dir=tmp_path).fetch_contract_evidence("EXACT", "Exact Company Inc")
    award_request = payloads[1]
    assert award_request["subawards"] is False
    assert award_request["filters"]["award_type_codes"] == ["A", "B", "C", "D"]


def test_uncertain_or_substring_entity_match_fails_closed(tmp_path):
    def requester(method, url, json, timeout):
        return _Response({"results": [{"recipient_name": "Exact Company Holdings"}]})
    result = USAspendingClient(requester=requester, cache_dir=tmp_path).fetch_contract_evidence("EX", "Exact Company Inc")
    assert result["government_contract_evidence"] == []
    assert result["metrics"]["entity_match_status"] == "UNCERTAIN_FAIL_CLOSED"


def test_verified_subsidiary_must_be_explicit_and_remains_labeled(tmp_path):
    client = USAspendingClient(requester=_requester, cache_dir=tmp_path)
    result = enrich_policy_for_research("EXACT", {
        "company": "Parent Corporation",
        "verified_government_recipient_name": "Exact Company Inc",
    }, client=client)
    assert result["government_contract_evidence"][0]["company_match"] == "VERIFIED_SUBSIDIARY"


def test_usaspending_timeout_is_failure_safe(tmp_path):
    def requester(*args, **kwargs): raise TimeoutError()
    result = USAspendingClient(requester=requester, cache_dir=tmp_path).fetch_contract_evidence("EX", "Exact Company Inc")
    assert result["government_contract_evidence"] == []
    assert result["metrics"]["timeout_count"] == 1


def test_cache_write_failure_cannot_break_research(monkeypatch, tmp_path):
    monkeypatch.setattr("services.policy_data._save", lambda *args, **kwargs: False)
    result = USAspendingClient(requester=_requester, cache_dir=tmp_path).fetch_contract_evidence("EXACT", "Exact Company Inc")
    assert result["government_contract_evidence"][0]["document_id"] == "A1"


def test_usaspending_failure_cannot_break_full_research(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("provider unavailable")
    monkeypatch.setattr(research_report_v2, "enrich_policy_for_research", fail)
    result = research_report_v2._load_policy_enrichment("TEST", {"company": "Test Inc"})
    assert result["government_contract_evidence"] == []
    assert result["metrics"]["failure_count"] == 1


def test_explicit_research_entrypoint_only_and_no_scanner_or_home_import():
    assert "_load_policy_enrichment" in inspect.getsource(research_report_v2.render_atlas_research_v2)
    assert "enrich_policy_for_research" in inspect.getsource(research_report_v2._load_policy_enrichment)
    assert "policy_data" not in inspect.getsource(overnight_market_scan)
    assert "policy_data" not in inspect.getsource(home_v104)


def test_ask_atlas_policy_is_deterministic_and_cannot_invent_or_infer_partisanship():
    report = {"ticker": "TEST", "policy_intelligence": build_policy_intelligence({}, today=TODAY), "sections": {}}
    result = ask_atlas("Does government policy help this company?", report)
    assert result["mode"] == "deterministic_policy_grounding"
    assert "enough verified company-specific policy evidence" in result["answer"]
    assert "political affiliation" in result["answer"]


def test_ai_policy_prompt_forbids_cross_labeling_and_invention():
    prompt = ai_synthesis._llm_prompt("What policy risks exist?", {"policy_intelligence": {}})[0]["content"]
    assert "only the supplied normalized policy_intelligence object" in prompt
    assert "Never invent a contract" in prompt
    assert "Never treat an award ceiling as revenue" in prompt
    assert "partisan alignment" in prompt


def test_customer_policy_renderer_hides_backend_plumbing():
    source = inspect.getsource(research_report_v2._render_policy_intelligence)
    assert "provider" not in source.lower()
    assert "API" not in source
    assert "What happened" in source
    assert "Why it matters" in source
