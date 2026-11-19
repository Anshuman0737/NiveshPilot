"""
Prediction Evaluation Study Runner, Replay Adapter, and Orchestration Foundation.

Provides deterministic, inspectable, offline Nifty 50 prediction evaluation study
execution, strict configuration, input-only admission gap inventory, chronological
replay transport adapter, and multi-model comparison orchestration.

Architectural ownership:
    inputs.py owns raw CSV loading, validation, provenance, and alignment.
    outcomes.py owns 20-session horizon classification (+/-0.5% band).
    features.py owns origin-time causal indicator construction.
    splits.py owns chronological split planning, strict-before purging, and refit tracking.
    frequency.py owns the fixed Laplace-1 empirical class frequency comparator.
    logistic.py owns the fixed logistic comparator (lazy import on scientific path).
    replay_export.py owns typed wire serialization for Node replay.
    metrics.py owns three-class probability scoring and independent evaluation metrics.
    study_results.py owns result DTOs, strict JSON/Markdown serialization, and completion binding.
    study.py owns strict configuration, input-only admission inventory, Node replay adapter,
    serial fit warning/thread ownership, and study lifecycle orchestration.

Boundary:
    Pure paths (configuration, admission inventory, replay adapter, CLI argument parser)
    are importable and verifiable under standard library Python (-E -B -S).
    Scientific comparator execution imports logistic and threadpoolctl lazily within
    a caller-owned, restored single-thread threadpool context.

Admission ordering (no hash cycle):
    prepare_input_admission freezes an input-only record from the admitted inputs and
    calendar. The configuration then binds that record's exact bytes with every other
    expected identity, so the record never names the configuration. A run verifies those
    identities and the frozen record before outcomes or features exist, and compares the
    frozen gap list with the canonical planner before any comparator or replay call.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, replace
import datetime
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import sys
import time
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Set, Tuple, Union
import warnings

from research.prediction_eval.inputs import (
    align_pair,
    FileInputSpec,
    InputValidationError,
    InputWarning,
    load_series,
    AlignedPair,
    LoadedSeries,
)
from research.prediction_eval.outcomes import (
    compute_twenty_session_outcomes,
    HORIZON_SESSIONS,
    OutcomeSeries,
    OUTCOME_CLASS_BEAR,
    OUTCOME_CLASS_BULL,
    OUTCOME_CLASS_NEUTRAL,
    TwentySessionOutcome,
    VALID_OUTCOME_CLASSES,
)
from research.prediction_eval.features import (
    compute_nifty_features,
    FeatureSeries,
    NiftyFeatureRecord,
    PredictorPayload,
    PROTOCOL_ID as FEATURES_PROTOCOL_ID,
    VALID_REGIMES,
    WARMUP_ORIGIN_INDEX,
)
from research.prediction_eval.splits import (
    build_split_plan,
    OriginSplitDecision,
    PARTITION_DEVELOPMENT,
    PARTITION_TEST,
    PARTITION_TRAIN,
    SplitPlan,
)
from research.prediction_eval.frequency import (
    build_frequency_predictions,
    FrequencyBlock,
    FrequencyPrediction,
    FrequencyResult,
    METHOD_ID as FREQUENCY_METHOD_ID,
)
from research.prediction_eval.replay_export import (
    SCHEMA_VERSION as REPLAY_INPUT_SCHEMA_VERSION,
    serialize_replay_input,
)
from research.prediction_eval.metrics import (
    _validate_method_predictions,
    ComparisonMetrics,
    EvaluationOrigin,
    ModelMetrics,
    PredictionLike,
    PROTOCOL_ID as METRICS_PROTOCOL_ID,
    RowScore,
    score_comparison,
    STATUS_EMPTY as METRICS_STATUS_EMPTY,
    STATUS_SCORED as METRICS_STATUS_SCORED,
)
from research.prediction_eval.study_results import (
    ADMISSION_POLICY,
    build_panel_summary,
    build_predictions_document,
    build_release_descriptor,
    build_result_document,
    build_run_manifest,
    DATA_KIND_HISTORICAL,
    DATA_KIND_SYNTHETIC,
    DATE_SELECTION_RULE,
    DATE_SELECTION_RULE_HISTORICAL,
    DEVELOPMENT_STATUS_HISTORICAL,
    DEVELOPMENT_STATUS_SYNTHETIC,
    EXPECTED_BUILD_MODE,
    EXPECTED_DIRECTIONS,
    EXPECTED_MODELS_SHA256,
    FAILURE_RECORD_NAME,
    FORECAST_STATE_AVAILABLE,
    FORECAST_STATE_UNAVAILABLE,
    HISTORICAL_LIMITATIONS,
    HISTORICAL_MIN_SESSIONS,
    historical_split_indices,
    is_valid_identifier,
    MAX_REPLAY_TIMEOUT_SECONDS,
    MethodOriginRecord,
    ORDERED_CLASSES,
    parse_strict_json,
    parse_strict_json_bytes,
    PartitionCounts,
    PartitionResult,
    PerOriginRecord,
    ReleaseDescriptor,
    render_report_markdown,
    REQUIRED_DEPENDENCIES,
    REQUIRED_SOURCE_MODULES,
    SCHEMA_VERSION_ADMISSION,
    SCHEMA_VERSION_ADMISSION_V1,
    SCHEMA_VERSION_ADMISSION_V2,
    SCHEMA_VERSION_APPROVAL_V1,
    SCHEMA_VERSION_CONFIG_V2,
    SCHEMA_VERSION_CONFIG_V3,
    SCHEMA_VERSION_FAILURE,
    SCHEMA_VERSION_RELEASE_DESCRIPTOR,
    SCHEMA_VERSION_RESULT_V2,
    SCHEMA_VERSION_RESULT_V3,
    SCHEMA_VERSION_RUN_MANIFEST_V2,
    SCHEMA_VERSION_RUN_MANIFEST_V3,
    SCHEMA_VERSION_SUMMARY_V2,
    SCHEMA_VERSION_SUMMARY_V3,
    SCORE_STATE_SCORED,
    SCORE_STATE_UNSCORED,
    serialize_strict_json,
    SOURCE_KIND_HISTORICAL,
    SOURCE_KIND_SYNTHETIC,
    STATUS_COMPARISON_UNAVAILABLE,
    STATUS_EMPTY,
    STATUS_SCORED,
    StudyResult,
    STUDY_PROTOCOL_ID,
    SYNTHETIC_LIMITATIONS,
    UncertaintyBlock,
    validate_admission_document,
    validate_approval_document,
    verify_promotion_binding,
    verify_study_artifacts_semantic_relations,
)
from research.prediction_eval.uncertainty import (
    BrierRow,
    compute_uncertainty,
    MAX_RESAMPLE_POSITIONS,
    RequestedKey,
    serialize_uncertainty_input,
    build_uncertainty_diagnostics_document,
    UNCERTAINTY_PROTOCOL_ID,
    UncertaintyRequest,
)

STUDY_SCHEMA_VERSION_V2: str = SCHEMA_VERSION_CONFIG_V2
STUDY_SCHEMA_VERSION_V3: str = SCHEMA_VERSION_CONFIG_V3

# One gap-free historical study needs B10000 x n800 x 3 views; the engine hard cap stays 30M
HISTORICAL_MAX_RESAMPLE_POSITIONS: int = 24000000

SUPPORTED_CONFIG_MODES: Dict[str, Dict[str, str]] = {
    STUDY_SCHEMA_VERSION_V2: {
        "data_kind": DATA_KIND_SYNTHETIC,
        "development_status": DEVELOPMENT_STATUS_SYNTHETIC,
        "date_selection_rule": DATE_SELECTION_RULE,
        "source_kind": SOURCE_KIND_SYNTHETIC,
    },
    STUDY_SCHEMA_VERSION_V3: {
        "data_kind": DATA_KIND_HISTORICAL,
        "development_status": DEVELOPMENT_STATUS_HISTORICAL,
        "date_selection_rule": DATE_SELECTION_RULE_HISTORICAL,
        "source_kind": SOURCE_KIND_HISTORICAL,
    },
}
SERIES_ID_NIFTY: str = "nifty50_price_index"
SERIES_ID_VIX: str = "india_vix"

REPLAY_CLAIM_LABEL: str = (
    "Retrospective replay of the frozen current heuristic; market data only; not historically issued forecasts"
)
EXPECTED_MODELS_PATH: str = "public/data/market_intelligence/models.json"
EXPECTED_20D_PLATT_PARAMS: Tuple[float, float] = (1.42, 0.02)
EXPECTED_BUILD_MANIFEST_PATH: str = "build/prediction-eval/candidate/build-manifest.json"
EXPECTED_REPLAY_SCRIPT_PATH: str = "research/prediction_eval/replay.cjs"
EXPECTED_BUILD_SCHEMA_VERSION: str = "nivesh-replay-build-v1"

# Bound on waiting for a killed child, so cleanup can never become its own hang.
CHILD_CLEANUP_WAIT_SECONDS: int = 5

EXPECTED_INPUT_UNITS: Dict[str, str] = {
    "nifty": "index_points",
    "vix": "volatility_index_points",
}

NUMERIC_PAYLOAD_FIELDS: Tuple[str, ...] = (
    "ret_5d",
    "rsi_14",
    "macd_hist",
    "vol_30d",
    "rel_strength_20d",
    "drawdown",
)

RESPONSE_ROOT_KEYS: Set[str] = {
    "schema_version",
    "claim_label",
    "computed_provenance",
    "declared_input",
    "forecasts",
}
FORECAST_ROW_KEYS: Set[str] = {"origin_index", "origin_date", "forecast"}
FORECAST_OBJECT_KEYS: Set[str] = {
    "horizon",
    "days",
    "probability_bullish",
    "probability_neutral",
    "probability_bearish",
    "expected_direction",
    "expected_return_pct",
    "confidence",
    "signal_quality",
    "model_disagreement",
    "top_bullish_drivers",
    "top_bearish_drivers",
}
FORECAST_COMPONENT_KEYS: Set[str] = {"technical", "fundamental", "event_news", "macro_regime", "cross_asset"}
CONFIDENCE_LEVELS: Tuple[str, ...] = ("LOW", "MEDIUM", "HIGH")
CONSENSUS_LEVELS: Tuple[str, ...] = ("High Consensus", "Moderate Agreement", "High Disagreement")

_SHA256_HEX_REGEX = re.compile(r"\A[0-9A-Fa-f]{64}\Z")
SAFE_INTEGER_MAX: int = 9007199254740991


def _config_error(field_name: str, message: str) -> InputValidationError:
    return InputValidationError(message, field=field_name, reason=message)


def _sha256_upper(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _norm_path(path: Union[str, Path]) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def _require_keys(value: Any, allowed: Set[str], field_name: str) -> Dict[str, Any]:
    """Requires a dictionary with exactly the declared keys, naming the first offender."""
    if type(value) is not dict:
        raise _config_error(field_name, f"Field '{field_name}' must be an object, got {type(value).__name__}")
    for key in value:
        if key not in allowed:
            raise _config_error(key, f"Unknown configuration key: '{key}'")
    for key in sorted(allowed):
        if key not in value:
            raise _config_error(key, f"Missing required configuration key: '{key}'")
    return value


def _require_string(value: Any, field_name: str) -> str:
    if type(value) is not str or not value:
        raise _config_error(field_name, f"Field '{field_name}' must be a non-empty string, got {value!r}")
    return value


def _require_absolute_path(value: Any, field_name: str) -> str:
    """Rejects relative and PATH-resolved names: no input may depend on the working directory."""
    text = _require_string(value, field_name)
    candidate = Path(text)
    if not candidate.is_absolute() or ".." in candidate.parts:
        raise _config_error(field_name, f"Field '{field_name}' must be an absolute normalized path, got {text!r}")
    return text


def _require_byte_count(value: Any, field_name: str) -> int:
    if type(value) is not int or value < 0 or value > SAFE_INTEGER_MAX:
        raise _config_error(field_name, f"Field '{field_name}' must be a non-negative integer, got {value!r}")
    return value


def _require_sha256(value: Any, field_name: str) -> str:
    if type(value) is not str or _SHA256_HEX_REGEX.match(value) is None:
        raise _config_error(field_name, f"Field '{field_name}' must be a 64-hex SHA-256, got {value!r}")
    return value.upper()


def _parse_date(val: Any, field_name: str) -> datetime.date:
    if type(val) is datetime.date:
        return val
    if not isinstance(val, str):
        raise InputValidationError(
            f"Field '{field_name}' must be an ISO date string, got {type(val).__name__}",
            field=field_name,
            reason="Invalid date type",
        )
    try:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", val):
            raise ValueError("expected YYYY-MM-DD")
        return datetime.date.fromisoformat(val)
    except Exception as exc:
        raise InputValidationError(
            f"Field '{field_name}' must be valid ISO YYYY-MM-DD: {exc}",
            field=field_name,
            reason=str(exc),
        ) from exc


def _validate_timeout(value: Any) -> int:
    """Rejects, never caps, an out-of-bounds replay timeout."""
    if type(value) is not int or value <= 0 or value > MAX_REPLAY_TIMEOUT_SECONDS:
        raise InputValidationError(
            f"timeout_seconds must be a positive integer <= {MAX_REPLAY_TIMEOUT_SECONDS}, got {value!r}",
            field="timeout_seconds",
            reason="Invalid timeout value",
        )
    return value


@dataclass(frozen=True)
class HeuristicPrediction:
    """Replay-adapted heuristic prediction record implementing PredictionLike."""

    origin_index: int
    origin_date: datetime.date
    probabilities: Tuple[float, float, float]
    expected_direction: str

    def __post_init__(self) -> None:
        if type(self.origin_index) is not int or self.origin_index < 0:
            raise ValueError(f"origin_index must be non-negative int, got {self.origin_index!r}")
        if type(self.origin_date) is not datetime.date:
            raise ValueError(f"origin_date must be datetime.date, got {type(self.origin_date).__name__}")
        if type(self.probabilities) is not tuple or len(self.probabilities) != 3:
            raise ValueError(f"probabilities must be a 3-tuple, got {self.probabilities!r}")
        if self.expected_direction not in EXPECTED_DIRECTIONS:
            raise ValueError(f"expected_direction must be one of {EXPECTED_DIRECTIONS}, got {self.expected_direction!r}")


@dataclass(frozen=True)
class BoundFile:
    """An absolute path with its expected exact byte count and SHA-256."""

    path: str
    raw_byte_count: int
    sha256: str


def derive_historical_split_cutoffs(
    sessions: Union[int, Sequence[Any]],
    expected_development_start: Optional[Any] = None,
    expected_test_start: Optional[Any] = None,
    rule: str = DATE_SELECTION_RULE_HISTORICAL,
) -> Any:
    """
    Derives split cutoffs for calendar_tail800_dev400_min2220_v1.
    If sessions is int N: returns (D, T, E, span) indices.
    If sessions is Sequence of dates: returns (D_date, T_date, E_date).
    Validates N >= 2220, D >= 1000, span == 800, strictly increasing dates,
    and matching caller assertions if provided.
    """
    if rule != DATE_SELECTION_RULE_HISTORICAL:
        raise InputValidationError(
            f"Unsupported historical date_selection_rule '{rule}'; expected '{DATE_SELECTION_RULE_HISTORICAL}'",
            field="date_selection_rule",
            reason=f"rule != {DATE_SELECTION_RULE_HISTORICAL}",
        )
    if isinstance(sessions, int):
        session_count = sessions
        axis_dates = None
    elif isinstance(sessions, Sequence):
        session_count = len(sessions)
        axis_dates = sessions
        for i in range(1, len(axis_dates)):
            if axis_dates[i] <= axis_dates[i - 1]:
                raise InputValidationError(
                    f"Dates must be strictly monotonically increasing, got {axis_dates[i-1]} and {axis_dates[i]}",
                    field="dates",
                    reason="Non-increasing dates",
                )
    else:
        raise InputValidationError("sessions must be integer count or sequence of dates", field="sessions")

    if session_count < HISTORICAL_MIN_SESSIONS:
        raise InputValidationError(
            f"Historical date selection requires at least {HISTORICAL_MIN_SESSIONS} trading sessions, got {session_count}",
            field="date_selection_rule",
            reason=f"session_count {session_count} < {HISTORICAL_MIN_SESSIONS}",
        )
    # The shared rule gives span 800 and D >= 1000 for every N that passed the minimum above
    d, t, e = historical_split_indices(session_count)
    span = e - t

    if axis_dates is not None:
        d_date = axis_dates[d]
        t_date = axis_dates[t]
        e_date = axis_dates[e]
        if expected_development_start is not None and expected_development_start != d_date:
            raise InputValidationError(
                f"development_start mismatch: derived {d_date}, got {expected_development_start}",
                field="development_start",
                reason="development_start mismatch",
            )
        if expected_test_start is not None and expected_test_start != t_date:
            raise InputValidationError(
                f"test_start mismatch: derived {t_date}, got {expected_test_start}",
                field="test_start",
                reason="test_start mismatch",
            )
        return d_date, t_date, e_date

    return d, t, e, span


@dataclass(frozen=True)
class FileBinding:
    bound: BoundFile
    source_url: Optional[str]
    requested_interval: Optional[Tuple[datetime.date, datetime.date]]
    acquisition_time: Optional[datetime.datetime]
    source_use_note: str

    def file_spec(self) -> FileInputSpec:
        return FileInputSpec(
            file_path=self.bound.path,
            source_url=self.source_url,
            requested_interval=self.requested_interval,
            acquisition_time=self.acquisition_time,
            source_use_note=self.source_use_note,
        )


@dataclass(frozen=True)
class InputBinding:
    """A bound series input with its declared FileInputSpec provenance and units."""

    units: str
    source_kind: str
    files: Tuple[FileBinding, ...]

    def file_specs(self) -> List[FileInputSpec]:
        return [f.file_spec() for f in self.files]


@dataclass(frozen=True)
class StudyConfiguration:
    """Validated strict configuration for an offline prediction study."""

    schema_version: str
    study_id: str
    protocol_id: str
    data_kind: str
    development_status: str
    development_start: datetime.date
    test_start: datetime.date
    date_selection_rule: str
    workspace_root: str
    allowed_output_parent: str
    timeout_seconds: int
    nifty_input: InputBinding
    vix_input: InputBinding
    calendar: BoundFile
    admission: BoundFile
    node_executable: BoundFile
    python_executable: BoundFile
    replay_script: BoundFile
    candidate_build_manifest: BoundFile
    models: BoundFile
    source_modules: Dict[str, Dict[str, Any]]
    python_version: str
    python_implementation: str
    dependency_versions: Dict[str, str]
    uncertainty: Dict[str, Any]
    config_path: Optional[str] = None
    config_bytes: Optional[bytes] = None

    def __post_init__(self) -> None:
        if self.schema_version not in SUPPORTED_CONFIG_MODES:
            raise InputValidationError(
                f"Unsupported configuration schema_version '{self.schema_version}'; expected one of {sorted(SUPPORTED_CONFIG_MODES.keys())}",
                field="schema_version",
                reason=f"Expected one of {sorted(SUPPORTED_CONFIG_MODES.keys())}",
            )
        mode = SUPPORTED_CONFIG_MODES[self.schema_version]
        if self.data_kind != mode["data_kind"]:
            raise InputValidationError(
                f"data_kind '{self.data_kind}' is not valid for schema '{self.schema_version}'; expected '{mode['data_kind']}'",
                field="data_kind",
                reason=f"Expected {mode['data_kind']} for {self.schema_version}",
            )
        if self.development_status != mode["development_status"]:
            raise _config_error(
                "development_status",
                f"Unsupported development_status '{self.development_status}'; expected '{mode['development_status']}'",
            )
        if self.protocol_id != STUDY_PROTOCOL_ID:
            raise _config_error("protocol_id", f"Unsupported protocol_id '{self.protocol_id}'; expected '{STUDY_PROTOCOL_ID}'")
        if not is_valid_identifier(self.study_id):
            raise _config_error("study_id", f"study_id must be a portable identifier, got {self.study_id!r}")
        _validate_timeout(self.timeout_seconds)
        if self.development_start >= self.test_start:
            raise InputValidationError(
                f"development_start ({self.development_start}) must be strictly before test_start ({self.test_start})",
                field="development_start",
                reason="development_start >= test_start",
            )
        if self.date_selection_rule != mode["date_selection_rule"]:
            raise _config_error(
                "date_selection_rule",
                f"Unsupported date_selection_rule '{self.date_selection_rule}'; expected '{mode['date_selection_rule']}'",
            )
        if self.nifty_input.source_kind != mode["source_kind"]:
            raise _config_error(
                "inputs.nifty.source_kind",
                f"inputs.nifty.source_kind must be '{mode['source_kind']}', got {self.nifty_input.source_kind!r}",
            )
        if self.vix_input.source_kind != mode["source_kind"]:
            raise _config_error(
                "inputs.vix.source_kind",
                f"inputs.vix.source_kind must be '{mode['source_kind']}', got {self.vix_input.source_kind!r}",
            )


def _load_bound_file(value: Any, field_name: str) -> BoundFile:
    doc = _require_keys(value, {"path", "raw_byte_count", "sha256"}, field_name)
    return BoundFile(
        path=_require_absolute_path(doc["path"], f"{field_name}.path"),
        raw_byte_count=_require_byte_count(doc["raw_byte_count"], f"{field_name}.raw_byte_count"),
        sha256=_require_sha256(doc["sha256"], f"{field_name}.sha256"),
    )


def _load_file_binding(doc: Mapping[str, Any], bound: BoundFile, field_name: str) -> FileBinding:
    """Parses one file's declared source fields; the caller has already validated its keys and identity."""
    source_url = doc["source_url"]
    if source_url is not None:
        source_url = _require_string(source_url, f"{field_name}.source_url")

    interval: Optional[Tuple[datetime.date, datetime.date]] = None
    if doc["requested_interval"] is not None:
        raw_interval = doc["requested_interval"]
        if type(raw_interval) is not list or len(raw_interval) != 2:
            raise _config_error(f"{field_name}.requested_interval", f"{field_name}.requested_interval must be null or two dates")
        interval = (
            _parse_date(raw_interval[0], f"{field_name}.requested_interval[0]"),
            _parse_date(raw_interval[1], f"{field_name}.requested_interval[1]"),
        )

    acquisition: Optional[datetime.datetime] = None
    if doc["acquisition_time"] is not None:
        text = _require_string(doc["acquisition_time"], f"{field_name}.acquisition_time")
        try:
            acquisition = datetime.datetime.fromisoformat(text)
        except ValueError as exc:
            raise _config_error(f"{field_name}.acquisition_time", f"{field_name}.acquisition_time is not ISO: {exc}") from exc

    return FileBinding(
        bound=bound,
        source_url=source_url,
        requested_interval=interval,
        acquisition_time=acquisition,
        source_use_note=_require_string(doc["source_use_note"], f"{field_name}.source_use_note"),
    )


def _load_input_binding(value: Any, role: str, is_historical: bool = False) -> InputBinding:
    field_name = f"inputs.{role}"
    if type(value) is not dict:
        raise _config_error(field_name, f"Field '{field_name}' must be an object, got {type(value).__name__}")

    if is_historical:
        doc = _require_keys(value, {"units", "source_kind", "files"}, field_name)
        if doc["units"] != EXPECTED_INPUT_UNITS[role]:
            raise _config_error(f"{field_name}.units", f"{field_name}.units must be '{EXPECTED_INPUT_UNITS[role]}', got {doc['units']!r}")
        if doc["source_kind"] != SOURCE_KIND_HISTORICAL:
            raise _config_error(f"{field_name}.source_kind", f"{field_name}.source_kind must be '{SOURCE_KIND_HISTORICAL}', got {doc['source_kind']!r}")
        raw_files = doc["files"]
        if type(raw_files) is not list or not raw_files:
            raise _config_error(f"{field_name}.files", f"{field_name}.files must be a non-empty list")
        file_bindings: List[FileBinding] = []
        seen_paths: Set[str] = set()
        for idx, file_item in enumerate(raw_files):
            item_field = f"{field_name}.files[{idx}]"
            f_doc = _require_keys(
                file_item,
                {
                    "path",
                    "raw_byte_count",
                    "sha256",
                    "source_url",
                    "requested_interval",
                    "acquisition_time",
                    "source_use_note",
                },
                item_field,
            )
            f_path = _require_absolute_path(f_doc["path"], f"{item_field}.path")
            norm_p = _norm_path(f_path)
            if norm_p in seen_paths:
                raise _config_error(f"{item_field}.path", f"Duplicate input path: {f_path}")
            seen_paths.add(norm_p)
            bound = BoundFile(
                path=f_path,
                raw_byte_count=_require_byte_count(f_doc["raw_byte_count"], f"{item_field}.raw_byte_count"),
                sha256=_require_sha256(f_doc["sha256"], f"{item_field}.sha256"),
            )
            file_bindings.append(_load_file_binding(f_doc, bound, item_field))
        return InputBinding(units=doc["units"], source_kind=doc["source_kind"], files=tuple(file_bindings))

    else:
        doc = _require_keys(
            value,
            {
                "path",
                "raw_byte_count",
                "sha256",
                "units",
                "source_kind",
                "source_url",
                "requested_interval",
                "acquisition_time",
                "source_use_note",
            },
            field_name,
        )
        bound = BoundFile(
            path=_require_absolute_path(doc["path"], f"{field_name}.path"),
            raw_byte_count=_require_byte_count(doc["raw_byte_count"], f"{field_name}.raw_byte_count"),
            sha256=_require_sha256(doc["sha256"], f"{field_name}.sha256"),
        )
        if doc["units"] != EXPECTED_INPUT_UNITS[role]:
            raise _config_error(f"{field_name}.units", f"{field_name}.units must be '{EXPECTED_INPUT_UNITS[role]}', got {doc['units']!r}")
        if doc["source_kind"] != SOURCE_KIND_SYNTHETIC:
            raise _config_error(f"{field_name}.source_kind", f"{field_name}.source_kind must be '{SOURCE_KIND_SYNTHETIC}', got {doc['source_kind']!r}")
        return InputBinding(
            units=doc["units"],
            source_kind=doc["source_kind"],
            files=(_load_file_binding(doc, bound, field_name),),
        )


def load_study_configuration(
    config_dict: Dict[str, Any],
    *,
    config_path: Optional[str] = None,
    config_bytes: Optional[bytes] = None,
) -> StudyConfiguration:
    """
    Validates and constructs a StudyConfiguration from a parsed dictionary.

    Every key is required: no scientific or identity default is supplied here. Rejects
    unknown keys, booleans in integer fields, unsupported versions and relative paths before
    any input is opened. Duplicate keys and nonfinite tokens are rejected by the strict parser.
    """
    if type(config_dict) is not dict:
        raise _config_error("config", "Configuration root must be an object")

    schema_version = config_dict.get("schema_version")
    if not isinstance(schema_version, str) or schema_version not in SUPPORTED_CONFIG_MODES:
        raise InputValidationError(
            f"Unsupported configuration schema_version '{schema_version}'; expected one of {sorted(SUPPORTED_CONFIG_MODES.keys())}",
            field="schema_version",
            reason=f"Expected one of {sorted(SUPPORTED_CONFIG_MODES.keys())}",
        )

    mode = SUPPORTED_CONFIG_MODES[schema_version]
    is_historical = schema_version == STUDY_SCHEMA_VERSION_V3

    data_kind = config_dict.get("data_kind")
    if data_kind != mode["data_kind"]:
        raise InputValidationError(
            f"data_kind '{data_kind}' is not valid for schema '{schema_version}'; expected '{mode['data_kind']}'",
            field="data_kind",
            reason=f"Expected {mode['data_kind']} for {schema_version}",
        )

    dev_status = config_dict.get("development_status")
    if dev_status != mode["development_status"]:
        raise _config_error(
            "development_status",
            f"Unsupported development_status '{dev_status}'; expected '{mode['development_status']}'",
        )

    rule = config_dict.get("date_selection_rule")
    if rule != mode["date_selection_rule"]:
        raise _config_error(
            "date_selection_rule",
            f"Unsupported date_selection_rule '{rule}'; expected '{mode['date_selection_rule']}'",
        )

    doc = _require_keys(
        config_dict,
        {
            "schema_version",
            "study_id",
            "protocol_id",
            "data_kind",
            "development_status",
            "development_start",
            "test_start",
            "date_selection_rule",
            "workspace_root",
            "allowed_output_parent",
            "timeout_seconds",
            "inputs",
            "admission",
            "tools",
            "source_modules",
            "runtime",
            "uncertainty",
        },
        "config",
    )

    inputs = _require_keys(doc["inputs"], {"nifty", "vix", "calendar"}, "inputs")
    tools = _require_keys(
        doc["tools"],
        {"node_executable", "python_executable", "replay_script", "candidate_build_manifest", "models"},
        "tools",
    )
    runtime = _require_keys(doc["runtime"], {"python_version", "python_implementation", "dependency_versions"}, "runtime")
    dependency_versions = _require_keys(runtime["dependency_versions"], set(REQUIRED_DEPENDENCIES), "runtime.dependency_versions")
    for name in REQUIRED_DEPENDENCIES:
        _require_string(dependency_versions[name], f"runtime.dependency_versions.{name}")

    unc_doc = _require_keys(doc["uncertainty"], {"protocol_id", "max_resample_positions"}, "uncertainty")
    if unc_doc["protocol_id"] != UNCERTAINTY_PROTOCOL_ID:
        raise _config_error("uncertainty.protocol_id", f"Expected uncertainty.protocol_id '{UNCERTAINTY_PROTOCOL_ID}', got {unc_doc['protocol_id']!r}")
    max_resample = unc_doc["max_resample_positions"]
    if type(max_resample) is not int or type(max_resample) is bool or max_resample < 1 or max_resample > MAX_RESAMPLE_POSITIONS:
        raise _config_error("uncertainty.max_resample_positions", f"uncertainty.max_resample_positions must be integer in [1, {MAX_RESAMPLE_POSITIONS}], got {max_resample!r}")
    if is_historical and max_resample != HISTORICAL_MAX_RESAMPLE_POSITIONS:
        raise _config_error(
            "uncertainty.max_resample_positions",
            f"historical uncertainty.max_resample_positions must be exactly {HISTORICAL_MAX_RESAMPLE_POSITIONS}, got {max_resample!r}",
        )

    source_modules_doc = _require_keys(doc["source_modules"], set(REQUIRED_SOURCE_MODULES), "source_modules")
    source_modules: Dict[str, Dict[str, Any]] = {}
    for rel_path in REQUIRED_SOURCE_MODULES:
        entry = _require_keys(source_modules_doc[rel_path], {"raw_byte_count", "sha256"}, f"source_modules[{rel_path}]")
        source_modules[rel_path] = {
            "raw_byte_count": _require_byte_count(entry["raw_byte_count"], f"source_modules[{rel_path}].raw_byte_count"),
            "sha256": _require_sha256(entry["sha256"], f"source_modules[{rel_path}].sha256"),
        }

    if type(doc["timeout_seconds"]) is not int:
        raise InputValidationError(
            f"timeout_seconds must be a positive integer, got {doc['timeout_seconds']!r}",
            field="timeout_seconds",
            reason="Invalid timeout_seconds",
        )

    models = _load_bound_file(tools["models"], "tools.models")
    if models.sha256 != EXPECTED_MODELS_SHA256:
        raise _config_error("tools.models.sha256", f"tools.models.sha256 must be the pinned model hash, got {models.sha256}")

    nifty_binding = _load_input_binding(inputs["nifty"], "nifty", is_historical=is_historical)
    vix_binding = _load_input_binding(inputs["vix"], "vix", is_historical=is_historical)
    if is_historical:
        n_paths = {_norm_path(f.bound.path) for f in nifty_binding.files}
        v_paths = {_norm_path(f.bound.path) for f in vix_binding.files}
        dup = n_paths & v_paths
        if dup:
            raise _config_error("inputs", f"Duplicate input path across input series: {sorted(dup)[0]}")

    return StudyConfiguration(
        schema_version=doc["schema_version"],
        study_id=doc["study_id"],
        protocol_id=doc["protocol_id"],
        data_kind=doc["data_kind"],
        development_status=doc["development_status"],
        development_start=_parse_date(doc["development_start"], "development_start"),
        test_start=_parse_date(doc["test_start"], "test_start"),
        date_selection_rule=doc["date_selection_rule"],
        workspace_root=_require_absolute_path(doc["workspace_root"], "workspace_root"),
        allowed_output_parent=_require_absolute_path(doc["allowed_output_parent"], "allowed_output_parent"),
        timeout_seconds=doc["timeout_seconds"],
        nifty_input=nifty_binding,
        vix_input=vix_binding,
        calendar=_load_bound_file(inputs["calendar"], "inputs.calendar"),
        admission=_load_bound_file(doc["admission"], "admission"),
        node_executable=_load_bound_file(tools["node_executable"], "tools.node_executable"),
        python_executable=_load_bound_file(tools["python_executable"], "tools.python_executable"),
        replay_script=_load_bound_file(tools["replay_script"], "tools.replay_script"),
        candidate_build_manifest=_load_bound_file(tools["candidate_build_manifest"], "tools.candidate_build_manifest"),
        models=models,
        source_modules=source_modules,
        python_version=_require_string(runtime["python_version"], "runtime.python_version"),
        python_implementation=_require_string(runtime["python_implementation"], "runtime.python_implementation"),
        dependency_versions=dict(dependency_versions),
        uncertainty=dict(unc_doc),
        config_path=config_path,
        config_bytes=config_bytes,
    )


def load_study_configuration_file(config_path: Union[str, Path]) -> StudyConfiguration:
    """Loads a configuration keeping its exact original bytes for later verification and persistence."""
    path_text = _require_absolute_path(str(config_path), "config_path")
    raw = Path(path_text).read_bytes()
    return load_study_configuration(parse_strict_json_bytes(raw), config_path=path_text, config_bytes=raw)


def _require_configuration_from_its_bytes(config: StudyConfiguration) -> None:
    """
    Requires the executable configuration to be the strict parse of its own original bytes.

    The direct API accepts a parsed dictionary beside raw bytes, while H and the run artifacts
    bind those raw bytes, so fields taken from anywhere else would run unapproved settings.
    Value-equal reformatting still parses equal; H names the exact bytes it approved.
    """
    parsed = load_study_configuration(
        parse_strict_json_bytes(config.config_bytes),
        config_path=config.config_path,
        config_bytes=config.config_bytes,
    )
    if parsed != config:
        raise InputValidationError(
            "Configuration fields differ from the strict parse of its original bytes",
            field="config",
            reason="configuration/bytes mismatch",
        )


def _parse_calendar_bytes(raw: bytes) -> List[datetime.date]:
    doc = parse_strict_json_bytes(raw)
    calendar = _require_keys(doc, {"sessions"}, "calendar")
    if type(calendar["sessions"]) is not list or not calendar["sessions"]:
        raise _config_error("calendar.sessions", "calendar.sessions must be a non-empty list of ISO dates")
    return [_parse_date(item, f"calendar.sessions[{idx}]") for idx, item in enumerate(calendar["sessions"])]


def compute_admission_inventory(
    aligned_pair: AlignedPair,
    *,
    test_start: datetime.date,
) -> Dict[str, Any]:
    """
    Computes the input-only admission gap inventory on mature master test span [T, N-20).

    Uses ONLY aligned input observations, warmup boundary (<200), and missing exact-date VIX.
    Does NOT invoke outcomes, feature predictors, comparators, replay, or scoring.
    """
    obs_list = aligned_pair.aligned_observations
    total_n = len(obs_list)

    # Locate test_start_index
    test_start_index: Optional[int] = None
    for idx, obs in enumerate(obs_list):
        if obs.date == test_start:
            test_start_index = idx
            break

    if test_start_index is None:
        raise InputValidationError(
            f"test_start date '{test_start.isoformat()}' not found in aligned observations",
            field="test_start",
            reason=f"Date {test_start.isoformat()} absent from master axis",
        )

    mature_test_start = test_start_index
    mature_test_end = max(mature_test_start, total_n - HORIZON_SESSIONS)
    span_count = mature_test_end - mature_test_start

    warmup_gaps = []
    missing_vix_gaps = []
    union_gaps = []

    for idx in range(mature_test_start, mature_test_end):
        obs = obs_list[idx]
        is_warmup = idx < WARMUP_ORIGIN_INDEX
        is_missing_vix = obs.vix_close is None

        if is_warmup:
            warmup_gaps.append(idx)
        if is_missing_vix:
            missing_vix_gaps.append(idx)
        if is_warmup or is_missing_vix:
            union_gaps.append(idx)

    return {
        "mature_test_start_index": mature_test_start,
        "mature_test_end_index": mature_test_end,
        "mature_test_span_count": span_count,
        "warmup_gap_positions": tuple(warmup_gaps),
        "warmup_gap_count": len(warmup_gaps),
        "missing_vix_gap_positions": tuple(missing_vix_gaps),
        "missing_vix_gap_count": len(missing_vix_gaps),
        "union_gap_positions": tuple(union_gaps),
        "union_gap_count": len(union_gaps),
        "gap_digest": _gap_digest(union_gaps),
        "policy": ADMISSION_POLICY,
    }


def _gap_digest(positions: Sequence[int]) -> str:
    """Digest of the ordered union gap positions."""
    return _sha256_upper(json.dumps(list(positions), separators=(",", ":")).encode("utf-8"))


def _build_admission_record(
    nifty_series: LoadedSeries,
    vix_series: LoadedSeries,
    aligned: AlignedPair,
    calendar_raw: bytes,
    *,
    development_start: Optional[datetime.date] = None,
    test_start: Optional[datetime.date] = None,
    is_historical: bool = False,
) -> Dict[str, Any]:
    """Builds the frozen record from loaded inputs only; it never names the configuration."""
    axis_dates = [obs.date for obs in aligned.aligned_observations]
    total_n = len(axis_dates)

    if is_historical:
        d_idx, t_idx, e_idx, span = derive_historical_split_cutoffs(total_n)
        # Optional configured dates are checked, never used to choose the window
        derived_dev_start, derived_test_start, _ = derive_historical_split_cutoffs(
            axis_dates,
            expected_development_start=development_start,
            expected_test_start=test_start,
        )
        inventory = compute_admission_inventory(aligned, test_start=derived_test_start)

        def _admitted_historical_files(series: LoadedSeries) -> Dict[str, Any]:
            files_list = []
            for prov in series.provenance:
                files_list.append({
                    "raw_byte_count": prov.raw_byte_count,
                    "sha256": prov.sha256.upper(),
                    "record_count": prov.record_count,
                    "observed_first_date": prov.observed_first_date.isoformat(),
                    "observed_last_date": prov.observed_last_date.isoformat(),
                })
            return {
                "files": files_list,
                "record_count": sum(p.record_count for p in series.provenance),
                "observed_first_date": series.records[0].date.isoformat(),
                "observed_last_date": series.records[-1].date.isoformat(),
            }

        return {
            "schema_version": SCHEMA_VERSION_ADMISSION_V2,
            "data_kind": DATA_KIND_HISTORICAL,
            "protocol_id": STUDY_PROTOCOL_ID,
            "date_selection_rule": DATE_SELECTION_RULE_HISTORICAL,
            "development_start": derived_dev_start.isoformat(),
            "test_start": derived_test_start.isoformat(),
            "development_start_index": d_idx,
            "inputs": {
                "nifty": _admitted_historical_files(nifty_series),
                "vix": _admitted_historical_files(vix_series),
                "calendar": {
                    "raw_byte_count": len(calendar_raw),
                    "sha256": _sha256_upper(calendar_raw),
                    "session_count": len(aligned.expected_sessions or ()),
                },
            },
            "axis": {
                "session_count": total_n,
                "first_date": axis_dates[0].isoformat(),
                "last_date": axis_dates[-1].isoformat(),
            },
            "mature_test_start_index": t_idx,
            "mature_test_end_index": e_idx,
            "mature_test_span_count": span,
            "warmup_gap_positions": list(inventory["warmup_gap_positions"]),
            "warmup_gap_count": inventory["warmup_gap_count"],
            "missing_vix_gap_positions": list(inventory["missing_vix_gap_positions"]),
            "missing_vix_gap_count": inventory["missing_vix_gap_count"],
            "union_gap_positions": list(inventory["union_gap_positions"]),
            "union_gap_count": inventory["union_gap_count"],
            "gap_digest": inventory["gap_digest"],
            "policy": inventory["policy"],
        }
    else:
        if development_start is None or development_start not in axis_dates:
            raise InputValidationError(
                f"development_start date '{development_start}' not found in aligned observations",
                field="development_start",
                reason=f"Date {development_start} absent from master axis",
            )
        if test_start is None or test_start not in axis_dates:
            raise InputValidationError(
                f"test_start date '{test_start}' not found in aligned observations",
                field="test_start",
                reason=f"Date {test_start} absent from master axis",
            )
        inventory = compute_admission_inventory(aligned, test_start=test_start)

        def _admitted_file(series: LoadedSeries) -> Dict[str, Any]:
            if len(series.provenance) != 1:
                raise InputValidationError("Each admitted series must come from exactly one file", field="provenance", reason="provenance count")
            prov = series.provenance[0]
            return {"raw_byte_count": prov.raw_byte_count, "sha256": prov.sha256.upper(), "record_count": prov.record_count}

        return {
            "schema_version": SCHEMA_VERSION_ADMISSION,
            "data_kind": DATA_KIND_SYNTHETIC,
            "protocol_id": STUDY_PROTOCOL_ID,
            "date_selection_rule": DATE_SELECTION_RULE,
            "development_start": development_start.isoformat(),
            "test_start": test_start.isoformat(),
            "inputs": {
                "nifty": _admitted_file(nifty_series),
                "vix": _admitted_file(vix_series),
                "calendar": {
                    "raw_byte_count": len(calendar_raw),
                    "sha256": _sha256_upper(calendar_raw),
                    "session_count": len(aligned.expected_sessions or ()),
                },
            },
            "axis": {
                "session_count": total_n,
                "first_date": axis_dates[0].isoformat(),
                "last_date": axis_dates[-1].isoformat(),
            },
            "mature_test_start_index": inventory["mature_test_start_index"],
            "mature_test_end_index": inventory["mature_test_end_index"],
            "mature_test_span_count": inventory["mature_test_span_count"],
            "warmup_gap_positions": list(inventory["warmup_gap_positions"]),
            "warmup_gap_count": inventory["warmup_gap_count"],
            "missing_vix_gap_positions": list(inventory["missing_vix_gap_positions"]),
            "missing_vix_gap_count": inventory["missing_vix_gap_count"],
            "union_gap_positions": list(inventory["union_gap_positions"]),
            "union_gap_count": inventory["union_gap_count"],
            "gap_digest": inventory["gap_digest"],
            "policy": inventory["policy"],
        }


def _align_with_calendar(nifty_series: LoadedSeries, vix_series: LoadedSeries, calendar_raw: bytes) -> AlignedPair:
    aligned = align_pair(nifty_series, vix_series, expected_sessions=_parse_calendar_bytes(calendar_raw))
    if aligned.calendar_status != "matches_supplied_sessions":
        raise InputValidationError(
            f"Inputs do not match the supplied calendar: status '{aligned.calendar_status}'",
            field="calendar_status",
            reason=f"calendar_status is '{aligned.calendar_status}'",
        )
    return aligned


def prepare_historical_admission(
    *,
    nifty_specs: Sequence[FileInputSpec],
    vix_specs: Sequence[FileInputSpec],
    calendar_path: Union[str, Path],
) -> Dict[str, Any]:
    """
    Prepares the frozen input-only admission record for historical inputs (v2).
    """
    calendar_raw = Path(calendar_path).read_bytes()
    nifty_series = load_series(SERIES_ID_NIFTY, list(nifty_specs))
    vix_series = load_series(SERIES_ID_VIX, list(vix_specs))
    aligned = _align_with_calendar(nifty_series, vix_series, calendar_raw)
    return _build_admission_record(
        nifty_series,
        vix_series,
        aligned,
        calendar_raw,
        is_historical=True,
    )


def prepare_input_admission(
    *,
    nifty_spec: Union[FileInputSpec, Sequence[FileInputSpec]],
    vix_spec: Union[FileInputSpec, Sequence[FileInputSpec]],
    calendar_path: Union[str, Path],
    development_start: Optional[datetime.date] = None,
    test_start: Optional[datetime.date] = None,
) -> Dict[str, Any]:
    """
    Prepares the frozen input-only synthetic admission record (v1).

    Historical inputs have their own producer, prepare_historical_admission, which derives the
    cutoffs from the admitted axis. This loads and aligns the admitted inputs and computes D/T,
    gap and policy metadata. It makes no outcome, feature, predictor, fit, replay or scoring call,
    and it never sees results. The caller freezes the returned record before writing the
    configuration that binds it.
    """
    calendar_raw = Path(calendar_path).read_bytes()
    nifty_series = load_series(SERIES_ID_NIFTY, [nifty_spec] if isinstance(nifty_spec, FileInputSpec) else list(nifty_spec))
    vix_series = load_series(SERIES_ID_VIX, [vix_spec] if isinstance(vix_spec, FileInputSpec) else list(vix_spec))
    aligned = _align_with_calendar(nifty_series, vix_series, calendar_raw)
    return _build_admission_record(
        nifty_series,
        vix_series,
        aligned,
        calendar_raw,
        development_start=development_start,
        test_start=test_start,
    )


def verify_admission_against_reference_plan(
    admission_inventory: Dict[str, Any],
    reference_plan: SplitPlan,
) -> None:
    """
    Verifies that the frozen admission gap inventory matches the reference SplitPlan exclusions
    on the mature test span [T, N-20) BEFORE invoking comparators or replay.

    Compares the ordered positions, their count and their digest. The canonical planner still
    owns eligibility; this only proves the frozen record and the planner agree.
    """
    # Value comparison below would accept true for 1, so native types are required here too
    for name, value in (
        ("mature_test_start_index", admission_inventory["mature_test_start_index"]),
        ("mature_test_end_index", admission_inventory["mature_test_end_index"]),
        ("union_gap_count", admission_inventory["union_gap_count"]),
        *(("union_gap_positions", position) for position in admission_inventory["union_gap_positions"]),
    ):
        if type(value) is not int:
            raise InputValidationError(
                f"Admission {name} must be a native integer, got {value!r}",
                field="admission_inventory",
                reason="non-native integer",
            )

    t_start = admission_inventory["mature_test_start_index"]
    t_end = admission_inventory["mature_test_end_index"]

    if t_start != reference_plan.test_start_index:
        raise InputValidationError(
            f"Admission mature start {t_start} differs from plan test start {reference_plan.test_start_index}",
            field="admission_inventory",
            reason="mature span start mismatch",
        )

    span_indices = set(range(t_start, t_end))
    test_indices_in_span = set(reference_plan.test_indices) & span_indices
    actual_excluded_in_span = tuple(sorted(span_indices - test_indices_in_span))

    expected_union_gaps = tuple(admission_inventory["union_gap_positions"])

    if actual_excluded_in_span != expected_union_gaps:
        raise InputValidationError(
            f"Admission gap inventory mismatch: expected {len(expected_union_gaps)} gaps, planner excluded {len(actual_excluded_in_span)}",
            field="admission_inventory",
            reason=f"Expected gaps {expected_union_gaps[:5]}..., got {actual_excluded_in_span[:5]}...",
        )
    if admission_inventory["union_gap_count"] != len(actual_excluded_in_span):
        raise InputValidationError(
            f"Admission gap count {admission_inventory['union_gap_count']} differs from planner exclusions",
            field="admission_inventory",
            reason="gap count mismatch",
        )
    if admission_inventory["gap_digest"] != _gap_digest(actual_excluded_in_span):
        raise InputValidationError(
            "Admission gap digest differs from the planner's ordered exclusions",
            field="admission_inventory",
            reason="gap digest mismatch",
        )


def _compare_field_aware_recursive(actual: Any, expected: Any, path: str = "root") -> None:
    """
    Recursive field-aware comparison between actual replay output and its trusted expectation.

    Rules:
      - Exact keys and sequence lengths/order.
      - Decimal Close strings compared as strings.
      - Booleans and nulls compared strictly (no bool == int).
      - Integer fields (origin indices, raw_byte_count, record_count, bytes, compiler_exit):
        exact non-boolean integers in safe range.
      - Numeric payload fields: finite binary64-representable numbers, exclude booleans,
        compare represented float value (accepting 0 vs 0.0 and signed zero).
      - SHA-256 strings: compared case-insensitively, valid 64-hex.
    """
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            raise ValueError(f"{path}: expected dict, got {type(actual).__name__}")
        if set(actual.keys()) != set(expected.keys()):
            missing = set(expected.keys()) - set(actual.keys())
            extra = set(actual.keys()) - set(expected.keys())
            raise ValueError(f"{path}: key mismatch. Missing: {missing}, Extra: {extra}")
        for k in expected:
            _compare_field_aware_recursive(actual[k], expected[k], f"{path}.{k}")
        return

    if isinstance(expected, list):
        if not isinstance(actual, list):
            raise ValueError(f"{path}: expected list, got {type(actual).__name__}")
        if len(actual) != len(expected):
            raise ValueError(f"{path}: length mismatch. Expected {len(expected)}, got {len(actual)}")
        for idx, (a_item, e_item) in enumerate(zip(actual, expected)):
            _compare_field_aware_recursive(a_item, e_item, f"{path}[{idx}]")
        return

    if expected is None:
        if actual is not None:
            raise ValueError(f"{path}: expected None, got {actual!r}")
        return

    if isinstance(expected, bool):
        if not isinstance(actual, bool) or actual != expected:
            raise ValueError(f"{path}: expected bool {expected!r}, got {actual!r}")
        return

    path_suffix = path.split(".")[-1]

    # SHA-256 fields
    if path_suffix == "sha256":
        if not isinstance(actual, str) or not _SHA256_HEX_REGEX.match(actual):
            raise ValueError(f"{path}: invalid 64-hex SHA-256 string: {actual!r}")
        if not isinstance(expected, str) or not _SHA256_HEX_REGEX.match(expected):
            raise ValueError(f"{path}: invalid expected SHA-256 string: {expected!r}")
        if actual.upper() != expected.upper():
            raise ValueError(f"{path}: SHA-256 mismatch: expected {expected}, got {actual}")
        return

    # Numeric payload fields
    if path_suffix in NUMERIC_PAYLOAD_FIELDS:
        if isinstance(actual, bool) or isinstance(expected, bool):
            raise ValueError(f"{path}: booleans are not allowed for numeric field")
        if not isinstance(actual, (int, float)) or not isinstance(expected, (int, float)):
            raise ValueError(f"{path}: expected numeric float/int, got actual={type(actual).__name__}, expected={type(expected).__name__}")
        try:
            actual_value = float(actual)
            expected_value = float(expected)
        except OverflowError as exc:
            raise ValueError(f"{path}: numeric value outside binary64 range") from exc
        if not math.isfinite(actual_value) or not math.isfinite(expected_value):
            raise ValueError(f"{path}: non-finite numeric value in payload: actual={actual}, expected={expected}")
        # An integer that binary64 would round is not the represented value it resembles
        if isinstance(actual, int) and int(actual_value) != actual:
            raise ValueError(f"{path}: integer is not exactly representable in binary64")
        if actual_value != expected_value:
            raise ValueError(f"{path}: numeric payload value mismatch: expected {expected}, got {actual}")
        return

    # Every other declared number on this wire is an integer count or status
    if type(expected) is int:
        if type(actual) is not int:
            raise ValueError(f"{path}: expected non-boolean integer, got {actual!r}")
        if not (0 <= actual <= SAFE_INTEGER_MAX):
            raise ValueError(f"{path}: integer out of safe bounds [0, 2^53-1]: {actual}")
        if actual != expected:
            raise ValueError(f"{path}: int mismatch. Expected {expected}, got {actual}")
        return

    # String fields (including Decimal Close strings, dates, market_regime, etc.)
    if isinstance(expected, str):
        if not isinstance(actual, str) or actual != expected:
            raise ValueError(f"{path}: string mismatch. Expected {expected!r}, got {actual!r}")
        return

    raise ValueError(f"{path}: unsupported expected value {expected!r}")


def _require_wire_keys(value: Any, keys: Set[str], path: str) -> Dict[str, Any]:
    if type(value) is not dict:
        raise ValueError(f"{path}: expected object, got {type(value).__name__}")
    if set(value.keys()) != keys:
        raise ValueError(f"{path}: key mismatch. Missing: {keys - set(value.keys())}, Extra: {set(value.keys()) - keys}")
    return value


def _require_wire_int(value: Any, expected: int, path: str) -> None:
    if type(value) is not int:
        raise ValueError(f"{path}: expected non-boolean integer, got {value!r}")
    if value != expected:
        raise ValueError(f"{path}: expected {expected}, got {value}")


def _require_wire_number(value: Any, path: str) -> None:
    if type(value) not in (int, float):
        raise ValueError(f"{path}: expected finite number, got {type(value).__name__}")
    try:
        finite = math.isfinite(value)
    except OverflowError as exc:
        raise ValueError(f"{path}: number outside binary64 range") from exc
    if not finite:
        raise ValueError(f"{path}: expected finite number, got {value!r}")


def _validate_forecast_object(forecast: Any, path: str) -> None:
    """Validates one DirectionalForecast from the existing wire; probabilities are checked with all rows."""
    doc = _require_wire_keys(forecast, FORECAST_OBJECT_KEYS, path)
    if doc["horizon"] != "20D":
        raise ValueError(f"{path}.horizon: expected '20D', got {doc['horizon']!r}")
    _require_wire_int(doc["days"], 20, f"{path}.days")
    if doc["expected_direction"] not in EXPECTED_DIRECTIONS:
        raise ValueError(f"{path}.expected_direction: unsupported value {doc['expected_direction']!r}")
    if doc["confidence"] not in CONFIDENCE_LEVELS:
        raise ValueError(f"{path}.confidence: unsupported value {doc['confidence']!r}")
    _require_wire_number(doc["expected_return_pct"], f"{path}.expected_return_pct")
    _require_wire_number(doc["signal_quality"], f"{path}.signal_quality")

    disagreement = _require_wire_keys(
        doc["model_disagreement"],
        {"components", "dispersion_std", "consensus_level"},
        f"{path}.model_disagreement",
    )
    components = _require_wire_keys(disagreement["components"], FORECAST_COMPONENT_KEYS, f"{path}.model_disagreement.components")
    for name, value in components.items():
        _require_wire_number(value, f"{path}.model_disagreement.components.{name}")
    _require_wire_number(disagreement["dispersion_std"], f"{path}.model_disagreement.dispersion_std")
    if disagreement["consensus_level"] not in CONSENSUS_LEVELS:
        raise ValueError(f"{path}.model_disagreement.consensus_level: unsupported value {disagreement['consensus_level']!r}")

    for key in ("top_bullish_drivers", "top_bearish_drivers"):
        drivers = doc[key]
        if type(drivers) is not list or not all(type(item) is str for item in drivers):
            raise ValueError(f"{path}.{key}: expected list of strings")


def validate_replay_response(
    response_doc: Any,
    *,
    request_bytes: bytes,
    features: FeatureSeries,
    trusted_model: Mapping[str, Any],
    trusted_build_manifest: Mapping[str, Any],
) -> Dict[int, HeuristicPrediction]:
    """
    Validates an untrusted replay response against the original request and trusted identities.

    All origins are validated before any target is selected. The child's own model and build
    preflight is counterevidence, not a substitute: this checks what the response claims.
    Request identity comes from the original bytes, never a reserialization.
    """
    root = _require_wire_keys(response_doc, RESPONSE_ROOT_KEYS, "response")

    # Validate top-level schema and claim
    if root["schema_version"] != "nivesh-replay-output-v1":
        raise ValueError(f"Unsupported replay schema_version '{root['schema_version']}'")
    if root["claim_label"] != REPLAY_CLAIM_LABEL:
        raise ValueError(f"Unexpected claim_label '{root['claim_label']}'")

    # Validate computed_provenance
    comp_prov = _require_wire_keys(root["computed_provenance"], {"request", "model", "build"}, "computed_provenance")

    # Request provenance
    req_prov = _require_wire_keys(comp_prov["request"], {"raw_byte_count", "sha256"}, "computed_provenance.request")
    _require_wire_int(req_prov["raw_byte_count"], len(request_bytes), "computed_provenance.request.raw_byte_count")
    _compare_field_aware_recursive(req_prov["sha256"], _sha256_upper(request_bytes), "computed_provenance.request.sha256")

    # Model provenance
    model_prov = _require_wire_keys(
        comp_prov["model"],
        {"path", "raw_byte_count", "sha256", "platt_params"},
        "computed_provenance.model",
    )
    if model_prov["path"] != trusted_model["path"]:
        raise ValueError(f"Model path mismatch: {model_prov['path']!r}")
    _require_wire_int(model_prov["raw_byte_count"], trusted_model["raw_byte_count"], "computed_provenance.model.raw_byte_count")
    try:
        _compare_field_aware_recursive(model_prov["sha256"], trusted_model["sha256"], "computed_provenance.model.sha256")
    except ValueError as exc:
        raise ValueError(f"Model sha256 mismatch: {exc}") from exc
    platt = model_prov["platt_params"]
    if (
        type(platt) is not list
        or len(platt) != 2
        or any(type(item) is not float for item in platt)
        or tuple(platt) != EXPECTED_20D_PLATT_PARAMS
    ):
        raise ValueError(f"Model platt_params mismatch: {platt!r}")

    # Build provenance: the exact trusted manifest, field by field
    build_doc = comp_prov["build"]
    if type(build_doc) is not dict or build_doc.get("schema_version") != EXPECTED_BUILD_SCHEMA_VERSION:
        raise ValueError(f"Unsupported candidate build schema: {build_doc!r}")
    _compare_field_aware_recursive(build_doc, dict(trusted_build_manifest), "computed_provenance.build")

    # Field-aware recursive comparison on declared_input
    expected_input_doc = parse_strict_json(request_bytes.decode("utf-8"))
    _compare_field_aware_recursive(root["declared_input"], expected_input_doc, "declared_input")

    # Validate forecasts
    forecasts = root["forecasts"]
    if type(forecasts) is not list:
        raise ValueError("forecasts must be a list")

    total_rows = len(features.records)
    if len(forecasts) != total_rows:
        raise ValueError(f"Forecasts count ({len(forecasts)}) != feature records count ({total_rows})")

    ready_predictions: List[HeuristicPrediction] = []

    for idx, f_entry in enumerate(forecasts):
        row = _require_wire_keys(f_entry, FORECAST_ROW_KEYS, f"forecasts[{idx}]")
        rec = features.records[idx]

        _require_wire_int(row["origin_index"], rec.origin_index, f"forecasts[{idx}].origin_index")
        if row["origin_date"] != rec.origin_date.isoformat():
            raise ValueError(f"Forecast row {idx} origin_date ({row['origin_date']}) != expected ({rec.origin_date})")

        fc = row["forecast"]
        if not rec.feature_ready:
            if fc is not None:
                raise ValueError(f"Unready origin {rec.origin_index} must have forecast=null, got {fc!r}")
            continue

        if not isinstance(fc, dict):
            raise ValueError(f"Ready origin {rec.origin_index} missing forecast object")
        _validate_forecast_object(fc, f"forecasts[{idx}].forecast")

        # Map to BEAR, NEUTRAL, BULL order
        ready_predictions.append(
            HeuristicPrediction(
                origin_index=rec.origin_index,
                origin_date=rec.origin_date,
                probabilities=(fc["probability_bearish"], fc["probability_neutral"], fc["probability_bullish"]),
                expected_direction=fc["expected_direction"],
            )
        )

    # The scorer's own validator owns the full-precision probability policy. The predictions
    # are their own cohort here because only origin keys are compared, not realized classes.
    try:
        validated = _validate_method_predictions(ready_predictions, ready_predictions, "heuristic")
    except InputValidationError as exc:
        raise ValueError(f"Replay probabilities rejected: {exc}") from exc

    return {
        pred.origin_index: HeuristicPrediction(
            origin_index=pred.origin_index,
            origin_date=pred.origin_date,
            probabilities=probabilities,
            expected_direction=pred.expected_direction,
        )
        for pred, probabilities in zip(ready_predictions, validated)
    }


def _write_exclusive(path: Path, data: bytes) -> None:
    """Creates a new evidence file; an existing file is never replaced."""
    with open(path, "xb") as f:
        f.write(data)


def _publish_completion_manifest(path: Path, data: bytes) -> None:
    """
    Creates run-manifest.json exclusively and leaves no partial file behind a caught failure.

    A file that already exists is never opened for writing or removed. If writing or closing
    fails after this call created the file, that file is removed and the primary error is
    raised; a removal that also fails is disclosed on the error as manifest_cleanup_error.
    A crash or a concurrent writer is outside what this can guarantee.
    """
    handle = open(path, "xb")
    error: Optional[Exception] = None
    try:
        handle.write(data)
    except Exception as exc:
        error = exc
    try:
        handle.close()
    except Exception as exc:
        if error is None:
            error = exc
    if error is None:
        return
    try:
        os.unlink(path)
    except Exception as cleanup_err:
        setattr(error, "manifest_cleanup_error", str(cleanup_err))
    raise error


def _replay_attempt_files(work_dir: Path, ordinal: int) -> Dict[str, Path]:
    suffix = "" if ordinal == 1 else f"-{ordinal:03d}"
    return {
        "request": work_dir / f"replay-request{suffix}.json",
        "response": work_dir / f"replay-response{suffix}.json",
        "stderr": work_dir / f"replay-stderr{suffix}.log",
        "receipt": work_dir / f"replay-invocation{suffix}.json",
    }


def _claim_attempt(
    make_files: Callable[[int], Dict[str, Path]],
    request_bytes: bytes,
) -> Tuple[int, Dict[str, Path]]:
    """Claims the next attempt by exclusively creating its request file, so ordinals cannot collide."""
    ordinal = 1
    while True:
        files = make_files(ordinal)
        try:
            _write_exclusive(files["request"], request_bytes)
            return ordinal, files
        except FileExistsError:
            ordinal += 1


def _terminate_child(process: Any) -> Tuple[bytes, bytes, bool, Optional[str]]:
    """Kills a started child and waits within a bound; returns (stdout, stderr, drained, error)."""
    errors: List[str] = []
    try:
        process.kill()
    except Exception as exc:
        errors.append(f"kill failed: {exc}")
    try:
        out, err = process.communicate(timeout=CHILD_CLEANUP_WAIT_SECONDS)
        return out or b"", err or b"", True, "; ".join(errors) or None
    except Exception as exc:
        errors.append(f"post-kill capture failed: {exc}")
    try:
        process.wait(timeout=CHILD_CLEANUP_WAIT_SECONDS)
    except Exception as exc:
        errors.append(f"post-kill wait failed: {exc}")
    return b"", b"", False, "; ".join(errors)


def _replay_child_environment() -> Dict[str, str]:
    """
    The exact environment the pinned Node child receives: the Windows system root and temporary
    directories, or TMPDIR on POSIX, each only when present. Nothing else is inherited, so
    runtime-affecting values such as NODE_OPTIONS never reach the child. os.environ is unchanged.
    """
    names = ("SYSTEMROOT", "TEMP", "TMP") if os.name == "nt" else ("TMPDIR",)
    return {name: os.environ[name] for name in names if name in os.environ}


def run_replay_adapter(
    features: FeatureSeries,
    *,
    node_executable: str,
    replay_script: str,
    workspace_root: str,
    work_dir: Path,
    timeout_seconds: int,
    trusted_model: Mapping[str, Any],
    trusted_build_manifest: Mapping[str, Any],
) -> Tuple[Dict[int, HeuristicPrediction], Dict[str, Any]]:
    """
    Serializes complete FeatureSeries, invokes pinned Node replay, and validates untrusted response.

    All replay evidence stays under work_dir, the root the caller owns. The child gets only the
    explicit environment the receipt records, so an inherited value grants no write authority.

    Returns:
      (dict mapping origin_index -> HeuristicPrediction, verified replay evidence dict)
    """
    _validate_timeout(timeout_seconds)
    for name, value in (("node_executable", node_executable), ("replay_script", replay_script), ("workspace_root", workspace_root)):
        _require_absolute_path(value, name)

    work_dir = Path(work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)

    request_bytes = serialize_replay_input(features)
    request_byte_count = len(request_bytes)
    request_sha256 = _sha256_upper(request_bytes)

    # Exclusive per-attempt claims: a prior or partial attempt is never overwritten
    try:
        work_attempt_idx, work_files = _claim_attempt(lambda n: _replay_attempt_files(work_dir, n), request_bytes)
    except Exception as save_err:
        raise RuntimeError(f"Failed to record replay evidence: {save_err}") from save_err

    request_file = work_files["request"]
    response_file = work_files["response"]
    stderr_file = work_files["stderr"]
    receipt_file = work_files["receipt"]

    node_cmd = [
        node_executable,
        replay_script,
        str(request_file),
    ]

    # The exact mapping supplied to the child, recorded unchanged in every receipt
    child_env = _replay_child_environment()
    declared_env = dict(child_env)

    def _receipt(**fields: Any) -> Dict[str, Any]:
        doc = {
            "attempt": work_attempt_idx,
            "exe": node_executable,
            "argv": node_cmd,
            "cwd": workspace_root,
            "shell": False,
            "start_utc": start_utc,
            "timeout_seconds": timeout_seconds,
            "request": {
                "path": str(request_file),
                "bytes": request_byte_count,
                "sha256": request_sha256,
            },
            "declared_environment": declared_env,
        }
        doc.update(fields)
        return doc

    def _write_receipt(doc: Dict[str, Any]) -> None:
        _write_exclusive(receipt_file, serialize_strict_json(doc))

    start_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
    t0 = time.monotonic()

    try:
        p = subprocess.Popen(
            node_cmd,
            cwd=workspace_root,
            env=child_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )
    except Exception as exc:
        receipt_doc = _receipt(
            end_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            duration_seconds=time.monotonic() - t0,
            timed_out=False,
            immediate_child_exit=None,
            launch_state="failed",
            launch_error=str(exc),
            capture_state="not_started",
            capture_error=None,
            stdout=None,
            stderr=None,
        )
        try:
            _write_receipt(receipt_doc)
        except Exception as save_err:
            raise RuntimeError(f"Failed to launch replay child process: {exc}; receipt write also failed: {save_err}") from exc
        raise RuntimeError(f"Failed to launch replay child process: {exc}") from exc

    timed_out = False
    capture_state = "complete"
    capture_error: Optional[str] = None
    capture_exception: Optional[Exception] = None
    raw_stdout = b""
    raw_stderr = b""

    try:
        raw_stdout, raw_stderr = p.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        raw_stdout, raw_stderr, drained, capture_error = _terminate_child(p)
        capture_state = "drained_after_kill" if drained else "incomplete"
        if not drained:
            raw_stdout = exc.stdout or b""
            raw_stderr = exc.stderr or b""
    except Exception as exc:
        capture_exception = exc
        capture_state = "error"
        raw_stdout, raw_stderr, _, cleanup_error = _terminate_child(p)
        capture_error = str(exc) if cleanup_error is None else f"{exc}; {cleanup_error}"

    end_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
    duration = time.monotonic() - t0

    receipt_doc = _receipt(
        end_utc=end_utc,
        duration_seconds=duration,
        timed_out=timed_out,
        immediate_child_exit=p.returncode,
        launch_state="started",
        launch_error=None,
        capture_state=capture_state,
        capture_error=capture_error,
        stdout={
            "path": str(response_file),
            "bytes": len(raw_stdout),
            "sha256": _sha256_upper(raw_stdout),
        },
        stderr={
            "path": str(stderr_file),
            "bytes": len(raw_stderr),
            "sha256": _sha256_upper(raw_stderr),
        },
    )

    try:
        _write_exclusive(response_file, raw_stdout)
        _write_exclusive(stderr_file, raw_stderr)
        _write_receipt(receipt_doc)
    except Exception as save_err:
        if capture_exception is not None:
            raise RuntimeError(f"Replay capture failed: {capture_exception}; evidence write also failed: {save_err}") from capture_exception
        raise RuntimeError(f"Failed to record replay evidence: {save_err}") from save_err

    if capture_exception is not None:
        raise RuntimeError(f"Replay capture failed: {capture_exception}") from capture_exception

    if timed_out:
        raise RuntimeError(f"Replay process timed out after {timeout_seconds}s")

    if p.returncode != 0:
        err_msg = raw_stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"Replay process exited with code {p.returncode}: {err_msg}")

    if request_file.read_bytes() != request_bytes:
        raise ValueError("Replay request file changed during the attempt")

    # Parse untrusted stdout
    try:
        stdout_text = raw_stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"Replay stdout is not valid UTF-8: {exc}") from exc

    response_doc = parse_strict_json(stdout_text)
    if not isinstance(response_doc, dict):
        raise ValueError("Replay response root must be a JSON object")

    heuristic_predictions = validate_replay_response(
        response_doc,
        request_bytes=request_bytes,
        features=features,
        trusted_model=trusted_model,
        trusted_build_manifest=trusted_build_manifest,
    )

    evidence = {
        "request": {"raw_byte_count": request_byte_count, "sha256": request_sha256},
        "response": {"raw_byte_count": len(raw_stdout), "sha256": _sha256_upper(raw_stdout)},
        "immediate_child_exit": p.returncode,
        "attempt": work_attempt_idx,
    }
    return heuristic_predictions, evidence


def _execute_serial_comparators(
    features: FeatureSeries,
    outcomes: OutcomeSeries,
    *,
    development_start: datetime.date,
    test_start: datetime.date,
    warning_collector: Optional[List[Dict[str, Any]]] = None,
    expected_dependency_versions: Optional[Mapping[str, str]] = None,
) -> Tuple[FrequencyResult, Any, List[Dict[str, Any]]]:
    """
    Executes frequency comparator and lazy-imported logistic comparator serially
    within a caller-owned, restored single-thread threadpool and warnings context.

    Filters policy:
      simplefilter('always') FIRST.
      filterwarnings('error', category=FutureWarning) SECOND.
      Both with prepend semantics.
    """
    # Lazy imports for scientific path
    try:
        import numpy
        import scipy
        import sklearn
        import threadpoolctl
        from research.prediction_eval.logistic import (
            build_logistic_predictions,
            LogisticResult,
        )
    except ImportError as exc:
        raise RuntimeError(f"Failed to import scientific dependencies (logistic/threadpoolctl): {exc}") from exc

    if expected_dependency_versions is not None:
        actual_versions = {
            "numpy": numpy.__version__,
            "scikit-learn": sklearn.__version__,
            "scipy": scipy.__version__,
            "threadpoolctl": threadpoolctl.__version__,
        }
        if actual_versions != dict(expected_dependency_versions):
            raise RuntimeError(f"Scientific dependency versions differ from the configuration: {actual_versions}")

    captured_warnings_list: List[Dict[str, Any]] = []
    synced_count = 0

    def _sync_warnings(records) -> None:
        nonlocal synced_count
        while synced_count < len(records):
            w = records[synced_count]
            item = {
                "category": w.category.__name__,
                "message": str(w.message),
                "filename": w.filename,
                "lineno": w.lineno,
            }
            captured_warnings_list.append(item)
            if warning_collector is not None:
                warning_collector.append(item)
            synced_count += 1

    try:
        # Caller-owned restored single-thread threadpool context
        with threadpoolctl.threadpool_limits(limits=1):
            with warnings.catch_warnings(record=True) as warn_records:
                # 1. simplefilter('always') first
                warnings.simplefilter("always")
                # 2. filterwarnings('error', category=FutureWarning) second (prepends)
                warnings.filterwarnings("error", category=FutureWarning)

                try:
                    freq_result = build_frequency_predictions(
                        features,
                        outcomes,
                        development_start=development_start,
                        test_start=test_start,
                    )
                finally:
                    _sync_warnings(warn_records)

                try:
                    log_result = build_logistic_predictions(
                        features,
                        outcomes,
                        development_start=development_start,
                        test_start=test_start,
                    )
                finally:
                    _sync_warnings(warn_records)

    except Exception as exc:
        setattr(exc, "captured_warnings", list(captured_warnings_list))
        raise

    return freq_result, log_result, captured_warnings_list


def _reconcile_split_plans(
    reference_plan: SplitPlan,
    freq_plan: SplitPlan,
    log_plan: SplitPlan,
) -> None:
    """Verifies that both comparators produced identical SplitPlans to the canonical reference."""
    for label, plan in (("frequency", freq_plan), ("logistic", log_plan)):
        if plan.development_start != reference_plan.development_start or plan.test_start != reference_plan.test_start:
            raise InputValidationError(f"{label} plan boundary dates mismatch", field="split_plan", reason="plan mismatch")
        if plan.development_start_index != reference_plan.development_start_index:
            raise InputValidationError(f"{label} plan development_start_index mismatch", field="split_plan", reason="plan mismatch")
        if plan.test_start_index != reference_plan.test_start_index:
            raise InputValidationError(f"{label} plan test_start_index mismatch", field="split_plan", reason="plan mismatch")
        if plan.train_indices != reference_plan.train_indices:
            raise InputValidationError(f"{label} plan train_indices mismatch", field="split_plan", reason="plan mismatch")
        if plan.development_indices != reference_plan.development_indices:
            raise InputValidationError(f"{label} plan development_indices mismatch", field="split_plan", reason="plan mismatch")
        if plan.refit_indices != reference_plan.refit_indices:
            raise InputValidationError(f"{label} plan refit_indices mismatch", field="split_plan", reason="plan mismatch")
        if plan.test_indices != reference_plan.test_indices:
            raise InputValidationError(f"{label} plan test_indices mismatch", field="split_plan", reason="plan mismatch")
        if plan.decisions != reference_plan.decisions:
            raise InputValidationError(f"{label} plan decisions mismatch", field="split_plan", reason="plan mismatch")


def _reconcile_block(
    label: str,
    block: Any,
    *,
    partition: str,
    fitting_indices: Tuple[int, ...],
    target_indices: Tuple[int, ...],
    cutoff_index: int,
    cutoff_date: datetime.date,
    reference_plan: SplitPlan,
) -> None:
    """Checks one returned block's keys and pools against the reference, available or not."""

    def _reject(detail: str) -> None:
        raise InputValidationError(f"{label} {partition} block {detail}", field="comparator_block", reason="block mismatch")

    if block.partition != partition:
        _reject("partition mismatch")
    if block.requested_indices != target_indices:
        _reject("requested_indices mismatch")

    fit = block.fit
    returned_pool = getattr(block, "fitting_indices", None)
    if returned_pool is None:
        returned_pool = fit.fitting_indices if fit is not None else ()
        if fit is None and len(fitting_indices) != 0:
            _reject("is unavailable although its fitting pool is non-empty")
    if returned_pool != fitting_indices:
        _reject("fitting pool mismatch")

    block_cutoff = getattr(block, "cutoff_index", None)
    block_date = getattr(block, "cutoff_date", None)
    if block_cutoff is None and fit is not None:
        block_cutoff, block_date = fit.cutoff_index, fit.cutoff_date
    if block_cutoff is not None and (block_cutoff != cutoff_index or block_date != cutoff_date):
        _reject("cutoff mismatch")

    if fit is None:
        if len(block.predictions) != 0:
            _reject("is unavailable but carries predictions")
        return
    expected_keys = [(i, reference_plan.decisions[i].origin_date) for i in target_indices]
    if [(p.origin_index, p.origin_date) for p in block.predictions] != expected_keys:
        _reject("prediction keys mismatch")


def _reconcile_comparator_blocks(reference_plan: SplitPlan, freq_res: Any, log_res: Any) -> None:
    """Compares every returned plan and block with the reference, including unavailable blocks."""
    _reconcile_split_plans(reference_plan, freq_res.plan, log_res.plan)
    for label, result in (("frequency", freq_res), ("logistic", log_res)):
        _reconcile_block(
            label,
            result.development_block,
            partition=PARTITION_DEVELOPMENT,
            fitting_indices=reference_plan.train_indices,
            target_indices=reference_plan.development_indices,
            cutoff_index=reference_plan.development_start_index,
            cutoff_date=reference_plan.development_start,
            reference_plan=reference_plan,
        )
        _reconcile_block(
            label,
            result.test_block,
            partition=PARTITION_TEST,
            fitting_indices=reference_plan.refit_indices,
            target_indices=reference_plan.test_indices,
            cutoff_index=reference_plan.test_start_index,
            cutoff_date=reference_plan.test_start,
            reference_plan=reference_plan,
        )


def _frequency_block_state(
    block: FrequencyBlock,
    *,
    fitting_indices: Tuple[int, ...],
    cutoff_index: int,
    cutoff_date: datetime.date,
) -> Dict[str, Any]:
    """Projects one returned frequency block, keeping its pool and cutoff when fit is None."""
    fit = None
    if block.fit is not None:
        fit = {
            "class_counts": list(block.fit.class_counts),
            "probabilities": list(block.fit.probabilities),
        }
    return {
        "method": FREQUENCY_METHOD_ID,
        "partition": block.partition,
        "fitting_indices": list(fitting_indices),
        "cutoff_index": cutoff_index,
        "cutoff_date": cutoff_date.isoformat(),
        "requested_indices": list(block.requested_indices),
        "prediction_count": len(block.predictions),
        "unavailable_reason": block.unavailable_reason,
        "fit": fit,
    }


def _logistic_block_state(block: Any, *, method: str) -> Dict[str, Any]:
    """Projects one returned logistic block with all of its fitted or unavailable metadata."""
    fit = None
    if block.fit is not None:
        fit = {
            "numeric_means": list(block.fit.numeric_means),
            "numeric_variances": list(block.fit.numeric_variances),
            "numeric_scales": list(block.fit.numeric_scales),
            "coefficients": [list(row) for row in block.fit.coefficients],
            "intercepts": list(block.fit.intercepts),
            "n_iter": block.fit.n_iter,
            "classes": list(block.fit.classes),
            "feature_names": list(block.fit.feature_names),
        }
    return {
        "method": method,
        "partition": block.partition,
        "fitting_indices": list(block.fitting_indices),
        "cutoff_index": block.cutoff_index,
        "cutoff_date": block.cutoff_date.isoformat(),
        "class_counts": list(block.class_counts),
        "regime_counts": list(block.regime_counts),
        "requested_indices": list(block.requested_indices),
        "prediction_count": len(block.predictions),
        "unavailable_reason": block.unavailable_reason,
        "failure_stage": block.failure_stage,
        "fit": fit,
    }


def _partition_counts(
    partition_name: str,
    target_indices: Tuple[int, ...],
    reference_plan: SplitPlan,
    requested_count: int,
    model_available_counts: Dict[str, int],
) -> PartitionCounts:
    """
    Derives coverage counts from canonical planner decisions; no second eligibility rule.

    Reason tallies can overlap on one origin, so only raw minus eligible is the unique count.
    """
    decisions = [d for d in reference_plan.decisions if d.partition == partition_name]
    reason_counts = Counter(reason for d in decisions for reason in d.exclusion_reasons)
    return PartitionCounts(
        raw_partition_count=len(decisions),
        eligible_count=len(target_indices),
        excluded_count=len(decisions) - len(target_indices),
        requested_count=requested_count,
        exclusion_reason_counts=dict(sorted(reason_counts.items())),
        model_available_counts=model_available_counts,
    )


def _method_record(
    probabilities: Optional[Tuple[float, float, float]],
    row: Optional[RowScore],
) -> MethodOriginRecord:
    if probabilities is None:
        return MethodOriginRecord(forecast_state=FORECAST_STATE_UNAVAILABLE, probabilities=None)
    if row is None:
        return MethodOriginRecord(forecast_state=FORECAST_STATE_AVAILABLE, probabilities=probabilities)
    return MethodOriginRecord(
        forecast_state=FORECAST_STATE_AVAILABLE,
        probabilities=probabilities,
        predicted_class=row.predicted_class,
        brier=row.brier,
        log_loss=row.log_loss,
        log_loss_state=row.log_loss_state,
    )


def _evaluate_partition(
    partition_name: str,
    target_indices: Tuple[int, ...],
    reference_plan: SplitPlan,
    outcomes: OutcomeSeries,
    heuristic_map: Dict[int, HeuristicPrediction],
    freq_block: FrequencyBlock,
    log_block: Any,
    *,
    logistic_method: str = "fixed-logistic-v1",
) -> PartitionResult:
    """
    Evaluates a single chronological partition (development or test).
    Inspects upstream method availability before scoring; skips 3-way score if unavailable.

    Usable forecasts are preserved independently of scoring. An unavailable fit wins before
    the empty status, and no single-model score or common subset is ever substituted.
    """
    is_development = partition_name == PARTITION_DEVELOPMENT
    cutoff_index = reference_plan.development_start_index if is_development else reference_plan.test_start_index
    cutoff_date = reference_plan.development_start if is_development else reference_plan.test_start
    fitting_indices = reference_plan.train_indices if is_development else reference_plan.refit_indices

    # The adapter proved every ready origin has a forecast, so a missing target is a defect
    missing_heuristic = [tidx for tidx in target_indices if tidx not in heuristic_map]
    if missing_heuristic:
        raise ValueError(f"Validated replay has no forecast for target origins {missing_heuristic[:5]}")

    # Check method availability
    unavailable_reasons: List[str] = []

    # Frequency availability
    f_available = freq_block.fit is not None and freq_block.unavailable_reason is None
    f_reason = freq_block.unavailable_reason
    if not f_available:
        unavailable_reasons.append(f"frequency: {f_reason}")

    # Logistic availability
    l_available = log_block.fit is not None and log_block.unavailable_reason is None
    l_reason = log_block.unavailable_reason
    if not l_available:
        unavailable_reasons.append(f"logistic: {l_reason}")

    # Build cohort
    cohort: List[EvaluationOrigin] = []
    for tidx in target_indices:
        o_date = reference_plan.decisions[tidx].origin_date
        o_class = outcomes.outcomes[tidx].outcome_class
        cohort.append(EvaluationOrigin(origin_index=tidx, origin_date=o_date, actual_class=o_class))

    h_preds = [heuristic_map[tidx] for tidx in target_indices]
    f_preds = list(freq_block.predictions)
    l_preds = list(log_block.predictions)

    counts = _partition_counts(
        partition_name,
        target_indices,
        reference_plan,
        len(freq_block.requested_indices),
        {
            "heuristic": len(h_preds),
            "frequency": len(f_preds) if f_available else 0,
            "logistic": len(l_preds) if l_available else 0,
        },
    )

    comparison_status: str
    comparison_metrics: Optional[ComparisonMetrics] = None

    if not (f_available and l_available):
        comparison_status = STATUS_COMPARISON_UNAVAILABLE
    elif len(cohort) == 0:
        comparison_status = STATUS_EMPTY
        comparison_metrics = score_comparison([], heuristic=[], frequency=[], logistic=[])
    else:
        comparison_status = STATUS_SCORED
        comparison_metrics = score_comparison(cohort, heuristic=h_preds, frequency=f_preds, logistic=l_preds)

    scored = comparison_status == STATUS_SCORED
    per_origin_records: List[PerOriginRecord] = []
    for idx, orig in enumerate(cohort):
        outcome = outcomes.outcomes[orig.origin_index]
        per_origin_records.append(
            PerOriginRecord(
                origin_index=orig.origin_index,
                origin_date=orig.origin_date,
                origin_close=str(outcome.origin_close),
                maturity_index=outcome.maturity_index,
                maturity_date=outcome.maturity_date,
                maturity_close=str(outcome.maturity_close),
                actual_class=orig.actual_class,
                score_state=SCORE_STATE_SCORED if scored else SCORE_STATE_UNSCORED,
                heuristic_expected_direction=h_preds[idx].expected_direction,
                heuristic=_method_record(
                    h_preds[idx].probabilities,
                    comparison_metrics.heuristic.row_scores[idx] if scored else None,
                ),
                frequency=_method_record(
                    f_preds[idx].probabilities if f_available else None,
                    comparison_metrics.frequency.row_scores[idx] if scored else None,
                ),
                logistic=_method_record(
                    l_preds[idx].probabilities if l_available else None,
                    comparison_metrics.logistic.row_scores[idx] if scored else None,
                ),
            )
        )

    return PartitionResult(
        partition=partition_name,
        cutoff_index=cutoff_index,
        cutoff_date=cutoff_date,
        requested_indices=target_indices,
        requested_dates=tuple(reference_plan.decisions[tidx].origin_date for tidx in target_indices),
        counts=counts,
        heuristic_available=True,
        frequency_available=f_available,
        frequency_unavailable_reason=f_reason,
        frequency_block=_frequency_block_state(
            freq_block,
            fitting_indices=fitting_indices,
            cutoff_index=cutoff_index,
            cutoff_date=cutoff_date,
        ),
        logistic_available=l_available,
        logistic_unavailable_reason=l_reason,
        logistic_failure_stage=log_block.failure_stage,
        logistic_block=_logistic_block_state(log_block, method=logistic_method),
        comparison_status=comparison_status,
        comparison_unavailable_reasons=tuple(unavailable_reasons),
        comparison_metrics=comparison_metrics,
        per_origin_records=tuple(per_origin_records),
    )


def _is_reparse_or_link(path: Union[str, Path]) -> bool:
    """True for a symlink, junction or other reparse point, including a dangling one."""
    try:
        info = os.lstat(path)
    except (FileNotFoundError, NotADirectoryError):
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(getattr(info, "st_file_attributes", 0) & reparse_flag)


def _reject_reparse_traversal(path: Path, label: str) -> None:
    """
    Checks every existing lexical component of an absolute path, without resolving it.

    A regular leaf below a linked ancestor would otherwise pass: resolving both paths through
    the same link keeps them related. This is a static check, not a race-free guarantee.
    """
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        if _is_reparse_or_link(current):
            raise ValueError(f"{label} is reached through a reparse point at {current}")


def _resolve_contained_output(
    output_dir: Union[str, Path],
    allowed_parent: Optional[Union[str, Path]],
    protected_paths: Sequence[str],
    workspace_root: str,
) -> Path:
    """
    Validates a NEW run root before anything is written, and returns its resolved path.

    The root must be a direct child of the explicit allowed parent, reached without a reparse
    point at any existing lexical component, not an alias of a bound input, and outside source,
    served-asset (public, dist), model and build roots of the passed workspace root.
    """
    if allowed_parent is None or not str(allowed_parent):
        raise ValueError("An explicit allowed output parent is required")

    parent_path = Path(allowed_parent)
    output_path = Path(output_dir)
    if not parent_path.is_absolute() or not output_path.is_absolute():
        raise ValueError(f"Output and allowed parent must be absolute: {output_path}, {parent_path}")
    _reject_reparse_traversal(parent_path, "Allowed output parent")
    _reject_reparse_traversal(output_path, "Output path")
    # Normalization would collapse allowed/../allowed/run into a direct child, so refuse it first
    if ".." in output_path.parts:
        raise ValueError(f"Output path must not contain a parent traversal: {output_path}")
    if not parent_path.is_dir():
        raise ValueError(f"Allowed output parent is not a directory: {parent_path}")

    resolved_parent = parent_path.resolve()
    resolved_output = output_path.resolve()

    # Check for path traversal escaping allowed parent
    try:
        rel = resolved_output.relative_to(resolved_parent)
    except ValueError as exc:
        raise ValueError(f"Output path escapes allowed parent directory: {resolved_output}") from exc
    if len(rel.parts) != 1:
        raise ValueError(f"Output path {resolved_output} must be a direct child of {resolved_parent}")

    # Resolution can land inside the parent after following a link, so also compare lexically
    if _norm_path(os.path.abspath(output_path)) != _norm_path(os.path.join(os.path.abspath(parent_path), rel.parts[0])):
        raise ValueError(f"Output path reaches the allowed parent through a reparse point: {output_path}")

    if not is_valid_identifier(resolved_output.name):
        raise ValueError(f"Output directory name is not a portable run identifier: {resolved_output.name}")

    if os.path.lexists(output_path):
        raise ValueError(f"Output directory already exists: {resolved_output}")

    output_key = _norm_path(resolved_output)
    for protected in protected_paths:
        if _norm_path(Path(protected).resolve()) == output_key:
            raise ValueError(f"Output path aliases a bound input: {protected}")

    root = Path(workspace_root).resolve()
    for forbidden in (
        root / "research",
        root / "src",
        root / "public",
        root / "dist",
        root / "build" / "prediction-eval" / "candidate",
        root / "build" / "prediction-eval" / "venv-logistic",
    ):
        forbidden_key = _norm_path(forbidden)
        if output_key == forbidden_key or output_key.startswith(forbidden_key + os.sep):
            raise ValueError(f"Output path is inside a protected root: {forbidden}")

    return resolved_output


def _read_bound_file(bound: BoundFile, label: str) -> bytes:
    """Reads a bound file once and verifies its exact byte count and SHA-256."""
    try:
        data = Path(bound.path).read_bytes()
    except OSError as exc:
        raise InputValidationError(f"Cannot read bound file {label}: {exc}", field=label, reason=str(exc)) from exc
    if len(data) != bound.raw_byte_count or _sha256_upper(data) != bound.sha256:
        raise InputValidationError(
            f"Bound file {label} differs from its configured identity",
            field=label,
            reason=f"expected {bound.raw_byte_count} bytes {bound.sha256}",
        )
    return data


def _require_canonical_path(bound: BoundFile, workspace_root: Path, rel_path: str, label: str) -> None:
    """replay.cjs resolves its model and build itself, so any other configured path is rejected."""
    if _norm_path(bound.path) != _norm_path(workspace_root.joinpath(*rel_path.split("/"))):
        raise InputValidationError(
            f"{label} must be the canonical {rel_path}; alternative paths are unsupported",
            field=label,
            reason="Non-canonical execution path",
        )


def _require_package_workspace(workspace_root: str) -> Path:
    """The configured workspace must be this package's actual root before any path in it is trusted."""
    workspace = Path(workspace_root)
    package_root = Path(__file__).resolve().parents[2]
    if _norm_path(workspace.resolve()) != _norm_path(package_root):
        raise InputValidationError(
            f"workspace_root {workspace} is not this package's root {package_root}",
            field="workspace_root",
            reason="Workspace mismatch",
        )
    return workspace


def _verify_run_prerequisites(config: StudyConfiguration) -> Dict[str, Any]:
    """
    Verifies source, tool, build, model and runtime identities before any input is read.

    Returns the verified identities, built from measured bytes rather than configured labels.
    """
    if config.config_path is None or config.config_bytes is None:
        raise InputValidationError("Configuration must be loaded from its file", field="config", reason="missing original bytes")
    if Path(config.config_path).read_bytes() != config.config_bytes:
        raise InputValidationError("Configuration file changed after load", field="config", reason="config drift")

    workspace_root = _require_package_workspace(config.workspace_root)

    _require_canonical_path(config.replay_script, workspace_root, EXPECTED_REPLAY_SCRIPT_PATH, "tools.replay_script")
    _require_canonical_path(config.models, workspace_root, EXPECTED_MODELS_PATH, "tools.models")
    _require_canonical_path(config.candidate_build_manifest, workspace_root, EXPECTED_BUILD_MANIFEST_PATH, "tools.candidate_build_manifest")

    source_identities: Dict[str, Dict[str, Any]] = {}
    for rel_path, expected in config.source_modules.items():
        bound = BoundFile(str(workspace_root.joinpath(*rel_path.split("/"))), expected["raw_byte_count"], expected["sha256"])
        _read_bound_file(bound, f"source_modules[{rel_path}]")
        source_identities[rel_path] = {"raw_byte_count": bound.raw_byte_count, "sha256": bound.sha256}

    _read_bound_file(config.node_executable, "tools.node_executable")
    _read_bound_file(config.python_executable, "tools.python_executable")
    if _norm_path(os.path.abspath(sys.executable)) != _norm_path(config.python_executable.path):
        raise InputValidationError("tools.python_executable is not this interpreter", field="tools.python_executable", reason="Runtime mismatch")
    if platform.python_version() != config.python_version or platform.python_implementation() != config.python_implementation:
        raise InputValidationError(
            f"Runtime {platform.python_implementation()} {platform.python_version()} differs from the configuration",
            field="runtime",
            reason="Runtime mismatch",
        )

    replay_bytes = _read_bound_file(config.replay_script, "tools.replay_script")
    model_bytes = _read_bound_file(config.models, "tools.models")
    build_bytes = _read_bound_file(config.candidate_build_manifest, "tools.candidate_build_manifest")

    model_doc = parse_strict_json_bytes(model_bytes)
    model_20d = model_doc.get("20D") if type(model_doc) is dict else None
    platt = model_20d.get("platt_params") if type(model_20d) is dict else None
    if type(platt) is not list or tuple(platt) != EXPECTED_20D_PLATT_PARAMS:
        raise InputValidationError(f"Model 20D platt_params mismatch: {platt!r}", field="tools.models", reason="Platt mismatch")

    build_doc = parse_strict_json_bytes(build_bytes)
    if type(build_doc) is not dict or build_doc.get("schema_version") != EXPECTED_BUILD_SCHEMA_VERSION:
        raise InputValidationError("Unsupported candidate build manifest", field="tools.candidate_build_manifest", reason="Build schema")
    toolchain = build_doc.get("toolchain")
    node_identity = toolchain.get("node_executable") if type(toolchain) is dict else None
    if (
        build_doc.get("mode") != EXPECTED_BUILD_MODE
        or type(build_doc.get("compiler_exit")) is not int
        or build_doc.get("compiler_exit") != 0
        or type(node_identity) is not dict
        or str(node_identity.get("sha256", "")).upper() != config.node_executable.sha256
        or node_identity.get("bytes") != config.node_executable.raw_byte_count
    ):
        raise InputValidationError(
            "Candidate build manifest does not bind the configured Node executable",
            field="tools.candidate_build_manifest",
            reason="Build identity mismatch",
        )

    return {
        "source_identities": source_identities,
        "runtime_identities": {
            "python_version": config.python_version,
            "python_implementation": config.python_implementation,
            "python_executable": {
                "raw_byte_count": config.python_executable.raw_byte_count,
                "sha256": config.python_executable.sha256,
            },
            "platform": sys.platform,
            "node_version": toolchain.get("node_version"),
            "node_executable": {
                "raw_byte_count": config.node_executable.raw_byte_count,
                "sha256": config.node_executable.sha256,
            },
            "dependency_versions": dict(config.dependency_versions),
        },
        "model_identity": {
            "path": EXPECTED_MODELS_PATH,
            "raw_byte_count": len(model_bytes),
            "sha256": _sha256_upper(model_bytes),
            "platt_params": list(EXPECTED_20D_PLATT_PARAMS),
        },
        "build_identity": {
            "raw_byte_count": len(build_bytes),
            "sha256": _sha256_upper(build_bytes),
            "mode": build_doc["mode"],
            "calculation_id": build_doc.get("calculation_id"),
            "compiler_exit": build_doc["compiler_exit"],
        },
        "replay_script_identity": {"raw_byte_count": len(replay_bytes), "sha256": _sha256_upper(replay_bytes)},
        "trusted_build_manifest": build_doc,
    }


def _load_admitted_inputs(
    config: StudyConfiguration,
    retain_warnings: Callable[[LoadedSeries], None],
) -> Tuple[LoadedSeries, LoadedSeries, AlignedPair, bytes]:
    """
    Loads the inputs and proves the bytes the loader hashed are the configured bytes.

    Each series hands over its returned warnings at once, so a later loader or alignment
    failure cannot lose them. A loader that raises returned nothing and contributes nothing.
    """
    calendar_raw = _read_bound_file(config.calendar, "inputs.calendar")
    is_historical = config.data_kind == DATA_KIND_HISTORICAL

    nifty_specs = config.nifty_input.file_specs()
    nifty_series = load_series(SERIES_ID_NIFTY, nifty_specs if is_historical else nifty_specs[0])
    retain_warnings(nifty_series)

    vix_specs = config.vix_input.file_specs()
    vix_series = load_series(SERIES_ID_VIX, vix_specs if is_historical else vix_specs[0])
    retain_warnings(vix_series)

    for label, series, binding in (
        ("inputs.nifty", nifty_series, config.nifty_input),
        ("inputs.vix", vix_series, config.vix_input),
    ):
        if len(series.provenance) != len(binding.files):
            raise InputValidationError(
                f"Provenance count mismatch for {label}: expected {len(binding.files)}, got {len(series.provenance)}",
                field=label,
                reason="provenance count mismatch",
            )
        for idx, (prov, f_bind) in enumerate(zip(series.provenance, binding.files)):
            item_label = f"{label}.files[{idx}]" if is_historical else label
            if _norm_path(prov.file_path) != _norm_path(f_bind.bound.path):
                raise InputValidationError(
                    f"Bound file {item_label} path mismatch: expected {f_bind.bound.path}, got {prov.file_path}",
                    field=item_label,
                    reason="path mismatch",
                )
            if prov.raw_byte_count != f_bind.bound.raw_byte_count or prov.sha256.upper() != f_bind.bound.sha256:
                raise InputValidationError(
                    f"Bound file {item_label} differs from its configured identity",
                    field=item_label,
                    reason=f"expected {f_bind.bound.raw_byte_count} bytes {f_bind.bound.sha256}",
                )

    return nifty_series, vix_series, _align_with_calendar(nifty_series, vix_series, calendar_raw), calendar_raw


def _verify_frozen_admission(
    config: StudyConfiguration,
    nifty_series: LoadedSeries,
    vix_series: LoadedSeries,
    aligned: AlignedPair,
    calendar_raw: bytes,
) -> Tuple[Dict[str, Any], bytes]:
    """
    Verifies the separately supplied admission record against the loaded inputs.

    The comparison is input-only and precedes outcomes and features, so nothing observed in
    results can re-admit a date or gap.
    """
    admission_raw = _read_bound_file(config.admission, "admission")
    frozen = parse_strict_json_bytes(admission_raw)
    # Types first: the equality below is by value, and bound bytes prove identity, not type
    try:
        validate_admission_document(frozen, "admission")
    except ValueError as exc:
        raise InputValidationError(f"Frozen admission record is malformed: {exc}", field="admission", reason="admission schema") from exc
    expected = _build_admission_record(
        nifty_series,
        vix_series,
        aligned,
        calendar_raw,
        development_start=config.development_start,
        test_start=config.test_start,
        is_historical=(config.data_kind == DATA_KIND_HISTORICAL),
    )
    if frozen != expected:
        differing = sorted(k for k in expected if frozen[k] != expected[k])
        raise InputValidationError(
            f"Frozen admission record differs from the admitted inputs in {differing}",
            field="admission",
            reason="admission mismatch",
        )
    return frozen, admission_raw


def _series_identity(series: LoadedSeries, binding: InputBinding) -> Dict[str, Any]:
    if binding.source_kind == SOURCE_KIND_HISTORICAL:
        files_list = []
        for prov, f_bind in zip(series.provenance, binding.files):
            files_list.append({
                "path": f_bind.bound.path,
                "raw_byte_count": prov.raw_byte_count,
                "sha256": prov.sha256.upper(),
                "record_count": prov.record_count,
                "observed_first_date": prov.observed_first_date.isoformat(),
                "observed_last_date": prov.observed_last_date.isoformat(),
                "source_url": f_bind.source_url,
                "requested_interval": [d.isoformat() for d in f_bind.requested_interval] if f_bind.requested_interval else None,
                "acquisition_time": f_bind.acquisition_time.isoformat() if f_bind.acquisition_time else None,
                "source_use_note": f_bind.source_use_note,
            })
        return {
            "units": binding.units,
            "source_kind": binding.source_kind,
            "files": files_list,
        }
    else:
        prov = series.provenance[0]
        f_bind = binding.files[0]
        return {
            "raw_byte_count": prov.raw_byte_count,
            "sha256": prov.sha256.upper(),
            "record_count": prov.record_count,
            "observed_first_date": series.records[0].date.isoformat(),
            "observed_last_date": series.records[-1].date.isoformat(),
            "units": binding.units,
            "source_kind": binding.source_kind,
            "source_url": f_bind.source_url,
            "requested_interval": None
            if f_bind.requested_interval is None
            else [f_bind.requested_interval[0].isoformat(), f_bind.requested_interval[1].isoformat()],
            "acquisition_time": None if f_bind.acquisition_time is None else f_bind.acquisition_time.isoformat(),
            "source_use_note": f_bind.source_use_note,
        }


def _input_warning_record(warning: InputWarning) -> Dict[str, Any]:
    """Projects one returned loader warning. Private: it can hold raw file text and paths."""
    return {
        "file_path": warning.file_path,
        "line": warning.line,
        "field": warning.field,
        "message": warning.message,
        "raw_value": warning.raw_value,
    }


class _RunLifecycle:
    """Tracks the current stage and retained warnings of one owned run root."""

    def __init__(self, run_root: Path) -> None:
        self.run_root = run_root
        self.stage = "initialized"
        self.warnings: List[Dict[str, Any]] = []
        self.input_warnings: List[Dict[str, Any]] = []

    def enter(self, stage: str) -> None:
        self.stage = stage

    def retain_input_warnings(self, series: LoadedSeries) -> None:
        """Keeps a returned series' warnings in order; repeats are separate diagnostics."""
        self.input_warnings.extend(_input_warning_record(warning) for warning in series.warnings)

    def _partial_artifacts(self) -> List[Dict[str, Any]]:
        entries = []
        for item in sorted(self.run_root.iterdir()):
            if item.is_file():
                data = item.read_bytes()
                entries.append({"path": item.name, "bytes": len(data), "sha256": _sha256_upper(data)})
        return entries

    def record_failure(self, exc: Exception) -> None:
        """
        Writes one explicit failure record without ever masking the primary error.

        If storage itself fails the record cannot exist, so the failure is disclosed on the
        exception for the caller instead of being claimed as saved.
        """
        retained = list(self.warnings)
        for item in getattr(exc, "captured_warnings", []):
            if item not in retained:
                retained.append(item)
        try:
            doc = {
                "schema_version": SCHEMA_VERSION_FAILURE,
                "run_id": self.run_root.name,
                "completed": False,
                "stage": self.stage,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "captured_warnings": retained,
                "input_warnings": list(self.input_warnings),
                "partial_artifacts": self._partial_artifacts(),
            }
            _write_exclusive(self.run_root / FAILURE_RECORD_NAME, serialize_strict_json(doc))
        except Exception as diag_err:
            setattr(exc, "failure_record_error", str(diag_err))


def run_study(
    config: StudyConfiguration,
    output_dir: Path,
    *,
    allowed_parent: Union[str, Path],
    approval: Optional[BoundFile] = None,
) -> StudyResult:
    """
    Executes the complete offline prediction study workflow:
      1. Checks the configured workspace is this package's root, then validates the exclusive
         new run root inside the explicit allowed parent.
      2. Verifies source, tool, build, model, runtime and configuration identities.
      3. Loads inputs on the Nifty master axis, retains each loader's returned warnings as it
         returns, and verifies their configured bytes.
      4. Validates the frozen admission record's native types, then its values, BEFORE outcomes
         or features exist.
      5. Computes outcomes, features and the canonical reference SplitPlan.
      6. Checks the frozen gap inventory against that plan BEFORE replay or comparators.
      7. Runs Node replay adapter for heuristic predictions.
      8. Executes frequency and logistic comparators serially within restored warning/thread context.
      9. Reconciles returned plans, pools, blocks and requested keys with the reference.
      10. Evaluates partitions and scores three-way comparison where available.
      11. Writes all private and candidate artifacts; writes run-manifest.json LAST.

    Before the root is owned, a failure reaches only the caller. After that, every failure
    leaves one stage-aware record and no completion manifest.
    """
    is_historical = config.data_kind == DATA_KIND_HISTORICAL

    if is_historical:
        if approval is None:
            raise InputValidationError(
                "Human approval BoundFile is required for historical study execution",
                field="approval",
                reason="approval is required in historical mode",
            )
    else:
        if approval is not None:
            raise InputValidationError(
                "Human approval must not be provided for synthetic study",
                field="approval",
                reason="approval not allowed in synthetic mode",
            )

    # Before any path below is trusted; a configuration without bytes is refused at prerequisites
    if config.config_bytes is not None:
        _require_configuration_from_its_bytes(config)

    if allowed_parent is None or _norm_path(allowed_parent) != _norm_path(config.allowed_output_parent):
        raise ValueError(f"allowed_parent must be the configured allowed_output_parent: {config.allowed_output_parent}")

    # The protected roots below come from this root, so a wrong one fails before any directory
    _require_package_workspace(config.workspace_root)

    protected = []
    for f in config.nifty_input.files:
        protected.append(f.bound.path)
    for f in config.vix_input.files:
        protected.append(f.bound.path)
    protected.append(config.calendar.path)
    protected.append(config.admission.path)
    if config.config_path is not None:
        protected.append(config.config_path)
    if approval is not None:
        protected.append(approval.path)

    # 1. Exclusive output directory and containment check
    resolved_output = _resolve_contained_output(output_dir, allowed_parent, protected, config.workspace_root)
    resolved_output.mkdir(exist_ok=False)

    lifecycle = _RunLifecycle(resolved_output)
    try:
        return _execute_owned_run(config, resolved_output, lifecycle, approval=approval)
    except Exception as exc:
        lifecycle.record_failure(exc)
        raise


def _execute_owned_run(
    config: StudyConfiguration,
    resolved_output: Path,
    lifecycle: _RunLifecycle,
    *,
    approval: Optional[BoundFile] = None,
) -> StudyResult:
    """Runs the study inside an owned run root; every stage is named for the failure record."""
    written_artifacts: List[Dict[str, Any]] = []
    is_historical = config.data_kind == DATA_KIND_HISTORICAL

    def _write_artifact(rel_path: str, content_bytes: bytes) -> None:
        _write_exclusive(resolved_output / rel_path, content_bytes)
        written_artifacts.append(
            {
                "path": rel_path,
                "bytes": len(content_bytes),
                "sha256": _sha256_upper(content_bytes),
            }
        )

    # 2. Prerequisites
    lifecycle.enter("verify_prerequisites")
    verified = _verify_run_prerequisites(config)
    _write_artifact("config.json", config.config_bytes)

    # Human approval verification stage (before load_inputs, outcomes, or features)
    approval_raw: Optional[bytes] = None
    approval_doc: Optional[Dict[str, Any]] = None
    if config.data_kind == DATA_KIND_HISTORICAL:
        lifecycle.enter("verify_human_approval")
        if approval is None:
            raise InputValidationError("Missing required approval BoundFile", field="approval", reason="approval is None")
        approval_raw = _read_bound_file(approval, "approval")
        approval_doc = parse_strict_json_bytes(approval_raw)
        validate_approval_document(approval_doc, "approval")

        # H -> C join
        c_bytes = config.config_bytes
        c_sha = _sha256_upper(c_bytes)
        c_len = len(c_bytes)
        h_c = approval_doc["config_identity"]
        if h_c["raw_byte_count"] != c_len or h_c["sha256"].upper() != c_sha:
            raise InputValidationError(
                f"Human approval config_identity mismatch: expected {c_len} bytes {c_sha}, got {h_c['raw_byte_count']} bytes {h_c['sha256']}",
                field="approval.config_identity",
                reason="approval config_identity mismatch",
            )

        # H -> A join
        h_a = approval_doc["admission_identity"]
        if h_a["raw_byte_count"] != config.admission.raw_byte_count or h_a["sha256"].upper() != config.admission.sha256:
            raise InputValidationError(
                f"Human approval admission_identity mismatch: expected {config.admission.raw_byte_count} bytes {config.admission.sha256}, got {h_a['raw_byte_count']} bytes {h_a['sha256']}",
                field="approval.admission_identity",
                reason="approval admission_identity mismatch",
            )

        # Check evidence files
        for idx, item in enumerate(approval_doc["source_use_evidence"]):
            for e_idx, ev in enumerate(item["evidence"]):
                ev_bound = BoundFile(path=ev["path"], raw_byte_count=ev["raw_byte_count"], sha256=ev["sha256"])
                _read_bound_file(ev_bound, f"approval.source_use_evidence[{idx}].evidence[{e_idx}]")
        for c_idx, cev in enumerate(approval_doc["calendar_evidence"]["evidence"]):
            cev_bound = BoundFile(path=cev["path"], raw_byte_count=cev["raw_byte_count"], sha256=cev["sha256"])
            _read_bound_file(cev_bound, f"approval.calendar_evidence.evidence[{c_idx}]")

        # Verify input_refs cover every C file exactly once
        seen_refs = set()
        for idx, entry in enumerate(approval_doc["source_use_evidence"]):
            for r_idx, ref in enumerate(entry["input_refs"]):
                key = (ref["role"], ref["file_index"])
                if key in seen_refs:
                    raise InputValidationError(
                        f"Duplicate input_ref {key} in approval source_use_evidence",
                        field=f"approval.source_use_evidence[{idx}].input_refs[{r_idx}]",
                        reason="duplicate input_ref",
                    )
                seen_refs.add(key)
        expected_refs = set()
        for r_role, r_binding in (("nifty", config.nifty_input), ("vix", config.vix_input)):
            for f_i in range(len(r_binding.files)):
                expected_refs.add((r_role, f_i))
        if seen_refs != expected_refs:
            raise InputValidationError(
                f"Approval input_refs do not cover every configured file exactly once. Missing: {sorted(expected_refs - seen_refs)}, Extra: {sorted(seen_refs - expected_refs)}",
                field="approval.source_use_evidence",
                reason="input_refs coverage mismatch",
            )

        # Write 13th artifact
        _write_artifact("historical-admission.json", approval_raw)

    # 3. Load inputs
    lifecycle.enter("load_inputs")
    nifty_series, vix_series, aligned, calendar_raw = _load_admitted_inputs(config, lifecycle.retain_input_warnings)

    # If historical: the configured cutoffs must equal the dates the rule derives from the actual axis
    if config.data_kind == DATA_KIND_HISTORICAL:
        derive_historical_split_cutoffs(
            [obs.date for obs in aligned.aligned_observations],
            expected_development_start=config.development_start,
            expected_test_start=config.test_start,
        )

    # 4. Frozen input-only admission, before any outcome or feature exists
    lifecycle.enter("verify_admission")
    admission_record, admission_raw = _verify_frozen_admission(config, nifty_series, vix_series, aligned, calendar_raw)
    _write_artifact("admission.json", admission_raw)

    # 5. Canonical reference SplitPlan
    lifecycle.enter("build_outcomes_features")
    outcomes = compute_twenty_session_outcomes(nifty_series)
    features = compute_nifty_features(aligned)

    lifecycle.enter("reference_plan")
    ref_plan = build_split_plan(
        features,
        outcomes,
        development_start=config.development_start,
        test_start=config.test_start,
    )

    # 6. Check frozen admission gap inventory against reference plan BEFORE replay/comparators
    lifecycle.enter("verify_plan_admission")
    verify_admission_against_reference_plan(admission_record, ref_plan)

    # 7. Replay adapter
    lifecycle.enter("replay")
    heuristic_map, replay_evidence = run_replay_adapter(
        features,
        node_executable=config.node_executable.path,
        replay_script=config.replay_script.path,
        workspace_root=config.workspace_root,
        work_dir=resolved_output,
        timeout_seconds=config.timeout_seconds,
        trusted_model=verified["model_identity"],
        trusted_build_manifest=verified["trusted_build_manifest"],
    )

    # 8. Serial comparators execution
    lifecycle.enter("comparators")
    freq_res, log_res, captured_warnings = _execute_serial_comparators(
        features,
        outcomes,
        development_start=config.development_start,
        test_start=config.test_start,
        warning_collector=lifecycle.warnings,
        expected_dependency_versions=config.dependency_versions,
    )

    # 9. Plan and block reconciliation
    lifecycle.enter("reconcile")
    _reconcile_comparator_blocks(ref_plan, freq_res, log_res)

    # 10. Evaluate partitions
    lifecycle.enter("scoring")
    dev_part = _evaluate_partition(
        "development",
        ref_plan.development_indices,
        ref_plan,
        outcomes,
        heuristic_map,
        freq_res.development_block,
        log_res.development_block,
        logistic_method=log_res.method,
    )

    test_part = _evaluate_partition(
        "test",
        ref_plan.test_indices,
        ref_plan,
        outcomes,
        heuristic_map,
        freq_res.test_block,
        log_res.test_block,
        logistic_method=log_res.method,
    )

    # 10b. Statistical uncertainty computation for paired test-loss differences
    lifecycle.enter("uncertainty")
    axis_dates = tuple(obs.date for obs in aligned.aligned_observations)
    test_start_idx = None
    for idx, obs_item in enumerate(aligned.aligned_observations):
        if obs_item.date == config.test_start:
            test_start_idx = idx
            break
    if test_start_idx is None:
        raise RuntimeError(f"test_start {config.test_start} not found in aligned observations")

    requested_keys = tuple(RequestedKey(r.origin_index, r.origin_date) for r in test_part.per_origin_records)
    if test_part.comparison_status in ("scored", "empty"):
        method_rows = {
            "heuristic": tuple(BrierRow(r.origin_index, r.origin_date, r.heuristic.brier) for r in test_part.per_origin_records),
            "frequency": tuple(BrierRow(r.origin_index, r.origin_date, r.frequency.brier) for r in test_part.per_origin_records),
            "logistic": tuple(BrierRow(r.origin_index, r.origin_date, r.logistic.brier) for r in test_part.per_origin_records),
        }
    else:
        method_rows = None

    req_temp = UncertaintyRequest(
        axis_dates=axis_dates,
        test_start_index=test_start_idx,
        requested_keys=requested_keys,
        comparison_status=test_part.comparison_status,
        method_available={
            "heuristic": test_part.heuristic_available,
            "frequency": test_part.frequency_available,
            "logistic": test_part.logistic_available,
        },
        method_rows=method_rows,
        union_gap_positions=tuple(admission_record["union_gap_positions"]),
    )
    raw_uncertainty_input = serialize_uncertainty_input(req_temp)
    _write_artifact("uncertainty-input.json", raw_uncertainty_input)
    uncertainty_input_sha = _sha256_upper(raw_uncertainty_input)
    uncertainty_input_id = {
        "raw_byte_count": len(raw_uncertainty_input),
        "sha256": uncertainty_input_sha,
    }

    # The identity is the hash of the bytes serialized from the unbound request, so it is bound only now
    req_with_id = replace(req_temp, input_identity=uncertainty_input_id)

    max_resample = config.uncertainty["max_resample_positions"]
    uncertainty_result = compute_uncertainty(
        req_with_id,
        max_resample_positions=max_resample,
        runtime_identity={
            "python_implementation": verified["runtime_identities"]["python_implementation"],
            "python_version": verified["runtime_identities"]["python_version"],
        },
    )
    uncertainty_block = UncertaintyBlock.from_result(uncertainty_result)

    raw_uncertainty_diagnostics = serialize_strict_json(
        build_uncertainty_diagnostics_document(uncertainty_result.diagnostics)
    )
    _write_artifact("uncertainty-diagnostics.json", raw_uncertainty_diagnostics)

    # Build StudyResult
    lifecycle.enter("build_result")
    obs = aligned.aligned_observations

    approval_identity = None
    if is_historical:
        if approval is None or approval_raw is None:
            raise InputValidationError("Approval is required for historical study result", field="approval", reason="missing approval")
        approval_identity = {
            "raw_byte_count": len(approval_raw),
            "sha256": _sha256_upper(approval_raw),
        }

    private_paths = {
        "config": config.config_path,
        "nifty_input": ";".join(f.bound.path for f in config.nifty_input.files),
        "vix_input": ";".join(f.bound.path for f in config.vix_input.files),
        "calendar": config.calendar.path,
        "admission": config.admission.path,
        "node_executable": config.node_executable.path,
        "python_executable": config.python_executable.path,
        "workspace_root": config.workspace_root,
    }
    if approval is not None:
        private_paths["approval"] = approval.path

    study_result = StudyResult(
        run_id=resolved_output.name,
        study_id=config.study_id,
        protocol_id=config.protocol_id,
        data_kind=config.data_kind,
        development_status=config.development_status,
        claim_label=REPLAY_CLAIM_LABEL,
        coverage_start_date=obs[0].date,
        coverage_end_date=obs[-1].date,
        development_start=config.development_start,
        test_start=config.test_start,
        admission_inventory=admission_record,
        config_identity={"raw_byte_count": len(config.config_bytes), "sha256": _sha256_upper(config.config_bytes)},
        admission_identity={"raw_byte_count": len(admission_raw), "sha256": _sha256_upper(admission_raw)},
        input_identities={
            "nifty": _series_identity(nifty_series, config.nifty_input),
            "vix": _series_identity(vix_series, config.vix_input),
            "calendar": {
                "raw_byte_count": len(calendar_raw),
                "sha256": _sha256_upper(calendar_raw),
                "session_count": len(aligned.expected_sessions or ()),
            },
        },
        source_identities=verified["source_identities"],
        runtime_identities=verified["runtime_identities"],
        model_identity=verified["model_identity"],
        build_identity=verified["build_identity"],
        replay_identity={
            "claim_label": REPLAY_CLAIM_LABEL,
            "script": verified["replay_script_identity"],
            "request": replay_evidence["request"],
            "response": replay_evidence["response"],
            "model_sha256": verified["model_identity"]["sha256"],
            "build_manifest_sha256": verified["build_identity"]["sha256"],
            "calculation_id": verified["build_identity"]["calculation_id"],
        },
        private_paths=private_paths,
        comparator_metadata={
            "frequency": {
                "method": freq_res.method,
                "alpha": freq_res.alpha,
                "classes": list(freq_res.classes),
                "series_id": freq_res.series_id,
                "horizon_sessions": freq_res.horizon_sessions,
                "protocol_id": freq_res.protocol_id,
                "outcome_definition": freq_res.outcome_definition,
            },
            "logistic": {
                "method": log_res.method,
                "configuration": {
                    "solver": log_res.configuration.solver,
                    "c": log_res.configuration.c,
                    "l1_ratio": log_res.configuration.l1_ratio,
                    "fit_intercept": log_res.configuration.fit_intercept,
                    "tol": log_res.configuration.tol,
                    "max_iter": log_res.configuration.max_iter,
                    "class_weight": log_res.configuration.class_weight,
                    "warm_start": log_res.configuration.warm_start,
                    "verbose": log_res.configuration.verbose,
                },
                "classes": list(log_res.classes),
                "series_id": log_res.series_id,
                "horizon_sessions": log_res.horizon_sessions,
                "protocol_id": log_res.protocol_id,
                "outcome_definition": log_res.outcome_definition,
                "dependency_versions": [list(pair) for pair in log_res.dependency_versions],
                "numeric_features": list(log_res.numeric_features),
                "encoded_features": list(log_res.encoded_features),
                "regime_order": list(log_res.regime_order),
            },
        },
        partitions={
            "development": dev_part,
            "test": test_part,
        },
        warnings=tuple(captured_warnings),
        input_warnings=tuple(lifecycle.input_warnings),
        uncertainty=uncertainty_block,
        approval_identity=approval_identity,
        limitations=HISTORICAL_LIMITATIONS if is_historical else SYNTHETIC_LIMITATIONS,
    )

    # 11. Write artifacts in order; manifest LAST
    lifecycle.enter("write_result")
    result_doc = build_result_document(study_result)
    _write_artifact("result.json", serialize_strict_json(result_doc))
    _write_artifact("predictions.json", serialize_strict_json(build_predictions_document(study_result)))

    lifecycle.enter("write_summary")
    summary_doc = build_panel_summary(study_result)
    _write_artifact("panel-summary.json", serialize_strict_json(summary_doc))

    # Everything after panel-summary.json must leave no valid completion manifest on failure
    lifecycle.enter("render_report")
    report_text = render_report_markdown(study_result)
    _write_artifact("report.md", report_text.encode("utf-8") + b"\n")

    lifecycle.enter("verify_artifacts")
    # Inventory the replay streams first: the semantic check then joins them to the captured
    # identities, and the recheck below catches any change after this inventory
    for name in ("replay-request.json", "replay-response.json", "replay-stderr.log", "replay-invocation.json"):
        data = (resolved_output / name).read_bytes()
        written_artifacts.append({"path": name, "bytes": len(data), "sha256": _sha256_upper(data)})
    ok_rel, msg_rel = verify_study_artifacts_semantic_relations(resolved_output)
    if not ok_rel:
        raise RuntimeError(f"Semantic verification of study artifacts failed: {msg_rel}")

    lifecycle.enter("finalize_manifest")
    # Hash what is actually on disk, not what was intended
    for entry in written_artifacts:
        data = (resolved_output / entry["path"]).read_bytes()
        if len(data) != entry["bytes"] or _sha256_upper(data) != entry["sha256"]:
            raise RuntimeError(f"Artifact changed before completion: {entry['path']}")

    manifest_doc = build_run_manifest(
        run_id=study_result.run_id,
        study_id=study_result.study_id,
        protocol_id=study_result.protocol_id,
        data_kind=study_result.data_kind,
        development_status=study_result.development_status,
        coverage_start_date=study_result.coverage_start_date,
        coverage_end_date=study_result.coverage_end_date,
        artifacts=written_artifacts,
        config_identity=study_result.config_identity,
        admission_identity=study_result.admission_identity,
        input_identities=study_result.input_identities,
        source_identities=study_result.source_identities,
        runtime_identities=study_result.runtime_identities,
        model_identity=study_result.model_identity,
        build_identity=study_result.build_identity,
        completion_timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        approval_identity=study_result.approval_identity,
    )
    _publish_completion_manifest(resolved_output / "run-manifest.json", serialize_strict_json(manifest_doc))

    return study_result


def parse_cli_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parses command-line arguments for study runner."""
    parser = argparse.ArgumentParser(
        prog="research.prediction_eval.study",
        description="Offline Nifty 50 Prediction Evaluation Study Runner",
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to private study configuration JSON file",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Path to new, exclusive study run output directory",
    )
    parser.add_argument(
        "--approval",
        default=None,
        help="Path to private human approval JSON file (historical only; requires both identity flags)",
    )
    parser.add_argument(
        "--approval-bytes",
        type=int,
        default=None,
        help="Externally pinned raw byte count of the human approval file",
    )
    parser.add_argument(
        "--approval-sha256",
        default=None,
        help="Externally pinned 64-hex SHA-256 of the human approval file",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """In-process CLI entry point."""
    args = parse_cli_args(argv)
    config_path = Path(args.config)
    output_path = Path(args.output_dir)

    if not config_path.exists():
        sys.stderr.write(f"Configuration file not found: {config_path}\n")
        return 1

    # The approval identity is an external pin, so it is never read from the approval file
    # itself: all three flags together, or none. Synthetic runs refuse a supplied approval.
    approval_flags = (args.approval, args.approval_bytes, args.approval_sha256)
    approval_bound: Optional[BoundFile] = None
    if any(flag is not None for flag in approval_flags):
        if any(flag is None for flag in approval_flags):
            sys.stderr.write("Approval requires --approval, --approval-bytes and --approval-sha256 together\n")
            return 1
        try:
            app_bytes = _require_byte_count(args.approval_bytes, "approval_bytes")
            app_sha = _require_sha256(args.approval_sha256, "approval_sha256")
        except InputValidationError as exc:
            sys.stderr.write(f"Invalid approval binding: {exc}\n")
            return 1
        app_path = Path(args.approval)
        if not app_path.exists():
            sys.stderr.write(f"Approval file not found: {app_path}\n")
            return 1
        approval_bound = BoundFile(path=str(app_path.resolve()), raw_byte_count=app_bytes, sha256=app_sha)

    try:
        config = load_study_configuration_file(config_path)
        run_study(config, output_path, allowed_parent=config.allowed_output_parent, approval=approval_bound)
        return 0
    except Exception as exc:
        sys.stderr.write(f"Study execution failed: {exc}\n")
        diag_err = getattr(exc, "failure_record_error", None)
        if diag_err is not None:
            sys.stderr.write(f"Failure record could not be written: {diag_err}\n")
        cleanup_err = getattr(exc, "manifest_cleanup_error", None)
        if cleanup_err is not None:
            sys.stderr.write(f"Partial run-manifest.json could not be removed: {cleanup_err}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
