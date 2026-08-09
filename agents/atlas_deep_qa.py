"""Atlas deep component, data-integrity, visual, and UX-comprehension QA.

Read-only with respect to Atlas product data. The runner writes only audit
artifacts and screenshots to its configured output directory.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
from difflib import SequenceMatcher
import json
import math
import re
import time
from pathlib import Path
from typing import Any, Iterable, Mapping

from playwright.async_api import Page, async_playwright


PAGES = (
    "Home", "Today's Opportunities", "Volume Intelligence", "Atlas Core Holdings",
    "Research Any Ticker", "Earnings Intelligence", "Full Ranked Scan",
    "Portfolio Intelligence", "Watchlist Intelligence", "Recovery", "ETFs",
    "Political Intelligence", "Ask AI", "Developer Center",
)
DEEP_TICKERS = ("NVDA", "CRM", "AVGO", "AR")
DESTRUCTIVE_RE = re.compile(
    r"delete|remove|trash|logout|sign out|billing|checkout|buy|sell|place order|"
    r"execute|upload|import|clear cache|clear all|disconnect", re.I,
)
ERROR_RE = re.compile(
    r"traceback|uncaught exception|streamlitapiexception|modulenotfounderror|"
    r"attributeerror|typeerror|keyerror|valueerror", re.I,
)
MISSING_TEXT = {"", "n/a", "na", "none", "null", "unavailable", "unknown", "—", "-", "not available"}

FIELD_GROUPS: dict[str, dict[str, tuple[str, ...]]] = {
    "financial": {
        "revenue_growth": ("Revenue Growth", "revenue_growth", "revenue_growth_pct"),
        "earnings_growth": ("Earnings Growth", "earnings_growth", "earningsGrowth"),
        "gross_margin": ("Gross Margin", "gross_margin", "grossMargins", "gross_profit_margin"),
        "operating_margin": ("Operating Margin", "operating_margin", "operatingMargins", "operating_profit_margin"),
        "net_margin": ("Net Margin", "net_margin", "profitMargins", "net_profit_margin"),
        "free_cash_flow": ("Free Cash Flow", "free_cash_flow", "freeCashflow"),
        "operating_cash_flow": ("Operating Cash Flow", "operating_cash_flow", "operatingCashflow"),
        "cash": ("Cash", "total_cash", "cash_and_equivalents"),
        "debt": ("Total Debt", "total_debt", "Debt"),
        "current_ratio": ("Current Ratio", "current_ratio"),
        "roic": ("ROIC", "roic", "return_on_invested_capital"),
        "roe": ("ROE", "roe", "returnOnEquity", "return_on_equity"),
        "forward_pe": ("Forward PE", "forward_pe", "forwardPE"),
    },
    "analyst": {
        "consensus_target": ("Analyst Target", "consensus_target", "target_mean_price", "targetMeanPrice", "analyst_target_mean"),
        "high_target": ("High Target", "target_high_price", "targetHighPrice", "analyst_target_high"),
        "low_target": ("Low Target", "target_low_price", "targetLowPrice", "analyst_target_low"),
        "analyst_count": ("Analyst Count", "analyst_count", "numberOfAnalystOpinions"),
        "implied_upside": ("Target Upside %", "analyst_upside_pct", "implied_upside"),
        "recommendation": ("Recommendation", "recommendation", "recommendationKey", "recommendation_key"),
    },
    "earnings": {
        "next_earnings_date": ("Next Earnings", "next_earnings_date", "earnings_date"),
        "latest_reported_date": ("Latest Reported", "latest_reported_date", "reported_date"),
        "reported_eps": ("Reported EPS", "reported_eps", "actual_eps", "latest_eps"),
        "eps_estimate": ("EPS Estimate", "eps_estimate", "estimated_eps"),
        "eps_surprise": ("EPS Surprise", "eps_surprise", "eps_surprise_pct"),
        "revenue_surprise": ("Revenue Surprise", "revenue_surprise", "revenue_surprise_pct"),
        "management_guidance": ("Management Guidance", "management_guidance", "Guidance"),
        "transcript_availability": ("Transcript Available", "transcript_available", "transcript_url"),
    },
    "research_trade": {
        "current_price": ("Current Price", "current_price", "price"),
        "atlas_fair_value": ("AI Fair Value", "atlas_fair_value", "fair_value", "Atlas Fair Value", "ai_base_target"),
        "wall_street_target": ("Wall Street Target", "analyst_target", "target_mean_price", "analyst_target_mean"),
        "expected_return": ("Expected Return", "expected_return_pct", "Target Upside %", "expected_upside_pct"),
        "entry": ("Entry", "entry_price", "entry_zone", "entry_range"),
        "stop": ("Stop", "stop_price", "stop_loss"),
        "target_1": ("Target 1", "target_1"),
        "target_2": ("Target 2", "target_2"),
        "confidence": ("Confidence", "confidence", "AI Confidence"),
        "opportunity": ("Opportunity", "opportunity", "Opportunity Score", "ai_score"),
        "evidence_coverage": ("Evidence Coverage", "evidence_coverage", "component_coverage_pct", "evidence_confidence"),
        "suggested_position": ("Suggested Position", "suggested_position", "position_size"),
        "atlas_rating": ("Atlas Rating", "Decision", "Recommendation", "recommendation_key"),
    },
}

NUMERIC_FIELDS = {
    name for fields in FIELD_GROUPS.values() for name in fields
    if name not in {"recommendation", "next_earnings_date", "latest_reported_date",
                    "management_guidance", "transcript_availability", "entry",
                    "suggested_position", "atlas_rating"}
}
UX_CLASSES = {
    "UNEXPLAINED_CONTROL", "AMBIGUOUS_METRIC", "AMBIGUOUS_LABEL",
    "MISSING_HELP_TEXT", "UNCLEAR_EMPTY_STATE", "UNCLEAR_ERROR_MESSAGE", "NO_NEXT_ACTION",
}


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    try:
        if math.isnan(value):
            return None
    except Exception:
        pass
    return value.item() if hasattr(value, "item") else value


def _first(row: Mapping[str, Any], aliases: Iterable[str]) -> tuple[Any, str]:
    raw = row.get("Raw") if isinstance(row.get("Raw"), Mapping) else {}
    for key in aliases:
        for source in (row, raw):
            if key in source:
                value = source[key]
                if not _missing(value):
                    return value, key
    return None, ""


def _missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in MISSING_TEXT
    try:
        return bool(math.isnan(float(value)))
    except Exception:
        return False


def _number(value: Any) -> float | None:
    if _missing(value) or isinstance(value, bool):
        return None
    try:
        return float(str(value).replace("$", "").replace(",", "").replace("%", "").strip())
    except Exception:
        return None


def _source(row: Mapping[str, Any], key: str) -> dict[str, Any]:
    provenance = row.get("provenance") if isinstance(row.get("provenance"), Mapping) else {}
    item = provenance.get(key) if isinstance(provenance.get(key), Mapping) else {}
    return {
        "provider": item.get("provider") or row.get("data_source") or row.get("source") or ",".join(row.get("_qa_sources") or []) or "UNKNOWN",
        "source_timestamp": item.get("timestamp") or row.get("source_timestamp") or row.get("scan_time") or "",
        "retrieved_at": item.get("retrieved_at") or row.get("research_refreshed_at") or row.get("generated_at") or row.get("scan_time") or "",
    }


def classify_fields(row: Mapping[str, Any], ticker: str) -> list[dict[str, Any]]:
    output = []
    context: dict[str, Any] = {}
    for group, fields in FIELD_GROUPS.items():
        for field, aliases in fields.items():
            value, key = _first(row, aliases)
            context[field] = value
            numeric = _number(value)
            if _missing(value):
                status = "MISSING"
            elif numeric == 0 and field in NUMERIC_FIELDS:
                status = "ZERO_VALID" if _zero_supported(row, field, key) else "SUSPICIOUS_ZERO"
            else:
                status = "AVAILABLE"
            source = _source(row, key or field)
            if status == "AVAILABLE" and source["retrieved_at"] and _looks_stale(source["retrieved_at"]):
                status = "STALE"
            output.append({
                "ticker": ticker, "group": group, "field": field,
                "displayed_value": _jsonable(value), "mapped_key": key,
                "status": status, **source,
            })

    # Cross-field false-zero evidence.
    reported = next(x for x in output if x["field"] == "reported_eps")
    latest = next(x for x in output if x["field"] == "latest_reported_date")
    if reported["displayed_value"] in (0, 0.0, "0", "0.0") and latest["status"] == "MISSING":
        reported["status"] = "SUSPICIOUS_ZERO"
        reported["reason"] = "Latest reported date is unavailable, so zero EPS lacks source evidence."
    return output


def _zero_supported(row: Mapping[str, Any], field: str, key: str) -> bool:
    provenance = row.get("provenance") if isinstance(row.get("provenance"), Mapping) else {}
    item = provenance.get(key) if isinstance(provenance.get(key), Mapping) else {}
    return bool(item.get("zero_valid") or item.get("source_value") in (0, 0.0, "0", "0.0"))


def _looks_stale(value: Any) -> bool:
    # Avoid inventing freshness when timestamps cannot be parsed. Explicit stale flags
    # are handled in source data; the browser report records unparseable provenance.
    return str(value).strip().lower() == "stale"


def consistency_findings(ticker: str, fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by = {item["field"]: item for item in fields}
    out = []

    def add(category: str, severity: str, description: str, values: Mapping[str, Any]):
        out.append({"ticker": ticker, "category": category, "severity": severity,
                    "description": description, "values": _jsonable(values)})

    if by["latest_reported_date"]["status"] == "MISSING" and by["reported_eps"]["status"] == "SUSPICIOUS_ZERO":
        add("POSSIBLE_FALSE_ZERO", "HIGH", "Reported EPS is zero while latest reported date is unavailable.",
            {k: by[k]["displayed_value"] for k in ("latest_reported_date", "reported_eps", "eps_surprise")})
    target = _number(by["consensus_target"]["displayed_value"])
    count = _number(by["analyst_count"]["displayed_value"])
    if target and count == 0:
        add("CONFLICTING_ANALYST_DATA", "HIGH", "Consensus target exists while analyst count is zero.",
            {"consensus_target": target, "analyst_count": count})
    price = _number(by["current_price"]["displayed_value"])
    fair = _number(by["atlas_fair_value"]["displayed_value"])
    expected = _number(by["expected_return"]["displayed_value"])
    if price and fair and expected is not None:
        calculated = (fair / price - 1) * 100
        if abs(calculated - expected) > 5:
            add("RETURN_MISMATCH", "HIGH", "Displayed expected return materially differs from fair-value/current-price return.",
                {"current_price": price, "fair_value": fair, "displayed": expected, "calculated": round(calculated, 2)})
    coverage = _number(by["evidence_coverage"]["displayed_value"])
    missing_major = sum(by[name]["status"] in {"MISSING", "UNKNOWN", "SUSPICIOUS_ZERO"}
                        for name in ("revenue_growth", "operating_margin", "free_cash_flow", "roic", "roe", "reported_eps", "analyst_count"))
    if coverage is not None and coverage >= 85 and missing_major >= 3:
        add("COVERAGE_CONFLICT", "HIGH", "Evidence coverage is high despite multiple missing major dimensions.",
            {"coverage": coverage, "missing_major_dimensions": missing_major})
    return out


def numeric_alias_findings(ticker: str, fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    numbers: dict[float, list[str]] = defaultdict(list)
    for item in fields:
        value = _number(item["displayed_value"])
        if value is not None and value != 0:
            numbers[round(value, 4)].append(item["field"])
    findings = []
    for value, labels in numbers.items():
        if len(labels) < 2:
            continue
        target_labels = {"consensus_target", "wall_street_target", "atlas_fair_value", "target_1", "target_2"}
        classification = "POSSIBLE_ALIASING" if len(set(labels) & target_labels) >= 2 else "LEGITIMATE_DUPLICATION"
        findings.append({"ticker": ticker, "value": value, "labels": labels, "classification": classification})
    return findings


def _summary(row: Mapping[str, Any]) -> str:
    for key in ("ai_summary", "summary", "Investment Thesis", "investment_thesis", "Guidance", "Primary Risk"):
        if not _missing(row.get(key)):
            return str(row[key])
    return ""


def duplicate_content(rows: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    pairs = []
    generic = Counter()
    sentences: dict[str, list[str]] = defaultdict(list)
    for ticker, row in rows.items():
        text = _summary(row)
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            normalized = re.sub(r"\b[A-Z]{1,5}\b|\d+(?:\.\d+)?%?|\$\d+(?:\.\d+)?", "<value>", sentence.lower())
            normalized = re.sub(r"\s+", " ", normalized).strip()
            if len(normalized.split()) >= 5:
                sentences[normalized].append(ticker)
        for phrase in ("some financial evidence remains incomplete", "atlas sees value, but prefers staged buying", "monitor for confirmation"):
            if phrase in text.lower():
                generic[phrase] += 1
    tickers = sorted(rows)
    for i, left in enumerate(tickers):
        for right in tickers[i + 1:]:
            a, b = _summary(rows[left]), _summary(rows[right])
            if not a or not b:
                continue
            score = round(SequenceMatcher(None, re.sub(left.lower(), "<ticker>", a.lower()), re.sub(right.lower(), "<ticker>", b.lower())).ratio() * 100, 1)
            if score >= 72:
                pairs.append({"left": left, "right": right, "similarity": score, "classification": "NEAR_IDENTICAL_EXPLANATION"})
    repeated = [{"sentence": text, "tickers": values, "occurrences": len(values)} for text, values in sentences.items() if len(set(values)) > 1]
    return {"pairs": pairs, "repeated_sentences": repeated,
            "generic_phrases": [{"phrase": k, "occurrences": v} for k, v in generic.items() if v > 1]}


def load_rows(root: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    rows: dict[str, dict[str, Any]] = {}
    sources = []
    candidates = (
        "market_full_scan.json", "top_ai_ideas.json", "total_market_universe.json",
        "watchlist_scan.json", "recovery_scan.json", "etf_scan.json",
    )
    for name in candidates:
        path = root / name
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        records = payload if isinstance(payload, list) else payload.get("records") or payload.get("data") or payload.get("rows") or []
        if not isinstance(records, list):
            continue
        sources.append(name)
        for raw in records:
            if not isinstance(raw, Mapping):
                continue
            ticker = str(raw.get("Ticker") or raw.get("ticker") or "").upper().strip()
            if not ticker:
                continue
            merged = rows.setdefault(ticker, {})
            for key, value in raw.items():
                if key not in merged or _missing(merged[key]):
                    merged[key] = value
            merged.setdefault("_qa_sources", []).append(name)
    return rows, sources


def representative_tickers(rows: Mapping[str, Mapping[str, Any]]) -> list[str]:
    selected = list(DEEP_TICKERS)
    # Saved datasets do not consistently persist the UI's final decision label.
    # Select category representatives from real source membership/evidence instead
    # of recomputing or guessing Atlas recommendation logic.
    selectors = (
        lambda row: "recovery_scan.json" in row.get("_qa_sources", []),
        lambda row: "watchlist_scan.json" in row.get("_qa_sources", []),
        lambda row: not _missing(row.get("next_earnings_date") or row.get("earnings_date")),
        lambda row: (_number(row.get("volume_ratio")) or 0) >= 1.5,
        lambda row: (_number(row.get("market_cap")) or 0) >= 200_000_000_000,
    )
    for matches in selectors:
        for ticker, row in rows.items():
            if ticker not in selected and matches(row):
                selected.append(ticker)
                break
    return [ticker for ticker in selected if ticker in rows]


def root_causes(completeness: list[dict[str, Any]], consistency: list[dict[str, Any]], duplicates: Mapping[str, Any], ux: list[dict[str, Any]], visuals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}

    def add(cause: str, severity: str, category: str, ticker: str = "", page: str = "", evidence: Any = None):
        key = (cause, category)
        item = grouped.setdefault(key, {"root_cause": cause, "severity": severity, "category": category,
            "description": cause.replace("_", " ").title(), "affected_pages": set(), "affected_tickers": set(),
            "occurrence_count": 0, "evidence": [], "likely_source_files": [],
            "recommended_repair": "Trace the shared mapping, instrumentation, or rendering path before changing product behavior.",
            "recommended_regression_test": f"Add a grouped regression test for {cause}."})
        item["occurrence_count"] += 1
        if ticker: item["affected_tickers"].add(ticker)
        if page: item["affected_pages"].add(page)
        if evidence is not None and len(item["evidence"]) < 8: item["evidence"].append(evidence)

    missing_by_field: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for field in completeness:
        if field["status"] in {"MISSING", "UNKNOWN", "SUSPICIOUS_ZERO"}:
            missing_by_field[field["field"]].append(field)
    by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for items in missing_by_field.values():
        for item in items: by_group[item["group"]].append(item)
    for group, items in by_group.items():
        cause = f"{group.upper()}_MAPPING_OR_PROVIDER_DATA_MISSING"
        severity = "HIGH" if any(item["field"] in {"roic", "roe", "reported_eps", "revenue_growth", "free_cash_flow"} for item in items) else "MEDIUM"
        for item in items:
            add(cause, severity, "Required Data", item["ticker"], "Research Any Ticker", {"field": item["field"], "status": item["status"]})
        grouped[(cause, "Required Data")]["likely_source_files"] = ["app.py", "engines/live_research_engine.py", "services/market_data.py"]
    for item in consistency:
        add(item["category"], item["severity"], "Data Consistency", item["ticker"], "Research Any Ticker", item)
    for item in duplicates.get("pairs", []):
        add("GENERIC_OR_SHARED_AI_TEMPLATE", "MEDIUM", "AI Content Quality", item["left"], "Research Any Ticker", item)
    for item in ux:
        add(item["classification"], item.get("severity", "MEDIUM"), "UX Comprehension", page=item.get("page", ""), evidence=item)
    for item in visuals:
        add(item["classification"], item.get("severity", "MEDIUM"), "Visual Quality", item.get("ticker", ""), item.get("page", ""), item)

    severity_rank = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
    output = []
    for item in grouped.values():
        item["affected_pages"] = sorted(item["affected_pages"])
        item["affected_tickers"] = sorted(item["affected_tickers"])
        output.append(item)
    return sorted(output, key=lambda x: (-severity_rank[x["severity"]], x["root_cause"]))


def domain_health(roots: list[dict[str, Any]], page_count: int, responsive_ok: bool) -> dict[str, Any]:
    domains = {
        "Runtime Health": 100, "Navigation Health": 100 if page_count == len(PAGES) else 60,
        "Research Health": 100, "AI Content Quality": 100, "Data Completeness": 100,
        "Data Consistency": 100, "Visual Quality": 100,
        "Responsive Quality": 100 if responsive_ok else 60, "Source Freshness": 100,
    }
    mapping = {"Required Data": "Data Completeness", "Data Consistency": "Data Consistency",
               "AI Content Quality": "AI Content Quality", "Visual Quality": "Visual Quality",
               "UX Comprehension": "Runtime Health"}
    weight = {"CRITICAL": 24, "HIGH": 14, "MEDIUM": 7, "LOW": 3}
    for item in roots:
        domain = mapping.get(item["category"], "Research Health")
        impact = min(1.6, 1 + max(0, len(item["affected_tickers"]) - 1) * .05)
        domains[domain] = max(0, round(domains[domain] - weight[item["severity"]] * impact))
    overall = round(sum(domains.values()) / len(domains))
    return {"domains": domains, "overall": overall,
            "calculation": "Unweighted mean of domain scores; each domain is reduced by unique root causes weighted by severity and bounded impact, not raw occurrences."}


class BrowserAudit:
    def __init__(self, page: Page, output: Path):
        self.page, self.output = page, output
        self.inventory: list[dict[str, Any]] = []
        self.screenshots: list[dict[str, Any]] = []
        self.visuals: list[dict[str, Any]] = []
        self.ux: list[dict[str, Any]] = []

    async def shot(self, name: str, page_name: str, component: str, state="default", ticker=""):
        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_")
        path = self.output / "screenshots" / f"{safe}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            await self.page.screenshot(path=str(path), full_page=True)
            status = "PASS"
        except Exception as exc:
            status = f"FAIL: {type(exc).__name__}"
        self.screenshots.append({"page": page_name, "component": component, "state": state,
                                 "ticker": ticker, "screenshot_path": str(path), "status": status})

    async def navigate(self, label: str) -> bool:
        for _attempt in range(2):
            candidates = (
                self.page.get_by_role("radio", name=label, exact=True),
                self.page.get_by_role("button", name=label, exact=True),
                self.page.get_by_role("link", name=label, exact=True),
                self.page.get_by_text(label, exact=True),
            )
            for candidate in candidates:
                try:
                    if await candidate.count():
                        await candidate.first.scroll_into_view_if_needed(timeout=3000)
                        await candidate.first.click(timeout=7000, force=True)
                        await asyncio.sleep(1.0)
                        return True
                except Exception:
                    continue
            await asyncio.sleep(.5)
        return False

    async def inspect_page(self, page_name: str):
        navigated = await self.navigate(page_name)
        body = await self.page.locator("body").inner_text()
        self.inventory.append({"page": page_name, "component": "primary page", "control_label": page_name,
                               "control_type": "navigation", "state_tested": "opened", "ticker": "",
                               "status": "PASS" if navigated and not ERROR_RE.search(body) else "FAIL",
                               "evidence": body[:500]})
        await self.shot(f"component_{page_name}_page", page_name, "page", "opened")
        controls = self.page.locator('button, [role="tab"], [role="combobox"], [role="checkbox"], [role="slider"], input, textarea')
        count = min(await controls.count(), 120)
        for index in range(count):
            node = controls.nth(index)
            try:
                if not await node.is_visible(): continue
                label = (await node.get_attribute("aria-label") or await node.inner_text() or await node.get_attribute("placeholder") or "").strip()
                role = await node.get_attribute("role") or await node.evaluate("e => e.tagName.toLowerCase()")
                destructive = bool(DESTRUCTIVE_RE.search(label))
                self.inventory.append({"page": page_name, "component": label or f"{role}[{index}]",
                    "control_label": label, "control_type": role, "state_tested": "excluded-destructive" if destructive else "inventoried",
                    "ticker": "", "status": "PASS", "evidence": {"index": index}})
                expanded = await node.get_attribute("aria-expanded")
                if not destructive and (role == "tab" or expanded == "false"):
                    try:
                        await node.click(timeout=2500); await asyncio.sleep(.2)
                        self.inventory[-1]["state_tested"] = "opened"
                        await self.shot(f"component_{page_name}_{label}_open", page_name, label, "open")
                        if page_name == "Developer Center" and role == "tab":
                            await self._audit_developer_tab(label)
                    except Exception as exc:
                        self.inventory[-1]["status"] = "WARN"
                        self.inventory[-1]["evidence"] = type(exc).__name__
                elif not destructive and role == "combobox":
                    try:
                        await node.click(timeout=2500); await asyncio.sleep(.15); await node.press("Escape")
                        self.inventory[-1]["state_tested"] = "opened-and-closed"
                    except Exception as exc:
                        self.inventory[-1]["status"] = "WARN"; self.inventory[-1]["evidence"] = type(exc).__name__
                elif not destructive and role == "checkbox":
                    try:
                        await node.click(timeout=2500); await asyncio.sleep(.15); await node.click(timeout=2500)
                        self.inventory[-1]["state_tested"] = "toggled-and-restored"
                    except Exception as exc:
                        self.inventory[-1]["status"] = "WARN"; self.inventory[-1]["evidence"] = type(exc).__name__
            except Exception:
                continue
        await self._visual_checks(page_name)
        await self._ux_checks(page_name)

    async def research_tickers(self, tickers: Iterable[str]):
        for ticker in tickers:
            if not await self.navigate("Research Any Ticker"):
                continue
            field = self.page.locator('input[placeholder*="Example:" i]').first
            try:
                await field.fill(ticker)
                await self.page.get_by_role("button", name="Research ticker", exact=True).click()
                marker = self.page.locator(
                    f'[data-atlas-qa="research-container"][data-atlas-status="complete"][data-atlas-ticker="{ticker}"]'
                )
                await marker.wait_for(state="attached", timeout=60000)
                body = await self.page.locator("body").inner_text()
                section_names = ("Financial Analysis", "Analyst Intelligence", "Earnings Intelligence", "Target Analysis", "Atlas AI Summary")
                for section in section_names:
                    status = "PASS" if section.lower() in body.lower() else "WARN"
                    self.inventory.append({"page": "Research Any Ticker", "component": section,
                        "control_label": section, "control_type": "report section", "state_tested": "rendered",
                        "ticker": ticker, "status": status, "evidence": f"matching complete marker for {ticker}"})
                    await self.shot(f"component_research_{ticker}_{section}", "Research Any Ticker", section, "rendered", ticker)
            except Exception as exc:
                self.inventory.append({"page": "Research Any Ticker", "component": "full research",
                    "control_label": "Research ticker", "control_type": "form", "state_tested": "submitted",
                    "ticker": ticker, "status": "FAIL", "evidence": f"{type(exc).__name__}: {exc}"})

    async def _visual_checks(self, page_name: str):
        defects = await self.page.evaluate("""() => {
          const out=[];
          for (const el of document.querySelectorAll('code, pre')) {
            const t=(el.innerText||'').trim();
            if (t.split(/\\s+/).length >= 5 && !/[{}();=<>]|python|bash|json/i.test(t)) out.push({kind:'PROSE_AS_CODE',text:t.slice(0,180)});
          }
          for (const el of document.querySelectorAll('body *')) {
            if (el.scrollWidth > el.clientWidth + 12 && el.clientWidth > 80) out.push({kind:'HORIZONTAL_OVERFLOW',text:(el.innerText||'').slice(0,100)});
          }
          return out.slice(0,20);
        }""")
        for defect in defects:
            self.visuals.append({"page": page_name, "classification": defect["kind"], "severity": "MEDIUM", "evidence": defect["text"]})

    async def _ux_checks(self, page_name: str):
        if page_name != "Developer Center":
            return
        body = (await self.page.locator("body").inner_text()).lower()
        if "internal quality-control center" not in body:
            self.ux.append({"page": page_name, "control": "Atlas Developer Center", "classification": "MISSING_HELP_TEXT",
                            "severity": "HIGH", "evidence": "Developer Center purpose introduction is not visible."})

    async def _audit_developer_tab(self, label: str):
        body = (await self.page.locator("body").inner_text()).lower()
        expected = {
            "Pipeline Audit": ("market, financial, analyst, earnings", "next action"),
            "Runtime QA v3": ("simulates real user activity",),
            "AI Content Integrity": ("repeated explanations", "next action"),
            "Controlled Fix Plan": ("root causes",),
            "Run Instructions": ("how atlas qa tests are executed",),
        }
        for phrase in expected.get(label, ()):
            if phrase not in body:
                classification = "NO_NEXT_ACTION" if phrase == "next action" else "MISSING_HELP_TEXT"
                self.ux.append({"page": "Developer Center", "control": label, "classification": classification,
                                "severity": "MEDIUM", "evidence": f"Expected visible explanation containing: {phrase}"})

    async def responsive(self):
        results = []
        for label, size in (("desktop", (1440, 1000)), ("tablet", (768, 1024)), ("mobile", (390, 844))):
            await self.page.set_viewport_size({"width": size[0], "height": size[1]})
            for page_name in ("Home", "Research Any Ticker", "Developer Center"):
                await self.navigate(page_name)
                geometry = await self.page.evaluate("() => ({viewport:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth})")
                ok = geometry["scroll"] <= geometry["viewport"] + 12
                results.append({"viewport": label, "page": page_name, "status": "PASS" if ok else "FAIL", **geometry})
                await self.shot(f"component_{label}_{page_name}", page_name, "responsive page", label)
        return results


async def browser_audit(url: str, output: Path) -> dict[str, Any]:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 1000})
        await page.goto(url, wait_until="domcontentloaded", timeout=90000)
        await asyncio.sleep(4)
        audit = BrowserAudit(page, output)
        for page_name in PAGES:
            await audit.inspect_page(page_name)
        await audit.research_tickers(DEEP_TICKERS)
        responsive = await audit.responsive()
        await browser.close()
    return {"inventory": audit.inventory, "screenshots": audit.screenshots,
            "visual_defects": audit.visuals, "ux_findings": audit.ux,
            "responsive": responsive}


def write_json(output: Path, name: str, payload: Any):
    (output / name).write_text(json.dumps(_jsonable(payload), indent=2, default=str), encoding="utf-8")


def markdown_report(report: Mapping[str, Any]) -> str:
    lines = ["# Atlas Deep QA", "", f"Status: **{report['status']}**", f"Overall health: **{report['health']['overall']}%**", "", "## Domain health", ""]
    for name, score in report["health"]["domains"].items(): lines.append(f"- {name}: {score}%")
    lines += ["", "## Coverage", "", f"- Pages visited: {report['summary']['pages_visited']}/{len(PAGES)}",
              f"- Components inventoried: {report['summary']['components_inventoried']}",
              f"- Screenshots: {report['summary']['screenshots']}",
              f"- Tickers audited: {', '.join(report['summary']['tickers'])}", "", "## Unique root causes", ""]
    for item in report["root_causes"]:
        lines.append(f"- **{item['severity']} — {item['root_cause']}**: {item['occurrence_count']} occurrence(s), {len(item['affected_tickers'])} ticker(s)")
    return "\n".join(lines) + "\n"


async def run(root: Path, output: Path, url: str) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    rows, source_files = load_rows(root)
    tickers = representative_tickers(rows)
    selected = {ticker: rows[ticker] for ticker in tickers}
    completeness = [field for ticker, row in selected.items() for field in classify_fields(row, ticker)]
    consistency = [finding for ticker in tickers for finding in consistency_findings(ticker, [x for x in completeness if x["ticker"] == ticker])]
    aliasing = [finding for ticker in tickers for finding in numeric_alias_findings(ticker, [x for x in completeness if x["ticker"] == ticker])]
    duplicates = duplicate_content(selected)
    browser = await browser_audit(url, output)
    roots = root_causes(completeness, consistency, duplicates, browser["ux_findings"], browser["visual_defects"])
    visited = len({x["page"] for x in browser["inventory"] if x["component"] == "primary page" and x["status"] == "PASS"})
    responsive_ok = all(x["status"] == "PASS" for x in browser["responsive"])
    health = domain_health(roots, visited, responsive_ok)
    unknowns = [{"component": x["field"], "ticker": x["ticker"], "expected_field": x["field"],
                 "expected_source_provider": x["provider"], "actual_state": x["status"],
                 "root_cause": "MAPPING_FAILURE" if not x["mapped_key"] else "MISSING_PROVIDER_DATA"}
                for x in completeness if x["status"] in {"UNKNOWN", "MISSING"}]
    report = {
        "version": "ATLAS-DEEP-QA-1.0", "status": "PASS" if visited == len(PAGES) and responsive_ok else "FAIL",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "summary": {"pages_visited": visited, "components_inventoried": len(browser["inventory"]),
                    "screenshots": len(browser["screenshots"]), "tickers": tickers,
                    "data_sources": source_files, "destructive_actions_executed": 0},
        "health": health, "root_causes": roots, "data_consistency": consistency,
        "duplicate_content": duplicates, "visual_defects": browser["visual_defects"],
        "ux_comprehension": browser["ux_findings"], "unknown_components": unknowns,
        "numeric_aliasing": aliasing, "responsive": browser["responsive"],
    }
    write_json(output, "atlas_deep_qa.json", report)
    (output / "atlas_deep_qa.md").write_text(markdown_report(report), encoding="utf-8")
    write_json(output, "atlas_component_inventory.json", browser["inventory"])
    write_json(output, "atlas_data_completeness.json", completeness)
    write_json(output, "atlas_data_consistency.json", {"semantic_findings": consistency, "numeric_aliasing": aliasing})
    write_json(output, "atlas_visual_defects.json", browser["visual_defects"])
    write_json(output, "atlas_duplicate_content.json", duplicates)
    write_json(output, "atlas_root_causes.json", roots)
    write_json(output, "atlas_screenshot_manifest.json", browser["screenshots"])
    write_json(output, "atlas_fix_plan.json", {"unique_root_causes": roots, "automatic_repairs_applied": False})
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--url", default="http://localhost:8501")
    parser.add_argument("--output", default="audit_results/deep_qa")
    args = parser.parse_args()
    report = asyncio.run(run(Path(args.root).resolve(), Path(args.output).resolve(), args.url))
    print(json.dumps({"status": report["status"], "summary": report["summary"], "health": report["health"]}, indent=2))


if __name__ == "__main__":
    main()
