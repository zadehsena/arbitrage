"""Local, read-only web dashboard for cross-venue market research."""
from __future__ import annotations

import argparse
import json
from decimal import Decimal, InvalidOperation
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .accounts import kalshi_balance, load_dotenv, polymarket_us_balances
from .football import MARKET_BREAKDOWN_VERSION
from .sports import build_sport_report, is_current_sport_record, supported_sports


ROOT = Path(__file__).resolve().parent.parent
WEB_ROOT = ROOT / "web"
REPORTS_DIR = ROOT / "reports"


def _dollars(value: object) -> str | None:
    """Format cent-denominated venue values without sending raw API payloads."""
    try:
        return f"{Decimal(str(value)) / 100:.2f}"
    except (InvalidOperation, ValueError):
        return None


def account_summary() -> dict:
    """Return read-only wallet totals, never API credentials or raw responses."""
    load_dotenv(str(ROOT / ".env"))
    wallets = []
    try:
        payload = kalshi_balance()
        wallets.append({
            "venue": "Kalshi",
            "balance": payload.get("balance_dollars") or _dollars(payload.get("balance")),
            "portfolio_value": _dollars(payload.get("portfolio_value")),
            "connected": True,
        })
    except Exception:
        wallets.append({"venue": "Kalshi", "balance": None, "portfolio_value": None, "connected": False})

    try:
        balances = polymarket_us_balances().get("balances", [])
        usd = next((item for item in balances if item.get("currency") == "USD"), balances[0] if balances else {})
        wallets.append({
            "venue": "Polymarket US",
            "balance": usd.get("displayedCash", usd.get("currentBalance")),
            "portfolio_value": usd.get("currentBalance"),
            "connected": bool(usd),
        })
    except Exception:
        wallets.append({"venue": "Polymarket US", "balance": None, "portfolio_value": None, "connected": False})

    # These venues do not have account integrations yet. Keep their cards in
    # the dashboard so the wallet layout reflects every venue being compared.
    wallets.extend([
        {"venue": "Novig", "placeholder": True},
        {"venue": "ProphetX", "placeholder": True},
    ])

    return {"wallets": wallets, "updated_at": datetime.now(UTC).isoformat()}


def opportunities_payload() -> dict:
    """Summarize cached reports for the home dashboard without new API calls."""
    rows = []
    counts: dict[str, int] = {}
    for sport in supported_sports():
        path = REPORTS_DIR / f"{sport}_matches.json"
        if not path.exists():
            continue
        try:
            records = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        current = [record for record in records if is_current_sport_record(record, sport)]
        counts[sport] = len(current)
        for record in current:
            kalshi = [item.get("yes_ask") for item in record.get("kalshi_moneyline_asks", [])[:2]]
            poly = [item.get("displayed_quote") for item in record.get("polymarket_us_displayed_moneyline_quotes", [])[:2]]
            try:
                total = min(float(kalshi[0]) + float(poly[1]), float(kalshi[1]) + float(poly[0]))
                edge = max(0, 1 - total)
            except (IndexError, TypeError, ValueError):
                edge = 0
            rows.append({"sport": sport, "title": record.get("polymarket_us_title") or record.get("kalshi_title"),
                         "start_time": record.get("start_time"), "kalshi": kalshi, "polymarket_us": poly,
                         "teams": record.get("teams", []),
                         "edge": edge, "kalshi_ticker": record.get("kalshi_event_ticker"),
                         "polymarket_slug": record.get("polymarket_us_event_slug")})
    return {"opportunities": sorted(rows, key=lambda row: row["edge"], reverse=True)[:8], "sport_counts": counts}


def sport_payload(sport: str, refresh: bool = False) -> dict:
    if sport not in supported_sports():
        raise ValueError(f"unsupported sport: {sport}")
    report_path = REPORTS_DIR / f"{sport}_matches.json"
    if refresh or not report_path.exists():
        records, kalshi_count, polymarket_count = build_sport_report(sport)
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(records, indent=2) + "\n")
    else:
        records = json.loads(report_path.read_text())
        kalshi_count = None
        polymarket_count = None
        # Reports written before logo support lack the `teams` field. Refresh
        # them automatically instead of showing permanent initials badges.
        if any(not record.get("teams") or not record.get("kalshi_url") or not record.get("polymarket_us_url")
               or not record.get("kalshi_market_breakdown") or not record.get("polymarket_us_market_breakdown")
               or "market_catalog" not in record
               or record.get("market_breakdown_version") != MARKET_BREAKDOWN_VERSION
               for record in records):
            records, kalshi_count, polymarket_count = build_sport_report(sport)
            report_path.write_text(json.dumps(records, indent=2) + "\n")
    # Older cached reports may predate the stale-event filter. Apply it at
    # read time too, so completed games disappear without needing a refresh.
    records = [record for record in records if is_current_sport_record(record, sport)]
    return {
        "sport": sport,
        "records": records,
        "updated_at": datetime.now(UTC).isoformat(),
        "kalshi_events_compared": kalshi_count,
        "polymarket_events_compared": polymarket_count,
    }


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

    def end_headers(self) -> None:
        # This local development dashboard must reflect edited JS and CSS
        # immediately; cached assets can otherwise keep an older layout alive.
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/account-summary":
            self.send_json(account_summary())
            return
        if path == "/api/opportunities":
            self.send_json(opportunities_payload())
            return
        sport = path.removeprefix("/api/sports/")
        if sport in supported_sports():
            try:
                self.send_json(sport_payload(sport))
            except Exception as error:  # makes API/network errors visible in the UI
                self.send_json({"error": str(error)}, HTTPStatus.BAD_GATEWAY)
            return
        if path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        prefix = "/api/sports/"
        suffix = "/refresh"
        if not path.startswith(prefix) or not path.endswith(suffix):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        sport = path[len(prefix):-len(suffix)]
        if sport not in supported_sports():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            self.send_json(sport_payload(sport, refresh=True))
        except Exception as error:
            self.send_json({"error": str(error)}, HTTPStatus.BAD_GATEWAY)

    def send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode()
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # The browser can cancel an in-flight auto-refresh when navigating
            # away. The response is no longer needed, so do not log a server
            # error or attempt a second response on the closed socket.
            return


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local read-only arbitrage research dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    print(f"Dashboard: http://{args.host}:{args.port}")
    print("Read-only: no orders, transfers, or withdrawals are available.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
