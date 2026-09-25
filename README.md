# Cross-venue prediction-market scanner

Read-only scanner for a very narrow arbitrage pattern: buy complementary outcomes on Kalshi and Polymarket only when the two contracts have been manually verified to resolve identically. It never places an order or uses account credentials.

## Setup

Requires Python 3.11+ (no packages needed).

```bash
cp config/matches.example.json config/matches.json
python -m unittest discover -s tests
python -m arbitrage.scan --config config/matches.json
```

Edit `config/matches.json`. For each reviewed match, include both Polymarket CLOB token IDs:

```json
{
  "label": "…",
  "kalshi_ticker": "…",
  "polymarket_yes_token_id": "…",
  "polymarket_no_token_id": "…",
  "resolution_notes": "same source, cutoff, and outcome definition"
}
```

The scanner compares executable *ask* prices—not last prices—and reports an opportunity only when:

`Kalshi ask + Polymarket complementary ask + configured fee/slippage buffer < $1.00`

Displayed depth is the smaller of the two top-of-book sizes; it is not guaranteed fillable volume. Adjust `fee_buffer_per_contract` to cover both venues’ actual fees, withdrawal/funding costs, latency, and any price movement. The output is a research signal, not trading advice.

## Accounts and secrets

Public data needs no account connection. To link accounts for read-only portfolio data, copy `.env.example` to `.env`; it is git-ignored. Do not paste a private key into chat, commit it, or use a primary wallet key.

1. Create a Kalshi API key with the narrowest available read scope. Set `KALSHI_API_KEY_ID` plus either the PEM file's absolute `KALSHI_PRIVATE_KEY_PATH`, or the one-line Base64 PEM value `KALSHI_PRIVATE_KEY_B64`, in `.env`.
2. For **Polymarket US** (`polymarket.us`), create a new API key at the developer portal and set `POLYMARKET_US_KEY_ID` plus `POLYMARKET_US_SECRET_KEY`. This project signs only read-only balance and position requests; it cannot trade, transfer, or withdraw.
3. Install the one local dependency and verify both connections:

```bash
python -m pip install -r requirements.txt
python -m arbitrage.portfolio
```

Kalshi private endpoints use an API key ID plus an RSA-PSS-signed request. Polymarket US uses an API key pair and Ed25519 request signatures. This repository intentionally does not implement authenticated order placement, transfers, or withdrawals.

## Critical verification

Title similarity is insufficient. Before adding a mapping, compare the complete resolution rules, oracle/source, time cutoff/timezone, treatment of cancellations or revisions, and whether each side is eligible to trade in your jurisdiction. A false “match” can turn an apparent arbitrage into two correlated directional bets.
