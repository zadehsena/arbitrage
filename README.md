# Cross-venue prediction-market scanner

Read-only Kalshi and Polymarket US market-research tools. They discover likely matching events and compare a reviewed pair; they never place an order, transfer funds, or withdraw funds.

## Setup

Requires Python 3.11+.

```bash
cp .env.example .env
python -m pip install -r requirements.txt
python -m unittest discover -s tests
```

## Discover cross-platform candidates

The discovery command compares open Kalshi and Polymarket US event titles (for example, a sports game containing moneyline, spread, and totals contracts) and creates a short list for manual rule review. It needs no API credentials and does not trade:

```bash
python -m arbitrage.discover --max-markets 500 --limit 50 --json reports/candidates.json
```

Similarity is only a lead. A candidate is never an arbitrage until you verify the full resolution rules, source, cutoff, and outcome semantics on both venues.

## Football matches and odds

To report likely CFB and NFL game matches together with Kalshi top-of-book asks and Polymarket US displayed moneyline quotes:

```bash
python -m arbitrage.football
```

The full local report is written to `reports/football_matches.json`. Use `--leagues cfb` or `--leagues nfl` to narrow it. The Polymarket US figures in this report are displayed quotes, so they are not sufficient to trade or establish an arbitrage.

## Local dashboard

Run a local, read-only table view of matched games:

```bash
python -m arbitrage.dashboard
```

Open http://127.0.0.1:8000. Football, Soccer, Hockey, Basketball, and Baseball use validated public Kalshi-series ↔ Polymarket US-league mappings. **Other** remains reserved for future validated mappings. The **Refresh data** button makes fresh public-data requests for the active tab and overwrites only its ignored local report.

For a pair you have already identified, compare the event-level contracts directly:

```bash
python -m arbitrage.compare \
  --kalshi-event KXNCAAFGAME-26SEP25ARMYTEM \
  --polymarket-us-event cfb-army-templ-2026-09-25
```

This expands a sports event into its contracts. It is useful for reviewing moneyline, spread, and total definitions, but does not place trades or declare an arbitrage.

## Accounts and secrets

Public data needs no account connection. To link accounts for read-only portfolio data, copy `.env.example` to `.env`; it is git-ignored. Do not paste a private key into chat, commit it, or use a primary wallet key.

1. Create a Kalshi API key with the narrowest available read scope. Set `KALSHI_API_KEY_ID` plus either the PEM file's absolute `KALSHI_PRIVATE_KEY_PATH`, or the one-line Base64 PEM value `KALSHI_PRIVATE_KEY_B64`, in `.env`.
2. For **Polymarket US** (`polymarket.us`), create a new API key at the developer portal and set `POLYMARKET_US_KEY_ID` plus `POLYMARKET_US_SECRET_KEY`. This project signs only read-only balance and position requests; it cannot trade, transfer, or withdraw.
3. Verify both connections:

```bash
python -m pip install -r requirements.txt
python -m arbitrage.portfolio
```

Kalshi private endpoints use an API key ID plus an RSA-PSS-signed request. Polymarket US uses an API key pair and Ed25519 request signatures.

## Critical verification

Title similarity is insufficient. Before adding a mapping, compare the complete resolution rules, oracle/source, time cutoff/timezone, treatment of cancellations or revisions, and whether each side is eligible to trade in your jurisdiction. A false “match” can turn an apparent arbitrage into two correlated directional bets.
