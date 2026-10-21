"""Offline valuation education contract and renderer tests; standard library only."""
import ast
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping
import unittest

from ui.research_learning import build_valuation_guide


def sample():
    # Synthetic test evidence; never used by the customer runtime.
    return {
        "status": "AVAILABLE",
        "header": {"price": 10, "fair_value": 12, "fair_value_gap_pct": 20,
                   "price_source": "Close fixture", "price_timestamp": "2025-01-02"},
        "evidence": {"evaluation_snapshot_id": "snapshot:fixture"},
        "financial_snapshot": {"status": "AVAILABLE", "items": [
            {"field": "total_debt", "value": 0, "unit": "USD", "provider": "Filing fixture",
             "period": "2024-FY", "as_of": "2025-02-01", "evidence_id": "filing:fixture"}]},
        "financial_depth": {"status": "LIMITED", "valuation_models": [
            {"name": "Model fixture", "value": 12, "unit": "USD_PER_SHARE",
             "source": "CERTIFIED_ATLAS_VALUATION", "fiscal_period": "2026-FY",
             "weight": 0.6, "assumptions": {"forward_eps": 2, "unlabeled_rate": 0.1}}]},
    }


class ValuationGuideTests(unittest.TestCase):
    def test_exact_values_and_independent_dates_without_mutation(self):
        page = sample()
        before = deepcopy(page)
        result = build_valuation_guide(page)
        self.assertEqual(page, before)
        self.assertEqual(result["price"], 10)
        self.assertEqual(result["fair_value"], 12)
        self.assertEqual(result["gap_pct"], 20)
        self.assertEqual(result["balance"][0]["value"], 0)
        self.assertEqual(result["balance"][0]["as_of"], "2025-02-01")
        self.assertEqual(result["models"][0], page["financial_depth"]["valuation_models"][0])
        self.assertNotIn("as_of", result["models"][0])
        result["models"][0]["assumptions"]["forward_eps"] = 99
        self.assertEqual(page, before)

    def test_missing_and_withheld_lanes_fail_closed(self):
        self.assertEqual(build_valuation_guide({"status": "RATING_NOT_PUBLISHED", **{
            k: v for k, v in sample().items() if k != "status"}}), {"status": "UNAVAILABLE"})
        page = sample()
        page["financial_snapshot"]["status"] = "UNAVAILABLE"
        page["financial_depth"]["status"] = "NOT_AVAILABLE"
        result = build_valuation_guide(page)
        self.assertEqual(result["balance"], ())
        self.assertEqual(result["models"], ())
        empty = build_valuation_guide({"status": "AVAILABLE"})
        for field in ("price", "fair_value", "gap_pct", "price_as_of", "snapshot"):
            self.assertIsNone(empty[field])

    def test_no_ratios_targets_or_gap_are_derived(self):
        page = sample()
        page["header"].pop("fair_value_gap_pct")
        result = build_valuation_guide(page)
        self.assertIsNone(result["gap_pct"])
        self.assertNotIn("net_debt", result)
        self.assertNotIn("expected_return", result)

    def test_invalid_numbers_sources_and_units_are_excluded(self):
        for value in (True, "12", float("nan"), float("inf"), None):
            with self.subTest(value=value):
                page = sample()
                page["header"].update(price=value, fair_value=value, fair_value_gap_pct=value)
                page["financial_snapshot"]["items"][0]["value"] = value
                page["financial_depth"]["valuation_models"][0]["value"] = value
                result = build_valuation_guide(page)
                self.assertIsNone(result["price"])
                self.assertIsNone(result["fair_value"])
                self.assertIsNone(result["gap_pct"])
                self.assertEqual(result["models"], ())
                self.assertEqual(result["balance"], ())
        for patch in ({"source": None}, {"unit": "USD"}):
            page = sample()
            page["financial_depth"]["valuation_models"][0].update(patch)
            self.assertEqual(build_valuation_guide(page)["models"], ())
        page = sample()
        page["financial_snapshot"]["items"][0]["evidence_id"] = None
        self.assertEqual(build_valuation_guide(page)["balance"], ())

    def test_malformed_collections_and_duplicate_facts(self):
        page = sample()
        fact = page["financial_snapshot"]["items"][0]
        page["financial_snapshot"]["items"].extend([None, fact, {**fact, "field": "unknown"}])
        self.assertEqual(len(build_valuation_guide(page)["balance"]), 1)
        page["financial_snapshot"]["items"] = "not a collection"
        page["financial_depth"]["valuation_models"] = {"value": 5}
        result = build_valuation_guide(page)
        self.assertEqual(result["balance"], ())
        self.assertEqual(result["models"], ())


class RecordingUI:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args))
            return self
        return record

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def render_fixture(page):
    """Execute the actual renderer in isolation from optional Streamlit/pandas.

    The AST extraction compiles the unmodified function body; only presentation
    dependencies are replaced by recording doubles.
    """
    tree = ast.parse((Path(__file__).resolve().parents[1] / "customer_research_v2.py").read_text())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "_render_valuation_guide")
    ui = RecordingUI()
    namespace = {"Any": Any, "Mapping": Mapping, "st": ui,
                 "build_valuation_guide": build_valuation_guide, "_marker": lambda *a, **k: None,
                 "_money": lambda x: str(x), "_pct": lambda x, **kw: str(x),
                 "_financial_value": lambda x, unit: str(x),
                 "_financial_period": lambda x: str(x) if x else "Unavailable",
                 "_escape_markdown_currency": lambda x: str(x).replace("$", "\\$")}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "valuation-renderer", "exec"), namespace)
    namespace["_render_valuation_guide"](page, ticker="FIXTURE")
    return ui.calls


class ValuationRendererTests(unittest.TestCase):
    def test_shows_exact_assumptions_and_separate_provenance(self):
        calls = render_fixture(sample())
        output = " ".join(str(args) for _, args in calls)
        self.assertIn("Close as of: 2025-01-02", output)
        self.assertIn("Model evidence as of: Unavailable", output)
        self.assertIn("Fiscal period: 2026-FY", output)
        self.assertIn("Evidence as of: 2025-02-01", output)
        self.assertIn("Evidence ID: filing:fixture", output)
        self.assertIn("not an expected return", output)
        self.assertIn(("json", ({"forward_eps": 2, "unlabeled_rate": 0.1},)), calls)

    def test_missing_evidence_is_explicit_and_withheld_renders_nothing(self):
        calls = render_fixture({"status": "AVAILABLE"})
        output = " ".join(str(args) for _, args in calls)
        self.assertIn("valuation-model detail and assumptions are unavailable", output)
        self.assertIn("cash, debt, and market capitalization evidence is unavailable", output)
        self.assertFalse(any(name == "json" for name, _ in calls))
        self.assertEqual(render_fixture({"status": "RATING_NOT_PUBLISHED"}), [])


if __name__ == "__main__":
    unittest.main()
