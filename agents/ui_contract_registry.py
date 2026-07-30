"""Canonical product expectations for Atlas pages and research sections."""

from __future__ import annotations

NAVIGATION_REQUIREMENTS = {
    "Home",
    "Today's Opportunities",
    "Volume Intelligence",
    "Atlas Core Holdings",
    "Research Any Ticker",
    "Earnings Intelligence",
    "Full Ranked Scan",
    "Portfolio Intelligence",
    "Watchlist Intelligence",
    "Recovery",
    "ETFs",
    "Political Intelligence",
    "Ask AI",
    "Developer Center",
}

RESEARCH_COMPONENT_REQUIREMENTS = {
    "fundamentals": {
        "required": True,
        "purpose": "Business quality, growth, profitability, cash flow, and balance-sheet health.",
    },
    "technical": {
        "required": True,
        "purpose": "Trend, momentum, volume, support, resistance, and entry timing.",
    },
    "valuation": {
        "required": True,
        "purpose": "Validated fair value and expected return.",
    },
    "analyst": {
        "required": False,
        "purpose": "Wall Street consensus and target support.",
    },
    "earnings": {
        "required": False,
        "purpose": "Recent results, guidance, and management interpretation.",
    },
    "news": {
        "required": False,
        "purpose": "Recent verified catalysts and risks.",
    },
    "institutional": {
        "required": False,
        "purpose": "Institutional ownership and flow evidence.",
    },
    "political": {
        "required": False,
        "purpose": "Disclosed political activity and regulatory exposure.",
    },
}

CUSTOMER_TRUST_RULES = {
    "missing_not_zero": "Unavailable evidence must not be displayed as a real zero.",
    "missing_optional_not_negative": "Missing optional evidence must not automatically weaken the verdict.",
    "no_fake_low_risk": "No data must not be summarized as low risk.",
    "target_independence": "Atlas fair value should disclose when it relies on analyst targets.",
    "verdict_alignment": "Verdict, horizon, sizing, expected return, and blockers must not contradict one another.",
    "grounded_ai": "AI summaries must separate verified facts, Atlas inference, and unavailable evidence.",
}

__all__ = [
    "NAVIGATION_REQUIREMENTS",
    "RESEARCH_COMPONENT_REQUIREMENTS",
    "CUSTOMER_TRUST_RULES",
]
