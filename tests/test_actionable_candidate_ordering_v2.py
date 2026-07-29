
import core.pipeline_v104 as pipeline


def test_verdict_priority_places_actionable_names_first(monkeypatch):
    source = {
        "A": {"opportunity_score": 90, "committee_verdict": "AVOID"},
        "B": {"opportunity_score": 70, "committee_verdict": "BUY_NOW"},
        "C": {"opportunity_score": 75, "committee_verdict": "ACCUMULATE"},
    }

    def fake_score(raw):
        ticker = raw["ticker"]
        return {
            "ticker": ticker,
            "company": ticker,
            "sector": "Technology",
            "eligible": True,
            "opportunity_score": source[ticker]["opportunity_score"],
            "component_coverage_pct": 80,
            "components": {},
        }

    def fake_confidence(item):
        return {"confidence_pct": 70}

    def fake_committee(item):
        return {
            "committee_verdict": source[item["ticker"]]["committee_verdict"],
            "committee_ready": True,
        }

    monkeypatch.setattr(pipeline, "score_stock", fake_score)
    monkeypatch.setattr(pipeline, "calibrate_v103_confidence", fake_confidence)
    monkeypatch.setattr(pipeline, "build_committee_verdict", fake_committee)

    result = pipeline.build_v104_pipeline(
        [{"ticker": "A"}, {"ticker": "B"}, {"ticker": "C"}]
    )
    assert [r["ticker"] for r in result["ranked_candidates"]] == ["B", "C", "A"]
    assert [r["ticker"] for r in result["research_candidates"]] == ["B", "C"]
