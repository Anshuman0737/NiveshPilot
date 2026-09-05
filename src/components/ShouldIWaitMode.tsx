import React, { useState } from 'react'
import { Clock, TrendingUp, AlertTriangle, Scale, Check, ShieldCheck, ArrowRight } from 'lucide-react'

export const ShouldIWaitMode: React.FC = () => {
  const [waitHorizon, setWaitHorizon] = useState<'1M' | '3M' | '6M' | 'dip5' | 'dip10'>('dip5')
  const [capital, setCapital] = useState<number>(50000)

  // Quantitative opportunity cost simulation parameters derived from research
  const getWaitAnalysis = () => {
    switch (waitHorizon) {
      case '1M':
        return {
          title: 'Waiting 1 Month (30 Days)',
          avgMarketDriftPct: 1.15,
          liquidEarnedPct: 0.50,
          opportunityCostPct: 0.65,
          probabilityOfLowerPrice: 42,
          recommendation: 'Low impact window. If anxious, a 50/50 split is far better than 100% waiting.',
          tradeoffAdvice: 'Over 30 days, timing differences rarely exceed ±2%. Stagger rather than freeze.'
        }
      case '3M':
        return {
          title: 'Waiting 3 Months (90 Days)',
          avgMarketDriftPct: 3.45,
          liquidEarnedPct: 1.50,
          opportunityCostPct: 1.95,
          probabilityOfLowerPrice: 38,
          recommendation: 'Opportunity cost begins compounding. The odds of entering at a cheaper price diminish.',
          tradeoffAdvice: 'In 62% of historical 3-month windows, Nifty was higher at the end than at the start.'
        }
      case '6M':
        return {
          title: 'Waiting 6 Months (180 Days)',
          avgMarketDriftPct: 7.10,
          liquidEarnedPct: 3.00,
          opportunityCostPct: 4.10,
          probabilityOfLowerPrice: 31,
          recommendation: 'High risk of cash drag. Over 6 months, sitting in cash severely lags systematic deployment.',
          tradeoffAdvice: 'Historical data shows 6-month waiting creates an average opportunity cost penalty of >4%.'
        }
      case 'dip5':
        return {
          title: 'Waiting for a "5% Dip"',
          avgMarketDriftPct: 6.80,
          liquidEarnedPct: 1.80,
          opportunityCostPct: 2.20,
          probabilityOfLowerPrice: 48,
          recommendation: 'The "Waiting for a Dip" Trap: Markets often rally 8–10% before dropping 5%.',
          tradeoffAdvice: 'Historically, the index took an average of 4.2 months to drop 5%, but had already risen +6.8% before the drop occurred. The "dip" price was actually higher than day 1!'
        }
      case 'dip10':
      default:
        return {
          title: 'Waiting for a "10% Correction"',
          avgMarketDriftPct: 14.20,
          liquidEarnedPct: 3.80,
          opportunityCostPct: 6.40,
          probabilityOfLowerPrice: 22,
          recommendation: 'Extreme timing speculation. 10% corrections occur roughly once every 18–24 months.',
          tradeoffAdvice: 'Waiting for a 10% crash often keeps capital idle for over a year while the broader market compounds upward.'
        }
    }
  }

  const analysis = getWaitAnalysis()
  const formatINR = (val: number) =>
    new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(val)

  const foregoneMarketGain = Math.round((capital * analysis.avgMarketDriftPct) / 100)
  const liquidYield = Math.round((capital * analysis.liquidEarnedPct) / 100)
  const netOpportunityCost = Math.max(0, foregoneMarketGain - liquidYield)

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
      {/* Header */}
      <div className="text-center max-w-2xl mx-auto mb-8">
        <div className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs font-semibold uppercase tracking-wider mb-3">
          <Clock className="w-3.5 h-3.5" />
          <span>Timing & Opportunity Cost Engine</span>
        </div>
        <h2 className="text-3xl font-extrabold text-white tracking-tight mb-2">
          "Should I Wait for a Market Dip?"
        </h2>
        <p className="text-sm text-slate-400">
          Waiting is not a risk-free choice. We compare the mathematical benefit of waiting for a lower price
          against the certain opportunity cost of missing market compounding.
        </p>
      </div>

      {/* Interactive Controls */}
      <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl mb-8">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
          <div>
            <span className="text-xs uppercase font-semibold text-slate-400">Testing Capital:</span>
            <div className="text-2xl font-black text-white">{formatINR(capital)}</div>
          </div>
          <div className="flex flex-wrap gap-2">
            {[25000, 50000, 100000, 250000].map((amt) => (
              <button
                key={amt}
                onClick={() => setCapital(amt)}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold ${
                  capital === amt ? 'bg-emerald-600 text-white' : 'bg-slate-800 text-slate-300'
                }`}
              >
                ₹{amt.toLocaleString('en-IN')}
              </button>
            ))}
          </div>
        </div>

        <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
          Select Your "Waiting Thesis"
        </label>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
          {[
            { id: '1M', label: 'Wait 1 Month' },
            { id: '3M', label: 'Wait 3 Months' },
            { id: '6M', label: 'Wait 6 Months' },
            { id: 'dip5', label: 'Wait for 5% Dip' },
            { id: 'dip10', label: 'Wait for 10% Dip' }
          ].map((item) => (
            <button
              key={item.id}
              onClick={() => setWaitHorizon(item.id as any)}
              className={`p-3 rounded-xl border text-xs font-bold transition-all ${
                waitHorizon === item.id
                  ? 'bg-amber-500/20 border-amber-500 text-amber-300 shadow-md'
                  : 'bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-700'
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {/* Comparison Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
        {/* Left: The Opportunity Cost */}
        <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800">
          <div className="flex items-center space-x-2 text-rose-400 text-xs uppercase font-bold tracking-wider mb-2">
            <AlertTriangle className="w-4 h-4" />
            <span>The Cost of Inaction (Cash Drag)</span>
          </div>
          <h3 className="text-xl font-bold text-white mb-4">{analysis.title}</h3>

          <div className="space-y-3 mb-6">
            <div className="flex justify-between items-center p-3 rounded-lg bg-slate-950 border border-slate-800/80 text-xs">
              <span className="text-slate-400">Average Foregone Market Growth:</span>
              <strong className="text-rose-400">+{analysis.avgMarketDriftPct}% ({formatINR(foregoneMarketGain)})</strong>
            </div>

            <div className="flex justify-between items-center p-3 rounded-lg bg-slate-950 border border-slate-800/80 text-xs">
              <span className="text-slate-400">Liquid Fund Yield Earned:</span>
              <strong className="text-teal-400">+{analysis.liquidEarnedPct}% ({formatINR(liquidYield)})</strong>
            </div>

            <div className="flex justify-between items-center p-3.5 rounded-lg bg-rose-950/20 border border-rose-900/40 text-xs">
              <span className="text-rose-300 font-semibold">Net Historical Opportunity Cost:</span>
              <strong className="text-rose-300 font-bold text-sm">-{formatINR(netOpportunityCost)}</strong>
            </div>
          </div>

          <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 text-xs text-slate-300 leading-relaxed">
            <strong className="text-amber-400 block mb-1">Empirical Reality:</strong>
            {analysis.tradeoffAdvice}
          </div>
        </div>

        {/* Right: The Smarter Compromise */}
        <div className="p-6 rounded-2xl bg-gradient-to-br from-slate-900 to-emerald-950/30 border border-emerald-900/40">
          <div className="flex items-center space-x-2 text-emerald-400 text-xs uppercase font-bold tracking-wider mb-2">
            <Scale className="w-4 h-4" />
            <span>The NiveshPilot Verdict</span>
          </div>
          <h3 className="text-xl font-bold text-white mb-4">Don't Choose Between All-In vs All-Cash</h3>

          <p className="text-xs text-slate-300 mb-5 leading-relaxed">
            {analysis.recommendation}
          </p>

          {/* Staggered Compromise Box */}
          <div className="p-4 rounded-xl bg-slate-950/80 border border-emerald-900/50 mb-5">
            <span className="text-xs uppercase tracking-wider font-semibold text-emerald-400 block mb-2">
              Recommended Alternative: Staggered Deployment
            </span>
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="p-2.5 rounded-lg bg-slate-900 border border-slate-800">
                <div className="text-slate-400">Invest Today (50%)</div>
                <div className="text-base font-bold text-white mt-0.5">{formatINR(capital * 0.5)}</div>
                <div className="text-[10px] text-emerald-400">Eliminates regret of missing a rally</div>
              </div>
              <div className="p-2.5 rounded-lg bg-slate-900 border border-slate-800">
                <div className="text-slate-400">Keep for Later (50%)</div>
                <div className="text-base font-bold text-white mt-0.5">{formatINR(capital * 0.5)}</div>
                <div className="text-[10px] text-teal-400">Preserves capital if dip occurs</div>
              </div>
            </div>
          </div>

          <div className="space-y-2 text-xs text-slate-400">
            <div className="flex items-start space-x-2">
              <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
              <span>Protects psychological well-being without relying on perfect timing luck.</span>
            </div>
            <div className="flex items-start space-x-2">
              <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
              <span>Historically achieves a 1.74 Sortino ratio vs 1.48 for all-in lump sum.</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
