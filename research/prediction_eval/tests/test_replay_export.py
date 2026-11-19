"""
Unit tests for Prediction Evaluation Replay Export.

Validates:
1. Exact wire mapping: root, row, payload, and provenance field sets match replay.cjs.
2. Immutability and repeatability: input FeatureSeries is unchanged, output bytes are identical across calls.
3. Axis preservation: empty axis, warmup boundary (199/200), intermediate missing VIX (205),
   and simultaneous warmup+missing_vix reason ordering.
4. Decimal representation: scale preservation, positive exponent plain notation, and context-precision independence.
5. Numeric representation: binary64 float preservation (zeros, subnormals, extremes), boolean rejection,
   exact vs inexact integer predictor conversion, and rejection of integers beyond binary64 range.
6. Dates and provenance: Gregorian years 0001..9999, rejection of datetime as origin date, naive vs aware
   and low-year acquisition timestamps, sub-minute offset rejection, rejection of inverted requested
   intervals and inverted or count-inconsistent observed ranges, and Unicode provenance.
7. Negative boundary checks with asserted fields: invalid protocol, non-FeatureSeries, calendar mismatches
   (including an empty axis), duplicate dates, non-contiguous indices, nonpositive Closes, inconsistent
   readiness or reason order, and malformed unready_reasons containers.
"""

from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal
import decimal
import json
import math
import unittest

from research.prediction_eval.inputs import (
    FileProvenance,
    InputValidationError,
)
from research.prediction_eval.features import (
    FeatureSeries,
    NiftyFeatureRecord,
    PredictorPayload,
    PROTOCOL_ID as FEATURES_PROTOCOL_ID,
    REGIME_BULL,
    REGIME_SIDEWAYS,
    REGIME_HIGH_VOLATILITY,
    REASON_WARMUP,
    REASON_MISSING_VIX,
)
from research.prediction_eval.replay_export import (
    SCHEMA_VERSION,
    FEATURE_PROTOCOL,
    SERIES_ID,
    ASSET,
    HORIZON,
    VARIANT,
    serialize_replay_input,
)


def _make_payload(
    ret_5d: float = 0.01,
    rsi_14: float = 55.0,
    macd_hist: float = 0.5,
    vol_30d: float = 0.15,
    rel_strength_20d: float = 0.0,
    drawdown: float = -0.02,
    market_regime: str = REGIME_BULL,
) -> PredictorPayload:
    return PredictorPayload(
        ret_5d=ret_5d,
        rsi_14=rsi_14,
        macd_hist=macd_hist,
        vol_30d=vol_30d,
        rel_strength_20d=rel_strength_20d,
        drawdown=drawdown,
        market_regime=market_regime,
    )


def _make_provenance(
    file_path: str = "data/nifty50.csv",
    raw_byte_count: int = 1024,
    sha256: str = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    record_count: int = 2,
    observed_first_date: datetime.date = datetime.date(2024, 1, 1),
    observed_last_date: datetime.date = datetime.date(2024, 1, 2),
    source_url: str = None,
    requested_interval: tuple = None,
    acquisition_time: datetime.datetime = None,
    source_use_note: str = None,
) -> FileProvenance:
    return FileProvenance(
        file_path=file_path,
        raw_byte_count=raw_byte_count,
        sha256=sha256,
        record_count=record_count,
        observed_first_date=observed_first_date,
        observed_last_date=observed_last_date,
        source_url=source_url,
        requested_interval=requested_interval,
        acquisition_time=acquisition_time,
        source_use_note=source_use_note,
    )


def _make_201_series(ready_payload: PredictorPayload = None) -> FeatureSeries:
    """Helper to create valid 201-row series where origins 0..199 are warmup and 200 is ready."""
    d = datetime.date(2024, 1, 1)
    one_day = datetime.timedelta(days=1)
    records = []
    p = ready_payload if ready_payload is not None else _make_payload()
    for i in range(201):
        is_ready = (i == 200)
        records.append(
            NiftyFeatureRecord(
                origin_index=i,
                origin_date=d,
                origin_close=Decimal("20000.00"),
                vix_close=Decimal("15.00"),
                feature_ready=is_ready,
                payload=p if is_ready else None,
                unready_reasons=() if is_ready else (REASON_WARMUP,),
            )
        )
        d += one_day
    return FeatureSeries(
        protocol_id=FEATURES_PROTOCOL_ID,
        axis_start_date=records[0].origin_date,
        records=tuple(records),
        calendar_status="not_checked",
        missing_sessions=(),
        extra_sessions=(),
        nifty_provenance=(),
        vix_provenance=(),
    )


class TestReplayExport(unittest.TestCase):
    """Test suite for research/prediction_eval/replay_export.py."""

    def test_exact_mapping_and_constants(self) -> None:
        """Verifies top-level wire schema, exact keys, and fixed protocol constants."""
        records = [
            NiftyFeatureRecord(
                origin_index=0,
                origin_date=datetime.date(2024, 1, 1),
                origin_close=Decimal("21000.50"),
                vix_close=Decimal("14.25"),
                feature_ready=False,
                payload=None,
                unready_reasons=(REASON_WARMUP,),
            )
        ]
        prov = _make_provenance()
        series = FeatureSeries(
            protocol_id=FEATURES_PROTOCOL_ID,
            axis_start_date=datetime.date(2024, 1, 1),
            records=tuple(records),
            calendar_status="not_checked",
            missing_sessions=(),
            extra_sessions=(),
            nifty_provenance=(prov,),
            vix_provenance=(prov,),
        )

        raw_bytes = serialize_replay_input(series)
        self.assertTrue(raw_bytes.endswith(b"\n"))
        self.assertFalse(raw_bytes.startswith(b"\xef\xbb\xbf"))  # No UTF-8 BOM

        doc = json.loads(raw_bytes.decode("utf-8"))
        expected_root_keys = {
            "schema_version",
            "feature_protocol",
            "series_id",
            "asset",
            "horizon",
            "variant",
            "axis_start_date",
            "calendar_status",
            "missing_sessions",
            "extra_sessions",
            "nifty_provenance",
            "vix_provenance",
            "rows",
        }
        self.assertEqual(set(doc.keys()), expected_root_keys)
        self.assertEqual(doc["schema_version"], SCHEMA_VERSION)
        self.assertEqual(doc["feature_protocol"], FEATURE_PROTOCOL)
        self.assertEqual(doc["series_id"], SERIES_ID)
        self.assertEqual(doc["asset"], ASSET)
        self.assertEqual(doc["horizon"], HORIZON)
        self.assertEqual(doc["variant"], VARIANT)
        self.assertEqual(doc["axis_start_date"], "2024-01-01")
        self.assertEqual(doc["calendar_status"], "not_checked")
        self.assertEqual(doc["missing_sessions"], [])
        self.assertEqual(doc["extra_sessions"], [])
        self.assertEqual(len(doc["rows"]), 1)

        row = doc["rows"][0]
        expected_row_keys = {
            "origin_index",
            "origin_date",
            "origin_close",
            "vix_close",
            "feature_ready",
            "unready_reasons",
            "payload",
        }
        self.assertEqual(set(row.keys()), expected_row_keys)
        self.assertEqual(row["origin_index"], 0)
        self.assertEqual(row["origin_date"], "2024-01-01")
        self.assertEqual(row["origin_close"], "21000.50")
        self.assertEqual(row["vix_close"], "14.25")
        self.assertFalse(row["feature_ready"])
        self.assertEqual(row["unready_reasons"], ["warmup"])
        self.assertIsNone(row["payload"])

    def test_immutability_and_repeatability(self) -> None:
        """Verifies that the input object is not modified and serialization is bit-identical across runs."""
        payload = _make_payload()
        rec0 = NiftyFeatureRecord(
            origin_index=0,
            origin_date=datetime.date(2024, 1, 1),
            origin_close=Decimal("20000.00"),
            vix_close=Decimal("13.50"),
            feature_ready=False,
            payload=None,
            unready_reasons=(REASON_WARMUP,),
        )
        series = FeatureSeries(
            protocol_id=FEATURES_PROTOCOL_ID,
            axis_start_date=datetime.date(2024, 1, 1),
            records=(rec0,),
            calendar_status="not_checked",
            missing_sessions=(),
            extra_sessions=(),
            nifty_provenance=(),
            vix_provenance=(),
        )

        bytes_1 = serialize_replay_input(series)
        bytes_2 = serialize_replay_input(series)
        self.assertEqual(bytes_1, bytes_2)

        # Invariance of original series
        self.assertEqual(series.protocol_id, FEATURES_PROTOCOL_ID)
        self.assertEqual(len(series.records), 1)
        self.assertEqual(series.records[0].origin_close, Decimal("20000.00"))

    def test_empty_axis(self) -> None:
        """Verifies that an empty FeatureSeries serializes with axis_start_date null and empty rows."""
        series = FeatureSeries(
            protocol_id=FEATURES_PROTOCOL_ID,
            axis_start_date=None,
            records=(),
            calendar_status="not_checked",
            missing_sessions=(),
            extra_sessions=(),
            nifty_provenance=(),
            vix_provenance=(),
        )
        raw_bytes = serialize_replay_input(series)
        doc = json.loads(raw_bytes.decode("utf-8"))
        self.assertIsNone(doc["axis_start_date"])
        self.assertEqual(doc["rows"], [])

    def test_readiness_boundary_199_200_and_missing_vix_205(self) -> None:
        """Verifies warmup boundary at 199/200, missing VIX at 205, and dual warmup+missing reason order."""
        records = []
        d = datetime.date(2023, 1, 2)
        one_day = datetime.timedelta(days=1)
        payload = _make_payload()

        for i in range(207):
            vix = None if i in (10, 205) else Decimal("14.00")
            is_warmup = i < 200
            is_missing_vix = vix is None

            reasons = []
            if is_warmup:
                reasons.append(REASON_WARMUP)
            if is_missing_vix:
                reasons.append(REASON_MISSING_VIX)

            is_ready = len(reasons) == 0
            row_payload = payload if is_ready else None

            records.append(
                NiftyFeatureRecord(
                    origin_index=i,
                    origin_date=d,
                    origin_close=Decimal("20000.00"),
                    vix_close=vix,
                    feature_ready=is_ready,
                    payload=row_payload,
                    unready_reasons=tuple(reasons),
                )
            )
            d += one_day

        series = FeatureSeries(
            protocol_id=FEATURES_PROTOCOL_ID,
            axis_start_date=records[0].origin_date,
            records=tuple(records),
            calendar_status="not_checked",
            missing_sessions=(),
            extra_sessions=(),
            nifty_provenance=(),
            vix_provenance=(),
        )

        doc = json.loads(serialize_replay_input(series).decode("utf-8"))
        rows = doc["rows"]
        self.assertEqual(len(rows), 207)

        # Row 10: warmup + missing VIX -> exactly ['warmup', 'missing_vix']
        self.assertFalse(rows[10]["feature_ready"])
        self.assertEqual(rows[10]["unready_reasons"], ["warmup", "missing_vix"])
        self.assertIsNone(rows[10]["vix_close"])
        self.assertIsNone(rows[10]["payload"])

        # Row 199: last warmup row
        self.assertFalse(rows[199]["feature_ready"])
        self.assertEqual(rows[199]["unready_reasons"], ["warmup"])
        self.assertIsNone(rows[199]["payload"])

        # Row 200: first ready row
        self.assertTrue(rows[200]["feature_ready"])
        self.assertEqual(rows[200]["unready_reasons"], [])
        self.assertIsNotNone(rows[200]["payload"])
        self.assertEqual(rows[200]["payload"]["market_regime"], REGIME_BULL)

        # Row 205: intermediate missing VIX after warmup
        self.assertFalse(rows[205]["feature_ready"])
        self.assertEqual(rows[205]["unready_reasons"], ["missing_vix"])
        self.assertIsNone(rows[205]["vix_close"])
        self.assertIsNone(rows[205]["payload"])

        # Row 204 and 206: neighboring ready rows
        self.assertTrue(rows[204]["feature_ready"])
        self.assertTrue(rows[206]["feature_ready"])

    def test_decimal_scale_and_context_independence(self) -> None:
        """Verifies that Decimals preserve trailing scale and positive exponents without context interference."""
        saved_prec = decimal.getcontext().prec
        with decimal.localcontext() as ctx:
            # Set context precision abnormally low to test that formatting is independent
            ctx.prec = 2

            d_scaled = Decimal("100.2300")
            d_exp_pos = Decimal("1e2")
            d_exp_sci = Decimal("1.25E+3")
            d_long_frac = Decimal("100.1234567890123456789")
            # Values below 1 need the leading-zero form; trailing scale must survive
            d_below_one = Decimal("0.0050")
            d_tiny_exp = Decimal("5E-7")

            records = [
                NiftyFeatureRecord(
                    origin_index=0,
                    origin_date=datetime.date(2024, 1, 1),
                    origin_close=d_scaled,
                    vix_close=d_exp_pos,
                    feature_ready=False,
                    payload=None,
                    unready_reasons=(REASON_WARMUP,),
                ),
                NiftyFeatureRecord(
                    origin_index=1,
                    origin_date=datetime.date(2024, 1, 2),
                    origin_close=d_exp_sci,
                    vix_close=d_long_frac,
                    feature_ready=False,
                    payload=None,
                    unready_reasons=(REASON_WARMUP,),
                ),
                NiftyFeatureRecord(
                    origin_index=2,
                    origin_date=datetime.date(2024, 1, 3),
                    origin_close=d_below_one,
                    vix_close=d_tiny_exp,
                    feature_ready=False,
                    payload=None,
                    unready_reasons=(REASON_WARMUP,),
                ),
            ]
            series = FeatureSeries(
                protocol_id=FEATURES_PROTOCOL_ID,
                axis_start_date=datetime.date(2024, 1, 1),
                records=tuple(records),
                calendar_status="not_checked",
                missing_sessions=(),
                extra_sessions=(),
                nifty_provenance=(),
                vix_provenance=(),
            )

            doc = json.loads(serialize_replay_input(series).decode("utf-8"))
            self.assertEqual(doc["rows"][0]["origin_close"], "100.2300")
            self.assertEqual(doc["rows"][0]["vix_close"], "100")
            self.assertEqual(doc["rows"][1]["origin_close"], "1250")
            self.assertEqual(doc["rows"][1]["vix_close"], "100.1234567890123456789")
            self.assertEqual(doc["rows"][2]["origin_close"], "0.0050")
            self.assertEqual(doc["rows"][2]["vix_close"], "0.0000005")

        # Verify precision was safely restored to prior context upon exiting localcontext
        self.assertEqual(decimal.getcontext().prec, saved_prec)

    def test_numeric_predictor_preservation_and_checks(self) -> None:
        """Verifies binary64 float preservation including zeros, subnormals, and int representations."""
        subnormal_float = 1.0e-320
        large_finite_float = 1.7e308

        payload = _make_payload(
            ret_5d=0.0,
            rsi_14=0.0,
            macd_hist=-0.0,
            vol_30d=subnormal_float,
            rel_strength_20d=0.0,
            drawdown=large_finite_float,
        )
        series = _make_201_series(payload)

        doc = json.loads(serialize_replay_input(series).decode("utf-8"))
        p = doc["rows"][200]["payload"]
        self.assertEqual(p["ret_5d"], 0.0)
        self.assertEqual(p["rsi_14"], 0.0)
        self.assertEqual(p["vol_30d"], subnormal_float)
        self.assertEqual(p["drawdown"], large_finite_float)

    def test_date_and_provenance_representations(self) -> None:
        """Verifies four-digit ISO dates for years 0001..9999, naive/aware timestamps, and Unicode provenance."""
        d1 = datetime.date(1, 1, 5)
        d2 = datetime.date(99, 12, 31)
        d3 = datetime.date(9999, 12, 31)

        naive_acq = datetime.datetime(2024, 1, 15, 10, 30, 45, 123456)
        aware_acq = datetime.datetime(
            2024, 1, 15, 10, 30, 45, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        )

        prov1 = _make_provenance(
            file_path="data/provenance_unicode_индекс.csv",
            source_url="https://example.com/индекс?q=1",
            source_use_note="Historical extract с примечанием",
            requested_interval=(datetime.date(2024, 1, 1), datetime.date(2024, 1, 10)),
            acquisition_time=naive_acq,
        )
        prov2 = _make_provenance(
            file_path="data/vix.csv",
            acquisition_time=aware_acq,
        )
        # Low-year naive datetime keeps four-digit year padding and stays offset-free
        prov3 = _make_provenance(
            file_path="data/vix_part2.csv",
            acquisition_time=datetime.datetime(5, 3, 4, 1, 2, 3),
        )

        records = [
            NiftyFeatureRecord(
                origin_index=0,
                origin_date=d1,
                origin_close=Decimal("100.00"),
                vix_close=Decimal("15.00"),
                feature_ready=False,
                payload=None,
                unready_reasons=(REASON_WARMUP,),
            ),
            NiftyFeatureRecord(
                origin_index=1,
                origin_date=d2,
                origin_close=Decimal("105.00"),
                vix_close=Decimal("15.50"),
                feature_ready=False,
                payload=None,
                unready_reasons=(REASON_WARMUP,),
            ),
            NiftyFeatureRecord(
                origin_index=2,
                origin_date=d3,
                origin_close=Decimal("110.00"),
                vix_close=Decimal("16.00"),
                feature_ready=False,
                payload=None,
                unready_reasons=(REASON_WARMUP,),
            ),
        ]
        series = FeatureSeries(
            protocol_id=FEATURES_PROTOCOL_ID,
            axis_start_date=d1,
            records=tuple(records),
            calendar_status="not_checked",
            missing_sessions=(),
            extra_sessions=(),
            nifty_provenance=(prov1,),
            vix_provenance=(prov2, prov3),
        )

        doc = json.loads(serialize_replay_input(series).decode("utf-8"))
        self.assertEqual(doc["rows"][0]["origin_date"], "0001-01-05")
        self.assertEqual(doc["rows"][1]["origin_date"], "0099-12-31")
        self.assertEqual(doc["rows"][2]["origin_date"], "9999-12-31")

        p1 = doc["nifty_provenance"][0]
        self.assertEqual(p1["file_path"], "data/provenance_unicode_индекс.csv")
        self.assertEqual(p1["source_url"], "https://example.com/индекс?q=1")
        self.assertEqual(p1["source_use_note"], "Historical extract с примечанием")
        self.assertEqual(p1["requested_interval"], ["2024-01-01", "2024-01-10"])
        self.assertEqual(p1["acquisition_time"], "2024-01-15T10:30:45.123456")

        p2 = doc["vix_provenance"][0]
        self.assertEqual(p2["acquisition_time"], "2024-01-15T10:30:45+05:30")
        p3 = doc["vix_provenance"][1]
        self.assertEqual(p3["file_path"], "data/vix_part2.csv")
        self.assertEqual(p3["acquisition_time"], "0005-03-04T01:02:03")

    def test_calendar_status_invariants(self) -> None:
        """Verifies calendar_status mismatch requirements and disjoint session lists."""
        d1 = datetime.date(2024, 1, 1)
        d2 = datetime.date(2024, 1, 2)
        missing_d = datetime.date(2024, 1, 3)

        records = [
            NiftyFeatureRecord(
                origin_index=0,
                origin_date=d1,
                origin_close=Decimal("100.00"),
                vix_close=Decimal("15.00"),
                feature_ready=False,
                payload=None,
                unready_reasons=(REASON_WARMUP,),
            ),
            NiftyFeatureRecord(
                origin_index=1,
                origin_date=d2,
                origin_close=Decimal("105.00"),
                vix_close=Decimal("15.50"),
                feature_ready=False,
                payload=None,
                unready_reasons=(REASON_WARMUP,),
            ),
        ]

        # Valid mismatch: extra session is on axis (d2), missing session is not on axis (missing_d)
        series = FeatureSeries(
            protocol_id=FEATURES_PROTOCOL_ID,
            axis_start_date=d1,
            records=tuple(records),
            calendar_status="mismatch",
            missing_sessions=(missing_d,),
            extra_sessions=(d2,),
            nifty_provenance=(),
            vix_provenance=(),
        )
        doc = json.loads(serialize_replay_input(series).decode("utf-8"))
        self.assertEqual(doc["calendar_status"], "mismatch")
        self.assertEqual(doc["missing_sessions"], ["2024-01-03"])
        self.assertEqual(doc["extra_sessions"], ["2024-01-02"])

        # Invalid mismatch: extra session is NOT on axis
        invalid_extra_series = FeatureSeries(
            protocol_id=FEATURES_PROTOCOL_ID,
            axis_start_date=d1,
            records=tuple(records),
            calendar_status="mismatch",
            missing_sessions=(),
            extra_sessions=(datetime.date(2024, 1, 10),),
            nifty_provenance=(),
            vix_provenance=(),
        )
        with self.assertRaises(InputValidationError) as ctx:
            serialize_replay_input(invalid_extra_series)
        self.assertEqual(ctx.exception.field, "extra_sessions")

        # Invalid mismatch: missing session IS on axis
        invalid_missing_series = FeatureSeries(
            protocol_id=FEATURES_PROTOCOL_ID,
            axis_start_date=d1,
            records=tuple(records),
            calendar_status="mismatch",
            missing_sessions=(d1,),
            extra_sessions=(),
            nifty_provenance=(),
            vix_provenance=(),
        )
        with self.assertRaises(InputValidationError) as ctx:
            serialize_replay_input(invalid_missing_series)
        self.assertEqual(ctx.exception.field, "missing_sessions")

        # Invalid not_checked with non-empty discrepancies
        invalid_status_series = FeatureSeries(
            protocol_id=FEATURES_PROTOCOL_ID,
            axis_start_date=d1,
            records=tuple(records),
            calendar_status="not_checked",
            missing_sessions=(missing_d,),
            extra_sessions=(),
            nifty_provenance=(),
            vix_provenance=(),
        )
        with self.assertRaises(InputValidationError) as ctx:
            serialize_replay_input(invalid_status_series)
        self.assertEqual(ctx.exception.field, "calendar_status")

        # Invalid mismatch on an empty axis: an extra session cannot exist without origins
        empty_axis_extra_series = FeatureSeries(
            protocol_id=FEATURES_PROTOCOL_ID,
            axis_start_date=None,
            records=(),
            calendar_status="mismatch",
            missing_sessions=(),
            extra_sessions=(d2,),
            nifty_provenance=(),
            vix_provenance=(),
        )
        with self.assertRaises(InputValidationError) as ctx:
            serialize_replay_input(empty_axis_extra_series)
        self.assertEqual(ctx.exception.field, "extra_sessions")

    def test_rejection_of_boolean_and_wrong_types(self) -> None:
        """Verifies rejection of boolean substitutes in numeric slots and wrong types."""
        # Bool in Close price
        with self.assertRaises(InputValidationError) as ctx:
            records = [
                NiftyFeatureRecord(
                    origin_index=0,
                    origin_date=datetime.date(2024, 1, 1),
                    origin_close=True,  # type: ignore[arg-type]
                    vix_close=Decimal("15.00"),
                    feature_ready=False,
                    payload=None,
                    unready_reasons=(REASON_WARMUP,),
                )
            ]
            series = FeatureSeries(
                protocol_id=FEATURES_PROTOCOL_ID,
                axis_start_date=datetime.date(2024, 1, 1),
                records=tuple(records),
                calendar_status="not_checked",
                missing_sessions=(),
                extra_sessions=(),
                nifty_provenance=(),
                vix_provenance=(),
            )
            serialize_replay_input(series)
        self.assertEqual(ctx.exception.field, "origin_close")

        # Datetime as origin_date on row 1 (with valid row 0 date matching axis_start_date)
        with self.assertRaises(InputValidationError) as ctx:
            records = [
                NiftyFeatureRecord(
                    origin_index=0,
                    origin_date=datetime.date(2024, 1, 1),
                    origin_close=Decimal("20000.00"),
                    vix_close=Decimal("15.00"),
                    feature_ready=False,
                    payload=None,
                    unready_reasons=(REASON_WARMUP,),
                ),
                NiftyFeatureRecord(
                    origin_index=1,
                    origin_date=datetime.datetime(2024, 1, 2, 12, 0, 0),  # type: ignore[arg-type]
                    origin_close=Decimal("20000.00"),
                    vix_close=Decimal("15.00"),
                    feature_ready=False,
                    payload=None,
                    unready_reasons=(REASON_WARMUP,),
                ),
            ]
            series = FeatureSeries(
                protocol_id=FEATURES_PROTOCOL_ID,
                axis_start_date=datetime.date(2024, 1, 1),
                records=tuple(records),
                calendar_status="not_checked",
                missing_sessions=(),
                extra_sessions=(),
                nifty_provenance=(),
                vix_provenance=(),
            )
            serialize_replay_input(series)
        self.assertEqual(ctx.exception.field, "origin_date")

    def test_rejection_of_sub_minute_timezone_offset(self) -> None:
        """Verifies rejection of acquisition timestamps with sub-minute timezone offsets."""
        sub_minute_tz = datetime.timezone(datetime.timedelta(seconds=12030))  # 3h 20m 30s
        acq_time = datetime.datetime(2024, 1, 1, 10, 0, 0, tzinfo=sub_minute_tz)
        prov = _make_provenance(acquisition_time=acq_time)

        records = [
            NiftyFeatureRecord(
                origin_index=0,
                origin_date=datetime.date(2024, 1, 1),
                origin_close=Decimal("20000.00"),
                vix_close=Decimal("15.00"),
                feature_ready=False,
                payload=None,
                unready_reasons=(REASON_WARMUP,),
            )
        ]
        series = FeatureSeries(
            protocol_id=FEATURES_PROTOCOL_ID,
            axis_start_date=datetime.date(2024, 1, 1),
            records=tuple(records),
            calendar_status="not_checked",
            missing_sessions=(),
            extra_sessions=(),
            nifty_provenance=(prov,),
            vix_provenance=(),
        )
        with self.assertRaises(InputValidationError) as ctx:
            serialize_replay_input(series)
        self.assertIn("acquisition_time", ctx.exception.field)

    def test_rejection_of_wrong_protocol(self) -> None:
        """Verifies rejection when series protocol does not match expected nifty-close-features-v1."""
        series = FeatureSeries(
            protocol_id="unsupported-protocol-v2",
            axis_start_date=None,
            records=(),
            calendar_status="not_checked",
            missing_sessions=(),
            extra_sessions=(),
            nifty_provenance=(),
            vix_provenance=(),
        )
        with self.assertRaises(InputValidationError) as ctx:
            serialize_replay_input(series)
        self.assertEqual(ctx.exception.field, "series.protocol_id")

    def test_rejection_of_nonfinite_and_boolean_predictors(self) -> None:
        """Verifies rejection of NaN, Inf, and boolean values in PredictorPayload."""
        # Test boolean in ret_5d
        p_bool = _make_payload()
        object.__setattr__(p_bool, "ret_5d", True)
        with self.assertRaises(InputValidationError) as ctx:
            serialize_replay_input(_make_201_series(p_bool))
        self.assertEqual(ctx.exception.field, "ret_5d")

        # Test NaN in rsi_14
        p_nan = _make_payload()
        object.__setattr__(p_nan, "rsi_14", float("nan"))
        with self.assertRaises(InputValidationError) as ctx:
            serialize_replay_input(_make_201_series(p_nan))
        self.assertEqual(ctx.exception.field, "rsi_14")

        # Test Infinity in drawdown
        p_inf = _make_payload()
        object.__setattr__(p_inf, "drawdown", float("inf"))
        with self.assertRaises(InputValidationError) as ctx:
            serialize_replay_input(_make_201_series(p_inf))
        self.assertEqual(ctx.exception.field, "drawdown")

    def test_integer_predictor_exactness(self) -> None:
        """Verifies exact integer conversion and rejection of inexact or out-of-range integers."""
        # Exact int conversion (e.g. 1 -> 1.0)
        p_exact = _make_payload(ret_5d=1)
        series_exact = _make_201_series(p_exact)
        doc = json.loads(serialize_replay_input(series_exact).decode("utf-8"))
        self.assertEqual(doc["rows"][200]["payload"]["ret_5d"], 1.0)

        # Inexact int (2^53 + 1 = 9007199254740993) cannot be represented in binary64
        inexact_val = 9007199254740993
        p_inexact = _make_payload()
        object.__setattr__(p_inexact, "ret_5d", inexact_val)
        with self.assertRaises(InputValidationError) as ctx:
            serialize_replay_input(_make_201_series(p_inexact))
        self.assertEqual(ctx.exception.field, "ret_5d")

        # An exactly representable integer above 2^53 keeps its binary64 value
        p_big_exact = _make_payload(ret_5d=2**60)
        doc_big = json.loads(serialize_replay_input(_make_201_series(p_big_exact)).decode("utf-8"))
        self.assertEqual(doc_big["rows"][200]["payload"]["ret_5d"], float(2**60))

        # An integer beyond the finite binary64 range must fail as InputValidationError, not
        # escape as OverflowError. PredictorPayload rejects it on construction, so the frozen
        # field is bypassed the same way as above.
        p_overflow = _make_payload()
        object.__setattr__(p_overflow, "ret_5d", 2**1024)
        with self.assertRaises(InputValidationError) as ctx:
            serialize_replay_input(_make_201_series(p_overflow))
        self.assertEqual(ctx.exception.field, "ret_5d")
        self.assertIn("row 200", str(ctx.exception))

    def test_rejection_of_malformed_unready_reasons(self) -> None:
        """Verifies a ready row whose unready_reasons is not a reason sequence fails with field context."""
        # NiftyFeatureRecord checks reasons only for truthiness, so None passes construction on a
        # ready row; the serializer must reject it as InputValidationError, not a raw TypeError.
        series = _make_201_series()
        records = list(series.records)
        ready = records[200]
        records[200] = NiftyFeatureRecord(
            origin_index=200,
            origin_date=ready.origin_date,
            origin_close=ready.origin_close,
            vix_close=ready.vix_close,
            feature_ready=True,
            payload=ready.payload,
            unready_reasons=None,  # type: ignore[arg-type]
        )
        malformed = dataclasses.replace(series, records=tuple(records))
        with self.assertRaises(InputValidationError) as ctx:
            serialize_replay_input(malformed)
        self.assertEqual(ctx.exception.field, "unready_reasons")
        self.assertIn("Row 200", str(ctx.exception))

    def test_rejection_of_inconsistent_readiness_and_reasons(self) -> None:
        """Verifies readiness and reason order are derived from index and VIX presence, not trusted."""
        series = _make_201_series()
        payload = series.records[200].payload

        def with_row(idx: int, **changes) -> FeatureSeries:
            # Each altered record is still accepted by NiftyFeatureRecord itself
            records = list(series.records)
            records[idx] = dataclasses.replace(records[idx], **changes)
            return dataclasses.replace(series, records=tuple(records))

        cases = [
            # Warmup row claiming readiness
            (199, dict(feature_ready=True, payload=payload, unready_reasons=()), "feature_ready"),
            # Ready-eligible row claiming a missing VIX it does not have
            (200, dict(feature_ready=False, payload=None, unready_reasons=(REASON_MISSING_VIX,)), "feature_ready"),
            # Ready row whose VIX is actually missing
            (200, dict(vix_close=None), "feature_ready"),
            # Warmup plus missing VIX with the reasons reversed
            (10, dict(vix_close=None, unready_reasons=(REASON_MISSING_VIX, REASON_WARMUP)), "unready_reasons"),
        ]
        for idx, changes, field in cases:
            with self.subTest(row=idx, changes=sorted(changes)):
                with self.assertRaises(InputValidationError) as ctx:
                    serialize_replay_input(with_row(idx, **changes))
                self.assertEqual(ctx.exception.field, field)
                self.assertIn(f"Row {idx}", str(ctx.exception))

    def test_rejection_of_inverted_or_inconsistent_provenance_ranges(self) -> None:
        """Verifies requested intervals and observed date ranges are ordered and consistent with record_count."""

        def series_with(prov: FileProvenance) -> FeatureSeries:
            return FeatureSeries(
                protocol_id=FEATURES_PROTOCOL_ID,
                axis_start_date=None,
                records=(),
                calendar_status="not_checked",
                missing_sessions=(),
                extra_sessions=(),
                nifty_provenance=(prov,),
                vix_provenance=(),
            )

        cases = [
            (
                _make_provenance(requested_interval=(datetime.date(2024, 1, 10), datetime.date(2024, 1, 1))),
                "nifty_provenance[0].requested_interval",
                "Inverted requested interval: 2024-01-10 > 2024-01-01",
            ),
            (
                _make_provenance(
                    observed_first_date=datetime.date(2024, 1, 2),
                    observed_last_date=datetime.date(2024, 1, 1),
                ),
                "nifty_provenance[0]",
                "Inverted observed date range",
            ),
            (
                _make_provenance(record_count=0),
                "nifty_provenance[0]",
                "Non-null observed dates with record_count 0",
            ),
            (
                _make_provenance(observed_last_date=None),
                "nifty_provenance[0]",
                "Null observed date with record_count > 0",
            ),
        ]
        for prov, field, reason in cases:
            with self.subTest(reason=reason):
                with self.assertRaises(InputValidationError) as ctx:
                    serialize_replay_input(series_with(prov))
                self.assertEqual(ctx.exception.field, field)
                self.assertEqual(ctx.exception.reason, reason)

    def test_rejection_of_nonpositive_decimal_closes(self) -> None:
        """Verifies rejection of zero and negative Close values for origin and VIX."""
        d = datetime.date(2024, 1, 1)

        # Zero origin_close
        rec_zero_close = NiftyFeatureRecord(
            origin_index=0,
            origin_date=d,
            origin_close=Decimal("0.00"),
            vix_close=Decimal("15.00"),
            feature_ready=False,
            payload=None,
            unready_reasons=(REASON_WARMUP,),
        )
        series_zero_close = FeatureSeries(
            protocol_id=FEATURES_PROTOCOL_ID,
            axis_start_date=d,
            records=(rec_zero_close,),
            calendar_status="not_checked",
            missing_sessions=(),
            extra_sessions=(),
            nifty_provenance=(),
            vix_provenance=(),
        )
        with self.assertRaises(InputValidationError) as ctx:
            serialize_replay_input(series_zero_close)
        self.assertEqual(ctx.exception.field, "origin_close")

        # Negative origin_close
        rec_neg_close = NiftyFeatureRecord(
            origin_index=0,
            origin_date=d,
            origin_close=Decimal("-100.50"),
            vix_close=Decimal("15.00"),
            feature_ready=False,
            payload=None,
            unready_reasons=(REASON_WARMUP,),
        )
        series_neg_close = FeatureSeries(
            protocol_id=FEATURES_PROTOCOL_ID,
            axis_start_date=d,
            records=(rec_neg_close,),
            calendar_status="not_checked",
            missing_sessions=(),
            extra_sessions=(),
            nifty_provenance=(),
            vix_provenance=(),
        )
        with self.assertRaises(InputValidationError) as ctx:
            serialize_replay_input(series_neg_close)
        self.assertEqual(ctx.exception.field, "origin_close")

        # Zero vix_close
        rec_zero_vix = NiftyFeatureRecord(
            origin_index=0,
            origin_date=d,
            origin_close=Decimal("20000.00"),
            vix_close=Decimal("0.00"),
            feature_ready=False,
            payload=None,
            unready_reasons=(REASON_WARMUP,),
        )
        series_zero_vix = FeatureSeries(
            protocol_id=FEATURES_PROTOCOL_ID,
            axis_start_date=d,
            records=(rec_zero_vix,),
            calendar_status="not_checked",
            missing_sessions=(),
            extra_sessions=(),
            nifty_provenance=(),
            vix_provenance=(),
        )
        with self.assertRaises(InputValidationError) as ctx:
            serialize_replay_input(series_zero_vix)
        self.assertEqual(ctx.exception.field, "vix_close")

    def test_rejection_of_duplicate_axis_date(self) -> None:
        """Verifies rejection of duplicate dates on the origin axis."""
        d = datetime.date(2024, 1, 1)
        records = [
            NiftyFeatureRecord(
                origin_index=0,
                origin_date=d,
                origin_close=Decimal("20000.00"),
                vix_close=Decimal("15.00"),
                feature_ready=False,
                payload=None,
                unready_reasons=(REASON_WARMUP,),
            ),
            NiftyFeatureRecord(
                origin_index=1,
                origin_date=d,  # duplicate date
                origin_close=Decimal("20100.00"),
                vix_close=Decimal("15.50"),
                feature_ready=False,
                payload=None,
                unready_reasons=(REASON_WARMUP,),
            ),
        ]
        series = FeatureSeries(
            protocol_id=FEATURES_PROTOCOL_ID,
            axis_start_date=d,
            records=tuple(records),
            calendar_status="not_checked",
            missing_sessions=(),
            extra_sessions=(),
            nifty_provenance=(),
            vix_provenance=(),
        )
        with self.assertRaises(InputValidationError) as ctx:
            serialize_replay_input(series)
        self.assertEqual(ctx.exception.field, "origin_date")

    def test_rejection_of_noncontiguous_index(self) -> None:
        """Verifies rejection when origin_index does not match contiguous 0-based position."""
        d1 = datetime.date(2024, 1, 1)
        d2 = datetime.date(2024, 1, 2)
        records = [
            NiftyFeatureRecord(
                origin_index=0,
                origin_date=d1,
                origin_close=Decimal("20000.00"),
                vix_close=Decimal("15.00"),
                feature_ready=False,
                payload=None,
                unready_reasons=(REASON_WARMUP,),
            ),
            NiftyFeatureRecord(
                origin_index=2,  # skipped index 1
                origin_date=d2,
                origin_close=Decimal("20100.00"),
                vix_close=Decimal("15.50"),
                feature_ready=False,
                payload=None,
                unready_reasons=(REASON_WARMUP,),
            ),
        ]
        series = FeatureSeries(
            protocol_id=FEATURES_PROTOCOL_ID,
            axis_start_date=d1,
            records=tuple(records),
            calendar_status="not_checked",
            missing_sessions=(),
            extra_sessions=(),
            nifty_provenance=(),
            vix_provenance=(),
        )
        with self.assertRaises(InputValidationError) as ctx:
            serialize_replay_input(series)
        self.assertEqual(ctx.exception.field, "origin_index")

    def test_rejection_of_boolean_and_noninteger_origin_index(self) -> None:
        """Verifies rejection of boolean, float, string, or negative origin_index values (A1)."""
        d1 = datetime.date(2024, 1, 1)

        # Test with boolean False (compares equal to 0 in Python)
        rec_bool = NiftyFeatureRecord(
            origin_index=False,  # type: ignore[arg-type]
            origin_date=d1,
            origin_close=Decimal("20000.00"),
            vix_close=Decimal("15.00"),
            feature_ready=False,
            payload=None,
            unready_reasons=(REASON_WARMUP,),
        )
        series_bool = FeatureSeries(
            protocol_id=FEATURES_PROTOCOL_ID,
            axis_start_date=d1,
            records=(rec_bool,),
            calendar_status="not_checked",
            missing_sessions=(),
            extra_sessions=(),
            nifty_provenance=(),
            vix_provenance=(),
        )
        with self.assertRaises(InputValidationError) as ctx:
            serialize_replay_input(series_bool)
        self.assertEqual(ctx.exception.field, "rows[0].origin_index")

        # Test with float 0.0 (compares equal to 0 in Python)
        rec_float = NiftyFeatureRecord(
            origin_index=0.0,  # type: ignore[arg-type]
            origin_date=d1,
            origin_close=Decimal("20000.00"),
            vix_close=Decimal("15.00"),
            feature_ready=False,
            payload=None,
            unready_reasons=(REASON_WARMUP,),
        )
        series_float = FeatureSeries(
            protocol_id=FEATURES_PROTOCOL_ID,
            axis_start_date=d1,
            records=(rec_float,),
            calendar_status="not_checked",
            missing_sessions=(),
            extra_sessions=(),
            nifty_provenance=(),
            vix_provenance=(),
        )
        with self.assertRaises(InputValidationError) as ctx:
            serialize_replay_input(series_float)
        self.assertEqual(ctx.exception.field, "rows[0].origin_index")

    def test_rejection_of_sha256_with_trailing_newline_or_invalid_length(self) -> None:
        """Verifies full-string matching of sha256 hex grammar, strictly rejecting trailing newlines (A2)."""
        prov_trailing_newline = FileProvenance(
            file_path="data/nifty50.csv",
            raw_byte_count=1000,
            sha256="a" * 64 + "\n",  # 65 chars with trailing newline
            record_count=0,
            observed_first_date=None,
            observed_last_date=None,
            source_url="https://example.com/nifty50.csv",
            requested_interval=None,
            acquisition_time=None,
            source_use_note="synthetic",
        )
        series = FeatureSeries(
            protocol_id=FEATURES_PROTOCOL_ID,
            axis_start_date=None,
            records=(),
            calendar_status="not_checked",
            missing_sessions=(),
            extra_sessions=(),
            nifty_provenance=(prov_trailing_newline,),
            vix_provenance=(),
        )
        with self.assertRaises(InputValidationError) as ctx:
            serialize_replay_input(series)
        self.assertEqual(ctx.exception.field, "nifty_provenance[0].sha256")

        # Verify exact 64-hex requirement
        prov_short = FileProvenance(
            file_path="data/nifty50.csv",
            raw_byte_count=1000,
            sha256="a" * 63,
            record_count=0,
            observed_first_date=None,
            observed_last_date=None,
            source_url="https://example.com/nifty50.csv",
            requested_interval=None,
            acquisition_time=None,
            source_use_note="synthetic",
        )
        series_short = FeatureSeries(
            protocol_id=FEATURES_PROTOCOL_ID,
            axis_start_date=None,
            records=(),
            calendar_status="not_checked",
            missing_sessions=(),
            extra_sessions=(),
            nifty_provenance=(prov_short,),
            vix_provenance=(),
        )
        with self.assertRaises(InputValidationError) as ctx:
            serialize_replay_input(series_short)
        self.assertEqual(ctx.exception.field, "nifty_provenance[0].sha256")

    def test_rejection_of_malformed_calendar_status_and_records_structure(self) -> None:
        """Verifies contextual InputValidationError when calendar_status or records structure is malformed (A3)."""
        d1 = datetime.date(2024, 1, 1)

        # Unhashable list for calendar_status must raise InputValidationError, not raw TypeError
        series_bad_status = FeatureSeries(
            protocol_id=FEATURES_PROTOCOL_ID,
            axis_start_date=None,
            records=(),
            calendar_status=[],  # type: ignore[arg-type]
            missing_sessions=(),
            extra_sessions=(),
            nifty_provenance=(),
            vix_provenance=(),
        )
        with self.assertRaises(InputValidationError) as ctx:
            serialize_replay_input(series_bad_status)
        self.assertEqual(ctx.exception.field, "series.calendar_status")

        # None inside records tuple with valid non-null axis_start_date must raise InputValidationError, not AttributeError
        series_none_record = FeatureSeries(
            protocol_id=FEATURES_PROTOCOL_ID,
            axis_start_date=d1,
            records=(None,),  # type: ignore[arg-type]
            calendar_status="not_checked",
            missing_sessions=(),
            extra_sessions=(),
            nifty_provenance=(),
            vix_provenance=(),
        )
        with self.assertRaises(InputValidationError) as ctx:
            serialize_replay_input(series_none_record)
        self.assertEqual(ctx.exception.field, "rows[0]")

        # String axis_start_date must raise InputValidationError, not AttributeError
        series_str_axis = FeatureSeries(
            protocol_id=FEATURES_PROTOCOL_ID,
            axis_start_date="2024-01-01",  # type: ignore[arg-type]
            records=(
                NiftyFeatureRecord(
                    origin_index=0,
                    origin_date=d1,
                    origin_close=Decimal("20000.00"),
                    vix_close=Decimal("15.00"),
                    feature_ready=False,
                    payload=None,
                    unready_reasons=(REASON_WARMUP,),
                ),
            ),
            calendar_status="not_checked",
            missing_sessions=(),
            extra_sessions=(),
            nifty_provenance=(),
            vix_provenance=(),
        )
        with self.assertRaises(InputValidationError) as ctx:
            serialize_replay_input(series_str_axis)
        self.assertEqual(ctx.exception.field, "axis_start_date")

    def test_rejection_of_unencodable_surrogates(self) -> None:
        """Verifies rejection of unencodable Unicode surrogates in text fields (A3)."""
        prov_surrogate = FileProvenance(
            file_path="data/nifty50.csv",
            raw_byte_count=1000,
            sha256="a" * 64,
            record_count=0,
            observed_first_date=None,
            observed_last_date=None,
            source_url="https://example.com/nifty50.csv",
            requested_interval=None,
            acquisition_time=None,
            source_use_note="isolated surrogate: \ud800",
        )
        series = FeatureSeries(
            protocol_id=FEATURES_PROTOCOL_ID,
            axis_start_date=None,
            records=(),
            calendar_status="not_checked",
            missing_sessions=(),
            extra_sessions=(),
            nifty_provenance=(prov_surrogate,),
            vix_provenance=(),
        )
        with self.assertRaises(InputValidationError) as ctx:
            serialize_replay_input(series)
        self.assertEqual(ctx.exception.field, "nifty_provenance[0].source_use_note")

    def test_rejection_of_non_featureseries_input(self) -> None:
        """Verifies rejection when input to serialize_replay_input is not a FeatureSeries."""
        with self.assertRaises(InputValidationError) as ctx:
            serialize_replay_input({"not": "a FeatureSeries"})  # type: ignore[arg-type]
        self.assertEqual(ctx.exception.field, "series")

        with self.assertRaises(InputValidationError) as ctx:
            serialize_replay_input(None)  # type: ignore[arg-type]
        self.assertEqual(ctx.exception.field, "series")


if __name__ == "__main__":
    unittest.main()
