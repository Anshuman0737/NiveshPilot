"""
Unit tests for Prediction Evaluation Input Foundation.

Validates:
1. Strict CSV parsing, BOM decoding, quote-handling, header normalization, and raw byte provenance.
2. Comprehensive structural and schema failure handling.
3. Invariant dd-MMM-yyyy and dd MMM yyyy parsing, calendar checks, and Decimal precision retention.
4. Global duplicate date rejection within and across files.
5. Advisory OHLC discrepancy warnings with strict Close price preservation (counterexample).
6. Exact-date cross-series alignment and sequence preservation with missing VIX at index 20 (counterexample).
7. Calendar verification states (not_checked, matches_supplied_sessions, mismatch) and sequence checks.
8. Provenance preservation and operational boundary isolation.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from typing import Union

from research.prediction_eval.inputs import (
    CalendarValidationError,
    DuplicateDateError,
    FileInputSpec,
    InputValidationError,
    InputWarning,
    align_pair,
    load_series,
)


class TestPredictionEvalInputs(unittest.TestCase):
    """Test suite for research/prediction_eval/inputs.py."""

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

    def test_01_bom_headers_quoted_comma_opposite_orders_multiple_files(self) -> None:
        """
        Validates BOM stripping, header padding/casing, quoted fields containing commas,
        opposite chronological source orders across multiple non-overlapping files,
        and preservation of raw bytes and hashes.
        """
        # File 1: UTF-8 BOM, descending order (04-Jan, 03-Jan), ancillary quoted comma field
        csv1_content = (
            "\ufeff  Date  ,  CLOSE  ,  Remarks  \n"
            "04-Jan-2024,21650.75,\"Volatile, end of week\"\n"
            "03-Jan-2024,21517.35,\"Steady, range-bound\"\n"
        ).encode("utf-8")
        file1 = self._write_file("part2_desc.csv", csv1_content)
        f1_bytes_before = file1.read_bytes()
        f1_hash_before = hashlib.sha256(f1_bytes_before).hexdigest()

        # File 2: Standard UTF-8, ascending order (01-Jan, 02-Jan)
        csv2_content = (
            "date,Close\n"
            "01-Jan-2024,21741.90\n"
            "02-Jan-2024,21665.80\n"
        )
        file2 = self._write_file("part1_asc.csv", csv2_content)
        f2_bytes_before = file2.read_bytes()
        f2_hash_before = hashlib.sha256(f2_bytes_before).hexdigest()

        series = load_series("nifty50_price_index", [file1, file2])

        # Verify disk files were strictly read-only and hashes are unmodified
        self.assertEqual(file1.read_bytes(), f1_bytes_before)
        self.assertEqual(hashlib.sha256(file1.read_bytes()).hexdigest(), f1_hash_before)
        self.assertEqual(file2.read_bytes(), f2_bytes_before)
        self.assertEqual(hashlib.sha256(file2.read_bytes()).hexdigest(), f2_hash_before)

        # Chronological sort across both files independent of input order
        expected_dates = (
            datetime.date(2024, 1, 1),
            datetime.date(2024, 1, 2),
            datetime.date(2024, 1, 3),
            datetime.date(2024, 1, 4),
        )
        self.assertEqual(series.dates, expected_dates)
        self.assertEqual(series.total_records, 4)
        self.assertEqual(series.first_date, datetime.date(2024, 1, 1))
        self.assertEqual(series.last_date, datetime.date(2024, 1, 4))

        # Precision retention check with Decimal
        expected_closes = (
            Decimal("21741.90"),
            Decimal("21665.80"),
            Decimal("21517.35"),
            Decimal("21650.75"),
        )
        actual_closes = tuple(r.close for r in series.records)
        self.assertEqual(actual_closes, expected_closes)

        # Provenance records per file
        self.assertEqual(len(series.provenance), 2)
        prov1 = series.provenance[0]
        self.assertEqual(prov1.file_path, str(file1))
        self.assertEqual(prov1.raw_byte_count, len(csv1_content))
        self.assertEqual(prov1.sha256, f1_hash_before)
        self.assertEqual(prov1.record_count, 2)
        self.assertEqual(prov1.observed_first_date, datetime.date(2024, 1, 3))
        self.assertEqual(prov1.observed_last_date, datetime.date(2024, 1, 4))

    def test_02_schema_and_structural_failures(self) -> None:
        """
        Validates rejection of all malformed CSV structures:
        missing columns, duplicate headers, blank headers, invalid UTF-8,
        unclosed quotes, short/long/blank records, empty files, and header-only files.
        Ensures no partial series is returned.
        """
        test_cases = [
            ("missing_date.csv", "Close\n100.0\n", "missing required 'date' header"),
            ("missing_close.csv", "Date\n01-Jan-2024\n", "missing required 'close' header"),
            ("dup_headers.csv", "Date,Close,close\n01-Jan-2024,100,100\n", "duplicate normalized header"),
            ("blank_header.csv", "Date,,Close\n01-Jan-2024,foo,100\n", "empty header column"),
            ("invalid_utf8.csv", b"\xff\xfe\x00\x00\x12\x34", "invalid utf-8"),
            ("unclosed_quote.csv", "Date,Close\n01-Jan-2024,\"100.5\n02-Jan-2024,101.0\n", "csv formatting error"),
            ("short_record.csv", "Date,Close,Volume\n01-Jan-2024,100.0\n", "fields; expected 3"),
            ("long_record.csv", "Date,Close\n01-Jan-2024,100.0,extra_field\n", "fields; expected 2"),
            ("blank_row_mid.csv", "Date,Close\n01-Jan-2024,100.0\n\n02-Jan-2024,101.0\n", "blank record"),
            ("empty_file.csv", b"", "empty csv file"),
            ("header_only.csv", "Date,Close\n", "header-only csv file"),
        ]

        for filename, content, err_fragment in test_cases:
            file_path = self._write_file(filename, content)
            with self.subTest(case=filename):
                with self.assertRaises(InputValidationError) as ctx:
                    load_series("nifty50_price_index", file_path)
                self.assertIn(err_fragment.lower(), str(ctx.exception).lower())

    def test_03_dates_and_close_syntax_validation(self) -> None:
        """
        Validates explicit date formatting, English month validation,
        calendar correctness, whitespace handling, and plain positive Decimal Close syntax.
        """
        # Calendar impossibilities must fail
        invalid_dates = [
            "29-Feb-2023",  # Non-leap year
            "31-Apr-2024",  # April has 30 days
            "00-Jan-2024",  # Impossible day
            "32-Jan-2024",  # Impossible day
            "2024-01-01",   # ISO format rejected
            "01/01/2024",   # Slashes rejected
            "1-Jan-2024",    # Single-digit day rejected
            "01-Mai-2024",  # Non-English month rejected
            "01-13-2024",   # Numeric month rejected
        ]
        for bad_date in invalid_dates:
            with self.subTest(date=bad_date):
                f = self._write_file(f"bad_date_{bad_date.replace('/', '_')}.csv", f"Date,Close\n{bad_date},100.0\n")
                with self.assertRaises(InputValidationError):
                    load_series("nifty50_price_index", f)

        # Valid leap year date must succeed
        f_leap = self._write_file("leap.csv", "Date,Close\n29-Feb-2024,22000.0\n")
        series_leap = load_series("nifty50_price_index", f_leap)
        self.assertEqual(series_leap.records[0].date, datetime.date(2024, 2, 29))

        # Month casing & surrounding whitespace must succeed
        f_case = self._write_file(
            "case.csv",
            "Date,Close\n"
            "  01-JAN-2024  ,  21000.50  \n"
            "02-jan-2024,21050.25\n"
            "03-DeC-2023,20500.00\n"
        )
        series_case = load_series("nifty50_price_index", f_case)
        self.assertEqual(len(series_case.records), 3)
        self.assertEqual(series_case.records[0].date, datetime.date(2023, 12, 3))
        self.assertEqual(series_case.records[0].close, Decimal("20500.00"))

        # Close syntax errors must fail
        invalid_closes = [
            "",             # Empty
            "   ",          # Whitespace only
            "0",            # Zero nonpositive
            "0.00",         # Zero decimal nonpositive
            "-15.5",        # Negative
            "1e4",          # Scientific notation
            "1.2E+3",       # Scientific notation
            "NaN",          # Non-finite
            "Inf",          # Non-finite
            "Infinity",     # Non-finite
            "100.",         # Trailing dot without fractional digits
            ".75",          # Leading dot without integer digits
        ]
        for bad_close in invalid_closes:
            with self.subTest(close=bad_close):
                f = self._write_file(f"bad_close_{len(bad_close)}.csv", f"Date,Close\n01-Jan-2024,{bad_close}\n")
                with self.assertRaises(InputValidationError):
                    load_series("nifty50_price_index", f)

        # Properly quoted grouped Close value must fail Close syntax rather than column count
        f_grouped = self._write_file(
            "bad_close_grouped.csv",
            'Date,Close\n01-Jan-2024,"21,500.00"\n'
        )
        with self.assertRaises(InputValidationError) as ctx_grp:
            load_series("nifty50_price_index", f_grouped)
        self.assertEqual(ctx_grp.exception.field, "Close")
        self.assertIn("plain decimal syntax", str(ctx_grp.exception).lower())

        # Precision retention check for long decimals (assert numeric equality, scale and digit tuple)
        f_prec = self._write_file(
            "prec.csv",
            "Date,Close\n01-Jan-2024,21741.12345678901234567890\n"
        )
        series_prec = load_series("nifty50_price_index", f_prec)
        prec_val = series_prec.records[0].close
        self.assertEqual(prec_val, Decimal("21741.12345678901234567890"))
        self.assertEqual(prec_val.as_tuple().exponent, -20)
        expected_digits = (2, 1, 7, 4, 1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 0)
        self.assertEqual(prec_val.as_tuple().digits, expected_digits)
        self.assertEqual(str(prec_val), "21741.12345678901234567890")

    def test_04_duplicate_dates_within_and_across_files(self) -> None:
        """
        Validates that duplicate dates (both identical and conflicting Close values)
        are rejected within a single file and across multiple files, reporting both source locations.
        Also validates that missing files report an understandable error.
        """
        # Identical duplicate within same file
        f_dup_same = self._write_file(
            "dup_same.csv",
            "Date,Close\n01-Jan-2024,100.0\n01-Jan-2024,100.0\n"
        )
        with self.assertRaises(DuplicateDateError) as ctx:
            load_series("nifty50_price_index", f_dup_same)
        self.assertIn("01-Jan-2024", str(ctx.exception))
        self.assertIn("line 3", str(ctx.exception))
        self.assertIn("line 2", str(ctx.exception))

        # Conflicting duplicate within same file
        f_dup_conflict = self._write_file(
            "dup_conflict.csv",
            "Date,Close\n02-Jan-2024,100.0\n02-Jan-2024,105.0\n"
        )
        with self.assertRaises(DuplicateDateError) as ctx:
            load_series("nifty50_price_index", f_dup_conflict)
        self.assertIn("02-Jan-2024", str(ctx.exception))

        # Duplicate across two files (conflicting Closes), tested in both file orders
        f_a = self._write_file("file_a.csv", "Date,Close\n05-Jan-2024,100.0\n")
        f_b = self._write_file("file_b.csv", "Date,Close\n05-Jan-2024,102.0\n")
        with self.assertRaises(DuplicateDateError) as ctx_ab:
            load_series("nifty50_price_index", [f_a, f_b])
        err_msg_ab = str(ctx_ab.exception)
        self.assertIn("05-Jan-2024", err_msg_ab)
        self.assertIn(str(f_a), err_msg_ab)
        self.assertIn(str(f_b), err_msg_ab)
        self.assertIn("line 2", err_msg_ab)

        with self.assertRaises(DuplicateDateError) as ctx_ba:
            load_series("nifty50_price_index", [f_b, f_a])
        err_msg_ba = str(ctx_ba.exception)
        self.assertIn("05-Jan-2024", err_msg_ba)
        self.assertIn(str(f_a), err_msg_ba)
        self.assertIn(str(f_b), err_msg_ba)
        self.assertIn("line 2", err_msg_ba)

        # Duplicate across two files (identical Closes), tested in both file orders
        f_c = self._write_file("file_c.csv", "Date,Close\n06-Jan-2024,100.0\n")
        f_d = self._write_file("file_d.csv", "Date,Close\n06-Jan-2024,100.0\n")
        with self.assertRaises(DuplicateDateError) as ctx_cd:
            load_series("nifty50_price_index", [f_c, f_d])
        err_msg_cd = str(ctx_cd.exception)
        self.assertIn("06-Jan-2024", err_msg_cd)
        self.assertIn(str(f_c), err_msg_cd)
        self.assertIn(str(f_d), err_msg_cd)
        self.assertIn("line 2", err_msg_cd)

        with self.assertRaises(DuplicateDateError) as ctx_dc:
            load_series("nifty50_price_index", [f_d, f_c])
        err_msg_dc = str(ctx_dc.exception)
        self.assertIn("06-Jan-2024", err_msg_dc)
        self.assertIn(str(f_c), err_msg_dc)
        self.assertIn(str(f_d), err_msg_dc)
        self.assertIn("line 2", err_msg_dc)

        # Missing file error
        with self.assertRaises(InputValidationError) as ctx:
            load_series("nifty50_price_index", self.test_dir / "non_existent.csv")
        self.assertIn("cannot access file", str(ctx.exception).lower())

    def test_05_disproving_ohlc_advisory_warnings_and_close_integrity(self) -> None:
        """
        Counterexample test:
        1. Low=20 and Close=19 discrepancy produces an advisory warning but leaves Close strictly 19.
        2. Malformed/missing OHLC values generate advisory warnings without failing load.
        3. Low > High discrepancy produces an advisory warning.
        4. Valid Close-only input produces zero warnings.
        5. Ordinary valid OHLC row produces zero warnings.
        """
        # Disproving case: Low=20, Close=19
        ohlc_csv = self._write_file(
            "ohlc_discrepancy.csv",
            "Date,Open,High,Low,Close\n"
            "01-Jan-2024,20.5,21.0,20.0,19.0\n"
        )
        series = load_series("nifty50_price_index", ohlc_csv)
        self.assertEqual(len(series.records), 1)
        # Critical verification: Close is NOT clamped or modified; date is intact
        self.assertEqual(series.records[0].close, Decimal("19.0"))
        self.assertEqual(series.records[0].date, datetime.date(2024, 1, 1))

        # Advisory warning recorded
        self.assertEqual(len(series.warnings), 1)
        w = series.warnings[0]
        self.assertEqual(w.field, "Close/Low")
        self.assertIn("below Low", w.message)

        # Malformed/missing OHLC values produce warnings but load successfully
        ohlc_malformed = self._write_file(
            "ohlc_malformed.csv",
            "Date,Open,High,Low,Close\n"
            "02-Jan-2024,malformed,25.0,,22.0\n"
        )
        series_m = load_series("nifty50_price_index", ohlc_malformed)
        self.assertEqual(series_m.records[0].close, Decimal("22.0"))
        self.assertEqual(len(series_m.warnings), 2)  # Open malformed, Low missing

        # Low > High produces warning
        ohlc_inverted = self._write_file(
            "ohlc_inverted.csv",
            "Date,Open,High,Low,Close\n"
            "03-Jan-2024,22.0,20.0,25.0,21.0\n"
        )
        series_inv = load_series("nifty50_price_index", ohlc_inverted)
        self.assertEqual(series_inv.records[0].close, Decimal("21.0"))
        warning_fields = {w.field for w in series_inv.warnings}
        self.assertIn("Low/High", warning_fields)

        # Close-only CSV: exactly 0 warnings
        close_only = self._write_file("close_only.csv", "Date,Close\n01-Jan-2024,100.0\n")
        series_co = load_series("nifty50_price_index", close_only)
        self.assertEqual(len(series_co.warnings), 0)

        # Ordinary valid OHLC row: exactly 0 warnings
        valid_ohlc = self._write_file(
            "valid_ohlc.csv",
            "Date,Open,High,Low,Close\n"
            "01-Jan-2024,100.0,105.0,98.0,102.0\n"
        )
        series_vo = load_series("nifty50_price_index", valid_ohlc)
        self.assertEqual(len(series_vo.warnings), 0)

    def test_06_disproving_opposite_orders_and_missing_vix_index_20(self) -> None:
        """
        Counterexample test:
        Demonstrates exact-date pairing with opposite chronological orders.
        In a 25-session sequence (indices 0 to 24), missing VIX observation at date
        corresponding to index 20 leaves Nifty date and Close completely intact at index 20,
        with vix_close=None, and does not drop or shift sessions.
        VIX-only dates are reported separately and never added to the aligned axis.
        """
        start_date = datetime.date(2024, 1, 1)
        nifty_dates = [start_date + datetime.timedelta(days=i) for i in range(25)]

        # Nifty file in chronological order
        nifty_rows = ["Date,Close"]
        for idx, d in enumerate(nifty_dates):
            nifty_rows.append(f"{d.strftime('%d-%b-%Y')},{21000 + idx * 10}")
        f_nifty = self._write_file("nifty_25.csv", "\n".join(nifty_rows) + "\n")
        nifty_series = load_series("nifty50_price_index", f_nifty)
        self.assertEqual(nifty_series.total_records, 25)

        # VIX file:
        # 1. Reverse chronological order
        # 2. Omits date corresponding to Nifty index 20 (nifty_dates[20])
        # 3. Contains an extra VIX date not in Nifty
        vix_extra_date = datetime.date(2024, 2, 15)
        vix_dates = [d for idx, d in enumerate(nifty_dates) if idx != 20] + [vix_extra_date]
        vix_dates.sort(reverse=True)

        vix_rows = ["Date,Close"]
        for d in vix_dates:
            vix_rows.append(f"{d.strftime('%d-%b-%Y')},14.50")
        f_vix = self._write_file("vix_rev.csv", "\n".join(vix_rows) + "\n")
        vix_series = load_series("india_vix", f_vix)

        pair = align_pair(nifty_series, vix_series)

        # The master aligned axis must have length 25 (exactly matching Nifty)
        self.assertEqual(len(pair.aligned_observations), 25)

        # Every index before and after 20 has valid VIX close
        for i in range(25):
            obs = pair.aligned_observations[i]
            self.assertEqual(obs.date, nifty_dates[i])
            self.assertEqual(obs.nifty_close, Decimal(str(21000 + i * 10)))
            if i == 20:
                # Crucial counterexample check: index 20 has exact Nifty values and vix_close is None
                self.assertIsNone(obs.vix_close)
            else:
                self.assertEqual(obs.vix_close, Decimal("14.50"))

        # Asymmetric dates reported separately
        missing_vix_date = nifty_dates[20]
        self.assertEqual(pair.nifty_only_dates, (missing_vix_date,))
        self.assertEqual(pair.vix_only_dates, (vix_extra_date,))

        # Extra VIX date must NEVER be in aligned observations
        aligned_dates = {obs.date for obs in pair.aligned_observations}
        self.assertNotIn(vix_extra_date, aligned_dates)

    def test_07_calendar_status_and_expected_sessions_validation(self) -> None:
        """
        Validates calendar status behaviors:
        1. No calendar -> 'not_checked'.
        2. Equal calendar including synthetic weekend session -> 'matches_supplied_sessions'.
        3. Missing or extra dates -> 'mismatch' with exact disjoint date tuples.
        4. Invalid expected_sessions sequences -> CalendarValidationError.
        """
        f_nifty = self._write_file(
            "nifty_cal.csv",
            "Date,Close\n"
            "05-Jan-2024,21500.0\n"
            "06-Jan-2024,21550.0\n"  # Saturday (synthetic weekend session)
            "08-Jan-2024,21600.0\n"
        )
        f_vix = self._write_file(
            "vix_cal.csv",
            "Date,Close\n"
            "05-Jan-2024,14.0\n"
            "06-Jan-2024,14.2\n"
            "08-Jan-2024,14.1\n"
        )
        nifty = load_series("nifty50_price_index", f_nifty)
        vix = load_series("india_vix", f_vix)

        # 1. No expected calendar supplied
        pair_uncheked = align_pair(nifty, vix)
        self.assertEqual(pair_uncheked.calendar_status, "not_checked")
        self.assertEqual(pair_uncheked.missing_sessions, ())
        self.assertEqual(pair_uncheked.extra_sessions, ())

        # 2. Equal expected calendar (weekend session 06-Jan-2024 retained and verified)
        expected_match = [
            datetime.date(2024, 1, 5),
            datetime.date(2024, 1, 6),
            datetime.date(2024, 1, 8),
        ]
        pair_match = align_pair(nifty, vix, expected_sessions=expected_match)
        self.assertEqual(pair_match.calendar_status, "matches_supplied_sessions")
        self.assertEqual(pair_match.missing_sessions, ())
        self.assertEqual(pair_match.extra_sessions, ())

        # 3. Mismatch: expected has missing and extra sessions
        expected_mismatch = [
            datetime.date(2024, 1, 4),  # Missing from Nifty
            datetime.date(2024, 1, 5),
            # 06-Jan-2024 is in Nifty but missing from expected
            datetime.date(2024, 1, 8),
            datetime.date(2024, 1, 9),  # Missing from Nifty
        ]
        pair_mis = align_pair(nifty, vix, expected_sessions=expected_mismatch)
        self.assertEqual(pair_mis.calendar_status, "mismatch")
        self.assertEqual(
            pair_mis.missing_sessions,
            (datetime.date(2024, 1, 4), datetime.date(2024, 1, 9)),
        )
        self.assertEqual(
            pair_mis.extra_sessions,
            (datetime.date(2024, 1, 6),),
        )

        # 4. Invalid expected calendar sequences
        invalid_calendar_cases = [
            # Duplicate dates
            [datetime.date(2024, 1, 5), datetime.date(2024, 1, 5)],
            # Unordered dates
            [datetime.date(2024, 1, 8), datetime.date(2024, 1, 5)],
            # Non-date string
            ["05-Jan-2024", "08-Jan-2024"],
            # Datetime with time component
            [datetime.datetime(2024, 1, 5, 9, 15)],
            # Not a sequence
            "invalid_type",
        ]
        for bad_cal in invalid_calendar_cases:
            with self.subTest(calendar=bad_cal):
                with self.assertRaises(CalendarValidationError):
                    align_pair(nifty, vix, expected_sessions=bad_cal)  # type: ignore

    def test_08_provenance_and_boundaries(self) -> None:
        """
        Validates:
        1. Unknown declared metadata remains None.
        2. Caller-declared metadata survives alongside observed properties.
        3. Requested interval mismatch is visible without data modification.
        4. Invalid requested intervals (start > end) are rejected.
        5. Unsupported series IDs and incorrect pair roles are rejected.
        """
        f = self._write_file("prov.csv", "Date,Close\n10-Jan-2024,21600.0\n11-Jan-2024,21650.0\n")

        # 1. Spec with defaults (unknowns remain None)
        s_default = load_series("nifty50_price_index", f)
        prov_d = s_default.provenance[0]
        self.assertIsNone(prov_d.source_url)
        self.assertIsNone(prov_d.requested_interval)
        self.assertIsNone(prov_d.acquisition_time)
        self.assertIsNone(prov_d.source_use_note)
        self.assertIsNone(prov_d.requested_interval_matches)

        # 2. Spec with caller-declared metadata
        acq_time = datetime.datetime(2024, 1, 12, 18, 30, tzinfo=datetime.timezone.utc)
        req_interval = (datetime.date(2024, 1, 1), datetime.date(2024, 1, 31))
        spec = FileInputSpec(
            file_path=f,
            source_url="https://example.com/nifty.csv",
            requested_interval=req_interval,
            acquisition_time=acq_time,
            source_use_note="Official exchange archive slice",
        )
        s_declared = load_series("nifty50_price_index", spec)
        prov_decl = s_declared.provenance[0]
        self.assertEqual(prov_decl.source_url, "https://example.com/nifty.csv")
        self.assertEqual(prov_decl.requested_interval, req_interval)
        self.assertEqual(prov_decl.acquisition_time, acq_time)
        self.assertEqual(prov_decl.source_use_note, "Official exchange archive slice")

        # 3. Observed range differs from requested range (visible, not truncated or filled)
        self.assertEqual(prov_decl.observed_first_date, datetime.date(2024, 1, 10))
        self.assertEqual(prov_decl.observed_last_date, datetime.date(2024, 1, 11))
        self.assertFalse(prov_decl.requested_interval_matches)
        self.assertEqual(s_declared.total_records, 2)

        # 4. Invalid requested interval (start > end)
        bad_spec = FileInputSpec(
            file_path=f,
            requested_interval=(datetime.date(2024, 1, 31), datetime.date(2024, 1, 1)),
        )
        with self.assertRaises(InputValidationError):
            load_series("nifty50_price_index", bad_spec)

        # 5. Unsupported series IDs
        with self.assertRaises(InputValidationError) as ctx:
            load_series("nifty50_tri", f)
        self.assertIn("unsupported series_id", str(ctx.exception).lower())

        with self.assertRaises(InputValidationError) as ctx:
            load_series("us_vix", f)
        self.assertIn("unsupported series_id", str(ctx.exception).lower())

        # Role mismatch in align_pair
        vix_series = load_series("india_vix", f)
        with self.assertRaises(InputValidationError) as ctx:
            align_pair(vix_series, vix_series)  # VIX in Nifty role
        self.assertIn("nifty role", str(ctx.exception).lower())

        with self.assertRaises(InputValidationError) as ctx:
            align_pair(s_default, s_default)  # Nifty in VIX role
        self.assertIn("vix role", str(ctx.exception).lower())

    def test_09_explicit_newline_formats_and_multiline_diagnostics(self) -> None:
        """
        Validates explicit newline handling (LF, CRLF, and CR-only) and multiline
        ancillary field physical line diagnostics.

        1. Explicit-byte LF, CRLF, and CR versions must produce identical dates,
           Decimal Closes, and preserve raw file bytes and SHA-256 hashes without modification.
        2. A quoted multiline ancillary field spanning multiple lines followed by an invalid
           required value must report the hand-counted physical line number accurately.
        3. A record where an invalid required value spans across lines reports the correct line span.
        """
        expected_dates = (
            datetime.date(2024, 1, 1),
            datetime.date(2024, 1, 2),
        )
        expected_closes = (
            Decimal("100.00"),
            Decimal("101.00"),
        )

        newline_fixtures = [
            ("lf.csv", b"Date,Close\n01-Jan-2024,100.00\n02-Jan-2024,101.00\n"),
            ("crlf.csv", b"Date,Close\r\n01-Jan-2024,100.00\r\n02-Jan-2024,101.00\r\n"),
            ("cr.csv", b"Date,Close\r01-Jan-2024,100.00\r02-Jan-2024,101.00\r"),
        ]

        for fname, raw_bytes in newline_fixtures:
            with self.subTest(newline_format=fname):
                f_path = self._write_file(fname, raw_bytes)
                hash_before = hashlib.sha256(raw_bytes).hexdigest()

                series = load_series("nifty50_price_index", f_path)

                # Disk bytes and SHA-256 hash must be strictly preserved
                self.assertEqual(f_path.read_bytes(), raw_bytes)
                self.assertEqual(hashlib.sha256(f_path.read_bytes()).hexdigest(), hash_before)

                # Parsed dates and Closes must be identical across all newline conventions
                self.assertEqual(series.dates, expected_dates)
                actual_closes = tuple(r.close for r in series.records)
                self.assertEqual(actual_closes, expected_closes)
                self.assertEqual(series.total_records, 2)
                self.assertEqual(series.provenance[0].raw_byte_count, len(raw_bytes))
                self.assertEqual(series.provenance[0].sha256, hash_before)

        # Multiline ancillary field followed by invalid required value at physical line 5
        # Line 1: Date,Close,Notes
        # Line 2: 01-Jan-2024,100.00,"Line 2 note
        # Line 3: Line 3 note
        # Line 4: Line 4 note end"
        # Line 5: 02-Jan-2024,INVALID_CLOSE,"Single line note"
        multiline_ancillary_bytes = (
            b"Date,Close,Notes\n"
            b"01-Jan-2024,100.00,\"Line 2 note\n"
            b"Line 3 note\n"
            b"Line 4 note end\"\n"
            b"02-Jan-2024,INVALID_CLOSE,\"Single line note\"\n"
        )
        f_multi = self._write_file("multiline_ancillary_diag.csv", multiline_ancillary_bytes)
        with self.assertRaises(InputValidationError) as ctx_multi:
            load_series("nifty50_price_index", f_multi)
        self.assertEqual(ctx_multi.exception.line, "line 5")
        self.assertEqual(ctx_multi.exception.field, "Close")
        self.assertIn("plain decimal syntax", str(ctx_multi.exception).lower())

        # Multiline record where the invalid field itself spans lines 4 to 5
        # Line 1: Date,Close,Notes
        # Line 2: 01-Jan-2024,100.00,"Valid multiline note
        # Line 3: continues here"
        # Line 4: 02-Jan-2024,\"invalid_close\n
        # Line 5: across two lines\",note
        multiline_span_bytes = (
            b"Date,Close,Notes\n"
            b"01-Jan-2024,100.00,\"Valid multiline note\n"
            b"continues here\"\n"
            b"02-Jan-2024,\"invalid_close\n"
            b"across two lines\",note\n"
        )
        f_span = self._write_file("multiline_span_diag.csv", multiline_span_bytes)
        with self.assertRaises(InputValidationError) as ctx_span:
            load_series("nifty50_price_index", f_span)
        self.assertEqual(ctx_span.exception.line, "lines 4-5")
        self.assertEqual(ctx_span.exception.field, "Close")


    def test_10_parser_error_physical_locations(self) -> None:
        """Strict parser failures retain hand-counted spans and native reasons."""
        newline_cases = [("lf", b"\n"), ("crlf", b"\r\n"), ("cr", b"\r")]
        parser_cases = [
            (
                "multiline_closing_quote",
                [b"Date,Close,Notes", b'01-Jan-2024,100,"part', b'end"x'],
                "lines 2-3",
                "',' expected after '\"'",
            ),
            (
                "unterminated_quote",
                [b"Date,Close,Notes", b'01-Jan-2024,100,"part', b"still open"],
                "lines 2-3",
                "unexpected end of data",
            ),
            (
                "single_line_closing_quote",
                [b"Date,Close,Notes", b'01-Jan-2024,100,"note"x'],
                "line 2",
                "',' expected after '\"'",
            ),
        ]
        for newline_name, ending in newline_cases:
            for case_name, physical_lines, expected_location, expected_reason in parser_cases:
                with self.subTest(newline=newline_name, case=case_name):
                    raw_bytes = ending.join(physical_lines) + ending
                    file_path = self._write_file(f"{case_name}_{newline_name}.csv", raw_bytes)
                    try:
                        with self.assertRaises(InputValidationError) as ctx:
                            load_series("nifty50_price_index", file_path)
                    finally:
                        self.assertEqual(file_path.read_bytes(), raw_bytes)
                    error = ctx.exception
                    self.assertEqual(error.file_path, str(file_path))
                    self.assertEqual(error.reason, expected_reason)
                    self.assertEqual(error.line, expected_location)
                    self.assertEqual(
                        str(error),
                        f"CSV formatting error in '{file_path}' at {expected_location}: {expected_reason}",
                    )

    def test_11_header_only_physical_locations(self) -> None:
        """Header-only failures identify the parsed header, including its span."""
        newline_cases = [("lf", b"\n"), ("crlf", b"\r\n"), ("cr", b"\r")]
        header_cases = [
            ("ordinary", [b"Date,Close"], "line 1"),
            ("multiline", [b'Date,Close,"Notes', b'continued"'], "lines 1-2"),
        ]
        for newline_name, ending in newline_cases:
            for case_name, physical_lines, expected_location in header_cases:
                with self.subTest(newline=newline_name, header=case_name):
                    raw_bytes = ending.join(physical_lines) + ending
                    file_path = self._write_file(f"header_only_{case_name}_{newline_name}.csv", raw_bytes)
                    try:
                        with self.assertRaises(InputValidationError) as ctx:
                            load_series("nifty50_price_index", file_path)
                    finally:
                        self.assertEqual(file_path.read_bytes(), raw_bytes)
                    error = ctx.exception
                    self.assertEqual(error.file_path, str(file_path))
                    self.assertEqual(error.reason, "Header row present but no data rows")
                    self.assertEqual(error.line, expected_location)
                    self.assertEqual(
                        str(error),
                        f"Header-only CSV file with no data records at {expected_location}: '{file_path}'",
                    )

    def test_12_no_header_has_no_invented_location(self) -> None:
        """An absent header has no physical location to attach to its error."""
        for case_name, raw_bytes, expected_reason in [
            ("zero_bytes", b"", "File has 0 bytes"),
            ("bom_only", b"\xef\xbb\xbf", "File contains no rows"),
        ]:
            with self.subTest(case=case_name):
                file_path = self._write_file(f"no_header_{case_name}.csv", raw_bytes)
                try:
                    with self.assertRaises(InputValidationError) as ctx:
                        load_series("nifty50_price_index", file_path)
                finally:
                    self.assertEqual(file_path.read_bytes(), raw_bytes)
                error = ctx.exception
                self.assertEqual(error.file_path, str(file_path))
                self.assertEqual(error.reason, expected_reason)
                self.assertIsNone(error.line)
                self.assertEqual(str(error), f"Empty CSV file: '{file_path}'")

    def test_13_both_explicit_date_grammars(self) -> None:
        """Both grammars share literal calendar expectations and outer-cell stripping."""
        cases = [
            ("29-fEb-2040", datetime.date(2040, 2, 29)),
            ("29 fEb 2040", datetime.date(2040, 2, 29)),
            ("07-MaR-2036", datetime.date(2036, 3, 7)),
            ("07 MaR 2036", datetime.date(2036, 3, 7)),
            (" \t08-APR-2036\t ", datetime.date(2036, 4, 8)),
            (" \t08 APR 2036\t ", datetime.date(2036, 4, 8)),
        ]
        for case_id, (raw_date, expected_date) in enumerate(cases):
            with self.subTest(date=raw_date):
                path = self._write_file(
                    f"explicit_date_{case_id}.csv",
                    f"Date,Close\n{raw_date},12.3400\n",
                )
                series = load_series("nifty50_price_index", path)
                self.assertEqual(series.dates, (expected_date,))
                self.assertEqual(series.records[0].close, Decimal("12.3400"))
                self.assertEqual(series.records[0].close.as_tuple().exponent, -4)
                self.assertEqual(series.warnings, ())

    def test_14_date_grammar_near_misses_and_calendar_errors(self) -> None:
        """Reject inference/normalization while retaining field, path and row context."""
        invalid_dates = [
            ("29-Feb-2039", "Impossible calendar date"),
            ("29 Feb 2039", "Impossible calendar date"),
            ("31-Apr-2040", "Impossible calendar date"),
            ("31 Apr 2040", "Impossible calendar date"),
            ("00 Jan 2040", "Impossible calendar date"),
            ("32 Jan 2040", "Impossible calendar date"),
            ("01-Jan-0000", "Impossible calendar date"),
            ("01 Jan 0000", "Impossible calendar date"),
            ("07-Mai-2040", "Unknown English month"),
            ("07 Mai 2040", "Unknown English month"),
        ]
        syntax_errors = [
            "07-Mar 2040", "07 Mar-2040",
            "07  Mar 2040", "07 Mar  2040",
            "07--Mar-2040", "07-Mar--2040",
            "07\tMar\t2040", "07\tMar 2040", "07 Mar\t2040",
            "07\u00a0Mar\u00a02040", "07\u00a0Mar 2040", "07 Mar\u00a02040",
            "07\u202fMar\u202f2040", "07\u2003Mar\u20032040",
            "07/Mar/2040", "2040-03-07", "07-03-2040", "07 03 2040",
            "7-Mar-2040", "7 Mar 2040", "007 Mar 2040",
            "07 Mar 040", "07 Mar 02040", "07-March-2040", "07 Ma 2040",
            "07 M\u00e4r 2040", "\uff10\uff17 Mar 2040", "07 Mar \uff12\uff10\uff14\uff10",
            "07-Mar-2040junk", "07 Mar 2040junk",
        ]
        invalid_dates.extend((raw_date, "Invalid date format") for raw_date in syntax_errors)
        for case_id, (raw_date, message) in enumerate(invalid_dates):
            with self.subTest(date=raw_date):
                path = self._write_file(
                    f"invalid_grammar_{case_id}.csv",
                    f"Date,Close\n{raw_date},12.3400\n",
                )
                with self.assertRaises(InputValidationError) as ctx:
                    load_series("nifty50_price_index", path)
                error = ctx.exception
                self.assertEqual(error.field, "Date")
                self.assertEqual(error.file_path, str(path))
                self.assertEqual(error.line, "line 2")
                self.assertIn(message, str(error))
                self.assertIn(str(path), str(error))
                self.assertIn("line 2", str(error))
                if message == "Invalid date format":
                    self.assertIn("'dd-MMM-yyyy' or 'dd MMM yyyy'", str(error))
                    self.assertIn("'dd-MMM-yyyy' or 'dd MMM yyyy'", error.reason)

    def test_15_duplicate_dates_across_spellings(self) -> None:
        """Canonical dates reject equal/conflicting closes in both spelling orders."""
        spellings = [("29-Feb-2040", "29 fEb 2040"), ("29 fEb 2040", "29-Feb-2040")]
        for first, second in spellings:
            for second_close in ("7.500", "8.250"):
                with self.subTest(first=first, second=second, close=second_close):
                    within = self._write_file(
                        "duplicate_spellings.csv",
                        f"Date,Close\n{first},7.500\n{second},{second_close}\n",
                    )
                    with self.assertRaises(DuplicateDateError) as ctx:
                        load_series("nifty50_price_index", within)
                    self.assertEqual(ctx.exception.field, "Date")
                    self.assertEqual(ctx.exception.file_path, str(within))
                    self.assertEqual(ctx.exception.line, "line 3")
                    self.assertEqual(ctx.exception.reason, "Duplicate date 2040-02-29")
                    self.assertIn("line 2", str(ctx.exception))
                    self.assertIn(str(within), str(ctx.exception))

                    file_a = self._write_file("spelling_a.csv", f"Date,Close\n{first},7.500\n")
                    file_b = self._write_file("spelling_b.csv", f"Date,Close\n{second},{second_close}\n")
                    with self.assertRaises(DuplicateDateError) as ctx:
                        load_series("nifty50_price_index", [file_a, file_b])
                    self.assertEqual(ctx.exception.field, "Date")
                    self.assertEqual(ctx.exception.file_path, str(file_b))
                    self.assertEqual(ctx.exception.line, "line 2")
                    self.assertEqual(ctx.exception.reason, "Duplicate date 2040-02-29")
                    self.assertIn(str(file_a), str(ctx.exception))
                    self.assertIn(str(file_b), str(ctx.exception))
                    self.assertIn("line 2", str(ctx.exception))

    def test_16_space_dates_extra_columns_and_exact_alignment(self) -> None:
        """Synthetic Date-not-first CSV keeps raw provenance, sorting and missing VIX."""
        raw_bytes = (
            b"Label, Date , CLOSE ,Notes\n"
            b"synthetic-c,02 mAr 2040,13.125000,late\n"
            b"synthetic-a,29-Feb-2040,11.250000,leap\n"
            b"synthetic-b,01 Mar 2040,12.500000,middle\n"
        )
        path = self._write_file("synthetic_columns.csv", raw_bytes)
        nifty = load_series("nifty50_price_index", path)
        expected_dates = (
            datetime.date(2040, 2, 29),
            datetime.date(2040, 3, 1),
            datetime.date(2040, 3, 2),
        )
        self.assertEqual(nifty.dates, expected_dates)
        self.assertEqual(
            tuple(record.close for record in nifty.records),
            (Decimal("11.250000"), Decimal("12.500000"), Decimal("13.125000")),
        )
        self.assertEqual(tuple(record.close.as_tuple().exponent for record in nifty.records), (-6, -6, -6))
        self.assertEqual(nifty.warnings, ())
        self.assertEqual(path.read_bytes(), raw_bytes)
        self.assertEqual(nifty.provenance[0].raw_byte_count, len(raw_bytes))
        self.assertEqual(nifty.provenance[0].sha256, hashlib.sha256(raw_bytes).hexdigest())
        self.assertEqual(nifty.provenance[0].record_count, 3)
        self.assertEqual(nifty.provenance[0].observed_first_date, datetime.date(2040, 2, 29))
        self.assertEqual(nifty.provenance[0].observed_last_date, datetime.date(2040, 3, 2))

        vix_path = self._write_file(
            "synthetic_alignment.csv",
            "Date,Close\n02-Mar-2040,4.750\n29 FEB 2040,4.500\n",
        )
        vix = load_series("india_vix", vix_path)
        pair = align_pair(nifty, vix, expected_sessions=expected_dates)
        self.assertEqual(pair.calendar_status, "matches_supplied_sessions")
        self.assertEqual(pair.missing_sessions, ())
        self.assertEqual(pair.extra_sessions, ())
        self.assertEqual(tuple(obs.date for obs in pair.aligned_observations), expected_dates)
        self.assertEqual(
            tuple(obs.vix_close for obs in pair.aligned_observations),
            (Decimal("4.500"), None, Decimal("4.750")),
        )
        self.assertEqual(pair.nifty_only_dates, (datetime.date(2040, 3, 1),))
        self.assertEqual(pair.vix_only_dates, ())

if __name__ == "__main__":
    unittest.main()
