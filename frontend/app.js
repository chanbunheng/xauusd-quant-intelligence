// ============================================================================
// AurumQuant AI — Institutional XAU/USD Trading & Intelligence Platform (Nuxt 4)
// Frontend Controller: Preserves 100% of Live Railway + Supabase + Telegram APIs
// while powering the modernized Application Shell, Bento KPIs, 4-Region Terminal,
// AI Quant Copilot, Strategy Lab, Command Palette (⌘K), and Theme Switcher.
// ============================================================================

const API_BASE =
  typeof window !== "undefined" && typeof window.API_BASE === "string"
    ? window.API_BASE
    : "https://gold-signal-api-production.up.railway.app";

let currentSymbol = "OANDA:XAUUSD";
let currentStyle = "SWING";
let currentTf = "1h";
let currentData = null;
let currentMtfData = null;
let selectedRunDetail = null;
let lastTickPrice = null;
let latestTickBrokers = {};
let latestTgSubscribersCount = 1;

let showBB = true;
let showSignalLines = true;
let oscMode = "RSI";
let hoverIdx = null;

const STYLE_DEFAULTS = {
  SWING:    { tf: "1h",  sl: 1.5, tp1: 2.5, tp2: 4.0, label: "Swing Trade (Pro Default)" },
  INTRADAY: { tf: "15m", sl: 1.2, tp1: 1.8, tp2: 3.0, label: "Intraday Session" },
  SCALPING: { tf: "1m",  sl: 1.0, tp1: 1.5, tp2: 2.0, label: "High-Speed Scalping" },
  POSITION: { tf: "4h",  sl: 1.8, tp1: 3.0, tp2: 5.0, label: "Macro Position" }
};

const DURATION_BARS_MAP = {
  "300":  { preset: "300_BARS",  bars: 300 },
  "7d":   { preset: "7_DAYS",    bars: 450 },
  "30d":  { preset: "30_DAYS",   bars: 720 },
  "90d":  { preset: "90_DAYS",   bars: 1200 },
  "1y":   { preset: "1_YEAR",    bars: 2000 }
};

const STRATEGY_MODE_MAP = {
  ALL:                      "PRO_CONFIRMED",
  SWING_GOLDEN_POCKET:      "PRO_CONFIRMED",
  PRO_TREND_PULLBACK:       "TREND_ONLY",
  LIQUIDITY_SWEEP_REVERSAL: "MEAN_REVERSION",
  MOMENTUM_BREAKOUT:        "HIGH_CONFIDENCE"
};

function el(id) {
  return document.getElementById(id);
}

function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// Toast Notification Helper
function showToast(msg) {
  let t = el("toast");
  if (!t) {
    t = document.createElement("div");
    t.id = "toast";
    t.style.cssText =
      "position:fixed;bottom:22px;right:22px;z-index:9999;background:rgba(17,24,39,0.96);color:#f8fafc;border:1px solid #38bdf8;border-radius:10px;padding:10px 16px;font-size:12.5px;font-weight:700;box-shadow:0 12px 30px rgba(0,0,0,0.55);transition:opacity 0.25s;";
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.style.display = "block";
  t.style.opacity = "1";
  clearTimeout(window.__toastTimer);
  window.__toastTimer = setTimeout(() => {
    t.style.opacity = "0";
    setTimeout(() => {
      t.style.display = "none";
    }, 250);
  }, 3200);
}

// ============================================================================
// 1. CLOCKS, COUNTDOWN & MARKET KILLZONE SESSION TRACKER
// ============================================================================
function updateClocksAndCountdown() {
  const now = new Date();
  const utcMs = now.getTime() + now.getTimezoneOffset() * 60000;
  const utc7 = new Date(utcMs + 7 * 3600000);
  const hh = String(utc7.getHours()).padStart(2, "0");
  const mm = String(utc7.getMinutes()).padStart(2, "0");
  const ss = String(utc7.getSeconds()).padStart(2, "0");

  const headerTimeEl = el("headerTime");
  if (headerTimeEl) headerTimeEl.textContent = `${hh}:${mm}:${ss} UTC+7`;

  const tfSecMap = { "1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400 };
  const periodSec = tfSecMap[currentTf] || 3600;
  const nowSec = Math.floor(now.getTime() / 1000);
  const rem = periodSec - (nowSec % periodSec);
  const rHr = Math.floor(rem / 3600);
  const rMin = String(Math.floor((rem % 3600) / 60)).padStart(2, "0");
  const rSec = String(rem % 60).padStart(2, "0");

  const countdownEl = el("countdownTimer");
  if (countdownEl) {
    countdownEl.textContent = rHr > 0 ? `${rHr}h ${rMin}m ${rSec}s` : `${rMin}:${rSec}`;
  }

  const utcH = now.getUTCHours();
  const asiaOpen = utcH >= 0 && utcH < 9;
  const londonOpen = utcH >= 7 && utcH < 16;
  const nyOpen = utcH >= 12 && utcH < 21;

  if (el("sessAsia")) el("sessAsia").classList.toggle("active", asiaOpen);
  if (el("sessLondon")) el("sessLondon").classList.toggle("active", londonOpen);
  if (el("sessNY")) el("sessNY").classList.toggle("active", nyOpen);

  const kzEl = el("killzoneText");
  if (kzEl) {
    if (londonOpen && nyOpen) {
      kzEl.textContent = "🔥 LONDON + NY OVERLAP (Peak Gold Liquidity)";
      kzEl.style.color = "var(--buy)";
    } else if (londonOpen) {
      kzEl.textContent = "⚡ LONDON KILLZONE ACTIVE";
      kzEl.style.color = "var(--gold-bright)";
    } else if (nyOpen) {
      kzEl.textContent = "⚡ NEW YORK SESSION ACTIVE";
      kzEl.style.color = "var(--gold-bright)";
    } else {
      kzEl.textContent = "🌙 ASIAN CONSOLIDATION SESSION";
      kzEl.style.color = "var(--blue)";
    }
  }
}

// ============================================================================
// 2. LIVE 1.5s/2s TICK STREAMING & MULTI-BROKER BAR
// ============================================================================
async function pollLiveTick() {
  try {
    const res = await fetch(`${API_BASE}/api/tick?symbol=${encodeURIComponent(currentSymbol)}`);
    const tick = await res.json();
    if (!tick || !tick.active) return;

    const price = tick.active.price;
    const priceEl = el("headerPrice");
    const boxEl = el("headerPriceBox");
    if (priceEl) priceEl.textContent = `$${price.toFixed(2)}`;
    if (el("headerBrokerLabel")) {
      el("headerBrokerLabel").textContent = `${currentSymbol} (LIVE FEED)`;
    }

    if (lastTickPrice !== null && price !== lastTickPrice && boxEl) {
      boxEl.classList.remove("flash-up", "flash-down");
      void boxEl.offsetWidth;
      boxEl.classList.add(price > lastTickPrice ? "flash-up" : "flash-down");
      setTimeout(() => boxEl.classList.remove("flash-up", "flash-down"), 450);
    }
    lastTickPrice = price;

    const chg = tick.active.change_abs || 0;
    const chgPct = tick.active.change_pct || 0;
    const chgEl = el("headerChange");
    if (chgEl) {
      chgEl.textContent = `${chg >= 0 ? "+" : ""}${chg.toFixed(2)} (${chg >= 0 ? "+" : ""}${chgPct.toFixed(2)}%)`;
      chgEl.style.color = chg >= 0 ? "var(--buy)" : "var(--sell)";
    }

    if (tick.brokers) {
      latestTickBrokers = tick.brokers;
      renderBrokerPills(tick.brokers);
      renderTerminalWatchlist();
    }

    // Update live candle & floating P&L
    if (currentData) {
      currentData.current_price = price;
      if (currentData.series && currentData.series.candles && currentData.series.candles.length) {
        const lastC = currentData.series.candles[currentData.series.candles.length - 1];
        lastC.close = price;
        if (price > lastC.high) lastC.high = price;
        if (price < lastC.low) lastC.low = price;
        drawCharts();
      }
      updateBentoKpis();
    }
  } catch (e) {
    // Silent retry on next tick
  }
}

function renderBrokerPills(brokers) {
  const wrap = el("brokerPills");
  if (!wrap) return;
  const items = [];
  const order = ["OANDA:XAUUSD", "FX:XAUUSD", "FOREXCOM:XAUUSD", "TVC:DXY"];
  order.forEach((sym) => {
    const b = brokers[sym];
    if (!b) return;
    const isUp = (b.change_pct || 0) >= 0;
    const col = isUp ? "var(--buy)" : "var(--sell)";
    const fmtPrice = sym === "TVC:DXY" ? b.price.toFixed(3) : `$${b.price.toFixed(2)}`;
    items.push(`
      <span class="broker-pill">
        <span style="color:var(--text-2);">${escapeHtml(sym)}:</span>
        <strong class="tabular" style="color:var(--text-0);">${fmtPrice}</strong>
        <span class="tabular" style="color:${col};font-weight:700;">${isUp ? "+" : ""}${(b.change_pct || 0).toFixed(2)}%</span>
      </span>
    `);
  });
  if (items.length) wrap.innerHTML = items.join("");
}

// ============================================================================
// 3. FULL DASHBOARD SYNC (ANALYZE, MTF, BACKTESTS, LIVE SIGNALS, TELEGRAM)
// ============================================================================
async function fetchFullDashboard() {
  try {
    const [analyzeRes, mtfRes, runsRes, liveSigRes, tgRes] = await Promise.all([
      fetch(`${API_BASE}/api/analyze?symbol=${encodeURIComponent(currentSymbol)}&interval=${currentTf}&style=${currentStyle}`),
      fetch(`${API_BASE}/api/mtf?symbol=${encodeURIComponent(currentSymbol)}&style=${currentStyle}`),
      fetch(`${API_BASE}/api/backtests`),
      fetch(`${API_BASE}/api/live_signals`),
      fetch(`${API_BASE}/api/telegram/status`)
    ]);

    const data = await analyzeRes.json();
    const mtfData = await mtfRes.json();
    const runsData = await runsRes.json();
    const liveSigData = await liveSigRes.json();
    const tgData = await tgRes.json();

    if (data.error) throw new Error(data.error);
    currentData = data;
    currentMtfData = mtfData;

    renderMainSignal(data);
    renderAiAgentLayer(data.ai_agent);
    renderTelegramStatus(tgData);
    renderFundamentals(data.fundamentals);
    renderMtf(mtfData.mtf || {}, mtfData.mtf_order || ["15m", "1h", "4h", "1d"]);
    updatePositionSizer();
    renderTerminalWatchlist();
    drawCharts();

    if (data.backtest && !selectedRunDetail) {
      selectedRunDetail = data.backtest;
    }
    renderBacktestRunsList(runsData.runs || []);
    if (selectedRunDetail) {
      renderSelectedBacktest(selectedRunDetail);
    } else if (data.backtest) {
      renderSelectedBacktest(data.backtest);
    }
    renderLiveSignalsTable(liveSigData.signals || []);
    updateBentoKpis();
  } catch (err) {
    console.error("Dashboard sync error:", err);
  }
}

// ============================================================================
// 4. SECTION 1: 8-CARD BENTO PORTFOLIO & QUANT KPI STRIP
// ============================================================================
function updateBentoKpis() {
  const d = currentData;
  const bt = selectedRunDetail || (d && d.backtest) || null;

  // 1. Simulated Portfolio Equity ($100,000 base + 1 lot = 100 oz * net_pnl_pts)
  if (bt) {
    const netPts = bt.net_pnl_pts || 0;
    const simEquity = 100000 + netPts * 100;
    const retPct = ((simEquity - 100000) / 100000) * 100;
    if (el("kpiPortfolioEquity")) {
      el("kpiPortfolioEquity").textContent = `$${simEquity.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    }
    if (el("kpiPortfolioReturnPct")) {
      el("kpiPortfolioReturnPct").textContent = `${retPct >= 0 ? "+" : ""}${retPct.toFixed(2)}%`;
      el("kpiPortfolioReturnPct").style.color = retPct >= 0 ? "var(--buy)" : "var(--sell)";
    }

    // 2. Net Strategy P&L
    if (el("kpiTotalNetPnl")) {
      el("kpiTotalNetPnl").textContent = `${netPts >= 0 ? "+" : ""}${netPts.toFixed(2)} pts`;
      el("kpiTotalNetPnl").style.color = netPts >= 0 ? "var(--buy)" : "var(--sell)";
    }
    if (el("kpiTotalTradesSub")) {
      el("kpiTotalTradesSub").textContent = `${bt.total_trades || 0} trades (${bt.timeframe || currentTf})`;
    }
    if (el("kpiProfitFactorBadge")) {
      el("kpiProfitFactorBadge").textContent = `PF: ${bt.profit_factor || "--"}`;
    }

    // 4. Verified Win Rate
    if (el("kpiWinRate")) {
      el("kpiWinRate").textContent = `${bt.win_rate || 0}%`;
      el("kpiWinRate").style.color = (bt.win_rate || 0) >= 50 ? "var(--buy)" : "var(--gold-bright)";
    }
    if (el("kpiWinLossBreakdown")) {
      el("kpiWinLossBreakdown").textContent = `${bt.wins || 0}W / ${bt.losses || 0}L`;
    }
    if (el("kpiExpectancySub")) {
      const exp = bt.expectancy_pts || 0;
      el("kpiExpectancySub").textContent = `Exp: ${exp >= 0 ? "+" : ""}${exp.toFixed(2)} pts`;
    }

    // 8. Max Drawdown
    if (el("kpiMaxDrawdown")) {
      el("kpiMaxDrawdown").textContent = `-${(bt.max_drawdown_pts || 0).toFixed(2)} pts`;
    }
  }

  // 3. Active Lock Floating P&L
  if (d) {
    const pl = d.position_lock || {};
    if (pl.locked && pl.active_trade) {
      const at = pl.active_trade;
      const fp = d.current_price
        ? at.direction === "BUY"
          ? d.current_price - at.entry_price
          : at.entry_price - d.current_price
        : at.floating_pnl || 0;
      if (el("kpiUnrealizedPnl")) {
        el("kpiUnrealizedPnl").textContent = `${fp >= 0 ? "+" : ""}${fp.toFixed(2)} pts`;
        el("kpiUnrealizedPnl").style.color = fp >= 0 ? "var(--buy)" : "var(--sell)";
      }
      if (el("kpiActivePosSub")) {
        el("kpiActivePosSub").textContent = `#${at.id} ${at.direction} @ ${at.entry_price.toFixed(2)}`;
      }
      if (el("kpiActivePosBadge")) {
        el("kpiActivePosBadge").textContent = "LOCKED";
        el("kpiActivePosBadge").style.color = "var(--gold-bright)";
      }
    } else {
      if (el("kpiUnrealizedPnl")) {
        el("kpiUnrealizedPnl").textContent = "0.00 pts";
        el("kpiUnrealizedPnl").style.color = "var(--text-0)";
      }
      if (el("kpiActivePosSub")) {
        el("kpiActivePosSub").textContent = `0 Open on ${d.timeframe}`;
      }
      if (el("kpiActivePosBadge")) {
        el("kpiActivePosBadge").textContent = "READY";
        el("kpiActivePosBadge").style.color = "var(--buy)";
      }
    }

    // 5. AI Committee Gate
    if (d.ai_agent) {
      if (el("kpiAiVerdictShort")) {
        el("kpiAiVerdictShort").textContent = d.ai_agent.verdict || "EVALUATED";
        el("kpiAiVerdictShort").style.color =
          d.ai_agent.verdict && d.ai_agent.verdict.includes("APPROVED")
            ? "var(--buy)"
            : d.ai_agent.verdict && d.ai_agent.verdict.includes("VETO")
            ? "var(--sell)"
            : "var(--ai-accent)";
      }
      if (el("kpiAiConfPct")) {
        el("kpiAiConfPct").textContent = `${d.ai_agent.adjusted_confidence || d.confidence}%`;
      }
    }

    // 6. US Dollar Index (DXY)
    if (d.fundamentals && d.fundamentals.dxy && d.fundamentals.dxy.price > 0) {
      const dxy = d.fundamentals.dxy;
      if (el("kpiDxyPrice")) {
        el("kpiDxyPrice").textContent = `${dxy.price.toFixed(3)} (${dxy.change_pct >= 0 ? "+" : ""}${dxy.change_pct.toFixed(2)}%)`;
      }
      if (el("kpiDxyGoldBias")) {
        el("kpiDxyGoldBias").textContent = `Gold: ${dxy.gold_impact}`;
        el("kpiDxyGoldBias").style.color =
          dxy.gold_impact === "BULLISH" ? "var(--buy)" : dxy.gold_impact === "BEARISH" ? "var(--sell)" : "var(--gold-bright)";
      }
    }

    if (el("kpiAtrStopSub")) {
      el("kpiAtrStopSub").textContent = `SL: ${d.sl_mult}x ATR ($${(d.indicators?.atr14 || 0).toFixed(2)})`;
    }
  }

  if (el("kpiTgSubPill")) {
    el("kpiTgSubPill").textContent = `${latestTgSubscribersCount} Chat(s)`;
  }
}

// ============================================================================
// 5. SECTION 2 & 3: AI AGENT LAYER, TELEGRAM HUB, MAIN SIGNAL & MTF MATRIX
// ============================================================================
function renderMainSignal(d) {
  if (el("headerPrice")) el("headerPrice").textContent = `$${d.current_price.toFixed(2)}`;
  if (el("activeTfLabel")) el("activeTfLabel").textContent = `${d.trading_style} · ${d.timeframe}`;
  if (el("activeStyleBadgeHeader") && d.style_info) {
    el("activeStyleBadgeHeader").textContent = `${d.style_info.badge} (${d.timeframe})`;
  }
  if (el("regimeBadge")) {
    const isBull = d.indicators.ema21 >= d.indicators.ema50;
    el("regimeBadge").textContent = isBull ? "BULLISH EMA STRUCTURE" : "BEARISH EMA STRUCTURE";
    el("regimeBadge").style.color = isBull ? "var(--buy)" : "var(--sell)";
  }

  // Single-Position Lock Banner
  const pl = d.position_lock || {};
  const lockBanner = el("lockBanner");
  const lockTitle = el("lockTitle");
  const lockReason = el("lockReason");
  const closeBtn = el("closePosBtn");

  if (pl.locked && pl.active_trade) {
    const at = pl.active_trade;
    if (lockBanner) lockBanner.className = "lock-banner locked";
    if (lockTitle) {
      lockTitle.textContent = "🔒 Single-Position Lock Engaged:";
      lockTitle.style.color = "var(--gold-bright)";
    }
    if (lockReason) {
      const fp = at.floating_pnl || 0;
      lockReason.innerHTML = `Active Trade <strong>#${at.id} (${at.trading_style || d.trading_style} · ${at.direction} @ $${at.entry_price.toFixed(2)})</strong> · SL: $${at.sl_price.toFixed(2)} · TP1: $${at.tp1_price.toFixed(2)} · Floating P&L: <strong style="color:${fp >= 0 ? 'var(--buy)' : 'var(--sell)'};">${fp >= 0 ? '+' : ''}$${fp.toFixed(2)}</strong>`;
    }
    if (closeBtn) closeBtn.style.display = "inline-flex";
  } else {
    if (lockBanner) lockBanner.className = "lock-banner";
    if (lockTitle) {
      lockTitle.textContent = "🛡️ Single-Position Scanner Ready:";
      lockTitle.style.color = "var(--blue)";
    }
    if (lockReason) {
      lockReason.textContent = `0 Open Positions on ${d.timeframe} (${d.trading_style}). Pre-Signal 3-Agent AI Gate must approve before locking a new setup.`;
    }
    if (closeBtn) closeBtn.style.display = "none";
  }

  // Signal Hero Badge
  const dir = d.direction === "BUY" ? "BUY" : d.direction === "SELL" ? "SELL" : "NEUTRAL";
  const sigBadge = el("signalBadge");
  if (sigBadge) sigBadge.className = `signal-badge ${dir}`;
  if (el("signalDir")) el("signalDir").textContent = d.direction;
  if (el("signalConf")) el("signalConf").textContent = `Confidence: ${d.confidence}%`;
  if (el("signalSubType")) el("signalSubType").textContent = d.signal;

  // Entry / SL / TP1 / TP2 Levels
  const activeTrade = pl.locked && pl.active_trade ? pl.active_trade : null;
  const dispEntry = activeTrade ? activeTrade.entry_price : d.entry;
  const dispSl = activeTrade ? activeTrade.sl_price : d.stop_loss;
  const dispTp1 = activeTrade ? activeTrade.tp1_price : d.take_profit_1;
  const dispTp2 = activeTrade ? activeTrade.tp2_price : d.take_profit_2;

  const riskPts = Math.abs(dispEntry - dispSl);
  const tp1Pts = Math.abs(dispTp1 - dispEntry);
  const tp2Pts = Math.abs(dispTp2 - dispEntry);
  const rr1 = riskPts > 0 ? (tp1Pts / riskPts).toFixed(2) : "--";
  const rr2 = riskPts > 0 ? (tp2Pts / riskPts).toFixed(2) : "--";

  if (el("lvlEntry")) el("lvlEntry").textContent = `$${dispEntry.toFixed(2)}`;
  if (el("lvlSpread")) el("lvlSpread").textContent = activeTrade ? `Locked #${activeTrade.id}` : `Live Spot Ref`;
  if (el("lvlSL")) el("lvlSL").textContent = `$${dispSl.toFixed(2)}`;
  if (el("lvlRisk")) el("lvlRisk").textContent = `Risk: ${riskPts.toFixed(2)} pts (${d.sl_mult}x ATR)`;
  if (el("lvlTP1")) el("lvlTP1").textContent = `$${dispTp1.toFixed(2)}`;
  if (el("lvlRR1")) el("lvlRR1").textContent = `R:R 1:${rr1} (SL→BE)`;
  if (el("lvlTP2")) el("lvlTP2").textContent = `$${dispTp2.toFixed(2)}`;
  if (el("lvlRR2")) el("lvlRR2").textContent = `R:R 1:${rr2} (Runner)`;

  if (el("rationaleBox")) el("rationaleBox").textContent = d.rationale;

  // Checklist Grid
  const cGrid = el("checklistGrid");
  if (cGrid) {
    cGrid.innerHTML = (d.checklist || [])
      .map(
        (item) => `
        <div class="check-item ${item.passed ? "pass" : "fail"}">
          <span style="color:${item.passed ? "var(--buy)" : "var(--text-2)"};font-weight:800;">${item.passed ? "✓" : "○"}</span>
          <div>
            <div style="font-weight:700;color:var(--text-0);">${escapeHtml(item.name)}</div>
            <div style="font-size:10px;color:var(--text-2);">${escapeHtml(item.detail)}</div>
          </div>
        </div>
      `
      )
      .join("");
  }

  // Structure Stat Cards below MTF Matrix
  if (d.pivots) {
    if (el("pivP")) el("pivP").textContent = `$${d.pivots.pivot.toFixed(2)}`;
    if (el("pivR1S1")) el("pivR1S1").textContent = `R1: $${d.pivots.r1.toFixed(1)} · S1: $${d.pivots.s1.toFixed(1)}`;
  }
  if (d.ai_agent && el("vwapVal")) {
    el("vwapVal").textContent = d.ai_agent.watch_zone || "--";
  }
  if (d.indicators) {
    if (el("bbWidthVal")) el("bbWidthVal").textContent = `RSI(14): ${d.indicators.rsi14.toFixed(1)}`;
    if (el("atrVal")) el("atrVal").textContent = `$${d.indicators.atr14.toFixed(2)}`;
    if (el("emaRibbonVal")) {
      el("emaRibbonVal").textContent = `EMA21: ${d.indicators.ema21.toFixed(1)} / EMA50: ${d.indicators.ema50.toFixed(1)}`;
    }
  }
}

function renderAiAgentLayer(ai) {
  if (!ai) return;
  if (el("aiModelUsedBadge")) el("aiModelUsedBadge").textContent = ai.engine;
  if (el("aiVerdictTitle")) {
    el("aiVerdictTitle").textContent = `${ai.verdict_badge} (${ai.adjusted_confidence}% Confidence)`;
  }
  if (el("fibGoldenBadge")) {
    el("fibGoldenBadge").textContent = `Fib Golden Pocket: ${ai.watch_zone}`;
  }
  if (el("aiExecSummary")) {
    el("aiExecSummary").textContent = ai.executive_summary;
  }

  const grid = el("aiCommitteeGrid");
  if (!grid) return;
  grid.innerHTML = (ai.agents || [])
    .map((ag) => {
      const col =
        ag.bias === "BULLISH" || ag.bias === "BUY"
          ? "var(--buy)"
          : ag.bias === "BEARISH" || ag.bias === "SELL"
          ? "var(--sell)"
          : "var(--gold-bright)";
      return `
        <div class="agent-box">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
            <strong style="font-size:12px;color:var(--text-0);">${escapeHtml(ag.name)}</strong>
            <span class="tabular" style="font-size:10px;font-weight:800;padding:2px 7px;border-radius:4px;background:var(--bg-1);color:${col};">
              ${escapeHtml(ag.bias)} (${ag.score}%)
            </span>
          </div>
          <div style="font-size:10px;color:var(--text-2);font-weight:600;margin-bottom:4px;">${escapeHtml(ag.role)}</div>
          <div style="font-size:11.5px;color:var(--text-1);line-height:1.4;">${escapeHtml(ag.note)}</div>
        </div>
      `;
    })
    .join("");
}

function renderTelegramStatus(tg) {
  if (!tg) return;
  const badge = el("tgBotStatusBadge");
  if (tg.bot && tg.bot.ok) {
    if (badge) {
      badge.textContent = `ONLINE · @${tg.bot.username}`;
      badge.style.background = "var(--buy-dim)";
      badge.style.color = "var(--buy)";
    }
    const link = el("tgBotLink");
    if (link) {
      link.href = tg.bot.bot_link || `https://t.me/${tg.bot.username}`;
      link.textContent = `@${tg.bot.username} (${tg.bot.first_name}) ↗`;
    }
  } else if (badge) {
    badge.textContent = "BOT OFFLINE / CHECK TOKEN";
    badge.style.background = "var(--sell-dim)";
    badge.style.color = "var(--sell)";
  }

  if (el("tgAutoNotifyChk")) {
    el("tgAutoNotifyChk").checked = Boolean(tg.auto_notify);
  }

  const subs = tg.subscribers || [];
  latestTgSubscribersCount = subs.length;
  if (el("tgSubCount")) el("tgSubCount").textContent = String(subs.length);
  const subBox = el("tgSubscribersList");
  if (subBox) {
    if (!subs.length) {
      subBox.innerHTML = `No chats subscribed yet. Open <a href="https://t.me/this_is_ai_signal_bot" target="_blank" style="color:var(--gold-bright);font-weight:700;">@this_is_ai_signal_bot</a> and send <code>/start</code>, or enter your Chat ID above.`;
    } else {
      subBox.innerHTML = subs
        .map(
          (s) => `
          <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:6px;padding:6px 0;border-bottom:1px solid rgba(36,48,71,0.5);min-width:0;">
            <div style="min-width:0;flex:1;overflow-wrap:anywhere;">
              <div style="font-weight:700;color:var(--buy);line-height:1.3;">● ${escapeHtml(s.first_name || "Trader")} ${
            s.username ? `<span style="color:var(--text-1);font-weight:500;">(@${escapeHtml(s.username)})</span>` : ""
          }</div>
              <div style="font-size:10px;color:var(--text-2);margin-top:2px;">ID: <code style="color:var(--text-0);">${escapeHtml(s.chat_id)}</code></div>
            </div>
            <span style="font-size:9.5px;text-transform:uppercase;background:var(--bg-1);border:1px solid var(--border);padding:1px 6px;border-radius:99px;color:var(--gold-bright);font-weight:700;flex-shrink:0;">${escapeHtml(
              s.chat_type || "chat"
            )}</span>
          </div>
        `
        )
        .join("");
    }
  }

  const logs = tg.logs || [];
  const logBox = el("tgLogsList");
  if (logBox) {
    if (!logs.length) {
      logBox.innerHTML = "No alerts sent yet. Click <strong>Broadcast Signal Now</strong> to test!";
    } else {
      logBox.innerHTML = logs
        .map((l) => {
          const cleanPreview = escapeHtml(l.message_preview || "")
            .replace(/\s+/g, " ")
            .trim();
          return `
            <div style="padding:6px 0;border-bottom:1px solid rgba(36,48,71,0.5);min-width:0;">
              <div style="display:flex;justify-content:space-between;align-items:center;gap:6px;margin-bottom:3px;flex-wrap:wrap;">
                <span style="color:${l.ok ? "var(--buy)" : "var(--sell)"};font-weight:800;font-size:10px;background:${
            l.ok ? "var(--buy-dim)" : "var(--sell-dim)"
          };padding:1px 6px;border-radius:4px;">${escapeHtml(l.event_type)}</span>
                <span class="tabular" style="color:var(--text-2);font-size:10px;">${escapeHtml(
                  (l.sent_at || "").slice(11, 19)
                )} · <code>${escapeHtml(l.chat_id)}</code></span>
              </div>
              <div style="color:var(--text-1);font-size:10.5px;line-height:1.35;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;word-break:break-word;overflow-wrap:anywhere;">${cleanPreview}</div>
            </div>
          `;
        })
        .join("");
    }
  }
}

function renderMtf(mtf, mtfOrder) {
  const tbody = el("mtfTableBody");
  if (!tbody) return;
  let bullCount = 0;
  let bearCount = 0;

  const rows = [];
  mtfOrder.forEach((tf) => {
    const item = mtf[tf];
    if (!item) return;
    const isBull = item.ema21 >= item.ema50;
    if (isBull) bullCount++;
    else bearCount++;

    const pillCls = item.direction === "BUY" ? "BUY" : item.direction === "SELL" ? "SELL" : "NEUTRAL";
    rows.push(`
      <tr style="cursor:pointer;" onclick="switchTimeframe('${tf}')">
        <td><strong style="color:var(--gold-bright);">${tf.toUpperCase()}</strong></td>
        <td><span class="pill ${pillCls}">${escapeHtml(item.direction)}</span></td>
        <td class="tabular" style="font-weight:700;">${item.confidence}%</td>
        <td style="color:${isBull ? "var(--buy)" : "var(--sell)"};font-weight:700;">
          ${isBull ? "▲ Bullish EMA" : "▼ Bearish EMA"}
        </td>
        <td class="tabular">${item.rsi14.toFixed(1)}</td>
        <td class="tabular">$${item.entry.toFixed(2)}</td>
        <td class="tabular" style="color:var(--sell);">$${item.stop_loss.toFixed(2)}</td>
        <td class="tabular" style="color:var(--buy);">$${item.take_profit_1.toFixed(2)}</td>
      </tr>
    `);
  });

  tbody.innerHTML = rows.join("");

  const badge = el("mtfAlignmentBadge");
  if (badge) {
    const total = mtfOrder.length || 1;
    if (bullCount === total) {
      badge.className = "pill BUY";
      badge.textContent = `STRONG BULLISH (${bullCount}/${total} TFs)`;
    } else if (bearCount === total) {
      badge.className = "pill SELL";
      badge.textContent = `STRONG BEARISH (${bearCount}/${total} TFs)`;
    } else if (bullCount > bearCount) {
      badge.className = "pill BUY";
      badge.textContent = `BULLISH BIAS (${bullCount}/${total} TFs)`;
    } else if (bearCount > bullCount) {
      badge.className = "pill SELL";
      badge.textContent = `BEARISH BIAS (${bearCount}/${total} TFs)`;
    } else {
      badge.className = "pill NEUTRAL";
      badge.textContent = `MIXED CONFLUENCE (${bullCount}B / ${bearCount}S)`;
    }
  }
}

// ============================================================================
// 6. SECTION 4: 4-REGION INSTITUTIONAL TRADING TERMINAL
//    (Left Watchlist | Center Candlestick & Osc | Right Paper Order Sizer)
// ============================================================================
function renderTerminalWatchlist() {
  const container = el("terminalWatchlistContainer");
  if (!container) return;
  const query = (el("watchlistSearchInput")?.value || "").trim().toUpperCase();

  const b = latestTickBrokers || {};
  const oanda = b["OANDA:XAUUSD"] || { price: currentData?.current_price || 4748.0, change_pct: 0.12 };
  const fx = b["FX:XAUUSD"] || { price: oanda.price, change_pct: oanda.change_pct };
  const forex = b["FOREXCOM:XAUUSD"] || { price: oanda.price, change_pct: oanda.change_pct };
  const dxy = b["TVC:DXY"] || {
    price: currentData?.fundamentals?.dxy?.price || 98.81,
    change_pct: currentData?.fundamentals?.dxy?.change_pct || 0.04
  };

  const watchlistItems = [
    { symbol: "OANDA:XAUUSD", name: "Gold Spot · OANDA", price: `$${oanda.price.toFixed(2)}`, chg: oanda.change_pct || 0, selectable: true, mode: "LIVE" },
    { symbol: "FX:XAUUSD", name: "Gold Spot · FXCM", price: `$${fx.price.toFixed(2)}`, chg: fx.change_pct || 0, selectable: true, mode: "LIVE" },
    { symbol: "FOREXCOM:XAUUSD", name: "Gold Spot · FOREX.com", price: `$${forex.price.toFixed(2)}`, chg: forex.change_pct || 0, selectable: true, mode: "LIVE" },
    { symbol: "TVC:DXY", name: "US Dollar Index (Macro)", price: dxy.price.toFixed(3), chg: dxy.change_pct || 0, selectable: false, mode: "LIVE" },
    { symbol: "XAG/USD", name: "Silver Spot (Gold Corr +0.89)", price: "$33.42", chg: 0.42, selectable: false, mode: "SIM" },
    { symbol: "US10Y", name: "US 10Y Treasury Yield", price: "4.285%", chg: -0.18, selectable: false, mode: "SIM" },
    { symbol: "BTC/USD", name: "Bitcoin Macro Liquidity", price: "$94,650", chg: 1.15, selectable: false, mode: "SIM" }
  ];

  const filtered = watchlistItems.filter(
    (item) => !query || item.symbol.toUpperCase().includes(query) || item.name.toUpperCase().includes(query)
  );

  container.innerHTML = filtered
    .map((item) => {
      const isSelected = item.symbol === currentSymbol;
      const isUp = item.chg >= 0;
      return `
        <div class="watchlist-item ${isSelected ? "active" : ""}" data-sym="${item.symbol}" data-selectable="${item.selectable}">
          <div>
            <div class="watchlist-sym" style="display:flex;align-items:center;gap:5px;">
              <span>${escapeHtml(item.symbol)}</span>
              <span style="font-size:8.5px;padding:1px 4px;border-radius:4px;background:${
                item.mode === "LIVE" ? "var(--buy-dim)" : "rgba(245,158,11,0.16)"
              };color:${item.mode === "LIVE" ? "var(--buy)" : "var(--gold-bright)"};font-weight:800;">${item.mode}</span>
            </div>
            <div style="font-size:10px;color:var(--text-2);">${escapeHtml(item.name)}</div>
          </div>
          <div style="text-align:right;">
            <div class="watchlist-price">${item.price}</div>
            <div class="tabular" style="font-size:10.5px;font-weight:700;color:${isUp ? "var(--buy)" : "var(--sell)"};">
              ${isUp ? "+" : ""}${item.chg.toFixed(2)}%
            </div>
          </div>
        </div>
      `;
    })
    .join("");

  container.querySelectorAll(".watchlist-item").forEach((row) => {
    row.addEventListener("click", () => {
      const sym = row.dataset.sym;
      if (row.dataset.selectable === "true") {
        currentSymbol = sym;
        if (el("symbolSelect")) el("symbolSelect").value = sym;
        selectedRunDetail = null;
        fetchFullDashboard();
        pollLiveTick();
        showToast(`Switched active terminal feed to ${sym}`);
      } else {
        showToast(`${sym} is displayed as a macro correlation reference.`);
      }
    });
  });
}

function updatePositionSizer() {
  if (!currentData) return;
  const account = parseFloat(el("riskAccountInput")?.value) || 10000;
  const riskPct = parseFloat(el("riskPctInput")?.value) || 1.0;

  const entry = currentData.entry || currentData.current_price || 4748;
  const sl = currentData.stop_loss || entry - 15;
  const stopDist = Math.max(Math.abs(entry - sl), 0.1);

  const dollarRisk = account * (riskPct / 100);
  const ounces = dollarRisk / stopDist;
  const lots = ounces / 100;

  if (el("ticketSymbolLbl")) el("ticketSymbolLbl").textContent = currentSymbol;
  if (el("ticketBiasLbl")) {
    el("ticketBiasLbl").textContent = `${currentData.direction} (${currentData.confidence}%)`;
    el("ticketBiasLbl").style.color =
      currentData.direction === "BUY"
        ? "var(--buy)"
        : currentData.direction === "SELL"
        ? "var(--sell)"
        : "var(--gold-bright)";
  }
  if (el("ticketStopDistLbl")) el("ticketStopDistLbl").textContent = `${stopDist.toFixed(2)} pts`;
  if (el("calcDollarRisk")) el("calcDollarRisk").textContent = `$${dollarRisk.toFixed(2)}`;
  if (el("calcOuncesSize")) el("calcOuncesSize").textContent = `${ounces.toFixed(2)} oz`;
  if (el("calcLotSize")) el("calcLotSize").textContent = `${lots.toFixed(2)} lots`;
}

// ============================================================================
// 7. CANDLESTICK, EMA RIBBON, BOLLINGER & OSCILLATOR CANVAS ENGINE
// ============================================================================
function drawCharts() {
  const priceCanvas = el("priceCanvas");
  const oscCanvas = el("oscCanvas");
  if (!priceCanvas || !oscCanvas || !currentData || !currentData.series) return;

  const s = currentData.series;
  const candles = s.candles || [];
  if (!candles.length) return;

  const isLight = document.documentElement.getAttribute("data-theme") === "light";
  const canvasBg = isLight ? "#f8fafc" : "#080b12";
  const gridColor = isLight ? "rgba(148, 163, 184, 0.28)" : "rgba(36, 48, 71, 0.5)";
  const textColor = isLight ? "#475569" : "#94a3b8";

  const dpr = window.devicePixelRatio || 1;
  const rect = priceCanvas.getBoundingClientRect();
  const width = rect.width || 860;
  const height = 370;
  priceCanvas.width = width * dpr;
  priceCanvas.height = height * dpr;
  const ctx = priceCanvas.getContext("2d");
  ctx.scale(dpr, dpr);

  ctx.fillStyle = canvasBg;
  ctx.fillRect(0, 0, width, height);

  const padLeft = 14;
  const padRight = 74;
  const padTop = 18;
  const padBottom = 24;
  const plotW = width - padLeft - padRight;
  const plotH = height - padTop - padBottom;

  let minP = Infinity;
  let maxP = -Infinity;
  candles.forEach((c, i) => {
    minP = Math.min(minP, c.low, s.ema50[i]);
    maxP = Math.max(maxP, c.high, s.ema50[i]);
    if (showBB) {
      minP = Math.min(minP, s.bb_lower[i]);
      maxP = Math.max(maxP, s.bb_upper[i]);
    }
  });
  if (showSignalLines) {
    minP = Math.min(minP, currentData.stop_loss, currentData.take_profit_1, currentData.take_profit_2);
    maxP = Math.max(maxP, currentData.stop_loss, currentData.take_profit_1, currentData.take_profit_2);
  }
  const rangeP = Math.max(maxP - minP, 1.0);
  minP -= rangeP * 0.06;
  maxP += rangeP * 0.06;

  const yOf = (val) => padTop + plotH * (1 - (val - minP) / (maxP - minP));
  const stepX = plotW / candles.length;

  ctx.strokeStyle = gridColor;
  ctx.lineWidth = 1;
  for (let g = 0; g <= 5; g++) {
    const pVal = minP + ((maxP - minP) * g) / 5;
    const y = yOf(pVal);
    ctx.beginPath();
    ctx.moveTo(padLeft, y);
    ctx.lineTo(width - padRight, y);
    ctx.stroke();

    ctx.fillStyle = textColor;
    ctx.font = "11px JetBrains Mono, monospace";
    ctx.fillText(pVal.toFixed(2), width - padRight + 6, y + 4);
  }

  if (showBB) {
    ctx.strokeStyle = "rgba(148, 163, 184, 0.35)";
    ctx.setLineDash([3, 3]);
    ["bb_upper", "bb_lower"].forEach((key) => {
      ctx.beginPath();
      s[key].forEach((val, idx) => {
        const x = padLeft + idx * stepX + stepX / 2;
        const y = yOf(val);
        if (idx === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
    });
    ctx.setLineDash([]);
  }

  const candleW = Math.max(2, stepX * 0.62);
  candles.forEach((c, idx) => {
    const xCenter = padLeft + idx * stepX + stepX / 2;
    const isBull = c.close >= c.open;
    const col = isBull ? "#00d4aa" : "#f43f5e";
    ctx.strokeStyle = col;
    ctx.fillStyle = col;

    ctx.beginPath();
    ctx.moveTo(xCenter, yOf(c.high));
    ctx.lineTo(xCenter, yOf(c.low));
    ctx.stroke();

    const yOpen = yOf(c.open);
    const yClose = yOf(c.close);
    const top = Math.min(yOpen, yClose);
    const boxH = Math.max(1.5, Math.abs(yClose - yOpen));
    ctx.fillRect(xCenter - candleW / 2, top, candleW, boxH);
  });

  const drawLine = (arr, color, widthPx = 1.6) => {
    ctx.strokeStyle = color;
    ctx.lineWidth = widthPx;
    ctx.beginPath();
    arr.forEach((val, idx) => {
      const x = padLeft + idx * stepX + stepX / 2;
      const y = yOf(val);
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  };
  drawLine(s.ema9, "#38bdf8", 1.5);
  drawLine(s.ema21, "#f5c451", 1.6);
  drawLine(s.ema50, "#a855f7", 1.6);

  if (showSignalLines) {
    const pl = currentData.position_lock || {};
    const at = pl.locked && pl.active_trade ? pl.active_trade : null;
    const levels = [
      { val: at ? at.entry_price : currentData.entry, col: "#f5c451", lbl: at ? `LOCKED ENTRY #${at.id}` : "REF ENTRY" },
      { val: at ? at.sl_price : currentData.stop_loss, col: "#f43f5e", lbl: "SL" },
      { val: at ? at.tp1_price : currentData.take_profit_1, col: "#00d4aa", lbl: "TP1 (BE)" },
      { val: at ? at.tp2_price : currentData.take_profit_2, col: "#38bdf8", lbl: "TP2" }
    ];
    levels.forEach((lv) => {
      const y = yOf(lv.val);
      ctx.strokeStyle = lv.col;
      ctx.lineWidth = 1.2;
      ctx.setLineDash([5, 4]);
      ctx.beginPath();
      ctx.moveTo(padLeft, y);
      ctx.lineTo(width - padRight, y);
      ctx.stroke();
      ctx.setLineDash([]);

      ctx.fillStyle = lv.col;
      ctx.font = "bold 10px Inter, sans-serif";
      ctx.fillText(`${lv.lbl} $${lv.val.toFixed(2)}`, padLeft + 6, y - 4);
    });
  }

  if (hoverIdx !== null && hoverIdx >= 0 && hoverIdx < candles.length) {
    const hx = padLeft + hoverIdx * stepX + stepX / 2;
    ctx.strokeStyle = "rgba(245, 196, 81, 0.55)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(hx, padTop);
    ctx.lineTo(hx, height - padBottom);
    ctx.stroke();
  }

  drawOscillator(width, dpr, stepX, padLeft, padRight, canvasBg, textColor);
}

function drawOscillator(width, dpr, stepX, padLeft, padRight, canvasBg, textColor) {
  const oscCanvas = el("oscCanvas");
  if (!oscCanvas || !currentData || !currentData.series) return;
  const s = currentData.series;
  const height = 115;
  oscCanvas.width = width * dpr;
  oscCanvas.height = height * dpr;
  const ctx = oscCanvas.getContext("2d");
  ctx.scale(dpr, dpr);

  ctx.fillStyle = canvasBg;
  ctx.fillRect(0, 0, width, height);

  const padTop = 16;
  const padBottom = 16;
  const plotH = height - padTop - padBottom;

  if (oscMode === "RSI") {
    const yOf = (v) => padTop + plotH * (1 - v / 100);
    [70, 50, 30].forEach((lv) => {
      const y = yOf(lv);
      ctx.strokeStyle = lv === 50 ? "rgba(148,163,184,0.25)" : "rgba(245,196,81,0.35)";
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(padLeft, y);
      ctx.lineTo(width - padRight, y);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = textColor;
      ctx.font = "10px monospace";
      ctx.fillText(String(lv), width - padRight + 6, y + 3);
    });

    ctx.strokeStyle = "#38bdf8";
    ctx.lineWidth = 1.6;
    ctx.beginPath();
    s.rsi14.forEach((v, idx) => {
      const x = padLeft + idx * stepX + stepX / 2;
      const y = yOf(v);
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    ctx.fillStyle = textColor;
    ctx.font = "bold 10px Inter, sans-serif";
    ctx.fillText(`RSI(14): ${s.rsi14[s.rsi14.length - 1].toFixed(1)}`, padLeft + 6, 12);
  } else {
    const allVals = [...s.macd, ...s.macd_signal, ...s.macd_hist];
    const maxAbs = Math.max(...allVals.map((v) => Math.abs(v)), 0.5) * 1.15;
    const yOf = (v) => padTop + plotH * (0.5 - v / (2 * maxAbs));
    const yZero = yOf(0);

    ctx.strokeStyle = "rgba(148,163,184,0.3)";
    ctx.beginPath();
    ctx.moveTo(padLeft, yZero);
    ctx.lineTo(width - padRight, yZero);
    ctx.stroke();

    const barW = Math.max(2, stepX * 0.55);
    s.macd_hist.forEach((v, idx) => {
      const x = padLeft + idx * stepX + stepX / 2;
      const y = yOf(v);
      ctx.fillStyle = v >= 0 ? "rgba(0, 212, 170, 0.55)" : "rgba(244, 63, 94, 0.55)";
      ctx.fillRect(x - barW / 2, Math.min(y, yZero), barW, Math.max(1, Math.abs(y - yZero)));
    });

    const drawM = (arr, col) => {
      ctx.strokeStyle = col;
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      arr.forEach((v, idx) => {
        const x = padLeft + idx * stepX + stepX / 2;
        const y = yOf(v);
        if (idx === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
    };
    drawM(s.macd, "#38bdf8");
    drawM(s.macd_signal, "#f5c451");

    ctx.fillStyle = textColor;
    ctx.font = "bold 10px Inter, sans-serif";
    ctx.fillText(`MACD(12,26,9) Hist: ${s.macd_hist[s.macd_hist.length - 1].toFixed(2)}`, padLeft + 6, 12);
  }
}

// ============================================================================
// 8. SECTION 6: FUNDAMENTALS, MACRO CORRELATIONS (DXY) & WIRE NEWS
// ============================================================================
function renderFundamentals(f) {
  if (!f) return;
  const biasEl = el("fundBiasVal");
  if (biasEl) {
    biasEl.textContent = `${f.bias} (${f.score >= 0 ? "+" : ""}${f.score})`;
    biasEl.style.color = f.bias === "BULLISH" ? "var(--buy)" : f.bias === "BEARISH" ? "var(--sell)" : "var(--gold-bright)";
  }
  if (el("fundScoreSub")) {
    el("fundScoreSub").textContent = `${f.bullish_headlines} Bullish vs ${f.bearish_headlines} Bearish Wire Headlines`;
  }

  if (f.dxy && f.dxy.price > 0) {
    if (el("fundDxyPrice")) {
      el("fundDxyPrice").textContent = `${f.dxy.price.toFixed(3)} (${f.dxy.change_pct >= 0 ? "+" : ""}${f.dxy.change_pct.toFixed(2)}%)`;
    }
    if (el("fundDxyImpact")) {
      el("fundDxyImpact").innerHTML = `5m RSI: ${f.dxy.rsi_5m} · Gold Impact: <strong style="color:${
        f.dxy.gold_impact === "BULLISH" ? "var(--buy)" : f.dxy.gold_impact === "BEARISH" ? "var(--sell)" : "var(--gold-bright)"
      };">${escapeHtml(f.dxy.gold_impact)}</strong>`;
    }
  }
  if (el("fundSummaryText")) el("fundSummaryText").textContent = f.summary;

  const evPill = el("eventAlertPill");
  if (evPill) {
    if (f.high_impact_events && f.high_impact_events.length > 0) {
      evPill.style.display = "inline-block";
      evPill.textContent = `⚡ EVENT ACTIVE: ${f.high_impact_events.join(" · ")}`;
    } else {
      evPill.style.display = "none";
    }
  }

  if (el("newsCountLabel")) {
    el("newsCountLabel").textContent = `${(f.headlines || []).length} Recent Stories`;
  }
  const nList = el("newsList");
  if (nList) {
    nList.innerHTML = (f.headlines || [])
      .map((h) => {
        const titleHtml = h.story_url
          ? `<a href="${h.story_url}" target="_blank" style="color:var(--text-0);text-decoration:none;font-weight:600;">${escapeHtml(
              h.title
            )}</a>`
          : `<span style="font-weight:600;">${escapeHtml(h.title)}</span>`;
        return `
          <div class="news-item">
            <div style="display:flex;flex-direction:column;gap:2px;">
              ${titleHtml}
              <span style="font-size:10px;color:var(--text-2);">${escapeHtml(h.source)} · ${escapeHtml(h.published)}</span>
            </div>
            <span class="news-tag ${escapeHtml(h.sentiment)}">${escapeHtml(h.sentiment)}</span>
          </div>
        `;
      })
      .join("");
  }
}

// ============================================================================
// 9. SECTION 7: DEEP HISTORICAL BACKTEST ENGINE & SUPABASE LEDGER
// ============================================================================
function renderBacktestRunsList(runs) {
  const sel = el("savedRunsSelect");
  if (!sel) return;
  if (!runs || !runs.length) {
    sel.innerHTML = `<option value="">No saved runs yet</option>`;
    return;
  }
  sel.innerHTML = runs
    .map((r) => {
      const isSelected = selectedRunDetail && selectedRunDetail.id === r.id ? "selected" : "";
      const sign = r.net_pnl_pts >= 0 ? "+" : "";
      return `<option value="${r.id}" ${isSelected}>Run #${r.id} · ${r.symbol} (${r.timeframe}) · ${r.strategy_mode} · ${r.total_trades} Trades · Win ${r.win_rate}% · ${sign}${r.net_pnl_pts.toFixed(2)} pts</option>`;
    })
    .join("");
}

async function loadBacktestRun(runId) {
  if (!runId) return;
  const dir = el("filterDirSelect")?.value || "ALL";
  const out = el("filterOutSelect")?.value || "ALL";
  try {
    const res = await fetch(`${API_BASE}/api/backtest_detail?run_id=${runId}&direction=${dir}&outcome=${out}`);
    const data = await res.json();
    if (data.detail) {
      selectedRunDetail = data.detail;
      renderSelectedBacktest(data.detail);
      updateBentoKpis();
    }
  } catch (e) {
    console.error("Failed to load backtest run:", e);
  }
}

function renderSelectedBacktest(bt) {
  if (!bt) return;
  if (el("btWinRate")) {
    el("btWinRate").textContent = `${bt.win_rate}%`;
    el("btWinRate").style.color = bt.win_rate >= 50 ? "var(--buy)" : "var(--gold-bright)";
  }
  if (el("btWinLossCount")) el("btWinLossCount").textContent = `W: ${bt.wins} / L: ${bt.losses}`;

  if (el("btNetPnl")) {
    el("btNetPnl").textContent = `${bt.net_pnl_pts >= 0 ? "+" : ""}${bt.net_pnl_pts.toFixed(2)} pts`;
    el("btNetPnl").style.color = bt.net_pnl_pts >= 0 ? "var(--buy)" : "var(--sell)";
  }
  if (el("btTotalTrades")) el("btTotalTrades").textContent = `Trades: ${bt.total_trades} (${bt.bars_tested} bars)`;
  if (el("btProfitFactor")) el("btProfitFactor").textContent = String(bt.profit_factor);
  if (el("btExpectancy")) {
    el("btExpectancy").textContent = `Expectancy: ${bt.expectancy_pts >= 0 ? "+" : ""}${bt.expectancy_pts.toFixed(2)} pts`;
  }
  if (el("btMaxDD")) el("btMaxDD").textContent = `-${bt.max_drawdown_pts.toFixed(2)} pts`;
  if (el("btAvgWinLoss")) {
    el("btAvgWinLoss").textContent = `Avg W/L: +${bt.avg_win.toFixed(1)} / -${bt.avg_loss.toFixed(1)}`;
  }

  if (el("eqCurveSubtitle")) {
    el("eqCurveSubtitle").textContent = `Run #${bt.id} · ${bt.symbol} (${bt.timeframe}) · ${bt.strategy_mode}`;
  }

  // Win vs Loss Breakdown Bar
  const total = Math.max(bt.total_trades || 1, 1);
  const winPct = Math.round(((bt.wins || 0) / total) * 100);
  const lossPct = 100 - winPct;
  if (el("wlWinLabel")) el("wlWinLabel").textContent = `Wins: ${bt.wins} (${winPct}%)`;
  if (el("wlLossLabel")) el("wlLossLabel").textContent = `Losses: ${bt.losses} (${lossPct}%)`;
  if (el("wlWinBar")) el("wlWinBar").style.width = `${winPct}%`;
  if (el("wlLossBar")) el("wlLossBar").style.width = `${lossPct}%`;

  const trades = bt.trades || [];
  const tp2Count = trades.filter((t) => t.outcome && t.outcome.includes("TP2")).length;
  const tp1Count = trades.filter((t) => t.outcome && t.outcome.includes("TP1")).length;
  const slCount = trades.filter((t) => t.outcome && t.outcome.includes("LOSS")).length;
  if (el("wlTp2Count")) el("wlTp2Count").textContent = String(tp2Count);
  if (el("wlTp1Count")) el("wlTp1Count").textContent = String(tp1Count);
  if (el("wlSlCount")) el("wlSlCount").textContent = String(slCount);

  // Backtest Trades Table
  const tbody = el("btTradesBody");
  if (tbody) {
    if (!trades.length) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;color:var(--text-2);padding:16px;">No trades match current filter.</td></tr>`;
    } else {
      tbody.innerHTML = trades
        .map((t) => {
          const isWin = t.outcome && t.outcome.startsWith("WIN");
          const shortEntry = (t.entry_time || "").replace(" UTC+7", "").slice(5);
          const shortExit = (t.exit_time || "").replace(" UTC+7", "").slice(11);
          return `
            <tr>
              <td class="tabular">${escapeHtml(shortEntry)} → ${escapeHtml(shortExit)}</td>
              <td><span class="pill ${t.direction === "BUY" ? "BUY" : "SELL"}">${escapeHtml(t.direction)}</span></td>
              <td style="font-size:10.5px;color:var(--text-1);">${escapeHtml(t.signal_type)}</td>
              <td class="tabular">$${t.entry_price.toFixed(2)} → $${t.exit_price.toFixed(2)}</td>
              <td class="tabular" style="font-size:10.5px;">$${t.sl_price.toFixed(1)} / $${t.tp1_price.toFixed(1)}</td>
              <td><span class="pill ${isWin ? "BUY" : "SELL"}">${escapeHtml(t.outcome)}</span></td>
              <td class="tabular" style="font-weight:800;color:${t.pnl_pts >= 0 ? "var(--buy)" : "var(--sell)"};">
                ${t.pnl_pts >= 0 ? "+" : ""}${t.pnl_pts.toFixed(2)} pts
              </td>
            </tr>
          `;
        })
        .join("");
    }
  }

  drawEquityCurve(bt.equity_curve || []);
}

function drawEquityCurve(eqPoints) {
  const equityCanvas = el("equityCanvas");
  if (!equityCanvas) return;

  const isLight = document.documentElement.getAttribute("data-theme") === "light";
  const canvasBg = isLight ? "#f8fafc" : "#080b12";

  const dpr = window.devicePixelRatio || 1;
  const rect = equityCanvas.getBoundingClientRect();
  const width = rect.width || 600;
  const height = 165;
  equityCanvas.width = width * dpr;
  equityCanvas.height = height * dpr;
  const ctx = equityCanvas.getContext("2d");
  ctx.scale(dpr, dpr);

  ctx.fillStyle = canvasBg;
  ctx.fillRect(0, 0, width, height);

  if (!eqPoints || !eqPoints.length) {
    ctx.fillStyle = "#64748b";
    ctx.font = "12px Inter, sans-serif";
    ctx.fillText("No trades in this backtest run.", 20, height / 2);
    return;
  }

  const padL = 16, padR = 64, padT = 16, padB = 18;
  const plotW = width - padL - padR;
  const plotH = height - padT - padB;

  const vals = [0, ...eqPoints.map((p) => p.cum_pnl_pts)];
  let minV = Math.min(...vals, -2);
  let maxV = Math.max(...vals, 2);
  const span = Math.max(maxV - minV, 2);
  minV -= span * 0.1;
  maxV += span * 0.1;

  const yOf = (v) => padT + plotH * (1 - (v - minV) / (maxV - minV));
  const stepX = plotW / Math.max(vals.length - 1, 1);

  const yZero = yOf(0);
  ctx.strokeStyle = "rgba(148, 163, 184, 0.3)";
  ctx.setLineDash([4, 4]);
  ctx.beginPath();
  ctx.moveTo(padL, yZero);
  ctx.lineTo(width - padR, yZero);
  ctx.stroke();
  ctx.setLineDash([]);

  const lastVal = vals[vals.length - 1];
  const lineCol = lastVal >= 0 ? "#00d4aa" : "#f43f5e";
  const grad = ctx.createLinearGradient(0, padT, 0, height - padB);
  grad.addColorStop(0, lastVal >= 0 ? "rgba(0, 212, 170, 0.28)" : "rgba(244, 63, 94, 0.28)");
  grad.addColorStop(1, "rgba(8, 11, 18, 0.0)");

  ctx.beginPath();
  vals.forEach((v, idx) => {
    const x = padL + idx * stepX;
    const y = yOf(v);
    if (idx === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.lineTo(padL + (vals.length - 1) * stepX, height - padB);
  ctx.lineTo(padL, height - padB);
  ctx.closePath();
  ctx.fillStyle = grad;
  ctx.fill();

  ctx.strokeStyle = lineCol;
  ctx.lineWidth = 2;
  ctx.beginPath();
  vals.forEach((v, idx) => {
    const x = padL + idx * stepX;
    const y = yOf(v);
    if (idx === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  ctx.fillStyle = "#94a3b8";
  ctx.font = "11px monospace";
  ctx.fillText(`+${maxV.toFixed(1)}`, width - padR + 6, padT + 8);
  ctx.fillText(`0.0`, width - padR + 6, yZero + 4);
  ctx.fillText(`${minV.toFixed(1)}`, width - padR + 6, height - padB);
}

function renderLiveSignalsTable(signals) {
  const tbody = el("liveSignalsBody");
  if (!tbody) return;
  if (!signals || !signals.length) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;color:var(--text-2);padding:16px;">No live signals recorded yet.</td></tr>`;
    return;
  }

  tbody.innerHTML = signals
    .map((s) => {
      const isBuy = s.direction === "BUY";
      let statusBadge = `<span style="color:var(--gold-bright);font-weight:700;">🔒 ACTIVE</span>`;
      if (s.status === "HIT_TP1" || s.status === "HIT_TP2") {
        statusBadge = `<span class="pill BUY">${escapeHtml(s.status)}</span>`;
      } else if (s.status === "HIT_SL") {
        statusBadge = `<span class="pill SELL">HIT_SL</span>`;
      } else if (s.status === "MANUAL_CLOSE") {
        statusBadge = `<span style="color:var(--text-2);">CLOSED</span>`;
      }
      const pnl = s.pnl_pts || 0;
      const pnlTxt = pnl !== 0 ? ` (${pnl > 0 ? "+" : ""}${pnl.toFixed(2)} pts)` : "";

      return `
        <tr>
          <td class="tabular">${escapeHtml((s.candle_time || "").replace(" UTC+7", "").slice(5))}</td>
          <td><strong style="color:var(--gold-bright);">${escapeHtml(s.trading_style || "SWING")}</strong> · ${escapeHtml(s.timeframe)}</td>
          <td><span class="pill ${isBuy ? "BUY" : "SELL"}">${escapeHtml(s.direction)}</span></td>
          <td class="tabular">$${s.entry_price.toFixed(2)}</td>
          <td class="tabular" style="font-size:10.5px;">$${s.sl_price.toFixed(1)} / $${s.tp1_price.toFixed(1)}</td>
          <td style="font-size:10.5px;color:var(--ai-accent);font-weight:700;">${escapeHtml(s.ai_verdict || "APPROVED")} (${s.confidence}%)</td>
          <td class="tabular">${statusBadge}<span style="color:${pnl >= 0 ? "var(--buy)" : "var(--sell)"};font-weight:700;">${pnlTxt}</span></td>
        </tr>
      `;
    })
    .join("");
}

// ============================================================================
// 10. SECTION 5 & 8: AI QUANT COPILOT, STRATEGY LAB & FEATURE FLAGS
// ============================================================================
function renderStrategyLab() {
  const grid = el("strategyLabGrid");
  if (!grid) return;

  const blueprints = [
    {
      id: "SWING_GOLDEN_POCKET",
      name: "Swing Golden Pocket (Pro Default)",
      style: "SWING",
      tf: "1h",
      sl: 1.5,
      tp1: 2.5,
      tp2: 4.0,
      badge: "STAR STRATEGY",
      desc: "Institutional 1H/4H Fibonacci 38.2%–61.8% retracement aligned with EMA 21/50 structure & DXY filter."
    },
    {
      id: "PRO_TREND_PULLBACK",
      name: "Intraday Killzone EMA Pullback",
      style: "INTRADAY",
      tf: "15m",
      sl: 1.2,
      tp1: 1.8,
      tp2: 3.0,
      badge: "LONDON / NY",
      desc: "Captures 15m impulse pullbacks into EMA 21 during London & New York overlap sessions."
    },
    {
      id: "LIQUIDITY_SWEEP_REVERSAL",
      name: "Bollinger + RSI Liquidity Sweep",
      style: "SCALPING",
      tf: "5m",
      sl: 1.0,
      tp1: 1.5,
      tp2: 2.2,
      badge: "MEAN REVERSION",
      desc: "Detects exhaustion wicks outside 2σ Bollinger Bands with RSI(14) divergence."
    },
    {
      id: "MOMENTUM_BREAKOUT",
      name: "Macro Position Breakout Runner",
      style: "POSITION",
      tf: "4h",
      sl: 1.8,
      tp1: 3.0,
      tp2: 5.0,
      badge: "MACRO TREND",
      desc: "Multi-day 4H/1D volatility expansion runner with 50% partial lock at TP1 + break-even trail."
    }
  ];

  grid.innerHTML = blueprints
    .map(
      (bp) => `
      <div class="strategy-preset-card" data-style="${bp.style}" data-tf="${bp.tf}" data-sl="${bp.sl}" data-tp1="${bp.tp1}" data-tp2="${bp.tp2}" data-strat="${bp.id}">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
          <strong style="font-size:12.5px;color:var(--text-0);">${escapeHtml(bp.name)}</strong>
          <span style="font-size:9.5px;padding:2px 6px;border-radius:99px;background:rgba(139,92,246,0.16);color:#c4b5fd;font-weight:800;">${escapeHtml(bp.badge)}</span>
        </div>
        <div style="font-size:11px;color:var(--text-1);line-height:1.4;margin-bottom:8px;">${escapeHtml(bp.desc)}</div>
        <div class="tabular" style="font-size:10.5px;color:var(--gold-bright);font-weight:700;">
          Style: ${bp.style} (${bp.tf}) · SL ${bp.sl}x / TP1 ${bp.tp1}x / TP2 ${bp.tp2}x ATR
        </div>
      </div>
    `
    )
    .join("");

  grid.querySelectorAll(".strategy-preset-card").forEach((card) => {
    card.addEventListener("click", () => {
      const st = card.dataset.style;
      const tf = card.dataset.tf;
      if (el("btStrategySelect")) el("btStrategySelect").value = card.dataset.strat;
      if (el("btSlInput")) el("btSlInput").value = card.dataset.sl;
      if (el("btTp1Input")) el("btTp1Input").value = card.dataset.tp1;
      if (el("btTp2Input")) el("btTp2Input").value = card.dataset.tp2;
      switchTradingStyle(st, tf);
    });
  });
}

function renderFeatureFlagsPanel() {
  const grid = el("featureFlagsGrid");
  if (!grid) return;

  const modules = [
    { name: "TradingView Multi-Broker Stream", mode: "LIVE", status: "ACTIVE", desc: "Real-time 1.5s quotes across OANDA, FXCM, FOREX.com & TVC:DXY via Railway." },
    { name: "3-Agent AI Committee + Argon", mode: "LIVE", status: "ACTIVE", desc: "Technical + Macro/News + Risk Manager pre-signal gate with Gemini 4 Argon support." },
    { name: "Single-Position Lock Engine", mode: "LIVE", status: "ACTIVE", desc: "Prevents duplicate entries on a timeframe until active trade hits TP1/TP2 or SL." },
    { name: "Supabase PostgreSQL Cloud DB", mode: "LIVE", status: "ACTIVE", desc: "Persists backtest runs, forward-tested signals, and Telegram subscribers in ap-southeast-1." },
    { name: "Telegram Signal Hub (@this_is_ai_signal_bot)", mode: "LIVE", status: "ACTIVE", desc: "24/7 background daemon polling /start, /swing, /intraday, /scalp, /news." },
    { name: "Paper Order Simulator & Sizer", mode: "PAPER", status: "SAFE GUARD", desc: "Calculates exact oz/lot risk sizing and simulates orders without live broker risk." }
  ];

  grid.innerHTML = modules
    .map(
      (m) => `
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:12px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
          <strong style="font-size:12px;color:var(--text-0);">${escapeHtml(m.name)}</strong>
          <span class="mode-safety-pill ${m.mode === "LIVE" ? "live-lock" : "paper-sim"}">${m.mode} · ${m.status}</span>
        </div>
        <div style="font-size:11px;color:var(--text-1);line-height:1.4;">${escapeHtml(m.desc)}</div>
      </div>
    `
    )
    .join("");
}

function generateCopilotReply(topic) {
  const d = currentData;
  if (!d) {
    return "Waiting for live XAU/USD data from Railway (`OANDA:XAUUSD`)... Click **Sync Now** or wait a moment.";
  }
  const q = topic.toLowerCase();
  const price = d.current_price.toFixed(2);
  const ai = d.ai_agent || {};
  const dxy = d.fundamentals?.dxy || {};

  if (q.includes("swing") || q.includes("golden") || q.includes("fib")) {
    return `**1H Swing & Fibonacci Golden Pocket Analysis (${d.symbol} @ $${price}):**\n• **Active Bias:** ${d.direction} (${d.confidence}% confidence) — ${d.signal}\n• **Golden Pocket Zone (38.2%–61.8%):** ${ai.watch_zone || "Evaluating"}\n• **Levels:** Ref Entry $${d.entry.toFixed(2)} | Stop Loss $${d.stop_loss.toFixed(2)} (${d.sl_mult}x ATR) | TP1 $${d.take_profit_1.toFixed(2)} | TP2 $${d.take_profit_2.toFixed(2)}.`;
  }
  if (q.includes("dxy") || q.includes("macro") || q.includes("news")) {
    return `**Macro & US Dollar Index (\`TVC:DXY\`) Synthesis:**\n• **DXY Spot:** ${dxy.price ? dxy.price.toFixed(3) : "--"} (${dxy.change_pct >= 0 ? "+" : ""}${dxy.change_pct || 0}%) → Gold Impact: **${dxy.gold_impact || "NEUTRAL"}**\n• **Wire Headlines Bias:** ${d.fundamentals?.bias || "NEUTRAL"} (${d.fundamentals?.bullish_headlines || 0} Bullish vs ${d.fundamentals?.bearish_headlines || 0} Bearish)\n• **Summary:** ${d.fundamentals?.summary || "No major macro divergence."}`;
  }
  if (q.includes("risk") || q.includes("size") || q.includes("lot")) {
    const acct = parseFloat(el("riskAccountInput")?.value) || 10000;
    const rPct = parseFloat(el("riskPctInput")?.value) || 1.0;
    const stopDist = Math.max(Math.abs(d.entry - d.stop_loss), 0.1);
    const usdRisk = acct * (rPct / 100);
    const oz = usdRisk / stopDist;
    return `**Optimal Position Sizing ($${acct.toLocaleString()} Account @ ${rPct}% Risk):**\n• **Max Dollar Risk:** $${usdRisk.toFixed(2)}\n• **ATR(14) Stop Distance:** ${stopDist.toFixed(2)} pts ($${d.entry.toFixed(2)} → $${d.stop_loss.toFixed(2)})\n• **Recommended Size:** **${oz.toFixed(2)} oz** (${(oz / 100).toFixed(2)} standard lots). Move SL to Break-Even at TP1 ($${d.take_profit_1.toFixed(2)}).`;
  }
  if (q.includes("mtf") || q.includes("confluence")) {
    const badge = el("mtfAlignmentBadge")?.textContent || "Aligned";
    return `**Multi-Timeframe Confluence (${d.trading_style}):**\n• **Matrix Alignment:** ${badge}\n• **EMA Ribbon (${d.timeframe}):** EMA9 ($${d.indicators.ema9.toFixed(1)}) / EMA21 ($${d.indicators.ema21.toFixed(1)}) / EMA50 ($${d.indicators.ema50.toFixed(1)})\n• **AI Committee Verdict:** ${ai.verdict_badge || "Evaluated"} — ${ai.executive_summary || ""}`;
  }
  return `**AurumQuant AI Synthesis (${d.symbol} · ${d.trading_style} ${d.timeframe} @ $${price}):**\n• **Signal:** ${d.signal} (${d.confidence}% Confidence) | **AI Gate:** ${ai.verdict_badge || "--"}\n• **Entry:** $${d.entry.toFixed(2)} | **SL:** $${d.stop_loss.toFixed(2)} | **TP1:** $${d.take_profit_1.toFixed(2)} | **TP2:** $${d.take_profit_2.toFixed(2)}\n• **Rationale:** ${d.rationale}`;
}

function appendCopilotMessage(role, text) {
  const box = el("aiCopilotChatBox");
  if (!box) return;
  const div = document.createElement("div");
  div.className = `chat-msg ${role}`;
  const formatted = escapeHtml(text)
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\n/g, "<br/>");
  div.innerHTML =
    role === "ai"
      ? `<div style="font-size:10px;font-weight:800;color:var(--ai-accent);margin-bottom:3px;">AURUMQUANT AI COPILOT</div>${formatted}`
      : formatted;
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
}

// ============================================================================
// 11. NAVIGATION, THEME SWITCHER, COMMAND PALETTE (⌘K) & EVENT LISTENERS
// ============================================================================
function switchTradingStyle(style, customTf = null) {
  currentStyle = style;
  const cfg = STYLE_DEFAULTS[style] || STYLE_DEFAULTS.SWING;
  currentTf = customTf || cfg.tf;

  document.querySelectorAll("#styleGroup .style-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.style === style);
  });
  document.querySelectorAll("#tfGroup .tf-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.tf === currentTf);
  });

  if (el("btSlInput")) el("btSlInput").value = cfg.sl;
  if (el("btTp1Input")) el("btTp1Input").value = cfg.tp1;
  if (el("btTp2Input")) el("btTp2Input").value = cfg.tp2;

  selectedRunDetail = null;
  fetchFullDashboard();
  showToast(`Switched to ${cfg.label} (${currentTf})`);
}

function switchTimeframe(tf) {
  currentTf = tf;
  document.querySelectorAll("#tfGroup .tf-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.tf === tf);
  });
  selectedRunDetail = null;
  fetchFullDashboard();
  showToast(`Switched chart timeframe to ${tf.toUpperCase()}`);
}

window.switchTimeframe = switchTimeframe;

function switchWorkspaceView(viewKey) {
  const titles = {
    overview: ["Workspace", "AI Command Center"],
    terminal: ["Workspace", "Institutional Trading Terminal"],
    "ai-signals": ["AI Intelligence", "Pre-Signal 3-Agent Committee & Gate"],
    "ai-assistant": ["AI Intelligence", "AI Quant Copilot & Strategy Lab"],
    bots: ["Trading Operations", "24/7 Telegram Bot & Autonomous Scanner"],
    backtesting: ["Trading Operations", "Deep Historical Backtest & Supabase Ledger"],
    risk: ["Governance", "Risk Management & Modular Architecture"]
  };

  document.querySelectorAll(".nav-item[data-nav]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.nav === viewKey);
  });

  const [bc, title] = titles[viewKey] || titles.overview;
  if (el("pageBreadcrumb")) el("pageBreadcrumb").textContent = bc;
  if (el("pageTitle")) el("pageTitle").textContent = title;

  document.querySelectorAll(".workspace-section").forEach((sec) => {
    if (viewKey === "overview") {
      sec.classList.remove("hidden-by-nav");
    } else {
      const tags = (sec.dataset.section || "").split(/\s+/);
      sec.classList.toggle("hidden-by-nav", !tags.includes(viewKey));
    }
  });

  if (el("appSidebar")) el("appSidebar").classList.remove("mobile-open");
  setTimeout(() => {
    drawCharts();
    if (selectedRunDetail) drawEquityCurve(selectedRunDetail.equity_curve || []);
  }, 50);
}

function initCommandPalette() {
  const modal = el("cmdPaletteModal");
  const input = el("cmdPaletteInput");
  const list = el("cmdPaletteList");
  if (!modal || !input || !list) return;

  const commands = [
    { label: "Switch to Swing Trade (1H Default ★)", cat: "Trading Style", run: () => switchTradingStyle("SWING") },
    { label: "Switch to Intraday Session (15m)", cat: "Trading Style", run: () => switchTradingStyle("INTRADAY") },
    { label: "Switch to High-Speed Scalping (1m)", cat: "Trading Style", run: () => switchTradingStyle("SCALPING") },
    { label: "Switch to Macro Position (4H)", cat: "Trading Style", run: () => switchTradingStyle("POSITION") },
    { label: "Open Overview Command Center", cat: "Navigation", run: () => switchWorkspaceView("overview") },
    { label: "Open 4-Region Trading Terminal", cat: "Navigation", run: () => switchWorkspaceView("terminal") },
    { label: "Open AI Signals & 3-Agent Gate", cat: "Navigation", run: () => switchWorkspaceView("ai-signals") },
    { label: "Open AI Quant Copilot & Strategy Lab", cat: "Navigation", run: () => switchWorkspaceView("ai-assistant") },
    { label: "Open Deep Backtest & Supabase Ledger", cat: "Navigation", run: () => switchWorkspaceView("backtesting") },
    { label: "Broadcast Active Signal to Telegram Now", cat: "Telegram Bot", run: () => triggerTelegramBroadcast() },
    { label: "Toggle Dark / Light Theme", cat: "Appearance", run: () => toggleTheme() },
    { label: "Sync Live TradingView & AI Committee Now", cat: "System", run: () => fetchFullDashboard() }
  ];

  function renderCmds(q = "") {
    const query = q.trim().toLowerCase();
    const filtered = commands.filter(
      (c) => !query || c.label.toLowerCase().includes(query) || c.cat.toLowerCase().includes(query)
    );
    list.innerHTML = filtered
      .map(
        (c, i) => `
        <div class="cmd-item" data-idx="${i}">
          <span style="font-weight:600;">${escapeHtml(c.label)}</span>
          <span style="font-size:10.5px;color:var(--text-2);background:var(--bg-2);padding:2px 7px;border-radius:99px;">${escapeHtml(c.cat)}</span>
        </div>
      `
      )
      .join("");
    list.querySelectorAll(".cmd-item").forEach((item, idx) => {
      item.addEventListener("click", () => {
        filtered[idx].run();
        modal.classList.remove("open");
      });
    });
  }

  function openModal() {
    modal.classList.add("open");
    input.value = "";
    renderCmds("");
    setTimeout(() => input.focus(), 40);
  }

  if (el("openCmdPaletteBtn")) el("openCmdPaletteBtn").addEventListener("click", openModal);
  if (el("openCmdFooterBtn")) el("openCmdFooterBtn").addEventListener("click", openModal);

  modal.addEventListener("click", (e) => {
    if (e.target === modal) modal.classList.remove("open");
  });

  input.addEventListener("input", () => renderCmds(input.value));

  window.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      if (modal.classList.contains("open")) modal.classList.remove("open");
      else openModal();
    } else if (e.key === "Escape" && modal.classList.contains("open")) {
      modal.classList.remove("open");
    }
  });
}

function toggleTheme() {
  const html = document.documentElement;
  const next = html.getAttribute("data-theme") === "light" ? "dark" : "light";
  html.setAttribute("data-theme", next);
  try {
    localStorage.setItem("aurumquant_theme", next);
  } catch (e) {}
  drawCharts();
  if (selectedRunDetail) drawEquityCurve(selectedRunDetail.equity_curve || []);
  showToast(`Switched to ${next.toUpperCase()} theme`);
}

async function triggerTelegramBroadcast() {
  const chatId = el("tgChatIdInput")?.value.trim() || "";
  try {
    const res = await fetch(`${API_BASE}/api/telegram/send`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        symbol: currentSymbol,
        interval: currentTf,
        trading_style: currentStyle,
        chat_id: chatId
      })
    });
    const data = await res.json();
    if (data.telegram) renderTelegramStatus(data.telegram);
    if (data.broadcast && data.broadcast.sent > 0) {
      showToast(`Broadcasted ${currentStyle} (${currentTf}) AI Signal to ${data.broadcast.sent} Telegram chat(s)!`);
    } else {
      showToast(data.broadcast?.error || "Open @this_is_ai_signal_bot in Telegram and send /start first!");
    }
  } catch (e) {
    showToast("Telegram broadcast request failed.");
  }
}

function initEventListeners() {
  // Restore saved theme
  try {
    const savedTheme = localStorage.getItem("aurumquant_theme");
    if (savedTheme === "light" || savedTheme === "dark") {
      document.documentElement.setAttribute("data-theme", savedTheme);
    }
  } catch (e) {}

  // Sidebar collapse & mobile drawer
  if (el("sidebarCollapseBtn")) {
    el("sidebarCollapseBtn").addEventListener("click", () => {
      el("appShell")?.classList.toggle("sidebar-collapsed");
      setTimeout(() => {
        drawCharts();
        if (selectedRunDetail) drawEquityCurve(selectedRunDetail.equity_curve || []);
      }, 240);
    });
  }
  if (el("mobileMenuBtn")) {
    el("mobileMenuBtn").addEventListener("click", () => {
      el("appSidebar")?.classList.toggle("mobile-open");
    });
  }

  document.querySelectorAll(".nav-item[data-nav]").forEach((btn) => {
    btn.addEventListener("click", () => switchWorkspaceView(btn.dataset.nav));
  });

  if (el("themeToggleBtn")) {
    el("themeToggleBtn").addEventListener("click", toggleTheme);
  }

  // Style & Timeframe buttons
  document.querySelectorAll("#styleGroup .style-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchTradingStyle(btn.dataset.style));
  });
  document.querySelectorAll("#tfGroup .tf-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchTimeframe(btn.dataset.tf));
  });

  if (el("symbolSelect")) {
    el("symbolSelect").addEventListener("change", (e) => {
      currentSymbol = e.target.value;
      selectedRunDetail = null;
      fetchFullDashboard();
      pollLiveTick();
    });
  }

  if (el("refreshBtn")) {
    el("refreshBtn").addEventListener("click", () => {
      fetchFullDashboard();
      pollLiveTick();
      showToast("Synced live TradingView feeds, 3-Agent AI Committee & Supabase!");
    });
  }

  if (el("refreshNewsBtn")) {
    el("refreshNewsBtn").addEventListener("click", async () => {
      const res = await fetch(`${API_BASE}/api/fundamentals?force=1`);
      const data = await res.json();
      renderFundamentals(data);
      showToast("Refreshed Macro DXY & Live Wire Headlines!");
    });
  }

  if (el("closePosBtn")) {
    el("closePosBtn").addEventListener("click", async () => {
      await fetch(`${API_BASE}/api/position/close`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol: currentSymbol, timeframe: currentTf })
      });
      showToast("Closed active position — Single-Position Lock released!");
      fetchFullDashboard();
    });
  }

  // Telegram Bot Controls
  if (el("tgSyncBtn")) {
    el("tgSyncBtn").addEventListener("click", async () => {
      const chatId = el("tgChatIdInput")?.value.trim() || "";
      const res = await fetch(`${API_BASE}/api/telegram/sync`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chat_id: chatId })
      });
      const data = await res.json();
      renderTelegramStatus(data);
      const count = (data.subscribers || []).length;
      showToast(count > 0 ? `Synced! ${count} Telegram Chat(s) connected.` : "Polled @this_is_ai_signal_bot — send /start in Telegram!");
    });
  }

  if (el("tgSendNowBtn")) el("tgSendNowBtn").addEventListener("click", triggerTelegramBroadcast);
  if (el("sendTelegramQuickBtn")) el("sendTelegramQuickBtn").addEventListener("click", triggerTelegramBroadcast);

  if (el("tgAutoNotifyChk")) {
    el("tgAutoNotifyChk").addEventListener("change", async (e) => {
      const res = await fetch(`${API_BASE}/api/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ telegram_auto_notify: e.target.checked })
      });
      const data = await res.json();
      if (data.telegram) renderTelegramStatus(data.telegram);
      showToast(`Telegram 24/7 Auto-Push: ${e.target.checked ? "ENABLED" : "DISABLED"}`);
    });
  }

  if (el("saveGeminiKeyBtn")) {
    el("saveGeminiKeyBtn").addEventListener("click", async () => {
      const k = el("geminiKeyInput")?.value.trim() || "";
      await fetch(`${API_BASE}/api/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ gemini_api_key: k })
      });
      showToast(k ? "Saved Gemini 4 Argon API key — syncing AI Committee..." : "Using Built-in 3-Agent Quant Committee");
      fetchFullDashboard();
    });
  }

  // Chart Toolbar Controls
  if (el("toggleBBBtn")) {
    el("toggleBBBtn").addEventListener("click", (e) => {
      showBB = !showBB;
      e.currentTarget.textContent = `Bollinger Bands: ${showBB ? "ON" : "OFF"}`;
      drawCharts();
    });
  }
  if (el("toggleLevelsBtn")) {
    el("toggleLevelsBtn").addEventListener("click", (e) => {
      showSignalLines = !showSignalLines;
      e.currentTarget.textContent = `Signal Lines: ${showSignalLines ? "ON" : "OFF"}`;
      drawCharts();
    });
  }
  if (el("toggleOscBtn")) {
    el("toggleOscBtn").addEventListener("click", (e) => {
      oscMode = oscMode === "RSI" ? "MACD" : "RSI";
      e.currentTarget.textContent = `Oscillator: ${oscMode === "RSI" ? "RSI (14)" : "MACD (12,26,9)"}`;
      drawCharts();
    });
  }

  // Price Canvas Crosshair Readout
  const priceCanvas = el("priceCanvas");
  if (priceCanvas) {
    priceCanvas.addEventListener("mousemove", (e) => {
      if (!currentData || !currentData.series) return;
      const rect = priceCanvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const candles = currentData.series.candles;
      const plotW = rect.width - 14 - 74;
      const stepX = plotW / candles.length;
      const idx = Math.floor((x - 14) / stepX);
      if (idx >= 0 && idx < candles.length) {
        hoverIdx = idx;
        const c = candles[idx];
        const r = currentData.series.rsi14[idx];
        if (el("hoverOhlcInfo")) {
          el("hoverOhlcInfo").textContent = `${c.time_local || c.time} | O: $${c.open.toFixed(2)} H: $${c.high.toFixed(2)} L: $${c.low.toFixed(2)} C: $${c.close.toFixed(2)} | RSI: ${r.toFixed(1)}`;
        }
        drawCharts();
      }
    });
    priceCanvas.addEventListener("mouseleave", () => {
      hoverIdx = null;
      if (el("hoverOhlcInfo")) el("hoverOhlcInfo").textContent = "Hover chart to inspect candle (UTC+7)";
      drawCharts();
    });
  }

  // Watchlist search & Position Sizer
  if (el("watchlistSearchInput")) {
    el("watchlistSearchInput").addEventListener("input", renderTerminalWatchlist);
  }
  ["riskAccountInput", "riskPctInput"].forEach((id) => {
    if (el(id)) el(id).addEventListener("input", updatePositionSizer);
  });

  // Simulated Paper Order Buttons
  ["simBuyBtn", "simSellBtn"].forEach((btnId) => {
    if (el(btnId)) {
      el(btnId).addEventListener("click", () => {
        if (!currentData) return;
        const side = btnId === "simBuyBtn" ? "BUY" : "SELL";
        const lots = el("calcLotSize")?.textContent || "0.10 lots";
        const entry = currentData.current_price.toFixed(2);
        const fb = el("simOrderFeedback");
        if (fb) {
          fb.innerHTML = `<span style="color:${side === "BUY" ? "var(--buy)" : "var(--sell)"};font-weight:700;">✓ Simulated Paper ${side}:</span> ${lots} of ${currentSymbol} @ $${entry} (SL: $${currentData.stop_loss.toFixed(2)} / TP1: $${currentData.take_profit_1.toFixed(2)})`;
        }
        showToast(`Simulated Paper ${side} Ticket logged (${lots} @ $${entry})`);
      });
    }
  });

  // AI Quant Copilot
  document.querySelectorAll(".prompt-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const label = chip.textContent;
      appendCopilotMessage("user", label);
      const reply = generateCopilotReply(chip.dataset.prompt || label);
      appendCopilotMessage("ai", reply);
    });
  });
  if (el("aiCopilotSendBtn")) {
    const sendAsk = () => {
      const inp = el("aiCopilotInput");
      if (!inp || !inp.value.trim()) return;
      const q = inp.value.trim();
      inp.value = "";
      appendCopilotMessage("user", q);
      appendCopilotMessage("ai", generateCopilotReply(q));
    };
    el("aiCopilotSendBtn").addEventListener("click", sendAsk);
    el("aiCopilotInput")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") sendAsk();
    });
  }

  // Deep Historical Backtest Runner
  if (el("runBacktestBtn")) {
    el("runBacktestBtn").addEventListener("click", async () => {
      const btn = el("runBacktestBtn");
      btn.textContent = "Running Deep Backtest...";
      btn.disabled = true;
      try {
        const uiStrat = el("btStrategySelect")?.value || "ALL";
        const horizonKey = el("btHorizonSelect")?.value || "30d";
        const durCfg = DURATION_BARS_MAP[horizonKey] || DURATION_BARS_MAP["30d"];
        const payload = {
          trading_style: currentStyle,
          symbol: currentSymbol,
          interval: currentTf,
          strategy_mode: STRATEGY_MODE_MAP[uiStrat] || "PRO_CONFIRMED",
          duration_preset: durCfg.preset,
          bars_tested: durCfg.bars,
          sl_mult: parseFloat(el("btSlInput")?.value) || 1.5,
          tp1_mult: parseFloat(el("btTp1Input")?.value) || 2.5,
          tp2_mult: parseFloat(el("btTp2Input")?.value) || 4.0
        };
        const res = await fetch(`${API_BASE}/api/backtest/run`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.detail) {
          selectedRunDetail = data.detail;
          renderBacktestRunsList(data.runs || []);
          renderSelectedBacktest(data.detail);
          updateBentoKpis();
          showToast(`Saved ${currentStyle} Backtest Run #${data.detail.id} (${data.detail.bars_tested} bars) to Supabase!`);
        }
      } catch (err) {
        console.error("Backtest run error:", err);
      } finally {
        btn.textContent = "Run Deep Backtest & Save to DB";
        btn.disabled = false;
      }
    });
  }

  if (el("savedRunsSelect")) {
    el("savedRunsSelect").addEventListener("change", (e) => {
      if (e.target.value) loadBacktestRun(e.target.value);
    });
  }

  ["filterDirSelect", "filterOutSelect"].forEach((id) => {
    if (el(id)) {
      el(id).addEventListener("change", () => {
        if (selectedRunDetail) loadBacktestRun(selectedRunDetail.id);
      });
    }
  });

  window.addEventListener("resize", () => {
    drawCharts();
    if (selectedRunDetail) drawEquityCurve(selectedRunDetail.equity_curve || []);
  });
}

// ============================================================================
// 12. BOOTSTRAP ON LOAD
// ============================================================================
document.addEventListener("DOMContentLoaded", () => {
  renderStrategyLab();
  renderFeatureFlagsPanel();
  initCommandPalette();
  initEventListeners();
  updateClocksAndCountdown();
  setInterval(updateClocksAndCountdown, 1000);

  fetchFullDashboard();
  pollLiveTick();
  setInterval(pollLiveTick, 2000);
  setInterval(fetchFullDashboard, 20000);
});
