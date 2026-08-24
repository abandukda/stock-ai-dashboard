from datetime import datetime
from pathlib import Path
import tempfile
import time
from unittest.mock import patch

from services.fmp_research_acquisition import (
    EXPLICIT_RESEARCH_DEADLINE_SECONDS, FAMILY_PRIORITY,
    acquire_explicit_fmp_research,
)
from services.fmp_stable_client import DEADLINE_EXPIRED, FMPStableClient
from tests.test_fmp_first_research_acquisition import FakeFMP, NOW, production_row


ROOT = Path(__file__).resolve().parents[1]


class SlowFMP(FakeFMP):
    def get(self, endpoint_family, params=None, **kwargs):
        time.sleep(0.18)
        return super().get(endpoint_family, params, **kwargs)


class TimeoutSession:
    def __init__(self):
        self.calls = []

    def get(self, _url, *, params, timeout):
        self.calls.append(timeout)
        time.sleep(min(timeout, 0.02))
        from requests import Timeout
        raise Timeout()


def test_deadline_is_below_qa_budget_and_priority_is_deterministic():
    assert EXPLICIT_RESEARCH_DEADLINE_SECONDS == 28.0
    assert EXPLICIT_RESEARCH_DEADLINE_SECONDS < 45
    assert FAMILY_PRIORITY[0] == "profile"
    assert FAMILY_PRIORITY[-2:] == ("company_news", "press_releases")


def test_cold_and_warm_cache_request_contract(tmp_path):
    fixed = datetime.fromisoformat(NOW).timestamp()
    with patch("services.research_family_cache.time.time", return_value=fixed):
        cold = acquire_explicit_fmp_research("NVDA", production_row=production_row(), client=FakeFMP(), cache_root=tmp_path)
        warm = acquire_explicit_fmp_research("NVDA", production_row=production_row(), client=FakeFMP(), cache_root=tmp_path)
    assert cold["diagnostics"]["requests"] == 18
    assert warm["diagnostics"]["requests"] == 0
    assert warm["diagnostics"]["fresh_cache_hits"] == 12


def test_deadline_stops_new_requests_and_preserves_completed_families(tmp_path):
    checkpoints = []
    result = acquire_explicit_fmp_research(
        "NVDA", production_row=production_row(), client=SlowFMP(), cache_root=tmp_path,
        deadline_seconds=1.0, research_request_id="NVDA-request-1",
        progress_callback=lambda value: checkpoints.append(dict(value)),
    )
    diagnostics = result["diagnostics"]
    assert diagnostics["requests"] < 18
    assert diagnostics["deadline_expired"] is True
    assert diagnostics["enrichment_status"] == "ENRICHMENT_PARTIAL"
    assert checkpoints
    assert any(item.get("last_completed_stage", "").startswith("normalized:") for item in checkpoints)
    assert result["research_context"]["production_decision"]["recommendation"] == "BUY NOW"


def test_retry_is_suppressed_when_deadline_budget_is_exhausted():
    session = TimeoutSession()
    client = FMPStableClient("configured", timeout_seconds=12, retries=2, session=session)
    response = client.get("profile", {"symbol": "NVDA"}, deadline_monotonic=time.monotonic() + 0.02)
    assert response.outcome in {DEADLINE_EXPIRED, "TIMEOUT_OR_NETWORK_FAILURE"}
    assert len(session.calls) == 1


def test_progress_contract_is_visible_before_completion_and_qa_reads_it():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    qa = (ROOT / "agents/runtime_qa_user_journeys_v40.py").read_text(encoding="utf-8")
    assert 'data-atlas-readiness="SHELL_READY"' in app
    assert 'data-atlas-qa="research-progress"' in app
    assert "_research_progress_metadata" in qa
    assert "partial progress preserved" in qa


def test_request_id_and_etf_invalid_boundaries_remain_explicit():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    acquisition = (ROOT / "services/fmp_research_acquisition.py").read_text(encoding="utf-8")
    assert "atlas_research_request_id_" in app
    assert "if submitted and not re.fullmatch" in app
    assert 'if security != "ETF":' in acquisition


def test_spy_skips_peers_and_all_corporate_provider_families(tmp_path):
    client = FakeFMP()
    result = acquire_explicit_fmp_research(
        "SPY", production_row={"ticker": "SPY", "security_type": "ETF"},
        client=client, cache_root=tmp_path,
    )
    assert [family for family, _ in client.calls] == ["profile"]
    assert result["diagnostics"]["requests"] == 1
    assert result["research_context"]["evidence_families"]["earnings_history"]["semantic_status"] == "NOT_APPLICABLE"
