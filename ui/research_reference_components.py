"""Reference-aligned presentation of the same admitted customer evidence."""
from html import escape
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
.atlas-r2-head .atlas-r2-metrics{grid-template-columns:repeat(5,minmax(0,1fr));margin:.8rem 0 0;gap:.5rem}.atlas-r2-head .atlas-r2-metrics .atlas-r2-metric{padding:.75rem}.atlas-r2-head .atlas-r2-metrics strong{font-size:1.25rem;font-variant-numeric:tabular-nums}.atlas-r2-head .atlas-r2-metric p{font-size:.7rem;line-height:1.45;color:#9eb4c9;margin:.45rem 0 0}.atlas-research-section-nav{display:flex;gap:.45rem;overflow-x:auto;padding:.4rem 0 .7rem;margin:.3rem 0;scrollbar-width:thin}.atlas-research-section-nav a{white-space:nowrap;padding:.55rem .8rem;border:1px solid #21425a;border-radius:8px;background:#0a1e31;color:#bbddf6;text-decoration:none;font-size:.8rem}.atlas-research-section-nav a:hover,.atlas-research-section-nav a:focus-visible{background:#123957;color:white;outline:2px solid #56aef3}
@media(max-width:1000px){.atlas-r2-head .atlas-r2-metrics{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:700px){body:has([data-atlas-qa="research-v2-root"]) [data-testid="stMainBlockContainer"]{padding-left:.75rem!important;padding-right:.75rem!important}.atlas-r2-head .atlas-r2-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.atlas-r2-head .atlas-r2-metrics strong{font-size:1.2rem}.atlas-r2-head .atlas-r2-metrics .atlas-r2-metric:last-child{grid-column:1/-1}}
</style>'''


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
