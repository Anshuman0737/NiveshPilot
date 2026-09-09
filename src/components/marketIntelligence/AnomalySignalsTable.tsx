import React from 'react'

interface AnomalySignalsTableProps {
  onInspectAsset?: (symbol: string) => void
}

export const AnomalySignalsTable: React.FC<AnomalySignalsTableProps> = ({ onInspectAsset }) => {
  const anomalies = [
    {
      id: 'auto-energy',
      type: 'Sector Momentum',
      typeColor: 'bg-tertiary/20 text-tertiary',
      asset: 'Nifty Auto & Energy',
      symbol: '^CNXAUTO',
      magnitude: '+2.4σ Z-Score',
      magnitudeColor: 'text-tertiary',
      time: '12m ago',
      percentile: '96th',
      impact: 'Bullish Shift (+5.4%)',
      impactIcon: 'arrow_upward',
      impactColor: 'text-tertiary'
    },
    {
      id: 'tatamotors',
      type: 'Unusual Volume',
      typeColor: 'bg-secondary-container text-on-secondary',
      asset: 'Tata Motors (TATAMOTORS)',
      symbol: 'TATAMOTORS.NS',
      magnitude: '4.1x Volume Spike',
      magnitudeColor: 'text-tertiary',
      time: '18m ago',
      percentile: '98th',
      impact: 'Bullish Confirmation',
      impactIcon: 'check_circle',
      impactColor: 'text-tertiary'
    },
    {
      id: 'sunpharma',
      type: 'News Shock',
      typeColor: 'bg-error-container text-on-error',
      asset: 'Sun Pharma (SUNPHARMA)',
      symbol: 'SUNPHARMA.NS',
      magnitude: 'FDA Form 483 Update',
      magnitudeColor: 'text-error',
      time: '34m ago',
      percentile: '91st',
      impact: 'Neutral-to-Bearish (-3.8%)',
      impactIcon: 'arrow_downward',
      impactColor: 'text-error'
    },
    {
      id: 'infosys',
      type: 'Sentiment Shift',
      typeColor: 'bg-tertiary-container text-on-tertiary',
      asset: 'Infosys (INFY)',
      symbol: 'INFY.NS',
      magnitude: '+1.8σ Brand Sentiment',
      magnitudeColor: 'text-tertiary',
      time: '48m ago',
      percentile: '88th',
      impact: 'Bullish Revision (+2.1%)',
      impactIcon: 'trending_up',
      impactColor: 'text-tertiary'
    },
    {
      id: 'banknifty',
      type: 'Volatility Anomaly',
      typeColor: 'bg-secondary-fixed text-on-secondary-fixed',
      asset: 'Bank Nifty (BANKNIFTY)',
      symbol: '^NSEBANK',
      magnitude: 'IV Skew Drop (-3.1%)',
      magnitudeColor: 'text-secondary',
      time: '1h ago',
      percentile: '94th',
      impact: 'Volatility Compression',
      impactIcon: 'compress',
      impactColor: 'text-secondary'
    }
  ]

  return (
    <div className="bg-surface-container-low p-space-sm sm:p-space-md shadow-md mb-space-md rounded">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-space-xs pb-space-xs mb-space-xs bg-surface-container px-space-sm py-1.5 rounded">
        <div className="flex items-center gap-space-xs">
          <span className="material-symbols-outlined text-secondary text-[18px]">warning</span>
          <span className="font-headline-md text-headline-md text-on-surface font-semibold">
            Live Market-Wide Anomaly Signals
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2 font-data-mono-compact text-data-mono-compact">
          <span className="text-on-surface-variant">
            Z-Score Threshold: <strong className="text-on-surface font-semibold">|Z| &gt; 1.8σ</strong>
          </span>
          <span className="text-outline-variant">·</span>
          <span className="text-on-surface-variant">
            Active Vectors: <strong className="text-primary font-semibold">12 Anomaly Flags</strong>
          </span>
        </div>
      </div>

      {/* Responsive Table with horizontal scroll */}
      <div className="overflow-x-auto -mx-2 px-2 sm:mx-0 sm:px-0">
        <table className="w-full text-left font-data-mono-default text-data-mono-default min-w-[640px]">
          <thead>
            <tr className="bg-surface-container-lowest text-on-surface-variant font-label-caps text-label-caps">
              <th className="py-2 px-space-sm">SIGNAL TYPE</th>
              <th className="py-2 px-space-sm">ASSET / SECTOR</th>
              <th className="py-2 px-space-sm">ANOMALY MAGNITUDE</th>
              <th className="py-2 px-space-sm">DETECTED AT</th>
              <th className="py-2 px-space-sm">HISTORICAL PERCENTILE</th>
              <th className="py-2 px-space-sm">MODEL FORECAST IMPACT</th>
              <th className="py-2 px-space-sm text-right">ACTION</th>
            </tr>
          </thead>
          <tbody className="divide-y-0">
            {anomalies.map((item, idx) => (
              <tr
                key={item.id}
                className={`${
                  idx % 2 === 0 ? 'bg-surface-container' : 'bg-surface-container-low'
                } hover:bg-surface-container-high transition-colors`}
              >
                <td className="py-2.5 px-space-sm">
                  <span
                    className={`px-2 py-0.5 rounded font-data-mono-compact text-data-mono-compact font-semibold ${item.typeColor}`}
                  >
                    {item.type}
                  </span>
                </td>
                <td className="py-2.5 px-space-sm font-semibold text-on-surface">
                  {item.asset}
                </td>
                <td className={`py-2.5 px-space-sm font-semibold ${item.magnitudeColor}`}>
                  {item.magnitude}
                </td>
                <td className="py-2.5 px-space-sm text-on-surface-variant font-data-mono-compact text-data-mono-compact">
                  {item.time}
                </td>
                <td className="py-2.5 px-space-sm">
                  <span className="text-on-surface font-semibold">{item.percentile}</span>{' '}
                  <span className="text-on-surface-variant font-data-mono-compact text-data-mono-compact">
                    %ile
                  </span>
                </td>
                <td className="py-2.5 px-space-sm">
                  <span className={`inline-flex items-center gap-1 ${item.impactColor}`}>
                    <span className="material-symbols-outlined text-[14px]">
                      {item.impactIcon}
                    </span>
                    <span>{item.impact}</span>
                  </span>
                </td>
                <td className="py-2.5 px-space-sm text-right">
                  <button
                    type="button"
                    onClick={() => onInspectAsset && onInspectAsset(item.symbol)}
                    className="text-primary hover:text-on-surface font-body-compact text-body-compact transition-colors"
                  >
                    Inspect →
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
