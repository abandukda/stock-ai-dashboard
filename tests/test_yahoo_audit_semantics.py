import pytest

from scripts.audit_production_yahoo_dependencies import audit_source


def categories(source, path="services/example.py"):
    return {item["classification"] for item in audit_source(source, path=path)}


@pytest.mark.parametrize("source", [
    "import yfinance as yf\n",
    "payload = requests.get('https://query1.finance.yahoo.com/v8/chart/MSFT')\n",
    "value = acquire_yahoo_fallback('MSFT')\n",
    "forward_eps_source = 'YAHOO_INFO'\n",
])
def test_executable_production_yahoo_dependency_fails(source):
    assert categories(source) == {"PRODUCTION_ACTIVE"}


@pytest.mark.parametrize("source", [
    "# Yahoo was removed from production acquisition\n",
    "DISALLOWED_PROVIDER_TOKENS = ('YAHOO_INFO',)\n",
    "if provider == 'YAHOO_INFO': reject_stale_evidence()\n",
    "safe_label = sanitize_provider_name('Yahoo')\n",
])
def test_production_rejection_comments_and_sanitization_are_contextual(source):
    assert categories(source) == {"PRODUCTION_CONTEXTUAL"}


def test_test_fixture_mocking_yfinance_is_allowed():
    assert categories("import yfinance as yf\nyf.download('MSFT')\n", "tests/test_fixture.py") == {"TEST_ONLY"}


def test_isolated_legacy_dependency_is_reported_but_allowed():
    assert categories("import yfinance as yf\n", "app_backup.py") == {"LEGACY_ISOLATED"}
