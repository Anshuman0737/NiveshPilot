import {
  DirectionalForecast,
  ForecastHorizon,
  ComponentSubModels,
  ModelDisagreement,
  EventObservation
} from './types'

export interface CorePredictorFeatures {
  ret_5d?: number
  rsi_14?: number
  macd_hist?: number
  vol_30d?: number
  rel_strength_20d?: number
  drawdown?: number
  market_regime?: string
}

export const DAYS_MAP: Record<ForecastHorizon, number> = {
  '1D': 1,
  '5D': 5,
  '20D': 20,
  '60D': 60
}

export const DEFAULT_PLATT_PARAMS: [number, number] = [1.25, -0.05]

export function computeDirectionalForecastCore(
  features: CorePredictorFeatures,
  horizon: ForecastHorizon,
  events: EventObservation[] = [],
  customPlattParams?: [number, number] | null
): DirectionalForecast {
  const days = DAYS_MAP[horizon]

  // 1. Technical Score (-100 to +100)
  // Preserving legacy || semantics: RSI 0.0 -> 50.0, vol 0.0 -> 0.15
  const r5 = features.ret_5d || 0.0
  const rsi = features.rsi_14 || 50.0
  const macd = features.macd_hist || 0.0
  const vol = features.vol_30d || 0.15
  let techScore = (r5 * 400.0) + ((rsi - 50.0) * 0.8) + (macd * 35.0) - ((vol - 0.14) * 60.0)
  techScore = Math.max(-95.0, Math.min(95.0, techScore))

  // 2. Fundamental Score
  const rs20 = features.rel_strength_20d || 0.0
  const dd = features.drawdown || 0.0
  let fundScore = (rs20 * 550.0) + ((dd + 0.05) * 80.0)
  fundScore = Math.max(-90.0, Math.min(90.0, fundScore))

  // 3. Event / Information Surprise Score
  let eventScore = 0.0
  if (events && events.length > 0) {
    const topEvt = events[0]
    const surpriseScale = topEvt.surprise_pct / 10.0
    const sentFin = topEvt.sentiment_dimensions?.financial || 0.0
    eventScore = (surpriseScale * 35.0) + (sentFin * 45.0)
  }
  eventScore = Math.max(-95.0, Math.min(95.0, eventScore))

  // 4. Macro & Regime Score
  const regime = features.market_regime || 'Bull'
  const regimeWeights: Record<string, number> = {
    Bull: 35.0,
    Recovery: 22.0,
    Sideways: 5.0,
    Correction: -18.0,
    Bear: -42.0,
    'High-volatility': -35.0
  }
  const macroScore = regimeWeights[regime] || 0.0

  // 5. Cross-Asset Score
  let crossScore = 12.0
  if (regime.includes('High-volatility') || vol > 0.22) {
    crossScore = -28.0
  }

  // Operation order: components rounded BEFORE weighting
  const components: ComponentSubModels = {
    technical: +techScore.toFixed(1),
    fundamental: +fundScore.toFixed(1),
    event_news: +eventScore.toFixed(1),
    macro_regime: +macroScore.toFixed(1),
    cross_asset: +crossScore.toFixed(1)
  }

  // Horizon-dependent sub-model weighting
  let hWeights: Record<keyof ComponentSubModels, number>
  if (horizon === '1D') {
    hWeights = { technical: 0.30, event_news: 0.40, fundamental: 0.10, macro_regime: 0.10, cross_asset: 0.10 }
  } else if (horizon === '5D') {
    hWeights = { technical: 0.25, event_news: 0.35, fundamental: 0.15, macro_regime: 0.15, cross_asset: 0.10 }
  } else if (horizon === '20D') {
    hWeights = { technical: 0.15, event_news: 0.20, fundamental: 0.30, macro_regime: 0.20, cross_asset: 0.15 }
  } else {
    hWeights = { technical: 0.10, event_news: 0.10, fundamental: 0.40, macro_regime: 0.25, cross_asset: 0.15 }
  }

  const rawScore =
    components.technical * hWeights.technical +
    components.fundamental * hWeights.fundamental +
    components.event_news * hWeights.event_news +
    components.macro_regime * hWeights.macro_regime +
    components.cross_asset * hWeights.cross_asset

  const rawLogit = rawScore / 35.0

  // Platt scaling probability calibration
  const plattParams = customPlattParams || DEFAULT_PLATT_PARAMS
  const [A, B] = plattParams
  const calibratedBullProb = 1.0 / (1.0 + Math.exp(-(A * rawLogit + B)))

  const neutralBase = 0.20 - 0.08 * Math.abs(calibratedBullProb - 0.5)
  const pNeutral = Math.max(0.10, Math.min(0.28, neutralBase))
  const pRemaining = 1.0 - pNeutral

  const pBull = +(pRemaining * calibratedBullProb).toFixed(2)
  const pBear = +(pRemaining * (1.0 - calibratedBullProb)).toFixed(2)
  const finalNeutral = +(1.0 - pBull - pBear).toFixed(2)

  // Expected return %
  const retMult = horizon === '1D' ? 0.65 : horizon === '5D' ? 1.45 : horizon === '20D' ? 3.20 : 5.80
  const expectedReturn = +((pBull - pBear) * retMult).toFixed(2)

  // Direction classification
  let direction: DirectionalForecast['expected_direction'] = 'NEUTRAL / RANGE-BOUND'
  if (pBull >= 0.65) direction = 'STRONGLY BULLISH'
  else if (pBull >= 0.54) direction = 'MODERATELY BULLISH'
  else if (pBear >= 0.65) direction = 'STRONGLY BEARISH'
  else if (pBear >= 0.54) direction = 'MODERATELY BEARISH'

  // Model disagreement
  const compVals = Object.values(components)
  const meanComp = compVals.reduce((a, b) => a + b, 0) / compVals.length
  const variance = compVals.reduce((acc, v) => acc + Math.pow(v - meanComp, 2), 0) / compVals.length
  const std = +Math.sqrt(variance).toFixed(1)

  let consensusLevel: ModelDisagreement['consensus_level'] = 'Moderate Agreement'
  if (std < 18.0) consensusLevel = 'High Consensus'
  else if (std > 34.0) consensusLevel = 'High Disagreement'

  const probSeparation = Math.abs(pBull - pBear)
  let confidence: DirectionalForecast['confidence'] = 'LOW'
  if (probSeparation > 0.35 && std < 28.0) confidence = 'HIGH'
  else if (probSeparation > 0.15) confidence = 'MEDIUM'

  const signalQuality = +Math.min(10.0, Math.max(1.0, 5.0 + probSeparation * 6.0 - std * 0.05)).toFixed(1)

  // Top Drivers
  const topBullish: string[] = []
  const topBearish: string[] = []

  if (components.event_news > 20) {
    const topEvt = events[0]
    topBullish.push(`Event Surprise: ${topEvt?.surprise_category || 'Positive information shock'} (+${components.event_news} pts)`)
  } else if (components.event_news < -20) {
    topBearish.push(`Event reaction signal is subdued or negative (${components.event_news} pts)`)
  }

  if (components.technical > 15) {
    topBullish.push(`Technical momentum: RSI(${rsi.toFixed(0)}) & MACD trending positive`)
  } else if (components.technical < -15) {
    topBearish.push(`Technical weakness: Short-term price momentum decelerating`)
  }

  if (components.fundamental > 15) {
    topBullish.push(`Relative strength: Outperforming broad benchmark by +${(rs20 * 100).toFixed(1)}%`)
  } else if (components.fundamental < -15) {
    topBearish.push(`Lagging relative strength vs benchmark index (${(rs20 * 100).toFixed(1)}%)`)
  }

  if (components.macro_regime > 15) {
    topBullish.push(`Market Regime: Favorable ${regime} environment supporting trend continuation`)
  } else if (components.macro_regime < -10) {
    topBearish.push(`Macro headwinds: Elevated volatility and cautious regime conditioning`)
  }

  if (topBullish.length === 0) topBullish.push('Calm baseline volatility within normal parameters')
  if (topBearish.length === 0) topBearish.push('Range-bound consolidation resistance near recent swing high')

  return {
    horizon,
    days,
    probability_bullish: pBull,
    probability_neutral: finalNeutral,
    probability_bearish: pBear,
    expected_direction: direction,
    expected_return_pct: expectedReturn,
    confidence,
    signal_quality: signalQuality,
    model_disagreement: {
      components,
      dispersion_std: std,
      consensus_level: consensusLevel
    },
    top_bullish_drivers: topBullish,
    top_bearish_drivers: topBearish
  }
}
