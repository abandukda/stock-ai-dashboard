#!/usr/bin/env python3
"""Portable XLSX writer for the GitHub Actions certification runner."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import xlsxwriter


PRICE_FIELDS = {
    "current_price", "completed_close", "base_fv", "fair_value_low", "fair_value_high",
    "bear_case", "bull_case", "street_target", "street_target_low", "street_target_high",
    "entry_low", "entry_high", "stop", "technical_target", "sma50", "sma200", "support",
    "resistance", "value", "model_value", "calculated_per_share",
}
INTEGER_FIELDS = {
    "market_cap", "provider_market_cap", "calculated_market_cap", "revenue", "eps", "ebit",
    "ebitda", "ocf", "capex", "capex_raw", "capex_normalized", "fcf", "calculated_fcf",
    "provider_fcf", "cash", "debt", "net_debt", "equity", "assets", "shares",
    "enterprise_value", "equity_value",
}


def _serial(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, sort_keys=True, default=str)
    return value if not isinstance(value, str) or len(value) <= 1000 else f"{value[:997]}..."


def export(report_path: Path, output_path: Path) -> None:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    book = xlsxwriter.Workbook(output_path)
    book.set_properties({"title": "ATLAS Full-Universe QA Certification", "company": "ATLAS"})
    header = book.add_format({"font_name": "Arial", "font_size": 10, "bold": True,
                              "font_color": "#FFFFFF", "bg_color": "#19324D",
                              "align": "center", "valign": "vcenter", "text_wrap": True})
    body = book.add_format({"font_name": "Arial", "font_size": 10, "font_color": "#172033",
                            "valign": "top", "text_wrap": True})
    money = book.add_format({"font_name": "Arial", "font_size": 10, "num_format": "$#,##0.00"})
    integer = book.add_format({"font_name": "Arial", "font_size": 10, "num_format": "#,##0"})
    percent = book.add_format({"font_name": "Arial", "font_size": 10, "num_format": "0.0%"})
    decimal_percent = book.add_format({"font_name": "Arial", "font_size": 10, "num_format": "0.0"})
    for sheet_name, rows in report["sheets"].items():
        sheet = book.add_worksheet(sheet_name[:31])
        columns = list(dict.fromkeys(key for row in rows for key in row)) or ["Status"]
        sheet.hide_gridlines(2)
        sheet.freeze_panes(1, min(2, len(columns)))
        sheet.set_row(0, 32)
        for col, key in enumerate(columns):
            sheet.write(0, col, key, header)
            values = [_serial(row.get(key)) for row in rows] if rows else ["No records"]
            width = min(42, max(len(key) + 2, *(min(len(str(value)) + 2, 42) for value in values)))
            sheet.set_column(col, col, width)
            fmt = money if key in PRICE_FIELDS else integer if key in INTEGER_FIELDS else (
                decimal_percent if "margin_pct" in key else percent if key.endswith("_pct") or key in {"wacc", "terminal_growth"} else body
            )
            for row_index, value in enumerate(values, 1):
                sheet.write(row_index, col, value, fmt)
        if rows:
            sheet.autofilter(0, 0, len(rows), len(columns) - 1)
    book.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: export_full_qa_xlsx.py report.json output.xlsx")
    export(Path(sys.argv[1]), Path(sys.argv[2]))
