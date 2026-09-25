from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

from .client import kalshi_open_events, polymarket_us_open_events


STOP_WORDS = {"a", "an", "and", "at", "by", "for", "in", "is", "of", "on", "the", "to", "will"}


def words(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]+", text.lower()) if word not in STOP_WORDS}


def similarity(left: str, right: str) -> float:
    left_words, right_words = words(left), words(right)
    if not left_words or not right_words:
        return 0.0
    overlap = len(left_words & right_words) / len(left_words | right_words)
    sequence = SequenceMatcher(None, " ".join(sorted(left_words)), " ".join(sorted(right_words))).ratio()
    return round((overlap * 0.65) + (sequence * 0.35), 3)


def date_part(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return value[:10]


@dataclass(frozen=True)
class Candidate:
    score: float
    kalshi_ticker: str
    kalshi_title: str
    kalshi_close_date: str | None
    polymarket_us_slug: str
    polymarket_us_question: str
    polymarket_us_end_date: str | None
    warning: str = "Candidate only: compare full resolution rules, source, cutoff, and outcome before treating as a match."


def find_candidates(kalshi: list[dict], polymarket: list[dict], minimum_score: float) -> list[Candidate]:
    candidates: list[Candidate] = []
    for kalshi_market in kalshi:
        kalshi_title = kalshi_market.get("title") or kalshi_market.get("subtitle") or ""
        if not kalshi_title:
            continue
        for poly_market in polymarket:
            question = poly_market.get("question") or poly_market.get("title") or ""
            score = similarity(kalshi_title, question)
            if score < minimum_score:
                continue
            candidates.append(Candidate(
                score=score,
                kalshi_ticker=kalshi_market["ticker"],
                kalshi_title=kalshi_title,
                kalshi_close_date=date_part(kalshi_market.get("close_time") or kalshi_market.get("expiration_time")),
                polymarket_us_slug=poly_market["slug"],
                polymarket_us_question=question,
                polymarket_us_end_date=date_part(poly_market.get("endDate")),
            ))
    return sorted(candidates, key=lambda item: item.score, reverse=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Find likely Kalshi / Polymarket US event matches for human review")
    parser.add_argument("--max-markets", type=int, default=500, help="Open events to pull per venue (default: 500)")
    parser.add_argument("--min-score", type=float, default=0.58, help="Title similarity threshold from 0 to 1 (default: 0.58)")
    parser.add_argument("--limit", type=int, default=50, help="Maximum candidates to print (default: 50)")
    parser.add_argument("--json", type=Path, help="Optional path for the full candidate report")
    args = parser.parse_args()
    if args.max_markets < 1 or not 0 <= args.min_score <= 1 or args.limit < 1:
        parser.error("--max-markets and --limit must be positive; --min-score must be from 0 to 1")

    raw_kalshi = kalshi_open_events(args.max_markets)
    raw_polymarket = polymarket_us_open_events(args.max_markets)
    kalshi = [{"ticker": event["event_ticker"], "title": event.get("title", ""),
               "close_time": event.get("close_time") or event.get("expected_expiration_time")}
              for event in raw_kalshi]
    polymarket = [{"slug": event["slug"], "question": event.get("title", ""),
                   "endDate": event.get("endDate") or event.get("eventDate")}
                  for event in raw_polymarket]
    candidates = find_candidates(kalshi, polymarket, args.min_score)
    print(f"Fetched {len(kalshi)} Kalshi and {len(polymarket)} Polymarket US open events.")
    print(f"Found {len(candidates)} title-similarity event candidates (not verified matches).")
    for item in candidates[:args.limit]:
        print(f"\n{item.score:.3f} | Kalshi event {item.kalshi_ticker} | {item.kalshi_title}")
        print(f"      Polymarket US event {item.polymarket_us_slug} | {item.polymarket_us_question}")
        print(f"      dates: Kalshi {item.kalshi_close_date or 'unknown'}; Polymarket US {item.polymarket_us_end_date or 'unknown'}")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps([asdict(item) for item in candidates], indent=2) + "\n")
        print(f"\nWrote {len(candidates)} candidates to {args.json}")


if __name__ == "__main__":
    main()
