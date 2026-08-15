
"""Ask Atlas AI grounded in the canonical V2 research report."""

from __future__ import annotations

from typing import Any, Mapping
import json

from engines.atlas_intelligence_engine import build_executive_intelligence
from engines.semantic_fields import valuation_families
from engines.analyst_intelligence import grounded_analyst_context

try:
    from services.ai_synthesis import answer_ticker_question, llm_is_configured
except Exception:
    answer_ticker_question = None

    def llm_is_configured() -> bool:
        return False


def _compact_context(report: Mapping[str, Any]) -> dict[str, Any]:
    intelligence = report.get("intelligence") or build_executive_intelligence(report)
    sections = report.get("sections") or {}
    valuation = report.get("valuation_families") or valuation_families(report)
    analyst = report.get("analyst_intelligence") or {}
    return {
        "ticker": report.get("ticker"),
        "company": report.get("company"),
        "decision": report.get("committee_verdict"),
        "opportunity": report.get("opportunity_score"),
        "conviction": report.get("confidence_pct"),
        "current_price": report.get("current_price"),
        "atlas_fair_value": valuation.get("atlas_fair_value"),
        "atlas_valuation_status": valuation.get("atlas_valuation_status"),
        "atlas_fv_upside_pct": valuation.get("atlas_fv_upside_pct"),
        "analyst_consensus": valuation.get("analyst_target_mean"),
        "analyst_low": valuation.get("analyst_target_low"),
        "analyst_high": valuation.get("analyst_target_high"),
        "analyst_implied_upside_pct": valuation.get("analyst_upside_pct"),
        "upside": valuation.get("atlas_fv_upside_pct"),
        "investment_thesis": report.get("investment_thesis"),
        "financial_summary": (sections.get("financials") or {}).get("interpretation"),
        "technical_summary": (sections.get("technical") or {}).get("interpretation"),
        "earnings_summary": (sections.get("earnings") or {}).get("interpretation"),
        "political_summary": (sections.get("political") or {}).get("interpretation"),
        "news_summary": (sections.get("news") or {}).get("interpretation"),
        "primary_risk": (intelligence.get("key_risks") or [""])[0],
        "committee_conclusion": intelligence.get("executive_summary"),
        "upgrade_triggers": intelligence.get("upgrade_triggers"),
        "downgrade_triggers": intelligence.get("downgrade_triggers"),
        "today_move": intelligence.get("today_move"),
        "analyst_intelligence": grounded_analyst_context(analyst),
    }


def _deterministic_answer(question: str, report: Mapping[str, Any]) -> str:
    intelligence = report.get("intelligence") or build_executive_intelligence(report)
    q = question.lower()
    ticker = report.get("ticker") or "This stock"
    analyst = report.get("analyst_intelligence") or {}

    analyst_terms = (
        "wall street", "analyst", "target change", "target raise", "target cut",
        "more bullish", "more bearish", "agree with", "consensus",
    )
    if any(term in q for term in analyst_terms):
        mean = analyst.get("wall_street_mean_target")
        upside = analyst.get("wall_street_implied_upside_pct")
        coverage = analyst.get("analyst_coverage")
        relationship = analyst.get("atlas_street_relationship") or "VALUATION COMPARISON UNAVAILABLE"
        lines = [f"### Wall Street and Atlas on {ticker}"]
        if mean is not None:
            detail = f"Wall Street consensus is ${float(mean):,.2f}"
            if upside is not None:
                detail += f", implying {float(upside):+.1f}% from the current price"
            if coverage is not None:
                detail += f" with {int(coverage)} covering analysts"
            lines.append(detail + ".")
        else:
            lines.append("Wall Street consensus is not available in the current structured evidence.")
        for days in (30, 90):
            trend = analyst.get(f"trend_{days}d") or {}
            lines.append(
                f"**{days}-day trend:** {trend.get('classification', 'STABLE')} "
                f"({trend.get('positive', 0)} positive, {trend.get('negative', 0)} negative, "
                f"{trend.get('neutral', 0)} neutral)."
            )
        actions = analyst.get("recent_actions") or []
        if actions:
            lines.append("**Recent structured actions:**")
            for action in actions:
                firm = action.get("firm")
                label = action.get("primary_action")
                target = action.get("current_target")
                target_text = f" to ${float(target):,.2f}" if target is not None else ""
                lines.append(f"- {firm}: {label}{target_text} ({str(action.get('date') or '')[:10]}).")
        lines.append(f"**Atlas/Street relationship:** {relationship}. {analyst.get('atlas_street_divergence_message') or ''}")
        lines.append(
            f"**Decision context:** Atlas's {str(report.get('committee_verdict') or 'MONITOR').replace('_', ' ')} "
            "decision is produced by the existing multi-component decision model; Wall Street consensus and canonical Atlas valuation remain separate evidence."
        )
        return "\n\n".join(lines)

    if "move" in q or "drop" in q or "up today" in q or "down today" in q or "volume" in q:
        move = intelligence["today_move"]
        facts = "\n".join(f"- {item}" for item in move.get("verified_facts") or [])
        inferences = "\n".join(f"- {item}" for item in move.get("atlas_inferences") or [])
        limits = "\n".join(f"- {item}" for item in move.get("data_limitations") or [])
        return (
            f"### {ticker}: today's move\n"
            f"**Explanation confidence:** {move.get('explanation_confidence_pct', 0)}%\n\n"
            f"**Verified facts**\n{facts or '- No verified intraday facts loaded.'}\n\n"
            f"**Atlas inference**\n{inferences}\n\n"
            f"**Data limitations**\n{limits or '- No material limitations identified.'}"
        )

    if "upgrade" in q or "buy now" in q or "rating" in q or "accumulate" in q:
        upgrades = "\n".join(f"- {item}" for item in intelligence.get("upgrade_triggers") or [])
        downgrades = "\n".join(f"- {item}" for item in intelligence.get("downgrade_triggers") or [])
        return (
            f"### Why Atlas rates {ticker} {str(report.get('committee_verdict') or 'MONITOR').replace('_', ' ').title()}\n"
            f"{intelligence.get('executive_summary')}\n\n"
            f"**What could upgrade the rating**\n{upgrades}\n\n"
            f"**What could downgrade the rating**\n{downgrades}"
        )

    if "risk" in q:
        risks = "\n".join(f"- {item}" for item in intelligence.get("key_risks") or [])
        return f"### Main risks for {ticker}\n{risks or '- No structured risks were populated.'}"

    if "earn" in q:
        section = (report.get("sections") or {}).get("earnings") or {}
        return (
            f"### Earnings view for {ticker}\n"
            f"{section.get('interpretation') or 'Structured earnings evidence is not available.'}"
        )

    if "beginner" in q or "simple" in q or "explain" in q:
        return (
            f"### {ticker} in plain English\n"
            f"{intelligence.get('executive_summary')}\n\n"
            "Atlas is balancing business quality, valuation, chart strength, analyst support, "
            "news, and risk. A higher rating requires several of these signals to agree."
        )

    supports = "\n".join(f"- {item}" for item in intelligence.get("why_atlas_supports_it") or [])
    risks = "\n".join(f"- {item}" for item in intelligence.get("key_risks") or [])
    return (
        f"### Atlas answer for {ticker}\n"
        f"{intelligence.get('executive_summary')}\n\n"
        f"**Supporting evidence**\n{supports}\n\n"
        f"**Key risks**\n{risks}"
    )


def ask_atlas(question: str, report: Mapping[str, Any]) -> dict[str, Any]:
    question = str(question or "").strip()
    if not question:
        return {
            "answer": "Enter a question about this stock.",
            "mode": "validation",
            "sources_used": [],
        }

    context = _compact_context(report)
    analyst_terms = (
        "wall street", "analyst", "target change", "target raise", "target cut",
        "more bullish", "more bearish", "agree with", "consensus",
    )
    analyst_question = any(term in question.lower() for term in analyst_terms)
    # Analyst answers remain deterministic so an LLM cannot introduce a firm,
    # target, action, count, or median absent from the normalized object.
    if analyst_question:
        answer = _deterministic_answer(question, report)
        mode = "deterministic_analyst_grounding"
    elif llm_is_configured() and callable(answer_ticker_question):
        try:
            answer = answer_ticker_question(question, context)
            mode = "llm_grounded"
        except Exception:
            answer = _deterministic_answer(question, report)
            mode = "deterministic_fallback"
    else:
        answer = _deterministic_answer(question, report)
        mode = "deterministic"

    sections = report.get("sections") or {}
    sources = [
        name
        for name, section in sections.items()
        if isinstance(section, Mapping)
        and section.get("status") in {"available", "partial"}
    ]
    return {
        "answer": answer,
        "mode": mode,
        "sources_used": sources,
        "generated_from": report.get("generated_at"),
    }


__all__ = ["ask_atlas"]
