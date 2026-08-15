"""Fail-closed validation for the isolated Phase 4B point-in-time panel."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable, Mapping


MODEL_INPUT_FIELDS = {
    "price", "forward_pe", "forward_eps", "revenue_growth", "operating_margin",
    "sector", "industry",
}
FUTURE_LABEL_FIELDS = {
    "return_1m", "return_3m", "spy_return_1m", "spy_return_3m",
    "sector_return_1m", "sector_return_3m", "excess_spy_1m", "excess_spy_3m",
    "excess_sector_1m", "excess_sector_3m",
}


def _date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None


def validate_row(row: Mapping[str, Any]) -> list[dict[str, str]]:
    """Return violations. Any non-empty result excludes the row from the panel."""
    violations: list[dict[str, str]] = []
    observed = _date(row.get("observation_date"))
    if observed is None:
        violations.append({"code": "INVALID_OBSERVATION_DATE", "detail": "observation_date is missing or invalid"})
    if not row.get("formula_version"):
        violations.append({"code": "MISSING_FORMULA_VERSION", "detail": "formula_version is required"})

    for field in MODEL_INPUT_FIELDS:
        value = row.get(field)
        if value is not None and not row.get(f"{field}_provenance"):
            violations.append({"code": "MISSING_INPUT_PROVENANCE", "detail": field})

    for vintage_field in ("filing_available_date", "estimate_vintage_date", "fundamentals_vintage_date"):
        vintage = _date(row.get(vintage_field))
        if observed and vintage and vintage > observed:
            violations.append({"code": "LOOKAHEAD_DATE", "detail": f"{vintage_field}={vintage.isoformat()}"})

    forbidden_sources = {"CURRENT", "LATEST", "TODAY", "CURRENT_PROVIDER", "LATEST_PROVIDER"}
    for field in MODEL_INPUT_FIELDS:
        source = str(row.get(f"{field}_provenance") or "").upper()
        if any(marker in source for marker in forbidden_sources):
            violations.append({"code": "CURRENT_DATA_USED_HISTORICALLY", "detail": f"{field}:{source}"})

    inputs = set(row.get("model_input_fields") or MODEL_INPUT_FIELDS)
    leaked = sorted(inputs & FUTURE_LABEL_FIELDS)
    if leaked:
        violations.append({"code": "FUTURE_RETURN_AS_MODEL_INPUT", "detail": ",".join(leaked)})

    method = row.get("forward_eps_method")
    eps = row.get("forward_eps")
    if method == "DERIVED_FROM_CONTEMPORANEOUS_PRICE_AND_PE":
        price, pe = row.get("price"), row.get("forward_pe")
        if not price or not pe or price <= 0 or pe <= 0 or eps is None or abs(eps - price / pe) > 1e-8:
            violations.append({"code": "INVALID_DERIVED_EPS", "detail": "EPS must equal contemporaneous price / forward P/E"})
    elif eps is not None and method not in {"PROVIDER_DIRECT", "DERIVED_FROM_CONTEMPORANEOUS_PRICE_AND_PE"}:
        violations.append({"code": "INVALID_EPS_PROVENANCE", "detail": str(method)})

    return violations


def validate_panel(rows: Iterable[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    valid: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for source_row in rows:
        row = dict(source_row)
        month = str(row.get("observation_date") or "")[:7]
        key = (str(row.get("ticker") or "").upper(), month)
        row_violations = validate_row(row)
        if key in seen:
            row_violations.append({"code": "DUPLICATE_TICKER_MONTH", "detail": f"{key[0]}:{key[1]}"})
        if row_violations:
            violations.append({
                "scan_commit_sha": row.get("scan_commit_sha"),
                "ticker": row.get("ticker"),
                "observation_date": row.get("observation_date"),
                "violations": row_violations,
            })
        else:
            seen.add(key)
            valid.append(row)
    return valid, violations
