"""One-shot A/B diagnostic for exact-candidate Research submission context."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any

from playwright.async_api import Page, WebSocket, async_playwright

from agents.atlas_runtime_qa_v3 import _open_and_authenticate
from agents.atlas_visual_crawler_v1 import AtlasVisualCrawler, DESKTOP, _scopes
from agents.full_qa_visual_certification import open_authenticated_research_page


def _sha(root: Path) -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


def _classify_frame(payload: bytes | str, ticker: str) -> dict[str, Any]:
    raw = payload.encode("utf-8", "replace") if isinstance(payload, str) else bytes(payload)
    lowered = raw.lower()
    terms = {
        "ticker_value": ticker.encode().lower() in lowered,
        "submit_token": any(term in lowered for term in (b"submit", b"form_submit", b"research ticker")),
        "widget_state": any(term in lowered for term in (b"widget", b"backmsg", b"rerun")),
    }
    if terms["submit_token"]:
        classification = "SUBMIT_OR_BUTTON_TRIGGER"
    elif terms["ticker_value"]:
        classification = "TICKER_VALUE_COMMIT"
    else:
        classification = "UNRELATED_OR_BINARY_UNCLASSIFIED"
    return {
        "at_monotonic": time.monotonic(),
        "size": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "binary": isinstance(payload, bytes),
        "classification": classification,
        **terms,
    }


async def _marker_state(page: Page, ticker: str) -> dict[str, Any]:
    rerun = 0
    submitted = False
    terminal = ""
    exact_context = False
    for scope in _scopes(page):
        stages = scope.locator(
            '[data-atlas-qa="research-entry-stage"][data-atlas-stage="RESEARCH_ROUTE_ENTERED"]'
        )
        for index in range(await stages.count()):
            rerun = max(rerun, int(await stages.nth(index).get_attribute("data-atlas-rerun-count") or 0))
        submitted = submitted or bool(await scope.locator(
            f'[data-atlas-qa="research-submission-observed"]'
            f'[data-atlas-submitted="true"][data-atlas-ticker="{ticker}"]'
        ).count())
        containers = scope.locator(
            f'[data-atlas-qa="research-container"][data-atlas-ticker="{ticker}"]'
        )
        for index in range(await containers.count()):
            terminal = await containers.nth(index).get_attribute("data-atlas-status") or terminal
        exact_context = exact_context or bool(await scope.locator(
            f'[data-atlas-qa="research-context-v1"][data-atlas-ticker="{ticker}"]'
        ).count())
    return {
        "rerun": rerun,
        "submission_marker": submitted,
        "terminal_lifecycle": terminal,
        "exact_ticker_context": exact_context,
    }


async def _visibility(page: Page) -> str:
    return str(await page.evaluate("document.visibilityState"))


async def _attempt(
    *, crawler: AtlasVisualCrawler, page: Page, context: Any, ticker: str,
    bring_to_front: bool,
) -> dict[str, Any]:
    await crawler._page_visit(page, "Research Any Ticker", viewport="desktop")
    input_node, button, controls = await crawler._stable_research_controls(page)
    form = button.locator('xpath=ancestor::*[@data-testid="stForm"][1]')
    await page.evaluate("""() => {
      globalThis.__atlasDiagnostic = {visibility: [], dom: []};
      document.addEventListener('visibilitychange', () => {
        globalThis.__atlasDiagnostic.visibility.push({state: document.visibilityState, at: performance.now()});
      });
    }""")
    await button.evaluate("""button => {
      const sink = globalThis.__atlasDiagnostic.dom;
      for (const name of ['pointerdown', 'mousedown', 'click']) {
        button.addEventListener(name, event => sink.push({event: name, trusted: event.isTrusted, at: performance.now()}));
      }
      const form = button.closest('form') || button.closest('[data-testid="stForm"]');
      if (form) form.addEventListener('submit', event => sink.push({event: 'submit', trusted: event.isTrusted, at: performance.now()}));
    }""")
    await input_node.fill(ticker)
    before = await _marker_state(page, ticker)
    visibility_before = await _visibility(page)
    if bring_to_front:
        await page.bring_to_front()
    visibility_after_front = await _visibility(page)
    visibility_before_click = await _visibility(page)
    pages = []
    for item in context.pages:
        pages.append({"url": item.url, "visibility": await _visibility(item)})
    click_at = time.monotonic()
    outcome = "RETURNED_NORMALLY"
    error = ""
    try:
        await asyncio.wait_for(button.click(), timeout=5.0)
        await page.wait_for_timeout(250)
    except asyncio.TimeoutError:
        outcome = "TIMED_OUT"
        error = "TimeoutError"
    except asyncio.CancelledError:
        outcome = "CANCELLED"
        error = "CancelledError"
        raise
    except Exception as exc:
        outcome = "RAISED"
        error = type(exc).__name__
    visibility_after_click = await _visibility(page)
    await page.wait_for_timeout(7750)
    after = await _marker_state(page, ticker)
    completed = await crawler._completed_research(page, ticker)
    events = await page.evaluate("globalThis.__atlasDiagnostic")
    return {
        "bring_to_front": bring_to_front,
        "controls": controls,
        "visibility": {
            "before_bring_to_front": visibility_before,
            "after_bring_to_front": visibility_after_front,
            "immediately_before_click": visibility_before_click,
            "approximately_250ms_after_click": visibility_after_click,
            "transitions": events.get("visibility", []),
        },
        "dom_events": events.get("dom", []),
        "markers_before": before,
        "markers_after": after,
        "completed_research": completed,
        "asyncio_wrapper": {
            "outcome": outcome,
            "error": error,
            "seconds_after_click": round(time.monotonic() - click_at, 3),
        },
        "page_inventory": {"count": len(context.pages), "pages": pages},
        "passed": bool(completed.get("complete")),
    }


async def run(args: argparse.Namespace) -> dict[str, Any]:
    root = args.root.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    crawler = AtlasVisualCrawler(url=args.url, output_dir=output, root=root, headless=True)
    source_sha = _sha(root)
    websocket_frames: dict[str, list[dict[str, Any]]] = {"without": [], "with": []}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(viewport=DESKTOP)
        auth_page = await context.new_page()
        auth_page.on("websocket", crawler._track_streamlit_websocket)
        await _open_and_authenticate(
            auth_page, args.url, output, expected_sha=source_sha,
            allow_local_exact_candidate=True,
        )

        results = {}
        for label, foreground in (("without", False), ("with", True)):
            page = await open_authenticated_research_page(
                context, crawler, url=args.url, output=output,
                expected_sha=source_sha, viewport=DESKTOP,
            )
            def attach(ws: WebSocket, *, target=label) -> None:
                ws.on("framesent", lambda payload: websocket_frames[target].append(
                    _classify_frame(payload, "NVDA")
                ))
            page.on("websocket", attach)
            sentinel = await context.new_page()
            await sentinel.goto("about:blank")
            await sentinel.bring_to_front()
            results[label] = await _attempt(
                crawler=crawler, page=page, context=context, ticker="NVDA",
                bring_to_front=foreground,
            )
            results[label]["websocket_frames"] = websocket_frames[label]
            await page.close()
            await sentinel.close()
        await context.close()
        await browser.close()
    payload = {
        "source_sha": source_sha,
        "provider_calls": 0,
        "ticker": "NVDA",
        "without_bring_to_front": results["without"],
        "with_bring_to_front": results["with"],
    }
    (output / "research_context_ab.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8501")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
