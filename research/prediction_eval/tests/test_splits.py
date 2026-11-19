"""
Unit tests for Prediction Evaluation Chronological Splits Foundation.

Validates:
1. Discriminating synthetic acceptance fixture (N=480, D=260, T=360, missing VIX at 225/270):
   - Independent integer oracles for train (39), development (79), refit (138), and test (100).
   - Purge semantics: origin 239 retained in train, 240 purged from train yet refit-eligible;
     origin 339 retained in development, 340 purged from development and refit.
   - Complete partition audit covering all 480 origins with honest exclusion reasons.
2. Missing VIX at boundaries (D and T) and intermediate sessions:
   - Cutoff indices remain strictly unchanged (no shifting to next ready session).
   - Positional session horizon remains unchanged by missing intermediate VIX.
3. Input validation and contextual failure handling with stable field reporting (test_03):
   - Off-axis dates, datetime instead of date, D<=0, D==T and D>T cuts, empty series.
     T>=N cannot follow a successful date lookup, so off-axis dates cover it.
   - Calendar status (not_checked, mismatch), discrepancy metadata and series roles.
   - Unequal series lengths.
   - Defensive validation bypass via object.__setattr__ for maturity endpoints,
     unready reason order, None records and class labels.
4. Short valid series with honest empty pools:
   - Empty retained index tuples when all observations are unready/unknown.
   - Overlapping base exclusion reasons visible in deterministic order.
5. Future perturbation and class-blind selection:
   - Changing future prices/VIX at or after T leaves pre-test pools bit-for-bit identical.
   - Modifying outcome class labels leaves all index pools completely identical.
6. Immutability, frozen records, and repeated-call equality.
7. Module import and source audit: zero forbidden network, model, or dataframe imports.
8. Planner-boundary negatives on isolated copies of one valid fixture (test_08): record
   containers, indices, date agreement/order/uniqueness, Close agreement and validity,
   axis_start_date, readiness/payload/VIX and maturity status/index/tail, each asserting
   the responsible field and the failing row.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import copy
import datetime
from decimal import Decimal
import hashlib
import os
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
    FeatureSeries,
    NiftyFeatureRecord,
    PredictorPayload,
    PROTOCOL_ID,
    WARMUP_ORIGIN_INDEX,
    REASON_WARMUP,
    REASON_MISSING_VIX,
    compute_nifty_features,
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
    compute_twenty_session_outcomes,
)
from research.prediction_eval.splits import (
    PARTITION_DEVELOPMENT,
    PARTITION_TEST,
    PARTITION_TRAIN,
    REASON_LABEL_CROSSES_DEVELOPMENT,
    REASON_LABEL_CROSSES_TEST,
    REASON_UNKNOWN_OUTCOME,
    OriginSplitDecision,
    SplitPlan,
    build_split_plan,
)


class TestPredictionEvalSplits(unittest.TestCase):
    """Test suite for research/prediction_eval/splits.py."""

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

    def _generate_nonuniform_dates(
        self,
        count: int,
        start_date: datetime.date = datetime.date(2020, 1, 6),
    ) -> List[datetime.date]:
        """
        Generates strictly increasing dates with nonuniform spacing (skipping Sundays,
        occasional synthetic Saturday sessions, and multi-day holiday gaps).
        """
        dates: List[datetime.date] = []
        curr = start_date
        while len(dates) < count:
            weekday = curr.weekday()
            # Insert a synthetic Saturday session at index 50
            if len(dates) == 50 and weekday == 5:
                dates.append(curr)
            # Insert a 4-day leap at index 150
            elif len(dates) == 150:
                curr += datetime.timedelta(days=4)
                if curr.weekday() < 5:
                    dates.append(curr)
            elif weekday < 5:  # Monday to Friday
                dates.append(curr)
            curr += datetime.timedelta(days=1)
        return dates

    def _build_aligned_synthetic_fixture(
        self,
        n_origins: int,
        missing_vix_indices: Sequence[int] = (),
        prefix: str = "fixture",
    ) -> Tuple[FeatureSeries, OutcomeSeries, List[datetime.date]]:
        """
        Constructs an aligned FeatureSeries and OutcomeSeries from synthetic CSVs.
        Uses actual load_series -> align_pair -> compute_nifty_features and
        compute_twenty_session_outcomes on the same Nifty series.
        """
        dates = self._generate_nonuniform_dates(n_origins)
        missing_vix_set = set(missing_vix_indices)

        # Nifty CSV: upward trend with slight variation
        nifty_lines = ["Date,Close"]
        for idx, d in enumerate(dates):
            # Closes: 10000.00 + idx * 5.00
            nifty_lines.append(f"{d.strftime('%d-%b-%Y')},{10000 + idx * 5}.00")
        n_file = self._write_csv(f"{prefix}_nifty.csv", "\n".join(nifty_lines) + "\n")

        # VIX CSV: missing rows at declared indices
        vix_lines = ["Date,Close"]
        for idx, d in enumerate(dates):
            if idx in missing_vix_set:
                continue
            vix_lines.append(f"{d.strftime('%d-%b-%Y')},18.50")
        v_file = self._write_csv(f"{prefix}_vix.csv", "\n".join(vix_lines) + "\n")

        n_series = load_series("nifty50_price_index", n_file)
        v_series = load_series("india_vix", v_file)

        # Explicit expected_sessions matches Nifty dates exactly
        pair = align_pair(n_series, v_series, expected_sessions=dates)
        features = compute_nifty_features(pair)
        outcomes = compute_twenty_session_outcomes(n_series)

        return features, outcomes, dates

    @staticmethod
    def _force_frozen_fields(record, **fields):
        """
        Test-only defensive bypass: copy an initially valid frozen record, then force
        fields that its own constructor would reject, so the case reaches build_split_plan.
        The shared fixture record is never modified.
        """
        clone = replace(record)
        for name, value in fields.items():
            object.__setattr__(clone, name, value)
        return clone

    def test_01_synthetic_acceptance_example_and_integer_oracles(self) -> None:
        """
        Validates the primary acceptance fixture from requirements.md:
        - N=480, D=260, T=360, missing VIX only at origins 225 and 270.
        - Nonuniform calendar spacing distinguishes positions from calendar days.
        - Independent integer oracles:
          * train_indices: 200..239 inclusive except 225 -> 39 rows.
          * development_indices: 260..339 inclusive except 270 -> 79 rows.
          * refit_indices: 200..339 inclusive except 225/270 -> 138 rows.
          * test_indices: 360..459 inclusive -> 100 rows.
          * warmup: 0..199 (200 rows).
          * missing VIX: 225, 270 (2 rows).
          * unknown tail: 460..479 (20 rows).
          * train purge: 240..259 (20 rows).
          * development purge: 340..359 (20 rows).
          * Total retained (39 + 79 + 100 = 218) + excluded (262) = 480 rows.
        - Boundary purge transitions:
          * origin 239 matures at 259, stays in train.
          * origin 240 matures at 260, purged from train yet refit-eligible.
          * origin 339 matures at 359, stays in development.
          * origin 340 matures at 360, excluded from development and refit.
        """
        N = 480
        D = 260
        T = 360
        features, outcomes, dates = self._build_aligned_synthetic_fixture(
            n_origins=N,
            missing_vix_indices=(225, 270),
            prefix="accept_480",
        )

        dev_start = dates[D]
        test_start = dates[T]

        plan = build_split_plan(
            features,
            outcomes,
            development_start=dev_start,
            test_start=test_start,
        )

        # 1. Independent integer oracle expectations
        expected_train = tuple(i for i in range(200, 240) if i != 225)
        expected_dev = tuple(i for i in range(260, 340) if i != 270)
        expected_refit = tuple(i for i in range(200, 340) if i not in (225, 270))
        expected_test = tuple(range(360, 460))

        self.assertEqual(len(expected_train), 39)
        self.assertEqual(len(expected_dev), 79)
        self.assertEqual(len(expected_refit), 138)
        self.assertEqual(len(expected_test), 100)

        # Assert exact agreement with plan
        self.assertEqual(plan.train_indices, expected_train)
        self.assertEqual(plan.development_indices, expected_dev)
        self.assertEqual(plan.refit_indices, expected_refit)
        self.assertEqual(plan.test_indices, expected_test)

        self.assertEqual(plan.development_start, dev_start)
        self.assertEqual(plan.test_start, test_start)
        self.assertEqual(plan.development_start_index, D)
        self.assertEqual(plan.test_start_index, T)
        self.assertEqual(plan.development_index, D)
        self.assertEqual(plan.test_index, T)

        # 2. Boundary purge transitions
        # Origin 239 matures at 259 (< 260) -> kept in train
        dec_239 = plan.decisions[239]
        self.assertEqual(dec_239.partition, PARTITION_TRAIN)
        self.assertEqual(dec_239.exclusion_reasons, ())
        self.assertTrue(dec_239.in_refit)

        # Origin 240 matures at 260 (== D, NOT < D) -> purged from train yet in_refit=True
        dec_240 = plan.decisions[240]
        self.assertEqual(dec_240.partition, PARTITION_TRAIN)
        self.assertEqual(dec_240.exclusion_reasons, (REASON_LABEL_CROSSES_DEVELOPMENT,))
        self.assertTrue(dec_240.in_refit)
        self.assertNotIn(240, plan.train_indices)
        self.assertIn(240, plan.refit_indices)

        # Origin 339 matures at 359 (< 360) -> kept in development, in_refit=True
        dec_339 = plan.decisions[339]
        self.assertEqual(dec_339.partition, PARTITION_DEVELOPMENT)
        self.assertEqual(dec_339.exclusion_reasons, ())
        self.assertTrue(dec_339.in_refit)

        # Origin 340 matures at 360 (== T, NOT < T) -> purged from dev and NOT in refit
        dec_340 = plan.decisions[340]
        self.assertEqual(dec_340.partition, PARTITION_DEVELOPMENT)
        self.assertEqual(dec_340.exclusion_reasons, (REASON_LABEL_CROSSES_TEST,))
        self.assertFalse(dec_340.in_refit)
        self.assertNotIn(340, plan.development_indices)
        self.assertNotIn(340, plan.refit_indices)

        # 3. Complete audit across all 480 decisions
        self.assertEqual(len(plan.decisions), 480)
        retained_count = 0
        excluded_count = 0

        for i, dec in enumerate(plan.decisions):
            self.assertEqual(dec.origin_index, i)
            self.assertEqual(dec.origin_date, dates[i])

            if len(dec.exclusion_reasons) == 0:
                retained_count += 1
            else:
                excluded_count += 1

            # Specific reason assertions by zone
            if i < 200:
                self.assertEqual(dec.partition, PARTITION_TRAIN)
                self.assertEqual(dec.exclusion_reasons, (REASON_WARMUP,))
                self.assertFalse(dec.in_refit)
            elif i == 225:
                self.assertEqual(dec.partition, PARTITION_TRAIN)
                self.assertEqual(dec.exclusion_reasons, (REASON_MISSING_VIX,))
                self.assertFalse(dec.in_refit)
            elif 240 <= i < 260:
                self.assertEqual(dec.partition, PARTITION_TRAIN)
                self.assertEqual(dec.exclusion_reasons, (REASON_LABEL_CROSSES_DEVELOPMENT,))
                self.assertTrue(dec.in_refit)
            elif i == 270:
                self.assertEqual(dec.partition, PARTITION_DEVELOPMENT)
                self.assertEqual(dec.exclusion_reasons, (REASON_MISSING_VIX,))
                self.assertFalse(dec.in_refit)
            elif 340 <= i < 360:
                self.assertEqual(dec.partition, PARTITION_DEVELOPMENT)
                self.assertEqual(dec.exclusion_reasons, (REASON_LABEL_CROSSES_TEST,))
                self.assertFalse(dec.in_refit)
            elif 460 <= i < 480:
                self.assertEqual(dec.partition, PARTITION_TEST)
                self.assertEqual(dec.exclusion_reasons, (REASON_UNKNOWN_OUTCOME,))
                self.assertFalse(dec.in_refit)

        self.assertEqual(retained_count, 218)
        self.assertEqual(excluded_count, 262)
        self.assertEqual(retained_count + excluded_count, 480)

        # Disjoint coverage: retained train + dev + test plus excluded covers all 480
        all_retained = set(plan.train_indices) | set(plan.development_indices) | set(plan.test_indices)
        self.assertEqual(len(all_retained), 218)
        self.assertEqual(len(set(plan.train_indices)), 39)
        self.assertEqual(len(set(plan.development_indices)), 79)
        self.assertEqual(len(set(plan.test_indices)), 100)
        self.assertTrue(set(plan.train_indices).isdisjoint(set(plan.development_indices)))
        self.assertTrue(set(plan.development_indices).isdisjoint(set(plan.test_indices)))
        self.assertTrue(set(plan.train_indices).isdisjoint(set(plan.test_indices)))

    def test_02_missing_vix_at_boundaries_and_intermediate(self) -> None:
        """
        Validates:
        - Missing VIX at development_start (D=260) and test_start (T=360) leaves
          cutoff indices unchanged (D remains 260, T remains 360).
        - No shifting to the first eligible date.
        - Origins 260 and 360 are excluded with reason ('missing_vix',).
        - Missing intermediate VIX (e.g. at origin 280) never changes the
          20-position outcome horizon or subsequent index association.
        """
        N = 480
        D = 260
        T = 360
        # Omit VIX at D (260), T (360), and intermediate 280
        features, outcomes, dates = self._build_aligned_synthetic_fixture(
            n_origins=N,
            missing_vix_indices=(260, 280, 360),
            prefix="vix_at_bounds",
        )

        plan = build_split_plan(
            features,
            outcomes,
            development_start=dates[D],
            test_start=dates[T],
        )

        # Cutoffs remain exactly at D and T
        self.assertEqual(plan.development_start_index, 260)
        self.assertEqual(plan.test_start_index, 360)

        # Origin 260 is at development boundary, excluded due to missing_vix
        dec_260 = plan.decisions[260]
        self.assertEqual(dec_260.partition, PARTITION_DEVELOPMENT)
        self.assertEqual(dec_260.exclusion_reasons, (REASON_MISSING_VIX,))
        self.assertNotIn(260, plan.development_indices)
        self.assertNotIn(260, plan.refit_indices)

        # Origin 360 is at test boundary, excluded due to missing_vix
        dec_360 = plan.decisions[360]
        self.assertEqual(dec_360.partition, PARTITION_TEST)
        self.assertEqual(dec_360.exclusion_reasons, (REASON_MISSING_VIX,))
        self.assertNotIn(360, plan.test_indices)

        # Origin 280 is an intermediate missing VIX: excluded from dev and refit
        dec_280 = plan.decisions[280]
        self.assertEqual(dec_280.partition, PARTITION_DEVELOPMENT)
        self.assertEqual(dec_280.exclusion_reasons, (REASON_MISSING_VIX,))
        self.assertNotIn(280, plan.development_indices)
        self.assertNotIn(280, plan.refit_indices)

        # Outcome at 280 still has exact 20-position maturity index 300
        o_280 = outcomes[280]
        self.assertEqual(o_280.maturity_index, 300)
        self.assertEqual(o_280.maturity_date, dates[300])

    def test_03_input_validation_and_contextual_failures(self) -> None:
        """
        Validates strict contextual error handling reporting exact responsible field names:
        - dates absent from axis (development_start, test_start)
        - datetime.datetime instead of datetime.date
        - boundary ordering and edge failures: D <= 0, D == T, D > T, empty series
          (T >= N cannot follow a successful date lookup; absent dates cover it)
        - calendar status not_checked and mismatch, non-empty discrepancies
        - series role mismatches (protocol_id, series_id)
        - unequal series lengths
        - defensive validation testing via object.__setattr__ bypass for maturity
          endpoints, unready reason order, None records and class labels.
        Axis, index, Close, readiness, payload, VIX and maturity-state negatives are in test_08.
        """
        N = 300
        features, outcomes, dates = self._build_aligned_synthetic_fixture(
            n_origins=N,
            prefix="val_suite",
        )
        d_valid = dates[100]
        t_valid = dates[200]

        # 1. Missing dates on axis
        off_axis_date = datetime.date(2010, 1, 1)
        with self.assertRaises(InputValidationError) as ctx:
            build_split_plan(features, outcomes, development_start=off_axis_date, test_start=t_valid)
        self.assertEqual(ctx.exception.field, "development_start")

        with self.assertRaises(InputValidationError) as ctx:
            build_split_plan(features, outcomes, development_start=d_valid, test_start=off_axis_date)
        self.assertEqual(ctx.exception.field, "test_start")

        # 2. datetime.datetime instead of datetime.date
        d_datetime = datetime.datetime(d_valid.year, d_valid.month, d_valid.day, 9, 15)
        with self.assertRaises(InputValidationError) as ctx:
            build_split_plan(features, outcomes, development_start=d_datetime, test_start=t_valid)  # type: ignore[arg-type]
        self.assertEqual(ctx.exception.field, "development_start")

        t_datetime = datetime.datetime(t_valid.year, t_valid.month, t_valid.day, 9, 15)
        with self.assertRaises(InputValidationError) as ctx:
            build_split_plan(features, outcomes, development_start=d_valid, test_start=t_datetime)  # type: ignore[arg-type]
        self.assertEqual(ctx.exception.field, "test_start")

        # 3. Boundary ordering and edge cuts: D <= 0 and D >= T
        # D == 0 (dates[0])
        with self.assertRaises(InputValidationError) as ctx:
            build_split_plan(features, outcomes, development_start=dates[0], test_start=t_valid)
        self.assertEqual(ctx.exception.field, "development_start")

        # D == T
        with self.assertRaises(InputValidationError) as ctx:
            build_split_plan(features, outcomes, development_start=dates[150], test_start=dates[150])
        self.assertEqual(ctx.exception.field, "development_start")

        # D > T
        with self.assertRaises(InputValidationError) as ctx:
            build_split_plan(features, outcomes, development_start=dates[200], test_start=dates[100])
        self.assertEqual(ctx.exception.field, "development_start")

        # T >= N cannot follow a successful date lookup (member dates map to 0..N-1), so the
        # off-axis cases above cover it; T = N-1 is a valid one-origin test partition.
        # An empty series fails at the boundary step:
        empty_pair = align_pair(
            load_series("nifty50_price_index", self._write_csv("empty_n.csv", "Date,Close\n01-Jan-2024,100\n")),
            load_series("india_vix", self._write_csv("empty_v.csv", "Date,Close\n01-Jan-2024,15\n")),
        )
        empty_features = FeatureSeries(
            protocol_id=PROTOCOL_ID,
            axis_start_date=None,
            records=(),
            calendar_status="matches_supplied_sessions",
            missing_sessions=(),
            extra_sessions=(),
            nifty_provenance=(),
            vix_provenance=(),
        )
        empty_outcomes = OutcomeSeries(series_id="nifty50_price_index", outcomes=())
        with self.assertRaises(InputValidationError) as ctx:
            build_split_plan(empty_features, empty_outcomes, development_start=d_valid, test_start=t_valid)
        self.assertEqual(ctx.exception.field, "development_start")

        # 4. Calendar status prerequisite
        features_not_checked = FeatureSeries(
            protocol_id=PROTOCOL_ID,
            axis_start_date=features.axis_start_date,
            records=features.records,
            calendar_status="not_checked",
            missing_sessions=(),
            extra_sessions=(),
            nifty_provenance=features.nifty_provenance,
            vix_provenance=features.vix_provenance,
        )
        with self.assertRaises(InputValidationError) as ctx:
            build_split_plan(features_not_checked, outcomes, development_start=d_valid, test_start=t_valid)
        self.assertEqual(ctx.exception.field, "calendar_status")

        features_mismatch = FeatureSeries(
            protocol_id=PROTOCOL_ID,
            axis_start_date=features.axis_start_date,
            records=features.records,
            calendar_status="mismatch",
            missing_sessions=(),
            extra_sessions=(),
            nifty_provenance=features.nifty_provenance,
            vix_provenance=features.vix_provenance,
        )
        with self.assertRaises(InputValidationError) as ctx:
            build_split_plan(features_mismatch, outcomes, development_start=d_valid, test_start=t_valid)
        self.assertEqual(ctx.exception.field, "calendar_status")

        # 5. Non-empty discrepancy tuples with matches_supplied_sessions
        features_bad_missing = FeatureSeries(
            protocol_id=PROTOCOL_ID,
            axis_start_date=features.axis_start_date,
            records=features.records,
            calendar_status="matches_supplied_sessions",
            missing_sessions=(dates[0],),
            extra_sessions=(),
            nifty_provenance=features.nifty_provenance,
            vix_provenance=features.vix_provenance,
        )
        with self.assertRaises(InputValidationError) as ctx:
            build_split_plan(features_bad_missing, outcomes, development_start=d_valid, test_start=t_valid)
        self.assertEqual(ctx.exception.field, "missing_sessions")

        features_bad_extra = FeatureSeries(
            protocol_id=PROTOCOL_ID,
            axis_start_date=features.axis_start_date,
            records=features.records,
            calendar_status="matches_supplied_sessions",
            missing_sessions=(),
            extra_sessions=(dates[0],),
            nifty_provenance=features.nifty_provenance,
            vix_provenance=features.vix_provenance,
        )
        with self.assertRaises(InputValidationError) as ctx:
            build_split_plan(features_bad_extra, outcomes, development_start=d_valid, test_start=t_valid)
        self.assertEqual(ctx.exception.field, "extra_sessions")

        # 6. Series protocol and role validation
        features_bad_protocol = FeatureSeries(
            protocol_id="unsupported-protocol-v2",
            axis_start_date=features.axis_start_date,
            records=features.records,
            calendar_status="matches_supplied_sessions",
            missing_sessions=(),
            extra_sessions=(),
            nifty_provenance=features.nifty_provenance,
            vix_provenance=features.vix_provenance,
        )
        with self.assertRaises(InputValidationError) as ctx:
            build_split_plan(features_bad_protocol, outcomes, development_start=d_valid, test_start=t_valid)
        self.assertEqual(ctx.exception.field, "protocol_id")

        outcomes_bad_series = OutcomeSeries(series_id="india_vix", outcomes=outcomes.outcomes)
        with self.assertRaises(InputValidationError) as ctx:
            build_split_plan(features, outcomes_bad_series, development_start=d_valid, test_start=t_valid)
        self.assertEqual(ctx.exception.field, "series_id")

        # 7. Series length mismatch
        outcomes_truncated = OutcomeSeries(series_id="nifty50_price_index", outcomes=outcomes.outcomes[:-5])
        with self.assertRaises(InputValidationError) as ctx:
            build_split_plan(features, outcomes_truncated, development_start=d_valid, test_start=t_valid)
        self.assertEqual(ctx.exception.field, "records")

        # 8. Defensive validation bypass testing:
        # Construct isolated records and mutate fields via object.__setattr__ to bypass
        # dataclass __post_init__ guards, proving splits.py defends its own boundary.

        # A. Maturity date mismatch
        bad_outcomes_list = list(outcomes.outcomes)
        tampered_o = bad_outcomes_list[0]
        # Copy and alter maturity_date to different date
        tampered_copy = TwentySessionOutcome(
            origin_index=0,
            origin_date=tampered_o.origin_date,
            origin_close=tampered_o.origin_close,
            is_mature=True,
            status=STATUS_MATURE,
            maturity_index=20,
            maturity_date=tampered_o.maturity_date,
            maturity_close=tampered_o.maturity_close,
            outcome_class=tampered_o.outcome_class,
        )
        object.__setattr__(tampered_copy, "maturity_date", dates[25])  # Date 25 instead of 20
        bad_outcomes_list[0] = tampered_copy
        bad_outcomes_series = OutcomeSeries(series_id="nifty50_price_index", outcomes=tuple(bad_outcomes_list))
        with self.assertRaises(InputValidationError) as ctx:
            build_split_plan(features, bad_outcomes_series, development_start=d_valid, test_start=t_valid)
        self.assertEqual(ctx.exception.field, "maturity_date")

        # B. Maturity Close mismatch
        tampered_close_copy = TwentySessionOutcome(
            origin_index=0,
            origin_date=tampered_o.origin_date,
            origin_close=tampered_o.origin_close,
            is_mature=True,
            status=STATUS_MATURE,
            maturity_index=20,
            maturity_date=tampered_o.maturity_date,
            maturity_close=tampered_o.maturity_close,
            outcome_class=tampered_o.outcome_class,
        )
        object.__setattr__(tampered_close_copy, "maturity_close", Decimal("999999.00"))
        bad_outcomes_list[0] = tampered_close_copy
        bad_close_series = OutcomeSeries(series_id="nifty50_price_index", outcomes=tuple(bad_outcomes_list))
        with self.assertRaises(InputValidationError) as ctx:
            build_split_plan(features, bad_close_series, development_start=d_valid, test_start=t_valid)
        self.assertEqual(ctx.exception.field, "maturity_close")

        # C. Feature unready_reasons order inconsistency
        bad_feat_list = list(features.records)
        tampered_f = bad_feat_list[0]
        tampered_f_copy = NiftyFeatureRecord(
            origin_index=0,
            origin_date=tampered_f.origin_date,
            origin_close=tampered_f.origin_close,
            vix_close=tampered_f.vix_close,
            feature_ready=False,
            payload=None,
            unready_reasons=("warmup",),
        )
        # Force invalid reason order or unknown reason
        object.__setattr__(tampered_f_copy, "unready_reasons", ("missing_vix", "warmup"))
        bad_feat_list[0] = tampered_f_copy
        bad_feat_series = FeatureSeries(
            protocol_id=PROTOCOL_ID,
            axis_start_date=features.axis_start_date,
            records=tuple(bad_feat_list),
            calendar_status="matches_supplied_sessions",
            missing_sessions=(),
            extra_sessions=(),
            nifty_provenance=features.nifty_provenance,
            vix_provenance=features.vix_provenance,
        )
        with self.assertRaises(InputValidationError) as ctx:
            build_split_plan(bad_feat_series, outcomes, development_start=d_valid, test_start=t_valid)
        self.assertEqual(ctx.exception.field, "unready_reasons")

        # D. A1.1: Feature series with first record None dereferenced before record guard
        bad_feat_first_none = FeatureSeries(
            protocol_id=PROTOCOL_ID,
            axis_start_date=features.axis_start_date,
            records=(None,) + tuple(features.records[1:10]),
            calendar_status="matches_supplied_sessions",
            missing_sessions=(),
            extra_sessions=(),
            nifty_provenance=features.nifty_provenance,
            vix_provenance=features.vix_provenance,
        )
        bad_outcomes_sub = OutcomeSeries(
            series_id="nifty50_price_index",
            outcomes=tuple(outcomes.outcomes[:10]),
        )
        with self.assertRaises(InputValidationError) as ctx:
            build_split_plan(bad_feat_first_none, bad_outcomes_sub, development_start=d_valid, test_start=t_valid)
        self.assertEqual(ctx.exception.field, "records")

        # E. A1.2: Future feature record None at maturity endpoint dereferenced before its guard
        short_feats, short_outs, short_dates = self._build_aligned_synthetic_fixture(
            n_origins=25,
            prefix="a1_fut_none",
        )
        bad_feat_recs = list(short_feats.records)
        bad_feat_recs[20] = None  # Future record 20 is None
        bad_feat_fut_none = FeatureSeries(
            protocol_id=PROTOCOL_ID,
            axis_start_date=short_feats.axis_start_date,
            records=tuple(bad_feat_recs),
            calendar_status="matches_supplied_sessions",
            missing_sessions=(),
            extra_sessions=(),
            nifty_provenance=short_feats.nifty_provenance,
            vix_provenance=short_feats.vix_provenance,
        )
        with self.assertRaises(InputValidationError) as ctx:
            build_split_plan(bad_feat_fut_none, short_outs, development_start=short_dates[5], test_start=short_dates[15])
        self.assertEqual(ctx.exception.field, "records")

        # F. A1.3: Unhashable outcome_class (e.g. list) raises InputValidationError, not TypeError
        bad_outcomes_list_class = list(outcomes.outcomes)
        tampered_class_copy = TwentySessionOutcome(
            origin_index=0,
            origin_date=tampered_o.origin_date,
            origin_close=tampered_o.origin_close,
            is_mature=True,
            status=STATUS_MATURE,
            maturity_index=20,
            maturity_date=tampered_o.maturity_date,
            maturity_close=tampered_o.maturity_close,
            outcome_class=tampered_o.outcome_class,
        )
        object.__setattr__(tampered_class_copy, "outcome_class", ["bull"])
        bad_outcomes_list_class[0] = tampered_class_copy
        bad_class_series = OutcomeSeries(series_id="nifty50_price_index", outcomes=tuple(bad_outcomes_list_class))
        with self.assertRaises(InputValidationError) as ctx:
            build_split_plan(features, bad_class_series, development_start=d_valid, test_start=t_valid)
        self.assertEqual(ctx.exception.field, "outcome_class")

    def test_04_short_series_and_honest_empty_pools(self) -> None:
        """
        Validates behavior on a short series (N=25 < 200 warmup threshold):
        - Origins 0..4 have observed maturities at indices 20..24 < 25 (only 'warmup' exclusion).
        - Origins 5..24 have unknown outcomes with i + 20 >= 25 (both 'warmup' and 'unknown_outcome' exclusions).
        - SplitPlan returns honest empty index tuples:
          * train_indices = ()
          * development_indices = ()
          * refit_indices = ()
          * test_indices = ()
        - Overlapping base exclusion reasons visible in deterministic order:
          ('warmup', 'unknown_outcome').
        - Origin decisions are populated and preserved in original order.
        """
        N = 25
        features, outcomes, dates = self._build_aligned_synthetic_fixture(
            n_origins=N,
            prefix="short_25",
        )
        D = 5
        T = 15

        plan = build_split_plan(
            features,
            outcomes,
            development_start=dates[D],
            test_start=dates[T],
        )

        self.assertEqual(plan.train_indices, ())
        self.assertEqual(plan.development_indices, ())
        self.assertEqual(plan.refit_indices, ())
        self.assertEqual(plan.test_indices, ())

        self.assertEqual(len(plan.decisions), 25)
        for i, dec in enumerate(plan.decisions):
            self.assertEqual(dec.origin_index, i)
            self.assertEqual(dec.origin_date, dates[i])
            self.assertFalse(dec.in_refit)
            if i < 5:
                # Origins 0..4 mature at indices 20..24 < 25, so outcome is mature; only warmup applies
                self.assertEqual(dec.exclusion_reasons, (REASON_WARMUP,))
            else:
                # Origins 5..24 have i + 20 >= 25, so both warmup and unknown_outcome apply
                self.assertEqual(dec.exclusion_reasons, (REASON_WARMUP, REASON_UNKNOWN_OUTCOME))
            if i < D:
                self.assertEqual(dec.partition, PARTITION_TRAIN)
            elif i < T:
                self.assertEqual(dec.partition, PARTITION_DEVELOPMENT)
            else:
                self.assertEqual(dec.partition, PARTITION_TEST)

        # 2. Overlapping base reasons test with all three base exclusions:
        # Build a 20-origin series (all unknown tail) with missing VIX at origin 10
        feat20, out20, dates20 = self._build_aligned_synthetic_fixture(
            n_origins=20,
            missing_vix_indices=(10,),
            prefix="short_20_overlap",
        )
        plan20 = build_split_plan(
            feat20,
            out20,
            development_start=dates20[5],
            test_start=dates20[15],
        )
        # Origin 10 has warmup, missing_vix, and unknown_outcome in exact order
        dec10 = plan20.decisions[10]
        self.assertEqual(dec10.exclusion_reasons, (REASON_WARMUP, REASON_MISSING_VIX, REASON_UNKNOWN_OUTCOME))
        self.assertFalse(dec10.in_refit)


    def test_05_future_perturbation_and_class_blind_selection(self) -> None:
        """
        Validates temporal safety and class independence:
        1. Future perturbation at or after test_start (T=320) in a 400-origin series:
           - Earlier pre-test index pools (train_indices, development_indices, refit_indices)
             are bit-for-bit identical to the unperturbed baseline.
           - Pre-test feature and label values remain identical.
           - An outcome crossing T may change its future endpoint price but stays excluded.
        2. Class-blind selection:
           - Overwriting outcome classes directly across all origins (e.g. all BULL or all BEAR)
             leaves every single index pool (train, development, refit, test) 100% identical.
        """
        N = 400
        D = 240
        T = 320

        # Run A: Baseline series
        features_a, outcomes_a, dates_a = self._build_aligned_synthetic_fixture(
            n_origins=N,
            prefix="future_base",
        )
        plan_a = build_split_plan(
            features_a,
            outcomes_a,
            development_start=dates_a[D],
            test_start=dates_a[T],
        )

        # Run B: Perturb prices and VIX at and after T (indices 320..399)
        # Create perturbed Nifty and VIX CSVs
        nifty_lines_b = ["Date,Close"]
        for idx, d in enumerate(dates_a):
            if idx < T:
                c = 10000 + idx * 5
            else:
                # 50% crash and wild volatility in the future
                c = (10000 + idx * 5) // 2
            nifty_lines_b.append(f"{d.strftime('%d-%b-%Y')},{c}.00")
        f_b = self._write_csv("future_pert_nifty.csv", "\n".join(nifty_lines_b) + "\n")

        vix_lines_b = ["Date,Close"]
        for idx, d in enumerate(dates_a):
            v_c = "18.50" if idx < T else "45.00"
            vix_lines_b.append(f"{d.strftime('%d-%b-%Y')},{v_c}")
        v_b = self._write_csv("future_pert_vix.csv", "\n".join(vix_lines_b) + "\n")

        n_ser_b = load_series("nifty50_price_index", f_b)
        v_ser_b = load_series("india_vix", v_b)
        pair_b = align_pair(n_ser_b, v_ser_b, expected_sessions=dates_a)
        features_b = compute_nifty_features(pair_b)
        outcomes_b = compute_twenty_session_outcomes(n_ser_b)

        plan_b = build_split_plan(
            features_b,
            outcomes_b,
            development_start=dates_a[D],
            test_start=dates_a[T],
        )

        # Pre-test index pools MUST be bit-for-bit identical
        self.assertEqual(plan_a.train_indices, plan_b.train_indices)
        self.assertEqual(plan_a.development_indices, plan_b.development_indices)
        self.assertEqual(plan_a.refit_indices, plan_b.refit_indices)

        # Pre-test decisions MUST match
        for idx in range(T):
            dec_a = plan_a.decisions[idx]
            dec_b = plan_b.decisions[idx]
            self.assertEqual(dec_a.partition, dec_b.partition)
            self.assertEqual(dec_a.exclusion_reasons, dec_b.exclusion_reasons)
            self.assertEqual(dec_a.in_refit, dec_b.in_refit)

        # Notice: at origin 310, maturity is 310 + 20 = 330 (which is in the perturbed future)
        # Outcome label at 310 changed from Bull in A to Bear in B
        self.assertNotEqual(outcomes_a[310].outcome_class, outcomes_b[310].outcome_class)
        # Yet both stay excluded from development with reason 'label_crosses_test_boundary'
        self.assertEqual(plan_a.decisions[310].exclusion_reasons, (REASON_LABEL_CROSSES_TEST,))
        self.assertEqual(plan_b.decisions[310].exclusion_reasons, (REASON_LABEL_CROSSES_TEST,))
        self.assertFalse(plan_a.decisions[310].in_refit)
        self.assertFalse(plan_b.decisions[310].in_refit)

        # Selected pre-test predictor payload and label values MUST be bit-for-bit identical
        for k in plan_a.refit_indices:
            self.assertEqual(features_a.records[k].payload, features_b.records[k].payload)
            self.assertEqual(features_a.records[k].origin_close, features_b.records[k].origin_close)
            self.assertEqual(features_a.records[k].vix_close, features_b.records[k].vix_close)
            self.assertEqual(outcomes_a.outcomes[k].outcome_class, outcomes_b.outcomes[k].outcome_class)
            self.assertEqual(outcomes_a.outcomes[k].maturity_close, outcomes_b.outcomes[k].maturity_close)
            self.assertEqual(outcomes_a.outcomes[k].maturity_date, outcomes_b.outcomes[k].maturity_date)

        # Part 2: Class-blind selection
        # Overwrite all mature outcome classes to BEAR in a tampered copy
        tampered_outcomes = []
        for o in outcomes_a.outcomes:
            if o.is_mature:
                tampered_o = TwentySessionOutcome(
                    origin_index=o.origin_index,
                    origin_date=o.origin_date,
                    origin_close=o.origin_close,
                    is_mature=True,
                    status=STATUS_MATURE,
                    maturity_index=o.maturity_index,
                    maturity_date=o.maturity_date,
                    maturity_close=o.maturity_close,
                    outcome_class=OUTCOME_CLASS_BEAR,
                )
                tampered_outcomes.append(tampered_o)
            else:
                tampered_outcomes.append(o)

        outcomes_all_bear = OutcomeSeries(
            series_id="nifty50_price_index",
            outcomes=tuple(tampered_outcomes),
        )

        plan_class_blind = build_split_plan(
            features_a,
            outcomes_all_bear,
            development_start=dates_a[D],
            test_start=dates_a[T],
        )

        # Every single index pool must match 100%
        self.assertEqual(plan_a.train_indices, plan_class_blind.train_indices)
        self.assertEqual(plan_a.development_indices, plan_class_blind.development_indices)
        self.assertEqual(plan_a.refit_indices, plan_class_blind.refit_indices)
        self.assertEqual(plan_a.test_indices, plan_class_blind.test_indices)

    def test_06_immutability_and_equality(self) -> None:
        """
        Validates immutability, frozen records, and equality:
        - Repeated calls with identical inputs produce equal SplitPlan instances.
        - SplitPlan and OriginSplitDecision reject attribute modification.
        - All returned index collections and decisions are immutable tuples.
        - Source FeatureSeries and OutcomeSeries are not modified.
        """
        N = 300
        D = 220
        T = 260
        features, outcomes, dates = self._build_aligned_synthetic_fixture(
            n_origins=N,
            prefix="immutable",
        )

        # S2-A1: Independent complete value snapshots of both input series without object aliasing
        features_snapshot = copy.deepcopy(features)
        outcomes_snapshot = copy.deepcopy(outcomes)
        csv_hashes_before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in self.test_dir.glob("*.csv")}

        # Verify that snapshots are independent distinct instances (no aliasing)
        self.assertIsNot(features_snapshot, features)
        self.assertIsNot(outcomes_snapshot, outcomes)
        self.assertIsNot(features_snapshot.records, features.records)
        self.assertIsNot(outcomes_snapshot.outcomes, outcomes.outcomes)
        self.assertIsNot(features_snapshot.nifty_provenance, features.nifty_provenance)
        self.assertIsNot(features_snapshot.vix_provenance, features.vix_provenance)
        # Deep record and payload independence on ready origin (index 250)
        self.assertIsNot(features_snapshot.records[250], features.records[250])
        self.assertIsNot(features_snapshot.records[250].payload, features.records[250].payload)
        self.assertIsNot(outcomes_snapshot.outcomes[250], outcomes.outcomes[250])

        plan1 = build_split_plan(
            features,
            outcomes,
            development_start=dates[D],
            test_start=dates[T],
        )
        plan2 = build_split_plan(
            features,
            outcomes,
            development_start=dates[D],
            test_start=dates[T],
        )

        # Input and nested record immutability against independent snapshot
        self.assertEqual(features, features_snapshot)
        self.assertEqual(features.protocol_id, features_snapshot.protocol_id)
        self.assertEqual(features.axis_start_date, features_snapshot.axis_start_date)
        self.assertEqual(features.calendar_status, features_snapshot.calendar_status)
        self.assertEqual(features.missing_sessions, features_snapshot.missing_sessions)
        self.assertEqual(features.extra_sessions, features_snapshot.extra_sessions)
        self.assertEqual(features.nifty_provenance, features_snapshot.nifty_provenance)
        self.assertEqual(features.vix_provenance, features_snapshot.vix_provenance)
        self.assertEqual(features.records, features_snapshot.records)

        self.assertEqual(outcomes, outcomes_snapshot)
        self.assertEqual(outcomes.series_id, outcomes_snapshot.series_id)
        self.assertEqual(outcomes.outcomes, outcomes_snapshot.outcomes)

        # Deep per-origin record and payload value equality check
        for idx in range(N):
            self.assertEqual(features.records[idx], features_snapshot.records[idx])
            self.assertEqual(features.records[idx].payload, features_snapshot.records[idx].payload)
            self.assertEqual(outcomes.outcomes[idx], outcomes_snapshot.outcomes[idx])

        # Synthetic source files on disk remain strictly untouched
        for p_str, h_before in csv_hashes_before.items():
            p_obj = Path(p_str)
            self.assertTrue(p_obj.exists())
            self.assertEqual(hashlib.sha256(p_obj.read_bytes()).hexdigest(), h_before)

        # Equality
        self.assertEqual(plan1, plan2)
        self.assertEqual(plan1.train_indices, plan2.train_indices)
        self.assertEqual(plan1.development_indices, plan2.development_indices)
        self.assertEqual(plan1.refit_indices, plan2.refit_indices)
        self.assertEqual(plan1.test_indices, plan2.test_indices)
        self.assertEqual(plan1.decisions, plan2.decisions)

        # Immutability
        with self.assertRaises(FrozenInstanceError):
            plan1.development_start = dates[0]  # type: ignore[misc]

        with self.assertRaises(FrozenInstanceError):
            plan1.train_indices = ()  # type: ignore[misc]

        dec = plan1.decisions[0]
        with self.assertRaises(FrozenInstanceError):
            dec.in_refit = True  # type: ignore[misc]

        with self.assertRaises(FrozenInstanceError):
            dec.exclusion_reasons = ()  # type: ignore[misc]

        # Verify tuple types
        self.assertIsInstance(plan1.train_indices, tuple)
        self.assertIsInstance(plan1.development_indices, tuple)
        self.assertIsInstance(plan1.refit_indices, tuple)
        self.assertIsInstance(plan1.test_indices, tuple)
        self.assertIsInstance(plan1.decisions, tuple)
        self.assertIsInstance(dec.exclusion_reasons, tuple)

        # Sequence protocol on SplitPlan
        self.assertEqual(len(plan1), N)
        self.assertEqual(plan1[0], plan1.decisions[0])
        self.assertEqual(list(iter(plan1)), list(plan1.decisions))

    def test_07_import_and_source_audit(self) -> None:
        """
        Audits module dependencies and imports (SOURCE_INSPECTED):
        - research.prediction_eval.splits does not import network, subprocess,
          dataframe libraries, models, json, or csv.
        """
        import research.prediction_eval.splits as splits_mod

        mod_dict = splits_mod.__dict__
        forbidden_terms = (
            "pandas",
            "numpy",
            "urllib",
            "requests",
            "socket",
            "subprocess",
            "os",
            "sys",
            "json",
            "csv",
            "random",
        )
        for term in forbidden_terms:
            self.assertNotIn(term, mod_dict, f"Forbidden term '{term}' exposed in splits module.")

    def test_08_planner_boundary_rejects_malformed_axes_and_metadata(self) -> None:
        """
        Planner-boundary negatives (requirements discriminating example 2). Every case is an
        isolated copy of one valid 300-origin fixture with a single defect, so only the
        targeted guard can fire; each asserts the responsible InputValidationError.field and,
        for per-row guards, the failing origin index in the message.
        - Index cases keep dates valid; date cases keep indices positional and change
          feature and outcome dates together, before the 20-session endpoint region,
          so an earlier index or later endpoint guard cannot mask the ordering guard.
        - Bool 1 / True equal valid integers and flags numerically, so only the strict
          type rule can reject them.
        - Equal invalid Close pairs pass the cross-series comparison and isolate the
          positive-finite rule; a different-scale equal Close must be accepted.
        - States a frozen constructor would reject use the labelled test-only bypass.
        """
        base_f, base_o, dates = self._build_aligned_synthetic_fixture(
            n_origins=300,
            prefix="boundary_negatives",
        )
        d_valid = dates[100]
        t_valid = dates[200]
        baseline_plan = build_split_plan(base_f, base_o, development_start=d_valid, test_start=t_valid)

        f_recs = base_f.records
        o_recs = base_o.outcomes

        def put(records, position, record):
            return records[:position] + (record,) + records[position + 1:]

        def feats(position, record):
            return replace(base_f, records=put(f_recs, position, record))

        def outs(position, record):
            return replace(base_o, outcomes=put(o_recs, position, record))

        def with_dates(new_dates):
            # Same new date on both series at each position; origin indices stay positional.
            new_f, new_o = f_recs, o_recs
            for position, new_date in new_dates.items():
                new_f = put(new_f, position, replace(new_f[position], origin_date=new_date))
                new_o = put(new_o, position, replace(new_o[position], origin_date=new_date))
            return replace(base_f, records=new_f), replace(base_o, outcomes=new_o)

        bypass = self._force_frozen_fields
        close_5 = f_recs[5].origin_close
        # Origins 200..299 are feature-ready, 0..199 warmup; outcomes 0..279 are mature,
        # 280..299 the unknown tail.
        cases = [
            # (label, features, outcomes, expected field, failing origin index or None)
            ("feature records list", replace(base_f, records=list(f_recs)), base_o, "records", None),
            ("outcome records list", base_f, replace(base_o, outcomes=list(o_recs)), "outcomes", None),
            ("feature index off by one", feats(5, replace(f_recs[5], origin_index=6)), base_o, "origin_index", 5),
            ("feature index bool", feats(1, replace(f_recs[1], origin_index=True)), base_o, "origin_index", 1),
            ("outcome index bool", base_f, outs(1, replace(o_recs[1], origin_index=True)), "origin_index", 1),
            ("outcome index off by one (bypass)", base_f, outs(5, bypass(o_recs[5], origin_index=6)), "origin_index", 5),
            ("outcome date diverges", base_f,
             outs(5, replace(o_recs[5], origin_date=dates[5] + datetime.timedelta(days=1))), "origin_date", 5),
            ("duplicate date on both series", *with_dates({5: dates[4]}), "origin_date", 5),
            ("reordered dates on both series", *with_dates({5: dates[6], 6: dates[5]}), "origin_date", 6),
            ("origin close diverges", base_f,
             outs(5, replace(o_recs[5], origin_close=close_5 + Decimal("0.01"))), "origin_close", 5),
            ("equal infinite closes", feats(5, replace(f_recs[5], origin_close=Decimal("Infinity"))),
             outs(5, replace(o_recs[5], origin_close=Decimal("Infinity"))), "origin_close", 5),
            ("equal zero closes", feats(5, replace(f_recs[5], origin_close=Decimal("0"))),
             outs(5, replace(o_recs[5], origin_close=Decimal("0"))), "origin_close", 5),
            ("axis start is second date", replace(base_f, axis_start_date=dates[1]), base_o, "axis_start_date", None),
            ("axis start is datetime",
             replace(base_f, axis_start_date=datetime.datetime(dates[0].year, dates[0].month, dates[0].day)),
             base_o, "axis_start_date", None),
            ("feature_ready int 1", feats(250, replace(f_recs[250], feature_ready=1)), base_o, "feature_ready", 250),
            ("ready row marked unready (bypass)", feats(250, bypass(f_recs[250], feature_ready=False)),
             base_o, "feature_ready", 250),
            ("ready row without payload (bypass)", feats(250, bypass(f_recs[250], payload=None)),
             base_o, "payload", 250),
            ("warmup row with payload (bypass)", feats(100, bypass(f_recs[100], payload=f_recs[250].payload)),
             base_o, "payload", 100),
            ("zero VIX", feats(250, replace(f_recs[250], vix_close=Decimal("0"))), base_o, "vix_close", 250),
            ("float VIX", feats(250, replace(f_recs[250], vix_close=18.5)), base_o, "vix_close", 250),
            ("is_mature int 1", base_f, outs(5, replace(o_recs[5], is_mature=1)), "is_mature", 5),
            ("missing label at observed endpoint", base_f,
             outs(5, replace(o_recs[5], is_mature=False, status=STATUS_UNKNOWN, maturity_index=None,
                             maturity_date=None, maturity_close=None, outcome_class=None)),
             "status", 5),
            ("wrong maturity_index (bypass)", base_f, outs(5, bypass(o_recs[5], maturity_index=26)), "maturity_index", 5),
            ("fabricated mature tail", base_f,
             outs(290, replace(o_recs[290], is_mature=True, status=STATUS_MATURE, maturity_index=310,
                               maturity_date=dates[-1] + datetime.timedelta(days=28),
                               maturity_close=o_recs[290].origin_close, outcome_class=OUTCOME_CLASS_NEUTRAL)),
             "status", 290),
        ]

        for label, features, outcomes, field, position in cases:
            with self.subTest(case=label):
                with self.assertRaises(InputValidationError) as ctx:
                    build_split_plan(features, outcomes, development_start=d_valid, test_start=t_valid)
                self.assertEqual(ctx.exception.field, field)
                if position is not None:
                    self.assertRegex(str(ctx.exception), rf"\b(?:index|position) {position}\b")

        # Numerical, not textual, Close agreement: an equal value at another scale is accepted.
        rescaled = close_5.quantize(Decimal("0.001"))
        self.assertNotEqual(str(rescaled), str(close_5))
        rescaled_plan = build_split_plan(
            base_f,
            outs(5, replace(o_recs[5], origin_close=rescaled)),
            development_start=d_valid,
            test_start=t_valid,
        )
        self.assertEqual(rescaled_plan, baseline_plan)

        # The shared fixture was never mutated by any case construction.
        self.assertEqual(
            build_split_plan(base_f, base_o, development_start=d_valid, test_start=t_valid),
            baseline_plan,
        )


if __name__ == "__main__":
    unittest.main()
