import importlib.util
import sys
import types
from pathlib import Path

cache = types.ModuleType("services.research_cache")
cache.load_cached_research = lambda *a, **k: None
cache.save_cached_research = lambda *a, **k: None
services = types.ModuleType("services")
sys.modules.setdefault("services", services)
sys.modules["services.research_cache"] = cache

yf = types.ModuleType("yfinance")
yf.Ticker = lambda *a, **k: None
yf.download = lambda *a, **k: None
sys.modules["yfinance"] = yf

requests = types.ModuleType("requests")
requests.get = lambda *a, **k: None
sys.modules["requests"] = requests

path = Path(__file__).parents[1] / "engines" / "live_research_engine.py"
spec = importlib.util.spec_from_file_location("live_engine_test", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_fair_value_populates_with_analyst_target():
    result = module._fair_value_complete(
        100.0,
        {"forwardEps": 5.0},
        {"Revenue Growth": 12.0, "Earnings Growth": 15.0, "Operating Margin": 25.0, "Forward PE": 20.0},
        {"analyst_target_mean": 130.0, "analyst_target_low": 110.0, "analyst_target_high": 150.0},
    )
    assert result["atlas_fair_value"] is not None
    assert result["expected_return_pct"] is not None
    assert result["fair_value_confidence"] >= 55


def test_fair_value_stays_unavailable_when_no_legitimate_inputs():
    result = module._fair_value_complete(100.0, {}, {}, {})
    assert result["atlas_fair_value"] is None
    assert result["Atlas Fair Value"] is None
    assert result["fair_value_status"] == "Insufficient valuation evidence"
