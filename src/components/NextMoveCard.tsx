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
  Scale,
  ArrowRight,
  Sliders,
  Sparkles,
  BarChart3,
  Bot,
  Layers,
  FileCheck2
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

type CardTab = 'charts' | 'rationale' | 'ai' | 'diagnostics'

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
  const [activeTab, setActiveTab] = useState<CardTab>('charts')
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
          desc: 'Current market evidence supports high initial entry with a disciplined liquid buffer.'
        }
      case 'INVEST GRADUALLY':
        return {
          bg: 'bg-teal-500/10 border-teal-500/30 text-teal-300',
          dot: 'bg-teal-400',
          desc: 'Deploy some capital today, keeping dry powder in liquid yields to accumulate lower prices.'
        }
      case 'WAIT':
      case 'HOLD':
        return {
          bg: 'bg-amber-500/10 border-amber-500/30 text-amber-300',
          dot: 'bg-amber-400',
          desc: 'Turbulent volatility detected. Prioritize capital preservation in risk-free liquid yields.'
        }
      case "DON'T INVEST IN EQUITY":
        return {
          bg: 'bg-rose-500/10 border-rose-500/30 text-rose-300',
          dot: 'bg-rose-400',
          desc: 'Short time horizon or emergency buffer needed. Equity is unsuitable at this stage.'
        }
      default:
        return {
          bg: 'bg-slate-800 border-slate-700 text-slate-300',
          dot: 'bg-slate-400',
          desc: 'Mixed or stale indicators. Defaulting to systematic dollar-cost averaging baseline.'
        }
    }
  }

  const badge = getSignalBadge(signal)

  const toggleDiagnostic = (id: string) => {
    setOpenDiagnosticDrawer(openDiagnosticDrawer === id ? null : id)
  }

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6">
      {/* Sleek Master Card */}
      <div className="rounded-3xl glass-panel relative overflow-hidden border border-white/[0.08] shadow-2xl transition-all">
        {/* Subtle Ambient Radial Glow */}
        <div className="absolute -top-32 -right-32 w-80 h-80 bg-emerald-500/[0.07] rounded-full blur-3xl pointer-events-none" />
        <div className="absolute -bottom-32 -left-32 w-80 h-80 bg-indigo-500/[0.05] rounded-full blur-3xl pointer-events-none" />

        {/* Top Metadata Strip */}
        <div className="px-6 py-3.5 border-b border-white/[0.06] bg-slate-950/40 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
          <div className="flex flex-wrap items-center gap-2 text-slate-400">
            <span className="font-semibold text-white">{formatINR(profile.amount || 10000)}</span>
            <span className="text-slate-600">•</span>
            <span className="text-slate-300">{profile.horizon} horizon</span>
            <span className="text-slate-600">•</span>
            <span className="text-slate-300">{profile.goal}</span>
            <button
              onClick={onModifyProfile}
              className="text-xs text-indigo-400 hover:text-indigo-300 font-semibold px-2 py-0.5 rounded-full hover:bg-white/[0.05] transition-colors ml-1"
            >
              Edit Profile
            </button>
          </div>

          {/* Mode Pill Switcher */}
          <div className="flex items-center p-1 bg-slate-900/80 rounded-full border border-white/[0.06] text-[11px]">
            <span className="text-[10px] uppercase font-bold text-slate-500 px-2.5">Level:</span>
            {(['Beginner', 'Intermediate', 'Research'] as ExplanationLevel[]).map((lvl) => (
              <button
                key={lvl}
                onClick={() => setExplanationLevel(lvl)}
                className={`px-3 py-1 rounded-full font-medium transition-all ${
                  explanationLevel === lvl
                    ? 'bg-white/[0.12] text-white shadow-sm font-semibold'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {lvl}
              </button>
            ))}
          </div>
        </div>

        {/* Main Decision Hero */}
        <div className="p-6 sm:p-8 border-b border-white/[0.06]">
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
            <div>
              <div className="flex items-center space-x-2 mb-2">
                <span className="text-[11px] uppercase tracking-widest font-bold text-slate-400">
                  Your Evidence-Backed Next Move
                </span>
                <span
                  className={`inline-flex items-center space-x-1.5 px-2.5 py-0.5 rounded-full border text-[11px] font-bold ${badge.bg}`}
                >
                  <span className={`w-1.5 h-1.5 rounded-full ${badge.dot}`} />
                  <span>{evidenceStrength} Evidence</span>
                </span>
              </div>

              <h2 className="text-3xl sm:text-5xl font-black text-white tracking-tight">
                {signal}
              </h2>
              <p className="text-sm text-slate-300 mt-2 max-w-xl leading-relaxed">
                {badge.desc}
              </p>
            </div>

            {/* Visual Rupee Deployment Split Card */}
            <div className="p-4 sm:p-5 rounded-2xl bg-slate-950/70 border border-white/[0.08] min-w-[280px]">
              <div className="flex items-center justify-between text-[11px] uppercase font-bold text-slate-400 mb-2">
                <span>Capital Deployment Split</span>
                <span className="text-white">{formatINR(profile.amount || 10000)}</span>
              </div>

              {signal === "DON'T INVEST IN EQUITY" ? (
                <div className="text-rose-300 text-xs font-semibold py-1">
                  100% reserved in SBI Liquid Fund / High-Yield Fixed Deposit
                </div>
              ) : (
                <div className="space-y-2.5">
                  {/* Visual Progress Bar Ratio */}
                  <div className="w-full h-3 rounded-full bg-slate-800 overflow-hidden flex">
                    <div
                      style={{ width: `${deployment.immediatePercent}%` }}
                      className="bg-emerald-500 h-full transition-all"
                      title={`Invest Now: ${deployment.immediatePercent}%`}
                    />
                    <div
                      style={{ width: `${deployment.staggeredPercent}%` }}
                      className="bg-teal-500/40 h-full transition-all"
                      title={`Stagger/Buffer: ${deployment.staggeredPercent}%`}
                    />
                  </div>

                  <div className="flex justify-between items-baseline text-xs">
                    <div>
                      <span className="text-slate-400 block text-[10px]">Invest Now:</span>
                      <span className="font-bold text-emerald-400 text-sm">
                        {formatINR(deployment.immediateAmount)}{' '}
                        <span className="text-xs font-normal">({deployment.immediatePercent}%)</span>
                      </span>
                    </div>
                    {deployment.staggeredPercent > 0 && (
                      <div className="text-right">
                        <span className="text-slate-400 block text-[10px]">Liquid Buffer:</span>
                        <span className="font-bold text-teal-300 text-sm">
                          {formatINR(deployment.staggeredAmount)}{' '}
                          <span className="text-xs font-normal">({deployment.staggeredPercent}%)</span>
                        </span>
                      </div>
                    )}
                  </div>

                  <div className="text-[10px] text-slate-500 leading-tight">
                    {deployment.staggerDurationDesc}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Minimal Target Fund Selector Strip */}
          <div className="mt-6 flex flex-wrap items-center justify-between gap-3 p-3 rounded-2xl bg-white/[0.02] border border-white/[0.05] text-xs">
            <div className="flex items-center space-x-2">
              <span className="text-slate-500">Benchmark Scheme:</span>
              <span className="font-bold text-white">{fund.scheme_name}</span>
              <span className="px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 text-[10px] font-mono">
                {fund.category}
              </span>
            </div>

            <select
              value={fund.internal_id}
              onChange={(e) => {
                const sel = allFunds.find((f) => f.internal_id === e.target.value)
                if (sel) onSelectFund(sel)
              }}
              className="bg-slate-900/90 text-slate-200 border border-white/[0.08] rounded-xl px-3 py-1 text-xs focus:outline-none focus:border-indigo-500 cursor-pointer"
            >
              {allFunds.map((f) => (
                <option key={f.internal_id} value={f.internal_id}>
                  {f.scheme_name}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Minimalist Segmented Inner Tab Dock */}
        <div className="px-6 pt-4 pb-2 bg-slate-950/40 border-b border-white/[0.04] flex items-center space-x-1.5 overflow-x-auto text-xs scrollbar-none">
          <button
            onClick={() => setActiveTab('charts')}
            className={`px-3.5 py-1.5 rounded-full transition-all flex items-center space-x-1.5 ${
              activeTab === 'charts'
                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-semibold'
                : 'text-slate-400 hover:text-white hover:bg-white/[0.04]'
            }`}
          >
            <BarChart3 className="w-3.5 h-3.5" />
            <span>Trajectory & Timeline</span>
          </button>

          <button
            onClick={() => setActiveTab('rationale')}
            className={`px-3.5 py-1.5 rounded-full transition-all flex items-center space-x-1.5 ${
              activeTab === 'rationale'
                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-semibold'
                : 'text-slate-400 hover:text-white hover:bg-white/[0.04]'
            }`}
          >
            <CheckCircle2 className="w-3.5 h-3.5" />
            <span>Why & Risk Scenarios</span>
          </button>

          <button
            onClick={() => setActiveTab('ai')}
            className={`px-3.5 py-1.5 rounded-full transition-all flex items-center space-x-1.5 ${
              activeTab === 'ai'
                ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 font-semibold'
                : 'text-slate-400 hover:text-white hover:bg-white/[0.04]'
            }`}
          >
            <Bot className="w-3.5 h-3.5" />
            <span>AI Co-Pilot Audit</span>
          </button>

          <button
            onClick={() => setActiveTab('diagnostics')}
            className={`px-3.5 py-1.5 rounded-full transition-all flex items-center space-x-1.5 ${
              activeTab === 'diagnostics'
                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-semibold'
                : 'text-slate-400 hover:text-white hover:bg-white/[0.04]'
            }`}
          >
            <Sliders className="w-3.5 h-3.5" />
            <span>Audit & Transparency</span>
          </button>
        </div>

        {/* Tab View Contents */}
        <div className="p-6 sm:p-8 space-y-6">
          {/* TAB 1: CHARTS (Trajectory & Deployment Scrubber) */}
          {activeTab === 'charts' && (
            <div className="space-y-6 animate-fade-in">
              <InteractiveStrategyChart
                initialCapital={profile.amount || 10000}
                defaultScenario="walkforward_12m"
              />

              <DeploymentTimelineGraph
                deployment={deployment}
                totalCapital={profile.amount || 10000}
                fundName={fund.scheme_name}
              />
            </div>
          )}

          {/* TAB 2: RATIONALE & RISKS */}
          {activeTab === 'rationale' && (
            <div className="space-y-5 animate-fade-in">
              {/* Why */}
              <div className="p-5 rounded-2xl bg-slate-950/60 border border-white/[0.06] space-y-2.5">
                <div className="flex items-center space-x-2 text-xs font-bold uppercase tracking-wider text-emerald-400">
                  <CheckCircle2 className="w-4 h-4" />
                  <span>Why This Move Makes Sense</span>
                </div>
                <div className="space-y-2 text-sm text-slate-300 leading-relaxed">
                  <p className="flex items-start space-x-2">
                    <span className="text-emerald-400 font-bold">•</span>
                    <span>{volatilityDesc}.</span>
                  </p>
                  <p className="flex items-start space-x-2">
                    <span className="text-emerald-400 font-bold">•</span>
                    <span>{drawdownDesc}.</span>
                  </p>
                  {mainReasons.map((r, i) => (
                    <p key={i} className="flex items-start space-x-2">
                      <span className="text-emerald-400 font-bold">•</span>
                      <span>{r}</span>
                    </p>
                  ))}
                </div>
              </div>

              {/* Risks */}
              <div className="p-5 rounded-2xl bg-slate-950/60 border border-white/[0.06] space-y-2.5">
                <div className="flex items-center space-x-2 text-xs font-bold uppercase tracking-wider text-amber-400">
                  <AlertTriangle className="w-4 h-4" />
                  <span>What Could Go Wrong (Downside Scenarios)</span>
                </div>
                <div className="space-y-2 text-sm text-slate-300 leading-relaxed">
                  {risks.map((r, i) => (
                    <div key={i} className="flex items-start space-x-2">
                      <span className="text-amber-400 font-bold">•</span>
                      <span>{r}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Historical Precedent */}
              <div className="p-5 rounded-2xl bg-slate-950/60 border border-white/[0.06]">
                <div className="flex items-center justify-between mb-3 text-xs">
                  <span className="font-bold text-white flex items-center space-x-2">
                    <History className="w-3.5 h-3.5 text-indigo-400" />
                    <span>Historical Precedent ({historicalStats.occurredCount} Test Windows)</span>
                  </span>
                  <span className="text-slate-400 text-[11px]">12M Walk-Forward Windows</span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                  <div className="p-3 rounded-xl bg-slate-900 border border-white/[0.05]">
                    <span className="text-slate-400 block mb-0.5">Positive Outcomes</span>
                    <span className="text-lg font-bold text-emerald-400">{historicalStats.positive12mPct}%</span>
                    <span className="text-[10px] text-slate-500 block">Periods with gain</span>
                  </div>
                  <div className="p-3 rounded-xl bg-slate-900 border border-white/[0.05]">
                    <span className="text-slate-400 block mb-0.5">Median 12M Return</span>
                    <span className="text-lg font-bold text-white">+{historicalStats.median12mReturnPct}%</span>
                    <span className="text-[10px] text-slate-500 block">Typical period return</span>
                  </div>
                  <div className="p-3 rounded-xl bg-slate-900 border border-white/[0.05]">
                    <span className="text-slate-400 block mb-0.5">Worst Single Drop</span>
                    <span className="text-lg font-bold text-rose-400">{historicalStats.worst12mReturnPct}%</span>
                    <span className="text-[10px] text-slate-500 block">Covid crash trough</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: AI CO-PILOT */}
          {activeTab === 'ai' && (
            <div className="animate-fade-in">
              <AICoPilotCard
                evidence={evidence}
                fund={fund}
                profile={profile}
                onOpenSettings={onOpenAISettings || (() => {})}
              />
            </div>
          )}

          {/* TAB 4: DIAGNOSTICS & AUDIT */}
          {activeTab === 'diagnostics' && (
            <div className="space-y-3 animate-fade-in text-xs">
              {/* Token */}
              <div className="p-3 rounded-xl bg-slate-950/80 border border-white/[0.06] flex items-center justify-between font-mono text-[11px]">
                <span className="text-slate-500">Deterministic Replay Token:</span>
                <span className="text-indigo-300 font-bold select-all">{decision_id}</span>
              </div>

              {/* Drawer 1: Why not invest all now? */}
              {whyNotInvestAllNow && (
                <div className="p-4 rounded-xl bg-slate-950/60 border border-white/[0.06]">
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
                  {openDiagnosticDrawer === 'whyNotAllNow' && (
                    <p className="mt-2 text-slate-300 leading-relaxed border-t border-white/[0.04] pt-2">
                      {whyNotInvestAllNow}
                    </p>
                  )}
                </div>
              )}

              {/* Drawer 2: What if I wait? */}
              {whatIfIWait && (
                <div className="p-4 rounded-xl bg-slate-950/60 border border-white/[0.06]">
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
                  {openDiagnosticDrawer === 'whatIfWait' && (
                    <p className="mt-2 text-slate-300 leading-relaxed border-t border-white/[0.04] pt-2">
                      {whatIfIWait}
                    </p>
                  )}
                </div>
              )}

              {/* Drawer 3: What if I ignore NiveshPilot? */}
              {whatIfIIgnoreNiveshPilot && (
                <div className="p-4 rounded-xl bg-slate-950/60 border border-white/[0.06]">
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
                  {openDiagnosticDrawer === 'whatIfIgnore' && (
                    <p className="mt-2 text-slate-300 leading-relaxed border-t border-white/[0.04] pt-2">
                      {whatIfIIgnoreNiveshPilot}
                    </p>
                  )}
                </div>
              )}

              {/* Drawer 4: Invalidation Rules */}
              <div className="p-4 rounded-xl bg-slate-950/60 border border-white/[0.06]">
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
                {openDiagnosticDrawer === 'invalidation' && (
                  <div className="mt-2 text-slate-300 space-y-1.5 border-t border-white/[0.04] pt-2">
                    {invalidationConditions.map((cond, i) => (
                      <div key={i} className="flex items-start space-x-2">
                        <span className="text-cyan-400 font-bold">•</span>
                        <span>{cond}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
