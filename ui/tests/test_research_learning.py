"""Offline tests: python -m unittest discover -s ui/tests -p test_research_learning.py."""
from copy import deepcopy
import ast
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Mapping
import unittest

from ui.research_learning import build_learning_guide


def fact(field="net_income", value=0, **extra):
    return dict(field=field, value=value, evidence_id="filing:example",
                provider="Retained filing", period="2025-FY", as_of="2026-02-01",
                unit="USD", **extra)


def page(*items):
    return {"status": "AVAILABLE", "financial_snapshot": {"status": "AVAILABLE", "items": items}}


class ResearchLearningTests(unittest.TestCase):
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

    def test_business_requires_available_profile_and_source_identity(self):
        source = page()
        source["about"] = {"status": "AVAILABLE", "profile": {"description": "Customers pay for tools."},
                           "provenance": {"raw_evidence_id": "profile:1", "provider": "Retained profile",
                                          "capture_timestamp": "2025-01-01"}}
        before = deepcopy(source)
        business = build_learning_guide(source)["business"]
        self.assertEqual(business["description"], "Customers pay for tools.")
        self.assertEqual(business["provenance"], source["about"]["provenance"])
        self.assertEqual(source, before)
        source["about"]["status"] = "UNAVAILABLE"
        self.assertIsNone(build_learning_guide(source)["business"])
        source["about"]["status"] = "AVAILABLE"
        source["about"]["provenance"] = {}
        self.assertIsNone(build_learning_guide(source)["business"])

    def test_valuation_preserves_each_facts_own_date_and_source(self):
        source = page()
        close = dict(fact_name="Last Certified Close", value=12, display_value="$12.00",
                     classification="CERTIFIED_ATLAS", source="Archive", source_timestamp="2025-01-01",
                     period="Retained close", evidence_ids=("close:1",))
        fair_value = {**close, "fact_name": "ATLAS Fair Value", "value": 15, "display_value": "$15.00",
                      "source_timestamp": "2024-12-01", "evidence_ids": ("valuation:1",)}
        source["fundamentals"] = [close, fair_value]
        before = deepcopy(source)
        self.assertEqual(build_learning_guide(source)["valuation"], (close, fair_value))
        self.assertEqual(source, before)
        for override in ({"value": True}, {"value": float("nan")}, {"source": None},
                         {"evidence_ids": ()}, {"classification": "CONTEXTUAL"}, {"fact_name": "Target"}):
            source["fundamentals"] = [{**close, **override}]
            self.assertEqual(build_learning_guide(source)["valuation"], ())

    def test_resilience_balances_stay_separate_without_netting_or_safety_claims(self):
        cash = fact("cash_and_equivalents", 0)
        debt = {**fact("total_debt", 20), "period": "2024-FY"}
        source = page(cash, debt, fact("total_debt", 999), fact("total_debt", True))
        guide = build_learning_guide(source)
        self.assertEqual(guide["earnings"], ())
        self.assertEqual([row["value"] for row in guide["resilience"]], [0, 20])
        self.assertEqual([row["period"] for row in guide["resilience"]], ["2025-FY", "2024-FY"])
        self.assertNotIn("net_debt", guide)
        source["financial_snapshot"]["status"] = "UNAVAILABLE"
        self.assertEqual(build_learning_guide(source)["resilience"], ())

    def test_missing_new_sections_are_explicitly_empty(self):
        guide = build_learning_guide(page())
        self.assertIsNone(guide["business"])
        self.assertEqual(guide["valuation"], ())
        self.assertEqual(guide["resilience"], ())

    def test_renderer_shows_evidence_and_missing_data_without_optional_ui_dependencies(self):
        # Execute the actual render functions with a recording Streamlit boundary.
        # This keeps the focused offline test runnable without installing the app.
        tree = ast.parse((Path(__file__).parents[1] / "customer_research_v2.py").read_text())
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                     and node.name in {"_render_learning_guide", "_render_learning_fact"}]
        self.assertEqual(len(functions), 2)
        output = []

        class Recorder:
            def expander(self, label, **kwargs):
                output.append(label)
                return nullcontext()

            def __getattr__(self, name):
                return lambda value, **kwargs: output.append(str(value))

        namespace = dict(Any=Any, Mapping=Mapping, st=Recorder(), build_learning_guide=build_learning_guide,
                         _marker=lambda *args, **kwargs: None, _escape_markdown_currency=str,
                         _financial_value=lambda value, unit: str(value),
                         _financial_period=lambda value: str(value or "Unavailable"),
                         _list=lambda values: output.extend(values))
        exec(compile(ast.Module(body=functions, type_ignores=[]), "learning-renderer", "exec"), namespace)
        render = namespace["_render_learning_guide"]
        render(page(), ticker="EXAMPLE")
        text = "\n".join(output)
        self.assertIn("source-linked business description is unavailable", text)
        self.assertIn("no comparison is inferred", text)
        self.assertIn("missing evidence does not mean low risk", text)
        output.clear()
        source = page(fact("total_debt", 20))
        source["about"] = {"status": "AVAILABLE", "profile": {"description": "Retained business description."},
                           "provenance": {"raw_evidence_id": "profile:dated", "capture_timestamp": "2025-01-01"}}
        source["fundamentals"] = [dict(fact_name="Last Certified Close", value=12, display_value="$12.00",
                                      source="Archive", source_timestamp="2024-12-01", evidence_ids=("close:dated",),
                                      classification="CERTIFIED_ATLAS")]
        render(source, ticker="EXAMPLE")
        text = "\n".join(output)
        for expected in ("Retained business description.", "profile:dated", "2025-01-01", "Source: Unavailable",
                         "Last Certified Close: $12.00", "2024-12-01", "close:dated", "Borrowed money: 20",
                         "filing:example", "not a promised gain"):
            self.assertIn(expected, text)
        output.clear()
        render({**source, "status": "RATING_NOT_PUBLISHED"}, ticker="EXAMPLE")
        self.assertEqual(output, [])


if __name__ == "__main__":
    unittest.main()
