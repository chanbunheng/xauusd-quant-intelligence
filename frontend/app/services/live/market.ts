import type { MarketServiceContract } from '../contracts/market'
import type { MarketTick, TradingSignalPayload, TradingStyle, Timeframe } from '../../types/trading'

export function createLiveMarketService(apiBase: string): MarketServiceContract {
  return {
    async getLiveTick(symbol: string): Promise<MarketTick> {
      const res = await fetch(`${apiBase}/api/tick?symbol=${encodeURIComponent(symbol)}`)
      const data = await res.json()
      return { ...data, origin: 'LIVE' }
    },
    async analyzeTimeframe(symbol: string, interval: Timeframe, style: TradingStyle): Promise<TradingSignalPayload> {
      const res = await fetch(
        `${apiBase}/api/analyze?symbol=${encodeURIComponent(symbol)}&interval=${interval}&style=${style}`
      )
      return await res.json()
    },
    async getMultiTimeframeMatrix(symbol: string, style: TradingStyle) {
      const res = await fetch(
        `${apiBase}/api/mtf?symbol=${encodeURIComponent(symbol)}&style=${style}`
      )
      return await res.json()
    },
    async getFundamentals(force = false) {
      const res = await fetch(`${apiBase}/api/fundamentals${force ? '?force=1' : ''}`)
      return await res.json()
    },
  }
}
