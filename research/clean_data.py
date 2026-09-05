"""
NiveshPilot - Data Anomaly Detection & Cleaning Module
Enforces strict point-in-time data integrity:
- Flags impossible NAV jumps (>15% for equity, >1% for liquid)
- Flags duplicate dates and zero/negative NAVs
- Generates Data Quality Score (0 to 100)
- Triggers 'NO CLEAR SIGNAL' state when quality is compromised.
"""

import json
import os
import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
PUBLIC_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "public", "data")

def audit_fund_series(fund_id: str, df: pd.DataFrame, category: str) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Audits a single fund series for temporal anomalies, jumps, and missing records.
    Returns cleaned dataframe and audit metrics.
    """
    issues = []
    total_records = len(df)
    
    # Check required columns
    required_cols = ["date", "nav"]
    for col in required_cols:
        if col not in df.columns:
            issues.append(f"Missing required column: {col}")
            return df, {"fund_id": fund_id, "quality_score": 0, "status": "REJECTED", "issues": issues}
            
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    
    # 1. Duplicate dates
    dup_count = df.duplicated(subset=["date"]).sum()
    if dup_count > 0:
        issues.append(f"Found {dup_count} duplicate dates. Deduplicating by keeping latest.")
        df = df.drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)
        
    # 2. Zero or negative NAVs
    invalid_navs = (df["nav"] <= 0).sum()
    if invalid_navs > 0:
        issues.append(f"Found {invalid_navs} non-positive NAV values.")
        df = df[df["nav"] > 0].reset_index(drop=True)
        
    # 3. Abnormal single-day returns
    df["daily_return"] = df["nav"].pct_change()
    threshold = 0.01 if "Liquid" in category else 0.15
    abnormal_jumps = (df["daily_return"].abs() > threshold).sum()
    if abnormal_jumps > 0:
        issues.append(f"Found {abnormal_jumps} abnormal single-day return jumps exceeding {threshold*100}%.")
        
    # 4. Large date gaps
    df["date_diff"] = df["date"].diff().dt.days
    large_gaps = (df["date_diff"] > 7).sum()
    if large_gaps > 0:
        issues.append(f"Found {large_gaps} trading gaps longer than 7 calendar days.")
        
    # Calculate Data Quality Score
    score = 100
    score -= min(30, int(dup_count) * 5)
    score -= min(40, int(invalid_navs) * 20)
    score -= min(30, int(abnormal_jumps) * 10)
    score -= min(20, int(large_gaps) * 5)
    score = max(0, score)
    
    status = "ACCEPTABLE" if score >= 80 else ("CAUTION" if score >= 60 else "REJECTED")
    
    audit_report = {
        "fund_id": fund_id,
        "category": category,
        "total_records": int(len(df)),
        "start_date": df["date"].min().strftime("%Y-%m-%d"),
        "end_date": df["date"].max().strftime("%Y-%m-%d"),
        "quality_score": int(score),
        "status": status,
        "issues": issues,
        "anomalies_detected": len(issues) > 0
    }
    
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    df = df.drop(columns=["daily_return", "date_diff"], errors="ignore")
    return df, audit_report

def run_cleaning_pipeline():
    """Runs data cleaning across all registered funds."""
    with open(os.path.join(DATA_DIR, "schemes_metadata.json"), "r") as f:
        schemes = json.load(f)
        
    with open(os.path.join(DATA_DIR, "nav_history.json"), "r") as f:
        nav_histories = json.load(f)
        
    clean_histories = {}
    audit_reports = {}
    
    for scheme in schemes:
        fid = scheme["internal_id"]
        cat = scheme["category"]
        if fid in nav_histories:
            raw_df = pd.DataFrame(nav_histories[fid])
            clean_df, report = audit_fund_series(fid, raw_df, cat)
            clean_histories[fid] = clean_df.to_dict(orient="records")
            audit_reports[fid] = report
            print(f"[{fid}] Quality Score: {report['quality_score']}/100 - Status: {report['status']}")
            
    with open(os.path.join(DATA_DIR, "cleaned_nav_history.json"), "w") as f:
        json.dump(clean_histories, f)
    with open(os.path.join(PUBLIC_DATA_DIR, "cleaned_nav_history.json"), "w") as f:
        json.dump(clean_histories, f)
        
    with open(os.path.join(DATA_DIR, "data_quality_report.json"), "w") as f:
        json.dump(audit_reports, f, indent=2)
    with open(os.path.join(PUBLIC_DATA_DIR, "data_quality_report.json"), "w") as f:
        json.dump(audit_reports, f, indent=2)
        
    print(f"Data cleaning pipeline finished. Reports written.")

if __name__ == "__main__":
    run_cleaning_pipeline()
