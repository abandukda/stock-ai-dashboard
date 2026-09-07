"""Deterministic share-basis bridges for securities with non-simple listings.

The registry never replaces provider market capitalization or reported shares.
It records how the quoted security relates to ordinary/economic shares so QA
does not compare unlike bases.
"""
from __future__ import annotations

from typing import Any, Mapping

VERSION = "ATLAS_SHARE_STRUCTURE_V1"

STRUCTURES: dict[str, dict[str, Any]] = {
    "BZ": {"classification": "ADR_RATIO", "adr_ratio": 2.0, "description": "ADS represents two Class A ordinary shares"},
    "DRD": {"classification": "ADR_RATIO", "adr_ratio": 10.0, "description": "ADR represents ten ordinary shares"},
    "BP": {"classification": "ADR_RATIO", "adr_ratio": 6.0, "description": "ADS represents six ordinary shares"},
    "TSM": {"classification": "ADR_RATIO", "adr_ratio": 5.0, "description": "ADS represents five ordinary shares"},
    "SHEL": {"classification": "ADR_RATIO", "adr_ratio": 2.0, "description": "ADR represents two ordinary shares"},
    "UMC": {"classification": "ADR_RATIO", "adr_ratio": 5.0, "description": "ADS represents five ordinary shares"},
    "BEKE": {"classification": "ADR_RATIO", "adr_ratio": 3.0, "description": "ADS represents three Class A ordinary shares"},
    "DSP": {"classification": "PROVIDER_BASIS_DIFFERENCE", "description": "listed class differs from total economic share basis"},
    "CHTR": {"classification": "DUAL_CLASS", "description": "multiple voting/economic classes require total economic shares"},
    "DELL": {"classification": "DUAL_CLASS", "description": "multiple classes and economic interests require total economic shares"},
    "CRGY": {"classification": "DUAL_CLASS", "description": "public shares and non-listed operating-company units differ"},
    "BILL": {"classification": "STALE_SHARES", "description": "point-in-time shares and provider market-cap basis require date alignment"},
    "QSR": {"classification": "DUAL_CLASS", "description": "common shares and exchangeable partnership units differ"},
    "CVNA": {"classification": "DUAL_CLASS", "description": "public Class A shares differ from total economic ownership"},
}


def share_structure_for(ticker: str) -> dict[str, Any]:
    item = STRUCTURES.get(str(ticker or "").strip().upper())
    return {"version": VERSION, **item} if item else {}


def materialize_share_bridge(row: Mapping[str, Any]) -> dict[str, Any]:
    output = dict(row)
    ticker = str(output.get("ticker") or output.get("symbol") or "").upper()
    structure = share_structure_for(ticker)
    if not structure:
        return output
    current = output.get("current_shares_outstanding")
    price = output.get("current_price") or output.get("price")
    market_cap = output.get("market_cap")
    try:
        current_f, price_f, cap_f = float(current), float(price), float(market_cap)
    except (TypeError, ValueError):
        current_f = price_f = cap_f = None
    ratio = structure.get("adr_ratio")
    reconciliation_shares = current_f / ratio if current_f is not None and ratio else None
    method = "ADR_RATIO_ADJUSTED_ORDINARY_SHARES" if reconciliation_shares is not None else "PROVIDER_MARKET_CAP_BASIS"
    if reconciliation_shares is None and price_f not in (None, 0) and cap_f is not None:
        reconciliation_shares = cap_f / price_f
        method = "PROVIDER_IMPLIED_TOTAL_ECONOMIC_SHARES"
    output["share_structure"] = {
        **structure,
        "reported_current_shares": current_f,
        "reported_current_shares_basis": "ORDINARY_SHARES" if ratio else "LISTED_OR_REPORTED_CLASS",
        "market_cap_reconciliation_shares": reconciliation_shares,
        "market_cap_reconciliation_method": method,
        "provider_market_cap_preserved": True,
    }
    return output


__all__ = ["STRUCTURES", "VERSION", "materialize_share_bridge", "share_structure_for"]
