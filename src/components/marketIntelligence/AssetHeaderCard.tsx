import React from 'react'
import { AssetMetadata, DataFreshness } from '../../engine/marketIntelligence/types'
import { LiveMarketQuote } from '../../engine/marketIntelligence/providers/MarketDataProvider'
import { Activity, ShieldCheck, Zap, AlertCircle, Info } from 'lucide-react'

interface AssetHeaderCardProps {
  asset: AssetMetadata
  quote: LiveMarketQuote | null
  dataQualityScore: number
  onOpenHealth: () => void
}

export const AssetHeaderCard: React.FC<AssetHeaderCardProps> = ({
  asset,
  quote,
  dataQualityScore,
  onOpenHealth
}) => {
  const freshnessColors: Record<DataFreshness, string> = {
    LIVE: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
    DELAYED: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
    END_OF_DAY: 'bg-teal-500/10 text-teal-400 border-teal-500/30',
    HISTORICAL: 'bg-indigo-500/10 text-indigo-400 border-indigo-500/30',
    STALE: 'bg-rose-500/10 text-rose-400 border-rose-500/30',
    UNAVAILABLE: 'bg-slate-700/30 text-slate-400 border-slate-700'
  }

  const freshness = quote?.freshness || 'HISTORICAL'
  const isPositive = (quote?.change ?? 0) >= 0

  return (
    <div className="p-6 rounded-3xl bg-slate-900/80 backdrop-blur-xl border border-white/[0.08] shadow-2xl relative overflow-hidden">
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        {/* Left: Asset Identity & Sector */}
        <div className="space-y-1.5">
          <div className="flex items-center space-x-2.5">
            <h1 className="text-2xl sm:text-3xl font-black text-white tracking-tight">
              {asset.name}
            </h1>
            <span className="text-xs font-mono font-bold px-2.5 py-0.5 rounded-lg bg-white/[0.05] border border-white/[0.1] text-slate-300">
              {asset.symbol}
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
            <span className="px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 font-semibold border border-emerald-500/20 uppercase tracking-wider text-[10px]">
              {asset.asset_class.replace('_', ' ')}
            </span>
            <span>•</span>
            <span className="font-medium text-slate-300">{asset.sector}</span>
            <span>•</span>
            <span>{asset.exchange} ({asset.currency})</span>
            {asset.benchmark && asset.benchmark !== 'N/A' && (
              <>
                <span>•</span>
                <span className="text-slate-500">Benchmark: {asset.benchmark}</span>
              </>
            )}
          </div>
        </div>

        {/* Right: Real-time Price & Quality Badges */}
        <div className="flex flex-wrap items-center gap-4 sm:gap-6 self-end md:self-auto">
          {/* Price & Day Movement */}
          <div className="text-right">
            {quote && quote.price > 0 ? (
              <>
                <div className="text-2xl sm:text-3xl font-mono font-black text-white tracking-tight">
                  {asset.currency === 'INR' ? '₹' : '$'}
                  {quote.price.toLocaleString('en-IN', {
                    minimumFractionDigits: asset.asset_class === 'mutual_fund' ? 4 : 2,
                    maximumFractionDigits: asset.asset_class === 'mutual_fund' ? 4 : 2
                  })}
                </div>
                <div
                  className={`text-xs font-mono font-bold flex items-center justify-end space-x-1 ${
                    isPositive ? 'text-emerald-400' : 'text-rose-400'
                  }`}
                >
                  <span>
                    {isPositive ? '+' : ''}
                    {quote.change.toFixed(2)} ({isPositive ? '+' : ''}
                    {quote.changePct.toFixed(2)}%)
                  </span>
                </div>
              </>
            ) : (
              <div className="text-sm font-semibold text-slate-500">Market price unavailable</div>
            )}
          </div>

          {/* Freshness Badge & Health Trigger */}
          <div className="flex flex-col items-end space-y-1.5">
            <div className="flex items-center space-x-2">
              <span
                className={`text-[10px] font-mono font-black px-2.5 py-1 rounded-full border uppercase tracking-widest flex items-center space-x-1.5 ${freshnessColors[freshness]}`}
              >
                <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
                <span>{freshness}</span>
              </span>

              <button
                onClick={onOpenHealth}
                className="p-1.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.06] text-slate-400 hover:text-white transition-colors"
                title="Inspect Data Provider Health"
              >
                <Activity className="w-3.5 h-3.5" />
              </button>
            </div>

            {/* Data Quality Rating */}
            <div className="text-[11px] text-slate-400 flex items-center space-x-1.5">
              <span>Data Quality:</span>
              <span
                className={`font-bold font-mono ${
                  dataQualityScore >= 80
                    ? 'text-emerald-400'
                    : dataQualityScore >= 60
                    ? 'text-amber-400'
                    : 'text-rose-400'
                }`}
              >
                {dataQualityScore}/100
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
