from agents.r3_ai_first_acceptance import (
    REQUIRED_HOME_STATES,
    REQUIRED_VIEWPORTS,
    human_acceptance_status,
    narrative_distinctness,
    validate_readability,
    validate_screenshot_manifest,
    validate_source_grounding,
    validate_usefulness,
)


def _manifest(sha="abc"):
    rows = []
    for state in REQUIRED_HOME_STATES:
        for viewport, (width, height) in REQUIRED_VIEWPORTS.items():
            slug = f"{state}-{viewport}"
            rows.append({"state": state, "viewport": viewport, "source_sha": sha,
                         "width": width, "height": height, "path": f"{slug}.png",
                         "sha256": f"sha-{slug}", "horizontal_overflow": False,
                         "exception": False})
    return rows


def test_manifest_requires_original_evidence_at_1440_390_and_360():
    rows = [r for r in _manifest() if r["viewport"] != "mobile_360"]
    failures = validate_screenshot_manifest(rows, exact_sha="abc")
    assert any("mobile_360" in item for item in failures)


def test_manifest_rejects_wrong_sha_dimensions_and_duplicate_capture():
    rows = _manifest()
    rows[0]["source_sha"] = "wrong"
    rows[1]["width"] = 999
    rows[2]["sha256"] = rows[3]["sha256"]
    failures = validate_screenshot_manifest(rows, exact_sha="abc")
    assert any(item.startswith("SOURCE_SHA_MISMATCH") for item in failures)
    assert any(item.startswith("DIMENSION_MISMATCH") for item in failures)
    assert "SCREENSHOT_SHA256_NOT_UNIQUE" in failures


def test_grounding_requires_known_field_and_evidence_ids_for_every_claim():
    good = [{"text": "Fair Value is $346.05.", "field_ids": ["fair_value"],
             "evidence_ids": ["ev-fv"]}]
    assert validate_source_grounding(good, allowed_field_ids={"fair_value"},
                                     allowed_evidence_ids={"ev-fv"}) == []
    bad = [{"text": "Revenue grew 83%.", "field_ids": [], "evidence_ids": ["made-up"]}]
    failures = validate_source_grounding(bad, allowed_field_ids={"revenue_growth"},
                                         allowed_evidence_ids={"ev-revenue"})
    assert "UNGROUNDED_CLAIM:0" in failures
    assert "UNKNOWN_EVIDENCE_ID:0" in failures
    assert "UNGROUNDED_NUMERIC_CLAIM:0" in failures


def test_distinctness_rejects_ticker_copy_and_accepts_specific_narratives():
    copied = {"NVDA": "Strong growth supports the opportunity despite valuation risk.",
              "AVT": "Strong growth supports the opportunity despite valuation risk."}
    assert narrative_distinctness(copied)[1]
    specific = {"NVDA": "Accelerator demand supports growth; watch supply constraints.",
                "AVT": "Inventory normalization supports distribution margins; watch working capital."}
    assert narrative_distinctness(specific)[1] == []


def test_readability_and_usefulness_fail_closed():
    assert "SENTENCE_TOO_LONG" in validate_readability("word " * 40 + ".")
    record = {"bottom_line": "One sentence.", "reasons": ["r1"], "risks": ["r"],
              "strengthen": "s", "weaken": "w", "invalidate": "i",
              "what_to_watch": "watch", "freshness": "dated"}
    assert validate_usefulness(record) == []
    del record["invalidate"]
    assert "USEFULNESS_FIELD_MISSING:invalidate" in validate_usefulness(record)


def test_human_protocol_never_converts_placeholders_into_acceptance():
    placeholders = [{"participant_id": f"P{i}"} for i in range(1, 6)]
    status, failures = human_acceptance_status(placeholders)
    assert status == "NOT_RUN_OR_INCOMPLETE"
    assert failures
    completed = [{"participant_id": f"P{i}", "completed": True,
                  "evidence_ref": f"session-{i}.md", "distinctness": 4,
                  "readability": 4, "usefulness": 4} for i in range(1, 6)]
    status, failures = human_acceptance_status(completed)
    assert status == "EVIDENCE_COMPLETE_REVIEW_REQUIRED"
    assert failures == []
