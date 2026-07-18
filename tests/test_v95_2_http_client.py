import requests

from services.http_client import robust_get


class FakeResponse:
    def __init__(self, status_code, headers=None):
        self.status_code = status_code
        self.headers = headers or {}


class FakeSession:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


def test_timeout_is_always_applied():
    session = FakeSession([FakeResponse(200)])
    response = robust_get(
        "https://example.test",
        session=session,
        backoff_seconds=0,
    )
    assert response.status_code == 200
    assert session.calls[0][1]["timeout"] == (5.0, 20.0)


def test_transient_status_is_retried(monkeypatch):
    monkeypatch.setattr("services.http_client.time.sleep", lambda *_: None)
    monkeypatch.setattr("services.http_client.random.uniform", lambda *_: 0)
    session = FakeSession([FakeResponse(429), FakeResponse(200)])

    response = robust_get(
        "https://example.test",
        session=session,
        max_attempts=2,
        backoff_seconds=0,
    )

    assert response.status_code == 200
    assert len(session.calls) == 2


def test_permanent_client_error_is_not_retried():
    session = FakeSession([FakeResponse(404)])
    response = robust_get(
        "https://example.test",
        session=session,
        max_attempts=3,
        backoff_seconds=0,
    )
    assert response.status_code == 404
    assert len(session.calls) == 1
