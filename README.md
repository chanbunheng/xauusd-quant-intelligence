# XAU/USD Quantitative AI Intelligence Terminal (`xauusd-quant-intelligence`)

An institutional-grade **XAU/USD (Spot Gold)** quantitative signal engine, multi-timeframe analytics terminal, and autonomous Telegram execution hub powered by a **3-Agent AI Committee (`gemini-4-argon` architecture)**, live **TradingView WebSocket feeds**, and **Supabase PostgreSQL**.

---

## Core Architecture

1. **Live Multi-Broker TradingView Data Engine (`tradingview_mcp.py`)**
   - Streams real-time OHLCV candlesticks and tick quotes across `OANDA:XAUUSD`, `FX:XAUUSD`, and `FOREXCOM:XAUUSD` (`1m`, `5m`, `15m`, `1h`, `4h`, `1d`).
   - Tracks live US Dollar Index (`TVC:DXY`) inverse correlation and institutional wire headlines (Reuters / Dow Jones).

2. **Multi-Style Quantitative Strategy Engine (`analyze_gold_5m.py`)**
   - **Swing Trade (`1h` Default Specialist)**: EMA 21/50/200 structure, Fibonacci Golden Pocket (`38.2%–61.8%`) retracement zones, and `2.5x–4.0x ATR` targets.
   - **Intraday Session Trade (`15m` / `5m`)**: London & New York Killzone pullbacks and momentum breakouts.
   - **High-Frequency Scalping (`1m` / `5m`)**: Bollinger Band liquidity sweeps and RSI hooks.
   - **Macro Position Trade (`4h` / `1D`)**: Multi-week institutional structure and macro trend alignment.

3. **Pre-Signal 3-Agent AI Committee Gate**
   - **Agent 1 — Technical & Structure Strategist**: Audits EMA ribbon alignment, Fibonacci Golden Pocket location, and higher-timeframe confluence.
   - **Agent 2 — Macro & DXY Intelligence Agent**: Evaluates `TVC:DXY` dollar pressure, Reuters/Dow Jones gold wire sentiment, and high-impact macro catalysts (FOMC, CPI, NFP).
   - **Agent 3 — Chief Risk Officer (Final Gate)**: Enforces minimum Risk-to-Reward (`R:R`) ratios, blocks counter-trend or mid-air entries, and manages the **Strict Single-Position Lock** (one active trade per symbol/timeframe until `SL`, `TP1`, or `TP2` is reached).
   - Optional live cloud LLM synthesis via Google Gemini (`gemini-4-argon`).

4. **24/7 Autonomous Telegram Signal Hub (`@this_is_ai_signal_bot`)**
   - Interactive commands: `/start`, `/swing`, `/intraday`, `/scalp`, `/position`, `/news`, `/id`.
   - Autonomous 60-second cloud scanner pushes newly approved setups and real-time `TP1` / `TP2` / `SL` closure alerts to subscribed traders and groups.

5. **Cloud-Native Persistence (`db.py`)**
   - Primary storage on **Supabase PostgreSQL** (`ap-southeast-1`) protected by Row-Level Security (`RLS`), with automatic local SQLite (`gold_quant.db`) caching and fallback.

---

## Quick Start

### Local Development
```bash
pip install -r requirements.txt
python3 server.py
```
Open `http://127.0.0.1:8765` in your browser.

### Environment Variables (Railway / Production)
| Variable | Description |
| :--- | :--- |
| `HOST` | Bind address (`0.0.0.0` in cloud) |
| `PORT` | HTTP server port (`8765` default) |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Supabase API key |
| `SUPABASE_BOT_SECRET` | Private RLS header secret for database write/read authorization |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot token from `@BotFather` |
| `TELEGRAM_GROUP_ID` | Default Telegram group Chat ID for automated broadcasts |
| `GEMINI_API_KEY` | *(Optional)* Google Gemini API key for live cloud LLM synthesis |
