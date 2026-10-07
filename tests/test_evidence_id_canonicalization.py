from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from services.canonical_data_validation import CERTIFIED
from services.certified_customer_evaluation import _digest, _field
from services.publication_governance import _hash_payload


CANDIDATE_DIGEST = "c" * 64
ARTIFACT_NAMES = (
    "market_full_scan.json",
    "market_prescreen.json",
    "market_scan_state.json",
    "recovery_scan.json",
    "etf_scan.json",
    "total_market_universe.json",
    "discovery_candidate_pool.json",
    "full_evaluation_pool.json",
)


def _certified_field(evidence_ids):
    return _field(
        "atlas_fair_value",
        346.05,
        status=CERTIFIED,
        source="FINNHUB",
        evidence_ids=evidence_ids,
        as_of="2026-10-06T20:31:25-04:00",
        currency="USD",
        unit="PER_SHARE",
        snapshot_id="snapshot",
    )


def _publication_digest(evidence_ids) -> tuple[str, dict[str, str]]:
    field = _certified_field(evidence_ids)
    protected = {
        "ticker": "NVDA",
        "action": "BUY_NOW",
        "opportunity": 85.96,
        "decision_confidence": 87.46,
        "ranking": 1,
        "atlas_fair_value": field,
        "expected_return": 0.8596,
        "entry": 180.0,
        "targets": [300.0, 346.05],
        "stop": 160.0,
        "sizing": "STANDARD",
        "customer_publication_allowed": True,
    }
    payloads = {
        name: ([protected] if name not in {"market_scan_state.json", "total_market_universe.json"}
               else {"candidate_digest": CANDIDATE_DIGEST, "record": protected})
        for name in ARTIFACT_NAMES
    }
    hashes = {name: _hash_payload(payload) for name, payload in payloads.items()}
    return _digest({"artifact_hashes": hashes, "candidate_digest": CANDIDATE_DIGEST}), hashes


def test_empty_singleton_repeated_and_differently_ordered_evidence_ids():
    assert _certified_field(())["evidence_ids"] == ()
    assert _certified_field(["only"])["evidence_ids"] == ("only",)
    assert _certified_field(["b", "a", "b"])["evidence_ids"] == ("a", "b", "b")
    assert _certified_field(["b", "a"])["evidence_ids"] == _certified_field(["a", "b"])["evidence_ids"]


def test_evidence_order_is_semantically_stable_but_membership_changes_digest():
    first = _certified_field(["evidence:b", "evidence:a"])
    second = _certified_field(["evidence:a", "evidence:b"])
    changed = _certified_field(["evidence:a", "evidence:c"])

    assert first == second
    assert _digest(first) == _digest(second)
    assert _digest(first) != _digest(changed)
    assert set(first["evidence_ids"]) == {"evidence:a", "evidence:b"}


def test_python_hash_seed_does_not_change_canonical_evidence_order():
    root = Path(__file__).resolve().parents[1]
    code = """
import json
from services.canonical_data_validation import CERTIFIED
from services.certified_customer_evaluation import _field
ids = {"FINNHUB:PRICE", "FINNHUB:ESTIMATE", "FINNHUB:FUNDAMENTALS"}
field = _field("value", 1, status=CERTIFIED, source="FINNHUB", evidence_ids=ids,
               as_of="2026-10-06T20:31:25-04:00", snapshot_id="snapshot")
print(json.dumps(field["evidence_ids"]))
"""
    outputs = set()
    for seed in ("1", "2", "17", "101"):
        env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(root)}
        outputs.add(subprocess.check_output([sys.executable, "-c", code], cwd=root, env=env, text=True).strip())
    assert outputs == {'["FINNHUB:ESTIMATE", "FINNHUB:FUNDAMENTALS", "FINNHUB:PRICE"]'}


def test_identical_semantic_publication_has_stable_eight_artifact_hashes():
    first_digest, first_hashes = _publication_digest(["evidence:b", "evidence:a"])
    second_digest, second_hashes = _publication_digest(["evidence:a", "evidence:b"])

    assert set(first_hashes) == set(ARTIFACT_NAMES)
    assert first_hashes == second_hashes
    assert first_digest == second_digest


def test_evidence_membership_changes_publication_digest_without_changing_candidate():
    baseline, _ = _publication_digest(["evidence:a", "evidence:b"])
    changed, _ = _publication_digest(["evidence:a", "evidence:c"])

    assert baseline != changed
    assert CANDIDATE_DIGEST == "c" * 64


def test_protected_investment_values_are_not_changed_by_canonicalization():
    field = _certified_field(["evidence:b", "evidence:a"])

    assert field["value"] == 346.05
    assert field["certification_status"] == CERTIFIED
    assert field["provider"] == "FINNHUB"
    assert field["currency"] == "USD"
    assert field["unit"] == "PER_SHARE"
    assert field["snapshot_id"] == "snapshot"
