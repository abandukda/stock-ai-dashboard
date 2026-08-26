"""Atlas QA Enterprise v4.0 — production synthetic QA.

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
from agents.runtime_qa_user_journeys_v40 import (
    page_certification_metadata, run_targeted_critical_journeys,
    run_user_journeys, wait_for_page_settlement,
)
from agents.runtime_qa_architecture import (
    CERTIFICATION_ARTIFACT, CORE_PAGE_CONTRACTS, RUNTIME_QA_FRAMEWORK_VERSION,
    architecture_preflight, architecture_versions, certification_integrity,
    certification_record, journey_completeness, research_ticker_matrix,
)
from agents.product_hardening_certification import (
    MOBILE_CRITICAL_JOURNEYS, screenshot_manifest_entry,
    visual_certification_completeness,
)


DEFAULT_URL = "https://stock-ai-dashboard.streamlit.app"
PAGE_TIMEOUT_MS = 35_000
ACTION_TIMEOUT_MS = 6_000
LOGIN_TIMEOUT_SECONDS = 240
TOTAL_TIMEOUT_SECONDS = 1_500

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


def _visual_manifest(source_sha: str, page_results: list[dict[str, Any]], user_journeys: dict[str, Any]) -> list[dict[str, str]]:
    """Build a sanitized screenshot manifest from full-certification evidence."""
    manifest: list[dict[str, str]] = []
    for page_result in page_results:
        manifest.append(screenshot_manifest_entry(
            source_sha=source_sha, page=str(page_result.get("page") or ""),
            screenshot_path=str(page_result.get("screenshot") or ""),
            status="PASS" if (
                page_result.get("screenshot") and page_result.get("status") == "PASS"
                and page_result.get("navigation_status") == "PASS"
                and page_result.get("rendered_exception_status") == "PASS"
            ) else "FAIL",
            viewport="desktop", state="page", expected_state="page identity, ready state, no rendered exception",
            observed_state=(
                f"page={page_result.get('status') or 'NOT_EXECUTED'};"
                f"navigation={page_result.get('navigation_status') or 'NOT_EXECUTED'};"
                f"rendered_exception={page_result.get('rendered_exception_status') or 'NOT_EXECUTED'}"
            ),
        ))
    interactions = (user_journeys.get("interaction_certification") or {}).get("results") or []
    for result in interactions:
        page = str(result.get("source_page") or "")
        interaction_id = str(result.get("interaction_id") or "")
        for state in ("before", "after"):
            path = str(result.get(f"{state}_screenshot") or "")
            if path or result.get("interaction_type") in {"DRILL_DOWN", "NAVIGATION", "EXPANDER"}:
                manifest.append(screenshot_manifest_entry(
                    source_sha=source_sha, page=page, screenshot_path=path,
                    status="PASS" if path else "FAIL", interaction_id=interaction_id,
                    state=state, expected_state=str(result.get("expected_state") or "required interaction evidence"),
                    observed_state=str(result.get("status") or "NOT_EXECUTED"),
                ))
        for tab in result.get("tabs") or []:
            path = str(tab.get("screenshot_path") or "")
            manifest.append(screenshot_manifest_entry(
                source_sha=source_sha, page=page, screenshot_path=path,
                status="PASS" if path and tab.get("selected") and tab.get("content_rendered") else "FAIL",
                interaction_id=interaction_id, tab_name=str(tab.get("label") or ""), state="tab-selected",
                expected_state="selected tab renders distinct content without exception",
                observed_state="PASS" if tab.get("selected") and tab.get("content_rendered") and not tab.get("rendered_exception") else "FAIL",
            ))
    for step in user_journeys.get("steps") or []:
        if step.get("journey") != "Core mobile certification":
            continue
        manifest.append(screenshot_manifest_entry(
            source_sha=source_sha, page=str(step.get("page") or step.get("step") or ""),
            screenshot_path=str(step.get("screenshot") or ""),
            status="PASS" if step.get("status") == "PASS" and step.get("screenshot") else "FAIL",
            viewport="mobile", state=str(step.get("step") or "state"),
            expected_state="mobile journey renders and remains interactive without exception",
            observed_state=str(step.get("status") or "NOT_EXECUTED"),
        ))
        evidence = step.get("evidence") or {}
        for state in ("before", "after"):
            path = str(evidence.get(f"{state}_screenshot") or "")
            if path or step.get("step") in {"home-card-to-research", "opportunities-to-research"}:
                manifest.append(screenshot_manifest_entry(
                    source_sha=source_sha, page=str(step.get("page") or step.get("step") or ""),
                    screenshot_path=path, status="PASS" if path else "FAIL",
                    viewport="mobile", state=state, interaction_id=str(step.get("step") or ""),
                    expected_state="mobile navigation/drill-down evidence",
                    observed_state=str(step.get("status") or "NOT_EXECUTED"),
                ))
    return manifest


def _mobile_result_index(user_journeys: dict[str, Any]) -> dict[str, dict[str, str]]:
    return {
        str(step.get("step") or ""): {"status": str(step.get("status") or "NOT_EXECUTED")}
        for step in user_journeys.get("steps") or []
        if step.get("journey") == "Core mobile certification"
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


async def _rendered_exception_present(page: Page) -> bool:
    for scope in _all_scopes(page):
        try:
            if await scope.locator('[data-testid="stException"]').count():
                return True
        except Exception:
            continue
    return False


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

    screenshot_path = ""
    if output_dir is not None:
        try:
            safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", page_name).strip("_") or "page"
            path = output_dir / f"visual_{safe_name}.png"
            await page.screenshot(
                path=str(path),
                full_page=True,
            )
            screenshot_path = str(path)
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
        screenshot=screenshot_path,
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


def _classify_failed_request(url: str, status: int) -> dict[str, str]:
    """Classify platform traffic without retaining query strings or credentials."""
    from urllib.parse import urlsplit
    parts = urlsplit(str(url or ""))
    path = parts.path or "/"
    if path.endswith("/api/v2/user/details") and status == 404:
        return {"path": path, "classification": "PLATFORM_NOISE", "relevance": "NOT_ATLAS_FUNCTIONALITY"}
    if path.endswith("/api/v1/app/event/open") and status == 403:
        return {"path": path, "classification": "PLATFORM_TELEMETRY_NOISE", "relevance": "NOT_ATLAS_FUNCTIONALITY"}
    return {"path": path, "classification": "APPLICATION_OR_DEPENDENCY_REQUEST_FAILURE", "relevance": "REVIEW_REQUIRED"}


def preserve_partial_journey_progress(
    current: dict[str, Any], partial: dict[str, Any],
    required: dict[str, int], exception_category: str,
) -> dict[str, Any]:
    """Invalidate a timed-out audit without erasing already completed work."""
    result = dict(partial) if partial.get("steps") else dict(current)
    family_progress = result.get("family_completed") or {}
    result.update({
        "status": "ENGINE_EXCEPTION",
        "engine_exception_category": exception_category,
        "required_journey_completeness": journey_completeness(
            required, family_progress, engine_error=exception_category,
        ),
        "cross_page_consistency": result.get("cross_page_consistency") or {
            "status": "NOT_EXECUTED",
            "reason": f"Journey engine terminated with {exception_category}.",
        },
    })
    return result


def settlement_failure_classification(detail: str) -> str:
    """Marker/time settlement defects are QA defects unless a real exception rendered."""
    return "PRODUCT_DEFECT" if "rendered_exception=True" in str(detail or "") else "QA_DEFECT"


def research_performance_classification(*, canonical_ready: bool, render_complete: bool, provider_seconds: float, wait_seconds: float) -> str:
    """Separate a slow product path from a QA wait/marker defect."""
    if canonical_ready and not render_complete and provider_seconds < wait_seconds:
        return "QA_WAIT_DEFECT"
    if provider_seconds >= wait_seconds or (not canonical_ready and provider_seconds > 0):
        return "PRODUCT_PERFORMANCE_DEFECT"
    return "QA_WAIT_DEFECT"


async def run_runtime_qa_v3(*, url: str, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    architecture = architecture_preflight(".")
    versions = architecture_versions(".")
    if architecture.get("status") != "PASS":
        early = {
            "version": RUNTIME_QA_FRAMEWORK_VERSION,
            "source_commit": versions["source_commit"],
            "architecture_versions": versions,
            "status": "ARCHITECTURE_DRIFT",
            "architecture_preflight": architecture,
            "certifications": [],
        }
        (output_dir / CERTIFICATION_ARTIFACT).write_text(json.dumps(early, indent=2), encoding="utf-8")
        raise RuntimeError(f"Architecture preflight failed: {architecture.get('failures')}")
    contract = build_code_contract(".")
    page_results: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    failed_requests: list[dict[str, Any]] = []
    console_errors: list[dict[str, Any]] = []
    authentication: dict[str, Any] = {}
    resolved_ticker_matrix = research_ticker_matrix(".")
    required_expected = {"navigation": 14, "research": 6, "ask": 6, "responsive": 6, "cross_page": 1}
    user_journeys: dict[str, Any] = {
        "status": "NOT_EXECUTED", "ticker_matrix": resolved_ticker_matrix,
        "cross_page_consistency": {"status": "NOT_EXECUTED", "reason": "Browser journeys have not started."},
        "required_journey_completeness": journey_completeness(required_expected, {}, engine_error="NOT_EXECUTED"),
        "steps": [], "counts": {"PASS": 0, "WARN": 0, "FAIL": 0},
        "interaction_certification": {
            "coverage": {"full_certification_allowed": False, "coverage_pct": 0.0},
            "results": [], "status": "NOT_EXECUTED",
        },
    }
    (output_dir / CERTIFICATION_ARTIFACT).write_text(json.dumps({
        "version": RUNTIME_QA_FRAMEWORK_VERSION,
        "source_commit": versions["source_commit"],
        "architecture_versions": versions,
        "status": "IN_PROGRESS",
        "audit_valid": False,
        "ticker_matrix": resolved_ticker_matrix,
        "required_journey_completeness": user_journeys["required_journey_completeness"],
        "cross_page_consistency": user_journeys["cross_page_consistency"],
        "certifications": [],
    }, indent=2), encoding="utf-8")

    print("=" * 72, flush=True)
    print("ATLAS QA ENTERPRISE V4.0 — RUNTIME + VISUAL + AI + USER JOURNEYS", flush=True)
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
                    settled, _, settlement_detail = await wait_for_page_settlement(page, page_name, output_dir)
                    if not settled:
                        raise TimeoutError(settlement_detail)
                    result = await asyncio.wait_for(
                        _inventory(page, page_name, output_dir),
                        timeout=20,
                    )
                except Exception as exc:
                    failure_classification = settlement_failure_classification(str(exc))
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
                            classification=failure_classification,
                            architecture_severity="P1",
                        ).to_dict()],
                    )

                result_dict = result.to_dict()
                result_dict["navigation_status"] = "PASS" if result.status == "PASS" else "FAIL"
                result_dict["rendered_exception_status"] = "FAIL" if await _rendered_exception_present(page) else "PASS"
                result_dict["page_certification"] = await page_certification_metadata(page, page_name)
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

            print("[journeys] Starting full synthetic client journeys", flush=True)
            partial_journeys: dict[str, Any] = {}
            try:
                user_journeys = await asyncio.wait_for(
                    run_user_journeys(
                        page,
                        output_dir=output_dir,
                        navigation_labels=pages,
                        prevalidated_navigation=page_results,
                        progress_state=partial_journeys,
                    ),
                    timeout=600,
                )
                (output_dir / "atlas_user_journeys_v40.json").write_text(
                    json.dumps(user_journeys, indent=2, default=str),
                    encoding="utf-8",
                )
                for step in user_journeys.get("steps", []):
                    if step.get("status") == "FAIL":
                        step_evidence = step.get("evidence") or {}
                        reconciliation = step_evidence.get("canonical_reconciliation") or {}
                        supported_classification = reconciliation.get("classification")
                        if supported_classification not in {
                            "ARCHITECTURE_DRIFT", "PRODUCT_DEFECT", "DATA_PIPELINE_DEFECT",
                            "QA_DEFECT", "PROVIDER_LIMITATION",
                        }:
                            supported_classification = "PRODUCT_DEFECT"
                        issues.append(QAIssue(
                            severity="HIGH",
                            category="User Journey Failure",
                            page=step.get("page") or "Application",
                            element=f"{step.get('journey')} — {step.get('step')}",
                            expected="The synthetic client journey completes without a broken interaction.",
                            actual=step.get("detail") or "Synthetic journey failed.",
                            recommendation=(
                                "Reproduce the failed journey using the attached screenshot and evidence. "
                                "Inspect the page renderer, Streamlit control, and downstream engine."
                            ),
                            likely_files=["app.py", "ui/research_report_v2.py", "engines/ask_atlas_engine.py"],
                            evidence=step,
                            regression_test="Keep this synthetic journey in the permanent QA suite.",
                            classification=supported_classification,
                            architecture_severity=reconciliation.get("severity") or "P1",
                        ).to_dict())
            except Exception as exc:
                exception_category = type(exc).__name__
                user_journeys = preserve_partial_journey_progress(
                    user_journeys, partial_journeys, required_expected, exception_category,
                )
                issues.append(QAIssue(
                    severity="HIGH",
                    category="User Journey Engine",
                    page="Application",
                    element="Synthetic client journeys",
                    expected="Navigation, research, Ask AI, and responsive smoke journeys execute.",
                    actual=exception_category,
                    recommendation="Inspect agents/runtime_qa_user_journeys_v40.py and journey screenshots.",
                    likely_files=["agents/runtime_qa_user_journeys_v40.py"],
                    classification="QA_DEFECT",
                    architecture_severity="P1",
                ).to_dict())
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

    certifications: list[dict[str, Any]] = []
    for item in page_results:
        semantic_required = item.get("page") in CORE_PAGE_CONTRACTS
        navigation_ok = item.get("status") == "PASS"
        certifications.append(certification_record(
            page=item.get("page"), journey="Page certification", ticker="",
            screenshot_paths=(item.get("screenshot"),) if item.get("screenshot") else (),
            classification="QA_DEFECT" if semantic_required or not navigation_ok else "PASS",
            severity="P1" if semantic_required or not navigation_ok else None,
            navigation_status="PASS" if navigation_ok else "FAIL",
            semantic_status="NOT_EXECUTED" if semantic_required else "NOT_REQUIRED",
            reconciliation_status="NOT_EXECUTED" if semantic_required else "NOT_REQUIRED",
        ))
    for step in (user_journeys.get("steps") or []):
        evidence = step.get("evidence") or {}
        reconciliation = evidence.get("canonical_reconciliation") or evidence.get("canonical_context_certification") or {}
        classification = reconciliation.get("classification")
        if not classification:
            classification = "PASS" if step.get("status") == "PASS" else "QA_DEFECT"
        semantic_required = step.get("page") in {"Research Any Ticker", "Ask AI"}
        if semantic_required and not reconciliation:
            classification = "QA_DEFECT"
        certifications.append(certification_record(
            page=step.get("page"), journey=f"{step.get('journey')} — {step.get('step')}",
            ticker=((evidence.get("canonical_research_summary") or {}).get("ticker") or (evidence.get("grounding") or {}).get("ticker") or ""),
            canonical_reconciliation=reconciliation,
            freshness_result={family: value.get("freshness") for family, value in (reconciliation.get("family_reconciliation") or {}).items()},
            provenance_result={"rendered_families": evidence.get("rendered_family_summary") or {}},
            cross_page_consistency=user_journeys.get("cross_page_consistency") or {},
            screenshot_paths=(step.get("screenshot"),) if step.get("screenshot") else (),
            classification=classification,
            severity=reconciliation.get("severity") or (None if classification in {"PASS", "PASS_WITH_EVIDENCE_LIMITATIONS", "PROVIDER_LIMITATION"} else "P1"),
            navigation_status="PASS" if step.get("status") == "PASS" else "FAIL",
            semantic_status="PASS" if reconciliation and classification in {"PASS", "PASS_WITH_EVIDENCE_LIMITATIONS"} else "NOT_EXECUTED" if semantic_required else "NOT_REQUIRED",
            reconciliation_status="PASS" if reconciliation else "NOT_EXECUTED" if semantic_required else "NOT_REQUIRED",
            responsive_status="PASS" if str(step.get("journey") or "").startswith(("Responsive ", "Core mobile")) and step.get("status") == "PASS" else "NOT_APPLICABLE",
        ))

    screenshot_manifest = _visual_manifest(versions["source_commit"], page_results, user_journeys)
    evidence_reconciliations: dict[str, dict[str, str]] = {}
    for page_name in ("Research Any Ticker", "Earnings Intelligence", "Ask AI"):
        matching = [item for item in certifications if item.get("page") == page_name]
        complete = any(
            item.get("canonical_reconciliation")
            and item.get("classification") in {"PASS", "PASS_WITH_EVIDENCE_LIMITATIONS", "PROVIDER_LIMITATION"}
            for item in matching
        )
        evidence_reconciliations[page_name] = {"status": "PASS" if complete else "NOT_EXECUTED"}
    political_page = next((item for item in page_results if item.get("page") == "Political Intelligence"), {})
    political_meta = political_page.get("page_certification") or {}
    political_complete = bool(
        political_meta.get("evidence_type") == "CONGRESSIONAL_TRANSACTION"
        and int(political_meta.get("evidence_count") or 0) > 0
        and int(political_meta.get("complete_evidence_count") or 0) == int(political_meta.get("evidence_count") or 0)
        and political_meta.get("evidence_digest")
        and political_meta.get("ownership_separation") == "true"
    )
    evidence_reconciliations["Political Intelligence"] = {"status": "PASS" if political_complete else "NOT_EXECUTED"}
    visual_certification = visual_certification_completeness(
        source_sha=versions["source_commit"], architecture_versions=versions,
        page_results=page_results,
        interaction_certification=user_journeys.get("interaction_certification") or {},
        screenshot_manifest=screenshot_manifest,
        evidence_reconciliations=evidence_reconciliations,
        mobile_results=_mobile_result_index(user_journeys),
        session_result=user_journeys.get("session_stability") or {},
    )

    integrity = certification_integrity(
        authenticated=bool(authentication.get("authenticated_dashboard_detected")),
        page_count=len(page_results),
        journey_state=user_journeys.get("required_journey_completeness") or {},
        ticker_matrix=resolved_ticker_matrix,
        cross_page=user_journeys.get("cross_page_consistency") or {},
    )
    base_audit_ready = bool(
        authentication.get("authenticated_dashboard_detected")
        and len(page_results) >= 3
        and any((item.get("visible_text") or "").strip() for item in page_results)
    )
    interaction_certification = user_journeys.get("interaction_certification") or {}
    interaction_coverage_result = interaction_certification.get("coverage") or {}
    audit_valid = bool(
        base_audit_ready and integrity["audit_valid"]
        and interaction_coverage_result.get("full_certification_allowed")
        and visual_certification.get("full_certification_allowed")
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
    for item in deduped_requests:
        item.update(_classify_failed_request(item.pop("url", ""), int(item.get("status") or 0)))

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
        "version": RUNTIME_QA_FRAMEWORK_VERSION,
        "source_commit": versions["source_commit"],
        "architecture_versions": versions,
        "architecture_preflight": architecture,
        "certification_integrity": integrity,
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
        "user_journeys": user_journeys,
        "performance": (user_journeys or {}).get("performance", {}),
        "interaction_certification": interaction_certification,
        "visual_certification": visual_certification,
        "screenshot_manifest": screenshot_manifest,
        "evidence_reconciliations": evidence_reconciliations,
        "issues": issues,
        "code_contract": contract,
        "certifications": certifications,
    }

    certification_artifact = {
        "version": RUNTIME_QA_FRAMEWORK_VERSION,
        "source_commit": versions["source_commit"],
        "architecture_versions": versions,
        "rollout_state": architecture.get("rollout_state"),
        "status": "PASS" if audit_valid else "INCOMPLETE",
        "audit_valid": audit_valid,
        "certification_integrity": integrity,
        "ticker_matrix": resolved_ticker_matrix,
        "required_journey_completeness": user_journeys.get("required_journey_completeness"),
        "cross_page_consistency": user_journeys.get("cross_page_consistency") or {"status": "NOT_EXECUTED", "reason": "No results."},
        "interaction_certification": interaction_certification,
        "visual_certification": visual_certification,
        "screenshot_manifest": screenshot_manifest,
        "evidence_reconciliations": evidence_reconciliations,
        "certifications": certifications,
    }
    (output_dir / CERTIFICATION_ARTIFACT).write_text(
        json.dumps(certification_artifact, indent=2, default=str), encoding="utf-8",
    )

    report_path = output_dir / "atlas_runtime_qa_v3.json"
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    fix_path = write_fix_plan(report, output_dir)

    markdown = [
        "# Atlas QA Enterprise v4.0",
        "",
        f"- Status: {status}",
        f"- Audit valid: {audit_valid}",
        f"- Health: {health}%",
        f"- Duration: {report['duration_seconds']} seconds",
        f"- Pages inspected: {len(page_results)}",
        f"- Failed request URLs captured: {len(deduped_requests)}",
        f"- AI summaries reviewed: {ai_integrity['records_reviewed']}",
        f"- User journey failures: {(user_journeys.get('counts') or {}).get('FAIL', 0)}",
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


async def run_targeted_preflight_v3(*, url: str, output_dir: Path) -> dict[str, Any]:
    """Authenticate through the existing QA path and run only six QA.4 journeys."""
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    architecture = architecture_preflight(".")
    versions = architecture_versions(".")
    artifact_path = output_dir / "atlas_targeted_preflight.json"
    base = {
        "version": "QA4_TARGETED_PREFLIGHT_V1",
        "source_sha": versions["source_commit"],
        "architecture_preflight": architecture.get("status"),
        "authentication_success": False,
        "expected": 6, "attempted": 0, "passed": 0, "failed": 0,
        "status": "QA_INFRASTRUCTURE_BLOCKER" if architecture.get("status") != "PASS" else "IN_PROGRESS",
        "total_duration_seconds": 0.0, "journeys": [],
    }
    if architecture.get("status") != "PASS":
        artifact_path.write_text(json.dumps(base, indent=2), encoding="utf-8")
        return base

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context: BrowserContext = await browser.new_context(viewport={"width": 1440, "height": 1000})
        page = await context.new_page()
        page.set_default_timeout(ACTION_TIMEOUT_MS)
        try:
            authentication = await asyncio.wait_for(_open_and_authenticate(page, url, output_dir), timeout=300)
            authenticated = bool(authentication.get("authenticated_dashboard_detected"))
            if not authenticated:
                base["status"] = "QA_INFRASTRUCTURE_BLOCKER"
            else:
                base["authentication_success"] = True
                base.update(await run_targeted_critical_journeys(page, output_dir=output_dir))
                base["source_sha"] = versions["source_commit"]
                base["architecture_preflight"] = architecture.get("status")
                base["authentication_success"] = True
        except Exception:
            # The artifact intentionally records no credential, raw exception,
            # URL, payload, or stack trace.
            base["status"] = "QA_INFRASTRUCTURE_BLOCKER"
        finally:
            await context.close()
            await browser.close()
    base["total_duration_seconds"] = round(time.monotonic() - started, 3)
    artifact_path.write_text(json.dumps(base, indent=2, default=str), encoding="utf-8")
    return base


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--output", default="audit_results")
    parser.add_argument("--mode", choices=("full", "targeted_preflight"), default="full")
    args = parser.parse_args()
    result = asyncio.run(
        (run_targeted_preflight_v3 if args.mode == "targeted_preflight" else run_runtime_qa_v3)(
            url=args.url,
            output_dir=Path(args.output),
        )
    )
    if args.mode == "targeted_preflight" and result.get("status") != "TARGETED_PREFLIGHT_PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
