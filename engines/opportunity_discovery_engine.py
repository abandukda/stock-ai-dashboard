"""
Atlas V95 — Opportunity Discovery Engine

New file: engines/opportunity_discovery_engine.py

This is a read-only discovery layer. It ranks fresh opportunities for full
research, but never assigns Buy Now / Accumulate / Monitor / Avoid.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Sequence
import math
import re

MISSING_STRINGS = {"", "n/a", "na", "none", "null", "nan", "unavailable", "under review", "not available", "not reported", "-", "—"}
DEFAULT_EXCLUDED_SECTORS = {"financial services", "financials", "banks", "banking", "insurance", "entertainment", "gambling", "casinos", "alcohol", "beverages - alcoholic"}
DEFAULT_EXCLUDED_KEYWORDS = {"casino", "sports betting", "gambling", "alcohol", "beer", "wine", "spirits", "entertainment", "bank", "banking", "insurance", "credit services"}
SIGNAL_WEIGHTS = {
    "earnings_surprise": 16.0, "guidance_raise": 15.0, "estimate_revision": 11.0,
    "fresh_catalyst": 10.0, "unusual_volume": 9.0, "technical_breakout": 9.0,
    "relative_strength": 8.0, "fundamental_acceleration": 10.0,
    "margin_expansion": 7.0, "free_cash_flow_improvement": 7.0,
    "valuation_dislocation": 9.0, "institutional_accumulation": 7.0,
    "insider_buying": 7.0, "political_support": 5.0, "macro_tailwind": 4.0,
    "recovery_signal": 6.0,
}
NEGATIVE_WEIGHTS = {
    "earnings_miss": -14.0, "guidance_cut": -16.0,
    "negative_estimate_revision": -10.0, "high_risk": -12.0,
    "overextended": -6.0, "weak_liquidity": -6.0,
    "negative_free_cash_flow": -8.0, "revenue_contraction": -8.0,
    "low_data_coverage": -10.0,
}

@dataclass(frozen=True)
class DiscoveryConfig:
    minimum_price: float = 20.0
    minimum_market_cap: float = 500_000_000.0
    minimum_average_volume: float = 250_000.0
    minimum_signal_score: float = 25.0
    minimum_data_coverage_pct: float = 35.0
    maximum_candidates: int = 40
    maximum_per_sector: int = 6
    include_price_buckets: bool = True
    exclude_israeli_companies: bool = True
    excluded_sectors: Sequence[str] = field(default_factory=lambda: tuple(sorted(DEFAULT_EXCLUDED_SECTORS)))
    excluded_keywords: Sequence[str] = field(default_factory=lambda: tuple(sorted(DEFAULT_EXCLUDED_KEYWORDS)))

def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return default if text.lower() in MISSING_STRINGS else text

def _num(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        number = float(value)
        return default if math.isnan(number) or math.isinf(number) else number
    text = str(value).replace(",", "").replace("$", "").replace("%", "").replace("x", "").strip()
    if text.lower() in MISSING_STRINGS:
        return default
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return default
    try:
        number = float(match.group(0))
        return default if math.isnan(number) or math.isinf(number) else number
    except ValueError:
        return default

def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in MISSING_STRINGS
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    try:
        return not math.isnan(float(value))
    except Exception:
        return True

def _first(row: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in row and _present(row.get(key)):
            return row.get(key)
    return default

def _normalize_rows(rows: Any) -> List[Mapping[str, Any]]:
    if rows is None:
        return []
    if hasattr(rows, "to_dict"):
        try:
            return list(rows.to_dict("records"))
        except Exception:
            pass
    if isinstance(rows, Mapping):
        for key in ("rows", "data", "results", "stocks"):
            value = rows.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, Mapping)]
        return [rows]
    if isinstance(rows, Iterable) and not isinstance(rows, (str, bytes, bytearray)):
        return [item for item in rows if isinstance(item, Mapping)]
    return []

def _ticker(row: Mapping[str, Any]) -> str:
    return _text(_first(row, "Ticker", "ticker", "symbol"), "UNKNOWN").upper()

def _company(row: Mapping[str, Any]) -> str:
    return _text(_first(row, "Company", "company", "Name", "longName", "shortName"), _ticker(row))

def _sector(row: Mapping[str, Any]) -> str:
    return _text(_first(row, "Sector", "sector", "Industry", "industry"), "Unknown")

def _country(row: Mapping[str, Any]) -> str:
    return _text(_first(row, "Country", "country", "country_of_origin", "domicile"), "Unknown")

def _price_bucket(price: float | None) -> str:
    if price is None: return "unknown"
    if price < 30: return "under_30"
    if price < 75: return "30_to_75"
    if price < 200: return "75_to_200"
    return "over_200"

def _contains_any(text: str, values: Iterable[str]) -> bool:
    lower = text.lower()
    return any(value.lower() in lower for value in values)

def _exclusion_reason(row: Mapping[str, Any], config: DiscoveryConfig) -> str | None:
    price = _num(_first(row, "Current Price", "Price", "price", "Close"))
    market_cap = _num(_first(row, "Market Cap", "market_cap", "marketCap"))
    avg_volume = _num(_first(row, "Average Volume", "average_volume", "averageVolume", "Avg Volume"))
    sector, industry, company, country = _sector(row), _text(_first(row, "Industry", "industry"), ""), _company(row), _country(row)
    description = _text(_first(row, "Business Summary", "description", "longBusinessSummary"), "")
    combined = " ".join([sector, industry, company, description])
    if price is None or price <= 0: return "missing_or_invalid_price"
    if price < config.minimum_price: return "below_minimum_price"
    if market_cap is not None and market_cap < config.minimum_market_cap: return "below_minimum_market_cap"
    if avg_volume is not None and avg_volume < config.minimum_average_volume: return "below_minimum_liquidity"
    if _contains_any(sector, config.excluded_sectors): return "excluded_sector"
    if _contains_any(combined, config.excluded_keywords): return "excluded_business_type"
    if config.exclude_israeli_companies:
        if country.lower() in {"israel", "israeli"}: return "excluded_country"
        if _text(_first(row, "Is Israeli", "is_israeli"), "").lower() in {"true", "yes", "1"}: return "excluded_country"
    return None

def _coverage_pct(row: Mapping[str, Any]) -> float:
    groups = {
        "price": ("Current Price", "Price", "price", "Close"),
        "market_cap": ("Market Cap", "market_cap", "marketCap"),
        "revenue_growth": ("Revenue Growth", "Revenue Growth %", "revenue_growth", "revenueGrowth"),
        "eps_growth": ("EPS Growth", "eps_growth", "earningsGrowth"),
        "margin": ("Operating Margin", "operating_margin", "operatingMargins"),
        "fcf": ("Free Cash Flow", "free_cash_flow", "freeCashflow"),
        "technicals": ("RSI", "rsi", "Technical Score", "technical_score"),
        "valuation": ("Atlas Fair Value", "atlas_fair_value", "Analyst Target", "targetMeanPrice"),
        "news": ("news_items", "latest_news", "news", "latest_news_headline"),
        "earnings": ("earnings_summary", "earnings_ai_summary", "guidance_summary", "management_guidance"),
        "institutional": ("institutional_summary", "institutional_activity", "smart_money"),
        "policy": ("political_support", "political_context", "policy_context"),
    }
    available = sum(_present(_first(row, *keys)) for keys in groups.values())
    return available / len(groups) * 100.0

def _discover_signals(row: Mapping[str, Any]) -> Dict[str, Any]:
    signals, negatives = [], []
    def add_signal(name: str, evidence: str, strength: float = 1.0) -> None:
        signals.append({"name": name, "weight": round(SIGNAL_WEIGHTS[name] * max(0.25, min(strength, 1.5)), 2), "evidence": evidence})
    def add_negative(name: str, evidence: str, strength: float = 1.0) -> None:
        negatives.append({"name": name, "weight": round(NEGATIVE_WEIGHTS[name] * max(0.25, min(strength, 1.5)), 2), "evidence": evidence})

    earnings_surprise = _num(_first(row, "EPS Surprise %", "earnings_surprise_pct", "eps_surprise_pct", "Earnings Surprise"))
    if earnings_surprise is not None:
        if earnings_surprise >= 5: add_signal("earnings_surprise", f"EPS beat expectations by approximately {earnings_surprise:.1f}%.", min(1.5, earnings_surprise / 15.0))
        elif earnings_surprise <= -5: add_negative("earnings_miss", f"EPS missed expectations by approximately {abs(earnings_surprise):.1f}%.", min(1.5, abs(earnings_surprise) / 15.0))

    guidance = _text(_first(row, "guidance_direction", "guidance_status", "Guidance", "management_guidance"), "").lower()
    if any(word in guidance for word in ("raise", "raised", "increase", "above")): add_signal("guidance_raise", "Management raised or improved forward guidance.")
    elif any(word in guidance for word in ("cut", "lowered", "reduced", "below")): add_negative("guidance_cut", "Management lowered forward guidance.")

    estimate_revision = _num(_first(row, "Estimate Revision %", "estimate_revision_pct", "analyst_revision_pct", "EPS Revision %"))
    if estimate_revision is not None:
        if estimate_revision >= 2: add_signal("estimate_revision", f"Analyst estimates improved by approximately {estimate_revision:.1f}%.", min(1.5, estimate_revision / 8.0))
        elif estimate_revision <= -2: add_negative("negative_estimate_revision", f"Analyst estimates declined by approximately {abs(estimate_revision):.1f}%.", min(1.5, abs(estimate_revision) / 8.0))

    if _present(_first(row, "latest_news_headline", "Top News", "news_items", "latest_news")): add_signal("fresh_catalyst", "A fresh verified company catalyst is available.")
    relative_volume = _num(_first(row, "Relative Volume", "relative_volume", "relativeVolume"))
    if relative_volume is not None and relative_volume >= 1.4: add_signal("unusual_volume", f"Relative volume is elevated at approximately {relative_volume:.2f}x.", min(1.5, relative_volume / 2.5))

    breakout = _text(_first(row, "Breakout", "technical_breakout", "breakout_status", "Technical Signal"), "").lower()
    if breakout in {"true", "yes", "1"} or any(p in breakout for p in ("breakout", "reclaim", "above resistance")): add_signal("technical_breakout", "Price action shows a confirmed breakout or reclaim.")

    rs_vs_spy = _num(_first(row, "Relative Strength vs SPY", "relative_strength_vs_spy", "rs_vs_spy"))
    if rs_vs_spy is not None and rs_vs_spy >= 3: add_signal("relative_strength", f"The stock is outperforming SPY by approximately {rs_vs_spy:.1f}%.", min(1.5, rs_vs_spy / 10.0))

    revenue = _num(_first(row, "Revenue Growth", "Revenue Growth %", "revenue_growth", "revenueGrowth"))
    prior_revenue = _num(_first(row, "Prior Revenue Growth", "prior_revenue_growth", "revenue_growth_prior"))
    if revenue is not None:
        if revenue >= 10 and (prior_revenue is None or revenue > prior_revenue): add_signal("fundamental_acceleration", f"Revenue growth is approximately {revenue:.1f}% and is improving.", min(1.5, max(revenue, revenue - (prior_revenue or 0)) / 25.0))
        elif revenue < 0: add_negative("revenue_contraction", f"Revenue is contracting by approximately {abs(revenue):.1f}%.", min(1.5, abs(revenue) / 20.0))

    margin = _num(_first(row, "Operating Margin", "operating_margin", "operatingMargins"))
    prior_margin = _num(_first(row, "Prior Operating Margin", "prior_operating_margin"))
    if margin is not None and prior_margin is not None and margin - prior_margin >= 1.0: add_signal("margin_expansion", f"Operating margin expanded by approximately {margin - prior_margin:.1f} points.", min(1.5, (margin - prior_margin) / 5.0))

    fcf = _num(_first(row, "Free Cash Flow", "free_cash_flow", "freeCashflow"))
    prior_fcf = _num(_first(row, "Prior Free Cash Flow", "prior_free_cash_flow"))
    if fcf is not None:
        if fcf > 0 and (prior_fcf is None or fcf > prior_fcf): add_signal("free_cash_flow_improvement", "Free cash flow is positive and improving.")
        elif fcf < 0: add_negative("negative_free_cash_flow", "Free cash flow is negative.")

    current = _num(_first(row, "Current Price", "Price", "price", "Close"))
    fair = _num(_first(row, "Atlas Fair Value", "atlas_fair_value", "fair_value"))
    if current and fair and current > 0:
        upside = ((fair - current) / current) * 100.0
        if upside >= 15: add_signal("valuation_dislocation", f"Atlas Fair Value implies approximately {upside:.1f}% upside.", min(1.5, upside / 40.0))

    institution = _text(_first(row, "institutional_activity", "institutional_summary", "smart_money"), "").lower()
    if any(p in institution for p in ("accumulation", "increased", "buying", "added", "inflow")): add_signal("institutional_accumulation", "Institutional evidence indicates accumulation or increasing ownership.")
    insider = _text(_first(row, "insider_activity", "insider_summary", "insider_signal"), "").lower()
    if any(p in insider for p in ("buy", "purchased", "accumulation")): add_signal("insider_buying", "Recent insider activity includes verified purchases.")
    policy = _text(_first(row, "political_support", "political_context", "policy_context", "political_support_summary"), "").lower()
    if any(p in policy for p in ("support", "benefit", "tailwind", "funding", "incentive", "subsidy", "contract")): add_signal("political_support", "Verified policy or government support strengthens the setup.")
    macro = _text(_first(row, "macro_tailwind", "macro_context", "sector_tailwind"), "").lower()
    if any(p in macro for p in ("tailwind", "benefit", "favorable", "improving")): add_signal("macro_tailwind", "Macro or sector conditions provide a favorable tailwind.")
    recovery = _text(_first(row, "Recovery Signal", "recovery_signal", "recovery_status"), "").lower()
    if recovery in {"true", "yes", "1"} or "recovery" in recovery: add_signal("recovery_signal", "The stock shows a verified recovery or reversal signal.")

    risk = _text(_first(row, "Risk Level", "risk_level"), "").lower()
    if risk == "high": add_negative("high_risk", "Risk classification is high.")
    rsi = _num(_first(row, "RSI", "rsi"))
    if rsi is not None and rsi >= 75: add_negative("overextended", f"RSI of {rsi:.0f} indicates an overextended setup.")
    current_ratio = _num(_first(row, "Current Ratio", "current_ratio", "currentRatio"))
    if current_ratio is not None and 0 < current_ratio < 0.8: add_negative("weak_liquidity", f"Current ratio of {current_ratio:.2f} indicates weak short-term liquidity.")

    return {"signals": signals, "negative_signals": negatives, "positive_score": round(sum(i["weight"] for i in signals), 2), "negative_score": round(sum(i["weight"] for i in negatives), 2)}

def score_discovery_candidate(row: Mapping[str, Any], *, config: DiscoveryConfig | None = None) -> Dict[str, Any]:
    config = config or DiscoveryConfig()
    exclusion = _exclusion_reason(row, config)
    coverage = _coverage_pct(row)
    payload = _discover_signals(row)
    negatives = list(payload["negative_signals"])
    if coverage < config.minimum_data_coverage_pct:
        negatives.append({"name": "low_data_coverage", "weight": NEGATIVE_WEIGHTS["low_data_coverage"], "evidence": f"Discovery data coverage is only {coverage:.1f}%."})
    positive_score = payload["positive_score"]
    negative_score = round(sum(i["weight"] for i in negatives), 2)
    normalized_score = max(0.0, min(100.0, 40.0 + positive_score + negative_score))
    price = _num(_first(row, "Current Price", "Price", "price", "Close"))
    market_cap = _num(_first(row, "Market Cap", "market_cap", "marketCap"))
    qualifies = exclusion is None and coverage >= config.minimum_data_coverage_pct and normalized_score >= config.minimum_signal_score and len(payload["signals"]) >= 2
    top_signals = sorted(payload["signals"], key=lambda i: i["weight"], reverse=True)[:6]
    top_negatives = sorted(negatives, key=lambda i: i["weight"])[:4]
    return {
        "ticker": _ticker(row), "company": _company(row), "sector": _sector(row),
        "country": _country(row), "price": price, "market_cap": market_cap,
        "price_bucket": _price_bucket(price), "discovery_score": round(normalized_score, 1),
        "positive_signal_score": positive_score, "negative_signal_score": negative_score,
        "data_coverage_pct": round(coverage, 1), "qualifies_for_enrichment": qualifies,
        "exclusion_reason": exclusion, "top_signals": top_signals,
        "negative_signals": top_negatives, "signal_count": len(payload["signals"]),
        "why_discovered": [i["evidence"] for i in top_signals], "row": dict(row),
    }

def _diversify_candidates(candidates: List[Dict[str, Any]], config: DiscoveryConfig) -> List[Dict[str, Any]]:
    candidates = sorted(candidates, key=lambda i: (i["discovery_score"], i["data_coverage_pct"], i["signal_count"]), reverse=True)
    selected, selected_tickers = [], set()
    sector_counts, bucket_counts = Counter(), Counter()
    desired_bucket_minimum = {"under_30": 4, "30_to_75": 6, "75_to_200": 8, "over_200": 4}
    for candidate in candidates:
        if len(selected) >= config.maximum_candidates: break
        sector, bucket = candidate["sector"], candidate["price_bucket"]
        if sector_counts[sector] >= config.maximum_per_sector: continue
        if config.include_price_buckets and bucket_counts[bucket] >= desired_bucket_minimum.get(bucket, 999) and len(selected) < min(config.maximum_candidates, 22): continue
        selected.append(candidate); selected_tickers.add(candidate["ticker"]); sector_counts[sector] += 1; bucket_counts[bucket] += 1
    for candidate in candidates:
        if len(selected) >= config.maximum_candidates: break
        if candidate["ticker"] in selected_tickers: continue
        if sector_counts[candidate["sector"]] >= config.maximum_per_sector: continue
        selected.append(candidate); selected_tickers.add(candidate["ticker"]); sector_counts[candidate["sector"]] += 1; bucket_counts[candidate["price_bucket"]] += 1
    return selected

def discover_opportunities(rows: Any, *, config: DiscoveryConfig | None = None) -> Dict[str, Any]:
    config = config or DiscoveryConfig()
    normalized = _normalize_rows(rows)
    scored = [score_discovery_candidate(row, config=config) for row in normalized]
    qualifying = [i for i in scored if i["qualifies_for_enrichment"]]
    rejected = [i for i in scored if not i["qualifies_for_enrichment"]]
    selected = _diversify_candidates(qualifying, config)
    signal_distribution = Counter(s["name"] for item in scored for s in item["top_signals"])
    exclusions = Counter(i["exclusion_reason"] for i in rejected if i["exclusion_reason"])
    rejection_reasons = Counter()
    for item in rejected:
        if item["exclusion_reason"]: rejection_reasons[item["exclusion_reason"]] += 1
        elif item["data_coverage_pct"] < config.minimum_data_coverage_pct: rejection_reasons["insufficient_discovery_coverage"] += 1
        elif item["signal_count"] < 2: rejection_reasons["insufficient_independent_signals"] += 1
        else: rejection_reasons["discovery_score_below_threshold"] += 1
    diagnostics = []
    if len(normalized) < 1000: diagnostics.append("Discovery universe is below 1,000 symbols; verify full-universe loading.")
    if len(qualifying) < 25: diagnostics.append("Fewer than 25 stocks qualified for full enrichment.")
    if not selected: diagnostics.append("No candidates were selected; inspect coverage, exclusions, and signal mappings.")
    return {
        "version": "V95", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "read_only": True, "responsibility": "candidate discovery only", "config": asdict(config),
        "discovery_summary": {"universe_received": len(normalized), "excluded": sum(exclusions.values()), "qualified_for_enrichment": len(qualifying), "selected_for_full_research": len(selected), "rejected": len(rejected)},
        "ranked_candidates": [{k: v for k, v in i.items() if k != "row"} for i in selected],
        "selected_rows": [i["row"] for i in selected],
        "rejected_candidates": [{k: v for k, v in i.items() if k != "row"} for i in rejected[:250]],
        "signal_distribution": dict(signal_distribution), "exclusion_summary": dict(exclusions),
        "top_rejection_reasons": [{"reason": r, "count": c} for r, c in rejection_reasons.most_common(12)],
        "price_bucket_distribution": dict(Counter(i["price_bucket"] for i in selected)),
        "sector_distribution": dict(Counter(i["sector"] for i in selected)),
        "diagnostics": diagnostics,
    }

def validate_discovery_contract(result: Mapping[str, Any]) -> List[str]:
    errors = []
    if result.get("read_only") is not True: errors.append("V95 must remain read-only")
    if result.get("responsibility") != "candidate discovery only": errors.append("V95 responsibility must remain candidate discovery only")
    for candidate in result.get("ranked_candidates") or []:
        if any(k in candidate for k in ("action_code", "display_action", "Recommendation", "Decision", "v89_decision")):
            errors.append(f"{candidate.get('ticker', 'UNKNOWN')} contains a decision field")
    return errors

__all__ = ["DiscoveryConfig", "score_discovery_candidate", "discover_opportunities", "validate_discovery_contract"]
