"""
Unit tests for Prediction Evaluation Features Foundation.

Validates:
1. Full axis / readiness boundary: lengths 1, 200, 201, longer; warmup guard at index 199,
   first ready at index 200; preservation of nonuniform gaps and synthetic weekend sessions;
   tail readiness remains present even when 1B outcome labels are unknown.
2. Missing VIX at intermediate ready origin (index 205) with nonflat price shock: only current row loses payload/readiness;
   retains original origin index, date, and Decimal Close; earlier/later computed price features match complete-VIX control;
   independently demonstrates later price feature sensitivity to shock; VIX-only observations
   do not create origins; warmup+missing reasons visible; VIX above/below 26 alters only regime.
3. Future perturbation, truncated prefix replay, and append invariance: at least 280 Nifty sessions;
   changing future prices/VIX strictly after cutoff (239) leaves all computed prefix rows bit-for-bit identical;
   truncated prefix of length 240 matches full series prefix; alters mature 1B outcome label while feature payload stays identical.
4. Flat 201+ history at Close 100 / VIX 20: zero returns, zero volatility, zero drawdown,
   zero MACD histogram, zero relative strength, RSI 0, Sideways regime; exact payload fields.
5. Independent numeric oracles: ret_5d=0.1, sample vol_30d=sqrt(0.084) (discriminating ddof=1 vs 0),
   first-spike MACD histogram=2240/3861 percentage points; mixed-gain/loss RSI 50;
   floor-sensitive RSI oracle (loss < 1e-9) at 1e-12 precision; historical peak.
6. Regime classification: discriminating full-axis synthetic fixtures for all six admitted branches,
   overlap precedence, VIX exactly 26.0 vs 26.0001, strict drawdown boundary pairs (Bear, Recovery, Correction),
   and Bull branch exact SMA equality boundary (SMA50 == SMA200).
7. Validation, conversion overflow/underflow, derived variance overflow, finite large-number Bull regime,
   subnormal tiny positive constant prices yielding Sideways (F1 regression),
   discriminating nonflat Decimal context independence, and FrozenInstanceError immutability.
8. Import and ownership audit: no generator/outcomes/network/model imports in features.py.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import datetime
from decimal import Decimal
import decimal
import hashlib
import math
from pathlib import Path
import tempfile
import unittest
from typing import List, Sequence, Tuple, Union

from research.prediction_eval.inputs import (
    AlignedPair,
    InputValidationError,
    align_pair,
    load_series,
)
from research.prediction_eval.features import (
    PROTOCOL_ID,
    REGIME_BEAR,
    REGIME_BULL,
    REGIME_CORRECTION,
    REGIME_HIGH_VOLATILITY,
    REGIME_RECOVERY,
    REGIME_SIDEWAYS,
    VALID_REGIMES,
    WARMUP_ORIGIN_INDEX,
    FeatureSeries,
    NiftyFeatureRecord,
    PredictorPayload,
    compute_nifty_features,
)
from research.prediction_eval.outcomes import (
    STATUS_MATURE,
    STATUS_UNKNOWN,
    compute_twenty_session_outcomes,
)


class TestPredictionEvalFeatures(unittest.TestCase):
    """Test suite for research/prediction_eval/features.py."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_csv(self, filename: str, content: Union[str, bytes]) -> Path:
        p = self.test_dir / filename
        if isinstance(content, str):
            p.write_text(content, encoding="utf-8")
        else:
            p.write_bytes(content)
        return p

    def _generate_calendar(self, count: int, start_date: datetime.date = datetime.date(2023, 1, 2)) -> List[datetime.date]:
        """Generates consecutive weekdays (skipping Saturday/Sunday)."""
        dates: List[datetime.date] = []
        curr = start_date
        while len(dates) < count:
            if curr.weekday() < 5:  # Monday to Friday
                dates.append(curr)
            curr += datetime.timedelta(days=1)
        return dates

    def _make_pair(
        self,
        nifty_rows: Sequence[Tuple[datetime.date, str]],
        vix_rows: Sequence[Tuple[datetime.date, str]],
        prefix: str = "test",
    ) -> AlignedPair:
        """Helper to create an AlignedPair from date/price string sequences."""
        nifty_lines = ["Date,Close"]
        for d, c in nifty_rows:
            nifty_lines.append(f"{d.strftime('%d-%b-%Y')},{c}")
        n_file = self._write_csv(f"{prefix}_nifty.csv", "\n".join(nifty_lines))

        vix_lines = ["Date,Close"]
        for d, c in vix_rows:
            vix_lines.append(f"{d.strftime('%d-%b-%Y')},{c}")
        v_file = self._write_csv(f"{prefix}_vix.csv", "\n".join(vix_lines))

        n_series = load_series("nifty50_price_index", n_file)
        v_series = load_series("india_vix", v_file)
        return align_pair(n_series, v_series)

    def test_01_full_axis_readiness_boundary_and_outcome_independence(self) -> None:
        """
        Validates:
        - Exact boundary lengths: 1, 200, 201, and 205 sessions.
        - Origin index 199 has feature_ready=False and payload=None.
        - Origin index 200 has feature_ready=True and a complete PredictorPayload when VIX is present.
        - Preserves nonuniform calendar gaps and synthetic Saturday sessions.
        - Tail readiness remains present at indices 200..204 even when 1B outcomes are unknown.
        """
        # Case A: Length 1
        d1 = [datetime.date(2023, 1, 2)]
        pair1 = self._make_pair([(d1[0], "100.00")], [(d1[0], "15.00")], prefix="len1")
        feats1 = compute_nifty_features(pair1)
        self.assertEqual(len(feats1), 1)
        self.assertFalse(feats1[0].feature_ready)
        self.assertIsNone(feats1[0].payload)
        self.assertEqual(feats1[0].unready_reasons, ("warmup",))
        self.assertEqual(feats1.ready_count, 0)
        self.assertEqual(feats1.unready_count, 1)

        # Case B: Length 200 (all unready due to warmup)
        dates200 = self._generate_calendar(200)
        n_rows200 = [(d, "100.00") for d in dates200]
        v_rows200 = [(d, "15.00") for d in dates200]
        pair200 = self._make_pair(n_rows200, v_rows200, prefix="len200")
        feats200 = compute_nifty_features(pair200)
        self.assertEqual(len(feats200), 200)
        self.assertEqual(feats200.ready_count, 0)
        self.assertEqual(feats200.unready_count, 200)
        self.assertFalse(feats200[199].feature_ready)
        self.assertIsNone(feats200[199].payload)
        self.assertEqual(feats200[199].unready_reasons, ("warmup",))

        # Case C: Length 201 (index 200 is first ready)
        dates201 = self._generate_calendar(201)
        n_rows201 = [(d, "100.00") for d in dates201]
        v_rows201 = [(d, "15.00") for d in dates201]
        pair201 = self._make_pair(n_rows201, v_rows201, prefix="len201")
        feats201 = compute_nifty_features(pair201)
        self.assertEqual(len(feats201), 201)
        self.assertEqual(feats201.ready_count, 1)
        self.assertEqual(feats201.unready_count, 200)
        self.assertFalse(feats201[199].feature_ready)
        self.assertTrue(feats201[200].feature_ready)
        self.assertIsNotNone(feats201[200].payload)
        self.assertEqual(feats201[200].unready_reasons, ())

        # Case D: Non-uniform gaps and synthetic weekend session, with cross-owner outcome comparison
        # Insert a 10-day holiday gap and a Saturday session into 205 sessions
        dates_custom: List[datetime.date] = []
        curr = datetime.date(2023, 1, 2)
        while len(dates_custom) < 205:
            if len(dates_custom) == 50:
                # Synthetic Saturday session
                dates_custom.append(curr + datetime.timedelta(days=(5 - curr.weekday())))
            elif len(dates_custom) == 100:
                # 10-day leap
                curr += datetime.timedelta(days=10)
            if curr.weekday() < 5 and curr not in dates_custom:
                dates_custom.append(curr)
            curr += datetime.timedelta(days=1)

        dates_custom.sort()
        n_rows_custom = [(d, "100.00") for d in dates_custom]
        v_rows_custom = [(d, "15.00") for d in dates_custom]
        pair_custom = self._make_pair(n_rows_custom, v_rows_custom, prefix="custom_gaps")

        feats_custom = compute_nifty_features(pair_custom)
        outcomes_custom = compute_twenty_session_outcomes(pair_custom.nifty_series)

        self.assertEqual(len(feats_custom), 205)
        self.assertEqual(feats_custom.ready_count, 5)  # indices 200, 201, 202, 203, 204
        for idx in range(200, 205):
            self.assertTrue(feats_custom[idx].feature_ready)
            self.assertIsNotNone(feats_custom[idx].payload)
            # Cross-owner assertion: 1B outcomes at indices 185..204 have is_mature=False and status='unknown'
            self.assertFalse(outcomes_custom[idx].is_mature)
            self.assertEqual(outcomes_custom[idx].status, STATUS_UNKNOWN)

    def test_02_missing_vix_intermediate_and_warmup_combination(self) -> None:
        """
        Validates:
        - Missing VIX at an intermediate ready origin (index 205) with nonflat price shock marks only origin 205 unready.
        - Retains original origin index, date, and exact Decimal Close at index 205.
        - Earlier (200..204) and later (206..209) computed numeric features match a complete-VIX control run.
        - Independently demonstrates later price features (drawdown, vol_30d) retain sensitivity to the price shock.
        - VIX-only observations do not create origins on the master Nifty axis.
        - Missing VIX during warmup (index 50) visibly exposes both reasons in order: ('warmup', 'missing_vix').
        - Changing current VIX above/below 26 changes only that origin's regime, not historical/future state.
        """
        dates = self._generate_calendar(210)
        # Nonflat price shock at missing-VIX origin index 205 (Close 110.00 between 100.00 neighbors)
        n_rows = [(dates[i], "110.00" if i == 205 else "100.00") for i in range(210)]

        # VIX rows: omit index 50 (warmup) and index 205 (ready)
        # Add an extra VIX date that does not exist in Nifty (e.g. Sunday)
        extra_vix_date = datetime.date(2023, 1, 1)  # Sunday
        v_rows = [(d, "15.00") for idx, d in enumerate(dates) if idx not in (50, 205)]
        v_rows.append((extra_vix_date, "15.00"))

        pair_missing = self._make_pair(n_rows, v_rows, prefix="vix_missing")
        feats_missing = compute_nifty_features(pair_missing)

        # Full control pair where VIX is complete for all 210 dates
        v_rows_control = [(d, "15.00") for d in dates]
        pair_control = self._make_pair(n_rows, v_rows_control, prefix="vix_control")
        feats_control = compute_nifty_features(pair_control)

        # VIX-only date did not create an extra origin
        self.assertEqual(len(feats_missing), 210)
        self.assertIn(extra_vix_date, pair_missing.vix_only_dates)

        # Warmup + missing VIX at index 50: both reasons in order
        self.assertFalse(feats_missing[50].feature_ready)
        self.assertIsNone(feats_missing[50].payload)
        self.assertEqual(feats_missing[50].unready_reasons, ("warmup", "missing_vix"))

        # Intermediate missing VIX at index 205: only index 205 is unready, retains exact metadata
        self.assertFalse(feats_missing[205].feature_ready)
        self.assertIsNone(feats_missing[205].payload)
        self.assertEqual(feats_missing[205].unready_reasons, ("missing_vix",))
        self.assertEqual(feats_missing[205].index, 205)
        self.assertEqual(feats_missing[205].date, dates[205])
        self.assertEqual(feats_missing[205].close, Decimal("110.00"))

        # Indices 200..204 and 206..209 are ready and match control
        for idx in list(range(200, 205)) + list(range(206, 210)):
            self.assertTrue(feats_missing[idx].feature_ready)
            payload_m = feats_missing[idx].payload
            payload_c = feats_control[idx].payload
            self.assertIsNotNone(payload_m)
            self.assertIsNotNone(payload_c)
            self.assertEqual(payload_m, payload_c)

        # Independently demonstrate that at least one later price feature retains the shock at index 206
        # At index 206, peak was 110.0 at index 205, so drawdown is (100 - 110) / 110 = -10/110 ~ -0.090909
        p_m206 = feats_missing[206].payload
        self.assertIsNotNone(p_m206)
        expected_dd_206 = (100.0 - 110.0) / 110.0
        self.assertTrue(math.isclose(p_m206.drawdown, expected_dd_206, rel_tol=1e-12, abs_tol=1e-12))
        self.assertNotEqual(p_m206.drawdown, 0.0)
        self.assertGreater(p_m206.vol_30d, 0.0)

        # Changing VIX at index 200 from 25.0 to 27.0 changes only regime at index 200
        n_rows_flat = [(d, "100.00") for d in dates]
        v_rows_25 = [(d, "25.00") for d in dates]
        v_rows_27 = [(d, "27.00" if idx == 200 else "25.00") for idx, d in enumerate(dates)]
        pair_25 = self._make_pair(n_rows_flat, v_rows_25, prefix="vix_25")
        pair_27 = self._make_pair(n_rows_flat, v_rows_27, prefix="vix_27")
        f_25 = compute_nifty_features(pair_25)
        f_27 = compute_nifty_features(pair_27)

        self.assertEqual(f_25[200].payload.market_regime, REGIME_SIDEWAYS)
        self.assertEqual(f_27[200].payload.market_regime, REGIME_HIGH_VOLATILITY)
        # All other ready origins have identical regime and price features
        for idx in range(201, 210):
            self.assertEqual(f_25[idx].payload, f_27[idx].payload)

    def test_03_future_perturbation_and_prefix_replay(self) -> None:
        """
        Validates:
        - At least 280 Nifty sessions (here 300 sessions).
        - Fixed ready cutoff k = 239.
        - Run A: original prices and VIX.
        - Run B: identical prefix 0..239, but sessions 240..299 have 60% price crash and altered VIX.
        - Run C: identical prefix 0..239, but appended with 50 extra future sessions (350 total).
        - Every computed row/value/reason at or before cutoff 239 matches bit-for-bit across all runs.
        - Altered future prices do change mature 1B outcome at index 225, while feature payload stays identical.
        - Legitimate change in global file provenance SHA-256 is observed.
        """
        dates350 = self._generate_calendar(350)
        dates300 = dates350[:300]
        cutoff = 239

        # Run A: steady upward sequence of 300 sessions
        n_rows_a = [(d, f"{100.0 + idx * 0.1:.2f}") for idx, d in enumerate(dates300)]
        v_rows_a = [(d, "18.00") for d in dates300]
        pair_a = self._make_pair(n_rows_a, v_rows_a, prefix="run_a")
        feats_a = compute_nifty_features(pair_a)
        outcomes_a = compute_twenty_session_outcomes(pair_a.nifty_series)

        # Run B: identical prefix 0..239, crash in future 240..299
        n_rows_b: List[Tuple[datetime.date, str]] = []
        v_rows_b: List[Tuple[datetime.date, str]] = []
        for idx, d in enumerate(dates300):
            if idx <= cutoff:
                n_rows_b.append((d, f"{100.0 + idx * 0.1:.2f}"))
                v_rows_b.append((d, "18.00"))
            else:
                # 60% drop and VIX spike
                n_rows_b.append((d, f"{(100.0 + idx * 0.1) * 0.4:.2f}"))
                v_rows_b.append((d, "35.00"))
        pair_b = self._make_pair(n_rows_b, v_rows_b, prefix="run_b")
        feats_b = compute_nifty_features(pair_b)
        outcomes_b = compute_twenty_session_outcomes(pair_b.nifty_series)

        # Run C: identical prefix 0..239, appended to 350 sessions
        n_rows_c = [(d, f"{100.0 + idx * 0.1:.2f}") for idx, d in enumerate(dates350)]
        v_rows_c = [(d, "18.00") for d in dates350]
        pair_c = self._make_pair(n_rows_c, v_rows_c, prefix="run_c")
        feats_c = compute_nifty_features(pair_c)

        # Run T: truncated identical prefix containing strictly only the first cutoff + 1 sessions (0..239)
        n_rows_t = n_rows_a[: cutoff + 1]
        v_rows_t = v_rows_a[: cutoff + 1]
        pair_t = self._make_pair(n_rows_t, v_rows_t, prefix="run_t")
        feats_t = compute_nifty_features(pair_t)
        self.assertEqual(len(feats_t), cutoff + 1)

        # File provenance hashes differ due to changed future file content
        self.assertNotEqual(
            pair_a.nifty_series.provenance[0].sha256,
            pair_b.nifty_series.provenance[0].sha256,
        )

        # Prefix replay invariance: all rows 0..239 must match exactly across all runs
        for i in range(cutoff + 1):
            rec_a = feats_a[i]
            rec_b = feats_b[i]
            rec_c = feats_c[i]
            rec_t = feats_t[i]

            self.assertEqual(rec_a.feature_ready, rec_b.feature_ready)
            self.assertEqual(rec_a.feature_ready, rec_c.feature_ready)
            self.assertEqual(rec_a.feature_ready, rec_t.feature_ready)
            self.assertEqual(rec_a.unready_reasons, rec_b.unready_reasons)
            self.assertEqual(rec_a.unready_reasons, rec_c.unready_reasons)
            self.assertEqual(rec_a.unready_reasons, rec_t.unready_reasons)

            if rec_a.feature_ready:
                p_a = rec_a.payload
                p_b = rec_b.payload
                p_c = rec_c.payload
                p_t = rec_t.payload
                self.assertIsNotNone(p_a)
                self.assertIsNotNone(p_b)
                self.assertIsNotNone(p_c)
                self.assertIsNotNone(p_t)
                self.assertEqual(p_a, p_b)
                self.assertEqual(p_a, p_c)
                self.assertEqual(p_a, p_t)

        # Cross-owner verification: at origin 225, maturity session is 225 + 20 = 245
        # In Run A, price at 245 was rising (+0.1/day) -> mature Bull outcome
        # In Run B, price at 245 crashed by 60% -> mature Bear outcome
        # Feature payload at origin 225 remains 100% identical!
        self.assertTrue(outcomes_a[225].is_mature)
        self.assertTrue(outcomes_b[225].is_mature)
        self.assertNotEqual(outcomes_a[225].outcome_class, outcomes_b[225].outcome_class)
        self.assertEqual(feats_a[225].payload, feats_b[225].payload)

    def test_04_flat_history_zero_invariants_and_payload_fields(self) -> None:
        """
        Validates:
        - Flat history of 205 sessions at Close 100.0 and VIX 20.0.
        - Exact zero returns, zero volatility, zero drawdown, zero MACD hist, zero relative strength.
        - RSI 14 is exactly 0.0 (inherited convention: flat yields RSI 0, NOT 50).
        - Regime is Sideways.
        - PredictorPayload has EXACTLY the 7 named fields and no future/outcome fields.
        """
        dates = self._generate_calendar(205)
        n_rows = [(d, "100.00") for d in dates]
        v_rows = [(d, "20.00") for d in dates]
        pair = self._make_pair(n_rows, v_rows, prefix="flat")
        feats = compute_nifty_features(pair)

        self.assertEqual(len(feats), 205)
        for i in range(200, 205):
            rec = feats[i]
            self.assertTrue(rec.feature_ready)
            payload = rec.payload
            self.assertIsNotNone(payload)
            self.assertEqual(payload.ret_5d, 0.0)
            self.assertEqual(payload.vol_30d, 0.0)
            self.assertEqual(payload.drawdown, 0.0)
            self.assertEqual(payload.macd_hist, 0.0)
            self.assertEqual(payload.rel_strength_20d, 0.0)
            self.assertEqual(payload.rsi_14, 0.0)
            self.assertEqual(payload.market_regime, REGIME_SIDEWAYS)

            # Field set audit: exactly 7 fields
            field_names = tuple(f for f in payload.__dataclass_fields__.keys())
            expected_fields = (
                "ret_5d",
                "rsi_14",
                "macd_hist",
                "vol_30d",
                "rel_strength_20d",
                "drawdown",
                "market_regime",
            )
            self.assertEqual(field_names, expected_fields)
            for forbidden in ("future_ret_1d", "future_ret_5d", "future_ret_20d", "outcome_class"):
                self.assertFalse(hasattr(payload, forbidden))

    def test_05_independent_numeric_oracles(self) -> None:
        """
        Validates exact independent mathematical oracles:
        - 200 Closes at 100 followed by Close 110 at index 200:
          * ret_5d = 0.1
          * vol_30d = sqrt(0.084) (strictly discriminates ddof=1 vs ddof=0)
          * MACD histogram = 2240/3861 percentage points
        - Mixed-gain/loss fixture (equal gains and losses -> RSI 50.0).
        - Floor-sensitive RSI oracle (loss < 1e-9) at 1e-12 precision.
        - Historical peak immutability (later higher price cannot alter earlier drawdown).
        """
        dates = self._generate_calendar(205)

        # Oracle 1: 200 Closes at 100, then Close 110 at index 200
        n_rows = [(d, "100.00") for d in dates[:200]] + [(dates[200], "110.00")] + [(d, "110.00") for d in dates[201:205]]
        v_rows = [(d, "20.00") for d in dates]
        pair = self._make_pair(n_rows, v_rows, prefix="oracle_spike")
        feats = compute_nifty_features(pair)

        p200 = feats[200].payload
        self.assertIsNotNone(p200)

        # ret_5d: 110 / 100 - 1 = 0.1
        self.assertTrue(math.isclose(p200.ret_5d, 0.1, rel_tol=1e-12, abs_tol=1e-12))

        # vol_30d: sample standard deviation with ddof=1 is sqrt(0.084)
        expected_vol = math.sqrt(0.084)
        self.assertTrue(math.isclose(p200.vol_30d, expected_vol, rel_tol=1e-12, abs_tol=1e-12))
        # Population vol with ddof=0 would be sqrt(29/30 * 0.084) = sqrt(0.0812) != sqrt(0.084)
        pop_vol = math.sqrt(29.0 / 30.0 * 0.084)
        self.assertFalse(math.isclose(p200.vol_30d, pop_vol, rel_tol=1e-4))

        # MACD histogram: 2240 / 3861 percentage points
        expected_macd_hist = 2240.0 / 3861.0
        self.assertTrue(math.isclose(p200.macd_hist, expected_macd_hist, rel_tol=1e-12, abs_tol=1e-12))

        # Oracle 2: Mixed-gain/loss fixture (equal gains and losses over last 14 entries -> RSI 50.0)
        # 187 sessions flat at 100, then 14 sessions alternating +1, -1: 101, 100, 101, 100...
        n_rows_rsi = [(d, "100.00") for d in dates[:187]]
        curr_price = 100.0
        for i in range(187, 201):
            curr_price = 101.0 if (i % 2 == 1) else 100.0
            n_rows_rsi.append((dates[i], f"{curr_price:.2f}"))
        pair_rsi = self._make_pair(n_rows_rsi, v_rows[:201], prefix="oracle_rsi")
        feats_rsi = compute_nifty_features(pair_rsi)
        p_rsi = feats_rsi[200].payload
        self.assertIsNotNone(p_rsi)
        self.assertTrue(math.isclose(p_rsi.rsi_14, 50.0, rel_tol=1e-12, abs_tol=1e-12))

        # Oracle 3: Historical peak immutability
        # Prices start at 150, drop to 120, then at index 203 spike to 200
        n_rows_peak = [(dates[0], "150.00")] + [(d, "120.00") for d in dates[1:203]] + [(d, "200.00") for d in dates[203:205]]
        pair_peak = self._make_pair(n_rows_peak, v_rows, prefix="oracle_peak")
        feats_peak = compute_nifty_features(pair_peak)

        # At index 200, peak was 150.0, so drawdown is (120 - 150) / 150 = -0.2
        expected_dd_200 = (120.0 - 150.0) / 150.0
        self.assertTrue(math.isclose(feats_peak[200].payload.drawdown, expected_dd_200, rel_tol=1e-12, abs_tol=1e-12))
        # At index 203, new peak is 200.0, drawdown is 0.0
        self.assertTrue(math.isclose(feats_peak[203].payload.drawdown, 0.0, rel_tol=1e-12, abs_tol=1e-12))

        # Oracle 4: Floor-sensitive RSI oracle (nonzero loss below 1e-9 floor)
        # Over 14 entries (187..200):
        # Index 188 has gain ~ 1.4e-8 (mean_gain ~ 1e-9)
        # Index 189 has loss ~ 1.4e-10 (mean_loss ~ 1e-11 < 1e-9)
        # With active 1e-9 denominator floor, effective denominator is clamped to 1e-9.
        # Independent oracle derived from represented binary64 floats accounts for delta rounding.
        n_rows_floor = [(d, "10.00000000000") for d in dates[:188]]
        n_rows_floor.append((dates[188], "10.00000001400"))
        n_rows_floor.append((dates[189], "10.00000001386"))
        for d in dates[190:201]:
            n_rows_floor.append((d, "10.00000001386"))
        pair_floor = self._make_pair(n_rows_floor, v_rows[:201], prefix="oracle_rsi_floor")
        feats_floor = compute_nifty_features(pair_floor)
        p_floor = feats_floor[200].payload
        self.assertIsNotNone(p_floor)

        # Independent oracle from represented binary64 inputs:
        c_base = float(Decimal("10.00000000000"))
        c_spike = float(Decimal("10.00000001400"))
        c_drop = float(Decimal("10.00000001386"))

        # Represented deltas:
        delta_gain = c_spike - c_base
        delta_loss = -(c_drop - c_spike)

        # 14-period arithmetic means:
        mean_gain_oracle = delta_gain / 14.0
        mean_loss_oracle = delta_loss / 14.0

        # Loss is strictly positive but below 1e-9 floor (discriminates floor activation):
        self.assertGreater(mean_loss_oracle, 0.0)
        self.assertLess(mean_loss_oracle, 1e-9)

        # With active 1e-9 floor, effective denominator is 1e-9:
        rs_floored_oracle = mean_gain_oracle / 1e-9
        expected_rsi_floored = 100.0 - (100.0 / (1.0 + rs_floored_oracle))

        # Assert BOTH rel_tol=1e-12 and abs_tol=1e-12 against independent oracle:
        self.assertTrue(math.isclose(p_floor.rsi_14, expected_rsi_floored, rel_tol=1e-12, abs_tol=1e-12))

        # Discriminate removal of denominator floor:
        # Without floor, denominator would be mean_loss (~1e-11), giving rs ~ 100 and rsi ~ 99.01
        rs_unfloored_oracle = mean_gain_oracle / mean_loss_oracle
        expected_rsi_unfloored = 100.0 - (100.0 / (1.0 + rs_unfloored_oracle))
        self.assertFalse(math.isclose(p_floor.rsi_14, expected_rsi_unfloored, rel_tol=1e-2))

    def test_06_regime_classification_all_branches_and_boundaries(self) -> None:
        """
        Validates:
        - Discriminating fixtures for all six admitted branches:
          1. High-volatility (VIX > 26.0)
          2. Bear (p < SMA200 and SMA50 < SMA200 and drawdown < -0.15)
          3. Recovery (drawdown < -0.08 and p > SMA50 and r20 > 0.02)
          4. Correction (p > SMA200 and drawdown < -0.04 and r20 < -0.015)
          5. Bull (p > SMA200 and SMA50 >= SMA200 and r20 >= 0)
          6. Sideways (otherwise)
        - Overlap precedence: VIX > 26 overrides Bear price conditions.
        - Boundary checks: VIX == 26.0 vs 26.0001, drawdown threshold boundaries.
        """
        dates = self._generate_calendar(205)

        # 1. High-volatility branch (VIX = 27.0 > 26.0)
        p_hv = self._make_pair([(d, "100.00") for d in dates], [(d, "27.00") for d in dates], prefix="reg_hv")
        self.assertEqual(compute_nifty_features(p_hv)[200].payload.market_regime, REGIME_HIGH_VOLATILITY)

        # Strict boundary: VIX == 26.0 is NOT High-volatility
        p_vix26 = self._make_pair([(d, "100.00") for d in dates], [(d, "26.00") for d in dates], prefix="reg_vix26")
        self.assertEqual(compute_nifty_features(p_vix26)[200].payload.market_regime, REGIME_SIDEWAYS)

        # VIX == 26.0001 IS High-volatility
        p_vix26_eps = self._make_pair([(d, "100.00") for d in dates], [(d, "26.0001") for d in dates], prefix="reg_vix26_eps")
        self.assertEqual(compute_nifty_features(p_vix26_eps)[200].payload.market_regime, REGIME_HIGH_VOLATILITY)

        # 2. Bear branch: peak=200, steady decline to 100
        # Indices 0..100 at 200, then declining down to 100 at index 200
        # p=100, SMA50 ~ 110, SMA200 ~ 150 -> p < SMA200, SMA50 < SMA200, dd = (100-200)/200 = -0.50 < -0.15
        n_rows_bear = [(dates[i], f"{200.0 - (100.0 * i / 200.0):.2f}") for i in range(205)]
        p_bear = self._make_pair(n_rows_bear, [(d, "20.00") for d in dates], prefix="reg_bear")
        self.assertEqual(compute_nifty_features(p_bear)[200].payload.market_regime, REGIME_BEAR)

        # Overlap precedence: Bear price condition with VIX = 30.0 -> High-volatility
        p_bear_hv = self._make_pair(n_rows_bear, [(d, "30.00") for d in dates], prefix="reg_bear_hv")
        self.assertEqual(compute_nifty_features(p_bear_hv)[200].payload.market_regime, REGIME_HIGH_VOLATILITY)

        # 3. Recovery branch:
        # Peak=120, dropped to 100 (dd=-0.166), then in last 20 days surged to 108.
        # At index 200: p=108, peak=120 -> dd = (108-120)/120 = -0.10 (< -0.08, but >= -0.15 so not Bear).
        # r20 = 108/100 - 1 = 0.08 > 0.02. SMA50 ~ 103 < 108.
        n_rows_rec = [(dates[0], "120.00")] + [(d, "100.00") for d in dates[1:181]] + [(d, "108.00") for d in dates[181:205]]
        p_rec = self._make_pair(n_rows_rec, [(d, "20.00") for d in dates], prefix="reg_rec")
        self.assertEqual(compute_nifty_features(p_rec)[200].payload.market_regime, REGIME_RECOVERY)

        # 4. Correction branch:
        # Uptrend: 0..150 at 100, 151..195 at 150 (peak=150), then pull back to 140 over last 5 days (196..200).
        # At index 200: p=140, peak=150 -> dd = (140-150)/150 = -0.0667 (< -0.04).
        # SMA200 ~ 111 < 140. r20 = 140/150 - 1 = -0.0667 (< -0.015).
        n_rows_corr = [(d, "100.00") for d in dates[:150]] + [(d, "150.00") for d in dates[150:195]] + [(d, "140.00") for d in dates[195:205]]
        p_corr = self._make_pair(n_rows_corr, [(d, "20.00") for d in dates], prefix="reg_corr")
        self.assertEqual(compute_nifty_features(p_corr)[200].payload.market_regime, REGIME_CORRECTION)

        # 5. Bull branch:
        # Steady uptrend / high plateau: 0..100 at 100, 101..205 at 120.
        # At index 200: p=120, SMA200 ~ 110, SMA50 = 120 >= SMA200, r20 = 0.0 >= 0, dd = 0.0.
        n_rows_bull = [(d, "100.00") for d in dates[:100]] + [(d, "120.00") for d in dates[100:205]]
        p_bull = self._make_pair(n_rows_bull, [(d, "20.00") for d in dates], prefix="reg_bull")
        self.assertEqual(compute_nifty_features(p_bull)[200].payload.market_regime, REGIME_BULL)

        # 5b. Bull branch with SMA50 EXACTLY equal to SMA200 (boundary condition: sma50 >= sma200)
        # 201 observations: indices 0..198 at 100.00, index 199 at 80.00, index 200 at 120.00; VIX 20.00.
        # Mathematical and binary64 representation:
        # Last 50 (indices 151..200): 48 * 100.0 + 80.0 + 120.0 = 5000.0 -> SMA50 = 5000.0 / 50.0 = 100.0.
        # Last 200 (indices 1..200): 198 * 100.0 + 80.0 + 120.0 = 20000.0 -> SMA200 = 20000.0 / 200.0 = 100.0.
        # At index 200: p = 120.0 > SMA200 (100.0).
        # SMA50 == SMA200 (100.0 == 100.0).
        # r20 = (120.0 / 100.0) - 1.0 = 0.20 >= 0.0.
        # peak = 120.0 -> drawdown = 0.0 (excludes Bear, Recovery, Correction).
        # VIX = 20.0 <= 26.0 (excludes High-volatility).
        # Admitted Bull at exact equality: discriminates replacing >= with > in Bull rule.
        c50_vals = [100.0] * 48 + [80.0, 120.0]
        c200_vals = [100.0] * 198 + [80.0, 120.0]
        expected_sma50 = sum(c50_vals) / 50.0
        expected_sma200 = sum(c200_vals) / 200.0
        self.assertEqual(expected_sma50, 100.0)
        self.assertEqual(expected_sma200, 100.0)
        self.assertEqual(expected_sma50, expected_sma200)

        n_rows_bull_eq = [(dates[i], "100.00") for i in range(199)] + [
            (dates[199], "80.00"),
            (dates[200], "120.00"),
        ]
        p_bull_eq = self._make_pair(n_rows_bull_eq, [(d, "20.00") for d in dates[:201]], prefix="reg_bull_eq")
        feats_bull_eq = compute_nifty_features(p_bull_eq)
        rec_bull_eq = feats_bull_eq[200]
        self.assertTrue(rec_bull_eq.feature_ready)
        self.assertIsNotNone(rec_bull_eq.payload)
        self.assertEqual(rec_bull_eq.payload.market_regime, REGIME_BULL)

        # 6. Sideways branch: flat 100
        p_side = self._make_pair([(d, "100.00") for d in dates], [(d, "20.00") for d in dates], prefix="reg_side")
        self.assertEqual(compute_nifty_features(p_side)[200].payload.market_regime, REGIME_SIDEWAYS)

        # Strict drawdown boundary pairs:
        # A. Bear boundary (-0.15 vs -0.1505):
        # Peak 200.0, price declining down to 170.0 (dd = -0.15) vs 169.90 (dd = -0.1505).
        # Requires p < SMA200 and SMA50 < SMA200.
        n_rows_bear_base = [(dates[i], "200.00") for i in range(100)] + [
            (dates[i], f"{200.0 - 20.0 * (i - 100) / 50.0:.2f}") for i in range(100, 150)
        ] + [
            (dates[i], f"{180.0 - 9.0 * (i - 150) / 49.0:.2f}") for i in range(150, 200)
        ]
        # At index 200, close 170.00: dd = (170 - 200)/200 = -0.15. dd < -0.15 is False -> Sideways.
        pair_bear_eq = self._make_pair(
            n_rows_bear_base + [(dates[200], "170.00")] + [(d, "170.00") for d in dates[201:]],
            [(d, "20.00") for d in dates],
            prefix="bear_eq",
        )
        self.assertEqual(compute_nifty_features(pair_bear_eq)[200].payload.market_regime, REGIME_SIDEWAYS)

        # At index 200, close 169.90: dd = (169.90 - 200)/200 = -0.1505 < -0.15. dd < -0.15 is True -> Bear.
        pair_bear_out = self._make_pair(
            n_rows_bear_base + [(dates[200], "169.90")] + [(d, "169.90") for d in dates[201:]],
            [(d, "20.00") for d in dates],
            prefix="bear_out",
        )
        self.assertEqual(compute_nifty_features(pair_bear_out)[200].payload.market_regime, REGIME_BEAR)

        # B. Recovery boundary (-0.08 vs -0.081):
        # Peak 100.0, drop to 80.0, surge to 92.0 (dd = -0.08) vs 91.90 (dd = -0.081).
        # Requires p > SMA50 and r20 > 0.02, while not meeting Bull (p <= SMA200 or SMA50 < SMA200).
        n_rows_rec_base = [(dates[i], "100.00") for i in range(150)] + [
            (dates[i], "80.00") for i in range(150, 181)
        ] + [
            (dates[i], "85.00") for i in range(181, 200)
        ]
        # At index 200, close 92.00: dd = (92 - 100)/100 = -0.08. dd < -0.08 is False -> Sideways.
        pair_rec_eq = self._make_pair(
            n_rows_rec_base + [(dates[200], "92.00")] + [(d, "92.00") for d in dates[201:]],
            [(d, "20.00") for d in dates],
            prefix="rec_eq",
        )
        self.assertEqual(compute_nifty_features(pair_rec_eq)[200].payload.market_regime, REGIME_SIDEWAYS)

        # At index 200, close 91.90: dd = (91.90 - 100)/100 = -0.081 < -0.08. dd < -0.08 is True -> Recovery.
        pair_rec_out = self._make_pair(
            n_rows_rec_base + [(dates[200], "91.90")] + [(d, "91.90") for d in dates[201:]],
            [(d, "20.00") for d in dates],
            prefix="rec_out",
        )
        self.assertEqual(compute_nifty_features(pair_rec_out)[200].payload.market_regime, REGIME_RECOVERY)

        # C. Correction boundary (-0.04 vs -0.041):
        # Uptrend with pullback: 0..150 at 80.0, 151..195 at 100.0 (peak 100.0), 196..199 at 97.0.
        # At index 200, close 96.00 (dd = -0.04) vs 95.90 (dd = -0.041).
        # Requires p > SMA200 and r20 < -0.015.
        n_rows_corr_base = [(dates[i], "80.00") for i in range(150)] + [
            (dates[i], "100.00") for i in range(150, 196)
        ] + [
            (dates[i], "97.00") for i in range(196, 200)
        ]
        # At index 200, close 96.00: dd = (96 - 100)/100 = -0.04. dd < -0.04 is False -> Sideways.
        pair_corr_eq = self._make_pair(
            n_rows_corr_base + [(dates[200], "96.00")] + [(d, "96.00") for d in dates[201:]],
            [(d, "20.00") for d in dates],
            prefix="corr_eq",
        )
        self.assertEqual(compute_nifty_features(pair_corr_eq)[200].payload.market_regime, REGIME_SIDEWAYS)

        # At index 200, close 95.90: dd = (95.90 - 100)/100 = -0.041 < -0.04. dd < -0.04 is True -> Correction.
        pair_corr_out = self._make_pair(
            n_rows_corr_base + [(dates[200], "95.90")] + [(d, "95.90") for d in dates[201:]],
            [(d, "20.00") for d in dates],
            prefix="corr_out",
        )
        self.assertEqual(compute_nifty_features(pair_corr_out)[200].payload.market_regime, REGIME_CORRECTION)

    def test_07_validation_nonfinite_and_immutability(self) -> None:
        """
        Validates:
        - Rejection of invalid API types and swapped series roles.
        - Conversion overflow and underflow rejection on Nifty and VIX Close.
        - Derived variance overflow rejection (field='vol_30d').
        - Exact large-number Bull regime calculation (A1 primary trigger) without overflow.
        - Arithmetic independence from ambient low Decimal precision context on discriminating nonflat series.
        - Immutability of feature series, feature records, and predictor payloads (FrozenInstanceError).
        - Preservation of input series and raw fixture files on disk.
        """
        dates = self._generate_calendar(205)
        pair = self._make_pair([(d, "100.00") for d in dates], [(d, "20.00") for d in dates], prefix="valid_test")

        # Rejection of wrong types
        with self.assertRaises(InputValidationError):
            compute_nifty_features("invalid_type")  # type: ignore[arg-type]

        # Swapped series roles
        swapped_pair = AlignedPair(
            nifty_series=pair.vix_series,
            vix_series=pair.nifty_series,
            aligned_observations=pair.aligned_observations,
            nifty_only_dates=(),
            vix_only_dates=(),
            calendar_status="not_checked",
            missing_sessions=(),
            extra_sessions=(),
        )
        with self.assertRaises(InputValidationError):
            compute_nifty_features(swapped_pair)

        # 1. Conversion overflow on Nifty Close (e.g. 10^309 exceeds binary64 max ~ 1.79e308)
        n_rows_ovfl = [(dates[0], "1" + "0" * 309)] + [(d, "100.00") for d in dates[1:]]
        pair_ovfl = self._make_pair(n_rows_ovfl, [(d, "20.00") for d in dates], prefix="ovfl_nifty")
        with self.assertRaises(InputValidationError) as cm_ovfl:
            compute_nifty_features(pair_ovfl)
        self.assertIn(cm_ovfl.exception.field, ("close", "nifty_close"))

        # 2. Conversion underflow on Nifty Close (e.g. 10^-330 underflows float to 0.0)
        n_rows_undfl = [(dates[0], "0." + "0" * 330 + "1")] + [(d, "100.00") for d in dates[1:]]
        pair_undfl = self._make_pair(n_rows_undfl, [(d, "20.00") for d in dates], prefix="undfl_nifty")
        with self.assertRaises(InputValidationError) as cm_undfl:
            compute_nifty_features(pair_undfl)
        self.assertIn(cm_undfl.exception.field, ("close", "nifty_close"))

        # 3. VIX conversion overflow at ready origin (index 200)
        v_rows_vix_ovfl = [(d, "20.00") for d in dates[:200]] + [(dates[200], "1" + "0" * 309)] + [(d, "20.00") for d in dates[201:]]
        pair_vix_ovfl = self._make_pair([(d, "100.00") for d in dates], v_rows_vix_ovfl, prefix="ovfl_vix")
        with self.assertRaises(InputValidationError) as cm_vix:
            compute_nifty_features(pair_vix_ovfl)
        self.assertEqual(cm_vix.exception.field, "vix_close")

        # 4. VIX conversion underflow at ready origin (index 200)
        # Positive tiny plain-decimal VIX that underflows binary64 float to 0.0
        v_rows_vix_undfl = [(d, "20.00") for d in dates[:200]] + [(dates[200], "0." + "0" * 330 + "1")] + [(d, "20.00") for d in dates[201:]]
        pair_vix_undfl = self._make_pair([(d, "100.00") for d in dates], v_rows_vix_undfl, prefix="undfl_vix")
        with self.assertRaises(InputValidationError) as cm_vix_undfl:
            compute_nifty_features(pair_vix_undfl)
        self.assertEqual(cm_vix_undfl.exception.field, "vix_close")
        self.assertIn("200", str(cm_vix_undfl.exception))
        self.assertIn(str(dates[200]), str(cm_vix_undfl.exception))

        # 5. Derived variance overflow (A1 related trigger: 200 Closes 1 followed by 10^200)
        n_rows_var_ovfl = [(d, "1.00") for d in dates[:200]] + [(dates[200], "1" + "0" * 200)] + [(d, "1.00") for d in dates[201:]]
        pair_var_ovfl = self._make_pair(n_rows_var_ovfl, [(d, "20.00") for d in dates], prefix="var_ovfl")
        with self.assertRaises(InputValidationError) as cm_var:
            compute_nifty_features(pair_var_ovfl)
        self.assertEqual(cm_var.exception.field, "vol_30d")

        # 6. Finite large-number Bull regime (A1 primary trigger):
        # 201 observations: 0..99 at 10^307, 100..200 at 1.2*10^307, all VIX 20.0
        # Closes are plain decimal digits; individual binary64 floats are finite (< 1.79e308).
        # Trailing means: SMA50 = 1.2e307, SMA200 = 1.101e307, drawdown = 0, r20 = 0.
        # Evaluates to Bull regime without intermediate overflow to infinity or fall-through to Sideways.
        c_10e307 = "1" + "0" * 307
        c_12e307 = "12" + "0" * 306
        n_rows_large = [(dates[i], c_10e307) for i in range(100)] + [(dates[i], c_12e307) for i in range(100, 201)]
        v_rows_large = [(dates[i], "20.00") for i in range(201)]
        pair_large = self._make_pair(n_rows_large, v_rows_large, prefix="large_bull")
        feats_large = compute_nifty_features(pair_large)
        self.assertTrue(feats_large[200].feature_ready)
        p_large = feats_large[200].payload
        self.assertIsNotNone(p_large)
        self.assertEqual(p_large.market_regime, REGIME_BULL)

        # 6b. Subnormal tiny positive constant prices yield Sideways regime (F1 regression):
        # 201 observations at "0." + "0" * 323 + "5" (binary64 5e-324), all VIX 20.0.
        # Positive representable subnormal float: passes loader parsing and float conversion.
        # Trailing means SMA50 and SMA200 must stably preserve 5e-324 without underflowing to 0.0.
        # With p == 5e-324 == SMA200, p > SMA200 is False, so flat history correctly selects Sideways.
        c_tiny_str = "0." + "0" * 323 + "5"
        raw_float = float(Decimal(c_tiny_str))
        self.assertGreater(raw_float, 0.0)
        self.assertEqual(raw_float, 5e-324)

        n_rows_tiny = [(dates[i], c_tiny_str) for i in range(201)]
        v_rows_tiny = [(dates[i], "20.00") for i in range(201)]
        pair_tiny = self._make_pair(n_rows_tiny, v_rows_tiny, prefix="tiny_flat_f1")
        feats_tiny = compute_nifty_features(pair_tiny)
        self.assertTrue(feats_tiny[200].feature_ready)
        p_tiny = feats_tiny[200].payload
        self.assertIsNotNone(p_tiny)
        self.assertEqual(p_tiny.market_regime, REGIME_SIDEWAYS)

        # 7. Context independence on discriminating nonflat series: prec=1 and Traps active
        n_rows_varying = [(d, f"{100.0 + idx * 0.5:.2f}") for idx, d in enumerate(dates)]
        v_rows_varying = [(d, "22.50") for d in dates]
        pair_varying = self._make_pair(n_rows_varying, v_rows_varying, prefix="var_ctx")
        feats_normal = compute_nifty_features(pair_varying)

        with decimal.localcontext() as ctx:
            ctx.prec = 1
            ctx.traps[decimal.Inexact] = True
            ctx.traps[decimal.Rounded] = True
            feats_low_prec = compute_nifty_features(pair_varying)
            self.assertEqual(feats_low_prec.total_origins, 205)
            self.assertEqual(feats_low_prec[200].payload, feats_normal[200].payload)

        # 8. Immutability of returned records and series (FrozenInstanceError)
        feats = compute_nifty_features(pair)
        rec200 = feats[200]
        with self.assertRaises(FrozenInstanceError):
            rec200.feature_ready = False  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            rec200.payload.ret_5d = 1.0  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            feats.records = ()  # type: ignore[misc]

        # Raw file byte preservation
        for prov in pair.nifty_series.provenance:
            f_bytes = Path(prov.file_path).read_bytes()
            self.assertEqual(len(f_bytes), prov.raw_byte_count)
            self.assertEqual(hashlib.sha256(f_bytes).hexdigest(), prov.sha256)

    def test_08_import_and_source_audit(self) -> None:
        """
        Validates import boundaries (SOURCE_INSPECTED):
        - research.prediction_eval.features does not import outcomes, models, network, or generator.
        """
        import research.prediction_eval.features as feat_mod

        # Inspect module source or attributes
        module_dict = feat_mod.__dict__
        forbidden_terms = (
            "outcomes",
            "compute_twenty_session_outcomes",
            "market_intelligence_engine",
            "pandas",
            "numpy",
            "urllib",
            "requests",
            "socket",
        )
        for term in forbidden_terms:
            self.assertNotIn(term, module_dict, f"Forbidden reference '{term}' found in features module.")


if __name__ == "__main__":
    unittest.main()
