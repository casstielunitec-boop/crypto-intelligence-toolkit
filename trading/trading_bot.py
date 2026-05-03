#!/usr/bin/env python3
"""
Binance Spot Trading Bot
========================
Simple momentum-based strategy with dry-run mode.
~250 lines, zero bloat.

Setup:
  1. pip install requests python-dotenv
  2. Copy .env.example to .env, fill in your keys
  3. Run: python trading_bot.py BTCUSDT 0.001

The bot starts in DRY-RUN mode by default (no real orders).
Set DRY_RUN=false in .env to trade live.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

# Load .env from current dir or parent
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()

# ── Logging ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("trading_bot")

# ── Config ───────────────────────────────────────────────
API_KEY = os.getenv("BINANCE_API_KEY", "")
API_SECRET = os.getenv("BINANCE_SECRET_KEY", os.getenv("BINANCE_API_SECRET", ""))
BASE_URL = os.getenv("BINANCE_BASE_URL", "https://api.binance.com")
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"

if not API_KEY or not API_SECRET:
    log.error("❌ BINANCE_API_KEY and BINANCE_SECRET_KEY must be set in .env")
    sys.exit(1)

# ── Strategy Parameters ──────────────────────────────────
FAST_WINDOW = 8       # Fast SMA periods
SLOW_WINDOW = 34      # Slow SMA periods
STOP_LOSS_BPS = -30   # -0.3% stop-loss
TAKE_PROFIT_BPS = 50  # +0.5% take-profit
MIN_PROFIT_BPS = 15   # Fee gate: skip trades below this edge
INTERVAL_SEC = 180    # Seconds between cycles

# ── Binance API Helpers ──────────────────────────────────
def _sign(params: dict) -> str:
    qs = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    return hmac.new(API_SECRET.encode(), qs.encode(), hashlib.sha256).hexdigest()


def _request(method: str, endpoint: str, params: dict | None = None,
             signed: bool = False) -> dict | list:
    headers = {"X-MBX-APIKEY": API_KEY}
    url = BASE_URL + endpoint
    if signed:
        params = params or {}
        params["timestamp"] = int(time.time() * 1000)
        params["signature"] = _sign(params)
    try:
        resp = requests.request(method, url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        log.error("API error: %s — %s", e, resp.text[:200])
        raise
    except requests.exceptions.Timeout:
        log.warning("API timeout on %s %s", method, endpoint)
        raise


def get_price(symbol: str) -> Decimal:
    data = _request("GET", "/api/v3/ticker/price", {"symbol": symbol})
    return Decimal(str(data["price"]))


def get_klines(symbol: str, limit: int = 50, interval: str = "1m") -> list[dict]:
    """Fetch recent klines/candlesticks."""
    data = _request("GET", "/api/v3/klines", {
        "symbol": symbol, "interval": interval, "limit": limit
    })
    result = []
    for k in data:
        result.append({
            "time": k[0],
            "open": Decimal(str(k[1])),
            "high": Decimal(str(k[2])),
            "low": Decimal(str(k[3])),
            "close": Decimal(str(k[4])),
            "volume": Decimal(str(k[5])),
        })
    return result


def get_account_balance(asset: str = "USDT") -> Decimal:
    account = _request("GET", "/api/v3/account", {}, signed=True)
    for bal in account.get("balances", []):
        if bal["asset"] == asset:
            return Decimal(str(bal["free"]))
    return Decimal("0")


def get_position_qty(symbol: str) -> Decimal:
    """Get the free quantity of the base asset (e.g. BTC for BTCUSDT)."""
    base = symbol.replace("USDT", "")
    return get_account_balance(base)


def place_order(symbol: str, side: str, quantity: Decimal) -> dict:
    params = {
        "symbol": symbol,
        "side": side.upper(),
        "type": "MARKET",
        "quantity": f"{quantity:.6f}",
    }
    endpoint = "/api/v3/order/test" if DRY_RUN else "/api/v3/order"
    return _request("POST", endpoint, params, signed=True)


# ── Strategy ─────────────────────────────────────────────
def sma(values: list[Decimal], window: int) -> Decimal | None:
    if len(values) < window:
        return None
    return sum(values[-window:]) / Decimal(window)


def compute_signal(prices: list[Decimal]) -> dict:
    """Return dict with 'action' (BUY/SELL/HOLD), 'momentum_bps', details."""
    fast = sma(prices, FAST_WINDOW)
    slow = sma(prices, SLOW_WINDOW)
    if fast is None or slow is None or slow == 0:
        return {"action": "HOLD", "momentum_bps": 0, "reason": "warming up"}

    mom_bps = int(((fast - slow) / slow) * 10000)
    current = prices[-1]

    # Determine action
    if mom_bps > MIN_PROFIT_BPS:
        return {"action": "BUY", "momentum_bps": mom_bps,
                "reason": f"fast > slow by {mom_bps} bps"}
    elif mom_bps < -MIN_PROFIT_BPS:
        return {"action": "SELL", "momentum_bps": mom_bps,
                "reason": f"fast < slow by {abs(mom_bps)} bps"}
    else:
        return {"action": "HOLD", "momentum_bps": mom_bps,
                "reason": f"signal {mom_bps} bps inside fee gate"}


def should_exit(symbol: str, entry_price: Decimal, current_price: Decimal,
                position_qty: Decimal) -> str | None:
    """Return 'STOP_LOSS', 'TAKE_PROFIT', or None."""
    if position_qty == 0 or entry_price == 0:
        return None
    pnl_bps = int(((current_price - entry_price) / entry_price) * 10000)
    if pnl_bps <= STOP_LOSS_BPS:
        return "STOP_LOSS"
    if pnl_bps >= TAKE_PROFIT_BPS:
        return "TAKE_PROFIT"
    return None


# ── Main Loop ────────────────────────────────────────────
def main():
    if len(sys.argv) < 3:
        print("Usage: python trading_bot.py <SYMBOL> <QTY>")
        print("  Example: python trading_bot.py BTCUSDT 0.001")
        sys.exit(1)

    symbol = sys.argv[1].upper()
    qty = Decimal(str(sys.argv[2]))
    mode = "DRY-RUN" if DRY_RUN else "LIVE"

    log.info("=" * 50)
    log.info("🚀 Crypto Intelligence Trading Bot")
    log.info("  Symbol:     %s", symbol)
    log.info("  Quantity:   %s", qty)
    log.info("  Mode:       %s", mode)
    log.info("  Strategy:   SMA(%d, %d)", FAST_WINDOW, SLOW_WINDOW)
    log.info("  Interval:   %ds", INTERVAL_SEC)
    log.info("=" * 50)

    prices: list[Decimal] = []
    position_qty = Decimal("0")
    entry_price = Decimal("0")
    cycle = 0

    while True:
        cycle += 1
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        try:
            # Fetch data
            klines = get_klines(symbol, limit=SLOW_WINDOW + 5)
            close_prices = [k["close"] for k in klines]
            current_price = close_prices[-1]
            prices = close_prices

            # Update position info
            try:
                position_qty = get_position_qty(symbol.replace("USDT", ""))
                if position_qty > 0 and entry_price == 0:
                    # Estimate entry from current price if not set
                    entry_price = current_price
            except Exception:
                pass  # account endpoint may fail on free-tier IP

            # Check exit conditions
            exit_signal = should_exit(symbol, entry_price, current_price,
                                       position_qty)
            if exit_signal and position_qty > 0:
                log.info("🛑 %s triggered at %s (%s)", exit_signal,
                         current_price, now_utc)
                try:
                    result = place_order(symbol, "SELL", position_qty)
                    log.info("✅ SELL executed: %s", json.dumps(
                        result if isinstance(result, dict) else {}, default=str))
                except Exception as e:
                    log.error("SELL failed: %s", e)
                position_qty = Decimal("0")
                entry_price = Decimal("0")
                continue

            # Get trading signal
            sig = compute_signal(prices)
            action = sig["action"]

            # Act on signal
            if action in ("BUY", "SELL") and position_qty == 0:
                log.info("📡 Signal: %s (%s) — %s", action,
                         sig["reason"], now_utc)
                try:
                    result = place_order(symbol, action, qty)
                    log.info("✅ %s order placed: %s", action,
                             json.dumps(
                                 result if isinstance(result, dict) else {},
                                 default=str))
                    entry_price = current_price
                except Exception as e:
                    log.error("%s order failed: %s", action, e)
            elif action in ("BUY", "SELL") and position_qty > 0 and action == "SELL":
                log.info("📡 SELL signal while in position — %s", now_utc)
                try:
                    result = place_order(symbol, "SELL", position_qty)
                    log.info("✅ SELL executed: %s", json.dumps(
                        result if isinstance(result, dict) else {}, default=str))
                except Exception as e:
                    log.error("SELL failed: %s", e)
                position_qty = Decimal("0")
                entry_price = Decimal("0")
            else:
                log.info("⏸️  HOLD [%s] (%s)", sig["reason"], now_utc)

        except Exception as e:
            log.error("Cycle %d error: %s", cycle, e)

        time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    main()
