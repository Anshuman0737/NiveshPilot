import React, { useState, useEffect } from 'react'
import { AssetClass } from '../../engine/marketIntelligence/types'

interface MarketIntelHeaderProps {
  onToggleMobileNav: () => void
  searchQuery: string
  onSearchChange: (query: string) => void
  selectedClass: AssetClass | 'all'
  onSelectClass: (cls: AssetClass | 'all') => void
  marketRegion: 'IN' | 'US'
  onToggleRegion: (region: 'IN' | 'US') => void
  onExplainForecast: () => void
  onExitToAdvisor?: () => void
  userRole?: string
  userName?: string
}

export const MarketIntelHeader: React.FC<MarketIntelHeaderProps> = ({
  onToggleMobileNav,
  searchQuery,
  onSearchChange,
  selectedClass,
  onSelectClass,
  marketRegion,
  onToggleRegion,
  onExplainForecast,
  onExitToAdvisor,
  userRole = 'Lead Quant',
  userName = 'Arjun Mehta'
}) => {
  const [timeStr, setTimeStr] = useState<string>('')

  useEffect(() => {
    const updateClock = () => {
      const now = new Date()
      const hours = String(now.getHours()).padStart(2, '0')
      const minutes = String(now.getMinutes()).padStart(2, '0')
      const seconds = String(now.getSeconds()).padStart(2, '0')
      setTimeStr(`${hours}:${minutes}:${seconds} IST`)
    }
    updateClock()
    const timer = setInterval(updateClock, 1000)
    return () => clearInterval(timer)
  }, [])

  return (
    <header className="fixed top-0 left-0 xl:left-64 right-0 h-14 bg-surface-container-lowest/95 backdrop-blur-xl border-b border-outline-variant/40 z-40 px-3 sm:px-space-lg flex items-center justify-between gap-2 sm:gap-space-md">
      {/* Left: Mobile Hamburger & Search */}
      <div className="flex items-center gap-2 sm:gap-space-md flex-1 max-w-2xl">
        {/* Mobile Hamburger Menu Toggle */}
        <button
          onClick={onToggleMobileNav}
          className="xl:hidden p-1.5 rounded-lg text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high transition-colors"
          aria-label="Open navigation drawer"
        >
          <span className="material-symbols-outlined text-[20px]">menu</span>
        </button>

        {/* Search Input with Asset Filters */}
        <div className="relative flex items-center w-full bg-surface-container-low border border-outline-variant/50 rounded h-8 px-2">
          <span className="material-symbols-outlined text-outline text-[18px] mr-1 sm:mr-2 shrink-0">
            search
          </span>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search stocks, ETFs, funds, commodities (⌘K)..."
            className="bg-transparent border-none outline-none w-full font-data-mono-default text-[11px] sm:text-data-mono-default text-on-surface placeholder:text-outline/70"
          />

          {/* Quick Class Pills */}
          <div className="hidden sm:flex items-center gap-1 ml-2 shrink-0">
            {[
              { id: 'all', label: 'ALL' },
              { id: 'equity', label: 'EQ' },
              { id: 'etf', label: 'ETF' },
              { id: 'mutual_fund', label: 'MF' },
              { id: 'commodity', label: 'CMD' }
            ].map((tab) => {
              const isSelected = selectedClass === tab.id
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => onSelectClass(tab.id as any)}
                  className={`font-label-caps text-label-caps px-1 py-0.5 rounded transition-colors ${
                    isSelected
                      ? 'bg-primary-container text-on-primary-container font-bold'
                      : 'bg-surface-container-high text-on-surface-variant hover:text-on-surface'
                  }`}
                >
                  {tab.label}
                </button>
              )
            })}
          </div>
        </div>

        {/* Live Market Clock */}
        <div className="hidden lg:flex items-center gap-space-xs font-label-caps text-label-caps text-on-surface-variant whitespace-nowrap shrink-0">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-tertiary opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-tertiary"></span>
          </span>
          <span className="text-tertiary font-data-mono-compact text-data-mono-compact font-semibold">
            NSE/BSE OPEN
          </span>
          <span>·</span>
          <span className="font-data-mono-compact text-data-mono-compact">{timeStr}</span>
        </div>
      </div>

      {/* Right: Controls, Explain Button, Bell, Profile */}
      <div className="flex items-center gap-1.5 sm:gap-space-md shrink-0">
        {/* Market Region Switcher */}
        <div className="hidden md:flex items-center bg-surface-container-low p-0.5 rounded border border-outline-variant/40">
          <button
            type="button"
            onClick={() => onToggleRegion('IN')}
            className={`px-2 py-1 font-label-caps text-label-caps rounded transition-colors ${
              marketRegion === 'IN'
                ? 'bg-secondary-container text-on-secondary-container font-semibold'
                : 'text-on-surface-variant hover:text-on-surface'
            }`}
          >
            IN · NSE/BSE
          </button>
          <button
            type="button"
            onClick={() => onToggleRegion('US')}
            className={`px-2 py-1 font-label-caps text-label-caps rounded transition-colors ${
              marketRegion === 'US'
                ? 'bg-secondary-container text-on-secondary-container font-semibold'
                : 'text-on-surface-variant hover:text-on-surface'
            }`}
          >
            US · NYSE
          </button>
        </div>

        {/* Telemetry info */}
        <div className="hidden 2xl:flex flex-col text-right font-data-mono-compact text-data-mono-compact text-on-surface-variant">
          <span>Pipeline: 2m ago</span>
          <span className="text-tertiary font-semibold">99.4% Integrity</span>
        </div>

        {/* Explain Forecast Button */}
        <button
          type="button"
          onClick={onExplainForecast}
          className="flex items-center gap-1 h-7 px-2 sm:px-2.5 bg-primary/10 border border-primary/40 rounded text-primary hover:bg-primary/20 transition-all font-body-compact text-body-compact font-semibold shadow-sm"
        >
          <span className="material-symbols-outlined text-[16px]">auto_awesome</span>
          <span className="hidden sm:inline">Explain Forecast</span>
          <span className="sm:hidden">Explain</span>
        </button>

        {/* Notification Bell */}
        <button
          type="button"
          className="relative p-1 text-on-surface-variant hover:text-on-surface rounded hover:bg-surface-container-high transition-colors"
          aria-label="Notifications"
        >
          <span className="material-symbols-outlined text-[20px]">notifications</span>
          <span className="absolute top-1 right-1 w-1.5 h-1.5 bg-error rounded-full animate-pulse"></span>
        </button>

        {/* Quick Return to Decision Advisor (Retail Mode) */}
        {onExitToAdvisor && (
          <button
            type="button"
            onClick={onExitToAdvisor}
            className="flex items-center gap-1 sm:gap-1.5 h-7 px-2 sm:px-2.5 bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/30 rounded text-emerald-300 hover:text-emerald-200 transition-all font-body-compact text-body-compact font-semibold text-xs shadow-sm cursor-pointer"
            title="Return to ₹10k Decision Advisor"
          >
            <span className="material-symbols-outlined text-[16px]">arrow_back</span>
            <span className="hidden sm:inline">Decision Advisor (₹10k)</span>
            <span className="sm:hidden">Advisor</span>
          </button>
        )}

        {/* User Profile */}
        <div className="flex items-center gap-2 pl-1 sm:pl-2 border-l border-outline-variant/40">
          <div className="w-7 h-7 sm:w-8 sm:h-8 rounded-full bg-surface-container-highest border border-outline-variant flex items-center justify-center font-data-mono-compact text-primary font-bold text-xs">
            AM
          </div>
          <div className="hidden md:flex flex-col text-left">
            <span className="font-body-compact text-body-compact font-semibold text-on-surface leading-none">
              {userName}
            </span>
            <span className="font-label-caps text-label-caps text-on-surface-variant mt-0.5">
              {userRole}
            </span>
          </div>
        </div>
      </div>
    </header>
  )
}
