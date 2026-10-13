from scripts.report_r2_period_depth import period_coverage


def test_period_standard_is_fail_closed_and_conserved():
    records = [{"ticker": "A", "professional_evidence_lineage": {"fields": {}}}]
    recovered = {"A": {
        "free_cash_flow": {"period": "FY2025", "frequency": "ANNUAL", "evidence_id": "e1", "provider": "FINNHUB", "unit": "USD"},
    }}
    result = period_coverage(records, {"A"}, recovered)
    by_metric = {row["metric"]: row for row in result["matrix"]}
    assert by_metric["free_cash_flow"]["status"] == "BELOW_STANDARD"
    assert by_metric["free_cash_flow"]["annual_count"] == 1
    assert by_metric["revenue"]["status"] == "NOT_AVAILABLE"
    assert result["conservation"] == {"STANDARD_MET": 0, "BELOW_STANDARD": 1, "NOT_AVAILABLE": 3, "total": 4}
    assert result["authority_preserved"] is True and result["g6_changed"] is False
