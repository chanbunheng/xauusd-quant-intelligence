#!/usr/bin/env python3
"""
Gold (XAU/USD) Pro Institutional TradingView Signal, AI Agent Layer, Telegram Bot & SQLite Backtest Server.
Serves interactive UI on http://127.0.0.1:8765 and JSON APIs:
- GET  /api/tick?symbol=OANDA:XAUUSD
- GET  /api/analyze?symbol=OANDA:XAUUSD&interval=1h&style=SWING
- GET  /api/mtf?symbol=OANDA:XAUUSD&style=SWING
- GET  /api/fundamentals
- GET  /api/backtests
- GET  /api/backtest_detail?run_id=1&direction=ALL&outcome=ALL
- POST /api/backtest/run
- POST /api/position/close
- GET  /api/live_signals
- GET  /api/telegram/status
- POST /api/telegram/sync
- POST /api/telegram/send
- POST /api/settings
"""

import json
import os
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from analyze_gold_5m import (
    TRADING_STYLES,
    analyze_timeframe,
    broadcast_telegram_signal,
    fetch_fundamental_analysis,
    fetch_live_tv_tick,
    run_and_store_backtest,
    sync_telegram_updates,
    verify_telegram_bot,
)
from db import (
    force_close_active_signals,
    get_all_settings,
    get_backtest_run_details,
    get_backtest_runs,
    get_db_status,
    get_live_signals,
    init_db,
    remove_telegram_subscriber,
    set_setting,
    upsert_telegram_subscriber,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8765"))
ALLOWED_SYMBOLS = ("FX:XAUUSD", "OANDA:XAUUSD", "FOREXCOM:XAUUSD")
ALLOWED_STYLES = ("SWING", "INTRADAY", "SCALPING", "POSITION")
ALLOWED_INTERVALS = ("1m", "5m", "15m", "1h", "4h", "1d")


def _telegram_background_worker():
    """
    24/7 Cloud Background Daemon:
    1. Every 5s: Polls @this_is_ai_signal_bot for /start, /swing, /intraday, /scalp, /news commands.
    2. Every 60s: Runs autonomous Swing (1h) & Intraday (15m) AI Agent scans on OANDA:XAUUSD so new signals
       and TP/SL hits are recorded to Supabase & pushed to Telegram even with zero browsers open.
    """
    last_auto_scan = 0.0
    while True:
        try:
            sync_telegram_updates(run_commands=True)
        except Exception:
            pass

        now_ts = time.time()
        if now_ts - last_auto_scan >= 60.0:
            last_auto_scan = now_ts
            for style, tf in (("SWING", "1h"), ("INTRADAY", "15m")):
                try:
                    analyze_timeframe(
                        symbol="OANDA:XAUUSD",
                        interval=tf,
                        trading_style=style,
                        include_series=False,
                    )
                except Exception:
                    pass

        time.sleep(5)


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/api/health":
            self._send_json(
                {
                    "ok": True,
                    "service": "xauusd-ai-quant-backend",
                    "database": get_db_status(),
                }
            )
            return

        if path in ("/", "/index.html"):
            index_path = os.path.join(BASE_DIR, "index.html")
            with open(index_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        symbol = qs.get("symbol", ["OANDA:XAUUSD"])[0]
        if symbol not in ALLOWED_SYMBOLS:
            symbol = "OANDA:XAUUSD"

        style = qs.get("style", ["SWING"])[0].upper()
        if style not in ALLOWED_STYLES:
            style = "SWING"

        if path == "/api/tick":
            try:
                tick = fetch_live_tv_tick(symbol=symbol)
                self._send_json(tick)
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=500)
            return

        if path == "/api/fundamentals":
            try:
                force = qs.get("force", ["0"])[0] == "1"
                data = fetch_fundamental_analysis(force=force)
                self._send_json(data)
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=500)
            return

        if path == "/api/analyze":
            default_tf = TRADING_STYLES[style]["default_tf"]
            interval = qs.get("interval", [default_tf])[0]
            if interval not in ALLOWED_INTERVALS:
                interval = default_tf
            try:
                data = analyze_timeframe(
                    symbol=symbol,
                    interval=interval,
                    trading_style=style,
                    include_series=True,
                )
                self._send_json(data)
            except Exception as exc:
                self._send_json({"error": str(exc), "trace": traceback.format_exc()}, status=500)
            return

        if path == "/api/mtf":
            try:
                mtf_list = TRADING_STYLES[style]["mtf_list"]
                mtf = {}
                for tf in mtf_list:
                    res = analyze_timeframe(
                        symbol=symbol,
                        interval=tf,
                        trading_style=style,
                        include_series=False,
                    )
                    mtf[tf] = {
                        "timeframe": tf,
                        "trading_style": style,
                        "direction": res["direction"],
                        "signal": res["signal"],
                        "confidence": res["confidence"],
                        "ai_verdict": res["ai_agent"]["verdict"],
                        "price": res["current_price"],
                        "entry": res["entry"],
                        "stop_loss": res["stop_loss"],
                        "take_profit_1": res["take_profit_1"],
                        "rsi14": res["indicators"]["rsi14"],
                        "ema9": res["indicators"]["ema9"],
                        "ema21": res["indicators"]["ema21"],
                        "ema50": res["indicators"]["ema50"],
                    }
                self._send_json({"mtf": mtf, "mtf_order": mtf_list, "trading_style": style})
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=500)
            return

        if path == "/api/telegram/status":
            try:
                force = qs.get("force", ["0"])[0] == "1"
                status = verify_telegram_bot(force=force)
                settings = get_all_settings()
                status["has_gemini_key"] = bool(settings.get("gemini_api_key", "").strip())
                self._send_json(status)
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=500)
            return

        if path == "/api/backtests":
            try:
                runs = get_backtest_runs(limit=50)
                self._send_json({"runs": runs})
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=500)
            return

        if path == "/api/backtest_detail":
            try:
                run_id_str = qs.get("run_id", [None])[0]
                run_id = int(run_id_str) if run_id_str and run_id_str.isdigit() else None
                direction = qs.get("direction", ["ALL"])[0]
                outcome = qs.get("outcome", ["ALL"])[0]
                detail = get_backtest_run_details(
                    run_id=run_id,
                    direction_filter=direction if direction in ("BUY", "SELL") else None,
                    outcome_filter=outcome if outcome in ("WIN", "LOSS") else None,
                    limit=400,
                )
                self._send_json({"detail": detail})
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=500)
            return

        if path == "/api/live_signals":
            try:
                signals = get_live_signals(limit=80)
                self._send_json({"signals": signals})
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=500)
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        try:
            body = json.loads(raw) if raw else {}
        except Exception:
            body = {}

        if parsed.path == "/api/backtest/run":
            try:
                symbol = body.get("symbol", "OANDA:XAUUSD")
                if symbol not in ALLOWED_SYMBOLS:
                    symbol = "OANDA:XAUUSD"
                trading_style = body.get("trading_style", "SWING").upper()
                if trading_style not in ALLOWED_STYLES:
                    trading_style = "SWING"
                style_cfg = TRADING_STYLES[trading_style]

                interval = body.get("interval", style_cfg["default_tf"])
                if interval not in ALLOWED_INTERVALS:
                    interval = style_cfg["default_tf"]
                strategy_mode = body.get("strategy_mode", "PRO_CONFIRMED")
                if strategy_mode not in ("PRO_CONFIRMED", "TREND_ONLY", "MEAN_REVERSION", "HIGH_CONFIDENCE"):
                    strategy_mode = "PRO_CONFIRMED"
                duration_preset = body.get("duration_preset", "450_BARS")
                bars_tested = int(body.get("bars_tested", 450))
                sl_mult = float(body.get("sl_mult", style_cfg["sl_mult"]))
                tp1_mult = float(body.get("tp1_mult", style_cfg["tp1_mult"]))
                tp2_mult = float(body.get("tp2_mult", style_cfg["tp2_mult"]))

                detail = run_and_store_backtest(
                    symbol=symbol,
                    interval=interval,
                    trading_style=trading_style,
                    strategy_mode=strategy_mode,
                    bars_tested=bars_tested,
                    duration_preset=duration_preset,
                    sl_mult=sl_mult,
                    tp1_mult=tp1_mult,
                    tp2_mult=tp2_mult,
                )
                runs = get_backtest_runs(limit=50)
                self._send_json({"detail": detail, "runs": runs})
            except Exception as exc:
                self._send_json({"error": str(exc), "trace": traceback.format_exc()}, status=500)
            return

        if parsed.path == "/api/position/close":
            try:
                force_close_active_signals(
                    symbol=body.get("symbol"), timeframe=body.get("timeframe")
                )
                self._send_json({"ok": True})
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=500)
            return

        if parsed.path == "/api/telegram/sync":
            try:
                chat_id_manual = (body.get("chat_id") or "").strip()
                if chat_id_manual:
                    upsert_telegram_subscriber(
                        chat_id_manual, username="ManualInput", first_name="Dashboard Trader"
                    )
                sync_res = sync_telegram_updates(run_commands=True)
                status = verify_telegram_bot(force=False)
                status["sync_result"] = sync_res
                self._send_json(status)
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=500)
            return

        if parsed.path == "/api/telegram/send":
            try:
                symbol = body.get("symbol", "OANDA:XAUUSD")
                if symbol not in ALLOWED_SYMBOLS:
                    symbol = "OANDA:XAUUSD"
                style = body.get("trading_style", "SWING").upper()
                if style not in ALLOWED_STYLES:
                    style = "SWING"
                interval = body.get("interval", TRADING_STYLES[style]["default_tf"])
                if interval not in ALLOWED_INTERVALS:
                    interval = TRADING_STYLES[style]["default_tf"]
                chat_id = (body.get("chat_id") or "").strip() or None

                # First sync any recent /start messages from Telegram so chat_id is auto-detected
                sync_telegram_updates(run_commands=False)
                sig_data = analyze_timeframe(
                    symbol=symbol,
                    interval=interval,
                    trading_style=style,
                    include_series=False,
                )
                send_res = broadcast_telegram_signal(
                    sig_data,
                    target_chat_id=chat_id,
                    event_type=f"BROADCAST_{style}",
                )
                status = verify_telegram_bot(force=False)
                self._send_json({"broadcast": send_res, "telegram": status})
            except Exception as exc:
                self._send_json({"error": str(exc), "trace": traceback.format_exc()}, status=500)
            return

        if parsed.path == "/api/settings":
            try:
                if "telegram_auto_notify" in body:
                    set_setting("telegram_auto_notify", "1" if body["telegram_auto_notify"] else "0")
                if "gemini_api_key" in body:
                    set_setting("gemini_api_key", str(body["gemini_api_key"]).strip())
                if "remove_chat_id" in body and body["remove_chat_id"]:
                    remove_telegram_subscriber(body["remove_chat_id"])
                status = verify_telegram_bot(force=False)
                settings = get_all_settings()
                status["has_gemini_key"] = bool(settings.get("gemini_api_key", "").strip())
                self._send_json({"ok": True, "telegram": status})
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=500)
            return

        self.send_response(404)
        self.end_headers()


if __name__ == "__main__":
    init_db()
    t = threading.Thread(target=_telegram_background_worker, daemon=True)
    t.start()
    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer((HOST, PORT), DashboardHandler)
    print(f"Gold Signal Dashboard & API running at http://{HOST}:{PORT} (DB: Supabase PostgreSQL)", flush=True)
    server.serve_forever()
