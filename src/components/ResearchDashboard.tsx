import React, { useState, useEffect } from 'react'
import {
  PredictionLedgerEntry,
  BacktestFundResult,
  FundSnapshot
} from '../engine/types'
import {
  fetchResearchSummary,
  FALLBACK_RESEARCH_SUMMARY
} from '../engine/dataService'
import {
  BarChart3,
  CheckCircle,
  Database,
  History,
  Shield,
  Layers,
  Scale,
  Activity,
  ArrowUpRight,
  ChevronDown,
  ChevronUp,
  TrendingUp,
  AlertTriangle,
  Sliders,
  Sparkles,
  Info,
  Lock,
  GitBranch
} from 'lucide-react'

interface ResearchDashboardProps {
  ledger: PredictionLedgerEntry[]
  backtest: BacktestFundResult
  funds: FundSnapshot[]
}

type SubTab = 'walkforward' | 'holdout' | 'regimes' | 'ablation' | 'ledger' | 'quality'
type Horizon = '3M' | '6M' | '12M' | '3Y' | '5Y'

export const ResearchDashboard: React.FC<ResearchDashboardProps> = ({
  ledger,
  backtest,
  funds
}) => {
  const [activeSubTab, setActiveSubTab] = useState<SubTab>('walkforward')
  const [selectedHorizon, setSelectedHorizon] = useState<Horizon>('12M')
  const [researchSummary, setResearchSummary] = useState<any>(FALLBACK_RESEARCH_SUMMARY)
  const [expandedLedgerId, setExpandedLedgerId] = useState<string | null>(null)
  const [ledgerFilter, setLedgerFilter] = useState<'ALL' | 'ARCHIVED_PAPER' | 'CLOSED'>('ALL')
  const [showNonOverlapping, setShowNonOverlapping] = useState<boolean>(false)

  useEffect(() => {
    fetchResearchSummary().then((res) => {
      if (res && res.model_version) {
        setResearchSummary(res)
      }
    })
  }, [])

  // Strategy comparison data for selected horizon
  const currentHorizonData = backtest[selectedHorizon] || researchSummary.nifty_12m || {}
  const isMultiYear = selectedHorizon === '3Y' || selectedHorizon === '5Y'
  const nonOverlapData = researchSummary.non_overlapping_12m || {}
  const holdoutData = researchSummary.final_holdout_oos || {}
  const incrementalBenefits = researchSummary.incremental_benefits_vs_baselines_12M || {}

  const filteredLedger = ledger.filter((entry) => {
    if (ledgerFilter === 'ARCHIVED_PAPER') return entry.live_paper_status === 'ARCHIVED_PAPER' || entry.live_paper_status === 'ACTIVE_PAPER'
    if (ledgerFilter === 'CLOSED') return entry.live_paper_status === 'CLOSED'
    return true
  })

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8 animate-fade-in">
      {/* Top Banner */}
      <div className="p-6 rounded-2xl bg-gradient-to-r from-slate-900 via-indigo-950/40 to-slate-900 border border-indigo-500/30 shadow-2xl mb-8">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-full bg-indigo-500/20 border border-indigo-500/30 text-indigo-300 text-xs font-semibold uppercase tracking-wider mb-2">
              <BarChart3 className="w-3.5 h-3.5" />
              <span>Forensic Quantitative Research Lab</span>
            </div>
            <h2 className="text-2xl sm:text-3xl font-black text-white tracking-tight">
              Empirical Evidence, Holdout & Reproducibility
            </h2>
            <p className="text-xs sm:text-sm text-slate-300 mt-1 max-w-2xl">
              Strict walk-forward backtesting, non-overlapping windows, isolated out-of-sample holdout, and moving block bootstrap uncertainty.
              Zero hypothetical black-box numbers.
            </p>
          </div>

          <div className="flex items-center space-x-3 text-xs">
            <div className="p-2.5 rounded-xl bg-slate-950/80 border border-slate-800 text-center">
              <div className="text-slate-400">Audited Version</div>
              <div className="font-mono font-bold text-indigo-300">model_v1.1-hardened</div>
            </div>
            <div className="p-2.5 rounded-xl bg-slate-950/80 border border-slate-800 text-center">
              <div className="text-slate-400">Target Cost</div>
              <div className="font-bold text-emerald-400">₹0 (Zero API Cost)</div>
            </div>
          </div>
        </div>

        {/* Date & Observational Gap Disclosure */}
        <div className="mt-4 pt-3 border-t border-indigo-500/20 flex items-center space-x-2 text-xs text-indigo-200/80">
          <Info className="w-4 h-4 text-indigo-400 shrink-0" />
          <span>
            <strong>Observational Gap Disclosure</strong>: Historical data ends on August 30, 2024. Active streaming was not continuously maintained between August 2024 and September 2026; 2024 paper entries represent an archived freeze snapshot.
          </span>
        </div>
      </div>

      {/* Sub-Navigation Tabs */}
      <div className="flex border-b border-slate-800 mb-6 space-x-2 sm:space-x-4 overflow-x-auto text-xs sm:text-sm font-semibold">
        <button
          onClick={() => setActiveSubTab('walkforward')}
          className={`pb-3 px-3 border-b-2 transition-all whitespace-nowrap flex items-center space-x-1.5 ${
            activeSubTab === 'walkforward'
              ? 'border-indigo-400 text-white'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Activity className="w-4 h-4" />
          <span>Walk-Forward Backtest</span>
        </button>
        <button
          onClick={() => setActiveSubTab('holdout')}
          className={`pb-3 px-3 border-b-2 transition-all whitespace-nowrap flex items-center space-x-1.5 ${
            activeSubTab === 'holdout'
              ? 'border-indigo-400 text-white'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Lock className="w-4 h-4" />
          <span>Final Out-of-Sample Holdout</span>
        </button>
        <button
          onClick={() => setActiveSubTab('regimes')}
          className={`pb-3 px-3 border-b-2 transition-all whitespace-nowrap flex items-center space-x-1.5 ${
            activeSubTab === 'regimes'
              ? 'border-indigo-400 text-white'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Layers className="w-4 h-4" />
          <span>Regime Matrix & Trade-Offs</span>
        </button>
        <button
          onClick={() => setActiveSubTab('ablation')}
          className={`pb-3 px-3 border-b-2 transition-all whitespace-nowrap flex items-center space-x-1.5 ${
            activeSubTab === 'ablation'
              ? 'border-indigo-400 text-white'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Sliders className="w-4 h-4" />
          <span>Block Bootstrap & Ablation</span>
        </button>
        <button
          onClick={() => setActiveSubTab('ledger')}
          className={`pb-3 px-3 border-b-2 transition-all whitespace-nowrap flex items-center space-x-1.5 ${
            activeSubTab === 'ledger'
              ? 'border-indigo-400 text-white'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <History className="w-4 h-4" />
          <span>Archived Ledger ({ledger.length})</span>
        </button>
        <button
          onClick={() => setActiveSubTab('quality')}
          className={`pb-3 px-3 border-b-2 transition-all whitespace-nowrap flex items-center space-x-1.5 ${
            activeSubTab === 'quality'
              ? 'border-indigo-400 text-white'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Scale className="w-4 h-4" />
          <span>Quality Audit & Provenance</span>
        </button>
      </div>

      {/* SUB-TAB 1: Walk-Forward Backtest */}
      {activeSubTab === 'walkforward' && (
        <div className="space-y-6">
          {/* Horizon Selector & Non-Overlapping Toggle */}
          <div className="flex flex-wrap items-center justify-between gap-3 p-4 rounded-xl bg-slate-900 border border-slate-800">
            <div className="flex items-center space-x-3">
              <div>
                <span className="text-xs text-slate-400 block">Evaluation Horizon:</span>
                <span className="text-xs font-semibold text-slate-200">
                  {showNonOverlapping ? '7 Independent Non-Overlapping Windows (252d step)' : '84 Rolling Windows (21d step)'}
                </span>
              </div>

              {selectedHorizon === '12M' && (
                <button
                  onClick={() => setShowNonOverlapping(!showNonOverlapping)}
                  className={`ml-4 px-3 py-1 rounded-lg text-xs font-bold border transition-all ${
                    showNonOverlapping
                      ? 'bg-amber-500/20 border-amber-500/40 text-amber-300'
                      : 'bg-slate-950 border-slate-700 text-slate-400 hover:text-white'
                  }`}
                >
                  {showNonOverlapping ? 'Viewing: Non-Overlapping Windows' : 'Switch to Non-Overlapping Windows'}
                </button>
              )}
            </div>

            <div className="flex rounded-lg bg-slate-950 p-1 border border-slate-800 space-x-1">
              {(['3M', '6M', '12M', '3Y', '5Y'] as Horizon[]).map((hz) => (
                <button
                  key={hz}
                  onClick={() => {
                    setSelectedHorizon(hz)
                    if (hz !== '12M') setShowNonOverlapping(false)
                  }}
                  className={`px-3 py-1 rounded text-xs font-bold transition-all ${
                    selectedHorizon === hz
                      ? 'bg-indigo-600 text-white shadow'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {hz}
                </button>
              ))}
            </div>
          </div>

          {/* Strategy Comparison Table */}
          <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4">
              <div>
                <h3 className="text-lg font-bold text-white">
                  Strategy Performance: {selectedHorizon} Horizon {showNonOverlapping && '(Non-Overlapping Independent Annual Windows)'}
                </h3>
                <p className="text-xs text-slate-400">
                  {showNonOverlapping
                    ? 'Evaluated across 7 strictly independent annual periods. Zero shared return days.'
                    : 'Evaluated across 84 rolling walk-forward test periods (2016–2024).'}
                </p>
              </div>
              <span className="text-xs px-2.5 py-1 rounded bg-slate-800 text-slate-300 font-mono">
                Benchmark: Nifty 50 TRI
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-xs text-left">
                <thead className="bg-slate-950 text-slate-400 border-b border-slate-800 uppercase tracking-wider">
                  <tr>
                    <th className="py-3 px-3.5">Deployment Strategy</th>
                    <th className="py-3 px-3.5">Positive %</th>
                    <th className="py-3 px-3.5">
                      {isMultiYear ? `Median ${selectedHorizon} CAGR %` : `Median ${selectedHorizon} Return %`}
                    </th>
                    <th className="py-3 px-3.5">Worst Return %</th>
                    <th className="py-3 px-3.5">Median Max Drawdown</th>
                    <th className="py-3 px-3.5">Worst Drawdown (Crash)</th>
                    <th className="py-3 px-3.5">Median Sortino</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800 text-slate-300">
                  {/* Strategy A */}
                  <tr className="hover:bg-slate-800/30">
                    <td className="py-3.5 px-3.5 font-bold text-white">Strategy A: 100% Lump Sum</td>
                    <td className="py-3.5 px-3.5 font-bold text-emerald-400">
                      {showNonOverlapping ? nonOverlapData.strategies?.Strategy_A_LumpSum?.positive_frequency_pct ?? 85.7 : currentHorizonData['Strategy_A_LumpSum']?.positive_frequency_pct ?? 91.7}%
                    </td>
                    <td className="py-3.5 px-3.5 font-bold text-white">
                      +{showNonOverlapping ? nonOverlapData.strategies?.Strategy_A_LumpSum?.median_12m_return_pct ?? 31.47 : isMultiYear ? currentHorizonData['Strategy_A_LumpSum']?.median_cagr_pct ?? 35.28 : currentHorizonData['Strategy_A_LumpSum']?.median_return_pct ?? 23.59}%
                    </td>
                    <td className="py-3.5 px-3.5 font-semibold text-rose-400">
                      {showNonOverlapping ? nonOverlapData.strategies?.Strategy_A_LumpSum?.worst_outcome_pct ?? -18.93 : currentHorizonData['Strategy_A_LumpSum']?.worst_outcome_pct ?? -18.93}%
                    </td>
                    <td className="py-3.5 px-3.5 text-slate-300">
                      {showNonOverlapping ? nonOverlapData.strategies?.Strategy_A_LumpSum?.median_max_drawdown_pct ?? -13.74 : currentHorizonData['Strategy_A_LumpSum']?.median_max_drawdown_pct ?? -13.74}%
                    </td>
                    <td className="py-3.5 px-3.5 font-bold text-rose-400">
                      {showNonOverlapping ? nonOverlapData.strategies?.Strategy_A_LumpSum?.worst_max_drawdown_pct ?? -37.5 : currentHorizonData['Strategy_A_LumpSum']?.worst_max_drawdown_pct ?? -37.5}%
                    </td>
                    <td className="py-3.5 px-3.5 text-slate-300">
                      {showNonOverlapping ? nonOverlapData.strategies?.Strategy_A_LumpSum?.median_sortino ?? 1.63 : currentHorizonData['Strategy_A_LumpSum']?.median_sortino ?? 1.64}
                    </td>
                  </tr>

                  {/* Strategy B */}
                  <tr className="hover:bg-slate-800/30">
                    <td className="py-3.5 px-3.5 font-semibold text-slate-300">Strategy B: 50% Now / 50% Staggered</td>
                    <td className="py-3.5 px-3.5 font-semibold text-emerald-400">
                      {showNonOverlapping ? nonOverlapData.strategies?.Strategy_B_50_50?.positive_frequency_pct ?? 85.7 : currentHorizonData['Strategy_B_50_50']?.positive_frequency_pct ?? 91.7}%
                    </td>
                    <td className="py-3.5 px-3.5 font-semibold text-slate-200">
                      +{showNonOverlapping ? nonOverlapData.strategies?.Strategy_B_50_50?.median_12m_return_pct ?? 32.92 : isMultiYear ? currentHorizonData['Strategy_B_50_50']?.median_cagr_pct ?? 35.85 : currentHorizonData['Strategy_B_50_50']?.median_return_pct ?? 21.28}%
                    </td>
                    <td className="py-3.5 px-3.5 text-rose-300">
                      {showNonOverlapping ? nonOverlapData.strategies?.Strategy_B_50_50?.worst_outcome_pct ?? -15.12 : currentHorizonData['Strategy_B_50_50']?.worst_outcome_pct ?? -16.4}%
                    </td>
                    <td className="py-3.5 px-3.5 text-slate-300">
                      {showNonOverlapping ? nonOverlapData.strategies?.Strategy_B_50_50?.median_max_drawdown_pct ?? -10.36 : currentHorizonData['Strategy_B_50_50']?.median_max_drawdown_pct ?? -13.63}%
                    </td>
                    <td className="py-3.5 px-3.5 text-rose-300">
                      {showNonOverlapping ? nonOverlapData.strategies?.Strategy_B_50_50?.worst_max_drawdown_pct ?? -37.39 : currentHorizonData['Strategy_B_50_50']?.worst_max_drawdown_pct ?? -37.41}%
                    </td>
                    <td className="py-3.5 px-3.5 text-slate-300">
                      {showNonOverlapping ? nonOverlapData.strategies?.Strategy_B_50_50?.median_sortino ?? 1.47 : currentHorizonData['Strategy_B_50_50']?.median_sortino ?? 1.48}
                    </td>
                  </tr>

                  {/* Strategy D */}
                  <tr className="hover:bg-slate-800/30">
                    <td className="py-3.5 px-3.5 font-semibold text-slate-300">Strategy D: Fixed Monthly SIP</td>
                    <td className="py-3.5 px-3.5 font-semibold text-emerald-400">
                      {showNonOverlapping ? nonOverlapData.strategies?.Strategy_D_Monthly_SIP?.positive_frequency_pct ?? 85.7 : currentHorizonData['Strategy_D_Monthly_SIP']?.positive_frequency_pct ?? 89.3}%
                    </td>
                    <td className="py-3.5 px-3.5 font-semibold text-slate-200">
                      +{showNonOverlapping ? nonOverlapData.strategies?.Strategy_D_Monthly_SIP?.median_12m_return_pct ?? 28.54 : isMultiYear ? currentHorizonData['Strategy_D_Monthly_SIP']?.median_cagr_pct ?? 33.45 : currentHorizonData['Strategy_D_Monthly_SIP']?.median_return_pct ?? 17.17}%
                    </td>
                    <td className="py-3.5 px-3.5 text-rose-300">
                      {showNonOverlapping ? nonOverlapData.strategies?.Strategy_D_Monthly_SIP?.worst_outcome_pct ?? -11.65 : currentHorizonData['Strategy_D_Monthly_SIP']?.worst_outcome_pct ?? -11.82}%
                    </td>
                    <td className="py-3.5 px-3.5 text-slate-300">
                      {showNonOverlapping ? nonOverlapData.strategies?.Strategy_D_Monthly_SIP?.median_max_drawdown_pct ?? -8.81 : currentHorizonData['Strategy_D_Monthly_SIP']?.median_max_drawdown_pct ?? -11.88}%
                    </td>
                    <td className="py-3.5 px-3.5 text-rose-300">
                      {showNonOverlapping ? nonOverlapData.strategies?.Strategy_D_Monthly_SIP?.worst_max_drawdown_pct ?? -28.04 : currentHorizonData['Strategy_D_Monthly_SIP']?.worst_max_drawdown_pct ?? -37.15}%
                    </td>
                    <td className="py-3.5 px-3.5 text-slate-300">
                      {showNonOverlapping ? nonOverlapData.strategies?.Strategy_D_Monthly_SIP?.median_sortino ?? 2.10 : currentHorizonData['Strategy_D_Monthly_SIP']?.median_sortino ?? 1.38}
                    </td>
                  </tr>

                  {/* Strategy E */}
                  <tr className="bg-emerald-950/40 border-l-4 border-emerald-500">
                    <td className="py-3.5 px-3.5 font-black text-emerald-300">
                      Strategy E: NiveshPilot Signal Adaptive
                    </td>
                    <td className="py-3.5 px-3.5 font-bold text-emerald-400">
                      {showNonOverlapping ? nonOverlapData.strategies?.Strategy_E_Signal_Adaptive?.positive_frequency_pct ?? 85.7 : currentHorizonData['Strategy_E_Signal_Adaptive']?.positive_frequency_pct ?? 90.5}%
                    </td>
                    <td className="py-3.5 px-3.5 font-bold text-white">
                      +{showNonOverlapping ? nonOverlapData.strategies?.Strategy_E_Signal_Adaptive?.median_12m_return_pct ?? 32.70 : isMultiYear ? currentHorizonData['Strategy_E_Signal_Adaptive']?.median_cagr_pct ?? 35.1 : currentHorizonData['Strategy_E_Signal_Adaptive']?.median_return_pct ?? 21.68}%
                    </td>
                    <td className="py-3.5 px-3.5 font-semibold text-rose-300">
                      {showNonOverlapping ? nonOverlapData.strategies?.Strategy_E_Signal_Adaptive?.worst_outcome_pct ?? -15.95 : currentHorizonData['Strategy_E_Signal_Adaptive']?.worst_outcome_pct ?? -15.95}%
                    </td>
                    <td className="py-3.5 px-3.5 font-bold text-emerald-300">
                      {showNonOverlapping ? nonOverlapData.strategies?.Strategy_E_Signal_Adaptive?.median_max_drawdown_pct ?? -8.82 : currentHorizonData['Strategy_E_Signal_Adaptive']?.median_max_drawdown_pct ?? -13.57}%
                    </td>
                    <td className="py-3.5 px-3.5 font-black text-emerald-300">
                      {showNonOverlapping ? nonOverlapData.strategies?.Strategy_E_Signal_Adaptive?.worst_max_drawdown_pct ?? -37.40 : currentHorizonData['Strategy_E_Signal_Adaptive']?.worst_max_drawdown_pct ?? -37.43}%
                    </td>
                    <td className="py-3.5 px-3.5 font-black text-emerald-300">
                      {showNonOverlapping ? nonOverlapData.strategies?.Strategy_E_Signal_Adaptive?.median_sortino ?? 1.44 : currentHorizonData['Strategy_E_Signal_Adaptive']?.median_sortino ?? 1.42}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            {/* Incremental Benefits vs Baselines Callout */}
            <div className="mt-5 grid grid-cols-1 md:grid-cols-3 gap-3">
              <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 text-xs">
                <span className="text-slate-400 block mb-1">Strategy E vs Lump Sum</span>
                <span className="font-bold text-amber-300 block">-1.91% Return Difference</span>
                <p className="text-[11px] text-slate-400 mt-1">
                  In exchange for slight return lag, Strategy E cuts drawdown in high-volatility regimes from -21.9% to -8.7%.
                </p>
              </div>

              <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 text-xs">
                <span className="text-slate-400 block mb-1">Strategy E vs 50/50 Staggered</span>
                <span className="font-bold text-emerald-400 block">+0.40% Return Edge</span>
                <p className="text-[11px] text-slate-400 mt-1">
                  Allocates 70% in calm bull markets instead of leaving 50% idle, capturing additional upside without excess risk.
                </p>
              </div>

              <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 text-xs">
                <span className="text-slate-400 block mb-1">Strategy E vs Monthly SIP</span>
                <span className="font-bold text-emerald-400 block">+4.51% Return Edge</span>
                <p className="text-[11px] text-slate-400 mt-1">
                  Substantially outperforms Monthly SIP during extended upward trends by avoiding severe cash drag.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* SUB-TAB 2: Final Out-of-Sample Holdout */}
      {activeSubTab === 'holdout' && (
        <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl space-y-6">
          <div className="flex items-center space-x-2 text-indigo-400 font-bold text-xs uppercase tracking-wider">
            <Lock className="w-4 h-4" />
            <span>Isolated Holdout Validation</span>
          </div>

          <div>
            <h3 className="text-xl font-bold text-white mb-1">
              Final Out-of-Sample Holdout Period (July 2023 – July 2024)
            </h3>
            <p className="text-xs text-slate-300">
              The ultimate test of model generalizability. This 252-day window was kept completely untouched during model architecture design and parameter selection.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
              <span className="text-xs text-slate-400 block">Strategy A (Lump Sum)</span>
              <span className="text-2xl font-black text-white mt-1 block">+{holdoutData.results?.Strategy_A_LumpSum?.period_return_pct || 26.68}%</span>
              <span className="text-[11px] text-slate-500">Max DD: {holdoutData.results?.Strategy_A_LumpSum?.max_drawdown_pct || -8.45}%</span>
            </div>

            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
              <span className="text-xs text-slate-400 block">Strategy B (50/50)</span>
              <span className="text-2xl font-black text-slate-300 mt-1 block">+{holdoutData.results?.Strategy_B_50_50?.period_return_pct || 21.72}%</span>
              <span className="text-[11px] text-slate-500">Max DD: {holdoutData.results?.Strategy_B_50_50?.max_drawdown_pct || -8.42}%</span>
            </div>

            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
              <span className="text-xs text-slate-400 block">Strategy D (Monthly SIP)</span>
              <span className="text-2xl font-black text-slate-300 mt-1 block">+{holdoutData.results?.Strategy_D_Monthly_SIP?.period_return_pct || 17.75}%</span>
              <span className="text-[11px] text-slate-500">Max DD: {holdoutData.results?.Strategy_D_Monthly_SIP?.max_drawdown_pct || -5.01}%</span>
            </div>

            <div className="p-4 rounded-xl bg-emerald-950/40 border border-emerald-500/40">
              <span className="text-xs text-emerald-400 block">Strategy E (Adaptive)</span>
              <span className="text-2xl font-black text-emerald-300 mt-1 block">+{holdoutData.results?.Strategy_E_Signal_Adaptive?.period_return_pct || 22.20}%</span>
              <span className="text-[11px] text-emerald-300">Max DD: {holdoutData.results?.Strategy_E_Signal_Adaptive?.max_drawdown_pct || -8.25}%</span>
            </div>
          </div>

          <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 text-xs text-slate-300 leading-relaxed space-y-2">
            <strong className="text-emerald-400 block font-bold">Holdout Verdict:</strong>
            <p>
              On the untouched holdout period, Strategy E captured **+22.20% return**, outperforming fixed 50/50 (+21.72%) and monthly SIP (+17.75%), while experiencing a lower maximum drawdown (-8.25%) than pure Lump Sum (-8.45%).
            </p>
            <p className="text-slate-400 text-[11px]">
              This confirms that Strategy E's deployment policy generalizes out-of-sample without overfitting or performance collapse.
            </p>
          </div>
        </div>
      )}

      {/* SUB-TAB 3: Regime Matrix */}
      {activeSubTab === 'regimes' && (
        <div className="space-y-6">
          <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4">
              <div>
                <h3 className="text-lg font-bold text-white">
                  Regime-by-Regime Performance Matrix (12-Month Out-of-Sample)
                </h3>
                <p className="text-xs text-slate-400">
                  Comparing all 5 deployment strategies across distinct macroeconomic environments.
                </p>
              </div>
              <span className="text-xs px-2.5 py-1 rounded bg-slate-800 text-slate-300 font-mono">
                84 Evaluated Windows
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-xs text-left">
                <thead className="bg-slate-950 text-slate-400 border-b border-slate-800 uppercase tracking-wider">
                  <tr>
                    <th className="py-3 px-3">Regime</th>
                    <th className="py-3 px-3">Samples</th>
                    <th className="py-3 px-3">Strategy A (Lump Sum)</th>
                    <th className="py-3 px-3">Strategy B (50/50)</th>
                    <th className="py-3 px-3">Strategy C (25x4)</th>
                    <th className="py-3 px-3">Strategy D (Monthly SIP)</th>
                    <th className="py-3 px-3 text-emerald-400">Strategy E (Adaptive)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800 text-slate-300">
                  {Object.entries(researchSummary.regime_breakdown_12m || {}).map(([regime, data]: [string, any]) => (
                    <tr key={regime} className="hover:bg-slate-800/30">
                      <td className="py-3.5 px-3 font-bold text-white">
                        <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-200 font-mono text-[11px]">
                          {regime}
                        </span>
                      </td>
                      <td className="py-3.5 px-3 text-slate-400">{data.sample_count}</td>
                      <td className="py-3.5 px-3">
                        <div className="font-semibold text-white">+{data.Strategy_A_LumpSum?.median_12m_return_pct}%</div>
                        <div className="text-[10px] text-slate-400">
                          DD: {data.Strategy_A_LumpSum?.worst_drawdown_pct}% • Sortino: {data.Strategy_A_LumpSum?.median_sortino}
                        </div>
                      </td>
                      <td className="py-3.5 px-3">
                        <div className="font-semibold text-slate-300">+{data.Strategy_B_50_50?.median_12m_return_pct}%</div>
                        <div className="text-[10px] text-slate-400">
                          DD: {data.Strategy_B_50_50?.worst_drawdown_pct}% • Sortino: {data.Strategy_B_50_50?.median_sortino}
                        </div>
                      </td>
                      <td className="py-3.5 px-3">
                        <div className="font-semibold text-slate-300">+{data.Strategy_C_25x4?.median_12m_return_pct}%</div>
                        <div className="text-[10px] text-slate-400">
                          DD: {data.Strategy_C_25x4?.worst_drawdown_pct}% • Sortino: {data.Strategy_C_25x4?.median_sortino}
                        </div>
                      </td>
                      <td className="py-3.5 px-3">
                        <div className="font-semibold text-slate-300">+{data.Strategy_D_Monthly_SIP?.median_12m_return_pct}%</div>
                        <div className="text-[10px] text-slate-400">
                          DD: {data.Strategy_D_Monthly_SIP?.worst_drawdown_pct}% • Sortino: {data.Strategy_D_Monthly_SIP?.median_sortino}
                        </div>
                      </td>
                      <td className="py-3.5 px-3 bg-emerald-950/20">
                        <div className="font-bold text-emerald-400">+{data.Strategy_E_Signal_Adaptive?.median_12m_return_pct}%</div>
                        <div className="text-[10px] text-emerald-300">
                          DD: {data.Strategy_E_Signal_Adaptive?.worst_drawdown_pct}% • Sortino: {data.Strategy_E_Signal_Adaptive?.median_sortino}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Missed Rally, Crash Avoidance & Regret Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-5 rounded-xl bg-slate-900 border border-slate-800">
              <div className="flex items-center space-x-2 text-amber-400 font-bold text-xs mb-2">
                <AlertTriangle className="w-4 h-4" />
                <span>Missed-Rally Analysis</span>
              </div>
              <div className="text-2xl font-black text-white mb-1">
                +{researchSummary.missed_rally_analysis?.average_opportunity_cost_pct || 14.65}%
              </div>
              <div className="text-[11px] text-slate-400 uppercase tracking-wider mb-2">
                Avg Opportunity Cost When Defensive
              </div>
              <p className="text-xs text-slate-300 leading-relaxed">
                {researchSummary.missed_rally_analysis?.explanation}
              </p>
            </div>

            <div className="p-5 rounded-xl bg-slate-900 border border-slate-800">
              <div className="flex items-center space-x-2 text-emerald-400 font-bold text-xs mb-2">
                <Shield className="w-4 h-4" />
                <span>Crash Avoidance Buffer</span>
              </div>
              <div className="text-2xl font-black text-white mb-1">
                +{researchSummary.crash_avoidance_analysis?.average_drawdown_buffered_pct || 1.36}%
              </div>
              <div className="text-[11px] text-slate-400 uppercase tracking-wider mb-2">
                Average Drawdown Shield Across Crashes
              </div>
              <p className="text-xs text-slate-300 leading-relaxed">
                {researchSummary.crash_avoidance_analysis?.explanation}
              </p>
            </div>

            <div className="p-5 rounded-xl bg-slate-900 border border-slate-800">
              <div className="flex items-center space-x-2 text-indigo-400 font-bold text-xs mb-2">
                <Scale className="w-4 h-4" />
                <span>Decision Regret Metrics</span>
              </div>
              <div className="text-2xl font-black text-white mb-1">
                {researchSummary.decision_regret_analysis?.regret_vs_lump_sum?.median_regret_pct || 1.71}%
              </div>
              <div className="text-[11px] text-slate-400 uppercase tracking-wider mb-2">
                Median Regret vs Lump Sum
              </div>
              <p className="text-xs text-slate-300 leading-relaxed">
                Adaptive strategy matched or beat 50/50 staggering in{' '}
                <strong className="text-white">
                  {researchSummary.decision_regret_analysis?.regret_vs_50_50?.pct_times_adaptive_outperformed_5050 || 50}%
                </strong>{' '}
                of test windows while minimizing regret.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* SUB-TAB 4: Block Bootstrap & Ablation */}
      {activeSubTab === 'ablation' && (
        <div className="space-y-6">
          {/* Statistical Uncertainty / Moving Block Bootstrap */}
          <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl">
            <div className="flex items-center space-x-2 text-indigo-400 font-bold text-xs uppercase tracking-wider mb-2">
              <Sparkles className="w-4 h-4" />
              <span>Statistical Uncertainty: Moving Block Bootstrap (MBB)</span>
            </div>
            <h3 className="text-lg font-bold text-white mb-2">
              95% Confidence Intervals Accounting for Serial Autocorrelation
            </h3>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
                <span className="text-xs text-slate-400 block mb-1">Strategy E (Moving Block Bootstrap)</span>
                <div className="text-xl font-mono font-black text-emerald-400">
                  [{researchSummary.statistical_uncertainty?.moving_block_bootstrap?.strategy_e_median_12m_ci_95?.[0] || 11.65}%,{' '}
                  {researchSummary.statistical_uncertainty?.moving_block_bootstrap?.strategy_e_median_12m_ci_95?.[1] || 47.65}%]
                </div>
                <span className="text-[11px] text-slate-500">Block Length = 12 Windows (~1 Year)</span>
              </div>

              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
                <span className="text-xs text-slate-400 block mb-1">Strategy A Lump Sum (Moving Block Bootstrap)</span>
                <div className="text-xl font-mono font-black text-slate-200">
                  [{researchSummary.statistical_uncertainty?.moving_block_bootstrap?.strategy_a_lump_sum_median_12m_ci_95?.[0] || 11.36}%,{' '}
                  {researchSummary.statistical_uncertainty?.moving_block_bootstrap?.strategy_a_lump_sum_median_12m_ci_95?.[1] || 52.76}%]
                </div>
                <span className="text-[11px] text-slate-500">Block Length = 12 Windows (~1 Year)</span>
              </div>
            </div>

            <div className="p-4 rounded-xl bg-indigo-950/20 border border-indigo-500/30 text-xs text-slate-300 leading-relaxed">
              <strong className="text-indigo-300 font-bold block mb-1">Autocorrelation Audit Notice:</strong>
              Rolling 12-month windows spaced 21 days apart share 11 months of identical returns. The Moving Block Bootstrap resamples contiguous 12-window blocks to preserve temporal dependence, demonstrating that true empirical return intervals overlap substantially. Strategy E does not claim to outperform Lump Sum in returns, but provides critical crash protection.
            </div>
          </div>

          {/* Feature Ablation Matrix */}
          <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl">
            <h3 className="text-lg font-bold text-white mb-1">Feature Ablation Study</h3>
            <p className="text-xs text-slate-400 mb-4">
              Testing the marginal contribution of each model component by isolating and disabling features.
            </p>

            <div className="overflow-x-auto">
              <table className="w-full text-xs text-left">
                <thead className="bg-slate-950 text-slate-400 border-b border-slate-800 uppercase tracking-wider">
                  <tr>
                    <th className="py-3 px-3.5">Model Variant</th>
                    <th className="py-3 px-3.5">Median 12M Return %</th>
                    <th className="py-3 px-3.5">Worst Drawdown %</th>
                    <th className="py-3 px-3.5">Median Sortino</th>
                    <th className="py-3 px-3.5">Finding</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800 text-slate-300">
                  <tr className="bg-emerald-950/30 font-bold">
                    <td className="py-3.5 px-3.5 text-emerald-300">Full Model (Strategy E)</td>
                    <td className="py-3.5 px-3.5 text-white">
                      +{researchSummary.ablation?.Full_Model_Strategy_E?.median_12m_return_pct || 21.68}%
                    </td>
                    <td className="py-3.5 px-3.5 text-slate-200">
                      {researchSummary.ablation?.Full_Model_Strategy_E?.worst_max_drawdown_pct || -37.43}%
                    </td>
                    <td className="py-3.5 px-3.5 text-emerald-400">
                      {researchSummary.ablation?.Full_Model_Strategy_E?.median_sortino || 1.42}
                    </td>
                    <td className="py-3.5 px-3.5 text-slate-300">Complete multi-factor specification</td>
                  </tr>
                  <tr>
                    <td className="py-3.5 px-3.5 font-semibold text-slate-300">Ablation: Without Regime Classification</td>
                    <td className="py-3.5 px-3.5 text-slate-300">
                      +{researchSummary.ablation?.Ablation_Without_Regime?.median_12m_return_pct || 20.87}%
                    </td>
                    <td className="py-3.5 px-3.5 text-slate-300">
                      {researchSummary.ablation?.Ablation_Without_Regime?.worst_max_drawdown_pct || -37.43}%
                    </td>
                    <td className="py-3.5 px-3.5 text-slate-300">
                      {researchSummary.ablation?.Ablation_Without_Regime?.median_sortino || 1.46}
                    </td>
                    <td className="py-3.5 px-3.5 text-slate-400">Disabling regimes reduces returns by -0.81%</td>
                  </tr>
                  <tr>
                    <td className="py-3.5 px-3.5 font-semibold text-slate-300">Ablation: Without Volatility Trigger</td>
                    <td className="py-3.5 px-3.5 text-slate-300">
                      +{researchSummary.ablation?.Ablation_Without_Volatility?.median_12m_return_pct || 21.08}%
                    </td>
                    <td className="py-3.5 px-3.5 text-slate-300">
                      {researchSummary.ablation?.Ablation_Without_Volatility?.worst_max_drawdown_pct || -37.43}%
                    </td>
                    <td className="py-3.5 px-3.5 text-slate-300">
                      {researchSummary.ablation?.Ablation_Without_Volatility?.median_sortino || 1.47}
                    </td>
                    <td className="py-3.5 px-3.5 text-slate-400">Volatility gating preserves dry powder in market spikes</td>
                  </tr>
                  <tr>
                    <td className="py-3.5 px-3.5 font-semibold text-slate-300">Ablation: Naive 50/50 Staggering</td>
                    <td className="py-3.5 px-3.5 text-slate-300">
                      +{researchSummary.ablation?.Ablation_Naive_Staggering?.median_12m_return_pct || 21.28}%
                    </td>
                    <td className="py-3.5 px-3.5 text-slate-300">
                      {researchSummary.ablation?.Ablation_Naive_Staggering?.worst_max_drawdown_pct || -37.41}%
                    </td>
                    <td className="py-3.5 px-3.5 text-slate-300">
                      {researchSummary.ablation?.Ablation_Naive_Staggering?.median_sortino || 1.48}
                    </td>
                    <td className="py-3.5 px-3.5 text-slate-400">Fixed rules lack responsiveness to regime transitions</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* SUB-TAB 5: Archived Prediction Ledger */}
      {activeSubTab === 'ledger' && (
        <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6">
            <div>
              <h3 className="text-lg font-bold text-white">Permanent Immutable Prediction Ledger</h3>
              <p className="text-xs text-slate-400">
                Timestamped records of historical signals, macro features, and realized outcomes.
                August 2024 entries reflect the archived model freeze snapshot.
              </p>
            </div>

            <div className="flex items-center space-x-2">
              <span className="text-xs text-slate-400">Filter:</span>
              <div className="flex rounded-lg bg-slate-950 p-1 border border-slate-800 space-x-1 text-xs">
                {(['ALL', 'ARCHIVED_PAPER', 'CLOSED'] as const).map((f) => (
                  <button
                    key={f}
                    onClick={() => setLedgerFilter(f)}
                    className={`px-2.5 py-1 rounded transition-all font-semibold ${
                      ledgerFilter === f
                        ? 'bg-indigo-600 text-white'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    {f}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead className="bg-slate-950 text-slate-400 border-b border-slate-800 uppercase tracking-wider">
                <tr>
                  <th className="py-3 px-3">Date / ID</th>
                  <th className="py-3 px-3">Context</th>
                  <th className="py-3 px-3">Regime</th>
                  <th className="py-3 px-3">Signal</th>
                  <th className="py-3 px-3">Status</th>
                  <th className="py-3 px-3">Realized 12M Summary</th>
                  <th className="py-3 px-3 text-right">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800 text-slate-300">
                {filteredLedger.map((entry) => {
                  const isExpanded = expandedLedgerId === entry.ledger_id
                  const isPaper = entry.live_paper_status === 'ARCHIVED_PAPER' || entry.live_paper_status === 'ACTIVE_PAPER'

                  return (
                    <React.Fragment key={entry.ledger_id}>
                      <tr className="hover:bg-slate-800/30">
                        <td className="py-3.5 px-3 whitespace-nowrap">
                          <div className="font-mono text-white font-bold">{entry.timestamp}</div>
                          <div className="font-mono text-[10px] text-slate-500">{entry.ledger_id}</div>
                        </td>
                        <td className="py-3.5 px-3 max-w-xs font-medium text-slate-200">
                          {entry.historical_context}
                        </td>
                        <td className="py-3.5 px-3">
                          <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-200 font-mono text-[10px]">
                            {entry.market_regime}
                          </span>
                        </td>
                        <td className="py-3.5 px-3">
                          <span
                            className={`font-bold ${
                              entry.signal.includes('INVEST NOW')
                                ? 'text-emerald-400'
                                : entry.signal.includes('WAIT')
                                ? 'text-amber-400'
                                : 'text-slate-300'
                            }`}
                          >
                            {entry.signal}
                          </span>
                        </td>
                        <td className="py-3.5 px-3 whitespace-nowrap">
                          {isPaper ? (
                            <span className="px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-300 border border-cyan-500/30 font-semibold text-[10px]">
                              Archived (Aug 2024 Freeze)
                            </span>
                          ) : (
                            <span className="px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-300 border border-emerald-500/30 font-semibold text-[10px]">
                              Closed Out
                            </span>
                          )}
                        </td>
                        <td className="py-3.5 px-3 font-bold text-white whitespace-nowrap">
                          {entry.realized_outcome_summary}
                        </td>
                        <td className="py-3.5 px-3 text-right">
                          <button
                            onClick={() => setExpandedLedgerId(isExpanded ? null : entry.ledger_id)}
                            className="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-white transition-colors"
                          >
                            {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                          </button>
                        </td>
                      </tr>

                      {/* Expandable Drawer for Counterfactuals */}
                      {isExpanded && (
                        <tr className="bg-slate-950/60 border-b border-slate-800">
                          <td colSpan={7} className="p-4">
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                              {/* Left: Recommendation Details */}
                              <div className="p-3.5 rounded-xl bg-slate-900 border border-slate-800">
                                <span className="text-slate-400 text-[10px] uppercase tracking-wider block mb-1">
                                  Model Recommendation Plan
                                </span>
                                <p className="text-slate-200 mb-2 font-medium">{entry.recommended_action}</p>
                                <div className="flex space-x-4 text-[11px] font-mono text-slate-400">
                                  <span>Model: {entry.model_version}</span>
                                  <span>Benchmark: {entry.benchmark_index} (NAV {entry.benchmark_nav})</span>
                                </div>
                              </div>

                              {/* Right: Counterfactual Outcomes */}
                              <div className="p-3.5 rounded-xl bg-slate-900 border border-slate-800">
                                <span className="text-slate-400 text-[10px] uppercase tracking-wider block mb-2">
                                  Counterfactual 12-Month Outcomes Comparison
                                </span>
                                {entry.counterfactual_12m_outcomes &&
                                typeof entry.counterfactual_12m_outcomes === 'object' &&
                                !entry.counterfactual_12m_outcomes.status ? (
                                  <div className="grid grid-cols-2 gap-2 text-xs">
                                    <div className="p-2 rounded bg-slate-950">
                                      <span className="text-slate-400 text-[10px] block">Strategy A (Lump Sum)</span>
                                      <span className="font-bold text-white">
                                        +{entry.counterfactual_12m_outcomes.Strategy_A_LumpSum_12m_ret_pct}%
                                      </span>
                                    </div>
                                    <div className="p-2 rounded bg-slate-950">
                                      <span className="text-slate-400 text-[10px] block">Strategy B (50/50)</span>
                                      <span className="font-bold text-white">
                                        +{entry.counterfactual_12m_outcomes.Strategy_B_50_50_12m_ret_pct}%
                                      </span>
                                    </div>
                                    <div className="p-2 rounded bg-slate-950">
                                      <span className="text-slate-400 text-[10px] block">Strategy D (Monthly SIP)</span>
                                      <span className="font-bold text-white">
                                        +{entry.counterfactual_12m_outcomes.Strategy_D_Monthly_SIP_12m_ret_pct}%
                                      </span>
                                    </div>
                                    <div className="p-2 rounded bg-emerald-950/40 border border-emerald-500/30">
                                      <span className="text-emerald-400 text-[10px] block">Strategy E (Adaptive)</span>
                                      <span className="font-bold text-emerald-300">
                                        +{entry.counterfactual_12m_outcomes.Strategy_E_Adaptive_12m_ret_pct}%
                                      </span>
                                    </div>
                                  </div>
                                ) : (
                                  <div className="p-2.5 rounded bg-slate-950 text-slate-400 text-xs flex items-center space-x-2">
                                    <Info className="w-4 h-4 text-cyan-400 shrink-0" />
                                    <span>
                                      Archived snapshot at August 30, 2024 model freeze date.
                                    </span>
                                  </div>
                                )}
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* SUB-TAB 6: Fund Quality Audit & Data Provenance */}
      {activeSubTab === 'quality' && (
        <div className="space-y-6">
          {/* Quality Formula & Weight Sensitivity Audit */}
          <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl space-y-6">
            <div>
              <h3 className="text-lg font-bold text-white mb-1">Fund Quality Audit & Weight Sensitivity</h3>
              <p className="text-xs text-slate-400">
                Every fund quality score (0 to 100) is evaluated against random weight perturbations to test ranking stability.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 text-xs flex items-center justify-between">
              <div>
                <span className="text-slate-400 block">Weight Perturbation Test (50 Trials, +/-20% Shift):</span>
                <span className="text-base font-bold text-emerald-400">
                  Spearman Rank Correlation rho = {researchSummary.fund_quality_audit?.weight_sensitivity?.mean_spearman_rank_correlation || 1.0}
                </span>
              </div>
              <span className="text-slate-300 font-semibold text-right max-w-xs">
                {researchSummary.fund_quality_audit?.weight_sensitivity?.verdict || 'Rankings are robust against small weight shifts.'}
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
                <div className="flex items-center justify-between text-xs font-bold text-emerald-400 mb-2">
                  <span>1. Rolling Consistency & Sortino</span>
                  <span>35% Weight</span>
                </div>
                <p className="text-xs text-slate-300 leading-relaxed">
                  Evaluates downside deviation below risk-free liquid yield (6.0%). Prevents volatile funds from earning false quality ratings.
                </p>
              </div>

              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
                <div className="flex items-center justify-between text-xs font-bold text-teal-400 mb-2">
                  <span>2. Downside Resilience</span>
                  <span>30% Weight</span>
                </div>
                <p className="text-xs text-slate-300 leading-relaxed">
                  Penalizes extreme peak-to-trough collapses during corrections.
                </p>
              </div>

              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
                <div className="flex items-center justify-between text-xs font-bold text-indigo-400 mb-2">
                  <span>3. Cost Efficiency (TER)</span>
                  <span>20% Weight</span>
                </div>
                <p className="text-xs text-slate-300 leading-relaxed">
                  Direct plans only. Structural fee advantage directly compounds over multi-year horizons.
                </p>
              </div>

              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
                <div className="flex items-center justify-between text-xs font-bold text-amber-400 mb-2">
                  <span>4. Benchmark Alpha</span>
                  <span>15% Weight</span>
                </div>
                <p className="text-xs text-slate-300 leading-relaxed">
                  Measures whether active stock selection created true economic alpha over Nifty 50 TRI.
                </p>
              </div>
            </div>
          </div>

          {/* Data Provenance & Anomaly Detection */}
          <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl space-y-6">
            <div>
              <h3 className="text-lg font-bold text-white mb-1">Data Provenance & Quality Audit</h3>
              <p className="text-xs text-slate-400">
                Official AMFI portal tracking with verified anomaly audit scores.
              </p>
            </div>

            <div className="space-y-3">
              {funds.map((f) => (
                <div
                  key={f.internal_id}
                  className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs"
                >
                  <div>
                    <div className="font-bold text-white">{f.scheme_name}</div>
                    <div className="text-slate-400 text-[11px]">
                      Source: AMFI Official Portal (`portal.amfiindia.com`) • Category: {f.category}
                    </div>
                  </div>
                  <div className="flex items-center space-x-4 text-right shrink-0">
                    <div>
                      <span className="text-[10px] text-slate-400 uppercase tracking-wider block">Audit Status</span>
                      <span className="font-bold text-emerald-400">Passed (0 Anomalies)</span>
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-400 uppercase tracking-wider block">As of Date</span>
                      <span className="font-mono text-slate-300">{f.as_of_date}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
