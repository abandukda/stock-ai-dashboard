from pathlib import Path


def test_research_report_uses_consistent_prose_and_trade_cards():
    source = Path("ui/research_report_v2.py").read_text(encoding="utf-8")
    assert 'data-atlas-qa="narrative"' in source
    assert 'data-atlas-qa="trade-card"' in source
    assert "word-break: keep-all" in source
    assert "white-space: nowrap" in source
    assert "_clean_prose" in source
    assert '.replace("`", "")' in source


def test_entry_zone_is_not_rendered_with_streamlit_metric():
    source = Path("ui/research_report_v2.py").read_text(encoding="utf-8")
    assert 'c[1].metric("Entry Zone"' not in source
    assert '("Entry Zone", entry_zone, "entry-zone")' in source
