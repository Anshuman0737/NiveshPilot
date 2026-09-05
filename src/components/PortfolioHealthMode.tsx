import React, { useState, useEffect } from 'react'
import { Holding, FundSnapshot } from '../engine/types'
import { analyzePortfolioHealth } from '../engine/portfolio'
import { generatePortfolioOptimizationBlueprint } from '../engine/portfolioOptimizer'
import { subscribeToLiveMarket, LiveQuote } from '../engine/liveMarketService'
import { PortfolioImportModal } from './PortfolioImportModal'
import { PortfolioUpgradeCard } from './PortfolioUpgradeCard'
import {
  Layers,
  AlertTriangle,
  ShieldCheck,
  Plus,
  Trash2,
  UploadCloud,
  FileText,
  Sparkles,
  Building2,
  TrendingUp,
  PieChart,
  BarChart2,
  Briefcase
} from 'lucide-react'

interface PortfolioHealthModeProps {
  funds: FundSnapshot[]
}

const DEFAULT_SAMPLE_HOLDINGS: Holding[] = [
  {
    id: 'h1',
    fundId: 'MIRAE_LARGE',
    fundName: 'Mirae Asset Large Cap Fund',
    category: 'Large Cap Fund',
    investedAmount: 50000,
    currentValue: 58400
  },
  {
    id: 'h2',
    fundId: 'PPFAS_FLEXI',
    fundName: 'Parag Parikh Flexi Cap Fund',
    category: 'Flexi Cap Fund',
    investedAmount: 60000,
    currentValue: 74200
  },
  {
    id: 'h3',
    fundId: 'HDFC_MIDCAP',
    fundName: 'HDFC Mid-Cap Opportunities Fund',
    category: 'Mid Cap Fund',
    investedAmount: 30000,
    currentValue: 39500
  },
  {
    id: 'h4',
    fundId: 'SBI_LIQUID',
    fundName: 'SBI Liquid Fund',
    category: 'Liquid Fund',
    investedAmount: 20000,
    currentValue: 21400
  }
]

export const PortfolioHealthMode: React.FC<PortfolioHealthModeProps> = ({ funds }) => {
  const [holdings, setHoldings] = useState<Holding[]>(DEFAULT_SAMPLE_HOLDINGS)
  const [liveQuotes, setLiveQuotes] = useState<LiveQuote[]>([])
  const [showAddModal, setShowAddModal] = useState(false)
  const [showImportModal, setShowImportModal] = useState(false)
  const [newFundId, setNewFundId] = useState(funds[0]?.internal_id || 'MIRAE_LARGE')
  const [newInvested, setNewInvested] = useState(25000)

  useEffect(() => {
    const unsub = subscribeToLiveMarket((quotes) => setLiveQuotes(quotes))
    return () => unsub()
  }, [])

  const health = analyzePortfolioHealth(holdings, liveQuotes)
  const blueprint = generatePortfolioOptimizationBlueprint(holdings, funds)

  const formatINR = (val: number) =>
    new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(val)

  const handleAddHolding = () => {
    const target = funds.find((f) => f.internal_id === newFundId)
    if (!target) return

    const newH: Holding = {
      id: `h_${Date.now()}`,
      fundId: target.internal_id,
      fundName: target.scheme_name.split(' - ')[0],
      category: target.category,
      investedAmount: newInvested,
      currentValue: newInvested
    }
    setHoldings([...holdings, newH])
    setShowAddModal(false)
  }

  const handleRemove = (id: string) => {
    setHoldings(holdings.filter((h) => h.id !== id))
  }

  const loadPreset = (type: 'balanced' | 'overlap_heavy') => {
    if (type === 'balanced') {
      setHoldings(DEFAULT_SAMPLE_HOLDINGS)
    } else {
      setHoldings([
        {
          id: 'o1',
          fundId: 'MIRAE_LARGE',
          fundName: 'Mirae Asset Large Cap Fund',
          category: 'Large Cap Fund',
          investedAmount: 50000,
          currentValue: 56000
        },
        {
          id: 'o2',
          fundId: 'PPFAS_FLEXI',
          fundName: 'Parag Parikh Flexi Cap Fund',
          category: 'Flexi Cap Fund',
          investedAmount: 50000,
          currentValue: 58000
        },
        {
          id: 'o3',
          fundId: 'ICICI_HYBRID',
          fundName: 'ICICI Prudential Large & Mid Cap',
          category: 'Large Cap Fund',
          investedAmount: 50000,
          currentValue: 54000
        }
      ])
    }
  }

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
      {/* Minimal Header */}
      <div className="text-center max-w-2xl mx-auto mb-8">
        <div className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-xs font-semibold uppercase tracking-wider mb-3">
          <Layers className="w-3.5 h-3.5" />
          <span>Portfolio Health & Overlap Diagnostic</span>
        </div>
        <h2 className="text-3xl sm:text-4xl font-black text-white tracking-tight mb-2">
          "Is My Portfolio Truly Diversified?"
        </h2>
        <p className="text-sm text-slate-400">
          Import your CAS statement or screenshots to diagnose stock duplication, eliminate distributor fee drag, and generate an upgraded institutional portfolio.
        </p>
      </div>

      {/* Action Bar: Import Trigger + Presets */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-3.5 rounded-2xl glass-panel mb-8">
        <button
          onClick={() => setShowImportModal(true)}
          className="px-5 py-2.5 rounded-full bg-emerald-500 hover:bg-emerald-400 text-navy-950 font-extrabold text-xs sm:text-sm flex items-center space-x-2 shadow-lg shadow-emerald-500/20 hover:scale-[1.02] transition-all"
        >
          <UploadCloud className="w-4 h-4 text-navy-950" />
          <span>Import Investments (PDF / Screenshot / Text)</span>
        </button>

        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="text-slate-500 font-medium hidden sm:inline">Load Sample:</span>
          <button
            onClick={() => loadPreset('balanced')}
            className="px-3 py-1.5 rounded-full bg-slate-900/60 hover:bg-slate-800 text-slate-300 border border-white/[0.06] transition-colors"
          >
            Balanced Core
          </button>
          <button
            onClick={() => loadPreset('overlap_heavy')}
            className="px-3 py-1.5 rounded-full bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/30 transition-colors"
          >
            High Overlap Trap
          </button>
        </div>
      </div>

      {/* Summary Scorecard */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3.5 mb-8">
        <div className="p-4 rounded-2xl glass-card">
          <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Total Value</span>
          <div className="text-2xl font-black text-white mt-1">{formatINR(health.totalCurrentValue)}</div>
          <span className="text-xs text-emerald-400 font-bold">+{health.totalGainPct}% return</span>
        </div>

        <div className="p-4 rounded-2xl glass-card">
          <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Equity Allocation</span>
          <div className="text-2xl font-black text-white mt-1">{health.equityExposurePct}%</div>
          <span className="text-xs text-slate-400">Debt / Liquid: {health.debtExposurePct}%</span>
        </div>

        <div className="p-4 rounded-2xl glass-card">
          <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Active Funds</span>
          <div className="text-2xl font-black text-white mt-1">{holdings.length}</div>
          <span className="text-xs text-slate-400">Target: 3 to 5 funds</span>
        </div>

        <div className="p-4 rounded-2xl glass-card">
          <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Diversification</span>
          <div className={`text-2xl font-black mt-1 ${health.diversificationStatus === 'Healthy' ? 'text-emerald-400' : 'text-amber-400'}`}>
            {health.diversificationStatus}
          </div>
          <span className="text-xs text-slate-400">
            {health.highOverlapDetected ? 'High overlap detected' : 'Clean distribution'}
          </span>
        </div>
      </div>

      {/* Overlap & Health Alert Box */}
      <div className="p-5 rounded-2xl glass-panel mb-8 border border-white/[0.06]">
        <div className="flex items-start space-x-3">
          {health.highOverlapDetected ? (
            <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
          ) : (
            <ShieldCheck className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
          )}
          <div>
            <h4 className="font-bold text-white text-base mb-1">
              Portfolio Health Assessment: {health.diversificationStatus}
            </h4>
            <p className="text-sm text-slate-300 leading-relaxed">{health.diversificationAdvice}</p>
          </div>
        </div>
      </div>

      {/* Institutional Portfolio Analyser (ICICI Direct Style & Beyond) */}
      <div className="p-6 rounded-3xl glass-panel mb-8 border border-white/[0.08] relative overflow-hidden">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 mb-6 border-b border-white/[0.06]">
          <div>
            <div className="flex items-center space-x-2 mb-1">
              <Building2 className="w-4 h-4 text-emerald-400" />
              <span className="text-[11px] font-bold uppercase tracking-wider text-emerald-400">
                Institutional Portfolio Analyser
              </span>
              <span className="text-[9px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-300 font-bold border border-emerald-500/20">
                ICICI Direct Style + Live Real-Time Feeds
              </span>
            </div>
            <h3 className="text-xl font-black text-white">Market-Cap, Sector & Underlying Stock Exposure</h3>
          </div>
          <div className="text-xs text-slate-400">
            Aggregated across <strong className="text-white">{holdings.length}</strong> mutual funds
          </div>
        </div>

        {/* 1. Market Cap Bifurcation (ICICI Direct feature) */}
        <div className="mb-6 p-4 rounded-2xl bg-slate-950/60 border border-white/[0.05]">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-300">
              Market Capitalization Bifurcation
            </span>
            <span className="text-[11px] text-slate-400">SEBI Classification</span>
          </div>

          {/* Segmented Visual Stack Bar */}
          <div className="w-full h-3 bg-slate-800 rounded-full overflow-hidden flex mb-3">
            <div
              style={{ width: `${health.marketCapBifurcation.largeCapPct}%` }}
              className="bg-emerald-500 h-full transition-all"
              title={`Large Cap: ${health.marketCapBifurcation.largeCapPct}%`}
            />
            <div
              style={{ width: `${health.marketCapBifurcation.midCapPct}%` }}
              className="bg-teal-400 h-full transition-all"
              title={`Mid Cap: ${health.marketCapBifurcation.midCapPct}%`}
            />
            <div
              style={{ width: `${health.marketCapBifurcation.smallCapPct}%` }}
              className="bg-cyan-400 h-full transition-all"
              title={`Small Cap: ${health.marketCapBifurcation.smallCapPct}%`}
            />
            <div
              style={{ width: `${health.marketCapBifurcation.debtPct}%` }}
              className="bg-indigo-400 h-full transition-all"
              title={`Debt / Liquid: ${health.marketCapBifurcation.debtPct}%`}
            />
          </div>

          {/* Legend Chips */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
            <div className="p-2 rounded-xl bg-white/[0.02] border border-white/[0.04]">
              <div className="flex items-center space-x-1.5 mb-1">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 shrink-0" />
                <span className="font-semibold text-slate-300">Giant / Large Cap</span>
              </div>
              <div className="text-lg font-black text-emerald-400">{health.marketCapBifurcation.largeCapPct}%</div>
              <div className="text-[10px] text-slate-500">Top 100 Bluechip Indian Companies</div>
            </div>

            <div className="p-2 rounded-xl bg-white/[0.02] border border-white/[0.04]">
              <div className="flex items-center space-x-1.5 mb-1">
                <span className="w-2.5 h-2.5 rounded-full bg-teal-400 shrink-0" />
                <span className="font-semibold text-slate-300">Mid Cap</span>
              </div>
              <div className="text-lg font-black text-teal-400">{health.marketCapBifurcation.midCapPct}%</div>
              <div className="text-[10px] text-slate-500">101st - 250th Growth Equities</div>
            </div>

            <div className="p-2 rounded-xl bg-white/[0.02] border border-white/[0.04]">
              <div className="flex items-center space-x-1.5 mb-1">
                <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 shrink-0" />
                <span className="font-semibold text-slate-300">Small Cap</span>
              </div>
              <div className="text-lg font-black text-cyan-400">{health.marketCapBifurcation.smallCapPct}%</div>
              <div className="text-[10px] text-slate-500">251st+ High-Beta Opportunities</div>
            </div>

            <div className="p-2 rounded-xl bg-white/[0.02] border border-white/[0.04]">
              <div className="flex items-center space-x-1.5 mb-1">
                <span className="w-2.5 h-2.5 rounded-full bg-indigo-400 shrink-0" />
                <span className="font-semibold text-slate-300">Debt / Liquid</span>
              </div>
              <div className="text-lg font-black text-indigo-400">{health.marketCapBifurcation.debtPct}%</div>
              <div className="text-[10px] text-slate-500">T-Bills, Cash & Sovereigns</div>
            </div>
          </div>
        </div>

        {/* 2. Top Consolidated Stocks (ICICI Direct feature) */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Left: Top 10 Consolidated Equities */}
          <div className="p-4 rounded-2xl bg-slate-950/60 border border-white/[0.05]">
            <div className="flex items-center justify-between mb-3 pb-2 border-b border-white/[0.04]">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-300">
                Top Consolidated Equities
              </span>
              <span className="text-[10px] text-slate-500">Actual Company Exposure</span>
            </div>

            {health.consolidatedStocks.length === 0 ? (
              <div className="text-xs text-slate-500 py-4 text-center">Add funds to view underlying stock breakdown.</div>
            ) : (
              <div className="space-y-2">
                {health.consolidatedStocks.map((stock, i) => (
                  <div
                    key={stock.symbol}
                    className="p-2.5 rounded-xl bg-white/[0.02] hover:bg-white/[0.04] border border-white/[0.04] flex items-center justify-between gap-3 text-xs transition-colors"
                  >
                    <div className="flex items-center space-x-2 min-w-0">
                      <span className="text-[10px] font-mono text-slate-500 w-4">#{i + 1}</span>
                      <div className="truncate">
                        <div className="font-bold text-white truncate flex items-center space-x-1.5">
                          <span>{stock.name}</span>
                          <span className="text-[10px] font-normal text-slate-500">({stock.symbol})</span>
                        </div>
                        <div className="text-[10px] text-slate-400 flex items-center space-x-2">
                          <span>{stock.sector}</span>
                          <span>•</span>
                          <span className="text-emerald-400/80">Held in {stock.heldByFunds.length} fund{stock.heldByFunds.length > 1 ? 's' : ''}</span>
                        </div>
                      </div>
                    </div>

                    <div className="text-right shrink-0">
                      <div className="font-black text-white">{stock.totalWeightPct}%</div>
                      <div className="text-[10px] text-slate-400">{formatINR(stock.totalValue)}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Right: Consolidated Sector Allocation */}
          <div className="p-4 rounded-2xl bg-slate-950/60 border border-white/[0.05]">
            <div className="flex items-center justify-between mb-3 pb-2 border-b border-white/[0.04]">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-300">
                Sector Allocation Breakdown
              </span>
              <span className="text-[10px] text-slate-500">Portfolio Weight</span>
            </div>

            {health.consolidatedSectors.length === 0 ? (
              <div className="text-xs text-slate-500 py-4 text-center">No sector data available.</div>
            ) : (
              <div className="space-y-2.5">
                {health.consolidatedSectors.map((sec) => (
                  <div key={sec.sector} className="space-y-1">
                    <div className="flex justify-between text-xs">
                      <span className="font-semibold text-slate-300">{sec.sector}</span>
                      <div className="space-x-2 text-right">
                        <span className="font-bold text-white">{sec.weightPct}%</span>
                        <span className="text-[10px] text-slate-500">({formatINR(sec.value)})</span>
                      </div>
                    </div>
                    <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
                      <div
                        style={{ width: `${Math.min(100, sec.weightPct * 2.5)}%` }}
                        className="h-full bg-gradient-to-r from-emerald-500 to-teal-400 rounded-full"
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Real-time Portfolio Upgrade Blueprint Component */}
      {holdings.length > 0 && (
        <PortfolioUpgradeCard
          blueprint={blueprint}
          onApplyUpgrade={(upgraded) => setHoldings(upgraded)}
        />
      )}

      {/* Holdings Table & Overlap Inspector */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Holdings List */}
        <div className="lg:col-span-2 p-6 rounded-3xl glass-panel">
          <div className="flex items-center justify-between pb-4 mb-4 border-b border-white/[0.06]">
            <div>
              <h3 className="text-lg font-bold text-white">Current Holdings</h3>
              <p className="text-xs text-slate-400">Zero broker password required. Client-side private analysis.</p>
            </div>
            <div className="flex items-center space-x-2">
              <button
                onClick={() => setShowImportModal(true)}
                className="px-3 py-1.5 rounded-full bg-indigo-500/15 hover:bg-indigo-500/25 text-indigo-300 border border-indigo-500/30 font-semibold text-xs flex items-center space-x-1 transition-colors"
                title="Import CAS statement or screenshot"
              >
                <FileText className="w-3.5 h-3.5" />
                <span>Import</span>
              </button>
              <button
                onClick={() => setShowAddModal(true)}
                className="px-3.5 py-1.5 rounded-full bg-emerald-500 hover:bg-emerald-400 text-navy-950 font-bold text-xs flex items-center space-x-1 transition-colors"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Add Fund</span>
              </button>
            </div>
          </div>

          <div className="space-y-3">
            {holdings.length === 0 ? (
              <div className="text-center py-8 text-slate-500 text-xs">
                No funds in portfolio. Click "Import Investments" or "Add Fund" to start.
              </div>
            ) : (
              holdings.map((h) => (
                <div
                  key={h.id}
                  className="p-3.5 rounded-2xl bg-slate-950/60 border border-white/[0.05] flex items-center justify-between gap-3"
                >
                  <div>
                    <div className="font-bold text-sm text-white">{h.fundName}</div>
                    <div className="text-xs text-slate-400">{h.category}</div>
                  </div>
                  <div className="flex items-center space-x-4 text-right">
                    <div>
                      <div className="text-sm font-bold text-white">{formatINR(h.currentValue)}</div>
                      <div className="text-[11px] text-slate-400">Invested: {formatINR(h.investedAmount)}</div>
                    </div>
                    <button
                      onClick={() => handleRemove(h.id)}
                      className="p-1 text-slate-500 hover:text-rose-400 transition-colors"
                      title="Remove fund"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Overlap Matrix & Stock Duplication Box */}
        <div className="p-6 rounded-3xl glass-panel">
          <h3 className="text-lg font-bold text-white mb-1">Stock Overlap Inspector</h3>
          <p className="text-xs text-slate-400 mb-4">
            Common underlying holdings shared across your active funds.
          </p>

          {health.overlapPairs.length === 0 ? (
            <div className="text-xs text-slate-500 italic">Add 2 or more funds to compare overlap.</div>
          ) : (
            <div className="space-y-3">
              {health.overlapPairs.map((pair, idx) => {
                const f1 = funds.find((f) => f.internal_id === pair.fund1)?.scheme_name.split(' - ')[0] || pair.fund1
                const f2 = funds.find((f) => f.internal_id === pair.fund2)?.scheme_name.split(' - ')[0] || pair.fund2
                return (
                  <div key={idx} className="p-3 rounded-2xl bg-slate-950/60 border border-white/[0.05] text-xs">
                    <div className="flex items-center justify-between font-bold text-white mb-1">
                      <span className="truncate pr-2">{f1} vs {f2}</span>
                      <span className={`px-2 py-0.5 rounded-full text-[11px] font-black ${pair.overlapPct >= 50 ? 'bg-rose-500/20 text-rose-300' : 'bg-emerald-500/20 text-emerald-300'}`}>
                        {pair.overlapPct}% Overlap
                      </span>
                    </div>
                    {pair.commonStocks.length > 0 && (
                      <div className="text-[11px] text-slate-400 mb-1">
                        Shared stocks: <strong className="text-slate-300">{pair.commonStocks.slice(0, 4).join(', ')}</strong>
                      </div>
                    )}
                    <p className="text-[11px] text-slate-400 leading-snug">{pair.advice}</p>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>

      {/* Add Fund Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-navy-950/80 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-md glass-panel rounded-3xl p-6 shadow-2xl border border-white/[0.1]">
            <h3 className="text-lg font-bold text-white mb-4">Add Mutual Fund Holding</h3>

            <label className="block text-xs font-semibold text-slate-400 mb-1">Select Scheme</label>
            <select
              value={newFundId}
              onChange={(e) => setNewFundId(e.target.value)}
              className="w-full p-2.5 rounded-xl bg-slate-950 border border-white/[0.08] text-sm text-white mb-4 focus:outline-none focus:border-indigo-500"
            >
              {funds.map((f) => (
                <option key={f.internal_id} value={f.internal_id}>
                  {f.scheme_name.split(' - ')[0]} ({f.category})
                </option>
              ))}
            </select>

            <label className="block text-xs font-semibold text-slate-400 mb-1">Invested Amount (₹)</label>
            <input
              type="number"
              min="1000"
              step="1000"
              value={newInvested}
              onChange={(e) => setNewInvested(Number(e.target.value))}
              className="w-full p-2.5 rounded-xl bg-slate-950 border border-white/[0.08] text-sm text-white mb-6 focus:outline-none focus:border-indigo-500"
            />

            <div className="flex justify-end space-x-3">
              <button
                onClick={() => setShowAddModal(false)}
                className="px-4 py-2 rounded-full text-xs font-semibold text-slate-400 hover:text-white"
              >
                Cancel
              </button>
              <button
                onClick={handleAddHolding}
                className="px-5 py-2 rounded-full bg-emerald-500 hover:bg-emerald-400 text-navy-950 font-bold text-xs"
              >
                Add to Portfolio
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Multi-Modal Import Modal (PDF / Screenshot / Text / Presets) */}
      <PortfolioImportModal
        isOpen={showImportModal}
        onClose={() => setShowImportModal(false)}
        onImport={(importedHoldings) => setHoldings(importedHoldings)}
        knownFunds={funds}
      />
    </div>
  )
}
