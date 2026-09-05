# Backtest Assumptions & Execution Specification

This document details all execution, friction, settlement, and cash accounting assumptions used in NiveshPilot walk-forward backtests.

---

## 1. Execution & Timing
- **Decision Timestamp**: Signals are computed after market close on Date $t$ using the official closing NAV published by AMFI.
- **Execution Date**: Order is assumed to be placed on Date $t$ and executed at T+1 NAV (in accordance with SEBI mutual fund cutoff rules).
- **Execution Frictional Drag**:
  - Mutual fund transactions incur mandatory Government of India stamp duty of **0.005%** on purchase value.
  - Modeled deduction: $\text{Units} = \frac{\text{Capital} \times (1 - 0.00005)}{\text{NAV}_{t+1}}$.
  - Direct plan expense ratios are natively embedded in the daily NAV series.

---

## 2. Idle Cash Yield Treatment
- All capital not yet deployed into equity does NOT sit at 0% cash drag.
- Undeployed cash is assumed to remain invested in an ultra-low-risk Liquid Mutual Fund (SBI Liquid Fund proxy), accruing interest daily at an annualized rate of **6.0% p.a.**:
  $$R_{\text{daily\_cash}} = (1 + 0.060)^{1/252} - 1 \approx 0.0231\% \text{ per day}$$

---

## 3. Walk-Forward Window Parameters
- **Universe Period**: January 1, 2016 – August 30, 2024 (2,120+ trading days).
- **Warm-Up Window**: 252 trading days (1 year) required before the first rolling decision can be issued.
- **Rolling Step**: Every 21 trading days (approximately 1 calendar month).
- **Sample Count**: Exactly 84 rolling 12-month evaluation windows.
- **Horizons Evaluated**:
  - 3 Months (63 trading days)
  - 6 Months (126 trading days)
  - 12 Months (252 trading days)
  - 3 Years (756 trading days)
  - 5 Years (1260 trading days)

---

## 4. Benchmark Baselines
1. **Strategy A (Lump Sum)**: 100% on Day 0.
2. **Strategy B (50/50 Staggered)**: 50% Day 0, 50% Day 30.
3. **Strategy C (25% x 4)**: 25% on Days 0, 21, 42, 63.
4. **Strategy D (Monthly SIP)**: 16.7% across 6 tranches (Days 0, 21, 42, 63, 84, 105).
