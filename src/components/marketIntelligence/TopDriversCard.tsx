import React from 'react'
import { PlusCircle, MinusCircle, HelpCircle, ArrowRight } from 'lucide-react'

interface TopDriversCardProps {
  topBullishDrivers: string[]
  topBearishDrivers: string[]
  counterfactualText?: string
}

export const TopDriversCard: React.FC<TopDriversCardProps> = ({
  topBullishDrivers,
  topBearishDrivers,
  counterfactualText = 'Baseline forecast was Bullish 54%; recent positive revenue surprise and relative strength widened conviction by +12 percentage points.'
}) => {
  return (
    <div className="p-6 rounded-3xl bg-slate-900/80 border border-white/[0.08] shadow-2xl space-y-4">
      <div className="pb-3 border-b border-white/[0.06]">
        <span className="text-[10px] uppercase font-bold tracking-widest text-emerald-400">
          Evidentiary Attribution
        </span>
        <h3 className="text-base font-bold text-white mt-0.5">
          Top Bullish & Bearish Signal Drivers
        </h3>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Bullish Drivers */}
        <div className="p-4 rounded-2xl bg-emerald-500/[0.03] border border-emerald-500/20 space-y-2.5">
          <div className="flex items-center space-x-1.5 text-xs font-bold text-emerald-400">
            <PlusCircle className="w-4 h-4 shrink-0" />
            <span>Top Bullish Evidence</span>
          </div>
          <ul className="space-y-2 text-xs text-slate-300">
            {topBullishDrivers.map((d, i) => (
              <li key={i} className="flex items-start space-x-2">
                <span className="text-emerald-500 font-bold shrink-0">•</span>
                <span>{d}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Bearish Drivers */}
        <div className="p-4 rounded-2xl bg-rose-500/[0.03] border border-rose-500/20 space-y-2.5">
          <div className="flex items-center space-x-1.5 text-xs font-bold text-rose-400">
            <MinusCircle className="w-4 h-4 shrink-0" />
            <span>Top Bearish Evidence / Risks</span>
          </div>
          <ul className="space-y-2 text-xs text-slate-300">
            {topBearishDrivers.map((d, i) => (
              <li key={i} className="flex items-start space-x-2">
                <span className="text-rose-500 font-bold shrink-0">•</span>
                <span>{d}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Counterfactual Attribution Box */}
      <div className="p-3.5 rounded-2xl bg-white/[0.02] border border-white/[0.06] text-xs text-slate-300 flex items-start space-x-2.5">
        <HelpCircle className="w-4 h-4 text-cyan-400 shrink-0 mt-0.5" />
        <div>
          <span className="font-bold text-white">What Changed the Forecast? </span>
          <span className="text-slate-400 leading-relaxed">{counterfactualText}</span>
        </div>
      </div>
    </div>
  )
}
