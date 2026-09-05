"""
NiveshPilot - Feature Engineering & Market Regime Engine
Builds point-in-time quantitative features strictly without lookahead bias.
Computes returns, drawdowns, realized volatilities, downside deviations,
market regime classification, and transparent fund quality scores.

Terminology rule:
- 12-month return is reported as simple percentage return ("12-Month Return %").
- "CAGR" is reserved strictly for multi-year periods (3-year and 5-year annualized returns).
"""

import json
import os
import pandas as pd
import numpy as np
from typing import Dict, Any, List

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
PUBLIC_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "public", "data")
RISK_FREE_RATE = 0.060  # 6.0% Indian risk-free proxy (10Y G-Sec / Repo benchmark)

def compute_cagr(start_nav: float, end_nav: float, days: int) -> float:
    """
    Computes Compound Annual Growth Rate over multi-year horizons (>= 504 trading days / 2 years).
    For exactly 1 year or less, use compute_period_return instead.
    """
    if start_nav <= 0 or end_nav <= 0 or days <= 0:
        return 0.0
    years = days / 252.0
    return float((end_nav / start_nav) ** (1.0 / years) - 1.0)

def compute_period_return(start_nav: float, end_nav: float) -> float:
    """Computes total percentage return over a single period."""
    if start_nav <= 0:
        return 0.0
    return float((end_nav - start_nav) / start_nav)

def classify_market_regime(nav_series: pd.Series, dates: pd.Series) -> pd.Series:
    """
    Classifies market regime point-in-time using Benchmark NAV (Nifty 50 TRI):
    - Bull: Price > 200 SMA, 50 SMA >= 200 SMA, 3M momentum positive, low/moderate vol
    - Bear: Price < 200 SMA, 50 SMA < 200 SMA, drawdown < -15%
    - Correction: In bull market, but pullback with drawdown between -5% and -18% and 1M momentum negative
    - Recovery: Bottoming after deep correction, price crossed above 50 SMA, 1M momentum positive
    - High-volatility: Realized 30-day volatility > 28% annualized (overrides directional labels)
    - Sideways: 200 SMA slope flat and 3M return range-bound (|ret_3m| < 3%)
    - Unknown: Insufficient history (<200 days) or ambiguous signals
    """
    n = len(nav_series)
    regimes = ["Unknown"] * n
    
    sma20 = nav_series.rolling(20).mean()
    sma50 = nav_series.rolling(50).mean()
    sma200 = nav_series.rolling(200).mean()
    
    daily_ret = nav_series.pct_change()
    vol30 = daily_ret.rolling(30).std() * np.sqrt(252)
    rolling_peak = nav_series.cummax()
    drawdown = (nav_series - rolling_peak) / rolling_peak
    ret_1m = nav_series.pct_change(21)
    ret_3m = nav_series.pct_change(63)
    
    for i in range(200, n):
        p = nav_series.iloc[i]
        s20 = sma20.iloc[i]
        s50 = sma50.iloc[i]
        s200 = sma200.iloc[i]
        dd = drawdown.iloc[i]
        v30 = vol30.iloc[i]
        r1m = ret_1m.iloc[i]
        r3m = ret_3m.iloc[i]
        
        # High volatility override: severe uncertainty
        if v30 > 0.28:
            regimes[i] = "High-volatility"
        # Bear Market: deep below 200 SMA with downward cross
        elif p < s200 and s50 < s200 and dd < -0.15:
            regimes[i] = "Bear"
        # Recovery: Rebounding from deep drawdown, crossing above 50 SMA
        elif dd < -0.10 and p > s50 and r1m > 0.03:
            regimes[i] = "Recovery"
        # Correction: Pullback within a larger bull market
        elif p > s200 and dd < -0.05 and r1m < -0.02:
            regimes[i] = "Correction"
        # Bull: Healthy trend above 200 SMA & positive momentum
        elif p > s200 and s50 >= s200 and r3m > 0:
            regimes[i] = "Bull"
        # Sideways: Range-bound consolidation
        elif abs(r3m) < 0.03:
            regimes[i] = "Sideways"
        else:
            regimes[i] = "Bull" if p > s200 else "Correction"
            
    return pd.Series(regimes, index=nav_series.index)

def calculate_fund_features(df: pd.DataFrame, benchmark_df: pd.DataFrame, metadata: Dict[str, Any]) -> pd.DataFrame:
    """Calculates all point-in-time quantitative features for a single mutual fund."""
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    
    # Merge benchmark for alpha calculation
    bench_sub = benchmark_df[["date", "nav"]].rename(columns={"nav": "bench_nav"})
    bench_sub["date"] = pd.to_datetime(bench_sub["date"])
    merged = pd.merge(df, bench_sub, on="date", how="left").ffill()
    
    # 1. Daily & Rolling Returns
    merged["daily_ret"] = merged["nav"].pct_change()
    merged["bench_daily_ret"] = merged["bench_nav"].pct_change()
    
    merged["ret_1m"] = merged["nav"].pct_change(21)
    merged["ret_3m"] = merged["nav"].pct_change(63)
    merged["ret_6m"] = merged["nav"].pct_change(126)
    merged["ret_1y"] = merged["nav"].pct_change(252)  # 12-month percentage return
    
    # Annualized 3Y & 5Y returns (CAGR)
    merged["ret_3y_cagr"] = (merged["nav"] / merged["nav"].shift(756)) ** (1.0 / 3.0) - 1.0
    merged["ret_5y_cagr"] = (merged["nav"] / merged["nav"].shift(1260)) ** (1.0 / 5.0) - 1.0
    
    # 2. Drawdowns & Peak Tracking
    merged["rolling_peak"] = merged["nav"].cummax()
    merged["drawdown"] = (merged["nav"] - merged["rolling_peak"]) / merged["rolling_peak"]
    
    # Drawdown duration in trading days
    dd_durations = []
    current_dur = 0
    for dd in merged["drawdown"]:
        if dd < 0:
            current_dur += 1
        else:
            current_dur = 0
        dd_durations.append(current_dur)
    merged["drawdown_duration_days"] = dd_durations
    
    # 3. Volatility & Downside Deviation
    merged["vol_30d"] = merged["daily_ret"].rolling(30).std() * np.sqrt(252)
    merged["vol_90d"] = merged["daily_ret"].rolling(90).std() * np.sqrt(252)
    
    rf_daily = RISK_FREE_RATE / 252.0
    downside_rets = merged["daily_ret"].apply(lambda x: min(0.0, x - rf_daily))
    merged["downside_vol_90d"] = np.sqrt((downside_rets.rolling(90).apply(lambda x: (x**2).mean(), raw=True))) * np.sqrt(252)
    
    # 4. Rolling Sortino & Sharpe
    excess_ret_1y = merged["ret_1y"] - RISK_FREE_RATE
    merged["rolling_sharpe_1y"] = excess_ret_1y / (merged["vol_90d"] + 1e-6)
    merged["rolling_sortino_1y"] = excess_ret_1y / (merged["downside_vol_90d"] + 1e-6)
    
    # 5. Relative Alpha to Nifty 50 TRI
    merged["alpha_1y"] = merged["ret_1y"] - merged["bench_nav"].pct_change(252)
    
    # 6. Transparent Fund Quality Score (0 to 100)
    # Heuristic baseline weights: Consistency (35%), Downside Protection (30%), Cost Efficiency (20%), Longevity (15%)
    exp_ratio = metadata.get("expense_ratio", 0.70)
    cost_score = max(0, min(100, int((1.50 - exp_ratio) / 1.50 * 100)))
    
    quality_scores = []
    for i in range(len(merged)):
        if i < 252:
            quality_scores.append(50)  # Default prior for insufficient history
            continue
            
        dd = merged["drawdown"].iloc[i]
        sortino = merged["rolling_sortino_1y"].iloc[i]
        alpha = merged["alpha_1y"].iloc[i]
        
        # Consistency score (0-100)
        c_score = 50 + min(50, max(-50, sortino * 20))
        # Downside score (0-100)
        d_score = max(0, 100 + dd * 250)  # 0 drawdown = 100, -20% = 50, -40% = 0
        # Alpha score (0-100)
        a_score = 50 + min(50, max(-50, alpha * 300))
        
        composite = 0.35 * c_score + 0.30 * d_score + 0.20 * cost_score + 0.15 * a_score
        quality_scores.append(int(round(np.clip(composite, 0, 100))))
        
    merged["fund_quality_score"] = quality_scores
    merged["fund_id"] = metadata["internal_id"]
    merged["date"] = merged["date"].dt.strftime("%Y-%m-%d")
    
    return merged

def build_all_features():
    """Builds features for all funds and exports enriched dataset."""
    with open(os.path.join(DATA_DIR, "schemes_metadata.json"), "r") as f:
        schemes = {s["internal_id"]: s for s in json.load(f)}
        
    with open(os.path.join(DATA_DIR, "cleaned_nav_history.json"), "r") as f:
        nav_histories = json.load(f)
        
    bench_df = pd.DataFrame(nav_histories["NIFTY50_TRI"])
    bench_df["regime"] = classify_market_regime(bench_df["nav"], bench_df["date"])
    
    features_dict = {}
    latest_snapshots = []
    
    for fid, meta in schemes.items():
        if fid not in nav_histories:
            continue
        df = pd.DataFrame(nav_histories[fid])
        feat_df = calculate_fund_features(df, bench_df, meta)
        
        # Merge market regime onto fund features
        feat_df = pd.merge(feat_df, bench_df[["date", "regime"]], on="date", how="left")
        feat_df["regime"] = feat_df["regime"].fillna("Unknown")
        
        feat_df = feat_df.replace({np.nan: None})
        features_dict[fid] = feat_df.to_dict(orient="records")
        
        latest_row = feat_df.iloc[-1]
        snapshot = {
            "internal_id": fid,
            "scheme_name": meta["scheme_name"],
            "category": meta["category"],
            "amc": meta["amc"],
            "expense_ratio": meta["expense_ratio"],
            "aum_cr": meta["aum_cr"],
            "inception_date": meta["inception_date"],
            "current_nav": float(latest_row["nav"]),
            "as_of_date": latest_row["date"],
            "ret_1m": round(float(latest_row["ret_1m"] or 0) * 100, 2),
            "ret_3m": round(float(latest_row["ret_3m"] or 0) * 100, 2),
            "ret_6m": round(float(latest_row["ret_6m"] or 0) * 100, 2),
            "ret_1y": round(float(latest_row["ret_1y"] or 0) * 100, 2),  # 12-Month Return %
            "ret_3y_cagr": round(float(latest_row["ret_3y_cagr"] or 0) * 100, 2),  # 3-Year CAGR
            "ret_5y_cagr": round(float(latest_row["ret_5y_cagr"] or 0) * 100, 2),  # 5-Year CAGR
            "current_drawdown": round(float(latest_row["drawdown"] or 0) * 100, 2),
            "vol_30d": round(float(latest_row["vol_30d"] or 0) * 100, 2),
            "rolling_sortino_1y": round(float(latest_row["rolling_sortino_1y"] or 0), 2),
            "fund_quality_score": int(latest_row["fund_quality_score"] or 50),
            "market_regime": latest_row["regime"]
        }
        latest_snapshots.append(snapshot)
        print(f"Features built for {fid}: Latest NAV = {latest_row['nav']}, Quality = {latest_row['fund_quality_score']}/100")
        
    with open(os.path.join(DATA_DIR, "features.json"), "w") as f:
        json.dump(features_dict, f)
    with open(os.path.join(PUBLIC_DATA_DIR, "features.json"), "w") as f:
        json.dump(features_dict, f)
        
    with open(os.path.join(DATA_DIR, "fund_snapshots.json"), "w") as f:
        json.dump(latest_snapshots, f, indent=2)
    with open(os.path.join(PUBLIC_DATA_DIR, "fund_snapshots.json"), "w") as f:
        json.dump(latest_snapshots, f, indent=2)
        
    print("Features and latest snapshots written successfully.")

if __name__ == "__main__":
    build_all_features()
