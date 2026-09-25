from __future__ import annotations

import json
import ssl
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


KALSHI_BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
POLYMARKET_CLOB_URL = "https://clob.polymarket.com"


def _get_json(url: str) -> Any:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "cross-venue-arbitrage-scanner/0.1"})
    import certifi
    context = ssl.create_default_context(cafile=certifi.where())
    with urlopen(request, timeout=20, context=context) as response:
        return json.load(response)


@dataclass(frozen=True)
class Quote:
    ask: Decimal
    size: Decimal


def kalshi_market(ticker: str) -> dict[str, Any]:
    return _get_json(f"{KALSHI_BASE_URL}/markets/{ticker}")["market"]


def kalshi_quote(market: dict[str, Any], side: str) -> Quote | None:
    ask = market.get(f"{side}_ask_dollars")
    size = market.get(f"{side}_ask_size_fp")
    if ask is None or size is None:
        return None
    ask_decimal, size_decimal = Decimal(str(ask)), Decimal(str(size))
    if ask_decimal <= 0 or size_decimal <= 0:
        return None
    return Quote(ask_decimal, size_decimal)


def polymarket_quote(token_id: str) -> Quote | None:
    book = _get_json(f"{POLYMARKET_CLOB_URL}/book?{urlencode({'token_id': token_id})}")
    asks = book.get("asks", [])
    if not asks:
        return None
    best = min(asks, key=lambda level: Decimal(str(level["price"])))
    ask, size = Decimal(str(best["price"])), Decimal(str(best["size"]))
    if ask <= 0 or size <= 0:
        return None
    return Quote(ask, size)
