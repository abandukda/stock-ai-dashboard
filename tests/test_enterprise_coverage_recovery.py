from copy import deepcopy
import json
from pathlib import Path

from services.certified_customer_evaluation import build_certified_customer_evaluation
from services.enterprise_coverage_ledger import STATES, build_coverage_ledger
from services.valuation_applicability_audit import registry_conflicts


ROOT = Path(__file__).resolve().parents[1]


def _row(ticker):
    for name in ("market_full_scan.json", "full_evaluation_pool.json"):
        rows = json.loads((ROOT / name).read_text())
        match = next((row for row in rows if row.get("ticker") == ticker), None)
        if match:
            return match
    raise LookupError(ticker)


def test_stage_b_reconciles_against_weighted_model_precision_not_display_rounding():
    row = deepcopy(_row("A"))
    evaluation = row["canonical_investment_evaluation"]
    valuation = evaluation["atlas_valuation"]
    price = evaluation["market_snapshot"]["price"]
    valuation["professional_valuation_v2"]["models"] = [
        {"status": "PUBLISHED", "value": 0.0914, "weight": 1.0, "name": "P/FCF"},
    ]
    valuation["fair_value"] = 0.09
    valuation["expected_return"] = round(((0.0914 / price) - 1) * 100, 1)

    result = build_certified_customer_evaluation(row)

    assert result["fields"]["atlas_fair_value"]["value"] == 0.09
    assert result["fields"]["atlas_upside_pct"]["value"] == valuation["expected_return"]
    assert result["customer_publication_allowed"] is True


def test_zero_fair_value_is_preserved_instead_of_treated_as_missing():
    row = deepcopy(_row("A"))
    evaluation = row["canonical_investment_evaluation"]
    valuation = evaluation["atlas_valuation"]
    price = evaluation["market_snapshot"]["price"]
    valuation["professional_valuation_v2"]["models"] = [
        {"status": "PUBLISHED", "value": 0.0029, "weight": 1.0, "name": "P/FCF"},
    ]
    valuation["fair_value"] = 0.0
    valuation["expected_return"] = round(((0.0029 / price) - 1) * 100, 1)

    result = build_certified_customer_evaluation(row)

    assert result["fields"]["atlas_fair_value"]["value"] == 0.0
    assert result["customer_publication_allowed"] is True


def test_extraordinary_valuation_gate_remains_fail_closed():
    row = deepcopy(_row("A"))
    evaluation = row["canonical_investment_evaluation"]
    valuation = evaluation["atlas_valuation"]
    price = evaluation["market_snapshot"]["price"]
    valuation["professional_valuation_v2"]["models"] = [
        {"status": "PUBLISHED", "value": price * 7, "weight": 1.0, "name": "P/FCF"},
    ]
    valuation["fair_value"] = round(price * 7, 2)
    valuation["expected_return"] = 600.0

    result = build_certified_customer_evaluation(row)

    assert result["fields"]["atlas_fair_value"]["value"] is None
    assert result["customer_publication_allowed"] is False
    assert "EXTRAORDINARY_VALUATION_UNCORROBORATED" in result["reconciliation_blockers"]


def test_coverage_ledger_registers_every_withheld_reason_without_protected_values():
    row = deepcopy(_row("A"))
    row["publication_certification"]["customer_publication_allowed"] = False
    row["publication_certification"]["blockers"] = ["CUSTOMER_PROJECTION_RECONCILIATION_FAILED"]

    ledger = build_coverage_ledger(
        [row], source_run_id="37216506983",
        source_artifact="atlas-finnhub-full-universe-final-37216506983",
    )
    publication = next(item for item in ledger if item["dataset"] == "publication")

    assert publication["state"] == "NOT_PROJECTED"
    assert publication["reason_code"] == "CUSTOMER_PROJECTION_RECONCILIATION_FAILED"
    assert publication["state"] in STATES
    assert "action" not in publication
    assert "fair_value" not in publication
    assert all(item["reason_code"] for item in ledger)
    assert publication["source_identity"]["source_run_id"] == "37216506983"


def test_crc_registry_conflict_is_detected_without_changing_policy():
    conflicts = registry_conflicts()

    assert {
        "company_type": "COMMODITY_PRODUCER",
        "methodology_id": "VAL_P_FCF_V1",
        "canonical_validation": "WEAK_FOR_COMPANY_TYPE",
        "evidence_strength_policy": "APPLICABLE",
        "requires_methodology_owner_decision": True,
    } in conflicts
