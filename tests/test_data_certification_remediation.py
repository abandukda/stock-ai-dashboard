from services.data_certification_remediation import classify_blockers, continuity_check, provider_quality
from services.secondary_financial_validation import acquire_secondary_fmp_inputs


def test_blockers_are_classified_without_becoming_actions():
    record={"certification_state":"REVIEW_REQUIRED","warnings":["MARKET_CAP_BRIDGE_FAILURE"],
            "checks":{"market_cap_bridge":{"status":"NOT_TESTABLE","failure_classification":"CURRENT_SHARES_FIELD_MISSING"}}}
    result=classify_blockers(record)
    assert result[0]["classification"]=="PROVIDER_FIELD_MISSING"
    assert "WATCH" not in str(result)


def test_continuity_requires_attributable_event_for_large_change():
    series=[{"period":"2025","revenue":100},{"period":"2026","revenue":200}]
    assert continuity_check(series,field="revenue")
    series[1]["attributable_event_evidence_id"]="SEC-1"
    assert continuity_check(series,field="revenue")==[]


def test_provider_quality_uses_metric_specific_reconciliation_results():
    record={"input_lineage":{"revenue":{"source":"FMP"}},"checks":{"input_reconciliation":{
        "agreements":[{"metric":"revenue","secondary_source":"TWELVE_DATA"}],"divergences":[]}}}
    quality=provider_quality([record])["families"]["revenue"]
    assert quality["records_checked"]==1
    assert quality["agreement_rate"]==100
    assert quality["secondary_validators"]=={"TWELVE_DATA":1}
    assert quality["secondary_validation_attempted"]==1
    assert quality["secondary_validation_success"]==1
    assert quality["secondary_validation_unavailable"]==0
    assert quality["secondary_validation_incompatible"]==0
    assert quality["secondary_validation_failure"]==0


def test_bounded_fmp_secondary_preserves_share_concepts_and_lineage():
    payloads={
        "income-statement":[{"date":"2025-12-31","revenue":1000,"operatingIncome":140,"netIncome":100,"epsDiluted":2,"ebitda":180,"weightedAverageShsOutDil":50}],
        "balance-sheet-statement":[{"date":"2025-12-31","cashAndCashEquivalents":80,"totalDebt":120}],
        "cash-flow-statement":[{"date":"2025-12-31","operatingCashFlow":150,"capitalExpenditure":-30,"freeCashFlow":120}],
        "enterprise-values":[{"date":"2026-09-05","numberOfShares":55}],
    }
    class Response:
        status_code=200
        def __init__(self,payload): self._payload=payload
        def json(self): return self._payload
    class Session:
        def get(self,url,params,timeout): return Response(payloads[url.rsplit("/",1)[-1]])
    result=acquire_secondary_fmp_inputs(["ABC"],api_key="redacted",session=Session())
    values=result["inputs"]["ABC"]
    assert values["current_shares_outstanding"]["value"]==55
    assert values["diluted_shares"]["value"]==50
    assert values["operating_income"]["value"]==140
    assert values["operating_income"]["period"]==values["revenue"]["period"]
    assert values["free_cash_flow"]["evidence_id"].startswith("FMPVAL-")
