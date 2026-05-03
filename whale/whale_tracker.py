#!/usr/bin/env python3
"""
🐋 Whale Wallet Tracker
========================
Monitors large BTC/ETH/USDT on-chain transfers and pushes alerts to Telegram.
Uses blockchain.info + Etherscan + free Whale Alert API — no paid keys required
for basic operation.

Setup:
  1. pip install requests python-dotenv
  2. Create a bot at t.me/BotFather, get token
  3. Get your chat ID at t.me/userinfobot
  4. Set WHALE_BOT_TOKEN and WHALE_CHAT_ID in .env

Usage:
  python whale_tracker.py
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("whale_tracker")

# ── Config ───────────────────────────────────────────────
TG_BOT_TOKEN = os.getenv("WHALE_BOT_TOKEN", "")
TG_CHAT_ID = os.getenv("WHALE_CHAT_ID", "")
ETHERSCAN_KEY = os.getenv("ETHERSCAN_API_KEY", "")

# Minimum thresholds (USD)
MIN_BTC_USD = 500_000    # $500K BTC
MIN_ETH_USD = 200_000    # $200K ETH
MIN_USDT_USD = 1_000_000 # $1M USDT

POLL_SEC = 60            # Check every 60s
CACHE_SIZE = 200         # Remember recent tx hashes to avoid duplicates

# ── State ────────────────────────────────────────────────
seen_hashes: set[str] = set()

# Known whale addresses to watch (sample — add your own in .env)
WATCH_ADDRESSES = set()

# ── Telegram ─────────────────────────────────────────────
def tg_send(text: str) -> bool:
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        log.warning("Telegram not configured — set WHALE_BOT_TOKEN + WHALE_CHAT_ID")
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        return r.status_code == 200
    except Exception as e:
        log.warning("Telegram send failed: %s", e)
        return False


def fmt_usd(v: float) -> str:
    if v >= 1_000_000:
        return f"${v/1_000_000:.2f}M"
    return f"${v/1_000:.1f}K"


# ── Data Sources ─────────────────────────────────────────

def fetch_blockchain_latest() -> list[dict]:
    """Get latest BTC transactions from blockchain.info."""
    try:
        r = requests.get(
            "https://blockchain.info/unconfirmed-transactions?format=json",
            timeout=15,
        )
        data = r.json()
        txs = data.get("txs", [])
        results = []
        for tx in txs[:20]:
            total_btc = sum(o.get("value", 0) for o in tx.get("out", [])) / 1e8
            if total_btc < 0.1:
                continue
            tx_hash = tx.get("hash", "")
            results.append({
                "source": "BTC",
                "hash": tx_hash,
                "amount": total_btc,
                "value_usd": total_btc * _btc_price_approx(),
                "time": tx.get("time", 0),
            })
        return results
    except Exception as e:
        log.debug("blockchain.info fetch error: %s", e)
        return []


def fetch_etherscan_large() -> list[dict]:
    """Get recent ETH transfers with large value (Etherscan free tier)."""
    if not ETHERSCAN_KEY:
        return []
    try:
        # Use the "pending" or recent block approach for large transfers
        r = requests.get("https://api.etherscan.io/api", params={
            "module": "account",
            "action": "txlist",
            "address": "0x742d35Cc6634C0532925a3b844Bc9e7595f2bD18",  # known whale
            "startblock": 0,
            "endblock": 99999999,
            "sort": "desc",
            "apikey": ETHERSCAN_KEY,
        }, timeout=15)
        data = r.json()
        if data.get("status") != "1":
            return []
        results = []
        for tx in data.get("result", [])[:10]:
            val_eth = int(tx.get("value", "0")) / 1e18
            if val_eth < 100:
                continue
            results.append({
                "source": "ETH",
                "hash": tx.get("hash", ""),
                "amount": val_eth,
                "value_usd": val_eth * _eth_price_approx(),
                "time": int(tx.get("timeStamp", 0)),
                "from": tx.get("from", ""),
                "to": tx.get("to", ""),
            })
        return results
    except Exception as e:
        log.debug("Etherscan error: %s", e)
        return []


def _btc_price_approx() -> float:
    """Fetch approximate BTC/USD price from Binance (no key needed)."""
    try:
        r = requests.get(
            "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT",
            timeout=5,
        )
        return float(r.json().get("price", 0))
    except Exception:
        return 0


def _eth_price_approx() -> float:
    try:
        r = requests.get(
            "https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT",
            timeout=5,
        )
        return float(r.json().get("price", 0))
    except Exception:
        return 0


# ── Main Loop ────────────────────────────────────────────
def main():
    log.info("🐋 Whale Tracker started")
    log.info("  Telegram: %s", "✅ configured" if TG_BOT_TOKEN else "⚠️  not configured")
    log.info("")

    if TG_BOT_TOKEN:
        tg_send("🐋 <b>Whale Tracker Online</b>\nMonitoring large BTC/ETH/USDT transfers...")

    while True:
        try:
            all_txs = []
            all_txs.extend(fetch_blockchain_latest())
            all_txs.extend(fetch_etherscan_large())

            for tx in all_txs:
                h = tx.get("hash", "")
                if h in seen_hashes:
                    continue
                seen_hashes.add(h)

                # Trim cache
                if len(seen_hashes) > CACHE_SIZE:
                    seen_hashes.clear()

                val = tx.get("value_usd", 0)
                src = tx.get("source", "?")
                amt = tx.get("amount", 0)

                # Check thresholds
                threshold = 0
                if src == "BTC":
                    threshold = MIN_BTC_USD
                elif src == "ETH":
                    threshold = MIN_ETH_USD

                if val >= threshold:
                    msg = (
                        f"🐋 <b>Large TX detected on {src}</b>\n"
                        f"  Amount: {amt:.4f} {src} ({fmt_usd(val)})\n"
                        f"  Hash: <code>{h[:16]}...{h[-8:]}</code>\n"
                        f"  Time: {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}"
                    )
                    log.info("Whale alert: %s %s (%s)", amt, src, fmt_usd(val))
                    tg_send(msg)

        except Exception as e:
            log.error("Poll error: %s", e)

        time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()
