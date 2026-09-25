"""Local, read-only web dashboard for cross-venue market research."""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .sports import build_sport_report, supported_sports


ROOT = Path(__file__).resolve().parent.parent
WEB_ROOT = ROOT / "web"
REPORTS_DIR = ROOT / "reports"


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
               for record in records):
            records, kalshi_count, polymarket_count = build_sport_report(sport)
            report_path.write_text(json.dumps(records, indent=2) + "\n")
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

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
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
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


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
