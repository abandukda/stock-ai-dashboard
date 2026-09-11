"""Fail-closed customer projection for one exact canonical evaluation snapshot.

This module is publication architecture, not investment methodology.  It never
calculates a score or changes an Action; it only decides which already-canonical
values are safe to expose and independently reconciles critical arithmetic.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any, Mapping

from services.canonical_data_validation import CERTIFIED, CERTIFIED_HIGH_UNCERTAINTY

VERSION = "ATLAS_CERTIFIED_CUSTOMER_EVALUATION_V1"
PUBLISHABLE = {CERTIFIED, CERTIFIED_HIGH_UNCERTAINTY}


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _num(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _close(left: Any, right: Any, tolerance: float = 0.005) -> bool:
    a, b = _num(left), _num(right)
    if a is None or b is None:
        return False
    return abs(a - b) <= max(0.01, abs(b) * tolerance)


def _field(name: str, value: Any, *, status: str, source: Any = None,
           evidence_ids: Any = (), as_of: Any = None, period: Any = None,
           period_type: Any = None, basis: Any = None, currency: Any = None,
           unit: Any = None, transformation: Any = None, snapshot_id: str,
           limitations: Any = ()) -> dict[str, Any]:
    ids = tuple(str(item) for item in (evidence_ids or ()) if item)
    safe = status in PUBLISHABLE and value is not None and bool(source) and bool(ids) and bool(as_of)
    return {
        "field_name": name, "value": value if safe else None,
        "certification_status": status,
        "provider": source, "evidence_ids": ids, "as_of": as_of,
        "period": period, "period_type": period_type, "basis": basis,
        "currency": currency, "unit": unit, "transformation": transformation,
        "snapshot_id": snapshot_id, "limitations": tuple(limitations or ()),
    }


def _input_lineage(evaluation: Mapping[str, Any]) -> dict[str, Any]:
    valuation = _mapping(evaluation.get("valuation_validation"))
    return _mapping(valuation.get("input_lineage"))


def _snapshot_id_for(ticker: str, evaluation: Mapping[str, Any]) -> str:
    market = _mapping(evaluation.get("market_snapshot"))
    return _digest({
        "ticker": ticker, "evaluation": evaluation.get("input_digest"),
        "decision": evaluation.get("decision_digest"), "market": market.get("evidence_id"),
        "evaluated_at": evaluation.get("evaluated_at"),
    })


def certified_projection_matches(
    projection: Mapping[str, Any], evaluation: Mapping[str, Any], ticker: str,
) -> bool:
    """Return true only when a persisted customer projection is for this exact snapshot."""
    digests = _mapping(projection.get("digests"))
    normalized = str(ticker or evaluation.get("ticker") or "").upper()
    return (
        projection.get("version") == VERSION
        and str(projection.get("ticker") or "").upper() == normalized
        and digests.get("evaluation_snapshot_id") == _snapshot_id_for(normalized, evaluation)
        and digests.get("decision_digest") == evaluation.get("decision_digest")
    )


def _lineage_field(
    fields: dict[str, dict[str, Any]], name: str, value: Any, lineage: Mapping[str, Any],
    *, status: str, snapshot_id: str, default_source: Any = None,
    default_as_of: Any = None, default_ids: Any = (), unit: Any = None,
    basis: Any = None,
) -> None:
    item = _mapping(lineage.get(name))
    evidence_ids = (item.get("evidence_id"),) if item.get("evidence_id") else default_ids
    fields[name] = _field(
        name, value, status=status, source=item.get("source") or default_source,
        evidence_ids=evidence_ids, as_of=item.get("as_of") or default_as_of,
        period=item.get("period"), period_type=item.get("period_type"),
        basis=item.get("basis") or basis, currency=item.get("currency"),
        unit=item.get("unit") or unit, transformation=item.get("transformation"),
        snapshot_id=snapshot_id,
    )


def build_certified_customer_evaluation(row: Mapping[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """Build the only material-data contract accepted by customer renderers."""
    evaluation = _mapping(row.get("canonical_investment_evaluation"))
    publication = _mapping(row.get("publication_certification")) or _mapping(evaluation.get("publication_certification"))
    if not publication:
        from services.publication_governance import certify_record
        publication = certify_record(row, now=now)
    ticker = str(row.get("ticker") or row.get("symbol") or evaluation.get("ticker") or "").upper()
    market = _mapping(evaluation.get("market_snapshot"))
    fundamentals = _mapping(evaluation.get("fundamentals"))
    fundamental_data = _mapping(fundamentals.get("data"))
    technical = _mapping(evaluation.get("technical_confirmation"))
    risk = _mapping(evaluation.get("risk"))
    trade = _mapping(evaluation.get("trade_plan"))
    volume = _mapping(evaluation.get("volume_intelligence"))
    valuation = _mapping(evaluation.get("valuation_validation"))
    atlas_valuation = _mapping(evaluation.get("atlas_valuation"))
    lineage = _input_lineage(evaluation)
    components = _mapping(publication.get("components"))
    snapshot_id = _snapshot_id_for(ticker, evaluation)

    market_state = _mapping(components.get("market")).get("state") or "INSUFFICIENT_INPUTS"
    fundamentals_state = _mapping(components.get("fundamentals")).get("state") or "INSUFFICIENT_INPUTS"
    valuation_state = _mapping(components.get("valuation")).get("state") or "INSUFFICIENT_INPUTS"
    decision_state = _mapping(components.get("decision")).get("state") or "INSUFFICIENT_INPUTS"
    market_ids = (market.get("evidence_id"),)
    fundamental_ids = fundamentals.get("evidence_ids") or ()
    fundamental_as_of = fundamentals.get("as_of") or _mapping(evaluation.get("evidence_as_of")).get("fundamentals")

    fields: dict[str, dict[str, Any]] = {}
    fields["price"] = _field("price", market.get("price"), status=market_state,
        source=market.get("provider"), evidence_ids=market_ids, as_of=market.get("provider_timestamp"),
        basis=market.get("source_type"), currency=market.get("currency") or "USD", unit="PER_SHARE",
        snapshot_id=snapshot_id)
    market_values = {
        "market_cap": lineage.get("market_cap", {}).get("canonical_value") if isinstance(lineage.get("market_cap"), Mapping) else None,
        "enterprise_value": lineage.get("enterprise_value", {}).get("canonical_value") if isinstance(lineage.get("enterprise_value"), Mapping) else None,
        "shares_outstanding": lineage.get("current_shares_outstanding", {}).get("canonical_value") if isinstance(lineage.get("current_shares_outstanding"), Mapping) else None,
        "economic_shares": lineage.get("diluted_shares", {}).get("canonical_value") if isinstance(lineage.get("diluted_shares"), Mapping) else None,
        "adr_ads_ratio": lineage.get("adr_ads_ratio", {}).get("canonical_value") if isinstance(lineage.get("adr_ads_ratio"), Mapping) else None,
    }
    lineage_names = {
        "shares_outstanding": "current_shares_outstanding",
        "economic_shares": "diluted_shares",
    }
    for name, value in market_values.items():
        _lineage_field(
            fields, name, value, {name: lineage.get(lineage_names.get(name, name))},
            status=market_state, snapshot_id=snapshot_id,
            default_source=market.get("provider"), default_as_of=market.get("provider_timestamp"),
            default_ids=market_ids, unit="SHARES" if "shares" in name else "CURRENCY",
        )
    for name in ("revenue", "eps", "revenue_growth_pct", "eps_growth_pct", "gross_margin_pct",
                 "operating_margin_pct", "net_margin_pct", "operating_cash_flow", "free_cash_flow",
                 "capex", "cash", "debt", "net_debt", "current_ratio", "roe", "roa", "roic"):
        input_item = _mapping(lineage.get(name))
        aliases = {"roe": "roe_pct", "roic": "roic_pct"}
        value = fundamental_data.get(name)
        if value is None:
            value = fundamental_data.get(aliases.get(name))
        if value is None:
            value = input_item.get("canonical_value") if input_item.get("canonical_value") is not None else input_item.get("value")
        if value is None:
            value = evaluation.get("trial_presentation_fields", {}).get(name) if isinstance(evaluation.get("trial_presentation_fields"), Mapping) else None
        ids = (input_item.get("evidence_id"),) if input_item.get("evidence_id") else fundamental_ids
        fields[name] = _field(name, value, status=fundamentals_state,
            source=input_item.get("source") or fundamentals.get("source"), evidence_ids=ids,
            as_of=input_item.get("as_of") or fundamental_as_of, period=input_item.get("period"),
            period_type=input_item.get("period_type"), basis=input_item.get("basis"),
            currency=input_item.get("currency") or "USD", unit=input_item.get("unit"),
            transformation=input_item.get("transformation"), snapshot_id=snapshot_id)

    # Independent Stage-B accounting reconstruction. Missing components never
    # become neutral: the dependent reconstructed field is withheld.
    recon: dict[str, Any] = {}
    certified_market_price = _num(fields["price"]["value"])
    # Market capitalization uses current governed shares outstanding.  The
    # diluted/economic denominator remains separately certified for per-share
    # valuation bridges and must not silently replace the market-cap basis.
    economic_shares = _num(fields["shares_outstanding"]["value"] or fields["economic_shares"]["value"])
    if certified_market_price is not None and economic_shares is not None:
        recon["market_cap"] = certified_market_price * economic_shares
    revenue = _num(fields["revenue"]["value"])
    operating_income_item = _mapping(lineage.get("operating_income"))
    operating_income = _num(operating_income_item.get("canonical_value") or operating_income_item.get("value"))
    if revenue and operating_income is not None:
        recon["operating_margin_pct"] = operating_income / revenue
    ocf, capex = _num(fields["operating_cash_flow"]["value"]), _num(fields["capex"]["value"])
    if ocf is not None and capex is not None:
        recon["free_cash_flow"] = ocf - abs(capex)
    cash, debt = _num(fields["cash"]["value"]), _num(fields["debt"]["value"])
    if cash is not None and debt is not None:
        recon["net_debt"] = debt - cash
    accounting_mismatches = [name for name, value in recon.items()
                             if fields.get(name, {}).get("value") is not None and not _close(value, fields[name]["value"])]
    for name in accounting_mismatches:
        fields[name]["value"] = None
        fields[name]["certification_status"] = "REVIEW_REQUIRED"
        fields[name]["limitations"] = ("Independent accounting reconstruction did not reconcile.",)
    dependency_mismatches = tuple(name for name in accounting_mismatches if name != "market_cap")

    estimate_fields = {}
    trial_fields = _mapping(evaluation.get("trial_presentation_fields"))
    estimate_evidence = _mapping(trial_fields.get("forward_estimate_evidence"))
    estimate_evidence_ids = tuple(estimate_evidence.get("evidence_ids") or ())
    for name in ("forward_eps", "forward_revenue"):
        item = _mapping(lineage.get(name))
        value = item.get("canonical_value") if item else None
        period = item.get("period")
        item_ids = (item.get("evidence_id"),) if item.get("evidence_id") else estimate_evidence_ids
        explicitly_stale = item.get("stale") is True or str(item.get("freshness_status") or "").upper() == "STALE"
        historical_substitution = str(item.get("period_type") or "").upper() == "TTM"
        status = CERTIFIED if value is not None and period and item_ids and not explicitly_stale and not historical_substitution else "INSUFFICIENT_INPUTS"
        estimate_fields[name] = _field(name, value, status=status, source=item.get("source"),
            evidence_ids=item_ids, as_of=item.get("as_of") or estimate_evidence.get("as_of"), period=period,
            period_type=item.get("period_type"), basis=item.get("basis"), currency=item.get("currency"),
            unit=item.get("unit"), transformation=item.get("transformation"), snapshot_id=snapshot_id,
            limitations=() if status == CERTIFIED else ("Forward period or governed evidence is incomplete.",))
    eps_period = estimate_fields["forward_eps"].get("period")
    revenue_period = estimate_fields["forward_revenue"].get("period")
    if eps_period and revenue_period and eps_period != revenue_period:
        for name in ("forward_eps", "forward_revenue"):
            estimate_fields[name]["value"] = None
            estimate_fields[name]["certification_status"] = "REVIEW_REQUIRED"
            estimate_fields[name]["limitations"] = ("Forward EPS and revenue fiscal periods do not reconcile.",)
    fields.update(estimate_fields)
    forward_eps = _num(estimate_fields["forward_eps"].get("value"))
    certified_price = _num(fields["price"].get("value"))
    if forward_eps and certified_price:
        fields["forward_pe"] = _field(
            "forward_pe", certified_price / forward_eps, status=CERTIFIED,
            source="STAGE_B_RECONSTRUCTION",
            evidence_ids=tuple({*estimate_fields["forward_eps"]["evidence_ids"], *fields["price"]["evidence_ids"]}),
            as_of=max(str(estimate_fields["forward_eps"]["as_of"]), str(fields["price"]["as_of"])),
            period=estimate_fields["forward_eps"]["period"], period_type="FORWARD",
            basis="CERTIFIED_PRICE_OVER_FORWARD_EPS", unit="MULTIPLE", snapshot_id=snapshot_id,
        )
    else:
        fields["forward_pe"] = _field(
            "forward_pe", None, status="INSUFFICIENT_INPUTS", snapshot_id=snapshot_id,
            limitations=("Certified price and forward EPS are required.",),
        )

    fv = atlas_valuation.get("fair_value") or atlas_valuation.get("base_fair_value") or valuation.get("published_fair_value")
    upside = atlas_valuation.get("expected_return")
    if upside is None:
        upside = atlas_valuation.get("expected_return_pct") or atlas_valuation.get("upside_pct")
    valuation_ids = tuple(evaluation.get("evidence_ids") or ())
    valuation_as_of = valuation.get("valuation_as_of") or evaluation.get("evaluated_at")
    fields["atlas_fair_value"] = _field("atlas_fair_value", fv, status=valuation_state,
        source=valuation.get("version") or atlas_valuation.get("methodology_version"), evidence_ids=valuation_ids,
        as_of=valuation_as_of, period=valuation.get("forecast_period"), basis="RECONCILED_METHODS",
        currency="USD", unit="PER_SHARE", snapshot_id=snapshot_id)
    price = _num(fields["price"]["value"])
    rebuilt_upside = ((float(fields["atlas_fair_value"]["value"]) / price) - 1) * 100 if price and fields["atlas_fair_value"]["value"] is not None else None
    if upside is None:
        upside = rebuilt_upside
    upside_status = valuation_state if rebuilt_upside is not None and _close(upside, rebuilt_upside, 0.01) else "REVIEW_REQUIRED"
    fields["atlas_upside_pct"] = _field("atlas_upside_pct", upside, status=upside_status,
        source=valuation.get("version") or atlas_valuation.get("methodology_version"), evidence_ids=valuation_ids,
        as_of=valuation_as_of, basis="FAIR_VALUE_OVER_CERTIFIED_PRICE", unit="PERCENT",
        snapshot_id=snapshot_id, limitations=() if upside_status in PUBLISHABLE else ("Stage-B upside reconstruction did not reconcile.",))
    if upside_status not in PUBLISHABLE:
        valuation_state = "REVIEW_REQUIRED"

    professional = _mapping(atlas_valuation.get("professional_valuation_v2"))
    warnings = tuple(str(item) for item in (valuation.get("warnings") or ()))
    model_weights = _mapping(professional.get("model_weights") or valuation.get("model_weights"))
    extraordinary_certified = (
        valuation_state == CERTIFIED
        and len([weight for weight in model_weights.values() if (_num(weight) or 0) > 0]) >= 2
        and (_num(professional.get("valuation_confidence")) or 0) >= 60
        and not warnings
        and str(professional.get("scenario_status") or "").upper() in {"CERTIFIED", "PUBLISHED"}
    )
    extraordinary_block = rebuilt_upside is not None and rebuilt_upside > 500 and not extraordinary_certified
    if extraordinary_block:
        for name in ("atlas_fair_value", "atlas_upside_pct"):
            fields[name]["value"] = None
            fields[name]["certification_status"] = "REVIEW_REQUIRED"
            fields[name]["limitations"] = ("Extraordinary valuation could not pass enhanced reconstruction and corroboration.",)
        valuation_state = "REVIEW_REQUIRED"

    action = _mapping(evaluation.get("guidance")).get("state")
    decision_safe = (
        publication.get("customer_publication_allowed") is True
        and decision_state in PUBLISHABLE
        and valuation_state in PUBLISHABLE
        and not dependency_mismatches
    )
    decision = {
        "six_pillars": {key: evaluation.get(key) for key in ("technical_quality", "fundamental_quality", "valuation_quality", "risk_quality", "entry_quality", "volume_quality")} if decision_safe else {},
        "opportunity": evaluation.get("opportunity") if decision_safe else None,
        "decision_confidence": evaluation.get("decision_confidence") if decision_safe else None,
        "component_coverage": evaluation.get("component_coverage") if decision_safe else None,
        "action": action if decision_safe else None,
        "decision_digest": evaluation.get("decision_digest") if decision_safe else None,
    }

    trade_fields: dict[str, dict[str, Any]] = {}
    trade_state = _mapping(components.get("trade_plan")).get("state") or "INSUFFICIENT_INPUTS"
    trade_source = trade.get("source")
    trade_as_of = trade.get("as_of") or evaluation.get("evaluated_at")
    trade_ids = tuple(evaluation.get("evidence_ids") or ())
    for name in ("entry_low", "entry_high", "stop_loss", "trade_target_1", "trade_target_2", "risk_reward", "position_size"):
        trade_fields[name] = _field(
            name, trade.get(name), status=trade_state, source=trade_source,
            evidence_ids=trade_ids, as_of=trade_as_of, basis="CANONICAL_TRADE_PLAN",
            unit="PER_SHARE" if name not in {"risk_reward", "position_size"} else None,
            snapshot_id=snapshot_id,
        )

    method_fields = []
    for index, model in enumerate(professional.get("models") or ()):
        if not isinstance(model, Mapping):
            continue
        method_status = valuation_state if model.get("status") == "PUBLISHED" else str(model.get("status") or "INSUFFICIENT_INPUTS")
        method_fields.append({
            "name": model.get("name"),
            "value": _field(
                f"valuation_method_{index}_value", model.get("value"), status=method_status,
                source=valuation.get("version") or professional.get("version"), evidence_ids=valuation_ids,
                as_of=valuation_as_of, period=model.get("fiscal_period"),
                basis=model.get("valuation_basis") or model.get("name"), currency="USD",
                unit="PER_SHARE", snapshot_id=snapshot_id,
            ),
            "weight": _field(
                f"valuation_method_{index}_weight", model.get("weight"), status=method_status,
                source=valuation.get("version") or professional.get("version"), evidence_ids=valuation_ids,
                as_of=valuation_as_of, basis="CANONICAL_MODEL_WEIGHT", unit="DECIMAL",
                snapshot_id=snapshot_id,
            ),
        })

    wall_street = _mapping(row.get("wall_street_analysis"))
    street_consensus = _mapping(wall_street.get("consensus"))
    distribution = _mapping(wall_street.get("rating_distribution"))
    low, mean, median, high = (_num(street_consensus.get(key)) for key in
                               ("target_low", "target_mean", "target_median", "target_high"))
    target_order_valid = all(value is None for value in (low, mean, median, high)) or (
        low is not None and high is not None
        and (mean is None or low <= mean <= high)
        and (median is None or low <= median <= high)
    )
    distribution_total = sum(int(_num(distribution.get(key)) or 0) for key in
                             ("strong_buy", "buy", "hold", "sell", "strong_sell"))
    analyst_count = int(_num(street_consensus.get("analyst_count")) or 0)
    actions_valid = all(
        action.get("date") and action.get("firm")
        and (_mapping(action.get("original_fields")).get("evidence_id"))
        for action in (wall_street.get("recent_actions") or ()) if isinstance(action, Mapping)
    )
    street_safe = (
        wall_street.get("provider") == "TWELVE_DATA"
        and bool(wall_street.get("evidence_ids")) and bool(wall_street.get("as_of"))
        and str(wall_street.get("commercial_display_status") or "").startswith("DISPLAY_ALLOWED")
        and target_order_valid and actions_valid
        and (not distribution_total or not analyst_count or distribution_total == analyst_count)
        and wall_street.get("stale") is not True
        and str(wall_street.get("freshness_status") or "").upper() != "STALE"
    )
    certified_street = wall_street if street_safe else {}

    domains = {
        "identity_certification": _mapping(components.get("identity")).get("state"),
        "market_certification": market_state,
        "fundamentals_certification": fundamentals_state,
        "forward_estimates_certification": CERTIFIED if all(item["value"] is not None for item in estimate_fields.values()) else "INSUFFICIENT_INPUTS",
        "technical_certification": _mapping(components.get("technical")).get("state"),
        "risk_certification": _mapping(components.get("risk")).get("state"),
        "trade_plan_certification": _mapping(components.get("trade_plan")).get("state"),
        "volume_certification": _mapping(components.get("volume")).get("state"),
        "valuation_methods_certification": valuation_state,
        "valuation_package_certification": valuation_state,
        "wall_street_certification": CERTIFIED if street_safe else ("NOT_APPLICABLE" if not wall_street else "REVIEW_REQUIRED"),
        "snapshot_certification": CERTIFIED if evaluation.get("decision_digest") and market.get("evidence_id") else "REVIEW_REQUIRED",
        "decision_certification": decision_state,
        "publication_certification": publication.get("certification_state"),
    }
    digests = {
        "evaluation_snapshot_id": snapshot_id,
        "market_digest": _digest(market), "fundamentals_digest": _digest(fundamentals),
        "valuation_digest": _digest({"valuation": valuation, "atlas": atlas_valuation}),
        "decision_digest": evaluation.get("decision_digest"),
    }
    digests["certification_digest"] = _digest({"domains": domains, "fields": fields, **digests})
    return {
        "version": VERSION, "ticker": ticker, "generated_at": (now or datetime.now(timezone.utc)).isoformat(),
        "domains": domains, "fields": fields, "decision": decision,
        "trade_plan": {key: item["value"] for key, item in trade_fields.items() if item["value"] is not None},
        "trade_plan_fields": trade_fields,
        "valuation_methods": tuple(method_fields),
        "technical": technical if _mapping(components.get("technical")).get("state") in PUBLISHABLE else {},
        "risk": risk if _mapping(components.get("risk")).get("state") in PUBLISHABLE else {},
        "volume": volume if _mapping(components.get("volume")).get("state") in PUBLISHABLE else {},
        "wall_street_analysis": certified_street, "digests": digests,
        "accounting_reconstruction": recon, "accounting_mismatches": tuple(accounting_mismatches),
        "customer_publication_allowed": bool(decision_safe),
        "customer_message": None if decision_safe else "ATLAS cannot certify a complete investment rating for this ticker right now because some required financial evidence could not be reconciled.",
    }


__all__ = ["VERSION", "build_certified_customer_evaluation", "certified_projection_matches"]
