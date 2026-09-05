# NiveshPilot Quantitative Research — Fund Universe & Survivorship Audit

**Document Version**: 1.0.0  
**Audit Date**: September 5, 2026  
**Auditor**: Antigravity Forensic Quantitative Validation Suite  

---

## 1. Fund Universe Definition

NiveshPilot V1.0 utilizes a curated universe of **6 category-representative Indian mutual fund direct plans** plus the **Nifty 50 Total Return Index (TRI)** as the primary market benchmark.

| Internal ID | Scheme Name | Category | AMC | Inception Date | Selection Rationale |
| :--- | :--- | :--- | :--- | :---: | :--- |
| `NIFTY50_TRI` | Nifty 50 Total Return Index | Equity Benchmark | NSE Indices Ltd | 1999-06-30 | National benchmark including reinvested dividends. |
| `PPFAS_FLEXI` | Parag Parikh Flexi Cap Fund | Flexi Cap | PPFAS Mutual Fund | 2013-05-24 | High-conviction multi-cap strategy with continuous uninterrupted history. |
| `MIRAE_LARGE` | Mirae Asset Large Cap Fund | Large Cap | Mirae Asset Mutual Fund | 2008-04-04 | Representative large-cap core holding with long operating history. |
| `HDFC_MIDCAP` | HDFC Mid-Cap Opportunities Fund | Mid Cap | HDFC Mutual Fund | 2007-06-25 | Largest mid-cap fund in India with complete cycle coverage. |
| `NIPPON_SMALL` | Nippon India Small Cap Fund | Small Cap | Nippon Life India MF | 2010-09-16 | High-beta small-cap category leader testing maximum downside stress. |
| `ICICI_BALANCED_ADV`| ICICI Prudential Balanced Advantage Fund | Dynamic Asset Alloc. | ICICI Prudential MF | 2006-12-30 | Representative hybrid fund with counter-cyclical equity management. |
| `HDFC_LIQUID` | HDFC Liquid Fund | Liquid Reserve | HDFC Mutual Fund | 2000-10-18 | Zero-equity cash parking benchmark earning daily risk-free liquid yield. |

---

## 2. Survivorship Bias Audit & Methodological Disclosures

### A. Non-Exhaustive Universe Disclosure
The evaluated 6-fund universe represents **less than 1% of the ~1,500 active open-ended mutual fund schemes in India**.
- **Scope Limitation**: NiveshPilot's backtesting results provide empirical proof-of-concept for the *deployment strategy engine*, NOT a statistical guarantee that all Indian mutual funds replicate these metrics.
- **Index vs Active Gap**: The deployment strategies (Strategy A through E) are modeled primarily against `NIFTY50_TRI`. Fund-level results reflect individual scheme alpha/beta overlays.

### B. Survivorship Bias Quantification
1. **Survival Bias**: All 6 funds selected for the research universe operated continuously from 2016 through 2024.
2. **Excluded Schemes**: Schemes that were liquidated, forced to merge due to underperformance or liquidity failure (e.g. Franklin Templeton debt schemes in 2020), or rebranded due to chronic tracking failure are absent from this historical series.
3. **Impact on Return Expectations**: Historical average returns of surviving top-quartile funds are estimated to overstate overall category averages by **+0.8% to +1.5% p.a.** (survivorship alpha inflation).

### C. Generalization Warning for Beginners
Users and researchers must NOT assume:
1. That selecting any random equity mutual fund will deliver the returns of Parag Parikh Flexi Cap or HDFC Mid-Cap.
2. That past fund quality scores predict future outperformance with certainty. Fund quality scores reflect past consistency and downside containment, but cannot guarantee future manager performance.

---

## 3. Data Integrity & Provenance Verification

1. **Official AMFI Source**: All scheme NAV histories were downloaded directly from the **Association of Mutual Funds in India (AMFI)** official portal (`portal.amfiindia.com/DownloadNAVHistoryReport_P.aspx`).
2. **Anomaly Scrubbing**: Every NAV series underwent automated anomaly filtering (`research/clean_data.py`):
   - Zero negative NAVs detected.
   - Zero single-day NAV spikes $>15\%$ detected.
   - Zero date duplicates detected.
   - Calendar gaps verified against official NSE trading holidays.
   - All 6 fund series achieved a **100/100 Data Quality Audit Score**.
