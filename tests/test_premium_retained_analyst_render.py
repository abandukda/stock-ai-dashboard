"""Actual retained-file reader -> customer projection -> responsive Research UI."""
import os
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright
from test_premium_home_render import capture_complete_streamlit


class PremiumRetainedAnalystRender(unittest.TestCase):
    def test_valid_malformed_and_zero_coverage_at_three_sizes(self):
        target = Path("audit_results/premium_research/retained_analyst")
        target.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="atlas-generated-analyst-") as temporary:
            root = Path(temporary)
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            env = dict(os.environ, PYTHONPATH=str(Path.cwd()),
                       STREAMLIT_GLOBAL_DEVELOPMENT_MODE="false",
                       ATLAS_GENERATED_ANALYST_ROOT=str(root), ATLAS_QA_PROVIDER_CALLS_ALLOWED="0",
                       ATLAS_ALLOW_EXTERNAL_AI="false", ATLAS_CUSTOMER_REPORT_CARD_ENABLED="false")
            with (target / "GENERATED_server.log").open("w") as log:
                process = subprocess.Popen([
                    sys.executable, "-m", "streamlit", "run", "scripts/retained_analyst_review_fixture.py",
                    "--server.address=127.0.0.1", f"--server.port={port}", "--server.headless=true",
                    "--browser.gatherUsageStats=false", "--theme.base=dark",
                ], env=env, stdout=log, stderr=subprocess.STDOUT)
                try:
                    deadline = time.monotonic() + 30
                    while time.monotonic() < deadline:
                        self.assertIsNone(process.poll(), "Generated Research fixture exited")
                        with socket.socket() as probe:
                            if probe.connect_ex(("127.0.0.1", port)) == 0:
                                break
                        time.sleep(.2)
                    else:
                        self.fail("Generated retained Research startup timed out")
                    with sync_playwright() as pw:
                        browser = pw.chromium.launch(headless=True)
                        try:
                            for mode in ("valid", "malformed", "zero", "literal", "target_missing", "target_invalid", "flag_off", "eps_valid"):
                                for width in (360, 768, 1440):
                                    context = browser.new_context(viewport={"width": width, "height": 1000})
                                    external = []

                                    def route(request):
                                        url = urlsplit(request.request.url)
                                        if url.hostname == "127.0.0.1" and url.port == port:
                                            request.continue_()
                                        else:
                                            external.append(request.request.url)
                                            request.abort()

                                    context.route("**/*", route)
                                    page = context.new_page()
                                    try:
                                        page.goto(f"http://127.0.0.1:{port}/?mode={mode}")
                                        marker = page.locator('[data-retained-analyst-fixture-complete="true"]')
                                        marker.wait_for(state="attached", timeout=30000)
                                        self.assertEqual(page.locator('[data-testid="stException"]').count(), 0)
                                        self.assertEqual(marker.get_attribute("data-mode"), mode)
                                        self.assertEqual(marker.get_attribute("data-cache-source"), "PRIMARY")
                                        self.assertEqual(marker.get_attribute("data-history-status"), "MISSING")
                                        self.assertEqual(marker.get_attribute("data-provider-calls"), "0")
                                        self.assertEqual(marker.get_attribute("data-action"), "BUY NOW")
                                        self.assertEqual(marker.get_attribute("data-fair-value"), "346.05")
                                        expected_count = {"valid": "6", "malformed": "NONE", "zero": "0", "literal": "6", "target_missing": "6", "target_invalid": "6", "flag_off": "NONE", "eps_valid": "6"}[mode]
                                        self.assertEqual(marker.get_attribute("data-analyst-count"), expected_count)
                                        positive = mode in {"valid", "literal", "target_missing", "target_invalid", "eps_valid"}
                                        self.assertEqual(marker.get_attribute("data-consensus"), "Strong Buy" if positive else "NONE")
                                        self.assertEqual(marker.get_attribute("data-accepted-family-count"), {"malformed": "1", "literal": "3", "target_missing": "1", "target_invalid": "1", "eps_valid": "3"}.get(mode, "2"))
                                        self.assertEqual(marker.get_attribute("data-rejected-family-count"), "1" if mode in {"malformed", "target_invalid"} else "0")
                                        if mode != "flag_off":
                                            consensus = page.locator('[data-testid="stMetric"]').filter(
                                                has=page.get_by_text("Consensus", exact=True),
                                            ).locator('[data-testid="stMetricValue"]')
                                            self.assertEqual(consensus.inner_text(), "Strong Buy" if positive else "Unavailable")
                                            self.assertTrue(consensus.evaluate("e => e.scrollWidth <= e.clientWidth + 1"), "Consensus must remain readable")
                                            if mode == "zero":
                                                page.get_by_text("No recommendations are recorded for this period; ATLAS does not infer a consensus.", exact=True).wait_for()
                                                page.get_by_text("0 analysts · recommendation period", exact=False).wait_for()
                                            elif positive:
                                                page.get_by_text("6 analysts · recommendation period", exact=False).wait_for()
                                            else:
                                                page.get_by_text("Unavailable analysts · recommendation period", exact=False).wait_for()
                                                self.assertNotIn("unknown", page.inner_text("body"))
                                            caption = page.get_by_text("analysts · recommendation period", exact=False)
                                            self.assertIn("target as of", caption.inner_text())
                                            if mode not in {"target_missing", "target_invalid"}:
                                                self.assertIn("provider calendar date · timezone unspecified", caption.inner_text())
                                            self.assertNotIn("UTC", caption.inner_text())
                                            if not positive:
                                                self.assertNotIn("Strong Buy", page.inner_text("body"))
                                        else:
                                            self.assertEqual(marker.get_attribute("data-wall-status"), "DISABLED")
                                            page.get_by_text("Wall Street context is unavailable for this evidence bundle.", exact=True).wait_for()
                                            self.assertNotIn("Strong Buy", page.inner_text("body"))
                                        if mode in {"zero", "malformed", "target_missing", "target_invalid"}:
                                            self.assertEqual(marker.get_attribute("data-wall-status"), "PARTIAL")
                                        # Inspect real Vega SVG marks, not projected JSON or screenshot pixels.
                                        chart = page.locator('[data-testid="stVegaLiteChart"]:visible').first
                                        chart.scroll_into_view_if_needed()
                                        bars = chart.locator('svg path[role="graphics-symbol"][aria-label^="Reference:"]')
                                        expected_labels = {"Last Certified Close", "ATLAS Fair Value"}
                                        if mode not in {"target_missing", "target_invalid", "flag_off"}:
                                            expected_labels.add("Wall St. Average")
                                        bars.first.wait_for(state="visible")
                                        self.assertEqual(bars.count(), len(expected_labels))
                                        geometry = bars.evaluate_all("""es => es.map(e => ({
                                            label:e.getAttribute('aria-label'), box:e.getBoundingClientRect().toJSON(),
                                            svg:e.ownerSVGElement.getBoundingClientRect().toJSON()
                                        }))""")
                                        self.assertEqual({item["label"].split(";",1)[0].removeprefix("Reference: ") for item in geometry}, expected_labels)
                                        for item in geometry:
                                            box, svg = item["box"], item["svg"]
                                            self.assertGreater(box["width"], 0)
                                            self.assertGreater(box["height"], 0)
                                            self.assertGreaterEqual(box["left"], max(0, svg["left"])-1)
                                            self.assertLessEqual(box["right"], min(width, svg["right"])+1)
                                        (target / f"GENERATED_NOT_PRODUCTION_{mode}_{width}_chart.json").write_text(json.dumps(geometry, indent=2))
                                        chart.screenshot(path=str(target / f"GENERATED_NOT_PRODUCTION_{mode}_{width}_chart.png"))
                                        if mode == "literal":
                                            headline = 'NVDA generated headline ![pixel](https://example.invalid/news-pixel) [details](https://example.invalid/story) <img src="https://example.invalid/raw"> & evidence'
                                            publisher = 'Generated publisher ![publisher](https://example.invalid/publisher-pixel) [site](https://example.invalid/publisher) <b>Publisher</b> & attribution'
                                            page.get_by_text("What changed: a headline or a change in the business?", exact=True).click()
                                            headlines = page.locator("p.atlas-retained-context-literal").filter(has_text=headline)
                                            publishers = page.locator("p.atlas-retained-context-literal").filter(has_text=publisher)
                                            self.assertEqual(headlines.count(), 2, "Both main and beginner news surfaces must preserve literal source")
                                            self.assertEqual(publishers.count(), 2)
                                            for item in headlines.all():
                                                self.assertEqual(item.inner_text(), headline)
                                                self.assertTrue(item.is_visible())
                                            for item in publishers.all():
                                                self.assertTrue(item.inner_text().startswith(publisher + " · "))
                                                self.assertTrue(item.is_visible())
                                            self.assertEqual(page.locator('img[src*="example.invalid"], a[href*="example.invalid"]').count(), 0)
                                        earnings_heading = page.get_by_role("heading", name="Retained reported EPS", exact=True)
                                        if mode == "eps_valid":
                                            earnings_heading.wait_for()
                                            earnings_heading.scroll_into_view_if_needed()
                                            table = page.locator('[data-testid="stTable"]').filter(has_text="Actual EPS · provider units")
                                            self.assertEqual(table.count(), 1)
                                            text = table.inner_text()
                                            for value in ("2026-07-31", "2026-04-30", "2026-01-31", "1.2", "-3.25", "0", "-1"):
                                                self.assertIn(value, text)
                                            self.assertNotIn("$", text)
                                            self.assertNotIn("USD", text)
                                            page.get_by_text("Currency, accounting basis and split comparability are unverified. Actual and estimate values are shown separately; no earnings beat, miss or surprise is inferred.", exact=True).wait_for()
                                            page.get_by_text("Period end is not the announcement or publication date.", exact=False).wait_for()
                                            source = page.get_by_text("Source: FINNHUB_RETAINED_EVIDENCE", exact=False)
                                            source.wait_for()
                                            self.assertIn("Oct 23, 2026 · 12:00 AM UTC", source.inner_text())
                                            earnings_heading.scroll_into_view_if_needed()
                                            page.screenshot(path=str(target / f"GENERATED_NOT_PRODUCTION_{mode}_{width}_earnings.png"))
                                            self.assertNotIn("earnings beat", table.inner_text().lower())
                                        else:
                                            self.assertEqual(earnings_heading.count(), 0, "Missing EPS evidence must not be invented")
                                        loading = '[data-stale="true"], [data-testid*="Skeleton"], [data-testid*="skeleton"]'
                                        page.wait_for_function('''selector => ![...document.querySelectorAll(selector)].some(e => {
                                            const r=e.getBoundingClientRect(),s=getComputedStyle(e);
                                            return r.width>0&&r.height>0&&s.display!=="none"&&s.visibility!=="hidden";
                                        })''', arg=loading, timeout=10000)
                                        self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), width + 1)
                                        capture_complete_streamlit(page, target / f"GENERATED_NOT_PRODUCTION_{mode}_{width}.png")
                                        self.assertEqual(external, [])
                                        self.assertFalse((root / "network_attempts.log").exists())
                                    except Exception:
                                        page.screenshot(path=str(target / f"FAILED_{mode}_{width}.png"), full_page=True)
                                        (target / f"FAILED_{mode}_{width}_DOM.html").write_text(page.content())
                                        raise
                                    finally:
                                        context.close()
                        finally:
                            browser.close()
                finally:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
