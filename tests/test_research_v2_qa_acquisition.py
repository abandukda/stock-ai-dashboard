from pathlib import Path

from scripts import acquire_research_v2_qa_context as acquisition


class _Record:
    def __init__(self, capability, ticker):
        self.capability, self.ticker = capability, ticker

    def as_dict(self):
        return {
            "payload": {"capability": self.capability},
            "provenance": {
                "provider": "FINNHUB", "symbol": self.ticker,
                "raw_evidence_id": f"FINNHUB:{self.capability}:{self.ticker}",
            },
        }


class _Adapter:
    calls = []

    def __init__(self, *args, **kwargs):
        pass

    def fetch(self, capability, ticker, **kwargs):
        self.calls.append((capability, ticker, kwargs))
        return _Record(capability, ticker)


def test_bounded_acquisition_has_exact_call_count_and_shared_spy(monkeypatch, tmp_path: Path):
    _Adapter.calls = []
    monkeypatch.setattr(acquisition, "FinnhubShadowAdapter", _Adapter)
    result = acquisition.acquire(("NVDA", "MSFT", "AVT"), tmp_path / "context.json")
    assert result["scope"] == "QA_ONLY"
    assert result["provider_calls"] == 22
    assert len(_Adapter.calls) == 22
    assert sum(1 for _, ticker, _ in _Adapter.calls if ticker == "SPY") == 1
    assert all(row["spy_historical_ohlcv"] == result["tickers"]["NVDA"]["spy_historical_ohlcv"] for row in result["tickers"].values())


def test_qa_acquisition_never_requests_live_quote(monkeypatch, tmp_path: Path):
    _Adapter.calls = []
    monkeypatch.setattr(acquisition, "FinnhubShadowAdapter", _Adapter)
    acquisition.acquire(("NVDA",), tmp_path / "context.json")
    assert not {capability for capability, _, _ in _Adapter.calls} & {"live_quote", "quote_us"}
