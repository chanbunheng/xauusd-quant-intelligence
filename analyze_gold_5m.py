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

# Trading Styles Configuration — SWING TRADE is the Default & Specialized Mode
TRADING_STYLES = {
    "SWING": {
        "code": "SWING",
        "name": "Swing Trade (Pro Default)",
        "badge": "SWING SPECIALIST",
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
            "Specialized Institutional Swing Strategy: Targets high-R:R multi-session Gold waves using "
            "EMA 21/50/200 trend structure, 48-bar Fibonacci Golden Pocket (38.2%–61.8%) pullbacks, "
            "and 4H/Daily confluence with wider 1.5x ATR stops and 2.5x / 4.0x ATR swing targets."
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
    "1_YEAR": {"bars": 5000, "force_min_tf": "1h", "label": "1 Year (365d) Deep"},
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


def fetch_tradingview_candles(symbol="OANDA:XAUUSD", interval="1h", n_bars=450):
    """
    Connects directly to TradingView's live chart WebSocket (wss://data.tradingview.com)
    to pull real-time Spot Gold OHLCV candles (supports up to 5,000 historical bars).
    """
    tv_int = TV_INTERVAL_MAP.get(interval, "60")
    host = "data.tradingview.com"
    ctx = _ssl_context()
    raw = socket.create_connection((host, 443), timeout=12)
    sock = ctx.wrap_socket(raw, server_hostname=host)
    sock.settimeout(12)
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
        _ws_send(sock, _tv_pack("create_series", [cs, "sds_1", "s1", "sds_sym_1", tv_int, n_bars, ""]))

        bars = []
        for _ in range(45):
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
                            bars.append(
                                {
                                    "timestamp": ts,
                                    "time": dt_utc.strftime("%Y-%m-%d %H:%M UTC"),
                                    "time_local": dt_local.strftime("%Y-%m-%d %H:%M UTC+7"),
                                    "open": round(float(v[1]), 2),
                                    "high": round(float(v[2]), 2),
                                    "low": round(float(v[3]), 2),
                                    "close": round(float(v[4]), 2),
                                    "volume": round(float(v[5]) if len(v) > 5 else 0.0, 1),
                                }
                            )
                    if obj.get("m") == "series_completed":
                        return symbol, bars
                except Exception:
                    pass
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
    Fast (<150ms) live tick & multi-timeframe summary from TradingView Scanner API.
    """
    tv_url = "https://scanner.tradingview.com/cfd/scan"
    cols = [
        "close", "open", "high", "low", "change", "change_abs",
        "close|1", "open|1", "high|1", "low|1", "RSI|1", "Recommend.All|1",
        "close|5", "open|5", "high|5", "low|5", "RSI|5", "Recommend.All|5",
        "close|15", "RSI|15", "Recommend.All|15",
        "close|60", "RSI|60", "Recommend.All|60",
        "close|240", "RSI|240", "Recommend.All|240",
        "RSI", "Recommend.All",
    ]
    payload = json.dumps(
        {
            "symbols": {
                "tickers": ["FX:XAUUSD", "OANDA:XAUUSD", "FOREXCOM:XAUUSD", "TVC:DXY"],
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
        brokers[sym] = {
            "symbol": sym,
            "price": round(float(d.get("close") or 0), 2),
            "day_open": round(float(d.get("open") or 0), 2),
            "day_high": round(float(d.get("high") or 0), 2),
            "day_low": round(float(d.get("low") or 0), 2),
            "change_pct": round(float(d.get("change") or 0), 2),
            "change_abs": round(float(d.get("change_abs") or 0), 2),
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
    for i in range(len(closes)):
        window = closes[max(0, i - period + 1) : i + 1]
        mean = sum(window) / len(window)
        variance = sum((x - mean) ** 2 for x in window) / len(window)
        sd = math.sqrt(variance)
        mid.append(round(mean, 2))
        upper.append(round(mean + num_std * sd, 2))
        lower.append(round(mean - num_std * sd, 2))
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
    for i, tr in enumerate(trs):
        if i < period:
            val = sum(trs[: i + 1]) / (i + 1)
        else:
            val = (val * (period - 1) + tr) / period
        out.append(max(val, 0.35))
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
    sl_mult=None,
    tp1_mult=None,
    tp2_mult=None,
    fundamental_bias="NEUTRAL",
    fundamental_score=0,
):
    """
    Multi-Style Institutional Strategy Engine with Swing Trade Specialization:
    - SWING (Default Specialty): Uses 48-bar Swing Structure, Fibonacci Golden Pocket (38.2%–61.8%),
      EMA 21/50/200 institutional trend alignment, and wider 1.5x / 2.5x / 4.0x ATR targets.
    - INTRADAY: Session trend pullbacks & liquidity sweeps (1.2x / 1.8x / 3.0x ATR).
    - SCALPING: Fast 1m/5m EMA 9/21 momentum bursts (1.0x / 1.5x / 2.0x ATR).
    - POSITION: Macro 4H/Daily trend waves (1.8x / 3.0x / 5.0x ATR).
    """
    style_cfg = TRADING_STYLES.get(trading_style, TRADING_STYLES["SWING"])
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
    price = c["close"]
    open_p = c["open"]
    high_p = c["high"]
    low_p = c["low"]

    ema9 = ema9_s[idx]
    ema21 = ema21_s[idx]
    ema50 = ema50_s[idx]
    ema200 = ema200_s[idx] if ema200_s else ema50
    prev_ema9 = ema9_s[max(0, idx - 1)]
    rsi14 = rsi_s[idx]
    prev_rsi = rsi_s[max(0, idx - 1)]
    atr14 = max(atr_s[idx], 0.4)
    hist = macd_h[idx]
    prev_hist = macd_h[max(0, idx - 1)]

    window_start = max(0, idx - lookback)
    recent_high = max(x["high"] for x in candles[window_start : idx + 1])
    recent_low = min(x["low"] for x in candles[window_start : idx + 1])
    swing_range = max(recent_high - recent_low, 0.01)

    # Fibonacci Golden Pocket (38.2% - 61.8% retracement) for Swing Trading
    fib_382_bull = recent_high - 0.382 * swing_range
    fib_500_bull = recent_high - 0.500 * swing_range
    fib_618_bull = recent_high - 0.618 * swing_range
    fib_382_bear = recent_low + 0.382 * swing_range
    fib_618_bear = recent_low + 0.618 * swing_range

    in_bull_golden_zone = (fib_618_bull - 0.35 * atr14) <= low_p <= (fib_382_bull + 0.35 * atr14)
    in_bear_golden_zone = (fib_382_bear - 0.35 * atr14) <= high_p <= (fib_618_bear + 0.35 * atr14)

    bar_range = max(high_p - low_p, 0.01)
    body = abs(price - open_p)
    body_ratio = body / bar_range
    lower_wick = min(price, open_p) - low_p
    upper_wick = high_p - max(price, open_p)

    bull_candle = (price > open_p and body_ratio >= 0.28) or (price >= open_p and lower_wick >= 0.45 * bar_range)
    bear_candle = (price < open_p and body_ratio >= 0.28) or (price <= open_p and upper_wick >= 0.45 * bar_range)

    # Check 1: EMA Trend Structure (Swing & Position emphasize EMA 21/50/200; Scalp/Intraday emphasize EMA 9/21/50)
    if trading_style in ("SWING", "POSITION"):
        uptrend_structure = (ema21 >= ema50 - 0.25 * atr14) and (price >= ema50 - 0.3 * atr14) and (ema9 >= ema21 - 0.2 * atr14)
        downtrend_structure = (ema21 <= ema50 + 0.25 * atr14) and (price <= ema50 + 0.3 * atr14) and (ema9 <= ema21 + 0.2 * atr14)
    else:
        uptrend_structure = ema9 >= ema21 and price > ema21 and ema21 >= ema50 - 0.3 * atr14
        downtrend_structure = ema9 <= ema21 and price < ema21 and ema21 <= ema50 + 0.3 * atr14

    # Check 2: Pullback to EMA / Fibonacci Golden Zone
    touched_buy_zone = (
        low_p <= ema9 + 0.4 * atr14
        or prev_c["low"] <= ema9_s[max(0, idx - 1)] + 0.4 * atr14
        or prev2_c["low"] <= ema21_s[max(0, idx - 2)] + 0.45 * atr14
        or (trading_style in ("SWING", "POSITION") and in_bull_golden_zone)
    ) and (price - ema21) <= 1.8 * atr14

    touched_sell_zone = (
        high_p >= ema9 - 0.4 * atr14
        or prev_c["high"] >= ema9_s[max(0, idx - 1)] - 0.4 * atr14
        or prev2_c["high"] >= ema21_s[max(0, idx - 2)] - 0.45 * atr14
        or (trading_style in ("SWING", "POSITION") and in_bear_golden_zone)
    ) and (ema21 - price) <= 1.8 * atr14

    # Check 3: Momentum & Oscillator Confirmation
    bull_momentum = (hist >= prev_hist or hist > 0) and (42 <= rsi14 <= 69) and (price >= prev_c["close"])
    bear_momentum = (hist <= prev_hist or hist < 0) and (31 <= rsi14 <= 58) and (price <= prev_c["close"])

    # Check 4: Liquidity Sweep Reversal Confirmation
    bb_low_val = bb_l[idx] if bb_l else recent_low
    bb_high_val = bb_u[idx] if bb_u else recent_high
    prev_bb_low = bb_l[max(0, idx - 1)] if bb_l else recent_low
    prev_bb_high = bb_u[max(0, idx - 1)] if bb_u else recent_high

    bull_sweep_confirmed = (
        (low_p <= bb_low_val or prev_c["low"] <= prev_bb_low or prev_rsi <= 32 or rsi14 <= 32)
        and bull_candle
        and price > prev_c["close"]
        and rsi14 > prev_rsi
    )
    bear_sweep_confirmed = (
        (high_p >= bb_high_val or prev_c["high"] >= prev_bb_high or prev_rsi >= 68 or rsi14 >= 68)
        and bear_candle
        and price < prev_c["close"]
        and rsi14 < prev_rsi
    )

    # Check 5: Structure Breakout
    brk_len = 12 if trading_style in ("SWING", "POSITION") else 8
    prev_brk_high = max(x["high"] for x in candles[max(0, idx - brk_len) : idx]) if idx >= 2 else high_p
    prev_brk_low = min(x["low"] for x in candles[max(0, idx - brk_len) : idx]) if idx >= 2 else low_p
    bull_breakout = (
        ema9 > ema21 > ema50
        and bull_candle
        and price > prev_brk_high
        and body >= 0.50 * atr14
        and 52 <= rsi14 <= 71
    )
    bear_breakout = (
        ema9 < ema21 < ema50
        and bear_candle
        and price < prev_brk_low
        and body >= 0.50 * atr14
        and 29 <= rsi14 <= 48
    )

    direction = "WAIT"
    signal_type = "WAIT"
    signal = f"WAIT (Scanning {style_cfg['name']} Structure)"
    base_conf = 42
    reason = ""

    if uptrend_structure and touched_buy_zone and bull_candle and bull_momentum and ema9 >= prev_ema9 - 0.05 * atr14:
        direction = "BUY"
        signal_type = "SWING_GOLDEN_PULLBACK" if trading_style == "SWING" else "PRO_TREND_PULLBACK"
        signal = f"BUY ({'Swing Fib/EMA Pullback' if trading_style == 'SWING' else 'Confirmed Trend Pullback'})"
        base_conf = 84 if (trading_style == "SWING" and in_bull_golden_zone) else 82
        reason = (
            f"{style_cfg['name']} Pullback Confirmed: EMA21 ({ema21:.2f}) >= EMA50 ({ema50:.2f}), "
            f"price rejected demand/Fibonacci zone (50% Fib: {fib_500_bull:.2f}) with bullish candle & rising RSI ({rsi14:.1f})."
        )
    elif downtrend_structure and touched_sell_zone and bear_candle and bear_momentum and ema9 <= prev_ema9 + 0.05 * atr14:
        direction = "SELL"
        signal_type = "SWING_GOLDEN_PULLBACK" if trading_style == "SWING" else "PRO_TREND_PULLBACK"
        signal = f"SELL ({'Swing Fib/EMA Pullback' if trading_style == 'SWING' else 'Confirmed Trend Pullback'})"
        base_conf = 84 if (trading_style == "SWING" and in_bear_golden_zone) else 82
        reason = (
            f"{style_cfg['name']} Pullback Confirmed: EMA21 ({ema21:.2f}) <= EMA50 ({ema50:.2f}), "
            f"price rejected supply/Fibonacci zone (50% Fib: {fib_500_bull:.2f}) with bearish candle & falling RSI ({rsi14:.1f})."
        )
    elif bull_sweep_confirmed:
        direction = "BUY"
        signal_type = "LIQUIDITY_SWEEP"
        signal = f"BUY ({'Swing Demand Sweep' if trading_style == 'SWING' else 'Liquidity Sweep Reversal'})"
        base_conf = 79
        reason = (
            f"Institutional Liquidity Sweep Confirmed: Lower band/swing low ({bb_low_val:.2f}) swept and rejected "
            f"with bullish close ({price:.2f}) & RSI hook ({prev_rsi:.1f} → {rsi14:.1f})."
        )
    elif bear_sweep_confirmed:
        direction = "SELL"
        signal_type = "LIQUIDITY_SWEEP"
        signal = f"SELL ({'Swing Supply Sweep' if trading_style == 'SWING' else 'Liquidity Sweep Reversal'})"
        base_conf = 79
        reason = (
            f"Institutional Liquidity Sweep Confirmed: Upper band/swing high ({bb_high_val:.2f}) swept and rejected "
            f"with bearish close ({price:.2f}) & RSI hook ({prev_rsi:.1f} → {rsi14:.1f})."
        )
    elif bull_breakout:
        direction = "BUY"
        signal_type = "MOMENTUM_BREAKOUT"
        signal = f"BUY ({'Swing Structure Breakout' if trading_style == 'SWING' else 'Institutional Breakout'})"
        base_conf = 81
        reason = (
            f"Structure Breakout Confirmed: Stacked EMA 9/21/50 ribbon with expansion candle "
            f"closing above {brk_len}-bar structure ({prev_brk_high:.2f}) and RSI at {rsi14:.1f}."
        )
    elif bear_breakout:
        direction = "SELL"
        signal_type = "MOMENTUM_BREAKOUT"
        signal = f"SELL ({'Swing Structure Breakdown' if trading_style == 'SWING' else 'Institutional Breakdown'})"
        base_conf = 81
        reason = (
            f"Structure Breakdown Confirmed: Stacked bearish EMA 9/21/50 ribbon with expansion candle "
            f"closing below {brk_len}-bar structure ({prev_brk_low:.2f}) and RSI at {rsi14:.1f}."
        )
    else:
        direction = "WAIT"
        signal_type = "WAIT"
        signal = f"WAIT (No Confirmed {style_cfg['code'].title()} Setup — Hold Fire)"
        base_conf = 42
        reason = (
            f"No {style_cfg['name']} trade opened: Price ({price:.2f}) is mid-structure between Swing High ({recent_high:.2f}) "
            f"and Swing Low ({recent_low:.2f}). Waiting for Golden Pocket ({fib_618_bull:.2f}–{fib_382_bull:.2f}) or EMA21 ({ema21:.2f}) confirmation."
        )

    # Adjust confidence with Fundamental & News alignment
    if direction == "BUY":
        if fundamental_bias == "BULLISH":
            base_conf = min(96, base_conf + 8)
        elif fundamental_bias == "BEARISH":
            base_conf = max(60, base_conf - 6)
    elif direction == "SELL":
        if fundamental_bias == "BEARISH":
            base_conf = min(96, base_conf + 8)
        elif fundamental_bias == "BULLISH":
            base_conf = max(60, base_conf - 6)

    entry = round(price, 2)
    # Determine structural bias even when WAIT so reference levels show the dominant swing direction
    ref_bull = ema21 >= ema50
    if direction == "BUY" or (direction == "WAIT" and ref_bull):
        sl = round(price - sl_mult * atr14, 2)
        tp1 = round(price + tp1_mult * atr14, 2)
        tp2 = round(price + tp2_mult * atr14, 2)
    else:
        sl = round(price + sl_mult * atr14, 2)
        tp1 = round(price - tp1_mult * atr14, 2)
        tp2 = round(price - tp2_mult * atr14, 2)

    risk = abs(entry - sl)
    reward2 = abs(tp2 - entry)
    rr_ratio = round(reward2 / risk, 2) if risk > 0 else 2.0

    checklist = [
        {
            "name": f"{style_cfg['code'].title()} EMA 21/50/200 Trend",
            "passed": bool(uptrend_structure or downtrend_structure),
            "detail": (
                f"Bullish Swing (EMA200 {ema200:.1f})"
                if uptrend_structure
                else (f"Bearish Swing (EMA200 {ema200:.1f})" if downtrend_structure else "Consolidating")
            ),
        },
        {
            "name": "Fib Golden Pocket / Value Zone",
            "passed": bool(touched_buy_zone or touched_sell_zone or bull_sweep_confirmed or bear_sweep_confirmed),
            "detail": (
                f"In Fib/EMA Zone ({fib_500_bull:.1f})"
                if (touched_buy_zone or touched_sell_zone or bull_sweep_confirmed or bear_sweep_confirmed)
                else f"Await {fib_500_bull:.1f} / {ema21:.1f}"
            ),
        },
        {
            "name": "Rejection / Expansion Candle",
            "passed": bool(bull_candle or bear_candle),
            "detail": f"{int(body_ratio * 100)}% Body ({'Bullish' if bull_candle else ('Bearish' if bear_candle else 'Doji/Neutral')})",
        },
        {
            "name": "RSI & MACD Swing Impulse",
            "passed": bool(bull_momentum or bear_momentum or bull_sweep_confirmed or bear_sweep_confirmed),
            "detail": f"RSI {rsi14:.1f} · MACD Hist {hist:+.2f}",
        },
        {
            "name": "Macro DXY & News Alignment",
            "passed": bool(
                (direction == "BUY" and fundamental_bias != "BEARISH")
                or (direction == "SELL" and fundamental_bias != "BULLISH")
                or fundamental_bias != "NEUTRAL"
            ),
            "detail": f"{fundamental_bias} ({fundamental_score:+d})",
        },
    ]

    return {
        "trading_style": trading_style,
        "style_name": style_cfg["name"],
        "style_badge": style_cfg["badge"],
        "hold_duration_label": style_cfg["hold_duration_label"],
        "sl_mult": sl_mult,
        "tp1_mult": tp1_mult,
        "tp2_mult": tp2_mult,
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
        "recent_high": round(recent_high, 2),
        "recent_low": round(recent_low, 2),
        "fib_382": round(fib_382_bull, 2),
        "fib_500": round(fib_500_bull, 2),
        "fib_618": round(fib_618_bull, 2),
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


def run_and_store_backtest(
    symbol="OANDA:XAUUSD",
    interval="1h",
    trading_style="SWING",
    strategy_mode="PRO_CONFIRMED",
    bars_tested=450,
    duration_preset=None,
    sl_mult=None,
    tp1_mult=None,
    tp2_mult=None,
    candles=None,
):
    """
    Runs a historical simulation across `bars_tested` (or deep `duration_preset`: 7_DAYS, 30_DAYS, 90_DAYS, 1_YEAR)
    for the chosen `trading_style` (SWING, INTRADAY, SCALPING, POSITION) with STRICT SINGLE-POSITION LOCK:
    - Never opens a new trade while a trade is still open.
    - Never opens a trade when `direction == 'WAIT'`.
    - Moves Stop Loss to Break-Even (Entry) once TP1 is hit, banking 50% at TP1 and letting 50% run to TP2!
    """
    if trading_style not in TRADING_STYLES:
        trading_style = "SWING"
    style_cfg = TRADING_STYLES[trading_style]

    if sl_mult is None:
        sl_mult = style_cfg["sl_mult"]
    if tp1_mult is None:
        tp1_mult = style_cfg["tp1_mult"]
    if tp2_mult is None:
        tp2_mult = style_cfg["tp2_mult"]

    actual_interval = interval
    actual_bars = int(bars_tested)

    if duration_preset and duration_preset in DURATION_PRESETS:
        preset = DURATION_PRESETS[duration_preset]
        actual_bars = preset["bars"]
        min_tf = preset.get("force_min_tf")
        tf_rank = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}
        if min_tf and tf_rank.get(actual_interval, 60) < tf_rank.get(min_tf, 60):
            actual_interval = min_tf

    if candles is None or len(candles) < actual_bars:
        _, candles = fetch_tradingview_candles(
            symbol=symbol, interval=actual_interval, n_bars=actual_bars
        )
    if len(candles) < 40:
        raise RuntimeError(f"Insufficient candles ({len(candles)}) to backtest")

    fundamentals = fetch_fundamental_analysis()
    f_bias = fundamentals["bias"]
    f_score = fundamentals["score"]

    closes = [c["close"] for c in candles]
    ema9_s = ema_series(closes, 9)
    ema21_s = ema_series(closes, 21)
    ema50_s = ema_series(closes, 50)
    ema200_s = ema_series(closes, 200)
    rsi14_s = rsi_series(closes, 14)
    atr14_s = atr_series(candles, 14)
    _, _, macd_h = macd_series(closes, 12, 26, 9)
    bb_u, _, bb_l = bollinger_series(closes, 20, 2.0)

    trades = []
    n = len(candles)
    i = 50
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
            sl_mult=sl_mult,
            tp1_mult=tp1_mult,
            tp2_mult=tp2_mult,
            fundamental_bias=f_bias,
            fundamental_score=f_score,
        )

        if sig["direction"] == "WAIT":
            i += 1
            continue

        if strategy_mode == "TREND_ONLY" and sig["signal_type"] not in ("PRO_TREND_PULLBACK", "SWING_GOLDEN_PULLBACK"):
            i += 1
            continue
        if strategy_mode == "MEAN_REVERSION" and sig["signal_type"] != "LIQUIDITY_SWEEP":
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
            if direction == "BUY":
                if cl <= active_sl:
                    if hit_tp1:
                        outcome = "WIN_TP1_BE"
                        exit_price = round((tp1 + entry) / 2.0, 2)
                    else:
                        outcome = "LOSS_SL"
                        exit_price = sl
                    exit_time = candles[j]["time_local"]
                    exit_idx = j
                    break
                if ch >= tp2:
                    outcome = "WIN_TP2"
                    exit_price = tp2
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
                        exit_price = round((tp1 + entry) / 2.0, 2)
                    else:
                        outcome = "LOSS_SL"
                        exit_price = sl
                    exit_time = candles[j]["time_local"]
                    exit_idx = j
                    break
                if cl <= tp2:
                    outcome = "WIN_TP2"
                    exit_price = tp2
                    exit_time = candles[j]["time_local"]
                    exit_idx = j
                    break
                if cl <= tp1 and not hit_tp1:
                    hit_tp1 = True
                    active_sl = entry

        if outcome is None and hit_tp1:
            outcome = "WIN_TP1"
            exit_price = tp1
            exit_idx = min(i + max_hold - 1, n - 1)
            exit_time = candles[exit_idx]["time_local"]

        if outcome is not None:
            pnl = (exit_price - entry) if direction == "BUY" else (entry - exit_price)
            pnl = round(pnl, 2)
            cum_pnl = round(cum_pnl + pnl, 2)
            peak_pnl = max(peak_pnl, cum_pnl)
            max_dd = max(max_dd, round(peak_pnl - cum_pnl, 2))
            trades.append(
                {
                    "entry_time": candles[i]["time_local"],
                    "exit_time": exit_time,
                    "direction": direction,
                    "signal_type": sig["signal_type"],
                    "confidence": sig["confidence"],
                    "entry": entry,
                    "sl": sl,
                    "tp1": tp1,
                    "tp2": tp2,
                    "exit": round(exit_price, 2),
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
    avg_win = round(gross_win / wins, 2) if wins > 0 else 0.0
    avg_loss = round(gross_loss / losses, 2) if losses > 0 else 0.0
    expectancy = round(cum_pnl / total, 2) if total > 0 else 0.0

    span_str = ""
    if candles:
        span_str = f"{candles[0]['time_local'][:10]} → {candles[-1]['time_local'][:10]}"

    mode_label = f"{trading_style} · {strategy_mode}"
    if duration_preset and duration_preset in DURATION_PRESETS:
        mode_label = f"{trading_style} · {strategy_mode} ({DURATION_PRESETS[duration_preset]['label']})"

    now_local = datetime.now(TZ_UTC7).strftime("%Y-%m-%d %H:%M:%S UTC+7")
    summary = {
        "created_at": now_local,
        "symbol": symbol,
        "timeframe": actual_interval,
        "trading_style": trading_style,
        "strategy_mode": mode_label,
        "bars_tested": len(candles),
        "sl_atr_mult": sl_mult,
        "tp1_atr_mult": tp1_mult,
        "tp2_atr_mult": tp2_mult,
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "net_pnl_pts": round(cum_pnl, 2),
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
    include_series=False,
):
    """
    Full institutional analysis pipeline:
    1. Streams TradingView OHLCV candles + live Scanner tick + Macro DXY/News Intelligence
    2. Computes Trading-Style-Specific Signal (SWING by default, INTRADAY, SCALPING, POSITION)
    3. Passes the candidate setup through the Pre-Signal AI Agent Layer (3-Agent Committee / Gemini 4 Argon)
       BEFORE emitting the final signal or locking a position
    4. Evaluates Single-Position Lock and triggers automatic Telegram Bot notifications on state transitions
    """
    init_db()
    if trading_style not in TRADING_STYLES:
        trading_style = "SWING"
    style_cfg = TRADING_STYLES[trading_style]

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
        sl_mult=style_cfg["sl_mult"],
        tp1_mult=style_cfg["tp1_mult"],
        tp2_mult=style_cfg["tp2_mult"],
        fundamental_bias=fundamentals["bias"],
        fundamental_score=fundamentals["score"],
    )

    day_high = max(highs[-288:]) if len(highs) >= 288 else max(highs)
    day_low = min(lows[-288:]) if len(lows) >= 288 else min(lows)
    last_close = closes[-1]
    pivot = (day_high + day_low + last_close) / 3.0
    r1 = 2 * pivot - day_low
    s1 = 2 * pivot - day_high
    r2 = pivot + (day_high - day_low)
    s2 = pivot - (day_high - day_low)

    swing_h = sig["recent_high"]
    swing_l = sig["recent_low"]
    diff = max(swing_h - swing_l, 0.01)
    fib_levels = {
        "0.0% (Swing High)": round(swing_h, 2),
        "23.6%": round(swing_h - 0.236 * diff, 2),
        "38.2% (Golden Top)": round(swing_h - 0.382 * diff, 2),
        "50.0% (Equilibrium)": round(swing_h - 0.500 * diff, 2),
        "61.8% (Golden Base)": round(swing_h - 0.618 * diff, 2),
        "78.6%": round(swing_h - 0.786 * diff, 2),
        "100.0% (Swing Low)": round(swing_l, 2),
    }

    indicators = {
        "ema9": round(ema9_s[-1], 2),
        "ema21": round(ema21_s[-1], 2),
        "ema50": round(ema50_s[-1], 2),
        "ema200": round(ema200_s[-1], 2),
        "rsi14": round(rsi14_s[-1], 2),
        "atr14": round(atr14_s[-1], 2),
        "macd": round(macd_l[-1], 2),
        "macd_signal": round(macd_sig[-1], 2),
        "macd_hist": round(macd_h[-1], 2),
        "bb_upper": bb_u[-1],
        "bb_mid": bb_m[-1],
        "bb_lower": bb_l[-1],
        "recent_2h_high": sig["recent_high"],
        "recent_2h_low": sig["recent_low"],
        "day_high": round(day_high, 2),
        "day_low": round(day_low, 2),
    }
    pivots = {
        "r2": round(r2, 2),
        "r1": round(r1, 2),
        "pivot": round(pivot, 2),
        "s1": round(s1, 2),
        "s2": round(s2, 2),
    }

    # ===============================================================
    # RUN PRE-SIGNAL AI AGENT LAYER BEFORE FINAL SIGNAL OUTPUT
    # ===============================================================
    ai_agent = run_ai_agent_layer(
        symbol=symbol,
        interval=interval,
        trading_style=trading_style,
        candle_ts=candles[-1]["timestamp"],
        current_price=round(last_close, 2),
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
        "timeframe": interval,
        "trading_style": trading_style,
        "style_info": style_cfg,
        "all_styles": TRADING_STYLES,
        "last_candle_time": candles[-1]["time"],
        "last_candle_time_local": candles[-1]["time_local"],
        "last_candle_ts": candles[-1]["timestamp"],
        "current_price": round(last_close, 2),
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
            "ema9": [round(x, 2) for x in ema9_s[-tail:]],
            "ema21": [round(x, 2) for x in ema21_s[-tail:]],
            "ema50": [round(x, 2) for x in ema50_s[-tail:]],
            "ema200": [round(x, 2) for x in ema200_s[-tail:]],
            "bb_upper": bb_u[-tail:],
            "bb_lower": bb_l[-tail:],
            "rsi14": [round(x, 2) for x in rsi14_s[-tail:]],
            "macd": [round(x, 2) for x in macd_l[-tail:]],
            "macd_signal": [round(x, 2) for x in macd_sig[-tail:]],
            "macd_hist": [round(x, 2) for x in macd_h[-tail:]],
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
                strategy_mode="PRO_CONFIRMED",
                bars_tested=450,
                sl_mult=style_cfg["sl_mult"],
                tp1_mult=style_cfg["tp1_mult"],
                tp2_mult=style_cfg["tp2_mult"],
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
