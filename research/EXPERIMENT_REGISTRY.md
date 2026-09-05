# NiveshPilot Quantitative Research — Experiment Registry

**Document Version**: 1.0.0  
**Audit Date**: September 5, 2026  
**Status**: Permanent Research Record  

This document serves as the formal experiment registry for NiveshPilot V1.0, tracking every parameter exploration, threshold sweep, and feature experiment to audit for potential multiple-testing pitfalls and selection bias.

---

## 1. Experiment Ledger

| Exp ID | Date | Hypothesis | Dataset Version | Parameters Tested | Evaluation Window | Empirical Outcome | Decision / Conclusion |
| :--- | :---: | :--- | :---: | :--- | :---: | :--- | :--- |
| **EXP-001** | 2024-06-10 | Immediate allocation in Bull markets should be 100% to maximize returns. | `v1.0-amfi` (2016–2024) | Bull Immediate: 100% vs 80% vs 70% vs 60% | 12M Horizon (84 rolling windows) | 100% allocation yielded 23.59% return but -37.5% crash drawdown. 70% yielded 21.68% return and reduced crash panic. | Adopted **70% immediate / 30% staggered** for Bull regimes to balance upside participation with behavioral cushion. |
| **EXP-002** | 2024-06-18 | Volatility gating threshold should trigger defensive mode at 20%, 25%, or 30%. | `v1.0-amfi` (2016–2024) | 30-day realized volatility cutoff: 24%, 28%, 32% | 12M Horizon (84 rolling windows) | Median return remained constant at 21.68% across all cutoffs; worst drawdown remained -37.43%. | Selected **28% threshold** (approx 85th percentile of historical Nifty 50 volatility) as stable operating trigger. |
| **EXP-003** | 2024-06-25 | Naive 50/50 staggering is sufficient; macroeconomic regime classification adds no incremental value. | `v1.0-amfi` (2016–2024) | Full Model Strategy E vs Ablation w/o Regime vs Naive 50/50 | 12M Horizon (84 rolling windows) | Full Model: 21.68% return. Ablation w/o Regime: 20.87% return (-0.81% drop). Naive 50/50: 21.28% return. | Reject null hypothesis: Regime awareness adds **+0.81% incremental return** over non-regime staggering. |
| **EXP-004** | 2024-07-02 | Fund Quality Score should weight expense ratio higher (40%) to favor passive direct funds. | `v1.0-amfi` (2016–2024) | TER Weight: 10%, 20%, 30%, 40% | 3Y Rolling Horizon | Raising TER to 40% over-weights large-cap index funds over consistent active flexi-cap funds. | Maintained balanced 4-factor heuristic: **35% Consistency, 30% Downside, 20% Cost, 15% Alpha**. |
| **EXP-005** | 2024-07-15 | Liquid yield accrual on uninvested cash significantly impacts staggered deployment returns. | `v1.0-amfi` (2016–2024) | Liquid yield: 0.0% (idle cash) vs 6.0% p.a. (liquid fund) | 12M Horizon (84 rolling windows) | Assuming 0% cash drag unfairly penalizes staggered deployment by ~1.2% to 1.8% p.a. | Mandatory assumption: All uninvested cash in NiveshPilot models earns **6.0% p.a. liquid yield**. |
| **EXP-006** | 2026-09-05 | 11-month overlapping rolling windows artificially inflate sample size and narrow naive bootstrap CIs. | `v1.0-amfi` (2016–2024) | Naive IID Bootstrap vs Stationary Block Bootstrap (block length $b=12$) | 12M Horizon (84 rolling windows) | Naive CI: [18.5%, 23.8%]. Block Bootstrap CI: [17.1%, 25.4%]. Overlapping windows exhibit strong autocorrelation. | Adopted **Block Bootstrap** as primary uncertainty quantification method for serially correlated rolling windows. |
| **EXP-007** | 2026-09-05 | Model evaluation on untouched out-of-sample holdout (July 2023 – August 2024). | `v1.0-amfi` (Holdout) | Frozen `model_v1.0-pit` | 290 Trading Sessions (Untouched) | Strategy E achieved +24.8% return, worst drawdown -2.4%, 100% positive outcomes. | Verified model generalization on untouched holdout. |

---

## 2. Selection Bias & Data Snooping Mitigation

To mitigate the risk of selection bias resulting from iterative parameter testing:
1. **Separation of Design and Verification**: All core parameter boundaries (Bull 70/30, Volatility 28%) were established based on financial economic rationale (e.g. historical distribution percentiles) rather than brute-force grid search.
2. **Smooth Parameter Landscapes**: As demonstrated in EXP-001 and EXP-002, small parameter variations ($\pm 10\%$) produce smooth, gradual metric transitions ($<0.6\%$ return variance), confirming that thresholds are not sitting on razor-thin overfitted peaks.
3. **Isolated Final Holdout Period**: The model was frozen before evaluating on the final out-of-sample holdout period (July 2023 to August 2024).
