from scripts.atlas_execution_monitor import receipt


def test_fingerprint_ignores_timing_but_detects_failed_run_and_source_change():
    p = {'main_sha': 'a'*40, 'runs': [{'id': 7, 'head_sha': 'a'*40, 'status': 'completed', 'conclusion': 'success'}]}
    a = receipt(p)
    assert a['material_change'] and a['notifications_sent'] == 0
    assert not receipt({**p, 'updated_at': 'later'}, a['fingerprint'])['material_change']
    p['runs'][0]['conclusion'] = 'failure'
    assert receipt(p, a['fingerprint'])['material_change']
    p['main_sha'] = 'b'*40
    assert receipt(p, a['fingerprint'])['material_change']


def test_order_is_irrelevant_and_unavailable_authorities_are_explicit():
    p = {'pulls': [{'number': 2, 'head': {'sha': 'a'}}, {'number': 1, 'head': {'sha': 'b'}}]}
    a = receipt(p)
    p['pulls'].reverse()
    assert receipt(p)['fingerprint'] == a['fingerprint']
    assert 'runner_admin_state' in a['state']['unavailable']
    assert a['activation'] == 'MANUAL_REVIEW_ONLY'
