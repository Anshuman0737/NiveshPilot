import React from 'react'
import { Compass, Sparkles, Sliders, ShieldCheck, BarChart3, Clock, AlertTriangle, Layers } from 'lucide-react'

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
  isSuitableForEquity: boolean
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  setActiveTab,
  advancedMode,
  setAdvancedMode,
  onOpenOnboarding,
  isSuitableForEquity
}) => {
  return (
    <header className="sticky top-0 z-40 bg-navy-950/90 backdrop-blur-md border-b border-slate-800">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Brand */}
          <div className="flex items-center space-x-3 cursor-pointer" onClick={() => setActiveTab('home')}>
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-700 flex items-center justify-center shadow-lg shadow-emerald-900/30">
              <Compass className="w-6 h-6 text-white" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-bold text-lg text-white tracking-tight">NiveshPilot</span>
                <span className="text-[10px] uppercase font-semibold tracking-wider px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  ₹0 Cost MVP
                </span>
              </div>
              <p className="text-xs text-slate-400 hidden sm:block">Indian Mutual Fund Decision Intelligence</p>
            </div>
          </div>

          {/* Nav Links */}
          <nav className="hidden md:flex items-center space-x-1 lg:space-x-2 text-sm font-medium">
            <button
              onClick={() => setActiveTab('home')}
              className={`px-3 py-1.5 rounded-lg transition-all ${
                activeTab === 'home'
                  ? 'bg-slate-800 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
            >
              Your Next Move
            </button>
            <button
              onClick={() => setActiveTab('ihavex')}
              className={`px-3 py-1.5 rounded-lg transition-all ${
                activeTab === 'ihavex'
                  ? 'bg-slate-800 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
            >
              "I Have ₹X"
            </button>
            <button
              onClick={() => setActiveTab('wait')}
              className={`px-3 py-1.5 rounded-lg transition-all flex items-center space-x-1 ${
                activeTab === 'wait'
                  ? 'bg-slate-800 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
            >
              <Clock className="w-3.5 h-3.5" />
              <span>Should I Wait?</span>
            </button>
            <button
              onClick={() => setActiveTab('sell')}
              className={`px-3 py-1.5 rounded-lg transition-all flex items-center space-x-1 ${
                activeTab === 'sell'
                  ? 'bg-slate-800 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
            >
              <AlertTriangle className="w-3.5 h-3.5" />
              <span>Should I Sell?</span>
            </button>
            <button
              onClick={() => setActiveTab('portfolio')}
              className={`px-3 py-1.5 rounded-lg transition-all flex items-center space-x-1 ${
                activeTab === 'portfolio'
                  ? 'bg-slate-800 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              <span>Portfolio & Overlap</span>
            </button>
            <button
              onClick={() => setActiveTab('compare')}
              className={`px-3 py-1.5 rounded-lg transition-all ${
                activeTab === 'compare'
                  ? 'bg-slate-800 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
            >
              Fund Match
            </button>
          </nav>

          {/* Actions & Advanced Mode Toggle */}
          <div className="flex items-center space-x-3">
            {/* Suitability Badge / Quick Re-check */}
            <button
              onClick={onOpenOnboarding}
              className={`flex items-center space-x-1.5 text-xs px-2.5 py-1.5 rounded-lg border transition-all ${
                isSuitableForEquity
                  ? 'bg-emerald-950/40 text-emerald-300 border-emerald-800/50 hover:bg-emerald-900/40'
                  : 'bg-rose-950/40 text-rose-300 border-rose-800/50 hover:bg-rose-900/40'
              }`}
              title="Click to change your financial goal or time horizon"
            >
              <ShieldCheck className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">
                {isSuitableForEquity ? 'Profile: Equity Suitable' : 'Profile: Safety First'}
              </span>
              <span className="sm:hidden">Profile</span>
            </button>

            {/* Advanced Research Mode Toggle */}
            <button
              onClick={() => setAdvancedMode(!advancedMode)}
              className={`flex items-center space-x-1.5 text-xs font-medium px-3 py-1.5 rounded-lg border transition-all ${
                advancedMode
                  ? 'bg-indigo-600/20 text-indigo-300 border-indigo-500/40 shadow-inner'
                  : 'bg-slate-900 text-slate-400 border-slate-800 hover:border-slate-700 hover:text-slate-300'
              }`}
              title="Toggle between Beginner-first View and Quantitative Research Mode"
            >
              <BarChart3 className="w-3.5 h-3.5" />
              <span className="hidden md:inline">Advanced Mode</span>
              <span className={`w-2 h-2 rounded-full ${advancedMode ? 'bg-indigo-400 animate-pulse' : 'bg-slate-600'}`} />
            </button>
          </div>
        </div>

        {/* Mobile Tab Sub-bar */}
        <div className="flex md:hidden overflow-x-auto py-2 space-x-1 text-xs border-t border-slate-900 scrollbar-none">
          <button
            onClick={() => setActiveTab('home')}
            className={`px-3 py-1 rounded whitespace-nowrap ${activeTab === 'home' ? 'bg-slate-800 text-white' : 'text-slate-400'}`}
          >
            Next Move
          </button>
          <button
            onClick={() => setActiveTab('ihavex')}
            className={`px-3 py-1 rounded whitespace-nowrap ${activeTab === 'ihavex' ? 'bg-slate-800 text-white' : 'text-slate-400'}`}
          >
            "I Have ₹X"
          </button>
          <button
            onClick={() => setActiveTab('wait')}
            className={`px-3 py-1 rounded whitespace-nowrap ${activeTab === 'wait' ? 'bg-slate-800 text-white' : 'text-slate-400'}`}
          >
            Wait?
          </button>
          <button
            onClick={() => setActiveTab('sell')}
            className={`px-3 py-1 rounded whitespace-nowrap ${activeTab === 'sell' ? 'bg-slate-800 text-white' : 'text-slate-400'}`}
          >
            Sell?
          </button>
          <button
            onClick={() => setActiveTab('portfolio')}
            className={`px-3 py-1 rounded whitespace-nowrap ${activeTab === 'portfolio' ? 'bg-slate-800 text-white' : 'text-slate-400'}`}
          >
            Portfolio
          </button>
          <button
            onClick={() => setActiveTab('compare')}
            className={`px-3 py-1 rounded whitespace-nowrap ${activeTab === 'compare' ? 'bg-slate-800 text-white' : 'text-slate-400'}`}
          >
            Match
          </button>
        </div>
      </div>
    </header>
  )
}
