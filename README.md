# XAU/USD Quantitative AI Intelligence Terminal (`xauusd-quant-intelligence`)

An institutional-grade **XAU/USD (Spot Gold)** quantitative signal engine, multi-timeframe analytics terminal, and autonomous Telegram execution hub powered by a **3-Agent AI Committee (`gemini-4-argon` architecture)**, live **TradingView WebSocket feeds**, and **Supabase PostgreSQL**.

---

## Live Production Architecture (3-Tier Cloud)

| Tier | Platform | Directory | Live URL |
| :--- | :--- | :--- | :--- |
| **1. Frontend Web Terminal** | **Vercel (Global Edge CDN)** | [`/frontend`](./frontend) | **https://quant-intelligence.vercel.app** |
| **2. Backend API & 24/7 AI Worker** | **Railway (`python:3.12-slim`)** | [`/backend`](./backend) | **https://gold-signal-api-production.up.railway.app** |
| **3. Cloud Database** | **Supabase PostgreSQL (`ap-southeast-1`)** | Managed (`RLS` enabled) | **https://cpotlpgymbgfqhedbmrb.supabase.co** |

---

## Repository Structure

```text
xauusd-quant-intelligence/
├── frontend/                 # Deployed to Vercel (Root Directory: frontend)
│   ├── index.html            # Institutional Terminal UI
│   ├── config.js             # Connects to Railway Backend API (API_BASE)
│   ├── app.js                # Interactive Charts, AI Committee, MTF & Telegram Hub
│   ├── styles.css            # Institutional Dark-Gold Stylesheet
│   └── vercel.json           # Vercel Edge CDN routing & headers
│
├── backend/                  # Deployed to Railway (Root Directory: backend)
│   ├── server.py             # REST API (/api/*) + 24/7 Telegram & TradingView Worker
│   ├── analyze_gold_5m.py    # Multi-Style Quant Engine + 3-Agent AI Committee
│   ├── tradingview_mcp.py    # Live TradingView WebSocket Collector
│   ├── db.py                 # Supabase PostgreSQL Client + Local SQLite Fallback
│   ├── Dockerfile            # Production Container Definition
│   └── requirements.txt      # Python Dependencies
│
└── README.md
```

---

## Deployment Configuration

### 1. Frontend on Vercel (`https://quant-intelligence.vercel.app`)
- **Framework Preset**: `Other` (Static)
- **Root Directory**: `frontend`
- **Build Command**: *(Leave empty — static files)*
- **Output Directory**: `.`

### 2. Backend on Railway (`https://gold-signal-api-production.up.railway.app`)
- **Root Directory**: `/backend`
- **Start Command**: `python3 server.py`
- **Healthcheck Path**: `/api/health`
- **Environment Variables**: `HOST=0.0.0.0`, `PORT=8765`, `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_BOT_SECRET`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_GROUP_ID=-5523180993`, `USE_SUPABASE=1`.
