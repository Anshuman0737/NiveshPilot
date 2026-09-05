import React, { useState } from 'react'
import { FundSnapshot, SuitabilityProfile } from '../engine/types'
import { computeInvestmentDecision } from '../engine/decision'
import { Shield, Sparkles, Check, ArrowRight, HelpCircle, AlertCircle, Info, BarChart2 } from 'lucide-react'
import { DeploymentTimelineGraph } from './DeploymentTimelineGraph'
import { InteractiveStrategyChart } from './InteractiveStrategyChart'

interface IHaveXModeProps {
  funds: FundSnapshot[]
  currentProfile: SuitabilityProfile
  onSelectFundForHome: (fund: FundSnapshot) => void
}

export const IHaveXMode: React.FC<IHaveXModeProps> = ({
  funds,
  currentProfile,
  onSelectFundForHome
}) => {
  const [amount, setAmount] = useState<number>(currentProfile.amount || 25000)
  const [selectedFundId, setSelectedFundId] = useState<string>('PPFAS_FLEXI')

  const selectedFund = funds.find((f) => f.internal_id === selectedFundId) || funds[0]

  const customProfile: SuitabilityProfile = {
    ...currentProfile,
    amount
  }

  const decision = computeInvestmentDecision(customProfile, selectedFund)
  const { deployment, signal, mainReasons, risks, historicalStats, evidenceStrength } = decision

  const formatINR = (val: number) =>
    new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0
    }).format(val)

  const quickPicks = [5000, 10000, 25000, 50000, 100000, 250000]

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
      {/* Title & Explainer */}
      <div className="mb-8 text-center max-w-2xl mx-auto">
        <div className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-semibold uppercase tracking-wider mb-3">
          <Sparkles className="w-3.5 h-3.5" />
          <span>Flagship Decision Tool</span>
        </div>
        <h2 className="text-3xl font-extrabold text-white tracking-tight mb-2">
          "I Have ₹X to Invest"
        </h2>
        <p className="text-sm text-slate-400">
          Enter any amount of capital. We calculate the evidence-backed immediate vs staggered
          deployment based on market regimes and risk containment.
        </p>
      </div>

      {/* Capital Input Card */}
      <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl mb-8">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-5">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1">
              Available Capital
            </label>
            <div className="text-3xl sm:text-4xl font-black text-white">{formatINR(amount)}</div>
          </div>

          <div className="flex flex-wrap gap-2">
            {quickPicks.map((pick) => (
              <button
                key={pick}
                onClick={() => setAmount(pick)}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                  amount === pick
                    ? 'bg-emerald-600 text-white shadow-md'
                    : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
                }`}
              >
                ₹{pick.toLocaleString('en-IN')}
              </button>
            ))}
          </div>
        </div>

        {/* Range Slider */}
        <input
          type="range"
          min="1000"
          max="500000"
          step="1000"
          value={amount}
          onChange={(e) => setAmount(Number(e.target.value))}
          className="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-emerald-500 mb-6"
        />

        {/* Fund Candidate Selector */}
        <div className="pt-4 border-t border-slate-800">
          <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
            Select Target Fund or Category
          </label>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
            {funds.map((f) => {
              const isChosen = f.internal_id === selectedFundId
              return (
                <button
                  key={f.internal_id}
                  onClick={() => setSelectedFundId(f.internal_id)}
                  className={`p-3 rounded-xl border text-left transition-all ${
                    isChosen
                      ? 'bg-emerald-950/40 border-emerald-500/80 shadow-md'
                      : 'bg-slate-950/60 border-slate-800 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[11px] font-semibold text-slate-400">{f.category}</span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-emerald-400 font-bold">
                      {f.fund_quality_score}/100
                    </span>
                  </div>
                  <div className="text-xs font-bold text-white line-clamp-1">{f.scheme_name.split(' - ')[0]}</div>
                  <div className="text-[11px] text-slate-400 mt-1">1Y Return: +{f.ret_1y}% • Exp: {f.expense_ratio}%</div>
                </button>
              )
            })}
          </div>
        </div>
      </div>

      {/* Decision Output Container */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Recommended Deployment Box */}
        <div className="lg:col-span-2 p-6 rounded-2xl bg-gradient-to-br from-slate-900 via-slate-900 to-navy-950 border border-slate-800 shadow-xl">
          <div className="flex items-center justify-between pb-4 mb-4 border-b border-slate-800">
            <div>
              <span className="text-xs uppercase tracking-wider font-semibold text-slate-400">
                Recommended Deployment
              </span>
              <h3 className="text-xl font-black text-white mt-0.5">{signal}</h3>
            </div>
            <span className="text-xs px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-300 border border-emerald-500/30 font-bold">
              Evidence: {evidenceStrength}
            </span>
          </div>

          {/* Allocation Split Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
              <span className="text-xs text-slate-400 font-medium">Deploy Immediately ({deployment.immediatePercent}%)</span>
              <div className="text-2xl font-black text-emerald-400 mt-1">
                {formatINR(deployment.immediateAmount)}
              </div>
              <p className="text-xs text-slate-400 mt-1">
                Invest today into {selectedFund.scheme_name.split(' - ')[0]}
              </p>
            </div>

            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
              <span className="text-xs text-slate-400 font-medium">Stagger for Later ({deployment.staggeredPercent}%)</span>
              <div className="text-2xl font-black text-teal-400 mt-1">
                {formatINR(deployment.staggeredAmount)}
              </div>
              <p className="text-xs text-slate-400 mt-1">
                {deployment.staggerDurationDesc} (park in liquid yield)
              </p>
            </div>
          </div>

          {/* Dynamic Deployment Timeline Flow */}
          <div className="mb-5">
            <DeploymentTimelineGraph
              deployment={deployment}
              totalCapital={amount}
              fundName={selectedFund.scheme_name}
            />
          </div>

          {/* Key Rationale */}
          <div className="mb-5">
            <h4 className="text-xs uppercase tracking-wider font-bold text-slate-400 mb-2">
              Why this specific split?
            </h4>
            <ul className="space-y-1.5 text-xs text-slate-300">
              {mainReasons.map((r, i) => (
                <li key={i} className="flex items-start space-x-2">
                  <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
                  <span>{r}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Downside & Risks */}
          <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 text-xs text-slate-400">
            <strong className="text-amber-300 font-semibold block mb-1">What could go wrong?</strong>
            {risks[0] || 'Market could decline further after initial entry, testing emotional resolve.'}
          </div>
        </div>

        {/* Right: Historical Comparable Evidence */}
        <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl flex flex-col justify-between">
          <div>
            <span className="text-xs uppercase tracking-wider font-semibold text-slate-400">
              Historical Track
            </span>
            <h3 className="text-lg font-bold text-white mt-0.5 mb-4">Past Comparable Outcomes</h3>

            <p className="text-xs text-slate-400 mb-4 leading-relaxed">
              Based on {historicalStats.occurredCount} walk-forward rolling test periods under similar market regimes:
            </p>

            <div className="space-y-3 mb-6">
              <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                <div className="text-xs text-slate-400">12-Month Positive Frequency</div>
                <div className="text-xl font-bold text-emerald-400">{historicalStats.positive12mPct}%</div>
                <div className="text-[11px] text-slate-500">Periods finishing above invested capital</div>
              </div>

              <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                <div className="text-xs text-slate-400">Median 12-Month Gain</div>
                <div className="text-xl font-bold text-white">+{historicalStats.median12mReturnPct}%</div>
                <div className="text-[11px] text-slate-500">Median outcome across tested windows</div>
              </div>

              <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                <div className="text-xs text-slate-400">Worst Case Drawdown</div>
                <div className="text-xl font-bold text-rose-400">{historicalStats.worst12mReturnPct}%</div>
                <div className="text-[11px] text-slate-500">Staggering buffered catastrophic crash</div>
              </div>
            </div>
          </div>

          <div className="pt-4 border-t border-slate-800 text-[11px] text-slate-500 leading-normal">
            <Info className="w-3.5 h-3.5 inline mr-1 text-slate-400" />
            Decision Intelligence output is purely educational decision support. Not SEBI registered investment advice.
          </div>
        </div>
      </div>

      {/* Interactive Capital Trajectory & Drawdown Protection Curve */}
      <div className="mt-8">
        <InteractiveStrategyChart
          initialCapital={amount}
          defaultScenario="walkforward_12m"
        />
      </div>
    </div>
  )
}
