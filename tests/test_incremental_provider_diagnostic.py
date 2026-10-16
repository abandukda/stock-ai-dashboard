from scripts.diagnose_incremental_provider_record import classify


def test_failed_october_15_candle_replay_identifies_date_parameter_contract():
    result = classify({
        "capability": "historical_ohlcv", "endpoint": "/stock/candle", "symbol": "A",
        "parameters": {"resolution": "D", "from": "2026-10-15", "to": "2026-10-15"},
        "status_code": 400, "payload": {},
    }, session="2026-10-15")
    assert result["classified_cause"] == "INCORRECT_STOCK_CANDLE_DATE_PARAMETERS"
    assert result["provider_calls"] == result["production_writes"] == 0


def test_diagnostic_distinguishes_no_data_entitlement_and_schema():
    base = {"capability": "historical_ohlcv", "endpoint": "/stock/candle", "symbol": "A",
            "parameters": {"resolution": "D", "from": 1, "to": 2}}
    assert classify({**base, "status_code": 200, "payload": {"s": "no_data"}}, session="2026-10-15")["classified_cause"] == "VALID_PROVIDER_NO_DATA_RESPONSE"
    assert classify({**base, "status_code": 403, "payload": {}}, session="2026-10-15")["classified_cause"] == "ENTITLEMENT_OR_ENDPOINT_MISMATCH"
    assert classify({**base, "status_code": 200, "payload": []}, session="2026-10-15")["classified_cause"] == "PROVIDER_RESPONSE_SCHEMA_MISMATCH"
