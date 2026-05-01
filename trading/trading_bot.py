#!/usr/bin/env python3
"""
Binance Spot Auto-Trading Bot (Minimal Self-Contained)
=======================================================
This is your trading engine in ~200 lines.

Features:
  - BUY/SELL with stop-loss and take-profit
  - Configurable position size and signal thresholds
  - Runs on BTCUSDT, ETHUSDT, or any spot pair
  - Dry-run mode for testing without real money

Setup:
  1. pip install requests python-dotenv
  2. Create .env with BINANCE_API_KEY and BINANCE_SECRET_KEY
  3. Set DRY_RUN=false when you're ready for real trades

Usage:
  python trading_bot.py BTCUSDT 0.001
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────
API_KEY = os.getenv("BINANCE_API_KEY", "")
API_SECRET = os.getenv("BINANCE_SECRET_KEY", "")
BASE_URL = os.getenv("BINANCE_BASE_URL", "https://api.binance.com")
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"

# ── Strategy Params ─────────────────────────────────────
ENTRY_MOMENTUM_BPS = 6       # Enter when short-term momentum > this
MIN_PROFIT_BPS = 15          # Fee gate: signal must exceed fees + buffer
STOP_LOSS_BPS = -30          # Exit if PnL drops below this
TAKE_PROFIT_BPS = 50         # Exit if PnL exceeds this
FAST_WINDOW = 8              # Periods for fast MA
SLOW_WINDOW = 34             # Periods for slow MA
INTERVAL_SEC = 180           # Seconds between ticks


# ── Binance API ─────────────────────────────────────────
def _sign(params: dict) -> str:
    qs = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    return hmac.new(API_SECRET.encode(), qs.encode(), hashlib.sha256).hexdigest()


def _request(method: str, endpoint: str, params: dict | None = None, signed: bool = False) -> dict:
    headers = {"X-MBX-APIKEY": API_KEY}
    url = BASE_URL + endpoint
    if signed and params:
        params["timestamp"] = int(time.time() * 1000)
        params["signature"] = _sign(params)
    resp = requests.request(method, url, params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_price(symbol: str) -> Decimal:
    data = _request("GET", "/api/v3/ticker/price", {"symbol": symbol})
    return Decimal(data["price"])


def get_account() -> dict:
    return _request("GET", "/api/v3/account", {}, signed=True)


def place_order(symbol: str, side: str, quantity: Decimal, order_type: str = "MARKET") -> dict:
    params = {
        "symbol": symbol,
        "side": side.upper(),
        "type": order_type.upper(),
        "quantity": f"{quantity:.6f}",
        "newClientOrderId": f"toolkit_{int(time.time()*1000)}",
    }
    endpoint = "/api/v3/order/test" if DRY_RUN else "/api/v3/order"
    return _request("POST", endpoint, params, signed=True)


# ── Strategy Engine ─────────────────────────────────────
def avg(values: list[Decimal], window: int) -> Decimal | None:
    if len(values) < window:
        return None
    return sum(values[-window:], Decimal("0")) / Decimal(window)


def momentum_bps(prices: list[Decimal]) -> Decimal | None:
    fast = avg(prices, FAST_WINDOW)
    slow = avg(prices, SLOW_WINDOW)
    if fast is None or slow is None:
        return None
    return ((fast - slow) / slow) * Decimal("10000")


def decide(symbol: str, prices: list[Decimal], position_qty: Decimal, position_entry: Decimal) -> str:
    """Returns: BUY | SELL | HOLD"""
    mom = momentum_bps(prices)
    if mom is None:
        return "HOLD"

    current = prices[-1] if prices else Decimal("0")

    # Check exit conditions
    if position_qty > 0 and position_entry > 0:
        pnl_bps = ((current - position_entry) / position_entry) * Decimal("10000")
        if pnl_bps <= STOP_LOSS_BPS:
            log.info("STOP LOSS triggered at %.1f bps", pnl_bps)
            return "SELL"
        if pnl_bps >= TAKE_PROFIT_BPS:
            log.info("TAKE PROFIT at %.1f bps", pnl_bps)
            return "SELL"

    # Check entry conditions
    if position_qty == 0 and mom >= ENTRY_MOMENTUM_BPS:
        signal = abs(mom)
        if signal >= MIN_PROFIT_BPS:
            return "BUY"

    return "HOLD"


# ── Main Loop ────────────────────────────────────────────
def run(symbol: str, qty: Decimal):
    prices: list[Decimal] = []
    position_qty = Decimal("0")
    position_entry = Decimal("0")
    tick = 0

    log.info("=== Toolkit Trading Bot ===")
    log.info("Symbol: %s | Qty: %s | Dry-pun: %s | Interval: %ss", symbol, qty, DRY_RUN, INTERVAL_SEC)
    log.info("Entry: %s bps | Stop: %s bps | TP: %s bps | FeeGate: %s bps",
             ENTRY_MOMENTUM_BPS, STOP_LOSS_BPS, TAKE_PROFIT_BPS, MIN_PROFIT_BPS)

    while True:
        tick += 1
        try:
            price = get_price(symbol)
            prices.append(price)
            if len(prices) > SLOW_WINDOW * 2:
                prices.pop(0)

            action = decide(symbol, prices, position_qty, position_entry)
            mom = momentum_bps(prices)

            if action == "BUY":
                result = place_order(symbol, "BUY", qty)
                position_qty = qty
                position_entry = price
                status = "TEST" if DRY_RUN else result.get("status", "?")
                log.info("🔵 BUY %s %s @ %s | status=%s", qty, symbol, price, status)

            elif action == "SELL":
                result = place_order(symbol, "SELL", position_qty)
                pnl_bps = ((price - position_entry) / position_entry) * Decimal("10000")
                status = "TEST" if DRY_RUN else result.get("status", "?")
                log.info("🔴 SELL %s %s @ %s | pnl=%.1f bps | status=%s",
                         position_qty, symbol, price, pnl_bps, status)
                position_qty = Decimal("0")
                position_entry = Decimal("0")

            else:
                if tick % 10 == 0:
                    log.debug("HOLD mom=%.1f bps prices=%d", mom or 0, len(prices))

        except requests.RequestException as e:
            log.error("API error: %s", e)
        except Exception as e:
            log.exception("Unexpected error: %s", e)

        time.sleep(INTERVAL_SEC)


# ── Entry Point ──────────────────────────────────────────
if __name__ == "__main__":
    import sys

    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    qty = Decimal(sys.argv[2]) if len(sys.argv) > 2 else Decimal("0.001")

    print(f"\n{'⚠️  DRY RUN MODE — no real orders' if DRY_RUN else '🚀 LIVE MODE — real orders enabled'}")
    print(f"Symbol: {symbol} | Qty: {qty}\n")

    run(symbol, qty)
