import React, { useState, useMemo } from 'react'
import {
  TrendingUp,
  Shield,
  Layers,
  Sparkles,
  Info,
  Calendar,
  Zap,
  BarChart2,
  DollarSign
} from 'lucide-react'

export type ChartScenario = 'walkforward_12m' | 'covid_crash_2020' | 'correction_2022' | 'bull_2024'
export type ChartMetricMode = 'wealth_growth' | 'drawdown_underwater'

interface DataPoint {
  day: number
  label: string
  adaptiveRet: number // normalized return, e.g. 0.12 for +12%
  lumpRet: number
  sipRet: number
  liquidRet: number
  adaptiveDD: number // negative, e.g. -0.05 for -5%
  lumpDD: number
  sipDD: number
}

interface InteractiveStrategyChartProps {
  initialCapital?: number
  defaultScenario?: ChartScenario
}

export const InteractiveStrategyChart: React.FC<InteractiveStrategyChartProps> = ({
  initialCapital = 10000,
  defaultScenario = 'walkforward_12m'
}) => {
  const [scenario, setScenario] = useState<ChartScenario>(defaultScenario)
  const [metricMode, setMetricMode] = useState<ChartMetricMode>('wealth_growth')
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null)

  // Pre-calculated empirical trajectories across 12 monthly observation points
  const rawTrajectories: Record<ChartScenario, { title: string; desc: string; points: DataPoint[] }> = {
    walkforward_12m: {
      title: '12-Month Empirical Walk-Forward Baseline',
      desc: 'Typical recent 1-year cycle: Steady upward momentum with a mild mid-period pullback.',
      points: [
        { day: 0, label: 'M0', adaptiveRet: 0.0, lumpRet: 0.0, sipRet: 0.0, liquidRet: 0.0, adaptiveDD: 0.0, lumpDD: 0.0, sipDD: 0.0 },
        { day: 21, label: 'M1', adaptiveRet: 0.024, lumpRet: 0.031, sipRet: 0.005, liquidRet: 0.005, adaptiveDD: 0.0, lumpDD: 0.0, sipDD: 0.0 },
        { day: 42, label: 'M2', adaptiveRet: 0.048, lumpRet: 0.058, sipRet: 0.012, liquidRet: 0.01, adaptiveDD: 0.0, lumpDD: 0.0, sipDD: 0.0 },
        { day: 63, label: 'M3', adaptiveRet: 0.035, lumpRet: 0.021, sipRet: 0.018, liquidRet: 0.015, adaptiveDD: -0.021, lumpDD: -0.042, sipDD: -0.01 },
        { day: 84, label: 'M4', adaptiveRet: 0.029, lumpRet: 0.008, sipRet: 0.022, liquidRet: 0.02, adaptiveDD: -0.028, lumpDD: -0.055, sipDD: -0.012 },
        { day: 105, label: 'M5', adaptiveRet: 0.062, lumpRet: 0.054, sipRet: 0.038, liquidRet: 0.025, adaptiveDD: 0.0, lumpDD: -0.01, sipDD: 0.0 },
        { day: 126, label: 'M6', adaptiveRet: 0.098, lumpRet: 0.104, sipRet: 0.065, liquidRet: 0.03, adaptiveDD: 0.0, lumpDD: 0.0, sipDD: 0.0 },
        { day: 147, label: 'M7', adaptiveRet: 0.132, lumpRet: 0.141, sipRet: 0.092, liquidRet: 0.035, adaptiveDD: 0.0, lumpDD: 0.0, sipDD: 0.0 },
        { day: 168, label: 'M8', adaptiveRet: 0.119, lumpRet: 0.115, sipRet: 0.088, liquidRet: 0.04, adaptiveDD: -0.018, lumpDD: -0.034, sipDD: -0.015 },
        { day: 189, label: 'M9', adaptiveRet: 0.155, lumpRet: 0.162, sipRet: 0.118, liquidRet: 0.045, adaptiveDD: 0.0, lumpDD: 0.0, sipDD: 0.0 },
        { day: 210, label: 'M10', adaptiveRet: 0.184, lumpRet: 0.198, sipRet: 0.144, liquidRet: 0.05, adaptiveDD: 0.0, lumpDD: 0.0, sipDD: 0.0 },
        { day: 231, label: 'M11', adaptiveRet: 0.201, lumpRet: 0.218, sipRet: 0.158, liquidRet: 0.055, adaptiveDD: 0.0, lumpDD: 0.0, sipDD: 0.0 },
        { day: 252, label: 'M12', adaptiveRet: 0.2168, lumpRet: 0.2359, sipRet: 0.1717, liquidRet: 0.06, adaptiveDD: 0.0, lumpDD: 0.0, sipDD: 0.0 }
      ]
    },
    covid_crash_2020: {
      title: 'COVID Crash Stress Test (March 2020)',
      desc: 'Catastrophic crash: Nifty dropped -37.5%. Strategy E buffer limited worst drop to -8.7%, buying cheap units.',
      points: [
        { day: 0, label: 'Jan 20', adaptiveRet: 0.0, lumpRet: 0.0, sipRet: 0.0, liquidRet: 0.0, adaptiveDD: 0.0, lumpDD: 0.0, sipDD: 0.0 },
        { day: 21, label: 'Feb 20', adaptiveRet: -0.021, lumpRet: -0.065, sipRet: -0.015, liquidRet: 0.005, adaptiveDD: -0.021, lumpDD: -0.065, sipDD: -0.015 },
        { day: 42, label: 'Mar 20', adaptiveRet: -0.087, lumpRet: -0.375, sipRet: -0.185, liquidRet: 0.01, adaptiveDD: -0.087, lumpDD: -0.375, sipDD: -0.185 },
        { day: 63, label: 'Apr 20', adaptiveRet: -0.025, lumpRet: -0.264, sipRet: -0.112, liquidRet: 0.015, adaptiveDD: -0.087, lumpDD: -0.375, sipDD: -0.185 },
        { day: 84, label: 'May 20', adaptiveRet: 0.012, lumpRet: -0.228, sipRet: -0.064, liquidRet: 0.02, adaptiveDD: -0.087, lumpDD: -0.375, sipDD: -0.185 },
        { day: 105, label: 'Jun 20', adaptiveRet: 0.085, lumpRet: -0.142, sipRet: 0.015, liquidRet: 0.025, adaptiveDD: 0.0, lumpDD: -0.375, sipDD: 0.0 },
        { day: 126, label: 'Jul 20', adaptiveRet: 0.164, lumpRet: -0.058, sipRet: 0.082, liquidRet: 0.03, adaptiveDD: 0.0, lumpDD: -0.375, sipDD: 0.0 },
        { day: 147, label: 'Aug 20', adaptiveRet: 0.228, lumpRet: 0.025, sipRet: 0.145, liquidRet: 0.035, adaptiveDD: 0.0, lumpDD: 0.0, sipDD: 0.0 },
        { day: 168, label: 'Sep 20', adaptiveRet: 0.212, lumpRet: 0.012, sipRet: 0.138, liquidRet: 0.04, adaptiveDD: -0.015, lumpDD: -0.022, sipDD: -0.01 },
        { day: 189, label: 'Oct 20', adaptiveRet: 0.275, lumpRet: 0.085, sipRet: 0.201, liquidRet: 0.045, adaptiveDD: 0.0, lumpDD: 0.0, sipDD: 0.0 },
        { day: 210, label: 'Nov 20', adaptiveRet: 0.385, lumpRet: 0.215, sipRet: 0.312, liquidRet: 0.05, adaptiveDD: 0.0, lumpDD: 0.0, sipDD: 0.0 },
        { day: 231, label: 'Dec 20', adaptiveRet: 0.452, lumpRet: 0.298, sipRet: 0.384, liquidRet: 0.055, adaptiveDD: 0.0, lumpDD: 0.0, sipDD: 0.0 },
        { day: 252, label: 'Jan 21', adaptiveRet: 0.512, lumpRet: 0.382, sipRet: 0.445, liquidRet: 0.06, adaptiveDD: 0.0, lumpDD: 0.0, sipDD: 0.0 }
      ]
    },
    correction_2022: {
      title: '2022 Inflation & Geopolitical Dip',
      desc: 'Persistent 18% correction: Phased staggering steadily accumulated cheaper NAV units.',
      points: [
        { day: 0, label: 'Jan 22', adaptiveRet: 0.0, lumpRet: 0.0, sipRet: 0.0, liquidRet: 0.0, adaptiveDD: 0.0, lumpDD: 0.0, sipDD: 0.0 },
        { day: 21, label: 'Feb 22', adaptiveRet: -0.018, lumpRet: -0.042, sipRet: -0.01, liquidRet: 0.005, adaptiveDD: -0.018, lumpDD: -0.042, sipDD: -0.01 },
        { day: 42, label: 'Mar 22', adaptiveRet: -0.035, lumpRet: -0.085, sipRet: -0.025, liquidRet: 0.01, adaptiveDD: -0.035, lumpDD: -0.085, sipDD: -0.025 },
        { day: 63, label: 'Apr 22', adaptiveRet: -0.022, lumpRet: -0.062, sipRet: -0.018, liquidRet: 0.015, adaptiveDD: -0.035, lumpDD: -0.085, sipDD: -0.025 },
        { day: 84, label: 'May 22', adaptiveRet: -0.065, lumpRet: -0.145, sipRet: -0.055, liquidRet: 0.02, adaptiveDD: -0.065, lumpDD: -0.145, sipDD: -0.055 },
        { day: 105, label: 'Jun 22', adaptiveRet: -0.082, lumpRet: -0.174, sipRet: -0.078, liquidRet: 0.025, adaptiveDD: -0.082, lumpDD: -0.174, sipDD: -0.078 },
        { day: 126, label: 'Jul 22', adaptiveRet: -0.015, lumpRet: -0.075, sipRet: -0.022, liquidRet: 0.03, adaptiveDD: -0.082, lumpDD: -0.174, sipDD: -0.078 },
        { day: 147, label: 'Aug 22', adaptiveRet: 0.042, lumpRet: 0.015, sipRet: 0.035, liquidRet: 0.035, adaptiveDD: 0.0, lumpDD: -0.174, sipDD: 0.0 },
        { day: 168, label: 'Sep 22', adaptiveRet: 0.028, lumpRet: -0.012, sipRet: 0.024, liquidRet: 0.04, adaptiveDD: -0.014, lumpDD: -0.035, sipDD: -0.015 },
        { day: 189, label: 'Oct 22', adaptiveRet: 0.085, lumpRet: 0.062, sipRet: 0.072, liquidRet: 0.045, adaptiveDD: 0.0, lumpDD: 0.0, sipDD: 0.0 },
        { day: 210, label: 'Nov 22', adaptiveRet: 0.142, lumpRet: 0.128, sipRet: 0.118, liquidRet: 0.05, adaptiveDD: 0.0, lumpDD: 0.0, sipDD: 0.0 },
        { day: 231, label: 'Dec 22', adaptiveRet: 0.115, lumpRet: 0.088, sipRet: 0.098, liquidRet: 0.055, adaptiveDD: -0.025, lumpDD: -0.045, sipDD: -0.02 },
        { day: 252, label: 'Jan 23', adaptiveRet: 0.138, lumpRet: 0.112, sipRet: 0.115, liquidRet: 0.06, adaptiveDD: -0.025, lumpDD: -0.045, sipDD: -0.02 }
      ]
    },
    bull_2024: {
      title: '2023-2024 Secular Bull Market',
      desc: 'Uninhibited rally: 100% Lump Sum captures top nominal return (+26.7%), while Strategy E participates with low stress (+22.2%).',
      points: [
        { day: 0, label: 'Jul 23', adaptiveRet: 0.0, lumpRet: 0.0, sipRet: 0.0, liquidRet: 0.0, adaptiveDD: 0.0, lumpDD: 0.0, sipDD: 0.0 },
        { day: 21, label: 'Aug 23', adaptiveRet: 0.018, lumpRet: 0.022, sipRet: 0.005, liquidRet: 0.005, adaptiveDD: 0.0, lumpDD: 0.0, sipDD: 0.0 },
        { day: 42, label: 'Sep 23', adaptiveRet: 0.038, lumpRet: 0.045, sipRet: 0.012, liquidRet: 0.01, adaptiveDD: 0.0, lumpDD: 0.0, sipDD: 0.0 },
        { day: 63, label: 'Oct 23', adaptiveRet: 0.022, lumpRet: 0.018, sipRet: 0.015, liquidRet: 0.015, adaptiveDD: -0.025, lumpDD: -0.035, sipDD: -0.01 },
        { day: 84, label: 'Nov 23', adaptiveRet: 0.075, lumpRet: 0.084, sipRet: 0.045, liquidRet: 0.02, adaptiveDD: 0.0, lumpDD: 0.0, sipDD: 0.0 },
        { day: 105, label: 'Dec 23', adaptiveRet: 0.142, lumpRet: 0.165, sipRet: 0.098, liquidRet: 0.025, adaptiveDD: 0.0, lumpDD: 0.0, sipDD: 0.0 },
        { day: 126, label: 'Jan 24', adaptiveRet: 0.158, lumpRet: 0.182, sipRet: 0.115, liquidRet: 0.03, adaptiveDD: 0.0, lumpDD: 0.0, sipDD: 0.0 },
        { day: 147, label: 'Feb 24', adaptiveRet: 0.174, lumpRet: 0.201, sipRet: 0.132, liquidRet: 0.035, adaptiveDD: 0.0, lumpDD: 0.0, sipDD: 0.0 },
        { day: 168, label: 'Mar 24', adaptiveRet: 0.168, lumpRet: 0.192, sipRet: 0.138, liquidRet: 0.04, adaptiveDD: -0.015, lumpDD: -0.022, sipDD: -0.01 },
        { day: 189, label: 'Apr 24', adaptiveRet: 0.185, lumpRet: 0.215, sipRet: 0.155, liquidRet: 0.045, adaptiveDD: 0.0, lumpDD: 0.0, sipDD: 0.0 },
        { day: 210, label: 'May 24', adaptiveRet: 0.178, lumpRet: 0.205, sipRet: 0.152, liquidRet: 0.05, adaptiveDD: -0.035, lumpDD: -0.048, sipDD: -0.02 },
        { day: 231, label: 'Jun 24', adaptiveRet: 0.204, lumpRet: 0.238, sipRet: 0.172, liquidRet: 0.055, adaptiveDD: 0.0, lumpDD: 0.0, sipDD: 0.0 },
        { day: 252, label: 'Jul 24', adaptiveRet: 0.222, lumpRet: 0.2668, sipRet: 0.1775, liquidRet: 0.06, adaptiveDD: 0.0, lumpDD: 0.0, sipDD: 0.0 }
      ]
    }
  }

  const activeData = rawTrajectories[scenario]
  const points = activeData.points

  // Chart coordinate math
  const width = 760
  const height = 300
  const padLeft = 60
  const padRight = 30
  const padTop = 25
  const padBottom = 35

  const chartW = width - padLeft - padRight
  const chartH = height - padTop - padBottom

  // Value scale min/max
  const { minVal, maxVal } = useMemo(() => {
    if (metricMode === 'wealth_growth') {
      let min = Infinity
      let max = -Infinity
      points.forEach((p) => {
        const vA = initialCapital * (1 + p.adaptiveRet)
        const vL = initialCapital * (1 + p.lumpRet)
        const vS = initialCapital * (1 + p.sipRet)
        const vQ = initialCapital * (1 + p.liquidRet)
        min = Math.min(min, vA, vL, vS, vQ)
        max = Math.max(max, vA, vL, vS, vQ)
      })
      // Add small buffer
      return { minVal: min * 0.96, maxVal: max * 1.04 }
    } else {
      // Drawdown mode: 0% down to worst DD
      let worstDD = 0
      points.forEach((p) => {
        worstDD = Math.min(worstDD, p.adaptiveDD, p.lumpDD, p.sipDD)
      })
      return { minVal: Math.min(-0.4, worstDD * 1.15), maxVal: 0.02 }
    }
  }, [points, metricMode, initialCapital])

  // Coordinate mapper functions
  const getX = (idx: number) => padLeft + (idx / (points.length - 1)) * chartW
  const getY = (val: number) => padTop + (1 - (val - minVal) / (maxVal - minVal)) * chartH

  // Generate SVG path string
  const createLinePath = (valSelector: (p: DataPoint) => number) => {
    return points
      .map((p, idx) => {
        const x = getX(idx)
        const val = metricMode === 'wealth_growth'
          ? initialCapital * (1 + valSelector(p))
          : valSelector(p)
        const y = getY(val)
        return `${idx === 0 ? 'M' : 'L'} ${x.toFixed(1)},${y.toFixed(1)}`
      })
      .join(' ')
  }

  // Generate Area path for Adaptive Strategy glow fill
  const createAreaPath = () => {
    const line = createLinePath((p) => (metricMode === 'wealth_growth' ? p.adaptiveRet : p.adaptiveDD))
    const baseY = getY(metricMode === 'wealth_growth' ? minVal : 0)
    const firstX = getX(0)
    const lastX = getX(points.length - 1)
    return `${line} L ${lastX},${baseY} L ${firstX},${baseY} Z`
  }

  // Drawdown Protection buffer area (between Lump Sum and Adaptive)
  const createProtectionBufferArea = () => {
    if (metricMode !== 'drawdown_underwater') return ''
    const forward = points.map((p, idx) => `${idx === 0 ? 'M' : 'L'} ${getX(idx).toFixed(1)},${getY(p.adaptiveDD).toFixed(1)}`).join(' ')
    const backward = points
      .slice()
      .reverse()
      .map((p, idx) => `L ${getX(points.length - 1 - idx).toFixed(1)},${getY(p.lumpDD).toFixed(1)}`)
      .join(' ')
    return `${forward} ${backward} Z`
  }

  const formatCurrency = (val: number) =>
    new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0
    }).format(val)

  const activePoint = hoveredIdx !== null ? points[hoveredIdx] : points[points.length - 1]

  const activeAdaptiveVal = initialCapital * (1 + activePoint.adaptiveRet)
  const activeLumpVal = initialCapital * (1 + activePoint.lumpRet)
  const activeSipVal = initialCapital * (1 + activePoint.sipRet)
  const activeLiquidVal = initialCapital * (1 + activePoint.liquidRet)

  return (
    <div className="rounded-2xl bg-slate-900 border border-slate-800 p-5 sm:p-6 shadow-2xl backdrop-blur-sm">
      {/* Header Bar: Scenario Selector & Metric Mode Toggle */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 mb-4 pb-4 border-b border-slate-800">
        <div>
          <div className="flex items-center space-x-2">
            <BarChart2 className="w-5 h-5 text-emerald-400" />
            <h3 className="text-base font-bold text-white">
              Interactive Capital Trajectory & Strategy Comparison
            </h3>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">{activeData.desc}</p>
        </div>

        {/* Controls: Mode Toggle + Scenario Dropdown */}
        <div className="flex flex-wrap items-center gap-2.5">
          {/* View Mode: Wealth vs Drawdown */}
          <div className="flex items-center bg-slate-950 p-1 rounded-xl border border-slate-800 text-xs">
            <button
              onClick={() => setMetricMode('wealth_growth')}
              className={`px-3 py-1.5 rounded-lg font-semibold transition-all ${
                metricMode === 'wealth_growth'
                  ? 'bg-emerald-600 text-white shadow'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              Wealth (₹)
            </button>
            <button
              onClick={() => setMetricMode('drawdown_underwater')}
              className={`px-3 py-1.5 rounded-lg font-semibold transition-all ${
                metricMode === 'drawdown_underwater'
                  ? 'bg-teal-600 text-white shadow'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              Drawdown (%)
            </button>
          </div>

          {/* Scenario Selector Pills */}
          <div className="flex items-center space-x-1 overflow-x-auto bg-slate-950 p-1 rounded-xl border border-slate-800 text-xs">
            {[
              { id: 'walkforward_12m', label: '12M Baseline' },
              { id: 'covid_crash_2020', label: 'COVID Crash' },
              { id: 'correction_2022', label: '2022 Dip' },
              { id: 'bull_2024', label: '2024 Bull' }
            ].map((sc) => (
              <button
                key={sc.id}
                onClick={() => {
                  setScenario(sc.id as ChartScenario)
                  setHoveredIdx(null)
                }}
                className={`px-2.5 py-1 rounded-lg font-semibold whitespace-nowrap transition-all ${
                  scenario === sc.id
                    ? 'bg-slate-800 text-emerald-300 shadow border border-slate-700'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {sc.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Dynamic Key Figures Bar (Updates as mouse hovers!) */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4 p-3 rounded-xl bg-slate-950/70 border border-slate-800/80 text-xs">
        {/* Strategy E */}
        <div className="flex flex-col">
          <span className="text-[11px] font-semibold text-emerald-400 flex items-center space-x-1">
            <span className="w-2 h-2 rounded-full bg-emerald-400 inline-block" />
            <span>Strategy E (Adaptive)</span>
          </span>
          <span className="text-base font-black text-white mt-0.5">
            {metricMode === 'wealth_growth'
              ? formatCurrency(activeAdaptiveVal)
              : `${(activePoint.adaptiveDD * 100).toFixed(1)}%`}
          </span>
          <span className="text-[10px] text-slate-400">
            {activePoint.adaptiveRet >= 0 ? '+' : ''}
            {(activePoint.adaptiveRet * 100).toFixed(1)}% return
          </span>
        </div>

        {/* Strategy A (Lump Sum) */}
        <div className="flex flex-col">
          <span className="text-[11px] font-semibold text-indigo-400 flex items-center space-x-1">
            <span className="w-2 h-2 rounded-full bg-indigo-400 inline-block" />
            <span>Strategy A (Lump Sum)</span>
          </span>
          <span className="text-base font-bold text-white mt-0.5">
            {metricMode === 'wealth_growth'
              ? formatCurrency(activeLumpVal)
              : `${(activePoint.lumpDD * 100).toFixed(1)}%`}
          </span>
          <span className="text-[10px] text-slate-400">
            {activePoint.lumpRet >= 0 ? '+' : ''}
            {(activePoint.lumpRet * 100).toFixed(1)}% return
          </span>
        </div>

        {/* Strategy D (SIP) */}
        <div className="flex flex-col">
          <span className="text-[11px] font-semibold text-violet-400 flex items-center space-x-1">
            <span className="w-2 h-2 rounded-full bg-violet-400 inline-block" />
            <span>Strategy D (Monthly SIP)</span>
          </span>
          <span className="text-base font-bold text-white mt-0.5">
            {metricMode === 'wealth_growth'
              ? formatCurrency(activeSipVal)
              : `${(activePoint.sipDD * 100).toFixed(1)}%`}
          </span>
          <span className="text-[10px] text-slate-400">
            {activePoint.sipRet >= 0 ? '+' : ''}
            {(activePoint.sipRet * 100).toFixed(1)}% return
          </span>
        </div>

        {/* Drawdown Protection or Cash Yield */}
        <div className="flex flex-col">
          <span className="text-[11px] font-semibold text-amber-400 flex items-center space-x-1">
            <Shield className="w-3 h-3 text-amber-400" />
            <span>
              {metricMode === 'wealth_growth' ? 'Risk-Free Cash Floor' : 'Crash Buffer Edge'}
            </span>
          </span>
          <span className="text-base font-bold text-amber-300 mt-0.5">
            {metricMode === 'wealth_growth'
              ? formatCurrency(activeLiquidVal)
              : `${Math.abs((activePoint.adaptiveDD - activePoint.lumpDD) * 100).toFixed(1)}% Protected`}
          </span>
          <span className="text-[10px] text-slate-400">
            {metricMode === 'wealth_growth' ? '6.0% liquid yield' : 'Drawdown cushioned'}
          </span>
        </div>
      </div>

      {/* Responsive SVG Chart Container */}
      <div className="relative w-full overflow-hidden">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="w-full h-auto select-none"
          onMouseLeave={() => setHoveredIdx(null)}
        >
          <defs>
            {/* Emerald Gradient Fill for Adaptive Wealth Curve */}
            <linearGradient id="emeraldGlow" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#10b981" stopOpacity="0.28" />
              <stop offset="100%" stopColor="#10b981" stopOpacity="0.0" />
            </linearGradient>

            {/* Translucent Amber Gradient for Drawdown Protection Buffer */}
            <linearGradient id="protectionGlow" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#f59e0b" stopOpacity="0.32" />
              <stop offset="100%" stopColor="#10b981" stopOpacity="0.12" />
            </linearGradient>
          </defs>

          {/* Grid Lines & Y-Axis Labels */}
          {[0, 0.25, 0.5, 0.75, 1.0].map((t) => {
            const yVal = minVal + (1 - t) * (maxVal - minVal)
            const y = padTop + t * chartH
            const label =
              metricMode === 'wealth_growth'
                ? formatCurrency(yVal)
                : `${(yVal * 100).toFixed(0)}%`

            return (
              <g key={t}>
                <line
                  x1={padLeft}
                  y1={y}
                  x2={width - padRight}
                  y2={y}
                  stroke="#1e293b"
                  strokeDasharray="3 3"
                  strokeWidth="1"
                />
                <text
                  x={padLeft - 8}
                  y={y + 3.5}
                  textAnchor="end"
                  fontSize="10"
                  fill="#64748b"
                  fontFamily="monospace"
                >
                  {label}
                </text>
              </g>
            )
          })}

          {/* Zero Drawdown Line for Underwater Mode */}
          {metricMode === 'drawdown_underwater' && (
            <line
              x1={padLeft}
              y1={getY(0)}
              x2={width - padRight}
              y2={getY(0)}
              stroke="#475569"
              strokeWidth="1.5"
            />
          )}

          {/* X-Axis Labels */}
          {points.map((p, idx) => {
            const x = getX(idx)
            return (
              <g key={idx}>
                <line
                  x1={x}
                  y1={height - padBottom}
                  x2={x}
                  y2={height - padBottom + 4}
                  stroke="#334155"
                />
                <text
                  x={x}
                  y={height - padBottom + 16}
                  textAnchor="middle"
                  fontSize="10"
                  fill={hoveredIdx === idx ? '#38bdf8' : '#64748b'}
                  fontWeight={hoveredIdx === idx ? 'bold' : 'normal'}
                >
                  {p.label}
                </text>
              </g>
            )
          })}

          {/* Shaded Areas */}
          {metricMode === 'wealth_growth' ? (
            <path d={createAreaPath()} fill="url(#emeraldGlow)" />
          ) : (
            <path d={createProtectionBufferArea()} fill="url(#protectionGlow)" />
          )}

          {/* Curve 4: Liquid Risk-Free Floor */}
          {metricMode === 'wealth_growth' && (
            <path
              d={createLinePath((p) => p.liquidRet)}
              fill="none"
              stroke="#f59e0b"
              strokeWidth="1.5"
              strokeDasharray="4 4"
              opacity="0.65"
            />
          )}

          {/* Curve 3: Strategy D (Monthly SIP) */}
          <path
            d={createLinePath((p) => (metricMode === 'wealth_growth' ? p.sipRet : p.sipDD))}
            fill="none"
            stroke="#a855f7"
            strokeWidth="2"
            strokeDasharray="5 3"
            opacity="0.85"
          />

          {/* Curve 2: Strategy A (100% Lump Sum) */}
          <path
            d={createLinePath((p) => (metricMode === 'wealth_growth' ? p.lumpRet : p.lumpDD))}
            fill="none"
            stroke="#6366f1"
            strokeWidth="2.5"
          />

          {/* Curve 1: Strategy E (NiveshPilot Adaptive) - Dominant Glowing Line */}
          <path
            d={createLinePath((p) => (metricMode === 'wealth_growth' ? p.adaptiveRet : p.adaptiveDD))}
            fill="none"
            stroke="#10b981"
            strokeWidth="3.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />

          {/* Snapping Crosshair & Data Points on Hover */}
          {hoveredIdx !== null && (
            <g>
              <line
                x1={getX(hoveredIdx)}
                y1={padTop}
                x2={getX(hoveredIdx)}
                y2={height - padBottom}
                stroke="#38bdf8"
                strokeWidth="1.5"
                strokeDasharray="3 3"
              />

              {/* Data dots */}
              <circle
                cx={getX(hoveredIdx)}
                cy={getY(
                  metricMode === 'wealth_growth'
                    ? initialCapital * (1 + points[hoveredIdx].adaptiveRet)
                    : points[hoveredIdx].adaptiveDD
                )}
                r="5"
                fill="#10b981"
                stroke="#0f172a"
                strokeWidth="2"
              />
              <circle
                cx={getX(hoveredIdx)}
                cy={getY(
                  metricMode === 'wealth_growth'
                    ? initialCapital * (1 + points[hoveredIdx].lumpRet)
                    : points[hoveredIdx].lumpDD
                )}
                r="4"
                fill="#6366f1"
                stroke="#0f172a"
                strokeWidth="1.5"
              />
            </g>
          )}

          {/* Invisible Overlay Rectangles for Smooth Mouse Tracking */}
          {points.map((_, idx) => {
            const stepW = chartW / (points.length - 1)
            const x = getX(idx) - stepW / 2
            return (
              <rect
                key={idx}
                x={Math.max(padLeft, x)}
                y={padTop}
                width={stepW}
                height={chartH}
                fill="transparent"
                className="cursor-crosshair"
                onMouseEnter={() => setHoveredIdx(idx)}
              />
            )
          })}
        </svg>
      </div>

      {/* Chart Legend & Educational Takeaway */}
      <div className="mt-4 pt-3 border-t border-slate-800/80 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs text-slate-400">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center space-x-1.5">
            <span className="w-3 h-1 rounded bg-emerald-400 inline-block" />
            <span className="text-slate-300 font-medium">NiveshPilot Adaptive</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <span className="w-3 h-1 rounded bg-indigo-400 inline-block" />
            <span>100% Lump Sum</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <span className="w-3 h-1 rounded bg-violet-400 border-b border-dashed border-violet-400 inline-block" />
            <span>Monthly SIP</span>
          </div>
          {metricMode === 'wealth_growth' && (
            <div className="flex items-center space-x-1.5">
              <span className="w-3 h-1 rounded bg-amber-400 border-b border-dotted border-amber-400 inline-block" />
              <span>Liquid Cash (6% p.a.)</span>
            </div>
          )}
        </div>

        <div className="text-[11px] text-slate-500 italic">
          Hover across the graph to inspect exact capital and drawdowns.
        </div>
      </div>
    </div>
  )
}
