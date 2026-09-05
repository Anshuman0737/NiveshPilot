import React, { useState, useEffect } from 'react'
import {
  Activity,
  TrendingUp,
  AlertTriangle,
  Sliders,
  RotateCcw,
  ShieldCheck,
  Zap,
  Info,
  ChevronDown,
  ChevronUp
} from 'lucide-react'

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
  // Live market baseline numbers (NSE Nifty 50 TRI)
  const BASELINE_INDEX = 25235.9
  const BASELINE_CHANGE = 142.3
  const BASELINE_PCT = 0.57
  const BASELINE_VOL = 12.8
  const BASELINE_DD = -1.4
  const BASELINE_REGIME = 'Bull (Low Volatility)'

  // Live tick simulation (gentle heartbeat every 4 seconds)
  const [tickOffset, setTickOffset] = useState<number>(0)
  const [lastTickTime, setLastTickTime] = useState<string>('')
  const [isSimulatorOpen, setIsSimulatorOpen] = useState<boolean>(false)

  // Simulation controls
  const [simDrop, setSimDrop] = useState<number>(0)
  const [simVol, setSimVol] = useState<number>(12.8)

  useEffect(() => {
    const updateTime = () => {
      const now = new Date()
      setLastTickTime(
        now.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
      )
    }
    updateTime()

    const interval = setInterval(() => {
      // Subtle micro-tick within ±0.03% to simulate live streaming quotes
      const microDrift = (Math.random() - 0.48) * 1.8
      setTickOffset((prev) => +(prev + microDrift).toFixed(2))
      updateTime()
    }, 4000)

    return () => clearInterval(interval)
  }, [])

  // Derived simulated figures
  const isSimulated = simDrop > 0 || Math.abs(simVol - BASELINE_VOL) > 1.0

  const activeIndex = isSimulated
    ? +(BASELINE_INDEX * (1 - simDrop / 100)).toFixed(2)
    : +(BASELINE_INDEX + tickOffset).toFixed(2)

  const activeChange = isSimulated
    ? +(-BASELINE_INDEX * (simDrop / 100)).toFixed(2)
    : +(BASELINE_CHANGE + tickOffset).toFixed(2)

  const activeChangePct = isSimulated
    ? +(-simDrop).toFixed(2)
    : +(BASELINE_PCT + (tickOffset / BASELINE_INDEX) * 100).toFixed(2)

  const activeVol = isSimulated ? simVol : BASELINE_VOL
  const activeDD = isSimulated ? +(-simDrop - 1.4).toFixed(1) : BASELINE_DD

  // Determine dynamic regime and signal based on stress inputs
  let activeRegime = BASELINE_REGIME
  let activeSignal = 'INVEST NOW'
  let regimeColor = 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10'

  if (activeVol >= 35) {
    activeRegime = 'Extreme Dislocation (Out of Distribution)'
    activeSignal = 'WAIT / NO CLEAR SIGNAL'
    regimeColor = 'text-rose-400 border-rose-500/30 bg-rose-500/10'
  } else if (activeVol >= 25 || simDrop >= 15) {
    activeRegime = 'High Volatility / Deep Correction'
    activeSignal = 'INVEST GRADUALLY (4 Tranches)'
    regimeColor = 'text-amber-400 border-amber-500/30 bg-amber-500/10'
  } else if (simDrop >= 5 || activeVol >= 18) {
    activeRegime = 'Correction (Pullback Opportunity)'
    activeSignal = 'INVEST GRADUALLY (3 Tranches)'
    regimeColor = 'text-teal-400 border-teal-500/30 bg-teal-500/10'
  }

  // Notify parent component if callback provided
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
    setSimVol(BASELINE_VOL)
  }

  return (
    <div className="w-full border-b border-slate-800 bg-slate-950/80 backdrop-blur-md sticky top-16 z-30 transition-colors">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-2.5">
        {/* Main Ticker Bar */}
        <div className="flex flex-wrap items-center justify-between gap-3 text-xs">
          {/* Live Status Pulse */}
          <div className="flex items-center space-x-2.5">
            <div className="relative flex h-2.5 w-2.5">
              <span
                className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${
                  isSimulated ? 'bg-amber-400' : 'bg-emerald-400'
                }`}
              />
              <span
                className={`relative inline-flex rounded-full h-2.5 w-2.5 ${
                  isSimulated ? 'bg-amber-500' : 'bg-emerald-500'
                }`}
              />
            </div>
            <div className="flex items-center space-x-1.5 font-semibold">
              <span className="text-white">
                {isSimulated ? 'SIMULATED STRESS TEST' : 'LIVE REGIME MONITOR'}
              </span>
              <span className="text-slate-500 hidden sm:inline">•</span>
              <span className="text-slate-400 hidden sm:inline">NSE NIFTY 50 TRI</span>
            </div>
          </div>

          {/* Key Live Figures Grid */}
          <div className="flex flex-wrap items-center gap-3 sm:gap-6">
            {/* Benchmark Level */}
            <div className="flex items-baseline space-x-1.5">
              <span className="text-slate-400 text-[11px]">Nifty TRI:</span>
              <span className="font-bold text-white tracking-tight">
                ₹{activeIndex.toLocaleString('en-IN', { maximumFractionDigits: 1 })}
              </span>
              <span
                className={`text-[11px] font-semibold flex items-center ${
                  activeChange >= 0 ? 'text-emerald-400' : 'text-rose-400'
                }`}
              >
                {activeChange >= 0 ? '+' : ''}
                {activeChange.toFixed(1)} ({activeChangePct >= 0 ? '+' : ''}
                {activeChangePct}%)
              </span>
            </div>

            {/* Market Regime Badge */}
            <div className="hidden md:flex items-center space-x-1.5">
              <span className="text-slate-400 text-[11px]">Regime:</span>
              <span
                className={`px-2 py-0.5 rounded-md border text-[11px] font-semibold ${regimeColor}`}
              >
                {activeRegime}
              </span>
            </div>

            {/* 30D Volatility */}
            <div className="hidden lg:flex items-center space-x-1.5">
              <span className="text-slate-400 text-[11px]">30D Vol:</span>
              <span
                className={`font-semibold text-[11px] ${
                  activeVol < 18
                    ? 'text-emerald-300'
                    : activeVol < 25
                    ? 'text-amber-300'
                    : 'text-rose-300'
                }`}
              >
                {activeVol.toFixed(1)}%
              </span>
            </div>

            {/* Drawdown */}
            <div className="hidden xl:flex items-center space-x-1.5">
              <span className="text-slate-400 text-[11px]">Peak DD:</span>
              <span className="font-semibold text-slate-200 text-[11px]">{activeDD}%</span>
            </div>

            {/* Liquid Yield */}
            <div className="hidden sm:flex items-center space-x-1.5">
              <span className="text-slate-400 text-[11px]">Cash Yield:</span>
              <span className="font-semibold text-teal-300 text-[11px]">6.0% p.a.</span>
            </div>

            {/* Simulator Toggle Button */}
            <button
              onClick={() => setIsSimulatorOpen(!isSimulatorOpen)}
              className={`px-2.5 py-1 rounded-lg font-semibold text-[11px] transition-all flex items-center space-x-1 border ${
                isSimulated
                  ? 'bg-amber-500/20 border-amber-500/40 text-amber-300 hover:bg-amber-500/30'
                  : 'bg-slate-900 border-slate-800 text-slate-300 hover:bg-slate-800 hover:text-white'
              }`}
            >
              <Zap className="w-3 h-3 text-amber-400" />
              <span>{isSimulated ? 'Simulating Shock' : 'Stress Simulator'}</span>
              {isSimulatorOpen ? (
                <ChevronUp className="w-3 h-3" />
              ) : (
                <ChevronDown className="w-3 h-3" />
              )}
            </button>
          </div>
        </div>

        {/* Expandable Live Shock Simulator Drawer */}
        {isSimulatorOpen && (
          <div className="mt-3 pt-3 border-t border-slate-800/80 bg-slate-900/90 rounded-xl p-4 shadow-xl border border-slate-800 animate-fadeIn">
            <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 mb-4">
              <div>
                <div className="flex items-center space-x-2">
                  <Zap className="w-4 h-4 text-amber-400" />
                  <h4 className="text-sm font-bold text-white">
                    Live Market Stress & Regime Response Simulator
                  </h4>
                </div>
                <p className="text-xs text-slate-400 mt-0.5">
                  Test how NiveshPilot dynamically alters its deployment signal, tranches, and risk
                  containment in response to hypothetical market drops and volatility shocks.
                </p>
              </div>

              {isSimulated && (
                <button
                  onClick={handleReset}
                  className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold flex items-center space-x-1.5 transition-all shrink-0 border border-slate-700"
                >
                  <RotateCcw className="w-3 h-3 text-amber-400" />
                  <span>Reset to Live Baseline</span>
                </button>
              )}
            </div>

            {/* Sliders Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Slider 1: Market Pullback */}
              <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800">
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-xs font-semibold text-slate-300">
                    Simulated Market Drop from Peak
                  </label>
                  <span
                    className={`font-bold text-xs ${
                      simDrop === 0
                        ? 'text-slate-400'
                        : simDrop < 10
                        ? 'text-amber-400'
                        : 'text-rose-400'
                    }`}
                  >
                    {simDrop === 0 ? '0% (Normal)' : `-${simDrop}%`}
                  </span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="35"
                  step="1"
                  value={simDrop}
                  onChange={(e) => setSimDrop(Number(e.target.value))}
                  className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-amber-500"
                />
                <div className="flex justify-between text-[10px] text-slate-500 mt-1">
                  <span>0% (Peak)</span>
                  <span>-10% (Correction)</span>
                  <span>-20% (Bear)</span>
                  <span>-35% (Crash)</span>
                </div>
              </div>

              {/* Slider 2: Volatility Shock */}
              <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800">
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-xs font-semibold text-slate-300">
                    Simulated 30-Day Realized Volatility
                  </label>
                  <span
                    className={`font-bold text-xs ${
                      simVol < 18
                        ? 'text-emerald-400'
                        : simVol < 25
                        ? 'text-amber-400'
                        : 'text-rose-400'
                    }`}
                  >
                    {simVol.toFixed(1)}% annualized
                  </span>
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
                <div className="flex justify-between text-[10px] text-slate-500 mt-1">
                  <span>10% (Calm)</span>
                  <span>18% (Moderate)</span>
                  <span>28% (High)</span>
                  <span>45% (Panic)</span>
                </div>
              </div>
            </div>

            {/* Dynamic Real-Time Reaction Banner */}
            <div className="mt-3 p-3 rounded-xl bg-slate-950/80 border border-slate-800 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
              <div className="flex items-center space-x-2">
                <span className="text-slate-400">Dynamic Response:</span>
                <span
                  className={`px-2.5 py-1 rounded-lg font-bold border text-xs ${
                    activeSignal.includes('NOW')
                      ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                      : activeSignal.includes('GRADUALLY')
                      ? 'bg-teal-500/20 text-teal-300 border-teal-500/40'
                      : 'bg-rose-500/20 text-rose-300 border-rose-500/40'
                  }`}
                >
                  {activeSignal}
                </span>
              </div>

              <div className="text-slate-400 text-[11px] leading-relaxed">
                {activeSignal.includes('NOW') &&
                  'Normal market: High upfront deployment (70%) with a 30% liquid yield buffer.'}
                {activeSignal.includes('GRADUALLY (3') &&
                  'Dip detected: 40% initial deployment, staggering 60% across 3 tranches to average down.'}
                {activeSignal.includes('GRADUALLY (4') &&
                  'Elevated turbulence: Defensive 25% x 4 deployment schedule preserves cash in liquid safety.'}
                {activeSignal.includes('WAIT') &&
                  'Extreme volatility (>35%): Out of historical distribution. Capital halted in liquid safety.'}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
