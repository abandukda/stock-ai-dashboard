"""Versioned, bounded interaction contracts for Atlas product certification."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping


INTERACTION_REGISTRY_VERSION = "ATLAS_INTERACTION_REGISTRY_V1"
INTERACTION_TYPES = frozenset({
    "NAVIGATION", "DRILL_DOWN", "FILTER", "TAB", "EXPANDER", "SEARCH",
    "STATE_CHANGE", "EXTERNAL_LINK", "READ_ONLY_ACTION",
})
CORE_INTERACTION_PAGES = (
    "Home", "Today's Opportunities", "Research Any Ticker",
    "Earnings Intelligence", "ETFs", "Watchlist Intelligence",
    "Portfolio Intelligence", "Ask AI",
)


@dataclass(frozen=True)
class InteractionContract:
    stable_id: str
    source_page: str
    interaction_type: str
    visible_label: str
    expected_result: str
    expected_page: str = ""
    expected_ticker: str = ""
    required: bool = True
    sampling: str = "REPRESENTATIVE"
    failure_severity: str = "P2"

    def __post_init__(self) -> None:
        if self.interaction_type not in INTERACTION_TYPES:
            raise ValueError("unknown interaction type")
        if not self.stable_id or not self.source_page or not self.expected_result:
            raise ValueError("incomplete interaction contract")
        if self.failure_severity not in {"P0", "P1", "P2", "P3"}:
            raise ValueError("invalid interaction failure severity")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


STATIC_INTERACTIONS = (
    InteractionContract("home-report-card-dynamic", "Home", "DRILL_DOWN", "Open Full Research", "Research context loads for the card ticker", "Research Any Ticker", failure_severity="P1"),
    InteractionContract("home-more-decisions-tabs", "Home", "TAB", "More Decisions tabs", "Every Home tab selects and renders distinct content"),
    InteractionContract("opportunities-research-link", "Today's Opportunities", "DRILL_DOWN", "Ticker Research", "Correct ticker Research context loads", "Research Any Ticker"),
    InteractionContract("opportunities-filters", "Today's Opportunities", "FILTER", "Opportunity filters", "Filtered rows update without exception"),
    InteractionContract("research-submit", "Research Any Ticker", "SEARCH", "Research ticker", "Submitted ticker reaches canonical Research"),
    InteractionContract("research-all-tabs", "Research Any Ticker", "TAB", "Research tabs", "Every tab selects and retains ticker context"),
    InteractionContract("research-important-expanders", "Research Any Ticker", "EXPANDER", "Evidence and methodology details", "Each expander opens with content"),
    InteractionContract("research-ask-transition", "Research Any Ticker", "DRILL_DOWN", "Ask Atlas AI", "Ask uses the same ticker context", "Ask AI"),
    InteractionContract("earnings-research-link", "Earnings Intelligence", "DRILL_DOWN", "Ticker Research", "Correct ticker and earnings period reach Research", "Research Any Ticker"),
    InteractionContract("earnings-tabs", "Earnings Intelligence", "TAB", "Earnings tabs", "Every earnings tab renders"),
    InteractionContract("etf-research-link", "ETFs", "DRILL_DOWN", "ETF Research", "ETF context loads without corporate semantics", "Research Any Ticker"),
    InteractionContract("etf-tabs", "ETFs", "TAB", "ETF holdings and allocation tabs", "Every ETF tab renders"),
    InteractionContract("watchlist-safe-controls", "Watchlist Intelligence", "READ_ONLY_ACTION", "Watchlist inspection controls", "No real customer state is mutated"),
    InteractionContract("portfolio-safe-controls", "Portfolio Intelligence", "READ_ONLY_ACTION", "Portfolio inspection controls", "No real customer state is mutated"),
    InteractionContract("ask-submit", "Ask AI", "SEARCH", "Ask Atlas", "Ticker-grounded answer renders"),
)


def interaction_registry(dynamic: Iterable[InteractionContract] = ()) -> dict[str, Any]:
    contracts = [*STATIC_INTERACTIONS, *dynamic]
    if len({item.stable_id for item in contracts}) != len(contracts):
        raise ValueError("duplicate interaction ID")
    return {
        "version": INTERACTION_REGISTRY_VERSION,
        "core_pages": list(CORE_INTERACTION_PAGES),
        "interactions": [item.to_dict() for item in contracts],
    }


def interaction_result(
    contract: Mapping[str, Any], *, click_accepted: bool, state_changed: bool,
    destination_settled: bool, ticker_matches: bool = True,
    rendered_exception: bool = False, before_screenshot: str = "",
    after_screenshot: str = "", detail: str = "",
) -> dict[str, Any]:
    passed = bool(click_accepted and state_changed and destination_settled and ticker_matches and not rendered_exception)
    dead = bool(click_accepted and not state_changed and not rendered_exception)
    return {
        "interaction_id": str(contract.get("stable_id") or ""),
        "source_page": str(contract.get("source_page") or ""),
        "interaction_type": str(contract.get("interaction_type") or ""),
        "required": bool(contract.get("required", True)),
        "status": "PASS" if passed else "FAIL",
        "classification": "PASS" if passed else "DEAD_INTERACTION" if dead else "PRODUCT_DEFECT" if rendered_exception else "QA_DEFECT",
        "severity": "" if passed else "P1" if dead else str(contract.get("failure_severity") or "P2"),
        "click_accepted": bool(click_accepted),
        "state_changed": bool(state_changed),
        "destination_settled": bool(destination_settled),
        "ticker_matches": bool(ticker_matches),
        "rendered_exception": bool(rendered_exception),
        "before_screenshot": before_screenshot,
        "after_screenshot": after_screenshot,
        "expected_state": str(contract.get("expected_result") or ""),
        "observed_state": detail,
        "detail": detail,
    }


def interaction_coverage(registry: Mapping[str, Any], results: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    contracts = list(registry.get("interactions") or [])
    result_by_id = {str(item.get("interaction_id") or ""): dict(item) for item in results}
    pages: dict[str, dict[str, int | float]] = {}
    totals = {"discovered": len(contracts), "required": 0, "attempted": 0, "passed": 0, "failed": 0, "skipped": 0}
    required_attempted = 0
    for contract in contracts:
        page = str(contract.get("source_page") or "Unknown")
        bucket = pages.setdefault(page, {"discovered": 0, "required": 0, "attempted": 0, "passed": 0, "failed": 0, "skipped": 0})
        bucket["discovered"] += 1
        required = bool(contract.get("required", True))
        if required:
            totals["required"] += 1
            bucket["required"] += 1
        result = result_by_id.get(str(contract.get("stable_id") or ""))
        if result is None:
            totals["skipped"] += 1
            bucket["skipped"] += 1
            continue
        totals["attempted"] += 1
        bucket["attempted"] += 1
        if required:
            required_attempted += 1
        outcome = "passed" if result.get("status") == "PASS" else "failed"
        totals[outcome] += 1
        bucket[outcome] += 1
    denominator = totals["required"] or 1
    totals["coverage_pct"] = round(required_attempted / denominator * 100, 1)
    required_ids = {str(c.get("stable_id")) for c in contracts if c.get("required", True)}
    passed_ids = {key for key, value in result_by_id.items() if value.get("status") == "PASS"}
    totals["full_certification_allowed"] = required_ids.issubset(passed_ids)
    for page, bucket in pages.items():
        denominator = int(bucket["required"]) or 1
        required_ids_for_page = {
            str(c.get("stable_id")) for c in contracts
            if c.get("required", True) and str(c.get("source_page") or "Unknown") == page
        }
        attempted_required = len(required_ids_for_page.intersection(result_by_id))
        bucket["coverage_pct"] = round(attempted_required / denominator * 100, 1)
    return {**totals, "by_page": pages}


__all__ = [
    "CORE_INTERACTION_PAGES", "INTERACTION_REGISTRY_VERSION", "INTERACTION_TYPES",
    "InteractionContract", "interaction_coverage", "interaction_registry", "interaction_result",
]
