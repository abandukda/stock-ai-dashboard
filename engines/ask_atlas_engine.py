
"""Ask Atlas AI grounded in the canonical V2 research report."""

from __future__ import annotations

from typing import Any, Mapping
import json
import re

from engines.atlas_intelligence_engine import build_executive_intelligence
from engines.semantic_fields import ai_valuation_object, valuation_families
from engines.analyst_intelligence import grounded_analyst_context
from engines.policy_intelligence import build_policy_intelligence, public_policy_context

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
    policy = report.get("policy_intelligence") or build_policy_intelligence(report)
    ai_valuation = ai_valuation_object(report)
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
        "wall_street_implied_upside_pct": valuation.get("analyst_upside_pct"),
        "decision_target": report.get("decision_valuation_target"),
        "decision_target_source": report.get("decision_target_source"),
        "decision_target_implied_upside_pct": (
            report.get("decision_expected_return_pct")
            if report.get("decision_expected_return_pct") is not None
            else report.get("expected_return_pct")
        ),
        "valuation_semantics": {
            "atlas_fair_value": "independent canonical Atlas valuation",
            "atlas_fv_upside_pct": "canonical Atlas Fair Value versus current price",
            "wall_street_consensus": "external analyst mean target",
            "wall_street_implied_upside_pct": "Wall Street consensus versus current price",
            "decision_target": "internal target attributed by decision_target_source",
        },
        "upside": valuation.get("atlas_fv_upside_pct"),
        "investment_thesis": report.get("investment_thesis"),
        "financial_summary": (sections.get("financials") or {}).get("interpretation"),
        "technical_summary": (sections.get("technical") or {}).get("interpretation"),
        "earnings_summary": (sections.get("earnings") or {}).get("interpretation"),
        "earnings_intelligence": report.get("earnings_intelligence") or {},
        "earnings_history": (report.get("earnings_intelligence") or {}).get("history") or [],
        "market_context": report.get("market_context") or {},
        "verified_company_news": (sections.get("news") or {}).get("data") or [],
        "political_summary": (sections.get("political") or {}).get("interpretation"),
        "news_summary": (sections.get("news") or {}).get("interpretation"),
        "primary_risk": (intelligence.get("key_risks") or [""])[0],
        "committee_conclusion": intelligence.get("executive_summary"),
        "upgrade_triggers": intelligence.get("upgrade_triggers"),
        "downgrade_triggers": intelligence.get("downgrade_triggers"),
        "today_move": intelligence.get("today_move"),
        "analyst_intelligence": grounded_analyst_context(analyst),
        "policy_intelligence": public_policy_context(policy),
        "ai_valuation": ai_valuation,
        # FIRST.3 exposes normalized evidence for future grounded synthesis;
        # Ask does not calculate or replace any protected decision field.
        "research_context": report.get("research_context") or {},
    }


def _question_section(question: str) -> str:
    q = question.lower()
    groups = (
        ("valuation", ("valuation", "fair value", "worth", "target", "upside")),
        ("analysts", ("analyst", "wall street", "consensus", "rating change")),
        ("earnings", ("earn", "eps", "revenue surprise", "guidance", "transcript")),
        ("technical", ("technical", "chart", "rsi", "moving average", "volume", "breakout")),
        ("news", ("news", "headline", "catalyst")),
        ("policy", ("policy", "government", "regulation", "tariff", "sanction", "contract")),
        ("risk", ("risk", "downside", "invalidate")),
    )
    return next((name for name, terms in groups if any(term in q for term in terms)), "overview")


def extract_requested_ticker(question: str, allowed_symbols: list[str]) -> str | None:
    """Return an exact ticker token; never use ticker-substring matching."""
    allowed = {str(symbol).strip().upper() for symbol in allowed_symbols if str(symbol).strip()}
    tokens = re.findall(r"(?<![A-Z0-9])([A-Z]{1,10}(?:[.-][A-Z]{1,3})?)(?![A-Z0-9])", str(question or "").upper())
    return next((token for token in tokens if token in allowed), None)


def _grounding_metadata(question: str, report: Mapping[str, Any]) -> dict[str, Any]:
    section = _question_section(question)
    sections = report.get("sections") or {}
    registry = report.get("evidence_registry") or {}
    registry_name = {"policy": "policy", "valuation": "valuation", "risk": "risk"}.get(section, section)
    if section == "overview":
        used = [
            name for name, item in registry.items()
            if isinstance(item, Mapping) and item.get("status") == "AVAILABLE"
        ]
        missing = [
            f"{name}:{item.get('status') or 'DATA_UNAVAILABLE'}"
            for name, item in registry.items()
            if isinstance(item, Mapping) and item.get("status") != "AVAILABLE"
        ]
    elif registry_name in registry:
        state = (registry.get(registry_name) or {}).get("status")
        used = [registry_name] if state == "AVAILABLE" else []
        missing = [] if state == "AVAILABLE" else [f"{registry_name}:{state or 'DATA_UNAVAILABLE'}"]
    else:
        item = sections.get(section) or {}
        available = item.get("status") in {"available", "partial"}
        used = [section] if available else []
        missing = [] if available else [f"{section}:DATA_UNAVAILABLE"]
    return {
        "ticker": str(report.get("ticker") or "UNKNOWN").upper(),
        "section": section,
        "evidence_used": used,
        "evidence_missing": missing,
        "generated_at": report.get("generated_at"),
        "framework_version": "ASK_ATLAS_GROUNDED_V1",
    }


def _deterministic_answer(question: str, report: Mapping[str, Any]) -> str:
    intelligence = report.get("intelligence") or build_executive_intelligence(report)
    q = question.lower()
    ticker = report.get("ticker") or "This stock"
    analyst = report.get("analyst_intelligence") or {}
    policy = report.get("policy_intelligence") or build_policy_intelligence(report)
    ai_valuation = ai_valuation_object(report)

    earnings_terms = (
        "earnings getting", "earnings better", "earnings worse", "quarters has",
        "quarters have", "beaten estimates", "beat estimates", "earnings trend",
        "next quarter", "eps surprise", "revenue surprise",
    )
    if "earn" in q or any(term in q for term in earnings_terms):
        earnings = report.get("earnings_intelligence") or {}
        summary = report.get("earnings_summary") or {}
        if earnings.get("semantic_status") == "NOT_APPLICABLE":
            return f"### Earnings view for {ticker}\nCorporate earnings intelligence does not apply to ETFs."
        if earnings.get("semantic_status") != "AVAILABLE":
            return (
                f"### Earnings view for {ticker}\nReported earnings history is unavailable, so Atlas cannot verify whether "
                "earnings are improving or deteriorating. Atlas has not verified management guidance or transcript evidence."
            )
        latest = earnings.get("latest_quarter") or {}
        lines = [f"### Earnings view for {ticker}", summary.get("what_happened") or "The latest quarter is available."]
        lines.append(
            f"**Recent streaks:** {earnings.get('consecutive_eps_beats', 0)} consecutive EPS beat(s); "
            f"{earnings.get('consecutive_revenue_beats', 0)} consecutive revenue beat(s)."
        )
        lines.append(
            f"**Trend:** EPS surprises are {str(earnings.get('eps_surprise_trend') or 'UNAVAILABLE').lower()}; "
            f"revenue surprises are {str(earnings.get('revenue_surprise_trend') or 'UNAVAILABLE').lower()}."
        )
        lines.append(f"**Watch next:** {summary.get('watch_next') or 'The next verified reported quarter.'}")
        lines.append("**Evidence boundary:** Atlas has not verified management guidance or transcript evidence.")
        if latest.get("report_date"):
            lines.append(f"Latest reported evidence date: {latest['report_date']}.")
        return "\n\n".join(lines)

    market_terms = (
        "risk-off", "risk off", "market-wide", "market wide", "broad market",
        "buy the dip", "don't panic", "decline company-specific", "decline company specific",
    )
    if any(term in q for term in market_terms):
        context = report.get("market_context") or {}
        regime = context.get("market_regime") or "UNAVAILABLE"
        lines = [f"### Market-stress context for {ticker}", f"**Broad-market regime:** {str(regime).replace('_', ' ').title()}."]
        if regime == "UNAVAILABLE":
            lines.append("Atlas lacks sufficient broad-market trend evidence to classify this decline as company-specific or market-wide.")
        else:
            lines.append(
                "Atlas separates broad-market pressure from company evidence. Patience or staged buying requires the company thesis to remain intact; "
                "fundamental, guidance, valuation, or technical deterioration instead warrants caution or thesis review."
            )
        lines.append("Atlas does not issue a blanket 'buy the dip' or 'don't panic' instruction.")
        return "\n\n".join(lines)

    ai_valuation_terms = (
        "ai valuation", "ai base value", "ai bear", "ai bull",
        "ai think", "ai thinks", "ai worth",
        "quant fair value", "quant fv", "valuation method", "valuation different",
        "which valuation", "how was the ai valuation",
    )
    if any(term in q for term in ai_valuation_terms):
        status = ai_valuation.get("ai_valuation_status") or "UNDER_REVIEW"
        lines = [f"### ATLAS AI Valuation for {ticker}", f"**Status:** {str(status).replace('_', ' ').title()}"]
        if status == "PUBLISHED":
            lines.extend([
                f"**Method:** {str(ai_valuation.get('ai_valuation_method') or 'Unavailable').replace('_', ' ').title()}",
                f"**12–18 month range:** ${float(ai_valuation['ai_bear_value']):,.2f} to ${float(ai_valuation['ai_bull_value']):,.2f}; base ${float(ai_valuation['ai_base_value']):,.2f}.",
                f"**Deterministic confidence:** {(ai_valuation.get('ai_valuation_confidence') or {}).get('band', 'Unavailable')}.",
            ])
            if ai_valuation.get("ai_method_rationale"):
                lines.append(f"**Why this method:** {ai_valuation['ai_method_rationale']}")
            assumptions = ai_valuation.get("ai_assumptions") or []
            if assumptions:
                lines.append("**Verified/bounded assumptions:** " + "; ".join(f"{item.get('name')}: {item.get('value')}" for item in assumptions) + ".")
        elif status == "INSUFFICIENT_JUSTIFIED_MULTIPLE_EVIDENCE":
            lines.append(
                "**Why it is not published:** Atlas has sufficient company-level financial evidence for valuation analysis, "
                "but its independent justified-multiple framework is not yet sufficiently calibrated. Atlas will not use "
                "today's market multiple, Wall Street targets, or another valuation target to manufacture a value."
            )
        else:
            gaps = ai_valuation.get("ai_evidence_gaps") or ["The research-only evidence gate was not satisfied."]
            lines.append("**Why it is not published:** " + "; ".join(str(item) for item in gaps))
        lines.append(f"**Valuation relationship:** {str(ai_valuation.get('valuation_relationship') or 'COMPARISON_UNAVAILABLE').replace('_', ' ').title()}.")
        lines.append("Atlas Quant Fair Value, ATLAS AI Valuation, and Wall Street Consensus are separate perspectives. None is automatically the correct value.")
        return "\n\n".join(lines)

    policy_terms = (
        "policy", "government", "contract", "regulation", "regulatory",
        "tariff", "trade", "export control", "sanction", "lobbying",
    )
    if any(term in q for term in policy_terms):
        status = str(policy.get("policy_overall_status") or "INSUFFICIENT_VERIFIED_EVIDENCE").replace("_", " ").title()
        lines = [f"### Policy and government intelligence for {ticker}", f"**Overall exposure:** {status}"]
        items = []
        for key in (
            "government_contract_evidence", "regulatory_evidence", "trade_tariff_evidence",
            "export_control_evidence", "legislative_policy_evidence", "public_funding_evidence", "policy_news",
        ):
            items.extend(policy.get(key) or [])
        if not items:
            lines.append("Atlas does not currently have enough verified company-specific policy evidence to classify this exposure.")
        else:
            for item in items[:5]:
                lines.append(f"- {item.get('fact')} Why it matters: {item.get('why_it_matters') or 'No additional verified consequence was supplied.'} Authority: {item.get('authority') or 'Unavailable'}. Status: {item.get('relevance_status') or 'UNKNOWN'}.")
        lines.append("Atlas does not infer political affiliation, favoritism, endorsement, or influence from this evidence.")
        return "\n\n".join(lines)

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
    grounding = _grounding_metadata(question, report)
    if not question:
        return {
            "answer": "Enter a question about this stock.",
            "mode": "validation",
            "sources_used": [],
            **grounding,
        }

    context = _compact_context(report)
    analyst_terms = (
        "wall street", "analyst", "target change", "target raise", "target cut",
        "more bullish", "more bearish", "agree with", "consensus",
    )
    analyst_question = any(term in question.lower() for term in analyst_terms)
    policy_question = any(term in question.lower() for term in (
        "policy", "government", "contract", "regulation", "regulatory",
        "tariff", "trade", "export control", "sanction", "lobbying",
    ))
    ai_valuation_question = any(term in question.lower() for term in (
        "ai valuation", "ai base value", "ai bear", "ai bull", "quant fair value",
        "ai think", "ai thinks", "ai worth", "quant fv", "valuation method",
        "valuation different", "which valuation",
    ))
    earnings_question = "earn" in question.lower() or any(term in question.lower() for term in (
        "beat estimates", "beaten estimates", "next quarter", "eps surprise", "revenue surprise",
    ))
    market_stress_question = any(term in question.lower() for term in (
        "risk-off", "risk off", "market-wide", "market wide", "broad market", "buy the dip", "don't panic",
    ))
    # Analyst answers remain deterministic so an LLM cannot introduce a firm,
    # target, action, count, or median absent from the normalized object.
    if earnings_question or market_stress_question:
        answer = _deterministic_answer(question, report)
        mode = "deterministic_earnings_grounding" if earnings_question else "deterministic_market_context_grounding"
    elif ai_valuation_question:
        answer = _deterministic_answer(question, report)
        mode = "deterministic_ai_valuation_grounding"
    elif analyst_question or policy_question:
        answer = _deterministic_answer(question, report)
        mode = "deterministic_analyst_grounding" if analyst_question else "deterministic_policy_grounding"
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
        **grounding,
    }


__all__ = ["ask_atlas", "extract_requested_ticker"]
