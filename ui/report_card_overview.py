"""Read-only Report Card executive presentation; never derives investment returns."""
from html import escape
from typing import Any, Mapping
from services.report_card import HORIZONS


def benchmark_evidence(report: Mapping[str, Any], horizon: int | None = None) -> dict[str, Any]:
    """Select paired recorded returns only; never create a portfolio series."""
    import math
    if not report.get('observation_count'):
        return {'status': 'PENDING', 'rows': (),
                'reason': 'No prospective observations are recorded. Approved entry timing, aligned SPY evidence and matured horizons are required before comparison.'}
    # The legacy service admits per-row returns without a policy label. Any
    # explicit restriction (including unknown future policy) fails closed.
    if report.get('performance_policy') not in (None, ''):
        return {'status': 'WITHHELD', 'rows': (),
                'reason': 'Recorded prices do not authorize performance. Approved aligned-entry methodology is required.'}
    rows = report.get('rows')
    rows = rows if isinstance(rows, (tuple, list)) else ()
    if horizon is not None:
        rows = [item for item in rows if isinstance(item, Mapping)
                and item.get('horizon_sessions') == horizon]
    pairs = []
    identities = [(item.get('signal_id'), item.get('horizon_sessions'))
                  for item in rows if isinstance(item, Mapping)]
    for item in rows:
        if not isinstance(item, Mapping) or item.get('status') != 'AVAILABLE':
            continue
        identity = (item.get('signal_id'), item.get('horizon_sessions'))
        if identities.count(identity) != 1:
            continue
        if (not all(isinstance(item.get(key), str) and item[key].strip()
                    for key in ('signal_id', 'ticker', 'observed_at'))
                or type(item.get('horizon_sessions')) is not int or item['horizon_sessions'] not in HORIZONS
                or not all(type(item.get(key)) in (int, float) and math.isfinite(item[key])
                           for key in ('stock_return', 'spy_return'))):
            continue
        pairs.append(dict(item))
    if pairs and report.get('observation_count', 0) > 0:
        return {'status': 'AVAILABLE', 'rows': tuple(pairs),
                'reason': 'Individual recorded observations at the same registered horizon; not a funded portfolio or cumulative return.'}
    pending = any(isinstance(item, Mapping) and item.get('status') == 'NOT_MATURED_OR_NOT_OBSERVED' for item in rows)
    return {'status': 'PENDING' if not report.get('observation_count') or pending else 'UNAVAILABLE', 'rows': (),
            'reason': 'No approved paired ATLAS signal and SPY returns are available. Missing evidence and not-yet-observed horizons remain unmeasured.'}


def render_benchmark_panel(report: Mapping[str, Any]) -> None:
    import streamlit as st
    selected = st.selectbox('Comparison horizon', HORIZONS,
                            format_func=lambda value: f'{value} trading sessions',
                            key='report_card_benchmark_horizon')
    evidence = benchmark_evidence(report, selected)
    st.markdown(
        f'<section class="atlas-rc-benchmark atlas-rc-benchmark--{evidence["status"].lower()}" data-atlas-qa="report-card-benchmark-evidence" '
        f'data-atlas-benchmark-status="{evidence["status"]}" data-atlas-benchmark-horizon="{selected}">'
        '<h2>ATLAS signals vs SPY</h2><div class="atlas-rc-legend"><b>● ATLAS signal</b><span>● SPY benchmark</span></div>'
        + (f'<div class="atlas-rc-empty"><strong>Comparison {evidence["status"].lower()}</strong>'
           '<span>No performance curve is drawn without approved evidence.</span></div>' if not evidence['rows'] else '')
        + f'<p>{escape(evidence["reason"])}</p></section>', unsafe_allow_html=True,
    )
    if not evidence['rows']:
        return
    import plotly.graph_objects as go
    pairs = [item for item in evidence['rows'] if item['horizon_sessions'] == selected]
    figure = go.Figure()
    for name, field, color in (('ATLAS signal', 'stock_return', '#39aaff'), ('SPY benchmark', 'spy_return', '#dbe8f5')):
        figure.add_bar(name=name, x=[f'{item["ticker"]} · {item["signal_id"]}' for item in pairs],
                       y=[item[field] for item in pairs], marker_color=color,
                       customdata=[[item['observed_at'], item['horizon_sessions']] for item in pairs],
                       hovertemplate='%{x}<br>Return: %{y:.2%}<br>Observed: %{customdata[0]}<br>Horizon: %{customdata[1]} sessions<extra>%{fullData.name}</extra>')
    categories = [f'{item["ticker"]} · {item["signal_id"]}' for item in pairs]
    labels = [f'{item["ticker"]} · {item["signal_id"][:8]}'+('…' if len(item['signal_id']) > 8 else '') for item in pairs]
    figure.update_layout(barmode='group', height=340, margin=dict(l=70, r=10, t=20, b=100),
                         paper_bgcolor='#0b192a', plot_bgcolor='#0b192a', font_color='#c5d9ec',
                         yaxis=dict(tickformat='.0%', title=dict(text='Recorded return', standoff=12),
                                    automargin=True, tickfont=dict(color='#c5d9ec')),
                         xaxis=dict(title='Original signal identity', tickmode='array', tickvals=categories,
                                    ticktext=labels, tickangle=0, tickfont=dict(color='#c5d9ec'), automargin=True),
                         legend=dict(orientation='h', y=-.4, x=0, font=dict(color='#c5d9ec')))
    st.plotly_chart(figure, width='stretch', key='report_card_benchmark_pairs', theme=None)


def overview_html(report: Mapping[str, Any]) -> str:
    observations = int(report['observation_count'])
    comparison = benchmark_evidence(report)
    metrics = (
        ('Signals', report['signal_count'], 'Original registered cohort'),
        ('Observations', observations, 'Prospective evidence in the ledger'),
        ('Open signals', report['open_signal_count'], 'Tracking remains in progress'),
        ('SPY comparisons', report['spy_comparison_count'], 'Same-session benchmark evidence'),
        ('Performance', 'Per signal' if comparison['status'] == 'AVAILABLE' else comparison['status'].title(),
         'No portfolio return inferred'),
    )
    cards = ''.join(
        f'<article><small>{escape(label)}</small><strong>{escape(str(value))}</strong>'
        f'<span>{escape(note)}</span></article>' for label, value, note in metrics
    )
    if observations == 0:
        title = 'Performance is pending'
        description = ('No prospective price observations have been recorded. Signal returns, '
                       'SPY excess returns and win rates are unavailable until genuine, certified '
                       'observations are authorized and recorded.')
    elif report.get('performance_policy') not in (None, ''):
        title = 'Recorded prices; performance withheld'
        description = ('Recorded observations remain visible as evidence counts. Returns, SPY excess returns '
                       'and win rates are withheld pending separately approved, aligned-entry methodology. '
                       'A valid snapshot hash does not establish performance authority.')
    elif comparison['status'] != 'AVAILABLE':
        title = 'Performance comparison ' + comparison['status'].lower()
        description = ('Recorded observation counts do not establish usable paired returns. '
                       + comparison['reason'])
    else:
        title = 'Recorded evidence is available'
        description = ('Review each signal and horizon below for its recorded price, return and '
                       'same-session SPY comparison. Missing observations remain pending; '
                       'no cohort-wide performance is inferred here.')
    return (
        '<section class="atlas-rc-summary" aria-label="Report Card evidence summary" '
        'data-atlas-qa="report-card-executive-summary">'
        f'<div class="atlas-rc-metrics" tabindex="0" role="region" aria-label="Report Card KPI strip">{cards}</div>'
        '<div class="atlas-rc-status-line">'
        f'<b>{escape(title)}</b><p>{escape(description)}</p>'
        '<p>Open a signal below to inspect its original dated price chart and evidence. '
        'Historical prices provide context; they do not create a prospective observation.</p>'
        '<span class="atlas-rc-private">Private review · Public activation OFF</span>'
        '</div></section>'
    )


OVERVIEW_CSS = '''<style>
.atlas-report-card-hero{padding:1rem;border:1px solid #293b51;border-radius:14px;background:#0d1b2c;color:#e8eff8;margin-bottom:.75rem}.atlas-report-card-hero .atlas-kicker{font-size:.68rem;letter-spacing:.08em;color:#70b9ed}.atlas-report-card-hero h1{font-size:1.55rem!important;line-height:1.2!important;margin:.4rem 0!important;padding:0!important;color:#edf6ff}.atlas-report-card-hero p{font-size:.82rem;line-height:1.5;color:#adc4dc;margin:.3rem 0}
.atlas-rc-summary{margin:.25rem 0 .5rem;color:#e8eff8}
.atlas-rc-metrics{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:.5rem;overflow-x:auto}
.atlas-rc-metrics:focus-visible{outline:2px solid #8bc1ff;outline-offset:2px}
.atlas-rc-summary article{min-width:0;border:1px solid #293b51;border-radius:16px;padding:1.15rem;background:linear-gradient(145deg,#122236,#0d1727)}
.atlas-rc-summary small{display:block;font-size:.73rem;letter-spacing:.065em;color:#a8bed5;line-height:1.4}
.atlas-rc-metrics article{padding:.75rem}.atlas-rc-metrics strong{display:block;font-size:clamp(1rem,1.6vw,1.5rem);line-height:1.2;font-variant-numeric:tabular-nums;margin:.25rem 0;color:#f5f9ff}
.atlas-rc-metrics span{display:block;font-size:.77rem;line-height:1.45;color:#a8b9cc}
.atlas-rc-evidence-grid{display:grid;grid-template-columns:1.25fr 1fr;gap:.75rem;margin-top:.75rem}
.atlas-rc-summary .atlas-rc-pending{border-color:#665637;background:linear-gradient(135deg,#27251e,#131f2e)}
.atlas-rc-summary h2{font-size:1.25rem!important;line-height:1.25!important;margin:.5rem 0!important;padding:0!important}
.atlas-rc-summary p{font-size:.9rem;line-height:1.6;color:#c4d2e1;margin:.5rem 0}
.atlas-rc-private{display:inline-block;margin-top:.4rem;font-size:.72rem;padding:.35rem .6rem;border:1px solid #3a536e;border-radius:999px;color:#b9d7f5}
.atlas-rc-status-line{margin:.75rem 0;padding:.8rem 1rem;border-left:3px solid #3998e8;background:#101e30;border-radius:4px 12px 12px 4px}.atlas-rc-status-line p{font-size:.8rem;margin:.25rem 0}.atlas-rc-status-line b{font-size:.95rem;color:#d8eaff}
.atlas-rc-benchmark{padding:1rem;border:1px solid #2c4560;border-radius:14px;background:linear-gradient(145deg,#0e2339,#091522);color:#dcecff;min-height:240px}.atlas-rc-benchmark--available{min-height:0}.atlas-rc-benchmark h2{font-size:1.15rem!important;margin:0 0 .5rem!important}.atlas-rc-benchmark p{color:#a9bfd5;font-size:.85rem;line-height:1.55}.atlas-rc-legend{display:flex;gap:1rem;font-size:.75rem;color:#afc6df}.atlas-rc-legend b{color:#52b6ff}.atlas-rc-empty{display:grid;place-content:center;min-height:140px;text-align:center;border:1px dashed #36536f;border-radius:10px;margin:.8rem 0;padding:.7rem}.atlas-rc-empty strong{font-size:1rem;color:#e3d5b2}.atlas-rc-empty span{font-size:.8rem;color:#aac0d6;margin-top:.5rem}
.atlas-rc-support{padding:.75rem;border:1px solid #293b51;border-radius:14px;background:#0d1b2c;color:#c4d2e1;overflow-wrap:anywhere}
.atlas-rc-support h2{font-size:1rem!important;margin:0!important;padding:0!important;color:#e8eff8}.atlas-rc-support p{font-size:.8rem;line-height:1.4;margin:.55rem 0}.atlas-rc-support small{font-size:.72rem;color:#a8bed5}
.atlas-rc-status-line{margin:.5rem 0;padding:.55rem .75rem}.atlas-rc-status-line p{font-size:.78rem;line-height:1.4}
.atlas-rc-benchmark--pending,.atlas-rc-benchmark--unavailable,.atlas-rc-benchmark--withheld{min-height:200px}.atlas-rc-empty{min-height:90px}
@media(max-width:600px){.atlas-rc-metrics{grid-template-columns:repeat(5,minmax(125px,1fr));gap:.4rem;padding-bottom:.4rem}.atlas-rc-summary article{padding:.6rem}.atlas-rc-metrics strong{font-size:1.1rem}.atlas-rc-summary h2{font-size:1.1rem!important}}
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
        registration = _registration_time(signal.get('registered_at'))
        registration_date = ' '.join(registration.split()[:3])
        rows.append(
            f'<tr data-atlas-signal-id="{escape(str(signal["signal_id"]))}">'
            f'<th scope="row">{escape(str(signal["ticker"]))}</th>'
            f'<td><span class="atlas-rc-signal-state">{escape(state)}</span></td>'
            f'<td title="{escape(registration, quote=True)}">{escape(registration_date)}</td>'
            f'<td>{escape(_date(signal.get("signal_timestamp")))}</td>'
            f'<td>{escape(_reference_price(signal.get("reference_price")))}'
            f'<small>{escape(_date(signal.get("reference_price_timestamp")))}</small></td>'
            '<td>Unavailable<small>Not the reference price</small></td>'
            f'<td>{escape(", ".join(str(value) for value in signal.get("registered_horizons") or ())) or "Unavailable"}'
            '<small>Trading sessions · SPY alignment: see detail</small></td>'
            '</tr>'
        )
    return (
        f'<section class="atlas-rc-directory" data-atlas-qa="report-card-signal-directory" data-atlas-signal-count="{len(signals)}">'
        '<h2>Original signal history</h2><p>Registered recommendations and their original price evidence.</p>'
        '<div class="atlas-rc-directory-scroll" tabindex="0" role="region" aria-label="Original signal history table">'
        '<table><caption>Original registered signals</caption><thead><tr>'
        '<th scope="col">Signal</th><th scope="col">Observations</th><th scope="col">Registered (UTC)</th>'
        '<th scope="col">Original signal date</th><th scope="col">Signal reference price</th>'
        '<th scope="col">Executable entry</th><th scope="col">Registered horizons / SPY</th>'
        '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>'
        '<p class="atlas-rc-reference-note">Scroll the table for entry, horizon and observation evidence. '
        'A signal reference price is not an executable entry. '
        'Registration is the immutable ledger record time, not proof of customer publication. '
        'Original signal and reference-price dates do not establish an executable entry. '
        'Historical prices do not create prospective returns. Open a signal to inspect its original chart and evidence.</p>'
        '</section>'
    )


DIRECTORY_CSS = '''<style>
.atlas-rc-directory{margin:0 0 1rem;padding:.8rem;border:1px solid #293b51;border-radius:14px;background:#0d1b2c;color:#e7eff9}.atlas-rc-directory h2{font-size:1.15rem!important;margin:.25rem 0!important;color:#e7eff9}
.atlas-rc-directory p{color:#a9bfd5;font-size:.88rem;line-height:1.5}.atlas-rc-directory-scroll{max-height:420px;overflow:auto;border:1px solid #30455e;border-radius:14px;background:#101d2f}
.atlas-rc-directory table{width:100%;border-collapse:collapse;min-width:760px;font-size:.82rem}
.atlas-rc-directory caption{text-align:left;padding:.6rem .8rem;color:#a9bfd5;font-size:.78rem}
.atlas-rc-directory th,.atlas-rc-directory td{padding:.55rem .6rem;text-align:left;border-bottom:1px solid #263b54;vertical-align:middle}
.atlas-rc-directory thead th{position:sticky;top:0;background:#182b42;color:#c0d6ed;font-size:.72rem;letter-spacing:.025em;z-index:1}
.atlas-rc-directory tbody th{color:#f1f7ff;font-weight:750}.atlas-rc-directory td{color:#d4e2f1;font-variant-numeric:tabular-nums;white-space:nowrap}
.atlas-rc-directory td small{display:block;color:#9aafc6;font-size:.7rem;margin-top:.22rem;white-space:normal;max-width:140px}
.atlas-rc-signal-state{display:inline-block;padding:.25rem .5rem;border:1px solid #6a593c;border-radius:999px;background:#2a281f;color:#e8cc91;font-size:.76rem}
.atlas-rc-directory .atlas-rc-reference-note{font-size:.75rem;color:#9bafc5;margin:.6rem 0}
.atlas-rc-directory-scroll:focus-visible{outline:3px solid #8bc1ff;outline-offset:3px}
@media(max-width:600px){.atlas-rc-directory th,.atlas-rc-directory td{padding:.55rem .6rem}}
</style>'''


def select_history(signals, *, query='', observations='All', order='Ledger order'):
    """Presentation-only selection; original records and ledger ordering stay intact."""
    from datetime import datetime, timezone
    query = query.strip().casefold()
    result = [item for item in signals if
              (not query or query in ' '.join(str(item.get(field) or '') for field in
               ('ticker', 'signal_id', 'original_action', 'signal_timestamp', 'registered_at')).casefold())
              and (observations == 'All'
                   or observations == 'Pending' and not item.get('observation_count')
                   or observations == 'Recorded' and bool(item.get('observation_count')))]
    if order in ('Ticker A–Z', 'Ticker Z–A'):
        return sorted(result, key=lambda item: str(item['ticker']).casefold(), reverse=order == 'Ticker Z–A')
    if order in ('Registered newest', 'Registered oldest'):
        def timestamp(item):
            try:
                value = datetime.fromisoformat(str(item.get('registered_at')).replace('Z', '+00:00'))
                return value.astimezone(timezone.utc).timestamp() if value.tzinfo else None
            except (ValueError, TypeError, OverflowError):
                return None
        known = [item for item in result if timestamp(item) is not None]
        unknown = [item for item in result if timestamp(item) is None]
        return sorted(known, key=timestamp, reverse=order == 'Registered newest') + unknown
    return result


def render_signal_directory(signals, *, on_open) -> None:
    import streamlit as st
    search_column, filter_column, sort_column = st.columns([2, 1, 1])
    with search_column:
        query = st.text_input('Search original signals', key='report_card_history_query',
                          placeholder='Ticker, signal ID, action or date')
    with filter_column:
        observations = st.selectbox('Observation filter', ('All', 'Pending', 'Recorded'),
                                key='report_card_history_observations')
    with sort_column:
        order = st.selectbox('History order', ('Ledger order', 'Ticker A–Z', 'Ticker Z–A',
                                         'Registered newest', 'Registered oldest'),
                         key='report_card_history_order')
    visible = select_history(signals, query=query, observations=observations, order=order)
    st.caption(f'Showing {len(visible)} of {len(signals)} original signals. Recorded counts are not performance approval.')
    st.markdown(DIRECTORY_CSS + signal_directory_html(visible), unsafe_allow_html=True)
    by_id = {str(item['signal_id']): item for item in visible}
    if st.session_state.get('report_card_directory_selection') not in by_id:
        st.session_state['report_card_directory_selection'] = next(iter(by_id), None)
    if not by_id:
        st.info('No original signals match these controls. Clear the search or choose All observations.')
        return
    selected = st.selectbox(
        'Open an original signal', tuple(by_id),
        format_func=lambda signal_id: f'{by_id[signal_id]["ticker"]} · {_date(by_id[signal_id].get("signal_timestamp"))} · {signal_id}',
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
