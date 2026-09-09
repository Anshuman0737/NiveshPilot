import React from 'react'
import { getProviderHealthList } from '../../engine/marketIntelligence/providers/ProviderManager'
import { X, Activity, CheckCircle2, AlertTriangle, ShieldCheck, Database } from 'lucide-react'

interface ProviderHealthModalProps {
  isOpen: boolean
  onClose: () => void
}

export const ProviderHealthModal: React.FC<ProviderHealthModalProps> = ({ isOpen, onClose }) => {
  if (!isOpen) return null

  const providers = getProviderHealthList()

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md animate-fade-in">
      <div className="w-full max-w-2xl bg-slate-900 border border-white/[0.1] rounded-3xl p-6 sm:p-8 shadow-2xl space-y-6 relative">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-white/[0.08]">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
              <Activity className="w-5 h-5 text-emerald-400" />
            </div>
            <div>
              <h3 className="text-lg font-bold text-white">Data Provider Health & Provenance</h3>
              <p className="text-xs text-slate-400">
                Live monitoring of external public APIs, latency & data integrity
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-2 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] text-slate-400 hover:text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Providers Table */}
        <div className="space-y-3 max-h-[60vh] overflow-y-auto pr-1">
          {providers.map((p) => {
            const isOnline = p.status === 'ONLINE'
            return (
              <div
                key={p.id}
                className="p-4 rounded-2xl bg-white/[0.02] border border-white/[0.04] flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs"
              >
                <div className="space-y-1">
                  <div className="flex items-center space-x-2">
                    <span className="font-bold text-slate-200">{p.name}</span>
                    <span
                      className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                        isOnline
                          ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                          : 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                      }`}
                    >
                      {p.status}
                    </span>
                  </div>
                  <div className="text-[10px] text-slate-500 font-mono truncate max-w-sm">
                    {p.endpoint}
                  </div>
                </div>

                <div className="flex items-center space-x-4 shrink-0 font-mono text-[11px]">
                  <div>
                    <span className="text-slate-500 block text-[9px] uppercase">Latency</span>
                    <span className="font-bold text-white">{p.latencyMs} ms</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[9px] uppercase">Freshness</span>
                    <span className="text-cyan-400 font-bold">{p.freshness}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[9px] uppercase">Errors</span>
                    <span className={p.errorCount > 0 ? 'text-rose-400 font-bold' : 'text-slate-400'}>
                      {p.errorCount}
                    </span>
                  </div>
                </div>
              </div>
            )
          })}
        </div>

        {/* Footer Policy Notice */}
        <div className="p-3.5 rounded-2xl bg-white/[0.02] border border-white/[0.04] text-xs text-slate-400 flex items-start space-x-2">
          <Database className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
          <div className="leading-relaxed text-[11px]">
            <strong className="text-slate-200">Zero-Fabrication Guarantee: </strong>
            If an external provider is unreachable or returns stale quotes, NiveshPilot marks the metric as{' '}
            <code className="text-amber-400 font-mono">UNAVAILABLE</code> or{' '}
            <code className="text-indigo-400 font-mono">HISTORICAL</code>. We never invent synthetic market prices.
          </div>
        </div>
      </div>
    </div>
  )
}
