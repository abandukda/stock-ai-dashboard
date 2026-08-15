"""Build the isolated Atlas Phase 4B panel from committed scan vintages.

No production module imports this file. Outcomes are labels and never inputs to
the canonical valuation replay.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
import json
import math
from pathlib import Path
import statistics
import subprocess
from typing import Any, Callable, Iterable, Mapping

import pandas as pd

from engines.atlas_valuation import AtlasValuationInputs, calculate_atlas_fair_value
from analysis.phase4a.validate_point_in_time import validate_panel


FORMULA_VERSION = "ATLAS_CANONICAL_PHASE3_2026_08"
EPS_DERIVED = "DERIVED_FROM_CONTEMPORANEOUS_PRICE_AND_PE"
UNIVERSE = (
    "NVDA", "AVGO", "MU", "CRM", "CIEN", "DVN", "XOM", "CVX", "OXY",
    "PAAS", "KGC", "B", "AU", "WPM", "HCA", "GILD", "INSM", "GPN",
    "UAL", "EME", "BABA", "CCL", "BKNG", "PINS", "CHTR",
)
SECTOR_BENCHMARKS = {
    "Technology": "XLK", "Energy": "XLE", "Basic Materials": "XLB",
    "Healthcare": "XLV", "Industrials": "XLI", "Consumer Cyclical": "XLY",
    "Communication Services": "XLC", "Financial Services": "XLF",
    "Consumer Defensive": "XLP", "Real Estate": "XLRE", "Utilities": "XLU",
}


def _run_git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, text=True, capture_output=True).stdout


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(str(value).replace("$", "").replace(",", "").replace("%", "").strip())
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _first(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, "", "Unknown", "Unavailable"):
            return row[key]
    return None


def _rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("rows", "results", "stocks", "data"):
            if isinstance(payload.get(key), list):
                return [x for x in payload[key] if isinstance(x, dict)]
    return []


def git_vintages(repo: Path) -> list[dict[str, Any]]:
    """Load every committed scan version deterministically in commit order."""
    shas = _run_git(repo, "log", "--reverse", "--format=%H", "--", "market_full_scan.json").splitlines()
    result = []
    for sha in shas:
        timestamp = _run_git(repo, "show", "-s", "--format=%cI", sha).strip()
        try:
            payload = json.loads(_run_git(repo, "show", f"{sha}:market_full_scan.json"))
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            continue
        result.append({"sha": sha, "timestamp": timestamp, "rows": _rows(payload)})
    return result


def select_monthly_vintages(vintages: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Final committed valid scan vintage in each calendar month."""
    selected: dict[str, dict[str, Any]] = {}
    for vintage in vintages:
        if not vintage.get("rows"):
            continue
        key = str(vintage["timestamp"])[:7]
        if key not in selected or str(vintage["timestamp"]) > str(selected[key]["timestamp"]):
            selected[key] = dict(vintage)
    return [selected[key] for key in sorted(selected)]


def _historical_row(vintage: Mapping[str, Any], source: Mapping[str, Any]) -> dict[str, Any]:
    ticker = str(_first(source, "ticker", "symbol", "Ticker") or "").upper()
    price = _number(_first(source, "price", "current_price", "Price"))
    pe = _number(_first(source, "forward_pe", "Forward PE", "Forward P/E"))
    direct_eps = _number(_first(source, "forward_eps", "Forward EPS"))
    growth = _number(_first(source, "revenue_growth", "Revenue Growth"))
    margin = _number(_first(source, "operating_profit_margin", "operating_margin", "Operating Margin"))
    observed = str(vintage["timestamp"])[:10]
    provenance = f"GIT_SCAN_VINTAGE:{vintage['sha']}"

    if direct_eps is not None and direct_eps > 0:
        eps, eps_method = direct_eps, "PROVIDER_DIRECT"
    elif price is not None and price > 0 and pe is not None and pe > 0:
        eps, eps_method = price / pe, EPS_DERIVED
    else:
        eps, eps_method = None, "UNAVAILABLE"

    valuation = calculate_atlas_fair_value(AtlasValuationInputs(
        price=price, forward_pe=pe, forward_eps=eps,
        forward_eps_source=provenance if eps is not None else None,
        revenue_growth=growth,
        revenue_growth_source=provenance if growth is not None else None,
        revenue_growth_horizon="PROVIDER_DEFINED" if growth is not None else None,
        operating_margin=margin,
    ))
    rejection = ",".join(valuation.validation_flags) or None
    return {
        "scan_commit_sha": vintage["sha"], "scan_timestamp": vintage["timestamp"],
        "observation_date": observed, "ticker": ticker,
        "sector": _first(source, "sector", "Sector"),
        "sector_provenance": provenance if _first(source, "sector", "Sector") is not None else None,
        "industry": _first(source, "industry", "Industry"),
        "industry_provenance": provenance if _first(source, "industry", "Industry") is not None else None,
        "price": price, "price_provenance": provenance if price is not None else None,
        "forward_pe": pe, "forward_pe_provenance": provenance if pe is not None else None,
        "forward_eps": eps, "forward_eps_method": eps_method,
        "forward_eps_provenance": provenance if eps is not None else None,
        "revenue_growth": growth, "revenue_growth_provenance": provenance if growth is not None else None,
        "operating_margin": margin,
        "operating_margin_provenance": provenance if margin is not None else None,
        "formula_version": FORMULA_VERSION,
        "justified_pe": valuation.justified_pe,
        "required_multiple_expansion": valuation.multiple_expansion_ratio,
        "raw_atlas_fv": valuation.raw_fair_value,
        "raw_atlas_upside": valuation.raw_upside_pct,
        "atlas_fv_status": valuation.status,
        "published_atlas_fv": valuation.fair_value,
        "rejection_reason": rejection,
        "model_input_fields": ["price", "forward_pe", "forward_eps", "revenue_growth", "operating_margin"],
    }


def construct_candidates(vintages: Iterable[Mapping[str, Any]], universe: Iterable[str] = UNIVERSE) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    wanted = {x.upper() for x in universe}
    candidates: list[dict[str, Any]] = []
    exclusions: list[dict[str, str]] = []
    by_month: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for vintage in vintages:
        if vintage.get("rows"):
            by_month[str(vintage["timestamp"])[:7]].append(vintage)
    for month in sorted(by_month):
        for ticker in sorted(wanted):
            latest_seen: dict[str, Any] | None = None
            selected: dict[str, Any] | None = None
            # Final valid ticker observation in the month, not merely the final
            # global scan (whose universe or schema may be different).
            for vintage in sorted(by_month[month], key=lambda x: str(x["timestamp"])):
                by_ticker = {str(_first(item, "ticker", "symbol", "Ticker") or "").upper(): item for item in vintage["rows"]}
                if ticker not in by_ticker:
                    continue
                latest_seen = _historical_row(vintage, by_ticker[ticker])
                if all(latest_seen[key] is not None for key in ("price", "forward_pe", "revenue_growth")):
                    selected = latest_seen
            if selected is not None:
                candidates.append(selected)
            elif latest_seen is None:
                exclusions.append({"ticker": ticker, "observation_month": month, "reason": "TICKER_NOT_PRESENT_IN_ANY_MONTH_VINTAGE"})
            else:
                missing = [key for key in ("price", "forward_pe", "revenue_growth") if latest_seen[key] is None]
                exclusions.append({"ticker": ticker, "observation_month": month, "reason": "NO_VALID_MONTH_OBSERVATION_MISSING:" + ",".join(missing)})
    return candidates, exclusions


def _closest_adjusted_return(series: pd.Series, observed: date, months: int) -> float | None:
    if series.empty:
        return None
    start = pd.Timestamp(observed)
    target = start + pd.DateOffset(months=months)
    if target.date() > datetime.now(timezone.utc).date():
        return None
    start_values = series[series.index >= start]
    end_values = series[series.index >= target]
    if start_values.empty or end_values.empty:
        return None
    first, last = float(start_values.iloc[0]), float(end_values.iloc[0])
    return ((last / first) - 1.0) * 100 if first > 0 else None


def download_adjusted_prices(symbols: Iterable[str], start: date, end: date) -> dict[str, pd.Series]:
    """Bounded outcome-label download; callers may inject a deterministic provider."""
    import yfinance as yf
    requested = sorted(set(symbols))
    raw = yf.download(requested, start=start.isoformat(), end=end.isoformat(), auto_adjust=False, progress=False, threads=True)
    result: dict[str, pd.Series] = {}
    for symbol in requested:
        try:
            adjusted = raw["Adj Close"][symbol] if len(requested) > 1 else raw["Adj Close"]
            result[symbol] = adjusted.dropna()
        except (KeyError, TypeError):
            result[symbol] = pd.Series(dtype=float)
    return result


def attach_outcomes(rows: list[dict[str, Any]], price_provider: Callable[[Iterable[str], date, date], dict[str, pd.Series]] | None = None) -> None:
    if not rows:
        return
    symbols = {row["ticker"] for row in rows} | {"SPY"}
    symbols |= {SECTOR_BENCHMARKS[row["sector"]] for row in rows if row.get("sector") in SECTOR_BENCHMARKS}
    start = min(date.fromisoformat(row["observation_date"]) for row in rows) - timedelta(days=7)
    end = datetime.now(timezone.utc).date() + timedelta(days=1)
    prices = (price_provider or download_adjusted_prices)(symbols, start, end)
    for row in rows:
        observed = date.fromisoformat(row["observation_date"])
        benchmark = SECTOR_BENCHMARKS.get(row.get("sector"))
        row["sector_benchmark"] = benchmark
        for months, label in ((1, "1m"), (3, "3m")):
            ticker_return = _closest_adjusted_return(prices.get(row["ticker"], pd.Series(dtype=float)), observed, months)
            spy_return = _closest_adjusted_return(prices.get("SPY", pd.Series(dtype=float)), observed, months)
            sector_return = _closest_adjusted_return(prices.get(benchmark, pd.Series(dtype=float)), observed, months) if benchmark else None
            row[f"return_{label}"] = ticker_return
            row[f"spy_return_{label}"] = spy_return
            row[f"excess_spy_{label}"] = ticker_return - spy_return if ticker_return is not None and spy_return is not None else None
            row[f"sector_return_{label}"] = sector_return
            row[f"excess_sector_{label}"] = ticker_return - sector_return if ticker_return is not None and sector_return is not None else None


def _stats(values: Iterable[float | None]) -> dict[str, Any]:
    clean = [float(x) for x in values if x is not None and math.isfinite(float(x))]
    return {"n": len(clean), "mean": statistics.fmean(clean) if clean else None, "median": statistics.median(clean) if clean else None}


def _bucket(upside: float | None) -> str:
    if upside is None: return "UNAVAILABLE"
    if upside < -20: return "< -20%"
    if upside < 0: return "-20% to 0%"
    if upside < 20: return "0-20%"
    if upside < 40: return "20-40%"
    if upside < 60: return "40-60%"
    if upside <= 80: return "60-80%"
    return ">80%"


def summarize(rows: list[dict[str, Any]], exclusions: list[dict[str, str]], vintages: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    expansion: dict[str, list[dict[str, Any]]] = defaultdict(list)
    sectors: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[_bucket(row.get("raw_atlas_upside"))].append(row)
        ratio = row.get("required_multiple_expansion")
        expansion[">3.0x" if ratio and ratio > 3 else ">2.0x" if ratio and ratio > 2 else ">1.5x" if ratio and ratio > 1.5 else "<=1.5x"].append(row)
        sectors[str(row.get("sector") or "UNAVAILABLE")].append(row)

    def group_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "n": len(items), "insufficient_sample": len(items) < 30,
            "raw_upside": _stats(x.get("raw_atlas_upside") for x in items),
            "return_1m": _stats(x.get("return_1m") for x in items),
            "return_3m": _stats(x.get("return_3m") for x in items),
            "positive_return_rate_1m": (sum((x.get("return_1m") or 0) > 0 for x in items if x.get("return_1m") is not None) / sum(x.get("return_1m") is not None for x in items)) if any(x.get("return_1m") is not None for x in items) else None,
            "spy_beating_rate_1m": (sum((x.get("excess_spy_1m") or 0) > 0 for x in items if x.get("excess_spy_1m") is not None) / sum(x.get("excess_spy_1m") is not None for x in items)) if any(x.get("excess_spy_1m") is not None for x in items) else None,
            "sector_beating_rate_1m": (sum((x.get("excess_sector_1m") or 0) > 0 for x in items if x.get("excess_sector_1m") is not None) / sum(x.get("excess_sector_1m") is not None for x in items)) if any(x.get("excess_sector_1m") is not None for x in items) else None,
        }

    above = [x for x in rows if x.get("raw_atlas_upside") is not None and x["raw_atlas_upside"] > 80]
    return {
        "panel_purpose": "ENGINEERING_VALIDATION_ONLY",
        "formula_version": FORMULA_VERSION,
        "monthly_deduplication_rule": "FINAL_VALID_COMMITTED_SCAN_VINTAGE_PER_CALENDAR_MONTH",
        "git_vintages_used": [{"sha": x["sha"], "timestamp": x["timestamp"]} for x in vintages],
        "tickers_attempted": list(UNIVERSE), "tickers_included": sorted({x["ticker"] for x in rows}),
        "exclusions": exclusions, "valid_observations": len(rows),
        "observation_dates": sorted({x["observation_date"] for x in rows}),
        "forward_eps_methods": dict(Counter(x["forward_eps_method"] for x in rows)),
        "atlas_fv_status": dict(Counter(x["atlas_fv_status"] for x in rows)),
        "raw_upside_buckets": {key: group_summary(groups.get(key, [])) for key in ("< -20%", "-20% to 0%", "0-20%", "20-40%", "40-60%", "60-80%", ">80%")},
        "required_expansion_groups": {key: group_summary(expansion.get(key, [])) for key in ("<=1.5x", ">1.5x", ">2.0x", ">3.0x")},
        "sectors": {key: {**group_summary(items), "required_expansion": _stats(x.get("required_multiple_expansion") for x in items), "published_fv_count": sum(x["atlas_fv_status"] == "PUBLISHED" for x in items), "rejected_fv_count": sum(x["atlas_fv_status"].startswith("REJECTED") for x in items)} for key, items in sorted(sectors.items())},
        "guard_above_80": {"count": len(above), "sectors": dict(Counter(str(x.get("sector") or "UNAVAILABLE") for x in above)), "required_expansion": _stats(x.get("required_multiple_expansion") for x in above), "outcomes": group_summary(above)},
        "overall": group_summary(rows),
        "cien_decision_semantics": "PENDING DECISION-SEMANTICS REVIEW",
    }


def build(repo: Path, output_dir: Path, include_outcomes: bool = True, price_provider=None) -> dict[str, Any]:
    all_vintages = git_vintages(repo)
    candidates, exclusions = construct_candidates(all_vintages)
    vintages_by_sha = {item["sha"]: item for item in all_vintages}
    vintages = [vintages_by_sha[sha] for sha in sorted({row["scan_commit_sha"] for row in candidates}, key=lambda value: str(vintages_by_sha[value]["timestamp"]))]
    valid, violations = validate_panel(candidates)
    if include_outcomes:
        attach_outcomes(valid, price_provider=price_provider)
    output_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(valid).to_parquet(output_dir / "point_in_time_feasibility.parquet", index=False)
    (output_dir / "lookahead_violations.json").write_text(json.dumps(violations, indent=2, default=str) + "\n")
    summary = summarize(valid, exclusions, vintages)
    summary["lookahead_violations"] = len(violations)
    (output_dir / "panel_summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output-dir", type=Path, default=Path("audit_results/phase4a"))
    parser.add_argument("--no-outcomes", action="store_true")
    args = parser.parse_args()
    print(json.dumps(build(args.repo.resolve(), args.output_dir, not args.no_outcomes), indent=2, default=str))


if __name__ == "__main__":
    main()
