import json
from pathlib import Path

from agents.atlas_runtime_qa_v3 import home_runtime_authority_failures
from agents.runtime_qa_user_journeys_v40 import exact_research_authority_matches
from engines.home_guidance_story_v1 import load_exact_customer_inventory_with_status
from services.runtime_projection_contract import validate_runtime_projection


ROOT = Path(__file__).resolve().parents[1]


def _manifest():
    return json.loads((ROOT / "publication_manifest.json").read_text(encoding="utf-8"))


def _expectations():
    return json.loads((ROOT / "certification/runtime_projection_expectations_64c0a00a.json").read_text(encoding="utf-8"))


def test_bounded_projection_is_distinct_and_valid():
    manifest = _manifest()
    rows = json.loads((ROOT / "full_evaluation_pool.json").read_text(encoding="utf-8"))
    contract = manifest["runtime_projection_contract"]
    source_digest = manifest["artifact_hashes"]["full_evaluation_pool.json"]
    projection_digest = contract["runtime_projection"]["files"]["full_evaluation_pool.json"]["semantic_sha256"]
    assert source_digest != projection_digest
    assert validate_runtime_projection(rows, manifest, artifact_name="full_evaluation_pool.json") == (True, ())


def test_exact_home_loader_fails_closed_on_projection_mutation(tmp_path):
    manifest = _manifest()
    rows = json.loads((ROOT / "full_evaluation_pool.json").read_text(encoding="utf-8"))
    path = tmp_path / "full_evaluation_pool.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    loaded, valid, failures = load_exact_customer_inventory_with_status(path, manifest)
    assert valid and len(loaded) == 35 and failures == ()
    rows[0]["ticker"] = "MUTATED"
    path.write_text(json.dumps(rows), encoding="utf-8")
    assert load_exact_customer_inventory_with_status(path, manifest)[1:] == (
        False, ("RUNTIME_PROJECTION_DIGEST_MISMATCH", "RUNTIME_PROJECTION_REQUIRED_TICKERS_MISMATCH")
    )


def test_source_inventory_is_exact_21_11_10_and_no_withheld_leaks():
    contract = _manifest()["runtime_projection_contract"]
    source = contract["source_certification"]["inventory"]
    runtime = contract["runtime_projection"]
    assert (source["canonical_buy_now_count"], source["publishable_buy_now_count"], source["withheld_buy_now_count"]) == (21, 11, 10)
    assert runtime["withheld_customer_leakage"] == []
    assert set(source["withheld_buy_now"]).isdisjoint(runtime["deployed_inventory"]["customer_allowed"])


def test_home_markers_require_exact_identity_inventory_and_partitions():
    expected = _expectations()
    identity = expected["identity"]
    source = expected["source_inventory"]
    authority = {
        "candidate_digest": identity["candidate_digest"], "publication_digest": identity["publication_digest"],
        "source_sha": identity["source_sha"], "evidence_snapshot": identity["evidence_snapshot_at"],
    }
    inventory = {
        "canonical_count": "21", "publishable_count": "11", "withheld_count": "10",
        "canonical_tickers": ",".join(source["canonical_buy_now"]),
        "publishable_tickers": ",".join(source["publishable_buy_now"]),
        "withheld_tickers": ",".join(source["withheld_buy_now"]),
    }
    assert home_runtime_authority_failures(authority, inventory, expected) == []
    inventory["withheld_count"] = "9"
    assert home_runtime_authority_failures(authority, inventory, expected) == ["HOME_WITHHELD_COUNT_MISMATCH"]


def test_research_authority_checks_all_exact_fields():
    expected = _expectations()["expected_facts"]["NVDA"]
    actual = {key: str(value) if key != "action" else value for key, value in expected.items()}
    assert exact_research_authority_matches(actual, expected)
    actual["opportunity"] = "85.95"
    assert not exact_research_authority_matches(actual, expected)
