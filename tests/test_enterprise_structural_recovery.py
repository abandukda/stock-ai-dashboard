from copy import deepcopy

from scripts.finnhub_canonical_proving_set import _normalized_row
from services.enterprise_review_queue import build_review_queue
from services.finnhub_full_universe_executor import _terminal_from_acquisition


def _record(capability, payload, evidence_id):
    return {
        "payload": payload,
        "provenance": {
            "provider": "FINNHUB",
            "certification_status": "CERTIFIED",
            "derived_use_permission": "CERTIFIED_CALCULATION",
            "raw_evidence_id": evidence_id,
            "capture_timestamp": "2026-10-04T17:03:48+00:00",
        },
    }


def _records(*, industry="Technology", company="Example Corp"):
    return {
        "company_profile": _record("company_profile", {
            "name": company, "industry": industry, "exchange": "NASDAQ",
        }, "FINNHUB:COMPANY_PROFILE:EX:abc"),
        "financial_statements": _record("financial_statements", {"reports": []}, "FINNHUB:FINANCIAL_STATEMENTS:EX:def"),
        "basic_financials": _record("basic_financials", {}, "FINNHUB:BASIC_FINANCIALS:EX:ghi"),
        "historical_ohlcv": _record("historical_ohlcv", {}, "FINNHUB:HISTORICAL_OHLCV:EX:jkl"),
    }


def test_missing_fy_and_technical_history_preserve_profile_and_evidence():
    result = _normalized_row("EX", {"security_type": "COMMON_STOCK"}, _records())
    assert result.row is None
    assert result.security_master == {
        "ticker": "EX", "company_name": "Example Corp", "security_type": "COMMON_STOCK",
        "exchange": "NASDAQ", "sector": "Technology", "industry": "Technology",
        "model_domain": None, "profile_evidence_id": "FINNHUB:COMPANY_PROFILE:EX:abc",
        "provider": "FINNHUB", "capture_timestamp": "2026-10-04T17:03:48+00:00",
        "certification_status": "CERTIFIED", "missing_fields": (),
    }
    assert result.analytical_inputs["latest_fy_available"] is False
    assert result.analytical_inputs["completed_bar_count"] == 0
    assert result.analytical_inputs["evidence_ids"] == tuple(sorted(result.analytical_inputs["evidence_ids"]))
    assert result.blockers == ["LATEST_FY_FINANCIAL_REPORT_MISSING", "COMPLETED_TECHNICAL_HISTORY_INSUFFICIENT"]


def test_classification_failure_does_not_erase_valid_company_identity():
    result = _normalized_row("EX", {}, _records(industry=None))
    assert result.row is None
    assert result.security_master["company_name"] == "Example Corp"
    assert result.security_master["profile_evidence_id"] == "FINNHUB:COMPANY_PROFILE:EX:abc"
    assert "sector" in result.security_master["missing_fields"]
    assert "GOVERNED_CLASSIFICATION_UNRESOLVED" in result.blockers


def test_zero_valued_financial_fields_survive_complete_normalization():
    records = _records()
    facts = {
        name: {"value": value} for name, value in {
            "revenue": 0, "operating_income": 0, "net_income": 0,
            "operating_cash_flow": 0, "capex": 0, "free_cash_flow": 0,
            "total_debt": 0, "cash_and_equivalents": 0, "ebitda": 1,
            "weighted_average_shares_diluted": 0,
            "weighted_average_shares_basic": 0,
        }.items()
    }
    records["financial_statements"]["payload"] = {
        "reports": [{"fiscal_period": "FY", "fiscal_date": "2025-12-31", "currency": "USD", "canonical_facts": facts}],
    }
    count = 200
    records["historical_ohlcv"]["payload"] = {
        "timestamps": list(range(1, count + 1)), "open": [1] * count,
        "high": [1] * count, "low": [1] * count, "close": [1] * count,
        "volume": [0] * count, "completed_session_flags": [True] * count,
    }
    records["basic_financials"]["payload"] = {
        "market_capitalization": 0, "shares_outstanding": 0,
        "provider_contract_metrics": {},
    }
    result = _normalized_row("EX", {"security_type": "COMMON_STOCK", "sector": "Technology", "industry": "Software"}, records)
    assert result.blockers == []
    assert result.row is not None
    assert result.row["latest_revenue"] == 0
    assert result.row["operating_cash_flow"] == 0
    assert result.row["free_cash_flow"] == 0
    assert result.row["total_debt"] == 0


def test_terminal_serialization_is_deterministic_and_leaks_no_protected_fields():
    normalized = _normalized_row("EX", {}, _records(industry=None))
    item = {
        "ticker": "EX", "blockers": normalized.blockers,
        "credential_entitlement_failures": 0,
        "security_master": normalized.security_master,
        "analytical_inputs": normalized.analytical_inputs,
    }
    identity = {"checkpoint_identity_sha256": "checkpoint", "run_identity_sha256": "run"}
    first = _terminal_from_acquisition(deepcopy(item), identity)
    second = _terminal_from_acquisition(deepcopy(item), identity)
    assert first == second
    assert first["canonical_action"] == "RATING_NOT_PUBLISHED"
    assert first["security_master"]["company_name"] == "Example Corp"
    assert first["retained_evidence"]["evidence_ids"]
    assert not ({"fair_value", "opportunity", "decision_confidence", "six_pillars"} & first.keys())


def test_review_queue_registers_every_reason_without_automatic_approval():
    row = {
        "ticker": "CRC",
        "source_sha": "sha",
        "candidate_digest": "candidate",
        "security_master": {"ticker": "CRC", "company_name": "CRC", "sector": "Energy"},
        "reason_codes": ["SECTOR_MODEL_APPLICABILITY_WARNING"],
        "publication_certification": {
            "customer_publication_allowed": False,
            "blockers": ["EXTRAORDINARY_VALUATION_UNCORROBORATED"],
        },
    }
    queue = build_review_queue([row], source_run_id=37216506983, source_artifact="artifact")
    assert queue["counts"]["items"] == 2
    assert {item["blocker_code"] for item in queue["items"]} == {
        "SECTOR_MODEL_APPLICABILITY_WARNING", "EXTRAORDINARY_VALUATION_UNCORROBORATED",
    }
    assert all(item["publication_status"] == "WITHHELD" for item in queue["items"])
    assert all("canonical_action" not in item for item in queue["items"])
    methodology = next(item for item in queue["items"] if "APPLICABILITY" in item["blocker_code"])
    assert methodology["re_evaluation_eligible"] is False
