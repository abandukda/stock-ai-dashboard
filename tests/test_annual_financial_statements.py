import hashlib
import json
from pathlib import Path

from services.annual_financial_statements import annual_financial_statements
from ui.customer_research_v2 import _annual_statement_frame


ROOT = Path(__file__).resolve().parents[1]


def test_bundle_matches_immutable_manifest_and_preserves_authority():
    folder = ROOT / "data" / "customer_research" / "annual_financials"
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    raw = (folder / manifest["bundle"]).read_bytes()
    bundle = json.loads(raw)

    assert hashlib.sha256(raw).hexdigest() == manifest["bundle_sha256"]
    assert manifest["ticker_count"] == len(bundle["tickers"]) == 11
    assert manifest["filing_count"] == 147
    assert manifest["display_period_count"] == sum(len(row["periods"]) for row in bundle["tickers"].values()) == 52
    assert manifest["ratings_changed"] is False
    assert manifest["publications_changed"] is False
    assert manifest["provider_calls"] == 0
    assert all(row["ratings_changed"] is False and row["publications_changed"] is False for row in bundle["tickers"].values())


def test_ticker_projection_is_bounded_lineage_preserving_and_typed():
    history = annual_financial_statements("nvda")

    assert history["status"] == "AVAILABLE"
    assert history["classification"] == "HISTORICAL_NON_SCORING"
    assert len(history["periods"]) == 5
    assert set(history["statements"]) == {"INCOME_STATEMENT", "CASH_FLOW", "BALANCE_SHEET"}
    available = next(
        cell for item in history["statements"]["INCOME_STATEMENT"]
        for cell in item["cells"] if cell["status"] == "AVAILABLE"
    )
    assert available["provenance"]["endpoint"] == "/stock/financials-reported"
    assert available["provenance"]["frequency"] == "annual"
    assert len(available["provenance"]["raw_sha256"]) == 64
    assert annual_financial_statements("AAPL")["status"] == "UNAVAILABLE"


def test_annual_statement_frame_never_imputes_missing_cells():
    history = annual_financial_statements("SBC")
    frame = _annual_statement_frame(history["statements"]["BALANCE_SHEET"], history["periods"])

    assert not frame.empty
    assert list(frame.columns) == ["Line item", "2025", "2024"]
    assert "Unavailable" in frame.values


def test_renderer_declares_non_scoring_authority_and_original_qa_marker():
    source = (ROOT / "ui" / "customer_research_v2.py").read_text(encoding="utf-8")
    assert '"annual-financial-statements"' in source
    assert 'classification="historical-non-scoring"' in source
    assert "they do not change the certified Action" in source
    assert '"INCOME_STATEMENT": "Annual income statement"' in source
    assert '"CASH_FLOW": "Annual cash flow"' in source
    assert '"BALANCE_SHEET": "Annual balance sheet"' in source
