from pathlib import Path


def test_runtime_qa_contains_visual_formatting_rules():
    source = Path("agents/atlas_runtime_qa_v3.py").read_text(encoding="utf-8")
    for rule in (
        "UNEXPECTED_INLINE_CODE",
        "TYPOGRAPHY_INCONSISTENCY",
        "VERTICAL_CHARACTER_WRAP",
        "CARD_TEXT_OVERFLOW",
        "INCONSISTENT_CARD_HEIGHTS",
        "METRIC_VERTICAL_WRAP",
    ):
        assert rule in source


def test_runtime_qa_saves_page_screenshots():
    source = Path("agents/atlas_runtime_qa_v3.py").read_text(encoding="utf-8")
    assert "visual_{safe_name}.png" in source
    assert "full_page=True" in source
