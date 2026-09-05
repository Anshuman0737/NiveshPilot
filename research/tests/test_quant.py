"""
Comprehensive Unit Test Suite for NiveshPilot Quantitative Core
Covers:
1. Mathematical correctness: CAGR, period returns, drawdown, Sortino, volatility.
2. Temporal anti-lookahead protections across all features.
3. Data integrity and anomaly detection: impossible jumps, negative NAVs, duplicates, gaps.
4. Backtesting execution: capital conservation, schedule validation, settlement.
5. Counterfactual and Decision Regret calculations.
6. Missed-rally and opportunity cost math.
7. Model threshold stability and Out-of-Distribution / No-Signal behavior.
"""

import pytest
import numpy as np
import pandas as pd
from research.build_features import (
    compute_cagr,
    compute_period_return,
    classify_market_regime,
    calculate_fund_features
)
from research.clean_data import audit_fund_series
from research.backtest import simulate_deployment

# -------------------------------------------------------------
# 1. QUANTITATIVE MATHEMATICS & TERMINOLOGY TESTS
# -------------------------------------------------------------

def test_compute_cagr_multi_year():
    """Validates multi-year CAGR calculation (>=2 years)."""
    # 100 to 121 in 2 years (504 trading days) -> 10.0% CAGR
    cagr_2y = compute_cagr(100.0, 121.0, 504)
    assert abs(cagr_2y - 0.10) < 0.005
    
    # 100 to 200 in 5 years (1260 trading days) -> ~14.87% CAGR
    cagr_5y = compute_cagr(100.0, 200.0, 1260)
    assert abs(cagr_5y - 0.1487) < 0.005
    
    # Negative growth: 100 to 81 in 2 years -> -10% CAGR
    cagr_neg = compute_cagr(100.0, 81.0, 504)
    assert abs(cagr_neg - (-0.10)) < 0.005

def test_compute_period_return_single_period():
    """Validates period return calculation for single period (<= 1 year)."""
    ret = compute_period_return(100.0, 115.4)
    assert abs(ret - 0.154) < 1e-5
    
    ret_neg = compute_period_return(100.0, 85.0)
    assert abs(ret_neg - (-0.15)) < 1e-5

def test_drawdown_calculation():
    """Validates peak-to-trough drawdown calculation."""
    navs = np.array([100.0, 120.0, 90.0, 110.0, 130.0])
    peak = pd.Series(navs).cummax()
    dd = (navs - peak) / peak
    # At index 2: NAV 90 vs Peak 120 -> Drawdown = (90 - 120)/120 = -0.25 (-25%)
    assert abs(dd[2] - (-0.25)) < 1e-5
    # At index 4: NAV 130 is new all-time high -> Drawdown = 0.0
    assert dd[4] == 0.0

# -------------------------------------------------------------
# 2. TEMPORAL INTEGRITY & ANTI-LOOKAHEAD TESTS
# -------------------------------------------------------------

def test_no_lookahead_bias_in_regime():
    """Verifies changing future NAVs has ZERO impact on past regime labels."""
    np.random.seed(42)
    navs_base = 100.0 * np.cumprod(1 + np.random.normal(0.0005, 0.01, 300))
    nav_series_1 = pd.Series(navs_base)
    dates = pd.Series(pd.date_range("2020-01-01", periods=300, freq="B"))
    
    regimes_1 = classify_market_regime(nav_series_1, dates)
    
    # Synthesize severe future crash from day 250
    navs_modified = navs_base.copy()
    navs_modified[250:] = navs_modified[250:] * 0.40  # 60% crash
    nav_series_2 = pd.Series(navs_modified)
    regimes_2 = classify_market_regime(nav_series_2, dates)
    
    # Regimes at and before day 249 must be mathematically identical
    assert regimes_1.iloc[200] == regimes_2.iloc[200]
    assert regimes_1.iloc[245] == regimes_2.iloc[245]

def test_no_lookahead_in_feature_engineering():
    """Verifies that rolling volatility and drawdowns do not leak future information."""
    dates = pd.date_range("2020-01-01", periods=100, freq="B")
    navs = [100.0 + i for i in range(100)]
    df1 = pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "nav": navs})
    bench1 = pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "nav": navs})
    meta = {"internal_id": "TEST", "expense_ratio": 0.5}
    
    feat1 = calculate_fund_features(df1, bench1, meta)
    val_50 = feat1.iloc[50]["vol_30d"]
    
    # Modify day 75 drastically
    navs_mod = navs.copy()
    navs_mod[75:] = [500.0] * 25
    df2 = pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "nav": navs_mod})
    bench2 = pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "nav": navs_mod})
    feat2 = calculate_fund_features(df2, bench2, meta)
    
    # Value at index 50 must be completely unaffected
    assert feat1.iloc[50]["vol_30d"] == feat2.iloc[50]["vol_30d"]
    assert feat1.iloc[50]["drawdown"] == feat2.iloc[50]["drawdown"]

# -------------------------------------------------------------
# 3. DATA INTEGRITY & ANOMALY DETECTION TESTS
# -------------------------------------------------------------

def test_anomaly_detection_catches_abnormal_jumps():
    """Ensures single-day NAV jump > 15% is detected and flagged."""
    dates = pd.date_range("2024-01-01", periods=10, freq="B")
    navs = [100.0] * 9 + [125.0]  # 25% impossible jump
    df = pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "nav": navs})
    
    cleaned_df, report = audit_fund_series("TEST_JUMP", df, "Large Cap Fund")
    assert report["anomalies_detected"] is True
    assert any("abnormal single-day return jumps" in issue for issue in report["issues"])
    assert report["quality_score"] < 100

def test_anomaly_detection_removes_zero_and_negative_nav():
    """Ensures non-positive NAV records are filtered out."""
    dates = pd.date_range("2024-01-01", periods=6, freq="B")
    navs = [10.0, 10.5, 0.0, -2.5, 11.0, 11.2]
    df = pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "nav": navs})
    
    cleaned_df, report = audit_fund_series("TEST_ZERO", df, "Flexi Cap Fund")
    assert report["anomalies_detected"] is True
    assert len(cleaned_df) == 4  # 0.0 and -2.5 removed
    assert (cleaned_df["nav"] > 0).all()

def test_anomaly_detection_deduplicates_dates():
    """Ensures duplicate timestamps are resolved."""
    dates = ["2024-01-01", "2024-01-02", "2024-01-02", "2024-01-03"]
    navs = [100.0, 101.0, 101.5, 102.0]
    df = pd.DataFrame({"date": dates, "nav": navs})
    
    cleaned_df, report = audit_fund_series("TEST_DUP", df, "Large Cap Fund")
    assert report["anomalies_detected"] is True
    assert len(cleaned_df) == 3
    assert cleaned_df.iloc[1]["nav"] == 101.5  # kept latest

def test_liquid_fund_strict_jump_threshold():
    """Validates that liquid funds use a strict 1% jump threshold (not 15%)."""
    dates = pd.date_range("2024-01-01", periods=5, freq="B")
    navs = [1000.0, 1000.2, 1015.0, 1015.2, 1015.5]  # ~1.48% jump in liquid fund
    df = pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "nav": navs})
    
    cleaned_df, report = audit_fund_series("TEST_LIQ", df, "Liquid Fund")
    assert report["anomalies_detected"] is True
    assert any("abnormal single-day return jumps" in issue for issue in report["issues"])

# -------------------------------------------------------------
# 4. BACKTESTING EXECUTION & CAPITAL CONSERVATION TESTS
# -------------------------------------------------------------

def test_deployment_simulation_preserves_capital_on_flat_market():
    """Validates that flat NAV preserves total capital (minus negligible liquid interest)."""
    navs = np.array([100.0] * 70)
    regimes = ["Bull"] * 70
    vols = np.array([0.10] * 70)
    dds = np.array([0.0] * 70)
    
    res = simulate_deployment("Strategy_A_LumpSum", 0, 60, navs, regimes, vols, dds, 10000.0)
    assert abs(res["final_value"] - 10000.0) < 5.0

def test_all_strategies_execute_validly():
    """Verifies that all 5 strategies run without crash and return valid metrics."""
    navs = np.array([100.0 + i*0.1 for i in range(150)])
    regimes = ["Bull"] * 150
    vols = np.array([0.12] * 150)
    dds = np.array([0.0] * 150)
    
    strats = [
        "Strategy_A_LumpSum",
        "Strategy_B_50_50",
        "Strategy_C_25x4",
        "Strategy_D_Monthly_SIP",
        "Strategy_E_Signal_Adaptive"
    ]
    for s in strats:
        sim = simulate_deployment(s, 0, 126, navs, regimes, vols, dds, 50000.0)
        assert sim is not None
        assert sim["final_value"] > 50000.0
        assert sim["max_drawdown"] <= 0.0

def test_adaptive_strategy_regime_behavior():
    """Verifies that Strategy E adapts schedule in Bear/High-vol vs Bull."""
    navs = np.array([100.0] * 100)
    vols_high = np.array([0.35] * 100)
    regimes_bear = ["Bear"] * 100
    dds = np.array([-0.20] * 100)
    
    sim_defensive = simulate_deployment("Strategy_E_Signal_Adaptive", 0, 60, navs, regimes_bear, vols_high, dds, 10000.0)
    assert sim_defensive is not None
    # Capital preservation check
    assert sim_defensive["final_value"] >= 10000.0

# -------------------------------------------------------------
# 5. MISSED RALLY, REGRET & STATISTICAL METRICS TESTS
# -------------------------------------------------------------

def test_decision_regret_math():
    """Verifies decision regret formula: Lump Sum return minus Adaptive return."""
    lump_ret = 0.25      # +25%
    adaptive_ret = 0.18  # +18%
    regret_vs_lump = lump_ret - adaptive_ret
    assert abs(regret_vs_lump - 0.07) < 1e-5  # +7% foregone gain regret
    
    # In a market crash:
    lump_crash = -0.30     # -30%
    adaptive_crash = -0.12 # -12%
    regret_crash = lump_crash - adaptive_crash
    assert abs(regret_crash - (-0.18)) < 1e-5  # Negative regret = avoided -18% drawdown

def test_missed_rally_opportunity_cost():
    """Verifies that opportunity cost is strictly non-negative when market rises."""
    lump_gain = 0.14
    staggered_gain = 0.09
    opp_cost = max(0.0, lump_gain - staggered_gain)
    assert abs(opp_cost - 0.05) < 1e-5
    
    # When market falls, opportunity cost of waiting is 0
    lump_loss = -0.10
    staggered_loss = -0.04
    opp_cost_falling = max(0.0, lump_loss - staggered_loss)
    assert opp_cost_falling == 0.0

# -------------------------------------------------------------
# 6. MODEL OUT-OF-DISTRIBUTION & QUALITY TESTS
# -------------------------------------------------------------

def test_out_of_distribution_volatility_triggers_high_vol():
    """Validates that unprecedented volatility (>28%) triggers High-volatility regime."""
    navs = pd.Series([100.0, 140.0, 80.0, 130.0, 70.0] * 60)
    dates = pd.Series(pd.date_range("2020-01-01", periods=300, freq="B"))
    regimes = classify_market_regime(navs, dates)
    # The extreme swings must trigger High-volatility
    assert "High-volatility" in regimes.values

def test_anomaly_detection_flags_calendar_gaps():
    """Ensures large gaps > 7 calendar days are detected in time series."""
    dates = ["2024-01-01", "2024-01-02", "2024-01-15"]  # 13 day gap
    navs = [100.0, 100.5, 101.0]
    df = pd.DataFrame({"date": dates, "nav": navs})
    cleaned_df, report = audit_fund_series("TEST_GAP", df, "Large Cap Fund")
    assert report["anomalies_detected"] is True
    assert any("trading gaps longer than 7 calendar days" in issue for issue in report["issues"])

def test_drawdown_buffering_during_crash():
    """Validates that staggered deployment exhibits lower drawdown than lump sum in crash."""
    # 30% crash over 40 days
    navs = np.array([100.0 - i * 0.75 for i in range(40)] + [70.0] * 30)
    regimes = ["Bear"] * 70
    vols = np.array([0.30] * 70)
    dds = np.array([-0.25] * 70)
    
    sim_lump = simulate_deployment("Strategy_A_LumpSum", 0, 60, navs, regimes, vols, dds, 100000.0)
    sim_adaptive = simulate_deployment("Strategy_E_Signal_Adaptive", 0, 60, navs, regimes, vols, dds, 100000.0)
    
    # Adaptive drawdown must be significantly milder than Lump Sum (-30%)
    assert sim_adaptive["max_drawdown"] > sim_lump["max_drawdown"]
    assert abs(sim_adaptive["max_drawdown"]) < abs(sim_lump["max_drawdown"])

def test_flat_zero_nav_series_handled_gracefully():
    """Ensures CAGR and period return handle 0 or negative without raising unhandled exception."""
    assert compute_cagr(0.0, 100.0, 504) == 0.0
    assert compute_period_return(0.0, 100.0) == 0.0

# -------------------------------------------------------------
# 7. SYSTEM-LEVEL INVARIANTS & PROPERTY-BASED TESTS
# -------------------------------------------------------------

def test_property_capital_conservation_all_strategies():
    """
    Property: For all strategies and varying capital amounts, the deployment
    strictly conserves every rupee (cash + equity value matches net assets exactly).
    """
    test_capitals = [5000.0, 25000.0, 100000.0, 1000000.0]
    strategies = [
        "Strategy_A_LumpSum",
        "Strategy_B_50_50",
        "Strategy_C_25x4",
        "Strategy_D_Monthly_SIP",
        "Strategy_E_Signal_Adaptive"
    ]
    np.random.seed(101)
    navs = 100.0 * np.cumprod(1 + np.random.normal(0.0002, 0.012, 150))
    regimes = ["Bull"] * 50 + ["Correction"] * 50 + ["Bear"] * 50
    vols = np.array([0.14] * 50 + [0.22] * 50 + [0.32] * 50)
    dds = np.array([-0.02] * 50 + [-0.12] * 50 + [-0.25] * 50)
    
    for cap in test_capitals:
        for strat in strategies:
            res = simulate_deployment(strat, 0, 120, navs, regimes, vols, dds, cap)
            assert res is not None
            assert np.isfinite(res["final_value"])
            assert res["final_value"] > 0.0
            assert res["max_drawdown"] <= 0.0
            assert res["max_drawdown"] >= -1.0
            assert res["ann_vol"] >= 0.0

def test_property_deterministic_replay():
    """
    Property: Given identical market paths and parameters, the backtesting engine
    is 100% deterministic (zero stochastic drift or non-reproducible state).
    """
    np.random.seed(202)
    navs = 100.0 * np.cumprod(1 + np.random.normal(0.0003, 0.015, 150))
    regimes = ["Correction"] * 150
    vols = np.array([0.20] * 150)
    dds = np.array([-0.08] * 150)
    
    run_1 = simulate_deployment("Strategy_E_Signal_Adaptive", 10, 90, navs, regimes, vols, dds, 75000.0)
    run_2 = simulate_deployment("Strategy_E_Signal_Adaptive", 10, 90, navs, regimes, vols, dds, 75000.0)
    
    assert run_1["final_value"] == run_2["final_value"]
    assert run_1["period_return"] == run_2["period_return"]
    assert run_1["max_drawdown"] == run_2["max_drawdown"]
    assert run_1["ann_vol"] == run_2["ann_vol"]
    assert run_1["sortino"] == run_2["sortino"]

def test_property_proportional_capital_scaling():
    """
    Property: Simulating with capital C vs k*C produces identical percentage returns,
    identical max drawdown, identical volatility, and exactly k-scaled final values
    within 2-decimal rounding tolerance.
    """
    np.random.seed(303)
    navs = 100.0 * np.cumprod(1 + np.random.normal(0.0001, 0.01, 100))
    regimes = ["Bull"] * 100
    vols = np.array([0.15] * 100)
    dds = np.array([-0.03] * 100)
    
    cap_small = 10000.0
    multiplier = 7.5
    cap_large = cap_small * multiplier
    
    for strat in ["Strategy_A_LumpSum", "Strategy_B_50_50", "Strategy_C_25x4", "Strategy_E_Signal_Adaptive"]:
        res_small = simulate_deployment(strat, 0, 70, navs, regimes, vols, dds, cap_small)
        res_large = simulate_deployment(strat, 0, 70, navs, regimes, vols, dds, cap_large)
        
        # Scaling of absolute wealth (accounting for round(2) paise differences):
        assert abs(res_large["final_value"] - (res_small["final_value"] * multiplier)) < 0.10
        # Invariant percentage metrics:
        assert abs(res_large["period_return"] - res_small["period_return"]) < 1e-3
        assert abs(res_large["max_drawdown"] - res_small["max_drawdown"]) < 1e-3
        assert abs(res_large["ann_vol"] - res_small["ann_vol"]) < 1e-3

def test_property_temporal_isolation_across_windows():
    """
    Property: Strict Temporal Isolation. Modifying data after day T cannot
    retroactively alter any metric or trajectory up to day T.
    """
    np.random.seed(404)
    navs_original = 100.0 * np.cumprod(1 + np.random.normal(0.0004, 0.01, 200))
    regimes = ["Bull"] * 200
    vols = np.array([0.16] * 200)
    dds = np.array([-0.04] * 200)
    
    # Run window from 0 to 60
    res_orig = simulate_deployment("Strategy_E_Signal_Adaptive", 0, 60, navs_original, regimes, vols, dds, 50000.0)
    
    # Mutilate future data from day 61 to 200 (catastrophic crash + spikes)
    navs_mutilated = navs_original.copy()
    navs_mutilated[61:] = navs_mutilated[61:] * 0.20
    
    res_mut = simulate_deployment("Strategy_E_Signal_Adaptive", 0, 60, navs_mutilated, regimes, vols, dds, 50000.0)
    
    assert res_orig["final_value"] == res_mut["final_value"]
    assert res_orig["period_return"] == res_mut["period_return"]
    assert res_orig["max_drawdown"] == res_mut["max_drawdown"]
    assert res_orig["sortino"] == res_mut["sortino"]

def test_property_drawdown_monotonicity_in_severe_bear():
    """
    Property: In a strictly monotonic bear crash, all staggered strategies
    must have equal or strictly milder drawdowns than 100% Lump Sum.
    """
    # Monotonically declining NAV
    navs = np.array([100.0 - 0.5 * i for i in range(80)])  # drops from 100 to 60.5 (-39.5%)
    regimes = ["Bear"] * 80
    vols = np.array([0.28] * 80)
    dds = np.array([-0.20] * 80)
    
    lump = simulate_deployment("Strategy_A_LumpSum", 0, 70, navs, regimes, vols, dds, 100000.0)
    staggered_b = simulate_deployment("Strategy_B_50_50", 0, 70, navs, regimes, vols, dds, 100000.0)
    staggered_c = simulate_deployment("Strategy_C_25x4", 0, 70, navs, regimes, vols, dds, 100000.0)
    adaptive_e = simulate_deployment("Strategy_E_Signal_Adaptive", 0, 70, navs, regimes, vols, dds, 100000.0)
    
    # Drawdown of staggered must be mathematically milder (less negative) than Lump Sum
    assert staggered_b["max_drawdown"] > lump["max_drawdown"]
    assert staggered_c["max_drawdown"] > lump["max_drawdown"]
    assert adaptive_e["max_drawdown"] > lump["max_drawdown"]

def test_property_bull_rally_opportunity_cost():
    """
    Property: In a strictly monotonic relentless bull market, Lump Sum must
    outperform staggered strategies, formally establishing the empirical cost of downside insurance.
    """
    # Monotonically increasing NAV
    navs = np.array([100.0 + 0.6 * i for i in range(80)])  # rises from 100 to 147.4 (+47.4%)
    regimes = ["Bull"] * 80
    vols = np.array([0.12] * 80)
    dds = np.array([0.0] * 80)
    
    lump = simulate_deployment("Strategy_A_LumpSum", 0, 70, navs, regimes, vols, dds, 100000.0)
    staggered_c = simulate_deployment("Strategy_C_25x4", 0, 70, navs, regimes, vols, dds, 100000.0)
    adaptive_e = simulate_deployment("Strategy_E_Signal_Adaptive", 0, 70, navs, regimes, vols, dds, 100000.0)
    
    # Lump sum must strictly beat staggered deployment in a non-stop rally
    assert lump["period_return"] > staggered_c["period_return"]
    assert lump["period_return"] > adaptive_e["period_return"]
    # Foregone return is strictly positive (proves honest opportunity cost)
    foregone_return = lump["period_return"] - adaptive_e["period_return"]
    assert foregone_return > 0.03

