from __future__ import annotations

import json

from .accounts import kalshi_balance, load_dotenv, polymarket_positions, polymarket_us_balances


def main() -> None:
    load_dotenv()
    outcomes: dict[str, object] = {}
    try:
        outcomes["kalshi"] = kalshi_balance()
    except (KeyError, FileNotFoundError) as error:
        outcomes["kalshi"] = {"not_configured": str(error)}
    try:
        outcomes["polymarket_us"] = {
            "balances": polymarket_us_balances(),
            "positions": polymarket_positions(),
        }
    except (KeyError, ValueError) as error:
        outcomes["polymarket_us"] = {"not_configured": str(error)}
    print(json.dumps(outcomes, indent=2))


if __name__ == "__main__":
    main()
