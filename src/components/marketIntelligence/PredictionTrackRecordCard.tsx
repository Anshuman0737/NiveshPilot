import React, { useState, useEffect } from 'react'
import { PaperPredictionRecord } from '../../engine/marketIntelligence/types'
import { loadPaperPredictionLedger, computeLedgerStats } from '../../engine/marketIntelligence/paperForecastLedger'
import { Lock, CheckCircle2, XCircle, Clock, ShieldCheck } from 'lucide-react'

export const PredictionTrackRecordCard: React.FC = () => {
  const [ledger, setLedger] = useState<PaperPredictionRecord[]>([])

  useEffect(() => {
    loadPaperPredictionLedger().then((data) => setLedger(data))
  }, [])

  const stats = computeLedgerStats(ledger)

  return (
    <div className="p-6 rounded-3xl bg-slate-900/80 border border-white/[0.08] shadow-2xl space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-white/[0.06]">
        <div>
          <span className="text-[10px] uppercase font-bold tracking-widest text-emerald-400">
            Immutable Audit Trail
          </span>
          <h3 className="text-base font-bold text-white mt-0.5">
            Cryptographic Paper Prediction Track Record
          </h3>
        </div>

        {/* Aggregate Track Record Badges */}
        <div className="flex items-center space-x-3 text-xs font-mono">
          <div className="px-3 py-1 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
            Hit Rate: <strong>{stats.hitRatePct}%</strong> ({stats.scoredCount} Scored)
          </div>
          <div className="px-3 py-1 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
            Active: <strong>{stats.activeCount}</strong>
          </div>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-white/[0.06] text-slate-400 font-mono text-[11px]">
              <th className="py-2">Prediction ID</th>
              <th className="py-2">Asset / Horizon</th>
              <th className="py-2">Forecast Direction</th>
              <th className="py-2">Bull / Neu / Bear</th>
              <th className="py-2">Snapshot Hash</th>
              <th className="py-2">Status</th>
              <th className="py-2">Realized Return</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/[0.04] font-mono">
            {ledger.map((pred) => {
              const isScored = pred.status === 'SCORED'
              const pBull = Math.round(pred.probability_bullish * 100)
              const pNeu = Math.round(pred.probability_neutral * 100)
              const pBear = Math.round(pred.probability_bearish * 100)

              return (
                <tr key={pred.prediction_id} className="hover:bg-white/[0.02]">
                  <td className="py-3 text-[11px] text-slate-400 flex items-center space-x-1">
                    <Lock className="w-3 h-3 text-slate-500 shrink-0" />
                    <span>{pred.prediction_id}</span>
                  </td>
                  <td className="py-3 font-bold text-white">
                    {pred.asset}{' '}
                    <span className="text-[10px] font-normal px-1.5 py-0.5 rounded bg-white/[0.05] text-slate-400">
                      {pred.horizon}
                    </span>
                  </td>
                  <td className="py-3">
                    <span
                      className={`text-[11px] font-bold ${
                        pred.expected_direction.includes('BULLISH')
                          ? 'text-emerald-400'
                          : pred.expected_direction.includes('BEARISH')
                          ? 'text-rose-400'
                          : 'text-slate-300'
                      }`}
                    >
                      {pred.expected_direction}
                    </span>
                  </td>
                  <td className="py-3 text-[11px]">
                    <span className="text-emerald-400">{pBull}%</span> /{' '}
                    <span className="text-slate-400">{pNeu}%</span> /{' '}
                    <span className="text-rose-400">{pBear}%</span>
                  </td>
                  <td className="py-3 text-[10px] text-slate-500 font-mono">
                    #{pred.feature_snapshot_hash}
                  </td>
                  <td className="py-3">
                    {isScored ? (
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 flex items-center space-x-1 w-fit">
                        <CheckCircle2 className="w-2.5 h-2.5" />
                        <span>Scored</span>
                      </span>
                    ) : (
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 flex items-center space-x-1 w-fit">
                        <Clock className="w-2.5 h-2.5" />
                        <span>Active</span>
                      </span>
                    )}
                  </td>
                  <td className="py-3">
                    {pred.actual_return_pct !== null ? (
                      <span
                        className={`font-bold ${
                          pred.actual_return_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'
                        }`}
                      >
                        {pred.actual_return_pct >= 0 ? '+' : ''}
                        {pred.actual_return_pct}%
                      </span>
                    ) : (
                      <span className="text-slate-600 text-[11px]">Pending Expiry</span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
