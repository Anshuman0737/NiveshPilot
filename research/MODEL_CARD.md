# Model Card: NiveshPilot `model_v1.0-pit` (Audited V1.1)

## Model Details
- **Model Name**: NiveshPilot Adaptive Capital Deployment Engine
- **Model Version**: `model_v1.0-pit` (Frozen as of August 30, 2024; Forensic Audit V1.1 September 2026)
- **Model Type**: Deterministic Rule-Based Quantitative Regime & Volatility Filter
- **Target Cost**: ₹0 Runtime Cost (Zero Paid APIs or Proprietary Subscriptions)
- **Primary Objective**: Provide evidence-backed decision support for beginner retail investors answering: *“I have ₹X available. What is the most sensible deployment schedule right now?”*
- **Observational Gap Disclosure**: The underlying historical data cutoff is August 30, 2024. Active real-time streaming was not maintained between August 2024 and September 2026; August 2024 entries represent an archived freeze snapshot.

---

## Intended Use
- **Educational Decision Support**: Translating complex quantitative indicators (regimes, realized volatility, drawdowns) into an understandable, actionable next step (*INVEST NOW*, *INVEST GRADUALLY*, *WAIT*, *HOLD*, *DON'T INVEST IN EQUITY*, *NO CLEAR SIGNAL*).
- **Behavioral Regret Containment**: Mitigating the psychological impulse to buy lump sum at cyclical peaks or panic-sell at cyclical bottoms.
- **Target Asset Class**: Diversified Indian Equity Mutual Funds (Large Cap, Flexi Cap, Mid Cap) and Liquid Funds for cash buffering.

---

## Non-Intended Use
- **NOT an Intraday Trading System**: Designed for multi-month/multi-year investment runway; not applicable to day-trading, F&O, leverage, or crypto.
- **NOT a Guaranteed Predictor**: Does not claim to forecast future market direction or guarantee returns.
- **NOT SEBI Registered Advisory**: Does not provide individualized, regulated financial planning or portfolio management services.

---

## Training & Validation Scope
- **Benchmark Data**: Nifty 50 Total Return Index (2016–2024, 2,120+ trading sessions).
- **Validation Methodology**: Strict walk-forward rolling out-of-sample evaluation across 84 rolling monthly windows, supplemented by 7 strictly non-overlapping independent annual windows.
- **Isolated Holdout**: Evaluated on an untouched out-of-sample holdout period (July 2023 to July 2024).
- **Anti-Leakage Standard**: Every feature computed strictly point-in-time ($t$ using history $\le t$). Future date leakage unit-tested and verified.

---

## Reconciled Empirical Performance Summary (12-Month Horizon)

### Overlapping Rolling Windows (N = 84)
- **Positive Outcome Frequency**: **90.5%**
- **Median 12-Month Return**: **+21.68%** (captures 92% of Lump Sum's +23.59%, beats Monthly SIP's +17.17%)
- **Worst Crash Drawdown**: **-37.43%** (overall sample)
- **High-Volatility Regime Drawdown**: Limited to **-8.7%** (vs -21.9% for Lump Sum)
- **Median Sortino Ratio**: **1.42** (vs 1.64 for Lump Sum, 1.48 for 50/50, 1.38 for Monthly SIP)
  *Note on Sortino Reconciliation*: In Correction regimes, Strategy E Sortino is **1.79 vs 1.75** for Lump Sum. Earlier prototype documentation reported a mock value of 1.74 which has been formally reconciled in `research/MODEL_CHANGE_LOG.md`.
- **Moving Block Bootstrap 95% Confidence Interval**: `[11.65%, 47.65%]` (accounting for 11-month autocorrelation)

### Non-Overlapping Independent Windows (N = 7)
- **Positive Outcome Frequency**: **85.7%** (6 positive out of 7 independent years)
- **Median 12-Month Return**: **+32.70%** (vs +31.47% for Lump Sum, +28.54% for Monthly SIP)
- **Median Sortino**: **1.44** (vs 1.63 for Lump Sum, 1.47 for 50/50)

### Untouched Out-of-Sample Holdout (July 2023 – July 2024)
- **Realized 12-Month Return**: **+22.20%**
- **Peak Drawdown**: **-8.25%**
- **Sortino Ratio**: **1.90** (vs 1.87 for 50/50, 1.60 for Monthly SIP)

---

## Known Weaknesses & Failure Modes
1. **Sudden V-Shaped Rallies**: In rapid V-shaped recoveries (e.g. April–May 2020), defensive staggering retains capital in liquid yield, incurring an average opportunity cost of +14.65% compared to 100% immediate lump sum.
2. **Prolonged Sideways Grind**: In range-bound markets (e.g. 2022), neither lump sum nor staggered deployment outperforms low-risk debt instruments.
3. **Survivorship Bias**: Tested against active surviving Direct-growth schemes. Scheme mergers or liquidations in the broader mutual fund universe are documented as an empirical limitation (`research/SURVIVORSHIP_AUDIT.md`).

---

## Out-of-Distribution & Kill Switch Behavior
If market volatility exceeds 28% while trend indicators conflict, or if underlying data fails anomaly verification checks, the model automatically triggers **NO CLEAR SIGNAL** and defaults to a systematic, non-discretionary baseline.
