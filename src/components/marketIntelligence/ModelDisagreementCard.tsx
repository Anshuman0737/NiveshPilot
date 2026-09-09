import React from 'react'
import { ModelDisagreement } from '../../engine/marketIntelligence/types'
import { Layers, CheckCircle2, AlertTriangle, ShieldCheck } from 'lucide-react'

interface ModelDisagreementCardProps {
  disagreement: ModelDisagreement
}

export const ModelDisagreementCard: React.FC<ModelDisagreementCardProps> = ({ disagreement }) => {
  const { components, dispersion_std, consensus_level } = disagreement

  const subModels = [
    {
      id: 'technical',
      name: 'Technical / Price Dynamics',
      desc: 'RSI(14), MACD histogram, realized 30D volatility & volume anomaly',
      score: components.technical
    },
    {
      id: 'fundamental',
      name: 'Fundamental / Relative Strength',
      desc: '20-day benchmark alpha, valuation metrics & multi-year drawdowns',
      score: components.fundamental
    },
    {
      id: 'event_news',
      name: 'Event / Information Surprise',
      desc: 'Actual vs expected surprise scores, filings & multi-factor sentiment',
      score: components.event_news
    },
    {
      id: 'macro_regime',
      name: 'Macro & Market Regime',
      desc: 'NSE benchmark trend, 50/200 SMA slope, India VIX & liquidity conditions',
      score: components.macro_regime
    },
    {
      id: 'cross_asset',
      name: 'Cross-Asset & Commodity Context',
      desc: 'USD/INR FX volatility, crude oil 20D momentum & sector tailwinds',
      score: components.cross_asset
    }
  ]

  return (
    <div className="p-6 rounded-3xl bg-slate-900/80 border border-white/[0.08] shadow-2xl space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-white/[0.06]">
        <div>
          <span className="text-[10px] uppercase font-bold tracking-widest text-emerald-400">
            Ensemble Transparency
          </span>
          <h3 className="text-base font-bold text-white mt-0.5">
            Component Model Conviction & Disagreement
          </h3>
        </div>

        <div className="flex items-center space-x-2">
          <span
            className={`px-3 py-1 rounded-full text-xs font-bold border flex items-center space-x-1.5 ${
              consensus_level === 'High Consensus'
                ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                : consensus_level === 'Moderate Agreement'
                ? 'bg-teal-500/10 text-teal-400 border-teal-500/30'
                : 'bg-amber-500/10 text-amber-400 border-amber-500/30'
            }`}
          >
            {consensus_level === 'High Consensus' ? (
              <CheckCircle2 className="w-3.5 h-3.5" />
            ) : (
              <AlertTriangle className="w-3.5 h-3.5" />
            )}
            <span>{consensus_level}</span>
          </span>
          <span className="text-[11px] font-mono text-slate-500">σ = {dispersion_std}</span>
        </div>
      </div>

      <div className="space-y-3.5">
        {subModels.map((m) => {
          const isPos = m.score >= 0
          const barWidth = Math.min(100, Math.abs(m.score))

          return (
            <div key={m.id} className="space-y-1.5">
              <div className="flex items-center justify-between text-xs">
                <div>
                  <span className="font-bold text-slate-200">{m.name}</span>
                  <div className="text-[10px] text-slate-500">{m.desc}</div>
                </div>
                <span
                  className={`font-mono font-black text-xs ${
                    isPos ? 'text-emerald-400' : 'text-rose-400'
                  }`}
                >
                  {isPos ? '+' : ''}
                  {m.score.toFixed(1)}
                </span>
              </div>

              {/* Centered bi-directional conviction bar (-100 to +100) */}
              <div className="w-full h-2 bg-slate-950 rounded-full overflow-hidden flex border border-white/[0.04] relative">
                {/* Center marker (0) */}
                <div className="absolute top-0 bottom-0 left-1/2 w-0.5 bg-slate-700 z-10" />

                {/* Left side (negative) */}
                <div className="w-1/2 h-full flex justify-end">
                  {!isPos && (
                    <div
                      style={{ width: `${barWidth}%` }}
                      className="h-full bg-rose-500 rounded-l-full transition-all"
                    />
                  )}
                </div>

                {/* Right side (positive) */}
                <div className="w-1/2 h-full flex justify-start">
                  {isPos && (
                    <div
                      style={{ width: `${barWidth}%` }}
                      className="h-full bg-emerald-500 rounded-r-full transition-all"
                    />
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
