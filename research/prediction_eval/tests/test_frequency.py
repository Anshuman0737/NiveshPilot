"""
Unit tests for Prediction Evaluation Fixed-Frequency Baseline Comparator.

Validates:
1. Compact asymmetric oracle (N=300, D=226, T=260):
   - Train fit (origins 200..205): exact integer counts (3, 2, 1), probabilities (4/9, 3/9, 2/9).
   - Development targets 226..239: exact coverage, constant within-block probabilities.
   - Refit (origins 200..239): exact integer counts (4, 32, 4), probabilities (5/43, 33/43, 5/43).
     Explains all eight nonneutral origins independently.
   - Test targets 260..279: exact coverage, constant within-block probabilities.
   - Discriminating rejection of rounded-to-two-decimal probabilities against the oracle.
2. Independent label counterfactuals:
   - Origin 205 label perturbation affects both train fit and refit.
   - Origin 206 label perturbation affects only refit (purged at development boundary).
   - Origin 239 label perturbation affects only refit.
   - Origin 240 label perturbation affects neither fit (crosses test boundary).
   - Excluded missing-VIX row label perturbation affects neither fit.
3. Temporal safety under future perturbation:
   - Price and VIX changes strictly at or after test_start (T) leave pre-test fits and
     predictions bit-for-bit identical.
   - Development outcomes legitimately influence refit while never changing the frozen
     development distribution.
4. Asymmetric mixed classes, missing class, and one-class fits:
   - Fit with missing class (0 observed in one category) retains valid Laplace probability.
   - One-class fit retains valid Laplace probabilities summing to 1 within 1e-12.
5. Empty train with nonempty refit (N=300, D=210, T=260):
   - Development block has fit=None, unavailable_reason='no_fit_rows', predictions=().
   - Refit has 40 rows, valid fit and test predictions.
6. Honest unavailable state on all-unready short series (N=25):
   - Both blocks have fit=None, unavailable_reason='no_fit_rows', predictions=().
   - Method identity, alpha, classes, series_id, horizon, protocol, and outcome definition
     remain accessible on result.
7. Empty target pool with nonempty fit:
   - Removing VIX only across the development target block (226..239) preserves train fit,
     gives predictions=() and unavailable_reason=None.
   - Independent recalculation of affected refit oracle (26 rows, counts (4, 18, 4),
     probabilities (5/29, 19/29, 5/29)).
8. Planner boundary propagation:
   - Invalid dates, ordering, and series roles fail with responsible field from build_split_plan.
9. Immutability, repeated-call equality, and input preservation:
   - All returned dataclasses reject attribute mutation.
   - Input FeatureSeries and OutcomeSeries are verified untouched via deep snapshots.
   - Repeated calls produce equal results.
10. Clean import boundary:
    - Pure standard library: zero model, metric, network, random, or external dependencies.
"""

from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError, replace
import datetime
from decimal import Decimal
import math
from pathlib import Path
import tempfile
import unittest
from typing import List, Sequence, Tuple, Union

from research.prediction_eval.inputs import (
    InputValidationError,
    align_pair,
    load_series,
)
from research.prediction_eval.features import (
    FeatureSeries,
    PROTOCOL_ID,
    compute_nifty_features,
)
from research.prediction_eval.outcomes import (
    HORIZON_SESSIONS,
    OutcomeSeries,
    OUTCOME_CLASS_BEAR,
    OUTCOME_CLASS_BULL,
    OUTCOME_CLASS_NEUTRAL,
    STATUS_MATURE,
    STATUS_UNKNOWN,
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
from research.prediction_eval.frequency import (
    ALPHA,
    FrequencyBlock,
    FrequencyFit,
    FrequencyPrediction,
    FrequencyResult,
    METHOD_ID,
    ORDERED_CLASSES,
    OUTCOME_DEFINITION,
    SERIES_ID,
    UNAVAILABLE_REASON_NO_FIT_ROWS,
    build_frequency_predictions,
)


class TestPredictionEvalFrequency(unittest.TestCase):
    """Test suite for research/prediction_eval/frequency.py."""

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
        start_date: datetime.date = datetime.date(2021, 1, 4),
    ) -> List[datetime.date]:
        """Generates strictly increasing dates with nonuniform calendar spacing."""
        dates: List[datetime.date] = []
        curr = start_date
        while len(dates) < count:
            weekday = curr.weekday()
            # Synthetic Saturday session at index 50
            if len(dates) == 50 and weekday == 5:
                dates.append(curr)
            # 4-day leap at index 150
            elif len(dates) == 150:
                curr += datetime.timedelta(days=4)
                if curr.weekday() < 5:
                    dates.append(curr)
            elif weekday < 5:  # Monday to Friday
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
        Default prices: 100.00, default VIX: 20.00.
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

    def test_01_compact_asymmetric_oracle(self) -> None:
        """
        Validates the compact asymmetric oracle specified in requirements.md:
        - N=300, D=226, T=260.
        - Closes: 100.00 except 220, 221, 222 = 99.00 and 225 = 101.00.
        - VIX: 20.00 (no missing VIX).
        - Development fit:
          * fitting origins 200..205 (6 rows)
          * class counts: (3, 2, 1) in order (BEAR, NEUTRAL, BULL)
          * smoothed probabilities: (4/9, 3/9, 2/9)
          * cutoff: index 226, date dates[226]
        - Development predictions:
          * targets 226..239 (14 rows)
          * all predictions carry exact probabilities (4/9, 3/9, 2/9)
        - Refit:
          * fitting origins 200..239 (40 rows)
          * class counts: (4, 32, 4) in order (BEAR, NEUTRAL, BULL)
          * smoothed probabilities: (5/43, 33/43, 5/43)
          * cutoff: index 260, date dates[260]
          * eight nonneutral origins explained independently:
            Origins 200, 201, 202 mature at 220, 221, 222 (99.00 / 100.00 - 1 = -1% -> BEAR).
            Origin 225 (101.00) matures at 245 (100.00 / 101.00 - 1 = -0.99% -> BEAR).
            Origin 205 (100.00) matures at 225 (101.00 / 100.00 - 1 = +1% -> BULL).
            Origins 220, 221, 222 (99.00) mature at 240, 241, 242 (100.00 / 99.00 - 1 = +1.01% -> BULL).
            Remaining 32 origins in 200..239 are 100.00 -> 100.00 (NEUTRAL).
        - Test predictions:
          * targets 260..279 (20 rows)
          * all predictions carry exact probabilities (5/43, 33/43, 5/43)
        - Tail 280..299 excluded (unknown outcome).
        - Reject rounded-to-two-decimal implementation with the oracle.
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
            prefix="asym_oracle",
        )

        d_date = dates[D]
        t_date = dates[T]

        result = build_frequency_predictions(
            features,
            outcomes,
            development_start=d_date,
            test_start=t_date,
        )

        # 1. Top-level metadata invariants
        self.assertEqual(result.method, METHOD_ID)
        self.assertEqual(result.version, METHOD_ID)
        self.assertEqual(result.method_id, METHOD_ID)
        self.assertEqual(result.alpha, 1.0)
        self.assertEqual(result.classes, (OUTCOME_CLASS_BEAR, OUTCOME_CLASS_NEUTRAL, OUTCOME_CLASS_BULL))
        self.assertEqual(result.series_id, "nifty50_price_index")
        self.assertEqual(result.horizon_sessions, 20)
        self.assertEqual(result.protocol_id, PROTOCOL_ID)
        self.assertEqual(result.outcome_definition, OUTCOME_DEFINITION)

        # 2. Development block validation
        dev_block = result.development_block
        self.assertIs(dev_block, result.development)
        self.assertEqual(dev_block.partition, PARTITION_DEVELOPMENT)
        self.assertIsNone(dev_block.unavailable_reason)

        expected_dev_targets = tuple(range(226, 240))
        self.assertEqual(len(expected_dev_targets), 14)
        self.assertEqual(dev_block.requested_indices, expected_dev_targets)

        dev_fit = dev_block.fit
        self.assertIsNotNone(dev_fit)
        expected_train_fitting = tuple(range(200, 206))
        self.assertEqual(dev_fit.fitting_indices, expected_train_fitting)
        self.assertEqual(dev_fit.cutoff_index, D)
        self.assertEqual(dev_fit.cutoff_date, d_date)
        self.assertEqual(dev_fit.class_counts, (3, 2, 1))

        # Expected dev probabilities: ((3+1)/9, (2+1)/9, (1+1)/9) = (4/9, 3/9, 2/9)
        expected_dev_probs = (4.0 / 9.0, 3.0 / 9.0, 2.0 / 9.0)
        self.assertEqual(dev_fit.probabilities, expected_dev_probs)
        self.assertTrue(math.isclose(sum(dev_fit.probabilities), 1.0, abs_tol=1e-12))

        # Discriminate rounded-to-two-decimals:
        # 4/9 ~ 0.4444... Rounded to 2 decimals is 0.44 != 4/9
        self.assertNotEqual(dev_fit.probabilities[0], 0.44)
        self.assertTrue(abs(dev_fit.probabilities[0] - 0.44) > 1e-4)

        # Development predictions
        self.assertEqual(len(dev_block.predictions), 14)
        for idx, pred in enumerate(dev_block.predictions):
            target_i = 226 + idx
            self.assertEqual(pred.origin_index, target_i)
            self.assertEqual(pred.origin_date, dates[target_i])
            self.assertEqual(pred.probabilities, expected_dev_probs)

        # 3. Test block validation
        test_block = result.test_block
        self.assertIs(test_block, result.test)
        self.assertEqual(test_block.partition, PARTITION_TEST)
        self.assertIsNone(test_block.unavailable_reason)

        expected_test_targets = tuple(range(260, 280))
        self.assertEqual(len(expected_test_targets), 20)
        self.assertEqual(test_block.requested_indices, expected_test_targets)

        test_fit = test_block.fit
        self.assertIsNotNone(test_fit)
        expected_refit_fitting = tuple(range(200, 240))
        self.assertEqual(len(expected_refit_fitting), 40)
        self.assertEqual(test_fit.fitting_indices, expected_refit_fitting)
        self.assertEqual(test_fit.cutoff_index, T)
        self.assertEqual(test_fit.cutoff_date, t_date)
        self.assertEqual(test_fit.class_counts, (4, 32, 4))

        # Expected test probabilities: ((4+1)/43, (32+1)/43, (4+1)/43) = (5/43, 33/43, 5/43)
        expected_test_probs = (5.0 / 43.0, 33.0 / 43.0, 5.0 / 43.0)
        self.assertEqual(test_fit.probabilities, expected_test_probs)
        self.assertTrue(math.isclose(sum(test_fit.probabilities), 1.0, abs_tol=1e-12))

        # Discriminate rounded-to-two-decimals:
        # 5/43 ~ 0.116279... Rounded to 2 decimals is 0.12 != 5/43
        self.assertNotEqual(test_fit.probabilities[0], 0.12)
        self.assertTrue(abs(test_fit.probabilities[0] - 0.12) > 1e-4)

        # Test predictions
        self.assertEqual(len(test_block.predictions), 20)
        for idx, pred in enumerate(test_block.predictions):
            target_i = 260 + idx
            self.assertEqual(pred.origin_index, target_i)
            self.assertEqual(pred.origin_date, dates[target_i])
            self.assertEqual(pred.probabilities, expected_test_probs)

        # Tail 280..299 must stay excluded from test targets
        all_pred_indices = {p.origin_index for p in test_block.predictions}
        for tail_i in range(280, 300):
            self.assertNotIn(tail_i, all_pred_indices)
            self.assertNotIn(tail_i, test_block.requested_indices)

    def test_02_independent_label_counterfactuals(self) -> None:
        """
        Validates independent label counterfactual perturbations:
        - Perturbing label at 205 affects BOTH train fit and refit.
        - Perturbing label at 206 affects ONLY refit, NOT train fit.
        - Perturbing label at 239 affects ONLY refit, NOT train fit.
        - Perturbing label at 240 affects NEITHER train fit nor refit.
        - Label at excluded missing-VIX row affects NEITHER fit.
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
        # Include a missing VIX at origin 215 to test excluded-row label perturbation
        features, outcomes, dates = self._build_oracle_fixture(
            n_origins=N,
            missing_vix_indices=(215,),
            close_overrides=close_overrides,
            prefix="counterfactual",
        )

        d_date = dates[D]
        t_date = dates[T]

        baseline = build_frequency_predictions(
            features, outcomes, development_start=d_date, test_start=t_date
        )

        # In baseline with missing VIX at 215:
        # Train fitting: 200..205 (6 rows, 215 is > 205 so unaffected) -> counts (3, 2, 1)
        # Refit fitting: 200..239 except 215 (39 rows) -> counts (4, 31, 4)
        base_train_counts = baseline.development_block.fit.class_counts
        base_refit_counts = baseline.test_block.fit.class_counts
        self.assertEqual(base_train_counts, (3, 2, 1))
        self.assertEqual(base_refit_counts, (4, 31, 4))

        def _with_tampered_label(target_origin: int, new_label: str) -> OutcomeSeries:
            outs = list(outcomes.outcomes)
            old_rec = outs[target_origin]
            outs[target_origin] = replace(old_rec, outcome_class=new_label)
            return OutcomeSeries(series_id=outcomes.series_id, outcomes=tuple(outs))

        # 1. Perturbation at 205: original is BULL. Change to BEAR.
        # Origin 205 is in train (200..205) and in refit (200..239).
        out_205 = _with_tampered_label(205, OUTCOME_CLASS_BEAR)
        res_205 = build_frequency_predictions(features, out_205, development_start=d_date, test_start=t_date)
        # Train counts: (3+1, 2, 1-1) = (4, 2, 0)
        self.assertEqual(res_205.development_block.fit.class_counts, (4, 2, 0))
        # Refit counts: (4+1, 31, 4-1) = (5, 31, 3)
        self.assertEqual(res_205.test_block.fit.class_counts, (5, 31, 3))

        # 2. Perturbation at 206: original is NEUTRAL. Change to BULL.
        # Origin 206 is purged from train (206+20 = 226 >= D=226), but in refit (206+20 < T=260).
        out_206 = _with_tampered_label(206, OUTCOME_CLASS_BULL)
        res_206 = build_frequency_predictions(features, out_206, development_start=d_date, test_start=t_date)
        # Train counts: UNCHANGED! (3, 2, 1)
        self.assertEqual(res_206.development_block.fit.class_counts, (3, 2, 1))
        self.assertEqual(res_206.development_block.fit.probabilities, baseline.development_block.fit.probabilities)
        # Refit counts: (4, 31-1, 4+1) = (4, 30, 5). Changed!
        self.assertEqual(res_206.test_block.fit.class_counts, (4, 30, 5))

        # 3. Perturbation at 239: original is NEUTRAL. Change to BEAR.
        # Origin 239 is in development partition, but in refit.
        out_239 = _with_tampered_label(239, OUTCOME_CLASS_BEAR)
        res_239 = build_frequency_predictions(features, out_239, development_start=d_date, test_start=t_date)
        # Train counts: UNCHANGED!
        self.assertEqual(res_239.development_block.fit.class_counts, (3, 2, 1))
        # Refit counts: (4+1, 31-1, 4) = (5, 30, 4). Changed!
        self.assertEqual(res_239.test_block.fit.class_counts, (5, 30, 4))

        # 4. Perturbation at 240: original is NEUTRAL. Change to BULL.
        # Origin 240 matures at 260 (== T=260, NOT < T). Purged from development and excluded from refit.
        out_240 = _with_tampered_label(240, OUTCOME_CLASS_BULL)
        res_240 = build_frequency_predictions(features, out_240, development_start=d_date, test_start=t_date)
        # Train counts: UNCHANGED!
        self.assertEqual(res_240.development_block.fit.class_counts, (3, 2, 1))
        # Refit counts: UNCHANGED!
        self.assertEqual(res_240.test_block.fit.class_counts, (4, 31, 4))

        # 5. Perturbation at 215 (missing VIX): original is NEUTRAL. Change to BULL.
        # Origin 215 is excluded from both train and refit due to missing VIX.
        out_215 = _with_tampered_label(215, OUTCOME_CLASS_BULL)
        res_215 = build_frequency_predictions(features, out_215, development_start=d_date, test_start=t_date)
        # Both fits must be UNCHANGED!
        self.assertEqual(res_215.development_block.fit.class_counts, (3, 2, 1))
        self.assertEqual(res_215.test_block.fit.class_counts, (4, 31, 4))

    def test_03_future_price_perturbation_at_or_after_t(self) -> None:
        """
        Validates temporal causal safety under future price perturbations:
        - Recomputed future price and VIX perturbations strictly at or after T=260 cannot change
          either fitting pool, class counts, or probabilities.
        - Development outcomes may legitimately influence final refit while never changing
          the frozen development distribution.
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
        # Baseline run
        feat_base, out_base, dates = self._build_oracle_fixture(
            n_origins=N,
            close_overrides=close_overrides,
            prefix="fut_base",
        )
        res_base = build_frequency_predictions(
            feat_base, out_base, development_start=dates[D], test_start=dates[T]
        )

        # Perturbed run: all prices at indices 260..299 slashed by 50%, VIX doubled
        close_overrides_pert = list(close_overrides) + [(i, "50.00") for i in range(260, 300)]
        vix_overrides_pert = [(i, "40.00") for i in range(260, 300)]
        feat_pert, out_pert, _ = self._build_oracle_fixture(
            n_origins=N,
            close_overrides=close_overrides_pert,
            vix_overrides=vix_overrides_pert,
            prefix="fut_pert",
        )
        res_pert = build_frequency_predictions(
            feat_pert, out_pert, development_start=dates[D], test_start=dates[T]
        )

        # Pre-test fits must be 100% bit-for-bit identical!
        self.assertEqual(
            res_base.development_block.fit.fitting_indices,
            res_pert.development_block.fit.fitting_indices,
        )
        self.assertEqual(
            res_base.development_block.fit.class_counts,
            res_pert.development_block.fit.class_counts,
        )
        self.assertEqual(
            res_base.development_block.fit.probabilities,
            res_pert.development_block.fit.probabilities,
        )
        self.assertEqual(
            res_base.test_block.fit.fitting_indices,
            res_pert.test_block.fit.fitting_indices,
        )
        self.assertEqual(
            res_base.test_block.fit.class_counts,
            res_pert.test_block.fit.class_counts,
        )
        self.assertEqual(
            res_base.test_block.fit.probabilities,
            res_pert.test_block.fit.probabilities,
        )

        # Development predictions are identical
        self.assertEqual(
            len(res_base.development_block.predictions),
            len(res_pert.development_block.predictions),
        )
        for p_base, p_pert in zip(
            res_base.development_block.predictions,
            res_pert.development_block.predictions,
        ):
            self.assertEqual(p_base.probabilities, p_pert.probabilities)

        # Development distribution is frozen: refit includes development outcomes (e.g. 226..239),
        # but development block predictions do NOT change after refit is constructed.
        self.assertEqual(
            res_base.development_block.predictions[0].probabilities,
            (4.0 / 9.0, 3.0 / 9.0, 2.0 / 9.0),
        )
        self.assertEqual(
            res_base.test_block.predictions[0].probabilities,
            (5.0 / 43.0, 33.0 / 43.0, 5.0 / 43.0),
        )

    def test_04_asymmetric_mixed_classes_missing_class_and_one_class_fits(self) -> None:
        """
        Validates:
        - Missing class: nonempty fit where 1 class has 0 observations (e.g. BEAR=0).
          Laplace smoothed probability is (0+1)/(N+3) > 0.
        - One-class fit: nonempty fit where only 1 class is observed (e.g. 10 NEUTRAL, 0 BEAR, 0 BULL).
          Laplace smoothed probabilities sum to 1 within 1e-12.
        - Exact class order (BEAR, NEUTRAL, BULL) and full binary64 precision.
        """
        N = 300
        D = 230
        T = 270
        dates = self._generate_nonuniform_dates(N)

        # 1. Missing class test:
        # All Closes 100 except Closes 220..224 = 101 (BULL moves from 200..204).
        # Closes 225..229 = 100 (NEUTRAL moves).
        # No BEAR moves! (BEAR count = 0).
        close_overrides = [(i, "101.00") for i in range(220, 225)]
        feat_miss, out_miss, _ = self._build_oracle_fixture(
            n_origins=N,
            close_overrides=close_overrides,
            prefix="missing_class",
        )
        res_miss = build_frequency_predictions(
            feat_miss, out_miss, development_start=dates[D], test_start=dates[T]
        )
        dev_fit = res_miss.development_block.fit
        self.assertIsNotNone(dev_fit)
        # Train fitting: 200..209 (10 rows).
        # Origins 200..204 mature at 220..224 (close 101 / 100 -> BULL) -> 5 BULL.
        # Origins 205..209 mature at 225..229 (close 100 / 100 -> NEUTRAL) -> 5 NEUTRAL.
        # BEAR: 0.
        # Counts: (0, 5, 5), total = 10.
        self.assertEqual(dev_fit.class_counts, (0, 5, 5))
        expected_probs = (1.0 / 13.0, 6.0 / 13.0, 6.0 / 13.0)
        self.assertEqual(dev_fit.probabilities, expected_probs)
        self.assertTrue(math.isclose(sum(dev_fit.probabilities), 1.0, abs_tol=1e-12))
        self.assertGreater(dev_fit.probabilities[0], 0.0)

        # 2. One-class fit test:
        # All Closes 100.00 everywhere -> 100% NEUTRAL moves!
        feat_one, out_one, _ = self._build_oracle_fixture(
            n_origins=N,
            close_overrides=(),
            prefix="one_class",
        )
        res_one = build_frequency_predictions(
            feat_one, out_one, development_start=dates[D], test_start=dates[T]
        )
        one_fit = res_one.development_block.fit
        self.assertIsNotNone(one_fit)
        # Train fitting: 200..209 (10 rows).
        # All 10 are NEUTRAL.
        # Counts: (0, 10, 0), total = 10.
        self.assertEqual(one_fit.class_counts, (0, 10, 0))
        expected_one_probs = (1.0 / 13.0, 11.0 / 13.0, 1.0 / 13.0)
        self.assertEqual(one_fit.probabilities, expected_one_probs)
        self.assertTrue(math.isclose(sum(one_fit.probabilities), 1.0, abs_tol=1e-12))

    def test_05_empty_train_with_nonempty_refit(self) -> None:
        """
        Validates empty train fitting with nonempty refit:
        - Synthetic N=300, D=210, T=260.
        - Origins i in train (i < 210): candidate rows 200..209 have maturity >= 220 >= D=210.
        - All rows 200..209 are purged from train (label_crosses_development_boundary).
        - Development fitting indices: empty ()!
        - Development block: fit=None, unavailable_reason='no_fit_rows', predictions=().
        - Requested indices for development: plan.development_indices (retained!).
        - Refit fitting indices: rows 200..239 (40 rows, maturity < 260) -> nonempty!
        - Test block: valid fit, predictions nonempty, unavailable_reason=None.
        """
        N = 300
        D = 210
        T = 260
        features, outcomes, dates = self._build_oracle_fixture(
            n_origins=N,
            prefix="empty_train",
        )

        result = build_frequency_predictions(
            features,
            outcomes,
            development_start=dates[D],
            test_start=dates[T],
        )

        # Development block is unavailable due to no_fit_rows
        dev_block = result.development_block
        self.assertIsNone(dev_block.fit)
        self.assertEqual(dev_block.unavailable_reason, UNAVAILABLE_REASON_NO_FIT_ROWS)
        self.assertEqual(dev_block.predictions, ())
        # Canonical target indices are retained!
        self.assertEqual(dev_block.requested_indices, result.plan.development_indices)
        self.assertGreater(len(dev_block.requested_indices), 0)

        # Test block has a valid fit and predictions
        test_block = result.test_block
        self.assertIsNotNone(test_block.fit)
        self.assertIsNone(test_block.unavailable_reason)
        self.assertEqual(len(test_block.fit.fitting_indices), 40)
        self.assertEqual(len(test_block.predictions), len(test_block.requested_indices))
        self.assertGreater(len(test_block.predictions), 0)

    def test_06_honest_unavailable_state_on_all_unready_short_series(self) -> None:
        """
        Validates honest unavailable states on an all-unready short series (N=25):
        - Both development and test fitting pools have 0 rows.
        - Development and test blocks: fit=None, unavailable_reason='no_fit_rows', predictions=().
        - Method identity, alpha, classes, series_id, horizon, protocol, and outcome definition
          remain available on result.
        """
        N = 25
        D = 5
        T = 15
        features, outcomes, dates = self._build_oracle_fixture(
            n_origins=N,
            prefix="all_unready",
        )

        result = build_frequency_predictions(
            features,
            outcomes,
            development_start=dates[D],
            test_start=dates[T],
        )

        self.assertEqual(result.method, METHOD_ID)
        self.assertEqual(result.alpha, 1.0)
        self.assertEqual(result.classes, ORDERED_CLASSES)
        self.assertEqual(result.series_id, "nifty50_price_index")
        self.assertEqual(result.horizon_sessions, 20)
        self.assertEqual(result.protocol_id, PROTOCOL_ID)
        self.assertEqual(result.outcome_definition, OUTCOME_DEFINITION)

        dev_b = result.development_block
        self.assertIsNone(dev_b.fit)
        self.assertEqual(dev_b.unavailable_reason, UNAVAILABLE_REASON_NO_FIT_ROWS)
        self.assertEqual(dev_b.predictions, ())

        test_b = result.test_block
        self.assertIsNone(test_b.fit)
        self.assertEqual(test_b.unavailable_reason, UNAVAILABLE_REASON_NO_FIT_ROWS)
        self.assertEqual(test_b.predictions, ())

    def test_07_empty_target_pool_with_nonempty_fit_and_recalculated_refit(self) -> None:
        """
        Validates empty target pool with nonempty fit:
        - Train fitting pool (200..205) is nonempty -> train fit is valid.
        - Remove VIX only in the development target block (226..239).
        - Development block: fit is NOT None, predictions=(), unavailable_reason=None.
        - Independent recalculation of affected refit oracle:
          Refit fitting rows are 200..225 (26 rows; 226..239 excluded due to missing VIX).
          Counts: (4, 18, 4), smoothed probabilities: (5/29, 19/29, 5/29).
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
        # Omit VIX strictly at 226..239
        missing_vix_targets = tuple(range(226, 240))
        features, outcomes, dates = self._build_oracle_fixture(
            n_origins=N,
            missing_vix_indices=missing_vix_targets,
            close_overrides=close_overrides,
            prefix="empty_target",
        )

        result = build_frequency_predictions(
            features,
            outcomes,
            development_start=dates[D],
            test_start=dates[T],
        )

        dev_b = result.development_block
        # Nonempty fit is preserved!
        self.assertIsNotNone(dev_b.fit)
        self.assertEqual(dev_b.fit.fitting_indices, tuple(range(200, 206)))
        self.assertEqual(dev_b.fit.class_counts, (3, 2, 1))
        self.assertEqual(dev_b.fit.probabilities, (4.0 / 9.0, 3.0 / 9.0, 2.0 / 9.0))
        # Empty target pool: predictions is empty, unavailable_reason is None!
        self.assertEqual(dev_b.requested_indices, ())
        self.assertEqual(dev_b.predictions, ())
        self.assertIsNone(dev_b.unavailable_reason)

        # Recalculated refit oracle:
        # Refit fitting indices: 200..225 (26 rows).
        # In 200..225:
        # Bear: 200, 201, 202 (mature at 220..222=99), 225 (origin 101, matures at 245=100) -> 4 BEAR.
        # Bull: 205 (mature at 225=101), 220, 221, 222 (origins 99, mature at 240..242=100) -> 4 BULL.
        # Neutral: 26 - 8 = 18 NEUTRAL.
        # Counts: (4, 18, 4), N = 26.
        # Smoothed probs: ((4+1)/29, (18+1)/29, (4+1)/29) = (5/29, 19/29, 5/29).
        test_fit = result.test_block.fit
        self.assertIsNotNone(test_fit)
        self.assertEqual(len(test_fit.fitting_indices), 26)
        self.assertEqual(test_fit.class_counts, (4, 18, 4))
        expected_refit_recalculated = (5.0 / 29.0, 19.0 / 29.0, 5.0 / 29.0)
        self.assertEqual(test_fit.probabilities, expected_refit_recalculated)
        self.assertTrue(math.isclose(sum(test_fit.probabilities), 1.0, abs_tol=1e-12))

    def test_08_planner_boundary_error_propagation(self) -> None:
        """
        Validates that planner-boundary errors (invalid boundary dates, ordering, calendar)
        fail through build_frequency_predictions reporting the responsible field.
        """
        N = 300
        features, outcomes, dates = self._build_oracle_fixture(n_origins=N, prefix="planner_err")
        d_valid = dates[226]
        t_valid = dates[260]

        # Off-axis development_start date
        off_axis = datetime.date(1999, 1, 1)
        with self.assertRaises(InputValidationError) as ctx:
            build_frequency_predictions(features, outcomes, development_start=off_axis, test_start=t_valid)
        self.assertEqual(ctx.exception.field, "development_start")

        # Boundary inversion: D >= T
        with self.assertRaises(InputValidationError) as ctx:
            build_frequency_predictions(features, outcomes, development_start=t_valid, test_start=d_valid)
        self.assertEqual(ctx.exception.field, "development_start")

        # Wrong series role in outcomes
        bad_outcomes = OutcomeSeries(series_id="india_vix", outcomes=outcomes.outcomes)
        with self.assertRaises(InputValidationError) as ctx:
            build_frequency_predictions(features, bad_outcomes, development_start=d_valid, test_start=t_valid)
        self.assertEqual(ctx.exception.field, "series_id")

        # Invalid supplied calendar status
        bad_calendar_features = replace(features, calendar_status="mismatch")
        with self.assertRaises(InputValidationError) as ctx:
            build_frequency_predictions(bad_calendar_features, outcomes, development_start=d_valid, test_start=t_valid)
        self.assertEqual(ctx.exception.field, "calendar_status")

        # Divergent paired origin date between features and outcomes
        divergent_outcome_list = list(outcomes.outcomes)
        tampered_o = divergent_outcome_list[5]
        divergent_outcome_list[5] = replace(
            tampered_o,
            origin_date=tampered_o.origin_date + datetime.timedelta(days=1),
        )
        divergent_outcomes = OutcomeSeries(
            series_id=outcomes.series_id,
            outcomes=tuple(divergent_outcome_list),
        )
        with self.assertRaises(InputValidationError) as ctx:
            build_frequency_predictions(features, divergent_outcomes, development_start=d_valid, test_start=t_valid)
        self.assertEqual(ctx.exception.field, "origin_date")

    def test_09_immutability_and_repeated_call_equality(self) -> None:
        """
        Validates:
        - Frozen dataclass immutability for FrequencyResult, FrequencyBlock, FrequencyFit,
          FrequencyPrediction (FrozenInstanceError).
        - Source FeatureSeries and OutcomeSeries are verified untouched via deepcopy snapshots.
        - Repeated calls with identical inputs produce equal results.
        """
        N = 300
        D = 226
        T = 260
        features, outcomes, dates = self._build_oracle_fixture(n_origins=N, prefix="immut")

        # Raw synthetic CSV fixture paths and bytes before execution
        nifty_csv_path = self.test_dir / "immut_nifty.csv"
        vix_csv_path = self.test_dir / "immut_vix.csv"
        nifty_bytes_before = nifty_csv_path.read_bytes()
        vix_bytes_before = vix_csv_path.read_bytes()

        # Deep snapshots before execution
        feat_snap = copy.deepcopy(features)
        out_snap = copy.deepcopy(outcomes)

        res1 = build_frequency_predictions(features, outcomes, development_start=dates[D], test_start=dates[T])
        res2 = build_frequency_predictions(features, outcomes, development_start=dates[D], test_start=dates[T])

        # Inputs are completely unmutated
        self.assertEqual(features, feat_snap)
        self.assertEqual(outcomes, out_snap)
        self.assertEqual(nifty_csv_path.read_bytes(), nifty_bytes_before)
        self.assertEqual(vix_csv_path.read_bytes(), vix_bytes_before)

        # Repeated-call equality
        self.assertEqual(res1, res2)
        self.assertEqual(res1.development_block, res2.development_block)
        self.assertEqual(res1.test_block, res2.test_block)

        # Frozen dataclass mutation rejection
        with self.assertRaises(FrozenInstanceError):
            res1.method = "tampered"  # type: ignore[misc]

        with self.assertRaises(FrozenInstanceError):
            res1.development_block = res1.test_block  # type: ignore[misc]

        dev_b = res1.development_block
        with self.assertRaises(FrozenInstanceError):
            dev_b.partition = "test"  # type: ignore[misc]

        dev_fit = dev_b.fit
        self.assertIsNotNone(dev_fit)
        with self.assertRaises(FrozenInstanceError):
            dev_fit.probabilities = (0.0, 1.0, 0.0)  # type: ignore[misc]

        pred0 = dev_b.predictions[0]
        with self.assertRaises(FrozenInstanceError):
            pred0.probabilities = (0.0, 0.0, 1.0)  # type: ignore[misc]

    def test_10_module_imports_and_clean_boundary(self) -> None:
        """
        Audits module dependencies and imports (SOURCE_INSPECTED):
        - research.prediction_eval.frequency contains zero network, random, model, or
          external math libraries.
        """
        import research.prediction_eval.frequency as freq_mod

        mod_dict = freq_mod.__dict__
        forbidden_terms = (
            "random",
            "urllib",
            "requests",
            "socket",
            "subprocess",
            "pandas",
            "numpy",
            "scipy",
            "sklearn",
            "joblib",
            "pickle",
        )
        for term in forbidden_terms:
            self.assertNotIn(term, mod_dict, f"Forbidden term '{term}' found in frequency module namespace.")


if __name__ == "__main__":
    unittest.main()
