#!/usr/bin/env python3
"""
TradingView + Fundamental News + SQLite Backtest MCP Server (Stdio JSON-RPC 2.0).
"""

import json
import sys
import traceback

from analyze_gold_5m import (
    analyze_timeframe,
    fetch_fundamental_analysis,
    fetch_live_tv_tick,
    run_and_store_backtest,
)
from db import (
    get_backtest_run_details,
    get_backtest_runs,
    get_live_signals,
    init_db,
)

TOOLS = [
    {
        "name": "tradingview_get_live_quote",
        "description": "Fetch real-time zero-delay price, daily high/low, DXY correlation, and TradingView technical recommendation ratings (1m, 5m, 15m, 1h) for Spot Gold (OANDA:XAUUSD, FX:XAUUSD, FOREXCOM:XAUUSD).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "default": "OANDA:XAUUSD",
                }
            },
        },
    },
    {
        "name": "tradingview_get_fundamentals",
        "description": "Fetch live Fundamental & Macro Intelligence for Gold: US Dollar Index (TVC:DXY) correlation, Reuters/Dow Jones/TradingView Gold News headlines, NLP sentiment score (-100 to +100), and High-Impact Economic Event alerts (CPI, NFP, FOMC).",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "tradingview_analyze_timeframe",
        "description": "Pull live TradingView OHLCV candles via WebSocket, run the Pro Multi-Confirmation Strategy Engine + Fundamental News check, enforce the Single-Position Lock in SQLite (gold_quant.db), and return BUY, SELL, or WAIT (when no confirmed setup is present).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "default": "OANDA:XAUUSD",
                },
                "interval": {
                    "type": "string",
                    "enum": ["1m", "5m", "15m", "1h", "4h", "1d"],
                    "default": "1h",
                },
                "trading_style": {
                    "type": "string",
                    "enum": ["SWING", "INTRADAY", "SCALPING", "POSITION"],
                    "default": "SWING",
                },
            },
        },
    },
    {
        "name": "tradingview_run_backtest",
        "description": "Run a historical strategy backtest (with Single-Position Lock + Auto Break-Even @ TP1) across intraday or deep durations (450_BARS, 7_DAYS, 30_DAYS, 90_DAYS, 1_YEAR) and persist to SQLite (gold_quant.db).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "default": "OANDA:XAUUSD"},
                "interval": {
                    "type": "string",
                    "enum": ["1m", "5m", "15m", "1h", "4h", "1d"],
                    "default": "1h",
                },
                "trading_style": {
                    "type": "string",
                    "enum": ["SWING", "INTRADAY", "SCALPING", "POSITION"],
                    "default": "SWING",
                },
                "strategy_mode": {
                    "type": "string",
                    "enum": ["PRO_CONFIRMED", "TREND_ONLY", "MEAN_REVERSION", "HIGH_CONFIDENCE"],
                    "default": "PRO_CONFIRMED",
                },
                "duration_preset": {
                    "type": "string",
                    "enum": ["450_BARS", "1500_BARS", "7_DAYS", "30_DAYS", "90_DAYS", "1_YEAR"],
                    "default": "450_BARS",
                },
                "sl_mult": {"type": "number", "default": 1.5},
                "tp1_mult": {"type": "number", "default": 2.5},
                "tp2_mult": {"type": "number", "default": 4.0},
            },
        },
    },
    {
        "name": "tradingview_query_backtest_db",
        "description": "Query saved backtest runs, specific backtest trade ledgers, or forward-tested live signals from the SQLite database (gold_quant.db).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query_type": {
                    "type": "string",
                    "enum": ["runs_list", "run_detail", "live_signals"],
                    "default": "runs_list",
                },
                "run_id": {"type": "integer"},
            },
        },
    },
]


def handle_call_tool(name, args):
    args = args or {}
    if name == "tradingview_get_live_quote":
        return fetch_live_tv_tick(symbol=args.get("symbol", "OANDA:XAUUSD"))

    if name == "tradingview_get_fundamentals":
        return fetch_fundamental_analysis(force=True)

    if name == "tradingview_analyze_timeframe":
        return analyze_timeframe(
            symbol=args.get("symbol", "OANDA:XAUUSD"),
            interval=args.get("interval", "1h"),
            trading_style=args.get("trading_style", "SWING"),
            include_series=False,
        )

    if name == "tradingview_run_backtest":
        return run_and_store_backtest(
            symbol=args.get("symbol", "OANDA:XAUUSD"),
            interval=args.get("interval", "1h"),
            trading_style=args.get("trading_style", "SWING"),
            strategy_mode=args.get("strategy_mode", "PRO_CONFIRMED"),
            duration_preset=args.get("duration_preset", "450_BARS"),
            sl_mult=float(args.get("sl_mult", 1.5)),
            tp1_mult=float(args.get("tp1_mult", 2.5)),
            tp2_mult=float(args.get("tp2_mult", 4.0)),
        )

    if name == "tradingview_query_backtest_db":
        qtype = args.get("query_type", "runs_list")
        if qtype == "live_signals":
            return {"live_signals": get_live_signals(limit=50)}
        if qtype == "run_detail":
            return {"detail": get_backtest_run_details(run_id=args.get("run_id"))}
        return {"runs": get_backtest_runs(limit=30)}

    raise ValueError(f"Unknown tool: {name}")


def send_response(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def main():
    init_db()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue

        method = req.get("method")
        req_id = req.get("id")

        if method == "initialize":
            params = req.get("params") or {}
            client_proto = params.get("protocolVersion", "2024-11-05")
            send_response(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": client_proto,
                        "capabilities": {"tools": {}},
                        "serverInfo": {
                            "name": "tradingview-gold",
                            "version": "2.0.0",
                        },
                    },
                }
            )
        elif method == "notifications/initialized":
            continue
        elif method == "ping":
            send_response({"jsonrpc": "2.0", "id": req_id, "result": {}})
        elif method == "tools/list":
            send_response({"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            params = req.get("params") or {}
            t_name = params.get("name")
            t_args = params.get("arguments") or {}
            try:
                res_obj = handle_call_tool(t_name, t_args)
                send_response(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [{"type": "text", "text": json.dumps(res_obj, indent=2)}],
                            "isError": False,
                        },
                    }
                )
            except Exception as exc:
                send_response(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [
                                {"type": "text", "text": f"Error: {exc}\n{traceback.format_exc()}"}
                            ],
                            "isError": True,
                        },
                    }
                )
        elif req_id is not None:
            send_response(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }
            )


if __name__ == "__main__":
    main()
