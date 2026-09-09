import { ProviderHealth, DataFreshness } from '../types'

const healthRegistry: Map<string, ProviderHealth> = new Map([
  [
    'yahoo_market',
    {
      id: 'yahoo_market',
      name: 'Yahoo Finance Market Data Feed',
      endpoint: 'https://query1.finance.yahoo.com/v8/finance/chart/',
      status: 'ONLINE',
      latencyMs: 142,
      lastSuccessfulSync: new Date().toISOString(),
      freshness: 'LIVE',
      errorCount: 0
    }
  ],
  [
    'amfi_nav',
    {
      id: 'amfi_nav',
      name: 'AMFI Official Daily NAV Feed',
      endpoint: 'https://api.mfapi.in/mf/',
      status: 'ONLINE',
      latencyMs: 195,
      lastSuccessfulSync: new Date().toISOString(),
      freshness: 'END_OF_DAY',
      errorCount: 0
    }
  ],
  [
    'zerodha_margins',
    {
      id: 'zerodha_margins',
      name: 'Zerodha Kite Open Margins API',
      endpoint: 'https://api.kite.trade/margins/equity',
      status: 'ONLINE',
      latencyMs: 110,
      lastSuccessfulSync: new Date().toISOString(),
      freshness: 'LIVE',
      errorCount: 0
    }
  ],
  [
    'google_news',
    {
      id: 'google_news',
      name: 'Financial News RSS Aggregator',
      endpoint: 'https://news.google.com/rss/search',
      status: 'ONLINE',
      latencyMs: 230,
      lastSuccessfulSync: new Date().toISOString(),
      freshness: 'LIVE',
      errorCount: 0
    }
  ],
  [
    'rbi_macro',
    {
      id: 'rbi_macro',
      name: 'RBI & Macro Historical Archive',
      endpoint: 'Local Verified Point-in-Time Dataset',
      status: 'ONLINE',
      latencyMs: 8,
      lastSuccessfulSync: new Date().toISOString(),
      freshness: 'LIVE',
      errorCount: 0
    }
  ]
])

export function getProviderHealthList(): ProviderHealth[] {
  return Array.from(healthRegistry.values())
}

export function recordProviderSuccess(id: string, latencyMs: number, freshness: DataFreshness) {
  const p = healthRegistry.get(id)
  if (p) {
    p.status = 'ONLINE'
    p.latencyMs = Math.round((p.latencyMs * 0.7) + (latencyMs * 0.3))
    p.lastSuccessfulSync = new Date().toISOString()
    p.freshness = freshness
  }
}

export function recordProviderError(id: string) {
  const p = healthRegistry.get(id)
  if (p) {
    p.errorCount += 1
    if (p.errorCount >= 3) {
      p.status = 'DEGRADED'
    }
    if (p.errorCount >= 7) {
      p.status = 'OFFLINE'
    }
  }
}

export function computeDataQualityScore(freshness: DataFreshness, eventCount: number, hasPrice: boolean): number {
  let score = 70

  if (freshness === 'LIVE') score += 20
  else if (freshness === 'DELAYED') score += 12
  else if (freshness === 'END_OF_DAY') score += 15
  else if (freshness === 'HISTORICAL') score += 5
  else score -= 40 // UNAVAILABLE

  if (hasPrice) score += 5
  else score -= 25

  if (eventCount >= 3) score += 5
  else if (eventCount >= 1) score += 3

  const degradedCount = Array.from(healthRegistry.values()).filter((p) => p.status !== 'ONLINE').length
  score -= degradedCount * 8

  return Math.min(100, Math.max(0, score))
}
