from ui.report_card_overview import overview_html


def report(observations=0):
    return dict(signal_count=20, observation_count=observations, open_signal_count=20, spy_comparison_count=0)


def test_zero_observations_cannot_be_presented_as_zero_return_or_win_rate():
    view = overview_html(report())
    assert 'Performance is pending' in view
    assert 'win rates are unavailable' in view
    assert '0%' not in view and '$0' not in view
    assert 'Public activation OFF' in view
    assert 'Historical prices provide context' in view
    assert 'do not create a prospective observation' in view


def test_recorded_observations_do_not_imply_aggregate_performance():
    value = dict(report(3), rows=[dict(signal_id='synthetic', ticker='AAA', horizon_sessions=5,
        status='AVAILABLE', observed_at='2026-10-16T20:00:00Z', stock_return=.1, spy_return=-.02)])
    view = overview_html(value)
    assert 'Recorded evidence is available' in view
    assert 'no cohort-wide performance is inferred' in view
    assert 'Performance is pending' not in view
    assert '<strong>3</strong>' in view


def test_recorded_missing_or_unpaired_observations_do_not_claim_performance_available():
    for rows in ([], [dict(status='MISSING_PRICE')], [dict(signal_id='synthetic', ticker='AAA',
            horizon_sessions=5, status='AVAILABLE', observed_at='2026-10-16T20:00:00Z',
            stock_return=.1, spy_return=None)]):
        view = overview_html(dict(report(3), rows=rows))
        assert '<strong>Unavailable</strong>' in view
        assert 'Recorded observation counts do not establish usable paired returns' in view
        assert 'Recorded evidence is available' not in view
        assert '<strong>Per signal</strong>' not in view
        assert '<strong>3</strong>' in view


def test_pending_horizons_with_missing_prices_remain_pending_not_zero():
    view = overview_html(dict(report(3), rows=[dict(status='MISSING_PRICE'),
        dict(status='NOT_MATURED_OR_NOT_OBSERVED')]))
    assert '<strong>Pending</strong>' in view
    assert 'Performance comparison pending' in view
    assert '0%' not in view


def test_signal_directory_preserves_original_dates_and_never_calls_reference_an_entry():
    from ui.report_card_overview import signal_directory_html
    view = signal_directory_html([dict(signal_id='signal-a', ticker='AAA',
        signal_timestamp='2026-10-08T03:20:18Z', reference_price=100,
        reference_price_timestamp='2026-10-06T00:00:00Z', observation_count=0)])
    assert 'Oct 08, 2026' in view and 'Oct 06, 2026' in view
    assert '$100.00' in view and 'Pending' in view
    assert 'not an executable entry' in view
    assert '0%' not in view and 'Successful' not in view


def test_signal_directory_escapes_identity_and_preserves_unavailable_prices():
    from ui.report_card_overview import signal_directory_html
    view = signal_directory_html([dict(signal_id='signal-a', ticker='<script>bad</script>',
        reference_price=None, observation_count=0)])
    assert '<script>' not in view and '&lt;script&gt;' in view
    assert 'Unavailable' in view and '$0.00' not in view


def test_signal_picker_binds_exact_selected_identity_without_ledger_access():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_string('''
from ui.report_card_overview import render_signal_directory
from ui.internal_report_card import open_report_card_detail
render_signal_directory([
 {'signal_id':'original-a','ticker':'AAA','observation_count':0},
 {'signal_id':'original-b','ticker':'BBB','observation_count':0}], on_open=open_report_card_detail)
''').run()
    assert not app.exception
    app.selectbox(key='report_card_directory_selection').select('original-b').run()
    app.button[0].click().run()
    assert not app.exception
    assert app.session_state['report_card_selected_signal_id'] == 'original-b'
    assert app.session_state['report_card_view_mode'] == 'DETAIL'


def test_horizon_coverage_preserves_pending_counts_and_escapes_labels():
    from ui.report_card_overview import horizon_coverage_html
    view = horizon_coverage_html({1: {'available': 0, 'unavailable': 0, 'pending': 20},
                                  '<unsafe>': {'available': 2, 'unavailable': 1, 'pending': 17}})
    assert '<td>20</td>' in view and '<td>17</td>' in view
    assert '&lt;unsafe&gt;' in view and '<unsafe>' not in view
    assert 'pending is not a measured return' in view
    assert '0%' not in view and '$0' not in view


def test_registration_is_distinct_from_signal_and_reference_dates():
    from ui.report_card_overview import signal_directory_html
    view = signal_directory_html([dict(signal_id='synthetic', ticker='AAA',
        registered_at='2026-10-07T23:20:18-04:00',
        signal_timestamp='2026-10-06T00:00:00Z', reference_price=100,
        reference_price_timestamp='2026-10-05T20:00:00Z')])
    assert 'Oct 08, 2026 03:20:18 UTC' in view
    assert 'Oct 06, 2026' in view and 'Oct 05, 2026' in view
    assert 'Original signal date' in view
    assert 'not proof of customer publication' in view
    assert 'do not establish an executable entry' in view


def test_missing_or_naive_registration_never_falls_back_to_original_signal_date():
    from ui.report_card_overview import signal_directory_html
    for value in (None, '2026-10-08T03:20:18', 'invalid'):
        view = signal_directory_html([dict(signal_id='synthetic', ticker='AAA',
            registered_at=value, signal_timestamp='2026-10-06T00:00:00Z')])
        assert 'Registration unavailable' in view
        assert 'Oct 06, 2026' in view
        assert 'Oct 08, 2026' not in view


def test_benchmark_selects_only_paired_authoritative_rows_without_aggregation():
    from copy import deepcopy
    from ui.report_card_overview import benchmark_evidence
    original = dict(observation_count=1, rows=[dict(signal_id='signal-a', ticker='AAA', horizon_sessions=5,
                    status='AVAILABLE', observed_at='2026-10-16T20:00:00Z', stock_return=.1, spy_return=-.02)])
    before = deepcopy(original)
    result = benchmark_evidence(original)
    assert result['status'] == 'AVAILABLE'
    assert len(result['rows']) == 1
    assert result['rows'][0]['stock_return'] == .1 and result['rows'][0]['spy_return'] == -.02
    assert original == before
    result['rows'][0]['stock_return'] = 999
    assert original == before
    assert 'not a funded portfolio or cumulative return' in result['reason']


def test_benchmark_never_admits_withheld_missing_unpaired_or_duplicate_returns():
    from ui.report_card_overview import benchmark_evidence
    base = dict(signal_id='signal-a', ticker='AAA', horizon_sessions=5, status='AVAILABLE',
                observed_at='2026-10-16T20:00:00Z', stock_return=.1, spy_return=-.02)
    for change in ({'status':'METHODOLOGY_RESTRICTED'}, {'spy_return':None}, {'stock_return':True},
                   {'stock_return':float('nan')}, {'observed_at':''}, {'horizon_sessions':True}):
        assert benchmark_evidence(dict(observation_count=1, rows=[{**base, **change}]))['rows'] == ()
    assert benchmark_evidence(dict(observation_count=1, rows=[base, dict(base)]))['rows'] == ()
    for policy in ('VISIBILITY_ONLY_NO_RETURN_AUTHORITY', 'UNKNOWN_FUTURE_POLICY'):
        evidence = benchmark_evidence(dict(observation_count=1, rows=[base], performance_policy=policy))
        assert evidence['status'] == 'WITHHELD' and evidence['rows'] == ()


def _render_benchmark_case(case):
    from ui.report_card_overview import render_benchmark_panel
    render_benchmark_panel(case)


def test_actual_pending_benchmark_has_no_curve_or_invented_zero():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_function(_render_benchmark_case, kwargs={'case':dict(observation_count=0,rows=[])}).run()
    assert not app.exception
    assert app.selectbox(key='report_card_benchmark_horizon').options == [
        f'{h} trading sessions' for h in (1, 5, 21, 63, 126, 252)]
    app.selectbox(key='report_card_benchmark_horizon').select(252).run()
    rendered = '\n'.join(str(item.value) for item in app.markdown)
    assert 'data-atlas-benchmark-status="PENDING"' in rendered
    assert 'No performance curve is drawn' in rendered
    assert '0%' not in rendered
    assert not app.get('plotly_chart')


def test_actual_benchmark_chart_uses_exact_paired_values():
    import json
    from streamlit.testing.v1 import AppTest
    case = dict(observation_count=1, rows=[dict(signal_id='synthetic',ticker='AAA',horizon_sessions=5,
                status='AVAILABLE', observed_at='2026-10-16T20:00:00Z', stock_return=.1, spy_return=-.02)])
    app = AppTest.from_function(_render_benchmark_case,kwargs={'case':case}).run()
    assert not app.exception
    app.selectbox(key='report_card_benchmark_horizon').select(5).run()
    charts = app.get('plotly_chart')
    assert len(charts) == 1
    data = json.loads(charts[0].proto.spec)['data']
    assert data[0]['y'] == [.1] and data[1]['y'] == [-.02]
    assert data[0]['x'] == ['AAA · synthetic']


def test_signal_history_discloses_entry_and_registered_horizon_without_deriving_entry():
    from ui.report_card_overview import signal_directory_html
    view = signal_directory_html([dict(signal_id='synthetic', ticker='AAA', reference_price=100,
                                      registered_horizons=[1,5,21], observation_count=0)])
    assert 'Executable entry' in view and 'Not the reference price' in view
    assert '1, 5, 21' in view and 'SPY alignment: see detail' in view


def test_explicit_unknown_performance_policy_is_withheld_consistently():
    from ui.report_card_overview import benchmark_evidence
    value = dict(report(3), performance_policy="UNREVIEWED_FUTURE_POLICY")
    html = overview_html(value)
    assert benchmark_evidence(value)["status"] == "WITHHELD"
    assert "<strong>Withheld</strong>" in html
    assert "Recorded prices; performance withheld" in html
    assert "Recorded evidence is available" not in html
    assert "<strong>Per signal</strong>" not in html


def test_mobile_chart_shortens_labels_without_changing_full_signal_identity():
    import json
    from streamlit.testing.v1 import AppTest
    identity = "a" * 64
    case = dict(observation_count=1, rows=[dict(signal_id=identity, ticker="AAA", horizon_sessions=5,
                status="AVAILABLE", observed_at="2026-10-16T20:00:00Z", stock_return=.1, spy_return=-.02)])
    app = AppTest.from_function(_render_benchmark_case, kwargs={"case": case}).run()
    assert not app.exception
    app.selectbox(key="report_card_benchmark_horizon").select(5).run()
    spec = json.loads(app.get("plotly_chart")[0].proto.spec)
    assert spec["data"][0]["x"] == ["AAA · " + identity]
    assert spec["layout"]["xaxis"]["tickvals"] == ["AAA · " + identity]
    assert spec["layout"]["xaxis"]["ticktext"] == ["AAA · aaaaaaaa…"]
    assert spec["data"][0]["y"] == [.1]
    assert "%{x}" in spec["data"][0]["hovertemplate"]


def test_all_registered_horizons_work_when_pending_and_evidence_is_scoped():
    from streamlit.testing.v1 import AppTest
    from services.report_card import HORIZONS
    base = dict(signal_id='synthetic', ticker='AAA', observed_at='2026-10-16T20:00:00Z')
    rows = [dict(base, horizon_sessions=h, status='NOT_MATURED_OR_NOT_OBSERVED') for h in HORIZONS]
    rows[1].update(status='AVAILABLE', stock_return=.1, spy_return=-.02)
    rows[2].update(status='MISSING_PRICE')
    app = AppTest.from_function(_render_benchmark_case,kwargs={'case':dict(observation_count=2,rows=rows)}).run()
    assert app.selectbox[0].options == [f'{h} trading sessions' for h in HORIZONS]
    for horizon, status in [(1,'PENDING'), (5,'AVAILABLE'), (21,'UNAVAILABLE'), (252,'PENDING'), (5,'AVAILABLE')]:
        app.selectbox(key='report_card_benchmark_horizon').select(horizon).run()
        assert not app.exception
        assert f'data-atlas-benchmark-status="{status}"' in '\n'.join(str(x.value) for x in app.markdown)
        assert len(app.get('plotly_chart')) == int(status == 'AVAILABLE')
    withheld = dict(observation_count=2,rows=rows,performance_policy='VISIBILITY_ONLY_NO_RETURN_AUTHORITY')
    app = AppTest.from_function(_render_benchmark_case,kwargs={'case':withheld}).run()
    for horizon in HORIZONS:
        app.selectbox[0].select(horizon).run()
        assert not app.get('plotly_chart')
        assert 'WITHHELD' in '\n'.join(str(x.value) for x in app.markdown)


def test_history_selection_is_stable_and_does_not_modify_original_records():
    from copy import deepcopy
    from ui.report_card_overview import select_history
    signals = [dict(signal_id='b',ticker='BBB',observation_count=0,registered_at='2026-10-08T10:00:00Z'),
               dict(signal_id='a2',ticker='AAA',observation_count=2,registered_at=None),
               dict(signal_id='a1',ticker='AAA',observation_count=0,registered_at='2026-10-08T09:00:00Z')]
    before = deepcopy(signals)
    def ids(**kwargs): return [x['signal_id'] for x in select_history(signals,**kwargs)]
    assert ids() == ['b','a2','a1']
    assert ids(order='Ticker A–Z') == ['a2','a1','b']
    assert ids(order='Registered newest') == ['b','a1','a2']
    assert ids(order='Registered oldest') == ['a1','b','a2']
    assert ids(query=' aaa ',observations='Pending') == ['a1']
    assert ids(observations='Recorded') == ['a2']
    assert ids(query='absent') == []
    assert signals == before


def test_history_controls_clear_stale_selection_and_open_exact_filtered_identity():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_string('''
from ui.report_card_overview import render_signal_directory
from ui.internal_report_card import open_report_card_detail
render_signal_directory([
 {'signal_id':'same-old','ticker':'AAA','observation_count':0},
 {'signal_id':'same-new','ticker':'AAA','observation_count':1},
 {'signal_id':'other','ticker':'BBB','observation_count':0}], on_open=open_report_card_detail)
''').run()
    app.selectbox(key='report_card_directory_selection').select('same-new').run()
    app.selectbox(key='report_card_history_observations').select('Pending').run()
    assert app.selectbox(key='report_card_directory_selection').value == 'same-old'
    app.text_input[0].input('absent').run()
    assert not app.button and not app.exception
    app.text_input[0].input('bbb').run()
    assert app.selectbox(key='report_card_directory_selection').value == 'other'
    app.button[0].click().run()
    assert app.session_state['report_card_selected_signal_id'] == 'other'
    app.text_input[0].input('').run()
    app.selectbox(key='report_card_history_order').select('Ticker Z–A').run()
    assert app.selectbox(key='report_card_directory_selection').value == 'other'
    assert not app.exception
