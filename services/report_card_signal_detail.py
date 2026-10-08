"""Evidence-bound, read-only projection for an internal Report Card signal."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from services.report_card import HORIZONS


CONTEXT_CLASSIFICATION = "CONTEXTUAL_NON_SCORING"
UNAVAILABLE = "No approved evidence is available for this section."


def _records(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("records", "rows", "evaluations", "data"):
            if isinstance(payload.get(key), list):
                return [item for item in payload[key] if isinstance(item, Mapping)]
    return []


def load_certified_authority(root: Path | None) -> list[Mapping[str, Any]]:
    """Load persisted authority only. Never calls a provider or synthesizes data."""
    if root is None:
        return []
    path = Path(root) / "full_evaluation_pool.json"
    if not path.is_file():
        return []
    return _records(json.loads(path.read_text(encoding="utf-8")))


def _matching_authority(signal: Mapping[str, Any], rows: Iterable[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    ticker = str(signal.get("ticker") or "").upper()
    candidate = str(signal.get("candidate_digest") or "")
    snapshot = str(signal.get("evaluation_snapshot_id") or "")
    for row in rows:
        certified = row.get("certified_customer_evaluation") or {}
        digests = certified.get("digests") or {}
        if (
            str(row.get("ticker") or row.get("symbol") or "").upper() == ticker
            and candidate
            and str(row.get("candidate_digest") or "") == candidate
            and snapshot
            and str(digests.get("evaluation_snapshot_id") or "") == snapshot
        ):
            return row
    return None


def _evidence_ids(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in {"evidence_id", "endpoint"} and item:
                found.append(str(item))
            elif key == "evidence_ids" and isinstance(item, (list, tuple)):
                found.extend(str(entry) for entry in item if entry)
            elif isinstance(item, (Mapping, list, tuple)):
                found.extend(_evidence_ids(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.extend(_evidence_ids(item))
    return sorted(set(found))


def _context_section(title: str, text: str = UNAVAILABLE, evidence_ids: Iterable[str] = ()) -> dict[str, Any]:
    return {
        "title": title,
        "text": text,
        "status": "AVAILABLE" if text != UNAVAILABLE else "UNAVAILABLE",
        "context_classification": CONTEXT_CLASSIFICATION,
        "evidence_ids": sorted(set(str(item) for item in evidence_ids if item)),
    }


def _performance(observations: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_horizon = {int(item["horizon_trading_days"]): item for item in observations}
    rows = []
    for horizon in HORIZONS:
        item = by_horizon.get(horizon)
        available = bool(item and item.get("data_status") == "AVAILABLE")
        rows.append({
            "horizon_sessions": horizon,
            "status": "AVAILABLE" if available else (str(item.get("data_status")) if item else "PENDING"),
            "observed_price": item.get("observed_price") if available else None,
            "observed_at": item.get("observed_at") if available else None,
            "stock_return": item.get("stock_return") if available else None,
            "spy_return": item.get("benchmark_return") if available else None,
            "excess_return": item.get("excess_return") if available else None,
            "corporate_action_status": item.get("corporate_action_status") if item else "NOT_YET_OBSERVED",
            "price_source": item.get("price_source") if item else None,
            "benchmark_source": item.get("benchmark_source") if item else None,
        })
    return rows


def build_signal_detail(
    signal: Mapping[str, Any],
    observations: Iterable[Mapping[str, Any]],
    *,
    authority_rows: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build display facts without mutating or recomputing certified authority."""
    observations = list(observations)
    authority = _matching_authority(signal, authority_rows)
    certified = (authority or {}).get("certified_customer_evaluation") or {}
    canonical = (authority or {}).get("canonical_investment_evaluation") or {}
    revalidation = (authority or {}).get("buy_now_revalidation") or {}
    fields = certified.get("fields") or {}
    evidence_ids = sorted(set(str(item) for item in (signal.get("evidence_ids") or ()) if item))
    authority_evidence = _evidence_ids({"certified": certified, "canonical": canonical, "revalidation": revalidation})
    performance = _performance(observations)
    available = [item for item in performance if item["status"] == "AVAILABLE"]
    latest = available[-1] if available else None

    economic = revalidation.get("economic_explanation") or {}
    primary_driver = economic.get("primary_valuation_driver")
    uncertainty = economic.get("biggest_valuation_uncertainty")
    risk = (revalidation.get("invalidation_thesis") or {}).get("primary_risk")
    stop_loss = (certified.get("trade_plan") or {}).get("stop_loss")
    original_thesis = []
    if canonical.get("opportunity_thesis"):
        original_thesis.append(f'Primary thesis: {str(canonical["opportunity_thesis"]).replace("_", " ").title()}.')
    if primary_driver:
        original_thesis.append(f"Valuation support: {primary_driver}")
    technical = canonical.get("technical_confirmation") or {}
    if technical.get("status") == "AVAILABLE" and technical.get("state"):
        original_thesis.append(
            f'Technical support at issuance: {str(technical["state"]).replace("_", " ").title()} '
            f'as of {technical.get("as_of") or "the certified snapshot"}.'
        )
    fundamental = canonical.get("fundamental_quality") or {}
    if fundamental.get("status") and fundamental.get("score") is not None:
        original_thesis.append(
            f'Fundamental support at issuance: {float(fundamental["score"]):.2f} '
            f'with {str(fundamental["status"]).lower()} governed coverage.'
        )
    trade_plan = canonical.get("trade_plan") or certified.get("trade_plan") or {}
    if trade_plan.get("entry_relationship_valid") and trade_plan.get("entry_range"):
        original_thesis.append(f'Entry rationale: the reference price was inside the governed entry range {trade_plan["entry_range"]}.')
    original_risk = risk or ((canonical.get("risk") or {}).get("evidence") or {}).get("volatility_risk") or uncertainty
    if original_risk:
        original_thesis.append(f"Original primary risk: {original_risk}")
    view_change = []
    if risk:
        view_change.append(str(risk))
    if stop_loss is not None:
        view_change.append(f"Governed original stop-loss level: ${float(stop_loss):,.2f}.")

    if latest:
        relative = (
            f'At {latest["horizon_sessions"]} trading sessions, the signal return is '
            f'{float(latest["stock_return"] or 0) * 100:.2f}% versus '
            f'{float(latest["spy_return"] or 0) * 100:.2f}% for SPY; relative performance is '
            f'{float(latest["excess_return"] or 0) * 100:.2f}%.'
        )
        change = f'Latest governed observation: ${float(latest["observed_price"]):,.2f} at {latest["observed_at"]}.'
    else:
        relative = "No registered performance horizon has a governed observation yet."
        change = "Current market-state evidence has not yet been recorded in the prospective ledger."

    current_price = latest.get("observed_price") if latest else None
    reference_price = signal.get("reference_price")
    fair_value = signal.get("atlas_fair_value")
    distance_reference = (
        (float(current_price) / float(reference_price) - 1.0) * 100.0
        if current_price is not None and reference_price not in (None, 0) else None
    )
    distance_fair_value = (
        (float(current_price) / float(fair_value) - 1.0) * 100.0
        if current_price is not None and fair_value not in (None, 0) else None
    )

    market_as_of = ((revalidation.get("evidence_as_of") or {}).get("market")
                    or (canonical.get("market_data_as_of")))
    company = str((authority or {}).get("company") or signal.get("company_name") or signal.get("ticker") or "Unavailable")
    market_cap_field = fields.get("market_cap") or {}
    profile_evidence = _evidence_ids(market_cap_field)
    certified_market_cap = (market_cap_field.get("value")
                            if market_cap_field.get("certification_status") == "CERTIFIED" else None)
    profile = {
        "company_name": company,
        "ticker": signal.get("ticker"),
        "sector": (authority or {}).get("sector") if authority else None,
        "industry": (authority or {}).get("industry") if authority else None,
        "market_cap": certified_market_cap,
        "business_summary": None,
        "leadership": None,
        "headquarters": None,
        "founded": None,
        "employees": None,
        "source": "PERSISTED_CERTIFIED_AUTHORITY" if authority else "UNAVAILABLE",
        "source_timestamp": market_cap_field.get("as_of") or market_as_of,
        "freshness": "CERTIFIED_AT_ISSUANCE" if authority else "UNAVAILABLE",
        "evidence_ids": profile_evidence,
    }

    return {
        "signal_id": signal.get("signal_id"),
        "ticker": signal.get("ticker"),
        "company_name": company,
        "customer_visible": False,
        "public_performance_claims_allowed": False,
        "authority_status": "EXACT_CERTIFIED_MATCH" if authority else "CERTIFIED_ENRICHMENT_UNAVAILABLE",
        "generation_mode": "DETERMINISTIC_GROUNDED_SYNTHESIS",
        "context_classification": CONTEXT_CLASSIFICATION,
        "original_signal": {
            "action": signal.get("canonical_recommendation"),
            "timestamp": signal.get("first_seen_at"),
            "reference_price": signal.get("reference_price"),
            "reference_price_timestamp": signal.get("reference_price_timestamp"),
            "atlas_fair_value": signal.get("atlas_fair_value"),
            "opportunity": signal.get("opportunity"),
            "confidence": signal.get("decision_confidence"),
            "candidate_digest": signal.get("candidate_digest"),
            "publication_digest": signal.get("publication_digest"),
            "evaluation_snapshot_id": signal.get("evaluation_snapshot_id"),
            "evidence_ids": evidence_ids,
        },
        "current_market_state": {
            "status": "LAST_GOVERNED_OBSERVATION" if latest else "UNAVAILABLE",
            "price": current_price,
            "observed_at": latest.get("observed_at") if latest else None,
            "source": latest.get("price_source") if latest else None,
            "is_live": False,
            "day_change": None,
            "volume": None,
            "session_status": "FINALIZED_GOVERNED_OBSERVATION" if latest else "UNAVAILABLE",
            "freshness": latest.get("observed_at") if latest else None,
            "distance_to_reference_pct": distance_reference,
            "distance_to_fair_value_pct": distance_fair_value,
        },
        "performance": performance,
        "digest": [
            _context_section("Relative performance", relative, evidence_ids),
            _context_section("What changed since the signal", change, evidence_ids),
            _context_section("Catalysts", evidence_ids=()),
            _context_section("Headwinds and risk", str(risk or uncertainty) if (risk or uncertainty) else UNAVAILABLE, authority_evidence),
            _context_section("Earnings and management", evidence_ids=()),
            _context_section("Market context", evidence_ids=()),
        ],
        "original_thesis": original_thesis,
        "view_change_conditions": view_change,
        "company_profile": profile,
        "event_timeline": [],
        "event_timeline_status": "No approved post-signal event evidence is available.",
        "move_attribution": {
            "status": "INSUFFICIENT_APPROVED_EVIDENCE",
            "text": "No causal attribution is made without approved post-signal evidence.",
            "positive_drivers": [],
            "negative_drivers": [],
            "uncertain_or_not_attributable": ["No approved causal event evidence is available."],
            "context_classification": CONTEXT_CLASSIFICATION,
            "evidence_ids": [],
        },
    }


__all__ = ["CONTEXT_CLASSIFICATION", "build_signal_detail", "load_certified_authority"]
