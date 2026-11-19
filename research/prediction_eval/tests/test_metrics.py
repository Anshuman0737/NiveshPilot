"""
Unit tests for Prediction Evaluation Scoring and Multi-Model Comparison.

Validates:
1. Canonical Three-Class Toy Oracle and Inspectable Synthetic Scorecard Diagnostic:
   - Emits exactly one single stdout line starting with 'SYNTHETIC_SCORECARD '.
   - Tests independent Decimal/Fraction expected values for heuristic, frequency, and logistic.
   - Verifies explicit ISO dates, key preservation, confusion matrix, and tie counts.
2. Independent Acceptance Oracles:
   - Perfect one-hot (Brier 0, log 0, correct).
   - Wrong one-hot (Brier 2, infinite log loss, zero count 1).
   - Non-actual zero probability is finite; tiny positive actual probability (5e-324) is finite.
   - Uniform distribution (Brier 2/3, log ln 3, predicted BEAR, tie_count 1).
   - Three uniform rows across three classes: tie_count 3, accuracy 1/3.
   - Class mapping check: actual NEUTRAL with (0.1, 0.8, 0.1) vs (0.1, 0.1, 0.8).
3. Tie Breaking and Non-Maximum Count Policies:
   - Top ties: (0.4, 0.2, 0.4) -> BEAR / tie=1; (0.2, 0.4, 0.4) -> NEUTRAL / tie=1.
   - Equal non-maxima: (0.2, 0.2, 0.6) -> BULL / tie=0.
   - Near-ties with distinct floats -> tie=0.
4. Descriptive Reliability Calibration Bins:
   - Ten bins in class-major order (30 bins per model).
   - Interior edge transitions: exact 0.9 -> bin 9, nextafter(0.9, 0) -> bin 8, exact 0 -> bin 0, exact 1 -> bin 9.
   - Upper neighbor nextafter(j/10, 1) -> bin j for every interior edge, isolated per edge, for every model.
   - Empty bin identity, count conservation (N per class, 3N total per model).
   - Fixed classes, bin edges and full (class_label, bin_index) order for every model, scored and empty.
5. 21-Row Sequence and Key Preservation:
   - 20 perfect rows + 1 wrong one-hot -> mean Brier 2/21.
   - Exhaustive (index, date) key verification across all rows without dropping.
6. Empty Cohort (N=0) Policy:
   - status='empty', sample_count=0, support=(0,0,0), zero confusion, recalls None,
     accuracy None, mean_brier None, mean_log_loss None, log state 'empty', 30 empty bins.
7. Cohort Alignment and Rejection:
   - Missing row in one method, extra row, out-of-order row, mismatched index/date.
   - Same missing row in all three methods against the explicit cohort.
8. Negative Input Validation:
   - Non-list/tuple container, non-integer index, bool index, datetime instead of date.
   - Invalid actual_class, non-increasing index, non-increasing date.
   - Huge integer probability rejection without overflow.
   - Negative, >1, NaN, Inf, non-tuple probabilities, sum != 1.0 (deviating > 1e-12).
   - Representative errors carry method and row position (or method and counts for length errors).
9. Structural Compatibility and Import Isolation:
   - Genuine FrequencyPrediction structural protocol compatibility without fitting.
   - Clean standard-library import isolation: confirms logistic and sklearn are NOT imported.
10. Immutability and Input Preservation:
    - Verifies frozen dataclass behavior on all returned structures.
    - Mutating caller input containers after scoring leaves results unmodified.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import datetime
import decimal
from decimal import Decimal
from fractions import Fraction
import json
import math
import sys
import unittest
from typing import Any, List, NamedTuple, Tuple

from research.prediction_eval.inputs import InputValidationError
from research.prediction_eval.outcomes import (
    OUTCOME_CLASS_BEAR,
    OUTCOME_CLASS_BULL,
    OUTCOME_CLASS_NEUTRAL,
)
from research.prediction_eval.frequency import FrequencyPrediction
from research.prediction_eval.metrics import (
    BIN_EDGES,
    CLASSES,
    ComparisonMetrics,
    EvaluationOrigin,
    INTERIOR_EDGES,
    LOG_LOSS_STATE_EMPTY,
    LOG_LOSS_STATE_FINITE,
    LOG_LOSS_STATE_INFINITE,
    ModelMetrics,
    PredictionLike,
    PROTOCOL_ID,
    ReliabilityBin,
    RowScore,
    STATUS_EMPTY,
    STATUS_SCORED,
    score_comparison,
)


class MockPrediction(NamedTuple):
    origin_index: int
    origin_date: datetime.date
    probabilities: Tuple[float, float, float]


class TestPredictionEvalMetrics(unittest.TestCase):
    """Test suite for research/prediction_eval/metrics.py."""

    def test_toy_oracle_and_synthetic_scorecard_emission(self) -> None:
        """
        Validates the 3-class mixed toy oracle using independent Fraction/Decimal arithmetic
        and emits exactly one SYNTHETIC_SCORECARD line to stdout for inspectable verification.
        """
        d1 = datetime.date(2024, 1, 15)
        d2 = datetime.date(2024, 2, 1)
        d3 = datetime.date(2024, 2, 20)

        origins = [
            EvaluationOrigin(origin_index=10, origin_date=d1, actual_class=OUTCOME_CLASS_BEAR),
            EvaluationOrigin(origin_index=25, origin_date=d2, actual_class=OUTCOME_CLASS_NEUTRAL),
            EvaluationOrigin(origin_index=42, origin_date=d3, actual_class=OUTCOME_CLASS_BULL),
        ]

        # Toy heuristic vectors
        h_preds = [
            MockPrediction(10, d1, (0.6, 0.3, 0.1)),
            MockPrediction(25, d2, (0.2, 0.5, 0.3)),
            MockPrediction(42, d3, (0.4, 0.2, 0.4)),
        ]

        # Toy frequency vectors (perfect one-hot)
        f_preds = [
            MockPrediction(10, d1, (1.0, 0.0, 0.0)),
            MockPrediction(25, d2, (0.0, 1.0, 0.0)),
            MockPrediction(42, d3, (0.0, 0.0, 1.0)),
        ]

        # Toy logistic vectors (uniform)
        u_prob = 1.0 / 3.0
        l_preds = [
            MockPrediction(10, d1, (u_prob, u_prob, u_prob)),
            MockPrediction(25, d2, (u_prob, u_prob, u_prob)),
            MockPrediction(42, d3, (u_prob, u_prob, u_prob)),
        ]

        res = score_comparison(origins, heuristic=h_preds, frequency=f_preds, logistic=l_preds)

        self.assertEqual(res.protocol_id, PROTOCOL_ID)
        self.assertEqual(res.status, STATUS_SCORED)
        self.assertEqual(res.sample_count, 3)
        self.assertEqual(res.class_support, (1, 1, 1))

        # Independent verification of Heuristic
        # Row 0: actual BEAR, (0.6, 0.3, 0.1) -> Brier = (-0.4)^2 + 0.3^2 + 0.1^2 = 0.26 = 13/50
        # Row 1: actual NEUTRAL, (0.2, 0.5, 0.3) -> Brier = 0.2^2 + (-0.5)^2 + 0.3^2 = 0.38 = 19/50
        # Row 2: actual BULL, (0.4, 0.2, 0.4) -> Brier = 0.4^2 + 0.2^2 + (-0.6)^2 = 0.56 = 28/50
        # Mean Brier: (0.26 + 0.38 + 0.56) / 3 = 1.20 / 3 = 0.40 = 2/5
        self.assertAlmostEqual(res.heuristic.row_scores[0].brier, float(Fraction(13, 50)), places=12)
        self.assertAlmostEqual(res.heuristic.row_scores[1].brier, float(Fraction(19, 50)), places=12)
        self.assertAlmostEqual(res.heuristic.row_scores[2].brier, float(Fraction(28, 50)), places=12)
        self.assertAlmostEqual(res.heuristic.mean_brier, float(Fraction(2, 5)), places=12)

        # Heuristic predictions: Row 0 -> BEAR, Row 1 -> NEUTRAL, Row 2 -> BEAR (tie 0.4 vs 0.4 selects BEAR)
        self.assertEqual(res.heuristic.row_scores[0].predicted_class, OUTCOME_CLASS_BEAR)
        self.assertEqual(res.heuristic.row_scores[1].predicted_class, OUTCOME_CLASS_NEUTRAL)
        self.assertEqual(res.heuristic.row_scores[2].predicted_class, OUTCOME_CLASS_BEAR)
        self.assertEqual(res.heuristic.tie_count, 1)
        self.assertEqual(res.heuristic.zero_actual_probability_count, 0)
        self.assertAlmostEqual(res.heuristic.accuracy, float(Fraction(2, 3)), places=12)
        self.assertEqual(
            res.heuristic.confusion,
            (
                (1, 0, 0),
                (0, 1, 0),
                (1, 0, 0),
            ),
        )
        self.assertEqual(res.heuristic.class_recall, (1.0, 1.0, 0.0))

        # Independent log loss: (-ln(0.6) - ln(0.5) - ln(0.4)) / 3 via isolated Decimal.from_float
        with decimal.localcontext() as dec_ctx:
            dec_ctx.prec = 50
            d_p0 = Decimal.from_float(0.6)
            d_p1 = Decimal.from_float(0.5)
            d_p2 = Decimal.from_float(0.4)
            d_h_log_sum = -(d_p0.ln() + d_p1.ln() + d_p2.ln())
            expected_h_log = float(d_h_log_sum / Decimal(3))

        self.assertEqual(res.heuristic.log_loss_state, LOG_LOSS_STATE_FINITE)
        self.assertIsNotNone(res.heuristic.mean_log_loss)
        self.assertAlmostEqual(res.heuristic.mean_log_loss, expected_h_log, places=12)

        # Independent verification of Frequency (perfect one-hot)
        self.assertAlmostEqual(res.frequency.mean_brier, 0.0, places=12)
        self.assertAlmostEqual(res.frequency.accuracy, 1.0, places=12)
        self.assertEqual(res.frequency.tie_count, 0)
        self.assertEqual(res.frequency.zero_actual_probability_count, 0)
        self.assertEqual(res.frequency.log_loss_state, LOG_LOSS_STATE_FINITE)
        self.assertAlmostEqual(res.frequency.mean_log_loss, 0.0, places=12)
        self.assertEqual(
            res.frequency.confusion,
            (
                (1, 0, 0),
                (0, 1, 0),
                (0, 0, 1),
            ),
        )
        self.assertEqual(res.frequency.class_recall, (1.0, 1.0, 1.0))

        # Independent verification of Logistic (uniform 1/3)
        # Brier per row: (1/3 - 1)^2 + (1/3 - 0)^2 + (1/3 - 0)^2 = 4/9 + 1/9 + 1/9 = 6/9 = 2/3
        self.assertAlmostEqual(res.logistic.mean_brier, float(Fraction(2, 3)), places=12)
        self.assertAlmostEqual(res.logistic.accuracy, float(Fraction(1, 3)), places=12)
        self.assertEqual(res.logistic.tie_count, 3)
        self.assertEqual(res.logistic.zero_actual_probability_count, 0)
        self.assertEqual(res.logistic.log_loss_state, LOG_LOSS_STATE_FINITE)

        with decimal.localcontext() as dec_ctx:
            dec_ctx.prec = 50
            d_u = Decimal.from_float(u_prob)
            expected_l_log = float(-d_u.ln())

        self.assertAlmostEqual(res.logistic.mean_log_loss, expected_l_log, places=12)
        self.assertEqual(
            res.logistic.confusion,
            (
                (1, 0, 0),
                (1, 0, 0),
                (1, 0, 0),
            ),
        )
        self.assertEqual(res.logistic.class_recall, (1.0, 0.0, 0.0))

        # Build and emit inspectable synthetic scorecard line from ACTUAL results
        scorecard_payload = {
            "fixture_kind": "synthetic_probability_vectors_not_fitted_models",
            "protocol_id": res.protocol_id,
            "status": res.status,
            "sample_count": res.sample_count,
            "class_support": list(res.class_support),
            "origins": [
                {"origin_index": o.origin_index, "origin_date": o.origin_date.isoformat(), "actual_class": o.actual_class}
                for o in res.origins
            ],
            "heuristic": {
                "mean_brier": res.heuristic.mean_brier,
                "mean_log_loss": res.heuristic.mean_log_loss,
                "log_loss_state": res.heuristic.log_loss_state,
                "accuracy": res.heuristic.accuracy,
                "tie_count": res.heuristic.tie_count,
                "zero_actual_probability_count": res.heuristic.zero_actual_probability_count,
                "confusion": [list(row) for row in res.heuristic.confusion],
                "class_recall": list(res.heuristic.class_recall),
            },
            "frequency": {
                "mean_brier": res.frequency.mean_brier,
                "mean_log_loss": res.frequency.mean_log_loss,
                "log_loss_state": res.frequency.log_loss_state,
                "accuracy": res.frequency.accuracy,
                "tie_count": res.frequency.tie_count,
                "zero_actual_probability_count": res.frequency.zero_actual_probability_count,
                "confusion": [list(row) for row in res.frequency.confusion],
                "class_recall": list(res.frequency.class_recall),
            },
            "logistic": {
                "mean_brier": res.logistic.mean_brier,
                "mean_log_loss": res.logistic.mean_log_loss,
                "log_loss_state": res.logistic.log_loss_state,
                "accuracy": res.logistic.accuracy,
                "tie_count": res.logistic.tie_count,
                "zero_actual_probability_count": res.logistic.zero_actual_probability_count,
                "confusion": [list(row) for row in res.logistic.confusion],
                "class_recall": list(res.logistic.class_recall),
            },
        }

        # Print single strictly formatted JSON line for native test-output extraction
        print(f"SYNTHETIC_SCORECARD {json.dumps(scorecard_payload, allow_nan=False)}")

    def test_loss_oracles_one_hot_wrong_and_infinite_log(self) -> None:
        """Validates perfect one-hot, wrong one-hot, non-actual zeros, and infinite log loss."""
        d = datetime.date(2024, 3, 1)
        origin = [EvaluationOrigin(0, d, OUTCOME_CLASS_BULL)]

        # Perfect one-hot
        h_perf = [MockPrediction(0, d, (0.0, 0.0, 1.0))]
        res_perf = score_comparison(origin, heuristic=h_perf, frequency=h_perf, logistic=h_perf)
        self.assertAlmostEqual(res_perf.heuristic.mean_brier, 0.0, places=12)
        self.assertAlmostEqual(res_perf.heuristic.mean_log_loss, 0.0, places=12)
        self.assertEqual(res_perf.heuristic.log_loss_state, LOG_LOSS_STATE_FINITE)
        self.assertEqual(res_perf.heuristic.zero_actual_probability_count, 0)
        self.assertAlmostEqual(res_perf.heuristic.accuracy, 1.0, places=12)

        # Wrong one-hot: actual BULL, predicted BEAR with prob 1.0
        # Brier: (1-0)^2 + (0-0)^2 + (0-1)^2 = 2.0
        h_wrong = [MockPrediction(0, d, (1.0, 0.0, 0.0))]
        res_wrong = score_comparison(origin, heuristic=h_wrong, frequency=h_wrong, logistic=h_wrong)
        self.assertAlmostEqual(res_wrong.heuristic.mean_brier, 2.0, places=12)
        self.assertIsNone(res_wrong.heuristic.mean_log_loss)
        self.assertEqual(res_wrong.heuristic.log_loss_state, LOG_LOSS_STATE_INFINITE)
        self.assertEqual(res_wrong.heuristic.zero_actual_probability_count, 1)
        self.assertAlmostEqual(res_wrong.heuristic.accuracy, 0.0, places=12)

        # Tiny positive probability (5e-324) is finite and must not be floored or clipped to zero
        # With actual BULL: (0.5, 0.5 - 5e-324, 5e-324)
        tiny_p = 5e-324
        h_tiny = [MockPrediction(0, d, (0.5, 0.5 - tiny_p, tiny_p))]
        res_tiny = score_comparison(origin, heuristic=h_tiny, frequency=h_tiny, logistic=h_tiny)
        self.assertEqual(res_tiny.heuristic.log_loss_state, LOG_LOSS_STATE_FINITE)
        self.assertEqual(res_tiny.heuristic.zero_actual_probability_count, 0)
        self.assertIsNotNone(res_tiny.heuristic.mean_log_loss)
        with decimal.localcontext() as dec_ctx:
            dec_ctx.prec = 50
            d_tiny = Decimal.from_float(tiny_p)
            expected_tiny_log = float(-d_tiny.ln())
        self.assertTrue(math.isclose(res_tiny.heuristic.mean_log_loss, expected_tiny_log, rel_tol=1e-12, abs_tol=1e-12))

    def test_class_mapping_sensitivity(self) -> None:
        """Validates that class mapping sensitively distinguishes actual NEUTRAL vs BULL."""
        d = datetime.date(2024, 3, 5)
        orig_neutral = [EvaluationOrigin(0, d, OUTCOME_CLASS_NEUTRAL)]

        # Actual NEUTRAL with p=(0.1, 0.8, 0.1)
        # Brier: (0.1)^2 + (0.8 - 1)^2 + (0.1)^2 = 0.01 + 0.04 + 0.01 = 0.06
        pred_a = [MockPrediction(0, d, (0.1, 0.8, 0.1))]
        res_a = score_comparison(orig_neutral, heuristic=pred_a, frequency=pred_a, logistic=pred_a)
        self.assertAlmostEqual(res_a.heuristic.mean_brier, 0.06, places=12)
        self.assertAlmostEqual(res_a.heuristic.accuracy, 1.0, places=12)

        # Swapping neutral/bull: p=(0.1, 0.1, 0.8) with actual NEUTRAL
        # Brier: (0.1)^2 + (0.1 - 1)^2 + (0.8)^2 = 0.01 + 0.81 + 0.64 = 1.46
        pred_b = [MockPrediction(0, d, (0.1, 0.1, 0.8))]
        res_b = score_comparison(orig_neutral, heuristic=pred_b, frequency=pred_b, logistic=pred_b)
        self.assertAlmostEqual(res_b.heuristic.mean_brier, 1.46, places=12)
        self.assertAlmostEqual(res_b.heuristic.accuracy, 0.0, places=12)

    def test_tie_breaking_and_equal_non_maxima_policy(self) -> None:
        """Validates first-max selection, tie count increments, and non-max equality ignoring."""
        d1 = datetime.date(2024, 4, 1)
        d2 = datetime.date(2024, 4, 2)
        d3 = datetime.date(2024, 4, 3)
        origins = [
            EvaluationOrigin(0, d1, OUTCOME_CLASS_BULL),
            EvaluationOrigin(1, d2, OUTCOME_CLASS_BULL),
            EvaluationOrigin(2, d3, OUTCOME_CLASS_BULL),
        ]

        # Row 0: (0.4, 0.2, 0.4) -> top tie BEAR/BULL -> selects BEAR, tie_count 1
        # Row 1: (0.2, 0.4, 0.4) -> top tie NEUTRAL/BULL -> selects NEUTRAL, tie_count 1
        # Row 2: (0.2, 0.2, 0.6) -> equal lower non-max (0.2 == 0.2 < 0.6) -> selects BULL, tie_count 0
        preds = [
            MockPrediction(0, d1, (0.4, 0.2, 0.4)),
            MockPrediction(1, d2, (0.2, 0.4, 0.4)),
            MockPrediction(2, d3, (0.2, 0.2, 0.6)),
        ]

        res = score_comparison(origins, heuristic=preds, frequency=preds, logistic=preds)
        self.assertEqual(res.heuristic.row_scores[0].predicted_class, OUTCOME_CLASS_BEAR)
        self.assertEqual(res.heuristic.row_scores[1].predicted_class, OUTCOME_CLASS_NEUTRAL)
        self.assertEqual(res.heuristic.row_scores[2].predicted_class, OUTCOME_CLASS_BULL)
        self.assertEqual(res.heuristic.tie_count, 2)

    def test_reliability_bins_edges_and_count_conservation(self) -> None:
        """
        Validates 10 reliability bins per class, interior edge equality to the right,
        shared-bin mean and observed frequency, all 9 interior edge transitions,
        isolated upper neighbors of every interior edge for all three models,
        and count conservation (N per class, 3N total per model).
        """
        d1 = datetime.date(2024, 5, 1)
        d2 = datetime.date(2024, 5, 2)
        d3 = datetime.date(2024, 5, 3)
        d4 = datetime.date(2024, 5, 4)
        d5 = datetime.date(2024, 5, 5)
        d6 = datetime.date(2024, 5, 6)

        # 1. Shared-bin oracle for bin 1 [0.1, 0.2):
        # Three BEAR probabilities: 0.11, 0.12, 0.19.
        # Row 0: actual BEAR (1)
        # Row 1: actual NEUTRAL (0)
        # Row 2: actual NEUTRAL (0)
        # Sum = 0.42, count = 3 -> mean_probability = 0.14, observed_frequency = 1/3
        # Plus boundary rows:
        # Row 3: BEAR p=0.0 -> bin 0
        # Row 4: BEAR p=math.nextafter(0.9, 0.0) -> bin 8
        # Row 5: BEAR p=0.9 -> bin 9 (interior edge equality to the right: [0.9, 1.0])
        p_below_09 = math.nextafter(0.9, 0.0)
        origins = [
            EvaluationOrigin(0, d1, OUTCOME_CLASS_BEAR),
            EvaluationOrigin(1, d2, OUTCOME_CLASS_NEUTRAL),
            EvaluationOrigin(2, d3, OUTCOME_CLASS_NEUTRAL),
            EvaluationOrigin(3, d4, OUTCOME_CLASS_BEAR),
            EvaluationOrigin(4, d5, OUTCOME_CLASS_BULL),
            EvaluationOrigin(5, d6, OUTCOME_CLASS_BULL),
        ]
        preds = [
            MockPrediction(0, d1, (0.11, 0.49, 0.40)),
            MockPrediction(1, d2, (0.12, 0.48, 0.40)),
            MockPrediction(2, d3, (0.19, 0.41, 0.40)),
            MockPrediction(3, d4, (0.0, 0.50, 0.50)),
            MockPrediction(4, d5, (p_below_09, (1.0 - p_below_09) / 2.0, (1.0 - p_below_09) / 2.0)),
            MockPrediction(5, d6, (0.9, 0.05, 0.05)),
        ]

        res = score_comparison(origins, heuristic=preds, frequency=preds, logistic=preds)
        bins = res.heuristic.reliability_bins

        # Total 30 bins: 10 for BEAR, 10 for NEUTRAL, 10 for BULL in class-major order
        self.assertEqual(len(bins), 30)

        bear_bins = [b for b in bins if b.class_label == OUTCOME_CLASS_BEAR]
        self.assertEqual(len(bear_bins), 10)

        # Bin 0: p=0.0, count=1, mean=0.0, freq=1.0 (row 3 is BEAR)
        self.assertEqual(bear_bins[0].count, 1)
        self.assertEqual(bear_bins[0].mean_probability, 0.0)
        self.assertEqual(bear_bins[0].observed_frequency, 1.0)

        # Bin 1: Shared-bin oracle: 0.11, 0.12, 0.19 -> count=3, mean=0.14, freq=1/3
        self.assertEqual(bear_bins[1].count, 3)
        self.assertAlmostEqual(bear_bins[1].mean_probability, 0.14, places=12)
        self.assertAlmostEqual(bear_bins[1].observed_frequency, 1.0 / 3.0, places=12)

        # Bin 8: nextafter(0.9, 0.0) -> count=1, mean=p_below_09, freq=0.0 (row 4 is BULL)
        self.assertEqual(bear_bins[8].count, 1)
        self.assertAlmostEqual(bear_bins[8].mean_probability, p_below_09, places=12)
        self.assertEqual(bear_bins[8].observed_frequency, 0.0)

        # Bin 9: exact 0.9 -> count=1, mean=0.9, freq=0.0 (row 5 is BULL)
        self.assertEqual(bear_bins[9].count, 1)
        self.assertAlmostEqual(bear_bins[9].mean_probability, 0.9, places=12)
        self.assertEqual(bear_bins[9].observed_frequency, 0.0)

        # Count conservation: sum of counts for each class must equal N (6)
        for cls in CLASSES:
            cls_bins = [b for b in bins if b.class_label == cls]
            self.assertEqual(sum(b.count for b in cls_bins), 6)

        # Sum across all 3 classes must equal 3N (18)
        self.assertEqual(sum(b.count for b in bins), 18)

        # 2. Comprehensive check of all nine interior edges: 0.1, 0.2, ..., 0.9
        # Interior edge equality to the right: exact edge e enters bin int(e*10),
        # nextafter(e, 0.0) enters bin int(e*10) - 1. Exact 1.0 enters bin 9.
        edge_origins = []
        edge_preds = []
        base_d = datetime.date(2024, 5, 10)
        row_idx = 0
        for edge_int in range(1, 10):
            e = edge_int / 10.0
            e_below = math.nextafter(e, 0.0)
            edge_origins.append(EvaluationOrigin(row_idx, base_d + datetime.timedelta(days=row_idx), OUTCOME_CLASS_BEAR))
            edge_preds.append(MockPrediction(row_idx, base_d + datetime.timedelta(days=row_idx), (e_below, (1.0 - e_below) / 2.0, (1.0 - e_below) / 2.0)))
            row_idx += 1
            edge_origins.append(EvaluationOrigin(row_idx, base_d + datetime.timedelta(days=row_idx), OUTCOME_CLASS_BEAR))
            edge_preds.append(MockPrediction(row_idx, base_d + datetime.timedelta(days=row_idx), (e, (1.0 - e) / 2.0, (1.0 - e) / 2.0)))
            row_idx += 1

        # Plus exact 1.0 -> bin 9
        edge_origins.append(EvaluationOrigin(row_idx, base_d + datetime.timedelta(days=row_idx), OUTCOME_CLASS_BEAR))
        edge_preds.append(MockPrediction(row_idx, base_d + datetime.timedelta(days=row_idx), (1.0, 0.0, 0.0)))

        edge_res = score_comparison(edge_origins, heuristic=edge_preds, frequency=edge_preds, logistic=edge_preds)
        edge_bear_bins = [b for b in edge_res.heuristic.reliability_bins if b.class_label == OUTCOME_CLASS_BEAR]

        self.assertEqual(edge_bear_bins[0].count, 1)
        for b_idx in range(1, 10):
            self.assertEqual(edge_bear_bins[b_idx].count, 2)

        # 3. Upper neighbor of every interior edge: nextafter(j/10, 1.0) lies inside [j/10, (j+1)/10)
        # and enters bin j. Each edge is scored as its own one-row cohort, so a misplaced count
        # cannot be offset by another row; expected indices come from the bin rule, not the scorer.
        expected_upper_bins = (
            (0.1, 1), (0.2, 2), (0.3, 3), (0.4, 4), (0.5, 5), (0.6, 6), (0.7, 7), (0.8, 8), (0.9, 9),
        )
        upper_d = datetime.date(2024, 5, 25)
        for edge, expected_bin in expected_upper_bins:
            e_above = math.nextafter(edge, 1.0)
            rest = (1.0 - e_above) / 2.0
            upper_origin = [EvaluationOrigin(0, upper_d, OUTCOME_CLASS_BEAR)]
            upper_pred = [MockPrediction(0, upper_d, (e_above, rest, rest))]
            upper_res = score_comparison(upper_origin, heuristic=upper_pred, frequency=upper_pred, logistic=upper_pred)
            for model in (upper_res.heuristic, upper_res.frequency, upper_res.logistic):
                with self.subTest(edge=edge):
                    occupied_bear = [
                        (b.class_label, b.bin_index, b.count)
                        for b in model.reliability_bins
                        if b.class_label == OUTCOME_CLASS_BEAR and b.count > 0
                    ]
                    self.assertEqual(occupied_bear, [(OUTCOME_CLASS_BEAR, expected_bin, 1)])

    def test_twenty_one_row_sequence_and_key_preservation(self) -> None:
        """
        Validates 21-row cohort: 20 perfect rows + 1 wrong one-hot -> mean Brier = 2/21.
        Exhaustively checks every exact (index, date) key across all three methods.
        Also validates near-ties vs exact ties.
        """
        base_date = datetime.date(2024, 6, 1)
        origins = []
        h_preds = []
        f_preds = []
        l_preds = []
        for i in range(21):
            d = base_date + datetime.timedelta(days=i)
            # First 20 actual BEAR; last actual BULL
            actual = OUTCOME_CLASS_BEAR if i < 20 else OUTCOME_CLASS_BULL
            origins.append(EvaluationOrigin(i * 2, d, actual))
            # Heuristic: all predict BEAR with 1.0 -> first 20 are perfect (loss 0), 21st is wrong one-hot (loss 2)
            h_preds.append(MockPrediction(i * 2, d, (1.0, 0.0, 0.0)))
            # Frequency: near-tie on row 0, exact tie on row 1, perfect elsewhere
            if i == 0:
                # Near-tie: 0.4000000000000001 vs 0.4 -> distinct floats, NO tie
                f_preds.append(MockPrediction(i * 2, d, (0.4000000000000001, 0.1999999999999999, 0.4)))
            elif i == 1:
                # Exact tie: 0.4 vs 0.4 -> tie_count increment
                f_preds.append(MockPrediction(i * 2, d, (0.4, 0.2, 0.4)))
            else:
                f_preds.append(MockPrediction(i * 2, d, (1.0, 0.0, 0.0)))
            # Logistic: uniform 1/3
            u = 1.0 / 3.0
            l_preds.append(MockPrediction(i * 2, d, (u, u, u)))

        res = score_comparison(origins, heuristic=h_preds, frequency=f_preds, logistic=l_preds)

        self.assertEqual(res.sample_count, 21)
        # Expected mean Brier for heuristic = (20 * 0 + 1 * 2) / 21 = 2/21
        expected_brier = 2.0 / 21.0
        self.assertAlmostEqual(res.heuristic.mean_brier, expected_brier, places=12)

        # Assert every exact (index, date) key in all THREE methods without dropping or shifting
        for model in (res.heuristic, res.frequency, res.logistic):
            self.assertEqual(len(model.row_scores), 21)
            for i in range(21):
                score_row = model.row_scores[i]
                expected_orig = origins[i]
                self.assertEqual(score_row.origin.origin_index, expected_orig.origin_index)
                self.assertEqual(score_row.origin.origin_date, expected_orig.origin_date)
                self.assertEqual(score_row.origin.actual_class, expected_orig.actual_class)

        # Check heuristic row briers
        for i in range(21):
            if i < 20:
                self.assertAlmostEqual(res.heuristic.row_scores[i].brier, 0.0, places=12)
            else:
                self.assertAlmostEqual(res.heuristic.row_scores[i].brier, 2.0, places=12)

        # Frequency: row 0 (near-tie) selects BEAR without tie increment; row 1 (exact tie) increments tie
        self.assertEqual(res.frequency.row_scores[0].predicted_class, OUTCOME_CLASS_BEAR)
        self.assertEqual(res.frequency.row_scores[1].predicted_class, OUTCOME_CLASS_BEAR)
        self.assertEqual(res.frequency.tie_count, 1)

        # Logistic: all 21 rows are 3-way ties
        self.assertEqual(res.logistic.tie_count, 21)

    def test_empty_cohort_policy(self) -> None:
        """Validates exact empty result contract when N=0."""
        res = score_comparison([], heuristic=[], frequency=[], logistic=[])

        self.assertEqual(res.protocol_id, PROTOCOL_ID)
        self.assertEqual(res.status, STATUS_EMPTY)
        self.assertEqual(res.sample_count, 0)
        self.assertEqual(res.class_support, (0, 0, 0))
        self.assertEqual(res.origins, ())

        for model in (res.heuristic, res.frequency, res.logistic):
            self.assertEqual(model.row_scores, ())
            self.assertIsNone(model.mean_brier)
            self.assertIsNone(model.mean_log_loss)
            self.assertEqual(model.log_loss_state, LOG_LOSS_STATE_EMPTY)
            self.assertEqual(model.zero_actual_probability_count, 0)
            self.assertEqual(model.tie_count, 0)
            self.assertIsNone(model.accuracy)
            self.assertEqual(model.confusion, ((0, 0, 0), (0, 0, 0), (0, 0, 0)))
            self.assertEqual(model.class_recall, (None, None, None))
            self.assertEqual(len(model.reliability_bins), 30)
            for b in model.reliability_bins:
                self.assertEqual(b.count, 0)
                self.assertIsNone(b.mean_probability)
                self.assertIsNone(b.observed_frequency)

    def test_result_classes_bin_edges_and_bin_sequence(self) -> None:
        """
        Validates the fixed class order, fixed bin edges and the complete class-major
        (class_label, bin_index) sequence for all three models in scored and empty results,
        whose reliability bins are built by separate code paths.
        """
        # Expected values are written out from the specification, not taken from the scorer
        expected_classes = ("BEAR", "NEUTRAL", "BULL")
        expected_edges = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
        expected_bin_keys = [(cls, b) for cls in expected_classes for b in range(10)]

        d = datetime.date(2024, 11, 1)
        origins = [EvaluationOrigin(0, d, OUTCOME_CLASS_NEUTRAL)]
        preds = [MockPrediction(0, d, (0.2, 0.5, 0.3))]
        scored = score_comparison(origins, heuristic=preds, frequency=preds, logistic=preds)
        empty = score_comparison([], heuristic=[], frequency=[], logistic=[])

        # Exact edges enter the right-hand bin: 0.2 -> BEAR bin 2, 0.5 -> NEUTRAL bin 5, 0.3 -> BULL bin 3
        cases = (
            (scored, STATUS_SCORED, [("BEAR", 2), ("NEUTRAL", 5), ("BULL", 3)]),
            (empty, STATUS_EMPTY, []),
        )
        for res, status, expected_occupied in cases:
            self.assertEqual(res.status, status)
            self.assertEqual(res.classes, expected_classes)
            self.assertEqual(res.bin_edges, expected_edges)
            for model in (res.heuristic, res.frequency, res.logistic):
                self.assertEqual(
                    [(b.class_label, b.bin_index) for b in model.reliability_bins],
                    expected_bin_keys,
                )
                self.assertEqual(
                    [(b.class_label, b.bin_index) for b in model.reliability_bins if b.count > 0],
                    expected_occupied,
                )

    def test_cohort_misalignment_rejection(self) -> None:
        """Validates rejection of mismatched, missing, extra, and misaligned prediction rows."""
        d1 = datetime.date(2024, 7, 1)
        d2 = datetime.date(2024, 7, 2)
        origins = [
            EvaluationOrigin(0, d1, OUTCOME_CLASS_BEAR),
            EvaluationOrigin(1, d2, OUTCOME_CLASS_BULL),
        ]
        valid_preds = [
            MockPrediction(0, d1, (1.0, 0.0, 0.0)),
            MockPrediction(1, d2, (0.0, 0.0, 1.0)),
        ]

        # Missing row in heuristic (1 row vs 2 origins)
        with self.assertRaises(InputValidationError) as ctx:
            score_comparison(origins, heuristic=valid_preds[:1], frequency=valid_preds, logistic=valid_preds)
        self.assertEqual(ctx.exception.field, "heuristic")
        # A length error names the method and both counts; it has no row position to report
        self.assertIn("heuristic", str(ctx.exception))
        self.assertNotIn("position", str(ctx.exception))
        self.assertIn("expected 2", ctx.exception.reason)
        self.assertIn("got 1", ctx.exception.reason)

        # Same missing row in all three methods vs 2-origin cohort
        with self.assertRaises(InputValidationError) as ctx:
            score_comparison(origins, heuristic=valid_preds[:1], frequency=valid_preds[:1], logistic=valid_preds[:1])
        self.assertIn(ctx.exception.field, ("heuristic", "frequency", "logistic"))

        # Extra row in logistic
        extra_preds = valid_preds + [MockPrediction(2, datetime.date(2024, 7, 3), (0.0, 1.0, 0.0))]
        with self.assertRaises(InputValidationError) as ctx:
            score_comparison(origins, heuristic=valid_preds, frequency=valid_preds, logistic=extra_preds)
        self.assertEqual(ctx.exception.field, "logistic")

        # Mismatched origin_index
        bad_idx_preds = [
            MockPrediction(999, d1, (1.0, 0.0, 0.0)),
            MockPrediction(1, d2, (0.0, 0.0, 1.0)),
        ]
        with self.assertRaises(InputValidationError) as ctx:
            score_comparison(origins, heuristic=bad_idx_preds, frequency=valid_preds, logistic=valid_preds)
        self.assertEqual(ctx.exception.field, "origin_index")
        self.assertIn("heuristic", str(ctx.exception))
        self.assertIn("position 0", str(ctx.exception))

        # Mismatched origin_date
        bad_date_preds = [
            MockPrediction(0, datetime.date(2099, 1, 1), (1.0, 0.0, 0.0)),
            MockPrediction(1, d2, (0.0, 0.0, 1.0)),
        ]
        with self.assertRaises(InputValidationError) as ctx:
            score_comparison(origins, heuristic=bad_date_preds, frequency=valid_preds, logistic=valid_preds)
        self.assertEqual(ctx.exception.field, "origin_date")

    def test_negative_schema_and_probability_validation(self) -> None:
        """Validates rejection of schema violations, non-strictly increasing dates, and bad probabilities."""
        d = datetime.date(2024, 8, 1)

        # Non-list/tuple container
        with self.assertRaises(InputValidationError) as ctx:
            score_comparison("not_a_list", heuristic=[], frequency=[], logistic=[])
        self.assertEqual(ctx.exception.field, "origins")

        # Non-integer origin_index
        bad_origins = [EvaluationOrigin("zero", d, OUTCOME_CLASS_BEAR)]  # type: ignore[arg-type]
        with self.assertRaises(InputValidationError) as ctx:
            score_comparison(bad_origins, heuristic=[], frequency=[], logistic=[])
        self.assertEqual(ctx.exception.field, "origin_index")

        # Bool origin_index
        bad_origins_bool = [EvaluationOrigin(True, d, OUTCOME_CLASS_BEAR)]  # type: ignore[arg-type]
        with self.assertRaises(InputValidationError) as ctx:
            score_comparison(bad_origins_bool, heuristic=[], frequency=[], logistic=[])
        self.assertEqual(ctx.exception.field, "origin_index")

        # Non-strictly increasing origin_date (equal dates)
        equal_dates = [
            EvaluationOrigin(0, d, OUTCOME_CLASS_BEAR),
            EvaluationOrigin(1, d, OUTCOME_CLASS_BULL),
        ]
        p_dummy = [MockPrediction(0, d, (1.0, 0.0, 0.0)), MockPrediction(1, d, (0.0, 0.0, 1.0))]
        with self.assertRaises(InputValidationError) as ctx:
            score_comparison(equal_dates, heuristic=p_dummy, frequency=p_dummy, logistic=p_dummy)
        self.assertEqual(ctx.exception.field, "origin_date")
        self.assertIn("position 1", str(ctx.exception))

        # Non-strictly increasing origin_index (descending)
        desc_indices = [
            EvaluationOrigin(5, d, OUTCOME_CLASS_BEAR),
            EvaluationOrigin(3, d + datetime.timedelta(days=1), OUTCOME_CLASS_BULL),
        ]
        p_desc = [
            MockPrediction(5, d, (1.0, 0.0, 0.0)),
            MockPrediction(3, d + datetime.timedelta(days=1), (0.0, 0.0, 1.0)),
        ]
        with self.assertRaises(InputValidationError) as ctx:
            score_comparison(desc_indices, heuristic=p_desc, frequency=p_desc, logistic=p_desc)
        self.assertEqual(ctx.exception.field, "origin_index")

        # Huge int probability component (must reject safely without overflow)
        valid_origin = [EvaluationOrigin(0, d, OUTCOME_CLASS_BEAR)]
        huge_int_prob = [MockPrediction(0, d, (10**50, 0, 0))]  # type: ignore[arg-type]
        with self.assertRaises(InputValidationError) as ctx:
            score_comparison(valid_origin, heuristic=huge_int_prob, frequency=huge_int_prob, logistic=huge_int_prob)
        self.assertEqual(ctx.exception.field, "probabilities")

        # Negative probability float
        neg_prob = [MockPrediction(0, d, (-0.1, 0.6, 0.5))]
        with self.assertRaises(InputValidationError) as ctx:
            score_comparison(valid_origin, heuristic=neg_prob, frequency=neg_prob, logistic=neg_prob)
        self.assertEqual(ctx.exception.field, "probabilities")

        # Non-finite probability float (NaN)
        nan_prob = [MockPrediction(0, d, (float("nan"), 0.5, 0.5))]
        with self.assertRaises(InputValidationError) as ctx:
            score_comparison(valid_origin, heuristic=nan_prob, frequency=nan_prob, logistic=nan_prob)
        self.assertEqual(ctx.exception.field, "probabilities")

        # Sum not equal to 1.0 (exceeds 1e-12)
        sum_prob = [MockPrediction(0, d, (0.33, 0.33, 0.33))]  # sum = 0.99
        with self.assertRaises(InputValidationError) as ctx:
            score_comparison(valid_origin, heuristic=sum_prob, frequency=sum_prob, logistic=sum_prob)
        self.assertEqual(ctx.exception.field, "probabilities")

        # datetime.datetime rejected as origin_date on EvaluationOrigin
        dt_origin = [EvaluationOrigin(0, datetime.datetime(2024, 8, 1, 10, 0), OUTCOME_CLASS_BEAR)]  # type: ignore[arg-type]
        with self.assertRaises(InputValidationError) as ctx:
            score_comparison(dt_origin, heuristic=p_dummy, frequency=p_dummy, logistic=p_dummy)
        self.assertEqual(ctx.exception.field, "origin_date")

        # datetime.datetime rejected as origin_date on Prediction
        dt_pred = [MockPrediction(0, datetime.datetime(2024, 8, 1, 10, 0), (1.0, 0.0, 0.0))]  # type: ignore[arg-type]
        with self.assertRaises(InputValidationError) as ctx:
            score_comparison(valid_origin, heuristic=dt_pred, frequency=dt_pred, logistic=dt_pred)
        self.assertEqual(ctx.exception.field, "origin_date")

        # Non-tuple probabilities container (list rejected)
        list_prob = [MockPrediction(0, d, [0.4, 0.3, 0.3])]  # type: ignore[arg-type]
        with self.assertRaises(InputValidationError) as ctx:
            score_comparison(valid_origin, heuristic=list_prob, frequency=list_prob, logistic=list_prob)
        self.assertEqual(ctx.exception.field, "probabilities")

        # Decimal probability component rejected
        dec_prob = [MockPrediction(0, d, (Decimal("0.4"), 0.3, 0.3))]  # type: ignore[arg-type]
        with self.assertRaises(InputValidationError) as ctx:
            score_comparison(valid_origin, heuristic=dec_prob, frequency=dec_prob, logistic=dec_prob)
        self.assertEqual(ctx.exception.field, "probabilities")

        # Infinite probability float (+inf)
        inf_prob = [MockPrediction(0, d, (float("inf"), 0.0, 0.0))]
        with self.assertRaises(InputValidationError) as ctx:
            score_comparison(valid_origin, heuristic=inf_prob, frequency=inf_prob, logistic=inf_prob)
        self.assertEqual(ctx.exception.field, "probabilities")

        # Missing attribute on prediction
        class MissingAttrPred:
            origin_index = 0
            origin_date = d

        with self.assertRaises(InputValidationError) as ctx:
            score_comparison(valid_origin, heuristic=[MissingAttrPred()], frequency=p_dummy, logistic=p_dummy)
        self.assertEqual(ctx.exception.field, "heuristic")

        # Reordered rows in predictions vs cohort
        d_b = datetime.date(2024, 8, 2)
        origs_order = [EvaluationOrigin(0, d, OUTCOME_CLASS_BEAR), EvaluationOrigin(1, d_b, OUTCOME_CLASS_BULL)]
        reordered_preds = [MockPrediction(1, d_b, (0.0, 0.0, 1.0)), MockPrediction(0, d, (1.0, 0.0, 0.0))]
        with self.assertRaises(InputValidationError) as ctx:
            score_comparison(origs_order, heuristic=reordered_preds, frequency=reordered_preds, logistic=reordered_preds)
        self.assertEqual(ctx.exception.field, "origin_index")

        # Late-invalid method validation (heuristic has infinite loss, but logistic has malformed probabilities)
        p_valid_one = [MockPrediction(0, d, (1.0, 0.0, 0.0))]
        inf_preds = [MockPrediction(0, d, (0.0, 0.5, 0.5))]
        bad_l_preds = [MockPrediction(0, d, (-0.1, 0.6, 0.5))]
        with self.assertRaises(InputValidationError) as ctx:
            score_comparison(valid_origin, heuristic=inf_preds, frequency=p_valid_one, logistic=bad_l_preds)
        self.assertEqual(ctx.exception.field, "probabilities")
        # The row diagnostic must name the failing method and row, not only the field
        self.assertIn("logistic", str(ctx.exception))
        self.assertIn("position 0", str(ctx.exception))

    def test_mixed_log_loss_propagation_and_zero_support_recall(self) -> None:
        """
        Validates that infinite log loss on a single row propagates to mean_log_loss=None
        without dropping infinite rows or preventing Brier/accuracy/bins computation,
        and verifies that zero class support produces class_recall=None for that class.
        """
        d1 = datetime.date(2024, 7, 10)
        d2 = datetime.date(2024, 7, 11)
        d3 = datetime.date(2024, 7, 12)

        # Cohort has 2 BEAR and 1 BULL; ZERO NEUTRAL!
        origins = [
            EvaluationOrigin(0, d1, OUTCOME_CLASS_BEAR),
            EvaluationOrigin(1, d2, OUTCOME_CLASS_BEAR),
            EvaluationOrigin(2, d3, OUTCOME_CLASS_BULL),
        ]

        # Model 1 (heuristic): row 0 has actual prob 0.0 -> infinite log loss
        # row 1 has actual prob 0.8 -> finite
        # row 2 has actual prob 0.7 -> finite
        h_preds = [
            MockPrediction(0, d1, (0.0, 0.5, 0.5)),
            MockPrediction(1, d2, (0.8, 0.1, 0.1)),
            MockPrediction(2, d3, (0.2, 0.1, 0.7)),
        ]

        # Model 2 (frequency): all positive probabilities -> finite log loss
        f_preds = [
            MockPrediction(0, d1, (0.7, 0.2, 0.1)),
            MockPrediction(1, d2, (0.6, 0.2, 0.2)),
            MockPrediction(2, d3, (0.1, 0.1, 0.8)),
        ]

        res = score_comparison(origins, heuristic=h_preds, frequency=f_preds, logistic=f_preds)

        self.assertEqual(res.class_support, (2, 0, 1))

        # Heuristic: infinite log loss on row 0 propagates to model
        self.assertIsNone(res.heuristic.mean_log_loss)
        self.assertEqual(res.heuristic.log_loss_state, LOG_LOSS_STATE_INFINITE)
        self.assertEqual(res.heuristic.zero_actual_probability_count, 1)

        # Row-level log states
        self.assertEqual(res.heuristic.row_scores[0].log_loss_state, LOG_LOSS_STATE_INFINITE)
        self.assertIsNone(res.heuristic.row_scores[0].log_loss)
        self.assertEqual(res.heuristic.row_scores[1].log_loss_state, LOG_LOSS_STATE_FINITE)
        self.assertIsNotNone(res.heuristic.row_scores[1].log_loss)
        self.assertEqual(res.heuristic.row_scores[2].log_loss_state, LOG_LOSS_STATE_FINITE)
        self.assertIsNotNone(res.heuristic.row_scores[2].log_loss)

        # Brier, accuracy, confusion, reliability bins remain fully available
        self.assertIsNotNone(res.heuristic.mean_brier)
        self.assertIsNotNone(res.heuristic.accuracy)
        self.assertEqual(len(res.heuristic.reliability_bins), 30)

        # Class recall: support is (2, 0, 1), so class_recall[1] (NEUTRAL) must be None!
        self.assertEqual(res.heuristic.class_recall[1], None)
        self.assertIsNotNone(res.heuristic.class_recall[0])
        self.assertIsNotNone(res.heuristic.class_recall[2])

        # Frequency: all finite in the same cohort
        self.assertIsNotNone(res.frequency.mean_log_loss)
        self.assertEqual(res.frequency.log_loss_state, LOG_LOSS_STATE_FINITE)
        self.assertEqual(res.frequency.zero_actual_probability_count, 0)
        self.assertEqual(res.frequency.class_recall[1], None)

    def test_bounded_diagnostics_and_subclass_rejection(self) -> None:
        """
        Validates safe bounded error diagnostics under huge integers/strings,
        rejection of non-native numeric subclasses, and detachment of mutable EvaluationOrigin subclasses.
        """
        d = datetime.date(2024, 8, 15)

        # 1. Negative huge index (-(10**5000)) rejects safely without ValueError (A1)
        huge_neg_idx = -(10**5000)
        bad_orig_huge = [EvaluationOrigin(huge_neg_idx, d, OUTCOME_CLASS_BEAR)]
        p_dummy = [MockPrediction(0, d, (1.0, 0.0, 0.0))]
        with self.assertRaises(InputValidationError) as ctx:
            score_comparison(bad_orig_huge, heuristic=p_dummy, frequency=p_dummy, logistic=p_dummy)
        self.assertEqual(ctx.exception.field, "origin_index")

        # 2. Positive huge index mismatch rejects without ValueError (A1)
        huge_pos_idx = 10**5000
        orig_huge_pos = [EvaluationOrigin(huge_pos_idx, d, OUTCOME_CLASS_BEAR)]
        p_huge_mismatch = [MockPrediction(huge_pos_idx + 1, d, (1.0, 0.0, 0.0))]
        with self.assertRaises(InputValidationError) as ctx:
            score_comparison(orig_huge_pos, heuristic=p_huge_mismatch, frequency=p_huge_mismatch, logistic=p_huge_mismatch)
        self.assertEqual(ctx.exception.field, "origin_index")

        # 3. Non-strictly increasing huge indices reject without ValueError (A1)
        origs_huge_equal = [
            EvaluationOrigin(huge_pos_idx, d, OUTCOME_CLASS_BEAR),
            EvaluationOrigin(huge_pos_idx, d + datetime.timedelta(days=1), OUTCOME_CLASS_BULL),
        ]
        p_two = [MockPrediction(huge_pos_idx, d, (1.0, 0.0, 0.0)), MockPrediction(huge_pos_idx, d + datetime.timedelta(days=1), (0.0, 0.0, 1.0))]
        with self.assertRaises(InputValidationError) as ctx:
            score_comparison(origs_huge_equal, heuristic=p_two, frequency=p_two, logistic=p_two)
        self.assertEqual(ctx.exception.field, "origin_index")

        # 4. Malformed actual_class with failing __repr__ rejects with InputValidationError (A1)
        class BrokenRepr:
            def __repr__(self) -> str:
                raise RuntimeError("failing repr")

        bad_orig_repr = [EvaluationOrigin(0, d, BrokenRepr())]  # type: ignore[arg-type]
        with self.assertRaises(InputValidationError) as ctx:
            score_comparison(bad_orig_repr, heuristic=p_dummy, frequency=p_dummy, logistic=p_dummy)
        self.assertEqual(ctx.exception.field, "actual_class")

        # 5. Malformed huge string actual_class rejects with bounded message (A1)
        huge_str_cls = "A" * 100000
        bad_orig_huge_str = [EvaluationOrigin(0, d, huge_str_cls)]
        with self.assertRaises(InputValidationError) as ctx:
            score_comparison(bad_orig_huge_str, heuristic=p_dummy, frequency=p_dummy, logistic=p_dummy)
        self.assertEqual(ctx.exception.field, "actual_class")
        self.assertLess(len(str(ctx.exception)), 500)

        # 6. Int subclass in probability components is rejected (A2)
        class IntSubclass(int):
            pass

        valid_orig = [EvaluationOrigin(0, d, OUTCOME_CLASS_BEAR)]
        subclass_int_prob = [MockPrediction(0, d, (IntSubclass(1), 0, 0))]  # type: ignore[arg-type]
        with self.assertRaises(InputValidationError) as ctx:
            score_comparison(valid_orig, heuristic=subclass_int_prob, frequency=subclass_int_prob, logistic=subclass_int_prob)
        self.assertEqual(ctx.exception.field, "probabilities")

        # 7. Float subclass in probability components is rejected (A2)
        class FloatSubclass(float):
            def __sub__(self, other: Any) -> float:
                return 0.0

        subclass_float_prob = [MockPrediction(0, d, (FloatSubclass(0.4), 0.2, 0.4))]  # type: ignore[arg-type]
        with self.assertRaises(InputValidationError) as ctx:
            score_comparison(valid_orig, heuristic=subclass_float_prob, frequency=subclass_float_prob, logistic=subclass_float_prob)
        self.assertEqual(ctx.exception.field, "probabilities")

        # 8. Mutable subclass of EvaluationOrigin does not alter scored result (A2)
        class MutableEvaluationOrigin(EvaluationOrigin):
            def __init__(self, idx: int, dt: datetime.date, cls: str) -> None:
                super().__init__(idx, dt, cls)
                self.auxiliary_label = cls

            def __getattribute__(self, name: str) -> Any:
                if name == "actual_class":
                    return object.__getattribute__(self, "auxiliary_label")
                return super().__getattribute__(name)

        mut_orig = MutableEvaluationOrigin(0, d, OUTCOME_CLASS_BEAR)
        p_mut = [MockPrediction(0, d, (1.0, 0.0, 0.0))]
        res_mut = score_comparison([mut_orig], heuristic=p_mut, frequency=p_mut, logistic=p_mut)

        # Result origin must be an exact owned plain EvaluationOrigin
        self.assertIs(type(res_mut.origins[0]), EvaluationOrigin)
        self.assertIs(type(res_mut.heuristic.row_scores[0].origin), EvaluationOrigin)
        self.assertEqual(res_mut.origins[0].actual_class, OUTCOME_CLASS_BEAR)

        # Mutating the caller's subclass instance does NOT alter the scored result
        mut_orig.auxiliary_label = OUTCOME_CLASS_BULL
        self.assertEqual(res_mut.origins[0].actual_class, OUTCOME_CLASS_BEAR)
        self.assertEqual(res_mut.heuristic.row_scores[0].origin.actual_class, OUTCOME_CLASS_BEAR)

    def test_frequency_prediction_structural_compatibility_and_clean_import(self) -> None:
        """
        Validates genuine FrequencyPrediction structural compatibility without model fitting,
        and verifies that logistic and sklearn modules are NOT imported into the test process.
        """
        d = datetime.date(2024, 9, 1)
        origin = [EvaluationOrigin(0, d, OUTCOME_CLASS_BEAR)]

        # Construct genuine FrequencyPrediction from frequency.py
        freq_pred = FrequencyPrediction(origin_index=0, origin_date=d, probabilities=(1.0, 0.0, 0.0))
        self.assertIsInstance(freq_pred, PredictionLike)

        res = score_comparison(origin, heuristic=[freq_pred], frequency=[freq_pred], logistic=[freq_pred])
        self.assertEqual(res.sample_count, 1)
        self.assertAlmostEqual(res.frequency.mean_brier, 0.0, places=12)

        # Pure-suite import isolation audit: logistic and sklearn must NOT be imported
        self.assertNotIn("research.prediction_eval.logistic", sys.modules)
        self.assertNotIn("sklearn", sys.modules)

    def test_immutability_and_caller_container_preservation(self) -> None:
        """Validates frozen dataclass mutation rejection and caller container isolation."""
        d = datetime.date(2024, 10, 1)
        origins = [EvaluationOrigin(0, d, OUTCOME_CLASS_BEAR)]
        preds = [MockPrediction(0, d, (1.0, 0.0, 0.0))]

        res = score_comparison(origins, heuristic=preds, frequency=preds, logistic=preds)

        # Frozen dataclass mutation rejection
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            res.sample_count = 999  # type: ignore[misc]

        with self.assertRaises((FrozenInstanceError, AttributeError)):
            res.heuristic.tie_count = 999  # type: ignore[misc]

        with self.assertRaises((FrozenInstanceError, AttributeError)):
            res.origins[0].actual_class = OUTCOME_CLASS_BULL  # type: ignore[misc]

        # Mutating caller's mutable list afterwards does not alter the scored result
        origins.append(EvaluationOrigin(1, datetime.date(2024, 10, 2), OUTCOME_CLASS_BULL))
        self.assertEqual(len(res.origins), 1)
        self.assertEqual(res.sample_count, 1)


if __name__ == "__main__":
    unittest.main()
