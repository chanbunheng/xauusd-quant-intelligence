#!/usr/bin/env python3
"""
Database Manager for XAU/USD Gold Signal Terminal.
Primary Database: Supabase PostgreSQL (Project: gold-signal-db / cpotlpgymbgfqhedbmrb, Region: ap-southeast-1)
Local Cache / Fallback: SQLite (gold_quant.db)

Stores:
1. backtest_runs: Summary metrics & parameters for every backtest run (including trading_style & deep 30d/90d/1y runs)
2. backtest_trades: Every individual simulated trade linked to a backtest run
3. live_signals: Strict Single-Position Lock forward-tested live signals vetted by the AI Agent Layer
4. app_settings: Persistent configuration (Telegram Bot token, Gemini API key, default trading style)
5. telegram_subscribers & telegram_logs: Subscribed Telegram chat IDs and alert delivery ledger
"""

import json
import os
import sqlite3
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

DB_PATH = os.environ.get(
    "DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "gold_quant.db"),
)
TZ_UTC7 = timezone(timedelta(hours=7))

DEFAULT_TELEGRAM_TOKEN = os.environ.get(
    "TELEGRAM_BOT_TOKEN", "9190309560:AAEfcT6FMHYEQoYrVucvrq3o9YjgY7Zgtnw"
)
DEFAULT_TELEGRAM_GROUP_ID = os.environ.get("TELEGRAM_GROUP_ID", "-5523180993")

# Supabase PostgreSQL Configuration (gold-signal-db / ap-southeast-1)
SUPABASE_URL = os.environ.get(
    "SUPABASE_URL", "https://cpotlpgymbgfqhedbmrb.supabase.co"
).rstrip("/")
SUPABASE_KEY = os.environ.get(
    "SUPABASE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNwb3RscGd5bWJnZnFoZWRibXJiIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTQ0NzYzMjcsImV4cCI6MjExMDA1MjMyN30.pXpiqyhjXY77yifpB_u4fN2BiTVNU7Hry4WBScq3jcc",
)
SUPABASE_BOT_SECRET = os.environ.get(
    "SUPABASE_BOT_SECRET", "gold_quant_sb_secret_9f8e7d6c5b4a3210_xauusd"
)
USE_SUPABASE = os.environ.get("USE_SUPABASE", "1") != "0" and bool(SUPABASE_URL and SUPABASE_KEY)

_DB_INITIALIZED = False


def _sb_request(method, table_or_path, params=None, body=None, prefer="return=representation"):
    """Executes an authenticated REST query against Supabase PostgreSQL with RLS x-bot-secret."""
    if not USE_SUPABASE:
        return None
    url = f"{SUPABASE_URL}/rest/v1/{table_or_path.lstrip('/')}"
    if params:
        qs = urllib.parse.urlencode(params, safe=".,()*!:")
        url = f"{url}?{qs}"

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "x-bot-secret": SUPABASE_BOT_SECRET,
        "Accept": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer

    data_bytes = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data_bytes = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=8) as resp:
        raw = resp.read().decode("utf-8")
        if not raw:
            return []
        return json.loads(raw)


def get_db_status():
    return {
        "provider": "Supabase PostgreSQL" if USE_SUPABASE else "SQLite Local",
        "project_ref": "cpotlpgymbgfqhedbmrb",
        "supabase_url": SUPABASE_URL,
        "region": "ap-southeast-1 (Singapore)",
    }


def get_conn():
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_column(conn, table, col_name, col_def):
    cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if col_name not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")


def init_db():
    global _DB_INITIALIZED
    if _DB_INITIALIZED:
        return
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS backtest_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                trading_style TEXT NOT NULL DEFAULT 'SWING',
                strategy_mode TEXT NOT NULL,
                bars_tested INTEGER NOT NULL,
                sl_atr_mult REAL NOT NULL,
                tp1_atr_mult REAL NOT NULL,
                tp2_atr_mult REAL NOT NULL,
                total_trades INTEGER NOT NULL,
                wins INTEGER NOT NULL,
                losses INTEGER NOT NULL,
                win_rate REAL NOT NULL,
                net_pnl_pts REAL NOT NULL,
                profit_factor REAL NOT NULL,
                max_drawdown_pts REAL NOT NULL,
                expectancy_pts REAL NOT NULL,
                avg_win REAL NOT NULL,
                avg_loss REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS backtest_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                entry_time TEXT NOT NULL,
                exit_time TEXT NOT NULL,
                direction TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                confidence INTEGER NOT NULL,
                entry_price REAL NOT NULL,
                sl_price REAL NOT NULL,
                tp1_price REAL NOT NULL,
                tp2_price REAL NOT NULL,
                exit_price REAL NOT NULL,
                outcome TEXT NOT NULL,
                pnl_pts REAL NOT NULL,
                cum_pnl_pts REAL NOT NULL,
                rationale TEXT,
                FOREIGN KEY(run_id) REFERENCES backtest_runs(id)
            );

            CREATE TABLE IF NOT EXISTS live_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recorded_at TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                trading_style TEXT NOT NULL DEFAULT 'SWING',
                candle_time TEXT NOT NULL,
                direction TEXT NOT NULL,
                signal TEXT NOT NULL,
                confidence INTEGER NOT NULL,
                entry_price REAL NOT NULL,
                sl_price REAL NOT NULL,
                tp1_price REAL NOT NULL,
                tp2_price REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                outcome_price REAL,
                outcome_time TEXT,
                pnl_pts REAL,
                rationale TEXT,
                ai_verdict TEXT DEFAULT 'APPROVED',
                ai_summary TEXT DEFAULT '',
                tp1_hit INTEGER DEFAULT 0,
                UNIQUE(symbol, timeframe, candle_time)
            );

            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS telegram_subscribers (
                chat_id TEXT PRIMARY KEY,
                username TEXT DEFAULT '',
                first_name TEXT DEFAULT '',
                chat_type TEXT DEFAULT 'private',
                subscribed_at TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS telegram_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sent_at TEXT NOT NULL,
                chat_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                message_preview TEXT NOT NULL,
                ok INTEGER NOT NULL DEFAULT 1
            );
            """
        )
        _ensure_column(conn, "backtest_runs", "trading_style", "TEXT NOT NULL DEFAULT 'SWING'")
        _ensure_column(conn, "live_signals", "trading_style", "TEXT NOT NULL DEFAULT 'SWING'")
        _ensure_column(conn, "live_signals", "ai_verdict", "TEXT DEFAULT 'APPROVED'")
        _ensure_column(conn, "live_signals", "ai_summary", "TEXT DEFAULT ''")
        _ensure_column(conn, "live_signals", "tp1_hit", "INTEGER DEFAULT 0")

        now_str = datetime.now(TZ_UTC7).strftime("%Y-%m-%d %H:%M:%S UTC+7")
        defaults = {
            "telegram_bot_token": DEFAULT_TELEGRAM_TOKEN,
            "telegram_auto_notify": "1",
            "default_trading_style": "SWING",
            "ai_agent_mode": "HYBRID_ARGON",
            "gemini_api_key": os.environ.get("GEMINI_API_KEY", ""),
            "telegram_last_update_id": "0",
        }
        for k, v in defaults.items():
            conn.execute(
                "INSERT OR IGNORE INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)",
                (k, v, now_str),
            )
        if DEFAULT_TELEGRAM_GROUP_ID:
            conn.execute(
                """
                INSERT OR IGNORE INTO telegram_subscribers (chat_id, username, first_name, chat_type, subscribed_at, active)
                VALUES (?, 'AI_Bot_Signal_Group', 'AI Bot Signal', 'group', ?, 1)
                """,
                (DEFAULT_TELEGRAM_GROUP_ID, now_str),
            )
        conn.commit()
    _DB_INITIALIZED = True


def get_setting(key, default=""):
    init_db()
    if USE_SUPABASE:
        try:
            rows = _sb_request("GET", "app_settings", params={"key": f"eq.{key}", "select": "value"})
            if rows:
                return rows[0]["value"]
        except Exception:
            pass
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key, value):
    init_db()
    now_str = datetime.now(TZ_UTC7).strftime("%Y-%m-%d %H:%M:%S UTC+7")
    if USE_SUPABASE:
        try:
            _sb_request(
                "POST",
                "app_settings",
                params={"on_conflict": "key"},
                body={"key": key, "value": str(value), "updated_at": now_str},
                prefer="resolution=merge-duplicates,return=minimal",
            )
        except Exception:
            pass
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (key, str(value), now_str),
        )
        conn.commit()


def get_all_settings():
    init_db()
    if USE_SUPABASE:
        try:
            rows = _sb_request("GET", "app_settings", params={"select": "key,value,updated_at"})
            if rows:
                return {r["key"]: r["value"] for r in rows}
        except Exception:
            pass
    with get_conn() as conn:
        rows = conn.execute("SELECT key, value, updated_at FROM app_settings").fetchall()
        return {r["key"]: r["value"] for r in rows}


def upsert_telegram_subscriber(chat_id, username="", first_name="", chat_type="private"):
    init_db()
    now_str = datetime.now(TZ_UTC7).strftime("%Y-%m-%d %H:%M:%S UTC+7")
    cid = str(chat_id).strip()
    if USE_SUPABASE:
        try:
            _sb_request(
                "POST",
                "telegram_subscribers",
                params={"on_conflict": "chat_id"},
                body={
                    "chat_id": cid,
                    "username": username or "",
                    "first_name": first_name or "Trader",
                    "chat_type": chat_type or "private",
                    "subscribed_at": now_str,
                    "active": 1,
                },
                prefer="resolution=merge-duplicates,return=minimal",
            )
        except Exception:
            pass
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO telegram_subscribers (chat_id, username, first_name, chat_type, subscribed_at, active)
            VALUES (?, ?, ?, ?, ?, 1)
            ON CONFLICT(chat_id) DO UPDATE SET
                username=CASE WHEN excluded.username != '' THEN excluded.username ELSE telegram_subscribers.username END,
                first_name=CASE WHEN excluded.first_name != '' THEN excluded.first_name ELSE telegram_subscribers.first_name END,
                chat_type=excluded.chat_type,
                active=1
            """,
            (cid, username or "", first_name or "", chat_type or "private", now_str),
        )
        conn.commit()


def remove_telegram_subscriber(chat_id):
    init_db()
    cid = str(chat_id).strip()
    if USE_SUPABASE:
        try:
            _sb_request(
                "DELETE",
                "telegram_subscribers",
                params={"chat_id": f"eq.{cid}"},
                prefer="return=minimal",
            )
        except Exception:
            pass
    with get_conn() as conn:
        conn.execute("DELETE FROM telegram_subscribers WHERE chat_id = ?", (cid,))
        conn.commit()


def get_telegram_subscribers(active_only=True):
    init_db()
    if USE_SUPABASE:
        try:
            params = {"select": "*", "order": "subscribed_at.desc"}
            if active_only:
                params["active"] = "eq.1"
            rows = _sb_request("GET", "telegram_subscribers", params=params)
            if rows is not None:
                return rows
        except Exception:
            pass
    with get_conn() as conn:
        if active_only:
            rows = conn.execute(
                "SELECT * FROM telegram_subscribers WHERE active = 1 ORDER BY subscribed_at DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM telegram_subscribers ORDER BY subscribed_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]


def log_telegram_message(chat_id, event_type, message_preview, ok=True):
    init_db()
    now_str = datetime.now(TZ_UTC7).strftime("%Y-%m-%d %H:%M:%S UTC+7")
    preview = (message_preview or "")[:240]
    ok_int = 1 if ok else 0
    if USE_SUPABASE:
        try:
            _sb_request(
                "POST",
                "telegram_logs",
                body={
                    "sent_at": now_str,
                    "chat_id": str(chat_id),
                    "event_type": event_type,
                    "message_preview": preview,
                    "ok": ok_int,
                },
                prefer="return=minimal",
            )
        except Exception:
            pass
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO telegram_logs (sent_at, chat_id, event_type, message_preview, ok)
            VALUES (?, ?, ?, ?, ?)
            """,
            (now_str, str(chat_id), event_type, preview, ok_int),
        )
        conn.commit()


def get_telegram_logs(limit=25):
    init_db()
    if USE_SUPABASE:
        try:
            rows = _sb_request(
                "GET",
                "telegram_logs",
                params={"select": "*", "order": "id.desc", "limit": str(limit)},
            )
            if rows is not None:
                return rows
        except Exception:
            pass
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM telegram_logs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def save_backtest_run(summary, trades):
    init_db()
    sb_run_id = None
    if USE_SUPABASE:
        try:
            inserted_runs = _sb_request(
                "POST",
                "backtest_runs",
                body={
                    "created_at": summary["created_at"],
                    "symbol": summary["symbol"],
                    "timeframe": summary["timeframe"],
                    "trading_style": summary.get("trading_style", "SWING"),
                    "strategy_mode": summary["strategy_mode"],
                    "bars_tested": summary["bars_tested"],
                    "sl_atr_mult": summary["sl_atr_mult"],
                    "tp1_atr_mult": summary["tp1_atr_mult"],
                    "tp2_atr_mult": summary["tp2_atr_mult"],
                    "total_trades": summary["total_trades"],
                    "wins": summary["wins"],
                    "losses": summary["losses"],
                    "win_rate": summary["win_rate"],
                    "net_pnl_pts": summary["net_pnl_pts"],
                    "profit_factor": summary["profit_factor"],
                    "max_drawdown_pts": summary["max_drawdown_pts"],
                    "expectancy_pts": summary["expectancy_pts"],
                    "avg_win": summary["avg_win"],
                    "avg_loss": summary["avg_loss"],
                },
                prefer="return=representation",
            )
            if inserted_runs and len(inserted_runs) > 0:
                sb_run_id = inserted_runs[0]["id"]
                if trades:
                    trade_payloads = [
                        {
                            "run_id": sb_run_id,
                            "symbol": summary["symbol"],
                            "timeframe": summary["timeframe"],
                            "entry_time": t["entry_time"],
                            "exit_time": t["exit_time"],
                            "direction": t["direction"],
                            "signal_type": t["signal_type"],
                            "confidence": t["confidence"],
                            "entry_price": t["entry"],
                            "sl_price": t["sl"],
                            "tp1_price": t["tp1"],
                            "tp2_price": t["tp2"],
                            "exit_price": t["exit"],
                            "outcome": t["outcome"],
                            "pnl_pts": t["pnl"],
                            "cum_pnl_pts": t["cum_pnl"],
                            "rationale": t.get("rationale", ""),
                        }
                        for t in trades
                    ]
                    _sb_request(
                        "POST",
                        "backtest_trades",
                        body=trade_payloads,
                        prefer="return=minimal",
                    )
        except Exception:
            pass

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO backtest_runs (
                created_at, symbol, timeframe, trading_style, strategy_mode, bars_tested,
                sl_atr_mult, tp1_atr_mult, tp2_atr_mult,
                total_trades, wins, losses, win_rate, net_pnl_pts,
                profit_factor, max_drawdown_pts, expectancy_pts, avg_win, avg_loss
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary["created_at"],
                summary["symbol"],
                summary["timeframe"],
                summary.get("trading_style", "SWING"),
                summary["strategy_mode"],
                summary["bars_tested"],
                summary["sl_atr_mult"],
                summary["tp1_atr_mult"],
                summary["tp2_atr_mult"],
                summary["total_trades"],
                summary["wins"],
                summary["losses"],
                summary["win_rate"],
                summary["net_pnl_pts"],
                summary["profit_factor"],
                summary["max_drawdown_pts"],
                summary["expectancy_pts"],
                summary["avg_win"],
                summary["avg_loss"],
            ),
        )
        local_run_id = cur.lastrowid

        for t in trades:
            cur.execute(
                """
                INSERT INTO backtest_trades (
                    run_id, symbol, timeframe, entry_time, exit_time,
                    direction, signal_type, confidence,
                    entry_price, sl_price, tp1_price, tp2_price, exit_price,
                    outcome, pnl_pts, cum_pnl_pts, rationale
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    local_run_id,
                    summary["symbol"],
                    summary["timeframe"],
                    t["entry_time"],
                    t["exit_time"],
                    t["direction"],
                    t["signal_type"],
                    t["confidence"],
                    t["entry"],
                    t["sl"],
                    t["tp1"],
                    t["tp2"],
                    t["exit"],
                    t["outcome"],
                    t["pnl"],
                    t["cum_pnl"],
                    t.get("rationale", ""),
                ),
            )
        conn.commit()
        return sb_run_id if sb_run_id is not None else local_run_id


def get_backtest_runs(limit=40):
    init_db()
    if USE_SUPABASE:
        try:
            rows = _sb_request(
                "GET",
                "backtest_runs",
                params={"select": "*", "order": "id.desc", "limit": str(limit)},
            )
            if rows is not None:
                return rows
        except Exception:
            pass
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM backtest_runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_backtest_run_details(run_id=None, direction_filter=None, outcome_filter=None, limit=400):
    init_db()
    if USE_SUPABASE:
        try:
            if run_id is None:
                runs = _sb_request(
                    "GET",
                    "backtest_runs",
                    params={"select": "*", "order": "id.desc", "limit": "1"},
                )
            else:
                runs = _sb_request(
                    "GET",
                    "backtest_runs",
                    params={"select": "*", "id": f"eq.{run_id}", "limit": "1"},
                )
            if runs:
                run_dict = dict(runs[0])
                t_params = {
                    "select": "*",
                    "run_id": f"eq.{run_dict['id']}",
                    "order": "id.desc",
                    "limit": str(limit),
                }
                if direction_filter in ("BUY", "SELL"):
                    t_params["direction"] = f"eq.{direction_filter}"
                if outcome_filter == "WIN":
                    t_params["outcome"] = "like.WIN*"
                elif outcome_filter == "LOSS":
                    t_params["outcome"] = "like.LOSS*"
                trades = _sb_request("GET", "backtest_trades", params=t_params) or []
                eq_rows = (
                    _sb_request(
                        "GET",
                        "backtest_trades",
                        params={
                            "select": "id,entry_time,exit_time,pnl_pts,cum_pnl_pts,outcome",
                            "run_id": f"eq.{run_dict['id']}",
                            "order": "id.asc",
                        },
                    )
                    or []
                )
                run_dict["trades"] = trades
                run_dict["equity_curve"] = eq_rows
                return run_dict
        except Exception:
            pass

    with get_conn() as conn:
        if run_id is None:
            row = conn.execute("SELECT * FROM backtest_runs ORDER BY id DESC LIMIT 1").fetchone()
        else:
            row = conn.execute("SELECT * FROM backtest_runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            return None
        run_dict = dict(row)

        query = "SELECT * FROM backtest_trades WHERE run_id = ?"
        params = [run_dict["id"]]
        if direction_filter in ("BUY", "SELL"):
            query += " AND direction = ?"
            params.append(direction_filter)
        if outcome_filter == "WIN":
            query += " AND outcome LIKE 'WIN%'"
        elif outcome_filter == "LOSS":
            query += " AND outcome LIKE 'LOSS%'"
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        trades = [dict(r) for r in conn.execute(query, params).fetchall()]
        eq_rows = conn.execute(
            "SELECT id, entry_time, exit_time, pnl_pts, cum_pnl_pts, outcome FROM backtest_trades WHERE run_id = ? ORDER BY id ASC",
            (run_dict["id"],),
        ).fetchall()
        run_dict["trades"] = trades
        run_dict["equity_curve"] = [dict(r) for r in eq_rows]
        return run_dict


def record_and_evaluate_live_signal(sig_data, candles, on_event_callback=None):
    """
    Enforces Strict Single-Position Lock AFTER the AI Agent Layer has vetted the signal.
    Persists to Supabase PostgreSQL (and mirrors locally in SQLite).
    """
    init_db()
    now_str = datetime.now(TZ_UTC7).strftime("%Y-%m-%d %H:%M:%S UTC+7")
    symbol = sig_data["symbol"]
    timeframe = sig_data["timeframe"]
    trading_style = sig_data.get("trading_style", "SWING")
    current_price = sig_data["current_price"]
    ai_agent = sig_data.get("ai_agent") or {}
    ai_verdict = ai_agent.get("verdict", "APPROVED")
    ai_summary = ai_agent.get("executive_summary", "")

    events_to_notify = []

    if USE_SUPABASE:
        try:
            active_rows = (
                _sb_request(
                    "GET",
                    "live_signals",
                    params={
                        "select": "*",
                        "symbol": f"eq.{symbol}",
                        "timeframe": f"eq.{timeframe}",
                        "status": "eq.ACTIVE",
                        "order": "id.asc",
                    },
                )
                or []
            )

            if len(active_rows) > 1:
                for old_row in active_rows[:-1]:
                    _sb_request(
                        "PATCH",
                        "live_signals",
                        params={"id": f"eq.{old_row['id']}"},
                        body={"status": "SUPERSEDED", "outcome_time": now_str},
                        prefer="return=minimal",
                    )
                active_rows = [active_rows[-1]]

            still_active = None
            if active_rows and candles:
                row = active_rows[0]
                d = row["direction"]
                entry = float(row["entry_price"])
                sl = float(row["sl_price"])
                tp1 = float(row["tp1_price"])
                tp2 = float(row["tp2_price"])

                closed_status = None
                outcome_p = None
                outcome_t = None
                pnl = 0.0

                for c in candles[-5:]:
                    if c["time"] <= row["candle_time"]:
                        continue
                    ch = c["high"]
                    cl = c["low"]
                    ct = c.get("time_local") or c["time"]
                    if d == "BUY":
                        if cl <= sl:
                            closed_status, outcome_p, outcome_t, pnl = "HIT_SL", sl, ct, round(sl - entry, 2)
                            break
                        elif ch >= tp2:
                            closed_status, outcome_p, outcome_t, pnl = "HIT_TP2", tp2, ct, round(tp2 - entry, 2)
                            break
                        elif ch >= tp1:
                            closed_status, outcome_p, outcome_t, pnl = "HIT_TP1", tp1, ct, round(tp1 - entry, 2)
                            break
                    else:
                        if ch >= sl:
                            closed_status, outcome_p, outcome_t, pnl = "HIT_SL", sl, ct, round(entry - sl, 2)
                            break
                        elif cl <= tp2:
                            closed_status, outcome_p, outcome_t, pnl = "HIT_TP2", tp2, ct, round(entry - tp2, 2)
                            break
                        elif cl <= tp1:
                            closed_status, outcome_p, outcome_t, pnl = "HIT_TP1", tp1, ct, round(entry - tp1, 2)
                            break

                if closed_status:
                    _sb_request(
                        "PATCH",
                        "live_signals",
                        params={"id": f"eq.{row['id']}"},
                        body={
                            "status": closed_status,
                            "outcome_price": outcome_p,
                            "outcome_time": outcome_t,
                            "pnl_pts": pnl,
                        },
                        prefer="return=minimal",
                    )
                    closed_trade = dict(row)
                    closed_trade["status"] = closed_status
                    closed_trade["outcome_price"] = outcome_p
                    closed_trade["outcome_time"] = outcome_t
                    closed_trade["pnl_pts"] = pnl
                    events_to_notify.append(("POSITION_CLOSED", closed_trade))
                else:
                    still_active = dict(row)

            if still_active:
                d = still_active["direction"]
                entry = float(still_active["entry_price"])
                floating = round((current_price - entry) if d == "BUY" else (entry - current_price), 2)
                still_active["floating_pnl"] = floating
                res_payload = {
                    "locked": True,
                    "reason": (
                        f"Position #{still_active['id']} ({still_active.get('trading_style', 'SWING')} · {d} @ {entry:.2f}) "
                        f"is currently ACTIVE in Supabase. Waiting for SL ({still_active['sl_price']:.2f}) or TP1 ({still_active['tp1_price']:.2f}) "
                        f"before scanning for next setup."
                    ),
                    "active_trade": still_active,
                }
            elif sig_data["direction"] in ("BUY", "SELL"):
                inserted_rows = (
                    _sb_request(
                        "POST",
                        "live_signals",
                        params={"on_conflict": "symbol,timeframe,candle_time"},
                        body={
                            "recorded_at": now_str,
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "trading_style": trading_style,
                            "candle_time": sig_data["last_candle_time"],
                            "direction": sig_data["direction"],
                            "signal": sig_data["signal"],
                            "confidence": sig_data["confidence"],
                            "entry_price": sig_data["entry"],
                            "sl_price": sig_data["stop_loss"],
                            "tp1_price": sig_data["take_profit_1"],
                            "tp2_price": sig_data["take_profit_2"],
                            "status": "ACTIVE",
                            "rationale": sig_data["rationale"],
                            "ai_verdict": ai_verdict,
                            "ai_summary": ai_summary,
                        },
                        prefer="resolution=ignore-duplicates,return=representation",
                    )
                    or []
                )
                inserted = len(inserted_rows) > 0
                active_d = inserted_rows[0] if inserted else None
                if not active_d:
                    latest_active = (
                        _sb_request(
                            "GET",
                            "live_signals",
                            params={
                                "select": "*",
                                "symbol": f"eq.{symbol}",
                                "timeframe": f"eq.{timeframe}",
                                "status": "eq.ACTIVE",
                                "order": "id.desc",
                                "limit": "1",
                            },
                        )
                        or []
                    )
                    active_d = latest_active[0] if latest_active else None

                if active_d:
                    active_d["floating_pnl"] = 0.0
                    if inserted:
                        events_to_notify.append(("NEW_SIGNAL", active_d))
                    res_payload = {
                        "locked": True,
                        "newly_opened": inserted,
                        "reason": (
                            f"New AI-Approved {trading_style} {active_d['direction']} position #{active_d['id']} "
                            f"opened @ {active_d['entry_price']:.2f} (Supabase). Single-position lock engaged until SL/TP."
                        ),
                        "active_trade": active_d,
                    }
                else:
                    res_payload = {
                        "locked": False,
                        "reason": "No active position open. Scanning for AI-approved entry...",
                        "active_trade": None,
                    }
            else:
                res_payload = {
                    "locked": False,
                    "reason": (
                        f"0 Active Positions ({trading_style}). AI Agent Gate status: {ai_verdict} — "
                        f"Waiting for confirmed setup before opening position."
                    ),
                    "active_trade": None,
                }

            if on_event_callback and events_to_notify:
                for ev_type, trade_obj in events_to_notify:
                    try:
                        on_event_callback(ev_type, trade_obj, sig_data)
                    except Exception:
                        pass
            return res_payload
        except Exception:
            pass

    # Fallback to Local SQLite if Supabase is offline
    with get_conn() as conn:
        active_rows = conn.execute(
            "SELECT * FROM live_signals WHERE symbol = ? AND timeframe = ? AND status = 'ACTIVE' ORDER BY id ASC",
            (symbol, timeframe),
        ).fetchall()

        if len(active_rows) > 1:
            for old_row in active_rows[:-1]:
                conn.execute(
                    "UPDATE live_signals SET status='SUPERSEDED', outcome_time=? WHERE id=?",
                    (now_str, old_row["id"]),
                )
            active_rows = [active_rows[-1]]

        still_active = None
        if active_rows and candles:
            row = active_rows[0]
            d = row["direction"]
            entry = row["entry_price"]
            sl = row["sl_price"]
            tp1 = row["tp1_price"]
            tp2 = row["tp2_price"]

            closed_status = None
            outcome_p = None
            outcome_t = None
            pnl = 0.0

            for c in candles[-5:]:
                if c["time"] <= row["candle_time"]:
                    continue
                ch = c["high"]
                cl = c["low"]
                ct = c.get("time_local") or c["time"]
                if d == "BUY":
                    if cl <= sl:
                        closed_status, outcome_p, outcome_t, pnl = "HIT_SL", sl, ct, round(sl - entry, 2)
                        break
                    elif ch >= tp2:
                        closed_status, outcome_p, outcome_t, pnl = "HIT_TP2", tp2, ct, round(tp2 - entry, 2)
                        break
                    elif ch >= tp1:
                        closed_status, outcome_p, outcome_t, pnl = "HIT_TP1", tp1, ct, round(tp1 - entry, 2)
                        break
                else:
                    if ch >= sl:
                        closed_status, outcome_p, outcome_t, pnl = "HIT_SL", sl, ct, round(entry - sl, 2)
                        break
                    elif cl <= tp2:
                        closed_status, outcome_p, outcome_t, pnl = "HIT_TP2", tp2, ct, round(entry - tp2, 2)
                        break
                    elif cl <= tp1:
                        closed_status, outcome_p, outcome_t, pnl = "HIT_TP1", tp1, ct, round(entry - tp1, 2)
                        break

            if closed_status:
                conn.execute(
                    "UPDATE live_signals SET status=?, outcome_price=?, outcome_time=?, pnl_pts=? WHERE id=?",
                    (closed_status, outcome_p, outcome_t, pnl, row["id"]),
                )
                conn.commit()
                closed_trade = dict(row)
                closed_trade["status"] = closed_status
                closed_trade["outcome_price"] = outcome_p
                closed_trade["outcome_time"] = outcome_t
                closed_trade["pnl_pts"] = pnl
                events_to_notify.append(("POSITION_CLOSED", closed_trade))
            else:
                still_active = dict(row)

        if still_active:
            d = still_active["direction"]
            entry = still_active["entry_price"]
            floating = round((current_price - entry) if d == "BUY" else (entry - current_price), 2)
            still_active["floating_pnl"] = floating
            res_payload = {
                "locked": True,
                "reason": (
                    f"Position #{still_active['id']} ({still_active.get('trading_style', 'SWING')} · {d} @ {entry:.2f}) "
                    f"is currently ACTIVE. Waiting for SL ({still_active['sl_price']:.2f}) or TP1 ({still_active['tp1_price']:.2f}) "
                    f"before scanning for next setup."
                ),
                "active_trade": still_active,
            }
        elif sig_data["direction"] in ("BUY", "SELL"):
            cur = conn.cursor()
            cur.execute(
                """
                INSERT OR IGNORE INTO live_signals (
                    recorded_at, symbol, timeframe, trading_style, candle_time, direction, signal,
                    confidence, entry_price, sl_price, tp1_price, tp2_price, status, rationale,
                    ai_verdict, ai_summary
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?)
                """,
                (
                    now_str,
                    symbol,
                    timeframe,
                    trading_style,
                    sig_data["last_candle_time"],
                    sig_data["direction"],
                    sig_data["signal"],
                    sig_data["confidence"],
                    sig_data["entry"],
                    sig_data["stop_loss"],
                    sig_data["take_profit_1"],
                    sig_data["take_profit_2"],
                    sig_data["rationale"],
                    ai_verdict,
                    ai_summary,
                ),
            )
            inserted = cur.rowcount > 0
            conn.commit()
            new_row = conn.execute(
                "SELECT * FROM live_signals WHERE symbol=? AND timeframe=? AND status='ACTIVE' ORDER BY id DESC LIMIT 1",
                (symbol, timeframe),
            ).fetchone()
            if new_row:
                active_d = dict(new_row)
                active_d["floating_pnl"] = 0.0
                if inserted:
                    events_to_notify.append(("NEW_SIGNAL", active_d))
                res_payload = {
                    "locked": True,
                    "newly_opened": inserted,
                    "reason": (
                        f"New AI-Approved {trading_style} {active_d['direction']} position #{active_d['id']} "
                        f"opened @ {active_d['entry_price']:.2f}. Single-position lock engaged until SL/TP."
                    ),
                    "active_trade": active_d,
                }
            else:
                res_payload = {
                    "locked": False,
                    "reason": "No active position open. Scanning for AI-approved entry...",
                    "active_trade": None,
                }
        else:
            res_payload = {
                "locked": False,
                "reason": (
                    f"0 Active Positions ({trading_style}). AI Agent Gate status: {ai_verdict} — "
                    f"Waiting for confirmed setup before opening position."
                ),
                "active_trade": None,
            }

    if on_event_callback and events_to_notify:
        for ev_type, trade_obj in events_to_notify:
            try:
                on_event_callback(ev_type, trade_obj, sig_data)
            except Exception:
                pass

    return res_payload


def force_close_active_signals(symbol=None, timeframe=None):
    """Allows the user to manually close an active paper position from the UI so the scanner can look for a new entry."""
    init_db()
    now_str = datetime.now(TZ_UTC7).strftime("%Y-%m-%d %H:%M:%S UTC+7")
    if USE_SUPABASE:
        try:
            params = {"status": "eq.ACTIVE"}
            if symbol and timeframe:
                params["symbol"] = f"eq.{symbol}"
                params["timeframe"] = f"eq.{timeframe}"
            _sb_request(
                "PATCH",
                "live_signals",
                params=params,
                body={"status": "MANUAL_CLOSE", "outcome_time": now_str},
                prefer="return=minimal",
            )
        except Exception:
            pass
    with get_conn() as conn:
        if symbol and timeframe:
            conn.execute(
                "UPDATE live_signals SET status='MANUAL_CLOSE', outcome_time=? WHERE symbol=? AND timeframe=? AND status='ACTIVE'",
                (now_str, symbol, timeframe),
            )
        else:
            conn.execute(
                "UPDATE live_signals SET status='MANUAL_CLOSE', outcome_time=? WHERE status='ACTIVE'",
                (now_str,),
            )
        conn.commit()


def get_live_signals(limit=60):
    init_db()
    if USE_SUPABASE:
        try:
            rows = _sb_request(
                "GET",
                "live_signals",
                params={
                    "select": "*",
                    "status": "neq.SUPERSEDED",
                    "order": "id.desc",
                    "limit": str(limit),
                },
            )
            if rows is not None:
                return rows
        except Exception:
            pass
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM live_signals WHERE status != 'SUPERSEDED' ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
