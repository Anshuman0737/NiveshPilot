/**
 * Zerodha Kite Free Public Market Integration Service
 * Utilizes official Zerodha open endpoints (https://api.kite.trade)
 * Zero authentication required, ₹0 cost.
 */

export interface ZerodhaMarginInfo {
  tradingsymbol: string
  mis_multiplier: number
  mis_margin_pct: number
  co_lower?: number
  co_upper?: number
  leverageDesc: string
}

// In-memory cache for ultra-fast instant lookups
let zerodhaMarginCache: Map<string, ZerodhaMarginInfo> | null = null

// Fallback baseline for top Indian heavyweights
const BASELINE_ZERODHA_MARGINS: Record<string, { multiplier: number; marginPct: number }> = {
  RELIANCE: { multiplier: 5, marginPct: 20 },
  HDFCBANK: { multiplier: 5, marginPct: 20 },
  ICICIBANK: { multiplier: 5, marginPct: 20 },
  TCS: { multiplier: 5, marginPct: 20 },
  INFY: { multiplier: 5, marginPct: 20 },
  ITC: { multiplier: 5, marginPct: 20 },
  SBIN: { multiplier: 5, marginPct: 20 },
  LT: { multiplier: 5, marginPct: 20 },
  BHARTIARTL: { multiplier: 5, marginPct: 20 },
  TATAMOTORS: { multiplier: 5, marginPct: 20 },
  KOTAKBANK: { multiplier: 5, marginPct: 20 },
  AXISBANK: { multiplier: 5, marginPct: 20 },
  MARUTI: { multiplier: 5, marginPct: 20 },
  BAJFINANCE: { multiplier: 5, marginPct: 20 },
  HCLTECH: { multiplier: 5, marginPct: 20 }
}

/**
 * Fetch official free Zerodha margins for Indian equities
 */
export async function fetchZerodhaMargins(): Promise<Map<string, ZerodhaMarginInfo>> {
  if (zerodhaMarginCache) return zerodhaMarginCache

  const marginMap = new Map<string, ZerodhaMarginInfo>()

  // Populate defaults first
  Object.entries(BASELINE_ZERODHA_MARGINS).forEach(([sym, data]) => {
    marginMap.set(sym, {
      tradingsymbol: sym,
      mis_multiplier: data.multiplier,
      mis_margin_pct: data.marginPct,
      leverageDesc: `${data.multiplier}x MIS (Intraday)`
    })
  })

  try {
    // Try Vite proxy first, then direct public API
    const endpoints = ['/api/zerodha/margins/equity', 'https://api.kite.trade/margins/equity']
    let rawData: any[] | null = null

    for (const url of endpoints) {
      try {
        const res = await fetch(url, { signal: AbortSignal.timeout(3000) })
        if (res.ok) {
          rawData = await res.json()
          if (Array.isArray(rawData) && rawData.length > 0) break
        }
      } catch {
        // try next endpoint
      }
    }

    if (rawData && Array.isArray(rawData)) {
      rawData.forEach((item) => {
        if (item && item.tradingsymbol) {
          const sym = item.tradingsymbol.toUpperCase()
          const multiplier = item.mis_multiplier || 5
          const marginPct = item.mis_margin || 20
          marginMap.set(sym, {
            tradingsymbol: sym,
            mis_multiplier: multiplier,
            mis_margin_pct: marginPct,
            co_lower: item.co_lower,
            co_upper: item.co_upper,
            leverageDesc: `${multiplier}x MIS Margin (${marginPct}% Capital)`
          })
        }
      })
    }
  } catch (err) {
    console.warn('Zerodha margins using baseline fallback', err)
  }

  zerodhaMarginCache = marginMap
  return marginMap
}

/**
 * Get margin info for a specific stock symbol
 */
export function getStockMarginInfo(symbol: string): ZerodhaMarginInfo {
  const cleanSym = symbol.replace('.NS', '').replace('.BO', '').toUpperCase()
  if (zerodhaMarginCache && zerodhaMarginCache.has(cleanSym)) {
    return zerodhaMarginCache.get(cleanSym)!
  }

  const baseline = BASELINE_ZERODHA_MARGINS[cleanSym] || { multiplier: 5, marginPct: 20 }
  return {
    tradingsymbol: cleanSym,
    mis_multiplier: baseline.multiplier,
    mis_margin_pct: baseline.marginPct,
    leverageDesc: `${baseline.multiplier}x MIS (Intraday)`
  }
}
