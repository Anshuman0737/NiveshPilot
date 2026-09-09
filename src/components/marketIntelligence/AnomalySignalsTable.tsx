import React from 'react'
import { MarketAnomaly } from '../../engine/marketIntelligence/anomalyScanner'

interface AnomalySignalsTableProps {
  anomalies?: MarketAnomaly[]
  onInspectAsset?: (symbol: string) => void
}

export const AnomalySignalsTable: React.FC<AnomalySignalsTableProps> = ({
  anomalies = [],
  onInspectAsset
}) => {
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
            Z-Score Threshold: <strong className="text-on-surface font-semibold">|Z| &gt; 1.75σ</strong>
          </span>
          <span className="text-outline-variant">·</span>
          <span className="text-on-surface-variant">
            Active Detections:{' '}
            <strong className="text-primary font-semibold">
              {anomalies.length} Empirical Anomalies
            </strong>
          </span>
        </div>
      </div>

      {/* Table or Honest Empty State */}
      {anomalies.length === 0 ? (
        <div className="py-8 px-4 text-center bg-surface-container-lowest rounded border border-outline-variant/30">
          <span className="material-symbols-outlined text-outline text-[32px] mb-2 block">
            verified
          </span>
          <div className="font-body-default text-body-default text-on-surface font-medium">
            No Statistical Anomalies Exceeding |Z| &gt; 1.75σ
          </div>
          <p className="font-data-mono-compact text-data-mono-compact text-on-surface-variant mt-1 max-w-md mx-auto">
            All tracked asset vectors in the current session are trading within expected Gaussian
            variance and moving average volume bounds.
          </p>
        </div>
      ) : (
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
                    {item.assetName}
                  </td>
                  <td className={`py-2.5 px-space-sm font-semibold`}>
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
                      className="text-primary hover:text-on-surface font-body-compact text-body-compact transition-colors cursor-pointer"
                    >
                      Inspect →
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
