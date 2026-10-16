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
    install = source.index('Install and verify pinned certification dependency')
    certification = source.index('python3 scripts/certify_incremental_buy_now.py')
    assert install < certification
    assert 'python3 -m pip install --disable-pip-version-check --no-deps ijson==3.5.1' in source
    assert "assert version('ijson') == '3.5.1'" in source
    assert 'import services.incremental_publication_bridge' in source
    assert 'python3 scripts/certify_incremental_buy_now.py --help >/dev/null' in source
    assert '--provider-free-replay' in source
    assert '--replay-retained-records' in source
    assert 'resolve_incremental_retained_records.py' in source
    assert '--artifact-root "$RUNNER_TEMP/membership"' in source
    assert "assert r['source_row_count'] == 6033" in source
    assert "assert r['selected_row_count'] == 1298" in source
    assert "assert r['excluded_row_count'] == 4735" in source
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
    assert 'expected_duplicate_claim.stderr' in source
    assert "grep -q 'INCREMENTAL_ACQUISITION_CLAIM_ALREADY_CONSUMED'" in source
