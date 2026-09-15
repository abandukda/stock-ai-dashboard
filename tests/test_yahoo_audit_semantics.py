import pytest

from scripts.audit_production_yahoo_dependencies import audit, audit_source


def categories(source, path="services/example.py"):
    return {item["classification"] for item in audit_source(source, path=path)}


@pytest.mark.parametrize("source", [
    "import yfinance as yf\n",
    "payload = requests.get('https://query1.finance.yahoo.com/v8/chart/MSFT')\n",
    "value = acquire_yahoo_fallback('MSFT')\n",
    "forward_eps_source = 'YAHOO_INFO'\n",
])
def test_executable_production_yahoo_dependency_fails(source):
    assert categories(source) == {"ACTIVE_PRODUCTION_DEPENDENCY"}


@pytest.mark.parametrize("source", [
    "# Yahoo was removed from production acquisition\n",
    "DISALLOWED_PROVIDER_TOKENS = ('YAHOO_INFO',)\n",
    "if provider == 'YAHOO_INFO': reject_stale_evidence()\n",
    "safe_label = sanitize_provider_name('Yahoo')\n",
])
def test_production_rejection_and_sanitization_are_non_acquisitional(source):
    result = categories(source)
    assert result <= {"CONTEXTUAL_PUBLISHER_LINEAGE", "SAFE_COMMENT_DOCUMENTATION"}


def test_test_fixture_mocking_yfinance_is_allowed():
    assert categories("import yfinance as yf\nyf.download('MSFT')\n", "tests/test_fixture.py") == {"TEST_FIXTURE"}


def test_isolated_legacy_dependency_is_reported_but_allowed():
    assert categories("import yfinance as yf\n", "app_backup.py") == {"LEGACY_DEAD_CODE"}


def test_production_cache_or_fallback_reference_is_a_policy_violation():
    assert categories("legacy_yahoo_cache = load_cache()\n") == {"CACHE_FALLBACK"}


def test_customer_copy_is_reported_separately():
    assert categories("source_label = 'Yahoo Finance'\n", "ui/example.py") == {"CUSTOMER_COPY"}


def test_repository_policy_gate_has_no_production_violation():
    result = audit()
    assert result["PRODUCTION_ACTIVE_YAHOO_DEPENDENCY_COUNT"] == 0
    assert result["cache_fallback_count"] == 0
    assert result["customer_copy_count"] == 0
    assert result["PRODUCTION_YAHOO_POLICY_VIOLATION_COUNT"] == 0
