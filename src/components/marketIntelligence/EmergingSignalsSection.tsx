import React from 'react'

interface EmergingSignalsSectionProps {
  onInspectAsset: (symbol: string) => void
}

export const EmergingSignalsSection: React.FC<EmergingSignalsSectionProps> = ({
  onInspectAsset
}) => {
  return (
    <div className="mb-space-md">
      {/* Section Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 mb-space-xs px-space-xs">
        <div className="flex items-center gap-space-xs">
          <span className="font-headline-md text-headline-md text-on-surface font-semibold">
            Emerging Quantitative Signals
          </span>
          <span className="px-1.5 py-0.5 rounded bg-surface-container text-on-surface-variant font-data-mono-compact text-data-mono-compact">
            3 High-Conviction Sets
          </span>
        </div>
        <span className="font-data-mono-compact text-data-mono-compact text-on-surface-variant">
          Markov Inference Pipeline v4.8 · Updated Continuous
        </span>
      </div>

      {/* 3 Institutional Signal Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-space-md">
        {/* CARD 1: RELIANCE */}
        <div className="bg-surface-container-low p-space-md flex flex-col justify-between shadow-md hover:bg-surface-container transition-all rounded">
          <div>
            {/* Header */}
            <div className="flex items-start justify-between pb-space-xs mb-space-xs bg-surface-container/60 p-space-xs rounded">
              <div>
                <div className="flex items-center gap-1.5">
                  <span className="font-headline-md text-headline-md text-on-surface font-semibold">
                    RELIANCE
                  </span>
                  <span className="font-data-mono-compact text-data-mono-compact px-1 py-0.5 rounded bg-surface-container-highest text-secondary">
                    NSE · EQ
                  </span>
                </div>
                <span className="font-body-compact text-body-compact text-on-surface-variant">
                  Reliance Industries Ltd.
                </span>
              </div>
              <div className="text-right">
                <span className="px-2 py-0.5 rounded bg-tertiary/20 text-tertiary font-label-caps text-label-caps uppercase font-semibold">
                  MODERATELY BULLISH
                </span>
                <div className="font-data-mono-compact text-data-mono-compact text-on-surface-variant mt-0.5">
                  5D Horizon
                </div>
              </div>
            </div>

            {/* Probability Distribution */}
            <div className="mb-space-sm bg-surface-container-lowest p-space-xs rounded">
              <div className="flex justify-between items-center font-data-mono-compact text-data-mono-compact text-on-surface-variant mb-1">
                <span>PROBABILITY DISTRIBUTION</span>
                <span className="text-tertiary font-semibold">Delta: +9.0 pts (4h)</span>
              </div>
              <div className="w-full h-2 rounded overflow-hidden flex bg-surface-container-high mb-1.5">
                <div className="bg-tertiary h-full" style={{ width: '67%' }} title="67% Bullish"></div>
                <div className="bg-secondary h-full" style={{ width: '18%' }} title="18% Neutral"></div>
                <div className="bg-error h-full" style={{ width: '15%' }} title="15% Bearish"></div>
              </div>
              <div className="flex justify-between font-data-mono-compact text-data-mono-compact">
                <span className="text-tertiary">↑ 67% Bullish</span>
                <span className="text-secondary">→ 18% Neutral</span>
                <span className="text-error">↓ 15% Bearish</span>
              </div>
            </div>

            {/* Mini Price Visual with Event Timestamp & 5D Probability Cone */}
            <div className="mb-space-sm bg-surface-container-lowest p-space-xs rounded">
              <div className="flex justify-between items-center font-label-caps text-label-caps text-on-surface-variant mb-1">
                <span>PRICE PATH & 5D FAN CHART</span>
                <span className="font-data-mono-compact text-data-mono-compact text-on-surface font-semibold">
                  ₹2,984.50 (+2.8%)
                </span>
              </div>
              <div className="relative w-full h-16 bg-surface-container-low overflow-hidden rounded">
                <svg className="w-full h-full" preserveAspectRatio="none" viewBox="0 0 260 64">
                  {/* Forecast Cone Area */}
                  <polygon fill="rgba(78, 222, 163, 0.15)" points="160,34 260,12 260,42" />
                  {/* Historical Line */}
                  <polyline fill="none" points="0,48 40,46 80,44 120,40 160,34" stroke="#adc6ff" strokeWidth="1.5" />
                  {/* Projected Median */}
                  <polyline fill="none" points="160,34 210,26 260,20" stroke="#4edea3" strokeDasharray="3,3" strokeWidth="1.5" />
                  {/* Event Dot */}
                  <circle cx="160" cy="34" fill="#4edea3" r="3.5" />
                  <line stroke="#464554" strokeDasharray="2,2" strokeWidth="1" x1="160" x2="160" y1="0" y2="64" />
                </svg>
                <span className="absolute top-1 left-[62%] font-label-caps text-label-caps bg-surface-container-highest px-1 text-tertiary rounded">
                  09:12 Event
                </span>
              </div>
            </div>

            {/* Supporting Drivers */}
            <div className="space-y-1 mb-space-sm">
              <span className="font-label-caps text-label-caps text-on-surface-variant uppercase">
                SUPPORTING DRIVERS (+ Attribution)
              </span>
              <div className="flex items-center justify-between text-body-compact font-body-compact bg-surface-container-lowest p-1 rounded">
                <span className="text-on-surface truncate pr-2">5G monetization & clean energy tie-up</span>
                <span className="font-data-mono-compact text-data-mono-compact text-tertiary font-semibold whitespace-nowrap">
                  +6.2%
                </span>
              </div>
              <div className="flex items-center justify-between text-body-compact font-body-compact bg-surface-container-lowest p-1 rounded">
                <span className="text-on-surface truncate pr-2">News attention velocity (+340%)</span>
                <span className="font-data-mono-compact text-data-mono-compact text-tertiary font-semibold whitespace-nowrap">
                  +3.4%
                </span>
              </div>
              <div className="flex items-center justify-between text-body-compact font-body-compact bg-surface-container-lowest p-1 rounded">
                <span className="text-on-surface truncate pr-2">Energy & Telecom relative momentum</span>
                <span className="font-data-mono-compact text-data-mono-compact text-tertiary font-semibold whitespace-nowrap">
                  +2.1%
                </span>
              </div>
            </div>

            {/* Headwinds */}
            <div className="space-y-1 mb-space-sm">
              <span className="font-label-caps text-label-caps text-on-surface-variant uppercase">
                HEADWINDS (- Penalty)
              </span>
              <div className="flex items-center justify-between text-body-compact font-body-compact bg-surface-container-lowest p-1 rounded">
                <span className="text-on-surface truncate pr-2">Elevated trailing 12M P/E multiple</span>
                <span className="font-data-mono-compact text-data-mono-compact text-error font-semibold whitespace-nowrap">
                  -1.7%
                </span>
              </div>
              <div className="flex items-center justify-between text-body-compact font-body-compact bg-surface-container-lowest p-1 rounded">
                <span className="text-on-surface truncate pr-2">Broader mid-cap breadth fatigue</span>
                <span className="font-data-mono-compact text-data-mono-compact text-error font-semibold whitespace-nowrap">
                  -1.2%
                </span>
              </div>
            </div>
          </div>

          {/* Metrics Footer & Action */}
          <div className="pt-space-xs bg-surface-container p-space-xs mt-space-xs rounded">
            <div className="flex items-center justify-between font-data-mono-compact text-data-mono-compact text-on-surface-variant mb-space-xs">
              <span>Confidence: <strong className="text-tertiary font-semibold">MED (74%)</strong></span>
              <span>Signal: <strong className="text-on-surface">7.8/10</strong></span>
              <span>2m ago</span>
            </div>
            <button
              type="button"
              onClick={() => onInspectAsset('RELIANCE.NS')}
              className="w-full py-1.5 px-space-sm bg-surface-container-highest hover:bg-surface-bright text-on-surface font-body-compact text-body-compact font-semibold rounded flex items-center justify-center gap-1 transition-all"
            >
              <span>View Intelligence Diagnostic</span>
              <span className="material-symbols-outlined text-[14px]">arrow_forward</span>
            </button>
          </div>
        </div>

        {/* CARD 2: TCS */}
        <div className="bg-surface-container-low p-space-md flex flex-col justify-between shadow-md hover:bg-surface-container transition-all rounded">
          <div>
            {/* Header */}
            <div className="flex items-start justify-between pb-space-xs mb-space-xs bg-surface-container/60 p-space-xs rounded">
              <div>
                <div className="flex items-center gap-1.5">
                  <span className="font-headline-md text-headline-md text-on-surface font-semibold">
                    TCS
                  </span>
                  <span className="font-data-mono-compact text-data-mono-compact px-1 py-0.5 rounded bg-surface-container-highest text-secondary">
                    NSE · EQ
                  </span>
                </div>
                <span className="font-body-compact text-body-compact text-on-surface-variant">
                  Tata Consultancy Services
                </span>
              </div>
              <div className="text-right">
                <span className="px-2 py-0.5 rounded bg-secondary-container text-on-secondary font-label-caps text-label-caps uppercase font-semibold">
                  NEUTRAL / RANGE
                </span>
                <div className="font-data-mono-compact text-data-mono-compact text-on-surface-variant mt-0.5">
                  5D Horizon
                </div>
              </div>
            </div>

            {/* Probability Distribution */}
            <div className="mb-space-sm bg-surface-container-lowest p-space-xs rounded">
              <div className="flex justify-between items-center font-data-mono-compact text-data-mono-compact text-on-surface-variant mb-1">
                <span>PROBABILITY DISTRIBUTION</span>
                <span className="text-error font-semibold">Delta: -4.2 pts (4h)</span>
              </div>
              <div className="w-full h-2 rounded overflow-hidden flex bg-surface-container-high mb-1.5">
                <div className="bg-tertiary h-full" style={{ width: '28%' }} title="28% Bullish"></div>
                <div className="bg-secondary h-full" style={{ width: '54%' }} title="54% Neutral"></div>
                <div className="bg-error h-full" style={{ width: '18%' }} title="18% Bearish"></div>
              </div>
              <div className="flex justify-between font-data-mono-compact text-data-mono-compact">
                <span className="text-tertiary">↑ 28% Bullish</span>
                <span className="text-secondary">→ 54% Neutral</span>
                <span className="text-error">↓ 18% Bearish</span>
              </div>
            </div>

            {/* Mini Price Visual */}
            <div className="mb-space-sm bg-surface-container-lowest p-space-xs rounded">
              <div className="flex justify-between items-center font-label-caps text-label-caps text-on-surface-variant mb-1">
                <span>PRICE PATH & 5D FAN CHART</span>
                <span className="font-data-mono-compact text-data-mono-compact text-on-surface font-semibold">
                  ₹4,290.10 (-0.12%)
                </span>
              </div>
              <div className="relative w-full h-16 bg-surface-container-low overflow-hidden rounded">
                <svg className="w-full h-full" preserveAspectRatio="none" viewBox="0 0 260 64">
                  {/* Forecast Cone Area Flat */}
                  <polygon fill="rgba(173, 198, 255, 0.15)" points="160,30 260,22 260,40" />
                  {/* Historical Line */}
                  <polyline fill="none" points="0,28 50,32 100,27 130,34 160,30" stroke="#adc6ff" strokeWidth="1.5" />
                  {/* Projected Median */}
                  <polyline fill="none" points="160,30 210,31 260,31" stroke="#adc6ff" strokeDasharray="3,3" strokeWidth="1.5" />
                  {/* Event Dot */}
                  <circle cx="160" cy="30" fill="#adc6ff" r="3.5" />
                  <line stroke="#464554" strokeDasharray="2,2" strokeWidth="1" x1="160" x2="160" y1="0" y2="64" />
                </svg>
                <span className="absolute top-1 left-[62%] font-label-caps text-label-caps bg-surface-container-highest px-1 text-on-surface-variant rounded">
                  Range Bind
                </span>
              </div>
            </div>

            {/* Supporting Drivers */}
            <div className="space-y-1 mb-space-sm">
              <span className="font-label-caps text-label-caps text-on-surface-variant uppercase">
                SUPPORTING DRIVERS (+ Attribution)
              </span>
              <div className="flex items-center justify-between text-body-compact font-body-compact bg-surface-container-lowest p-1 rounded">
                <span className="text-on-surface truncate pr-2">EU Cloud enterprise migration win</span>
                <span className="font-data-mono-compact text-data-mono-compact text-tertiary font-semibold whitespace-nowrap">
                  +3.4%
                </span>
              </div>
              <div className="flex items-center justify-between text-body-compact font-body-compact bg-surface-container-lowest p-1 rounded">
                <span className="text-on-surface truncate pr-2">Dividend yield support floor</span>
                <span className="font-data-mono-compact text-data-mono-compact text-tertiary font-semibold whitespace-nowrap">
                  +1.1%
                </span>
              </div>
            </div>

            {/* Headwinds */}
            <div className="space-y-1 mb-space-sm">
              <span className="font-label-caps text-label-caps text-on-surface-variant uppercase">
                HEADWINDS (- Penalty)
              </span>
              <div className="flex items-center justify-between text-body-compact font-body-compact bg-surface-container-lowest p-1 rounded">
                <span className="text-on-surface truncate pr-2">US BFSI discretionary contract delay</span>
                <span className="font-data-mono-compact text-data-mono-compact text-error font-semibold whitespace-nowrap">
                  -4.1%
                </span>
              </div>
              <div className="flex items-center justify-between text-body-compact font-body-compact bg-surface-container-lowest p-1 rounded">
                <span className="text-on-surface truncate pr-2">Forex currency conversion drag</span>
                <span className="font-data-mono-compact text-data-mono-compact text-error font-semibold whitespace-nowrap">
                  -1.5%
                </span>
              </div>
            </div>
          </div>

          {/* Metrics Footer & Action */}
          <div className="pt-space-xs bg-surface-container p-space-xs mt-space-xs rounded">
            <div className="flex items-center justify-between font-data-mono-compact text-data-mono-compact text-on-surface-variant mb-space-xs">
              <span>Confidence: <strong className="text-primary font-semibold">HIGH (88%)</strong></span>
              <span>Signal: <strong className="text-on-surface">8.2/10</strong></span>
              <span>5m ago</span>
            </div>
            <button
              type="button"
              onClick={() => onInspectAsset('TCS.NS')}
              className="w-full py-1.5 px-space-sm bg-surface-container-highest hover:bg-surface-bright text-on-surface font-body-compact text-body-compact font-semibold rounded flex items-center justify-center gap-1 transition-all"
            >
              <span>View Intelligence Diagnostic</span>
              <span className="material-symbols-outlined text-[14px]">arrow_forward</span>
            </button>
          </div>
        </div>

        {/* CARD 3: HDFCBANK */}
        <div className="bg-surface-container-low p-space-md flex flex-col justify-between shadow-md hover:bg-surface-container transition-all rounded">
          <div>
            {/* Header */}
            <div className="flex items-start justify-between pb-space-xs mb-space-xs bg-surface-container/60 p-space-xs rounded">
              <div>
                <div className="flex items-center gap-1.5">
                  <span className="font-headline-md text-headline-md text-on-surface font-semibold">
                    HDFCBANK
                  </span>
                  <span className="font-data-mono-compact text-data-mono-compact px-1 py-0.5 rounded bg-surface-container-highest text-secondary">
                    NSE · EQ
                  </span>
                </div>
                <span className="font-body-compact text-body-compact text-on-surface-variant">
                  HDFC Bank Limited
                </span>
              </div>
              <div className="text-right">
                <span className="px-2 py-0.5 rounded bg-tertiary text-on-tertiary font-label-caps text-label-caps uppercase font-semibold">
                  STRONGLY BULLISH
                </span>
                <div className="font-data-mono-compact text-data-mono-compact text-on-surface-variant mt-0.5">
                  5D Horizon
                </div>
              </div>
            </div>

            {/* Probability Distribution */}
            <div className="mb-space-sm bg-surface-container-lowest p-space-xs rounded">
              <div className="flex justify-between items-center font-data-mono-compact text-data-mono-compact text-on-surface-variant mb-1">
                <span>PROBABILITY DISTRIBUTION</span>
                <span className="text-tertiary font-semibold">Delta: +12.5 pts (4h)</span>
              </div>
              <div className="w-full h-2 rounded overflow-hidden flex bg-surface-container-high mb-1.5">
                <div className="bg-tertiary h-full" style={{ width: '74%' }} title="74% Bullish"></div>
                <div className="bg-secondary h-full" style={{ width: '16%' }} title="16% Neutral"></div>
                <div className="bg-error h-full" style={{ width: '10%' }} title="10% Bearish"></div>
              </div>
              <div className="flex justify-between font-data-mono-compact text-data-mono-compact">
                <span className="text-tertiary">↑ 74% Bullish</span>
                <span className="text-secondary">→ 16% Neutral</span>
                <span className="text-error">↓ 10% Bearish</span>
              </div>
            </div>

            {/* Mini Price Visual */}
            <div className="mb-space-sm bg-surface-container-lowest p-space-xs rounded">
              <div className="flex justify-between items-center font-label-caps text-label-caps text-on-surface-variant mb-1">
                <span>PRICE PATH & 5D FAN CHART</span>
                <span className="font-data-mono-compact text-data-mono-compact text-on-surface font-semibold">
                  ₹1,672.40 (+1.8%)
                </span>
              </div>
              <div className="relative w-full h-16 bg-surface-container-low overflow-hidden rounded">
                <svg className="w-full h-full" preserveAspectRatio="none" viewBox="0 0 260 64">
                  {/* Steep Bullish Fan Cone */}
                  <polygon fill="rgba(78, 222, 163, 0.2)" points="160,38 260,8 260,34" />
                  {/* Historical Line */}
                  <polyline fill="none" points="0,52 45,50 90,44 125,43 160,38" stroke="#adc6ff" strokeWidth="1.5" />
                  {/* Projected Median */}
                  <polyline fill="none" points="160,38 210,24 260,16" stroke="#4edea3" strokeDasharray="3,3" strokeWidth="1.5" />
                  {/* Event Dot */}
                  <circle cx="160" cy="38" fill="#4edea3" r="3.5" />
                  <line stroke="#464554" strokeDasharray="2,2" strokeWidth="1" x1="160" x2="160" y1="0" y2="64" />
                </svg>
                <span className="absolute top-1 left-[62%] font-label-caps text-label-caps bg-surface-container-highest px-1 text-tertiary rounded">
                  FII Accumulation
                </span>
              </div>
            </div>

            {/* Supporting Drivers */}
            <div className="space-y-1 mb-space-sm">
              <span className="font-label-caps text-label-caps text-on-surface-variant uppercase">
                SUPPORTING DRIVERS (+ Attribution)
              </span>
              <div className="flex items-center justify-between text-body-compact font-body-compact bg-surface-container-lowest p-1 rounded">
                <span className="text-on-surface truncate pr-2">Deposit growth acceleration ahead of peers</span>
                <span className="font-data-mono-compact text-data-mono-compact text-tertiary font-semibold whitespace-nowrap">
                  +7.1%
                </span>
              </div>
              <div className="flex items-center justify-between text-body-compact font-body-compact bg-surface-container-lowest p-1 rounded">
                <span className="text-on-surface truncate pr-2">Asset credit cost normalization run-rate</span>
                <span className="font-data-mono-compact text-data-mono-compact text-tertiary font-semibold whitespace-nowrap">
                  +3.8%
                </span>
              </div>
              <div className="flex items-center justify-between text-body-compact font-body-compact bg-surface-container-lowest p-1 rounded">
                <span className="text-on-surface truncate pr-2">Foreign institutional net buy imbalance</span>
                <span className="font-data-mono-compact text-data-mono-compact text-tertiary font-semibold whitespace-nowrap">
                  +3.2%
                </span>
              </div>
            </div>

            {/* Headwinds */}
            <div className="space-y-1 mb-space-sm">
              <span className="font-label-caps text-label-caps text-on-surface-variant uppercase">
                HEADWINDS (- Penalty)
              </span>
              <div className="flex items-center justify-between text-body-compact font-body-compact bg-surface-container-lowest p-1 rounded">
                <span className="text-on-surface truncate pr-2">NIM net interest margin compression</span>
                <span className="font-data-mono-compact text-data-mono-compact text-error font-semibold whitespace-nowrap">
                  -1.6%
                </span>
              </div>
            </div>
          </div>

          {/* Metrics Footer & Action */}
          <div className="pt-space-xs bg-surface-container p-space-xs mt-space-xs rounded">
            <div className="flex items-center justify-between font-data-mono-compact text-data-mono-compact text-on-surface-variant mb-space-xs">
              <span>Confidence: <strong className="text-primary font-semibold">HIGH (86%)</strong></span>
              <span>Signal: <strong className="text-on-surface">8.7/10</strong></span>
              <span>1m ago</span>
            </div>
            <button
              type="button"
              onClick={() => onInspectAsset('HDFCBANK.NS')}
              className="w-full py-1.5 px-space-sm bg-surface-container-highest hover:bg-surface-bright text-on-surface font-body-compact text-body-compact font-semibold rounded flex items-center justify-center gap-1 transition-all"
            >
              <span>View Intelligence Diagnostic</span>
              <span className="material-symbols-outlined text-[14px]">arrow_forward</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
