
"""
Atlas V2 Phase 2A — Institutional ownership normalization.

Normalizes ownership data already present in scanner/provider payloads.
This module does not invent ownership values or call an external provider.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence
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
        text = str(value).replace("%", "").replace(",", "").strip()
        number = float(text)
        return number if math.isfinite(number) else default
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
        _mapping(row.get("ownership")),
        _mapping(row.get("institutional")),
        _mapping(row.get("holders")),
    ]
    return [source for source in sources if source]


def _first(row: Mapping[str, Any], *keys: str, default=None):
    for source in _sources(row):
        for key in keys:
            if key in source and _present(source.get(key)):
                return source.get(key)
    return default


def _normalize_pct(value: Any):
    number = _num(value)
    if number is None:
        return None
    if -2 <= number <= 2:
        number *= 100
    return round(number, 2)


def _holder_rows(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = _first(
        row,
        "major_holders",
        "institutional_holders",
        "topInstitutionalHolders",
        "top_institutional_holders",
        "institutionalOwnershipList",
        "holders",
        default=[],
    )
    output = []
    for item in _sequence(raw):
        if not isinstance(item, Mapping):
            continue
        output.append(
            {
                "holder": (
                    item.get("holder")
                    or item.get("name")
                    or item.get("investor")
                    or item.get("Holder")
                ),
                "shares": item.get("shares") or item.get("Shares"),
                "ownership_pct": _normalize_pct(
                    item.get("ownership_pct")
                    or item.get("percentage")
                    or item.get("percent")
                    or item.get("pctHeld")
                ),
                "change_pct": _normalize_pct(
                    item.get("change_pct")
                    or item.get("change")
                    or item.get("changeInSharesPercentage")
                ),
                "reported_date": (
                    item.get("reported_date")
                    or item.get("date")
                    or item.get("filingDate")
                ),
            }
        )
    return output[:25]


def normalize_institutional_data(row: Mapping[str, Any]) -> dict[str, Any]:
    ownership_pct = _normalize_pct(
        _first(
            row,
            "institutional_ownership_pct",
            "institutional_ownership",
            "Institutional Ownership",
            "Institutional Ownership %",
            "heldPercentInstitutions",
            "institutionsPercentHeld",
            "institutionalOwnership",
            "institutionalOwnershipPercentage",
        )
    )
    change_pct = _normalize_pct(
        _first(
            row,
            "institutional_change_pct",
            "institutional_ownership_change",
            "Institutional Ownership Change",
            "ownership_change_pct",
            "inst_change",
        )
    )
    buying = _num(
        _first(
            row,
            "institutional_buying",
            "institutional_purchases",
            "institutionalPurchases",
            "institutional_buy_count",
        )
    )
    selling = _num(
        _first(
            row,
            "institutional_selling",
            "institutional_sales",
            "institutionalSales",
            "institutional_sell_count",
        )
    )
    holders = _holder_rows(row)

    score = _num(
        _first(
            row,
            "institutional_score",
            "Institutional Score",
            "smart_money_score",
            "Smart Money Score",
        )
    )

    score_basis = []
    if score is None:
        parts = []
        if ownership_pct is not None:
            # High ownership confirms professional participation, but is not
            # automatically bullish because passive funds own many large caps.
            parts.append(max(35.0, min(85.0, 45.0 + ownership_pct * 0.35)))
            score_basis.append("ownership percentage")
        if change_pct is not None:
            parts.append(max(20.0, min(90.0, 55.0 + change_pct * 3.0)))
            score_basis.append("ownership change")
        if buying is not None or selling is not None:
            buy_value = buying or 0.0
            sell_value = selling or 0.0
            total = max(buy_value + sell_value, 1.0)
            parts.append(35.0 + 50.0 * buy_value / total)
            score_basis.append("reported buying versus selling")
        if holders:
            parts.append(65.0)
            score_basis.append("major-holder records")
        score = round(sum(parts) / len(parts), 1) if parts else None

    status = "available" if any(
        value not in (None, [], {})
        for value in (ownership_pct, change_pct, buying, selling, holders)
    ) else "unavailable"

    return {
        "status": status,
        "institutional_ownership_pct": ownership_pct,
        "institutional_change_pct": change_pct,
        "institutional_buying": buying,
        "institutional_selling": selling,
        "major_holders": holders,
        "institutional_score": score,
        "score_basis": score_basis,
        "source": _first(
            row,
            "ownership_source",
            "institutional_source",
            "source",
            default="Current Atlas scanner payload",
        ),
        "as_of": _first(
            row,
            "ownership_as_of",
            "institutional_as_of",
            "updated_at",
            "as_of",
            default="",
        ),
    }


__all__ = ["normalize_institutional_data"]
