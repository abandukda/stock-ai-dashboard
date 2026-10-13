import json
import zipfile

from scripts.build_r2_reconciliation_package import build_package, publication_tickers, publishable_buy_now_tickers


def test_streams_publication_and_buy_now_populations(tmp_path):
    archive = tmp_path / "bundle.zip"
    pool = [
        {"ticker": "A", "certified_customer_evaluation": {"customer_publication_allowed": True}, "nested": {"large": [1, 2]}},
        {"ticker": "B", "certified_customer_evaluation": {"customer_publication_allowed": False}},
    ]
    buy = {"records": [
        {"ticker": "A", "publication_eligible": True, "provenance_valid": True},
        {"ticker": "B", "publication_eligible": False, "provenance_valid": True},
    ]}
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("publication_bundle/full_evaluation_pool.json", json.dumps(pool))
        zipped.writestr("buy_now_provenance.json", json.dumps(buy))
    assert publication_tickers(archive) == {"A"}
    assert publishable_buy_now_tickers(archive) == {"A"}


def test_package_conserves_and_fails_closed_on_unavailable_six_boundary_contract():
    package, missing = build_package(
        [{"ticker": "A", "free_cash_flow": 10, "professional_evidence_lineage": {"fields": {
            "free_cash_flow": {"evidence_id": "e1", "period": "FY2026", "provider": "FINNHUB", "unit": "USD"}
        }}}],
        {"A"}, {"A"}, source_identity={"source_sha": "abc"}, archive_sha256="def",
    )
    assert package["conservation"]["classified_field_cells"] == 15
    assert package["six_boundary_mapping"]["status"] == "BLOCKED_MAPPING"
    assert package["population_matrix"]["customer_published"]["ticker_count"] == 1
    assert package["population_matrix"]["publishable_buy_now"]["fields"]["free_cash_flow"]["immediately_displayable"] == 1
    assert package["g6_request"]["missing_cell_count"] == 14
    assert len(missing) == 14
    assert all(row["customer_published"] and row["publishable_buy_now"] for row in missing)
