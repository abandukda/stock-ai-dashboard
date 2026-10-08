import json
from pathlib import Path

import pytest

from engines.ask_atlas_engine import ask_atlas
from services.customer_authority import bind_report_to_customer_authority, customer_authority


def _row(ticker="NVDA", *, allowed=True):
    facts = {
        "NVDA": (346.05, 85.96, 87.46),
        "MSFT": (704.48, 80.06, 86.20),
        "AVT": (130.97, 80.66, 87.85),
    }
    fair_value, opportunity, confidence = facts[ticker]
    return {
        "ticker": ticker, "candidate_digest": "candidate", "source_sha": "source",
        "certified_customer_evaluation": {
            "ticker": ticker, "customer_publication_allowed": allowed,
            "decision": {"action": "BUY_NOW", "opportunity": opportunity, "decision_confidence": confidence},
            "fields": {"atlas_fair_value": {"value": fair_value, "certification_status": "CERTIFIED"}},
            "digests": {"evaluation_snapshot_id": f"snapshot-{ticker}"},
        },
    }


@pytest.mark.parametrize("ticker,expected", [
    ("NVDA", (346.05, 85.96, 87.46)),
    ("MSFT", (704.48, 80.06, 86.20)),
    ("AVT", (130.97, 80.66, 87.85)),
])
def test_cross_surface_authority_is_exact(ticker, expected):
    authority = customer_authority({"Raw": _row(ticker)})
    assert authority["action"] == "BUY_NOW"
    assert (authority["fair_value"], authority["opportunity"], authority["confidence"]) == expected
    assert authority["publication_allowed"] is True
    assert authority["evaluation_snapshot"] == f"snapshot-{ticker}"


def test_withheld_and_incomplete_authority_fail_closed():
    assert customer_authority(_row(allowed=False))["status"] == "RATING_NOT_PUBLISHED"
    incomplete = _row()
    incomplete["certified_customer_evaluation"]["fields"]["atlas_fair_value"].pop("value")
    assert customer_authority(incomplete)["status"] == "RATING_NOT_PUBLISHED"


@pytest.mark.parametrize("question", [
    "What does ATLAS think about NVDA?", "Why does ATLAS like NVDA?",
])
def test_direct_ask_uses_certified_authority_and_fields(question):
    report = bind_report_to_customer_authority({"ticker": "NVDA", "sections": {}}, _row())
    result = ask_atlas(question, report)
    assert result["canonical_decision_state"] == "BUY_NOW"
    for text in ("BUY NOW", "$346.05", "85.96", "87.46"):
        assert text in result["answer"]


def test_withheld_ask_never_exposes_protected_fields():
    report = bind_report_to_customer_authority({"ticker": "NVDA", "sections": {}}, _row(allowed=False))
    result = ask_atlas("What does ATLAS think about NVDA?", report)
    assert "does not currently publish" in result["answer"]
    assert "346.05" not in result["answer"]


def test_production_runtime_rows_match_governed_expectations():
    rows = json.loads(Path("market_full_scan.json").read_text())
    expectations = json.loads(Path("certification/runtime_projection_expectations_64c0a00a.json").read_text())["expected_facts"]
    by_ticker = {row["ticker"]: row for row in rows}
    for ticker in ("NVDA", "MSFT", "AVT"):
        authority = customer_authority(by_ticker[ticker])
        expected = expectations[ticker]
        assert authority["action"] == expected["action"]
        assert authority["fair_value"] == expected["atlas_fair_value"]
        assert authority["opportunity"] == expected["opportunity"]
        assert authority["confidence"] == expected["decision_confidence"]
        assert authority["evaluation_snapshot"] == expected["evaluation_snapshot_id"]
