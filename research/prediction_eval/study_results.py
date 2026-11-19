"""
Prediction Evaluation Study Results, Artifact Contracts, and Serialization.

Provides deterministic, inspectable, standard-library result containers,
strict JSON and Markdown serialization, closed result/summary/manifest schema
validation, completion manifest binding, and candidate release descriptor
verification for offline prediction studies.

Architectural ownership:
    study.py owns configuration, input-only admission, replay transport,
    and study orchestration.
    study_results.py owns immutable result DTOs, strict summary schema
    generation, report rendering, completion binding, and UI display-state
    evaluation.

Boundary:
    Operates strictly in memory with standard-library tools, except the explicit
    read-only verify_completed_run check of one run directory. Completely importable
    without scientific libraries (runs under python -E -B -S). Candidate display
    artifacts remain private until formal source-use and human content clearance.
    Hash consistency is not publisher authentication.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import datetime
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Set, Tuple, Union

from research.prediction_eval.features import (
    REASON_MISSING_VIX,
    REASON_WARMUP,
    VALID_REGIMES,
    WARMUP_ORIGIN_INDEX,
)
from research.prediction_eval.inputs import InputValidationError
from research.prediction_eval.metrics import (
    ComparisonMetrics,
    EvaluationOrigin,
    ModelMetrics,
    PROTOCOL_ID as METRICS_PROTOCOL_ID,
    ReliabilityBin,
    RowScore,
    STATUS_EMPTY as METRICS_STATUS_EMPTY,
    STATUS_SCORED as METRICS_STATUS_SCORED,
)
from research.prediction_eval.outcomes import (
    OUTCOME_CLASS_BEAR,
    OUTCOME_CLASS_BULL,
    OUTCOME_CLASS_NEUTRAL,
    VALID_OUTCOME_CLASSES,
)
from research.prediction_eval.splits import (
    REASON_LABEL_CROSSES_DEVELOPMENT,
    REASON_LABEL_CROSSES_TEST,
    REASON_UNKNOWN_OUTCOME,
)
from research.prediction_eval.uncertainty import (
    available_block_lengths,
    BLOCK_LENGTH_LABELS,
    BLOCK_LENGTH_SEEDS,
    BLOCK_LENGTHS,
    BOOTSTRAP_REPLICATES,
    common_unavailable_reason,
    HORIZON_SESSIONS,
    MAX_RESAMPLE_POSITIONS,
    NO_POINT_REASONS,
    NOMINAL_COVERAGE,
    ORDERED_PAIR_IDS,
    PAIR_HEURISTIC_MINUS_FREQUENCY,
    PAIR_HEURISTIC_MINUS_LOGISTIC,
    paired_loss_differences,
    parse_uncertainty_input,
    QUANTILE_RULE,
    REASON_INSUFFICIENT_BLOCKS,
    SCHEMA_VERSION_UNCERTAINTY_DIAGNOSTICS,
    SCHEMA_VERSION_UNCERTAINTY_INPUT,
    SUPPORTED_UNCERTAINTY_STATUSES,
    UNCERTAINTY_METHOD,
    UNCERTAINTY_PROTOCOL_ID,
    UNCERTAINTY_STATUS_AVAILABLE,
    UNCERTAINTY_STATUS_PARTIALLY_AVAILABLE,
    UNCERTAINTY_STATUS_UNAVAILABLE,
    UncertaintyRequest,
    UncertaintyResult,
    UncertaintyValidationError,
    validate_uncertainty_diagnostics_document,
    validate_uncertainty_result_document,
)

SCHEMA_VERSION_SUMMARY_V2: str = "nivesh-evaluation-summary-v2"
SCHEMA_VERSION_SUMMARY_V3: str = "nivesh-evaluation-summary-v3"

SCHEMA_VERSION_RUN_MANIFEST_V2: str = "nivesh-study-run-manifest-v2"
SCHEMA_VERSION_RUN_MANIFEST_V3: str = "nivesh-study-run-manifest-v3"

SCHEMA_VERSION_RELEASE_DESCRIPTOR: str = "nivesh-study-release-descriptor-v1"

SCHEMA_VERSION_RESULT_V2: str = "nivesh-study-result-v2"
SCHEMA_VERSION_RESULT_V3: str = "nivesh-study-result-v3"

SCHEMA_VERSION_FAILURE: str = "nivesh-study-failure-v1"

SCHEMA_VERSION_ADMISSION_V1: str = "nivesh-study-admission-v1"
SCHEMA_VERSION_ADMISSION_V2: str = "nivesh-study-admission-v2"
SCHEMA_VERSION_ADMISSION: str = SCHEMA_VERSION_ADMISSION_V1

SCHEMA_VERSION_APPROVAL_V1: str = "nivesh-historical-admission-v1"

# Configuration versions live here so the completed-run checker can relate config.json
# without importing study.py, which imports this module.
SCHEMA_VERSION_CONFIG_V2: str = "nivesh-study-config-v2"
SCHEMA_VERSION_CONFIG_V3: str = "nivesh-study-config-v3"

STUDY_PROTOCOL_ID: str = "nivesh-offline-study-v1"
OUTCOME_DEFINITION: str = "close-return-20-session-half-percent-neutral-inclusive-v1"

DATE_SELECTION_RULE: str = "calendar_only_fixed_before_outcomes"
DATE_SELECTION_RULE_HISTORICAL: str = "calendar_tail800_dev400_min2220_v1"
ADMISSION_POLICY: str = "nonzero_gaps_lead_to_unavailable_intervals"

# calendar_tail800_dev400_min2220_v1 on an admitted axis of N sessions: E=N-20, T=E-800, D=T-400.
# At the minimum N=2220 this gives D=1000, T=1400, E=2200, so D>=1000 holds for every admitted N.
HISTORICAL_MIN_SESSIONS: int = 2220
HISTORICAL_TEST_SPAN: int = 800
HISTORICAL_DEVELOPMENT_SPAN: int = 400


def historical_split_indices(session_count: int) -> Tuple[int, int, int]:
    """
    Returns (development_start_index, mature_test_start_index, mature_test_end_index).

    Pure arithmetic and the only definition of the historical rule. Each caller first checks
    HISTORICAL_MIN_SESSIONS against its own representation and keeps its own error contract.
    """
    end = session_count - HORIZON_SESSIONS
    test_start = end - HISTORICAL_TEST_SPAN
    return test_start - HISTORICAL_DEVELOPMENT_SPAN, test_start, end


# T at the minimum N. A portable v3 summary carries indices but not N, so it can check this bound.
HISTORICAL_MIN_TEST_START_INDEX: int = historical_split_indices(HISTORICAL_MIN_SESSIONS)[1]

# Absolute tolerance for a scored TEST point against the difference of its two stated TEST mean
# Briers. Both are means over the same n scored sessions: the scorer sums rows left to right
# (error at most about (n-1)*2**-53 * 2 per mean, Brier <= 2), and the point is an fsum of the
# row differences over n (a few ulps). The gap is below 4.5e-16 * n, so 1e-9 holds for any
# cohort under two million sessions while staying far below the 4-decimal display and any real
# signed disagreement. The private archive check keeps exact equality with the saved losses.
PAIRED_POINT_TOLERANCE: float = 1e-9
_PAIR_COMPARATORS: Dict[str, str] = {
    PAIR_HEURISTIC_MINUS_FREQUENCY: "frequency",
    PAIR_HEURISTIC_MINUS_LOGISTIC: "logistic",
}

# The scorer's accepted conservation rule and the three-class Brier ceiling: with every
# component in [0, 1], a row loses at most 1 on the actual class and 1 on one other class.
PROBABILITY_SUM_TOLERANCE: float = 1e-12
MAX_THREE_CLASS_BRIER: float = 2.0

# Support is declared here, never by whatever an untrusted descriptor or summary claims.
SUPPORTED_SUMMARY_SCHEMA_VERSIONS: frozenset = frozenset({SCHEMA_VERSION_SUMMARY_V2, SCHEMA_VERSION_SUMMARY_V3})
SUPPORTED_RESULT_SCHEMA_VERSIONS: frozenset = frozenset({SCHEMA_VERSION_RESULT_V2, SCHEMA_VERSION_RESULT_V3})
SUPPORTED_RUN_MANIFEST_SCHEMA_VERSIONS: frozenset = frozenset({SCHEMA_VERSION_RUN_MANIFEST_V2, SCHEMA_VERSION_RUN_MANIFEST_V3})
SUPPORTED_ADMISSION_SCHEMA_VERSIONS: frozenset = frozenset({SCHEMA_VERSION_ADMISSION_V1, SCHEMA_VERSION_ADMISSION_V2})
SUPPORTED_PROTOCOL_IDS: frozenset = frozenset({STUDY_PROTOCOL_ID})

DATA_KIND_SYNTHETIC: str = "synthetic"
DATA_KIND_HISTORICAL: str = "historical"
SUPPORTED_DATA_KINDS: frozenset = frozenset({DATA_KIND_SYNTHETIC, DATA_KIND_HISTORICAL})

DEVELOPMENT_STATUS_SYNTHETIC: str = "synthetic_development"
DEVELOPMENT_STATUS_HISTORICAL: str = "retrospective_historical_evaluation"
SUPPORTED_DEVELOPMENT_STATUSES: frozenset = frozenset({DEVELOPMENT_STATUS_SYNTHETIC, DEVELOPMENT_STATUS_HISTORICAL})

SOURCE_KIND_SYNTHETIC: str = "synthetic_fixture"
SOURCE_KIND_HISTORICAL: str = "admitted_historical_market_data"
SUPPORTED_SOURCE_KINDS: frozenset = frozenset({SOURCE_KIND_SYNTHETIC, SOURCE_KIND_HISTORICAL})

STATUS_SCORED: str = "scored"
STATUS_EMPTY: str = "empty"
STATUS_COMPARISON_UNAVAILABLE: str = "comparison_unavailable"

FORECAST_STATE_AVAILABLE: str = "available"
FORECAST_STATE_UNAVAILABLE: str = "unavailable"
SCORE_STATE_SCORED: str = "scored"
SCORE_STATE_UNSCORED: str = "unscored"

UI_STATE_UNAVAILABLE: str = "unavailable"
UI_STATE_ERROR: str = "error"
UI_STATE_UNSUPPORTED_VERSION: str = "unsupported_version"
UI_STATE_STALE: str = "stale"
UI_STATE_DISPLAYABLE: str = "displayable"

ORDERED_CLASSES: Tuple[str, ...] = (
    OUTCOME_CLASS_BEAR,
    OUTCOME_CLASS_NEUTRAL,
    OUTCOME_CLASS_BULL,
)

MODEL_NAMES: Tuple[str, ...] = ("heuristic", "frequency", "logistic")

EXCLUSION_REASONS: Tuple[str, ...] = (
    REASON_WARMUP,
    REASON_MISSING_VIX,
    REASON_UNKNOWN_OUTCOME,
    REASON_LABEL_CROSSES_DEVELOPMENT,
    REASON_LABEL_CROSSES_TEST,
)

EXPECTED_DIRECTIONS: Tuple[str, ...] = (
    "STRONGLY BULLISH",
    "MODERATELY BULLISH",
    "NEUTRAL / RANGE-BOUND",
    "MODERATELY BEARISH",
    "STRONGLY BEARISH",
)

FREQUENCY_UNAVAILABLE_REASONS: Tuple[str, ...] = ("no_fit_rows",)
LOGISTIC_UNAVAILABLE_REASONS: Tuple[str, ...] = (
    "no_fit_rows",
    "missing_training_classes",
    "not_converged",
    "nonfinite_model_state",
)
LOGISTIC_FAILURE_STAGES: Tuple[str, ...] = ("scaler", "fit", "prediction")

REQUIRED_SUMMARY_KEYS_V2: Set[str] = {
    "schema_version",
    "run_id",
    "study_id",
    "protocol_id",
    "data_kind",
    "development_status",
    "claim_label",
    "dataset_attribution",
    "replay_identity",
    "provenance_identity",
    "chronological_cutoffs",
    "admission_summary",
    "fixed_definitions",
    "partitions",
    "uncertainty",
    "limitations",
}
REQUIRED_SUMMARY_KEYS: Set[str] = REQUIRED_SUMMARY_KEYS_V2

REQUIRED_MANIFEST_ARTIFACTS_V2: Set[str] = {
    "config.json",
    "admission.json",
    "replay-request.json",
    "replay-response.json",
    "replay-stderr.log",
    "replay-invocation.json",
    "result.json",
    "predictions.json",
    "panel-summary.json",
    "report.md",
    "uncertainty-input.json",
    "uncertainty-diagnostics.json",
}
REQUIRED_MANIFEST_ARTIFACTS_V3: Set[str] = REQUIRED_MANIFEST_ARTIFACTS_V2 | {"historical-admission.json"}

# Every module a run measures. Kept here so provenance validators enforce the same closed set
# the configuration binds; study.py imports it, since this module cannot import study.py.
REQUIRED_SOURCE_MODULES: Tuple[str, ...] = (
    "research/prediction_eval/inputs.py",
    "research/prediction_eval/outcomes.py",
    "research/prediction_eval/features.py",
    "research/prediction_eval/splits.py",
    "research/prediction_eval/frequency.py",
    "research/prediction_eval/logistic.py",
    "research/prediction_eval/replay_export.py",
    "research/prediction_eval/metrics.py",
    "research/prediction_eval/study.py",
    "research/prediction_eval/study_results.py",
    "research/prediction_eval/uncertainty.py",
    "research/prediction_eval/replay.cjs",
    "research/prediction_eval/compile_replay.cjs",
)

# The configuration loader and the archived-run relations below enforce the same closed
# dependency set and fixed model pin; study.py imports both, keeping the import direction.
REQUIRED_DEPENDENCIES: Tuple[str, ...] = ("numpy", "scikit-learn", "scipy", "threadpoolctl")
EXPECTED_MODELS_SHA256: str = "87C4DB2A4EB3B40AE5F7499C977AB407FFE3C3BE367E4DAE8FD8AE1804F543CD"
# The runner's fixed build mode and replay timeout ceiling, shared the same way
EXPECTED_BUILD_MODE: str = "candidate"
MAX_REPLAY_TIMEOUT_SECONDS: int = 60
# The version pairs logistic.py records for every complete run, fitted or not
LOGISTIC_DEPENDENCY_NAMES: Tuple[str, ...] = ("numpy", "scikit-learn", "scipy")

REQUIRED_MANIFEST_KEYS_V2: Set[str] = {
    "schema_version",
    "run_id",
    "study_id",
    "protocol_id",
    "data_kind",
    "development_status",
    "coverage_start_date",
    "coverage_end_date",
    "summary_schema_version",
    "artifacts",
    "config_identity",
    "admission_identity",
    "input_identities",
    "source_identities",
    "runtime_identities",
    "model_identity",
    "build_identity",
    "completed",
    "completion_timestamp",
}
REQUIRED_MANIFEST_KEYS_V3: Set[str] = REQUIRED_MANIFEST_KEYS_V2 | {"approval_identity"}

REQUIRED_RESULT_KEYS_V2: Set[str] = {
    "schema_version",
    "run_id",
    "study_id",
    "protocol_id",
    "data_kind",
    "development_status",
    "claim_label",
    "coverage_start_date",
    "coverage_end_date",
    "development_start",
    "test_start",
    "admission",
    "config_identity",
    "admission_identity",
    "input_identities",
    "source_identities",
    "runtime_identities",
    "model_identity",
    "build_identity",
    "replay_identity",
    "private_paths",
    "comparator_metadata",
    "partitions",
    "warnings",
    "input_warnings",
    "uncertainty",
    "limitations",
}
REQUIRED_RESULT_KEYS_V3: Set[str] = REQUIRED_RESULT_KEYS_V2 | {"approval_identity"}

REQUIRED_APPROVAL_KEYS: Set[str] = {
    "schema_version",
    "decision_id",
    "approved_by",
    "approved_at",
    "decision",
    "config_identity",
    "admission_identity",
    "source_use_evidence",
    "calendar_evidence",
    "public_sharing_status",
    "raw_file_hash_release",
}

PRIVATE_INPUT_ROLE_KEYS: Tuple[str, ...] = ("units", "source_kind", "files")
PRIVATE_PROVENANCE_FILE_KEYS: Tuple[str, ...] = (
    "path",
    "raw_byte_count",
    "sha256",
    "record_count",
    "observed_first_date",
    "observed_last_date",
    "source_url",
    "requested_interval",
    "acquisition_time",
    "source_use_note",
)

REPLAY_EVIDENCE_ARTIFACTS: Tuple[str, ...] = (
    "replay-request.json",
    "replay-response.json",
    "replay-stderr.log",
    "replay-invocation.json",
)
SEMANTIC_RELATION_ARTIFACTS_V2: Tuple[str, ...] = (
    "uncertainty-input.json",
    "uncertainty-diagnostics.json",
    "result.json",
    "predictions.json",
    "panel-summary.json",
    "admission.json",
    "config.json",
) + REPLAY_EVIDENCE_ARTIFACTS

# Every key run_replay_adapter writes into a receipt, launched or not
REPLAY_RECEIPT_KEYS: Set[str] = {
    "attempt",
    "exe",
    "argv",
    "cwd",
    "shell",
    "start_utc",
    "timeout_seconds",
    "request",
    "declared_environment",
    "end_utc",
    "duration_seconds",
    "timed_out",
    "immediate_child_exit",
    "launch_state",
    "launch_error",
    "capture_state",
    "capture_error",
    "stdout",
    "stderr",
}
SEMANTIC_RELATION_ARTIFACTS_V3: Tuple[str, ...] = SEMANTIC_RELATION_ARTIFACTS_V2 + ("historical-admission.json",)

SYNTHETIC_LIMITATIONS: Tuple[str, ...] = (
    "Retrospective evaluation of frozen heuristic with empty events; not historically issued forecasts.",
    "Observation time is end-of-day after supplied session data; does not establish trade execution.",
    "Synthetic evaluation data; results cannot establish forecast accuracy on live market data.",
    "Stationary bootstrap intervals condition on frozen models and protocol; marginal views under approximate stationarity without refitting uncertainty or coverage guarantees.",
)

HISTORICAL_LIMITATIONS: Tuple[str, ...] = (
    "Retrospective evaluation of frozen heuristic with empty events; not historically issued forecasts.",
    "Observation time is end-of-day after supplied session data; does not establish trade execution.",
    "Admitted historical market data; results cannot establish live trading returns or stationarity guarantees.",
    "Stationary bootstrap intervals condition on frozen models and protocol; marginal views under approximate stationarity without refitting uncertainty or coverage guarantees.",
    "No forecast accuracy guarantee: metrics describe this retrospective sample only, not future performance.",
    "The test window is not an untouched holdout: the frozen heuristic, features and protocol were designed with access to historical market behavior.",
)

FAILURE_RECORD_NAME: str = "failure-diagnostics.json"

_SHA256_HEX_REGEX = re.compile(r"\A[0-9A-Fa-f]{64}\Z")
_IDENTIFIER_REGEX = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_ISO_DATE_REGEX = re.compile(r"\A[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_ARTIFACT_NAME_REGEX = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]*\Z")


def _reject_duplicate_keys(pairs: List[Tuple[str, Any]]) -> Dict[str, Any]:
    """Custom object_pairs_hook for json.loads that rejects duplicate keys."""
    d: Dict[str, Any] = {}
    for k, v in pairs:
        if k in d:
            raise ValueError(f"Duplicate JSON key: {k!r}")
        d[k] = v
    return d


def _reject_constant(token: str) -> None:
    """Rejects non-finite constants like NaN, Infinity, -Infinity in strict JSON."""
    raise ValueError(f"Non-finite JSON token not allowed in strict JSON: {token!r}")


def _finite_float(token: str) -> float:
    """Parses a JSON real, rejecting literals such as 1e999 that overflow to infinity."""
    value = float(token)
    if not math.isfinite(value):
        raise ValueError(f"Non-finite JSON number not allowed in strict JSON: {token!r}")
    return value


def parse_strict_json(json_text: str) -> Any:
    """Parses JSON text rejecting duplicate keys, NaN, Infinity and overflowing reals."""
    try:
        return json.loads(
            json_text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
    except Exception as exc:
        raise ValueError(f"Strict JSON parse error: {exc}") from exc


def parse_strict_json_bytes(raw: bytes) -> Any:
    """Parses exact bytes as strict UTF-8 JSON; the buffer is never reserialized."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"Strict JSON is not valid UTF-8: {exc}") from exc
    return parse_strict_json(text)


def is_valid_identifier(value: Any) -> bool:
    """True for a bounded portable identifier (run_id or study_id)."""
    return type(value) is str and _IDENTIFIER_REGEX.match(value) is not None


def _fail(path: str, message: str) -> None:
    raise ValueError(f"{path}: {message}")


def _require_mapping(value: Any, keys: Set[str], path: str) -> Dict[str, Any]:
    """Requires a JSON object with exactly the declared keys."""
    if type(value) is not dict:
        _fail(path, f"expected object, got {type(value).__name__}")
    if set(value.keys()) != keys:
        missing = sorted(keys - set(value.keys()))
        extra = sorted(set(value.keys()) - keys)
        _fail(path, f"key mismatch; missing={missing}, unknown={extra}")
    return value


def _require_int(value: Any, path: str, minimum: int = 0) -> int:
    if type(value) is not int:
        _fail(path, f"expected non-boolean integer, got {value!r}")
    if value < minimum:
        _fail(path, f"expected integer >= {minimum}, got {value}")
    return value


def _require_str(value: Any, path: str, *, allow_empty: bool = False) -> str:
    if type(value) is not str or (not allow_empty and not value):
        _fail(path, f"expected non-empty string, got {value!r}")
    return value


def _require_optional_str(value: Any, path: str) -> Optional[str]:
    if value is None:
        return None
    return _require_str(value, path)


def _require_number(value: Any, path: str) -> float:
    """Requires a finite non-boolean JSON number; 0 and 0.0 are both valid."""
    if type(value) not in (int, float):
        _fail(path, f"expected finite number, got {type(value).__name__}")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        # An integer beyond binary64 range must stay a schema error, not a raw arithmetic one
        finite = False
    if not finite:
        _fail(path, "expected finite number")
    return value


def _require_sha(value: Any, path: str) -> str:
    if type(value) is not str or _SHA256_HEX_REGEX.match(value) is None:
        _fail(path, f"expected 64-hex SHA-256, got {value!r}")
    return value


def _require_date(value: Any, path: str) -> str:
    if type(value) is not str or _ISO_DATE_REGEX.match(value) is None:
        _fail(path, f"expected ISO date, got {value!r}")
    try:
        datetime.date.fromisoformat(value)
    except ValueError as exc:
        _fail(path, f"invalid date {value!r}: {exc}")
    return value


def _require_enum(value: Any, allowed: Sequence[str], path: str) -> str:
    if type(value) is not str or value not in allowed:
        _fail(path, f"expected one of {list(allowed)}, got {value!r}")
    return value


def _require_identifier(value: Any, path: str) -> str:
    if not is_valid_identifier(value):
        _fail(path, f"expected portable identifier, got {value!r}")
    return value


def _require_list(value: Any, path: str, length: Optional[int] = None) -> List[Any]:
    if type(value) is not list:
        _fail(path, f"expected array, got {type(value).__name__}")
    if length is not None and len(value) != length:
        _fail(path, f"expected {length} entries, got {len(value)}")
    return value


def _require_fraction(value: Any, path: str) -> float:
    """Requires a finite number in [0, 1]; signed zero is in range."""
    number = _require_number(value, path)
    if not 0.0 <= number <= 1.0:
        _fail(path, f"expected a value in [0, 1], got {number!r}")
    return number


def _require_loss(value: Any, path: str, maximum: Optional[float] = None) -> float:
    """Requires a nonnegative finite loss. Log loss has no ceiling: tiny positives stay valid."""
    number = _require_number(value, path)
    if number < 0.0 or (maximum is not None and number > maximum):
        _fail(path, f"loss out of range: {number!r}")
    return number


def _require_stated_rate(value: float, numerator: int, denominator: int, path: str) -> None:
    """A stated rate must agree with the counts beside it. This relates fields; it rescores nothing."""
    if abs(value - numerator / denominator) > PROBABILITY_SUM_TOLERANCE:
        _fail(path, f"rate {value!r} contradicts counts {numerator}/{denominator}")


def _require_probability_vector(value: Any, path: str) -> None:
    _require_list(value, path, 3)
    for idx, p in enumerate(value):
        _require_fraction(p, f"{path}[{idx}]")
    if abs(math.fsum(value) - 1.0) > PROBABILITY_SUM_TOLERANCE:
        _fail(path, f"probabilities must sum to 1 within {PROBABILITY_SUM_TOLERANCE}")


def _require_increasing_indices(value: Any, path: str) -> None:
    _require_list(value, path)
    previous = -1
    for idx, item in enumerate(value):
        _require_int(item, f"{path}[{idx}]")
        if item <= previous:
            _fail(f"{path}[{idx}]", "indices must strictly increase")
        previous = item


def validate_file_identity(value: Any, path: str) -> None:
    """Validates a path-free {raw_byte_count, sha256} identity."""
    doc = _require_mapping(value, {"raw_byte_count", "sha256"}, path)
    _require_int(doc["raw_byte_count"], f"{path}.raw_byte_count")
    _require_sha(doc["sha256"], f"{path}.sha256")


def _validate_file_provenance_counts(entry: Mapping[str, Any], label: str) -> None:
    """Persisted byte, hash, record-count and observed-date fields of one input file."""
    _require_int(entry["raw_byte_count"], f"{label}.raw_byte_count")
    _require_sha(entry["sha256"], f"{label}.sha256")
    _require_int(entry["record_count"], f"{label}.record_count", 1)
    _require_date(entry["observed_first_date"], f"{label}.observed_first_date")
    _require_date(entry["observed_last_date"], f"{label}.observed_last_date")


def _validate_file_provenance_source(entry: Mapping[str, Any], label: str) -> None:
    """Persisted caller-declared source fields of one input file."""
    _require_optional_str(entry["source_url"], f"{label}.source_url")
    interval = entry["requested_interval"]
    if interval is not None:
        _require_list(interval, f"{label}.requested_interval", 2)
        _require_date(interval[0], f"{label}.requested_interval[0]")
        _require_date(interval[1], f"{label}.requested_interval[1]")
    _require_optional_str(entry["acquisition_time"], f"{label}.acquisition_time")
    _require_str(entry["source_use_note"], f"{label}.source_use_note")


def validate_input_identities(value: Any, path: str, is_historical: Optional[bool] = None) -> None:
    doc = _require_mapping(value, {"nifty", "vix", "calendar"}, path)
    if is_historical is None:
        is_historical = type(doc.get("nifty")) is dict and "files" in doc["nifty"]

    if is_historical:
        for role in ("nifty", "vix"):
            role_entry = _require_mapping(doc[role], set(PRIVATE_INPUT_ROLE_KEYS), f"{path}.{role}")
            _require_str(role_entry["units"], f"{path}.{role}.units")
            _require_enum(role_entry["source_kind"], (SOURCE_KIND_HISTORICAL,), f"{path}.{role}.source_kind")
            files_list = _require_list(role_entry["files"], f"{path}.{role}.files")
            if not files_list:
                _fail(f"{path}.{role}.files", "expected non-empty files list")
            for idx, file_item in enumerate(files_list):
                file_path_label = f"{path}.{role}.files[{idx}]"
                entry = _require_mapping(file_item, set(PRIVATE_PROVENANCE_FILE_KEYS), file_path_label)
                _require_str(entry["path"], f"{file_path_label}.path")
                _validate_file_provenance_counts(entry, file_path_label)
                _validate_file_provenance_source(entry, file_path_label)
    else:
        series_keys = {
            "raw_byte_count",
            "sha256",
            "record_count",
            "observed_first_date",
            "observed_last_date",
            "units",
            "source_kind",
            "source_url",
            "requested_interval",
            "acquisition_time",
            "source_use_note",
        }
        for role in ("nifty", "vix"):
            entry = _require_mapping(doc[role], series_keys, f"{path}.{role}")
            _validate_file_provenance_counts(entry, f"{path}.{role}")
            _require_str(entry["units"], f"{path}.{role}.units")
            _require_enum(entry["source_kind"], (SOURCE_KIND_SYNTHETIC,), f"{path}.{role}.source_kind")
            _validate_file_provenance_source(entry, f"{path}.{role}")

    calendar = _require_mapping(doc["calendar"], {"raw_byte_count", "sha256", "session_count"}, f"{path}.calendar")
    _require_int(calendar["raw_byte_count"], f"{path}.calendar.raw_byte_count")
    _require_sha(calendar["sha256"], f"{path}.calendar.sha256")
    _require_int(calendar["session_count"], f"{path}.calendar.session_count", 1)


def validate_source_identities(value: Any, path: str) -> None:
    if type(value) is not dict or not value:
        _fail(path, "expected non-empty object")
    for rel_path, entry in value.items():
        if type(rel_path) is not str or rel_path.startswith(("/", "\\")) or ":" in rel_path or ".." in rel_path:
            _fail(path, f"source identity key must be a relative path, got {rel_path!r}")
        validate_file_identity(entry, f"{path}[{rel_path}]")
    if set(value.keys()) != set(REQUIRED_SOURCE_MODULES):
        missing = sorted(set(REQUIRED_SOURCE_MODULES) - set(value.keys()))
        extra = sorted(set(value.keys()) - set(REQUIRED_SOURCE_MODULES))
        _fail(path, f"source identities must be the required closed set; missing={missing}, unknown={extra}")


def validate_runtime_identities(value: Any, path: str) -> None:
    doc = _require_mapping(
        value,
        {
            "python_version",
            "python_implementation",
            "python_executable",
            "platform",
            "node_version",
            "node_executable",
            "dependency_versions",
        },
        path,
    )
    _require_str(doc["python_version"], f"{path}.python_version")
    _require_str(doc["python_implementation"], f"{path}.python_implementation")
    validate_file_identity(doc["python_executable"], f"{path}.python_executable")
    _require_str(doc["platform"], f"{path}.platform")
    _require_str(doc["node_version"], f"{path}.node_version")
    validate_file_identity(doc["node_executable"], f"{path}.node_executable")
    deps = doc["dependency_versions"]
    if type(deps) is not dict or not deps:
        _fail(f"{path}.dependency_versions", "expected non-empty object")
    for name, version in deps.items():
        _require_str(version, f"{path}.dependency_versions[{name}]")


def validate_model_identity(value: Any, path: str) -> None:
    doc = _require_mapping(value, {"path", "raw_byte_count", "sha256", "platt_params"}, path)
    _require_str(doc["path"], f"{path}.path")
    _require_int(doc["raw_byte_count"], f"{path}.raw_byte_count")
    _require_sha(doc["sha256"], f"{path}.sha256")
    params = _require_list(doc["platt_params"], f"{path}.platt_params", 2)
    for idx, item in enumerate(params):
        _require_number(item, f"{path}.platt_params[{idx}]")


def validate_build_identity(value: Any, path: str) -> None:
    doc = _require_mapping(value, {"raw_byte_count", "sha256", "mode", "calculation_id", "compiler_exit"}, path)
    _require_int(doc["raw_byte_count"], f"{path}.raw_byte_count")
    _require_sha(doc["sha256"], f"{path}.sha256")
    _require_str(doc["mode"], f"{path}.mode")
    _require_str(doc["calculation_id"], f"{path}.calculation_id")
    if type(doc["compiler_exit"]) is not int or doc["compiler_exit"] != 0:
        _fail(f"{path}.compiler_exit", f"expected integer 0, got {doc['compiler_exit']!r}")


def validate_replay_identity(value: Any, path: str) -> None:
    doc = _require_mapping(
        value,
        {"claim_label", "script", "request", "response", "model_sha256", "build_manifest_sha256", "calculation_id"},
        path,
    )
    _require_str(doc["claim_label"], f"{path}.claim_label")
    validate_file_identity(doc["script"], f"{path}.script")
    validate_file_identity(doc["request"], f"{path}.request")
    validate_file_identity(doc["response"], f"{path}.response")
    _require_sha(doc["model_sha256"], f"{path}.model_sha256")
    _require_sha(doc["build_manifest_sha256"], f"{path}.build_manifest_sha256")
    _require_str(doc["calculation_id"], f"{path}.calculation_id")


def validate_admission_summary(value: Any, path: str) -> None:
    doc = _require_mapping(
        value,
        {
            "mature_test_start_index",
            "mature_test_end_index",
            "mature_test_span_count",
            "warmup_gap_count",
            "missing_vix_gap_count",
            "union_gap_count",
            "gap_digest",
            "policy",
        },
        path,
    )
    start = _require_int(doc["mature_test_start_index"], f"{path}.mature_test_start_index")
    end = _require_int(doc["mature_test_end_index"], f"{path}.mature_test_end_index")
    span = _require_int(doc["mature_test_span_count"], f"{path}.mature_test_span_count")
    if end < start or span != end - start:
        _fail(path, "mature span does not match its bounds")
    warmup = _require_int(doc["warmup_gap_count"], f"{path}.warmup_gap_count")
    missing = _require_int(doc["missing_vix_gap_count"], f"{path}.missing_vix_gap_count")
    union = _require_int(doc["union_gap_count"], f"{path}.union_gap_count")
    if union > span or union < max(warmup, missing) or union > warmup + missing:
        _fail(path, "gap union is inconsistent with its reason counts")
    _require_sha(doc["gap_digest"], f"{path}.gap_digest")
    _require_str(doc["policy"], f"{path}.policy")


def _require_gap_positions(value: Any, count: int, start: int, end: int, path: str) -> None:
    _require_increasing_indices(value, path)
    if len(value) != count:
        _fail(path, f"expected {count} positions, got {len(value)}")
    if value and (value[0] < start or value[-1] >= end):
        _fail(path, f"positions must stay inside the mature span [{start}, {end})")


def validate_approval_document(value: Any, path: str = "approval") -> None:
    """Closed native-type validation of the private human approval record (nivesh-historical-admission-v1)."""
    doc = _require_mapping(value, REQUIRED_APPROVAL_KEYS, path)
    if doc["schema_version"] != SCHEMA_VERSION_APPROVAL_V1:
        _fail(f"{path}.schema_version", f"unsupported approval schema {doc['schema_version']!r}; expected {SCHEMA_VERSION_APPROVAL_V1!r}")
    _require_identifier(doc["decision_id"], f"{path}.decision_id")
    _require_str(doc["approved_by"], f"{path}.approved_by")
    _require_str(doc["approved_at"], f"{path}.approved_at")
    try:
        datetime.datetime.fromisoformat(doc["approved_at"])
    except ValueError as exc:
        _fail(f"{path}.approved_at", f"approved_at must be an ISO-format datetime: {exc}")
    _require_enum(doc["decision"], ("APPROVED_FOR_ONE_PRIVATE_STUDY",), f"{path}.decision")
    _require_enum(doc["public_sharing_status"], ("NOT_CLEARED",), f"{path}.public_sharing_status")
    _require_enum(doc["raw_file_hash_release"], ("WITHHELD",), f"{path}.raw_file_hash_release")

    for id_key in ("config_identity", "admission_identity"):
        id_doc = _require_mapping(doc[id_key], {"raw_byte_count", "sha256"}, f"{path}.{id_key}")
        _require_int(id_doc["raw_byte_count"], f"{path}.{id_key}.raw_byte_count", 1)
        _require_sha(id_doc["sha256"], f"{path}.{id_key}.sha256")

    source_use = _require_list(doc["source_use_evidence"], f"{path}.source_use_evidence")
    if not source_use:
        _fail(f"{path}.source_use_evidence", "source_use_evidence must not be empty")
    for idx, item in enumerate(source_use):
        item_path = f"{path}.source_use_evidence[{idx}]"
        entry = _require_mapping(item, {"input_refs", "evidence", "note"}, item_path)
        refs = _require_list(entry["input_refs"], f"{item_path}.input_refs")
        if not refs:
            _fail(f"{item_path}.input_refs", "input_refs must not be empty")
        for r_idx, ref in enumerate(refs):
            ref_path = f"{item_path}.input_refs[{r_idx}]"
            r_doc = _require_mapping(ref, {"role", "file_index"}, ref_path)
            _require_enum(r_doc["role"], ("nifty", "vix"), f"{ref_path}.role")
            f_idx = r_doc["file_index"]
            if type(f_idx) is not int or type(f_idx) is bool or f_idx < 0:
                _fail(f"{ref_path}.file_index", f"file_index must be non-boolean int >= 0, got {f_idx!r}")
        ev_list = _require_list(entry["evidence"], f"{item_path}.evidence")
        if not ev_list:
            _fail(f"{item_path}.evidence", "evidence list must not be empty")
        for e_idx, ev in enumerate(ev_list):
            ev_path = f"{item_path}.evidence[{e_idx}]"
            ev_doc = _require_mapping(ev, {"path", "raw_byte_count", "sha256"}, ev_path)
            _require_str(ev_doc["path"], f"{ev_path}.path")
            _require_int(ev_doc["raw_byte_count"], f"{ev_path}.raw_byte_count", 1)
            _require_sha(ev_doc["sha256"], f"{ev_path}.sha256")
        _require_str(entry["note"], f"{item_path}.note")

    cal_ev = _require_mapping(doc["calendar_evidence"], {"evidence", "independent_source_note"}, f"{path}.calendar_evidence")
    cal_list = _require_list(cal_ev["evidence"], f"{path}.calendar_evidence.evidence")
    if not cal_list:
        _fail(f"{path}.calendar_evidence.evidence", "calendar_evidence evidence must not be empty")
    for c_idx, cev in enumerate(cal_list):
        cev_path = f"{path}.calendar_evidence.evidence[{c_idx}]"
        cev_doc = _require_mapping(cev, {"path", "raw_byte_count", "sha256"}, cev_path)
        _require_str(cev_doc["path"], f"{cev_path}.path")
        _require_int(cev_doc["raw_byte_count"], f"{cev_path}.raw_byte_count", 1)
        _require_sha(cev_doc["sha256"], f"{cev_path}.sha256")
    _require_str(cal_ev["independent_source_note"], f"{path}.calendar_evidence.independent_source_note")


def validate_admission_document(value: Any, path: str = "admission") -> None:
    """
    Closed native-type validation of the complete frozen admission record.

    Supports synthetic v1 (nivesh-study-admission-v1) and historical v2 (nivesh-study-admission-v2).
    """
    if type(value) is not dict:
        _fail(path, "expected object")
    ver = value.get("schema_version")
    if ver == SCHEMA_VERSION_ADMISSION_V2:
        doc = _require_mapping(
            value,
            {
                "schema_version",
                "data_kind",
                "protocol_id",
                "date_selection_rule",
                "development_start",
                "test_start",
                "development_start_index",
                "inputs",
                "axis",
                "mature_test_start_index",
                "mature_test_end_index",
                "mature_test_span_count",
                "warmup_gap_positions",
                "warmup_gap_count",
                "missing_vix_gap_positions",
                "missing_vix_gap_count",
                "union_gap_positions",
                "union_gap_count",
                "gap_digest",
                "policy",
            },
            path,
        )
        _require_enum(doc["schema_version"], (SCHEMA_VERSION_ADMISSION_V2,), f"{path}.schema_version")
        _require_enum(doc["data_kind"], (DATA_KIND_HISTORICAL,), f"{path}.data_kind")
        _require_enum(doc["protocol_id"], sorted(SUPPORTED_PROTOCOL_IDS), f"{path}.protocol_id")
        _require_enum(doc["date_selection_rule"], (DATE_SELECTION_RULE_HISTORICAL,), f"{path}.date_selection_rule")
        _require_enum(doc["policy"], (ADMISSION_POLICY,), f"{path}.policy")
        development_start = _require_date(doc["development_start"], f"{path}.development_start")
        test_start = _require_date(doc["test_start"], f"{path}.test_start")
        if development_start >= test_start:
            _fail(path, "development_start must precede test_start")

        inputs = _require_mapping(doc["inputs"], {"nifty", "vix", "calendar"}, f"{path}.inputs")
        for role in ("nifty", "vix"):
            role_entry = _require_mapping(
                inputs[role],
                {"files", "record_count", "observed_first_date", "observed_last_date"},
                f"{path}.inputs.{role}",
            )
            _require_int(role_entry["record_count"], f"{path}.inputs.{role}.record_count", 1)
            _require_date(role_entry["observed_first_date"], f"{path}.inputs.{role}.observed_first_date")
            _require_date(role_entry["observed_last_date"], f"{path}.inputs.{role}.observed_last_date")
            files_list = _require_list(role_entry["files"], f"{path}.inputs.{role}.files")
            if not files_list:
                _fail(f"{path}.inputs.{role}.files", "files list must not be empty")
            for idx, item in enumerate(files_list):
                entry = _require_mapping(
                    item,
                    {"raw_byte_count", "sha256", "record_count", "observed_first_date", "observed_last_date"},
                    f"{path}.inputs.{role}.files[{idx}]",
                )
                _require_int(entry["raw_byte_count"], f"{path}.inputs.{role}.files[{idx}].raw_byte_count")
                _require_sha(entry["sha256"], f"{path}.inputs.{role}.files[{idx}].sha256")
                _require_int(entry["record_count"], f"{path}.inputs.{role}.files[{idx}].record_count", 1)
                _require_date(entry["observed_first_date"], f"{path}.inputs.{role}.files[{idx}].observed_first_date")
                _require_date(entry["observed_last_date"], f"{path}.inputs.{role}.files[{idx}].observed_last_date")

        calendar = _require_mapping(inputs["calendar"], {"raw_byte_count", "sha256", "session_count"}, f"{path}.inputs.calendar")
        _require_int(calendar["raw_byte_count"], f"{path}.inputs.calendar.raw_byte_count")
        _require_sha(calendar["sha256"], f"{path}.inputs.calendar.sha256")
        _require_int(calendar["session_count"], f"{path}.inputs.calendar.session_count", 1)

        axis = _require_mapping(doc["axis"], {"session_count", "first_date", "last_date"}, f"{path}.axis")
        session_count = _require_int(axis["session_count"], f"{path}.axis.session_count", 1)
        if _require_date(axis["first_date"], f"{path}.axis.first_date") > _require_date(axis["last_date"], f"{path}.axis.last_date"):
            _fail(f"{path}.axis", "axis dates are inverted")

        if session_count < HISTORICAL_MIN_SESSIONS:
            _fail(path, f"historical session_count must be at least {HISTORICAL_MIN_SESSIONS}, got {session_count}")
        exp_d, exp_t, exp_e = historical_split_indices(session_count)

        d_idx = _require_int(doc["development_start_index"], f"{path}.development_start_index")
        if d_idx != exp_d:
            _fail(f"{path}.development_start_index", f"expected {exp_d}, got {d_idx}")

        start = _require_int(doc["mature_test_start_index"], f"{path}.mature_test_start_index")
        if start != exp_t:
            _fail(f"{path}.mature_test_start_index", f"expected {exp_t}, got {start}")

        end = _require_int(doc["mature_test_end_index"], f"{path}.mature_test_end_index")
        if end != exp_e:
            _fail(f"{path}.mature_test_end_index", f"expected {exp_e}, got {end}")

        span = _require_int(doc["mature_test_span_count"], f"{path}.mature_test_span_count")
        if span != HISTORICAL_TEST_SPAN or span != end - start:
            _fail(path, f"mature span count must be exactly {HISTORICAL_TEST_SPAN} and match end - start")

    else:
        doc = _require_mapping(
            value,
            {
                "schema_version",
                "data_kind",
                "protocol_id",
                "date_selection_rule",
                "development_start",
                "test_start",
                "inputs",
                "axis",
                "mature_test_start_index",
                "mature_test_end_index",
                "mature_test_span_count",
                "warmup_gap_positions",
                "warmup_gap_count",
                "missing_vix_gap_positions",
                "missing_vix_gap_count",
                "union_gap_positions",
                "union_gap_count",
                "gap_digest",
                "policy",
            },
            path,
        )
        _require_enum(doc["schema_version"], (SCHEMA_VERSION_ADMISSION_V1,), f"{path}.schema_version")
        _require_enum(doc["data_kind"], (DATA_KIND_SYNTHETIC,), f"{path}.data_kind")
        _require_enum(doc["protocol_id"], sorted(SUPPORTED_PROTOCOL_IDS), f"{path}.protocol_id")
        _require_enum(doc["date_selection_rule"], (DATE_SELECTION_RULE,), f"{path}.date_selection_rule")
        _require_enum(doc["policy"], (ADMISSION_POLICY,), f"{path}.policy")
        development_start = _require_date(doc["development_start"], f"{path}.development_start")
        test_start = _require_date(doc["test_start"], f"{path}.test_start")
        if development_start >= test_start:
            _fail(path, "development_start must precede test_start")

        inputs = _require_mapping(doc["inputs"], {"nifty", "vix", "calendar"}, f"{path}.inputs")
        for role in ("nifty", "vix"):
            entry = _require_mapping(inputs[role], {"raw_byte_count", "sha256", "record_count"}, f"{path}.inputs.{role}")
            _require_int(entry["raw_byte_count"], f"{path}.inputs.{role}.raw_byte_count")
            _require_sha(entry["sha256"], f"{path}.inputs.{role}.sha256")
            _require_int(entry["record_count"], f"{path}.inputs.{role}.record_count", 1)
        calendar = _require_mapping(inputs["calendar"], {"raw_byte_count", "sha256", "session_count"}, f"{path}.inputs.calendar")
        _require_int(calendar["raw_byte_count"], f"{path}.inputs.calendar.raw_byte_count")
        _require_sha(calendar["sha256"], f"{path}.inputs.calendar.sha256")
        _require_int(calendar["session_count"], f"{path}.inputs.calendar.session_count", 1)

        axis = _require_mapping(doc["axis"], {"session_count", "first_date", "last_date"}, f"{path}.axis")
        session_count = _require_int(axis["session_count"], f"{path}.axis.session_count", 1)
        if _require_date(axis["first_date"], f"{path}.axis.first_date") > _require_date(axis["last_date"], f"{path}.axis.last_date"):
            _fail(f"{path}.axis", "axis dates are inverted")

        start = _require_int(doc["mature_test_start_index"], f"{path}.mature_test_start_index")
        end = _require_int(doc["mature_test_end_index"], f"{path}.mature_test_end_index")
        span = _require_int(doc["mature_test_span_count"], f"{path}.mature_test_span_count")
        if end < start or span != end - start or end > session_count:
            _fail(path, "mature span does not match its bounds")

    warmup_count = _require_int(doc["warmup_gap_count"], f"{path}.warmup_gap_count")
    missing_count = _require_int(doc["missing_vix_gap_count"], f"{path}.missing_vix_gap_count")
    union_count = _require_int(doc["union_gap_count"], f"{path}.union_gap_count")
    _require_gap_positions(doc["warmup_gap_positions"], warmup_count, start, end, f"{path}.warmup_gap_positions")
    _require_gap_positions(doc["missing_vix_gap_positions"], missing_count, start, end, f"{path}.missing_vix_gap_positions")
    _require_gap_positions(doc["union_gap_positions"], union_count, start, end, f"{path}.union_gap_positions")
    if doc["union_gap_positions"] != sorted(set(doc["warmup_gap_positions"]) | set(doc["missing_vix_gap_positions"])):
        _fail(f"{path}.union_gap_positions", "union must be exactly the reason positions")
    _require_sha(doc["gap_digest"], f"{path}.gap_digest")


def validate_input_warning(value: Any, path: str) -> None:
    """Closed validation of one retained loader InputWarning; an empty raw value is real data."""
    doc = _require_mapping(value, {"file_path", "line", "field", "message", "raw_value"}, path)
    for key in ("file_path", "line", "field", "message"):
        _require_str(doc[key], f"{path}.{key}")
    if doc["raw_value"] is not None:
        _require_str(doc["raw_value"], f"{path}.raw_value", allow_empty=True)


def _validate_counts_document(value: Any, path: str) -> None:
    doc = _require_mapping(
        value,
        {
            "raw_partition_count",
            "eligible_count",
            "excluded_count",
            "requested_count",
            "exclusion_reason_counts",
            "model_available_counts",
        },
        path,
    )
    raw = _require_int(doc["raw_partition_count"], f"{path}.raw_partition_count")
    eligible = _require_int(doc["eligible_count"], f"{path}.eligible_count")
    excluded = _require_int(doc["excluded_count"], f"{path}.excluded_count")
    requested = _require_int(doc["requested_count"], f"{path}.requested_count")
    if excluded != raw - eligible:
        _fail(path, "excluded_count must equal raw_partition_count - eligible_count")
    if requested != eligible:
        _fail(path, "requested_count must equal eligible_count for canonical comparator targets")
    reasons = doc["exclusion_reason_counts"]
    if type(reasons) is not dict:
        _fail(f"{path}.exclusion_reason_counts", "expected object")
    for reason, count in reasons.items():
        _require_enum(reason, EXCLUSION_REASONS, f"{path}.exclusion_reason_counts key")
        _require_int(count, f"{path}.exclusion_reason_counts[{reason}]", 1)
        if count > excluded:
            _fail(path, f"reason {reason} count exceeds unique exclusions")
    # Reasons can overlap on one origin, so their sum may exceed the unique excluded count.
    if sum(reasons.values()) < excluded:
        _fail(path, "reason counts cannot cover the unique exclusions")
    available = _require_mapping(doc["model_available_counts"], set(MODEL_NAMES), f"{path}.model_available_counts")
    for name in MODEL_NAMES:
        count = _require_int(available[name], f"{path}.model_available_counts.{name}")
        if count > requested:
            _fail(path, f"{name} available count exceeds requested targets")


def _validate_model_metrics_document(value: Any, path: str, sample_count: int, class_support: Sequence[int]) -> None:
    doc = _require_mapping(
        value,
        {
            "mean_brier",
            "mean_log_loss",
            "log_loss_state",
            "zero_actual_probability_count",
            "tie_count",
            "accuracy",
            "confusion",
            "class_recall",
            "reliability_bins",
        },
        path,
    )
    state = _require_enum(doc["log_loss_state"], ("finite", "infinite", "empty"), f"{path}.log_loss_state")
    zero_count = _require_int(doc["zero_actual_probability_count"], f"{path}.zero_actual_probability_count")
    tie_count = _require_int(doc["tie_count"], f"{path}.tie_count")
    if zero_count > sample_count or tie_count > sample_count:
        _fail(path, "row counters exceed sample_count")

    if sample_count == 0:
        if state != "empty" or doc["mean_brier"] is not None or doc["mean_log_loss"] is not None or doc["accuracy"] is not None:
            _fail(path, "an empty cohort must have null metrics and empty state")
    else:
        _require_loss(doc["mean_brier"], f"{path}.mean_brier", MAX_THREE_CLASS_BRIER)
        _require_fraction(doc["accuracy"], f"{path}.accuracy")
        if state == "empty":
            _fail(path, "a nonempty cohort cannot have empty log-loss state")
        if state == "finite":
            _require_loss(doc["mean_log_loss"], f"{path}.mean_log_loss")
            if zero_count != 0:
                _fail(path, "finite log-loss state cannot have zero-probability rows")
        else:
            if doc["mean_log_loss"] is not None:
                _fail(path, "infinite log-loss state must keep mean_log_loss null")
            if zero_count == 0:
                _fail(path, "infinite log-loss state requires a zero-probability row")

    confusion = _require_list(doc["confusion"], f"{path}.confusion", 3)
    for row_idx, row in enumerate(confusion):
        _require_list(row, f"{path}.confusion[{row_idx}]", 3)
        for col_idx, cell in enumerate(row):
            _require_int(cell, f"{path}.confusion[{row_idx}][{col_idx}]")
        if sum(row) != class_support[row_idx]:
            _fail(f"{path}.confusion[{row_idx}]", "row sum must equal class support")
    if sample_count > 0:
        _require_stated_rate(doc["accuracy"], sum(confusion[k][k] for k in range(3)), sample_count, f"{path}.accuracy")

    recalls = _require_list(doc["class_recall"], f"{path}.class_recall", 3)
    for idx, recall in enumerate(recalls):
        if class_support[idx] == 0:
            if recall is not None:
                _fail(f"{path}.class_recall[{idx}]", "undefined recall must stay null")
        else:
            _require_fraction(recall, f"{path}.class_recall[{idx}]")
            _require_stated_rate(recall, confusion[idx][idx], class_support[idx], f"{path}.class_recall[{idx}]")

    bins = _require_list(doc["reliability_bins"], f"{path}.reliability_bins", 30)
    for pos, entry in enumerate(bins):
        bin_path = f"{path}.reliability_bins[{pos}]"
        item = _require_mapping(entry, {"class_label", "bin_index", "count", "mean_probability", "observed_frequency"}, bin_path)
        if item["class_label"] != ORDERED_CLASSES[pos // 10] or type(item["bin_index"]) is not int or item["bin_index"] != pos % 10:
            _fail(bin_path, "bins must stay in class-major order")
        count = _require_int(item["count"], f"{bin_path}.count")
        if count == 0:
            if item["mean_probability"] is not None or item["observed_frequency"] is not None:
                _fail(bin_path, "an empty bin must keep null means")
        else:
            # Range only: an exact bin-edge or mean relation would reject accepted float behavior
            _require_fraction(item["mean_probability"], f"{bin_path}.mean_probability")
            _require_fraction(item["observed_frequency"], f"{bin_path}.observed_frequency")
    for class_pos in range(3):
        if sum(b["count"] for b in bins[class_pos * 10 : class_pos * 10 + 10]) != sample_count:
            _fail(path, f"bin counts for {ORDERED_CLASSES[class_pos]} must equal sample_count")


def _validate_metrics_document(value: Any, path: str, status: str, requested_count: int) -> None:
    if status == STATUS_COMPARISON_UNAVAILABLE:
        if value is not None:
            _fail(path, "comparison_unavailable must keep metrics null")
        return
    doc = _require_mapping(value, {"sample_count", "class_support", "status", "models"}, path)
    sample_count = _require_int(doc["sample_count"], f"{path}.sample_count")
    support = _require_list(doc["class_support"], f"{path}.class_support", 3)
    for idx, item in enumerate(support):
        _require_int(item, f"{path}.class_support[{idx}]")
    if sum(support) != sample_count:
        _fail(path, "class support must sum to sample_count")
    if sample_count != requested_count:
        _fail(path, "sample_count must equal the requested cohort")
    expected_status = METRICS_STATUS_SCORED if status == STATUS_SCORED else METRICS_STATUS_EMPTY
    if doc["status"] != expected_status:
        _fail(path, f"metric status {doc['status']!r} contradicts comparison status {status!r}")
    if (status == STATUS_SCORED) != (sample_count > 0):
        _fail(path, "scored requires rows; empty requires none")
    models = _require_mapping(doc["models"], set(MODEL_NAMES), f"{path}.models")
    for name in MODEL_NAMES:
        _validate_model_metrics_document(models[name], f"{path}.models.{name}", sample_count, support)


def _validate_method_states_document(value: Any, path: str, status: str) -> None:
    doc = _require_mapping(value, set(MODEL_NAMES), path)
    heuristic = _require_mapping(doc["heuristic"], {"available"}, f"{path}.heuristic")
    frequency = _require_mapping(doc["frequency"], {"available", "unavailable_reason"}, f"{path}.frequency")
    logistic = _require_mapping(doc["logistic"], {"available", "unavailable_reason", "failure_stage"}, f"{path}.logistic")
    for name, item in (("heuristic", heuristic), ("frequency", frequency), ("logistic", logistic)):
        if type(item["available"]) is not bool:
            _fail(f"{path}.{name}.available", "expected boolean")
    if heuristic["available"] is not True:
        _fail(f"{path}.heuristic", "the replay adapter fails the run rather than dropping heuristic forecasts")
    if frequency["available"]:
        if frequency["unavailable_reason"] is not None:
            _fail(f"{path}.frequency", "available method cannot carry a reason")
    else:
        _require_enum(frequency["unavailable_reason"], FREQUENCY_UNAVAILABLE_REASONS, f"{path}.frequency.unavailable_reason")
    if logistic["available"]:
        if logistic["unavailable_reason"] is not None or logistic["failure_stage"] is not None:
            _fail(f"{path}.logistic", "available method cannot carry a reason or stage")
    else:
        reason = _require_enum(logistic["unavailable_reason"], LOGISTIC_UNAVAILABLE_REASONS, f"{path}.logistic.unavailable_reason")
        if reason in ("no_fit_rows", "missing_training_classes"):
            if logistic["failure_stage"] is not None:
                _fail(f"{path}.logistic", f"{reason} has no failure stage")
        else:
            _require_enum(logistic["failure_stage"], LOGISTIC_FAILURE_STAGES, f"{path}.logistic.failure_stage")
    all_available = frequency["available"] and logistic["available"]
    if all_available == (status == STATUS_COMPARISON_UNAVAILABLE):
        _fail(path, f"method availability contradicts status {status!r}")


def _validate_availability_counts(counts: Mapping[str, Any], method_states: Mapping[str, Any], path: str) -> None:
    """An available method covers every requested origin; an unavailable one covers none."""
    for name in MODEL_NAMES:
        expected = counts["requested_count"] if method_states[name]["available"] else 0
        if counts["model_available_counts"][name] != expected:
            _fail(f"{path}.counts.model_available_counts.{name}", f"expected {expected} for its method state")


def _validate_comparison_state(status: str, reasons: Any, path: str) -> None:
    _require_enum(status, (STATUS_SCORED, STATUS_EMPTY, STATUS_COMPARISON_UNAVAILABLE), f"{path}.comparison_status")
    _require_list(reasons, f"{path}.comparison_unavailable_reasons")
    for idx, reason in enumerate(reasons):
        _require_str(reason, f"{path}.comparison_unavailable_reasons[{idx}]")
    if (status == STATUS_COMPARISON_UNAVAILABLE) != (len(reasons) > 0):
        _fail(path, "unavailable reasons must exist exactly when the comparison is unavailable")


def _validate_uncertainty_document(value: Any, path: str) -> None:
    try:
        validate_uncertainty_result_document(value)
    except (UncertaintyValidationError, ValueError) as exc:
        _fail(path, str(exc))


def _validate_summary_relations(doc: Mapping[str, Any], schema_ver: str, path: str) -> None:
    """
    Relates the closed portable blocks to one another, using only facts the summary carries.

    Partition cutoff dates are the declared chronological cutoffs and the TEST cutoff index is the
    admitted mature start. The uncertainty block counts the TEST requested origins over the
    admitted span; its reason, length states and point nullability follow from the TEST comparison
    status, that count and the admitted gap count, in common_unavailable_reason's order. A v3
    summary also keeps the frozen historical window. The scored count is not inferred from the
    span. Axis dates, rows and resampling stay private to the archive relations (_relate_axis,
    _relate_statistics).
    """
    cutoffs = doc["chronological_cutoffs"]
    admission = doc["admission_summary"]
    partitions = doc["partitions"]
    test = partitions["test"]
    for name, declared in (("development", "development_start"), ("test", "test_start")):
        if partitions[name]["cutoff_date"] != cutoffs[declared]:
            _fail(f"{path}.partitions.{name}.cutoff_date", f"must equal chronological_cutoffs.{declared}")
    start = admission["mature_test_start_index"]
    span = admission["mature_test_span_count"]
    if test["cutoff_index"] != start:
        _fail(f"{path}.partitions.test.cutoff_index", f"must equal admission_summary.mature_test_start_index {start}")
    if schema_ver == SCHEMA_VERSION_SUMMARY_V3:
        if span != HISTORICAL_TEST_SPAN:
            _fail(f"{path}.admission_summary.mature_test_span_count", f"v3 requires {HISTORICAL_TEST_SPAN} mature slots, got {span}")
        if start < HISTORICAL_MIN_TEST_START_INDEX:
            _fail(f"{path}.partitions.test.cutoff_index", f"v3 requires a TEST index of at least {HISTORICAL_MIN_TEST_START_INDEX}, got {start}")
        development_index = start - HISTORICAL_DEVELOPMENT_SPAN
        if partitions["development"]["cutoff_index"] != development_index:
            _fail(
                f"{path}.partitions.development.cutoff_index",
                f"v3 requires the TEST index minus {HISTORICAL_DEVELOPMENT_SPAN} ({development_index})",
            )

    requested = test["counts"]["requested_count"]
    gaps = admission["union_gap_count"]
    # The saved requested keys and the admitted union gaps partition the mature span exactly,
    # whatever the comparator outcome
    if requested != span - gaps:
        _fail(
            f"{path}.partitions.test.counts.requested_count",
            f"must be the admitted span {span} minus union_gap_count {gaps} ({span - gaps}), got {requested}",
        )

    uncertainty = doc["uncertainty"]
    if uncertainty["n"] != requested or uncertainty["mature_span_count"] != span:
        _fail(
            f"{path}.uncertainty",
            f"n and mature_span_count must be the TEST requested_count {requested} and the admitted span {span}, "
            f"got {uncertainty['n']} and {uncertainty['mature_span_count']}",
        )
    common_reason = common_unavailable_reason(test["comparison_status"], requested, gaps)
    cleared = () if common_reason is not None else available_block_lengths(requested)
    expected_reason = common_reason if common_reason is not None or cleared else REASON_INSUFFICIENT_BLOCKS
    if uncertainty["reason"] != expected_reason:
        _fail(f"{path}.uncertainty.reason", f"must be {expected_reason!r} for the TEST comparison status, requested count and admitted gaps")
    for view in uncertainty["block_lengths"]:
        if (view["status"] == UNCERTAINTY_STATUS_AVAILABLE) != (view["block_length"] in cleared):
            _fail(f"{path}.uncertainty.block_lengths", f"length {view['block_length']} state contradicts the TEST cohort")
    no_point = common_reason in NO_POINT_REASONS
    for entry in uncertainty["point_differences"]:
        if (entry["point_difference"] is None) != no_point:
            _fail(f"{path}.uncertainty.point_differences", f"{entry['pair_id']} nullability contradicts the TEST comparison")
    if no_point:
        return
    # A point exists only for a scored TEST with requested origins, so its metrics carry finite
    # means. The interval state does not matter: below-floor and gapped points are checked too.
    models = test["metrics"]["models"]
    for entry in uncertainty["point_differences"]:
        comparator = _PAIR_COMPARATORS[entry["pair_id"]]
        expected = models["heuristic"]["mean_brier"] - models[comparator]["mean_brier"]
        if abs(entry["point_difference"] - expected) > PAIRED_POINT_TOLERANCE:
            _fail(
                f"{path}.uncertainty.point_differences",
                f"{entry['pair_id']} {entry['point_difference']!r} differs from the TEST mean Brier difference "
                f"heuristic - {comparator} ({expected!r}) by more than {PAIRED_POINT_TOLERANCE!r}",
            )


def _validate_common_identity(doc: Mapping[str, Any], path: str) -> None:
    """Checks the identity fields shared by the result, summary and manifest documents."""
    _require_identifier(doc["run_id"], f"{path}.run_id")
    _require_identifier(doc["study_id"], f"{path}.study_id")
    _require_enum(doc["protocol_id"], sorted(SUPPORTED_PROTOCOL_IDS), f"{path}.protocol_id")
    schema_ver = doc.get("schema_version")
    if schema_ver in (SCHEMA_VERSION_SUMMARY_V3, SCHEMA_VERSION_RESULT_V3, SCHEMA_VERSION_RUN_MANIFEST_V3):
        if doc.get("data_kind") != DATA_KIND_HISTORICAL:
            _fail(f"{path}.data_kind", f"v3 schema requires {DATA_KIND_HISTORICAL!r}, got {doc.get('data_kind')!r}")
        if doc.get("development_status") != DEVELOPMENT_STATUS_HISTORICAL:
            _fail(f"{path}.development_status", f"v3 schema requires {DEVELOPMENT_STATUS_HISTORICAL!r}, got {doc.get('development_status')!r}")
    elif schema_ver in (SCHEMA_VERSION_SUMMARY_V2, SCHEMA_VERSION_RESULT_V2, SCHEMA_VERSION_RUN_MANIFEST_V2):
        if doc.get("data_kind") != DATA_KIND_SYNTHETIC:
            _fail(f"{path}.data_kind", f"v2 schema requires {DATA_KIND_SYNTHETIC!r}, got {doc.get('data_kind')!r}")
        if doc.get("development_status") != DEVELOPMENT_STATUS_SYNTHETIC:
            _fail(f"{path}.development_status", f"v2 schema requires {DEVELOPMENT_STATUS_SYNTHETIC!r}, got {doc.get('development_status')!r}")
    else:
        if doc.get("data_kind") not in SUPPORTED_DATA_KINDS:
            _fail(f"{path}.data_kind", f"unsupported data_kind {doc.get('data_kind')!r}")
        if doc.get("development_status") not in SUPPORTED_DEVELOPMENT_STATUSES:
            _fail(f"{path}.development_status", f"unsupported development_status {doc.get('development_status')!r}")


def validate_summary_document(doc: Any) -> None:
    """Closed validation of nivesh-evaluation-summary. Raises ValueError on any violation."""
    path = "summary"
    _require_mapping(doc, REQUIRED_SUMMARY_KEYS, path)
    schema_ver = _require_enum(doc["schema_version"], sorted(SUPPORTED_SUMMARY_SCHEMA_VERSIONS), f"{path}.schema_version")
    _validate_common_identity(doc, path)
    _require_str(doc["claim_label"], f"{path}.claim_label")

    attribution = _require_mapping(
        doc["dataset_attribution"],
        {"source_kind", "asset_label", "series_id", "coverage_start_date", "coverage_end_date"},
        f"{path}.dataset_attribution",
    )
    if schema_ver == SCHEMA_VERSION_SUMMARY_V3:
        _require_enum(attribution["source_kind"], (SOURCE_KIND_HISTORICAL,), f"{path}.dataset_attribution.source_kind")
    else:
        _require_enum(attribution["source_kind"], (SOURCE_KIND_SYNTHETIC,), f"{path}.dataset_attribution.source_kind")
    _require_str(attribution["asset_label"], f"{path}.dataset_attribution.asset_label")
    _require_str(attribution["series_id"], f"{path}.dataset_attribution.series_id")
    start = _require_date(attribution["coverage_start_date"], f"{path}.dataset_attribution.coverage_start_date")
    end = _require_date(attribution["coverage_end_date"], f"{path}.dataset_attribution.coverage_end_date")
    if start > end:
        _fail(f"{path}.dataset_attribution", "coverage dates are inverted")

    validate_replay_identity(doc["replay_identity"], f"{path}.replay_identity")
    if schema_ver == SCHEMA_VERSION_SUMMARY_V3:
        provenance = _require_mapping(
            doc["provenance_identity"],
            {"config_sha256", "admission_sha256", "approval_sha256"},
            f"{path}.provenance_identity",
        )
    else:
        provenance = _require_mapping(
            doc["provenance_identity"],
            {"config_sha256", "admission_sha256", "nifty_input_sha256", "vix_input_sha256", "calendar_sha256"},
            f"{path}.provenance_identity",
        )
    for key, item in provenance.items():
        _require_sha(item, f"{path}.provenance_identity.{key}")

    cutoffs = _require_mapping(doc["chronological_cutoffs"], {"development_start", "test_start"}, f"{path}.chronological_cutoffs")
    dev = _require_date(cutoffs["development_start"], f"{path}.chronological_cutoffs.development_start")
    test = _require_date(cutoffs["test_start"], f"{path}.chronological_cutoffs.test_start")
    if dev >= test:
        _fail(f"{path}.chronological_cutoffs", "development_start must precede test_start")

    validate_admission_summary(doc["admission_summary"], f"{path}.admission_summary")

    definitions = _require_mapping(
        doc["fixed_definitions"],
        {"classes", "neutral_band", "horizon_sessions", "primary_probability_metric", "log_loss_zero_policy"},
        f"{path}.fixed_definitions",
    )
    if definitions["classes"] != list(ORDERED_CLASSES):
        _fail(f"{path}.fixed_definitions.classes", "fixed class order changed")
    if definitions["horizon_sessions"] != 20 or type(definitions["horizon_sessions"]) is not int:
        _fail(f"{path}.fixed_definitions.horizon_sessions", "horizon must be 20")
    _require_str(definitions["neutral_band"], f"{path}.fixed_definitions.neutral_band")
    _require_str(definitions["primary_probability_metric"], f"{path}.fixed_definitions.primary_probability_metric")
    _require_str(definitions["log_loss_zero_policy"], f"{path}.fixed_definitions.log_loss_zero_policy")

    partitions = _require_mapping(doc["partitions"], {"development", "test"}, f"{path}.partitions")
    for name in ("development", "test"):
        part_path = f"{path}.partitions.{name}"
        part = _require_mapping(
            partitions[name],
            {
                "partition",
                "cutoff_index",
                "cutoff_date",
                "counts",
                "comparison_status",
                "comparison_unavailable_reasons",
                "method_states",
                "metrics",
            },
            part_path,
        )
        if part["partition"] != name:
            _fail(f"{part_path}.partition", "partition name mismatch")
        _require_int(part["cutoff_index"], f"{part_path}.cutoff_index")
        _require_date(part["cutoff_date"], f"{part_path}.cutoff_date")
        _validate_counts_document(part["counts"], f"{part_path}.counts")
        status = part["comparison_status"]
        _validate_comparison_state(status, part["comparison_unavailable_reasons"], part_path)
        _validate_method_states_document(part["method_states"], f"{part_path}.method_states", status)
        _validate_availability_counts(part["counts"], part["method_states"], part_path)
        _validate_metrics_document(part["metrics"], f"{part_path}.metrics", status, part["counts"]["requested_count"])

    _validate_uncertainty_document(doc["uncertainty"], f"{path}.uncertainty")
    _validate_summary_relations(doc, schema_ver, path)
    limitations = _require_list(doc["limitations"], f"{path}.limitations")
    if not limitations:
        _fail(f"{path}.limitations", "limitations are required")
    for idx, item in enumerate(limitations):
        _require_str(item, f"{path}.limitations[{idx}]")


def validate_frequency_block_state(value: Any, path: str) -> None:
    """Closed validation of one returned FrequencyBlock projection, available or not."""
    doc = _require_mapping(
        value,
        {
            "method",
            "partition",
            "fitting_indices",
            "cutoff_index",
            "cutoff_date",
            "requested_indices",
            "prediction_count",
            "unavailable_reason",
            "fit",
        },
        path,
    )
    _require_str(doc["method"], f"{path}.method")
    _require_enum(doc["partition"], ("development", "test"), f"{path}.partition")
    _require_increasing_indices(doc["fitting_indices"], f"{path}.fitting_indices")
    _require_int(doc["cutoff_index"], f"{path}.cutoff_index")
    _require_date(doc["cutoff_date"], f"{path}.cutoff_date")
    _require_increasing_indices(doc["requested_indices"], f"{path}.requested_indices")
    predictions = _require_int(doc["prediction_count"], f"{path}.prediction_count")
    fit = doc["fit"]
    if fit is None:
        _require_enum(doc["unavailable_reason"], FREQUENCY_UNAVAILABLE_REASONS, f"{path}.unavailable_reason")
        if predictions != 0:
            _fail(path, "an unavailable block cannot have predictions")
        return
    if doc["unavailable_reason"] is not None:
        _fail(path, "a fitted block cannot carry an unavailable reason")
    if predictions != len(doc["requested_indices"]):
        _fail(path, "a fitted block must predict every requested origin")
    item = _require_mapping(fit, {"class_counts", "probabilities"}, f"{path}.fit")
    counts = _require_list(item["class_counts"], f"{path}.fit.class_counts", 3)
    for idx, count in enumerate(counts):
        _require_int(count, f"{path}.fit.class_counts[{idx}]")
    if sum(counts) != len(doc["fitting_indices"]):
        _fail(f"{path}.fit", "class counts must sum to the fitting pool")
    _require_probability_vector(item["probabilities"], f"{path}.fit.probabilities")


def validate_logistic_block_state(value: Any, path: str) -> None:
    """Closed validation of one returned LogisticBlock projection, available or not."""
    doc = _require_mapping(
        value,
        {
            "method",
            "partition",
            "fitting_indices",
            "cutoff_index",
            "cutoff_date",
            "class_counts",
            "regime_counts",
            "requested_indices",
            "prediction_count",
            "unavailable_reason",
            "failure_stage",
            "fit",
        },
        path,
    )
    _require_str(doc["method"], f"{path}.method")
    _require_enum(doc["partition"], ("development", "test"), f"{path}.partition")
    _require_increasing_indices(doc["fitting_indices"], f"{path}.fitting_indices")
    _require_int(doc["cutoff_index"], f"{path}.cutoff_index")
    _require_date(doc["cutoff_date"], f"{path}.cutoff_date")
    _require_increasing_indices(doc["requested_indices"], f"{path}.requested_indices")
    counts = _require_list(doc["class_counts"], f"{path}.class_counts", 3)
    regimes = _require_list(doc["regime_counts"], f"{path}.regime_counts", len(VALID_REGIMES))
    for idx, count in enumerate(counts):
        _require_int(count, f"{path}.class_counts[{idx}]")
    for idx, count in enumerate(regimes):
        _require_int(count, f"{path}.regime_counts[{idx}]")
    if sum(counts) != len(doc["fitting_indices"]) or sum(regimes) != len(doc["fitting_indices"]):
        _fail(path, "class and regime counts must sum to the fitting pool")
    predictions = _require_int(doc["prediction_count"], f"{path}.prediction_count")
    fit = doc["fit"]
    if fit is None:
        reason = _require_enum(doc["unavailable_reason"], LOGISTIC_UNAVAILABLE_REASONS, f"{path}.unavailable_reason")
        if reason in ("no_fit_rows", "missing_training_classes"):
            if doc["failure_stage"] is not None:
                _fail(path, f"{reason} has no failure stage")
        else:
            _require_enum(doc["failure_stage"], LOGISTIC_FAILURE_STAGES, f"{path}.failure_stage")
        if predictions != 0:
            _fail(path, "an unavailable block cannot have predictions")
        return
    if doc["unavailable_reason"] is not None or doc["failure_stage"] is not None:
        _fail(path, "a fitted block cannot carry a reason or stage")
    if predictions != len(doc["requested_indices"]):
        _fail(path, "a fitted block must predict every requested origin")
    item = _require_mapping(
        fit,
        {
            "numeric_means",
            "numeric_variances",
            "numeric_scales",
            "coefficients",
            "intercepts",
            "n_iter",
            "classes",
            "feature_names",
        },
        f"{path}.fit",
    )
    for key in ("numeric_means", "numeric_variances", "numeric_scales"):
        vector = _require_list(item[key], f"{path}.fit.{key}", 6)
        for idx, number in enumerate(vector):
            _require_number(number, f"{path}.fit.{key}[{idx}]")
    coefficients = _require_list(item["coefficients"], f"{path}.fit.coefficients", 3)
    for row_idx, row in enumerate(coefficients):
        _require_list(row, f"{path}.fit.coefficients[{row_idx}]", 12)
        for col_idx, number in enumerate(row):
            _require_number(number, f"{path}.fit.coefficients[{row_idx}][{col_idx}]")
    intercepts = _require_list(item["intercepts"], f"{path}.fit.intercepts", 3)
    for idx, number in enumerate(intercepts):
        _require_number(number, f"{path}.fit.intercepts[{idx}]")
    _require_int(item["n_iter"], f"{path}.fit.n_iter")
    if item["classes"] != list(ORDERED_CLASSES):
        _fail(f"{path}.fit.classes", "fixed class order changed")
    _require_list(item["feature_names"], f"{path}.fit.feature_names", 12)


def validate_comparator_metadata(value: Any, path: str) -> None:
    """Closed validation of the persisted frequency and logistic comparator metadata."""
    doc = _require_mapping(value, {"frequency", "logistic"}, path)

    def _common(item: Mapping[str, Any], item_path: str) -> None:
        _require_str(item["method"], f"{item_path}.method")
        if item["classes"] != list(ORDERED_CLASSES):
            _fail(f"{item_path}.classes", "fixed class order changed")
        _require_str(item["series_id"], f"{item_path}.series_id")
        if type(item["horizon_sessions"]) is not int or item["horizon_sessions"] != 20:
            _fail(f"{item_path}.horizon_sessions", "horizon must be the native integer 20")
        _require_str(item["protocol_id"], f"{item_path}.protocol_id")
        _require_str(item["outcome_definition"], f"{item_path}.outcome_definition")

    def _name_list(item: Any, item_path: str, length: int) -> None:
        for idx, name in enumerate(_require_list(item, item_path, length)):
            _require_str(name, f"{item_path}[{idx}]")

    frequency_path = f"{path}.frequency"
    frequency = _require_mapping(
        doc["frequency"],
        {"method", "alpha", "classes", "series_id", "horizon_sessions", "protocol_id", "outcome_definition"},
        frequency_path,
    )
    _common(frequency, frequency_path)
    _require_number(frequency["alpha"], f"{frequency_path}.alpha")

    logistic_path = f"{path}.logistic"
    logistic = _require_mapping(
        doc["logistic"],
        {
            "method",
            "configuration",
            "classes",
            "series_id",
            "horizon_sessions",
            "protocol_id",
            "outcome_definition",
            "dependency_versions",
            "numeric_features",
            "encoded_features",
            "regime_order",
        },
        logistic_path,
    )
    _common(logistic, logistic_path)
    config_path = f"{logistic_path}.configuration"
    configuration = _require_mapping(
        logistic["configuration"],
        {"solver", "c", "l1_ratio", "fit_intercept", "tol", "max_iter", "class_weight", "warm_start", "verbose"},
        config_path,
    )
    _require_str(configuration["solver"], f"{config_path}.solver")
    for key in ("c", "l1_ratio", "tol"):
        _require_number(configuration[key], f"{config_path}.{key}")
    for key in ("fit_intercept", "warm_start"):
        if type(configuration[key]) is not bool:
            _fail(f"{config_path}.{key}", f"expected boolean, got {configuration[key]!r}")
    _require_int(configuration["max_iter"], f"{config_path}.max_iter", 1)
    _require_int(configuration["verbose"], f"{config_path}.verbose")
    _require_optional_str(configuration["class_weight"], f"{config_path}.class_weight")

    versions_path = f"{logistic_path}.dependency_versions"
    for idx, pair in enumerate(_require_list(logistic["dependency_versions"], versions_path)):
        _name_list(pair, f"{versions_path}[{idx}]", 2)
    _name_list(logistic["numeric_features"], f"{logistic_path}.numeric_features", 6)
    _name_list(logistic["encoded_features"], f"{logistic_path}.encoded_features", len(VALID_REGIMES))
    if logistic["regime_order"] != list(VALID_REGIMES):
        _fail(f"{logistic_path}.regime_order", "fixed regime order changed")


def _validate_method_row(value: Any, path: str, score_state: str, actual_class: str, *, heuristic: bool = False) -> None:
    keys = {"forecast_state", "probabilities", "predicted_class", "brier", "log_loss", "log_loss_state"}
    if heuristic:
        keys = keys | {"expected_direction"}
    doc = _require_mapping(value, keys, path)
    state = _require_enum(doc["forecast_state"], (FORECAST_STATE_AVAILABLE, FORECAST_STATE_UNAVAILABLE), f"{path}.forecast_state")
    if heuristic:
        _require_enum(doc["expected_direction"], EXPECTED_DIRECTIONS, f"{path}.expected_direction")
    if state == FORECAST_STATE_UNAVAILABLE:
        if doc["probabilities"] is not None:
            _fail(path, "an unavailable method cannot carry probabilities")
    else:
        _require_probability_vector(doc["probabilities"], f"{path}.probabilities")
    if score_state == SCORE_STATE_UNSCORED:
        if any(doc[key] is not None for key in ("predicted_class", "brier", "log_loss", "log_loss_state")):
            _fail(path, "an unscored row cannot carry scores")
        return
    if state != FORECAST_STATE_AVAILABLE:
        _fail(path, "a scored row needs an available forecast")

    # Relations among this row's own fields; the scorer stays the only owner of loss values
    probabilities = doc["probabilities"]
    predicted = _require_enum(doc["predicted_class"], ORDERED_CLASSES, f"{path}.predicted_class")
    if predicted != ORDERED_CLASSES[probabilities.index(max(probabilities))]:
        _fail(f"{path}.predicted_class", "predicted class must be the first maximum of the forecast")
    _require_loss(doc["brier"], f"{path}.brier", MAX_THREE_CLASS_BRIER)
    log_state = _require_enum(doc["log_loss_state"], ("finite", "infinite"), f"{path}.log_loss_state")
    actual_probability = probabilities[ORDERED_CLASSES.index(actual_class)]
    if log_state == "finite":
        _require_loss(doc["log_loss"], f"{path}.log_loss")
        if actual_probability == 0:
            _fail(path, "a zero actual-class probability cannot have finite log loss")
    else:
        if doc["log_loss"] is not None:
            _fail(path, "an infinite row keeps log_loss null")
        if actual_probability != 0:
            _fail(path, "infinite log loss requires a zero actual-class probability")


def _validate_per_origin_document(value: Any, path: str, status: str) -> None:
    doc = _require_mapping(
        value,
        {
            "origin_index",
            "origin_date",
            "origin_close",
            "maturity_index",
            "maturity_date",
            "maturity_close",
            "actual_class",
            "score_state",
            "heuristic",
            "frequency",
            "logistic",
        },
        path,
    )
    origin = _require_int(doc["origin_index"], f"{path}.origin_index")
    _require_date(doc["origin_date"], f"{path}.origin_date")
    _require_str(doc["origin_close"], f"{path}.origin_close")
    if _require_int(doc["maturity_index"], f"{path}.maturity_index") != origin + 20:
        _fail(path, "maturity must stay exactly 20 positions after the origin")
    _require_date(doc["maturity_date"], f"{path}.maturity_date")
    _require_str(doc["maturity_close"], f"{path}.maturity_close")
    actual_class = _require_enum(doc["actual_class"], ORDERED_CLASSES, f"{path}.actual_class")
    score_state = _require_enum(doc["score_state"], (SCORE_STATE_SCORED, SCORE_STATE_UNSCORED), f"{path}.score_state")
    if (score_state == SCORE_STATE_SCORED) != (status == STATUS_SCORED):
        _fail(path, f"row score state {score_state!r} contradicts comparison status {status!r}")
    _validate_method_row(doc["heuristic"], f"{path}.heuristic", score_state, actual_class, heuristic=True)
    _validate_method_row(doc["frequency"], f"{path}.frequency", score_state, actual_class)
    _validate_method_row(doc["logistic"], f"{path}.logistic", score_state, actual_class)


def _validate_block_relation(block: Mapping[str, Any], partition: Mapping[str, Any], method: str, path: str) -> None:
    """A returned block must describe the same partition, cutoff, keys and state as its summary fields."""
    state = partition["method_states"][method]
    if block["partition"] != partition["partition"] or block["requested_indices"] != partition["requested_indices"]:
        _fail(path, "block partition or requested keys differ from the partition")
    if block["cutoff_index"] != partition["cutoff_index"] or block["cutoff_date"] != partition["cutoff_date"]:
        _fail(path, "block cutoff index or date differs from the partition cutoff")
    if (block["fit"] is not None) != state["available"] or block["unavailable_reason"] != state["unavailable_reason"]:
        _fail(path, f"block state contradicts the {method} method state")
    if method == "logistic" and block["failure_stage"] != state["failure_stage"]:
        _fail(path, "block failure stage contradicts the logistic method state")


def _validate_result_partition(value: Any, path: str, name: str) -> None:
    doc = _require_mapping(
        value,
        {
            "partition",
            "cutoff_index",
            "cutoff_date",
            "requested_indices",
            "requested_dates",
            "counts",
            "comparison_status",
            "comparison_unavailable_reasons",
            "method_states",
            "frequency_block",
            "logistic_block",
            "metrics",
            "per_origin_records",
        },
        path,
    )
    if doc["partition"] != name:
        _fail(f"{path}.partition", "partition name mismatch")
    _require_int(doc["cutoff_index"], f"{path}.cutoff_index")
    _require_date(doc["cutoff_date"], f"{path}.cutoff_date")
    _require_increasing_indices(doc["requested_indices"], f"{path}.requested_indices")
    dates = _require_list(doc["requested_dates"], f"{path}.requested_dates", len(doc["requested_indices"]))
    for idx, item in enumerate(dates):
        _require_date(item, f"{path}.requested_dates[{idx}]")
    _validate_counts_document(doc["counts"], f"{path}.counts")
    if doc["counts"]["requested_count"] != len(doc["requested_indices"]):
        _fail(path, "requested_count must match the requested keys")
    status = doc["comparison_status"]
    _validate_comparison_state(status, doc["comparison_unavailable_reasons"], path)
    _validate_method_states_document(doc["method_states"], f"{path}.method_states", status)
    _validate_availability_counts(doc["counts"], doc["method_states"], path)
    validate_frequency_block_state(doc["frequency_block"], f"{path}.frequency_block")
    validate_logistic_block_state(doc["logistic_block"], f"{path}.logistic_block")
    _validate_block_relation(doc["frequency_block"], doc, "frequency", f"{path}.frequency_block")
    _validate_block_relation(doc["logistic_block"], doc, "logistic", f"{path}.logistic_block")
    _validate_metrics_document(doc["metrics"], f"{path}.metrics", status, len(doc["requested_indices"]))
    rows = _require_list(doc["per_origin_records"], f"{path}.per_origin_records", len(doc["requested_indices"]))
    for pos, row in enumerate(rows):
        row_path = f"{path}.per_origin_records[{pos}]"
        _validate_per_origin_document(row, row_path, status)
        if row["origin_index"] != doc["requested_indices"][pos] or row["origin_date"] != doc["requested_dates"][pos]:
            _fail(row_path, "row key differs from the requested key")
        for method in MODEL_NAMES:
            if (row[method]["forecast_state"] == FORECAST_STATE_AVAILABLE) != doc["method_states"][method]["available"]:
                _fail(f"{row_path}.{method}", "forecast state contradicts the method state")


def validate_result_document(doc: Any) -> None:
    """Closed validation of the private complete result artifact. Raises ValueError on violation."""
    path = "result"
    if type(doc) is not dict:
        _fail(path, "expected object")
    schema_ver = doc.get("schema_version")
    # Type first: an array or object version is unhashable and must stay a schema error
    if type(schema_ver) is not str or schema_ver not in SUPPORTED_RESULT_SCHEMA_VERSIONS:
        _fail(f"{path}.schema_version", f"unsupported schema {schema_ver!r}")
    is_historical = schema_ver == SCHEMA_VERSION_RESULT_V3
    req_keys = REQUIRED_RESULT_KEYS_V3 if is_historical else REQUIRED_RESULT_KEYS_V2
    _require_mapping(doc, req_keys, path)
    _validate_common_identity(doc, path)
    _require_str(doc["claim_label"], f"{path}.claim_label")
    for key in ("coverage_start_date", "coverage_end_date", "development_start", "test_start"):
        _require_date(doc[key], f"{path}.{key}")
    validate_admission_document(doc["admission"], f"{path}.admission")
    validate_file_identity(doc["config_identity"], f"{path}.config_identity")
    validate_file_identity(doc["admission_identity"], f"{path}.admission_identity")
    if is_historical:
        validate_file_identity(doc["approval_identity"], f"{path}.approval_identity")
    validate_input_identities(doc["input_identities"], f"{path}.input_identities", is_historical=is_historical)
    validate_source_identities(doc["source_identities"], f"{path}.source_identities")
    validate_runtime_identities(doc["runtime_identities"], f"{path}.runtime_identities")
    validate_model_identity(doc["model_identity"], f"{path}.model_identity")
    validate_build_identity(doc["build_identity"], f"{path}.build_identity")
    validate_replay_identity(doc["replay_identity"], f"{path}.replay_identity")
    private_paths = doc["private_paths"]
    if type(private_paths) is not dict:
        _fail(f"{path}.private_paths", "expected object")
    for key, item in private_paths.items():
        _require_str(item, f"{path}.private_paths.{key}")
    validate_comparator_metadata(doc["comparator_metadata"], f"{path}.comparator_metadata")
    partitions = _require_mapping(doc["partitions"], {"development", "test"}, f"{path}.partitions")
    for name in ("development", "test"):
        _validate_result_partition(partitions[name], f"{path}.partitions.{name}", name)
    warnings_list = _require_list(doc["warnings"], f"{path}.warnings")
    for idx, item in enumerate(warnings_list):
        entry = _require_mapping(item, {"category", "message", "filename", "lineno"}, f"{path}.warnings[{idx}]")
        _require_str(entry["category"], f"{path}.warnings[{idx}].category")
        _require_str(entry["message"], f"{path}.warnings[{idx}].message", allow_empty=True)
        _require_str(entry["filename"], f"{path}.warnings[{idx}].filename", allow_empty=True)
        _require_int(entry["lineno"], f"{path}.warnings[{idx}].lineno")
    for idx, item in enumerate(_require_list(doc["input_warnings"], f"{path}.input_warnings")):
        validate_input_warning(item, f"{path}.input_warnings[{idx}]")
    _validate_uncertainty_document(doc["uncertainty"], f"{path}.uncertainty")
    for idx, item in enumerate(_require_list(doc["limitations"], f"{path}.limitations")):
        _require_str(item, f"{path}.limitations[{idx}]")


def validate_run_manifest_document(doc: Any) -> None:
    """Closed validation of a completed run manifest. Raises ValueError on any violation."""
    path = "manifest"
    if type(doc) is not dict:
        _fail(path, "expected object")
    schema_ver = doc.get("schema_version")
    if type(schema_ver) is not str or schema_ver not in SUPPORTED_RUN_MANIFEST_SCHEMA_VERSIONS:
        _fail(f"{path}.schema_version", f"unsupported manifest schema {schema_ver!r}")
    is_historical = schema_ver == SCHEMA_VERSION_RUN_MANIFEST_V3
    req_keys = REQUIRED_MANIFEST_KEYS_V3 if is_historical else REQUIRED_MANIFEST_KEYS_V2
    _require_mapping(doc, req_keys, path)
    _validate_common_identity(doc, path)
    start = _require_date(doc["coverage_start_date"], f"{path}.coverage_start_date")
    end = _require_date(doc["coverage_end_date"], f"{path}.coverage_end_date")
    if start > end:
        _fail(path, "coverage dates are inverted")
    _require_enum(doc["summary_schema_version"], sorted(SUPPORTED_SUMMARY_SCHEMA_VERSIONS), f"{path}.summary_schema_version")
    if doc["completed"] is not True:
        _fail(f"{path}.completed", "run-manifest.json reports run is not completed")
    _require_str(doc["completion_timestamp"], f"{path}.completion_timestamp")
    validate_file_identity(doc["config_identity"], f"{path}.config_identity")
    validate_file_identity(doc["admission_identity"], f"{path}.admission_identity")
    if is_historical:
        validate_file_identity(doc["approval_identity"], f"{path}.approval_identity")
    validate_input_identities(doc["input_identities"], f"{path}.input_identities", is_historical=is_historical)
    validate_source_identities(doc["source_identities"], f"{path}.source_identities")
    validate_runtime_identities(doc["runtime_identities"], f"{path}.runtime_identities")
    validate_model_identity(doc["model_identity"], f"{path}.model_identity")
    validate_build_identity(doc["build_identity"], f"{path}.build_identity")

    artifacts = _require_list(doc["artifacts"], f"{path}.artifacts")
    seen: Set[str] = set()
    for idx, entry in enumerate(artifacts):
        item = _require_mapping(entry, {"path", "bytes", "sha256"}, f"{path}.artifacts[{idx}]")
        name = item["path"]
        if type(name) is not str or _ARTIFACT_NAME_REGEX.match(name) is None:
            _fail(f"{path}.artifacts[{idx}].path", f"expected contained relative name, got {name!r}")
        if name in seen:
            _fail(f"{path}.artifacts[{idx}].path", f"duplicate artifact entry {name!r}")
        seen.add(name)
        _require_int(item["bytes"], f"{path}.artifacts[{idx}].bytes")
        _require_sha(item["sha256"], f"{path}.artifacts[{idx}].sha256")
    required_artifacts = REQUIRED_MANIFEST_ARTIFACTS_V3 if is_historical else REQUIRED_MANIFEST_ARTIFACTS_V2
    for name in sorted(required_artifacts - seen):
        _fail(f"{path}.artifacts", f"run-manifest.json missing required artifact '{name}'")
    for name in sorted(seen - required_artifacts):
        _fail(f"{path}.artifacts", f"run-manifest.json has unexpected artifact '{name}'")


@dataclass(frozen=True)
class UncertaintyBlock:
    """
    Closed container for paired test-loss uncertainty results in S2.
    """

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
    point_differences: Tuple[Dict[str, Any], ...]
    block_lengths: Tuple[Dict[str, Any], ...]

    @classmethod
    def from_result(cls, res: UncertaintyResult) -> UncertaintyBlock:
        return cls(
            protocol_id=res.protocol_id,
            method=res.method,
            status=res.status,
            reason=res.reason,
            n=res.n,
            mature_span_count=res.mature_span_count,
            replicates=res.replicates,
            nominal_coverage=res.nominal_coverage,
            quantile_rule=res.quantile_rule,
            block_floor_factor=res.block_floor_factor,
            point_differences=tuple(
                {"pair_id": p.pair_id, "point_difference": p.point_difference}
                for p in res.point_differences
            ),
            block_lengths=tuple(
                {
                    "block_length": bl.block_length,
                    "label": bl.label,
                    "status": bl.status,
                    "reason": bl.reason,
                    "seed": bl.seed,
                    "pairs": tuple(
                        {"pair_id": pr.pair_id, "lower": pr.lower, "upper": pr.upper}
                        for pr in bl.pairs
                    ),
                }
                for bl in res.block_lengths
            ),
        )

    def __post_init__(self) -> None:
        # Same projection the result serializer writes, validated here at construction
        validate_uncertainty_result_document(_uncertainty_document(self))


@dataclass(frozen=True)
class PartitionCounts:
    """
    Inspection counts for an evaluation partition, derived from the canonical planner.

    raw_partition_count: plan decisions assigned to this raw partition.
    eligible_count: canonical retained target origins.
    excluded_count: raw_partition_count - eligible_count (unique exclusions).
    requested_count: comparator target origins, normally eligible_count.
    exclusion_reason_counts: per-reason tallies; reasons can overlap on one origin.
    """

    raw_partition_count: int
    eligible_count: int
    excluded_count: int
    requested_count: int
    exclusion_reason_counts: Dict[str, int]
    model_available_counts: Dict[str, int]

    def __post_init__(self) -> None:
        _validate_counts_document(_counts_document(self), "PartitionCounts")


def _counts_document(counts: PartitionCounts) -> Dict[str, Any]:
    return {
        "raw_partition_count": counts.raw_partition_count,
        "eligible_count": counts.eligible_count,
        "excluded_count": counts.excluded_count,
        "requested_count": counts.requested_count,
        "exclusion_reason_counts": dict(counts.exclusion_reason_counts),
        "model_available_counts": dict(counts.model_available_counts),
    }


@dataclass(frozen=True)
class MethodOriginRecord:
    """
    One method's state at one origin.

    probabilities is None when the method is unavailable. Score fields are None when no
    valid three-way comparison exists: an unscored row never invents a loss. A scored row
    keeps the owner's raw-zero semantics: log_loss None with log_loss_state 'infinite'.
    """

    forecast_state: str
    probabilities: Optional[Tuple[float, float, float]]
    predicted_class: Optional[str] = None
    brier: Optional[float] = None
    log_loss: Optional[float] = None
    log_loss_state: Optional[str] = None


@dataclass(frozen=True)
class PerOriginRecord:
    """Detailed origin-level forecast, realized outcome, and scoring record."""

    origin_index: int
    origin_date: datetime.date
    origin_close: str
    maturity_index: int
    maturity_date: datetime.date
    maturity_close: str
    actual_class: str
    score_state: str
    heuristic_expected_direction: str
    heuristic: MethodOriginRecord
    frequency: MethodOriginRecord
    logistic: MethodOriginRecord

    def __post_init__(self) -> None:
        status = STATUS_SCORED if self.score_state == SCORE_STATE_SCORED else STATUS_EMPTY
        _validate_per_origin_document(_per_origin_document(self), "PerOriginRecord", status)


def _method_row_document(record: MethodOriginRecord) -> Dict[str, Any]:
    return {
        "forecast_state": record.forecast_state,
        "probabilities": None if record.probabilities is None else list(record.probabilities),
        "predicted_class": record.predicted_class,
        "brier": record.brier,
        "log_loss": record.log_loss,
        "log_loss_state": record.log_loss_state,
    }


def _per_origin_document(record: PerOriginRecord) -> Dict[str, Any]:
    heuristic = _method_row_document(record.heuristic)
    heuristic["expected_direction"] = record.heuristic_expected_direction
    return {
        "origin_index": record.origin_index,
        "origin_date": record.origin_date.isoformat(),
        "origin_close": record.origin_close,
        "maturity_index": record.maturity_index,
        "maturity_date": record.maturity_date.isoformat(),
        "maturity_close": record.maturity_close,
        "actual_class": record.actual_class,
        "score_state": record.score_state,
        "heuristic": heuristic,
        "frequency": _method_row_document(record.frequency),
        "logistic": _method_row_document(record.logistic),
    }


@dataclass(frozen=True)
class PartitionResult:
    """Evaluated results and status for a single chronological partition."""

    partition: str
    cutoff_index: int
    cutoff_date: datetime.date
    requested_indices: Tuple[int, ...]
    requested_dates: Tuple[datetime.date, ...]
    counts: PartitionCounts
    heuristic_available: bool
    frequency_available: bool
    frequency_unavailable_reason: Optional[str]
    frequency_block: Dict[str, Any]
    logistic_available: bool
    logistic_unavailable_reason: Optional[str]
    logistic_failure_stage: Optional[str]
    logistic_block: Dict[str, Any]
    comparison_status: str
    comparison_unavailable_reasons: Tuple[str, ...]
    comparison_metrics: Optional[ComparisonMetrics]
    per_origin_records: Tuple[PerOriginRecord, ...]

    def __post_init__(self) -> None:
        if self.partition not in ("development", "test"):
            raise ValueError(f"Invalid partition '{self.partition}'; expected 'development' or 'test'")
        if self.comparison_status not in (STATUS_SCORED, STATUS_EMPTY, STATUS_COMPARISON_UNAVAILABLE):
            raise ValueError(f"Invalid comparison_status '{self.comparison_status}'")
        if self.comparison_status == STATUS_COMPARISON_UNAVAILABLE:
            if self.comparison_metrics is not None:
                raise ValueError("comparison_metrics must be None when comparison_status is comparison_unavailable")
            if len(self.comparison_unavailable_reasons) == 0:
                raise ValueError("comparison_unavailable_reasons must be non-empty when status is comparison_unavailable")
        else:
            if self.comparison_metrics is None:
                raise ValueError(f"comparison_metrics must be present when status is '{self.comparison_status}'")
        _validate_result_partition(_partition_document(self), f"PartitionResult[{self.partition}]", self.partition)


def _serialize_model_metrics(metrics: ModelMetrics) -> Dict[str, Any]:
    """Serializes ModelMetrics into strict summary dictionary."""
    bins_list = []
    for b in metrics.reliability_bins:
        bins_list.append(
            {
                "class_label": b.class_label,
                "bin_index": b.bin_index,
                "count": b.count,
                "mean_probability": b.mean_probability,
                "observed_frequency": b.observed_frequency,
            }
        )

    return {
        "mean_brier": metrics.mean_brier,
        "mean_log_loss": metrics.mean_log_loss,
        "log_loss_state": metrics.log_loss_state,
        "zero_actual_probability_count": metrics.zero_actual_probability_count,
        "tie_count": metrics.tie_count,
        "accuracy": metrics.accuracy,
        "confusion": [list(row) for row in metrics.confusion],
        "class_recall": list(metrics.class_recall),
        "reliability_bins": bins_list,
    }


def _metrics_document(metrics: Optional[ComparisonMetrics]) -> Optional[Dict[str, Any]]:
    if metrics is None:
        return None
    return {
        "sample_count": metrics.sample_count,
        "class_support": list(metrics.class_support),
        "status": metrics.status,
        "models": {
            "heuristic": _serialize_model_metrics(metrics.heuristic),
            "frequency": _serialize_model_metrics(metrics.frequency),
            "logistic": _serialize_model_metrics(metrics.logistic),
        },
    }


def _method_states_document(p_res: PartitionResult) -> Dict[str, Any]:
    return {
        "heuristic": {"available": p_res.heuristic_available},
        "frequency": {
            "available": p_res.frequency_available,
            "unavailable_reason": p_res.frequency_unavailable_reason,
        },
        "logistic": {
            "available": p_res.logistic_available,
            "unavailable_reason": p_res.logistic_unavailable_reason,
            "failure_stage": p_res.logistic_failure_stage,
        },
    }


def _partition_document(p_res: PartitionResult) -> Dict[str, Any]:
    return {
        "partition": p_res.partition,
        "cutoff_index": p_res.cutoff_index,
        "cutoff_date": p_res.cutoff_date.isoformat(),
        "requested_indices": list(p_res.requested_indices),
        "requested_dates": [d.isoformat() for d in p_res.requested_dates],
        "counts": _counts_document(p_res.counts),
        "comparison_status": p_res.comparison_status,
        "comparison_unavailable_reasons": list(p_res.comparison_unavailable_reasons),
        "method_states": _method_states_document(p_res),
        "frequency_block": p_res.frequency_block,
        "logistic_block": p_res.logistic_block,
        "metrics": _metrics_document(p_res.comparison_metrics),
        "per_origin_records": [_per_origin_document(r) for r in p_res.per_origin_records],
    }


@dataclass(frozen=True)
class StudyResult:
    """Validated comprehensive result of an offline prediction study."""

    run_id: str
    study_id: str
    protocol_id: str
    data_kind: str
    development_status: str
    claim_label: str
    coverage_start_date: datetime.date
    coverage_end_date: datetime.date
    development_start: datetime.date
    test_start: datetime.date
    admission_inventory: Dict[str, Any]
    config_identity: Dict[str, Any]
    admission_identity: Dict[str, Any]
    input_identities: Dict[str, Any]
    source_identities: Dict[str, Any]
    runtime_identities: Dict[str, Any]
    model_identity: Dict[str, Any]
    build_identity: Dict[str, Any]
    replay_identity: Dict[str, Any]
    private_paths: Dict[str, str]
    comparator_metadata: Dict[str, Any]
    partitions: Dict[str, PartitionResult]
    warnings: Tuple[Dict[str, Any], ...]
    input_warnings: Tuple[Dict[str, Any], ...]
    uncertainty: UncertaintyBlock
    approval_identity: Optional[Dict[str, Any]] = None
    limitations: Tuple[str, ...] = SYNTHETIC_LIMITATIONS

    def __post_init__(self) -> None:
        if not is_valid_identifier(self.run_id):
            raise ValueError("run_id must be a portable identifier")
        if not is_valid_identifier(self.study_id):
            raise ValueError("study_id must be a portable identifier")
        if type(self.protocol_id) is not str or self.protocol_id not in SUPPORTED_PROTOCOL_IDS:
            raise ValueError(f"Unsupported protocol_id '{self.protocol_id}'")
        if self.data_kind not in SUPPORTED_DATA_KINDS:
            raise ValueError(f"Invalid data_kind '{self.data_kind}'")
        if self.data_kind == DATA_KIND_HISTORICAL:
            if self.development_status != DEVELOPMENT_STATUS_HISTORICAL:
                raise ValueError(f"Invalid development_status '{self.development_status}' for historical data")
            if self.approval_identity is None:
                raise ValueError("approval_identity is required for historical study result")
        else:
            if self.development_status != DEVELOPMENT_STATUS_SYNTHETIC:
                raise ValueError(f"Invalid development_status '{self.development_status}' for synthetic data")
            if self.approval_identity is not None:
                raise ValueError("approval_identity must be None for synthetic study result")
        if "development" not in self.partitions or "test" not in self.partitions:
            raise ValueError("partitions must include 'development' and 'test'")


@dataclass(frozen=True)
class ReleaseDescriptor:
    """
    Portable candidate descriptor binding a summary to its completed run.

    Constructing one approves nothing: it stays private, and matching hashes are
    consistency evidence, not publisher authentication.
    """

    schema_version: str
    run_id: str
    study_id: str
    protocol_id: str
    summary_schema_version: str
    coverage_end_date: str
    summary_bytes: int
    summary_sha256: str
    manifest_bytes: int
    manifest_sha256: str

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION_RELEASE_DESCRIPTOR:
            raise ValueError(f"Invalid release descriptor schema_version '{self.schema_version}'")
        if not is_valid_identifier(self.run_id):
            raise ValueError("run_id must be a portable identifier")
        if not is_valid_identifier(self.study_id):
            raise ValueError("study_id must be a portable identifier")
        if type(self.protocol_id) is not str or not self.protocol_id:
            raise ValueError("protocol_id must be a non-empty string")
        if type(self.summary_schema_version) is not str or not self.summary_schema_version:
            raise ValueError("summary_schema_version must be a non-empty string")
        _require_date(self.coverage_end_date, "descriptor.coverage_end_date")
        if type(self.summary_bytes) is not int or self.summary_bytes <= 0:
            raise ValueError("summary_bytes must be a positive int")
        if type(self.manifest_bytes) is not int or self.manifest_bytes <= 0:
            raise ValueError("manifest_bytes must be a positive int")
        if type(self.summary_sha256) is not str or _SHA256_HEX_REGEX.match(self.summary_sha256) is None:
            raise ValueError("summary_sha256 must be a 64-character hex string")
        if type(self.manifest_sha256) is not str or _SHA256_HEX_REGEX.match(self.manifest_sha256) is None:
            raise ValueError("manifest_sha256 must be a 64-character hex string")


_ASSET_LABELS: Dict[str, Tuple[str, str]] = {
    DATA_KIND_SYNTHETIC: (SOURCE_KIND_SYNTHETIC, "Synthetic fixture on the Nifty 50 price-index schema"),
    DATA_KIND_HISTORICAL: (SOURCE_KIND_HISTORICAL, "Admitted historical market data on the Nifty 50 price-index schema"),
}
_ADMISSION_SUMMARY_KEYS: Tuple[str, ...] = (
    "mature_test_start_index",
    "mature_test_end_index",
    "mature_test_span_count",
    "warmup_gap_count",
    "missing_vix_gap_count",
    "union_gap_count",
    "gap_digest",
    "policy",
)
_SUMMARY_PARTITION_KEYS: Tuple[str, ...] = (
    "partition",
    "cutoff_index",
    "cutoff_date",
    "counts",
    "comparison_status",
    "comparison_unavailable_reasons",
    "method_states",
    "metrics",
)


def project_panel_summary(result_doc: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Projects the portable aggregate from a private result document, in memory or as saved.

    This is the only definition of the summary contents: the builder applies it to a fresh
    result document and the completed-run checker applies it to the saved result.json, so a
    summary that differs from its own result cannot verify. An explicit whitelist: no raw
    prices, CSV inputs, per-origin records, coefficients, absolute paths or tracebacks.
    """
    is_historical = result_doc["data_kind"] == DATA_KIND_HISTORICAL
    source_kind, asset_label = _ASSET_LABELS[result_doc["data_kind"]]
    if is_historical:
        # Raw provider and calendar digests are withheld; these compound digests still need owner review
        provenance = {
            "config_sha256": result_doc["config_identity"]["sha256"],
            "admission_sha256": result_doc["admission_identity"]["sha256"],
            "approval_sha256": result_doc["approval_identity"]["sha256"],
        }
    else:
        provenance = {
            "config_sha256": result_doc["config_identity"]["sha256"],
            "admission_sha256": result_doc["admission_identity"]["sha256"],
            "nifty_input_sha256": result_doc["input_identities"]["nifty"]["sha256"],
            "vix_input_sha256": result_doc["input_identities"]["vix"]["sha256"],
            "calendar_sha256": result_doc["input_identities"]["calendar"]["sha256"],
        }
    admission = result_doc["admission"]
    return {
        "schema_version": SCHEMA_VERSION_SUMMARY_V3 if is_historical else SCHEMA_VERSION_SUMMARY_V2,
        "run_id": result_doc["run_id"],
        "study_id": result_doc["study_id"],
        "protocol_id": result_doc["protocol_id"],
        "data_kind": result_doc["data_kind"],
        "development_status": result_doc["development_status"],
        "claim_label": result_doc["claim_label"],
        "dataset_attribution": {
            "source_kind": source_kind,
            "asset_label": asset_label,
            "series_id": "^NSEI",
            "coverage_start_date": result_doc["coverage_start_date"],
            "coverage_end_date": result_doc["coverage_end_date"],
        },
        "replay_identity": dict(result_doc["replay_identity"]),
        "provenance_identity": provenance,
        "chronological_cutoffs": {
            "development_start": result_doc["development_start"],
            "test_start": result_doc["test_start"],
        },
        "admission_summary": {key: admission.get(key) for key in _ADMISSION_SUMMARY_KEYS},
        "fixed_definitions": {
            "classes": list(ORDERED_CLASSES),
            "neutral_band": "inclusive_half_percent",
            "horizon_sessions": 20,
            "primary_probability_metric": "mean_brier",
            "log_loss_zero_policy": "infinite_with_count_retention",
        },
        "partitions": {
            name: {key: result_doc["partitions"][name][key] for key in _SUMMARY_PARTITION_KEYS}
            for name in ("development", "test")
        },
        "uncertainty": result_doc["uncertainty"],
        "limitations": list(result_doc["limitations"]),
    }


def build_panel_summary(result: StudyResult) -> Dict[str, Any]:
    """
    Constructs the versioned aggregate panel-summary dictionary from a validated StudyResult.

    Retains explicit zero/infinite/empty meanings and validates the closed schema before
    returning. Contents come from project_panel_summary over the result document.
    """
    summary = project_panel_summary(build_result_document(result))
    validate_summary_document(summary)
    return summary


def _uncertainty_document(block: UncertaintyBlock) -> Dict[str, Any]:
    return {
        "protocol_id": block.protocol_id,
        "method": block.method,
        "status": block.status,
        "reason": block.reason,
        "n": block.n,
        "mature_span_count": block.mature_span_count,
        "replicates": block.replicates,
        "nominal_coverage": block.nominal_coverage,
        "quantile_rule": block.quantile_rule,
        "block_floor_factor": block.block_floor_factor,
        "point_differences": [dict(p) for p in block.point_differences],
        "block_lengths": [
            {
                "block_length": b["block_length"],
                "label": b["label"],
                "status": b["status"],
                "reason": b["reason"],
                "seed": b["seed"],
                "pairs": [dict(pr) for pr in b["pairs"]],
            }
            for b in block.block_lengths
        ],
    }


def build_result_document(result: StudyResult) -> Dict[str, Any]:
    """
    Constructs the private complete result artifact with explicit fields, not a dataclass dump.

    Holds per-origin rows, returned fit state and private paths, so it never leaves the run
    root; the portable aggregate is build_panel_summary.
    """
    is_historical = result.data_kind == DATA_KIND_HISTORICAL
    document: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION_RESULT_V3 if is_historical else SCHEMA_VERSION_RESULT_V2,
        "run_id": result.run_id,
        "study_id": result.study_id,
        "protocol_id": result.protocol_id,
        "data_kind": result.data_kind,
        "development_status": result.development_status,
        "claim_label": result.claim_label,
        "coverage_start_date": result.coverage_start_date.isoformat(),
        "coverage_end_date": result.coverage_end_date.isoformat(),
        "development_start": result.development_start.isoformat(),
        "test_start": result.test_start.isoformat(),
        "admission": result.admission_inventory,
        "config_identity": result.config_identity,
        "admission_identity": result.admission_identity,
        "input_identities": result.input_identities,
        "source_identities": result.source_identities,
        "runtime_identities": result.runtime_identities,
        "model_identity": result.model_identity,
        "build_identity": result.build_identity,
        "replay_identity": result.replay_identity,
        "private_paths": result.private_paths,
        "comparator_metadata": result.comparator_metadata,
        "partitions": {name: _partition_document(result.partitions[name]) for name in ("development", "test")},
        "warnings": [dict(w) for w in result.warnings],
        "input_warnings": [dict(w) for w in result.input_warnings],
        "uncertainty": _uncertainty_document(result.uncertainty),
        "limitations": list(result.limitations),
    }
    if is_historical:
        document["approval_identity"] = result.approval_identity
    validate_result_document(document)
    return document


def build_predictions_document(result: StudyResult) -> Dict[str, Any]:
    """Projects the per-origin rows of both partitions, the same rows held in result.json."""
    return {
        name: [_per_origin_document(r) for r in result.partitions[name].per_origin_records]
        for name in ("development", "test")
    }


def serialize_strict_json(obj: Any) -> bytes:
    """
    Serializes an object to deterministic strict UTF-8 JSON bytes with allow_nan=False.
    Appends exactly one final LF newline.
    """
    try:
        text = json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False)
    except (ValueError, OverflowError, TypeError) as exc:
        raise ValueError(f"Strict JSON serialization failed: {exc}") from exc
    return text.encode("utf-8") + b"\n"


def render_report_markdown(result: StudyResult) -> str:
    """
    Renders human-readable Markdown report from the SAME StudyResult object.
    Beginner-readable summary of study parameters, status, and performance.
    """
    lines = [
        f"# Prediction Evaluation Study Report: {result.study_id}",
        "",
        f"- **Run ID**: `{result.run_id}`",
        f"- **Protocol ID**: `{result.protocol_id}`",
        f"- **Data Kind**: `{result.data_kind}`",
        f"- **Development Status**: `{result.development_status}`",
        f"- **Claim**: {result.claim_label}",
        f"- **Coverage Span**: {result.coverage_start_date.isoformat()} to {result.coverage_end_date.isoformat()}",
        f"- **Development Start**: {result.development_start.isoformat()}",
        f"- **Test Start**: {result.test_start.isoformat()}",
        "",
        "## Admission Gap Inventory",
        "",
        f"- Mature Test Span: `[{result.admission_inventory.get('mature_test_start_index')}, {result.admission_inventory.get('mature_test_end_index')})` ({result.admission_inventory.get('mature_test_span_count')} sessions)",
        f"- Warmup Gaps: {result.admission_inventory.get('warmup_gap_count')}",
        f"- Missing VIX Gaps: {result.admission_inventory.get('missing_vix_gap_count')}",
        f"- Union Excluded Gaps: {result.admission_inventory.get('union_gap_count')}",
        f"- Gap Position Digest: `{result.admission_inventory.get('gap_digest')}`",
        f"- Policy: `{result.admission_inventory.get('policy')}`",
        "",
        "## Partitions and Comparison Metrics",
        "",
    ]

    for part_name in ("development", "test"):
        p_res = result.partitions[part_name]
        lines.append(f"### {part_name.capitalize()} Partition")
        lines.append(f"- Cutoff Date: {p_res.cutoff_date.isoformat()} (Index {p_res.cutoff_index})")
        lines.append(f"- Raw Partition Origins: {p_res.counts.raw_partition_count}")
        lines.append(f"- Eligible Observations: {p_res.counts.eligible_count}")
        lines.append(f"- Excluded Observations: {p_res.counts.excluded_count}")
        lines.append(f"- Requested Observations: {p_res.counts.requested_count}")
        if p_res.counts.exclusion_reason_counts:
            reason_text = ", ".join(
                f"{reason}={count}" for reason, count in sorted(p_res.counts.exclusion_reason_counts.items())
            )
            lines.append(f"- Exclusion Reasons (may overlap): {reason_text}")
        lines.append(f"- Comparison Status: `{p_res.comparison_status}`")

        if p_res.comparison_status == STATUS_COMPARISON_UNAVAILABLE:
            reasons_str = ", ".join(p_res.comparison_unavailable_reasons)
            lines.append(f"- Unavailability Reasons: {reasons_str}")
            available = p_res.counts.model_available_counts
            lines.append(
                f"- Usable Forecasts: heuristic={available['heuristic']}, "
                f"frequency={available['frequency']}, logistic={available['logistic']}"
            )
        elif p_res.comparison_metrics is not None:
            cm = p_res.comparison_metrics
            lines.append(f"- Scored Observations: {cm.sample_count}")
            lines.append(f"- Class Support (BEAR, NEUTRAL, BULL): {cm.class_support}")
            lines.append("")
            lines.append("| Metric | Heuristic | Frequency | Logistic |")
            lines.append("| :--- | :---: | :---: | :---: |")

            def _fmt(val: Optional[float]) -> str:
                if val is None:
                    return "N/A"
                return f"{val:.4f}"

            lines.append(f"| Mean Brier Score | {_fmt(cm.heuristic.mean_brier)} | {_fmt(cm.frequency.mean_brier)} | {_fmt(cm.logistic.mean_brier)} |")
            lines.append(f"| Mean Log Loss | {_fmt(cm.heuristic.mean_log_loss)} ({cm.heuristic.log_loss_state}) | {_fmt(cm.frequency.mean_log_loss)} ({cm.frequency.log_loss_state}) | {_fmt(cm.logistic.mean_log_loss)} ({cm.logistic.log_loss_state}) |")
            lines.append(f"| Accuracy | {_fmt(cm.heuristic.accuracy)} | {_fmt(cm.frequency.accuracy)} | {_fmt(cm.logistic.accuracy)} |")
            lines.append(f"| Zero Prob Count | {cm.heuristic.zero_actual_probability_count} | {cm.frequency.zero_actual_probability_count} | {cm.logistic.zero_actual_probability_count} |")
            lines.append(f"| Tie Count | {cm.heuristic.tie_count} | {cm.frequency.tie_count} | {cm.logistic.tie_count} |")
        lines.append("")

    lines.append("## Statistical Uncertainty")
    lines.append(f"- Protocol ID: `{result.uncertainty.protocol_id}`")
    lines.append(f"- Method: `{result.uncertainty.method}`")
    lines.append(f"- Status: `{result.uncertainty.status}`")
    if result.uncertainty.reason:
        lines.append(f"- Top Reason: {result.uncertainty.reason}")
    lines.append(f"- Cohort Size (n): {result.uncertainty.n} (Mature Span: {result.uncertainty.mature_span_count})")
    lines.append(f"- Replicates: {result.uncertainty.replicates}, Nominal Coverage: {result.uncertainty.nominal_coverage}, Quantile Rule: `{result.uncertainty.quantile_rule}`")
    lines.append("")
    lines.append("### Point Differences (Test Cohort)")
    for pd in result.uncertainty.point_differences:
        val = pd.get("point_difference")
        val_str = f"{val:+.6f}" if val is not None else "None"
        lines.append(f"- `{pd.get('pair_id')}`: {val_str}")
    lines.append("")
    lines.append("### Stationary Block Length Views")
    for bl in result.uncertainty.block_lengths:
        lines.append(f"#### Block Length {bl.get('block_length')} (`{bl.get('status')}`)")
        lines.append(f"- Label: {bl.get('label')}")
        lines.append(f"- Seed: `{bl.get('seed')}`")
        if bl.get("reason"):
            lines.append(f"- Reason: {bl.get('reason')}")
        for pr in bl.get("pairs", ()):
            lo = pr.get("lower")
            hi = pr.get("upper")
            lo_str = f"{lo:+.6f}" if lo is not None else "None"
            hi_str = f"{hi:+.6f}" if hi is not None else "None"
            lines.append(f"  - `{pr.get('pair_id')}`: [{lo_str}, {hi_str}]")
    lines.append("")

    lines.append("## Limitations and Disclosures")
    for lim in result.limitations:
        lines.append(f"- {lim}")
    lines.append("")

    return "\n".join(lines)


def build_run_manifest(
    *,
    run_id: str,
    study_id: str,
    protocol_id: str,
    data_kind: str,
    development_status: str,
    coverage_start_date: datetime.date,
    coverage_end_date: datetime.date,
    artifacts: Sequence[Dict[str, Any]],
    config_identity: Dict[str, Any],
    admission_identity: Dict[str, Any],
    input_identities: Dict[str, Any],
    source_identities: Dict[str, Any],
    runtime_identities: Dict[str, Any],
    model_identity: Dict[str, Any],
    build_identity: Dict[str, Any],
    completion_timestamp: str,
    approval_identity: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Constructs the run-manifest.json dictionary.
    Excludes its own path and hash. Written LAST after all required artifacts are validated.
    Artifact entries are relative names. Synthetic-v2 identities are path-free; historical-v3
    input identities carry each original file's private path, source URL and source-use note,
    so a v3 manifest is a private artifact and never a public asset.
    """
    is_historical = data_kind == DATA_KIND_HISTORICAL
    manifest: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION_RUN_MANIFEST_V3 if is_historical else SCHEMA_VERSION_RUN_MANIFEST_V2,
        "run_id": run_id,
        "study_id": study_id,
        "protocol_id": protocol_id,
        "data_kind": data_kind,
        "development_status": development_status,
        "coverage_start_date": coverage_start_date.isoformat(),
        "coverage_end_date": coverage_end_date.isoformat(),
        "summary_schema_version": SCHEMA_VERSION_SUMMARY_V3 if is_historical else SCHEMA_VERSION_SUMMARY_V2,
        "artifacts": [dict(a) for a in artifacts],
        "config_identity": dict(config_identity),
        "admission_identity": dict(admission_identity),
        "input_identities": input_identities,
        "source_identities": dict(source_identities),
        "runtime_identities": dict(runtime_identities),
        "model_identity": dict(model_identity),
        "build_identity": dict(build_identity),
        "completed": True,
        "completion_timestamp": completion_timestamp,
    }
    if is_historical:
        if approval_identity is None:
            raise ValueError("approval_identity is required for historical run manifest")
        manifest["approval_identity"] = dict(approval_identity)
    validate_run_manifest_document(manifest)
    return manifest


def build_release_descriptor(
    *,
    run_id: str,
    study_id: str,
    protocol_id: str,
    summary_schema_version: str,
    coverage_end_date: str,
    summary_bytes: int,
    summary_sha256: str,
    manifest_bytes: int,
    manifest_sha256: str,
) -> ReleaseDescriptor:
    """Builds a portable ReleaseDescriptor binding candidate summary to verified manifest."""
    return ReleaseDescriptor(
        schema_version=SCHEMA_VERSION_RELEASE_DESCRIPTOR,
        run_id=run_id,
        study_id=study_id,
        protocol_id=protocol_id,
        summary_schema_version=summary_schema_version,
        coverage_end_date=coverage_end_date,
        summary_bytes=summary_bytes,
        summary_sha256=summary_sha256.upper(),
        manifest_bytes=manifest_bytes,
        manifest_sha256=manifest_sha256.upper(),
    )


def release_descriptor_document(descriptor: ReleaseDescriptor) -> Dict[str, Any]:
    """Projects a descriptor to its portable document; it holds no private path."""
    return {
        "schema_version": descriptor.schema_version,
        "run_id": descriptor.run_id,
        "study_id": descriptor.study_id,
        "protocol_id": descriptor.protocol_id,
        "summary_schema_version": descriptor.summary_schema_version,
        "coverage_end_date": descriptor.coverage_end_date,
        "summary_bytes": descriptor.summary_bytes,
        "summary_sha256": descriptor.summary_sha256,
        "manifest_bytes": descriptor.manifest_bytes,
        "manifest_sha256": descriptor.manifest_sha256,
    }


def parse_release_descriptor(raw: bytes) -> ReleaseDescriptor:
    """Parses a portable descriptor strictly. A caller treats ValueError as the malformed state."""
    doc = _require_mapping(
        parse_strict_json_bytes(raw),
        {
            "schema_version",
            "run_id",
            "study_id",
            "protocol_id",
            "summary_schema_version",
            "coverage_end_date",
            "summary_bytes",
            "summary_sha256",
            "manifest_bytes",
            "manifest_sha256",
        },
        "descriptor",
    )
    return ReleaseDescriptor(**doc)


def build_candidate_descriptor(summary_bytes: bytes, manifest_bytes: bytes) -> ReleaseDescriptor:
    """Derives a private candidate descriptor from exact bytes that pass the completion binding."""
    ok, reason = verify_completion_binding(summary_bytes, manifest_bytes)
    if not ok:
        raise ValueError(f"Cannot describe an incomplete run: {reason}")
    summary_doc = parse_strict_json_bytes(summary_bytes)
    return build_release_descriptor(
        run_id=summary_doc["run_id"],
        study_id=summary_doc["study_id"],
        protocol_id=summary_doc["protocol_id"],
        summary_schema_version=summary_doc["schema_version"],
        coverage_end_date=summary_doc["dataset_attribution"]["coverage_end_date"],
        summary_bytes=len(summary_bytes),
        summary_sha256=hashlib.sha256(summary_bytes).hexdigest(),
        manifest_bytes=len(manifest_bytes),
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
    )


def verify_completion_binding(summary_bytes: bytes, manifest_bytes: bytes) -> Tuple[bool, str]:
    """
    Verifies panel-summary.json against a complete run-manifest.json. Returns (is_valid, reason).

    Rejects malformed or non-strict JSON, closed-schema violations, an incomplete manifest,
    summary/manifest identity disagreement, and a summary byte count or SHA-256 mismatch.
    """
    try:
        summary_doc = parse_strict_json_bytes(summary_bytes)
    except ValueError as exc:
        return False, f"Malformed panel-summary.json: {exc}"
    try:
        validate_summary_document(summary_doc)
    except ValueError as exc:
        return False, f"Invalid panel-summary.json: {exc}"

    try:
        manifest_doc = parse_strict_json_bytes(manifest_bytes)
    except ValueError as exc:
        return False, f"Malformed run-manifest.json: {exc}"
    try:
        validate_run_manifest_document(manifest_doc)
    except ValueError as exc:
        return False, f"Invalid run-manifest.json: {exc}"

    attribution = summary_doc["dataset_attribution"]
    relations = (
        ("run_id", summary_doc["run_id"], manifest_doc["run_id"]),
        ("study_id", summary_doc["study_id"], manifest_doc["study_id"]),
        ("protocol_id", summary_doc["protocol_id"], manifest_doc["protocol_id"]),
        ("data_kind", summary_doc["data_kind"], manifest_doc["data_kind"]),
        ("development_status", summary_doc["development_status"], manifest_doc["development_status"]),
        ("schema_version", summary_doc["schema_version"], manifest_doc["summary_schema_version"]),
        ("coverage_start_date", attribution["coverage_start_date"], manifest_doc["coverage_start_date"]),
        ("coverage_end_date", attribution["coverage_end_date"], manifest_doc["coverage_end_date"]),
    )
    for name, summary_value, manifest_value in relations:
        if summary_value != manifest_value:
            return False, f"Summary {name} {summary_value!r} does not match manifest {manifest_value!r}"

    summary_entry = next(a for a in manifest_doc["artifacts"] if a["path"] == "panel-summary.json")
    actual_summary_bytes = len(summary_bytes)
    actual_summary_sha256 = hashlib.sha256(summary_bytes).hexdigest().upper()
    if summary_entry["bytes"] != actual_summary_bytes:
        return False, f"Summary byte count mismatch: manifest says {summary_entry['bytes']}, actual {actual_summary_bytes}"
    if summary_entry["sha256"].upper() != actual_summary_sha256:
        return False, f"Summary SHA-256 mismatch: manifest says {summary_entry['sha256']}, actual {actual_summary_sha256}"

    return True, "Completion binding verified"


def verify_promotion_binding(
    summary_bytes: bytes,
    manifest_bytes: bytes,
    descriptor: Optional[ReleaseDescriptor],
) -> Tuple[bool, str]:
    """
    Verifies the checked promotion binding of a summary, a completed manifest and a descriptor.

    Returns (is_valid, reason). A descriptor is required. Beyond verify_completion_binding it
    must agree on run, study, protocol, supported summary schema and coverage, and it must
    carry the exact summary and manifest byte counts and hashes. Success is hash consistency
    only: it neither authenticates a publisher nor approves any release.
    """
    if descriptor is None:
        return False, "Promotion requires a release descriptor"

    ok, reason = verify_completion_binding(summary_bytes, manifest_bytes)
    if not ok:
        return False, reason

    summary_doc = parse_strict_json_bytes(summary_bytes)
    if descriptor.summary_schema_version not in SUPPORTED_SUMMARY_SCHEMA_VERSIONS:
        return False, f"Unsupported descriptor summary_schema_version '{descriptor.summary_schema_version}'"
    if descriptor.protocol_id not in SUPPORTED_PROTOCOL_IDS:
        return False, f"Unsupported descriptor protocol_id '{descriptor.protocol_id}'"

    relations = (
        ("run_id", descriptor.run_id, summary_doc["run_id"]),
        ("study_id", descriptor.study_id, summary_doc["study_id"]),
        ("protocol_id", descriptor.protocol_id, summary_doc["protocol_id"]),
        ("summary_schema_version", descriptor.summary_schema_version, summary_doc["schema_version"]),
        ("coverage_end_date", descriptor.coverage_end_date, summary_doc["dataset_attribution"]["coverage_end_date"]),
    )
    for name, descriptor_value, summary_value in relations:
        if descriptor_value != summary_value:
            return False, f"Descriptor {name} '{descriptor_value}' does not match '{summary_value}'"

    actual_summary_bytes = len(summary_bytes)
    actual_summary_sha256 = hashlib.sha256(summary_bytes).hexdigest().upper()
    if descriptor.summary_bytes != actual_summary_bytes:
        return False, f"Descriptor summary_bytes {descriptor.summary_bytes} does not match actual {actual_summary_bytes}"
    if descriptor.summary_sha256.upper() != actual_summary_sha256:
        return False, f"Descriptor summary_sha256 {descriptor.summary_sha256} does not match actual {actual_summary_sha256}"

    actual_manifest_bytes = len(manifest_bytes)
    actual_manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest().upper()
    if descriptor.manifest_bytes != actual_manifest_bytes:
        return False, f"Descriptor manifest_bytes {descriptor.manifest_bytes} does not match actual {actual_manifest_bytes}"
    if descriptor.manifest_sha256.upper() != actual_manifest_sha256:
        return False, f"Descriptor manifest_sha256 {descriptor.manifest_sha256} does not match actual {actual_manifest_sha256}"

    return True, "Binding verified"


def verify_completed_run(run_dir: Union[str, Path]) -> Tuple[bool, str]:
    """
    Read-only check that a run directory holds every required file with the exact manifest
    bytes and hashes, the completion binding holds, and no failure record exists.
    """
    root = Path(run_dir)
    try:
        manifest_bytes = (root / "run-manifest.json").read_bytes()
        summary_bytes = (root / "panel-summary.json").read_bytes()
    except OSError as exc:
        return False, f"Run artifacts unavailable: {exc}"

    ok, reason = verify_completion_binding(summary_bytes, manifest_bytes)
    if not ok:
        return False, reason
    if (root / FAILURE_RECORD_NAME).exists():
        return False, "A failure record exists in the run directory"

    manifest_doc = parse_strict_json_bytes(manifest_bytes)
    if manifest_doc["run_id"] != root.resolve().name:
        return False, f"Manifest run_id '{manifest_doc['run_id']}' does not match the run directory"
    for entry in manifest_doc["artifacts"]:
        try:
            data = (root / entry["path"]).read_bytes()
        except OSError as exc:
            return False, f"Required artifact '{entry['path']}' unavailable: {exc}"
        if len(data) != entry["bytes"]:
            return False, f"Artifact '{entry['path']}' byte count mismatch"
        if hashlib.sha256(data).hexdigest().upper() != entry["sha256"].upper():
            return False, f"Artifact '{entry['path']}' SHA-256 mismatch"

    # Cross-artifact semantic relations check
    sem_ok, sem_reason = verify_study_artifacts_semantic_relations(root)
    if not sem_ok:
        return False, sem_reason

    # The manifest repeats the result's provenance, so the two must not diverge
    result_doc = parse_strict_json_bytes((root / "result.json").read_bytes())
    keys_to_compare = [
        "run_id",
        "study_id",
        "protocol_id",
        "coverage_start_date",
        "coverage_end_date",
        "config_identity",
        "admission_identity",
        "input_identities",
        "source_identities",
        "runtime_identities",
        "model_identity",
        "build_identity",
    ]
    if manifest_doc.get("schema_version") == SCHEMA_VERSION_RUN_MANIFEST_V3:
        keys_to_compare.append("approval_identity")
    for key in keys_to_compare:
        if manifest_doc.get(key) != result_doc.get(key):
            return False, f"Manifest {key} does not match result.json"

    return True, "Completed run verified"


def _raw_identity(raw: bytes) -> Dict[str, Any]:
    return {"raw_byte_count": len(raw), "sha256": hashlib.sha256(raw).hexdigest().upper()}


def _relate_axis(request: UncertaintyRequest, admission: Mapping[str, Any], result: Mapping[str, Any]) -> None:
    """
    Binds the input axis to every authoritative axis fact a run keeps.

    Admission holds the session count, end dates and mature bounds, not each interior date. The
    persisted rows add the origin and maturity dates they name; other interior dates have no
    independent record to compare with, so hash identity is their only binding.
    """
    axis = [day.isoformat() for day in request.axis_dates]
    total = len(axis)
    start = request.test_start_index
    end = max(start, total - HORIZON_SESSIONS)
    test_part = result["partitions"]["test"]
    development_part = result["partitions"]["development"]

    if result["admission"] != admission:
        _fail("result.admission", "does not match admission.json")
    axis_facts = admission["axis"]
    if total != axis_facts["session_count"] or axis[0] != axis_facts["first_date"] or axis[-1] != axis_facts["last_date"]:
        _fail("uncertainty-input.axis_dates", "does not match the admission axis count and end dates")
    if axis[0] != result["coverage_start_date"] or axis[-1] != result["coverage_end_date"]:
        _fail("uncertainty-input.axis_dates", "does not match the result coverage dates")
    if start != admission["mature_test_start_index"] or start != test_part["cutoff_index"]:
        _fail("uncertainty-input.test_start_index", f"{start} does not match the admission and test cutoff index")
    if end != admission["mature_test_end_index"] or end - start != admission["mature_test_span_count"]:
        _fail("uncertainty-input", "mature span does not match admission")
    if axis[start] != result["test_start"] or axis[start] != admission["test_start"] or axis[start] != test_part["cutoff_date"]:
        _fail("uncertainty-input.axis_dates", "test start date does not match result and admission")
    if list(request.union_gap_positions) != admission["union_gap_positions"]:
        _fail("uncertainty-input.union_gap_positions", "does not match admission union_gap_positions")

    development_index = development_part["cutoff_index"]
    if (
        development_index >= total
        or axis[development_index] != result["development_start"]
        or axis[development_index] != development_part["cutoff_date"]
    ):
        _fail("result.partitions.development", "cutoff index or date does not match the input axis")
    if result["development_start"] != admission["development_start"]:
        _fail("result.development_start", "does not match admission")

    rule = admission.get("date_selection_rule")
    if rule == DATE_SELECTION_RULE_HISTORICAL:
        if total < HISTORICAL_MIN_SESSIONS:
            _fail("axis", f"historical axis must have >= {HISTORICAL_MIN_SESSIONS} sessions, got {total}")
        exp_d, exp_t, exp_e = historical_split_indices(total)
        if admission.get("development_start_index") != exp_d or development_index != exp_d:
            _fail("axis", f"development cutoff index {development_index} does not match expected {exp_d}")
        if start != exp_t:
            _fail("axis", f"test cutoff index {start} does not match expected {exp_t}")
        if end != exp_e:
            _fail("axis", f"mature test end index {end} does not match expected {exp_e}")
        if admission.get("mature_test_span_count") != HISTORICAL_TEST_SPAN:
            _fail("axis", f"mature_test_span_count must be exactly {HISTORICAL_TEST_SPAN}, got {admission.get('mature_test_span_count')}")

    for part in (development_part, test_part):
        for row in part["per_origin_records"]:
            if row["maturity_index"] >= total:
                _fail("result.per_origin_records", f"maturity_index {row['maturity_index']} is beyond the input axis")
            if axis[row["origin_index"]] != row["origin_date"] or axis[row["maturity_index"]] != row["maturity_date"]:
                _fail("uncertainty-input.axis_dates", f"disagrees with persisted row {row['origin_index']}")


def _relate_input_rows(request: UncertaintyRequest, test_part: Mapping[str, Any]) -> None:
    """Compares the saved TEST projection with the persisted scorer rows, key by key."""
    if request.comparison_status != test_part["comparison_status"]:
        _fail("uncertainty-input.comparison_status", f"{request.comparison_status!r} != test {test_part['comparison_status']!r}")
    states = test_part["method_states"]
    if request.method_available != {name: states[name]["available"] for name in MODEL_NAMES}:
        _fail("uncertainty-input.method_available", "does not match the test method states")

    records = test_part["per_origin_records"]
    keys = [(key.origin_index, key.origin_date.isoformat()) for key in request.requested_keys]
    if keys != [(row["origin_index"], row["origin_date"]) for row in records]:
        _fail("uncertainty-input.requested_keys", "do not match the test origin records")

    if request.method_rows is None:
        return
    for name in MODEL_NAMES:
        rows = request.method_rows[name]
        if len(rows) != len(records):
            _fail(f"uncertainty-input.method_rows.{name}", "count differs from the test origin records")
        for pos, (row, record) in enumerate(zip(rows, records)):
            if row.origin_index != record["origin_index"] or row.origin_date.isoformat() != record["origin_date"]:
                _fail(f"uncertainty-input.method_rows.{name}[{pos}]", "key mismatch with the test origin record")
            # repr keeps the loss exact: == would equate signed zeros and an int with its float
            if repr(row.brier) != repr(record[name]["brier"]):
                _fail(f"uncertainty-input.method_rows.{name}[{pos}]", "loss mismatch with test origin record brier")


def _relate_statistics(request: UncertaintyRequest, uncertainty: Mapping[str, Any], summary_uncertainty: Mapping[str, Any]) -> None:
    """Derives the expected state from the saved cohort. Nothing here resamples or rescores."""
    if summary_uncertainty != uncertainty:
        _fail("panel-summary.uncertainty", "summary.uncertainty does not match result.uncertainty")

    n = len(request.requested_keys)
    total = len(request.axis_dates)
    span = max(request.test_start_index, total - HORIZON_SESSIONS) - request.test_start_index
    if uncertainty["n"] != n or uncertainty["mature_span_count"] != span:
        _fail("result.uncertainty", f"n and mature_span_count must be {n} and {span}")

    common_reason = common_unavailable_reason(request.comparison_status, n, len(request.union_gap_positions))
    cleared = () if common_reason is not None else available_block_lengths(n)
    expected_reason = common_reason if common_reason is not None or cleared else REASON_INSUFFICIENT_BLOCKS
    if uncertainty["reason"] != expected_reason:
        _fail("result.uncertainty.reason", f"must be {expected_reason!r} for the saved cohort")
    for view in uncertainty["block_lengths"]:
        if (view["status"] == UNCERTAINTY_STATUS_AVAILABLE) != (view["block_length"] in cleared):
            _fail("result.uncertainty.block_lengths", f"length {view['block_length']} state contradicts the saved cohort")

    if common_reason in NO_POINT_REASONS:
        return
    differences = paired_loss_differences(request.method_rows)
    for entry, values in zip(uncertainty["point_differences"], differences):
        if entry["point_difference"] != math.fsum(values) / float(n):
            _fail("result.uncertainty.point_differences", f"{entry['pair_id']} is not the full-cohort mean of the saved losses")


def _relate_diagnostics(
    request: UncertaintyRequest,
    diagnostics: Mapping[str, Any],
    raw_input: bytes,
    result: Mapping[str, Any],
) -> None:
    """Relates engine counters to the saved cohort and to the bytes and runtime they describe."""
    if diagnostics["input_identity"] != _raw_identity(raw_input):
        _fail("uncertainty-diagnostics.input_identity", "does not match actual uncertainty-input.json bytes/hash")
    runtime = diagnostics["runtime_identity"]
    private_runtime = result["runtime_identities"]
    for key in ("python_implementation", "python_version"):
        if runtime[key] != private_runtime[key]:
            _fail(f"uncertainty-diagnostics.runtime_identity.{key}", f"Diagnostics {key} != result runtime_identities")

    n = len(request.requested_keys)
    available_count = 0
    for view, length in zip(result["uncertainty"]["block_lengths"], diagnostics["lengths"]):
        if view["block_length"] != length["block_length"] or view["seed"] != length["seed"]:
            _fail("uncertainty-diagnostics.lengths", f"length {view['block_length']} identity mismatch")
        if view["status"] == UNCERTAINTY_STATUS_AVAILABLE:
            available_count += 1
            if length["replicates_completed"] != BOOTSTRAP_REPLICATES or length["sampled_positions"] != BOOTSTRAP_REPLICATES * n:
                _fail("uncertainty-diagnostics.lengths", f"available length {view['block_length']} counters contradict n={n}")
        elif length["replicates_completed"] != 0:
            _fail("uncertainty-diagnostics.lengths", f"unavailable length {view['block_length']} must have 0 replicates")

    required = BOOTSTRAP_REPLICATES * n * available_count
    if diagnostics["resource"]["required_positions"] != required:
        _fail("uncertainty-diagnostics.resource", f"required_positions must be {required}")


def _relate_config(config: Any, raw_config: bytes, diagnostics: Mapping[str, Any], result: Mapping[str, Any]) -> None:
    """Binds the saved configuration's cap, protocol, runtime and expected source identities."""
    if result["config_identity"] != _raw_identity(raw_config):
        _fail("result.config_identity", "does not match actual config.json bytes/hash")
    if type(config) is not dict:
        _fail("config", "expected object")
    for key in ("uncertainty", "runtime", "source_modules"):
        if type(config.get(key)) is not dict:
            _fail(f"config.{key}", "expected object")

    if config["uncertainty"].get("protocol_id") != UNCERTAINTY_PROTOCOL_ID:
        _fail("config.uncertainty.protocol_id", "does not name the uncertainty protocol")
    cap = config["uncertainty"].get("max_resample_positions")
    if type(cap) is not int or cap != diagnostics["resource"]["max_resample_positions"]:
        _fail("config.uncertainty.max_resample_positions", "does not match the diagnostics resource cap")

    private_runtime = result["runtime_identities"]
    for key in ("python_implementation", "python_version"):
        if config["runtime"].get(key) != private_runtime[key]:
            _fail(f"config.runtime.{key}", "does not match result runtime_identities")

    expected_sources = config["source_modules"]
    if set(expected_sources.keys()) != set(REQUIRED_SOURCE_MODULES):
        _fail("config.source_modules", "is not the required closed set")
    for rel_path, measured in result["source_identities"].items():
        validate_file_identity(expected_sources[rel_path], f"config.source_modules[{rel_path}]")
        expected = expected_sources[rel_path]
        if expected["raw_byte_count"] != measured["raw_byte_count"] or expected["sha256"].upper() != measured["sha256"].upper():
            _fail(f"result.source_identities[{rel_path}]", "does not match the saved configuration")


def _relate_historical_config(config: Mapping[str, Any], raw_admission: bytes, result: Mapping[str, Any], admission: Mapping[str, Any]) -> None:
    """
    Binds the saved historical configuration to the admission and result it produced.

    The runner already validated these bytes with the closed loader before science; this
    repeats only the joins a completed run must keep: closed mode, cutoffs, the exact A
    binding, the calendar and every ordered original file. acquisition_time is not compared
    because the result keeps the parsed datetime's ISO form, not the configured text.
    """
    expected_mode = {
        "schema_version": SCHEMA_VERSION_CONFIG_V3,
        "data_kind": DATA_KIND_HISTORICAL,
        "development_status": DEVELOPMENT_STATUS_HISTORICAL,
        "date_selection_rule": DATE_SELECTION_RULE_HISTORICAL,
    }
    for key, value in expected_mode.items():
        if config.get(key) != value:
            _fail(f"config.{key}", f"must be {value!r} for a historical run, got {config.get(key)!r}")
    for key in ("development_start", "test_start"):
        if config.get(key) != result[key]:
            _fail(f"config.{key}", "does not match result.json and admission.json")

    binding = config.get("admission")
    if type(binding) is not dict or binding.get("raw_byte_count") != len(raw_admission) or str(binding.get("sha256", "")).upper() != _raw_identity(raw_admission)["sha256"]:
        _fail("config.admission", "does not bind the actual admission.json bytes/hash")

    inputs = config.get("inputs")
    if type(inputs) is not dict:
        _fail("config.inputs", "expected object")
    identities = result["input_identities"]
    calendar = inputs.get("calendar")
    if type(calendar) is not dict or calendar.get("raw_byte_count") != identities["calendar"]["raw_byte_count"] or str(calendar.get("sha256", "")).upper() != identities["calendar"]["sha256"].upper():
        _fail("config.inputs.calendar", "does not match result.json calendar identity")

    for role in ("nifty", "vix"):
        c_role = inputs.get(role)
        r_role = identities[role]
        a_role = admission["inputs"][role]
        if type(c_role) is not dict or type(c_role.get("files")) is not list:
            _fail(f"config.inputs.{role}", "expected object with a files list")
        if c_role.get("units") != r_role["units"] or c_role.get("source_kind") != r_role["source_kind"]:
            _fail(f"config.inputs.{role}", "units or source_kind does not match result.json")
        c_files, r_files, a_files = c_role["files"], r_role["files"], a_role["files"]
        if not len(c_files) == len(r_files) == len(a_files):
            _fail(f"config.inputs.{role}.files", "file count differs across config.json, result.json and admission.json")
        for idx, (c_file, r_file, a_file) in enumerate(zip(c_files, r_files, a_files)):
            c_label = f"config.inputs.{role}.files[{idx}]"
            if type(c_file) is not dict:
                _fail(c_label, "expected object")
            for key in ("path", "raw_byte_count", "source_url", "requested_interval", "source_use_note"):
                if c_file.get(key) != r_file[key]:
                    _fail(c_label, f"{key} does not match result.json")
            if str(c_file.get("sha256", "")).upper() != r_file["sha256"].upper():
                _fail(c_label, "sha256 does not match result.json")
            a_label = f"admission.inputs.{role}.files[{idx}]"
            for key in ("raw_byte_count", "record_count", "observed_first_date", "observed_last_date"):
                if a_file[key] != r_file[key]:
                    _fail(a_label, f"{key} does not match result.json")
            if a_file["sha256"].upper() != r_file["sha256"].upper():
                _fail(a_label, "sha256 does not match result.json")
        if (
            a_role["record_count"] != sum(item["record_count"] for item in a_files)
            or a_role["observed_first_date"] != min(item["observed_first_date"] for item in a_files)
            or a_role["observed_last_date"] != max(item["observed_last_date"] for item in a_files)
        ):
            _fail(f"admission.inputs.{role}", "series totals or date bounds do not follow from its files")


def _relate_approval_coverage(approval: Mapping[str, Any], config: Mapping[str, Any]) -> None:
    """H must reference every configured original file exactly once, as the runner required."""
    expected = {(role, index) for role in ("nifty", "vix") for index in range(len(config["inputs"][role]["files"]))}
    seen = [(ref["role"], ref["file_index"]) for entry in approval["source_use_evidence"] for ref in entry["input_refs"]]
    if len(seen) != len(set(seen)) or set(seen) != expected:
        _fail(
            "historical-admission.source_use_evidence",
            f"input_refs must cover every configured file exactly once; missing={sorted(expected - set(seen))}, "
            f"unexpected={sorted(set(seen) - expected)}, repeated={len(seen) - len(set(seen))}",
        )


def _relate_run_bindings(config: Mapping[str, Any], result: Mapping[str, Any]) -> None:
    """
    Relates the saved tool, model and dependency declarations to the runtime, model, build,
    replay and comparator identities the result recorded, and checks the fixed model pin.
    These are derivable archive facts only: no archived runtime is imported or queried, so
    agreement cannot show which executable or interpreter actually ran.
    """
    tool_names = {"node_executable", "python_executable", "replay_script", "candidate_build_manifest", "models"}
    tools = _require_mapping(config.get("tools"), tool_names, "config.tools")
    for name in sorted(tool_names):
        entry = _require_mapping(tools[name], {"path", "raw_byte_count", "sha256"}, f"config.tools.{name}")
        _require_str(entry["path"], f"config.tools.{name}.path")
        _require_int(entry["raw_byte_count"], f"config.tools.{name}.raw_byte_count")
        _require_sha(entry["sha256"], f"config.tools.{name}.sha256")
    # The loader accepts either hex case for a validated digest, so the pin compares as it does
    if tools["models"]["sha256"].upper() != EXPECTED_MODELS_SHA256:
        _fail("config.tools.models.sha256", "is not the pinned model hash")

    runtime = result["runtime_identities"]
    model = result["model_identity"]
    build = result["build_identity"]
    replay = result["replay_identity"]
    for name, measured, label in (
        ("node_executable", runtime["node_executable"], "result.runtime_identities.node_executable"),
        ("python_executable", runtime["python_executable"], "result.runtime_identities.python_executable"),
        ("models", model, "result.model_identity"),
        ("candidate_build_manifest", build, "result.build_identity"),
        ("replay_script", replay["script"], "result.replay_identity.script"),
    ):
        declared = tools[name]
        if declared["raw_byte_count"] != measured["raw_byte_count"] or declared["sha256"].upper() != measured["sha256"].upper():
            _fail(f"config.tools.{name}", f"does not match {label}")
    if model["sha256"].upper() != EXPECTED_MODELS_SHA256 or replay["model_sha256"].upper() != EXPECTED_MODELS_SHA256:
        _fail("result.model_identity.sha256", "the result and its replay identity must name the pinned model hash")
    if replay["build_manifest_sha256"].upper() != build["sha256"].upper() or replay["calculation_id"] != build["calculation_id"]:
        _fail("result.replay_identity", "build manifest hash or calculation_id differs from result.build_identity")
    if build["mode"] != EXPECTED_BUILD_MODE:
        _fail("result.build_identity.mode", f"must be {EXPECTED_BUILD_MODE!r}, the only build the replay accepts")
    # The run measures the canonical replay.cjs twice: as a source module and as the replay script
    script_source = result["source_identities"]["research/prediction_eval/replay.cjs"]
    if (
        script_source["raw_byte_count"] != replay["script"]["raw_byte_count"]
        or script_source["sha256"].upper() != replay["script"]["sha256"].upper()
    ):
        _fail("result.replay_identity.script", "differs from the replay.cjs source identity")

    declared_versions = _require_mapping(
        config["runtime"].get("dependency_versions"), set(REQUIRED_DEPENDENCIES), "config.runtime.dependency_versions"
    )
    for name in REQUIRED_DEPENDENCIES:
        _require_str(declared_versions[name], f"config.runtime.dependency_versions.{name}")
    if runtime["dependency_versions"] != declared_versions:
        _fail("result.runtime_identities.dependency_versions", "does not match the saved configuration")
    seen: Set[str] = set()
    for idx, (name, version) in enumerate(result["comparator_metadata"]["logistic"]["dependency_versions"]):
        if name in seen or declared_versions.get(name) != version:
            _fail(f"result.comparator_metadata.logistic.dependency_versions[{idx}]", "does not match the saved configuration")
        seen.add(name)
    if seen != set(LOGISTIC_DEPENDENCY_NAMES):
        _fail(
            "result.comparator_metadata.logistic.dependency_versions",
            f"must name exactly {list(LOGISTIC_DEPENDENCY_NAMES)}, got {sorted(seen)}",
        )


def _relate_fitting_blocks(result: Mapping[str, Any]) -> None:
    """
    Relates every listed fitting row to its block cutoff with the planner's own rule: past the
    warmup, and a label that matures strictly before the cutoff. The development pool and every
    recorded development target must stay inside the test refit pool, and both methods must list
    the one canonical pool. The archive keeps no independent readiness record, so this cannot
    show a listed pool is complete.
    """
    pools: Dict[str, List[int]] = {}
    for name in ("development", "test"):
        part = result["partitions"][name]
        for method in ("frequency", "logistic"):
            block = part[f"{method}_block"]
            label = f"result.partitions.{name}.{method}_block.fitting_indices"
            for pos, index in enumerate(block["fitting_indices"]):
                if index < WARMUP_ORIGIN_INDEX:
                    _fail(f"{label}[{pos}]", f"index {index} is inside the warmup")
                if index + HORIZON_SESSIONS >= block["cutoff_index"]:
                    _fail(f"{label}[{pos}]", f"index {index} does not mature strictly before cutoff {block['cutoff_index']}")
        if part["frequency_block"]["fitting_indices"] != part["logistic_block"]["fitting_indices"]:
            _fail(f"result.partitions.{name}", "frequency and logistic blocks list different fitting pools")
        pools[name] = part["frequency_block"]["fitting_indices"]
    omitted = sorted(set(pools["development"]) - set(pools["test"]))
    if omitted:
        _fail("result.partitions.test", f"refit pool omits development fitting rows {omitted[:5]}")
    # A recorded DEV target is eligible and matures strictly before T, so the planner refits on it
    test_cutoff = result["partitions"]["test"]["cutoff_index"]
    targets = result["partitions"]["development"]["requested_indices"]
    late = [index for index in targets if index + HORIZON_SESSIONS >= test_cutoff]
    if late:
        _fail("result.partitions.development", f"targets {late[:5]} do not mature strictly before test cutoff {test_cutoff}")
    missing = sorted(set(targets) - set(pools["test"]))
    if missing:
        _fail("result.partitions.test", f"refit pool omits recorded development targets {missing[:5]}")


def _relate_replay_evidence(raw: Mapping[str, bytes], result: Mapping[str, Any], config: Mapping[str, Any]) -> None:
    """
    Binds the saved replay streams to the identities the result captured and to the receipt of
    one successful first attempt, whose saved invocation must be the one the saved configuration
    describes. Receipt paths are recorded labels, compared only with other saved labels: they are
    not proof of archived content, and an archive moved elsewhere still verifies. Matching bytes
    are consistency evidence: they do not authenticate the child process or give race-free custody.
    """
    streams = {
        "request": _raw_identity(raw["replay-request.json"]),
        "response": _raw_identity(raw["replay-response.json"]),
        "stderr": _raw_identity(raw["replay-stderr.log"]),
    }
    replay = result["replay_identity"]
    for key in ("request", "response"):
        if replay[key]["raw_byte_count"] != streams[key]["raw_byte_count"] or replay[key]["sha256"].upper() != streams[key]["sha256"]:
            _fail(f"result.replay_identity.{key}", f"does not match actual replay-{key}.json bytes/hash")

    receipt = _require_mapping(parse_strict_json_bytes(raw["replay-invocation.json"]), REPLAY_RECEIPT_KEYS, "replay-invocation")
    for key, expected in (
        ("attempt", 1),
        ("shell", False),
        ("launch_state", "started"),
        ("capture_state", "complete"),
        ("timed_out", False),
        ("immediate_child_exit", 0),
    ):
        if type(receipt[key]) is not type(expected) or receipt[key] != expected:
            _fail(f"replay-invocation.{key}", f"must be {expected!r} for the successful first attempt, got {receipt[key]!r}")
    for key in ("launch_error", "capture_error"):
        if receipt[key] is not None:
            _fail(f"replay-invocation.{key}", "a successful attempt has no error")
    for key in ("exe", "cwd", "start_utc", "end_utc"):
        _require_str(receipt[key], f"replay-invocation.{key}")
    for idx, item in enumerate(_require_list(receipt["argv"], "replay-invocation.argv")):
        _require_str(item, f"replay-invocation.argv[{idx}]")
    timeout = _require_int(receipt["timeout_seconds"], "replay-invocation.timeout_seconds", 1)
    _require_number(receipt["duration_seconds"], "replay-invocation.duration_seconds")
    environment = receipt["declared_environment"]
    if type(environment) is not dict or any(type(value) is not str for value in environment.values()):
        _fail("replay-invocation.declared_environment", "expected an object of strings")

    for key, stream, name in (
        ("request", "request", "replay-request.json"),
        ("stdout", "response", "replay-response.json"),
        ("stderr", "stderr", "replay-stderr.log"),
    ):
        entry = _require_mapping(receipt[key], {"path", "bytes", "sha256"}, f"replay-invocation.{key}")
        _require_str(entry["path"], f"replay-invocation.{key}.path")
        _require_int(entry["bytes"], f"replay-invocation.{key}.bytes")
        _require_sha(entry["sha256"], f"replay-invocation.{key}.sha256")
        if entry["bytes"] != streams[stream]["raw_byte_count"] or entry["sha256"].upper() != streams[stream]["sha256"]:
            _fail(f"replay-invocation.{key}", f"does not match actual {name} bytes/hash")

    # The adapter launches [node, replay.cjs, request] from the configured labels, in the
    # configured workspace, under the configured timeout, which the runner caps at 60 seconds
    tools = config["tools"]
    argv = receipt["argv"]
    expected_argv = [receipt["exe"], tools["replay_script"]["path"], receipt["request"]["path"]]
    if argv != expected_argv:
        _fail("replay-invocation.argv", "must be the recorded executable, configured replay script and recorded request")
    if receipt["exe"] != tools["node_executable"]["path"]:
        _fail("replay-invocation.exe", "does not match config.tools.node_executable.path")
    if receipt["cwd"] != _require_str(config.get("workspace_root"), "config.workspace_root"):
        _fail("replay-invocation.cwd", "does not match config.workspace_root")
    if timeout > MAX_REPLAY_TIMEOUT_SECONDS:
        _fail("replay-invocation.timeout_seconds", f"{timeout} exceeds the {MAX_REPLAY_TIMEOUT_SECONDS}-second replay bound")
    if timeout != _require_int(config.get("timeout_seconds"), "config.timeout_seconds", 1):
        _fail("replay-invocation.timeout_seconds", "does not match config.timeout_seconds")


def _relate_predictions(raw_predictions: bytes, result: Mapping[str, Any]) -> None:
    """predictions.json must be the canonical bytes of the per-origin projection of result.json."""
    parse_strict_json_bytes(raw_predictions)
    expected = {name: result["partitions"][name]["per_origin_records"] for name in ("development", "test")}
    # Canonical bytes keep types exact: == would equate 1 with 1.0 and True with 1
    if raw_predictions != serialize_strict_json(expected):
        _fail("predictions.json", "differs from the per-origin projection of result.json")


def _relate_written_artifacts(raw: Mapping[str, bytes]) -> None:
    request = parse_uncertainty_input(raw["uncertainty-input.json"])

    diagnostics = parse_strict_json_bytes(raw["uncertainty-diagnostics.json"])
    validate_uncertainty_diagnostics_document(diagnostics)
    result = parse_strict_json_bytes(raw["result.json"])
    validate_result_document(result)
    summary = parse_strict_json_bytes(raw["panel-summary.json"])
    validate_summary_document(summary)
    admission = parse_strict_json_bytes(raw["admission.json"])
    validate_admission_document(admission, "admission")
    config = parse_strict_json_bytes(raw["config.json"])

    if result["admission_identity"] != _raw_identity(raw["admission.json"]):
        _fail("result.admission_identity", "does not match actual admission.json bytes/hash")

    # Each validator ties its schema version to data_kind, so one kind means one closed mode
    kinds = {"result": result["data_kind"], "panel-summary": summary["data_kind"], "admission": admission["data_kind"]}
    if len(set(kinds.values())) != 1:
        _fail("artifact mode", f"data_kind disagrees across artifacts: {kinds}")
    is_historical = result["data_kind"] == DATA_KIND_HISTORICAL
    if ("historical-admission.json" in raw) != is_historical:
        _fail("historical-admission.json", "must exist exactly for a historical run")
    approval: Optional[Dict[str, Any]] = None
    if is_historical:
        raw_h = raw["historical-admission.json"]
        approval = parse_strict_json_bytes(raw_h)
        validate_approval_document(approval, "historical-admission")
        h_identity = _raw_identity(raw_h)
        if result.get("approval_identity") != h_identity:
            _fail("result.approval_identity", "does not match actual historical-admission.json bytes/hash")
        # H -> C and H -> A joins; the runner accepts either SHA-256 case, so compare as it does
        for key, name in (("config_identity", "config.json"), ("admission_identity", "admission.json")):
            actual = _raw_identity(raw[name])
            named = approval[key]
            if named["raw_byte_count"] != actual["raw_byte_count"] or named["sha256"].upper() != actual["sha256"]:
                _fail(f"historical-admission.{key}", f"does not match actual {name} bytes/hash")

    _relate_axis(request, admission, result)
    _relate_input_rows(request, result["partitions"]["test"])
    _relate_statistics(request, result["uncertainty"], summary["uncertainty"])
    _relate_diagnostics(request, diagnostics, raw["uncertainty-input.json"], result)
    _relate_config(config, raw["config.json"], diagnostics, result)
    if approval is not None:
        _relate_historical_config(config, raw["admission.json"], result, admission)
        _relate_approval_coverage(approval, config)
    _relate_run_bindings(config, result)
    _relate_fitting_blocks(result)
    _relate_replay_evidence(raw, result, config)
    _relate_predictions(raw["predictions.json"], result)

    # Last, so the narrower relations above keep naming their own cause
    expected_summary = project_panel_summary(result)
    if summary != expected_summary:
        differing = sorted(key for key in expected_summary if summary.get(key) != expected_summary[key])
        _fail("panel-summary.json", f"differs from its projection of result.json in {differing}")


def verify_study_artifacts_semantic_relations(run_dir: Union[str, Path]) -> Tuple[bool, str]:
    """
    Checks semantic relations among written run artifacts, before and after the manifest exists:
      1. input axis/keys/availability/loss triples/gaps match canonical TEST private
         per-origin result and admission, not development or rounded means.
      2. summary.uncertainty equals the explicit portable projection of result.uncertainty, and
         that block's counts, states and points follow from the saved cohort.
      3. diagnostics input identity equals actual input bytes/hash, and runtime equals
         caller-verified private result runtime.
      4. length/seed/replicate/count relationships agree with result statistical states, the
         required-operation count and the saved configuration's cap, runtime and sources.
      5. result, summary and admission share one closed mode; a historical run also binds
         config.json mode, cutoffs, A identity and every ordered original file to result and
         admission, and H's input_refs to every configured file exactly once.
      6. config.json tool byte/hash fields, the pinned model hash (either hex case) and the
         required dependency versions agree with the result's runtime, model, build, replay and
         comparator fields; the build is the candidate build, both replay.cjs identities agree,
         and the logistic metadata names exactly numpy, scikit-learn and scipy.
      7. each method block keeps its partition cutoff, both cutoff dates sit on the axis, blocks
         list only warmed-up rows maturing strictly before their cutoff, the development pool
         and every recorded development target stay inside the refit pool, and both methods
         list one pool.
      8. the saved replay request and response match the result's captured identities, and
         request, stdout and stderr match a typed successful first-attempt receipt whose argv,
         executable, cwd and timeout are the saved configuration's labels and bounded value.
      9. predictions.json is the canonical per-origin projection of result.json, and
         panel-summary.json equals its deterministic projection of result.json.

    Malformed or inconsistent artifacts return False. Stream fingerprints and restart counts
    stay opaque here: proving them would need the RNG rerun this check must not perform.
    Consistent bytes do not authenticate the archive, its producer or the process that ran.
    """
    root = Path(run_dir)
    raw: Dict[str, bytes] = {}
    try:
        has_h = (root / "historical-admission.json").exists()
        required_names = SEMANTIC_RELATION_ARTIFACTS_V3 if has_h else SEMANTIC_RELATION_ARTIFACTS_V2
        for name in required_names:
            path = root / name
            if not path.exists():
                return False, f"Required artifact '{name}' missing for semantic verification"
            raw[name] = path.read_bytes()
        _relate_written_artifacts(raw)
    except (OSError, ValueError) as exc:
        return False, f"Semantic relation verification failed: {exc}"
    return True, "Artifact semantic relations verified"


def _ui_state(state: str, reason: str, summary_doc: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "display_state": state,
        "can_display_metrics": state == UI_STATE_DISPLAYABLE,
        "reason": reason,
        "summary_data": summary_doc if state == UI_STATE_DISPLAYABLE else None,
    }


def evaluate_ui_display_state(
    raw_summary_bytes: Optional[bytes],
    descriptor: Optional[ReleaseDescriptor],
    digest_fn: Optional[Callable[[bytes], str]] = None,
) -> Dict[str, Any]:
    """
    Evaluates UI presentation state in fixed precedence order, on the exact fetched bytes.

    Precedence:
      1. missing descriptor / artifact => 'unavailable'
      2. unparseable bytes or non-object root => 'error'
      3. schema/protocol outside the independently supported sets => 'unsupported_version'
      4. closed schema violation => 'error'
      5. run_id, study_id, summary schema or coverage_end_date different from descriptor => 'stale'
      6. digest failure / byte-count / SHA mismatch => 'error'
      7. exact supported identity / hash binding => 'displayable'

    Support comes from this module's constants, so a matching v99 summary and descriptor
    stay unsupported. Two supported but different schemas are a stale selection, as in
    verify_promotion_binding. No state other than 'displayable' exposes summary data.
    """
    if raw_summary_bytes is None or descriptor is None:
        return _ui_state(UI_STATE_UNAVAILABLE, "Missing release descriptor or summary artifact")

    try:
        summary_doc = parse_strict_json_bytes(raw_summary_bytes)
    except ValueError as exc:
        return _ui_state(UI_STATE_ERROR, f"Malformed summary JSON: {exc}")

    if not isinstance(summary_doc, dict):
        return _ui_state(UI_STATE_ERROR, "Summary root is not a JSON object")

    # Version support is decided before the closed schema, whose shape only a supported
    # version may be assumed to follow.
    schema_version = summary_doc.get("schema_version")
    protocol_id = summary_doc.get("protocol_id")
    if type(schema_version) is not str or type(protocol_id) is not str:
        return _ui_state(UI_STATE_ERROR, "Summary schema_version and protocol_id must be strings")
    if schema_version not in SUPPORTED_SUMMARY_SCHEMA_VERSIONS:
        return _ui_state(UI_STATE_UNSUPPORTED_VERSION, f"Unsupported summary schema: {schema_version}")
    if protocol_id not in SUPPORTED_PROTOCOL_IDS:
        return _ui_state(UI_STATE_UNSUPPORTED_VERSION, f"Unsupported protocol: {protocol_id}")
    if descriptor.summary_schema_version not in SUPPORTED_SUMMARY_SCHEMA_VERSIONS:
        return _ui_state(UI_STATE_UNSUPPORTED_VERSION, f"Unsupported descriptor schema: {descriptor.summary_schema_version}")
    if descriptor.protocol_id not in SUPPORTED_PROTOCOL_IDS:
        return _ui_state(UI_STATE_UNSUPPORTED_VERSION, f"Unsupported descriptor protocol: {descriptor.protocol_id}")

    try:
        validate_summary_document(summary_doc)
    except ValueError as exc:
        return _ui_state(UI_STATE_ERROR, f"Malformed summary: {exc}")

    parsed_cov_end = summary_doc["dataset_attribution"]["coverage_end_date"]
    if (
        summary_doc["run_id"] != descriptor.run_id
        or summary_doc["study_id"] != descriptor.study_id
        or schema_version != descriptor.summary_schema_version
        or parsed_cov_end != descriptor.coverage_end_date
    ):
        return _ui_state(
            UI_STATE_STALE,
            f"Summary identity ({summary_doc['run_id']}, {summary_doc['study_id']}, {schema_version}, {parsed_cov_end}) "
            f"differs from selected descriptor ({descriptor.run_id}, {descriptor.study_id}, "
            f"{descriptor.summary_schema_version}, {descriptor.coverage_end_date})",
        )

    if len(raw_summary_bytes) != descriptor.summary_bytes:
        return _ui_state(UI_STATE_ERROR, f"Byte count mismatch: expected {descriptor.summary_bytes}, got {len(raw_summary_bytes)}")

    try:
        if digest_fn is not None:
            computed_sha = digest_fn(raw_summary_bytes)
        else:
            computed_sha = hashlib.sha256(raw_summary_bytes).hexdigest().upper()
    except Exception as exc:
        return _ui_state(UI_STATE_ERROR, f"Digest computation failed: {exc}")

    if not isinstance(computed_sha, str) or computed_sha.upper() != descriptor.summary_sha256.upper():
        return _ui_state(UI_STATE_ERROR, f"SHA-256 digest mismatch: expected {descriptor.summary_sha256}, got {computed_sha}")

    return _ui_state(UI_STATE_DISPLAYABLE, "Exact supported identity and cryptographic binding verified", summary_doc)
