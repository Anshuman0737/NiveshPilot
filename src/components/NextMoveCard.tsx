import React, { useState } from 'react'
import {
  EvidenceObject,
  RecommendationSignal,
  FundSnapshot,
  SuitabilityProfile,
  ExplanationLevel
} from '../engine/types'
import {
  ChevronDown,
  ChevronUp,
  HelpCircle,
  AlertTriangle,
  RefreshCw,
  History,
  CheckCircle2,
  Ban,
  Scale,
  ShieldAlert,
  ArrowRight,
  Sliders,
  Layers,
  Sparkles,
  Info,
  TrendingUp,
  BarChart2
} from 'lucide-react'
import { InteractiveStrategyChart } from './InteractiveStrategyChart'
import { DeploymentTimelineGraph } from './DeploymentTimelineGraph'
import { AICoPilotCard } from './AICoPilotCard'

interface NextMoveCardProps {
  evidence: EvidenceObject
  fund: FundSnapshot
  profile: SuitabilityProfile
  onSelectFund: (fund: FundSnapshot) => void
  allFunds: FundSnapshot[]
  onModifyProfile: () => void
  onOpenAISettings?: () => void
}

export const NextMoveCard: React.FC<NextMoveCardProps> = ({
  evidence,
  fund,
  profile,
  onSelectFund,
  allFunds,
  onModifyProfile,
  onOpenAISettings
}) => {
  const [explanationLevel, setExplanationLevel] = useState<ExplanationLevel>('Beginner')
  const [showDeepDiagnostics, setShowDeepDiagnostics] = useState<boolean>(false)
  const [openDiagnosticDrawer, setOpenDiagnosticDrawer] = useState<string | null>(null)

  const {
    signal,
    deployment,
    marketRegime,
    volatilityDesc,
    drawdownDesc,
    evidenceStrength,
    mainReasons,
    risks,
    invalidationConditions,
    whyNotInvestAllNow,
    whatIfIWait,
    whatIfIIgnoreNiveshPilot,
    whyWeMightBeWrong,
    historicalStats,
    decision_id,
    modelHealth,
    modelHealthReason,
    whatChanged
  } = evidence

  const formatINR = (val: number) =>
    new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0
    }).format(val)

  const getSignalBadge = (sig: RecommendationSignal) => {
    switch (sig) {
      case 'INVEST NOW':
        return {
          bg: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300',
          dot: 'bg-emerald-400',
          desc: 'Current evidence supports high initial entry with a modest liquidity buffer.'
        }
      case 'INVEST GRADUALLY':
        return {
          bg: 'bg-teal-500/10 border-teal-500/30 text-teal-300',
          dot: 'bg-teal-400',
          desc: 'Deploy some capital today, keeping dry powder in liquid yields for better prices.'
        }
      case 'WAIT':
      case 'HOLD':
        return {
          bg: 'bg-amber-500/10 border-amber-500/30 text-amber-300',
          dot: 'bg-amber-400',
          desc: 'Market is moving more sharply than usual. Stagger capital defensively.'
        }
      case "DON'T INVEST IN EQUITY":
        return {
          bg: 'bg-rose-500/10 border-rose-500/30 text-rose-300',
          dot: 'bg-rose-400',
          desc: 'Equity risk conflicts with your time horizon or immediate safety needs.'
        }
      default:
        return {
          bg: 'bg-slate-800 border-slate-700 text-slate-300',
          dot: 'bg-slate-400',
          desc: 'Mixed or stale indicators. Default to systematic baseline.'
        }
    }
  }

  const badge = getSignalBadge(signal)

  const toggleDiagnostic = (id: string) => {
    setOpenDiagnosticDrawer(openDiagnosticDrawer === id ? null : id)
  }

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6">
      <div className="rounded-3xl bg-slate-900/90 border border-slate-800 shadow-2xl overflow-hidden backdrop-blur-sm">
        {/* Header Bar: Suitability Profile Summary & Tiered Explanation Selector */}
        <div className="px-6 py-4 border-b border-slate-800/80 bg-slate-950/60 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
          <div className="flex flex-wrap items-center gap-2 text-slate-400">
            <span>Profile:</span>
            <span className="font-semibold text-white">{formatINR(profile.amount || 10000)}</span>
            <span>•</span>
            <span className="font-semibold text-white">{profile.horizon} horizon</span>
            <span>•</span>
            <span className="font-semibold text-white">{profile.goal}</span>
            <button
              onClick={onModifyProfile}
              className="text-indigo-400 hover:text-indigo-300 font-bold underline ml-1"
            >
              Edit
            </button>
          </div>

          {/* Explanation Level Selector */}
          <div className="flex items-center space-x-1 self-start sm:self-auto bg-slate-900 p-1 rounded-xl border border-slate-800">
            <span className="text-[10px] uppercase font-bold text-slate-500 px-2">Mode:</span>
            {(['Beginner', 'Intermediate', 'Research'] as ExplanationLevel[]).map((lvl) => (
              <button
                key={lvl}
                onClick={() => setExplanationLevel(lvl)}
                className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all ${
                  explanationLevel === lvl
                    ? 'bg-indigo-600 text-white shadow'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {lvl}
              </button>
            ))}
          </div>
        </div>

        {/* Model Health / Audit Notice Bar */}
        <div className="px-6 py-2 bg-slate-950/40 border-b border-slate-800/60 flex flex-wrap items-center justify-between gap-2 text-[11px]">
          <div className="flex items-center space-x-2">
            <span className="text-slate-500">Model Health:</span>
            <span
              className={`font-semibold px-2 py-0.5 rounded-full border text-[10px] ${
                modelHealth === 'HEALTHY'
                  ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                  : modelHealth === 'CAUTION'
                  ? 'bg-amber-500/10 border-amber-500/30 text-amber-300'
                  : 'bg-rose-500/10 border-rose-500/30 text-rose-400'
              }`}
            >
              {modelHealth}
            </span>
            <span className="text-slate-400">{modelHealthReason}</span>
          </div>

          {whatChanged && explanationLevel !== 'Beginner' && (
            <div className="text-indigo-300 text-[11px] truncate max-w-md">
              <span className="font-bold">What changed: </span>
              <span>{whatChanged}</span>
            </div>
          )}
        </div>

        {/* PRIMARY SCREEN: Clean 4-Part Information Architecture */}
        <div className="p-6 sm:p-8 space-y-6">
          {/* SECTION 1: The Core Recommendation & Deployment Split */}
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 pb-6 border-b border-slate-800">
            <div>
              <span className="text-xs uppercase tracking-widest font-extrabold text-slate-400 block mb-1">
                Your Evidence-Backed Next Move
              </span>
              <div className="flex items-center space-x-3">
                <h1 className="text-3xl sm:text-4xl font-black text-white tracking-tight">
                  {signal}
                </h1>
                <span
                  className={`inline-flex items-center space-x-1.5 px-3 py-1 rounded-full border text-xs font-bold ${badge.bg}`}
                >
                  <span className={`w-2 h-2 rounded-full ${badge.dot}`}></span>
                  <span>{evidenceStrength} Evidence</span>
                </span>
              </div>
              <p className="text-sm text-slate-300 mt-2 max-w-xl leading-relaxed">
                {badge.desc}
              </p>
            </div>

            {/* Exact Rupee Deployment Box */}
            <div className="p-4 rounded-2xl bg-slate-950 border border-slate-800 shrink-0 min-w-[240px]">
              <span className="text-[10px] uppercase font-bold tracking-wider text-slate-400 block mb-2">
                Capital Deployment Plan ({formatINR(profile.amount || 10000)})
              </span>
              {signal === "DON'T INVEST IN EQUITY" ? (
                <div className="text-rose-300 text-xs font-semibold">
                  100% reserved in SBI Liquid Fund / High-Yield Fixed Deposit
                </div>
              ) : (
                <div className="space-y-2 text-xs">
                  <div className="flex justify-between items-center">
                    <span className="text-slate-300">Invest Today:</span>
                    <span className="text-base font-bold text-emerald-400">
                      {formatINR(deployment.immediateAmount)} ({deployment.immediatePercent}%)
                    </span>
                  </div>
                  {deployment.staggeredPercent > 0 && (
                    <div className="flex justify-between items-center pt-1 border-t border-slate-900">
                      <span className="text-slate-400">Stagger Later:</span>
                      <span className="font-semibold text-slate-200">
                        {formatINR(deployment.staggeredAmount)} ({deployment.staggeredPercent}%)
                      </span>
                    </div>
                  )}
                  <div className="text-[10px] text-slate-500 pt-1">
                    {deployment.staggerDurationDesc}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Fund Selector Dropdown */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3.5 rounded-xl bg-slate-950/60 border border-slate-800 text-xs">
            <div className="flex items-center space-x-2">
              <span className="text-slate-400">Target Fund:</span>
              <span className="font-bold text-white">{fund.scheme_name}</span>
              <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono text-[10px]">
                {fund.category}
              </span>
            </div>
            <select
              value={fund.internal_id}
              onChange={(e) => {
                const sel = allFunds.find((f) => f.internal_id === e.target.value)
                if (sel) onSelectFund(sel)
              }}
              className="bg-slate-900 text-slate-200 border border-slate-700 rounded-lg px-2.5 py-1 text-xs focus:outline-none focus:border-indigo-500"
            >
              {allFunds.map((f) => (
                <option key={f.internal_id} value={f.internal_id}>
                  {f.scheme_name}
                </option>
              ))}
            </select>
          </div>

          {/* Interactive Dynamic Deployment Flow Visualizer */}
          <DeploymentTimelineGraph
            deployment={deployment}
            totalCapital={profile.amount || 10000}
            fundName={fund.scheme_name}
          />

          {/* AI Co-Pilot & Adversarial Decision Audit Card */}
          <AICoPilotCard
            evidence={evidence}
            fund={fund}
            profile={profile}
            onOpenSettings={onOpenAISettings || (() => {})}
          />

          {/* SECTION 2: WHY (Primary Rationale) */}
          <div className="p-5 rounded-2xl bg-slate-950/70 border border-slate-800/80 space-y-3">
            <div className="flex items-center space-x-2 text-xs font-bold uppercase tracking-wider text-emerald-400">
              <CheckCircle2 className="w-4 h-4" />
              <span>Why This Move Makes Sense Right Now</span>
            </div>

            <div className="space-y-2 text-sm text-slate-200 leading-relaxed">
              {explanationLevel === 'Beginner' ? (
                <>
                  <p className="flex items-start space-x-2">
                    <span className="text-emerald-400 font-bold">•</span>
                    <span>{volatilityDesc}.</span>
                  </p>
                  <p className="flex items-start space-x-2">
                    <span className="text-emerald-400 font-bold">•</span>
                    <span>{drawdownDesc}.</span>
                  </p>
                  <p className="flex items-start space-x-2">
                    <span className="text-emerald-400 font-bold">•</span>
                    <span>{mainReasons[0] || 'Deployment structure balances upside participation with risk containment.'}</span>
                  </p>
                </>
              ) : (
                mainReasons.map((reason, idx) => (
                  <p key={idx} className="flex items-start space-x-2">
                    <span className="text-emerald-400 font-bold">•</span>
                    <span>{reason}</span>
                  </p>
                ))
              )}
            </div>
          </div>

          {/* SECTION 3: RISK (What Could Go Wrong) */}
          <div className="p-5 rounded-2xl bg-slate-950/70 border border-slate-800/80 space-y-3">
            <div className="flex items-center space-x-2 text-xs font-bold uppercase tracking-wider text-amber-400">
              <AlertTriangle className="w-4 h-4" />
              <span>What Could Go Wrong (Downside Scenarios)</span>
            </div>

            <div className="space-y-2 text-sm text-slate-300 leading-relaxed">
              {risks.slice(0, explanationLevel === 'Beginner' ? 2 : risks.length).map((r, idx) => (
                <div key={idx} className="flex items-start space-x-2">
                  <span className="text-amber-400 font-bold">•</span>
                  <span>{r}</span>
                </div>
              ))}
            </div>
          </div>

          {/* SECTION 4: HISTORICAL EVIDENCE (Comparable Past Precedents) */}
          <div className="p-5 rounded-2xl bg-slate-950/70 border border-slate-800/80">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center space-x-2 text-xs font-bold uppercase tracking-wider text-indigo-400">
                <History className="w-4 h-4" />
                <span>Historical Precedent ({historicalStats.occurredCount} Test Windows)</span>
              </div>
              <span className="text-[11px] text-slate-400">12-Month Walk-Forward Results</span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
              <div className="p-3 rounded-xl bg-slate-900 border border-slate-800">
                <span className="text-slate-400 block mb-1">Positive Outcome Rate</span>
                <span className="text-lg font-bold text-emerald-400">{historicalStats.positive12mPct}%</span>
                <span className="text-[10px] text-slate-500 block mt-0.5">Windows with nominal gain</span>
              </div>

              <div className="p-3 rounded-xl bg-slate-900 border border-slate-800">
                <span className="text-slate-400 block mb-1">Median 12-Month Return</span>
                <span className="text-lg font-bold text-white">+{historicalStats.median12mReturnPct}%</span>
                <span className="text-[10px] text-slate-500 block mt-0.5">Not annualized CAGR</span>
              </div>

              <div className="p-3 rounded-xl bg-slate-900 border border-slate-800">
                <span className="text-slate-400 block mb-1">Worst Single Crash</span>
                <span className="text-lg font-bold text-rose-400">{historicalStats.worst12mReturnPct}%</span>
                <span className="text-[10px] text-slate-500 block mt-0.5">Peak Covid drop</span>
              </div>
            </div>

            {/* Interactive Strategy Comparison & Drawdown Protection Chart */}
            <div className="mt-4 pt-4 border-t border-slate-900">
              <InteractiveStrategyChart
                initialCapital={profile.amount || 10000}
                defaultScenario="walkforward_12m"
              />
            </div>
          </div>

          {/* DEEP DIAGNOSTICS ACCORDION TOGGLE (Priority 26) */}
          <div className="pt-2 border-t border-slate-800/80">
            <button
              onClick={() => setShowDeepDiagnostics(!showDeepDiagnostics)}
              className="w-full py-3 px-4 rounded-xl bg-slate-950 hover:bg-slate-900 border border-slate-800 text-xs font-bold text-indigo-300 flex items-center justify-between transition-colors"
            >
              <div className="flex items-center space-x-2">
                <Sliders className="w-4 h-4 text-indigo-400" />
                <span>{showDeepDiagnostics ? 'Hide Full Decision Diagnostics' : 'Inspect Full Decision Diagnostics & Counterfactuals'}</span>
              </div>
              {showDeepDiagnostics ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>

            {/* Deep diagnostics inner drawers */}
            {showDeepDiagnostics && (
              <div className="mt-4 space-y-3 text-xs">
                {/* Drawer 1: Why not invest all now? */}
                {whyNotInvestAllNow && (
                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
                    <button
                      onClick={() => toggleDiagnostic('whyNotAllNow')}
                      className="w-full flex items-center justify-between text-left font-bold text-slate-200"
                    >
                      <div className="flex items-center space-x-2">
                        <Scale className="w-3.5 h-3.5 text-teal-400" />
                        <span>Why not invest 100% right now?</span>
                      </div>
                      {openDiagnosticDrawer === 'whyNotAllNow' ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                    </button>
                    {(openDiagnosticDrawer === 'whyNotAllNow' || explanationLevel === 'Research') && (
                      <p className="mt-2 text-slate-300 leading-relaxed border-t border-slate-900 pt-2">
                        {whyNotInvestAllNow}
                      </p>
                    )}
                  </div>
                )}

                {/* Drawer 2: What if I wait? */}
                {whatIfIWait && (
                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
                    <button
                      onClick={() => toggleDiagnostic('whatIfWait')}
                      className="w-full flex items-center justify-between text-left font-bold text-slate-200"
                    >
                      <div className="flex items-center space-x-2">
                        <HelpCircle className="w-3.5 h-3.5 text-indigo-400" />
                        <span>What if I wait for a dip?</span>
                      </div>
                      {openDiagnosticDrawer === 'whatIfWait' ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                    </button>
                    {(openDiagnosticDrawer === 'whatIfWait' || explanationLevel === 'Research') && (
                      <p className="mt-2 text-slate-300 leading-relaxed border-t border-slate-900 pt-2">
                        {whatIfIWait}
                      </p>
                    )}
                  </div>
                )}

                {/* Drawer 3: What if I ignore NiveshPilot? */}
                {whatIfIIgnoreNiveshPilot && (
                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
                    <button
                      onClick={() => toggleDiagnostic('whatIfIgnore')}
                      className="w-full flex items-center justify-between text-left font-bold text-slate-200"
                    >
                      <div className="flex items-center space-x-2">
                        <ArrowRight className="w-3.5 h-3.5 text-purple-400" />
                        <span>What if I ignore NiveshPilot?</span>
                      </div>
                      {openDiagnosticDrawer === 'whatIfIgnore' ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                    </button>
                    {(openDiagnosticDrawer === 'whatIfIgnore' || explanationLevel === 'Research') && (
                      <p className="mt-2 text-slate-300 leading-relaxed border-t border-slate-900 pt-2">
                        {whatIfIIgnoreNiveshPilot}
                      </p>
                    )}
                  </div>
                )}

                {/* Drawer 4: Invalidation rules */}
                <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
                  <button
                    onClick={() => toggleDiagnostic('invalidation')}
                    className="w-full flex items-center justify-between text-left font-bold text-slate-200"
                  >
                    <div className="flex items-center space-x-2">
                      <RefreshCw className="w-3.5 h-3.5 text-cyan-400" />
                      <span>What would change our view? (Invalidation Rules)</span>
                    </div>
                    {openDiagnosticDrawer === 'invalidation' ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                  </button>
                  {(openDiagnosticDrawer === 'invalidation' || explanationLevel === 'Research') && (
                    <div className="mt-2 text-slate-300 space-y-1.5 border-t border-slate-900 pt-2">
                      {invalidationConditions.map((cond, i) => (
                        <div key={i} className="flex items-start space-x-2">
                          <span className="text-cyan-400 font-bold">•</span>
                          <span>{cond}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Drawer 5: Deterministic Decision Replay */}
                <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-between text-[11px] font-mono">
                  <span className="text-slate-500">Deterministic Replay Token:</span>
                  <span className="text-indigo-300 font-bold">{decision_id}</span>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
