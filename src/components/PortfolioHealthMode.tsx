import React, { useState } from 'react'
import { Holding, FundSnapshot } from '../engine/types'
import { analyzePortfolioHealth } from '../engine/portfolio'
import { Layers, AlertTriangle, ShieldCheck, Plus, Trash2, CheckCircle2, Info, PieChart } from 'lucide-react'

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
  const [showAddModal, setShowAddModal] = useState(false)
  const [newFundId, setNewFundId] = useState(funds[0]?.internal_id || 'MIRAE_LARGE')
  const [newInvested, setNewInvested] = useState(25000)

  const health = analyzePortfolioHealth(holdings)

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
      currentValue: newInvested // assume at par for newly added
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
      // Intentionally overlapping portfolio to demonstrate warning
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
          fundName: 'ICICI Prudential Equity & Debt',
          category: 'Aggressive Hybrid Fund',
          investedAmount: 50000,
          currentValue: 54000
        }
      ])
    }
  }

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
      {/* Header */}
      <div className="text-center max-w-2xl mx-auto mb-8">
        <div className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-xs font-semibold uppercase tracking-wider mb-3">
          <Layers className="w-3.5 h-3.5" />
          <span>Portfolio Health & Overlap Diagnostic</span>
        </div>
        <h2 className="text-3xl font-extrabold text-white tracking-tight mb-2">
          "Is My Portfolio Truly Diversified?"
        </h2>
        <p className="text-sm text-slate-400">
          Owning 7 different equity funds does NOT automatically make you 7x diversified.
          Inspect portfolio concentration, asset allocation, and underlying stock duplication.
        </p>
      </div>

      {/* Preset Buttons */}
      <div className="flex flex-wrap items-center justify-center gap-2 mb-6 text-xs">
        <span className="text-slate-500 font-semibold mr-1">Load Demo Portfolio:</span>
        <button
          onClick={() => loadPreset('balanced')}
          className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
        >
          Balanced Core (Large + Flexi + Mid + Liquid)
        </button>
        <button
          onClick={() => loadPreset('overlap_heavy')}
          className="px-3 py-1.5 rounded-lg bg-rose-950/40 hover:bg-rose-900/40 text-rose-300 border border-rose-900/50 transition-colors"
        >
          High Duplication Overlap Sample
        </button>
      </div>

      {/* Summary Scorecard */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3.5 mb-8">
        <div className="p-4 rounded-xl bg-slate-900 border border-slate-800">
          <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Total Value</span>
          <div className="text-2xl font-black text-white mt-0.5">{formatINR(health.totalCurrentValue)}</div>
          <span className="text-xs text-emerald-400 font-bold">+{health.totalGainPct}% return</span>
        </div>

        <div className="p-4 rounded-xl bg-slate-900 border border-slate-800">
          <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Equity Allocation</span>
          <div className="text-2xl font-black text-white mt-0.5">{health.equityExposurePct}%</div>
          <span className="text-xs text-slate-400">Debt / Liquid: {health.debtExposurePct}%</span>
        </div>

        <div className="p-4 rounded-xl bg-slate-900 border border-slate-800">
          <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Active Funds</span>
          <div className="text-2xl font-black text-white mt-0.5">{holdings.length}</div>
          <span className="text-xs text-slate-400">Target: 3 to 5 funds</span>
        </div>

        <div className="p-4 rounded-xl bg-slate-900 border border-slate-800">
          <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Diversification</span>
          <div className={`text-2xl font-black mt-0.5 ${health.diversificationStatus === 'Healthy' ? 'text-emerald-400' : 'text-amber-400'}`}>
            {health.diversificationStatus}
          </div>
          <span className="text-xs text-slate-400">
            {health.highOverlapDetected ? 'High overlap detected' : 'Clean distribution'}
          </span>
        </div>
      </div>

      {/* Overlap & Health Alert Box */}
      <div className="p-5 rounded-2xl bg-gradient-to-r from-slate-900 via-slate-900 to-navy-950 border border-slate-800 shadow-xl mb-8">
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

      {/* Holdings Table & Overlap Inspector */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Holdings List */}
        <div className="lg:col-span-2 p-6 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl">
          <div className="flex items-center justify-between pb-4 mb-4 border-b border-slate-800">
            <div>
              <h3 className="text-lg font-bold text-white">Current Holdings</h3>
              <p className="text-xs text-slate-400">Zero broker password required. Client-side private analysis.</p>
            </div>
            <button
              onClick={() => setShowAddModal(true)}
              className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs flex items-center space-x-1 transition-colors"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Add Fund</span>
            </button>
          </div>

          <div className="space-y-3">
            {holdings.map((h) => (
              <div
                key={h.id}
                className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-between gap-3"
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
            ))}
          </div>
        </div>

        {/* Overlap Matrix & Stock Duplication Box */}
        <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl">
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
                  <div key={idx} className="p-3 rounded-xl bg-slate-950 border border-slate-800 text-xs">
                    <div className="flex items-center justify-between font-bold text-white mb-1">
                      <span className="truncate pr-2">{f1} vs {f2}</span>
                      <span className={`px-2 py-0.5 rounded text-[11px] font-black ${pair.overlapPct >= 50 ? 'bg-rose-500/20 text-rose-300' : 'bg-emerald-500/20 text-emerald-300'}`}>
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
          <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-2xl">
            <h3 className="text-lg font-bold text-white mb-4">Add Mutual Fund Holding</h3>

            <label className="block text-xs font-semibold text-slate-400 mb-1">Select Scheme</label>
            <select
              value={newFundId}
              onChange={(e) => setNewFundId(e.target.value)}
              className="w-full p-2.5 rounded-xl bg-slate-950 border border-slate-700 text-sm text-white mb-4"
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
              className="w-full p-2.5 rounded-xl bg-slate-950 border border-slate-700 text-sm text-white mb-6"
            />

            <div className="flex justify-end space-x-3">
              <button
                onClick={() => setShowAddModal(false)}
                className="px-4 py-2 rounded-lg text-sm text-slate-400 hover:text-white"
              >
                Cancel
              </button>
              <button
                onClick={handleAddHolding}
                className="px-5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-sm"
              >
                Add to Portfolio
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
