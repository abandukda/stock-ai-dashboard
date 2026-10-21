"""Offline valuation lesson tests; no UI dependencies or external data needed."""
import ast
from copy import deepcopy
from pathlib import Path
import unittest

from ui.research_learning import build_valuation_lesson


def page():
    # Synthetic values exercise display behavior, never customer finance data.
    return {
        "status": "AVAILABLE",
        "valuation_evidence": {
            "price": {"value": 20, "source": "Fixture close", "as_of": "2025-01-02",
                      "period": "close", "unit": "PER_SHARE", "evidence_ids": ["fixture:close"]},
            "fair_value": {"value": 25, "source": "Fixture valuation", "as_of": "2024-12-31",
                           "period": "FY2024", "unit": "PER_SHARE", "evidence_ids": ["fixture:value"]},
        },
        "financial_depth": {"status": "LIMITED", "valuation_models": [
            {"name": "Fixture earnings model", "value": 25, "unit": "USD_PER_SHARE",
             "fiscal_period": "FY2024", "source": "Fixture model", "assumptions": {"forward_eps": 2}},
        ]},
    }


class ValuationLearningTests(unittest.TestCase):
    def test_preserves_separate_reference_dates_values_and_lineage_without_mutation(self):
        source = page()
        before = deepcopy(source)
        result = build_valuation_lesson(source)
        self.assertEqual(source, before)
        for reference in result["references"]:
            for key, value in source["valuation_evidence"][reference["kind"]].items():
                self.assertEqual(reference[key], value)
        self.assertNotEqual(result["references"][0]["as_of"], result["references"][1]["as_of"])
        self.assertEqual(result["models"][0]["assumptions"], {"forward_eps": 2})
        self.assertNotIn("expected_return", result)

    def test_withheld_page_cannot_expose_retained_values_or_models(self):
        for status in ("RATING_NOT_PUBLISHED", "UNAVAILABLE", None):
            source = page()
            source["status"] = status
            self.assertEqual(build_valuation_lesson(source),
                             {"status": "UNAVAILABLE", "references": (), "models": ()})

    def test_missing_lineage_is_not_borrowed_from_chart_or_price(self):
        source = page()
        source["valuation_evidence"]["fair_value"] = {"value": 25}
        source["valuation_chart"] = {"as_of": "2099-01-01"}
        reference = build_valuation_lesson(source)["references"][1]
        self.assertNotIn("as_of", reference)
        self.assertNotIn("source", reference)
        self.assertNotIn("evidence_ids", reference)
        source.pop("valuation_evidence")
        source["header"] = {"price": 20, "fair_value": 25}
        self.assertEqual(build_valuation_lesson(source)["references"], ())

    def test_rejects_invalid_numbers_but_retains_zero_and_negative_model_outputs(self):
        for value in (True, "25", float("nan"), float("inf"), None):
            source = page()
            source["valuation_evidence"]["price"]["value"] = value
            source["financial_depth"]["valuation_models"][0]["value"] = value
            result = build_valuation_lesson(source)
            self.assertEqual(len(result["references"]), 1)
            self.assertEqual(result["models"], ())
        for value in (0, -5):
            source = page()
            source["financial_depth"]["valuation_models"][0]["value"] = value
            self.assertEqual(build_valuation_lesson(source)["models"][0]["value"], value)

    def test_unavailable_depth_and_wrong_model_units_fail_closed(self):
        source = page()
        source["financial_depth"]["status"] = "NOT_AVAILABLE"
        self.assertEqual(build_valuation_lesson(source)["models"], ())
        source = page()
        source["financial_depth"]["valuation_models"][0]["unit"] = "PERCENT"
        self.assertEqual(build_valuation_lesson(source)["models"], ())

    def test_missing_assumptions_are_not_invented(self):
        source = page()
        source["financial_depth"]["valuation_models"][0].pop("assumptions")
        self.assertEqual(build_valuation_lesson(source)["models"][0]["assumptions"], {})

    def test_method_explanation_requires_exact_published_methodology(self):
        source = page()
        model = source["financial_depth"]["valuation_models"][0]
        # A display name alone must not lead to a guessed methodology.
        model["name"] = "DCF"
        self.assertIsNone(build_valuation_lesson(source)["models"][0]["explanation"])
        model["methodology_id"] = "VAL_FORWARD_PE_V1"
        self.assertIn("not a reported result", build_valuation_lesson(source)["models"][0]["explanation"])
        model["methodology_id"] = "VAL_FCFF_DCF_V1"
        self.assertIn("today's money", build_valuation_lesson(source)["models"][0]["explanation"])


class RecordingUI:
    def __init__(self):
        self.output = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def expander(self, label, **_kwargs):
        self.output.append(label)
        return self

    def __getattr__(self, _name):
        return lambda text, **_kwargs: self.output.append(str(text))


def render_lesson(source):
    """Load the real renderer functions without importing missing Streamlit.

    The extracted functions are executed unchanged with a recording UI. This
    verifies visible evidence/limitations, but does not replace browser testing.
    """
    tree = ast.parse((Path(__file__).parents[1] / "customer_research_v2.py").read_text())
    names = {"_render_valuation_lesson", "_financial_period", "_escape_markdown_currency"}
    selected = ast.Module(body=[node for node in tree.body if isinstance(node, ast.FunctionDef)
                                and node.name in names], type_ignores=[])
    from datetime import datetime
    ui = RecordingUI()
    namespace = {"Mapping": dict, "Any": object, "datetime": datetime, "st": ui,
                 "build_valuation_lesson": build_valuation_lesson,
                 "_marker": lambda *_args, **_kwargs: None,
                 "_money": lambda value: f"${value:,.2f}"}
    exec(compile(selected, "customer_research_v2.py", "exec"), namespace)
    namespace["_render_valuation_lesson"](source, ticker="FIXTURE")
    return "\n".join(ui.output)


class ValuationRenderingTests(unittest.TestCase):
    def test_renders_each_source_and_date_with_estimate_and_return_caveats(self):
        output = render_lesson(page())
        for expected in ("Fixture close", "Fixture valuation", "Jan 2, 2025", "Dec 31, 2024",
                         "fixture:close", "fixture:value", "not an expected return",
                         "forward eps: 2", "Model-specific source date and evidence ID: unavailable"):
            self.assertIn(expected, output)

    def test_partial_evidence_explains_missing_values_and_assumptions(self):
        source = page()
        source["valuation_evidence"] = {"fair_value": {"value": 25}}
        source["financial_depth"]["valuation_models"][0].pop("assumptions")
        output = render_lesson(source)
        self.assertIn("Source-bound last certified close is unavailable", output)
        self.assertIn("As of: Unavailable", output)
        self.assertIn("Model assumptions are unavailable", output)
        self.assertNotIn("Jan 2, 2025", output)

    def test_empty_and_withheld_pages_do_not_imply_complete_evidence(self):
        output = render_lesson({"status": "AVAILABLE"})
        self.assertIn("Source-bound Fair Value evidence is unavailable", output)
        self.assertIn("Published model outputs and assumptions are unavailable", output)
        source = page()
        source["status"] = "RATING_NOT_PUBLISHED"
        self.assertEqual(render_lesson(source), "")


if __name__ == "__main__":
    unittest.main()
