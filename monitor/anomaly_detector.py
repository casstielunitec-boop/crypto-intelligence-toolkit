#!/usr/bin/env python3
"""
📊 Market Anomaly Detector
===========================
Scans top crypto pairs for volume surges, price breakouts, and order book
imbalances. No API key needed — uses Binance public endpoints only.

Run every 5 minutes:
  python anomaly_detector.py

Add to cron / Task Scheduler for continuous monitoring.
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
log = logging.getLogger("anomaly_detector")

# ── Watchlist (top volume pairs) ─────────────────────────
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
    "DOGEUSDT", "XRPUSDT", "ADAUSDT", "AVAXUSDT",
    "MATICUSDT", "LINKUSDT", "ARBUSDT", "PEPEUSDT",
]

# ── Thresholds ───────────────────────────────────────────
VOL_SPIKE_MIN = 2.0      # 2x average volume
PRICE_MOVE_BPS = 400     # 4% move in 24h = alert
IMBALANCE_RATIO = 3.0    # bid/ask ratio >3x = alert
HISTORY_SIZE = 12        # rolling window for baseline
POLL_SEC = 300           # 5 min

# ── Rolling Windows ──────────────────────────────────────
volume_history: dict[str, list[float]] = {s: [] for s in SYMBOLS}


def fetch_24hr(symbol: str) -> dict:
    """Fetch 24hr ticker (public, no key needed)."""
    try:
        r = requests.get(
            "https://api.binance.com/api/v3/ticker/24hr",
            params={"symbol": symbol},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.debug("fetch_24hr %s: %s", symbol, e)
        return {}


def fetch_depth(symbol: str, limit: int = 20) -> dict:
    try:
        r = requests.get(
            "https://api.binance.com/api/v3/depth",
            params={"symbol": symbol, "limit": limit},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.debug("fetch_depth %s: %s", symbol, e)
        return {}


def check_volume(symbol: str, data: dict) -> str | None:
    vol = float(data.get("volume", 0))
    quote_vol = float(data.get("quoteVolume", 0))
    history = volume_history[symbol]
    history.append(vol)

    if len(history) > HISTORY_SIZE:
        history.pop(0)

    if len(history) < HISTORY_SIZE:
        return None

    avg = sum(history) / len(history)
    if avg > 0 and vol > avg * VOL_SPIKE_MIN:
        ratio = vol / avg
        return (
            f"📊 {symbol}: Volume surge {ratio:.1f}x\n"
            f"   Avg ${quote_vol/avg:,.0f} → Now ${quote_vol:,.0f}"
        )
    return None


def check_price(data: dict) -> str | None:
    change_pct = float(data.get("priceChangePercent", 0))
    if abs(change_pct) * 100 >= PRICE_MOVE_BPS:
        emoji = "📈" if change_pct > 0 else "📉"
        symbol = data.get("symbol", "?")
        return f"{emoji} {symbol}: {change_pct:+.2f}% in 24h"
    return None


def check_depth(symbol: str) -> str | None:
    depth = fetch_depth(symbol, limit=20)
    if not depth:
        return None
    bids = sum(float(b[1]) for b in depth.get("bids", []))
    asks = sum(float(a[1]) for a in depth.get("asks", []))
    if asks < 0.1 or bids < 0.1:
        return None
    ratio = bids / asks
    if ratio > IMBALANCE_RATIO:
        return f"🟢 {symbol}: Buy wall {ratio:.1f}x (bids ${bids:,.0f} / asks ${asks:,.0f})"
    elif asks / bids > IMBALANCE_RATIO:
        return f"🔴 {symbol}: Sell wall {asks/bids:.1f}x (asks ${asks:,.0f} / bids ${bids:,.0f})"
    return None


def main():
    log.info("🔍 Anomaly Detector started — %d symbols, %ds interval", len(SYMBOLS), POLL_SEC)
    log.info("")

    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        # Single-shot mode for cron
        _run_once()
        return

    while True:
        _run_once()
        log.info("💤 Sleeping %ds...", POLL_SEC)
        print()
        time.sleep(POLL_SEC)


def _run_once():
    now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    alerts = []

    for symbol in SYMBOLS:
        ticker = fetch_24hr(symbol)
        if not ticker:
            continue

        alerts.extend(filter(None, [check_volume(symbol, ticker)]))
        alerts.extend(filter(None, [check_price(ticker)]))
        alerts.extend(filter(None, [check_depth(symbol)]))

    if alerts:
        print(f"\n{'='*50}")
        print(f"🚨 ANOMALY REPORT — {now}")
        print(f"{'='*50}")
        for a in alerts:
            print(f"  {a}")
        print(f"{'='*50}")
    else:
        print(f"  ✅ No anomalies — {now}")


if __name__ == "__main__":
    main()
