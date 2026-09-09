import React from 'react'

interface EventCascadeSectionProps {
  onInspectAsset?: (symbol: string) => void
}

export const EventCascadeSection: React.FC<EventCascadeSectionProps> = ({ onInspectAsset }) => {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-space-md mb-space-md">
      {/* LEFT: Sequential Event Cascade (2 Cols on lg) */}
      <div className="lg:col-span-2 bg-surface-container-low p-space-sm sm:p-space-md shadow-md flex flex-col justify-between rounded">
        <div>
          <div className="flex items-center justify-between pb-space-xs mb-space-sm bg-surface-container px-space-sm py-1 rounded">
            <div className="flex items-center gap-space-xs">
              <span className="material-symbols-outlined text-primary text-[18px]">history</span>
              <span className="font-headline-md text-headline-md text-on-surface font-semibold">
                What Changed Today: Sequential Event Cascade
              </span>
            </div>
            <span className="font-data-mono-compact text-data-mono-compact text-tertiary">
              Real-time Stream Sync
            </span>
          </div>

          {/* Timeline items */}
          <div className="relative pl-6 space-y-4 before:absolute before:left-2 before:top-2 before:bottom-2 before:w-0.5 before:bg-surface-container-highest">
            {/* 10:02 IST */}
            <div className="relative">
              <span className="absolute -left-[27px] top-1 w-2.5 h-2.5 rounded-full bg-tertiary ring-4 ring-surface-container-low"></span>
              <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-data-mono-compact text-data-mono-compact text-on-surface-variant font-semibold">
                    10:02 IST
                  </span>
                  <span
                    onClick={() => onInspectAsset && onInspectAsset('RELIANCE.NS')}
                    className="font-label-caps text-label-caps px-1 py-0.5 rounded bg-surface-container text-secondary cursor-pointer hover:bg-surface-container-high"
                  >
                    RELIANCE
                  </span>
                  <span className="font-body-compact text-body-compact text-on-surface font-semibold">
                    Market reaction (+2.8%) outpaces historical median (+1.1%)
                  </span>
                </div>
                <span className="font-data-mono-compact text-data-mono-compact text-tertiary font-semibold">
                  +1.7σ Expansion
                </span>
              </div>
              <p className="font-body-compact text-body-compact text-on-surface-variant mt-0.5">
                Automated volume-weighted price discovery confirmed aggressive institutional accumulation across large blocks.
              </p>
            </div>

            {/* 09:47 IST */}
            <div className="relative">
              <span className="absolute -left-[27px] top-1 w-2.5 h-2.5 rounded-full bg-primary ring-4 ring-surface-container-low"></span>
              <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-data-mono-compact text-data-mono-compact text-on-surface-variant font-semibold">
                    09:47 IST
                  </span>
                  <span
                    onClick={() => onInspectAsset && onInspectAsset('RELIANCE.NS')}
                    className="font-label-caps text-label-caps px-1 py-0.5 rounded bg-surface-container text-secondary cursor-pointer hover:bg-surface-container-high"
                  >
                    RELIANCE
                  </span>
                  <span className="font-body-compact text-body-compact text-on-surface font-semibold">
                    Ensemble updated 5D probability: 58% → 67% (+9 pts)
                  </span>
                </div>
                <span className="font-data-mono-compact text-data-mono-compact text-primary font-semibold">
                  Model Re-weight
                </span>
              </div>
              <p className="font-body-compact text-body-compact text-on-surface-variant mt-0.5">
                Weight shifted from neutral dispersion to high-confidence breakout channel.
              </p>
            </div>

            {/* 09:41 IST */}
            <div className="relative">
              <span className="absolute -left-[27px] top-1 w-2.5 h-2.5 rounded-full bg-secondary ring-4 ring-surface-container-low"></span>
              <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-data-mono-compact text-data-mono-compact text-on-surface-variant font-semibold">
                    09:41 IST
                  </span>
                  <span
                    onClick={() => onInspectAsset && onInspectAsset('RELIANCE.NS')}
                    className="font-label-caps text-label-caps px-1 py-0.5 rounded bg-surface-container text-secondary cursor-pointer hover:bg-surface-container-high"
                  >
                    RELIANCE
                  </span>
                  <span className="font-body-compact text-body-compact text-on-surface font-semibold">
                    Block deal & abnormal volume detected (3.2x 20D average)
                  </span>
                </div>
                <span className="font-data-mono-compact text-data-mono-compact text-secondary font-semibold">
                  Volume Spike
                </span>
              </div>
              <p className="font-body-compact text-body-compact text-on-surface-variant mt-0.5">
                Aggregated block windows logged ₹412 Cr turnover in 8 trading minutes.
              </p>
            </div>

            {/* 09:26 IST */}
            <div className="relative">
              <span className="absolute -left-[27px] top-1 w-2.5 h-2.5 rounded-full bg-tertiary-container ring-4 ring-surface-container-low"></span>
              <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-data-mono-compact text-data-mono-compact text-on-surface-variant font-semibold">
                    09:26 IST
                  </span>
                  <span
                    onClick={() => onInspectAsset && onInspectAsset('RELIANCE.NS')}
                    className="font-label-caps text-label-caps px-1 py-0.5 rounded bg-surface-container text-secondary cursor-pointer hover:bg-surface-container-high"
                  >
                    RELIANCE
                  </span>
                  <span className="font-body-compact text-body-compact text-on-surface font-semibold">
                    Sentiment index surged to +0.71 (+2.3σ deviation)
                  </span>
                </div>
                <span className="font-data-mono-compact text-data-mono-compact text-tertiary font-semibold">
                  +2.3σ NLP Score
                </span>
              </div>
              <p className="font-body-compact text-body-compact text-on-surface-variant mt-0.5">
                NLP parsing of conference commentary scored 94th percentile bullish tonality.
              </p>
            </div>

            {/* 09:19 IST */}
            <div className="relative">
              <span className="absolute -left-[27px] top-1 w-2.5 h-2.5 rounded-full bg-surface-bright ring-4 ring-surface-container-low"></span>
              <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-data-mono-compact text-data-mono-compact text-on-surface-variant font-semibold">
                    09:19 IST
                  </span>
                  <span
                    onClick={() => onInspectAsset && onInspectAsset('RELIANCE.NS')}
                    className="font-label-caps text-label-caps px-1 py-0.5 rounded bg-surface-container text-secondary cursor-pointer hover:bg-surface-container-high"
                  >
                    RELIANCE
                  </span>
                  <span className="font-body-compact text-body-compact text-on-surface font-semibold">
                    News attention velocity surged +340% across 38 feeds
                  </span>
                </div>
                <span className="font-data-mono-compact text-data-mono-compact text-on-surface-variant">
                  News Ingestion
                </span>
              </div>
              <p className="font-body-compact text-body-compact text-on-surface-variant mt-0.5">
                Wires, SEBI exchange disclosures, and global energy journals triggered high-priority ingestion alerts.
              </p>
            </div>

            {/* 09:12 IST */}
            <div className="relative">
              <span className="absolute -left-[27px] top-1 w-2.5 h-2.5 rounded-full bg-secondary-fixed ring-4 ring-surface-container-low"></span>
              <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-data-mono-compact text-data-mono-compact text-on-surface-variant font-semibold">
                    09:12 IST
                  </span>
                  <span
                    onClick={() => onInspectAsset && onInspectAsset('RELIANCE.NS')}
                    className="font-label-caps text-label-caps px-1 py-0.5 rounded bg-surface-container text-secondary cursor-pointer hover:bg-surface-container-high"
                  >
                    RELIANCE
                  </span>
                  <span className="font-body-compact text-body-compact text-on-surface font-semibold">
                    Clean energy & enterprise telecom partnership finalized
                  </span>
                </div>
                <span className="font-data-mono-compact text-data-mono-compact text-secondary-fixed font-semibold">
                  Root Event
                </span>
              </div>
              <p className="font-body-compact text-body-compact text-on-surface-variant mt-0.5">
                Official exchange filing: multi-year cloud network infrastructure and green hydrogen supply agreement.
              </p>
            </div>
          </div>
        </div>

        {/* Timeline Footer */}
        <div className="pt-space-sm mt-space-sm bg-surface-container-lowest p-space-xs rounded flex items-center justify-between text-on-surface-variant font-data-mono-compact text-data-mono-compact">
          <span>Displaying 6 of 84 logged today</span>
          <button
            type="button"
            className="text-primary hover:text-on-surface flex items-center gap-1 transition-colors"
          >
            <span>Open Full Chronicle Log</span>
            <span className="material-symbols-outlined text-[14px]">open_in_new</span>
          </button>
        </div>
      </div>

      {/* RIGHT: Asset Correlation Pulse & Quant Takeaway (1 Col) */}
      <div className="bg-surface-container-low p-space-sm sm:p-space-md flex flex-col justify-between shadow-md rounded">
        <div>
          <div className="flex items-center justify-between pb-space-xs mb-space-sm bg-surface-container px-space-sm py-1 rounded">
            <span className="font-headline-md text-headline-md text-on-surface font-semibold">
              Asset Correlation Pulse
            </span>
            <span className="font-data-mono-compact text-data-mono-compact text-secondary">
              Inter-Market Matrix
            </span>
          </div>

          {/* Inter-Market Pair Rows */}
          <div className="space-y-space-xs mb-space-sm">
            <div className="bg-surface-container-lowest p-space-xs rounded flex items-center justify-between text-on-surface font-body-compact text-body-compact">
              <span>NIFTY BANK vs IT</span>
              <div className="flex items-center gap-2">
                <div className="w-20 sm:w-24 bg-surface-container-high h-2 rounded flex">
                  <div className="bg-tertiary h-full w-[35%]"></div>
                </div>
                <span className="font-data-mono-compact text-data-mono-compact text-tertiary font-semibold">
                  +0.35
                </span>
              </div>
            </div>

            <div className="bg-surface-container-lowest p-space-xs rounded flex items-center justify-between text-on-surface font-body-compact text-body-compact">
              <span>USD/INR vs NIFTY 50</span>
              <div className="flex items-center gap-2">
                <div className="w-20 sm:w-24 bg-surface-container-high h-2 rounded flex justify-end">
                  <div className="bg-error h-full w-[62%]"></div>
                </div>
                <span className="font-data-mono-compact text-data-mono-compact text-error font-semibold">
                  -0.62
                </span>
              </div>
            </div>

            <div className="bg-surface-container-lowest p-space-xs rounded flex items-center justify-between text-on-surface font-body-compact text-body-compact">
              <span>CRUDE vs PAINTS/AUTO</span>
              <div className="flex items-center gap-2">
                <div className="w-20 sm:w-24 bg-surface-container-high h-2 rounded flex justify-end">
                  <div className="bg-error h-full w-[78%]"></div>
                </div>
                <span className="font-data-mono-compact text-data-mono-compact text-error font-semibold">
                  -0.78
                </span>
              </div>
            </div>

            <div className="bg-surface-container-lowest p-space-xs rounded flex items-center justify-between text-on-surface font-body-compact text-body-compact">
              <span>GOLD vs REAL YIELDS</span>
              <div className="flex items-center gap-2">
                <div className="w-20 sm:w-24 bg-surface-container-high h-2 rounded flex justify-end">
                  <div className="bg-error h-full w-[44%]"></div>
                </div>
                <span className="font-data-mono-compact text-data-mono-compact text-error font-semibold">
                  -0.44
                </span>
              </div>
            </div>
          </div>

          {/* Quant Takeaway Box */}
          <div className="bg-surface-container-lowest p-space-sm rounded space-y-2 mb-space-sm border border-outline-variant/30">
            <div className="flex items-center gap-1 text-secondary font-label-caps text-label-caps uppercase">
              <span className="material-symbols-outlined text-[14px]">psychology</span>
              <span>Quant Takeaway</span>
            </div>
            <p className="font-body-compact text-body-compact text-on-surface-variant leading-relaxed">
              The ongoing rally in domestic equities is driven by private banking balance sheet quality and commodity input margin relief. The low correlation between IT and Banking indicates sector-specific dispersion, providing ideal conditions for statistical arbitrage and factor selection.
            </p>
          </div>
        </div>

        {/* Ensemble Health Bar */}
        <div className="bg-surface-container p-space-sm rounded">
          <div className="flex items-center justify-between text-on-surface font-label-caps text-label-caps uppercase mb-1">
            <span>Ensemble Health</span>
            <span className="text-tertiary font-data-mono-compact text-data-mono-compact font-semibold">
              99.8% Nominal
            </span>
          </div>
          <div className="w-full bg-surface-container-lowest h-1.5 rounded-full overflow-hidden">
            <div className="bg-tertiary h-full w-[99.8%]"></div>
          </div>
        </div>
      </div>
    </div>
  )
}
