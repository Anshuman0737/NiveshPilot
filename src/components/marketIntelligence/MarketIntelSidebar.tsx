import React from 'react'

interface MarketIntelSidebarProps {
  isOpen: boolean
  onClose: () => void
  currentPath: string
  onNavigate: (path: string) => void
}

export const MarketIntelSidebar: React.FC<MarketIntelSidebarProps> = ({
  isOpen,
  onClose,
  currentPath,
  onNavigate
}) => {
  const terminalItems = [
    { id: 'overview', label: 'Market Overview', icon: 'space_dashboard' },
    { id: 'predictions', label: 'Asset Diagnostics', icon: 'troubleshoot' },
    { id: 'events', label: 'Event Shock Cascades', icon: 'account_tree', badge: '3 Active', badgeColor: 'bg-tertiary/20 text-tertiary border-tertiary/40' },
    { id: 'stocks', label: 'Equities (NSE/BSE)', icon: 'trending_up' },
    { id: 'mutual-funds', label: 'Mutual Funds', icon: 'pie_chart' },
    { id: 'etfs', label: 'Index ETFs', icon: 'layers' },
    { id: 'commodities', label: 'Commodities & Macro', icon: 'water_drop' },
    { id: 'model-health', label: 'Model Health & Audit', icon: 'monitor_heart', badge: '99.9%' }
  ]

  const retailTools = [
    { id: 'home', label: 'Decision Advisor (₹10k)', icon: 'psychology', badge: 'Retail Hub', badgeColor: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40' },
    { id: 'portfolio', label: 'Portfolio Health & Upgrade', icon: 'account_balance_wallet' },
    { id: 'ihavex', label: 'I Have ₹X Allocator', icon: 'currency_rupee' },
    { id: 'wait', label: 'Should I Wait?', icon: 'hourglass_bottom' },
    { id: 'sell', label: 'Should I Sell?', icon: 'sell' },
    { id: 'compare', label: 'Fund Match Comparison', icon: 'compare_arrows' },
    { id: 'research', label: 'Quant Research Lab', icon: 'biotech' }
  ]

  const handleItemClick = (id: string) => {
    onNavigate(id)
    if (window.innerWidth < 1280) {
      onClose()
    }
  }

  return (
    <>
      {/* Mobile Backdrop */}
      {isOpen && (
        <div
          onClick={onClose}
          className="fixed inset-0 bg-black/70 backdrop-blur-sm z-40 xl:hidden transition-opacity"
          aria-hidden="true"
        />
      )}

      {/* Sidebar Container */}
      <aside
        className={`fixed left-0 top-0 h-full w-64 bg-surface-container-lowest z-50 flex flex-col justify-between border-r border-outline-variant/40 transition-transform duration-300 ease-in-out ${
          isOpen ? 'translate-x-0' : '-translate-x-full xl:translate-x-0'
        }`}
      >
        <div className="flex flex-col flex-1 overflow-y-auto">
          {/* Logo & Brand Header */}
          <div className="h-14 px-space-md flex items-center justify-between border-b border-outline-variant/30 shrink-0">
            <div className="flex items-center gap-space-xs">
              <div className="w-8 h-8 rounded bg-surface-container-high flex items-center justify-center font-data-mono-lg text-primary font-bold border border-outline-variant/40 shadow-sm">
                🧭
              </div>
              <div className="flex flex-col">
                <span className="font-headline-md text-headline-md tracking-tight uppercase text-on-surface">
                  NiveshPilot
                </span>
                <span className="font-label-caps text-label-caps text-on-surface-variant uppercase">
                  Market Intel
                </span>
              </div>
            </div>
            <div className="flex items-center gap-1">
              <span className="font-data-mono-compact text-data-mono-compact px-space-xs py-space-2xs rounded bg-surface-container-high text-secondary border border-outline-variant/50">
                v4.2 PRO
              </span>
              {/* Mobile Close Button */}
              <button
                onClick={onClose}
                className="xl:hidden p-1 text-on-surface-variant hover:text-on-surface rounded hover:bg-surface-container-high"
                aria-label="Close menu"
              >
                <span className="material-symbols-outlined text-[20px]">close</span>
              </button>
            </div>
          </div>

          {/* Navigation Links */}
          <nav className="flex-1 px-space-xs py-space-sm space-y-space-sm overflow-y-auto">
            {/* Group 1: Quant Terminal */}
            <div>
              <div className="px-space-sm py-1 font-label-caps text-[10px] text-on-surface-variant/70 uppercase tracking-wider font-semibold">
                Quant Terminal
              </div>
              <div className="space-y-0.5 mt-1">
                {terminalItems.map((item) => {
                  const isActive = currentPath === item.id
                  return (
                    <button
                      key={item.id}
                      onClick={() => handleItemClick(item.id)}
                      className={`w-full flex items-center justify-between px-space-sm py-1.5 rounded transition-all text-left ${
                        isActive
                          ? 'bg-primary-container text-on-primary-container font-semibold shadow-sm'
                          : 'text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface'
                      }`}
                    >
                      <div className="flex items-center gap-space-sm">
                        <span className="material-symbols-outlined text-[16px]">{item.icon}</span>
                        <span className="font-body-default text-body-default text-xs">{item.label}</span>
                      </div>
                      {item.badge && (
                        <span
                          className={`font-data-mono-compact text-[10px] px-1.5 py-0.5 rounded border ${
                            item.badgeColor
                              ? item.badgeColor
                              : 'bg-surface-container-high text-on-surface-variant border-outline-variant/40'
                          }`}
                        >
                          {item.badge}
                        </span>
                      )}
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Group 2: NiveshPilot Decision & Allocation Tools */}
            <div className="pt-2 border-t border-outline-variant/30">
              <div className="px-space-sm py-1 font-label-caps text-[10px] text-emerald-400/80 uppercase tracking-wider font-semibold flex items-center justify-between">
                <span>NiveshPilot Tools</span>
                <span className="text-[9px] font-mono px-1 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  RETAIL
                </span>
              </div>
              <div className="space-y-0.5 mt-1">
                {retailTools.map((item) => {
                  const isActive = currentPath === item.id
                  return (
                    <button
                      key={item.id}
                      onClick={() => handleItemClick(item.id)}
                      className={`w-full flex items-center justify-between px-space-sm py-1.5 rounded transition-all text-left ${
                        isActive
                          ? 'bg-emerald-500/20 text-emerald-300 font-semibold shadow-sm'
                          : 'text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface'
                      }`}
                    >
                      <div className="flex items-center gap-space-sm">
                        <span className="material-symbols-outlined text-[16px]">{item.icon}</span>
                        <span className="font-body-default text-body-default text-xs">{item.label}</span>
                      </div>
                      {item.badge && (
                        <span
                          className={`font-data-mono-compact text-[10px] px-1.5 py-0.5 rounded border ${
                            item.badgeColor
                              ? item.badgeColor
                              : 'bg-surface-container-high text-on-surface-variant border-outline-variant/40'
                          }`}
                        >
                          {item.badge}
                        </span>
                      )}
                    </button>
                  )
                })}
              </div>
            </div>
          </nav>
        </div>

        {/* Bottom Engine Telemetry Status */}
        <div className="p-space-sm bg-surface-container-low border-t border-outline-variant/30 space-y-space-xs">
          <div className="flex items-center justify-between font-label-caps text-label-caps text-on-surface-variant uppercase">
            <span className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-tertiary animate-pulse"></span>
              Engine
            </span>
            <span className="font-data-mono-compact text-data-mono-compact text-tertiary">
              42ms · NSE/BSE
            </span>
          </div>
          <div className="flex items-center justify-between font-label-caps text-label-caps text-on-surface-variant uppercase">
            <span>Sync</span>
            <span className="font-data-mono-compact text-data-mono-compact text-on-surface">
              v4.8b · Realtime
            </span>
          </div>
          <div className="flex items-center justify-between font-label-caps text-label-caps text-on-surface-variant uppercase">
            <span>Status</span>
            <span className="font-data-mono-compact text-data-mono-compact text-secondary">
              99.98% OK
            </span>
          </div>
        </div>
      </aside>
    </>
  )
}
