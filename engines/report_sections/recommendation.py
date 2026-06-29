"""Recommendation, classification, and thesis bullets for Atlas reports."""
from __future__ import annotations
from typing import Any
from engines.report_sections.formatting import safe_num, safe_text

def build_recommendation(row: dict[str, Any]) -> str:
    raw = safe_text(
        row.get("Recommendation") or row.get("Verdict") or row.get("Final Verdict") or row.get("Action"),
        "Review",
    )
    upper = raw.upper()
    if "BUY NOW" in upper or upper == "BUY" or "STRONG BUY" in upper:
        return "✅ BUY NOW"
    if "GRADUAL" in upper or "WEAKNESS" in upper:
        return "🟡 BUY GRADUALLY"
    if "AVOID" in upper or "SELL" in upper:
        return "🔴 AVOID"
    if "HOLD" in upper or "WATCH" in upper:
        return "⚪ WATCH"
    return raw

def build_classification(row: dict[str, Any]) -> str:
    quality = safe_num(row.get("Quality") or row.get("Quality Score") or row.get("Financial Health") or row.get("Financial Health Score") or row.get("Finance Agent Score"))
    upside = safe_num(row.get("Upside") or row.get("Upside %") or row.get("Target Upside %") or row.get("Upside Potential %"))
    analyst = safe_num(row.get("Analyst Score") or row.get("Analyst Support Score") or row.get("Wall Street Score") or row.get("Research Confidence"))
    if quality >= 85:
        return "🏆 Elite Quality"
    if quality >= 75:
        return "✅ Quality Growth"
    if upside >= 100:
        return "🚀 High Upside"
    if upside >= 50:
        return "⚡ High Opportunity"
    if analyst >= 80:
        return "📈 Analyst Favorite"
    return "🔎 Research Candidate"

def build_why_we_like_it(row: dict[str, Any]) -> list[str]:
    bullets: list[str] = []
    quality = safe_num(row.get("Quality") or row.get("Financial Health") or row.get("Finance Agent Score"))
    upside = safe_num(row.get("Target Upside %") or row.get("Upside") or row.get("Upside %"))
    rr = safe_num(row.get("Risk/Reward") or row.get("Risk Reward"))
    analyst = safe_text(row.get("Analyst Support") or row.get("Analyst View"), "")
    if quality >= 75:
        bullets.append("Financial quality appears supportive of the investment case.")
    if upside >= 15:
        bullets.append("The current target framework suggests meaningful upside potential.")
    if rr >= 1.5:
        bullets.append("The risk/reward profile is favorable based on the latest scan.")
    if analyst and analyst != "N/A":
        bullets.append(f"Wall Street support appears constructive: {analyst}.")
    if safe_num(row.get("RSI")) > 45:
        bullets.append("Technical momentum does not appear severely weak.")
    if not bullets:
        bullets.append("The stock has enough supporting signals to justify further review.")
    return bullets[:5]

def build_key_risks(row: dict[str, Any]) -> list[str]:
    risks: list[str] = []
    quality = safe_num(row.get("Quality") or row.get("Financial Health") or row.get("Finance Agent Score"))
    upside = safe_num(row.get("Target Upside %") or row.get("Upside") or row.get("Upside %"))
    atr = safe_num(row.get("ATR %"))
    thesis_risk = safe_text(row.get("Primary Risk") or row.get("Risk") or row.get("What Could Go Wrong"), "")
    if thesis_risk and thesis_risk != "N/A":
        risks.append(thesis_risk)
    if quality and quality < 70:
        risks.append("Financial quality is still developing, so execution and position sizing matter.")
    if upside >= 75:
        risks.append("Very high upside estimates can carry higher uncertainty and wider volatility.")
    if atr >= 6:
        risks.append("Volatility is elevated, so position sizing should be conservative.")
    risks.append("Market sentiment, earnings results, and analyst revisions can change the thesis.")
    return risks[:5]
