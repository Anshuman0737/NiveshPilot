import React from 'react'

export const MarketRegimeModule: React.FC = () => {
  return (
    <div className="bg-surface-container-low p-space-sm sm:p-space-md mb-space-md shadow-md rounded">
      {/* Top Macro Diagnostic Status Bar */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-2 sm:gap-space-md pb-space-sm bg-surface-container px-3 sm:px-space-md py-space-xs mb-space-sm rounded">
        <div className="flex flex-wrap items-center gap-space-xs sm:gap-space-sm">
          <span className="font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">
            Macro Diagnostic
          </span>
          <div className="px-2.5 py-1 rounded bg-tertiary-container text-on-tertiary font-data-mono-default text-data-mono-default font-semibold flex items-center gap-1.5 shadow-sm text-xs sm:text-sm">
            <span className="relative flex h-2 w-2 shrink-0">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-tertiary-fixed opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-tertiary-fixed"></span>
            </span>
            <span>CURRENT REGIME: RISK-ON · EXPANSIONARY</span>
          </div>
          <span className="text-outline-variant font-data-mono-compact text-data-mono-compact hidden sm:inline">
            |
          </span>
          <span className="font-data-mono-compact text-data-mono-compact text-on-surface-variant">
            Regime Persistence: <strong className="text-on-surface font-semibold">14 Days</strong>
          </span>
        </div>

        {/* Right Model Metrics */}
        <div className="flex flex-wrap items-center gap-2 sm:gap-space-md font-data-mono-compact text-data-mono-compact">
          <div className="flex items-center gap-1">
            <span className="text-on-surface-variant">Model Confidence:</span>
            <span className="text-tertiary font-semibold">72%</span>
          </div>
          <span className="text-outline-variant">·</span>
          <div className="flex items-center gap-1">
            <span className="text-on-surface-variant">Calibration:</span>
            <span className="text-primary font-semibold">8.9/10</span>
          </div>
          <span className="text-outline-variant">·</span>
          <div className="flex items-center gap-1">
            <span className="text-on-surface-variant">Transition Prob:</span>
            <span className="text-secondary font-semibold">14%</span>
          </div>
        </div>
      </div>

      {/* Multi-Factor 6-Indicator Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-px bg-surface-container-highest p-px mb-space-sm rounded overflow-hidden">
        {/* Trend Structure */}
        <div className="bg-surface-container-lowest p-space-sm flex flex-col justify-between">
          <div className="flex justify-between items-center text-on-surface-variant font-label-caps text-label-caps mb-1">
            <span>TREND STRUCTURE</span>
            <span className="text-tertiary">BULLISH</span>
          </div>
          <div className="font-body-compact text-body-compact text-on-surface font-semibold mb-1.5">
            Above 50 & 200 EMA
          </div>
          <div className="w-full bg-surface-container-high h-1.5 rounded-full overflow-hidden">
            <div className="bg-tertiary h-full w-4/5"></div>
          </div>
          <div className="flex justify-between text-on-surface-variant font-data-mono-compact text-data-mono-compact mt-1">
            <span>Strength</span>
            <span className="text-tertiary font-semibold">84/100</span>
          </div>
        </div>

        {/* Volatility */}
        <div className="bg-surface-container-lowest p-space-sm flex flex-col justify-between">
          <div className="flex justify-between items-center text-on-surface-variant font-label-caps text-label-caps mb-1">
            <span>VOLATILITY REGIME</span>
            <span className="text-tertiary">COMPRESSED</span>
          </div>
          <div className="font-body-compact text-body-compact text-on-surface font-semibold mb-1.5">
            India VIX 13.2
          </div>
          <div className="w-full bg-surface-container-high h-1.5 rounded-full overflow-hidden">
            <div className="bg-tertiary h-full w-1/4"></div>
          </div>
          <div className="flex justify-between text-on-surface-variant font-data-mono-compact text-data-mono-compact mt-1">
            <span>Percentile (1Y)</span>
            <span className="text-on-surface font-semibold">18th %ile</span>
          </div>
        </div>

        {/* Market Breadth */}
        <div className="bg-surface-container-lowest p-space-sm flex flex-col justify-between">
          <div className="flex justify-between items-center text-on-surface-variant font-label-caps text-label-caps mb-1">
            <span>MARKET BREADTH</span>
            <span className="text-tertiary">HEALTHY</span>
          </div>
          <div className="font-body-compact text-body-compact text-on-surface font-semibold mb-1.5">
            68% Advancing
          </div>
          <div className="w-full bg-surface-container-high h-1.5 rounded-full overflow-hidden flex">
            <div className="bg-tertiary h-full w-[68%]"></div>
            <div className="bg-error h-full w-[32%]"></div>
          </div>
          <div className="flex justify-between text-on-surface-variant font-data-mono-compact text-data-mono-compact mt-1">
            <span>A/D Ratio</span>
            <span className="text-on-surface font-semibold">2.12x</span>
          </div>
        </div>

        {/* Rates & Liquidity */}
        <div className="bg-surface-container-lowest p-space-sm flex flex-col justify-between">
          <div className="flex justify-between items-center text-on-surface-variant font-label-caps text-label-caps mb-1">
            <span>RATES & LIQUIDITY</span>
            <span className="text-secondary">SURPLUS</span>
          </div>
          <div className="font-body-compact text-body-compact text-on-surface font-semibold mb-1.5">
            RBI Neutral Stance
          </div>
          <div className="w-full bg-surface-container-high h-1.5 rounded-full overflow-hidden">
            <div className="bg-secondary-container h-full w-3/5"></div>
          </div>
          <div className="flex justify-between text-on-surface-variant font-data-mono-compact text-data-mono-compact mt-1">
            <span>System Liquidity</span>
            <span className="text-on-surface font-semibold">+₹1.24L Cr</span>
          </div>
        </div>

        {/* Credit Spreads */}
        <div className="bg-surface-container-lowest p-space-sm flex flex-col justify-between">
          <div className="flex justify-between items-center text-on-surface-variant font-label-caps text-label-caps mb-1">
            <span>CREDIT SPREADS</span>
            <span className="text-tertiary">TIGHT</span>
          </div>
          <div className="font-body-compact text-body-compact text-on-surface font-semibold mb-1.5">
            AAA vs Sov 48 bps
          </div>
          <div className="w-full bg-surface-container-high h-1.5 rounded-full overflow-hidden">
            <div className="bg-tertiary h-full w-1/3"></div>
          </div>
          <div className="flex justify-between text-on-surface-variant font-data-mono-compact text-data-mono-compact mt-1">
            <span>Stress Index</span>
            <span className="text-on-surface font-semibold">0.14 (Low)</span>
          </div>
        </div>

        {/* Sector Rotation */}
        <div className="bg-surface-container-lowest p-space-sm flex flex-col justify-between">
          <div className="flex justify-between items-center text-on-surface-variant font-label-caps text-label-caps mb-1">
            <span>SECTOR ROTATION</span>
            <span className="text-secondary">CYCLICAL</span>
          </div>
          <div className="font-body-compact text-body-compact text-on-surface font-semibold mb-1.5 truncate">
            Banks, IT, Auto Lead
          </div>
          <div className="w-full bg-surface-container-high h-1.5 rounded-full overflow-hidden">
            <div className="bg-secondary h-full w-3/4"></div>
          </div>
          <div className="flex justify-between text-on-surface-variant font-data-mono-compact text-data-mono-compact mt-1">
            <span>Defensive Weight</span>
            <span className="text-on-surface font-semibold">22% (Low)</span>
          </div>
        </div>
      </div>

      {/* 90-Day Visual Regime Matrix Timeline */}
      <div className="bg-surface-container-lowest p-space-sm flex flex-col gap-1.5 rounded">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 font-label-caps text-label-caps text-on-surface-variant">
          <span>HISTORICAL REGIME CLUSTERS (LAST 90 TRADING SESSIONS)</span>
          <div className="flex flex-wrap items-center gap-2 sm:gap-space-md">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded bg-tertiary"></span>Expansionary (58%)
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded bg-secondary"></span>Consolidation (27%)
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded bg-error"></span>Risk-Off (15%)
            </span>
          </div>
        </div>

        {/* Bar strip simulation */}
        <div className="w-full h-3 bg-surface-container-high rounded flex overflow-hidden">
          <div className="h-full bg-tertiary" style={{ width: '18%' }} title="Day 1-16: Expansionary"></div>
          <div className="h-full bg-secondary" style={{ width: '8%' }} title="Day 17-23: Consolidation"></div>
          <div className="h-full bg-error" style={{ width: '15%' }} title="Day 24-37: Risk-Off Pullback"></div>
          <div className="h-full bg-secondary" style={{ width: '19%' }} title="Day 38-54: Neutral Drift"></div>
          <div className="h-full bg-tertiary" style={{ width: '40%' }} title="Day 55-90: Sustained Bull Expansion (Current)"></div>
        </div>

        <div className="flex justify-between text-on-surface-variant font-data-mono-compact text-data-mono-compact">
          <span>T-90 Days</span>
          <span>T-60 Days</span>
          <span>T-30 Days</span>
          <span className="text-tertiary font-semibold">T-0 (Today: 14 Consecutive Expansion Sessions)</span>
        </div>
      </div>
    </div>
  )
}
