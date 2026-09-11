"""Presentation-only Home story built from immutable production artifacts."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any, Iterable, Mapping

from engines.atlas_guidance_v1 import founder_guidance_v1_enabled
from engines.research_context import build_production_decision
from engines.semantic_fields import analyst_consensus, canonical_atlas_fair_value, atlas_valuation_status, number
from services.on_demand_evaluation_service import evaluate_on_demand
from services.data_mode_policy import display_scope, internal_trial_mode


HOME_GUIDANCE_STORY_VERSION = "HOME_GUIDANCE_VNEXT_V1"


def build_homepage_promotion_metrics(cards: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Report Home promotion separately from immutable canonical Actions."""
    rows = list(cards)
    canonical_buy = sum(card.get("guidance") == "BUY_NOW" for card in rows)
    featured_buy = sum(
        card.get("guidance") == "BUY_NOW"
        and (card.get("homepage_promotion_eligibility") or {}).get("eligible") is True
        for card in rows
    )
    canonical_build = sum(card.get("guidance") == "ACCUMULATE" for card in rows)
    featured_build = sum(
        card.get("guidance") == "ACCUMULATE"
        and (card.get("homepage_promotion_eligibility") or {}).get("eligible") is True
        for card in rows
    )
    return {
        "canonical_buy_now_count": canonical_buy,
        "homepage_featured_buy_now_count": featured_buy,
        "promotion_filtered_buy_now_count": canonical_buy - featured_buy,
        "canonical_build_count": canonical_build,
        "homepage_featured_build_count": featured_build,
        "promotion_filtered_build_count": canonical_build - featured_build,
        "non_scoring": True,
    }
GUIDANCE_GROUPS = (
    ("Actionable Now", {"BUY_NOW", "ACCUMULATE"}),
    ("Getting Close", {"WAIT_FOR_CONFIRMATION", "WAIT_FOR_ENTRY"}),
    ("Risk / Avoid", {"AVOID"}),
    ("Data Limited", {"DATA_LIMITED"}),
    ("Certification Pending", {"WITHHELD"}),
)

HOME_FIELD_AUTHORITY = {
    "production_rank": "market_full_scan.json immutable file position",
    "guidance": "CANONICAL_INVESTMENT_EVALUATION_V1.guidance",
    "actionability": "CANONICAL_INVESTMENT_EVALUATION_V1.actionability",
    "opportunity": "CANONICAL_INVESTMENT_EVALUATION_V1.opportunity",
    "decision_confidence": "CANONICAL_INVESTMENT_EVALUATION_V1.decision_confidence",
    "scan_conviction": "persisted Full Scan conviction",
    "atlas_fair_value": "ATLAS_VALUATION_V1 published value",
    "atlas_expected_return": "ATLAS_VALUATION_V1 published expected return",
    "technical_state": "canonical technical evaluation state",
    "volume_state": "ATLAS_VOLUME_INTELLIGENCE_V1 state",
    "recovery_score": "recovery_scan.json exact-ticker row",
    "analyst_consensus": "persisted analyst consensus family",
    "trade_plan": "canonical evaluation trade_plan",
    "last_known_price": "persisted Full Scan price observation (never promoted to current quote)",
    "technical_evidence": "persisted Full Scan indicators (context only; never technical state)",
    "volume_evidence": "persisted Full Scan volume observations (context only; never volume state)",
    "fundamentals_evidence": "persisted Full Scan fundamental observations",
    "snapshot_evidence_health": "persisted Full Scan evidence-confidence label",
}

CUSTOMER_ACTION_PRESENTATION = {
    "BUY_NOW": {"label": "BUY NOW", "stars": "★★★★★", "rating": 5.0, "tone": "buy", "instruction": "Entry conditions are satisfied. ATLAS would initiate a position now."},
    "ACCUMULATE": {"label": "BUILD A POSITION", "stars": "★★★★½", "rating": 4.5, "tone": "build", "instruction": "Begin with a partial position and add only as the thesis confirms."},
    "WAIT_FOR_ENTRY": {"label": "WAIT FOR BETTER ENTRY", "stars": "★★★★", "rating": 4.0, "tone": "wait", "instruction": "Do not chase. Wait for price to return to ATLAS's preferred entry area."},
    "WAIT_FOR_CONFIRMATION": {"label": "WAIT FOR CONFIRMATION", "stars": "★★★½", "rating": 3.5, "tone": "wait", "instruction": "Stay patient. The thesis is attractive, but confirmation is incomplete."},
    "DATA_LIMITED": {"label": "WATCH", "stars": "★★½", "rating": 2.5, "tone": "watch", "instruction": "Do not enter yet. Keep it on the watchlist while the setup develops."},
    "AVOID": {"label": "AVOID", "stars": "★", "rating": 1.0, "tone": "avoid", "instruction": "ATLAS would not deploy capital here under current conditions."},
    "WITHHELD": {"label": "RATING NOT PUBLISHED", "stars": "", "rating": None, "tone": "neutral", "instruction": "ATLAS is refreshing the supporting evidence before publishing a rating."},
}


def customer_action_presentation(guidance: Any) -> dict[str, Any]:
    return dict(CUSTOMER_ACTION_PRESENTATION.get(str(guidance or "DATA_LIMITED").upper(), CUSTOMER_ACTION_PRESENTATION["DATA_LIMITED"]))


def _rows(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("rows", "results", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, Mapping)]
    return []


def _ticker(row: Mapping[str, Any]) -> str:
    return str(row.get("ticker") or row.get("Ticker") or row.get("symbol") or "").strip().upper()


def _present(value: Any) -> bool:
    return value is not None and value != "" and not isinstance(value, (Mapping, list, tuple, set))


def _technical_status(evaluation: Mapping[str, Any]) -> tuple[str, str]:
    technical = evaluation.get("technical_confirmation") if isinstance(evaluation.get("technical_confirmation"), Mapping) else {}
    return str(technical.get("state") or "UNAVAILABLE"), str(technical.get("status") or "DATA_UNAVAILABLE")


def _reason_copy(code: str) -> str:
    copy = {
        "CURRENT_MARKET_EVIDENCE_UNAVAILABLE": "Fresh market evidence is required.",
        "TECHNICAL_STRUCTURE_UNAVAILABLE": "Canonical technical confirmation is required.",
        "PRICE_EVIDENCE_UNAVAILABLE": "A valid approved price observation is required.",
        "BASIC_FUNDAMENTALS_UNAVAILABLE": "Basic canonical fundamentals are required.",
        "RISK_EVIDENCE_UNAVAILABLE": "Canonical risk evidence is required.",
        "BREAKOUT_VOLUME_NOT_CONFIRMED": "Completed-bar volume confirmation is required.",
        "CANONICAL_OPPORTUNITY_UNAVAILABLE": "Canonical Opportunity must be published.",
        "DECISION_CONFIDENCE_UNAVAILABLE": "Decision Confidence must be published.",
        "TRADE_PLAN_INCOMPLETE": "A complete canonical trade plan is required.",
        "VALUATION_CONFIRMATION_UNAVAILABLE": "Published Atlas valuation confirmation is required.",
        "PRICE_ABOVE_ENTRY_RANGE": "Price must return to an approved entry range.",
        "TECHNICAL_STATE_EXTENDED": "Technical extension must normalize.",
    }
    return copy.get(str(code), str(code).replace("_", " ").capitalize() + ".")


def _evidence_health(evaluation: Mapping[str, Any]) -> str:
    statuses = []
    for key in ("fundamentals", "risk"):
        item = evaluation.get(key) if isinstance(evaluation.get(key), Mapping) else {}
        statuses.append(str(item.get("status") or "DATA_UNAVAILABLE"))
    technical = evaluation.get("technical_confirmation") if isinstance(evaluation.get("technical_confirmation"), Mapping) else {}
    statuses.append(str(technical.get("status") or "DATA_UNAVAILABLE"))
    if statuses and all(status == "AVAILABLE" for status in statuses):
        return "COMPLETE"
    if any(status in {"AVAILABLE", "PARTIAL"} for status in statuses):
        return "PARTIAL"
    return "LIMITED"


def _first_number(row: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = number(row.get(key))
        if value is not None:
            return value
    return None


def _first_value(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value is not None and value != "":
            return value
    return None


def _snapshot_evidence(row: Mapping[str, Any], price: float | None) -> dict[str, Any]:
    """Expose persisted observations without promoting them to decision authority."""
    deep = row.get("deep_research_evidence") if isinstance(row.get("deep_research_evidence"), Mapping) else {}
    return {
        "technical": {
            "price": price,
            "rsi": _first_number(row, "rsi"),
            "sma20": _first_number(row, "sma20"),
            "sma50": _first_number(row, "sma50"),
            "sma200": _first_number(row, "sma200") if row.get("sma200") is not None else number(deep.get("sma200")),
            "support": _first_number(row, "v42_support_1", "support"),
            "resistance": _first_number(row, "v42_resistance_1", "resistance"),
            "breakout_setup": row.get("breakout_status") or row.get("setup_status"),
        },
        "volume": {
            "relative_volume": _first_number(row, "volume_ratio", "relative_volume"),
            "average_volume": _first_number(row, "avg_volume_20d", "average_volume"),
            "average_dollar_volume": _first_number(row, "avg_dollar_volume", "dollar_volume"),
        },
        "fundamentals": {
            "revenue_growth": _first_number(row, "revenue_growth"),
            "operating_margin": _first_number(row, "operating_profit_margin"),
            "free_cash_flow": _first_number(row, "free_cash_flow"),
            "cash": _first_number(row, "cash", "cash_and_equivalents"),
            "debt": _first_number(row, "total_debt", "debt"),
        },
        "completeness": row.get("evidence_confidence") or row.get("evidence_completeness"),
    }


def _internal_catalysts(row: Mapping[str, Any], *, internal: bool) -> tuple[dict[str, Any], ...]:
    ticker = _ticker(row)
    output = []
    seen: set[str] = set()
    for item in (row.get("recent_headlines") or row.get("news_evidence") or ()):
        if not isinstance(item, Mapping):
            continue
        licensed = item.get("commercial_display_allowed") is True or str(item.get("commercial_status") or "").upper() in {"LICENSED", "DISPLAY_ALLOWED"}
        if not internal and not licensed:
            continue
        headline = item.get("title") or item.get("headline")
        source = item.get("publisher") or item.get("source")
        published = item.get("published_at") or item.get("date")
        relevance = str(item.get("ticker_relevance") or "").upper()
        item_ticker = str(item.get("ticker") or "").upper()
        identity = " ".join(str(headline or "").lower().split())
        if (not headline or not source or identity in seen or
                re.search(r"\b(investor alert|class action|law firm|fraud investigation|shareholder investigation|litigation deadline|encourages? .*investors? to contact)\b", identity) or
                (item_ticker and item_ticker != ticker) or (relevance and not relevance.startswith("VERIFIED"))):
            continue
        seen.add(identity)
        evidence_id = item.get("evidence_id") or item.get("id") or "NEWS-" + hashlib.sha256(
            json.dumps([ticker, headline, source, published], separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()[:16]
        lowered = identity
        why = item.get("why_it_matters") or item.get("summary")
        if not why and any(term in lowered for term in ("earnings", "profit", "revenue", "guidance")):
            why = "This update may change the company's earnings trajectory or forward estimates."
        elif not why and any(term in lowered for term in ("fda", "regulatory", "drug", "product")):
            why = "This development may change product demand, regulatory risk, or the revenue outlook."
        elif not why and any(term in lowered for term in ("acquisition", "merger", "contract", "customer")):
            why = "This event may change future revenue, cash flow, or execution risk."
        elif not why:
            why = "This company-specific development may affect future estimates, execution, or valuation."
        output.append({**dict(item), "headline": headline, "publisher": source, "published_at": published,
                       "evidence_id": evidence_id, "why_it_matters": why,
                       "display_scope": "INTERNAL_TRIAL" if internal and not licensed else "COMMERCIAL_CUSTOMER"})
    return tuple(output[:3])


def build_home_guidance_candidate(
    row: Mapping[str, Any], *, production_rank: int,
    recovery_row: Mapping[str, Any] | None = None,
    current_evaluation: Mapping[str, Any] | None = None,
    production_snapshot_id: str | None = None,
    production_snapshot_timestamp: Any = None,
) -> dict[str, Any]:
    """Resolve one Home card without ranking or decision recalculation."""
    ticker = _ticker(row)
    production_decision = build_production_decision(row)
    persisted_evaluation = row.get("canonical_investment_evaluation") if isinstance(row.get("canonical_investment_evaluation"), Mapping) else None
    if persisted_evaluation:
        from engines.atlas_guidance_v1 import GUIDANCE_POLICY_VERSION
        persisted_guidance = persisted_evaluation.get("guidance") if isinstance(persisted_evaluation.get("guidance"), Mapping) else {}
        if persisted_guidance.get("policy_version") != GUIDANCE_POLICY_VERSION:
            persisted_evaluation = None
    # A published completed-session evaluation is the canonical rating.  The
    # short-lived Home acquisition is optional context and must not downgrade
    # or replace that rating when its own enrichment is incomplete.
    evaluation = dict(persisted_evaluation or current_evaluation or evaluate_on_demand(
        row, context={"production_decision": production_decision, "evidence_registry": {}},
    ))
    if persisted_evaluation and current_evaluation:
        # Optional synthesis/context may refresh independently, but it cannot
        # replace any canonical completed-session decision field.
        for presentation_key in ("atlas_ai_view", "customer_plain_english_summary", "trial_intelligence", "trial_presentation_fields"):
            if current_evaluation.get(presentation_key):
                evaluation[presentation_key] = current_evaluation[presentation_key]
    trial_fields = evaluation.get("trial_presentation_fields") if isinstance(evaluation.get("trial_presentation_fields"), Mapping) else {}
    if trial_fields:
        row = {**dict(row), **dict(trial_fields)}
    guidance = evaluation.get("guidance") if isinstance(evaluation.get("guidance"), Mapping) else {}
    actionability = evaluation.get("actionability") if isinstance(evaluation.get("actionability"), Mapping) else {}
    valuation = evaluation.get("atlas_valuation") if isinstance(evaluation.get("atlas_valuation"), Mapping) else {}
    professional = valuation.get("professional_valuation_v2") if isinstance(valuation.get("professional_valuation_v2"), Mapping) else {}
    professional_governed = bool(professional)
    validation = evaluation.get("valuation_validation") if isinstance(evaluation.get("valuation_validation"), Mapping) else {}
    if professional_governed and not validation:
        from services.canonical_data_validation import validate_valuation
        validation = validate_valuation({**dict(row), "canonical_investment_evaluation": evaluation})
        evaluation["valuation_validation"] = validation
    valuation_status = str(professional.get("status") if professional_governed else valuation.get("status") or atlas_valuation_status(row) or "DATA_UNAVAILABLE")
    if validation.get("customer_publication_allowed") is False:
        valuation_status = "REVIEW_REQUIRED"
    fair_value = professional.get("atlas_base_fair_value") if valuation_status == "PUBLISHED" and professional_governed else valuation.get("fair_value") if valuation_status == "PUBLISHED" else None
    expected_return = valuation.get("expected_return") if valuation_status == "PUBLISHED" and fair_value is not None else None
    street = analyst_consensus(row)
    from engines.analyst_intelligence import build_analyst_intelligence
    analyst_intelligence = build_analyst_intelligence({
        **dict(row), "current_price": _first_number(row, "current_price", "price", "last_price"),
        "atlas_fair_value": fair_value, "atlas_fv_upside_pct": expected_return,
    })
    persisted_wall_street = row.get("wall_street_analysis") if isinstance(row.get("wall_street_analysis"), Mapping) else {}
    wall_street_analysis = dict(persisted_wall_street or analyst_intelligence.get("wall_street_analysis") or {})
    internal = internal_trial_mode()
    commercial_street_allowed = (
        row.get("wall_street_commercial_display_allowed") is True
        or str(row.get("wall_street_commercial_display_status") or "").upper() in {"LICENSED", "DISPLAY_ALLOWED"}
        or row.get("twelve_wall_street_commercial_display_allowed") is True
        or row.get("analyst_targets_commercial_display_allowed") is True
        or str(row.get("analyst_commercial_status") or "").upper() in {"LICENSED", "DISPLAY_ALLOWED"}
    )
    street_display_allowed = internal or commercial_street_allowed
    if wall_street_analysis.get("status") == "WALL_STREET_DISPLAY_RESTRICTED" and not internal:
        street_display_allowed = False
    if internal and wall_street_analysis.get("status") == "WALL_STREET_DISPLAY_RESTRICTED":
        # Older artifacts intentionally discarded restricted values.  They
        # cannot be reconstructed at render time; suppress licensing copy and
        # fail honestly until context evidence is refreshed under trial policy.
        wall_street_analysis = {
            **wall_street_analysis,
            "status": "WALL_STREET_DATA_UNAVAILABLE",
            "limitations": ("A governed Wall Street context refresh is required for this snapshot.",),
            "display_authority": None,
        }
    if not street_display_allowed:
        source_status = str(wall_street_analysis.get("status") or "WALL_STREET_DATA_UNAVAILABLE")
        wall_street_analysis = {
            "status": "WALL_STREET_DATA_UNAVAILABLE", "as_of": None, "provider": None,
            "evidence_ids": (), "consensus": {}, "rating_distribution": {},
            "recent_actions": (), "estimate_context": {}, "atlas_comparison": {},
            "limitations": ("Commercial display rights are not confirmed.",), "non_scoring": True,
            "underlying_status": wall_street_analysis.get("underlying_status") or source_status,
            "display_authority": "COMMERCIAL_RIGHTS_UNCONFIRMED",
            "commercial_display_status": "COMMERCIAL_DISPLAY_NOT_CERTIFIED",
        }
    price = _first_number(row, "current_price", "price", "last_price")
    snapshot = _snapshot_evidence(row, price)
    street_upside = (
        round(((street["mean"] / price) - 1) * 100, 1)
        if street.get("mean") is not None and price is not None and price > 0 else None
    )
    reasons = tuple(str(item) for item in guidance.get("reason_codes") or ())
    governed_guidance = str(guidance.get("state") or "DATA_LIMITED")
    publication = row.get("publication_certification") if isinstance(row.get("publication_certification"), Mapping) else {}
    publication = publication or (evaluation.get("publication_certification") if isinstance(evaluation.get("publication_certification"), Mapping) else {})
    legacy_test_or_prepublication = not evaluation.get("decision_digest")
    if not publication and not legacy_test_or_prepublication and not (current_evaluation is not None and persisted_evaluation is None):
        from services.publication_governance import certify_record
        publication = certify_record({**dict(row), "canonical_investment_evaluation": evaluation})
    published_guidance = governed_guidance if not publication or publication.get("action_publication_eligible") is True else "WITHHELD"
    customer_action = customer_action_presentation(published_guidance)
    technical_state, technical_status = _technical_status(evaluation)
    volume = evaluation.get("volume_intelligence") if isinstance(evaluation.get("volume_intelligence"), Mapping) else {}
    risk = evaluation.get("risk") if isinstance(evaluation.get("risk"), Mapping) else {}
    fundamentals = evaluation.get("fundamentals") if isinstance(evaluation.get("fundamentals"), Mapping) else {}
    trial_intelligence = evaluation.get("trial_intelligence") if isinstance(evaluation.get("trial_intelligence"), Mapping) else {}
    market = evaluation.get("market_snapshot") if isinstance(evaluation.get("market_snapshot"), Mapping) else {}
    market_price = number(market.get("price"))
    live_price = market_price if market.get("fresh_current_price") is True else None
    observed_price = live_price if live_price is not None else market_price if market_price is not None else price
    completed_bar = evaluation.get("phase1_completed_bar") if isinstance(evaluation.get("phase1_completed_bar"), Mapping) else {}
    bar_quality = evaluation.get("phase1_bar_quality") if isinstance(evaluation.get("phase1_bar_quality"), Mapping) else {}
    trade_plan = dict(evaluation.get("trade_plan") or {})
    entry_low, entry_high = number(trade_plan.get("entry_low")), number(trade_plan.get("entry_high"))
    entry_relationship = (
        "WITHIN_ENTRY_RANGE" if observed_price is not None and entry_low is not None and entry_high is not None and entry_low <= observed_price <= entry_high else
        "BELOW_ENTRY_RANGE" if observed_price is not None and entry_low is not None and observed_price < entry_low else
        "ABOVE_ENTRY_RANGE" if observed_price is not None and entry_high is not None and observed_price > entry_high else
        "DATA_UNAVAILABLE"
    )
    recovery = dict(recovery_row or {})
    company = row.get("company") or row.get("company_name") or row.get("name") or ticker
    candidate = {
        "ticker": ticker,
        "display_scope": display_scope(),
        "company": str(company),
        "production_rank": int(production_rank),
        "production_snapshot_id": production_snapshot_id,
        "production_snapshot_timestamp": production_snapshot_timestamp,
        "production_source_artifact": "market_full_scan.json",
        "snapshot_membership": "CURRENT_FULL_SCAN",
        "guidance": governed_guidance,
        "customer_guidance": published_guidance,
        "governed_guidance": governed_guidance,
        "publication_certification": dict(publication),
        "opportunity_thesis": guidance.get("opportunity_thesis") or evaluation.get("opportunity_thesis"),
        "customer_action": customer_action,
        "guidance_status": str(guidance.get("status") or "DATA_UNAVAILABLE"),
        "actionability": str(actionability.get("status") or guidance.get("actionability") or "UNAVAILABLE"),
        "opportunity": evaluation.get("opportunity"),
        "decision_confidence": evaluation.get("decision_confidence"),
        "component_coverage": evaluation.get("component_coverage"),
        "six_pillars": {
            key: dict(evaluation.get(key) or {}) for key in (
                "technical_quality", "fundamental_quality", "valuation_quality",
                "risk_quality", "entry_quality", "volume_quality",
            )
        },
        "scan_conviction": number(row.get("conviction") if row.get("conviction") is not None else row.get("conviction_score")),
        "atlas_fair_value": fair_value,
        "atlas_valuation_status": valuation_status,
        "atlas_expected_return": expected_return,
        "atlas_expected_return_status": "AVAILABLE" if expected_return is not None else "DATA_UNAVAILABLE",
        "valuation_driver_evidence": {
            "method": (
                _first_value(row, "fair_value_method")
                or (_first_value(row, "target_source") if street_display_allowed or "analyst" not in str(row.get("target_source") or "").lower() else None)
            ),
            "growth_input_pct": _first_number(row, "atlas_valuation_growth_value"),
            "operating_margin_pct": _first_number(row, "atlas_valuation_operating_margin"),
            "forward_eps": _first_number(row, "forward_eps", "eps_forward"),
            "forward_pe": _first_number(row, "forward_pe"),
            "justified_pe": _first_number(row, "atlas_valuation_justified_pe"),
            "multiple_expansion_ratio": _first_number(row, "atlas_valuation_multiple_expansion_ratio"),
            "multiple_expansion_band": _first_value(row, "atlas_valuation_multiple_expansion_band"),
            "confidence": _first_number(row, "fair_value_confidence"),
            "analyst_discrepancy": _first_value(row, "atlas_valuation_analyst_discrepancy") if street_display_allowed else None,
            "assumption_flags": tuple(row.get("atlas_valuation_assumption_flags") or ()),
        },
        "technical_state": technical_state,
        "technical_status": technical_status,
        "volume_state": str(volume.get("state") or "UNAVAILABLE"),
        "volume_status": str(volume.get("status") or "DATA_UNAVAILABLE"),
        "fundamentals_status": str(fundamentals.get("status") or "DATA_UNAVAILABLE"),
        "risk_status": str(risk.get("status") or "DATA_UNAVAILABLE"),
        "trade_plan_status": "AVAILABLE" if (evaluation.get("trade_plan") or {}) else "DATA_UNAVAILABLE",
        "reason_codes": reasons,
        "why_atlas": tuple(_reason_copy(code) for code in reasons[:3]),
        "what_changes_guidance": tuple(_reason_copy(code) for code in reasons[:3]),
        "evidence_health": _evidence_health(evaluation),
        "methodology_version": evaluation.get("methodology_version"),
        "evaluation_timestamp": evaluation.get("evaluated_at"),
        "latest_rating_as_of": market.get("provider_timestamp") or evaluation.get("evaluated_at"),
        "live_entry_status": (
            "LIVE — current-session evidence validated" if live_price is not None else
            "MARKET CLOSED — revalidate next session" if market.get("latest_completed_session_valid") is True else
            "CURRENT-SESSION EVIDENCE UNAVAILABLE"
        ),
        "market_source_type": str((evaluation.get("market_snapshot") or {}).get("source_type") or "UNAVAILABLE"),
        "market_customer_label": str((evaluation.get("market_snapshot") or {}).get("customer_label") or "Market evidence unavailable"),
        "current_price": live_price,
        "display_price": observed_price,
        "display_price_label": "Current Price" if live_price is not None else str(market.get("customer_label") or ("Last-known Price" if observed_price is not None else "Price unavailable")),
        "market_evidence": {
            "status": "LIVE" if live_price is not None else ("LAST_KNOWN" if market_price is not None else "UNAVAILABLE"),
            "provider": market.get("provider"), "source_type": market.get("source_type"),
            "market_session": market.get("market_session"), "stale": market.get("stale"),
            "provider_timestamp": market.get("provider_timestamp"),
            "received_timestamp": market.get("received_timestamp"),
            "freshness_age_seconds": market.get("freshness_age_seconds"),
            "feed_health": market.get("feed_health"),
            "evidence_id": (market.get("evidence_id") or (evaluation.get("market_snapshot") or {}).get("evidence_id")),
            "methodology_version": market.get("source_methodology_version") or market.get("version"),
        },
        "latest_completed_bar": dict(completed_bar),
        "completed_bar_quality": dict(bar_quality),
        "home_chart": dict(evaluation.get("phase1_home_chart") or {}),
        "last_known_price": price,
        "last_known_price_label": "Persisted / last-known price" if price is not None else "Persisted price unavailable",
        "technical_evidence": snapshot["technical"],
        "canonical_technical_evidence": dict((evaluation.get("technical_confirmation") or {}).get("evidence") or {}),
        "volume_evidence": snapshot["volume"],
        "fundamentals_evidence": {
            **snapshot["fundamentals"],
            "revenue": _first_number(row, "latest_revenue", "reported_revenue", "revenue"),
            "eps": _first_number(row, "latest_eps", "reported_eps", "eps"),
            "gross_margin": _first_number(row, "gross_profit_margin", "gross_margin"),
            "net_margin": _first_number(row, "net_profit_margin", "net_margin"),
            "operating_cash_flow": _first_number(row, "operating_cash_flow"),
            "free_cash_flow": _first_number(row, "free_cash_flow", "fcf"),
            "cash": _first_number(row, "cash_and_equivalents", "cash"),
            "debt": _first_number(row, "total_debt", "debt"),
            "ebitda_margin": _first_number(row, "ebitda_margin"),
            "net_debt_to_ebitda": _first_number(row, "net_debt_to_ebitda", "Net Debt / EBITDA"),
            "roe": _first_number(row, "return_on_equity", "roe"),
            "roic": _first_number(row, "return_on_invested_capital", "roic"),
            "reporting_period": _first_value(row, "financial_period", "reporting_period", "fiscal_period"),
            "financial_as_of": _first_value(row, "financial_as_of", "statement_date"),
            "net_cash": _first_number(row, "net_cash"),
            "profitability_evidence": _first_value(row, "finance_agent_summary", "financial_summary"),
        },
        "company_evidence": {
            "forward_eps": _first_number(row, "forward_eps", "eps_forward"),
            "forward_eps_period": _first_value(row, "forward_eps_period"),
            "forward_revenue": _first_number(row, "forward_revenue", "revenue_forward"),
            "forward_revenue_period": _first_value(row, "forward_revenue_period"),
            "earnings_growth": _first_number(row, "earnings_growth", "eps_growth"),
            "latest_earnings_date": _first_value(row, "latest_earnings_date", "earnings_date"),
            "reported_eps": _first_number(row, "reported_eps"),
            "eps_estimate": _first_number(row, "eps_estimate"),
            "eps_surprise_pct": _first_number(row, "eps_surprise_pct", "earnings_surprise"),
            "reported_revenue": _first_number(row, "reported_revenue"),
            "revenue_estimate": _first_number(row, "revenue_estimate"),
            "revenue_surprise_pct": _first_number(row, "revenue_surprise_pct"),
            "guidance_direction": _first_value(row, "guidance_direction", "management_guidance_direction"),
            "next_earnings_date": row.get("next_earnings_date") or row.get("earnings_date"),
            "estimate_revision": _first_value(row, "estimate_revision", "estimate_revision_trend", "analyst_revision_trend"),
            "estimate_contributor_count": _first_number(row, "estimate_contributor_count", "earnings_estimate_count") if row.get("estimate_commercial_display_allowed") is True else None,
            "forward_estimate_evidence": row.get("forward_estimate_evidence") if isinstance(row.get("forward_estimate_evidence"), Mapping) else {},
            "estimate_revision_history": row.get("estimate_revision_history") if isinstance(row.get("estimate_revision_history"), Mapping) else {},
            "industry": row.get("industry"), "sector": row.get("sector"),
            "business_summary": _first_value(row, "business_summary", "company_description", "description"),
            "business_kpis": _first_value(row, "approved_business_kpis", "business_kpis", "key_business_metrics"),
            "primary_risk": _first_value(row, "primary_risk", "finance_agent_risks", "risk_tags"),
        },
        "snapshot_evidence_health": snapshot["completeness"],
        "trade_plan": trade_plan,
        "entry_relationship": entry_relationship,
        "wall_street": {
            "rating": (wall_street_analysis.get("consensus") or {}).get("consensus_rating") if street_display_allowed else None,
            "analyst_count": (wall_street_analysis.get("consensus") or {}).get("analyst_count") if street_display_allowed else None,
            "mean_target": (wall_street_analysis.get("consensus") or {}).get("target_mean") if street_display_allowed else None,
            "low_target": (wall_street_analysis.get("consensus") or {}).get("target_low") if street_display_allowed else None,
            "high_target": (wall_street_analysis.get("consensus") or {}).get("target_high") if street_display_allowed else None,
            "implied_upside": (wall_street_analysis.get("consensus") or {}).get("implied_upside_pct") if street_display_allowed else None,
            "target_actions": tuple(row.get("phase1_target_actions") or ()),
            "recent_rating_action": _first_value(row, "recent_analyst_action", "latest_upgrade_downgrade"),
            "commercial_display_status": wall_street_analysis.get("commercial_display_status") if street_display_allowed else "COMMERCIAL_LICENSE_UNCONFIRMED",
            "display_scope": "INTERNAL_TRIAL" if internal and not commercial_street_allowed else "COMMERCIAL_CUSTOMER",
        },
        "wall_street_analysis": wall_street_analysis,
        "recent_catalysts": tuple((row.get("news_context") or {}).get("records") or ()) if internal and isinstance(row.get("news_context"), Mapping) else _internal_catalysts(row, internal=internal),
        "context_evidence": {
            "normalized": {key: row.get(key) for key in ("news_context", "insider_context", "institutional_context", "congressional_context", "financial_detail_context")},
            "insider": {
                "activity": _first_value(row, "insider_activity_label", "insider_activity") if internal else None,
                "buy_count": _first_number(row, "insider_buy_count") if internal else None,
                "sell_count": _first_number(row, "insider_sell_count") if internal else None,
                "net_change": _first_number(row, "insider_net_change") if internal else None,
                "source": "FINNHUB" if internal and row.get("source_finnhub_insider") else None,
            },
            "institutional": {
                "ownership_pct": (
                    value if internal and (value := _first_number(row, "institutional_ownership_pct")) is not None and 0 <= value <= 100 else None
                ),
                "trend": _first_value(row, "institutional_change", "institutional_trend") if internal else None,
                "source": _first_value(row, "institutional_ownership_source", "institutional_source") if internal else None,
            },
            "political": {
                "summary": _first_value(row, "political_support_summary", "political_support", "political_context") if internal else None,
                "buy_count": _first_number(row, "political_buys", "congress_buys") if internal else None,
                "sell_count": _first_number(row, "political_sells", "congress_sells") if internal else None,
                "source": _first_value(row, "political_source", "congress_source") if internal else None,
            },
            "non_scoring": True, "display_scope": display_scope(),
        },
        "internal_evidence_lanes": ({
            "company_press_releases": _first_value(row, "company_press_releases", "press_releases"),
            "transcript_summary": _first_value(row, "transcript_summary", "earnings_call_summary"),
            "institutional_holders": _first_value(row, "institutional_holders", "ownership_holders"),
            "insider_transactions": _first_value(row, "insider_transactions", "insider_activity"),
            "political_transactions": _first_value(row, "political_trades", "congress_trades", "senate_trades"),
            "etf_evidence": _first_value(row, "etf_evidence", "etf_holdings", "fund_exposure"),
            "twelve_trial_intelligence": trial_intelligence,
            "display_scope": "INTERNAL_TRIAL", "non_scoring": True,
        } if internal else {}),
        "recovery": {
            "score": recovery.get("recovery_score"),
            "state": recovery.get("recovery_label") or recovery.get("recovery_state"),
            "reason": recovery.get("recovery_rebound_reason") or recovery.get("recovery_thesis"),
            "snapshot_timestamp": recovery.get("scan_time") or recovery.get("generated_at"),
        },
        "production_decision": dict(production_decision),
        "evaluation": evaluation,
        "atlas_ai_view": dict(evaluation.get("atlas_ai_view") or {}),
        "presentation_mode": "ACTIVE" if founder_guidance_v1_enabled() and current_evaluation is not None else "PREVIEW",
    }
    from services.home_promotion_policy import classify_homepage_promotion
    candidate["homepage_promotion_eligibility"] = classify_homepage_promotion(row)
    from services.atlas_view_summary import build_summary_payload, plain_english_summary, summary_evidence_map
    customer_payload = build_summary_payload(candidate)
    candidate["customer_plain_english_summary"] = {
        "version": "ATLAS_CUSTOMER_101_V1", "text": plain_english_summary(customer_payload),
        "evidence_map": summary_evidence_map(customer_payload), "authority": "PRESENTATION_ONLY",
    }
    return candidate


def build_home_guidance_story(
    full_scan_payload: Any, recovery_payload: Any, *, watchlist_tickers: Iterable[str] = (),
    current_evaluations: Mapping[str, Mapping[str, Any]] | None = None,
    scan_timestamp: Any = None, market_today: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    full_rows = _rows(full_scan_payload)
    recovery_payload_rows = _rows(recovery_payload)
    recovery_rows = {_ticker(row): row for row in recovery_payload_rows if _ticker(row)}
    evaluations = {str(key).upper(): value for key, value in (current_evaluations or {}).items()}
    timestamp = scan_timestamp or next((row.get("scan_time") or row.get("generated_at") for row in full_rows if row.get("scan_time") or row.get("generated_at")), None)
    payload_identity = full_scan_payload if isinstance(full_scan_payload, Mapping) else {}
    snapshot_id = str(
        payload_identity.get("snapshot_id") or payload_identity.get("scan_id") or
        payload_identity.get("artifact_id") or
        hashlib.sha256(json.dumps(full_rows, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
    )
    certification_contract_present = any(isinstance(row.get("publication_certification"), Mapping) for row in full_rows)
    published_rows = []
    for production_rank, row in enumerate(full_rows, start=1):
        if not certification_contract_present:
            published_rows.append((production_rank, row))
            continue
        certification = row.get("publication_certification") if isinstance(row.get("publication_certification"), Mapping) else {}
        if certification.get("customer_publication_allowed") is not True:
            continue
        certified_action = certification.get("certified_action")
        if not certified_action:
            continue
        evaluation = row.get("canonical_investment_evaluation") if isinstance(row.get("canonical_investment_evaluation"), Mapping) else {}
        guidance = evaluation.get("guidance") if isinstance(evaluation.get("guidance"), Mapping) else {}
        if str(guidance.get("state") or "") != str(certified_action):
            continue
        if certified_action == "BUY_NOW":
            revalidation = row.get("positive_action_revalidation") if isinstance(row.get("positive_action_revalidation"), Mapping) else {}
            if not revalidation and isinstance(evaluation.get("positive_action_revalidation"), Mapping):
                revalidation = evaluation.get("positive_action_revalidation") or {}
            decision_digest = row.get("decision_digest") or evaluation.get("decision_digest")
            if revalidation.get("status") != "BUY_NOW_REVALIDATED":
                continue
            if revalidation.get("source_decision_digest") != decision_digest:
                continue
        published_rows.append((production_rank, row))
    cards = [
        build_home_guidance_candidate(
            row, production_rank=production_rank, recovery_row=recovery_rows.get(_ticker(row)),
            current_evaluation=evaluations.get(_ticker(row)),
            production_snapshot_id=snapshot_id, production_snapshot_timestamp=timestamp,
        )
        for production_rank, row in published_rows
        if _ticker(row)
    ]
    groups = [
        {"title": title, "states": tuple(sorted(states)), "cards": [card for card in cards if card.get("customer_guidance", card["guidance"]) in states]}
        for title, states in GUIDANCE_GROUPS
    ]
    watched = {str(value).strip().upper() for value in watchlist_tickers if str(value).strip()}
    cards_by_ticker = {card["ticker"]: card for card in cards}
    recovery_cards = []
    for recovery_row in recovery_payload_rows:
        ticker = _ticker(recovery_row)
        if not ticker:
            continue
        if ticker in cards_by_ticker:
            recovery_cards.append(cards_by_ticker[ticker])
            continue
        recovery_cards.append({
            "ticker": ticker,
            "company": str(recovery_row.get("company") or recovery_row.get("company_name") or ticker),
            "production_rank": None,
            "snapshot_membership": "CURRENT_RECOVERY_ONLY",
            "production_snapshot_id": None,
            "production_snapshot_timestamp": None,
            "production_source_artifact": None,
            "recovery": {
                "score": recovery_row.get("recovery_score"),
                "state": recovery_row.get("recovery_label") or recovery_row.get("recovery_state"),
                "reason": recovery_row.get("recovery_rebound_reason") or recovery_row.get("recovery_thesis"),
                "snapshot_timestamp": recovery_row.get("scan_time") or recovery_row.get("generated_at"),
                "source_artifact": "recovery_scan.json",
            },
        })
    active = founder_guidance_v1_enabled() and bool(evaluations)
    return {
        "version": HOME_GUIDANCE_STORY_VERSION,
        "mode": "ACTIVE" if active else "PREVIEW",
        "title": "ATLAS Today",
        "status_label": "Current ATLAS Guidance" if active else "Founder Guidance Preview",
        "freshness_label": "Snapshot Guidance — based on latest available ATLAS evidence",
        "scan_timestamp": timestamp,
        "production_snapshot_id": snapshot_id,
        "production_source_artifact": "market_full_scan.json",
        "candidate_count": len(cards),
        "groups": groups,
        "cards": cards,
        "market_today": dict(market_today or {}),
        "homepage_promotion_metrics": build_homepage_promotion_metrics(cards),
        "recovery_cards": recovery_cards,
        "watchlist_cards": [card for card in cards if card["ticker"] in watched],
        "technical_cards": [card for card in cards if card["technical_status"] == "AVAILABLE"],
        "what_changed": {"status": "DATA_UNAVAILABLE", "message": "What Changed is not yet available for this evaluation snapshot."},
        "field_authority": dict(HOME_FIELD_AUTHORITY),
    }


__all__ = [
    "CUSTOMER_ACTION_PRESENTATION", "GUIDANCE_GROUPS", "HOME_FIELD_AUTHORITY", "HOME_GUIDANCE_STORY_VERSION",
    "build_home_guidance_candidate", "build_home_guidance_story", "build_homepage_promotion_metrics", "customer_action_presentation",
]
