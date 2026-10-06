from agents.visual_qa_certification_v2 import visual_same_snapshot_parity


def _row(ticker, action, fair_value, opportunity, confidence, *, publish=True):
    return {
        "ticker": ticker,
        "publication_certification": {"customer_publication_allowed": publish},
        "certified_customer_evaluation": {
            "customer_publication_allowed": publish,
            "decision": {"action": action, "opportunity": opportunity, "decision_confidence": confidence},
            "fields": {"atlas_fair_value": {"value": fair_value}},
            "digests": {"evaluation_snapshot_id": f"snapshot-{ticker}"},
        },
    }


def test_visual_parity_uses_structured_home_and_research_evidence():
    rows = [_row("NVDA", "BUY_NOW", 338.82, 86.68, 88.54),
            _row("MSFT", "BUY_NOW", 640.0, 80.0, 90.0),
            _row("AVT", "BUY_NOW", 70.0, 75.0, 82.0),
            _row("ZBRA", "BUY_NOW", 400.0, 70.0, 80.0, publish=False)]
    home = {"cards": [
        {"ticker": "NVDA", "action": "BUY_NOW", "opportunity": "86.68", "confidence": "88.54", "text": "ATLAS Fair Value $338.82 Opportunity 86.68 Confidence 88.54"},
        {"ticker": "MSFT", "action": "BUY_NOW", "opportunity": "80", "confidence": "90", "text": "ATLAS Fair Value $640.00 Opportunity 80 Confidence 90"},
        {"ticker": "AVT", "action": "BUY_NOW", "opportunity": "75", "confidence": "82", "text": "ATLAS Fair Value $70.00 Opportunity 75 Confidence 82"},
    ]}
    research = {ticker: {"text": text} for ticker, text in {
        "NVDA": "BUY NOW ATLAS Fair Value $338.82 Opportunity 86.68 Decision Confidence 88.54",
        "MSFT": "BUY NOW ATLAS Fair Value $640.00 Opportunity 80 Decision Confidence 90",
        "AVT": "BUY NOW ATLAS Fair Value $70.00 Opportunity 75 Decision Confidence 82",
    }.items()}
    result = visual_same_snapshot_parity(rows=rows, home_evidence=home, research_evidence=research,
                                         identity={"valid": True, "candidate_digest": "c", "publication_digest": "p", "candidate_source_sha": "s"},
                                         candidate_run_id="1")
    assert result["status"] == "PASS"
    assert result["tickers_checked"] == ["NVDA", "MSFT", "AVT"]
    assert result["withheld_publication_leakage"] == 0


def test_visual_parity_rejects_withheld_home_leak_and_missing_research_fact():
    rows = [_row("NVDA", "BUY_NOW", 338.82, 86.68, 88.54),
            _row("MSFT", "BUY_NOW", 640.0, 80.0, 90.0),
            _row("AVT", "BUY_NOW", 70.0, 75.0, 82.0),
            _row("ZBRA", "BUY_NOW", 400.0, 70.0, 80.0, publish=False)]
    home = {"cards": [{"ticker": ticker, "action": "BUY_NOW", "text": f"ATLAS Fair Value ${fv:.2f} Opportunity {opp} Confidence {conf}", "opportunity": opp, "confidence": conf}
                      for ticker, fv, opp, conf in (("NVDA",338.82,86.68,88.54),("MSFT",640,80,90),("AVT",70,75,82),("ZBRA",400,70,80))]}
    research = {"NVDA": {"text": "BUY NOW $338.82 Opportunity 86.68 Confidence 88.54"},
                "MSFT": {"text": "BUY NOW $640 Opportunity 80 Confidence 90"},
                "AVT": {"text": "BUY NOW $70 Opportunity 75"}}
    result = visual_same_snapshot_parity(rows=rows, home_evidence=home, research_evidence=research,
                                         identity={"valid": True}, candidate_run_id="1")
    assert result["status"] == "FAIL"
    assert result["withheld_publication_leakage"] == 1
