import React, { useState, useEffect } from 'react'
import { BacktestReport } from '../../engine/marketIntelligence/types'
import { CheckCircle2, AlertTriangle, ShieldCheck, BarChart3 } from 'lucide-react'

export const HistoricalPerformanceCard: React.FC = () => {
  const [report, setReport] = useState<BacktestReport | null>(null)
  const [activeTab, setActiveTab] = useState<'horizons' | 'ablation' | 'calibration' | 'failures'>('horizons')

  useEffect(() => {
    fetch('/data/market_intelligence/backtest_report.json')
      .then((res) => res.json())
      .then((data) => setReport(data))
      .catch((err) => console.warn('Could not load backtest report:', err))
  }, [])

  if (!report) {
    return (
      <div className="p-6 rounded-3xl bg-slate-900/60 border border-slate-800 text-center text-xs text-slate-500">
        Loading empirical walk-forward performance report...
      </div>
    )
  }

  return (
    <div className="p-6 rounded-3xl bg-slate-900/80 border border-white/[0.08] shadow-2xl space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-white/[0.06]">
        <div>
          <span className="text-[10px] uppercase font-bold tracking-widest text-emerald-400">
            Empirical Validation
          </span>
          <h3 className="text-base font-bold text-white mt-0.5">
            Walk-Forward Backtesting & Calibration Verification
          </h3>
        </div>

        {/* Tab switcher */}
        <div className="flex items-center space-x-1 p-1 rounded-xl bg-slate-950/80 border border-white/[0.06] text-xs">
          <button
            onClick={() => setActiveTab('horizons')}
            className={`px-2.5 py-1 rounded-lg font-bold transition-all ${
              activeTab === 'horizons' ? 'bg-emerald-500 text-slate-950 font-extrabold' : 'text-slate-400 hover:text-white'
            }`}
          >
            Horizons
          </button>
          <button
            onClick={() => setActiveTab('ablation')}
            className={`px-2.5 py-1 rounded-lg font-bold transition-all ${
              activeTab === 'ablation' ? 'bg-emerald-500 text-slate-950 font-extrabold' : 'text-slate-400 hover:text-white'
            }`}
          >
            Ablation
          </button>
          <button
            onClick={() => setActiveTab('calibration')}
            className={`px-2.5 py-1 rounded-lg font-bold transition-all ${
              activeTab === 'calibration' ? 'bg-emerald-500 text-slate-950 font-extrabold' : 'text-slate-400 hover:text-white'
            }`}
          >
            Calibration
          </button>
          <button
            onClick={() => setActiveTab('failures')}
            className={`px-2.5 py-1 rounded-lg font-bold transition-all ${
              activeTab === 'failures' ? 'bg-emerald-500 text-slate-950 font-extrabold' : 'text-slate-400 hover:text-white'
            }`}
          >
            Failure Cases
          </button>
        </div>
      </div>

      {/* Tab 1: Horizon Performance */}
      {activeTab === 'horizons' && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-white/[0.06] text-slate-400 font-mono text-[11px]">
                <th className="py-2 font-bold">Horizon</th>
                <th className="py-2 font-bold">Directional Acc %</th>
                <th className="py-2 font-bold">Brier Score</th>
                <th className="py-2 font-bold">Log Loss</th>
                <th className="py-2 font-bold">ROC-AUC</th>
                <th className="py-2 font-bold">Sharpe</th>
                <th className="py-2 font-bold">Max DD %</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.04] font-mono">
              {Object.entries(report.summary_by_horizon).map(([h, m]) => (
                <tr key={h} className="hover:bg-white/[0.02]">
                  <td className="py-2.5 font-bold text-white">{h}</td>
                  <td className="py-2.5 font-bold text-emerald-400">{m.directional_accuracy_pct}%</td>
                  <td className="py-2.5 text-slate-300">{m.brier_score}</td>
                  <td className="py-2.5 text-slate-300">{m.log_loss}</td>
                  <td className="py-2.5 text-cyan-400">{m.roc_auc}</td>
                  <td className="py-2.5 text-white font-bold">{m.annualized_sharpe}</td>
                  <td className="py-2.5 text-rose-400">{m.max_drawdown_pct}%</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-[10px] text-slate-500 mt-2 font-sans">
            * Evaluated across {report.total_test_windows} out-of-sample expanding windows ({report.evaluation_period}). Purged and embargoed to avoid serial autocorrelation leakage.
          </p>
        </div>
      )}

      {/* Tab 2: Feature Ablation Study */}
      {activeTab === 'ablation' && (
        <div className="space-y-3">
          <p className="text-xs text-slate-400">
            Ablation testing verifies whether adding news, information surprise, and brand sentiment genuinely increases predictive power over baseline technicals:
          </p>
          <div className="space-y-2">
            {Object.entries(report.ablation_study).map(([name, item]) => (
              <div
                key={name}
                className="p-3 rounded-2xl bg-white/[0.02] border border-white/[0.04] flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs"
              >
                <div className="space-y-0.5">
                  <div className="font-bold text-slate-200">{name}</div>
                  <div className="text-[10px] text-slate-500 font-mono">
                    Brier: {item.brier_score} • ROC-AUC: {item.roc_auc}
                  </div>
                </div>
                <div className="flex items-center space-x-3 shrink-0">
                  <span className="font-mono font-bold text-white">{item.directional_accuracy}% Acc</span>
                  <span
                    className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold ${
                      item.delta_vs_baseline.startsWith('+')
                        ? 'bg-emerald-500/10 text-emerald-400'
                        : 'bg-slate-800 text-slate-400'
                    }`}
                  >
                    {item.delta_vs_baseline}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tab 3: Reliability Calibration */}
      {activeTab === 'calibration' && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead>
              <tr className="border-b border-white/[0.06] text-slate-400 text-[11px]">
                <th className="py-2">Predicted Probability Bucket</th>
                <th className="py-2">Mean Predicted</th>
                <th className="py-2">Empirical Realized Rate</th>
                <th className="py-2">Sample Size</th>
                <th className="py-2">Calibration Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.04]">
              {report.calibration_table.map((row) => {
                const diff = Math.abs(row.mean_predicted - row.realized_rate)
                const isWellCalibrated = diff < 0.03

                return (
                  <tr key={row.predicted_bucket} className="hover:bg-white/[0.02]">
                    <td className="py-2.5 font-bold text-slate-200">{row.predicted_bucket}</td>
                    <td className="py-2.5 text-slate-400">{(row.mean_predicted * 100).toFixed(1)}%</td>
                    <td className="py-2.5 font-bold text-white">{(row.realized_rate * 100).toFixed(1)}%</td>
                    <td className="py-2.5 text-slate-500">{row.sample_size}</td>
                    <td className="py-2.5">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          isWellCalibrated
                            ? 'bg-emerald-500/10 text-emerald-400'
                            : 'bg-amber-500/10 text-amber-400'
                        }`}
                      >
                        {isWellCalibrated ? 'Calibrated (±3%)' : 'Minor Drift'}
                      </span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Tab 4: Failure Analysis */}
      {activeTab === 'failures' && (
        <div className="space-y-3">
          <p className="text-xs text-slate-400">
            Mandatory post-mortem accounting of predictions that failed out-of-sample:
          </p>
          <div className="space-y-3">
            {report.failure_analysis.map((fail) => (
              <div
                key={fail.failure_id}
                className="p-3.5 rounded-2xl bg-rose-500/[0.03] border border-rose-500/20 text-xs space-y-1.5"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-bold text-rose-400">{fail.type}</span>
                  <span className="text-[10px] font-mono text-slate-500">
                    {fail.date} • {fail.asset}
                  </span>
                </div>
                <div className="text-[11px] font-mono text-slate-300">
                  Predicted Bullish:{' '}
                  <strong className="text-white">{(fail.forecast_bullish_prob * 100).toFixed(0)}%</strong> vs
                  Realized Return: <strong className="text-rose-400">{fail.realized_5d_return}%</strong>
                </div>
                <p className="text-slate-400 leading-relaxed text-[11px]">
                  <strong className="text-slate-300">Root Cause:</strong> {fail.root_cause}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
