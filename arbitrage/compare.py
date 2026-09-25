from __future__ import annotations

import argparse
import re
from decimal import Decimal

from .client import kalshi_event, polymarket_us_event
from .discover import similarity


def id_from_input(value: str, venue: str) -> str:
    """Accept an event identifier or its normal website URL."""
    value = value.rstrip("/")
    if "/" not in value:
        return value
    final = value.rsplit("/", 1)[-1]
    if not final:
        raise ValueError(f"Could not extract {venue} event ID from {value!r}")
    return final.upper() if venue == "Kalshi" else final


def money(value: object | None) -> str:
    if value is None:
        return "—"
    try:
        return f"${Decimal(str(value)):.4f}"
    except Exception:
        return str(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only comparison of one Kalshi and one Polymarket US event")
    parser.add_argument("--kalshi-event", required=True, help="Kalshi event ticker or website URL")
    parser.add_argument("--polymarket-us-event", required=True, help="Polymarket US event slug or website URL")
    args = parser.parse_args()

    kalshi = kalshi_event(id_from_input(args.kalshi_event, "Kalshi"))
    poly = polymarket_us_event(id_from_input(args.polymarket_us_event, "Polymarket US"))
    score = similarity(kalshi.get("title", ""), poly.get("title", ""))
    print(f"Title similarity: {score:.3f} (1.000 means identical normalized title; not a rules match)")
    print(f"Kalshi: {kalshi.get('title')} | {kalshi.get('event_ticker')}")
    print(f"Polymarket US: {poly.get('title')} | {poly.get('slug')}")
    print("\nKalshi contracts (executable top-of-book asks):")
    for market in kalshi.get("markets", []):
        print(f"  {market.get('ticker')} | {market.get('title')} | "
              f"YES ask {money(market.get('yes_ask_dollars'))}; "
              f"NO ask {money(market.get('no_ask_dollars'))}")
    print("\nPolymarket US contracts (displayed quotes; obtain BBO before trading):")
    poly_markets = [market for market in poly.get("markets", [])
                    if market.get("sportsMarketType") == "moneyline"]
    if not poly_markets:
        poly_markets = [market for market in poly.get("markets", [])
                        if "who will win in the upcoming" in market.get("question", "").lower()]
    for market in poly_markets:
        sides = []
        for side in market.get("marketSides", []):
            quote = side.get("quote", {}).get("value")
            sides.append(f"{side.get('description')}: {money(quote)}")
        print(f"  {market.get('slug')} | {market.get('question')} | {'; '.join(sides) or 'no quote'}")
    print("\nRequired review: same outcome set, regulation/OT treatment, postponement/cancellation rules,"
          " official source, cutoff, fees, and executable depth. This command never trades.")


if __name__ == "__main__":
    main()
