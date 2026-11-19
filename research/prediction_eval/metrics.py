"""
Prediction Evaluation Scoring and Comparison Foundation.

Provides deterministic, inspectable, standard-library three-class prediction scoring,
confusion matrices, Brier scores, exact log loss, descriptive reliability diagrams,
and multi-model comparison metrics for chronological Nifty 50 evaluation cohorts.

Architectural ownership:
    inputs.py owns raw CSV loading, validation, provenance, and alignment.
    outcomes.py owns 20-session horizon classification (+/-0.5% band).
    features.py owns origin-time causal indicator construction.
    splits.py owns chronological split planning, strict-before purging, and refit tracking.
    frequency.py owns the fixed Laplace-1 empirical class frequency baseline.
    logistic.py owns the fixed logistic regression comparator.
    metrics.py owns three-class probability scoring, independent evaluation metrics,
    and concrete immutable comparison structures.

Scoring boundary:
    Measures supplied predictions against realized outcomes. It neither
    improves, normalizes, nor alters upstream predictions, and makes no claim of
    market forecasting skill or trading profitability.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
import datetime
import math
from typing import Any, List, Optional, Protocol, Sequence, Tuple, Union, runtime_checkable

from research.prediction_eval.inputs import InputValidationError
from research.prediction_eval.outcomes import (
    OUTCOME_CLASS_BEAR,
    OUTCOME_CLASS_BULL,
    OUTCOME_CLASS_NEUTRAL,
)

PROTOCOL_ID: str = "nivesh-three-class-metrics-v1"

CLASSES: Tuple[str, ...] = (
    OUTCOME_CLASS_BEAR,
    OUTCOME_CLASS_NEUTRAL,
    OUTCOME_CLASS_BULL,
)

BIN_EDGES: Tuple[float, ...] = tuple(i / 10.0 for i in range(11))
INTERIOR_EDGES: Tuple[float, ...] = tuple(i / 10.0 for i in range(1, 10))

STATUS_SCORED: str = "scored"
STATUS_EMPTY: str = "empty"

LOG_LOSS_STATE_FINITE: str = "finite"
LOG_LOSS_STATE_INFINITE: str = "infinite"
LOG_LOSS_STATE_EMPTY: str = "empty"


@runtime_checkable
class PredictionLike(Protocol):
    """Read-only structural protocol exposing prediction attributes."""

    @property
    def origin_index(self) -> int: ...

    @property
    def origin_date(self) -> datetime.date: ...

    @property
    def probabilities(self) -> Tuple[float, float, float]: ...


@dataclass(frozen=True)
class EvaluationOrigin:
    """Validated evaluation origin observation with realized outcome class."""

    origin_index: int
    origin_date: datetime.date
    actual_class: str


@dataclass(frozen=True)
class RowScore:
    """Per-origin prediction loss and classification record for a single model."""

    origin: EvaluationOrigin
    probabilities: Tuple[float, float, float]
    predicted_class: str
    brier: float
    log_loss: Optional[float]
    log_loss_state: str


@dataclass(frozen=True)
class ReliabilityBin:
    """Descriptive one-vs-rest reliability calibration bin for a single class."""

    class_label: str
    bin_index: int
    count: int
    mean_probability: Optional[float]
    observed_frequency: Optional[float]


@dataclass(frozen=True)
class ModelMetrics:
    """Summary evaluation metrics and descriptive reliability bins for a single model."""

    row_scores: Tuple[RowScore, ...]
    mean_brier: Optional[float]
    mean_log_loss: Optional[float]
    log_loss_state: str
    zero_actual_probability_count: int
    tie_count: int
    accuracy: Optional[float]
    confusion: Tuple[Tuple[int, int, int], ...]
    class_recall: Tuple[Optional[float], Optional[float], Optional[float]]
    reliability_bins: Tuple[ReliabilityBin, ...]


@dataclass(frozen=True)
class ComparisonMetrics:
    """Immutable three-model comparison metrics scored across a shared cohort."""

    protocol_id: str
    classes: Tuple[str, ...]
    bin_edges: Tuple[float, ...]
    origins: Tuple[EvaluationOrigin, ...]
    sample_count: int
    class_support: Tuple[int, int, int]
    status: str
    heuristic: ModelMetrics
    frequency: ModelMetrics
    logistic: ModelMetrics


def _validate_method_predictions(
    predictions: Any,
    cohort: Sequence[EvaluationOrigin],
    method_name: str,
) -> Tuple[Tuple[float, float, float], ...]:
    """Validates structural protocol conformance and cohort alignment for a method."""
    if len(predictions) != len(cohort):
        raise InputValidationError(
            f"{method_name} prediction count ({len(predictions)}) does not match cohort count ({len(cohort)})",
            field=method_name,
            reason=f"Prediction count mismatch on {method_name}: expected {len(cohort)}, got {len(predictions)}",
        )

    validated_probs: List[Tuple[float, float, float]] = []

    for pos, (pred, expected_orig) in enumerate(zip(predictions, cohort)):
        try:
            p_idx = pred.origin_index
            p_date = pred.origin_date
            raw_probs = pred.probabilities
        except AttributeError as exc:
            raise InputValidationError(
                f"Missing required prediction attribute on {method_name} at position {pos}: {exc}",
                field=method_name,
                reason=f"Missing prediction attribute on {method_name} at position {pos}",
            ) from exc

        if type(p_idx) is not int or isinstance(p_idx, bool):
            raise InputValidationError(
                f"origin_index on {method_name} at position {pos} must be a native int, got {type(p_idx).__name__}",
                field="origin_index",
                reason=f"Non-integer origin_index on {method_name} at position {pos}",
            )

        if type(p_date) is not datetime.date or isinstance(p_date, datetime.datetime):
            raise InputValidationError(
                f"origin_date on {method_name} at position {pos} must be exact datetime.date, got {type(p_date).__name__}",
                field="origin_date",
                reason=f"Invalid origin_date type on {method_name} at position {pos}",
            )

        if p_idx != expected_orig.origin_index:
            raise InputValidationError(
                f"origin_index mismatch on {method_name} at position {pos}",
                field="origin_index",
                reason=f"origin_index mismatch on {method_name} at position {pos}",
            )

        if p_date != expected_orig.origin_date:
            raise InputValidationError(
                f"origin_date mismatch on {method_name} at position {pos}",
                field="origin_date",
                reason=f"origin_date mismatch on {method_name} at position {pos}",
            )

        if type(raw_probs) is not tuple or len(raw_probs) != 3:
            raise InputValidationError(
                f"probabilities on {method_name} at position {pos} must be a native 3-tuple, got {type(raw_probs).__name__}",
                field="probabilities",
                reason=f"Invalid probabilities container type or length on {method_name} at position {pos}",
            )

        parsed_components: List[float] = []
        for c_idx, val in enumerate(raw_probs):
            if type(val) is not int and type(val) is not float or isinstance(val, bool):
                raise InputValidationError(
                    f"Probability component at index {c_idx} on {method_name} at position {pos} must be native int or float, got {type(val).__name__}",
                    field="probabilities",
                    reason=f"Invalid probability component type {type(val).__name__} on {method_name} at position {pos}",
                )
            if type(val) is int:
                if val not in (0, 1):
                    raise InputValidationError(
                        f"Integer probability component at index {c_idx} on {method_name} at position {pos} must be in [0, 1]",
                        field="probabilities",
                        reason=f"Integer probability component out of range [0, 1] on {method_name} at position {pos}",
                    )
                parsed_components.append(float(val))
            else:
                if not math.isfinite(val) or val < 0.0 or val > 1.0:
                    raise InputValidationError(
                        f"Float probability component at index {c_idx} on {method_name} at position {pos} must be finite in [0, 1]",
                        field="probabilities",
                        reason=f"Float probability component out of range [0, 1] on {method_name} at position {pos}",
                    )
                parsed_components.append(float(val))

        fsum_val = math.fsum(parsed_components)
        if abs(fsum_val - 1.0) > 1e-12:
            raise InputValidationError(
                f"Probabilities on {method_name} at position {pos} must sum to 1 within 1e-12",
                field="probabilities",
                reason=f"Probability sum deviates from 1.0 by {abs(fsum_val - 1.0)} on {method_name} at position {pos}",
            )

        validated_probs.append((parsed_components[0], parsed_components[1], parsed_components[2]))

    return tuple(validated_probs)


def _build_empty_model_metrics() -> ModelMetrics:
    """Constructs the canonical empty ModelMetrics structure for N=0."""
    zero_confusion: Tuple[Tuple[int, int, int], ...] = (
        (0, 0, 0),
        (0, 0, 0),
        (0, 0, 0),
    )
    recalls_none: Tuple[Optional[float], Optional[float], Optional[float]] = (
        None,
        None,
        None,
    )
    empty_bins: List[ReliabilityBin] = []
    for cls in CLASSES:
        for b in range(10):
            empty_bins.append(
                ReliabilityBin(
                    class_label=cls,
                    bin_index=b,
                    count=0,
                    mean_probability=None,
                    observed_frequency=None,
                )
            )

    return ModelMetrics(
        row_scores=(),
        mean_brier=None,
        mean_log_loss=None,
        log_loss_state=LOG_LOSS_STATE_EMPTY,
        zero_actual_probability_count=0,
        tie_count=0,
        accuracy=None,
        confusion=zero_confusion,
        class_recall=recalls_none,
        reliability_bins=tuple(empty_bins),
    )


def _compute_single_model_metrics(
    origins: Tuple[EvaluationOrigin, ...],
    probabilities: Tuple[Tuple[float, float, float], ...],
    class_support: Tuple[int, int, int],
) -> ModelMetrics:
    """Computes full evaluation metrics, losses, confusion, and reliability bins for one method."""
    n_samples = len(origins)
    if n_samples == 0:
        return _build_empty_model_metrics()

    row_scores: List[RowScore] = []
    tie_count = 0
    zero_actual_probability_count = 0
    confusion = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
    has_infinite_log = False

    # Bins collector: [class_idx][bin_idx] -> list of (prob, is_actual)
    bin_data: List[List[List[Tuple[float, bool]]]] = [
        [[] for _ in range(10)] for _ in range(3)
    ]

    for i in range(n_samples):
        orig = origins[i]
        probs = probabilities[i]
        actual_cls = orig.actual_class
        actual_idx = CLASSES.index(actual_cls)

        # 1. Predicted class and tie detection
        max_p = max(probs)
        max_count = sum(1 for p in probs if p == max_p)
        if max_count >= 2:
            tie_count += 1

        if probs[0] == max_p:
            predicted_cls = OUTCOME_CLASS_BEAR
            pred_idx = 0
        elif probs[1] == max_p:
            predicted_cls = OUTCOME_CLASS_NEUTRAL
            pred_idx = 1
        else:
            predicted_cls = OUTCOME_CLASS_BULL
            pred_idx = 2

        confusion[actual_idx][pred_idx] += 1

        # 2. Brier score: sum over all 3 classes of (p_k - onehot_k)^2
        brier = (
            (probs[0] - (1.0 if actual_idx == 0 else 0.0)) ** 2
            + (probs[1] - (1.0 if actual_idx == 1 else 0.0)) ** 2
            + (probs[2] - (1.0 if actual_idx == 2 else 0.0)) ** 2
        )

        # 3. Log loss: exact -math.log(p_actual)
        p_actual = probs[actual_idx]
        if p_actual == 0.0:
            row_log_loss = None
            row_log_state = LOG_LOSS_STATE_INFINITE
            zero_actual_probability_count += 1
            has_infinite_log = True
        else:
            row_log_loss = -math.log(p_actual)
            row_log_state = LOG_LOSS_STATE_FINITE

        row_scores.append(
            RowScore(
                origin=orig,
                probabilities=probs,
                predicted_class=predicted_cls,
                brier=brier,
                log_loss=row_log_loss,
                log_loss_state=row_log_state,
            )
        )

        # 4. Descriptive reliability data collection
        for k in range(3):
            p_k = probs[k]
            bin_idx = bisect.bisect_right(INTERIOR_EDGES, p_k)
            bin_data[k][bin_idx].append((p_k, actual_idx == k))

    # Aggregate metrics
    mean_brier = sum(r.brier for r in row_scores) / float(n_samples)

    if has_infinite_log:
        mean_log_loss = None
        model_log_state = LOG_LOSS_STATE_INFINITE
    else:
        mean_log_loss = sum(r.log_loss for r in row_scores) / float(n_samples)  # type: ignore[arg-type]
        model_log_state = LOG_LOSS_STATE_FINITE

    correct_total = confusion[0][0] + confusion[1][1] + confusion[2][2]
    accuracy = float(correct_total) / float(n_samples)

    recalls: List[Optional[float]] = []
    for k in range(3):
        support_k = class_support[k]
        if support_k == 0:
            recalls.append(None)
        else:
            recalls.append(float(confusion[k][k]) / float(support_k))

    confusion_tuple = (
        (confusion[0][0], confusion[0][1], confusion[0][2]),
        (confusion[1][0], confusion[1][1], confusion[1][2]),
        (confusion[2][0], confusion[2][1], confusion[2][2]),
    )

    # Construct descriptive reliability bins in class-major order
    reliability_bins: List[ReliabilityBin] = []
    for k in range(3):
        cls_name = CLASSES[k]
        for b in range(10):
            entries = bin_data[k][b]
            bin_count = len(entries)
            if bin_count == 0:
                mean_prob = None
                obs_freq = None
            else:
                mean_prob = sum(item[0] for item in entries) / float(bin_count)
                obs_freq = sum(1.0 for item in entries if item[1]) / float(bin_count)

            reliability_bins.append(
                ReliabilityBin(
                    class_label=cls_name,
                    bin_index=b,
                    count=bin_count,
                    mean_probability=mean_prob,
                    observed_frequency=obs_freq,
                )
            )

    return ModelMetrics(
        row_scores=tuple(row_scores),
        mean_brier=mean_brier,
        mean_log_loss=mean_log_loss,
        log_loss_state=model_log_state,
        zero_actual_probability_count=zero_actual_probability_count,
        tie_count=tie_count,
        accuracy=accuracy,
        confusion=confusion_tuple,
        class_recall=(recalls[0], recalls[1], recalls[2]),
        reliability_bins=tuple(reliability_bins),
    )


def score_comparison(
    origins: Sequence[Any],
    *,
    heuristic: Sequence[Any],
    frequency: Sequence[Any],
    logistic: Sequence[Any],
) -> ComparisonMetrics:
    """
    Computes three-class evaluation metrics across a shared chronological origin cohort.

    Parameters:
        origins: Native list or tuple of EvaluationOrigin objects (or structural equivalents).
        heuristic: Native list or tuple of PredictionLike objects from the heuristic model.
        frequency: Native list or tuple of PredictionLike objects from the frequency baseline.
        logistic: Native list or tuple of PredictionLike objects from the logistic comparator.

    Returns:
        ComparisonMetrics exposing protocol identity, shared cohort metadata, and
        individual ModelMetrics for all three methods.

    Raises:
        InputValidationError: On invalid container types, missing or out-of-order origins,
                              non-strictly increasing indices/dates, cohort misalignment,
                              invalid probabilities, or probability sum divergence.
    """
    # 1. Container type validation
    if type(origins) not in (list, tuple):
        raise InputValidationError(
            f"origins must be a native list or tuple, got {type(origins).__name__}",
            field="origins",
            reason=f"Unsupported container type {type(origins).__name__} for origins",
        )

    method_containers = (
        ("heuristic", heuristic),
        ("frequency", frequency),
        ("logistic", logistic),
    )
    for name, container in method_containers:
        if type(container) not in (list, tuple):
            raise InputValidationError(
                f"{name} predictions must be a native list or tuple, got {type(container).__name__}",
                field=name,
                reason=f"Unsupported container type {type(container).__name__} for {name}",
            )

    # 2. Origins cohort validation
    n_samples = len(origins)
    validated_origins: List[EvaluationOrigin] = []
    prev_index: Optional[int] = None
    prev_date: Optional[datetime.date] = None

    for pos, orig in enumerate(origins):
        try:
            idx = orig.origin_index
            dt = orig.origin_date
            cls = orig.actual_class
        except AttributeError as exc:
            raise InputValidationError(
                f"Missing required attribute on origin at position {pos}: {exc}",
                field="origins",
                reason=f"Missing required attribute on origin at position {pos}",
            ) from exc

        if type(idx) is not int or isinstance(idx, bool) or idx < 0:
            raise InputValidationError(
                f"origin_index at position {pos} must be a non-negative native int, got {type(idx).__name__}",
                field="origin_index",
                reason=f"Invalid origin_index at position {pos}",
            )

        if type(dt) is not datetime.date or isinstance(dt, datetime.datetime):
            raise InputValidationError(
                f"origin_date at position {pos} must be exact datetime.date, got {type(dt).__name__}",
                field="origin_date",
                reason=f"Invalid origin_date type at position {pos}",
            )

        if type(cls) is not str:
            raise InputValidationError(
                f"actual_class at position {pos} must be a native str in {CLASSES}, got {type(cls).__name__}",
                field="actual_class",
                reason=f"Invalid actual_class type {type(cls).__name__} at position {pos}",
            )
        if cls not in CLASSES:
            safe_cls = cls[:32] if len(cls) <= 32 else (cls[:29] + "...")
            raise InputValidationError(
                f"actual_class at position {pos} must be one of {CLASSES}, got {safe_cls!r}",
                field="actual_class",
                reason=f"Unrecognized actual_class at position {pos}",
            )

        if prev_index is not None and idx <= prev_index:
            raise InputValidationError(
                f"origin_index must strictly increase; non-increasing index at position {pos}",
                field="origin_index",
                reason=f"Non-increasing origin_index at position {pos}",
            )

        if prev_date is not None and dt <= prev_date:
            raise InputValidationError(
                f"origin_date must strictly increase; non-increasing date at position {pos}",
                field="origin_date",
                reason=f"Non-increasing origin_date at position {pos}",
            )

        prev_index = idx
        prev_date = dt

        # Always construct an owned plain EvaluationOrigin instance with validated scalars
        validated_origins.append(
            EvaluationOrigin(origin_index=idx, origin_date=dt, actual_class=cls)
        )

    origins_tuple = tuple(validated_origins)

    # 3. Model prediction validations
    heuristic_probs = _validate_method_predictions(heuristic, origins_tuple, "heuristic")
    frequency_probs = _validate_method_predictions(frequency, origins_tuple, "frequency")
    logistic_probs = _validate_method_predictions(logistic, origins_tuple, "logistic")

    # 4. Class support calculation
    bear_count = sum(1 for o in origins_tuple if o.actual_class == OUTCOME_CLASS_BEAR)
    neutral_count = sum(1 for o in origins_tuple if o.actual_class == OUTCOME_CLASS_NEUTRAL)
    bull_count = sum(1 for o in origins_tuple if o.actual_class == OUTCOME_CLASS_BULL)
    class_support = (bear_count, neutral_count, bull_count)

    # 5. Compute metrics for all three models
    heuristic_metrics = _compute_single_model_metrics(origins_tuple, heuristic_probs, class_support)
    frequency_metrics = _compute_single_model_metrics(origins_tuple, frequency_probs, class_support)
    logistic_metrics = _compute_single_model_metrics(origins_tuple, logistic_probs, class_support)

    status = STATUS_SCORED if n_samples > 0 else STATUS_EMPTY

    return ComparisonMetrics(
        protocol_id=PROTOCOL_ID,
        classes=CLASSES,
        bin_edges=BIN_EDGES,
        origins=origins_tuple,
        sample_count=n_samples,
        class_support=class_support,
        status=status,
        heuristic=heuristic_metrics,
        frequency=frequency_metrics,
        logistic=logistic_metrics,
    )


__all__ = [
    "BIN_EDGES",
    "CLASSES",
    "ComparisonMetrics",
    "EvaluationOrigin",
    "INTERIOR_EDGES",
    "LOG_LOSS_STATE_EMPTY",
    "LOG_LOSS_STATE_FINITE",
    "LOG_LOSS_STATE_INFINITE",
    "ModelMetrics",
    "PredictionLike",
    "PROTOCOL_ID",
    "ReliabilityBin",
    "RowScore",
    "STATUS_EMPTY",
    "STATUS_SCORED",
    "score_comparison",
]
