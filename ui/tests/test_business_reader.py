"""Offline: python -m unittest discover -s ui/tests -p test_business_reader.py."""
import ast
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping
import unittest
from unittest.mock import Mock

from ui.research_learning import build_business_reader


def fixture():
    # Synthetic test inputs only; never used as customer fallback data.
    return {
        "status": "AVAILABLE",
        "about": {"status": "AVAILABLE", "profile": {"description": "Example sells tools."},
                  "provenance": {"provider": "Retained profile", "raw_evidence_id": "profile:test",
                                 "capture_timestamp": "2025-10-01"}},
        "financial_snapshot": {"status": "AVAILABLE", "items": [
            dict(field=field, value=value, unit="USD", provider="Retained filing",
                 evidence_id=f"filing:{field}", period=period, as_of="2025-09-01")
            for field, value, period in (("latest_revenue", 100, "2024-FY"),
                                         ("net_income", -2, "2025-Q1"),
                                         ("operating_cash_flow", 0, None))]},
    }


class BusinessReaderTests(unittest.TestCase):
    def test_preserves_exact_values_independent_dates_and_periods_without_mutation(self):
        page = fixture()
        before = deepcopy(page)
        reader = build_business_reader(page)
        self.assertEqual(reader["description"]["as_of"], "2025-10-01")
        self.assertEqual([stage["fact"]["value"] for stage in reader["stages"]], [100, -2, 0])
        self.assertEqual([stage["fact"]["period"] for stage in reader["stages"]], ["2024-FY", "2025-Q1", None])
        reader["stages"][0]["fact"]["value"] = 999
        reader["description"]["text"] = "Changed"
        self.assertEqual(page, before)

    def test_withheld_page_never_exposes_nested_evidence(self):
        page = fixture()
        page["status"] = "RATING_NOT_PUBLISHED"
        self.assertEqual(build_business_reader(page),
                         {"status": "UNAVAILABLE", "description": None, "stages": ()})

    def test_profile_requires_own_source_and_identity_not_industry_or_global_identity(self):
        for key in ("provider", "raw_evidence_id"):
            page = fixture()
            del page["about"]["provenance"][key]
            page["evidence"] = {"evidence_ids": ["unrelated:valuation"]}
            self.assertIsNone(build_business_reader(page)["description"])
        for profile in ({"industry": "Tools"}, {"description": 42}, {"description": "  "}):
            page = fixture()
            page["about"]["profile"] = profile
            self.assertIsNone(build_business_reader(page)["description"])
        page = fixture()
        page["about"]["status"] = "UNAVAILABLE"
        self.assertIsNone(build_business_reader(page)["description"])

    def test_description_alias_and_missing_capture_date(self):
        page = fixture()
        page["about"]["profile"] = {"business_summary": "  Example sells tools.  "}
        del page["about"]["provenance"]["capture_timestamp"]
        reader = build_business_reader(page)
        self.assertEqual(reader["description"]["text"], "Example sells tools.")
        self.assertIsNone(reader["description"]["as_of"])

    def test_invalid_or_ambiguous_financial_evidence_fails_closed_per_step(self):
        for change in ({"value": True}, {"value": "100"}, {"value": float("nan")},
                       {"value": float("inf")}, {"unit": "EUR"}, {"currency": "EUR"},
                       {"provider": None}, {"evidence_id": None}):
            with self.subTest(change=change):
                page = fixture()
                page["financial_snapshot"]["items"][0].update(change)
                reader = build_business_reader(page)
                self.assertIsNone(reader["stages"][0]["fact"])
                self.assertEqual(reader["stages"][1]["fact"]["value"], -2)
        page = fixture()
        page["financial_snapshot"]["items"].append(dict(page["financial_snapshot"]["items"][0]))
        self.assertIsNone(build_business_reader(page)["stages"][0]["fact"])
        page["financial_snapshot"]["status"] = "UNAVAILABLE"
        self.assertTrue(all(stage["fact"] is None for stage in build_business_reader(page)["stages"]))

    def test_empty_available_page_has_explicit_gaps(self):
        reader = build_business_reader({"status": "AVAILABLE"})
        self.assertIsNone(reader["description"])
        self.assertEqual(len(reader["stages"]), 3)
        self.assertTrue(all(stage["fact"] is None for stage in reader["stages"]))

    def test_renderer_shows_sources_gaps_and_advanced_questions(self):
        # Isolate rendering from optional Streamlit/runtime service imports.
        tree = ast.parse((Path(__file__).parents[1] / "customer_research_v2.py").read_text())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == "_render_business_reader")
        streamlit = Mock()
        streamlit.expander.return_value = nullcontext()
        literal = Mock()
        namespace = dict(st=streamlit, Mapping=Mapping, Any=Any,
                         _research_learning=SimpleNamespace(build_business_reader=build_business_reader),
                         _literal_retained_context=literal,
                         _financial_period=lambda value: value or "Unavailable",
                         _financial_value=lambda value, unit: f"{value} {unit}")
        exec(compile(ast.Module(body=[function], type_ignores=[]), "business_renderer", "exec"), namespace)
        render = namespace["_render_business_reader"]
        render(fixture())
        citations = " ".join(str(call.args[0]) for call in literal.call_args_list)
        for text in ("Example sells tools.", "profile:test", "2025-10-01", "Retained filing",
                     "2024-FY", "2025-Q1", "Fiscal period: Unavailable", "2025-09-01"):
            self.assertIn(text, citations)
        self.assertIn("-2 USD", [call.args[0] for call in streamlit.write.call_args_list])
        streamlit.expander.assert_called_once_with(
            "Go deeper: test the business model before trusting the thesis", expanded=False)
        streamlit.reset_mock()
        literal.reset_mock()
        render({"status": "AVAILABLE"})
        streamlit.info.assert_called_once()
        self.assertEqual(streamlit.caption.call_count, 4)
        literal.assert_not_called()
        streamlit.reset_mock()
        render({"status": "RATING_NOT_PUBLISHED"})
        streamlit.markdown.assert_not_called()
        streamlit.expander.assert_not_called()

    def test_warm_module_without_new_builder_degrades_explicitly(self):
        tree = ast.parse((Path(__file__).parents[1] / "customer_research_v2.py").read_text())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == "_render_business_reader")
        streamlit = Mock()
        namespace = dict(st=streamlit, Mapping=Mapping, Any=Any,
                         _research_learning=SimpleNamespace())
        exec(compile(ast.Module(body=[function], type_ignores=[]), "business_renderer", "exec"), namespace)
        namespace["_render_business_reader"](fixture())
        streamlit.info.assert_called_once_with("The business-model reader is unavailable in this application session.")


if __name__ == "__main__":
    unittest.main()
