"""
Unit tests for Prediction Evaluation Outcomes Foundation.

Validates:
1. Twenty-position clock: origin 0 pairs with index 20 (not 19 or 21) across calendar gaps and weekends.
2. Synthetic axis counterexample: origin 100 with index-20 at 99.4 is BEAR even with missing VIX at index 10.
3. Exact classification boundaries: +/-0.5% exact boundaries are NEUTRAL; just-outside are BULL/BEAR.
4. Non-100 origin and high-precision Decimal exactness.
5. Independence from ambient Decimal context precision (prec=1) and arithmetic rounding traps.
6. Sequence lengths (short, exactly 20, exactly 21, longer) and explicit unknown tail preservation.
7. Rejection of wrong declared series role (e.g. india_vix) and invalid input types.
8. Immutability, frozen records, and source series / raw fixture byte preservation.
9. Rejection of contradictory TwentySessionOutcome construction states.
"""

from __future__ import annotations

import datetime
import decimal
from decimal import Decimal
import hashlib
from pathlib import Path
import tempfile
import unittest
from typing import List, Union

from research.prediction_eval.inputs import (
    InputValidationError,
    align_pair,
    load_series,
)
from research.prediction_eval.outcomes import (
    HORIZON_SESSIONS,
    OUTCOME_CLASS_BEAR,
    OUTCOME_CLASS_BULL,
    OUTCOME_CLASS_NEUTRAL,
    STATUS_MATURE,
    STATUS_UNKNOWN,
    OutcomeSeries,
    TwentySessionOutcome,
    classify_twenty_session_move,
    compute_twenty_session_outcomes,
)


class TestPredictionEvalOutcomes(unittest.TestCase):
    """Test suite for research/prediction_eval/outcomes.py."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_file(self, filename: str, content: Union[str, bytes]) -> Path:
        p = self.test_dir / filename
        if isinstance(content, str):
            p.write_text(content, encoding="utf-8")
        else:
            p.write_bytes(content)
        return p

    def test_01_twenty_position_clock_and_calendar_gaps(self) -> None:
        """
        Validates the 20-position clock invariant:
        - Origin index i pairs strictly with maturity index i + 20 (origin 0 -> index 20, NOT 19 or 21).
        - Positional counting operates on the supplied sorted axis regardless of calendar gaps,
          holidays, or synthetic weekend trading sessions.
        """
        # Construct 25 sessions with intentional non-uniform calendar spacing:
        # e.g., 01-Jan, 02-Jan, 05-Jan (Friday), 06-Jan (Saturday weekend session),
        # 16-Jan (10-day gap), etc.
        dates: List[datetime.date] = [
            datetime.date(2024, 1, 1),
            datetime.date(2024, 1, 2),
            datetime.date(2024, 1, 3),
            datetime.date(2024, 1, 4),
            datetime.date(2024, 1, 5),   # Index 4 (Friday)
            datetime.date(2024, 1, 6),   # Index 5 (Saturday synthetic session)
            datetime.date(2024, 1, 8),   # Index 6 (Monday)
            datetime.date(2024, 1, 9),
            datetime.date(2024, 1, 10),
            datetime.date(2024, 1, 11),
            datetime.date(2024, 1, 12),
            datetime.date(2024, 1, 15),
            datetime.date(2024, 1, 16),
            datetime.date(2024, 1, 17),
            datetime.date(2024, 1, 18),
            datetime.date(2024, 1, 19),
            datetime.date(2024, 1, 22),
            datetime.date(2024, 1, 23),
            datetime.date(2024, 1, 24),
            datetime.date(2024, 1, 25),  # Index 19
            datetime.date(2024, 2, 5),   # Index 20 (Multi-day calendar leap)
            datetime.date(2024, 2, 6),   # Index 21
            datetime.date(2024, 2, 7),   # Index 22
            datetime.date(2024, 2, 8),   # Index 23
            datetime.date(2024, 2, 9),   # Index 24
        ]
        self.assertEqual(len(dates), 25)

        # Build CSV with distinct identifiable closes
        csv_lines = ["Date,Close"]
        for idx, d in enumerate(dates):
            # Closes: 21000 + idx * 10
            csv_lines.append(f"{d.strftime('%d-%b-%Y')},{21000 + idx * 10}.00")

        csv_file = self._write_file("nifty_clock_test.csv", "\n".join(csv_lines) + "\n")
        bytes_before = csv_file.read_bytes()
        hash_before = hashlib.sha256(bytes_before).hexdigest()

        series = load_series("nifty50_price_index", csv_file)
        result = compute_twenty_session_outcomes(series)

        # Ensure disk bytes are intact
        self.assertEqual(csv_file.read_bytes(), bytes_before)
        self.assertEqual(hashlib.sha256(csv_file.read_bytes()).hexdigest(), hash_before)

        # Invariant checks
        self.assertEqual(result.total_origins, 25)
        self.assertEqual(result.mature_count, 5)
        self.assertEqual(result.unknown_count, 20)

        # Origin 0 MUST pair with index 20, NOT 19 or 21
        o0 = result[0]
        self.assertEqual(o0.origin_index, 0)
        self.assertEqual(o0.origin_date, dates[0])
        self.assertEqual(o0.origin_close, Decimal("21000.00"))
        self.assertTrue(o0.is_mature)
        self.assertEqual(o0.status, STATUS_MATURE)
        self.assertEqual(o0.maturity_index, 20)
        self.assertNotEqual(o0.maturity_index, 19)
        self.assertNotEqual(o0.maturity_index, 21)
        self.assertEqual(o0.maturity_date, dates[20])
        self.assertEqual(o0.maturity_close, Decimal("21200.00"))

        # Origins 1 to 4 pair with indices 21 to 24
        for i in range(5):
            rec = result[i]
            self.assertEqual(rec.origin_index, i)
            self.assertEqual(rec.origin_date, dates[i])
            self.assertEqual(rec.origin_close, Decimal(f"{21000 + i * 10}.00"))
            self.assertTrue(rec.is_mature)
            self.assertEqual(rec.status, STATUS_MATURE)
            self.assertEqual(rec.maturity_index, i + 20)
            self.assertEqual(rec.maturity_date, dates[i + 20])
            self.assertEqual(rec.maturity_close, Decimal(f"{21000 + (i + 20) * 10}.00"))

        # Origins 5 to 24 are unmatured
        for i in range(5, 25):
            rec = result[i]
            self.assertEqual(rec.origin_index, i)
            self.assertEqual(rec.origin_date, dates[i])
            self.assertEqual(rec.origin_close, Decimal(f"{21000 + i * 10}.00"))
            self.assertFalse(rec.is_mature)
            self.assertEqual(rec.status, STATUS_UNKNOWN)
            self.assertIsNone(rec.maturity_index)
            self.assertIsNone(rec.maturity_date)
            self.assertIsNone(rec.maturity_close)
            self.assertIsNone(rec.outcome_class)

    def test_02_synthetic_axis_counterexample_and_vix_independence(self) -> None:
        """
        Counterexample test:
        - Origin 0 has Close=100.0.
        - Index 20 has Close=99.4 (which is < 99.5, classified as BEAR).
        - Index 21 has Close=101.0 (which would be BULL if an off-by-one used 21).
        - India VIX series has a missing observation at intermediate index 10.
        - Verifies:
          1. Missing VIX at intermediate index 10 does not change origin 0 BEAR or maturity index 20.
          2. Outcomes depend strictly on the unchanged Nifty series; VIX is neither required nor consumed.
        """
        start_d = datetime.date(2024, 1, 1)
        dates = [start_d + datetime.timedelta(days=i) for i in range(25)]

        # Construct Nifty CSV
        nifty_lines = ["Date,Close"]
        for idx, d in enumerate(dates):
            if idx == 0:
                c = "100.00"
            elif idx == 20:
                c = "99.40"   # BEAR boundary move: (99.4/100) - 1 = -0.6% < -0.5%
            elif idx == 21:
                c = "101.00"  # Opposite regime: BULL move
            else:
                c = "100.00"
            nifty_lines.append(f"{d.strftime('%d-%b-%Y')},{c}")

        nifty_file = self._write_file("nifty_counterexample.csv", "\n".join(nifty_lines) + "\n")
        nifty_series = load_series("nifty50_price_index", nifty_file)

        # Construct VIX CSV missing observation at index 10
        vix_lines = ["Date,Close"]
        for idx, d in enumerate(dates):
            if idx == 10:
                continue  # Missing intermediate VIX
            vix_lines.append(f"{d.strftime('%d-%b-%Y')},14.00")

        vix_file = self._write_file("vix_missing_10.csv", "\n".join(vix_lines) + "\n")
        vix_series = load_series("india_vix", vix_file)

        # Verify alignment exposes the missing VIX at index 10
        pair = align_pair(nifty_series, vix_series)
        self.assertIsNone(pair.aligned_observations[10].vix_close)
        self.assertEqual(pair.nifty_only_dates, (dates[10],))

        # Compute outcomes directly from nifty_series
        result = compute_twenty_session_outcomes(nifty_series)

        # Verify origin 0 outcome
        o0 = result[0]
        self.assertEqual(o0.origin_index, 0)
        self.assertEqual(o0.origin_close, Decimal("100.00"))
        self.assertEqual(o0.maturity_index, 20)
        self.assertEqual(o0.maturity_date, dates[20])
        self.assertEqual(o0.maturity_close, Decimal("99.40"))
        self.assertEqual(o0.outcome_class, OUTCOME_CLASS_BEAR)

        # Origin 1 pairs with index 21 (100.00 -> 101.00: +1.0% > +0.5% -> BULL)
        o1 = result[1]
        self.assertEqual(o1.origin_index, 1)
        self.assertEqual(o1.maturity_index, 21)
        self.assertEqual(o1.maturity_close, Decimal("101.00"))
        self.assertEqual(o1.outcome_class, OUTCOME_CLASS_BULL)

    def test_03_exact_boundaries_neutral_and_just_outside(self) -> None:
        """
        Validates classification against the exact +/-0.5% threshold:
        - Exact -0.5% boundary: 100 -> 99.5 is NEUTRAL (200 * 99.5 == 199 * 100 == 19900).
        - Exact +0.5% boundary: 100 -> 100.5 is NEUTRAL (200 * 100.5 == 201 * 100 == 20100).
        - Just below -0.5%: 100 -> 99.49999999999999999999 is BEAR.
        - Just inside -0.5%: 100 -> 99.50000000000000000001 is NEUTRAL.
        - Just inside +0.5%: 100 -> 100.49999999999999999999 is NEUTRAL.
        - Just above +0.5%: 100 -> 100.50000000000000000001 is BULL.
        - Flat move: 100 -> 100 is NEUTRAL.
        - Ordinary moves: 100 -> 105 is BULL, 100 -> 95 is BEAR.
        """
        c0 = Decimal("100")

        test_cases = [
            # (maturity_close, expected_class, description)
            (Decimal("99.5"), OUTCOME_CLASS_NEUTRAL, "Exact lower boundary (-0.5%)"),
            (Decimal("100.5"), OUTCOME_CLASS_NEUTRAL, "Exact upper boundary (+0.5%)"),
            (Decimal("99.49999999999999999999"), OUTCOME_CLASS_BEAR, "Just below lower boundary"),
            (Decimal("99.50000000000000000001"), OUTCOME_CLASS_NEUTRAL, "Just inside lower boundary"),
            (Decimal("100.49999999999999999999"), OUTCOME_CLASS_NEUTRAL, "Just inside upper boundary"),
            (Decimal("100.50000000000000000001"), OUTCOME_CLASS_BULL, "Just above upper boundary"),
            (Decimal("100.0"), OUTCOME_CLASS_NEUTRAL, "Zero percentage return"),
            (Decimal("105.0"), OUTCOME_CLASS_BULL, "Strong bullish move (+5%)"),
            (Decimal("95.0"), OUTCOME_CLASS_BEAR, "Strong bearish move (-5%)"),
            (Decimal("100.51"), OUTCOME_CLASS_BULL, "Slightly above threshold (+0.51%)"),
            (Decimal("99.49"), OUTCOME_CLASS_BEAR, "Slightly below threshold (-0.51%)"),
        ]

        for maturity_close, expected_class, desc in test_cases:
            with self.subTest(maturity=str(maturity_close), case=desc):
                actual = classify_twenty_session_move(c0, maturity_close)
                self.assertEqual(actual, expected_class, f"Failed for {desc}: got {actual}")

    def test_04_non_100_origin_and_long_precision(self) -> None:
        """
        Validates classification on realistic non-100 origins with long precision:
        - Origin close: Decimal('21741.90').
          Exact upper boundary: 21741.90 * 201 / 200 = 21850.6095 -> NEUTRAL.
          Exact lower boundary: 21741.90 * 199 / 200 = 21633.1905 -> NEUTRAL.
          Just above upper: 21850.609500000000000000000001 -> BULL.
          Just below lower: 21633.190499999999999999999999 -> BEAR.
        - High-precision origin with 25 decimal places preserves exactness.
        """
        c0 = Decimal("21741.90")

        # Independent algebraic calculations:
        # C20_upper = 21741.90 * 201 / 200 = 21850.6095
        # C20_lower = 21741.90 * 199 / 200 = 21633.1905
        exact_upper = Decimal("21850.6095")
        exact_lower = Decimal("21633.1905")

        self.assertEqual(classify_twenty_session_move(c0, exact_upper), OUTCOME_CLASS_NEUTRAL)
        self.assertEqual(classify_twenty_session_move(c0, exact_lower), OUTCOME_CLASS_NEUTRAL)

        just_above_upper = Decimal("21850.609500000000000000000001")
        just_below_lower = Decimal("21633.190499999999999999999999")
        just_inside_upper = Decimal("21850.609499999999999999999999")
        just_inside_lower = Decimal("21633.190500000000000000000001")

        self.assertEqual(classify_twenty_session_move(c0, just_above_upper), OUTCOME_CLASS_BULL)
        self.assertEqual(classify_twenty_session_move(c0, just_below_lower), OUTCOME_CLASS_BEAR)
        self.assertEqual(classify_twenty_session_move(c0, just_inside_upper), OUTCOME_CLASS_NEUTRAL)
        self.assertEqual(classify_twenty_session_move(c0, just_inside_lower), OUTCOME_CLASS_NEUTRAL)

        # High-precision origin: 25 decimal digits
        c0_long = Decimal("12345.1234567890123456789012345")
        # Independent exact calculation of terminating decimal representations (denominator 200 adds 3 digits)
        with decimal.localcontext(decimal.Context(prec=60)):
            exact_upper_long = c0_long * Decimal("201") / Decimal("200")
            exact_lower_long = c0_long * Decimal("199") / Decimal("200")
            delta = Decimal("1e-35")
            above_long = exact_upper_long + delta
            below_long = exact_lower_long - delta
            inside_upper_long = exact_upper_long - delta
            inside_lower_long = exact_lower_long + delta

        self.assertEqual(classify_twenty_session_move(c0_long, exact_upper_long), OUTCOME_CLASS_NEUTRAL)
        self.assertEqual(classify_twenty_session_move(c0_long, exact_lower_long), OUTCOME_CLASS_NEUTRAL)
        self.assertEqual(classify_twenty_session_move(c0_long, inside_upper_long), OUTCOME_CLASS_NEUTRAL)
        self.assertEqual(classify_twenty_session_move(c0_long, inside_lower_long), OUTCOME_CLASS_NEUTRAL)

        self.assertEqual(classify_twenty_session_move(c0_long, above_long), OUTCOME_CLASS_BULL)
        self.assertEqual(classify_twenty_session_move(c0_long, below_long), OUTCOME_CLASS_BEAR)

    def test_05_deliberately_low_decimal_precision_and_traps(self) -> None:
        """
        Validates robustness against ambient Decimal context:
        - When decimal.localcontext() has prec=1 and strict traps (Inexact, Rounded, FloatOperation, Subnormal) enabled,
          class decisions remain mathematically exact and raise NO arithmetic exceptions.
        - Verifies that exact rational conversion isolates classification from context traps.
        """
        c0 = Decimal("100.00")
        c20_neutral_upper = Decimal("100.50")
        c20_neutral_lower = Decimal("99.50")
        c20_bull = Decimal("101.00")
        c20_bear = Decimal("99.00")

        # Create a 21-observation series to test full function execution under low precision
        start_d = datetime.date(2024, 1, 1)
        csv_lines = ["Date,Close"]
        for i in range(21):
            d = start_d + datetime.timedelta(days=i)
            # Origin 0 is 100.00, maturity at index 20 is 100.50 (exact boundary -> NEUTRAL)
            c = "100.00" if i == 0 else ("100.50" if i == 20 else "100.20")
            csv_lines.append(f"{d.strftime('%d-%b-%Y')},{c}")

        csv_file = self._write_file("low_prec_series.csv", "\n".join(csv_lines) + "\n")
        series = load_series("nifty50_price_index", csv_file)

        with decimal.localcontext() as ctx:
            ctx.prec = 1
            ctx.traps[decimal.Inexact] = True
            ctx.traps[decimal.Rounded] = True
            ctx.traps[decimal.FloatOperation] = True
            ctx.traps[decimal.Subnormal] = True

            # In this context, any Decimal operation like Decimal("100.50") * 200 or / would raise Inexact/Rounded
            # Our rational implementation MUST succeed without error
            self.assertEqual(classify_twenty_session_move(c0, c20_neutral_upper), OUTCOME_CLASS_NEUTRAL)
            self.assertEqual(classify_twenty_session_move(c0, c20_neutral_lower), OUTCOME_CLASS_NEUTRAL)
            self.assertEqual(classify_twenty_session_move(c0, c20_bull), OUTCOME_CLASS_BULL)
            self.assertEqual(classify_twenty_session_move(c0, c20_bear), OUTCOME_CLASS_BEAR)

            # Full function execution under harsh context
            result = compute_twenty_session_outcomes(series)
            self.assertEqual(result.mature_count, 1)
            self.assertEqual(result.unknown_count, 20)
            self.assertEqual(result[0].outcome_class, OUTCOME_CLASS_NEUTRAL)

    def test_06_sequence_lengths_and_explicit_unknown_tail(self) -> None:
        """
        Validates sequence length boundaries:
        - Sequence length <= 20: 0 mature outcomes, all origins unknown.
        - Sequence length == 21: exactly 1 mature outcome (origin 0), exactly 20 unknown outcomes.
        - Sequence length == 25: exactly 5 mature outcomes (origins 0..4), exactly 20 unknown outcomes.
        - Sequence length == 42: exactly 22 mature outcomes (origins 0..21), exactly 20 unknown outcomes.
        - Every origin observation is preserved.
        """
        start_d = datetime.date(2024, 1, 1)

        def _make_series(n: int, name: str):
            lines = ["Date,Close"]
            for i in range(n):
                d = start_d + datetime.timedelta(days=i)
                lines.append(f"{d.strftime('%d-%b-%Y')},{20000 + i}.00")
            f = self._write_file(f"{name}.csv", "\n".join(lines) + "\n")
            return load_series("nifty50_price_index", f)

        # 1. Short sequence length 1
        s1 = _make_series(1, "len_1")
        r1 = compute_twenty_session_outcomes(s1)
        self.assertEqual(r1.total_origins, 1)
        self.assertEqual(r1.mature_count, 0)
        self.assertEqual(r1.unknown_count, 1)
        self.assertFalse(r1[0].is_mature)
        self.assertEqual(r1[0].status, STATUS_UNKNOWN)
        self.assertIsNone(r1[0].maturity_index)

        # 2. Sequence length 5
        s5 = _make_series(5, "len_5")
        r5 = compute_twenty_session_outcomes(s5)
        self.assertEqual(r5.total_origins, 5)
        self.assertEqual(r5.mature_count, 0)
        self.assertEqual(r5.unknown_count, 5)
        for o in r5:
            self.assertFalse(o.is_mature)
            self.assertEqual(o.status, STATUS_UNKNOWN)
            self.assertIsNone(o.maturity_index)

        # 3. Exactly 20 observations
        s20 = _make_series(20, "len_20")
        r20 = compute_twenty_session_outcomes(s20)
        self.assertEqual(r20.total_origins, 20)
        self.assertEqual(r20.mature_count, 0)
        self.assertEqual(r20.unknown_count, 20)
        for o in r20:
            self.assertFalse(o.is_mature)
            self.assertEqual(o.status, STATUS_UNKNOWN)

        # 4. Exactly 21 observations: exactly 1 mature, 20 unknown
        s21 = _make_series(21, "len_21")
        r21 = compute_twenty_session_outcomes(s21)
        self.assertEqual(r21.total_origins, 21)
        self.assertEqual(r21.mature_count, 1)
        self.assertEqual(r21.unknown_count, 20)
        # Origin 0 is mature at index 20
        self.assertTrue(r21[0].is_mature)
        self.assertEqual(r21[0].status, STATUS_MATURE)
        self.assertEqual(r21[0].maturity_index, 20)
        # Origins 1 through 20 are unknown
        for i in range(1, 21):
            self.assertFalse(r21[i].is_mature)
            self.assertEqual(r21[i].status, STATUS_UNKNOWN)
            self.assertIsNone(r21[i].maturity_index)

        # 5. Length 25: exactly 5 mature, 20 unknown
        s25 = _make_series(25, "len_25")
        r25 = compute_twenty_session_outcomes(s25)
        self.assertEqual(r25.total_origins, 25)
        self.assertEqual(r25.mature_count, 5)
        self.assertEqual(r25.unknown_count, 20)
        for i in range(5):
            self.assertTrue(r25[i].is_mature)
            self.assertEqual(r25[i].maturity_index, i + 20)
        for i in range(5, 25):
            self.assertFalse(r25[i].is_mature)
            self.assertIsNone(r25[i].maturity_index)

        # 6. Length 42: exactly 22 mature (0..21), 20 unknown (22..41)
        s42 = _make_series(42, "len_42")
        r42 = compute_twenty_session_outcomes(s42)
        self.assertEqual(r42.total_origins, 42)
        self.assertEqual(r42.mature_count, 22)
        self.assertEqual(r42.unknown_count, 20)
        for i in range(22):
            self.assertTrue(r42[i].is_mature)
            self.assertEqual(r42[i].maturity_index, i + 20)
        for i in range(22, 42):
            self.assertFalse(r42[i].is_mature)
            self.assertIsNone(r42[i].maturity_index)

    def test_07_rejection_of_wrong_series_role_and_types(self) -> None:
        """
        Validates error handling:
        - Passing an India VIX series raises InputValidationError.
        - Passing a non-LoadedSeries object raises InputValidationError.
        - Nonpositive Close inputs in classify_twenty_session_move raise ValueError.
        """
        csv_f = self._write_file("vix_series.csv", "Date,Close\n01-Jan-2024,14.50\n")
        vix_series = load_series("india_vix", csv_f)

        # Reject VIX series in outcome calculator
        with self.assertRaises(InputValidationError) as ctx:
            compute_twenty_session_outcomes(vix_series)
        self.assertEqual(ctx.exception.field, "series_id")
        self.assertIn("wrong series id", str(ctx.exception.reason).lower())
        self.assertIn("nifty50_price_index", str(ctx.exception).lower())

        # Reject wrong types
        with self.assertRaises(InputValidationError) as ctx_type:
            compute_twenty_session_outcomes("not_a_series")  # type: ignore
        self.assertIn("loadedseries", str(ctx_type.exception).lower())

        with self.assertRaises(InputValidationError) as ctx_list:
            compute_twenty_session_outcomes([1, 2, 3])  # type: ignore
        self.assertIn("loadedseries", str(ctx_list.exception).lower())

        # classify_twenty_session_move nonpositive checks
        with self.assertRaises(ValueError):
            classify_twenty_session_move(Decimal("0"), Decimal("100"))
        with self.assertRaises(ValueError):
            classify_twenty_session_move(Decimal("-10"), Decimal("100"))
        with self.assertRaises(ValueError):
            classify_twenty_session_move(Decimal("100"), Decimal("0"))
        with self.assertRaises(ValueError):
            classify_twenty_session_move(Decimal("100"), Decimal("-5"))

    def test_08_immutability_and_source_preservation(self) -> None:
        """
        Validates immutability, frozen records, and source preservation:
        - TwentySessionOutcome instances are frozen dataclasses and reject mutation.
        - Input LoadedSeries records, provenance, and warnings are unmodified.
        - OutcomeSeries supports __len__, __iter__, __getitem__, and property subsets.
        """
        start_d = datetime.date(2024, 1, 1)
        csv_lines = ["Date,Close"]
        for i in range(25):
            d = start_d + datetime.timedelta(days=i)
            csv_lines.append(f"{d.strftime('%d-%b-%Y')},{21000 + i * 10}.00")

        csv_file = self._write_file("immutability_check.csv", "\n".join(csv_lines) + "\n")
        series = load_series("nifty50_price_index", csv_file)

        records_before = series.records
        provenance_before = series.provenance
        warnings_before = series.warnings

        result = compute_twenty_session_outcomes(series)

        # Source series objects are identical and untouched
        self.assertIs(series.records, records_before)
        self.assertIs(series.provenance, provenance_before)
        self.assertIs(series.warnings, warnings_before)

        # Frozen instance rejection
        o0 = result[0]
        with self.assertRaises(Exception):
            o0.origin_close = Decimal("99999.00")  # type: ignore
        with self.assertRaises(Exception):
            o0.is_mature = False  # type: ignore

        # Sequence properties
        self.assertEqual(len(result), 25)
        self.assertEqual(result.total_origins, 25)
        self.assertEqual(len(result.mature_outcomes), 5)
        self.assertEqual(len(result.unknown_outcomes), 20)
        self.assertEqual(result.mature_count, 5)
        self.assertEqual(result.unknown_count, 20)

        # Iteration works
        iterated = list(result)
        self.assertEqual(len(iterated), 25)
        self.assertEqual(iterated[0], result[0])
        self.assertEqual(iterated[-1], result[-1])

    def test_09_contradictory_record_states_rejected(self) -> None:
        """
        Validates __post_init__ consistency enforcement on TwentySessionOutcome:
        - Contradictory states (e.g. is_mature=True with status='unknown', missing maturity fields,
          or unmatured records with populated future fields) raise ValueError.
        """
        d0 = datetime.date(2024, 1, 1)
        d20 = datetime.date(2024, 1, 29)
        c0 = Decimal("100.00")
        c20 = Decimal("102.00")

        # 1. is_mature=True but status='unknown'
        with self.assertRaises(ValueError) as ctx:
            TwentySessionOutcome(
                origin_index=0,
                origin_date=d0,
                origin_close=c0,
                is_mature=True,
                status=STATUS_UNKNOWN,
                maturity_index=20,
                maturity_date=d20,
                maturity_close=c20,
                outcome_class=OUTCOME_CLASS_BULL,
            )
        self.assertIn("contradictory outcome state", str(ctx.exception).lower())

        # 2. is_mature=True but maturity_index is None
        with self.assertRaises(ValueError) as ctx:
            TwentySessionOutcome(
                origin_index=0,
                origin_date=d0,
                origin_close=c0,
                is_mature=True,
                status=STATUS_MATURE,
                maturity_index=None,
                maturity_date=d20,
                maturity_close=c20,
                outcome_class=OUTCOME_CLASS_BULL,
            )
        self.assertIn("maturity_index", str(ctx.exception).lower())

        # 3. is_mature=True but maturity_index != origin_index + 20
        with self.assertRaises(ValueError) as ctx:
            TwentySessionOutcome(
                origin_index=0,
                origin_date=d0,
                origin_close=c0,
                is_mature=True,
                status=STATUS_MATURE,
                maturity_index=19,  # Off-by-one
                maturity_date=d20,
                maturity_close=c20,
                outcome_class=OUTCOME_CLASS_BULL,
            )
        self.assertIn("invalid maturity_index", str(ctx.exception).lower())

        # 4. is_mature=True but maturity_date precedes origin_date
        with self.assertRaises(ValueError) as ctx:
            TwentySessionOutcome(
                origin_index=0,
                origin_date=d20,
                origin_close=c0,
                is_mature=True,
                status=STATUS_MATURE,
                maturity_index=20,
                maturity_date=d0,  # Prior date
                maturity_close=c20,
                outcome_class=OUTCOME_CLASS_BULL,
            )
        self.assertIn("cannot precede", str(ctx.exception).lower())

        # 5. is_mature=True but invalid outcome_class
        with self.assertRaises(ValueError) as ctx:
            TwentySessionOutcome(
                origin_index=0,
                origin_date=d0,
                origin_close=c0,
                is_mature=True,
                status=STATUS_MATURE,
                maturity_index=20,
                maturity_date=d20,
                maturity_close=c20,
                outcome_class="INVALID_CLASS",
            )
        self.assertIn("invalid outcome_class", str(ctx.exception).lower())

        # 6. is_mature=False but status='mature'
        with self.assertRaises(ValueError) as ctx:
            TwentySessionOutcome(
                origin_index=0,
                origin_date=d0,
                origin_close=c0,
                is_mature=False,
                status=STATUS_MATURE,
            )
        self.assertIn("contradictory outcome state", str(ctx.exception).lower())

        # 7. is_mature=False but populated maturity_close
        with self.assertRaises(ValueError) as ctx:
            TwentySessionOutcome(
                origin_index=0,
                origin_date=d0,
                origin_close=c0,
                is_mature=False,
                status=STATUS_UNKNOWN,
                maturity_close=c20,
            )
        self.assertIn("cannot have maturity_close", str(ctx.exception).lower())

        # 8. is_mature=False but populated outcome_class
        with self.assertRaises(ValueError) as ctx:
            TwentySessionOutcome(
                origin_index=0,
                origin_date=d0,
                origin_close=c0,
                is_mature=False,
                status=STATUS_UNKNOWN,
                outcome_class=OUTCOME_CLASS_BEAR,
            )
        self.assertIn("cannot have outcome_class", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
