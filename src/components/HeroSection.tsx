import React from 'react'
import { ArrowRight, Shield, Database, Scale, Sparkles, CheckCircle2 } from 'lucide-react'

interface HeroSectionProps {
  onFindNextMove: () => void
  onExploreResearch: () => void
  currentAmount: number
  onSelectAmount?: (amount: number) => void
}

const QUICK_AMOUNTS = [10000, 25000, 50000, 100000, 250000]

export const HeroSection: React.FC<HeroSectionProps> = ({
  onFindNextMove,
  onExploreResearch,
  currentAmount,
  onSelectAmount
}) => {
  const formattedAmount = new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0
  }).format(currentAmount || 10000)

  return (
    <section className="relative pt-12 pb-14 sm:pt-16 sm:pb-20 overflow-hidden border-b border-white/[0.04]">
      {/* Sleek Radial Ambient Spotlight */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full max-w-7xl h-[450px] bg-[radial-gradient(ellipse_80%_60%_at_50%_0%,rgba(16,185,129,0.12),rgba(255,255,255,0))] pointer-events-none" />
      <div className="absolute top-1/4 right-1/4 w-96 h-96 bg-indigo-500/[0.04] rounded-full blur-3xl pointer-events-none" />

      <div className="relative max-w-4xl mx-auto px-4 sm:px-6 text-center z-10">
        {/* Minimal Pill Badge */}
        <div className="inline-flex items-center space-x-2 px-3.5 py-1 rounded-full bg-white/[0.04] border border-white/[0.08] text-xs font-medium text-slate-300 mb-6 backdrop-blur-md">
          <Sparkles className="w-3.5 h-3.5 text-emerald-400" />
          <span>Objective Indian Mutual Fund Decision Intelligence</span>
        </div>

        {/* Minimal High-Impact Headline */}
        <h1 className="text-4xl sm:text-6xl font-black tracking-tight text-white mb-5 leading-[1.1]">
          What should I do with my next{' '}
          <span className="text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 via-teal-300 to-cyan-400">
            {formattedAmount}?
          </span>
        </h1>

        {/* Focused Subheading */}
        <p className="max-w-2xl mx-auto text-base sm:text-lg text-slate-400 mb-8 leading-relaxed font-normal">
          Translating 8+ years of empirical AMFI data and 6 market regimes into one clear,
          evidence-backed next move. No hype. No paid APIs. Zero financial noise.
        </p>

        {/* Interactive Quick Capital Scrubber */}
        {onSelectAmount && (
          <div className="flex flex-wrap items-center justify-center gap-2 mb-8 text-xs">
            <span className="text-slate-500 font-medium mr-1">Quick Select:</span>
            {QUICK_AMOUNTS.map((amt) => {
              const isSelected = currentAmount === amt
              const label =
                amt >= 100000 ? `₹${amt / 100000} Lakh` : `₹${(amt / 1000).toFixed(0)}k`
              return (
                <button
                  key={amt}
                  onClick={() => onSelectAmount(amt)}
                  className={`px-3 py-1.5 rounded-full font-semibold transition-all ${
                    isSelected
                      ? 'bg-emerald-500 text-navy-950 shadow-md shadow-emerald-500/20 scale-105'
                      : 'bg-slate-900/60 hover:bg-slate-800 text-slate-400 hover:text-white border border-white/[0.06]'
                  }`}
                >
                  {label}
                </button>
              )
            })}
          </div>
        )}

        {/* Minimal Modern CTAs */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3 sm:gap-4 mb-10">
          <button
            onClick={onFindNextMove}
            className="w-full sm:w-auto px-7 py-3.5 rounded-full bg-emerald-500 hover:bg-emerald-400 text-navy-950 font-extrabold text-sm shadow-xl shadow-emerald-500/20 hover:scale-[1.02] transition-all flex items-center justify-center space-x-2 group"
          >
            <span>Personalize My Next Move</span>
            <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
          </button>
          <button
            onClick={onExploreResearch}
            className="w-full sm:w-auto px-6 py-3.5 rounded-full bg-slate-900/60 hover:bg-slate-800/80 text-slate-300 hover:text-white font-semibold text-sm border border-white/[0.08] hover:border-white/[0.16] backdrop-blur-md transition-all flex items-center justify-center space-x-2"
          >
            <Database className="w-4 h-4 text-slate-400" />
            <span>Explore Empirical Research</span>
          </button>
        </div>

        {/* Minimalist Trust Features */}
        <div className="flex flex-wrap items-center justify-center gap-6 sm:gap-10 text-xs text-slate-400 pt-6 border-t border-white/[0.04]">
          <div className="flex items-center space-x-2">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
            <span>100% Client-Side Private (₹0 Cost)</span>
          </div>
          <div className="flex items-center space-x-2">
            <CheckCircle2 className="w-3.5 h-3.5 text-teal-400 shrink-0" />
            <span>AMFI Historical Benchmark Archives</span>
          </div>
          <div className="flex items-center space-x-2">
            <CheckCircle2 className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
            <span>Deterministic SHA-256 Decision Hash</span>
          </div>
        </div>
      </div>
    </section>
  )
}
