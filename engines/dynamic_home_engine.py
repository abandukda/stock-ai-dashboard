from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

from engines.decision_intelligence_engine import evidence_pack, primary_risk, decision, movement_explanation

HISTORY_FILE = Path("data/atlas_discovery_history.json")
MEGA_CAPS = {"MSFT", "NVDA", "META", "AMZN", "GOOGL", "GOOG", "AAPL", "AVGO", "TSM", "AMD", "COST", "LLY"}
_SECTION_CACHE: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}


def _num(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        if isinstance(value, str):
            value = value.replace("$", "").replace(",", "").replace("%", "").strip()
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return default
        return result
    except Exception:
        return default


def _pick(row: Mapping[str, Any], keys: Sequence[str], default: Any = None) -> Any:
    for key in keys:
        if key in row:
            value = row.get(key)
            if value not in (None, "", "N/A", "Unavailable", "—"):
                return value
    return default


def _ticker(row: Mapping[str, Any]) -> str:
    return str(_pick(row, ["Ticker", "ticker", "symbol"], "")).strip().upper()


def _pct(value: Any) -> Optional[float]:
    n = _num(value)
    if n is None:
        return None
    return n * 100 if -2 <= n <= 2 else n


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _score(row: Mapping[str, Any], keys: Sequence[str], default: float = 50.0) -> float:
    return _clamp(_num(_pick(row, keys), default) or default)


def _rank_reason(row: Mapping[str, Any], prior: Optional[Mapping[str, Any]] = None) -> List[str]:
    reasons: List[Tuple[float, str]] = []
    ticker = _ticker(row)
    rev = _pct(_pick(row, ["Revenue Growth", "revenue_growth", "Revenue Growth %"]))
    eps = _pct(_pick(row, ["Earnings Growth", "earnings_growth", "EPS Growth", "eps_growth"]))
    rsi = _num(_pick(row, ["RSI", "rsi", "RSI 14"]))
    vol = _num(_pick(row, ["Volume Ratio", "relative_volume", "Relative Volume"]))
    upside = _pct(_pick(row, ["expected_upside_pct", "Expected Return", "Target Upside %", "Upside"]))
    news = str(_pick(row, ["latest_news_headline", "Top News", "news_headline"], "")).strip()
    earnings = _pct(_pick(row, ["eps_surprise_pct", "EPS Surprise", "earnings_surprise"]))
    analyst_revision = _pct(_pick(row, ["analyst_revision_pct", "target_revision_pct", "Analyst Revision %"]))

    if earnings is not None and abs(earnings) >= 3:
        reasons.append((95, f"Earnings surprise of {earnings:+.1f}% changed the setup."))
    if analyst_revision is not None and abs(analyst_revision) >= 2:
        reasons.append((90, f"Analyst target revisions moved {analyst_revision:+.1f}%."))
    if vol is not None and vol >= 1.5:
        reasons.append((85, f"Relative volume is elevated at {vol:.1f}× normal."))
    if news and not news.lower().startswith("no recent"):
        reasons.append((82, f"Fresh catalyst: {news[:105]}."))
    if upside is not None and upside >= 15:
        reasons.append((75, f"Atlas modeled upside is {upside:.1f}%."))
    if rsi is not None and 48 <= rsi <= 68:
        reasons.append((60, f"RSI of {rsi:.0f} shows constructive momentum without being overextended."))
    if rev is not None and rev >= 12:
        reasons.append((55, f"Revenue growth remains strong at {rev:.1f}%."))
    if eps is not None and eps >= 12:
        reasons.append((54, f"Earnings growth is positive at {eps:.1f}%."))
    if prior:
        old_rank = _num(prior.get("rank"))
        current_rank = _num(row.get("dynamic_rank"))
        if old_rank and current_rank and old_rank > current_rank:
            reasons.append((88, f"Rank improved by {int(old_rank-current_rank)} places since the prior snapshot."))
    if not reasons:
        reasons.append((10, f"{ticker} remains on the radar because the core evidence is stable."))
    return [text for _, text in sorted(reasons, reverse=True)[:4]]


def load_history(path: Path = HISTORY_FILE) -> Dict[str, Any]:
    try:
        if path.exists():
            data = json.loads(path.read_text())
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def save_history(rows: Sequence[Mapping[str, Any]], path: Path = HISTORY_FILE) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "tickers": {
                _ticker(row): {
                    "rank": int(row.get("dynamic_rank", idx + 1)),
                    "home_score": round(float(row.get("home_score", 0)), 2),
                    "opportunity_score": round(float(row.get("opportunity_score", 0)), 2),
                    "shown_days": int(row.get("shown_days", 1)),
                }
                for idx, row in enumerate(rows)
                if _ticker(row)
            },
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2))
        tmp.replace(path)
    except Exception:
        pass


def build_dynamic_rankings(df: pd.DataFrame, max_rows: int = 100) -> List[Dict[str, Any]]:
    if df is None or df.empty:
        return []
    history = load_history()
    prior = history.get("tickers", {}) if isinstance(history, dict) else {}
    output: List[Dict[str, Any]] = []

    for _, series in df.head(max_rows).iterrows():
        row = dict(series)
        ticker = _ticker(row)
        if not ticker:
            continue
        quality = _score(row, ["Quality", "Quality Score", "quality_score", "financial_score"], 50)
        opportunity = _score(row, ["Opportunity", "Opportunity Score", "opportunity_score", "technical_agent_score", "Technical Score"], 50)
        confidence = _score(row, ["Confidence", "Research Confidence", "confidence", "conviction_score"], 50)
        technical = _score(row, ["Technical Score", "technical_agent_score", "Technical", "technical_score"], opportunity)
        valuation = _score(row, ["Valuation Score", "valuation_agent_score", "valuation_score"], 50)
        catalyst = _score(row, ["Catalyst Score", "catalyst_agent_score", "News Score", "news_score"], 40)

        rel_vol = _num(_pick(row, ["Volume Ratio", "relative_volume", "Relative Volume"]), 1.0) or 1.0
        eps_surprise = abs(_pct(_pick(row, ["eps_surprise_pct", "EPS Surprise", "earnings_surprise"])) or 0.0)
        analyst_revision = abs(_pct(_pick(row, ["analyst_revision_pct", "target_revision_pct", "Analyst Revision %"])) or 0.0)
        news = str(_pick(row, ["latest_news_headline", "Top News", "news_headline"], "")).strip()
        live_catalyst = min(100.0, catalyst + min(20, max(0, rel_vol - 1) * 18) + min(18, eps_surprise * 1.5) + min(15, analyst_revision * 2) + (8 if news and not news.lower().startswith("no recent") else 0))

        p = prior.get(ticker, {}) if isinstance(prior, dict) else {}
        prior_score = _num(p.get("home_score"))
        shown_days = int(_num(p.get("shown_days"), 0) or 0) + 1
        score_change = 0.0 if prior_score is None else abs((opportunity - prior_score) / max(abs(prior_score), 1)) * 100
        stale = shown_days >= 3 and score_change < 2 and live_catalyst < 55
        freshness = 95 if not p else max(15, 72 - shown_days * 12)
        if news and not news.lower().startswith("no recent"):
            freshness = min(100, freshness + 15)
        home_score = (
            0.45 * opportunity
            + 0.20 * live_catalyst
            + 0.15 * technical
            + 0.10 * valuation
            + 0.05 * confidence
            + 0.05 * freshness
        )
        if stale:
            home_score -= 12
        if quality < 55:
            home_score -= (55 - quality) * 0.25

        row.update({
            "home_score": round(_clamp(home_score), 2),
            "opportunity_score": opportunity,
            "dynamic_catalyst_score": round(_clamp(live_catalyst), 2),
            "freshness_score": round(_clamp(freshness), 2),
            "shown_days": shown_days,
            "is_stale_core": stale,
            "is_mega_cap": ticker in MEGA_CAPS,
            "prior_rank": int(_num(p.get("rank"), 0) or 0) or None,
            "is_new_discovery": not bool(p),
        })
        output.append(row)

    output.sort(key=lambda r: (r["home_score"], r.get("dynamic_catalyst_score", 0), r.get("opportunity_score", 0)), reverse=True)
    for idx, row in enumerate(output, start=1):
        row["dynamic_rank"] = idx
        old = row.get("prior_rank")
        row["rank_change"] = (old - idx) if old else None
        row["why_today"] = evidence_pack(row, 6)
        row["primary_risk"] = primary_risk(row)
        decision_pack = decision(row)
        row["atlas_decision"] = decision_pack["label"]
        row["decision_guidance"] = decision_pack["action"]
        row["movement_explanation"] = movement_explanation(row)

    save_history(output)
    return output


def _frame_signature(df: pd.DataFrame) -> str:
    """Stable-enough signature so repeated Streamlit renders do not mutate history."""
    try:
        tickers = ",".join(sorted({_ticker(dict(r)) for _, r in df.head(200).iterrows() if _ticker(dict(r))}))
        stamps = []
        for key in ("generated_at", "scan_time", "Last Scan", "last_scan"):
            if key in df.columns and not df.empty:
                stamps.append(str(df.iloc[0].get(key, "")))
        return f"{len(df)}|{tickers}|{'|'.join(stamps)}"
    except Exception:
        return str(id(df))


def build_home_sections(df: pd.DataFrame) -> Dict[str, List[Dict[str, Any]]]:
    """Build paid-client homepage sections and return consistent results per scan."""
    if df is None or df.empty:
        return {k: [] for k in ("today", "movers", "new", "hidden", "core", "mega", "all")}

    signature = _frame_signature(df)
    if signature in _SECTION_CACHE:
        return _SECTION_CACHE[signature]

    ranked = build_dynamic_rankings(df)
    if not ranked:
        return {k: [] for k in ("today", "movers", "new", "hidden", "core", "mega", "all")}

    today = [r for r in ranked if not r.get("is_stale_core") and not r.get("is_mega_cap")][:8]
    if len(today) < 6:
        today = [r for r in ranked if not r.get("is_stale_core")][:8]

    actual_movers = [r for r in ranked if r.get("rank_change") not in (None, 0)]
    movers = sorted(actual_movers, key=lambda r: abs(r.get("rank_change") or 0), reverse=True)[:6]
    # First snapshot / quiet day: show the largest score deltas versus opportunity as baseline movers.
    if not movers:
        movers = sorted(ranked, key=lambda r: abs(float(r.get("home_score", 0)) - float(r.get("opportunity_score", 0))), reverse=True)[:6]
        for r in movers:
            r.setdefault("movement_note", "Baseline — rank history is still accumulating")

    new = [r for r in ranked if r.get("is_new_discovery")][:6]
    if not new:
        # Do not leave a dead panel: show the freshest eligible candidates.
        new = sorted([r for r in ranked if not r.get("is_mega_cap")], key=lambda r: r.get("freshness_score", 0), reverse=True)[:6]
        for r in new:
            r.setdefault("movement_note", "Fresh candidate — not a brand-new ticker")

    hidden: List[Dict[str, Any]] = []
    for r in ranked:
        cap = _num(_pick(r, ["Market Cap", "market_cap", "marketCap"]))
        analysts = _num(_pick(r, ["Analyst Count", "analyst_count", "numberOfAnalystOpinions"]), 0) or 0
        if cap and 500_000_000 <= cap <= 20_000_000_000 and analysts <= 20 and r.get("home_score", 0) >= 55:
            hidden.append(r)
        if len(hidden) >= 6:
            break
    if not hidden:
        hidden = [r for r in ranked if not r.get("is_mega_cap") and _score(r, ["Quality", "quality_score"], 50) >= 70][:6]

    core = [r for r in ranked if r.get("is_stale_core") and _score(r, ["Quality", "quality_score"], 50) >= 75][:8]
    if not core:
        core = [r for r in ranked if not r.get("is_mega_cap") and _score(r, ["Quality", "quality_score"], 50) >= 85][:8]

    mega = [r for r in ranked if r.get("is_mega_cap")][:10]
    # Mega-cap monitor should always exist when those names are in the universe.
    if not mega:
        mega = [r for r in ranked if _ticker(r) in MEGA_CAPS][:10]

    result = {"today": today, "movers": movers, "new": new, "hidden": hidden, "core": core, "mega": mega, "all": ranked}
    _SECTION_CACHE[signature] = result
    return result


# Compatibility alias for older/newer app builds.
def build_dynamic_home_sections(df: pd.DataFrame) -> Dict[str, List[Dict[str, Any]]]:
    return build_home_sections(df)

