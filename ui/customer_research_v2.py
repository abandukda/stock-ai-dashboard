"""Customer-facing ATLAS Research V2 renderer."""
from __future__ import annotations

from html import escape
from typing import Any, Callable, Mapping
from datetime import datetime
import hashlib
import json
import math

import pandas as pd
import streamlit as st

from services.customer_research_view import Availability, build_customer_research_view
from services.customer_metric_format import (
    customer_confidence,
    customer_money,
    customer_percent,
    customer_score,
)


def _six_pillar_display_rows(pillars: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    """Create one immutable, ticker-bound source for both chart and table."""
    rows = []
    for item in pillars.get("items") or ():
        score = item.get("certified_score")
        weight = item.get("weight")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(float(score)):
            continue
        if not 0.0 <= float(score) <= 100.0:
            continue
        if weight is not None and (
            isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(float(weight))
        ):
            weight = None
        weight_display = None
        if weight is not None:
            weight_display = float(weight) * 100.0 if item.get("weight_unit") == "FRACTION" else float(weight)
        rows.append(
            {
                "Pillar": str(item["pillar"]).replace("_", " ").title(),
                "Certified score": float(score),
                "Governed weight (%)": weight_display,
            }
        )
    return tuple(rows)


def _six_pillar_frame(pillars: Mapping[str, Any]) -> pd.DataFrame:
    rows = _six_pillar_display_rows(pillars)
    return pd.DataFrame(rows).set_index("Pillar") if rows else pd.DataFrame(columns=["Certified score", "Governed weight (%)"])


def _money(value: Any) -> str:
    return customer_money(value)


def _pct(value: Any, *, signed: bool = False) -> str:
    return customer_percent(value, signed=signed)


def _escape_markdown_currency(value: Any) -> str:
    """Preserve governed text while preventing Markdown dollar-math parsing."""
    return str(value).replace("$", "\\$")


def _marker(name: str, ticker: str, **attrs: Any) -> None:
    attributes = " ".join(
        f'data-atlas-{escape(str(key).replace("_", "-"))}="{escape(str(value))}"'
        for key, value in attrs.items()
    )
    st.markdown(
        f'<span data-atlas-qa="research-v2-{escape(name)}" data-atlas-ticker="{escape(ticker)}" '
        f'{attributes} aria-hidden="true" style="display:none">research-v2-{escape(name)}</span>',
        unsafe_allow_html=True,
    )


def _render_production_authority_marker(page: Mapping[str, Any]) -> bool:
    """Emit authority only from the final ticker-bound customer projection."""
    ticker = str(page.get("ticker") or "").strip().upper()
    identity = page.get("identity") if isinstance(page.get("identity"), Mapping) else {}
    authority = page.get("authority") if isinstance(page.get("authority"), Mapping) else {}
    evidence = page.get("evidence") if isinstance(page.get("evidence"), Mapping) else {}
    snapshot = str(identity.get("evaluation_snapshot") or "")
    candidate = str(identity.get("candidate_digest") or "")
    publication = str(identity.get("publication_digest") or "")
    source_sha = str(identity.get("source_sha") or "")
    if (
        not ticker
        or str(identity.get("ticker") or "").strip().upper() != ticker
        or not snapshot
        or snapshot != str(evidence.get("evaluation_snapshot_id") or "")
        or not candidate or candidate != str(evidence.get("candidate_digest") or "")
        or not publication or publication != str(evidence.get("publication_digest") or "")
        or not source_sha or source_sha != str(evidence.get("source_sha") or "")
    ):
        return False
    st.markdown(
        f'<span data-atlas-qa="research-production-authority" data-atlas-ticker="{escape(ticker)}" '
        f'data-atlas-action="{escape(str(authority.get("action") or ""))}" '
        f'data-atlas-fair-value="{escape(str(authority.get("fair_value") or ""))}" '
        f'data-atlas-opportunity="{escape(str(authority.get("opportunity") or ""))}" '
        f'data-atlas-confidence="{escape(str(authority.get("confidence") or ""))}" '
        f'data-atlas-evaluation-snapshot="{escape(snapshot)}" '
        f'data-atlas-candidate-digest="{escape(candidate)}" '
        f'data-atlas-publication-digest="{escape(publication)}" '
        f'data-atlas-source-sha="{escape(source_sha)}" '
        'aria-hidden="true" style="display:none">research-production-authority</span>',
        unsafe_allow_html=True,
    )
    return True


def _list(items: list[str]) -> None:
    # Streamlit Markdown treats dollar-delimited text as math. Escape currency
    # so governed debt/cash values remain readable and numerically unchanged.
    st.markdown("\n".join(f"- {_escape_markdown_currency(item)}" for item in items))


def _dates(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    if numeric.notna().all():
        return pd.to_datetime(numeric, unit="s", utc=True, errors="coerce")
    return pd.to_datetime(values, utc=True, errors="coerce")


def _provenance_caption(provenance: Mapping[str, Any]) -> str:
    source = provenance.get("source") or provenance.get("provider") or "Governed source"
    as_of = provenance.get("capture_timestamp") or provenance.get("as_of") or "timestamp unavailable"
    return f"Source: {str(source).replace('_', ' ').title()} · Evidence captured {_friendly_time(as_of)}"


def _dark_line_chart(frame: pd.DataFrame, *, height: int, y_title: str, key: str) -> None:
    series = [str(column) for column in frame.columns]
    palette = ["#2dd4bf", "#60a5fa", "#f59e0b", "#a78bfa"]
    data = frame.reset_index().rename(columns={frame.index.name or "index": "Date"}).melt("Date", var_name="Series", value_name="Value")
    st.vega_lite_chart(data, use_container_width=True, theme=None, key=key, spec={
        "height": height,
        "mark": {"type": "line", "strokeWidth": 2.2},
        "encoding": {
            "x": {"field": "Date", "type": "temporal", "axis": {"title": "Date", "format": "%b %Y", "tickCount": 6, "labelOverlap": "greedy", "labelColor": "#94a3b8", "titleColor": "#cbd5e1", "gridColor": "#1e293b"}},
            "y": {"field": "Value", "type": "quantitative", "scale": {"zero": False, "nice": True}, "axis": {"title": y_title, "labelColor": "#94a3b8", "titleColor": "#cbd5e1", "gridColor": "#1e293b"}},
            "color": {"field": "Series", "type": "nominal", "scale": {"domain": series, "range": palette[:len(series)]}, "legend": {"title": None, "orient": "bottom", "direction": "horizontal", "columns": 2, "labelLimit": 180, "labelColor": "#cbd5e1", "titleColor": "#cbd5e1"}},
            "tooltip": [{"field": "Date", "type": "temporal", "format": "%b %d, %Y"}, {"field": "Series"}, {"field": "Value", "format": ",.2f"}],
        },
        "config": {"background": "#08111f", "view": {"stroke": "#243244"}, "axis": {"domainColor": "#334155", "tickColor": "#334155"}},
    })


def _friendly_time(value: Any) -> str:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).strftime("%b %-d, %Y · %-I:%M %p UTC")
    except (TypeError, ValueError):
        return "Date unavailable"


def _financial_value(value: Any, unit: str) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "Unavailable"
    if unit == "PERCENT":
        return f"{number:,.1f}%"
    if unit == "USD_PER_SHARE":
        return f"${number:,.2f}"
    if unit == "USD":
        if abs(number) >= 1_000_000_000_000:
            return f"${number / 1_000_000_000_000:,.2f}T"
        if abs(number) >= 1_000_000_000:
            return f"${number / 1_000_000_000:,.2f}B"
        if abs(number) >= 1_000_000:
            return f"${number / 1_000_000:,.2f}M"
        return f"${number:,.2f}"
    return f"{number:,.2f}"


def _financial_period(value: Any) -> str:
    """Keep fiscal labels intact and render ISO dates without invented times."""
    text = str(value or "").strip()
    if not text:
        return "Unavailable"
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime("%b %-d, %Y")
    except ValueError:
        return text


def _financial_statement_rows(items: Any) -> list[dict[str, str]]:
    """Format retained statement facts without deriving periods or values."""
    rows: list[dict[str, str]] = []
    for item in items or ():
        if not isinstance(item, Mapping):
            continue
        rows.append({
            "Line item": str(item.get("label") or item.get("field") or "Financial evidence"),
            "Certified value": _financial_value(item.get("value"), str(item.get("unit") or "")),
            "Fiscal period": _financial_period(item.get("period") or item.get("as_of")),
            "Source": str(item.get("provider") or "Certified source"),
            "Evidence ID": str(item.get("evidence_id") or "Unavailable"),
        })
    return rows


def _technical_chart_frames(rows: pd.DataFrame, *, date_key: str, ticker: str,
                            close_key: str, indicator_keys: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Separate price-unit overlays from bounded oscillators.

    A moving average may share the stock-price axis. RSI may not: combining
    dollars and a 0-100 oscillator on one axis is visually misleading even
    when every retained value is correct.
    """
    dated = rows.dropna(subset=[date_key]).set_index(date_key)
    price_keys = [key for key in indicator_keys if key != "rsi"]
    price_columns = [key for key in [close_key, *price_keys] if key in dated]
    price_frame = dated[price_columns].rename(columns={close_key: ticker}) if price_columns else pd.DataFrame()
    oscillator_frame = dated[["rsi"]].rename(columns={"rsi": "RSI (0-100)"}) if "rsi" in indicator_keys else pd.DataFrame()
    return price_frame, oscillator_frame


def _financial_depth_status_rows(depth: Mapping[str, Any]) -> list[dict[str, str]]:
    statements = depth.get("statements") if isinstance(depth.get("statements"), Mapping) else {}
    labels = {
        "income_statement": "Income statement",
        "cash_flow": "Cash flow",
        "balance_sheet": "Balance sheet",
    }
    rows: list[dict[str, str]] = []
    for lane, label in labels.items():
        facts = list(statements.get(lane) or ())
        periods = {
            str(item.get("period") or item.get("as_of") or "").strip()
            for item in facts if isinstance(item, Mapping)
            and str(item.get("period") or item.get("as_of") or "").strip()
        }
        if not facts:
            depth_label = "No retained periods"
        elif periods:
            depth_label = f"{len(periods)} retained period{'s' if len(periods) != 1 else ''}"
        else:
            depth_label = "Period unavailable"
        rows.append({
            "Statement": label,
            "Coverage": "Available" if facts else "Unavailable",
            "Certified line items": str(len(facts)),
            "Period depth": depth_label,
        })
    return rows


def _financial_depth_status_markup(rows: list[dict[str, str]], *, ticker: str) -> str:
    cards = []
    for row in rows:
        available = row["Coverage"] == "Available"
        state = "available" if available else "unavailable"
        cards.append(
            f'<article class="atlas-financial-coverage-card atlas-financial-coverage-{state}" '
            f'data-atlas-qa="research-v2-financial-coverage-card" data-atlas-ticker="{escape(ticker)}" '
            f'data-atlas-state="{state}"><small>{escape(row["Statement"])}</small>'
            f'<strong>{escape(row["Coverage"])}</strong>'
            f'<span>{escape(row["Certified line items"])} certified line items · '
            f'{escape(row["Period depth"])}</span></article>'
        )
    return (
        '<style>.atlas-financial-coverage{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));'
        'gap:.5rem;margin:.55rem 0 .75rem}.atlas-financial-coverage-card{padding:.65rem .7rem;'
        'border:1px solid rgba(148,163,184,.2);border-radius:11px;background:#0b1525;min-width:0}'
        '.atlas-financial-coverage-card small,.atlas-financial-coverage-card strong,'
        '.atlas-financial-coverage-card span{display:block}.atlas-financial-coverage-card small{color:#94a3b8;'
        'font-size:.7rem}.atlas-financial-coverage-card strong{margin:.2rem 0;color:#5eead4;font-size:.92rem}'
        '.atlas-financial-coverage-card span{color:#cbd5e1;font-size:.76rem;line-height:1.35}'
        '.atlas-financial-coverage-unavailable strong{color:#94a3b8}'
        '@media(max-width:700px){.atlas-financial-coverage{grid-template-columns:1fr}.atlas-financial-coverage-card{padding:.55rem .62rem}}'
        '</style><section class="atlas-financial-coverage" aria-label="Certified financial statement coverage">'
        + "".join(cards) + "</section>"
    )


def _render_financial_depth(depth: Mapping[str, Any], *, ticker: str) -> None:
    """Render premium financial depth with explicit evidence limitations."""
    status = str(depth.get("status") or "NOT_AVAILABLE")
    period_depth = str(depth.get("statement_depth") or "LATEST_PERIOD_ONLY")
    _marker("financial-depth", ticker, status=status, statement_depth=period_depth)
    st.markdown("### Financial statements")
    st.caption(
        "These tables show retained certified line items, not a reconstructed filing. "
        "Unavailable statements and periods remain explicitly unavailable."
    )
    coverage_rows = _financial_depth_status_rows(depth)
    st.markdown(_financial_depth_status_markup(coverage_rows, ticker=ticker), unsafe_allow_html=True)
    with st.expander("Statement coverage details", expanded=False):
        st.dataframe(
            pd.DataFrame(coverage_rows), hide_index=True,
            use_container_width=True, key=f"research-statement-coverage-{ticker}",
        )
    if status == "NOT_AVAILABLE":
        st.info("Certified income statement, cash-flow, and balance-sheet line items are unavailable for this snapshot.")
    else:
        labels = {
            "income_statement": "Income statement",
            "cash_flow": "Cash flow",
            "balance_sheet": "Balance sheet",
        }
        statements = depth.get("statements") if isinstance(depth.get("statements"), Mapping) else {}
        tabs = st.tabs(list(labels.values()))
        for tab, (lane, title) in zip(tabs, labels.items()):
            with tab:
                rows = _financial_statement_rows(statements.get(lane))
                if rows:
                    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                                 key=f"research-{lane}-{ticker}")
                else:
                    st.info(f"Certified {title.lower()} line items are unavailable for this snapshot.")
        if depth.get("limitation"):
            st.caption(str(depth["limitation"]))

    models = list(depth.get("valuation_models") or ())
    st.markdown("### Certified valuation models")
    if models:
        rows = []
        for item in models:
            weight = item.get("weight")
            weight_pct = float(weight) * 100 if weight is not None and float(weight) <= 1 else weight
            rows.append({
                "Model": item.get("name") or item.get("methodology_id"),
                "Fair value": _financial_value(item.get("value"), str(item.get("unit") or "")),
                "Fiscal period": item.get("fiscal_period") or "Unavailable",
                "Confidence": customer_score(item.get("confidence")),
                "Governed weight": _pct(weight_pct),
                "Source": item.get("source") or "Certified ATLAS valuation",
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                     key=f"research-valuation-models-{ticker}")
    else:
        st.info("Published certified valuation-model detail is unavailable for this snapshot.")

    company_case = depth.get("company_case") if isinstance(depth.get("company_case"), Mapping) else {}
    st.markdown("### Company-specific investment case")
    for title, key in (("What supports the case", "thesis"), ("What could go wrong", "risks"),
                       ("What would invalidate the case", "invalidation")):
        items = [str(item) for item in company_case.get(key) or () if str(item).strip()]
        st.markdown(f"**{title}**")
        if items:
            _list(items)
        else:
            st.caption("No approved company-specific evidence is retained for this item.")
    if company_case.get("invalidation_limitation"):
        st.caption(str(company_case["invalidation_limitation"]))


def _annual_statement_frame(statement: Any, periods: Any) -> pd.DataFrame:
    """Pivot retained cells for display; never calculate or fill a value."""
    period_rows = [item for item in periods or () if isinstance(item, Mapping)]
    accession_period = {
        str(item.get("accession")): str(item.get("fiscal_year") or item.get("fiscal_period_end") or "Unavailable")
        for item in period_rows
    }
    columns = list(accession_period.values())
    rows: list[dict[str, str]] = []
    for item in statement or ():
        if not isinstance(item, Mapping):
            continue
        labels = item.get("observed_labels") or ()
        label = str(next(iter(labels), None) or item.get("concept") or item.get("field_id") or "Unlabeled fact")
        row = {"Line item": label}
        by_accession = {
            str(cell.get("accession")): cell for cell in item.get("cells") or () if isinstance(cell, Mapping)
        }
        unit = item.get("unit") if isinstance(item.get("unit"), Mapping) else {}
        canonical = str(unit.get("canonical") or "")
        for accession, period in accession_period.items():
            cell = by_accession.get(accession) or {}
            row[period] = (
                _financial_value(cell.get("value"), canonical)
                if cell.get("status") == "AVAILABLE" else "Unavailable"
            )
        rows.append(row)
    return pd.DataFrame(rows, columns=["Line item", *columns])


def _statement_history_period_label(period: Mapping[str, Any], *, frequency: str) -> str:
    if frequency == "quarterly":
        year = period.get("fiscal_year")
        quarter = period.get("fiscal_quarter")
        return f"FY{year} Q{quarter}" if year and quarter else _financial_period(period.get("fiscal_period_end"))
    return str(period.get("fiscal_year") or _financial_period(period.get("fiscal_period_end")))


def _statement_history_frame(statement: Any, periods: Any, *, frequency: str) -> pd.DataFrame:
    """Pivot exact retained history cells without filling, scaling, or calculating."""
    period_rows = [item for item in periods or () if isinstance(item, Mapping)]
    accession_period = {
        str(item.get("accession")): _statement_history_period_label(item, frequency=frequency)
        for item in period_rows
    }
    columns = list(accession_period.values())
    rows: list[dict[str, str]] = []
    order = (
        "revenue", "cost of revenue", "gross profit", "operating expense", "operating income",
        "interest", "income before tax", "income tax", "net income", "earnings per share",
        "operating cash", "capital expenditure", "free cash flow", "cash", "total assets",
        "total debt", "total liabilities", "stockholders equity",
    )
    def row_rank(item: Mapping[str, Any]) -> tuple[int, str]:
        labels = item.get("labels") or item.get("observed_labels") or ()
        label = str(next(iter(labels), None) or item.get("concept") or item.get("field_id") or "")
        lowered = label.casefold()
        return (next((index for index, token in enumerate(order) if token in lowered), len(order)), lowered)

    for item in sorted((entry for entry in statement or () if isinstance(entry, Mapping)), key=row_rank):
        labels = item.get("labels") or item.get("observed_labels") or ()
        label = str(next(iter(labels), None) or item.get("concept") or item.get("field_id") or "Unlabeled fact")
        row = {"Line item": label}
        by_accession = {
            str(cell.get("accession")): cell for cell in item.get("cells") or () if isinstance(cell, Mapping)
        }
        unit = item.get("unit") if isinstance(item.get("unit"), Mapping) else {}
        canonical = str(unit.get("canonical") or "")
        for accession, period in accession_period.items():
            cell = by_accession.get(accession) or {}
            row[period] = (
                _financial_value(cell.get("value"), canonical)
                if cell.get("status") == "AVAILABLE" else "Unavailable"
            )
        rows.append(row)
    return pd.DataFrame(rows, columns=["Line item", *columns])


def _statement_history_trend(statement: Any, periods: Any, *, frequency: str) -> pd.DataFrame:
    """Return one exact, same-unit reported series suitable for a customer trend chart."""
    preferred = ("revenue", "sales", "net income", "operating income", "free cash flow")
    period_rows = [item for item in periods or () if isinstance(item, Mapping)]
    by_accession = {str(item.get("accession")): item for item in period_rows}
    candidates = []
    for item in statement or ():
        if not isinstance(item, Mapping):
            continue
        unit = item.get("unit") if isinstance(item.get("unit"), Mapping) else {}
        if str(unit.get("canonical") or "") not in {"USD", "USD_PER_SHARE", "NUMBER"}:
            continue
        labels = item.get("labels") or item.get("observed_labels") or ()
        label = str(next(iter(labels), None) or item.get("concept") or "Financial trend")
        rank = next((index for index, token in enumerate(preferred) if token in label.lower()), len(preferred))
        cells = []
        for cell in item.get("cells") or ():
            if not isinstance(cell, Mapping) or cell.get("status") != "AVAILABLE":
                continue
            period = by_accession.get(str(cell.get("accession")))
            value = cell.get("value")
            if not period or isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            cells.append({
                "Period": _statement_history_period_label(period, frequency=frequency),
                "Value": float(value), "Series": label,
            })
        if len(cells) >= 2:
            candidates.append((rank, label, cells))
    if not candidates:
        return pd.DataFrame(columns=["Period", "Value", "Series"])
    return pd.DataFrame(sorted(candidates, key=lambda item: (item[0], item[1]))[0][2])


def _per_share_credibility_rows(credibility: Mapping[str, Any]) -> list[dict[str, str]]:
    """Expose filing-reported EPS/share bases without cross-basis arithmetic."""
    if (
        credibility.get("contract") != "ATLAS_CUSTOMER_PER_SHARE_CREDIBILITY_V1"
        or credibility.get("provider_calls") != 0
        or credibility.get("rating_authority") != "UNCHANGED"
        or credibility.get("publication_authority") != "UNCHANGED"
    ):
        return []
    rows = []
    for record in credibility.get("records") or ():
        if not isinstance(record, Mapping):
            continue
        eps = record.get("diluted_eps") if isinstance(record.get("diluted_eps"), Mapping) else {}
        shares = record.get("diluted_weighted_average_shares") if isinstance(record.get("diluted_weighted_average_shares"), Mapping) else {}
        basis = record.get("share_basis") if isinstance(record.get("share_basis"), Mapping) else {}
        eps_value = eps.get("value") if eps.get("status") == "AVAILABLE" else None
        share_value = shares.get("value") if shares.get("status") == "AVAILABLE" else None
        rows.append({
            "Fiscal year": str(record.get("fiscal_year") or "Unavailable"),
            "Period end": str(record.get("period_end") or "Unavailable"),
            "Diluted EPS (reported)": _financial_value(eps_value, "USD_PER_SHARE") if eps_value is not None else "Unavailable",
            "Diluted weighted-average shares": f"{float(share_value):,.0f}" if share_value is not None else "Unavailable",
            "Share-basis comparability": str(basis.get("comparability_to_prior_period") or "NOT_CERTIFIED").replace("_", " ").title(),
            "Filing accession": str(record.get("accession") or "Unavailable"),
            "EPS fact ID": str(eps.get("fact_id") or "Unavailable"),
        })
    return rows


def _render_per_share_credibility(credibility: Mapping[str, Any], *, ticker: str) -> None:
    rows = _per_share_credibility_rows(credibility)
    if not rows:
        return
    discontinuities = sum(
        bool((record.get("share_basis") or {}).get("discontinuity_from_prior_period"))
        for record in credibility.get("records") or () if isinstance(record, Mapping)
    )
    _marker("per-share-credibility", ticker, records=len(rows), discontinuities=discontinuities)
    st.markdown("#### Filing-reported diluted EPS and share basis")
    st.warning(
        "Historical diluted EPS is shown exactly as reported in each filing. The retained evidence does not "
        "certify a common corporate-action-adjusted share basis, so periods flagged with a share-count "
        "discontinuity are not plotted or presented as directly comparable. No split adjustment was inferred."
    )
    st.dataframe(
        pd.DataFrame(rows[-8:]), hide_index=True, use_container_width=True,
        key=f"research-history-eps-credibility-{ticker}",
    )
    st.caption(
        f"{len(rows)} filing periods retained · {discontinuities} unverified share-basis discontinuities · "
        "reported zero remains zero; missing remains Unavailable. See accession and fact ID for lineage."
    )


def _render_combined_statement_history(history: Mapping[str, Any], *, ticker: str) -> bool:
    """Render source-bound annual plus quarterly history when its authority contract is present."""
    if (
        history.get("contract") != "ATLAS_CUSTOMER_STATEMENT_HISTORY_PROJECTION_V1"
        or history.get("status") != "AVAILABLE"
        or str(history.get("ticker") or "").upper() != ticker
        or history.get("read_only") is not True
        or history.get("rating_authority") != "UNCHANGED"
        or history.get("publication_authority") != "UNCHANGED"
        or history.get("provider_calls") != 0
    ):
        return False
    annual = history.get("annual") if isinstance(history.get("annual"), Mapping) else {}
    quarterly = history.get("quarterly") if isinstance(history.get("quarterly"), Mapping) else {}
    _marker(
        "statement-history", ticker, status="AVAILABLE", classification="historical-non-scoring",
        annual_periods=annual.get("visible_period_count", 0),
        quarterly_periods=quarterly.get("visible_period_count", 0),
    )
    st.markdown("### Financial statement history")
    st.markdown(
        '<style>[class*="st-key-research-history-"] [data-testid="stDataFrame"]{border:1px solid #334155;'
        'border-radius:12px;background:#07111f;color:#f8fafc}[class*="st-key-research-history-"] '
        '[role="columnheader"]{background:#111c2e!important;color:#f8fafc!important;font-weight:750!important}'
        '[class*="st-key-research-history-"] [role="gridcell"]{color:#e2e8f0!important;text-align:right}'
        '[class*="st-key-research-history-"] [role="gridcell"]:first-child{text-align:left;font-weight:650}'
        '@media(max-width:420px){[class*="st-key-research-history-"]{overflow-x:auto} '
        '[class*="st-key-research-history-"] [data-testid="stDataFrame"]{min-width:680px}}</style>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Reported filing facts with retained lineage. Annual and quarterly history is read-only context and "
        "does not change the certified Action, Fair Value, Opportunity, Confidence, or publication status."
    )
    annual_tab, quarterly_tab = st.tabs(["Annual history", "Quarterly history"])
    lanes = {
        "INCOME_STATEMENT": "Income statement",
        "CASH_FLOW": "Cash flow",
        "BALANCE_SHEET": "Balance sheet",
    }
    for container, frequency, projection in (
        (annual_tab, "annual", annual), (quarterly_tab, "quarterly", quarterly),
    ):
        with container:
            periods = projection.get("visible_periods") or projection.get("periods") or ()
            statements = projection.get("statements") if isinstance(projection.get("statements"), Mapping) else {}
            if projection.get("status") != "AVAILABLE" or not periods:
                st.info(f"Validated {frequency} filing history is unavailable for this security.")
                continue
            statement_tabs = st.tabs(list(lanes.values()))
            for statement_tab, (lane, label) in zip(statement_tabs, lanes.items()):
                with statement_tab:
                    statement = statements.get(lane) or ()
                    if isinstance(statement, Mapping):
                        statement = statement.get("rows") or ()
                    frame = _statement_history_frame(statement, periods, frequency=frequency)
                    if frame.empty:
                        st.info(f"Validated {frequency} {label.lower()} facts are unavailable.")
                    else:
                        st.dataframe(
                            frame, hide_index=True, use_container_width=True,
                            key=f"research-history-{frequency}-{lane.lower()}-{ticker}",
                        )
            income_statement = statements.get("INCOME_STATEMENT") or ()
            if isinstance(income_statement, Mapping):
                income_statement = income_statement.get("rows") or ()
            trend = _statement_history_trend(income_statement, periods, frequency=frequency)
            if not trend.empty:
                st.markdown(f"**{frequency.title()} reported trend**")
                st.line_chart(trend.set_index("Period")[["Value"]], use_container_width=True)
                st.caption(f"Exact reported {trend.iloc[0]['Series']} values; no interpolation or forecast.")
    disclosure = quarterly.get("disclosure") if isinstance(quarterly.get("disclosure"), Mapping) else {}
    _render_per_share_credibility(
        history.get("per_share_credibility") if isinstance(history.get("per_share_credibility"), Mapping) else {},
        ticker=ticker,
    )
    with st.expander("Sources and accounting boundaries", expanded=False):
        st.markdown(
            "- Annual source: retained `/stock/financials-reported` annual filings.\n"
            "- Quarterly source: retained `/stock/financials-reported` quarterly filings.\n"
            "- Quarterly income-statement and cash-flow values are cumulative year-to-date except Q1.\n"
            "- A discrete quarter is shown only when an exact prior-YTD match supports subtraction.\n"
            "- Balance-sheet values are instantaneous at period end. Missing values remain Unavailable, never zero."
        )
        st.caption(
            f"Annual source hash: {annual.get('source_presentation_sha256') or annual.get('presentation_sha256') or 'Unavailable'} · "
            f"Quarterly normalized hash: {quarterly.get('source_normalized_sha256') or 'Unavailable'} · "
            f"Quarterly series hash: {quarterly.get('source_series_sha256') or 'Unavailable'} · "
            f"Boundary: {disclosure.get('missing_values') or 'NEVER_RENDER_AS_ZERO'}"
        )
    return True


def _render_annual_financial_statements(history: Mapping[str, Any], *, ticker: str) -> None:
    status = str(history.get("status") or "UNAVAILABLE")
    periods = list(history.get("periods") or ())
    statements = history.get("statements") if isinstance(history.get("statements"), Mapping) else {}
    _marker("annual-financial-statements", ticker, status=status, periods=len(periods), classification="historical-non-scoring")
    st.markdown("### Annual filing history")
    st.caption(
        "Reported annual filing facts with retained source lineage. These historical tables are context only: "
        "they do not change the certified Action, Fair Value, Opportunity, Confidence, or publication status."
    )
    if status != "AVAILABLE":
        st.info(history.get("message") or "Validated annual filing history is unavailable for this security.")
        return
    labels = {
        "INCOME_STATEMENT": "Annual income statement",
        "CASH_FLOW": "Annual cash flow",
        "BALANCE_SHEET": "Annual balance sheet",
    }
    tabs = st.tabs(list(labels.values()))
    for tab, (lane, title) in zip(tabs, labels.items()):
        with tab:
            frame = _annual_statement_frame(statements.get(lane), periods)
            if frame.empty:
                st.info(f"Validated annual {title.lower()} facts are unavailable.")
            else:
                st.dataframe(frame, hide_index=True, use_container_width=True,
                             key=f"research-annual-{lane.lower()}-{ticker}")
    latest = periods[-1] if periods else {}
    st.caption(
        f"Latest retained fiscal year: {latest.get('fiscal_year') or 'Unavailable'} · "
        f"Filing accession: {latest.get('accession') or 'Unavailable'} · "
        f"Source presentation: {history.get('source_presentation_sha256') or 'Unavailable'} · "
        "Provider endpoint: /stock/financials-reported (annual)."
    )


def _range_rows(frame: pd.DataFrame, selected: str) -> pd.DataFrame:
    """Return a display-only date window without altering retained values."""
    if frame.empty or selected == "1Y":
        return frame
    months = {"1M": 1, "3M": 3, "6M": 6}.get(selected)
    if months is None:
        return frame
    cutoff = frame.index.max() - pd.DateOffset(months=months)
    return frame.loc[frame.index >= cutoff]


def render_customer_research_first_screen(report: Mapping[str, Any]) -> dict[str, Any]:
    """Render the settled ticker's customer-safe summary before search controls."""
    customer_view = build_customer_research_view(report)
    page = customer_view.as_mapping()
    ticker = str(page.get("ticker") or "UNKNOWN")
    if page.get("status") != "AVAILABLE":
        _marker("terminal", ticker, state="RATING_NOT_PUBLISHED")
        company = str(page.get("company") or ticker)
        identity = ticker if company.upper() == ticker else f"{ticker} · {company}"
        disposition = str(page.get("withheld_disposition") or "RATING_NOT_PUBLISHED")
        reason = (
            "ATLAS does not currently publish an investment rating for this security under its certified model."
            if disposition != "HUMAN_REVIEW_QUEUED"
            else "ATLAS has not published a rating while an authorized review is pending."
        )
        st.markdown(
            '<section data-atlas-qa="research-withheld-message" '
            f'data-atlas-ticker="{escape(ticker)}" role="status" '
            'style="padding:.9rem 1rem;border:1px solid rgba(251,191,36,.35);'
            'border-radius:12px;background:rgba(120,53,15,.18);color:#f8fafc;'
            'font-size:1rem;line-height:1.5;margin:.5rem 0 1rem">'
            f'<strong>{escape(identity)}</strong><br>'
            f'A certified ATLAS rating is not available for {escape(ticker)}.<br>'
            f'{escape(reason)}'
            '</section>',
            unsafe_allow_html=True,
        )
        return page
    h = page["header"]
    confidence_score = customer_confidence(h["confidence"])
    _marker("root", ticker, version=page["version"], authority="certified_customer_evaluation", section_count=5)
    st.markdown("""<style>
    .atlas-r2-head{padding:.9rem 1rem;border:1px solid rgba(45,212,191,.25);border-radius:16px;background:linear-gradient(145deg,rgba(15,23,42,.96),rgba(18,39,51,.88));margin-bottom:.55rem}.atlas-r2-kicker{color:#61d8c3;font-size:.68rem;font-weight:800;letter-spacing:.13em}.atlas-r2-title{display:flex;align-items:baseline;justify-content:space-between;gap:.8rem;flex-wrap:wrap}.atlas-r2-head h1{margin:.18rem 0;font-size:1.55rem}.atlas-r2-action{color:#5eead4;font-size:.82rem;font-weight:850;letter-spacing:.07em}.atlas-r2-meta{color:#94a3b8;font-size:.76rem}.atlas-r2-metrics{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:.55rem;margin:.65rem 0}.atlas-r2-metric{padding:.7rem .75rem;border:1px solid rgba(148,163,184,.18);border-radius:12px;background:#0f192b;min-width:0}.atlas-r2-metric small{display:block;color:#8ea1bb;font-size:.62rem;letter-spacing:.08em;text-transform:uppercase}.atlas-r2-metric strong{display:block;color:#f8fafc;font-size:1.15rem;line-height:1.15;margin-top:.25rem;overflow-wrap:anywhere}.atlas-r2-grid{display:grid;grid-template-columns:1fr 1fr;gap:.7rem}.atlas-r2-panel{padding:.9rem;border:1px solid rgba(148,163,184,.16);border-radius:14px;background:rgba(15,23,42,.55)}
    @media(max-width:700px){.atlas-r2-head h1{font-size:1.25rem}.atlas-r2-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.atlas-r2-metric strong{font-size:1rem}.atlas-r2-grid{grid-template-columns:1fr}.atlas-r2-panel{padding:.75rem}}
    </style>""", unsafe_allow_html=True)
    st.markdown(
        f'<section class="atlas-r2-head"><div class="atlas-r2-kicker">CERTIFIED ATLAS RESEARCH</div>'
        f'<div class="atlas-r2-title"><h1>{escape(ticker)} · {escape(str(page["company"]))}</h1><span class="atlas-r2-action">{escape(h["action"])}</span></div>'
        f'<div class="atlas-r2-meta">{escape(str(page.get("sector") or "Sector unavailable"))} · Last certified close {escape(str(h.get("evidence_as_of") or "Date unavailable"))}</div>'
        f'<div class="atlas-r2-metrics">'
        f'<div class="atlas-r2-metric"><small>Last Certified Close</small><strong>{escape(_money(h["price"]))}</strong></div>'
        f'<div class="atlas-r2-metric"><small>ATLAS Fair Value</small><strong>{escape(_money(h["fair_value"]))}</strong></div>'
        f'<div class="atlas-r2-metric"><small>Fair Value Gap</small><strong>{escape(_pct(h["fair_value_gap_pct"], signed=True))}</strong></div>'
        f'<div class="atlas-r2-metric"><small>Opportunity</small><strong>{escape(customer_score(h["opportunity"]))}</strong></div>'
        f'<div class="atlas-r2-metric"><small>Evidence Confidence</small><strong>{escape(str(h.get("confidence_band") or "Unavailable"))} · {escape(confidence_score)}</strong></div>'
        f'</div></section>', unsafe_allow_html=True,
    )
    _marker(
        "stock-header", ticker,
        action=h["action"], fair_value=h["fair_value"],
        opportunity=h["opportunity"], confidence=h["confidence"],
        snapshot=page["identity"].get("evaluation_snapshot"),
    )
    if h["fair_value_gap_pct"] is not None:
        direction = "above" if h["fair_value_gap_pct"] >= 0 else "below"
        st.caption(f'ATLAS Fair Value is {abs(float(h["fair_value_gap_pct"])):.2f}% {direction} the last certified close. This is not a guaranteed return.')
    if customer_view.availability.get("certified_close") == Availability.CERTIFIED_DATED.value:
        st.warning("This Research uses a dated certified close. Review the displayed as-of date before acting.")
    if h["action"] not in {"BUY NOW", "BUILD A POSITION"}:
        st.caption("Not currently actionable — continue monitoring the certified evidence.")
    return page


def render_customer_research_v2(report: Mapping[str, Any], *, ask_cta: Callable[[Mapping[str, Any]], None]) -> bool:
    customer_view = build_customer_research_view(report)
    page = customer_view.as_mapping()
    ticker = str(page.get("ticker") or "UNKNOWN")
    first_screen_rendered = st.session_state.pop("_atlas_research_first_screen_rendered", "") == ticker
    if page.get("status") != "AVAILABLE":
        if not first_screen_rendered:
            render_customer_research_first_screen(report)
        return True
    if not first_screen_rendered:
        page = render_customer_research_first_screen(report)
    if not _render_production_authority_marker(page):
        st.error("Certified Research identity could not be reconciled for this ticker.")
        return False
    header = page["header"]
    ask_cta(report)

    summary = page["summary"]
    _marker("section", ticker, section_name="Decision")
    st.markdown("## ATLAS Investment Summary")
    st.write(summary["verdict"])
    st.markdown(
        '<style>.atlas-research-101{margin:.55rem 0 1rem;padding:.7rem .8rem;border:1px solid #243244;'
        'border-radius:12px;background:#0b1525;color:#cbd5e1}.atlas-research-101 summary{cursor:pointer;'
        'font-weight:750;color:#f8fafc}.atlas-research-101 li{margin:.35rem 0;line-height:1.45}'
        '@media(max-width:420px){.atlas-research-101{padding:.65rem;font-size:.9rem}.atlas-research-101 ul{padding-left:1.15rem}}</style>'
        '<div class="atlas-research-101" data-atlas-qa="research-101"><strong>Research 101 — what these numbers mean</strong>'
        '<div style="margin-top:.35rem">Start with the published Action and dated price, then compare Fair Value, evidence confidence, and the risks that could weaken the case.</div>'
        '<details style="margin-top:.45rem"><summary>What each number means</summary>'
        '<ul><li><strong>Action</strong> is the published ATLAS decision for this certified snapshot.</li>'
        '<li><strong>Last Certified Close</strong> is the price and date used by that decision; it is not a live quote.</li>'
        '<li><strong>Fair Value</strong> is an evidence-based estimate, not a guaranteed future price.</li>'
        '<li><strong>Opportunity</strong> compares relative attractiveness inside the certified ATLAS method.</li>'
        '<li><strong>Evidence Confidence</strong> measures evidence completeness and consistency, not the chance the stock will rise.</li>'
        '<li><strong>Annual and quarterly statements</strong> are reported filing history, not forecasts. Quarterly flow values may be cumulative year-to-date; missing values stay Unavailable and never mean zero.</li>'
        '</ul></details></div>',
        unsafe_allow_html=True,
    )
    if summary["why_rating"]:
        st.markdown("**Why the stock may be attractive**")
        _list(summary["why_rating"])
    if summary["risks"]:
        st.markdown("**Biggest verified risks**")
        _list(summary["risks"])
    _marker("since-signal", ticker, status=page["signal"]["status"])
    signal = page["signal"]
    if signal["status"] == "AVAILABLE":
        st.markdown("### Since ATLAS Flagged It")
        s = st.columns(5)
        s[0].metric("Action at issuance", signal["action"])
        s[1].metric("Reference price", _money(signal["reference_price"]))
        s[2].metric("Return since signal", _pct(signal["stock_return"], signed=True))
        s[3].metric("SPY same period", _pct(signal["spy_return"], signed=True))
        s[4].metric("Excess vs SPY", _pct(signal["excess_return"], signed=True))
        st.caption(f'Signal date: {signal.get("signal_date") or "Unavailable"}')

    _marker("section", ticker, section_name="Technical & Trade State")
    st.markdown("## Technical & Trade State")
    st.markdown("### Price history")
    _marker("chart-root", ticker, status=page["chart"]["status"])
    chart = page["chart"]
    ownership = chart.get("ownership") or {}
    owner_values = {
        str(ownership.get(name) or "").strip().upper()
        for name in (
            "requested_ticker", "source_report_ticker", "certified_authority_ticker",
            "chart_payload_ticker", "displayed_ticker",
        )
    }
    ownership_valid = owner_values == {ticker}
    _marker("chart-ownership", ticker, status="PASS" if ownership_valid else "FAIL", **ownership)
    if not ownership_valid:
        st.error("Research chart ownership could not be certified for this ticker.")
        return
    if chart["status"] != "AVAILABLE":
        st.info(chart["message"])
    else:
        rows = pd.DataFrame(chart["series"])
        date_key = next((key for key in ("date", "timestamp", "datetime") if key in rows), None)
        close_key = next((key for key in ("adjusted_close", "close", "price") if key in rows), None)
        if date_key and close_key:
            rows[date_key] = _dates(rows[date_key])
            stock_rows = rows.dropna(subset=[date_key, close_key]).set_index(date_key)[[close_key]].rename(columns={close_key: ticker})
            selected_range = st.selectbox("Price range", ("1M", "3M", "6M", "1Y"), index=2, key=f"research-price-range-{ticker}")
            stock_rows = _range_rows(stock_rows, selected_range)
            # The chart is rendered after the first-screen helper has returned,
            # so its local ``h`` binding is intentionally unavailable here.
            # Use the already-certified projection carried by this page.
            price_frame = stock_rows.copy()
            _dark_line_chart(price_frame, height=300, y_title="Price (USD/share)", key=f"research-price-chart-{ticker}")
            fair_value = header.get("fair_value")
            if fair_value is not None:
                st.caption(
                    f"ATLAS Fair Value: {_money(fair_value)} per share, compared with the last certified "
                    f"close of {_money(header.get('price'))}. It is shown separately so it does not compress "
                    "the historical price chart."
                )
            spy = chart.get("spy_comparison") or {}
            spy_rows = pd.DataFrame(spy.get("series") or [])
            if spy.get("status") == "AVAILABLE" and not spy_rows.empty:
                spy_date = next((key for key in ("date", "timestamp", "datetime") if key in spy_rows), None)
                spy_close = next((key for key in ("adjusted_close", "close", "price") if key in spy_rows), None)
                if spy_date and spy_close:
                    spy_rows[spy_date] = _dates(spy_rows[spy_date])
                    spy_rows = spy_rows.dropna(subset=[spy_date, spy_close]).set_index(spy_date)[[spy_close]].rename(columns={spy_close: "SPY"})
                    joined = stock_rows.join(spy_rows, how="inner").dropna()
                    if not joined.empty and float(joined.iloc[0][ticker]) and float(joined.iloc[0]["SPY"]):
                        normalized = joined[[ticker, "SPY"]].divide(joined.iloc[0][[ticker, "SPY"]]).multiply(100.0)
                        _marker("spy-comparison-chart", ticker, status="AVAILABLE", unit="NORMALIZED_INDEX_100")
                        st.markdown("### Stock performance compared with SPY")
                        _dark_line_chart(normalized, height=320, y_title="Normalized performance (start = 100)", key=f"research-spy-chart-{ticker}")
                        st.caption(_provenance_caption(spy.get("provenance") or {}))
                    else:
                        _marker("spy-comparison-chart", ticker, status="UNAVAILABLE")
                        st.info("SPY comparison is unavailable because comparable completed-session dates do not overlap.")
                else:
                    _marker("spy-comparison-chart", ticker, status="UNAVAILABLE")
                    st.info("SPY comparison is unavailable because dated benchmark evidence is incomplete.")
            else:
                _marker("spy-comparison-chart", ticker, status=spy.get("status") or "UNAVAILABLE")
                st.caption("SPY comparison unavailable for this evidence bundle.")
            st.caption(_provenance_caption(chart.get("provenance") or {}))
            if chart.get("corporate_action_status") == "UNADJUSTED_CLOSE_NO_RETURN_CLAIM":
                st.caption("Historical closes are shown without an adjusted-return claim because corporate-action adjustment provenance is unavailable.")

            technical = chart.get("technical_indicators") or {}
            indicator_keys = [key for key in technical.get("keys") or () if key in rows]
            if technical.get("status") == "AVAILABLE" and indicator_keys:
                price_indicators, oscillators = _technical_chart_frames(
                    rows, date_key=date_key, ticker=ticker, close_key=close_key,
                    indicator_keys=indicator_keys,
                )
                _marker("technical-indicators-chart", ticker, status="AVAILABLE", unit="TYPED_SEPARATE_AXES")
                st.markdown("### Technical context")
                if not price_indicators.empty and len(price_indicators.columns) > 1:
                    _dark_line_chart(
                        price_indicators, height=260, y_title="Price and moving averages (USD/share)",
                        key=f"research-technical-price-chart-{ticker}",
                    )
                if not oscillators.empty:
                    _dark_line_chart(
                        oscillators, height=220, y_title="RSI (0-100)",
                        key=f"research-technical-rsi-chart-{ticker}",
                    )
                st.caption(
                    "Technical indicators describe the retained historical series; they do not independently change the certified Action."
                )
            else:
                _marker("technical-indicators-chart", ticker, status="UNAVAILABLE")
                st.caption("Certified technical indicator history is unavailable for this evidence bundle; no series was inferred.")
        else:
            st.info("Price history is unavailable under the governed display contract.")

    _marker("summary", ticker, classification="CERTIFIED_ATLAS")
    weakest = summary.get("weakest_pillar") or {}
    if weakest:
        st.caption(
            f'Weakest certified pillar: {weakest["name"]} · {float(weakest["score"]):.1f} out of 100. '
            'A lower pillar score identifies an area where the certified investment case is less supportive.'
        )
    condition_labels = {
        "strengthen": "Strengthens the case — evidence to monitor",
        "weaken": "Weakens the case — evidence to monitor",
        "invalidate": "General monitoring conditions — not certified invalidation triggers",
    }
    for key, label in condition_labels.items():
        items = list((summary.get("watch_conditions") or {}).get(key) or ())
        if items:
            st.markdown(f"**{label}**")
            _list(items)

    pillars = page.get("six_pillars") or {}
    valid_count = len(pillars.get("items") or ())
    st.markdown(f"### Certified pillar coverage — {valid_count} of 6")
    pillar_identity = [
        {
            "pillar": item.get("pillar"), "score": item.get("certified_score"),
            "weight": item.get("weight"), "snapshot": item.get("snapshot_identity"),
        }
        for item in pillars.get("items") or ()
    ]
    pillar_digest = hashlib.sha256(
        json.dumps(pillar_identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    _marker(
        "six-pillar-profile", ticker, status=pillars.get("status") or "UNAVAILABLE",
        count=valid_count, digest=pillar_digest,
    )
    if pillars.get("status") in {"AVAILABLE", "PARTIAL"}:
        display_rows = _six_pillar_display_rows(pillars)
        frame = pd.DataFrame(display_rows).set_index("Pillar") if display_rows else pd.DataFrame()
        if frame.empty:
            st.info(pillars.get("message") or "Certified six-pillar evidence is unavailable.")
        else:
            chart_rows = []
            table_markers = []
            for row in display_rows:
                label = escape(str(row["Pillar"]))
                slug = str(row["Pillar"]).lower().replace(" ", "-")
                score = float(row["Certified score"])
                weight = row["Governed weight (%)"]
                weight_attr = "" if weight is None else f"{float(weight):.10g}"
                chart_rows.append(
                    f'<div class="atlas-pillar-row" data-atlas-qa="research-v2-pillar-chart-row" '
                    f'data-atlas-ticker="{escape(ticker)}" data-atlas-pillar="{escape(slug)}" '
                    f'data-atlas-score="{score:.10g}" data-atlas-weight="{weight_attr}">'
                    f'<div class="atlas-pillar-label"><span>{label}</span><strong>{score:.1f}</strong></div>'
                    f'<div class="atlas-pillar-track"><span style="width:{score:.6f}%"></span></div></div>'
                )
                table_markers.append(
                    f'<span data-atlas-qa="research-v2-pillar-table-row" data-atlas-ticker="{escape(ticker)}" '
                    f'data-atlas-pillar="{escape(slug)}" data-atlas-score="{score:.10g}" '
                    f'data-atlas-weight="{weight_attr}" aria-hidden="true" style="display:none"></span>'
                )
            st.markdown(
                '<style>.atlas-pillar-chart{padding:.8rem;border:1px solid #243244;border-radius:12px;'
                'background:#08111f}.atlas-pillar-row{margin:.55rem 0}.atlas-pillar-label{display:flex;'
                'justify-content:space-between;color:#cbd5e1;font-size:.82rem}.atlas-pillar-label strong{color:#f8fafc}'
                '.atlas-pillar-track{height:13px;margin-top:.25rem;border-radius:7px;background:#172337;overflow:hidden}'
                '.atlas-pillar-track span{display:block;height:100%;border-radius:7px;background:#2dd4bf}</style>'
                f'<div class="atlas-pillar-chart" data-atlas-ticker="{escape(ticker)}">'
                + "".join(chart_rows) + "</div>" + "".join(table_markers),
                unsafe_allow_html=True,
            )
            st.dataframe(
                frame[["Certified score"]].style.format("{:.1f}"),
                use_container_width=True,
                key=f"research-pillar-scores-{ticker}",
            )
            weight_rows = frame.dropna(subset=["Governed weight (%)"])[["Governed weight (%)"]]
            if pillars.get("weights_status") == "AVAILABLE":
                st.dataframe(
                    weight_rows.style.format("{:.1f}%"),
                    use_container_width=True,
                    key=f"research-pillar-weights-{ticker}",
                )
            else:
                st.caption("Governed pillar weights are unavailable in this snapshot; scores are shown without inferred weights.")
            if pillars.get("status") == "PARTIAL":
                st.caption(pillars.get("message") or "Some certified pillars are unavailable for customer display.")
    else:
        st.info(pillars.get("message") or "Certified six-pillar evidence is unavailable.")


    _marker("section", ticker, section_name="Fundamentals & Valuation")
    st.markdown("## Fundamentals & Valuation")
    st.markdown("### ATLAS vs Wall Street")
    _marker("analyst-module", ticker, status=page["wall_street"]["status"])
    wall = page["wall_street"]
    if wall["status"] == "UNAVAILABLE" or wall["status"] == "DISABLED":
        st.info("Wall Street context is unavailable for this evidence bundle.")
    else:
        a = st.columns(4)
        a[0].metric("Consensus", wall.get("consensus") or "Unavailable")
        a[1].metric("Buy", wall.get("buy_count") if wall.get("buy_count") is not None else "Unavailable")
        a[2].metric("Hold", wall.get("hold_count") if wall.get("hold_count") is not None else "Unavailable")
        a[3].metric("Sell", wall.get("sell_count") if wall.get("sell_count") is not None else "Unavailable")
        b = st.columns(5)
        b[0].metric("Last Certified Close", _money(header["price"]))
        b[1].metric("Wall St. Low", _money(wall.get("target_low")))
        b[2].metric("Wall St. Average", _money(wall.get("target_average")))
        b[3].metric("Wall St. High", _money(wall.get("target_high")))
        b[4].metric("ATLAS Fair Value", _money(header["fair_value"]))
        st.caption(f'{wall.get("analyst_count") or "Unavailable"} analysts · as of {_friendly_time(wall.get("as_of"))} · contextual and non-scoring')

    valuation = page.get("valuation_chart") or {}
    _marker("valuation-comparison-chart", ticker, status=valuation.get("status") or "UNAVAILABLE", unit=valuation.get("unit") or "")
    if valuation.get("status") == "AVAILABLE":
        valuation_frame = pd.DataFrame([{"Reference": key, "USD/share": value} for key, value in valuation["values"].items()])
        st.vega_lite_chart(valuation_frame, use_container_width=True, theme=None, key=f"research-valuation-chart-{ticker}", spec={
            "height": 240, "mark": {"type": "bar", "cornerRadiusEnd": 5},
            "encoding": {"x": {"field": "Reference", "type": "nominal", "axis": {"labelAngle": 0, "labelColor": "#cbd5e1", "title": None}}, "y": {"field": "USD/share", "type": "quantitative", "axis": {"title": "USD per share", "format": "$,.0f", "labelColor": "#94a3b8", "titleColor": "#cbd5e1", "gridColor": "#1e293b"}}, "color": {"field": "Reference", "type": "nominal", "scale": {"range": ["#60a5fa", "#2dd4bf", "#f59e0b"]}, "legend": None}, "tooltip": [{"field": "Reference"}, {"field": "USD/share", "format": "$,.2f"}]},
            "config": {"background": "#08111f", "view": {"stroke": "#243244"}},
        })
        st.caption(f'Valuation comparison as of {_friendly_time(valuation.get("as_of"))}. Wall Street context is non-scoring.')
    else:
        st.info(valuation.get("message") or "Comparable certified valuation points are unavailable.")

    _marker("risks", ticker)
    _marker("view-change-conditions", ticker)
    conditions_present = any((summary.get("watch_conditions") or {}).get(key) for key in ("strengthen", "weaken", "invalidate"))
    _marker("section", ticker, section_name="Risk & Evidence")
    if summary["risks"] or conditions_present:
        risk_items = list(summary["risks"])
        monitoring = list((summary.get("watch_conditions") or {}).get("invalidate") or ())
        risk_html = "".join(f"<li>{escape(str(item))}</li>" for item in risk_items)
        monitoring_html = "".join(f"<li>{escape(str(item))}</li>" for item in monitoring)
        limited = "" if risk_items else (
            '<p><strong>Limited evidence:</strong> No company-specific measured risk is retained for this snapshot. '
            'ATLAS does not substitute generic language.</p>'
        )
        st.markdown(
            f'<section class="atlas-risk-evidence" data-atlas-qa="research-v2-risk-content" '
            f'data-atlas-ticker="{escape(ticker)}"><h2>Risk &amp; Evidence</h2>'
            f'<h3>Company-specific measured risks</h3>{limited}<ul>{risk_html}</ul>'
            f'<h3>General monitoring conditions</h3><p>These conditions are monitoring prompts, not certified '
            f'quantitative invalidation triggers.</p><ul>{monitoring_html}</ul></section>',
            unsafe_allow_html=True,
        )

    _marker("what-changed", ticker, status=page["recent_changes"]["status"])
    if page["recent_changes"]["items"]:
        st.markdown("## What Changed Recently")
        for item in page["recent_changes"]["items"]:
            st.markdown(f'**{item.get("headline") or "Company update"}**  ')
            st.caption(f'{item.get("article_publisher") or "Source unavailable"} · {_friendly_time(item.get("article_timestamp"))}')

    st.markdown("## Fundamentals Snapshot")
    _marker("fundamentals", ticker, count=len(page["fundamentals"]))
    if page["fundamentals"]:
        for fact in page["fundamentals"][:6]:
            st.metric(fact["fact_name"], fact["display_value"])
    else:
        fundamentals = page.get("qa_fundamentals") or {}
        metrics = [
            ("Revenue growth", fundamentals.get("revenue_growth_ttm_yoy"), "%"),
            ("Operating margin", fundamentals.get("operating_margin_ttm"), "%"),
            ("TTM P/E", fundamentals.get("pe_ttm"), "×"),
            ("Market cap", fundamentals.get("market_capitalization"), "$"),
        ]
        visible = [(label, value, unit) for label, value, unit in metrics if value is not None]
        if visible:
            cols = st.columns(len(visible))
            for col, (label, value, unit) in zip(cols, visible):
                display = f'${float(value)/1_000_000_000:,.1f}B' if unit == "$" else f'{float(value):,.2f}{unit}'
                col.metric(label, display)
        else:
            st.info("Not enough evidence")

    financial_snapshot = page.get("financial_snapshot") or {}
    _marker("financial-snapshot", ticker, status=financial_snapshot.get("status") or "UNAVAILABLE",
            count=len(financial_snapshot.get("items") or ()))
    if financial_snapshot.get("status") == "AVAILABLE":
        st.markdown("### Certified financial evidence")
        items = list(financial_snapshot.get("items") or ())
        for start in range(0, len(items), 4):
            group = items[start:start + 4]
            cols = st.columns(len(group))
            for col, item in zip(cols, group):
                period = _friendly_time(item.get("period") or item.get("as_of"))
                analyst_note = f' · {item["analyst_count"]} analysts' if item.get("analyst_count") else ""
                col.metric(
                    str(item.get("label") or item.get("field") or "Financial evidence"),
                    _financial_value(item.get("value"), str(item.get("unit") or "")),
                    help=f'{period} · {item.get("provider") or "Certified source"}{analyst_note}',
                )
        with st.expander("Financial evidence periods and provenance", expanded=False):
            evidence_rows = [{
                "Metric": item.get("label"),
                "Value": _financial_value(item.get("value"), str(item.get("unit") or "")),
                "Fiscal period / as of": _friendly_time(item.get("period") or item.get("as_of")),
                "Source": item.get("provider") or "Certified source",
                "Evidence ID": item.get("evidence_id"),
            } for item in items]
            st.dataframe(pd.DataFrame(evidence_rows), hide_index=True, use_container_width=True)
        st.markdown("### What this means")
        st.caption(
            "Revenue shows how much the company sells. Operating margin shows how much operating profit "
            "it keeps from each $100 of revenue. Free cash flow is cash left after operating costs and major "
            "investments; it can support growth, debt repayment, or shareholder returns. Debt reduces financial "
            "flexibility when it is large relative to cash and earnings. A single period describes the current "
            "snapshot but does not prove that the business is improving or weakening."
        )
    else:
        st.info(financial_snapshot.get("message") or "Certified financial evidence is unavailable for this snapshot.")

    _render_financial_depth(page.get("financial_depth") or {}, ticker=ticker)
    if not _render_combined_statement_history(page.get("statement_history") or {}, ticker=ticker):
        _render_annual_financial_statements(page.get("annual_financial_statements") or {}, ticker=ticker)

    financial_trend = page.get("financial_trend") or {}
    _marker("financial-trend-chart", ticker, status=financial_trend.get("status") or "UNAVAILABLE")
    if financial_trend.get("status") == "AVAILABLE":
        periodicity = str(financial_trend.get("periodicity") or "UNAVAILABLE")
        heading = "Annual earnings and financial trends" if periodicity == "ANNUAL" else "Reported earnings and financial trends"
        st.markdown(f"### {heading}")
        if periodicity == "UNAVAILABLE":
            st.caption("Reporting frequency is unavailable; periods are shown exactly as retained and are not relabeled as annual or quarterly.")
        all_series = financial_trend["series"]
        units = financial_trend.get("units") or {}
        for unit, title in (("USD", "Reported financial value (USD)"), ("USD_PER_SHARE", "Reported value (USD/share)"), ("PERCENT", "Reported margin (%)")):
            selected = {name: values for name, values in all_series.items() if units.get(name) == unit}
            if selected:
                trend_frame = pd.DataFrame(selected, index=financial_trend["periods"])
                _dark_line_chart(trend_frame, height=280, y_title=title,
                                 key=f"research-financial-trend-{ticker}-{unit.lower()}")
        st.caption(_provenance_caption(financial_trend.get("provenance") or {}))

    _marker("section", ticker, section_name="Catalysts & Sentiment")
    _marker("catalysts", ticker, status=page["catalysts"]["status"])
    events = page["catalysts"].get("events") or []
    if events:
        st.markdown("## Catalysts & Sentiment")
        st.markdown("### Verified next events")
        for item in events:
            st.write(f'**Upcoming earnings** · {item.get("date") or "Date unavailable"}')

    st.markdown("## About the Company")
    _marker("about-company", ticker, status=page["about"]["status"])
    profile = page["about"].get("profile") or {}
    st.write(f'{page["about"].get("company") or page["company"]} · {page["about"].get("industry") or page["about"].get("sector") or "Industry unavailable"}')
    details = [str(value) for value in (profile.get("exchange"), profile.get("country"), profile.get("ipo_date")) if value]
    st.caption(" · ".join(details) if details else "Additional governed company details are unavailable for this snapshot.")

    _marker("evidence-methodology", ticker)
    with st.expander("Evidence & Methodology", expanded=False):
        evidence = page["evidence"]
        st.markdown(f'**Evaluation snapshot:** `{evidence.get("evaluation_snapshot_id") or "Unavailable"}`  ')
        st.markdown(f'**Candidate:** `{evidence.get("candidate_digest") or "Unavailable"}`  ')
        st.markdown(f'**Publication:** `{evidence.get("publication_digest") or "Unavailable"}`  ')
        st.markdown(f'**Methodology:** `{evidence["methodology_version"]}`')
        unavailable = []
        if page["recent_changes"]["status"] != "AVAILABLE": unavailable.append("Recent changes")
        if financial_trend.get("status") != "AVAILABLE": unavailable.append("Financial trends")
        if page["catalysts"]["status"] != "AVAILABLE": unavailable.append("Catalysts")
        if chart.get("technical_indicators", {}).get("status") != "AVAILABLE": unavailable.append("Technical history")
        if unavailable:
            st.markdown("**Unavailable in this certified snapshot:** " + ", ".join(unavailable))
        st.caption("Contextual evidence is non-scoring and cannot change Action, Fair Value, Opportunity, or Confidence.")
    st.caption("Ask ATLAS remains grounded to this ticker and certified evaluation snapshot.")
    return True


__all__ = ["render_customer_research_first_screen", "render_customer_research_v2"]
