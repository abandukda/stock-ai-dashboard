"""Provider-agnostic financial period identity for observational reconciliation."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any, Mapping


@dataclass(frozen=True)
class FinancialPeriodIdentity:
    canonical_security_id: str
    accession_number: str | None
    fiscal_period_end: str | None
    report_type: str | None
    filed_date: str | None
    fiscal_year: int | None
    fiscal_quarter: int | None
    source_provider: str
    source_period_label: str | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_period_identity(*, security_id: str, provider: str, accession: Any = None,
                          period_end: Any = None, report_type: Any = None, filed_date: Any = None,
                          fiscal_year: Any = None, fiscal_quarter: Any = None,
                          source_label: Any = None) -> FinancialPeriodIdentity:
    end = normalize_date(period_end)
    year = _integer(fiscal_year) or (int(end[:4]) if end else None)
    quarter = _quarter(fiscal_quarter if fiscal_quarter is not None else source_label)
    return FinancialPeriodIdentity(
        canonical_security_id=str(security_id).upper().strip(),
        accession_number=_text(accession), fiscal_period_end=end,
        report_type=normalize_report_type(report_type, source_label), filed_date=normalize_date(filed_date),
        fiscal_year=year, fiscal_quarter=quarter, source_provider=str(provider).upper().strip(),
        source_period_label=_text(source_label),
    )


def period_match(left: FinancialPeriodIdentity, right: FinancialPeriodIdentity) -> dict[str, Any]:
    if left.canonical_security_id != right.canonical_security_id:
        return {"matched": False, "basis": "SECURITY_ID_MISMATCH"}
    if left.accession_number and right.accession_number:
        same = left.accession_number == right.accession_number
        return {"matched": same, "basis": "ACCESSION_NUMBER" if same else "ACCESSION_MISMATCH"}
    if left.fiscal_period_end and right.fiscal_period_end:
        same_type = not left.report_type or not right.report_type or left.report_type == right.report_type
        same = left.fiscal_period_end == right.fiscal_period_end and same_type
        return {"matched": same, "basis": "FISCAL_PERIOD_END_AND_REPORT_TYPE" if same else "PERIOD_END_OR_TYPE_MISMATCH"}
    return {"matched": False, "basis": "INSUFFICIENT_PERIOD_IDENTITY"}


def identity_from_finnhub_report(symbol: str, report: Mapping[str, Any]) -> FinancialPeriodIdentity:
    return build_period_identity(
        security_id=symbol, provider="FINNHUB", accession=report.get("access_number"),
        period_end=report.get("fiscal_date"), report_type=report.get("filing_form") or report.get("fiscal_period"),
        filed_date=report.get("filed_date"), source_label=report.get("source_period") or report.get("fiscal_period"),
    )


def normalize_date(value: Any) -> str | None:
    if value in (None, "", "TTM", "MRQ"):
        return None
    if isinstance(value, datetime): return value.date().isoformat()
    if isinstance(value, date): return value.isoformat()
    text = str(value).strip()
    try: return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError: return text[:10] if len(text) >= 10 and text[4:5] == "-" else None


def normalize_report_type(value: Any, label: Any = None) -> str | None:
    text = str(value or label or "").upper().strip()
    if text in {"10-K", "20-F", "40-F", "FY", "ANNUAL"}: return "ANNUAL"
    if text in {"10-Q", "Q1", "Q2", "Q3", "Q4", "QUARTERLY"}: return "QUARTERLY"
    if text in {"TTM", "MRQ"}: return text
    return None


def _text(value: Any) -> str | None:
    text = str(value).strip() if value not in (None, "") else ""
    return text or None


def _integer(value: Any) -> int | None:
    try: return int(value)
    except (TypeError, ValueError): return None


def _quarter(value: Any) -> int | None:
    text = str(value or "").upper().strip().removeprefix("Q")
    number = _integer(text)
    return number if number in {1, 2, 3, 4} else None


__all__ = ["FinancialPeriodIdentity", "build_period_identity", "identity_from_finnhub_report", "normalize_date", "period_match"]
