"""Offline fixtures only; no application initialization or provider access."""
import ast
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping
import unittest
from unittest.mock import Mock

from ui.research_learning import build_earnings_reader


def fixture():
    periods = [dict(fiscal_year=year, fiscal_quarter=2, accession=str(year),
                    fiscal_period_end=f"{year}-06-30", filed_date=f"{year}-08-01")
               for year in (2024, 2025)]
    row = dict(concept="us-gaap:NetIncomeLoss", unit={"canonical": "USD"}, cells=[
        dict(accession=str(year), status="AVAILABLE", value=value, fact_id=f"fact:{year}",
             duration_semantics="REPORTED_CUMULATIVE_YTD",
             provenance={"filing_accession": str(year), "raw_sha256": "retained-hash"})
        for year, value in ((2024, 0), (2025, -12))])
    return dict(status="AVAILABLE", ticker="EXAMPLE", statement_history=dict(
        contract="ATLAS_CUSTOMER_STATEMENT_HISTORY_PROJECTION_V1", ticker="EXAMPLE",
        status="AVAILABLE", read_only=True, rating_authority="UNCHANGED",
        publication_authority="UNCHANGED", provider_calls=0,
        quarterly=dict(status="AVAILABLE", visible_periods=periods,
                       statements={"INCOME_STATEMENT": [row]})))


class EarningsReaderTests(unittest.TestCase):
    def test_pairs_same_quarter_and_preserves_zero_loss_dates_and_input(self):
        source = fixture()
        before = deepcopy(source)
        reader = build_earnings_reader(source)
        profit = reader["rows"][1]
        self.assertEqual(profit["latest"]["value"], -12)
        self.assertEqual(profit["prior"]["value"], 0)
        self.assertEqual(profit["latest"]["filed_date"], "2025-08-01")
        self.assertEqual(profit["latest"]["basis"], "REPORTED_CUMULATIVE_YTD")
        self.assertIsNone(reader["rows"][0]["latest"])
        self.assertEqual(source, before)

    def test_authority_gates(self):
        for key, value in (("ticker", "OTHER"), ("read_only", False),
                           ("publication_authority", "CHANGED"), ("rating_authority", "CHANGED"),
                           ("provider_calls", 1), ("contract", "OTHER"), ("status", "UNAVAILABLE")):
            source = fixture()
            source["statement_history"][key] = value
            with self.subTest(key=key):
                self.assertEqual(build_earnings_reader(source)["status"], "UNAVAILABLE")
        source = fixture()
        source["status"] = "RATING_NOT_PUBLISHED"
        self.assertEqual(build_earnings_reader(source)["rows"], ())

    def test_invalid_cells_never_become_numbers(self):
        for change in ({"value": True}, {"value": float("nan")}, {"value": float("inf")},
                       {"value": "12"}, {"status": "AMBIGUOUS"}, {"fact_id": None},
                       {"duration_semantics": "DISCRETE_AND_YTD"}, {"provenance": {}},
                       {"provenance": {"filing_accession": "OTHER", "raw_sha256": "hash"}}):
            source = fixture()
            source["statement_history"]["quarterly"]["statements"]["INCOME_STATEMENT"][0]["cells"][1].update(change)
            with self.subTest(change=change):
                profit = build_earnings_reader(source)["rows"][1]
                self.assertIsNone(profit["latest"])
                self.assertEqual(profit["prior"]["value"], 0)

    def test_no_guessing_among_concepts_units_or_periods(self):
        for mode in ("duplicate_concept", "duplicate_cell", "wrong_unit", "wrong_concept", "wrong_quarter", "duplicate_period"):
            source = fixture()
            q = source["statement_history"]["quarterly"]
            row = q["statements"]["INCOME_STATEMENT"][0]
            if mode == "duplicate_concept":
                q["statements"]["INCOME_STATEMENT"].append(deepcopy(row))
            elif mode == "duplicate_cell":
                row["cells"].append(deepcopy(row["cells"][0]))
            elif mode == "wrong_unit":
                row["unit"]["canonical"] = "USD_PER_SHARE"
            elif mode == "wrong_concept":
                row["concept"] = "custom:NetIncomeLoss"
            elif mode == "wrong_quarter":
                q["visible_periods"][0]["fiscal_quarter"] = 1
            else:
                q["visible_periods"].append(deepcopy(q["visible_periods"][0]))
            with self.subTest(mode=mode):
                self.assertIsNone(build_earnings_reader(source)["rows"][1]["prior"])

    def test_q1_basis_and_missing_date(self):
        source = fixture()
        q = source["statement_history"]["quarterly"]
        for period in q["visible_periods"]:
            period.update(fiscal_quarter=1, filed_date=None)
        for cell in q["statements"]["INCOME_STATEMENT"][0]["cells"]:
            cell["duration_semantics"] = "DISCRETE_AND_YTD"
        latest = build_earnings_reader(source)["rows"][1]["latest"]
        self.assertEqual(latest["basis"], "DISCRETE_AND_YTD")
        self.assertIsNone(latest["filed_date"])

    def test_renderer_shows_sources_ytd_missing_and_advanced_detail(self):
        tree = ast.parse((Path(__file__).parents[1] / "customer_research_v2.py").read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                        and n.name == "_render_earnings_reader")
        st = Mock()
        st.expander.side_effect = lambda *a, **k: nullcontext()
        namespace = dict(st=st, Mapping=Mapping, Any=Any, build_earnings_reader=build_earnings_reader,
                         _escape_markdown_currency=str, _financial_value=lambda v, u: str(v))
        exec(compile(ast.Module(body=[function], type_ignores=[]), "reader", "exec"), namespace)
        namespace["_render_earnings_reader"](fixture())
        output = " ".join(str(c) for c in st.mock_calls)
        for expected in ("Year-to-date through 2025-06-30", "Filed: 2025-08-01", "fact:2025",
                         "REPORTED_CUMULATIVE_YTD", "unavailable", "beat or miss"):
            self.assertIn(expected, output)
        st.reset_mock()
        namespace["_render_earnings_reader"]({"status": "RATING_NOT_PUBLISHED"})
        st.info.assert_called_once()
        st.write.assert_not_called()


if __name__ == "__main__":
    unittest.main()
