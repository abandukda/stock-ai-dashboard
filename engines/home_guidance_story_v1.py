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
ACTION_COUNTER_STATES = ("BUY_NOW", "ACCUMULATE", "WAIT_FOR_ENTRY", "WAIT_FOR_CONFIRMATION", "DATA_LIMITED", "AVOID")


def _action_state(item: Mapping[str, Any]) -> str:
    value = item.get("customer_guidance", item.get("guidance"))
    if isinstance(value, Mapping):
        value = value.get("state")
    value = str(value or "DATA_LIMITED").upper()
    return "DATA_LIMITED" if value in {"WATCH", "WATCH_NOT_READY", "WITHHELD"} else value


def select_home_featured_cards(cards: Iterable[Mapping[str, Any]], *, limit: int = 10) -> list[Mapping[str, Any]]:
    """Return the exact immutable card collection represented by Home counters."""
    eligible = [card for card in cards if (card.get("homepage_promotion_eligibility") or {}).get("eligible") is not False]
    buys = [card for card in eligible if _action_state(card) == "BUY_NOW"]
    selected = {str(card.get("ticker") or "") for card in buys}
    return buys + [card for card in eligible if str(card.get("ticker") or "") not in selected][:max(0, limit - len(buys))]


def _counts(items: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    values = [_action_state(item) for item in items]
    return {state: values.count(state) for state in ACTION_COUNTER_STATES}


def build_home_action_count_contract(
    canonical_rows: Iterable[Mapping[str, Any]], published_cards: Iterable[Mapping[str, Any]],
    featured_cards: Iterable[Mapping[str, Any]], *, manifest: Mapping[str, Any] | None = None,
    artifact_sha256: str | None = None,
) -> dict[str, Any]:
    """Reconcile canonical, customer-published and actually rendered Home Actions."""
    canonical_items = []
    for row in canonical_rows:
        evaluation = row.get("canonical_investment_evaluation") if isinstance(row.get("canonical_investment_evaluation"), Mapping) else {}
        guidance = evaluation.get("guidance") if isinstance(evaluation.get("guidance"), Mapping) else {}
        if guidance.get("state"):
            canonical_items.append({"guidance": guidance.get("state")})
    published = list(published_cards); featured = list(featured_cards)
    eligible = [card for card in published if (card.get("homepage_promotion_eligibility") or {}).get("eligible") is not False]
    canonical_counts, published_counts = _counts(canonical_items), _counts(published)
    eligible_counts, featured_counts = _counts(eligible), _counts(featured)
    withheld = {state: max(0, canonical_counts[state] - published_counts[state]) for state in ACTION_COUNTER_STATES}
    promotion_filtered = {state: published_counts[state] - eligible_counts[state] for state in ACTION_COUNTER_STATES}
    surface_deferred = {state: eligible_counts[state] - featured_counts[state] for state in ACTION_COUNTER_STATES}
    manifest = dict(manifest) if isinstance(manifest, Mapping) else {}
    expected_publication = manifest.get("customer_publication_count")
    certification_digest = dict(manifest.get("artifact_hashes") or {}).get("market_full_scan.json")
    # Context-only refreshes may legitimately change the full artifact after
    # certification. Only an explicit counter-generation digest is comparable.
    expected_hash = manifest.get("home_counter_artifact_sha256")
    failures = []
    if expected_publication is not None and int(expected_publication) != len(published):
        failures.append("CUSTOMER_PUBLICATION_COUNT_MISMATCH")
    if expected_hash and artifact_sha256 and str(expected_hash) != str(artifact_sha256):
        failures.append("PRODUCTION_GENERATION_MISMATCH")
    if sum(published_counts.values()) != len(published):
        failures.append("PUBLISHED_COUNTER_TAXONOMY_MISMATCH")
    if sum(featured_counts.values()) != len(featured):
        failures.append("HOME_FEATURED_COUNTER_TAXONOMY_MISMATCH")
    if not len(featured) <= len(published) <= len(canonical_items):
        failures.append("ACTION_POPULATION_ORDER_INVALID")
    zero_reasons = {}
    for state in ACTION_COUNTER_STATES:
        zero_reasons[state] = (
            "HAS_HOME_FEATURED_CANDIDATES" if featured_counts[state] else
            "NO_CANONICAL_CANDIDATES" if not canonical_counts[state] else
            "CANONICAL_CANDIDATES_ALL_WITHHELD" if not published_counts[state] else
            "PUBLISHED_CANDIDATES_PROMOTION_FILTERED" if not eligible_counts[state] else
            "NO_HOME_FEATURED_CANDIDATES"
        )
    return {
        "version": "ATLAS_HOME_ACTION_COUNT_CONTRACT_V1",
        "artifact_run_id": manifest.get("run_id") or manifest.get("workflow_run_id"),
        "artifact_source_sha": manifest.get("source_commit_sha"),
        "generated_at": manifest.get("generated_at"), "certification_digest": certification_digest,
        "canonical_action_counts": canonical_counts, "customer_published_action_counts": published_counts,
        "home_featured_action_counts": featured_counts, "withheld_action_counts": withheld,
        "promotion_filtered_action_counts": promotion_filtered, "home_surface_deferred_action_counts": surface_deferred,
        "canonical_evaluated_count": len(canonical_items), "customer_publication_count": len(published),
        "home_featured_count": len(featured), "counter_sum": sum(featured_counts.values()),
        "rendered_card_count": len(featured), "zero_reasons": zero_reasons,
        "reconciled": not failures, "failure_reason": ";".join(failures) if failures else None,
        "non_scoring": True,
    }


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
    from services.targeted_revalidation import assess_targeted_revalidation
    revalidation = assess_targeted_revalidation(persisted_evaluation, current_evaluation)
    # A published completed-session evaluation is the canonical rating.  The
    # short-lived Home acquisition is optional context and must not downgrade
    # or replace that rating when its own enrichment is incomplete.
    evaluation = dict(
        current_evaluation if revalidation.get("state") == "REVALIDATED" else
        persisted_evaluation or current_evaluation or evaluate_on_demand(
        row, context={"production_decision": production_decision, "evidence_registry": {}},
    ))
    if persisted_evaluation and current_evaluation:
        # Optional synthesis/context may refresh independently, but it cannot
        # replace any canonical completed-session decision field.
        for presentation_key in (
            "atlas_ai_view", "customer_plain_english_summary", "trial_intelligence",
            "trial_presentation_fields", "phase1_completed_bar", "phase1_bar_quality",
            "phase1_home_chart",
        ):
            if current_evaluation.get(presentation_key):
                evaluation[presentation_key] = current_evaluation[presentation_key]
    trial_fields = evaluation.get("trial_presentation_fields") if isinstance(evaluation.get("trial_presentation_fields"), Mapping) else {}
    if trial_fields:
        row = {**dict(row), **dict(trial_fields)}
    certified = (
        evaluation.get("certified_customer_evaluation")
        if isinstance(evaluation.get("certified_customer_evaluation"), Mapping)
        else row.get("certified_customer_evaluation")
        if isinstance(row.get("certified_customer_evaluation"), Mapping)
        else None
    )
    from services.certified_customer_evaluation import (
        build_certified_customer_evaluation, certified_projection_matches,
    )
    if certified and not certified_projection_matches(certified, evaluation, ticker):
        certified = None
    if not certified:
        certified = build_certified_customer_evaluation({**dict(row), "canonical_investment_evaluation": evaluation})
    certified = dict(certified)
    use_certified = bool(
        isinstance(row.get("publication_certification"), Mapping)
        or isinstance(evaluation.get("publication_certification"), Mapping)
    )
    certified_fields = certified.get("fields") if isinstance(certified.get("fields"), Mapping) else {}
    certified_decision = certified.get("decision") if isinstance(certified.get("decision"), Mapping) else {}
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
    fair_value = (
        (certified_fields.get("atlas_fair_value") or {}).get("value") if use_certified else
        professional.get("atlas_base_fair_value") if valuation_status == "PUBLISHED" and professional_governed else
        valuation.get("fair_value") if valuation_status == "PUBLISHED" else None
    )
    expected_return = (
        (certified_fields.get("atlas_upside_pct") or {}).get("value") if use_certified and fair_value is not None else
        valuation.get("expected_return") if valuation_status == "PUBLISHED" and fair_value is not None else None
    )
    street = analyst_consensus(row)
    from engines.analyst_intelligence import build_analyst_intelligence
    analyst_intelligence = build_analyst_intelligence({
        **dict(row), "current_price": _first_number(row, "current_price", "price", "last_price"),
        "atlas_fair_value": fair_value, "atlas_fv_upside_pct": expected_return,
    })
    persisted_wall_street = (
        certified.get("wall_street_analysis") if use_certified and isinstance(certified.get("wall_street_analysis"), Mapping)
        else row.get("wall_street_analysis") if isinstance(row.get("wall_street_analysis"), Mapping) else {}
    )
    wall_street_analysis = dict(
        persisted_wall_street if use_certified
        else persisted_wall_street or analyst_intelligence.get("wall_street_analysis") or {}
    )
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
    governed_guidance = str((certified_decision.get("action") if use_certified else guidance.get("state")) or "DATA_LIMITED")
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
    market_price = number((certified_fields.get("price") or {}).get("value")) if use_certified else number(market.get("price"))
    live_price = number(revalidation.get("live_price"))
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
        "certified_customer_evaluation": certified if use_certified else {},
        "customer_material_authority": "certified_customer_evaluation" if use_certified else "LEGACY_PREPUBLICATION_TEST",
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
        "decision_as_of": certified.get("generated_at") or evaluation.get("evaluated_at"),
        "decision_snapshot_id": dict(certified.get("digests") or {}).get("evaluation_snapshot_id"),
        "decision_digest": dict(certified.get("digests") or {}).get("decision_digest") or evaluation.get("decision_digest"),
        "targeted_revalidation": dict(revalidation),
        "latest_rating_as_of": market.get("provider_timestamp") or evaluation.get("evaluated_at"),
        "live_entry_status": (
            "LIVE — current-session evidence validated" if live_price is not None else
            "MARKET CLOSED — revalidate next session" if market.get("latest_completed_session_valid") is True else
            "CURRENT-SESSION EVIDENCE UNAVAILABLE"
        ),
        "market_source_type": str(revalidation.get("source_type") or market.get("source_type") or "UNAVAILABLE"),
        "market_customer_label": str(revalidation.get("customer_label") or market.get("customer_label") or "Market evidence unavailable"),
        "current_price": live_price,
        "live_price": live_price,
        "price_as_of": (
            revalidation.get("price_as_of") or market.get("provider_timestamp")
            or (certified_fields.get("price") or {}).get("as_of")
            or completed_bar.get("datetime") or completed_bar.get("timestamp")
        ),
        "live_implied_upside_pct": round((float(fair_value) / live_price - 1) * 100, 1) if fair_value is not None and live_price not in (None, 0) else None,
        "display_price": observed_price,
        "display_price_label": "Current Price" if live_price is not None else str(market.get("customer_label") or ("Last-known Price" if observed_price is not None else "Price unavailable")),
        "market_evidence": {
            "status": "LIVE" if live_price is not None else ("LAST_KNOWN" if market_price is not None else "UNAVAILABLE"),
            "provider": revalidation.get("price_source") or market.get("provider"),
            "source_type": revalidation.get("source_type") or market.get("source_type"),
            "market_session": revalidation.get("market_session") or market.get("market_session"),
            "stale": revalidation.get("stale") if revalidation.get("stale") is not None else market.get("stale"),
            "provider_timestamp": revalidation.get("price_as_of") or market.get("provider_timestamp"),
            "received_timestamp": revalidation.get("received_timestamp") or market.get("received_timestamp"),
            "freshness_age_seconds": revalidation.get("freshness_age_seconds"),
            "feed_health": revalidation.get("feed_health") or market.get("feed_health"),
            "evidence_id": revalidation.get("evidence_id") or market.get("evidence_id"),
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
        "certified_customer_evaluation": certified if use_certified else {},
        "evaluation": evaluation,
        "atlas_ai_view": dict(evaluation.get("atlas_ai_view") or {}),
        "presentation_mode": "ACTIVE" if founder_guidance_v1_enabled() and current_evaluation is not None else "PREVIEW",
    }
    if use_certified:
        # Customer cards are projections of the certified snapshot.  Keep the
        # canonical evaluation attached for internal diagnostics, but remove
        # every material legacy/provider-shaped fallback from renderer inputs.
        def certified_value(name):
            item = certified_fields.get(name)
            return item.get("value") if isinstance(item, Mapping) else None

        candidate["opportunity"] = certified_decision.get("opportunity")
        candidate["decision_confidence"] = certified_decision.get("decision_confidence")
        candidate["component_coverage"] = certified_decision.get("component_coverage")
        candidate["six_pillars"] = dict(certified_decision.get("six_pillars") or {})
        candidate["trade_plan"] = dict(certified.get("trade_plan") or {})
        candidate["canonical_technical_evidence"] = dict(certified.get("technical") or {})
        candidate["volume_evidence"] = dict(certified.get("volume") or {})
        candidate["fundamentals_evidence"] = {
            name: certified_value(name) for name in (
                "revenue", "revenue_growth_pct", "eps", "eps_growth_pct",
                "gross_margin_pct", "operating_margin_pct", "net_margin_pct",
                "operating_cash_flow", "free_cash_flow", "capex", "cash", "debt",
                "net_debt", "current_ratio", "roe", "roa", "roic",
            ) if certified_value(name) is not None
        }
        prior_company_evidence = dict(candidate.get("company_evidence") or {})
        candidate["company_evidence"] = {
            "forward_eps": certified_value("forward_eps"),
            "forward_eps_period": (certified_fields.get("forward_eps") or {}).get("period"),
            "forward_revenue": certified_value("forward_revenue"),
            "forward_revenue_period": (certified_fields.get("forward_revenue") or {}).get("period"),
            "forward_pe": certified_value("forward_pe"),
            # Descriptive identity/context is non-numeric and does not become
            # financial authority. Material financial claims below remain
            # exclusively projected from certified fields.
            "business_summary": prior_company_evidence.get("business_summary"),
            "industry": prior_company_evidence.get("industry"),
            "sector": prior_company_evidence.get("sector"),
            "primary_risk": prior_company_evidence.get("primary_risk"),
        }
        candidate["valuation_driver_evidence"] = {
            "forward_eps": certified_value("forward_eps"),
            "forward_pe": certified_value("forward_pe"),
        }
        candidate["recent_catalysts"] = ()
        candidate["context_evidence"] = {"non_scoring": True, "display_scope": display_scope()}
        candidate["internal_evidence_lanes"] = {}
        # The certified price remains immutable evidence, while the dedicated
        # Twelve presentation overlay may show a newer price without changing
        # any certified decision field.
        candidate["display_price"] = live_price if live_price is not None else certified_value("price")
        candidate["last_known_price"] = certified_value("price")
    from services.home_promotion_policy import classify_homepage_promotion
    candidate["homepage_promotion_eligibility"] = classify_homepage_promotion(row)
    from services.atlas_view_summary import (
        build_certified_summary_facts, build_summary_payload, certify_customer_presentation_consistency,
        plain_english_summary, summary_evidence_map,
    )
    candidate["certified_summary_facts"] = build_certified_summary_facts(candidate)
    customer_payload = build_summary_payload(candidate)
    summary_text = plain_english_summary(customer_payload)
    consistency = certify_customer_presentation_consistency(summary_text, customer_payload)
    candidate["customer_plain_english_summary"] = {
        "version": "ATLAS_CUSTOMER_101_V2", "text": summary_text if consistency["valid"] else consistency["safe_text"],
        "evidence_map": summary_evidence_map(customer_payload), "authority": "PRESENTATION_ONLY",
        "consistency": consistency,
    }
    return candidate


def build_home_guidance_story(
    full_scan_payload: Any, recovery_payload: Any, *, watchlist_tickers: Iterable[str] = (),
    current_evaluations: Mapping[str, Mapping[str, Any]] | None = None,
    scan_timestamp: Any = None, market_today: Mapping[str, Any] | None = None,
    production_manifest: Mapping[str, Any] | None = None, production_artifact_sha256: str | None = None,
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
    home_featured_cards = select_home_featured_cards(cards)
    action_counts = build_home_action_count_contract(
        full_rows, cards, home_featured_cards, manifest=production_manifest,
        artifact_sha256=production_artifact_sha256,
    )
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
        "home_featured_cards": home_featured_cards,
        "home_action_count_contract": action_counts,
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
    "build_home_action_count_contract", "build_home_guidance_candidate", "build_home_guidance_story",
    "build_homepage_promotion_metrics", "customer_action_presentation", "select_home_featured_cards",
]
