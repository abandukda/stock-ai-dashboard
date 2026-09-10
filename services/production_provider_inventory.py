"""Machine-readable provider contract for production decision evidence."""
from __future__ import annotations

from typing import Final


TWELVE_CANONICAL_FIELD_MAP: Final = (
    ("SECURITY_IDENTITY", "symbol/name/exchange/country/type", "stocks", "eligibility", True, True),
    ("COMPANY_PROFILE", "name/exchange/type", "stocks/profile", "routing and explanation", True, True),
    ("MARKET_PRICE", "close/current price", "time_series/quote", "entry and valuation bridge", True, True),
    ("DAILY_HISTORY", "OHLCV", "time_series:1day", "technicals and volume", True, True),
    ("TECHNICALS", "SMA20/SMA50/SMA200/RSI/ATR/support/resistance", "ATLAS from time_series:1day", "technical pillar", True, True),
    ("VOLUME", "completed daily volume/RVOL inputs", "ATLAS from time_series:1day", "volume pillar", True, True),
    ("FINANCIAL_STATEMENTS", "revenue/profit/income/OCF/capex/cash/debt/equity", "income_statement/balance_sheet/cash_flow", "fundamentals and valuation", True, True),
    ("SHARES", "current/basic/diluted shares", "statistics/statements", "market-cap bridge and EPS", True, True),
    ("MARKET_CAP", "price x governed current economic shares", "quote/statistics", "eligibility and valuation", True, True),
    ("ESTIMATES", "forward EPS/revenue", "earnings_estimate/revenue_estimate", "valuation and outlook", True, True),
    ("EARNINGS_HISTORY", "actual/estimate/surprise", "earnings", "fundamental evidence", True, True),
    ("ANALYST_TARGETS", "target range/consensus", "price_target", "non-scoring context", False, False),
    ("OWNERSHIP", "holders", "institutional_holders", "non-scoring context", False, False),
    ("INSIDERS", "transactions", "insider_transactions", "non-scoring context", False, False),
    ("NEWS_CATALYSTS", "company press releases", "press_releases", "non-scoring context", False, False),
)


def production_provider_inventory() -> list[dict[str, object]]:
    return [
        {
            "classification": classification,
            "canonical_field": field,
            "provider": "TWELVE_DATA",
            "endpoint_or_evidence_family": endpoint,
            "consuming_calculation": consumer,
            "affects_action": affects_action,
            "required_for_certification": required,
            "intended_twelve_replacement": "CANONICAL_NOW",
        }
        for classification, field, endpoint, consumer, affects_action, required in TWELVE_CANONICAL_FIELD_MAP
    ] + [{
        "classification": "EARNINGS_TRANSCRIPT_CONTEXT",
        "canonical_field": "earnings_evidence",
        "provider": "FMP",
        "endpoint_or_evidence_family": "earning-call-transcript",
        "consuming_calculation": "qualitative explanation only",
        "affects_action": False,
        "required_for_certification": False,
        "intended_twelve_replacement": "NOT_APPLICABLE_OPTIONAL_CONTEXT",
    }]


__all__ = ["TWELVE_CANONICAL_FIELD_MAP", "production_provider_inventory"]
