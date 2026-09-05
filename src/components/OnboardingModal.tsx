import React, { useState } from 'react'
import {
  SuitabilityProfile,
  InvestmentHorizon,
  InvestmentGoal,
  RiskReaction,
  RiskCapacity
} from '../engine/types'
import { X, ArrowRight, ArrowLeft, CheckCircle2, ShieldAlert, Sparkles, ShieldCheck } from 'lucide-react'
import { evaluateSuitability } from '../engine/suitability'

interface OnboardingModalProps {
  isOpen: boolean
  onClose: () => void
  currentProfile: SuitabilityProfile
  onSaveProfile: (profile: SuitabilityProfile) => void
}

export const OnboardingModal: React.FC<OnboardingModalProps> = ({
  isOpen,
  onClose,
  currentProfile,
  onSaveProfile
}) => {
  const [step, setStep] = useState(1)
  const [profile, setProfile] = useState<SuitabilityProfile>({ ...currentProfile })
  const [customAmount, setCustomAmount] = useState<string>('')
  const [isCustom, setIsCustom] = useState(false)

  if (!isOpen) return null

  const presetAmounts = [500, 1000, 5000, 10000, 25000, 50000, 100000]

  const horizons: { label: string; value: InvestmentHorizon; note: string }[] = [
    { label: 'Less than 1 year', value: '<1Y', note: 'Immediate liquidity needed' },
    { label: '1–3 years', value: '1-3Y', note: 'Short-medium term goal' },
    { label: '3–5 years', value: '3-5Y', note: 'Medium term runway' },
    { label: '5–10 years', value: '5-10Y', note: 'Long term compounding' },
    { label: '10+ years', value: '10Y+', note: 'Very long term wealth creation' }
  ]

  const goals: { label: string; value: InvestmentGoal }[] = [
    { label: 'Emergency reserve (Safety cushion)', value: 'Emergency reserve' },
    { label: 'Wealth creation (General growth)', value: 'Wealth creation' },
    { label: 'Retirement (Long term)', value: 'Retirement' },
    { label: 'House purchase or down payment', value: 'House' },
    { label: 'Education fund', value: 'Education' },
    { label: 'Car or major lifestyle purchase', value: 'Car' },
    { label: 'Other personal objective', value: 'Other' }
  ]

  const capacityOptions = [
    {
      label: 'Fully Funded (6+ months emergency reserve)',
      capacity: 'High' as RiskCapacity,
      hasBuffer: true,
      desc: 'I have an independent bank buffer to handle unexpected life expenses without touching my investments.'
    },
    {
      label: 'Partially Funded (2–3 months buffer)',
      capacity: 'Moderate' as RiskCapacity,
      hasBuffer: true,
      desc: 'I have some emergency liquidity, but a prolonged crisis would strain my finances.'
    },
    {
      label: 'No Emergency Buffer Yet',
      capacity: 'Low' as RiskCapacity,
      hasBuffer: false,
      desc: 'This money would be needed if an unexpected medical or career disruption occurs.'
    }
  ]

  const riskOptions: { label: string; value: RiskReaction; desc: string }[] = [
    { label: 'Sell immediately', value: 'Sell immediately', desc: 'I cannot bear to see paper losses on my capital.' },
    { label: 'Feel uncomfortable but hold', value: 'Feel uncomfortable but hold', desc: 'I would be anxious, but I know markets fluctuate.' },
    { label: 'Hold confidently', value: 'Hold confidently', desc: 'Temporary drawdowns are normal in equity investing.' },
    { label: 'Invest more', value: 'Invest more', desc: 'A drop is a buying opportunity at cheaper valuations.' }
  ]

  const handleFinish = () => {
    onSaveProfile(profile)
    onClose()
  }

  const liveSuitability = evaluateSuitability(profile)
  const totalSteps = 6

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-navy-950/80 backdrop-blur-sm animate-fade-in">
      <div className="relative w-full max-w-xl bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
          <div>
            <span className="text-xs uppercase tracking-wider font-semibold text-emerald-400">Step {step} of {totalSteps}</span>
            <h2 className="text-lg font-bold text-white">Suitability & Intent Check</h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Progress Bar */}
        <div className="w-full bg-slate-800 h-1">
          <div
            className="bg-emerald-500 h-1 transition-all duration-300"
            style={{ width: `${(step / totalSteps) * 100}%` }}
          />
        </div>

        {/* Step Content */}
        <div className="p-6">
          {/* Question 1: Amount */}
          {step === 1 && (
            <div>
              <h3 className="text-xl font-bold text-white mb-2">How much are you investing?</h3>
              <p className="text-sm text-slate-400 mb-6">
                Enter the amount of capital you have available for your next move.
              </p>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 mb-4">
                {presetAmounts.map((amt) => {
                  const isSelected = !isCustom && profile.amount === amt
                  return (
                    <button
                      key={amt}
                      type="button"
                      onClick={() => {
                        setIsCustom(false)
                        setProfile({ ...profile, amount: amt })
                      }}
                      className={`p-3 rounded-xl border text-sm font-semibold transition-all ${
                        isSelected
                          ? 'bg-emerald-600/20 border-emerald-500 text-emerald-300 shadow-sm'
                          : 'bg-slate-800/60 border-slate-700/60 text-slate-300 hover:border-slate-600 hover:bg-slate-800'
                      }`}
                    >
                      ₹{amt.toLocaleString('en-IN')}
                    </button>
                  )
                })}
                <button
                  type="button"
                  onClick={() => setIsCustom(true)}
                  className={`p-3 rounded-xl border text-sm font-semibold transition-all ${
                    isCustom
                      ? 'bg-emerald-600/20 border-emerald-500 text-emerald-300 shadow-sm'
                      : 'bg-slate-800/60 border-slate-700/60 text-slate-300 hover:border-slate-600 hover:bg-slate-800'
                  }`}
                >
                  Custom
                </button>
              </div>

              {isCustom && (
                <div className="mt-4">
                  <label className="block text-xs font-medium text-slate-400 mb-1">Enter custom amount in ₹</label>
                  <div className="relative">
                    <span className="absolute left-3.5 top-3 text-slate-400 font-bold">₹</span>
                    <input
                      type="number"
                      min="500"
                      step="500"
                      placeholder="e.g. 75000"
                      value={customAmount}
                      onChange={(e) => {
                        setCustomAmount(e.target.value)
                        const val = parseInt(e.target.value, 10)
                        if (!isNaN(val) && val > 0) {
                          setProfile({ ...profile, amount: val })
                        }
                      }}
                      className="w-full pl-8 pr-4 py-2.5 rounded-xl bg-slate-950 border border-slate-700 text-white focus:outline-none focus:border-emerald-500"
                    />
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Question 2: Horizon */}
          {step === 2 && (
            <div>
              <h3 className="text-xl font-bold text-white mb-2">When might you need this money?</h3>
              <p className="text-sm text-slate-400 mb-6">
                Equity investments require sufficient runway. Money needed urgently should not be in the stock market.
              </p>

              <div className="space-y-2.5">
                {horizons.map((h) => {
                  const isSelected = profile.horizon === h.value
                  return (
                    <button
                      key={h.value}
                      type="button"
                      onClick={() => setProfile({ ...profile, horizon: h.value })}
                      className={`w-full p-3.5 rounded-xl border text-left flex items-center justify-between transition-all ${
                        isSelected
                          ? 'bg-emerald-600/20 border-emerald-500 text-emerald-200'
                          : 'bg-slate-800/60 border-slate-700/60 text-slate-300 hover:border-slate-600 hover:bg-slate-800'
                      }`}
                    >
                      <div>
                        <div className="font-semibold text-sm text-white">{h.label}</div>
                        <div className="text-xs text-slate-400">{h.note}</div>
                      </div>
                      {isSelected && <CheckCircle2 className="w-5 h-5 text-emerald-400" />}
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          {/* Question 3: Goal */}
          {step === 3 && (
            <div>
              <h3 className="text-xl font-bold text-white mb-2">What is the goal?</h3>
              <p className="text-sm text-slate-400 mb-6">
                Your investment objective dictates whether equity risk is acceptable.
              </p>

              <div className="space-y-2">
                {goals.map((g) => {
                  const isSelected = profile.goal === g.value
                  return (
                    <button
                      key={g.value}
                      type="button"
                      onClick={() => setProfile({ ...profile, goal: g.value })}
                      className={`w-full p-3 rounded-xl border text-left flex items-center justify-between transition-all ${
                        isSelected
                          ? 'bg-emerald-600/20 border-emerald-500 text-emerald-200'
                          : 'bg-slate-800/60 border-slate-700/60 text-slate-300 hover:border-slate-600 hover:bg-slate-800'
                      }`}
                    >
                      <span className="font-medium text-sm text-white">{g.label}</span>
                      {isSelected && <CheckCircle2 className="w-5 h-5 text-emerald-400" />}
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          {/* Question 4: Risk Capacity (Financial Loss Absorption) */}
          {step === 4 && (
            <div>
              <h3 className="text-xl font-bold text-white mb-2">
                Do you have an emergency cash buffer?
              </h3>
              <p className="text-sm text-slate-400 mb-6">
                <strong>Financial Risk Capacity</strong>: How much loss can your household realistically absorb before being forced to sell at a loss?
              </p>

              <div className="space-y-2.5">
                {capacityOptions.map((c, i) => {
                  const isSelected = profile.riskCapacity === c.capacity && profile.hasEmergencyCushion === c.hasBuffer
                  return (
                    <button
                      key={i}
                      type="button"
                      onClick={() => setProfile({ ...profile, riskCapacity: c.capacity, hasEmergencyCushion: c.hasBuffer })}
                      className={`w-full p-3.5 rounded-xl border text-left flex items-center justify-between transition-all ${
                        isSelected
                          ? 'bg-emerald-600/20 border-emerald-500 text-emerald-200'
                          : 'bg-slate-800/60 border-slate-700/60 text-slate-300 hover:border-slate-600 hover:bg-slate-800'
                      }`}
                    >
                      <div>
                        <div className="font-semibold text-sm text-white">{c.label}</div>
                        <div className="text-xs text-slate-400">{c.desc}</div>
                      </div>
                      {isSelected && <CheckCircle2 className="w-5 h-5 text-emerald-400" />}
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          {/* Question 5: Risk Tolerance (Emotional Reaction) */}
          {step === 5 && (
            <div>
              <h3 className="text-xl font-bold text-white mb-2">
                What would you do if ₹10,000 temporarily became ₹8,000?
              </h3>
              <p className="text-sm text-slate-400 mb-6">
                <strong>Emotional Risk Tolerance</strong>: Temporary drawdowns of 10–25% happen routinely in Indian equities. How would you psychologically respond?
              </p>

              <div className="space-y-2.5">
                {riskOptions.map((r) => {
                  const isSelected = profile.riskReaction === r.value
                  return (
                    <button
                      key={r.value}
                      type="button"
                      onClick={() => setProfile({ ...profile, riskReaction: r.value })}
                      className={`w-full p-3.5 rounded-xl border text-left flex items-center justify-between transition-all ${
                        isSelected
                          ? 'bg-emerald-600/20 border-emerald-500 text-emerald-200'
                          : 'bg-slate-800/60 border-slate-700/60 text-slate-300 hover:border-slate-600 hover:bg-slate-800'
                      }`}
                    >
                      <div>
                        <div className="font-semibold text-sm text-white">{r.label}</div>
                        <div className="text-xs text-slate-400">{r.desc}</div>
                      </div>
                      {isSelected && <CheckCircle2 className="w-5 h-5 text-emerald-400" />}
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          {/* Question 6: Prior Investment Experience & Suitability Summary */}
          {step === 6 && (
            <div>
              <h3 className="text-xl font-bold text-white mb-2">Do you already invest?</h3>
              <p className="text-sm text-slate-400 mb-4">
                We never require brokerage logins or passwords. You can enter or import your holdings later.
              </p>

              <div className="grid grid-cols-2 gap-3 mb-6">
                <button
                  type="button"
                  onClick={() => setProfile({ ...profile, alreadyInvests: false })}
                  className={`p-4 rounded-xl border text-center transition-all ${
                    !profile.alreadyInvests
                      ? 'bg-emerald-600/20 border-emerald-500 text-emerald-300'
                      : 'bg-slate-800/60 border-slate-700/60 text-slate-300 hover:border-slate-600'
                  }`}
                >
                  <div className="font-bold text-base text-white">No, I'm new</div>
                  <div className="text-xs text-slate-400 mt-1">Starting my first investment</div>
                </button>
                <button
                  type="button"
                  onClick={() => setProfile({ ...profile, alreadyInvests: true })}
                  className={`p-4 rounded-xl border text-center transition-all ${
                    profile.alreadyInvests
                      ? 'bg-emerald-600/20 border-emerald-500 text-emerald-300'
                      : 'bg-slate-800/60 border-slate-700/60 text-slate-300 hover:border-slate-600'
                  }`}
                >
                  <div className="font-bold text-base text-white">Yes, I already invest</div>
                  <div className="text-xs text-slate-400 mt-1">I have existing mutual funds</div>
                </button>
              </div>

              {/* Live Suitability Gate Notice */}
              {!liveSuitability.isSuitableForEquity ? (
                <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-800/60 text-rose-200 text-xs leading-relaxed flex items-start space-x-3">
                  <ShieldAlert className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
                  <div>
                    <strong className="font-semibold block text-rose-300 mb-0.5">
                      Suitability Gate Alert: {liveSuitability.title}
                    </strong>
                    {liveSuitability.reason}
                  </div>
                </div>
              ) : (
                <div className="p-4 rounded-xl bg-emerald-950/40 border border-emerald-800/60 text-emerald-200 text-xs leading-relaxed flex items-start space-x-3">
                  <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
                  <div>
                    <strong className="font-semibold block text-emerald-300 mb-0.5">
                      Suitability Gate Passed
                    </strong>
                    Your timeline, emergency buffer, and financial objective provide appropriate safety margins for equity mutual fund deployment.
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer Navigation */}
        <div className="px-6 py-4 bg-slate-950 border-t border-slate-800 flex items-center justify-between">
          {step > 1 ? (
            <button
              onClick={() => setStep(step - 1)}
              className="px-4 py-2 rounded-lg text-sm text-slate-400 hover:text-white flex items-center space-x-1"
            >
              <ArrowLeft className="w-4 h-4" />
              <span>Back</span>
            </button>
          ) : (
            <div />
          )}

          {step < totalSteps ? (
            <button
              onClick={() => setStep(step + 1)}
              className="px-5 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-sm transition-colors flex items-center space-x-1.5 shadow-md shadow-emerald-950"
            >
              <span>Next</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          ) : (
            <button
              onClick={handleFinish}
              className="px-6 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-sm transition-colors flex items-center space-x-2 shadow-lg shadow-emerald-900/40"
            >
              <Sparkles className="w-4 h-4" />
              <span>Generate My Next Move</span>
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
