from __future__ import annotations

import base64
import json
import os
import ssl
import time
from pathlib import Path
from urllib.request import Request, urlopen

from .client import KALSHI_BASE_URL


def load_dotenv(path: str = ".env") -> None:
    """Small dependency-free .env loader; never logs values."""
    file = Path(path)
    if not file.exists():
        return
    for line in file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _json(request: Request) -> object:
    import certifi
    context = ssl.create_default_context(cafile=certifi.where())
    with urlopen(request, timeout=20, context=context) as response:
        return json.load(response)


def kalshi_balance() -> object:
    """Fetch balance only. Requires a Kalshi key ID plus a PEM path or Base64 PEM."""
    key_id = os.environ["KALSHI_API_KEY_ID"]
    encoded_key = os.getenv("KALSHI_PRIVATE_KEY_B64")
    pem = base64.b64decode(encoded_key) if encoded_key else Path(
        os.environ["KALSHI_PRIVATE_KEY_PATH"]
    ).expanduser().read_bytes()
    timestamp = str(int(time.time() * 1000))
    path = "/trade-api/v2/portfolio/balance"
    message = (timestamp + "GET" + path).encode()

    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    private_key = serialization.load_pem_private_key(pem, password=None)
    signature = private_key.sign(
        message,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    headers = {
        "Accept": "application/json",
        "KALSHI-ACCESS-KEY": key_id,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode(),
        "KALSHI-ACCESS-TIMESTAMP": timestamp,
    }
    return _json(Request(KALSHI_BASE_URL + "/portfolio/balance", headers=headers))


def polymarket_positions() -> object:
    """Fetch Polymarket US positions using the account's API key pair."""
    return polymarket_us_get("/v1/portfolio/positions")


def polymarket_us_balances() -> object:
    """Fetch Polymarket US balances only; no trades, transfers, or writes occur."""
    return polymarket_us_get("/v1/account/balances")


def polymarket_us_get(path: str) -> object:
    key_id = os.environ["POLYMARKET_US_KEY_ID"]
    secret = os.environ["POLYMARKET_US_SECRET_KEY"]
    timestamp = str(int(time.time() * 1000))
    from cryptography.hazmat.primitives.asymmetric import ed25519

    # Polymarket US specifies the first 32 decoded bytes as the Ed25519 private key.
    private_key = ed25519.Ed25519PrivateKey.from_private_bytes(base64.b64decode(secret)[:32])
    signature = base64.b64encode(private_key.sign(f"{timestamp}GET{path}".encode())).decode()
    headers = {
        "Accept": "application/json",
        "User-Agent": "cross-venue-arbitrage-scanner/0.1",
        "X-PM-Access-Key": key_id,
        "X-PM-Timestamp": timestamp,
        "X-PM-Signature": signature,
    }
    return _json(Request("https://api.polymarket.us" + path, headers=headers))
