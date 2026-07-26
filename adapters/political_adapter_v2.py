
"""
Atlas V2 Phase 2A — Political and congressional activity normalization.

Normalizes data already present in the scanner/provider payload. It separates
"No records found" from "Data was not loaded."
"""

from __future__ import annotations

from typing import Any, Mapping
import math


_MISSING = {"", "none", "null", "nan", "n/a", "na", "unknown", "unavailable", "under review"}


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in _MISSING
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    return value not in ([], {})


def _num(value: Any, default=None):
    try:
        if not _present(value):
            return default
        return float(str(value).replace(",", "").replace("%", "").strip())
    except Exception:
        return default


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _sources(row: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    sources = [
        row,
        _mapping(row.get("raw")),
        _mapping(row.get("Raw")),
        _mapping(row.get("political")),
        _mapping(row.get("congressional")),
        _mapping(row.get("policy")),
    ]
    return [source for source in sources if source]


def _first(row: Mapping[str, Any], *keys: str, default=None):
    for source in _sources(row):
        for key in keys:
            if key in source and _present(source.get(key)):
                return source.get(key)
    return default


def _transactions(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = _first(
        row,
        "political_transactions",
        "congressional_trades",
        "political_trades",
        "house_trades",
        "senate_trades",
        "transactions",
        default=[],
    )
    output = []
    for item in _sequence(raw):
        if not isinstance(item, Mapping):
            continue
        output.append(
            {
                "politician": (
                    item.get("politician")
                    or item.get("representative")
                    or item.get("senator")
                    or item.get("name")
                ),
                "party": item.get("party"),
                "chamber": item.get("chamber") or item.get("house"),
                "transaction": (
                    item.get("transaction")
                    or item.get("type")
                    or item.get("transactionType")
                ),
                "transaction_date": (
                    item.get("transaction_date")
                    or item.get("transactionDate")
                    or item.get("date")
                ),
                "disclosure_date": (
                    item.get("disclosure_date")
                    or item.get("disclosureDate")
                    or item.get("filingDate")
                ),
                "amount": (
                    item.get("amount")
                    or item.get("value")
                    or item.get("amountRange")
                ),
            }
        )
    return output[:30]


def normalize_political_data(row: Mapping[str, Any]) -> dict[str, Any]:
    transactions = _transactions(row)
    buyers = _num(
        _first(
            row,
            "political_buyers",
            "congressional_buyers",
            "political_buy_count",
        )
    )
    sellers = _num(
        _first(
            row,
            "political_sellers",
            "congressional_sellers",
            "political_sell_count",
        )
    )

    if buyers is None and transactions:
        buyers = sum(
            "buy" in str(item.get("transaction") or "").lower()
            or "purchase" in str(item.get("transaction") or "").lower()
            for item in transactions
        )
    if sellers is None and transactions:
        sellers = sum(
            "sell" in str(item.get("transaction") or "").lower()
            or "sale" in str(item.get("transaction") or "").lower()
            for item in transactions
        )

    policy_summary = _first(
        row,
        "political_support_summary",
        "political_support",
        "political_context",
        "policy_context",
        "Political Signal",
        default="",
    )
    regulatory = _first(
        row,
        "regulatory_exposure",
        "regulatory_risk",
        "Regulatory Exposure",
        default="",
    )
    export_controls = _first(
        row,
        "export_control_exposure",
        "export_controls",
        "Export Control Exposure",
        default="",
    )
    government_contracts = _first(
        row,
        "government_contract_exposure",
        "government_contracts",
        "Government Contract Exposure",
        default="",
    )
    tariff = _first(
        row,
        "tariff_exposure",
        "Tariff Exposure",
        default="",
    )

    score = _num(
        _first(
            row,
            "political_score",
            "Political Score",
            "political_buying_score",
            "Political Buying Score",
            "policymaker_disclosure_score",
            "congressional_trading_score",
        )
    )
    if score is None:
        parts = []
        buy_value = buyers or 0.0
        sell_value = sellers or 0.0
        if buy_value or sell_value:
            total = max(buy_value + sell_value, 1.0)
            parts.append(35.0 + 50.0 * buy_value / total)
        text = " ".join(
            str(value).lower()
            for value in (
                policy_summary,
                regulatory,
                export_controls,
                government_contracts,
                tariff,
            )
            if value
        )
        if text:
            if any(word in text for word in ("tailwind", "support", "benefit", "funding", "contract", "incentive")):
                parts.append(70.0)
            elif any(word in text for word in ("restriction", "investigation", "headwind", "sanction", "ban")):
                parts.append(35.0)
            else:
                parts.append(52.0)
        score = round(sum(parts) / len(parts), 1) if parts else None

    provider_attempted = bool(
        _first(
            row,
            "political_source",
            "political_as_of",
            "political_fetch_status",
            "congressional_source",
            default="",
        )
    )
    if transactions or buyers or sellers or policy_summary or regulatory or export_controls or government_contracts or tariff:
        status = "available"
        retrieval_status = "scanner_payload"
    elif provider_attempted:
        status = "no_records"
        retrieval_status = "no_records_found"
    else:
        status = "unavailable"
        retrieval_status = "not_loaded"

    return {
        "status": status,
        "retrieval_status": retrieval_status,
        "political_score": score,
        "buyers": buyers,
        "sellers": sellers,
        "transactions": transactions,
        "policy_summary": policy_summary,
        "regulatory_exposure": regulatory,
        "export_control_exposure": export_controls,
        "government_contract_exposure": government_contracts,
        "tariff_exposure": tariff,
        "source": _first(
            row,
            "political_source",
            "congressional_source",
            "source",
            default="Current Atlas scanner payload",
        ),
        "as_of": _first(
            row,
            "political_as_of",
            "congressional_as_of",
            "updated_at",
            default="",
        ),
    }


__all__ = ["normalize_political_data"]
