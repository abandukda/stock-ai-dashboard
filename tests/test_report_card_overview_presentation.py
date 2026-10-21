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
