export type TradingStyle = 'SWING' | 'INTRADAY' | 'SCALPING' | 'POSITION'
export type Timeframe = '1m' | '5m' | '15m' | '1h' | '4h' | '1d'
export type SignalDirection = 'BUY' | 'SELL' | 'NEUTRAL'
export type DataOrigin = 'LIVE' | 'PAPER' | 'MOCK_PREVIEW'

export interface MarketTick {
  symbol: string
  price: number
  change: number
  change_pct: number
  high: number
  low: number
  bid: number
  ask: number
  spread: number
  timestamp_utc7: string
  origin: DataOrigin
}

export interface AgentMemberReport {
  name: string
  role: string
  stance: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | 'APPROVED' | 'HOLD FIRE' | 'VETOED'
  score: number
  note: string
}

export interface AiCommitteeAssessment {
  verdict: string
  verdict_label: string
  approved: boolean
  confidence: number
  model_used: string
  executive_summary: string
  risk_management_note: string
  committee: AgentMemberReport[]
}

export interface TradingSignalPayload {
  symbol: string
  timeframe: Timeframe
  trading_style: TradingStyle
  trading_style_label: string
  current_price: number
  direction: SignalDirection
  signal: string
  confidence: number
  entry: number
  stop_loss: number
  take_profit_1: number
  take_profit_2: number
  risk_reward_tp1: number
  risk_reward_tp2: number
  rationale: string
  ai_agent: AiCommitteeAssessment
  last_candle_time: string
}

export interface FeatureFlagsConfig {
  aiSignals: boolean
  aiAgentsCommittee: boolean
  telegramBotHub: boolean
  deepBacktesting: boolean
  aiAssistant: boolean
  strategyLab: boolean
  paperOrderSimulator: boolean
  advancedRisk: boolean
  socialTrading: boolean
}
