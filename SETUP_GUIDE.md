# 🛠️ 30-Minute Setup Guide

## Step 1: Install Dependencies (2 min)

```bash
pip install requests python-dotenv
```

## Step 2: Get Your API Keys (10 min)

### Binance (for trading bot + anomaly detector)
1. Go to [Binance.com](https://www.binance.com) → API Management
2. Create a new API key
3. **Enable**: Read + Spot Trading
4. **⚠️ DO NOT enable**: Withdraw
5. Copy `API Key` and `Secret Key`

### Telegram (for whale alerts)
1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow prompts
3. Copy the `BOT_TOKEN`
4. Message [@userinfobot](https://t.me/userinfobot) to get your `CHAT_ID`

### Etherscan (optional, for faster ETH tracking)
1. Go to [Etherscan.io](https://etherscan.io/register)
2. Register and get a free API key

## Step 3: Configure .env (3 min)

Rename `.env.example` to `.env` and fill in your keys:

```env
# Binance
BINANCE_API_KEY=your_key_here
BINANCE_SECRET_KEY=your_secret_here

# Telegram (whale tracker)
WHALE_BOT_TOKEN=your_bot_token
WHALE_CHAT_ID=your_chat_id

# Etherscan (optional)
ETHERSCAN_API_KEY=your_key_here

# Dry run mode — set to false when ready
DRY_RUN=true
```

## Step 4: Test Everything (10 min)

### Test 1: Trading Bot (Dry Run)
```bash
python trading/trading_bot.py BTCUSDT 0.0001
```
Should show "DRY RUN MODE" and log price ticks every 180s.

### Test 2: Whale Tracker
```bash
python whale/whale_tracker.py
```
Should connect to Whale Alert API and push to Telegram.

### Test 3: Anomaly Detector
```bash
python monitor/anomaly_detector.py
```
Should scan all 12 tokens and report anomalies.

## Step 5: Go Live (5 min)

1. Set `DRY_RUN=false` in `.env`
2. Start each script in separate terminal windows
3. Keep an eye on the first few trades

---

## 🚨 Safety Checklist (Read Before Going Live)

- [ ] API keys have NO withdraw permission
- [ ] Tested with DRY_RUN=true first
- [ ] Position size ≤ 5% of account
- [ ] Stop-loss is enabled
- [ ] You understand that trading crypto carries risk

---

## 📬 Need Help?

- Issues? DM me on the platform where you bought this
- Want custom features? I build trading infra for hire
- This toolkit is your base. Extend it however you want.
