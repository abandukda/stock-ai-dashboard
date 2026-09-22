from pathlib import Path
import json

from scripts.finnhub_p_fcf_peer_certification import (
    TARGETS, derive_candidate_symbols, load_governed_classifications,
)


def test_candidate_universe_is_derived_from_governed_classification_not_hard_coded(tmp_path: Path):
    rows = [
        {"ticker": "AAPL", "sector": "Technology", "industry": "Hardware", "market_cap": 100},
        {"ticker": "P1", "sector": "Technology", "industry": "Hardware", "market_cap": 80},
        {"ticker": "P2", "sector": "Technology", "industry": "Hardware", "market_cap": 120},
        {"ticker": "P3", "sector": "Technology", "industry": "Hardware", "market_cap": 150},
        {"ticker": "S1", "sector": "Technology", "industry": "Software", "market_cap": 90},
    ]
    primary = tmp_path / "classification.json"; primary.write_text(json.dumps(rows))
    supplemental = tmp_path / "supplemental.json"; supplemental.write_text(json.dumps({"universe": []}))
    catalog, provenance = load_governed_classifications(primary, supplemental)
    symbols, diagnostics = derive_candidate_symbols(catalog, ("AAPL",))
    assert symbols == ["AAPL", "P1", "P2", "P3", "S1"]
    assert diagnostics["AAPL"]["industry_candidates_available"] == 3
    assert provenance["primary_sha256"]


def test_required_targets_are_fixed_but_peer_lists_are_not_embedded_per_target():
    assert TARGETS == ("AAPL", "MSFT", "NVDA", "WMT", "IBM", "F", "PFE", "TSLA")
    import inspect
    import scripts.finnhub_p_fcf_peer_certification as module
    source = inspect.getsource(module.derive_candidate_symbols)
    assert "AAPL" not in source and "MSFT" not in source
    assert "minimum_peer_count" not in source


def test_supplemental_gics_consumer_staples_joins_governed_consumer_defensive_taxonomy(tmp_path: Path):
    primary = tmp_path / "classification.json"; primary.write_text(json.dumps([
        {"ticker": "COST", "sector": "Consumer Defensive", "industry": "Discount Stores", "market_cap": 400},
    ]))
    supplemental = tmp_path / "supplemental.json"; supplemental.write_text(json.dumps({"assets": [
        {"ticker": "WMT", "type": "STOCK", "sector": "Consumer Staples"},
    ]}))
    catalog, _ = load_governed_classifications(primary, supplemental)
    assert catalog["WMT"]["sector"] == "Consumer Defensive"
    assert catalog["WMT"]["source_sector"] == "Consumer Staples"
    assert catalog["WMT"]["sector_normalization"] == "ATLAS_GOVERNED_SECTOR_TAXONOMY_EQUIVALENCE_V1"
