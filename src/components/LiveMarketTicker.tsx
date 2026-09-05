import React, { useState, useEffect } from 'react'
import {
  LiveQuote,
  subscribeToLiveMarket,
  getSectorBreadth,
  SectorPerformance
} from '../engine/liveMarketService'
import {
  TrendingUp,
  TrendingDown,
  Activity,
  Layers,
  X,
  ExternalLink,
  ChevronRight,
  ShieldCheck,
  Flame
} from 'lucide-react'

export const LiveMarketTicker: React.FC = () => {
  const [quotes, setQuotes] = useState<LiveQuote[]>([])
  const [selectedQuote, setSelectedQuote] = useState<LiveQuote | null>(null)
  const [showSectors, setShowSectors] = useState<boolean>(false)

  useEffect(() => {
    const unsubscribe = subscribeToLiveMarket((newQuotes) => {
      setQuotes(newQuotes)
    })
    return () => unsubscribe()
  }, [])

  if (quotes.length === 0) return null

  const sectors = getSectorBreadth(quotes)
  const indices = quotes.filter((q) => q.category === 'index')
  const stocks = quotes.filter((q) => q.category === 'stock')

  const formatINR = (val: number) =>
    new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 1
    }).format(val)

  return (
    <div className="w-full bg-slate-950/90 border-b border-white/[0.06] backdrop-blur-lg select-none relative z-20">
      {/* Streaming Ticker Ribbon */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-2 flex items-center justify-between gap-3 overflow-hidden">
        {/* Left Live Badge */}
        <div className="flex items-center space-x-2 shrink-0 pr-3 border-r border-white/[0.08]">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
          </span>
          <span className="text-[10px] font-black tracking-widest text-slate-300 uppercase hidden sm:inline">
            Live Markets
          </span>
        </div>

        {/* Horizontal Scrolling Ribbon */}
        <div className="flex items-center space-x-4 sm:space-x-6 overflow-x-auto scrollbar-none py-0.5 text-xs">
          {/* Indices */}
          {indices.map((q) => {
            const isUp = q.change >= 0
            const isVix = q.symbol === 'INDIA VIX'
            return (
              <div
                key={q.symbol}
                onClick={() => setSelectedQuote(q)}
                className="flex items-center space-x-1.5 cursor-pointer hover:opacity-80 transition-opacity shrink-0 px-2 py-0.5 rounded-full hover:bg-white/[0.05]"
              >
                <span className="font-bold text-slate-200 text-[11px]">{q.symbol}</span>
                <span className="font-mono text-white text-[11px]">
                  {q.price.toLocaleString('en-IN', { maximumFractionDigits: isVix ? 2 : 1 })}
                </span>
                <span
                  className={`flex items-center text-[10px] font-bold ${
                    isUp ? 'text-emerald-400' : 'text-rose-400'
                  }`}
                >
                  {isUp ? '+' : ''}
                  {q.changePct}%
                </span>
              </div>
            )
          })}

          <span className="text-slate-700 shrink-0">•</span>

          {/* Top Indian Stocks */}
          {stocks.map((q) => {
            const isUp = q.change >= 0
            return (
              <div
                key={q.symbol}
                onClick={() => setSelectedQuote(q)}
                className="flex items-center space-x-1.5 cursor-pointer hover:opacity-80 transition-opacity shrink-0 px-2 py-0.5 rounded-full hover:bg-white/[0.05]"
              >
                <span className="font-semibold text-slate-300 text-[11px]">{q.symbol}</span>
                <span className="font-mono text-slate-100 text-[11px]">₹{q.price}</span>
                <span
                  className={`text-[10px] font-bold ${isUp ? 'text-emerald-400' : 'text-rose-400'}`}
                >
                  {isUp ? '+' : ''}
                  {q.changePct}%
                </span>
              </div>
            )
          })}
        </div>

        {/* Right Sector Breadth Toggle */}
        <div className="shrink-0 pl-3 border-l border-white/[0.08] hidden md:flex items-center">
          <button
            onClick={() => setShowSectors(!showSectors)}
            className="flex items-center space-x-1 text-[11px] font-medium text-slate-400 hover:text-white px-2 py-1 rounded-full hover:bg-white/[0.05] transition-all"
          >
            <Activity className="w-3 h-3 text-indigo-400" />
            <span>Sectors</span>
          </button>
        </div>
      </div>

      {/* Sector Breadth Drawer */}
      {showSectors && (
        <div className="border-t border-white/[0.04] bg-slate-900/60 backdrop-blur-md px-4 sm:px-8 py-2.5 flex flex-wrap items-center justify-between gap-3 text-xs animate-fade-in">
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
            Live Sector Performance:
          </span>
          <div className="flex flex-wrap items-center gap-3">
            {sectors.map((s) => (
              <div
                key={s.sector}
                className="flex items-center space-x-1.5 px-2.5 py-0.5 rounded-full bg-white/[0.03] border border-white/[0.05]"
              >
                <span className="text-slate-300 text-[11px]">{s.sector}:</span>
                <span
                  className={`font-bold text-[11px] ${
                    s.changePct >= 0 ? 'text-emerald-400' : 'text-rose-400'
                  }`}
                >
                  {s.changePct >= 0 ? '+' : ''}
                  {s.changePct}%
                </span>
                <span className="text-[10px] text-slate-500">({s.topStock})</span>
              </div>
            ))}
          </div>
          <button
            onClick={() => setShowSectors(false)}
            className="text-slate-500 hover:text-slate-300 p-1"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Selected Stock / Index Live Detail Modal */}
      {selectedQuote && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-navy-950/80 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-md bg-slate-900 border border-white/[0.1] rounded-3xl p-6 shadow-2xl relative">
            <button
              onClick={() => setSelectedQuote(null)}
              className="absolute top-4 right-4 p-1.5 text-slate-400 hover:text-white rounded-full hover:bg-white/[0.05]"
            >
              <X className="w-4 h-4" />
            </button>

            <div className="flex items-start justify-between mb-4">
              <div>
                <span className="px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 text-[10px] font-bold uppercase">
                  {selectedQuote.category === 'index' ? 'Market Index' : selectedQuote.sector || 'NSE Stock'}
                </span>
                <h3 className="text-2xl font-black text-white mt-1">{selectedQuote.symbol}</h3>
                <p className="text-xs text-slate-400">{selectedQuote.name}</p>
              </div>
              <div className="text-right">
                <div className="text-2xl font-black text-white font-mono">
                  ₹{selectedQuote.price.toLocaleString('en-IN')}
                </div>
                <div
                  className={`text-xs font-bold ${
                    selectedQuote.change >= 0 ? 'text-emerald-400' : 'text-rose-400'
                  }`}
                >
                  {selectedQuote.change >= 0 ? '+' : ''}
                  {selectedQuote.change.toFixed(1)} ({selectedQuote.change >= 0 ? '+' : ''}
                  {selectedQuote.changePct}%)
                </div>
              </div>
            </div>

            {/* Today's Range Slider */}
            <div className="p-3.5 rounded-2xl bg-slate-950 border border-white/[0.05] mb-4 space-y-2">
              <div className="flex justify-between text-[11px] text-slate-400">
                <span>Day Low: ₹{selectedQuote.dayLow}</span>
                <span>Day High: ₹{selectedQuote.dayHigh}</span>
              </div>
              <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden relative">
                <div
                  style={{
                    width: `${Math.min(
                      100,
                      Math.max(
                        0,
                        ((selectedQuote.price - selectedQuote.dayLow) /
                          (selectedQuote.dayHigh - selectedQuote.dayLow || 1)) *
                          100
                      )
                    )}%`
                  }}
                  className="h-full bg-emerald-400 rounded-full"
                />
              </div>
              <div className="flex justify-between text-[10px] text-slate-500">
                <span>Prev Close: ₹{selectedQuote.prevClose}</span>
                <span>Live NSE Feed</span>
              </div>
            </div>

            {/* Key Metrics */}
            <div className="grid grid-cols-2 gap-2 text-xs mb-4">
              {selectedQuote.peRatio && (
                <div className="p-2.5 rounded-xl bg-slate-950/60 border border-white/[0.05]">
                  <span className="text-[10px] text-slate-500 block">P/E Valuation:</span>
                  <span className="font-bold text-white text-sm">{selectedQuote.peRatio}x</span>
                </div>
              )}
              {selectedQuote.marketCapCr && (
                <div className="p-2.5 rounded-xl bg-slate-950/60 border border-white/[0.05]">
                  <span className="text-[10px] text-slate-500 block">Market Cap:</span>
                  <span className="font-bold text-white text-sm">
                    ₹{(selectedQuote.marketCapCr / 1000).toFixed(0)}k Cr
                  </span>
                </div>
              )}
            </div>

            <div className="text-[11px] text-slate-400 bg-emerald-500/[0.06] border border-emerald-500/20 p-3 rounded-2xl flex items-center space-x-2">
              <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />
              <span>
                Held across major Indian mutual funds (Parag Parikh, Mirae Large, HDFC Mid-Cap).
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
