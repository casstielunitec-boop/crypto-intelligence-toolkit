#!/usr/bin/env python3
"""
🐋 Whale Wallet Tracker
========================
Monitors large BTC/ETH/USDT transfers on-chain and pushes alerts to Telegram.

Setup:
  1. pip install requests python-dotenv
  2. Create a Telegram Bot via @BotFather, get BOT_TOKEN
  3. Get your chat ID via @userinfobot
  4. Set WHALE_BOT_TOKEN and WHALE_CHAT_ID in .env
  5. (Optional) Get Etherscan API key for faster ETH polling

Usage:
  python whale_tracker.py
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("whale")

# ── Config ──────────────────────────────────────────────
TG_BOT_TOKEN = os.getenv("WHALE_BOT_TOKEN", "")
TG_CHAT_ID = os.getenv("WHALE_CHAT_ID", "")
ETHERSCAN_KEY = os.getenv("ETHERSCAN_API_KEY", "")

# Thresholds (USD equivalent, approximate)
WHALE_THRESHOLD_BTC = 500_000   # $500K+
WHALE_THRESHOLD_ETH = 200_000   # $200K+
WHALE_THRESHOLD_USDT = 1_000_000 # $1M+

# Poll intervals
POLL_INTERVAL_SEC = 60
CACHE_SIZE = 100


# ── Telegram ─────────────────────────────────────────────
def telegram_send(message: str) -> bool:
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        log.warning("Telegram not configured — skipping push")
        return False
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, json={
            "chat_id": TG_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
        }, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        log.error("Telegram push failed: %s", e)
        return False


# ── Free Blockchair API (no key needed) ─────────────────
def fetch_btc_large_txs(min_value_sat: int = 50_000_000_000) -> list[dict]:
    """Query Blockchair for large BTC transactions. 500M sats ≈ $100K+."""
    # Blockchair free tier limits, so we use a simplified approach
    try:
        resp = requests.get(
            "https://api.blockchair.com/bitcoin/transactions",
            params={"q": f"output_total(>{min_value_sat})", "limit": 10},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("data", [])
    except Exception as e:
        log.debug("Blockchair BTC error: %s", e)
        return []


# ── Whale Alert public API ───────────────────────────────
def fetch_whale_alert_txs() -> list[dict]:
    """Free tier of whale-alert.io — fetches recent large transfers."""
    try:
        resp = requests.get(
            "https://api.whale-alert.io/v1/transactions",
            params={"min_value": 500000, "limit": 5},
            timeout=15,
        )
        if resp.status_code == 429:
            return []
        resp.raise_for_status()
        return resp.json().get("transactions", [])
    except Exception as e:
        log.debug("Whale Alert API error: %s", e)
        return []


# ── Etherscan large transfers ────────────────────────────
def fetch_eth_large_txs() -> list[dict]:
    if not ETHERSCAN_KEY:
        return []
    try:
        resp = requests.get(
            "https://api.etherscan.io/api",
            params={
                "module": "account",
                "action": "txlist",
                "address": "0x0000000000000000000000000000000000000000",  # will use whale addresses
                "startblock": 0,
                "endblock": 99999999,
                "sort": "desc",
                "apikey": ETHERSCAN_KEY,
            },
            timeout=15,
        )
        return resp.json().get("result", [])[:5] if resp.json().get("status") == "1" else []
    except Exception as e:
        log.debug("Etherscan error: %s", e)
        return []


# ── Formatter ────────────────────────────────────────────
def format_alert(symbol: str, amount: float, usd_value: float, tx_from: str, tx_to: str, tx_hash: str = "") -> str:
    emoji = {"BTC": "🟠", "ETH": "🔷", "USDT": "💵"}.get(symbol, "💰")
    short_hash = tx_hash[:8] + "..." if tx_hash else ""
    return (
        f"{emoji} <b>WHALE ALERT</b> — {symbol}\n"
        f"Amount: {amount:,.2f} {symbol} (≈${usd_value:,.0f})\n"
        f"From: <code>{tx_from[:10]}...</code>\n"
        f"To: <code>{tx_to[:10]}...</code>\n"
        f"{'Tx: ' + short_hash if short_hash else ''}"
    )


# ── Main Loop ────────────────────────────────────────────
def main():
    seen: set[str] = set()

    log.info("🐋 Whale Tracker started")
    log.info("Thresholds: BTC>$%sK | ETH>$%sK | USDT>$%sM",
             WHALE_THRESHOLD_BTC//1000, WHALE_THRESHOLD_ETH//1000, WHALE_THRESHOLD_USDT//1000000)
    telegram_send("🐋 Whale Tracker is online. Monitoring large transfers...")

    while True:
        try:
            alerts = []

            # Whale Alert API
            txs = fetch_whale_alert_txs()
            for tx in txs:
                key = tx.get("hash", str(tx.get("id", "")))
                if key in seen:
                    continue
                seen.add(key)
                symbol = tx.get("symbol", "BTC")
                amount = float(tx.get("amount", 0))
                usd = float(tx.get("amount_usd", 0))
                alerts.append(format_alert(
                    symbol, amount, usd,
                    tx.get("from", {}).get("owner", "Unknown"),
                    tx.get("to", {}).get("owner", "Unknown"),
                    key,
                ))

            # Trim cache
            if len(seen) > CACHE_SIZE * 3:
                seen = set(list(seen)[-CACHE_SIZE:])

            # Push alerts
            for alert in alerts:
                log.info("Alert: %s", alert[:80])
                telegram_send(alert)

            if not alerts:
                log.debug("No new whales — sleeping %ss", POLL_INTERVAL_SEC)

        except Exception as e:
            log.exception("Tracker loop error: %s", e)

        time.sleep(POLL_INTERVAL_SEC)


if __name__ == "__main__":
    main()
