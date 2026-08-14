"""Canonical, provider-agnostic Atlas Fair Value calculation.

This module owns valuation arithmetic and semantic diagnostics only.  It does
not score, rank, recommend, size positions, or calculate trade levels.  Analyst
targets are accepted solely for a post-calculation discrepancy diagnostic and
never participate in Atlas Fair Value.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from typing import Any, Mapping


PUBLISHED = "PUBLISHED"
REJECTED_EXTREME_UPSIDE = "REJECTED_EXTREME_UPSIDE"
REJECTED_EXTREME_DOWNSIDE = "REJECTED_EXTREME_DOWNSIDE"
INSUFFICIENT_INPUTS = "INSUFFICIENT_INPUTS"
FORMULA_NOT_APPLICABLE = "FORMULA_NOT_APPLICABLE"
MODEL_UNDER_REVIEW = "MODEL_UNDER_REVIEW"

PROVIDER_DIRECT = "PROVIDER_DIRECT"
DERIVED_FROM_PRICE_AND_FORWARD_PE = "DERIVED_FROM_PRICE_AND_FORWARD_PE"
UNAVAILABLE = "UNAVAILABLE"
PROVIDER_VALUE = "PROVIDER_VALUE"
FALLBACK_ASSUMPTION = "FALLBACK_ASSUMPTION"


def number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(str(value).replace("$", "").replace(",", "").replace("%", "").strip())
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def percent(value: Any) -> float | None:
    """Normalize provider decimal ratios without double scaling percentages."""
    result = number(value)
    if result is not None and abs(result) <= 2:
        result *= 100.0
    return result


def first_value(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row.get(key) not in (None, "", "Unknown", "Unavailable"):
            return row.get(key)
    return None


def canonical_operating_margin(row: Mapping[str, Any]) -> float | None:
    return percent(first_value(row, "operating_profit_margin", "operating_margin", "Operating Margin"))


@dataclass(frozen=True)
class AtlasValuationInputs:
    price: float | None
    forward_pe: float | None = None
    forward_eps: float | None = None
    forward_eps_source: str | None = None
    revenue_growth: float | None = None
    revenue_growth_source: str | None = None
    revenue_growth_horizon: str | None = None
    operating_margin: float | None = None
    analyst_target_mean: float | None = None
    analyst_target_low: float | None = None
    analyst_target_high: float | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "AtlasValuationInputs":
        return cls(
            price=number(first_value(row, "price", "current_price", "Price")),
            forward_pe=number(first_value(row, "forward_pe", "Forward PE", "Forward P/E")),
            forward_eps=number(first_value(row, "forward_eps", "Forward EPS")),
            forward_eps_source=str(first_value(row, "forward_eps_source") or "") or None,
            # Preserve raw provider units here; calculate_atlas_fair_value owns
            # the single normalization boundary.
            revenue_growth=number(first_value(row, "revenue_growth", "Revenue Growth")),
            revenue_growth_source=str(first_value(row, "revenue_growth_source") or "") or None,
            revenue_growth_horizon=str(first_value(row, "revenue_growth_horizon") or "") or None,
            operating_margin=number(first_value(row, "operating_profit_margin", "operating_margin", "Operating Margin")),
            analyst_target_mean=number(first_value(row, "analyst_target_mean", "Analyst Target")),
            analyst_target_low=number(first_value(row, "analyst_target_low", "Analyst Target Low")),
            analyst_target_high=number(first_value(row, "analyst_target_high", "Analyst Target High")),
        )


@dataclass(frozen=True)
class AtlasValuationResult:
    fair_value: float | None
    upside_pct: float | None
    status: str
    forward_eps: float | None
    forward_eps_method: str
    forward_eps_source: str | None
    growth_value: float | None
    growth_method: str
    growth_source: str
    growth_horizon: str
    operating_margin: float | None
    justified_pe: float | None
    multiple_expansion_ratio: float | None
    multiple_expansion_band: str
    analyst_discrepancy: str
    assumption_flags: tuple[str, ...] = field(default_factory=tuple)
    validation_flags: tuple[str, ...] = field(default_factory=tuple)
    raw_fair_value: float | None = None
    raw_upside_pct: float | None = None

    def public_fields(self) -> dict[str, Any]:
        """Serialize safe persisted diagnostics, excluding rejected raw values."""
        data = asdict(self)
        data.pop("raw_fair_value", None)
        data.pop("raw_upside_pct", None)
        # Guard thresholds and rejection explanations remain internal QA data.
        # Client/persisted payloads receive only the safe semantic status.
        data.pop("validation_flags", None)
        data["atlas_fair_value"] = data.pop("fair_value")
        data["atlas_fv_upside_pct"] = data.pop("upside_pct")
        data["atlas_valuation_status"] = data.pop("status")
        # Namespace valuation diagnostics so reporting metadata cannot be
        # mistaken for primary scoring evidence by legacy component adapters.
        for key in (
            "growth_value", "growth_method", "growth_source", "growth_horizon",
            "operating_margin", "justified_pe", "multiple_expansion_ratio",
            "multiple_expansion_band", "analyst_discrepancy", "assumption_flags",
        ):
            data[f"atlas_valuation_{key}"] = data.pop(key)
        return data


def _multiple_band(ratio: float | None) -> str:
    if ratio is None:
        return "UNAVAILABLE"
    if ratio > 3.0:
        return "ABOVE_3_0X"
    if ratio > 2.0:
        return "ABOVE_2_0X"
    if ratio > 1.5:
        return "ABOVE_1_5X"
    return "AT_OR_BELOW_1_5X"


def _analyst_discrepancy(value: float | None, inputs: AtlasValuationInputs) -> str:
    low, high = number(inputs.analyst_target_low), number(inputs.analyst_target_high)
    if value is None or low is None or high is None:
        return "ANALYST_DATA_UNAVAILABLE"
    if value > high:
        return "ATLAS_ABOVE_ANALYST_HIGH"
    if value < low:
        return "ATLAS_BELOW_ANALYST_LOW"
    return "ATLAS_WITHIN_ANALYST_RANGE"


def calculate_atlas_fair_value(inputs: AtlasValuationInputs) -> AtlasValuationResult:
    """Apply the unchanged scheduled-production Atlas valuation methodology."""
    price = number(inputs.price)
    forward_pe = number(inputs.forward_pe)
    direct_eps = number(inputs.forward_eps)
    assumptions: list[str] = []
    validation: list[str] = []

    if price is None or price <= 0:
        return AtlasValuationResult(
            None, None, INSUFFICIENT_INPUTS, None, UNAVAILABLE, None, None, UNAVAILABLE,
            str(inputs.revenue_growth_source or "UNAVAILABLE"),
            str(inputs.revenue_growth_horizon or "UNKNOWN"), percent(inputs.operating_margin),
            None, None, "UNAVAILABLE", "ANALYST_DATA_UNAVAILABLE",
            validation_flags=("PRICE_UNAVAILABLE",),
        )

    if direct_eps is not None and direct_eps > 0:
        forward_eps = direct_eps
        eps_method = PROVIDER_DIRECT
        eps_source = inputs.forward_eps_source or "PROVIDER_DIRECT"
    elif forward_pe is not None and forward_pe > 0:
        forward_eps = price / forward_pe
        eps_method = DERIVED_FROM_PRICE_AND_FORWARD_PE
        eps_source = "DERIVED"
        assumptions.append("FORWARD_EPS_DERIVED")
    elif forward_pe is not None and forward_pe <= 0:
        return AtlasValuationResult(
            None, None, FORMULA_NOT_APPLICABLE, None, UNAVAILABLE, None, None, UNAVAILABLE,
            str(inputs.revenue_growth_source or "UNAVAILABLE"),
            str(inputs.revenue_growth_horizon or "UNKNOWN"), percent(inputs.operating_margin),
            None, None, "UNAVAILABLE", "ANALYST_DATA_UNAVAILABLE",
            validation_flags=("NONPOSITIVE_FORWARD_PE",),
        )
    else:
        return AtlasValuationResult(
            None, None, INSUFFICIENT_INPUTS, None, UNAVAILABLE, None, None, UNAVAILABLE,
            str(inputs.revenue_growth_source or "UNAVAILABLE"),
            str(inputs.revenue_growth_horizon or "UNKNOWN"), percent(inputs.operating_margin),
            None, None, "UNAVAILABLE", "ANALYST_DATA_UNAVAILABLE",
            validation_flags=("FORWARD_EPS_AND_FORWARD_PE_UNAVAILABLE",),
        )

    supplied_growth = percent(inputs.revenue_growth)
    if supplied_growth is None:
        growth = 8.0
        growth_method = FALLBACK_ASSUMPTION
        growth_source = "ATLAS_ASSUMPTION"
        growth_horizon = "NOT_APPLICABLE"
        assumptions.append("REVENUE_GROWTH_FALLBACK_8_PERCENT")
    else:
        growth = supplied_growth
        growth_method = PROVIDER_VALUE
        growth_source = str(inputs.revenue_growth_source or "UNKNOWN")
        growth_horizon = str(inputs.revenue_growth_horizon or "UNKNOWN")
        if growth_source == "UNKNOWN" or growth_horizon == "UNKNOWN":
            assumptions.append("GROWTH_PROVENANCE_INCOMPLETE")
    growth = max(-10.0, min(40.0, growth))

    margin = percent(inputs.operating_margin)
    margin_bonus = 2.0 if margin is not None and margin >= 25.0 else 0.0
    justified_pe = max(12.0, min(38.0, 16.0 + 0.45 * growth + margin_bonus))
    raw_fair_value = round(forward_eps * justified_pe, 2)
    raw_upside = ((raw_fair_value / price) - 1.0) * 100.0
    ratio = justified_pe / forward_pe if forward_pe is not None and forward_pe > 0 else None

    status = PUBLISHED
    fair_value: float | None = raw_fair_value
    upside: float | None = raw_upside
    if raw_fair_value <= 0:
        status = FORMULA_NOT_APPLICABLE
        validation.append("NONPOSITIVE_MODEL_VALUE")
    elif raw_upside < -60.0:
        status = REJECTED_EXTREME_DOWNSIDE
        validation.append("BELOW_MINUS_60_PERCENT_GUARD")
    elif raw_upside > 80.0:
        status = REJECTED_EXTREME_UPSIDE
        validation.append("ABOVE_80_PERCENT_GUARD")
    elif 29.65 <= raw_upside <= 30.35:
        status = MODEL_UNDER_REVIEW
        validation.append("LEGACY_30_PERCENT_SENTINEL")
    if status != PUBLISHED:
        fair_value = None
        upside = None

    return AtlasValuationResult(
        fair_value=fair_value,
        upside_pct=round(upside, 1) if upside is not None else None,
        status=status,
        forward_eps=forward_eps,
        forward_eps_method=eps_method,
        forward_eps_source=eps_source,
        growth_value=growth,
        growth_method=growth_method,
        growth_source=growth_source,
        growth_horizon=growth_horizon,
        operating_margin=margin,
        justified_pe=justified_pe,
        multiple_expansion_ratio=ratio,
        multiple_expansion_band=_multiple_band(ratio),
        analyst_discrepancy=_analyst_discrepancy(raw_fair_value, inputs),
        assumption_flags=tuple(assumptions),
        validation_flags=tuple(validation),
        raw_fair_value=raw_fair_value,
        raw_upside_pct=raw_upside,
    )


__all__ = [
    "AtlasValuationInputs", "AtlasValuationResult", "calculate_atlas_fair_value",
    "canonical_operating_margin", "percent", "PUBLISHED",
]
