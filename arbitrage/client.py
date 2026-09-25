from __future__ import annotations

import json
import ssl
from functools import lru_cache
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


KALSHI_BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
POLYMARKET_US_GATEWAY_URL = "https://gateway.polymarket.us"


def _get_json(url: str) -> Any:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "cross-venue-arbitrage-scanner/0.1"})
    import certifi
    context = ssl.create_default_context(cafile=certifi.where())
    with urlopen(request, timeout=20, context=context) as response:
        return json.load(response)


def kalshi_market(ticker: str) -> dict[str, Any]:
    return _get_json(f"{KALSHI_BASE_URL}/markets/{ticker}")["market"]


def kalshi_event(event_ticker: str) -> dict[str, Any]:
    payload = _get_json(f"{KALSHI_BASE_URL}/events/{event_ticker}")
    event = payload["event"]
    # Kalshi returns the parent event and its contracts as sibling fields.
    return {**event, "markets": payload.get("markets", [])}


@lru_cache(maxsize=256)
def kalshi_series(series_ticker: str) -> dict[str, Any]:
    return _get_json(f"{KALSHI_BASE_URL}/series/{series_ticker}")["series"]


def kalshi_open_events(max_events: int = 500) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    cursor: str | None = None
    while len(events) < max_events:
        query = {"status": "open", "limit": min(200, max_events - len(events))}
        if cursor:
            query["cursor"] = cursor
        page = _get_json(f"{KALSHI_BASE_URL}/events?{urlencode(query)}")
        batch = page.get("events", [])
        events.extend(batch)
        cursor = page.get("cursor")
        if not cursor or not batch:
            break
    return events[:max_events]


def kalshi_open_events_for_series(series_ticker: str, max_events: int = 1000) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    cursor: str | None = None
    while len(events) < max_events:
        query = {
            "series_ticker": series_ticker, "status": "open",
            "limit": min(200, max_events - len(events)),
        }
        if cursor:
            query["cursor"] = cursor
        page = _get_json(f"{KALSHI_BASE_URL}/events?{urlencode(query)}")
        batch = page.get("events", [])
        events.extend(batch)
        cursor = page.get("cursor")
        if not cursor or not batch:
            break
    return events[:max_events]


def polymarket_us_open_events(max_events: int = 500) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    while len(events) < max_events:
        query = {
            "active": "true", "closed": "false", "archived": "false",
            "limit": min(200, max_events - len(events)), "offset": len(events),
        }
        page = _get_json(f"{POLYMARKET_US_GATEWAY_URL}/v1/events?{urlencode(query)}")
        batch = page.get("events", [])
        events.extend(batch)
        if not batch:
            break
    return events[:max_events]


def polymarket_us_league_events(league: str, max_events: int = 500) -> list[dict[str, Any]]:
    """Retrieve all available pages from a Polymarket US league feed."""
    events: list[dict[str, Any]] = []
    seen: set[str] = set()
    offset = 0
    while len(events) < max_events:
        limit = min(100, max_events - len(events))
        payload = _get_json(
            f"{POLYMARKET_US_GATEWAY_URL}/v2/leagues/{league}/events?"
            f"{urlencode({'limit': limit, 'offset': offset})}"
        )
        batch = payload.get("events", [])
        for event in batch:
            identifier = str(event.get("id") or event.get("slug") or offset)
            if identifier not in seen:
                seen.add(identifier)
                events.append(event)
        offset += len(batch)
        if len(batch) < limit or not batch:
            break
    return events[:max_events]


def polymarket_us_event(slug: str) -> dict[str, Any]:
    return _get_json(f"{POLYMARKET_US_GATEWAY_URL}/v1/events/slug/{slug}")["event"]
