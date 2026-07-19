"""
Atlas V100 — Institutional Command Center

New file:
    ui/command_center.py

Purpose
-------
Render a subscriber-facing executive command center from finalized Atlas
outputs without changing any investment recommendation, score, or ranking.

Consumes:
- V96 discovery report
- V97 transparency report
- V98.1 ranking report
- V98.2 competition report
- finalized stock rows / V93 snapshots

This module is read-only and presentation-only.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Mapping
import math

import pandas as pd
import streamlit as st


MISSING = {
    "",
    "n/a",
    "na",
    "none",
    "null",
    "nan",
    "unavailable",
    "under review",
    "not available",
    "not reported",
    "unknown",
    "-",
    "—",
}


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in MISSING
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    return True


def _num(value: Any, default: float | None = None) -> float | None:
    if not _present(value):
        return default
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default


def _text(value: Any, default: str = "") -> str:
    return str(value).strip() if _present(value) else default


def _ticker(row: Mapping[str, Any]) -> str:
    return _text(
        row.get("Ticker")
        or row.get("ticker")
        or row.get("symbol"),
        "UNKNOWN",
    ).upper()


def _company(row: Mapping[str, Any]) -> str:
    return _text(
        row.get("Company")
        or row.get("company")
        or row.get("Name"),
        _ticker(row),
    )


def _snapshot(row: Mapping[str, Any]) -> Mapping[str, Any]:
    value = row.get("v93_snapshot")
    return value if isinstance(value, Mapping) else {}


def _decision(row: Mapping[str, Any]) -> Mapping[str, Any]:
    value = row.get("v89_decision")
    return value if isinstance(value, Mapping) else {}


def _current_price(row: Mapping[str, Any]) -> float | None:
    snapshot = _snapshot(row)
    return _num(
        snapshot.get("current_price"),
        _num(row.get("Current Price"), _num(row.get("Price"))),
    )


def _fair_value(row: Mapping[str, Any]) -> float | None:
    snapshot = _snapshot(row)
    return _num(
        snapshot.get("atlas_fair_value"),
        _num(row.get("Atlas Fair Value"), _num(row.get("AI Fair Value"))),
    )


def _expected_return(row: Mapping[str, Any]) -> float | None:
    snapshot = _snapshot(row)
    decision = _decision(row)
    return _num(
        snapshot.get("expected_return_pct"),
        _num(
            decision.get("expected_return_pct"),
            _num(row.get("Target Upside %")),
        ),
    )


def _confidence(row: Mapping[str, Any]) -> float | None:
    snapshot = _snapshot(row)
    decision = _decision(row)
    return _num(
        snapshot.get("confidence"),
        _num(
            decision.get("conviction"),
            _num(row.get("Final Conviction")),
        ),
    )


def _action(row: Mapping[str, Any]) -> str:
    snapshot = _snapshot(row)
    decision = _decision(row)
    return _text(
        decision.get("display_action")
        or snapshot.get("display_action")
        or row.get("Recommendation")
        or row.get("Decision"),
        "Monitor",
    )


def _normalize_rows(rows: Any) -> List[Dict[str, Any]]:
    if rows is None:
        return []
    if hasattr(rows, "to_dict"):
        try:
            rows = rows.to_dict("records")
        except Exception:
            rows = []
    if isinstance(rows, Mapping):
        for key in ("rows", "data", "results", "stocks"):
            value = rows.get(key)
            if isinstance(value, list):
                rows = value
                break
        else:
            rows = [rows]
    if isinstance(rows, Iterable) and not isinstance(
        rows,
        (str, bytes, bytearray),
    ):
        return [
            dict(item)
            for item in rows
            if isinstance(item, Mapping)
        ]
    return []


def index_by_ticker(
    rows: Iterable[Mapping[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    output: Dict[str, Dict[str, Any]] = {}
    for row in rows or []:
        if not isinstance(row, Mapping):
            continue
        ticker = _ticker(row)
        if ticker != "UNKNOWN":
            output[ticker] = dict(row)
    return output


def build_command_center_model(
    *,
    stock_rows: Any,
    discovery_report: Mapping[str, Any] | None = None,
    transparency_report: Mapping[str, Any] | None = None,
    ranking_report: Mapping[str, Any] | None = None,
    competition_report: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Build the immutable V100 command-center view model.
    """
    rows = _normalize_rows(stock_rows)
    by_ticker = index_by_ticker(rows)

    discovery_report = dict(discovery_report or {})
    transparency_report = dict(transparency_report or {})
    ranking_report = dict(ranking_report or {})
    competition_report = dict(competition_report or {})

    discovery = discovery_report.get("funnel_counts") or {}
    transparency = transparency_report.get("summary") or {}
    ranking = ranking_report.get("ranking_summary") or {}
    competition = competition_report.get("competition_summary") or {}

    ranked = ranking_report.get("ranked_candidates") or []
    selected = competition_report.get("selected_candidates") or []

    ranked_by_ticker = index_by_ticker(ranked)
    selected_by_ticker = index_by_ticker(selected)

    enriched: List[Dict[str, Any]] = []
    for row in rows:
        ticker = _ticker(row)
        rank = ranked_by_ticker.get(ticker, {})
        portfolio = selected_by_ticker.get(ticker, {})
        enriched.append({
            "ticker": ticker,
            "company": _company(row),
            "action": _action(row),
            "current_price": _current_price(row),
            "fair_value": _fair_value(row),
            "expected_return": _expected_return(row),
            "confidence": _confidence(row),
            "opportunity_score": _num(rank.get("opportunity_score")),
            "opportunity_tier": _text(
                rank.get("opportunity_tier"),
                "Under review",
            ),
            "overall_rank": _num(rank.get("overall_rank")),
            "percentile_text": _text(
                rank.get("top_percentile_text"),
                "Under review",
            ),
            "sector": _text(
                rank.get("sector") or row.get("Sector"),
                "Unknown",
            ),
            "portfolio_rank": _num(portfolio.get("portfolio_rank")),
            "selection_reason": _text(
                portfolio.get("selection_reason"),
                "",
            ),
            "row": row,
        })

    ranked_enriched = sorted(
        enriched,
        key=lambda item: (
            item["opportunity_score"] is not None,
            item["opportunity_score"] or 0,
            item["confidence"] or 0,
        ),
        reverse=True,
    )

    top_opportunities = [
        item for item in ranked_enriched
        if item["portfolio_rank"] is not None
    ][:8]
    if not top_opportunities:
        top_opportunities = ranked_enriched[:8]

    buy_now = [
        item for item in enriched
        if "buy now" in item["action"].lower()
    ]
    accumulate = [
        item for item in enriched
        if "accumulate" in item["action"].lower()
    ]
    monitor = [
        item for item in enriched
        if "monitor" in item["action"].lower()
        or "watch" in item["action"].lower()
    ]
    avoid = [
        item for item in enriched
        if "avoid" in item["action"].lower()
    ]

    confidences = [
        item["confidence"]
        for item in enriched
        if item["confidence"] is not None
    ]
    returns = [
        item["expected_return"]
        for item in enriched
        if item["expected_return"] is not None
    ]

    market_health_components = []
    consistency = _num(transparency.get("consistency_rate_pct"))
    if consistency is not None:
        market_health_components.append(consistency)

    avg_opportunity = _num(ranking.get("average_opportunity_score"))
    if avg_opportunity is not None:
        market_health_components.append(avg_opportunity)

    elite_count = int(_num(ranking.get("elite_count"), 0) or 0)
    high_count = int(_num(ranking.get("high_count"), 0) or 0)
    ranked_count = int(_num(ranking.get("universe_ranked"), 0) or 0)
    breadth_score = (
        min(100.0, ((elite_count + high_count) / ranked_count) * 500.0)
        if ranked_count > 0
        else None
    )
    if breadth_score is not None:
        market_health_components.append(breadth_score)

    market_health = (
        sum(market_health_components) / len(market_health_components)
        if market_health_components
        else None
    )

    sector_scores: Dict[str, List[float]] = defaultdict(list)
    for item in ranked_enriched:
        if item["opportunity_score"] is not None:
            sector_scores[item["sector"]].append(
                item["opportunity_score"]
            )

    sector_leadership = []
    for sector, scores in sector_scores.items():
        average = sum(scores) / len(scores)
        if average >= 80:
            status = "Bullish"
        elif average >= 65:
            status = "Constructive"
        elif average >= 50:
            status = "Neutral"
        else:
            status = "Weak"

        sector_leadership.append({
            "sector": sector,
            "average_score": round(average, 1),
            "status": status,
            "candidate_count": len(scores),
        })

    sector_leadership.sort(
        key=lambda item: item["average_score"],
        reverse=True,
    )

    warnings: List[str] = []
    if elite_count == 0:
        warnings.append("No Elite opportunities were identified.")
    if int(_num(competition.get("selected_candidates"), 0) or 0) == 0:
        warnings.append("Portfolio competition selected no candidates.")
    if consistency is not None and consistency < 95:
        warnings.append("Decision consistency is below 95%.")
    if int(_num(discovery.get("shortlisted_for_full_research"), 0) or 0) == 0:
        warnings.append(
            "The discovery funnel produced no full-research shortlist."
        )
    if not buy_now:
        warnings.append("No Buy Now opportunities are currently present.")

    return {
        "version": "V100",
        "read_only": True,
        "responsibility": "institutional command-center presentation only",
        "summary": {
            "universe_received": int(
                _num(discovery.get("universe_received"), len(rows)) or 0
            ),
            "research_shortlist": int(
                _num(
                    discovery.get("shortlisted_for_full_research"),
                    0,
                ) or 0
            ),
            "ranked_universe": ranked_count,
            "portfolio_candidates": int(
                _num(competition.get("selected_candidates"), 0) or 0
            ),
            "buy_now_count": len(buy_now),
            "accumulate_count": len(accumulate),
            "monitor_count": len(monitor),
            "avoid_count": len(avoid),
            "elite_count": elite_count,
            "average_confidence": (
                round(sum(confidences) / len(confidences), 1)
                if confidences else None
            ),
            "average_expected_return": (
                round(sum(returns) / len(returns), 1)
                if returns else None
            ),
            "decision_consistency_pct": consistency,
            "market_health_score": (
                round(market_health, 1)
                if market_health is not None
                else None
            ),
        },
        "top_opportunities": top_opportunities,
        "sector_leadership": sector_leadership[:10],
        "opportunity_distribution": {
            "Elite": int(_num(ranking.get("elite_count"), 0) or 0),
            "Exceptional": int(
                _num(ranking.get("exceptional_count"), 0) or 0
            ),
            "High": int(_num(ranking.get("high_count"), 0) or 0),
            "Good": int(_num(ranking.get("good_count"), 0) or 0),
            "Average": int(_num(ranking.get("average_count"), 0) or 0),
            "Weak": int(_num(ranking.get("weak_count"), 0) or 0),
        },
        "warnings": warnings,
    }


def _health_label(score: float | None) -> str:
    if score is None:
        return "Under review"
    if score >= 80:
        return "Healthy"
    if score >= 65:
        return "Constructive"
    if score >= 50:
        return "Mixed"
    return "Risk-Off"


def _metric_value(value: Any, suffix: str = "") -> str:
    number = _num(value)
    if number is None:
        return "Under review"
    if suffix == "%":
        return f"{number:.1f}%"
    return f"{number:,.0f}{suffix}"


def render_command_center(
    *,
    stock_rows: Any,
    discovery_report: Mapping[str, Any] | None = None,
    transparency_report: Mapping[str, Any] | None = None,
    ranking_report: Mapping[str, Any] | None = None,
    competition_report: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Render the V100 Institutional Command Center and return its view model.
    """
    model = build_command_center_model(
        stock_rows=stock_rows,
        discovery_report=discovery_report,
        transparency_report=transparency_report,
        ranking_report=ranking_report,
        competition_report=competition_report,
    )
    summary = model["summary"]

    st.markdown(
        """
<style>
.v100-hero {
    border: 1px solid rgba(90, 170, 255, .30);
    border-radius: 22px;
    padding: 22px;
    margin-bottom: 18px;
    background: linear-gradient(
        135deg,
        rgba(5, 20, 35, .96),
        rgba(10, 31, 55, .88)
    );
}
.v100-kicker {
    letter-spacing: .16em;
    text-transform: uppercase;
    font-size: .80rem;
    opacity: .72;
    font-weight: 800;
}
.v100-title {
    font-size: clamp(2rem, 5vw, 4.2rem);
    line-height: 1.02;
    font-weight: 900;
    margin-top: 10px;
}
.v100-subtitle {
    margin-top: 12px;
    opacity: .76;
    max-width: 980px;
}
.v100-card {
    border: 1px solid rgba(120, 140, 170, .24);
    border-radius: 16px;
    padding: 16px;
    min-height: 180px;
    background: rgba(15, 23, 42, .48);
    overflow-wrap: anywhere;
}
.v100-ticker {
    font-size: 1.45rem;
    font-weight: 900;
}
.v100-company {
    opacity: .68;
    margin-bottom: 10px;
}
.v100-pill {
    display: inline-block;
    border-radius: 999px;
    padding: 5px 10px;
    margin: 3px 4px 3px 0;
    border: 1px solid rgba(120, 140, 170, .28);
    font-size: .80rem;
    overflow-wrap: anywhere;
}
</style>
""",
        unsafe_allow_html=True,
    )

    st.markdown(
        """
<div class="v100-hero">
  <div class="v100-kicker">Atlas AI Institutional Command Center</div>
  <div class="v100-title">Today’s Investment Committee</div>
  <div class="v100-subtitle">
    Atlas narrows the investable universe through discovery, research,
    ranking, competition, and decision validation before surfacing ideas.
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    health = _num(summary.get("market_health_score"))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Market Health",
        _metric_value(health),
        _health_label(health),
    )
    c2.metric(
        "Universe Reviewed",
        f"{summary['universe_received']:,}",
    )
    c3.metric(
        "Portfolio Candidates",
        summary["portfolio_candidates"],
    )
    c4.metric(
        "Buy Now",
        summary["buy_now_count"],
    )

    c5, c6, c7, c8 = st.columns(4)
    c5.metric(
        "Elite Opportunities",
        summary["elite_count"],
    )
    c6.metric(
        "Research Shortlist",
        summary["research_shortlist"],
    )
    c7.metric(
        "Average Confidence",
        _metric_value(summary["average_confidence"], "%"),
    )
    c8.metric(
        "Decision Consistency",
        _metric_value(
            summary["decision_consistency_pct"],
            "%",
        ),
    )

    st.markdown("## Today’s Best Opportunities")
    opportunities = model["top_opportunities"]

    if not opportunities:
        st.info(
            "No ranked opportunities are currently available for the command center."
        )
    else:
        for start in range(0, len(opportunities), 2):
            columns = st.columns(2)
            for offset, item in enumerate(
                opportunities[start:start + 2]
            ):
                with columns[offset]:
                    score = _num(item.get("opportunity_score"))
                    score_text = (
                        f"{score:.1f}"
                        if score is not None
                        else "Under review"
                    )
                    rank = item.get("overall_rank")
                    rank_text = (
                        f"#{int(rank)}"
                        if _num(rank) is not None
                        else "Under review"
                    )
                    return_text = (
                        f"{item['expected_return']:+.1f}%"
                        if _num(item.get("expected_return")) is not None
                        else "Under review"
                    )
                    confidence_text = (
                        f"{item['confidence']:.1f}%"
                        if _num(item.get("confidence")) is not None
                        else "Under review"
                    )

                    st.markdown(
                        f"""
<div class="v100-card">
  <div class="v100-ticker">{item['ticker']}</div>
  <div class="v100-company">{item['company']}</div>
  <span class="v100-pill">{item['action']}</span>
  <span class="v100-pill">{item['opportunity_tier']}</span>
  <span class="v100-pill">{item['percentile_text']}</span>
  <hr style="opacity:.15">
  <b>Opportunity Score:</b> {score_text}<br>
  <b>Overall Rank:</b> {rank_text}<br>
  <b>Expected Return:</b> {return_text}<br>
  <b>Confidence:</b> {confidence_text}<br>
  <b>Sector:</b> {item['sector']}
</div>
""",
                        unsafe_allow_html=True,
                    )

    left, right = st.columns(2)

    with left:
        st.markdown("## Opportunity Distribution")
        distribution = pd.DataFrame(
            [
                {"Tier": tier, "Count": count}
                for tier, count in model[
                    "opportunity_distribution"
                ].items()
            ]
        )
        st.dataframe(
            distribution,
            hide_index=True,
            use_container_width=True,
        )

    with right:
        st.markdown("## Sector Leadership")
        sectors = pd.DataFrame(model["sector_leadership"])
        if sectors.empty:
            st.caption("Sector-ranking data is not yet available.")
        else:
            st.dataframe(
                sectors.rename(
                    columns={
                        "sector": "Sector",
                        "average_score": "Average Score",
                        "status": "Status",
                        "candidate_count": "Candidates",
                    }
                ),
                hide_index=True,
                use_container_width=True,
            )

    st.markdown("## Command Center Alerts")
    if model["warnings"]:
        for warning in model["warnings"]:
            st.warning(warning)
    else:
        st.success("No command-center warnings detected.")

    return model


def validate_command_center_contract(
    model: Mapping[str, Any],
) -> List[str]:
    errors: List[str] = []

    if model.get("read_only") is not True:
        errors.append("V100 must remain read-only")

    if model.get("responsibility") != (
        "institutional command-center presentation only"
    ):
        errors.append("V100 responsibility contract changed")

    for item in model.get("top_opportunities") or []:
        if "v89_decision" in item:
            errors.append(
                f"{item.get('ticker', 'UNKNOWN')} exposes a decision object"
            )

    return errors


__all__ = [
    "build_command_center_model",
    "render_command_center",
    "validate_command_center_contract",
    "index_by_ticker",
]
