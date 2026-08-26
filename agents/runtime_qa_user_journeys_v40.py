"""Synthetic client journeys for Atlas Runtime QA.

The engine behaves like a cautious real user:
- visits every navigation item
- opens tabs and expanders
- tests safe internal links/buttons
- researches valid and invalid tickers
- asks Atlas questions and validates non-empty, ticker-aware answers
- measures interaction latency
- captures screenshots and structured evidence

Destructive actions (delete, trade, logout, billing, upload, etc.) are never clicked.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, asdict
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Iterable, Mapping

from playwright.async_api import Frame, Page
from agents.runtime_qa_architecture import (
    certify_analyst_action_readiness, certify_ask_context, certify_etf_context,
    certify_missing_production_ticker, certify_research_context,
    decode_context_summary, protected_decision_digest,
    journey_completeness, production_decision_for_ticker, research_ticker_matrix, stable_digest,
)
from agents.runtime_qa_interactions import (
    InteractionContract, interaction_coverage, interaction_registry, interaction_result,
)


ERROR_RE = re.compile(
    r"traceback|uncaught exception|streamlitapiexception|modulenotfounderror|"
    r"importerror|attributeerror|typeerror|keyerror|valueerror",
    re.I,
)
SPINNER_RE = re.compile(r"running|loading|please wait|working", re.I)

SAFE_DENY_RE = re.compile(
    r"delete|remove|trash|logout|sign out|subscribe|billing|checkout|"
    r"buy|sell|place order|execute|upload|import|reset|clear all|disconnect",
    re.I,
)

PAGE_LABELS = (
    "Home",
    "Today's Opportunities",
    "Volume Intelligence",
    "Atlas Core Holdings",
    "Research Any Ticker",
    "Earnings Intelligence",
    "Full Ranked Scan",
    "Portfolio Intelligence",
    "Watchlist Intelligence",
    "Recovery",
    "ETFs",
    "Political Intelligence",
    "Ask AI",
    "Developer Center",
)

PAGE_READY_TEXT = {
    "Home": re.compile(r"Atlas V2 Institutional Intelligence|Morning Brief", re.I),
    "Today's Opportunities": re.compile(r"Today's Opportunities", re.I),
    "Volume Intelligence": re.compile(r"Volume & Momentum|Volume Intelligence", re.I),
    "Atlas Core Holdings": re.compile(r"Atlas Core Holdings", re.I),
    "Research Any Ticker": re.compile(r"Live Atlas Research|Enter a ticker to open current Atlas research", re.I),
    "Earnings Intelligence": re.compile(r"Earnings Intelligence", re.I),
    "Full Ranked Scan": re.compile(r"Full Ranked AI Scan", re.I),
    "Portfolio Intelligence": re.compile(r"Portfolio Intelligence", re.I),
    "Watchlist Intelligence": re.compile(r"Watchlist Intelligence", re.I),
    "Recovery": re.compile(r"Recovery Intelligence", re.I),
    "ETFs": re.compile(r"ETF Intelligence", re.I),
    "Political Intelligence": re.compile(r"Political Intelligence", re.I),
    "Ask AI": re.compile(r"Ask Atlas AI|Ask about a ticker", re.I),
    "Developer Center": re.compile(r"Developer Center", re.I),
}

PAGE_QA_IDS = {label: re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") for label in PAGE_LABELS}
PER_ROUTE_SETTLEMENT_SECONDS = 12
GENERIC_NAVIGATION_BUDGET_SECONDS = 180
RESEARCH_STEP_BUDGET_SECONDS = 45
ASK_STEP_BUDGET_SECONDS = 30
RESPONSIVE_PHASE_BUDGET_SECONDS = 75
REQUIRED_PHASE_MAX_SECONDS = (
    6 * RESEARCH_STEP_BUDGET_SECONDS
    + 6 * ASK_STEP_BUDGET_SECONDS
    + RESPONSIVE_PHASE_BUDGET_SECONDS
)


def navigation_phase_upper_bound(page_count: int) -> int:
    """Maximum generic-navigation wall time before remaining routes fail fast."""
    per_page = PER_ROUTE_SETTLEMENT_SECONDS + 3
    return min(GENERIC_NAVIGATION_BUDGET_SECONDS, max(0, int(page_count)) * per_page)

_TICKER_MATRIX = research_ticker_matrix(".")
RESEARCH_TICKERS = tuple(_TICKER_MATRIX["tickers"][:-1])
INVALID_TICKER = "INVALID123"
MISSING_PRODUCTION_TICKER = str(_TICKER_MATRIX.get("missing_production") or "")
CURRENT_TOP15_TICKER = str(_TICKER_MATRIX.get("dynamic_top15") or "")

ASK_AI_QUESTIONS = (
    "Why does ATLAS like this company?",
    "What are the biggest risks?",
    "Are earnings improving?",
    "What do analysts expect?",
    "What changed recently?",
    "What should I watch next?",
)
_ASK_TICKER = CURRENT_TOP15_TICKER or "NVDA"
ASK_AI_PROMPTS = tuple((_ASK_TICKER, f"{_ASK_TICKER}: {question}") for question in ASK_AI_QUESTIONS)
_RESEARCH_SUMMARIES: dict[str, dict[str, Any]] = {}


def navigation_contract_satisfied(*, selected: bool, page_ready: bool, rendered_exception: bool) -> bool:
    """Pure settlement rule shared by browser journeys and regression tests."""
    return bool(selected and page_ready and not rendered_exception)


def page_identity_settled(*, requested: str, rendered: str, selected: bool, page_ready: bool, rendered_exception: bool) -> bool:
    return bool(
        requested == rendered and
        navigation_contract_satisfied(selected=selected, page_ready=page_ready, rendered_exception=rendered_exception)
    )


def research_lifecycle_complete(
    *, canonical_context_ready: bool, render_complete: bool, rendered_exception: bool,
) -> bool:
    """A finalized context is necessary but not sufficient for a rendered report."""
    return bool(canonical_context_ready and render_complete and not rendered_exception)


def research_content_sections(text: str) -> list[str]:
    """Return legitimate section headings without treating them as errors."""
    expected = (
        "Executive Summary", "Live Price & Educational Trade Plan", "Atlas Rating",
        "Investment Thesis", "Financial Analysis", "Final Decision", "Atlas AI Summary",
        "AI Summary & Decision Insight", "Analyst Intelligence", "Earnings Intelligence",
    )
    return [section for section in expected if section.lower() in str(text or "").lower()]


def cross_page_digest_result(ticker: str, page_digests: Mapping[str, str]) -> dict[str, Any]:
    """Certify a non-empty set of page decision digests for one ticker."""
    captured = {str(page): str(digest) for page, digest in page_digests.items() if digest}
    unique = set(captured.values())
    return {
        "status": "PASS" if captured and len(unique) == 1 else "FAIL" if captured else "NOT_EXECUTED",
        "reason": None if captured else "No dynamic Top-15 page decision markers were captured.",
        "ticker": ticker,
        "page_decision_digests": captured,
        "consistent": len(unique) == 1 and bool(captured),
    }


async def _page_identity_matches(page: Page, label: str) -> bool:
    page_id = PAGE_QA_IDS.get(label) or re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    selector = (
        f'#atlas-qa-route-{page_id}[data-atlas-page="{page_id}"][data-atlas-status="selected"], '
        f'#atlas-qa-page-{page_id}[data-atlas-page="{page_id}"][data-atlas-page-ready="true"]'
    )
    for scope in _scopes(page):
        try:
            if await scope.locator(selector).count():
                return True
        except Exception:
            continue
    return False


def research_context_complete(context: Mapping[str, Any], ticker: str) -> bool:
    return bool(
        str(context.get("ticker") or "").upper() == str(ticker or "").upper()
        and all(context.get(key) for key in ("company", "security-type", "generated-at"))
        and context.get("context-version") == "RESEARCH_CONTEXT_V1"
        and context.get("decision-digest")
    )


def ask_grounding_complete(context: Mapping[str, Any], ticker: str) -> bool:
    return bool(
        str(context.get("ticker") or "").upper() == str(ticker or "").upper()
        and all(context.get(key) for key in ("section", "generated-at", "framework"))
        and context.get("context-version") == "RESEARCH_CONTEXT_V1"
        and context.get("context-digest")
        and context.get("decision-status")
        and context.get("decision-digest")
    )


@dataclass
class JourneyStep:
    journey: str
    step: str
    status: str
    duration_seconds: float
    page: str = ""
    detail: str = ""
    screenshot: str = ""
    evidence: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _scopes(page: Page) -> list[Page | Frame]:
    return [page, *list(page.frames)]


async def _visible_text(page: Page) -> str:
    chunks: list[str] = []
    for scope in _scopes(page):
        try:
            text = await scope.locator("body").inner_text(timeout=2500)
        except Exception:
            continue
        if text:
            chunks.append(text)
    return "\n".join(chunks)


async def _has_rendered_exception(page: Page) -> bool:
    """Detect an actual Streamlit exception, not prose containing words like 'error'."""
    for scope in _scopes(page):
        try:
            if await scope.locator('[data-testid="stException"]').count():
                return True
        except Exception:
            continue
    return False


async def _rendered_exception_identity(page: Page, *, ticker: str, stage: str) -> dict[str, str]:
    """Return only stable, sanitized exception identity; never a stack trace."""
    for scope in _scopes(page):
        try:
            marker = scope.locator('[data-atlas-qa="research-render-exception"]')
            if await marker.count():
                node = marker.last
                return {
                    "category": await node.get_attribute("data-atlas-exception-category") or "STREAMLIT_RENDER_EXCEPTION",
                    "filename": await node.get_attribute("data-atlas-exception-file") or "UNKNOWN",
                    "function": await node.get_attribute("data-atlas-exception-function") or "UNKNOWN",
                    "line": await node.get_attribute("data-atlas-exception-line") or "0",
                    "fingerprint": await node.get_attribute("data-atlas-exception-fingerprint") or "",
                    "ticker": await node.get_attribute("data-atlas-ticker") or ticker,
                    "stage": await node.get_attribute("data-atlas-research-stage") or stage,
                }
            nodes = scope.locator('[data-testid="stException"]')
            if not await nodes.count():
                continue
            text = _clean(await nodes.first.inner_text(timeout=1500))
            class_match = re.search(r"\b([A-Za-z][A-Za-z0-9_]*(?:Error|Exception))\b", text)
            category = class_match.group(1) if class_match else "STREAMLIT_RENDER_EXCEPTION"
            sanitized = re.sub(r"(?:https?://|/)[^\s]+", "[redacted-location]", text)
            fingerprint = hashlib.sha256(sanitized[:500].encode("utf-8")).hexdigest()[:16]
            return {"category": category, "fingerprint": fingerprint, "ticker": ticker, "stage": stage}
        except Exception:
            continue
    return {}


async def _page_contract_ready(page: Page, label: str) -> bool:
    page_id = PAGE_QA_IDS.get(label)
    if not page_id:
        return False
    selector = f'#atlas-qa-page-{page_id}[data-atlas-page="{page_id}"][data-atlas-page-ready="true"]'
    for scope in _scopes(page):
        try:
            if await scope.locator(selector).count():
                return True
        except Exception:
            continue
    return False


async def _screenshot(page: Page, output_dir: Path, name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_") or "journey"
    path = output_dir / f"journey_{safe}.png"
    try:
        await page.screenshot(path=str(path), full_page=True)
        return path.name
    except Exception:
        return ""


async def _click_text(page: Page, label: str, *, timeout_ms: int = 6500) -> bool:
    for scope in _scopes(page):
        candidates = (
            scope.get_by_role("radio", name=label, exact=True),
            scope.get_by_role("button", name=label, exact=True),
            scope.get_by_role("link", name=label, exact=True),
            scope.get_by_text(label, exact=True),
        )
        for locator in candidates:
            try:
                if await locator.count() and await locator.first.is_visible():
                    await locator.first.click(timeout=timeout_ms)
                    await asyncio.sleep(1.0)
                    return True
            except Exception:
                continue
    return False


async def _navigate(page: Page, label: str, output_dir: Path | None = None) -> tuple[bool, float, str]:
    started = time.monotonic()
    before_shot = await _screenshot(page, output_dir, f"before_nav_{label}") if output_dir else ""
    clicked = await _click_text(page, label)
    if not clicked:
        return False, time.monotonic() - started, f"Could not click navigation label: {label}"

    deadline = time.monotonic() + PER_ROUTE_SETTLEMENT_SECONDS
    text = ""
    while time.monotonic() < deadline:
        text = await _visible_text(page)
        selected = False
        for scope in _scopes(page):
            try:
                controls = scope.get_by_role("radio", name=label, exact=True)
                for index in range(await controls.count()):
                    control = controls.nth(index)
                    if await control.is_checked():
                        selected = True
                        break
            except Exception:
                continue
            if selected:
                break
        explicit_ready = await _page_contract_ready(page, label)
        identity_matches = await _page_identity_matches(page, label)
        text_ready = bool(PAGE_READY_TEXT.get(label, re.compile(re.escape(label), re.I)).search(text))
        # Canonical DOM markers are authoritative and intentionally hidden.
        # Heading text is retained only as diagnostic evidence.
        page_ready = explicit_ready and identity_matches
        rendered_exception = await _has_rendered_exception(page)
        rendered_identity = label if identity_matches else ""
        if page_identity_settled(requested=label, rendered=rendered_identity, selected=selected,
                                 page_ready=page_ready, rendered_exception=rendered_exception):
            return True, time.monotonic() - started, ""
        await asyncio.sleep(0.5)
    after_shot = await _screenshot(page, output_dir, f"failed_nav_{label}") if output_dir else ""
    return False, time.monotonic() - started, (
        f"Navigation did not settle on {label}: selected={selected}, page_ready={page_ready}, "
        f"identity_matches={identity_matches}, explicit_ready={explicit_ready}, heading_diagnostic={text_ready}, rendered_exception={rendered_exception}, "
        f"before_screenshot={before_shot or 'none'}, after_screenshot={after_shot or 'none'}."
    )


async def wait_for_page_settlement(page: Page, label: str, output_dir: Path | None = None) -> tuple[bool, float, str]:
    """Public route-settlement contract shared by inventory and journey engines."""
    started = time.monotonic()
    deadline = time.monotonic() + PER_ROUTE_SETTLEMENT_SECONDS
    identity = ready = rendered_exception = False
    heading_diagnostic = False
    while time.monotonic() < deadline:
        identity = await _page_identity_matches(page, label)
        ready = await _page_contract_ready(page, label)
        text = await _visible_text(page)
        heading_diagnostic = bool(PAGE_READY_TEXT.get(label, re.compile(re.escape(label), re.I)).search(text))
        rendered_exception = await _has_rendered_exception(page)
        if identity and ready and not rendered_exception:
            return True, time.monotonic() - started, ""
        await asyncio.sleep(0.4)
    shot = await _screenshot(page, output_dir, f"failed_settlement_{label}") if output_dir else ""
    return False, time.monotonic() - started, (
        f"Rendered page identity did not settle on {label}; identity={identity}, ready={ready}, "
        f"heading_diagnostic={heading_diagnostic}, rendered_exception={rendered_exception}; "
        f"screenshot={shot or 'none'}."
    )


async def _find_text_input(page: Page, purpose: str):
    selectors: list[str]
    if purpose == "research":
        selectors = [
            'input[placeholder*="ticker" i]',
            'input[aria-label*="ticker" i]',
            'input[type="text"]',
        ]
    else:
        selectors = [
            'textarea[placeholder*="ask" i]',
            'textarea[placeholder*="question" i]',
            'input[placeholder*="ask" i]',
            'input[placeholder*="question" i]',
            'textarea',
            'input[type="text"]',
        ]

    for scope in _scopes(page):
        for selector in selectors:
            try:
                locator = scope.locator(selector)
                count = await locator.count()
                for index in range(min(count, 8)):
                    item = locator.nth(index)
                    if await item.is_visible() and await item.is_enabled():
                        return item
            except Exception:
                continue
    return None


async def _wait_for_text_input(page: Page, purpose: str, timeout_seconds: float = 10):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        field = await _find_text_input(page, purpose)
        if field is not None:
            return field
        await asyncio.sleep(0.35)
    return None


async def _click_matching_button(page: Page, patterns: Iterable[str]) -> str:
    regex = re.compile("|".join(re.escape(item) for item in patterns), re.I)
    for scope in _scopes(page):
        try:
            buttons = scope.get_by_role("button")
            count = await buttons.count()
        except Exception:
            continue
        for index in range(min(count, 50)):
            button = buttons.nth(index)
            try:
                if not await button.is_visible() or not await button.is_enabled():
                    continue
                label = _clean(await button.inner_text())
                if SAFE_DENY_RE.search(label):
                    continue
                if regex.search(label):
                    await button.click(timeout=6000)
                    await asyncio.sleep(0.7)
                    return label
            except Exception:
                continue
    return ""


async def _click_qa_submit(page: Page, form_key: str, expected_name: re.Pattern[str]) -> str:
    """Select a submit inside one named Streamlit form; never fall through to unrelated controls."""
    for scope in _scopes(page):
        # Current Streamlit does not expose widget keys in every release, so use the
        # unique exact accessible name as the compatible form-submit contract.
        candidates = scope.get_by_role("button", name=expected_name)
        for index in range(await candidates.count()):
            button = candidates.nth(index)
            try:
                label = _clean(await button.inner_text())
                if await button.is_visible() and await button.is_enabled() and not SAFE_DENY_RE.search(label):
                    await button.click(timeout=6000)
                    return label
            except Exception:
                continue
    return ""


async def _wait_for_qa_state(page: Page, qa: str, status: str, ticker: str, timeout_seconds: float) -> bool:
    selector = (
        f'[data-atlas-qa="{qa}"][data-atlas-status="{status}"]'
        f'[data-atlas-ticker="{ticker}"]'
    )
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        for scope in _scopes(page):
            try:
                if await scope.locator(selector).count():
                    return True
            except Exception:
                continue
        await asyncio.sleep(0.4)
    return False


async def _qa_response_length(page: Page, ticker: str) -> int:
    selector = f'[data-atlas-qa="ask-ai-response"][data-atlas-status="complete"][data-atlas-ticker="{ticker}"]'
    for scope in _scopes(page):
        try:
            marker = scope.locator(selector).last
            value = await marker.get_attribute("data-atlas-response-length")
            if value:
                return int(value)
        except Exception:
            continue
    return 0


async def _qa_state_metadata(page: Page, qa: str, status: str, ticker: str) -> dict[str, str]:
    selector = f'[data-atlas-qa="{qa}"][data-atlas-status="{status}"][data-atlas-ticker="{ticker}"]'
    attributes = (
        "data-atlas-ticker", "data-atlas-company", "data-atlas-security-type",
        "data-atlas-generated-at", "data-atlas-section", "data-atlas-evidence-used",
        "data-atlas-evidence-missing", "data-atlas-framework",
        "data-atlas-context-version", "data-atlas-decision-status",
        "data-atlas-decision-digest", "data-atlas-context-digest",
    )
    for scope in _scopes(page):
        try:
            marker = scope.locator(selector).last
            if not await marker.count():
                continue
            return {
                name.removeprefix("data-atlas-"): (await marker.get_attribute(name) or "")
                for name in attributes
            }
        except Exception:
            continue
    return {}


async def _research_progress_metadata(page: Page, ticker: str) -> dict[str, Any]:
    selector = f'[data-atlas-qa="research-progress"][data-atlas-ticker="{ticker}"]'
    attributes = (
        "data-atlas-ticker", "data-atlas-request-id", "data-atlas-readiness",
        "data-atlas-current-stage", "data-atlas-last-completed-stage",
        "data-atlas-provider-calls", "data-atlas-cache-hits",
        "data-atlas-progress-summary",
    )
    for scope in _scopes(page):
        try:
            marker = scope.locator(selector).last
            if await marker.count():
                result = {name.removeprefix("data-atlas-"): (await marker.get_attribute(name) or "") for name in attributes}
                try:
                    result["progress_summary"] = json.loads(result.pop("progress-summary") or "{}")
                except (TypeError, ValueError):
                    result["progress_summary"] = {}
                return result
        except Exception:
            continue
    return {}


async def _canonical_research_summary(page: Page, ticker: str) -> dict[str, Any]:
    selector = f'[data-atlas-qa="research-context-v1"][data-atlas-ticker="{ticker}"]'
    for scope in _scopes(page):
        try:
            marker = scope.locator(selector).last
            if await marker.count():
                return decode_context_summary(await marker.get_attribute("data-atlas-context-summary") or "")
        except Exception:
            continue
    return {}


async def _rendered_family_summary(page: Page) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for scope in _scopes(page):
        try:
            markers = scope.locator('[data-atlas-qa="research-rendered-family"]')
            for index in range(await markers.count()):
                marker = markers.nth(index)
                family = await marker.get_attribute("data-atlas-family") or ""
                if family:
                    result[family] = {
                        "displayed": await marker.get_attribute("data-atlas-displayed") or "false",
                        "semantic_status": await marker.get_attribute("data-atlas-rendered-status") or "",
                        "provider": await marker.get_attribute("data-atlas-provider") or "",
                        "cache_status": await marker.get_attribute("data-atlas-cache-status") or "",
                        "render_source": await marker.get_attribute("data-atlas-render-source") or "",
                    }
        except Exception:
            continue
    return result


async def _page_certification_metadata(page: Page, label: str) -> dict[str, str]:
    page_id = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    selector = f'[data-atlas-qa="page-certification"][data-atlas-page="{page_id}"]'
    for scope in _scopes(page):
        try:
            marker = scope.locator(selector).last
            if await marker.count():
                return {
                    "ticker": await marker.get_attribute("data-atlas-ticker") or "",
                    "decision_digest": await marker.get_attribute("data-atlas-decision-digest") or "",
                }
        except Exception:
            continue
    return {}


async def page_certification_metadata(page: Page, label: str) -> dict[str, str]:
    """Public sanitized page-decision marker reader for the inventory phase."""
    return await _page_certification_metadata(page, label)


async def _wait_for_change(
    page: Page,
    before: str,
    *,
    required_term: str = "",
    timeout_seconds: float = 22,
) -> tuple[str, bool]:
    deadline = time.monotonic() + timeout_seconds
    latest = before
    while time.monotonic() < deadline:
        await asyncio.sleep(0.65)
        latest = await _visible_text(page)
        meaningful_change = len(latest) > len(before) + 80 or latest != before
        term_ok = not required_term or required_term.lower() in latest.lower()
        if meaningful_change and term_ok and not ERROR_RE.search(latest):
            return latest, True
    return latest, False


async def _exercise_safe_controls(page: Page, page_name: str) -> dict[str, Any]:
    """Click safe tabs/expanders and a small number of safe internal links/buttons."""
    result = {"tabs_clicked": 0, "expanders_clicked": 0, "buttons_clicked": [], "errors": [], "interaction_notes": []}

    # Streamlit tabs.
    for scope in _scopes(page):
        try:
            tabs = scope.get_by_role("tab")
            for index in range(min(await tabs.count(), 12)):
                tab = tabs.nth(index)
                if not await tab.is_visible():
                    continue
                try:
                    await tab.click(timeout=3500)
                    result["tabs_clicked"] += 1
                    await asyncio.sleep(0.15)
                except Exception as exc:
                    # Streamlit may replace a tab node during a successful rerun. This
                    # is diagnostic unless the settled page also renders an error.
                    result["interaction_notes"].append(f"tab[{index}] detached: {type(exc).__name__}")
        except Exception:
            pass

    # Streamlit expanders are usually buttons with aria-expanded.
    for scope in _scopes(page):
        try:
            expanders = scope.locator('button[aria-expanded="false"]')
            for index in range(min(await expanders.count(), 10)):
                item = expanders.nth(index)
                try:
                    label = _clean(await item.inner_text())
                    if label and not SAFE_DENY_RE.search(label) and await item.is_visible():
                        await item.click(timeout=3500)
                        result["expanders_clicked"] += 1
                        await asyncio.sleep(0.15)
                except Exception as exc:
                    result["interaction_notes"].append(f"expander[{index}] detached: {type(exc).__name__}")
        except Exception:
            pass

    # Safe internal calls-to-action only. Avoid generic buttons that may mutate data.
    cta_re = re.compile(r"open complete atlas research|view research|show upcoming earnings|show details", re.I)
    for scope in _scopes(page):
        try:
            nodes = scope.locator("button, a")
            count = await nodes.count()
        except Exception:
            continue
        for index in range(min(count, 80)):
            node = nodes.nth(index)
            try:
                if not await node.is_visible() or not await node.is_enabled():
                    continue
                label = _clean(await node.inner_text())
                if not label or SAFE_DENY_RE.search(label) or not cta_re.search(label):
                    continue
                if len(result["buttons_clicked"]) >= 3:
                    break
                await node.click(timeout=4000)
                result["buttons_clicked"].append(label[:120])
                await asyncio.sleep(0.35)
            except Exception:
                continue

    text = await _visible_text(page)
    if ERROR_RE.search(text):
        result["errors"].append("Rendered error text detected after safe interaction exercise.")
    return result


async def _research_one(page: Page, ticker: str, output_dir: Path) -> JourneyStep:
    journey = f"Research {ticker}"
    started = time.monotonic()
    # Every ticker begins from a fresh route render.  This clears stale DOM
    # exceptions without reusing any prior ticker's rendered state.
    ok, _, nav_detail = await _navigate(page, "Research Any Ticker", output_dir)
    if not ok:
        return JourneyStep(journey, "open research page", "FAIL", time.monotonic()-started, "Research Any Ticker", nav_detail)

    before = await _visible_text(page)
    field = await _wait_for_text_input(page, "research")
    if field is None:
        return JourneyStep(journey, "locate ticker input", "FAIL", time.monotonic()-started, "Research Any Ticker", "No visible ticker text input was found.")

    try:
        await field.fill(ticker)
    except Exception as exc:
        return JourneyStep(journey, "enter ticker", "FAIL", time.monotonic()-started, "Research Any Ticker", f"{type(exc).__name__}: {exc}")

    clicked = await _click_qa_submit(page, "research_ticker_form", re.compile(r"^Research ticker$", re.I))
    if not clicked:
        try:
            await field.press("Enter")
        except Exception:
            pass

    expected_status = "error" if ticker == INVALID_TICKER else "complete"
    canonical_marker_ready = False
    marker_ready = False
    progress: dict[str, Any] = {}
    exception_identity: dict[str, str] = {}
    poll_deadline = time.monotonic() + 44.0
    try:
        while time.monotonic() < poll_deadline:
            progress = await _research_progress_metadata(page, ticker) or progress
            exception_identity = await _rendered_exception_identity(page, ticker=ticker, stage=str(progress.get("current-stage") or "research_render")) or exception_identity
            if expected_status == "error":
                marker_ready = await _wait_for_qa_state(page, "research-container", "error", ticker, 0.05)
            else:
                canonical_marker_ready = await _wait_for_qa_state(page, "research-context", "ready", ticker, 0.05)
                marker_ready = await _wait_for_qa_state(page, "research-container", "complete", ticker, 0.05)
            if marker_ready and (expected_status == "error" or canonical_marker_ready):
                break
            await asyncio.sleep(0.25)
    except asyncio.CancelledError:
        progress = await _research_progress_metadata(page, ticker) or progress
        exception_identity = await _rendered_exception_identity(page, ticker=ticker, stage=str(progress.get("current-stage") or "research_timeout")) or exception_identity
        screenshot = await _screenshot(page, output_dir, f"research_timeout_{ticker}")
        return JourneyStep(
            journey, "generate full research", "FAIL", time.monotonic()-started,
            "Research Any Ticker", "Per-ticker Research budget exhausted with partial progress preserved.",
            screenshot, {"research_progress": progress, "rendered_exception_identity": exception_identity},
        )
    context = await _qa_state_metadata(page, "research-container", expected_status, ticker)
    canonical_summary = await _canonical_research_summary(page, ticker) if expected_status == "complete" else {}
    if canonical_summary:
        _RESEARCH_SUMMARIES[ticker] = canonical_summary
    rendered_families = await _rendered_family_summary(page) if expected_status == "complete" else {}
    after = await _visible_text(page)
    changed = after != before
    screenshot = await _screenshot(page, output_dir, f"research_{ticker}")

    if ticker == INVALID_TICKER:
        invalid_handled = bool(
            re.search(r"invalid|not found|unable|no data|unsupported|enter a valid", after, re.I)
        ) and not ERROR_RE.search(after)
        invalid_provider_calls = int(progress.get("provider-calls") or 0)
        canonical_context_absent = not bool(await _canonical_research_summary(page, ticker))
        return JourneyStep(
            journey, "invalid ticker handling",
            "PASS" if invalid_handled and marker_ready else "FAIL",
            time.monotonic()-started,
            "Research Any Ticker",
            "Invalid ticker was handled without a crash." if invalid_handled else "Invalid ticker did not produce a clear validation message.",
            screenshot,
            {
                "submit_control": clicked, "content_changed": changed,
                "qa_marker_ready": marker_ready, "provider_calls": invalid_provider_calls,
                "canonical_context_absent": canonical_context_absent,
                "no_investment_decision": canonical_context_absent,
            },
        )

    markers = research_content_sections(after)
    ticker_present = context.get("ticker") == ticker or ticker.lower() in after.lower()
    context_ready = research_context_complete(context, ticker)
    reconciliation = certify_research_context(canonical_summary, rendered_families)
    expected_decision = production_decision_for_ticker(ticker)
    decision_digest_matches = bool(canonical_summary) and canonical_summary.get("production_decision_digest") == protected_decision_digest(expected_decision)
    special: dict[str, Any] = {}
    if ticker == MISSING_PRODUCTION_TICKER:
        empty_expected = production_decision_for_ticker(ticker)
        special["missing_production"] = {
            "status": canonical_summary.get("production_decision_status"),
            "digest_matches_empty_decision": canonical_summary.get("production_decision_digest") == protected_decision_digest(empty_expected),
        }
    if ticker == "SPY":
        special["etf"] = certify_etf_context(canonical_summary)
    special["analyst_action_readiness"] = canonical_summary.get("analyst_action_readiness") or {}
    rendered_exception = await _has_rendered_exception(page)
    exception_identity = await _rendered_exception_identity(page, ticker=ticker, stage="research_render") or exception_identity
    lifecycle_complete = research_lifecycle_complete(
        canonical_context_ready=canonical_marker_ready and context_ready,
        render_complete=marker_ready,
        rendered_exception=rendered_exception,
    )
    passed = lifecycle_complete and ticker_present and len(markers) >= 2 and bool(canonical_summary) and decision_digest_matches
    return JourneyStep(
        journey,
        "generate full research",
        "PASS" if passed else "FAIL",
        time.monotonic()-started,
        "Research Any Ticker",
        f"Rendered content sections: {', '.join(markers) or 'none'}",
        screenshot,
        {
            "submit_control": clicked,
            "content_changed": changed,
            "qa_marker_ready": marker_ready,
            "canonical_marker_ready": canonical_marker_ready,
            "render_lifecycle_complete": lifecycle_complete,
            "ticker_present": ticker_present,
            "research_context_ready": context_ready,
            "research_context": context,
            "canonical_research_summary": canonical_summary,
            "canonical_reconciliation": reconciliation,
            "rendered_family_summary": rendered_families,
            "decision_digest_matches": decision_digest_matches,
            "special_certification": special,
            "markers": markers,
            "rendered_exception_identity": exception_identity,
            "research_progress": progress,
        },
    )


async def _ask_question(page: Page, ticker: str, prompt: str, output_dir: Path) -> JourneyStep:
    journey = f"Ask AI — {ticker}"
    started = time.monotonic()

    # Prefer the dedicated Ask AI page.
    ok, _, nav_detail = await _navigate(page, "Ask AI", output_dir)
    if not ok:
        return JourneyStep(journey, "open Ask AI", "FAIL", time.monotonic()-started, "Ask AI", nav_detail)

    before = await _visible_text(page)
    field = await _wait_for_text_input(page, "ask")
    if field is None:
        return JourneyStep(journey, "locate question input", "FAIL", time.monotonic()-started, "Ask AI", "No visible Ask AI input was found.")

    try:
        await field.fill(prompt)
    except Exception as exc:
        return JourneyStep(journey, "enter question", "FAIL", time.monotonic()-started, "Ask AI", f"{type(exc).__name__}: {exc}")

    clicked = await _click_qa_submit(page, "ask_ai_form", re.compile(r"^Ask Atlas$", re.I))
    if not clicked:
        try:
            await field.press("Enter")
        except Exception:
            pass

    # The first request may initialize the synthesis client; later requests use the normal budget.
    timeout = 60 if ticker == ASK_AI_PROMPTS[0][0] else 35
    marker_ready = await _wait_for_qa_state(page, "ask-ai-response", "complete", ticker, timeout)
    grounding = await _qa_state_metadata(page, "ask-ai-response", "complete", ticker)
    response_length = await _qa_response_length(page, ticker)
    after = await _visible_text(page)
    changed = after != before
    screenshot = await _screenshot(page, output_dir, f"ask_ai_{ticker}")

    new_text = after[len(before):] if after.startswith(before) else after
    ticker_present = grounding.get("ticker") == ticker or ticker.lower() in new_text.lower() or ticker.lower() in after.lower()
    grounding_ready = ask_grounding_complete(grounding, ticker)
    numeric_evidence = bool(re.search(r"\d+(?:\.\d+)?%|\$\d+|\d+\.\d+", new_text))
    unsupported_numeric = bool(numeric_evidence and str(grounding.get("evidence-used") or "0") == "0")
    canonical_ask = certify_ask_context(_RESEARCH_SUMMARIES.get(ticker, {}), {
        "ticker": grounding.get("ticker"), "context_digest": grounding.get("context-digest"),
    }) if ticker in _RESEARCH_SUMMARIES else {"classification": "ARCHITECTURE_DRIFT", "severity": "P1", "reason": "Research context was not captured for Ask comparison."}
    generic_only = bool(re.fullmatch(r".*(review the available data|unable to answer|try again).*", _clean(new_text), re.I))
    rendered_exception = await _has_rendered_exception(page)
    exception_identity = await _rendered_exception_identity(page, ticker=ticker, stage="ask_render")
    passed = marker_ready and response_length > 0 and ticker_present and grounding_ready and len(_clean(new_text).split()) >= 18 and not rendered_exception and not generic_only and not unsupported_numeric and canonical_ask.get("classification") == "PASS"

    return JourneyStep(
        journey,
        "answer investment question",
        "PASS" if passed else "FAIL",
        time.monotonic()-started,
        "Ask AI",
        "Ticker-aware answer returned." if passed else "Ask AI response was missing, generic, ticker-inconsistent, or errored.",
        screenshot,
        {
            "submit_control": clicked,
            "content_changed": changed,
            "qa_marker_ready": marker_ready,
            "ticker_present": ticker_present,
            "grounding_ready": grounding_ready,
            "grounding": grounding,
            "numeric_evidence": numeric_evidence,
            "unsupported_numeric_claim": unsupported_numeric,
            "canonical_context_certification": canonical_ask,
            "response_word_count": len(_clean(new_text).split()),
            "response_length": response_length,
            "rendered_exception_identity": exception_identity,
        },
    )


async def _responsive_smoke(page: Page, output_dir: Path) -> list[JourneyStep]:
    # Stable report labels include "Responsive tablet" and "Responsive mobile".
    steps: list[JourneyStep] = []
    original = page.viewport_size or {"width": 1440, "height": 1000}
    for label, width, height in (("tablet", 768, 1024), ("mobile", 390, 844)):
        started = time.monotonic()
        try:
            await page.set_viewport_size({"width": width, "height": height})
            await asyncio.sleep(0.5)
            geometry = await page.evaluate(
                """() => ({
                    viewport: document.documentElement.clientWidth,
                    scroll: document.documentElement.scrollWidth,
                    bodyScroll: document.body ? document.body.scrollWidth : 0
                })"""
            )
            overflow = max(int(geometry.get("scroll", 0)), int(geometry.get("bodyScroll", 0))) > int(geometry.get("viewport", width)) + 12
            shot = await _screenshot(page, output_dir, f"responsive_{label}")
            steps.append(JourneyStep(
                f"Responsive {label}",
                "horizontal overflow smoke",
                "FAIL" if overflow else "PASS",
                time.monotonic()-started,
                page.url,
                f"viewport={geometry.get('viewport')} scrollWidth={max(geometry.get('scroll',0), geometry.get('bodyScroll',0))}",
                shot,
                geometry,
            ))
        except Exception as exc:
            steps.append(JourneyStep(
                f"Responsive {label}",
                "responsive smoke",
                "FAIL",
                time.monotonic()-started,
                page.url,
                f"{type(exc).__name__}: {exc}",
            ))
    await page.set_viewport_size(original)
    return steps


async def _core_mobile_certification(page: Page, output_dir: Path) -> list[JourneyStep]:
    steps: list[JourneyStep] = []
    original = page.viewport_size or {"width": 1440, "height": 1000}
    await page.set_viewport_size({"width": 390, "height": 844})
    for label in ("Home", "Today's Opportunities", "Research Any Ticker", "Ask AI"):
        started = time.monotonic()
        ok, _, detail = await _navigate(page, label, output_dir)
        screenshot = await _screenshot(page, output_dir, f"mobile_{label}") if ok else ""
        metadata = await _page_certification_metadata(page, label) if ok else {}
        rendered_exception = await _has_rendered_exception(page) if ok else True
        steps.append(JourneyStep(
            "Core mobile certification", label,
            "PASS" if ok and screenshot and not rendered_exception else "FAIL",
            time.monotonic() - started, label, detail or "Mobile core page rendered.",
            screenshot, {"page_certification": metadata, "rendered_exception": rendered_exception},
        ))
    await page.set_viewport_size(original)
    return steps


async def _discover_interaction_markers(page: Page, source_page: str) -> list[InteractionContract]:
    """Read sanitized interaction contracts emitted by the rendered product."""
    discovered: list[InteractionContract] = []
    seen: set[str] = set()
    for scope in _scopes(page):
        try:
            markers = scope.locator("[data-atlas-interaction-id]")
            for index in range(min(await markers.count(), 60)):
                marker = markers.nth(index)
                stable_id = str(await marker.get_attribute("data-atlas-interaction-id") or "")
                if not stable_id or stable_id in seen:
                    continue
                seen.add(stable_id)
                discovered.append(InteractionContract(
                    stable_id=stable_id,
                    source_page=source_page,
                    interaction_type=str(await marker.get_attribute("data-atlas-interaction-type") or "READ_ONLY_ACTION"),
                    visible_label=_clean(await marker.inner_text(timeout=500)) or stable_id,
                    expected_result="Rendered interaction contract settles to its declared destination/state",
                    expected_page=str(await marker.get_attribute("data-atlas-expected-page") or ""),
                    expected_ticker=str(await marker.get_attribute("data-atlas-expected-ticker") or ""),
                    required=False,
                    failure_severity="P1" if stable_id.startswith(("home-report-card-", "home-research-")) else "P2",
                ))
        except Exception:
            continue
    return discovered


async def _certify_all_tabs(page: Page, page_label: str, output_dir: Path, expected_ticker: str = "") -> dict[str, Any] | None:
    """Exercise every rendered tab and reject stale/non-selected tab state."""
    tabs = None
    for scope in _scopes(page):
        candidate = scope.locator('[role="tab"]')
        if await candidate.count():
            tabs = candidate
            break
    if tabs is None:
        return None
    count = min(await tabs.count(), 30)
    before_path = await _screenshot(page, output_dir, f"interaction_{page_label}_tabs_before")
    states = []
    previous_digest = ""
    for index in range(count):
        tab = tabs.nth(index)
        label = _clean(await tab.inner_text(timeout=800))
        try:
            await tab.click(timeout=ACTION_TIMEOUT_MS if "ACTION_TIMEOUT_MS" in globals() else 6000)
            await page.wait_for_timeout(250)
            selected = str(await tab.get_attribute("aria-selected") or "").lower() == "true"
            panel_text = ""
            controls = str(await tab.get_attribute("aria-controls") or "")
            if controls:
                for scope in _scopes(page):
                    panel = scope.locator(f'#{controls}')
                    if await panel.count():
                        panel_text = _clean(await panel.first.inner_text(timeout=1000))
                        break
            if not panel_text:
                for scope in _scopes(page):
                    panels = scope.locator('[role="tabpanel"]')
                    if await panels.count() > index:
                        panel_text = _clean(await panels.nth(index).inner_text(timeout=1000))
                        break
            content_digest = hashlib.sha256(panel_text.encode("utf-8")).hexdigest()[:12] if panel_text else ""
            stale_content = bool(previous_digest and content_digest and previous_digest == content_digest)
            ticker_retained = True
            if expected_ticker:
                ticker_retained = await _wait_for_qa_state(page, "research-container", "complete", expected_ticker, 0.2)
            rendered_exception = await _has_rendered_exception(page)
            states.append({
                "label": label, "selected": selected,
                "content_rendered": bool(panel_text), "content_digest": content_digest,
                "stale_content": stale_content, "ticker_retained": ticker_retained,
                "rendered_exception": rendered_exception,
            })
            if content_digest:
                previous_digest = content_digest
        except Exception:
            states.append({"label": label, "selected": False, "content_rendered": False, "content_digest": "", "stale_content": False, "ticker_retained": False, "rendered_exception": False})
    after_path = await _screenshot(page, output_dir, f"interaction_{page_label}_tabs_after")
    passed = bool(states) and all(item["selected"] and item["content_rendered"] and item["ticker_retained"] and not item["stale_content"] and not item["rendered_exception"] for item in states)
    registry_id = {
        "Home": "home-more-decisions-tabs",
        "Research Any Ticker": "research-all-tabs",
        "Earnings Intelligence": "earnings-tabs",
        "ETFs": "etf-tabs",
    }.get(page_label, re.sub(r"[^a-z0-9]+", "-", page_label.lower()).strip("-") + "-all-tabs")
    return {
        "interaction_id": registry_id,
        "source_page": page_label,
        "interaction_type": "TAB",
        "required": page_label in {"Home", "Research Any Ticker", "Earnings Intelligence", "ETFs"},
        "status": "PASS" if passed else "FAIL",
        "classification": "PASS" if passed else "PRODUCT_DEFECT" if any(item["rendered_exception"] for item in states) else "QA_DEFECT",
        "severity": "" if passed else "P1",
        "tabs": states,
        "before_screenshot": before_path,
        "after_screenshot": after_path,
    }


async def _certify_important_expanders(page: Page, page_label: str, output_dir: Path) -> dict[str, Any] | None:
    controls = None
    for scope in _scopes(page):
        candidate = scope.locator('button[aria-expanded]')
        if await candidate.count():
            controls = candidate
            break
    if controls is None:
        return None
    states = []
    before = await _screenshot(page, output_dir, f"interaction_{page_label}_expanders_before")
    for index in range(min(await controls.count(), 10)):
        control = controls.nth(index)
        label = _clean(await control.inner_text(timeout=800))
        if SAFE_DENY_RE.search(label):
            continue
        try:
            if str(await control.get_attribute("aria-expanded") or "false").lower() != "true":
                await control.click(timeout=3500)
                await page.wait_for_timeout(200)
            opened = str(await control.get_attribute("aria-expanded") or "false").lower() == "true"
            rendered_exception = await _has_rendered_exception(page)
            states.append({"label": label, "opened": opened, "rendered_exception": rendered_exception})
            if opened:
                await control.click(timeout=3500)
        except Exception:
            states.append({"label": label, "opened": False, "rendered_exception": False})
    after = await _screenshot(page, output_dir, f"interaction_{page_label}_expanders_after")
    passed = bool(states) and all(item["opened"] and not item["rendered_exception"] for item in states)
    return {
        "interaction_id": "research-important-expanders" if page_label == "Research Any Ticker" else re.sub(r"[^a-z0-9]+", "-", page_label.lower()).strip("-") + "-expanders",
        "source_page": page_label, "interaction_type": "EXPANDER",
        "required": page_label == "Research Any Ticker",
        "status": "PASS" if passed else "FAIL",
        "classification": "PASS" if passed else "PRODUCT_DEFECT" if any(item["rendered_exception"] for item in states) else "QA_DEFECT",
        "severity": "" if passed else "P2", "expanders": states,
        "before_screenshot": before, "after_screenshot": after,
    }


async def _interaction_crawler(page: Page, output_dir: Path, progress_state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Bounded core-page interaction inventory and tab execution."""
    dynamic: list[InteractionContract] = []
    results: list[dict[str, Any]] = []
    tab_inventory: dict[str, list[str]] = {}
    def checkpoint() -> None:
        if progress_state is None:
            return
        registry = interaction_registry(dynamic)
        progress_state.clear()
        progress_state.update({
            "registry": registry, "results": list(results),
            "coverage": interaction_coverage(registry, results),
            "tab_inventory": dict(tab_inventory), "status": "IN_PROGRESS",
        })
    # Inventory every active page for tabs/declared interactions. Deep required
    # contracts remain concentrated on the eight customer-critical pages.
    for label in PAGE_LABELS:
        ok, _, _ = await _navigate(page, label, output_dir)
        if not ok:
            continue
        page_dynamic = await _discover_interaction_markers(page, label)
        dynamic.extend(page_dynamic)
        tab_result = await _certify_all_tabs(page, label, output_dir)
        if tab_result:
            results.append(tab_result)
            tab_inventory[label] = [item["label"] for item in tab_result.get("tabs") or []]
        expander_result = await _certify_important_expanders(page, label, output_dir)
        if expander_result:
            results.append(expander_result)
        checkpoint()
        # Deterministically sample first/middle/last dynamic controls.  Failed
        # interactions retain before/after screenshots and never mutate known
        # customer-owned state.
        candidates = [item for item in page_dynamic if item.interaction_type in {"DRILL_DOWN", "NAVIGATION", "EXTERNAL_LINK", "READ_ONLY_ACTION"}]
        sampled = list(dict.fromkeys([0, len(candidates) // 2, len(candidates) - 1])) if candidates else []
        for index in sampled:
            contract = candidates[index]
            before = await _screenshot(page, output_dir, f"interaction_{contract.stable_id}_before")
            before_text = await _visible_text(page)
            clicked = False
            for scope in _scopes(page):
                marker = scope.locator(f'[data-atlas-interaction-id="{contract.stable_id}"]')
                if not await marker.count():
                    continue
                button = marker.first.locator("xpath=following::button[1]")
                if await button.count():
                    try:
                        await button.first.click(timeout=6000)
                        clicked = True
                    except Exception:
                        pass
                    break
            if clicked:
                await page.wait_for_timeout(600)
            after_text = await _visible_text(page)
            expected_ticker = contract.expected_ticker.upper()
            ticker_matches = not expected_ticker or expected_ticker.lower() in after_text.lower()
            expected_page_label = "Research Any Ticker" if contract.expected_page == "research-any-ticker" else contract.expected_page
            destination_detail = "No route transition required."
            if expected_page_label:
                destination, _, destination_detail = await wait_for_page_settlement(page, expected_page_label, output_dir)
            else:
                destination = after_text != before_text
            expected_component = True
            if destination and expected_page_label == "Research Any Ticker" and expected_ticker:
                expected_component = await _wait_for_qa_state(page, "research-container", "complete", expected_ticker, 4)
            rendered_exception = await _has_rendered_exception(page)
            after = await _screenshot(page, output_dir, f"interaction_{contract.stable_id}_after")
            result = interaction_result(
                contract.to_dict(), click_accepted=clicked,
                state_changed=after_text != before_text,
                destination_settled=destination and expected_component,
                ticker_matches=ticker_matches,
                rendered_exception=rendered_exception,
                before_screenshot=before, after_screenshot=after,
                detail=(destination_detail or "Destination settled.") + (" Expected component rendered." if expected_component else " Expected component missing."),
            )
            results.append(result)
            if contract.stable_id.startswith("home-report-card-") and not any(
                item.get("interaction_id") == "home-report-card-dynamic" for item in results
            ):
                results.append({**result, "interaction_id": "home-report-card-dynamic", "required": True})
            if label != "Home":
                await _navigate(page, label, output_dir)
            checkpoint()
    registry = interaction_registry(dynamic)
    coverage = interaction_coverage(registry, results)
    final = {"registry": registry, "results": results, "coverage": coverage, "tab_inventory": tab_inventory, "status": "COMPLETE"}
    if progress_state is not None:
        progress_state.clear()
        progress_state.update(final)
    return final


async def _targeted_home_research(page: Page, output_dir: Path) -> JourneyStep:
    """Exercise one real rendered Home Research card and its declared contract."""
    started = time.monotonic()
    ok, _, detail = await _navigate(page, "Home", output_dir)
    if not ok:
        return JourneyStep("Home report card", "open Home", "FAIL", time.monotonic() - started, "Home", detail)
    markers = []
    for scope in _scopes(page):
        try:
            candidates = scope.locator('[data-atlas-interaction-id^="home-report-card-"]')
            markers.extend(await candidates.all())
        except Exception:
            continue
    if not markers:
        return JourneyStep("Home report card", "discover Research card", "FAIL", time.monotonic() - started, "Home", "No rendered Home report-card interaction marker was found.")
    marker = markers[0]
    interaction_id = str(await marker.get_attribute("data-atlas-interaction-id") or "")
    expected_ticker = str(await marker.get_attribute("data-atlas-expected-ticker") or "").upper()
    expected_page = str(await marker.get_attribute("data-atlas-expected-page") or "")
    before = await _screenshot(page, output_dir, f"targeted_{interaction_id}_before")
    clicked = False
    button = marker.locator("xpath=following::button[1]")
    if await button.count():
        try:
            await button.first.click(timeout=6000)
            clicked = True
        except Exception:
            clicked = False
    destination_ok, _, settlement = await wait_for_page_settlement(page, "Research Any Ticker", output_dir) if clicked else (False, 0.0, "Click was not accepted.")
    component_ready = await _wait_for_qa_state(page, "research-container", "complete", expected_ticker, 12) if destination_ok and expected_ticker else False
    exception_identity = await _rendered_exception_identity(page, ticker=expected_ticker, stage="home_research_destination")
    after = await _screenshot(page, output_dir, f"targeted_{interaction_id}_after")
    passed = bool(clicked and destination_ok and component_ready and expected_ticker and not exception_identity)
    return JourneyStep(
        "Home report card", "click through to Research",
        "PASS" if passed else "FAIL", time.monotonic() - started, "Home",
        "Correct ticker Research context settled." if passed else settlement,
        after,
        {
            "interaction_id": interaction_id, "expected_ticker": expected_ticker,
            "actual_ticker": expected_ticker if component_ready else "",
            "expected_destination": expected_page, "actual_destination": "research-any-ticker" if destination_ok else "",
            "click_accepted": clicked, "page_ready": destination_ok,
            "expected_component_rendered": component_ready,
            "classification": "PASS" if passed else "DEAD_INTERACTION" if clicked and not destination_ok else "PRODUCT_DEFECT" if exception_identity else "QA_DEFECT",
            "severity": "" if passed else "P1", "before_screenshot": before,
            "after_screenshot": after, "rendered_exception_identity": exception_identity,
        },
    )


def _targeted_step_summary(step: JourneyStep) -> dict[str, Any]:
    """Keep targeted artifacts diagnostic but free of provider/financial payloads."""
    evidence = dict(step.evidence or {})
    canonical_summary = dict(evidence.get("canonical_research_summary") or {})
    progress = dict(evidence.get("research_progress") or {})
    progress_summary = dict(progress.get("progress_summary") or {})
    special = dict(evidence.get("special_certification") or {})
    safe = {
        "journey": step.journey, "step": step.step, "status": step.status,
        "duration_seconds": round(float(step.duration_seconds), 3), "page": step.page,
        "detail": step.detail, "screenshot": step.screenshot,
        "interaction_id": evidence.get("interaction_id"),
        "expected_ticker": evidence.get("expected_ticker"), "actual_ticker": evidence.get("actual_ticker"),
        "expected_destination": evidence.get("expected_destination"), "actual_destination": evidence.get("actual_destination"),
        "before_screenshot": evidence.get("before_screenshot"), "after_screenshot": evidence.get("after_screenshot"),
        "classification": evidence.get("classification"), "severity": evidence.get("severity"),
        "research_request_id": progress.get("request-id"), "readiness": progress.get("readiness"),
        "provider_calls": progress.get("provider-calls"), "cache_hits": progress.get("cache-hits"),
        "family_timings": progress_summary.get("family_timings") or {},
        "enrichment_status": progress_summary.get("enrichment_status"),
        "exception_identity": evidence.get("rendered_exception_identity") or {},
        "context_digest": stable_digest(canonical_summary) if canonical_summary else None,
        "decision_digest_matches": evidence.get("decision_digest_matches"),
        "invalid_provider_calls": evidence.get("provider_calls"),
        "no_investment_decision": evidence.get("no_investment_decision"),
        "etf": special.get("etf") or {},
    }
    if "tabs" in evidence:
        safe["tabs"] = evidence["tabs"]
    if "grounding" in evidence:
        grounding = evidence.get("grounding") or {}
        safe["ask_grounding"] = {
            key: grounding.get(key) for key in (
                "ticker", "context-version", "context-digest", "decision-digest",
                "evidence-used", "evidence-missing",
            )
        }
    return safe


async def run_targeted_critical_journeys(page: Page, *, output_dir: Path) -> dict[str, Any]:
    """Run exactly the six QA.4 deployed preflight journeys, stopping on failure."""
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    steps: list[JourneyStep] = []

    async def record(step: JourneyStep) -> bool:
        steps.append(step)
        return step.status == "PASS"

    async def with_screenshot_chain(name: str, operation) -> JourneyStep:
        before = await _screenshot(page, output_dir, f"targeted_{name}_before")
        step = await operation
        after = step.screenshot or await _screenshot(page, output_dir, f"targeted_{name}_after")
        evidence = dict(step.evidence or {})
        evidence.setdefault("before_screenshot", before)
        evidence.setdefault("after_screenshot", after)
        step.evidence = evidence
        step.screenshot = after
        return step

    nvda = await with_screenshot_chain("nvda_research", _research_one(page, "NVDA", output_dir))
    if not await record(nvda):
        return _targeted_result(steps, started)
    home = await _targeted_home_research(page, output_dir)
    if not await record(home):
        return _targeted_result(steps, started)
    nvda_reload = await _research_one(page, "NVDA", output_dir)
    ok = nvda_reload.status == "PASS"
    detail = nvda_reload.detail
    tabs_result = await _certify_all_tabs(page, "Research Any Ticker", output_dir, "NVDA") if ok else None
    tabs_step = JourneyStep(
        "NVDA Research tabs", "exercise every rendered tab",
        "PASS" if tabs_result and tabs_result.get("status") == "PASS" else "FAIL",
        0.0, "Research Any Ticker", "All rendered NVDA Research tabs exercised." if tabs_result else detail,
        str((tabs_result or {}).get("after_screenshot") or ""), {"tabs": (tabs_result or {}).get("tabs") or [], "before_screenshot": (tabs_result or {}).get("before_screenshot"), "after_screenshot": (tabs_result or {}).get("after_screenshot")},
    )
    if not await record(tabs_step):
        return _targeted_result(steps, started)
    ask = await with_screenshot_chain("nvda_ask", _ask_question(page, "NVDA", "Why does ATLAS like this company?", output_dir))
    if not await record(ask):
        return _targeted_result(steps, started)
    spy = await with_screenshot_chain("spy_research", _research_one(page, "SPY", output_dir))
    if not await record(spy):
        return _targeted_result(steps, started)
    invalid = await with_screenshot_chain("invalid123", _research_one(page, INVALID_TICKER, output_dir))
    await record(invalid)
    return _targeted_result(steps, started)


def _targeted_result(steps: list[JourneyStep], started: float) -> dict[str, Any]:
    summaries = [_targeted_step_summary(step) for step in steps]
    passed = sum(item["status"] == "PASS" for item in summaries)
    failed = sum(item["status"] == "FAIL" for item in summaries)
    by_journey = {item["journey"]: item for item in summaries}
    nvda = by_journey.get("Research NVDA") or {}
    home = by_journey.get("Home report card") or {}
    tab_step = by_journey.get("NVDA Research tabs") or {}
    tab_rows = list(tab_step.get("tabs") or [])
    ask = by_journey.get("Ask AI — NVDA") or {}
    ask_grounding = dict(ask.get("ask_grounding") or {})
    result = {
        "version": "QA4_TARGETED_PREFLIGHT_V1", "expected": 6,
        "attempted": len(summaries), "passed": passed, "failed": failed,
        "status": "TARGETED_PREFLIGHT_PASS" if len(summaries) == 6 and failed == 0 else "TARGETED_PREFLIGHT_FAIL",
        "total_duration_seconds": round(time.monotonic() - started, 3), "journeys": summaries,
        "nvda_perf2_waterfall": {
            key: nvda.get(key) for key in (
                "research_request_id", "readiness", "provider_calls", "cache_hits",
                "family_timings", "enrichment_status", "exception_identity",
            )
        },
        "home_interaction": {
            key: home.get(key) for key in (
                "interaction_id", "expected_ticker", "actual_ticker",
                "expected_destination", "actual_destination",
                "before_screenshot", "after_screenshot", "classification", "severity",
            )
        },
        "research_tabs": {
            "discovered": len(tab_rows), "attempted": len(tab_rows),
            "passed": sum(bool(row.get("selected") and row.get("content_rendered") and row.get("ticker_retained") and not row.get("stale_content") and not row.get("rendered_exception")) for row in tab_rows),
            "failed": sum(not bool(row.get("selected") and row.get("content_rendered") and row.get("ticker_retained") and not row.get("stale_content") and not row.get("rendered_exception")) for row in tab_rows),
            "results": tab_rows,
        },
        "ask_context_digest": {
            "research": nvda.get("context_digest"), "ask": ask_grounding.get("context-digest"),
            "matches": bool(nvda.get("context_digest") and nvda.get("context_digest") == ask_grounding.get("context-digest")),
        },
        "spy_result": by_journey.get("Research SPY") or {},
        "invalid123_result": by_journey.get(f"Research {INVALID_TICKER}") or {},
    }
    return result


async def run_user_journeys(
    page: Page,
    *,
    output_dir: Path,
    navigation_labels: Iterable[str] = PAGE_LABELS,
    prevalidated_navigation: Iterable[Mapping[str, Any]] = (),
    progress_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    steps: list[JourneyStep] = []
    started = time.monotonic()

    def publish_progress(status: str = "IN_PROGRESS") -> None:
        if progress_state is None:
            return
        values = [step.to_dict() for step in steps]
        predicates = {
            "navigation": lambda step: step["journey"] == "Navigation coverage",
            "research": lambda step: step["journey"].startswith("Research "),
            "ask": lambda step: step["journey"].startswith("Ask AI —"),
            "responsive": lambda step: step["journey"].startswith("Responsive ") or step["journey"] == "Core mobile certification",
        }
        family_completed = {}
        for family, predicate in predicates.items():
            matching = [step for step in values if predicate(step)]
            family_completed[family] = {
                "attempted": len(matching),
                "completed": sum(step["status"] == "PASS" for step in matching),
                "failed": sum(step["status"] == "FAIL" for step in matching),
            }
        family_completed["cross_page"] = {"attempted": 0, "completed": 0, "failed": 0}
        progress_state.clear()
        progress_state.update({
            "version": "ATLAS-USER-JOURNEYS-V4.0",
            "status": status,
            "steps": values,
            "counts": {state: sum(step["status"] == state for step in values) for state in ("PASS", "WARN", "FAIL")},
            "ticker_matrix": _TICKER_MATRIX,
            "stable_ask_questions": ASK_AI_QUESTIONS,
            "partial_progress": True,
            "family_completed": family_completed,
            "required_journey_completeness": journey_completeness({
                "navigation": len(tuple(navigation_labels)), "research": len(RESEARCH_TICKERS) + 1,
                "ask": len(ASK_AI_PROMPTS), "responsive": 6, "cross_page": 1,
            }, family_completed),
            "cross_page_consistency": {"status": "NOT_EXECUTED", "reason": "Journey execution is still in progress."},
        })

    # 1. Reuse the already completed architecture/inventory navigation whenever
    # available. This prevents a second 14-page traversal from consuming the
    # Research and Ask budget.
    prevalidated = list(prevalidated_navigation)
    if prevalidated:
        for result in prevalidated:
            label = str(result.get("page") or "")
            status = "PASS" if result.get("status") == "PASS" else "FAIL"
            steps.append(JourneyStep(
                "Navigation coverage", label, status,
                float(result.get("duration_seconds") or 0), label,
                "Reused bounded architecture inventory result.",
                str(result.get("screenshot") or ""),
                {"page_certification": dict(result.get("page_certification") or {})},
            ))
        publish_progress()
    else:
        navigation_deadline = time.monotonic() + GENERIC_NAVIGATION_BUDGET_SECONDS
        for label in navigation_labels:
            if time.monotonic() >= navigation_deadline:
                steps.append(JourneyStep(
                    "Navigation coverage", label, "FAIL", 0, label,
                    "Generic navigation phase budget exhausted; required Research remained reserved.",
                ))
                publish_progress()
                continue
            step_start = time.monotonic()
            ok, duration, detail = await _navigate(page, label, output_dir)
            if not ok:
                steps.append(JourneyStep("Navigation coverage", label, "FAIL", duration, label, detail))
                publish_progress()
                continue

            try:
                controls = await asyncio.wait_for(_exercise_safe_controls(page, label), timeout=3)
            except TimeoutError:
                controls = {"errors": [], "interaction_notes": ["Safe-control exercise reached its per-route budget."]}
            controls["page_certification"] = await _page_certification_metadata(page, label)
            screenshot = await _screenshot(page, output_dir, f"nav_{label}")
            status = "FAIL" if controls["errors"] else "PASS"
            steps.append(JourneyStep(
                "Navigation coverage", label, status, time.monotonic()-step_start, label,
                "; ".join(controls["errors"]) if controls["errors"] else "Page opened and safe controls were exercised.",
                screenshot, controls,
            ))
            publish_progress()

    # 2. Research journeys receive their execution opportunity before any
    # optional repeated navigation work.
    for ticker in (*RESEARCH_TICKERS, INVALID_TICKER):
        try:
            step = await asyncio.wait_for(_research_one(page, ticker, output_dir), timeout=RESEARCH_STEP_BUDGET_SECONDS)
        except TimeoutError:
            step = JourneyStep(f"Research {ticker}", "generate full research", "FAIL", RESEARCH_STEP_BUDGET_SECONDS, "Research Any Ticker", "Per-ticker Research budget exhausted.")
        steps.append(step)
        publish_progress()

    # 3. Ask AI journeys.
    for ticker, prompt in ASK_AI_PROMPTS:
        try:
            step = await asyncio.wait_for(_ask_question(page, ticker, prompt, output_dir), timeout=ASK_STEP_BUDGET_SECONDS)
        except TimeoutError:
            step = JourneyStep(f"Ask AI — {ticker}", "answer investment question", "FAIL", ASK_STEP_BUDGET_SECONDS, "Ask AI", "Per-question Ask budget exhausted.")
        steps.append(step)
        publish_progress()

    # 4. Responsive smoke after returning to Research page.
    await _navigate(page, "Research Any Ticker", output_dir)
    try:
        steps.extend(await asyncio.wait_for(_responsive_smoke(page, output_dir), timeout=45))
    except TimeoutError:
        for label in ("tablet", "mobile"):
            steps.append(JourneyStep(f"Responsive {label}", "responsive layout", "FAIL", 45, "Research Any Ticker", "Responsive phase budget exhausted."))
    publish_progress()

    # 5. Interaction-level certification. Required interactions that were not
    # attempted remain explicit and prevent a 100% certification result.
    interaction_progress: dict[str, Any] = {}
    try:
        interactions = await asyncio.wait_for(_interaction_crawler(page, output_dir, interaction_progress), timeout=60)
    except TimeoutError:
        registry = interaction_progress.get("registry") or interaction_registry()
        completed_results = list(interaction_progress.get("results") or [])
        interactions = {
            "registry": registry, "results": completed_results,
            "coverage": interaction_coverage(registry, completed_results),
            "tab_inventory": dict(interaction_progress.get("tab_inventory") or {}),
            "status": "QA_WAIT_DEFECT",
        }
    publish_progress()
    try:
        steps.extend(await asyncio.wait_for(_core_mobile_certification(page, output_dir), timeout=30))
    except TimeoutError:
        for label in ("Home", "Today's Opportunities", "Research Any Ticker", "Ask AI"):
            steps.append(JourneyStep("Core mobile certification", label, "FAIL", 30, label, "Core mobile phase budget exhausted."))
    publish_progress()

    values = [step.to_dict() for step in steps]
    counts = {
        status: sum(step["status"] == status for step in values)
        for status in ("PASS", "WARN", "FAIL")
    }
    performance = {
        "total_seconds": round(time.monotonic()-started, 2),
        "slow_steps": sorted(
            [
                {"journey": step["journey"], "step": step["step"], "seconds": step["duration_seconds"]}
                for step in values
                if step["duration_seconds"] >= 8
            ],
            key=lambda item: item["seconds"],
            reverse=True,
        ),
    }
    cross_page = {}
    for step in values:
        marker = (step.get("evidence") or {}).get("page_certification") or {}
        if marker.get("ticker") == CURRENT_TOP15_TICKER and marker.get("decision_digest"):
            cross_page[step.get("page") or step.get("step")] = marker.get("decision_digest")
    cross_page_result = cross_page_digest_result(CURRENT_TOP15_TICKER, cross_page)
    selectors = {
        "navigation": lambda step: step["journey"] == "Navigation coverage",
        "research": lambda step: step["journey"].startswith("Research "),
        "ask": lambda step: step["journey"].startswith("Ask AI —"),
        "responsive": lambda step: step["journey"].startswith("Responsive ") or step["journey"] == "Core mobile certification",
    }
    family_completed = {}
    for family, predicate in selectors.items():
        matching = [step for step in values if predicate(step)]
        family_completed[family] = {
            "attempted": len(matching),
            "completed": sum(step["status"] == "PASS" for step in matching),
            "failed": sum(step["status"] == "FAIL" for step in matching),
        }
    family_completed["cross_page"] = {
        "attempted": 1, "completed": 1 if cross_page_result["status"] == "PASS" else 0,
        "failed": 0 if cross_page_result["status"] == "PASS" else 1,
    }
    completeness = journey_completeness({
        "navigation": len(tuple(navigation_labels)), "research": len(RESEARCH_TICKERS) + 1,
        "ask": len(ASK_AI_PROMPTS), "responsive": 6, "cross_page": 1,
    }, family_completed)
    result = {
        "version": "ATLAS-USER-JOURNEYS-V4.0",
        "status": "PASS" if counts["FAIL"] == 0 else "FAIL",
        "counts": counts,
        "steps": values,
        "performance": performance,
        "ticker_matrix": _TICKER_MATRIX,
        "stable_ask_questions": ASK_AI_QUESTIONS,
        "required_journey_completeness": completeness,
        "cross_page_consistency": cross_page_result,
        "interaction_certification": interactions,
    }
    if progress_state is not None:
        progress_state.clear()
        progress_state.update(result)
        progress_state["partial_progress"] = False
    return result


__all__ = [
    "ASK_AI_PROMPTS", "ASK_AI_QUESTIONS", "INVALID_TICKER", "PAGE_LABELS",
    "PAGE_READY_TEXT", "RESEARCH_TICKERS", "ask_grounding_complete",
    "navigation_contract_satisfied", "research_context_complete", "run_user_journeys",
    "page_identity_settled", "page_certification_metadata", "run_targeted_critical_journeys",
    "wait_for_page_settlement",
]
