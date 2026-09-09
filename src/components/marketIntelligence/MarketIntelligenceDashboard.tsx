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
import { computeDataQualityScore } from '../../engine/marketIntelligence/providers/ProviderManager'
import { evaluateAssetSuitability } from '../../engine/marketIntelligence/suitabilityBridge'
import { SuitabilityProfile } from '../../engine/types'
import { AssetHeaderCard } from './AssetHeaderCard'
import { ProbabilisticForecastCard } from './ProbabilisticForecastCard'
import { PriceForecastChart } from './PriceForecastChart'
import { EventTimelineView } from './EventTimelineView'
import { ModelDisagreementCard } from './ModelDisagreementCard'
import { TopDriversCard } from './TopDriversCard'
import { HistoricalPerformanceCard } from './HistoricalPerformanceCard'
import { PredictionTrackRecordCard } from './PredictionTrackRecordCard'
import { ProviderHealthModal } from './ProviderHealthModal'
import {
  Search,
  Filter,
  ShieldCheck,
  AlertTriangle,
  Compass,
  Layers,
  Sparkles,
  TrendingUp,
  Activity
} from 'lucide-react'

interface MarketIntelligenceDashboardProps {
  userProfile?: SuitabilityProfile
  initialSymbol?: string
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
  initialSymbol = 'RELIANCE.NS'
}) => {
  const [assets, setAssets] = useState<AssetMetadata[]>([])
  const [selectedSymbol, setSelectedSymbol] = useState<string>(initialSymbol)
  const [selectedClass, setSelectedClass] = useState<AssetClass | 'all'>('all')
  const [searchQuery, setSearchQuery] = useState<string>('')
  const [activeHorizon, setActiveHorizon] = useState<ForecastHorizon>('5D')

  // Live state
  const [quote, setQuote] = useState<LiveMarketQuote | null>(null)
  const [events, setEvents] = useState<EventObservation[]>([])
  const [prices, setPrices] = useState<AssetPricePoint[]>([])
  const [forecast, setForecast] = useState<DirectionalForecast | null>(null)
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [isHealthOpen, setIsHealthOpen] = useState<boolean>(false)

  // 1. Initial assets metadata load
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

  const selectedAsset = assets.find((a) => a.symbol === selectedSymbol) || assets[0]

  // 2. Fetch live quote, events, prices, and compute forecast
  useEffect(() => {
    if (!selectedAsset) return

    let isMounted = true
    setIsLoading(true)

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
          setIsLoading(false)
        }
      } catch (err) {
        console.warn('Sync market intelligence caught error:', err)
        if (isMounted) setIsLoading(false)
      }
    }

    syncData()

    return () => {
      isMounted = false
    }
  }, [selectedSymbol, activeHorizon, assets])

  // Filtered asset list
  const filteredAssets = assets.filter((a) => {
    const matchClass = selectedClass === 'all' || a.asset_class === selectedClass
    const matchSearch =
      a.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      a.symbol.toLowerCase().includes(searchQuery.toLowerCase()) ||
      a.sector.toLowerCase().includes(searchQuery.toLowerCase())
    return matchClass && matchSearch
  })

  const suitability = selectedAsset
    ? evaluateAssetSuitability(selectedAsset, forecast, userProfile)
    : null

  const dataQualityScore = computeDataQualityScore(
    quote?.freshness || 'HISTORICAL',
    events.length,
    !!quote && quote.price > 0
  )

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8 animate-fade-in">
      {/* Dashboard Top Title Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2">
            <span className="text-xs uppercase font-bold tracking-widest text-emerald-400 px-2.5 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20">
              Dynamic Market Intelligence
            </span>
            <span className="text-xs text-slate-500 font-mono">P(Return &gt; θ | Market State, Info State)</span>
          </div>
          <h1 className="text-2xl sm:text-4xl font-black text-white tracking-tight mt-1.5">
            Probabilistic Directional Forecasting
          </h1>
          <p className="text-sm text-slate-400 max-w-3xl mt-1 leading-relaxed">
            Multi-horizon directional conviction conditioned on real price structures, normalized corporate/macro events,
            and information surprise reactions. Calibrated with zero lookahead bias.
          </p>
        </div>

        {/* Global Health Trigger */}
        <button
          onClick={() => setIsHealthOpen(true)}
          className="self-start md:self-auto px-4 py-2 rounded-2xl bg-slate-900/90 hover:bg-slate-800 border border-white/[0.08] text-xs font-bold text-slate-300 hover:text-white flex items-center space-x-2 transition-all shadow-lg"
        >
          <Activity className="w-4 h-4 text-emerald-400" />
          <span>Provider Health & Status</span>
        </button>
      </div>

      {/* Asset Class Filter Bar & Asset Selector */}
      <div className="p-4 rounded-3xl bg-slate-900/80 border border-white/[0.06] space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          {/* Asset Class Filter Tabs */}
          <div className="flex flex-wrap items-center gap-1.5 text-xs font-bold">
            {(['all', 'equity', 'etf', 'commodity', 'mutual_fund', 'index'] as const).map((cls) => (
              <button
                key={cls}
                onClick={() => setSelectedClass(cls)}
                className={`px-3 py-1.5 rounded-xl capitalize transition-all ${
                  selectedClass === cls
                    ? 'bg-emerald-500 text-slate-950 font-extrabold shadow-md'
                    : 'bg-white/[0.03] text-slate-400 hover:text-white border border-white/[0.04]'
                }`}
              >
                {cls === 'all' ? 'All Assets' : cls.replace('_', ' ')}
              </button>
            ))}
          </div>

          {/* Search Box */}
          <div className="relative w-full sm:w-64">
            <Search className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search ticker, company or sector..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 rounded-xl bg-slate-950 border border-white/[0.08] text-xs text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500 transition-colors"
            />
          </div>
        </div>

        {/* Horizontal Quick-Pick Asset Chips */}
        <div className="flex items-center space-x-2 overflow-x-auto pb-1 pt-1 no-scrollbar">
          {filteredAssets.map((a) => {
            const isSelected = a.symbol === selectedSymbol
            return (
              <button
                key={a.symbol}
                onClick={() => setSelectedSymbol(a.symbol)}
                className={`px-3 py-1.5 rounded-xl text-xs font-mono font-bold shrink-0 transition-all flex items-center space-x-2 ${
                  isSelected
                    ? 'bg-gradient-to-r from-emerald-500/20 to-teal-500/20 border border-emerald-500/40 text-emerald-300'
                    : 'bg-white/[0.02] hover:bg-white/[0.05] border border-white/[0.04] text-slate-400 hover:text-white'
                }`}
              >
                <span>{a.symbol}</span>
                <span className="text-[10px] font-sans text-slate-500 font-normal">
                  ({a.name.split(' ')[0]})
                </span>
              </button>
            )
          })}
        </div>
      </div>

      {selectedAsset && (
        <div className="space-y-6">
          {/* Asset Header Card */}
          <AssetHeaderCard
            asset={selectedAsset}
            quote={quote}
            dataQualityScore={dataQualityScore}
            onOpenHealth={() => setIsHealthOpen(true)}
          />

          {/* Responsible UX Suitability Banner */}
          {suitability && !suitability.isPermittedBySuitability && (
            <div className="p-4 rounded-2xl bg-amber-500/[0.06] border border-amber-500/30 flex items-start space-x-3 text-xs">
              <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
              <div>
                <span className="font-bold text-amber-300 uppercase tracking-wider text-[11px] block">
                  Suitability Safety Advisory ({suitability.badge})
                </span>
                <p className="text-slate-300 leading-relaxed mt-0.5">{suitability.message}</p>
              </div>
            </div>
          )}

          {/* Probabilistic Forecast Dominant Card */}
          <ProbabilisticForecastCard
            forecast={forecast}
            activeHorizon={activeHorizon}
            onSelectHorizon={setActiveHorizon}
          />

          {/* Interactive Price & Forecast Cone SVG Chart */}
          <PriceForecastChart
            prices={prices}
            forecast={forecast}
            activeHorizon={activeHorizon}
            currency={selectedAsset.currency}
          />

          {/* Two-Column Grid: Evidentiary Drivers & Model Disagreement */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <TopDriversCard
              topBullishDrivers={forecast?.top_bullish_drivers || []}
              topBearishDrivers={forecast?.top_bearish_drivers || []}
            />

            {forecast && <ModelDisagreementCard disagreement={forecast.model_disagreement} />}
          </div>

          {/* Real Chronological Event Timeline */}
          <EventTimelineView events={events} />

          {/* Empirical Walk-Forward Backtesting & Calibration Verification */}
          <HistoricalPerformanceCard />

          {/* Immutable Cryptographic Prediction Track Record */}
          <PredictionTrackRecordCard />
        </div>
      )}

      {/* Provider Health Modal */}
      <ProviderHealthModal isOpen={isHealthOpen} onClose={() => setIsHealthOpen(false)} />
    </div>
  )
}
