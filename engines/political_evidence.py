"""Canonical, non-scoring congressional transaction evidence semantics."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _first(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value is not None and not (isinstance(value, str) and not value.strip()):
            return value
    return None


def _transaction_type(value: Any) -> str:
    text = _text(value)
    lowered = text.lower()
    if any(token in lowered for token in ("purchase", "buy", "add")):
        return "Buy"
    if any(token in lowered for token in ("sale", "sell", "sold", "dispose")):
        return "Sell"
    if "exchange" in lowered:
        return "Exchange"
    return text or "Other"


def normalize_political_transaction(row: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return auditable transaction metadata without inventing amounts/dates."""
    if not isinstance(row, Mapping):
        return None
    ticker = _text(_first(row, "symbol", "ticker", "Ticker", "assetTicker", "securityTicker")).upper()
    if not re.fullmatch(r"[A-Z]{1,5}", ticker):
        return None
    first = _text(_first(row, "firstName", "representative", "senator", "name", "disclosureOwner"))
    last = _text(_first(row, "lastName"))
    member = f"{first} {last}".strip() if last and last.lower() not in first.lower() else first
    transaction_date = _text(_first(row, "transactionDate", "transaction_date", "tradeDate", "date"))
    disclosure_date = _text(_first(row, "disclosureDate", "disclosure_date", "filingDate", "reportedDate"))
    provider = _text(_first(row, "provider", "source", "sourceName")) or "FMP"
    source_url = _text(_first(row, "source_url", "sourceUrl", "url", "link", "disclosureUrl"))
    payload = {
        "member_name": member or "Not provided",
        "chamber_or_office": _text(_first(row, "chamber", "Chamber", "office", "district")),
        "ticker": ticker,
        "security": _text(_first(row, "securityName", "assetDescription", "companyName", "company", "issuer")) or ticker,
        "transaction_type": _transaction_type(_first(row, "transaction", "transactionType", "type")),
        "transaction_date": transaction_date,
        "disclosure_date": disclosure_date,
        "reported_amount_range": _text(_first(row, "amount", "amountRange", "transactionAmount", "range")) or "Not disclosed",
        "provider": provider,
        "source_url": source_url,
        "evidence_type": "CONGRESSIONAL_TRANSACTION",
    }
    identity = {key: payload[key] for key in (
        "member_name", "ticker", "transaction_type", "transaction_date",
        "disclosure_date", "reported_amount_range", "provider",
    )}
    payload["evidence_id"] = "political-" + hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:20]
    return payload


__all__ = ["normalize_political_transaction"]
