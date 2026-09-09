import React from 'react'
import {
  DirectionalForecast,
  ForecastHorizon,
  ExpectedDirection,
  ConfidenceLevel
} from '../../engine/marketIntelligence/types'
import { TrendingUp, TrendingDown, Minus, ShieldAlert, Sparkles, CheckCircle2, Clock } from 'lucide-react'

interface ProbabilisticForecastCardProps {
  forecast: DirectionalForecast | null
  activeHorizon: ForecastHorizon
  onSelectHorizon: (h: ForecastHorizon) => void
  evidenceFreshnessText?: string
}

export const ProbabilisticForecastCard: React.FC<ProbabilisticForecastCardProps> = ({
  forecast,
  activeHorizon,
  onSelectHorizon,
  evidenceFreshnessText = 'Very recent (<1h ago)'
}) => {
  const horizons: Array<{ id: ForecastHorizon; label: string; desc: string }> = [
    { id: '1D', label: '1D', desc: 'Next Session' },
    { id: '5D', label: '5D', desc: 'Swing (1 Wk)' },
    { id: '20D', label: '20D', desc: 'Medium (1 Mo)' },
    { id: '60D', label: '60D', desc: 'Quarterly (3 Mo)' }
  ]

  if (!forecast) {
    return (
      <div className="p-8 rounded-3xl bg-slate-900/60 border border-slate-800 text-center space-y-3">
        <ShieldAlert className="w-8 h-8 text-amber-400 mx-auto" />
        <h3 className="text-lg font-bold text-white">Insufficient Data for Forecast</h3>
        <p className="text-xs text-slate-400 max-w-md mx-auto">
          We refuse to fabricate market predictions. Real data for this horizon or asset is currently being refreshed or unavailable.
        </p>
      </div>
    )
  }

  const pBull = Math.round(forecast.probability_bullish * 100)
  const pNeu = Math.round(forecast.probability_neutral * 100)
  const pBear = Math.round(forecast.probability_bearish * 100)

  const directionColors: Record<ExpectedDirection, { bg: string; text: string; border: string }> = {
    'STRONGLY BULLISH': { bg: 'bg-emerald-500/10', text: 'text-emerald-400', border: 'border-emerald-500/30' },
    'MODERATELY BULLISH': { bg: 'bg-teal-500/10', text: 'text-teal-400', border: 'border-teal-500/30' },
    'NEUTRAL / RANGE-BOUND': { bg: 'bg-slate-500/10', text: 'text-slate-300', border: 'border-slate-500/30' },
    'MODERATELY BEARISH': { bg: 'bg-rose-500/10', text: 'text-rose-400', border: 'border-rose-500/30' },
    'STRONGLY BEARISH': { bg: 'bg-red-500/10', text: 'text-red-400', border: 'border-red-500/30' }
  }

  const dirStyle = directionColors[forecast.expected_direction]

  return (
    <div className="p-6 sm:p-8 rounded-3xl bg-slate-900/90 border border-white/[0.08] shadow-2xl relative overflow-hidden space-y-6">
      {/* Top Header: Horizon Picker */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-white/[0.06]">
        <div>
          <span className="text-[10px] uppercase font-bold tracking-widest text-emerald-400">
            Probabilistic Directional Forecast
          </span>
          <h2 className="text-xl sm:text-2xl font-black text-white mt-0.5">
            Expected Direction & Probability
          </h2>
        </div>

        {/* Horizon Tabs */}
        <div className="flex items-center space-x-1 p-1 rounded-2xl bg-slate-950/80 border border-white/[0.06] self-start sm:self-auto">
          {horizons.map((h) => {
            const isActive = activeHorizon === h.id
            return (
              <button
                key={h.id}
                onClick={() => onSelectHorizon(h.id)}
                className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all flex flex-col items-center ${
                  isActive
                    ? 'bg-gradient-to-r from-emerald-500 to-teal-500 text-slate-950 shadow-md font-extrabold'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                <span>{h.label}</span>
                <span className={`text-[9px] font-normal ${isActive ? 'text-slate-950 font-bold' : 'text-slate-500'}`}>
                  {h.desc}
                </span>
              </button>
            )
          })}
        </div>
      </div>

      {/* Main Signal Display */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-center">
        {/* Left: Direction Badge & Return Expectation (5 cols) */}
        <div className="lg:col-span-5 space-y-3">
          <div className="flex items-center space-x-2 text-xs text-slate-400">
            <span>Forecast Horizon:</span>
            <span className="font-bold text-white font-mono">{forecast.days} Trading Day{forecast.days > 1 ? 's' : ''}</span>
            <span>•</span>
            <span className="flex items-center space-x-1 text-slate-500 text-[11px]">
              <Clock className="w-3 h-3" />
              <span>{evidenceFreshnessText}</span>
            </span>
          </div>

          <div
            className={`inline-flex items-center space-x-2 px-4 py-2 rounded-2xl border text-sm sm:text-base font-black tracking-wide ${dirStyle.bg} ${dirStyle.text} ${dirStyle.border}`}
          >
            {forecast.expected_direction.includes('BULLISH') ? (
              <TrendingUp className="w-5 h-5" />
            ) : forecast.expected_direction.includes('BEARISH') ? (
              <TrendingDown className="w-5 h-5" />
            ) : (
              <Minus className="w-5 h-5" />
            )}
            <span>{forecast.expected_direction}</span>
          </div>

          <div className="text-xs text-slate-400 leading-relaxed">
            Expected return distribution median:{' '}
            <span className={`font-mono font-bold ${forecast.expected_return_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {forecast.expected_return_pct >= 0 ? '+' : ''}
              {forecast.expected_return_pct.toFixed(2)}%
            </span>{' '}
            over the selected horizon.
          </div>
        </div>

        {/* Right: Probability Gauge Stack Bar (7 cols) */}
        <div className="lg:col-span-7 space-y-3">
          <div className="flex items-center justify-between text-xs">
            <span className="font-bold text-slate-300">Calibrated Outcome Distribution</span>
            <span className="text-[10px] text-slate-500">Sum: 100% (Platt Scaled)</span>
          </div>

          {/* Segmented Stack Bar */}
          <div className="w-full h-4 bg-slate-950 rounded-full overflow-hidden flex border border-white/[0.06] shadow-inner">
            <div
              style={{ width: `${pBull}%` }}
              className="bg-emerald-500 h-full transition-all flex items-center justify-center text-[10px] font-black text-slate-950"
              title={`Bullish Probability: ${pBull}%`}
            >
              {pBull >= 12 && `${pBull}%`}
            </div>
            <div
              style={{ width: `${pNeu}%` }}
              className="bg-slate-600 h-full transition-all flex items-center justify-center text-[10px] font-bold text-slate-200"
              title={`Neutral / Range-bound Probability: ${pNeu}%`}
            >
              {pNeu >= 12 && `${pNeu}%`}
            </div>
            <div
              style={{ width: `${pBear}%` }}
              className="bg-rose-500 h-full transition-all flex items-center justify-center text-[10px] font-black text-slate-950"
              title={`Bearish Probability: ${pBear}%`}
            >
              {pBear >= 12 && `${pBear}%`}
            </div>
          </div>

          {/* Legend Chips */}
          <div className="grid grid-cols-3 gap-2 text-center text-xs">
            <div className="p-2 rounded-xl bg-emerald-500/5 border border-emerald-500/20">
              <div className="text-[10px] uppercase font-bold text-emerald-400">Bullish</div>
              <div className="text-lg font-black text-emerald-300">{pBull}%</div>
            </div>
            <div className="p-2 rounded-xl bg-slate-800/40 border border-slate-700/40">
              <div className="text-[10px] uppercase font-bold text-slate-400">Neutral</div>
              <div className="text-lg font-black text-slate-300">{pNeu}%</div>
            </div>
            <div className="p-2 rounded-xl bg-rose-500/5 border border-rose-500/20">
              <div className="text-[10px] uppercase font-bold text-rose-400">Bearish</div>
              <div className="text-lg font-black text-rose-300">{pBear}%</div>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom Row: Confidence, Signal Quality & Model Consensus */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-4 border-t border-white/[0.06] text-xs">
        {/* Card 1: Confidence */}
        <div className="p-3 rounded-2xl bg-white/[0.02] border border-white/[0.04] space-y-1">
          <div className="text-[10px] uppercase font-bold tracking-wider text-slate-500">
            Model Confidence
          </div>
          <div className="flex items-center space-x-2">
            <span
              className={`font-black font-mono px-2 py-0.5 rounded-md text-xs ${
                forecast.confidence === 'HIGH'
                  ? 'bg-emerald-500/20 text-emerald-400'
                  : forecast.confidence === 'MEDIUM'
                  ? 'bg-teal-500/20 text-teal-400'
                  : 'bg-amber-500/20 text-amber-400'
              }`}
            >
              {forecast.confidence}
            </span>
            <span className="text-[11px] text-slate-400">
              {forecast.confidence === 'HIGH'
                ? 'Strong probability separation'
                : forecast.confidence === 'MEDIUM'
                ? 'Moderate conviction'
                : 'Elevated uncertainty'}
            </span>
          </div>
        </div>

        {/* Card 2: Signal Quality */}
        <div className="p-3 rounded-2xl bg-white/[0.02] border border-white/[0.04] space-y-1">
          <div className="text-[10px] uppercase font-bold tracking-wider text-slate-500">
            Signal Quality
          </div>
          <div className="flex items-center space-x-2">
            <span className="text-base font-black text-white font-mono">
              {forecast.signal_quality}
              <span className="text-xs text-slate-500">/10</span>
            </span>
            <span className="text-[11px] text-slate-400">Point-in-time calibrated</span>
          </div>
        </div>

        {/* Card 3: Model Consensus */}
        <div className="p-3 rounded-2xl bg-white/[0.02] border border-white/[0.04] space-y-1">
          <div className="text-[10px] uppercase font-bold tracking-wider text-slate-500">
            Component Consensus
          </div>
          <div className="flex items-center space-x-2">
            <span className="font-bold text-slate-200">
              {forecast.model_disagreement.consensus_level}
            </span>
            <span className="text-[10px] text-slate-500 font-mono">
              (σ = {forecast.model_disagreement.dispersion_std})
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
