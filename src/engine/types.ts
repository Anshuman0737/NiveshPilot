export type RecommendationSignal =
  | 'INVEST NOW'
  | 'INVEST GRADUALLY'
  | 'WAIT'
  | 'HOLD'
  | 'REVIEW'
  | 'DON\'T INVEST IN EQUITY'
  | 'NO CLEAR SIGNAL'

export type MarketRegime =
  | 'Bull'
  | 'Bear'
  | 'Correction'
  | 'Recovery'
  | 'Sideways'
  | 'High-volatility'
  | 'Unknown'

export type ModelConfidence = 'LOW' | 'MEDIUM' | 'HIGH'
export type EvidenceStrength = 'Strong' | 'Moderate' | 'Weak'
export type ModelHealthState = 'HEALTHY' | 'CAUTION' | 'DATA_ISSUE' | 'OUT_OF_DISTRIBUTION' | 'NO_SIGNAL'
export type ExplanationLevel = 'Beginner' | 'Intermediate' | 'Research'

export type InvestmentHorizon = '<1Y' | '1-3Y' | '3-5Y' | '5-10Y' | '10Y+'

export type InvestmentGoal =
  | 'Emergency reserve'
  | 'Car'
  | 'Education'
  | 'House'
  | 'Retirement'
  | 'Wealth creation'
  | 'Other'

export type RiskReaction =
  | 'Sell immediately'
  | 'Feel uncomfortable but hold'
  | 'Hold confidently'
  | 'Invest more'

export type RiskCapacity = 'Low' | 'Moderate' | 'High'

export interface SuitabilityProfile {
  amount: number
  horizon: InvestmentHorizon
  goal: InvestmentGoal
  riskCapacity: RiskCapacity          // Financial ability to absorb loss
  riskReaction: RiskReaction          // Psychological emotional tolerance
  hasEmergencyCushion: boolean        // Independent 6-month safety buffer
  alreadyInvests: boolean
}

export interface SuitabilityGateResult {
  isSuitableForEquity: boolean
  gateTriggered: boolean
  signalOverride?: RecommendationSignal
  title: string
  reason: string
  recommendedAlternative: string
}

export interface DeploymentBreakdown {
  immediatePercent: number
  immediateAmount: number
  staggeredPercent: number
  staggeredAmount: number
  staggerTranches: number
  staggerIntervalDays: number
  staggerDurationDesc: string
  uninvestedYieldVehicle: string
}

export interface HistoricalSignalStats {
  occurredCount: number
  positive6mPct: number
  median6mReturnPct: number
  worst6mReturnPct: number
  positive12mPct: number
  median12mReturnPct: number
  worst12mReturnPct: number
}

export interface EvidenceObject {
  signal: RecommendationSignal
  deployment: DeploymentBreakdown
  horizon: InvestmentHorizon
  marketRegime: MarketRegime
  volatilityDesc: string               // Plain-English description
  drawdownDesc: string                 // Plain-English description
  evidenceStrength: EvidenceStrength   // Qualitative evidence strength
  confidenceReason: string
  historicalSampleCount: number
  mainReasons: string[]
  risks: string[]
  invalidationConditions: string[]
  whyNotInvestAllNow: string           // "Why not the obvious option?"
  whatIfIWait: string                  // Trade-off of waiting
  whatIfIIgnoreNiveshPilot: string     // Counterfactual comparison
  whyWeMightBeWrong: string[]          // User trust feature
  historicalStats: HistoricalSignalStats
  decision_id: string                  // Deterministic replay token
  modelHealth: ModelHealthState        // HEALTHY | CAUTION | DATA_ISSUE | OUT_OF_DISTRIBUTION | NO_SIGNAL
  modelHealthReason: string            // Transparency on data freshness and drift
  whatChanged?: string                 // Explanation of change vs prior baseline
}

export interface FundSnapshot {
  internal_id: string
  scheme_name: string
  category: string
  amc: string
  expense_ratio: number
  aum_cr: number
  inception_date: string
  current_nav: number
  as_of_date: string
  ret_1m: number
  ret_3m: number
  ret_6m: number
  ret_1y: number                       // 12-Month Return %
  ret_3y_cagr: number                  // 3-Year CAGR
  ret_5y_cagr: number                  // 5-Year CAGR
  current_drawdown: number
  vol_30d: number
  rolling_sortino_1y: number
  fund_quality_score: number
  market_regime: string
}

export interface Holding {
  id: string
  fundId: string
  fundName: string
  category: string
  investedAmount: number
  currentValue: number
}

export interface PredictionLedgerEntry {
  ledger_id: string
  timestamp: string
  model_version: string
  data_version: string
  benchmark_index: string
  benchmark_nav: number
  market_regime: string
  drawdown_pct: number
  volatility_30d_pct: number
  signal: string
  recommended_action: string
  strategy: string
  deployment_plan: {
    immediate_pct: number
    staggered_pct: number
    tranches: number
  }
  evidence_strength: string
  historical_context: string
  live_paper_status: string
  counterfactual_12m_outcomes: { [key: string]: any }
  regret_vs_lump_sum_pct: number | null
  realized_outcome_summary: string
}

export interface StrategyMetric {
  sample_count: number
  metric_label?: string
  median_return_pct?: number
  mean_return_pct?: number
  median_cagr_pct?: number
  mean_cagr_pct?: number
  positive_frequency_pct: number
  worst_outcome_pct?: number
  best_outcome_pct?: number
  median_max_drawdown_pct: number
  worst_max_drawdown_pct: number
  median_sortino: number
  median_vol_pct: number
}

export interface BacktestFundResult {
  [horizon: string]: {
    [strategy: string]: any
  }
}
