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
    elif report.get('performance_policy') == 'VISIBILITY_ONLY_NO_RETURN_AUTHORITY':
        title = 'Recorded prices; performance withheld'
        description = ('Recorded observations remain visible as evidence counts. Returns, SPY excess returns '
                       'and win rates are withheld pending separately approved, aligned-entry methodology. '
                       'A valid snapshot hash does not establish performance authority.')
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


def _date(value: Any) -> str:
    from datetime import datetime, timezone
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).strftime('%b %d, %Y')
    except (TypeError, ValueError):
        return 'Date unavailable'


def _registration_time(value: Any) -> str:
    """Only an explicit timezone-aware ledger envelope timestamp is registration."""
    from datetime import datetime, timezone
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            return 'Registration unavailable'
        return parsed.astimezone(timezone.utc).strftime('%b %d, %Y %H:%M:%S UTC')
    except (TypeError, ValueError):
        return 'Registration unavailable'


def _reference_price(value: Any) -> str:
    import math
    try:
        price = float(value)
        return f'${price:,.2f}' if math.isfinite(price) else 'Unavailable'
    except (TypeError, ValueError):
        return 'Unavailable'


def signal_directory_html(signals) -> str:
    """Original signal identity and pending evidence; no derived entry or return."""
    rows = []
    for signal in signals:
        count = int(signal.get('observation_count') or 0)
        state = f'{count} recorded' if count else 'Pending'
        rows.append(
            f'<tr data-atlas-signal-id="{escape(str(signal["signal_id"]))}">'
            f'<th scope="row">{escape(str(signal["ticker"]))}</th>'
            f'<td>{escape(_registration_time(signal.get("registered_at")))}</td>'
            f'<td>{escape(_date(signal.get("signal_timestamp")))}</td>'
            f'<td>{escape(_reference_price(signal.get("reference_price")))}'
            f'<small>{escape(_date(signal.get("reference_price_timestamp")))}</small></td>'
            f'<td><span class="atlas-rc-signal-state">{escape(state)}</span></td></tr>'
        )
    return (
        f'<section class="atlas-rc-directory" data-atlas-qa="report-card-signal-directory" data-atlas-signal-count="{len(signals)}">'
        '<h2>Original signal history</h2><p>Registered recommendations and their original price evidence.</p>'
        '<div class="atlas-rc-directory-scroll" tabindex="0" role="region" aria-label="Original signal history table">'
        '<table><caption>Original registered signals</caption><thead><tr>'
        '<th scope="col">Signal</th><th scope="col">Registered (UTC)</th>'
        '<th scope="col">Original signal date</th><th scope="col">Signal reference price</th><th scope="col">Observations</th>'
        '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>'
        '<p class="atlas-rc-reference-note">A signal reference price is not an executable entry. '
        'Registration is the immutable ledger record time, not proof of customer publication. '
        'Original signal and reference-price dates do not establish an executable entry. '
        'Historical prices do not create prospective returns. Open a signal to inspect its original chart and evidence.</p>'
        '</section>'
    )


DIRECTORY_CSS = '''<style>
.atlas-rc-directory{margin:1.1rem 0;color:#e7eff9}.atlas-rc-directory h2{font-size:1.45rem!important;margin:.25rem 0!important}
.atlas-rc-directory p{color:#a9bfd5;font-size:.88rem;line-height:1.5}.atlas-rc-directory-scroll{max-height:420px;overflow:auto;border:1px solid #30455e;border-radius:14px;background:#101d2f}
.atlas-rc-directory table{width:100%;border-collapse:collapse;min-width:480px;font-size:.88rem}
.atlas-rc-directory caption{text-align:left;padding:.6rem .8rem;color:#a9bfd5;font-size:.78rem}
.atlas-rc-directory th,.atlas-rc-directory td{padding:.8rem;text-align:left;border-bottom:1px solid #263b54;vertical-align:middle}
.atlas-rc-directory thead th{position:sticky;top:0;background:#182b42;color:#c0d6ed;font-size:.72rem;letter-spacing:.025em;z-index:1}
.atlas-rc-directory tbody th{color:#f1f7ff;font-weight:750}.atlas-rc-directory td{color:#d4e2f1;font-variant-numeric:tabular-nums}
.atlas-rc-directory td small{display:block;color:#9aafc6;font-size:.7rem;margin-top:.22rem}
.atlas-rc-signal-state{display:inline-block;padding:.25rem .5rem;border:1px solid #6a593c;border-radius:999px;background:#2a281f;color:#e8cc91;font-size:.76rem}
.atlas-rc-directory .atlas-rc-reference-note{font-size:.75rem;color:#9bafc5;margin:.6rem 0}
.atlas-rc-directory-scroll:focus-visible{outline:3px solid #8bc1ff;outline-offset:3px}
@media(max-width:600px){.atlas-rc-directory th,.atlas-rc-directory td{padding:.65rem .6rem}.atlas-rc-directory table{min-width:440px;font-size:.82rem}}
</style>'''


def render_signal_directory(signals, *, on_open) -> None:
    import streamlit as st
    st.markdown(DIRECTORY_CSS + signal_directory_html(signals), unsafe_allow_html=True)
    by_id = {str(item['signal_id']): item for item in signals}
    if not by_id:
        st.caption('No registered signals are available.')
        return
    selected = st.selectbox(
        'Open an original signal', tuple(by_id),
        format_func=lambda signal_id: f'{by_id[signal_id]["ticker"]} · {_date(by_id[signal_id].get("signal_timestamp"))}',
        key='report_card_directory_selection',
    )
    st.button('Open selected signal →', key='report_card_directory_open',
              on_click=on_open, args=(st.session_state, selected), type='primary')


def horizon_coverage_html(coverage: Mapping[Any, Mapping[str, Any]]) -> str:
    """Render recorded coverage verbatim; pending is never a zero return."""
    rows = ''.join(
        '<tr><th scope="row">' + escape(str(horizon)) + ' sessions</th>'
        + ''.join('<td>' + str(int(values.get(key, 0))) + '</td>'
                  for key in ('available', 'unavailable', 'pending')) + '</tr>'
        for horizon, values in coverage.items()
    )
    return (
        '<section class="atlas-rc-directory" data-atlas-qa="report-card-horizon-coverage">'
        '<div class="atlas-rc-directory-scroll" tabindex="0" role="region" aria-label="Horizon observation coverage">'
        '<table><caption>Recorded observation counts by horizon; pending is not a measured return.</caption>'
        '<thead><tr><th scope="col">Horizon</th><th scope="col">Available</th>'
        '<th scope="col">Unavailable</th><th scope="col">Pending</th></tr></thead>'
        '<tbody>' + rows + '</tbody></table></div></section>'
    )
