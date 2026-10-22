"""Provider-free monitor normalization. No credentials, network or mutation."""
import hashlib
import json


def material_state(payload):
    """Ignore volatile timing/log URLs; retain every material status transition."""
    return {
        'main_sha': payload.get('main_sha'),
        'runs': sorted([{'id': r['id'], 'head_sha': r['head_sha'], 'status': r['status'],
                         'conclusion': r.get('conclusion')} for r in payload.get('runs', [])], key=lambda r: r['id']),
        'pulls': sorted([{'number': p['number'], 'head_sha': p['head']['sha'],
                          'draft': p.get('draft', False)} for p in payload.get('pulls', [])], key=lambda p: p['number']),
        # Missing authority is visible, never interpreted as a pass or an online runner.
        'unavailable': ['runner_admin_state', 'environment_approvals', 'authenticated_live_source_sha',
                        'current_source_host_ledger', 'current_certified_data'],
    }


def receipt(payload, previous_fingerprint=''):
    state = material_state(payload)
    digest = hashlib.sha256(json.dumps(state, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'schema': 'ATLAS_MONITOR_REVIEW_V1', 'state': state, 'fingerprint': digest,
            'material_change': digest != previous_fingerprint, 'notifications_sent': 0,
            'activation': 'MANUAL_REVIEW_ONLY', 'provider_calls': 0, 'production_writes': 0}
