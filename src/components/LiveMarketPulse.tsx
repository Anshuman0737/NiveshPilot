import React, { useState, useEffect } from 'react'
import {
  Activity,
  Sliders,
  RotateCcw,
  Zap,
  ChevronDown,
  ChevronUp
} from 'lucide-react'
import { subscribeToLiveMarket, LiveQuote } from '../engine/liveMarketService'

export interface SimulatedMarketState {
  isSimulated: boolean
  marketDropPct: number
  volatilityPct: number
  simulatedIndex: number
  simulatedRegime: string
  simulatedSignal: string
}

interface LiveMarketPulseProps {
  onSimulateStateChange?: (state: SimulatedMarketState) => void
}

export const LiveMarketPulse: React.FC<LiveMarketPulseProps> = ({ onSimulateStateChange }) => {
  const [liveNifty, setLiveNifty] = useState<LiveQuote | null>(null)
  const [liveVix, setLiveVix] = useState<LiveQuote | null>(null)
  const [isSimulatorOpen, setIsSimulatorOpen] = useState<boolean>(false)

  const [simDrop, setSimDrop] = useState<number>(0)
  const [simVol, setSimVol] = useState<number>(13.4)

  useEffect(() => {
    const unsub = subscribeToLiveMarket((quotes) => {
      const nifty = quotes.find((q) => q.symbol === 'NIFTY 50')
      const vix = quotes.find((q) => q.symbol === 'INDIA VIX')
      if (nifty) setLiveNifty(nifty)
      if (vix) setLiveVix(vix)
    })
    return () => unsub()
  }, [])

  const baseIndex = liveNifty?.price || 24852.4
  const baseChange = liveNifty?.change || 142.3
  const baseChangePct = liveNifty?.changePct || 0.57
  const baseVol = liveVix?.price || 13.4
  const baseDD = -1.4

  const isSimulated = simDrop > 0 || Math.abs(simVol - baseVol) > 1.0

  const activeIndex = isSimulated
    ? +(baseIndex * (1 - simDrop / 100)).toFixed(2)
    : baseIndex

  const activeChange = isSimulated
    ? +(-baseIndex * (simDrop / 100)).toFixed(2)
    : baseChange

  const activeChangePct = isSimulated
    ? +(-simDrop).toFixed(2)
    : baseChangePct

  const activeVol = isSimulated ? simVol : baseVol
  const activeDD = isSimulated ? +(-simDrop - 1.4).toFixed(1) : baseDD

  let activeRegime = 'Bull (Low Volatility)'
  let activeSignal = 'INVEST NOW'
  let regimeColor = 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20'

  if (activeVol >= 35) {
    activeRegime = 'Extreme Dislocation'
    activeSignal = 'WAIT / NO CLEAR SIGNAL'
    regimeColor = 'text-rose-400 bg-rose-500/10 border-rose-500/20'
  } else if (activeVol >= 25 || simDrop >= 15) {
    activeRegime = 'High Volatility Correction'
    activeSignal = 'INVEST GRADUALLY (4 Tranches)'
    regimeColor = 'text-amber-400 bg-amber-500/10 border-amber-500/20'
  } else if (simDrop >= 5 || activeVol >= 18) {
    activeRegime = 'Correction Pullback'
    activeSignal = 'INVEST GRADUALLY (3 Tranches)'
    regimeColor = 'text-teal-400 bg-teal-500/10 border-teal-500/20'
  }

  useEffect(() => {
    if (onSimulateStateChange) {
      onSimulateStateChange({
        isSimulated,
        marketDropPct: simDrop,
        volatilityPct: activeVol,
        simulatedIndex: activeIndex,
        simulatedRegime: activeRegime,
        simulatedSignal: activeSignal
      })
    }
  }, [isSimulated, simDrop, activeVol, activeIndex, activeRegime, activeSignal, onSimulateStateChange])

  const handleReset = () => {
    setSimDrop(0)
    setSimVol(baseVol)
  }

  return (
    <div className="w-full border-b border-white/[0.04] bg-navy-950/40 backdrop-blur-md sticky top-16 z-30 transition-all">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-2">
        {/* Minimalist Horizontal Ticker Strip */}
        <div className="flex flex-wrap items-center justify-between gap-2.5 text-xs">
          {/* Live Status Chip */}
          <div className="flex items-center space-x-2">
            <span className="relative flex h-2 w-2">
              <span
                className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${
                  isSimulated ? 'bg-amber-400' : 'bg-emerald-400'
                }`}
              />
              <span
                className={`relative inline-flex rounded-full h-2 w-2 ${
                  isSimulated ? 'bg-amber-500' : 'bg-emerald-500'
                }`}
              />
            </span>
            <span className="font-semibold text-slate-300 text-[11px] uppercase tracking-wider">
              {isSimulated ? 'Simulated Market Shock' : 'Live AMFI/NSE Pulse'}
            </span>
          </div>

          {/* Metric Stats Stream */}
          <div className="flex flex-wrap items-center gap-3 sm:gap-5 text-slate-400 text-[11px]">
            {/* Benchmark Level */}
            <div className="flex items-baseline space-x-1.5">
              <span className="text-slate-500">Nifty TRI</span>
              <span className="font-bold text-white tracking-tight">
                ₹{activeIndex.toLocaleString('en-IN', { maximumFractionDigits: 1 })}
              </span>
              <span
                className={`font-semibold ${
                  activeChange >= 0 ? 'text-emerald-400' : 'text-rose-400'
                }`}
              >
                {activeChange >= 0 ? '+' : ''}
                {activeChangePct}%
              </span>
            </div>

            <span className="text-slate-700 hidden sm:inline">•</span>

            {/* Regime */}
            <div className="hidden sm:flex items-center space-x-1.5">
              <span className="text-slate-500">Regime</span>
              <span className={`px-2 py-0.5 rounded-full border font-medium ${regimeColor}`}>
                {activeRegime}
              </span>
            </div>

            <span className="text-slate-700 hidden md:inline">•</span>

            {/* 30D Vol */}
            <div className="hidden md:flex items-center space-x-1.5">
              <span className="text-slate-500">30D Vol</span>
              <span className="font-semibold text-slate-200">{activeVol.toFixed(1)}%</span>
            </div>

            <span className="text-slate-700 hidden lg:inline">•</span>

            {/* Liquid Yield */}
            <div className="hidden lg:flex items-center space-x-1.5">
              <span className="text-slate-500">Liquid Yield</span>
              <span className="font-semibold text-teal-300">6.0% p.a.</span>
            </div>
          </div>

          {/* Simulator Toggle Button */}
          <div className="flex items-center space-x-2">
            <button
              onClick={() => setIsSimulatorOpen(!isSimulatorOpen)}
              className={`px-2.5 py-1 rounded-full text-[11px] font-medium flex items-center space-x-1 transition-all border ${
                isSimulated || isSimulatorOpen
                  ? 'bg-indigo-500/15 text-indigo-300 border-indigo-500/30'
                  : 'bg-slate-900/60 text-slate-400 border-white/[0.06] hover:text-white hover:border-white/[0.12]'
              }`}
            >
              <Sliders className="w-3 h-3 text-indigo-400" />
              <span>Stress Simulator</span>
              {isSimulatorOpen ? (
                <ChevronUp className="w-3 h-3" />
              ) : (
                <ChevronDown className="w-3 h-3" />
              )}
            </button>

            {isSimulated && (
              <button
                onClick={handleReset}
                className="p-1 text-slate-400 hover:text-white rounded-full hover:bg-white/[0.05] transition-colors"
                title="Reset simulation"
              >
                <RotateCcw className="w-3 h-3" />
              </button>
            )}
          </div>
        </div>

        {/* Minimalist Accordion Slider Drawer */}
        {isSimulatorOpen && (
          <div className="mt-3 pt-3 border-t border-white/[0.04] grid grid-cols-1 md:grid-cols-2 gap-4 animate-fade-in text-xs">
            <div className="space-y-1.5">
              <div className="flex justify-between font-medium text-slate-300 text-[11px]">
                <span>Simulate Market Drawdown:</span>
                <span className="text-rose-400 font-bold">-{simDrop}% Drop</span>
              </div>
              <input
                type="range"
                min="0"
                max="35"
                step="1"
                value={simDrop}
                onChange={(e) => setSimDrop(Number(e.target.value))}
                className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-rose-500"
              />
            </div>

            <div className="space-y-1.5">
              <div className="flex justify-between font-medium text-slate-300 text-[11px]">
                <span>Simulate Realized Volatility:</span>
                <span className="text-amber-400 font-bold">{simVol.toFixed(1)}% Vol</span>
              </div>
              <input
                type="range"
                min="10"
                max="45"
                step="0.5"
                value={simVol}
                onChange={(e) => setSimVol(Number(e.target.value))}
                className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-amber-500"
              />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
