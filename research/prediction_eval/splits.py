"""
Prediction Evaluation Chronological Splits Foundation.

Provides deterministic, inspectable, chronological evaluation split planning,
common date alignment, strict-before maturity-safe label purges, and separate
final-refit pool tracking for Nifty 50 feature and twenty-session outcome series.

Architectural ownership:
    inputs.py owns raw CSV parsing, validation, provenance, and exact-date alignment.
    outcomes.py owns future-label timing and exact-band classification (+/-0.5%).
    features.py owns origin-time causal feature construction and regime classification.
    splits.py owns evaluation split planning, common date alignment, maturity-safe
    boundary purging, and separate final-refit pool tracking.

Temporal and eligibility policy:
    1. Origin axis alignment: Features and outcomes must share identical, strictly
       increasing origin dates, matching origin indices, and numerical Close agreement.
    2. Calendar agreement: Features calendar_status must be 'matches_supplied_sessions'
       with zero discrepancies; this validates agreement with a caller-supplied calendar,
       not authentic exchange-schedule certification.
    3. Strict-before boundary purges:
       - Train partition (i < D): requires maturity_index < D; otherwise
         'label_crosses_development_boundary'.
       - Development partition (D <= i < T): requires maturity_index < T; otherwise
         'label_crosses_test_boundary'.
       - Test partition (i >= T): retains all base-eligible origins; unmatured tail
         remains excluded as 'unknown_outcome'.
    4. Separate final refit pool: All base-eligible origins i < T with maturity_index < T,
       drawn from both earlier partitions. Origins purged at the development boundary
       may re-enter refit if mature before test start.
    5. Pure standard-library in-memory function: Zero file I/O, network calls, random state,
       fitting, scoring, or model training.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Optional, Set, Tuple
from dataclasses import dataclass

from research.prediction_eval.inputs import InputValidationError
from research.prediction_eval.features import (
    FeatureSeries,
    NiftyFeatureRecord,
    PredictorPayload,
    PROTOCOL_ID,
    WARMUP_ORIGIN_INDEX,
    REASON_WARMUP,
    REASON_MISSING_VIX,
)
from research.prediction_eval.outcomes import (
    OutcomeSeries,
    TwentySessionOutcome,
    HORIZON_SESSIONS,
    VALID_OUTCOME_CLASSES,
    STATUS_MATURE,
    STATUS_UNKNOWN,
)

PARTITION_TRAIN: str = "train"
PARTITION_DEVELOPMENT: str = "development"
PARTITION_TEST: str = "test"
VALID_PARTITIONS: Set[str] = {
    PARTITION_TRAIN,
    PARTITION_DEVELOPMENT,
    PARTITION_TEST,
}

REASON_UNKNOWN_OUTCOME: str = "unknown_outcome"
REASON_LABEL_CROSSES_DEVELOPMENT: str = "label_crosses_development_boundary"
REASON_LABEL_CROSSES_TEST: str = "label_crosses_test_boundary"


@dataclass(frozen=True)
class OriginSplitDecision:
    """
    Inspectable split decision for a single input origin observation.

    Attributes:
        origin_index: Positional index on the original supplied Nifty axis.
        origin_date: Exact calendar date of the origin observation.
        partition: Raw chronological partition ('train', 'development', or 'test').
        exclusion_reasons: Deterministic tuple of exclusion reasons for this partition.
            Empty tuple indicates the origin is retained in its partition.
        in_refit: True if the origin is eligible for the separate final-refit pool.
    """

    origin_index: int
    origin_date: datetime.date
    partition: str
    exclusion_reasons: Tuple[str, ...]
    in_refit: bool

    def __post_init__(self) -> None:
        if type(self.origin_index) is not int or self.origin_index < 0:
            raise ValueError(f"origin_index must be a non-negative int, got {self.origin_index!r}")
        if type(self.origin_date) is not datetime.date:
            raise ValueError(f"origin_date must be datetime.date, got {type(self.origin_date).__name__}")
        if self.partition not in VALID_PARTITIONS:
            raise ValueError(f"Invalid partition '{self.partition}'; expected one of {sorted(VALID_PARTITIONS)}")
        if type(self.exclusion_reasons) is not tuple:
            raise ValueError(f"exclusion_reasons must be a tuple, got {type(self.exclusion_reasons).__name__}")
        if type(self.in_refit) is not bool:
            raise ValueError(f"in_refit must be a bool, got {type(self.in_refit).__name__}")


@dataclass(frozen=True)
class SplitPlan:
    """
    Immutable chronological evaluation split plan across all input origins.

    Exposes raw-axis cutoffs, disjoint retained index pools, the final refit pool,
    and an origin-retained decision for every observation in the original sequence.
    """

    development_start: datetime.date
    test_start: datetime.date
    development_start_index: int
    test_start_index: int
    train_indices: Tuple[int, ...]
    development_indices: Tuple[int, ...]
    refit_indices: Tuple[int, ...]
    test_indices: Tuple[int, ...]
    decisions: Tuple[OriginSplitDecision, ...]

    @property
    def development_index(self) -> int:
        """Alias for development_start_index."""
        return self.development_start_index

    @property
    def test_index(self) -> int:
        """Alias for test_start_index."""
        return self.test_start_index

    def __len__(self) -> int:
        return len(self.decisions)

    def __iter__(self):
        return iter(self.decisions)

    def __getitem__(self, index: int) -> OriginSplitDecision:
        return self.decisions[index]


def build_split_plan(
    features: FeatureSeries,
    outcomes: OutcomeSeries,
    *,
    development_start: datetime.date,
    test_start: datetime.date,
) -> SplitPlan:
    """
    Plans chronological evaluation partitions on common-date feature and outcome series.

    Parameters:
        features: FeatureSeries computed by compute_nifty_features.
        outcomes: OutcomeSeries computed by compute_twenty_session_outcomes.
        development_start: Date marking the start of the development block (exclusive train end).
        test_start: Date marking the start of the test block (exclusive development end).

    Returns:
        SplitPlan containing raw cutoffs, retained index pools, and origin decisions.

    Raises:
        InputValidationError: On missing/invalid series, mismatched axes, calendar discrepancies,
                              invalid or unobserved boundary dates, or contradictory metadata.
    """
    # 1. Type validation of primary series containers
    if not isinstance(features, FeatureSeries):
        raise InputValidationError(
            f"Expected FeatureSeries instance, got {type(features).__name__}",
            field="features",
            reason=f"features must be a FeatureSeries instance, got {type(features).__name__}",
        )

    if not isinstance(outcomes, OutcomeSeries):
        raise InputValidationError(
            f"Expected OutcomeSeries instance, got {type(outcomes).__name__}",
            field="outcomes",
            reason=f"outcomes must be an OutcomeSeries instance, got {type(outcomes).__name__}",
        )

    # 2. Protocol and series role validation
    if features.protocol_id != PROTOCOL_ID:
        raise InputValidationError(
            f"Invalid protocol_id '{features.protocol_id}'; expected '{PROTOCOL_ID}'",
            field="protocol_id",
            reason=f"Protocol ID mismatch: expected '{PROTOCOL_ID}', got '{features.protocol_id}'",
        )

    if outcomes.series_id != "nifty50_price_index":
        raise InputValidationError(
            f"Invalid series_id '{outcomes.series_id}'; expected 'nifty50_price_index'",
            field="series_id",
            reason=f"Series ID mismatch: expected 'nifty50_price_index', got '{outcomes.series_id}'",
        )

    # 3. Tuple container validation
    if type(features.records) is not tuple:
        raise InputValidationError(
            f"features.records must be a tuple, got {type(features.records).__name__}",
            field="records",
            reason=f"features.records must be a tuple, got {type(features.records).__name__}",
        )

    if type(outcomes.outcomes) is not tuple:
        raise InputValidationError(
            f"outcomes.outcomes must be a tuple, got {type(outcomes.outcomes).__name__}",
            field="outcomes",
            reason=f"outcomes.outcomes must be a tuple, got {type(outcomes.outcomes).__name__}",
        )

    # 4. Series length matching (no zip truncation or repair)
    n_features = len(features.records)
    n_outcomes = len(outcomes.outcomes)
    if n_features != n_outcomes:
        raise InputValidationError(
            f"Mismatched series lengths: features has {n_features} records, outcomes has {n_outcomes}",
            field="records",
            reason=f"Length mismatch: features={n_features}, outcomes={n_outcomes}",
        )

    # 5. Axis start date verification for empty series
    if n_features == 0:
        if features.axis_start_date is not None:
            raise InputValidationError(
                f"axis_start_date must be None for empty series, got {features.axis_start_date}",
                field="axis_start_date",
                reason="Empty features series must have axis_start_date=None",
            )

    # 6. Calendar prerequisite verification
    if features.calendar_status != "matches_supplied_sessions":
        raise InputValidationError(
            f"Calendar prerequisite failed: calendar_status must be 'matches_supplied_sessions', got '{features.calendar_status}'",
            field="calendar_status",
            reason=f"calendar_status is '{features.calendar_status}'",
        )

    if type(features.missing_sessions) is not tuple or len(features.missing_sessions) > 0:
        raise InputValidationError(
            f"missing_sessions must be an empty tuple, got {features.missing_sessions!r}",
            field="missing_sessions",
            reason="missing_sessions is not empty",
        )

    if type(features.extra_sessions) is not tuple or len(features.extra_sessions) > 0:
        raise InputValidationError(
            f"extra_sessions must be an empty tuple, got {features.extra_sessions!r}",
            field="extra_sessions",
            reason="extra_sessions is not empty",
        )

    # 7. Boundary arguments type verification (real datetime.date, not datetime.datetime)
    if type(development_start) is not datetime.date:
        raise InputValidationError(
            f"development_start must be datetime.date (not datetime), got {type(development_start).__name__}",
            field="development_start",
            reason=f"development_start is {type(development_start).__name__}",
        )

    if type(test_start) is not datetime.date:
        raise InputValidationError(
            f"test_start must be datetime.date (not datetime), got {type(test_start).__name__}",
            field="test_start",
            reason=f"test_start is {type(test_start).__name__}",
        )

    # 8. Boundary selection on empty series
    if n_features == 0:
        raise InputValidationError(
            "Cannot plan splits on an empty series: boundary dates cannot be matched",
            field="development_start",
            reason="Series is empty",
        )

    # 9. Complete original axis audit: structural integrity across every origin
    prev_date: Optional[datetime.date] = None
    for i in range(n_features):
        f_rec = features.records[i]
        o_rec = outcomes.outcomes[i]

        if not isinstance(f_rec, NiftyFeatureRecord):
            raise InputValidationError(
                f"features.records[{i}] must be NiftyFeatureRecord, got {type(f_rec).__name__}",
                field="records",
                reason=f"Invalid record type at index {i}",
            )

        if not isinstance(o_rec, TwentySessionOutcome):
            raise InputValidationError(
                f"outcomes.outcomes[{i}] must be TwentySessionOutcome, got {type(o_rec).__name__}",
                field="outcomes",
                reason=f"Invalid outcome type at index {i}",
            )

        # Index verification: true integer equal to position
        if type(f_rec.origin_index) is not int or f_rec.origin_index != i:
            raise InputValidationError(
                f"features origin_index at position {i} is {f_rec.origin_index!r}; expected {i}",
                field="origin_index",
                reason=f"features origin_index mismatch at position {i}",
            )

        if type(o_rec.origin_index) is not int or o_rec.origin_index != i:
            raise InputValidationError(
                f"outcomes origin_index at position {i} is {o_rec.origin_index!r}; expected {i}",
                field="origin_index",
                reason=f"outcomes origin_index mismatch at position {i}",
            )

        # Date verification: real date, equal, strictly increasing
        if type(f_rec.origin_date) is not datetime.date:
            raise InputValidationError(
                f"features origin_date at index {i} must be datetime.date, got {type(f_rec.origin_date).__name__}",
                field="origin_date",
                reason=f"features origin_date is {type(f_rec.origin_date).__name__} at index {i}",
            )

        if type(o_rec.origin_date) is not datetime.date:
            raise InputValidationError(
                f"outcomes origin_date at index {i} must be datetime.date, got {type(o_rec.origin_date).__name__}",
                field="origin_date",
                reason=f"outcomes origin_date is {type(o_rec.origin_date).__name__} at index {i}",
            )

        if f_rec.origin_date != o_rec.origin_date:
            raise InputValidationError(
                f"Origin date mismatch at index {i}: features has {f_rec.origin_date}, outcomes has {o_rec.origin_date}",
                field="origin_date",
                reason=f"Origin date mismatch: {f_rec.origin_date} != {o_rec.origin_date} at index {i}",
            )

        if prev_date is not None and f_rec.origin_date <= prev_date:
            raise InputValidationError(
                f"Origin dates must be strictly increasing and unique; found {f_rec.origin_date} <= {prev_date} at index {i}",
                field="origin_date",
                reason=f"Non-increasing or duplicate date {f_rec.origin_date} at index {i}",
            )
        prev_date = f_rec.origin_date

        # Origin Close verification: positive finite Decimal, numerical agreement
        if not isinstance(f_rec.origin_close, Decimal) or not f_rec.origin_close.is_finite() or f_rec.origin_close <= 0:
            raise InputValidationError(
                f"features origin_close at index {i} ({f_rec.origin_date}) must be positive finite Decimal, got {f_rec.origin_close!r}",
                field="origin_close",
                reason=f"Invalid features origin_close at index {i}",
            )

        if not isinstance(o_rec.origin_close, Decimal) or not o_rec.origin_close.is_finite() or o_rec.origin_close <= 0:
            raise InputValidationError(
                f"outcomes origin_close at index {i} ({o_rec.origin_date}) must be positive finite Decimal, got {o_rec.origin_close!r}",
                field="origin_close",
                reason=f"Invalid outcomes origin_close at index {i}",
            )

        if f_rec.origin_close != o_rec.origin_close:
            raise InputValidationError(
                f"Origin close mismatch at index {i} ({f_rec.origin_date}): features has {f_rec.origin_close}, outcomes has {o_rec.origin_close}",
                field="origin_close",
                reason=f"Origin close mismatch: {f_rec.origin_close} != {o_rec.origin_close} at index {i}",
            )

        # Feature readiness metadata verification
        if type(f_rec.feature_ready) is not bool:
            raise InputValidationError(
                f"feature_ready at index {i} must be bool, got {type(f_rec.feature_ready).__name__}",
                field="feature_ready",
                reason=f"feature_ready is {type(f_rec.feature_ready).__name__} at index {i}",
            )

        if f_rec.vix_close is not None:
            if not isinstance(f_rec.vix_close, Decimal) or not f_rec.vix_close.is_finite() or f_rec.vix_close <= 0:
                raise InputValidationError(
                    f"vix_close at index {i} ({f_rec.origin_date}) must be positive finite Decimal when present, got {f_rec.vix_close!r}",
                    field="vix_close",
                    reason=f"Invalid vix_close at index {i}",
                )

        expected_warmup = (i < WARMUP_ORIGIN_INDEX)
        expected_missing_vix = (f_rec.vix_close is None)
        if expected_warmup and expected_missing_vix:
            expected_reasons = (REASON_WARMUP, REASON_MISSING_VIX)
        elif expected_warmup:
            expected_reasons = (REASON_WARMUP,)
        elif expected_missing_vix:
            expected_reasons = (REASON_MISSING_VIX,)
        else:
            expected_reasons = ()

        if type(f_rec.unready_reasons) is not tuple or f_rec.unready_reasons != expected_reasons:
            raise InputValidationError(
                f"unready_reasons mismatch at index {i} ({f_rec.origin_date}): expected {expected_reasons}, got {f_rec.unready_reasons}",
                field="unready_reasons",
                reason=f"unready_reasons mismatch at index {i}",
            )

        if f_rec.feature_ready != (len(expected_reasons) == 0):
            raise InputValidationError(
                f"Contradictory feature_ready at index {i} ({f_rec.origin_date}): feature_ready={f_rec.feature_ready} but reasons={f_rec.unready_reasons}",
                field="feature_ready",
                reason=f"feature_ready inconsistency at index {i}",
            )

        if f_rec.feature_ready:
            if not isinstance(f_rec.payload, PredictorPayload):
                raise InputValidationError(
                    f"Feature-ready record at index {i} ({f_rec.origin_date}) must have PredictorPayload, got {type(f_rec.payload).__name__}",
                    field="payload",
                    reason=f"Missing PredictorPayload at ready index {i}",
                )
        else:
            if f_rec.payload is not None:
                raise InputValidationError(
                    f"Unready record at index {i} ({f_rec.origin_date}) must have payload=None, got {type(f_rec.payload).__name__}",
                    field="payload",
                    reason=f"Non-None payload at unready index {i}",
                )

        # Outcome maturity verification
        if type(o_rec.is_mature) is not bool:
            raise InputValidationError(
                f"is_mature at index {i} must be bool, got {type(o_rec.is_mature).__name__}",
                field="is_mature",
                reason=f"is_mature is {type(o_rec.is_mature).__name__} at index {i}",
            )

        future_idx = i + HORIZON_SESSIONS
        if future_idx < n_features:
            if o_rec.status != STATUS_MATURE or not o_rec.is_mature:
                raise InputValidationError(
                    f"Expected mature outcome at index {i} ({o_rec.origin_date}), got status='{o_rec.status}' and is_mature={o_rec.is_mature}",
                    field="status",
                    reason=f"Outcome must be mature at index {i}",
                )
            if type(o_rec.maturity_index) is not int or o_rec.maturity_index != future_idx:
                raise InputValidationError(
                    f"maturity_index mismatch at index {i}: expected {future_idx}, got {o_rec.maturity_index!r}",
                    field="maturity_index",
                    reason=f"maturity_index mismatch at index {i}",
                )
            if type(o_rec.maturity_date) is not datetime.date:
                raise InputValidationError(
                    f"maturity_date at index {i} must be datetime.date (not datetime), got {type(o_rec.maturity_date).__name__}",
                    field="maturity_date",
                    reason=f"Invalid maturity_date type at index {i}",
                )
            if not isinstance(o_rec.maturity_close, Decimal) or not o_rec.maturity_close.is_finite() or o_rec.maturity_close <= 0:
                raise InputValidationError(
                    f"maturity_close at index {i} must be positive finite Decimal, got {o_rec.maturity_close!r}",
                    field="maturity_close",
                    reason=f"Invalid maturity_close at index {i}",
                )
            if type(o_rec.outcome_class) is not str or o_rec.outcome_class not in VALID_OUTCOME_CLASSES:
                raise InputValidationError(
                    f"Invalid outcome_class '{o_rec.outcome_class}' at index {i}; expected one of {sorted(VALID_OUTCOME_CLASSES)}",
                    field="outcome_class",
                    reason=f"Invalid outcome_class '{o_rec.outcome_class}' at index {i}",
                )
        else:
            if o_rec.status != STATUS_UNKNOWN or o_rec.is_mature:
                raise InputValidationError(
                    f"Expected unknown outcome tail at index {i} ({o_rec.origin_date}), got status='{o_rec.status}' and is_mature={o_rec.is_mature}",
                    field="status",
                    reason=f"Outcome must be unknown at index {i}",
                )
            if o_rec.maturity_index is not None:
                raise InputValidationError(
                    f"Unmatured outcome at index {i} cannot have maturity_index, got {o_rec.maturity_index}",
                    field="maturity_index",
                    reason=f"Unmatured outcome has maturity_index at index {i}",
                )
            if o_rec.maturity_date is not None:
                raise InputValidationError(
                    f"Unmatured outcome at index {i} cannot have maturity_date, got {o_rec.maturity_date}",
                    field="maturity_date",
                    reason=f"Unmatured outcome has maturity_date at index {i}",
                )
            if o_rec.maturity_close is not None:
                raise InputValidationError(
                    f"Unmatured outcome at index {i} cannot have maturity_close, got {o_rec.maturity_close}",
                    field="maturity_close",
                    reason=f"Unmatured outcome has maturity_close at index {i}",
                )
            if o_rec.outcome_class is not None:
                raise InputValidationError(
                    f"Unmatured outcome at index {i} cannot have outcome_class, got '{o_rec.outcome_class}'",
                    field="outcome_class",
                    reason=f"Unmatured outcome has outcome_class at index {i}",
                )

    # 10. Axis start date verification (executed after Pass 1 guarantees records[0] is valid)
    first_date = features.records[0].origin_date
    if features.axis_start_date != first_date:
        raise InputValidationError(
            f"axis_start_date {features.axis_start_date} does not match first record date {first_date}",
            field="axis_start_date",
            reason=f"axis_start_date mismatch: {features.axis_start_date} != {first_date}",
        )

    # 11. Pass 2: Cross-record endpoint consistency audit
    # Every feature record 0..n_features-1 is proven structurally valid in Pass 1.
    for i in range(n_features):
        future_idx = i + HORIZON_SESSIONS
        if future_idx < n_features:
            endpoint_f = features.records[future_idx]
            o_rec = outcomes.outcomes[i]
            if o_rec.maturity_date != endpoint_f.origin_date:
                raise InputValidationError(
                    f"maturity_date mismatch at index {i}: expected {endpoint_f.origin_date}, got {o_rec.maturity_date}",
                    field="maturity_date",
                    reason=f"maturity_date mismatch at index {i}",
                )
            if o_rec.maturity_close != endpoint_f.origin_close:
                raise InputValidationError(
                    f"maturity_close mismatch at index {i}: expected {endpoint_f.origin_close}, got {o_rec.maturity_close}",
                    field="maturity_close",
                    reason=f"maturity_close mismatch at index {i}",
                )

    # 12. Boundary lookup and validation on the verified axis
    date_to_index = {features.records[idx].origin_date: idx for idx in range(n_features)}
    if development_start not in date_to_index:
        raise InputValidationError(
            f"development_start date {development_start} not found on origin axis",
            field="development_start",
            reason=f"development_start date {development_start} not present on axis",
        )

    if test_start not in date_to_index:
        raise InputValidationError(
            f"test_start date {test_start} not found on origin axis",
            field="test_start",
            reason=f"test_start date {test_start} not present on axis",
        )

    d_idx = date_to_index[development_start]
    t_idx = date_to_index[test_start]

    # Require 0 < D < T < N so every raw partition is nonempty
    if d_idx <= 0:
        raise InputValidationError(
            f"development_start index {d_idx} must be > 0 so that train partition is non-empty",
            field="development_start",
            reason=f"development_start index {d_idx} <= 0",
        )

    if d_idx >= t_idx:
        raise InputValidationError(
            f"development_start index {d_idx} ({development_start}) must be strictly less than test_start index {t_idx} ({test_start})",
            field="development_start",
            reason=f"development_start index {d_idx} >= test_start index {t_idx}",
        )

    if t_idx >= n_features:
        raise InputValidationError(
            f"test_start index {t_idx} must be strictly less than series length {n_features}",
            field="test_start",
            reason=f"test_start index {t_idx} >= {n_features}",
        )

    # 11. Selection and temporal policy pass
    train_indices = []
    dev_indices = []
    test_indices = []
    refit_indices = []
    decisions = []

    for i in range(n_features):
        f_rec = features.records[i]
        o_rec = outcomes.outcomes[i]

        # Raw partition assignment based on original axis position
        if i < d_idx:
            partition = PARTITION_TRAIN
        elif i < t_idx:
            partition = PARTITION_DEVELOPMENT
        else:
            partition = PARTITION_TEST

        # Base eligibility: feature-ready AND mature outcome
        base_reasons = []
        if i < WARMUP_ORIGIN_INDEX:
            base_reasons.append(REASON_WARMUP)
        if f_rec.vix_close is None:
            base_reasons.append(REASON_MISSING_VIX)
        if not o_rec.is_mature:
            base_reasons.append(REASON_UNKNOWN_OUTCOME)

        base_eligible = (len(base_reasons) == 0)

        # Partition purge reasons (only applied to base-eligible rows)
        purge_reasons = []
        if base_eligible:
            if partition == PARTITION_TRAIN:
                # Retain only if label matures strictly before development start
                if not (o_rec.maturity_index is not None and o_rec.maturity_index < d_idx):
                    purge_reasons.append(REASON_LABEL_CROSSES_DEVELOPMENT)
            elif partition == PARTITION_DEVELOPMENT:
                # Retain only if label matures strictly before test start
                if not (o_rec.maturity_index is not None and o_rec.maturity_index < t_idx):
                    purge_reasons.append(REASON_LABEL_CROSSES_TEST)
            # Test partition retains all base-eligible rows

        exclusion_reasons = tuple(base_reasons if not base_eligible else purge_reasons)

        # Final refit membership:
        # Separate fitting pool containing all base-eligible rows i < T with maturity_index < T,
        # drawn from both train and development raw partitions.
        in_refit = bool(
            base_eligible
            and (i < t_idx)
            and (o_rec.maturity_index is not None and o_rec.maturity_index < t_idx)
        )

        decision = OriginSplitDecision(
            origin_index=i,
            origin_date=f_rec.origin_date,
            partition=partition,
            exclusion_reasons=exclusion_reasons,
            in_refit=in_refit,
        )
        decisions.append(decision)

        if len(exclusion_reasons) == 0:
            if partition == PARTITION_TRAIN:
                train_indices.append(i)
            elif partition == PARTITION_DEVELOPMENT:
                dev_indices.append(i)
            else:
                test_indices.append(i)

        if in_refit:
            refit_indices.append(i)

    return SplitPlan(
        development_start=development_start,
        test_start=test_start,
        development_start_index=d_idx,
        test_start_index=t_idx,
        train_indices=tuple(train_indices),
        development_indices=tuple(dev_indices),
        refit_indices=tuple(refit_indices),
        test_indices=tuple(test_indices),
        decisions=tuple(decisions),
    )
