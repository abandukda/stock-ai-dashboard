import io
from pathlib import Path
import tarfile

from scripts.finnhub_bulk_sample_audit import DATASETS, SYMBOLS, inspect_archive


def test_bulk_sample_scope_is_bounded_to_requested_datasets_and_symbols():
    assert DATASETS == ("stock_profile", "stock_financials", "stock_metric", "historical_market_cap", "stock_ohlc1d")
    assert SYMBOLS == {"AAPL", "MSFT", "NVDA", "WMT", "IBM", "F", "PFE", "TSLA", "ORCL", "COST", "GM", "AMGN"}


def test_archive_inspection_preserves_missing_values_and_filters_symbols(tmp_path: Path):
    path = tmp_path / "sample.tar"
    payload = b"symbol,value,note\nAAPL,0,N/A\nZZZZ,12,ignored\nMSFT,,null\n"
    with tarfile.open(path, "w") as archive:
        info = tarfile.TarInfo("rows.csv"); info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    result = inspect_archive(path, "stock_metric")
    assert set(result["samples"]) == {"AAPL", "MSFT"}
    assert result["samples"]["AAPL"][0]["value"] == "0"
    assert result["samples"]["MSFT"][0]["value"] == ""
    assert result["sample_sentinel_counts"]["zero"] == 1
    assert result["sample_sentinel_counts"]["blank"] == 1
    assert result["sample_sentinel_counts"]["na"] == 1
