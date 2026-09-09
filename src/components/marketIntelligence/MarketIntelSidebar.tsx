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
  const navItems = [
    { id: 'overview', label: 'Overview', icon: 'space_dashboard' },
    { id: 'market-intelligence', label: 'Market Intelligence', icon: 'query_stats' },
    { id: 'watchlist', label: 'Watchlist', icon: 'visibility', badge: '18' },
    { id: 'my-portfolio', label: 'My Portfolio', icon: 'account_balance_wallet' },
    { id: 'mutual-funds', label: 'Mutual Funds', icon: 'pie_chart' },
    { id: 'stocks', label: 'Stocks', icon: 'trending_up' },
    { id: 'etfs', label: 'ETFs', icon: 'layers' },
    { id: 'commodities', label: 'Commodities', icon: 'drive_file_rename_outline' },
    { id: 'research', label: 'Research', icon: 'biotech' },
    { id: 'predictions', label: 'Predictions', icon: 'psychology' },
    { id: 'events', label: 'Events', icon: 'event_note', badge: '3 New', badgeColor: 'bg-tertiary/20 text-tertiary border-tertiary/40' },
    { id: 'backtesting', label: 'Backtesting', icon: 'history_edu' },
    { id: 'model-health', label: 'Model Health', icon: 'monitor_heart' },
    { id: 'settings', label: 'Settings', icon: 'tune' }
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
          <div className="h-14 px-space-md flex items-center justify-between border-b border-outline-variant/30">
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
          <nav className="flex-1 px-space-xs py-space-sm space-y-space-2xs">
            {navItems.map((item) => {
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
                    <span className="font-body-default text-body-default">{item.label}</span>
                  </div>
                  {item.badge && (
                    <span
                      className={`font-data-mono-compact text-data-mono-compact px-1.5 py-0.5 rounded border ${
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
