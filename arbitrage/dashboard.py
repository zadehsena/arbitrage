"""Local, read-only web dashboard for cross-venue market research."""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, InvalidOperation
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .accounts import kalshi_balance, load_dotenv, polymarket_us_balances
from .football import MARKET_BREAKDOWN_VERSION
from .sports import (
    build_sport_report,
    is_current_sport_record,
    supported_leagues,
    supported_sports,
)


ROOT = Path(__file__).resolve().parent.parent
WEB_ROOT = ROOT / "web"
REPORTS_DIR = ROOT / "reports"
ACCOUNT_SUMMARY_TIMEOUT_SECONDS = 5
SPORT_PAGE_SIZE = 25


def _report_metadata_path(report_path: Path) -> Path:
    """Return the small sidecar file containing a cached report's source totals."""
    return report_path.with_name(f"{report_path.stem}_metadata.json")


def _write_sport_report_cache(report_path: Path, records: list[dict],
                              kalshi_count: int, polymarket_count: int) -> None:
    """Cache report rows and the upstream event totals used to produce them."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(records, indent=2) + "\n")
    _report_metadata_path(report_path).write_text(json.dumps({
        "kalshi_events_compared": kalshi_count,
        "polymarket_events_compared": polymarket_count,
    }, indent=2) + "\n")


def _cached_source_counts(report_path: Path) -> tuple[int | None, int | None]:
    """Read upstream event totals without treating matched rows as source rows."""
    try:
        metadata = json.loads(_report_metadata_path(report_path).read_text())
        return metadata.get("kalshi_events_compared"), metadata.get("polymarket_events_compared")
    except (OSError, json.JSONDecodeError):
        return None, None


def _requested_leagues(query: str) -> tuple[str, ...] | None:
    """Read a comma-separated league filter from an API query string."""
    values = parse_qs(query).get("leagues", [])
    leagues = tuple(league.strip() for value in values for league in value.split(",") if league.strip())
    return leagues or None


def _pagination(query: str) -> tuple[int, int]:
    """Return a bounded, non-negative API page offset and size."""
    values = parse_qs(query)
    try:
        offset = max(0, int(values.get("offset", ["0"])[0]))
        limit = min(SPORT_PAGE_SIZE, max(1, int(values.get("limit", [str(SPORT_PAGE_SIZE)])[0])))
    except ValueError:
        return 0, SPORT_PAGE_SIZE
    return offset, limit


def _dollars(value: object) -> str | None:
    """Format cent-denominated venue values without sending raw API payloads."""
    try:
        return f"{Decimal(str(value)) / 100:.2f}"
    except (InvalidOperation, ValueError):
        return None


def account_summary() -> dict:
    """Return read-only wallet totals, never API credentials or raw responses."""
    load_dotenv(str(ROOT / ".env"))

    # Do not let one slow venue delay the whole dashboard. Account requests
    # remain read-only, but this view only needs a brief best-effort snapshot.
    with ThreadPoolExecutor(max_workers=2) as executor:
        kalshi_future = executor.submit(_kalshi_wallet)
        polymarket_future = executor.submit(_polymarket_wallet)
        wallets = [kalshi_future.result(), polymarket_future.result()]

    # These venues do not have account integrations yet. Keep their cards in
    # the dashboard so the wallet layout reflects every venue being compared.
    wallets.extend([
        {"venue": "Novig", "placeholder": True},
        {"venue": "ProphetX", "placeholder": True},
    ])

    return {"wallets": wallets, "updated_at": datetime.now(UTC).isoformat()}


def _kalshi_wallet() -> dict:
    try:
        payload = kalshi_balance(timeout=ACCOUNT_SUMMARY_TIMEOUT_SECONDS)
        return {
            "venue": "Kalshi",
            "balance": payload.get("balance_dollars") or _dollars(payload.get("balance")),
            "portfolio_value": _dollars(payload.get("portfolio_value")),
            "connected": True,
        }
    except Exception:
        return {"venue": "Kalshi", "balance": None, "portfolio_value": None, "connected": False}


def _polymarket_wallet() -> dict:
    try:
        balances = polymarket_us_balances(timeout=ACCOUNT_SUMMARY_TIMEOUT_SECONDS).get("balances", [])
        usd = next((item for item in balances if item.get("currency") == "USD"), balances[0] if balances else {})
        return {
            "venue": "Polymarket US",
            "balance": usd.get("displayedCash", usd.get("currentBalance")),
            "portfolio_value": usd.get("currentBalance"),
            "connected": bool(usd),
        }
    except Exception:
        return {"venue": "Polymarket US", "balance": None, "portfolio_value": None, "connected": False}


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
                         "polymarket_slug": record.get("polymarket_us_event_slug"),
                         "kalshi_url": record.get("kalshi_url"),
                         "polymarket_us_url": record.get("polymarket_us_url")})
    return {"opportunities": sorted(rows, key=lambda row: row["edge"], reverse=True)[:8], "sport_counts": counts}


def sport_payload(sport: str, leagues: tuple[str, ...] | None = None,
                  refresh: bool = False, offset: int = 0,
                  limit: int = SPORT_PAGE_SIZE) -> dict:
    if sport not in supported_sports():
        raise ValueError(f"unsupported sport: {sport}")
    if leagues:
        unknown_leagues = set(leagues) - set(supported_leagues(sport))
        if unknown_leagues:
            raise ValueError(f"unsupported {sport} league: {', '.join(sorted(unknown_leagues))}")
    # Each sidebar choice gets its own cache so a college/pro selection never
    # displays records fetched for the other category.
    cache_suffix = f"_{'-'.join(leagues)}" if leagues else ""
    report_path = REPORTS_DIR / f"{sport}{cache_suffix}_matches.json"
    if refresh or not report_path.exists():
        records, kalshi_count, polymarket_count = build_sport_report(sport, leagues)
        _write_sport_report_cache(report_path, records, kalshi_count, polymarket_count)
    else:
        records = json.loads(report_path.read_text())
        kalshi_count, polymarket_count = _cached_source_counts(report_path)
        # Reports written before logo support lack the `teams` field. Refresh
        # them automatically instead of showing permanent initials badges.
        if any(not record.get("teams") or not record.get("kalshi_url") or not record.get("polymarket_us_url")
               or not record.get("kalshi_market_breakdown") or not record.get("polymarket_us_market_breakdown")
               or "market_catalog" not in record
               or (leagues and record.get("league") not in leagues)
               or record.get("market_breakdown_version") != MARKET_BREAKDOWN_VERSION
               for record in records):
            records, kalshi_count, polymarket_count = build_sport_report(sport, leagues)
            _write_sport_report_cache(report_path, records, kalshi_count, polymarket_count)
    # Older cached reports may predate the stale-event filter. Apply it at
    # read time too, so completed games disappear without needing a refresh.
    records = [record for record in records
               if is_current_sport_record(record, sport)
               and (not leagues or record.get("league") in leagues)]
    total_records = len(records)
    page = records[offset:offset + limit]
    next_offset = offset + len(page)
    return {
        "sport": sport,
        "leagues": leagues or (),
        "records": page,
        "total_records": total_records,
        "next_offset": next_offset if next_offset < total_records else None,
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
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        if path == "/api/account-summary":
            self.send_json(account_summary())
            return
        if path == "/api/opportunities":
            self.send_json(opportunities_payload())
            return
        sport = path.removeprefix("/api/sports/")
        if sport in supported_sports():
            try:
                leagues = _requested_leagues(parsed_url.query)
                offset, limit = _pagination(parsed_url.query)
                self.send_json(sport_payload(sport, leagues, offset=offset, limit=limit))
            except Exception as error:  # makes API/network errors visible in the UI
                self.send_json({"error": str(error)}, HTTPStatus.BAD_GATEWAY)
            return
        if path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        parsed_url = urlparse(self.path)
        path = parsed_url.path
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
            leagues = _requested_leagues(parsed_url.query)
            offset, limit = _pagination(parsed_url.query)
            self.send_json(sport_payload(sport, leagues, refresh=True, offset=offset, limit=limit))
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
