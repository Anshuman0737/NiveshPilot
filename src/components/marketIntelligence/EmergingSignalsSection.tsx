import React from 'react'
import { AssetMetadata, DirectionalForecast, AssetPricePoint } from '../../engine/marketIntelligence/types'
import { LiveMarketQuote } from '../../engine/marketIntelligence/providers/MarketDataProvider'

export interface EmergingSignalItem {
  asset: AssetMetadata
  quote: LiveMarketQuote | null
  forecast: DirectionalForecast
  prices: AssetPricePoint[]
}

interface EmergingSignalsSectionProps {
  signals?: EmergingSignalItem[]
  onInspectAsset: (symbol: string) => void
}

export const EmergingSignalsSection: React.FC<EmergingSignalsSectionProps> = ({
  signals = [],
  onInspectAsset
}) => {
  // Generate real SVG sparkline coordinates from actual prices
  const generateSparklinePath = (prices: AssetPricePoint[]): { path: string; isUp: boolean } => {
    const recent = prices.slice(-20)
    if (recent.length < 2) {
      return { path: 'M 0,24 L 180,24', isUp: true }
    }
    const closes = recent.map((p) => p.close)
    const min = Math.min(...closes)
    const max = Math.max(...closes)
    const range = Math.max(0.01, max - min)
    const isUp = closes[closes.length - 1] >= closes[0]

    const points = recent.map((p, idx) => {
      const x = +((idx / (recent.length - 1)) * 180).toFixed(1)
      const y = +(44 - ((p.close - min) / range) * 38).toFixed(1)
      return `${x},${y}`
    })

    return { path: `M ${points.join(' L ')}`, isUp }
  }

  return (
    <div className="mb-space-md">
      {/* Section Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 mb-space-xs px-space-xs">
        <div className="flex items-center gap-space-xs">
          <span className="font-headline-md text-headline-md text-on-surface font-semibold">
            Emerging Quantitative Signals
          </span>
          <span className="px-1.5 py-0.5 rounded bg-surface-container text-on-surface-variant font-data-mono-compact text-data-mono-compact">
            {signals.length} High-Conviction Sets
          </span>
        </div>
        <span className="font-data-mono-compact text-data-mono-compact text-on-surface-variant">
          Empirical Markov Inference Engine · Calibrated Live
        </span>
      </div>

      {/* 3 Institutional Signal Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-space-md">
        {signals.map((sig) => {
          const { asset, quote, forecast, prices } = sig
          const bullProb = Math.round(forecast.probability_bullish * 100)
          const neuProb = Math.round(forecast.probability_neutral * 100)
          const bearProb = Math.round(forecast.probability_bearish * 100)
          const spark = generateSparklinePath(prices)
          const isBullish = forecast.expected_direction.includes('BULLISH')
          const isBearish = forecast.expected_direction.includes('BEARISH')

          const directionColor = isBullish
            ? 'bg-tertiary/20 text-tertiary'
            : isBearish
            ? 'bg-error/20 text-error'
            : 'bg-secondary/20 text-secondary'

          const priceStr = quote?.price
            ? `₹${quote.price.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`
            : prices.length > 0
            ? `₹${prices[prices.length - 1].close.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`
            : 'N/A'

          return (
            <div
              key={asset.symbol}
              className="bg-surface-container-low p-space-md flex flex-col justify-between shadow-md hover:bg-surface-container transition-all rounded border border-outline-variant/30"
            >
              <div>
                {/* Header */}
                <div className="flex items-start justify-between pb-space-xs mb-space-xs bg-surface-container/60 p-space-xs rounded">
                  <div>
                    <div className="flex items-center gap-1.5">
                      <span className="font-headline-md text-headline-md text-on-surface font-semibold">
                        {asset.symbol.split('.')[0]}
                      </span>
                      <span className="font-data-mono-compact text-data-mono-compact px-1 py-0.5 rounded bg-surface-container-highest text-secondary uppercase">
                        {asset.exchange} · {asset.asset_class.slice(0, 3)}
                      </span>
                    </div>
                    <span className="font-body-compact text-body-compact text-on-surface-variant block truncate max-w-[180px]">
                      {asset.name}
                    </span>
                  </div>
                  <div className="text-right">
                    <span
                      className={`px-2 py-0.5 rounded font-label-caps text-label-caps uppercase font-semibold ${directionColor}`}
                    >
                      {forecast.expected_direction}
                    </span>
                    <div className="font-data-mono-compact text-data-mono-compact text-on-surface-variant mt-0.5">
                      {forecast.horizon} · {priceStr}
                    </div>
                  </div>
                </div>

                {/* Probability Distribution */}
                <div className="mb-space-sm bg-surface-container-lowest p-space-xs rounded">
                  <div className="flex justify-between items-center font-data-mono-compact text-data-mono-compact text-on-surface-variant mb-1">
                    <span>PLATT-SCALED PROBABILITY</span>
                    <span className={isBullish ? 'text-tertiary font-semibold' : 'text-error font-semibold'}>
                      Quality: {(forecast.signal_quality * 10).toFixed(1)}/10
                    </span>
                  </div>
                  <div className="w-full h-2 rounded overflow-hidden flex bg-surface-container-high mb-1.5">
                    <div
                      className="bg-tertiary h-full transition-all"
                      style={{ width: `${bullProb}%` }}
                      title={`${bullProb}% Bullish`}
                    ></div>
                    <div
                      className="bg-secondary h-full transition-all"
                      style={{ width: `${neuProb}%` }}
                      title={`${neuProb}% Neutral`}
                    ></div>
                    <div
                      className="bg-error h-full transition-all"
                      style={{ width: `${bearProb}%` }}
                      title={`${bearProb}% Bearish`}
                    ></div>
                  </div>
                  <div className="flex justify-between font-data-mono-compact text-data-mono-compact">
                    <span className="text-tertiary">↑ {bullProb}% Bullish</span>
                    <span className="text-secondary">→ {neuProb}% Neutral</span>
                    <span className="text-error">↓ {bearProb}% Bearish</span>
                  </div>
                </div>

                {/* Real Empirical SVG Price Path */}
                <div className="mb-space-sm bg-surface-container-lowest p-space-xs rounded">
                  <div className="flex justify-between items-center font-data-mono-compact text-data-mono-compact text-on-surface-variant mb-1">
                    <span>RECENT REAL PRICE ACTION (20D)</span>
                    <span className={spark.isUp ? 'text-tertiary' : 'text-error'}>
                      {spark.isUp ? '▲ Upward Momentum' : '▼ Mean Reversion'}
                    </span>
                  </div>
                  <div className="w-full h-12 relative flex items-center justify-center">
                    <svg className="w-full h-full" viewBox="0 0 180 48" preserveAspectRatio="none">
                      <path
                        d={spark.path}
                        fill="none"
                        stroke={spark.isUp ? '#4edea3' : '#ffb4ab'}
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </div>
                </div>

                {/* Causal Driver & Contradiction Factors */}
                <div className="space-y-1 bg-surface-container-lowest p-space-xs rounded mb-space-sm font-data-mono-compact text-data-mono-compact">
                  <div className="flex items-center gap-1.5 text-tertiary">
                    <span className="material-symbols-outlined text-[13px]">trending_up</span>
                    <span className="text-on-surface font-semibold truncate">
                      {forecast.top_bullish_drivers[0] || 'Technical Trend Continuation'}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 text-error">
                    <span className="material-symbols-outlined text-[13px]">warning</span>
                    <span className="text-on-surface-variant truncate">
                      {forecast.top_bearish_drivers[0] || 'Macro Volatility Headwind'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Action Button */}
              <button
                type="button"
                onClick={() => onInspectAsset(asset.symbol)}
                className="w-full py-1.5 px-space-sm bg-surface-container-high hover:bg-surface-container-highest text-on-surface font-body-compact text-body-compact font-semibold rounded flex items-center justify-center gap-1 transition-all cursor-pointer border border-outline-variant/40"
              >
                <span>Inspect Intelligence Diagnostic</span>
                <span className="material-symbols-outlined text-[16px]">arrow_forward</span>
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
