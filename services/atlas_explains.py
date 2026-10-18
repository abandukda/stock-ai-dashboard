"""Grounded, provider-disabled page explanations for the customer product.

This module is presentation-only.  It never changes investment calculations,
certified decisions, publication state, or Report Card observations.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Final, Mapping


ATLAS_EXPLAINS_VERSION: Final = "ATLAS_EXPLAINS_V1"


@dataclass(frozen=True)
class ExplanationSection:
    label: str
    text: str
    classification: str


@dataclass(frozen=True)
class PageExplanation:
    page: str
    title: str
    takeaway: str
    simple: tuple[ExplanationSection, ...]
    detailed: tuple[ExplanationSection, ...]
    source_date: str
    synthesis_mode: str = "DETERMINISTIC_GROUNDED_FALLBACK"
    external_model_active: bool = False
    non_scoring: bool = True

    def as_dict(self) -> dict:
        return asdict(self)


def _section(label: str, text: str, classification: str) -> ExplanationSection:
    if classification not in {"SOURCE_FACT", "CALCULATION", "INTERPRETATION", "SCENARIO", "LIMITATION"}:
        raise ValueError("ATLAS_EXPLAINS_CLASSIFICATION_INVALID")
    if not str(text).strip():
        raise ValueError("ATLAS_EXPLAINS_EMPTY_TEXT")
    return ExplanationSection(label=label, text=str(text).strip(), classification=classification)


_PAGE_COPY: Final[Mapping[str, Mapping[str, str]]] = {
    "Home": {
        "title": "Your ATLAS starting point",
        "takeaway": "Start here for the latest certified opportunity list, market context, and the evidence date behind what you see.",
        "meaning": "The page separates certified investment decisions from educational market context so you can see what is actionable and what is simply useful background.",
        "care": "A strong-looking idea is only useful when its evidence is complete, dated, and still inside the published decision rules.",
        "encouraging": "Certified opportunities and clear evidence links make the strongest current cases easy to find.",
        "risks": "A retained snapshot can become stale. Always check the market-session and publication dates before relying on it.",
        "next": "Monitor the next completed market session, material company changes, and whether the certified action changes.",
    },
    "BUY NOW": {
        "title": "Understanding BUY NOW",
        "takeaway": "These are the strongest currently certified setups—not promises that a stock will rise.",
        "meaning": "A BUY NOW label means the existing six-pillar method cleared its evidence, quality, valuation, and timing gates for the published snapshot.",
        "care": "It helps you focus research on ideas that met every required gate instead of chasing the loudest market story.",
        "encouraging": "The setup has broad support across the unchanged ATLAS method and a defined evidence trail.",
        "risks": "Prices and company facts can change after publication; certification does not remove investment risk.",
        "next": "Watch the evidence date, entry conditions, company catalysts, and any new withholding or risk flag.",
    },
    "Research": {
        "title": "How to read company Research",
        "takeaway": "Use Simple View for the investment story, then open Detailed View to inspect the evidence and assumptions.",
        "meaning": "Research brings the certified decision, financial evidence, valuation, risks, catalysts, and market history into one company-specific view.",
        "care": "The detail shows whether a conclusion is supported by company facts or limited by missing or stale evidence.",
        "encouraging": "Facts, calculations, interpretation, and unavailable fields are kept visibly separate.",
        "risks": "Missing histories or stale context stay unavailable; ATLAS does not fill gaps with invented facts.",
        "next": "Watch the next earnings event, financial trend, valuation gap, and the conditions that would change the assessment.",
    },
    "Charts": {
        "title": "What the chart can—and cannot—tell you",
        "takeaway": "Charts describe verified price history and levels; they do not predict the next move or alter an ATLAS score.",
        "meaning": "Support, resistance, trend, signal markers, and SPY comparisons are deterministic descriptions of retained completed-session data.",
        "care": "They help you see timing and context without mistaking a visual pattern for proof of future performance.",
        "encouraging": "Every annotation comes from validated dated history and has an accessible table fallback.",
        "risks": "Short or incomplete history can make a timeframe or annotation unavailable.",
        "next": "Monitor the latest verified close, whether a level still holds, and the next completed-session update.",
    },
    "Report Card": {
        "title": "How ATLAS measures itself",
        "takeaway": "The Report Card records what happened after an original signal and compares it with SPY—only after observations are verified.",
        "meaning": "Original recommendations are immutable. Later prices are appended as source-bound observations at registered trading-session horizons.",
        "care": "This prevents hindsight edits and makes measured outcomes easier to evaluate honestly.",
        "encouraging": "Pending, measured, withheld, and unavailable states remain distinct, with provenance and backup controls.",
        "risks": "An unmeasured signal is not a win or loss, and a short history is not proof of long-term skill.",
        "next": "Watch for the next eligible observation horizon, backup verification, and the separate public activation gate.",
    },
    "Recovery Radar": {
        "title": "Understanding Recovery Radar",
        "takeaway": "Recovery Radar looks for evidence that a fallen stock may be stabilizing; it is not an automatic buy list.",
        "meaning": "It separates why the price weakened, what recovery evidence is confirmed, and what still needs proof.",
        "care": "A low price can reflect a real business problem, so recovery evidence matters more than the size of the decline.",
        "encouraging": "Confirmed improvement, valuation support, and technical stabilization can strengthen a recovery case.",
        "risks": "Early signals can fail, and missing financial or catalyst evidence can keep a candidate unconfirmed.",
        "next": "Monitor the stated confirmation, invalidation, earnings, and risk conditions for the selected company.",
    },
    "ETF Analysis": {
        "title": "How to read ETF Analysis",
        "takeaway": "ETF Analysis compares saved fund evidence; it does not assume every fund fits every investor.",
        "meaning": "The screen organizes persisted ETF candidates and their available metrics without turning them into certified stock recommendations.",
        "care": "Funds can differ in holdings, concentration, cost, liquidity, and market exposure even when their names sound similar.",
        "encouraging": "A consistent table makes comparable verified fields easier to review.",
        "risks": "Missing holdings or fee evidence limits the comparison, and market exposure can still lose value.",
        "next": "Monitor source dates, composition, concentration, liquidity, fees, and the fund objective.",
    },
    "Watchlist": {
        "title": "Using your Watchlist",
        "takeaway": "A watchlist is a monitoring tool: it helps you notice meaningful changes without creating a new recommendation.",
        "meaning": "Each card preserves the certified action and shows dated context such as price, valuation distance, and material changes.",
        "care": "You can follow a company without treating attention as a signal to buy it.",
        "encouraging": "The same certified evidence and narrative contract are reused across Watchlist and Research.",
        "risks": "Saved tickers can have unavailable research or stale context, which is disclosed rather than hidden.",
        "next": "Monitor earnings, material changes, evidence freshness, and whether the certified action changes.",
    },
}


_ALIASES: Final = {
    "Today's Opportunities": "BUY NOW", "Top AI Ideas": "BUY NOW",
    "Research Any Ticker": "Research", "Internal Report Card": "Report Card",
    "Recovery": "Recovery Radar", "ETFs": "ETF Analysis",
    "Watchlist Intelligence": "Watchlist",
}


def build_page_explanation(page: str, *, source_date: str | None = None) -> PageExplanation:
    canonical = _ALIASES.get(str(page), str(page))
    copy = _PAGE_COPY.get(canonical)
    if copy is None:
        raise KeyError(f"ATLAS_EXPLAINS_PAGE_UNSUPPORTED:{canonical}")
    date = str(source_date or "Source date unavailable")
    simple = (
        _section("What am I looking at?", f"This is the {copy['title']} view in ATLAS.", "SOURCE_FACT"),
        _section("What does it mean in simple language?", copy["meaning"], "INTERPRETATION"),
        _section("Why should an investor care?", copy["care"], "INTERPRETATION"),
        _section("What is encouraging?", copy["encouraging"], "INTERPRETATION"),
        _section("Important risks or limitations", copy["risks"], "LIMITATION"),
        _section("What should I monitor next?", copy["next"], "SCENARIO"),
    )
    detailed = (
        _section("Evidence boundary", f"Only evidence accepted by this page's existing governed contract is shown. Evidence date: {date}.", "SOURCE_FACT"),
        _section("Calculation boundary", "Displayed calculations remain the output of existing registered code; this explanation cannot change them.", "CALCULATION"),
        _section("Interpretation boundary", "Plain-English interpretation explains the displayed evidence and remains separate from certified recommendations.", "INTERPRETATION"),
        _section("Scenario boundary", "Things to monitor are scenarios, not forecasts or promises of future performance.", "SCENARIO"),
    )
    return PageExplanation(page=canonical, title=copy["title"], takeaway=copy["takeaway"], simple=simple, detailed=detailed, source_date=date)


def synthesize_page_explanation(page: str, *, source_date: str | None = None, external_model_enabled: bool = False) -> PageExplanation:
    """Structured synthesis interface; external execution is fail-closed."""
    if external_model_enabled:
        raise PermissionError("ATLAS_EXTERNAL_SYNTHESIS_NOT_AUTHORIZED")
    return build_page_explanation(page, source_date=source_date)


__all__ = ["ATLAS_EXPLAINS_VERSION", "PageExplanation", "build_page_explanation", "synthesize_page_explanation"]
