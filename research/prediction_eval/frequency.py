"""
Prediction Evaluation Fixed-Frequency Baseline Comparator.

Provides deterministic, inspectable Laplace-smoothed empirical frequency predictions
for chronological evaluation partitions planned by build_split_plan.

Architectural ownership:
    inputs.py owns raw CSV loading, validation, provenance, and alignment.
    outcomes.py owns 20-session horizon classification (+/-0.5% band).
    features.py owns origin-time causal indicator construction.
    splits.py owns chronological split planning, strict-before purging, and refit tracking.
    frequency.py owns the fixed Laplace-1 empirical class frequency comparator and its
    concrete immutable output records.

Comparator policy:
    1. Split plan delegation: delegates once to build_split_plan with exact caller cutoffs.
       Accepts no caller plan, fitting indices, smoothing knob, or online-update mode.
    2. Two independent fixed fits:
       - Development block: fits strictly plan.train_indices once; predicts plan.development_indices.
         Label cutoff is plan.development_start_index and plan.development_start.
       - Test block: fits strictly plan.refit_indices once; predicts plan.test_indices.
         Label cutoff is plan.test_start_index and plan.test_start.
       - Never updates development fit with development outcomes after constructing refit.
    3. Laplace smoothing: fixed alpha = 1. Fixed class order: BEAR, NEUTRAL, BULL.
       Probabilities: (c_k + 1) / (N + 3). Full binary64 precision, no display rounding or clipping.
       Valid when one, two, or all three classes are observed in a nonempty fitting pool (individual class counts may be zero). Zero fitting rows yields the unavailable no_fit_rows state.
    4. Unavailable fitting state:
       - Empty fitting pool (len == 0): fit = None, unavailable_reason = 'no_fit_rows',
         predictions = (), retaining requested target indices.
       - Nonempty fit with empty target pool: preserves fit, predictions = (), unavailable_reason = None.
    5. Pure standard library: in-memory calculation with zero file I/O, process, clock, or network calls.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Optional, Sequence, Tuple
from dataclasses import dataclass

from research.prediction_eval.inputs import (
    InputValidationError,
    SUPPORTED_SERIES_IDS,
)
from research.prediction_eval.features import (
    FeatureSeries,
    PROTOCOL_ID,
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

METHOD_ID: str = "fixed-laplace1-frequency-v1"
ALPHA: float = 1.0
OUTCOME_DEFINITION: str = "close-return-20-session-half-percent-neutral-inclusive-v1"
SERIES_ID: str = "nifty50_price_index"

UNAVAILABLE_REASON_NO_FIT_ROWS: str = "no_fit_rows"

ORDERED_CLASSES: Tuple[str, ...] = (
    OUTCOME_CLASS_BEAR,
    OUTCOME_CLASS_NEUTRAL,
    OUTCOME_CLASS_BULL,
)


@dataclass(frozen=True)
class FrequencyPrediction:
    """
    Point prediction record for a single origin observation in a target block.

    Attributes:
        origin_index: Positional index on the original supplied Nifty axis.
        origin_date: Exact calendar date of the origin observation.
        probabilities: Ordered probability tuple in fixed order (BEAR, NEUTRAL, BULL).
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
            if not isinstance(p, float) or not (0.0 <= p <= 1.0):
                raise ValueError(f"probability component must be float in [0, 1], got {p!r}")
        prob_sum = sum(self.probabilities)
        if abs(prob_sum - 1.0) > 1e-12:
            raise ValueError(f"probabilities must sum to 1 within 1e-12, got {prob_sum}")


@dataclass(frozen=True)
class FrequencyFit:
    """
    Fixed empirical class frequency fit with Laplace smoothing (alpha=1).

    Attributes:
        fitting_indices: Immutable tuple of original positional indices admitted to this fit.
        cutoff_index: Strict integer cutoff index; no outcome label at or after this cutoff enters the fit.
        cutoff_date: Strict cutoff date corresponding to cutoff_index.
        class_counts: Exact integer counts in fixed order (BEAR, NEUTRAL, BULL).
        probabilities: Smoothed probabilities in fixed order (BEAR, NEUTRAL, BULL).
    """

    fitting_indices: Tuple[int, ...]
    cutoff_index: int
    cutoff_date: datetime.date
    class_counts: Tuple[int, int, int]
    probabilities: Tuple[float, float, float]

    def __post_init__(self) -> None:
        if type(self.fitting_indices) is not tuple:
            raise ValueError(f"fitting_indices must be a tuple, got {type(self.fitting_indices).__name__}")
        if type(self.cutoff_index) is not int or self.cutoff_index < 0:
            raise ValueError(f"cutoff_index must be a non-negative int, got {self.cutoff_index!r}")
        if type(self.cutoff_date) is not datetime.date:
            raise ValueError(f"cutoff_date must be datetime.date, got {type(self.cutoff_date).__name__}")
        if type(self.class_counts) is not tuple or len(self.class_counts) != 3:
            raise ValueError(f"class_counts must be a 3-tuple of ints, got {self.class_counts!r}")
        for c in self.class_counts:
            if type(c) is not int or c < 0:
                raise ValueError(f"class count must be a non-negative int, got {c!r}")
        if sum(self.class_counts) != len(self.fitting_indices):
            raise ValueError(
                f"Sum of class_counts ({sum(self.class_counts)}) must equal number of fitting_indices ({len(self.fitting_indices)})"
            )
        if type(self.probabilities) is not tuple or len(self.probabilities) != 3:
            raise ValueError(f"probabilities must be a 3-tuple, got {self.probabilities!r}")
        for p in self.probabilities:
            if not isinstance(p, float) or not (0.0 <= p <= 1.0):
                raise ValueError(f"probability component must be float in [0, 1], got {p!r}")
        prob_sum = sum(self.probabilities)
        if abs(prob_sum - 1.0) > 1e-12:
            raise ValueError(f"probabilities must sum to 1 within 1e-12, got {prob_sum}")


@dataclass(frozen=True)
class FrequencyBlock:
    """
    Evaluation block container for a partition (development or test).

    Attributes:
        partition: Chronological partition name ('development' or 'test').
        requested_indices: Canonical target indices from SplitPlan in original order.
        fit: Optional FrequencyFit; None when fitting pool had zero rows.
        predictions: Tuple of FrequencyPrediction records, one per requested index when fit is available.
        unavailable_reason: Optional string reason (e.g. 'no_fit_rows'); None when fit succeeded.
    """

    partition: str
    requested_indices: Tuple[int, ...]
    fit: Optional[FrequencyFit]
    predictions: Tuple[FrequencyPrediction, ...]
    unavailable_reason: Optional[str]

    def __post_init__(self) -> None:
        if self.partition not in (PARTITION_DEVELOPMENT, PARTITION_TEST):
            raise ValueError(f"Invalid block partition '{self.partition}'; expected 'development' or 'test'")
        if type(self.requested_indices) is not tuple:
            raise ValueError(f"requested_indices must be a tuple, got {type(self.requested_indices).__name__}")
        if type(self.predictions) is not tuple:
            raise ValueError(f"predictions must be a tuple, got {type(self.predictions).__name__}")
        if self.fit is None:
            if self.unavailable_reason is None:
                raise ValueError("unavailable_reason must be specified when fit is None")
            if len(self.predictions) != 0:
                raise ValueError("predictions must be empty when fit is None")
        else:
            if self.unavailable_reason is not None:
                raise ValueError(f"unavailable_reason must be None when fit is present, got {self.unavailable_reason!r}")
            if len(self.requested_indices) > 0 and len(self.predictions) != len(self.requested_indices):
                raise ValueError(
                    f"predictions count ({len(self.predictions)}) must match requested_indices count ({len(self.requested_indices)})"
                )


@dataclass(frozen=True)
class FrequencyResult:
    """
    Immutable result of fixed Laplace-1 empirical frequency baseline prediction.

    Attributes:
        method: Identifier 'fixed-laplace1-frequency-v1'.
        alpha: Fixed Laplace smoothing parameter (1.0).
        classes: Ordered outcome classes ('BEAR', 'NEUTRAL', 'BULL').
        series_id: Canonical asset series ID ('nifty50_price_index').
        horizon_sessions: Forward horizon in trading sessions (20).
        protocol_id: Feature calculation protocol ID ('nifty-close-features-v1').
        outcome_definition: Identifier for +/-0.5% band outcome definition.
        plan: SplitPlan produced by build_split_plan.
        development_block: FrequencyBlock for the development partition.
        test_block: FrequencyBlock for the test partition.
    """

    method: str
    alpha: float
    classes: Tuple[str, ...]
    series_id: str
    horizon_sessions: int
    protocol_id: str
    outcome_definition: str
    plan: SplitPlan
    development_block: FrequencyBlock
    test_block: FrequencyBlock

    @property
    def version(self) -> str:
        """Alias for method identifier."""
        return self.method

    @property
    def method_id(self) -> str:
        """Alias for method identifier."""
        return self.method

    @property
    def development(self) -> FrequencyBlock:
        """Alias for development_block."""
        return self.development_block

    @property
    def test(self) -> FrequencyBlock:
        """Alias for test_block."""
        return self.test_block


def _fit_and_predict_block(
    partition: str,
    fitting_indices: Tuple[int, ...],
    target_indices: Tuple[int, ...],
    cutoff_index: int,
    cutoff_date: datetime.date,
    outcomes: OutcomeSeries,
    plan: SplitPlan,
) -> FrequencyBlock:
    """
    Fits empirical class counts and predicts probabilities for a single evaluation block.

    Parameters:
        partition: 'development' or 'test'.
        fitting_indices: Tuple of positional indices admitted for fitting.
        target_indices: Tuple of positional indices requested for prediction.
        cutoff_index: Strict integer cutoff index for label availability.
        cutoff_date: Strict cutoff date for label availability.
        outcomes: Validated OutcomeSeries.
        plan: Canonical SplitPlan mapping indices to origin dates.

    Returns:
        FrequencyBlock with fit and prediction tuples, or unavailable state when fitting pool is empty.
    """
    if len(fitting_indices) == 0:
        return FrequencyBlock(
            partition=partition,
            requested_indices=target_indices,
            fit=None,
            predictions=(),
            unavailable_reason=UNAVAILABLE_REASON_NO_FIT_ROWS,
        )

    b_count = 0
    n_count = 0
    u_count = 0

    for idx in fitting_indices:
        cls = outcomes[idx].outcome_class
        if cls == OUTCOME_CLASS_BEAR:
            b_count += 1
        elif cls == OUTCOME_CLASS_NEUTRAL:
            n_count += 1
        elif cls == OUTCOME_CLASS_BULL:
            u_count += 1
        else:
            raise ValueError(f"Unexpected outcome_class '{cls}' at origin index {idx}")

    n_total = len(fitting_indices)
    denom = float(n_total + 3)
    b_prob = float(b_count + 1) / denom
    n_prob = float(n_count + 1) / denom
    u_prob = float(u_count + 1) / denom
    probs = (b_prob, n_prob, u_prob)
    counts = (b_count, n_count, u_count)

    fit = FrequencyFit(
        fitting_indices=fitting_indices,
        cutoff_index=cutoff_index,
        cutoff_date=cutoff_date,
        class_counts=counts,
        probabilities=probs,
    )

    if len(target_indices) == 0:
        predictions = ()
    else:
        preds = []
        for t_idx in target_indices:
            t_date = plan.decisions[t_idx].origin_date
            preds.append(
                FrequencyPrediction(
                    origin_index=t_idx,
                    origin_date=t_date,
                    probabilities=probs,
                )
            )
        predictions = tuple(preds)

    return FrequencyBlock(
        partition=partition,
        requested_indices=target_indices,
        fit=fit,
        predictions=predictions,
        unavailable_reason=None,
    )


def build_frequency_predictions(
    features: FeatureSeries,
    outcomes: OutcomeSeries,
    *,
    development_start: datetime.date,
    test_start: datetime.date,
) -> FrequencyResult:
    """
    Generates fixed Laplace-1 empirical class frequency predictions for evaluation partitions.

    Parameters:
        features: Validated FeatureSeries produced by compute_nifty_features.
        outcomes: Validated OutcomeSeries produced by compute_twenty_session_outcomes.
        development_start: Date marking the start of the development block (exclusive train end).
        test_start: Date marking the start of the test block (exclusive development end).

    Returns:
        FrequencyResult exposing canonical plan, development block, and test block.

    Raises:
        InputValidationError: On any input schema, axis, date, or calendar defect propagated from
                              build_split_plan.
    """
    plan = build_split_plan(
        features,
        outcomes,
        development_start=development_start,
        test_start=test_start,
    )

    dev_block = _fit_and_predict_block(
        partition=PARTITION_DEVELOPMENT,
        fitting_indices=plan.train_indices,
        target_indices=plan.development_indices,
        cutoff_index=plan.development_start_index,
        cutoff_date=plan.development_start,
        outcomes=outcomes,
        plan=plan,
    )

    test_block = _fit_and_predict_block(
        partition=PARTITION_TEST,
        fitting_indices=plan.refit_indices,
        target_indices=plan.test_indices,
        cutoff_index=plan.test_start_index,
        cutoff_date=plan.test_start,
        outcomes=outcomes,
        plan=plan,
    )

    return FrequencyResult(
        method=METHOD_ID,
        alpha=ALPHA,
        classes=ORDERED_CLASSES,
        series_id=SERIES_ID,
        horizon_sessions=HORIZON_SESSIONS,
        protocol_id=PROTOCOL_ID,
        outcome_definition=OUTCOME_DEFINITION,
        plan=plan,
        development_block=dev_block,
        test_block=test_block,
    )


__all__ = [
    "ALPHA",
    "FrequencyBlock",
    "FrequencyFit",
    "FrequencyPrediction",
    "FrequencyResult",
    "METHOD_ID",
    "ORDERED_CLASSES",
    "OUTCOME_DEFINITION",
    "SERIES_ID",
    "UNAVAILABLE_REASON_NO_FIT_ROWS",
    "build_frequency_predictions",
]
