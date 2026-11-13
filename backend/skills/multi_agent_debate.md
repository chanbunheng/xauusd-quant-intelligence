---
name: multi-agent-debate
description: TradingAgents-inspired 3-Agent Bull vs. Bear Debate and Chief Risk Officer Judge workflow.
---

# Multi-Agent Debate Protocol (Bull vs. Bear vs. Judge)

Modeled on institutional trading desk workflows (`TauricResearch/TradingAgents` & `HKUDS/AI-Trader`):

## 1. Bullish Technical & Structure Analyst
- Evaluates EMA 9/21/50/200 alignment, Higher-Timeframe TradingView Scanner consensus (`15m`, `1h`, `4h`, `1D`), Fibonacci Golden Pocket (`38.2%–61.8%`), Order Blocks, and Fair Value Gaps.
- Presents the strongest objective evidence **in favor** of the candidate direction (or identifies the next high-probability watch zone if `WAIT`).

## 2. Bearish Macro & Risk Critic
- Actively challenges the setup to prevent false breakouts and overtrading:
  - Checks `TVC:DXY` inverse correlation and Reuters/Dow Jones wire sentiment.
  - Checks RSI exhaustion (`>= 74` overbought / `<= 26` oversold).
  - Checks ICT Killzone liquidity grade (flags low-volume off-session traps).
  - Checks High-Impact Macro Events (FOMC, CPI, NFP, Powell).

## 3. Chief Risk Officer (CRO) Judge
- Weighs Bull Case vs. Bear Case.
- **VETOES** to `WAIT` if severe macro conflict, 4+ HTF counter-trend conflict, or extreme RSI chase is detected.
- **APPROVES** only when structure, risk-to-reward, and macro guardrails align.
