"""Bounded, evidence-only AI synthesis for the three Home discoveries."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
import re
from typing import Any, Callable, Mapping

from engines.semantic_fields import (
    analyst_consensus,
    analyst_scenarios,
    canonical_atlas_fair_value,
    first_present,
    scanner_trade_plan,
)


def implied_upside_pct(value: Any, current_price: Any) -> float | None:
    """Reporting-only price relationship; never an investment-model input."""
    try:
        value_number, price_number = float(value), float(current_price)
    except (TypeError, ValueError):
        return None
    if value_number <= 0 or price_number <= 0:
        return None
    return round((value_number / price_number - 1) * 100, 1)


@dataclass(frozen=True)
class BuyNowSynthesisContext:
    ticker: str
    company_name: str
    verdict: str
    opportunity_score: Any
    confidence_pct: Any
    current_price: Any
    preferred_entry: Any
    decision_model_expected_return_pct: Any
    atlas_fair_value: Any
    atlas_fair_value_upside_pct: Any
    analyst_consensus: Mapping[str, Any]
    wall_street_implied_upside_pct: Any
    analyst_scenarios: Mapping[str, Any]
    scanner_trade_plan: Mapping[str, Any]
    fundamentals: Mapping[str, Any]
    earnings: Mapping[str, Any]
    technicals: Mapping[str, Any]
    ownership: Mapping[str, Any]
    supporting_facts: tuple[str, ...]
    risks: tuple[str, ...]
    catalyst: Mapping[str, Any] | None
    evidence_gaps: tuple[str, ...]
    support_quality: str
    missing_material_domains: tuple[str, ...]
    signal_timestamp: Any


def build_buy_now_context(row: Mapping[str, Any]) -> BuyNowSynthesisContext:
    guidance = row.get("guidance_summary") if isinstance(row.get("guidance_summary"), Mapping) else {}
    facts = tuple(str(item.get("fact")) for item in guidance.get("supporting_facts", []) if isinstance(item, Mapping) and item.get("fact"))
    risks = tuple(str(item.get("risk")) for item in guidance.get("key_risks", []) if isinstance(item, Mapping) and item.get("risk"))
    entry = first_present(row, "entry_range", "Entry Range")
    entry_low = first_present(row, "preferred_entry_low", "entry_low", "Entry Low")
    entry_high = first_present(row, "preferred_entry_high", "entry_high", "Entry High")
    if not entry and entry_low is not None and entry_high is not None:
        entry = f"{entry_low}–{entry_high}"
    return BuyNowSynthesisContext(
        ticker=str(row.get("ticker") or "UNKNOWN"),
        company_name=str(first_present(row, "company", "company_name", "Company") or row.get("ticker") or "UNKNOWN"),
        verdict=str(row.get("committee_verdict") or ""),
        opportunity_score=row.get("opportunity_score"),
        confidence_pct=row.get("confidence_pct"),
        current_price=row.get("current_price") if row.get("current_price") is not None else row.get("price"),
        preferred_entry=entry,
        decision_model_expected_return_pct=row.get("decision_expected_return_pct") if row.get("decision_expected_return_pct") is not None else row.get("expected_return_pct"),
        atlas_fair_value=canonical_atlas_fair_value(row),
        atlas_fair_value_upside_pct=implied_upside_pct(canonical_atlas_fair_value(row), row.get("current_price") if row.get("current_price") is not None else row.get("price")),
        analyst_consensus=analyst_consensus(row),
        wall_street_implied_upside_pct=implied_upside_pct(analyst_consensus(row).get("mean"), row.get("current_price") if row.get("current_price") is not None else row.get("price")),
        analyst_scenarios=analyst_scenarios(row),
        scanner_trade_plan=scanner_trade_plan(row),
        fundamentals={key: first_present(row, *aliases) for key, aliases in {
            "revenue_growth": ("revenue_growth", "Revenue Growth"),
            "earnings_growth": ("earnings_growth", "Earnings Growth"),
            "gross_margin": ("gross_profit_margin", "gross_margin", "Gross Margin"),
            "operating_margin": ("operating_profit_margin", "operating_margin", "Operating Margin"),
            "free_cash_flow": ("free_cash_flow", "free_cashflow", "Free Cash Flow"),
            "operating_cash_flow": ("operating_cash_flow", "operatingCashflow", "Operating Cash Flow"),
            "roic": ("roic", "ROIC"), "roe": ("roe", "return_on_equity", "ROE"),
        }.items()},
        earnings={key: first_present(row, *aliases) for key, aliases in {
            "latest_earnings_date": ("latest_earnings_date", "Latest Earnings Date"),
            "reported_eps": ("reported_eps", "Reported EPS"), "estimated_eps": ("estimated_eps", "eps_estimate", "Estimated EPS"),
            "eps_surprise_pct": ("eps_surprise_pct", "EPS Surprise %"), "revenue_surprise_pct": ("revenue_surprise_pct", "Revenue Surprise %"),
        }.items()},
        technicals={key: first_present(row, *aliases) for key, aliases in {
            "rsi": ("rsi", "RSI"), "sma20": ("sma20", "SMA20"), "sma50": ("sma50", "SMA50"),
            "volume_ratio": ("volume_ratio", "Volume Ratio"),
        }.items()},
        ownership={key: first_present(row, *aliases) for key, aliases in {
            "institutional_ownership_pct": ("institutional_ownership_pct", "institutional_ownership"),
            "insider_ownership_pct": ("insider_ownership_pct", "insider_ownership"),
        }.items()},
        supporting_facts=facts[:3], risks=risks[:3],
        catalyst=guidance.get("next_catalyst") if isinstance(guidance.get("next_catalyst"), Mapping) else None,
        evidence_gaps=tuple(str(value) for value in guidance.get("unavailable_evidence", []) if value)[:6],
        support_quality=str(row.get("headline_support_quality") or "SUPPORTED WITH EVIDENCE GAPS"),
        missing_material_domains=tuple(str(value) for value in row.get("headline_missing_material_domains", []) if value),
        signal_timestamp=row.get("signal_as_of") or first_present(row, "generated_at", "scan_time"),
    )


def evidence_fingerprint(context: BuyNowSynthesisContext) -> str:
    payload = json.dumps(asdict(context), sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _support_gap_disclosure(context: BuyNowSynthesisContext) -> str | None:
    missing = set(context.missing_material_domains)
    labels = []
    if "profitability_cash" in missing:
        labels.append("margin/cash-flow")
    if "earnings_result" in missing:
        labels.append("latest earnings-result")
    if "verified_news_or_catalyst" in missing:
        labels.append("verified news/catalyst")
    if not labels:
        return None
    joined = labels[0] if len(labels) == 1 else (
        " and ".join(labels) if len(labels) == 2 else f"{', '.join(labels[:-1])}, and {labels[-1]}"
    )
    return f"{joined.capitalize()} confirmation remains incomplete in the current evidence."


def deterministic_buy_now_summary(context: BuyNowSynthesisContext) -> dict[str, Any]:
    facts = list(context.supporting_facts)
    risks = list(context.risks)
    catalyst = context.catalyst or {}
    why = facts[:2] or ["No ticker-specific supporting fact is available."]
    if context.atlas_fair_value is None and context.analyst_consensus.get("mean") is None:
        why.append("Valuation confirmation is limited because canonical Atlas Fair Value and Wall Street consensus are unavailable.")
    elif context.atlas_fair_value is None:
        why.append("Canonical Atlas Fair Value is unavailable, so the valuation view relies on separately labeled external analyst evidence.")
    disclosure = _support_gap_disclosure(context)
    if disclosure:
        why.append(disclosure)
    return {
        "what_atlas_thinks": f"{context.ticker} remains {context.verdict.replace('_', ' ')} on the persisted Atlas decision.",
        "what_to_do_now": f"Use the persisted preferred entry ({context.preferred_entry}) and open full research before acting." if context.preferred_entry else "Preferred-entry evidence is unavailable; open full research before acting.",
        "why_now": why[:3],
        "risks": risks[:3] or ["Ticker-specific risk evidence is unavailable."],
        "next_catalyst": catalyst if catalyst.get("date") else None,
        "thesis_change": "Reassess when the cited evidence, risk, catalyst, or persisted Atlas verdict materially changes.",
        "evidence_gaps": list(context.evidence_gaps),
        "source": "deterministic_fallback",
    }


def synthesize_buy_now(
    context: BuyNowSynthesisContext,
    generator: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Use an optional bounded generator; reject unsafe or malformed output."""
    fallback = deterministic_buy_now_summary(context)
    if generator is None:
        return fallback
    try:
        result = dict(generator(asdict(context)))
    except Exception:
        return fallback
    required = {"what_atlas_thinks", "what_to_do_now", "why_now", "risks", "thesis_change", "evidence_gaps"}
    if not required.issubset(result) or not isinstance(result.get("why_now"), list) or not isinstance(result.get("risks"), list):
        return fallback
    supplied_numbers = set(re.findall(r"-?\d+(?:\.\d+)?", json.dumps(asdict(context), default=str)))
    result_text = json.dumps(result, default=str)
    returned_numbers = set(re.findall(r"-?\d+(?:\.\d+)?", result_text))
    if not returned_numbers.issubset(supplied_numbers):
        return fallback
    normalized = result_text.lower().replace("%", "")
    atlas_upside = context.atlas_fair_value_upside_pct
    street_upside = context.wall_street_implied_upside_pct
    if street_upside is not None and street_upside != atlas_upside:
        street_number = re.escape(f"{float(street_upside):g}")
        if re.search(rf"atlas.{{0,70}}{street_number}.{{0,20}}upside", normalized):
            return fallback
    if atlas_upside is not None and atlas_upside != street_upside:
        atlas_number = re.escape(f"{float(atlas_upside):g}")
        if re.search(rf"wall street.{{0,70}}{atlas_number}.{{0,20}}upside", normalized):
            return fallback
    # Structured facts remain authoritative even when prose synthesis is AI-generated.
    result["next_catalyst"] = context.catalyst if context.catalyst and context.catalyst.get("date") else None
    result["evidence_gaps"] = list(context.evidence_gaps)
    disclosure = _support_gap_disclosure(context)
    if disclosure:
        result["why_now"] = [str(value) for value in result["why_now"][:2]] + [disclosure]
    result["source"] = "ai"
    return result


def configured_openai_generator(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """One bounded structured call; callers decide caching and call count."""
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OpenAI is not configured")
    from openai import OpenAI
    response = OpenAI(api_key=os.environ["OPENAI_API_KEY"]).chat.completions.create(
        model=os.getenv("ATLAS_LLM_MODEL", "gpt-4o-mini"),
        temperature=0.1,
        max_tokens=650,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": (
                "Synthesize only the supplied Atlas evidence. Never alter the verdict, "
                "invent a value/catalyst, or treat analyst/scenario/trade targets as Atlas Fair Value. "
                "Canonical Atlas Fair Value upside, Wall Street implied upside, and decision-model expected return "
                "are separate supplied concepts. Attribute each number to its exact named source and never call "
                "Wall Street implied upside 'Atlas upside'. "
                "Acknowledge material missing valuation, margin, cash-flow, earnings-surprise, or catalyst evidence. "
                "Respect support_quality and explicitly disclose supplied missing_material_domains. "
                "Make why_now two or three concise, company-specific sentences grounded in the supplied facts. "
                "Return JSON keys what_atlas_thinks, what_to_do_now, why_now (list), risks (list), "
                "next_catalyst, thesis_change, evidence_gaps."
            )},
            {"role": "user", "content": json.dumps(dict(payload), default=str, sort_keys=True)},
        ],
    )
    return json.loads(response.choices[0].message.content or "{}")


__all__ = ["BuyNowSynthesisContext", "build_buy_now_context", "evidence_fingerprint", "implied_upside_pct", "synthesize_buy_now", "configured_openai_generator"]
