import { AssetMetadata, AssetPricePoint, DataFreshness } from '../types'

export interface LiveMarketQuote {
  symbol: string
  price: number
  change: number
  changePct: number
  freshness: DataFreshness
  timestamp: string
  source: string
  volume?: number
}

// In-memory cache for historical and live data with TTL
let cachedAssets: AssetMetadata[] | null = null
let cachedHistoricalPrices: Record<string, AssetPricePoint[]> | null = null
const quoteCache: Map<string, { quote: LiveMarketQuote; fetchedAt: number }> = new Map()
const QUOTE_CACHE_TTL_MS = 15000 // 15 seconds TTL for market quotes

export async function loadAssetsMetadata(): Promise<AssetMetadata[]> {
  if (cachedAssets && cachedAssets.length > 0) return cachedAssets
  try {
    const res = await fetch('/data/market_intelligence/assets.json')
    if (res.ok) {
      const data = await res.json()
      cachedAssets = data
      return data
    }
  } catch (err) {
    console.warn('Could not fetch /data/market_intelligence/assets.json:', err)
  }
  return []
}

export async function loadHistoricalPrices(symbol: string): Promise<AssetPricePoint[]> {
  const all = await loadAllHistoricalPrices()
  return all[symbol] || []
}

export async function loadAllHistoricalPrices(): Promise<Record<string, AssetPricePoint[]>> {
  if (!cachedHistoricalPrices) {
    try {
      const res = await fetch('/data/market_intelligence/historical_prices.json')
      if (res.ok) {
        cachedHistoricalPrices = await res.json()
      }
    } catch (err) {
      console.warn('Could not fetch historical prices:', err)
      return {}
    }
  }
  return cachedHistoricalPrices || {}
}

export async function fetchLiveAssetQuote(asset: AssetMetadata): Promise<LiveMarketQuote> {
  const cached = quoteCache.get(asset.symbol)
  const now = Date.now()
  if (cached && now - cached.fetchedAt < QUOTE_CACHE_TTL_MS) {
    return cached.quote
  }

  // 1. Mutual Funds: Query AMFI official endpoint
  if (asset.asset_class === 'mutual_fund' && asset.amfi_code) {
    try {
      const res = await fetch(`https://api.mfapi.in/mf/${asset.amfi_code}`)
      if (res.ok) {
        const json = await res.json()
        if (json.data && json.data.length >= 2) {
          const latest = parseFloat(json.data[0].nav)
          const prev = parseFloat(json.data[1].nav)
          const change = +(latest - prev).toFixed(4)
          const changePct = +((change / prev) * 100).toFixed(2)
          const quote: LiveMarketQuote = {
            symbol: asset.symbol,
            price: latest,
            change,
            changePct,
            freshness: 'END_OF_DAY',
            timestamp: json.data[0].date,
            source: 'Official AMFI Daily NAV Archive'
          }
          quoteCache.set(asset.symbol, { quote, fetchedAt: now })
          return quote
        }
      }
    } catch {
      // Fall through to historical fallback
    }
  }

  // 2. Equities, ETFs, Commodities, Indices: Query Yahoo Finance proxy
  const encodedSym = encodeURIComponent(asset.symbol)
  const endpoint = `/api/yahoo/v8/finance/chart/${encodedSym}?range=5d&interval=1d`
  try {
    const res = await fetch(endpoint)
    if (res.ok) {
      const json = await res.json()
      const meta = json.chart?.result?.[0]?.meta
      if (meta && meta.regularMarketPrice !== undefined) {
        const p = meta.regularMarketPrice
        const prevClose = meta.chartPreviousClose || meta.previousClose || p
        const change = +(p - prevClose).toFixed(2)
        const changePct = prevClose > 0 ? +((change / prevClose) * 100).toFixed(2) : 0
        const isLive = Math.abs(now / 1000 - meta.regularMarketTime) < 3600

        const quote: LiveMarketQuote = {
          symbol: asset.symbol,
          price: p,
          change,
          changePct,
          freshness: isLive ? 'LIVE' : 'DELAYED',
          timestamp: new Date(meta.regularMarketTime * 1000).toISOString(),
          source: 'Yahoo Finance Market Data Feed',
          volume: meta.regularMarketVolume
        }
        quoteCache.set(asset.symbol, { quote, fetchedAt: now })
        return quote
      }
    }
  } catch {
    // Network or proxy unavailable
  }

  // 3. Fallback to latest verified point-in-time historical data with honest freshness label
  const hist = await loadHistoricalPrices(asset.symbol)
  if (hist.length > 0) {
    const last = hist[hist.length - 1]
    const prev = hist.length > 1 ? hist[hist.length - 2] : last
    const change = +(last.close - prev.close).toFixed(2)
    const changePct = prev.close > 0 ? +((change / prev.close) * 100).toFixed(2) : 0
    const quote: LiveMarketQuote = {
      symbol: asset.symbol,
      price: last.close,
      change,
      changePct,
      freshness: 'HISTORICAL' as DataFreshness,
      timestamp: last.date,
      source: 'Verified Point-in-Time Historical Dataset',
      volume: last.volume
    }
    quoteCache.set(asset.symbol, { quote, fetchedAt: now })
    return quote
  }

  // 4. Return explicit unavailable status (No mock or fake prices)
  return {
    symbol: asset.symbol,
    price: 0,
    change: 0,
    changePct: 0,
    freshness: 'UNAVAILABLE',
    timestamp: new Date().toISOString(),
    source: 'None'
  }
}
