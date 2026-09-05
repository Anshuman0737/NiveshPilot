import { SuitabilityProfile, SuitabilityGateResult } from './types'

/**
 * NiveshPilot Suitability Gate Engine
 * Enforces a strict, hierarchical priority evaluation sequence:
 * 1. Goal
 * 2. Time horizon
 * 3. Liquidity needs / Emergency cushion
 * 4. Risk Capacity (financial ability to absorb loss)
 * 5. Risk Tolerance (psychological/emotional reaction)
 * 
 * Never lets a favorable market regime override user suitability.
 */
export function evaluateSuitability(profile: SuitabilityProfile): SuitabilityGateResult {
  const { goal, horizon, hasEmergencyCushion, riskCapacity, riskReaction } = profile

  // Priority 1: Goal is Emergency Reserve
  if (goal === 'Emergency reserve') {
    return {
      isSuitableForEquity: false,
      gateTriggered: true,
      signalOverride: "DON'T INVEST IN EQUITY",
      title: 'Emergency Reserves Must Not Be Invested in Equity',
      reason:
        'An emergency fund protects you against sudden life shocks (medical expenses, job transition). Indian equity markets routinely experience drawdowns of 15% to 38%. You must never risk having to sell stocks at a loss in a personal emergency.',
      recommendedAlternative:
        'Park 100% of this capital in an ultra-low-risk Liquid Mutual Fund (e.g. SBI Liquid Fund) or a bank Fixed Deposit for instant liquidity without equity price volatility.'
    }
  }

  // Priority 2: Short Horizon (< 1 Year)
  if (horizon === '<1Y') {
    return {
      isSuitableForEquity: false,
      gateTriggered: true,
      signalOverride: "DON'T INVEST IN EQUITY",
      title: 'Time Horizon Is Too Short for Equity Mutual Funds',
      reason:
        'Over horizons under 12 months, equity returns are dominated by unpredictable short-term macro noise and sentiment shocks. Historical 1-year returns can swing widely. Equity is not a suitable short-term parking vehicle.',
      recommendedAlternative:
        'Consider an Arbitrage Fund or a Liquid Fund where capital stability takes priority over capital growth.'
    }
  }

  // Priority 3: Lack of Essential Emergency Cushion
  if (!hasEmergencyCushion && riskCapacity === 'Low') {
    return {
      isSuitableForEquity: false,
      gateTriggered: true,
      signalOverride: "DON'T INVEST IN EQUITY",
      title: 'Address Immediate Financial Safety Before Investing in Equity',
      reason:
        'You indicated you do not yet have an independent 6-month living-expense safety buffer and have low financial capacity to absorb losses. Starting equity without an emergency reserve forces panic-selling during ordinary life emergencies.',
      recommendedAlternative:
        'Direct this capital toward building your primary 6-month safety reserve in a high-interest savings or liquid fund first.'
    }
  }

  // Priority 4: Risk Capacity vs Horizon Conflict (1–3 Years + Low Capacity)
  if (horizon === '1-3Y' && riskCapacity === 'Low') {
    return {
      isSuitableForEquity: false,
      gateTriggered: true,
      signalOverride: "DON'T INVEST IN EQUITY",
      title: 'Financial Risk Capacity Is Too Low for a 1–3 Year Equity Window',
      reason:
        'Even if your psychological willingness to take risk is high, your financial situation cannot realistically absorb a temporary 15–20% portfolio dip within a 1–3 year timeframe.',
      recommendedAlternative:
        'Consider Conservative Hybrid or Short-Duration Debt funds to maintain capital stability with modest real returns.'
    }
  }

  // Priority 5: Low Emotional Risk Tolerance (Sell Immediately on 20% Dip)
  if (horizon === '1-3Y' && riskReaction === 'Sell immediately') {
    return {
      isSuitableForEquity: false,
      gateTriggered: true,
      signalOverride: "DON'T INVEST IN EQUITY",
      title: 'Emotional Reaction to Normal Market Fluctuations Conflicts with Equity',
      reason:
        'In equity investing, 10–20% temporary pullbacks are routine. Selling immediately during a decline locks in temporary paper drops into permanent, irreversible cash losses.',
      recommendedAlternative:
        'Consider building confidence with Conservative Debt or Balanced Advantage Funds with lower daily volatility before entering pure equity.'
    }
  }

  // Priority 6: Passed all Suitability Gates
  return {
    isSuitableForEquity: true,
    gateTriggered: false,
    title: 'Profile Suitable for Equity Mutual Funds',
    reason:
      'Your financial objective, time horizon, and emergency cushion provide appropriate safety margins to ride out standard market cycles.',
    recommendedAlternative: ''
  }
}
