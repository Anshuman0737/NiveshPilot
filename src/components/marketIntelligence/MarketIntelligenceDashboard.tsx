import React, { useState, useEffect } from 'react'
import {
  AssetMetadata,
  AssetClass,
  ForecastHorizon,
  DirectionalForecast,
  EventObservation,
  AssetPricePoint
} from '../../engine/marketIntelligence/types'
import {
  loadAssetsMetadata,
  loadHistoricalPrices,
  fetchLiveAssetQuote,
  LiveMarketQuote
} from '../../engine/marketIntelligence/providers/MarketDataProvider'
import { fetchLiveNewsEvents } from '../../engine/marketIntelligence/providers/NewsEventProvider'
import { computeDirectionalForecast } from '../../engine/marketIntelligence/forecastEngine'
import { evaluateAssetSuitability } from '../../engine/marketIntelligence/suitabilityBridge'
import { SuitabilityProfile } from '../../engine/types'

// Terminal Components
import { MarketIntelSidebar } from './MarketIntelSidebar'
import { MarketIntelHeader } from './MarketIntelHeader'
import { MarketStateStrip } from './MarketStateStrip'
import { MarketRegimeModule } from './MarketRegimeModule'
import { EmergingSignalsSection } from './EmergingSignalsSection'
import { EventCascadeSection } from './EventCascadeSection'
import { AnomalySignalsTable } from './AnomalySignalsTable'
import { AssetDiagnosticView } from './AssetDiagnosticView'
import { ExplainForecastModal } from './ExplainForecastModal'
import { ProviderHealthModal } from './ProviderHealthModal'

interface MarketIntelligenceDashboardProps {
  userProfile?: SuitabilityProfile
  initialSymbol?: string
  onNavigateTab?: (tab: string) => void
  onExitToAdvisor?: () => void
}

export const MarketIntelligenceDashboard: React.FC<MarketIntelligenceDashboardProps> = ({
  userProfile = {
    amount: 50000,
    horizon: '5-10Y',
    goal: 'Wealth creation',
    riskCapacity: 'High',
    riskReaction: 'Hold confidently',
    hasEmergencyCushion: true,
    alreadyInvests: true
  },
  initialSymbol = 'RELIANCE.NS',
  onNavigateTab,
  onExitToAdvisor
}) => {
  // Navigation & View Mode
  const [viewMode, setViewMode] = useState<'overview' | 'diagnostic'>('overview')
  const [currentSidebarPath, setCurrentSidebarPath] = useState<string>('overview')
  const [isMobileNavOpen, setIsMobileNavOpen] = useState<boolean>(false)

  // Filters & State
  const [assets, setAssets] = useState<AssetMetadata[]>([])
  const [selectedSymbol, setSelectedSymbol] = useState<string>(initialSymbol)
  const [selectedClass, setSelectedClass] = useState<AssetClass | 'all'>('all')
  const [searchQuery, setSearchQuery] = useState<string>('')
  const [activeHorizon, setActiveHorizon] = useState<ForecastHorizon>('5D')
  const [marketRegion, setMarketRegion] = useState<'IN' | 'US'>('IN')

  // Modals
  const [isExplainModalOpen, setIsExplainModalOpen] = useState<boolean>(false)
  const [isHealthModalOpen, setIsHealthModalOpen] = useState<boolean>(false)

  // Live Data State
  const [quote, setQuote] = useState<LiveMarketQuote | null>(null)
  const [events, setEvents] = useState<EventObservation[]>([])
  const [, setPrices] = useState<AssetPricePoint[]>([])
  const [forecast, setForecast] = useState<DirectionalForecast | null>(null)

  // 1. Initial assets universe load
  useEffect(() => {
    loadAssetsMetadata().then((data) => {
      if (data && data.length > 0) {
        setAssets(data)
        if (!data.some((a) => a.symbol === selectedSymbol)) {
          setSelectedSymbol(data[0].symbol)
        }
      }
    })
  }, [])

  const selectedAsset = assets.find((a) => a.symbol === selectedSymbol) || assets[0] || {
    symbol: 'RELIANCE.NS',
    name: 'Reliance Industries Ltd.',
    asset_class: 'equity' as AssetClass,
    sector: 'Energy & Retail',
    currency: 'INR',
    isin: 'INE002A01018',
    lookback_years: 5
  }

  // 2. Fetch live quote, events, history, and calculate forecast
  useEffect(() => {
    if (!selectedAsset) return

    let isMounted = true

    const syncData = async () => {
      try {
        const [q, evts, hist] = await Promise.all([
          fetchLiveAssetQuote(selectedAsset),
          fetchLiveNewsEvents(selectedAsset.symbol, selectedAsset.name),
          loadHistoricalPrices(selectedAsset.symbol)
        ])

        if (!isMounted) return

        setQuote(q)
        setEvents(evts)
        setPrices(hist)

        const fc = await computeDirectionalForecast(selectedAsset, activeHorizon, evts)
        if (isMounted) {
          setForecast(fc)
        }
      } catch (err) {
        console.warn('Market intelligence sync caught error:', err)
      }
    }

    syncData()

    return () => {
      isMounted = false
    }
  }, [selectedSymbol, activeHorizon, selectedAsset])

  // Filtered asset list based on search or class filter
  const filteredAssets = assets.filter((a) => {
    const matchClass = selectedClass === 'all' || a.asset_class === selectedClass
    const matchSearch =
      a.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      a.symbol.toLowerCase().includes(searchQuery.toLowerCase()) ||
      a.sector.toLowerCase().includes(searchQuery.toLowerCase())
    return matchClass && matchSearch
  })

  // Handle Sidebar Navigation
  const handleSidebarNavigate = (path: string) => {
    setCurrentSidebarPath(path)
    if (path === 'overview') {
      setViewMode('overview')
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } else if (path === 'predictions') {
      setViewMode('diagnostic')
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } else if (path === 'events') {
      setViewMode('overview')
      setTimeout(() => {
        const el = document.getElementById('event-cascade-section')
        if (el) el.scrollIntoView({ behavior: 'smooth' })
      }, 100)
    } else if (path === 'stocks') {
      setSelectedClass('equity')
      setViewMode('overview')
    } else if (path === 'mutual-funds') {
      setSelectedClass('mutual_fund')
      setViewMode('overview')
    } else if (path === 'etfs') {
      setSelectedClass('etf')
      setViewMode('overview')
    } else if (path === 'commodities') {
      setSelectedClass('commodity')
      setViewMode('overview')
    } else if (path === 'model-health') {
      setIsHealthModalOpen(true)
    } else if (path === 'home') {
      if (onExitToAdvisor) {
        onExitToAdvisor()
      } else if (onNavigateTab) {
        onNavigateTab('home')
      }
    } else if (path === 'portfolio' && onNavigateTab) {
      onNavigateTab('portfolio')
    } else if (path === 'ihavex' && onNavigateTab) {
      onNavigateTab('ihavex')
    } else if (path === 'wait' && onNavigateTab) {
      onNavigateTab('wait')
    } else if (path === 'sell' && onNavigateTab) {
      onNavigateTab('sell')
    } else if (path === 'compare' && onNavigateTab) {
      onNavigateTab('compare')
    } else if (path === 'research' && onNavigateTab) {
      onNavigateTab('research')
    }
  }

  const handleInspectAsset = (symbol: string) => {
    setSelectedSymbol(symbol)
    setViewMode('diagnostic')
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const suitability = selectedAsset
    ? evaluateAssetSuitability(selectedAsset, forecast, userProfile)
    : null

  return (
    <div className="min-h-screen bg-background text-on-surface font-body-default text-body-default antialiased selection:bg-tertiary/20 selection:text-tertiary">
      {/* 1. Left Sidebar Navigation (Desktop Fixed + Mobile Slide-over) */}
      <MarketIntelSidebar
        isOpen={isMobileNavOpen}
        onClose={() => setIsMobileNavOpen(false)}
        currentPath={currentSidebarPath}
        onNavigate={handleSidebarNavigate}
      />

      {/* 2. Top Institutional Header */}
      <MarketIntelHeader
        onToggleMobileNav={() => setIsMobileNavOpen(!isMobileNavOpen)}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        selectedClass={selectedClass}
        onSelectClass={(cls) => {
          setSelectedClass(cls)
          if (viewMode === 'diagnostic') setViewMode('overview')
        }}
        marketRegion={marketRegion}
        onToggleRegion={setMarketRegion}
        onExplainForecast={() => setIsExplainModalOpen(true)}
        onExitToAdvisor={onExitToAdvisor || (() => onNavigateTab?.('home'))}
      />

      {/* 3. Main Workspace Area */}
      <div className="xl:pl-64 transition-all duration-300">
        <main className="w-full pt-14 px-2 sm:px-space-base pb-space-xl">
          <div className="flex flex-col w-full text-on-surface">
            {/* Top Global Alert / System Broadcast */}
            <div className="w-full bg-surface-container-lowest px-space-sm sm:px-space-md py-1.5 flex flex-col sm:flex-row sm:items-center justify-between gap-1 text-on-surface-variant font-label-caps text-label-caps mb-space-sm shadow-sm rounded">
              <div className="flex flex-wrap items-center gap-space-xs sm:gap-space-sm">
                <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-tertiary/20 text-tertiary font-data-mono-compact text-data-mono-compact uppercase">
                  System Broadcast
                </span>
                <span className="text-on-surface">
                  Markov Ensemble v4.8: Live calibration complete across 2,400+ equity vectors. Macro regime delta synchronized at 14:20 IST.
                </span>
              </div>
              <div className="flex items-center gap-2 sm:gap-space-md shrink-0">
                <span className="text-secondary font-data-mono-compact text-data-mono-compact">
                  LATENCY: 18ms
                </span>
                <span className="text-outline">·</span>
                <span className="text-on-surface-variant">NEXT RUN: 14:30 IST</span>
              </div>
            </div>

            {/* Suitability Caution Alert (If Emergency Fund < 6M or Short Horizon) */}
            {suitability && !suitability.isPermittedBySuitability && (
              <div className="mb-space-sm p-space-sm rounded bg-error-container/20 border border-error/40 flex items-start gap-2 text-error">
                <span className="material-symbols-outlined text-[18px] shrink-0 mt-0.5">
                  shield_with_heart
                </span>
                <div className="font-body-compact text-body-compact">
                  <strong>Suitability Safety Gate Active:</strong> {suitability.message} Market forecasts remain educational and will not override emergency liquidity needs.
                </div>
              </div>
            )}

            {/* VIEW MODE ROUTING */}
            {viewMode === 'overview' ? (
              <>
                {/* Page Header Area */}
                <div className="flex flex-col md:flex-row md:items-end justify-between px-space-sm sm:px-space-md py-space-sm mb-space-sm bg-surface-container-low rounded">
                  <div className="flex flex-col gap-0.5">
                    <div className="flex items-center gap-space-xs">
                      <span className="material-symbols-outlined text-secondary text-[18px]">
                        query_stats
                      </span>
                      <span className="font-label-caps text-label-caps text-secondary uppercase tracking-widest">
                        Autonomous Quant Intel Engine
                      </span>
                    </div>
                    <h1 className="font-headline-xl text-headline-xl text-on-surface tracking-tight">
                      Market Intelligence
                    </h1>
                    <p className="font-body-default text-body-default text-on-surface-variant">
                      Real-time market state, emerging events and probabilistic directional forecasts across Indian &amp; Global asset classes.
                    </p>
                  </div>

                  <div className="mt-space-sm md:mt-0 flex flex-wrap items-center gap-space-xs font-data-mono-compact text-data-mono-compact">
                    <div className="bg-surface-container px-space-sm py-1 rounded flex items-center gap-space-xs">
                      <span className="text-on-surface-variant">SIGNAL HORIZON:</span>
                      <span className="text-primary font-semibold">T+5 TRADING SESSIONS</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => setIsExplainModalOpen(true)}
                      className="bg-primary hover:bg-primary-container text-on-primary hover:text-on-primary-container px-space-sm py-1 rounded font-body-compact text-body-compact font-semibold transition-all flex items-center gap-1 shadow-sm"
                    >
                      <span className="material-symbols-outlined text-[14px]">tune</span>
                      <span>Filter Parameters</span>
                    </button>
                  </div>
                </div>

                {/* 1. COMPACT MARKET-STATE STRIP (7 live assets) */}
                <MarketStateStrip onSelectAsset={handleInspectAsset} />

                {/* 2. MARKET REGIME ANALYSIS MODULE */}
                <MarketRegimeModule />

                {/* 3. EMERGING QUANTITATIVE SIGNALS (3 Institutional Cards) */}
                <EmergingSignalsSection onInspectAsset={handleInspectAsset} />

                {/* 4. WHAT CHANGED TODAY (Sequential Cascade & Asset Correlation Pulse) */}
                <EventCascadeSection onInspectAsset={handleInspectAsset} />

                {/* 5. LIVE MARKET-WIDE ANOMALY SIGNALS (Dense Table) */}
                <AnomalySignalsTable onInspectAsset={handleInspectAsset} />

                {/* Institutional Notice Footer */}
                <div className="p-space-sm bg-surface-container-lowest text-on-surface-variant font-body-compact text-body-compact flex items-start gap-2 shadow-sm rounded">
                  <span className="material-symbols-outlined text-outline text-[16px] mt-0.5 shrink-0">
                    info
                  </span>
                  <p className="flex-1 leading-normal">
                    <strong>Institutional Notice:</strong> Probabilistic forecasts represent quantitative model estimations and historical backtested distributions. They do not constitute investment advice or guarantees of market performance. Real-time inference pipelines process data through stochastic filtering and causal graph models subject to model drift and liquidity constraints.
                  </p>
                </div>
              </>
            ) : (
              /* ASSET INTELLIGENCE DEEP-DIVE (BENTO VIEW) */
              <AssetDiagnosticView
                asset={selectedAsset}
                quote={quote}
                forecast={forecast}
                events={events}
                activeHorizon={activeHorizon}
                onChangeHorizon={setActiveHorizon}
                onBackToOverview={() => {
                  setViewMode('overview')
                  window.scrollTo({ top: 0, behavior: 'smooth' })
                }}
                allAssets={filteredAssets}
                onSelectAsset={(sym) => setSelectedSymbol(sym)}
              />
            )}
          </div>
        </main>
      </div>

      {/* Explain Forecast Modal */}
      <ExplainForecastModal
        isOpen={isExplainModalOpen}
        onClose={() => setIsExplainModalOpen(false)}
        asset={selectedAsset}
        forecast={forecast}
      />

      {/* Provider Health Modal */}
      <ProviderHealthModal
        isOpen={isHealthModalOpen}
        onClose={() => setIsHealthModalOpen(false)}
      />
    </div>
  )
}
