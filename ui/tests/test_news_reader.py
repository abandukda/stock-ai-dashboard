"""Offline chronology and rendering checks; all finance/news inputs are synthetic."""
import ast
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping
import unittest
from unittest.mock import Mock

from ui.research_learning import build_news_reader


def article(timestamp, headline="Example report"):
    return dict(headline=headline, article_publisher="Example publisher", article_timestamp=timestamp)


def fixture(*items):
    return dict(status="AVAILABLE", fundamentals=[dict(
        fact_name="Last Certified Close", classification="CERTIFIED_ATLAS", source="Retained close",
        source_timestamp="2025-02-01T16:00:00Z", evidence_ids=["test:close"])],
        recent_changes=dict(status="AVAILABLE", items=list(items)))


class NewsReaderTests(unittest.TestCase):
    def test_orders_and_compares_instants_in_utc_without_mutating_page(self):
        page = fixture(article("2025-02-01T10:00:00-05:00", "Earlier"),
                       article("2025-02-01T18:00:00+01:00", "Later"),
                       article("2025-02-01T16:00:00Z", "Equal"))
        before = deepcopy(page)
        reader = build_news_reader(page)
        self.assertEqual([row["relation"] for row in reader["items"]], ["AFTER", "OVERLAPPING", "BEFORE"])
        self.assertEqual(reader["items"][0]["published_at"], "2025-02-01T18:00:00+01:00")
        reader["reference"]["source"] = "Changed"
        reader["items"][0]["headline"] = "Changed"
        self.assertEqual(page, before)

    def test_date_only_never_implies_intraday_ordering(self):
        page = fixture(article("2025-02-01"), article("2025-02-02", "Next day"))
        self.assertEqual([row["relation"] for row in build_news_reader(page)["items"]], ["AFTER", "OVERLAPPING"])
        page["fundamentals"][0]["source_timestamp"] = "2025-02-01"
        page["recent_changes"]["items"] = [article("2025-02-01T23:59:59Z")]
        self.assertEqual(build_news_reader(page)["items"][0]["relation"], "OVERLAPPING")

    def test_reference_requires_unique_certified_dated_provenance(self):
        for patch in ({"source": None}, {"evidence_ids": []}, {"evidence_ids": "test"},
                      {"evidence_ids": [True]}, {"classification": "CONTEXTUAL"},
                      {"source_timestamp": "invalid"}, {"source_timestamp": "2025-02-01T16:00:00"}):
            with self.subTest(patch=patch):
                page = fixture(article("2025-02-02"))
                page["fundamentals"][0].update(patch)
                reader = build_news_reader(page)
                self.assertIsNone(reader["reference"])
                self.assertEqual(reader["items"][0]["relation"], "UNAVAILABLE")
        page = fixture(article("2025-02-02"))
        page["fundamentals"] *= 2
        self.assertIsNone(build_news_reader(page)["reference"])

    def test_missing_dates_deduplication_and_malformed_inputs(self):
        page = fixture(article(None, "Undated"), article("2025-02-02"),
                       article("2025-02-02"), article("bad", "Bad date"),
                       article("2025-02-01T12:00:00", "No timezone"), None,
                       {"headline": "No publisher"})
        reader = build_news_reader(page)
        self.assertEqual(len(reader["items"]), 4)
        self.assertEqual(reader["items"][0]["relation"], "AFTER")
        self.assertTrue(all(row["published_at"] is None for row in reader["items"][1:]))
        for value in (None, True, [], "bad", 42):
            self.assertEqual(build_news_reader(value)["status"], "UNAVAILABLE")
            page["recent_changes"]["items"] = value
            self.assertEqual(build_news_reader(page)["items"], ())
        page = fixture(article("2025-02-02"))
        page["recent_changes"]["status"] = "UNAVAILABLE"
        self.assertEqual(build_news_reader(page)["items"], ())
        page["status"] = "RATING_NOT_PUBLISHED"
        self.assertEqual(build_news_reader(page), dict(status="UNAVAILABLE", reference=None, items=()))

    def test_renderer_preserves_literal_sources_and_explains_limits(self):
        tree = ast.parse((Path(__file__).parents[1] / "customer_research_v2.py").read_text())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == "_render_news_reader")
        st, literal = Mock(), Mock()
        st.expander.side_effect = lambda *args, **kwargs: nullcontext()
        module = SimpleNamespace(build_news_reader=build_news_reader)
        namespace = dict(st=st, _literal_retained_context=literal, Mapping=Mapping, Any=Any,
                         _research_learning=module)
        exec(compile(ast.Module(body=[function], type_ignores=[]), "news_renderer", "exec"), namespace)
        render = namespace["_render_news_reader"]
        render(fixture(article("2025-02-02", "[literal](untrusted)"), article(None, "Undated")))
        retained = " ".join(call.args[0] for call in literal.call_args_list)
        for value in ("[literal](untrusted)", "Example publisher", "2025-02-02", "test:close", "Published: Unavailable"):
            self.assertIn(value, retained)
        captions = " ".join(call.args[0] for call in st.caption.call_args_list)
        self.assertIn("Published after", captions)
        self.assertIn("not the evaluation date", captions)
        self.assertIn("no Action, Fair Value, or risk change is inferred", captions)
        st.reset_mock()
        render(dict(status="AVAILABLE"))
        self.assertEqual(st.info.call_count, 2)
        st.reset_mock()
        render(dict(status="RATING_NOT_PUBLISHED"))
        st.expander.assert_not_called()
        module.build_news_reader = None
        render(fixture())
        st.info.assert_called_once_with("The dated news reader is unavailable in this application session.")


if __name__ == "__main__":
    unittest.main()
