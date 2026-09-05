import React from 'react'
import { ArrowRight, Shield, Database, Scale, HelpCircle } from 'lucide-react'

interface HeroSectionProps {
  onFindNextMove: () => void
  onExploreResearch: () => void
  currentAmount: number
}

export const HeroSection: React.FC<HeroSectionProps> = ({
  onFindNextMove,
  onExploreResearch,
  currentAmount
}) => {
  const formattedAmount = new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0
  }).format(currentAmount || 10000)

  return (
    <section className="relative pt-8 pb-10 sm:pt-12 sm:pb-14 overflow-hidden border-b border-slate-900 bg-gradient-to-b from-navy-950 via-slate-950 to-navy-900/50">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
        {/* Calm Pill Badge */}
        <div className="inline-flex items-center space-x-2 px-3.5 py-1.5 rounded-full bg-slate-900/80 border border-slate-800 text-xs font-medium text-slate-300 mb-6">
          <Scale className="w-3.5 h-3.5 text-emerald-400" />
          <span>Clarity under uncertainty, not fake certainty</span>
        </div>

        {/* Hero Title */}
        <h1 className="text-3xl sm:text-5xl lg:text-6xl font-extrabold tracking-tight text-white mb-4">
          What should I do with my next{' '}
          <span className="text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-teal-300">
            {formattedAmount}?
          </span>
        </h1>

        {/* Subheading */}
        <p className="max-w-2xl mx-auto text-base sm:text-lg text-slate-400 mb-8 leading-relaxed">
          NiveshPilot turns complicated market regime and Indian mutual-fund data into a simple,
          evidence-backed next step. Zero noise. Zero paid APIs. Zero hype.
        </p>

        {/* CTAs */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3 sm:gap-4 mb-8">
          <button
            onClick={onFindNextMove}
            className="w-full sm:w-auto px-6 py-3.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-sm shadow-lg shadow-emerald-900/30 transition-all flex items-center justify-center space-x-2 group"
          >
            <span>Find My Next Move</span>
            <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
          </button>
          <button
            onClick={onExploreResearch}
            className="w-full sm:w-auto px-6 py-3.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold text-sm border border-slate-700 transition-all flex items-center justify-center space-x-2"
          >
            <Database className="w-4 h-4 text-slate-400" />
            <span>Explore the Research</span>
          </button>
        </div>

        {/* Mandatory Core Disclaimers & Principles */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 max-w-3xl mx-auto text-left text-xs text-slate-400 pt-4 border-t border-slate-900/80">
          <div className="flex items-start space-x-2 p-2 rounded-lg bg-slate-900/40 border border-slate-900">
            <Shield className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
            <span>
              <strong>Zero False Promises</strong>: We never promise guaranteed returns or claim to predict market bottoms.
            </span>
          </div>
          <div className="flex items-start space-x-2 p-2 rounded-lg bg-slate-900/40 border border-slate-900">
            <Database className="w-4 h-4 text-teal-400 shrink-0 mt-0.5" />
            <span>
              <strong>Public AMFI Data</strong>: Tested against historical Nifty & mutual-fund data without illegal scraping.
            </span>
          </div>
          <div className="flex items-start space-x-2 p-2 rounded-lg bg-slate-900/40 border border-slate-900">
            <HelpCircle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
            <span>
              <strong>Honest Uncertainty</strong>: When market evidence is conflicting, the engine will state "No Clear Signal".
            </span>
          </div>
        </div>
      </div>
    </section>
  )
}
