"""Provider-free layout contracts; generated renders remain a separate acceptance gate."""
from pathlib import Path
import unittest
from unittest.mock import patch

from ui.research_reference_components import fundamentals_cards_html, RESEARCH_REFERENCE_CSS


class PremiumResearchComposition(unittest.TestCase):
    def test_source_values_are_escaped_without_recalculation_or_missing_value_inference(self):
        facts = [{"fact_name": "P/E <reported>", "display_value": "Unavailable"},
                 {"fact_name": "Revenue", "display_value": "$12.34B <source>"}]
        html = fundamentals_cards_html(facts)
        self.assertEqual(html.count("<article>"), 2)
        self.assertIn("P/E &lt;reported&gt;", html)
        self.assertIn("$12.34B &lt;source&gt;", html)
        self.assertIn("Unavailable", html)
        self.assertNotIn("0.0", html)
        self.assertEqual(facts[0]["display_value"], "Unavailable")

    def test_chart_and_single_digest_precede_reading_modes_with_tablet_and_mobile_stacking(self):
        source = Path("ui/customer_research_v2.py").read_text()
        renderer = source[source.index("def render_customer_research_v2("):]
        self.assertLess(renderer.index("_render_research_price_evidence("), renderer.index("st.tabs("))
        self.assertLess(renderer.index("reference.executive_digest_html("), renderer.index("st.tabs("))
        self.assertEqual(renderer.count("reference.executive_digest_html("), 1)
        self.assertIn('st.columns([2, 1], gap="large")', renderer)
        self.assertIn("max-width:1100px", RESEARCH_REFERENCE_CSS)
        self.assertIn("flex-direction:column", RESEARCH_REFERENCE_CSS)
        self.assertIn("max-width:700px", RESEARCH_REFERENCE_CSS)

    def test_chart_ownership_mismatch_returns_false_before_any_price_chart(self):
        import ui.customer_research_v2 as renderer
        calls = []
        class Sink:
            def markdown(self, *_a, **_k): pass
            def error(self, message): calls.append(message)
            def caption(self, *_a, **_k): pass
        page = {"header": {}, "chart": {"status": "AVAILABLE", "ownership": {
            "requested_ticker": "NVDA", "source_report_ticker": "MSFT",
            "certified_authority_ticker": "NVDA", "chart_payload_ticker": "NVDA",
            "displayed_ticker": "NVDA"}}}
        with patch.object(renderer, "st", Sink()), patch.object(renderer, "_annotated_customer_price_chart") as chart:
            self.assertFalse(renderer._render_research_price_evidence(page, {}, ticker="NVDA"))
            chart.assert_not_called()
        self.assertEqual(calls, ["Research chart ownership could not be certified for this ticker."])

    def test_missing_chart_remains_honest_and_does_not_infer_series(self):
        import ui.customer_research_v2 as renderer
        messages = []
        class Sink:
            def markdown(self, *_a, **_k): pass
            def info(self, message): messages.append(message)
            def caption(self, *_a, **_k): pass
        page = {"header": {}, "chart": {"status": "UNAVAILABLE", "message": "Retained history unavailable.",
            "ownership": {name: "NVDA" for name in ("requested_ticker", "source_report_ticker",
            "certified_authority_ticker", "chart_payload_ticker", "displayed_ticker")}}}
        with patch.object(renderer, "st", Sink()), patch.object(renderer, "_annotated_customer_price_chart") as chart:
            self.assertTrue(renderer._render_research_price_evidence(page, {}, ticker="NVDA"))
            chart.assert_not_called()
        self.assertEqual(messages, ["Retained history unavailable."])
