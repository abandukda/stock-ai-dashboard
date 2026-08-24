from __future__ import annotations

from pathlib import Path

from agents.atlas_runtime_qa_v3 import _classify_failed_request
from agents.runtime_qa_architecture import (
    certification_integrity, certification_record, journey_completeness,
)
from agents.runtime_qa_user_journeys_v40 import page_identity_settled


EXPECTED = {"navigation": 14, "research": 6, "ask": 6, "responsive": 6, "cross_page": 1}
MATRIX = {"entries": [{"role": "fixed_equity", "ticker": "NVDA"}]}


def test_page_one_behind_never_settles():
    assert not page_identity_settled(
        requested="ETFs", rendered="Recovery", selected=True,
        page_ready=True, rendered_exception=False,
    )


def test_timeout_marks_required_journeys_incomplete_and_audit_invalid():
    completeness = journey_completeness(EXPECTED, {}, engine_error="TimeoutError")
    result = certification_integrity(
        authenticated=True, page_count=14, journey_state=completeness,
        ticker_matrix=MATRIX, cross_page={"status": "NOT_EXECUTED", "reason": "TimeoutError"},
    )
    assert completeness["status"] == "INCOMPLETE"
    assert completeness["engine_error_category"] == "TimeoutError"
    assert result["audit_valid"] is False
    assert result["classification"] == "QA_DEFECT" and result["severity"] == "P1"


def test_empty_ticker_matrix_and_cross_page_are_not_pass():
    complete = journey_completeness(EXPECTED, EXPECTED)
    empty_matrix = certification_integrity(
        authenticated=True, page_count=14, journey_state=complete,
        ticker_matrix={}, cross_page={"status": "PASS"},
    )
    empty_cross = certification_integrity(
        authenticated=True, page_count=14, journey_state=complete,
        ticker_matrix=MATRIX, cross_page={},
    )
    assert "TICKER_MATRIX_EMPTY" in empty_matrix["failures"]
    assert "CROSS_PAGE_NOT_EXECUTED" in empty_cross["failures"]


def test_empty_reconciliation_cannot_be_semantic_pass():
    record = certification_record(
        page="Research Any Ticker", journey="Page certification", classification="PASS",
        navigation_status="PASS", semantic_status="PASS", reconciliation_status="PASS",
    )
    assert record["classification"] == "QA_DEFECT"
    assert record["reconciliation_status"] == "NOT_EXECUTED"


def test_user_details_404_is_explicit_platform_noise():
    result = _classify_failed_request("https://example.invalid/api/v2/user/details?token=secret", 404)
    assert result == {
        "path": "/api/v2/user/details", "classification": "PLATFORM_NOISE",
        "relevance": "NOT_ATLAS_FUNCTIONALITY",
    }
    assert "secret" not in str(result)


def test_application_emits_canonical_page_identity_and_global_page_ready():
    source = Path("app.py").read_text(encoding="utf-8")
    assert 'data-atlas-qa="page-route"' in source
    assert 'data-atlas-qa="page-contract"' in source
    assert 'data-atlas-page-ready="true"' in source


def test_runtime_seeds_artifact_and_propagates_engine_exception():
    source = Path("agents/atlas_runtime_qa_v3.py").read_text(encoding="utf-8")
    assert '"ticker_matrix": resolved_ticker_matrix' in source
    assert '"engine_exception_category": exception_category' in source
    assert 'classification="QA_DEFECT"' in source
    assert "timeout=600" in source
