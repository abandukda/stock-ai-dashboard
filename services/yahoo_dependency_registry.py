"""Governance inventory for Yahoo dependencies during the FMP-first migration.

Nothing in this module imports Yahoo, calls a provider, or selects runtime data.
The registry is an explicit migration-debt ledger and an architecture-test
baseline.  Future phases must remove or update entries as dependencies retire.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


YAHOO_DEPENDENCY_REGISTRY_VERSION: Final = "YAHOO_DEPENDENCY_REGISTRY_V1"

ACTIVE_PRIMARY: Final = "ACTIVE_PRIMARY"
ACTIVE_FALLBACK: Final = "ACTIVE_FALLBACK"
LEGACY_APP_HELPER: Final = "LEGACY_APP_HELPER"
OFFLINE_RESEARCH: Final = "OFFLINE_RESEARCH"
BACKUP_ONLY: Final = "BACKUP_ONLY"
LEGACY_PENDING_REMOVAL: Final = "LEGACY_PENDING_REMOVAL"

ACTIVE_STATUSES: Final = frozenset({ACTIVE_PRIMARY, ACTIVE_FALLBACK})
LEGACY_STATUSES: Final = frozenset({LEGACY_APP_HELPER, OFFLINE_RESEARCH, BACKUP_ONLY, LEGACY_PENDING_REMOVAL})
SUPPORTED_DEPENDENCY_STATUSES: Final = ACTIVE_STATUSES | LEGACY_STATUSES


@dataclass(frozen=True)
class YahooDependency:
    stable_id: str
    file: str
    function: str
    data_family: str
    production_purpose: tuple[str, ...]
    intended_replacement: tuple[str, ...]
    migration_phase: str
    current_status: str
    retirement_gate: str
    source_markers: tuple[str, ...]


def _dependency(
    stable_id: str,
    file: str,
    function: str,
    data_family: str,
    production_purpose: tuple[str, ...],
    intended_replacement: tuple[str, ...],
    migration_phase: str,
    current_status: str,
    retirement_gate: str,
    source_markers: tuple[str, ...],
) -> YahooDependency:
    return YahooDependency(
        stable_id=stable_id,
        file=file,
        function=function,
        data_family=data_family,
        production_purpose=production_purpose,
        intended_replacement=intended_replacement,
        migration_phase=migration_phase,
        current_status=current_status,
        retirement_gate=retirement_gate,
        source_markers=source_markers,
    )


YAHOO_DEPENDENCIES: Final[tuple[YahooDependency, ...]] = (
    _dependency("YAHOO_SCANNER_UNIVERSE", "overnight_market_scan.py", "get_yahoo_screeners", "UNIVERSE_SCREENERS", ("UNIVERSE",), ("FMP_REFERENCE_UNIVERSE",), "FMP-FIRST.8", ACTIVE_PRIMARY, "UNIVERSE_COVERAGE_AND_ELIGIBILITY_REPLAY", ("yf.screen(",)),
    _dependency("YAHOO_SCANNER_DAILY_OHLCV", "overnight_market_scan.py", "download_price_batch", "HISTORICAL_DAILY_OHLCV", ("SCANNER_TECHNICALS", "PRESCREEN"), ("FMP_EOD_BULK", "LICENSED_MARKET_DATA_PROVIDER"), "FMP-FIRST.9", ACTIVE_PRIMARY, "OHLCV_CORPORATE_ACTION_AND_INDICATOR_REPLAY", ("yf.download(",)),
    _dependency("YAHOO_SCANNER_METADATA", "overnight_market_scan.py", "get_metadata", "PROFILE_SCORING_VALUATION_METADATA", ("EXCLUSIONS", "PRESCREEN", "SCORING", "VALUATION", "ETF_ROUTING"), ("profile-bulk", "income-statement", "analyst-estimates", "grades-consensus", "price-target-consensus"), "FMP-FIRST.8", ACTIVE_PRIMARY, "EXACT_EXCLUSION_PRESCREEN_RANK_AND_INVESTMENT_REPLAY", ("yf.Ticker(symbol)", "ticker.get_info()")),
    _dependency("YAHOO_SCANNER_ETF_FUNDS", "overnight_market_scan.py", "get_etf_research", "ETF_HOLDINGS_ALLOCATIONS", ("ETF_RESEARCH",), ("FMP_ETF_PROFILE", "FMP_ETF_HOLDINGS", "FMP_ETF_ALLOCATIONS"), "FMP-FIRST.7", ACTIVE_PRIMARY, "ETF_SCHEMA_COVERAGE_AND_UI_QA", ("yf.Ticker(cache_key).funds_data",)),
    _dependency("YAHOO_CANONICAL_MARKET_HISTORY", "engines/canonical_market_data.py", "_fetch_yahoo_history", "HISTORICAL_DAILY_OHLCV", ("RESEARCH_CHART", "TECHNICAL_CONTEXT"), ("FMP_EOD", "LICENSED_MARKET_DATA_PROVIDER"), "FMP-FIRST.9", ACTIVE_PRIMARY, "ADJUSTMENT_SESSION_AND_INDICATOR_REPLAY", ("yf.download(", "yf.Ticker(ticker).history(")),
    _dependency("YAHOO_HOME_MARKET_TAPE", "ui/home_v104.py", "_home_market_tape", "INTRADAY_MARKET_TAPE", ("HOME_PRESENTATION",), ("LICENSED_MARKET_DATA_PROVIDER",), "FMP-FIRST.10", ACTIVE_PRIMARY, "LICENSED_FEED_RUNTIME_QA", ("import yfinance as yf", "fetch_home_market_tape(yf.download)")),
    _dependency("YAHOO_EXPLICIT_RESEARCH_HISTORY", "engines/live_research_engine.py", "_download_history", "HISTORICAL_DAILY_OHLCV", ("EXPLICIT_RESEARCH_CHART", "TECHNICALS"), ("CANONICAL_MARKET_DATA_SERVICE",), "FMP-FIRST.2", ACTIVE_PRIMARY, "RESEARCH_CONTEXT_AND_HISTORY_REPLAY", ("yf.download(", "yf.Ticker(ticker).history(")),
    _dependency("YAHOO_EXPLICIT_RESEARCH_ROW", "engines/live_research_engine.py", "build_live_research", "MIXED_RESEARCH_ROW", ("LEGACY_UI_COMPATIBILITY",), ("RESEARCH_CONTEXT_V1", "FMP_RESEARCH_ACQUISITION"), "FMP-FIRST.3", LEGACY_PENDING_REMOVAL, "REMOVE_AFTER_CANONICAL_UI_RUNTIME_QA", ("tk = yf.Ticker(symbol)", "info = tk.get_info()")),
    _dependency("YAHOO_EXPLICIT_RESEARCH_ACTIONS", "engines/live_research_engine.py", "fetch_analyst_action_history", "ANALYST_FIRM_ACTIONS", ("LEGACY_UI_COMPATIBILITY",), ("FMP_GRADES", "TOP_ANALYST_ACTIONS_V1"), "FMP-FIRST.3", LEGACY_PENDING_REMOVAL, "REMOVE_AFTER_TOP_ANALYST_ACTIONS_UI_QA", ("tk.upgrades_downgrades",)),
    _dependency("YAHOO_RESEARCH_PRICE_FALLBACK", "app.py", "build_price_only_live_row", "RECENT_DAILY_PRICE", ("RESEARCH_ERROR_FALLBACK",), ("CANONICAL_MARKET_DATA_SERVICE",), "FMP-FIRST.2", ACTIVE_FALLBACK, "RESEARCH_FAILURE_AND_STALE_FALLBACK_QA", ("yf.download(",)),

    # Legacy helpers remain callable in the monolithic application even where
    # later definitions currently shadow their original consumers.
    _dependency("YAHOO_LEGACY_CHART_HISTORY", "app.py", "fetch_chart_history", "HISTORICAL_OHLCV", ("LEGACY_CHART",), ("CANONICAL_MARKET_DATA_SERVICE",), "FMP-FIRST.10", LEGACY_APP_HELPER, "ACTIVE_CONSUMER_REMOVAL", ("yf.download(",)),
    _dependency("YAHOO_LEGACY_CHART_HISTORY_FIXED", "app.py", "fetch_chart_history_fixed", "HISTORICAL_OHLCV", ("LEGACY_CHART",), ("CANONICAL_MARKET_DATA_SERVICE",), "FMP-FIRST.10", LEGACY_APP_HELPER, "ACTIVE_CONSUMER_REMOVAL", ("yf.download(",)),
    _dependency("YAHOO_LEGACY_CHART_HISTORY_FORCE", "app.py", "fetch_chart_history_force_chart", "HISTORICAL_OHLCV", ("LEGACY_CHART",), ("CANONICAL_MARKET_DATA_SERVICE",), "FMP-FIRST.10", LEGACY_APP_HELPER, "ACTIVE_CONSUMER_REMOVAL", ("yf.download(",)),
    _dependency("YAHOO_LEGACY_DETAIL_CHART", "app.py", "fetch_detail_chart_history_v4184", "HISTORICAL_OHLCV", ("LEGACY_DETAIL_CHART",), ("CANONICAL_MARKET_DATA_SERVICE",), "FMP-FIRST.10", LEGACY_APP_HELPER, "ACTIVE_CONSUMER_REMOVAL", ("yf.download(",)),
    _dependency("YAHOO_LEGACY_RESEARCH_ROW", "app.py", "build_legacy_live_research_row", "MIXED_RESEARCH_ROW", ("LEGACY_RESEARCH",), ("RESEARCH_CONTEXT_V1",), "FMP-FIRST.2", LEGACY_APP_HELPER, "RESEARCH_CONTEXT_ACTIVATION", ("yf.Ticker(ticker)", "yf.download(")),
    _dependency("YAHOO_LEGACY_QUOTE", "app.py", "v4242_yahoo_quote", "QUOTE_PROFILE", ("LEGACY_QUOTE",), ("LICENSED_MARKET_DATA_PROVIDER", "FMP_PROFILE"), "FMP-FIRST.10", LEGACY_APP_HELPER, "ACTIVE_CONSUMER_REMOVAL", ("yf.Ticker(yf_symbol)",)),
    _dependency("YAHOO_LEGACY_CHART_LEVELS", "app.py", "v4244_chart_levels_from_history", "HISTORICAL_OHLCV", ("LEGACY_TECHNICAL_LEVELS",), ("CANONICAL_MARKET_DATA_SERVICE",), "FMP-FIRST.9", LEGACY_APP_HELPER, "INDICATOR_REPLAY", ("yf.download(",)),
    _dependency("YAHOO_LEGACY_INFO_V451", "app.py", "v451_yahoo_info", "PROFILE_METADATA", ("LEGACY_RESEARCH",), ("FMP_PROFILE",), "FMP-FIRST.10", LEGACY_APP_HELPER, "ACTIVE_CONSUMER_REMOVAL", ("yf.Ticker(t)",)),
    _dependency("YAHOO_LEGACY_INFO_V502", "app.py", "v502_yahoo_info", "PROFILE_METADATA", ("LEGACY_RESEARCH",), ("FMP_PROFILE",), "FMP-FIRST.10", LEGACY_APP_HELPER, "ACTIVE_CONSUMER_REMOVAL", ("yf.Ticker(ticker).info",)),
    _dependency("YAHOO_LEGACY_CURRENT_PRICE", "app.py", "v507_current_price_lookup", "RECENT_DAILY_PRICE", ("LEGACY_PORTFOLIO",), ("LICENSED_MARKET_DATA_PROVIDER",), "FMP-FIRST.10", LEGACY_APP_HELPER, "ACTIVE_CONSUMER_REMOVAL", ("yf.download(",)),
    _dependency("YAHOO_LEGACY_STATEMENTS", "app.py", "v5071a_yahoo_statement_bundle", "FINANCIAL_STATEMENTS", ("LEGACY_RESEARCH",), ("FMP_FINANCIAL_STATEMENTS",), "FMP-FIRST.3", LEGACY_APP_HELPER, "FMP_RESEARCH_CONTEXT_QA", ("yf.Ticker(ticker)",)),
    _dependency("YAHOO_LEGACY_MARKET_TAPE_V72", "app.py", "v72_fetch_market_tape", "MARKET_TAPE", ("LEGACY_HOME",), ("LICENSED_MARKET_DATA_PROVIDER",), "FMP-FIRST.10", LEGACY_APP_HELPER, "ACTIVE_CONSUMER_REMOVAL", ("yf.download(",)),
    _dependency("YAHOO_LEGACY_MARKET_QUOTE_V74", "app.py", "v74_market_quote", "MARKET_TAPE", ("LEGACY_HOME",), ("LICENSED_MARKET_DATA_PROVIDER",), "FMP-FIRST.10", LEGACY_APP_HELPER, "ACTIVE_CONSUMER_REMOVAL", ("yf.Ticker(symbol).history(",)),
    _dependency("YAHOO_LEGACY_EARNINGS_CALENDAR", "app.py", "v426_yahoo_calendar_earnings", "EARNINGS_CALENDAR", ("LEGACY_EARNINGS",), ("FMP_EARNINGS_CALENDAR",), "FMP-FIRST.3", LEGACY_APP_HELPER, "FMP_EARNINGS_QA", ("https://finance.yahoo.com/calendar/earnings",)),
    _dependency("YAHOO_LEGACY_MARKET_RSS_V432", "app.py", "v432_market_news_items", "MARKET_NEWS", ("LEGACY_NEWS",), ("FMP_NEWS",), "FMP-FIRST.3", LEGACY_APP_HELPER, "FMP_NEWS_LICENSE_AND_QA", ("https://finance.yahoo.com/news/rssindex",)),
    _dependency("YAHOO_LEGACY_COMPANY_RSS_V432", "app.py", "v432_company_news_items", "COMPANY_NEWS", ("LEGACY_NEWS",), ("FMP_NEWS_STOCK",), "FMP-FIRST.3", LEGACY_APP_HELPER, "FMP_NEWS_LICENSE_AND_QA", ("https://feeds.finance.yahoo.com/rss/2.0/headline",)),
    _dependency("YAHOO_LEGACY_MARKET_RSS_V44", "app.py", "v44_market_news_items", "MARKET_NEWS", ("LEGACY_NEWS",), ("FMP_NEWS",), "FMP-FIRST.3", LEGACY_APP_HELPER, "FMP_NEWS_LICENSE_AND_QA", ("https://finance.yahoo.com/news/rssindex",)),
    _dependency("YAHOO_LEGACY_COMPANY_RSS_V46", "app.py", "v46_news_intelligence", "COMPANY_NEWS", ("LEGACY_NEWS",), ("FMP_NEWS_STOCK",), "FMP-FIRST.3", LEGACY_APP_HELPER, "FMP_NEWS_LICENSE_AND_QA", ("https://feeds.finance.yahoo.com/rss/2.0/headline",)),
    _dependency("YAHOO_OFFLINE_PIT_HISTORY", "analysis/phase4a/build_point_in_time_panel.py", "download_adjusted_prices", "OFFLINE_HISTORICAL_OHLCV", ("OFFLINE_CALIBRATION",), ("FMP_EOD", "LICENSED_MARKET_DATA_PROVIDER"), "FMP-FIRST.9", OFFLINE_RESEARCH, "OFFLINE_REPLAY_MIGRATION", ("yf.download(",)),
    _dependency("YAHOO_STANDALONE_ANALYZER", "analyzer.py", "analyze_stock", "LEGACY_STANDALONE_RESEARCH", ("OFFLINE_TOOL",), ("RESEARCH_CONTEXT_V1",), "FMP-FIRST.10", OFFLINE_RESEARCH, "TOOL_DEPRECATION_OR_MIGRATION", ("yf.Ticker(ticker)",)),
    _dependency("YAHOO_APP_BACKUP_SNAPSHOT", "app_backup.py", "*", "BACKUP_SNAPSHOT", ("NON_RUNTIME_BACKUP",), (), "FMP-FIRST.10", BACKUP_ONLY, "ARCHIVE_OR_REMOVE_BACKUP", ("import yfinance as yf",)),
)


# Architecture-test baseline.  Adding a new importing source file requires an
# explicit registry review; tests and the historical backup are classified
# separately rather than treated as active production dependencies.
YFINANCE_IMPORT_ALLOWLIST: Final = frozenset({
    "analysis/phase4a/build_point_in_time_panel.py",
    "analyzer.py",
    "app.py",
    "app_backup.py",
    "engines/canonical_market_data.py",
    "engines/live_research_engine.py",
    "overnight_market_scan.py",
    "ui/home_v104.py",
})

YAHOO_URL_ALLOWLIST: Final = frozenset({
    ("app.py", "v426_yahoo_calendar_earnings", "https://finance.yahoo.com/calendar/earnings"),
    ("app.py", "v432_market_news_items", "https://finance.yahoo.com/news/rssindex"),
    ("app.py", "v432_company_news_items", "https://feeds.finance.yahoo.com/rss/2.0/headline"),
    ("app.py", "v44_market_news_items", "https://finance.yahoo.com/news/rssindex"),
    ("app.py", "v46_news_intelligence", "https://feeds.finance.yahoo.com/rss/2.0/headline"),
})

EXPECTED_YAHOO_DEPENDENCY_COUNT_V1: Final = 31


def yahoo_dependency_summary() -> tuple[YahooDependency, ...]:
    """Return immutable governance records; never select a provider value."""
    return YAHOO_DEPENDENCIES


def yahoo_migration_metrics() -> dict[str, int]:
    active = sum(item.current_status in ACTIVE_STATUSES for item in YAHOO_DEPENDENCIES)
    primary = sum(item.current_status == ACTIVE_PRIMARY for item in YAHOO_DEPENDENCIES)
    fallback = sum(item.current_status == ACTIVE_FALLBACK for item in YAHOO_DEPENDENCIES)
    legacy = sum(item.current_status in LEGACY_STATUSES for item in YAHOO_DEPENDENCIES)
    return {
        "total_registered_yahoo_dependencies": len(YAHOO_DEPENDENCIES),
        "active_yahoo_dependencies": active,
        "active_production_yahoo_dependencies": primary + fallback,
        "active_primary_yahoo_dependencies": primary,
        "active_fallback_yahoo_dependencies": fallback,
        "legacy_yahoo_dependencies": legacy,
    }


__all__ = [
    "ACTIVE_FALLBACK", "ACTIVE_PRIMARY", "ACTIVE_STATUSES", "BACKUP_ONLY",
    "EXPECTED_YAHOO_DEPENDENCY_COUNT_V1", "LEGACY_APP_HELPER", "LEGACY_PENDING_REMOVAL", "LEGACY_STATUSES",
    "OFFLINE_RESEARCH", "SUPPORTED_DEPENDENCY_STATUSES", "YAHOO_DEPENDENCIES",
    "YAHOO_DEPENDENCY_REGISTRY_VERSION", "YAHOO_URL_ALLOWLIST",
    "YFINANCE_IMPORT_ALLOWLIST", "YahooDependency", "yahoo_dependency_summary",
    "yahoo_migration_metrics",
]
