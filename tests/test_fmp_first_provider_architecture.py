from __future__ import annotations

import ast
from collections import Counter
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from engines.ai_valuation import JUSTIFIED_MULTIPLE_FRAMEWORK_APPROVED
from services.provider_ownership import (
    ATLAS,
    ATLAS_PROPRIETARY,
    COMMERCIAL_LICENSE_PENDING,
    FMP,
    LICENSED_MARKET_DATA_PROVIDER,
    PROVIDER_OWNERSHIP,
    PROVIDER_OWNERSHIP_VERSION,
    SEC,
    SUPPORTED_AUTHORITY_STATES,
    SUPPORTED_PROVIDERS,
    provider_migration_metrics,
    provider_ownership_summary,
)
from services.technical_intelligence.config import TECHNICAL_MODEL_VERSION
from services.yahoo_dependency_registry import (
    ACTIVE_STATUSES,
    EXPECTED_YAHOO_DEPENDENCY_COUNT_V1,
    SUPPORTED_DEPENDENCY_STATUSES,
    YAHOO_DEPENDENCIES,
    YAHOO_DEPENDENCY_REGISTRY_VERSION,
    YAHOO_URL_ALLOWLIST,
    YFINANCE_IMPORT_ALLOWLIST,
    yahoo_dependency_summary,
    yahoo_migration_metrics,
)


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOTS = (
    ROOT / "analysis",
    ROOT / "engines",
    ROOT / "services",
    ROOT / "ui",
)
RUNTIME_FILES = (ROOT / "app.py", ROOT / "app_backup.py", ROOT / "analyzer.py", ROOT / "overnight_market_scan.py")


def _python_files() -> list[Path]:
    files = list(RUNTIME_FILES)
    for root in RUNTIME_ROOTS:
        files.extend(root.rglob("*.py"))
    return sorted(set(files))


def _function_sources(path: Path, function_name: str) -> str:
    source = path.read_text(encoding="utf-8")
    if function_name == "*":
        return source
    tree = ast.parse(source)
    chunks: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            chunks.append(ast.get_source_segment(source, node) or "")
    assert chunks, f"registered function missing: {path.relative_to(ROOT)}::{function_name}"
    return "\n".join(chunks)


def test_provider_registry_is_complete_unique_immutable_metadata() -> None:
    assert PROVIDER_OWNERSHIP_VERSION == "PROVIDER_OWNERSHIP_V1"
    assert len(PROVIDER_OWNERSHIP) >= 40
    assert len({item.family for item in PROVIDER_OWNERSHIP}) == len(PROVIDER_OWNERSHIP)
    assert provider_ownership_summary() is PROVIDER_OWNERSHIP
    for item in PROVIDER_OWNERSHIP:
        assert item.intended_primary in SUPPORTED_PROVIDERS
        assert item.current_primary in SUPPORTED_PROVIDERS
        assert item.rollback_owner in SUPPORTED_PROVIDERS
        assert set(item.fallbacks) <= SUPPORTED_PROVIDERS
        assert item.authority_status in SUPPORTED_AUTHORITY_STATES
        assert item.canonical_schema and item.consumers and item.methodology_effect
        assert item.cache_ttl_seconds is None or item.cache_ttl_seconds >= 0
    with pytest.raises(FrozenInstanceError):
        PROVIDER_OWNERSHIP[0].family = "MUTATED"  # type: ignore[misc]


def test_fmp_commercial_status_and_non_fmp_authority_boundaries() -> None:
    by_family = {item.family: item for item in PROVIDER_OWNERSHIP}
    fmp_target = [item for item in PROVIDER_OWNERSHIP if item.intended_primary == FMP]
    assert fmp_target
    assert all(item.commercial_status == COMMERCIAL_LICENSE_PENDING for item in fmp_target)
    assert by_family["SEC_FILINGS"].intended_primary == SEC
    assert by_family["SEC_FILINGS"].current_primary == SEC
    atlas_families = {
        "TECHNICAL_CALCULATIONS", "OPPORTUNITY", "CONFIDENCE", "RECOMMENDATION",
        "BUY_NOW", "RANKING", "ATLAS_FAIR_VALUE", "DECISION_EXPECTED_RETURN",
        "TRADE_PLAN", "POSITION_SIZING", "DETERMINISTIC_INTELLIGENCE", "AI_SYNTHESIS",
    }
    for family in atlas_families:
        item = by_family[family]
        assert (item.intended_primary, item.current_primary, item.rollback_owner) == (ATLAS, ATLAS, ATLAS)
        assert item.commercial_status == ATLAS_PROPRIETARY
    for family in {"LIVE_QUOTES_TRADES", "WEBSOCKET_MARKET_FEED", "INTRADAY_MARKET_DATA", "REAL_TIME_ALERTS", "LIVE_BULL_RUN_RADAR_INPUT"}:
        assert by_family[family].intended_primary == LICENSED_MARKET_DATA_PROVIDER


def test_provider_metrics_are_derived_from_registry() -> None:
    metrics = provider_migration_metrics()
    assert metrics == {
        "total_families": len(PROVIDER_OWNERSHIP),
        "fmp_intended_primary_families": sum(x.intended_primary == FMP for x in PROVIDER_OWNERSHIP),
        "fmp_current_primary_families": sum(x.current_primary == FMP for x in PROVIDER_OWNERSHIP),
        "families_under_validation": sum(x.authority_status in {"MIGRATION_VALIDATION", "SHADOW_VALIDATION", "READY_FOR_CUTOVER"} for x in PROVIDER_OWNERSHIP),
    }


def test_yahoo_registry_has_stable_count_unique_ids_and_valid_metadata() -> None:
    assert YAHOO_DEPENDENCY_REGISTRY_VERSION == "YAHOO_DEPENDENCY_REGISTRY_V1"
    assert len(YAHOO_DEPENDENCIES) == EXPECTED_YAHOO_DEPENDENCY_COUNT_V1
    assert len({item.stable_id for item in YAHOO_DEPENDENCIES}) == len(YAHOO_DEPENDENCIES)
    assert yahoo_dependency_summary() is YAHOO_DEPENDENCIES
    for item in YAHOO_DEPENDENCIES:
        assert item.current_status in SUPPORTED_DEPENDENCY_STATUSES
        assert item.file and item.function and item.data_family
        assert item.production_purpose and item.migration_phase and item.retirement_gate
        assert item.source_markers


def test_every_registered_yahoo_dependency_still_matches_source() -> None:
    for item in YAHOO_DEPENDENCIES:
        source = _function_sources(ROOT / item.file, item.function)
        for marker in item.source_markers:
            assert marker in source, f"stale marker: {item.stable_id}: {marker}"


def test_no_unregistered_yfinance_imports_can_enter_runtime() -> None:
    discovered: set[str] = set()
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(
            (isinstance(node, ast.Import) and any(alias.name == "yfinance" for alias in node.names))
            or (isinstance(node, ast.ImportFrom) and node.module == "yfinance")
            for node in ast.walk(tree)
        ):
            discovered.add(path.relative_to(ROOT).as_posix())
    assert discovered == set(YFINANCE_IMPORT_ALLOWLIST)


def test_no_unregistered_yahoo_urls_can_enter_runtime() -> None:
    expected = Counter((file, url) for file, _function, url in YAHOO_URL_ALLOWLIST)
    actual: Counter[tuple[str, str]] = Counter()
    for path in _python_files():
        relative = path.relative_to(ROOT).as_posix()
        if relative in {"app_backup.py", "services/yahoo_dependency_registry.py"}:
            continue
        source = path.read_text(encoding="utf-8")
        for url in {url for _file, _function, url in YAHOO_URL_ALLOWLIST}:
            count = source.count(url)
            if count:
                actual[(relative, url)] += count
    assert actual == expected


def test_yahoo_metrics_make_migration_debt_measurable() -> None:
    metrics = yahoo_migration_metrics()
    assert metrics["total_registered_yahoo_dependencies"] == EXPECTED_YAHOO_DEPENDENCY_COUNT_V1
    assert metrics["active_yahoo_dependencies"] == sum(x.current_status in ACTIVE_STATUSES for x in YAHOO_DEPENDENCIES)
    assert metrics["active_production_yahoo_dependencies"] == metrics["active_yahoo_dependencies"]
    assert sum((metrics["active_primary_yahoo_dependencies"], metrics["active_fallback_yahoo_dependencies"], metrics["legacy_yahoo_dependencies"])) == EXPECTED_YAHOO_DEPENDENCY_COUNT_V1


def test_governance_modules_are_not_runtime_provider_selectors() -> None:
    for filename in ("services/provider_ownership.py", "services/yahoo_dependency_registry.py"):
        source = (ROOT / filename).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        assert not ({"requests", "yfinance", "httpx", "urllib3"} & imports)
        assert "os.environ" not in source and "getenv(" not in source
    for path in (ROOT / "overnight_market_scan.py", ROOT / "app.py", ROOT / "engines", ROOT / "ui"):
        files = [path] if path.is_file() else list(path.rglob("*.py"))
        for file in files:
            source = file.read_text(encoding="utf-8")
            assert "provider_ownership" not in source
            assert "yahoo_dependency_registry" not in source


def test_investment_and_provisional_gates_are_unchanged() -> None:
    assert JUSTIFIED_MULTIPLE_FRAMEWORK_APPROVED is False
    assert TECHNICAL_MODEL_VERSION == "BULL_RUN_RADAR_V1_PROVISIONAL"
