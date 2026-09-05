import React, { useState } from 'react'
import { AlertOctagon, CheckCircle2, AlertTriangle, ShieldCheck, HelpCircle, ArrowRight } from 'lucide-react'

export const ShouldISellMode: React.FC = () => {
  const [sellingReason, setSellingReason] = useState<string>('market_drop')

  const reasons = [
    {
      id: 'market_drop',
      title: 'The market / NAV dropped recently (-5% to -15%)',
      desc: 'I am seeing red in my portfolio and feel nervous.'
    },
    {
      id: 'goal_reached',
      title: 'I have reached my financial goal or timeline is up',
      desc: 'I need the money in the next few weeks / months for my planned goal.'
    },
    {
      id: 'fund_lagging',
      title: 'Fund has lagged its benchmark category for 2+ consecutive years',
      desc: 'Persistent underperformance, not just a bad quarter.'
    },
    {
      id: 'manager_change',
      title: 'Significant fund structural change or expense ratio spike',
      desc: 'Key fund manager resigned, strategy altered, or fees increased sharply.'
    },
    {
      id: 'emergency_need',
      title: 'Urgent personal emergency / Liquidity need',
      desc: 'Unforeseen medical, family, or employment hardship requires immediate cash.'
    }
  ]

  const getDiagnosticVerdict = () => {
    switch (sellingReason) {
      case 'market_drop':
        return {
          verdict: 'HOLD / DO NOT PANIC-SELL',
          color: 'emerald',
          badgeClass: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
          title: 'A Market Drop Alone Is NOT a Reason to Sell',
          explanation:
            'Temporary declines of 10–20% are the price of admission for superior long-term equity returns. Selling during a pullback permanently locks in a paper loss and guarantees you will miss the subsequent recovery.',
          actionableAdvice: [
            'Check your time horizon: If you don’t need this capital for 3+ years, do nothing.',
            'Historical reality: Over the last 20 years, every major Nifty pullback (-15% to -38%) was followed by a subsequent recovery to fresh highs.',
            'Selling converts an unrealized temporary drawdown into a permanent capital loss.'
          ]
        }
      case 'goal_reached':
        return {
          verdict: 'REDEEM OR DE-RISK SYSTEMATICALLY',
          color: 'teal',
          badgeClass: 'bg-teal-500/10 text-teal-400 border-teal-500/30',
          title: 'Capital Has Fulfilled Its Purpose: Protect It Now',
          explanation:
            'When your target date arrives, protecting accumulated capital takes absolute priority over seeking further market gains.',
          actionableAdvice: [
            'Systematically transfer (STP) equity into an ultra-safe Liquid or Overnight Fund.',
            'Never leave capital needed within 6–12 months exposed to volatile equity swings.'
          ]
        }
      case 'fund_lagging':
        return {
          verdict: 'REVIEW & SWITCH TO CONSISTENT CATEGORY PEER',
          color: 'amber',
          badgeClass: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
          title: 'Genuine Fund Deterioration Detected',
          explanation:
            'While 1–2 bad quarters are normal, 2–3 full years of persistent benchmark underperformance indicates a flawed stock-selection process or structural drag.',
          actionableAdvice: [
            'Compare the fund’s rolling 3-year alpha against its category benchmark (e.g. Nifty 50 TRI).',
            'If the thesis has fundamentally decayed, switch to a low-cost Nifty Index Fund or top-quartile active peer.',
            'Factor in exit loads (usually 0% after 1 year) and LTCG capital gains tax implications.'
          ]
        }
      case 'manager_change':
        return {
          verdict: 'WATCHLIST & MONITOR (NO IMMEDIATE RUSH)',
          color: 'slate',
          badgeClass: 'bg-slate-500/10 text-slate-300 border-slate-500/30',
          title: 'Fund Thesis Changed: Review Next 2 Quarters',
          explanation:
            'A fund manager departure is noteworthy, but institutional fund houses have structured investment committees. Give the new management 2 quarters to observe strategy continuity before exiting.',
          actionableAdvice: [
            'Check if the investment philosophy (value vs growth, concentration vs diversified) changed.',
            'If the expense ratio spiked significantly above category averages, consider low-cost alternatives.'
          ]
        }
      case 'emergency_need':
      default:
        return {
          verdict: 'REDEEM ONLY WHAT IS REQUIRED FOR SAFETY',
          color: 'rose',
          badgeClass: 'bg-rose-500/10 text-rose-300 border-rose-500/30',
          title: 'Immediate Financial Safety Comes First',
          explanation:
            'Real-life health and survival always supersede stock market investments. If you have no other emergency liquidity, withdraw what is strictly needed.',
          actionableAdvice: [
            'Liquidate debt/liquid holdings first if available to avoid selling equity at a loss.',
            'Sell only the exact amount required for the immediate emergency; leave the balance compounding.',
            'Once stabilized, rebuild a dedicated 6-month liquid emergency cushion before resuming equity.'
          ]
        }
    }
  }

  const verdict = getDiagnosticVerdict()

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8">
      {/* Header */}
      <div className="text-center max-w-2xl mx-auto mb-8">
        <div className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-full bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs font-semibold uppercase tracking-wider mb-3">
          <AlertOctagon className="w-3.5 h-3.5" />
          <span>Exit & Thesis Diagnostic</span>
        </div>
        <h2 className="text-3xl font-extrabold text-white tracking-tight mb-2">
          "Should I Sell My Mutual Fund?"
        </h2>
        <p className="text-sm text-slate-400">
          A temporary market drop is NOT the same thing as a broken investment thesis.
          Identify why you want to sell before taking an irreversible action.
        </p>
      </div>

      {/* Reason Picker */}
      <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl mb-8">
        <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3">
          Why are you considering selling?
        </label>
        <div className="space-y-2.5">
          {reasons.map((r) => (
            <button
              key={r.id}
              onClick={() => setSellingReason(r.id)}
              className={`w-full p-4 rounded-xl border text-left transition-all ${
                sellingReason === r.id
                  ? 'bg-emerald-950/40 border-emerald-500 text-white shadow-md'
                  : 'bg-slate-950 border-slate-800/80 text-slate-300 hover:border-slate-700'
              }`}
            >
              <div className="font-bold text-sm text-white mb-0.5">{r.title}</div>
              <div className="text-xs text-slate-400">{r.desc}</div>
            </button>
          ))}
        </div>
      </div>

      {/* Diagnostic Verdict Box */}
      <div className="p-6 sm:p-8 rounded-2xl bg-gradient-to-b from-slate-900 to-navy-950 border border-slate-800 shadow-2xl">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 mb-4 border-b border-slate-800">
          <div>
            <span className="text-xs uppercase tracking-wider text-slate-500 font-semibold">Diagnostic Verdict</span>
            <h3 className="text-2xl font-black text-white mt-1">{verdict.verdict}</h3>
          </div>
          <span className={`text-xs px-3 py-1 rounded-full border font-bold uppercase ${verdict.badgeClass}`}>
            Evidence Check
          </span>
        </div>

        <h4 className="text-lg font-bold text-white mb-3">{verdict.title}</h4>
        <p className="text-sm text-slate-300 mb-6 leading-relaxed">{verdict.explanation}</p>

        <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
          <div className="text-xs uppercase tracking-wider font-bold text-slate-400 mb-3">
            What you should do right now:
          </div>
          <div className="space-y-2.5 text-xs text-slate-300">
            {verdict.actionableAdvice.map((adv, idx) => (
              <div key={idx} className="flex items-start space-x-2.5">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                <span className="leading-relaxed">{adv}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
