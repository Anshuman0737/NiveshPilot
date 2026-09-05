import React, { useState, useEffect } from 'react'
import {
  SuitabilityProfile,
  FundSnapshot,
  PredictionLedgerEntry,
  BacktestFundResult
} from './engine/types'
import {
  fetchFundSnapshots,
  fetchPredictionLedger,
  fetchBacktestResults,
  FALLBACK_SNAPSHOTS,
  FALLBACK_LEDGER,
  FALLBACK_BACKTEST
} from './engine/dataService'
import { computeInvestmentDecision } from './engine/decision'
import { evaluateSuitability } from './engine/suitability'
import { Navbar, ActiveTab } from './components/Navbar'
import { LiveMarketPulse, SimulatedMarketState } from './components/LiveMarketPulse'
import { HeroSection } from './components/HeroSection'
import { OnboardingModal } from './components/OnboardingModal'
import { AISettingsModal } from './components/AISettingsModal'
import { NextMoveCard } from './components/NextMoveCard'
import { IHaveXMode } from './components/IHaveXMode'
import { ShouldIWaitMode } from './components/ShouldIWaitMode'
import { ShouldISellMode } from './components/ShouldISellMode'
import { PortfolioHealthMode } from './components/PortfolioHealthMode'
import { FundComparisonMode } from './components/FundComparisonMode'
import { ResearchDashboard } from './components/ResearchDashboard'
import { DisclaimerFooter } from './components/DisclaimerFooter'
import { ArrowRight, ShieldCheck, Sparkles, Scale, Info } from 'lucide-react'

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<ActiveTab>('home')
  const [advancedMode, setAdvancedMode] = useState<boolean>(false)
  const [isOnboardingOpen, setIsOnboardingOpen] = useState<boolean>(false)
  const [isAISettingsOpen, setIsAISettingsOpen] = useState<boolean>(false)

  // Initial user financial suitability profile
  const [profile, setProfile] = useState<SuitabilityProfile>({
    amount: 10000,
    horizon: '5-10Y',
    goal: 'Wealth creation',
    riskCapacity: 'High',
    riskReaction: 'Hold confidently',
    hasEmergencyCushion: true,
    alreadyInvests: false
  })

  // Data states
  const [funds, setFunds] = useState<FundSnapshot[]>(FALLBACK_SNAPSHOTS)
  const [ledger, setLedger] = useState<PredictionLedgerEntry[]>(FALLBACK_LEDGER)
  const [backtest, setBacktest] = useState<BacktestFundResult>(FALLBACK_BACKTEST)
  const [selectedFundId, setSelectedFundId] = useState<string>('PPFAS_FLEXI')
  const [simulatedState, setSimulatedState] = useState<SimulatedMarketState | null>(null)

  useEffect(() => {
    // Asynchronously fetch fresh data if available
    fetchFundSnapshots().then((res) => {
      if (res && res.length > 0) setFunds(res)
    })
    fetchPredictionLedger().then((res) => {
      if (res && res.length > 0) setLedger(res)
    })
    fetchBacktestResults().then((res) => {
      if (res) setBacktest(res)
    })
  }, [])

  const selectedFund = funds.find((f) => f.internal_id === selectedFundId) || funds[0]

  // Dynamically react if live market shock simulation is active
  const activeFund: FundSnapshot = React.useMemo(() => {
    if (!simulatedState?.isSimulated) return selectedFund
    return {
      ...selectedFund,
      current_drawdown: +(-simulatedState.marketDropPct - 1.4).toFixed(1),
      vol_30d: simulatedState.volatilityPct,
      market_regime: (simulatedState.simulatedRegime.includes('Dislocation')
        ? 'High-volatility'
        : simulatedState.simulatedRegime.includes('High Volatility')
        ? 'High-volatility'
        : simulatedState.simulatedRegime.includes('Correction')
        ? 'Correction'
        : 'Bull') as any
    }
  }, [selectedFund, simulatedState])

  const decision = computeInvestmentDecision(profile, activeFund)
  const suitability = evaluateSuitability(profile)

  return (
    <div className="min-h-screen flex flex-col bg-navy-950 text-slate-100 selection:bg-emerald-500/20 selection:text-emerald-200">
      {/* Top Navbar */}
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        advancedMode={advancedMode}
        setAdvancedMode={setAdvancedMode}
        onOpenOnboarding={() => setIsOnboardingOpen(true)}
        onOpenAISettings={() => setIsAISettingsOpen(true)}
        isSuitableForEquity={suitability.isSuitableForEquity}
      />

      {/* Dynamic Live Market Pulse & Stress Simulator */}
      <LiveMarketPulse onSimulateStateChange={setSimulatedState} />

      {/* Main Content Area */}
      <main className="flex-grow">
        {/* Onboarding Wizard Modal */}
        <OnboardingModal
          isOpen={isOnboardingOpen}
          onClose={() => setIsOnboardingOpen(false)}
          currentProfile={profile}
          onSaveProfile={(newProf) => {
            setProfile(newProf)
            setActiveTab('home')
          }}
        />

        {/* AI Co-Pilot & Model Settings Modal */}
        <AISettingsModal
          isOpen={isAISettingsOpen}
          onClose={() => setIsAISettingsOpen(false)}
        />

        {/* VIEW ROUTING */}
        {activeTab === 'home' && (
          <div>
            {/* Hero Section */}
            <HeroSection
              currentAmount={profile.amount}
              onFindNextMove={() => setIsOnboardingOpen(true)}
              onExploreResearch={() => setAdvancedMode(true)}
              onSelectAmount={(amt) => setProfile((prev) => ({ ...prev, amount: amt }))}
            />

            {/* Dominant Next Move Card Section */}
            <section className="py-8 sm:py-12">
              <NextMoveCard
                evidence={decision}
                fund={selectedFund}
                profile={profile}
                onSelectFund={(f) => setSelectedFundId(f.internal_id)}
                allFunds={funds}
                onModifyProfile={() => setIsOnboardingOpen(true)}
                onOpenAISettings={() => setIsAISettingsOpen(true)}
              />
            </section>

            {/* Quick Action Decision Modes Grid */}
            <section className="max-w-4xl mx-auto px-4 sm:px-6 py-6 border-t border-slate-900">
              <div className="text-center mb-6">
                <span className="text-xs uppercase font-bold tracking-widest text-slate-400">
                  Explore Common Dilemmas
                </span>
                <h3 className="text-xl font-bold text-white mt-1">What else are you wondering?</h3>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                {/* Card 1: I have ₹X */}
                <button
                  onClick={() => setActiveTab('ihavex')}
                  className="p-5 rounded-2xl bg-slate-900/60 hover:bg-slate-900 border border-slate-800 text-left transition-all group"
                >
                  <div className="text-xs uppercase tracking-wider font-semibold text-emerald-400 mb-1">
                    Calculate Deployment
                  </div>
                  <h4 className="font-bold text-white text-base mb-1 group-hover:text-emerald-300 transition-colors">
                    "I Have ₹X to Invest"
                  </h4>
                  <p className="text-xs text-slate-400 leading-relaxed mb-3">
                    Input custom capital and get rupee-level deployment splits.
                  </p>
                  <span className="text-xs font-semibold text-emerald-400 flex items-center space-x-1">
                    <span>Try Calculator</span>
                    <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform" />
                  </span>
                </button>

                {/* Card 2: Should I Wait? */}
                <button
                  onClick={() => setActiveTab('wait')}
                  className="p-5 rounded-2xl bg-slate-900/60 hover:bg-slate-900 border border-slate-800 text-left transition-all group"
                >
                  <div className="text-xs uppercase tracking-wider font-semibold text-amber-400 mb-1">
                    Timing Analysis
                  </div>
                  <h4 className="font-bold text-white text-base mb-1 group-hover:text-amber-300 transition-colors">
                    "Should I Wait for a Dip?"
                  </h4>
                  <p className="text-xs text-slate-400 leading-relaxed mb-3">
                    Compare the expected benefit of waiting against certain cash drag.
                  </p>
                  <span className="text-xs font-semibold text-amber-400 flex items-center space-x-1">
                    <span>Inspect Tradeoff</span>
                    <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform" />
                  </span>
                </button>

                {/* Card 3: Should I Sell? */}
                <button
                  onClick={() => setActiveTab('sell')}
                  className="p-5 rounded-2xl bg-slate-900/60 hover:bg-slate-900 border border-slate-800 text-left transition-all group"
                >
                  <div className="text-xs uppercase tracking-wider font-semibold text-rose-400 mb-1">
                    Panic Prevention
                  </div>
                  <h4 className="font-bold text-white text-base mb-1 group-hover:text-rose-300 transition-colors">
                    "Should I Sell My Fund?"
                  </h4>
                  <p className="text-xs text-slate-400 leading-relaxed mb-3">
                    Diagnose if market drop is normal or if your thesis broke.
                  </p>
                  <span className="text-xs font-semibold text-rose-400 flex items-center space-x-1">
                    <span>Run Diagnostic</span>
                    <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform" />
                  </span>
                </button>
              </div>
            </section>

            {/* Advanced Research Mode Embedded view if toggled on */}
            {advancedMode && (
              <section className="py-8 border-t border-slate-900 bg-navy-950/60">
                <ResearchDashboard ledger={ledger} backtest={backtest} funds={funds} />
              </section>
            )}
          </div>
        )}

        {activeTab === 'ihavex' && (
          <IHaveXMode
            funds={funds}
            currentProfile={profile}
            onSelectFundForHome={(f) => {
              setSelectedFundId(f.internal_id)
              setActiveTab('home')
            }}
          />
        )}

        {activeTab === 'wait' && <ShouldIWaitMode />}

        {activeTab === 'sell' && <ShouldISellMode />}

        {activeTab === 'portfolio' && <PortfolioHealthMode funds={funds} />}

        {activeTab === 'compare' && <FundComparisonMode funds={funds} profile={profile} />}

        {activeTab === 'research' && (
          <ResearchDashboard ledger={ledger} backtest={backtest} funds={funds} />
        )}
      </main>

      {/* Global Disclaimer Footer */}
      <DisclaimerFooter />
    </div>
  )
}
