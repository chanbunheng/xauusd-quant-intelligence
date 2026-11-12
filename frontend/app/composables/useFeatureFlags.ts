import type { FeatureFlagsConfig } from '../types/trading'

export const DEFAULT_FEATURE_FLAGS: FeatureFlagsConfig = {
  aiSignals: true,           // LIVE: Connected to Railway /api/analyze
  aiAgentsCommittee: true,   // LIVE: 3-Agent Committee + Gemini 4 Argon
  telegramBotHub: true,      // LIVE: @this_is_ai_signal_bot + Supabase
  deepBacktesting: true,     // LIVE: SQLite / Supabase Backtest Engine
  aiAssistant: true,         // HYBRID: Live Market Context + Deterministic Quant Copilot
  strategyLab: true,         // PREVIEW + LIVE Backtest Presets
  paperOrderSimulator: true, // PAPER MODE: Position sizing & simulated order ticket
  advancedRisk: true,        // PREVIEW: Portfolio VaR & Killzone exposure analytics
  socialTrading: false,      // COMING SOON
}

export function useFeatureFlags() {
  return {
    flags: DEFAULT_FEATURE_FLAGS,
    isLiveFeature: (key: keyof FeatureFlagsConfig) =>
      ['aiSignals', 'aiAgentsCommittee', 'telegramBotHub', 'deepBacktesting'].includes(key),
  }
}
