"""Bounded, sanitized Alpaca market-data entitlement diagnostic.

The probe emits allowlisted metadata only. It never prints credentials,
authenticated URLs, response payloads, or market prices. It is intended for a
manual GitHub Actions workflow and is not imported by production code.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
import socket
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SYMBOLS = ("NVDA", "SPY", "META", "CGRNQ")
RENAMED_SYMBOL = "FB"
DEFAULT_REQUEST_CAP = 20
DEFAULT_TIMEOUT_SECONDS = 10.0
DATA_BASE = "https://data.alpaca.markets"
ASSET_BASE = "https://paper-api.alpaca.markets"


class RequestBudget:
    def __init__(self, cap: int) -> None:
        self.cap = min(max(int(cap), 1), DEFAULT_REQUEST_CAP)
        self.used = 0

    def consume(self) -> None:
        if self.used >= self.cap:
            raise RuntimeError("REQUEST_CAP_REACHED")
        self.used += 1


def _rows(payload: Any, *keys: str) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, Mapping)]
    if isinstance(payload, Mapping):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, Mapping)]
            if isinstance(value, Mapping):
                return [item for item in value.values() if isinstance(item, Mapping)]
    return []


def _dates(rows: list[Mapping[str, Any]]) -> list[str]:
    values: set[str] = set()
    for row in rows:
        for key, value in row.items():
            if key.lower() not in {"t", "timestamp", "date", "process_date", "ex_date", "record_date", "payable_date"}:
                continue
            text = str(value or "")
            if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
                values.add(text[:10])
    return sorted(values)


def _rate_metadata(headers: Mapping[str, Any]) -> dict[str, int | None]:
    output: dict[str, int | None] = {}
    for source, target in (
        ("X-RateLimit-Limit", "limit"),
        ("X-RateLimit-Remaining", "remaining"),
        ("X-RateLimit-Reset", "reset_epoch"),
    ):
        try:
            output[target] = int(headers.get(source)) if headers.get(source) is not None else None
        except (TypeError, ValueError):
            output[target] = None
    return output


def _http_json(
    path: str,
    params: Mapping[str, Any],
    *,
    key_id: str,
    secret_key: str,
    budget: RequestBudget,
    timeout: float,
    base: str = DATA_BASE,
    opener: Callable[..., Any] = urlopen,
) -> tuple[int | None, Any, str | None, dict[str, int | None]]:
    budget.consume()
    request = Request(
        f"{base}{path}?{urlencode(dict(params))}",
        headers={
            "APCA-API-KEY-ID": key_id,
            "APCA-API-SECRET-KEY": secret_key,
            "User-Agent": "Atlas-Alpaca-Sanitized-Entitlement-Probe/1.0",
        },
    )
    try:
        with opener(request, timeout=timeout) as response:
            status = int(response.status)
            rate = _rate_metadata(response.headers)
            raw = response.read()
        try:
            return status, json.loads(raw), None, rate
        except (json.JSONDecodeError, UnicodeDecodeError):
            return status, None, "NON_JSON_RESPONSE", rate
    except HTTPError as exc:
        return int(exc.code), None, "HTTP_ERROR", _rate_metadata(exc.headers or {})
    except (URLError, TimeoutError, socket.timeout):
        return None, None, "NETWORK_ERROR", {}
    except Exception:
        return None, None, "UNEXPECTED_ERROR", {}


def _endpoint_result(
    family: str,
    feed: str | None,
    status: int | None,
    payload: Any,
    error: str | None,
    rate: Mapping[str, int | None],
    *,
    row_keys: tuple[str, ...],
) -> dict[str, Any]:
    rows = _rows(payload, *row_keys)
    dates = _dates(rows)
    return {
        "kind": "rest_metadata",
        "endpoint_family": family,
        "feed": feed,
        "http_status": status,
        "authorized": bool(status is not None and 200 <= status < 300),
        "error_category": error,
        "row_count": len(rows),
        "earliest_date": dates[0] if dates else None,
        "latest_date": dates[-1] if dates else None,
        "rate_limit": dict(rate),
    }


def _session_counts(rows: list[Mapping[str, Any]]) -> dict[str, int]:
    counts = {"pre_market": 0, "regular": 0, "after_hours": 0, "overnight": 0, "unclassified": 0}
    for row in rows:
        text = str(row.get("t") or row.get("timestamp") or "")
        try:
            moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
            from zoneinfo import ZoneInfo
            local = moment.astimezone(ZoneInfo("America/New_York"))
            minute = local.hour * 60 + local.minute
            if 4 * 60 <= minute < 9 * 60 + 30:
                counts["pre_market"] += 1
            elif 9 * 60 + 30 <= minute < 16 * 60:
                counts["regular"] += 1
            elif 16 * 60 <= minute < 20 * 60:
                counts["after_hours"] += 1
            else:
                counts["overnight"] += 1
        except (ValueError, TypeError):
            counts["unclassified"] += 1
    return counts


def _websocket_probe(feed: str, key_id: str, secret_key: str, timeout: float) -> dict[str, Any]:
    """Authenticate and subscribe to the four allowlisted symbols only."""
    try:
        import websocket  # type: ignore

        ws = websocket.create_connection(
            f"wss://stream.data.alpaca.markets/v2/{feed}",
            timeout=timeout,
        )
        try:
            connected = json.loads(ws.recv())
            ws.send(json.dumps({"action": "auth", "key": key_id, "secret": secret_key}))
            authenticated = json.loads(ws.recv())
            ws.send(json.dumps({"action": "subscribe", "bars": list(SYMBOLS)}))
            subscribed = json.loads(ws.recv())
        finally:
            ws.close()

        def messages(value: Any) -> list[Mapping[str, Any]]:
            return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []

        connected_ok = any(item.get("T") == "success" and item.get("msg") == "connected" for item in messages(connected))
        auth_ok = any(item.get("T") == "success" and item.get("msg") == "authenticated" for item in messages(authenticated))
        subscription_rows = [item for item in messages(subscribed) if item.get("T") == "subscription"]
        accepted = sorted({str(symbol) for item in subscription_rows for symbol in (item.get("bars") or []) if symbol in SYMBOLS})
        errors = [int(item.get("code")) for value in (connected, authenticated, subscribed) for item in messages(value) if item.get("T") == "error" and isinstance(item.get("code"), int)]
        return {
            "kind": "websocket_metadata",
            "feed": feed,
            "connected": connected_ok,
            "authenticated": auth_ok,
            "requested_symbol_count": len(SYMBOLS),
            "accepted_symbol_count": len(accepted),
            "subscription_lower_bound": len(accepted),
            "error_codes": errors,
            "error_category": None if auth_ok else "AUTH_OR_ENTITLEMENT_ERROR",
        }
    except (TimeoutError, socket.timeout):
        return {"kind": "websocket_metadata", "feed": feed, "connected": False, "authenticated": False, "requested_symbol_count": len(SYMBOLS), "accepted_symbol_count": 0, "subscription_lower_bound": 0, "error_codes": [], "error_category": "TIMEOUT"}
    except Exception:
        return {"kind": "websocket_metadata", "feed": feed, "connected": False, "authenticated": False, "requested_symbol_count": len(SYMBOLS), "accepted_symbol_count": 0, "subscription_lower_bound": 0, "error_codes": [], "error_category": "CONNECTION_OR_ENTITLEMENT_ERROR"}


def _emit(value: Mapping[str, Any]) -> None:
    print(json.dumps(dict(value), sort_keys=True, separators=(",", ":")))


def run() -> int:
    key_id = os.getenv("APCA_API_KEY_ID", "").strip()
    secret_key = os.getenv("APCA_API_SECRET_KEY", "").strip()
    cap = int(os.getenv("ALPACA_PROBE_REQUEST_CAP", str(DEFAULT_REQUEST_CAP)))
    timeout = min(float(os.getenv("ALPACA_PROBE_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS))), DEFAULT_TIMEOUT_SECONDS)
    budget = RequestBudget(cap)
    credentials_ready = bool(key_id and secret_key)
    _emit({
        "kind": "probe_start",
        "credentials_configured": credentials_ready,
        "required_secret_names": ["APCA_API_KEY_ID", "APCA_API_SECRET_KEY"],
        "symbols": list(SYMBOLS),
        "renamed_symbol": RENAMED_SYMBOL,
        "hard_request_cap": budget.cap,
        "planned_rest_requests": 15,
        "planned_websocket_tests": 2,
        "timeout_seconds": timeout,
    })
    if not credentials_ready:
        _emit({"kind": "probe_complete", "requests_used": 0, "websocket_tests_used": 0, "status": "MISSING_CREDENTIALS_ZERO_NETWORK_CALLS"})
        return 2

    today = datetime.now(timezone.utc).date()
    recent_start = today - timedelta(days=14)
    prior_month = today - timedelta(days=30)
    prior_year = today - timedelta(days=365)
    results: list[dict[str, Any]] = []

    def request(family: str, path: str, params: Mapping[str, Any], feed: str | None, keys: tuple[str, ...], base: str = DATA_BASE) -> tuple[Any, dict[str, Any]]:
        status, payload, error, rate = _http_json(path, params, key_id=key_id, secret_key=secret_key, budget=budget, timeout=timeout, base=base)
        result = _endpoint_result(family, feed, status, payload, error, rate, row_keys=keys)
        results.append(result)
        _emit(result)
        return payload, result

    symbols_csv = ",".join(SYMBOLS)
    for feed in ("iex", "sip", "delayed_sip"):
        request("latest_trades", "/v2/stocks/trades/latest", {"symbols": symbols_csv, "feed": feed}, feed, ("trades",))

    for timeframe in ("1Day", "1Hour", "1Min"):
        request("historical_bars", "/v2/stocks/NVDA/bars", {"feed": "sip", "timeframe": timeframe, "start": "2016-01-01", "end": (today - timedelta(days=1)).isoformat(), "sort": "asc", "limit": 1, "adjustment": "raw"}, "sip", ("bars",))
    request("historical_bars", "/v2/stocks/SPY/bars", {"feed": "sip", "timeframe": "1Day", "start": "2016-01-01", "end": (today - timedelta(days=1)).isoformat(), "sort": "asc", "limit": 1, "adjustment": "raw"}, "sip", ("bars",))

    extended_payload, extended_result = request("extended_hours_bars", "/v2/stocks/NVDA/bars", {"feed": "sip", "timeframe": "1Min", "start": recent_start.isoformat(), "end": (today - timedelta(days=1)).isoformat(), "sort": "asc", "limit": 10000, "adjustment": "raw"}, "sip", ("bars",))
    _emit({"kind": "extended_hours_metadata", "authorized": extended_result["authorized"], "session_counts": _session_counts(_rows(extended_payload, "bars"))})

    request("historical_auctions", "/v2/stocks/auctions", {"symbols": "NVDA,SPY", "feed": "sip", "start": prior_month.isoformat(), "end": (today - timedelta(days=1)).isoformat(), "limit": 100}, "sip", ("auctions",))
    request("corporate_actions", "/v1/corporate-actions", {"symbols": symbols_csv, "region": "us", "start": prior_year.isoformat(), "end": today.isoformat(), "limit": 100}, None, ("corporate_actions", "forward_splits", "reverse_splits", "cash_dividends", "name_changes", "worthless_removals"))
    request("renamed_history_current_symbol", "/v2/stocks/META/bars", {"feed": "sip", "timeframe": "1Day", "start": "2022-06-06", "end": "2022-06-11", "asof": "2022-06-10", "limit": 10, "adjustment": "raw"}, "sip", ("bars",))
    request("renamed_history_old_symbol", "/v2/stocks/FB/bars", {"feed": "sip", "timeframe": "1Day", "start": "2022-06-06", "end": "2022-06-11", "asof": "2022-06-06", "limit": 10, "adjustment": "raw"}, "sip", ("bars",))
    request("delisted_otc_history", "/v2/stocks/CGRNQ/bars", {"feed": "sip", "timeframe": "1Day", "start": "2016-01-01", "end": (today - timedelta(days=1)).isoformat(), "sort": "desc", "limit": 1, "adjustment": "raw"}, "sip", ("bars",))
    for symbol in ("FB", "CGRNQ"):
        asset_payload, asset_result = request("asset_status", f"/v2/assets/{symbol}", {}, None, ("asset",), ASSET_BASE)
        asset = asset_payload if isinstance(asset_payload, Mapping) else {}
        _emit({
            "kind": "asset_metadata",
            "symbol": symbol,
            "authorized": asset_result["authorized"],
            "status": asset.get("status") if asset.get("status") in {"active", "inactive"} else None,
            "exchange": str(asset.get("exchange") or "")[:16] or None,
            "tradable": asset.get("tradable") if isinstance(asset.get("tradable"), bool) else None,
        })

    ws_results = [_websocket_probe(feed, key_id, secret_key, timeout) for feed in ("iex", "sip")]
    for result in ws_results:
        _emit(result)

    sip_rest = any(item["endpoint_family"] == "latest_trades" and item["feed"] == "sip" and item["authorized"] for item in results)
    delayed_sip = any(item["endpoint_family"] == "latest_trades" and item["feed"] == "delayed_sip" and item["authorized"] for item in results)
    sip_ws = any(item["feed"] == "sip" and item["authenticated"] for item in ws_results)
    inferred = "REALTIME_SIP_ENTITLED" if sip_rest and sip_ws else ("BASIC_OR_HIGHER_DELAYED_SIP" if delayed_sip else "ENTITLEMENT_UNRESOLVED")
    _emit({
        "kind": "probe_complete",
        "status": "COMPLETE",
        "requests_used": budget.used,
        "websocket_tests_used": len(ws_results),
        "inferred_feed_entitlement": inferred,
        "http_failure_categories": sorted({str(item["error_category"]) for item in results if item.get("error_category")}),
        "websocket_failure_categories": sorted({str(item["error_category"]) for item in ws_results if item.get("error_category")}),
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
