"""Ticker-aware cross-stock AI summary quality checks.

This module separates product defects from QA extraction defects, rejects
navigation/page labels as tickers, de-duplicates repeated cards, and compares
the underlying evidence in summaries rather than relying on raw prose shape.
"""

from __future__ import annotations

from collections import Counter
from difflib import SequenceMatcher
import math
import re
from typing import Any, Iterable, Mapping, Sequence

from agents.qa_v3_models import QAIssue


GENERIC_PHRASES = (
    "strong fundamentals",
    "positive technical confirmation",
    "attractive valuation",
    "long term growth",
    "ranks highly relative to the reviewed universe",
    "institutional support",
    "monitor for confirmation",
    "some financial evidence remains incomplete",
    "atlas sees value but prefers staged buying",
)

INVALID_TICKERS = {
    "AI", "NO", "YES", "BUY", "NOW", "ETF", "EPS", "RSI", "PE", "PEG",
    "HOME", "TODAY", "ASK", "ATLAS", "FULL", "TOP", "CORE", "WATCHLIST",
    "RECOVERY", "POLITICAL", "DEVELOPER", "CENTER", "EARNINGS", "VOLUME",
    "RESEARCH", "PORTFOLIO", "INTELLIGENCE", "SUMMARY", "MONITOR",
    "ACCUMULATE", "AVOID", "PASS", "FAIL", "APPLICATION",
}

PAGE_LABELS = {
    "Home",
    "Today's Opportunities",
    "Top AI Ideas",
    "Volume Intelligence",
    "Atlas Core Holdings",
    "Research Any Ticker",
    "Earnings Intelligence",
    "Full Ranked Scan",
    "Portfolio Intelligence",
    "Watchlist Intelligence",
    "Recovery",
    "ETFs",
    "Political Intelligence",
    "Ask AI",
    "Developer Center",
}

NUMBER_RE = re.compile(r"(?<![A-Za-z])[-+]?\$?\d+(?:\.\d+)?%?(?:×|x)?")
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9&'.-]*")
TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.-]{0,5}$")

EVIDENCE_GROUPS = {
    "financial": (
        "revenue", "eps", "margin", "cash flow", "free cash flow", "debt",
        "roic", "roe", "growth", "profitability",
    ),
    "valuation": (
        "valuation", "fair value", "target", "upside", "expected return",
        "p/e", "pe ratio", "peg", "multiple",
    ),
    "technical": (
        "volume", "relative volume", "rvol", "momentum", "rsi", "sma",
        "moving average", "support", "resistance", "technical",
    ),
    "earnings": (
        "earnings", "guidance", "surprise", "beat", "miss", "management",
    ),
    "risk": (
        "risk", "caution", "downside", "uncertainty", "debt", "competition",
        "execution", "regulatory", "volatility",
    ),
    "catalyst": (
        "catalyst", "launch", "demand", "contract", "backlog", "product",
        "approval", "expansion", "upgrade", "news",
    ),
    "analyst": (
        "analyst", "wall street", "price target", "rating", "institutional",
    ),
}


def is_valid_ticker(value: Any) -> bool:
    ticker = str(value or "").strip().upper()
    return bool(
        TICKER_RE.fullmatch(ticker)
        and ticker not in INVALID_TICKERS
        and ticker.title() not in PAGE_LABELS
    )


def normalize_summary(text: str, ticker: str = "", company: str = "") -> str:
    value = str(text or "").lower()
    for item in (ticker, company):
        clean = str(item or "").strip().lower()
        if clean:
            value = re.sub(rf"\b{re.escape(clean)}\b", " company ", value)
    value = NUMBER_RE.sub(" number ", value)
    value = re.sub(r"[^a-z0-9$%×.' -]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _content_tokens(text: str, ticker: str = "", company: str = "") -> set[str]:
    normalized = normalize_summary(text, ticker, company)
    stop = {
        "the", "a", "an", "and", "or", "but", "is", "are", "was", "were",
        "to", "of", "for", "with", "in", "on", "at", "by", "from", "this",
        "that", "company", "number", "atlas", "currently", "primary",
        "support", "caution", "scores", "score", "normal",
    }
    return {
        token.lower()
        for token in TOKEN_RE.findall(normalized)
        if len(token) > 2 and token.lower() not in stop
    }


def _evidence_profile(text: str) -> dict[str, Any]:
    lower = str(text or "").lower()
    groups = {
        name: sorted(term for term in terms if term in lower)
        for name, terms in EVIDENCE_GROUPS.items()
    }
    return {
        "groups": groups,
        "group_names": sorted(name for name, terms in groups.items() if terms),
        "numeric_facts": NUMBER_RE.findall(text),
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def summary_similarity(
    left: str,
    right: str,
    *,
    left_ticker: str = "",
    right_ticker: str = "",
    left_company: str = "",
    right_company: str = "",
) -> float:
    """Return evidence-aware similarity from 0 to 100.

    Structural prose is down-weighted. Shared evidence language and meaningful
    content-token overlap are weighted more heavily.
    """
    a = normalize_summary(left, left_ticker, left_company)
    b = normalize_summary(right, right_ticker, right_company)
    if not a or not b:
        return 0.0

    sequence = SequenceMatcher(None, a, b).ratio()
    token_overlap = _jaccard(
        _content_tokens(left, left_ticker, left_company),
        _content_tokens(right, right_ticker, right_company),
    )

    left_profile = _evidence_profile(left)
    right_profile = _evidence_profile(right)
    left_groups = set(left_profile["group_names"])
    right_groups = set(right_profile["group_names"])
    evidence_overlap = _jaccard(left_groups, right_groups)

    # A professional common structure alone should not trigger duplication.
    score = (sequence * 0.20) + (token_overlap * 0.55) + (evidence_overlap * 0.25)
    return round(score * 100.0, 1)


def specificity_score(
    summary: str,
    row: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    row = row or {}
    text = str(summary or "").strip()
    lower = text.lower()
    tokens = TOKEN_RE.findall(text)

    numeric_facts = len(NUMBER_RE.findall(text))
    ticker = str(row.get("ticker") or row.get("Ticker") or "").strip()
    company = str(row.get("company") or row.get("Company") or "").strip()
    sector = str(row.get("sector") or row.get("Sector") or "").strip()

    ticker_hit = bool(is_valid_ticker(ticker) and re.search(rf"\b{re.escape(ticker)}\b", text))
    company_hit = bool(company and company.lower() in lower)
    sector_hit = bool(sector and sector.lower() in lower)
    entity_hits = sum((ticker_hit, company_hit, sector_hit))

    generic_hits = sum(phrase in lower for phrase in GENERIC_PHRASES)
    profile = _evidence_profile(text)
    evidence_group_count = len(profile["group_names"])

    score = 18
    score += min(24, numeric_facts * 6)
    score += min(18, entity_hits * 8)
    score += min(36, evidence_group_count * 6)
    score -= min(30, generic_hits * 8)

    if len(tokens) >= 28:
        score += 8
    elif len(tokens) < 16:
        score -= 18

    if not ticker_hit and not company_hit:
        score -= 20

    score = max(0, min(100, score))
    return {
        "score": score,
        "numeric_facts": numeric_facts,
        "entity_hits": entity_hits,
        "ticker_hit": ticker_hit,
        "company_hit": company_hit,
        "sector_hit": sector_hit,
        "evidence_hits": evidence_group_count,
        "evidence_groups": profile["group_names"],
        "generic_hits": generic_hits,
        "word_count": len(tokens),
    }


def _record_key(ticker: str, summary: str) -> tuple[str, str]:
    return ticker.upper(), normalize_summary(summary, ticker)[:500]


def _issue_dict(issue: QAIssue, *, classification: str, occurrence_count: int = 1) -> dict[str, Any]:
    value = issue.to_dict()
    value["classification"] = classification
    value["occurrence_count"] = occurrence_count
    return value


def audit_summary_collection(
    records: Iterable[Mapping[str, Any]],
    *,
    similarity_threshold: float = 82.0,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    seen_records: set[tuple[str, str]] = set()

    for record in records:
        summary = str(
            record.get("ai_summary")
            or record.get("summary")
            or record.get("investment_thesis")
            or record.get("atlas_summary")
            or ""
        ).strip()
        ticker = str(record.get("ticker") or record.get("Ticker") or "").strip().upper()
        company = str(record.get("company") or record.get("Company") or ticker).strip()
        page = str(record.get("page") or "Cross-Stock AI Review")

        reasons = []
        if not summary:
            reasons.append("missing_summary")
        if not is_valid_ticker(ticker):
            reasons.append("invalid_ticker")
        if ticker and ticker.title() in PAGE_LABELS:
            reasons.append("page_label_as_ticker")
        if len(TOKEN_RE.findall(summary)) < 12:
            reasons.append("summary_too_short")

        if reasons:
            rejected.append({
                "ticker": ticker,
                "company": company,
                "page": page,
                "reasons": reasons,
                "classification": "QA_EXTRACTION_ISSUE",
            })
            continue

        key = _record_key(ticker, summary)
        if key in seen_records:
            continue
        seen_records.add(key)

        details = specificity_score(summary, record)
        item = {
            "ticker": ticker,
            "company": company,
            "summary": summary,
            "page": page,
            "specificity": details,
        }
        items.append(item)

        if details["score"] < 60:
            issue = QAIssue(
                severity="HIGH" if details["score"] < 45 else "MEDIUM",
                category="AI Content Integrity",
                page=page,
                ticker=ticker,
                element="AI summary specificity",
                expected=(
                    "A stock-specific summary with company identity, catalyst or risk, "
                    "valuation or technical context, and supporting numeric evidence."
                ),
                actual=f"Specificity score {details['score']}/100.",
                recommendation=(
                    "Generate the narrative from normalized stock-specific evidence "
                    "rather than a shared fallback sentence."
                ),
                likely_files=[
                    "engines/atlas_intelligence_engine.py",
                    "engines/atlas_research_builder_v2.py",
                    "engines/ask_atlas_engine.py",
                ],
                evidence=details,
                regression_test="Require valid stock summaries to exceed the minimum specificity score.",
            )
            issues.append(_issue_dict(issue, classification="PRODUCT_ISSUE"))

    pairs: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str, str, str]] = set()
    for index, left in enumerate(items):
        for right in items[index + 1:]:
            if left["ticker"] == right["ticker"]:
                continue

            similarity = summary_similarity(
                left["summary"],
                right["summary"],
                left_ticker=left["ticker"],
                right_ticker=right["ticker"],
                left_company=left["company"],
                right_company=right["company"],
            )
            if similarity < similarity_threshold:
                continue

            pair_key = (
                min(left["ticker"], right["ticker"]),
                max(left["ticker"], right["ticker"]),
                normalize_summary(left["summary"], left["ticker"], left["company"])[:240],
                normalize_summary(right["summary"], right["ticker"], right["company"])[:240],
            )
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            pair = {
                "left": left["ticker"],
                "right": right["ticker"],
                "similarity_pct": similarity,
                "left_page": left["page"],
                "right_page": right["page"],
            }
            pairs.append(pair)
            issue = QAIssue(
                severity="HIGH" if similarity >= 90 else "MEDIUM",
                category="Duplicate AI Summary",
                page="Cross-Stock AI Review",
                element=f"{left['ticker']} / {right['ticker']}",
                expected=(
                    "Different stocks receive materially different explanations "
                    "grounded in their own catalysts, risks, valuation, and data."
                ),
                actual=f"Evidence-aware summary similarity is {similarity:.1f}%.",
                recommendation=(
                    "Replace reused reasoning with company-specific catalysts, risks, "
                    "valuation evidence, and numeric facts."
                ),
                likely_files=[
                    "engines/atlas_intelligence_engine.py",
                    "engines/atlas_research_builder_v2.py",
                ],
                evidence=pair,
                regression_test="Compare every valid stock summary and fail above the threshold.",
            )
            issues.append(_issue_dict(issue, classification="PRODUCT_ISSUE"))

    return {
        "records_received": len(list(records)) if isinstance(records, Sequence) else None,
        "records_reviewed": len(items),
        "records_rejected": len(rejected),
        "rejected_records": rejected,
        "duplicate_pairs": pairs,
        "summary_scores": items,
        "issues": issues,
    }
