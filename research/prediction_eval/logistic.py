"""
Prediction Evaluation Fixed Logistic Regression Comparator.

Provides deterministic, inspectable, offline L2-regularized multinomial logistic
regression comparator predictions for chronological evaluation partitions planned
by build_split_plan.

Architectural ownership:
    inputs.py owns raw CSV loading, validation, provenance, and alignment.
    outcomes.py owns 20-session horizon classification (+/-0.5% band).
    features.py owns origin-time causal indicator construction.
    splits.py owns chronological split planning, strict-before purging, and refit tracking.
    frequency.py owns the fixed Laplace-1 empirical class frequency baseline.
    logistic.py owns the fixed logistic comparator, numerical scaling, estimator fitting,
    warning ownership, and concrete immutable output records.

Comparator policy:
    1. Split plan delegation: delegates exactly once to build_split_plan with exact caller
       cutoffs. Accepts no caller plan, indices, tuning hyperparameters, or alternate planner.
    2. Shared payload validation: validates all selected fitting and target payloads from both
       blocks before evaluating availability or performing any fit. Rejects unsupported types,
       booleans, strings, non-finites, and conversion overflow as InputValidationError.
    3. Two independent fixed fits:
       - Development block: fits strictly plan.train_indices once; predicts plan.development_indices.
         Label cutoff is plan.development_start_index and plan.development_start.
       - Test block: fits strictly plan.refit_indices once; predicts plan.test_indices.
         Label cutoff is plan.test_start_index and plan.test_start.
       - Development model and predictions are never updated after constructing refit.
    4. Admitted fixed numerical configuration:
       - scikit-learn 1.9.1 LogisticRegression(l1_ratio=0.0, C=1.0, solver='lbfgs',
         fit_intercept=True, tol=1e-6, max_iter=2000, class_weight=None, warm_start=False, verbose=0).
       - Features: 6 numeric standardized via StandardScaler (fitted only to that block's fitting rows)
         plus 6 unscaled one-hot regime indicators in fixed features.VALID_REGIMES order.
       - Classes: mapped BEAR=0, NEUTRAL=1, BULL=2. Verified classes_ == [0, 1, 2].
    5. Closed unavailable vocabulary and deterministic precedence:
       - no_fit_rows: empty fitting pool (failure_stage is None).
       - missing_training_classes: fewer than all 3 classes observed (failure_stage is None).
       - not_converged: ConvergenceWarning raised during fit (failure_stage='fit').
       - nonfinite_model_state: nonfinite scaler/fit/prediction state (failure_stage distinguishes
         'scaler', 'fit', or 'prediction').
       - A prediction-stage failure discards the fit and all predictions for that block.
    6. Warning ownership:
       - Narrowly scopes catch_warnings(record=False) and filterwarnings('error', category=ConvergenceWarning)
         strictly around estimator.fit. Context exit restores surrounding policy on success and exception.
    7. Pure computational module:
       - Serial execution only. No subprocesses, network, filesystem I/O, timestamps, thread mutation,
         or global environment alterations.
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime
import math
from typing import Optional, Sequence, Tuple, Union
import warnings

import numpy as np
import scipy
import sklearn
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from research.prediction_eval.inputs import InputValidationError
from research.prediction_eval.features import (
    FeatureSeries,
    NiftyFeatureRecord,
    PredictorPayload,
    PROTOCOL_ID,
    VALID_REGIMES,
)
from research.prediction_eval.outcomes import (
    HORIZON_SESSIONS,
    OutcomeSeries,
    OUTCOME_CLASS_BEAR,
    OUTCOME_CLASS_BULL,
    OUTCOME_CLASS_NEUTRAL,
    VALID_OUTCOME_CLASSES,
)
from research.prediction_eval.splits import (
    PARTITION_DEVELOPMENT,
    PARTITION_TEST,
    PARTITION_TRAIN,
    SplitPlan,
    build_split_plan,
)

METHOD_ID: str = "fixed-logistic-v1"
SERIES_ID: str = "nifty50_price_index"
OUTCOME_DEFINITION: str = "close-return-20-session-half-percent-neutral-inclusive-v1"

UNAVAILABLE_REASON_NO_FIT_ROWS: str = "no_fit_rows"
UNAVAILABLE_REASON_MISSING_TRAINING_CLASSES: str = "missing_training_classes"
UNAVAILABLE_REASON_NOT_CONVERGED: str = "not_converged"
UNAVAILABLE_REASON_NONFINITE_MODEL_STATE: str = "nonfinite_model_state"

CLOSED_UNAVAILABLE_REASONS: Tuple[str, ...] = (
    UNAVAILABLE_REASON_NO_FIT_ROWS,
    UNAVAILABLE_REASON_MISSING_TRAINING_CLASSES,
    UNAVAILABLE_REASON_NOT_CONVERGED,
    UNAVAILABLE_REASON_NONFINITE_MODEL_STATE,
)

STAGE_SCALER: str = "scaler"
STAGE_FIT: str = "fit"
STAGE_PREDICTION: str = "prediction"
VALID_FAILURE_STAGES: Tuple[str, ...] = (
    STAGE_SCALER,
    STAGE_FIT,
    STAGE_PREDICTION,
)

NUMERIC_FEATURE_NAMES: Tuple[str, ...] = (
    "ret_5d",
    "rsi_14",
    "macd_hist",
    "vol_30d",
    "rel_strength_20d",
    "drawdown",
)

ENCODED_FEATURE_NAMES: Tuple[str, ...] = tuple(f"regime_{r}" for r in VALID_REGIMES)
ALL_FEATURE_NAMES: Tuple[str, ...] = NUMERIC_FEATURE_NAMES + ENCODED_FEATURE_NAMES

ORDERED_CLASSES: Tuple[str, ...] = (
    OUTCOME_CLASS_BEAR,
    OUTCOME_CLASS_NEUTRAL,
    OUTCOME_CLASS_BULL,
)

CLASS_TO_INT = {
    OUTCOME_CLASS_BEAR: 0,
    OUTCOME_CLASS_NEUTRAL: 1,
    OUTCOME_CLASS_BULL: 2,
}

INT_TO_CLASS = {
    0: OUTCOME_CLASS_BEAR,
    1: OUTCOME_CLASS_NEUTRAL,
    2: OUTCOME_CLASS_BULL,
}


@dataclass(frozen=True)
class LogisticConfiguration:
    """Fixed inspectable configuration for the logistic regression estimator."""

    solver: str = "lbfgs"
    c: float = 1.0
    l1_ratio: float = 0.0
    fit_intercept: bool = True
    tol: float = 1e-6
    max_iter: int = 2000
    class_weight: Optional[str] = None
    warm_start: bool = False
    verbose: int = 0


@dataclass(frozen=True)
class LogisticPrediction:
    """
    Point prediction record for a single origin observation in a target block.

    Attributes:
        origin_index: Positional index on the original supplied Nifty axis.
        origin_date: Exact calendar date of the origin observation.
        probabilities: Ordered finite probability tuple in fixed order (BEAR, NEUTRAL, BULL).
    """

    origin_index: int
    origin_date: datetime.date
    probabilities: Tuple[float, float, float]

    def __post_init__(self) -> None:
        if type(self.origin_index) is not int or self.origin_index < 0:
            raise ValueError(f"origin_index must be a non-negative int, got {self.origin_index!r}")
        if type(self.origin_date) is not datetime.date:
            raise ValueError(f"origin_date must be datetime.date, got {type(self.origin_date).__name__}")
        if type(self.probabilities) is not tuple or len(self.probabilities) != 3:
            raise ValueError(f"probabilities must be a 3-tuple, got {self.probabilities!r}")
        for p in self.probabilities:
            if not isinstance(p, float) or isinstance(p, bool) or not math.isfinite(p) or not (0.0 <= p <= 1.0):
                raise ValueError(f"probability component must be finite float in [0, 1], got {p!r}")
        prob_sum = sum(self.probabilities)
        if abs(prob_sum - 1.0) > 1e-12:
            raise ValueError(f"probabilities must sum to 1 within 1e-12, got {prob_sum}")


@dataclass(frozen=True)
class LogisticFit:
    """
    Recorded parameter state of a converged logistic regression fit.

    Attributes:
        numeric_means: StandardScaler empirical means for 6 numeric features.
        numeric_variances: StandardScaler empirical variances for 6 numeric features.
        numeric_scales: StandardScaler scale values (standard deviations) for 6 numeric features.
        coefficients: Coefficient matrix of shape (3, 12) for (classes, features).
        intercepts: Intercept vector of length 3 (one per class).
        n_iter: Number of optimization iterations performed.
        classes: Ordered outcome classes ('BEAR', 'NEUTRAL', 'BULL').
        feature_names: Ordered declared feature names (6 numeric + 6 one-hot).
    """

    numeric_means: Tuple[float, ...]
    numeric_variances: Tuple[float, ...]
    numeric_scales: Tuple[float, ...]
    coefficients: Tuple[Tuple[float, ...], ...]
    intercepts: Tuple[float, ...]
    n_iter: int
    classes: Tuple[str, ...] = ORDERED_CLASSES
    feature_names: Tuple[str, ...] = ALL_FEATURE_NAMES

    def __post_init__(self) -> None:
        if type(self.numeric_means) is not tuple or len(self.numeric_means) != 6:
            raise ValueError(f"numeric_means must be a 6-tuple of floats, got {self.numeric_means!r}")
        if type(self.numeric_variances) is not tuple or len(self.numeric_variances) != 6:
            raise ValueError(f"numeric_variances must be a 6-tuple of floats, got {self.numeric_variances!r}")
        if type(self.numeric_scales) is not tuple or len(self.numeric_scales) != 6:
            raise ValueError(f"numeric_scales must be a 6-tuple of floats, got {self.numeric_scales!r}")
        for seq in (self.numeric_means, self.numeric_variances, self.numeric_scales):
            for v in seq:
                if not isinstance(v, float) or isinstance(v, bool) or not math.isfinite(v):
                    raise ValueError(f"Scaler vector values must be finite floats, got {v!r}")

        if type(self.coefficients) is not tuple or len(self.coefficients) != 3:
            raise ValueError(f"coefficients must be a 3-tuple of rows, got {self.coefficients!r}")
        for row in self.coefficients:
            if type(row) is not tuple or len(row) != 12:
                raise ValueError(f"coefficient row must be a 12-tuple, got {row!r}")
            for c in row:
                if not isinstance(c, float) or isinstance(c, bool) or not math.isfinite(c):
                    raise ValueError(f"coefficient values must be finite floats, got {c!r}")

        if type(self.intercepts) is not tuple or len(self.intercepts) != 3:
            raise ValueError(f"intercepts must be a 3-tuple of floats, got {self.intercepts!r}")
        for b in self.intercepts:
            if not isinstance(b, float) or isinstance(b, bool) or not math.isfinite(b):
                raise ValueError(f"intercept values must be finite floats, got {b!r}")

        if type(self.n_iter) is not int or self.n_iter < 0:
            raise ValueError(f"n_iter must be a non-negative int, got {self.n_iter!r}")
        if type(self.classes) is not tuple or self.classes != ORDERED_CLASSES:
            raise ValueError(f"classes must be {ORDERED_CLASSES}, got {self.classes!r}")
        if type(self.feature_names) is not tuple or self.feature_names != ALL_FEATURE_NAMES:
            raise ValueError(f"feature_names must be {ALL_FEATURE_NAMES}, got {self.feature_names!r}")


@dataclass(frozen=True)
class LogisticBlock:
    """
    Evaluation block container for a partition (development or test).

    Attributes:
        partition: Chronological partition name ('development' or 'test').
        fitting_indices: Immutable tuple of original positional indices admitted to this fit.
        cutoff_index: Strict integer cutoff index for label availability.
        cutoff_date: Strict cutoff date corresponding to cutoff_index.
        class_counts: Exact integer counts in fixed order (BEAR, NEUTRAL, BULL).
        regime_counts: Exact integer counts in fixed order (VALID_REGIMES).
        requested_indices: Canonical target indices from SplitPlan in original order.
        fit: Optional LogisticFit; None when unavailable.
        predictions: Tuple of LogisticPrediction records, one per requested index when fit is available.
        unavailable_reason: Optional closed vocabulary reason; None when fit succeeded.
        failure_stage: Optional failure stage ('scaler', 'fit', 'prediction'); None when succeeded or data-insufficient.
    """

    partition: str
    fitting_indices: Tuple[int, ...]
    cutoff_index: int
    cutoff_date: datetime.date
    class_counts: Tuple[int, int, int]
    regime_counts: Tuple[int, int, int, int, int, int]
    requested_indices: Tuple[int, ...]
    fit: Optional[LogisticFit]
    predictions: Tuple[LogisticPrediction, ...] = ()
    unavailable_reason: Optional[str] = None
    failure_stage: Optional[str] = None

    def __post_init__(self) -> None:
        if self.partition not in (PARTITION_DEVELOPMENT, PARTITION_TEST):
            raise ValueError(f"Invalid block partition '{self.partition}'; expected 'development' or 'test'")
        if type(self.fitting_indices) is not tuple:
            raise ValueError(f"fitting_indices must be a tuple, got {type(self.fitting_indices).__name__}")
        if type(self.cutoff_index) is not int or self.cutoff_index < 0:
            raise ValueError(f"cutoff_index must be a non-negative int, got {self.cutoff_index!r}")
        if type(self.cutoff_date) is not datetime.date:
            raise ValueError(f"cutoff_date must be datetime.date, got {type(self.cutoff_date).__name__}")
        if type(self.class_counts) is not tuple or len(self.class_counts) != 3:
            raise ValueError(f"class_counts must be a 3-tuple, got {self.class_counts!r}")
        for c in self.class_counts:
            if type(c) is not int or c < 0:
                raise ValueError(f"class count must be a non-negative int, got {c!r}")
        if sum(self.class_counts) != len(self.fitting_indices):
            raise ValueError(
                f"Sum of class_counts ({sum(self.class_counts)}) must equal number of fitting_indices ({len(self.fitting_indices)})"
            )

        if type(self.regime_counts) is not tuple or len(self.regime_counts) != len(VALID_REGIMES):
            raise ValueError(f"regime_counts must be a {len(VALID_REGIMES)}-tuple, got {self.regime_counts!r}")
        for r in self.regime_counts:
            if type(r) is not int or r < 0:
                raise ValueError(f"regime count must be a non-negative int, got {r!r}")
        if sum(self.regime_counts) != len(self.fitting_indices):
            raise ValueError(
                f"Sum of regime_counts ({sum(self.regime_counts)}) must equal number of fitting_indices ({len(self.fitting_indices)})"
            )

        if type(self.requested_indices) is not tuple:
            raise ValueError(f"requested_indices must be a tuple, got {type(self.requested_indices).__name__}")
        if type(self.predictions) is not tuple:
            raise ValueError(f"predictions must be a tuple, got {type(self.predictions).__name__}")

        if self.fit is None:
            if self.unavailable_reason is None:
                raise ValueError("unavailable_reason must be specified when fit is None")
            if self.unavailable_reason not in CLOSED_UNAVAILABLE_REASONS:
                raise ValueError(
                    f"unavailable_reason '{self.unavailable_reason}' not in closed vocabulary {CLOSED_UNAVAILABLE_REASONS}"
                )
            if len(self.predictions) != 0:
                raise ValueError("predictions must be empty when fit is None")
            if self.unavailable_reason in (UNAVAILABLE_REASON_NO_FIT_ROWS, UNAVAILABLE_REASON_MISSING_TRAINING_CLASSES):
                if self.failure_stage is not None:
                    raise ValueError(f"failure_stage must be None for {self.unavailable_reason}, got {self.failure_stage!r}")
            elif self.unavailable_reason in (UNAVAILABLE_REASON_NOT_CONVERGED, UNAVAILABLE_REASON_NONFINITE_MODEL_STATE):
                if self.failure_stage not in VALID_FAILURE_STAGES:
                    raise ValueError(f"failure_stage must be in {VALID_FAILURE_STAGES}, got {self.failure_stage!r}")
        else:
            if self.unavailable_reason is not None:
                raise ValueError(f"unavailable_reason must be None when fit is present, got {self.unavailable_reason!r}")
            if self.failure_stage is not None:
                raise ValueError(f"failure_stage must be None when fit is present, got {self.failure_stage!r}")
            if len(self.requested_indices) > 0 and len(self.predictions) != len(self.requested_indices):
                raise ValueError(
                    f"predictions count ({len(self.predictions)}) must match requested_indices count ({len(self.requested_indices)})"
                )
            if len(self.requested_indices) == 0 and len(self.predictions) != 0:
                raise ValueError("predictions must be empty when requested_indices is empty")


@dataclass(frozen=True)
class LogisticResult:
    """
    Immutable result of fixed logistic comparator evaluation.

    Attributes:
        method: Method identifier 'fixed-logistic-v1'.
        configuration: Frozen LogisticConfiguration object.
        classes: Ordered outcome classes ('BEAR', 'NEUTRAL', 'BULL').
        numeric_features: Ordered numeric feature names.
        encoded_features: Ordered one-hot encoded regime feature names.
        regime_order: Ordered regime names.
        series_id: Canonical asset series ID ('nifty50_price_index').
        horizon_sessions: Forward horizon in trading sessions (20).
        protocol_id: Feature calculation protocol ID ('nifty-close-features-v1').
        outcome_definition: Identifier for +/-0.5% band outcome definition.
        dependency_versions: Immutable tuple of (package, version) pairs.
        plan: SplitPlan produced by build_split_plan.
        development_block: LogisticBlock for the development partition.
        test_block: LogisticBlock for the test partition.
    """

    method: str
    configuration: LogisticConfiguration
    classes: Tuple[str, ...]
    numeric_features: Tuple[str, ...]
    encoded_features: Tuple[str, ...]
    regime_order: Tuple[str, ...]
    series_id: str
    horizon_sessions: int
    protocol_id: str
    outcome_definition: str
    dependency_versions: Tuple[Tuple[str, str], ...]
    plan: SplitPlan
    development_block: LogisticBlock
    test_block: LogisticBlock


def _validate_selected_payloads(
    features: FeatureSeries,
    selected_indices: Sequence[int],
) -> None:
    """
    Validates selected fitting and target payloads before checking block availability or fitting.

    Accepts supported native numeric int/float values with bool excluded and finite binary64 conversion.
    Rejects strings, Decimal, complex, unsupported types, nonfinite values, and conversion overflow
    as InputValidationError. Verifies supported string regime.
    """
    for i in selected_indices:
        rec = features.records[i]
        payload = rec.payload
        if payload is None:
            raise InputValidationError(
                f"Missing PredictorPayload at selected origin index {rec.origin_index} ({rec.origin_date})",
                field="payload",
                reason=f"Origin {rec.origin_index} ({rec.origin_date}): payload is None",
            )

        for field_name in NUMERIC_FEATURE_NAMES:
            val = getattr(payload, field_name)
            if type(val) is bool:
                raise InputValidationError(
                    f"Invalid boolean value for numeric field '{field_name}' at origin index {rec.origin_index} ({rec.origin_date})",
                    field=field_name,
                    reason=f"Origin {rec.origin_index} ({rec.origin_date}): boolean {val!r} is not allowed",
                )
            if not isinstance(val, (int, float)):
                raise InputValidationError(
                    f"Unsupported type {type(val).__name__} for numeric field '{field_name}' at origin index {rec.origin_index} ({rec.origin_date})",
                    field=field_name,
                    reason=f"Origin {rec.origin_index} ({rec.origin_date}): type {type(val).__name__} is not allowed",
                )
            try:
                flt_val = float(val)
            except (OverflowError, ValueError) as exc:
                # Name only the rejected value's type: formatting a huge int can itself raise under
                # the interpreter's int-to-string digit limit and would hide this contextual error.
                raise InputValidationError(
                    f"Conversion overflow for numeric field '{field_name}' at origin index {rec.origin_index} ({rec.origin_date}): {exc}",
                    field=field_name,
                    reason=f"Origin {rec.origin_index} ({rec.origin_date}): overflow converting {type(val).__name__} to float",
                ) from exc
            if not math.isfinite(flt_val):
                raise InputValidationError(
                    f"Non-finite value {flt_val} for numeric field '{field_name}' at origin index {rec.origin_index} ({rec.origin_date})",
                    field=field_name,
                    reason=f"Origin {rec.origin_index} ({rec.origin_date}): non-finite float {flt_val}",
                )

        regime = payload.market_regime
        if not isinstance(regime, str) or regime not in VALID_REGIMES:
            raise InputValidationError(
                f"Unsupported market_regime '{regime}' at origin index {rec.origin_index} ({rec.origin_date}); expected one of {VALID_REGIMES}",
                field="market_regime",
                reason=f"Origin {rec.origin_index} ({rec.origin_date}): invalid regime '{regime}'",
            )


def _extract_feature_matrix(
    features: FeatureSeries,
    indices: Sequence[int],
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Extracts raw numeric feature array and unscaled one-hot regime array for the given origin indices.

    Returns:
        X_num: shape (len(indices), 6) float64 array of raw numeric features.
        X_reg: shape (len(indices), 6) float64 array of unscaled one-hot regime columns in VALID_REGIMES order.
    """
    n_rows = len(indices)
    x_num = np.empty((n_rows, 6), dtype=np.float64)
    x_reg = np.zeros((n_rows, 6), dtype=np.float64)

    for row_idx, origin_idx in enumerate(indices):
        p = features.records[origin_idx].payload
        assert p is not None
        x_num[row_idx, 0] = float(p.ret_5d)
        x_num[row_idx, 1] = float(p.rsi_14)
        x_num[row_idx, 2] = float(p.macd_hist)
        x_num[row_idx, 3] = float(p.vol_30d)
        x_num[row_idx, 4] = float(p.rel_strength_20d)
        x_num[row_idx, 5] = float(p.drawdown)

        reg_idx = VALID_REGIMES.index(p.market_regime)
        x_reg[row_idx, reg_idx] = 1.0

    return x_num, x_reg


def _fit_and_predict_block(
    partition: str,
    fitting_indices: Tuple[int, ...],
    target_indices: Tuple[int, ...],
    cutoff_index: int,
    cutoff_date: datetime.date,
    features: FeatureSeries,
    outcomes: OutcomeSeries,
    config: LogisticConfiguration,
) -> LogisticBlock:
    """
    Fits StandardScaler and LogisticRegression on fitting rows and predicts target rows for one block.
    """
    # 1. Exact integer counts in fixed class/regime order across fitting indices
    bear_cnt = sum(1 for i in fitting_indices if outcomes[i].outcome_class == OUTCOME_CLASS_BEAR)
    neutral_cnt = sum(1 for i in fitting_indices if outcomes[i].outcome_class == OUTCOME_CLASS_NEUTRAL)
    bull_cnt = sum(1 for i in fitting_indices if outcomes[i].outcome_class == OUTCOME_CLASS_BULL)
    class_counts = (bear_cnt, neutral_cnt, bull_cnt)

    regime_counts_list = []
    for r in VALID_REGIMES:
        cnt = sum(1 for i in fitting_indices if features.records[i].payload is not None and features.records[i].payload.market_regime == r)
        regime_counts_list.append(cnt)
    regime_counts = tuple(regime_counts_list)

    # 2. Availability Check 1: no_fit_rows
    if len(fitting_indices) == 0:
        return LogisticBlock(
            partition=partition,
            fitting_indices=fitting_indices,
            cutoff_index=cutoff_index,
            cutoff_date=cutoff_date,
            class_counts=(0, 0, 0),
            regime_counts=(0, 0, 0, 0, 0, 0),
            requested_indices=target_indices,
            fit=None,
            predictions=(),
            unavailable_reason=UNAVAILABLE_REASON_NO_FIT_ROWS,
            failure_stage=None,
        )

    # 3. Availability Check 2: missing_training_classes (all 3 required by study policy)
    if bear_cnt == 0 or neutral_cnt == 0 or bull_cnt == 0:
        return LogisticBlock(
            partition=partition,
            fitting_indices=fitting_indices,
            cutoff_index=cutoff_index,
            cutoff_date=cutoff_date,
            class_counts=class_counts,
            regime_counts=regime_counts,
            requested_indices=target_indices,
            fit=None,
            predictions=(),
            unavailable_reason=UNAVAILABLE_REASON_MISSING_TRAINING_CLASSES,
            failure_stage=None,
        )

    # 4. Numerical Phase: stage 'scaler'
    try:
        x_num_fit, x_reg_fit = _extract_feature_matrix(features, fitting_indices)
        scaler = StandardScaler()
        x_num_fit_scaled = scaler.fit_transform(x_num_fit)

        if not (
            np.all(np.isfinite(scaler.mean_))
            and np.all(np.isfinite(scaler.var_))
            and np.all(np.isfinite(scaler.scale_))
            and np.all(np.isfinite(x_num_fit_scaled))
        ):
            return LogisticBlock(
                partition=partition,
                fitting_indices=fitting_indices,
                cutoff_index=cutoff_index,
                cutoff_date=cutoff_date,
                class_counts=class_counts,
                regime_counts=regime_counts,
                requested_indices=target_indices,
                fit=None,
                predictions=(),
                unavailable_reason=UNAVAILABLE_REASON_NONFINITE_MODEL_STATE,
                failure_stage=STAGE_SCALER,
            )
    except (FloatingPointError, OverflowError):
        return LogisticBlock(
            partition=partition,
            fitting_indices=fitting_indices,
            cutoff_index=cutoff_index,
            cutoff_date=cutoff_date,
            class_counts=class_counts,
            regime_counts=regime_counts,
            requested_indices=target_indices,
            fit=None,
            predictions=(),
            unavailable_reason=UNAVAILABLE_REASON_NONFINITE_MODEL_STATE,
            failure_stage=STAGE_SCALER,
        )

    x_fit = np.hstack([x_num_fit_scaled, x_reg_fit])
    y_fit = np.array([CLASS_TO_INT[outcomes[i].outcome_class] for i in fitting_indices], dtype=np.int64)

    # 5. Numerical Phase: stage 'fit'
    clf = LogisticRegression(
        solver=config.solver,
        C=config.c,
        l1_ratio=config.l1_ratio,
        fit_intercept=config.fit_intercept,
        tol=config.tol,
        max_iter=config.max_iter,
        class_weight=config.class_weight,
        warm_start=config.warm_start,
        verbose=config.verbose,
    )

    try:
        try:
            with warnings.catch_warnings(record=False):
                warnings.filterwarnings("error", category=ConvergenceWarning)
                clf.fit(x_fit, y_fit)
        except ConvergenceWarning:
            return LogisticBlock(
                partition=partition,
                fitting_indices=fitting_indices,
                cutoff_index=cutoff_index,
                cutoff_date=cutoff_date,
                class_counts=class_counts,
                regime_counts=regime_counts,
                requested_indices=target_indices,
                fit=None,
                predictions=(),
                unavailable_reason=UNAVAILABLE_REASON_NOT_CONVERGED,
                failure_stage=STAGE_FIT,
            )
    except (FloatingPointError, OverflowError):
        return LogisticBlock(
            partition=partition,
            fitting_indices=fitting_indices,
            cutoff_index=cutoff_index,
            cutoff_date=cutoff_date,
            class_counts=class_counts,
            regime_counts=regime_counts,
            requested_indices=target_indices,
            fit=None,
            predictions=(),
            unavailable_reason=UNAVAILABLE_REASON_NONFINITE_MODEL_STATE,
            failure_stage=STAGE_FIT,
        )

    # Verify programming contract
    if not np.array_equal(clf.classes_, np.array([0, 1, 2])):
        raise RuntimeError(f"Unexpected classes_ from LogisticRegression: {clf.classes_!r}")

    if not (np.all(np.isfinite(clf.coef_)) and np.all(np.isfinite(clf.intercept_))):
        return LogisticBlock(
            partition=partition,
            fitting_indices=fitting_indices,
            cutoff_index=cutoff_index,
            cutoff_date=cutoff_date,
            class_counts=class_counts,
            regime_counts=regime_counts,
            requested_indices=target_indices,
            fit=None,
            predictions=(),
            unavailable_reason=UNAVAILABLE_REASON_NONFINITE_MODEL_STATE,
            failure_stage=STAGE_FIT,
        )

    fit_obj = LogisticFit(
        numeric_means=tuple(float(m) for m in scaler.mean_),
        numeric_variances=tuple(float(v) for v in scaler.var_),
        numeric_scales=tuple(float(s) for s in scaler.scale_),
        coefficients=tuple(tuple(float(c) for c in row) for row in clf.coef_),
        intercepts=tuple(float(b) for b in clf.intercept_),
        n_iter=int(clf.n_iter_[0]),
    )

    # 6. Numerical Phase: stage 'prediction'
    if len(target_indices) == 0:
        return LogisticBlock(
            partition=partition,
            fitting_indices=fitting_indices,
            cutoff_index=cutoff_index,
            cutoff_date=cutoff_date,
            class_counts=class_counts,
            regime_counts=regime_counts,
            requested_indices=target_indices,
            fit=fit_obj,
            predictions=(),
            unavailable_reason=None,
            failure_stage=None,
        )

    try:
        x_num_target, x_reg_target = _extract_feature_matrix(features, target_indices)
        x_num_target_scaled = scaler.transform(x_num_target)
        if not np.all(np.isfinite(x_num_target_scaled)):
            return LogisticBlock(
                partition=partition,
                fitting_indices=fitting_indices,
                cutoff_index=cutoff_index,
                cutoff_date=cutoff_date,
                class_counts=class_counts,
                regime_counts=regime_counts,
                requested_indices=target_indices,
                fit=None,
                predictions=(),
                unavailable_reason=UNAVAILABLE_REASON_NONFINITE_MODEL_STATE,
                failure_stage=STAGE_PREDICTION,
            )

        x_target = np.hstack([x_num_target_scaled, x_reg_target])
        raw_probs = clf.predict_proba(x_target)
        # Backend output contract: exactly one row per requested target and one column per class.
        # Any other shape is a setup/programming error; extra rows or columns must never be
        # consumed as a prefix that looks like available predictions.
        expected_shape = (len(target_indices), len(ORDERED_CLASSES))
        if not isinstance(raw_probs, np.ndarray) or raw_probs.shape != expected_shape:
            raise RuntimeError(
                f"Unexpected predict_proba output shape {getattr(raw_probs, 'shape', None)!r}; expected {expected_shape}"
            )
        if not np.all(np.isfinite(raw_probs)):
            return LogisticBlock(
                partition=partition,
                fitting_indices=fitting_indices,
                cutoff_index=cutoff_index,
                cutoff_date=cutoff_date,
                class_counts=class_counts,
                regime_counts=regime_counts,
                requested_indices=target_indices,
                fit=None,
                predictions=(),
                unavailable_reason=UNAVAILABLE_REASON_NONFINITE_MODEL_STATE,
                failure_stage=STAGE_PREDICTION,
            )
    except (FloatingPointError, OverflowError):
        return LogisticBlock(
            partition=partition,
            fitting_indices=fitting_indices,
            cutoff_index=cutoff_index,
            cutoff_date=cutoff_date,
            class_counts=class_counts,
            regime_counts=regime_counts,
            requested_indices=target_indices,
            fit=None,
            predictions=(),
            unavailable_reason=UNAVAILABLE_REASON_NONFINITE_MODEL_STATE,
            failure_stage=STAGE_PREDICTION,
        )

    # Range [0, 1] and sum within 1e-12 check
    preds_list = []
    for row_idx, target_idx in enumerate(target_indices):
        p0 = float(raw_probs[row_idx, 0])
        p1 = float(raw_probs[row_idx, 1])
        p2 = float(raw_probs[row_idx, 2])
        if not (0.0 <= p0 <= 1.0 and 0.0 <= p1 <= 1.0 and 0.0 <= p2 <= 1.0):
            return LogisticBlock(
                partition=partition,
                fitting_indices=fitting_indices,
                cutoff_index=cutoff_index,
                cutoff_date=cutoff_date,
                class_counts=class_counts,
                regime_counts=regime_counts,
                requested_indices=target_indices,
                fit=None,
                predictions=(),
                unavailable_reason=UNAVAILABLE_REASON_NONFINITE_MODEL_STATE,
                failure_stage=STAGE_PREDICTION,
            )
        p_sum = p0 + p1 + p2
        if abs(p_sum - 1.0) > 1e-12:
            return LogisticBlock(
                partition=partition,
                fitting_indices=fitting_indices,
                cutoff_index=cutoff_index,
                cutoff_date=cutoff_date,
                class_counts=class_counts,
                regime_counts=regime_counts,
                requested_indices=target_indices,
                fit=None,
                predictions=(),
                unavailable_reason=UNAVAILABLE_REASON_NONFINITE_MODEL_STATE,
                failure_stage=STAGE_PREDICTION,
            )

        t_date = features.records[target_idx].origin_date
        preds_list.append(
            LogisticPrediction(
                origin_index=target_idx,
                origin_date=t_date,
                probabilities=(p0, p1, p2),
            )
        )

    return LogisticBlock(
        partition=partition,
        fitting_indices=fitting_indices,
        cutoff_index=cutoff_index,
        cutoff_date=cutoff_date,
        class_counts=class_counts,
        regime_counts=regime_counts,
        requested_indices=target_indices,
        fit=fit_obj,
        predictions=tuple(preds_list),
        unavailable_reason=None,
        failure_stage=None,
    )


def build_logistic_predictions(
    features: FeatureSeries,
    outcomes: OutcomeSeries,
    *,
    development_start: datetime.date,
    test_start: datetime.date,
) -> LogisticResult:
    """
    Generates fixed logistic regression comparator predictions for chronological evaluation partitions.

    Parameters:
        features: Validated FeatureSeries produced by compute_nifty_features.
        outcomes: Validated OutcomeSeries produced by compute_twenty_session_outcomes.
        development_start: Date marking the start of the development block (exclusive train end).
        test_start: Date marking the start of the test block (exclusive development end).

    Returns:
        LogisticResult exposing configuration, classes, feature ordering, dependency versions,
        canonical split plan, development block, and test block.

    Raises:
        InputValidationError: On any input schema, axis, date, or calendar defect propagated from
                              build_split_plan, or on invalid selected predictor payload fields.
    """
    # 1. Delegate exactly once to build_split_plan
    plan = build_split_plan(
        features,
        outcomes,
        development_start=development_start,
        test_start=test_start,
    )

    # 2. Validate all selected fitting and target payloads from BOTH blocks before checking availability
    selected_indices = sorted(
        set(plan.train_indices)
        | set(plan.development_indices)
        | set(plan.refit_indices)
        | set(plan.test_indices)
    )
    _validate_selected_payloads(features, selected_indices)

    # 3. Fixed immutable configuration
    config = LogisticConfiguration()

    # 4. Independently evaluate development and test blocks
    dev_block = _fit_and_predict_block(
        partition=PARTITION_DEVELOPMENT,
        fitting_indices=plan.train_indices,
        target_indices=plan.development_indices,
        cutoff_index=plan.development_start_index,
        cutoff_date=plan.development_start,
        features=features,
        outcomes=outcomes,
        config=config,
    )

    test_block = _fit_and_predict_block(
        partition=PARTITION_TEST,
        fitting_indices=plan.refit_indices,
        target_indices=plan.test_indices,
        cutoff_index=plan.test_start_index,
        cutoff_date=plan.test_start,
        features=features,
        outcomes=outcomes,
        config=config,
    )

    dependency_versions: Tuple[Tuple[str, str], ...] = (
        ("numpy", str(np.__version__)),
        ("scikit-learn", str(sklearn.__version__)),
        ("scipy", str(scipy.__version__)),
    )

    return LogisticResult(
        method=METHOD_ID,
        configuration=config,
        classes=ORDERED_CLASSES,
        numeric_features=NUMERIC_FEATURE_NAMES,
        encoded_features=ENCODED_FEATURE_NAMES,
        regime_order=VALID_REGIMES,
        series_id=SERIES_ID,
        horizon_sessions=HORIZON_SESSIONS,
        protocol_id=PROTOCOL_ID,
        outcome_definition=OUTCOME_DEFINITION,
        dependency_versions=dependency_versions,
        plan=plan,
        development_block=dev_block,
        test_block=test_block,
    )


__all__ = [
    "ALL_FEATURE_NAMES",
    "CLOSED_UNAVAILABLE_REASONS",
    "ENCODED_FEATURE_NAMES",
    "INT_TO_CLASS",
    "CLASS_TO_INT",
    "LogisticBlock",
    "LogisticConfiguration",
    "LogisticFit",
    "LogisticPrediction",
    "LogisticResult",
    "METHOD_ID",
    "NUMERIC_FEATURE_NAMES",
    "ORDERED_CLASSES",
    "OUTCOME_DEFINITION",
    "SERIES_ID",
    "STAGE_FIT",
    "STAGE_PREDICTION",
    "STAGE_SCALER",
    "UNAVAILABLE_REASON_MISSING_TRAINING_CLASSES",
    "UNAVAILABLE_REASON_NO_FIT_ROWS",
    "UNAVAILABLE_REASON_NONFINITE_MODEL_STATE",
    "UNAVAILABLE_REASON_NOT_CONVERGED",
    "VALID_FAILURE_STAGES",
    "build_logistic_predictions",
]
