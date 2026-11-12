import type { MarketTick, TradingSignalPayload, TradingStyle, Timeframe } from '../../types/trading'

export interface MarketServiceContract {
  getLiveTick(symbol: string): Promise<MarketTick>
  analyzeTimeframe(symbol: string, interval: Timeframe, style: TradingStyle): Promise<TradingSignalPayload>
  getMultiTimeframeMatrix(symbol: string, style: TradingStyle): Promise<Record<string, unknown>>
  getFundamentals(force?: boolean): Promise<Record<string, unknown>>
}

export interface SignalLedgerServiceContract {
  getLiveSignals(): Promise<Record<string, unknown>[]>
  closeActivePosition(symbol: string, timeframe: Timeframe): Promise<{ ok: boolean }>
}
