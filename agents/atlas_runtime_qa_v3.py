"""Atlas Runtime QA v3.1 — authenticated one-shot browser audit.

Primary goals:
- Reliably authenticate through Streamlit's password-only login, including
  delayed/iframe-rendered login forms.
- Refuse to report a healthy audit when the authenticated dashboard was not reached.
- Discover navigation from the rendered application rather than assuming one selector.
- Record exact failing network URLs and statuses.
- Save partial reports continuously and always produce actionable artifacts.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time
import traceback
from typing import Any, Iterable

from playwright.async_api import BrowserContext, Frame, Locator, Page, async_playwright

from agents.ai_content_integrity_v3 import audit_summary_collection
from agents.code_contract_mapper_v3 import build_code_contract
from agents.fix_planner_v3 import write_fix_plan
from agents.qa_v3_models import PageResult, QAIssue


DEFAULT_URL = "https://stock-ai-dashboard.streamlit.app"
PAGE_TIMEOUT_MS = 35_000
ACTION_TIMEOUT_MS = 6_000
LOGIN_TIMEOUT_SECONDS = 240
TOTAL_TIMEOUT_SECONDS = 900

KNOWN_NAV_LABELS = (
    "Home",
    "Today's Opportunities",
    "Top AI Ideas",
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

SUMMARY_HEADING = re.compile(
    r"atlas perspective|executive summary|ai summary|atlas summary|"
    r"why atlas is interested|why it is interesting|investment thesis|ai interpretation",
    re.I,
)
CARD_START_HEADING = re.compile(r"^(?:atlas perspective|executive summary)$", re.I)
CARD_STOP_HEADINGS = {
    "Why it is interesting", "Why Atlas is interested", "What Atlas is watching",
    "Open complete Atlas research", "Atlas Rating", "Opportunity", "Confidence",
    "Today's Move", "Relative Volume", "Dollar Volume", "Expected Return",
    "Atlas Target", "Evidence Coverage", "Suggested Position",
}
INVALID_SUMMARY_IDENTIFIERS = {
    "AI", "NO", "YES", "BUY", "NOW", "ETF", "EPS", "RSI", "HOME", "TODAY",
    "ASK", "ATLAS", "FULL", "TOP", "CORE", "WATCHLIST", "RECOVERY",
    "POLITICAL", "DEVELOPER", "CENTER", "EARNINGS", "VOLUME", "RESEARCH",
    "PORTFOLIO", "INTELLIGENCE", "SUMMARY", "MONITOR", "ACCUMULATE", "AVOID",
}
VALID_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.-]{0,5}$")
ERROR_TEXT = re.compile(
    r"traceback|modulenotfounderror|streamlitapiexception|uncaught exception",
    re.I,
)
MISSING_TEXT = re.compile(
    r"\b(?:nan|not loaded|under review|data unavailable|no data available)\b",
    re.I,
)


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _scope_name(scope: Page | Frame) -> str:
    return "page" if isinstance(scope, Page) else f"frame:{scope.url or 'unknown'}"


def _all_scopes(page: Page) -> list[Page | Frame]:
    scopes: list[Page | Frame] = [page]
    scopes.extend(frame for frame in page.frames if frame != page.main_frame)
    return scopes


async def _safe_count(locator: Locator) -> int:
    try:
        return await locator.count()
    except Exception:
        return 0


async def _safe_text(scope: Page | Frame, timeout: int = 2500) -> str:
    try:
        return await scope.locator("body").inner_text(timeout=timeout)
    except Exception:
        return ""


async def _combined_visible_text(page: Page) -> str:
    chunks = []
    for scope in _all_scopes(page):
        value = await _safe_text(scope)
        if value:
            chunks.append(value)
    return "\n".join(chunks)


async def _wait_for_streamlit_shell(page: Page) -> None:
    for _ in range(30):
        if page.is_closed():
            raise RuntimeError("Browser page closed before Streamlit loaded.")
        text = await _combined_visible_text(page)
        if text or len(page.frames) > 1:
            return
        await page.wait_for_timeout(500)


async def _wake_if_needed(page: Page) -> None:
    for _ in range(3):
        body = await _combined_visible_text(page)
        if not re.search(r"sleep|hibernat|get this app back up|wake app", body, re.I):
            return
        for scope in _all_scopes(page):
            button = scope.get_by_role(
                "button",
                name=re.compile(r"wake|get this app back up|rerun", re.I),
            )
            if await _safe_count(button):
                await button.first.click(timeout=ACTION_TIMEOUT_MS)
                await page.wait_for_timeout(7000)
                break


async def _find_password_target(
    page: Page,
) -> tuple[Page | Frame, Locator] | None:
    selectors = (
        lambda scope: scope.locator('input[type="password"]'),
        lambda scope: scope.get_by_label(re.compile(r"^password$", re.I)),
        lambda scope: scope.locator('input[aria-label*="password" i]'),
        lambda scope: scope.locator('input[placeholder*="password" i]'),
        lambda scope: scope.locator('[data-testid="stTextInput"] input'),
    )
    for scope in _all_scopes(page):
        for build in selectors:
            locator = build(scope)
            if await _safe_count(locator):
                try:
                    if await locator.first.is_visible(timeout=800):
                        return scope, locator.first
                except Exception:
                    continue
    return None


async def _known_navigation_visible(page: Page) -> list[str]:
    found: list[str] = []
    for label in KNOWN_NAV_LABELS:
        for scope in _all_scopes(page):
            candidates = (
                scope.get_by_role("radio", name=label, exact=True),
                scope.get_by_role("button", name=label, exact=True),
                scope.get_by_role("tab", name=label, exact=True),
                scope.get_by_text(label, exact=True),
            )
            matched = False
            for locator in candidates:
                if await _safe_count(locator):
                    matched = True
                    break
            if matched:
                found.append(label)
                break
    return list(dict.fromkeys(found))


async def _submit_login(
    page: Page,
    scope: Page | Frame,
    password_target: Locator,
    password: str,
) -> None:
    await password_target.fill(password)

    login_candidates = (
        scope.get_by_role("button", name=re.compile(r"^login$", re.I)),
        scope.get_by_role(
            "button",
            name=re.compile(r"log in|sign in|continue|enter|access", re.I),
        ),
        scope.locator('button[type="submit"]'),
    )
    for locator in login_candidates:
        if await _safe_count(locator):
            try:
                await locator.first.click(timeout=ACTION_TIMEOUT_MS)
                return
            except Exception:
                continue
    await password_target.press("Enter")


async def _authenticate_and_confirm(page: Page, output_dir: Path) -> dict[str, Any]:
    password = (
        os.getenv("ATLAS_AUDIT_PASSWORD")
        or os.getenv("GUEST_PASSWORD")
        or os.getenv("VIEWER_PASSWORD")
        or os.getenv("VIEW_PASSWORD")
        or ""
    ).strip()
    if len(password) >= 2 and password[0] == password[-1] and password[0] in {"\"", "'"}:
        password = password[1:-1].strip()
    started = time.monotonic()
    diagnostics: dict[str, Any] = {
        "password_field_detected": False,
        "password_submitted": False,
        "authenticated_dashboard_detected": False,
        "navigation_labels": [],
        "frames_seen": [],
        "configured_secret_length": len(password),
        "poll_count": 0,
    }

    while time.monotonic() - started < LOGIN_TIMEOUT_SECONDS:
        diagnostics["poll_count"] += 1
        elapsed = round(time.monotonic() - started, 1)
        if diagnostics["poll_count"] == 1 or diagnostics["poll_count"] % 14 == 0:
            print(f"[login] Waiting for login/dashboard ({elapsed}s elapsed)...", flush=True)
        diagnostics["frames_seen"] = [frame.url for frame in page.frames]

        nav = await _known_navigation_visible(page)
        if nav:
            diagnostics["authenticated_dashboard_detected"] = True
            diagnostics["navigation_labels"] = nav
            print(f"[login] Authenticated dashboard confirmed with {len(nav)} nav labels.", flush=True)
            return diagnostics

        target = await _find_password_target(page)
        if target is not None:
            diagnostics["password_field_detected"] = True
            if not password:
                raise RuntimeError(
                    "ATLAS_AUDIT_PASSWORD is missing. Configure the GitHub repository "
                    "secret with the guest/view-only password."
                )
            if not diagnostics["password_submitted"]:
                scope, locator = target
                print(f"[login] Password field found in {_scope_name(scope)}.", flush=True)
                await _submit_login(page, scope, locator, password)
                diagnostics["password_submitted"] = True
                print("[login] Password submitted; waiting for Streamlit rerun...", flush=True)
                await page.wait_for_timeout(5000)
                continue

            visible = await _combined_visible_text(page)
            configured_lengths = [int(value) for value in re.findall(r"length:\s*(\d+)", visible, re.I)]
            diagnostics["configured_password_lengths_seen"] = configured_lengths
            if configured_lengths and len(password) not in configured_lengths:
                raise RuntimeError(
                    f"ATLAS_AUDIT_PASSWORD length {len(password)} does not match any "
                    f"configured viewer password length displayed by Atlas: {configured_lengths}."
                )
            if re.search(r"invalid password|incorrect password|login failed", visible, re.I):
                raise RuntimeError(
                    "Atlas rejected ATLAS_AUDIT_PASSWORD. Confirm the GitHub secret "
                    "matches the Streamlit guest/view-only password."
                )

        await page.wait_for_timeout(750)

    diagnostics["navigation_labels"] = await _known_navigation_visible(page)
    visible = await _combined_visible_text(page)
    (output_dir / "login_diagnostics.json").write_text(
        json.dumps(
            {
                **diagnostics,
                "visible_text_preview": visible[:5000],
                "page_url": page.url,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    try:
        await page.screenshot(
            path=str(output_dir / "login_failure.png"),
            full_page=False,
            timeout=5000,
        )
    except Exception:
        pass
    raise RuntimeError(
        "Authenticated Atlas dashboard was not reached within the login timeout. "
        "See login_diagnostics.json and login_failure.png."
    )


async def _open_and_authenticate(
    page: Page,
    url: str,
    output_dir: Path,
) -> dict[str, Any]:
    print(f"[open] Opening {url}", flush=True)
    await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
    await _wait_for_streamlit_shell(page)
    await _wake_if_needed(page)
    return await _authenticate_and_confirm(page, output_dir)


async def _discover_navigation(page: Page, expected_pages: Iterable[str]) -> list[str]:
    discovered = await _known_navigation_visible(page)

    # Include expected code-contract labels only when they are rendered.
    for label in expected_pages:
        if label in discovered:
            continue
        for scope in _all_scopes(page):
            if await _safe_count(scope.get_by_text(label, exact=True)):
                discovered.append(label)
                break

    # Streamlit radio controls expose labels through input/label structures.
    for scope in _all_scopes(page):
        radios = scope.locator('[role="radiogroup"] [role="radio"], input[type="radio"]')
        for index in range(min(await _safe_count(radios), 40)):
            try:
                label = _clean(
                    await radios.nth(index).get_attribute("aria-label")
                    or await radios.nth(index).inner_text()
                )
                if label and label not in discovered:
                    discovered.append(label)
            except Exception:
                continue

    ordered = [label for label in KNOWN_NAV_LABELS if label in discovered]
    ordered.extend(label for label in discovered if label not in ordered)
    return ordered


async def _click_navigation(page: Page, label: str) -> None:
    for scope in _all_scopes(page):
        candidates = (
            scope.get_by_role("radio", name=label, exact=True),
            scope.get_by_role("button", name=label, exact=True),
            scope.get_by_role("tab", name=label, exact=True),
            scope.get_by_text(label, exact=True),
        )
        for locator in candidates:
            if await _safe_count(locator):
                try:
                    await locator.first.click(timeout=ACTION_TIMEOUT_MS)
                    await page.wait_for_timeout(900)
                    return
                except Exception:
                    continue
    raise RuntimeError(f"Navigation control not clickable: {label}")


def _page_issues(page_name: str, text: str) -> list[QAIssue]:
    """Report only actionable page-level defects.

    A single legitimate "Under review" field or evidence limitation is not a
    page defect. Repeated generic fallback language is reported only when it is
    unusually frequent on the same page.
    """
    issues: list[QAIssue] = []
    if ERROR_TEXT.search(text):
        issues.append(QAIssue(
            severity="CRITICAL",
            category="Rendered Error",
            page=page_name,
            element="Visible page content",
            expected="No traceback or uncaught application exception.",
            actual="Rendered exception text was detected.",
            recommendation="Inspect the active page renderer and its imports.",
            likely_files=["app.py"],
        ))

    generic_limitations = len(re.findall(
        r"some financial evidence remains incomplete",
        text,
        flags=re.I,
    ))
    if generic_limitations >= 3:
        issues.append(QAIssue(
            severity="MEDIUM",
            category="Repeated Generic Limitation",
            page=page_name,
            element="Stock-card caution language",
            expected=(
                "Missing evidence is identified by ticker and component rather than "
                "one repeated generic fallback sentence."
            ),
            actual=(
                f"The same generic financial-evidence limitation appears "
                f"{generic_limitations} times."
            ),
            recommendation=(
                "Render ticker-specific missing components or suppress the generic "
                "fallback when no actionable detail is available."
            ),
            likely_files=[
                "engines/atlas_research_builder_v2.py",
                "ui/research_report_v2.py",
            ],
        ))
    return issues


async def _visual_layout_issues(page: Page, page_name: str) -> list[QAIssue]:
    """Inspect rendered DOM geometry and typography for professional UI defects."""
    findings: list[dict[str, Any]] = []
    for scope in _all_scopes(page):
        try:
            values = await scope.locator("body").evaluate(
                """
                () => {
                  const visible = (el) => {
                    const s = getComputedStyle(el);
                    const r = el.getBoundingClientRect();
                    return s.display !== 'none' && s.visibility !== 'hidden'
                      && Number(s.opacity || 1) > 0 && r.width > 2 && r.height > 2;
                  };
                  const result = [];

                  document.querySelectorAll('[data-atlas-qa="narrative"]').forEach((el) => {
                    if (!visible(el)) return;
                    const base = getComputedStyle(el);
                    const code = el.querySelectorAll('code, pre');
                    if (code.length) {
                      result.push({
                        kind: 'UNEXPECTED_INLINE_CODE',
                        name: el.dataset.atlasQaName || 'narrative',
                        detail: `${code.length} code/pre element(s) found inside ordinary prose`,
                        severity: 'HIGH'
                      });
                    }
                    [...el.querySelectorAll('*')].forEach((child) => {
                      if (!visible(child)) return;
                      const style = getComputedStyle(child);
                      const highlighted =
                        style.backgroundColor !== 'rgba(0, 0, 0, 0)' &&
                        style.backgroundColor !== 'transparent';
                      const monospace = /mono|courier/i.test(style.fontFamily);
                      if (highlighted || monospace) {
                        result.push({
                          kind: 'TYPOGRAPHY_INCONSISTENCY',
                          name: el.dataset.atlasQaName || 'narrative',
                          detail: `child uses ${style.fontFamily} with background ${style.backgroundColor}`,
                          severity: 'HIGH'
                        });
                      }
                    });
                    if (el.scrollWidth > el.clientWidth + 4) {
                      result.push({
                        kind: 'NARRATIVE_HORIZONTAL_OVERFLOW',
                        name: el.dataset.atlasQaName || 'narrative',
                        detail: `scrollWidth ${el.scrollWidth}px exceeds ${el.clientWidth}px`,
                        severity: 'HIGH'
                      });
                    }
                  });

                  const cards = [...document.querySelectorAll('[data-atlas-qa="trade-card"]')]
                    .filter(visible);
                  cards.forEach((card) => {
                    const value = card.querySelector('.atlas-trade-value');
                    if (!value) return;
                    const rect = value.getBoundingClientRect();
                    const style = getComputedStyle(value);
                    const lineHeight = parseFloat(style.lineHeight) || parseFloat(style.fontSize) * 1.2;
                    const lines = Math.max(1, Math.round(rect.height / lineHeight));
                    const text = (value.innerText || '').trim();

                    if (lines >= 3 || (text.length >= 5 && rect.width < 65)) {
                      result.push({
                        kind: 'VERTICAL_CHARACTER_WRAP',
                        name: card.dataset.atlasQaName || 'trade-card',
                        detail: `"${text}" rendered across approximately ${lines} lines in ${Math.round(rect.width)}px`,
                        severity: 'CRITICAL'
                      });
                    }
                    if (value.scrollWidth > value.clientWidth + 4) {
                      result.push({
                        kind: 'CARD_TEXT_OVERFLOW',
                        name: card.dataset.atlasQaName || 'trade-card',
                        detail: `"${text}" overflows by ${value.scrollWidth - value.clientWidth}px`,
                        severity: 'HIGH'
                      });
                    }
                  });

                  if (cards.length >= 3) {
                    const heights = cards.map((card) => Math.round(card.getBoundingClientRect().height));
                    const min = Math.min(...heights);
                    const max = Math.max(...heights);
                    if (max - min > 35) {
                      result.push({
                        kind: 'INCONSISTENT_CARD_HEIGHTS',
                        name: 'trade-plan-grid',
                        detail: `card heights range from ${min}px to ${max}px`,
                        severity: 'MEDIUM'
                      });
                    }
                  }

                  document.querySelectorAll('[data-testid="stMetricValue"]').forEach((el) => {
                    if (!visible(el)) return;
                    const rect = el.getBoundingClientRect();
                    const text = (el.innerText || '').trim();
                    const style = getComputedStyle(el);
                    const lineHeight = parseFloat(style.lineHeight) || parseFloat(style.fontSize) * 1.2;
                    const lines = Math.max(1, Math.round(rect.height / lineHeight));
                    if (text.length >= 5 && lines >= 3) {
                      result.push({
                        kind: 'METRIC_VERTICAL_WRAP',
                        name: text.slice(0, 50),
                        detail: `metric value rendered across approximately ${lines} lines`,
                        severity: 'CRITICAL'
                      });
                    }
                  });

                  return result;
                }
                """
            )
            if isinstance(values, list):
                findings.extend(item for item in values if isinstance(item, dict))
        except Exception:
            continue

    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in findings:
        key = (str(item.get("kind")), str(item.get("name")), str(item.get("detail")))
        unique[key] = item

    issues: list[QAIssue] = []
    for item in unique.values():
        kind = str(item.get("kind") or "VISUAL_LAYOUT")
        name = str(item.get("name") or "Rendered component")
        detail = str(item.get("detail") or "Visual defect detected.")
        severity = str(item.get("severity") or "MEDIUM")
        issues.append(QAIssue(
            severity=severity,
            category="Visual Formatting",
            page=page_name,
            element=name,
            expected=(
                "Text remains horizontally readable, cards remain aligned, and "
                "ordinary prose uses consistent typography without code-style highlights."
            ),
            actual=f"{kind}: {detail}",
            recommendation=(
                "Inspect the component CSS and renderer. Prevent break-all wrapping, "
                "use responsive minimum widths, remove Markdown backticks from prose, "
                "and enforce inherited typography."
            ),
            likely_files=[
                "ui/research_report_v2.py",
                "agents/atlas_runtime_qa_v3.py",
            ],
            evidence={"visual_rule": kind, "component": name, "detail": detail},
            regression_test="Run DOM geometry and typography checks at desktop and mobile widths.",
        ))
    return issues


async def _inventory(page: Page, page_name: str, output_dir: Path | None = None) -> PageResult:
    started = time.monotonic()
    text = await _combined_visible_text(page)
    issues = _page_issues(page_name, text)
    issues.extend(await _visual_layout_issues(page, page_name))

    metrics = tables = charts = buttons = tabs = expanders = 0
    for scope in _all_scopes(page):
        metrics += await _safe_count(scope.locator('[data-testid="stMetric"]'))
        tables += await _safe_count(
            scope.locator('[data-testid="stDataFrame"], [data-testid="stTable"], table')
        )
        charts += await _safe_count(
            scope.locator(
                '[data-testid="stPlotlyChart"], [data-testid="stVegaLiteChart"], '
                'canvas, svg.main-svg'
            )
        )
        buttons += await _safe_count(scope.get_by_role("button"))
        tabs += await _safe_count(scope.locator('[role="tab"]'))
        expanders += await _safe_count(scope.locator('[data-testid="stExpander"]'))

    if output_dir is not None:
        try:
            safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", page_name).strip("_") or "page"
            await page.screenshot(
                path=str(output_dir / f"visual_{safe_name}.png"),
                full_page=True,
            )
        except Exception:
            pass

    return PageResult(
        page=page_name,
        status="FAIL" if any(issue.severity == "CRITICAL" for issue in issues) else "PASS",
        duration_seconds=round(time.monotonic() - started, 2),
        visible_text=text[:50000],
        metrics=metrics,
        tables=tables,
        charts=charts,
        buttons=buttons,
        tabs=tabs,
        expanders=expanders,
        issues=[issue.to_dict() for issue in issues],
    )


def _is_valid_summary_ticker(value: str) -> bool:
    ticker = str(value or "").strip().upper()
    return bool(
        VALID_TICKER_RE.fullmatch(ticker)
        and ticker not in INVALID_SUMMARY_IDENTIFIERS
        and ticker not in {label.upper() for label in KNOWN_NAV_LABELS}
    )


def _nearest_ticker(lines: list[str], heading_index: int) -> str:
    """Find the ticker belonging to the card immediately before a summary."""
    # Prefer the ticker just before "Atlas Rating", which marks the card start.
    lower_bound = max(0, heading_index - 20)
    segment = lines[lower_bound:heading_index]
    for relative in range(len(segment) - 1, -1, -1):
        if segment[relative].lower() == "atlas rating" and relative > 0:
            candidate = segment[relative - 1].strip().upper()
            if _is_valid_summary_ticker(candidate):
                return candidate

    # Fallback: walk backwards, rejecting labels, numeric values, and sentences.
    for candidate in reversed(segment):
        clean = candidate.strip().upper()
        if _is_valid_summary_ticker(clean):
            return clean
    return ""


def _summary_after_heading(lines: list[str], heading_index: int) -> str:
    chunks: list[str] = []
    for line in lines[heading_index + 1:]:
        if not line:
            continue
        if line in CARD_STOP_HEADINGS:
            break
        if SUMMARY_HEADING.fullmatch(line) and chunks:
            break
        if line.startswith("Open complete Atlas research"):
            break
        # Avoid swallowing the next card ticker.
        if chunks and _is_valid_summary_ticker(line.upper()) and len(line) <= 6:
            break
        chunks.append(line)
        if len(" ".join(chunks)) >= 700:
            break
    return _clean(" ".join(chunks))


def _extract_summary_records(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract one genuine stock narrative per ticker.

    Navigation labels, page headings, "NO", and repeated copies of the same card
    are rejected before AI-content scoring.
    """
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for result in results:
        text = str(result.get("visible_text") or "")
        if not SUMMARY_HEADING.search(text):
            continue

        lines = [_clean(line) for line in text.splitlines() if _clean(line)]
        for index, line in enumerate(lines):
            if not CARD_START_HEADING.fullmatch(line):
                continue

            ticker = _nearest_ticker(lines, index)
            summary = _summary_after_heading(lines, index)
            if not ticker or len(summary.split()) < 12:
                continue

            key = (ticker, re.sub(r"\s+", " ", summary.lower())[:500])
            if key in seen:
                continue
            seen.add(key)

            records.append({
                "ticker": ticker,
                "company": ticker,
                "ai_summary": summary,
                "page": result.get("page"),
                "source_heading": line,
            })
    return records


def _deduplicate_issues(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], dict[str, Any]] = {}
    for item in items:
        evidence = item.get("evidence") or {}
        key = (
            item.get("severity"),
            item.get("category"),
            item.get("page"),
            item.get("ticker"),
            item.get("element"),
            item.get("actual"),
            json.dumps(evidence, sort_keys=True, default=str),
        )
        if key not in grouped:
            value = dict(item)
            value["occurrence_count"] = int(value.get("occurrence_count") or 1)
            value["pages_seen"] = sorted({str(value.get("page") or "")})
            grouped[key] = value
        else:
            grouped[key]["occurrence_count"] += 1
            page = str(item.get("page") or "")
            if page and page not in grouped[key]["pages_seen"]:
                grouped[key]["pages_seen"].append(page)
                grouped[key]["pages_seen"].sort()
    return list(grouped.values())


def _product_issues(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item for item in items
        if item.get("classification", "PRODUCT_ISSUE") == "PRODUCT_ISSUE"
    ]


async def run_runtime_qa_v3(*, url: str, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    contract = build_code_contract(".")
    page_results: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    failed_requests: list[dict[str, Any]] = []
    console_errors: list[dict[str, Any]] = []
    authentication: dict[str, Any] = {}

    print("=" * 72, flush=True)
    print("ATLAS RUNTIME QA V3.5 — CONTENT AND VISUAL FORMATTING QA", flush=True)
    print("=" * 72, flush=True)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context: BrowserContext = await browser.new_context(
            viewport={"width": 1440, "height": 1000},
        )
        page = await context.new_page()
        page.set_default_timeout(ACTION_TIMEOUT_MS)

        page.on(
            "console",
            lambda message: console_errors.append({
                "type": message.type,
                "text": message.text,
                "page": page.url,
            }) if message.type == "error" else None,
        )
        page.on(
            "response",
            lambda response: failed_requests.append({
                "status": response.status,
                "url": response.url,
                "resource_type": response.request.resource_type,
                "method": response.request.method,
                "page": page.url,
            }) if response.status >= 400 else None,
        )

        try:
            authentication = await asyncio.wait_for(
                _open_and_authenticate(page, url, output_dir),
                timeout=300,
            )
            pages = await _discover_navigation(
                page,
                contract.get("navigation_pages") or [],
            )
            print(f"[nav] Discovered {len(pages)} pages: {', '.join(pages)}", flush=True)

            if len(pages) < 3:
                raise RuntimeError(
                    f"Authenticated dashboard confirmation was insufficient: only "
                    f"{len(pages)} navigation labels were discovered."
                )

            for index, page_name in enumerate(pages, 1):
                if time.monotonic() - started > TOTAL_TIMEOUT_SECONDS:
                    issues.append(QAIssue(
                        severity="CRITICAL",
                        category="Total Runtime Guard",
                        page="Application",
                        element="Runtime",
                        expected="The audit completes within nine minutes.",
                        actual="The total runtime guard was reached.",
                        recommendation="Inspect the last page timing and isolate the slow interaction.",
                        likely_files=["agents/atlas_runtime_qa_v3.py"],
                    ).to_dict())
                    break

                print(f"[page {index}/{len(pages)}] {page_name}", flush=True)
                try:
                    if index > 1 or page_name != "Home":
                        await asyncio.wait_for(
                            _click_navigation(page, page_name),
                            timeout=12,
                        )
                    result = await asyncio.wait_for(
                        _inventory(page, page_name),
                        timeout=15,
                    )
                except Exception as exc:
                    result = PageResult(
                        page=page_name,
                        status="FAIL",
                        duration_seconds=0,
                        issues=[QAIssue(
                            severity="HIGH",
                            category="Page Audit Failure",
                            page=page_name,
                            element="Navigation or inventory",
                            expected="The page opens and exposes inspectable content.",
                            actual=f"{type(exc).__name__}: {exc}",
                            recommendation="Inspect the page route and navigation widget.",
                            likely_files=["app.py"],
                        ).to_dict()],
                    )

                result_dict = result.to_dict()
                page_results.append(result_dict)
                issues.extend(result_dict["issues"])
                (output_dir / "runtime_progress.json").write_text(
                    json.dumps({
                        "authenticated": authentication,
                        "completed_pages": [item["page"] for item in page_results],
                        "page_results": page_results,
                        "issues": issues,
                        "failed_requests": failed_requests,
                    }, indent=2, default=str),
                    encoding="utf-8",
                )
        except Exception as exc:
            failure_trace = traceback.format_exc()
            (output_dir / "initialization_error.txt").write_text(
                failure_trace,
                encoding="utf-8",
            )
            issues.append(QAIssue(
                severity="CRITICAL",
                category="Audit Initialization",
                page="Application",
                element="Authentication and navigation",
                expected="The authenticated dashboard is reached and at least three pages are discovered.",
                actual=f"{type(exc).__name__}: {exc}",
                recommendation=(
                    "Inspect initialization_error.txt and login_diagnostics.json. "
                    "Verify ATLAS_AUDIT_PASSWORD only if the trace reaches login handling."
                ),
                likely_files=["agents/atlas_runtime_qa_v3.py"],
                evidence={"traceback": failure_trace[-8000:]},
            ).to_dict())
        finally:
            await context.close()
            await browser.close()

    summaries = _extract_summary_records(page_results)
    ai_integrity = audit_summary_collection(summaries)
    issues.extend(ai_integrity["issues"])
    issues = _deduplicate_issues(issues)

    audit_valid = bool(
        authentication.get("authenticated_dashboard_detected")
        and len(page_results) >= 3
        and any((item.get("visible_text") or "").strip() for item in page_results)
    )

    # De-duplicate failed requests by status/url/resource type.
    deduped_requests = list({
        (
            item["status"],
            item["url"],
            item["resource_type"],
        ): item
        for item in failed_requests
    }.values())

    if not audit_valid:
        health = 0
        status = "AUDIT_INVALID"
    else:
        product_findings = _product_issues(issues)
        counts_preview = {
            level: sum(item.get("severity") == level for item in product_findings)
            for level in ("CRITICAL", "HIGH", "MEDIUM", "LOW")
        }
        health = max(
            0,
            100
            - counts_preview["CRITICAL"] * 15
            - counts_preview["HIGH"] * 6
            - counts_preview["MEDIUM"] * 2
            - counts_preview["LOW"],
        )
        status = "COMPLETE"

    product_findings = _product_issues(issues)
    counts = {
        level: sum(item.get("severity") == level for item in product_findings)
        for level in ("CRITICAL", "HIGH", "MEDIUM", "LOW")
    }
    qa_counts = {
        level: sum(
            item.get("severity") == level
            and item.get("classification") == "QA_EXTRACTION_ISSUE"
            for item in issues
        )
        for level in ("CRITICAL", "HIGH", "MEDIUM", "LOW")
    }

    report = {
        "version": "ATLAS-RUNTIME-QA-V3.5",
        "status": status,
        "audit_valid": audit_valid,
        "url": url,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(time.monotonic() - started, 1),
        "health_score": health,
        "severity_counts": counts,
        "qa_extraction_counts": qa_counts,
        "authentication": authentication,
        "navigation_discovered": [item["page"] for item in page_results],
        "pages_inspected": len(page_results),
        "page_results": page_results,
        "failed_requests": deduped_requests,
        "console_errors": console_errors,
        "ai_content_integrity": ai_integrity,
        "summary_records_extracted": summaries,
        "issues": issues,
        "code_contract": contract,
    }

    report_path = output_dir / "atlas_runtime_qa_v3.json"
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    fix_path = write_fix_plan(report, output_dir)

    markdown = [
        "# Atlas Runtime QA v3.5",
        "",
        f"- Status: {status}",
        f"- Audit valid: {audit_valid}",
        f"- Health: {health}%",
        f"- Duration: {report['duration_seconds']} seconds",
        f"- Pages inspected: {len(page_results)}",
        f"- Failed request URLs captured: {len(deduped_requests)}",
        f"- AI summaries reviewed: {ai_integrity['records_reviewed']}",
        "",
        "## Findings",
        "",
    ]
    for issue in issues:
        markdown.extend([
            f"### {issue.get('severity')} — {issue.get('category')}",
            f"- Page: {issue.get('page')}",
            f"- Expected: {issue.get('expected')}",
            f"- Actual: {issue.get('actual')}",
            f"- Likely files: {', '.join(issue.get('likely_files') or []) or 'Under review'}",
            f"- Recommendation: {issue.get('recommendation')}",
            "",
        ])
    (output_dir / "atlas_runtime_qa_v3.md").write_text(
        "\n".join(markdown),
        encoding="utf-8",
    )

    print("=" * 72, flush=True)
    print(f"AUDIT {status}", flush=True)
    print(f"Authenticated: {authentication.get('authenticated_dashboard_detected', False)}", flush=True)
    print(f"Pages inspected: {len(page_results)}", flush=True)
    print(f"Health: {health}%", flush=True)
    print(f"Report: {report_path}", flush=True)
    print(f"Fix plan: {fix_path}", flush=True)
    print("=" * 72, flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--output", default="audit_results")
    args = parser.parse_args()
    asyncio.run(
        run_runtime_qa_v3(
            url=args.url,
            output_dir=Path(args.output),
        )
    )


if __name__ == "__main__":
    main()
