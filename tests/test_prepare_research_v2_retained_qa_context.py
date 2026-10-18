from pathlib import Path

from scripts.prepare_research_v2_retained_qa_context import prepare


def test_retained_context_is_explicitly_zero_provider_and_unenriched(tmp_path: Path) -> None:
    output = tmp_path / "context.json"
    payload = prepare(("NVDA", "MSFT", "AVT"), output)
    assert payload["scope"] == "RETAINED_EVIDENCE_ONLY"
    assert payload["provider_calls"] == 0
    assert payload["tickers"] == {"NVDA": {}, "MSFT": {}, "AVT": {}}
    assert output.is_file()
