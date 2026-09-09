"""
Unit and Property Invariant Tests for Dynamic Market Intelligence Engine
Tests:
1. Temporal anti-lookahead isolation (zero future leakage into past features).
2. Probability sum conservation: P(Bullish) + P(Neutral) + P(Bearish) == 1.000.
3. Information Surprise Score categorization and mathematical precision.
4. Platt probability calibration monotonicity.
5. Model disagreement dispersion and consensus calculation.
6. Provenance and metadata completeness across assets, events, and ledgers.
7. Cryptographic SHA-256 hash generation for prediction snapshots.
"""

import pytest
import numpy as np
import pandas as pd
from research.market_intelligence_engine import (
    ASSETS_METADATA,
    EVENTS_REPOSITORY,
    CalibratedEnsembleForecaster,
    calculate_asset_features,
    build_paper_prediction_ledger
)

def test_anti_lookahead_temporal_isolation():
    """Modifying future price history must have ZERO effect on past features and regimes."""
    np.random.seed(42)
    n = 300
    dates = pd.date_range("2021-01-01", periods=n, freq="B").strftime("%Y-%m-%d")
    prices_base = 1000.0 * np.cumprod(1 + np.random.normal(0.0005, 0.01, n))
    
    df1 = pd.DataFrame({
        "date": dates,
        "close": prices_base,
        "open": prices_base,
        "high": prices_base * 1.005,
        "low": prices_base * 0.995,
        "volume": [100000] * n
    })
    bench1 = df1.copy()
    vix1 = pd.DataFrame({
        "date": dates,
        "close": [14.0] * n,
        "open": [14.0] * n,
        "high": [15.0] * n,
        "low": [13.0] * n,
        "volume": [0] * n
    })
    
    feat1 = calculate_asset_features(df1, bench1, vix1)
    
    # Synthesize massive crash starting on day 240
    df2 = df1.copy()
    df2.loc[240:, "close"] = df2.loc[240:, "close"] * 0.40  # 60% drop
    df2.loc[240:, "high"] = df2.loc[240:, "high"] * 0.40
    df2.loc[240:, "low"] = df2.loc[240:, "low"] * 0.40
    
    feat2 = calculate_asset_features(df2, bench1, vix1)
    
    # Verification: On or before day 239, all technicals and regimes must be bit-for-bit identical
    for col in ["ret_1d", "ret_5d", "ret_20d", "vol_30d", "drawdown", "rsi_14", "atr_14_pct", "macd_hist"]:
        val1 = feat1.loc[235, col]
        val2 = feat2.loc[235, col]
        assert abs(val1 - val2) < 1e-9, f"Lookahead leakage detected in {col} at day 235"
        
    assert feat1.loc[235, "market_regime"] == feat2.loc[235, "market_regime"]

def test_calibrated_probabilities_sum_to_one():
    """Bullish + Neutral + Bearish probabilities must sum to 1.000 across all horizons."""
    for horizon in ["1D", "5D", "20D", "60D"]:
        forecaster = CalibratedEnsembleForecaster(horizon, 5)
        # Test across diverse market conditions
        for tech in [-80.0, -30.0, 0.0, 45.0, 85.0]:
            for fund in [-50.0, 10.0, 60.0]:
                for evt in [-40.0, 0.0, 70.0]:
                    components = {
                        "technical": tech,
                        "fundamental": fund,
                        "event_news": evt,
                        "macro_regime": 15.0,
                        "cross_asset": 5.0
                    }
                    res = forecaster.forecast(components)
                    p_bull = res["probability_bullish"]
                    p_neu = res["probability_neutral"]
                    p_bear = res["probability_bearish"]
                    
                    total = p_bull + p_neu + p_bear
                    assert abs(total - 1.0) < 1e-4, f"Probabilities do not sum to 1.0: {p_bull} + {p_neu} + {p_bear} = {total}"
                    assert 0.0 <= p_bull <= 1.0
                    assert 0.0 <= p_neu <= 1.0
                    assert 0.0 <= p_bear <= 1.0

def test_information_surprise_score_categorization():
    """Verifies that surprise scores match economic expectations."""
    for evt in EVENTS_REPOSITORY:
        exp = evt["expected_value"]
        act = evt["actual_value"]
        cat = evt["surprise_category"]
        
        if exp > 0 and act > exp:
            assert "Better than Expected" in cat or "In Line" in cat
        elif exp > 0 and act < exp:
            assert "Below Expected" in cat or "In Line" in cat
            
        assert -1.0 <= evt["sentiment_dimensions"]["financial"] <= 1.0
        assert 0.0 <= evt["reliability_score"] <= 1.0

def test_platt_calibration_monotonicity():
    """Higher positive components must monotonically increase Bullish probability."""
    forecaster = CalibratedEnsembleForecaster("5D", 5)
    probs = []
    for score in [-80.0, -40.0, -10.0, 0.0, 20.0, 50.0, 80.0]:
        components = {
            "technical": score,
            "fundamental": score,
            "event_news": score,
            "macro_regime": score,
            "cross_asset": score
        }
        res = forecaster.forecast(components)
        probs.append(res["probability_bullish"])
        
    for i in range(len(probs) - 1):
        assert probs[i] < probs[i + 1], f"Monotonicity violated: {probs[i]} >= {probs[i+1]}"

def test_model_disagreement_dispersion():
    """Model disagreement standard deviation must be non-negative and properly categorized."""
    forecaster = CalibratedEnsembleForecaster("20D", 20)
    
    # Case A: Consensus
    comp_consensus = {
        "technical": 50.0,
        "fundamental": 52.0,
        "event_news": 48.0,
        "macro_regime": 51.0,
        "cross_asset": 49.0
    }
    res_a = forecaster.forecast(comp_consensus)
    assert res_a["model_disagreement"]["consensus_level"] == "High Consensus"
    assert res_a["model_disagreement"]["dispersion_std"] < 10.0
    
    # Case B: Disagreement
    comp_conflict = {
        "technical": 85.0,
        "fundamental": -75.0,
        "event_news": 80.0,
        "macro_regime": -60.0,
        "cross_asset": 20.0
    }
    res_b = forecaster.forecast(comp_conflict)
    assert res_b["model_disagreement"]["consensus_level"] == "High Disagreement"
    assert res_b["model_disagreement"]["dispersion_std"] > 35.0

def test_paper_prediction_ledger_cryptographic_integrity():
    """Verifies that all paper ledger entries have SHA-256 snapshot hashes and valid structures."""
    ledger = build_paper_prediction_ledger()
    assert len(ledger) >= 5
    
    for entry in ledger:
        assert entry["prediction_id"].startswith("PRED_")
        assert len(entry["feature_snapshot_hash"]) == 16  # 16-hex character prefix
        assert entry["confidence"] in ["LOW", "MEDIUM", "HIGH"]
        assert entry["expected_direction"] in [
            "STRONGLY BULLISH", "MODERATELY BULLISH", "NEUTRAL / RANGE-BOUND",
            "MODERATELY BEARISH", "STRONGLY BEARISH"
        ]
        if entry["status"] == "SCORED":
            assert entry["actual_return_pct"] is not None
            assert entry["is_correct_direction"] in [True, False]
            assert "calibration_bucket" in entry

def test_assets_metadata_completeness():
    """Ensures all supported asset classes have required fields and benchmarks."""
    for asset in ASSETS_METADATA:
        assert "symbol" in asset
        assert "name" in asset
        assert asset["asset_class"] in ["equity", "etf", "commodity", "mutual_fund", "index"]
        assert "exchange" in asset
        assert "currency" in asset
        assert "description" in asset
