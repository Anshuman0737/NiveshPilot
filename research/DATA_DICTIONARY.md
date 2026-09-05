# NiveshPilot Data Dictionary

This document provides formal definitions, mathematical expressions, sources, and units for all financial variables and entities used in NiveshPilot.

---

## 1. Primary Entities

### `Fund`
- `internal_id`: String identifier (e.g. `PPFAS_FLEXI`, `MIRAE_LARGE`).
- `amfi_code`: Official AMFI numerical scheme code.
- `scheme_name`: Full regulatory name of the scheme (Direct Plan - Growth).
- `category`: SEBI-defined mutual fund category (e.g., Large Cap Fund, Flexi Cap Fund).
- `expense_ratio`: Total Expense Ratio (TER) expressed as an annual percentage (%).
- `aum_cr`: Assets Under Management in Crores (₹ Cr).

### `NAVObservation`
- `date`: Trading date formatted as `YYYY-MM-DD`.
- `nav`: Net Asset Value per unit in Indian Rupees (₹), rounded to 4 decimal places.
- `source`: Primary provenance origin (`portal.amfiindia.com` or `NSE Indices Ltd`).
- `retrieval_date`: ISO 8601 UTC timestamp of data ingestion.

---

## 2. Calculated Point-in-Time Features

### `ret_1m`, `ret_3m`, `ret_6m`
- **Definition**: Rolling percentage return over 21, 63, and 126 trading days.
- **Formula**: `(NAV_t - NAV_{t-k}) / NAV_{t-k}`
- **Unit**: Percentage (%).

### `ret_1y` (12-Month Return)
- **Definition**: Rolling percentage return over exactly 252 trading days.
- **Rule**: Explicitly named "12-Month Return" (never labeled CAGR).
- **Formula**: `(NAV_t - NAV_{t-252}) / NAV_{t-252}`

### `ret_3y_cagr`, `ret_5y_cagr`
- **Definition**: Compound Annual Growth Rate over multi-year horizons (756 and 1260 trading days).
- **Formula**: `(NAV_t / NAV_{t-k}) ** (252 / k) - 1.0`
- **Unit**: Annualized percentage (%).

### `drawdown`
- **Definition**: Percentage decline from the expanding peak.
- **Formula**: `(NAV_t - CumMax(NAV_{0..t})) / CumMax(NAV_{0..t})`
- **Range**: `[-1.0, 0.0]`. Expressed as percentage (e.g. -12.4%).

### `vol_30d`, `vol_90d`
- **Definition**: Annualized standard deviation of daily logarithmic returns over 30 and 90 trading days.
- **Formula**: `Std(ln(NAV_t / NAV_{t-1})) * sqrt(252)`
- **Unit**: Annualized percentage (%).

### `rolling_sortino_1y`
- **Definition**: Ratio of excess 1-year return over the risk-free rate (6.0%) divided by 90-day annualized downside deviation below the risk-free rate.
- **Formula**: `(ret_1y - 0.06) / DownsideDev_90d`

### `fund_quality_score`
- **Definition**: Transparent heuristic score from 0 to 100 assessing structural quality:
  - Rolling Consistency & Sortino: **35%**
  - Downside Resilience & Drawdown Containment: **30%**
  - Cost Efficiency (TER): **20%**
  - Rolling Benchmark Alpha: **15%**

---

## 3. Decision & Strategy Outputs

### `MarketRegime`
- `Bull`: `NAV > 200 SMA` and `50 SMA >= 200 SMA` and `ret_3m > 0`.
- `Correction`: Pullback within Bull market where `drawdown` is between -5% and -18% and `ret_1m < -2%`.
- `Recovery`: Rebounding from drawdown < -10% where `NAV > 50 SMA` and `ret_1m > 3%`.
- `Bear`: `NAV < 200 SMA` and `50 SMA < 200 SMA` and `drawdown < -15%`.
- `High-volatility`: `vol_30d > 28%` (overrides directional trend).
- `Sideways`: `|ret_3m| < 3%` and flat 200 SMA.
- `Unknown`: Insufficient data (<200 days) or conflicting signals.

### `RecommendationSignal`
- `INVEST NOW`
- `INVEST GRADUALLY`
- `WAIT`
- `HOLD`
- `REVIEW`
- `DON'T INVEST IN EQUITY`
- `NO CLEAR SIGNAL`

### `decision_id`
- **Definition**: Deterministic SHA-256 derived identifier uniquely identifying the decision parameters, profile inputs, timestamp, and model version (e.g. `NP-DEC-20240830-7F8A`). Enables bit-for-bit deterministic replay.

---

## 4. Backtest & Uncertainty Variables

### `Overlapping vs Non-Overlapping Windows`
- **Overlapping Rolling Windows**: Windows stepped every 21 trading days (monthly entry) over a 252-day horizon ($N = 84$). Consecutive windows share 231 trading days (11 months) of common returns. Autocorrelation is explicitly accounted for using Moving Block Bootstrap.
- **Non-Overlapping Windows**: Windows stepped every 252 trading days (annual entry) over a 252-day horizon ($N = 7$). Consecutive windows are statistically independent with zero shared return periods.

### `Friction & Cash Drag Specifications`
- **Liquid Yield**: All undeployed cash accrues daily risk-free liquid yield at 6.0% annualized (`(1 + 0.06)^(1/252) - 1`).
- **Transaction Friction**: 0.005% government stamp duty applied to all equity purchases on settlement date ($T+1$).
- **Expense Ratios**: Total Expense Ratios (TER) are embedded directly within official daily AMFI NAV disclosures (Direct plans only).

