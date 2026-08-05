import asyncio
from pathlib import Path

from agents.code_contract_mapper_v3 import discover_navigation_from_app
from agents.atlas_runtime_qa_v3 import _known_navigation_visible


class FakeLocator:
    def __init__(self, count):
        self._count = count

    async def count(self):
        return self._count


class FakeScope:
    def __init__(self, matched_label="Home"):
        self.matched_label = matched_label
        self.frames = []
        self.main_frame = object()

    def get_by_role(self, role, name=None, exact=None):
        return FakeLocator(1 if role == "button" and name == self.matched_label else 0)

    def get_by_text(self, text, exact=None):
        return FakeLocator(0)


def test_navigation_detection_does_not_create_async_generator_error():
    result = asyncio.run(_known_navigation_visible(FakeScope()))
    assert result == ["Home"]


def test_contract_mapper_handles_apostrophes_and_uses_last_pages_assignment(tmp_path):
    app = tmp_path / "app.py"
    app.write_text(
        "pages = ['Old A', 'Old B', 'Old C', 'Old D', 'Old E']\n"
        "pages = [\"Home\", \"Today's Opportunities\", \"Volume Intelligence\", "
        "\"Research Any Ticker\", \"Developer Center\"]\n",
        encoding="utf-8",
    )
    pages = discover_navigation_from_app(app)
    assert pages == [
        "Home",
        "Today's Opportunities",
        "Volume Intelligence",
        "Research Any Ticker",
        "Developer Center",
    ]
    assert "," not in pages


def test_runtime_source_has_no_async_await_generator_inside_any():
    source = Path("agents/atlas_runtime_qa_v3.py").read_text(encoding="utf-8")
    assert "any(await " not in source
