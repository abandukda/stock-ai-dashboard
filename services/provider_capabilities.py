"""Small, family-specific provider capability protocols."""
from __future__ import annotations

from typing import Protocol, Sequence

from services.provider_domain_contracts import GovernedRecord


class MarketHistoryProvider(Protocol):
    def market_history(self, symbol: str, *, start: str | None = None, end: str | None = None) -> GovernedRecord: ...


class LiveQuoteProvider(Protocol):
    def live_quote(self, symbol: str) -> GovernedRecord: ...


class FinancialStatementProvider(Protocol):
    def financial_statements(self, symbol: str, *, frequency: str = "annual") -> GovernedRecord: ...


class FundamentalsProvider(Protocol):
    def fundamentals(self, symbol: str) -> GovernedRecord: ...


class CorporateActionsProvider(Protocol):
    def corporate_actions(self, symbol: str) -> Sequence[GovernedRecord]: ...


class AnalystContextProvider(Protocol):
    def analyst_context(self, symbol: str) -> Sequence[GovernedRecord]: ...


class OwnershipProvider(Protocol):
    def ownership_context(self, symbol: str) -> Sequence[GovernedRecord]: ...


class InsiderProvider(Protocol):
    def insider_context(self, symbol: str) -> Sequence[GovernedRecord]: ...


class NewsProvider(Protocol):
    def company_news(self, symbol: str, *, start: str, end: str) -> Sequence[GovernedRecord]: ...


class RegulatoryFilingProvider(Protocol):
    def filings(self, symbol: str) -> Sequence[GovernedRecord]: ...


class TranscriptProvider(Protocol):
    def transcript(self, symbol: str, *, year: int, quarter: int) -> GovernedRecord: ...


__all__ = [name for name in globals() if name.endswith("Provider")]
