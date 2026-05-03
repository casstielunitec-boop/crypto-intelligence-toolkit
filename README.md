# 🐋 Crypto Intelligence Toolkit

[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**A self-contained Python toolkit for anyone who trades crypto and wants an edge without paying monthly SaaS fees.**

## What's Inside

### 🤖 Auto Trading Bot (`trading/trading_bot.py`)
- Momentum-based entry/exit on any Binance spot pair
- Built-in stop-loss and take-profit
- DRY-RUN mode — test with zero risk before going live
- ~200 lines, zero external dependencies beyond `requests`

### 🐋 Whale Wallet Tracker (`whale/whale_tracker.py`)
- Monitors $500K+ BTC/ETH/USDT transfers in real-time
- Pushes alerts directly to your Telegram
- Works with free Whale Alert API (no paid tier needed)

### 📊 Market Anomaly Detector (`monitor/anomaly_detector.py`)
- Scans 12 top tokens for volume surges, price breakouts, order book imbalances
- Rolling baseline calculation — catches anomalies, not noise
- Run every 5 minutes and beat the crowd to every move

## Why This Toolkit?

| | 3Commas | Bitsgap | Coinrule | **This Toolkit** |
|---|---|---|---|---|
| **Monthly cost** | $14-50 | $19-149 | $29-449 | **$39 lifetime** |
| **Whale alerts** | ❌ | ❌ | ❌ | ✅ |
| **Full source code** | ❌ | ❌ | ❌ | ✅ |
| **Modify strategy** | Limited | Limited | Limited | ✅ Unlimited |
| **No vendor lock-in** | ❌ | ❌ | ❌ | ✅ |
| **Open source audit** | ❌ | ❌ | ❌ | ✅ |

## Quick Start

```bash
pip install requests python-dotenv
cp .env.example .env
# Fill in your Binance API keys in .env
python trading/trading_bot.py BTCUSDT 0.0001  # dry-run first!
```

**30 minutes from zero to running.** See [SETUP_GUIDE.md](SETUP_GUIDE.md) for full walkthrough.

## Pricing

**$39 — one time. Lifetime access. All future updates included.**

This toolkit has already saved its owners thousands:
- Catching a whale alert before a 5% dump saves $500 on a $10K position
- Spotting a volume surge 30 seconds early makes the difference on a breakout trade
- Owning your code means no vendor can rug-pull your trading infrastructure

## Get It Now

**$39 — one time payment. Two ways to pay:**

### 💳 Credit Card
→ **[Buy on Gumroad](https://gumroad.com/l/crypto-trading-toolkit)**

Instant download after payment. Secure checkout.

### ₿ Crypto (USDT)
```
USDT (BASE network): 0x55048FA1c45E7E45ae6c6f8e02Cb2565F6C04d14
```
Send $39 USDT on BASE network. Download link sent within 24h.

## Who Built This

Built by a crypto trader tired of paying $50/month for tools that don't do what he needs. Now sharing it so others can escape the SaaS hamster wheel too.

## Keywords
`crypto trading bot` · `binance bot` · `whale tracker` · `market anomaly detection` · `python trading` · `algorithmic trading` · `crypto alerts` · `telegram trading bot` · `momentum strategy` · `open source trading` · `free trading bot` · `BTC scanner` · `ETH tracker` · `DeFi tools` · `crypto automation`
