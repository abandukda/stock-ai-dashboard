from agents.ai_content_integrity_v3 import (
    audit_summary_collection,
    summary_similarity,
)


def test_duplicate_summaries_are_detected():
    records = [
        {"ticker": "AAA", "company": "Alpha", "ai_summary":
         "Alpha has strong fundamentals and attractive valuation with 20% upside."},
        {"ticker": "BBB", "company": "Beta", "ai_summary":
         "Beta has strong fundamentals and attractive valuation with 20% upside."},
    ]
    report = audit_summary_collection(records, similarity_threshold=75)
    assert report["duplicate_pairs"]


def test_different_summaries_have_lower_similarity():
    value = summary_similarity(
        "Revenue accelerated 24% after a cloud product launch.",
        "Debt increased and margins contracted after weak guidance.",
    )
    assert value < 75
