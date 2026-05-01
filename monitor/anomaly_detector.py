#!/usr/bin/env python3
"""
Market Anomaly Detector
=======================
Scans Binance spot pairs for:
  - Volatility spikes (sudden price moves)
  - Volume surges (abnormal trading activity)
  - Order book imbalances (aggressive buying/selling)

Run every 5 minutes. First to spot breakouts wins.

Usage:
  python anomaly_detector.py
"""
from __future__ import annotations

import json
import logging
import os
import time
from decimal import Decimal

import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("anomaly")

# ── Watchlist ────────────────────────────────────────────
# Top volume + high interest tokens
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
    "DOGEUSDT", "XRPUSDT", "ADAUSDT", "AVAXUSDT",
    "MATICUSDT", "LINKUSDT", "ARBUSDT", "PEPEUSDT",
]

# ── Thresholds ───────────────────────────────────────────
VOL_SPIKE_MULTIPLIER = 2.0       # Current volume > 2x average → alert
PRICE_MOVE_BPS = 500              # 5% price move in window → alert
# BALANCE_IMCALCULATION = 5      # >5x imbalance bid/ask → alert

HISTORY_PERIODS = 12             # Periods to calculate baseline
POLL_SEC = 300                    # Check every 5 min

Window: dict[str, list[dict]] = {}
for s in SYMBOLS:
    Window[s] = []


def fetch_ticker(symbol: str) -> dict:
    try:
        resp = requests.get("https://api.binance.com/api/v3/ticker/24hr", params={"symbol": symbol}, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return {}


def fetch_depth(symbol: str, limit: int = 20) -> dict:
    """Order book depth — spot buy/sell wall imbalances."""
    try:
        resp = requests.get("https://api.binance.com/api/v3/depth", params={"symbol": symbol, "limit": limit}, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return {}


def analyze_volume(symbol: str, data: dict) -> str | None:
    vol = float(data.get("volume", 0))
    quote_vol = float(data.get("quoteVolume", 0))
    Window[symbol].append(vol)

    # Keep rolling window
    if len(Window[symbol]) > HISTORY_PERIODS:
        Window[symbol].pop(0)

    if len(Window[symbol]) < HISTORY_PERIODS:
        return None  # Not enough history

    avg_vol = sum(Window[symbol]) / len(Window[symbol])
    if avg_vol > 0 and vol > avg_vol * VOL_SPIKE_MULTIPLIER:
        ratio = vol / avg_vol
        return f"📊 成交量暴增 {ratio:.1f}x (avg ${avg_vol:,.0f} → now ${quote_vol:,.0f})"

    return None


def analyze_price(symbol: str, data: dict) -> str | None:
    change_pct = float(data.get("priceChangePercent", 0))
    if abs(change_pct) * 100 >= PRICE_MOVE_BPS:
        direction = "📈" if change_pct > 0 else "📉"
        return f"{direction} 价格异动 {change_pct:+.2f}% (1h)"
    return None


def analyze_depth(symbol: str) -> str | None:
    depth = fetch_depth(symbol)
    if not depth:
        return None
    bids = sum(float(b[1]) for b in depth.get("bids", []))
    asks = sum(float(a[1]) for a in depth.get("asks", []))
    if asks < 1:
        return None
    ratio = bids / asks
    if ratio > 3:
        return f"🟢 买盘强势 {ratio:.1f}x (bids:{bids:.0f} asks:{asks:.0f})"
    elif ratio < 0.33:
        return f"🔴 卖盘强势 {1/ratio:.1f}x (asks:{asks:.0f} bids:{bids:.0f})"
    return None


def main():
    log.info("🔍 Anomaly Detector started — watching %d symbols every %ds", len(SYMBOLS), POLL_SEC)

    while True:
        alerts = []
        for symbol in SYMBOLS:
            try:
                ticker = fetch_ticker(symbol)
                if not ticker:
                    continue

                signals = []
                v = analyze_volume(symbol, ticker)
                if v:
                    signals.append(v)
                p = analyze_price(symbol, ticker)
                if p:
                    signals.append(p)
                d = analyze_depth(symbol)
                if d:
                    signals.append(d)

                if signals:
                    price = ticker.get("lastPrice", "?")
                    alerts.append(f"\n{symbol}  @ ${price}\n" + "\n".join(signals))

            except Exception as e:
                log.debug("Error analyzing %s: %s", symbol, e)

        if alerts:
            log.info("=" * 50)
            for alert in alerts:
                log.info(alert)
            log.info("=" * 50)
        else:
            log.debug("No anomalies detected — %d symbols clean", len(SYMBOLS))

        time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()
