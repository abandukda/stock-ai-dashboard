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

from agents.atlas_runtime_qa_v3 import _open_and_authenticate
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


VISUAL_CRAWLER_VERSION = "ATLAS_VISUAL_CRAWLER_V1_1"
DESKTOP = {"width": 1440, "height": 1000}
MOBILE = {"width": 390, "height": 844}
GLOBAL_FATALS = {"APP_UNREACHABLE", "AUTHENTICATION_FAILED", "BROWSER_DIED"}
MOBILE_PAGES = (
    "Home", "Research Any Ticker", "Today's Opportunities", "Ask AI",
    "Political Intelligence",
)
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
    "Recovery": ("Recovery",),
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


class GlobalCrawlFailure(RuntimeError):
    def __init__(self, category: str) -> None:
        super().__init__(category)
        self.category = category


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
        self.authentication: dict[str, Any] = {}
        self.ticker_matrix = full_certification_ticker_matrix(root)
        self._shot_number = 0
        self.research_contexts: dict[str, dict[str, str]] = {}

    def _source_sha(self) -> str:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=self.root, text=True,
        ).strip()

    async def _shot(
        self, page: Page, *, page_name: str, interaction: str, state: str,
        viewport: str = "desktop", ticker: str = "", complete_surface: bool = False,
    ) -> str:
        self._shot_number += 1
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", f"{self._shot_number:04d}_{viewport}_{page_name}_{interaction}_{state}")
        path = self.screenshot_dir / f"{slug[:180]}.png"
        try:
            metadata: dict[str, Any] = {"capture": "viewport", "segments": 1, "complete": True}
            last_error: Exception | None = None
            for attempt in range(3):
                try:
                    if complete_surface:
                        metadata = await self._stitched_streamlit_screenshot(page, path)
                    else:
                        await page.screenshot(path=str(path), full_page=False)
                    last_error = None
                    break
                except Exception as exc:
                    last_error = exc
                    await page.wait_for_timeout(150 * (attempt + 1))
            if last_error is not None:
                await page.screenshot(path=str(path), full_page=False)
                metadata = {"capture": "viewport_fallback", "segments": 1, "complete": False}
            relative = str(path.relative_to(self.output_dir))
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
    ) -> VisualResult:
        result = VisualResult(
            category=category, page=page_name, interaction=interaction,
            expected=expected, observed=observed,
            status="PASS" if passed else "FAIL",
            severity="NONE" if passed else (severity or "P2"),
            elapsed_seconds=round(elapsed, 3), ticker_context=ticker,
            viewport=viewport, screenshots=[item for item in screenshots if item],
            exception=exception or {},
        )
        self.results.append(result)
        self._write_artifacts(final=False)
        return result

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
            visible, visible_detail = await self._visible_primary(page, page_name)
            rendered_exception = await _has_rendered_exception(page)
            route_current = await self._current_route_visible(page, page_name)
            if not settled and route_current and visible and not rendered_exception:
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

    async def _current_route_visible(self, page: Page, page_name: str) -> bool:
        """Prefer the current radio selection over stale lifecycle nodes from old reruns."""
        for scope in _scopes(page):
            try:
                radio = scope.get_by_role("radio", name=page_name, exact=True)
                if await radio.count() and await radio.first.is_checked():
                    return True
            except Exception:
                continue
        text = await _visible_text(page)
        return page_name.lower() in text.lower()

    async def _click_tabs(self, page: Page, *, page_name: str, ticker: str = "", viewport: str = "desktop") -> None:
        tabs: list[str] = []
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
                await tab.click(timeout=6000)
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
                after = await self._shot(page, page_name=page_name, interaction=f"tab-{name}", state="after", viewport=viewport, ticker=ticker)
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
                    expected="Tab is independently operable", observed=type(exc).__name__,
                    passed=False, elapsed=time.monotonic() - started, ticker=ticker,
                    viewport=viewport, screenshots=(before, after), severity="P2",
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
        controls = await tab.get_attribute("aria-controls")
        if controls:
            panel = page.locator(f'#{controls}')
            if await panel.count() and (await panel.first.inner_text()).strip():
                return True
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
                expanded = (await node.get_attribute("aria-expanded")) != "false"
                exception = await _has_rendered_exception(page)
                after = await self._shot(page, page_name=page_name, interaction=f"expander-{name}", state="after", viewport=viewport)
                await self._record(
                    category="EXPANDER", page_name=page_name, interaction=name,
                    expected="Important expander opens with visible content",
                    observed=f"expanded={expanded}; exception={exception}",
                    passed=expanded and not exception, elapsed=time.monotonic() - started,
                    viewport=viewport, screenshots=(before, after),
                    exception=await self._exception_identity(page) if exception else {},
                )
                if expanded:
                    await node.click(timeout=3000)
            except Exception as exc:
                await self._record(
                    category="EXPANDER", page_name=page_name, interaction=name,
                    expected="Expander remains independently operable", observed=type(exc).__name__,
                    passed=False, elapsed=time.monotonic() - started, viewport=viewport,
                    screenshots=(before,), severity="P3",
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
        await self._page_visit(page, "Research Any Ticker", viewport=viewport)
        before = await self._shot(page, page_name="Research Any Ticker", interaction=f"submit-{ticker}", state="before", viewport=viewport, ticker=ticker)
        try:
            input_node = None
            button = None
            for scope in _scopes(page):
                inputs = scope.get_by_label("Ticker", exact=True)
                if not await inputs.count():
                    inputs = scope.locator('input[placeholder*="NVDA"]')
                buttons = scope.get_by_role("button", name="Research ticker", exact=True)
                if await inputs.count() and await buttons.count():
                    input_node, button = inputs.first, buttons.first
                    break
            if input_node is None or button is None:
                raise RuntimeError("VISIBLE_RESEARCH_CONTROLS_MISSING")
            await input_node.fill(ticker)
            await button.click()
            deadline = time.monotonic() + 45
            text = ""
            while time.monotonic() < deadline:
                text = await _visible_text(page)
                if ticker == "INVALID123":
                    if re.search(r"invalid|unavailable|not found", text, re.I):
                        break
                elif await self._exact_research_ticker(page, ticker):
                    break
                await page.wait_for_timeout(400)
            exception = await _has_rendered_exception(page)
            displayed = await self._exact_research_ticker(page, ticker) if ticker != "INVALID123" else False
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
            after = await self._shot(page, page_name="Research Any Ticker", interaction=f"submit-{ticker}", state="after", viewport=viewport, ticker=ticker, complete_surface=ticker != "INVALID123")
            await self._record(
                category="RESEARCH", page_name="Research Any Ticker", interaction="submit",
                expected=f"Visible Research result and exact ticker {ticker}",
                observed=f"ticker_visible={displayed}; safe_invalid={safe_invalid}; no_stale_ticker={no_stale_ticker}; exception={exception}",
                passed=passed, elapsed=time.monotonic() - started, ticker=ticker,
                viewport=viewport, screenshots=(before, after), severity="P1",
                exception=await self._exception_identity(page) if exception else {},
            )
            if passed and tabs and ticker != "INVALID123":
                await self._click_tabs(page, page_name="Research Any Ticker", ticker=ticker, viewport=viewport)
            return passed
        except Exception as exc:
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
        await self._open_buy_now_expander(page)
        unique = await self._discover_visible_home_cards(page)
        indexes = sorted(set((0, len(unique) // 2, len(unique) - 1))) if unique else []
        for index in indexes:
            interaction_id, ticker = unique[index]
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
        """Discover actual visible BUY NOW CTAs, not hidden marker inventory."""
        cards: list[tuple[str, str]] = []
        seen: set[str] = set()
        for scope in _scopes(page):
            try:
                buttons = scope.get_by_role("button", name=re.compile(r"Open Full Research", re.I))
                for index in range(await buttons.count()):
                    button = buttons.nth(index)
                    if not await button.is_visible():
                        continue
                    marker = button.locator("xpath=preceding::*[@data-atlas-interaction-id][1]")
                    if not await marker.count():
                        continue
                    interaction_id = await marker.first.get_attribute("data-atlas-interaction-id") or ""
                    ticker = (await marker.first.get_attribute("data-atlas-expected-ticker") or "").upper()
                    if not interaction_id or not ticker or ticker in seen:
                        continue
                    card_text = ""
                    for test_id in ("stHorizontalBlock", "stVerticalBlock"):
                        card = button.locator(f"xpath=ancestor::*[@data-testid='{test_id}'][1]")
                        if await card.count():
                            card_text += " " + await card.first.inner_text()
                    if "BUY NOW" not in card_text.upper():
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
                buttons = scope.get_by_role("button", name=re.compile(r"Open Full Research", re.I))
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
            grounded = ticker_match and metadata_present and visible_evidence
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

    async def _desktop(self, page: Page) -> None:
        await page.set_viewport_size(DESKTOP)
        for page_name in ACTIVE_PAGES:
            await self._page_visit(page, page_name)
            if page_name in {"Earnings Intelligence", "Political Intelligence"}:
                await self._click_expanders(page, page_name=page_name)
                await self._supporting_evidence(page, page_name=page_name)
        await self._home_cards(page)
        roles = self.ticker_matrix.get("role_tickers", {})
        minimum = ["NVDA", roles.get("top_idea"), roles.get("home_first"), roles.get("home_middle"), roles.get("home_last"), roles.get("etf") or "SPY", roles.get("missing_production"), "INVALID123"]
        tickers = list(dict.fromkeys(ticker for ticker in [*minimum, *self.ticker_matrix.get("top15", [])] if ticker))
        deep = set(ticker for ticker in minimum if ticker and ticker != "INVALID123")
        for ticker in tickers:
            await self._submit_research(page, ticker, tabs=ticker in deep)
        await self._ask(page)

    async def _mobile(self, page: Page) -> None:
        await page.set_viewport_size(MOBILE)
        for page_name in MOBILE_PAGES:
            await self._page_visit(page, page_name, viewport="mobile")
            if page_name == "Home":
                await self._home_cards(page, viewport="mobile")
            elif page_name == "Research Any Ticker":
                await self._submit_research(page, "NVDA", tabs=True, viewport="mobile")
            elif page_name == "Ask AI":
                await self._ask(page, viewport="mobile")
            elif page_name == "Political Intelligence":
                await self._click_expanders(page, page_name=page_name, viewport="mobile")
                await self._supporting_evidence(page, page_name=page_name, viewport="mobile")

    async def run(self) -> dict[str, Any]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        async with async_playwright() as pw:
            browser: Browser = await pw.chromium.launch(headless=self.headless)
            context: BrowserContext = await browser.new_context(viewport=DESKTOP)
            page = await context.new_page()
            try:
                try:
                    self.authentication = await _open_and_authenticate(
                        page, self.url, self.output_dir, expected_sha=self.source_sha,
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
                await self._desktop(page)
                await self._mobile(page)
            finally:
                await context.close()
                await browser.close()
        return self._write_artifacts(final=True)

    def _summary(self, *, final: bool) -> dict[str, Any]:
        def counts(category: str) -> dict[str, int]:
            rows = [row for row in self.results if row.category == category]
            return {"attempted": len(rows), "passed": sum(row.status == "PASS" for row in rows), "failed": sum(row.status == "FAIL" for row in rows)}
        all_counts = {"attempted": len(self.results), "passed": sum(row.status == "PASS" for row in self.results), "failed": sum(row.status == "FAIL" for row in self.results)}
        expected_shots = len(self.manifest)
        generated_shots = sum(bool(item.get("generated")) for item in self.manifest)
        return {
            "version": VISUAL_CRAWLER_VERSION, "source_sha": self.source_sha,
            "started_at": self.started_at, "finished": final,
            "duration_seconds": round(time.monotonic() - self.started, 3),
            "authentication_success": bool(self.authentication),
            "counts": {
                "all": all_counts, "pages": counts("PAGE"),
                "interactions": {
                    "attempted": all_counts["attempted"] - counts("PAGE")["attempted"],
                    "passed": all_counts["passed"] - counts("PAGE")["passed"],
                    "failed": all_counts["failed"] - counts("PAGE")["failed"],
                },
                "research_tickers": counts("RESEARCH"), "tabs": counts("TAB"),
                "screenshots": {"expected": expected_shots, "generated": generated_shots, "missing": expected_shots - generated_shots},
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
        columns = ["category", "page", "ticker_context", "interaction", "expected", "observed", "status", "severity", "elapsed_seconds", "viewport", "screenshots", "exception"]
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
        summary = await crawler.run()
    except GlobalCrawlFailure as exc:
        crawler._write_artifacts(final=True)
        print(json.dumps({"status": exc.category, "artifact": str(Path(args.output) / "atlas_visual_qa_summary.json")}, sort_keys=True))
        return 3
    failed = int(summary["counts"]["all"]["failed"])
    print(json.dumps({"status": "PASS" if not failed else "COMPLETE_WITH_DEFECTS", "failures": failed, "artifact": str(Path(args.output) / "atlas_visual_qa_summary.json")}, sort_keys=True))
    return 0 if not failed else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", default="atlas_visual_qa_v1")
    parser.add_argument("--root", default=".")
    parser.add_argument("--headed", action="store_true")
    return asyncio.run(_async_main(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
