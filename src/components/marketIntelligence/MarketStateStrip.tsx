import React from 'react'

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
}

export const MarketStateStrip: React.FC<MarketStateStripProps> = ({ onSelectAsset }) => {
  const items: MarketIndexItem[] = [
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

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-7 gap-px bg-surface-container-highest p-px mb-space-md shadow-sm rounded overflow-hidden">
      {items.map((item, idx) => {
        const isLastOnMobile = idx === items.length - 1
        return (
          <div
            key={item.id}
            onClick={() => onSelectAsset && onSelectAsset(item.symbol)}
            className={`bg-surface-container-low p-space-xs hover:bg-surface-container transition-colors flex flex-col justify-between cursor-pointer group ${
              isLastOnMobile ? 'col-span-2 sm:col-span-1' : ''
            }`}
          >
            {/* Header: Name + Status */}
            <div className="flex items-center justify-between font-label-caps text-label-caps text-on-surface-variant">
              <span className="group-hover:text-on-surface transition-colors">{item.name}</span>
              {item.status === 'OPEN' ? (
                <span className="text-tertiary flex items-center gap-0.5 font-data-mono-compact text-data-mono-compact">
                  <span className="w-1 h-1 rounded-full bg-tertiary animate-pulse"></span>
                  OPEN
                </span>
              ) : item.status === 'CLOSED' ? (
                <span className="text-outline font-data-mono-compact text-data-mono-compact">
                  CLOSED
                </span>
              ) : (
                <span className="text-secondary font-data-mono-compact text-data-mono-compact">
                  TRADING
                </span>
              )}
            </div>

            {/* Price & Change % */}
            <div className="flex items-baseline justify-between mt-1">
              <span className="font-data-mono-default text-data-mono-default text-on-surface font-semibold">
                {item.price}
              </span>
              <span
                className={`font-data-mono-compact text-data-mono-compact font-medium ${
                  item.isPositive === true
                    ? 'text-tertiary'
                    : item.isPositive === false
                    ? 'text-error'
                    : 'text-outline'
                }`}
              >
                {item.changePct}
              </span>
            </div>

            {/* Change Abs & Sparkline */}
            <div className="flex items-center justify-between text-on-surface-variant font-data-mono-compact text-data-mono-compact mt-1">
              <span
                className={
                  item.isPositive === true
                    ? 'text-tertiary/90'
                    : item.isPositive === false
                    ? 'text-error/90'
                    : 'text-on-surface-variant'
                }
              >
                {item.changeAbs}
              </span>
              <svg
                className={`w-12 sm:w-14 h-4 overflow-visible ${
                  item.isPositive === true
                    ? 'text-tertiary stroke-current fill-none'
                    : item.isPositive === false
                    ? 'text-error stroke-current fill-none'
                    : 'text-outline stroke-current fill-none'
                }`}
                viewBox="0 0 50 16"
              >
                <polyline
                  points={item.points}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="1.5"
                />
              </svg>
            </div>
          </div>
        )
      })}
    </div>
  )
}
