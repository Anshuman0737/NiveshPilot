import React, { useState } from 'react'
import { AssetPricePoint, ForecastHorizon, DirectionalForecast } from '../../engine/marketIntelligence/types'

interface PriceForecastChartProps {
  prices: AssetPricePoint[]
  forecast: DirectionalForecast | null
  activeHorizon: ForecastHorizon
  currency: string
}

export const PriceForecastChart: React.FC<PriceForecastChartProps> = ({
  prices,
  forecast,
  activeHorizon,
  currency
}) => {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null)

  // Take the last 60 trading days for clear presentation
  const recentPrices = prices.slice(-60)
  if (recentPrices.length < 5) {
    return (
      <div className="p-8 rounded-3xl bg-slate-900/60 border border-slate-800 text-center text-xs text-slate-500">
        Insufficient price history to render forecast cone.
      </div>
    )
  }

  const latestPrice = recentPrices[recentPrices.length - 1].close
  const horizonDays = forecast?.days || 5

  // Construct forward projection points
  const expectedReturn = forecast?.expected_return_pct || 0
  const bullProb = forecast?.probability_bullish || 0.5
  const bearProb = forecast?.probability_bearish || 0.3

  const projectedMedian = latestPrice * (1 + expectedReturn / 100)
  const projectedUpper = latestPrice * (1 + Math.max(0.01, expectedReturn / 100 + bullProb * 0.05))
  const projectedLower = latestPrice * (1 + Math.min(-0.01, expectedReturn / 100 - bearProb * 0.05))

  // Min and Max for SVG scaling
  const allHistoricalValues = recentPrices.map((p) => p.close)
  const allValues = [...allHistoricalValues, projectedUpper, projectedLower]
  const minVal = Math.min(...allValues) * 0.985
  const maxVal = Math.max(...allValues) * 1.015
  const range = maxVal - minVal || 1.0

  const svgWidth = 800
  const svgHeight = 280
  const padLeft = 60
  const padRight = 80
  const padTop = 30
  const padBottom = 40

  const plotWidth = svgWidth - padLeft - padRight
  const plotHeight = svgHeight - padTop - padBottom

  const nHist = recentPrices.length
  const totalSteps = nHist + horizonDays

  const getX = (stepIndex: number) => padLeft + (stepIndex / (totalSteps - 1)) * plotWidth
  const getY = (val: number) => padTop + plotHeight - ((val - minVal) / range) * plotHeight

  // Build historical path
  const historicalPathD = recentPrices
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${getX(i).toFixed(1)} ${getY(p.close).toFixed(1)}`)
    .join(' ')

  // Forecast cone anchor coordinates
  const lastX = getX(nHist - 1)
  const lastY = getY(latestPrice)
  const futureX = getX(totalSteps - 1)
  const upperY = getY(projectedUpper)
  const medianY = getY(projectedMedian)
  const lowerY = getY(projectedLower)

  const coneAreaD = `M ${lastX.toFixed(1)} ${lastY.toFixed(1)} L ${futureX.toFixed(1)} ${upperY.toFixed(1)} L ${futureX.toFixed(1)} ${lowerY.toFixed(1)} Z`

  // Hover data
  const hoveredPoint = hoverIndex !== null && hoverIndex < nHist ? recentPrices[hoverIndex] : null

  return (
    <div className="p-6 rounded-3xl bg-slate-900/80 border border-white/[0.08] shadow-2xl space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-white/[0.06]">
        <div>
          <span className="text-[10px] uppercase font-bold tracking-widest text-slate-400">
            Price History & Horizon Projection Cone
          </span>
          <h3 className="text-base font-bold text-white mt-0.5">
            60-Day Realized Trajectory + {activeHorizon} Calibrated Cone
          </h3>
        </div>

        <div className="flex items-center space-x-3 text-xs">
          <div className="flex items-center space-x-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-cyan-400" />
            <span className="text-slate-300">Historical Price</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <span className="w-2.5 h-2.5 rounded-sm bg-emerald-500/30 border border-emerald-500" />
            <span className="text-emerald-400">Forecast Range</span>
          </div>
        </div>
      </div>

      {/* SVG Container */}
      <div className="relative overflow-hidden w-full">
        <svg
          viewBox={`0 0 ${svgWidth} ${svgHeight}`}
          className="w-full h-auto select-none"
          onMouseLeave={() => setHoverIndex(null)}
        >
          <defs>
            <linearGradient id="coneGrad" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#10b981" stopOpacity="0.1" />
              <stop offset="100%" stopColor="#10b981" stopOpacity="0.25" />
            </linearGradient>
            <linearGradient id="lineGrad" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#06b6d4" />
              <stop offset="100%" stopColor="#3b82f6" />
            </linearGradient>
          </defs>

          {/* Horizontal Grid lines */}
          {[0, 0.25, 0.5, 0.75, 1.0].map((pct, idx) => {
            const y = padTop + plotHeight * pct
            const val = maxVal - pct * range
            return (
              <g key={idx}>
                <line
                  x1={padLeft}
                  y1={y}
                  x2={svgWidth - padRight}
                  y2={y}
                  stroke="rgba(255,255,255,0.05)"
                  strokeDasharray="4 4"
                />
                <text
                  x={padLeft - 8}
                  y={y + 3}
                  textAnchor="end"
                  className="fill-slate-500 text-[9px] font-mono"
                >
                  {currency === 'INR' ? '₹' : '$'}
                  {Math.round(val).toLocaleString('en-IN')}
                </text>
              </g>
            )
          })}

          {/* Probabilistic Forecast Cone Shading */}
          <path d={coneAreaD} fill="url(#coneGrad)" />

          {/* Median Projection Dashed Line */}
          <line
            x1={lastX}
            y1={lastY}
            x2={futureX}
            y2={medianY}
            stroke="#10b981"
            strokeWidth="2"
            strokeDasharray="4 3"
          />

          {/* Cone Upper and Lower Boundary Edges */}
          <line x1={lastX} y1={lastY} x2={futureX} y2={upperY} stroke="#34d399" strokeWidth="1.5" strokeOpacity="0.6" />
          <line x1={lastX} y1={lastY} x2={futureX} y2={lowerY} stroke="#f87171" strokeWidth="1.5" strokeOpacity="0.6" />

          {/* Historical Price Polyline */}
          <path d={historicalPathD} fill="none" stroke="url(#lineGrad)" strokeWidth="2.5" />

          {/* Transition Divider (Now) */}
          <line
            x1={lastX}
            y1={padTop}
            x2={lastX}
            y2={padTop + plotHeight}
            stroke="#f59e0b"
            strokeWidth="1.5"
            strokeDasharray="3 3"
          />
          <text
            x={lastX}
            y={padTop - 8}
            textAnchor="middle"
            className="fill-amber-400 text-[10px] font-bold font-mono tracking-wider"
          >
            NOW (T)
          </text>

          {/* Projected Target Points */}
          <circle cx={futureX} cy={medianY} r="4" fill="#10b981" />
          <text
            x={futureX + 8}
            y={medianY + 3}
            className="fill-emerald-400 text-[10px] font-bold font-mono"
          >
            {currency === 'INR' ? '₹' : '$'}
            {Math.round(projectedMedian).toLocaleString('en-IN')}
          </text>

          {/* Invisible hover overlay rectangles */}
          {recentPrices.map((_, i) => {
            const x = getX(i)
            const w = plotWidth / (totalSteps - 1)
            return (
              <rect
                key={i}
                x={x - w / 2}
                y={padTop}
                width={w}
                height={plotHeight}
                fill="transparent"
                onMouseEnter={() => setHoverIndex(i)}
                className="cursor-crosshair"
              />
            )
          })}

          {/* Hover Crosshair & Dot */}
          {hoverIndex !== null && hoverIndex < nHist && (
            <g>
              <line
                x1={getX(hoverIndex)}
                y1={padTop}
                x2={getX(hoverIndex)}
                y2={padTop + plotHeight}
                stroke="rgba(255,255,255,0.4)"
                strokeDasharray="2 2"
              />
              <circle
                cx={getX(hoverIndex)}
                cy={getY(recentPrices[hoverIndex].close)}
                r="4.5"
                fill="#38bdf8"
                stroke="#0f172a"
                strokeWidth="2"
              />
            </g>
          )}
        </svg>

        {/* Floating Tooltip */}
        {hoveredPoint && (
          <div className="absolute top-2 left-16 p-2.5 rounded-xl bg-slate-950/95 border border-white/10 text-xs shadow-xl space-y-0.5 pointer-events-none">
            <div className="text-[10px] text-slate-400 font-mono">{hoveredPoint.date}</div>
            <div className="font-bold text-white font-mono">
              Close: {currency === 'INR' ? '₹' : '$'}
              {hoveredPoint.close.toLocaleString('en-IN')}
            </div>
            {hoveredPoint.rsi_14 !== undefined && (
              <div className="text-[10px] text-slate-400">
                RSI(14): <span className="text-cyan-400 font-mono">{hoveredPoint.rsi_14.toFixed(1)}</span>
                {' • '}
                Regime: <span className="text-emerald-400">{hoveredPoint.market_regime || 'Bull'}</span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
