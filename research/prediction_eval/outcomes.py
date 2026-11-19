"""
Prediction Evaluation Outcomes Foundation.

Provides inspectable twenty-session forward price outcomes and exact movement
classification (+/-0.5% band) for chronological Nifty 50 price-index series.

Architectural ownership:
    inputs.py owns raw CSV parsing, validation, provenance, and chronological sorting.
    outcomes.py owns future-label timing and exact-band classification for downstream
    prediction evaluation and training labels.

Future data boundary:
    Outcomes represent realized future observations available only after the 20-session
    horizon has elapsed. This module does not perform as-of feature admission, train/test
    splits, purging, embargoing, eligibility filtering, or predictive modeling.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from fractions import Fraction
from typing import List, Optional, Set, Tuple
from dataclasses import dataclass

from research.prediction_eval.inputs import (
    InputValidationError,
    LoadedSeries,
    PriceRecord,
)

HORIZON_SESSIONS: int = 20

OUTCOME_CLASS_BULL: str = "BULL"
OUTCOME_CLASS_BEAR: str = "BEAR"
OUTCOME_CLASS_NEUTRAL: str = "NEUTRAL"
VALID_OUTCOME_CLASSES: Set[str] = {
    OUTCOME_CLASS_BULL,
    OUTCOME_CLASS_BEAR,
    OUTCOME_CLASS_NEUTRAL,
}

STATUS_MATURE: str = "mature"
STATUS_UNKNOWN: str = "unknown"
VALID_STATUSES: Set[str] = {STATUS_MATURE, STATUS_UNKNOWN}


@dataclass(frozen=True)
class TwentySessionOutcome:
    """
    Inspectable twenty-session outcome for a single Nifty 50 origin observation.

    Retains the origin position index, date, and Close price from the input series.
    If an observed session exists exactly twenty positions ahead (origin_index + 20),
    the record exposes that actual maturity index, date, Close price, and directional
    movement class ('BULL', 'BEAR', or 'NEUTRAL') with status='mature' and is_mature=True.

    If the maturity session falls beyond the end of the series, all maturity fields
    are None, outcome_class is None, is_mature is False, and status='unknown'.
    No hypothetical dates, estimated prices, or directional classes are ever fabricated.
    """

    origin_index: int
    origin_date: datetime.date
    origin_close: Decimal
    is_mature: bool
    status: str
    maturity_index: Optional[int] = None
    maturity_date: Optional[datetime.date] = None
    maturity_close: Optional[Decimal] = None
    outcome_class: Optional[str] = None

    def __post_init__(self) -> None:
        """Enforces invariant consistency between maturity state and outcome fields."""
        if self.is_mature:
            if self.status != STATUS_MATURE:
                raise ValueError(
                    f"Contradictory outcome state: is_mature=True but status='{self.status}'; "
                    f"expected status='{STATUS_MATURE}'."
                )
            if self.maturity_index is None:
                raise ValueError("Mature outcome must specify maturity_index.")
            if self.maturity_index != self.origin_index + HORIZON_SESSIONS:
                raise ValueError(
                    f"Invalid maturity_index {self.maturity_index}; expected "
                    f"origin_index + {HORIZON_SESSIONS} ({self.origin_index + HORIZON_SESSIONS})."
                )
            if self.maturity_date is None:
                raise ValueError("Mature outcome must specify maturity_date.")
            if self.maturity_date < self.origin_date:
                raise ValueError(
                    f"Maturity date {self.maturity_date} cannot precede origin date {self.origin_date}."
                )
            if self.maturity_close is None:
                raise ValueError("Mature outcome must specify maturity_close.")
            if self.maturity_close <= 0:
                raise ValueError(f"Maturity close {self.maturity_close} must be strictly positive.")
            if self.outcome_class not in VALID_OUTCOME_CLASSES:
                raise ValueError(
                    f"Invalid outcome_class '{self.outcome_class}'; expected one of {sorted(VALID_OUTCOME_CLASSES)}."
                )
        else:
            if self.status != STATUS_UNKNOWN:
                raise ValueError(
                    f"Contradictory outcome state: is_mature=False but status='{self.status}'; "
                    f"expected status='{STATUS_UNKNOWN}'."
                )
            if self.maturity_index is not None:
                raise ValueError(
                    f"Unmatured outcome cannot have maturity_index (got {self.maturity_index})."
                )
            if self.maturity_date is not None:
                raise ValueError(
                    f"Unmatured outcome cannot have maturity_date (got {self.maturity_date})."
                )
            if self.maturity_close is not None:
                raise ValueError(
                    f"Unmatured outcome cannot have maturity_close (got {self.maturity_close})."
                )
            if self.outcome_class is not None:
                raise ValueError(
                    f"Unmatured outcome cannot have outcome_class (got '{self.outcome_class}')."
                )


@dataclass(frozen=True)
class OutcomeSeries:
    """
    Immutable chronological sequence of twenty-session outcomes for a Nifty price series.

    Encapsulates origin-retained outcomes, counts of mature and unknown tails,
    and provides sequence access without mutating or re-evaluating records.
    """

    series_id: str
    outcomes: Tuple[TwentySessionOutcome, ...]

    def __len__(self) -> int:
        return len(self.outcomes)

    def __iter__(self):
        return iter(self.outcomes)

    def __getitem__(self, index: int) -> TwentySessionOutcome:
        return self.outcomes[index]

    @property
    def total_origins(self) -> int:
        """Total number of origin observations in the series."""
        return len(self.outcomes)

    @property
    def mature_count(self) -> int:
        """Number of origins with observed twenty-session maturities."""
        return sum(1 for o in self.outcomes if o.is_mature)

    @property
    def unknown_count(self) -> int:
        """Number of origins with unobserved/unknown maturities (final tail)."""
        return sum(1 for o in self.outcomes if not o.is_mature)

    @property
    def mature_outcomes(self) -> Tuple[TwentySessionOutcome, ...]:
        """Subset of mature outcome records."""
        return tuple(o for o in self.outcomes if o.is_mature)

    @property
    def unknown_outcomes(self) -> Tuple[TwentySessionOutcome, ...]:
        """Subset of unknown / unmatured outcome records."""
        return tuple(o for o in self.outcomes if not o.is_mature)


def classify_twenty_session_move(
    origin_close: Decimal,
    maturity_close: Decimal,
) -> str:
    """
    Classifies a twenty-session price movement against the exact +/-0.5% band.

    Parameters:
        origin_close: Decimal Close price at origin session C0 (> 0).
        maturity_close: Decimal Close price at maturity session C20 (> 0).

    Returns:
        'BULL' if (C20 / C0) - 1 > 0.005.
        'BEAR' if (C20 / C0) - 1 < -0.005.
        'NEUTRAL' otherwise, including both exact boundaries:
            (C20 / C0) - 1 == +0.005 and (C20 / C0) - 1 == -0.005.

    Numerical design:
        Uses standard-library fractions.Fraction to convert Decimal inputs into exact
        rational numbers. This guarantees that class decisions are completely independent
        of ambient decimal.Context precision and rounding traps (such as Inexact, Rounded,
        or Subnormal), and avoids binary floating-point representation drift.
        Algebraically, for strictly positive C0 and C20:
            (C20 / C0) - 1 > 1 / 200  <=>  200 * C20 > 201 * C0  (BULL)
            (C20 / C0) - 1 < -1 / 200 <=>  200 * C20 < 199 * C0  (BEAR)
            Exact boundaries 200 * C20 == 201 * C0 and 200 * C20 == 199 * C0 are NEUTRAL.
    """
    if origin_close <= 0:
        raise ValueError(f"origin_close must be strictly positive, got {origin_close}")
    if maturity_close <= 0:
        raise ValueError(f"maturity_close must be strictly positive, got {maturity_close}")

    c0 = Fraction(origin_close)
    c20 = Fraction(maturity_close)

    # Scale by 200 for exact cross-comparison against 201 * c0 (+0.5%) and 199 * c0 (-0.5%)
    c20_scaled = c20 * 200
    if c20_scaled > c0 * 201:
        return OUTCOME_CLASS_BULL
    if c20_scaled < c0 * 199:
        return OUTCOME_CLASS_BEAR
    return OUTCOME_CLASS_NEUTRAL


def compute_twenty_session_outcomes(series: LoadedSeries) -> OutcomeSeries:
    """
    Computes inspectable twenty-session forward price outcomes for a validated Nifty series.

    Parameters:
        series: LoadedSeries instance produced by load_series for 'nifty50_price_index'.

    Returns:
        OutcomeSeries containing one TwentySessionOutcome record per supplied Nifty origin.

    Raises:
        InputValidationError: If the series is not a LoadedSeries or has an invalid series_id.

    Invariants:
        1. Positional session counting: origin i pairs with future session i + 20 on the supplied axis.
           Calendar dates, weekends, and gaps do not alter positional indexing.
        2. Preservation: Every origin observation is preserved with its index, date, and Close.
        3. Tail handling: The final min(20, N) origins have is_mature=False and status='unknown'.
           For N <= 20, all origins are unknown. For N == 21, exactly origin 0 is mature.
        4. Independent of VIX: Outcomes depend only on the Nifty sequence; missing VIX observations
           never compress, expand, or shift the outcome axis.
        5. Future data boundary: Outcomes represent actual realized future labels for downstream
           evaluation or training. This function does not perform as-of feature admission, train/test
           splitting, purging, embargoing, eligibility masking, or predictive modeling.
        6. Pure function: Operates strictly in-memory with zero file I/O, network calls, or side effects.
    """
    if not isinstance(series, LoadedSeries):
        raise InputValidationError(
            f"Expected LoadedSeries instance, got {type(series).__name__}",
            field="series",
            reason=f"Input series must be a LoadedSeries instance, got {type(series).__name__}",
        )

    if series.series_id != "nifty50_price_index":
        raise InputValidationError(
            f"Invalid series for outcome calculation: expected 'nifty50_price_index', got '{series.series_id}'",
            field="series_id",
            reason=f"Wrong series ID '{series.series_id}'; outcomes require 'nifty50_price_index'",
        )

    records = series.records
    total_records = len(records)
    outcomes: List[TwentySessionOutcome] = []

    for i in range(total_records):
        origin_rec = records[i]
        future_idx = i + HORIZON_SESSIONS

        if future_idx < total_records:
            maturity_rec = records[future_idx]
            outcome_cls = classify_twenty_session_move(origin_rec.close, maturity_rec.close)
            outcomes.append(
                TwentySessionOutcome(
                    origin_index=i,
                    origin_date=origin_rec.date,
                    origin_close=origin_rec.close,
                    is_mature=True,
                    status=STATUS_MATURE,
                    maturity_index=future_idx,
                    maturity_date=maturity_rec.date,
                    maturity_close=maturity_rec.close,
                    outcome_class=outcome_cls,
                )
            )
        else:
            outcomes.append(
                TwentySessionOutcome(
                    origin_index=i,
                    origin_date=origin_rec.date,
                    origin_close=origin_rec.close,
                    is_mature=False,
                    status=STATUS_UNKNOWN,
                    maturity_index=None,
                    maturity_date=None,
                    maturity_close=None,
                    outcome_class=None,
                )
            )

    return OutcomeSeries(
        series_id=series.series_id,
        outcomes=tuple(outcomes),
    )
