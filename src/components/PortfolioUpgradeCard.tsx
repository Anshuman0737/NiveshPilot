import React, { useState } from 'react'
import { Holding } from '../engine/types'
import { PortfolioOptimizationBlueprint } from '../engine/portfolioOptimizer'
import {
  TrendingUp,
  Sparkles,
  ArrowRight,
  ShieldCheck,
  CheckCircle2,
  XCircle,
  PlusCircle,
  Clock,
  Layers,
  Percent,
  Check,
  Zap
} from 'lucide-react'

interface PortfolioUpgradeCardProps {
  blueprint: PortfolioOptimizationBlueprint
  onApplyUpgrade: (upgradedHoldings: Holding[]) => void
}

export const PortfolioUpgradeCard: React.FC<PortfolioUpgradeCardProps> = ({
  blueprint,
  onApplyUpgrade
}) => {
  const [isApplied, setIsApplied] = useState(false)

  const formatINR = (val: number) =>
    new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(val)

  const handleApply = () => {
    onApplyUpgrade(blueprint.upgradedHoldings)
    setIsApplied(true)
    setTimeout(() => setIsApplied(false), 4000)
  }

  const keepActions = blueprint.actions.filter((a) => a.type === 'keep')
  const pruneActions = blueprint.actions.filter((a) => a.type === 'prune')
  const addActions = blueprint.actions.filter((a) => a.type === 'add')

  return (
    <div className="p-6 sm:p-8 rounded-3xl glass-panel relative overflow-hidden border border-emerald-500/20 shadow-2xl mb-8 transition-all">
      {/* Soft Ambient Radial Accents */}
      <div className="absolute -top-24 -right-24 w-80 h-80 bg-emerald-500/[0.08] rounded-full blur-3xl pointer-events-none" />
      <div className="absolute -bottom-24 -left-24 w-80 h-80 bg-indigo-500/[0.06] rounded-full blur-3xl pointer-events-none" />

      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 pb-6 mb-6 border-b border-white/[0.06] relative z-10">
        <div>
          <div className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-[11px] font-bold uppercase tracking-wider mb-2">
            <Zap className="w-3 h-3 fill-emerald-400" />
            <span>Empirical Portfolio Upgrade Blueprint</span>
          </div>
          <h3 className="text-2xl sm:text-3xl font-black text-white tracking-tight">
            Upgraded Best Version of Your Holdings
          </h3>
          <p className="text-xs sm:text-sm text-slate-400 mt-1 max-w-2xl leading-relaxed">
            Eliminates duplicate large-cap stock overlap, cuts distributor fee drag, and locks in institutional-grade diversification.
          </p>
        </div>

        <div className="flex items-center shrink-0">
          <button
            onClick={handleApply}
            disabled={isApplied}
            className={`px-6 py-3 rounded-full font-extrabold text-xs sm:text-sm flex items-center space-x-2 transition-all shadow-xl ${
              isApplied
                ? 'bg-emerald-500 text-navy-950 shadow-emerald-500/25'
                : 'bg-emerald-500 hover:bg-emerald-400 text-navy-950 shadow-emerald-500/20 hover:scale-[1.02]'
            }`}
          >
            {isApplied ? (
              <>
                <Check className="w-4 h-4 text-navy-950 font-black" />
                <span>Upgraded Portfolio Applied!</span>
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4 text-navy-950" />
                <span>Apply Upgraded Portfolio</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Side-by-Side Comparison Metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3.5 mb-6 relative z-10">
        {/* Health Score */}
        <div className="p-4 rounded-2xl bg-slate-950/60 border border-white/[0.06]">
          <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider flex items-center justify-between">
            <span>Portfolio Score</span>
            <span className="text-[10px] font-bold text-emerald-400">+{blueprint.scoreDelta} pts</span>
          </span>
          <div className="flex items-baseline space-x-2 mt-1.5">
            <span className="text-xl font-bold text-slate-500 line-through">
              {blueprint.currentScore}/100
            </span>
            <ArrowRight className="w-3.5 h-3.5 text-slate-600 shrink-0" />
            <span className="text-2xl font-black text-emerald-400 text-glow-emerald">
              {blueprint.upgradedScore}/100
            </span>
          </div>
          <span className="text-[11px] text-slate-500">Quality + asset balance</span>
        </div>

        {/* Expense Ratio */}
        <div className="p-4 rounded-2xl bg-slate-950/60 border border-white/[0.06]">
          <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider flex items-center justify-between">
            <span>Annual Fee Drag</span>
            <Percent className="w-3.5 h-3.5 text-indigo-400" />
          </span>
          <div className="flex items-baseline space-x-2 mt-1.5">
            <span className="text-xl font-bold text-rose-400/80 line-through">
              {blueprint.currentExpenseRatio}%
            </span>
            <ArrowRight className="w-3.5 h-3.5 text-slate-600 shrink-0" />
            <span className="text-2xl font-black text-emerald-400">
              {blueprint.upgradedExpenseRatio}%
            </span>
          </div>
          <span className="text-[11px] text-slate-500">Direct plan TER savings</span>
        </div>

        {/* 10-Year Compounded Fee Savings */}
        <div className="p-4 rounded-2xl bg-emerald-500/[0.08] border border-emerald-500/25">
          <span className="text-[11px] font-semibold text-emerald-300 uppercase tracking-wider flex items-center justify-between">
            <span>10-Yr Extra Wealth</span>
            <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
          </span>
          <div className="text-2xl font-black text-emerald-400 mt-1.5 text-glow-emerald">
            {formatINR(blueprint.tenYearFeeSavings)}
          </div>
          <span className="text-[11px] text-emerald-300/80">Compounded extra in your pocket</span>
        </div>

        {/* Peak Stock Overlap */}
        <div className="p-4 rounded-2xl bg-slate-950/60 border border-white/[0.06]">
          <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider flex items-center justify-between">
            <span>Peak Overlap</span>
            <Layers className="w-3.5 h-3.5 text-indigo-400" />
          </span>
          <div className="flex items-baseline space-x-2 mt-1.5">
            <span className="text-xl font-bold text-amber-400/80 line-through">
              {blueprint.currentMaxOverlap}%
            </span>
            <ArrowRight className="w-3.5 h-3.5 text-slate-600 shrink-0" />
            <span className="text-2xl font-black text-emerald-400">
              {blueprint.upgradedMaxOverlap}%
            </span>
          </div>
          <span className="text-[11px] text-slate-500">Duplicate stocks eliminated</span>
        </div>
      </div>

      {/* Key Optimization Insights */}
      {blueprint.keyInsights.length > 0 && (
        <div className="p-4 rounded-2xl bg-slate-950/50 border border-white/[0.05] mb-6 space-y-2">
          <div className="text-xs font-bold text-slate-300 flex items-center space-x-1.5 uppercase tracking-wider">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <span>Empirical Diagnosis & Rationale</span>
          </div>
          {blueprint.keyInsights.map((insight, idx) => (
            <p key={idx} className="text-xs text-slate-300 leading-relaxed pl-4 relative">
              <span className="absolute left-1 top-1.5 w-1.5 h-1.5 rounded-full bg-emerald-400" />
              {insight}
            </p>
          ))}
        </div>
      )}

      {/* Step-by-Step Action Roadmap */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5 mb-6">
        {/* Keep Section */}
        <div className="p-4 rounded-2xl bg-slate-950/50 border border-emerald-500/20 flex flex-col">
          <div className="flex items-center space-x-2 mb-3 pb-2 border-b border-white/[0.05]">
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            <span className="text-xs font-bold text-emerald-400 uppercase tracking-wider">
              Step 1: Keep Core ({keepActions.length})
            </span>
          </div>
          <div className="space-y-2.5 flex-1">
            {keepActions.length === 0 ? (
              <p className="text-xs text-slate-500 italic">No existing fund retained.</p>
            ) : (
              keepActions.map((act, i) => (
                <div key={i} className="p-3 rounded-xl bg-slate-900/60 border border-white/[0.04] text-xs">
                  <div className="font-bold text-white mb-0.5">{act.fundName}</div>
                  <div className="text-[11px] text-emerald-400 font-semibold mb-1">
                    Target Weight: {act.targetWeightPct}%
                  </div>
                  <p className="text-[11px] text-slate-400 leading-snug">{act.reason}</p>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Prune / Switch Section */}
        <div className="p-4 rounded-2xl bg-slate-950/50 border border-rose-500/20 flex flex-col">
          <div className="flex items-center space-x-2 mb-3 pb-2 border-b border-white/[0.05]">
            <XCircle className="w-4 h-4 text-rose-400 shrink-0" />
            <span className="text-xs font-bold text-rose-400 uppercase tracking-wider">
              Step 2: Prune / Stop SIP ({pruneActions.length})
            </span>
          </div>
          <div className="space-y-2.5 flex-1">
            {pruneActions.length === 0 ? (
              <p className="text-xs text-slate-500 italic">No funds need pruning.</p>
            ) : (
              pruneActions.map((act, i) => (
                <div key={i} className="p-3 rounded-xl bg-slate-900/60 border border-white/[0.04] text-xs">
                  <div className="font-bold text-white mb-0.5">{act.fundName}</div>
                  <div className="text-[11px] text-rose-400 font-semibold mb-1">
                    Action: Stop SIP / Reallocate
                  </div>
                  <p className="text-[11px] text-slate-400 leading-snug">{act.reason}</p>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Add Section */}
        <div className="p-4 rounded-2xl bg-slate-950/50 border border-indigo-500/20 flex flex-col">
          <div className="flex items-center space-x-2 mb-3 pb-2 border-b border-white/[0.05]">
            <PlusCircle className="w-4 h-4 text-indigo-400 shrink-0" />
            <span className="text-xs font-bold text-indigo-400 uppercase tracking-wider">
              Step 3: Add to Complete ({addActions.length})
            </span>
          </div>
          <div className="space-y-2.5 flex-1">
            {addActions.length === 0 ? (
              <p className="text-xs text-slate-500 italic">Portfolio is complete. No new funds needed.</p>
            ) : (
              addActions.map((act, i) => (
                <div key={i} className="p-3 rounded-xl bg-slate-900/60 border border-white/[0.04] text-xs">
                  <div className="font-bold text-white mb-0.5">{act.fundName}</div>
                  <div className="text-[11px] text-indigo-400 font-semibold mb-1">
                    Target Weight: {act.targetWeightPct}%
                  </div>
                  <p className="text-[11px] text-slate-400 leading-snug">{act.reason}</p>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Future Monthly SIP Blueprint */}
      <div className="p-4 rounded-2xl bg-slate-950/70 border border-white/[0.06]">
        <div className="flex items-center justify-between mb-3 pb-2 border-b border-white/[0.05]">
          <div className="flex items-center space-x-2 text-xs font-bold text-amber-300 uppercase tracking-wider">
            <Clock className="w-3.5 h-3.5 text-amber-400" />
            <span>Recommended Future Monthly SIP Allocation</span>
          </div>
          <span className="text-[11px] text-slate-400">Set this in Groww / Zerodha / INDmoney</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {blueprint.recommendedSipBreakdown.map((sip, idx) => (
            <div
              key={idx}
              className="p-3 rounded-xl bg-slate-900/50 border border-white/[0.04] flex flex-col justify-between"
            >
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-bold text-white">{sip.fundName}</span>
                  <span className="px-2 py-0.5 rounded-full bg-amber-400/10 border border-amber-400/20 text-amber-300 text-[11px] font-bold">
                    {sip.allocationPct}%
                  </span>
                </div>
                <div className="text-[11px] text-slate-400 mb-2">{sip.category}</div>
              </div>
              <p className="text-[10px] text-slate-400 leading-tight">{sip.reason}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
