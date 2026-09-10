"""Governed, non-scoring supporting-evidence normalization.

These objects explain a canonical decision.  They are never inputs to it.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any, Mapping, Sequence


VERSION = "ATLAS_CONTEXT_EVIDENCE_V1"
CONTEXT_ENDPOINTS = ("press_releases", "insider_transactions", "institutional_holders")
DISPLAY_ALLOWED = "DISPLAY_ALLOWED"
DISPLAY_RESTRICTED = "COMMERCIAL_DISPLAY_NOT_CERTIFIED"
_SPAM = re.compile(r"class action|shareholder alert|law offices|securities fraud|investigation notice", re.I)


def _records(payload: Any, *keys: str) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, Mapping)]
    if not isinstance(payload, Mapping):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, Mapping)]
    return []


def _first(record: Mapping[str, Any], *keys: str) -> Any:
    return next((record.get(k) for k in keys if record.get(k) not in (None, "")), None)


def _family(families: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = families.get(name)
    return value if isinstance(value, Mapping) else {}


def _base(family: Mapping[str, Any], *, status: str, records: Sequence[Mapping[str, Any]], limitations: Sequence[str] = ()) -> dict[str, Any]:
    permitted = family.get("commercial_display_allowed") is True or family.get("commercial_display_status") == DISPLAY_ALLOWED
    return {
        "status": status,
        "provider": family.get("provider") or "TWELVE_DATA",
        "evidence_ids": tuple(x for x in (family.get("evidence_id"),) if x),
        "as_of": family.get("observed_at"),
        "records": tuple(records) if permitted else (),
        "limitations": tuple(limitations) + (() if permitted else ("Commercial display rights are not certified.",)),
        "commercial_display_status": DISPLAY_ALLOWED if permitted else DISPLAY_RESTRICTED,
        "non_scoring": True,
        "normalization_version": VERSION,
    }


def normalize_news(symbol: str, family: Mapping[str, Any]) -> dict[str, Any]:
    raw = _records(family.get("payload"), "press_releases", "data", "results", "items")
    accepted, seen = [], set()
    symbol = symbol.upper()
    for item in raw:
        headline = str(_first(item, "headline", "title", "name") or "").strip()
        source = _first(item, "source", "publisher", "site")
        published = _first(item, "datetime", "published_at", "date", "time")
        item_symbol = str(_first(item, "symbol", "ticker") or symbol).upper()
        if not headline or not source or not published or item_symbol != symbol or _SPAM.search(headline):
            continue
        key = re.sub(r"\W+", " ", headline.lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        accepted.append({
            "ticker": symbol, "headline": headline, "source": source, "published_at": published,
            "summary": _first(item, "summary", "description"), "url": _first(item, "url", "link"),
            "evidence_id": family.get("evidence_id"), "commercial_display_status": DISPLAY_ALLOWED,
        })
    if accepted:
        status = "NEWS_AVAILABLE" if len(accepted) >= 2 else "NEWS_PARTIAL"
    elif family.get("status") == "AVAILABLE":
        status = "NEWS_NONE_RECENT"
    else:
        status = "NEWS_DATA_UNAVAILABLE"
    return _base(family, status=status, records=accepted[:3])


def normalize_insiders(symbol: str, family: Mapping[str, Any]) -> dict[str, Any]:
    raw = _records(family.get("payload"), "insider_transactions", "data", "transactions")
    normalized = []
    for item in raw:
        shares = _first(item, "shares", "amount", "securities_transacted")
        raw_type = str(_first(item, "transaction_type", "type", "transaction_code", "acquisition_or_disposition") or "").upper()
        direction = "BUY" if raw_type in {"BUY", "PURCHASE", "P", "A"} else "SELL" if raw_type in {"SELL", "SALE", "S", "D"} else "OTHER"
        normalized.append({
            "ticker": symbol, "insider_name": _first(item, "insider_name", "name", "reporting_name"),
            "role": _first(item, "role", "title", "position"), "direction": direction,
            "transaction_type": raw_type or None, "transaction_date": _first(item, "transaction_date", "date"),
            "filing_date": _first(item, "filing_date", "filingDate"), "shares": shares,
            "price": _first(item, "price", "transaction_price"), "value": _first(item, "value", "transaction_value"),
            "ownership_after": _first(item, "ownership_after", "shares_owned_following_transaction"),
            "evidence_id": family.get("evidence_id"),
        })
    complete = [x for x in normalized if x["transaction_date"] and x["direction"] != "OTHER"]
    status = "INSIDER_AVAILABLE" if complete and len(complete) == len(normalized) else "INSIDER_PARTIAL" if normalized else "INSIDER_NONE_RECENT" if family.get("status") == "AVAILABLE" else "INSIDER_DATA_UNAVAILABLE"
    return _base(family, status=status, records=normalized[:20])


def normalize_institutions(symbol: str, family: Mapping[str, Any]) -> dict[str, Any]:
    raw = _records(family.get("payload"), "institutional_holders", "data", "holders")
    normalized = [{
        "ticker": symbol, "holder": _first(x, "holder", "name", "investor"),
        "shares": _first(x, "shares", "shares_held"), "value": _first(x, "value", "market_value"),
        "change": _first(x, "change", "change_in_shares"), "ownership_pct": _first(x, "ownership_pct", "percent_held"),
        "filing_period": _first(x, "filing_period", "report_date", "date", "quarter"),
        "evidence_id": family.get("evidence_id"),
    } for x in raw]
    status = "INSTITUTIONAL_AVAILABLE" if normalized and all(x["filing_period"] for x in normalized) else "INSTITUTIONAL_PARTIAL" if normalized else "INSTITUTIONAL_DATA_UNAVAILABLE"
    return _base(family, status=status, records=normalized[:20])


def unavailable_congressional() -> dict[str, Any]:
    return {
        "status": "CONGRESSIONAL_DATA_UNAVAILABLE", "provider": None, "evidence_ids": (), "as_of": None,
        "records": (), "limitations": ("No governed congressional-trading provider is active.", "Disclosures are delayed and context-only."),
        "commercial_display_status": DISPLAY_RESTRICTED, "non_scoring": True, "delayed_disclosure": True,
        "normalization_version": VERSION,
    }


_FINANCIAL_FIELDS = {
    "revenue": "latest_revenue", "revenue_growth": "revenue_growth", "eps": "latest_eps", "eps_growth": "earnings_growth",
    "gross_margin": "gross_profit_margin", "operating_margin": "operating_profit_margin", "net_margin": "net_profit_margin",
    "operating_cash_flow": "operating_cash_flow", "free_cash_flow": "free_cash_flow", "cash": "cash_and_equivalents",
    "total_debt": "total_debt", "net_debt": "net_debt", "current_ratio": "current_ratio", "debt_equity": "debt_to_equity",
    "roe": "return_on_equity", "roa": "return_on_assets", "roic": "roic", "shares_outstanding": "current_shares_outstanding",
    "diluted_shares": "diluted_shares", "forward_eps": "forward_eps", "forward_revenue": "forward_revenue",
    "forward_pe": "provider_forward_pe", "ev_ebitda": "provider_ev_ebitda", "p_fcf": "price_to_free_cash_flow",
}


def normalize_financial_detail(row: Mapping[str, Any]) -> dict[str, Any]:
    lineage = ((row.get("professional_evidence_lineage") or {}).get("fields") or {}) if isinstance(row.get("professional_evidence_lineage"), Mapping) else {}
    fields = {}
    for label, canonical in _FINANCIAL_FIELDS.items():
        value = row.get(canonical)
        fields[label] = {"canonical_field": canonical, "value": value, "classification": "CANONICAL_AVAILABLE" if value is not None else "AVAILABLE_ELSEWHERE_IN_CANONICAL_CONTRACT" if canonical in lineage else "PROVIDER_NOT_AVAILABLE", "lineage": lineage.get(canonical)}
    return {"status": "AVAILABLE" if any(x["value"] is not None for x in fields.values()) else "DATA_UNAVAILABLE", "fields": fields, "as_of": row.get("professional_evidence_as_of"), "evidence_ids": tuple(row.get("twelve_trial_evidence_ids") or ()), "non_scoring": True, "normalization_version": VERSION}


def materialize_context_evidence(row: Mapping[str, Any], families: Mapping[str, Any]) -> dict[str, Any]:
    symbol = str(row.get("ticker") or row.get("symbol") or "").upper()
    output = dict(row)
    output["financial_detail_context"] = normalize_financial_detail(output)
    output["news_context"] = normalize_news(symbol, _family(families, "press_releases"))
    output["insider_context"] = normalize_insiders(symbol, _family(families, "insider_transactions"))
    output["institutional_context"] = normalize_institutions(symbol, _family(families, "institutional_holders"))
    output["congressional_context"] = unavailable_congressional()
    return output


def context_coverage(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    pct = lambda n: round(100 * n / total, 2) if total else 0.0
    financial = {key: pct(sum(((r.get("financial_detail_context") or {}).get("fields") or {}).get(key, {}).get("value") is not None for r in rows)) for key in ("gross_margin", "operating_margin", "net_margin", "roe", "roa", "roic", "debt_equity", "net_debt", "forward_eps", "forward_revenue", "forward_pe", "ev_ebitda", "p_fcf")}
    lanes = {}
    for lane in ("news", "insider", "institutional", "congressional"):
        counts = {}
        for row in rows:
            status = str((row.get(f"{lane}_context") or {}).get("status") or f"{lane.upper()}_DATA_UNAVAILABLE")
            counts[status] = counts.get(status, 0) + 1
        lanes[f"{lane}_context"] = {"counts": counts, "percentages": {k: pct(v) for k, v in counts.items()}}
    return {"population": total, "financial_detail_coverage_pct": financial, **lanes}


def enrich_published_context(rows: Sequence[Mapping[str, Any]], **acquisition_kwargs: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Acquire context only after customer selection; canonical decisions stay byte-for-byte stable."""
    from services.twelve_data_trial_intelligence import acquire_twelve_trial_dossiers
    symbols = tuple(str(r.get("ticker") or r.get("symbol") or "").upper() for r in rows if r.get("ticker") or r.get("symbol"))
    result = acquire_twelve_trial_dossiers(symbols, endpoints=CONTEXT_ENDPOINTS, **acquisition_kwargs)
    dossiers = result.get("dossiers") if isinstance(result.get("dossiers"), Mapping) else {}
    output = []
    for source in rows:
        row = dict(source)
        evaluation = dict(row.get("canonical_investment_evaluation") or {})
        presentation = dict(evaluation.get("trial_presentation_fields") or {})
        normalized = materialize_context_evidence({**row, **presentation}, (dossiers.get(str(row.get("ticker") or row.get("symbol") or "").upper()) or {}).get("families") or {})
        for key in ("financial_detail_context", "news_context", "insider_context", "institutional_context", "congressional_context"):
            row[key] = normalized[key]
        output.append(row)
    return output, dict(result)


__all__ = ["CONTEXT_ENDPOINTS", "VERSION", "context_coverage", "enrich_published_context", "materialize_context_evidence", "normalize_financial_detail", "normalize_news", "normalize_insiders", "normalize_institutions", "unavailable_congressional"]
