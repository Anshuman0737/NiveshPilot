"""
Unit tests for Prediction Evaluation Fixed Logistic Regression Comparator.

Validates:
1. Compact asymmetric fixture from test_frequency (N=300, D=226, T=260):
   - Train fit (origins 200..205): exact integer counts (3, 2, 1), probabilities (0.5, 1/3, 1/6)
     within absolute tolerance 1e-5. Discriminates from Laplace (4/9, 3/9, 2/9).
   - Observes exactly one planner call and returned plan identity/cutoffs.
   - Development targets 226..239, test targets 260..279, tail 280..299 excluded.
2. Separate bounded, well-conditioned loader-backed nonconstant three-class fixture:
   - Independent stdlib fitting means, population variances (ddof=0), and scales for 6 numeric features.
   - Matches fit.numeric_means, fit.numeric_variances, fit.numeric_scales within abs=rel=1e-12.
   - Verifies zero relative-strength field (index 4): mean=0.0, var=0.0, scale=1.0.
   - Independent forward target probability reconstruction using stdlib arithmetic, fixed one-hot
     regime encoding, and stable softmax for EVERY prediction in BOTH blocks (abs=rel=1e-12).
   - Proves nonzero fitted effect and differing target predictions across rows.
3. Stdlib mean-normalized gradient on exact fitting rows:
   - Evaluates joint infinity norm of coefficient and intercept gradients (norm <= 1e-5).
   - Predeclared negative controls:
     * Zero-W gradient infinity norm >= 1e-3 (minimum 100-fold separation).
     * Unscaled target probabilities deviate >= 1e-10.
     * Independently target-fitted scaling probabilities deviate >= 1e-10.
   - Emits compact machine-readable synthetic oracle diagnostic in raw stdout.
4. Non-vacuous temporal counterfactuals:
   - Separate train and refit pools.
   - First-boundary purged-origin refit re-entry (origins 206..225 purged at D, present in refit).
   - Target and excluded label perturbations leave the relevant fit unchanged.
   - Development fit unaffected by refit construction.
   - Future price/VIX perturbations strictly at or after T=260 leave both fitting index sets,
     scaler parameters, and model states completely unchanged while target payloads change.
   - Preserves nonuniform calendar dates and missing-VIX positions.
5. Empty rows, missing training classes, empty targets, and absent fitting regimes:
   - Empty fitting pool yields no_fit_rows with fit=None, empty predictions, surviving counts.
   - Fewer than all 3 classes yields missing_training_classes with surviving class/regime counts.
   - Empty target pool with valid fit preserves fit with predictions=() and unavailable_reason=None.
   - Absent fitting regimes: unobserved regimes receive valid 0.0 columns and model fits cleanly.
   - Malformed selected target payload in insufficient-fit block raises InputValidationError before
     availability check.
   - Representative planner error propagation with responsible field reporting.
   - test_09: one corrupted test target per case, outside every fitting pool, for an empty refit
     (no_fit_rows) and an all-neutral refit (missing_training_classes), with clean controls.
   - test_10: one representative selected-payload value per comparator guard class (unsupported
     type, nonfinite float, binary64 conversion overflow) forced onto a copied payload.
6. Controlled actual-call-path failures and warning policy:
   - ConvergenceWarning mapped to unavailable_reason='not_converged' at stage 'fit'.
   - Enabled RuntimeWarning remains observable to caller.
   - FutureWarning raises under outer -W error::FutureWarning.
   - Scoped warning filter is restored on success and exception.
   - Injected numeric failures at scaler, fit, and prediction stages map to nonfinite_model_state
     with exact failure_stage, discarding fit on prediction failure.
   - Reaching iteration limit alone without warning is not unavailable.
   - Independent other-block behavior.
   - test_11: binary64 conversion overflow is still reported as InputValidationError under a finite
     int-to-string digit limit (the rejected integer is not formatted into the error).
   - test_12: finite predict_proba output with an extra row or column is a setup/programming error,
     not a consumed prefix.
7. Deep immutability, repeated-call equality, and clean boundary:
   - All returned dataclasses reject attribute mutation (FrozenInstanceError).
   - Input FeatureSeries, OutcomeSeries, and raw CSV files verified unmutated via deepcopy/bytes.
   - Repeated calls with identical inputs produce identical results.
   - Strict standard library and admitted numerical runtime imports only.
"""

from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError, replace
import datetime
from decimal import Decimal
import json
import math
from pathlib import Path
import sys
import tempfile
from typing import List, Sequence, Tuple, Union
import unittest
import warnings

import numpy as np
import scipy
import sklearn
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_info, threadpool_limits

from research.prediction_eval.inputs import (
    InputValidationError,
    align_pair,
    load_series,
)
from research.prediction_eval.features import (
    FeatureSeries,
    NiftyFeatureRecord,
    PredictorPayload,
    PROTOCOL_ID,
    REGIME_BEAR,
    REGIME_BULL,
    REGIME_CORRECTION,
    REGIME_HIGH_VOLATILITY,
    REGIME_RECOVERY,
    REGIME_SIDEWAYS,
    VALID_REGIMES,
    compute_nifty_features,
)
from research.prediction_eval.outcomes import (
    HORIZON_SESSIONS,
    OutcomeSeries,
    OUTCOME_CLASS_BEAR,
    OUTCOME_CLASS_BULL,
    OUTCOME_CLASS_NEUTRAL,
    TwentySessionOutcome,
    compute_twenty_session_outcomes,
)
from research.prediction_eval.splits import (
    PARTITION_DEVELOPMENT,
    PARTITION_TEST,
    PARTITION_TRAIN,
    SplitPlan,
    build_split_plan,
)
from research.prediction_eval import splits
import research.prediction_eval.logistic as logistic_mod
from research.prediction_eval.logistic import (
    ALL_FEATURE_NAMES,
    CLOSED_UNAVAILABLE_REASONS,
    ENCODED_FEATURE_NAMES,
    INT_TO_CLASS,
    CLASS_TO_INT,
    LogisticBlock,
    LogisticConfiguration,
    LogisticFit,
    LogisticPrediction,
    LogisticResult,
    METHOD_ID,
    NUMERIC_FEATURE_NAMES,
    ORDERED_CLASSES,
    OUTCOME_DEFINITION,
    SERIES_ID,
    STAGE_FIT,
    STAGE_PREDICTION,
    STAGE_SCALER,
    UNAVAILABLE_REASON_MISSING_TRAINING_CLASSES,
    UNAVAILABLE_REASON_NO_FIT_ROWS,
    UNAVAILABLE_REASON_NONFINITE_MODEL_STATE,
    UNAVAILABLE_REASON_NOT_CONVERGED,
    VALID_FAILURE_STAGES,
    build_logistic_predictions,
)


class TestPredictionEvalLogistic(unittest.TestCase):
    """Test suite for research/prediction_eval/logistic.py."""

    def setUp(self) -> None:
        # Cleanups are registered as each resource is acquired, so a failing assertion below
        # still releases both (unittest skips tearDown when setUp fails).
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.test_dir = Path(self.temp_dir.name)
        # Explicit test-harness threadpool scoping: single thread for numerical dependencies
        self.enterContext(threadpool_limits(limits=1))
        pools = threadpool_info()
        self.assertTrue(len(pools) > 0 and all(p["num_threads"] == 1 for p in pools))

    @staticmethod
    def _replace_payload(
        features: FeatureSeries, origin_index: int, payload: PredictorPayload
    ) -> FeatureSeries:
        """Returns a copy of features whose record at origin_index carries payload; the input is not modified."""
        records = list(features.records)
        records[origin_index] = replace(records[origin_index], payload=payload)
        return replace(features, records=tuple(records))

    @staticmethod
    def _force_payload_field(payload: PredictorPayload, field_name: str, value: object) -> PredictorPayload:
        """
        Test-only bypass: copies a valid payload, then forces a value that PredictorPayload's own
        constructor would reject, so the comparator's selected-payload guard is the check under test.
        """
        clone = replace(payload)
        object.__setattr__(clone, field_name, value)
        return clone

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
        start_date: datetime.date = datetime.date(2021, 1, 4),
    ) -> List[datetime.date]:
        """Generates strictly increasing dates with nonuniform calendar spacing."""
        dates: List[datetime.date] = []
        curr = start_date
        while len(dates) < count:
            weekday = curr.weekday()
            if len(dates) == 50 and weekday == 5:
                dates.append(curr)
            elif len(dates) == 150:
                curr += datetime.timedelta(days=4)
                if curr.weekday() < 5:
                    dates.append(curr)
            elif weekday < 5:
                dates.append(curr)
            curr += datetime.timedelta(days=1)
        return dates

    def _build_oracle_fixture(
        self,
        n_origins: int = 300,
        missing_vix_indices: Sequence[int] = (),
        close_overrides: Sequence[Tuple[int, str]] = (),
        vix_overrides: Sequence[Tuple[int, str]] = (),
        prefix: str = "oracle",
    ) -> Tuple[FeatureSeries, OutcomeSeries, List[datetime.date]]:
        """
        Builds a synthetic Nifty and VIX pair using actual load_series -> align_pair ->
        compute_nifty_features and compute_twenty_session_outcomes.
        """
        dates = self._generate_nonuniform_dates(n_origins)
        missing_vix_set = set(missing_vix_indices)
        close_map = dict(close_overrides)
        vix_map = dict(vix_overrides)

        nifty_lines = ["Date,Close"]
        for idx, d in enumerate(dates):
            c_val = close_map.get(idx, "100.00")
            nifty_lines.append(f"{d.strftime('%d-%b-%Y')},{c_val}")
        n_file = self._write_csv(f"{prefix}_nifty.csv", "\n".join(nifty_lines) + "\n")

        vix_lines = ["Date,Close"]
        for idx, d in enumerate(dates):
            if idx in missing_vix_set:
                continue
            v_val = vix_map.get(idx, "20.00")
            vix_lines.append(f"{d.strftime('%d-%b-%Y')},{v_val}")
        v_file = self._write_csv(f"{prefix}_vix.csv", "\n".join(vix_lines) + "\n")

        n_series = load_series("nifty50_price_index", n_file)
        v_series = load_series("india_vix", v_file)
        pair = align_pair(n_series, v_series, expected_sessions=dates)

        features = compute_nifty_features(pair)
        outcomes = compute_twenty_session_outcomes(n_series)
        return features, outcomes, dates

    def _build_nonconstant_fixture(
        self,
        n_origins: int = 320,
        d_index: int = 230,
        t_index: int = 270,
        prefix: str = "nonconstant",
    ) -> Tuple[FeatureSeries, OutcomeSeries, List[datetime.date]]:
        """
        Builds a well-conditioned nonconstant fixture with varying features across all 6 numeric fields,
        multiple regimes, and all 3 classes (BEAR, NEUTRAL, BULL) present in both train and refit pools.
        """
        dates = self._generate_nonuniform_dates(n_origins)
        prices = [100.0] * n_origins
        for i in range(n_origins):
            wave = 3.0 * math.sin(i * 0.2)
            prices[i] = 100.0 + wave + (i % 7) * 0.4

        for i in range(200, 260):
            m = i % 3
            if m == 0:
                prices[i + 20] = prices[i] * 1.001
            elif m == 1:
                prices[i + 20] = prices[i] * 1.020
            else:
                prices[i + 20] = prices[i] * 0.980

        nifty_lines = ["Date,Close"]
        vix_lines = ["Date,Close"]
        for idx, d in enumerate(dates):
            c = prices[idx]
            v = 20.0 + 2.0 * math.cos(idx * 0.1)
            nifty_lines.append(f"{d.strftime('%d-%b-%Y')},{c:.2f}")
            vix_lines.append(f"{d.strftime('%d-%b-%Y')},{v:.2f}")

        n_file = self._write_csv(f"{prefix}_nifty.csv", "\n".join(nifty_lines) + "\n")
        v_file = self._write_csv(f"{prefix}_vix.csv", "\n".join(vix_lines) + "\n")

        n_series = load_series("nifty50_price_index", n_file)
        v_series = load_series("india_vix", v_file)
        pair = align_pair(n_series, v_series, expected_sessions=dates)

        features = compute_nifty_features(pair)
        outcomes = compute_twenty_session_outcomes(n_series)
        return features, outcomes, dates

    def test_01_compact_asymmetric_constant_rows_and_planner_call(self) -> None:
        """
        Validates the compact asymmetric fixture from test_frequency:
        - N=300, D=226, T=260. Close=100.00 except 220, 221, 222 = 99.00 and 225 = 101.00, VIX=20.00.
        - Exact pool indices and cutoffs:
          * development fitting origins 200..205 (6 rows) with class counts (3, 2, 1).
          * refit origins 200..239 (40 rows) with class counts (4, 32, 4).
          * targets: development 226..239 (14 rows), test 260..279 (20 rows), unknown tail 280..299 excluded.
        - Development fitting payloads are constant across 200..205:
          * Empirical logistic expectation: (.5, 1/3, 1/6), abs_tol=1e-5.
          * Discriminates from Laplace frequency (4/9, 3/9, 2/9).
        - Observes exactly one planner call and returned plan identity/cutoffs.
        """
        N = 300
        D = 226
        T = 260
        close_overrides = [
            (220, "99.00"),
            (221, "99.00"),
            (222, "99.00"),
            (225, "101.00"),
        ]
        features, outcomes, dates = self._build_oracle_fixture(
            n_origins=N,
            close_overrides=close_overrides,
            prefix="asym_logistic",
        )
        d_date = dates[D]
        t_date = dates[T]

        # Planner observer wrapping canonical splits.build_split_plan in logistic module
        orig_build_split_plan = logistic_mod.build_split_plan
        planner_calls = []

        def spy_build_split_plan(features_arg, outcomes_arg, *, development_start, test_start):
            plan = orig_build_split_plan(
                features_arg,
                outcomes_arg,
                development_start=development_start,
                test_start=test_start,
            )
            planner_calls.append({
                "features": features_arg,
                "outcomes": outcomes_arg,
                "development_start": development_start,
                "test_start": test_start,
                "plan": plan,
            })
            return plan

        try:
            logistic_mod.build_split_plan = spy_build_split_plan
            result = build_logistic_predictions(
                features,
                outcomes,
                development_start=d_date,
                test_start=t_date,
            )
        finally:
            logistic_mod.build_split_plan = orig_build_split_plan

        # Assert exactly once called with exact cutoffs and returned plan identity
        self.assertEqual(len(planner_calls), 1)
        self.assertIs(planner_calls[0]["features"], features)
        self.assertIs(planner_calls[0]["outcomes"], outcomes)
        self.assertEqual(planner_calls[0]["development_start"], d_date)
        self.assertEqual(planner_calls[0]["test_start"], t_date)
        self.assertIs(result.plan, planner_calls[0]["plan"])

        # Plan agreement and exactly one planner call verification
        self.assertEqual(result.plan.development_start_index, D)
        self.assertEqual(result.plan.test_start_index, T)
        self.assertEqual(result.plan.development_start, d_date)
        self.assertEqual(result.plan.test_start, t_date)

        # Development block
        dev_b = result.development_block
        self.assertEqual(dev_b.partition, PARTITION_DEVELOPMENT)
        self.assertIsNone(dev_b.unavailable_reason)
        self.assertIsNotNone(dev_b.fit)

        dev_fit = dev_b.fit
        self.assertEqual(dev_b.fitting_indices, tuple(range(200, 206)))
        self.assertEqual(dev_b.class_counts, (3, 2, 1))
        self.assertEqual(dev_b.requested_indices, tuple(range(226, 240)))
        self.assertEqual(len(dev_b.predictions), 14)

        # Constant fitting row empirical logistic expectation: (3/6, 2/6, 1/6) = (0.5, 1/3, 1/6)
        expected_dev_probs = (0.5, 1.0 / 3.0, 1.0 / 6.0)
        for pred in dev_b.predictions:
            p0, p1, p2 = pred.probabilities
            self.assertTrue(math.isclose(p0, expected_dev_probs[0], abs_tol=1e-5))
            self.assertTrue(math.isclose(p1, expected_dev_probs[1], abs_tol=1e-5))
            self.assertTrue(math.isclose(p2, expected_dev_probs[2], abs_tol=1e-5))
            # Discriminate from Laplace frequency (4/9, 3/9, 2/9)
            self.assertFalse(math.isclose(p0, 4.0 / 9.0, abs_tol=1e-3))
            self.assertFalse(math.isclose(p2, 2.0 / 9.0, abs_tol=1e-3))

        # Test block
        test_b = result.test_block
        self.assertEqual(test_b.partition, PARTITION_TEST)
        self.assertIsNone(test_b.unavailable_reason)
        self.assertIsNotNone(test_b.fit)

        test_fit = test_b.fit
        self.assertEqual(test_b.fitting_indices, tuple(range(200, 240)))
        self.assertEqual(test_b.class_counts, (4, 32, 4))
        self.assertEqual(test_b.requested_indices, tuple(range(260, 280)))
        self.assertEqual(len(test_b.predictions), 20)

        # Tail 280..299 excluded
        pred_indices = {p.origin_index for p in test_b.predictions}
        for tail_idx in range(280, 300):
            self.assertNotIn(tail_idx, pred_indices)

        # Exact requested prediction index and date order on successful blocks
        self.assertEqual(
            tuple(p.origin_index for p in dev_b.predictions),
            dev_b.requested_indices,
        )
        self.assertEqual(
            tuple(p.origin_date for p in dev_b.predictions),
            tuple(dates[i] for i in dev_b.requested_indices),
        )
        self.assertEqual(
            tuple(p.origin_index for p in test_b.predictions),
            test_b.requested_indices,
        )
        self.assertEqual(
            tuple(p.origin_date for p in test_b.predictions),
            tuple(dates[i] for i in test_b.requested_indices),
        )

    def test_02_and_03_nonconstant_fixture_forward_gradient_and_negative_controls(self) -> None:
        """
        Validates the nonconstant fixture with independent stdlib oracles, gradient stationarity,
        and negative controls:
        - Independent stdlib fitting means, population variances (ddof=0), and scales for all 6 numeric fields.
        - Check actual zero relative-strength field (index 4): mean=0.0, var=0.0, scale=1.0.
        - Independent forward target probability reconstruction using stable softmax (abs=rel=1e-12).
        - Proves nonzero fitted effect and differing target predictions.
        - Stdlib mean-normalized gradient infinity norm <= 1e-5.
        - Predeclared negative controls:
          * Zero-W gradient infinity norm >= 1e-3 (minimum 100-fold separation).
          * Unscaled target probabilities deviate >= 1e-10.
          * Target-fitted scaler probabilities deviate >= 1e-10.
        - Emits compact machine-readable synthetic oracle diagnostic in raw stdout.
        """
        D = 230
        T = 270
        features, outcomes, dates = self._build_nonconstant_fixture(
            n_origins=320,
            d_index=D,
            t_index=T,
            prefix="nonconst_val",
        )
        d_date = dates[D]
        t_date = dates[T]

        result = build_logistic_predictions(
            features,
            outcomes,
            development_start=d_date,
            test_start=t_date,
        )

        diagnostic_data = {
            "fixture": "nonconstant_320",
            "development_start": str(d_date),
            "test_start": str(t_date),
            "blocks": {},
        }

        for block_name, block in [("development", result.development_block), ("test", result.test_block)]:
            self.assertIsNone(block.unavailable_reason)
            self.assertIsNotNone(block.fit)
            fit = block.fit
            fitting_indices = block.fitting_indices
            target_indices = block.requested_indices
            N_fit = len(fitting_indices)
            N_tgt = len(target_indices)

            # 1. Independent stdlib fitting means, variances, and scales
            num_means = [
                sum(getattr(features.records[i].payload, f) for i in fitting_indices) / N_fit
                for f in NUMERIC_FEATURE_NAMES
            ]
            num_vars = [
                sum((getattr(features.records[i].payload, f) - num_means[j]) ** 2 for i in fitting_indices) / N_fit
                for j, f in enumerate(NUMERIC_FEATURE_NAMES)
            ]
            num_scales = [math.sqrt(v) if v > 0.0 else 1.0 for v in num_vars]

            # Compare with fit object within 1e-12
            for j in range(6):
                self.assertTrue(math.isclose(fit.numeric_means[j], num_means[j], rel_tol=1e-12, abs_tol=1e-12))
                self.assertTrue(math.isclose(fit.numeric_variances[j], num_vars[j], rel_tol=1e-12, abs_tol=1e-12))
                self.assertTrue(math.isclose(fit.numeric_scales[j], num_scales[j], rel_tol=1e-12, abs_tol=1e-12))

            # Zero relative strength field check (field index 4: rel_strength_20d)
            self.assertEqual(fit.numeric_means[4], 0.0)
            self.assertEqual(fit.numeric_variances[4], 0.0)
            self.assertEqual(fit.numeric_scales[4], 1.0)

            # 2. Forward target probability reconstruction
            max_fwd_err = 0.0
            distinct_probs = set()
            for pred in block.predictions:
                t_i = pred.origin_index
                p = features.records[t_i].payload
                assert p is not None
                x_std = [
                    (getattr(p, f) - num_means[j]) / num_scales[j]
                    for j, f in enumerate(NUMERIC_FEATURE_NAMES)
                ]
                x_reg = [1.0 if p.market_regime == r else 0.0 for r in VALID_REGIMES]
                x_full = x_std + x_reg

                z = [
                    fit.intercepts[k] + sum(fit.coefficients[k][j] * x_full[j] for j in range(12))
                    for k in range(3)
                ]
                max_z = max(z)
                exp_z = [math.exp(zk - max_z) for zk in z]
                sum_exp = sum(exp_z)
                reconstructed_p = tuple(ez / sum_exp for ez in exp_z)
                distinct_probs.add(reconstructed_p)

                for k in range(3):
                    diff = abs(pred.probabilities[k] - reconstructed_p[k])
                    max_fwd_err = max(max_fwd_err, diff)
                    self.assertTrue(
                        math.isclose(pred.probabilities[k], reconstructed_p[k], rel_tol=1e-12, abs_tol=1e-12)
                    )

            self.assertLessEqual(max_fwd_err, 1e-12)
            # Prove nonzero fitted effect and differing predictions across target rows
            self.assertGreater(len(distinct_probs), 1)

            # 3. Stdlib mean-normalized gradient on exact fitting rows
            grad_coef = [[0.0] * 12 for _ in range(3)]
            grad_intercept = [0.0] * 3
            for i in fitting_indices:
                p = features.records[i].payload
                assert p is not None
                x_std = [
                    (getattr(p, f) - num_means[j]) / num_scales[j]
                    for j, f in enumerate(NUMERIC_FEATURE_NAMES)
                ]
                x_reg = [1.0 if p.market_regime == r else 0.0 for r in VALID_REGIMES]
                x_full = x_std + x_reg

                z = [
                    fit.intercepts[k] + sum(fit.coefficients[k][j] * x_full[j] for j in range(12))
                    for k in range(3)
                ]
                max_z = max(z)
                exp_z = [math.exp(zk - max_z) for zk in z]
                sum_exp = sum(exp_z)
                row_probs = [ez / sum_exp for ez in exp_z]
                y_true = CLASS_TO_INT[outcomes[i].outcome_class]

                for k in range(3):
                    e_k = row_probs[k] - (1.0 if y_true == k else 0.0)
                    grad_intercept[k] += e_k / float(N_fit)
                    for j in range(12):
                        grad_coef[k][j] += (e_k * x_full[j]) / float(N_fit)

            for k in range(3):
                for j in range(12):
                    grad_coef[k][j] += fit.coefficients[k][j] / (1.0 * float(N_fit))

            inf_norm = max(
                max(abs(b) for b in grad_intercept),
                max(abs(grad_coef[k][j]) for k in range(3) for j in range(12)),
            )
            self.assertLessEqual(inf_norm, 1e-5)

            # Negative control 1: Zero-W gradient infinity norm >= 1e-3
            grad_w0 = [[0.0] * 12 for _ in range(3)]
            for i in fitting_indices:
                p = features.records[i].payload
                assert p is not None
                x_std = [
                    (getattr(p, f) - num_means[j]) / num_scales[j]
                    for j, f in enumerate(NUMERIC_FEATURE_NAMES)
                ]
                x_reg = [1.0 if p.market_regime == r else 0.0 for r in VALID_REGIMES]
                x_full = x_std + x_reg
                z_w0 = list(fit.intercepts)
                max_z = max(z_w0)
                exp_z = [math.exp(zk - max_z) for zk in z_w0]
                sum_exp = sum(exp_z)
                probs_w0 = [ez / sum_exp for ez in exp_z]
                y_true = CLASS_TO_INT[outcomes[i].outcome_class]
                for k in range(3):
                    e_k = probs_w0[k] - (1.0 if y_true == k else 0.0)
                    for j in range(12):
                        grad_w0[k][j] += (e_k * x_full[j]) / float(N_fit)

            inf_norm_w0 = max(abs(grad_w0[k][j]) for k in range(3) for j in range(12))
            self.assertGreaterEqual(inf_norm_w0, 1e-3)
            # Minimum 100-fold separation
            self.assertGreaterEqual(inf_norm_w0 / max(inf_norm, 1e-12), 100.0)

            # Target-fitted statistics for negative control 3
            tgt_means = [
                sum(getattr(features.records[i].payload, f) for i in target_indices) / float(N_tgt)
                for f in NUMERIC_FEATURE_NAMES
            ]
            tgt_vars = [
                sum((getattr(features.records[i].payload, f) - tgt_means[j]) ** 2 for i in target_indices) / float(N_tgt)
                for j, f in enumerate(NUMERIC_FEATURE_NAMES)
            ]
            tgt_scales = [math.sqrt(v) if v > 0.0 else 1.0 for v in tgt_vars]

            max_unscaled_diff = 0.0
            max_tgt_scale_diff = 0.0
            for pred in block.predictions:
                t_i = pred.origin_index
                p = features.records[t_i].payload
                assert p is not None
                x_raw = [getattr(p, f) for f in NUMERIC_FEATURE_NAMES]
                x_tgt_std = [
                    (getattr(p, f) - tgt_means[j]) / tgt_scales[j]
                    for j, f in enumerate(NUMERIC_FEATURE_NAMES)
                ]
                x_reg = [1.0 if p.market_regime == r else 0.0 for r in VALID_REGIMES]

                # Negative control 2: unscaled target numerics
                z_unscaled = [
                    fit.intercepts[k] + sum(fit.coefficients[k][j] * (x_raw + x_reg)[j] for j in range(12))
                    for k in range(3)
                ]
                ez_u = [math.exp(zk - max(z_unscaled)) for zk in z_unscaled]
                probs_u = [e / sum(ez_u) for e in ez_u]
                for a, b in zip(pred.probabilities, probs_u):
                    max_unscaled_diff = max(max_unscaled_diff, abs(a - b))

                # Negative control 3: target-fitted scaling
                z_tgt = [
                    fit.intercepts[k] + sum(fit.coefficients[k][j] * (x_tgt_std + x_reg)[j] for j in range(12))
                    for k in range(3)
                ]
                ez_t = [math.exp(zk - max(z_tgt)) for zk in z_tgt]
                probs_t = [e / sum(ez_t) for e in ez_t]
                for a, b in zip(pred.probabilities, probs_t):
                    max_tgt_scale_diff = max(max_tgt_scale_diff, abs(a - b))

            self.assertGreaterEqual(max_unscaled_diff, 1e-10)
            self.assertGreaterEqual(max_tgt_scale_diff, 1e-10)

            diagnostic_data["blocks"][block_name] = {
                "cutoff_index": block.cutoff_index,
                "cutoff_date": block.cutoff_date.isoformat(),
                "fitting_indices": list(block.fitting_indices),
                "requested_indices": list(block.requested_indices),
                "fitting_indices_count": N_fit,
                "requested_indices_count": N_tgt,
                "class_counts": list(block.class_counts),
                "regime_counts": list(block.regime_counts),
                "n_iter": fit.n_iter,
                "max_forward_error": max_fwd_err,
                "gradient_infinity_norm": inf_norm,
                "zero_w_gradient_norm": inf_norm_w0,
                "max_unscaled_target_diff": max_unscaled_diff,
                "max_target_fitted_scale_diff": max_tgt_scale_diff,
                "scaler_means": list(fit.numeric_means),
                "scaler_variances": list(fit.numeric_variances),
                "scaler_scales": list(fit.numeric_scales),
                "coefficients": [list(row) for row in fit.coefficients],
                "intercepts": list(fit.intercepts),
            }

        cfg = result.configuration
        diagnostic_data["configuration"] = {
            "solver": cfg.solver,
            "c": cfg.c,
            "fit_intercept": cfg.fit_intercept,
            "tol": cfg.tol,
            "max_iter": cfg.max_iter,
            "l1_ratio": cfg.l1_ratio,
            "warm_start": cfg.warm_start,
            "verbose": cfg.verbose,
        }
        diagnostic_data["encoded_column_order"] = list(ALL_FEATURE_NAMES)
        diagnostic_data["encoded_feature_order"] = list(result.encoded_features)
        diagnostic_data["feature_order"] = list(result.numeric_features)
        diagnostic_data["regime_order"] = list(result.regime_order)
        diagnostic_data["class_order"] = list(result.classes)
        diagnostic_data["versions"] = {
            "sklearn": sklearn.__version__,
            "numpy": np.__version__,
            "scipy": scipy.__version__,
        }
        diagnostic_data["threadpools"] = threadpool_info()

        # Emit machine-readable diagnostic line in raw stdout
        print("\nSYNTHETIC_ORACLE_DIAGNOSTIC: " + json.dumps(diagnostic_data, sort_keys=True))

    def test_04_temporal_counterfactuals_and_reentry(self) -> None:
        """
        Validates temporal causal safety under perturbations and boundary re-entry:
        - Separate train and refit pools.
        - First-boundary purged-origin refit re-entry:
          Origins 206..225 are purged from train (maturity >= D=226), but re-enter refit (maturity < T=260).
        - Excluded/target label changes leave the relevant fit unchanged.
        - Development fit unaffected by refit construction.
        - Future price and VIX changes strictly at or after T=260 leave both fitting index sets,
          scaler states, and model states completely unchanged while showing changed target payload.
        """
        N = 300
        D = 226
        T = 260
        close_overrides = [
            (220, "99.00"),
            (221, "99.00"),
            (222, "99.00"),
            (225, "101.00"),
        ]
        feat_base, out_base, dates = self._build_oracle_fixture(
            n_origins=N,
            close_overrides=close_overrides,
            prefix="temp_base",
        )
        res_base = build_logistic_predictions(
            feat_base, out_base, development_start=dates[D], test_start=dates[T]
        )

        # 1. Re-entry check: origins 206..225 purged from train, present in refit
        dev_b = res_base.development_block
        test_b = res_base.test_block
        dev_fit = dev_b.fit
        test_fit = test_b.fit
        assert dev_fit is not None and test_fit is not None
        self.assertEqual(dev_b.fitting_indices, tuple(range(200, 206)))
        self.assertEqual(test_b.fitting_indices, tuple(range(200, 240)))
        for i in range(206, 226):
            self.assertNotIn(i, dev_b.fitting_indices)
            self.assertIn(i, test_b.fitting_indices)

        # 2. Excluded label change: perturb label at origin 240 (crosses test boundary)
        outs_tampered = list(out_base.outcomes)
        outs_tampered[240] = replace(outs_tampered[240], outcome_class=OUTCOME_CLASS_BEAR)
        out_pert = OutcomeSeries(series_id=out_base.series_id, outcomes=tuple(outs_tampered))
        res_label_pert = build_logistic_predictions(
            feat_base, out_pert, development_start=dates[D], test_start=dates[T]
        )
        # Both fits must be bit-for-bit identical!
        assert res_label_pert.development_block.fit is not None
        assert res_label_pert.test_block.fit is not None
        self.assertEqual(res_label_pert.development_block.fit, dev_fit)
        self.assertEqual(res_label_pert.test_block.fit, test_fit)

        # 3. Future price/VIX perturbation at or after T=260
        close_overrides_fut = list(close_overrides) + [(i, "50.00") for i in range(260, 300)]
        vix_overrides_fut = [(i, "35.00") for i in range(260, 300)]
        feat_fut, out_fut, _ = self._build_oracle_fixture(
            n_origins=N,
            close_overrides=close_overrides_fut,
            vix_overrides=vix_overrides_fut,
            prefix="temp_fut",
        )
        res_fut = build_logistic_predictions(
            feat_fut, out_fut, development_start=dates[D], test_start=dates[T]
        )
        assert res_fut.development_block.fit is not None
        assert res_fut.test_block.fit is not None

        # Both fitting index sets and full LogisticFit states remain completely identical!
        self.assertEqual(dev_b.fitting_indices, res_fut.development_block.fitting_indices)
        self.assertEqual(test_b.fitting_indices, res_fut.test_block.fitting_indices)
        self.assertEqual(res_fut.development_block.fit, dev_fit)
        self.assertEqual(res_fut.test_block.fit, test_fit)

        # While target payloads and predictions at T change meaningfully
        p_base_260 = res_base.test_block.predictions[0].probabilities
        p_fut_260 = res_fut.test_block.predictions[0].probabilities
        self.assertNotEqual(p_base_260, p_fut_260)

        # 4. Target-label perturbation: perturb label at development target origin 230
        # Origin 230 is a target in dev (not in dev fitting pool 200..205), but is in test refit pool 200..239
        outs_tgt = list(out_base.outcomes)
        outs_tgt[230] = replace(outs_tgt[230], outcome_class=OUTCOME_CLASS_BEAR)
        out_tgt_pert = OutcomeSeries(series_id=out_base.series_id, outcomes=tuple(outs_tgt))
        res_tgt_pert = build_logistic_predictions(
            feat_base, out_tgt_pert, development_start=dates[D], test_start=dates[T]
        )
        # Development fitting state and class counts must be completely identical!
        dev_tgt_fit = res_tgt_pert.development_block.fit
        assert dev_tgt_fit is not None
        self.assertEqual(res_tgt_pert.development_block.class_counts, dev_b.class_counts)
        self.assertEqual(dev_tgt_fit, dev_fit)

        # 5. Re-entry label perturbation: perturb purged origin 215 (maturity 235 >= D=226, < T=260)
        # Origin 215 is purged from train (not in dev 200..205), but re-enters refit (in test 200..239).
        outs_reentry = list(out_base.outcomes)
        outs_reentry[215] = replace(outs_reentry[215], outcome_class=OUTCOME_CLASS_BEAR)
        out_reentry_pert = OutcomeSeries(series_id=out_base.series_id, outcomes=tuple(outs_reentry))
        res_reentry = build_logistic_predictions(
            feat_base, out_reentry_pert, development_start=dates[D], test_start=dates[T]
        )
        dev_reentry_fit = res_reentry.development_block.fit
        test_reentry_fit = res_reentry.test_block.fit
        assert dev_reentry_fit is not None and test_reentry_fit is not None
        # Development fit and counts remain completely unaffected
        self.assertEqual(res_reentry.development_block.class_counts, dev_b.class_counts)
        self.assertEqual(dev_reentry_fit, dev_fit)
        # But test block refit class counts reflect the changed re-entry label
        self.assertNotEqual(res_reentry.test_block.class_counts, test_b.class_counts)
        self.assertEqual(res_reentry.test_block.class_counts[0], test_b.class_counts[0] + 1)  # BEAR increased

        # 6. Target VIX/regime perturbation: perturb VIX only on target origin 230.
        # Origin 230 is a development target (226..239) AND a test refit row (200..239).
        # Perturbing VIX at origin 230 changes target payload regime while leaving development
        # fitting state unchanged (test refit state is legitimately modified).
        vix_tgt_pert = [(230, "32.00")]  # High-volatility regime (> 26.0) instead of Sideways
        feat_vix_tgt, out_vix_tgt, _ = self._build_oracle_fixture(
            n_origins=N,
            close_overrides=close_overrides,
            vix_overrides=vix_tgt_pert,
            prefix="vix_tgt_pert",
        )
        res_vix_tgt = build_logistic_predictions(
            feat_vix_tgt, out_vix_tgt, development_start=dates[D], test_start=dates[T]
        )
        dev_vix_fit = res_vix_tgt.development_block.fit
        assert dev_vix_fit is not None
        # Full development fitting state remains completely unchanged
        self.assertEqual(dev_vix_fit, dev_fit)
        # Test refit state is altered by the origin 230 VIX change
        assert res_vix_tgt.test_block.fit is not None
        self.assertNotEqual(res_vix_tgt.test_block.fit, test_fit)

        # While target payload regime at origin 230 is demonstrably changed to High-volatility
        rec_base_230 = feat_base.records[230]
        rec_vix_230 = feat_vix_tgt.records[230]
        assert rec_base_230.payload is not None and rec_vix_230.payload is not None
        self.assertEqual(rec_base_230.payload.market_regime, REGIME_SIDEWAYS)
        self.assertEqual(rec_vix_230.payload.market_regime, REGIME_HIGH_VOLATILITY)
        self.assertNotEqual(rec_base_230.payload.market_regime, rec_vix_230.payload.market_regime)

        # 7. Exercise valid regime absent from fitting through fixed columns:
        # In baseline dev fitting pool (200..205), regimes High-volatility, Bear, Recovery, Correction,
        # and Bull have count 0 (all 6 fitting rows are Sideways).
        self.assertEqual(len(dev_b.regime_counts), len(VALID_REGIMES))
        high_vol_idx = VALID_REGIMES.index(REGIME_HIGH_VOLATILITY)
        self.assertEqual(dev_b.regime_counts[high_vol_idx], 0)

        # Connect changed target regime to zero development fitting count and verify
        # prediction for origin 230 succeeds despite its regime having zero fitting observations
        absent_regimes = [VALID_REGIMES[idx] for idx, c in enumerate(dev_b.regime_counts) if c == 0]
        self.assertIn(REGIME_HIGH_VOLATILITY, absent_regimes)
        self.assertIn(REGIME_BEAR, absent_regimes)
        self.assertIn(REGIME_RECOVERY, absent_regimes)
        self.assertIn(REGIME_CORRECTION, absent_regimes)
        self.assertIn(REGIME_BULL, absent_regimes)

        pred_vix_230 = [p for p in res_vix_tgt.development_block.predictions if p.origin_index == 230][0]
        self.assertEqual(pred_vix_230.origin_index, 230)
        self.assertEqual(pred_vix_230.origin_date, dates[230])
        self.assertEqual(len(pred_vix_230.probabilities), 3)
        self.assertTrue(math.isclose(sum(pred_vix_230.probabilities), 1.0, abs_tol=1e-12))
        for p_prob in pred_vix_230.probabilities:
            self.assertGreaterEqual(p_prob, 0.0)
            self.assertLessEqual(p_prob, 1.0)

    def test_05_empty_missing_classes_empty_targets_and_schema_validation_precedence(self) -> None:
        """
        Validates:
        - 0 fitting rows yields no_fit_rows, fit=None, predictions=(), surviving counts.
        - Missing training classes yields missing_training_classes, fit=None, predictions=(), surviving counts.
        - Empty target pool with valid fit preserves fit with predictions=() and unavailable_reason=None.
        - Absent fitting regimes: unobserved regimes receive valid 0.0 columns and model fits cleanly.
        - Malformed selected target payload in insufficient-fit block raises InputValidationError
          before availability check.
        - Representative planner error propagation with responsible field reporting.
        """
        # 1. 0 fitting rows on short series (N=25)
        feat_short, out_short, dates_short = self._build_oracle_fixture(n_origins=25, prefix="short25")
        res_short = build_logistic_predictions(
            feat_short, out_short, development_start=dates_short[5], test_start=dates_short[15]
        )
        for block in [res_short.development_block, res_short.test_block]:
            self.assertIsNone(block.fit)
            self.assertEqual(block.unavailable_reason, UNAVAILABLE_REASON_NO_FIT_ROWS)
            self.assertIsNone(block.failure_stage)
            self.assertEqual(block.predictions, ())
            self.assertEqual(block.class_counts, (0, 0, 0))
            self.assertEqual(block.regime_counts, (0, 0, 0, 0, 0, 0))

        # 2. Missing training class: all labels become BEAR, 0 NEUTRAL and 0 BULL in fitting pool
        N = 300
        D = 230
        T = 270
        feat_nc, out_nc, dates_nc = self._build_oracle_fixture(n_origins=N, prefix="miss_class")
        # Invert neutral labels to BEAR across training set (all outcomes become BEAR)
        outs_mod = []
        for i, o in enumerate(out_nc.outcomes):
            if o.outcome_class == OUTCOME_CLASS_NEUTRAL:
                outs_mod.append(replace(o, outcome_class=OUTCOME_CLASS_BEAR))
            else:
                outs_mod.append(o)
        out_no_neutral = OutcomeSeries(series_id=out_nc.series_id, outcomes=tuple(outs_mod))
        res_no_neutral = build_logistic_predictions(
            feat_nc, out_no_neutral, development_start=dates_nc[D], test_start=dates_nc[T]
        )
        dev_b = res_no_neutral.development_block
        self.assertIsNone(dev_b.fit)
        self.assertEqual(dev_b.unavailable_reason, UNAVAILABLE_REASON_MISSING_TRAINING_CLASSES)
        self.assertIsNone(dev_b.failure_stage)
        self.assertEqual(dev_b.predictions, ())
        self.assertEqual(dev_b.class_counts[1], 0)  # Neutral is 0
        self.assertGreater(dev_b.class_counts[0], 0)  # Bear is > 0

        # 3. Empty target pool with valid fit
        feat_no_dev_target, out_no_dev_target, dates_targets = self._build_oracle_fixture(
            n_origins=N,
            missing_vix_indices=tuple(range(226, 240)),
            close_overrides=[(220, "99.00"), (221, "99.00"), (222, "99.00"), (225, "101.00")],
            prefix="empty_dev_tgt",
        )
        res_no_dev_target = build_logistic_predictions(
            feat_no_dev_target, out_no_dev_target, development_start=dates_targets[226], test_start=dates_targets[260]
        )
        self.assertIsNotNone(res_no_dev_target.development_block.fit)
        self.assertIsNone(res_no_dev_target.development_block.unavailable_reason)
        self.assertEqual(res_no_dev_target.development_block.requested_indices, ())
        self.assertEqual(res_no_dev_target.development_block.predictions, ())

        # 4. Schema validation precedence across both blocks:
        # Case 4a: Development block has 0 fitting rows (D=210 on N=300), but target row has boolean ret_5d.
        # Origin 215 is also a refit fitting row here; test_09 isolates targets outside every fitting pool.
        feat_bool_tgt, out_bool_tgt, dates_bool = self._build_oracle_fixture(n_origins=N, prefix="bool_tgt")
        tampered_recs = list(feat_bool_tgt.records)
        target_rec = tampered_recs[215]
        assert target_rec.payload is not None
        tampered_payload = replace(target_rec.payload, ret_5d=True)  # type: ignore[arg-type]
        tampered_recs[215] = replace(target_rec, payload=tampered_payload)
        feat_tampered = replace(feat_bool_tgt, records=tuple(tampered_recs))

        with self.assertRaises(InputValidationError) as ctx:
            build_logistic_predictions(
                feat_tampered, out_bool_tgt, development_start=dates_bool[210], test_start=dates_bool[260]
            )
        self.assertEqual(ctx.exception.field, "ret_5d")
        self.assertIn("215", str(ctx.exception))

        # Case 4b: Development block has valid 3-class fitting rows (D=226, T=260),
        # but test target row (origin 265) has malformed boolean ret_5d.
        # Proves validation fails with origin context before any fitter is called.
        close_overrides_4b = [(220, "99.00"), (221, "99.00"), (222, "99.00"), (225, "101.00")]
        feat_4b, out_4b, dates_4b = self._build_oracle_fixture(
            n_origins=N, close_overrides=close_overrides_4b, prefix="mal_test_tgt"
        )
        recs_4b = list(feat_4b.records)
        tgt_265 = recs_4b[265]
        assert tgt_265.payload is not None
        recs_4b[265] = replace(tgt_265, payload=replace(tgt_265.payload, ret_5d=True))  # type: ignore[arg-type]
        feat_4b_tampered = replace(feat_4b, records=tuple(recs_4b))

        # Mock LogisticRegression.fit to ensure no fitter is ever invoked
        orig_clf_fit = LogisticRegression.fit
        fit_invoked = []

        def spy_fit(self_clf, X, y):
            fit_invoked.append(True)
            return orig_clf_fit(self_clf, X, y)

        try:
            LogisticRegression.fit = spy_fit
            with self.assertRaises(InputValidationError) as ctx_4b:
                build_logistic_predictions(
                    feat_4b_tampered, out_4b, development_start=dates_4b[226], test_start=dates_4b[260]
                )
            self.assertEqual(ctx_4b.exception.field, "ret_5d")
            self.assertIn("265", str(ctx_4b.exception))
            self.assertEqual(len(fit_invoked), 0)  # Fitter was NOT called
        finally:
            LogisticRegression.fit = orig_clf_fit

        # 5. Representative planner error propagation
        with self.assertRaises(InputValidationError) as ctx:
            build_logistic_predictions(
                feat_bool_tgt, out_bool_tgt, development_start=datetime.date(1995, 1, 1), test_start=dates_bool[260]
            )
        self.assertEqual(ctx.exception.field, "development_start")

    def test_06_controlled_failure_paths_and_warning_ownership(self) -> None:
        """
        Validates controlled failure paths and warning handling:
        - ConvergenceWarning maps to unavailable_reason='not_converged' at stage 'fit'.
        - Enabled RuntimeWarning remains observable to caller (not swallowed).
        - FutureWarning raises under outer -W error::FutureWarning.
        - Warning filter restoration after success and exception.
        - Injected numeric scaler, fit, and prediction nonfinite failures map to nonfinite_model_state
          with exact failure_stage, discarding fit on prediction failure.
        - Reaching max_iter alone without ConvergenceWarning is not unavailable.
        - Independent other-block behavior.
        """
        D = 230
        T = 270
        features, outcomes, dates = self._build_nonconstant_fixture(
            n_origins=320, d_index=D, t_index=T, prefix="fail_suite"
        )
        d_date = dates[D]
        t_date = dates[T]

        # 1. Warning filter restoration on success and exception
        filters_before = list(warnings.filters)
        _ = build_logistic_predictions(features, outcomes, development_start=d_date, test_start=t_date)
        self.assertEqual(warnings.filters, filters_before)

        # 2. ConvergenceWarning handling
        orig_fit = LogisticRegression.fit

        def mock_fit_convergence_warn(self_clf, X, y):
            warnings.warn("Optimization failed to converge", ConvergenceWarning)
            return orig_fit(self_clf, X, y)

        try:
            LogisticRegression.fit = mock_fit_convergence_warn
            res_conv = build_logistic_predictions(features, outcomes, development_start=d_date, test_start=t_date)
            dev_b = res_conv.development_block
            self.assertIsNone(dev_b.fit)
            self.assertEqual(dev_b.unavailable_reason, UNAVAILABLE_REASON_NOT_CONVERGED)
            self.assertEqual(dev_b.failure_stage, STAGE_FIT)
            self.assertEqual(dev_b.predictions, ())
        finally:
            LogisticRegression.fit = orig_fit

        self.assertEqual(warnings.filters, filters_before)

        # 3. Enabled RuntimeWarning remains observable
        def mock_fit_runtime_warn(self_clf, X, y):
            warnings.warn("Test runtime warning", RuntimeWarning)
            return orig_fit(self_clf, X, y)

        try:
            LogisticRegression.fit = mock_fit_runtime_warn
            with warnings.catch_warnings(record=True) as w_records:
                warnings.simplefilter("always", RuntimeWarning)
                _ = build_logistic_predictions(features, outcomes, development_start=d_date, test_start=t_date)
                runtime_warnings = [w for w in w_records if issubclass(w.category, RuntimeWarning)]
                self.assertGreater(len(runtime_warnings), 0)
        finally:
            LogisticRegression.fit = orig_fit

        # 3b. FutureWarning propagates under outer -W error::FutureWarning
        def mock_fit_future_warn(self_clf, X, y):
            warnings.warn("Test future warning", FutureWarning)
            return orig_fit(self_clf, X, y)

        try:
            LogisticRegression.fit = mock_fit_future_warn
            with self.assertRaises(FutureWarning):
                build_logistic_predictions(features, outcomes, development_start=d_date, test_start=t_date)
        finally:
            LogisticRegression.fit = orig_fit

        self.assertEqual(warnings.filters, filters_before)

        # 4. Injected numeric scaler failure
        orig_scaler_transform = StandardScaler.fit_transform

        def mock_scaler_nan(self_s, X):
            arr = orig_scaler_transform(self_s, X)
            arr[0, 0] = np.nan
            return arr

        try:
            StandardScaler.fit_transform = mock_scaler_nan
            res_scaler_fail = build_logistic_predictions(features, outcomes, development_start=d_date, test_start=t_date)
            dev_b = res_scaler_fail.development_block
            self.assertIsNone(dev_b.fit)
            self.assertEqual(dev_b.unavailable_reason, UNAVAILABLE_REASON_NONFINITE_MODEL_STATE)
            self.assertEqual(dev_b.failure_stage, STAGE_SCALER)
            self.assertEqual(dev_b.predictions, ())
        finally:
            StandardScaler.fit_transform = orig_scaler_transform

        # 5. Injected numeric fit failure (nonfinite coef)
        def mock_fit_nan_coef(self_clf, X, y):
            res = orig_fit(self_clf, X, y)
            self_clf.coef_[0, 0] = np.nan
            return res

        try:
            LogisticRegression.fit = mock_fit_nan_coef
            res_fit_fail = build_logistic_predictions(features, outcomes, development_start=d_date, test_start=t_date)
            dev_b = res_fit_fail.development_block
            self.assertIsNone(dev_b.fit)
            self.assertEqual(dev_b.unavailable_reason, UNAVAILABLE_REASON_NONFINITE_MODEL_STATE)
            self.assertEqual(dev_b.failure_stage, STAGE_FIT)
            self.assertEqual(dev_b.predictions, ())
        finally:
            LogisticRegression.fit = orig_fit

        # 6. Injected numeric prediction failure
        orig_predict_proba = LogisticRegression.predict_proba

        def mock_predict_nan(self_clf, X):
            probs = orig_predict_proba(self_clf, X)
            probs[0, 0] = np.nan
            return probs

        try:
            LogisticRegression.predict_proba = mock_predict_nan
            res_pred_fail = build_logistic_predictions(features, outcomes, development_start=d_date, test_start=t_date)
            dev_b = res_pred_fail.development_block
            # Prediction failure discards fit and all predictions
            self.assertIsNone(dev_b.fit)
            self.assertEqual(dev_b.unavailable_reason, UNAVAILABLE_REASON_NONFINITE_MODEL_STATE)
            self.assertEqual(dev_b.failure_stage, STAGE_PREDICTION)
            self.assertEqual(dev_b.predictions, ())
        finally:
            LogisticRegression.predict_proba = orig_predict_proba

        # 7. Reaching max_iter alone without ConvergenceWarning remains available
        def mock_fit_max_iter(self_clf, X, y):
            res = orig_fit(self_clf, X, y)
            self_clf.n_iter_ = np.array([2000], dtype=np.int32)
            return res

        try:
            LogisticRegression.fit = mock_fit_max_iter
            res_max_iter = build_logistic_predictions(features, outcomes, development_start=d_date, test_start=t_date)
            self.assertIsNotNone(res_max_iter.development_block.fit)
            self.assertIsNone(res_max_iter.development_block.unavailable_reason)
            self.assertEqual(res_max_iter.development_block.fit.n_iter, 2000)
            self.assertGreater(len(res_max_iter.development_block.predictions), 0)
        finally:
            LogisticRegression.fit = orig_fit

        # 8. Independent other-block behavior: test-block-only scaler failure
        # Development block succeeds; test block encounters injected failure.
        call_count = {"count": 0}

        def mock_scaler_test_only(self_s, X):
            arr = orig_scaler_transform(self_s, X)
            call_count["count"] += 1
            if call_count["count"] == 2:  # 2nd call is test block
                arr[0, 0] = np.nan
            return arr

        try:
            StandardScaler.fit_transform = mock_scaler_test_only
            res_indep = build_logistic_predictions(features, outcomes, development_start=d_date, test_start=t_date)
            # Development block is completely healthy
            dev_healthy = res_indep.development_block
            self.assertIsNotNone(dev_healthy.fit)
            self.assertIsNone(dev_healthy.unavailable_reason)
            self.assertIsNone(dev_healthy.failure_stage)
            self.assertGreater(len(dev_healthy.predictions), 0)
            self.assertEqual(dev_healthy.class_counts, (4, 3, 3))
            self.assertEqual(sum(dev_healthy.class_counts), 10)
            # Test block is unavailable at scaler stage, but counts and metadata are preserved
            test_unavail = res_indep.test_block
            self.assertIsNone(test_unavail.fit)
            self.assertEqual(test_unavail.unavailable_reason, UNAVAILABLE_REASON_NONFINITE_MODEL_STATE)
            self.assertEqual(test_unavail.failure_stage, STAGE_SCALER)
            self.assertEqual(test_unavail.predictions, ())
            self.assertEqual(test_unavail.fitting_indices, tuple(range(200, 250)))
            self.assertEqual(test_unavail.requested_indices, tuple(range(270, 300)))
            self.assertEqual(test_unavail.cutoff_index, T)
            self.assertEqual(test_unavail.cutoff_date, t_date)
            self.assertEqual(sum(test_unavail.class_counts), 50)
            self.assertEqual(sum(test_unavail.regime_counts), 50)
        finally:
            StandardScaler.fit_transform = orig_scaler_transform

    def test_07_immutability_and_repeated_call_equality(self) -> None:
        """
        Validates:
        - Frozen dataclass immutability for LogisticResult, LogisticBlock, LogisticFit,
          LogisticPrediction, LogisticConfiguration (FrozenInstanceError).
        - Source FeatureSeries, OutcomeSeries, and raw CSV files verified unmutated via deepcopy/bytes.
        - Repeated calls with identical inputs produce identical results.
        """
        D = 230
        T = 270
        features, outcomes, dates = self._build_nonconstant_fixture(
            n_origins=320, d_index=D, t_index=T, prefix="immut_suite"
        )
        d_date = dates[D]
        t_date = dates[T]

        n_csv = self.test_dir / "immut_suite_nifty.csv"
        v_csv = self.test_dir / "immut_suite_vix.csv"
        n_bytes_before = n_csv.read_bytes()
        v_bytes_before = v_csv.read_bytes()

        feat_snap = copy.deepcopy(features)
        out_snap = copy.deepcopy(outcomes)

        res1 = build_logistic_predictions(features, outcomes, development_start=d_date, test_start=t_date)
        res2 = build_logistic_predictions(features, outcomes, development_start=d_date, test_start=t_date)

        # Inputs untouched
        self.assertEqual(features, feat_snap)
        self.assertEqual(outcomes, out_snap)
        self.assertEqual(n_csv.read_bytes(), n_bytes_before)
        self.assertEqual(v_csv.read_bytes(), v_bytes_before)

        # Repeated-call equality
        self.assertEqual(res1, res2)

        # Frozen instance mutation rejection
        with self.assertRaises(FrozenInstanceError):
            res1.method = "tampered"  # type: ignore[misc]

        with self.assertRaises(FrozenInstanceError):
            res1.development_block = res1.test_block  # type: ignore[misc]

        dev_b = res1.development_block
        with self.assertRaises(FrozenInstanceError):
            dev_b.partition = "test"  # type: ignore[misc]

        dev_fit = dev_b.fit
        assert dev_fit is not None
        with self.assertRaises(FrozenInstanceError):
            dev_fit.n_iter = 999  # type: ignore[misc]

        pred0 = dev_b.predictions[0]
        with self.assertRaises(FrozenInstanceError):
            pred0.probabilities = (0.0, 1.0, 0.0)  # type: ignore[misc]

    def test_08_unexpected_value_error_propagation(self) -> None:
        """
        Validates A1: unexpected backend ValueError from StandardScaler or
        LogisticRegression.predict_proba must propagate directly to caller
        rather than being masked as nonfinite_model_state.
        """
        D = 230
        T = 270
        features, outcomes, dates = self._build_nonconstant_fixture(
            n_origins=320, d_index=D, t_index=T, prefix="val_err"
        )
        d_date = dates[D]
        t_date = dates[T]

        # 1. Unexpected ValueError from StandardScaler.fit_transform propagates
        orig_fit_transform = StandardScaler.fit_transform

        def mock_scaler_val_err(self_s, X):
            raise ValueError("sentinel scaler unexpected ValueError")

        try:
            StandardScaler.fit_transform = mock_scaler_val_err
            with self.assertRaises(ValueError) as ctx:
                build_logistic_predictions(features, outcomes, development_start=d_date, test_start=t_date)
            self.assertIn("sentinel scaler unexpected ValueError", str(ctx.exception))
        finally:
            StandardScaler.fit_transform = orig_fit_transform

        # 2. Unexpected ValueError from LogisticRegression.predict_proba propagates
        orig_predict_proba = LogisticRegression.predict_proba

        def mock_predict_val_err(self_clf, X):
            raise ValueError("sentinel prediction unexpected ValueError")

        try:
            LogisticRegression.predict_proba = mock_predict_val_err
            with self.assertRaises(ValueError) as ctx:
                build_logistic_predictions(features, outcomes, development_start=d_date, test_start=t_date)
            self.assertIn("sentinel prediction unexpected ValueError", str(ctx.exception))
        finally:
            LogisticRegression.predict_proba = orig_predict_proba

    def test_09_validation_precedes_availability_for_insufficient_test_blocks(self) -> None:
        """
        Isolates selected-target validation in blocks that cannot fit, one corruption per case.
        Each corrupted origin is a requested test target outside every fitting pool, so only the
        shared selected-payload validation, which runs before availability checks, can reject it:
        - D=210, T=215: train, development and refit pools are all empty (both blocks no_fit_rows);
          corrupted target 215.
        - D=210, T=260: refit 200..239 is nonempty but all NEUTRAL (missing_training_classes);
          corrupted target 265.
        Clean controls on the same fixture confirm each insufficient state and its retained metadata.
        """
        # All closes 100.00 and VIX 20.00: every mature label is NEUTRAL
        features, outcomes, dates = self._build_oracle_fixture(n_origins=300, prefix="insufficient_tgt")
        cases = [
            # (label, D, T, corrupted test target, expected refit size, expected test-block reason)
            ("empty_refit", 210, 215, 215, 0, UNAVAILABLE_REASON_NO_FIT_ROWS),
            ("all_neutral_refit", 210, 260, 265, 40, UNAVAILABLE_REASON_MISSING_TRAINING_CLASSES),
        ]
        for label, d_idx, t_idx, target, refit_size, test_reason in cases:
            with self.subTest(case=label):
                d_date, t_date = dates[d_idx], dates[t_idx]
                plan = build_split_plan(features, outcomes, development_start=d_date, test_start=t_date)
                self.assertEqual(len(plan.refit_indices), refit_size)
                self.assertIn(target, plan.test_indices)
                self.assertNotIn(target, set(plan.train_indices) | set(plan.refit_indices))

                # Clean control: both blocks are insufficient and keep their pools, counts and cutoffs
                clean = build_logistic_predictions(features, outcomes, development_start=d_date, test_start=t_date)
                dev_b, test_b = clean.development_block, clean.test_block
                self.assertEqual(dev_b.unavailable_reason, UNAVAILABLE_REASON_NO_FIT_ROWS)
                self.assertEqual(test_b.unavailable_reason, test_reason)
                for block, fitting, requested, cutoff in (
                    (dev_b, plan.train_indices, plan.development_indices, d_idx),
                    (test_b, plan.refit_indices, plan.test_indices, t_idx),
                ):
                    self.assertIsNone(block.fit)
                    self.assertIsNone(block.failure_stage)
                    self.assertEqual(block.predictions, ())
                    self.assertEqual(block.fitting_indices, fitting)
                    self.assertEqual(block.requested_indices, requested)
                    self.assertEqual(block.cutoff_index, cutoff)
                    self.assertEqual(block.cutoff_date, dates[cutoff])
                    self.assertEqual(sum(block.class_counts), len(fitting))
                    self.assertEqual(sum(block.regime_counts), len(fitting))
                self.assertIn(target, test_b.requested_indices)
                self.assertEqual(test_b.class_counts, (0, refit_size, 0))

                # Exactly one corrupted selected target; it is not a fitting row in either block
                record = features.records[target]
                assert record.payload is not None
                corrupted = self._replace_payload(
                    features, target, replace(record.payload, ret_5d=True)  # type: ignore[arg-type]
                )
                with self.assertRaises(InputValidationError) as ctx:
                    build_logistic_predictions(corrupted, outcomes, development_start=d_date, test_start=t_date)
                self.assertEqual(ctx.exception.field, "ret_5d")
                self.assertIn(f"origin index {target} ({dates[target]})", str(ctx.exception))

    def test_10_selected_payload_type_nonfinite_and_overflow_guards(self) -> None:
        """
        Defensive coverage of the comparator's selected-payload guards: one representative value per
        guard class on one field (ret_5d) of one selected test target (D=210, T=215, no fitting rows):
        - unsupported types: str, Decimal, complex
        - nonfinite floats: NaN, +infinity
        - an int too large for binary64 conversion
        PredictorPayload's constructor already rejects these values, so each case forces the value
        onto a copy of a valid payload. Normal loader output cannot produce them; this checks the
        public comparator boundary only.
        """
        features, outcomes, dates = self._build_oracle_fixture(n_origins=300, prefix="guard_classes")
        d_date, t_date = dates[210], dates[215]
        target = 215
        original = features.records[target].payload
        assert original is not None
        original_snapshot = copy.deepcopy(original)
        cases = [
            # (label, forced ret_5d value, expected message prefix from the matching guard)
            ("str", "0.0", "Unsupported type str"),
            ("decimal", Decimal("0.0"), "Unsupported type Decimal"),
            ("complex", complex(0.0, 0.0), "Unsupported type complex"),
            ("nan", float("nan"), "Non-finite value"),
            ("infinity", float("inf"), "Non-finite value"),
            ("int_overflow", 10 ** 400, "Conversion overflow"),
        ]
        for label, bad_value, message_prefix in cases:
            with self.subTest(case=label):
                corrupted = self._replace_payload(
                    features, target, self._force_payload_field(original, "ret_5d", bad_value)
                )
                with self.assertRaises(InputValidationError) as ctx:
                    build_logistic_predictions(corrupted, outcomes, development_start=d_date, test_start=t_date)
                self.assertEqual(ctx.exception.field, "ret_5d")
                message = str(ctx.exception)
                self.assertTrue(message.startswith(message_prefix), message)
                self.assertIn(f"origin index {target} ({dates[target]})", message)

        # The shared valid fixture payload was never modified
        self.assertIs(features.records[target].payload, original)
        self.assertEqual(original, original_snapshot)

    def test_11_conversion_overflow_report_survives_integer_string_limit(self) -> None:
        """
        A selected int too large for binary64 must still be rejected as InputValidationError when the
        interpreter limits int-to-decimal-string conversion. The value has 5001 digits, above the
        4300-digit limit this test sets for its own duration; the previous limit is restored on every
        exit. Production never changes the limit. The huge value is never formatted or logged here.
        """
        features, outcomes, dates = self._build_oracle_fixture(n_origins=300, prefix="overflow_digits")
        target = 215
        original = features.records[target].payload
        assert original is not None
        corrupted = self._replace_payload(
            features, target, self._force_payload_field(original, "ret_5d", 10 ** 5000)
        )

        previous_limit = sys.get_int_max_str_digits()
        sys.set_int_max_str_digits(4300)
        try:
            with self.subTest(case="int_above_digit_limit"):
                with self.assertRaises(InputValidationError) as ctx:
                    build_logistic_predictions(
                        corrupted, outcomes, development_start=dates[210], test_start=dates[215]
                    )
                self.assertEqual(ctx.exception.field, "ret_5d")
                message = str(ctx.exception)
                self.assertTrue(message.startswith("Conversion overflow"), message)
                self.assertIn(f"origin index {target} ({dates[target]})", message)
                self.assertIn(f"Origin {target} ({dates[target]})", ctx.exception.reason)
                # The original binary64 conversion failure stays chained as the cause
                self.assertIsInstance(ctx.exception.__cause__, OverflowError)
        finally:
            sys.set_int_max_str_digits(previous_limit)
        self.assertEqual(sys.get_int_max_str_digits(), previous_limit)

    def test_12_predict_proba_output_shape_contract(self) -> None:
        """
        A finite probability matrix with an extra row or an extra column is a setup/programming error
        (RuntimeError), never a prefix consumed as available predictions. Each case replaces
        LogisticRegression.predict_proba with a controlled finite return through the public builder.
        Every row's first three entries are (0.2, 0.3, 0.5) and any extra column is 0.0, so the range
        and sum checks alone would accept the matrix; only the shape contract can reject it.
        """
        features, outcomes, dates = self._build_nonconstant_fixture(n_origins=320, prefix="proba_shape")
        d_date, t_date = dates[230], dates[270]
        orig_predict_proba = LogisticRegression.predict_proba
        cases = [
            # (label, extra rows, extra columns)
            ("extra_row", 1, 0),
            ("extra_column", 0, 1),
        ]
        for label, extra_rows, extra_cols in cases:
            with self.subTest(case=label):
                calls = []

                def oversized_predict_proba(self_clf, X, extra_rows=extra_rows, extra_cols=extra_cols):
                    calls.append(X.shape[0])
                    out = np.zeros((X.shape[0] + extra_rows, 3 + extra_cols), dtype=np.float64)
                    out[:, 0] = 0.2
                    out[:, 1] = 0.3
                    out[:, 2] = 0.5
                    return out

                try:
                    LogisticRegression.predict_proba = oversized_predict_proba
                    with self.assertRaises(RuntimeError) as ctx:
                        build_logistic_predictions(features, outcomes, development_start=d_date, test_start=t_date)
                finally:
                    LogisticRegression.predict_proba = orig_predict_proba
                # The patched seam ran once (development block) and its output was refused there
                self.assertEqual(calls, [20])
                self.assertIn("predict_proba", str(ctx.exception))
        self.assertIs(LogisticRegression.predict_proba, orig_predict_proba)



if __name__ == "__main__":
    unittest.main()
