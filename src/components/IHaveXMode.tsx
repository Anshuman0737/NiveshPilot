import React, { useState } from 'react'
import { FundSnapshot, SuitabilityProfile } from '../engine/types'
import { computeInvestmentDecision } from '../engine/decision'
import {
  Shield,
  Sparkles,
  Check,
  ArrowRight,
  HelpCircle,
  AlertCircle,
  Info,
  BarChart2,
  Search,
  Building2,
  TrendingUp,
  Activity,
  Layers
} from 'lucide-react'
import { DeploymentTimelineGraph } from './DeploymentTimelineGraph'
import { InteractiveStrategyChart } from './InteractiveStrategyChart'
import { FundStockHoldingsCard } from './FundStockHoldingsCard'
import { LiveFundSearchModal } from './LiveFundSearchModal'

interface IHaveXModeProps {
  funds: FundSnapshot[]
  currentProfile: SuitabilityProfile
  onSelectFundForHome: (fund: FundSnapshot) => void
  onAddFund?: (fund: FundSnapshot) => void
}

const CATEGORIES = [
  'All',
  'Flexi Cap',
  'Large Cap',
  'Mid Cap',
  'Small Cap',
  'Hybrid',
  'Liquid'
]

export const IHaveXMode: React.FC<IHaveXModeProps> = ({
  funds,
  currentProfile,
  onSelectFundForHome,
  onAddFund
}) => {
  const [amount, setAmount] = useState<number>(currentProfile.amount || 25000)
  const [selectedFundId, setSelectedFundId] = useState<string>('PPFAS_FLEXI')
  const [selectedCategory, setSelectedCategory] = useState<string>('All')
  const [isSearchModalOpen, setIsSearchModalOpen] = useState<boolean>(false)

  // Ensure selectedFund is found
  const selectedFund =
    funds.find((f) => f.internal_id === selectedFundId) || funds[0]

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

  const filteredFunds = funds.filter((f) => {
    if (selectedCategory === 'All') return true
    return f.category.toLowerCase().includes(selectedCategory.toLowerCase())
  })

  const displayFunds = filteredFunds.length > 0 ? filteredFunds : funds

  const handleSelectLiveFund = (fund: FundSnapshot) => {
    if (onAddFund) {
      onAddFund(fund)
    }
    setSelectedFundId(fund.internal_id)
  }

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
      {/* Title & Explainer */}
      <div className="mb-8 text-center max-w-2xl mx-auto">
        <div className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-semibold uppercase tracking-wider mb-3">
          <Sparkles className="w-3.5 h-3.5" />
          <span>Dynamic Capital Allocator</span>
        </div>
        <h2 className="text-3xl sm:text-4xl font-extrabold text-white tracking-tight mb-2">
          "I Have ₹X to Invest"
        </h2>
        <p className="text-sm text-slate-400">
          Connected in real-time to official AMFI Mutual Fund NAVs and Indian equity stock prices.
          Calculate mathematical deployment splits without emotional bias.
        </p>
      </div>

      {/* Capital Input Card */}
      <div className="p-6 rounded-3xl bg-slate-900/90 border border-white/[0.08] shadow-2xl backdrop-blur-xl mb-8">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-5">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1">
              Available Capital to Deploy
            </label>
            <div className="text-3xl sm:text-4xl font-black text-white tracking-tight">
              {formatINR(amount)}
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            {quickPicks.map((pick) => (
              <button
                key={pick}
                onClick={() => setAmount(pick)}
                className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-all ${
                  amount === pick
                    ? 'bg-emerald-500 text-white shadow-lg shadow-emerald-500/25 scale-105'
                    : 'bg-white/[0.04] text-slate-300 hover:bg-white/[0.08] border border-white/[0.06]'
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

        {/* Fund Selection Header with Category Filters & Search Button */}
        <div className="pt-5 border-t border-white/[0.06]">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-3">
            <div>
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-300">
                Target Mutual Fund
              </label>
              <p className="text-[11px] text-slate-400">
                Choose from benchmark funds or search any of 40,000+ AMFI schemes live
              </p>
            </div>

            {/* Live Search AMFI Trigger Button */}
            <button
              onClick={() => setIsSearchModalOpen(true)}
              className="inline-flex items-center space-x-2 px-3.5 py-2 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-xs font-bold shadow-lg shadow-emerald-600/20 transition-all cursor-pointer shrink-0"
            >
              <Search className="w-3.5 h-3.5" />
              <span>Search 40,000+ AMFI Funds</span>
              <span className="text-[9px] px-1.5 py-0.2 rounded bg-white/20 uppercase font-black tracking-widest">
                LIVE
              </span>
            </button>
          </div>

          {/* Category Filter Pills */}
          <div className="flex items-center space-x-1.5 overflow-x-auto pb-2 mb-3 scrollbar-none">
            {CATEGORIES.map((cat) => (
              <button
                key={cat}
                onClick={() => setSelectedCategory(cat)}
                className={`px-2.5 py-1 rounded-lg text-xs font-medium whitespace-nowrap transition-all ${
                  selectedCategory === cat
                    ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 font-semibold'
                    : 'bg-white/[0.03] text-slate-400 hover:text-slate-200 border border-white/[0.04]'
                }`}
              >
                {cat}
              </button>
            ))}
          </div>

          {/* Fund Cards Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {displayFunds.map((f) => {
              const isChosen = f.internal_id === selectedFundId
              return (
                <button
                  key={f.internal_id}
                  onClick={() => setSelectedFundId(f.internal_id)}
                  className={`p-3.5 rounded-2xl border text-left transition-all relative overflow-hidden ${
                    isChosen
                      ? 'bg-gradient-to-br from-emerald-950/50 to-slate-900 border-emerald-500/80 shadow-lg shadow-emerald-950/50'
                      : 'bg-slate-950/60 border-white/[0.06] hover:border-white/[0.15]'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-[11px] font-semibold text-slate-400 truncate max-w-[140px]">
                      {f.category}
                    </span>
                    <div className="flex items-center space-x-1">
                      <span className="text-[9px] px-1.5 py-0.5 rounded bg-white/[0.06] text-emerald-400 font-bold border border-white/[0.06]">
                        {f.fund_quality_score}/100
                      </span>
                    </div>
                  </div>

                  <div className="text-xs font-bold text-white line-clamp-1 mb-1">
                    {f.scheme_name.split(' - ')[0]}
                  </div>

                  {/* Live NAV badge & 1Y return */}
                  <div className="flex items-center justify-between text-[11px] text-slate-400 pt-1 border-t border-white/[0.04]">
                    <span className="font-semibold text-slate-200">
                      NAV: ₹{f.current_nav ? f.current_nav.toFixed(2) : '100.00'}
                    </span>
                    <span className="text-emerald-400 font-semibold">
                      1Y: +{f.ret_1y}%
                    </span>
                  </div>
                </button>
              )
            })}
          </div>
        </div>
      </div>

      {/* Decision Output Container */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        {/* Left: Recommended Deployment Box */}
        <div className="lg:col-span-2 p-6 rounded-3xl bg-gradient-to-br from-slate-900 via-slate-900 to-navy-950 border border-white/[0.08] shadow-2xl">
          <div className="flex items-center justify-between pb-4 mb-4 border-b border-white/[0.06]">
            <div>
              <span className="text-xs uppercase tracking-wider font-semibold text-slate-400">
                Recommended Deployment
              </span>
              <h3 className="text-xl sm:text-2xl font-black text-white mt-0.5">{signal}</h3>
            </div>
            <span className="text-xs px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-300 border border-emerald-500/30 font-bold">
              Evidence: {evidenceStrength}
            </span>
          </div>

          {/* Allocation Split Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
            <div className="p-4 rounded-2xl bg-slate-950/70 border border-white/[0.06]">
              <span className="text-xs text-slate-400 font-medium">
                Deploy Immediately ({deployment.immediatePercent}%)
              </span>
              <div className="text-2xl sm:text-3xl font-black text-emerald-400 mt-1">
                {formatINR(deployment.immediateAmount)}
              </div>
              <p className="text-xs text-slate-400 mt-1 line-clamp-1">
                Invest today into {selectedFund.scheme_name.split(' - ')[0]}
              </p>
            </div>

            <div className="p-4 rounded-2xl bg-slate-950/70 border border-white/[0.06]">
              <span className="text-xs text-slate-400 font-medium">
                Stagger for Later ({deployment.staggeredPercent}%)
              </span>
              <div className="text-2xl sm:text-3xl font-black text-teal-400 mt-1">
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
          <div className="p-3.5 rounded-xl bg-slate-950/80 border border-white/[0.06] text-xs text-slate-400">
            <strong className="text-amber-300 font-semibold block mb-1">What could go wrong?</strong>
            {risks[0] || 'Market could decline further after initial entry, testing emotional resolve.'}
          </div>
        </div>

        {/* Right: Historical Comparable Evidence */}
        <div className="p-6 rounded-3xl bg-slate-900 border border-white/[0.08] shadow-2xl flex flex-col justify-between">
          <div>
            <span className="text-xs uppercase tracking-wider font-semibold text-slate-400">
              Historical Track
            </span>
            <h3 className="text-lg font-bold text-white mt-0.5 mb-4">Past Comparable Outcomes</h3>

            <p className="text-xs text-slate-400 mb-4 leading-relaxed">
              Based on {historicalStats.occurredCount} walk-forward rolling test periods under similar market regimes:
            </p>

            <div className="space-y-3 mb-6">
              <div className="p-3 rounded-xl bg-slate-950 border border-white/[0.06]">
                <div className="text-xs text-slate-400">12-Month Positive Frequency</div>
                <div className="text-xl font-bold text-emerald-400">
                  {historicalStats.positive12mPct}%
                </div>
                <div className="text-[11px] text-slate-500">Periods finishing above invested capital</div>
              </div>

              <div className="p-3 rounded-xl bg-slate-950 border border-white/[0.06]">
                <div className="text-xs text-slate-400">Median 12-Month Gain</div>
                <div className="text-xl font-bold text-white">
                  +{historicalStats.median12mReturnPct}%
                </div>
                <div className="text-[11px] text-slate-500">Median outcome across tested windows</div>
              </div>

              <div className="p-3 rounded-xl bg-slate-950 border border-white/[0.06]">
                <div className="text-xs text-slate-400">Worst Case Drawdown</div>
                <div className="text-xl font-bold text-rose-400">
                  {historicalStats.worst12mReturnPct}%
                </div>
                <div className="text-[11px] text-slate-500">Staggering buffered catastrophic crash</div>
              </div>
            </div>
          </div>

          <div className="pt-4 border-t border-white/[0.06] text-[11px] text-slate-500 leading-normal">
            <Info className="w-3.5 h-3.5 inline mr-1 text-slate-400" />
            Decision Intelligence output is purely educational decision support. Not SEBI registered investment advice.
          </div>
        </div>
      </div>

      {/* Live Underlying Stock Holdings Card */}
      <div className="mb-8">
        <FundStockHoldingsCard
          fundId={selectedFund.internal_id}
          fundName={selectedFund.scheme_name}
          category={selectedFund.category}
        />
      </div>

      {/* Interactive Capital Trajectory & Drawdown Protection Curve */}
      <div className="mt-8">
        <InteractiveStrategyChart
          initialCapital={amount}
          defaultScenario="walkforward_12m"
        />
      </div>

      {/* Live AMFI Search Modal */}
      <LiveFundSearchModal
        isOpen={isSearchModalOpen}
        onClose={() => setIsSearchModalOpen(false)}
        onSelectFund={handleSelectLiveFund}
      />
    </div>
  )
}

