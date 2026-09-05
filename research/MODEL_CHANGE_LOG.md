# NiveshPilot V1.0 — Model Change Log & Discrepancy Reconciliation

**Document Version**: 1.0.0  
**Audit Date**: September 5, 2026  
**Auditor**: Antigravity Forensic Quantitative Validation Suite  

---

## 1. Sortino Ratio Discrepancy Reconciliation (1.74 vs 1.42)

### Issue Summary
In early documentation and UI prototype mock files (`FALLBACK_BACKTEST`), Strategy E (NiveshPilot Signal-Adaptive) was reported as having a **Median Sortino Ratio of 1.74**, compared to **1.48 for Strategy A (100% Lump Sum)**.
However, execution of the full walk-forward backtest across the empirical 2016–2024 Nifty 50 TRI dataset yielded a **Median Sortino Ratio of 1.42 for Strategy E**, while Strategy A achieved **1.64**.

### Root Cause Analysis
1. **Initial Prototype Mock Values**: The 1.74 Sortino value originated in early UI layout prototyping where hypothetical backtest estimates were drafted before the complete walk-forward simulation engine (`research/backtest.py`) had been finalized.
2. **True Empirical Mechanics**: When the complete simulation was run with daily cash yield accrual (6.0% p.a. liquid yield on uninvested capital), T+1 settlement lag, and the 0.005% stamp duty friction across all 84 rolling 12-month windows:
   - **Strategy A (Lump Sum)**: Because Indian equities were in a strong secular bull run across 2016–2024 (excluding the 2-month Covid crash in March 2020), 100% immediate deployment captured substantial upside (+23.59% median return), elevating its return-to-downside-deviation ratio in positive windows. Its Sortino was **1.64**.
   - **Strategy E (Signal-Adaptive)**: In Bull regimes, Strategy E deployed 70% immediately and held 30% for 42 trading days. This cash drag slightly dampened total 12-month returns to **+21.68%** (a 1.91% return reduction), while during the rapid V-shaped recovery of 2020–2021, the delayed deployment experienced smaller upside. This produced an empirical median Sortino of **1.42**.
3. **Regime-Specific Sortino Superiority**:
   While the *overall aggregate* median Sortino of Strategy E is 1.42 vs 1.64 for Lump Sum, in **Correction regimes**, Strategy E delivers a superior Sortino (**1.79 vs 1.75**), and in **High-Volatility regimes**, Strategy E limits crash drawdowns to **-8.7% vs -21.9%** for Lump Sum.
4. **Resolution & Action Taken**:
   - All synthetic mock numbers (1.74, 15.4%) are completely deprecated and removed from `FALLBACK_BACKTEST`, `ResearchDashboard.tsx`, and all documentation.
   - The empirical backtest result (**Median Sortino 1.42**, **Median 12M Return +21.68%**) is the single source of truth across both code and documentation.
   - Any claim that Strategy E delivers a higher overall aggregate Sortino is retracted. Strategy E's actual statistical advantage is **peak panic drawdown reduction (-8.7% vs -21.9% in high-volatility) and lower decision regret**, NOT superior aggregate Sortino.

---

## 2. Date & Observational Gap Reconciliation (2024 Freeze vs September 2026)

### Issue Summary
Previous documentation stated that "live paper portfolio tracking is active as of August 30, 2024". The current system date is **September 2026**.

### Forensic Findings
- The historical dataset downloaded from AMFI and NSE Indices contains trading sessions up to **August 30, 2024**.
- There has been **no continuous live daily ingestion** connecting August 30, 2024 to September 2026 in the local environment.
- Calling tracking that halted on August 30, 2024 "live paper tracking" in 2026 is factually false and misleads users into believing the engine has an active, uninterrupted real-time feed.

### Resolution & Action Taken
- Re-labeled all 2024 paper entries from `ACTIVE_PAPER` to **`ARCHIVED_PAPER (August 2024 Freeze)`**.
- Explicitly disclosed the **2-year observational gap (August 2024 to September 2026)** in all model cards and reports.
- Added a `ModelHealthState` flag: when the data timestamp is older than 30 days, the engine flags `CAUTION: DATA STALE` or `NO_SIGNAL`.

---

## 3. Metric Definition Calibration (12-Month Return vs CAGR)

### Issue Summary
In multiple sections, 12-month horizon outcomes were referred to interchangeably as "CAGR" and "12-month return".

### Resolution & Action Taken
- Strictly enforced convention:
  - **12-Month Horizon**: Must strictly be labeled **"12-Month Return %"** or **"Median 12-Month Return %"**. Compound Annual Growth Rate (CAGR) is mathematically inappropriate for single-year periods.
  - **Multi-Year Horizons ($\ge$ 2 Years)**: Labeled **"3Y CAGR %"** and **"5Y CAGR %"**.

---

## 4. Model Versioning History

| Model Version | Freeze Date | Primary Change | Validation Status |
| :--- | :---: | :--- | :--- |
| `model_v0.1-proto` | 2024-05-15 | Initial heuristic prototype with hardcoded backtest estimates (Sortino 1.74). | Deprecated (Mock Data) |
| `model_v1.0-pit` | 2024-08-30 | Full walk-forward rolling backtest engine, point-in-time features, AMFI ingestion. | Verified (Sortino 1.42) |
| `model_v1.1-hardened` | 2026-09-05 | Forensic audit release: Block bootstrap CIs, isolated holdout test, deterministic replay tokens, model health states, and tiered UX. | **Current Production Candidate** |
