export interface LiveQuote {
  symbol: string
  name: string
  price: number
  change: number
  changePct: number
  dayHigh: number
  dayLow: number
  prevClose: number
  category: 'index' | 'stock'
  sector?: string
  peRatio?: number
  marketCapCr?: number
}

export interface SectorPerformance {
  sector: string
  changePct: number
  trend: 'up' | 'down' | 'flat'
  topStock: string
}

export const BASELINE_LIVE_QUOTES: LiveQuote[] = [
  {
    symbol: 'NIFTY 50',
    name: 'Nifty 50 Index',
    price: 24852.4,
    change: 142.3,
    changePct: 0.57,
    dayHigh: 24895.6,
    dayLow: 24780.1,
    prevClose: 24710.1,
    category: 'index'
  },
  {
    symbol: 'SENSEX',
    name: 'BSE Sensex 30',
    price: 81332.1,
    change: 480.2,
    changePct: 0.59,
    dayHigh: 81450.0,
    dayLow: 81100.4,
    prevClose: 80851.9,
    category: 'index'
  },
  {
    symbol: 'BANK NIFTY',
    name: 'Nifty Bank Index',
    price: 51240.8,
    change: 225.4,
    changePct: 0.44,
    dayHigh: 51380.0,
    dayLow: 51050.2,
    prevClose: 51015.4,
    category: 'index'
  },
  {
    symbol: 'INDIA VIX',
    name: 'India Volatility Index',
    price: 13.42,
    change: -0.35,
    changePct: -2.54,
    dayHigh: 13.9,
    dayLow: 13.1,
    prevClose: 13.77,
    category: 'index'
  },
  {
    symbol: 'NIFTY MIDCAP',
    name: 'Nifty Midcap 150',
    price: 21410.2,
    change: 165.8,
    changePct: 0.78,
    dayHigh: 21450.0,
    dayLow: 21280.0,
    prevClose: 21244.4,
    category: 'index'
  },
  {
    symbol: 'NIFTY SMALLCAP',
    name: 'Nifty Smallcap 250',
    price: 18920.4,
    change: 190.2,
    changePct: 1.01,
    dayHigh: 18980.0,
    dayLow: 18780.0,
    prevClose: 18730.2,
    category: 'index'
  },
  {
    symbol: 'RELIANCE',
    name: 'Reliance Industries Ltd',
    price: 2980.2,
    change: 32.4,
    changePct: 1.1,
    dayHigh: 2995.0,
    dayLow: 2950.0,
    prevClose: 2947.8,
    category: 'stock',
    sector: 'Energy',
    peRatio: 28.4,
    marketCapCr: 2015000
  },
  {
    symbol: 'HDFCBANK',
    name: 'HDFC Bank Ltd',
    price: 1642.5,
    change: 14.2,
    changePct: 0.87,
    dayHigh: 1655.0,
    dayLow: 1630.0,
    prevClose: 1628.3,
    category: 'stock',
    sector: 'Financials',
    peRatio: 18.2,
    marketCapCr: 1250000
  },
  {
    symbol: 'ICICIBANK',
    name: 'ICICI Bank Ltd',
    price: 1210.4,
    change: 8.9,
    changePct: 0.74,
    dayHigh: 1218.0,
    dayLow: 1202.0,
    prevClose: 1201.5,
    category: 'stock',
    sector: 'Financials',
    peRatio: 17.5,
    marketCapCr: 852000
  },
  {
    symbol: 'TCS',
    name: 'Tata Consultancy Services',
    price: 4180.0,
    change: -8.5,
    changePct: -0.2,
    dayHigh: 4210.0,
    dayLow: 4165.0,
    prevClose: 4188.5,
    category: 'stock',
    sector: 'Technology',
    peRatio: 31.2,
    marketCapCr: 1512000
  },
  {
    symbol: 'INFY',
    name: 'Infosys Ltd',
    price: 1840.1,
    change: 16.8,
    changePct: 0.92,
    dayHigh: 1850.0,
    dayLow: 1825.0,
    prevClose: 1823.3,
    category: 'stock',
    sector: 'Technology',
    peRatio: 27.1,
    marketCapCr: 765000
  },
  {
    symbol: 'BHARTIARTL',
    name: 'Bharti Airtel Ltd',
    price: 1560.0,
    change: 18.5,
    changePct: 1.2,
    dayHigh: 1572.0,
    dayLow: 1545.0,
    prevClose: 1541.5,
    category: 'stock',
    sector: 'Telecom',
    peRatio: 54.2,
    marketCapCr: 910000
  },
  {
    symbol: 'ITC',
    name: 'ITC Ltd',
    price: 498.2,
    change: 2.1,
    changePct: 0.42,
    dayHigh: 502.0,
    dayLow: 495.0,
    prevClose: 496.1,
    category: 'stock',
    sector: 'FMCG',
    peRatio: 26.5,
    marketCapCr: 622000
  },
  {
    symbol: 'SBIN',
    name: 'State Bank of India',
    price: 815.4,
    change: 5.6,
    changePct: 0.69,
    dayHigh: 820.0,
    dayLow: 810.0,
    prevClose: 809.8,
    category: 'stock',
    sector: 'Financials',
    peRatio: 10.4,
    marketCapCr: 728000
  },
  {
    symbol: 'LT',
    name: 'Larsen & Toubro Ltd',
    price: 3620.0,
    change: 28.0,
    changePct: 0.78,
    dayHigh: 3645.0,
    dayLow: 3590.0,
    prevClose: 3592.0,
    category: 'stock',
    sector: 'Capital Goods',
    peRatio: 34.1,
    marketCapCr: 498000
  },
  {
    symbol: 'TATAMOTORS',
    name: 'Tata Motors Ltd',
    price: 1020.5,
    change: 14.2,
    changePct: 1.41,
    dayHigh: 1032.0,
    dayLow: 1008.0,
    prevClose: 1006.3,
    category: 'stock',
    sector: 'Automotive',
    peRatio: 11.8,
    marketCapCr: 375000
  }
]

let currentLiveQuotes: LiveQuote[] = [...BASELINE_LIVE_QUOTES]
const listeners: Set<(quotes: LiveQuote[]) => void> = new Set()
let intervalId: any = null

function notifyListeners() {
  const payload = [...currentLiveQuotes]
  listeners.forEach((fn) => fn(payload))
}

export function subscribeToLiveMarket(callback: (quotes: LiveQuote[]) => void): () => void {
  listeners.add(callback)
  callback([...currentLiveQuotes])

  if (!intervalId && typeof window !== 'undefined') {
    intervalId = setInterval(() => {
      // Simulate live micro-ticks (gentle real-time drift)
      currentLiveQuotes = currentLiveQuotes.map((q) => {
        // Micro drift between -0.05% and +0.06%
        const driftPct = (Math.random() - 0.48) * 0.1
        const priceDelta = +(q.price * (driftPct / 100)).toFixed(2)
        const newPrice = +(q.price + priceDelta).toFixed(2)
        const newChange = +(q.change + priceDelta).toFixed(2)
        const newChangePct = +(((newPrice - q.prevClose) / q.prevClose) * 100).toFixed(2)
        const newHigh = Math.max(q.dayHigh, newPrice)
        const newLow = Math.min(q.dayLow, newPrice)

        return {
          ...q,
          price: newPrice,
          change: newChange,
          changePct: newChangePct,
          dayHigh: newHigh,
          dayLow: newLow
        }
      })
      notifyListeners()
    }, 3000)
  }

  return () => {
    listeners.delete(callback)
    if (listeners.size === 0 && intervalId) {
      clearInterval(intervalId)
      intervalId = null
    }
  }
}

export function getSectorBreadth(quotes: LiveQuote[]): SectorPerformance[] {
  const sectorMap: Record<string, { totalPct: number; count: number; topStock: string; maxPct: number }> = {}

  for (const q of quotes) {
    if (q.category === 'stock' && q.sector) {
      if (!sectorMap[q.sector]) {
        sectorMap[q.sector] = { totalPct: 0, count: 0, topStock: q.symbol, maxPct: q.changePct }
      }
      sectorMap[q.sector].totalPct += q.changePct
      sectorMap[q.sector].count += 1
      if (q.changePct > sectorMap[q.sector].maxPct) {
        sectorMap[q.sector].maxPct = q.changePct
        sectorMap[q.sector].topStock = q.symbol
      }
    }
  }

  return Object.entries(sectorMap).map(([sector, data]) => {
    const avgPct = +(data.totalPct / data.count).toFixed(2)
    return {
      sector,
      changePct: avgPct,
      trend: avgPct > 0.05 ? 'up' : avgPct < -0.05 ? 'down' : 'flat',
      topStock: data.topStock
    }
  })
}
