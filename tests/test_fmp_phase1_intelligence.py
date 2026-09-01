from __future__ import annotations

from datetime import datetime, timezone
import json

from engines.fmp_normalization import (
    normalize_insider_transaction,
    normalize_price_target_action,
    normalize_transcript_content,
)
from engines.research_context import build_research_context
from engines.transcript_intelligence import derive_transcript_intelligence
from services.analyst_estimate_snapshot_store import (
    ACCUMULATION_MESSAGE,
    append_daily_snapshots,
    normalize_estimate_snapshots,
    revision_summary,
)
from services.fmp_phase1_intelligence import load_cached_phase1_families
from services.fmp_phase1_intelligence import (
    acquire_latest_transcript_intelligence,
    acquire_transcript_index,
    acquire_transcript_intelligence,
    refresh_post_shell_evidence,
)
from services.fmp_stable_client import FMPResponse, SUCCESS
from services.research_family_cache import cache_path, load_family_envelope, save_family_envelope


def test_transcript_normalization_requires_exact_period_and_derived_output_excludes_raw_text():
    raw = {"symbol": "MSFT", "year": 2026, "quarter": 4, "date": "2026-07-29", "content": "Revenue growth remained strong. We expect demand to expand next quarter. Risk remains execution pressure."}
    normalized = normalize_transcript_content(raw, requested_year=2026, requested_quarter=4)
    assert normalized["semantic_status"] == "AVAILABLE"
    assert normalize_transcript_content(raw, requested_year=2025, requested_quarter=4)["semantic_status"] == "DATA_UNAVAILABLE"
    derived = derive_transcript_intelligence(normalized, evidence_id="ev_test")
    assert derived["semantic_status"] == "AVAILABLE"
    assert "content" not in derived
    assert any("demand" in item.lower() for item in derived["management_themes"])


def test_price_target_does_not_infer_prior_target():
    row = normalize_price_target_action({"symbol": "NVDA", "publishedDate": "2026-08-29", "priceTarget": 200, "analystCompany": "Firm"})
    assert row["price_target"] == 200
    assert row["prior_target_status"] == "PRIOR_TARGET_NOT_PROVEN"
    assert "prior_target" not in row


def test_insider_normalizer_preserves_zero_and_negative_values_and_is_context_only():
    row = normalize_insider_transaction({
        "symbol": "AAPL", "transactionDate": "2026-08-01", "filingDate": "2026-08-02",
        "securitiesTransacted": 0, "price": -1, "securitiesOwned": 0,
    })
    assert (row["shares"], row["price"], row["post_transaction_holdings"]) == (0.0, -1.0, 0.0)
    assert row["context_authority"] == "CONTEXT_ONLY"
    assert "transaction_value" not in row


def test_transcript_cache_is_immutable(tmp_path):
    content = {"fetched_at": datetime.now(timezone.utc).isoformat(), "transcript": {"content": "restricted"}}
    save_family_envelope("MSFT", "transcript_content", content, root=tmp_path, period_key="2026-Q4")
    try:
        save_family_envelope("MSFT", "transcript_content", content, root=tmp_path, period_key="2026-Q4")
        assert False, "immutable content overwrite must fail"
    except FileExistsError:
        pass
    derived = {"fetched_at": datetime.now(timezone.utc).isoformat(), "semantic_status": "AVAILABLE", "data": {"management_themes": []}}
    save_family_envelope("MSFT", "transcript_intelligence", derived, root=tmp_path, period_key="2026-Q4-ev-v1")
    try:
        save_family_envelope("MSFT", "transcript_intelligence", derived, root=tmp_path, period_key="2026-Q4-ev-v1")
        assert False, "immutable derived overwrite must fail"
    except FileExistsError:
        pass


def test_daily_estimate_snapshot_is_idempotent_and_same_period_only(tmp_path):
    rows = [{"date": "2027-06-30", "epsLow": 10, "epsHigh": 12, "epsAvg": 11, "numAnalystsEps": 20}]
    day1 = normalize_estimate_snapshots("MSFT", rows, observed_at="2026-09-01T00:00:00Z")
    assert append_daily_snapshots("MSFT", day1, root=tmp_path)["added"] == 2
    assert append_daily_snapshots("MSFT", day1, root=tmp_path)["added"] == 0
    assert revision_summary("MSFT", root=tmp_path)["status_detail"] == ACCUMULATION_MESSAGE
    rows[0]["epsAvg"] = 11.5
    day2 = normalize_estimate_snapshots("MSFT", rows, observed_at="2026-09-02T00:00:00Z")
    append_daily_snapshots("MSFT", day2, root=tmp_path)
    comparison = revision_summary("MSFT", root=tmp_path)["comparisons"][0]
    assert comparison["estimate_period"] == "2027-06-30"
    assert comparison["prior_average"] == 11.0 and comparison["current_average"] == 11.5


def test_ordinary_cache_load_has_no_provider_client_and_etf_is_not_applicable(tmp_path):
    families = load_cached_phase1_families("SPY", security_type="ETF", cache_root=tmp_path)
    assert families["transcript_intelligence"]["semantic_status"] == "NOT_APPLICABLE"
    assert families["insider_transactions"]["semantic_status"] == "NOT_APPLICABLE"


def test_new_corporate_families_are_not_applicable_for_etf_context():
    context = build_research_context(ticker="SPY", production_row={"ticker": "SPY", "security_type": "ETF"}, evidence_families={})
    for family in ("transcript_intelligence", "analyst_price_target_actions", "insider_transactions", "analyst_estimate_snapshots"):
        assert context["evidence_families"][family]["semantic_status"] == "NOT_APPLICABLE"


def test_workflow_persists_snapshot_cache_without_adding_it_to_production_commit():
    workflow = open(".github/workflows/overnight_scan.yml", encoding="utf-8").read()
    assert ".atlas_research_cache/analyst_estimate_snapshots_v1" in workflow
    commit_line = next(line for line in workflow.splitlines() if "git add --" in line)
    assert "analyst_estimate" not in commit_line
    assert "market_full_scan.json" in commit_line


class _FakeClient:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def get(self, family, params):
        self.calls.append((family, dict(params)))
        return FMPResponse(self.payloads[family], SUCCESS, family, "2026-09-01T12:00:00+00:00", 200, 1)


def test_post_shell_target_and_insider_refresh_has_separate_two_call_ceiling(tmp_path):
    client = _FakeClient({
        "price-target-news": [{"symbol": "MSFT", "publishedDate": "2026-08-29", "priceTarget": 600}],
        "insider-trading/search": [{"symbol": "MSFT", "transactionDate": "2026-08-20", "filingDate": "2026-08-21", "securitiesTransacted": 0}],
    })
    result = refresh_post_shell_evidence("MSFT", api_key="unused", cache_root=tmp_path, client=client)
    assert result["provider_calls"] == 2
    assert [item[0] for item in client.calls] == ["price-target-news", "insider-trading/search"]


def test_explicit_transcript_request_uses_returned_period_and_warm_repeat_uses_zero_calls(tmp_path):
    client = _FakeClient({
        "earning-call-transcript-dates": [{"symbol": "MSFT", "year": 2026, "quarter": 4, "date": "2026-07-29"}],
        "earning-call-transcript": [{"symbol": "MSFT", "year": 2026, "quarter": 4, "date": "2026-07-29", "content": "Revenue demand strengthened materially. We expect product adoption growth next quarter. Execution risk remains."}],
    })
    first = acquire_latest_transcript_intelligence("MSFT", api_key="unused", cache_root=tmp_path, client=client)
    assert first["provider_calls"] == 2
    assert client.calls[-1][1]["year"] == 2026 and client.calls[-1][1]["quarter"] == 4
    warm_client = _FakeClient({})
    second = acquire_latest_transcript_intelligence("MSFT", api_key="unused", cache_root=tmp_path, client=warm_client)
    assert second["provider_calls"] == 0 and warm_client.calls == []
    assert second["operation_metadata"] == {
        "ticker": "MSFT", "selected_year": 2026, "selected_quarter": 4,
        "transcript_evidence_id": second["family"]["evidence_ids"][0],
        "cache_status": "CACHE_HIT", "provider_call_count": 0,
        "synthesis_version": "TRANSCRIPT_SYNTHESIS_V1",
    }


def test_index_exposes_multiple_periods_and_explicit_historical_load_is_exact_and_cached(tmp_path):
    client = _FakeClient({
        "earning-call-transcript-dates": [
            {"symbol": "NVDA", "year": 2026, "quarter": 4, "date": "2026-08-20"},
            {"symbol": "NVDA", "year": 2026, "quarter": 3, "date": "2026-05-20"},
        ],
        "earning-call-transcript": [{
            "symbol": "NVDA", "year": 2026, "quarter": 3, "date": "2026-05-20",
            "content": "Management emphasized product demand growth. Execution risk remains. We expect adoption to expand next quarter.",
        }],
    })
    index = acquire_transcript_index("NVDA", api_key="unused", cache_root=tmp_path, client=client)
    assert [(p["fiscal_year"], p["fiscal_quarter"]) for p in index["family"]["data"]["periods"]] == [(2026, 4), (2026, 3)]
    result = acquire_transcript_intelligence(
        "NVDA", year=2026, quarter=3, api_key="unused", cache_root=tmp_path,
        client=client, _index_result=index,
    )
    assert client.calls[-1] == ("earning-call-transcript", {"symbol": "NVDA", "year": 2026, "quarter": 3})
    assert result["period"] == "2026-Q3" and result["provider_calls"] == 2
    assert result["family"]["evidence_ids"]
    assert "content" not in json.dumps(result["family"])
    warm = acquire_transcript_intelligence(
        "NVDA", year=2026, quarter=3, api_key="unused", cache_root=tmp_path,
        client=_FakeClient({}),
    )
    assert warm["provider_calls"] == 0
    assert warm["operation_metadata"]["cache_status"] == "CACHE_HIT"


def test_missing_indexed_historical_transcript_has_explicit_unavailable_state(tmp_path):
    client = _FakeClient({
        "earning-call-transcript-dates": [{"symbol": "MSFT", "year": 2025, "quarter": 2, "date": "2025-04-30"}],
        "earning-call-transcript": [],
    })
    result = acquire_transcript_intelligence(
        "MSFT", year=2025, quarter=2, api_key="unused", cache_root=tmp_path, client=client,
    )
    assert result["family"]["semantic_status"] == "DATA_UNAVAILABLE"
    assert result["family"]["limitations"] == ["Transcript commentary unavailable for this quarter."]
    assert result["operation_metadata"]["cache_status"] == "UNAVAILABLE"


def test_research_and_earnings_ui_destinations_are_present():
    research = open("ui/research_vnext.py", encoding="utf-8").read()
    earnings = open("ui/earnings_vnext.py", encoding="utf-8").read()
    assert "Management / Transcript Insight" in research
    assert "Refresh analyst targets & insider evidence" in research
    assert "Individual price-target actions" in earnings
    assert "Insider transactions · contextual only" in earnings
    assert "Previous earnings calls" in research
    assert "What management emphasized" in earnings
    assert "Load earnings-call insight" in earnings
    limitation = "Prior target was not provided by the source, so ATLAS does not calculate an individual target change."
    assert limitation in research and limitation in earnings
    assert "data-atlas-transcript-provider-calls" in research
    assert "data-atlas-transcript-provider-calls" in earnings


def test_phase1_is_absent_from_explicit_research_critical_path_and_perf_contract_unchanged():
    acquisition = open("services/fmp_research_acquisition.py", encoding="utf-8").read()
    for endpoint in ("earning-call-transcript", "price-target-news", "insider-trading/search"):
        assert endpoint not in acquisition
    assert "EXPLICIT_RESEARCH_DEADLINE_SECONDS = 28.0" in acquisition
    assert "24" in acquisition


def test_transcript_derived_claims_are_traceable_and_no_raw_body_is_in_ui_or_workflow():
    derived = derive_transcript_intelligence(
        {"content": "Management expects demand growth next quarter and identifies execution risk pressure.", "year": 2026, "quarter": 4},
        evidence_id="ev_traceable",
    )
    assert derived["source_evidence_ids"] == ["ev_traceable"]
    for path in ("ui/research_vnext.py", "ui/earnings_vnext.py", ".github/workflows/overnight_scan.yml"):
        source = open(path, encoding="utf-8").read()
        assert "transcript[\"content\"]" not in source
        assert "transcript.get(\"content\")" not in source
