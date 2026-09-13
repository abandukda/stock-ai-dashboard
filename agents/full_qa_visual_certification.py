"""Focused browser certification for the exact full-universe QA candidate."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import time
from typing import Any

from playwright.async_api import async_playwright

from agents.atlas_runtime_qa_v3 import _open_and_authenticate
from agents.atlas_visual_crawler_v1 import AtlasVisualCrawler, DESKTOP, MOBILE, _has_rendered_exception
from agents.runtime_qa_user_journeys_v40 import _visible_text
from agents.visual_qa_certification_v2 import (
    analyze_capture, candidate_identity, dom_fact_findings, enrich_manifest, expected_facts,
    repair_decision, validate_runtime_target, visual_summary,
)


VERSION = "ATLAS_FULL_QA_VISUAL_V2"
QA_MODES = ("RELEASE_FULL", "FAST_PREVIEW")
OPERATION_TIMEOUTS = {"authentication": 60.0, "navigation": 30.0, "page_render": 45.0,
                      "research": 60.0, "interaction": 10.0, "screenshot": 20.0, "dom": 5.0}
SCREENSHOT_BUDGETS = {
    "Home": {"desktop": 6, "mobile": 6}, "Research Any Ticker": {"desktop": 8, "mobile": 7},
    "Paid Detail": {"desktop": 12, "mobile": 12}, "Full Ranked Scan": {"desktop": 12, "mobile": 12},
    "Volume Intelligence": {"desktop": 6, "mobile": 4}, "Developer Center": {"desktop": 4, "mobile": 4},
}
REQUIRED_PAGES = ("Home", "Research Any Ticker", "Full Ranked Scan", "Volume Intelligence", "Developer Center")
CUSTOMER_ACTION_LABELS = {
    "BUY_NOW": "BUY NOW",
    "ACCUMULATE": "BUILD A POSITION",
    "WAIT_FOR_ENTRY": "WAIT FOR BETTER ENTRY",
    "WAIT_FOR_BETTER_ENTRY": "WAIT FOR BETTER ENTRY",
    "WAIT_FOR_CONFIRMATION": "WAIT FOR CONFIRMATION",
    "DATA_LIMITED": "WATCH",
    "AVOID": "AVOID",
}

EXPANDABLE_LABEL_RE = re.compile(
    r"(?:view\s+more|show\s+details|professional\s+detail|full\s+investment\s+case|"
    r"financial\s+health|professional\s+valuation|valuation\s+methods?|wall\s+street|"
    r"earnings|estimates?|news|catalysts?|insider|institutional|technicals?|volume|"
    r"trade\s+plan|risks?|what\s+changes|sources?|evidence|analysis|assumptions?|"
    r"financials?|ownership|scenario|thesis|guidance|score\s+attribution|research\s+readiness)",
    re.I,
)
NON_DISCLOSURE_BUTTON_RE = re.compile(r"^(?:home|research any ticker|full ranked scan|volume intelligence|developer center)$", re.I)


class QARuntimeBudgetExceeded(RuntimeError):
    pass


class TimingReport:
    def __init__(self, *, mode: str, ceiling_seconds: float) -> None:
        self.started = time.monotonic(); self.mode = mode; self.ceiling_seconds = ceiling_seconds
        self.operations: list[dict[str, Any]] = []; self.retry_counts: dict[str, int] = {}
        self.timeouts: list[dict[str, Any]] = []
        self.calls_avoided = {"screenshots": 0, "authentication": 0, "ticker_evaluations": 0}

    def record(self, operation: str, seconds: float, **dimensions: Any) -> None:
        self.operations.append({"operation": operation, "seconds": round(seconds, 3), **dimensions})

    def retry(self, operation: str) -> None:
        self.retry_counts[operation] = self.retry_counts.get(operation, 0) + 1

    def timeout(self, operation: str, seconds: float) -> None:
        self.timeouts.append({"operation": operation, "timeout_seconds": seconds})

    def enforce(self, stage: str) -> None:
        elapsed = time.monotonic() - self.started
        if elapsed > self.ceiling_seconds:
            raise QARuntimeBudgetExceeded(f"QA_RUNTIME_BUDGET_EXCEEDED:{stage}:{elapsed:.1f}s")

    def payload(self, crawler: AtlasVisualCrawler | None = None) -> dict[str, Any]:
        def totals(key: str) -> dict[str, float]:
            result: dict[str, float] = {}
            for row in self.operations:
                value = str(row.get(key) or "")
                if value: result[value] = round(result.get(value, 0.0) + float(row["seconds"]), 3)
            return result
        if crawler:
            self.calls_avoided["screenshots"] = crawler.screenshot_calls_avoided
            self.retry_counts["screenshot"] = crawler.screenshot_retries
        return {"version": VERSION, "mode": self.mode, "total_seconds": round(time.monotonic() - self.started, 3),
                "runtime_ceiling_seconds": self.ceiling_seconds, "stages": totals("stage"),
                "per_page": totals("page"), "per_ticker": totals("ticker"), "per_viewport": totals("viewport"),
                "per_interaction_type": totals("interaction_type"),
                "longest_operations": sorted(self.operations, key=lambda row: row["seconds"], reverse=True)[:10],
                "retry_counts": self.retry_counts, "timeouts": self.timeouts,
                "browser_navigation_count": sum(row["operation"] == "navigation" for row in self.operations),
                "screenshot_count": len({i.get("path") for i in (crawler.manifest if crawler else []) if i.get("path")}),
                "dom_snapshot_count": sum(row["operation"] == "dom" for row in self.operations),
                "calls_avoided": self.calls_avoided}


async def bounded_operation(name: str, operation, *, timeout: float, timing: TimingReport, retries: int = 0):
    for attempt in range(retries + 1):
        started = time.monotonic()
        try:
            result = await asyncio.wait_for(operation(), timeout=timeout)
            timing.record(name, time.monotonic() - started, stage=name)
            return result
        except asyncio.TimeoutError:
            timing.timeout(name, timeout); timing.record(name, time.monotonic() - started, stage=name)
            if attempt >= retries: raise
            timing.retry(name)
        except Exception:
            timing.record(name, time.monotonic() - started, stage=name)
            if attempt >= retries: raise
            timing.retry(name)


def visual_completion_contract(*, finished: bool, authentication_success: bool, checks: list[dict[str, Any]],
                               manifest: list[dict[str, Any]], mode: str, candidate_binding_valid: bool) -> dict[str, Any]:
    required = [row for row in checks if row.get("required")]
    passed = [row for row in required if row.get("status") == "PASS"]
    desktop = len({row.get("path") or row.get("file_path") for row in manifest if row.get("viewport") == "desktop" and (row.get("path") or row.get("file_path"))})
    mobile = len({row.get("path") or row.get("file_path") for row in manifest if row.get("viewport") == "mobile" and (row.get("path") or row.get("file_path"))})
    required_pages = REQUIRED_PAGES if mode == "RELEASE_FULL" else ("Home", "Research Any Ticker")
    pages_ok = all(any(row.get("page") == page and row.get("status") == "PASS" for row in checks) for page in required_pages)
    coverage = 1.0 if not required else len(passed) / len(required)
    manifest_ok = bool(manifest) and all((row.get("path") or row.get("file_path")) and row.get("generated", True) for row in manifest)
    mobile_coverage = 1.0 if mode == "FAST_PREVIEW" else float(mobile > 0)
    result = {"finished": finished, "authentication_success": authentication_success,
              "required_pages_passed": pages_ok, "required_interactions_coverage": coverage,
              "mobile_required_coverage": mobile_coverage, "screenshot_manifest_valid": manifest_ok,
              "candidate_binding_valid": candidate_binding_valid, "desktop_screenshot_count": desktop,
              "mobile_screenshot_count": mobile}
    result.update({
        "controls_discovered": len([row for row in checks if row.get("interaction_type") == "EXPANDER"]),
        "controls_required": len(required),
        "controls_opened": sum(row.get("click_success") is True for row in required),
        "controls_closed": sum(row.get("collapse_success") is True for row in required),
        "nested_controls_required": sum(row.get("interaction_type") == "NESTED_EXPANDER" for row in required),
        "nested_controls_passed": sum(row.get("interaction_type") == "NESTED_EXPANDER" and row.get("status") == "PASS" for row in required),
        "all_open_tests_required": sum(row.get("interaction_type") == "ALL_MAJOR_EXPANDED" for row in required),
        "all_open_tests_passed": sum(row.get("interaction_type") == "ALL_MAJOR_EXPANDED" and row.get("status") == "PASS" for row in required),
    })
    result["passed"] = all((finished, authentication_success, pages_ok, coverage == 1.0,
                            mobile_coverage == 1.0, manifest_ok, candidate_binding_valid))
    return result


def required_expandable(page_name: str, label: str) -> bool:
    """Govern which customer disclosures must be traversed fail-closed."""
    clean = re.sub(r"\s+", " ", str(label or "")).strip()
    if not clean or NON_DISCLOSURE_BUTTON_RE.fullmatch(clean):
        return False
    if page_name in {"Home", "Research Any Ticker"}:
        return True
    return bool(EXPANDABLE_LABEL_RE.search(clean))


def interaction_manifest_fields(
    *, label: str, initial_state: str, final_state: str, click_success: bool,
    expected_content: str, observed_content: str, interaction_type: str = "EXPANDER",
) -> dict[str, Any]:
    return {
        "interaction_type": interaction_type,
        "control_label": label,
        "initial_state": initial_state,
        "final_state": final_state,
        "click_success": bool(click_success),
        "expected_content": expected_content,
        "observed_content": observed_content,
    }


async def _expandable_inventory(page) -> list[dict[str, Any]]:
    """Inventory visible disclosure controls without treating navigation as disclosure."""
    return await page.evaluate("""() => {
      const visible = e => {
        const s=getComputedStyle(e), r=e.getBoundingClientRect();
        return s.visibility!=='hidden' && s.display!=='none' && r.width>2 && r.height>2;
      };
      const nodes = [...document.querySelectorAll('[data-testid="stExpander"] summary, details summary, button[aria-expanded]')];
      const seen = new Set(), output=[];
      for (const node of nodes) {
        if (!visible(node)) continue;
        const label=(node.innerText || node.textContent || '').replace(/\\s+/g,' ').trim();
        const key=`${label}|${output.filter(x=>x.label===label).length}`;
        if (!label || seen.has(key)) continue;
        seen.add(key);
        const details=node.closest('details');
        output.push({label, ordinal: output.filter(x=>x.label===label).length,
          expanded: details ? details.open : node.getAttribute('aria-expanded')==='true'});
      }
      return output;
    }""")


async def _expandable_locator(page, label: str, ordinal: int):
    controls = page.locator('[data-testid="stExpander"] summary, details summary, button[aria-expanded]')
    matches = controls.filter(has_text=label)
    return matches.nth(min(ordinal, max(await matches.count() - 1, 0)))


async def _expanded_state(control) -> bool:
    return bool(await control.evaluate("""node => {
      const details=node.closest('details');
      return details ? details.open : node.getAttribute('aria-expanded')==='true';
    }"""))


async def _expanded_content(control) -> str:
    return str(await control.evaluate("""node => {
      const host=node.closest('details') || node.parentElement;
      return (host?.innerText || '').replace(/\\s+/g,' ').trim();
    }""") or "")


def _annotate_latest_shot(crawler: AtlasVisualCrawler, path: str, fields: dict[str, Any]) -> None:
    for item in reversed(crawler.manifest):
        if item.get("path") == path:
            item.update(fields)
            return


async def certify_expandable_interactions(
    page, crawler: AtlasVisualCrawler, *, page_name: str, viewport: str, ticker: str = "",
    certified_facts: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Certify collapsed, individual, nested, all-open, and re-collapsed states."""
    checks: list[dict[str, Any]] = []
    defects: list[dict[str, Any]] = []
    inventory = await _expandable_inventory(page)
    default_shot = await crawler._shot(
        page, page_name=page_name, interaction="expandables", state="default-collapsed",
        viewport=viewport, ticker=ticker,
    )
    default_state = "MIXED" if any(item["expanded"] for item in inventory) else "COLLAPSED"
    _annotate_latest_shot(crawler, default_shot, interaction_manifest_fields(
        label="ALL_VISIBLE_DISCLOSURES", initial_state=default_state, final_state=default_state,
        click_success=True, expected_content=f"{len(inventory)} visible disclosure controls inventoried",
        observed_content=", ".join(item["label"] for item in inventory),
    ))

    # Normalize initially-open controls only after preserving the true default state.
    for item in reversed(inventory):
        if item["expanded"]:
            try:
                control = await _expandable_locator(page, item["label"], item["ordinal"])
                await control.click(timeout=5000)
                await page.wait_for_timeout(250)
            except Exception:
                pass

    processed: set[tuple[str, int]] = set()
    queue = [{**item, "nested": False} for item in await _expandable_inventory(page)]

    async def exercise_nested(parent_control, *, depth: int = 1) -> None:
        if depth > 4:
            return
        try:
            host = parent_control.locator("xpath=ancestor::details[1]")
            # Descendant disclosures only: never recurse into the parent
            # summary as though it were its own nested child.
            nested_nodes = host.locator(":scope details > summary")
            count = await nested_nodes.count()
        except Exception:
            return
        for nested_index in range(count):
            nested = nested_nodes.nth(nested_index)
            try:
                if not await nested.is_visible():
                    continue
                label = re.sub(r"\s+", " ", await nested.inner_text(timeout=1000)).strip()
                if not label:
                    continue
                opened = await _expanded_state(nested)
                if not opened:
                    await nested.click(timeout=5000)
                    await page.wait_for_timeout(350)
                opened = await _expanded_state(nested)
                content = await _expanded_content(nested) if opened else ""
                layout = await _layout(page)
                exception = await _has_rendered_exception(page)
                malformed = bool(re.search(r"(?:\bNone\b|\bnull\b|\bnan\b|Traceback|KeyError|TypeError)", content, re.I))
                passed_open = bool(opened and len(content) > len(label) and not layout["horizontal_overflow"] and not exception and not malformed)
                shot = await crawler._shot(
                    page, page_name=page_name, interaction=f"nested-expand-{label}",
                    state="expanded", viewport=viewport, ticker=ticker,
                )
                _annotate_latest_shot(crawler, shot, interaction_manifest_fields(
                    label=label, initial_state="COLLAPSED", final_state="EXPANDED",
                    click_success=opened, expected_content="Nested disclosure reveals valid customer content",
                    observed_content=content[:500], interaction_type="NESTED_EXPANDER",
                ))
                if opened:
                    await exercise_nested(nested, depth=depth + 1)
                    await nested.click(timeout=5000)
                    await page.wait_for_timeout(220)
                collapsed = not await _expanded_state(nested)
                passed = passed_open and collapsed
                check = {
                    "page": page_name, "viewport": viewport, "ticker": ticker,
                    "interaction_type": "NESTED_EXPANDER", "control_label": label,
                    "required": True, "initial_state": "COLLAPSED",
                    "final_state": "COLLAPSED" if collapsed else "UNKNOWN",
                    "click_success": opened, "collapse_success": collapsed,
                    "expected_content": "Nested expansion and collapse round trip",
                    "observed_content": content[:500], "status": "PASS" if passed else "FAIL",
                    "layout": layout, "screenshot": shot, "depth": depth,
                }
                checks.append(check)
                if not passed:
                    defects.append({"severity": "P1", "page": page_name, "viewport": viewport,
                                    "observed": json.dumps(check, sort_keys=True), "ticker_context": ticker})
            except Exception as exc:
                check = {"page": page_name, "viewport": viewport, "ticker": ticker,
                         "interaction_type": "NESTED_EXPANDER", "control_label": f"nested-{nested_index}",
                         "required": True, "click_success": False, "collapse_success": False,
                         "status": "FAIL", "observed": type(exc).__name__}
                checks.append(check)
                defects.append({"severity": "P1", "page": page_name, "viewport": viewport,
                                "observed": json.dumps(check, sort_keys=True), "ticker_context": ticker})

    while queue:
        item = queue.pop(0)
        key = (item["label"], int(item["ordinal"]))
        if key in processed:
            continue
        processed.add(key)
        required = required_expandable(page_name, item["label"])
        started = time.monotonic()
        opened = collapsed = False
        content = ""
        observed = ""
        shot = ""
        try:
            control = await _expandable_locator(page, item["label"], item["ordinal"])
            initial = "EXPANDED" if await _expanded_state(control) else "COLLAPSED"
            if initial == "EXPANDED":
                await control.click(timeout=5000)
                await page.wait_for_timeout(250)
            await control.click(timeout=5000)
            await page.wait_for_timeout(450)
            control = await _expandable_locator(page, item["label"], item["ordinal"])
            opened = await _expanded_state(control)
            content = await _expanded_content(control) if opened else ""
            layout = await _layout(page)
            exception = await _has_rendered_exception(page)
            malformed = bool(re.search(r"(?:\bNone\b|\bnull\b|\bnan\b|Traceback|KeyError|TypeError)", content, re.I))
            narrative = dom_fact_findings(content, {}, surface=page_name, ticker=ticker, required=())
            fact_keys: tuple[str, ...] = ()
            if certified_facts:
                if re.search(r"valuation|fair value", item["label"], re.I):
                    fact_keys = ("expected_atlas_fv", "expected_upside")
                elif re.search(r"wall street|analyst target", item["label"], re.I):
                    fact_keys = ("expected_wall_street_target", "expected_wall_street_consensus", "expected_analyst_count")
                elif re.search(r"earnings|estimates", item["label"], re.I):
                    fact_keys = ("expected_forward_eps", "expected_forward_revenue")
            fact_mismatches = dom_fact_findings(
                content, certified_facts or {}, surface=page_name, ticker=ticker, required=fact_keys,
            )
            passed_open = bool(opened and len(content) > len(item["label"]) and not layout["horizontal_overflow"] and not exception and not malformed and not narrative and not fact_mismatches)
            observed = f"opened={opened}; content_chars={len(content)}; overflow={layout['horizontal_overflow']}; exception={exception}; malformed={malformed}; contradictions={len(narrative)}; fact_mismatches={len(fact_mismatches)}"
            defects.extend(fact_mismatches)
            if required or EXPANDABLE_LABEL_RE.search(item["label"]):
                shot = await crawler._shot(
                    page, page_name=page_name, interaction=f"expand-{item['label']}",
                    state="expanded", viewport=viewport, ticker=ticker,
                )
                _annotate_latest_shot(crawler, shot, interaction_manifest_fields(
                    label=item["label"], initial_state="COLLAPSED", final_state="EXPANDED",
                    click_success=opened, expected_content="Visible certified customer content without overflow, exception, malformed values, or contradiction",
                    observed_content=content[:500],
                ))
            # Nested disclosure content is certified while every ancestor is
            # still open; closing the parent first would make the control
            # non-interactable and could create a false QA failure.
            await exercise_nested(control)
            await control.click(timeout=5000)
            await page.wait_for_timeout(300)
            control = await _expandable_locator(page, item["label"], item["ordinal"])
            collapsed = not await _expanded_state(control)
            passed = bool(passed_open and collapsed)
        except Exception as exc:
            passed = False
            observed = f"{type(exc).__name__}: disclosure interaction failed"
        check = {
            "page": page_name, "viewport": viewport, "ticker": ticker,
            "interaction_type": "NESTED_EXPANDER" if item.get("nested") else "EXPANDER",
            "control_label": item["label"], "required": required,
            "initial_state": "COLLAPSED", "final_state": "COLLAPSED" if collapsed else "UNKNOWN",
            "click_success": opened, "collapse_success": collapsed,
            "expected_content": "Expansion reveals valid customer content and collapse restores state",
            "observed_content": content[:500], "observed": observed,
            "status": "PASS" if passed else "FAIL", "screenshot": shot,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
        checks.append(check)
        if required and not passed:
            defects.append({"severity": "P1", "page": page_name, "viewport": viewport,
                            "observed": json.dumps(check, sort_keys=True), "ticker_context": ticker})

    # Prove major disclosures can coexist without layout failure.
    opened_controls: list[tuple[str, int]] = []
    for item in await _expandable_inventory(page):
        if not required_expandable(page_name, item["label"]):
            continue
        try:
            control = await _expandable_locator(page, item["label"], item["ordinal"])
            if not await _expanded_state(control):
                await control.click(timeout=5000)
                await page.wait_for_timeout(180)
            if await _expanded_state(control):
                opened_controls.append((item["label"], int(item["ordinal"])))
        except Exception:
            pass
    all_layout = await _layout(page)
    all_exception = await _has_rendered_exception(page)
    all_pass = len(opened_controls) == sum(required_expandable(page_name, item["label"]) for item in inventory) and not all_layout["horizontal_overflow"] and not all_exception
    all_shot = await crawler._shot(
        page, page_name=page_name, interaction="expandables", state="all-major-expanded",
        viewport=viewport, ticker=ticker,
    )
    _annotate_latest_shot(crawler, all_shot, interaction_manifest_fields(
        label="ALL_MAJOR_SECTIONS", initial_state="COLLAPSED", final_state="EXPANDED",
        click_success=all_pass, expected_content="All required major disclosures open together without layout or render failure",
        observed_content=f"opened={len(opened_controls)}; overflow={all_layout['horizontal_overflow']}; exception={all_exception}",
    ))
    checks.append({"page": page_name, "viewport": viewport, "ticker": ticker,
                   "interaction_type": "ALL_MAJOR_EXPANDED", "control_label": "ALL_MAJOR_SECTIONS",
                   "required": bool(inventory), "initial_state": "COLLAPSED", "final_state": "EXPANDED",
                   "click_success": all_pass, "expected_content": "All major sections coexist",
                   "observed_content": f"opened={len(opened_controls)}", "status": "PASS" if all_pass else "FAIL",
                   "layout": all_layout, "screenshot": all_shot})
    if inventory and not all_pass:
        defects.append({"severity": "P1", "page": page_name, "viewport": viewport,
                        "observed": "ALL_MAJOR_EXPANDED_FAILED", "ticker_context": ticker})
    for label, ordinal in reversed(opened_controls):
        try:
            control = await _expandable_locator(page, label, ordinal)
            if await _expanded_state(control):
                await control.click(timeout=5000)
                await page.wait_for_timeout(120)
        except Exception:
            pass
    return checks, defects


def expected_customer_action(row: dict[str, Any]) -> tuple[str, bool]:
    """Return the governed surface expectation, distinct from raw evaluation state."""
    evaluation = row.get("canonical_investment_evaluation") or {}
    row_certification = row.get("publication_certification") or {}
    evaluation_certification = evaluation.get("publication_certification") or {}
    publication_allowed = bool(row_certification.get("customer_publication_allowed")) and bool(
        evaluation_certification.get("action_publication_eligible")
    )
    if not publication_allowed:
        return "RATING NOT PUBLISHED", False
    action = str(((evaluation.get("guidance") or {}).get("state") or evaluation.get("action") or ""))
    return CUSTOMER_ACTION_LABELS.get(action, action.replace("_", " ")), True


def customer_action_matches(text: str, expected: str, publication_allowed: bool) -> bool:
    if publication_allowed:
        return not expected or expected in text or (expected == "DATA LIMITED" and "WATCH" in text)
    return any(label in text for label in ("RATING NOT PUBLISHED", "MONITOR", "NOT CURRENTLY ACTIONABLE", "DOES NOT PUBLISH"))


def certification_tickers(root: Path) -> list[str]:
    rows = json.loads((root / "market_full_scan.json").read_text(encoding="utf-8"))
    output: list[str] = []
    def add(value: Any) -> None:
        ticker = str(value or "").strip().upper()
        if ticker and ticker not in output:
            output.append(ticker)
    available = {str(row.get("ticker") or "").upper() for row in rows}
    for fixed in ("INTU", "NEM", "SD", "MPLN", "TGT", "NVDA", "BP", "TK", "MKTX", "CXT", "CXW", "REGN", "UBER", "TSM", "ABBV", "MDT", "OVV", "SWKS"):
        if fixed in available:
            add(fixed)
    for row in rows[:3]:
        add(row.get("ticker"))
    def action(row):
        return str((((row.get("canonical_investment_evaluation") or {}).get("guidance") or {}).get("state") or ""))
    # Permanent governed fixtures: every strongest positive/negative outcome,
    # then the top BUILD names and numerical-risk exemplars.
    for row in rows:
        if action(row) in {"BUY_NOW", "AVOID"}:
            add(row.get("ticker"))
    for row in [item for item in rows if action(item) == "ACCUMULATE"][:5]:
        add(row.get("ticker"))
    for state in ("WAIT_FOR_ENTRY", "WAIT_FOR_BETTER_ENTRY"):
        match = next((row for row in rows if action(row) == state), None)
        if match: add(match.get("ticker"))
    def metric(row, key):
        try: return float((row.get("canonical_investment_evaluation") or {}).get(key) or float("-inf"))
        except (TypeError, ValueError): return float("-inf")
    if rows:
        add(max(rows, key=lambda row: metric(row, "opportunity")).get("ticker"))
    def professional(row):
        return (((row.get("canonical_investment_evaluation") or {}).get("atlas_valuation") or {}).get("professional_valuation_v2") or {})
    def published_methods(row):
        return [item for item in professional(row).get("models") or () if isinstance(item, dict) and item.get("status") == "PUBLISHED"]
    def field(row, name):
        item = ((row.get("certified_customer_evaluation") or {}).get("fields") or {}).get(name) or {}
        try: return float(item.get("value"))
        except (TypeError, ValueError): return float("-inf")
    selectors = (
        lambda r: len(published_methods(r)) == 1,
        lambda r: len(published_methods(r)) > 1,
        lambda r: str(((r.get("wall_street_analysis") or {}).get("status") or "")).upper() == "PARTIAL",
        lambda r: not bool((r.get("wall_street_analysis") or {}).get("consensus")),
        lambda r: str(r.get("security_type") or "").upper() in {"ADR", "ADS"},
        lambda r: field(r, "forward_eps") == float("-inf") or field(r, "forward_revenue") == float("-inf"),
        lambda r: (r.get("homepage_promotion_eligibility") or {}).get("eligible") is False,
    )
    for selector in selectors:
        match = next((row for row in rows if selector(row)), None)
        if match: add(match.get("ticker"))
    for name in ("atlas_upside_pct", "operating_margin_pct", "market_cap"):
        valid = [row for row in rows if field(row, name) != float("-inf")]
        if valid:
            add(max(valid, key=lambda row: field(row, name)).get("ticker"))
            add(min(valid, key=lambda row: field(row, name)).get("ticker"))
    predicates = (
        lambda r: ((r.get("canonical_investment_evaluation") or {}).get("atlas_valuation") or {}).get("professional_valuation_v2", {}).get("status") == "PUBLISHED",
        lambda r: ((r.get("canonical_investment_evaluation") or {}).get("atlas_valuation") or {}).get("professional_valuation_v2", {}).get("status") != "PUBLISHED",
        lambda r: ((r.get("canonical_investment_evaluation") or {}).get("guidance") or {}).get("state") == "DATA_LIMITED",
    )
    for predicate in predicates:
        match = next((row for row in rows if predicate(row)), None)
        if match:
            add(match.get("ticker"))
    full_pool_path = root / "full_evaluation_pool.json"
    if full_pool_path.exists():
        full_pool = json.loads(full_pool_path.read_text(encoding="utf-8"))
        outside = next((row for row in full_pool if str(row.get("ticker") or row.get("symbol") or "").upper() not in available), None)
        if outside:
            add(outside.get("ticker") or outside.get("symbol"))
    return output


async def _layout(page) -> dict[str, Any]:
    return await page.evaluate("""() => {
      const visible = [...document.querySelectorAll('body *')].filter(e => {
        const s=getComputedStyle(e), r=e.getBoundingClientRect();
        return s.visibility!=='hidden' && s.display!=='none' && r.width>2 && r.height>2;
      });
      const clipped = visible.filter(e => e.scrollWidth > e.clientWidth + 2 && getComputedStyle(e).overflowX === 'hidden').length;
      return {horizontal_overflow: document.documentElement.scrollWidth > innerWidth + 2, clipped_nodes: clipped,
              body_text_length: (document.body.innerText || '').trim().length};
    }""")


async def run(args: argparse.Namespace) -> int:
    started = time.monotonic()
    mode = args.mode
    timing = TimingReport(mode=mode, ceiling_seconds=float(args.runtime_ceiling_seconds))
    root, output = Path(args.root).resolve(), Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    exact_mode = os.environ.get("ATLAS_EXACT_CANDIDATE_QA", "").lower() == "true"
    target_ok, target_failure = validate_runtime_target(args.url, exact_candidate_mode=exact_mode)
    if not target_ok:
        raise RuntimeError(target_failure)
    identity = candidate_identity(Path(args.candidate_dir).resolve(), code_sha=os.environ.get("GITHUB_SHA"), run_id=args.candidate_run_id)
    if not identity["valid"]:
        raise RuntimeError("EXACT_CANDIDATE_BINDING_FAILED:" + ",".join(identity["failure_reasons"]))
    crawler = AtlasVisualCrawler(url=args.url, output_dir=output, root=root)
    original_shot = crawler._shot
    async def budgeted_shot(page, *, page_name: str, interaction: str, state: str,
                            viewport: str = "desktop", ticker: str = "", complete_surface: bool = False):
        budget = SCREENSHOT_BUDGETS.get(page_name, {}).get(viewport)
        prior = [item for item in crawler.manifest if item.get("page") == page_name and item.get("viewport") == viewport and item.get("path")]
        if budget is not None and len({item["path"] for item in prior}) >= budget and state != "failure":
            crawler.screenshot_calls_avoided += 1
            path = prior[-1]["path"]
            crawler.manifest.append({"page": page_name, "interaction": interaction, "state": state,
                                     "ticker": ticker, "viewport": viewport, "path": path,
                                     "generated": True, "deduplicated": True, "budget_reused": True,
                                     "capture": "budget_reused", "segments": 0, "complete": True})
            return path
        return await original_shot(page, page_name=page_name, interaction=interaction, state=state,
                                   viewport=viewport, ticker=ticker, complete_surface=complete_surface)
    crawler._shot = budgeted_shot  # type: ignore[method-assign]
    source_rows = json.loads((root / "market_full_scan.json").read_text(encoding="utf-8"))
    by_ticker = {str(row.get("ticker") or "").upper(): row for row in source_rows}
    full_pool_path = root / "full_evaluation_pool.json"
    if full_pool_path.exists():
        for row in json.loads(full_pool_path.read_text(encoding="utf-8")):
            by_ticker.setdefault(str(row.get("ticker") or row.get("symbol") or "").upper(), row)
    defects: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    dom_dir = output / "dom_snapshots"
    dom_dir.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not args.headed)
        context = await browser.new_context(viewport=DESKTOP)
        page = await context.new_page()
        try:
            crawler.authentication = await bounded_operation(
                "auth", lambda: _open_and_authenticate(
                    page, args.url, output, expected_sha=crawler.source_sha,
                    allow_local_exact_candidate=True,
                ), timeout=OPERATION_TIMEOUTS["authentication"], timing=timing, retries=1,
            )
            for viewport, size in (("desktop", DESKTOP), ("mobile", MOBILE)):
                await page.set_viewport_size(size)
                pages = REQUIRED_PAGES if mode == "RELEASE_FULL" else ("Home", "Research Any Ticker")
                for name in pages:
                    timing.enforce(f"structural:{viewport}:{name}")
                    page_started = time.monotonic()
                    ok = await bounded_operation("navigation", lambda n=name, v=viewport: crawler._page_visit(page, n, viewport=v),
                                                 timeout=OPERATION_TIMEOUTS["navigation"], timing=timing, retries=1)
                    layout = await bounded_operation("dom", lambda: _layout(page), timeout=OPERATION_TIMEOUTS["dom"], timing=timing)
                    shot = await crawler._shot(page, page_name=name, interaction="master-certification", state="settled", viewport=viewport, complete_surface=True)
                    passed = bool(ok and not layout["horizontal_overflow"] and layout["body_text_length"] > 100)
                    check = {"page": name, "viewport": viewport, "status": "PASS" if passed else "FAIL", "layout": layout, "screenshot": shot}
                    checks.append(check)
                    if not passed:
                        defects.append({"severity": "P1", "page": name, "viewport": viewport,
                                        "observed": json.dumps(layout, sort_keys=True), "ticker_context": ""})
                        timing.record("page-certification", time.monotonic() - page_started,
                                      stage="structural", page=name, viewport=viewport)
                        # A broken structural contract cannot be made safer by
                        # spending minutes traversing its disclosure controls.
                        continue
                    interaction_checks, interaction_defects = await certify_expandable_interactions(
                        page, crawler, page_name=name, viewport=viewport,
                    )
                    checks.extend(interaction_checks)
                    defects.extend(interaction_defects)
                    timing.record("page-certification", time.monotonic() - page_started,
                                  stage="structural", page=name, viewport=viewport)
                    (dom_dir / f'{viewport}_{name.lower().replace(" ", "_")}.json').write_text(json.dumps({
                        "page": name, "viewport": viewport, "text": await _visible_text(page),
                        "qa_attributes": await page.evaluate("""() => [...document.querySelectorAll('[data-atlas-qa]')].map(e => Object.fromEntries([...e.attributes].filter(a => a.name.startsWith('data-atlas-')).map(a => [a.name,a.value])))"""),
                    }, indent=2), encoding="utf-8")
            await page.set_viewport_size(DESKTOP)
            visual_tickers = certification_tickers(root)
            if mode == "FAST_PREVIEW":
                visual_tickers = visual_tickers[:2]
            for index, ticker in enumerate(visual_tickers):
                # One key ticker receives the complete paid evidence-drawer/tab
                # journey; the remaining archetypes certify exact ticker/action
                # reconciliation without multiplying provider/runtime work.
                timing.enforce(f"research:{ticker}")
                ticker_started = time.monotonic()
                passed = await bounded_operation(
                    "research", lambda t=ticker, i=index: crawler._submit_research(page, t, tabs=i == 0, viewport="desktop"),
                    timeout=OPERATION_TIMEOUTS["research"], timing=timing, retries=1,
                )
                timing.record("research-ticker", time.monotonic() - ticker_started, stage="interaction",
                              page="Research Any Ticker", ticker=ticker, viewport="desktop", interaction_type="research")
                decision_tab = await crawler._fresh_visible_tab(page, "Decision")
                if decision_tab is not None:
                    await decision_tab.click(timeout=6000)
                    await page.wait_for_timeout(500)
                if index == 0:
                    interaction_checks, interaction_defects = await certify_expandable_interactions(
                        page, crawler, page_name="Paid Detail", viewport="desktop", ticker=ticker,
                        certified_facts=expected_facts(by_ticker[ticker]),
                    )
                    checks.extend(interaction_checks)
                    defects.extend(interaction_defects)
                layout = await _layout(page)
                text = (await _visible_text(page)).upper().replace("_", " ")
                ticker_facts = expected_facts(by_ticker[ticker])
                expected_action, publication_allowed = expected_customer_action(by_ticker[ticker])
                # Outside-Top-150 research is a fresh governed evaluation, not
                # a promise that the earlier discovery snapshot Action persists.
                safe_incomplete = "CANNOT CERTIFY A COMPLETE INVESTMENT RATING" in text
                action_match = (safe_incomplete or customer_action_matches(text, expected_action, publication_allowed)) if ticker in {str(row.get("ticker") or "").upper() for row in source_rows} else passed
                checks.append({"page": "Research Any Ticker", "viewport": "desktop", "ticker": ticker,
                               "status": "PASS" if passed and action_match and not layout["horizontal_overflow"] else "FAIL",
                               "canonical_action": expected_action, "publication_allowed": publication_allowed,
                               "surface_action_match": action_match, "layout": layout})
                # A fresh Research reassessment may correctly fail closed when
                # current evidence cannot certify a complete rating.  Preserve
                # the existing safe-incomplete contract instead of comparing
                # that state to the earlier immutable discovery Action.
                required_facts = () if safe_incomplete else ("expected_action",)
                defects.extend(dom_fact_findings(
                    text, ticker_facts, surface="RESEARCH", ticker=ticker,
                    required=required_facts,
                ))
                (dom_dir / f"research_{ticker}.json").write_text(json.dumps({
                    "page": "Research Any Ticker", "ticker": ticker, "text": await _visible_text(page),
                    "expected_action": expected_action, "publication_allowed": publication_allowed,
                }, indent=2), encoding="utf-8")
                if not passed or not action_match or layout["horizontal_overflow"]:
                    defects.append({"severity": "P1", "page": "Research Any Ticker", "viewport": "desktop",
                                    "observed": f"ticker={ticker}; action_match={action_match}; layout={json.dumps(layout, sort_keys=True)}", "ticker_context": ticker})
            if visual_tickers:
                mobile_ticker = visual_tickers[0]
                await page.set_viewport_size(MOBILE)
                mobile_passed = await crawler._submit_research(page, mobile_ticker, tabs=True, viewport="mobile")
                interaction_checks, interaction_defects = await certify_expandable_interactions(
                    page, crawler, page_name="Paid Detail", viewport="mobile", ticker=mobile_ticker,
                    certified_facts=expected_facts(by_ticker[mobile_ticker]),
                )
                checks.extend(interaction_checks)
                defects.extend(interaction_defects)
                if not mobile_passed:
                    defects.append({"severity": "P1", "page": "Paid Detail", "viewport": "mobile",
                                    "observed": "PAID_DETAIL_MOBILE_RENDER_FAILED", "ticker_context": mobile_ticker})
        finally:
            await context.close()
            await browser.close()
    existing = {(item.get("page") or item.get("surface"), item.get("ticker_context", item.get("ticker", "")), str(item.get("observed"))) for item in defects}
    for result in crawler.results:
        if result.status == "FAIL" and result.severity in {"P0", "P1", "P2"}:
            key = (result.page, result.ticker_context, str(result.observed))
            if key not in existing:
                defects.append({"severity": result.severity, "page": result.page,
                                "viewport": result.viewport, "observed": result.observed,
                                "ticker_context": result.ticker_context})
                existing.add(key)
    manifest = enrich_manifest(crawler.manifest, source_rows, identity)
    findings = analyze_capture(manifest, checks, identity)
    for item in defects:
        if item.get("finding_id"):
            findings.append(item)
        elif not any(f.get("surface") == item.get("page") and f.get("ticker") == item.get("ticker_context") for f in findings):
            from agents.visual_qa_certification_v2 import finding
            findings.append(finding(severity=item.get("severity", "P2"), category="STRUCTURAL_ASSERTION",
                                    surface=item.get("page", "UNKNOWN"), issue="CRAWLER_ASSERTION_FAILED",
                                    expected="PASS", observed=item.get("observed"), ticker=item.get("ticker_context")))
    repair_attempts = []
    for item in findings:
        decision = repair_decision(item, 0)
        repair_attempts.append({"finding_id": item.get("finding_id"), **decision,
                                "note": "No deterministic registered repair handler; financial and unregistered defects remain fail-closed."})
    final = visual_summary(identity, manifest, findings, duration_seconds=time.monotonic() - started, repair_attempts=repair_attempts)
    authentication_success = bool(crawler.authentication) and crawler.authentication.get("authentication_success", True) is True
    completion = visual_completion_contract(
        finished=True, authentication_success=authentication_success, checks=checks,
        manifest=manifest, mode=mode, candidate_binding_valid=bool(identity["valid"]),
    )
    if not completion["passed"]:
        final["publication_status"] = "FAIL"
        final["promotion_allowed"] = False
    summary = {"version": VERSION, "generated_at": datetime.now(timezone.utc).isoformat(),
               "status": final["publication_status"], "checks": checks, "defects": findings,
               "screenshot_manifest": manifest, "ticker_fixtures": certification_tickers(root),
               "candidate_identity": identity, **final}
    summary["mode"] = mode
    summary["completion_contract"] = completion
    summary["screenshot_budget_usage"] = {
        page: {viewport: len({item.get("file_path") or item.get("path") for item in manifest
                             if item.get("page") == page and item.get("viewport") == viewport and (item.get("file_path") or item.get("path"))})
               for viewport in ("desktop", "mobile")} for page in SCREENSHOT_BUDGETS
    }
    (output / "atlas_full_qa_visual_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (output / "screenshot_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (output / "visual_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (output / "visual_findings.json").write_text(json.dumps(findings, indent=2), encoding="utf-8")
    (output / "visual_summary.json").write_text(json.dumps(final, indent=2), encoding="utf-8")
    (output / "repair_attempts.json").write_text(json.dumps(repair_attempts, indent=2), encoding="utf-8")
    (output / "build_provenance.json").write_text(json.dumps(identity, indent=2), encoding="utf-8")
    (output / "market_runtime_health.json").write_text(json.dumps({"status": "CAPTURED_IN_DOM", "dom_snapshot_directory": "dom_snapshots"}, indent=2), encoding="utf-8")
    (output / "home_runtime_health.json").write_text(json.dumps({"status": "CAPTURED_IN_DOM", "dom_snapshot_directory": "dom_snapshots"}, indent=2), encoding="utf-8")
    (output / "test_results.json").write_text(json.dumps({"visual_checks": len(checks), "status": final["publication_status"]}, indent=2), encoding="utf-8")
    for check in checks:
        if check.get("interaction_type") and check.get("elapsed_seconds") is not None:
            timing.record("interaction-check", float(check["elapsed_seconds"]), stage="interaction",
                          page=check.get("page"), ticker=check.get("ticker"), viewport=check.get("viewport"),
                          interaction_type=check.get("interaction_type"))
    (output / "qa_timing_report.json").write_text(json.dumps(timing.payload(crawler), indent=2), encoding="utf-8")
    candidate_manifest = Path(args.candidate_dir).resolve() / "publication_manifest.json"
    if candidate_manifest.exists():
        (output / "publication_manifest.json").write_bytes(candidate_manifest.read_bytes())
    for folder in (output / "screenshots" / "before", output / "screenshots" / "after", output / "screenshots" / "final"):
        folder.mkdir(parents=True, exist_ok=True)
    # Compact canonical bundle layout; compatibility files above remain for
    # existing report consumers during the migration.
    for folder in (output / "final", output / "anomalies", output / "manifest",
                   output / "dom", output / "findings", output / "timings"):
        folder.mkdir(parents=True, exist_ok=True)
    shutil.copy2(output / "visual_manifest.json", output / "manifest" / "visual_manifest.json")
    shutil.copy2(output / "visual_findings.json", output / "findings" / "visual_findings.json")
    shutil.copy2(output / "qa_timing_report.json", output / "timings" / "qa_timing_report.json")
    for dom_file in dom_dir.glob("*.json"):
        shutil.copy2(dom_file, output / "dom" / dom_file.name)
    for item in manifest:
        relative = item.get("file_path")
        source = output / str(relative or "")
        if source.is_file():
            shutil.copy2(source, output / "screenshots" / "final" / source.name)
            shutil.copy2(source, output / "final" / source.name)
    return 0 if final["publication_status"] == "PASS" else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--root", default=".")
    parser.add_argument("--candidate-dir", default="audit_results/candidate_artifacts")
    parser.add_argument("--candidate-run-id", default=None)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--mode", choices=QA_MODES, default="RELEASE_FULL")
    parser.add_argument("--runtime-ceiling-seconds", type=float, default=5400.0)
    args = parser.parse_args()
    try:
        return asyncio.run(run(args))
    except Exception as exc:
        # Even startup/auth/navigation failures must leave bounded, machine-
        # readable timing evidence rather than an empty artifact directory.
        output = Path(args.output).resolve()
        output.mkdir(parents=True, exist_ok=True)
        timing_path = output / "qa_timing_report.json"
        if not timing_path.exists():
            timing_path.write_text(json.dumps({
                "version": VERSION, "mode": args.mode, "status": "FAILED",
                "failure": type(exc).__name__, "runtime_ceiling_seconds": args.runtime_ceiling_seconds,
                "stages": {}, "retry_counts": {}, "timeouts": [],
            }, indent=2) + "\n", encoding="utf-8")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
