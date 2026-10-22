"""Reference-aligned presentation of the same admitted customer evidence."""
from html import escape
import math
from typing import Any, Mapping
from datetime import datetime
import re
from zoneinfo import ZoneInfo

def _readable(value):
    def convert(match):
        try:
            stamp=datetime.fromisoformat(match.group().replace("Z","+00:00"))
            return stamp.astimezone(ZoneInfo("America/New_York")).strftime("%b %d, %Y, %I:%M %p %Z")
        except ValueError:
            return "Date unavailable"
    return re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})",convert,str(value))

def _as_of_date(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z","+00:00")).strftime("%b %d, %Y")
    except ValueError:
        return "Date unavailable"


RESEARCH_REFERENCE_CSS = r'''<style>
.atlas-research-digest{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(0,1fr);gap:1rem;margin:.7rem 0}.atlas-research-digest article{border:1px solid #204159;border-radius:14px;background:linear-gradient(135deg,#102638,#0a1828);padding:1.1rem;min-width:0}.atlas-research-digest small{color:#6fceff;font-size:.68rem;letter-spacing:.08em;font-weight:750}.atlas-research-digest h3{color:#edf5ff;font-size:1.25rem!important;margin:.5rem 0!important}.atlas-research-digest p{color:#cad9e9;font-size:.92rem;line-height:1.65}.atlas-research-digest .atlas-digest-update{background:#0a1828}.atlas-research-digest footer{font-size:.7rem;color:#91a9bf;line-height:1.6}.atlas-research-digest a{color:#79ceff}.atlas-research-analysis{display:grid;grid-template-columns:1fr 1fr;gap:.75rem}.atlas-research-analysis article{border:1px solid #253c50;border-radius:12px;padding:1rem;background:#0c1b2a}.atlas-research-analysis h4{font-size:1rem!important;color:#8ed6ff;margin:0 0 .5rem!important}.atlas-research-analysis p{font-size:.9rem;line-height:1.65;color:#d1dfed}
@media(max-width:800px){.atlas-research-digest,.atlas-research-analysis{grid-template-columns:1fr}.atlas-research-digest article{padding:.85rem}}
.atlas-r2-head .atlas-r2-metrics{grid-template-columns:repeat(5,minmax(0,1fr));margin:.8rem 0 0;gap:.5rem}.atlas-r2-head .atlas-r2-metrics .atlas-r2-metric{padding:.75rem}.atlas-r2-head .atlas-r2-metrics strong{font-size:1.25rem;font-variant-numeric:tabular-nums}.atlas-r2-head .atlas-r2-metric p{font-size:.7rem;line-height:1.45;color:#9eb4c9;margin:.45rem 0 0}.atlas-research-section-nav{display:flex;gap:.45rem;overflow-x:auto;padding:.4rem 0 .7rem;margin:.3rem 0;scrollbar-width:thin}.atlas-research-section-nav a{display:inline-flex;align-items:center;min-height:44px;box-sizing:border-box;white-space:nowrap;padding:.55rem .8rem;border:1px solid #21425a;border-radius:8px;background:#0a1e31;color:#bbddf6;text-decoration:none;font-size:.8rem}.atlas-research-section-nav a:hover,.atlas-research-section-nav a:focus-visible{background:#123957;color:white;outline:2px solid #56aef3}
[id^="atlas-research-"]{scroll-margin-top:1rem}.atlas-research-section-nav{overscroll-behavior-x:contain}.atlas-research-section-nav:focus-within{outline-offset:3px}
@media(max-width:1000px){.atlas-r2-head .atlas-r2-metrics{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:700px){body:has([data-atlas-qa="research-v2-root"]) [data-testid="stMainBlockContainer"]{padding-left:.75rem!important;padding-right:.75rem!important}.atlas-r2-head .atlas-r2-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.atlas-r2-head .atlas-r2-metrics strong{font-size:1.2rem}.atlas-r2-head .atlas-r2-metrics .atlas-r2-metric:last-child{grid-column:1/-1}}
.atlas-research-insight-rail .atlas-research-digest{grid-template-columns:1fr;margin:0}.atlas-research-insight-rail .atlas-research-digest article{padding:1rem}.atlas-research-insight-rail .atlas-research-digest h3{font-size:1.08rem!important}.atlas-research-insight-rail .atlas-research-digest p{font-size:.88rem;line-height:1.55}
.atlas-research-fundamentals{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.75rem;margin:.75rem 0 1.2rem}.atlas-research-fundamentals article{min-width:0;border:1px solid #21425a;border-radius:12px;background:linear-gradient(135deg,#102638,#0a1828);padding:1rem}.atlas-research-fundamentals small{display:block;color:#9ab3ca;font-size:.78rem;margin-bottom:.5rem}.atlas-research-fundamentals strong{display:block;color:#edf5ff;font-size:1.4rem;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
body:has([data-atlas-qa="research-v2-root"]) [data-testid="stHorizontalBlock"]:has([data-atlas-qa="research-chart-workspace"]){align-items:flex-start}
@media(max-width:1100px){body:has([data-atlas-qa="research-v2-root"]) [data-testid="stHorizontalBlock"]:has([data-atlas-qa="research-chart-workspace"]){flex-direction:column}body:has([data-atlas-qa="research-v2-root"]) [data-testid="stHorizontalBlock"]:has([data-atlas-qa="research-chart-workspace"])>[data-testid="stColumn"]{width:100%!important;flex:1 1 100%!important}.atlas-research-insight-rail .atlas-research-digest{grid-template-columns:1.35fr 1fr}}
@media(max-width:700px){.atlas-research-insight-rail .atlas-research-digest{grid-template-columns:1fr}.atlas-research-fundamentals{grid-template-columns:repeat(2,minmax(0,1fr));gap:.5rem}.atlas-research-fundamentals article{padding:.8rem}.atlas-research-fundamentals strong{font-size:1.15rem}}
</style>'''


RESEARCH_SECTION_LINKS = (
    ("overview", "Overview"), ("technicals", "Chart & technicals"),
    ("financials", "Valuation & analysts"), ("risks", "Risks & evidence"),
    ("news", "Company news"), ("statements", "Financial statements"),
    ("earnings", "Earnings history"), ("developments", "Events"), ("company", "Company"),
)


def research_section_navigation_html():
    """Navigate rendered evidence sections, including their honest pending states."""
    links = ''.join('<a href="#atlas-research-' + key + '">' + escape(label) + '</a>'
                    for key, label in RESEARCH_SECTION_LINKS)
    return ('<nav class="atlas-research-section-nav" aria-label="Research sections" '
            'data-atlas-qa="research-section-navigation">' + links + '</nav>')


def executive_digest_html(page):
    digest = page.get('investment_digest') or {}
    if digest.get('status') != 'AVAILABLE':
        return ''
    paragraphs = ''.join('<p>'+escape(_readable(s))+'</p>' for s in digest.get('executive_digest') or ())
    update = next((a['answer'] for a in digest.get('answers') or () if a['key']=='changes'), 'Dated company developments are unavailable.')
    return (RESEARCH_REFERENCE_CSS+'<section class="atlas-research-digest" data-atlas-qa="research-executive-digest">'
            '<article><small>EXECUTIVE DIGEST · VERIFIED EVIDENCE</small><h3>'+escape(str(page.get('company') or page.get('ticker')))+' at a glance</h3>'+paragraphs+
            '<footer>Deterministic evidence summary · External AI not invoked<br>Certified close as of '+escape(_as_of_date(digest.get('as_of')))+'</footer></article>'
            '<article class="atlas-digest-update"><small>RECENT DEVELOPMENTS</small><h3>What changed?</h3><p>'+escape(_readable(update))+'</p>'
            '<footer>Only dated company evidence admitted for customer display. Retained updates are not represented as current news.</footer></article></section>')


def comprehensive_analysis_html(page):
    digest = page.get('investment_digest') or {}
    if digest.get('status') != 'AVAILABLE': return ''
    return (RESEARCH_REFERENCE_CSS+'<section class="atlas-research-analysis" data-atlas-qa="research-comprehensive-analysis">'+''.join(
        '<article data-atlas-question="'+escape(str(a['key']))+'"><h4>'+escape(str(a['question']))+'</h4><p>'+escape(_readable(a['answer']))+'</p></article>' for a in digest.get('answers') or ())+'</section>')


def fundamentals_cards_html(facts):
    """Display admitted labels/values verbatim; perform no financial inference."""
    return ('<section class="atlas-research-fundamentals" aria-label="Fundamentals snapshot" '
            'data-atlas-qa="research-fundamental-cards">' + ''.join(
                '<article><small>' + escape(str(fact["fact_name"])) + '</small><strong>'
                + escape(str(fact["display_value"])) + '</strong></article>'
                for fact in facts) + '</section>')


# Public diagnostic projection only; never reload or depend on a warm financial module.
ADMISSION_STATUS_CODES = frozenset({"AVAILABLE", "PARTIAL", "UNAVAILABLE", "QA_ONLY", "NOT_RECORDED"})
ADMISSION_REASON_CODES = frozenset({
    "INVALID_TICKER", "ROOTS_NOT_CONFIGURED", "FILE_NOT_FOUND", "FILE_UNREADABLE",
    "SCHEMA_OR_LINEAGE_REJECTED", "SOURCE_PIN_MISMATCH", "BUNDLE_PIN_MISMATCH",
    "BACKUP_AUTHORITY_REJECTED", "RECORD_HASH_MISMATCH", "NO_VERIFIED_FAMILIES",
    "CONTEXT_ADMITTED", "HISTORY_FAMILY_REJECTED", "HISTORY_FAMILY_MISSING",
    "QA_ENRICHMENT_USED", "ADMISSION_RECEIPT_UNAVAILABLE", "BUNDLE_ACCEPTED",
})


def public_admission_marker_values(receipt: Any) -> dict[str, Any]:
    """Only public enumerated codes may cross the rendered diagnostic boundary."""
    receipt = receipt if isinstance(receipt, Mapping) else {}
    status, reason = receipt.get("status"), receipt.get("reason")
    result = {
        "status": status if isinstance(status, str) and status in ADMISSION_STATUS_CODES else "NOT_RECORDED",
        "reason": reason if isinstance(reason, str) and reason in ADMISSION_REASON_CODES else "ADMISSION_RECEIPT_UNAVAILABLE",
    }
    for field in ("primary_configured", "backup_configured", "source_pin_configured", "bundle_pin_configured"):
        result[field] = receipt.get(field) is True
    for field in ("accepted_family_count", "rejected_family_count"):
        value = receipt.get(field)
        result[field] = value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0
    history = receipt.get("history_status")
    result["history_status"] = history if isinstance(history, str) and history in {
        "ADMITTED", "REJECTED", "MISSING", "NOT_EVALUATED"
    } else "NOT_EVALUATED"
    result["history_reason"] = {
        "ADMITTED": "HISTORY_FAMILY_ADMITTED", "REJECTED": "HISTORY_FAMILY_REJECTED",
        "MISSING": "HISTORY_FAMILY_ABSENT", "NOT_EVALUATED": "HISTORY_NOT_EVALUATED",
    }[result["history_status"]]
    return result


# Shared, stateless customer presentation helpers live in this already
# refresh-safe module so an older loaded refresh allowlist remains compatible.
def market_cards_html(context, *, money, timestamp, show_empty_notice=True):
    cards=[]
    for item in list(context.get('instruments') or ())[:4]:
        value=item.get('change_pct')
        try:
            numeric=float(value)
            change=f'{numeric:+.2f}%' if math.isfinite(numeric) else 'Unavailable'
        except (TypeError,ValueError):
            numeric=0;change='Unavailable'
        tone='positive' if numeric>0 else 'negative' if numeric<0 else 'neutral'
        try:
            price=float(item.get('price'));price_label=money(price) if math.isfinite(price) and price>0 else 'Unavailable'
        except (TypeError,ValueError):price_label='Unavailable'
        cards.append('<article class="atlas-reference-index"><small>'+escape(str(item.get('symbol') or item.get('label') or 'Market'))+'</small><strong>'+escape(price_label)+'</strong><span class="'+tone+'">'+escape(change)+'</span></article>')
    body='<div class="atlas-reference-indices">'+''.join(cards)+'</div>' if cards else ('<p class="atlas-reference-market-empty">Current governed market readings unavailable.</p>' if show_empty_notice else '')
    return '<section data-atlas-qa="home-reference-markets" data-atlas-non-scoring="true"><header><h2>U.S. market context</h2><span>'+escape(timestamp(context.get('as_of')))+'</span></header><p class="atlas-reference-source">ETF market proxies · reference only · no inferred index levels</p>'+body+'</section>'


def opportunity_table_html(cards, *, money, score):
    rows=[]
    for card in cards:
        upside=card.get('live_implied_upside_pct')
        if upside is None:upside=card.get('atlas_expected_return')
        rows.append('<tr><td data-label="Rank">'+escape(str(card.get('production_rank') or '—'))+'</td><th scope="row">'+escape(str(card.get('ticker') or 'Unavailable'))+'<small>'+escape(str(card.get('company') or 'Company unavailable'))+'</small></th><td data-label="Dated close">'+escape(money(card.get('display_price')))+'</td><td data-label="ATLAS Fair Value">'+escape(money(card.get('atlas_fair_value')))+'</td><td data-label="Potential">'+escape(score(upside,suffix='%'))+'</td><td data-label="Confidence">'+escape(score(card.get('decision_confidence'),suffix='%'))+'</td></tr>')
    return '<section class="atlas-reference-shortlist" data-atlas-qa="home-reference-shortlist"><h3>Top published opportunities</h3><div role="region" aria-label="Published opportunity comparison" tabindex="0"><table><thead><tr><th>Rank</th><th>Company</th><th>Dated close</th><th>ATLAS Fair Value</th><th>Potential</th><th>Confidence</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table></div></section>'


def published_inventory_html(count, *, timestamp):
    """Present the admitted count and product target separately; never pad inventory."""
    return ('<div class="atlas-home-inventory-note" data-atlas-qa="home-published-inventory-note">'
            '<strong>' + escape(str(count)) + ' published BUY NOW opportunities</strong>'
            '<span>Top 15 is the target capacity; only admitted opportunities are shown.</span>'
            '<span>Retained certified snapshot · ' + escape(timestamp) + ' · Not a live refresh.</span></div>')
