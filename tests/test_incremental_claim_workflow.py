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


def test_protected_rehearsal_executes_full_entrypoint_without_credentials():
    source=(ROOT/'.github/workflows/atlas_finnhub_incremental_acquisition.yml').read_text()
    assert '--provider-free-replay' in source
    assert '--replay-retained-records' in source
    assert '--retained-technical-root "$RUNNER_TEMP/retained-shards"' in source
    assert 'pattern: atlas-finnhub-full-shard-*-${{ inputs.membership_run_id }}' in source
    assert "assert len(c['receipts']) == 2596" in source
    assert "assert r['symbol_count'] == 1298" in source
    assert "assert r['unaccounted_publication_records'] == 0" in source
    assert "assert r['publishable_count'] == 1223" in source
    assert "assert r['withheld_count'] == 75" in source
    assert "assert r['production_writes'] == 0" in source
    assert 'ENABLE_ATLAS_INCREMENTAL_REPLAY_ONCE:' in source
    assert 'test -z "${FINNHUB_API_KEY:-}"' in source
