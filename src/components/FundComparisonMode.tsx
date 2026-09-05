import React, { useState } from 'react'
import { FundSnapshot, SuitabilityProfile } from '../engine/types'
import { computePortfolioOverlap } from '../engine/portfolio'
import { computeInvestmentDecision } from '../engine/decision'
import { Scale, Check, AlertCircle, ArrowRight, ShieldCheck, TrendingUp, DollarSign } from 'lucide-react'

interface FundComparisonModeProps {
  funds: FundSnapshot[]
  profile: SuitabilityProfile
}

export const FundComparisonMode: React.FC<FundComparisonModeProps> = ({ funds, profile }) => {
  const [fundAId, setFundAId] = useState<string>('PPFAS_FLEXI')
  const [fundBId, setFundBId] = useState<string>('MIRAE_LARGE')

  const fundA = funds.find((f) => f.internal_id === fundAId) || funds[0]
  const fundB = funds.find((f) => f.internal_id === fundBId) || funds[1] || funds[0]

  const overlap = computePortfolioOverlap(fundA.internal_id, fundB.internal_id)
  const decisionA = computeInvestmentDecision(profile, fundA)
  const decisionB = computeInvestmentDecision(profile, fundB)

  // Comparative Suitability Assessment
  const getSuitabilityVerdict = () => {
    if (fundA.internal_id === fundB.internal_id) {
      return {
        winner: 'Same Fund Selected',
        reason: 'Please select two different funds to compare their characteristics.'
      }
    }

    // Evaluate based on user horizon & risk profile
    if (profile.horizon === '1-3Y' || profile.horizon === '<1Y') {
      if (fundA.category.includes('Liquid') || fundA.category.includes('Hybrid')) {
        return {
          winner: fundA.scheme_name.split(' - ')[0],
          reason: `${fundA.scheme_name.split(' - ')[0]} provides lower downside volatility (${fundA.vol_30d}% vs ${fundB.vol_30d}%), making it much safer for your shorter timeline.`
        }
      }
      if (fundB.category.includes('Liquid') || fundB.category.includes('Hybrid')) {
        return {
          winner: fundB.scheme_name.split(' - ')[0],
          reason: `${fundB.scheme_name.split(' - ')[0]} provides lower downside volatility (${fundB.vol_30d}% vs ${fundA.vol_30d}%), making it safer for your timeline.`
        }
      }
    }

    if (fundA.fund_quality_score > fundB.fund_quality_score + 5) {
      return {
        winner: fundA.scheme_name.split(' - ')[0],
        reason: `Higher overall quality score (${fundA.fund_quality_score} vs ${fundB.fund_quality_score}) with superior risk-adjusted Sortino (${fundA.rolling_sortino_1y} vs ${fundB.rolling_sortino_1y}) and contained drawdowns.`
      }
    } else if (fundB.fund_quality_score > fundA.fund_quality_score + 5) {
      return {
        winner: fundB.scheme_name.split(' - ')[0],
        reason: `Higher overall quality score (${fundB.fund_quality_score} vs ${fundA.fund_quality_score}) with superior risk-adjusted Sortino (${fundB.rolling_sortino_1y} vs ${fundA.rolling_sortino_1y}) and contained drawdowns.`
      }
    }

    return {
      winner: 'Both Funds Are Viable Under Different Allocations',
      reason: `Both funds demonstrate strong execution within their respective categories (${fundA.category} vs ${fundB.category}). Overlap is ${overlap.overlapPct}%.`
    }
  }

  const verdict = getSuitabilityVerdict()

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
      {/* Header */}
      <div className="text-center max-w-2xl mx-auto mb-8">
        <div className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-full bg-teal-500/10 border border-teal-500/20 text-teal-400 text-xs font-semibold uppercase tracking-wider mb-3">
          <Scale className="w-3.5 h-3.5" />
          <span>Head-to-Head Decision Support</span>
        </div>
        <h2 className="text-3xl font-extrabold text-white tracking-tight mb-2">
          Compare Fund A vs Fund B
        </h2>
        <p className="text-sm text-slate-400">
          We don’t just rank raw past returns. We evaluate downside risk, rolling consistency,
          expense drag, and which fund actually fits your stated goal.
        </p>
      </div>

      {/* Selectors */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
        {/* Fund A Selector */}
        <div className="p-4 rounded-xl bg-slate-900 border border-slate-800">
          <label className="block text-xs font-semibold uppercase tracking-wider text-emerald-400 mb-2">
            Fund A (Primary Candidate)
          </label>
          <select
            value={fundAId}
            onChange={(e) => setFundAId(e.target.value)}
            className="w-full p-2.5 rounded-lg bg-slate-950 border border-slate-700 text-sm font-bold text-white focus:outline-none focus:border-emerald-500 cursor-pointer"
          >
            {funds.map((f) => (
              <option key={f.internal_id} value={f.internal_id}>
                {f.scheme_name.split(' - ')[0]} ({f.category})
              </option>
            ))}
          </select>
        </div>

        {/* Fund B Selector */}
        <div className="p-4 rounded-xl bg-slate-900 border border-slate-800">
          <label className="block text-xs font-semibold uppercase tracking-wider text-teal-400 mb-2">
            Fund B (Alternative Candidate)
          </label>
          <select
            value={fundBId}
            onChange={(e) => setFundBId(e.target.value)}
            className="w-full p-2.5 rounded-lg bg-slate-950 border border-slate-700 text-sm font-bold text-white focus:outline-none focus:border-teal-500 cursor-pointer"
          >
            {funds.map((f) => (
              <option key={f.internal_id} value={f.internal_id}>
                {f.scheme_name.split(' - ')[0]} ({f.category})
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Suitability Recommendation Verdict Box */}
      <div className="p-6 rounded-2xl bg-gradient-to-r from-slate-900 via-slate-900 to-navy-950 border border-slate-800 shadow-xl mb-8">
        <div className="flex items-center space-x-2 text-xs uppercase font-bold tracking-wider text-emerald-400 mb-1">
          <ShieldCheck className="w-4 h-4" />
          <span>Goal & Suitability Assessment (Horizon: {profile.horizon})</span>
        </div>
        <h3 className="text-xl font-bold text-white mb-2">
          Recommended: {verdict.winner}
        </h3>
        <p className="text-sm text-slate-300 leading-relaxed">{verdict.reason}</p>
        <div className="mt-4 pt-4 border-t border-slate-800 flex items-center justify-between text-xs text-slate-400">
          <span>Mutual Fund Overlap: <strong className="text-white">{overlap.overlapPct}%</strong></span>
          <span className="italic">Avoid absolute marketing claims like "Best Fund in India".</span>
        </div>
      </div>

      {/* Side-by-Side Quantitative Matrix */}
      <div className="rounded-2xl bg-slate-900 border border-slate-800 shadow-xl overflow-hidden mb-8">
        <div className="px-6 py-4 border-b border-slate-800 bg-slate-900/60 font-bold text-sm text-white">
          Comprehensive Decision Comparison Matrix
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left">
            <thead className="bg-slate-950 text-slate-400 border-b border-slate-800 uppercase tracking-wider">
              <tr>
                <th className="py-3 px-4">Metric / Dimension</th>
                <th className="py-3 px-4 text-emerald-300 font-bold">{fundA.scheme_name.split(' - ')[0]}</th>
                <th className="py-3 px-4 text-teal-300 font-bold">{fundB.scheme_name.split(' - ')[0]}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-300">
              <tr>
                <td className="py-3 px-4 font-semibold text-slate-400">Category</td>
                <td className="py-3 px-4">{fundA.category}</td>
                <td className="py-3 px-4">{fundB.category}</td>
              </tr>
              <tr>
                <td className="py-3 px-4 font-semibold text-slate-400">Current Next Move Signal</td>
                <td className="py-3 px-4 font-bold text-emerald-400">{decisionA.signal}</td>
                <td className="py-3 px-4 font-bold text-teal-400">{decisionB.signal}</td>
              </tr>
              <tr>
                <td className="py-3 px-4 font-semibold text-slate-400">Fund Quality Score (Transparent)</td>
                <td className="py-3 px-4 font-bold text-white">{fundA.fund_quality_score} / 100</td>
                <td className="py-3 px-4 font-bold text-white">{fundB.fund_quality_score} / 100</td>
              </tr>
              <tr>
                <td className="py-3 px-4 font-semibold text-slate-400">1-Year Return</td>
                <td className="py-3 px-4 text-emerald-400 font-bold">+{fundA.ret_1y}%</td>
                <td className="py-3 px-4 text-teal-400 font-bold">+{fundB.ret_1y}%</td>
              </tr>
              <tr>
                <td className="py-3 px-4 font-semibold text-slate-400">3-Year Annualized CAGR</td>
                <td className="py-3 px-4 font-bold text-white">+{fundA.ret_3y_cagr}%</td>
                <td className="py-3 px-4 font-bold text-white">+{fundB.ret_3y_cagr}%</td>
              </tr>
              <tr>
                <td className="py-3 px-4 font-semibold text-slate-400">Current Drawdown from Peak</td>
                <td className="py-3 px-4 text-slate-300">{fundA.current_drawdown}%</td>
                <td className="py-3 px-4 text-slate-300">{fundB.current_drawdown}%</td>
              </tr>
              <tr>
                <td className="py-3 px-4 font-semibold text-slate-400">30-Day Realized Volatility</td>
                <td className="py-3 px-4">{fundA.vol_30d}%</td>
                <td className="py-3 px-4">{fundB.vol_30d}%</td>
              </tr>
              <tr>
                <td className="py-3 px-4 font-semibold text-slate-400">Sortino Ratio (Downside Efficiency)</td>
                <td className="py-3 px-4 font-bold text-white">{fundA.rolling_sortino_1y}</td>
                <td className="py-3 px-4 font-bold text-white">{fundB.rolling_sortino_1y}</td>
              </tr>
              <tr>
                <td className="py-3 px-4 font-semibold text-slate-400">Expense Ratio (Direct Plan)</td>
                <td className="py-3 px-4 font-bold text-white">{fundA.expense_ratio}% p.a.</td>
                <td className="py-3 px-4 font-bold text-white">{fundB.expense_ratio}% p.a.</td>
              </tr>
              <tr>
                <td className="py-3 px-4 font-semibold text-slate-400">AUM (Asset Size)</td>
                <td className="py-3 px-4">₹{fundA.aum_cr.toLocaleString('en-IN')} Cr</td>
                <td className="py-3 px-4">₹{fundB.aum_cr.toLocaleString('en-IN')} Cr</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
