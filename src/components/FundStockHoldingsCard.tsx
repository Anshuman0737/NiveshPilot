import React, { useState, useEffect } from 'react'
import { getFundStockHoldings, StockHolding } from '../engine/liveMfService'
import { subscribeToLiveMarket, LiveQuote } from '../engine/liveMarketService'
import {
  Layers,
  TrendingUp,
  TrendingDown,
  Building2,
  PieChart,
  ShieldAlert,
  Info,
  ExternalLink
} from 'lucide-react'

interface FundStockHoldingsCardProps {
  fundId: string
  fundName: string
  category: string
}

export const FundStockHoldingsCard: React.FC<FundStockHoldingsCardProps> = ({
  fundId,
  fundName,
  category
}) => {
  const [liveQuotes, setLiveQuotes] = useState<LiveQuote[]>([])
  const [selectedStock, setSelectedStock] = useState<StockHolding | null>(null)

  useEffect(() => {
    const unsub = subscribeToLiveMarket((quotes) => {
      setLiveQuotes(quotes)
    })
    return () => unsub()
  }, [])

  const holdings = getFundStockHoldings(fundId, liveQuotes)

  // Sector breakdown calculation
  const sectorWeights: Record<string, number> = {}
  let totalStockWeight = 0
  for (const h of holdings) {
    sectorWeights[h.sector] = (sectorWeights[h.sector] || 0) + h.weightPct
    totalStockWeight += h.weightPct
  }

  const topSectors = Object.entries(sectorWeights)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)

  return (
    <div className="p-5 sm:p-6 rounded-3xl glass-panel relative overflow-hidden border border-white/[0.08] transition-all">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 mb-4 border-b border-white/[0.06]">
        <div>
          <div className="flex items-center space-x-2 mb-1">
            <Building2 className="w-4 h-4 text-emerald-400" />
            <span className="text-[11px] font-bold uppercase tracking-wider text-emerald-400">
              Live Underlying Stock Portfolio
            </span>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-white/[0.04] text-slate-400 border border-white/[0.06]">
              Real-Time Stock Feed
            </span>
          </div>
          <h4 className="text-base sm:text-lg font-black text-white">
            What companies does <span className="text-emerald-300">{fundName.split(' - ')[0]}</span> actually own?
          </h4>
        </div>

        <div className="text-xs text-slate-400 bg-slate-950/60 px-3 py-1.5 rounded-2xl border border-white/[0.06] shrink-0">
          <span>Top 10 Weight: </span>
          <strong className="text-white">{totalStockWeight.toFixed(1)}% of Fund</strong>
        </div>
      </div>

      {/* Sector Allocation Breakdown Bar */}
      <div className="mb-5 space-y-2">
        <div className="flex justify-between text-xs text-slate-400">
          <span className="font-semibold text-slate-300 flex items-center space-x-1.5">
            <PieChart className="w-3.5 h-3.5 text-indigo-400" />
            <span>Sector Distribution:</span>
          </span>
          <span className="text-[11px] text-slate-500">Diversified Sector Weights</span>
        </div>

        {/* Visual Progress Bar */}
        <div className="w-full h-2.5 rounded-full bg-slate-800 overflow-hidden flex">
          {topSectors.map(([sector, wt], idx) => {
            const colors = [
              'bg-emerald-500',
              'bg-teal-400',
              'bg-indigo-500',
              'bg-purple-500',
              'bg-amber-400'
            ]
            return (
              <div
                key={sector}
                style={{ width: `${(wt / totalStockWeight) * 100}%` }}
                className={`${colors[idx % colors.length]} h-full transition-all`}
                title={`${sector}: ${wt.toFixed(1)}%`}
              />
            )
          })}
        </div>

        {/* Sector Chips */}
        <div className="flex flex-wrap gap-2 pt-1 text-[11px]">
          {topSectors.map(([sector, wt], idx) => {
            const dotColors = [
              'bg-emerald-400',
              'bg-teal-400',
              'bg-indigo-400',
              'bg-purple-400',
              'bg-amber-400'
            ]
            return (
              <span
                key={sector}
                className="flex items-center space-x-1.5 text-slate-400 bg-white/[0.02] px-2 py-0.5 rounded-full border border-white/[0.04]"
              >
                <span className={`w-1.5 h-1.5 rounded-full ${dotColors[idx % dotColors.length]}`} />
                <span className="text-slate-300">{sector}</span>
                <span className="font-mono text-white font-bold">{wt.toFixed(1)}%</span>
              </span>
            )
          })}
        </div>
      </div>

      {/* Top 10 Underlying Stock Holdings Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-2.5">
        {holdings.map((h, i) => {
          const isUp = h.changePct >= 0
          return (
            <div
              key={i}
              className="p-3 rounded-2xl bg-slate-950/60 border border-white/[0.05] hover:border-white/[0.12] transition-all flex flex-col justify-between group"
            >
              <div>
                <div className="flex items-start justify-between gap-1 mb-1">
                  <span className="font-black text-white text-xs tracking-tight group-hover:text-emerald-300 transition-colors">
                    {h.symbol}
                  </span>
                  <span className="px-1.5 py-0.5 rounded-md bg-emerald-500/10 text-emerald-400 font-bold font-mono text-[10px]">
                    {h.weightPct}%
                  </span>
                </div>
                <div className="text-[11px] text-slate-400 truncate mb-2" title={h.name}>
                  {h.name}
                </div>
              </div>

              <div className="pt-2 border-t border-white/[0.04] flex items-center justify-between text-[11px]">
                <span className="font-mono text-slate-200 font-semibold">₹{h.livePrice}</span>
                <span
                  className={`font-bold text-[10px] flex items-center ${
                    isUp ? 'text-emerald-400' : 'text-rose-400'
                  }`}
                >
                  {isUp ? '+' : ''}
                  {h.changePct}%
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
