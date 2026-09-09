export type AssetClass = 'equity' | 'etf' | 'commodity' | 'mutual_fund' | 'index'
export type ForecastHorizon = '1D' | '5D' | '20D' | '60D'
export type ExpectedDirection =
  | 'STRONGLY BULLISH'
  | 'MODERATELY BULLISH'
  | 'NEUTRAL / RANGE-BOUND'
  | 'MODERATELY BEARISH'
  | 'STRONGLY BEARISH'

export type ConfidenceLevel = 'LOW' | 'MEDIUM' | 'HIGH'
export type DataFreshness = 'LIVE' | 'DELAYED' | 'END_OF_DAY' | 'HISTORICAL' | 'STALE' | 'UNAVAILABLE'

export interface LookThroughHolding {
  symbol: string
  weight: number
}

export interface AssetMetadata {
  symbol: string
  name: string
  asset_class: AssetClass
  sector: string
  exchange: string
  currency: string
  benchmark: string
  zerodha_symbol?: string
  underlying_index?: string
  amfi_code?: string
  isin?: string
  look_through_holdings?: LookThroughHolding[]
  description: string
}

export interface SentimentDimensions {
  financial: number
  operational: number
  product: number
  brand: number
  regulatory: number
  customer: number
  competitive: number
}

export interface EventObservation {
  event_id: string
  symbol: string
  event_type: 'corporate' | 'product' | 'brand' | 'macro' | 'market'
  event_subtype: string
  title: string
  published_at: string
  effective_at: string
  source: string
  source_type: 'regulator' | 'investor_relations' | 'government' | 'recognized_provider' | 'news'
  source_url: string
  reliability_score: number
  expected_value: number
  actual_value: number
  metric_unit: string
  surprise_pct: number
  surprise_category:
    | 'Good News Better than Expected'
    | 'Good News Below Expected'
    | 'Bad News Worse than Expected'
    | 'Bad News Less Bad than Expected'
    | 'In Line with Expectations'
  sentiment_dimensions: SentimentDimensions
  novelty_score: number
  attention_zscore: number
  independent_source_count: number
  cluster_id: string
}

export interface ComponentSubModels {
  technical: number
  fundamental: number
  event_news: number
  macro_regime: number
  cross_asset: number
}

export interface ModelDisagreement {
  components: ComponentSubModels
  dispersion_std: number
  consensus_level: 'High Consensus' | 'Moderate Agreement' | 'High Disagreement'
}

export interface DirectionalForecast {
  horizon: ForecastHorizon
  days: number
  probability_bullish: number
  probability_neutral: number
  probability_bearish: number
  expected_direction: ExpectedDirection
  expected_return_pct: number
  confidence: ConfidenceLevel
  signal_quality: number
  model_disagreement: ModelDisagreement
  top_bullish_drivers: string[]
  top_bearish_drivers: string[]
}

export interface AssetPricePoint {
  date: string
  close: number
  open: number
  high: number
  low: number
  volume: number
  ret_1d?: number
  ret_5d?: number
  ret_20d?: number
  vol_30d?: number
  drawdown?: number
  rsi_14?: number
  atr_14_pct?: number
  macd_hist?: number
  volume_zscore?: number
  rel_strength_20d?: number
  market_regime?: string
}

export interface PaperPredictionRecord {
  prediction_id: string
  asset: string
  asset_class: AssetClass
  timestamp: string
  horizon: ForecastHorizon
  probability_bullish: number
  probability_neutral: number
  probability_bearish: number
  expected_direction: ExpectedDirection
  expected_return_pct: number
  confidence: ConfidenceLevel
  signal_quality: number
  model_version: string
  feature_snapshot_hash: string
  top_bullish_drivers: string[]
  top_bearish_drivers: string[]
  status: 'ACTIVE_PAPER' | 'SCORED'
  actual_return_pct: number | null
  is_correct_direction: boolean | null
  calibration_bucket: string
}

export interface ProviderHealth {
  id: string
  name: string
  endpoint: string
  status: 'ONLINE' | 'DEGRADED' | 'OFFLINE'
  latencyMs: number
  lastSuccessfulSync: string
  freshness: DataFreshness
  errorCount: number
}

export interface BacktestHorizonMetrics {
  directional_accuracy_pct: number
  balanced_accuracy_pct: number
  brier_score: number
  log_loss: number
  roc_auc: number
  annualized_sharpe: number
  max_drawdown_pct: number
}

export interface AblationStudyItem {
  directional_accuracy: number
  brier_score: number
  roc_auc: number
  delta_vs_baseline: string
}

export interface CalibrationBucket {
  predicted_bucket: string
  mean_predicted: number
  realized_rate: number
  sample_size: number
}

export interface BacktestReport {
  evaluation_period: string
  total_test_windows: number
  horizons_evaluated: string[]
  summary_by_horizon: Record<string, BacktestHorizonMetrics>
  ablation_study: Record<string, AblationStudyItem>
  regime_breakdown: Record<string, { accuracy: number; brier_score: number; sample_count: number }>
  calibration_table: CalibrationBucket[]
  failure_analysis: Array<{
    failure_id: string
    type: string
    date: string
    asset: string
    forecast_bullish_prob: number
    realized_5d_return: number
    root_cause: string
  }>
}
