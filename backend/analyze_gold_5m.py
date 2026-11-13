#!/usr/bin/env python3
"""
Pro Institutional TradingView Spot Gold (FX:XAUUSD / OANDA:XAUUSD / FOREXCOM:XAUUSD)
Signal Engine with:
- Multi-Style Trading Engine: SWING TRADE (Default & Specialty), INTRADAY, SCALPING, MACRO POSITION
- Pre-Signal AI Agent Layer (3-Agent Committee + Gemini 4 Argon Interactions API support) that vets,
  approves, refines, or vetoes candidate signals BEFORE final output
- Telegram Bot Integration (@this_is_ai_signal_bot) for automatic signal broadcasts & two-way commands
- Strict Single-Position Lock (1 active position at a time; scans for next only after SL/TP)
- Live Fundamental & Macro Intelligence (DXY correlation + Reuters/Dow Jones/TradingView Gold News NLP)
- Deep Historical Backtesting (450 Bars, 7 Days, 30 Days, 90 Days, 1 Year) stored in SQLite (gold_quant.db)
"""

import base64
import json
import math
import os
import random
import re
import socket
import ssl
import string
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from db import (
    DEFAULT_TELEGRAM_TOKEN,
    get_all_settings,
    get_backtest_run_details,
    get_backtest_runs,
    get_live_signals,
    get_setting,
    get_telegram_logs,
    get_telegram_subscribers,
    init_db,
    log_telegram_message,
    record_and_evaluate_live_signal,
    save_backtest_run,
    set_setting,
    upsert_telegram_subscriber,
)

HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "signals_history.json")
TZ_UTC7 = timezone(timedelta(hours=7))

TV_INTERVAL_MAP = {
    "1m": "1",
    "5m": "5",
    "15m": "15",
    "1h": "60",
    "4h": "240",
    "1d": "1D",
}

# Top 12 Institutional Global Assets (OANDA exclusive for Gold XAU/USD + Silver, Crypto, Indices, Forex, Top Stocks)
SUPPORTED_ASSETS = {
    "OANDA:XAUUSD":   {"symbol": "OANDA:XAUUSD",   "name": "Gold Spot (XAU/USD · OANDA)",   "short": "XAU/USD", "category": "Metals",  "decimals": 2},
    "OANDA:XAGUSD":   {"symbol": "OANDA:XAGUSD",   "name": "Silver Spot (XAG/USD · OANDA)", "short": "XAG/USD", "category": "Metals",  "decimals": 3},
    "BINANCE:BTCUSDT":{"symbol": "BINANCE:BTCUSDT","name": "Bitcoin (BTC/USDT)",            "short": "BTC/USD", "category": "Crypto",  "decimals": 2},
    "BINANCE:ETHUSDT":{"symbol": "BINANCE:ETHUSDT","name": "Ethereum (ETH/USDT)",           "short": "ETH/USD", "category": "Crypto",  "decimals": 2},
    "BINANCE:SOLUSDT":{"symbol": "BINANCE:SOLUSDT","name": "Solana (SOL/USDT)",             "short": "SOL/USD", "category": "Crypto",  "decimals": 2},
    "OANDA:SPX500USD":{"symbol": "OANDA:SPX500USD","name": "S&P 500 Index (SPX500)",        "short": "SPX500",  "category": "Indices", "decimals": 2},
    "OANDA:NAS100USD":{"symbol": "OANDA:NAS100USD","name": "Nasdaq 100 Tech (NAS100)",      "short": "NAS100",  "category": "Indices", "decimals": 2},
    "OANDA:EURUSD":   {"symbol": "OANDA:EURUSD",   "name": "EUR/USD Major Forex",           "short": "EUR/USD", "category": "Forex",   "decimals": 4},
    "OANDA:GBPUSD":   {"symbol": "OANDA:GBPUSD",   "name": "GBP/USD Cable Forex",           "short": "GBP/USD", "category": "Forex",   "decimals": 4},
    "OANDA:USDJPY":   {"symbol": "OANDA:USDJPY",   "name": "USD/JPY Yen Forex",             "short": "USD/JPY", "category": "Forex",   "decimals": 3},
    "NASDAQ:NVDA":    {"symbol": "NASDAQ:NVDA",    "name": "NVIDIA Corp (NVDA)",            "short": "NVDA",    "category": "Stocks",  "decimals": 2},
    "NASDAQ:AAPL":    {"symbol": "NASDAQ:AAPL",    "name": "Apple Inc (AAPL)",              "short": "AAPL",    "category": "Stocks",  "decimals": 2},
}

# Institutional Trading Strategies (SMC, ICT, Trend Pullback, Fib Golden Pocket, Wyckoff VSA, Bollinger, Breakout, Flexible)
TRADING_STRATEGIES = {
    "FLEXIBLE_HYBRID": {
        "code": "FLEXIBLE_HYBRID",
        "name": "Flexible AI Hybrid (All Strategies + Custom Rules)",
        "short": "Flexible AI",
        "badge": "ADAPTIVE AI",
        "description": "Runs SMC, ICT, Trend Pullback, Golden Pocket, Wyckoff VSA & Breakout in parallel and selects the highest-conviction setup matching your savedSL/TP and confidence filters.",
    },
    "SMC_ORDER_BLOCK": {
        "code": "SMC_ORDER_BLOCK",
        "name": "SMC (Break of Structure + Order Block + FVG)",
        "short": "SMC (BOS/OB/FVG)",
        "badge": "SMART MONEY",
        "description": "Institutional Smart Money Concepts: Detects Break of Structure (BOS/CHoCH), unmitigated 3-candle Fair Value Gaps (FVG), and institutional Order Block (OB) mitigation.",
    },
    "ICT_SILVER_BULLET": {
        "code": "ICT_SILVER_BULLET",
        "name": "ICT (Liquidity Sweep + Displacement + OTE)",
        "short": "ICT Silver Bullet",
        "badge": "ICT CONCEPTS",
        "description": "Inner Circle Trader methodology: Hunts Buy/Sell-Side Liquidity pools (Judas Sweep), requires displacement impulse + Optimal Trade Entry (OTE 61.8%–79% Fib / FVG).",
    },
    "TREND_PULLBACK": {
        "code": "TREND_PULLBACK",
        "name": "Trend Pullback (EMA 9/21/50/200 Ribbon)",
        "short": "Trend Pullback",
        "badge": "PRO TREND",
        "description": "Classic institutional trend continuation: Enters when price pulls back into stacked EMA 9/21/50 dynamic support/resistance with RSI(14) & MACD confirmation.",
    },
    "FIB_GOLDEN_POCKET": {
        "code": "FIB_GOLDEN_POCKET",
        "name": "Fibonacci Golden Pocket (38.2%–61.8% Wave)",
        "short": "Fib Golden Pocket",
        "badge": "HARMONIC WAVE",
        "description": "Measures multi-bar swing impulse waves and enters on institutional rejection inside the 38.2%–61.8% Fibonacci Golden Pocket retracement zone.",
    },
    "WYCKOFF_VSA": {
        "code": "WYCKOFF_VSA",
        "name": "Wyckoff Spring / Upthrust + Volume Spread (VSA)",
        "short": "Wyckoff & VSA",
        "badge": "WYCKOFF VSA",
        "description": "Detects accumulation Springs (false breakdown below range support closing back inside on high volume/wick) and distribution Upthrusts (UTAD).",
    },
    "BOLLINGER_MEAN_REV": {
        "code": "BOLLINGER_MEAN_REV",
        "name": "Bollinger 2σ + RSI Exhaustion Reversal",
        "short": "Bollinger Reversal",
        "badge": "MEAN REVERSION",
        "description": "Statistical mean-reversion: Captures exhaustion wicks outside 2.0σ Bollinger Bands paired with oversold (<32) or overbought (>68) RSI hooks.",
    },
    "TURTLE_BREAKOUT": {
        "code": "TURTLE_BREAKOUT",
        "name": "Donchian & Volatility Squeeze Breakout",
        "short": "Momentum Breakout",
        "badge": "BREAKOUT",
        "description": "Captures high-velocity expansion candles breaking out of N-bar Donchian structure highs/lows with stacked EMAs.",
    },
}

# Trading Styles Configuration (User's last choice is persisted in DB & localStorage)
TRADING_STYLES = {
    "SWING": {
        "code": "SWING",
        "name": "Swing Trade",
        "badge": "SWING MODE",
        "default_tf": "1h",
        "recommended_tfs": ["1h", "4h", "15m"],
        "mtf_list": ["15m", "1h", "4h", "1d"],
        "sl_mult": 1.5,
        "tp1_mult": 2.5,
        "tp2_mult": 4.0,
        "max_hold_bars": 96,
        "swing_lookback": 48,
        "hold_duration_label": "4 Hours – 3 Days (Multi-Session Swing Wave)",
        "description": (
            "Institutional Swing Mode: Targets multi-session waves using "
            "EMA 21/50/200 structure, 48-bar lookback zones, and 1.5x / 2.5x / 4.0x ATR targets."
        ),
    },
    "INTRADAY": {
        "code": "INTRADAY",
        "name": "Intraday Session Trade",
        "badge": "INTRADAY SESSION",
        "default_tf": "15m",
        "recommended_tfs": ["15m", "5m", "1h"],
        "mtf_list": ["5m", "15m", "1h", "4h"],
        "sl_mult": 1.2,
        "tp1_mult": 1.8,
        "tp2_mult": 3.0,
        "max_hold_bars": 72,
        "swing_lookback": 32,
        "hold_duration_label": "1 – 8 Hours (London / NY Session Wave)",
        "description": (
            "Intraday Session Strategy: Captures London & New York intraday trend expansions and "
            "session liquidity sweeps on 15m/5m structure with 1.2x ATR stops and 1.8x / 3.0x ATR targets."
        ),
    },
    "SCALPING": {
        "code": "SCALPING",
        "name": "High-Speed Scalping",
        "badge": "FAST SCALPER",
        "default_tf": "1m",
        "recommended_tfs": ["1m", "5m"],
        "mtf_list": ["1m", "5m", "15m", "1h"],
        "sl_mult": 1.0,
        "tp1_mult": 1.5,
        "tp2_mult": 2.0,
        "max_hold_bars": 60,
        "swing_lookback": 24,
        "hold_duration_label": "5 – 45 Minutes (Rapid Momentum Burst)",
        "description": (
            "Precision 1m/5m Momentum Scalper: Enters on tight EMA 9/21 pullbacks and Bollinger Band "
            "liquidity sweeps with rapid Break-Even protection at 1.5x ATR."
        ),
    },
    "POSITION": {
        "code": "POSITION",
        "name": "Macro Position Trade",
        "badge": "MACRO POSITION",
        "default_tf": "4h",
        "recommended_tfs": ["4h", "1d"],
        "mtf_list": ["15m", "1h", "4h", "1d"],
        "sl_mult": 1.8,
        "tp1_mult": 3.0,
        "tp2_mult": 5.0,
        "max_hold_bars": 120,
        "swing_lookback": 60,
        "hold_duration_label": "3 Days – 3 Weeks (Macro Trend Wave)",
        "description": (
            "Institutional 4H/Daily Position Strategy: Rides major macro Central Bank, DXY, and inflation "
            "cycles with deep 1.8x ATR stops and 3.0x / 5.0x ATR macro targets."
        ),
    },
}

DURATION_PRESETS = {
    "450_BARS": {"bars": 450, "label": "450 Bars (Standard)"},
    "1500_BARS": {"bars": 1500, "label": "1,500 Bars (~1-2 Weeks)"},
    "7_DAYS": {"bars": 2500, "label": "7 Days Deep"},
    "30_DAYS": {"bars": 5000, "force_min_tf": "5m", "label": "30 Days Deep"},
    "90_DAYS": {"bars": 5000, "force_min_tf": "15m", "label": "90 Days Deep"},
    "1_YEAR": {"bars": 7000, "force_min_tf": "1h", "label": "1 Year (365d) Deep"},
    "2_YEARS": {"bars": 14000, "force_min_tf": "1h", "label": "2 Years Deep"},
    "3_YEARS": {"bars": 10000, "force_min_tf": "4h", "label": "3 Years Deep"},
    "5_YEARS": {"bars": 15000, "force_min_tf": "4h", "label": "5 Years Deep"},
}

_FUNDAMENTAL_CACHE = {"ts": 0.0, "data": None}
_BOT_INFO_CACHE = {"ts": 0.0, "data": None}
_GEMINI_AGENT_CACHE = {}


def _ssl_context():
    cafile = "/etc/ssl/cert.pem" if os.path.exists("/etc/ssl/cert.pem") else None
    return ssl.create_default_context(cafile=cafile)


def _rand_id(prefix):
    return prefix + "_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=12))


def _tv_pack(func, params):
    msg = json.dumps({"m": func, "p": params}, separators=(",", ":"))
    return f"~m~{len(msg)}~m~{msg}"


def _ws_send(sock, text):
    payload = text.encode("utf-8")
    header = bytearray([0x81])
    length = len(payload)
    if length < 126:
        header.append(0x80 | length)
    elif length < 65536:
        header.append(0x80 | 126)
        header.extend(length.to_bytes(2, "big"))
    else:
        header.append(0x80 | 127)
        header.extend(length.to_bytes(8, "big"))
    mask = os.urandom(4)
    header.extend(mask)
    masked = bytearray(b ^ mask[i % 4] for i, b in enumerate(payload))
    sock.sendall(header + masked)


def _ws_recv_frame(sock):
    b12 = sock.recv(2)
    if len(b12) < 2:
        return None
    opcode = b12[0] & 0x0F
    length = b12[1] & 0x7F
    if length == 126:
        length = int.from_bytes(sock.recv(2), "big")
    elif length == 127:
        length = int.from_bytes(sock.recv(8), "big")
    data = bytearray()
    while len(data) < length:
        chunk = sock.recv(length - len(data))
        if not chunk:
            break
        data.extend(chunk)
    if opcode == 0x8:
        return None
    return data.decode("utf-8", errors="ignore")


def fetch_tradingview_candles(symbol="OANDA:XAUUSD", interval="1h", n_bars=450, min_timestamp=None):
    """
    Connects directly to TradingView's live chart WebSocket (wss://data.tradingview.com)
    to pull real-time OHLCV candles. Automatically paginates via `request_more_data`
    when more than 5,000 bars or an older `min_timestamp` is requested.
    """
    tv_int = TV_INTERVAL_MAP.get(interval, "60")
    host = "data.tradingview.com"
    ctx = _ssl_context()
    raw = socket.create_connection((host, 443), timeout=15)
    sock = ctx.wrap_socket(raw, server_hostname=host)
    sock.settimeout(15)
    try:
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        handshake = (
            f"GET /socket.io/websocket?from=chart%2F HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            f"Origin: https://www.tradingview.com\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n"
            f"User-Agent: Mozilla/5.0\r\n\r\n"
        )
        sock.sendall(handshake.encode("utf-8"))
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = sock.recv(1024)
            if not chunk:
                break
            resp += chunk

        cs = _rand_id("cs")
        _ws_send(sock, _tv_pack("set_auth_token", ["unauthorized_user_token"]))
        _ws_send(sock, _tv_pack("chart_create_session", [cs, ""]))
        _ws_send(
            sock,
            _tv_pack(
                "resolve_symbol",
                [cs, "sds_sym_1", f'={{"symbol":"{symbol}","adjustment":"splits"}}'],
            ),
        )
        initial_bars = min(max(int(n_bars), 50), 5000)
        _ws_send(sock, _tv_pack("create_series", [cs, "sds_1", "s1", "sds_sym_1", tv_int, initial_bars, ""]))

        bars_by_ts = {}
        last_batch_count = 0
        batches = 1
        max_batches = 7

        for _ in range(180):
            frame = _ws_recv_frame(sock)
            if not frame:
                break
            if frame.startswith("~m~") and "~h~" in frame:
                _ws_send(sock, frame)
            for m in re.finditer(r"~m~\d+~m~(\{.*?\})(?=~m~|$)", frame):
                try:
                    obj = json.loads(m.group(1))
                    if obj.get("m") == "timescale_update":
                        series = obj["p"][1].get("sds_1", {}).get("s", [])
                        for item in series:
                            v = item["v"]
                            ts = int(v[0])
                            dt_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
                            dt_local = datetime.fromtimestamp(ts, tz=TZ_UTC7)
                            c_val = float(v[4])
                            dec = 4 if c_val < 10 else (3 if c_val < 100 else 2)
                            bars_by_ts[ts] = {
                                "timestamp": ts,
                                "time": dt_utc.strftime("%Y-%m-%d %H:%M UTC"),
                                "time_local": dt_local.strftime("%Y-%m-%d %H:%M UTC+7"),
                                "open": round(float(v[1]), dec),
                                "high": round(float(v[2]), dec),
                                "low": round(float(v[3]), dec),
                                "close": round(c_val, dec),
                                "volume": round(float(v[5]) if len(v) > 5 else 0.0, 1),
                            }
                    if obj.get("m") == "series_completed":
                        cur_count = len(bars_by_ts)
                        oldest_ts = min(bars_by_ts.keys()) if bars_by_ts else None
                        need_more_bars = cur_count < n_bars
                        need_older_ts = (min_timestamp is not None) and (oldest_ts is None or oldest_ts > min_timestamp)
                        grew = cur_count > last_batch_count
                        if (need_more_bars or need_older_ts) and grew and batches < max_batches:
                            last_batch_count = cur_count
                            batches += 1
                            _ws_send(sock, _tv_pack("request_more_data", [cs, "sds_1", 5000]))
                        else:
                            bars = [bars_by_ts[k] for k in sorted(bars_by_ts.keys())]
                            return symbol, bars
                except Exception:
                    pass
        bars = [bars_by_ts[k] for k in sorted(bars_by_ts.keys())]
        return symbol, bars
    finally:
        try:
            sock.close()
        except Exception:
            pass


def fetch_fundamental_analysis(force=False):
    """
    Collects real-time Fundamental & Macro Intelligence for Gold (XAU/USD):
    1. Live U.S. Dollar Index (TVC:DXY) price, % change, RSI, and technical direction.
    2. Live institutional news headlines from TradingView (Reuters, Dow Jones, FXStreet).
    3. Sentiment scoring (Bullish vs Bearish Gold) + High-Impact Economic Event detection (CPI, NFP, FOMC, PPI, GDP).
    """
    now = time.time()
    if not force and _FUNDAMENTAL_CACHE["data"] and (now - _FUNDAMENTAL_CACHE["ts"] < 45):
        return _FUNDAMENTAL_CACHE["data"]

    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
    ctx = _ssl_context()

    dxy_info = {
        "symbol": "TVC:DXY",
        "price": 0.0,
        "change_pct": 0.0,
        "change_abs": 0.0,
        "rsi_5m": 50.0,
        "rec_5m": 0.0,
        "rec_1h": 0.0,
        "gold_impact": "NEUTRAL",
    }
    try:
        tv_url = "https://scanner.tradingview.com/cfd/scan"
        cols = ["close", "change", "change_abs", "RSI|5", "Recommend.All|5", "Recommend.All|60"]
        payload = json.dumps(
            {
                "symbols": {"tickers": ["TVC:DXY"], "query": {"types": []}},
                "columns": cols,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            tv_url,
            data=payload,
            headers={**headers, "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=6, context=ctx) as r:
            resp = json.loads(r.read().decode("utf-8"))
            rows = resp.get("data", [])
            if rows:
                d = dict(zip(cols, rows[0]["d"]))
                chg_pct = round(float(d.get("change") or 0.0), 2)
                rec_5m = round(float(d.get("Recommend.All|5") or 0.0), 2)
                rec_1h = round(float(d.get("Recommend.All|60") or 0.0), 2)
                if chg_pct >= 0.20 or rec_1h >= 0.25:
                    impact = "BEARISH"
                elif chg_pct <= -0.20 or rec_1h <= -0.25:
                    impact = "BULLISH"
                else:
                    impact = "NEUTRAL"
                dxy_info = {
                    "symbol": "TVC:DXY",
                    "price": round(float(d.get("close") or 0.0), 3),
                    "change_pct": chg_pct,
                    "change_abs": round(float(d.get("change_abs") or 0.0), 3),
                    "rsi_5m": round(float(d.get("RSI|5") or 50.0), 1),
                    "rec_5m": rec_5m,
                    "rec_1h": rec_1h,
                    "gold_impact": impact,
                }
    except Exception:
        pass

    bullish_words = [
        "rises", "gains", "climbs", "rebounds", "rally", "rallies", "jumps", "surges",
        "safe-haven", "safe haven", "rate cut", "dovish", "weaker dollar", "dollar slips",
        "dollar falls", "geopolitical", "support", "bullish", "highs", "buying", "demand",
    ]
    bearish_words = [
        "falls", "declines", "drops", "slips", "slides", "tumbles", "retreats", "loses",
        "stronger dollar", "lifting dollar", "yields rise", "hawkish", "tops forecasts",
        "hot inflation", "rate hike", "selloff", "pressure", "bearish", "lows", "outflows",
    ]
    event_keywords = {
        "CPI": "U.S. CPI Inflation Data",
        "NFP": "U.S. Nonfarm Payrolls (NFP)",
        "NONFARM": "U.S. Nonfarm Payrolls (NFP)",
        "FOMC": "Federal Reserve FOMC Decision",
        "POWELL": "Fed Chair Powell Speech",
        "FED ": "Federal Reserve Policy Update",
        "PPI": "U.S. PPI Producer Inflation",
        "GDP": "U.S. GDP Economic Release",
        "PCE": "U.S. Core PCE Inflation",
        "TARIFF": "Trade / Tariff Policy Headline",
    }

    headlines = []
    bull_count = 0
    bear_count = 0
    detected_events = []

    try:
        news_url = "https://news-headlines.tradingview.com/v2/view/headlines/symbol?client=web&lang=en&symbol=FX%3AXAUUSD"
        req = urllib.request.Request(news_url, headers=headers)
        with urllib.request.urlopen(req, timeout=6, context=ctx) as r:
            nd = json.loads(r.read().decode("utf-8"))
            for item in nd.get("items", [])[:12]:
                title = item.get("title", "").replace("\xa0", " ").strip()
                source = item.get("source", "TradingView")
                pub_ts = int(item.get("published") or 0)
                pub_str = (
                    datetime.fromtimestamp(pub_ts, tz=TZ_UTC7).strftime("%m-%d %H:%M UTC+7")
                    if pub_ts > 0
                    else ""
                )
                low_t = title.lower()
                b_score = sum(1 for w in bullish_words if w in low_t)
                s_score = sum(1 for w in bearish_words if w in low_t)
                if b_score > s_score:
                    sent = "BULLISH"
                    bull_count += 1
                elif s_score > b_score:
                    sent = "BEARISH"
                    bear_count += 1
                else:
                    sent = "NEUTRAL"

                up_t = title.upper()
                for ek, elabel in event_keywords.items():
                    if ek in up_t and elabel not in detected_events:
                        detected_events.append(elabel)

                headlines.append(
                    {
                        "title": title,
                        "source": source,
                        "published": pub_str,
                        "sentiment": sent,
                        "story_url": f"https://www.tradingview.com{item.get('storyPath', '')}"
                        if item.get("storyPath")
                        else "",
                    }
                )
    except Exception:
        pass

    score = 0
    if dxy_info["gold_impact"] == "BEARISH":
        score -= min(45, int(abs(dxy_info["change_pct"]) * 40 + 15))
    elif dxy_info["gold_impact"] == "BULLISH":
        score += min(45, int(abs(dxy_info["change_pct"]) * 40 + 15))

    net_news = bull_count - bear_count
    score += max(-45, min(45, net_news * 12))
    score = max(-100, min(100, score))

    if score >= 15:
        bias = "BULLISH"
    elif score <= -15:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"

    summary_parts = []
    if dxy_info["price"] > 0:
        summary_parts.append(
            f"DXY at {dxy_info['price']:.2f} ({dxy_info['change_pct']:+.2f}% → {dxy_info['gold_impact']} for Gold)"
        )
    summary_parts.append(f"News Flow: {bull_count} Bullish vs {bear_count} Bearish headlines")
    if detected_events:
        summary_parts.append(f"Active Catalysts: {', '.join(detected_events[:2])}")

    result = {
        "bias": bias,
        "score": score,
        "summary": " · ".join(summary_parts),
        "dxy": dxy_info,
        "bullish_headlines": bull_count,
        "bearish_headlines": bear_count,
        "high_impact_events": detected_events[:3],
        "headlines": headlines[:8],
    }
    _FUNDAMENTAL_CACHE["ts"] = now
    _FUNDAMENTAL_CACHE["data"] = result
    return result


def fetch_live_tv_tick(symbol="OANDA:XAUUSD"):
    """
    Fast (<150ms) live tick & multi-timeframe summary from TradingView Global Scanner API.
    Supports OANDA:XAUUSD (exclusive XAU broker feed) + top global Crypto, Indices, Forex, and Stocks.
    """
    tv_url = "https://scanner.tradingview.com/global/scan"
    cols = [
        "close", "open", "high", "low", "change", "change_abs",
        "close|1", "open|1", "high|1", "low|1", "RSI|1", "Recommend.All|1",
        "close|5", "open|5", "high|5", "low|5", "RSI|5", "Recommend.All|5",
        "close|15", "RSI|15", "Recommend.All|15",
        "close|60", "RSI|60", "Recommend.All|60",
        "close|240", "RSI|240", "Recommend.All|240",
        "RSI", "Recommend.All",
    ]
    tickers = list(SUPPORTED_ASSETS.keys()) + ["TVC:DXY"]
    payload = json.dumps(
        {
            "symbols": {
                "tickers": tickers,
                "query": {"types": []},
            },
            "columns": cols,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        tv_url,
        data=payload,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=6, context=_ssl_context()) as r:
        resp = json.loads(r.read().decode("utf-8"))

    brokers = {}
    selected = None
    for item in resp.get("data", []):
        sym = item["s"]
        d = dict(zip(cols, item["d"]))
        c_val = float(d.get("close") or 0)
        asset_meta = SUPPORTED_ASSETS.get(sym, {})
        dec = asset_meta.get("decimals", 4 if 0 < c_val < 10 else (3 if 0 < c_val < 100 else 2))
        brokers[sym] = {
            "symbol": sym,
            "name": asset_meta.get("name", sym),
            "short": asset_meta.get("short", sym.split(":")[-1]),
            "category": asset_meta.get("category", "Macro"),
            "decimals": dec,
            "price": round(c_val, dec),
            "day_open": round(float(d.get("open") or 0), dec),
            "day_high": round(float(d.get("high") or 0), dec),
            "day_low": round(float(d.get("low") or 0), dec),
            "change_pct": round(float(d.get("change") or 0), 2),
            "change_abs": round(float(d.get("change_abs") or 0), dec),
            "tv_recommend_1m": round(float(d.get("Recommend.All|1") or 0), 3),
            "tv_recommend_5m": round(float(d.get("Recommend.All|5") or 0), 3),
            "tv_recommend_15m": round(float(d.get("Recommend.All|15") or 0), 3),
            "tv_recommend_1h": round(float(d.get("Recommend.All|60") or 0), 3),
            "tv_recommend_4h": round(float(d.get("Recommend.All|240") or 0), 3),
            "tv_recommend_1d": round(float(d.get("Recommend.All") or 0), 3),
        }
        if sym == symbol:
            selected = brokers[sym]

    if not selected and brokers:
        selected = brokers.get("OANDA:XAUUSD") or next(iter(brokers.values()))

    now_utc = datetime.now(timezone.utc)
    now_local = datetime.now(TZ_UTC7)
    return {
        "symbol": symbol,
        "timestamp_utc": now_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "timestamp_local": now_local.strftime("%H:%M:%S UTC+7"),
        "active": selected,
        "brokers": brokers,
        "supported_assets": SUPPORTED_ASSETS,
    }


def ema_series(values, period):
    if not values:
        return []
    k = 2.0 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def rsi_series(closes, period=14):
    if len(closes) < 2:
        return [50.0] * len(closes)
    out = [50.0]
    gains = []
    losses = []
    prev_avg_g = 0.0
    prev_avg_l = 0.0
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
        if i < period:
            avg_g = sum(gains) / len(gains)
            avg_l = sum(losses) / len(losses)
        elif i == period:
            avg_g = sum(gains[:period]) / period
            avg_l = sum(losses[:period]) / period
        else:
            avg_g = (prev_avg_g * (period - 1) + gains[-1]) / period
            avg_l = (prev_avg_l * (period - 1) + losses[-1]) / period
        prev_avg_g, prev_avg_l = avg_g, avg_l
        if avg_l == 0:
            out.append(100.0)
        else:
            rs = avg_g / avg_l
            out.append(100.0 - (100.0 / (1.0 + rs)))
    return out


def macd_series(closes, fast=12, slow=26, sig=9):
    if not closes:
        return [], [], []
    ema_fast = ema_series(closes, fast)
    ema_slow = ema_series(closes, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = ema_series(macd_line, sig)
    hist = [m - s for m, s in zip(macd_line, signal_line)]
    return macd_line, signal_line, hist


def bollinger_series(closes, period=20, num_std=2.0):
    upper, mid, lower = [], [], []
    dec = 4 if (closes and closes[-1] < 10) else (3 if (closes and closes[-1] < 100) else 2)
    for i in range(len(closes)):
        window = closes[max(0, i - period + 1) : i + 1]
        mean = sum(window) / len(window)
        variance = sum((x - mean) ** 2 for x in window) / len(window)
        sd = math.sqrt(variance)
        mid.append(round(mean, dec))
        upper.append(round(mean + num_std * sd, dec))
        lower.append(round(mean - num_std * sd, dec))
    return upper, mid, lower


def atr_series(candles, period=14):
    if not candles:
        return []
    trs = [candles[0]["high"] - candles[0]["low"]]
    for i in range(1, len(candles)):
        h = candles[i]["high"]
        l = candles[i]["low"]
        pc = candles[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    out = []
    val = trs[0]
    min_floor = max(candles[-1]["close"] * 0.0002, 0.0001)
    for i, tr in enumerate(trs):
        if i < period:
            val = sum(trs[: i + 1]) / (i + 1)
        else:
            val = (val * (period - 1) + tr) / period
        out.append(max(val, min_floor))
    return out


def compute_signal_at(
    idx,
    candles,
    ema9_s,
    ema21_s,
    ema50_s,
    rsi_s,
    atr_s,
    macd_h,
    bb_u=None,
    bb_l=None,
    ema200_s=None,
    trading_style="SWING",
    strategy="FLEXIBLE_HYBRID",
    sl_mult=None,
    tp1_mult=None,
    tp2_mult=None,
    min_confidence=70,
    fundamental_bias="NEUTRAL",
    fundamental_score=0,
):
    """
    Multi-Style & Multi-Strategy Institutional Signal Engine:
    Supports 4 Trading Styles (SCALPING, INTRADAY, SWING, POSITION) and 8 Selectable Bot Strategies:
    1. FLEXIBLE_HYBRID: Evaluates all 7 institutional algorithms in parallel & picks highest conviction >= min_confidence
    2. SMC_ORDER_BLOCK: Smart Money Concepts (BOS/CHoCH + 3-bar Fair Value Gap FVG + Order Block OB mitigation)
    3. ICT_SILVER_BULLET: Inner Circle Trader (Liquidity Pool Judas Sweep + Displacement + OTE 61.8%-79% Fib)
    4. TREND_PULLBACK: EMA 9/21/50/200 Ribbon dynamic pullback + RSI/MACD impulse
    5. FIB_GOLDEN_POCKET: 38.2%-61.8% Fibonacci Golden Pocket wave rejection
    6. WYCKOFF_VSA: Wyckoff Spring / Upthrust (UTAD) false-breakout rejection + Volume Spread Analysis
    7. BOLLINGER_MEAN_REV: 2.0σ Bollinger Band exhaustion pierce + RSI hook reversal
    8. TURTLE_BREAKOUT: Donchian N-bar volatility squeeze breakout with stacked EMAs
    """
    style_cfg = TRADING_STYLES.get(trading_style, TRADING_STYLES["SWING"])
    strat_cfg = TRADING_STRATEGIES.get(strategy, TRADING_STRATEGIES["FLEXIBLE_HYBRID"])
    if sl_mult is None:
        sl_mult = style_cfg["sl_mult"]
    if tp1_mult is None:
        tp1_mult = style_cfg["tp1_mult"]
    if tp2_mult is None:
        tp2_mult = style_cfg["tp2_mult"]

    lookback = style_cfg["swing_lookback"]

    c = candles[idx]
    prev_c = candles[max(0, idx - 1)]
    prev2_c = candles[max(0, idx - 2)]
    prev3_c = candles[max(0, idx - 3)]
    price = c["close"]
    open_p = c["open"]
    high_p = c["high"]
    low_p = c["low"]
    dec = 4 if price < 10 else (3 if price < 100 else 2)

    ema9 = ema9_s[idx]
    ema21 = ema21_s[idx]
    ema50 = ema50_s[idx]
    ema200 = ema200_s[idx] if ema200_s else ema50
    prev_ema9 = ema9_s[max(0, idx - 1)]
    rsi14 = rsi_s[idx]
    prev_rsi = rsi_s[max(0, idx - 1)]
    atr14 = max(atr_s[idx], max(price * 0.0002, 0.0001))
    hist = macd_h[idx]
    prev_hist = macd_h[max(0, idx - 1)]

    window_start = max(0, idx - lookback)
    recent_high = max(x["high"] for x in candles[window_start : idx + 1])
    recent_low = min(x["low"] for x in candles[window_start : idx + 1])
    swing_range = max(recent_high - recent_low, atr14 * 0.1)

    # Prior structure window (excluding current bar) for sweeps & breakouts
    prior_slice = candles[max(0, idx - max(12, lookback // 2)) : idx] if idx >= 3 else [c]
    prior_high = max(x["high"] for x in prior_slice)
    prior_low = min(x["low"] for x in prior_slice)

    # Fibonacci Golden Pocket (38.2% - 61.8%) & ICT OTE (61.8% - 79.0%)
    fib_382_bull = recent_high - 0.382 * swing_range
    fib_500_bull = recent_high - 0.500 * swing_range
    fib_618_bull = recent_high - 0.618 * swing_range
    fib_790_bull = recent_high - 0.790 * swing_range
    fib_382_bear = recent_low + 0.382 * swing_range
    fib_618_bear = recent_low + 0.618 * swing_range
    fib_790_bear = recent_low + 0.790 * swing_range

    in_bull_golden_zone = (fib_618_bull - 0.45 * atr14) <= low_p <= (fib_382_bull + 0.45 * atr14)
    in_bear_golden_zone = (fib_382_bear - 0.45 * atr14) <= high_p <= (fib_618_bear + 0.45 * atr14)
    in_bull_ote = (fib_790_bull - 0.35 * atr14) <= low_p <= (fib_618_bull + 0.45 * atr14)
    in_bear_ote = (fib_618_bear - 0.45 * atr14) <= high_p <= (fib_790_bear + 0.35 * atr14)

    bar_range = max(high_p - low_p, atr14 * 0.05)
    body = abs(price - open_p)
    body_ratio = body / bar_range
    lower_wick = min(price, open_p) - low_p
    upper_wick = high_p - max(price, open_p)

    bull_candle = (price > open_p and body_ratio >= 0.25) or (price >= open_p and lower_wick >= 0.42 * bar_range)
    bear_candle = (price < open_p and body_ratio >= 0.25) or (price <= open_p and upper_wick >= 0.42 * bar_range)
    bull_displacement = (price > open_p and body >= 0.45 * atr14) or (
        prev_c["close"] > prev_c["open"] and abs(prev_c["close"] - prev_c["open"]) >= 0.45 * atr14 and bull_candle
    )
    bear_displacement = (price < open_p and body >= 0.45 * atr14) or (
        prev_c["close"] < prev_c["open"] and abs(prev_c["close"] - prev_c["open"]) >= 0.45 * atr14 and bear_candle
    )

    # EMA Trend Structure
    if trading_style in ("SWING", "POSITION"):
        uptrend_structure = (ema21 >= ema50 - 0.25 * atr14) and (price >= ema50 - 0.35 * atr14) and (ema9 >= ema21 - 0.25 * atr14)
        downtrend_structure = (ema21 <= ema50 + 0.25 * atr14) and (price <= ema50 + 0.35 * atr14) and (ema9 <= ema21 + 0.25 * atr14)
    else:
        uptrend_structure = ema9 >= ema21 - 0.1 * atr14 and price > ema21 - 0.15 * atr14 and ema21 >= ema50 - 0.35 * atr14
        downtrend_structure = ema9 <= ema21 + 0.1 * atr14 and price < ema21 + 0.15 * atr14 and ema21 <= ema50 + 0.35 * atr14

    touched_buy_zone = (
        low_p <= ema9 + 0.45 * atr14
        or prev_c["low"] <= ema9_s[max(0, idx - 1)] + 0.45 * atr14
        or prev2_c["low"] <= ema21_s[max(0, idx - 2)] + 0.5 * atr14
        or in_bull_golden_zone
    ) and (price - ema21) <= 2.0 * atr14

    touched_sell_zone = (
        high_p >= ema9 - 0.45 * atr14
        or prev_c["high"] >= ema9_s[max(0, idx - 1)] - 0.45 * atr14
        or prev2_c["high"] >= ema21_s[max(0, idx - 2)] - 0.5 * atr14
        or in_bear_golden_zone
    ) and (ema21 - price) <= 2.0 * atr14

    bull_momentum = (hist >= prev_hist or hist > 0) and (38 <= rsi14 <= 70) and (price >= prev_c["close"])
    bear_momentum = (hist <= prev_hist or hist < 0) and (30 <= rsi14 <= 62) and (price <= prev_c["close"])

    # SMC: 3-candle Fair Value Gap (FVG) & Order Block (OB) + Break of Structure (BOS)
    bull_fvg = False
    bear_fvg = False
    for k in range(max(2, idx - 6), idx + 1):
        if candles[k]["low"] > candles[k - 2]["high"]:
            bull_fvg = True
        if candles[k]["high"] < candles[k - 2]["low"]:
            bear_fvg = True

    smc_bull_bos = (price > prev_c["high"] or ema9 > ema21) and (ema21 >= ema50 - 0.35 * atr14)
    smc_bear_bos = (price < prev_c["low"] or ema9 < ema21) and (ema21 <= ema50 + 0.35 * atr14)
    smc_bull_ob = (in_bull_golden_zone or touched_buy_zone or bull_fvg) and bull_candle and (bull_displacement or bull_momentum)
    smc_bear_ob = (in_bear_golden_zone or touched_sell_zone or bear_fvg) and bear_candle and (bear_displacement or bear_momentum)

    # ICT: Liquidity Sweep (Judas swing below prior low / equal lows or into OTE) + Displacement
    ict_bull_sweep = (
        low_p <= prior_low + 0.25 * atr14
        or prev_c["low"] <= prior_low + 0.25 * atr14
        or in_bull_ote
        or (in_bull_golden_zone and lower_wick >= 0.30 * bar_range)
    )
    ict_bear_sweep = (
        high_p >= prior_high - 0.25 * atr14
        or prev_c["high"] >= prior_high - 0.25 * atr14
        or in_bear_ote
        or (in_bear_golden_zone and upper_wick >= 0.30 * bar_range)
    )
    ict_bull_ok = ict_bull_sweep and bull_candle and price > prev_c["close"] and rsi14 >= prev_rsi
    ict_bear_ok = ict_bear_sweep and bear_candle and price < prev_c["close"] and rsi14 <= prev_rsi

    # Wyckoff Spring / Upthrust (UTAD) & Volume Spread Analysis (VSA)
    avg_vol = sum(x.get("volume", 1.0) for x in prior_slice) / max(len(prior_slice), 1)
    vol_ratio = (c.get("volume", 1.0) / avg_vol) if avg_vol > 0 else 1.0
    wyckoff_spring = (
        (low_p <= prior_low + 0.35 * atr14 or prev_c["low"] <= prior_low + 0.35 * atr14)
        and price > prior_low
        and bull_candle
        and (lower_wick >= 0.30 * bar_range or vol_ratio >= 0.9 or rsi14 > prev_rsi)
    )
    wyckoff_utad = (
        (high_p >= prior_high - 0.35 * atr14 or prev_c["high"] >= prior_high - 0.35 * atr14)
        and price < prior_high
        and bear_candle
        and (upper_wick >= 0.30 * bar_range or vol_ratio >= 0.9 or rsi14 < prev_rsi)
    )

    # Bollinger 2.0σ + RSI Exhaustion Reversal
    bb_low_val = bb_l[idx] if bb_l else recent_low
    bb_high_val = bb_u[idx] if bb_u else recent_high
    prev_bb_low = bb_l[max(0, idx - 1)] if bb_l else recent_low
    prev_bb_high = bb_u[max(0, idx - 1)] if bb_u else recent_high

    bb_bull_rev = (
        (low_p <= bb_low_val + 0.15 * atr14 or prev_c["low"] <= prev_bb_low + 0.15 * atr14 or prev_rsi <= 35 or rsi14 <= 35)
        and bull_candle
        and price > prev_c["close"]
        and rsi14 > prev_rsi
    )
    bb_bear_rev = (
        (high_p >= bb_high_val - 0.15 * atr14 or prev_c["high"] >= prev_bb_high - 0.15 * atr14 or prev_rsi >= 65 or rsi14 >= 65)
        and bear_candle
        and price < prev_c["close"]
        and rsi14 < prev_rsi
    )

    # Donchian / Turtle Structure Breakout
    brk_len = 12 if trading_style in ("SWING", "POSITION") else 8
    prev_brk_high = max(x["high"] for x in candles[max(0, idx - brk_len) : idx]) if idx >= 2 else high_p
    prev_brk_low = min(x["low"] for x in candles[max(0, idx - brk_len) : idx]) if idx >= 2 else low_p
    bull_breakout = (
        ema9 >= ema21 >= ema50 - 0.2 * atr14
        and bull_candle
        and price > prev_brk_high
        and body >= 0.40 * atr14
        and 50 <= rsi14 <= 74
    )
    bear_breakout = (
        ema9 <= ema21 <= ema50 + 0.2 * atr14
        and bear_candle
        and price < prev_brk_low
        and body >= 0.40 * atr14
        and 26 <= rsi14 <= 50
    )

    # Evaluate individual strategy candidates: (direction, signal_type, signal_label, base_conf, reason)
    candidates = {}

    # 1. TREND_PULLBACK
    if uptrend_structure and touched_buy_zone and bull_candle and bull_momentum and ema9 >= prev_ema9 - 0.08 * atr14:
        candidates["TREND_PULLBACK"] = (
            "BUY",
            "TREND_PULLBACK",
            f"BUY ({style_cfg['code'].title()} EMA Trend Pullback)",
            84,
            f"Trend Pullback Confirmed: EMA21 ({ema21:.{dec}f}) >= EMA50 ({ema50:.{dec}f}), price rejected dynamic EMA support with bullish impulse & RSI {rsi14:.1f}.",
        )
    elif downtrend_structure and touched_sell_zone and bear_candle and bear_momentum and ema9 <= prev_ema9 + 0.08 * atr14:
        candidates["TREND_PULLBACK"] = (
            "SELL",
            "TREND_PULLBACK",
            f"SELL ({style_cfg['code'].title()} EMA Trend Pullback)",
            84,
            f"Trend Pullback Confirmed: EMA21 ({ema21:.{dec}f}) <= EMA50 ({ema50:.{dec}f}), price rejected dynamic EMA supply with bearish impulse & RSI {rsi14:.1f}.",
        )

    # 2. SMC_ORDER_BLOCK
    if smc_bull_bos and smc_bull_ob:
        candidates["SMC_ORDER_BLOCK"] = (
            "BUY",
            "SMC_ORDER_BLOCK",
            f"BUY (SMC Bullish BOS + {'FVG' if bull_fvg else 'Order Block'})",
            86 if bull_fvg else 83,
            f"Smart Money Concepts (SMC) BUY: Bullish Break of Structure with {'3-bar Fair Value Gap (FVG) & ' if bull_fvg else ''}Order Block mitigation near {fib_500_bull:.{dec}f}.",
        )
    elif smc_bear_bos and smc_bear_ob:
        candidates["SMC_ORDER_BLOCK"] = (
            "SELL",
            "SMC_ORDER_BLOCK",
            f"SELL (SMC Bearish BOS + {'FVG' if bear_fvg else 'Order Block'})",
            86 if bear_fvg else 83,
            f"Smart Money Concepts (SMC) SELL: Bearish Break of Structure with {'3-bar Fair Value Gap (FVG) & ' if bear_fvg else ''}Supply Order Block mitigation near {fib_500_bull:.{dec}f}.",
        )

    # 3. ICT_SILVER_BULLET
    if ict_bull_ok and (bull_displacement or bull_fvg or in_bull_ote):
        candidates["ICT_SILVER_BULLET"] = (
            "BUY",
            "ICT_SILVER_BULLET",
            "BUY (ICT Liquidity Sweep + Displacement)",
            85,
            f"ICT Silver Bullet BUY: Sell-side liquidity swept near {prior_low:.{dec}f} / OTE ({fib_618_bull:.{dec}f}) followed by bullish displacement & RSI hook ({rsi14:.1f}).",
        )
    elif ict_bear_ok and (bear_displacement or bear_fvg or in_bear_ote):
        candidates["ICT_SILVER_BULLET"] = (
            "SELL",
            "ICT_SILVER_BULLET",
            "SELL (ICT Liquidity Sweep + Displacement)",
            85,
            f"ICT Silver Bullet SELL: Buy-side liquidity swept near {prior_high:.{dec}f} / OTE ({fib_618_bear:.{dec}f}) followed by bearish displacement & RSI hook ({rsi14:.1f}).",
        )

    # 4. FIB_GOLDEN_POCKET
    if (in_bull_golden_zone or in_bull_ote) and bull_candle and (rsi14 >= prev_rsi or hist >= prev_hist):
        candidates["FIB_GOLDEN_POCKET"] = (
            "BUY",
            "FIB_GOLDEN_POCKET",
            "BUY (Fibonacci 38.2%–61.8% Golden Pocket)",
            84 if uptrend_structure else 80,
            f"Fibonacci Golden Pocket BUY: Price rejected the 38.2%–61.8% retracement zone ({fib_618_bull:.{dec}f}–{fib_382_bull:.{dec}f}) with bullish reversal candle.",
        )
    elif (in_bear_golden_zone or in_bear_ote) and bear_candle and (rsi14 <= prev_rsi or hist <= prev_hist):
        candidates["FIB_GOLDEN_POCKET"] = (
            "SELL",
            "FIB_GOLDEN_POCKET",
            "SELL (Fibonacci 38.2%–61.8% Golden Pocket)",
            84 if downtrend_structure else 80,
            f"Fibonacci Golden Pocket SELL: Price rejected the 38.2%–61.8% retracement zone ({fib_382_bear:.{dec}f}–{fib_618_bear:.{dec}f}) with bearish reversal candle.",
        )

    # 5. WYCKOFF_VSA
    if wyckoff_spring:
        candidates["WYCKOFF_VSA"] = (
            "BUY",
            "WYCKOFF_SPRING",
            "BUY (Wyckoff Spring + VSA Demand)",
            82,
            f"Wyckoff Accumulation Spring Confirmed: False breakdown below support ({prior_low:.{dec}f}) rejected back inside structure (Vol {vol_ratio:.1f}x avg).",
        )
    elif wyckoff_utad:
        candidates["WYCKOFF_VSA"] = (
            "SELL",
            "WYCKOFF_UTAD",
            "SELL (Wyckoff Upthrust UTAD + VSA Supply)",
            82,
            f"Wyckoff Distribution Upthrust (UTAD) Confirmed: False breakout above resistance ({prior_high:.{dec}f}) rejected back inside structure (Vol {vol_ratio:.1f}x avg).",
        )

    # 6. BOLLINGER_MEAN_REV
    if bb_bull_rev:
        candidates["BOLLINGER_MEAN_REV"] = (
            "BUY",
            "BOLLINGER_MEAN_REV",
            "BUY (Bollinger 2σ + RSI Exhaustion Reversal)",
            80,
            f"Bollinger Mean-Reversion BUY: Lower 2.0σ band ({bb_low_val:.{dec}f}) pierced and rejected with bullish close & RSI hook ({prev_rsi:.1f} → {rsi14:.1f}).",
        )
    elif bb_bear_rev:
        candidates["BOLLINGER_MEAN_REV"] = (
            "SELL",
            "BOLLINGER_MEAN_REV",
            "SELL (Bollinger 2σ + RSI Exhaustion Reversal)",
            80,
            f"Bollinger Mean-Reversion SELL: Upper 2.0σ band ({bb_high_val:.{dec}f}) pierced and rejected with bearish close & RSI hook ({prev_rsi:.1f} → {rsi14:.1f}).",
        )

    # 7. TURTLE_BREAKOUT
    if bull_breakout:
        candidates["TURTLE_BREAKOUT"] = (
            "BUY",
            "TURTLE_BREAKOUT",
            f"BUY ({brk_len}-Bar Structure Breakout)",
            82,
            f"Momentum Breakout Confirmed: Stacked EMA 9/21/50 ribbon with expansion candle closing above {brk_len}-bar high ({prev_brk_high:.{dec}f}).",
        )
    elif bear_breakout:
        candidates["TURTLE_BREAKOUT"] = (
            "SELL",
            "TURTLE_BREAKOUT",
            f"SELL ({brk_len}-Bar Structure Breakdown)",
            82,
            f"Momentum Breakdown Confirmed: Stacked bearish EMA 9/21/50 ribbon with expansion candle closing below {brk_len}-bar low ({prev_brk_low:.{dec}f}).",
        )

    # Select winning candidate based on user's chosen `strategy`
    chosen = None
    if strategy == "FLEXIBLE_HYBRID":
        # Pick highest-confidence candidate; prioritize SMC / Trend / ICT ties
        priority_order = [
            "SMC_ORDER_BLOCK",
            "TREND_PULLBACK",
            "ICT_SILVER_BULLET",
            "FIB_GOLDEN_POCKET",
            "TURTLE_BREAKOUT",
            "WYCKOFF_VSA",
            "BOLLINGER_MEAN_REV",
        ]
        best_score = -1
        for s_key in priority_order:
            if s_key in candidates:
                cand = candidates[s_key]
                if cand[3] > best_score:
                    best_score = cand[3]
                    chosen = cand
    else:
        chosen = candidates.get(strategy)

    if chosen:
        direction, signal_type, signal, base_conf, reason = chosen
    else:
        direction = "WAIT"
        signal_type = "WAIT"
        signal = f"WAIT (No {strat_cfg['short']} Setup — Hold Fire)"
        base_conf = 44
        reason = (
            f"No {strat_cfg['name']} trigger on {style_cfg['name']}: Price ({price:.{dec}f}) is between Swing High ({recent_high:.{dec}f}) "
            f"and Swing Low ({recent_low:.{dec}f}). Waiting for confirmed {strat_cfg['short']} zone ({fib_618_bull:.{dec}f}–{fib_382_bull:.{dec}f})."
        )

    # Adjust confidence with Fundamental & News alignment
    if direction == "BUY":
        if fundamental_bias == "BULLISH":
            base_conf = min(96, base_conf + 7)
        elif fundamental_bias == "BEARISH":
            base_conf = max(58, base_conf - 5)
    elif direction == "SELL":
        if fundamental_bias == "BEARISH":
            base_conf = min(96, base_conf + 7)
        elif fundamental_bias == "BULLISH":
            base_conf = max(58, base_conf - 5)

    # Enforce user's minimum confidence threshold filter
    if direction in ("BUY", "SELL") and base_conf < int(min_confidence or 70):
        direction = "WAIT"
        signal_type = "WAIT_BELOW_MIN_CONF"
        signal = f"WAIT (Filtered < {int(min_confidence)}% Min Confidence)"
        reason = f"Candidate {chosen[0]} setup scored {base_conf}% confidence, below your saved {int(min_confidence)}% threshold."

    entry = round(price, dec)
    ref_bull = ema21 >= ema50
    if direction == "BUY" or (direction == "WAIT" and ref_bull):
        sl = round(price - sl_mult * atr14, dec)
        tp1 = round(price + tp1_mult * atr14, dec)
        tp2 = round(price + tp2_mult * atr14, dec)
    else:
        sl = round(price + sl_mult * atr14, dec)
        tp1 = round(price - tp1_mult * atr14, dec)
        tp2 = round(price - tp2_mult * atr14, dec)

    risk = abs(entry - sl)
    reward2 = abs(tp2 - entry)
    rr_ratio = round(reward2 / risk, 2) if risk > 0 else 2.0

    checklist = [
        {
            "name": f"{style_cfg['code'].title()} EMA 21/50/200 Trend",
            "passed": bool(uptrend_structure or downtrend_structure),
            "detail": (
                f"Bullish (EMA200 {ema200:.{dec}f})"
                if uptrend_structure
                else (f"Bearish (EMA200 {ema200:.{dec}f})" if downtrend_structure else "Consolidating")
            ),
        },
        {
            "name": f"Strategy: {strat_cfg['short']}",
            "passed": bool(chosen is not None),
            "detail": (
                f"{signal_type.replace('_', ' ')} Triggered"
                if chosen is not None
                else f"Scanning {strat_cfg['short']}"
            ),
        },
        {
            "name": "Fib / Liquidity / OB Zone",
            "passed": bool(touched_buy_zone or touched_sell_zone or ict_bull_sweep or ict_bear_sweep or bull_fvg or bear_fvg),
            "detail": (
                f"In Key Zone ({fib_500_bull:.{dec}f})"
                if (touched_buy_zone or touched_sell_zone or ict_bull_sweep or ict_bear_sweep)
                else f"Watch {fib_500_bull:.{dec}f} / {ema21:.{dec}f}"
            ),
        },
        {
            "name": "Displacement / Rejection Bar",
            "passed": bool(bull_candle or bear_candle),
            "detail": f"{int(body_ratio * 100)}% Body ({'Bullish' if bull_candle else ('Bearish' if bear_candle else 'Neutral')})",
        },
        {
            "name": "RSI & MACD Impulse",
            "passed": bool(bull_momentum or bear_momentum or bb_bull_rev or bb_bear_rev),
            "detail": f"RSI {rsi14:.1f} · MACD {hist:+.{dec}f}",
        },
    ]

    return {
        "trading_style": trading_style,
        "style_name": style_cfg["name"],
        "style_badge": style_cfg["badge"],
        "strategy": strategy,
        "strategy_name": strat_cfg["name"],
        "strategy_short": strat_cfg["short"],
        "strategy_badge": strat_cfg["badge"],
        "hold_duration_label": style_cfg["hold_duration_label"],
        "sl_mult": sl_mult,
        "tp1_mult": tp1_mult,
        "tp2_mult": tp2_mult,
        "min_confidence": int(min_confidence or 70),
        "direction": direction,
        "signal_type": signal_type,
        "signal": signal,
        "confidence": int(base_conf),
        "entry": entry,
        "stop_loss": sl,
        "take_profit_1": tp1,
        "take_profit_2": tp2,
        "risk_reward": rr_ratio,
        "rationale": reason,
        "recent_high": round(recent_high, dec),
        "recent_low": round(recent_low, dec),
        "fib_382": round(fib_382_bull, dec),
        "fib_500": round(fib_500_bull, dec),
        "fib_618": round(fib_618_bull, dec),
        "checklist": checklist,
    }


def _call_gemini_argon_api(api_key, prompt_payload):
    """
    Calls Google Gemini 4 Argon (`gemini-4-argon`) via the official Interactions API
    (https://generativelanguage.googleapis.com/v1beta/interactions) with Structured JSON Output.
    Cached per candle timestamp + symbol + style so repeated polls don't spam the API.
    """
    cache_key = f"{prompt_payload['symbol']}_{prompt_payload['timeframe']}_{prompt_payload['trading_style']}_{prompt_payload['candle_ts']}_{prompt_payload['raw_direction']}"
    if cache_key in _GEMINI_AGENT_CACHE:
        return _GEMINI_AGENT_CACHE[cache_key]

    schema = {
        "type": "object",
        "properties": {
            "verdict": {
                "type": "string",
                "description": "APPROVED_HIGH_CONVICTION, APPROVED_CAUTIOUS, VETOED_TO_WAIT, or WATCHING_SWING_ZONE",
            },
            "final_direction": {
                "type": "string",
                "description": "BUY, SELL, or WAIT",
            },
            "adjusted_confidence": {
                "type": "integer",
                "description": "Final AI confidence score from 35 to 98",
            },
            "technical_agent_note": {
                "type": "string",
                "description": "1-sentence analysis of Swing structure, Fibonacci Golden Pocket, and EMA alignment",
            },
            "macro_agent_note": {
                "type": "string",
                "description": "1-sentence analysis of DXY correlation and live Gold news catalysts",
            },
            "risk_officer_note": {
                "type": "string",
                "description": "1-sentence risk assessment, R:R check, and key invalidation level",
            },
            "executive_summary": {
                "type": "string",
                "description": "2-sentence institutional portfolio manager decision explaining the final signal",
            },
        },
        "required": [
            "verdict",
            "final_direction",
            "adjusted_confidence",
            "technical_agent_note",
            "macro_agent_note",
            "risk_officer_note",
            "executive_summary",
        ],
    }

    body = {
        "model": "gemini-4-argon",
        "system_instruction": (
            "You are the Chief Institutional Gold (XAU/USD) Portfolio Manager & Risk Gatekeeper specializing in "
            "Swing Trading, Intraday, and Macro structure. Review the quantitative candidate signal, Fibonacci "
            "Golden Pocket levels, Multi-Timeframe TradingView recommendations, DXY correlation, and live wire "
            "headlines. If a BUY/SELL candidate fights strong higher-timeframe structure or severe opposing macro "
            "catalysts, veto it to WAIT. Otherwise approve or refine it and explain your institutional reasoning concisely."
        ),
        "input": json.dumps(prompt_payload),
        "response_format": {
            "type": "text",
            "mime_type": "application/json",
            "schema": schema,
        },
    }

    req = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/interactions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "x-goog-api-key": api_key.strip(),
            "Content-Type": "application/json",
            "Api-Revision": "2026-05-20",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10, context=_ssl_context()) as r:
        resp = json.loads(r.read().decode("utf-8"))
        output_text = resp.get("output_text")
        if not output_text:
            for step in resp.get("steps", []):
                if step.get("type") == "model_output":
                    for part in step.get("content", []):
                        if part.get("type") == "text" and part.get("text"):
                            output_text = part["text"]
        if output_text:
            parsed = json.loads(output_text)
            _GEMINI_AGENT_CACHE[cache_key] = parsed
            return parsed
    return None


def run_ai_agent_layer(
    symbol,
    interval,
    trading_style,
    candle_ts,
    current_price,
    raw_sig,
    indicators,
    pivots,
    fibonacci,
    fundamentals,
    tv_scanner,
):
    """
    PRE-SIGNAL AI AGENT LAYER (3-Agent Committee + Gemini 4 Argon LLM Integration):
    Sits between the Quantitative Strategy Engine and the Final Signal Output.
    1. Swing & Structure AI Agent: Evaluates EMA 21/50/200 stack, Fibonacci Golden Pocket (38.2%-61.8%),
       Higher-Timeframe TradingView Scanner recommendations (15m/1h/4h/1D), and Pivot R1/S1 headroom.
    2. Macro & News Catalyst AI Agent: Evaluates live TVC:DXY correlation, Reuters/Dow Jones Gold wire
       sentiment, and High-Impact Event risk (CPI, NFP, FOMC, Powell, Tariffs).
    3. Chief Risk Officer AI Agent (Final Gate): Synthesizes all inputs to APPROVE, REFINE, or VETO
       the candidate trade before the final signal is emitted or sent to Telegram!
    """
    style_cfg = TRADING_STYLES.get(trading_style, TRADING_STYLES["SWING"])
    raw_dir = raw_sig["direction"]
    raw_conf = raw_sig["confidence"]
    entry = raw_sig["entry"]
    sl = raw_sig["stop_loss"]
    tp1 = raw_sig["take_profit_1"]
    tp2 = raw_sig["take_profit_2"]
    atr14 = indicators["atr14"]
    ema9 = indicators["ema9"]
    ema21 = indicators["ema21"]
    ema50 = indicators["ema50"]
    ema200 = indicators.get("ema200", ema50)
    rsi14 = indicators["rsi14"]

    # Higher-Timeframe alignment from TradingView Scanner
    rec_15m = tv_scanner.get("tv_recommend_15m", 0.0) if tv_scanner else 0.0
    rec_1h = tv_scanner.get("tv_recommend_1h", 0.0) if tv_scanner else 0.0
    rec_4h = tv_scanner.get("tv_recommend_4h", 0.0) if tv_scanner else 0.0
    rec_1d = tv_scanner.get("tv_recommend_1d", 0.0) if tv_scanner else 0.0

    htf_bull_count = sum(1 for r in (rec_15m, rec_1h, rec_4h, rec_1d) if r > 0.05)
    htf_bear_count = sum(1 for r in (rec_15m, rec_1h, rec_4h, rec_1d) if r < -0.05)
    if ema21 > ema50:
        htf_bull_count += 1
    else:
        htf_bear_count += 1

    # Fibonacci Golden Pocket analysis
    fib_382 = raw_sig["fib_382"]
    fib_500 = raw_sig["fib_500"]
    fib_618 = raw_sig["fib_618"]
    swing_high = raw_sig["recent_high"]
    swing_low = raw_sig["recent_low"]
    golden_low = min(fib_382, fib_618)
    golden_high = max(fib_382, fib_618)

    # Check Pivot R1/R2 & S1/S2 headroom
    r1_dist = pivots["r1"] - current_price
    s1_dist = current_price - pivots["s1"]

    # --- SUB-AGENT 1: SWING & TECHNICAL STRUCTURE AGENT ---
    tech_score = 50
    if ema21 > ema50 and current_price >= ema50:
        tech_bias = "BULLISH"
        tech_score = 68 + min(22, htf_bull_count * 5)
    elif ema21 < ema50 and current_price <= ema50:
        tech_bias = "BEARISH"
        tech_score = 68 + min(22, htf_bear_count * 5)
    else:
        tech_bias = "NEUTRAL"
        tech_score = 52

    if golden_low - 0.5 * atr14 <= current_price <= golden_high + 0.5 * atr14:
        fib_status = f"Inside Fibonacci Golden Pocket (${golden_low:.2f}–${golden_high:.2f})"
        tech_score = min(96, tech_score + 8)
    elif current_price > golden_high:
        fib_status = f"Above Fib 38.2% (${fib_382:.2f}); Swing High at ${swing_high:.2f}"
    else:
        fib_status = f"Below Fib 61.8% (${fib_618:.2f}); Swing Low at ${swing_low:.2f}"

    tech_agent_note = (
        f"{style_cfg['name']} Structure is {tech_bias} (EMA21 ${ema21:.2f} vs EMA50 ${ema50:.2f}, EMA200 ${ema200:.2f}). "
        f"{fib_status}. Higher-TF alignment: {htf_bull_count} Bullish vs {htf_bear_count} Bearish."
    )

    # --- SUB-AGENT 2: MACRO DXY & NEWS CATALYST AGENT ---
    f_bias = fundamentals.get("bias", "NEUTRAL")
    f_score = fundamentals.get("score", 0)
    dxy = fundamentals.get("dxy", {})
    dxy_price = dxy.get("price", 0.0)
    dxy_chg = dxy.get("change_pct", 0.0)
    events = fundamentals.get("high_impact_events", [])
    bull_n = fundamentals.get("bullish_headlines", 0)
    bear_n = fundamentals.get("bearish_headlines", 0)

    macro_score = min(95, max(35, 50 + int(abs(f_score) * 0.45)))
    event_str = f"Active High-Impact Event: {', '.join(events)}." if events else "No immediate FOMC/CPI shock."
    macro_agent_note = (
        f"Macro Bias is {f_bias} (Score {f_score:+d}/100): DXY at {dxy_price:.2f} ({dxy_chg:+.2f}%) "
        f"with {bull_n} Bullish vs {bear_n} Bearish wire headlines. {event_str}"
    )

    # --- SUB-AGENT 3: CHIEF RISK OFFICER (PRE-SIGNAL GATEKEEPER) ---
    final_dir = raw_dir
    final_conf = raw_conf
    verdict = "WATCHING_SWING_ZONE"
    verdict_badge = "AI AGENT: WATCHING SWING ZONE"
    vetoed = False

    if raw_dir in ("BUY", "SELL"):
        # Check if AI Agent should VETO or APPROVE the raw quant signal
        severe_macro_conflict = (raw_dir == "BUY" and f_score <= -40) or (raw_dir == "SELL" and f_score >= 40)
        severe_htf_conflict = (raw_dir == "BUY" and htf_bear_count >= 4 and ema21 < ema50) or (
            raw_dir == "SELL" and htf_bull_count >= 4 and ema21 > ema50
        )
        extreme_rsi_chase = (raw_dir == "BUY" and rsi14 >= 74.0) or (raw_dir == "SELL" and rsi14 <= 26.0)

        if severe_macro_conflict or severe_htf_conflict or extreme_rsi_chase:
            vetoed = True
            final_dir = "WAIT"
            final_conf = 48
            verdict = "VETOED_TO_WAIT"
            verdict_badge = f"AI AGENT VETOED {raw_dir} → FORCED WAIT"
            veto_reasons = []
            if severe_macro_conflict:
                veto_reasons.append(f"opposing Macro/DXY flow ({f_bias} {f_score:+d})")
            if severe_htf_conflict:
                veto_reasons.append("counter-trend Higher-Timeframe Swing structure")
            if extreme_rsi_chase:
                veto_reasons.append(f"exhausted RSI ({rsi14:.1f}) chasing extreme")
            risk_officer_note = (
                f"VETOED raw {raw_dir} trigger due to {' & '.join(veto_reasons)}. Capital preservation rule enforced."
            )
            exec_summary = (
                f"AI Risk Gatekeeper blocked the candidate {raw_dir} @ ${entry:.2f} because {' and '.join(veto_reasons)}. "
                f"Holding fire in WAIT state until structure and macro flow align."
            )
        else:
            # Approved! Check if high conviction or cautious
            aligned_macro = (raw_dir == "BUY" and f_bias == "BULLISH") or (raw_dir == "SELL" and f_bias == "BEARISH")
            aligned_htf = (raw_dir == "BUY" and htf_bull_count >= 3) or (raw_dir == "SELL" and htf_bear_count >= 3)
            if aligned_macro and aligned_htf:
                verdict = "APPROVED_HIGH_CONVICTION"
                verdict_badge = f"AI AGENT APPROVED · HIGH CONVICTION {raw_dir}"
                final_conf = min(96, raw_conf + 6)
            elif aligned_macro or aligned_htf:
                verdict = "APPROVED_CONFIRMED"
                verdict_badge = f"AI AGENT APPROVED · CONFIRMED {raw_dir}"
                final_conf = min(94, raw_conf + 3)
            else:
                verdict = "APPROVED_CAUTIOUS"
                verdict_badge = f"AI AGENT APPROVED · CAUTIOUS {raw_dir}"
                final_conf = max(72, raw_conf - 2)

            risk_pts = abs(entry - sl)
            tp1_pts = abs(tp1 - entry)
            tp2_pts = abs(tp2 - entry)
            risk_officer_note = (
                f"APPROVED {style_cfg['name']} {raw_dir}: Risk ${risk_pts:.2f}/oz ({style_cfg['sl_mult']}x ATR) "
                f"vs TP1 +${tp1_pts:.2f} (moves SL→BE) & TP2 +${tp2_pts:.2f} (R:R 1:{raw_sig['risk_reward']})."
            )
            exec_summary = (
                f"AI Agent Committee APPROVED {style_cfg['name']} {raw_dir} @ ${entry:.2f} ({final_conf}% confidence). "
                f"{raw_sig['signal_type']} aligns with {tech_bias} structure and {f_bias} macro flow. "
                f"Move Stop Loss (${sl:.2f}) to Break-Even once TP1 (${tp1:.2f}) is reached; trail runner to TP2 (${tp2:.2f})."
            )
    else:
        # Raw signal is WAIT — AI Agent provides actionable Swing Trade Roadmap & Exact Watch Zones
        verdict = "WATCHING_SWING_ZONE"
        verdict_badge = f"AI AGENT: SCANNING {style_cfg['code']} ZONES (HOLD FIRE)"
        if tech_bias == "BULLISH":
            watch_zone = f"${golden_low:.2f} – ${max(golden_high, ema21):.2f} (Fib Golden Pocket / EMA21)"
            next_bias = "BULLISH SWING WATCH"
            risk_officer_note = (
                f"No mid-air entry allowed at ${current_price:.2f}. Waiting for pullback into {watch_zone} "
                f"or breakout above Swing High (${swing_high:.2f}) with 1:2.67 R:R."
            )
            exec_summary = (
                f"AI Swing Strategist maintains a {next_bias} ({interval}): Trend is bullish above EMA50 (${ema50:.2f}), "
                f"but current price (${current_price:.2f}) lacks a confirmed candle trigger. Optimal institutional buy zone "
                f"is {watch_zone} targeting ${tp1:.2f} (TP1) and ${tp2:.2f} (TP2)."
            )
        elif tech_bias == "BEARISH":
            watch_zone = f"${min(golden_low, ema21):.2f} – ${golden_high:.2f} (Fib Golden Pocket / EMA21)"
            next_bias = "BEARISH SWING WATCH"
            risk_officer_note = (
                f"No mid-air short allowed at ${current_price:.2f}. Waiting for rally into {watch_zone} "
                f"or breakdown below Swing Low (${swing_low:.2f}) with 1:2.67 R:R."
            )
            exec_summary = (
                f"AI Swing Strategist maintains a {next_bias} ({interval}): Trend is bearish below EMA50 (${ema50:.2f}), "
                f"but current price (${current_price:.2f}) lacks a confirmed candle trigger. Optimal institutional sell zone "
                f"is {watch_zone} targeting ${tp1:.2f} (TP1) and ${tp2:.2f} (TP2)."
            )
        else:
            watch_zone = f"Breakout > ${swing_high:.2f} or Sweep < ${swing_low:.2f}"
            risk_officer_note = (
                f"Market is range-bound between ${swing_low:.2f} and ${swing_high:.2f}. "
                f"Protecting capital until boundary sweep or EMA 21/50 expansion."
            )
            exec_summary = (
                f"AI Agent Committee advises PATIENCE (WAIT) on {interval} {style_cfg['name']}: XAU/USD is consolidating "
                f"near ${current_price:.2f} (Fib 50%: ${fib_500:.2f}). Watching for liquidity sweep at ${swing_low:.2f} / ${swing_high:.2f}."
            )

    engine_label = "Built-in 3-Agent Quant + Macro Committee (Gemini 4 Argon Architecture)"

    # Optional Live Gemini 4 Argon API upgrade if user configured GEMINI_API_KEY
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or get_setting("gemini_api_key", "")
    if api_key and len(api_key.strip()) > 15:
        try:
            prompt_payload = {
                "symbol": symbol,
                "timeframe": interval,
                "trading_style": trading_style,
                "candle_ts": candle_ts,
                "current_price": current_price,
                "raw_direction": raw_dir,
                "raw_signal": raw_sig["signal"],
                "raw_confidence": raw_conf,
                "entry": entry,
                "sl": sl,
                "tp1": tp1,
                "tp2": tp2,
                "ema21": ema21,
                "ema50": ema50,
                "ema200": ema200,
                "rsi14": rsi14,
                "fib_golden_pocket": [golden_low, golden_high],
                "swing_high": swing_high,
                "swing_low": swing_low,
                "dxy": dxy,
                "fundamental_bias": f_bias,
                "fundamental_score": f_score,
                "headlines": [h["title"] for h in fundamentals.get("headlines", [])[:5]],
            }
            llm_res = _call_gemini_argon_api(api_key, prompt_payload)
            if llm_res:
                engine_label = "Gemini 4 Argon Live API (gemini-4-argon Interactions API)"
                verdict = llm_res.get("verdict", verdict)
                if llm_res.get("final_direction") in ("BUY", "SELL", "WAIT"):
                    final_dir = llm_res["final_direction"]
                    vetoed = (raw_dir in ("BUY", "SELL")) and (final_dir == "WAIT")
                final_conf = int(llm_res.get("adjusted_confidence", final_conf))
                tech_agent_note = llm_res.get("technical_agent_note", tech_agent_note)
                macro_agent_note = llm_res.get("macro_agent_note", macro_agent_note)
                risk_officer_note = llm_res.get("risk_officer_note", risk_officer_note)
                exec_summary = llm_res.get("executive_summary", exec_summary)
                verdict_badge = f"GEMINI 4 ARGON: {verdict.replace('_', ' ')}"
        except Exception:
            pass

    return {
        "engine": engine_label,
        "trading_style": trading_style,
        "style_name": style_cfg["name"],
        "verdict": verdict,
        "verdict_badge": verdict_badge,
        "raw_direction": raw_dir,
        "final_direction": final_dir,
        "vetoed": vetoed,
        "adjusted_confidence": final_conf,
        "watch_zone": f"${golden_low:.2f} – ${golden_high:.2f} (Fib 38.2%–61.8%)",
        "executive_summary": exec_summary,
        "agents": [
            {
                "name": "1. Swing & Structure AI Agent",
                "role": "EMA 21/50/200 · Fibonacci Golden Pocket · MTF Confluence",
                "bias": tech_bias,
                "score": tech_score,
                "note": tech_agent_note,
            },
            {
                "name": "2. Macro & DXY Intelligence Agent",
                "role": "TVC:DXY Inverse Correlation · Reuters/Dow Jones Gold Wire",
                "bias": f_bias,
                "score": macro_score,
                "note": macro_agent_note,
            },
            {
                "name": "3. Chief Risk Officer (Final Gate)",
                "role": "Pre-Signal Approval / Veto · R:R & Single-Position Guard",
                "bias": final_dir if final_dir in ("BUY", "SELL") else "HOLD FIRE",
                "score": final_conf,
                "note": risk_officer_note,
            },
        ],
    }


# =====================================================================
# TELEGRAM BOT INTEGRATION (@this_is_ai_signal_bot)
# =====================================================================

def get_telegram_token():
    tok = get_setting("telegram_bot_token", DEFAULT_TELEGRAM_TOKEN).strip()
    return tok if tok else DEFAULT_TELEGRAM_TOKEN


def verify_telegram_bot(force=False):
    """
    Verifies the Telegram Bot token via `getMe` and returns bot details,
    active subscriber list, and recent message delivery logs.
    """
    now = time.time()
    token = get_telegram_token()
    if not force and _BOT_INFO_CACHE["data"] and (now - _BOT_INFO_CACHE["ts"] < 30):
        bot_info = _BOT_INFO_CACHE["data"]
    else:
        bot_info = {"ok": False, "username": "this_is_ai_signal_bot", "first_name": "AI Bot Signal"}
        try:
            url = f"https://api.telegram.org/bot{token}/getMe"
            with urllib.request.urlopen(url, timeout=6, context=_ssl_context()) as r:
                data = json.loads(r.read().decode("utf-8"))
                if data.get("ok") and data.get("result"):
                    res = data["result"]
                    bot_info = {
                        "ok": True,
                        "id": res.get("id"),
                        "username": res.get("username", "this_is_ai_signal_bot"),
                        "first_name": res.get("first_name", "AI Bot Signal"),
                        "bot_link": f"https://t.me/{res.get('username', 'this_is_ai_signal_bot')}",
                    }
                    _BOT_INFO_CACHE["ts"] = now
                    _BOT_INFO_CACHE["data"] = bot_info
        except Exception as exc:
            bot_info["error"] = str(exc)

    return {
        "bot": bot_info,
        "auto_notify": get_setting("telegram_auto_notify", "1") == "1",
        "subscribers": get_telegram_subscribers(active_only=True),
        "logs": get_telegram_logs(limit=20),
    }


def send_telegram_message(chat_id, html_text, event_type="SIGNAL"):
    """Sends an HTML-formatted message to a specific Telegram chat_id and logs delivery in SQLite."""
    token = get_telegram_token()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps(
        {
            "chat_id": str(chat_id).strip(),
            "text": html_text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8, context=_ssl_context()) as r:
            resp = json.loads(r.read().decode("utf-8"))
            ok = bool(resp.get("ok"))
            clean_preview = re.sub(r"<[^>]+>", "", html_text).replace("\n", " ").strip()
            log_telegram_message(chat_id, event_type, clean_preview, ok=ok)
            return {"ok": ok, "response": resp}
    except Exception as exc:
        log_telegram_message(chat_id, event_type, f"ERROR: {exc}", ok=False)
        return {"ok": False, "error": str(exc)}


def format_signal_telegram_html(sig_data, event_banner=None):
    """Formats a full XAU/USD AI Agent Signal & Swing Structure report for Telegram."""
    style_name = sig_data.get("style_name", "Swing Trade (Pro Default)")
    direction = sig_data.get("direction", "WAIT")
    icon = "🟢 <b>BUY</b>" if direction == "BUY" else ("🔴 <b>SELL</b>" if direction == "SELL" else "🟡 <b>WAIT (HOLD FIRE)</b>")
    ai = sig_data.get("ai_agent") or {}
    f = sig_data.get("fundamentals") or {}
    dxy = f.get("dxy") or {}

    header = event_banner or f"🏆 <b>XAU/USD AI AGENT SIGNAL ({style_name.upper()})</b>"
    lines = [
        header,
        f"━━━━━━━━━━━━━━━━━━━━━━",
        f"📊 <b>Symbol:</b> <code>{sig_data['symbol']}</code> ({sig_data['timeframe']})",
        f"🎯 <b>Trading Type:</b> {style_name}",
        f"⚡ <b>Final Verdict:</b> {icon} — <code>{sig_data['signal']}</code>",
        f"🤖 <b>AI Agent Gate:</b> <code>{ai.get('verdict_badge', 'APPROVED')}</code> ({sig_data['confidence']}%)",
        f"💰 <b>Spot Price:</b> <code>${sig_data['current_price']:.2f}</code>",
        f"",
        f"📌 <b>EXECUTION & RISK LEVELS:</b>",
        f"• <b>Entry Price:</b> <code>${sig_data['entry']:.2f}</code>",
        f"• <b>Stop Loss (SL):</b> <code>${sig_data['stop_loss']:.2f}</code> ({sig_data.get('sl_mult', 1.5)}x ATR)",
        f"• <b>Take Profit 1 (TP1 + BE):</b> <code>${sig_data['take_profit_1']:.2f}</code> ({sig_data.get('tp1_mult', 2.5)}x ATR)",
        f"• <b>Take Profit 2 (TP2 Runner):</b> <code>${sig_data['take_profit_2']:.2f}</code> ({sig_data.get('tp2_mult', 4.0)}x ATR)",
        f"• <b>Reward : Risk:</b> <code>1 : {sig_data['risk_reward']}</code>",
        f"",
        f"🧠 <b>AI AGENT LAYER ANALYSIS:</b>",
        f"{ai.get('executive_summary', sig_data.get('rationale', ''))}",
        f"",
        f"🌐 <b>MACRO & DXY INTELLIGENCE:</b>",
        f"• <b>Gold Macro Bias:</b> <code>{f.get('bias', 'NEUTRAL')} ({f.get('score', 0):+d})</code>",
        f"• <b>US Dollar (DXY):</b> <code>{dxy.get('price', 0.0):.3f} ({dxy.get('change_pct', 0.0):+.2f}%)</code>",
        f"• <b>Fib Golden Pocket:</b> <code>{ai.get('watch_zone', '--')}</code>",
        f"🕒 <i>{sig_data.get('last_candle_time_local', '')}</i>",
    ]
    return "\n".join(lines)


def broadcast_telegram_signal(sig_data, target_chat_id=None, event_type="MANUAL_SIGNAL", event_banner=None):
    """Broadcasts the formatted AI Agent signal to target_chat_id or all active subscribers."""
    html_msg = format_signal_telegram_html(sig_data, event_banner=event_banner)
    if target_chat_id:
        upsert_telegram_subscriber(target_chat_id, username="DashboardUser", first_name="Trader")
        res = send_telegram_message(target_chat_id, html_msg, event_type=event_type)
        return {"sent": 1 if res.get("ok") else 0, "results": [res]}

    subs = get_telegram_subscribers(active_only=True)
    if not subs:
        return {
            "sent": 0,
            "error": (
                "No Telegram chat_id subscribed yet. Open @this_is_ai_signal_bot in Telegram and send /start, "
                "or enter your Chat ID in the Telegram panel."
            ),
        }

    results = []
    sent_count = 0
    for s in subs:
        r = send_telegram_message(s["chat_id"], html_msg, event_type=event_type)
        if r.get("ok"):
            sent_count += 1
        results.append(r)
    return {"sent": sent_count, "results": results}


def _on_live_position_event(ev_type, trade_obj, sig_data):
    """Callback triggered automatically when a new AI-Approved position opens or hits TP1/TP2/SL."""
    if get_setting("telegram_auto_notify", "1") != "1":
        return
    subs = get_telegram_subscribers(active_only=True)
    if not subs:
        return

    if ev_type == "NEW_SIGNAL":
        banner = f"🚨 <b>NEW {sig_data.get('trading_style', 'SWING')} POSITION OPENED (#{trade_obj['id']})</b>"
        broadcast_telegram_signal(sig_data, event_type="AUTO_NEW_SIGNAL", event_banner=banner)
    elif ev_type == "POSITION_CLOSED":
        st = trade_obj.get("status", "CLOSED")
        pnl = trade_obj.get("pnl_pts", 0.0)
        emoji = "✅" if pnl >= 0 else "🛑"
        msg = (
            f"{emoji} <b>POSITION #{trade_obj['id']} CLOSED: {st}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Symbol / TF:</b> <code>{trade_obj['symbol']}</code> ({trade_obj['timeframe']} · {trade_obj.get('trading_style', 'SWING')})\n"
            f"• <b>Direction:</b> <b>{trade_obj['direction']}</b>\n"
            f"• <b>Entry → Exit:</b> <code>${trade_obj['entry_price']:.2f}</code> → <code>${(trade_obj.get('outcome_price') or 0):.2f}</code>\n"
            f"• <b>Realized P&L (1 oz):</b> <b>{'+' if pnl >= 0 else ''}${pnl:.2f}</b>\n"
            f"🔓 <i>Single-position lock released. AI Agent is now scanning for the next confirmed setup.</i>"
        )
        for s in subs:
            send_telegram_message(s["chat_id"], msg, event_type=f"AUTO_{st}")


def sync_telegram_updates(run_commands=True):
    """
    Polls Telegram `getUpdates` with full allowed_updates (including groups, supergroups,
    channel_post, and my_chat_member) to auto-discover group chats & private users
    and handle interactive bot commands (/start, /swing, /signal, /intraday, /scalp, /status, /news, /id).
    """
    token = get_telegram_token()
    last_id = int(get_setting("telegram_last_update_id", "0") or "0")
    allowed_json = urllib.parse.quote(json.dumps(["message", "channel_post", "my_chat_member", "chat_member"]))
    url = f"https://api.telegram.org/bot{token}/getUpdates?offset={last_id + 1}&timeout=1&allowed_updates={allowed_json}"
    new_subs = []
    try:
        with urllib.request.urlopen(url, timeout=6, context=_ssl_context()) as r:
            data = json.loads(r.read().decode("utf-8"))
            if not data.get("ok"):
                return {"ok": False, "subscribers": get_telegram_subscribers()}
            updates = data.get("result", [])
            max_id = last_id
            for u in updates:
                uid = int(u.get("update_id", 0))
                if uid > max_id:
                    max_id = uid

                # Check all possible update containers: message, channel_post, my_chat_member
                msg = u.get("message") or u.get("channel_post")
                my_cm = u.get("my_chat_member")

                chat = None
                from_user = None
                text = ""

                if msg:
                    chat = msg.get("chat") or {}
                    from_user = msg.get("from") or {}
                    text = (msg.get("text") or "").strip()
                elif my_cm:
                    chat = my_cm.get("chat") or {}
                    from_user = my_cm.get("from") or {}
                    new_cm = my_cm.get("new_chat_member") or {}
                    # Bot added or updated in group
                    if new_cm.get("status") in ("member", "administrator"):
                        text = "/start"

                if not chat:
                    continue

                chat_id = chat.get("id")
                if not chat_id:
                    continue

                chat_type = chat.get("type", "private")
                username = chat.get("username") or (from_user.get("username") if from_user else "") or ""
                group_title = chat.get("title") or ""
                first_name = (
                    group_title
                    or (from_user.get("first_name") if from_user else "")
                    or "Group / Trader"
                )

                upsert_telegram_subscriber(
                    chat_id, username=username, first_name=first_name, chat_type=chat_type
                )
                new_subs.append(str(chat_id))

                # Also check if bot was added as new member in message
                if msg and msg.get("new_chat_members"):
                    for ncm in msg.get("new_chat_members", []):
                        if ncm.get("id") == 9190309560 or "ai_signal" in (ncm.get("username") or "").lower():
                            text = "/start"

                if run_commands and text.startswith("/"):
                    cmd = text.split("@")[0].lower()
                    if cmd in ("/start", "/help"):
                        sig = analyze_timeframe("OANDA:XAUUSD", interval="1h", trading_style="SWING", include_series=False)
                        target_name = group_title if chat_type in ("group", "supergroup") else first_name
                        welcome = (
                            f"👋 <b>Welcome to XAU/USD AI Agent Signal Bot!</b>\n"
                            f"✅ Connected to <b>{target_name}</b> (<code>{chat_id}</code> · {chat_type.upper()}).\n"
                            f"🎯 <b>Default Mode:</b> Swing Trade (1H Specialist) with strict Single-Position Lock & AI Agent Gate.\n\n"
                            f"<b>Commands:</b>\n"
                            f"• /swing — Current 1H Swing Trade Setup & Levels\n"
                            f"• /intraday — 15m Intraday Session Setup\n"
                            f"• /scalp — 1m Momentum Scalp Setup\n"
                            f"• /position — 4H Macro Position Setup\n"
                            f"• /news — Live DXY Correlation & Gold News Wire\n"
                            f"• /id — Display this Chat ID\n\n"
                        ) + format_signal_telegram_html(sig)
                        send_telegram_message(chat_id, welcome, event_type="BOT_START")
                    elif cmd in ("/swing", "/signal"):
                        sig = analyze_timeframe("OANDA:XAUUSD", interval="1h", trading_style="SWING", include_series=False)
                        send_telegram_message(chat_id, format_signal_telegram_html(sig), event_type="CMD_SWING")
                    elif cmd == "/intraday":
                        sig = analyze_timeframe("OANDA:XAUUSD", interval="15m", trading_style="INTRADAY", include_series=False)
                        send_telegram_message(chat_id, format_signal_telegram_html(sig), event_type="CMD_INTRADAY")
                    elif cmd == "/scalp":
                        sig = analyze_timeframe("OANDA:XAUUSD", interval="1m", trading_style="SCALPING", include_series=False)
                        send_telegram_message(chat_id, format_signal_telegram_html(sig), event_type="CMD_SCALP")
                    elif cmd == "/position":
                        sig = analyze_timeframe("OANDA:XAUUSD", interval="4h", trading_style="POSITION", include_series=False)
                        send_telegram_message(chat_id, format_signal_telegram_html(sig), event_type="CMD_POSITION")
                    elif cmd == "/id":
                        id_msg = (
                            f"🆔 <b>Chat Information:</b>\n"
                            f"• <b>Title:</b> {first_name}\n"
                            f"• <b>Chat ID:</b> <code>{chat_id}</code>\n"
                            f"• <b>Type:</b> <code>{chat_type}</code>"
                        )
                        send_telegram_message(chat_id, id_msg, event_type="CMD_ID")
                    elif cmd == "/news":
                        f = fetch_fundamental_analysis()
                        h_lines = "\n".join(
                            f"• [{h['sentiment']}] {h['title']} <i>({h['source']})</i>"
                            for h in f.get("headlines", [])[:5]
                        )
                        n_msg = (
                            f"🌐 <b>XAU/USD MACRO & NEWS INTELLIGENCE</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"• <b>Fundamental Bias:</b> <code>{f['bias']} ({f['score']:+d})</code>\n"
                            f"• <b>US Dollar (DXY):</b> <code>{f['dxy']['price']:.3f} ({f['dxy']['change_pct']:+.2f}%)</code>\n\n"
                            f"<b>Top Wire Headlines:</b>\n{h_lines}"
                        )
                        send_telegram_message(chat_id, n_msg, event_type="CMD_NEWS")

            if max_id > last_id:
                set_setting("telegram_last_update_id", str(max_id))
    except Exception as exc:
        return {"ok": False, "error": str(exc), "subscribers": get_telegram_subscribers()}

    return {"ok": True, "new_subscribers": new_subs, "subscribers": get_telegram_subscribers()}


def get_saved_trading_config():
    """Returns the user's persisted trading settings from DB (app_settings)."""
    s = get_all_settings()
    sym = s.get("saved_symbol", "OANDA:XAUUSD")
    if sym not in SUPPORTED_ASSETS:
        sym = "OANDA:XAUUSD"
    style = s.get("saved_trading_style", "SWING").upper()
    if style not in TRADING_STYLES:
        style = "SWING"
    strat = s.get("saved_strategy", "FLEXIBLE_HYBRID").upper()
    if strat not in TRADING_STRATEGIES:
        strat = "FLEXIBLE_HYBRID"
    style_cfg = TRADING_STYLES[style]
    tf = s.get("saved_timeframe", style_cfg["default_tf"])
    if tf not in TV_INTERVAL_MAP:
        tf = style_cfg["default_tf"]

    def _flt(key, default):
        try:
            return float(s.get(key, default))
        except Exception:
            return float(default)

    exit_rule = s.get("saved_exit_rule", "TP1_ONLY").upper()
    if exit_rule not in ("TP1_ONLY", "BE_RUNNER"):
        exit_rule = "TP1_ONLY"

    return {
        "symbol": sym,
        "trading_style": style,
        "strategy": strat,
        "timeframe": tf,
        "exit_rule": exit_rule,
        "sl_mult": _flt("saved_sl_mult", style_cfg["sl_mult"]),
        "tp1_mult": _flt("saved_tp1_mult", style_cfg["tp1_mult"]),
        "tp2_mult": _flt("saved_tp2_mult", style_cfg["tp2_mult"]),
        "min_confidence": int(_flt("saved_min_conf", 70)),
        "account_balance": _flt("saved_account_balance", 10000.0),
        "risk_pct": _flt("saved_risk_pct", 1.0),
        "updated_at": s.get("saved_config_updated_at", ""),
    }


def run_and_store_backtest(
    symbol="OANDA:XAUUSD",
    interval="1h",
    trading_style="SWING",
    strategy="FLEXIBLE_HYBRID",
    strategy_mode="PRO_CONFIRMED",
    bars_tested=450,
    duration_preset=None,
    start_date=None,
    end_date=None,
    exit_rule="TP1_ONLY",
    sl_mult=None,
    tp1_mult=None,
    tp2_mult=None,
    min_confidence=70,
    candles=None,
):
    """
    Runs a historical simulation across `bars_tested`, `duration_preset` (up to 5_YEARS),
    or custom `start_date`..`end_date` (YYYY-MM-DD, UTC+7) with STRICT SINGLE-POSITION LOCK:
    - `exit_rule == "TP1_ONLY"` (default): 100% closes at TP1 (WIN_TP1) or SL (LOSS_SL). No BE move.
    - `exit_rule == "BE_RUNNER"`: 50% closes at TP1 + SL moves to BE; TP2 exits at blended (tp1 + tp2)/2.
    """
    if trading_style not in TRADING_STYLES:
        trading_style = "SWING"
    if strategy not in TRADING_STRATEGIES:
        strategy = "FLEXIBLE_HYBRID"
    exit_rule = (exit_rule or "TP1_ONLY").upper()
    if exit_rule not in ("TP1_ONLY", "BE_RUNNER"):
        exit_rule = "TP1_ONLY"

    style_cfg = TRADING_STYLES[trading_style]
    strat_cfg = TRADING_STRATEGIES[strategy]

    if sl_mult is None:
        sl_mult = style_cfg["sl_mult"]
    if tp1_mult is None:
        tp1_mult = style_cfg["tp1_mult"]
    if tp2_mult is None:
        tp2_mult = style_cfg["tp2_mult"]

    actual_interval = interval
    actual_bars = int(bars_tested)
    tf_rank = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}
    tf_seconds = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}

    start_ts = None
    end_ts = None
    min_ts_fetch = None
    if start_date or end_date:
        now_dt = datetime.now(TZ_UTC7)
        if start_date:
            s_dt = datetime.strptime(start_date[:10], "%Y-%m-%d").replace(tzinfo=TZ_UTC7)
            start_ts = int(s_dt.timestamp())
        if end_date:
            e_dt = datetime.strptime(end_date[:10], "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, tzinfo=TZ_UTC7
            )
            end_ts = int(e_dt.timestamp())
        else:
            end_ts = int(now_dt.timestamp())

        if start_ts is not None:
            days_back = max(1, (int(now_dt.timestamp()) - start_ts) // 86400 + 2)
            if days_back > 1100 and tf_rank.get(actual_interval, 60) < tf_rank["4h"]:
                actual_interval = "4h"
            elif days_back > 365 and tf_rank.get(actual_interval, 60) < tf_rank["1h"]:
                actual_interval = "1h"
            elif days_back > 60 and tf_rank.get(actual_interval, 60) < tf_rank["15m"]:
                actual_interval = "15m"
            elif days_back > 14 and tf_rank.get(actual_interval, 60) < tf_rank["5m"]:
                actual_interval = "5m"

            bar_sec = tf_seconds.get(actual_interval, 3600)
            warmup_sec = 220 * bar_sec
            min_ts_fetch = start_ts - warmup_sec
            est_bars = int((int(now_dt.timestamp()) - min_ts_fetch) / bar_sec) + 250
            actual_bars = max(actual_bars, min(est_bars, 30000))
    elif duration_preset and duration_preset in DURATION_PRESETS:
        preset = DURATION_PRESETS[duration_preset]
        actual_bars = preset["bars"]
        min_tf = preset.get("force_min_tf")
        if min_tf and tf_rank.get(actual_interval, 60) < tf_rank.get(min_tf, 60):
            actual_interval = min_tf

    if candles is None or len(candles) < actual_bars:
        _, candles = fetch_tradingview_candles(
            symbol=symbol,
            interval=actual_interval,
            n_bars=actual_bars,
            min_timestamp=min_ts_fetch,
        )

    if end_ts is not None:
        candles = [c for c in candles if c["timestamp"] <= end_ts]

    if len(candles) < 40:
        raise RuntimeError(f"Insufficient candles ({len(candles)}) to backtest")

    fundamentals = fetch_fundamental_analysis()
    f_bias = fundamentals["bias"]
    f_score = fundamentals["score"]

    closes = [c["close"] for c in candles]
    dec = 4 if closes[-1] < 10 else (3 if closes[-1] < 100 else 2)
    ema9_s = ema_series(closes, 9)
    ema21_s = ema_series(closes, 21)
    ema50_s = ema_series(closes, 50)
    ema200_s = ema_series(closes, 200)
    rsi14_s = rsi_series(closes, 14)
    atr14_s = atr_series(candles, 14)
    _, _, macd_h = macd_series(closes, 12, 26, 9)
    bb_u, _, bb_l = bollinger_series(closes, 20, 2.0)

    # Allow legacy strategy_mode dropdown values to map to specific strategies if strategy is FLEXIBLE_HYBRID
    effective_strategy = strategy
    if strategy_mode in TRADING_STRATEGIES:
        effective_strategy = strategy_mode

    trades = []
    n = len(candles)
    i = 50
    if start_ts is not None:
        while i < n - 3 and candles[i]["timestamp"] < start_ts:
            i += 1

    cum_pnl = 0.0
    peak_pnl = 0.0
    max_dd = 0.0
    max_hold = style_cfg["max_hold_bars"]

    while i < n - 3:
        sig = compute_signal_at(
            i,
            candles,
            ema9_s,
            ema21_s,
            ema50_s,
            rsi14_s,
            atr14_s,
            macd_h,
            bb_u=bb_u,
            bb_l=bb_l,
            ema200_s=ema200_s,
            trading_style=trading_style,
            strategy=effective_strategy,
            sl_mult=sl_mult,
            tp1_mult=tp1_mult,
            tp2_mult=tp2_mult,
            min_confidence=min_confidence,
            fundamental_bias=f_bias,
            fundamental_score=f_score,
        )

        if sig["direction"] == "WAIT":
            i += 1
            continue

        if strategy_mode == "TREND_ONLY" and sig["signal_type"] not in ("TREND_PULLBACK", "FIB_GOLDEN_POCKET", "SMC_ORDER_BLOCK"):
            i += 1
            continue
        if strategy_mode == "MEAN_REVERSION" and sig["signal_type"] not in ("BOLLINGER_MEAN_REV", "ICT_SILVER_BULLET", "WYCKOFF_SPRING", "WYCKOFF_UTAD"):
            i += 1
            continue
        if strategy_mode == "HIGH_CONFIDENCE" and sig["confidence"] < 80:
            i += 1
            continue

        direction = sig["direction"]
        entry = sig["entry"]
        sl = sig["stop_loss"]
        tp1 = sig["take_profit_1"]
        tp2 = sig["take_profit_2"]

        outcome = None
        exit_price = entry
        exit_time = candles[i]["time_local"]
        exit_idx = i + 1
        hit_tp1 = False
        active_sl = sl

        for j in range(i + 1, min(i + max_hold, n)):
            ch = candles[j]["high"]
            cl = candles[j]["low"]
            if exit_rule == "TP1_ONLY":
                if direction == "BUY":
                    if cl <= sl:
                        outcome = "LOSS_SL"
                        exit_price = sl
                        exit_time = candles[j]["time_local"]
                        exit_idx = j
                        break
                    if ch >= tp1:
                        outcome = "WIN_TP1"
                        exit_price = tp1
                        exit_time = candles[j]["time_local"]
                        exit_idx = j
                        break
                else:
                    if ch >= sl:
                        outcome = "LOSS_SL"
                        exit_price = sl
                        exit_time = candles[j]["time_local"]
                        exit_idx = j
                        break
                    if cl <= tp1:
                        outcome = "WIN_TP1"
                        exit_price = tp1
                        exit_time = candles[j]["time_local"]
                        exit_idx = j
                        break
            else:
                if direction == "BUY":
                    if cl <= active_sl:
                        if hit_tp1:
                            outcome = "WIN_TP1_BE"
                            exit_price = round((tp1 + entry) / 2.0, dec)
                        else:
                            outcome = "LOSS_SL"
                            exit_price = sl
                        exit_time = candles[j]["time_local"]
                        exit_idx = j
                        break
                    if ch >= tp2:
                        outcome = "WIN_TP2"
                        exit_price = round((tp1 + tp2) / 2.0, dec)
                        exit_time = candles[j]["time_local"]
                        exit_idx = j
                        break
                    if ch >= tp1 and not hit_tp1:
                        hit_tp1 = True
                        active_sl = entry
                else:
                    if ch >= active_sl:
                        if hit_tp1:
                            outcome = "WIN_TP1_BE"
                            exit_price = round((tp1 + entry) / 2.0, dec)
                        else:
                            outcome = "LOSS_SL"
                            exit_price = sl
                        exit_time = candles[j]["time_local"]
                        exit_idx = j
                        break
                    if cl <= tp2:
                        outcome = "WIN_TP2"
                        exit_price = round((tp1 + tp2) / 2.0, dec)
                        exit_time = candles[j]["time_local"]
                        exit_idx = j
                        break
                    if cl <= tp1 and not hit_tp1:
                        hit_tp1 = True
                        active_sl = entry

        if outcome is None and hit_tp1:
            outcome = "WIN_TP1"
            exit_idx = min(i + max_hold - 1, n - 1)
            exit_price = round((tp1 + candles[exit_idx]["close"]) / 2.0, dec) if exit_rule == "BE_RUNNER" else tp1
            exit_time = candles[exit_idx]["time_local"]

        if outcome is not None:
            pnl = (exit_price - entry) if direction == "BUY" else (entry - exit_price)
            pnl = round(pnl, dec)
            cum_pnl = round(cum_pnl + pnl, dec)
            peak_pnl = max(peak_pnl, cum_pnl)
            max_dd = max(max_dd, round(peak_pnl - cum_pnl, dec))
            trades.append(
                {
                    "trade_no": len(trades) + 1,
                    "entry_time": candles[i]["time_local"],
                    "exit_time": exit_time,
                    "direction": direction,
                    "signal_type": sig["signal_type"],
                    "confidence": sig["confidence"],
                    "entry": entry,
                    "sl": sl,
                    "tp1": tp1,
                    "tp2": tp2,
                    "exit": round(exit_price, dec),
                    "outcome": outcome,
                    "pnl": pnl,
                    "cum_pnl": cum_pnl,
                    "rationale": sig["rationale"],
                }
            )
            i = exit_idx + 2
        else:
            i += 1

    wins_list = [t["pnl"] for t in trades if t["outcome"].startswith("WIN")]
    loss_list = [abs(t["pnl"]) for t in trades if t["outcome"].startswith("LOSS")]
    wins = len(wins_list)
    losses = len(loss_list)
    total = wins + losses
    win_rate = round((wins / total) * 100, 1) if total > 0 else 0.0
    gross_win = sum(wins_list)
    gross_loss = sum(loss_list)
    profit_factor = round(gross_win / gross_loss, 2) if gross_loss > 0 else (99.0 if gross_win > 0 else 0.0)
    avg_win = round(gross_win / wins, dec) if wins > 0 else 0.0
    avg_loss = round(gross_loss / losses, dec) if losses > 0 else 0.0
    expectancy = round(cum_pnl / total, dec) if total > 0 else 0.0

    span_str = ""
    if candles:
        span_start = start_date[:10] if start_date else candles[0]["time_local"][:10]
        span_end = end_date[:10] if end_date else candles[-1]["time_local"][:10]
        span_str = f"{span_start} → {span_end}"

    strat_label = TRADING_STRATEGIES.get(effective_strategy, strat_cfg)["short"]
    exit_label = "TP1 Only" if exit_rule == "TP1_ONLY" else "50% TP1 + BE"
    if start_date or end_date:
        mode_label = f"{trading_style} · {strat_label} · {exit_label} ({span_str})"
    elif duration_preset and duration_preset in DURATION_PRESETS:
        mode_label = f"{trading_style} · {strat_label} · {exit_label} ({DURATION_PRESETS[duration_preset]['label']})"
    else:
        mode_label = f"{trading_style} · {strat_label} · {exit_label}"

    now_local = datetime.now(TZ_UTC7).strftime("%Y-%m-%d %H:%M:%S UTC+7")
    summary = {
        "created_at": now_local,
        "symbol": symbol,
        "timeframe": actual_interval,
        "trading_style": trading_style,
        "strategy_mode": mode_label,
        "exit_rule": exit_rule,
        "bars_tested": len(candles),
        "sl_atr_mult": sl_mult,
        "tp1_atr_mult": tp1_mult,
        "tp2_atr_mult": tp2_mult,
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "net_pnl_pts": round(cum_pnl, dec),
        "profit_factor": profit_factor,
        "max_drawdown_pts": max_dd,
        "expectancy_pts": expectancy,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "date_span": span_str,
    }

    run_id = save_backtest_run(summary, trades)
    detail = get_backtest_run_details(run_id=run_id)
    if detail:
        detail["date_span"] = span_str
    return detail


def analyze_timeframe(
    symbol="OANDA:XAUUSD",
    interval="1h",
    trading_style="SWING",
    strategy="FLEXIBLE_HYBRID",
    sl_mult=None,
    tp1_mult=None,
    tp2_mult=None,
    min_confidence=None,
    include_series=False,
):
    """
    Full institutional analysis pipeline:
    1. Streams TradingView OHLCV candles + live Global Scanner tick + Macro DXY/News Intelligence
    2. Computes Trading-Style & Strategy-Specific Signal (SMC, ICT, Trend Pullback, Golden Pocket, Wyckoff, etc.)
    3. Passes the candidate setup through the Pre-Signal AI Agent Layer (3-Agent Committee / Gemini 4 Argon)
       BEFORE emitting the final signal or locking a position
    4. Evaluates Single-Position Lock and triggers automatic Telegram Bot notifications on state transitions
    """
    init_db()
    saved_cfg = get_saved_trading_config()
    if trading_style not in TRADING_STYLES:
        trading_style = saved_cfg["trading_style"]
    if strategy not in TRADING_STRATEGIES:
        strategy = saved_cfg["strategy"]
    if symbol not in SUPPORTED_ASSETS:
        symbol = "OANDA:XAUUSD"

    style_cfg = TRADING_STYLES[trading_style]
    strat_cfg = TRADING_STRATEGIES[strategy]

    if sl_mult is None:
        sl_mult = saved_cfg["sl_mult"] if trading_style == saved_cfg["trading_style"] else style_cfg["sl_mult"]
    if tp1_mult is None:
        tp1_mult = saved_cfg["tp1_mult"] if trading_style == saved_cfg["trading_style"] else style_cfg["tp1_mult"]
    if tp2_mult is None:
        tp2_mult = saved_cfg["tp2_mult"] if trading_style == saved_cfg["trading_style"] else style_cfg["tp2_mult"]
    if min_confidence is None:
        min_confidence = saved_cfg["min_confidence"]

    symbol, candles = fetch_tradingview_candles(symbol=symbol, interval=interval, n_bars=450)
    if len(candles) < 30:
        raise RuntimeError(f"Insufficient {interval} candle data returned for {symbol}")

    tv_tick = None
    try:
        tv_tick = fetch_live_tv_tick(symbol=symbol)
        if tv_tick and tv_tick.get("active") and tv_tick["active"]["price"] > 0:
            live_p = tv_tick["active"]["price"]
            candles[-1]["close"] = live_p
            candles[-1]["high"] = max(candles[-1]["high"], live_p)
            candles[-1]["low"] = min(candles[-1]["low"], live_p)
    except Exception:
        pass

    fundamentals = fetch_fundamental_analysis()

    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    last_close = closes[-1]
    dec = SUPPORTED_ASSETS.get(symbol, {}).get("decimals", 4 if last_close < 10 else (3 if last_close < 100 else 2))

    ema9_s = ema_series(closes, 9)
    ema21_s = ema_series(closes, 21)
    ema50_s = ema_series(closes, 50)
    ema200_s = ema_series(closes, 200)
    rsi14_s = rsi_series(closes, 14)
    atr14_s = atr_series(candles, 14)
    macd_l, macd_sig, macd_h = macd_series(closes, 12, 26, 9)
    bb_u, bb_m, bb_l = bollinger_series(closes, 20, 2.0)

    idx = len(candles) - 1
    sig = compute_signal_at(
        idx,
        candles,
        ema9_s,
        ema21_s,
        ema50_s,
        rsi14_s,
        atr14_s,
        macd_h,
        bb_u=bb_u,
        bb_l=bb_l,
        ema200_s=ema200_s,
        trading_style=trading_style,
        strategy=strategy,
        sl_mult=sl_mult,
        tp1_mult=tp1_mult,
        tp2_mult=tp2_mult,
        min_confidence=min_confidence,
        fundamental_bias=fundamentals["bias"],
        fundamental_score=fundamentals["score"],
    )

    day_high = max(highs[-288:]) if len(highs) >= 288 else max(highs)
    day_low = min(lows[-288:]) if len(lows) >= 288 else min(lows)
    pivot = (day_high + day_low + last_close) / 3.0
    r1 = 2 * pivot - day_low
    s1 = 2 * pivot - day_high
    r2 = pivot + (day_high - day_low)
    s2 = pivot - (day_high - day_low)

    swing_h = sig["recent_high"]
    swing_l = sig["recent_low"]
    diff = max(swing_h - swing_l, 0.0001)
    fib_levels = {
        "0.0% (Swing High)": round(swing_h, dec),
        "23.6%": round(swing_h - 0.236 * diff, dec),
        "38.2% (Golden Top)": round(swing_h - 0.382 * diff, dec),
        "50.0% (Equilibrium)": round(swing_h - 0.500 * diff, dec),
        "61.8% (Golden Base)": round(swing_h - 0.618 * diff, dec),
        "78.6%": round(swing_h - 0.786 * diff, dec),
        "100.0% (Swing Low)": round(swing_l, dec),
    }

    indicators = {
        "ema9": round(ema9_s[-1], dec),
        "ema21": round(ema21_s[-1], dec),
        "ema50": round(ema50_s[-1], dec),
        "ema200": round(ema200_s[-1], dec),
        "rsi14": round(rsi14_s[-1], 2),
        "atr14": round(atr14_s[-1], dec),
        "macd": round(macd_l[-1], dec),
        "macd_signal": round(macd_sig[-1], dec),
        "macd_hist": round(macd_h[-1], dec),
        "bb_upper": bb_u[-1],
        "bb_mid": bb_m[-1],
        "bb_lower": bb_l[-1],
        "recent_2h_high": sig["recent_high"],
        "recent_2h_low": sig["recent_low"],
        "day_high": round(day_high, dec),
        "day_low": round(day_low, dec),
    }
    pivots = {
        "r2": round(r2, dec),
        "r1": round(r1, dec),
        "pivot": round(pivot, dec),
        "s1": round(s1, dec),
        "s2": round(s2, dec),
    }

    # ===============================================================
    # RUN PRE-SIGNAL AI AGENT LAYER BEFORE FINAL SIGNAL OUTPUT
    # ===============================================================
    ai_agent = run_ai_agent_layer(
        symbol=symbol,
        interval=interval,
        trading_style=trading_style,
        candle_ts=candles[-1]["timestamp"],
        current_price=round(last_close, dec),
        raw_sig=sig,
        indicators=indicators,
        pivots=pivots,
        fibonacci=fib_levels,
        fundamentals=fundamentals,
        tv_scanner=tv_tick["active"] if tv_tick else None,
    )

    # Apply AI Agent's Final Decision (Veto / Confidence Adjustment)
    final_direction = ai_agent["final_direction"]
    final_confidence = ai_agent["adjusted_confidence"]
    final_signal_label = sig["signal"]
    final_rationale = sig["rationale"]
    if ai_agent["vetoed"]:
        final_signal_label = f"WAIT (AI Agent Vetoed Raw {sig['direction']})"
        final_rationale = ai_agent["executive_summary"]

    # Add 6th Checklist Gate: Pre-Signal AI Agent Layer Verdict
    sig["checklist"].append(
        {
            "name": "AI Agent Final Gate",
            "passed": final_direction in ("BUY", "SELL") or not ai_agent["vetoed"],
            "detail": ai_agent["verdict"].replace("_", " "),
        }
    )

    result = {
        "symbol": symbol,
        "asset_info": SUPPORTED_ASSETS.get(symbol, {}),
        "all_assets": SUPPORTED_ASSETS,
        "timeframe": interval,
        "trading_style": trading_style,
        "style_info": style_cfg,
        "all_styles": TRADING_STYLES,
        "strategy": strategy,
        "strategy_info": strat_cfg,
        "all_strategies": TRADING_STRATEGIES,
        "saved_settings": saved_cfg,
        "last_candle_time": candles[-1]["time"],
        "last_candle_time_local": candles[-1]["time_local"],
        "last_candle_ts": candles[-1]["timestamp"],
        "current_price": round(last_close, dec),
        "decimals": dec,
        "direction": final_direction,
        "raw_direction": sig["direction"],
        "signal_type": sig["signal_type"],
        "signal": final_signal_label,
        "confidence": final_confidence,
        "entry": sig["entry"],
        "stop_loss": sig["stop_loss"],
        "take_profit_1": sig["take_profit_1"],
        "take_profit_2": sig["take_profit_2"],
        "sl_mult": sig["sl_mult"],
        "tp1_mult": sig["tp1_mult"],
        "tp2_mult": sig["tp2_mult"],
        "min_confidence": sig["min_confidence"],
        "risk_reward": sig["risk_reward"],
        "rationale": final_rationale,
        "checklist": sig["checklist"],
        "ai_agent": ai_agent,
        "fundamentals": fundamentals,
        "tv_scanner": tv_tick["active"] if tv_tick else None,
        "brokers": tv_tick["brokers"] if tv_tick else {},
        "indicators": indicators,
        "pivots": pivots,
        "fibonacci": fib_levels,
    }

    # Strict Single-Position Lock Evaluation & Recording (with automatic Telegram Bot callback)
    pos_lock = record_and_evaluate_live_signal(
        result, candles, on_event_callback=_on_live_position_event
    )
    result["position_lock"] = pos_lock

    if include_series:
        tail = 90
        result["series"] = {
            "candles": candles[-tail:],
            "ema9": [round(x, dec) for x in ema9_s[-tail:]],
            "ema21": [round(x, dec) for x in ema21_s[-tail:]],
            "ema50": [round(x, dec) for x in ema50_s[-tail:]],
            "ema200": [round(x, dec) for x in ema200_s[-tail:]],
            "bb_upper": bb_u[-tail:],
            "bb_lower": bb_l[-tail:],
            "rsi14": [round(x, 2) for x in rsi14_s[-tail:]],
            "macd": [round(x, dec) for x in macd_l[-tail:]],
            "macd_signal": [round(x, dec) for x in macd_sig[-tail:]],
            "macd_hist": [round(x, dec) for x in macd_h[-tail:]],
        }
        runs = get_backtest_runs(limit=15)
        matching = [
            r
            for r in runs
            if r["symbol"] == symbol
            and r["timeframe"] == interval
            and r.get("trading_style", "SWING") == trading_style
        ]
        if not matching:
            latest_bt = run_and_store_backtest(
                symbol=symbol,
                interval=interval,
                trading_style=trading_style,
                strategy=strategy,
                strategy_mode="PRO_CONFIRMED",
                bars_tested=450,
                sl_mult=sl_mult,
                tp1_mult=tp1_mult,
                tp2_mult=tp2_mult,
                min_confidence=min_confidence,
                candles=candles,
            )
        else:
            latest_bt = get_backtest_run_details(run_id=matching[0]["id"])
        result["backtest"] = latest_bt

    return result


if __name__ == "__main__":
    interval_arg = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "1h"
    style_arg = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else "SWING"
    full_flag = "--full" in sys.argv
    out = analyze_timeframe("OANDA:XAUUSD", interval_arg, trading_style=style_arg, include_series=full_flag)
    print(json.dumps(out, indent=2))
