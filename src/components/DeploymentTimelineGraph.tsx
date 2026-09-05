import React, { useState } from 'react'
import {
  Clock,
  Shield,
  Layers,
  Sparkles,
  ArrowRight,
  TrendingUp,
  CheckCircle2,
  DollarSign
} from 'lucide-react'
import { DeploymentBreakdown } from '../engine/types'

interface DeploymentTimelineGraphProps {
  deployment: DeploymentBreakdown
  totalCapital: number
  fundName: string
}

export const DeploymentTimelineGraph: React.FC<DeploymentTimelineGraphProps> = ({
  deployment,
  totalCapital,
  fundName
}) => {
  const [selectedStep, setSelectedStep] = useState<number>(0)

  const formatINR = (val: number) =>
    new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0
    }).format(val)

  // Derive execution tranches based on deployment recommendation
  const immediateAmt = deployment.immediateAmount || Math.round(totalCapital * 0.7)
  const staggeredAmt = deployment.staggeredAmount || Math.round(totalCapital * 0.3)
  const tranchesCount = deployment.staggerTranches || 2

  // Timeline milestones
  const steps = [
    {
      day: 0,
      label: 'Day 0 (Today)',
      title: 'Initial Entry & Safe Buffer Setup',
      equityDeployed: immediateAmt,
      liquidCash: staggeredAmt,
      interestEarned: 0,
      desc: `Deploy ${formatINR(immediateAmt)} (${Math.round((immediateAmt / totalCapital) * 100)}%) into ${fundName}. Park ${formatINR(staggeredAmt)} in Liquid Overnight Fund earning 6.0% p.a.`
    },
    {
      day: 21,
      label: 'Day 21 (Week 3)',
      title: 'Observation Checkpoint',
      equityDeployed: immediateAmt,
      liquidCash: staggeredAmt,
      interestEarned: Math.round(staggeredAmt * 0.06 * (21 / 365)),
      desc: `Monitoring market volatility. Liquid buffer has accrued ~₹${Math.round(staggeredAmt * 0.06 * (21 / 365))} in risk-free yield while keeping dry powder ready.`
    },
    {
      day: 42,
      label: 'Day 42 (Week 6)',
      title: 'Scheduled Second Tranche Execution',
      equityDeployed: totalCapital,
      liquidCash: 0,
      interestEarned: Math.round(staggeredAmt * 0.06 * (42 / 365)),
      desc: `Transfer the remaining ${formatINR(staggeredAmt)} plus accrued interest into ${fundName}, completing 100% phased deployment.`
    }
  ]

  const active = steps[selectedStep]
  const equityPct = Math.round((active.equityDeployed / totalCapital) * 100)
  const cashPct = Math.max(0, 100 - equityPct)

  return (
    <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
        <div>
          <div className="flex items-center space-x-2">
            <Clock className="w-4 h-4 text-teal-400" />
            <h4 className="text-sm font-bold text-white">Dynamic Deployment Timeline & Flow</h4>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Step through the timeline to see how your {formatINR(totalCapital)} moves from safe cash into equity units.
          </p>
        </div>

        {/* Step Selector Pills */}
        <div className="flex items-center space-x-1.5 bg-slate-950 p-1 rounded-xl border border-slate-800 text-xs">
          {steps.map((s, idx) => (
            <button
              key={idx}
              onClick={() => setSelectedStep(idx)}
              className={`px-3 py-1.5 rounded-lg font-semibold transition-all ${
                selectedStep === idx
                  ? 'bg-teal-600 text-white shadow'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      {/* Visual Dynamic Asset Allocation Bar */}
      <div className="mb-4">
        <div className="flex justify-between text-xs font-semibold mb-1.5">
          <span className="text-emerald-400 flex items-center space-x-1">
            <span className="w-2 h-2 rounded-full bg-emerald-400" />
            <span>Target Fund ({equityPct}%): {formatINR(active.equityDeployed)}</span>
          </span>
          <span className="text-amber-400 flex items-center space-x-1">
            <span className="w-2 h-2 rounded-full bg-amber-400" />
            <span>Liquid Cash ({cashPct}%): {formatINR(active.liquidCash)}</span>
          </span>
        </div>

        {/* Stacked Progress Bar */}
        <div className="w-full h-3 bg-slate-950 rounded-full overflow-hidden flex border border-slate-800">
          <div
            style={{ width: `${equityPct}%` }}
            className="h-full bg-gradient-to-r from-emerald-600 to-teal-500 transition-all duration-500 ease-out"
          />
          <div
            style={{ width: `${cashPct}%` }}
            className="h-full bg-gradient-to-r from-amber-500 to-amber-600 transition-all duration-500 ease-out"
          />
        </div>
      </div>

      {/* Dynamic Step Detail Card */}
      <div className="p-4 rounded-xl bg-slate-950/70 border border-slate-800/80">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2">
          <span className="text-xs font-bold text-teal-300 flex items-center space-x-1.5">
            <CheckCircle2 className="w-3.5 h-3.5 text-teal-400" />
            <span>{active.title}</span>
          </span>
          {active.interestEarned > 0 && (
            <span className="text-[11px] font-semibold text-amber-300 bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/20">
              +{formatINR(active.interestEarned)} risk-free liquid interest accrued
            </span>
          )}
        </div>
        <p className="text-xs text-slate-300 leading-relaxed">{active.desc}</p>
      </div>
    </div>
  )
}
