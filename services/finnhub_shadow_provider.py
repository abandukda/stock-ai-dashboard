"""Finnhub Core adapter for demo/shadow migration validation only.

No object returned here is certified or connected to production acquisition.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from typing import Any, Callable, Mapping, Sequence

import requests

from services.finnhub_financial_normalization import (
    canonical_financial_facts as _canonical_financial_facts,
    canonical_period as _canonical_period,
    currency_from_facts as _currency_from_facts,
)

from services.provider_domain_contracts import (
    CertificationStatus, DatasetFamily, GovernedRecord, MarketCoverageClass,
    ProvenanceEnvelope, UsePermission,
)


FINNHUB_ADAPTER_VERSION = "FINNHUB_SHADOW_ADAPTER_V1"
FINNHUB_BASE_URL = "https://finnhub.io/api/v1"
FINNHUB_DEMO_LICENSE = "DEMO_MIGRATION_VALIDATION_ONLY"
FINNHUB_FINANCIAL_NORMALIZATION_VERSION = "FINNHUB_FINANCIAL_NORMALIZATION_V2"


@dataclass(frozen=True)
class FinnhubEndpoint:
    capability: str
    path: str
    family: DatasetFamily
    source_family: str
    coverage: MarketCoverageClass = MarketCoverageClass.UNKNOWN


ENDPOINTS: tuple[FinnhubEndpoint, ...] = (
    FinnhubEndpoint("company_profile", "/stock/profile2", DatasetFamily.CONTEXTUAL_EXTERNAL_EVIDENCE, "COMPANY_PROFILE"),
    FinnhubEndpoint("financial_statements", "/stock/financials-reported", DatasetFamily.CANONICAL_QUANTITATIVE, "FINANCIAL_STATEMENTS"),
    FinnhubEndpoint("basic_financials", "/stock/metric", DatasetFamily.CANONICAL_QUANTITATIVE, "BASIC_FINANCIALS"),
    FinnhubEndpoint("dividends", "/stock/dividend2", DatasetFamily.CANONICAL_QUANTITATIVE, "DIVIDENDS"),
    FinnhubEndpoint("peers", "/stock/peers", DatasetFamily.CONTEXTUAL_EXTERNAL_EVIDENCE, "PEERS"),
    FinnhubEndpoint("ownership", "/stock/ownership", DatasetFamily.CONTEXTUAL_EXTERNAL_EVIDENCE, "OWNERSHIP"),
    FinnhubEndpoint("insider_transactions", "/stock/insider-transactions", DatasetFamily.CONTEXTUAL_EXTERNAL_EVIDENCE, "INSIDER_TRANSACTIONS"),
    FinnhubEndpoint("executives", "/stock/executive", DatasetFamily.CONTEXTUAL_EXTERNAL_EVIDENCE, "EXECUTIVES"),
    FinnhubEndpoint("company_news", "/company-news", DatasetFamily.CONTEXTUAL_EXTERNAL_EVIDENCE, "COMPANY_NEWS"),
    FinnhubEndpoint("sec_filings", "/stock/filings", DatasetFamily.CONTEXTUAL_EXTERNAL_EVIDENCE, "SEC_FILINGS"),
    FinnhubEndpoint("revenue_breakdown", "/stock/revenue-breakdown", DatasetFamily.CONTEXTUAL_EXTERNAL_EVIDENCE, "REVENUE_KPI_CONTEXT"),
    FinnhubEndpoint("recommendations", "/stock/recommendation", DatasetFamily.CONTEXTUAL_EXTERNAL_EVIDENCE, "ANALYST_RECOMMENDATIONS"),
    FinnhubEndpoint("price_targets", "/stock/price-target", DatasetFamily.CONTEXTUAL_EXTERNAL_EVIDENCE, "ANALYST_PRICE_TARGETS"),
    FinnhubEndpoint("analyst_actions", "/stock/upgrade-downgrade", DatasetFamily.CONTEXTUAL_EXTERNAL_EVIDENCE, "ANALYST_ACTIONS"),
    FinnhubEndpoint("eps_estimates", "/stock/eps-estimate", DatasetFamily.CONTEXTUAL_EXTERNAL_EVIDENCE, "EPS_ESTIMATES"),
    FinnhubEndpoint("revenue_estimates", "/stock/revenue-estimate", DatasetFamily.CONTEXTUAL_EXTERNAL_EVIDENCE, "REVENUE_ESTIMATES"),
    FinnhubEndpoint("ebitda_estimates", "/stock/ebitda-estimate", DatasetFamily.CONTEXTUAL_EXTERNAL_EVIDENCE, "EBITDA_ESTIMATES"),
    FinnhubEndpoint("ebit_estimates", "/stock/ebit-estimate", DatasetFamily.CONTEXTUAL_EXTERNAL_EVIDENCE, "EBIT_ESTIMATES"),
    FinnhubEndpoint("earnings_calendar", "/calendar/earnings", DatasetFamily.CONTEXTUAL_EXTERNAL_EVIDENCE, "EARNINGS_CALENDAR"),
    FinnhubEndpoint("historical_ohlcv", "/stock/candle", DatasetFamily.CANONICAL_QUANTITATIVE, "HISTORICAL_OHLCV", MarketCoverageClass.FULL_CONSOLIDATED),
    FinnhubEndpoint("live_quote", "/quote", DatasetFamily.LIVE_DISPLAY_ONLY, "LIVE_QUOTE", MarketCoverageClass.PARTIAL_REALTIME),
    FinnhubEndpoint("splits", "/stock/split", DatasetFamily.CANONICAL_QUANTITATIVE, "SPLITS"),
)
ENDPOINT_BY_CAPABILITY = {item.capability: item for item in ENDPOINTS}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _source_timestamp(payload: Any) -> str | None:
    if isinstance(payload, Mapping):
        for key in ("datetime", "date", "period", "from", "to", "lastUpdated"):
            if payload.get(key) not in (None, ""):
                return str(payload[key])
    return None


class FinnhubShadowAdapter:
    """Explicit shadow client; never selected by canonical production paths."""

    def __init__(
        self, api_key: str | None = None, *,
        get: Callable[..., Any] = requests.get,
        base_url: str = FINNHUB_BASE_URL,
        timeout_seconds: float = 15.0,
    ) -> None:
        self._api_key = str(api_key if api_key is not None else os.getenv("FINNHUB_API_KEY", "")).strip()
        self._get = get
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    def fetch(self, capability: str, symbol: str, **parameters: Any) -> GovernedRecord:
        endpoint = ENDPOINT_BY_CAPABILITY[capability]
        ticker = str(symbol).upper().strip()
        captured = _now()
        if not self._api_key:
            return self._unavailable(endpoint, ticker, captured, CertificationStatus.DATA_UNAVAILABLE, "FINNHUB_API_KEY is not configured")
        if capability == "splits":
            today = datetime.now(timezone.utc).date()
            parameters = {
                "from": (today - timedelta(days=365 * 15)).isoformat(),
                "to": today.isoformat(),
                **parameters,
            }
        params = {"symbol": ticker, **parameters, "token": self._api_key}
        try:
            response = self._get(f"{self._base_url}{endpoint.path}", params=params, timeout=self._timeout)
            status = int(getattr(response, "status_code", 0) or 0)
            payload = response.json() if status == 200 else {}
        except Exception as exc:
            return self._unavailable(endpoint, ticker, captured, CertificationStatus.DATA_UNAVAILABLE, type(exc).__name__)
        if status in {401, 403}:
            return self._unavailable(endpoint, ticker, captured, CertificationStatus.ENTITLEMENT_UNAVAILABLE, f"HTTP_{status}")
        if status != 200:
            return self._unavailable(endpoint, ticker, captured, CertificationStatus.DATA_UNAVAILABLE, f"HTTP_{status or 'UNKNOWN'}")
        if isinstance(payload, Mapping) and payload.get("error"):
            reason = str(payload.get("error"))[:160]
            entitlement = any(token in reason.lower() for token in ("premium", "permission", "entitlement", "access"))
            return self._unavailable(endpoint, ticker, captured,
                                     CertificationStatus.ENTITLEMENT_UNAVAILABLE if entitlement else CertificationStatus.DATA_UNAVAILABLE,
                                     f"PROVIDER_ERROR:{reason}")
        evidence_hash = _hash(payload)
        normalized = self._normalize(capability, payload)
        temporal = _normalized_temporal_metadata(normalized)
        provenance = ProvenanceEnvelope(
            provider="FINNHUB",
            dataset_family=endpoint.family,
            endpoint_or_source_family=endpoint.source_family,
            symbol=ticker,
            canonical_security_id=ticker,
            source_timestamp=_source_timestamp(payload) or temporal["source_timestamp"],
            capture_timestamp=captured,
            effective_period=temporal["effective_period"], fiscal_period=temporal["fiscal_period"],
            raw_evidence_id=f"FINNHUB:{endpoint.source_family}:{ticker}:{evidence_hash[:20]}",
            content_hash=evidence_hash,
            freshness_status="CAPTURED",
            certification_status=CertificationStatus.UNVERIFIED_SHADOW,
            license_class=FINNHUB_DEMO_LICENSE,
            display_permission=UsePermission.PROHIBITED,
            derived_use_permission=UsePermission.SHADOW_ONLY,
            market_coverage_class=endpoint.coverage,
            venue_coverage_description=(
                "Partial U.S. real-time venue coverage; display-only if separately licensed."
                if endpoint.coverage == MarketCoverageClass.PARTIAL_REALTIME
                else "Provider states historical/end-of-day OHLCV is consolidated."
                if endpoint.coverage == MarketCoverageClass.FULL_CONSOLIDATED else None
            ),
            estimated_volume_coverage_pct=(75.0 if endpoint.coverage == MarketCoverageClass.PARTIAL_REALTIME else None),
            coverage_as_of=captured,
            provider_statement_reference="ATLAS_FINNHUB_COVERAGE_STATEMENT_2026_09",
            adapter_version=FINNHUB_ADAPTER_VERSION,
            source_record_version=temporal["source_record_version"],
        )
        return GovernedRecord(provenance, normalized, ("Shadow/demo evidence; not authorized for ATLAS decisions.",))

    def entitlement_diagnostics(self, symbol: str, capabilities: Sequence[str] | None = None) -> dict[str, Any]:
        selected = tuple(capabilities or ENDPOINT_BY_CAPABILITY)
        results = {name: self.fetch(name, symbol).as_dict() for name in selected}
        return {
            "version": "FINNHUB_DEMO_ENTITLEMENT_DIAGNOSTICS_V1",
            "provider": "FINNHUB",
            "mode": "SHADOW_DEMO_MIGRATION_VALIDATION",
            "symbol": symbol.upper(),
            "credential_available": bool(self._api_key),
            "capabilities": {
                name: item["provenance"]["certification_status"] for name, item in results.items()
            },
            "records": results,
        }

    @staticmethod
    def _normalize(capability: str, payload: Any) -> Mapping[str, Any]:
        def records(value: Any) -> list[Mapping[str, Any]]:
            if isinstance(value, list):
                return [item for item in value if isinstance(item, Mapping)]
            if isinstance(value, Mapping):
                for key in ("data", "ownership", "transactions", "estimate", "earningsCalendar"):
                    if isinstance(value.get(key), list):
                        return [item for item in value[key] if isinstance(item, Mapping)]
            return []

        def pick(item: Mapping[str, Any], *names: str) -> Any:
            return next((item.get(name) for name in names if item.get(name) not in (None, "")), None)

        if capability == "live_quote" and isinstance(payload, Mapping):
            return {"price": payload.get("c"), "open": payload.get("o"), "high": payload.get("h"),
                    "low": payload.get("l"), "previous_close": payload.get("pc"), "provider_timestamp": payload.get("t")}
        if capability == "historical_ohlcv" and isinstance(payload, Mapping):
            columns = {"timestamps": payload.get("t") or [], "open": payload.get("o") or [],
                       "high": payload.get("h") or [], "low": payload.get("l") or [],
                       "close": payload.get("c") or [], "volume": payload.get("v") or [],
                       "adjustment_mode": "PROVIDER_REPORTED_UNRESOLVED"}
            return columns
        if capability == "company_profile" and isinstance(payload, Mapping):
            return {"name": payload.get("name"), "exchange": payload.get("exchange"),
                    "industry": payload.get("finnhubIndustry"), "country": payload.get("country"),
                    "currency": payload.get("currency"), "shares_outstanding_millions": payload.get("shareOutstanding")}
        if capability == "financial_statements" and isinstance(payload, Mapping):
            normalized_reports = []
            for report in records(payload):
                facts = []
                raw_report = report.get("report") if isinstance(report.get("report"), Mapping) else {}
                for statement, values in raw_report.items():
                    if not isinstance(values, list):
                        continue
                    for fact in values:
                        if isinstance(fact, Mapping):
                            facts.append({
                                "statement": statement, "concept": pick(fact, "concept", "label"),
                                "label": fact.get("label"), "unit": fact.get("unit"), "value": fact.get("value"),
                            })
                normalized_reports.append({
                    "fiscal_date": pick(report, "endDate", "filedDate", "year"),
                    "fiscal_period": _canonical_period(report), "source_period": report.get("quarter"),
                    "filing_form": report.get("form"), "filed_date": report.get("filedDate"),
                    "currency": report.get("currency") or _currency_from_facts(facts),
                    "access_number": report.get("accessNumber"), "facts": facts,
                    "canonical_facts": _canonical_financial_facts(facts, report),
                    "normalization_version": FINNHUB_FINANCIAL_NORMALIZATION_VERSION,
                })
            return {"reports": normalized_reports}
        if capability == "basic_financials" and isinstance(payload, Mapping):
            metric = payload.get("metric") if isinstance(payload.get("metric"), Mapping) else {}
            series = payload.get("series") if isinstance(payload.get("series"), Mapping) else {}
            raw_market_cap = pick(metric, "marketCapitalization")
            raw_shares = pick(metric, "shareOutstanding")
            return {
                "metric_type": payload.get("metricType"),
                "market_capitalization": _millions_to_absolute(raw_market_cap),
                "market_capitalization_lineage": {
                    "source_field": "metric.marketCapitalization", "source_value": raw_market_cap,
                    "source_unit": "USD_MILLIONS", "normalized_unit": "USD",
                    "scale_transformation": "MULTIPLY_BY_1E6",
                },
                "shares_outstanding": _millions_to_absolute(raw_shares),
                "shares_outstanding_lineage": {
                    "source_field": "metric.shareOutstanding", "source_value": raw_shares,
                    "source_unit": "SHARES_MILLIONS", "normalized_unit": "SHARES",
                    "scale_transformation": "MULTIPLY_BY_1E6",
                },
                "pe_ttm": pick(metric, "peTTM"), "pb_annual": pick(metric, "pbAnnual"),
                "operating_margin_ttm": pick(metric, "operatingMarginTTM"),
                "revenue_growth_ttm_yoy": pick(metric, "revenueGrowthTTMYoy"),
                "price_metrics": {key: value for key, value in metric.items() if str(key).lower().startswith("52week")},
                "series": series,
            }
        if capability == "price_targets" and isinstance(payload, Mapping):
            return {"target_high": payload.get("targetHigh"), "target_low": payload.get("targetLow"),
                    "target_mean": payload.get("targetMean"), "target_median": payload.get("targetMedian"),
                    "last_updated": payload.get("lastUpdated")}
        if capability == "recommendations":
            return {"periods": [{"period": pick(item, "period"), "strong_buy": item.get("strongBuy"),
                                  "buy": item.get("buy"), "hold": item.get("hold"),
                                  "sell": item.get("sell"), "strong_sell": item.get("strongSell")}
                                 for item in records(payload)]}
        if capability == "analyst_actions":
            return {"actions": [{"date": pick(item, "gradeTime", "date"), "firm": pick(item, "company", "firm"),
                                  "from_grade": item.get("fromGrade"), "to_grade": item.get("toGrade"),
                                  "action": item.get("action")}
                                 for item in records(payload)]}
        if capability in {"eps_estimates", "revenue_estimates", "ebitda_estimates", "ebit_estimates"}:
            return {"estimates": [{"period": pick(item, "period", "date"), "frequency": item.get("freq"),
                                    "average": pick(item, "epsAvg", "revenueAvg", "ebitdaAvg", "ebitAvg", "avg"),
                                    "high": pick(item, "epsHigh", "revenueHigh", "ebitdaHigh", "ebitHigh", "high"),
                                    "low": pick(item, "epsLow", "revenueLow", "ebitdaLow", "ebitLow", "low"),
                                    "analyst_count": pick(item, "numberAnalysts", "analystCount")}
                                   for item in records(payload)]}
        if capability == "earnings_calendar":
            return {"events": [{"date": item.get("date"), "hour": item.get("hour"),
                                 "eps_actual": item.get("epsActual"), "eps_estimate": item.get("epsEstimate"),
                                 "revenue_actual": item.get("revenueActual"), "revenue_estimate": item.get("revenueEstimate")}
                                for item in records(payload)]}
        if capability == "company_news":
            return {"articles": [{"headline": item.get("headline"), "summary": item.get("summary"),
                                   "article_timestamp": item.get("datetime"), "article_publisher": item.get("source"),
                                   "article_url": item.get("url"), "category": item.get("category"), "provider_article_id": item.get("id")}
                                  for item in records(payload)]}
        if capability == "sec_filings":
            return {"filings": [{"filing_date": pick(item, "filedDate", "acceptedDate"), "report_date": item.get("reportDate"),
                                  "filing_type": item.get("form"), "access_number": item.get("accessNumber"),
                                  "filing_url": pick(item, "filingUrl", "reportUrl")}
                                 for item in records(payload)]}
        if capability == "ownership":
            return {"ownership_records": [{"period": item.get("reportDate"), "holder": pick(item, "name", "holder"),
                                            "shares": pick(item, "share", "shares"), "change": item.get("change")}
                                           for item in records(payload)]}
        if capability == "insider_transactions":
            return {"transactions": [{"date": pick(item, "transactionDate", "filingDate"), "insider": item.get("name"),
                                       "transaction_code": item.get("transactionCode"), "shares": item.get("share"),
                                       "price": item.get("transactionPrice"), "change": item.get("change")}
                                      for item in records(payload)]}
        if capability == "executives":
            return {"executives": [{"name": item.get("name"), "title": item.get("position"),
                                     "age": item.get("age"), "since": item.get("since")}
                                    for item in records(payload)]}
        if capability == "peers":
            return {"symbols": [str(item) for item in payload if isinstance(item, str)] if isinstance(payload, list) else []}
        if capability == "revenue_breakdown":
            return {"breakdowns": [{"period": pick(item, "period", "date"), "data": item.get("data") or item.get("breakdown") or {}}
                                    for item in records(payload)]}
        if capability in {"dividends", "splits"}:
            return {"corporate_actions": [{"date": pick(item, "date", "exDate", "payDate"),
                                            "amount": pick(item, "amount", "dividend"),
                                            "split_from": item.get("fromFactor"), "split_to": item.get("toFactor")}
                                           for item in records(payload)]}
        raise ValueError(f"normalizer missing for capability {capability}")

    @staticmethod
    def _unavailable(endpoint: FinnhubEndpoint, ticker: str, captured: str,
                     status: CertificationStatus, reason: str) -> GovernedRecord:
        digest = _hash({"endpoint": endpoint.source_family, "symbol": ticker, "status": status.value, "reason": reason})
        return GovernedRecord(ProvenanceEnvelope(
            provider="FINNHUB", dataset_family=endpoint.family,
            endpoint_or_source_family=endpoint.source_family, symbol=ticker,
            canonical_security_id=ticker, capture_timestamp=captured,
            raw_evidence_id=f"FINNHUB:{endpoint.source_family}:{ticker}:{digest[:20]}",
            freshness_status="UNAVAILABLE", certification_status=status,
            license_class=FINNHUB_DEMO_LICENSE, display_permission=UsePermission.PROHIBITED,
            derived_use_permission=UsePermission.SHADOW_ONLY,
            market_coverage_class=endpoint.coverage, adapter_version=FINNHUB_ADAPTER_VERSION,
        ), {"status": status.value, "reason": reason}, ("No fallback or zero substitution was used.",))


__all__ = ["ENDPOINTS", "ENDPOINT_BY_CAPABILITY", "FINNHUB_ADAPTER_VERSION", "FINNHUB_FINANCIAL_NORMALIZATION_VERSION", "FinnhubShadowAdapter"]


def _normalized_temporal_metadata(payload: Mapping[str, Any]) -> dict[str, str | None]:
    reports = payload.get("reports") if isinstance(payload.get("reports"), list) else []
    report = reports[0] if reports and isinstance(reports[0], Mapping) else {}
    actions = payload.get("corporate_actions") if isinstance(payload.get("corporate_actions"), list) else []
    action = actions[0] if actions and isinstance(actions[0], Mapping) else {}
    timestamp = report.get("filed_date") or report.get("fiscal_date") or action.get("date")
    return {
        "source_timestamp": str(timestamp) if timestamp else None,
        "effective_period": str(report.get("fiscal_date")) if report.get("fiscal_date") else None,
        "fiscal_period": str(report.get("fiscal_period")) if report.get("fiscal_period") else None,
        "source_record_version": str(report.get("access_number")) if report.get("access_number") else None,
    }


def _millions_to_absolute(value: Any) -> float | None:
    try:
        return float(value) * 1_000_000
    except (TypeError, ValueError):
        return None
