"""Offline focused checks; fixtures are synthetic, never customer fallback data."""
import ast
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping
import unittest
from unittest.mock import Mock

from ui.research_learning import build_sales_dollar_guide


def fixture():
    return {"status": "AVAILABLE", "ticker": "TEST", "financial_trend": {
        "status": "AVAILABLE", "periodicity": "ANNUAL",
        "periods": ["2025-12-31", "2024-12-31"],
        "series": {"Revenue": [200, 100], "Net Income": [10, 10],
                   "Operating Cash Flow": [-4, 0], "Free Cash Flow": [-10, -20]},
        "units": {name: "USD" for name in
                  ("Revenue", "Net Income", "Operating Cash Flow", "Free Cash Flow")},
        "provenance": {"source": "Retained test filing", "raw_evidence_id": "test:filing",
                       "as_of": None}}}


class SalesDollarGuideTests(unittest.TestCase):
    def test_size_growth_does_not_imply_better_profitability(self):
        page = fixture()
        before = deepcopy(page)
        result = build_sales_dollar_guide(page)
        profit, cash, fcf = result["rows"]
        self.assertEqual((profit["prior"], profit["current"], profit["change"]), (10, 5, -5))
        self.assertEqual((cash["prior"], cash["current"]), (0, -2))
        self.assertEqual((fcf["prior"], fcf["current"]), (-20, -5))
        self.assertIn("cash used", cash["reading"])
        self.assertIn("cash shortfall", fcf["reading"])
        self.assertEqual(result["prior_period"], "2024-12-31")
        self.assertEqual(result["evidence_ids"], ("test:filing",))
        self.assertIsNone(result["as_of"])
        self.assertEqual(page, before)

    def test_zero_losses_and_tiny_amounts_are_explained(self):
        for amount, phrase in ((0, "neither a positive amount"), (-1, "a loss"),
                               (-.0001, "less than $0.01"), (1, "profit after expenses")):
            page = fixture()
            page["financial_trend"]["series"]["Net Income"][0] = amount
            self.assertIn(phrase, build_sales_dollar_guide(page)["rows"][0]["reading"])

    def test_positive_sales_required_in_both_years(self):
        for sales in ([0, 100], [100, 0], [-1, 100], [100, -1], [True, 100], [None, 100]):
            page = fixture()
            page["financial_trend"]["series"]["Revenue"] = sales
            self.assertEqual(build_sales_dollar_guide(page), {"status": "UNAVAILABLE", "rows": ()})

    def test_withheld_unmatched_and_unsourced_evidence_is_unavailable(self):
        for update in ({"status": "UNAVAILABLE"}, {"periodicity": "QUARTERLY"},
                       {"periods": ["2025-12-31", "2023-12-31"]},
                       {"periods": ["2025-12-31", "2024-09-30"]},
                       {"periods": ["2025-12-31", "2025-12-31"]},
                       {"provenance": {}}, {"provenance": {"source": "Filing"}}):
            page = fixture()
            page["financial_trend"].update(update)
            self.assertEqual(build_sales_dollar_guide(page)["status"], "UNAVAILABLE")
        page = fixture()
        page["status"] = "RATING_NOT_PUBLISHED"
        self.assertEqual(build_sales_dollar_guide(page)["rows"], ())

    def test_partial_evidence_does_not_invent_missing_ratios(self):
        page = fixture()
        page["financial_trend"]["units"]["Net Income"] = "EUR"
        page["financial_trend"]["series"]["Operating Cash Flow"] = [float("nan"), 0]
        self.assertEqual([row["label"] for row in build_sales_dollar_guide(page)["rows"]],
                         ["Cash after investment"])

    def test_overflow_is_rejected_but_cash_above_sales_is_allowed(self):
        page = fixture()
        page["financial_trend"]["series"]["Revenue"] = [1e-300, 1e-300]
        self.assertEqual(build_sales_dollar_guide(page)["status"], "AVAILABLE")
        page["financial_trend"]["series"]["Net Income"] = [1e300, 1e300]
        self.assertNotIn("Profit", [row["label"] for row in build_sales_dollar_guide(page)["rows"]])
        page = fixture()
        page["financial_trend"]["series"]["Operating Cash Flow"] = [400, 100]
        self.assertEqual(build_sales_dollar_guide(page)["rows"][1]["current"], 200)

    def renderer(self):
        tree = ast.parse((Path(__file__).parents[1] / "customer_research_v2.py").read_text())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == "_render_sales_dollar_guide")
        st = Mock()
        st.expander.return_value = nullcontext()
        namespace = dict(st=st, Mapping=Mapping, Any=Any,
                         _research_learning=SimpleNamespace(build_sales_dollar_guide=build_sales_dollar_guide),
                         _financial_period=lambda value: value or "Unavailable")
        exec(compile(ast.Module(body=[function], type_ignores=[]), "sales_renderer", "exec"), namespace)
        return st, namespace["_render_sales_dollar_guide"], namespace

    def test_renderer_cites_periods_sources_and_exposes_exact_calculations(self):
        st, render, _ = self.renderer()
        render(fixture())
        captions = " ".join(str(call.args[0]) for call in st.caption.call_args_list)
        for value in ("2024-12-31", "2025-12-31", "Retained test filing", "test:filing", "Evidence as of: Unavailable"):
            self.assertIn(value, captions)
        self.assertEqual(st.table.call_args.args[0][0]["Change (percentage points)"], "-5.00")
        calculations = " ".join(str(call.args[0]) for call in st.text.call_args_list)
        self.assertIn("2025-12-31: 10 / 200", calculations)
        self.assertIn("2024-12-31: 10 / 100", calculations)
        st.expander.assert_called_once()

    def test_renderer_absence_and_warm_module_fail_closed(self):
        st, render, namespace = self.renderer()
        render({"status": "RATING_NOT_PUBLISHED"})
        st.info.assert_called_once()
        st.table.assert_not_called()
        st.caption.assert_not_called()
        st.reset_mock()
        namespace["_research_learning"] = SimpleNamespace()
        render(fixture())
        self.assertIn("application session", st.info.call_args.args[0])
        st.table.assert_not_called()

    def test_customer_learning_flow_includes_the_comparison(self):
        tree = ast.parse((Path(__file__).parents[1] / "customer_research_v2.py").read_text())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == "_render_learning_guide")
        calls = [node.func.id for node in ast.walk(function)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)]
        self.assertEqual(calls.count("_render_sales_dollar_guide"), 1)


if __name__ == "__main__":
    unittest.main()
