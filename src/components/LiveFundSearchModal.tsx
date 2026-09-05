import React, { useState, useEffect } from 'react'
import {
  searchLiveMutualFunds,
  fetchLiveFundNav,
  convertLiveMfToSnapshot,
  LiveMfSearchResult
} from '../engine/liveMfService'
import { FundSnapshot } from '../engine/types'
import {
  Search,
  X,
  Sparkles,
  ArrowRight,
  TrendingUp,
  Loader2,
  Building,
  CheckCircle2,
  Database
} from 'lucide-react'

interface LiveFundSearchModalProps {
  isOpen: boolean
  onClose: () => void
  onSelectFund: (fund: FundSnapshot) => void
}

export const LiveFundSearchModal: React.FC<LiveFundSearchModalProps> = ({
  isOpen,
  onClose,
  onSelectFund
}) => {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<LiveMfSearchResult[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isFetchingNav, setIsFetchingNav] = useState(false)
  const [selectedCode, setSelectedCode] = useState<number | null>(null)

  useEffect(() => {
    if (!isOpen) return
    const timer = setTimeout(async () => {
      if (query.trim().length >= 2) {
        setIsLoading(true)
        const res = await searchLiveMutualFunds(query)
        setResults(res)
        setIsLoading(false)
      } else {
        // Initial popular Indian mutual fund recommendations
        setResults([
          { schemeCode: 122639, schemeName: 'Parag Parikh Flexi Cap Fund - Direct Plan - Growth' },
          { schemeCode: 118834, schemeName: 'Mirae Asset Large Cap Fund - Direct Plan - Growth' },
          { schemeCode: 118989, schemeName: 'HDFC Mid-Cap Opportunities Fund - Direct Plan - Growth' },
          { schemeCode: 120716, schemeName: 'Nippon India Small Cap Fund - Direct Plan - Growth' },
          { schemeCode: 120503, schemeName: 'Quant Small Cap Fund - Direct Plan - Growth' },
          { schemeCode: 120828, schemeName: 'UTI Nifty 50 Index Fund - Direct Plan - Growth' },
          { schemeCode: 125354, schemeName: 'Tata Digital India Fund - Direct Plan - Growth' },
          { schemeCode: 119717, schemeName: 'SBI Liquid Fund - Direct Plan - Growth' }
        ])
      }
    }, 250)

    return () => clearTimeout(timer)
  }, [query, isOpen])

  if (!isOpen) return null

  const handleSelect = async (schemeCode: number) => {
    setSelectedCode(schemeCode)
    setIsFetchingNav(true)
    const details = await fetchLiveFundNav(schemeCode)
    setIsFetchingNav(false)

    if (details) {
      const snapshot = convertLiveMfToSnapshot(details)
      onSelectFund(snapshot)
      onClose()
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-navy-950/85 backdrop-blur-md animate-fade-in">
      <div className="w-full max-w-2xl bg-slate-900 border border-white/[0.1] rounded-3xl p-6 shadow-2xl overflow-hidden max-h-[85vh] flex flex-col relative">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-white/[0.06]">
          <div>
            <div className="inline-flex items-center space-x-1.5 px-2.5 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-[10px] font-bold uppercase tracking-wider mb-1">
              <Database className="w-3 h-3" />
              <span>Official AMFI Database</span>
            </div>
            <h3 className="text-xl font-black text-white tracking-tight">
              Search 40,000+ Indian Mutual Funds Live
            </h3>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-slate-400 hover:text-white rounded-full hover:bg-white/[0.05] transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Search Input */}
        <div className="my-4 relative">
          <Search className="w-4 h-4 text-slate-400 absolute left-4 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Type any fund name (e.g. Quant Small Cap, Tata Digital, ICICI Bluechip, Parag Parikh)..."
            className="w-full pl-11 pr-4 py-3 rounded-2xl bg-slate-950 border border-white/[0.08] text-sm text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500 transition-all"
          />
          {isLoading && (
            <Loader2 className="w-4 h-4 text-emerald-400 animate-spin absolute right-4 top-1/2 -translate-y-1/2" />
          )}
        </div>

        {/* Results List */}
        <div className="flex-1 overflow-y-auto space-y-2 pr-1">
          {results.length === 0 && !isLoading ? (
            <div className="text-center py-10 text-slate-500 text-xs">
              No matching schemes found. Try a different AMC or scheme keyword.
            </div>
          ) : (
            results.map((r) => {
              const isSelected = selectedCode === r.schemeCode
              return (
                <div
                  key={r.schemeCode}
                  onClick={() => !isFetchingNav && handleSelect(r.schemeCode)}
                  className={`p-3.5 rounded-2xl border transition-all cursor-pointer flex items-center justify-between gap-3 group ${
                    isSelected
                      ? 'bg-emerald-500/10 border-emerald-500/40 text-emerald-300'
                      : 'bg-slate-950/60 border-white/[0.04] hover:border-white/[0.12] hover:bg-white/[0.03] text-slate-200'
                  }`}
                >
                  <div>
                    <div className="font-bold text-xs sm:text-sm text-white group-hover:text-emerald-300 transition-colors">
                      {r.schemeName}
                    </div>
                    <div className="text-[11px] text-slate-500 flex items-center space-x-2 mt-0.5">
                      <span>AMFI Code: {r.schemeCode}</span>
                    </div>
                  </div>

                  <div className="shrink-0 flex items-center space-x-2">
                    {isFetchingNav && isSelected ? (
                      <Loader2 className="w-4 h-4 text-emerald-400 animate-spin" />
                    ) : (
                      <button className="px-3 py-1 rounded-full bg-slate-800 group-hover:bg-emerald-500 group-hover:text-navy-950 text-slate-300 font-bold text-xs flex items-center space-x-1 transition-all">
                        <span>Load Live NAV</span>
                        <ArrowRight className="w-3 h-3" />
                      </button>
                    )}
                  </div>
                </div>
              )
            })
          )}
        </div>

        {/* Footer */}
        <div className="pt-3 border-t border-white/[0.06] mt-3 flex items-center justify-between text-[11px] text-slate-400">
          <span>Real-time daily NAVs fetched directly from AMFI (Association of Mutual Funds in India).</span>
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-full text-xs font-semibold text-slate-400 hover:text-white"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
