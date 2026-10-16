from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_manual_claim_does_not_enable_daily_scheduler():
    acquire=(ROOT/'.github/workflows/atlas_finnhub_incremental_acquisition.yml').read_text()
    daily=(ROOT/'.github/workflows/atlas_daily_incremental_buy_now.yml').read_text()
    assert 'ATLAS_INCREMENTAL_MANUAL_ACQUIRE_ENABLED' in acquire
    assert 'ATLAS_DAILY_BUY_NOW_LIVE_ENABLED: ${{ vars.' not in acquire
    assert 'test "$ATLAS_DAILY_BUY_NOW_LIVE_ENABLED" = false' in daily
    assert 'claims-root "$ATLAS_INCREMENTAL_CHECKPOINT_ROOT/claims"' in acquire
    assert 'Finalize consumed claim without reopening it' in acquire

def test_workflow_binds_unique_claim_inputs():
    source=(ROOT/'.github/workflows/atlas_finnhub_incremental_acquisition.yml').read_text()
    for required in ('claim_id:', 'claim_scope_sha256:', 'manual_enablement:',
                     '--claim-id', '--claim-scope-sha256'):
        assert required in source
