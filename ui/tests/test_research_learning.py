"""Offline tests: python -m unittest discover -s ui/tests -p test_research_learning.py."""
from copy import deepcopy
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


if __name__ == "__main__":
    unittest.main()
