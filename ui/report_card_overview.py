"""Read-only Report Card executive presentation; never derives investment returns."""
from html import escape
from typing import Any, Mapping


def overview_html(report: Mapping[str, Any]) -> str:
    observations = int(report['observation_count'])
    metrics = (
        ('Signals', report['signal_count'], 'Original registered cohort'),
        ('Observations', observations, 'Prospective evidence in the ledger'),
        ('Open signals', report['open_signal_count'], 'Tracking remains in progress'),
        ('SPY comparisons', report['spy_comparison_count'], 'Same-session benchmark evidence'),
    )
    cards = ''.join(
        f'<article><small>{escape(label)}</small><strong>{int(value):,}</strong>'
        f'<span>{escape(note)}</span></article>' for label, value, note in metrics
    )
    if observations == 0:
        title = 'Performance is pending'
        description = ('No prospective price observations have been recorded. Signal returns, '
                       'SPY excess returns and win rates are unavailable until genuine, certified '
                       'observations are authorized and recorded.')
    else:
        title = 'Recorded evidence is available'
        description = ('Review each signal and horizon below for its recorded price, return and '
                       'same-session SPY comparison. Missing observations remain pending; '
                       'no cohort-wide performance is inferred here.')
    return (
        '<section class="atlas-rc-summary" aria-label="Report Card evidence summary" '
        'data-atlas-qa="report-card-executive-summary">'
        f'<div class="atlas-rc-metrics">{cards}</div>'
        '<div class="atlas-rc-evidence-grid">'
        f'<article class="atlas-rc-pending"><small>PROSPECTIVE PERFORMANCE</small>'
        f'<h2>{escape(title)}</h2><p>{escape(description)}</p></article>'
        '<article><small>HISTORICAL SIGNAL EVIDENCE</small><h2>Review the original investment case</h2>'
        '<p>Open a signal below to inspect its original dated price chart and evidence. '
        'Historical prices provide context; they do not create a prospective observation.</p>'
        '<span class="atlas-rc-private">Private review · Public activation OFF</span></article>'
        '</div></section>'
    )


OVERVIEW_CSS = '''<style>
.atlas-rc-summary{margin:.5rem 0 1.5rem;color:#e8eff8}
.atlas-rc-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.75rem}
.atlas-rc-summary article{min-width:0;border:1px solid #293b51;border-radius:16px;padding:1.15rem;background:linear-gradient(145deg,#122236,#0d1727)}
.atlas-rc-summary small{display:block;font-size:.73rem;letter-spacing:.065em;color:#a8bed5;line-height:1.4}
.atlas-rc-metrics strong{display:block;font-size:2.2rem;line-height:1.2;font-variant-numeric:tabular-nums;margin:.4rem 0;color:#f5f9ff}
.atlas-rc-metrics span{display:block;font-size:.77rem;line-height:1.45;color:#a8b9cc}
.atlas-rc-evidence-grid{display:grid;grid-template-columns:1.25fr 1fr;gap:.75rem;margin-top:.75rem}
.atlas-rc-summary .atlas-rc-pending{border-color:#665637;background:linear-gradient(135deg,#27251e,#131f2e)}
.atlas-rc-summary h2{font-size:1.25rem!important;line-height:1.25!important;margin:.5rem 0!important;padding:0!important}
.atlas-rc-summary p{font-size:.9rem;line-height:1.6;color:#c4d2e1;margin:.5rem 0}
.atlas-rc-private{display:inline-block;margin-top:.4rem;font-size:.72rem;padding:.35rem .6rem;border:1px solid #3a536e;border-radius:999px;color:#b9d7f5}
@media(max-width:1000px){.atlas-rc-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.atlas-rc-evidence-grid{grid-template-columns:1fr 1fr}}
@media(max-width:600px){.atlas-rc-evidence-grid{grid-template-columns:1fr}.atlas-rc-summary article{padding:.85rem}.atlas-rc-metrics{gap:.5rem}.atlas-rc-metrics strong{font-size:1.8rem}.atlas-rc-summary h2{font-size:1.1rem!important}}
</style>'''
