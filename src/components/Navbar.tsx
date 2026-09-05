import React from 'react'
import {
  Compass,
  Sparkles,
  Sliders,
  ShieldCheck,
  BarChart3,
  Clock,
  AlertTriangle,
  Layers,
  Bot
} from 'lucide-react'

export type ActiveTab =
  | 'home'
  | 'ihavex'
  | 'wait'
  | 'sell'
  | 'portfolio'
  | 'compare'
  | 'research'

interface NavbarProps {
  activeTab: ActiveTab
  setActiveTab: (tab: ActiveTab) => void
  advancedMode: boolean
  setAdvancedMode: (v: boolean) => void
  onOpenOnboarding: () => void
  onOpenAISettings?: () => void
  isSuitableForEquity: boolean
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  setActiveTab,
  advancedMode,
  setAdvancedMode,
  onOpenOnboarding,
  onOpenAISettings,
  isSuitableForEquity
}) => {
  return (
    <header className="sticky top-0 z-40 bg-navy-950/80 backdrop-blur-xl border-b border-white/[0.06] transition-all">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Minimal Brand Logo */}
          <div
            className="flex items-center space-x-3 cursor-pointer group"
            onClick={() => setActiveTab('home')}
          >
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-emerald-500 to-teal-400 flex items-center justify-center shadow-lg shadow-emerald-500/20 group-hover:scale-105 transition-transform">
              <Compass className="w-5 h-5 text-navy-950 font-bold" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-extrabold text-base sm:text-lg text-white tracking-tight">
                  NiveshPilot
                </span>
                <span className="text-[10px] uppercase font-bold tracking-widest px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  ₹0 Cost
                </span>
              </div>
            </div>
          </div>

          {/* Minimalist Floating Segmented Pill Nav */}
          <nav className="hidden lg:flex items-center p-1 bg-slate-900/60 rounded-full border border-white/[0.08] text-xs font-medium backdrop-blur-md">
            <button
              onClick={() => setActiveTab('home')}
              className={`px-3.5 py-1.5 rounded-full transition-all ${
                activeTab === 'home'
                  ? 'bg-white/[0.12] text-white shadow-sm font-semibold'
                  : 'text-slate-400 hover:text-white hover:bg-white/[0.04]'
              }`}
            >
              Next Move
            </button>
            <button
              onClick={() => setActiveTab('ihavex')}
              className={`px-3.5 py-1.5 rounded-full transition-all ${
                activeTab === 'ihavex'
                  ? 'bg-white/[0.12] text-white shadow-sm font-semibold'
                  : 'text-slate-400 hover:text-white hover:bg-white/[0.04]'
              }`}
            >
              "I Have ₹X"
            </button>
            <button
              onClick={() => setActiveTab('wait')}
              className={`px-3.5 py-1.5 rounded-full transition-all ${
                activeTab === 'wait'
                  ? 'bg-white/[0.12] text-white shadow-sm font-semibold'
                  : 'text-slate-400 hover:text-white hover:bg-white/[0.04]'
              }`}
            >
              Should I Wait?
            </button>
            <button
              onClick={() => setActiveTab('sell')}
              className={`px-3.5 py-1.5 rounded-full transition-all ${
                activeTab === 'sell'
                  ? 'bg-white/[0.12] text-white shadow-sm font-semibold'
                  : 'text-slate-400 hover:text-white hover:bg-white/[0.04]'
              }`}
            >
              Should I Sell?
            </button>
            <button
              onClick={() => setActiveTab('portfolio')}
              className={`px-3.5 py-1.5 rounded-full transition-all flex items-center space-x-1.5 ${
                activeTab === 'portfolio'
                  ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 shadow-sm font-semibold'
                  : 'text-slate-400 hover:text-white hover:bg-white/[0.04]'
              }`}
            >
              <Layers className="w-3.5 h-3.5 text-emerald-400" />
              <span>Portfolio Upgrade</span>
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            </button>
            <button
              onClick={() => setActiveTab('compare')}
              className={`px-3.5 py-1.5 rounded-full transition-all ${
                activeTab === 'compare'
                  ? 'bg-white/[0.12] text-white shadow-sm font-semibold'
                  : 'text-slate-400 hover:text-white hover:bg-white/[0.04]'
              }`}
            >
              Fund Match
            </button>
          </nav>

          {/* Quick Actions */}
          <div className="flex items-center space-x-2 sm:space-x-2.5">
            {/* Minimal Suitability Badge */}
            <button
              onClick={onOpenOnboarding}
              className="flex items-center space-x-1.5 text-xs px-3 py-1.5 rounded-full bg-slate-900/60 border border-white/[0.08] hover:border-white/[0.15] text-slate-300 transition-all"
              title="Click to edit financial profile"
            >
              <span
                className={`w-2 h-2 rounded-full ${
                  isSuitableForEquity ? 'bg-emerald-400' : 'bg-rose-400'
                }`}
              />
              <span className="hidden sm:inline font-medium">
                {isSuitableForEquity ? 'Equity Ready' : 'Safety First'}
              </span>
            </button>

            {/* AI Co-Pilot Button */}
            <button
              onClick={onOpenAISettings}
              className="flex items-center space-x-1.5 text-xs font-semibold px-3 py-1.5 rounded-full bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 transition-all"
              title="Configure AI Co-Pilot (Ollama, Groq, Offline)"
            >
              <Bot className="w-3.5 h-3.5 text-indigo-400" />
              <span className="hidden md:inline">AI Co-Pilot</span>
            </button>

            {/* Research Mode Pill */}
            <button
              onClick={() => setAdvancedMode(!advancedMode)}
              className={`flex items-center space-x-1.5 text-xs font-medium px-3 py-1.5 rounded-full border transition-all ${
                advancedMode
                  ? 'bg-indigo-600/25 text-indigo-300 border-indigo-500/40 shadow-inner'
                  : 'bg-slate-900/60 text-slate-400 border-white/[0.08] hover:border-white/[0.15] hover:text-slate-200'
              }`}
              title="Toggle Research Dashboard"
            >
              <BarChart3 className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Quant View</span>
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  advancedMode ? 'bg-indigo-400 animate-pulse' : 'bg-slate-600'
                }`}
              />
            </button>
          </div>
        </div>

        {/* Mobile Horizontal Pill Scroller */}
        <div className="flex lg:hidden overflow-x-auto py-2 space-x-1.5 text-xs border-t border-white/[0.04] scrollbar-none">
          <button
            onClick={() => setActiveTab('home')}
            className={`px-3 py-1 rounded-full whitespace-nowrap transition-all ${
              activeTab === 'home' ? 'bg-white/10 text-white font-semibold' : 'text-slate-400'
            }`}
          >
            Next Move
          </button>
          <button
            onClick={() => setActiveTab('ihavex')}
            className={`px-3 py-1 rounded-full whitespace-nowrap transition-all ${
              activeTab === 'ihavex' ? 'bg-white/10 text-white font-semibold' : 'text-slate-400'
            }`}
          >
            "I Have ₹X"
          </button>
          <button
            onClick={() => setActiveTab('wait')}
            className={`px-3 py-1 rounded-full whitespace-nowrap transition-all ${
              activeTab === 'wait' ? 'bg-white/10 text-white font-semibold' : 'text-slate-400'
            }`}
          >
            Wait?
          </button>
          <button
            onClick={() => setActiveTab('sell')}
            className={`px-3 py-1 rounded-full whitespace-nowrap transition-all ${
              activeTab === 'sell' ? 'bg-white/10 text-white font-semibold' : 'text-slate-400'
            }`}
          >
            Sell?
          </button>
          <button
            onClick={() => setActiveTab('portfolio')}
            className={`px-3 py-1 rounded-full whitespace-nowrap transition-all flex items-center space-x-1 ${
              activeTab === 'portfolio' ? 'bg-emerald-500/20 text-emerald-300 font-semibold' : 'text-slate-400'
            }`}
          >
            <Layers className="w-3 h-3 text-emerald-400" />
            <span>Upgrade</span>
          </button>
          <button
            onClick={() => setActiveTab('compare')}
            className={`px-3 py-1 rounded-full whitespace-nowrap transition-all ${
              activeTab === 'compare' ? 'bg-white/10 text-white font-semibold' : 'text-slate-400'
            }`}
          >
            Match
          </button>
        </div>
      </div>
    </header>
  )
}
