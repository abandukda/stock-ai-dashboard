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
    view = overview_html(report(3))
    assert 'Recorded evidence is available' in view
    assert 'no cohort-wide performance is inferred' in view
    assert 'Performance is pending' not in view
    assert '<strong>3</strong>' in view


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
    app.selectbox[0].select('original-b').run()
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
