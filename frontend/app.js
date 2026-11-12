// XAU/USD Quantitative AI Intelligence Terminal - Frontend Application
const API_BASE = (typeof window !== "undefined" && typeof window.API_BASE === "string")
  ? window.API_BASE
  : "https://gold-signal-api-production.up.railway.app";

// Default is SWING TRADE on 1h Timeframe!
    let currentSymbol = "OANDA:XAUUSD";
    let currentStyle = "SWING";
    let currentTf = "1h";
    let currentData = null;
    let selectedRunDetail = null;
    let lastTickPrice = null;
    let showBB = true;
    let showSignalLines = true;
    let oscMode = "RSI";
    let streamEnabled = true;
    let soundEnabled = false;
    let customAlertPrice = null;
    let hoverIdx = null;

    const STYLE_DEFAULTS = {
      SWING:    { tf: "1h",  sl: 1.5, tp1: 2.5, tp2: 4.0, label: "Swing Trade (Pro Default)" },
      INTRADAY: { tf: "15m", sl: 1.2, tp1: 1.8, tp2: 3.0, label: "Intraday Session" },
      SCALPING: { tf: "1m",  sl: 1.0, tp1: 1.5, tp2: 2.0, label: "High-Speed Scalping" },
      POSITION: { tf: "4h",  sl: 1.8, tp1: 3.0, tp2: 5.0, label: "Macro Position" }
    };

    const priceCanvas = document.getElementById("priceCanvas");
    const oscCanvas = document.getElementById("oscCanvas");
    const equityCanvas = document.getElementById("equityCanvas");

    function showToast(msg) {
      const t = document.getElementById("toast");
      t.textContent = msg;
      t.style.display = "block";
      setTimeout(() => { t.style.display = "none"; }, 3000);
    }

    function playBeep(freq = 880, duration = 0.18) {
      if (!soundEnabled) return;
      try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.frequency.value = freq;
        osc.type = "sine";
        gain.gain.setValueAtTime(0.15, ctx.currentTime);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start();
        osc.stop(ctx.currentTime + duration);
      } catch (e) {}
    }

    function updateClocksAndCountdown() {
      const now = new Date();
      const utcMs = now.getTime() + now.getTimezoneOffset() * 60000;
      const utc7 = new Date(utcMs + 7 * 3600000);
      const hh = String(utc7.getHours()).padStart(2, "0");
      const mm = String(utc7.getMinutes()).padStart(2, "0");
      const ss = String(utc7.getSeconds()).padStart(2, "0");
      document.getElementById("clockUtc7").textContent = `${hh}:${mm}:${ss} UTC+7`;

      const tfSecMap = { "1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400 };
      const periodSec = tfSecMap[currentTf] || 3600;
      const nowSec = Math.floor(now.getTime() / 1000);
      const rem = periodSec - (nowSec % periodSec);
      const rHr = Math.floor(rem / 3600);
      const rMin = String(Math.floor((rem % 3600) / 60)).padStart(2, "0");
      const rSec = String(rem % 60).padStart(2, "0");
      document.getElementById("barCountdown").textContent = rHr > 0 ? `${rHr}h ${rMin}m ${rSec}s` : `${rMin}:${rSec}`;

      const utcH = now.getUTCHours();
      document.getElementById("sessTokyo").classList.toggle("open", utcH >= 0 && utcH < 9);
      document.getElementById("sessLondon").classList.toggle("open", utcH >= 7 && utcH < 16);
      document.getElementById("sessNY").classList.toggle("open", utcH >= 12 && utcH < 21);
    }

    async function pollLiveTick() {
      if (!streamEnabled) return;
      try {
        const res = await fetch(`${API_BASE}/api/tick?symbol=${encodeURIComponent(currentSymbol)}`);
        const tick = await res.json();
        if (!tick || !tick.active) return;

        const price = tick.active.price;
        const priceEl = document.getElementById("livePrice");
        const boxEl = document.getElementById("priceBox");
        priceEl.textContent = `$${price.toFixed(2)}`;

        if (lastTickPrice !== null && price !== lastTickPrice) {
          boxEl.classList.remove("flash-up", "flash-down");
          void boxEl.offsetWidth;
          boxEl.classList.add(price > lastTickPrice ? "flash-up" : "flash-down");
          setTimeout(() => boxEl.classList.remove("flash-up", "flash-down"), 500);
        }
        lastTickPrice = price;

        const chg = tick.active.change_abs;
        const chgPct = tick.active.change_pct;
        const chgEl = document.getElementById("priceChangeBadge");
        chgEl.textContent = `${chg >= 0 ? "+" : ""}${chg.toFixed(2)} (${chg >= 0 ? "+" : ""}${chgPct.toFixed(2)}%)`;
        chgEl.style.color = chg >= 0 ? "var(--buy)" : "var(--sell)";

        document.getElementById("lastUpdate").textContent = `Live · ${tick.timestamp_local}`;

        if (tick.brokers) {
          if (tick.brokers["OANDA:XAUUSD"]) {
            document.getElementById("b_OANDA").textContent = `$${tick.brokers["OANDA:XAUUSD"].price.toFixed(2)}`;
          }
          if (tick.brokers["FX:XAUUSD"]) {
            document.getElementById("b_FX").textContent = `$${tick.brokers["FX:XAUUSD"].price.toFixed(2)}`;
          }
          if (tick.brokers["FOREXCOM:XAUUSD"]) {
            document.getElementById("b_FOREXCOM").textContent = `$${tick.brokers["FOREXCOM:XAUUSD"].price.toFixed(2)}`;
          }
          if (tick.brokers["TVC:DXY"]) {
            const dxy = tick.brokers["TVC:DXY"];
            document.getElementById("b_DXY").textContent = `${dxy.price.toFixed(3)} (${dxy.change_pct >= 0 ? "+" : ""}${dxy.change_pct.toFixed(2)}%)`;
          }
        }

        if (currentData && currentData.position_lock && currentData.position_lock.locked && currentData.position_lock.active_trade) {
          const at = currentData.position_lock.active_trade;
          const fpnl = at.direction === "BUY" ? (price - at.entry_price) : (at.entry_price - price);
          const pnlEl = document.getElementById("posLockPnl");
          pnlEl.textContent = `Floating P&L: ${fpnl >= 0 ? "+" : ""}$${fpnl.toFixed(2)}`;
          pnlEl.style.color = fpnl >= 0 ? "var(--buy)" : "var(--sell)";
        }

        if (currentData && currentData.series && currentData.series.candles.length) {
          currentData.current_price = price;
          const lastC = currentData.series.candles[currentData.series.candles.length - 1];
          lastC.close = price;
          if (price > lastC.high) lastC.high = price;
          if (price < lastC.low) lastC.low = price;
          drawCharts();
        }
        checkCustomAlert(price);
      } catch (e) {}
    }

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
        renderStructureTables(data);
        updateCalculator(true);
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
      } catch (err) {
        console.error("Dashboard sync error:", err);
      }
    }

    function renderMainSignal(d) {
      document.getElementById("livePrice").textContent = `$${d.current_price.toFixed(2)}`;
      document.getElementById("activeSymbolLabel").textContent = `${d.symbol} (TradingView Live)`;
      document.getElementById("activeSymSmall").textContent = d.symbol;
      document.getElementById("activeTfLabel").textContent = d.timeframe;
      document.getElementById("lastUpdate").textContent = `Candle: ${d.last_candle_time_local}`;

      if (d.style_info) {
        document.getElementById("activeStyleLabel").textContent = d.style_info.name;
        document.getElementById("headerStyleBadge").textContent = `${d.style_info.badge} (${d.timeframe})`;
        document.getElementById("styleTitleText").textContent = `${d.style_info.name}:`;
        document.getElementById("styleDescText").textContent = d.style_info.description;
        document.getElementById("styleHoldBadge").textContent = `Hold: ${d.style_info.hold_duration_label}`;
      }

      const pl = d.position_lock || {};
      const lockBar = document.getElementById("posLockBar");
      const lockTxt = document.getElementById("posLockText");
      const lockPnl = document.getElementById("posLockPnl");
      const closeBtn = document.getElementById("closePosBtn");

      if (pl.locked && pl.active_trade) {
        const at = pl.active_trade;
        lockBar.className = "pos-lock-bar locked";
        lockTxt.innerHTML = `<strong style="color:var(--gold);">SINGLE-POSITION LOCK ENGAGED:</strong> Active Trade <strong>#${at.id} (${at.trading_style || d.trading_style} · ${at.direction} @ ${at.entry_price.toFixed(2)})</strong> · SL: ${at.sl_price.toFixed(2)} · TP1: ${at.tp1_price.toFixed(2)} · <em>Locked until SL/TP.</em>`;
        const fp = at.floating_pnl || 0;
        lockPnl.textContent = `Floating P&L: ${fp >= 0 ? "+" : ""}$${fp.toFixed(2)}`;
        lockPnl.style.color = fp >= 0 ? "var(--buy)" : "var(--sell)";
        closeBtn.style.display = "inline-flex";
      } else {
        lockBar.className = "pos-lock-bar";
        lockTxt.innerHTML = `<strong style="color:var(--blue);">SINGLE-POSITION SCANNER READY:</strong> 0 Active Positions on ${d.timeframe} (${d.trading_style}). AI Agent Gate must approve before opening trade.`;
        lockPnl.textContent = "No Open Position";
        lockPnl.style.color = "var(--text-1)";
        closeBtn.style.display = "none";
      }

      const isBuy = d.direction === "BUY";
      const isSell = d.direction === "SELL";
      const banner = document.getElementById("signalBanner");
      const badge = document.getElementById("signalText");
      const cls = isBuy ? "buy" : isSell ? "sell" : "wait";
      banner.className = `signal-banner ${cls}`;
      badge.className = `signal-badge ${cls}`;
      badge.textContent = isBuy ? `▲ ${d.signal}` : isSell ? `▼ ${d.signal}` : `⏳ ${d.signal}`;

      document.getElementById("signalConfidence").textContent = `${d.confidence}%`;
      document.getElementById("signalRR").textContent = `1 : ${d.risk_reward}`;
      if (d.ai_agent) {
        document.getElementById("aiGateBadgePill").textContent = d.ai_agent.verdict_badge;
      }

      const activeTrade = (pl.locked && pl.active_trade) ? pl.active_trade : null;
      const dispEntry = activeTrade ? activeTrade.entry_price : d.entry;
      const dispSl = activeTrade ? activeTrade.sl_price : d.stop_loss;
      const dispTp1 = activeTrade ? activeTrade.tp1_price : d.take_profit_1;
      const dispTp2 = activeTrade ? activeTrade.tp2_price : d.take_profit_2;

      document.getElementById("entryLabel").textContent = activeTrade ? `Locked Entry (#${activeTrade.id})` : "Ref Entry Price";
      document.getElementById("entryVal").textContent = dispEntry.toFixed(2);
      document.getElementById("slVal").textContent = dispSl.toFixed(2);
      document.getElementById("tp1Val").textContent = dispTp1.toFixed(2);
      document.getElementById("tp2Val").textContent = dispTp2.toFixed(2);

      document.getElementById("slSub").textContent = `${d.sl_mult}x ATR(14)`;
      document.getElementById("tp1Sub").textContent = `${d.tp1_mult}x ATR (Moves SL→BE)`;
      document.getElementById("tp2Sub").textContent = `${d.tp2_mult}x ATR Swing Runner`;

      const cGrid = document.getElementById("checklistGrid");
      cGrid.innerHTML = "";
      (d.checklist || []).forEach(item => {
        const div = document.createElement("div");
        div.className = `check-item ${item.passed ? "passed" : ""}`;
        div.innerHTML = `
          <div class="c-name">
            <span style="color:${item.passed ? 'var(--buy)' : 'var(--text-2)'};">${item.passed ? "✓" : "○"}</span>
            <span>${item.name}</span>
          </div>
          <div class="c-det">${item.detail}</div>
        `;
        cGrid.appendChild(div);
      });

      document.getElementById("rationaleText").textContent = d.rationale;
      document.getElementById("atrBadge").textContent = `ATR(14): $${d.indicators.atr14.toFixed(2)}`;

      document.getElementById("indEma21").textContent = d.indicators.ema21.toFixed(2);
      document.getElementById("indEma50").textContent = d.indicators.ema50.toFixed(2);
      document.getElementById("indEma200").textContent = (d.indicators.ema200 || d.indicators.ema50).toFixed(2);
      document.getElementById("indRsi").textContent = d.indicators.rsi14.toFixed(1);
    }

    function renderAiAgentLayer(ai) {
      if (!ai) return;
      document.getElementById("aiEngineLabel").textContent = ai.engine;
      document.getElementById("aiVerdictHeadline").textContent = `${ai.verdict_badge} (${ai.adjusted_confidence}% Confidence)`;
      document.getElementById("aiWatchZoneBadge").textContent = `Fib Golden Pocket: ${ai.watch_zone}`;
      document.getElementById("aiExecSummaryText").textContent = ai.executive_summary;

      const grid = document.getElementById("aiAgentsGrid");
      grid.innerHTML = "";
      (ai.agents || []).forEach(ag => {
        const col = ag.bias === "BULLISH" || ag.bias === "BUY" ? "var(--buy)"
                  : (ag.bias === "BEARISH" || ag.bias === "SELL" ? "var(--sell)" : "var(--gold)");
        const card = document.createElement("div");
        card.className = "ai-subcard";
        card.innerHTML = `
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <strong style="font-size:12px;color:var(--text-0);">${ag.name}</strong>
            <span style="font-size:10px;font-weight:800;padding:2px 7px;border-radius:4px;background:var(--bg-1);color:${col};">${ag.bias} (${ag.score}%)</span>
          </div>
          <div style="font-size:10px;color:var(--text-2);font-weight:600;">${ag.role}</div>
          <div style="font-size:11.5px;color:var(--text-1);line-height:1.4;">${ag.note}</div>
        `;
        grid.appendChild(card);
      });
    }

    function escapeHtml(str) {
      return String(str || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }

    function renderTelegramStatus(tg) {
      if (!tg) return;
      const badge = document.getElementById("tgBotStatusBadge");
      if (tg.bot && tg.bot.ok) {
        badge.textContent = `ONLINE · @${tg.bot.username}`;
        badge.style.background = "var(--buy-dim)";
        badge.style.color = "var(--buy)";
        const link = document.getElementById("tgBotLink");
        link.href = tg.bot.bot_link || `https://t.me/${tg.bot.username}`;
        link.textContent = `@${tg.bot.username} (${tg.bot.first_name}) ↗`;
      } else {
        badge.textContent = "BOT OFFLINE / CHECK TOKEN";
        badge.style.background = "var(--sell-dim)";
        badge.style.color = "var(--sell)";
      }

      document.getElementById("tgAutoNotifyChk").checked = Boolean(tg.auto_notify);

      const subs = tg.subscribers || [];
      document.getElementById("tgSubCount").textContent = String(subs.length);
      const subBox = document.getElementById("tgSubscribersList");
      if (!subs.length) {
        subBox.innerHTML = `No chats subscribed yet. Open <a href="https://t.me/this_is_ai_signal_bot" target="_blank" style="color:var(--gold);font-weight:700;">@this_is_ai_signal_bot</a> and send <code>/start</code>, or enter your Chat ID above.`;
      } else {
        subBox.innerHTML = subs.map(s => `
          <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:6px;padding:6px 0;border-bottom:1px solid rgba(38,50,70,0.5);min-width:0;">
            <div style="min-width:0;flex:1;overflow-wrap:anywhere;">
              <div style="font-weight:700;color:var(--buy);line-height:1.3;">● ${escapeHtml(s.first_name || 'Trader')} ${s.username ? `<span style="color:var(--text-1);font-weight:500;">(@${escapeHtml(s.username)})</span>` : ''}</div>
              <div style="font-size:10px;color:var(--text-2);margin-top:2px;">ID: <code style="color:var(--text-0);">${escapeHtml(s.chat_id)}</code></div>
            </div>
            <span style="font-size:9.5px;text-transform:uppercase;background:var(--bg-1);border:1px solid var(--border);padding:1px 6px;border-radius:99px;color:var(--gold);font-weight:700;flex-shrink:0;">${escapeHtml(s.chat_type || 'chat')}</span>
          </div>
        `).join("");
      }

      const logs = tg.logs || [];
      const logBox = document.getElementById("tgLogsList");
      if (!logs.length) {
        logBox.innerHTML = "No alerts sent yet. Click <strong>Broadcast Signal Now</strong> to test!";
      } else {
        logBox.innerHTML = logs.map(l => {
          const cleanPreview = escapeHtml(l.message_preview || "")
            .replace(/\s+/g, " ")
            .trim();
          return `
            <div style="padding:6px 0;border-bottom:1px solid rgba(38,50,70,0.5);min-width:0;">
              <div style="display:flex;justify-content:space-between;align-items:center;gap:6px;margin-bottom:3px;flex-wrap:wrap;">
                <span style="color:${l.ok ? 'var(--buy)' : 'var(--sell)'};font-weight:800;font-size:10px;background:${l.ok ? 'var(--buy-dim)' : 'var(--sell-dim)'};padding:1px 6px;border-radius:4px;">${escapeHtml(l.event_type)}</span>
                <span style="color:var(--text-2);font-size:10px;font-variant-numeric:tabular-nums;">${escapeHtml((l.sent_at || '').slice(11, 19))} · <code>${escapeHtml(l.chat_id)}</code></span>
              </div>
              <div style="color:var(--text-1);font-size:10.5px;line-height:1.35;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;word-break:break-word;overflow-wrap:anywhere;">${cleanPreview}</div>
            </div>
          `;
        }).join("");
      }
    }

    function renderFundamentals(f) {
      if (!f) return;
      const biasEl = document.getElementById("fundBiasVal");
      biasEl.textContent = `${f.bias} (${f.score >= 0 ? "+" : ""}${f.score})`;
      biasEl.style.color = f.bias === "BULLISH" ? "var(--buy)" : f.bias === "BEARISH" ? "var(--sell)" : "var(--gold)";
      document.getElementById("fundScoreSub").textContent = `${f.bullish_headlines} Bullish vs ${f.bearish_headlines} Bearish Wire Headlines`;

      if (f.dxy && f.dxy.price > 0) {
        document.getElementById("fundDxyPrice").textContent = `${f.dxy.price.toFixed(3)} (${f.dxy.change_pct >= 0 ? "+" : ""}${f.dxy.change_pct.toFixed(2)}%)`;
        document.getElementById("fundDxyImpact").innerHTML = `5m RSI: ${f.dxy.rsi_5m} · Gold Impact: <strong style="color:${f.dxy.gold_impact === 'BULLISH' ? 'var(--buy)' : f.dxy.gold_impact === 'BEARISH' ? 'var(--sell)' : 'var(--gold)'};">${f.dxy.gold_impact}</strong>`;
      }
      document.getElementById("fundSummaryText").textContent = f.summary;

      const evPill = document.getElementById("eventAlertPill");
      if (f.high_impact_events && f.high_impact_events.length > 0) {
        evPill.style.display = "inline-block";
        evPill.textContent = `⚡ EVENT ACTIVE: ${f.high_impact_events.join(" · ")}`;
      } else {
        evPill.style.display = "none";
      }

      document.getElementById("newsCountsLabel").textContent = `${(f.headlines || []).length} Recent Stories`;
      const nList = document.getElementById("newsList");
      nList.innerHTML = "";
      (f.headlines || []).forEach(h => {
        const row = document.createElement("div");
        row.className = "news-item";
        const titleHtml = h.story_url
          ? `<a href="${h.story_url}" target="_blank" style="color:var(--text-0);text-decoration:none;font-weight:600;">${h.title}</a>`
          : `<span style="font-weight:600;">${h.title}</span>`;
        row.innerHTML = `
          <div style="display:flex;flex-direction:column;gap:2px;">
            ${titleHtml}
            <span style="font-size:10px;color:var(--text-2);">${h.source} · ${h.published}</span>
          </div>
          <span class="news-tag ${h.sentiment}">${h.sentiment}</span>
        `;
        nList.appendChild(row);
      });
    }

    function renderMtf(mtf, mtfOrder) {
      const grid = document.getElementById("mtfGrid");
      grid.innerHTML = "";
      document.getElementById("mtfSubLabel").textContent = `${currentStyle} Confluence (${mtfOrder.join(" · ")})`;
      let bullStructure = 0;
      let bearStructure = 0;
      mtfOrder.forEach(tf => {
        const item = mtf[tf];
        if (!item) return;
        const isBullEma = item.ema21 >= item.ema50;
        if (isBullEma) bullStructure++; else bearStructure++;
        const dCls = item.direction === "BUY" ? "buy" : item.direction === "SELL" ? "sell" : "wait";
        const card = document.createElement("div");
        card.className = "mtf-card";
        card.style.cursor = "pointer";
        card.onclick = () => switchTimeframe(tf);
        card.innerHTML = `
          <div class="mtf-top">
            <span class="mtf-tf">${tf.toUpperCase()} Timeframe</span>
            <span class="mtf-dir ${dCls}">${item.direction} (${item.confidence}%)</span>
          </div>
          <div class="mtf-meta">
            <span>RSI: <strong>${item.rsi14.toFixed(1)}</strong></span>
            <span>EMA21/50: <strong style="color:${isBullEma ? 'var(--buy)' : 'var(--sell)'};">${isBullEma ? "Bullish" : "Bearish"}</strong></span>
          </div>
          <div class="mtf-meta">
            <span>Price: ${item.price.toFixed(2)}</span>
            <span>EMA50: ${item.ema50.toFixed(2)}</span>
          </div>
        `;
        grid.appendChild(card);
      });

      const verdictEl = document.getElementById("confluenceVerdict");
      const total = mtfOrder.length;
      if (bullStructure === total) {
        verdictEl.textContent = `STRONG BULLISH SWING ALIGNMENT (${bullStructure}/${total} Timeframes)`;
        verdictEl.style.color = "var(--buy)";
      } else if (bearStructure === total) {
        verdictEl.textContent = `STRONG BEARISH SWING ALIGNMENT (${bearStructure}/${total} Timeframes)`;
        verdictEl.style.color = "var(--sell)";
      } else if (bullStructure >= total - 1) {
        verdictEl.textContent = `BULLISH MTF BIAS (${bullStructure}/${total} Timeframes)`;
        verdictEl.style.color = "var(--buy)";
      } else if (bearStructure >= total - 1) {
        verdictEl.textContent = `BEARISH MTF BIAS (${bearStructure}/${total} Timeframes)`;
        verdictEl.style.color = "var(--sell)";
      } else {
        verdictEl.textContent = `MIXED / TRANSITIONAL (${bullStructure} Bullish vs ${bearStructure} Bearish)`;
        verdictEl.style.color = "var(--gold)";
      }
    }

    function renderStructureTables(d) {
      const pBody = document.querySelector("#pivotsTable tbody");
      pBody.innerHTML = "";
      const pOrder = [
        ["R2", d.pivots.r2, "var(--sell)"],
        ["R1", d.pivots.r1, "var(--sell)"],
        ["Pivot", d.pivots.pivot, "var(--gold)"],
        ["S1", d.pivots.s1, "var(--buy)"],
        ["S2", d.pivots.s2, "var(--buy)"]
      ];
      pOrder.forEach(([lbl, val, col]) => {
        const diff = (val - d.current_price).toFixed(2);
        const sign = diff > 0 ? "+" : "";
        pBody.innerHTML += `<tr>
          <td style="font-weight:700;color:${col};">${lbl}</td>
          <td>${val.toFixed(2)}</td>
          <td style="color:var(--text-1);">${sign}${diff}</td>
        </tr>`;
      });

      const fBody = document.querySelector("#fibTable tbody");
      fBody.innerHTML = "";
      Object.entries(d.fibonacci).forEach(([k, val]) => {
        const isGolden = k.includes("38.2") || k.includes("50.0") || k.includes("61.8");
        fBody.innerHTML += `<tr style="${isGolden ? 'background:rgba(245,196,81,0.08);' : ''}">
          <td style="color:${isGolden ? 'var(--gold)' : 'var(--text-1)'};font-weight:${isGolden ? '700' : '400'};">${k}</td>
          <td style="font-weight:700;">${val.toFixed(2)}</td>
        </tr>`;
      });
    }

    function renderBacktestRunsList(runs) {
      const tbody = document.querySelector("#runsTable tbody");
      tbody.innerHTML = "";
      runs.forEach(r => {
        const isSel = selectedRunDetail && selectedRunDetail.id === r.id;
        const tr = document.createElement("tr");
        tr.className = `clickable-row ${isSel ? "selected-run" : ""}`;
        tr.onclick = () => loadBacktestRun(r.id);
        const shortTime = r.created_at.replace(" UTC+7", "").slice(5);
        const pnlColor = r.net_pnl_pts >= 0 ? "var(--buy)" : "var(--sell)";
        tr.innerHTML = `
          <td style="font-weight:700;color:var(--gold);">#${r.id}</td>
          <td>${shortTime}</td>
          <td><strong>${r.timeframe}</strong> · ${r.strategy_mode}</td>
          <td>${r.bars_tested}</td>
          <td>${r.sl_atr_mult}x / ${r.tp1_atr_mult}x</td>
          <td>${r.total_trades}</td>
          <td style="font-weight:700;color:${r.win_rate >= 50 ? 'var(--buy)' : 'var(--text-0)'};">${r.win_rate}%</td>
          <td>${r.profit_factor}</td>
          <td style="font-weight:700;color:${pnlColor};">${r.net_pnl_pts >= 0 ? "+" : ""}$${r.net_pnl_pts.toFixed(2)}</td>
        `;
        tbody.appendChild(tr);
      });
    }

    async function loadBacktestRun(runId) {
      const dir = document.getElementById("filterDirection").value;
      const out = document.getElementById("filterOutcome").value;
      const res = await fetch(`${API_BASE}/api/backtest_detail?run_id=${runId}&direction=${dir}&outcome=${out}`);
      const data = await res.json();
      if (data.detail) {
        selectedRunDetail = data.detail;
        renderSelectedBacktest(data.detail);
        const runsRes = await fetch(`${API_BASE}/api/backtests`);
        const runsData = await runsRes.json();
        renderBacktestRunsList(runsData.runs || []);
      }
    }

    function renderSelectedBacktest(bt) {
      if (!bt) return;
      document.getElementById("kpiRunId").textContent = `#${bt.id}`;
      document.getElementById("kpiWinRate").textContent = `${bt.win_rate}%`;
      document.getElementById("kpiTrades").textContent = String(bt.total_trades);
      document.getElementById("kpiWL").textContent = `${bt.wins}W / ${bt.losses}L`;
      const pnlEl = document.getElementById("kpiNetPnl");
      pnlEl.textContent = `${bt.net_pnl_pts >= 0 ? "+" : ""}$${bt.net_pnl_pts.toFixed(2)}`;
      pnlEl.style.color = bt.net_pnl_pts >= 0 ? "var(--buy)" : "var(--sell)";
      document.getElementById("kpiPF").textContent = String(bt.profit_factor);
      document.getElementById("kpiDD").textContent = `-$${bt.max_drawdown_pts.toFixed(2)}`;
      const expEl = document.getElementById("kpiExp");
      expEl.textContent = `${bt.expectancy_pts >= 0 ? "+" : ""}$${bt.expectancy_pts.toFixed(2)}`;
      expEl.style.color = bt.expectancy_pts >= 0 ? "var(--buy)" : "var(--sell)";

      document.getElementById("eqSubtitle").textContent =
        `Run #${bt.id} · ${bt.symbol} (${bt.timeframe}) · ${bt.strategy_mode} · ${bt.bars_tested} Bars · Avg Win: +$${bt.avg_win.toFixed(2)} / Avg Loss: -$${bt.avg_loss.toFixed(2)}`;

      const tbody = document.querySelector("#tradesTable tbody");
      tbody.innerHTML = "";
      (bt.trades || []).forEach((t, idx) => {
        const isWin = t.outcome.startsWith("WIN");
        const shortEntry = t.entry_time.replace(" UTC+7", "").slice(5);
        const shortExit = t.exit_time.replace(" UTC+7", "").slice(11);
        tbody.innerHTML += `
          <tr>
            <td style="color:var(--text-2);">${idx + 1}</td>
            <td>${shortEntry} → ${shortExit}</td>
            <td><strong style="color:${t.direction === 'BUY' ? 'var(--buy)' : 'var(--sell)'};">${t.direction}</strong> <span style="font-size:10px;color:var(--text-2);">(${t.signal_type})</span></td>
            <td>${t.entry_price.toFixed(2)}</td>
            <td>${t.sl_price.toFixed(1)} / ${t.tp1_price.toFixed(1)}</td>
            <td>${t.exit_price.toFixed(2)}</td>
            <td class="${isWin ? 'tag-win' : 'tag-loss'}">${t.outcome}</td>
            <td class="${isWin ? 'tag-win' : 'tag-loss'}">${t.pnl_pts >= 0 ? "+" : ""}$${t.pnl_pts.toFixed(2)}</td>
            <td style="font-weight:700;color:${t.cum_pnl_pts >= 0 ? 'var(--gold)' : 'var(--sell)'};">${t.cum_pnl_pts >= 0 ? "+" : ""}$${t.cum_pnl_pts.toFixed(2)}</td>
          </tr>
        `;
      });

      drawEquityCurve(bt.equity_curve || []);
    }

    function drawEquityCurve(eqPoints) {
      const dpr = window.devicePixelRatio || 1;
      const rect = equityCanvas.getBoundingClientRect();
      const width = rect.width || 900;
      const height = 150;
      equityCanvas.width = width * dpr;
      equityCanvas.height = height * dpr;
      const ctx = equityCanvas.getContext("2d");
      ctx.scale(dpr, dpr);

      ctx.fillStyle = "#090c10";
      ctx.fillRect(0, 0, width, height);

      if (!eqPoints.length) {
        ctx.fillStyle = "#6e7f99";
        ctx.font = "12px sans-serif";
        ctx.fillText("No trades in this backtest run.", 20, height / 2);
        return;
      }

      const padL = 16, padR = 64, padT = 16, padB = 18;
      const plotW = width - padL - padR;
      const plotH = height - padT - padB;

      const vals = [0, ...eqPoints.map(p => p.cum_pnl_pts)];
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
      const lineCol = lastVal >= 0 ? "#10b981" : "#f43f5e";
      const grad = ctx.createLinearGradient(0, padT, 0, height - padB);
      grad.addColorStop(0, lastVal >= 0 ? "rgba(16, 185, 129, 0.28)" : "rgba(244, 63, 94, 0.28)");
      grad.addColorStop(1, "rgba(9, 12, 16, 0.0)");

      ctx.beginPath();
      vals.forEach((v, idx) => {
        const x = padL + idx * stepX;
        const y = yOf(v);
        if (idx === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
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
        if (idx === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      });
      ctx.stroke();

      if (vals.length <= 120) {
        vals.forEach((v, idx) => {
          if (idx === 0) return;
          const x = padL + idx * stepX;
          const y = yOf(v);
          const isWin = eqPoints[idx - 1].outcome.startsWith("WIN");
          ctx.fillStyle = isWin ? "#10b981" : "#f43f5e";
          ctx.beginPath();
          ctx.arc(x, y, 2.4, 0, Math.PI * 2);
          ctx.fill();
        });
      }

      ctx.fillStyle = "#a9b6cc";
      ctx.font = "11px sans-serif";
      ctx.fillText(`+$${maxV.toFixed(1)}`, width - padR + 6, padT + 8);
      ctx.fillText(`$0.0`, width - padR + 6, yZero + 4);
      ctx.fillText(`$${minV.toFixed(1)}`, width - padR + 6, height - padB);
    }

    function renderLiveSignalsTable(signals) {
      const tbody = document.querySelector("#liveSignalsTable tbody");
      tbody.innerHTML = "";
      signals.forEach(s => {
        const isBuy = s.direction === "BUY";
        let statusBadge = `<span style="color:var(--gold);font-weight:700;">🔒 ACTIVE (Locked)</span>`;
        if (s.status === "HIT_TP1" || s.status === "HIT_TP2") {
          statusBadge = `<span class="tag-win">${s.status} @ ${s.outcome_price ? s.outcome_price.toFixed(2) : ''}</span>`;
        } else if (s.status === "HIT_SL") {
          statusBadge = `<span class="tag-loss">HIT_SL @ ${s.outcome_price ? s.outcome_price.toFixed(2) : ''}</span>`;
        } else if (s.status === "MANUAL_CLOSE") {
          statusBadge = `<span style="color:var(--text-1);">MANUAL_CLOSE</span>`;
        }
        const pnl = s.pnl_pts || 0;
        tbody.innerHTML += `
          <tr>
            <td>#${s.id}</td>
            <td>${s.candle_time}</td>
            <td><span style="color:var(--gold);font-weight:700;">${s.trading_style || 'SWING'}</span> · <strong>${s.symbol}</strong> (${s.timeframe})</td>
            <td>
              <span style="font-weight:700;color:${isBuy ? 'var(--buy)' : 'var(--sell)'};">${s.signal}</span>
              <div style="font-size:10px;color:#c084fc;">AI Gate: ${s.ai_verdict || 'APPROVED'}</div>
            </td>
            <td>${s.confidence}%</td>
            <td>${s.entry_price.toFixed(2)}</td>
            <td style="color:var(--sell);">${s.sl_price.toFixed(2)}</td>
            <td style="color:var(--buy);">${s.tp1_price.toFixed(2)} / ${s.tp2_price.toFixed(2)}</td>
            <td>${statusBadge}</td>
            <td style="font-weight:700;color:${pnl > 0 ? 'var(--buy)' : pnl < 0 ? 'var(--sell)' : 'var(--text-2)'};">${pnl !== 0 ? (pnl > 0 ? '+' : '') + '$' + pnl.toFixed(2) : '--'}</td>
          </tr>
        `;
      });
    }

    function updateCalculator(syncFromSignal = false) {
      if (!currentData) return;
      const entryInput = document.getElementById("calcEntry");
      const slInput = document.getElementById("calcSL");
      if (syncFromSignal || !entryInput.value) {
        entryInput.value = currentData.entry.toFixed(2);
        slInput.value = currentData.stop_loss.toFixed(2);
      }
      const balance = parseFloat(document.getElementById("calcBalance").value) || 10000;
      const riskPct = parseFloat(document.getElementById("calcRiskPct").value) || 1.0;
      const entry = parseFloat(entryInput.value) || currentData.entry;
      const sl = parseFloat(slInput.value) || currentData.stop_loss;

      const riskUsd = balance * (riskPct / 100.0);
      const stopDist = Math.max(Math.abs(entry - sl), 0.05);
      const oz = riskUsd / stopDist;
      const lots = oz / 100.0;

      const tp1Dist = Math.abs(currentData.take_profit_1 - entry);
      const tp2Dist = Math.abs(currentData.take_profit_2 - entry);

      document.getElementById("resRiskUsd").textContent = `$${riskUsd.toFixed(2)}`;
      document.getElementById("resStopDist").textContent = `$${stopDist.toFixed(2)}`;
      document.getElementById("resOz").textContent = `${oz.toFixed(2)} oz`;
      document.getElementById("resLots").textContent = `${lots.toFixed(2)} lots`;
      document.getElementById("resProfitTp1").textContent = `+$${(oz * tp1Dist).toFixed(2)}`;
      document.getElementById("resProfitTp2").textContent = `+$${(oz * tp2Dist).toFixed(2)}`;
    }

    function checkCustomAlert(price) {
      if (!customAlertPrice) return;
      const banner = document.getElementById("alertBanner");
      if (Math.abs(price - customAlertPrice) <= 1.2) {
        banner.style.display = "block";
        banner.textContent = `PRICE ALERT TRIGGERED: ${currentSymbol} is at $${price.toFixed(2)} (Target: $${customAlertPrice.toFixed(2)})`;
        playBeep(1046, 0.35);
      }
    }

    function drawCharts() {
      if (!currentData || !currentData.series) return;
      const s = currentData.series;
      const candles = s.candles;
      if (!candles.length) return;

      const dpr = window.devicePixelRatio || 1;
      const rect = priceCanvas.getBoundingClientRect();
      const width = rect.width || 900;
      const height = 340;
      priceCanvas.width = width * dpr;
      priceCanvas.height = height * dpr;
      const ctx = priceCanvas.getContext("2d");
      ctx.scale(dpr, dpr);

      ctx.fillStyle = "#090c10";
      ctx.fillRect(0, 0, width, height);

      const padLeft = 14;
      const padRight = 72;
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

      ctx.strokeStyle = "rgba(38, 50, 70, 0.45)";
      ctx.lineWidth = 1;
      for (let g = 0; g <= 5; g++) {
        const pVal = minP + ((maxP - minP) * g) / 5;
        const y = yOf(pVal);
        ctx.beginPath();
        ctx.moveTo(padLeft, y);
        ctx.lineTo(width - padRight, y);
        ctx.stroke();

        ctx.fillStyle = "#6e7f99";
        ctx.font = "11px -apple-system, sans-serif";
        ctx.fillText(pVal.toFixed(2), width - padRight + 6, y + 4);
      }

      if (showBB) {
        ctx.strokeStyle = "rgba(148, 163, 184, 0.3)";
        ctx.setLineDash([3, 3]);
        ["bb_upper", "bb_lower"].forEach(key => {
          ctx.beginPath();
          s[key].forEach((val, idx) => {
            const x = padLeft + idx * stepX + stepX / 2;
            const y = yOf(val);
            if (idx === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
          });
          ctx.stroke();
        });
        ctx.setLineDash([]);
      }

      const candleW = Math.max(2, stepX * 0.62);
      candles.forEach((c, idx) => {
        const xCenter = padLeft + idx * stepX + stepX / 2;
        const isBull = c.close >= c.open;
        ctx.strokeStyle = isBull ? "#10b981" : "#f43f5e";
        ctx.fillStyle = isBull ? "#10b981" : "#f43f5e";

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
          if (idx === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        });
        ctx.stroke();
      };
      drawLine(s.ema9, "#38bdf8", 1.5);
      drawLine(s.ema21, "#f5c451", 1.6);
      drawLine(s.ema50, "#a855f7", 1.6);

      if (showSignalLines) {
        const pl = currentData.position_lock || {};
        const at = (pl.locked && pl.active_trade) ? pl.active_trade : null;
        const levels = [
          { val: at ? at.entry_price : currentData.entry, col: "#f5c451", lbl: at ? `LOCKED ENTRY #${at.id}` : "REF ENTRY" },
          { val: at ? at.sl_price : currentData.stop_loss, col: "#f43f5e", lbl: "SL" },
          { val: at ? at.tp1_price : currentData.take_profit_1, col: "#10b981", lbl: "TP1 (BE)" },
          { val: at ? at.tp2_price : currentData.take_profit_2, col: "#34d399", lbl: "TP2" }
        ];
        levels.forEach(lv => {
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
          ctx.font = "bold 10px -apple-system, sans-serif";
          ctx.fillText(`${lv.lbl} ${lv.val.toFixed(2)}`, padLeft + 6, y - 4);
        });
      }

      if (hoverIdx !== null && hoverIdx >= 0 && hoverIdx < candles.length) {
        const hx = padLeft + hoverIdx * stepX + stepX / 2;
        ctx.strokeStyle = "rgba(245, 196, 81, 0.5)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(hx, padTop);
        ctx.lineTo(hx, height - padBottom);
        ctx.stroke();
      }

      drawOscillator(width, dpr, stepX, padLeft, padRight);
    }

    function drawOscillator(width, dpr, stepX, padLeft, padRight) {
      const s = currentData.series;
      const height = 110;
      oscCanvas.width = width * dpr;
      oscCanvas.height = height * dpr;
      const ctx = oscCanvas.getContext("2d");
      ctx.scale(dpr, dpr);

      ctx.fillStyle = "#090c10";
      ctx.fillRect(0, 0, width, height);

      const padTop = 14;
      const padBottom = 16;
      const plotH = height - padTop - padBottom;

      if (oscMode === "RSI") {
        const yOf = (v) => padTop + plotH * (1 - v / 100);
        [70, 50, 30].forEach(lv => {
          const y = yOf(lv);
          ctx.strokeStyle = lv === 50 ? "rgba(38,50,70,0.5)" : "rgba(245,196,81,0.3)";
          ctx.setLineDash([3, 3]);
          ctx.beginPath();
          ctx.moveTo(padLeft, y);
          ctx.lineTo(width - padRight, y);
          ctx.stroke();
          ctx.setLineDash([]);
          ctx.fillStyle = "#6e7f99";
          ctx.font = "10px sans-serif";
          ctx.fillText(String(lv), width - padRight + 6, y + 3);
        });

        ctx.strokeStyle = "#38bdf8";
        ctx.lineWidth = 1.6;
        ctx.beginPath();
        s.rsi14.forEach((v, idx) => {
          const x = padLeft + idx * stepX + stepX / 2;
          const y = yOf(v);
          if (idx === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        });
        ctx.stroke();

        ctx.fillStyle = "#a9b6cc";
        ctx.font = "bold 10px sans-serif";
        ctx.fillText(`RSI(14): ${s.rsi14[s.rsi14.length - 1].toFixed(1)}`, padLeft + 6, 12);
      } else {
        const allVals = [...s.macd, ...s.macd_signal, ...s.macd_hist];
        const maxAbs = Math.max(...allVals.map(v => Math.abs(v)), 0.5) * 1.15;
        const yOf = (v) => padTop + plotH * (0.5 - v / (2 * maxAbs));
        const yZero = yOf(0);

        ctx.strokeStyle = "rgba(38,50,70,0.6)";
        ctx.beginPath();
        ctx.moveTo(padLeft, yZero);
        ctx.lineTo(width - padRight, yZero);
        ctx.stroke();

        const barW = Math.max(2, stepX * 0.55);
        s.macd_hist.forEach((v, idx) => {
          const x = padLeft + idx * stepX + stepX / 2;
          const y = yOf(v);
          ctx.fillStyle = v >= 0 ? "rgba(16, 185, 129, 0.55)" : "rgba(244, 63, 94, 0.55)";
          ctx.fillRect(x - barW / 2, Math.min(y, yZero), barW, Math.max(1, Math.abs(y - yZero)));
        });

        const drawM = (arr, col) => {
          ctx.strokeStyle = col;
          ctx.lineWidth = 1.4;
          ctx.beginPath();
          arr.forEach((v, idx) => {
            const x = padLeft + idx * stepX + stepX / 2;
            const y = yOf(v);
            if (idx === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
          });
          ctx.stroke();
        };
        drawM(s.macd, "#38bdf8");
        drawM(s.macd_signal, "#f5c451");

        ctx.fillStyle = "#a9b6cc";
        ctx.font = "bold 10px sans-serif";
        ctx.fillText(`MACD(12,26,9) Hist: ${s.macd_hist[s.macd_hist.length - 1].toFixed(2)}`, padLeft + 6, 12);
      }
    }

    priceCanvas.addEventListener("mousemove", (e) => {
      if (!currentData || !currentData.series) return;
      const rect = priceCanvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const candles = currentData.series.candles;
      const plotW = rect.width - 14 - 72;
      const stepX = plotW / candles.length;
      const idx = Math.floor((x - 14) / stepX);
      if (idx >= 0 && idx < candles.length) {
        hoverIdx = idx;
        const c = candles[idx];
        const r = currentData.series.rsi14[idx];
        document.getElementById("hoverReadout").textContent =
          `${c.time_local || c.time} | O: ${c.open.toFixed(2)} H: ${c.high.toFixed(2)} L: ${c.low.toFixed(2)} C: ${c.close.toFixed(2)} | RSI: ${r.toFixed(1)}`;
        drawCharts();
      }
    });

    priceCanvas.addEventListener("mouseleave", () => {
      hoverIdx = null;
      document.getElementById("hoverReadout").textContent = "Hover chart to inspect candle (UTC+7)";
      drawCharts();
    });

    function switchTradingStyle(style) {
      currentStyle = style;
      const cfg = STYLE_DEFAULTS[style] || STYLE_DEFAULTS.SWING;
      currentTf = cfg.tf;

      document.querySelectorAll("#styleGroup .style-btn").forEach(b => {
        b.classList.toggle("active", b.dataset.style === style);
      });
      document.querySelectorAll("#tfGroup .tf-btn").forEach(b => {
        b.classList.toggle("active", b.dataset.tf === currentTf);
      });

      document.getElementById("btTradingStyle").value = style;
      document.getElementById("btInterval").value = currentTf;
      document.getElementById("btSlMult").value = cfg.sl;
      document.getElementById("btTp1Mult").value = cfg.tp1;
      document.getElementById("btTp2Mult").value = cfg.tp2;

      selectedRunDetail = null;
      fetchFullDashboard();
      showToast(`Switched to ${cfg.label} (${currentTf} default)`);
    }

    function switchTimeframe(tf) {
      currentTf = tf;
      document.querySelectorAll("#tfGroup .tf-btn").forEach(b => {
        b.classList.toggle("active", b.dataset.tf === tf);
      });
      document.getElementById("btInterval").value = tf;
      selectedRunDetail = null;
      fetchFullDashboard();
    }

    document.querySelectorAll("#styleGroup .style-btn").forEach(btn => {
      btn.addEventListener("click", () => switchTradingStyle(btn.dataset.style));
    });

    document.querySelectorAll("#tfGroup .tf-btn").forEach(btn => {
      btn.addEventListener("click", () => switchTimeframe(btn.dataset.tf));
    });

    document.getElementById("btTradingStyle").addEventListener("change", (e) => {
      const cfg = STYLE_DEFAULTS[e.target.value] || STYLE_DEFAULTS.SWING;
      document.getElementById("btInterval").value = cfg.tf;
      document.getElementById("btSlMult").value = cfg.sl;
      document.getElementById("btTp1Mult").value = cfg.tp1;
      document.getElementById("btTp2Mult").value = cfg.tp2;
    });

    document.getElementById("symbolSelect").addEventListener("change", (e) => {
      currentSymbol = e.target.value;
      document.getElementById("btSymbol").value = currentSymbol;
      selectedRunDetail = null;
      fetchFullDashboard();
      pollLiveTick();
    });

    document.getElementById("refreshBtn").addEventListener("click", () => {
      fetchFullDashboard();
      pollLiveTick();
      showToast("Synced with TradingView & AI Agent Gate!");
    });

    document.getElementById("refreshNewsBtn").addEventListener("click", async () => {
      const res = await fetch(`${API_BASE}/api/fundamentals?force=1`);
      const data = await res.json();
      renderFundamentals(data);
      showToast("Refreshed Macro DXY & Live News!");
    });

    document.getElementById("closePosBtn").addEventListener("click", async () => {
      await fetch(`${API_BASE}/api/position/close`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol: currentSymbol, timeframe: currentTf })
      });
      showToast("Closed active position — scanner unlocked!");
      fetchFullDashboard();
    });

    // Telegram Bot Buttons
    document.getElementById("tgSyncBtn").addEventListener("click", async () => {
      const chatId = document.getElementById("tgChatIdInput").value.trim();
      const res = await fetch(`${API_BASE}/api/telegram/sync`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chat_id: chatId })
      });
      const data = await res.json();
      renderTelegramStatus(data);
      const count = (data.subscribers || []).length;
      showToast(count > 0 ? `Synced! ${count} Telegram Chat(s) connected.` : "Polled @this_is_ai_signal_bot — send /start in Telegram to register!");
    });

    async function triggerTelegramBroadcast() {
      const chatId = document.getElementById("tgChatIdInput").value.trim();
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
        showToast(`Sent ${currentStyle} AI Signal to ${data.broadcast.sent} Telegram chat(s)!`);
      } else {
        showToast(data.broadcast?.error || "Open @this_is_ai_signal_bot in Telegram and send /start first!");
      }
    }

    document.getElementById("tgSendNowBtn").addEventListener("click", triggerTelegramBroadcast);
    document.getElementById("quickSendTgBtn").addEventListener("click", triggerTelegramBroadcast);

    document.getElementById("tgAutoNotifyChk").addEventListener("change", async (e) => {
      const res = await fetch(`${API_BASE}/api/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ telegram_auto_notify: e.target.checked })
      });
      const data = await res.json();
      if (data.telegram) renderTelegramStatus(data.telegram);
      showToast(`Telegram Auto-Notify: ${e.target.checked ? "ENABLED" : "DISABLED"}`);
    });

    document.getElementById("saveGeminiKeyBtn").addEventListener("click", async () => {
      const k = document.getElementById("geminiKeyInput").value.trim();
      await fetch(`${API_BASE}/api/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ gemini_api_key: k })
      });
      showToast(k ? "Saved Gemini 4 Argon API key — syncing AI Agent..." : "Reverted to Built-in 3-Agent Committee");
      fetchFullDashboard();
    });

    document.getElementById("toggleBBBtn").addEventListener("click", (e) => {
      showBB = !showBB;
      e.currentTarget.textContent = `Bollinger Bands: ${showBB ? "ON" : "OFF"}`;
      drawCharts();
    });

    document.getElementById("toggleLevelsBtn").addEventListener("click", (e) => {
      showSignalLines = !showSignalLines;
      e.currentTarget.textContent = `Signal Lines: ${showSignalLines ? "ON" : "OFF"}`;
      drawCharts();
    });

    document.getElementById("switchOscBtn").addEventListener("click", (e) => {
      oscMode = oscMode === "RSI" ? "MACD" : "RSI";
      e.currentTarget.textContent = `Oscillator: ${oscMode === "RSI" ? "RSI (14)" : "MACD (12,26,9)"}`;
      drawCharts();
    });

    document.getElementById("copySignalBtn").addEventListener("click", () => {
      if (!currentData) return;
      const ai = currentData.ai_agent || {};
      const txt = `${currentData.symbol} (${currentData.trading_style} · ${currentData.timeframe})\nSignal: ${currentData.signal}\nAI Gate: ${ai.verdict_badge || 'APPROVED'} (${currentData.confidence}%)\nEntry: ${currentData.entry.toFixed(2)}\nSL: ${currentData.stop_loss.toFixed(2)}\nTP1: ${currentData.take_profit_1.toFixed(2)}\nTP2: ${currentData.take_profit_2.toFixed(2)}\nAI Summary: ${ai.executive_summary || ''}`;
      navigator.clipboard.writeText(txt);
      showToast("AI-Vetted Signal copied to clipboard!");
    });

    document.getElementById("runBacktestBtn").addEventListener("click", async () => {
      const btn = document.getElementById("runBacktestBtn");
      btn.textContent = "Running Deep Backtest...";
      btn.disabled = true;
      try {
        const payload = {
          trading_style: document.getElementById("btTradingStyle").value,
          symbol: document.getElementById("btSymbol").value,
          interval: document.getElementById("btInterval").value,
          strategy_mode: document.getElementById("btStrategy").value,
          duration_preset: document.getElementById("btDuration").value,
          sl_mult: parseFloat(document.getElementById("btSlMult").value),
          tp1_mult: parseFloat(document.getElementById("btTp1Mult").value),
          tp2_mult: parseFloat(document.getElementById("btTp2Mult").value)
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
          showToast(`Saved ${payload.trading_style} Run #${data.detail.id} (${data.detail.bars_tested} bars) to SQLite!`);
        }
      } catch (err) {
        console.error(err);
      } finally {
        btn.textContent = "Run & Save to Database";
        btn.disabled = false;
      }
    });

    ["filterDirection", "filterOutcome"].forEach(id => {
      document.getElementById(id).addEventListener("change", () => {
        if (selectedRunDetail) {
          loadBacktestRun(selectedRunDetail.id);
        }
      });
    });

    document.getElementById("tabDbBacktestBtn").addEventListener("click", () => {
      document.getElementById("tabDbBacktestBtn").classList.add("active");
      document.getElementById("tabDbLiveSignalsBtn").classList.remove("active");
      document.getElementById("dbBacktestSection").style.display = "block";
      document.getElementById("dbLiveSignalsSection").style.display = "none";
      if (selectedRunDetail) drawEquityCurve(selectedRunDetail.equity_curve || []);
    });

    document.getElementById("tabDbLiveSignalsBtn").addEventListener("click", async () => {
      document.getElementById("tabDbLiveSignalsBtn").classList.add("active");
      document.getElementById("tabDbBacktestBtn").classList.remove("active");
      document.getElementById("dbLiveSignalsSection").style.display = "block";
      document.getElementById("dbBacktestSection").style.display = "none";
      const res = await fetch(`${API_BASE}/api/live_signals`);
      const data = await res.json();
      renderLiveSignalsTable(data.signals || []);
    });

    document.getElementById("exportCsvBtn").addEventListener("click", () => {
      if (!selectedRunDetail || !selectedRunDetail.trades) return;
      const rows = [
        ["Trade #", "Run ID", "Symbol", "Timeframe", "Entry Time", "Exit Time", "Direction", "Signal Type", "Entry", "SL", "TP1", "TP2", "Exit", "Outcome", "PnL Pts", "Cum PnL Pts"]
      ];
      selectedRunDetail.trades.forEach((t, i) => {
        rows.push([
          i + 1, t.run_id, t.symbol, t.timeframe, t.entry_time, t.exit_time,
          t.direction, t.signal_type, t.entry_price, t.sl_price, t.tp1_price, t.tp2_price,
          t.exit_price, t.outcome, t.pnl_pts, t.cum_pnl_pts
        ]);
      });
      const csv = rows.map(r => r.join(",")).join("\n");
      const blob = new Blob([csv], { type: "text/csv" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `gold_backtest_run_${selectedRunDetail.id}.csv`;
      a.click();
      showToast(`Exported Run #${selectedRunDetail.id} CSV!`);
    });

    ["calcBalance", "calcRiskPct", "calcEntry", "calcSL"].forEach(id => {
      document.getElementById(id).addEventListener("input", () => updateCalculator(false));
    });

    document.getElementById("setAlertBtn").addEventListener("click", () => {
      const val = parseFloat(document.getElementById("alertPriceInput").value);
      if (!isNaN(val) && val > 0) {
        customAlertPrice = val;
        document.getElementById("activeAlertStatus").textContent = `Alert active for ${currentSymbol} @ $${val.toFixed(2)}`;
        document.getElementById("activeAlertStatus").style.color = "var(--gold)";
        showToast(`Price alert set for $${val.toFixed(2)}`);
      }
    });

    window.addEventListener("resize", () => {
      drawCharts();
      if (selectedRunDetail) drawEquityCurve(selectedRunDetail.equity_curve || []);
    });

    setInterval(updateClocksAndCountdown, 1000);
    updateClocksAndCountdown();

    setInterval(pollLiveTick, 2000);

    setInterval(() => {
      if (streamEnabled) fetchFullDashboard();
    }, 20000);

    fetchFullDashboard();
    pollLiveTick();
