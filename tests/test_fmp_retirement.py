from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from services.fmp_phase1_intelligence import (
    acquire_latest_transcript_intelligence,
    load_cached_phase1_families,
    refresh_post_shell_evidence,
)
from services.fmp_stable_client import AUTHORIZATION_FAILURE, FMPStableClient
from services.research_family_cache import load_family_envelope


class ExplodingSession:
    def get(self, *_args, **_kwargs):
        raise AssertionError("retired provider transport must not execute")


def test_retired_transport_cannot_make_direct_request():
    response = FMPStableClient("still-present-secret", session=ExplodingSession()).get("profile", {"symbol": "MSFT"})
    assert response.outcome == AUTHORIZATION_FAILURE
    assert response.attempts == 0


def test_stale_fmp_family_cache_is_rejected(tmp_path):
    path = tmp_path / "analyst_price_target_actions" / "MSFT.latest.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "cache_version": "RESEARCH_FAMILY_CACHE_V2_NO_FMP",
        "provider": "FMP",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "data": {"actions": [{"target": 500}]},
    }))
    assert load_family_envelope("MSFT", "analyst_price_target_actions", root=tmp_path) is None


def test_optional_context_is_explicitly_unavailable_without_calls(tmp_path):
    families = load_cached_phase1_families("MSFT", cache_root=tmp_path)
    expected = {
        "transcript_index", "transcript_intelligence", "analyst_price_target_actions",
        "insider_transactions", "institutional_ownership", "analyst_estimate_snapshots",
    }
    assert expected <= families.keys()
    assert all(families[name]["semantic_status"] == "DATA_UNAVAILABLE" for name in expected)
    refreshed = refresh_post_shell_evidence("MSFT", api_key="secret", cache_root=tmp_path, client=ExplodingSession())
    assert refreshed["provider_calls"] == 0
    transcript = acquire_latest_transcript_intelligence("MSFT", api_key="secret", cache_root=tmp_path, client=ExplodingSession())
    assert transcript["provider_calls"] == 0
    assert transcript["family"]["semantic_status"] == "DATA_UNAVAILABLE"


def test_customer_surfaces_have_honest_unavailable_copy_and_no_secret_dependency():
    research = Path("ui/research_vnext.py").read_text()
    earnings = Path("ui/earnings_vnext.py").read_text()
    recovery = Path("ui/recovery_vnext.py").read_text()
    for label in (
        "management transcript", "recent analyst target actions", "estimate-revision history",
        "insider transactions", "institutional context", "supplemental company profile",
        "supplemental price history",
    ):
        assert label in research
    assert "Earnings-call transcript evidence is unavailable" in earnings
    assert "Optional analyst-action, insider, ownership, and transcript context is unavailable" in recovery
    for source in (research, earnings, recovery):
        assert 'os.getenv("FMP_API_KEY"' not in source


def test_production_workflows_do_not_require_fmp_secret():
    overnight = Path(".github/workflows/overnight_scan.yml").read_text()
    full_qa = Path(".github/workflows/atlas_full_qa_certification.yml").read_text()
    assert "FMP_API_KEY" not in overnight
    assert "FMP_API_KEY" not in full_qa
