import React from 'react'
import { AssetPricePoint } from '../../engine/marketIntelligence/types'

export interface MarketIndexItem {
  id: string
  symbol: string
  name: string
  price: string
  changePct: string
  changeAbs: string
  status: 'OPEN' | 'CLOSED' | 'TRADING'
  isPositive: boolean | null
  points: string
}

interface MarketStateStripProps {
  onSelectAsset?: (symbol: string) => void
  liveQuotes?: Record<string, { price: number; change: number; changePct: number }>
  pricesMap?: Record<string, AssetPricePoint[]>
}

export const MarketStateStrip: React.FC<MarketStateStripProps> = ({
  onSelectAsset,
  liveQuotes = {},
  pricesMap = {}
}) => {
  const generatePolyline = (prices: AssetPricePoint[] | undefined, fallback: string): string => {
    if (!prices || prices.length < 4) return fallback
    const recent = prices.slice(-7)
    const closes = recent.map((p) => p.close)
    const min = Math.min(...closes)
    const max = Math.max(...closes)
    const range = Math.max(0.01, max - min)
    return recent
      .map((p, idx) => {
        const x = Math.round((idx / (recent.length - 1)) * 50)
        const y = Math.round(14 - ((p.close - min) / range) * 12)
        return `${x},${y}`
      })
      .join(' ')
  }

  const baseItems: MarketIndexItem[] = [
    {
      id: 'nifty50',
      symbol: '^NSEI',
      name: 'NIFTY 50',
      price: '24,842.10',
      changePct: '+0.48%',
      changeAbs: '+118.20',
      status: 'OPEN',
      isPositive: true,
      points: '0,12 8,10 16,13 24,8 32,9 40,3 50,2'
    },
    {
      id: 'sensex',
      symbol: '^BSESN',
      name: 'SENSEX',
      price: '81,420.30',
      changePct: '+0.42%',
      changeAbs: '+341.15',
      status: 'OPEN',
      isPositive: true,
      points: '0,11 10,9 20,12 30,7 40,5 50,3'
    },
    {
      id: 'nasdaq',
      symbol: '^IXIC',
      name: 'NASDAQ',
      price: '18,120.80',
      changePct: '+0.88%',
      changeAbs: '+158.40',
      status: 'CLOSED',
      isPositive: true,
      points: '0,14 12,11 22,8 32,9 42,4 50,1'
    },
    {
      id: 'sp500',
      symbol: '^GSPC',
      name: 'S&P 500',
      price: '5,648.40',
      changePct: '+0.55%',
      changeAbs: '+31.10',
      status: 'CLOSED',
      isPositive: true,
      points: '0,13 10,12 25,7 35,9 45,5 50,4'
    },
    {
      id: 'gold',
      symbol: 'GOLDBEES.NS',
      name: 'GOLD (MCX)',
      price: '₹71,840',
      changePct: '+0.32%',
      changeAbs: '+228.00',
      status: 'TRADING',
      isPositive: true,
      points: '0,10 15,12 25,8 35,6 45,7 50,4'
    },
    {
      id: 'crude',
      symbol: 'CL=F',
      name: 'CRUDE OIL',
      price: '$74.20/bbl',
      changePct: '-1.15%',
      changeAbs: '-0.86',
      status: 'TRADING',
      isPositive: false,
      points: '0,4 12,6 24,5 34,11 42,12 50,15'
    },
    {
      id: 'usdinr',
      symbol: 'USDINR=X',
      name: 'USD/INR',
      price: '83.92',
      changePct: '-0.04%',
      changeAbs: '-0.03',
      status: 'TRADING',
      isPositive: null,
      points: '0,7 15,8 25,6 35,9 45,8 50,8'
    }
  ]

  // Hydrate with real quotes and real SVG sparklines
  const items = baseItems.map((item) => {
    const q = liveQuotes[item.symbol]
    const pSeries = pricesMap[item.symbol]
    const pts = generatePolyline(pSeries, item.points)

    if (q) {
      const isPos = q.changePct > 0.05 ? true : q.changePct < -0.05 ? false : null
      return {
        ...item,
        price: item.symbol.startsWith('^') || item.symbol.includes('=') ? q.price.toLocaleString('en-IN', { maximumFractionDigits: 2 }) : `₹${q.price.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`,
        changePct: `${q.changePct >= 0 ? '+' : ''}${q.changePct.toFixed(2)}%`,
        changeAbs: `${q.change >= 0 ? '+' : ''}${q.change.toFixed(2)}`,
        isPositive: isPos,
        points: pts
      }
    }
    return { ...item, points: pts }
  })

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-7 gap-space-xs mb-space-sm">
      {items.map((item) => {
        const isUp = item.isPositive === true
        const isDown = item.isPositive === false
        const strokeColor = isUp ? '#4edea3' : isDown ? '#ffb4ab' : '#908fa0'
        const badgeColor =
          item.status === 'OPEN'
            ? 'bg-tertiary-container text-on-tertiary-container'
            : item.status === 'CLOSED'
            ? 'bg-surface-container-high text-on-surface-variant'
            : 'bg-surface-container-highest text-secondary'

        return (
          <div
            key={item.id}
            onClick={() => onSelectAsset && onSelectAsset(item.symbol)}
            className="bg-surface-container-low p-2 rounded flex flex-col justify-between shadow-sm hover:bg-surface-container transition-all cursor-pointer border border-outline-variant/30"
          >
            {/* Top row: Name & Status */}
            <div className="flex items-center justify-between font-label-caps text-label-caps mb-1">
              <span className="text-on-surface-variant font-bold truncate max-w-[85px]">
                {item.name}
              </span>
              <span className={`px-1 py-0.2 rounded font-semibold text-[9px] ${badgeColor}`}>
                {item.status}
              </span>
            </div>

            {/* Middle row: Price & Sparkline */}
            <div className="flex items-baseline justify-between gap-1 my-0.5">
              <span className="font-data-mono-default text-data-mono-default font-bold text-on-surface tracking-tight truncate">
                {item.price}
              </span>
              {/* Micro Sparkline SVG */}
              <div className="w-12 h-4 shrink-0">
                <svg
                  className="w-full h-full overflow-visible"
                  viewBox="0 0 50 16"
                  preserveAspectRatio="none"
                >
                  <polyline
                    fill="none"
                    points={item.points}
                    stroke={strokeColor}
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </div>
            </div>

            {/* Bottom row: Delta absolute & percentage */}
            <div className="flex items-center justify-between font-data-mono-compact text-data-mono-compact text-[10px]">
              <span className="text-on-surface-variant truncate">{item.changeAbs}</span>
              <span
                className={`font-semibold ${
                  isUp ? 'text-tertiary' : isDown ? 'text-error' : 'text-on-surface-variant'
                }`}
              >
                {item.changePct}
              </span>
            </div>
          </div>
        )
      })}
    </div>
  )
}
