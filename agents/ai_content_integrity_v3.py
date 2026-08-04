"""Cross-stock AI summary uniqueness and grounding checks."""

from __future__ import annotations
from collections import Counter
from difflib import SequenceMatcher
import re
from typing import Any, Iterable, Mapping

from agents.qa_v3_models import QAIssue


GENERIC_PHRASES = (
    "strong fundamentals",
    "positive technical confirmation",
    "attractive valuation",
    "long term growth",
    "ranks highly relative to the reviewed universe",
    "institutional support",
    "monitor for confirmation",
)

NUMBER_RE = re.compile(r"(?<![A-Za-z])[-+]?\$?\d+(?:\.\d+)?%?")
TOKEN_RE = re.compile(r"[A-Za-z0-9%$.-]+")


def normalize_summary(text: str, ticker: str = "", company: str = "") -> str:
    value = str(text or "").lower()
    for item in (ticker, company):
        if item:
            value = value.replace(str(item).lower(), " company ")
    value = NUMBER_RE.sub(" number ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def summary_similarity(
    left: str,
    right: str,
    *,
    left_ticker: str = "",
    right_ticker: str = "",
    left_company: str = "",
    right_company: str = "",
) -> float:
    a = normalize_summary(left, left_ticker, left_company)
    b = normalize_summary(right, right_ticker, right_company)
    if not a or not b:
        return 0.0
    return round(SequenceMatcher(None, a, b).ratio() * 100.0, 1)


def specificity_score(
    summary: str,
    row: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    row = row or {}
    text = str(summary or "")
    lower = text.lower()
    tokens = TOKEN_RE.findall(text)

    numeric_facts = len(NUMBER_RE.findall(text))
    ticker = str(row.get("ticker") or row.get("Ticker") or "")
    company = str(row.get("company") or row.get("Company") or "")
    sector = str(row.get("sector") or row.get("Sector") or "")

    entity_hits = sum(
        bool(item and item.lower() in lower)
        for item in (ticker, company, sector)
    )
    generic_hits = sum(phrase in lower for phrase in GENERIC_PHRASES)

    evidence_terms = (
        "revenue", "eps", "margin", "cash flow", "debt", "valuation",
        "target", "upside", "volume", "rvol", "momentum", "earnings",
        "guidance", "analyst", "risk", "catalyst", "institutional",
    )
    evidence_hits = sum(term in lower for term in evidence_terms)

    score = 35
    score += min(20, numeric_facts * 7)
    score += min(15, entity_hits * 7)
    score += min(25, evidence_hits * 4)
    score -= min(30, generic_hits * 8)
    if len(tokens) < 18:
        score -= 15
    score = max(0, min(100, score))

    return {
        "score": score,
        "numeric_facts": numeric_facts,
        "entity_hits": entity_hits,
        "evidence_hits": evidence_hits,
        "generic_hits": generic_hits,
        "word_count": len(tokens),
    }


def audit_summary_collection(
    records: Iterable[Mapping[str, Any]],
    *,
    similarity_threshold: float = 82.0,
) -> dict[str, Any]:
    items = []
    issues: list[QAIssue] = []

    for record in records:
        summary = str(
            record.get("ai_summary")
            or record.get("summary")
            or record.get("investment_thesis")
            or record.get("atlas_summary")
            or ""
        ).strip()
        if not summary:
            continue
        ticker = str(record.get("ticker") or record.get("Ticker") or "UNKNOWN")
        company = str(record.get("company") or record.get("Company") or ticker)
        details = specificity_score(summary, record)
        items.append({
            "ticker": ticker,
            "company": company,
            "summary": summary,
            "specificity": details,
        })
        if details["score"] < 60:
            issues.append(QAIssue(
                severity="HIGH" if details["score"] < 45 else "MEDIUM",
                category="AI Content Integrity",
                page="Cross-Stock AI Review",
                ticker=ticker,
                element="AI summary specificity",
                expected=(
                    "A stock-specific summary with a catalyst, risk, valuation or "
                    "technical context, and at least one supporting fact."
                ),
                actual=f"Specificity score {details['score']}/100.",
                recommendation=(
                    "Regenerate from normalized component evidence rather than a "
                    "generic fallback template."
                ),
                likely_files=[
                    "engines/atlas_intelligence_engine.py",
                    "engines/atlas_research_builder_v2.py",
                    "engines/ask_atlas_engine.py",
                ],
                evidence=details,
                regression_test=(
                    "Require stock summaries to exceed the minimum specificity score."
                ),
            ))

    pairs = []
    for index, left in enumerate(items):
        for right in items[index + 1:]:
            similarity = summary_similarity(
                left["summary"],
                right["summary"],
                left_ticker=left["ticker"],
                right_ticker=right["ticker"],
                left_company=left["company"],
                right_company=right["company"],
            )
            if similarity >= similarity_threshold:
                pair = {
                    "left": left["ticker"],
                    "right": right["ticker"],
                    "similarity_pct": similarity,
                }
                pairs.append(pair)
                issues.append(QAIssue(
                    severity="HIGH" if similarity >= 90 else "MEDIUM",
                    category="Duplicate AI Summary",
                    page="Cross-Stock AI Review",
                    element=f"{left['ticker']} / {right['ticker']}",
                    expected=(
                        "Different stocks receive materially different explanations "
                        "grounded in their own catalysts, risks, valuation, and data."
                    ),
                    actual=f"Normalized summary similarity is {similarity:.1f}%.",
                    recommendation=(
                        "Replace shared template output with component-grounded synthesis "
                        "and retain stock-specific numeric facts."
                    ),
                    likely_files=[
                        "engines/atlas_intelligence_engine.py",
                        "engines/atlas_research_builder_v2.py",
                    ],
                    evidence=pair,
                    regression_test=(
                        "Compare every summary in a scan and fail above the configured "
                        "similarity threshold."
                    ),
                ))

    return {
        "records_reviewed": len(items),
        "duplicate_pairs": pairs,
        "summary_scores": items,
        "issues": [issue.to_dict() for issue in issues],
    }
