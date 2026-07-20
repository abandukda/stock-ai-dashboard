from core.pipeline_v102 import build_canonical_pipeline

def row(ticker, tech, finance, analyst):
    return {
        "ticker":ticker,"company":ticker,"sector":"Technology",
        "industry":"Software","quote_type":"EQUITY","current_price":100,
        "analyst_target_mean":120,"finance_agent_score":finance,
        "analyst_support_score":analyst,
        "ai_committee":{"Technical Agent":{"score":tech}},
        "investment_thesis":"Thesis","guidance":"Guidance",
    }

def test_scores_and_confidence_vary():
    model = build_canonical_pipeline([
        row("A",90,85,88), row("B",60,55,65), row("C",75,70,80)
    ])
    scores = [r["opportunity_score"] for r in model["ranked_candidates"]]
    confidence = [r["confidence_pct"] for r in model["ranked_candidates"]]
    assert len(set(scores)) > 1
    assert len(set(confidence)) > 1

def test_percentile_matches_rank():
    model = build_canonical_pipeline([
        row("A",90,85,88), row("B",60,55,65)
    ])
    assert model["ranked_candidates"][0]["top_percentile_text"] == "Top 50%"

def test_incomplete_defaults_are_not_ranked():
    model = build_canonical_pipeline([{"ticker":"EMPTY","quote_type":"EQUITY"}])
    assert model["ranked_candidates"] == []
