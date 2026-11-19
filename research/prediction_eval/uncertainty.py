"""
Offline Nifty 50 Prediction Evaluation: Statistical Uncertainty Engine (S2).

This module owns pure standard-library DTOs, validation, stationary bootstrap
resampling, percentile quantile calculations, position stream fingerprinting,
and canonical acyclic artifact schemas for paired TEST-only Brier loss differences.

Normative requirements:
  - Protocol ID: nivesh-paired-stationary-brier-v1
  - Pure stdlib only: no numpy/scipy/arch dependencies, no file/process/network I/O.
  - Strict validation before unavailability: malformed data is always an error.
  - Precedence: comparison_unavailable > empty_cohort > non_contiguous > floor > available.
  - Fixed stationary bootstrap: L in (20, 40, 60), B=10000, seed=20261103+L, floor n >= 10L.
  - Linear integer quantile interpolation on 40ths: q = 1/40 (2.5%), 39/40 (97.5%).
  - Hard cap MAX_RESAMPLE_POSITIONS = 30000000; reject over-limit/invalid caps, never clamp.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import datetime
import hashlib
import json
import math
import random
import re
import struct
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    Union,
)

# --- Protocol & Schema Identifiers ---

UNCERTAINTY_PROTOCOL_ID: str = "nivesh-paired-stationary-brier-v1"
SCHEMA_VERSION_UNCERTAINTY_INPUT: str = "nivesh-uncertainty-input-v1"
SCHEMA_VERSION_UNCERTAINTY_DIAGNOSTICS: str = "nivesh-uncertainty-diagnostics-v1"

UNCERTAINTY_METHOD: str = "paired_stationary_bootstrap"
BOOTSTRAP_REPLICATES: int = 10000
NOMINAL_COVERAGE: float = 0.95
QUANTILE_RULE: str = "linear_integer40_v1"
BLOCK_FLOOR_FACTOR: int = 10
MAX_RESAMPLE_POSITIONS: int = 30000000

BLOCK_LENGTHS: Tuple[int, ...] = (20, 40, 60)
BLOCK_LENGTH_SEEDS: Dict[int, int] = {20: 20261123, 40: 20261143, 60: 20261163}
BLOCK_LENGTH_LABELS: Dict[int, str] = {
    20: "minimum, overlap-motivated setting; not a minimum realized block length",
    40: "intermediate block length",
    60: "long block length",
}

PAIR_HEURISTIC_MINUS_FREQUENCY: str = "heuristic_minus_frequency"
PAIR_HEURISTIC_MINUS_LOGISTIC: str = "heuristic_minus_logistic"
ORDERED_PAIR_IDS: Tuple[str, ...] = (
    PAIR_HEURISTIC_MINUS_FREQUENCY,
    PAIR_HEURISTIC_MINUS_LOGISTIC,
)

UNCERTAINTY_STATUS_AVAILABLE: str = "available"
UNCERTAINTY_STATUS_PARTIALLY_AVAILABLE: str = "partially_available"
UNCERTAINTY_STATUS_UNAVAILABLE: str = "unavailable"
SUPPORTED_UNCERTAINTY_STATUSES: frozenset[str] = frozenset({
    UNCERTAINTY_STATUS_AVAILABLE,
    UNCERTAINTY_STATUS_PARTIALLY_AVAILABLE,
    UNCERTAINTY_STATUS_UNAVAILABLE,
})

REASON_COMPARISON_UNAVAILABLE: str = "comparison_unavailable"
REASON_EMPTY_COHORT: str = "empty_cohort"
REASON_NON_CONTIGUOUS: str = "non_contiguous_test_cohort"
REASON_INSUFFICIENT_BLOCKS: str = "insufficient_nominal_blocks"

# Reasons that apply to every length at once, and the two of those that leave no point estimate
COMMON_UNAVAILABLE_REASONS: Tuple[str, ...] = (
    REASON_COMPARISON_UNAVAILABLE,
    REASON_EMPTY_COHORT,
    REASON_NON_CONTIGUOUS,
)
NO_POINT_REASONS: Tuple[str, ...] = (REASON_COMPARISON_UNAVAILABLE, REASON_EMPTY_COHORT)
SUPPORTED_UNAVAILABLE_REASONS: Tuple[str, ...] = COMMON_UNAVAILABLE_REASONS + (REASON_INSUFFICIENT_BLOCKS,)

METHOD_NAMES: Tuple[str, ...] = ("heuristic", "frequency", "logistic")

FINGERPRINT_PREFIX: bytes = b"NIVESHPILOT_S2_SB_INDEX_V1\x00"
RNG_API_LABEL: str = "python.random.Random/randrange/random on pinned runtime"

HORIZON_SESSIONS: int = 20

_SHA256_HEX_REGEX = re.compile(r"\A[0-9A-Fa-f]{64}\Z")
_SHA256_UPPER_HEX_REGEX = re.compile(r"\A[0-9A-F]{64}\Z")
_ISO_DATE_REGEX = re.compile(r"\A[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")


# --- Errors ---


class UncertaintyValidationError(ValueError):
    """Raised when an uncertainty request structure, types, keys or invariants are invalid."""

    def __init__(self, message: str, *, field: Optional[str] = None):
        super().__init__(message)
        self.field = field


class UncertaintyResourceError(RuntimeError):
    """Raised when required resampling positions exceed the configured or ceiling cap."""

    def __init__(self, message: str, *, required_positions: int, max_positions: int):
        super().__init__(message)
        self.required_positions = required_positions
        self.max_positions = max_positions


def _is_finite_number(value: Any) -> bool:
    """True for a finite native int or float. An integer beyond binary64 range is not finite."""
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


# --- Strict JSON Helpers ---


def _reject_duplicate_keys(pairs: List[Tuple[str, Any]]) -> Dict[str, Any]:
    d: Dict[str, Any] = {}
    for k, v in pairs:
        if k in d:
            raise ValueError(f"Duplicate JSON key: {k!r}")
        d[k] = v
    return d


def _reject_constant(token: str) -> None:
    raise ValueError(f"Non-finite JSON token not allowed: {token!r}")


def _finite_float(token: str) -> float:
    val = float(token)
    if not math.isfinite(val):
        raise ValueError(f"Non-finite JSON number not allowed: {token!r}")
    return val


def parse_strict_json(json_text: str) -> Any:
    return json.loads(
        json_text,
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_constant,
        parse_float=_finite_float,
    )


# --- Pure DTOs ---


@dataclass(frozen=True)
class BrierRow:
    """A scored observation row carrying its canonical origin index, date, and Brier score."""

    origin_index: int
    origin_date: datetime.date
    brier: float

    def __post_init__(self) -> None:
        if type(self.origin_index) is not int or type(self.origin_index) is bool or self.origin_index < 0:
            raise UncertaintyValidationError(f"origin_index must be non-negative int, got {self.origin_index!r}")
        if type(self.origin_date) is not datetime.date:
            raise UncertaintyValidationError(f"origin_date must be datetime.date, got {type(self.origin_date).__name__}")
        if not _is_finite_number(self.brier):
            raise UncertaintyValidationError(f"brier must be finite float, got {self.brier!r}")
        if self.brier < 0.0 or self.brier > 2.0:
            raise UncertaintyValidationError(f"brier must be in [0.0, 2.0], got {self.brier}")


@dataclass(frozen=True)
class RequestedKey:
    """Ordered canonical target origin index and session date."""

    origin_index: int
    origin_date: datetime.date

    def __post_init__(self) -> None:
        if type(self.origin_index) is not int or type(self.origin_index) is bool or self.origin_index < 0:
            raise UncertaintyValidationError(f"origin_index must be non-negative int, got {self.origin_index!r}")
        if type(self.origin_date) is not datetime.date:
            raise UncertaintyValidationError(f"origin_date must be datetime.date, got {type(self.origin_date).__name__}")


@dataclass(frozen=True)
class UncertaintyRequest:
    """
    Caller projection containing TEST-only scores, axis alignment, and admission context.

    input_identity is None while the domain request is serialized, because the identity is the
    hash of those very bytes. compute_uncertainty requires it, so it never enters the input.
    """

    axis_dates: Tuple[datetime.date, ...]
    test_start_index: int
    requested_keys: Tuple[RequestedKey, ...]
    comparison_status: str
    method_available: Dict[str, bool]
    method_rows: Optional[Dict[str, Tuple[BrierRow, ...]]]
    union_gap_positions: Tuple[int, ...]
    input_identity: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class PairInterval:
    """Lower and upper percentile endpoints for a paired difference at one block length."""

    pair_id: str
    lower: Optional[float]
    upper: Optional[float]

    def __post_init__(self) -> None:
        if self.pair_id not in ORDERED_PAIR_IDS:
            raise UncertaintyValidationError(f"Unknown pair_id {self.pair_id!r}")
        if (self.lower is None) != (self.upper is None):
            raise UncertaintyValidationError(f"Interval endpoints must both be None or both finite floats")
        if self.lower is not None:
            if not _is_finite_number(self.lower):
                raise UncertaintyValidationError(f"lower endpoint must be finite float, got {self.lower!r}")
            if not _is_finite_number(self.upper):
                raise UncertaintyValidationError(f"upper endpoint must be finite float, got {self.upper!r}")
            if self.lower < -2.0 or self.lower > 2.0:
                raise UncertaintyValidationError(f"lower endpoint out of Brier difference range [-2, 2]: {self.lower}")
            if self.upper < -2.0 or self.upper > 2.0:
                raise UncertaintyValidationError(f"upper endpoint out of Brier difference range [-2, 2]: {self.upper}")
            if self.lower > self.upper:
                raise UncertaintyValidationError(f"Interval lower ({self.lower}) exceeds upper ({self.upper})")


@dataclass(frozen=True)
class BlockLengthView:
    """Evaluation presentation and pair intervals for one block length."""

    block_length: int
    label: str
    status: str
    reason: Optional[str]
    seed: int
    pairs: Tuple[PairInterval, ...]

    def __post_init__(self) -> None:
        if self.block_length not in BLOCK_LENGTHS:
            raise UncertaintyValidationError(f"Unsupported block_length {self.block_length}")
        if self.status not in (UNCERTAINTY_STATUS_AVAILABLE, UNCERTAINTY_STATUS_UNAVAILABLE):
            raise UncertaintyValidationError(f"Per-length status must be available or unavailable, got {self.status!r}")
        if self.status == UNCERTAINTY_STATUS_AVAILABLE:
            if self.reason is not None:
                raise UncertaintyValidationError("Available block length must have reason None")
            for p in self.pairs:
                if p.lower is None or p.upper is None:
                    raise UncertaintyValidationError("Available block length must have finite pair endpoints")
        else:
            if not self.reason:
                raise UncertaintyValidationError("Unavailable block length must have non-empty reason")
            for p in self.pairs:
                if p.lower is not None or p.upper is not None:
                    raise UncertaintyValidationError("Unavailable block length must have None endpoints")


@dataclass(frozen=True)
class PointDifference:
    """Full-cohort point estimate difference math.fsum(d_i) / n for a pair."""

    pair_id: str
    point_difference: Optional[float]

    def __post_init__(self) -> None:
        if self.pair_id not in ORDERED_PAIR_IDS:
            raise UncertaintyValidationError(f"Unknown pair_id {self.pair_id!r}")
        if self.point_difference is not None:
            if not _is_finite_number(self.point_difference):
                raise UncertaintyValidationError(f"point_difference must be finite float, got {self.point_difference!r}")
            if self.point_difference < -2.0 or self.point_difference > 2.0:
                raise UncertaintyValidationError(f"point_difference out of range [-2, 2]: {self.point_difference}")


@dataclass(frozen=True)
class LengthDiagnostics:
    """Execution counters and stream fingerprint for one block length."""

    block_length: int
    seed: int
    replicates_completed: int
    sampled_positions: int
    random_calls: int
    randrange_calls: int
    index_stream_sha256: Optional[str]


@dataclass(frozen=True)
class UncertaintyDiagnostics:
    """Closed diagnostics document (nivesh-uncertainty-diagnostics-v1)."""

    schema_version: str
    protocol_id: str
    input_identity: Dict[str, Any]
    runtime_identity: Dict[str, Any]
    resource: Dict[str, int]
    lengths: Tuple[LengthDiagnostics, ...]


@dataclass(frozen=True)
class UncertaintyResult:
    """Closed uncertainty result container matching result and summary schemas."""

    protocol_id: str
    method: str
    status: str
    reason: Optional[str]
    n: int
    mature_span_count: int
    replicates: int
    nominal_coverage: float
    quantile_rule: str
    block_floor_factor: int
    point_differences: Tuple[PointDifference, ...]
    block_lengths: Tuple[BlockLengthView, ...]
    diagnostics: Optional[UncertaintyDiagnostics] = None

    def __post_init__(self) -> None:
        if self.protocol_id != UNCERTAINTY_PROTOCOL_ID:
            raise UncertaintyValidationError(f"protocol_id must be '{UNCERTAINTY_PROTOCOL_ID}', got {self.protocol_id!r}")
        if self.method != UNCERTAINTY_METHOD:
            raise UncertaintyValidationError(f"method must be '{UNCERTAINTY_METHOD}', got {self.method!r}")
        if type(self.status) is not str or self.status not in SUPPORTED_UNCERTAINTY_STATUSES:
            raise UncertaintyValidationError(f"status must be in {SUPPORTED_UNCERTAINTY_STATUSES}, got {self.status!r}")
        if self.status in (UNCERTAINTY_STATUS_AVAILABLE, UNCERTAINTY_STATUS_PARTIALLY_AVAILABLE):
            if self.reason is not None:
                raise UncertaintyValidationError("Available or partially_available status must have top reason None")
        else:
            if not self.reason:
                raise UncertaintyValidationError("Unavailable status must have non-empty top reason")
        if type(self.n) is not int or type(self.n) is bool or self.n < 0:
            raise UncertaintyValidationError(f"n must be non-negative integer, got {self.n!r}")
        if type(self.mature_span_count) is not int or type(self.mature_span_count) is bool or self.mature_span_count < 0:
            raise UncertaintyValidationError(f"mature_span_count must be non-negative integer, got {self.mature_span_count!r}")
        if self.replicates != BOOTSTRAP_REPLICATES:
            raise UncertaintyValidationError(f"replicates must be {BOOTSTRAP_REPLICATES}")
        if self.nominal_coverage != NOMINAL_COVERAGE:
            raise UncertaintyValidationError(f"nominal_coverage must be {NOMINAL_COVERAGE}")
        if self.quantile_rule != QUANTILE_RULE:
            raise UncertaintyValidationError(f"quantile_rule must be '{QUANTILE_RULE}'")
        if self.block_floor_factor != BLOCK_FLOOR_FACTOR:
            raise UncertaintyValidationError(f"block_floor_factor must be {BLOCK_FLOOR_FACTOR}")


# --- Quantile and Fingerprint Functions ---


def linear_integer40_quantile(values: Sequence[float], numerator: int, denominator: int = 40) -> float:
    """
    Computes quantile with linear integer interpolation on 40ths.

    h_scaled = (n - 1) * numerator
    j = h_scaled // denominator
    remainder = h_scaled % denominator
    w = remainder / denominator
    result = values[j] + w * (values[j+1] - values[j])
    """
    if type(numerator) is not int or type(denominator) is not int or type(numerator) is bool or type(denominator) is bool:
        raise UncertaintyValidationError("Quantile numerator and denominator must be native integers")
    if denominator <= 0 or numerator < 0 or numerator > denominator:
        raise UncertaintyValidationError(f"Invalid quantile numerator={numerator}, denominator={denominator}")
    n = len(values)
    if n == 0:
        raise UncertaintyValidationError("Cannot compute quantile of empty sequence")
    if n == 1:
        return float(values[0])
    h_scaled = (n - 1) * numerator
    j = h_scaled // denominator
    remainder = h_scaled % denominator
    if j >= n - 1:
        return float(values[n - 1])
    w = remainder / float(denominator)
    v_j = float(values[j])
    v_next = float(values[j + 1])
    return v_j + w * (v_next - v_j)


def compute_sampled_position_fingerprint(
    input_sha256: str,
    block_length: int,
    replicates: int,
    n: int,
    seed: int,
    position_stream: Iterable[Tuple[int, Sequence[int]]],
) -> str:
    """
    Exact per-length sampled-position fingerprint stream:
      ASCII 'NIVESHPILOT_S2_SB_INDEX_V1\x00'
      32 raw bytes of verified uncertainty-input SHA256
      L, B, n, seed each unsigned 64-bit big-endian
      for r=0..B-1: unsigned 64-bit big-endian r, then each of n sampled positions in order
    """
    hasher = hashlib.sha256()
    hasher.update(FINGERPRINT_PREFIX)
    if not _SHA256_HEX_REGEX.match(input_sha256):
        raise UncertaintyValidationError(f"input_sha256 must be 64-character hex string, got {input_sha256!r}")
    hasher.update(bytes.fromhex(input_sha256))
    hasher.update(struct.pack(">QQQQ", block_length, replicates, n, seed))
    for r, positions in position_stream:
        hasher.update(struct.pack(">Q", r))
        for pos in positions:
            hasher.update(struct.pack(">Q", pos))
    return hasher.hexdigest().upper()


def generate_stationary_indices(rng: Any, n: int, L: int) -> Tuple[List[int], int]:
    """
    Generates a single replicate stream of stationary bootstrap sample indices of length n.

    Uses the stationary bootstrap algorithm (Politis & Romano, 1994):
      - Initial position pos is drawn uniformly from {0, ..., n-1} via rng.randrange(n).
      - For each subsequent step 1..n-1:
          u = rng.random()
          if u < 1.0 / L:
              pos = rng.randrange(n)  # restart block
          else:
              pos = (pos + 1) % n    # continue block (with wrap-around)

    Returns:
      Tuple of (indices, restarts), where indices is a List[int] of length n,
      and restarts is the count of block restart events in steps 1..n-1.
    """
    if type(n) is not int or type(n) is bool or n <= 0:
        raise UncertaintyValidationError(f"Sample size n must be positive integer, got {n!r}")
    if type(L) is not int or type(L) is bool or L <= 0:
        raise UncertaintyValidationError(f"Block length L must be positive integer, got {L!r}")

    prob_restart = 1.0 / float(L)
    pos = rng.randrange(n)
    indices: List[int] = [pos]
    restarts = 0

    for _ in range(1, n):
        u = rng.random()
        if u < prob_restart:
            pos = rng.randrange(n)
            restarts += 1
        else:
            pos = (pos + 1) % n
        indices.append(pos)

    return indices, restarts


def compute_paired_replicate_means(
    d_hf: Sequence[float],
    d_hl: Sequence[float],
    indices: Sequence[int],
) -> Tuple[float, float]:
    """
    Computes replicate means for paired loss differences using the supplied indices.

    d_hf: Sequence of Brier loss differences (heuristic - frequency).
    d_hl: Sequence of Brier loss differences (heuristic - logistic).
    indices: Resampled index sequence of length n.

    Returns:
      (mean_hf, mean_hl) as exact IEEE floats via math.fsum.
    """
    n = len(indices)
    if n == 0:
        raise UncertaintyValidationError("Cannot compute replicate means for empty indices")
    sampled_hf = [d_hf[idx] for idx in indices]
    sampled_hl = [d_hl[idx] for idx in indices]
    mean_hf = math.fsum(sampled_hf) / float(n)
    mean_hl = math.fsum(sampled_hl) / float(n)
    return mean_hf, mean_hl


# --- Validation ---


def validate_uncertainty_request(request: UncertaintyRequest) -> None:
    """
    Validates structural types, axis alignment, keys, and contradiction states.
    All malformed shapes fail immediately as errors before any status precedence.
    """
    if not isinstance(request, UncertaintyRequest):
        raise UncertaintyValidationError(f"Expected UncertaintyRequest, got {type(request).__name__}")

    # axis_dates
    if type(request.axis_dates) not in (tuple, list) or not request.axis_dates:
        raise UncertaintyValidationError("axis_dates must be a non-empty sequence of dates")
    for idx, d in enumerate(request.axis_dates):
        if type(d) is not datetime.date:
            raise UncertaintyValidationError(f"axis_dates[{idx}] must be datetime.date, got {type(d).__name__}")
        if idx > 0 and d <= request.axis_dates[idx - 1]:
            raise UncertaintyValidationError(f"axis_dates must be strictly increasing: {request.axis_dates[idx-1]} >= {d}")

    total_n = len(request.axis_dates)

    # test_start_index
    if type(request.test_start_index) is not int or type(request.test_start_index) is bool:
        raise UncertaintyValidationError(f"test_start_index must be native integer, got {request.test_start_index!r}")
    if request.test_start_index < 0 or request.test_start_index >= total_n:
        raise UncertaintyValidationError(f"test_start_index {request.test_start_index} out of range [0, {total_n})")

    # potential mature test span
    mature_start = request.test_start_index
    mature_end = max(mature_start, total_n - HORIZON_SESSIONS)
    span_indices = set(range(mature_start, mature_end))

    # requested_keys
    if type(request.requested_keys) not in (tuple, list):
        raise UncertaintyValidationError("requested_keys must be a tuple or list")
    prev_idx = -1
    for k_pos, key in enumerate(request.requested_keys):
        if not isinstance(key, RequestedKey):
            raise UncertaintyValidationError(f"requested_keys[{k_pos}] must be RequestedKey, got {type(key).__name__}")
        if key.origin_index not in span_indices:
            raise UncertaintyValidationError(
                f"requested_keys[{k_pos}] origin_index {key.origin_index} not within mature test span [{mature_start}, {mature_end})"
            )
        if key.origin_date != request.axis_dates[key.origin_index]:
            raise UncertaintyValidationError(
                f"requested_keys[{k_pos}] date {key.origin_date} does not match axis_dates[{key.origin_index}] ({request.axis_dates[key.origin_index]})"
            )
        if key.origin_index <= prev_idx:
            raise UncertaintyValidationError(f"requested_keys must be strictly ordered by origin_index: {prev_idx} >= {key.origin_index}")
        prev_idx = key.origin_index

    # union_gap_positions
    if type(request.union_gap_positions) not in (tuple, list):
        raise UncertaintyValidationError("union_gap_positions must be a tuple or list")
    prev_gap = -1
    for g_pos, gap in enumerate(request.union_gap_positions):
        if type(gap) is not int or type(gap) is bool:
            raise UncertaintyValidationError(f"union_gap_positions[{g_pos}] must be native integer, got {gap!r}")
        if gap not in span_indices:
            raise UncertaintyValidationError(f"union_gap_positions[{g_pos}] {gap} not within mature test span [{mature_start}, {mature_end})")
        if gap <= prev_gap:
            raise UncertaintyValidationError(f"union_gap_positions must be strictly increasing: {prev_gap} >= {gap}")
        prev_gap = gap

    # Compare missing positions with frozen union gaps
    requested_set = {k.origin_index for k in request.requested_keys}
    expected_gaps = tuple(sorted(span_indices - requested_set))
    if tuple(request.union_gap_positions) != expected_gaps:
        raise UncertaintyValidationError(
            f"union_gap_positions mismatch: expected {expected_gaps}, got {request.union_gap_positions}"
        )

    # method_available
    if type(request.method_available) is not dict:
        raise UncertaintyValidationError("method_available must be a dict")
    expected_models = {"heuristic", "frequency", "logistic"}
    if set(request.method_available.keys()) != expected_models:
        raise UncertaintyValidationError(f"method_available keys must be {expected_models}, got {set(request.method_available.keys())}")
    for m, av in request.method_available.items():
        if type(av) is not bool:
            raise UncertaintyValidationError(f"method_available[{m!r}] must be native bool, got {type(av).__name__}")

    # comparison_status
    if request.comparison_status not in ("scored", "empty", "comparison_unavailable"):
        raise UncertaintyValidationError(f"Invalid comparison_status {request.comparison_status!r}")

    all_methods_available = all(request.method_available.values())

    # State contradiction checks
    if request.comparison_status == "comparison_unavailable":
        if all_methods_available:
            raise UncertaintyValidationError("comparison_unavailable requires at least one method unavailable")
        if request.method_rows is not None:
            raise UncertaintyValidationError("comparison_unavailable requires method_rows=None")

    elif request.comparison_status == "empty":
        if not all_methods_available:
            raise UncertaintyValidationError("empty comparison requires all methods available")
        if len(request.requested_keys) != 0:
            raise UncertaintyValidationError(f"empty comparison requires 0 requested keys, got {len(request.requested_keys)}")
        if type(request.method_rows) is not dict or set(request.method_rows.keys()) != expected_models:
            raise UncertaintyValidationError("empty comparison requires empty method_rows mapping for all three models")
        for m in expected_models:
            rows = request.method_rows[m]
            if type(rows) not in (tuple, list) or len(rows) != 0:
                raise UncertaintyValidationError(f"empty comparison requires an empty row sequence for {m}, got {rows!r}")

    elif request.comparison_status == "scored":
        if not all_methods_available:
            raise UncertaintyValidationError("scored comparison requires all methods available")
        if len(request.requested_keys) == 0:
            raise UncertaintyValidationError("scored comparison requires non-empty requested_keys")
        if type(request.method_rows) is not dict or set(request.method_rows.keys()) != expected_models:
            raise UncertaintyValidationError("scored comparison requires method_rows for all three models")

        n_req = len(request.requested_keys)
        for m in ("heuristic", "frequency", "logistic"):
            rows = request.method_rows[m]
            if type(rows) not in (tuple, list) or len(rows) != n_req:
                raise UncertaintyValidationError(f"method_rows[{m!r}] length {len(rows) if isinstance(rows, (tuple, list)) else 'None'} must match requested_keys length {n_req}")
            for r_idx, row in enumerate(rows):
                if not isinstance(row, BrierRow):
                    raise UncertaintyValidationError(f"method_rows[{m!r}][{r_idx}] must be BrierRow")
                target_key = request.requested_keys[r_idx]
                if row.origin_index != target_key.origin_index or row.origin_date != target_key.origin_date:
                    raise UncertaintyValidationError(
                        f"method_rows[{m!r}][{r_idx}] key ({row.origin_index}, {row.origin_date}) does not match requested_key ({target_key.origin_index}, {target_key.origin_date})"
                    )


def validate_input_identity(identity: Any) -> None:
    """Validates the caller's {raw_byte_count, sha256} identity of the written input bytes."""
    if type(identity) is not dict or set(identity.keys()) != {"raw_byte_count", "sha256"}:
        raise UncertaintyValidationError("input_identity must hold exactly raw_byte_count and sha256")
    if type(identity["raw_byte_count"]) is not int or identity["raw_byte_count"] < 0:
        raise UncertaintyValidationError("input_identity.raw_byte_count must be a non-negative native integer")
    if type(identity["sha256"]) is not str or not _SHA256_HEX_REGEX.match(identity["sha256"]):
        raise UncertaintyValidationError("input_identity.sha256 must be a 64-character hex string")


def validate_runtime_identity(identity: Any) -> None:
    """Validates the caller-verified runtime labels. This module never measures them itself."""
    if type(identity) is not dict or set(identity.keys()) != {"python_implementation", "python_version"}:
        raise UncertaintyValidationError("runtime_identity must hold exactly python_implementation and python_version")
    for key in ("python_implementation", "python_version"):
        if type(identity[key]) is not str or not identity[key]:
            raise UncertaintyValidationError(f"runtime_identity.{key} must be a non-empty string")


# --- Shared State Rules ---


def common_unavailable_reason(comparison_status: str, n: int, gap_count: int) -> Optional[str]:
    """Returns the reason that makes every length unavailable, in the fixed precedence order."""
    if comparison_status == "comparison_unavailable":
        return REASON_COMPARISON_UNAVAILABLE
    if comparison_status == "empty" or n == 0:
        return REASON_EMPTY_COHORT
    if gap_count > 0:
        return REASON_NON_CONTIGUOUS
    return None


def available_block_lengths(n: int) -> Tuple[int, ...]:
    """Returns the lengths whose floor n >= 10L a contiguous cohort of n origins clears."""
    return tuple(L for L in BLOCK_LENGTHS if n >= BLOCK_FLOOR_FACTOR * L)


def paired_loss_differences(
    method_rows: Mapping[str, Sequence[BrierRow]],
) -> Tuple[List[float], List[float]]:
    """Returns d_i for heuristic-frequency and heuristic-logistic on the identical ordered rows."""
    h_rows = method_rows["heuristic"]
    d_hf = [h.brier - f.brier for h, f in zip(h_rows, method_rows["frequency"])]
    d_hl = [h.brier - l.brier for h, l in zip(h_rows, method_rows["logistic"])]
    return d_hf, d_hl


# --- Pure Resampling Engine ---


def compute_uncertainty(
    request: UncertaintyRequest,
    *,
    max_resample_positions: int,
    runtime_identity: Dict[str, Any],
    rng_factory: Optional[Callable[[int], Any]] = None,
) -> UncertaintyResult:
    """
    Computes paired test-loss uncertainty with the fixed stationary bootstrap protocol.

    request.input_identity and runtime_identity are required for every state, including the
    unavailable ones: diagnostics always record them, and a fingerprint must bind real bytes.

    Precedence:
      1. comparison_unavailable: point differences=None, all intervals unavailable.
      2. empty_cohort: point differences=None, all intervals unavailable.
      3. non_contiguous_test_cohort: full-cohort point differences preserved, all intervals unavailable.
      4. per-length floor: n >= 10L required for that block length.
      5. available: stationary bootstrap intervals computed.
    """
    # 1. Validate max_resample_positions ceiling and parameter type
    if type(max_resample_positions) is not int or type(max_resample_positions) is bool:
        raise UncertaintyValidationError(f"max_resample_positions must be native integer, got {max_resample_positions!r}")
    if max_resample_positions < 1 or max_resample_positions > MAX_RESAMPLE_POSITIONS:
        raise UncertaintyValidationError(
            f"max_resample_positions must be in [1, {MAX_RESAMPLE_POSITIONS}], got {max_resample_positions}"
        )

    # 2. Strict request validation (types, dates, order, gaps, contradiction states)
    validate_uncertainty_request(request)

    # 3. Computation identities, before any statistical state or RNG
    validate_input_identity(request.input_identity)
    validate_runtime_identity(runtime_identity)
    input_identity = dict(request.input_identity)

    total_n = len(request.axis_dates)
    mature_start = request.test_start_index
    mature_end = max(mature_start, total_n - HORIZON_SESSIONS)
    mature_span_count = mature_end - mature_start
    n = len(request.requested_keys)

    def _common_unavailable_result(reason: str, point_values: Tuple[Optional[float], Optional[float]]) -> UncertaintyResult:
        return UncertaintyResult(
            protocol_id=UNCERTAINTY_PROTOCOL_ID,
            method=UNCERTAINTY_METHOD,
            status=UNCERTAINTY_STATUS_UNAVAILABLE,
            reason=reason,
            n=n,
            mature_span_count=mature_span_count,
            replicates=BOOTSTRAP_REPLICATES,
            nominal_coverage=NOMINAL_COVERAGE,
            quantile_rule=QUANTILE_RULE,
            block_floor_factor=BLOCK_FLOOR_FACTOR,
            point_differences=(
                PointDifference(PAIR_HEURISTIC_MINUS_FREQUENCY, point_values[0]),
                PointDifference(PAIR_HEURISTIC_MINUS_LOGISTIC, point_values[1]),
            ),
            block_lengths=tuple(_unavailable_view(L, reason) for L in BLOCK_LENGTHS),
            diagnostics=_build_diagnostics(
                max_resample_positions,
                0,
                0,
                tuple(_unused_length_diagnostics(L) for L in BLOCK_LENGTHS),
                input_identity,
                runtime_identity,
            ),
        )

    common_reason = common_unavailable_reason(request.comparison_status, n, len(request.union_gap_positions))

    # 4. Handle Precedence 1 and 2: comparison_unavailable and empty_cohort have no point estimate
    if common_reason in NO_POINT_REASONS:
        return _common_unavailable_result(common_reason, (None, None))

    # At this point, comparison is scored and n > 0. Compute full-cohort paired loss differences.
    assert request.method_rows is not None
    d_hf, d_hl = paired_loss_differences(request.method_rows)

    pt_hf = math.fsum(d_hf) / float(n)
    pt_hl = math.fsum(d_hl) / float(n)
    point_diffs = (
        PointDifference(PAIR_HEURISTIC_MINUS_FREQUENCY, pt_hf),
        PointDifference(PAIR_HEURISTIC_MINUS_LOGISTIC, pt_hl),
    )

    # 5. Handle Precedence 3: non_contiguous_test_cohort
    if common_reason is not None:
        return _common_unavailable_result(common_reason, (pt_hf, pt_hl))

    # Cohort is contiguous: n == mature_span_count.
    # Check per-length floor: n >= 10L.
    available_lengths = available_block_lengths(n)

    # Resource check before any RNG construction or draws
    required_positions = BOOTSTRAP_REPLICATES * n * len(available_lengths)
    if required_positions > max_resample_positions:
        raise UncertaintyResourceError(
            f"Required resampling positions {required_positions} exceeds execution cap {max_resample_positions}",
            required_positions=required_positions,
            max_positions=max_resample_positions,
        )

    # Precedence 4 & 5: per-length floor / availability
    views: List[BlockLengthView] = []
    diag_lengths: List[LengthDiagnostics] = []
    visited_positions_total = 0

    for L in BLOCK_LENGTHS:
        seed = BLOCK_LENGTH_SEEDS[L]
        if L not in available_lengths:
            views.append(_unavailable_view(L, REASON_INSUFFICIENT_BLOCKS))
            diag_lengths.append(_unused_length_diagnostics(L))
            continue

        # Available: execute stationary bootstrap
        if rng_factory is not None:
            rng = rng_factory(seed)
        else:
            rng = random.Random(seed)

        # Hasher for index stream fingerprint
        hasher = hashlib.sha256()
        hasher.update(FINGERPRINT_PREFIX)
        hasher.update(bytes.fromhex(input_identity["sha256"]))
        hasher.update(struct.pack(">QQQQ", L, BOOTSTRAP_REPLICATES, n, seed))

        replicate_means_hf: List[float] = []
        replicate_means_hl: List[float] = []

        randrange_calls = 0
        random_calls = 0

        for r in range(BOOTSTRAP_REPLICATES):
            hasher.update(struct.pack(">Q", r))
            indices, restarts = generate_stationary_indices(rng, n, L)
            randrange_calls += 1 + restarts
            random_calls += n - 1
            for pos in indices:
                hasher.update(struct.pack(">Q", pos))

            mean_hf, mean_hl = compute_paired_replicate_means(d_hf, d_hl, indices)
            replicate_means_hf.append(mean_hf)
            replicate_means_hl.append(mean_hl)

        replicate_means_hf.sort()
        replicate_means_hl.sort()

        lower_hf = linear_integer40_quantile(replicate_means_hf, 1, 40)
        upper_hf = linear_integer40_quantile(replicate_means_hf, 39, 40)
        lower_hl = linear_integer40_quantile(replicate_means_hl, 1, 40)
        upper_hl = linear_integer40_quantile(replicate_means_hl, 39, 40)

        stream_sha = hasher.hexdigest().upper()
        sampled_pos_count = BOOTSTRAP_REPLICATES * n
        visited_positions_total += sampled_pos_count

        views.append(
            BlockLengthView(
                block_length=L,
                label=BLOCK_LENGTH_LABELS[L],
                status=UNCERTAINTY_STATUS_AVAILABLE,
                reason=None,
                seed=seed,
                pairs=(
                    PairInterval(PAIR_HEURISTIC_MINUS_FREQUENCY, lower_hf, upper_hf),
                    PairInterval(PAIR_HEURISTIC_MINUS_LOGISTIC, lower_hl, upper_hl),
                ),
            )
        )
        diag_lengths.append(
            LengthDiagnostics(
                block_length=L,
                seed=seed,
                replicates_completed=BOOTSTRAP_REPLICATES,
                sampled_positions=sampled_pos_count,
                random_calls=random_calls,
                randrange_calls=randrange_calls,
                index_stream_sha256=stream_sha,
            )
        )

    # Derive top-level status and reason
    if len(available_lengths) == len(BLOCK_LENGTHS):
        top_status = UNCERTAINTY_STATUS_AVAILABLE
        top_reason = None
    elif len(available_lengths) > 0:
        top_status = UNCERTAINTY_STATUS_PARTIALLY_AVAILABLE
        top_reason = None
    else:
        top_status = UNCERTAINTY_STATUS_UNAVAILABLE
        top_reason = REASON_INSUFFICIENT_BLOCKS

    diag_obj = _build_diagnostics(
        max_resample_positions,
        required_positions,
        visited_positions_total,
        tuple(diag_lengths),
        input_identity,
        runtime_identity,
    )

    return UncertaintyResult(
        protocol_id=UNCERTAINTY_PROTOCOL_ID,
        method=UNCERTAINTY_METHOD,
        status=top_status,
        reason=top_reason,
        n=n,
        mature_span_count=mature_span_count,
        replicates=BOOTSTRAP_REPLICATES,
        nominal_coverage=NOMINAL_COVERAGE,
        quantile_rule=QUANTILE_RULE,
        block_floor_factor=BLOCK_FLOOR_FACTOR,
        point_differences=point_diffs,
        block_lengths=tuple(views),
        diagnostics=diag_obj,
    )


def _unavailable_view(block_length: int, reason: str) -> BlockLengthView:
    return BlockLengthView(
        block_length=block_length,
        label=BLOCK_LENGTH_LABELS[block_length],
        status=UNCERTAINTY_STATUS_UNAVAILABLE,
        reason=reason,
        seed=BLOCK_LENGTH_SEEDS[block_length],
        pairs=(
            PairInterval(PAIR_HEURISTIC_MINUS_FREQUENCY, None, None),
            PairInterval(PAIR_HEURISTIC_MINUS_LOGISTIC, None, None),
        ),
    )


def _unused_length_diagnostics(block_length: int) -> LengthDiagnostics:
    """An unavailable length keeps its prespecified seed; its stream was never drawn."""
    return LengthDiagnostics(
        block_length=block_length,
        seed=BLOCK_LENGTH_SEEDS[block_length],
        replicates_completed=0,
        sampled_positions=0,
        random_calls=0,
        randrange_calls=0,
        index_stream_sha256=None,
    )


def _build_diagnostics(
    max_resample_positions: int,
    required_positions: int,
    visited_positions: int,
    lengths: Tuple[LengthDiagnostics, ...],
    input_identity: Dict[str, Any],
    runtime_identity: Dict[str, Any],
) -> UncertaintyDiagnostics:
    return UncertaintyDiagnostics(
        schema_version=SCHEMA_VERSION_UNCERTAINTY_DIAGNOSTICS,
        protocol_id=UNCERTAINTY_PROTOCOL_ID,
        input_identity=input_identity,
        runtime_identity={
            "python_implementation": runtime_identity["python_implementation"],
            "python_version": runtime_identity["python_version"],
            "rng_api": RNG_API_LABEL,
        },
        resource={
            "max_resample_positions": max_resample_positions,
            "required_positions": required_positions,
            "visited_positions": visited_positions,
        },
        lengths=lengths,
    )


# --- Serialization & Document Schemas ---


def build_uncertainty_input_document(request: UncertaintyRequest) -> Dict[str, Any]:
    """Constructs the closed dictionary for uncertainty-input.json."""
    validate_uncertainty_request(request)
    method_rows_doc: Optional[Dict[str, Any]] = None
    if request.method_rows is not None:
        method_rows_doc = {
            m: [
                {
                    "origin_index": r.origin_index,
                    "origin_date": r.origin_date.isoformat(),
                    "brier": r.brier,
                }
                for r in request.method_rows[m]
            ]
            for m in ("heuristic", "frequency", "logistic")
        }

    return {
        "schema_version": SCHEMA_VERSION_UNCERTAINTY_INPUT,
        "protocol_id": UNCERTAINTY_PROTOCOL_ID,
        "axis_dates": [d.isoformat() for d in request.axis_dates],
        "test_start_index": request.test_start_index,
        "requested_keys": [
            {"origin_index": k.origin_index, "origin_date": k.origin_date.isoformat()}
            for k in request.requested_keys
        ],
        "comparison_status": request.comparison_status,
        "method_available": {
            "heuristic": request.method_available["heuristic"],
            "frequency": request.method_available["frequency"],
            "logistic": request.method_available["logistic"],
        },
        "method_rows": method_rows_doc,
        "union_gap_positions": list(request.union_gap_positions),
    }


def _canonical_input_bytes(doc: Mapping[str, Any]) -> bytes:
    text = json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return text.encode("utf-8") + b"\n"


def serialize_uncertainty_input(request: UncertaintyRequest) -> bytes:
    """Serializes canonical uncertainty-input.json: compact ASCII, sorted keys, trailing LF."""
    return _canonical_input_bytes(build_uncertainty_input_document(request))


def _require_document_object(value: Any, keys: Set[str], path: str) -> Dict[str, Any]:
    if type(value) is not dict:
        raise UncertaintyValidationError(f"{path} must be a JSON object")
    if set(value.keys()) != keys:
        missing = sorted(keys - set(value.keys()))
        extra = sorted(set(value.keys()) - keys)
        raise UncertaintyValidationError(f"{path} key mismatch: missing={missing}, extra={extra}")
    return value


def _require_document_list(value: Any, path: str) -> List[Any]:
    if type(value) is not list:
        raise UncertaintyValidationError(f"{path} must be a JSON array")
    return value


def _document_date(value: Any, path: str) -> datetime.date:
    if type(value) is not str or not _ISO_DATE_REGEX.match(value):
        raise UncertaintyValidationError(f"{path} must be an ISO date string, got {value!r}")
    try:
        return datetime.date.fromisoformat(value)
    except ValueError as exc:
        raise UncertaintyValidationError(f"{path} is not a calendar date: {exc}") from exc


def _request_from_input_document(doc: Any) -> UncertaintyRequest:
    """
    Builds the domain request from a closed document, keeping every value as supplied.

    Nothing is coerced: a bool, string or float that stands in for a native value stays that
    value here, so the DTOs and validate_uncertainty_request reject it instead of repairing it.
    """
    _require_document_object(
        doc,
        {
            "schema_version",
            "protocol_id",
            "axis_dates",
            "test_start_index",
            "requested_keys",
            "comparison_status",
            "method_available",
            "method_rows",
            "union_gap_positions",
        },
        "uncertainty-input",
    )
    if doc["schema_version"] != SCHEMA_VERSION_UNCERTAINTY_INPUT:
        raise UncertaintyValidationError(f"Expected schema_version '{SCHEMA_VERSION_UNCERTAINTY_INPUT}', got {doc['schema_version']!r}")
    if doc["protocol_id"] != UNCERTAINTY_PROTOCOL_ID:
        raise UncertaintyValidationError(f"Expected protocol_id '{UNCERTAINTY_PROTOCOL_ID}', got {doc['protocol_id']!r}")

    axis_dates = tuple(
        _document_date(item, f"axis_dates[{pos}]")
        for pos, item in enumerate(_require_document_list(doc["axis_dates"], "axis_dates"))
    )
    requested_keys: List[RequestedKey] = []
    for pos, item in enumerate(_require_document_list(doc["requested_keys"], "requested_keys")):
        key = _require_document_object(item, {"origin_index", "origin_date"}, f"requested_keys[{pos}]")
        requested_keys.append(RequestedKey(key["origin_index"], _document_date(key["origin_date"], f"requested_keys[{pos}].origin_date")))

    method_rows: Optional[Dict[str, Tuple[BrierRow, ...]]] = None
    if doc["method_rows"] is not None:
        rows_doc = _require_document_object(doc["method_rows"], set(METHOD_NAMES), "method_rows")
        method_rows = {}
        for name in METHOD_NAMES:
            rows: List[BrierRow] = []
            for pos, item in enumerate(_require_document_list(rows_doc[name], f"method_rows.{name}")):
                row_path = f"method_rows.{name}[{pos}]"
                row = _require_document_object(item, {"origin_index", "origin_date", "brier"}, row_path)
                rows.append(BrierRow(row["origin_index"], _document_date(row["origin_date"], f"{row_path}.origin_date"), row["brier"]))
            method_rows[name] = tuple(rows)

    return UncertaintyRequest(
        axis_dates=axis_dates,
        test_start_index=doc["test_start_index"],
        requested_keys=tuple(requested_keys),
        comparison_status=doc["comparison_status"],
        method_available=doc["method_available"],
        method_rows=method_rows,
        union_gap_positions=tuple(_require_document_list(doc["union_gap_positions"], "union_gap_positions")),
    )


def validate_uncertainty_input_document(doc: Any) -> None:
    """Validates the closed nested schema and domain relations of uncertainty-input.json."""
    validate_uncertainty_request(_request_from_input_document(doc))


def parse_uncertainty_input(raw_bytes: bytes) -> UncertaintyRequest:
    """
    Parses exact uncertainty-input.json bytes into a validated UncertaintyRequest.

    The bytes must be the canonical encoding of what they hold. Re-encoding the parsed document
    keeps each valid number as written, including signed zero; nothing is rounded or rescored.
    """
    try:
        doc = parse_strict_json(raw_bytes.decode("utf-8"))
    except ValueError as exc:
        raise UncertaintyValidationError(f"uncertainty-input is not strict UTF-8 JSON: {exc}") from exc

    request = _request_from_input_document(doc)
    validate_uncertainty_request(request)
    if _canonical_input_bytes(doc) != raw_bytes:
        raise UncertaintyValidationError("uncertainty-input bytes are not the canonical encoding")
    return request


def build_uncertainty_diagnostics_document(diag: UncertaintyDiagnostics) -> Dict[str, Any]:
    """Constructs the closed dictionary for uncertainty-diagnostics.json."""
    return {
        "schema_version": diag.schema_version,
        "protocol_id": diag.protocol_id,
        "input_identity": dict(diag.input_identity),
        "runtime_identity": dict(diag.runtime_identity),
        "resource": dict(diag.resource),
        "lengths": [
            {
                "block_length": l.block_length,
                "seed": l.seed,
                "replicates_completed": l.replicates_completed,
                "sampled_positions": l.sampled_positions,
                "random_calls": l.random_calls,
                "randrange_calls": l.randrange_calls,
                "index_stream_sha256": l.index_stream_sha256,
            }
            for l in diag.lengths
        ],
    }


def validate_uncertainty_diagnostics_document(doc: Any) -> None:
    """
    Validates the closed schema of uncertainty-diagnostics.json and the counter relations it can
    prove alone. randrange_calls gets bounds only: it holds restarts, which aggregate counters
    cannot authenticate exactly without replaying the stream.
    """
    if type(doc) is not dict:
        raise UncertaintyValidationError("uncertainty-diagnostics root must be an object")
    expected_keys = {
        "schema_version",
        "protocol_id",
        "input_identity",
        "runtime_identity",
        "resource",
        "lengths",
    }
    if set(doc.keys()) != expected_keys:
        missing = sorted(expected_keys - set(doc.keys()))
        extra = sorted(set(doc.keys()) - expected_keys)
        raise UncertaintyValidationError(f"uncertainty-diagnostics key mismatch: missing={missing}, extra={extra}")

    if doc["schema_version"] != SCHEMA_VERSION_UNCERTAINTY_DIAGNOSTICS:
        raise UncertaintyValidationError(f"Expected schema_version '{SCHEMA_VERSION_UNCERTAINTY_DIAGNOSTICS}', got {doc['schema_version']!r}")
    if doc["protocol_id"] != UNCERTAINTY_PROTOCOL_ID:
        raise UncertaintyValidationError(f"Expected protocol_id '{UNCERTAINTY_PROTOCOL_ID}', got {doc['protocol_id']!r}")

    # input_identity
    inp = doc["input_identity"]
    if type(inp) is not dict or set(inp.keys()) != {"raw_byte_count", "sha256"}:
        raise UncertaintyValidationError("input_identity must have raw_byte_count and sha256")
    if type(inp["raw_byte_count"]) is not int or inp["raw_byte_count"] < 0:
        raise UncertaintyValidationError("input_identity.raw_byte_count must be non-negative int")
    if type(inp["sha256"]) is not str or not _SHA256_HEX_REGEX.match(inp["sha256"]):
        raise UncertaintyValidationError("input_identity.sha256 must be 64-character hex string")

    # runtime_identity
    run = doc["runtime_identity"]
    if type(run) is not dict or set(run.keys()) != {"python_implementation", "python_version", "rng_api"}:
        raise UncertaintyValidationError("runtime_identity keys mismatch")
    validate_runtime_identity({key: run[key] for key in ("python_implementation", "python_version")})
    if run["rng_api"] != RNG_API_LABEL:
        raise UncertaintyValidationError(f"Expected rng_api '{RNG_API_LABEL}', got {run['rng_api']!r}")

    # resource
    res = doc["resource"]
    if type(res) is not dict or set(res.keys()) != {"max_resample_positions", "required_positions", "visited_positions"}:
        raise UncertaintyValidationError("resource keys mismatch")
    for r_k in ("max_resample_positions", "required_positions", "visited_positions"):
        if type(res[r_k]) is not int or type(res[r_k]) is bool or res[r_k] < 0:
            raise UncertaintyValidationError(f"resource.{r_k} must be non-negative int")
    if res["max_resample_positions"] < 1 or res["max_resample_positions"] > MAX_RESAMPLE_POSITIONS:
        raise UncertaintyValidationError(f"resource.max_resample_positions must be in [1, {MAX_RESAMPLE_POSITIONS}]")

    # lengths
    lengths = doc["lengths"]
    if type(lengths) not in (list, tuple) or len(lengths) != len(BLOCK_LENGTHS):
        raise UncertaintyValidationError(f"lengths must contain {len(BLOCK_LENGTHS)} entries")
    for pos, item in enumerate(lengths):
        if type(item) is not dict:
            raise UncertaintyValidationError(f"lengths[{pos}] must be an object")
        expected_len_keys = {
            "block_length",
            "seed",
            "replicates_completed",
            "sampled_positions",
            "random_calls",
            "randrange_calls",
            "index_stream_sha256",
        }
        if set(item.keys()) != expected_len_keys:
            raise UncertaintyValidationError(f"lengths[{pos}] keys mismatch")
        if type(item["block_length"]) is not int or item["block_length"] != BLOCK_LENGTHS[pos]:
            raise UncertaintyValidationError(f"lengths[{pos}] block_length must be {BLOCK_LENGTHS[pos]}")
        if type(item["seed"]) is not int or item["seed"] != BLOCK_LENGTH_SEEDS[BLOCK_LENGTHS[pos]]:
            raise UncertaintyValidationError(f"lengths[{pos}] seed must be {BLOCK_LENGTH_SEEDS[BLOCK_LENGTHS[pos]]}")
        for cnt in ("replicates_completed", "sampled_positions", "random_calls", "randrange_calls"):
            if type(item[cnt]) is not int or type(item[cnt]) is bool or item[cnt] < 0:
                raise UncertaintyValidationError(f"lengths[{pos}].{cnt} must be non-negative int")

        fingerprint = item["index_stream_sha256"]
        if item["replicates_completed"] == 0:
            if item["sampled_positions"] or item["random_calls"] or item["randrange_calls"] or fingerprint is not None:
                raise UncertaintyValidationError(f"lengths[{pos}] without replicates must keep zero counters and a null index_stream_sha256")
        elif item["replicates_completed"] == BOOTSTRAP_REPLICATES:
            if item["sampled_positions"] == 0 or item["sampled_positions"] % BOOTSTRAP_REPLICATES != 0:
                raise UncertaintyValidationError(f"lengths[{pos}].sampled_positions must be a positive multiple of {BOOTSTRAP_REPLICATES}")
            if item["random_calls"] != item["sampled_positions"] - BOOTSTRAP_REPLICATES:
                raise UncertaintyValidationError(f"lengths[{pos}].random_calls must be one per non-initial position")
            if not BOOTSTRAP_REPLICATES <= item["randrange_calls"] <= BOOTSTRAP_REPLICATES + item["random_calls"]:
                raise UncertaintyValidationError(f"lengths[{pos}].randrange_calls is outside its possible bounds")
            if type(fingerprint) is not str or not _SHA256_UPPER_HEX_REGEX.match(fingerprint):
                raise UncertaintyValidationError(f"lengths[{pos}].index_stream_sha256 must be upper-case 64-hex")
        else:
            raise UncertaintyValidationError(f"lengths[{pos}].replicates_completed must be 0 or {BOOTSTRAP_REPLICATES}")

    if res["visited_positions"] != sum(item["sampled_positions"] for item in lengths):
        raise UncertaintyValidationError("resource.visited_positions must equal the sum of sampled_positions")
    if res["required_positions"] != res["visited_positions"]:
        raise UncertaintyValidationError("resource.required_positions must equal visited_positions on a completed calculation")
    if res["required_positions"] > res["max_resample_positions"]:
        raise UncertaintyValidationError("resource.required_positions exceeds max_resample_positions")


def uncertainty_result_to_document(res: UncertaintyResult) -> Dict[str, Any]:
    """Converts an UncertaintyResult to the closed dictionary shape for result and summary."""
    return {
        "protocol_id": res.protocol_id,
        "method": res.method,
        "status": res.status,
        "reason": res.reason,
        "n": res.n,
        "mature_span_count": res.mature_span_count,
        "replicates": res.replicates,
        "nominal_coverage": res.nominal_coverage,
        "quantile_rule": res.quantile_rule,
        "block_floor_factor": res.block_floor_factor,
        "point_differences": [
            {"pair_id": p.pair_id, "point_difference": p.point_difference}
            for p in res.point_differences
        ],
        "block_lengths": [
            {
                "block_length": bl.block_length,
                "label": bl.label,
                "status": bl.status,
                "reason": bl.reason,
                "seed": bl.seed,
                "pairs": [
                    {"pair_id": pr.pair_id, "lower": pr.lower, "upper": pr.upper}
                    for pr in bl.pairs
                ],
            }
            for bl in res.block_lengths
        ],
    }


def validate_uncertainty_result_document(doc: Any) -> None:
    """Validates the closed statistical uncertainty block inside result.json and panel-summary.json."""
    if type(doc) is not dict:
        raise UncertaintyValidationError("uncertainty block must be an object")
    expected_keys = {
        "protocol_id",
        "method",
        "status",
        "reason",
        "n",
        "mature_span_count",
        "replicates",
        "nominal_coverage",
        "quantile_rule",
        "block_floor_factor",
        "point_differences",
        "block_lengths",
    }
    if set(doc.keys()) != expected_keys:
        missing = sorted(expected_keys - set(doc.keys()))
        extra = sorted(set(doc.keys()) - expected_keys)
        raise UncertaintyValidationError(f"uncertainty block key mismatch: missing={missing}, extra={extra}")

    if doc["protocol_id"] != UNCERTAINTY_PROTOCOL_ID:
        raise UncertaintyValidationError(f"Expected protocol_id '{UNCERTAINTY_PROTOCOL_ID}', got {doc['protocol_id']!r}")
    if doc["method"] != UNCERTAINTY_METHOD:
        raise UncertaintyValidationError(f"Expected method '{UNCERTAINTY_METHOD}', got {doc['method']!r}")
    # Type first: a list or object here must be a schema error, not an unhashable-key crash
    if type(doc["status"]) is not str or doc["status"] not in SUPPORTED_UNCERTAINTY_STATUSES:
        raise UncertaintyValidationError(f"Unsupported uncertainty status {doc['status']!r}")

    if doc["status"] in (UNCERTAINTY_STATUS_AVAILABLE, UNCERTAINTY_STATUS_PARTIALLY_AVAILABLE):
        if doc["reason"] is not None:
            raise UncertaintyValidationError("Available/partial status must have top reason None")
    elif type(doc["reason"]) is not str or doc["reason"] not in SUPPORTED_UNAVAILABLE_REASONS:
        raise UncertaintyValidationError(f"Unavailable status needs a supported top reason, got {doc['reason']!r}")

    for cnt_field in ("n", "mature_span_count", "replicates", "block_floor_factor"):
        val = doc[cnt_field]
        if type(val) is not int or type(val) is bool or val < 0:
            raise UncertaintyValidationError(f"{cnt_field} must be non-negative int")

    if doc["replicates"] != BOOTSTRAP_REPLICATES:
        raise UncertaintyValidationError(f"replicates must be {BOOTSTRAP_REPLICATES}")
    if type(doc["nominal_coverage"]) is not float or doc["nominal_coverage"] != NOMINAL_COVERAGE:
        raise UncertaintyValidationError(f"nominal_coverage must be {NOMINAL_COVERAGE}")
    if doc["quantile_rule"] != QUANTILE_RULE:
        raise UncertaintyValidationError(f"quantile_rule must be '{QUANTILE_RULE}'")
    if doc["block_floor_factor"] != BLOCK_FLOOR_FACTOR:
        raise UncertaintyValidationError(f"block_floor_factor must be {BLOCK_FLOOR_FACTOR}")

    # point_differences
    pt_diffs = doc["point_differences"]
    if type(pt_diffs) not in (list, tuple) or len(pt_diffs) != len(ORDERED_PAIR_IDS):
        raise UncertaintyValidationError(f"point_differences must have {len(ORDERED_PAIR_IDS)} entries")
    for pos, p_id in enumerate(ORDERED_PAIR_IDS):
        entry = pt_diffs[pos]
        if type(entry) is not dict or set(entry.keys()) != {"pair_id", "point_difference"}:
            raise UncertaintyValidationError(f"point_differences[{pos}] format mismatch")
        if entry["pair_id"] != p_id:
            raise UncertaintyValidationError(f"point_differences[{pos}] pair_id must be {p_id}")
        pt_val = entry["point_difference"]
        if pt_val is not None:
            if not _is_finite_number(pt_val):
                raise UncertaintyValidationError(f"point_differences[{pos}] value must be finite float or None")
            if pt_val < -2.0 or pt_val > 2.0:
                raise UncertaintyValidationError(f"point_differences[{pos}] out of range [-2, 2]: {pt_val}")

    # block_lengths
    bl_list = doc["block_lengths"]
    if type(bl_list) not in (list, tuple) or len(bl_list) != len(BLOCK_LENGTHS):
        raise UncertaintyValidationError(f"block_lengths must have {len(BLOCK_LENGTHS)} entries")
    for pos, L in enumerate(BLOCK_LENGTHS):
        b_entry = bl_list[pos]
        if type(b_entry) is not dict:
            raise UncertaintyValidationError(f"block_lengths[{pos}] must be an object")
        expected_b_keys = {"block_length", "label", "status", "reason", "seed", "pairs"}
        if set(b_entry.keys()) != expected_b_keys:
            raise UncertaintyValidationError(f"block_lengths[{pos}] keys mismatch")
        if type(b_entry["block_length"]) is not int or b_entry["block_length"] != L:
            raise UncertaintyValidationError(f"block_lengths[{pos}] block_length must be {L}")
        if b_entry["label"] != BLOCK_LENGTH_LABELS[L]:
            raise UncertaintyValidationError(f"block_lengths[{pos}] label mismatch")
        if type(b_entry["seed"]) is not int or b_entry["seed"] != BLOCK_LENGTH_SEEDS[L]:
            raise UncertaintyValidationError(f"block_lengths[{pos}] seed mismatch")
        b_status = b_entry["status"]
        if b_status not in (UNCERTAINTY_STATUS_AVAILABLE, UNCERTAINTY_STATUS_UNAVAILABLE):
            raise UncertaintyValidationError(f"block_lengths[{pos}] status must be available or unavailable")
        b_reason = b_entry["reason"]
        if b_status == UNCERTAINTY_STATUS_AVAILABLE:
            if b_reason is not None:
                raise UncertaintyValidationError(f"block_lengths[{pos}] is available and must have reason None")
        elif type(b_reason) is not str or b_reason not in SUPPORTED_UNAVAILABLE_REASONS:
            raise UncertaintyValidationError(f"block_lengths[{pos}] needs a supported reason, got {b_reason!r}")

        pairs = b_entry["pairs"]
        if type(pairs) not in (list, tuple) or len(pairs) != len(ORDERED_PAIR_IDS):
            raise UncertaintyValidationError(f"block_lengths[{pos}].pairs must have {len(ORDERED_PAIR_IDS)} entries")
        for p_pos, pair_id in enumerate(ORDERED_PAIR_IDS):
            p_obj = pairs[p_pos]
            if type(p_obj) is not dict or set(p_obj.keys()) != {"pair_id", "lower", "upper"}:
                raise UncertaintyValidationError(f"block_lengths[{pos}].pairs[{p_pos}] format mismatch")
            if p_obj["pair_id"] != pair_id:
                raise UncertaintyValidationError(f"block_lengths[{pos}].pairs[{p_pos}] pair_id must be {pair_id}")
            lo = p_obj["lower"]
            hi = p_obj["upper"]
            if b_status == UNCERTAINTY_STATUS_AVAILABLE:
                if lo is None or hi is None:
                    raise UncertaintyValidationError(f"Available block length {L} pair {pair_id} must have non-None bounds")
                if not _is_finite_number(lo):
                    raise UncertaintyValidationError(f"Available bound must be finite float: {lo!r}")
                if not _is_finite_number(hi):
                    raise UncertaintyValidationError(f"Available bound must be finite float: {hi!r}")
                if lo < -2.0 or lo > 2.0 or hi < -2.0 or hi > 2.0:
                    raise UncertaintyValidationError(f"Interval bounds out of [-2, 2]: [{lo}, {hi}]")
                if lo > hi:
                    raise UncertaintyValidationError(f"Lower bound ({lo}) exceeds upper ({hi})")
            else:
                if lo is not None or hi is not None:
                    raise UncertaintyValidationError(f"Unavailable block length {L} pair {pair_id} must have None bounds")

    _validate_uncertainty_state(doc)


def _validate_uncertainty_state(doc: Mapping[str, Any]) -> None:
    """
    Relates the top state, the three length states, the points and the counts of a typed block.

    Endpoints are never compared with the point estimate: a percentile interval need not
    contain it. Whether the block matches its cohort is the artifact relation check's job.
    """
    n = doc["n"]
    span = doc["mature_span_count"]
    top_reason = doc["reason"]
    views = doc["block_lengths"]

    available_count = sum(1 for view in views if view["status"] == UNCERTAINTY_STATUS_AVAILABLE)
    if available_count == len(BLOCK_LENGTHS):
        expected_status = UNCERTAINTY_STATUS_AVAILABLE
    elif available_count > 0:
        expected_status = UNCERTAINTY_STATUS_PARTIALLY_AVAILABLE
    else:
        expected_status = UNCERTAINTY_STATUS_UNAVAILABLE
    if doc["status"] != expected_status:
        raise UncertaintyValidationError(f"Top status {doc['status']!r} contradicts {available_count} available lengths")

    if top_reason in COMMON_UNAVAILABLE_REASONS:
        for view in views:
            if view["reason"] != top_reason:
                raise UncertaintyValidationError(f"Length {view['block_length']} reason contradicts common reason {top_reason!r}")
    else:
        # Only a contiguous cohort reaches the floor, so n and the mature span are the same count
        if n == 0 or n != span:
            raise UncertaintyValidationError(f"Floor and available states need n == mature_span_count > 0, got {n} and {span}")
        cleared = available_block_lengths(n)
        for view in views:
            expected_reason = None if view["block_length"] in cleared else REASON_INSUFFICIENT_BLOCKS
            if view["reason"] != expected_reason:
                raise UncertaintyValidationError(f"Length {view['block_length']} state contradicts its floor at n={n}")

    if top_reason == REASON_EMPTY_COHORT and n != 0:
        raise UncertaintyValidationError(f"empty_cohort requires n == 0, got {n}")
    if top_reason == REASON_NON_CONTIGUOUS and not 0 < n < span:
        raise UncertaintyValidationError(f"non_contiguous_test_cohort requires 0 < n < mature_span_count, got {n} and {span}")
    if n > span:
        raise UncertaintyValidationError(f"n {n} exceeds mature_span_count {span}")

    no_point = top_reason in NO_POINT_REASONS
    for entry in doc["point_differences"]:
        if (entry["point_difference"] is None) != no_point:
            raise UncertaintyValidationError(f"{entry['pair_id']} point difference contradicts reason {top_reason!r}")
