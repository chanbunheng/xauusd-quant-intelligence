---
name: risk-execution-guard
description: Fixed dollar risk ($10 default) dynamic lot sizing from 0.01 lot and clean TP1/BE exit discipline.
---

# Risk & Execution Guardrails

1. **Dynamic Lot Sizing (`min 0.01 lot`, `$10` Default Risk):**
   - `lot_size = max(0.01, round(risk_usd / (sl_distance * contract_size), 2))`
   - Ensures every trade risks the same fixed USD amount regardless of ATR volatility width.
2. **Clean Exit Discipline:**
   - Default `TP1_ONLY`: 100% close at TP1 or SL (zero ambiguity).
   - Optional `BE_RUNNER`: 50% banked at TP1 + SL moved to Break-Even; TP2 blended at `(tp1 + tp2) / 2`.
3. **Strict Single-Position Lock:**
   - Never stack overlapping positions on the same symbol & timeframe while a trade is active.
