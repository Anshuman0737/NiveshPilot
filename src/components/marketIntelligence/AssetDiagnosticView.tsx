import React, { useState } from 'react'
import {
  AssetMetadata,
  ForecastHorizon,
  DirectionalForecast,
  EventObservation
} from '../../engine/marketIntelligence/types'
import { LiveMarketQuote } from '../../engine/marketIntelligence/providers/MarketDataProvider'

interface AssetDiagnosticViewProps {
  asset: AssetMetadata
  quote: LiveMarketQuote | null
  forecast: DirectionalForecast | null
  events: EventObservation[]
  activeHorizon: ForecastHorizon
  onChangeHorizon: (horizon: ForecastHorizon) => void
  onBackToOverview: () => void
  allAssets: AssetMetadata[]
  onSelectAsset: (symbol: string) => void
}

export const AssetDiagnosticView: React.FC<AssetDiagnosticViewProps> = ({
  asset,
  quote,
  forecast,
  activeHorizon,
  onChangeHorizon,
  onBackToOverview,
  allAssets,
  onSelectAsset
}) => {
  const [chartRange, setChartRange] = useState<'1D' | '1W' | '1M' | '6M' | '1Y' | '5Y'>('1M')
  const [isCopied, setIsCopied] = useState<boolean>(false)

  // Calibrated probabilities fallback to real forecast or defaults
  const bullProb = forecast?.probability_bullish !== undefined ? Math.round(forecast.probability_bullish * 100) : 67
  const neuProb = forecast?.probability_neutral !== undefined ? Math.round(forecast.probability_neutral * 100) : 18
  const bearProb = forecast?.probability_bearish !== undefined ? Math.round(forecast.probability_bearish * 100) : 15

  const priceFormatted = quote?.price
    ? `₹${quote.price.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    : '₹1,420.50'

  const changePct = quote?.changePct ?? 1.84
  const isPositive = changePct >= 0
  const changeFormatted = `${isPositive ? '+' : ''}${changePct.toFixed(2)}%`

  const handleCopyLink = () => {
    navigator.clipboard.writeText(window.location.href)
    setIsCopied(true)
    setTimeout(() => setIsCopied(false), 2000)
  }

  return (
    <div className="flex flex-col w-full text-on-surface animate-fade-in">
      {/* Top Back Navigation & Asset Switcher */}
      <div className="flex flex-wrap items-center justify-between gap-2 pb-space-xs mb-space-xs">
        <button
          type="button"
          onClick={onBackToOverview}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-surface-container-high hover:bg-surface-bright text-primary font-body-compact text-body-compact font-semibold transition-colors"
        >
          <span className="material-symbols-outlined text-[16px]">arrow_back</span>
          <span>Back to Market Intelligence Overview</span>
        </button>

        {/* Asset Quick Switcher */}
        <div className="flex items-center gap-1 overflow-x-auto max-w-full pb-1">
          <span className="font-label-caps text-label-caps text-on-surface-variant uppercase shrink-0">
            Quick Switch:
          </span>
          {allAssets.slice(0, 6).map((a) => (
            <button
              key={a.symbol}
              type="button"
              onClick={() => onSelectAsset(a.symbol)}
              className={`font-data-mono-compact text-data-mono-compact px-2 py-0.5 rounded transition-colors shrink-0 ${
                a.symbol === asset.symbol
                  ? 'bg-primary text-on-primary font-bold shadow-sm'
                  : 'bg-surface-container text-on-surface-variant hover:text-on-surface'
              }`}
            >
              {a.symbol.replace('.NS', '')}
            </button>
          ))}
        </div>
      </div>

      {/* ASSET HEADER BAR */}
      <header className="w-full bg-surface-container-lowest border-b border-outline-variant/30 py-space-sm px-space-base mb-space-base rounded shadow-sm">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-space-sm">
          <div className="flex flex-wrap items-center gap-space-md">
            <div className="flex items-center gap-space-sm">
              <div className="w-9 h-9 rounded bg-surface-container-high flex items-center justify-center font-data-mono-lg text-data-mono-lg text-primary font-semibold border border-outline-variant/40 shadow-sm">
                {asset.name.charAt(0)}
              </div>
              <div className="flex flex-col">
                <div className="flex flex-wrap items-center gap-2">
                  <h1 className="font-headline-lg text-headline-lg tracking-tight text-on-surface">
                    {asset.name}
                  </h1>
                  <span className="font-data-mono-compact text-data-mono-compact px-1.5 py-0.5 rounded bg-surface-container-high text-on-surface-variant">
                    {asset.isin || 'INE002A01018'}
                  </span>
                  <span className="font-label-caps text-label-caps px-1 py-0.5 rounded bg-secondary-container/30 text-secondary border border-secondary/40">
                    NSE : {asset.symbol.replace('.NS', '')}
                  </span>
                </div>
                <div className="flex flex-wrap items-center gap-space-xs font-label-caps text-label-caps text-on-surface-variant uppercase mt-0.5">
                  <span className="flex items-center gap-1 text-tertiary">
                    <span className="w-1.5 h-1.5 rounded-full bg-tertiary animate-pulse"></span>
                    LIVE STREAMING
                  </span>
                  <span>·</span>
                  <span className="font-data-mono-compact text-data-mono-compact text-on-surface">
                    12ms WS Latency
                  </span>
                  <span>·</span>
                  <span>Next Auction 15:30 IST</span>
                </div>
              </div>
            </div>

            <div className="h-8 w-[1px] bg-outline-variant/30 hidden md:block"></div>

            {/* Price & Day Change */}
            <div className="flex items-baseline gap-space-sm">
              <span className="font-data-mono-lg text-headline-xl text-on-surface font-semibold">
                {priceFormatted}
              </span>
              <span
                className={`font-data-mono-default text-data-mono-default font-medium flex items-center ${
                  isPositive ? 'text-tertiary' : 'text-error'
                }`}
              >
                <span className="material-symbols-outlined text-[16px] mr-0.5">
                  {isPositive ? 'arrow_upward' : 'arrow_downward'}
                </span>
                {changeFormatted}
              </span>
            </div>
          </div>

          {/* Quick Actions */}
          <div className="flex items-center gap-space-xs flex-wrap">
            <button
              type="button"
              onClick={handleCopyLink}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded bg-surface-container-high border border-outline-variant/50 hover:border-outline text-on-surface font-body-compact text-body-compact transition-colors"
            >
              <span className="material-symbols-outlined text-[16px] text-tertiary">
                {isCopied ? 'check' : 'bookmark_add'}
              </span>
              <span>{isCopied ? 'Copied' : 'Watchlist'}</span>
            </button>
            <button
              type="button"
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded bg-surface-container-high border border-outline-variant/50 hover:border-outline text-on-surface font-body-compact text-body-compact transition-colors"
            >
              <span className="material-symbols-outlined text-[16px] text-secondary">balance</span>
              <span>Compare Model</span>
            </button>
            <button
              type="button"
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded bg-surface-container-high border border-outline-variant/50 hover:border-outline text-on-surface font-body-compact text-body-compact transition-colors"
            >
              <span className="material-symbols-outlined text-[16px] text-primary">biotech</span>
              <span>Forensic Research</span>
            </button>
            <button
              type="button"
              onClick={() => window.print()}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded bg-primary-container text-on-primary-container font-body-compact text-body-compact font-semibold shadow-sm hover:opacity-90 transition-opacity"
            >
              <span className="material-symbols-outlined text-[16px]">picture_as_pdf</span>
              <span>PDF Tear Sheet</span>
            </button>
          </div>
        </div>
      </header>

      {/* 2-COLUMN MAIN QUANT BENTO */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-space-base">
        {/* LEFT COLUMN: FORECAST & ATTRIBUTION (7 Cols on xl) */}
        <div className="xl:col-span-7 flex flex-col gap-space-base">
          {/* CENTRAL DIRECTIONAL FORECAST MODULE (THE HERO) */}
          <section className="bg-surface-container-low border border-outline-variant/40 rounded p-space-sm sm:p-space-base shadow-sm relative overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-space-sm pb-space-sm border-b border-outline-variant/30">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-primary text-[20px]">psychology</span>
                <span className="font-headline-md text-headline-md uppercase tracking-wide text-on-surface">
                  Directional Forecast Engine
                </span>
                <span className="font-data-mono-compact text-data-mono-compact px-1.5 py-0.5 rounded bg-surface-container-highest text-secondary">
                  17 PIPELINES
                </span>
              </div>

              {/* Horizon Tabs */}
              <div className="flex items-center bg-surface-container-lowest p-0.5 rounded border border-outline-variant/40">
                {(['1D', '5D', '20D', '60D'] as ForecastHorizon[]).map((hz) => {
                  const isActive = activeHorizon === hz
                  return (
                    <button
                      key={hz}
                      type="button"
                      onClick={() => onChangeHorizon(hz)}
                      className={`px-2.5 py-1 font-data-mono-compact text-data-mono-compact rounded transition-all ${
                        isActive
                          ? 'bg-primary text-on-primary font-semibold shadow-sm'
                          : 'text-on-surface-variant hover:text-on-surface'
                      }`}
                    >
                      {hz === '5D' && isActive ? '5D (ACTIVE)' : hz}
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Big Analytical Display */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-space-sm my-space-base">
              <div className="bg-surface-container p-space-sm rounded border border-outline-variant/30 flex flex-col justify-between">
                <span className="font-label-caps text-label-caps text-on-surface-variant uppercase">
                  REGIME POSTURE
                </span>
                <div className="mt-1">
                  <span className="font-headline-lg text-headline-lg text-tertiary font-bold tracking-tight">
                    {forecast?.expected_direction || 'MODERATELY BULLISH'}
                  </span>
                  <div className="flex items-center gap-1.5 mt-1 font-data-mono-compact text-data-mono-compact text-on-surface-variant">
                    <span>Confidence:</span>
                    <span className="text-tertiary font-semibold">
                      {forecast?.confidence ? `${forecast.confidence} (74%)` : 'MEDIUM (74%)'}
                    </span>
                  </div>
                </div>
              </div>

              <div className="bg-surface-container p-space-sm rounded border border-outline-variant/30 flex flex-col justify-between">
                <span className="font-label-caps text-label-caps text-on-surface-variant uppercase">
                  {activeHorizon} PROBABILITY SPLIT
                </span>
                <div className="flex items-baseline gap-2 mt-1">
                  <span className="font-data-mono-lg text-headline-xl text-tertiary font-bold">
                    {bullProb}%
                  </span>
                  <span className="font-label-caps text-label-caps text-tertiary font-medium">
                    BULLISH ↑
                  </span>
                </div>
                <div className="flex items-center justify-between font-data-mono-compact text-data-mono-compact text-on-surface-variant border-t border-outline-variant/20 pt-1 mt-1">
                  <span>Neutral: {neuProb}%</span>
                  <span>Bearish: {bearProb}%</span>
                </div>
              </div>

              <div className="bg-surface-container p-space-sm rounded border border-outline-variant/30 flex flex-col justify-between">
                <span className="font-label-caps text-label-caps text-on-surface-variant uppercase">
                  MODEL CONSENSUS
                </span>
                <div className="mt-1">
                  <span className="font-data-mono-lg text-headline-lg text-primary font-bold">
                    78%
                  </span>
                  <span className="font-body-compact text-body-compact text-on-surface-variant ml-1">
                    Alignment
                  </span>
                </div>
                <p className="font-label-caps text-label-caps text-on-surface-variant/80 uppercase mt-1">
                  13 of 17 models vote positive
                </p>
              </div>
            </div>

            {/* Density Distribution Curve Visualization */}
            <div className="bg-surface-container-lowest p-space-sm rounded border border-outline-variant/40 mt-space-sm">
              <div className="flex items-center justify-between font-label-caps text-label-caps text-on-surface-variant mb-1">
                <span className="text-error">BEARISH REGIME (&lt; -0.5%)</span>
                <span className="text-on-surface-variant">NEUTRAL (±0.5%)</span>
                <span className="text-tertiary">BULLISH REGIME (&gt; +0.5%)</span>
              </div>

              {/* Density Curve SVG */}
              <div className="w-full h-16 relative">
                <svg className="w-full h-full overflow-visible" preserveAspectRatio="none" viewBox="0 0 500 70">
                  <defs>
                    <linearGradient id="curveGrad" x1="0" x2="1" y1="0" y2="0">
                      <stop offset="0%" stopColor="#EF4444" stopOpacity="0.3" />
                      <stop offset="35%" stopColor="#EF4444" stopOpacity="0.1" />
                      <stop offset="50%" stopColor="#908fa0" stopOpacity="0.15" />
                      <stop offset="65%" stopColor="#4edea3" stopOpacity="0.3" />
                      <stop offset="100%" stopColor="#4edea3" stopOpacity="0.75" />
                    </linearGradient>
                    <linearGradient id="strokeGrad" x1="0" x2="1" y1="0" y2="0">
                      <stop offset="0%" stopColor="#ffb4ab" />
                      <stop offset="45%" stopColor="#908fa0" />
                      <stop offset="100%" stopColor="#4edea3" />
                    </linearGradient>
                  </defs>
                  {/* Skewed normal probability density path */}
                  <path
                    d="M 0,68 C 100,68 120,62 180,50 C 230,40 280,30 335,12 C 370,2 410,14 450,45 C 475,60 490,67 500,68 L 500,70 L 0,70 Z"
                    fill="url(#curveGrad)"
                  />
                  <path
                    d="M 0,68 C 100,68 120,62 180,50 C 230,40 280,30 335,12 C 370,2 410,14 450,45 C 475,60 490,67 500,68"
                    fill="none"
                    stroke="url(#strokeGrad)"
                    strokeWidth="2"
                  />
                  {/* Confidence Band Highlight */}
                  <rect
                    fill="#8083ff"
                    fillOpacity="0.12"
                    height="70"
                    stroke="#8083ff"
                    strokeDasharray="2 2"
                    strokeOpacity="0.4"
                    width="70"
                    x="295"
                    y="0"
                  />
                  {/* Percentile Pin 67% */}
                  <line stroke="#ffffff" strokeWidth="2" x1="335" x2="335" y1="4" y2="68" />
                  <polygon fill="#ffffff" points="335,2 331,9 339,9" />
                </svg>
                <div className="absolute top-1 left-[67%] -translate-x-1/2 bg-surface-bright px-1.5 py-0.5 rounded font-data-mono-compact text-data-mono-compact text-on-surface border border-outline-variant/60 shadow">
                  {bullProb}% [p10: 59% | p90: 73%]
                </div>
              </div>

              {/* Color Distribution Bar */}
              <div className="relative w-full h-2 rounded bg-surface-container-high overflow-hidden mt-1 flex">
                <div className="h-full bg-error/70" style={{ width: `${bearProb}%` }}></div>
                <div className="h-full bg-outline-variant/60" style={{ width: `${neuProb}%` }}></div>
                <div className="h-full bg-tertiary" style={{ width: `${bullProb}%` }}></div>
              </div>

              <div className="flex justify-between items-center mt-2 font-data-mono-compact text-data-mono-compact text-on-surface-variant">
                <span>Left Tail: -3.8% σ2</span>
                <span className="font-body-compact text-body-compact italic text-on-surface-variant/70 text-center px-1">
                  MODEL FORECAST · Probabilistic outcome based on 17 quantitative pipelines.
                </span>
                <span>Right Tail: +5.4% σ2</span>
              </div>
            </div>
          </section>

          {/* WHAT CHANGED THE FORECAST (EXPLAINABLE AI ATTRIBUTION) */}
          <section className="bg-surface-container-low border border-outline-variant/40 rounded p-space-sm sm:p-space-base shadow-sm">
            <div className="flex items-center justify-between pb-space-sm border-b border-outline-variant/30">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-secondary text-[20px]">troubleshoot</span>
                <h2 className="font-headline-md text-headline-md uppercase tracking-wide text-on-surface">
                  What Changed the Forecast? (XAI Attribution)
                </h2>
              </div>
              <span className="font-data-mono-compact text-data-mono-compact text-on-surface-variant">
                Session Window: 08:30 → 10:00 IST
              </span>
            </div>

            {/* Before / After Metrics Row */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-space-sm my-space-sm bg-surface-container-lowest p-space-sm rounded border border-outline-variant/30">
              <div>
                <span className="font-label-caps text-label-caps text-on-surface-variant block uppercase">
                  PRIOR POSTURE (08:30 IST)
                </span>
                <span className="font-data-mono-lg text-data-mono-lg text-on-surface font-semibold">
                  58.0%
                </span>
                <span className="font-body-compact text-body-compact text-on-surface-variant ml-1">
                  Bullish
                </span>
              </div>
              <div className="sm:border-l border-outline-variant/30 sm:pl-space-sm">
                <span className="font-label-caps text-label-caps text-on-surface-variant block uppercase">
                  CURRENT STATE (10:00 IST)
                </span>
                <span className="font-data-mono-lg text-data-mono-lg text-tertiary font-semibold">
                  {bullProb}.0%
                </span>
                <span className="font-body-compact text-body-compact text-on-surface-variant ml-1">
                  Bullish
                </span>
              </div>
              <div className="sm:border-l border-outline-variant/30 sm:pl-space-sm bg-tertiary/10 -m-space-sm p-space-sm rounded-r">
                <span className="font-label-caps text-label-caps text-tertiary font-bold block uppercase">
                  NET REVISION SHOCK
                </span>
                <span className="font-data-mono-lg text-headline-md text-tertiary font-bold">
                  +{(bullProb - 58.0).toFixed(1)} pts
                </span>
                <span className="font-data-mono-compact text-data-mono-compact text-tertiary/90 block">
                  Significant Momentum Inflow
                </span>
              </div>
            </div>

            {/* Horizontal Contribution Waterfall */}
            <div className="space-y-space-xs mt-space-sm">
              <span className="font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider block">
                FACTOR CONTRIBUTION BREAKDOWN (PERCENTAGE POINTS)
              </span>

              {/* Factor 1 */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between p-1.5 rounded bg-surface-container hover:bg-surface-container-high transition-colors gap-1">
                <div className="sm:w-1/2 pr-2">
                  <span className="font-body-compact text-body-compact text-on-surface block font-medium">
                    Positive Product Announcement
                  </span>
                  <span className="font-label-caps text-label-caps text-on-surface-variant block">
                    Enterprise 5G & Clean Energy rollout
                  </span>
                </div>
                <div className="sm:w-1/2 flex items-center gap-2">
                  <div className="flex-1 bg-surface-container-lowest h-3 rounded overflow-hidden relative">
                    <div className="h-full bg-tertiary rounded" style={{ width: '78%' }}></div>
                  </div>
                  <span className="w-14 text-right font-data-mono-compact text-data-mono-compact font-semibold text-tertiary">
                    +6.2 pts
                  </span>
                </div>
              </div>

              {/* Factor 2 */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between p-1.5 rounded bg-surface-container hover:bg-surface-container-high transition-colors gap-1">
                <div className="sm:w-1/2 pr-2">
                  <span className="font-body-compact text-body-compact text-on-surface block font-medium">
                    Abnormal News Attention Velocity
                  </span>
                  <span className="font-label-caps text-label-caps text-on-surface-variant block">
                    +340% volume shock on tier-1 terminals
                  </span>
                </div>
                <div className="sm:w-1/2 flex items-center gap-2">
                  <div className="flex-1 bg-surface-container-lowest h-3 rounded overflow-hidden relative">
                    <div className="h-full bg-tertiary rounded" style={{ width: '48%' }}></div>
                  </div>
                  <span className="w-14 text-right font-data-mono-compact text-data-mono-compact font-semibold text-tertiary">
                    +3.8 pts
                  </span>
                </div>
              </div>

              {/* Factor 3 */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between p-1.5 rounded bg-surface-container hover:bg-surface-container-high transition-colors gap-1">
                <div className="sm:w-1/2 pr-2">
                  <span className="font-body-compact text-body-compact text-on-surface block font-medium">
                    Sector Relative Momentum
                  </span>
                  <span className="font-label-caps text-label-caps text-on-surface-variant block">
                    Energy & Telecom index outperformance
                  </span>
                </div>
                <div className="sm:w-1/2 flex items-center gap-2">
                  <div className="flex-1 bg-surface-container-lowest h-3 rounded overflow-hidden relative">
                    <div className="h-full bg-tertiary rounded" style={{ width: '26%' }}></div>
                  </div>
                  <span className="w-14 text-right font-data-mono-compact text-data-mono-compact font-semibold text-tertiary">
                    +2.1 pts
                  </span>
                </div>
              </div>

              {/* Factor 4 (Negative) */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between p-1.5 rounded bg-surface-container hover:bg-surface-container-high transition-colors gap-1">
                <div className="sm:w-1/2 pr-2">
                  <span className="font-body-compact text-body-compact text-on-surface block font-medium">
                    Elevated Valuation Multiples
                  </span>
                  <span className="font-label-caps text-label-caps text-on-surface-variant block">
                    EV/EBITDA exceeding 5-yr historical median
                  </span>
                </div>
                <div className="sm:w-1/2 flex items-center gap-2">
                  <div className="flex-1 bg-surface-container-lowest h-3 rounded overflow-hidden relative">
                    <div className="h-full bg-error rounded ml-auto" style={{ width: '21%' }}></div>
                  </div>
                  <span className="w-14 text-right font-data-mono-compact text-data-mono-compact font-semibold text-error">
                    -1.7 pts
                  </span>
                </div>
              </div>

              {/* Factor 5 (Negative) */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between p-1.5 rounded bg-surface-container hover:bg-surface-container-high transition-colors gap-1">
                <div className="sm:w-1/2 pr-2">
                  <span className="font-body-compact text-body-compact text-on-surface block font-medium">
                    Macro Headwind (Crude & USD/INR)
                  </span>
                  <span className="font-label-caps text-label-caps text-on-surface-variant block">
                    Brent volatility index +4.2%
                  </span>
                </div>
                <div className="sm:w-1/2 flex items-center gap-2">
                  <div className="flex-1 bg-surface-container-lowest h-3 rounded overflow-hidden relative">
                    <div className="h-full bg-error rounded ml-auto" style={{ width: '15%' }}></div>
                  </div>
                  <span className="w-14 text-right font-data-mono-compact text-data-mono-compact font-semibold text-error">
                    -1.2 pts
                  </span>
                </div>
              </div>
            </div>
          </section>

          {/* MULTI-LAYER INTERACTIVE PRICE + EVENT OVERLAY CHART */}
          <section className="bg-surface-container-low border border-outline-variant/40 rounded p-space-sm sm:p-space-base shadow-sm">
            <div className="flex flex-wrap items-center justify-between pb-space-sm border-b border-outline-variant/30 gap-2">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-primary text-[20px]">show_chart</span>
                <h2 className="font-headline-md text-headline-md uppercase tracking-wide text-on-surface">
                  Event Attribution & Price Action
                </h2>
              </div>
              <div className="flex items-center gap-1 bg-surface-container-lowest p-0.5 rounded border border-outline-variant/40">
                {(['1D', '1W', '1M', '6M', '1Y', '5Y'] as const).map((rng) => (
                  <button
                    key={rng}
                    type="button"
                    onClick={() => setChartRange(rng)}
                    className={`px-2 py-0.5 font-data-mono-compact text-data-mono-compact rounded transition-colors ${
                      chartRange === rng
                        ? 'bg-primary-container text-on-primary-container font-semibold'
                        : 'text-on-surface-variant hover:text-on-surface'
                    }`}
                  >
                    {rng}
                  </button>
                ))}
              </div>
            </div>

            {/* Chart Graphic Canvas */}
            <div className="w-full bg-surface-container-lowest rounded p-space-sm mt-space-sm relative">
              <div className="w-full h-48 relative">
                <svg className="w-full h-full" preserveAspectRatio="none" viewBox="0 0 600 200">
                  <defs>
                    <linearGradient id="chartArea" x1="0" x2="0" y1="0" y2="1">
                      <stop offset="0%" stopColor="#4edea3" stopOpacity="0.25" />
                      <stop offset="100%" stopColor="#4edea3" stopOpacity="0.0" />
                    </linearGradient>
                  </defs>
                  {/* Grid Lines */}
                  <line stroke="#464554" strokeDasharray="3 3" strokeOpacity="0.2" x1="0" x2="600" y1="40" y2="40" />
                  <line stroke="#464554" strokeDasharray="3 3" strokeOpacity="0.2" x1="0" x2="600" y1="90" y2="90" />
                  <line stroke="#464554" strokeDasharray="3 3" strokeOpacity="0.2" x1="0" x2="600" y1="140" y2="140" />
                  {/* Price Area & Line */}
                  <path
                    d="M 0,130 L 45,125 L 90,140 L 140,115 L 200,120 L 260,105 L 320,110 L 380,85 L 430,90 L 490,45 L 540,35 L 600,28 L 600,195 L 0,195 Z"
                    fill="url(#chartArea)"
                  />
                  <path
                    d="M 0,130 L 45,125 L 90,140 L 140,115 L 200,120 L 260,105 L 320,110 L 380,85 L 430,90 L 490,45 L 540,35 L 600,28"
                    fill="none"
                    stroke="#4edea3"
                    strokeWidth="2.2"
                  />
                  {/* Vertical dashed event markers */}
                  <line stroke="#908fa0" strokeDasharray="2 2" strokeOpacity="0.5" x1="140" x2="140" y1="115" y2="195" />
                  <line stroke="#908fa0" strokeDasharray="2 2" strokeOpacity="0.5" x1="260" x2="260" y1="105" y2="195" />
                  <line stroke="#908fa0" strokeDasharray="2 2" strokeOpacity="0.5" x1="380" x2="380" y1="85" y2="195" />
                  <line stroke="#c0c1ff" strokeDasharray="2 2" strokeWidth="1.5" x1="490" x2="490" y1="45" y2="195" />

                  {/* Event Nodes */}
                  <circle cx="140" cy="115" fill="#1c2b3c" r="7" stroke="#908fa0" strokeWidth="1.5" />
                  <text fill="#d4e4fa" fontSize="8" fontWeight="bold" textAnchor="middle" x="140" y="118">E1</text>

                  <circle cx="260" cy="105" fill="#1c2b3c" r="7" stroke="#908fa0" strokeWidth="1.5" />
                  <text fill="#d4e4fa" fontSize="8" fontWeight="bold" textAnchor="middle" x="260" y="108">E2</text>

                  {/* E3 Active */}
                  <circle cx="490" cy="45" fill="#8083ff" r="10" stroke="#ffffff" strokeWidth="2" />
                  <text fill="#07006c" fontSize="9" fontWeight="bold" textAnchor="middle" x="490" y="49">E3</text>

                  <circle cx="540" cy="35" fill="#1c2b3c" r="7" stroke="#908fa0" strokeWidth="1.5" />
                  <text fill="#d4e4fa" fontSize="8" fontWeight="bold" textAnchor="middle" x="540" y="38">E4</text>
                </svg>
              </div>

              {/* Sub Volume Panel */}
              <div className="h-10 w-full mt-1 flex items-end gap-1 px-1 border-t border-outline-variant/30">
                <div className="flex-1 bg-surface-container-high h-[20%]"></div>
                <div className="flex-1 bg-surface-container-high h-[35%]"></div>
                <div className="flex-1 bg-surface-container-high h-[25%]"></div>
                <div className="flex-1 bg-secondary/40 h-[60%]"></div>
                <div className="flex-1 bg-surface-container-high h-[30%]"></div>
                <div className="flex-1 bg-surface-container-high h-[40%]"></div>
                <div className="flex-1 bg-surface-container-high h-[50%]"></div>
                <div className="flex-1 bg-secondary/40 h-[65%]"></div>
                <div className="flex-1 bg-surface-container-high h-[45%]"></div>
                <div className="flex-1 bg-surface-container-high h-[55%]"></div>
                <div className="flex-1 bg-tertiary h-[95%]"></div>
                <div className="flex-1 bg-tertiary/70 h-[80%]"></div>
              </div>

              <div className="flex justify-between items-center text-on-surface-variant font-data-mono-compact text-data-mono-compact mt-1">
                <span>09:00 IST</span>
                <span>11:00 IST</span>
                <span>13:00 IST</span>
                <span className="text-tertiary font-bold">14:24 (Live)</span>
              </div>

              {/* SELECTED EVENT CALLOUT CARD (E3) */}
              <div className="mt-space-sm bg-surface-container p-space-sm rounded border border-primary/40 shadow-lg">
                <div className="flex flex-wrap items-start justify-between gap-1">
                  <div className="flex items-center gap-2">
                    <span className="w-5 h-5 rounded-full bg-primary-container text-on-primary-container font-data-mono-compact text-data-mono-compact flex items-center justify-center font-bold">
                      E3
                    </span>
                    <span className="font-headline-md text-headline-md text-on-surface font-semibold">
                      Enterprise 5G & Green Hydrogen Expansion Filing
                    </span>
                  </div>
                  <span className="font-data-mono-compact text-data-mono-compact px-1.5 py-0.5 rounded bg-tertiary/20 text-tertiary border border-tertiary/40">
                    +7.2 pts Revision
                  </span>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-2 pt-2 border-t border-outline-variant/30 font-data-mono-compact text-data-mono-compact">
                  <div>
                    <span className="text-on-surface-variant block">TIME & SOURCE</span>
                    <span className="text-on-surface font-semibold">09:12 AM IST · NSE Filing</span>
                  </div>
                  <div>
                    <span className="text-on-surface-variant block">IMPORTANCE / NOVELTY</span>
                    <span className="text-tertiary font-semibold">High · 94th Percentile</span>
                  </div>
                  <div>
                    <span className="text-on-surface-variant block">MEDIA VELOCITY</span>
                    <span className="text-on-surface font-semibold">+420% vs Baseline</span>
                  </div>
                  <div>
                    <span className="text-on-surface-variant block">IMPACT POSTURE</span>
                    <span className="text-primary font-semibold">Bullish Re-rating</span>
                  </div>
                </div>
                <p className="font-label-caps text-label-caps text-on-surface-variant/70 mt-2">
                  STATISTICAL ASSOCIATION: Quantitatively attributed based on volume impulse and tick-time language entropy. Not asserted as sole causal price driver.
                </p>
              </div>
            </div>
          </section>
        </div>

        {/* RIGHT COLUMN: SENTIMENT, CONTRADICTIONS, HISTORY & CALIBRATION (5 Cols on xl) */}
        <div className="xl:col-span-5 flex flex-col gap-space-base">
          {/* 7-D SENTIMENT INTELLIGENCE */}
          <section className="bg-surface-container-low border border-outline-variant/40 rounded p-space-sm sm:p-space-base shadow-sm">
            <div className="flex items-center justify-between pb-space-sm border-b border-outline-variant/30">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-tertiary text-[20px]">sensors</span>
                <h2 className="font-headline-md text-headline-md uppercase tracking-wide text-on-surface">
                  7-D Sentiment Intelligence
                </h2>
              </div>
              <div className="flex items-center gap-1 font-data-mono-compact text-data-mono-compact text-tertiary">
                <span className="w-1.5 h-1.5 rounded-full bg-tertiary animate-pulse"></span>
                <span>Velocity: 4.8 art/min</span>
              </div>
            </div>

            <div className="bg-surface-container-lowest p-2 rounded border border-outline-variant/30 my-space-xs flex justify-between items-center">
              <span className="font-body-compact text-body-compact text-on-surface-variant">
                Aggregate Attention Shock
              </span>
              <span className="font-data-mono-compact text-data-mono-compact px-1.5 py-0.5 rounded bg-tertiary/20 text-tertiary font-bold">
                +384% vs 30D Baseline
              </span>
            </div>

            {/* 7 Sentiment Dimensions Table */}
            <div className="space-y-1.5 mt-space-xs">
              {[
                { name: 'Product / Innovation', score: '+0.82', sd: '(0.28)', shock: '+2.9σ SHOCK', color: 'bg-tertiary/20 text-tertiary' },
                { name: 'Brand Sentiment', score: '+0.71', sd: '(0.24)', shock: '+2.3σ', color: 'bg-tertiary/20 text-tertiary' },
                { name: 'Financial / Earnings', score: '+0.64', sd: '(0.32)', shock: '+1.8σ', color: 'bg-tertiary/20 text-tertiary' },
                { name: 'Customer Sentiment', score: '+0.58', sd: '(0.30)', shock: '+1.4σ', color: 'bg-secondary/20 text-secondary' },
                { name: 'Competitive Position', score: '+0.62', sd: '(0.38)', shock: '+1.2σ', color: 'bg-secondary/20 text-secondary' },
                { name: 'Management & Gov', score: '+0.45', sd: '(0.40)', shock: '+0.3σ', color: 'bg-surface-container-high text-on-surface-variant' },
                { name: 'Regulatory / Compliance', score: '+0.10', sd: '(0.15)', shock: '-0.3σ', color: 'bg-error/20 text-error' }
              ].map((dim) => (
                <div
                  key={dim.name}
                  className="flex items-center justify-between text-body-compact p-1.5 bg-surface-container/60 rounded gap-1"
                >
                  <span className="w-32 sm:w-36 text-on-surface truncate">{dim.name}</span>
                  <span className="font-data-mono-compact text-data-mono-compact text-on-surface font-semibold">
                    {dim.score}
                  </span>
                  <span className="font-data-mono-compact text-data-mono-compact text-on-surface-variant hidden sm:inline">
                    {dim.sd}
                  </span>
                  <span className={`font-data-mono-compact text-data-mono-compact px-1.5 py-0.5 rounded font-semibold ${dim.color}`}>
                    {dim.shock}
                  </span>
                </div>
              ))}
            </div>
          </section>

          {/* MARKET REACTION BENCHMARK */}
          <section className="bg-surface-container-low border border-outline-variant/40 rounded p-space-sm sm:p-space-base shadow-sm">
            <div className="flex items-center justify-between pb-space-sm border-b border-outline-variant/30">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-secondary text-[20px]">history</span>
                <h2 className="font-headline-md text-headline-md uppercase tracking-wide text-on-surface">
                  Market Reaction Benchmark
                </h2>
              </div>
              <span className="font-label-caps text-label-caps text-on-surface-variant">
                N=42 Analog Events (6Y)
              </span>
            </div>

            <div className="grid grid-cols-3 gap-2 my-space-xs text-center">
              <div className="bg-surface-container-lowest p-2 rounded border border-outline-variant/30">
                <span className="font-label-caps text-label-caps text-on-surface-variant block">
                  1D PRICE PULSE
                </span>
                <span className="font-data-mono-default text-data-mono-default text-tertiary font-bold">
                  +2.8%
                </span>
              </div>
              <div className="bg-surface-container-lowest p-2 rounded border border-outline-variant/30">
                <span className="font-label-caps text-label-caps text-on-surface-variant block">
                  VOLUME MULTIPLE
                </span>
                <span className="font-data-mono-default text-data-mono-default text-primary font-bold">
                  2.6x (30D)
                </span>
              </div>
              <div className="bg-surface-container-lowest p-2 rounded border border-outline-variant/30">
                <span className="font-label-caps text-label-caps text-on-surface-variant block">
                  REALIZED VOL
                </span>
                <span className="font-data-mono-default text-data-mono-default text-secondary font-bold">
                  +42% σ
                </span>
              </div>
            </div>

            {/* Comparative Distribution Bar */}
            <div className="bg-surface-container p-space-sm rounded mt-space-xs">
              <div className="flex flex-wrap justify-between items-center font-body-compact text-body-compact mb-1 gap-1">
                <span className="text-on-surface-variant">Hist. Median 1D: <strong className="text-on-surface">+1.1%</strong></span>
                <span className="text-on-surface-variant">Hist. Median 5D: <strong className="text-on-surface">+2.4%</strong></span>
                <span className="text-tertiary">Current: <strong className="text-tertiary">+2.8%</strong></span>
              </div>
              <div className="w-full h-2 bg-surface-container-lowest rounded relative overflow-hidden flex">
                <div className="h-full bg-secondary/40" style={{ width: '39%' }}></div>
                <div className="h-full bg-secondary/80" style={{ width: '46%' }}></div>
                <div className="h-full bg-tertiary" style={{ width: '15%' }}></div>
              </div>
              <p className="font-body-compact text-body-compact text-tertiary mt-2 flex items-center gap-1">
                <span className="material-symbols-outlined text-[14px]">check_circle</span>
                <span>Reaction is above historical median; market pricing in stronger operational surprise.</span>
              </p>
            </div>
          </section>

          {/* ENSEMBLE DECOMPOSITION & CONTRADICTIONS */}
          <section className="bg-surface-container-low border border-outline-variant/40 rounded p-space-sm sm:p-space-base shadow-sm">
            <div className="flex items-center justify-between pb-space-sm border-b border-outline-variant/30">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-primary text-[20px]">hub</span>
                <h2 className="font-headline-md text-headline-md uppercase tracking-wide text-on-surface">
                  Ensemble Decomposition & Risks
                </h2>
              </div>
            </div>

            {/* Ensemble Pipeline Consensus */}
            <div className="grid grid-cols-2 gap-1.5 my-space-xs font-data-mono-compact text-data-mono-compact">
              <div className="bg-surface-container p-1.5 rounded flex justify-between">
                <span className="text-on-surface-variant">Tech. Structure:</span>
                <span className="text-tertiary font-bold">72% Bull</span>
              </div>
              <div className="bg-surface-container p-1.5 rounded flex justify-between">
                <span className="text-on-surface-variant">Fundamentals:</span>
                <span className="text-tertiary font-bold">61% Bull</span>
              </div>
              <div className="bg-surface-container p-1.5 rounded flex justify-between">
                <span className="text-on-surface-variant">News / Event NLP:</span>
                <span className="text-tertiary font-bold">81% Bull</span>
              </div>
              <div className="bg-surface-container p-1.5 rounded flex justify-between">
                <span className="text-on-surface-variant">Macro / FX:</span>
                <span className="text-error font-bold">44% Bear Drag</span>
              </div>
            </div>

            {/* What is working against the forecast? */}
            <div className="bg-surface-container-lowest p-space-sm rounded border border-error/30 mt-space-sm">
              <div className="flex items-center gap-1 text-error font-headline-md text-body-default font-semibold mb-1">
                <span className="material-symbols-outlined text-[16px]">warning</span>
                <span>What is Working Against the Forecast?</span>
              </div>
              <ul className="space-y-1 font-body-compact text-body-compact text-on-surface-variant">
                <li className="flex items-start gap-1">
                  <span className="text-error font-bold">•</span>
                  <span><strong>High Trailing Valuation:</strong> P/E at 28.4 vs historical sector median 22.1 (Strong Drag).</span>
                </li>
                <li className="flex items-start gap-1">
                  <span className="text-error font-bold">•</span>
                  <span><strong>Nifty Market Breadth:</strong> &lt;45% components trading above 20 EMA (Moderate Drag).</span>
                </li>
                <li className="flex items-start gap-1">
                  <span className="text-error font-bold">•</span>
                  <span><strong>Implied Volatility Surge:</strong> Options skew pricing elevated downside protection tail.</span>
                </li>
              </ul>
            </div>

            {/* Synthesis Rationale quote */}
            <div className="bg-surface-container p-space-sm rounded border-l-2 border-primary mt-2">
              <span className="font-label-caps text-label-caps text-primary uppercase font-bold block mb-1">
                SYNTHESIS RATIONALE
              </span>
              <p className="font-body-compact text-body-compact text-on-surface italic">
                "The magnitude of the new commercial enterprise contracts and unusual institutional volume surge outweighs the negative macro drag by a ratio of <strong>2.8:1</strong> in our trained gradient-boosted ensemble."
              </p>
            </div>
          </section>

          {/* DATA QUALITY & MODEL CALIBRATION */}
          <section className="bg-surface-container-low border border-outline-variant/40 rounded p-space-sm sm:p-space-base shadow-sm">
            <div className="flex items-center justify-between pb-space-xs border-b border-outline-variant/30">
              <span className="font-headline-md text-headline-md uppercase tracking-wide text-on-surface">
                Data Quality & Model Calibration
              </span>
              <span className="font-data-mono-compact text-data-mono-compact px-2 py-0.5 rounded bg-tertiary-container text-on-tertiary-container font-bold">
                91 / 100 HEALTH
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-space-sm font-data-mono-compact text-data-mono-compact">
              <div className="bg-surface-container p-1.5 rounded text-center">
                <span className="text-on-surface-variant block">{activeHorizon} DIR ACCURACY</span>
                <span className="text-tertiary text-data-mono-default font-bold">68.4%</span>
              </div>
              <div className="bg-surface-container p-1.5 rounded text-center">
                <span className="text-on-surface-variant block">BRIER SCORE</span>
                <span className="text-secondary text-data-mono-default font-bold">0.182</span>
              </div>
              <div className="bg-surface-container p-1.5 rounded text-center">
                <span className="text-on-surface-variant block">60-70% BUCKET HIT</span>
                <span className="text-on-surface text-data-mono-default font-bold">67.8%</span>
              </div>
            </div>

            {/* Ingestion Pipeline Latencies */}
            <div className="flex flex-wrap items-center justify-between gap-1 text-on-surface-variant font-data-mono-compact text-data-mono-compact mt-space-sm pt-2 border-t border-outline-variant/20">
              <span>Market: <strong className="text-tertiary">LIVE 0s</strong></span>
              <span>News: <strong>2m ago</strong></span>
              <span>Sentiment: <strong>8m ago</strong></span>
              <span>Fundamentals: <strong>1d ago</strong></span>
              <span>Macro: <strong>3h ago</strong></span>
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}
