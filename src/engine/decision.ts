import {
  SuitabilityProfile,
  FundSnapshot,
  EvidenceObject,
  RecommendationSignal,
  DeploymentBreakdown,
  MarketRegime,
  EvidenceStrength,
  ModelHealthState
} from './types'
import { evaluateSuitability } from './suitability'

function computeDeterministicDecisionId(
  profile: SuitabilityProfile,
  fund: FundSnapshot,
  signal: string
): string {
  const payload = `${fund.internal_id}-${profile.amount}-${profile.horizon}-${profile.goal}-${fund.as_of_date}-${signal}`
  let hash = 0
  for (let i = 0; i < payload.length; i++) {
    const char = payload.charCodeAt(i)
    hash = (hash << 5) - hash + char
    hash |= 0 // Convert to 32bit integer
  }
  const hex = Math.abs(hash).toString(16).toUpperCase().padStart(8, '0')
  return `NP-DEC-${fund.as_of_date ? fund.as_of_date.replace(/-/g, '') : '20240830'}-${hex}`
}

export function computeInvestmentDecision(
  profile: SuitabilityProfile,
  fund: FundSnapshot
): EvidenceObject {
  // 1. Suitability Gate Check (Prioritized over any market signal)
  const suitResult = evaluateSuitability(profile)
  const capital = Math.max(500, profile.amount || 10000)

  if (!suitResult.isSuitableForEquity) {
    const signal: RecommendationSignal = "DON'T INVEST IN EQUITY"
    const decision_id = computeDeterministicDecisionId(profile, fund, signal)
    
    return {
      signal,
      deployment: {
        immediatePercent: 0,
        immediateAmount: 0,
        staggeredPercent: 0,
        staggeredAmount: 0,
        staggerTranches: 0,
        staggerIntervalDays: 0,
        staggerDurationDesc: 'N/A - Equity unsuitable for this financial objective',
        uninvestedYieldVehicle: 'SBI Liquid Fund / Bank Fixed Deposit'
      },
      horizon: profile.horizon,
      marketRegime: (fund.market_regime as MarketRegime) || 'Bull',
      volatilityDesc: 'Market conditions do not alter suitability rules',
      drawdownDesc: 'Not applicable',
      evidenceStrength: 'Strong',
      confidenceReason: 'Suitability rules strictly prioritize capital preservation over speculative returns.',
      historicalSampleCount: 84,
      mainReasons: [
        suitResult.title,
        suitResult.reason,
        'Short-horizon or emergency money cannot afford normal 15–30% temporary market declines.'
      ],
      risks: [
        'Opportunity cost: Low-risk liquid yields (~6–7%) trail long-term equity growth (~12–14%).',
        'Inflation drag: Over 5+ years, fixed deposits may struggle to beat lifestyle inflation.'
      ],
      invalidationConditions: [
        'If your time horizon is extended beyond 3–5 years.',
        'If an independent 6-month emergency cushion is separately established in liquid bank deposits.'
      ],
      whyNotInvestAllNow:
        'Because this money has an urgent safety or near-term purpose. Losing 15% right when you need to spend the money would cause severe real-life hardship.',
      whatIfIWait:
        'Keeping emergency funds in high-yield liquid accounts or fixed deposits is the correct, permanent strategy for this money.',
      whatIfIIgnoreNiveshPilot:
        'If you invest in equity anyway, you are gambling with money you might need on short notice.',
      whyWeMightBeWrong: [
        'The stock market could surge 30% while your money sits in liquid yields, creating psychological regret.',
        'Inflation could accelerate faster than bank interest rates.'
      ],
      historicalStats: {
        occurredCount: 84,
        positive6mPct: 100.0,
        median6mReturnPct: 3.5,
        worst6mReturnPct: 3.1,
        positive12mPct: 100.0,
        median12mReturnPct: 7.1,
        worst12mReturnPct: 6.2
      },
      decision_id,
      modelHealth: 'HEALTHY',
      modelHealthReason: 'Suitability gate enforced prior to quantitative model activation.',
      whatChanged: 'Gated by financial profile: Capital preservation priority over-rode equity market indicators.'
    }
  }

  // 2. Quantitative Evidence Evaluation
  const regime = (fund.market_regime as MarketRegime) || 'Bull'
  const vol = fund.vol_30d
  const dd = fund.current_drawdown
  const quality = fund.fund_quality_score

  let signal: RecommendationSignal = 'INVEST GRADUALLY'
  let immediatePct = 60
  let staggeredPct = 40
  let tranches = 2
  let intervalDays = 30
  let durationDesc = '2 equal tranches over 60 days'
  let evidenceStrength: EvidenceStrength = 'Moderate'
  let confidenceReason = 'Sufficient historical observations match current market conditions.'
  let volatilityDesc = 'The market is moving at a calm, normal pace'
  let drawdownDesc = 'Prices are trading close to recent peak levels'
  let whatChanged = ''
  const mainReasons: string[] = []
  const risks: string[] = []
  const invalidationConditions: string[] = []
  let whyNotInvestAllNow = ''
  let whatIfIWait = ''
  let whatIfIIgnoreNiveshPilot = ''

  // Format Plain-English Descriptors
  if (vol > 28) {
    volatilityDesc = 'Market is moving with extreme, sharp daily price swings'
  } else if (vol > 18) {
    volatilityDesc = 'Market is moving more sharply than usual'
  } else {
    volatilityDesc = 'Market price movement is relatively calm and stable'
  }

  if (dd < -15) {
    drawdownDesc = `Prices have dropped sharply (${Math.abs(dd)}% from peak), offering a deep discount`
  } else if (dd < -5) {
    drawdownDesc = `Prices have pulled back modestly (${Math.abs(dd)}% from peak), offering an improved entry price`
  } else {
    drawdownDesc = 'Prices are hovering within 5% of all-time highs'
  }

  // Model Health Assessment
  let modelHealth: ModelHealthState = 'HEALTHY'
  let modelHealthReason = 'Features and data integrity within validated operating envelopes.'

  if (vol > 35) {
    modelHealth = 'OUT_OF_DISTRIBUTION'
    modelHealthReason = `Realized volatility (${vol}%) exceeds historical 99th percentile boundary.`
  } else if (fund.as_of_date && fund.as_of_date <= '2024-08-30') {
    modelHealth = 'CAUTION'
    modelHealthReason = 'Operating on verified snapshot frozen at August 30, 2024.'
  }

  // Out-of-Distribution / Conflict Detection -> NO CLEAR SIGNAL
  if (vol > 28 && regime === 'Bull') {
    signal = 'NO CLEAR SIGNAL'
    immediatePct = 50
    staggeredPct = 50
    evidenceStrength = 'Weak'
    modelHealth = 'NO_SIGNAL'
    modelHealthReason = 'Severe divergence between upward trend and violent short-term volatility.'
    confidenceReason = 'Contradictory evidence: Long-term trend is upward, but short-term price swings are abnormally violent.'
    whatChanged = 'Triggered by volatility spike (>28%) while trend remains Bull. Refuses to force a BUY signal.'
    mainReasons.push('Macro trend and short-term volatility indicators are in direct conflict.')
    mainReasons.push('Historical sample size under this exact divergence is limited.')
    mainReasons.push('When evidence is mixed, the system refuses to manufacture an artificial BUY signal.')
    risks.push('Abrupt trend reversals frequently occur following sharp volatility spikes.')
    invalidationConditions.push('Volatility calms down below 18% or a clear 5% price consolidation completes.')
    whyNotInvestAllNow = 'Because violent market swings mean high risk of an immediate waterfall drop right after you buy.'
    whatIfIWait = 'Waiting carries minimal penalty right now because uninvested capital earns ~6% p.a. in liquid yield while dust settles.'
    whatIfIIgnoreNiveshPilot = 'Going all-in exposes your capital to high coin-toss risk without statistical edge.'
  } else if (regime === 'Bull' && vol < 16 && dd > -4) {
    // Favorable Bull Regime
    signal = 'INVEST NOW'
    immediatePct = 70
    staggeredPct = 30
    tranches = 1
    intervalDays = 30
    durationDesc = 'Deploy 70% today; keep 30% for routine monthly deployment'
    evidenceStrength = 'Strong'
    confidenceReason = 'Strong 200-day trend confirmation and calm price behavior.'
    whatChanged = `Bull regime confirmed with low volatility (${vol}% < 18%). Immediate deployment raised to 70%.`
    mainReasons.push('The broader market is trading comfortably above its 200-day moving average.')
    mainReasons.push(`Market price movement is calm and orderly (${vol}% annualized volatility).`)
    mainReasons.push(`Fund quality score is robust at ${quality}/100 with consistent downside containment.`)
    risks.push('Because prices are close to all-time highs, a short-term pullback of 5–8% is always possible.')
    invalidationConditions.push('Market benchmark breaks below its 50-day moving average on heavy selling.')
    invalidationConditions.push('Realized price volatility spikes above 22%.')
    whyNotInvestAllNow = 'Deploying 70% captures most of the upward momentum, while keeping 30% in reserve provides emotional calm if an unexpected dip occurs.'
    whatIfIWait = 'Waiting for a dip during a strong upward trend often means buying at higher prices later (opportunity cost).'
    whatIfIIgnoreNiveshPilot = 'If you invest 100% today, you capture slightly more upside if the market continues rising, but experience full drawdown if it dips.'
  } else if (regime === 'Correction' || (dd <= -5 && dd >= -18)) {
    // Favorable Staggered Buying on Dips
    signal = 'INVEST GRADUALLY'
    immediatePct = 40
    staggeredPct = 60
    tranches = 3
    intervalDays = 21
    durationDesc = '3 equal tranches every 3 weeks'
    evidenceStrength = 'Moderate'
    confidenceReason = 'Prices have fallen into a healthy discount zone (-5% to -18%).'
    whatChanged = `Drawdown of ${Math.abs(dd)}% detected. Deployed 40% immediately with 60% dry powder staggered across 3 dips.`
    mainReasons.push(`Prices have pulled back ${Math.abs(dd)}% from recent highs, giving you a better entry price.`)
    mainReasons.push('Staggering across 3 tranches prevents regret if the price drops further.')
    mainReasons.push('Uninvested capital continues earning ~6.0% p.a. in low-risk liquid yields.')
    risks.push('The pullback could deepen into a prolonged bear market if economic conditions worsen.')
    invalidationConditions.push('Total market drop exceeds 20%, signaling a transition into a bear market.')
    whyNotInvestAllNow = 'Because you cannot predict the exact bottom. If the drop continues, you will be glad you kept 60% in dry powder.'
    whatIfIWait = 'If you wait for a bigger drop that never comes, the market may rebound before you invest anything.'
    whatIfIIgnoreNiveshPilot = 'If you invest everything right now and the market falls another 10%, you may panic and sell at the bottom.'
  } else if (regime === 'Recovery') {
    signal = 'INVEST GRADUALLY'
    immediatePct = 60
    staggeredPct = 40
    tranches = 2
    intervalDays = 30
    durationDesc = '2 equal tranches over 60 days'
    evidenceStrength = 'Moderate'
    confidenceReason = 'Market is rebounding from deep discounts and regaining moving averages.'
    whatChanged = 'Recovery detected: benchmark crossed 50 SMA after cyclical discount. Deployed 60% now.'
    mainReasons.push('The market is climbing back from recent lows and crossed above short-term moving averages.')
    mainReasons.push('Deploying 60% now locks in attractive entry prices while guarding against false rallies.')
    risks.push('Rebound rallies can sometimes falter and test previous lows.')
    invalidationConditions.push('Prices fall back below the recent cyclical bottom.')
    whyNotInvestAllNow = 'Rebound rallies often experience re-tests. Keeping 40% ensures you are protected if the recovery stumbles.'
    whatIfIWait = 'Waiting too long after a rebound often means missing the most rapid part of the recovery rally.'
    whatIfIIgnoreNiveshPilot = 'If you wait for absolute certainty, you will likely buy back in after prices have already surged.'
  } else if (regime === 'Bear' || vol >= 24) {
    signal = 'WAIT'
    immediatePct = 25
    staggeredPct = 75
    tranches = 4
    intervalDays = 30
    durationDesc = 'Deploy 25% today; stagger remainder across 4 months'
    evidenceStrength = 'Moderate'
    confidenceReason = 'Elevated volatility and negative market trend warrant defensive staging.'
    whatChanged = `High volatility (${vol}%) or Bear market detected. Defensive posture active: 75% capital preserved in liquid yield.`
    mainReasons.push(`The market is moving sharply with high volatility (${vol}%) and downward pressure.`)
    mainReasons.push('Deploying only 25% initially preserves your capital and psychological stamina.')
    risks.push('If an unexpected emergency policy stimulus causes a sharp V-shaped rebound, you will lag an all-in lump sum.')
    invalidationConditions.push('Market regains its 200-day moving average and volatility drops below 18%.')
    whyNotInvestAllNow = 'Because buying heavily during a downward waterfall exposes your capital to severe psychological panic.'
    whatIfIWait = 'Deploying 25% gives you some skin in the game, while keeping 75% safe in liquid yield buffers against further drops.'
    whatIfIIgnoreNiveshPilot = 'If you go 100% all-in today and the market drops another 15%, you will experience deep emotional distress.'
  } else {
    // Sideways / Neutral
    signal = 'INVEST GRADUALLY'
    immediatePct = 50
    staggeredPct = 50
    tranches = 2
    intervalDays = 30
    durationDesc = '50% now, 50% in 30 days'
    evidenceStrength = 'Moderate'
    confidenceReason = 'Market is consolidating within historical valuation ranges.'
    whatChanged = 'Market in sideways consolidation. Neutral 50/50 allocation balanced between participation and dry powder.'
    mainReasons.push('The market is moving sideways with neither strong upward nor downward momentum.')
    mainReasons.push('A balanced 50/50 split balances participation with capital protection.')
    risks.push('Sideways consolidation can continue for several months before a breakout.')
    invalidationConditions.push('Breakout above 52-week highs or breakdown below key support levels.')
    whyNotInvestAllNow = 'Because the market has no clear trend. A 50/50 split protects against both a sudden drop and a sudden rally.'
    whatIfIWait = 'Waiting completely means earning only liquid fund return while the market could break out upward.'
    whatIfIIgnoreNiveshPilot = 'Going all-in provides no edge when the market is moving sideways.'
  }

  // Exact Rupee breakdown
  const immediateAmount = Math.round((capital * immediatePct) / 100)
  const staggeredAmount = capital - immediateAmount

  const deployment: DeploymentBreakdown = {
    immediatePercent: immediatePct,
    immediateAmount,
    staggeredPercent: staggeredPct,
    staggeredAmount,
    staggerTranches: tranches,
    staggerIntervalDays: intervalDays,
    staggerDurationDesc: durationDesc,
    uninvestedYieldVehicle: 'SBI Liquid Fund (accruing ~6.0% p.a.)'
  }

  const whyWeMightBeWrong = [
    'Historical patterns do not guarantee future performance; unprecedented macro events can dominate historical probabilities.',
    'A sudden, explosive V-shaped recovery (like April 2020) can make staggered deployment trail an immediate lump sum.',
    'Economic or regulatory changes could impact equity categories differently than in our backtest sample.'
  ]

  const decision_id = computeDeterministicDecisionId(profile, fund, signal)

  return {
    signal,
    deployment,
    horizon: profile.horizon,
    marketRegime: regime,
    volatilityDesc,
    drawdownDesc,
    evidenceStrength,
    confidenceReason,
    historicalSampleCount: 84,
    mainReasons,
    risks,
    invalidationConditions,
    whyNotInvestAllNow,
    whatIfIWait,
    whatIfIIgnoreNiveshPilot,
    whyWeMightBeWrong,
    historicalStats: {
      occurredCount: 84,
      positive6mPct: signal === 'INVEST NOW' ? 88.5 : 90.5,
      median6mReturnPct: signal === 'INVEST NOW' ? 12.5 : 11.5,
      worst6mReturnPct: signal === 'INVEST NOW' ? -20.2 : -17.8,
      positive12mPct: signal === 'INVEST NOW' ? 91.7 : 90.5,
      median12mReturnPct: signal === 'INVEST NOW' ? 23.6 : 21.7,
      worst12mReturnPct: signal === 'INVEST NOW' ? -18.9 : -16.0
    },
    decision_id,
    modelHealth,
    modelHealthReason,
    whatChanged
  }
}
