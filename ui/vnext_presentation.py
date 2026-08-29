"""Pure UX-1 presentation primitives for ATLAS VNext.

These helpers build immutable display models only.  They never derive a
recommendation, score, technical state, fair value, or trade level, and they do
not mutate the caller's canonical evidence.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Mapping, Sequence


EM_DASH = "—"
UNICODE_MINUS = "−"


class AvailabilityState(str, Enum):
    AVAILABLE = "AVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNAVAILABLE = "DATA_UNAVAILABLE"
    TEMPORARILY_UNAVAILABLE = "TEMPORARILY_UNAVAILABLE"
    STALE_FALLBACK = "STALE_FALLBACK"
    INCOMPLETE_EVIDENCE = "INCOMPLETE_EVIDENCE"


_AVAILABILITY_LABELS = {
    AvailabilityState.AVAILABLE: "Available",
    AvailabilityState.NOT_APPLICABLE: "Not applicable",
    AvailabilityState.UNAVAILABLE: "Unavailable",
    AvailabilityState.TEMPORARILY_UNAVAILABLE: "Temporarily unavailable",
    AvailabilityState.STALE_FALLBACK: "Stale fallback",
    AvailabilityState.INCOMPLETE_EVIDENCE: "Incomplete evidence",
}


@dataclass(frozen=True)
class DisplayValue:
    display: str
    exact_value: Any
    semantic_type: str
    availability: AvailabilityState = AvailabilityState.AVAILABLE
    exact_display: str | None = None


@dataclass(frozen=True)
class Badge:
    label: str
    canonical_value: str | None
    tone: str


@dataclass(frozen=True)
class DecisionHeader:
    recommendation: Any
    opportunity: Any
    confidence: Any
    research_completeness: Any
    actionability_label: str | None = None


@dataclass(frozen=True)
class PriceActionStrip:
    current_price: DisplayValue
    entry_low: DisplayValue
    entry_high: DisplayValue
    invalidation: DisplayValue


@dataclass(frozen=True)
class UpsideRiskPair:
    upside: DisplayValue
    downside_or_invalidation: DisplayValue


@dataclass(frozen=True)
class PrimaryEvidencePair:
    support: str
    contradiction_or_risk: str


@dataclass(frozen=True)
class EvidenceHealth:
    availability: AvailabilityState
    label: str
    freshness: str | None
    completeness: DisplayValue
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class ChangeSinceLastScan:
    field: str
    previous: Any
    current: Any
    changed: bool


@dataclass(frozen=True)
class CrossSignalAlignment:
    political_context: str | None
    atlas_context: str | None
    relationship: str
    disclaimer: str = "Contextual evidence only; this does not change ATLAS scoring or conviction."


@dataclass(frozen=True)
class EvidenceDrawer:
    title: str
    evidence_ids: tuple[str, ...]
    provenance: tuple[str, ...]
    limitations: tuple[str, ...]
    collapsed_by_default: bool = True


@dataclass(frozen=True)
class TickerOpportunityCard:
    ticker: str
    company: str | None
    action_state: Any
    technical_state: Badge
    price_action: PriceActionStrip
    upside_risk: UpsideRiskPair
    evidence: PrimaryEvidencePair
    health: EvidenceHealth
    research_cta: str = "Open Research"


@dataclass(frozen=True)
class TechnicalScenario:
    label: str
    levels: PriceActionStrip
    explanation: str
    collapsed_by_default: bool = True


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, (bool, Mapping, list, tuple, set, frozenset)):
        return None
    try:
        text = str(value).strip().replace(",", "").replace("$", "").replace("%", "")
        if not text or text.lower() in {"nan", "none", "null", "n/a", "unavailable"}:
            return None
        result = Decimal(text)
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def availability_label(state: AvailabilityState | str) -> str:
    try:
        canonical = state if isinstance(state, AvailabilityState) else AvailabilityState(str(state))
    except ValueError:
        canonical = AvailabilityState.UNAVAILABLE
    return _AVAILABILITY_LABELS[canonical]


class CanonicalNumberFormatter:
    """Explicit semantic formatters; percent and ratio inputs never cross-convert."""

    @staticmethod
    def unavailable(semantic_type: str, state: AvailabilityState = AvailabilityState.UNAVAILABLE) -> DisplayValue:
        return DisplayValue(availability_label(state), None, semantic_type, state)

    @staticmethod
    def currency(value: Any, *, exact: bool = False, decimals: int = 2) -> DisplayValue:
        number = _decimal(value)
        if number is None:
            return CanonicalNumberFormatter.unavailable("currency")
        exact_display = f"${number:,.{decimals}f}"
        absolute = abs(number)
        suffix, divisor = "", Decimal(1)
        for threshold, candidate_suffix in (
            (Decimal("1000000000000"), "T"), (Decimal("1000000000"), "B"),
            (Decimal("1000000"), "M"), (Decimal("1000"), "K"),
        ):
            if absolute >= threshold:
                suffix, divisor = candidate_suffix, threshold
                break
        display = exact_display if exact or not suffix else f"${number / divisor:,.1f}{suffix}"
        return DisplayValue(display, value, "currency", exact_display=exact_display)

    @staticmethod
    def price(value: Any, *, decimals: int = 2) -> DisplayValue:
        number = _decimal(value)
        if number is None:
            return CanonicalNumberFormatter.unavailable("price")
        display = f"${number:,.{decimals}f}"
        return DisplayValue(display, value, "price", exact_display=display)

    @staticmethod
    def percent(value: Any, *, decimals: int = 1, signed: bool = False) -> DisplayValue:
        """Format an already-percent value; 0.12 displays as 0.1%, not 12%."""
        number = _decimal(value)
        if number is None:
            return CanonicalNumberFormatter.unavailable("percent")
        sign = "+" if signed and number > 0 else UNICODE_MINUS if number < 0 else ""
        display = f"{sign}{abs(number):.{decimals}f}%"
        return DisplayValue(display, value, "percent", exact_display=f"{number}%")

    @staticmethod
    def ratio(value: Any, *, decimals: int = 2) -> DisplayValue:
        """Format a provider-native decimal ratio without percentage conversion."""
        number = _decimal(value)
        if number is None:
            return CanonicalNumberFormatter.unavailable("ratio")
        display = f"{number:.{decimals}f}×"
        return DisplayValue(display, value, "ratio", exact_display=str(number))

    @staticmethod
    def count(value: Any) -> DisplayValue:
        number = _decimal(value)
        if number is None:
            return CanonicalNumberFormatter.unavailable("count")
        return DisplayValue(f"{number:,.0f}", value, "count", exact_display=str(number))

    @staticmethod
    def currency_range(low: Any, high: Any) -> DisplayValue:
        low_value, high_value = _decimal(low), _decimal(high)
        if low_value is None or high_value is None:
            return CanonicalNumberFormatter.unavailable("currency_range")
        left = CanonicalNumberFormatter.currency(low).display
        right = CanonicalNumberFormatter.currency(high).display
        return DisplayValue(f"{left}–{right}", (low, high), "currency_range", exact_display=f"${low_value:,.2f}–${high_value:,.2f}")

    @staticmethod
    def customer_date(value: Any) -> DisplayValue:
        parsed: date | datetime | None = None
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, date):
            parsed = value
        elif isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                try:
                    parsed = date.fromisoformat(value[:10])
                except ValueError:
                    parsed = None
        if parsed is None:
            return CanonicalNumberFormatter.unavailable("date")
        return DisplayValue(parsed.strftime("%b %d, %Y").replace(" 0", " "), value, "date", exact_display=parsed.isoformat())

    @staticmethod
    def timestamp(value: Any) -> DisplayValue:
        parsed: datetime | None = value if isinstance(value, datetime) else None
        if parsed is None and isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                pass
        if parsed is None:
            return CanonicalNumberFormatter.unavailable("timestamp")
        if parsed.tzinfo is None:
            return CanonicalNumberFormatter.unavailable("timestamp")
        display = parsed.astimezone(timezone.utc).strftime("%b %d, %Y · %H:%M UTC").replace(" 0", " ")
        return DisplayValue(display, value, "timestamp", exact_display=parsed.isoformat())


_TECHNICAL_LABELS = {
    "NO_SETUP": "No Setup", "SETUP_FORMING": "Setup Forming",
    "NEAR_BREAKOUT": "Near Breakout", "BREAKOUT_CONFIRMED": "Breakout Confirmed",
    "EXTENDED": "Extended", "FAILED_BREAKOUT": "Failed Breakout",
}


def technical_state_badge(canonical_state: Any) -> Badge:
    """Render only an existing deterministic state; never infer one."""
    value = getattr(canonical_state, "value", canonical_state)
    key = str(value or "").strip().upper().replace(" ", "_")
    if key not in _TECHNICAL_LABELS:
        return Badge("Unavailable", None, "unavailable")
    tone = "positive" if key == "BREAKOUT_CONFIRMED" else "negative" if key == "FAILED_BREAKOUT" else "neutral"
    return Badge(_TECHNICAL_LABELS[key], key, tone)


def decision_header(*, recommendation: Any, opportunity: Any, confidence: Any, research_completeness: Any, actionability_label: str | None = None) -> DecisionHeader:
    return DecisionHeader(recommendation, opportunity, confidence, research_completeness, actionability_label)


def price_action_strip(*, current_price: Any, entry_low: Any, entry_high: Any, invalidation: Any) -> PriceActionStrip:
    return PriceActionStrip(*(CanonicalNumberFormatter.price(value) for value in (current_price, entry_low, entry_high, invalidation)))


def upside_risk_pair(*, upside_pct: Any, downside_or_invalidation_pct: Any) -> UpsideRiskPair:
    return UpsideRiskPair(CanonicalNumberFormatter.percent(upside_pct, signed=True), CanonicalNumberFormatter.percent(downside_or_invalidation_pct, signed=True))


def primary_evidence_pair(*, support: Any, contradiction_or_risk: Any) -> PrimaryEvidencePair:
    def text(value: Any) -> str:
        return str(value).strip() if isinstance(value, (str, int, float)) and str(value).strip() else "Unavailable"
    return PrimaryEvidencePair(text(support), text(contradiction_or_risk))


def evidence_health(*, semantic_status: str, cache_status: str | None, completeness_pct: Any, limitations: Sequence[str] = ()) -> EvidenceHealth:
    status = str(semantic_status or "DATA_UNAVAILABLE").upper()
    if status == "NOT_APPLICABLE":
        state = AvailabilityState.NOT_APPLICABLE
    elif str(cache_status or "").upper() == "STALE_FALLBACK":
        state = AvailabilityState.STALE_FALLBACK
    elif status == "TEMPORARILY_UNAVAILABLE":
        state = AvailabilityState.TEMPORARILY_UNAVAILABLE
    elif status == "AVAILABLE" and _decimal(completeness_pct) is not None and _decimal(completeness_pct) < 100:
        state = AvailabilityState.INCOMPLETE_EVIDENCE
    elif status == "AVAILABLE":
        state = AvailabilityState.AVAILABLE
    else:
        state = AvailabilityState.UNAVAILABLE
    freshness = "Stale fallback" if state == AvailabilityState.STALE_FALLBACK else str(cache_status) if cache_status else None
    return EvidenceHealth(state, availability_label(state), freshness, CanonicalNumberFormatter.percent(completeness_pct), tuple(str(item) for item in limitations))


def change_since_last_scan(field: str, previous: Any, current: Any) -> ChangeSinceLastScan:
    return ChangeSinceLastScan(str(field), previous, current, previous != current)


def cross_signal_alignment(*, political_context: str | None, atlas_context: str | None) -> CrossSignalAlignment:
    if not political_context or not atlas_context:
        relationship = "Unavailable"
    elif political_context.strip().lower() == atlas_context.strip().lower():
        relationship = "Aligned"
    else:
        relationship = "Conflicting context"
    return CrossSignalAlignment(political_context, atlas_context, relationship)


def evidence_drawer(*, title: str, evidence_ids: Sequence[str] = (), provenance: Sequence[str] = (), limitations: Sequence[str] = ()) -> EvidenceDrawer:
    return EvidenceDrawer(str(title), tuple(map(str, evidence_ids)), tuple(map(str, provenance)), tuple(map(str, limitations)))


def ticker_opportunity_card(*, ticker: str, company: str | None, action_state: Any, canonical_technical_state: Any, current_price: Any, entry_low: Any, entry_high: Any, invalidation: Any, upside_pct: Any, downside_pct: Any, primary_support: Any, primary_risk: Any, health: EvidenceHealth) -> TickerOpportunityCard:
    return TickerOpportunityCard(
        str(ticker).strip().upper(), company, action_state,
        technical_state_badge(canonical_technical_state),
        price_action_strip(current_price=current_price, entry_low=entry_low, entry_high=entry_high, invalidation=invalidation),
        upside_risk_pair(upside_pct=upside_pct, downside_or_invalidation_pct=downside_pct),
        primary_evidence_pair(support=primary_support, contradiction_or_risk=primary_risk),
        health,
    )


def monitor_technical_scenario(*, current_price: Any, entry_low: Any, entry_high: Any, invalidation: Any) -> TechnicalScenario:
    """Prepare the approved low-evidence presentation without activating it."""
    return TechnicalScenario(
        "Technical Scenario",
        price_action_strip(current_price=current_price, entry_low=entry_low, entry_high=entry_high, invalidation=invalidation),
        "These levels describe a deterministic technical scenario and do not represent a high-confidence ATLAS recommendation.",
    )


__all__ = [
    "AvailabilityState", "Badge", "CanonicalNumberFormatter", "ChangeSinceLastScan",
    "CrossSignalAlignment", "DecisionHeader", "DisplayValue", "EvidenceDrawer", "EvidenceHealth",
    "PriceActionStrip", "PrimaryEvidencePair", "UpsideRiskPair", "availability_label",
    "change_since_last_scan", "cross_signal_alignment", "decision_header",
    "evidence_drawer", "evidence_health", "monitor_technical_scenario",
    "price_action_strip", "primary_evidence_pair", "technical_state_badge",
    "ticker_opportunity_card", "upside_risk_pair", "TechnicalScenario",
    "TickerOpportunityCard",
]
