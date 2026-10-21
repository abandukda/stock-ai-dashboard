"""Offline tests: python -m unittest discover -s ui/tests -p test_research_learning.py."""
from copy import deepcopy
import ast
from contextlib import nullcontext
from pathlib import Path
from typing import Mapping, Any
import unittest
from unittest.mock import Mock

from ui.research_learning import build_learning_guide, build_valuation_guide


def fact(field="net_income", value=0, **extra):
    return dict(field=field, value=value, evidence_id="filing:example",
                provider="Retained filing", period="2025-FY", as_of="2026-02-01",
                unit="USD", **extra)


def page(*items):
    return {"status": "AVAILABLE", "financial_snapshot": {"status": "AVAILABLE", "items": items}}


class ResearchLearningTests(unittest.TestCase):
    def test_valuation_preserves_separate_dates_sources_and_missing_dates(self):
        close = dict(fact_name="Last Certified Close", value=12, source="Retained close",
                     source_timestamp="2025-12-31", evidence_ids=("close:1",),
                     classification="CERTIFIED_ATLAS")
        estimate = {**close, "fact_name": "ATLAS Fair Value", "value": 0,
                    "source": "Retained model", "source_timestamp": None,
                    "evidence_ids": ("valuation:1",)}
        source = {**page(), "fundamentals": [close, estimate],
                  "valuation_chart": {"as_of": "2026-01-02"}}
        before = deepcopy(source)
        result = build_valuation_guide(source)
        self.assertEqual(result["facts"], (close, estimate))
        self.assertEqual(source, before)
        self.assertIsNone(result["facts"][1]["source_timestamp"])
        self.assertEqual(set(result), {"facts", "models"})  # no derived price target or multiple

    def test_valuation_fails_closed_on_withheld_or_unsupported_facts(self):
        valid = dict(fact_name="ATLAS Fair Value", value=10, source="Retained model",
                     evidence_ids=("valuation:1",), classification="CERTIFIED_ATLAS")
        for change in ({"value": True}, {"value": float("nan")}, {"value": float("inf")},
                       {"value": "10"}, {"source": None}, {"evidence_ids": ()},
                       {"classification": "CONTEXTUAL_NON_SCORING"}, {"fact_name": "Target"}):
            with self.subTest(change=change):
                self.assertEqual(build_valuation_guide({**page(), "fundamentals": [{**valid, **change}]})["facts"], ())
        source = {"status": "RATING_NOT_PUBLISHED", "fundamentals": [valid],
                  "financial_depth": {"valuation_models": [{"value": 10}]}}
        self.assertEqual(build_valuation_guide(source), {"facts": (), "models": ()})

    def test_models_keep_exact_assumptions_without_synthesizing_missing_inputs(self):
        model = dict(name="Retained model", value=12, unit="USD_PER_SHARE",
                     source="CERTIFIED_ATLAS_VALUATION", fiscal_period="2025-FY",
                     assumptions={"growth": 0, "discount_rate": None})
        source = {**page(), "financial_depth": {"valuation_models": [model, None,
                  {**model, "value": float("nan")}, {**model, "source": "Unverified"},
                  {**model, "unit": "USD"}]}}
        before = deepcopy(source)
        guide = build_valuation_guide(source)
        self.assertEqual(guide["models"], (model,))
        guide["models"][0]["assumptions"]["growth"] = 99
        self.assertEqual(source["financial_depth"]["valuation_models"][0], before["financial_depth"]["valuation_models"][0])

    def test_valuation_renderer_displays_absence_and_exact_assumptions(self):
        # Exercise the renderer offline without importing the app's optional runtime
        # or services (which may read production data during app initialization).
        tree = ast.parse((Path(__file__).parents[1] / "customer_research_v2.py").read_text())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == "_render_valuation_guide")
        streamlit = Mock()
        streamlit.expander.return_value = nullcontext()
        namespace = dict(st=streamlit, Mapping=Mapping, Any=Any,
                         build_valuation_guide=build_valuation_guide,
                         _money=str, _escape_markdown_currency=str,
                         _financial_period=lambda value: value or "Unavailable")
        exec(compile(ast.Module(body=[function], type_ignores=[]), "valuation_renderer", "exec"), namespace)
        render = namespace["_render_valuation_guide"]
        render(page())
        captions = " ".join(str(call.args[0]) for call in streamlit.caption.call_args_list)
        self.assertIn("Last Certified Close: source-bound evidence is unavailable", captions)
        self.assertIn("ATLAS Fair Value: source-bound evidence is unavailable", captions)
        streamlit.info.assert_called_once()
        streamlit.reset_mock()
        render({**page(), "financial_depth": {"valuation_models": [dict(
            value=12, unit="USD_PER_SHARE", source="CERTIFIED_ATLAS_VALUATION",
            assumptions={"growth": 0, "discount_rate": None})]}})
        self.assertEqual([call.args[0] for call in streamlit.text.call_args_list],
                         ["growth: 0", "discount_rate: Unavailable"])
        streamlit.info.assert_not_called()

    def test_preserves_zero_negative_values_and_exact_provenance_without_mutation(self):
        source = page(fact(), fact("operating_cash_flow", -12))
        before = deepcopy(source)
        guide = build_learning_guide(source)
        self.assertEqual(source, before)
        self.assertEqual([row["value"] for row in guide["earnings"]], [0, -12])
        for original, selected in zip(source["financial_snapshot"]["items"], guide["earnings"]):
            for key, value in original.items():
                self.assertEqual(selected[key], value)

    def test_rejects_unsupported_or_invalid_financial_facts(self):
        source = page(fact(value=True), fact(value=float("nan")), fact(value=float("inf")),
                      fact(value="12"), fact("unsupported", 1),
                      {**fact(), "evidence_id": None}, None)
        self.assertEqual(build_learning_guide(source)["earnings"], ())

    def test_unavailable_or_withheld_data_does_not_leak(self):
        source = page(fact())
        source["financial_snapshot"]["status"] = "UNAVAILABLE"
        self.assertEqual(build_learning_guide(source)["earnings"], ())
        source["status"] = "RATING_NOT_PUBLISHED"
        self.assertEqual(build_learning_guide(source),
                         {"status": "UNAVAILABLE", "earnings": (), "headlines": ()})

    def test_estimates_are_taught_as_estimates_and_missing_dates_stay_missing(self):
        source = page({**fact("forward_eps", 2), "period": None, "as_of": None})
        row = build_learning_guide(source)["earnings"][0]
        self.assertIn("not a reported earnings result", row["explanation"])
        self.assertIsNone(row["period"])
        self.assertIsNone(row["as_of"])

    def test_news_requires_available_lane_source_and_date(self):
        headline = {"headline": "Example retained headline", "article_publisher": "Example source",
                    "article_timestamp": "2026-02-01"}
        source = page()
        source["recent_changes"] = {"status": "AVAILABLE", "items": [headline, {"headline": "Undated"}]}
        self.assertEqual(build_learning_guide(source)["headlines"], (headline,))
        source["recent_changes"]["status"] = "UNAVAILABLE"
        self.assertEqual(build_learning_guide(source)["headlines"], ())

    def test_monitoring_prompts_are_separate_and_no_conditions_are_invented(self):
        source = page()
        source["summary"] = {"watch_conditions": {"strengthen": ["Retained supportive condition"]}}
        guide = build_learning_guide(source)
        self.assertEqual(guide["bull_watch"], ("Retained supportive condition",))
        self.assertEqual(guide["bear_watch"], ())
        self.assertEqual(guide["risks"], ())
        self.assertIsNone(guide["snapshot"])


if __name__ == "__main__":
    unittest.main()
