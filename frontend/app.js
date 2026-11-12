// ============================================================================
// AurumQuant AI — Minimalist Institutional XAU/USD Trading Platform (Nuxt 4)
// Zero-Overflow Multi-View Controller + Action Confirmation Dialogs
// ============================================================================

const API_BASE =
  typeof window !== "undefined" && typeof window.API_BASE === "string"
    ? window.API_BASE
    : "https://gold-signal-api-production.up.railway.app";

let currentSymbol = "OANDA:XAUUSD";
let currentStyle = "SWING";
let currentTf = "1h";
let currentView = "overview";
let currentData = null;
let selectedRunDetail = null;
let lastTickPrice = null;
let latestTickBrokers = {};
let latestTgSubscribersCount = 1;
let customAlertPrice = null;

let showBB = true;
let showSignalLines = true;
let oscMode = "RSI";
let hoverIdx = null;
let pendingConfirmAction = null;

const STYLE_DEFAULTS = {
  SWING:    { tf: "1h",  sl: 1.5, tp1: 2.5, tp2: 4.0, label: "Swing Trade (1H)" },
  INTRADAY: { tf: "15m", sl: 1.2, tp1: 1.8, tp2: 3.0, label: "Intraday (15m)" },
  SCALPING: { tf: "1m",  sl: 1.0, tp1: 1.5, tp2: 2.0, label: "Scalping (1m)" },
  POSITION: { tf: "4h",  sl: 1.8, tp1: 3.0, tp2: 5.0, label: "Position (4H)" }
};

const DURATION_BARS_MAP = {
  "300": { preset: "300_BARS", bars: 300 },
  "7d":  { preset: "7_DAYS",   bars: 450 },
  "30d": { preset: "30_DAYS",  bars: 720 },
  "90d": { preset: "90_DAYS",  bars: 1200 },
  "1y":  { preset: "1_YEAR",   bars: 2000 }
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

function showToast(msg) {
  let t = el("toast");
  if (!t) {
    t = document.createElement("div");
    t.id = "toast";
    t.style.cssText =
      "position:fixed;bottom:20px;right:20px;z-index:9999;background:rgba(13,17,27,0.96);color:#f8fafc;border:1px solid #38bdf8;border-radius:9px;padding:9px 14px;font-size:12px;font-weight:700;box-shadow:0 10px 28px rgba(0,0,0,0.55);transition:opacity 0.2s;";
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
    }, 200);
  }, 2800);
}

// ============================================================================
// 1. REUSABLE ACTION CONFIRMATION DIALOG
// ============================================================================
function openConfirmDialog({
  title = "Confirm Action",
  badge = "CONFIRM",
  desc = "Please confirm this operation:",
  meta = "",
  confirmLabel = "Confirm ↵",
  danger = false,
  onConfirm = null,
  onCancel = null
}) {
  const modal = el("confirmActionModal");
  if (!modal) {
    if (onConfirm) onConfirm();
    return;
  }
  if (el("confirmModalTitle")) el("confirmModalTitle").textContent = title;
  if (el("confirmModalBadge")) el("confirmModalBadge").textContent = badge;
  if (el("confirmModalDesc")) el("confirmModalDesc").textContent = desc;
  const metaBox = el("confirmModalMeta");
  if (metaBox) {
    metaBox.innerHTML = meta;
    metaBox.style.display = meta ? "block" : "none";
  }
  const okBtn = el("confirmModalOkBtn");
  if (okBtn) {
    okBtn.textContent = confirmLabel;
    okBtn.className = danger ? "btn danger" : "btn primary";
  }
  pendingConfirmAction = { onConfirm, onCancel };
  modal.classList.add("open");
}

function closeConfirmDialog(confirmed = false) {
  const modal = el("confirmActionModal");
  if (modal) modal.classList.remove("open");
  const act = pendingConfirmAction;
  pendingConfirmAction = null;
  if (confirmed && act && typeof act.onConfirm === "function") {
    act.onConfirm();
  } else if (!confirmed && act && typeof act.onCancel === "function") {
    act.onCancel();
  }
}

// ============================================================================
// 2. CLOCKS, COUNTDOWN & MARKET SESSION BADGES
// ============================================================================
function updateClocksAndCountdown() {
  const now = new Date();
  const utcMs = now.getTime() + now.getTimezoneOffset() * 60000;
  const utc7 = new Date(utcMs + 7 * 3600000);
  const hh = String(utc7.getHours()).padStart(2, "0");
  const mm = String(utc7.getMinutes()).padStart(2, "0");
  const ss = String(utc7.getSeconds()).padStart(2, "0");

  if (el("headerTime")) el("headerTime").textContent = `${hh}:${mm}:${ss} UTC+7`;

  const tfSecMap = { "1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400 };
  const periodSec = tfSecMap[currentTf] || 3600;
  const nowSec = Math.floor(now.getTime() / 1000);
  const rem = periodSec - (nowSec % periodSec);
  const rHr = Math.floor(rem / 3600);
  const rMin = String(Math.floor((rem % 3600) / 60)).padStart(2, "0");
  const rSec = String(rem % 60).padStart(2, "0");

  if (el("countdownTimer")) {
    el("countdownTimer").textContent = rHr > 0 ? `${rHr}h ${rMin}m` : `${rMin}:${rSec}`;
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
      kzEl.textContent = "LDN+NY Overlap";
      kzEl.style.color = "var(--buy)";
    } else if (londonOpen) {
      kzEl.textContent = "London Active";
      kzEl.style.color = "var(--gold-bright)";
    } else if (nyOpen) {
      kzEl.textContent = "NY Active";
      kzEl.style.color = "var(--gold-bright)";
    } else {
      kzEl.textContent = "Asia Session";
      kzEl.style.color = "var(--blue)";
    }
  }
}

// ============================================================================
// 3. LIVE TICK POLLING & MULTI-BROKER TICKER
// ============================================================================
async function pollLiveTick() {
  try {
    const res = await fetch(`${API_BASE}/api/tick?symbol=${encodeURIComponent(currentSymbol)}`);
    const tick = await res.json();
    if (!tick || !tick.active) return;

    const price = tick.active.price;
    if (el("headerPrice")) el("headerPrice").textContent = `$${price.toFixed(2)}`;
    if (el("headerBrokerLabel")) {
      el("headerBrokerLabel").textContent = currentSymbol.split(":")[0];
    }

    const boxEl = el("headerPriceBox");
    if (lastTickPrice !== null && price !== lastTickPrice && boxEl) {
      boxEl.classList.remove("flash-up", "flash-down");
      void boxEl.offsetWidth;
      boxEl.classList.add(price > lastTickPrice ? "flash-up" : "flash-down");
      setTimeout(() => boxEl.classList.remove("flash-up", "flash-down"), 400);
    }
    lastTickPrice = price;

    const chg = tick.active.change_abs || 0;
    const chgPct = tick.active.change_pct || 0;
    const chgEl = el("headerChange");
    if (chgEl) {
      chgEl.textContent = `${chg >= 0 ? "+" : ""}${chgPct.toFixed(2)}%`;
      chgEl.style.color = chg >= 0 ? "var(--buy)" : "var(--sell)";
    }

    if (tick.brokers) {
      latestTickBrokers = tick.brokers;
      renderBrokerPills(tick.brokers);
      renderTerminalWatchlist();
    }

    if (customAlertPrice && Math.abs(price - customAlertPrice) <= 1.2) {
      showToast(`🔔 Alert: ${currentSymbol} reached $${price.toFixed(2)}!`);
      customAlertPrice = null;
      if (el("activeAlertStatus")) el("activeAlertStatus").textContent = "Triggered!";
    }

    if (currentData) {
      currentData.current_price = price;
      if (currentData.series && currentData.series.candles && currentData.series.candles.length) {
        const lastC = currentData.series.candles[currentData.series.candles.length - 1];
        lastC.close = price;
        if (price > lastC.high) lastC.high = price;
        if (price < lastC.low) lastC.low = price;
        if (currentView === "terminal") drawCharts();
      }
      updateBentoKpis();
    }
  } catch (e) {}
}

function renderBrokerPills(brokers) {
  const wrap = el("brokerPills");
  if (!wrap) return;
  const labels = {
    "OANDA:XAUUSD": "OANDA",
    "FX:XAUUSD": "FXCM",
    "FOREXCOM:XAUUSD": "FOREX",
    "TVC:DXY": "DXY"
  };
  const items = [];
  Object.keys(labels).forEach((sym) => {
    const b = brokers[sym];
    if (!b) return;
    const isUp = (b.change_pct || 0) >= 0;
    const col = isUp ? "var(--buy)" : "var(--sell)";
    const fmtPrice = sym === "TVC:DXY" ? b.price.toFixed(2) : `$${b.price.toFixed(2)}`;
    items.push(`
      <span class="broker-pill">
        <span style="color:var(--text-2);">${labels[sym]}</span>
        <strong style="color:var(--text-0);">${fmtPrice}</strong>
        <span style="color:${col};">${isUp ? "+" : ""}${(b.change_pct || 0).toFixed(2)}%</span>
      </span>
    `);
  });
  if (items.length) wrap.innerHTML = items.join("");
}

// ============================================================================
// 4. FULL DASHBOARD SYNC
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

    renderMainSignal(data);
    renderAiAgentLayer(data.ai_agent);
    renderTelegramStatus(tgData);
    renderFundamentals(data.fundamentals);
    renderMtf(mtfData.mtf || {}, mtfData.mtf_order || ["15m", "1h", "4h", "1d"]);
    updatePositionSizer();
    renderTerminalWatchlist();

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

    if (currentView === "terminal") drawCharts();
  } catch (err) {
    console.error("Sync error:", err);
  }
}

// ============================================================================
// 5. MINIMALIST 4-CARD KPI STRIP & OVERVIEW SIGNAL
// ============================================================================
function updateBentoKpis() {
  const d = currentData;
  const bt = selectedRunDetail || (d && d.backtest) || null;

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
    if (el("kpiWinRate")) {
      el("kpiWinRate").textContent = `${bt.win_rate || 0}%`;
      el("kpiWinRate").style.color = (bt.win_rate || 0) >= 50 ? "var(--buy)" : "var(--gold-bright)";
    }
    if (el("kpiTotalNetPnl")) {
      el("kpiTotalNetPnl").textContent = `${netPts >= 0 ? "+" : ""}${netPts.toFixed(1)} pts (${bt.total_trades || 0}T)`;
    }
    if (el("kpiProfitFactorBadge")) {
      el("kpiProfitFactorBadge").textContent = `PF ${bt.profit_factor || "--"}`;
    }
  }

  if (d) {
    if (el("kpiSignalShort")) {
      el("kpiSignalShort").textContent = `${d.direction} (${d.confidence}%)`;
      el("kpiSignalShort").style.color =
        d.direction === "BUY" ? "var(--buy)" : d.direction === "SELL" ? "var(--sell)" : "var(--gold-bright)";
    }
    if (el("kpiSignalEntrySub")) {
      el("kpiSignalEntrySub").textContent = `Entry $${d.entry.toFixed(2)}`;
    }

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
      if (el("kpiActivePosSub")) el("kpiActivePosSub").textContent = `Locked #${at.id} ${at.direction}`;
      if (el("kpiActivePosBadge")) el("kpiActivePosBadge").textContent = "LOCKED";
    } else {
      if (el("kpiUnrealizedPnl")) {
        el("kpiUnrealizedPnl").textContent = `${d.timeframe} Ready`;
        el("kpiUnrealizedPnl").style.color = "var(--text-2)";
      }
      if (el("kpiActivePosSub")) el("kpiActivePosSub").textContent = "0 Open Trades";
      if (el("kpiActivePosBadge")) el("kpiActivePosBadge").textContent = "READY";
    }

    if (d.ai_agent) {
      if (el("kpiAiVerdictShort")) {
        el("kpiAiVerdictShort").textContent = d.ai_agent.verdict || "READY";
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

    if (d.fundamentals?.dxy?.price > 0 && el("kpiDxyPrice")) {
      el("kpiDxyPrice").textContent = `DXY ${d.fundamentals.dxy.price.toFixed(2)} (${d.fundamentals.dxy.gold_impact})`;
    }
  }
}

function renderMainSignal(d) {
  if (el("headerPrice")) el("headerPrice").textContent = `$${d.current_price.toFixed(2)}`;
  if (el("activeTfLabel")) el("activeTfLabel").textContent = `${d.trading_style} · ${d.timeframe}`;
  if (el("activeStyleBadgeHeader")) {
    el("activeStyleBadgeHeader").textContent = `${d.trading_style} · ${d.timeframe}`;
  }
  if (el("chartHeaderSymTf")) {
    el("chartHeaderSymTf").textContent = `${d.symbol} · ${d.timeframe} (${d.trading_style})`;
  }

  const isBull = d.indicators.ema21 >= d.indicators.ema50;
  if (el("regimeBadge")) {
    el("regimeBadge").className = `pill ${isBull ? "BUY" : "SELL"}`;
    el("regimeBadge").textContent = isBull ? "BULLISH EMA" : "BEARISH EMA";
  }

  // Lock Banner
  const pl = d.position_lock || {};
  const lockBanner = el("lockBanner");
  const lockTitle = el("lockTitle");
  const lockReason = el("lockReason");
  const closeBtn = el("closePosBtn");

  if (pl.locked && pl.active_trade) {
    const at = pl.active_trade;
    if (lockBanner) lockBanner.className = "lock-banner locked";
    if (lockTitle) {
      lockTitle.textContent = `🔒 Locked #${at.id}:`;
      lockTitle.style.color = "var(--gold-bright)";
    }
    if (lockReason) {
      lockReason.innerHTML = `${at.direction} @ $${at.entry_price.toFixed(2)} · SL $${at.sl_price.toFixed(2)} · TP1 $${at.tp1_price.toFixed(2)}`;
    }
    if (closeBtn) closeBtn.style.display = "inline-flex";
  } else {
    if (lockBanner) lockBanner.className = "lock-banner";
    if (lockTitle) {
      lockTitle.textContent = "🛡️ Scanner Ready:";
      lockTitle.style.color = "var(--blue)";
    }
    if (lockReason) {
      lockReason.textContent = `0 Open Positions on ${d.timeframe}.`;
    }
    if (closeBtn) closeBtn.style.display = "none";
  }

  // Signal Badge
  const dir = d.direction === "BUY" ? "BUY" : d.direction === "SELL" ? "SELL" : "NEUTRAL";
  if (el("signalBadge")) el("signalBadge").className = `signal-badge ${dir}`;
  if (el("signalDir")) el("signalDir").textContent = d.direction;
  if (el("signalConf")) el("signalConf").textContent = `${d.confidence}% Conf`;
  if (el("signalSubType")) el("signalSubType").textContent = d.signal;

  const activeTrade = pl.locked && pl.active_trade ? pl.active_trade : null;
  const dispEntry = activeTrade ? activeTrade.entry_price : d.entry;
  const dispSl = activeTrade ? activeTrade.sl_price : d.stop_loss;
  const dispTp1 = activeTrade ? activeTrade.tp1_price : d.take_profit_1;
  const dispTp2 = activeTrade ? activeTrade.tp2_price : d.take_profit_2;

  const riskPts = Math.abs(dispEntry - dispSl);
  const tp1Pts = Math.abs(dispTp1 - dispEntry);
  const tp2Pts = Math.abs(dispTp2 - dispEntry);
  const rr1 = riskPts > 0 ? (tp1Pts / riskPts).toFixed(1) : "--";
  const rr2 = riskPts > 0 ? (tp2Pts / riskPts).toFixed(1) : "--";

  if (el("lvlEntry")) el("lvlEntry").textContent = `$${dispEntry.toFixed(2)}`;
  if (el("lvlSpread")) el("lvlSpread").textContent = activeTrade ? `Locked #${activeTrade.id}` : "Spot Ref";
  if (el("lvlSL")) el("lvlSL").textContent = `$${dispSl.toFixed(2)}`;
  if (el("lvlRisk")) el("lvlRisk").textContent = `${riskPts.toFixed(1)} pts (${d.sl_mult}x ATR)`;
  if (el("lvlTP1")) el("lvlTP1").textContent = `$${dispTp1.toFixed(2)}`;
  if (el("lvlRR1")) el("lvlRR1").textContent = `R:R 1:${rr1}`;
  if (el("lvlTP2")) el("lvlTP2").textContent = `$${dispTp2.toFixed(2)}`;
  if (el("lvlRR2")) el("lvlRR2").textContent = `R:R 1:${rr2}`;

  if (el("rationaleBox")) el("rationaleBox").textContent = d.rationale;

  // Compact Checklist Pills (Minimalist, zero clutter)
  const cGrid = el("checklistGrid");
  if (cGrid) {
    cGrid.innerHTML = (d.checklist || [])
      .map(
        (item) => `
        <span class="check-pill ${item.passed ? "pass" : ""}" title="${escapeHtml(item.detail)}">
          <b style="color:${item.passed ? "var(--buy)" : "var(--text-2)"};">${item.passed ? "✓" : "○"}</b>
          <span>${escapeHtml(item.name)}</span>
        </span>
      `
      )
      .join("");
  }

  if (d.pivots) {
    if (el("pivP")) el("pivP").textContent = `$${d.pivots.pivot.toFixed(2)}`;
    if (el("pivR1S1")) el("pivR1S1").textContent = `R1 $${d.pivots.r1.toFixed(0)} · S1 $${d.pivots.s1.toFixed(0)}`;
  }
  if (d.ai_agent && el("vwapVal")) el("vwapVal").textContent = d.ai_agent.watch_zone || "--";
  if (d.indicators) {
    if (el("bbWidthVal")) el("bbWidthVal").textContent = `RSI ${d.indicators.rsi14.toFixed(1)}`;
    if (el("atrVal")) el("atrVal").textContent = `$${d.indicators.atr14.toFixed(2)}`;
    if (el("emaRibbonVal")) {
      el("emaRibbonVal").textContent = `${d.indicators.ema21.toFixed(0)} / ${d.indicators.ema50.toFixed(0)}`;
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
        <td>${item.confidence}%</td>
        <td style="color:${isBull ? "var(--buy)" : "var(--sell)"};font-weight:700;">${isBull ? "▲ Bull" : "▼ Bear"}</td>
        <td>${item.rsi14.toFixed(1)}</td>
        <td>$${item.entry.toFixed(1)}</td>
        <td style="color:var(--sell);">$${item.stop_loss.toFixed(1)}</td>
        <td style="color:var(--buy);">$${item.take_profit_1.toFixed(1)}</td>
      </tr>
    `);
  });

  tbody.innerHTML = rows.join("");

  const badge = el("mtfAlignmentBadge");
  if (badge) {
    const total = mtfOrder.length || 1;
    if (bullCount >= total - 1) {
      badge.className = "pill BUY";
      badge.textContent = `BULLISH (${bullCount}/${total})`;
    } else if (bearCount >= total - 1) {
      badge.className = "pill SELL";
      badge.textContent = `BEARISH (${bearCount}/${total})`;
    } else {
      badge.className = "pill NEUTRAL";
      badge.textContent = `MIXED (${bullCount}B/${bearCount}S)`;
    }
  }
}

// ============================================================================
// 6. AI & MACRO VIEW
// ============================================================================
function renderAiAgentLayer(ai) {
  if (!ai) return;
  if (el("aiModelUsedBadge")) el("aiModelUsedBadge").textContent = ai.engine;
  if (el("aiVerdictTitle")) {
    el("aiVerdictTitle").textContent = `${ai.verdict_badge} (${ai.adjusted_confidence}%)`;
  }
  if (el("fibGoldenBadge")) {
    el("fibGoldenBadge").textContent = `Golden Pocket: ${ai.watch_zone}`;
  }
  if (el("aiExecSummary")) el("aiExecSummary").textContent = ai.executive_summary;

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
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <strong style="font-size:11.5px;color:var(--text-0);">${escapeHtml(ag.name)}</strong>
            <span class="tabular" style="font-size:10px;font-weight:800;color:${col};">${escapeHtml(ag.bias)} · ${ag.score}%</span>
          </div>
          <div class="agent-progress">
            <div class="agent-progress-bar" style="width:${Math.min(100, Math.max(10, ag.score))}%;background:${col};"></div>
          </div>
          <div style="font-size:11px;color:var(--text-1);">${escapeHtml(ag.note)}</div>
        </div>
      `;
    })
    .join("");
}

function renderFundamentals(f) {
  if (!f) return;
  const biasEl = el("fundBiasVal");
  if (biasEl) {
    biasEl.textContent = `${f.bias} (${f.score >= 0 ? "+" : ""}${f.score})`;
    biasEl.style.color = f.bias === "BULLISH" ? "var(--buy)" : f.bias === "BEARISH" ? "var(--sell)" : "var(--gold-bright)";
  }
  if (el("fundScoreSub")) {
    el("fundScoreSub").textContent = `${f.bullish_headlines} Bull / ${f.bearish_headlines} Bear`;
  }
  if (f.dxy && f.dxy.price > 0) {
    if (el("fundDxyPrice")) el("fundDxyPrice").textContent = `${f.dxy.price.toFixed(2)} (${f.dxy.change_pct >= 0 ? "+" : ""}${f.dxy.change_pct.toFixed(2)}%)`;
    if (el("fundDxyImpact")) el("fundDxyImpact").textContent = `Gold Impact: ${f.dxy.gold_impact}`;
  }
  if (el("fundSummaryText")) el("fundSummaryText").textContent = f.summary;

  const evPill = el("eventAlertPill");
  if (evPill) {
    if (f.high_impact_events && f.high_impact_events.length > 0) {
      evPill.style.display = "inline-block";
      evPill.textContent = `⚡ ${f.high_impact_events.join(" · ")}`;
    } else {
      evPill.style.display = "none";
    }
  }

  if (el("newsCountLabel")) el("newsCountLabel").textContent = `${(f.headlines || []).length} stories`;
  const nList = el("newsList");
  if (nList) {
    nList.innerHTML = (f.headlines || [])
      .map((h) => {
        const titleHtml = h.story_url
          ? `<a href="${h.story_url}" target="_blank" style="color:var(--text-0);text-decoration:none;font-weight:600;font-size:11.5px;">${escapeHtml(h.title)}</a>`
          : `<span style="font-weight:600;font-size:11.5px;">${escapeHtml(h.title)}</span>`;
        return `
          <div class="news-item">
            <div style="min-width:0;flex:1;">
              <div style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${titleHtml}</div>
              <div style="font-size:9.5px;color:var(--text-2);">${escapeHtml(h.source)} · ${escapeHtml(h.published)}</div>
            </div>
            <span class="news-tag ${escapeHtml(h.sentiment)}">${escapeHtml(h.sentiment)}</span>
          </div>
        `;
      })
      .join("");
  }
}

// ============================================================================
// 7. TERMINAL VIEW (WATCHLIST, CHART & PAPER SIZER)
// ============================================================================
function renderTerminalWatchlist() {
  const container = el("terminalWatchlistContainer");
  if (!container) return;
  const query = (el("watchlistSearchInput")?.value || "").trim().toUpperCase();

  const b = latestTickBrokers || {};
  const oanda = b["OANDA:XAUUSD"] || { price: currentData?.current_price || 4748.0, change_pct: 0.12 };
  const fx = b["FX:XAUUSD"] || { price: oanda.price, change_pct: oanda.change_pct };
  const forex = b["FOREXCOM:XAUUSD"] || { price: oanda.price, change_pct: oanda.change_pct };
  const dxy = b["TVC:DXY"] || { price: currentData?.fundamentals?.dxy?.price || 98.81, change_pct: 0.04 };

  const items = [
    { symbol: "OANDA:XAUUSD", name: "Gold · OANDA", price: `$${oanda.price.toFixed(2)}`, chg: oanda.change_pct || 0, selectable: true, mode: "LIVE" },
    { symbol: "FX:XAUUSD", name: "Gold · FXCM", price: `$${fx.price.toFixed(2)}`, chg: fx.change_pct || 0, selectable: true, mode: "LIVE" },
    { symbol: "FOREXCOM:XAUUSD", name: "Gold · FOREX", price: `$${forex.price.toFixed(2)}`, chg: forex.change_pct || 0, selectable: true, mode: "LIVE" },
    { symbol: "TVC:DXY", name: "US Dollar Index", price: dxy.price.toFixed(2), chg: dxy.change_pct || 0, selectable: false, mode: "LIVE" },
    { symbol: "XAG/USD", name: "Silver Spot", price: "$33.42", chg: 0.42, selectable: false, mode: "SIM" },
    { symbol: "US10Y", name: "US 10Y Yield", price: "4.28%", chg: -0.18, selectable: false, mode: "SIM" }
  ].filter((i) => !query || i.symbol.includes(query) || i.name.toUpperCase().includes(query));

  container.innerHTML = items
    .map((item) => {
      const isUp = item.chg >= 0;
      return `
        <div class="watchlist-item ${item.symbol === currentSymbol ? "active" : ""}" data-sym="${item.symbol}" data-sel="${item.selectable}">
          <div style="min-width:0;">
            <div class="watchlist-sym">${escapeHtml(item.symbol.replace(":XAUUSD", ""))}</div>
            <div style="font-size:9.5px;color:var(--text-2);">${escapeHtml(item.name)}</div>
          </div>
          <div style="text-align:right;">
            <div class="watchlist-price">${item.price}</div>
            <div class="tabular" style="font-size:10px;color:${isUp ? "var(--buy)" : "var(--sell)"};font-weight:700;">
              ${isUp ? "+" : ""}${item.chg.toFixed(2)}%
            </div>
          </div>
        </div>
      `;
    })
    .join("");

  container.querySelectorAll(".watchlist-item").forEach((row) => {
    row.addEventListener("click", () => {
      if (row.dataset.sel === "true" && row.dataset.sym !== currentSymbol) {
        const nextSym = row.dataset.sym;
        openConfirmDialog({
          title: "Switch Broker Feed",
          badge: "FEED",
          desc: `Switch live terminal feed to ${nextSym}?`,
          meta: `Current: ${currentSymbol} → Target: ${nextSym}`,
          confirmLabel: "Switch Feed ↵",
          onConfirm: () => {
            currentSymbol = nextSym;
            if (el("symbolSelect")) el("symbolSelect").value = nextSym;
            selectedRunDetail = null;
            fetchFullDashboard();
            pollLiveTick();
            showToast(`Switched feed to ${nextSym}`);
          }
        });
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
      currentData.direction === "BUY" ? "var(--buy)" : currentData.direction === "SELL" ? "var(--sell)" : "var(--gold-bright)";
  }
  if (el("ticketStopDistLbl")) el("ticketStopDistLbl").textContent = `${stopDist.toFixed(1)} pts`;
  if (el("calcDollarRisk")) el("calcDollarRisk").textContent = `$${dollarRisk.toFixed(2)}`;
  if (el("calcOuncesSize")) el("calcOuncesSize").textContent = `${ounces.toFixed(2)} oz`;
  if (el("calcLotSize")) el("calcLotSize").textContent = `${lots.toFixed(2)} lots`;
}

// ============================================================================
// 8. CHART & OSCILLATOR ENGINE
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
  const gridColor = isLight ? "rgba(148, 163, 184, 0.25)" : "rgba(30, 41, 59, 0.55)";
  const textColor = isLight ? "#475569" : "#94a3b8";

  const dpr = window.devicePixelRatio || 1;
  const rect = priceCanvas.getBoundingClientRect();
  const width = rect.width || 800;
  const height = 360;
  priceCanvas.width = width * dpr;
  priceCanvas.height = height * dpr;
  const ctx = priceCanvas.getContext("2d");
  ctx.scale(dpr, dpr);

  ctx.fillStyle = canvasBg;
  ctx.fillRect(0, 0, width, height);

  const padLeft = 12, padRight = 68, padTop = 16, padBottom = 22;
  const plotW = width - padLeft - padRight;
  const plotH = height - padTop - padBottom;

  let minP = Infinity, maxP = -Infinity;
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
    ctx.font = "10.5px JetBrains Mono, monospace";
    ctx.fillText(pVal.toFixed(1), width - padRight + 5, y + 3);
  }

  if (showBB) {
    ctx.strokeStyle = "rgba(148, 163, 184, 0.3)";
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
    ctx.fillRect(xCenter - candleW / 2, Math.min(yOpen, yClose), candleW, Math.max(1.5, Math.abs(yClose - yOpen)));
  });

  const drawLine = (arr, color) => {
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    arr.forEach((val, idx) => {
      const x = padLeft + idx * stepX + stepX / 2;
      const y = yOf(val);
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  };
  drawLine(s.ema9, "#38bdf8");
  drawLine(s.ema21, "#f5c451");
  drawLine(s.ema50, "#a855f7");

  if (showSignalLines) {
    const pl = currentData.position_lock || {};
    const at = pl.locked && pl.active_trade ? pl.active_trade : null;
    const levels = [
      { val: at ? at.entry_price : currentData.entry, col: "#f5c451", lbl: "ENTRY" },
      { val: at ? at.sl_price : currentData.stop_loss, col: "#f43f5e", lbl: "SL" },
      { val: at ? at.tp1_price : currentData.take_profit_1, col: "#00d4aa", lbl: "TP1" },
      { val: at ? at.tp2_price : currentData.take_profit_2, col: "#38bdf8", lbl: "TP2" }
    ];
    levels.forEach((lv) => {
      const y = yOf(lv.val);
      ctx.strokeStyle = lv.col;
      ctx.lineWidth = 1.1;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(padLeft, y);
      ctx.lineTo(width - padRight, y);
      ctx.stroke();
      ctx.setLineDash([]);

      ctx.fillStyle = lv.col;
      ctx.font = "bold 9.5px Inter, sans-serif";
      ctx.fillText(`${lv.lbl} $${lv.val.toFixed(1)}`, padLeft + 5, y - 3);
    });
  }

  drawOscillator(width, dpr, stepX, padLeft, padRight, canvasBg, textColor);
}

function drawOscillator(width, dpr, stepX, padLeft, padRight, canvasBg, textColor) {
  const oscCanvas = el("oscCanvas");
  if (!oscCanvas || !currentData || !currentData.series) return;
  const s = currentData.series;
  const height = 110;
  oscCanvas.width = width * dpr;
  oscCanvas.height = height * dpr;
  const ctx = oscCanvas.getContext("2d");
  ctx.scale(dpr, dpr);

  ctx.fillStyle = canvasBg;
  ctx.fillRect(0, 0, width, height);

  const padTop = 14, padBottom = 14;
  const plotH = height - padTop - padBottom;

  if (oscMode === "RSI") {
    const yOf = (v) => padTop + plotH * (1 - v / 100);
    [70, 50, 30].forEach((lv) => {
      const y = yOf(lv);
      ctx.strokeStyle = "rgba(148,163,184,0.22)";
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(padLeft, y);
      ctx.lineTo(width - padRight, y);
      ctx.stroke();
      ctx.setLineDash([]);
    });

    ctx.strokeStyle = "#38bdf8";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    s.rsi14.forEach((v, idx) => {
      const x = padLeft + idx * stepX + stepX / 2;
      const y = yOf(v);
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    ctx.fillStyle = textColor;
    ctx.font = "bold 9.5px Inter, sans-serif";
    ctx.fillText(`RSI(14): ${s.rsi14[s.rsi14.length - 1].toFixed(1)}`, padLeft + 5, 11);
  } else {
    const allVals = [...s.macd, ...s.macd_signal, ...s.macd_hist];
    const maxAbs = Math.max(...allVals.map((v) => Math.abs(v)), 0.5) * 1.15;
    const yOf = (v) => padTop + plotH * (0.5 - v / (2 * maxAbs));
    const yZero = yOf(0);

    const barW = Math.max(2, stepX * 0.55);
    s.macd_hist.forEach((v, idx) => {
      const x = padLeft + idx * stepX + stepX / 2;
      const y = yOf(v);
      ctx.fillStyle = v >= 0 ? "rgba(0, 212, 170, 0.5)" : "rgba(244, 63, 94, 0.5)";
      ctx.fillRect(x - barW / 2, Math.min(y, yZero), barW, Math.max(1, Math.abs(y - yZero)));
    });

    ctx.fillStyle = textColor;
    ctx.font = "bold 9.5px Inter, sans-serif";
    ctx.fillText(`MACD Hist: ${s.macd_hist[s.macd_hist.length - 1].toFixed(2)}`, padLeft + 5, 11);
  }
}

// ============================================================================
// 9. BACKTEST & TABBED LEDGER VIEW
// ============================================================================
function renderBacktestRunsList(runs) {
  const sel = el("savedRunsSelect");
  if (!sel) return;
  if (!runs || !runs.length) {
    sel.innerHTML = `<option value="">No saved runs</option>`;
    return;
  }
  sel.innerHTML = runs
    .map((r) => {
      const isSelected = selectedRunDetail && selectedRunDetail.id === r.id ? "selected" : "";
      const sign = r.net_pnl_pts >= 0 ? "+" : "";
      return `<option value="${r.id}" ${isSelected}>Run #${r.id} · ${r.symbol} (${r.timeframe}) · ${r.total_trades}T · Win ${r.win_rate}% · ${sign}${r.net_pnl_pts.toFixed(1)} pts</option>`;
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
  } catch (e) {}
}

function renderSelectedBacktest(bt) {
  if (!bt) return;
  if (el("btWinRate")) el("btWinRate").textContent = `${bt.win_rate}%`;
  if (el("btWinLossCount")) el("btWinLossCount").textContent = `${bt.wins}W / ${bt.losses}L`;
  if (el("btNetPnl")) {
    el("btNetPnl").textContent = `${bt.net_pnl_pts >= 0 ? "+" : ""}${bt.net_pnl_pts.toFixed(1)} pts`;
    el("btNetPnl").style.color = bt.net_pnl_pts >= 0 ? "var(--buy)" : "var(--sell)";
  }
  if (el("btTotalTrades")) el("btTotalTrades").textContent = `${bt.total_trades} trades (${bt.bars_tested} bars)`;
  if (el("btProfitFactor")) el("btProfitFactor").textContent = String(bt.profit_factor);
  if (el("btExpectancy")) el("btExpectancy").textContent = `Exp ${bt.expectancy_pts >= 0 ? "+" : ""}${bt.expectancy_pts.toFixed(2)} pts`;
  if (el("btMaxDD")) el("btMaxDD").textContent = `-${bt.max_drawdown_pts.toFixed(1)} pts`;
  if (el("btAvgWinLoss")) el("btAvgWinLoss").textContent = `+${bt.avg_win.toFixed(1)} / -${bt.avg_loss.toFixed(1)}`;
  if (el("eqCurveSubtitle")) el("eqCurveSubtitle").textContent = `Run #${bt.id} (${bt.timeframe})`;

  const total = Math.max(bt.total_trades || 1, 1);
  const winPct = Math.round(((bt.wins || 0) / total) * 100);
  if (el("wlWinLabel")) el("wlWinLabel").textContent = `Wins: ${bt.wins} (${winPct}%)`;
  if (el("wlLossLabel")) el("wlLossLabel").textContent = `Losses: ${bt.losses} (${100 - winPct}%)`;
  if (el("wlWinBar")) el("wlWinBar").style.width = `${winPct}%`;
  if (el("wlLossBar")) el("wlLossBar").style.width = `${100 - winPct}%`;

  const trades = bt.trades || [];
  if (el("wlTp2Count")) el("wlTp2Count").textContent = String(trades.filter((t) => t.outcome?.includes("TP2")).length);
  if (el("wlTp1Count")) el("wlTp1Count").textContent = String(trades.filter((t) => t.outcome?.includes("TP1")).length);
  if (el("wlSlCount")) el("wlSlCount").textContent = String(trades.filter((t) => t.outcome?.includes("LOSS")).length);

  const tbody = el("btTradesBody");
  if (tbody) {
    tbody.innerHTML = trades.length
      ? trades
          .map((t) => {
            const isWin = t.outcome && t.outcome.startsWith("WIN");
            const sEntry = (t.entry_time || "").replace(" UTC+7", "").slice(5);
            const sExit = (t.exit_time || "").replace(" UTC+7", "").slice(11);
            return `
              <tr>
                <td>${escapeHtml(sEntry)} → ${escapeHtml(sExit)}</td>
                <td><span class="pill ${t.direction === "BUY" ? "BUY" : "SELL"}">${escapeHtml(t.direction)}</span></td>
                <td>${escapeHtml(t.signal_type)}</td>
                <td>$${t.entry_price.toFixed(1)} → $${t.exit_price.toFixed(1)}</td>
                <td>$${t.sl_price.toFixed(1)} / $${t.tp1_price.toFixed(1)}</td>
                <td><span class="pill ${isWin ? "BUY" : "SELL"}">${escapeHtml(t.outcome)}</span></td>
                <td style="font-weight:800;color:${t.pnl_pts >= 0 ? "var(--buy)" : "var(--sell)"};">
                  ${t.pnl_pts >= 0 ? "+" : ""}${t.pnl_pts.toFixed(2)}
                </td>
              </tr>
            `;
          })
          .join("")
      : `<tr><td colspan="7" style="text-align:center;color:var(--text-2);padding:14px;">No trades found.</td></tr>`;
  }

  if (currentView === "backtest") drawEquityCurve(bt.equity_curve || []);
}

function drawEquityCurve(eqPoints) {
  const equityCanvas = el("equityCanvas");
  if (!equityCanvas) return;

  const isLight = document.documentElement.getAttribute("data-theme") === "light";
  const canvasBg = isLight ? "#f8fafc" : "#080b12";

  const dpr = window.devicePixelRatio || 1;
  const rect = equityCanvas.getBoundingClientRect();
  const width = rect.width || 560;
  const height = 165;
  equityCanvas.width = width * dpr;
  equityCanvas.height = height * dpr;
  const ctx = equityCanvas.getContext("2d");
  ctx.scale(dpr, dpr);

  ctx.fillStyle = canvasBg;
  ctx.fillRect(0, 0, width, height);

  if (!eqPoints || !eqPoints.length) return;

  const padL = 12, padR = 54, padT = 14, padB = 16;
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

  const lastVal = vals[vals.length - 1];
  ctx.strokeStyle = lastVal >= 0 ? "#00d4aa" : "#f43f5e";
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
  ctx.font = "10px monospace";
  ctx.fillText(`+${maxV.toFixed(0)}`, width - padR + 5, padT + 8);
  ctx.fillText(`${minV.toFixed(0)}`, width - padR + 5, height - padB);
}

function renderLiveSignalsTable(signals) {
  const tbody = el("liveSignalsBody");
  if (!tbody) return;
  tbody.innerHTML = (signals || []).length
    ? signals
        .map((s) => {
          const isBuy = s.direction === "BUY";
          const pnl = s.pnl_pts || 0;
          return `
            <tr>
              <td>${escapeHtml((s.candle_time || "").replace(" UTC+7", "").slice(5))}</td>
              <td><strong style="color:var(--gold-bright);">${escapeHtml(s.trading_style || "SWING")}</strong> · ${escapeHtml(s.timeframe)}</td>
              <td><span class="pill ${isBuy ? "BUY" : "SELL"}">${escapeHtml(s.direction)}</span></td>
              <td>$${s.entry_price.toFixed(1)}</td>
              <td>$${s.sl_price.toFixed(1)} / $${s.tp1_price.toFixed(1)}</td>
              <td style="color:var(--ai-accent);font-weight:700;">${escapeHtml(s.ai_verdict || "APPROVED")}</td>
              <td>${escapeHtml(s.status)} ${pnl !== 0 ? `(${pnl > 0 ? "+" : ""}${pnl.toFixed(1)})` : ""}</td>
            </tr>
          `;
        })
        .join("")
    : `<tr><td colspan="7" style="text-align:center;color:var(--text-2);padding:14px;">No signals recorded.</td></tr>`;
}

// ============================================================================
// 10. TELEGRAM HUB, COPILOT, STRATEGY LAB & SETTINGS
// ============================================================================
function renderTelegramStatus(tg) {
  if (!tg) return;
  const badge = el("tgBotStatusBadge");
  if (tg.bot && tg.bot.ok) {
    if (badge) {
      badge.className = "pill BUY";
      badge.textContent = `ONLINE · @${tg.bot.username}`;
    }
  } else if (badge) {
    badge.className = "pill SELL";
    badge.textContent = "OFFLINE";
  }

  if (el("tgAutoNotifyChk")) el("tgAutoNotifyChk").checked = Boolean(tg.auto_notify);

  const subs = tg.subscribers || [];
  latestTgSubscribersCount = subs.length;
  if (el("tgSubCount")) el("tgSubCount").textContent = String(subs.length);
  if (el("navTgCountBadge")) el("navTgCountBadge").textContent = `${subs.length} CHAT`;

  const subBox = el("tgSubscribersList");
  if (subBox) {
    subBox.innerHTML = subs.length
      ? subs
          .map(
            (s) => `
          <div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid var(--border-subtle);">
            <div style="min-width:0;">
              <strong style="color:var(--buy);">${escapeHtml(s.first_name || "Chat")}</strong>
              <span class="tabular" style="color:var(--text-2);margin-left:6px;">${escapeHtml(s.chat_id)}</span>
            </div>
            <span class="pill NEUTRAL">${escapeHtml(s.chat_type || "chat")}</span>
          </div>
        `
          )
          .join("")
      : "No chats subscribed yet. Send <code>/start</code> to @this_is_ai_signal_bot.";
  }

  const logs = tg.logs || [];
  const logBox = el("tgLogsList");
  if (logBox) {
    logBox.innerHTML = logs.length
      ? logs
          .map((l) => {
            const preview = escapeHtml(l.message_preview || "").replace(/\s+/g, " ").trim();
            return `
              <div style="padding:6px 0;border-bottom:1px solid var(--border-subtle);">
                <div style="display:flex;justify-content:space-between;margin-bottom:2px;">
                  <span style="color:${l.ok ? "var(--buy)" : "var(--sell)"};font-weight:700;">${escapeHtml(l.event_type)}</span>
                  <span class="tabular" style="color:var(--text-2);font-size:10px;">${escapeHtml((l.sent_at || "").slice(11, 19))}</span>
                </div>
                <div style="color:var(--text-1);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${preview}</div>
              </div>
            `;
          })
          .join("")
      : "No recent deliveries.";
  }
}

function renderStrategyLab() {
  const grid = el("strategyLabGrid");
  if (!grid) return;

  const blueprints = [
    { id: "SWING_GOLDEN_POCKET", name: "Swing Golden Pocket ★", style: "SWING", tf: "1h", sl: 1.5, tp1: 2.5, tp2: 4.0, desc: "1H Fibonacci 38.2%–61.8% + EMA 21/50 alignment." },
    { id: "PRO_TREND_PULLBACK", name: "Intraday EMA Pullback", style: "INTRADAY", tf: "15m", sl: 1.2, tp1: 1.8, tp2: 3.0, desc: "15m London/NY killzone pullback into EMA 21." },
    { id: "LIQUIDITY_SWEEP_REVERSAL", name: "Bollinger Liquidity Sweep", style: "SCALPING", tf: "5m", sl: 1.0, tp1: 1.5, tp2: 2.2, desc: "5m exhaustion wick outside 2σ Bollinger + RSI." },
    { id: "MOMENTUM_BREAKOUT", name: "Macro Breakout Runner", style: "POSITION", tf: "4h", sl: 1.8, tp1: 3.0, tp2: 5.0, desc: "4H multi-day trend expansion with 50% TP1 lock." }
  ];

  grid.innerHTML = blueprints
    .map(
      (bp) => `
      <div class="strategy-preset-card" data-name="${escapeHtml(bp.name)}" data-style="${bp.style}" data-tf="${bp.tf}" data-sl="${bp.sl}" data-tp1="${bp.tp1}" data-tp2="${bp.tp2}" data-strat="${bp.id}">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:3px;">
          <strong style="font-size:12px;color:var(--text-0);">${escapeHtml(bp.name)}</strong>
          <span class="pill NEUTRAL">${bp.style} · ${bp.tf}</span>
        </div>
        <div style="font-size:11px;color:var(--text-1);margin-bottom:4px;">${escapeHtml(bp.desc)}</div>
        <div class="tabular" style="font-size:10px;color:var(--gold-bright);">SL ${bp.sl}x · TP1 ${bp.tp1}x · TP2 ${bp.tp2}x ATR</div>
      </div>
    `
    )
    .join("");

  grid.querySelectorAll(".strategy-preset-card").forEach((card) => {
    card.addEventListener("click", () => {
      const name = card.dataset.name;
      const st = card.dataset.style;
      const tf = card.dataset.tf;
      openConfirmDialog({
        title: "Apply Strategy Blueprint",
        badge: "PRESET",
        desc: `Load "${name}" parameters and recalculate signals?`,
        meta: `Style: ${st} (${tf})\nSL: ${card.dataset.sl}x ATR · TP1: ${card.dataset.tp1}x ATR · TP2: ${card.dataset.tp2}x ATR`,
        confirmLabel: "Apply Preset ↵",
        onConfirm: () => {
          if (el("btStrategySelect")) el("btStrategySelect").value = card.dataset.strat;
          if (el("btSlInput")) el("btSlInput").value = card.dataset.sl;
          if (el("btTp1Input")) el("btTp1Input").value = card.dataset.tp1;
          if (el("btTp2Input")) el("btTp2Input").value = card.dataset.tp2;
          applyTradingStyleDirect(st, tf);
        }
      });
    });
  });
}

function renderFeatureFlagsPanel() {
  const grid = el("featureFlagsGrid");
  if (!grid) return;
  const modules = [
    { name: "TradingView Multi-Broker Feed", mode: "LIVE", desc: "1.5s quotes across OANDA, FXCM, FOREX & DXY." },
    { name: "3-Agent AI Gate + Argon", mode: "LIVE", desc: "Technical + Macro + Risk pre-signal filter." },
    { name: "Single-Position Lock", mode: "LIVE", desc: "Prevents duplicate entries until TP/SL." },
    { name: "Supabase Cloud PostgreSQL", mode: "LIVE", desc: "Stores backtests, signals & Telegram chats." },
    { name: "Telegram Daemon (@this_is_ai_signal_bot)", mode: "LIVE", desc: "24/7 cloud polling & auto-broadcast." },
    { name: "Paper Order Sizer", mode: "PAPER", desc: "Safe simulated execution & lot calculator." }
  ];
  grid.innerHTML = modules
    .map(
      (m) => `
      <div class="stat-card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
          <strong style="font-size:11.5px;color:var(--text-0);">${escapeHtml(m.name)}</strong>
          <span class="mode-safety-pill ${m.mode === "LIVE" ? "live-lock" : "paper-sim"}">${m.mode}</span>
        </div>
        <div style="font-size:10.5px;color:var(--text-1);">${escapeHtml(m.desc)}</div>
      </div>
    `
    )
    .join("");
}

function generateCopilotReply(topic) {
  const d = currentData;
  if (!d) return "Syncing live XAU/USD data...";
  const q = topic.toLowerCase();
  const price = d.current_price.toFixed(2);
  const ai = d.ai_agent || {};
  const dxy = d.fundamentals?.dxy || {};

  if (q.includes("swing") || q.includes("golden")) {
    return `**${d.symbol} @ $${price} (${d.timeframe}):**\n• **Signal:** ${d.direction} (${d.confidence}%) · Golden Pocket: ${ai.watch_zone || "--"}\n• **Levels:** Entry $${d.entry.toFixed(2)} | SL $${d.stop_loss.toFixed(2)} | TP1 $${d.take_profit_1.toFixed(2)}.`;
  }
  if (q.includes("dxy") || q.includes("macro")) {
    return `**Macro & DXY:**\n• **DXY:** ${dxy.price ? dxy.price.toFixed(2) : "--"} (${dxy.gold_impact || "NEUTRAL"} for Gold)\n• **News Bias:** ${d.fundamentals?.bias || "NEUTRAL"} (${d.fundamentals?.bullish_headlines || 0}B / ${d.fundamentals?.bearish_headlines || 0}S).`;
  }
  if (q.includes("risk") || q.includes("lot") || q.includes("size")) {
    const acct = parseFloat(el("riskAccountInput")?.value) || 10000;
    const rPct = parseFloat(el("riskPctInput")?.value) || 1.0;
    const stopDist = Math.max(Math.abs(d.entry - d.stop_loss), 0.1);
    const oz = (acct * (rPct / 100)) / stopDist;
    return `**Position Size ($${acct.toLocaleString()} @ ${rPct}% Risk):**\n• **Stop Distance:** ${stopDist.toFixed(1)} pts\n• **Recommended:** **${oz.toFixed(2)} oz** (${(oz / 100).toFixed(2)} lots).`;
  }
  return `**${d.symbol} (${d.trading_style} · ${d.timeframe}):** ${d.signal} (${d.confidence}%). Entry $${d.entry.toFixed(2)} | SL $${d.stop_loss.toFixed(2)} | TP1 $${d.take_profit_1.toFixed(2)}.`;
}

function appendCopilotMessage(role, text) {
  const box = el("aiCopilotChatBox");
  if (!box) return;
  const div = document.createElement("div");
  div.className = `chat-msg ${role}`;
  div.innerHTML = escapeHtml(text).replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>").replace(/\n/g, "<br/>");
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
}

// ============================================================================
// 11. DEDICATED SIDEBAR VIEW ROUTER & CONFIRMED ACTIONS
// ============================================================================
function switchWorkspaceView(viewKey) {
  const validViews = ["overview", "terminal", "ai-gate", "copilot", "backtest", "telegram", "settings"];
  if (!validViews.includes(viewKey)) viewKey = "overview";
  currentView = viewKey;

  const titles = {
    overview: "Overview",
    terminal: "Chart Terminal",
    "ai-gate": "AI & Macro News",
    copilot: "Copilot & Strategy Lab",
    backtest: "Backtest & Ledger",
    telegram: "Telegram Signal Hub",
    settings: "Settings & Risk"
  };

  document.querySelectorAll(".nav-item[data-nav]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.nav === viewKey);
  });

  if (el("pageTitle")) el("pageTitle").textContent = titles[viewKey] || "Overview";

  document.querySelectorAll(".workspace-view").forEach((v) => {
    v.classList.toggle("hidden-view", v.dataset.view !== viewKey);
  });

  if (el("appSidebar")) el("appSidebar").classList.remove("mobile-open");

  try {
    history.replaceState(null, "", `#${viewKey}`);
  } catch (e) {}

  setTimeout(() => {
    if (viewKey === "terminal") drawCharts();
    if (viewKey === "backtest" && selectedRunDetail) drawEquityCurve(selectedRunDetail.equity_curve || []);
  }, 30);
}

function applyTradingStyleDirect(style, customTf = null) {
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
  showToast(`Active Mode: ${cfg.label}`);
}

function switchTradingStyle(style) {
  if (style === currentStyle) return;
  const cfg = STYLE_DEFAULTS[style] || STYLE_DEFAULTS.SWING;
  openConfirmDialog({
    title: `Switch to ${cfg.label}`,
    badge: style,
    desc: "Change active trading style, default timeframe, and ATR risk multipliers?",
    meta: `Timeframe: ${cfg.tf} · SL: ${cfg.sl}x ATR · TP1: ${cfg.tp1}x ATR · TP2: ${cfg.tp2}x ATR`,
    confirmLabel: "Switch Mode ↵",
    onConfirm: () => applyTradingStyleDirect(style)
  });
}

function switchTimeframe(tf) {
  if (tf === currentTf) return;
  currentTf = tf;
  document.querySelectorAll("#tfGroup .tf-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.tf === tf);
  });
  selectedRunDetail = null;
  fetchFullDashboard();
  showToast(`Timeframe: ${tf.toUpperCase()}`);
}

window.switchTimeframe = switchTimeframe;

function promptTelegramBroadcast() {
  const d = currentData;
  const chatId = el("tgChatIdInput")?.value.trim() || "All Subscribed Chats";
  openConfirmDialog({
    title: "Broadcast Signal to Telegram",
    badge: "TELEGRAM",
    desc: "Send the current AI-vetted XAU/USD signal to @this_is_ai_signal_bot subscribers?",
    meta: d
      ? `Symbol: ${d.symbol} (${currentStyle} · ${currentTf})\nSignal: ${d.signal} (${d.confidence}%)\nEntry: $${d.entry.toFixed(2)} | SL: $${d.stop_loss.toFixed(2)} | TP1: $${d.take_profit_1.toFixed(2)}\nTarget: ${chatId}`
      : `Symbol: ${currentSymbol} (${currentStyle} · ${currentTf})`,
    confirmLabel: "Send to Telegram ↵",
    onConfirm: async () => {
      try {
        const res = await fetch(`${API_BASE}/api/telegram/send`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            symbol: currentSymbol,
            interval: currentTf,
            trading_style: currentStyle,
            chat_id: el("tgChatIdInput")?.value.trim() || ""
          })
        });
        const data = await res.json();
        if (data.telegram) renderTelegramStatus(data.telegram);
        if (data.broadcast && data.broadcast.sent > 0) {
          showToast(`Sent signal to ${data.broadcast.sent} Telegram chat(s)!`);
        } else {
          showToast(data.broadcast?.error || "Send /start to @this_is_ai_signal_bot first!");
        }
      } catch (e) {
        showToast("Telegram broadcast failed.");
      }
    }
  });
}

function initCommandPalette() {
  const modal = el("cmdPaletteModal");
  const input = el("cmdPaletteInput");
  const list = el("cmdPaletteList");
  if (!modal || !input || !list) return;

  const commands = [
    { label: "Go to Overview", cat: "View", run: () => switchWorkspaceView("overview") },
    { label: "Go to Chart Terminal", cat: "View", run: () => switchWorkspaceView("terminal") },
    { label: "Go to AI & Macro News", cat: "View", run: () => switchWorkspaceView("ai-gate") },
    { label: "Go to Copilot & Strategy Lab", cat: "View", run: () => switchWorkspaceView("copilot") },
    { label: "Go to Backtest & Ledger", cat: "View", run: () => switchWorkspaceView("backtest") },
    { label: "Go to Telegram Signal Hub", cat: "View", run: () => switchWorkspaceView("telegram") },
    { label: "Go to Settings & Risk", cat: "View", run: () => switchWorkspaceView("settings") },
    { label: "Switch Mode: Swing Trade (1H ★)", cat: "Style", run: () => switchTradingStyle("SWING") },
    { label: "Switch Mode: Intraday (15m)", cat: "Style", run: () => switchTradingStyle("INTRADAY") },
    { label: "Switch Mode: Scalping (1m)", cat: "Style", run: () => switchTradingStyle("SCALPING") },
    { label: "Broadcast Active Signal to Telegram", cat: "Action", run: () => promptTelegramBroadcast() },
    { label: "Toggle Dark / Light Theme", cat: "Theme", run: () => toggleTheme() }
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
          <span>${escapeHtml(c.label)}</span>
          <span class="pill NEUTRAL">${escapeHtml(c.cat)}</span>
        </div>
      `
      )
      .join("");
    list.querySelectorAll(".cmd-item").forEach((item, idx) => {
      item.addEventListener("click", () => {
        modal.classList.remove("open");
        filtered[idx].run();
      });
    });
  }

  function openModal() {
    modal.classList.add("open");
    input.value = "";
    renderCmds("");
    setTimeout(() => input.focus(), 30);
  }

  if (el("openCmdPaletteBtn")) el("openCmdPaletteBtn").addEventListener("click", openModal);
  if (el("openCmdFooterBtn")) el("openCmdFooterBtn").addEventListener("click", openModal);
  modal.addEventListener("click", (e) => {
    if (e.target === modal) modal.classList.remove("open");
  });
  input.addEventListener("input", () => renderCmds(input.value));

  window.addEventListener("keydown", (e) => {
    const confirmModal = el("confirmActionModal");
    if (confirmModal && confirmModal.classList.contains("open")) {
      if (e.key === "Escape") {
        e.preventDefault();
        closeConfirmDialog(false);
      } else if (e.key === "Enter") {
        e.preventDefault();
        closeConfirmDialog(true);
      }
      return;
    }

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
  if (currentView === "terminal") drawCharts();
  if (currentView === "backtest" && selectedRunDetail) drawEquityCurve(selectedRunDetail.equity_curve || []);
  showToast(`${next.toUpperCase()} theme active`);
}

function initEventListeners() {
  // Confirmation Dialog Buttons
  if (el("confirmModalCancelBtn")) {
    el("confirmModalCancelBtn").addEventListener("click", () => closeConfirmDialog(false));
  }
  if (el("confirmModalOkBtn")) {
    el("confirmModalOkBtn").addEventListener("click", () => closeConfirmDialog(true));
  }
  if (el("confirmActionModal")) {
    el("confirmActionModal").addEventListener("click", (e) => {
      if (e.target === el("confirmActionModal")) closeConfirmDialog(false);
    });
  }

  // Restore Theme
  try {
    const saved = localStorage.getItem("aurumquant_theme");
    if (saved === "light" || saved === "dark") document.documentElement.setAttribute("data-theme", saved);
  } catch (e) {}

  // Sidebar & Quick Jump Navigation
  if (el("sidebarCollapseBtn")) {
    el("sidebarCollapseBtn").addEventListener("click", () => {
      el("appShell")?.classList.toggle("sidebar-collapsed");
      setTimeout(() => {
        if (currentView === "terminal") drawCharts();
        if (currentView === "backtest" && selectedRunDetail) drawEquityCurve(selectedRunDetail.equity_curve || []);
      }, 200);
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
  document.querySelectorAll("[data-jump]").forEach((btn) => {
    btn.addEventListener("click", () => switchWorkspaceView(btn.dataset.jump));
  });

  if (el("themeToggleBtn")) el("themeToggleBtn").addEventListener("click", toggleTheme);

  // Style, Symbol & Timeframe Controls
  document.querySelectorAll("#styleGroup .style-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchTradingStyle(btn.dataset.style));
  });
  document.querySelectorAll("#tfGroup .tf-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchTimeframe(btn.dataset.tf));
  });
  if (el("symbolSelect")) {
    el("symbolSelect").addEventListener("change", (e) => {
      const nextSym = e.target.value;
      const prevSym = currentSymbol;
      openConfirmDialog({
        title: "Switch Broker Feed",
        badge: "FEED",
        desc: `Change active XAU/USD data source to ${nextSym}?`,
        meta: `Previous: ${prevSym} → New: ${nextSym}`,
        confirmLabel: "Switch Feed ↵",
        onConfirm: () => {
          currentSymbol = nextSym;
          selectedRunDetail = null;
          fetchFullDashboard();
          pollLiveTick();
          showToast(`Feed: ${nextSym}`);
        },
        onCancel: () => {
          e.target.value = prevSym;
        }
      });
    });
  }

  if (el("refreshBtn")) {
    el("refreshBtn").addEventListener("click", () => {
      fetchFullDashboard();
      pollLiveTick();
      showToast("Synced live market state");
    });
  }

  if (el("refreshNewsBtn")) {
    el("refreshNewsBtn").addEventListener("click", async () => {
      const res = await fetch(`${API_BASE}/api/fundamentals?force=1`);
      const data = await res.json();
      renderFundamentals(data);
      showToast("Refreshed DXY & Wire News");
    });
  }

  // Close Locked Position (with Confirmation Dialog)
  if (el("closePosBtn")) {
    el("closePosBtn").addEventListener("click", () => {
      const at = currentData?.position_lock?.active_trade;
      openConfirmDialog({
        title: "Close Active Locked Position",
        badge: "RISK LOCK",
        desc: "Force-close the locked position in Supabase and unlock the scanner?",
        meta: at
          ? `Trade #${at.id}: ${at.direction} @ $${at.entry_price.toFixed(2)} (${currentSymbol} · ${currentTf})`
          : `${currentSymbol} (${currentTf})`,
        confirmLabel: "Close Position ↵",
        danger: true,
        onConfirm: async () => {
          await fetch(`${API_BASE}/api/position/close`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ symbol: currentSymbol, timeframe: currentTf })
          });
          showToast("Position closed — scanner unlocked");
          fetchFullDashboard();
        }
      });
    });
  }

  // Telegram Actions (with Confirmation Dialog)
  if (el("tgSendNowBtn")) el("tgSendNowBtn").addEventListener("click", promptTelegramBroadcast);
  if (el("sendTelegramQuickBtn")) el("sendTelegramQuickBtn").addEventListener("click", promptTelegramBroadcast);

  if (el("tgSyncBtn")) {
    el("tgSyncBtn").addEventListener("click", () => {
      const chatId = el("tgChatIdInput")?.value.trim() || "";
      openConfirmDialog({
        title: "Sync Telegram Subscribers",
        badge: "TELEGRAM",
        desc: "Poll @this_is_ai_signal_bot for new /start registrations?",
        meta: chatId ? `Manual Chat ID to register: ${chatId}` : "Auto-detecting chats from Telegram Bot API",
        confirmLabel: "Sync Now ↵",
        onConfirm: async () => {
          const res = await fetch(`${API_BASE}/api/telegram/sync`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ chat_id: chatId })
          });
          const data = await res.json();
          renderTelegramStatus(data);
          showToast(`Synced ${(data.subscribers || []).length} Telegram chat(s)`);
        }
      });
    });
  }

  if (el("tgAutoNotifyChk")) {
    el("tgAutoNotifyChk").addEventListener("change", (e) => {
      const nextVal = e.target.checked;
      openConfirmDialog({
        title: `${nextVal ? "Enable" : "Disable"} 24/7 Telegram Auto-Push`,
        badge: "AUTOMATION",
        desc: `${nextVal ? "Automatically broadcast" : "Pause automatic broadcasting of"} new AI-approved signals and TP/SL hits to Telegram?`,
        meta: `Bot: @this_is_ai_signal_bot · Status: ${nextVal ? "ENABLED" : "PAUSED"}`,
        confirmLabel: "Update Setting ↵",
        onConfirm: async () => {
          const res = await fetch(`${API_BASE}/api/settings`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ telegram_auto_notify: nextVal })
          });
          const data = await res.json();
          if (data.telegram) renderTelegramStatus(data.telegram);
          showToast(`Auto-Push: ${nextVal ? "ON" : "OFF"}`);
        },
        onCancel: () => {
          e.target.checked = !nextVal;
        }
      });
    });
  }

  // Save Gemini Key & Price Alert (with Confirmation Dialog)
  if (el("saveGeminiKeyBtn")) {
    el("saveGeminiKeyBtn").addEventListener("click", () => {
      const k = el("geminiKeyInput")?.value.trim() || "";
      openConfirmDialog({
        title: "Update Cloud AI Key",
        badge: "GEMINI ARGON",
        desc: k
          ? "Save your Gemini 4 Argon API key for cloud LLM inference?"
          : "Clear saved API key and use the built-in 3-Agent Quant Committee?",
        meta: k ? `Key prefix: ${k.slice(0, 6)}...` : "Mode: Local 3-Agent Committee",
        confirmLabel: "Save Key ↵",
        onConfirm: async () => {
          await fetch(`${API_BASE}/api/settings`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ gemini_api_key: k })
          });
          showToast("Updated AI Committee settings");
          fetchFullDashboard();
        }
      });
    });
  }

  if (el("setAlertBtn")) {
    el("setAlertBtn").addEventListener("click", () => {
      const val = parseFloat(el("alertPriceInput")?.value);
      if (isNaN(val) || val <= 0) return;
      openConfirmDialog({
        title: "Set XAU/USD Price Alert",
        badge: "ALERT",
        desc: `Trigger a live notification when ${currentSymbol} reaches $${val.toFixed(2)}?`,
        meta: `Current Price: $${(currentData?.current_price || 0).toFixed(2)} → Target: $${val.toFixed(2)}`,
        confirmLabel: "Activate Alert ↵",
        onConfirm: () => {
          customAlertPrice = val;
          if (el("activeAlertStatus")) {
            el("activeAlertStatus").textContent = `Active @ $${val.toFixed(2)}`;
            el("activeAlertStatus").style.color = "var(--gold-bright)";
          }
          showToast(`Alert active @ $${val.toFixed(2)}`);
        }
      });
    });
  }

  // Terminal Chart Toggles & Paper Order Confirmation
  if (el("toggleBBBtn")) {
    el("toggleBBBtn").addEventListener("click", (e) => {
      showBB = !showBB;
      e.currentTarget.textContent = `BB: ${showBB ? "ON" : "OFF"}`;
      drawCharts();
    });
  }
  if (el("toggleLevelsBtn")) {
    el("toggleLevelsBtn").addEventListener("click", (e) => {
      showSignalLines = !showSignalLines;
      e.currentTarget.textContent = `Levels: ${showSignalLines ? "ON" : "OFF"}`;
      drawCharts();
    });
  }
  if (el("toggleOscBtn")) {
    el("toggleOscBtn").addEventListener("click", (e) => {
      oscMode = oscMode === "RSI" ? "MACD" : "RSI";
      e.currentTarget.textContent = `Osc: ${oscMode}`;
      drawCharts();
    });
  }

  const priceCanvas = el("priceCanvas");
  if (priceCanvas) {
    priceCanvas.addEventListener("mousemove", (e) => {
      if (!currentData || !currentData.series) return;
      const rect = priceCanvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const candles = currentData.series.candles;
      const stepX = (rect.width - 12 - 68) / candles.length;
      const idx = Math.floor((x - 12) / stepX);
      if (idx >= 0 && idx < candles.length) {
        hoverIdx = idx;
        const c = candles[idx];
        const r = currentData.series.rsi14[idx];
        if (el("hoverOhlcInfo")) {
          el("hoverOhlcInfo").textContent = `${c.time_local || c.time} | O $${c.open.toFixed(1)} H $${c.high.toFixed(1)} L $${c.low.toFixed(1)} C $${c.close.toFixed(1)} | RSI ${r.toFixed(1)}`;
        }
        drawCharts();
      }
    });
  }

  if (el("watchlistSearchInput")) {
    el("watchlistSearchInput").addEventListener("input", renderTerminalWatchlist);
  }
  ["riskAccountInput", "riskPctInput"].forEach((id) => {
    if (el(id)) el(id).addEventListener("input", updatePositionSizer);
  });

  ["simBuyBtn", "simSellBtn"].forEach((btnId) => {
    if (el(btnId)) {
      el(btnId).addEventListener("click", () => {
        if (!currentData) return;
        const side = btnId === "simBuyBtn" ? "BUY" : "SELL";
        const lots = el("calcLotSize")?.textContent || "0.10 lots";
        const riskUsd = el("calcDollarRisk")?.textContent || "$100.00";
        const entry = currentData.current_price.toFixed(2);
        openConfirmDialog({
          title: `Confirm Simulated Paper ${side}`,
          badge: "PAPER ORDER",
          desc: `Log a simulated Paper ${side} ticket using your calculated risk parameters?`,
          meta: `Instrument: ${currentSymbol} @ $${entry}\nSize: ${lots} (Max Risk: ${riskUsd})\nSL: $${currentData.stop_loss.toFixed(2)} · TP1: $${currentData.take_profit_1.toFixed(2)}`,
          confirmLabel: `Submit Paper ${side} ↵`,
          onConfirm: () => {
            const fb = el("simOrderFeedback");
            if (fb) {
              fb.innerHTML = `<span style="color:${side === "BUY" ? "var(--buy)" : "var(--sell)"};font-weight:700;">✓ Paper ${side}:</span> ${lots} @ $${entry}`;
            }
            showToast(`Paper ${side} logged (${lots} @ $${entry})`);
          }
        });
      });
    }
  });

  // Copilot Chat
  document.querySelectorAll(".prompt-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const label = chip.textContent;
      appendCopilotMessage("user", label);
      appendCopilotMessage("ai", generateCopilotReply(chip.dataset.prompt || label));
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
  if (el("clearCopilotBtn")) {
    el("clearCopilotBtn").addEventListener("click", () => {
      if (el("aiCopilotChatBox")) {
        el("aiCopilotChatBox").innerHTML = `<div class="chat-msg ai">Chat cleared. Select a prompt chip or ask a question below.</div>`;
      }
    });
  }

  // Backtest Runner (with Confirmation Dialog) & Ledger Tabs
  if (el("runBacktestBtn")) {
    el("runBacktestBtn").addEventListener("click", () => {
      const uiStrat = el("btStrategySelect")?.value || "ALL";
      const horizonKey = el("btHorizonSelect")?.value || "30d";
      const durCfg = DURATION_BARS_MAP[horizonKey] || DURATION_BARS_MAP["30d"];
      const sl = parseFloat(el("btSlInput")?.value) || 1.5;
      const tp1 = parseFloat(el("btTp1Input")?.value) || 2.5;
      const tp2 = parseFloat(el("btTp2Input")?.value) || 4.0;

      openConfirmDialog({
        title: "Run Deep Historical Backtest",
        badge: "BACKTEST",
        desc: "Execute walk-forward simulation and persist the run to Supabase PostgreSQL?",
        meta: `Symbol: ${currentSymbol} (${currentStyle} · ${currentTf})\nHorizon: ${durCfg.bars} bars (${durCfg.preset})\nMultipliers: SL ${sl}x · TP1 ${tp1}x · TP2 ${tp2}x ATR`,
        confirmLabel: "Run & Save ↵",
        onConfirm: async () => {
          const btn = el("runBacktestBtn");
          btn.textContent = "Running...";
          btn.disabled = true;
          try {
            const res = await fetch(`${API_BASE}/api/backtest/run`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                trading_style: currentStyle,
                symbol: currentSymbol,
                interval: currentTf,
                strategy_mode: STRATEGY_MODE_MAP[uiStrat] || "PRO_CONFIRMED",
                duration_preset: durCfg.preset,
                bars_tested: durCfg.bars,
                sl_mult: sl,
                tp1_mult: tp1,
                tp2_mult: tp2
              })
            });
            const data = await res.json();
            if (data.detail) {
              selectedRunDetail = data.detail;
              renderBacktestRunsList(data.runs || []);
              renderSelectedBacktest(data.detail);
              updateBentoKpis();
              showToast(`Saved Backtest Run #${data.detail.id} to Supabase!`);
            }
          } catch (err) {
            showToast("Backtest failed");
          } finally {
            btn.textContent = "Run Backtest";
            btn.disabled = false;
          }
        }
      });
    });
  }

  if (el("exportCsvBtn")) {
    el("exportCsvBtn").addEventListener("click", () => {
      if (!selectedRunDetail || !selectedRunDetail.trades) return;
      const rows = [["Trade #", "Entry Time", "Exit Time", "Direction", "Strategy", "Entry", "SL", "TP1", "Exit", "Outcome", "PnL Pts"]];
      selectedRunDetail.trades.forEach((t, i) => {
        rows.push([i + 1, t.entry_time, t.exit_time, t.direction, t.signal_type, t.entry_price, t.sl_price, t.tp1_price, t.exit_price, t.outcome, t.pnl_pts]);
      });
      const blob = new Blob([rows.map((r) => r.join(",")).join("\n")], { type: "text/csv" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `xauusd_backtest_run_${selectedRunDetail.id}.csv`;
      a.click();
      showToast(`Exported Run #${selectedRunDetail.id} CSV`);
    });
  }

  if (el("tabBtTradesBtn") && el("tabLiveLedgerBtn")) {
    el("tabBtTradesBtn").addEventListener("click", () => {
      el("tabBtTradesBtn").classList.add("active");
      el("tabLiveLedgerBtn").classList.remove("active");
      if (el("btTradesPane")) el("btTradesPane").style.display = "block";
      if (el("liveLedgerPane")) el("liveLedgerPane").style.display = "none";
      if (el("btFilterControls")) el("btFilterControls").style.display = "flex";
    });
    el("tabLiveLedgerBtn").addEventListener("click", () => {
      el("tabLiveLedgerBtn").classList.add("active");
      el("tabBtTradesBtn").classList.remove("active");
      if (el("liveLedgerPane")) el("liveLedgerPane").style.display = "block";
      if (el("btTradesPane")) el("btTradesPane").style.display = "none";
      if (el("btFilterControls")) el("btFilterControls").style.display = "none";
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
    if (currentView === "terminal") drawCharts();
    if (currentView === "backtest" && selectedRunDetail) drawEquityCurve(selectedRunDetail.equity_curve || []);
  });
}

// ============================================================================
// 12. INITIALIZE ON DOM READY
// ============================================================================
document.addEventListener("DOMContentLoaded", () => {
  renderStrategyLab();
  renderFeatureFlagsPanel();
  initCommandPalette();
  initEventListeners();

  const initialHash = (window.location.hash || "").replace("#", "");
  if (initialHash) switchWorkspaceView(initialHash);

  updateClocksAndCountdown();
  setInterval(updateClocksAndCountdown, 1000);

  fetchFullDashboard();
  pollLiveTick();
  setInterval(pollLiveTick, 2000);
  setInterval(fetchFullDashboard, 20000);
});
