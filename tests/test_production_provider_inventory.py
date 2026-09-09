from services.production_provider_inventory import production_provider_inventory


def test_quantitative_production_inventory_is_twelve_only():
    inventory = production_provider_inventory()
    quantitative = [row for row in inventory if row["classification"] != "EARNINGS_TRANSCRIPT_CONTEXT"]
    assert quantitative
    assert {row["provider"] for row in quantitative} == {"TWELVE_DATA"}
    fmp = [row for row in inventory if row["provider"] == "FMP"]
    assert len(fmp) == 1
    assert fmp[0]["canonical_field"] == "earnings_evidence"
    assert fmp[0]["affects_action"] is False
