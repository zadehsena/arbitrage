from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from .client import Quote, kalshi_market, kalshi_quote, polymarket_quote


@dataclass(frozen=True)
class Opportunity:
    label: str
    direction: str
    cost: Decimal
    edge: Decimal
    maximum_contracts: Decimal


def paired_opportunity(
    label: str, first: Quote | None, second: Quote | None, direction: str,
    fee_buffer: Decimal, minimum_edge: Decimal,
) -> Opportunity | None:
    if first is None or second is None:
        return None
    # One YES and one NO that have genuinely identical settlement terms pay $1 in all outcomes.
    cost = first.ask + second.ask + fee_buffer
    edge = Decimal("1") - cost
    if edge < minimum_edge:
        return None
    return Opportunity(label, direction, cost, edge, min(first.size, second.size))


def scan(config: dict) -> list[Opportunity]:
    fee_buffer = Decimal(str(config.get("fee_buffer_per_contract", "0.02")))
    minimum_edge = Decimal(str(config.get("minimum_edge_per_contract", "0.02")))
    results: list[Opportunity] = []
    for match in config.get("matches", []):
        market = kalshi_market(match["kalshi_ticker"])
        poly_yes = polymarket_quote(match["polymarket_yes_token_id"])
        # YES on one venue + NO on the other. The CLOB NO token is deliberately required:
        # do not infer NO price as 1-YES; the executable ask can differ.
        poly_no_id = match.get("polymarket_no_token_id")
        poly_no = polymarket_quote(poly_no_id) if poly_no_id else None
        results.extend(filter(None, [
            paired_opportunity(match["label"], kalshi_quote(market, "yes"), poly_no,
                               "buy Kalshi YES + Polymarket NO", fee_buffer, minimum_edge),
            paired_opportunity(match["label"], kalshi_quote(market, "no"), poly_yes,
                               "buy Kalshi NO + Polymarket YES", fee_buffer, minimum_edge),
        ]))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only executable-price cross-venue scanner")
    parser.add_argument("--config", default="config/matches.json")
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    opportunities = scan(config)
    if not opportunities:
        print("No opportunities above configured buffer. Confirm mappings and live order books.")
        return
    for item in opportunities:
        print(f"{item.label}: {item.direction}; all-in cost ${item.cost:.4f}; "
              f"gross edge ${item.edge:.4f}/contract; displayed depth {item.maximum_contracts}")


if __name__ == "__main__":
    main()
