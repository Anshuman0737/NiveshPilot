# Prediction Ledger Schema Specification

The NiveshPilot Prediction Ledger (`prediction_ledger.json`) is a permanent, immutable record of decision points, signals, deployment plans, and subsequent out-of-sample realized outcomes. Historical entries are never modified retrospectively.

---

## Record Schema

```typescript
interface PredictionLedgerEntry {
  // Unique immutable identifier
  ledger_id: string

  // ISO Date of the decision point (YYYY-MM-DD)
  timestamp: string

  // Frozen model identifier (e.g. "model_v1.0-pit")
  model_version: string

  // Dataset provenance version (e.g. "1.0.0-amfi")
  data_version: string

  // Target benchmark or scheme internal identifier
  benchmark_index: string

  // Benchmark closing NAV on decision date
  benchmark_nav: number

  // Point-in-time regime classification
  market_regime: 'Bull' | 'Bear' | 'Correction' | 'Recovery' | 'Sideways' | 'High-volatility' | 'Unknown'

  // Expanding peak drawdown percentage on decision date
  drawdown_pct: number

  // 30-day annualized realized volatility percentage
  volatility_30d_pct: number

  // Formal decision signal
  signal: 'INVEST NOW' | 'INVEST GRADUALLY' | 'WAIT' | 'HOLD' | 'REVIEW' | 'DON\'T INVEST IN EQUITY' | 'NO CLEAR SIGNAL'

  // Plain-English recommendation statement
  recommended_action: string

  // Internal quantitative strategy key
  strategy: string

  // Deployment schedule
  deployment_plan: {
    immediate_pct: number
    staggered_pct: number
    tranches: number
  }

  // Qualitative evidence strength
  evidence_strength: 'Strong' | 'Moderate' | 'Weak'

  // Historical macro context or catalyst
  historical_context: string

  // Tracking lifecycle status
  live_paper_status: 'CLOSED' | 'ACTIVE_PAPER'

  // Counterfactual 12-month returns across all 4 baselines
  counterfactual_12m_outcomes: {
    Strategy_A_LumpSum_12m_ret_pct?: number
    Strategy_B_50_50_12m_ret_pct?: number
    Strategy_D_Monthly_SIP_12m_ret_pct?: number
    Strategy_E_Adaptive_12m_ret_pct?: number
    status?: string
  }

  // Regret compared to immediate lump sum (Lump Sum return minus Adaptive return)
  regret_vs_lump_sum_pct: number | null

  // Human-readable outcome summary
  realized_outcome_summary: string
}
```
