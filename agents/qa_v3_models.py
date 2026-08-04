from __future__ import annotations
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class QAIssue:
    severity: str
    category: str
    page: str
    element: str
    expected: str
    actual: str
    recommendation: str
    likely_files: list[str] = field(default_factory=list)
    ticker: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    screenshot: str = ""
    regression_test: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PageResult:
    page: str
    status: str
    duration_seconds: float
    visible_text: str = ""
    metrics: int = 0
    tables: int = 0
    charts: int = 0
    buttons: int = 0
    tabs: int = 0
    expanders: int = 0
    issues: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
