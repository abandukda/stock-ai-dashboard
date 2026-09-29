import pytest

from services.finnhub_forward_valuation_bridge import (
    accounting_bridge, apply_forward_inputs, classify_method, select_forward_estimate,
)


def estimate(value=5, *, period="2027-12-31", currency_frequency="annual", analysts=12):
    return {"frequency": currency_frequency, "estimates": [{
        "period": period, "frequency": currency_frequency, "year": 2027,
        "average": value, "high": value + 1, "low": value - 1, "analyst_count": analysts,
    }]}


def profile(currency="USD"):
    return {"currency": currency, "estimate_currency": currency}


def row():
    fields = {
        name: {"evidence_id": f"E-{name}", "currency": "USD", "unit": "USD"}
        for name in ("market_cap", "total_debt", "cash_and_equivalents")
    }
    fields["diluted_shares"] = {"evidence_id": "E-shares", "unit": "SHARES"}
    return {
        "ticker": "AAA", "market_cap": 1_000, "total_debt": 100, "cash_and_equivalents": 50,
        "diluted_shares": 10, "professional_evidence_lineage": {"fields": fields, "evidence_ids": ["E0"]},
    }


def test_forward_eps_selects_earliest_future_annual_period_deterministically():
    payload = {"frequency": "annual", "estimates": [
        estimate(7, period="2028-12-31")["estimates"][0],
        estimate(6, period="2027-12-31")["estimates"][0],
        estimate(4, period="2025-12-31")["estimates"][0],
    ]}
    result = select_forward_estimate(
        profile=profile(), estimate=payload, capability="eps_estimates",
        snapshot_timestamp="2026-09-29T12:00:00Z", price_currency="USD",
    )
    assert result["status"] == "CERTIFIED_PROVIDER_CONTRACT"
    assert result["value"] == 6 and result["period"] == "2027-12-31"
    assert result["basis"] == "PER_SHARE" and result["analyst_count"] == 12


def test_forward_estimate_rejects_currency_mismatch_and_missing_analysts():
    mismatch = select_forward_estimate(
        profile=profile("EUR"), estimate=estimate(), capability="eps_estimates",
        snapshot_timestamp="2026-09-29T12:00:00Z", price_currency="USD",
    )
    assert mismatch["status"] == "CURRENCY_MISMATCH"
    incomplete = select_forward_estimate(
        profile=profile(), estimate=estimate(analysts=0), capability="eps_estimates",
        snapshot_timestamp="2026-09-29T12:00:00Z", price_currency="USD",
    )
    assert incomplete["status"] == "INPUT_INCOMPLETE"


def test_accounting_bridge_uses_absolute_values_and_requires_lineage():
    result = accounting_bridge(row())
    assert result["status"] == "CERTIFIED" and result["enterprise_value"] == 1050
    broken = row(); broken["professional_evidence_lineage"]["fields"].pop("total_debt")
    assert accounting_bridge(broken)["status"] == "ACCOUNTING_BRIDGE_INCOMPLETE"


def test_apply_forward_inputs_preserves_contract_metadata_without_scaling():
    inputs = {name: estimate(value) for name, value in {
        "eps_estimates": 5, "revenue_estimates": 1_000_000,
        "ebitda_estimates": 200_000, "dps_estimates": 2, "fcf_estimates": 120_000,
    }.items()}
    bridged, results = apply_forward_inputs(
        row(), profile=profile(), estimates=inputs, snapshot_timestamp="2026-09-29T12:00:00Z",
        evidence_ids={name: f"E-{name}" for name in inputs},
    )
    assert bridged["forward_eps"] == 5
    assert bridged["forward_ebitda"] == 200_000
    assert bridged["professional_evidence_lineage"]["fields"]["forward_ebitda"]["scale"] == "IDENTITY"
    assert all(result["status"] == "CERTIFIED_PROVIDER_CONTRACT" for result in results.values())


@pytest.mark.parametrize(("method", "status", "expected"), [
    ("VAL_FORWARD_PE_V1", "PUBLISHED", "CERTIFIED_APPLICABLE"),
    ("VAL_FORWARD_PE_V1", "NOT_APPLICABLE", "CERTIFIED_BUT_NOT_APPLICABLE"),
    ("VAL_FCFF_DCF_V1", "INSUFFICIENT_INPUTS", "SCENARIO_EVIDENCE_INCOMPLETE"),
])
def test_method_classification_is_fail_closed(method, status, expected):
    capabilities = {name: {"status": "CERTIFIED_PROVIDER_CONTRACT"} for name in (
        "eps_estimates", "ebitda_estimates", "revenue_estimates", "fcf_estimates", "dps_estimates",
    )}
    assert classify_method(
        row=row(), model={"methodology_id": method, "status": status}, forward_results=capabilities,
    ) == expected
