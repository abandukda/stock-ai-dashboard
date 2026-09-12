from copy import deepcopy

from services.targeted_revalidation import assess_targeted_revalidation


def _evaluation(*, price=100, action="WAIT_FOR_CONFIRMATION", digest="old", certified=False):
    result = {
        "decision_digest": digest,
        "evaluated_at": "2026-09-11T20:00:00Z",
        "market_snapshot": {
            "price": price, "provider": "TWELVE_DATA", "provider_timestamp": "2026-09-12T14:31:00Z",
            "market_session": "REGULAR", "fresh_current_price": True, "evidence_id": f"TD-{price}",
        },
        "guidance": {"state": action},
        "trade_plan": {"entry_low": 95, "entry_high": 105, "stop_loss": 90, "target_1": 120, "risk_reward": 2},
    }
    if certified:
        result["publication_certification"] = {"customer_publication_allowed": True}
        result["certified_customer_evaluation"] = {"customer_publication_allowed": True}
    return result


def test_price_overlay_stays_current_when_canonical_dependencies_do_not_change():
    prior, current = _evaluation(), _evaluation(price=101, digest="new")
    before = deepcopy(prior)
    result = assess_targeted_revalidation(prior, current)
    assert result["state"] == "CURRENT"
    assert result["live_price"] == 101
    assert result["price_source"] == "TWELVE_DATA"
    assert prior == before


def test_material_entry_change_fails_safe_until_revalidation_is_certified():
    result = assess_targeted_revalidation(_evaluation(), _evaluation(price=108, digest="new"))
    assert result["state"] == "REVALIDATION_REQUIRED"
    assert "ENTRY_RELATIONSHIP_CHANGED" in result["trigger_reasons"]
    assert "revalidating" in result["customer_message"].lower()


def test_certified_new_snapshot_can_be_published_as_revalidated():
    result = assess_targeted_revalidation(
        _evaluation(), _evaluation(price=108, digest="new", action="WAIT_FOR_ENTRY", certified=True),
    )
    assert result["state"] == "REVALIDATED"
    assert result["new_decision_digest"] == "new"
    assert "CANONICAL_ACTION_CHANGED" in result["trigger_reasons"]


def test_missing_live_price_is_explicitly_temporarily_unavailable():
    current = _evaluation()
    current["market_snapshot"]["price"] = None
    result = assess_targeted_revalidation(_evaluation(), current)
    assert result["state"] == "TEMPORARILY_UNAVAILABLE"
    assert result["live_price"] is None


def test_home_uses_live_price_overlay_without_mutating_certified_decision():
    import json
    from pathlib import Path
    from engines.home_guidance_story_v1 import build_home_guidance_candidate

    row = next(
        item for item in json.loads(Path("market_full_scan.json").read_text())
        if (item.get("publication_certification") or {}).get("customer_publication_allowed") is True
    )
    persisted = row["canonical_investment_evaluation"]
    current = deepcopy(persisted)
    certified_price = float(row["certified_customer_evaluation"]["fields"]["price"]["value"])
    live_price = round(certified_price + 0.01, 2)
    current["market_snapshot"] = {
        **dict(current.get("market_snapshot") or {}), "price": live_price,
        "provider": "TWELVE_DATA", "provider_timestamp": "2026-09-12T14:31:00Z",
        "fresh_current_price": True, "evidence_id": "TD-LIVE-1",
    }
    card = build_home_guidance_candidate(row, production_rank=1, current_evaluation=current)
    assert card["display_price"] == live_price
    assert card["last_known_price"] == certified_price
    assert card["price_as_of"] == "2026-09-12T14:31:00Z"
    assert card["atlas_expected_return"] == row["certified_customer_evaluation"]["fields"]["atlas_upside_pct"]["value"]
    expected = round((float(card["atlas_fair_value"]) / live_price - 1) * 100, 1)
    assert card["live_implied_upside_pct"] == expected
