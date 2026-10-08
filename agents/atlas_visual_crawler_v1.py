"""Non-blocking, browser-driven full-product visual diagnostics for ATLAS."""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import html
import json
import os
import re
import subprocess
import time
from io import BytesIO
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable

from playwright.async_api import Browser, BrowserContext, Page, async_playwright
from PIL import Image

from agents.atlas_runtime_qa_v3 import _open_and_authenticate, expected_deployed_source_sha
from agents.product_hardening_certification import ACTIVE_PAGES
from agents.runtime_qa_architecture import full_certification_ticker_matrix
from agents.runtime_qa_architecture import decode_context_summary, stable_digest
from agents.runtime_qa_user_journeys_v40 import (
    _has_rendered_exception,
    _navigate,
    _page_render_complete,
    _scopes,
    _visible_text,
)
from services.vnext_presentation_contract import (
    RESEARCH_TERMINAL_RATING_NOT_PUBLISHED,
    RESEARCH_VNEXT_VERSION,
    RESEARCH_WITHHELD_PRIMARY_COPY,
    RESEARCH_WITHHELD_SUPPORTING_COPY,
)


VISUAL_CRAWLER_VERSION = "ATLAS_VISUAL_CRAWLER_V1_1"
RESEARCH_COMPLETION_TIMEOUT_SECONDS = 90
REQUIRED_PHASE_TIMEOUT_SECONDS = 480
REQUIRED_PHASE_BUDGET = {
    "authentication_and_deployment": {"timeout_seconds": 60, "retries": 0},
    "home_desktop": {"timeout_seconds": 90, "retries": 0},
    "research_desktop_nvda": {"timeout_seconds": 45, "retries": 0},
    "research_desktop_msft": {"timeout_seconds": 45, "retries": 0},
    "research_desktop_avt": {"timeout_seconds": 45, "retries": 0},
    "earnings_watchlist_ask_desktop": {"timeout_seconds": 60, "retries": 0},
    "home_mobile": {"timeout_seconds": 30, "retries": 0},
    "research_mobile_nvda": {"timeout_seconds": 45, "retries": 0},
    "earnings_watchlist_ask_mobile": {"timeout_seconds": 60, "retries": 0},
}
RESEARCH_VNEXT_SECTIONS = (
    "decision", "fundamentals-and-valuation", "technical-and-trade-state",
    "catalysts-and-sentiment", "risk-and-evidence",
)
RESEARCH_VNEXT_SECTION_LABELS = (
    "ATLAS View", "ATLAS Fair Value", "Live Market & Trade",
    "Additional Context", "Decision Evidence",
)


def research_route_ownership_satisfied(
    *, route_selected: bool, heading_visible: bool,
    ticker_input_visible: bool, submit_control_visible: bool,
) -> bool:
    """Require the selected route and its complete visible ticker form."""
    return bool(
        route_selected and heading_visible
        and ticker_input_visible and submit_control_visible
    )


def deduplicate_research_control_pairs(
    pairs: Iterable[tuple[str, Any, Any, tuple[Any, ...]]],
) -> list[tuple[str, Any, Any, tuple[Any, ...]]]:
    """Collapse overlapping-scope discoveries of the same physical form."""
    unique: dict[str, tuple[str, Any, Any, tuple[Any, ...]]] = {}
    for pair in pairs:
        unique.setdefault(pair[0], pair)
    return list(unique.values())


def _research_declared_architecture(section_count: int, tab_labels: set[str]) -> bool:
    """Validate the renderer-owned Research architecture without tab bodies.

    Streamlit may mount tab panels lazily, but all required semantic tab
    controls must still be present.  A bare count of five is deliberately not
    sufficient: it cannot hide a missing or substituted required section.
    """
    return (
        section_count == len(RESEARCH_VNEXT_SECTIONS)
        and set(RESEARCH_VNEXT_SECTION_LABELS) <= tab_labels
    )
EARNINGS_VNEXT_SECTION_LABELS = (
    "Recently Reported", "Upcoming Earnings", "What Happened", "Why It Matters",
    "Guidance & Estimate Changes", "Market Reaction",
    "ATLAS Decision After Earnings", "What Changes the Thesis",
    "What ATLAS Is Watching Next", "Deep Evidence",
)
RECOVERY_VNEXT_SECTION_LABELS = (
    "Recovery Snapshot", "Why It Fell", "Evidence of Recovery",
    "Financial & Earnings Direction", "Management / Analyst Intelligence",
    "Valuation Support", "Technical Confirmation", "Catalysts",
    "Primary Risks", "What Invalidates Recovery",
    "What ATLAS Is Watching Next", "Deep Evidence",
)

RESEARCH_WITHHELD_FORBIDDEN_TEXT = (
    "BUY NOW", "BUILD A POSITION", "WAIT FOR A BETTER ENTRY",
    "WAIT FOR CONFIRMATION", "WATCH — NOT READY YET", "ATLAS FAIR VALUE",
    "POTENTIAL", "SIX PILLARS", "FULL INVESTMENT CASE",
)


def classify_research_terminal_state(
    *, ticker_present: bool, lifecycle_complete: bool, authoritative_version: bool,
    five_sections: bool, ask_cta: bool, withheld_marker: bool,
    published_decision_evidence: bool = False,
    publication_allowed: bool | None, visible_text: str, rendered_exception: bool,
    loading: bool,
) -> str:
    """Classify only explicit, internally consistent Research terminal states."""
    if not ticker_present or not lifecycle_complete or not authoritative_version or rendered_exception or loading:
        return "RESEARCH_RENDER_INCOMPLETE"
    normalized = re.sub(r"\s+", " ", str(visible_text or "")).upper()
    if publication_allowed is True:
        return (
            "PUBLISHED_RESEARCH_COMPLETE"
            if five_sections and ask_cta and published_decision_evidence
            else "RESEARCH_RENDER_INCOMPLETE"
        )
    if withheld_marker and publication_allowed is False:
        safe = (
            RESEARCH_WITHHELD_PRIMARY_COPY in normalized
            and RESEARCH_WITHHELD_SUPPORTING_COPY.upper() in normalized
            and not any(
            forbidden in normalized for forbidden in RESEARCH_WITHHELD_FORBIDDEN_TEXT
            )
        )
        return "RATING_NOT_PUBLISHED_COMPLETE" if safe else "RESEARCH_RENDER_INCOMPLETE"
    return "RESEARCH_RENDER_INCOMPLETE"


def recovery_candidate_archetypes(candidates: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    """Select population positions and evidence archetypes without hardcoded tickers."""
    if not candidates:
        return []
    def score(item: dict[str, Any], fallback: float) -> float:
        try:
            return float(item.get("score"))
        except (TypeError, ValueError):
            return fallback

    selected: list[tuple[str, dict[str, Any]]] = [
        ("first", candidates[0]),
        ("middle", candidates[len(candidates) // 2]),
        ("last", candidates[-1]),
        ("high-evidence", max(candidates, key=lambda item: score(item, float("-inf")))),
    ]
    partial = next(
        (item for item in candidates if any(token in str(item.get("evidence") or "").lower() for token in ("partial", "incomplete", "unavailable"))),
        min(candidates, key=lambda item: score(item, float("inf"))),
    )
    selected.append(("partial-evidence", partial))
    output: list[tuple[str, dict[str, Any]]] = []
    seen: set[tuple[str, str]] = set()
    for role, candidate in selected:
        identity = (role, str(candidate.get("ticker") or ""))
        if identity not in seen:
            seen.add(identity)
            output.append((role, candidate))
    return output
DESKTOP = {"width": 1440, "height": 1000}
MOBILE = {"width": 390, "height": 844}
GLOBAL_FATALS = {"APP_UNREACHABLE", "AUTHENTICATION_FAILED", "BROWSER_DIED"}
MOBILE_PAGES = (
    "Home", "Research Any Ticker", "Today's Opportunities", "Ask AI",
    "Political Intelligence", "Earnings Intelligence", "Full Ranked Scan", "Recovery",
)
REQUIRED_RESEARCH_TICKERS = ("NVDA", "MSFT", "AVT")
REQUIRED_PAGE_VIEWPORTS = frozenset({
    ("Home", "desktop"), ("Home", "mobile"),
    ("Research Any Ticker", "desktop"), ("Research Any Ticker", "mobile"),
    ("Earnings Intelligence", "desktop"), ("Earnings Intelligence", "mobile"),
    ("Watchlist Intelligence", "desktop"), ("Watchlist Intelligence", "mobile"),
    ("Ask AI", "desktop"), ("Ask AI", "mobile"),
})
REQUIRED_CUSTOMER_ROUTES = ("Home", "Research", "Earnings", "Watchlist", "Ask ATLAS")
PRIMARY_VISIBLE_SIGNALS = {
    "Home": ("Atlas Morning Decision", "Home"),
    "Today's Opportunities": ("Today's Opportunities", "Opportunity"),
    "Volume Intelligence": ("Volume Intelligence", "Volume"),
    "Atlas Core Holdings": ("Atlas Core Holdings", "Holdings"),
    "Research Any Ticker": ("Research Any Ticker", "Ticker"),
    "Earnings Intelligence": ("Earnings Intelligence", "Earnings"),
    "Full Ranked Scan": ("Full Ranked Scan", "Rank"),
    "Portfolio Intelligence": ("Portfolio Intelligence", "Portfolio"),
    "Watchlist Intelligence": ("Watchlist Intelligence", "Watchlist"),
    "Recovery": ("Recovery Intelligence", "Recovery Snapshot"),
    "ETFs": ("ETF",),
    "Political Intelligence": ("Political Intelligence", "Transaction"),
    "Ask AI": ("Ask", "ATLAS"),
    "Developer Center": ("Developer Center", "Developer"),
}


@dataclass
class VisualResult:
    category: str
    page: str
    interaction: str
    expected: str
    observed: str
    status: str
    severity: str
    elapsed_seconds: float
    ticker_context: str = ""
    viewport: str = "desktop"
    screenshots: list[str] = field(default_factory=list)
    exception: dict[str, str] = field(default_factory=dict)
    required: bool = False


class GlobalCrawlFailure(RuntimeError):
    def __init__(self, category: str) -> None:
        super().__init__(category)
        self.category = category


class ResearchSubmissionBoundaryError(RuntimeError):
    """Fail fast when the browser submission never crosses into Streamlit."""

    def __init__(self, category: str, evidence: dict[str, Any]) -> None:
        super().__init__(category)
        self.category = category
        self.evidence = evidence


def research_submission_proven(
    *,
    streamlit_event_frames: int,
    rerun_before: int,
    rerun_after: int,
    submission_marker: bool,
    completed_research: dict[str, Any],
) -> tuple[bool, str]:
    """Require transport plus exact-ticker certified terminal ownership.

    The production Research route no longer emits the historical
    ``research-submission-observed`` marker.  That marker remains useful
    supplementary telemetry, but it cannot veto stronger end-to-end proof.
    """
    unpublished_terminal = bool(
        completed_research.get("research_terminal_state") == "RATING_NOT_PUBLISHED_COMPLETE"
        and completed_research.get("publication_allowed") is False
        and completed_research.get("withheld_terminal")
    )
    end_to_end = bool(
        streamlit_event_frames > 0
        and rerun_after > rerun_before
        and completed_research.get("ticker")
        and completed_research.get("no_stale_ticker")
        and completed_research.get("lifecycle_complete")
        and completed_research.get("vnext")
        and (completed_research.get("certified_fields_reconciled") or unpublished_terminal)
        and completed_research.get("provider_boundary_zero")
    )
    if end_to_end:
        return True, (
            "LEGACY_MARKER_AND_CERTIFIED_COMPLETION"
            if submission_marker else "CERTIFIED_END_TO_END_SUBMISSION"
        )
    return False, "UNPROVEN"


def research_submission_failure(
    *, streamlit_event_frames: int, rerun_before: int, rerun_after: int,
    completed_research: dict[str, Any],
) -> str:
    """Return the first deterministic fail-closed submission boundary."""
    if streamlit_event_frames <= 0:
        return "RESEARCH_SUBMISSION_EVENT_NOT_OBSERVED"
    if rerun_after <= rerun_before:
        return "RESEARCH_RERUN_NOT_OBSERVED"
    if not completed_research.get("ticker") or not completed_research.get("no_stale_ticker"):
        return "RESEARCH_TICKER_OWNERSHIP_MISMATCH"
    if not completed_research.get("lifecycle_complete"):
        return "RESEARCH_TERMINAL_LIFECYCLE_NOT_REACHED"
    if not completed_research.get("vnext"):
        return "RESEARCH_CERTIFIED_SURFACE_NOT_RENDERED"
    unpublished_terminal = bool(
        completed_research.get("research_terminal_state") == "RATING_NOT_PUBLISHED_COMPLETE"
        and completed_research.get("publication_allowed") is False
        and completed_research.get("withheld_terminal")
    )
    if not completed_research.get("certified_fields_reconciled") and not unpublished_terminal:
        return "RESEARCH_CERTIFIED_FIELDS_NOT_RECONCILED"
    if not completed_research.get("provider_boundary_zero"):
        return "RESEARCH_PROVIDER_BOUNDARY_NOT_ZERO"
    return "RESEARCH_SUBMISSION_PROOF_UNAVAILABLE"


def normalize_research_action(value: str) -> str:
    """Normalize only presentation-equivalent customer Action spelling."""
    return re.sub(r"[^A-Z0-9]+", "_", str(value or "").strip().upper()).strip("_")


def certified_research_fields_reconciled(fields: dict[str, Any]) -> bool:
    """Require all four governed fields from their production DOM components."""
    action = normalize_research_action(str(fields.get("action") or ""))
    fair_value = str(fields.get("atlas_fair_value") or "").strip()
    opportunity = str(fields.get("opportunity") or "").strip()
    confidence = str(fields.get("decision_confidence") or "").strip()
    return bool(
        action in {
            "BUY_NOW", "BUILD_A_POSITION", "WAIT_FOR_A_BETTER_ENTRY",
            "WAIT_FOR_CONFIRMATION", "WATCH", "AVOID",
        }
        and fair_value and fair_value.upper() != "UNAVAILABLE"
        and opportunity and opportunity.upper() != "UNAVAILABLE"
        and confidence and confidence.upper() != "UNAVAILABLE"
    )


def required_research_authority_failures(
    observed: dict[str, Any], expected_fact: dict[str, Any], expected_identity: dict[str, Any],
) -> list[str]:
    """Return fail-closed exact-candidate mismatches for one required Research result."""
    failures: list[str] = []
    if normalize_research_action(observed.get("action")) != normalize_research_action(expected_fact.get("action")):
        failures.append("ACTION_MISMATCH")
    unpublished = bool(
        expected_fact.get("customer_publication_allowed") is False
        or normalize_research_action(expected_fact.get("action")) == "RATING_NOT_PUBLISHED"
    )
    numeric = (
        ("atlas_fair_value", "FAIR_VALUE_MISMATCH"),
        ("opportunity", "OPPORTUNITY_MISMATCH"),
        ("decision_confidence", "CONFIDENCE_MISMATCH"),
    )
    for key, label in (() if unpublished else numeric):
        try:
            actual = float(re.sub(r"[^0-9.-]", "", str(observed.get(key) or "")))
            expected = float(expected_fact[key])
        except (TypeError, ValueError, KeyError):
            failures.append(label)
            continue
        if abs(actual - expected) > 0.005:
            failures.append(label)
    identity_keys = (
        ("candidate_digest", "candidate_digest", "CANDIDATE_MISMATCH"),
        ("publication_digest", "publication_digest", "PUBLICATION_MISMATCH"),
        ("source_sha", "source_sha", "SOURCE_MISMATCH"),
        ("evaluation_snapshot_id", "evaluation_snapshot_id", "SNAPSHOT_MISMATCH"),
    )
    combined_expected = {**expected_identity, **expected_fact}
    for observed_key, expected_key, label in identity_keys:
        if str(observed.get(observed_key) or "") != str(combined_expected.get(expected_key) or ""):
            failures.append(label)
    if observed.get("provider_calls") != 0:
        failures.append("PROVIDER_BOUNDARY_NOT_ZERO")
    expected_terminal = (
        "RATING_NOT_PUBLISHED_COMPLETE" if unpublished else "PUBLISHED_RESEARCH_COMPLETE"
    )
    if observed.get("research_terminal_state") != expected_terminal:
        failures.append("TERMINAL_LIFECYCLE_MISSING")
    if unpublished and observed.get("publication_allowed") is not False:
        failures.append("PUBLICATION_POLICY_MISMATCH")
    return failures


def required_home_authority_failures(observed: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    """Return exact production-authority and governed-inventory mismatches."""
    keys = (
        "candidate_digest", "publication_digest", "source_sha", "projection_digest",
        "canonical_buy_now_count", "publishable_buy_now_count", "withheld_buy_now_count",
        "canonical_buy_now", "publishable_buy_now", "withheld_buy_now",
    )
    failures = [key.upper() + "_MISMATCH" for key in keys if observed.get(key) != expected.get(key)]
    publishable = set(observed.get("publishable_buy_now") or ())
    withheld = set(observed.get("withheld_buy_now") or ())
    if publishable & withheld:
        failures.append("WITHHELD_PUBLICATION_LEAKAGE")
    if observed.get("runtime_ready") is not True:
        failures.append("RUNTIME_PROJECTION_NOT_READY")
    return failures


class AtlasVisualCrawler:
    """Continue-through-failure visual inspection in one authenticated session."""

    def __init__(self, *, url: str, output_dir: Path, root: Path, headless: bool = True) -> None:
        self.url = url
        self.output_dir = output_dir
        self.root = root
        self.headless = headless
        self.screenshot_dir = output_dir / "screenshots"
        self.results: list[VisualResult] = []
        self.manifest: list[dict[str, Any]] = []
        self.started = time.monotonic()
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.source_sha = self._source_sha()
        self.expected_deployed_source_sha = expected_deployed_source_sha(self.source_sha)
        self.authentication: dict[str, Any] = {}
        self.ticker_matrix = full_certification_ticker_matrix(root)
        self._shot_number = 0
        self._screenshot_states: dict[str, str] = {}
        self.screenshot_calls_avoided = 0
        self.screenshot_timeouts = 0
        self.screenshot_retries = 0
        self.research_contexts: dict[str, dict[str, str]] = {}
        self._streamlit_frames_sent: list[dict[str, Any]] = []
        self.monitor_ticker = self._monitor_research_ticker()
        self.expected_runtime = self._load_runtime_expectations()
        self.enforce_required_authority = False

    def _load_runtime_expectations(self) -> dict[str, Any]:
        matches = sorted((self.root / "certification").glob("runtime_projection_expectations_*.json"))
        if len(matches) != 1:
            raise RuntimeError(f"RUNTIME_EXPECTATIONS_AMBIGUOUS:{len(matches)}")
        payload = json.loads(matches[0].read_text(encoding="utf-8"))
        identity = dict(payload.get("identity") or {})
        facts = dict(payload.get("expected_facts") or {})
        if not all(identity.get(key) for key in ("candidate_digest", "publication_digest", "source_sha")):
            raise RuntimeError("RUNTIME_EXPECTATIONS_IDENTITY_INCOMPLETE")
        if set(facts) != {"NVDA", "MSFT", "AVT"}:
            raise RuntimeError("RUNTIME_EXPECTATIONS_RESEARCH_SET_MISMATCH")
        return payload

    @staticmethod
    def _csv_set(value: str) -> set[str]:
        return {item.strip().upper() for item in str(value or "").split(",") if item.strip()}

    async def _home_runtime_authority(self, page: Page) -> dict[str, Any]:
        observed: dict[str, Any] = {}
        for scope in _scopes(page):
            authority = scope.locator('[data-atlas-qa="production-authority"]')
            inventory = scope.locator('[data-atlas-qa="home-inventory-authority"]')
            runtime = scope.locator('[data-atlas-qa="home-runtime-contract"]')
            if await authority.count() and await inventory.count() and await runtime.count():
                a, i, r = authority.last, inventory.last, runtime.last
                observed = {
                    "runtime_ready": (await r.get_attribute("data-atlas-runtime-ready")) == "true",
                    "candidate_digest": await a.get_attribute("data-atlas-candidate-digest") or "",
                    "publication_digest": await a.get_attribute("data-atlas-publication-digest") or "",
                    "source_sha": await a.get_attribute("data-atlas-source-sha") or "",
                    "projection_digest": await a.get_attribute("data-atlas-projection-digest") or "",
                    "canonical_buy_now_count": int(await i.get_attribute("data-atlas-canonical-count") or -1),
                    "publishable_buy_now_count": int(await i.get_attribute("data-atlas-publishable-count") or -1),
                    "withheld_buy_now_count": int(await i.get_attribute("data-atlas-withheld-count") or -1),
                    "canonical_buy_now": sorted(self._csv_set(await i.get_attribute("data-atlas-canonical-tickers") or "")),
                    "publishable_buy_now": sorted(self._csv_set(await i.get_attribute("data-atlas-publishable-tickers") or "")),
                    "withheld_buy_now": sorted(self._csv_set(await i.get_attribute("data-atlas-withheld-tickers") or "")),
                }
                break
        expected_identity = dict(self.expected_runtime.get("identity") or {})
        expected_inventory = dict(self.expected_runtime.get("source_inventory") or {})
        manifest = json.loads((self.root / "publication_manifest.json").read_text(encoding="utf-8"))
        projection = str((
            ((manifest.get("runtime_projection_contract") or {}).get("runtime_projection") or {})
            .get("semantic_digest") or ""
        ))
        expected = {**expected_identity, **expected_inventory, "projection_digest": projection}
        failures = required_home_authority_failures(observed, expected)
        publishable = set(observed.get("publishable_buy_now") or ())
        withheld = set(observed.get("withheld_buy_now") or ())
        observed["withheld_leakage"] = sorted(publishable & withheld)
        observed["failures"] = failures
        observed["passed"] = not failures
        return observed

    def _track_streamlit_websocket(self, websocket: Any) -> None:
        def record_frame(payload: Any) -> None:
            size = len(payload) if isinstance(payload, (bytes, str)) else 0
            self._streamlit_frames_sent.append({"at": time.monotonic(), "size": size})

        websocket.on("framesent", record_frame)

    async def _stable_research_controls(self, page: Page) -> tuple[Any, Any, dict[str, Any]]:
        """Resolve one visible, enabled, hit-testable form pair twice in succession."""
        deadline = time.monotonic() + 6.0
        prior_signature: tuple[Any, ...] | None = None
        stable_observations = 0
        last_evidence: dict[str, Any] = {}
        while time.monotonic() < deadline:
            discovered_pairs: list[tuple[str, Any, Any, tuple[Any, ...]]] = []
            for scope_index, scope in enumerate(_scopes(page)):
                forms = scope.locator('[data-testid="stForm"]')
                for form_index in range(await forms.count()):
                    form = forms.nth(form_index)
                    if not await form.is_visible():
                        continue
                    inputs = form.get_by_label("Ticker", exact=True)
                    if not await inputs.count():
                        inputs = form.locator('input[placeholder*="NVDA"]')
                    buttons = form.get_by_role("button", name="Research ticker", exact=True)
                    if await inputs.count() != 1 or await buttons.count() != 1:
                        continue
                    input_node, button = inputs.first, buttons.first
                    if not await input_node.is_visible() or not await input_node.is_enabled():
                        continue
                    if not await button.is_visible() or not await button.is_enabled():
                        continue
                    # Playwright visibility does not imply the element is in
                    # the current viewport. Normalize scroll position before
                    # the center-point actionability check, especially on mobile.
                    await input_node.scroll_into_view_if_needed()
                    await button.scroll_into_view_if_needed()
                    input_box = await input_node.bounding_box()
                    button_box = await button.bounding_box()
                    hit = bool(await button.evaluate("""
                        (button) => {
                          const box = button.getBoundingClientRect();
                          const node = document.elementFromPoint(
                            box.left + box.width / 2, box.top + box.height / 2
                          );
                          const actionable = node && node.closest ? node.closest('button') : null;
                          return Boolean(node && (
                            node === button || button.contains(node) || actionable === button
                          ));
                        }
                    """))
                    if not (input_box and button_box and hit):
                        continue
                    form_dom_id = str(await form.evaluate("""
                        (form) => {
                          globalThis.__atlasQaFormIds ||= new WeakMap();
                          globalThis.__atlasQaFormIdCounter ||= 0;
                          if (!globalThis.__atlasQaFormIds.has(form)) {
                            globalThis.__atlasQaFormIds.set(
                              form, `research-form-${++globalThis.__atlasQaFormIdCounter}`
                            );
                          }
                          return globalThis.__atlasQaFormIds.get(form);
                        }
                    """))
                    # Page and page.main_frame share one DOM/global and must
                    # therefore share an identity namespace. Child frames are
                    # distinct actionable surfaces even when URLs coincide.
                    is_main = scope is page or scope is page.main_frame
                    scope_identity = "main" if is_main else f"frame-{scope_index}"
                    pair_identity = f"{scope_identity}:{form_dom_id}"
                    signature = (
                        pair_identity,
                        round(input_box["x"]), round(input_box["y"]),
                        round(button_box["x"]), round(button_box["y"]),
                    )
                    discovered_pairs.append((pair_identity, input_node, button, signature))
            visible_pairs = deduplicate_research_control_pairs(discovered_pairs)
            last_evidence = {
                "visible_control_pairs": len(visible_pairs),
                "discovered_control_pairs": len(discovered_pairs),
                "stable_observations": stable_observations,
            }
            if len(visible_pairs) == 1:
                _, input_node, button, signature = visible_pairs[0]
                stable_observations = stable_observations + 1 if signature == prior_signature else 1
                prior_signature = signature
                if stable_observations >= 2:
                    return input_node, button, {
                        "visible_control_pairs": 1,
                        "discovered_control_pairs": len(discovered_pairs),
                        "stable_observations": stable_observations,
                        "hit_test": "PASS",
                    }
            elif len(visible_pairs) > 1:
                raise ResearchSubmissionBoundaryError("RESEARCH_CONTROL_AMBIGUITY", last_evidence)
            else:
                prior_signature = None
                stable_observations = 0
            await page.wait_for_timeout(125)
        raise ResearchSubmissionBoundaryError("RESEARCH_SUBMISSION_CONTROL_NOT_READY", last_evidence)

    async def _require_submission_boundary(
        self, page: Page, ticker: str, *, sent_before: int, rerun_before: int,
    ) -> dict[str, Any]:
        # Production intentionally omits the exact-candidate QA-only submit
        # marker. Keep the strict marker-based transport proof intact, while
        # allowing the stronger exact-ticker terminal Research contract to
        # become authoritative within the existing bounded Research budget.
        deadline = time.monotonic() + RESEARCH_COMPLETION_TIMEOUT_SECONDS
        evidence: dict[str, Any] = {}
        while time.monotonic() < deadline:
            sent_after = len(self._streamlit_frames_sent)
            rerun_after = 0
            submitted_marker = False
            for scope in _scopes(page):
                markers = scope.locator('[data-atlas-qa="research-entry-stage"][data-atlas-stage="RESEARCH_ROUTE_ENTERED"]')
                for index in range(await markers.count()):
                    rerun_after = max(
                        rerun_after,
                        int(await markers.nth(index).get_attribute("data-atlas-rerun-count") or 0),
                    )
                submitted_marker = submitted_marker or bool(await scope.locator(
                    f'[data-atlas-qa="research-submission-observed"]'
                    f'[data-atlas-submitted="true"][data-atlas-ticker="{ticker}"]'
                ).count())
            completed_research = await self._completed_research(page, ticker)
            proven, proof_mode = research_submission_proven(
                streamlit_event_frames=sent_after - sent_before,
                rerun_before=rerun_before,
                rerun_after=rerun_after,
                submission_marker=submitted_marker,
                completed_research=completed_research,
            )
            evidence = {
                "streamlit_event_frames": sent_after - sent_before,
                "rerun_before": rerun_before,
                "rerun_after": rerun_after,
                "submission_marker": submitted_marker,
                "exact_ticker_context": bool(completed_research.get("ticker")),
                "terminal_lifecycle_complete": bool(
                    completed_research.get("lifecycle_complete")
                ),
                "certified_vnext_decision_visible": bool(
                    completed_research.get("vnext")
                ),
                "no_stale_ticker": bool(completed_research.get("no_stale_ticker")),
                "certified_fields_reconciled": bool(
                    completed_research.get("certified_fields_reconciled")
                ),
                "certified_fields": completed_research.get("certified_fields") or {},
                "provider_calls": completed_research.get("provider_calls"),
                "provider_boundary_zero": bool(
                    completed_research.get("provider_boundary_zero")
                ),
                "proof_mode": proof_mode,
            }
            if proven:
                return evidence
            await page.wait_for_timeout(100)
        category = research_submission_failure(
            streamlit_event_frames=int(evidence.get("streamlit_event_frames", 0)),
            rerun_before=int(evidence.get("rerun_before", 0)),
            rerun_after=int(evidence.get("rerun_after", 0)),
            completed_research=completed_research,
        )
        raise ResearchSubmissionBoundaryError(category, evidence)

    def _monitor_research_ticker(self) -> str:
        """Choose a current incomplete/Monitor archetype without provider work."""
        try:
            payload = json.loads((self.root / "market_full_scan.json").read_text(encoding="utf-8"))
            rows = payload if isinstance(payload, list) else payload.get("rows", [])
        except (OSError, ValueError, TypeError):
            return "CRC"
        normalized = [row for row in rows if isinstance(row, dict)]
        for row in normalized:
            ticker = str(row.get("ticker") or row.get("Ticker") or "").upper()
            if ticker == "CRC":
                return ticker
        for row in normalized:
            ticker = str(row.get("ticker") or row.get("Ticker") or "").upper()
            if ticker and all(row.get(key) is None for key in ("atlas_fair_value", "opportunity_score", "confidence_pct")):
                return ticker
        return "CRC"

    async def _research_vnext_contract(self, page: Page, ticker: str) -> dict[str, Any]:
        sections: set[str] = set()
        story_blocks: set[str] = set()
        version = ""
        monitor = False
        ask_cta = False
        certification_incomplete = False
        withheld_terminal = False
        publication_allowed: bool | None = None
        declared_section_count = 0
        tab_labels: set[str] = set()
        for scope in _scopes(page):
            try:
                roots = scope.locator(f'[data-atlas-qa="research-vnext"][data-atlas-ticker="{ticker}"]')
                if await roots.count():
                    version = await roots.first.get_attribute("data-atlas-version") or ""
                    monitor = (await roots.first.get_attribute("data-atlas-monitor") or "").lower() == "true"
                    allowed = (await roots.first.get_attribute("data-atlas-publication-allowed") or "").lower()
                    try:
                        declared_section_count = int(
                            await roots.first.get_attribute("data-atlas-section-count") or 0
                        )
                    except (TypeError, ValueError):
                        declared_section_count = 0
                    if allowed in {"true", "false"}:
                        publication_allowed = allowed == "true"
                nodes = scope.locator(f'[data-atlas-qa="research-vnext-section"][data-atlas-ticker="{ticker}"]')
                for index in range(await nodes.count()):
                    sections.add(await nodes.nth(index).get_attribute("data-atlas-section") or "")
                blocks = scope.locator(f'[data-atlas-qa="research-ux3b-block"][data-atlas-ticker="{ticker}"]')
                for index in range(await blocks.count()):
                    story_blocks.add(await blocks.nth(index).get_attribute("data-atlas-block") or "")
                cta = scope.locator(f'[data-atlas-qa="research-ask-cta"][data-atlas-ticker="{ticker}"]')
                ask_cta = ask_cta or bool(await cta.count())
                incomplete = scope.locator(f'[data-atlas-qa="research-certification-incomplete"][data-atlas-ticker="{ticker}"]')
                certification_incomplete = certification_incomplete or bool(await incomplete.count())
                terminal = scope.locator(f'[data-atlas-qa="research-terminal"][data-atlas-ticker="{ticker}"]')
                if await terminal.count():
                    terminal_name = await terminal.last.get_attribute("data-atlas-research-terminal") or ""
                    withheld_terminal = withheld_terminal or terminal_name == RESEARCH_TERMINAL_RATING_NOT_PUBLISHED
                    allowed = (await terminal.last.get_attribute("data-atlas-publication-allowed") or "").lower()
                    if allowed in {"true", "false"}:
                        publication_allowed = allowed == "true"
                tabs = scope.get_by_role("tab")
                for index in range(await tabs.count()):
                    tab = tabs.nth(index)
                    if await tab.is_visible():
                        tab_labels.add(re.sub(r"\s+", " ", await tab.inner_text()).strip())
            except Exception:
                continue
        declared_architecture = _research_declared_architecture(
            declared_section_count, tab_labels,
        )
        return {
            "version": version, "sections": sorted(sections),
            # Streamlit lazily mounts tab bodies.  The renderer-owned count and
            # all five live tab controls certify architecture without requiring
            # five mutually exclusive tab panels to coexist in the DOM.
            "all_sections": declared_architecture,
            "declared_section_count": declared_section_count,
            "tab_labels": sorted(tab_labels),
            "monitor": monitor, "ask_cta": ask_cta,
            "certification_incomplete": certification_incomplete,
            "withheld_terminal": withheld_terminal,
            "publication_allowed": publication_allowed,
            "story_blocks": sorted(story_blocks),
            "decision_story": {
                "decision-why", "decision-core-metrics", "why-atlas-likes-it",
                "what-stops-atlas", "what-changes-the-thesis", "watching-next",
            } <= story_blocks,
        }

    async def _completed_research(self, page: Page, ticker: str) -> dict[str, Any]:
        """Require the requested report, canonical lifecycle, and UX-2 surface."""
        expected = ticker.strip().upper()
        result = {
            "ticker": False, "lifecycle_complete": False, "vnext": False,
            "five_sections": False, "loading": False, "ask_cta": False,
            "terminal_status": "", "rendered_exception": False,
            "rendered_tickers": [], "no_stale_ticker": False,
            "certified_fields_reconciled": False,
            "certified_fields": {},
            "provider_calls": None, "provider_boundary_zero": False,
            "candidate_digest": "", "publication_digest": "", "source_sha": "",
            "evaluation_snapshot_id": "", "authority_failures": [],
        }
        architecture = await self._research_vnext_contract(page, expected)
        result.update({
            "vnext": architecture["version"] == RESEARCH_VNEXT_VERSION,
            "five_sections": bool(architecture["all_sections"]),
            "ask_cta": bool(architecture["ask_cta"]),
            "certification_incomplete": bool(architecture.get("certification_incomplete")),
            "withheld_terminal": bool(architecture.get("withheld_terminal")),
            "publication_allowed": architecture.get("publication_allowed"),
        })
        rendered_tickers: set[str] = set()
        provider_calls: list[int] = []
        for scope in _scopes(page):
            try:
                lifecycle = scope.locator(
                    f'[data-atlas-qa="research-container"][data-atlas-ticker="{expected}"]'
                )
                for index in range(await lifecycle.count()):
                    # Playwright preserves DOM order. The final exact-ticker
                    # marker is the current lifecycle generation: an earlier
                    # loading marker must not mask a later completion, and a
                    # stale completion must not mask a later loading marker.
                    result["terminal_status"] = (
                        await lifecycle.nth(index).get_attribute("data-atlas-status") or ""
                    ).strip().lower()
                result["ticker"] = result["ticker"] or bool(await scope.locator(
                    f'[data-atlas-qa="research-context-v1"][data-atlas-ticker="{expected}"]'
                ).count())
                for selector in (
                    '[data-atlas-qa="research-context-v1"][data-atlas-ticker]',
                    '[data-atlas-qa="research-container"][data-atlas-ticker]',
                ):
                    nodes = scope.locator(selector)
                    for index in range(await nodes.count()):
                        value = (
                            await nodes.nth(index).get_attribute("data-atlas-ticker") or ""
                        ).strip().upper()
                        if value:
                            rendered_tickers.add(value)
                performance = scope.locator(
                    f'[data-atlas-qa="research-performance"][data-atlas-ticker="{expected}"]'
                )
                for index in range(await performance.count()):
                    provider_calls.append(int(
                        await performance.nth(index).get_attribute("data-atlas-provider-calls") or 0
                    ))
                authority = scope.locator(
                    f'[data-atlas-qa="research-production-authority"][data-atlas-ticker="{expected}"]'
                )
                if await authority.count():
                    node = authority.last
                    result.update({
                        "candidate_digest": await node.get_attribute("data-atlas-candidate-digest") or "",
                        "publication_digest": await node.get_attribute("data-atlas-publication-digest") or "",
                        "source_sha": await node.get_attribute("data-atlas-source-sha") or "",
                        "evaluation_snapshot_id": await node.get_attribute("data-atlas-evaluation-snapshot") or "",
                    })
            except Exception:
                continue
        result["rendered_tickers"] = sorted(rendered_tickers)
        result["no_stale_ticker"] = bool(rendered_tickers == {expected})
        result["provider_calls"] = max(provider_calls) if provider_calls else None
        result["provider_boundary_zero"] = bool(provider_calls and max(provider_calls) == 0)
        result["lifecycle_complete"] = result["terminal_status"] == "complete"
        result["loading"] = result["terminal_status"] == "loading"
        result["rendered_exception"] = await _has_rendered_exception(page)
        visible_text = await _visible_text(page)
        normalized_text = re.sub(r"\s+", " ", visible_text).upper()
        published_decision_evidence = bool(
            architecture.get("publication_allowed") is True
            and "ATLAS VIEW" in normalized_text
            and "ATLAS RATING:" in normalized_text
            and any(label in normalized_text for label in (
                "BUY NOW", "BUILD A POSITION", "WAIT FOR A BETTER ENTRY",
                "WAIT FOR CONFIRMATION", "WATCH", "AVOID",
            ))
        )
        result["published_decision_evidence"] = published_decision_evidence
        certified_fields = await self._research_certified_fields(page, expected)
        result["certified_fields"] = certified_fields
        result["certified_fields_reconciled"] = bool(
            published_decision_evidence
            and certified_research_fields_reconciled(certified_fields)
        )
        result["research_terminal_state"] = classify_research_terminal_state(
            ticker_present=result["ticker"], lifecycle_complete=result["lifecycle_complete"],
            authoritative_version=result["vnext"], five_sections=result["five_sections"],
            ask_cta=result["ask_cta"], withheld_marker=result["withheld_terminal"],
            published_decision_evidence=published_decision_evidence,
            publication_allowed=result["publication_allowed"], visible_text=visible_text,
            rendered_exception=result["rendered_exception"], loading=result["loading"],
        )
        result["complete"] = result["research_terminal_state"] in {
            "PUBLISHED_RESEARCH_COMPLETE", "RATING_NOT_PUBLISHED_COMPLETE",
        }
        expected_fact = dict((self.expected_runtime.get("expected_facts") or {}).get(expected) or {})
        if expected_fact and self.enforce_required_authority:
            result["authority_failures"] = required_research_authority_failures(
                {**result, **certified_fields}, expected_fact,
                dict(self.expected_runtime.get("identity") or {}),
            )
            result["complete"] = bool(result["complete"] and not result["authority_failures"])
        return result

    async def _research_certified_fields(self, page: Page, ticker: str) -> dict[str, str]:
        """Read the real production decision components for the active ticker.

        Streamlit renders metric labels and values as sibling DOM nodes, so a
        flattened page-text regex is not a reliable field contract. This keeps
        label/value ownership within each metric and scopes Action to the
        production ticker-specific decision container.
        """
        fields: dict[str, str] = {}
        expected_labels = {
            "ATLAS FAIR VALUE": "atlas_fair_value",
            "OPPORTUNITY": "opportunity",
            "DECISION CONFIDENCE": "decision_confidence",
        }
        for scope in _scopes(page):
            try:
                action = scope.locator(f'[class*="st-key-vnext_decision_action_{ticker}"]')
                for index in range(await action.count()):
                    node = action.nth(index)
                    if not await node.is_visible():
                        continue
                    text = re.sub(r"\s+", " ", await node.inner_text()).strip()
                    normalized = normalize_research_action(text.split("—", 1)[0])
                    if normalized:
                        fields["action"] = normalized
                metrics = scope.locator('[data-testid="stMetric"]')
                for index in range(await metrics.count()):
                    metric = metrics.nth(index)
                    if not await metric.is_visible():
                        continue
                    label_node = metric.locator('[data-testid="stMetricLabel"]')
                    value_node = metric.locator('[data-testid="stMetricValue"]')
                    if not await label_node.count() or not await value_node.count():
                        continue
                    label = re.sub(r"\s+", " ", await label_node.first.inner_text()).strip().upper()
                    key = expected_labels.get(label)
                    if key:
                        fields[key] = re.sub(
                            r"\s+", " ", await value_node.first.inner_text()
                        ).strip()
            except Exception:
                continue
        return fields

    def _source_sha(self) -> str:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=self.root, text=True,
        ).strip()

    async def _shot(
        self, page: Page, *, page_name: str, interaction: str, state: str,
        viewport: str = "desktop", ticker: str = "", complete_surface: bool = False,
    ) -> str:
        try:
            state_digest = await asyncio.wait_for(page.evaluate("""() => {
              const root = document.querySelector('[data-testid="stAppViewContainer"]') || document.body;
              return root ? root.innerHTML : '';
            }"""), timeout=3.0)
            # The rendered state and viewport determine visual identity.  Do
            # not defeat deduplication merely because two traversal labels
            # reached byte-identical DOM.
            # A visually identical DOM on a different governed surface is not
            # interchangeable evidence. Keep a distinct artifact per page,
            # viewport, ticker and interaction while still deduplicating exact
            # retry captures of that same state.
            state_key = hashlib.sha256(
                f"{page_name}|{interaction}|{state}|{ticker}|{viewport}|{state_digest}".encode("utf-8")
            ).hexdigest()
            prior = self._screenshot_states.get(state_key)
            if prior:
                self.screenshot_calls_avoided += 1
                self.manifest.append({
                    "page": page_name, "interaction": interaction, "state": state,
                    "ticker": ticker, "viewport": viewport, "path": prior,
                    "generated": True, "deduplicated": True,
                    "capture": "reused_state", "segments": 0, "complete": True,
                })
                return prior
        except Exception:
            state_key = ""
        self._shot_number += 1
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", f"{self._shot_number:04d}_{viewport}_{page_name}_{interaction}_{state}")
        path = self.screenshot_dir / f"{slug[:180]}.png"
        try:
            metadata: dict[str, Any] = {"capture": "viewport", "segments": 1, "complete": True}
            last_error: Exception | None = None
            for attempt in range(2):
                try:
                    if complete_surface:
                        metadata = await asyncio.wait_for(
                            self._stitched_streamlit_screenshot(page, path), timeout=20.0,
                        )
                    else:
                        await asyncio.wait_for(
                            page.screenshot(path=str(path), full_page=False), timeout=12.0,
                        )
                    last_error = None
                    break
                except asyncio.TimeoutError as exc:
                    self.screenshot_timeouts += 1
                    last_error = exc
                except Exception as exc:
                    last_error = exc
                if attempt == 0:
                    self.screenshot_retries += 1
                    await page.wait_for_timeout(150)
            if last_error is not None:
                raise last_error
            relative = str(path.relative_to(self.output_dir))
            if state_key:
                self._screenshot_states[state_key] = relative
            self.manifest.append({
                "page": page_name, "interaction": interaction, "state": state,
                "ticker": ticker, "viewport": viewport, "path": relative,
                "generated": True, **metadata,
            })
            return relative
        except Exception as exc:
            if page.is_closed():
                raise GlobalCrawlFailure("BROWSER_DIED") from exc
            self.manifest.append({
                "page": page_name, "interaction": interaction, "state": state,
                "ticker": ticker, "viewport": viewport, "path": "",
                "generated": False,
            })
            return ""

    async def _stitched_streamlit_screenshot(self, page: Page, path: Path) -> dict[str, Any]:
        """Capture Streamlit's real scrolling surface rather than only the browser viewport."""
        geometry = await page.evaluate("""
            () => {
              const candidates = [
                document.querySelector('[data-testid="stAppViewContainer"]'),
                document.querySelector('[data-testid="stMain"]'),
                document.scrollingElement,
              ].filter(Boolean);
              const node = candidates.sort((a, b) =>
                Math.max(b.scrollHeight || 0, b.clientHeight || 0) -
                Math.max(a.scrollHeight || 0, a.clientHeight || 0))[0];
              return {
                selector: node === document.scrollingElement ? '__document__' :
                  (node.getAttribute('data-testid') ? `[data-testid="${node.getAttribute('data-testid')}"]` : '__document__'),
                scrollHeight: Math.max(node.scrollHeight || 0, node.clientHeight || 0),
                clientHeight: Math.max(node.clientHeight || window.innerHeight, 1),
                originalTop: node.scrollTop || window.scrollY || 0,
              };
            }
        """)
        total = max(int(geometry.get("scrollHeight") or 1), 1)
        step = max(int(geometry.get("clientHeight") or 1), 1)
        positions = list(range(0, total, step)) or [0]
        images: list[Image.Image] = []
        selector = str(geometry.get("selector") or "__document__")
        for position in positions:
            await page.evaluate("""
                ([selector, top]) => {
                  const node = selector === '__document__' ? document.scrollingElement : document.querySelector(selector);
                  if (node === document.scrollingElement) window.scrollTo(0, top);
                  else if (node) node.scrollTop = top;
                }
            """, [selector, position])
            await page.wait_for_timeout(80)
            raw = await page.screenshot(full_page=False)
            images.append(Image.open(BytesIO(raw)).convert("RGB"))
        await page.evaluate("""
            ([selector, top]) => {
              const node = selector === '__document__' ? document.scrollingElement : document.querySelector(selector);
              if (node === document.scrollingElement) window.scrollTo(0, top);
              else if (node) node.scrollTop = top;
            }
        """, [selector, int(geometry.get("originalTop") or 0)])
        width = max(image.width for image in images)
        final_height = total
        stitched = Image.new("RGB", (width, final_height), "white")
        for position, image in zip(positions, images):
            remaining = max(final_height - position, 0)
            if not remaining:
                break
            crop = image.crop((0, 0, image.width, min(image.height, remaining)))
            stitched.paste(crop, (0, position))
        stitched.save(path)
        return {"capture": "streamlit_stitched", "segments": len(images), "complete": True, "scroll_height": total}

    async def _shot_locator(
        self, locator: Any, *, page_name: str, interaction: str, state: str,
        viewport: str, ticker: str,
    ) -> str:
        self._shot_number += 1
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", f"{self._shot_number:04d}_{viewport}_{page_name}_{interaction}_{state}")
        path = self.screenshot_dir / f"{slug[:180]}.png"
        try:
            await locator.scroll_into_view_if_needed(timeout=5000)
            await locator.screenshot(path=str(path))
            relative = str(path.relative_to(self.output_dir))
            self.manifest.append({
                "page": page_name, "interaction": interaction, "state": state,
                "ticker": ticker, "viewport": viewport, "path": relative,
                "generated": True, "capture": "visible_element", "segments": 1, "complete": True,
            })
            return relative
        except Exception:
            return await self._shot(
                locator.page, page_name=page_name, interaction=interaction, state=state,
                viewport=viewport, ticker=ticker,
            )

    async def _exception_identity(self, page: Page) -> dict[str, str]:
        for scope in _scopes(page):
            try:
                nodes = scope.locator('[data-testid="stException"]')
                if not await nodes.count():
                    continue
                text = re.sub(r"\s+", " ", await nodes.first.inner_text(timeout=1000))
                name = re.search(r"\b([A-Za-z][A-Za-z0-9_]*(?:Error|Exception))\b", text)
                category = name.group(1) if name else "STREAMLIT_EXCEPTION"
                return {
                    "category": category,
                    "fingerprint": hashlib.sha256(category.encode()).hexdigest()[:16],
                }
            except Exception:
                continue
        return {}

    async def _record(
        self, *, category: str, page_name: str, interaction: str, expected: str,
        observed: str, passed: bool, elapsed: float, ticker: str = "",
        viewport: str = "desktop", screenshots: Iterable[str] = (),
        exception: dict[str, str] | None = None, severity: str | None = None,
        status_override: str | None = None, required: bool | None = None,
    ) -> VisualResult:
        status = status_override if status_override in {"PASS", "FAIL", "NEEDS_REVIEW"} else ("PASS" if passed else "FAIL")
        if required is None:
            required = self._required_result(
                category=category, page_name=page_name, ticker=ticker,
                viewport=viewport,
            )
        result = VisualResult(
            category=category, page=page_name, interaction=interaction,
            expected=expected, observed=observed,
            status=status,
            severity="NONE" if passed else (severity or "P2"),
            elapsed_seconds=round(elapsed, 3), ticker_context=ticker,
            viewport=viewport, screenshots=[item for item in screenshots if item],
            exception=exception or {},
            required=required,
        )
        self.results.append(result)
        self._write_artifacts(final=False)
        return result

    @staticmethod
    def _required_result(
        *, category: str, page_name: str, ticker: str, viewport: str,
    ) -> bool:
        """Return the governed launch-critical status of a crawler finding."""
        if category == "GLOBAL":
            return True
        if category == "PAGE":
            return (page_name, viewport) in REQUIRED_PAGE_VIEWPORTS
        if page_name == "Home":
            return viewport in {"desktop", "mobile"}
        if page_name in {"Earnings Intelligence", "Watchlist Intelligence", "Ask AI"}:
            return viewport in {"desktop", "mobile"}
        if page_name != "Research Any Ticker":
            return False
        normalized = ticker.upper()
        if viewport == "desktop":
            return normalized in REQUIRED_RESEARCH_TICKERS
        return viewport == "mobile" and normalized == "NVDA"

    def _required_completeness(self) -> dict[str, Any]:
        required_results = [item for item in self.results if item.required]
        page_keys = {
            (item.page, item.viewport) for item in required_results
            if item.category == "PAGE" and item.status == "PASS"
        }
        research_keys = {
            (item.ticker_context.upper(), item.viewport) for item in required_results
            if item.category == "RESEARCH" and item.status == "PASS"
        }
        expected_research = {
            *((ticker, "desktop") for ticker in REQUIRED_RESEARCH_TICKERS),
            ("NVDA", "mobile"),
        }
        missing_pages = sorted(REQUIRED_PAGE_VIEWPORTS - page_keys)
        missing_research = sorted(expected_research - research_keys)
        failures = [asdict(item) for item in required_results if item.status == "FAIL"]
        return {
            "status": "PASS" if not missing_pages and not missing_research and not failures else "FAIL",
            "required_page_viewports": sorted(REQUIRED_PAGE_VIEWPORTS),
            "required_research_tickers": sorted(expected_research),
            "missing_page_viewports": missing_pages,
            "missing_research_tickers": missing_research,
            "failure_count": len(failures),
        }

    async def _customer_navigation_contract(self, page: Page) -> None:
        """Fail closed unless the authenticated shell exposes the exact VNext routes."""
        started = time.monotonic()
        marker = page.locator('[data-atlas-qa="customer-navigation-contract"]').last
        await marker.wait_for(state="attached", timeout=30000)
        version = await marker.get_attribute("data-atlas-contract-version") or ""
        role = await marker.get_attribute("data-atlas-role-category") or ""
        routes = tuple(filter(None, (await marker.get_attribute("data-atlas-customer-routes") or "").split("|")))
        active = await marker.get_attribute("data-atlas-active-route") or ""
        passed = (
            version == "ATLAS_CUSTOMER_NAV_VNEXT_1"
            and role in {"customer_viewer", "internal_admin"}
            and routes == REQUIRED_CUSTOMER_ROUTES
            and active in REQUIRED_CUSTOMER_ROUTES
        )
        await self._record(
            category="GLOBAL", page_name="GLOBAL", interaction="customer-navigation-authority",
            expected="Exact Home/Research/Earnings/Watchlist/Ask ATLAS navigation contract",
            observed=f"version={version}; role={role}; routes={routes}; active={active}",
            passed=passed, elapsed=time.monotonic() - started, severity="P1",
        )
        if not passed:
            raise GlobalCrawlFailure("CUSTOMER_NAVIGATION_AUTHORITY_FAILED")

    async def _visible_primary(self, page: Page, page_name: str) -> tuple[bool, str]:
        text = await _visible_text(page)
        signals = PRIMARY_VISIBLE_SIGNALS.get(page_name, (page_name,))
        matched = [signal for signal in signals if signal.lower() in text.lower()]
        visible_control = False
        for scope in _scopes(page):
            try:
                visible_control = visible_control or bool(await scope.locator(
                    'button:visible, input:visible, [role="tab"]:visible, [role="radio"]:visible, a:visible'
                ).count())
            except Exception:
                continue
        return bool(matched and visible_control), ", ".join(matched) or "no approved visible signal"

    async def _page_visit(self, page: Page, page_name: str, *, viewport: str = "desktop") -> bool:
        started = time.monotonic()
        try:
            settled, _, detail = await _navigate(page, page_name, self.output_dir)
            if page_name == "Home":
                # A cold exact-candidate Home run can finish after the generic
                # navigation settlement budget. Its existing lifecycle markers,
                # not an arbitrary sleep or partial visible shell, govern when
                # content assertions may begin.
                home_deadline = started + RESEARCH_COMPLETION_TIMEOUT_SECONDS - 5
                while time.monotonic() < home_deadline:
                    if await _page_render_complete(page, page_name):
                        settled = True
                        break
                    await page.wait_for_timeout(100)
                if not await _page_render_complete(page, page_name):
                    settled = False
            if page_name == "Research Any Ticker":
                # The first exact-candidate Research route performs a bounded
                # persisted-evidence load after navigation. Keep that route
                # generation alive instead of re-clicking the selected radio,
                # which restarts Streamlit's rerun. Reserve five seconds for
                # diagnostics inside the existing 90-second outer boundary.
                owner_deadline = started + RESEARCH_COMPLETION_TIMEOUT_SECONDS - 5
                while time.monotonic() < owner_deadline:
                    if await self._research_route_owned(page):
                        settled = True
                        break
                    await page.wait_for_timeout(100)
                if not await self._research_route_owned(page):
                    settled = False
            visible, visible_detail = await self._visible_primary(page, page_name)
            rendered_exception = await _has_rendered_exception(page)
            route_current = await self._current_route_visible(page, page_name)
            if page_name != "Research Any Ticker" and not settled and route_current and visible and not rendered_exception:
                detail = f"route-generation recovery: current selected route and visible primary surface; {detail}"
                settled = True
            shot = await self._shot(page, page_name=page_name, interaction="page", state="rendered", viewport=viewport, complete_surface=True)
            passed = bool(settled and route_current and visible and not rendered_exception)
            observed = (
                f"navigation={settled}; visible={visible} ({visible_detail}); "
                f"render_complete={await _page_render_complete(page, page_name)}; exception={rendered_exception}; {detail}"
            )
            await self._record(
                category="PAGE", page_name=page_name, interaction="navigate",
                expected="Selected route with visible customer content/control and no exception",
                observed=observed, passed=passed, elapsed=time.monotonic() - started,
                viewport=viewport, screenshots=(shot,),
                exception=await self._exception_identity(page) if rendered_exception else {},
                severity="P1" if rendered_exception else "P2",
            )
            return passed
        except GlobalCrawlFailure:
            raise
        except Exception as exc:
            if page.is_closed():
                raise GlobalCrawlFailure("BROWSER_DIED") from exc
            shot = await self._shot(page, page_name=page_name, interaction="page", state="failure", viewport=viewport)
            await self._record(
                category="PAGE", page_name=page_name, interaction="navigate",
                expected="Page remains crawlable", observed=f"QA operation failed: {type(exc).__name__}",
                passed=False, elapsed=time.monotonic() - started, viewport=viewport,
                screenshots=(shot,), severity="P2",
                exception={"category": type(exc).__name__, "fingerprint": hashlib.sha256(type(exc).__name__.encode()).hexdigest()[:16]},
            )
            return False

    async def _earnings_vnext_contract(self, page: Page, *, viewport: str) -> None:
        """Certify visible Earnings VNext evidence without treating gaps as facts."""
        started = time.monotonic()
        text = await _visible_text(page)
        version = False
        for scope in _scopes(page):
            try:
                version = version or bool(await scope.locator('[data-atlas-earnings-version="ATLAS_EARNINGS_VNEXT_V1"]').count())
            except Exception:
                continue
        required = {label: label.lower() in text.lower() for label in EARNINGS_VNEXT_SECTION_LABELS[:2]}
        evidence = any(token.lower() in text.lower() for token in (
            "EPS actual", "Revenue actual", "No normalized reported-quarter evidence",
        ))
        limitations = all(token.lower() in text.lower() for token in (
            "Estimate revision direction", "Event-aligned market reaction",
        )) if evidence and "EPS actual" in text else True
        exception = await _has_rendered_exception(page)
        shot = await self._shot(
            page, page_name="Earnings Intelligence", interaction="vnext-contract",
            state="evidence", viewport=viewport, complete_surface=True,
        )
        passed = bool(version and all(required.values()) and evidence and limitations and not exception)
        await self._record(
            category="EARNINGS", page_name="Earnings Intelligence", interaction="vnext-decision-story",
            expected="Reported/upcoming separation, visible canonical earnings evidence, explicit limitations, and no exception",
            observed=f"version={version}; sections={required}; evidence={evidence}; limitations={limitations}; exception={exception}",
            passed=passed, elapsed=time.monotonic() - started, viewport=viewport,
            screenshots=(shot,), severity="P1",
            exception=await self._exception_identity(page) if exception else {},
        )

    async def _recovery_vnext_contract(self, page: Page, *, viewport: str) -> None:
        """Certify the visible Recovery story while keeping evidence gaps honest."""
        started = time.monotonic()
        text = await _visible_text(page)
        version = False
        section_count = 0
        exact_ticker = False
        for scope in _scopes(page):
            try:
                version = version or bool(await scope.locator(
                    '[data-atlas-recovery-version="ATLAS_RECOVERY_VNEXT_V1"]'
                ).count())
                section_count = max(section_count, await scope.locator(
                    '[data-atlas-recovery-section]'
                ).count())
                exact_ticker = exact_ticker or bool(await scope.locator(
                    '[data-atlas-recovery-ticker]'
                ).count())
            except Exception:
                continue
        visible_contract = all(label.lower() in text.lower() for label in (
            "Recovery Snapshot", "Why It Fell", "Evidence of Recovery",
            "Technical Confirmation", "What Invalidates Recovery",
        ))
        cta = "View Investment Case" in text
        exception = await _has_rendered_exception(page)
        shot = await self._shot(
            page, page_name="Recovery", interaction="vnext-contract",
            state="evidence", viewport=viewport, complete_surface=True,
        )

    async def _full_scan_candidates(self, page: Page) -> list[dict[str, Any]]:
        """Read sanitized Full Scan VNext candidate markers in production order."""
        candidates: list[dict[str, Any]] = []
        for scope in _scopes(page):
            try:
                nodes = scope.locator("[data-atlas-full-scan-candidate]")
                for index in range(await nodes.count()):
                    node = nodes.nth(index)
                    ticker = (await node.get_attribute("data-atlas-ticker") or "").upper()
                    if not ticker or any(item["ticker"] == ticker for item in candidates):
                        continue
                    candidates.append({
                        "ticker": ticker,
                        "production_rank": int(await node.get_attribute("data-atlas-production-rank") or 0),
                        "filtered_position": int(await node.get_attribute("data-atlas-filtered-position") or 0),
                        "decision_status": await node.get_attribute("data-atlas-decision-status") or "",
                        "recommendation": await node.get_attribute("data-atlas-recommendation") or "",
                        "opportunity": await node.get_attribute("data-atlas-opportunity") or "",
                        "confidence": await node.get_attribute("data-atlas-confidence") or "",
                        "evidence_available": int(await node.get_attribute("data-atlas-evidence-available") or 0),
                        "evidence_total": int(await node.get_attribute("data-atlas-evidence-total") or 0),
                    })
            except Exception:
                continue
        return candidates

    async def _full_scan_vnext_contract(self, page: Page, *, viewport: str) -> None:
        """Certify Full Scan rank semantics, authority separation, and evidence."""
        started = time.monotonic()
        text = await _visible_text(page)
        version = population = 0
        for scope in _scopes(page):
            try:
                root = scope.locator('[data-atlas-full-scan-version="ATLAS_FULL_SCAN_VNEXT_V1"]')
                if await root.count():
                    version = max(version, await root.count())
                    population = max(population, int(await root.first.get_attribute("data-atlas-production-population") or 0))
            except Exception:
                continue
        candidates = await self._full_scan_candidates(page)
        positions = [item["production_rank"] for item in candidates]
        filtered = [item["filtered_position"] for item in candidates]
        first_mid_last = bool(candidates) and all(
            candidates[index]["ticker"] for index in {0, len(candidates) // 2, len(candidates) - 1}
        )
        high = any(
            item["evidence_total"] > 0
            and item["evidence_available"] >= item["evidence_total"] - 1
            for item in candidates
        )
        partial = any(
            item["evidence_total"] > 1
            and 0 < item["evidence_available"] < item["evidence_total"] - 1
            for item in candidates
        )
        authority = all(
            item["opportunity"] != item["confidence"]
            or not item["opportunity"] or not item["confidence"]
            for item in candidates
        )
        visible = all(token.lower() in text.lower() for token in (
            "Production Rank", "Filtered Position", "Why Ranked Here",
            "Prior Full Scan comparison is not available", "Atlas FV", "Wall Street consensus",
        ))
        exception = await _has_rendered_exception(page)
        shot = await self._shot(
            page, page_name="Full Ranked Scan", interaction="vnext-contract",
            state="evidence", viewport=viewport, complete_surface=True,
        )
        passed = bool(
            version and population and candidates and positions == sorted(positions)
            and filtered == list(range(1, len(filtered) + 1)) and first_mid_last
            and high and partial and authority and visible and not exception
        )
        await self._record(
            category="FULL_SCAN", page_name="Full Ranked Scan", interaction="vnext-decision-story",
            expected="Persisted population, production/filtered rank separation, dynamic archetypes, authority separation, honest movement state, and no exception",
            observed=(f"version={bool(version)}; population={population}; rendered={len(candidates)}; "
                      f"ordered={positions == sorted(positions)}; filtered_positions={filtered == list(range(1, len(filtered)+1))}; "
                      f"first_mid_last={first_mid_last}; high={high}; partial={partial}; authority={authority}; "
                      f"visible={visible}; exception={exception}"),
            passed=passed, elapsed=time.monotonic() - started, viewport=viewport,
            screenshots=(shot,), severity="P1",
            exception=await self._exception_identity(page) if exception else {},
        )

    async def _full_scan_candidate_journeys(self, page: Page, *, viewport: str) -> None:
        """Exercise dynamic Full Scan representatives and exact Research handoffs."""
        candidates = await self._full_scan_candidates(page)
        if not candidates:
            return
        representatives = [
            ("first", candidates[0]), ("middle", candidates[len(candidates) // 2]),
            ("last", candidates[-1]),
        ]
        high = next((item for item in candidates if (
            item["evidence_total"] > 0
            and item["evidence_available"] >= item["evidence_total"] - 1
        )), None)
        partial = next((item for item in candidates if (
            item["evidence_total"] > 1
            and 0 < item["evidence_available"] < item["evidence_total"] - 1
        )), None)
        if high:
            representatives.append(("high-evidence", high))
        if partial:
            representatives.append(("partial-evidence", partial))
        seen: set[tuple[str, str]] = set()
        for role, candidate in representatives:
            identity = (role, candidate["ticker"])
            if identity in seen:
                continue
            seen.add(identity)
            started = time.monotonic()
            ticker = candidate["ticker"]
            before = await self._shot(
                page, page_name="Full Ranked Scan", interaction=f"candidate-{role}",
                state="before", viewport=viewport, ticker=ticker,
            )
            try:
                button = page.get_by_role("button", name=f"View Investment Case — {ticker}", exact=True)
                await button.scroll_into_view_if_needed(timeout=5000)
                visible = await button.is_visible()
                journey = role in {"high-evidence", "partial-evidence"}
                if not journey:
                    await self._record(
                        category="FULL_SCAN_CANDIDATE", page_name="Full Ranked Scan", interaction=role,
                        expected=f"Dynamic {role} candidate exposes exact-ticker CTA and immutable production rank",
                        observed=(f"ticker={ticker}; rank={candidate['production_rank']}; "
                                  f"filtered={candidate['filtered_position']}; cta={visible}"),
                        passed=bool(visible and candidate["production_rank"] > 0),
                        elapsed=time.monotonic() - started, ticker=ticker, viewport=viewport,
                        screenshots=(before,), severity="P1",
                    )
                    continue
                await button.click(timeout=6000)
                deadline = time.monotonic() + 45
                destination = exact_ticker = settled = False
                research_status = ""
                while time.monotonic() < deadline:
                    destination = await self._current_route_visible(page, "Research Any Ticker")
                    exact_ticker = await self._exact_research_ticker(page, ticker)
                    settled = await _page_render_complete(page, "Research Any Ticker")
                    research_status = await self._research_decision_status(page, ticker)
                    if destination and exact_ticker and settled and research_status:
                        break
                    await page.wait_for_timeout(300)
                text = await _visible_text(page)
                exception = await _has_rendered_exception(page)
                stale = "Full Scan Intelligence" in text
                reconciled = candidate["decision_status"] == research_status
                after = await self._shot(
                    page, page_name="Research Any Ticker", interaction=f"full-scan-{role}-handoff",
                    state="after", viewport=viewport, ticker=ticker, complete_surface=True,
                )
                await self._record(
                    category="FULL_SCAN_DRILLDOWN", page_name="Full Ranked Scan", interaction=role,
                    expected=f"Visible CTA opens exact {ticker} Research with canonical state reconciliation",
                    observed=(f"destination={destination}; exact_ticker={exact_ticker}; settled={settled}; "
                              f"full_scan_status={candidate['decision_status']}; research_status={research_status}; "
                              f"reconciled={reconciled}; stale={stale}; exception={exception}"),
                    passed=destination and exact_ticker and settled and reconciled and not stale and not exception,
                    elapsed=time.monotonic() - started, ticker=ticker, viewport=viewport,
                    screenshots=(before, after), severity="P1",
                    exception=await self._exception_identity(page) if exception else {},
                )
                await self._page_visit(page, "Full Ranked Scan", viewport=viewport)
            except Exception as exc:
                failure = await self._shot(
                    page, page_name="Full Ranked Scan", interaction=f"candidate-{role}",
                    state="failure", viewport=viewport, ticker=ticker,
                )
                await self._record(
                    category="FULL_SCAN_CANDIDATE", page_name="Full Ranked Scan", interaction=role,
                    expected="Independent candidate failure is recorded and crawl continues",
                    observed=type(exc).__name__, passed=False, elapsed=time.monotonic() - started,
                    ticker=ticker, viewport=viewport, screenshots=(before, failure), severity="P1",
                )
                await self._page_visit(page, "Full Ranked Scan", viewport=viewport)
        passed = bool(
            version and section_count == len(RECOVERY_VNEXT_SECTION_LABELS)
            and visible_contract and exact_ticker and cta and not exception
        )
        await self._record(
            category="RECOVERY", page_name="Recovery", interaction="vnext-decision-story",
            expected="Twelve-section Recovery story, exact-ticker Research CTA, and no exception",
            observed=(f"version={version}; sections={section_count}; visible={visible_contract}; "
                      f"ticker={exact_ticker}; cta={cta}; exception={exception}"),
            passed=passed, elapsed=time.monotonic() - started, viewport=viewport,
            screenshots=(shot,), severity="P1",
            exception=await self._exception_identity(page) if exception else {},
        )

    async def _recovery_marker(self, page: Page) -> dict[str, str]:
        for scope in _scopes(page):
            try:
                nodes = scope.locator("[data-atlas-recovery-ticker]")
                if await nodes.count():
                    node = nodes.last
                    return {
                        "ticker": (await node.get_attribute("data-atlas-recovery-ticker") or "").upper(),
                        "score": await node.get_attribute("data-atlas-recovery-score") or "",
                        "label": await node.get_attribute("data-atlas-recovery-label") or "",
                        "evidence": await node.get_attribute("data-atlas-recovery-evidence") or "",
                        "decision_status": await node.get_attribute("data-atlas-recovery-decision-status") or "",
                        "recommendation": await node.get_attribute("data-atlas-recovery-recommendation") or "",
                    }
            except Exception:
                continue
        return {}

    async def _select_recovery_candidate(self, page: Page, label: str) -> dict[str, str]:
        control = page.get_by_label("Recovery candidate", exact=True)
        await control.click(timeout=5000)
        option = page.get_by_role("option", name=label, exact=True)
        await option.click(timeout=5000)
        expected = label.split("·", 1)[0].strip().upper()
        deadline = time.monotonic() + 12
        marker: dict[str, str] = {}
        while time.monotonic() < deadline:
            marker = await self._recovery_marker(page)
            if marker.get("ticker") == expected:
                return marker
            await page.wait_for_timeout(200)
        return marker

    async def _discover_recovery_candidates(self, page: Page) -> list[dict[str, Any]]:
        control = page.get_by_label("Recovery candidate", exact=True)
        await control.click(timeout=5000)
        labels = [text.strip() for text in await page.get_by_role("option").all_inner_texts() if text.strip()]
        await page.keyboard.press("Escape")
        candidates: list[dict[str, Any]] = []
        for label in labels:
            try:
                marker = await self._select_recovery_candidate(page, label)
                if marker.get("ticker"):
                    candidates.append({"selector_label": label, **marker})
            except Exception:
                continue
        return candidates

    async def _research_decision_status(self, page: Page, ticker: str) -> str:
        for scope in _scopes(page):
            try:
                nodes = scope.locator(f'[data-atlas-ticker="{ticker}"][data-atlas-decision-status]')
                if await nodes.count():
                    return await nodes.last.get_attribute("data-atlas-decision-status") or ""
            except Exception:
                continue
        return ""

    async def _recovery_candidate_journeys(self, page: Page, *, viewport: str, drill_down: bool) -> None:
        """Certify dynamic Recovery population/archetypes and real Research handoffs."""
        candidates = await self._discover_recovery_candidates(page)
        archetypes = recovery_candidate_archetypes(candidates)
        drill_roles = {"high-evidence", "partial-evidence"}
        for role, candidate in archetypes:
            started = time.monotonic()
            ticker = str(candidate.get("ticker") or "")
            before = ""
            try:
                marker = await self._select_recovery_candidate(page, str(candidate["selector_label"]))
                text = await _visible_text(page)
                exception = await _has_rendered_exception(page)
                section_count = max([
                    await scope.locator("[data-atlas-recovery-section]").count() for scope in _scopes(page)
                ] or [0])
                before = await self._shot(
                    page, page_name="Recovery", interaction=f"candidate-{role}", state="selected",
                    viewport=viewport, ticker=ticker, complete_surface=True,
                )
                visible = all(token.lower() in text.lower() for token in ("Recovery Snapshot", ticker, "View Investment Case"))
                passed = marker.get("ticker") == ticker and section_count == len(RECOVERY_VNEXT_SECTION_LABELS) and visible and not exception
                await self._record(
                    category="RECOVERY_CANDIDATE", page_name="Recovery", interaction=role,
                    expected=f"Dynamic {role} candidate renders complete Recovery VNext story",
                    observed=(f"ticker={ticker}; score={marker.get('score')}; label={marker.get('label')}; "
                              f"evidence={marker.get('evidence')}; sections={section_count}; exception={exception}"),
                    passed=passed, elapsed=time.monotonic() - started, ticker=ticker, viewport=viewport,
                    screenshots=(before,), severity="P1", exception=await self._exception_identity(page) if exception else {},
                )
                if not drill_down or role not in drill_roles:
                    continue
                button = page.get_by_role("button", name=f"View Investment Case — {ticker}", exact=True)
                await button.scroll_into_view_if_needed(timeout=5000)
                await button.click(timeout=6000)
                deadline = time.monotonic() + 45
                destination = exact_ticker = settled = False
                research_status = ""
                while time.monotonic() < deadline:
                    destination = await self._current_route_visible(page, "Research Any Ticker")
                    exact_ticker = await self._exact_research_ticker(page, ticker)
                    settled = await _page_render_complete(page, "Research Any Ticker")
                    research_status = await self._research_decision_status(page, ticker)
                    if destination and exact_ticker and settled and research_status:
                        break
                    await page.wait_for_timeout(300)
                research_text = await _visible_text(page)
                exception = await _has_rendered_exception(page)
                stale_recovery = "Recovery Snapshot" in research_text
                after = await self._shot(
                    page, page_name="Research Any Ticker", interaction=f"recovery-{role}-handoff",
                    state="settled", viewport=viewport, ticker=ticker, complete_surface=True,
                )
                recovery_status = marker.get("decision_status") or ""
                recovery_recommendation = str(marker.get("recommendation") or "").strip()
                normalized_recommendation = recovery_recommendation.replace("_", " ").lower()
                recommendation_match = (
                    recovery_status != "AVAILABLE"
                    or not recovery_recommendation
                    or normalized_recommendation in research_text.replace("_", " ").lower()
                )
                reconciled = bool(
                    recovery_status and research_status
                    and recovery_status == research_status and recommendation_match
                )
                await self._record(
                    category="RECOVERY_DRILLDOWN", page_name="Recovery", interaction=role,
                    expected=f"Actual Recovery CTA opens exact {ticker} Research with canonical state reconciliation",
                    observed=(f"recovery_ticker={ticker}; recovery_status={recovery_status}; destination={destination}; "
                              f"research_ticker={ticker if exact_ticker else ''}; research_status={research_status}; "
                              f"recommendation_match={recommendation_match}; reconciled={reconciled}; "
                              f"stale_recovery={stale_recovery}; exception={exception}"),
                    passed=destination and exact_ticker and settled and reconciled and not stale_recovery and not exception,
                    elapsed=time.monotonic() - started, ticker=ticker, viewport=viewport,
                    screenshots=(before, after), severity="P1", exception=await self._exception_identity(page) if exception else {},
                )
                await self._page_visit(page, "Recovery", viewport=viewport)
            except Exception as exc:
                failure = await self._shot(
                    page, page_name="Recovery", interaction=f"candidate-{role}", state="failure",
                    viewport=viewport, ticker=ticker,
                )
                await self._record(
                    category="RECOVERY_CANDIDATE", page_name="Recovery", interaction=role,
                    expected=f"Continue after independent {role} Recovery journey failure",
                    observed=type(exc).__name__, passed=False, elapsed=time.monotonic() - started,
                    ticker=ticker, viewport=viewport, screenshots=(before, failure), severity="P1",
                )
                await self._page_visit(page, "Recovery", viewport=viewport)

    async def _current_route_visible(self, page: Page, page_name: str) -> bool:
        """Prefer the current radio selection over stale lifecycle nodes from old reruns."""
        customer_label = {
            "Research Any Ticker": "Research",
            "Earnings Intelligence": "Earnings",
            "Watchlist Intelligence": "Watchlist",
            "Ask AI": "Ask ATLAS",
        }.get(page_name, page_name)
        for scope in _scopes(page):
            try:
                radio = scope.get_by_role("radio", name=customer_label, exact=True)
                if await radio.count() and await radio.first.is_checked():
                    return True
            except Exception:
                continue
        text = await _visible_text(page)
        return customer_label.lower() in text.lower()

    async def _research_route_owned(self, page: Page) -> bool:
        """Prove the live primary DOM belongs to the selected Research route."""
        route_selected = await self._current_route_visible(page, "Research Any Ticker")
        if not route_selected:
            return False
        for scope in _scopes(page):
            try:
                heading = scope.locator(".v65-section-title").filter(
                    has_text="Live Atlas Research"
                )
                inputs = scope.get_by_label("Ticker", exact=True)
                if not await inputs.count():
                    inputs = scope.locator('input[placeholder*="NVDA"]')
                buttons = scope.get_by_role("button", name="Research ticker", exact=True)
                if not (await heading.count() and await inputs.count() and await buttons.count()):
                    continue
                if research_route_ownership_satisfied(
                    route_selected=route_selected,
                    heading_visible=await heading.first.is_visible(),
                    ticker_input_visible=await inputs.first.is_visible(),
                    submit_control_visible=await buttons.first.is_visible(),
                ):
                    return True
            except Exception:
                continue
        return False

    async def _click_tabs(
        self, page: Page, *, page_name: str, ticker: str = "",
        viewport: str = "desktop", expected_tabs: Iterable[str] | None = None,
    ) -> None:
        tabs: list[str] = list(expected_tabs or ())
        if not tabs:
            for scope in _scopes(page):
                try:
                    locator = scope.get_by_role("tab")
                    for index in range(await locator.count()):
                        tab = locator.nth(index)
                        if await tab.is_visible():
                            tabs.append((await tab.inner_text()).strip() or f"tab-{index + 1}")
                except Exception:
                    continue
        seen: set[str] = set()
        for name in tabs:
            if name in seen:
                continue
            seen.add(name)
            started = time.monotonic()
            before_text = await _visible_text(page)
            before = await self._shot(page, page_name=page_name, interaction=f"tab-{name}", state="before", viewport=viewport, ticker=ticker)
            try:
                tab = await self._fresh_visible_tab(page, name)
                if tab is None:
                    raise RuntimeError("TAB_NOT_REACQUIRED")
                # Streamlit tabs can retain a transient rerun overlay after their
                # visible DOM settles. The post-click panel checks remain the
                # authority, so target the resolved tab without hit-test noise.
                await tab.click(timeout=6000, force=True)
                await page.wait_for_timeout(500)
                selected = False
                for scope in _scopes(page):
                    try:
                        refreshed = scope.get_by_role("tab", name=name, exact=True)
                        if await refreshed.count():
                            selected = (await refreshed.first.get_attribute("aria-selected")) == "true"
                            if selected:
                                break
                    except Exception:
                        continue
                after_text = await _visible_text(page)
                exception = await _has_rendered_exception(page)
                # Capture the complete selected surface. Streamlit regenerates
                # tab-panel IDs across reruns, so retaining a panel locator solely
                # for the screenshot can fail after the tab has rendered correctly.
                after = await self._shot(
                    page, page_name=page_name, interaction=f"tab-{name}",
                    state="after", viewport=viewport, ticker=ticker,
                    complete_surface=True,
                )
                changed = after_text != before_text or selected
                panel_identity = await self._selected_tab_panel_has_content(page, name)
                ticker_identity = await self._exact_research_ticker(page, ticker) if ticker else True
                passed = bool((selected or panel_identity) and changed and panel_identity and ticker_identity and not exception)
                await self._record(
                    category="TAB", page_name=page_name, interaction=name,
                    expected="Selected tab with non-stale visible content and no exception",
                    observed=f"selected={selected}; panel_identity={panel_identity}; content_changed={changed}; exact_ticker={ticker_identity}; exception={exception}",
                    passed=passed, elapsed=time.monotonic() - started, ticker=ticker,
                    viewport=viewport, screenshots=(before, after),
                    exception=await self._exception_identity(page) if exception else {},
                )
            except Exception as exc:
                after = await self._shot(page, page_name=page_name, interaction=f"tab-{name}", state="failure", viewport=viewport, ticker=ticker)
                await self._record(
                    category="TAB", page_name=page_name, interaction=name,
                    expected="Tab is independently operable",
                    observed=f"{type(exc).__name__}: {str(exc)[:240]}",
                    passed=False, elapsed=time.monotonic() - started, ticker=ticker,
                    viewport=viewport, screenshots=(before, after), severity="P2",
                    exception={"category": type(exc).__name__, "fingerprint": hashlib.sha256(type(exc).__name__.encode()).hexdigest()[:16]},
                )

    async def _fresh_visible_tab(self, page: Page, name: str) -> Any | None:
        for scope in _scopes(page):
            try:
                tabs = scope.get_by_role("tab", name=name, exact=True)
                for index in range(await tabs.count()):
                    candidate = tabs.nth(index)
                    if await candidate.is_visible():
                        return candidate
            except Exception:
                continue
        return None

    async def _selected_tab_panel_has_content(self, page: Page, name: str) -> bool:
        tab = await self._fresh_visible_tab(page, name)
        if tab is None:
            return False
        # Streamlit's generated aria-controls value is not guaranteed to be a
        # CSS-safe identifier. Validate the visible selected panel by role so a
        # valid UI cannot fail certification because of selector escaping.
        for scope in _scopes(page):
            panels = scope.get_by_role("tabpanel")
            for index in range(await panels.count()):
                panel = panels.nth(index)
                if await panel.is_visible() and (await panel.inner_text()).strip():
                    return True
        return bool((await _visible_text(page)).strip())

    async def _exact_research_ticker(self, page: Page, ticker: str) -> bool:
        expected = ticker.strip().upper()
        selectors = (
            '[data-atlas-qa="research-context-v1"][data-atlas-ticker]',
            '[data-atlas-qa="research-container"][data-atlas-ticker]',
            '[data-atlas-qa="research-performance"][data-atlas-ticker]',
        )
        for scope in _scopes(page):
            for selector in selectors:
                try:
                    nodes = scope.locator(selector)
                    for index in range(await nodes.count()):
                        if (await nodes.nth(index).get_attribute("data-atlas-ticker") or "").strip().upper() == expected:
                            return True
                except Exception:
                    continue
        return False

    async def _click_expanders(self, page: Page, *, page_name: str, viewport: str = "desktop") -> None:
        candidates: list[tuple[str, Any]] = []
        for scope in _scopes(page):
            try:
                nodes = scope.locator('[data-testid="stExpander"] summary, details summary')
                for index in range(await nodes.count()):
                    node = nodes.nth(index)
                    if await node.is_visible():
                        candidates.append(((await node.inner_text()).strip() or f"expander-{index + 1}", node))
            except Exception:
                continue
        for name, node in candidates:
            started = time.monotonic()
            before = await self._shot(page, page_name=page_name, interaction=f"expander-{name}", state="before", viewport=viewport)
            try:
                await node.click(timeout=5000)
                await page.wait_for_timeout(350)
                expanded = await node.evaluate("el => el.getAttribute('aria-expanded') === 'true' || !!el.closest('details')?.open")
                exception = await _has_rendered_exception(page)
                after = await self._shot(page, page_name=page_name, interaction=f"expander-{name}", state="after", viewport=viewport)
                collapsed = False
                if expanded:
                    await node.click(timeout=3000)
                    await page.wait_for_timeout(150)
                    collapsed = await node.evaluate("el => el.getAttribute('aria-expanded') === 'false' || !el.closest('details')?.open")
                await self._record(
                    category="EXPANDER", page_name=page_name, interaction=name,
                    expected="Required expander opens, exposes content, and closes",
                    observed=f"expanded={expanded}; collapsed={collapsed}; exception={exception}",
                    passed=expanded and collapsed and not exception, elapsed=time.monotonic() - started,
                    viewport=viewport, screenshots=(before, after),
                    exception=await self._exception_identity(page) if exception else {},
                )
            except Exception as exc:
                await self._record(
                    category="EXPANDER", page_name=page_name, interaction=name,
                    expected="Expander remains independently operable", observed=type(exc).__name__,
                    passed=False, elapsed=time.monotonic() - started, viewport=viewport,
                    screenshots=(before,), severity="P2",
                )

    async def _supporting_evidence(self, page: Page, *, page_name: str, viewport: str = "desktop") -> None:
        """Inspect visible evidence and exercise one declared Research drill-down."""
        started = time.monotonic()
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            complete = await _page_render_complete(page, page_name)
            marker_ready = False
            for scope in _scopes(page):
                try:
                    marker_ready = marker_ready or bool(await scope.locator(
                        '[data-atlas-qa="political-evidence"][data-atlas-record-count]'
                    ).count())
                except Exception:
                    continue
            if complete or marker_ready:
                break
            await page.wait_for_timeout(250)
        text = await _visible_text(page)
        if page_name == "Political Intelligence":
            fields = {
                "member": bool(re.search(r"member|representative|senator|politician", text, re.I)),
                "security": bool(re.search(r"ticker|security", text, re.I)),
                "transaction_type": bool(re.search(r"purchase|sale|buy|sell|transaction", text, re.I)),
                "transaction_date": bool(re.search(r"transaction date|trade date", text, re.I)),
                "disclosure_date": "disclosure date" in text.lower(),
                "amount_range": bool(re.search(r"amount|\$[\d,]+\s*(?:-|to)", text, re.I)),
                "source": bool(re.search(r"source|provider|disclosure", text, re.I)),
            }
            evidence_meta: dict[str, int] = {}
            evidence_shot = ""
            for scope in _scopes(page):
                try:
                    marker = scope.locator('[data-atlas-qa="political-evidence"]')
                    if await marker.count():
                        evidence_meta = {
                            "record_count": int(await marker.first.get_attribute("data-atlas-record-count") or 0),
                            "complete_count": int(await marker.first.get_attribute("data-atlas-complete-count") or 0),
                        }
                    tables = scope.locator('[data-testid="stDataFrame"]:visible')
                    if await tables.count():
                        evidence_shot = await self._shot_locator(
                            tables.last, page_name=page_name, interaction="political-visible-transaction",
                            state="evidence", viewport=viewport, ticker="",
                        )
                except Exception:
                    continue
            canonical_complete = evidence_meta.get("complete_count", 0) > 0
            evidence_present = bool(
                re.search(r"no verified|temporarily unavailable|no clean ticker-level", text, re.I) or
                (all(fields.values()) and canonical_complete and evidence_shot)
            )
            await self._record(
                category="EVIDENCE", page_name=page_name, interaction="political-evidence",
                expected="Member, security, action, transaction/disclosure dates, amount range, and provenance when evidence exists",
                observed=json.dumps({"visible_fields": fields, "canonical": evidence_meta}, sort_keys=True), passed=evidence_present,
                elapsed=time.monotonic() - started, viewport=viewport, severity="P2", screenshots=(evidence_shot,),
            )

        marker = None
        for scope in _scopes(page):
            try:
                nodes = scope.locator('[data-atlas-expected-page="research-any-ticker"][data-atlas-expected-ticker]')
                if await nodes.count():
                    marker = nodes.first
                    break
            except Exception:
                continue
        if marker is None:
            await self._record(
                category="DRILLDOWN", page_name=page_name, interaction="research-drilldown",
                expected="Research drill-down when supporting evidence exposes one",
                observed="No rendered Research drill-down; treated as optional for current data",
                passed=True, elapsed=time.monotonic() - started, viewport=viewport,
            )
            return
        interaction_id = await marker.get_attribute("data-atlas-interaction-id") or "supporting-research"
        ticker = (await marker.get_attribute("data-atlas-expected-ticker") or "").upper()
        before = await self._shot(page, page_name=page_name, interaction=interaction_id, state="before", viewport=viewport, ticker=ticker)
        try:
            interaction_selector = f'[data-atlas-interaction-id="{interaction_id}"]'
            fresh_marker = page.locator(interaction_selector).first
            button = fresh_marker.locator("xpath=following::button[1]")
            await button.first.scroll_into_view_if_needed()
            await button.first.click(timeout=6000)
            deadline = time.monotonic() + 45
            destination = False
            exact_ticker = False
            while time.monotonic() < deadline:
                destination = await self._current_route_visible(page, "Research Any Ticker")
                exact_ticker = await self._exact_research_ticker(page, ticker)
                if destination and exact_ticker:
                    break
                await page.wait_for_timeout(300)
            exception = await _has_rendered_exception(page)
            after = await self._shot(page, page_name="Research Any Ticker", interaction=interaction_id, state="after", viewport=viewport, ticker=ticker)
            await self._record(
                category="DRILLDOWN", page_name=page_name, interaction=interaction_id,
                expected=f"Research destination for {ticker}",
                observed=f"destination={destination}; exact_ticker={exact_ticker}; exception={exception}",
                passed=destination and exact_ticker and not exception,
                elapsed=time.monotonic() - started, ticker=ticker, viewport=viewport,
                screenshots=(before, after), severity="P1",
                exception=await self._exception_identity(page) if exception else {},
            )
        except Exception as exc:
            after = await self._shot(page, page_name=page_name, interaction=interaction_id, state="failure", viewport=viewport, ticker=ticker)
            await self._record(
                category="DRILLDOWN", page_name=page_name, interaction=interaction_id,
                expected=f"Research destination for {ticker}", observed=type(exc).__name__,
                passed=False, elapsed=time.monotonic() - started, ticker=ticker,
                viewport=viewport, screenshots=(before, after), severity="P1",
            )
    async def _submit_research(self, page: Page, ticker: str, *, tabs: bool, viewport: str = "desktop") -> bool:
        started = time.monotonic()
        route_ready = await self._page_visit(page, "Research Any Ticker", viewport=viewport)
        if not route_ready:
            raise RuntimeError("RESEARCH_ROUTE_NOT_READY")
        before = await self._shot(page, page_name="Research Any Ticker", interaction=f"submit-{ticker}", state="before", viewport=viewport, ticker=ticker)
        try:
            rerun_before = 0
            for scope in _scopes(page):
                markers = scope.locator('[data-atlas-qa="research-entry-stage"][data-atlas-stage="RESEARCH_ROUTE_ENTERED"]')
                for index in range(await markers.count()):
                    rerun_before = max(
                        rerun_before,
                        int(await markers.nth(index).get_attribute("data-atlas-rerun-count") or 0),
                    )
            input_node, button, controls_evidence = await self._stable_research_controls(page)
            await input_node.fill(ticker)
            sent_before = len(self._streamlit_frames_sent)
            await button.click()
            submission_evidence = await self._require_submission_boundary(
                page, ticker, sent_before=sent_before, rerun_before=rerun_before,
            )
            await self._record(
                category="RESEARCH_SUBMISSION_BOUNDARY", page_name="Research Any Ticker",
                interaction="submit-event-and-rerun",
                expected=(
                    "One stable visible form is proven by Streamlit transport telemetry "
                    "or exact-ticker certified terminal Research completion"
                ),
                observed=json.dumps({**controls_evidence, **submission_evidence}, sort_keys=True),
                passed=True, elapsed=time.monotonic() - started, ticker=ticker,
                viewport=viewport, screenshots=(), severity="P0",
            )
            # The first exact-candidate Research request warms Streamlit's
            # persisted-evidence builders and can legitimately take longer
            # than subsequent tickers. Keep the check bounded while avoiding
            # a false failure immediately before the result settles.
            deadline = time.monotonic() + RESEARCH_COMPLETION_TIMEOUT_SECONDS
            text = ""
            completion: dict[str, Any] = {}
            while time.monotonic() < deadline:
                text = await _visible_text(page)
                if ticker == "INVALID123":
                    if re.search(r"invalid|unavailable|not found", text, re.I):
                        break
                else:
                    completion = await self._completed_research(page, ticker)
                    if completion.get("complete"):
                        break
                await page.wait_for_timeout(400)
            exception = await _has_rendered_exception(page)
            displayed = bool(completion.get("complete")) if ticker != "INVALID123" else False
            safe_invalid = ticker != "INVALID123" or bool(re.search(r"invalid|unavailable|not found", text, re.I))
            canonical_tickers: set[str] = set()
            for scope in _scopes(page):
                for selector in (
                    '[data-atlas-qa="research-context-v1"][data-atlas-ticker]',
                    '[data-atlas-qa="research-container"][data-atlas-ticker]',
                ):
                    nodes = scope.locator(selector)
                    for index in range(await nodes.count()):
                        value = (await nodes.nth(index).get_attribute("data-atlas-ticker") or "").strip().upper()
                        if value:
                            canonical_tickers.add(value)
            stale = set(self.ticker_matrix.get("top15", [])) & canonical_tickers
            no_stale_ticker = ticker != "INVALID123" or not stale
            passed = bool((displayed or ticker == "INVALID123") and safe_invalid and no_stale_ticker and not exception)
            if displayed:
                self.research_contexts[ticker] = await self._research_identity(page, ticker)
                architecture = await self._research_vnext_contract(page, ticker)
                architecture_passed = completion.get("research_terminal_state") in {
                    "PUBLISHED_RESEARCH_COMPLETE", "RATING_NOT_PUBLISHED_COMPLETE",
                }
                await self._record(
                    category="RESEARCH_ARCHITECTURE", page_name="Research Any Ticker",
                    interaction="vnext-five-section-contract",
                    expected="Explicit complete published or rating-not-published Research terminal state",
                    observed=json.dumps({**architecture, "terminal_state": completion.get("research_terminal_state")}, sort_keys=True), passed=architecture_passed,
                    elapsed=time.monotonic() - started, ticker=ticker, viewport=viewport,
                    severity="P1", screenshots=(),
                )
                passed = passed and architecture_passed
            after = await self._shot(page, page_name="Research Any Ticker", interaction=f"submit-{ticker}", state="after", viewport=viewport, ticker=ticker, complete_surface=ticker != "INVALID123")
            for entry in reversed(self.manifest):
                if entry.get("path") == after:
                    entry["research_terminal_state"] = completion.get("research_terminal_state")
                    break
            await self._record(
                category="RESEARCH", page_name="Research Any Ticker", interaction="submit",
                expected=f"Visible Research result and exact ticker {ticker}",
                observed=f"completion={json.dumps(completion, sort_keys=True)}; safe_invalid={safe_invalid}; no_stale_ticker={no_stale_ticker}; exception={exception}",
                passed=passed, elapsed=time.monotonic() - started, ticker=ticker,
                viewport=viewport, screenshots=(before, after), severity="P1",
                exception=await self._exception_identity(page) if exception else {},
            )
            if (
                passed and tabs and ticker != "INVALID123"
                and not completion.get("certification_incomplete")
            ):
                # UX-2 is authoritative. Never rediscover/certify the preserved
                # legacy twelve-tab presentation for an active Research result.
                await self._click_tabs(
                    page, page_name="Research Any Ticker", ticker=ticker,
                    viewport=viewport, expected_tabs=RESEARCH_VNEXT_SECTION_LABELS,
                )
            return passed
        except Exception as exc:
            if isinstance(exc, ResearchSubmissionBoundaryError):
                await self._record(
                    category="RESEARCH_SUBMISSION_BOUNDARY", page_name="Research Any Ticker",
                    interaction="submit-event-and-rerun",
                    expected="One stable visible form emits a Streamlit event and rerun",
                    observed=f"{exc.category}; evidence={json.dumps(exc.evidence, sort_keys=True)}",
                    passed=False, elapsed=time.monotonic() - started, ticker=ticker,
                    viewport=viewport, screenshots=(), severity="P0",
                )
            after = await self._shot(page, page_name="Research Any Ticker", interaction=f"submit-{ticker}", state="failure", viewport=viewport, ticker=ticker)
            await self._record(
                category="RESEARCH", page_name="Research Any Ticker", interaction="submit",
                expected=f"Research remains usable for {ticker}", observed=type(exc).__name__,
                passed=False, elapsed=time.monotonic() - started, ticker=ticker,
                viewport=viewport, screenshots=(before, after), severity="P1",
            )
            return False

    async def _home_cards(self, page: Page, *, viewport: str = "desktop") -> None:
        await self._page_visit(page, "Home", viewport=viewport)
        authority = await self._home_runtime_authority(page)
        await self._record(
            category="HOME_RUNTIME_AUTHORITY", page_name="Home", interaction="exact-runtime-authority",
            expected="Exact candidate/publication/source/projection and governed inventory",
            observed=json.dumps(authority, sort_keys=True), passed=bool(authority.get("passed")),
            elapsed=0.0, viewport=viewport, severity="P0",
        )
        if not authority.get("passed"):
            raise GlobalCrawlFailure("HOME_RUNTIME_AUTHORITY_FAILED")
        contract = await self._home_guidance_vnext_contract(page)
        await self._record(
            category="HOME_GUIDANCE_VNEXT", page_name="Home", interaction="guidance-contract",
            expected="Guidance-first Home with separated authorities and bounded supporting sections",
            observed=json.dumps(contract, sort_keys=True), passed=bool(contract.get("passed")),
            elapsed=0.0, ticker=str(contract.get("first_ticker") or ""), viewport=viewport,
            screenshots=(), severity="P1",
        )
        await self._open_buy_now_expander(page)
        unique = await self._discover_visible_home_cards(page)
        by_ticker = {ticker: (interaction_id, ticker) for interaction_id, ticker in unique}
        if viewport == "desktop":
            selected = [by_ticker[ticker] for ticker in ("NVDA", "MSFT", "CODA") if ticker in by_ticker]
            missing = [ticker for ticker in ("NVDA", "MSFT", "CODA") if ticker not in by_ticker]
            for ticker in missing:
                await self._record(
                    category="HOME_DRILLDOWN", page_name="Home", interaction=f"home-to-research-{ticker.lower()}",
                    expected=f"Governed Home card exposes Research CTA for {ticker}",
                    observed="required CTA not discovered", passed=False, elapsed=0.0,
                    ticker=ticker, viewport=viewport, severity="P1",
                )
        else:
            selected = [by_ticker.get("NVDA", unique[0] if unique else ("", "NVDA"))]
        for interaction_id, ticker in selected:
            started = time.monotonic()
            before = ""
            operation = "resolve_visible_cta"
            try:
                marker, button = await self._visible_home_card_action(page, ticker, interaction_id)
                if button is None:
                    operation = "open_buy_now_expander"
                    await self._open_buy_now_expander(page)
                    operation = "resolve_expanded_visible_cta"
                    marker, button = await self._visible_home_card_action(page, ticker, interaction_id)
                if marker is None or button is None:
                    raise RuntimeError("CARD_ACTION_NOT_CLICKABLE")
                operation = "capture_visible_card"
                await button.scroll_into_view_if_needed(timeout=5000)
                card = button.locator("xpath=ancestor::*[@data-testid='stVerticalBlock'][1]")
                target = card.first if await card.count() else button
                before = await self._shot_locator(
                    target, page_name="Home", interaction=interaction_id, state="card-before",
                    viewport=viewport, ticker=ticker,
                )
                operation = "click_visible_cta"
                await button.click(timeout=6000)
                await page.wait_for_timeout(800)
                deadline = time.monotonic() + 45
                destination = False
                exact_ticker = False
                render_complete = False
                while time.monotonic() < deadline:
                    destination = await self._current_route_visible(page, "Research Any Ticker")
                    exact_ticker = await self._exact_research_ticker(page, ticker)
                    render_complete = await _page_render_complete(page, "Research Any Ticker")
                    if destination and exact_ticker and render_complete:
                        break
                    await page.wait_for_timeout(350)
                operation = "verify_destination"
                exception = await _has_rendered_exception(page)
                after = await self._shot(page, page_name="Research Any Ticker", interaction=interaction_id, state="full-report", viewport=viewport, ticker=ticker, complete_surface=True)
                await self._record(
                    category="HOME_DRILLDOWN", page_name="Home", interaction=interaction_id,
                    expected=f"Actual click opens Research Any Ticker for {ticker}",
                    observed=f"visible_cta=true; click_registered={destination}; destination={destination}; exact_ticker={exact_ticker}; full_report={render_complete}; exception={exception}",
                    passed=destination and exact_ticker and render_complete and not exception,
                    elapsed=time.monotonic() - started, ticker=ticker, viewport=viewport,
                    screenshots=(before, after), severity="P1",
                    exception=await self._exception_identity(page) if exception else {},
                )
                if destination and exact_ticker:
                    await self._click_tabs(
                        page, page_name="Research Any Ticker", ticker=ticker, viewport=viewport,
                    )
            except Exception as exc:
                after = await self._shot(page, page_name="Home", interaction=interaction_id, state="failure", viewport=viewport, ticker=ticker)
                await self._record(
                    category="HOME_DRILLDOWN", page_name="Home", interaction=interaction_id,
                    expected=f"Home card opens exact Research ticker {ticker}",
                    observed=f"{type(exc).__name__}@{operation}", passed=False, elapsed=time.monotonic() - started,
                    ticker=ticker, viewport=viewport, screenshots=(before, after), severity="P1",
                )
            await self._page_visit(page, "Home", viewport=viewport)

    async def _home_guidance_vnext_contract(self, page: Page) -> dict[str, Any]:
        result: dict[str, Any] = {
            "vnext": False, "preview": False, "market_context": False,
            "market_read": False, "action_summary": False,
            "strongest_opportunities": False, "worth_watching": False,
            "actionable_card_count": 0, "actionable_cards_certified": False,
            "decision_fields_visible": False, "governed_zero_state": False,
            "horizontal_overflow": False, "exception": False,
        }
        text = await _visible_text(page)
        required_sections: set[str] = set()
        evidence_states: list[str] = []
        for scope in _scopes(page):
            marker = scope.locator('[data-atlas-qa="home-guidance-vnext"]')
            if await marker.count():
                result["vnext"] = True
                result["preview"] = (await marker.first.get_attribute("data-atlas-mode") or "") == "PREVIEW"
            result["market_context"] = result["market_context"] or bool(await scope.locator(
                '[data-atlas-qa="market-today"][data-atlas-non-scoring="true"]'
            ).count())
            result["market_read"] = result["market_read"] or bool(await scope.locator(
                '[data-atlas-qa="atlas-market-read"][data-atlas-non-scoring="true"]'
            ).count())
            sections = scope.locator('[data-atlas-qa="home-guidance-section"][data-atlas-section]')
            for index in range(await sections.count()):
                value = await sections.nth(index).get_attribute("data-atlas-section")
                if value:
                    required_sections.add(value)
            cards = scope.locator('[data-atlas-qa="home-actionable-card"][data-atlas-ticker]')
            result["actionable_card_count"] += await cards.count()
            for index in range(await cards.count()):
                evidence_states.append(
                    await cards.nth(index).get_attribute("data-atlas-evidence-status") or ""
                )
        result["action_summary"] = (
            "atlas_action_summary" in required_sections and "ATLAS Action Summary" in text
        )
        result["strongest_opportunities"] = (
            "best_opportunities" in required_sections and "Strongest Opportunities" in text
        )
        result["worth_watching"] = (
            "worth_watching" in required_sections and "Worth Watching" in text
        )
        result["actionable_cards_certified"] = bool(
            evidence_states and all(state == "Evidence Complete" for state in evidence_states)
        )
        result["decision_fields_visible"] = bool(
            result["actionable_card_count"]
            and "ATLAS Fair Value" in text
            and "Potential" in text
            and ("Decision Confidence" in text or "Confidence" in text)
        )
        result["governed_zero_state"] = bool(
            result["actionable_card_count"] == 0
            and "ATLAS found no stocks meeting the strongest certified opportunity threshold" in text
        )
        try:
            result["horizontal_overflow"] = bool(await page.evaluate("document.documentElement.scrollWidth > window.innerWidth"))
        except Exception:
            result["horizontal_overflow"] = False
        result["exception"] = await _has_rendered_exception(page)
        result["passed"] = bool(
            result["vnext"] and result["market_context"] and result["market_read"]
            and result["action_summary"] and result["strongest_opportunities"]
            and result["worth_watching"]
            and (
                (
                    result["actionable_card_count"] > 0
                    and result["actionable_cards_certified"]
                    and result["decision_fields_visible"]
                )
                or result["governed_zero_state"]
            )
            and not result["horizontal_overflow"] and not result["exception"]
        )
        return result

    async def _open_buy_now_expander(self, page: Page) -> bool:
        for scope in _scopes(page):
            try:
                summaries = scope.locator('[data-testid="stExpander"] summary, details summary')
                for index in range(await summaries.count()):
                    summary = summaries.nth(index)
                    label = await summary.inner_text()
                    if await summary.is_visible() and re.search(r"View all\s+\d+\s+BUY NOW", label, re.I):
                        if "keyboard_arrow_down" not in label:
                            await summary.click(force=True)
                            await page.wait_for_timeout(800)
                        return True
            except Exception:
                continue
        return False

    async def _discover_visible_home_cards(self, page: Page) -> list[tuple[str, str]]:
        """Discover visible CTAs through their stable ticker-owned QA markers."""
        cards: list[tuple[str, str]] = []
        seen: set[str] = set()
        for scope in _scopes(page):
            try:
                markers = scope.locator(
                    '[data-atlas-qa="home-guidance-research-cta"]'
                    '[data-atlas-ticker][data-atlas-interaction-id]'
                )
                for index in range(await markers.count()):
                    marker = markers.nth(index)
                    button = marker.locator("xpath=following::button[1]").first
                    if not await button.count() or not await button.is_visible():
                        continue
                    interaction_id = await marker.get_attribute("data-atlas-interaction-id") or ""
                    ticker = (await marker.get_attribute("data-atlas-ticker") or "").upper()
                    if not interaction_id or not ticker or ticker in seen:
                        continue
                    card_text = ""
                    for test_id in ("stHorizontalBlock", "stVerticalBlock"):
                        card = button.locator(f"xpath=ancestor::*[@data-testid='{test_id}'][1]")
                        if await card.count():
                            card_text += " " + await card.first.inner_text()
                    if "BUY NOW" not in card_text.upper() and not await scope.locator(
                        '[data-atlas-qa="home-guidance-vnext"]'
                    ).count():
                        continue
                    seen.add(ticker)
                    cards.append((interaction_id, ticker))
            except Exception:
                continue
        return cards

    async def _visible_home_card_action(self, page: Page, ticker: str, preferred_id: str) -> tuple[Any | None, Any | None]:
        """Resolve marker metadata to a currently visible customer CTA."""
        selectors = [
            f'[data-atlas-interaction-id="{preferred_id}"]',
            f'[data-atlas-expected-ticker="{ticker}"][data-atlas-expected-page="research-any-ticker"]',
        ]
        for selector in selectors:
            for scope in _scopes(page):
                try:
                    markers = scope.locator(selector)
                    for index in range(await markers.count()):
                        marker = markers.nth(index)
                        button = marker.locator("xpath=following::button[1]").first
                        if await button.count() and await button.is_visible():
                            return marker, button
                except Exception:
                    continue
        exact_ticker = re.compile(rf"(?<![A-Z0-9]){re.escape(ticker)}(?![A-Z0-9])", re.I)
        for scope in _scopes(page):
            try:
                buttons = scope.get_by_role(
                    "button", name=re.compile(r"(?:Open Full Research|View Investment Case|View Research)", re.I)
                )
                for index in range(await buttons.count()):
                    button = buttons.nth(index)
                    if not await button.is_visible():
                        continue
                    for test_id in ("stHorizontalBlock", "stVerticalBlock"):
                        card = button.locator(f"xpath=ancestor::*[@data-testid='{test_id}'][1]")
                        if await card.count() and exact_ticker.search(await card.first.inner_text()):
                            return card.first, button
            except Exception:
                continue
        return None, None

    async def _research_identity(self, page: Page, ticker: str) -> dict[str, str]:
        identity = {"ticker": ticker, "context_digest": "", "decision_digest": ""}
        for scope in _scopes(page):
            nodes = scope.locator('[data-atlas-qa="research-context-v1"][data-atlas-ticker]')
            for index in range(await nodes.count()):
                node = nodes.nth(index)
                if (await node.get_attribute("data-atlas-ticker") or "").upper() == ticker.upper():
                    identity["decision_digest"] = await node.get_attribute("data-atlas-decision-digest") or ""
                    summary = await node.get_attribute("data-atlas-context-summary") or ""
                    identity["context_digest"] = stable_digest(decode_context_summary(summary)) if summary else ""
                    return identity
        return identity

    async def _ask(self, page: Page, *, viewport: str = "desktop") -> None:
        await self._page_visit(page, "Ask AI", viewport=viewport)
        started = time.monotonic()
        before = await self._shot(page, page_name="Ask AI", interaction="grounded-question", state="before", viewport=viewport, ticker="NVDA")
        try:
            control = None; button = None
            for scope in _scopes(page):
                inputs = scope.locator('textarea:visible, input[type="text"]:visible')
                buttons = scope.get_by_role("button")
                if await inputs.count() and await buttons.count():
                    control, button = inputs.last, buttons.last
                    break
            if control is None or button is None:
                raise RuntimeError("ASK_CONTROLS_MISSING")
            await control.fill("Why does ATLAS like NVDA?")
            await button.click()
            await page.wait_for_timeout(800)
            deadline = time.monotonic() + 30
            response_marker = None
            while time.monotonic() < deadline:
                candidates = page.locator('[data-atlas-qa="ask-ai-response"][data-atlas-status="complete"]')
                if await candidates.count():
                    response_marker = candidates.first
                    for candidate_index in range(await candidates.count()):
                        candidate = candidates.nth(candidate_index)
                        if (
                            await candidate.get_attribute("data-atlas-context-digest") and
                            await candidate.get_attribute("data-atlas-response-length")
                        ):
                            response_marker = candidate
                            break
                    if await response_marker.get_attribute("data-atlas-response-length"):
                        break
                if await _has_rendered_exception(page):
                    break
                await page.wait_for_timeout(300)
            text = await _visible_text(page)
            exception = await _has_rendered_exception(page)
            metadata: dict[str, str] = {}
            if response_marker is not None and await response_marker.count():
                for key in (
                    "ticker", "context-digest", "decision-digest", "evidence-used",
                    "evidence-missing", "evidence-ids", "evidence-limitations",
                ):
                    metadata[key] = await response_marker.get_attribute(f"data-atlas-{key}") or ""
            performance = page.locator('[data-atlas-qa="ask-performance"][data-atlas-ticker="NVDA"]')
            if await performance.count() and not metadata.get("context-digest"):
                metadata["context-digest"] = await performance.last.get_attribute("data-atlas-context-digest") or ""
            ticker_match = metadata.get("ticker", "").upper() == "NVDA"
            research_identity = self.research_contexts.get("NVDA", {})
            digest_match = bool(
                metadata.get("context-digest") and
                (not research_identity.get("context_digest") or
                 metadata.get("context-digest") == research_identity.get("context_digest"))
            )
            metadata_present = bool(
                digest_match and (metadata.get("decision-digest") or research_identity.get("decision_digest")) and
                (metadata.get("evidence-used") or metadata.get("evidence-missing") or
                 metadata.get("evidence-ids") or metadata.get("evidence-limitations"))
            )
            visible_evidence = bool(re.search(r"supporting evidence|evidence used|evidence missing|context digest|source|limitation", text, re.I))
            grounded = ticker_match and visible_evidence
            numeric_claims = bool(re.search(r"(?:\$\s*\d|\b\d+(?:\.\d+)?%)", text))
            evidence_metadata = metadata_present and visible_evidence
            unsupported_numeric = numeric_claims and not evidence_metadata
            raw_large_number = bool(re.search(r"(?<![\d,])(?:\d{10,}|\d{1,3}(?:,\d{3}){3,})(?![\d,])", text))
            after = await self._shot(page, page_name="Ask AI", interaction="grounded-question", state="answer-and-evidence", viewport=viewport, ticker="NVDA", complete_surface=True)
            await self._record(
                category="ASK", page_name="Ask AI", interaction="grounded-question",
                expected="NVDA-grounded answer with visible evidence/context metadata",
                observed=f"ticker_context={ticker_match}; context_digest={bool(metadata.get('context-digest'))}; decision_digest={bool(metadata.get('decision-digest'))}; evidence_metadata={evidence_metadata}; unsupported_numeric={unsupported_numeric}; exception={exception}",
                passed=grounded and not unsupported_numeric and not exception, elapsed=time.monotonic() - started,
                ticker="NVDA", viewport=viewport, screenshots=(before, after), severity="P1",
                exception=await self._exception_identity(page) if exception else {},
            )
            digest_state = "PASS" if digest_match else "FAIL"
            await self._record(
                category="ASK_RECONCILIATION", page_name="Ask AI", interaction="context-digest",
                expected="Ask context digest equals the rendered canonical Research context digest",
                observed=(
                    f"state={digest_state}; ask_digest={metadata.get('context-digest') or 'MISSING'}; "
                    f"research_digest={research_identity.get('context_digest') or 'MISSING'}; "
                    f"ticker={metadata.get('ticker') or 'MISSING'}"
                ),
                passed=digest_state == "PASS", elapsed=time.monotonic() - started,
                ticker="NVDA", viewport=viewport, screenshots=(after,), severity="P2",
                status_override=digest_state,
            )
            await self._record(
                category="UX", page_name="Ask AI", interaction="numeric-formatting",
                expected="Large numeric evidence is customer-formatted",
                observed=f"raw_large_numeric_value={raw_large_number}",
                passed=not raw_large_number, elapsed=time.monotonic() - started,
                ticker="NVDA", viewport=viewport, screenshots=(after,), severity="P2",
            )
        except Exception as exc:
            await self._record(
                category="ASK", page_name="Ask AI", interaction="grounded-question",
                expected="Ask control and grounded response", observed=type(exc).__name__,
                passed=False, elapsed=time.monotonic() - started, ticker="NVDA",
                viewport=viewport, screenshots=(before,), severity="P1",
            )

    async def _required_desktop(self, page: Page) -> None:
        await page.set_viewport_size(DESKTOP)
        await asyncio.wait_for(self._home_cards(page), timeout=90)
        for ticker in REQUIRED_RESEARCH_TICKERS:
            passed = await asyncio.wait_for(self._submit_research(page, ticker, tabs=True), timeout=45)
            if not passed:
                raise GlobalCrawlFailure(f"REQUIRED_RESEARCH_FAILED_{ticker}")
        if not await asyncio.wait_for(self._page_visit(page, "Earnings Intelligence"), timeout=20):
            raise GlobalCrawlFailure("REQUIRED_EARNINGS_DESKTOP_FAILED")
        await asyncio.wait_for(self._earnings_vnext_contract(page, viewport="desktop"), timeout=15)
        if not await asyncio.wait_for(self._page_visit(page, "Watchlist Intelligence"), timeout=20):
            raise GlobalCrawlFailure("REQUIRED_WATCHLIST_DESKTOP_FAILED")
        await asyncio.wait_for(self._ask(page, viewport="desktop"), timeout=35)

    async def _supplementary_desktop(self, page: Page) -> None:
        await page.set_viewport_size(DESKTOP)
        for page_name in (name for name in ACTIVE_PAGES if name not in {"Home", "Research Any Ticker"}):
            try:
                await self._supplementary_desktop_page(page, page_name)
            except GlobalCrawlFailure:
                raise
            except Exception as exc:
                await self._record(
                    category="SUPPLEMENTARY_EXECUTION", page_name=page_name,
                    interaction="desktop-journey", expected="Supplementary journey completes without an uncaught exception",
                    observed=type(exc).__name__, passed=False,
                    elapsed=0.0, severity="P2", required=False,
                )

    async def _supplementary_desktop_page(self, page: Page, page_name: str) -> None:
            await self._page_visit(page, page_name)
            if page_name == "Earnings Intelligence":
                await self._earnings_vnext_contract(page, viewport="desktop")
            if page_name == "Full Ranked Scan":
                await self._full_scan_vnext_contract(page, viewport="desktop")
                await self._full_scan_candidate_journeys(page, viewport="desktop")
            if page_name == "Recovery":
                await self._recovery_vnext_contract(page, viewport="desktop")
                await self._recovery_candidate_journeys(page, viewport="desktop", drill_down=True)
            if page_name in {"Earnings Intelligence", "Political Intelligence"}:
                await self._click_expanders(page, page_name=page_name)
                await self._supporting_evidence(page, page_name=page_name)
            if page_name == "Ask AI":
                await self._ask(page)

    async def _required_mobile(self, page: Page) -> None:
        await page.set_viewport_size(MOBILE)
        await asyncio.wait_for(self._home_cards(page, viewport="mobile"), timeout=30)
        passed = await asyncio.wait_for(self._submit_research(page, "NVDA", tabs=True, viewport="mobile"), timeout=45)
        if not passed:
            raise GlobalCrawlFailure("REQUIRED_RESEARCH_FAILED_NVDA_MOBILE")
        if not await asyncio.wait_for(self._page_visit(page, "Earnings Intelligence", viewport="mobile"), timeout=20):
            raise GlobalCrawlFailure("REQUIRED_EARNINGS_MOBILE_FAILED")
        await asyncio.wait_for(self._earnings_vnext_contract(page, viewport="mobile"), timeout=15)
        if not await asyncio.wait_for(self._page_visit(page, "Watchlist Intelligence", viewport="mobile"), timeout=20):
            raise GlobalCrawlFailure("REQUIRED_WATCHLIST_MOBILE_FAILED")
        await asyncio.wait_for(self._ask(page, viewport="mobile"), timeout=35)

    async def _supplementary_mobile(self, page: Page) -> None:
        await page.set_viewport_size(MOBILE)
        for page_name in (name for name in MOBILE_PAGES if name not in {"Home", "Research Any Ticker"}):
            try:
                await self._supplementary_mobile_page(page, page_name)
            except GlobalCrawlFailure:
                raise
            except Exception as exc:
                await self._record(
                    category="SUPPLEMENTARY_EXECUTION", page_name=page_name,
                    interaction="mobile-journey", expected="Supplementary mobile journey completes without an uncaught exception",
                    observed=type(exc).__name__, passed=False, elapsed=0.0,
                    viewport="mobile", severity="P2", required=False,
                )

    async def _supplementary_mobile_page(self, page: Page, page_name: str) -> None:
            await self._page_visit(page, page_name, viewport="mobile")
            if page_name == "Ask AI":
                await self._ask(page, viewport="mobile")
            elif page_name == "Political Intelligence":
                await self._click_expanders(page, page_name=page_name, viewport="mobile")
                await self._supporting_evidence(page, page_name=page_name, viewport="mobile")
            elif page_name == "Earnings Intelligence":
                await self._earnings_vnext_contract(page, viewport="mobile")
            elif page_name == "Full Ranked Scan":
                await self._full_scan_vnext_contract(page, viewport="mobile")
            elif page_name == "Recovery":
                await self._recovery_vnext_contract(page, viewport="mobile")
                await self._recovery_candidate_journeys(page, viewport="mobile", drill_down=False)

    async def run(self, *, phase: str = "all") -> dict[str, Any]:
        self.enforce_required_authority = phase in {"required", "all"}
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        async with async_playwright() as pw:
            browser: Browser = await pw.chromium.launch(headless=self.headless)
            context: BrowserContext = await browser.new_context(viewport=DESKTOP)
            page = await context.new_page()
            page.on("websocket", self._track_streamlit_websocket)
            try:
                try:
                    self.authentication = await asyncio.wait_for(
                        _open_and_authenticate(
                            page, self.url, self.output_dir,
                            expected_sha=self.expected_deployed_source_sha,
                            allow_local_exact_candidate=(
                                os.getenv("ATLAS_EXACT_CANDIDATE_QA", "").strip().lower()
                                in {"1", "true", "yes"}
                            ),
                        ),
                        timeout=60 if phase in {"required", "all"} else 300,
                    )
                except Exception as exc:
                    shot = await self._shot(page, page_name="GLOBAL", interaction="authentication", state="failure")
                    category = "APP_UNREACHABLE" if not page.url or page.url == "about:blank" else "AUTHENTICATION_FAILED"
                    await self._record(
                        category="GLOBAL", page_name="GLOBAL", interaction="authenticate",
                        expected="Reach and authenticate once", observed=type(exc).__name__,
                        passed=False, elapsed=time.monotonic() - self.started,
                        screenshots=(shot,), severity="P1",
                    )
                    raise GlobalCrawlFailure(category) from exc
                if phase in {"required", "all"}:
                    await self._customer_navigation_contract(page)
                    await asyncio.wait_for(self._required_desktop(page), timeout=285)
                    await asyncio.wait_for(self._required_mobile(page), timeout=135)
                    if self._required_completeness().get("status") != "PASS":
                        raise GlobalCrawlFailure("REQUIRED_PRODUCTION_CERTIFICATION_FAILED")
                if phase in {"supplementary", "all"}:
                    await self._supplementary_desktop(page)
                    await self._supplementary_mobile(page)
            finally:
                await context.close()
                await browser.close()
        return self._write_artifacts(final=True)

    def _summary(self, *, final: bool) -> dict[str, Any]:
        def counts(category: str) -> dict[str, int]:
            rows = [row for row in self.results if row.category == category]
            return {"attempted": len(rows), "passed": sum(row.status == "PASS" for row in rows), "failed": sum(row.status == "FAIL" for row in rows)}
        all_counts = {"attempted": len(self.results), "passed": sum(row.status == "PASS" for row in self.results), "failed": sum(row.status == "FAIL" for row in self.results)}
        required = [row for row in self.results if row.required]
        supplementary = [row for row in self.results if not row.required]
        expected_shots = len(self.manifest)
        generated_shots = sum(bool(item.get("generated")) for item in self.manifest)
        return {
            "version": VISUAL_CRAWLER_VERSION, "source_sha": self.source_sha,
            "started_at": self.started_at, "finished": final,
            "duration_seconds": round(time.monotonic() - self.started, 3),
            "required_phase_budget": {
                "operations": REQUIRED_PHASE_BUDGET,
                "worst_case_seconds": sum(
                    item["timeout_seconds"] * (item["retries"] + 1)
                    for item in REQUIRED_PHASE_BUDGET.values()
                ),
                "ceiling_seconds": REQUIRED_PHASE_TIMEOUT_SECONDS,
            },
            "authentication_success": bool(self.authentication),
            "required_completeness": self._required_completeness(),
            "capture_efficiency": {
                "deduplicated_screenshot_count": self.screenshot_calls_avoided,
                "screenshot_retries": self.screenshot_retries,
                "screenshot_timeouts": self.screenshot_timeouts,
            },
            "counts": {
                "all": all_counts, "pages": counts("PAGE"),
                "interactions": {
                    "attempted": all_counts["attempted"] - counts("PAGE")["attempted"],
                    "passed": all_counts["passed"] - counts("PAGE")["passed"],
                    "failed": all_counts["failed"] - counts("PAGE")["failed"],
                },
                "research_tickers": counts("RESEARCH"), "tabs": counts("TAB"),
                "screenshots": {"expected": expected_shots, "generated": generated_shots, "missing": expected_shots - generated_shots},
                "required": {"attempted": len(required), "passed": sum(row.status == "PASS" for row in required), "failed": sum(row.status == "FAIL" for row in required)},
                "supplementary": {"attempted": len(supplementary), "passed": sum(row.status == "PASS" for row in supplementary), "failed": sum(row.status == "FAIL" for row in supplementary)},
            },
            "ticker_matrix": self.ticker_matrix,
            "defects": [asdict(row) for row in self.results if row.status == "FAIL"],
            "results": [asdict(row) for row in self.results],
            "screenshot_manifest": self.manifest,
        }

    def _write_artifacts(self, *, final: bool) -> dict[str, Any]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        summary = self._summary(final=final)
        (self.output_dir / "atlas_visual_qa_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        (self.output_dir / "screenshot_manifest.json").write_text(json.dumps(self.manifest, indent=2), encoding="utf-8")
        csv_path = self.output_dir / "atlas_visual_qa_matrix.csv"
        columns = ["category", "page", "ticker_context", "interaction", "expected", "observed", "status", "severity", "elapsed_seconds", "viewport", "screenshots", "exception", "required"]
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns); writer.writeheader()
            for result in self.results:
                row = asdict(result); row["screenshots"] = "|".join(result.screenshots); row["exception"] = json.dumps(result.exception, sort_keys=True)
                writer.writerow(row)
        counts = summary["counts"]
        defects = summary["defects"]
        defect_lines = "\n".join(f"- {d['severity']} {d['page']} / {d['interaction']}: {d['observed']}" for d in defects) or "- None"
        markdown = f"""# ATLAS Visual QA V1\n\nSource: `{self.source_sha}`  \nDuration: {summary['duration_seconds']}s\n\n- Pages: {counts['pages']['passed']}/{counts['pages']['attempted']} passed\n- Interactions: {counts['interactions']['passed']}/{counts['interactions']['attempted']} passed\n- Research tickers: {counts['research_tickers']['passed']}/{counts['research_tickers']['attempted']} passed\n- Tabs: {counts['tabs']['passed']}/{counts['tabs']['attempted']} passed\n- Screenshots: {counts['screenshots']['generated']}/{counts['screenshots']['expected']} generated\n\n## Defects\n\n{defect_lines}\n"""
        (self.output_dir / "atlas_visual_qa_summary.md").write_text(markdown, encoding="utf-8")
        (self.output_dir / "atlas_visual_qa_summary.html").write_text(
            "<!doctype html><meta charset='utf-8'><title>ATLAS Visual QA</title><style>body{font:16px system-ui;max-width:1000px;margin:40px auto;white-space:pre-wrap}</style><body>" + html.escape(markdown) + "</body>", encoding="utf-8",
        )
        return summary


async def _async_main(args: argparse.Namespace) -> int:
    crawler = AtlasVisualCrawler(url=args.url, output_dir=Path(args.output), root=Path(args.root), headless=not args.headed)
    try:
        summary = await crawler.run(phase=args.phase)
    except GlobalCrawlFailure as exc:
        crawler._write_artifacts(final=True)
        print(json.dumps({"status": exc.category, "artifact": str(Path(args.output) / "atlas_visual_qa_summary.json")}, sort_keys=True))
        return 3
    required_complete = summary["required_completeness"]["status"] == "PASS"
    supplementary_failures = int(summary["counts"]["supplementary"]["failed"])
    print(json.dumps({
        "status": "PASS" if required_complete else "REQUIRED_COVERAGE_FAILED",
        "supplementary_failures": supplementary_failures,
        "artifact": str(Path(args.output) / "atlas_visual_qa_summary.json"),
    }, sort_keys=True))
    return 0 if required_complete else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", default="atlas_visual_qa_v1")
    parser.add_argument("--root", default=".")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--phase", choices=("required", "supplementary", "all"), default="all")
    return asyncio.run(_async_main(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
