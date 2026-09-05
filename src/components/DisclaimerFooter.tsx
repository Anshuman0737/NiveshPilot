import React from 'react'
import { Shield, Info, Scale, AlertTriangle, Compass } from 'lucide-react'

export const DisclaimerFooter: React.FC = () => {
  return (
    <footer className="mt-20 border-t border-slate-800/80 bg-navy-950/90 text-slate-400 text-xs">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-12">
        {/* Brand & Purpose */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-8 mb-8 border-b border-slate-800">
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 rounded-lg bg-emerald-600/20 border border-emerald-500/30 flex items-center justify-center">
              <Compass className="w-4 h-4 text-emerald-400" />
            </div>
            <div>
              <span className="font-bold text-white text-sm">NiveshPilot</span>
              <span className="text-slate-500 ml-2">• Decision Intelligence MVP</span>
            </div>
          </div>
          <div className="flex items-center space-x-4 text-[11px] text-slate-400">
            <span>₹0 Target Cost</span>
            <span>•</span>
            <span>No Paid APIs</span>
            <span>•</span>
            <span>Offline Capable</span>
            <span>•</span>
            <span>SEBI Non-Advisory Research</span>
          </div>
        </div>

        {/* Mandatory Disclaimers */}
        <div className="space-y-4 leading-relaxed text-[11px] text-slate-400">
          <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 text-slate-300">
            <strong className="text-amber-400 block font-semibold mb-1 flex items-center space-x-1.5">
              <AlertTriangle className="w-3.5 h-3.5" />
              <span>Mandatory Risk Disclaimer & Regulatory Notice</span>
            </strong>
            <p className="mb-2">
              <strong>Mutual fund investments are subject to market risks. Please read all scheme-related documents carefully before investing.</strong>{' '}
              Past performance, backtest simulations, and historical signal observations do not guarantee, promise, or predict future results.
            </p>
            <p>
              <strong>NiveshPilot is an educational, quantitative decision-support and research software tool.</strong>{' '}
              It is NOT a SEBI-registered Investment Adviser (RIA) or Research Analyst (RA). It does NOT provide personalized financial advice,
              guaranteed returns, price targets, or execution services. All model outputs are mechanical estimations derived from publicly available
              AMFI NAV data and statistical regime filters. Users must assess their own risk tolerance, liquidity needs, and financial circumstances
              or consult a SEBI-registered financial planner before executing any financial transaction.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-slate-400">
            <div>
              <h5 className="font-bold text-slate-300 mb-1">Data Provenance & Collection</h5>
              <p>
                Mutual fund Net Asset Value (NAV) historical records are obtained via official AMFI public downloadable facilities.
                Benchmark data reflects NSE Indices Ltd public archives. NiveshPilot does not scrape websites in violation of terms of service
                nor require broker account credentials.
              </p>
            </div>
            <div>
              <h5 className="font-bold text-slate-300 mb-1">Privacy & Independence Guarantee</h5>
              <p>
                Your entered capital, goals, and portfolio holdings are stored locally in your browser session.
                NiveshPilot does not sell user data, run advertising trackers, or transmit personal financial information to third-party AI APIs.
              </p>
            </div>
          </div>
        </div>

        <div className="mt-8 pt-6 border-t border-slate-900 text-center text-slate-400 text-[11px]">
          © {new Date().getFullYear()} NiveshPilot. Built for clarity under uncertainty.
        </div>
      </div>
    </footer>
  )
}
