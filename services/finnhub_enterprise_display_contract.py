"""Signed Finnhub Enterprise display authority for covered US-equity feeds.

This module grants *display* authority only.  It never grants scoring authority,
certification, raw-feed export, or access to endpoints absent from Appendix A.
"""
from __future__ import annotations

from dataclasses import dataclass

from services.provider_domain_contracts import UsePermission


CONTRACT_ID = "FINNHUB_MARKET_DATA_AGREEMENT_SIGNED_APPENDIX_A"
MARKET_SCOPE = "US_EQUITY"


@dataclass(frozen=True)
class EnterpriseDisplayAuthority:
    capability: str
    endpoint: str
    market_scope: str = MARKET_SCOPE
    commercial_website_mobile_display: bool = True
    derived_data_display: bool = True
    raw_machine_readable_redistribution: bool = False
    retention: str = "CONTRACT_PERIOD_ONLY"
    termination_action: str = "DELETE_AND_CONFIRM_IN_WRITING"
    contract_id: str = CONTRACT_ID

    @property
    def display_permission(self) -> UsePermission:
        return UsePermission.DISPLAY_ONLY


_COVERED = {
    "company_profile": "/stock/profile2",
    "executives": "/stock/executive",
    "company_news": "/company-news",
    "press_releases": "/press-releases2",
    "peers": "/stock/peers",
    "basic_financials": "/stock/metric",
    "ownership": "/stock/ownership",
    "fund_ownership": "/stock/fund-ownership",
    "institutional_profile": "/institutional/profile",
    "institutional_portfolio": "/institutional/portfolio",
    "institutional_ownership": "/institutional/ownership",
    "insider_transactions": "/stock/insider-transactions",
    "insider_sentiment": "/stock/insider-sentiment",
    "financial_statements": "/stock/financials-reported",
    "sec_filings": "/stock/filings",
    "dividends": "/stock/dividend",
    "sector_metrics": "/sector/metrics",
    "price_metrics": "/stock/price-metric",
    "historical_market_cap": "/stock/historical-market-cap",
    "recommendations": "/stock/recommendation",
    "price_targets": "/stock/price-target",
    "analyst_actions": "/stock/upgrade-downgrade",
    "revenue_estimates": "/stock/revenue-estimate",
    "eps_estimates": "/stock/eps-estimate",
    "ebitda_estimates": "/stock/ebitda-estimate",
    "ebit_estimates": "/stock/ebit-estimate",
    "net_income_estimates": "/stock/net-income-estimate",
    "gross_income_estimates": "/stock/gross-income-estimate",
    "pretax_income_estimates": "/stock/pretax-income-estimate",
    "dps_estimates": "/stock/dps-estimate",
    "ocf_estimates": "/stock/ocf-estimate",
    "capex_estimates": "/stock/capex-estimate",
    "fcf_estimates": "/stock/fcf-estimate",
    "stock_earnings": "/stock/earnings",
    "earnings_calendar": "/calendar/earnings",
    "live_quote": "/quote",
    "historical_ohlcv": "/stock/candle",
    "splits": "/stock/split",
    "earnings_quality": "/stock/earnings-quality-score",
    "revenue_breakdown": "/stock/revenue-breakdown2",
    "quote_us": "/quote/us",
}


ENTERPRISE_DISPLAY_MATRIX = {
    capability: EnterpriseDisplayAuthority(capability, endpoint)
    for capability, endpoint in _COVERED.items()
}


def display_authority(capability: str) -> EnterpriseDisplayAuthority | None:
    """Return signed-contract authority or ``None`` for fail-closed data."""
    return ENTERPRISE_DISPLAY_MATRIX.get(str(capability))


__all__ = [
    "CONTRACT_ID", "ENTERPRISE_DISPLAY_MATRIX", "EnterpriseDisplayAuthority",
    "MARKET_SCOPE", "display_authority",
]
