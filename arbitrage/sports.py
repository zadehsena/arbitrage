"""Validated sport/league mappings and read-only cross-venue reports."""
from __future__ import annotations

import re

from .client import kalshi_open_events_for_series, polymarket_us_league_events
from .football import match_events, report_record


# These pairs were checked against the public venue catalogs. A mapping is only
# a discovery aid; individual event rules and outcome definitions still require review.
SPORT_LEAGUE_MAPPINGS: dict[str, tuple[tuple[str, str], ...]] = {
    "football": (("cfb", "KXNCAAFGAME"), ("nfl", "KXNFLGAME")),
    "soccer": (("epl", "KXEPLGAME"), ("mls", "KXMLSGAME"), ("ucl", "KXUCLGAME")),
    "hockey": (("nhl", "KXNHLGAME"),),
    "basketball": (("nba", "KXNBAGAME"), ("wnba", "KXWNBAGAME"), ("cbb", "KXNCAABGAME")),
    "baseball": (("mlb", "KXMLBGAME"),),
    "tennis": (
        ("atp", "KXATPMATCH"), ("atp", "KXATPCHALLENGERMATCH"),
        ("wta", "KXWTAMATCH"), ("wta", "KXWTACHALLENGERMATCH"),
    ),
}

# Kalshi shortens many MLB club names in event titles. Expand only complete
# known names, keeping Chicago and New York clubs distinct before title scoring.
MLB_TEAM_ALIASES = {
    "Arizona": "Arizona Diamondbacks", "Atlanta": "Atlanta Braves",
    "Baltimore": "Baltimore Orioles", "Boston": "Boston Red Sox",
    "Chicago C": "Chicago Cubs", "Chicago WS": "Chicago White Sox",
    "Cincinnati": "Cincinnati Reds", "Cleveland": "Cleveland Guardians",
    "Colorado": "Colorado Rockies", "Detroit": "Detroit Tigers",
    "Houston": "Houston Astros", "Kansas City": "Kansas City Royals",
    "LA Angels": "Los Angeles Angels", "LA Dodgers": "Los Angeles Dodgers",
    "Miami": "Miami Marlins", "Milwaukee": "Milwaukee Brewers",
    "Minnesota": "Minnesota Twins", "New York M": "New York Mets",
    "New York Y": "New York Yankees", "Oakland": "Athletics",
    "Philadelphia": "Philadelphia Phillies", "Pittsburgh": "Pittsburgh Pirates",
    "San Diego": "San Diego Padres", "San Francisco": "San Francisco Giants",
    "Seattle": "Seattle Mariners", "St Louis": "St. Louis Cardinals",
    "Tampa Bay": "Tampa Bay Rays", "Texas": "Texas Rangers",
    "Toronto": "Toronto Blue Jays", "Washington": "Washington Nationals",
}


def normalize_mlb_title(title: str) -> str:
    """Expand Kalshi's MLB title abbreviations for matching only."""
    normalized = title
    for short_name, full_name in sorted(MLB_TEAM_ALIASES.items(), key=lambda pair: len(pair[0]), reverse=True):
        suffix = full_name[len(short_name):]

        def expand(match: re.Match[str]) -> str:
            # Do not turn an already complete name such as "Boston Red Sox"
            # into "Boston Red Sox Red Sox" when normalizing Polymarket.
            if suffix and match.string[match.end():].lower().startswith(suffix.lower()):
                return match.group(0)
            return full_name

        normalized = re.sub(rf"(?<![A-Za-z]){re.escape(short_name)}(?![A-Za-z])", expand, normalized,
                            flags=re.IGNORECASE)
    return normalized


def supported_sports() -> tuple[str, ...]:
    return tuple(SPORT_LEAGUE_MAPPINGS)


def build_sport_report(sport: str, max_kalshi_events: int = 500,
                       minimum_score: float = 0.72) -> tuple[list[dict], int, int]:
    """Return likely matched open game events for one dashboard sport.

    Requests public market data only. It never authenticates or places orders.
    """
    try:
        mappings = SPORT_LEAGUE_MAPPINGS[sport]
    except KeyError as error:
        raise ValueError(f"no cross-venue mapping configured for sport: {sport}") from error
    if max_kalshi_events < 1 or not 0 <= minimum_score <= 1:
        raise ValueError("max_kalshi_events must be positive and minimum_score must be from 0 to 1")

    kalshi_events = []
    polymarket_events = []
    for polymarket_league, kalshi_series in mappings:
        kalshi_events.extend(kalshi_open_events_for_series(kalshi_series, max_kalshi_events))
        polymarket_events.extend(
            event for event in polymarket_us_league_events(polymarket_league, max_kalshi_events)
            if event.get("active") and not event.get("closed")
        )
    # Tennis has multiple Kalshi match series for one ATP/WTA feed. Retain each
    # Polymarket US event once before attempting title matching.
    polymarket_events = list({event.get("id") or event.get("slug"): event for event in polymarket_events}.values())
    normalizer = normalize_mlb_title if sport == "baseball" else None
    # Tennis feeds often omit players' given names on Kalshi ("Halys") while
    # Polymarket US includes them ("Quentin Halys"). A lower candidate score
    # still requires both opponent names to align and remains review-only.
    effective_minimum_score = min(minimum_score, 0.50) if sport == "tennis" else minimum_score
    matches = match_events(kalshi_events, polymarket_events, effective_minimum_score, normalizer)
    records = [report_record(kalshi_event, poly_event, score)
               for kalshi_event, poly_event, score in matches]
    return records, len(kalshi_events), len(polymarket_events)
