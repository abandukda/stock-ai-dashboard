from services.evidence_lineage_governance import disallowed_lineage_paths
from services.publication_governance import build_manifest


def _row(*, allowed=True, source="FMP"):
    return {
        "ticker": "TEST", "forward_eps_source": source,
        "canonical_investment_evaluation": {"methodology_version": "FROZEN"},
        "publication_certification": {
            "certification_state": "CERTIFIED" if allowed else "REVIEW_REQUIRED",
            "customer_publication_allowed": allowed,
        },
    }


def test_lineage_scanner_finds_provider_provenance_but_not_incidental_text():
    assert disallowed_lineage_paths({"forward_eps_source": "YAHOO_INFO"}) == ["$.forward_eps_source"]
    assert disallowed_lineage_paths({"description": "Yahoo was mentioned in prose"}) == []


def test_manifest_fails_disallowed_lineage_and_reconciles_publication_counts():
    rows = [_row(source="YAHOO_INFO"), _row(allowed=False)]
    manifest = build_manifest(rows, run_id="r1", generated_at="2026-09-08T00:00:00Z",
                              artifact_payloads={"market_full_scan.json": rows}, provider_status={"status": "AVAILABLE"})
    assert manifest["published_yahoo_lineage_count"] == 1
    assert manifest["publication_gate_status"] == "FAIL"
    assert manifest["publishable_count"] == manifest["customer_publication_count"] == 1
    assert manifest["withheld_count"] == 1


def test_post_migration_cache_key_prevents_legacy_cache_reuse():
    from services.twelve_data_trial_intelligence import acquire_twelve_trial_dossiers

    class Response:
        def raise_for_status(self): pass
        def json(self): return {"statistics": {}}

    calls = []
    legacy_cache = {("TWELVE_DATA_INTERNAL_TRIAL_INTELLIGENCE_V1", "MU", "statistics"):
                    {"status": "AVAILABLE", "provider": "YAHOO_INFO"}}
    result = acquire_twelve_trial_dossiers(
        ["MU"], endpoints=("statistics",), evidence_cache=legacy_cache,
        get=lambda *args, **kwargs: calls.append(1) or Response(),
        secrets={"TWELVE_DATA_API_KEY": "secret"}, environ={"ATLAS_DATA_MODE": "INTERNAL_TRIAL"},
    )
    assert result["provider_calls"] == 1 and result["cache_hits"] == 0
