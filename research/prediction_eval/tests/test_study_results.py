"""
Unit tests for Study Results, Result Serialization, Manifest Binding, and UI Presentation Seam.

Verifies:
  - StudyResult immutable DTO construction, invariants, and validation.
  - Strict panel-summary.json generation, whitelisted fields, and exclusion of private paths/CSVs.
  - Raw zero/infinite/empty log-loss state semantics and descriptive reliability bins.
  - Markdown report rendering from the same result object.
  - run-manifest.json generation, complete artifact tracking, and self-hash exclusion.
  - ReleaseDescriptor binding and checked promotion validation.
  - UI display-state evaluation in fixed precedence order (unavailable, error, unsupported_version, stale, displayable).
  - Independent oracles from neutral requirements including the mixed three-row case, on the
    persisted summary and private result documents as well as in memory.
  - Closed nested schemas: DTO coherence and unknown-field, state and value rejection.
  - Native-type frozen admission, impossible finite metrics at the actual UI seam with matching
    raw-byte bindings, probability conservation, row coherence and private loader warnings.
"""

from __future__ import annotations

import copy
import dataclasses
import datetime
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
import tempfile
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence
import unittest

from research.prediction_eval.features import VALID_REGIMES
from research.prediction_eval.metrics import (
    ComparisonMetrics,
    EvaluationOrigin,
    ModelMetrics,
    PROTOCOL_ID as METRICS_PROTOCOL_ID,
    ReliabilityBin,
    RowScore,
    score_comparison,
    STATUS_EMPTY as METRICS_STATUS_EMPTY,
    STATUS_SCORED as METRICS_STATUS_SCORED,
)
from research.prediction_eval.outcomes import (
    OUTCOME_CLASS_BEAR,
    OUTCOME_CLASS_BULL,
    OUTCOME_CLASS_NEUTRAL,
)
from research.prediction_eval.study_results import (
    ADMISSION_POLICY,
    build_candidate_descriptor,
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
    evaluate_ui_display_state,
    EXPECTED_MODELS_SHA256,
    FAILURE_RECORD_NAME,
    HISTORICAL_LIMITATIONS,
    MethodOriginRecord,
    ORDERED_CLASSES,
    parse_release_descriptor,
    parse_strict_json_bytes,
    PartitionCounts,
    PartitionResult,
    PerOriginRecord,
    release_descriptor_document,
    ReleaseDescriptor,
    render_report_markdown,
    REQUIRED_DEPENDENCIES,
    REQUIRED_MANIFEST_ARTIFACTS_V2,
    REQUIRED_MANIFEST_ARTIFACTS_V3,
    SCHEMA_VERSION_ADMISSION,
    SCHEMA_VERSION_ADMISSION_V2,
    SCHEMA_VERSION_APPROVAL_V1,
    SCHEMA_VERSION_CONFIG_V3,
    SCHEMA_VERSION_RELEASE_DESCRIPTOR,
    SCHEMA_VERSION_RESULT_V3,
    SCHEMA_VERSION_RUN_MANIFEST_V2,
    SCHEMA_VERSION_RUN_MANIFEST_V3,
    SCHEMA_VERSION_SUMMARY_V2,
    SCHEMA_VERSION_SUMMARY_V3,
    SEMANTIC_RELATION_ARTIFACTS_V3,
    serialize_strict_json,
    SOURCE_KIND_HISTORICAL,
    STATUS_COMPARISON_UNAVAILABLE,
    STATUS_EMPTY,
    STATUS_SCORED,
    StudyResult,
    STUDY_PROTOCOL_ID,
    UI_STATE_DISPLAYABLE,
    UI_STATE_ERROR,
    UI_STATE_STALE,
    UI_STATE_UNAVAILABLE,
    UI_STATE_UNSUPPORTED_VERSION,
    UNCERTAINTY_STATUS_AVAILABLE,
    UNCERTAINTY_STATUS_UNAVAILABLE,
    UncertaintyBlock,
    _uncertainty_document,
    validate_admission_document,
    validate_approval_document,
    validate_result_document,
    validate_run_manifest_document,
    validate_summary_document,
    verify_completed_run,
    verify_completion_binding,
    verify_promotion_binding,
    verify_study_artifacts_semantic_relations,
)
from research.prediction_eval.uncertainty import (
    BLOCK_FLOOR_FACTOR,
    BLOCK_LENGTH_LABELS,
    BLOCK_LENGTH_SEEDS,
    BLOCK_LENGTHS,
    BOOTSTRAP_REPLICATES,
    BrierRow,
    compute_uncertainty,
    NOMINAL_COVERAGE,
    ORDERED_PAIR_IDS,
    QUANTILE_RULE,
    RequestedKey,
    serialize_uncertainty_input,
    UNCERTAINTY_METHOD,
    UNCERTAINTY_PROTOCOL_ID,
    UncertaintyRequest,
    build_uncertainty_diagnostics_document,
)


class DummyPrediction:
    def __init__(self, origin_index: int, origin_date: datetime.date, probabilities: tuple):
        self._origin_index = origin_index
        self._origin_date = origin_date
        self._probabilities = probabilities

    @property
    def origin_index(self) -> int:
        return self._origin_index

    @property
    def origin_date(self) -> datetime.date:
        return self._origin_date

    @property
    def probabilities(self) -> tuple:
        return self._probabilities


FILE_IDENTITY = {"raw_byte_count": 10, "sha256": "A" * 64}
INPUT_IDENTITIES = {
    role: {
        "raw_byte_count": 100,
        "sha256": "B" * 64,
        "record_count": 3,
        "observed_first_date": "2022-01-03",
        "observed_last_date": "2022-01-05",
        "units": "index_points",
        "source_kind": "synthetic_fixture",
        "source_url": None,
        "requested_interval": None,
        "acquisition_time": None,
        "source_use_note": "Generated synthetic test fixture",
    }
    for role in ("nifty", "vix")
}
INPUT_IDENTITIES["calendar"] = {"raw_byte_count": 50, "sha256": "C" * 64, "session_count": 3}
SOURCE_IDENTITIES = {
    path: dict(FILE_IDENTITY)
    for path in (
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
}
RUNTIME_IDENTITIES = {
    "python_version": sys.version.split()[0],
    "python_implementation": platform.python_implementation(),
    "python_executable": dict(FILE_IDENTITY),
    "platform": sys.platform,
    "node_version": "v22.0.0",
    "node_executable": dict(FILE_IDENTITY),
    # Synthetic labels for the closed required set; the archive relation compares them, not a live import
    "dependency_versions": {"numpy": "2.4.3", "scikit-learn": "1.9.1", "scipy": "1.17.0", "threadpoolctl": "3.6.0"},
}
# The fixed pin is stated here, not taken from production, so a changed pin fails this oracle
PINNED_MODEL_SHA256 = "87C4DB2A4EB3B40AE5F7499C977AB407FFE3C3BE367E4DAE8FD8AE1804F543CD"
MODEL_IDENTITY = {"path": "public/models.json", "raw_byte_count": 5, "sha256": PINNED_MODEL_SHA256, "platt_params": [1.42, 0.02]}
BUILD_IDENTITY = {"raw_byte_count": 7, "sha256": "E" * 64, "mode": "candidate", "calculation_id": "calc", "compiler_exit": 0}
REPLAY_IDENTITY = {
    "claim_label": "Retrospective replay of the frozen current heuristic",
    "script": dict(FILE_IDENTITY),
    "request": dict(FILE_IDENTITY),
    "response": dict(FILE_IDENTITY),
    "model_sha256": PINNED_MODEL_SHA256,
    "build_manifest_sha256": "E" * 64,
    "calculation_id": "calc",
}
ADMISSION = {
    "schema_version": SCHEMA_VERSION_ADMISSION,
    "data_kind": "synthetic",
    "protocol_id": STUDY_PROTOCOL_ID,
    "date_selection_rule": DATE_SELECTION_RULE,
    "development_start": "2022-01-03",
    "test_start": "2022-01-04",
    "inputs": {
        "nifty": {"raw_byte_count": 100, "sha256": "B" * 64, "record_count": 3},
        "vix": {"raw_byte_count": 100, "sha256": "B" * 64, "record_count": 3},
        "calendar": {"raw_byte_count": 50, "sha256": "C" * 64, "session_count": 3},
    },
    "axis": {"session_count": 3, "first_date": "2022-01-03", "last_date": "2022-01-05"},
    "mature_test_start_index": 1,
    "mature_test_end_index": 3,
    "mature_test_span_count": 2,
    "warmup_gap_positions": [],
    "warmup_gap_count": 0,
    "missing_vix_gap_positions": [],
    "missing_vix_gap_count": 0,
    "union_gap_positions": [],
    "union_gap_count": 0,
    "gap_digest": "F" * 64,
    "policy": ADMISSION_POLICY,
}
COMPARATOR_METADATA = {
    "frequency": {
        "method": "fixed-laplace1-frequency-v1",
        "alpha": 1.0,
        "classes": list(ORDERED_CLASSES),
        "series_id": "nifty50_price_index",
        "horizon_sessions": 20,
        "protocol_id": "nifty-close-features-v1",
        "outcome_definition": "close-return-20-session-half-percent-neutral-inclusive-v1",
    },
    "logistic": {
        "method": "fixed-logistic-v1",
        "configuration": {
            "solver": "lbfgs",
            "c": 1.0,
            "l1_ratio": 0.0,
            "fit_intercept": True,
            "tol": 1e-6,
            "max_iter": 2000,
            "class_weight": None,
            "warm_start": False,
            "verbose": 0,
        },
        "classes": list(ORDERED_CLASSES),
        "series_id": "nifty50_price_index",
        "horizon_sessions": 20,
        "protocol_id": "nifty-close-features-v1",
        "outcome_definition": "close-return-20-session-half-percent-neutral-inclusive-v1",
        "dependency_versions": [["numpy", "2.4.3"], ["scikit-learn", "1.9.1"], ["scipy", "1.17.0"]],
        "numeric_features": ["ret_5d", "rsi_14", "macd_hist", "vol_30d", "rel_strength_20d", "drawdown"],
        "encoded_features": [f"regime_{name}" for name in VALID_REGIMES],
        "regime_order": list(VALID_REGIMES),
    },
}
INPUT_WARNING = {
    "file_path": "D:\\private\\nifty.csv",
    "line": "line 5",
    "field": "Open",
    "message": "Malformed Open value 'private-open-cell'; expected plain decimal syntax",
    "raw_value": "private-open-cell",
}


def _pool_counts(size: int) -> List[int]:
    """Class counts that sum to the listed pool, spread in BEAR, NEUTRAL, BULL order."""
    return [size // 3 + (1 if size % 3 > 0 else 0), size // 3 + (1 if size % 3 > 1 else 0), size // 3]


def _frequency_block(
    partition: str,
    requested: Sequence[int],
    *,
    available: bool = True,
    cutoff_index: int = 0,
    cutoff_date: str = "2022-01-03",
    fitting: Sequence[int] = (0, 1, 2),
) -> Dict[str, Any]:
    return {
        "method": "fixed-laplace1-frequency-v1",
        "partition": partition,
        "fitting_indices": list(fitting) if available else [],
        "cutoff_index": cutoff_index,
        "cutoff_date": cutoff_date,
        "requested_indices": list(requested),
        "prediction_count": len(requested) if available else 0,
        "unavailable_reason": None if available else "no_fit_rows",
        "fit": {"class_counts": _pool_counts(len(fitting)), "probabilities": [1 / 3, 1 / 3, 1 / 3]} if available else None,
    }


def _logistic_block(
    partition: str,
    requested: Sequence[int],
    *,
    available: bool = True,
    cutoff_index: int = 0,
    cutoff_date: str = "2022-01-03",
    fitting: Sequence[int] = (0, 1, 2),
) -> Dict[str, Any]:
    fit = {
        "numeric_means": [0.0] * 6,
        "numeric_variances": [1.0] * 6,
        "numeric_scales": [1.0] * 6,
        "coefficients": [[0.0] * 12 for _ in range(3)],
        "intercepts": [0.0] * 3,
        "n_iter": 42,
        "classes": list(ORDERED_CLASSES),
        "feature_names": [f"f{i}" for i in range(12)],
    }
    return {
        "method": "fixed-logistic-v1",
        "partition": partition,
        "fitting_indices": list(fitting),
        "cutoff_index": cutoff_index,
        "cutoff_date": cutoff_date,
        "class_counts": _pool_counts(len(fitting)),
        "regime_counts": [len(fitting), 0, 0, 0, 0, 0],
        "requested_indices": list(requested),
        "prediction_count": len(requested) if available else 0,
        "unavailable_reason": None if available else "not_converged",
        "failure_stage": None if available else "fit",
        "fit": fit if available else None,
    }


# Completed-run fixture layout, stated from the planner rule: rows from 200 are past warmup, a
# fitting row needs i + 20 < cutoff, and the development pool is inside the refit pool
RUN_DEVELOPMENT_START = 223
RUN_DEVELOPMENT_POOL = (200, 201, 202)
RUN_REFIT_POOL = (200, 201, 202, 203)

# Saved invocation labels: config.json and the receipt name the same original locations, none of
# which exists here, so a relocated archive is checked against its own labels
SAVED_WORKSPACE_LABEL = "/synthetic/workspace"
SAVED_NODE_LABEL = "/synthetic/tools/node.exe"
SAVED_REPLAY_SCRIPT_LABEL = "/synthetic/workspace/research/prediction_eval/replay.cjs"
SAVED_TIMEOUT_SECONDS = 60

SYNTHETIC_REPLAY_REQUEST = b'{"schema_version": "nivesh-replay-input-v1", "note": "synthetic replay request for relation tests"}\n'
SYNTHETIC_REPLAY_RESPONSE = b'{"schema_version": "nivesh-replay-output-v1", "note": "synthetic replay response for relation tests"}\n'
SYNTHETIC_REPLAY_STDERR = b"synthetic child diagnostic line\n"


def _identity_of(data: bytes) -> Dict[str, Any]:
    return {"raw_byte_count": len(data), "sha256": hashlib.sha256(data).hexdigest().upper()}


def _replay_receipt(request: bytes, response: bytes, stderr: bytes) -> Dict[str, Any]:
    """A successful first-attempt receipt in the adapter's shape. Its paths name a relocated root."""
    root = "/synthetic/relocated-run"

    def _stream(name: str, data: bytes) -> Dict[str, Any]:
        return {"path": f"{root}/{name}", "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest().upper()}

    return {
        "attempt": 1,
        "exe": SAVED_NODE_LABEL,
        "argv": [SAVED_NODE_LABEL, SAVED_REPLAY_SCRIPT_LABEL, f"{root}/replay-request.json"],
        "cwd": SAVED_WORKSPACE_LABEL,
        "shell": False,
        "start_utc": "2026-11-04T00:00:00+00:00",
        "timeout_seconds": SAVED_TIMEOUT_SECONDS,
        "request": _stream("replay-request.json", request),
        "declared_environment": {"TEMP": "/synthetic/tmp", "TMP": "/synthetic/tmp"},
        "end_utc": "2026-11-04T00:00:01+00:00",
        "duration_seconds": 1.25,
        "timed_out": False,
        "immediate_child_exit": 0,
        "launch_state": "started",
        "launch_error": None,
        "capture_state": "complete",
        "capture_error": None,
        "stdout": _stream("replay-response.json", response),
        "stderr": _stream("replay-stderr.log", stderr),
    }


def _replay_files() -> Dict[str, bytes]:
    """Non-empty synthetic replay streams and the receipt that names their exact bytes."""
    receipt = _replay_receipt(SYNTHETIC_REPLAY_REQUEST, SYNTHETIC_REPLAY_RESPONSE, SYNTHETIC_REPLAY_STDERR)
    return {
        "replay-request.json": SYNTHETIC_REPLAY_REQUEST,
        "replay-response.json": SYNTHETIC_REPLAY_RESPONSE,
        "replay-stderr.log": SYNTHETIC_REPLAY_STDERR,
        "replay-invocation.json": serialize_strict_json(receipt),
    }


def _captured_replay_identity() -> Dict[str, Any]:
    return dict(copy.deepcopy(REPLAY_IDENTITY), request=_identity_of(SYNTHETIC_REPLAY_REQUEST), response=_identity_of(SYNTHETIC_REPLAY_RESPONSE))


def _saved_tools() -> Dict[str, Any]:
    """Saved tool declarations whose byte/hash fields are the identities the fixture result records."""

    def _tool(name: str, identity: Mapping[str, Any]) -> Dict[str, Any]:
        return {"path": f"/synthetic/tools/{name}", "raw_byte_count": identity["raw_byte_count"], "sha256": identity["sha256"]}

    return {
        "node_executable": _tool("node.exe", RUNTIME_IDENTITIES["node_executable"]),
        "python_executable": _tool("python.exe", RUNTIME_IDENTITIES["python_executable"]),
        # Same label the receipt's argv records, so the invocation join compares saved labels only
        "replay_script": dict(_tool("replay.cjs", REPLAY_IDENTITY["script"]), path=SAVED_REPLAY_SCRIPT_LABEL),
        "candidate_build_manifest": _tool("build-manifest.json", BUILD_IDENTITY),
        "models": _tool("models.json", MODEL_IDENTITY),
    }


def _set_pool(block: Dict[str, Any], pool: Sequence[int]) -> None:
    """Lists a new fitting pool with counts that still sum to it, so only the pool rule can object."""
    block["fitting_indices"] = list(pool)
    if "regime_counts" in block:
        block["class_counts"] = _pool_counts(len(pool))
        block["regime_counts"] = [len(pool)] + [0] * (len(VALID_REGIMES) - 1)
    elif block["fit"] is not None:
        block["fit"]["class_counts"] = _pool_counts(len(pool))


def _valid_uncertainty_block(
    status: str = UNCERTAINTY_STATUS_UNAVAILABLE,
    reason: Optional[str] = "comparison_unavailable",
    n: int = 0,
    point_differences: Optional[Tuple[Dict[str, Any], ...]] = None,
    block_lengths: Optional[Tuple[Dict[str, Any], ...]] = None,
    span: Optional[int] = None,
) -> UncertaintyBlock:
    if point_differences is None:
        point_differences = tuple(
            {"pair_id": pid, "point_difference": None}
            for pid in ORDERED_PAIR_IDS
        )
    if block_lengths is None:
        block_lengths = tuple(
            {
                "block_length": L,
                "label": BLOCK_LENGTH_LABELS[L],
                "status": status,
                "reason": reason,
                "seed": BLOCK_LENGTH_SEEDS[L],
                "pairs": tuple(
                    {"pair_id": pid, "lower": None, "upper": None}
                    for pid in ORDERED_PAIR_IDS
                ),
            }
            for L in BLOCK_LENGTHS
        )
    return UncertaintyBlock(
        protocol_id=UNCERTAINTY_PROTOCOL_ID,
        method=UNCERTAINTY_METHOD,
        status=status,
        reason=reason,
        n=n,
        mature_span_count=n if span is None else span,
        replicates=BOOTSTRAP_REPLICATES,
        nominal_coverage=NOMINAL_COVERAGE,
        quantile_rule=QUANTILE_RULE,
        block_floor_factor=BLOCK_FLOOR_FACTOR,
        point_differences=point_differences,
        block_lengths=block_lengths,
    )


# The toy TEST cutoff: index 1 on 2022-01-04, ADMISSION's mature start and test_start
SYNTHETIC_TEST_CUTOFF = ADMISSION["mature_test_start_index"]


def _coherent_admission(test: PartitionResult) -> Dict[str, Any]:
    """
    ADMISSION with a mature span that the TEST cohort fills, so a built summary keeps the
    portable relations (requested = span minus gaps; uncertainty n and span against TEST
    requested and the admitted span). A nonempty cohort fills a gap-free span. An empty cohort
    keeps ADMISSION's two slots, both gapped. Only the session counts grow; the toy dates stay.
    """
    doc = copy.deepcopy(ADMISSION)
    span = len(test.requested_indices) or doc["mature_test_span_count"]
    start = doc["mature_test_start_index"]
    end = start + span
    sessions = max(doc["axis"]["session_count"], end)
    doc.update(mature_test_end_index=end, mature_test_span_count=span)
    if not test.requested_indices:
        gaps = list(range(start, end))
        doc.update(missing_vix_gap_positions=gaps, missing_vix_gap_count=len(gaps), union_gap_positions=list(gaps), union_gap_count=len(gaps))
    doc["axis"]["session_count"] = sessions
    doc["inputs"]["calendar"]["session_count"] = sessions
    return doc


def _coherent_uncertainty(test: PartitionResult, span: int) -> UncertaintyBlock:
    """
    The schematic block a TEST partition takes over a gap-free admitted span, in the producer's
    reason order: comparison unavailable and empty keep no point; a scored cohort below every
    floor keeps the difference of its mean Briers. A cohort that clears a floor needs an explicit
    block, since this helper states no interval.
    """
    n = len(test.requested_indices)
    if test.comparison_status == STATUS_COMPARISON_UNAVAILABLE:
        return _valid_uncertainty_block(reason="comparison_unavailable", n=n, span=span)
    if n == 0:
        return _valid_uncertainty_block(reason="empty_cohort", n=0, span=span)
    if n >= BLOCK_FLOOR_FACTOR * BLOCK_LENGTHS[0]:
        raise ValueError("pass an explicit uncertainty block for a cohort that clears a floor")
    metrics = test.comparison_metrics
    points = tuple(
        {"pair_id": pair, "point_difference": metrics.heuristic.mean_brier - other.mean_brier}
        for pair, other in zip(ORDERED_PAIR_IDS, (metrics.frequency, metrics.logistic))
    )
    return _valid_uncertainty_block(reason="insufficient_nominal_blocks", n=n, span=span, point_differences=points)


class _StudyResultsFixtures(unittest.TestCase):
    """
    Shared synthetic fixtures and helpers with no test methods, so each test class below
    runs only its own tests instead of inheriting and repeating another class's cases.
    """

    def setUp(self) -> None:
        # Build three-row mixed oracle fixture
        self.d0 = datetime.date(2022, 1, 3)
        self.d1 = datetime.date(2022, 1, 4)
        self.d2 = datetime.date(2022, 1, 5)

        self.origins = [
            EvaluationOrigin(origin_index=0, origin_date=self.d0, actual_class=OUTCOME_CLASS_BEAR),
            EvaluationOrigin(origin_index=1, origin_date=self.d1, actual_class=OUTCOME_CLASS_NEUTRAL),
            EvaluationOrigin(origin_index=2, origin_date=self.d2, actual_class=OUTCOME_CLASS_BULL),
        ]

        # Toy heuristic: (.6, .3, .1), (.2, .5, .3), (.4, .2, .4)
        self.h_preds = [
            DummyPrediction(0, self.d0, (0.6, 0.3, 0.1)),
            DummyPrediction(1, self.d1, (0.2, 0.5, 0.3)),
            DummyPrediction(2, self.d2, (0.4, 0.2, 0.4)),
        ]

        # Toy frequency: perfect vectors
        self.f_preds = [
            DummyPrediction(0, self.d0, (1.0, 0.0, 0.0)),
            DummyPrediction(1, self.d1, (0.0, 1.0, 0.0)),
            DummyPrediction(2, self.d2, (0.0, 0.0, 1.0)),
        ]

        # Toy logistic: uniform vectors (1/3, 1/3, 1/3)
        u_prob = 1.0 / 3.0
        self.l_preds = [
            DummyPrediction(0, self.d0, (u_prob, u_prob, u_prob)),
            DummyPrediction(1, self.d1, (u_prob, u_prob, u_prob)),
            DummyPrediction(2, self.d2, (u_prob, u_prob, u_prob)),
        ]

        self.scored_comparison = score_comparison(
            self.origins,
            heuristic=self.h_preds,
            frequency=self.f_preds,
            logistic=self.l_preds,
        )

        self.counts = PartitionCounts(
            raw_partition_count=5,
            eligible_count=3,
            excluded_count=2,
            requested_count=3,
            exclusion_reason_counts={"unknown_outcome": 2},
            model_available_counts={"heuristic": 3, "frequency": 3, "logistic": 3},
        )

        self.study_result = self._study_result()

    def _scored_records(self, comparison: ComparisonMetrics, origins: Sequence[EvaluationOrigin]) -> tuple:
        records = []
        for idx, origin in enumerate(origins):

            def _method(metrics: ModelMetrics) -> MethodOriginRecord:
                row = metrics.row_scores[idx]
                return MethodOriginRecord(
                    forecast_state="available",
                    probabilities=row.probabilities,
                    predicted_class=row.predicted_class,
                    brier=row.brier,
                    log_loss=row.log_loss,
                    log_loss_state=row.log_loss_state,
                )

            records.append(
                PerOriginRecord(
                    origin_index=origin.origin_index,
                    origin_date=origin.origin_date,
                    origin_close="100.00",
                    maturity_index=origin.origin_index + 20,
                    maturity_date=origin.origin_date + datetime.timedelta(days=20),
                    maturity_close="101.00",
                    actual_class=origin.actual_class,
                    score_state="scored",
                    heuristic_expected_direction="NEUTRAL / RANGE-BOUND",
                    heuristic=_method(comparison.heuristic),
                    frequency=_method(comparison.frequency),
                    logistic=_method(comparison.logistic),
                )
            )
        return tuple(records)

    def _partition(
        self,
        name: str,
        comparison: Optional[ComparisonMetrics] = None,
        origins: Optional[Sequence[EvaluationOrigin]] = None,
        cutoff_index: int = 0,
        fitting: Sequence[int] = (0, 1, 2),
    ) -> PartitionResult:
        comparison = comparison if comparison is not None else self.scored_comparison
        origins = origins if origins is not None else self.origins
        indices = tuple(o.origin_index for o in origins)
        cutoff_date = self.d0 + datetime.timedelta(days=cutoff_index)
        cutoff = dict(cutoff_index=cutoff_index, cutoff_date=cutoff_date.isoformat(), fitting=fitting)
        return PartitionResult(
            partition=name,
            cutoff_index=cutoff_index,
            cutoff_date=cutoff_date,
            requested_indices=indices,
            requested_dates=tuple(o.origin_date for o in origins),
            counts=PartitionCounts(
                raw_partition_count=len(indices) + 2,
                eligible_count=len(indices),
                excluded_count=2,
                requested_count=len(indices),
                exclusion_reason_counts={"unknown_outcome": 2},
                model_available_counts={"heuristic": len(indices), "frequency": len(indices), "logistic": len(indices)},
            ),
            heuristic_available=True,
            frequency_available=True,
            frequency_unavailable_reason=None,
            frequency_block=_frequency_block(name, indices, **cutoff),
            logistic_available=True,
            logistic_unavailable_reason=None,
            logistic_failure_stage=None,
            logistic_block=_logistic_block(name, indices, **cutoff),
            comparison_status=STATUS_SCORED if origins else STATUS_EMPTY,
            comparison_unavailable_reasons=(),
            comparison_metrics=comparison,
            per_origin_records=self._scored_records(comparison, origins),
        )

    def _unavailable_partition(
        self,
        name: str,
        origins: Optional[Sequence[EvaluationOrigin]] = None,
        cutoff_index: int = 0,
        fitting: Sequence[int] = (0, 1, 2),
    ) -> PartitionResult:
        """Logistic not converged with usable heuristic and frequency forecasts, no scores."""
        origins = origins if origins is not None else self.origins
        cutoff_date = self.d0 + datetime.timedelta(days=cutoff_index)
        cutoff = dict(cutoff_index=cutoff_index, cutoff_date=cutoff_date.isoformat(), fitting=fitting)
        records = tuple(
            PerOriginRecord(
                origin_index=origin.origin_index,
                origin_date=origin.origin_date,
                origin_close="100.00",
                maturity_index=origin.origin_index + 20,
                maturity_date=origin.origin_date + datetime.timedelta(days=20),
                maturity_close="101.00",
                actual_class=origin.actual_class,
                score_state="unscored",
                heuristic_expected_direction="NEUTRAL / RANGE-BOUND",
                heuristic=MethodOriginRecord("available", self.h_preds[pos].probabilities),
                frequency=MethodOriginRecord("available", self.f_preds[pos].probabilities),
                logistic=MethodOriginRecord("unavailable", None),
            )
            for pos, origin in enumerate(origins)
        )
        indices = tuple(o.origin_index for o in origins)
        return PartitionResult(
            partition=name,
            cutoff_index=cutoff_index,
            cutoff_date=cutoff_date,
            requested_indices=indices,
            requested_dates=tuple(o.origin_date for o in origins),
            counts=PartitionCounts(
                raw_partition_count=5,
                eligible_count=3,
                excluded_count=2,
                requested_count=3,
                exclusion_reason_counts={"unknown_outcome": 2},
                model_available_counts={"heuristic": 3, "frequency": 3, "logistic": 0},
            ),
            heuristic_available=True,
            frequency_available=True,
            frequency_unavailable_reason=None,
            frequency_block=_frequency_block(name, indices, **cutoff),
            logistic_available=False,
            logistic_unavailable_reason="not_converged",
            logistic_failure_stage="fit",
            logistic_block=_logistic_block(name, indices, available=False, **cutoff),
            comparison_status=STATUS_COMPARISON_UNAVAILABLE,
            comparison_unavailable_reasons=("logistic: not_converged",),
            comparison_metrics=None,
            per_origin_records=records,
        )

    def _study_result(
        self,
        *,
        development: Optional[PartitionResult] = None,
        test: Optional[PartitionResult] = None,
        uncertainty: Optional[UncertaintyBlock] = None,
    ) -> StudyResult:
        # The default TEST partition starts at the admitted mature start, and the admission and
        # uncertainty block follow its cohort, so every built summary is portable-coherent
        test = test if test is not None else self._partition("test", cutoff_index=SYNTHETIC_TEST_CUTOFF)
        admission = _coherent_admission(test)
        if uncertainty is None:
            uncertainty = _coherent_uncertainty(test, admission["mature_test_span_count"])
        return StudyResult(
            run_id="run-2026-test-001",
            study_id="synthetic-toy-study",
            protocol_id=STUDY_PROTOCOL_ID,
            data_kind="synthetic",
            development_status="synthetic_development",
            claim_label="Retrospective replay of the frozen current heuristic",
            coverage_start_date=self.d0,
            coverage_end_date=self.d2,
            development_start=self.d0,
            test_start=self.d1,
            admission_inventory=admission,
            config_identity=dict(FILE_IDENTITY),
            admission_identity=dict(FILE_IDENTITY),
            input_identities=copy.deepcopy(INPUT_IDENTITIES),
            source_identities=copy.deepcopy(SOURCE_IDENTITIES),
            runtime_identities=copy.deepcopy(RUNTIME_IDENTITIES),
            model_identity=copy.deepcopy(MODEL_IDENTITY),
            build_identity=dict(BUILD_IDENTITY),
            replay_identity=copy.deepcopy(REPLAY_IDENTITY),
            private_paths={"nifty_input": "D:\\private\\nifty.csv"},
            comparator_metadata=copy.deepcopy(COMPARATOR_METADATA),
            partitions={
                "development": development if development is not None else self._partition("development"),
                "test": test,
            },
            warnings=({"category": "UserWarning", "message": "ordinary", "filename": "D:\\private\\x.py", "lineno": 3},),
            input_warnings=(dict(INPUT_WARNING),),
            uncertainty=uncertainty,
        )

    def _artifacts(self, summary_bytes: bytes) -> List[Dict[str, Any]]:
        entries = []
        for name in sorted(REQUIRED_MANIFEST_ARTIFACTS_V2):
            if name == "panel-summary.json":
                entries.append({"path": name, "bytes": len(summary_bytes), "sha256": hashlib.sha256(summary_bytes).hexdigest().upper()})
            else:
                entries.append({"path": name, "bytes": 100, "sha256": "A" * 64})
        return entries

    def _manifest_doc(self, summary_bytes: bytes, **overrides: Any) -> Dict[str, Any]:
        arguments: Dict[str, Any] = dict(
            run_id="run-2026-test-001",
            study_id="synthetic-toy-study",
            protocol_id=STUDY_PROTOCOL_ID,
            data_kind="synthetic",
            development_status="synthetic_development",
            coverage_start_date=self.d0,
            coverage_end_date=self.d2,
            artifacts=self._artifacts(summary_bytes),
            config_identity=FILE_IDENTITY,
            admission_identity=FILE_IDENTITY,
            input_identities=copy.deepcopy(INPUT_IDENTITIES),
            source_identities=copy.deepcopy(SOURCE_IDENTITIES),
            runtime_identities=copy.deepcopy(RUNTIME_IDENTITIES),
            model_identity=MODEL_IDENTITY,
            build_identity=BUILD_IDENTITY,
            completion_timestamp="2026-11-04T00:00:00Z",
        )
        arguments.update(overrides)
        return build_run_manifest(**arguments)

    def _bound_bytes(self) -> tuple:
        summary_bytes = serialize_strict_json(build_panel_summary(self.study_result))
        manifest_bytes = serialize_strict_json(self._manifest_doc(summary_bytes))
        return summary_bytes, manifest_bytes

    def _descriptor(self, raw_summary: bytes, raw_manifest: bytes, **overrides: Any) -> ReleaseDescriptor:
        arguments: Dict[str, Any] = dict(
            run_id="run-2026-test-001",
            study_id="synthetic-toy-study",
            protocol_id=STUDY_PROTOCOL_ID,
            summary_schema_version=SCHEMA_VERSION_SUMMARY_V2,
            coverage_end_date=self.d2.isoformat(),
            summary_bytes=len(raw_summary),
            summary_sha256=hashlib.sha256(raw_summary).hexdigest(),
            manifest_bytes=len(raw_manifest),
            manifest_sha256=hashlib.sha256(raw_manifest).hexdigest(),
        )
        arguments.update(overrides)
        return build_release_descriptor(**arguments)

    @staticmethod
    def _bytes_identity(data: bytes) -> Dict[str, Any]:
        return {"raw_byte_count": len(data), "sha256": hashlib.sha256(data).hexdigest().upper()}


class TestStudyResults(_StudyResultsFixtures):
    """Pure standard-library tests for study results, summaries, manifests, and UI binding."""

    def test_independent_oracles_mixed_three_row(self) -> None:
        """Verifies independently calculated expectations on the mixed three-row fixture."""
        cm = self.scored_comparison
        self.assertEqual(cm.sample_count, 3)
        self.assertEqual(cm.class_support, (1, 1, 1))

        # Heuristic: mean Brier = 2/5 (0.4)
        self.assertAlmostEqual(cm.heuristic.mean_brier, 0.4, places=12)
        self.assertAlmostEqual(cm.heuristic.accuracy, 2.0 / 3.0, places=12)
        self.assertEqual(cm.heuristic.tie_count, 1)

        # Frequency: perfect vectors -> mean Brier = 0.0, accuracy = 1.0, ties = 0
        self.assertAlmostEqual(cm.frequency.mean_brier, 0.0, places=12)
        self.assertAlmostEqual(cm.frequency.accuracy, 1.0, places=12)
        self.assertEqual(cm.frequency.tie_count, 0)

        # Logistic: uniform vectors -> mean Brier = 2/3, accuracy = 1/3, ties = 3
        self.assertAlmostEqual(cm.logistic.mean_brier, 2.0 / 3.0, places=12)
        self.assertAlmostEqual(cm.logistic.accuracy, 1.0 / 3.0, places=12)
        self.assertEqual(cm.logistic.tie_count, 3)

    def test_persisted_summary_and_result_carry_the_toy_oracles(self) -> None:
        """The same 2/5, 0 and 2/3 oracles, read back from the persisted bytes."""
        summary = parse_strict_json_bytes(serialize_strict_json(build_panel_summary(self.study_result)))
        models = summary["partitions"]["test"]["metrics"]["models"]

        self.assertAlmostEqual(models["heuristic"]["mean_brier"], 2.0 / 5.0, places=12)
        self.assertAlmostEqual(models["frequency"]["mean_brier"], 0.0, places=12)
        self.assertAlmostEqual(models["logistic"]["mean_brier"], 2.0 / 3.0, places=12)

        # Rows are actual classes, columns predicted. Heuristic row 3 ties (.4,.2,.4) to BEAR;
        # logistic ties every row to BEAR; the perfect frequency vectors stay on the diagonal.
        self.assertEqual(models["heuristic"]["confusion"], [[1, 0, 0], [0, 1, 0], [1, 0, 0]])
        self.assertEqual(models["frequency"]["confusion"], [[1, 0, 0], [0, 1, 0], [0, 0, 1]])
        self.assertEqual(models["logistic"]["confusion"], [[1, 0, 0], [1, 0, 0], [1, 0, 0]])
        self.assertEqual(models["heuristic"]["class_recall"], [1.0, 1.0, 0.0])
        self.assertEqual(models["logistic"]["class_recall"], [1.0, 0.0, 0.0])

        # BEAR probabilities .6, .2, .4 land in bins 6, 2 and 4, each with one row
        bear_bins = [b for b in models["heuristic"]["reliability_bins"] if b["class_label"] == "BEAR"]
        self.assertEqual([b["bin_index"] for b in bear_bins if b["count"]], [2, 4, 6])
        bin_six = bear_bins[6]
        self.assertAlmostEqual(bin_six["mean_probability"], 0.6, places=12)
        self.assertEqual(bin_six["observed_frequency"], 1.0)
        self.assertIsNone(bear_bins[0]["mean_probability"])
        self.assertEqual(bear_bins[2]["observed_frequency"], 0.0)

        result = parse_strict_json_bytes(serialize_strict_json(build_result_document(self.study_result)))
        validate_result_document(result)
        rows = result["partitions"]["test"]["per_origin_records"]
        self.assertAlmostEqual(rows[0]["heuristic"]["brier"], 0.26, places=12)
        self.assertAlmostEqual(rows[1]["heuristic"]["brier"], 0.38, places=12)
        self.assertAlmostEqual(rows[2]["heuristic"]["brier"], 0.56, places=12)
        self.assertEqual(rows[2]["heuristic"]["predicted_class"], "BEAR")
        self.assertAlmostEqual(rows[0]["logistic"]["log_loss"], math.log(3.0), places=12)
        self.assertEqual(rows[0]["frequency"]["log_loss_state"], "finite")
        self.assertEqual(result["warnings"][0]["message"], "ordinary")
        self.assertEqual(result["partitions"]["test"]["logistic_block"]["fit"]["n_iter"], 42)

    def test_zero_tiny_and_undefined_values_keep_their_states(self) -> None:
        """Raw zero stays null with infinite state; a tiny positive stays finite; empty recall stays null."""
        origins = [
            EvaluationOrigin(origin_index=0, origin_date=self.d0, actual_class=OUTCOME_CLASS_BULL),
            EvaluationOrigin(origin_index=1, origin_date=self.d1, actual_class=OUTCOME_CLASS_BULL),
        ]
        tiny = 5e-324
        zero_rows = [DummyPrediction(0, self.d0, (1.0, 0.0, 0.0)), DummyPrediction(1, self.d1, (0.5, 0.5, 0.0))]
        tiny_rows = [DummyPrediction(0, self.d0, (0.5, 0.5, tiny)), DummyPrediction(1, self.d1, (0.5, 0.5, tiny))]
        uniform = [DummyPrediction(i, d, (1 / 3, 1 / 3, 1 / 3)) for i, d in ((0, self.d0), (1, self.d1))]
        comparison = score_comparison(origins, heuristic=zero_rows, frequency=tiny_rows, logistic=uniform)
        result = self._study_result(test=self._partition("test", comparison, origins, cutoff_index=SYNTHETIC_TEST_CUTOFF))

        summary = parse_strict_json_bytes(serialize_strict_json(build_panel_summary(result)))
        models = summary["partitions"]["test"]["metrics"]["models"]
        self.assertIsNone(models["heuristic"]["mean_log_loss"])
        self.assertEqual(models["heuristic"]["log_loss_state"], "infinite")
        self.assertEqual(models["heuristic"]["zero_actual_probability_count"], 2)
        self.assertEqual(models["frequency"]["log_loss_state"], "finite")
        self.assertAlmostEqual(models["frequency"]["mean_log_loss"], -math.log(tiny), places=9)
        # Only BULL has support: BEAR and NEUTRAL recall are undefined, not zero
        self.assertEqual(models["frequency"]["class_recall"], [None, None, 0.0])

        rows = parse_strict_json_bytes(serialize_strict_json(build_result_document(result)))["partitions"]["test"]["per_origin_records"]
        self.assertIsNone(rows[0]["heuristic"]["log_loss"])
        self.assertEqual(rows[0]["heuristic"]["log_loss_state"], "infinite")
        self.assertIsNotNone(rows[0]["frequency"]["log_loss"])

    def test_empty_comparison_keeps_null_metrics(self) -> None:
        empty = score_comparison([], heuristic=[], frequency=[], logistic=[])
        result = self._study_result(development=self._partition("development", empty, []))
        summary = build_panel_summary(result)
        development = summary["partitions"]["development"]
        self.assertEqual(development["comparison_status"], STATUS_EMPTY)
        self.assertEqual(development["metrics"]["sample_count"], 0)
        self.assertIsNone(development["metrics"]["models"]["heuristic"]["mean_brier"])
        self.assertEqual(development["metrics"]["models"]["heuristic"]["log_loss_state"], "empty")

    def test_unavailable_partition_is_honest_everywhere(self) -> None:
        """Usable forecasts stay private, reasons and stages reach every artifact, no numbers invented."""
        result = self._study_result(test=self._unavailable_partition("test", cutoff_index=SYNTHETIC_TEST_CUTOFF))

        summary = build_panel_summary(result)
        test_part = summary["partitions"]["test"]
        self.assertEqual(test_part["comparison_status"], STATUS_COMPARISON_UNAVAILABLE)
        self.assertIsNone(test_part["metrics"])
        self.assertEqual(test_part["method_states"]["logistic"]["failure_stage"], "fit")
        self.assertEqual(test_part["counts"]["model_available_counts"], {"heuristic": 3, "frequency": 3, "logistic": 0})

        document = build_result_document(result)
        block = document["partitions"]["test"]["logistic_block"]
        self.assertIsNone(block["fit"])
        self.assertEqual(block["class_counts"], [1, 1, 1])
        self.assertEqual(block["fitting_indices"], [0, 1, 2])
        rows = build_predictions_document(result)["test"]
        self.assertEqual(rows[0]["frequency"]["probabilities"], [1.0, 0.0, 0.0])
        self.assertIsNone(rows[0]["logistic"]["probabilities"])
        self.assertIsNone(rows[0]["heuristic"]["brier"])

        report = render_report_markdown(result)
        self.assertIn("logistic: not_converged", report)
        self.assertIn("Usable Forecasts: heuristic=3, frequency=3, logistic=0", report)

    def test_panel_summary_structure_and_exclusions(self) -> None:
        """Verifies panel-summary.json schema, whitelisted fields, and private data exclusion."""
        summary = build_panel_summary(self.study_result)
        self.assertEqual(summary["schema_version"], SCHEMA_VERSION_SUMMARY_V2)
        self.assertEqual(summary["study_id"], "synthetic-toy-study")
        self.assertEqual(summary["data_kind"], "synthetic")
        self.assertEqual(summary["run_id"], "run-2026-test-001")
        self.assertEqual(summary["replay_identity"]["model_sha256"], PINNED_MODEL_SHA256)
        self.assertEqual(summary["provenance_identity"]["nifty_input_sha256"], "B" * 64)
        self.assertEqual(summary["dataset_attribution"]["source_kind"], "synthetic_fixture")
        self.assertIn("Synthetic", summary["dataset_attribution"]["asset_label"])

        # Exclusions: no raw prices, CSV inputs, per-origin records, coefficients, absolute paths
        summary_str = json.dumps(summary)
        self.assertNotIn("per_origin_records", summary)
        self.assertNotIn("coefficients", summary_str)
        self.assertNotIn("csv", summary_str.lower())
        self.assertNotIn("D:\\", summary_str)
        self.assertNotIn("C:\\", summary_str)
        self.assertNotIn("ordinary", summary_str)

        # Uncertainty block
        unc = summary["uncertainty"]
        self.assertEqual(unc["status"], UNCERTAINTY_STATUS_UNAVAILABLE)
        self.assertEqual(len(unc["block_lengths"]), 3)
        for bl in unc["block_lengths"]:
            self.assertEqual(bl["status"], UNCERTAINTY_STATUS_UNAVAILABLE)

    def test_strict_json_serialization_rejects_nan_and_inf(self) -> None:
        """Verifies strict JSON serializer rejects non-finite tokens."""
        bad_doc = {"value": float("nan")}
        with self.assertRaises(ValueError):
            serialize_strict_json(bad_doc)

        bad_inf = {"value": float("inf")}
        with self.assertRaises(ValueError):
            serialize_strict_json(bad_inf)

    def test_markdown_report_rendering(self) -> None:
        """Verifies markdown report includes expected sections and numbers from the same result."""
        md = render_report_markdown(self.study_result)
        self.assertIn("# Prediction Evaluation Study Report: synthetic-toy-study", md)
        self.assertIn("## Admission Gap Inventory", md)
        self.assertIn("## Partitions and Comparison Metrics", md)
        self.assertIn("0.4000", md)  # Heuristic Brier
        self.assertIn("0.0000", md)  # Frequency Brier
        self.assertIn("0.6667", md)  # Logistic Brier
        self.assertIn("Raw Partition Origins: 5", md)
        self.assertIn("Excluded Observations: 2", md)

    def test_partition_counts_reject_incoherent_coverage(self) -> None:
        base: Dict[str, Any] = dict(
            raw_partition_count=5,
            eligible_count=3,
            excluded_count=2,
            requested_count=3,
            exclusion_reason_counts={"unknown_outcome": 2},
            model_available_counts={"heuristic": 3, "frequency": 3, "logistic": 3},
        )
        PartitionCounts(**base)

        cases = {
            "excluded_not_raw_minus_eligible": dict(base, excluded_count=0),
            "requested_differs": dict(base, requested_count=2),
            "bool_count": dict(base, raw_partition_count=True),
            "unknown_reason": dict(base, exclusion_reason_counts={"looked_bad": 2}),
            "reasons_cannot_cover_exclusions": dict(base, exclusion_reason_counts={"unknown_outcome": 1}),
            "reason_exceeds_unique_exclusions": dict(base, exclusion_reason_counts={"unknown_outcome": 3}),
            "missing_model": dict(base, model_available_counts={"heuristic": 3, "frequency": 3}),
            "more_available_than_requested": dict(base, model_available_counts={"heuristic": 4, "frequency": 3, "logistic": 3}),
        }
        for name, kwargs in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    PartitionCounts(**kwargs)

        # Overlapping reasons on one origin legitimately sum above the unique exclusions
        PartitionCounts(**dict(base, exclusion_reason_counts={"unknown_outcome": 2, "missing_vix": 1}))

    def test_partition_result_rejects_incoherent_states(self) -> None:
        good = self._partition("test")
        fields = {name: getattr(good, name) for name in good.__dataclass_fields__}
        empty = score_comparison([], heuristic=[], frequency=[], logistic=[])

        cases: Dict[str, Dict[str, Any]] = {
            "scored_with_empty_metrics": {"comparison_metrics": empty},
            "empty_status_with_rows": {"comparison_status": STATUS_EMPTY},
            "unavailable_with_metrics": {"comparison_status": STATUS_COMPARISON_UNAVAILABLE, "comparison_unavailable_reasons": ("x",)},
            "unavailable_without_reasons": {"comparison_status": STATUS_COMPARISON_UNAVAILABLE, "comparison_metrics": None},
            "scored_with_reasons": {"comparison_unavailable_reasons": ("x",)},
            "unknown_status": {"comparison_status": "great"},
            "unknown_partition": {"partition": "train"},
            "rows_missing": {"per_origin_records": good.per_origin_records[:2]},
            "dates_missing": {"requested_dates": good.requested_dates[:2]},
            "available_with_reason": {"frequency_unavailable_reason": "no_fit_rows"},
            "unavailable_flag_while_scored": {"logistic_available": False, "logistic_unavailable_reason": "not_converged", "logistic_failure_stage": "fit"},
            "block_key_unknown": {"frequency_block": dict(good.frequency_block, extra=1)},
            # A block's cutoff is its partition's: one shifted session or a relabeled date is refused
            "frequency_cutoff_index_shifted": {"frequency_block": dict(good.frequency_block, cutoff_index=1)},
            "logistic_cutoff_date_relabeled": {"logistic_block": dict(good.logistic_block, cutoff_date="2022-01-04")},
            "fit_with_reason": {"logistic_block": dict(good.logistic_block, unavailable_reason="not_converged")},
            "unknown_reason": {
                "logistic_block": dict(_logistic_block("test", good.requested_indices, available=False), unavailable_reason="bad_luck"),
            },
            "stage_for_data_insufficiency": {
                "logistic_block": dict(
                    _logistic_block("test", good.requested_indices, available=False),
                    unavailable_reason="missing_training_classes",
                ),
            },
        }
        for name, changes in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    PartitionResult(**dict(fields, **changes))

    def test_origin_record_rejects_incoherent_scores(self) -> None:
        good = self._partition("test").per_origin_records[0]
        fields = {name: getattr(good, name) for name in good.__dataclass_fields__}

        cases: Dict[str, Dict[str, Any]] = {
            "scored_without_forecast": {"logistic": MethodOriginRecord("unavailable", None)},
            "infinite_with_value": {
                "heuristic": MethodOriginRecord("available", (0.6, 0.3, 0.1), "BEAR", 0.26, 0.5, "infinite"),
            },
            "finite_without_value": {
                "heuristic": MethodOriginRecord("available", (0.6, 0.3, 0.1), "BEAR", 0.26, None, "finite"),
            },
            "nan_brier": {
                "heuristic": MethodOriginRecord("available", (0.6, 0.3, 0.1), "BEAR", float("nan"), 0.5, "finite"),
            },
            "unknown_class": {"actual_class": "UP"},
            "compressed_horizon": {"maturity_index": good.origin_index + 19},
            "invented_direction": {"heuristic_expected_direction": "UP"},
            "out_of_range_probability": {
                "frequency": MethodOriginRecord("available", (1.5, 0.0, 0.0), "BEAR", 0.0, 0.0, "finite"),
            },
        }
        for name, changes in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    PerOriginRecord(**dict(fields, **changes))

        unscored = dict(fields, score_state="unscored")
        with self.assertRaises(ValueError):
            PerOriginRecord(**unscored)

    def test_study_result_rejects_unsupported_identity(self) -> None:
        fields = {name: getattr(self.study_result, name) for name in self.study_result.__dataclass_fields__}
        for name, changes in {
            "historical": {"data_kind": "historical"},
            "released": {"development_status": "released"},
            "protocol": {"protocol_id": "other"},
            "run_id_path": {"run_id": "../run"},
            "no_partition": {"partitions": {"test": self._partition("test")}},
        }.items():
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    StudyResult(**dict(fields, **changes))

    def test_summary_schema_is_closed_at_every_level(self) -> None:
        good = build_panel_summary(self.study_result)
        validate_summary_document(copy.deepcopy(good))

        def _mutated(mutate: Callable[[Dict[str, Any]], None]) -> Dict[str, Any]:
            doc = copy.deepcopy(good)
            mutate(doc)
            return doc

        test_metrics = lambda d: d["partitions"]["test"]["metrics"]  # noqa: E731
        heuristic = lambda d: test_metrics(d)["models"]["heuristic"]  # noqa: E731
        cases: Dict[str, Callable[[Dict[str, Any]], None]] = {
            "unknown_root": lambda d: d.update(extra=1),
            "missing_root": lambda d: d.pop("run_id"),
            "unsupported_schema": lambda d: d.update(schema_version="nivesh-evaluation-summary-v99"),
            "unsupported_protocol": lambda d: d.update(protocol_id="other"),
            "historical": lambda d: d.update(data_kind="historical"),
            "attribution_not_object": lambda d: d.update(dataset_attribution=[]),
            "attribution_unknown": lambda d: d["dataset_attribution"].update(extra=1),
            "attribution_not_synthetic": lambda d: d["dataset_attribution"].update(source_kind="exchange"),
            "replay_unknown": lambda d: d["replay_identity"].update(extra=1),
            "replay_bad_hash": lambda d: d["replay_identity"].update(model_sha256="xyz"),
            "inverted_coverage": lambda d: d["dataset_attribution"].update(coverage_start_date="2099-01-01"),
            "bad_gap_union": lambda d: d["admission_summary"].update(union_gap_count=5),
            "partition_unknown": lambda d: d["partitions"]["test"].update(extra=1),
            "partition_missing": lambda d: d["partitions"].pop("test"),
            "counts_bool": lambda d: d["partitions"]["test"]["counts"].update(eligible_count=True),
            "metric_status_contradiction": lambda d: test_metrics(d).update(status="empty"),
            "schema_not_string": lambda d: d.update(schema_version=["nivesh-evaluation-summary-v1"]),
            "protocol_not_string": lambda d: d.update(protocol_id={}),
            "number_beyond_binary64": lambda d: heuristic(d).update(mean_brier=10 ** 400),
            "nonfinite_metric": lambda d: heuristic(d).update(mean_brier=float("nan")),
            "infinite_metric": lambda d: heuristic(d).update(mean_brier=float("inf")),
            "string_metric": lambda d: heuristic(d).update(mean_brier="0.4000"),
            "infinite_state_with_mean": lambda d: heuristic(d).update(log_loss_state="infinite"),
            "confusion_mismatch": lambda d: heuristic(d)["confusion"].__setitem__(0, [0, 0, 0]),
            "recall_value_for_no_support": lambda d: test_metrics(d)["class_support"].__setitem__(0, 0),
            "bins_reordered": lambda d: heuristic(d)["reliability_bins"].reverse(),
            "bin_count_mismatch": lambda d: heuristic(d)["reliability_bins"][0].update(count=99, mean_probability=0.1, observed_frequency=0.0),
            "uncertainty_available": lambda d: d["uncertainty"].update(status="available"),
            "uncertainty_available_without_reason": lambda d: d["uncertainty"].update(status="available", reason=None),
            "uncertainty_free_text_reason": lambda d: d["uncertainty"].update(reason="comparison unavailable"),
            "uncertainty_interval": lambda d: d["uncertainty"].update(intervals=[]),
            "uncertainty_one_block": lambda d: d["uncertainty"].update(block_lengths=d["uncertainty"]["block_lengths"][:1]),
            "no_limitations": lambda d: d.update(limitations=[]),
        }
        for name, mutate in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    validate_summary_document(_mutated(mutate))

    def test_result_schema_is_closed_at_every_level(self) -> None:
        good = build_result_document(self.study_result)

        def _mutated(mutate: Callable[[Dict[str, Any]], None]) -> Dict[str, Any]:
            doc = copy.deepcopy(good)
            mutate(doc)
            return doc

        row = lambda d: d["partitions"]["test"]["per_origin_records"][0]  # noqa: E731
        cases: Dict[str, Callable[[Dict[str, Any]], None]] = {
            "unknown_root": lambda d: d.update(extra=1),
            "bad_schema": lambda d: d.update(schema_version="other"),
            "input_identity_unknown": lambda d: d["input_identities"]["nifty"].update(extra=1),
            "input_not_synthetic": lambda d: d["input_identities"]["vix"].update(source_kind="exchange"),
            "absolute_source_key": lambda d: d["source_identities"].update({"C:\\x.py": dict(FILE_IDENTITY)}),
            "runtime_missing": lambda d: d["runtime_identities"].pop("node_version"),
            "build_exit_bool": lambda d: d["build_identity"].update(compiler_exit=False),
            "row_key_differs": lambda d: row(d).update(origin_index=1),
            "row_unknown": lambda d: row(d).update(extra=1),
            "row_method_unknown": lambda d: row(d)["frequency"].update(extra=1),
            "warning_unknown": lambda d: d["warnings"][0].update(extra=1),
            "warning_lineno_bool": lambda d: d["warnings"][0].update(lineno=True),
        }
        for name, mutate in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    validate_result_document(_mutated(mutate))

    def test_frozen_admission_is_closed_with_native_types(self) -> None:
        """Every substitution here is value-equal or structural, so only type or shape can reject it."""
        good = copy.deepcopy(ADMISSION)
        good.update(
            missing_vix_gap_positions=[2],
            missing_vix_gap_count=1,
            union_gap_positions=[2],
            union_gap_count=1,
        )
        validate_admission_document(copy.deepcopy(good), "admission")

        def _set(*path_and_value: Any) -> Callable[[Dict[str, Any]], None]:
            *path, value = path_and_value

            def _apply(doc: Dict[str, Any]) -> None:
                target = doc
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value

            return _apply

        cases: Dict[str, Callable[[Dict[str, Any]], None]] = {
            "union_count_true": _set("union_gap_count", True),
            "missing_count_float": _set("missing_vix_gap_count", 1.0),
            "warmup_count_false": _set("warmup_gap_count", False),
            "span_float": _set("mature_test_span_count", 2.0),
            "start_true": _set("mature_test_start_index", True),
            "end_float": _set("mature_test_end_index", 3.0),
            "position_float": _set("union_gap_positions", [2.0]),
            "reason_position_float": _set("missing_vix_gap_positions", [2.0]),
            "nested_bytes_float": _set("inputs", "nifty", "raw_byte_count", 100.0),
            "nested_records_float": _set("inputs", "vix", "record_count", 3.0),
            "nested_sessions_float": _set("inputs", "calendar", "session_count", 3.0),
            "axis_sessions_float": _set("axis", "session_count", 3.0),
            "unknown_root": _set("extra", 1),
            "unknown_nested": _set("axis", "extra", 1),
            "unknown_nested_input": _set("inputs", "calendar", "extra", 1),
            "missing_root": lambda d: d.pop("gap_digest"),
            "missing_nested": lambda d: d["inputs"].pop("vix"),
            "not_object": lambda d: d.update(inputs=[]),
            "wrong_schema": _set("schema_version", "nivesh-study-admission-v2"),
            "historical": _set("data_kind", "historical"),
            "wrong_protocol": _set("protocol_id", "other"),
            "wrong_rule": _set("date_selection_rule", "looked_at_results"),
            "wrong_policy": _set("policy", "drop_gaps"),
            "bad_digest": _set("gap_digest", "not-hex"),
            "inverted_cutoffs": _set("test_start", "2021-01-01"),
            "span_beyond_axis": lambda d: d.update(mature_test_end_index=4, mature_test_span_count=3),
            "position_outside_span": lambda d: d.update(missing_vix_gap_positions=[0], union_gap_positions=[0]),
            "count_differs_from_list": _set("union_gap_count", 2),
            "union_is_not_the_reasons": lambda d: d.update(warmup_gap_positions=[1], warmup_gap_count=1),
            "positions_unordered": lambda d: d.update(
                missing_vix_gap_positions=[2, 1], missing_vix_gap_count=2, union_gap_positions=[2, 1], union_gap_count=2
            ),
        }
        for name, mutate in cases.items():
            doc = copy.deepcopy(good)
            mutate(doc)
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    validate_admission_document(doc, "admission")

    def test_result_rejections_name_their_cause(self) -> None:
        """Each case matches its own message, so a neighboring guard cannot satisfy the oracle."""
        good = build_result_document(self.study_result)
        validate_result_document(copy.deepcopy(good))

        def _row(doc: Dict[str, Any]) -> Dict[str, Any]:
            return doc["partitions"]["test"]["per_origin_records"][0]

        def _logistic(doc: Dict[str, Any]) -> Dict[str, Any]:
            return doc["comparator_metadata"]["logistic"]

        def _zero_actual_with_finite_loss(doc: Dict[str, Any]) -> None:
            _row(doc)["frequency"].update(probabilities=[0.0, 1.0, 0.0], predicted_class="NEUTRAL")

        def _positive_actual_with_infinite_loss(doc: Dict[str, Any]) -> None:
            _row(doc)["heuristic"].update(log_loss=None, log_loss_state="infinite")

        cases: Dict[str, Any] = {
            "admission_unknown_key": (lambda d: d["admission"].update(extra=1), "admission: key mismatch"),
            "admission_nested_float": (
                lambda d: d["admission"]["inputs"]["nifty"].update(raw_byte_count=100.0),
                "raw_byte_count: expected non-boolean integer",
            ),
            "admission_partial": (lambda d: d["admission"].pop("axis"), "admission: key mismatch"),
            "comparator_unknown_top": (lambda d: d["comparator_metadata"].update(extra={}), "comparator_metadata: key mismatch"),
            "comparator_missing_method": (lambda d: d["comparator_metadata"].pop("logistic"), "comparator_metadata: key mismatch"),
            "frequency_unknown_key": (lambda d: d["comparator_metadata"]["frequency"].update(extra=1), "frequency: key mismatch"),
            "frequency_alpha_bool": (lambda d: d["comparator_metadata"]["frequency"].update(alpha=True), "alpha: expected finite number"),
            "max_iter_true": (lambda d: _logistic(d)["configuration"].update(max_iter=True), "max_iter: expected non-boolean integer"),
            "max_iter_float": (lambda d: _logistic(d)["configuration"].update(max_iter=2000.0), "max_iter: expected non-boolean integer"),
            "verbose_false": (lambda d: _logistic(d)["configuration"].update(verbose=False), "verbose: expected non-boolean integer"),
            "fit_intercept_int": (lambda d: _logistic(d)["configuration"].update(fit_intercept=1), "fit_intercept: expected boolean"),
            "configuration_unknown": (lambda d: _logistic(d)["configuration"].update(extra=1), "configuration: key mismatch"),
            "horizon_float": (lambda d: _logistic(d).update(horizon_sessions=20.0), "horizon_sessions: horizon must be"),
            "dependency_pair_short": (lambda d: _logistic(d).update(dependency_versions=[["numpy"]]), "dependency_versions"),
            "regime_order_changed": (lambda d: _logistic(d)["regime_order"].reverse(), "regime_order: fixed regime order"),
            "zero_vector": (lambda d: _row(d)["heuristic"].update(probabilities=[0, 0, 0]), "must sum to 1"),
            "sum_off_beyond_tolerance": (lambda d: _row(d)["heuristic"].update(probabilities=[0.6, 0.3, 0.1 + 2e-12]), "must sum to 1"),
            "fit_probabilities_off": (
                lambda d: d["partitions"]["test"]["frequency_block"]["fit"].update(probabilities=[0.5, 0.5, 0.5]),
                "must sum to 1",
            ),
            "predicted_not_first_max": (lambda d: _row(d)["heuristic"].update(predicted_class="BULL"), "first maximum"),
            "negative_brier": (lambda d: _row(d)["heuristic"].update(brier=-0.1), "brier: loss out of range"),
            "brier_above_ceiling": (lambda d: _row(d)["heuristic"].update(brier=2.5), "brier: loss out of range"),
            "negative_log_loss": (lambda d: _row(d)["heuristic"].update(log_loss=-0.1), "log_loss: loss out of range"),
            "zero_actual_finite": (_zero_actual_with_finite_loss, "cannot have finite log loss"),
            "positive_actual_infinite": (_positive_actual_with_infinite_loss, "requires a zero actual-class"),
            "forecast_state_contradicts_method": (
                lambda d: _row(d)["logistic"].update(
                    forecast_state="unavailable", probabilities=None, predicted_class=None, brier=None, log_loss=None, log_loss_state=None
                ),
                "needs an available forecast",
            ),
            "block_requested_differs": (
                lambda d: d["partitions"]["test"]["frequency_block"].update(requested_indices=[0, 1], prediction_count=2),
                "block partition or requested keys",
            ),
            "block_partition_differs": (
                lambda d: d["partitions"]["test"]["logistic_block"].update(partition="development"),
                "block partition or requested keys",
            ),
            "available_count_contradicts_state": (
                lambda d: d["partitions"]["test"]["counts"]["model_available_counts"].update(frequency=0),
                "expected 3 for its method state",
            ),
            "input_warning_line_int": (lambda d: d["input_warnings"][0].update(line=5), "line: expected non-empty string"),
            "input_warning_raw_number": (lambda d: d["input_warnings"][0].update(raw_value=5), "raw_value: expected non-empty string"),
            "input_warning_unknown": (lambda d: d["input_warnings"][0].update(extra=1), "input_warnings[0]: key mismatch"),
            "input_warning_missing": (lambda d: d["input_warnings"][0].pop("field"), "input_warnings[0]: key mismatch"),
            "input_warnings_not_list": (lambda d: d.update(input_warnings={}), "input_warnings: expected array"),
        }
        for name, (mutate, expected) in cases.items():
            doc = copy.deepcopy(good)
            mutate(doc)
            with self.subTest(case=name):
                with self.assertRaises(ValueError) as ctx:
                    validate_result_document(doc)
                self.assertIn(expected, str(ctx.exception))

    def test_unavailable_block_state_must_match_method_state(self) -> None:
        good = build_result_document(self._study_result(test=self._unavailable_partition("test", cutoff_index=SYNTHETIC_TEST_CUTOFF)))
        validate_result_document(copy.deepcopy(good))

        cases: Dict[str, Callable[[Dict[str, Any]], None]] = {
            "reason_differs": lambda d: d["partitions"]["test"]["logistic_block"].update(
                unavailable_reason="nonfinite_model_state"
            ),
            "stage_differs": lambda d: d["partitions"]["test"]["logistic_block"].update(failure_stage="scaler"),
            "row_keeps_forecast_of_unavailable_method": lambda d: d["partitions"]["test"]["per_origin_records"][0]["logistic"].update(
                forecast_state="available", probabilities=[0.5, 0.25, 0.25]
            ),
        }
        for name, mutate in cases.items():
            doc = copy.deepcopy(good)
            mutate(doc)
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    validate_result_document(doc)

    def test_result_accepts_boundary_forms(self) -> None:
        """Rejections above must not reach the accepted conservation, array and signed-zero forms."""
        good = build_result_document(self.study_result)
        row = lambda d: d["partitions"]["test"]["per_origin_records"][0]  # noqa: E731
        cases: Dict[str, Callable[[Dict[str, Any]], None]] = {
            "sum_inside_tolerance": lambda d: row(d)["heuristic"].update(probabilities=[0.6, 0.3, 0.1 + 5e-13]),
            "integer_one_hot": lambda d: row(d)["frequency"].update(probabilities=[1, 0, 0]),
            "signed_zero_component": lambda d: row(d)["frequency"].update(probabilities=[1.0, -0.0, 0.0]),
            "signed_zero_losses": lambda d: row(d)["frequency"].update(brier=-0.0, log_loss=-0.0),
            "brier_at_ceiling": lambda d: row(d)["heuristic"].update(brier=2.0),
            "large_finite_log_loss": lambda d: row(d)["heuristic"].update(log_loss=744.44),
            "first_of_tied_maxima": lambda d: row(d)["heuristic"].update(probabilities=[0.4, 0.4, 0.2], predicted_class="BEAR"),
            "warning_raw_value_empty": lambda d: d["input_warnings"][0].update(raw_value=""),
            "warning_raw_value_null": lambda d: d["input_warnings"][0].update(raw_value=None),
            "no_input_warnings": lambda d: d.update(input_warnings=[]),
        }
        for name, mutate in cases.items():
            doc = parse_strict_json_bytes(serialize_strict_json(good))
            mutate(doc)
            with self.subTest(case=name):
                validate_result_document(parse_strict_json_bytes(serialize_strict_json(doc)))

    def test_input_warnings_stay_private_in_order_with_repeats(self) -> None:
        repeated = dict(INPUT_WARNING)
        other = dict(INPUT_WARNING, line="line 9", raw_value=None)
        fields = {name: getattr(self.study_result, name) for name in self.study_result.__dataclass_fields__}
        result = StudyResult(**dict(fields, input_warnings=(repeated, other, dict(repeated))))

        persisted = parse_strict_json_bytes(serialize_strict_json(build_result_document(result)))
        self.assertEqual(persisted["input_warnings"], [repeated, other, repeated])

        for name, text in (
            ("summary", serialize_strict_json(build_panel_summary(result)).decode("utf-8")),
            ("predictions", json.dumps(build_predictions_document(result))),
            ("report", render_report_markdown(result)),
        ):
            with self.subTest(artifact=name):
                self.assertNotIn("private-open-cell", text)
                self.assertNotIn("nifty.csv", text)

    def test_run_manifest_generation_and_self_exclusion(self) -> None:
        """Verifies run-manifest.json tracks required artifacts and excludes self."""
        summary_bytes = serialize_strict_json(build_panel_summary(self.study_result))
        manifest = self._manifest_doc(summary_bytes)

        self.assertEqual(manifest["schema_version"], SCHEMA_VERSION_RUN_MANIFEST_V2)
        self.assertTrue(manifest["completed"])
        art_paths = [a["path"] for a in manifest["artifacts"]]
        self.assertNotIn("run-manifest.json", art_paths)
        self.assertEqual(set(art_paths), REQUIRED_MANIFEST_ARTIFACTS_V2)
        self.assertEqual(manifest["input_identities"]["nifty"]["sha256"], "B" * 64)
        self.assertEqual(manifest["runtime_identities"]["node_version"], "v22.0.0")

        # Replay native evidence and the private result are required entries, not optional extras
        for name in ("result.json", "replay-response.json", "replay-stderr.log", "replay-invocation.json"):
            self.assertIn(name, art_paths)

    def test_manifest_requires_complete_exact_entries(self) -> None:
        summary_bytes = serialize_strict_json(build_panel_summary(self.study_result))
        good = self._manifest_doc(summary_bytes)

        def _mutated(mutate: Callable[[Dict[str, Any]], None]) -> Dict[str, Any]:
            doc = copy.deepcopy(good)
            mutate(doc)
            return doc

        cases: Dict[str, Callable[[Dict[str, Any]], None]] = {
            "entry_without_hash": lambda d: d["artifacts"][0].pop("sha256"),
            "entry_without_bytes": lambda d: d["artifacts"][0].pop("bytes"),
            "entry_unknown_key": lambda d: d["artifacts"][0].update(extra=1),
            "entry_bool_bytes": lambda d: d["artifacts"][0].update(bytes=True),
            "entry_bad_hash": lambda d: d["artifacts"][0].update(sha256="xyz"),
            "entry_escaping_path": lambda d: d["artifacts"][0].update(path="../config.json"),
            "entry_absolute_path": lambda d: d["artifacts"][0].update(path="D:\\x\\config.json"),
            "duplicate_entry": lambda d: d["artifacts"].append(dict(d["artifacts"][0])),
            "missing_entry": lambda d: d["artifacts"].pop(),
            "unexpected_entry": lambda d: d["artifacts"].append({"path": "extra.json", "bytes": 1, "sha256": "A" * 64}),
            "not_completed": lambda d: d.update(completed=False),
            "completed_not_boolean": lambda d: d.update(completed=1),
            "unknown_root": lambda d: d.update(extra=1),
            "missing_input_identity": lambda d: d.pop("input_identities"),
            "unsupported_summary_schema": lambda d: d.update(summary_schema_version="v99"),
            "historical": lambda d: d.update(data_kind="historical"),
        }
        for name, mutate in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    validate_run_manifest_document(_mutated(mutate))

    def test_checked_promotion_verification(self) -> None:
        """Verifies promotion binding between panel-summary.json, run-manifest.json, and descriptor."""
        summary_bytes, manifest_bytes = self._bound_bytes()
        desc = self._descriptor(summary_bytes, manifest_bytes)

        # Happy path
        ok, msg = verify_promotion_binding(summary_bytes, manifest_bytes, desc)
        self.assertTrue(ok, msg)

        # Failure case 1: Incomplete manifest missing report.md
        manifest_doc = json.loads(manifest_bytes.decode("utf-8"))
        bad_man_doc = dict(manifest_doc)
        bad_man_doc["artifacts"] = [a for a in manifest_doc["artifacts"] if a["path"] != "report.md"]
        bad_man_bytes = serialize_strict_json(bad_man_doc)
        ok, msg = verify_promotion_binding(summary_bytes, bad_man_bytes, desc)
        self.assertFalse(ok)
        self.assertIn("missing required artifact 'report.md'", msg)

        # Failure case 2: Summary hash mismatch
        tampered_summary = summary_bytes + b" "
        ok, msg = verify_promotion_binding(tampered_summary, manifest_bytes, desc)
        self.assertFalse(ok)

        # Failure case 3: Descriptor run_id mismatch
        bad_desc = self._descriptor(summary_bytes, manifest_bytes, run_id="different-run-id")
        ok, msg = verify_promotion_binding(summary_bytes, manifest_bytes, bad_desc)
        self.assertFalse(ok)
        self.assertIn("does not match", msg)

        # A candidate descriptor derived from the real bytes is the same binding
        self.assertEqual(build_candidate_descriptor(summary_bytes, manifest_bytes), desc)

        # Promotion cannot proceed without a descriptor
        ok, msg = verify_promotion_binding(summary_bytes, manifest_bytes, None)
        self.assertFalse(ok)

    def test_descriptor_fields_are_each_bound_in_isolation(self) -> None:
        """Every case keeps correct hashes, so only the named descriptor field can reject it."""
        summary_bytes, manifest_bytes = self._bound_bytes()

        cases = {
            "study_id": ({"study_id": "other-study"}, "study_id"),
            "protocol_id": ({"protocol_id": "other-protocol"}, "protocol_id"),
            "summary_schema_version": ({"summary_schema_version": "nivesh-evaluation-summary-v99"}, "summary_schema_version"),
            "coverage_end_date": ({"coverage_end_date": "2099-12-31"}, "coverage_end_date"),
            "summary_bytes": ({"summary_bytes": len(summary_bytes) + 1}, "summary_bytes"),
            "summary_sha256": ({"summary_sha256": "9" * 64}, "summary_sha256"),
            "manifest_bytes": ({"manifest_bytes": len(manifest_bytes) + 1}, "manifest_bytes"),
            "manifest_sha256": ({"manifest_sha256": "9" * 64}, "manifest_sha256"),
        }
        for name, (changes, expected_text) in cases.items():
            with self.subTest(field=name):
                ok, msg = verify_promotion_binding(summary_bytes, manifest_bytes, self._descriptor(summary_bytes, manifest_bytes, **changes))
                self.assertFalse(ok)
                self.assertIn(expected_text, msg)

    def test_summary_and_manifest_identities_must_agree(self) -> None:
        """Each manifest is internally valid and hash-bound, so only the relation can reject it."""
        summary_bytes = serialize_strict_json(build_panel_summary(self.study_result))
        cases = {
            "run_id": {"run_id": "other-run"},
            "study_id": {"study_id": "other-study"},
            "coverage_start_date": {"coverage_start_date": self.d1},
            "coverage_end_date": {"coverage_end_date": self.d1},
        }
        for name, changes in cases.items():
            with self.subTest(field=name):
                manifest_bytes = serialize_strict_json(self._manifest_doc(summary_bytes, **changes))
                ok, msg = verify_completion_binding(summary_bytes, manifest_bytes)
                self.assertFalse(ok)
                self.assertIn(name, msg)

    def test_completion_binding_parses_strictly(self) -> None:
        summary_bytes, manifest_bytes = self._bound_bytes()

        ok, msg = verify_completion_binding(summary_bytes, b'{"schema_version": "a", "schema_version": "b"}')
        self.assertFalse(ok)
        self.assertIn("Malformed run-manifest.json", msg)

        ok, _ = verify_completion_binding(b'{"mean_brier": NaN}', manifest_bytes)
        self.assertFalse(ok)

        ok, _ = verify_completion_binding(b"\xff\xfe", manifest_bytes)
        self.assertFalse(ok)

        # A schema-valid summary alone is not completion: a stale manifest entry fails
        doc = json.loads(manifest_bytes.decode("utf-8"))
        next(a for a in doc["artifacts"] if a["path"] == "panel-summary.json")["sha256"] = "9" * 64
        ok, msg = verify_completion_binding(summary_bytes, serialize_strict_json(doc))
        self.assertFalse(ok)
        self.assertIn("SHA-256 mismatch", msg)

    def _write_valid_run_dir(self, run_dir: Path, *, comparison_unavailable: bool = False) -> bytes:
        """
        Writes one coherent completed run, so a relation test can break exactly one fact.

        Daily axis N=247, development start D=223 and test start T=224: the mature span is
        [224, 227), filled by n=3 origins whose maturity index stays on the axis. n is below every
        floor. The development pool [200, 202] and refit pool [200, 203] are past the 200-row
        warmup and mature strictly before their cutoffs; 203 + 20 = 223 sits one below T.
        """
        d_idx, t_idx = RUN_DEVELOPMENT_START, RUN_DEVELOPMENT_START + 1
        axis = tuple(self.d0 + datetime.timedelta(days=i) for i in range(t_idx + 23))
        origins = [
            EvaluationOrigin(origin_index=t_idx, origin_date=axis[t_idx], actual_class=OUTCOME_CLASS_BEAR),
            EvaluationOrigin(origin_index=t_idx + 1, origin_date=axis[t_idx + 1], actual_class=OUTCOME_CLASS_NEUTRAL),
            EvaluationOrigin(origin_index=t_idx + 2, origin_date=axis[t_idx + 2], actual_class=OUTCOME_CLASS_BULL),
        ]
        keys = tuple(RequestedKey(o.origin_index, o.origin_date) for o in origins)

        def _predictions(source: Sequence[DummyPrediction]) -> List[DummyPrediction]:
            return [DummyPrediction(o.origin_index, o.origin_date, p.probabilities) for o, p in zip(origins, source)]

        rows: Optional[Dict[str, Any]] = None
        if comparison_unavailable:
            test_part = self._unavailable_partition("test", origins, cutoff_index=t_idx, fitting=RUN_REFIT_POOL)
            status = "comparison_unavailable"
            available = {"heuristic": True, "frequency": True, "logistic": False}
        else:
            comparison = score_comparison(
                origins,
                heuristic=_predictions(self.h_preds),
                frequency=_predictions(self.f_preds),
                logistic=_predictions(self.l_preds),
            )
            test_part = self._partition("test", comparison, origins, cutoff_index=t_idx, fitting=RUN_REFIT_POOL)
            status = "scored"
            available = {"heuristic": True, "frequency": True, "logistic": True}
            rows = {
                name: tuple(BrierRow(r.origin_index, r.origin_date, getattr(r, name).brier) for r in test_part.per_origin_records)
                for name in ("heuristic", "frequency", "logistic")
            }
        req_temp = UncertaintyRequest(
            axis_dates=axis,
            test_start_index=t_idx,
            requested_keys=keys,
            comparison_status=status,
            method_available=available,
            method_rows=rows,
            union_gap_positions=(),
        )
        raw_input = serialize_uncertainty_input(req_temp)
        input_id = {"raw_byte_count": len(raw_input), "sha256": hashlib.sha256(raw_input).hexdigest().upper()}
        res = compute_uncertainty(
            dataclasses.replace(req_temp, input_identity=input_id),
            max_resample_positions=1000,
            runtime_identity={
                "python_implementation": RUNTIME_IDENTITIES["python_implementation"],
                "python_version": RUNTIME_IDENTITIES["python_version"],
            },
        )
        u_block = UncertaintyBlock.from_result(res)

        adm_doc = copy.deepcopy(ADMISSION)
        adm_doc["axis"] = {"session_count": len(axis), "first_date": axis[0].isoformat(), "last_date": axis[-1].isoformat()}
        adm_doc.update(
            development_start=axis[d_idx].isoformat(),
            test_start=axis[t_idx].isoformat(),
            mature_test_start_index=t_idx,
            mature_test_end_index=t_idx + 3,
            mature_test_span_count=3,
        )
        admission_bytes = serialize_strict_json(adm_doc)
        config_bytes = serialize_strict_json(
            {
                "workspace_root": SAVED_WORKSPACE_LABEL,
                "timeout_seconds": SAVED_TIMEOUT_SECONDS,
                "tools": _saved_tools(),
                "uncertainty": {"protocol_id": UNCERTAINTY_PROTOCOL_ID, "max_resample_positions": 1000},
                "runtime": {
                    "python_version": RUNTIME_IDENTITIES["python_version"],
                    "python_implementation": RUNTIME_IDENTITIES["python_implementation"],
                    "dependency_versions": dict(RUNTIME_IDENTITIES["dependency_versions"]),
                },
                "source_modules": SOURCE_IDENTITIES,
            }
        )
        config_id = self._bytes_identity(config_bytes)
        admission_id = self._bytes_identity(admission_bytes)

        empty = score_comparison([], heuristic=[], frequency=[], logistic=[])
        sr = dataclasses.replace(
            self._study_result(
                development=self._partition("development", empty, [], cutoff_index=d_idx, fitting=RUN_DEVELOPMENT_POOL),
                test=test_part,
                uncertainty=u_block,
            ),
            coverage_end_date=axis[-1],
            development_start=axis[d_idx],
            test_start=axis[t_idx],
            admission_inventory=adm_doc,
            config_identity=config_id,
            admission_identity=admission_id,
            replay_identity=_captured_replay_identity(),
        )
        summary_bytes = serialize_strict_json(build_panel_summary(sr))
        result_bytes = serialize_strict_json(build_result_document(sr))
        predictions_bytes = serialize_strict_json(build_predictions_document(sr))
        report_bytes = render_report_markdown(sr).encode("utf-8")

        diag_doc = build_uncertainty_diagnostics_document(res.diagnostics)
        raw_diag = serialize_strict_json(diag_doc)

        file_map = {
            "panel-summary.json": summary_bytes,
            "result.json": result_bytes,
            "predictions.json": predictions_bytes,
            "report.md": report_bytes,
            "admission.json": admission_bytes,
            "uncertainty-input.json": raw_input,
            "uncertainty-diagnostics.json": raw_diag,
            "config.json": config_bytes,
            **_replay_files(),
        }
        artifacts = []
        for name in sorted(REQUIRED_MANIFEST_ARTIFACTS_V2):
            data = file_map[name]
            (run_dir / name).write_bytes(data)
            artifacts.append({"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest().upper()})
        manifest_path = run_dir / "run-manifest.json"
        manifest_path.write_bytes(
            serialize_strict_json(
                self._manifest_doc(
                    summary_bytes,
                    artifacts=artifacts,
                    coverage_end_date=axis[-1],
                    config_identity=config_id,
                    admission_identity=admission_id,
                )
            )
        )
        return summary_bytes

    @staticmethod
    def _canonical_input(doc: Mapping[str, Any]) -> bytes:
        text = json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
        return text.encode("ascii") + b"\n"

    def _replace_artifact(self, run_dir: Path, name: str, data: bytes) -> None:
        """
        Replaces one artifact and recomputes every digest that names it, directly or through
        another artifact, so no hash failure can stand in for the relation under test.
        """
        changed = {name: data}
        if name == "uncertainty-input.json":
            diagnostics = parse_strict_json_bytes((run_dir / "uncertainty-diagnostics.json").read_bytes())
            diagnostics["input_identity"] = self._bytes_identity(data)
            changed["uncertainty-diagnostics.json"] = serialize_strict_json(diagnostics)

        manifest = parse_strict_json_bytes((run_dir / "run-manifest.json").read_bytes())
        identity_field = {"config.json": "config_identity", "admission.json": "admission_identity"}.get(name)
        if identity_field is not None:
            result = parse_strict_json_bytes((run_dir / "result.json").read_bytes())
            result[identity_field] = self._bytes_identity(data)
            manifest[identity_field] = self._bytes_identity(data)
            changed["result.json"] = serialize_strict_json(result)

        for artifact, content in changed.items():
            (run_dir / artifact).write_bytes(content)
            entry = next(a for a in manifest["artifacts"] if a["path"] == artifact)
            entry.update(bytes=len(content), sha256=hashlib.sha256(content).hexdigest().upper())
        (run_dir / "run-manifest.json").write_bytes(serialize_strict_json(manifest))

    def _edit_json_artifact(self, run_dir: Path, name: str, mutate: Callable[[Dict[str, Any]], None]) -> None:
        doc = parse_strict_json_bytes((run_dir / name).read_bytes())
        mutate(doc)
        data = self._canonical_input(doc) if name == "uncertainty-input.json" else serialize_strict_json(doc)
        self._replace_artifact(run_dir, name, data)

    def test_semantic_relations_reject_each_rehashed_contradiction(self) -> None:
        """
        Every digest is recomputed, so each case reaches the relation it names. The shared check
        runs with and without the completed-run wrapper: study.py calls it before the manifest.
        """
        INPUT, DIAG, RESULT, SUMMARY = "uncertainty-input.json", "uncertainty-diagnostics.json", "result.json", "panel-summary.json"
        ADMISSION_FILE, CONFIG = "admission.json", "config.json"
        uncertainty_module_path = "research/prediction_eval/uncertainty.py"

        def _on_uncertainty(doc: Dict[str, Any], **changes: Any) -> None:
            doc["uncertainty"].update(changes)

        def _shift_point(doc: Dict[str, Any]) -> None:
            # 2**-40 (about 9.1e-13) stays inside the public paired-point tolerance, so only the
            # private equality and exact saved-loss relations can see it
            doc["uncertainty"]["point_differences"][0]["point_difference"] += 2.0 ** -40

        def _claim_unavailable(doc: Dict[str, Any]) -> None:
            block = doc["uncertainty"]
            block["reason"] = "comparison_unavailable"
            for entry in block["point_differences"]:
                entry["point_difference"] = None
            for view in block["block_lengths"]:
                view["reason"] = "comparison_unavailable"

        def _input_rows(doc: Dict[str, Any], name: str, pos: int, value: Any) -> None:
            doc["method_rows"][name][pos]["brier"] = value

        test_start = RUN_DEVELOPMENT_START + 1
        # A valid but false cutoff: after development start, one session past the true test start
        next_test_day = (self.d0 + datetime.timedelta(days=test_start + 1)).isoformat()

        def _drop_last_key(doc: Dict[str, Any]) -> None:
            doc["requested_keys"].pop()
            for rows in doc["method_rows"].values():
                rows.pop()
            doc["union_gap_positions"] = [test_start + 2]

        def _move_test_start(doc: Dict[str, Any]) -> None:
            doc["test_start_index"] = test_start - 1
            doc["union_gap_positions"] = [test_start - 1]

        def _summary_test_start_moved(doc: Dict[str, Any]) -> None:
            # The TEST cutoff date moves with the declared start, so the portable relations still
            # hold and only the projection of result.json can object
            doc["chronological_cutoffs"]["test_start"] = next_test_day
            doc["partitions"]["test"]["cutoff_date"] = next_test_day

        def _move_test_cutoff(doc: Dict[str, Any]) -> None:
            # Blocks move with their partition, so only the axis relation can object
            for key in ("", "frequency_block", "logistic_block"):
                (doc["partitions"]["test"][key] if key else doc["partitions"]["test"]).update(cutoff_index=test_start + 1)

        def _input_says_unavailable(doc: Dict[str, Any]) -> None:
            doc["comparison_status"] = "comparison_unavailable"
            doc["method_available"]["frequency"] = False
            doc["method_rows"] = None

        cases: List[Any] = [
            ("axis_last_date", [(INPUT, lambda d: d["axis_dates"].__setitem__(-1, "2023-03-01"))], "admission axis"),
            ("axis_first_date", [(INPUT, lambda d: d["axis_dates"].__setitem__(0, "2021-12-01"))], "admission axis"),
            ("axis_longer", [(INPUT, lambda d: d["axis_dates"].append("2023-03-01"))], "union_gap_positions"),
            ("test_start_moved", [(INPUT, _move_test_start)], "test_start_index"),
            ("comparison_status", [(INPUT, _input_says_unavailable)], "comparison_status"),
            ("key_removed", [(INPUT, _drop_last_key)], "union_gap_positions"),
            ("loss_changed", [(INPUT, lambda d: _input_rows(d, "heuristic", 0, 0.125))], "loss mismatch"),
            ("loss_signed_zero", [(INPUT, lambda d: _input_rows(d, "frequency", 0, -0.0))], "loss mismatch"),
            ("nested_extra_key", [(INPUT, lambda d: d["requested_keys"][0].update(extra=1))], "key mismatch"),
            ("rows_null_while_scored", [(INPUT, lambda d: d.update(method_rows=None))], "scored comparison requires method_rows"),
            ("extra_tail_row", [(INPUT, lambda d: d["method_rows"]["heuristic"].append(dict(d["method_rows"]["heuristic"][-1])))], "must match requested_keys"),
            ("required_positions", [(DIAG, lambda d: d["resource"].update(required_positions=1))], "required_positions"),
            ("cap_differs_from_config", [(DIAG, lambda d: d["resource"].update(max_resample_positions=999))], "max_resample_positions"),
            ("cap_zero", [(DIAG, lambda d: d["resource"].update(max_resample_positions=0))], "max_resample_positions"),
            ("unused_random_calls", [(DIAG, lambda d: d["lengths"][0].update(random_calls=1))], "zero counters"),
            ("unused_randrange_calls", [(DIAG, lambda d: d["lengths"][2].update(randrange_calls=1))], "zero counters"),
            ("runtime_version", [(DIAG, lambda d: d["runtime_identity"].update(python_version="0.0.0"))], "python_version"),
            ("input_identity", [(DIAG, lambda d: d["input_identity"].update(sha256="F" * 64))], "input_identity"),
            ("summary_only_point", [(SUMMARY, _shift_point)], "summary.uncertainty does not match result.uncertainty"),
            ("both_points", [(SUMMARY, _shift_point), (RESULT, _shift_point)], "full-cohort mean"),
            # These two contradict the summary's own TEST blocks, so the public validator names
            # them. The private count and reason guards have their own discriminating test below
            # (test_private_uncertainty_guards_reject_a_valid_summary_that_disagrees_with_the_saved_cohort).
            (
                "both_counts",
                [(SUMMARY, lambda d: _on_uncertainty(d, n=2, mature_span_count=2)), (RESULT, lambda d: _on_uncertainty(d, n=2, mature_span_count=2))],
                "summary.uncertainty: n and mature_span_count must be the TEST requested_count 3",
            ),
            ("both_reason", [(SUMMARY, _claim_unavailable), (RESULT, _claim_unavailable)], "summary.uncertainty.reason: must be"),
            ("embedded_admission", [(RESULT, lambda d: d["admission"]["axis"].update(last_date="2022-03-01"))], "result.admission"),
            ("admission_file", [(ADMISSION_FILE, lambda d: d.update(gap_digest="E" * 64))], "result.admission"),
            ("result_test_cutoff", [(RESULT, _move_test_cutoff)], "test_start_index"),
            (
                "row_maturity_date",
                [(RESULT, lambda d: d["partitions"]["test"]["per_origin_records"][0].update(maturity_date="2022-03-01"))],
                "disagrees with persisted row",
            ),
            ("result_source_member", [(RESULT, lambda d: d["source_identities"].pop(uncertainty_module_path))], "closed set"),
            ("config_cap", [(CONFIG, lambda d: d["uncertainty"].update(max_resample_positions=2000))], "max_resample_positions"),
            ("config_protocol", [(CONFIG, lambda d: d["uncertainty"].update(protocol_id="other"))], "protocol_id"),
            ("config_without_uncertainty", [(CONFIG, lambda d: d.pop("uncertainty"))], "config.uncertainty"),
            ("config_runtime", [(CONFIG, lambda d: d["runtime"].update(python_version="0.0.0"))], "config.runtime"),
            ("config_source_member", [(CONFIG, lambda d: d["source_modules"].pop(uncertainty_module_path))], "closed set"),
            ("config_source_hash", [(CONFIG, lambda d: d["source_modules"][uncertainty_module_path].update(sha256="9" * 64))], "result.source_identities"),
            # The summary is a fixed projection of result.json, so a valid but false aggregate cannot verify
            ("summary_cutoff", [(SUMMARY, _summary_test_start_moved)], "panel-summary.json"),
            ("summary_input_digest", [(SUMMARY, lambda d: d["provenance_identity"].update(nifty_input_sha256="9" * 64))], "panel-summary.json"),
            ("summary_gap_digest", [(SUMMARY, lambda d: d["admission_summary"].update(gap_digest="E" * 64))], "panel-summary.json"),
            ("summary_limitation_dropped", [(SUMMARY, lambda d: d["limitations"].pop())], "panel-summary.json"),
        ]
        for name, edits, expected in cases:
            with tempfile.TemporaryDirectory() as tmp:
                run_dir = Path(tmp) / "run-2026-test-001"
                run_dir.mkdir()
                self._write_valid_run_dir(run_dir)
                for artifact, mutate in edits:
                    self._edit_json_artifact(run_dir, artifact, mutate)
                with self.subTest(case=name):
                    ok, msg = verify_study_artifacts_semantic_relations(run_dir)
                    self.assertFalse(ok)
                    self.assertIn(expected, msg)
                    ok, msg = verify_completed_run(run_dir)
                    self.assertFalse(ok)
                    self.assertIn(expected, msg)

    def test_private_uncertainty_guards_reject_a_valid_summary_that_disagrees_with_the_saved_cohort(self) -> None:
        """
        Each edited summary passes the public validator on its own and both uncertainty copies
        agree, so only the private relation to the saved request can object: the count from its
        three saved keys, and the reason from its scored saved cohort. Every edit is rehashed.
        """
        RESULT, SUMMARY = "result.json", "panel-summary.json"

        def _two_of_three_slots_with_one_gap(doc: Dict[str, Any]) -> None:
            # Portable TEST: 2 requested and available origins over the 3 admitted slots, 1 gapped
            doc["admission_summary"].update(missing_vix_gap_count=1, union_gap_count=1)
            counts = doc["partitions"]["test"]["counts"]
            counts.update(
                eligible_count=2,
                requested_count=2,
                excluded_count=counts["raw_partition_count"] - 2,
                exclusion_reason_counts=dict(counts["exclusion_reason_counts"], missing_vix=1),
                model_available_counts={"heuristic": 2, "frequency": 2, "logistic": 0},
            )

        def _n_two(doc: Dict[str, Any]) -> None:
            doc["uncertainty"]["n"] = 2

        def _test_comparison_unavailable(doc: Dict[str, Any]) -> None:
            test = doc["partitions"]["test"]
            test.update(comparison_status=STATUS_COMPARISON_UNAVAILABLE, comparison_unavailable_reasons=["logistic: not_converged"], metrics=None)
            test["method_states"]["logistic"] = {"available": False, "unavailable_reason": "not_converged", "failure_stage": "fit"}
            test["counts"]["model_available_counts"]["logistic"] = 0

        def _comparison_unavailable_block(doc: Dict[str, Any]) -> None:
            block = doc["uncertainty"]
            block["reason"] = "comparison_unavailable"
            for entry in block["point_differences"]:
                entry["point_difference"] = None
            for view in block["block_lengths"]:
                view["reason"] = "comparison_unavailable"

        cases: List[Any] = [
            # Unavailable archive: the saved request keeps 3 keys over 3 gap-free slots
            (
                "saved_key_count",
                True,
                [(SUMMARY, _two_of_three_slots_with_one_gap), (SUMMARY, _n_two), (RESULT, _n_two)],
                (2, "comparison_unavailable"),
                "result.uncertainty: n and mature_span_count must be 3 and 3",
            ),
            # Scored archive: the saved request and result partition stay scored
            (
                "saved_cohort_reason",
                False,
                [(SUMMARY, _test_comparison_unavailable), (SUMMARY, _comparison_unavailable_block), (RESULT, _comparison_unavailable_block)],
                (3, "comparison_unavailable"),
                "result.uncertainty.reason: must be 'insufficient_nominal_blocks' for the saved cohort",
            ),
        ]
        for name, unavailable_archive, edits, claimed, expected in cases:
            with tempfile.TemporaryDirectory() as tmp:
                run_dir = Path(tmp) / "run-2026-test-001"
                run_dir.mkdir()
                self._write_valid_run_dir(run_dir, comparison_unavailable=unavailable_archive)
                for artifact, mutate in edits:
                    self._edit_json_artifact(run_dir, artifact, mutate)
                summary = parse_strict_json_bytes((run_dir / SUMMARY).read_bytes())
                result = parse_strict_json_bytes((run_dir / RESULT).read_bytes())
                saved_keys = parse_strict_json_bytes((run_dir / "uncertainty-input.json").read_bytes())["requested_keys"]
                with self.subTest(case=name):
                    validate_summary_document(copy.deepcopy(summary))
                    self.assertEqual(summary["uncertainty"], result["uncertainty"])
                    self.assertEqual((summary["uncertainty"]["n"], summary["uncertainty"]["reason"]), claimed)
                    self.assertEqual(len(saved_keys), 3)
                    for check in (verify_study_artifacts_semantic_relations, verify_completed_run):
                        ok, msg = check(run_dir)
                        self.assertFalse(ok, f"{check.__name__} accepted {name}")
                        self.assertIn(expected, msg)

    def test_input_bytes_must_stay_canonical_on_a_rehashed_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run-2026-test-001"
            run_dir.mkdir()
            self._write_valid_run_dir(run_dir)
            doc = parse_strict_json_bytes((run_dir / "uncertainty-input.json").read_bytes())
            self._replace_artifact(run_dir, "uncertainty-input.json", serialize_strict_json(doc))
            ok, msg = verify_completed_run(run_dir)
            self.assertFalse(ok)
            self.assertIn("canonical", msg)

    def test_unavailable_run_binds_availability_and_rows(self) -> None:
        def _swap_unavailable_method(doc: Dict[str, Any]) -> None:
            doc["method_available"].update(frequency=False, logistic=True)

        cases = {
            "which_method": (_swap_unavailable_method, "method_available"),
            "invented_rows": (lambda d: d.update(method_rows={"heuristic": [], "frequency": [], "logistic": []}), "comparison_unavailable requires method_rows=None"),
        }
        for name, (mutate, expected) in cases.items():
            with tempfile.TemporaryDirectory() as tmp:
                run_dir = Path(tmp) / "run-2026-test-001"
                run_dir.mkdir()
                self._write_valid_run_dir(run_dir, comparison_unavailable=True)
                ok, msg = verify_completed_run(run_dir)
                self.assertTrue(ok, msg)
                self._edit_json_artifact(run_dir, "uncertainty-input.json", mutate)
                with self.subTest(case=name):
                    ok, msg = verify_completed_run(run_dir)
                    self.assertFalse(ok)
                    self.assertIn(expected, msg)

    def test_manifest_provenance_must_match_the_result_and_required_sources(self) -> None:
        module = "research/prediction_eval/uncertainty.py"
        cases: Dict[str, Any] = {
            "source_hash": (lambda d: d["source_identities"][module].update(sha256="9" * 64), "Manifest source_identities"),
            "source_member": (lambda d: d["source_identities"].pop(module), "closed set"),
            "extra_source_member": (lambda d: d["source_identities"].update({"research/prediction_eval/extra.py": dict(FILE_IDENTITY)}), "closed set"),
            "config_identity": (lambda d: d["config_identity"].update(sha256="9" * 64), "Manifest config_identity"),
            "runtime": (lambda d: d["runtime_identities"].update(platform="other"), "Manifest runtime_identities"),
        }
        for name, (mutate, expected) in cases.items():
            with tempfile.TemporaryDirectory() as tmp:
                run_dir = Path(tmp) / "run-2026-test-001"
                run_dir.mkdir()
                self._write_valid_run_dir(run_dir)
                manifest = parse_strict_json_bytes((run_dir / "run-manifest.json").read_bytes())
                mutate(manifest)
                (run_dir / "run-manifest.json").write_bytes(serialize_strict_json(manifest))
                with self.subTest(case=name):
                    ok, msg = verify_completed_run(run_dir)
                    self.assertFalse(ok)
                    self.assertIn(expected, msg)

    def test_completed_run_binds_required_files_on_disk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run-2026-test-001"
            run_dir.mkdir()
            self._write_valid_run_dir(run_dir)

            ok, msg = verify_completed_run(run_dir)
            self.assertTrue(ok, msg)

            # A different byte in an unrelated required artifact breaks the completed run
            config_bytes = (run_dir / "config.json").read_bytes()
            (run_dir / "config.json").write_bytes(config_bytes + b" ")
            ok, msg = verify_completed_run(run_dir)
            self.assertFalse(ok)
            self.assertIn("config.json", msg)
            (run_dir / "config.json").write_bytes(config_bytes)

            # A missing required file breaks it too
            removed = (run_dir / "replay-stderr.log").read_bytes()
            (run_dir / "replay-stderr.log").unlink()
            ok, msg = verify_completed_run(run_dir)
            self.assertFalse(ok)
            (run_dir / "replay-stderr.log").write_bytes(removed)

            # A failure record contradicts completion
            (run_dir / FAILURE_RECORD_NAME).write_bytes(b"{}")
            ok, msg = verify_completed_run(run_dir)
            self.assertFalse(ok)
            (run_dir / FAILURE_RECORD_NAME).unlink()

            # A manifest absent means no completed run
            (run_dir / "run-manifest.json").unlink()
            ok, msg = verify_completed_run(run_dir)
            self.assertFalse(ok)

    def test_semantic_relations_broken(self) -> None:
        """Verifies that tampering with semantic relations fails verify_completed_run even when hashes match."""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run-2026-test-001"
            run_dir.mkdir()
            self._write_valid_run_dir(run_dir)

            # Tamper with uncertainty-diagnostics so semantic relation breaks, but rehash in manifest
            diag_doc = parse_strict_json_bytes((run_dir / "uncertainty-diagnostics.json").read_bytes())
            diag_doc["runtime_identity"]["python_implementation"] = "FakePython"
            tampered_diag_bytes = serialize_strict_json(diag_doc)
            (run_dir / "uncertainty-diagnostics.json").write_bytes(tampered_diag_bytes)

            # Re-sign manifest so SHA256 hashes are 100% valid
            man_doc = parse_strict_json_bytes((run_dir / "run-manifest.json").read_bytes())
            for item in man_doc["artifacts"]:
                if item["path"] == "uncertainty-diagnostics.json":
                    item["bytes"] = len(tampered_diag_bytes)
                    item["sha256"] = hashlib.sha256(tampered_diag_bytes).hexdigest().upper()
            (run_dir / "run-manifest.json").write_bytes(serialize_strict_json(man_doc))

            # Hashes match on disk, but semantic relation must fail!
            ok, msg = verify_completed_run(run_dir)
            self.assertFalse(ok)
            self.assertIn("python_implementation", msg)

    def _assert_rehashed_cases_fail(self, cases: Sequence[Any]) -> None:
        """Each case edits a fresh coherent run and recomputes every digest, then both gates refuse it."""
        for name, edits, expected in cases:
            with tempfile.TemporaryDirectory() as tmp:
                run_dir = Path(tmp) / "run-2026-test-001"
                run_dir.mkdir()
                self._write_valid_run_dir(run_dir)
                for edit in edits:
                    edit(run_dir)
                with self.subTest(case=name):
                    for check in (verify_study_artifacts_semantic_relations, verify_completed_run):
                        ok, msg = check(run_dir)
                        self.assertFalse(ok, f"{check.__name__} accepted {name}")
                        self.assertIn(expected, msg)

    def test_replay_and_predictions_relations_reject_rehashed_contradictions(self) -> None:
        """
        The saved replay streams, receipt and predictions are joined to the captured result by the
        shared owner that runs before the manifest and in verify_completed_run. A manifest whose
        hashes are all recomputed still fails when a bound relation contradicts the capture.
        """
        REQUEST, RESPONSE, STDERR, RECEIPT = "replay-request.json", "replay-response.json", "replay-stderr.log", "replay-invocation.json"
        RESULT, PREDICTIONS = "result.json", "predictions.json"

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run-2026-test-001"
            run_dir.mkdir()
            self._write_valid_run_dir(run_dir)
            for check in (verify_study_artifacts_semantic_relations, verify_completed_run):
                ok, msg = check(run_dir)
                self.assertTrue(ok, msg)
            # The receipt names a relocated root: its paths are records, not the proof of content
            receipt = parse_strict_json_bytes((run_dir / RECEIPT).read_bytes())
            self.assertNotIn(str(run_dir), receipt["stdout"]["path"])
            self.assertEqual((run_dir / STDERR).read_bytes(), SYNTHETIC_REPLAY_STDERR)

        def _raw(name: str, data: bytes) -> Callable[[Path], None]:
            return lambda run_dir: self._replace_artifact(run_dir, name, data)

        def _doc(name: str, mutate: Callable[[Any], None]) -> Callable[[Path], None]:
            return lambda run_dir: self._edit_json_artifact(run_dir, name, mutate)

        def _receipt(**changes: Any) -> Callable[[Path], None]:
            return _doc(RECEIPT, lambda d: d.update(changes))

        def _captured(key: str, data: bytes) -> Callable[[Path], None]:
            return _doc(RESULT, lambda d: d["replay_identity"].__setitem__(key, _identity_of(data)))

        def _first_test_row(doc: Dict[str, Any]) -> Dict[str, Any]:
            return doc["test"][0]

        new_response = SYNTHETIC_REPLAY_RESPONSE + b" "
        new_request = SYNTHETIC_REPLAY_REQUEST.replace(b"request", b"REQUEST")
        cases: List[Any] = [
            # Response or request replaced after capture: the result keeps the captured identity
            ("response_after_capture", [_raw(RESPONSE, new_response)], "result.replay_identity.response"),
            ("request_after_capture", [_raw(REQUEST, new_request)], "result.replay_identity.request"),
            # Result rebound to the new bytes: the successful receipt still names the captured ones
            ("receipt_stdout", [_raw(RESPONSE, new_response), _captured("response", new_response)], "replay-invocation.stdout"),
            ("receipt_request", [_raw(REQUEST, new_request), _captured("request", new_request)], "replay-invocation.request"),
            ("receipt_stderr", [_raw(STDERR, b"")], "replay-invocation.stderr"),
            ("second_attempt", [_receipt(attempt=2)], "replay-invocation.attempt"),
            ("boolean_attempt", [_receipt(attempt=True)], "replay-invocation.attempt"),
            ("timed_out", [_receipt(timed_out=True)], "replay-invocation.timed_out"),
            ("integer_timed_out", [_receipt(timed_out=0)], "replay-invocation.timed_out"),
            ("nonzero_exit", [_receipt(immediate_child_exit=1)], "replay-invocation.immediate_child_exit"),
            ("boolean_exit", [_receipt(immediate_child_exit=False)], "replay-invocation.immediate_child_exit"),
            ("launch_failed", [_receipt(launch_state="failed")], "replay-invocation.launch_state"),
            ("capture_drained_after_kill", [_receipt(capture_state="drained_after_kill")], "replay-invocation.capture_state"),
            ("capture_error_kept", [_receipt(capture_error="pipe broke")], "replay-invocation.capture_error"),
            ("receipt_key_dropped", [_doc(RECEIPT, lambda d: d.pop("declared_environment"))], "replay-invocation"),
            ("receipt_malformed", [_raw(RECEIPT, b"{")], "Strict JSON"),
            # The saved invocation must be the saved configuration's launch, label for label
            ("argv_empty", [_receipt(argv=[])], "replay-invocation.argv"),
            ("argv_without_request", [_doc(RECEIPT, lambda d: d["argv"].pop())], "replay-invocation.argv"),
            ("argv_other_script", [_doc(RECEIPT, lambda d: d["argv"].__setitem__(1, "/synthetic/elsewhere/replay.cjs"))], "replay-invocation.argv"),
            ("argv_other_request", [_doc(RECEIPT, lambda d: d["argv"].__setitem__(2, "/synthetic/relocated-run/replay-request-002.json"))], "replay-invocation.argv"),
            ("argv_other_executable", [_doc(RECEIPT, lambda d: d["argv"].__setitem__(0, "/synthetic/tools/other-node.exe"))], "replay-invocation.argv"),
            (
                "exe_not_configured",
                [_doc(RECEIPT, lambda d: d.update(exe="/synthetic/tools/other-node.exe", argv=["/synthetic/tools/other-node.exe"] + d["argv"][1:]))],
                "replay-invocation.exe",
            ),
            ("cwd_not_configured", [_receipt(cwd="/synthetic/other-workspace")], "replay-invocation.cwd"),
            ("timeout_differs_from_config", [_receipt(timeout_seconds=59)], "does not match config.timeout_seconds"),
            (
                "timeout_above_live_bound",
                [_doc("config.json", lambda d: d.update(timeout_seconds=61)), _receipt(timeout_seconds=61)],
                "exceeds the 60-second replay bound",
            ),
            ("timeout_float", [_receipt(timeout_seconds=60.0)], "replay-invocation.timeout_seconds"),
            ("timeout_boolean", [_receipt(timeout_seconds=True)], "replay-invocation.timeout_seconds"),
            ("prediction_value", [_doc(PREDICTIONS, lambda d: _first_test_row(d).update(origin_close="0.00"))], "predictions.json"),
            (
                "prediction_numeric_type",
                [_doc(PREDICTIONS, lambda d: _first_test_row(d).update(origin_index=float(_first_test_row(d)["origin_index"])))],
                "predictions.json",
            ),
            ("prediction_row_dropped", [_doc(PREDICTIONS, lambda d: d["test"].pop())], "predictions.json"),
            ("predictions_malformed", [_raw(PREDICTIONS, b"[")], "Strict JSON"),
        ]
        self._assert_rehashed_cases_fail(cases)

    def test_saved_bindings_and_fitting_blocks_reject_rehashed_contradictions(self) -> None:
        """
        Saved tool, model and dependency fields must agree with the result's runtime, model, build,
        replay and comparator fields, and listed fitting rows must follow the planner rule against
        their own partition cutoff. Expectations are stated here, not taken from the producer.
        """
        self.assertEqual(EXPECTED_MODELS_SHA256, PINNED_MODEL_SHA256)
        self.assertEqual(REQUIRED_DEPENDENCIES, ("numpy", "scikit-learn", "scipy", "threadpoolctl"))
        d_idx, t_idx = RUN_DEVELOPMENT_START, RUN_DEVELOPMENT_START + 1

        def _config(mutate: Callable[[Dict[str, Any]], None]) -> List[Callable[[Path], None]]:
            return [lambda run_dir: self._edit_json_artifact(run_dir, "config.json", mutate)]

        def _result(mutate: Callable[[Dict[str, Any]], None]) -> List[Callable[[Path], None]]:
            return [lambda run_dir: self._edit_json_artifact(run_dir, "result.json", mutate)]

        def _block(doc: Dict[str, Any], partition: str, method: str) -> Dict[str, Any]:
            return doc["partitions"][partition][f"{method}_block"]

        def _both_pools(partition: str, pool: Sequence[int]) -> Callable[[Dict[str, Any]], None]:
            def _apply(doc: Dict[str, Any]) -> None:
                for method in ("frequency", "logistic"):
                    _set_pool(_block(doc, partition, method), pool)

            return _apply

        def _tool(name: str, **changes: Any) -> Callable[[Dict[str, Any]], None]:
            return lambda c: c["tools"][name].update(changes)

        # The loader accepts a valid lowercase digest and uppercases it, so the saved pin may be lowercase
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run-2026-test-001"
            run_dir.mkdir()
            self._write_valid_run_dir(run_dir)
            for edit in _config(_tool("models", sha256=PINNED_MODEL_SHA256.lower())):
                edit(run_dir)
            # A coherent archive of that configuration also carries its digest in the summary
            config_sha = self._bytes_identity((run_dir / "config.json").read_bytes())["sha256"]
            self._edit_json_artifact(run_dir, "panel-summary.json", lambda d: d["provenance_identity"].update(config_sha256=config_sha))
            saved = parse_strict_json_bytes((run_dir / "config.json").read_bytes())
            self.assertEqual(saved["tools"]["models"]["sha256"], PINNED_MODEL_SHA256.lower())
            for check in (verify_study_artifacts_semantic_relations, verify_completed_run):
                ok, msg = check(run_dir)
                self.assertTrue(ok, msg)

        def _replay_source(doc: Dict[str, Any]) -> None:
            entry = doc.get("source_modules", doc.get("source_identities"))["research/prediction_eval/replay.cjs"]
            entry.update(sha256="9" * 64)

        def _dev_cutoff_relabel(doc: Dict[str, Any]) -> None:
            # Partition, both blocks and the declared development start agree (the result's field,
            # the summary's chronological cutoff), so only the axis relation can object
            wrong = (self.d0 + datetime.timedelta(days=d_idx - 1)).isoformat()
            part = doc["partitions"]["development"]
            for target in (part, part.get("frequency_block"), part.get("logistic_block")):
                if target is not None:
                    target["cutoff_date"] = wrong
            if "development_start" in doc:
                doc["development_start"] = wrong
            if "chronological_cutoffs" in doc:
                doc["chronological_cutoffs"]["development_start"] = wrong

        cases: List[Any] = [
            ("node_hash", _config(_tool("node_executable", sha256="9" * 64)), "config.tools.node_executable"),
            ("python_bytes", _config(_tool("python_executable", raw_byte_count=11)), "config.tools.python_executable"),
            ("replay_script_hash", _config(_tool("replay_script", sha256="9" * 64)), "config.tools.replay_script"),
            ("build_bytes", _config(_tool("candidate_build_manifest", raw_byte_count=8)), "config.tools.candidate_build_manifest"),
            ("model_not_pinned", _config(_tool("models", sha256="9" * 64)), "config.tools.models.sha256"),
            ("model_pin_lowercase_but_wrong", _config(_tool("models", sha256=("9" * 63 + "a"))), "config.tools.models.sha256"),
            ("model_pin_malformed", _config(_tool("models", sha256=PINNED_MODEL_SHA256[:63])), "config.tools.models.sha256"),
            ("tools_missing", _config(lambda c: c.pop("tools")), "config.tools"),
            # replay.cjs measured as a source module and as the replay script must be one file
            ("replay_source_differs_from_script", _config(_replay_source) + _result(_replay_source), "result.replay_identity.script"),
            ("build_not_candidate", _result(lambda d: d["build_identity"].update(mode="baseline")), "result.build_identity.mode"),
            ("logistic_versions_empty", _result(lambda d: d["comparator_metadata"]["logistic"].update(dependency_versions=[])), "must name exactly"),
            ("logistic_versions_without_scipy", _result(lambda d: d["comparator_metadata"]["logistic"]["dependency_versions"].pop(2)), "must name exactly"),
            # A coordinated DEV relabel: partition, both DEV blocks and the summary all name one wrong date
            (
                "development_cutoff_date_relabeled",
                _result(_dev_cutoff_relabel)
                + [lambda run_dir: self._edit_json_artifact(run_dir, "panel-summary.json", _dev_cutoff_relabel)],
                "result.partitions.development: cutoff index or date",
            ),
            ("replay_model_unpinned", _result(lambda d: d["replay_identity"].update(model_sha256="9" * 64)), "result.model_identity.sha256"),
            ("replay_build_hash", _result(lambda d: d["replay_identity"].update(build_manifest_sha256="9" * 64)), "result.replay_identity"),
            ("replay_calculation_id", _result(lambda d: d["replay_identity"].update(calculation_id="other")), "result.replay_identity"),
            ("dependency_value", _config(lambda c: c["runtime"]["dependency_versions"].update(scipy="0.0.0")), "result.runtime_identities.dependency_versions"),
            ("dependency_key_missing", _config(lambda c: c["runtime"]["dependency_versions"].pop("threadpoolctl")), "config.runtime.dependency_versions"),
            ("dependency_key_extra", _config(lambda c: c["runtime"]["dependency_versions"].update(pandas="1.0")), "config.runtime.dependency_versions"),
            (
                "comparator_version",
                _result(lambda d: d["comparator_metadata"]["logistic"]["dependency_versions"][2].__setitem__(1, "0.0.0")),
                "comparator_metadata.logistic.dependency_versions[2]",
            ),
            (
                "comparator_unknown_package",
                _result(lambda d: d["comparator_metadata"]["logistic"]["dependency_versions"].append(["pandas", "1.0"])),
                "comparator_metadata.logistic.dependency_versions[3]",
            ),
            ("wrong_block_cutoff_index", _result(lambda d: _block(d, "test", "frequency").update(cutoff_index=d_idx)), "block cutoff"),
            ("wrong_block_cutoff_date", _result(lambda d: _block(d, "test", "logistic").update(cutoff_date="2022-01-03")), "block cutoff"),
            # Equality boundary: i + 20 == cutoff is not strictly before it, at T and at D
            ("refit_row_at_test_cutoff", _result(lambda d: _set_pool(_block(d, "test", "frequency"), (200, 201, 202, t_idx - 20))), "does not mature strictly before cutoff 224"),
            ("development_row_at_its_cutoff", _result(lambda d: _set_pool(_block(d, "development", "logistic"), (200, 201, d_idx - 20))), "does not mature strictly before cutoff 223"),
            ("warmup_row", _result(lambda d: _set_pool(_block(d, "development", "frequency"), (199, 200, 201))), "inside the warmup"),
            ("methods_list_different_pools", _result(lambda d: _set_pool(_block(d, "test", "logistic"), (200, 201, 202))), "different fitting pools"),
            ("refit_omits_development_row", _result(_both_pools("test", (200, 201, 203))), "refit pool omits development fitting rows [202]"),
        ]
        self._assert_rehashed_cases_fail(cases)

    def test_malformed_shapes_fail_closed_without_raising(self) -> None:
        """A list where a version belongs, or an out-of-range integer, is a rejection, not a crash."""
        summary_bytes, manifest_bytes = self._bound_bytes()
        summary_doc = json.loads(summary_bytes.decode("utf-8"))
        bad_schema = serialize_strict_json(dict(summary_doc, schema_version=[SCHEMA_VERSION_SUMMARY_V2]))
        ok, msg = verify_completion_binding(bad_schema, manifest_bytes)
        self.assertFalse(ok)

        huge = copy.deepcopy(summary_doc)
        huge["partitions"]["test"]["metrics"]["models"]["heuristic"]["mean_brier"] = 10 ** 400
        huge_bytes = json.dumps(huge).encode("utf-8")
        ok, msg = verify_completion_binding(huge_bytes, manifest_bytes)
        self.assertFalse(ok)
        desc = self._descriptor(summary_bytes, manifest_bytes)
        self.assertEqual(evaluate_ui_display_state(huge_bytes, desc)["display_state"], UI_STATE_ERROR)

    def test_unhashable_result_and_manifest_versions_are_named_rejections(self) -> None:
        """
        An array or object version is unhashable, so it must be refused as a schema error before
        the supported-set lookup. Edited artifacts are rehashed into the manifest, so each seam
        reaches the validator that owns the version rather than an earlier digest guard.
        """
        summary_bytes, manifest_bytes = self._bound_bytes()
        good_result = build_result_document(self.study_result)
        good_manifest = parse_strict_json_bytes(manifest_bytes)
        for bad in ([], {}):
            with self.subTest(document="direct", version=bad):
                for validate, doc, field in (
                    (validate_result_document, good_result, "result.schema_version"),
                    (validate_run_manifest_document, good_manifest, "manifest.schema_version"),
                ):
                    with self.assertRaises(ValueError) as ctx:
                        validate(dict(copy.deepcopy(doc), schema_version=bad))
                    self.assertIn(field, str(ctx.exception))

            with self.subTest(document="completion_binding", version=bad):
                ok, msg = verify_completion_binding(summary_bytes, serialize_strict_json(dict(good_manifest, schema_version=bad)))
                self.assertFalse(ok)
                self.assertIn("Invalid run-manifest.json: manifest.schema_version", msg)

            with tempfile.TemporaryDirectory() as tmp:
                run_dir = Path(tmp) / "run-2026-test-001"
                run_dir.mkdir()
                self._write_valid_run_dir(run_dir)
                self.assertEqual(verify_completed_run(run_dir), (True, "Completed run verified"))
                self._edit_json_artifact(run_dir, "result.json", lambda d: d.update(schema_version=bad))
                with self.subTest(document="result_on_disk", version=bad):
                    for check in (verify_study_artifacts_semantic_relations, verify_completed_run):
                        ok, msg = check(run_dir)
                        self.assertFalse(ok)
                        self.assertIn("result.schema_version", msg)

            with tempfile.TemporaryDirectory() as tmp:
                run_dir = Path(tmp) / "run-2026-test-001"
                run_dir.mkdir()
                self._write_valid_run_dir(run_dir)
                manifest = parse_strict_json_bytes((run_dir / "run-manifest.json").read_bytes())
                (run_dir / "run-manifest.json").write_bytes(serialize_strict_json(dict(manifest, schema_version=bad)))
                with self.subTest(document="manifest_on_disk", version=bad):
                    ok, msg = verify_completed_run(run_dir)
                    self.assertFalse(ok)
                    self.assertIn("manifest.schema_version", msg)

    def test_descriptor_document_round_trip_is_strict(self) -> None:
        summary_bytes, manifest_bytes = self._bound_bytes()
        desc = self._descriptor(summary_bytes, manifest_bytes)
        document = release_descriptor_document(desc)

        self.assertEqual(parse_release_descriptor(serialize_strict_json(document)), desc)
        self.assertNotIn(":\\", json.dumps(document))

        cases = {
            "unknown_key": serialize_strict_json(dict(document, extra=1)),
            "missing_key": serialize_strict_json({k: v for k, v in document.items() if k != "run_id"}),
            "wrong_schema": serialize_strict_json(dict(document, schema_version="v99")),
            "bool_count": serialize_strict_json(dict(document, summary_bytes=True)),
            "duplicate_key": b'{"run_id": "a", "run_id": "b"}',
            "not_utf8": b"\xff\xfe",
            "not_object": b"[]",
        }
        for name, raw in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    parse_release_descriptor(raw)

    def test_descriptor_rejects_malformed_fields(self) -> None:
        summary_bytes, manifest_bytes = self._bound_bytes()
        for name, changes in {
            "bad_summary_hash": {"summary_sha256": "M" * 64},
            "bad_manifest_hash": {"manifest_sha256": "abc"},
            "bool_bytes": {"summary_bytes": True},
            "zero_bytes": {"manifest_bytes": 0},
            "bad_run_id": {"run_id": "../x"},
            "bad_study_id": {"study_id": ""},
            "bad_date": {"coverage_end_date": "soon"},
        }.items():
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    self._descriptor(summary_bytes, manifest_bytes, **changes)

    def test_ui_display_state_evaluation_precedence(self) -> None:
        """Verifies UI state evaluation in fixed precedence order."""
        summary_doc = build_panel_summary(self.study_result)
        summary_bytes = serialize_strict_json(summary_doc)
        s_sha = hashlib.sha256(summary_bytes).hexdigest().upper()
        s_len = len(summary_bytes)

        desc = build_release_descriptor(
            run_id="run-2026-test-001",
            study_id="synthetic-toy-study",
            protocol_id=STUDY_PROTOCOL_ID,
            summary_schema_version=SCHEMA_VERSION_SUMMARY_V2,
            coverage_end_date=self.d2.isoformat(),
            summary_bytes=s_len,
            summary_sha256=s_sha,
            manifest_bytes=1000,
            manifest_sha256="A" * 64,
        )

        # 1. Missing artifact or descriptor -> unavailable
        res1 = evaluate_ui_display_state(None, desc)
        self.assertEqual(res1["display_state"], UI_STATE_UNAVAILABLE)
        self.assertFalse(res1["can_display_metrics"])

        res1b = evaluate_ui_display_state(summary_bytes, None)
        self.assertEqual(res1b["display_state"], UI_STATE_UNAVAILABLE)

        # 2. Malformed JSON -> error
        res2 = evaluate_ui_display_state(b"not json {", desc)
        self.assertEqual(res2["display_state"], UI_STATE_ERROR)
        self.assertFalse(res2["can_display_metrics"])

        # 3. Unsupported schema/protocol -> unsupported_version
        bad_proto_doc = dict(summary_doc)
        bad_proto_doc["protocol_id"] = "unsupported-protocol-v9"
        bad_proto_bytes = serialize_strict_json(bad_proto_doc)
        res3 = evaluate_ui_display_state(bad_proto_bytes, desc)
        self.assertEqual(res3["display_state"], UI_STATE_UNSUPPORTED_VERSION)
        self.assertFalse(res3["can_display_metrics"])

        # 4. Parsed run_id or coverage_end_date mismatch -> stale
        diff_date_desc = build_release_descriptor(
            run_id="run-2026-test-001",
            study_id="synthetic-toy-study",
            protocol_id=STUDY_PROTOCOL_ID,
            summary_schema_version=SCHEMA_VERSION_SUMMARY_V2,
            coverage_end_date="2099-12-31",  # Different date
            summary_bytes=s_len,
            summary_sha256=s_sha,
            manifest_bytes=1000,
            manifest_sha256="A" * 64,
        )
        res4 = evaluate_ui_display_state(summary_bytes, diff_date_desc)
        self.assertEqual(res4["display_state"], UI_STATE_STALE)
        self.assertFalse(res4["can_display_metrics"])

        # A different selected run is stale even with the same study and coverage
        other_run_desc = build_release_descriptor(
            run_id="run-2026-test-002",
            study_id="synthetic-toy-study",
            protocol_id=STUDY_PROTOCOL_ID,
            summary_schema_version=SCHEMA_VERSION_SUMMARY_V2,
            coverage_end_date=self.d2.isoformat(),
            summary_bytes=s_len,
            summary_sha256=s_sha,
            manifest_bytes=1000,
            manifest_sha256="A" * 64,
        )
        self.assertEqual(evaluate_ui_display_state(summary_bytes, other_run_desc)["display_state"], UI_STATE_STALE)

        # 5. Digest mismatch or failure -> error
        tampered_bytes = serialize_strict_json(dict(summary_doc))  # same length if not changed, let's tamper SHA
        bad_hash_desc = build_release_descriptor(
            run_id="run-2026-test-001",
            study_id="synthetic-toy-study",
            protocol_id=STUDY_PROTOCOL_ID,
            summary_schema_version=SCHEMA_VERSION_SUMMARY_V2,
            coverage_end_date=self.d2.isoformat(),
            summary_bytes=s_len,
            summary_sha256="F" * 64,
            manifest_bytes=1000,
            manifest_sha256="A" * 64,
        )
        res5 = evaluate_ui_display_state(summary_bytes, bad_hash_desc)
        self.assertEqual(res5["display_state"], UI_STATE_ERROR)
        self.assertFalse(res5["can_display_metrics"])

        # Inability to compute digest -> error with NO metrics
        def _failing_digest(_b: bytes) -> str:
            raise RuntimeError("Digest engine broken")

        res5b = evaluate_ui_display_state(summary_bytes, desc, digest_fn=_failing_digest)
        self.assertEqual(res5b["display_state"], UI_STATE_ERROR)
        self.assertFalse(res5b["can_display_metrics"])

        # 6. Exact supported binding -> displayable
        res6 = evaluate_ui_display_state(summary_bytes, desc)
        self.assertEqual(res6["display_state"], UI_STATE_DISPLAYABLE)
        self.assertTrue(res6["can_display_metrics"])
        self.assertIsNotNone(res6["summary_data"])

    def test_ui_support_is_not_defined_by_the_descriptor(self) -> None:
        """A matching v99 summary and descriptor are unsupported, whatever their hashes say."""
        summary_doc = build_panel_summary(self.study_result)
        v99_bytes = serialize_strict_json(dict(summary_doc, schema_version="nivesh-evaluation-summary-v99"))
        v99_desc = build_release_descriptor(
            run_id="run-2026-test-001",
            study_id="synthetic-toy-study",
            protocol_id=STUDY_PROTOCOL_ID,
            summary_schema_version="nivesh-evaluation-summary-v99",
            coverage_end_date=self.d2.isoformat(),
            summary_bytes=len(v99_bytes),
            summary_sha256=hashlib.sha256(v99_bytes).hexdigest(),
            manifest_bytes=1000,
            manifest_sha256="A" * 64,
        )
        state = evaluate_ui_display_state(v99_bytes, v99_desc)
        self.assertEqual(state["display_state"], UI_STATE_UNSUPPORTED_VERSION)
        self.assertIsNone(state["summary_data"])

    def test_ui_malformed_shapes_are_errors_without_metrics(self) -> None:
        summary_doc = build_panel_summary(self.study_result)
        good_bytes = serialize_strict_json(summary_doc)
        desc = build_release_descriptor(
            run_id="run-2026-test-001",
            study_id="synthetic-toy-study",
            protocol_id=STUDY_PROTOCOL_ID,
            summary_schema_version=SCHEMA_VERSION_SUMMARY_V2,
            coverage_end_date=self.d2.isoformat(),
            summary_bytes=len(good_bytes),
            summary_sha256=hashlib.sha256(good_bytes).hexdigest(),
            manifest_bytes=1000,
            manifest_sha256="A" * 64,
        )
        cases = {
            "attribution_not_object": serialize_strict_json(dict(summary_doc, dataset_attribution=[])),
            "unknown_key": serialize_strict_json(dict(summary_doc, extra=1)),
            "schema_not_string": serialize_strict_json(dict(summary_doc, schema_version=1)),
            "root_not_object": b"[]",
            "duplicate_key": b'{"schema_version": "a", "schema_version": "b"}',
            "nan_token": good_bytes.replace(b'"horizon_sessions": 20', b'"horizon_sessions": NaN'),
        }
        for name, raw in cases.items():
            with self.subTest(case=name):
                state = evaluate_ui_display_state(raw, desc)
                self.assertEqual(state["display_state"], UI_STATE_ERROR)
                self.assertFalse(state["can_display_metrics"])
                self.assertIsNone(state["summary_data"])

        # Same identity, different bytes: a byte-count error, not a stale selection
        padded = good_bytes + b"\n"
        self.assertEqual(evaluate_ui_display_state(padded, desc)["display_state"], UI_STATE_ERROR)

    def _bound_to_exact_bytes(self, summary_doc: Dict[str, Any]) -> tuple:
        """A descriptor and manifest for these exact bytes, so no hash failure can mask validation."""
        raw_summary = serialize_strict_json(summary_doc)
        raw_manifest = serialize_strict_json(self._manifest_doc(raw_summary))
        return raw_summary, raw_manifest, self._descriptor(raw_summary, raw_manifest)

    def test_ui_rejects_impossible_finite_metrics_with_matching_bindings(self) -> None:
        """Each document is finite, closed and exactly bound, so only metric validation can reject it."""
        good = build_panel_summary(self.study_result)
        raw_good, _, good_desc = self._bound_to_exact_bytes(good)
        self.assertEqual(evaluate_ui_display_state(raw_good, good_desc)["display_state"], UI_STATE_DISPLAYABLE)

        def _model(doc: Dict[str, Any], name: str = "heuristic") -> Dict[str, Any]:
            return doc["partitions"]["test"]["metrics"]["models"][name]

        def _first_filled_bin(doc: Dict[str, Any]) -> Dict[str, Any]:
            return next(b for b in _model(doc)["reliability_bins"] if b["count"])

        cases: Dict[str, Any] = {
            "negative_recall": (lambda d: _model(d)["class_recall"].__setitem__(0, -1), "class_recall[0]"),
            "recall_above_one": (lambda d: _model(d)["class_recall"].__setitem__(0, 1.5), "class_recall[0]"),
            "recall_contradicts_confusion": (lambda d: _model(d)["class_recall"].__setitem__(0, 0.5), "contradicts counts"),
            "accuracy_contradicts_confusion": (lambda d: _model(d).update(accuracy=0.5), "contradicts counts"),
            "accuracy_above_one": (lambda d: _model(d).update(accuracy=1.5), "accuracy"),
            "negative_brier": (lambda d: _model(d).update(mean_brier=-0.1), "mean_brier"),
            "brier_above_ceiling": (lambda d: _model(d).update(mean_brier=2.5), "mean_brier"),
            "negative_log_loss": (lambda d: _model(d).update(mean_log_loss=-0.1), "mean_log_loss"),
            "negative_bin_mean": (lambda d: _first_filled_bin(d).update(mean_probability=-0.1), "mean_probability"),
            "bin_mean_above_one": (lambda d: _first_filled_bin(d).update(mean_probability=1.1), "mean_probability"),
            "negative_bin_frequency": (lambda d: _first_filled_bin(d).update(observed_frequency=-0.1), "observed_frequency"),
            "bin_frequency_above_one": (lambda d: _first_filled_bin(d).update(observed_frequency=1.1), "observed_frequency"),
            "bin_index_true": (lambda d: _model(d)["reliability_bins"][1].update(bin_index=True), "class-major order"),
            "available_count_contradicts_state": (
                lambda d: d["partitions"]["test"]["counts"]["model_available_counts"].update(frequency=0),
                "method state",
            ),
        }
        for name, (mutate, expected) in cases.items():
            doc = copy.deepcopy(good)
            mutate(doc)
            raw_summary, raw_manifest, desc = self._bound_to_exact_bytes(doc)
            with self.subTest(case=name):
                self.assertEqual(desc.summary_sha256, hashlib.sha256(raw_summary).hexdigest().upper())
                state = evaluate_ui_display_state(raw_summary, desc)
                self.assertEqual(state["display_state"], UI_STATE_ERROR)
                self.assertFalse(state["can_display_metrics"])
                self.assertIsNone(state["summary_data"])
                self.assertIn(expected, state["reason"])
                ok, msg = verify_promotion_binding(raw_summary, raw_manifest, desc)
                self.assertFalse(ok)
                self.assertIn("Invalid panel-summary.json", msg)

    def _assert_rejected_on_exact_bindings(self, doc: Dict[str, Any], expected: str) -> None:
        raw_summary = serialize_strict_json(doc)
        raw_manifest = serialize_strict_json(self._manifest_doc(raw_summary))
        desc = self._descriptor(raw_summary, raw_manifest)
        state = evaluate_ui_display_state(raw_summary, desc)
        self.assertEqual(state["display_state"], UI_STATE_ERROR)
        self.assertFalse(state["can_display_metrics"])
        self.assertIsNone(state["summary_data"])
        self.assertIn(expected, state["reason"])
        for ok, msg in (verify_completion_binding(raw_summary, raw_manifest), verify_promotion_binding(raw_summary, raw_manifest, desc)):
            self.assertFalse(ok)
            self.assertIn("Invalid panel-summary.json", msg)

    def test_uncertainty_contradictions_and_malformed_values_fail_closed_at_consumers(self) -> None:
        """
        Bytes and hashes stay exactly bound, so only uncertainty validation can reject these. The
        scored base keeps its points below every floor; the comparison-unavailable base (n=3 over
        the 3-slot span) has a common reason and no points. Each case names its own base, since
        the old shared base was a scored TEST with an n=0 comparison_unavailable block.
        """
        scored = build_panel_summary(self.study_result)
        unavailable = build_panel_summary(self._study_result(test=self._unavailable_partition("test", cutoff_index=SYNTHETIC_TEST_CUTOFF)))
        self.assertEqual(scored["uncertainty"]["reason"], "insufficient_nominal_blocks")
        self.assertEqual(unavailable["uncertainty"]["reason"], "comparison_unavailable")

        def _block(doc: Dict[str, Any]) -> Dict[str, Any]:
            return doc["uncertainty"]

        def _available_claim(doc: Dict[str, Any]) -> None:
            _block(doc).update(status="available", reason=None)

        def _point_on_unavailable(doc: Dict[str, Any]) -> None:
            _block(doc)["point_differences"][0]["point_difference"] = 0.125

        def _huge_bound(doc: Dict[str, Any]) -> None:
            view = _block(doc)["block_lengths"][0]
            view.update(status="available", reason=None)
            view["pairs"][0].update(lower=10 ** 400, upper=0.5)

        cases: Dict[str, Any] = {
            "available_with_all_lengths_unavailable": (scored, _available_claim, "contradicts"),
            "point_on_unavailable_comparison": (unavailable, _point_on_unavailable, "point difference contradicts"),
            "point_missing_on_scored_cohort": (scored, lambda d: _block(d)["point_differences"][1].update(point_difference=None), "point difference contradicts"),
            "free_text_length_reason": (scored, lambda d: _block(d)["block_lengths"][0].update(reason="x"), "supported reason"),
            "length_reason_differs": (unavailable, lambda d: _block(d)["block_lengths"][1].update(reason="empty_cohort"), "contradicts common reason"),
            "n_above_span": (unavailable, lambda d: _block(d).update(n=_block(d)["mature_span_count"] + 1), "exceeds mature_span_count"),
            "float_length": (scored, lambda d: _block(d)["block_lengths"][0].update(block_length=20.0), "block_length"),
            "status_list": (scored, lambda d: _block(d).update(status=[]), "Unsupported uncertainty status"),
            "status_object": (scored, lambda d: _block(d).update(status={}), "Unsupported uncertainty status"),
            "reason_list": (scored, lambda d: _block(d).update(reason=[]), "supported top reason"),
            "point_beyond_binary64": (scored, lambda d: _block(d)["point_differences"][0].update(point_difference=10 ** 400), "finite float"),
            "bound_beyond_binary64": (scored, _huge_bound, "finite float"),
        }
        for name, (base, mutate, expected) in cases.items():
            doc = copy.deepcopy(base)
            mutate(doc)
            with self.subTest(case=name):
                self._assert_rejected_on_exact_bindings(doc, expected)

    def test_literal_v1_outputs_are_unsupported_without_metrics(self) -> None:
        summary = build_panel_summary(self.study_result)
        v1_bytes = serialize_strict_json(dict(summary, schema_version="nivesh-evaluation-summary-v1"))
        v1_desc = build_release_descriptor(
            run_id="run-2026-test-001",
            study_id="synthetic-toy-study",
            protocol_id=STUDY_PROTOCOL_ID,
            summary_schema_version="nivesh-evaluation-summary-v1",
            coverage_end_date=self.d2.isoformat(),
            summary_bytes=len(v1_bytes),
            summary_sha256=hashlib.sha256(v1_bytes).hexdigest(),
            manifest_bytes=1000,
            manifest_sha256="A" * 64,
        )
        state = evaluate_ui_display_state(v1_bytes, v1_desc)
        self.assertEqual(state["display_state"], UI_STATE_UNSUPPORTED_VERSION)
        self.assertFalse(state["can_display_metrics"])
        self.assertIsNone(state["summary_data"])
        self.assertIn("nivesh-evaluation-summary-v1", state["reason"])

        with self.assertRaises(ValueError) as ctx:
            validate_summary_document(json.loads(v1_bytes.decode("utf-8")))
        self.assertIn("schema_version", str(ctx.exception))

        result = dict(build_result_document(self.study_result), schema_version="nivesh-study-result-v1")
        with self.assertRaises(ValueError) as ctx:
            validate_result_document(result)
        self.assertIn("nivesh-study-result-v1", str(ctx.exception))

        summary_bytes = serialize_strict_json(summary)
        manifest = dict(self._manifest_doc(summary_bytes), schema_version="nivesh-study-run-manifest-v1")
        with self.assertRaises(ValueError) as ctx:
            validate_run_manifest_document(manifest)
        self.assertIn("nivesh-study-run-manifest-v1", str(ctx.exception))
        ok, msg = verify_completion_binding(summary_bytes, serialize_strict_json(manifest))
        self.assertFalse(ok)
        self.assertIn("unsupported manifest schema", msg)

    def test_report_and_summary_carry_all_lengths_bounds_reasons_and_caveats(self) -> None:
        """n=400 clears L20 and L40; each row keeps equal prominence, with no private diagnostics."""
        views = []
        for L, bounds in ((20, (-0.25, 0.5)), (40, (-0.125, 0.375)), (60, (None, None))):
            views.append(
                {
                    "block_length": L,
                    "label": BLOCK_LENGTH_LABELS[L],
                    "status": "available" if bounds[0] is not None else "unavailable",
                    "reason": None if bounds[0] is not None else "insufficient_nominal_blocks",
                    "seed": BLOCK_LENGTH_SEEDS[L],
                    "pairs": tuple({"pair_id": pair, "lower": bounds[0], "upper": bounds[1]} for pair in ORDERED_PAIR_IDS),
                }
            )
        block = _valid_uncertainty_block(
            status="partially_available",
            reason=None,
            n=400,
            point_differences=tuple({"pair_id": pair, "point_difference": value} for pair, value in zip(ORDERED_PAIR_IDS, (-0.375, 0.125))),
            block_lengths=tuple(views),
        )
        # A scored, gap-free TEST cohort of the block's 400 origins, so the summary keeps the
        # portable relations. Every origin is BEAR and each method repeats one vector, so the
        # row Briers are exact dyadic values: heuristic (.75, .25, 0) gives 0.125, frequency
        # (.5, .5, 0) gives 0.5 and logistic (1, 0, 0) gives 0. The stated points are exactly
        # the TEST mean differences, -0.375 and +0.125; the bounds stay schematic.
        origins = [
            EvaluationOrigin(origin_index=SYNTHETIC_TEST_CUTOFF + i, origin_date=self.d1 + datetime.timedelta(days=i), actual_class=OUTCOME_CLASS_BEAR)
            for i in range(400)
        ]

        def _rows(probabilities: tuple) -> List[DummyPrediction]:
            return [DummyPrediction(o.origin_index, o.origin_date, probabilities) for o in origins]

        comparison = score_comparison(origins, heuristic=_rows((0.75, 0.25, 0.0)), frequency=_rows((0.5, 0.5, 0.0)), logistic=_rows((1.0, 0.0, 0.0)))
        self.assertEqual((comparison.heuristic.mean_brier, comparison.frequency.mean_brier, comparison.logistic.mean_brier), (0.125, 0.5, 0.0))
        result = self._study_result(test=self._partition("test", comparison, origins, cutoff_index=SYNTHETIC_TEST_CUTOFF), uncertainty=block)
        report = render_report_markdown(result)
        for expected in (
            "- Status: `partially_available`",
            "- Cohort Size (n): 400 (Mature Span: 400)",
            "`heuristic_minus_frequency`: -0.375000",
            "`heuristic_minus_logistic`: +0.125000",
            "#### Block Length 20 (`available`)",
            "#### Block Length 40 (`available`)",
            "#### Block Length 60 (`unavailable`)",
            "- Seed: `20261123`",
            "- Seed: `20261163`",
            "not a minimum realized block length",
            "[-0.250000, +0.500000]",
            "[-0.125000, +0.375000]",
            "[None, None]",
            "- Reason: insufficient_nominal_blocks",
            "marginal views under approximate stationarity",
        ):
            self.assertIn(expected, report)

        summary_text = serialize_strict_json(build_panel_summary(result)).decode("utf-8")
        for text in (report, summary_text):
            for forbidden in (
                "not_implemented",
                "deferred",
                "index_stream_sha256",
                "random_calls",
                "randrange_calls",
                "input_identity",
                "union_gap_positions",
                "uncertainty-input",
                "uncertainty-diagnostics",
            ):
                self.assertNotIn(forbidden, text)
        self.assertEqual(json.loads(summary_text)["uncertainty"]["block_lengths"][2]["reason"], "insufficient_nominal_blocks")

    def test_ui_keeps_valid_signed_zero_null_empty_infinite_and_tiny_states(self) -> None:
        """Range checks must leave every accepted scorer state displayable, on exact bound bytes."""
        origins = [
            EvaluationOrigin(origin_index=0, origin_date=self.d0, actual_class=OUTCOME_CLASS_BULL),
            EvaluationOrigin(origin_index=1, origin_date=self.d1, actual_class=OUTCOME_CLASS_BULL),
        ]
        tiny = 5e-324
        zero_rows = [DummyPrediction(0, self.d0, (1.0, 0.0, 0.0)), DummyPrediction(1, self.d1, (0.5, 0.5, 0.0))]
        tiny_rows = [DummyPrediction(0, self.d0, (0.5, 0.5, tiny)), DummyPrediction(1, self.d1, (0.5, 0.5, tiny))]
        uniform = [DummyPrediction(i, d, (1 / 3, 1 / 3, 1 / 3)) for i, d in ((0, self.d0), (1, self.d1))]
        comparison = score_comparison(origins, heuristic=zero_rows, frequency=tiny_rows, logistic=uniform)
        empty = score_comparison([], heuristic=[], frequency=[], logistic=[])
        result = self._study_result(
            development=self._partition("development", empty, []),
            test=self._partition("test", comparison, origins, cutoff_index=SYNTHETIC_TEST_CUTOFF),
        )

        raw_summary, _, desc = self._bound_to_exact_bytes(build_panel_summary(result))
        state = evaluate_ui_display_state(raw_summary, desc)
        self.assertEqual(state["display_state"], UI_STATE_DISPLAYABLE, state["reason"])
        models = state["summary_data"]["partitions"]["test"]["metrics"]["models"]
        self.assertIsNone(models["heuristic"]["mean_log_loss"])
        self.assertEqual(models["heuristic"]["log_loss_state"], "infinite")
        self.assertAlmostEqual(models["frequency"]["mean_log_loss"], -math.log(tiny), places=9)
        self.assertEqual(models["frequency"]["class_recall"], [None, None, 0.0])
        development = state["summary_data"]["partitions"]["development"]["metrics"]["models"]["heuristic"]
        self.assertEqual(development["log_loss_state"], "empty")
        self.assertIsNone(development["mean_brier"])

        unavailable = build_panel_summary(self._study_result(test=self._unavailable_partition("test", cutoff_index=SYNTHETIC_TEST_CUTOFF)))
        raw_unavailable, _, unavailable_desc = self._bound_to_exact_bytes(unavailable)
        self.assertEqual(evaluate_ui_display_state(raw_unavailable, unavailable_desc)["display_state"], UI_STATE_DISPLAYABLE)

        signed = build_panel_summary(self.study_result)
        perfect = signed["partitions"]["test"]["metrics"]["models"]["frequency"]
        perfect.update(mean_brier=-0.0, mean_log_loss=-0.0)
        heuristic = signed["partitions"]["test"]["metrics"]["models"]["heuristic"]
        heuristic["class_recall"][2] = -0.0
        next(b for b in heuristic["reliability_bins"] if b["count"] and b["observed_frequency"] == 0.0).update(observed_frequency=-0.0)
        raw_signed, _, signed_desc = self._bound_to_exact_bytes(signed)
        self.assertIn(b"-0.0", raw_signed)
        self.assertEqual(evaluate_ui_display_state(raw_signed, signed_desc)["display_state"], UI_STATE_DISPLAYABLE)

    def test_uncertainty_states_stay_distinct(self) -> None:
        """Statistical unavailable is distinct from partition comparison status."""
        summary = build_panel_summary(self._study_result(test=self._unavailable_partition("test", cutoff_index=SYNTHETIC_TEST_CUTOFF)))
        self.assertEqual(summary["uncertainty"]["status"], UNCERTAINTY_STATUS_UNAVAILABLE)
        self.assertEqual(summary["partitions"]["test"]["comparison_status"], STATUS_COMPARISON_UNAVAILABLE)
        self.assertEqual([b["block_length"] for b in summary["uncertainty"]["block_lengths"]], [20, 40, 60])

    def test_portable_summary_relations_bind_cutoffs_counts_and_reasons(self) -> None:
        """
        The summary relates its own blocks: cutoff dates to the declared cutoffs, the TEST index to
        the mature start, uncertainty n and span to TEST requested and the admitted span, and the
        reason to the TEST status, count and admitted gaps. Every negative keeps a valid
        uncertainty block of its own, so only the cross-block relation can reject it.
        """
        good = build_panel_summary(self.study_result)
        validate_summary_document(copy.deepcopy(good))
        # Stated oracle: 3 scored origins fill the 3-slot span from index 1, below every floor
        self.assertEqual(good["partitions"]["test"]["cutoff_index"], 1)
        self.assertEqual(good["partitions"]["test"]["cutoff_date"], "2022-01-04")
        self.assertEqual((good["uncertainty"]["n"], good["uncertainty"]["mature_span_count"]), (3, 3))
        self.assertEqual(good["uncertainty"]["reason"], "insufficient_nominal_blocks")
        self.assertAlmostEqual(good["uncertainty"]["point_differences"][0]["point_difference"], 0.4, places=12)
        self.assertAlmostEqual(good["uncertainty"]["point_differences"][1]["point_difference"], 0.4 - 2.0 / 3.0, places=12)

        # A scored cohort with one admitted gap: 3 scored origins in 4 slots keep their points and
        # take non_contiguous_test_cohort; the scored count is not the slot count
        gapped_admission = dict(
            _coherent_admission(self._partition("test", cutoff_index=SYNTHETIC_TEST_CUTOFF)),
            mature_test_end_index=5,
            mature_test_span_count=4,
            missing_vix_gap_positions=[4],
            missing_vix_gap_count=1,
            union_gap_positions=[4],
            union_gap_count=1,
        )
        gapped_admission["axis"] = dict(gapped_admission["axis"], session_count=5)
        points = tuple(dict(p) for p in self.study_result.uncertainty.point_differences)
        gapped_block = _valid_uncertainty_block(reason="non_contiguous_test_cohort", n=3, span=4, point_differences=points)
        gapped = build_panel_summary(dataclasses.replace(self.study_result, admission_inventory=gapped_admission, uncertainty=gapped_block))
        self.assertEqual(gapped["uncertainty"]["reason"], "non_contiguous_test_cohort")
        self.assertEqual(gapped["uncertainty"]["point_differences"], good["uncertainty"]["point_differences"])
        self.assertEqual(gapped["admission_summary"]["union_gap_count"], 1)

        # Comparison unavailable with 3 requested origins over the 3 gap-free slots: no point
        unavailable = build_panel_summary(self._study_result(test=self._unavailable_partition("test", cutoff_index=SYNTHETIC_TEST_CUTOFF)))
        self.assertEqual((unavailable["partitions"]["test"]["counts"]["requested_count"], unavailable["uncertainty"]["n"]), (3, 3))
        self.assertEqual([p["point_difference"] for p in unavailable["uncertainty"]["point_differences"]], [None, None])

        # Zero origins with every admitted slot gapped: 0 requested = 2 slots - 2 gaps
        empty = score_comparison([], heuristic=[], frequency=[], logistic=[])
        all_gap = build_panel_summary(self._study_result(test=self._partition("test", empty, [], cutoff_index=SYNTHETIC_TEST_CUTOFF)))
        self.assertEqual(
            (all_gap["admission_summary"]["mature_test_span_count"], all_gap["admission_summary"]["union_gap_count"], all_gap["uncertainty"]["reason"]),
            (2, 2, "empty_cohort"),
        )

        # Signed and near-zero arithmetic: equal stated means admit a zero or negative-zero point,
        # and a point inside the shared absolute tolerance is accepted
        for label, mean, point in (("equal_means_zero", 0.4, 0.0), ("equal_means_negative_zero", 0.4, -0.0), ("inside_tolerance", None, 0.4 + 5e-10)):
            doc = copy.deepcopy(good)
            if mean is not None:
                doc["partitions"]["test"]["metrics"]["models"]["frequency"]["mean_brier"] = mean
            doc["uncertainty"]["point_differences"][0]["point_difference"] = point
            with self.subTest(control=label):
                validate_summary_document(doc)

        def _claim_unavailable(doc: Dict[str, Any]) -> None:
            block = doc["uncertainty"]
            block["reason"] = "comparison_unavailable"
            for entry in block["point_differences"]:
                entry["point_difference"] = None
            for view in block["block_lengths"]:
                view["reason"] = "comparison_unavailable"

        def _claim_floor(doc: Dict[str, Any]) -> None:
            # A schema-valid below-floor block (n == span, points present) on an unavailable comparison
            block = doc["uncertainty"]
            block["reason"] = "insufficient_nominal_blocks"
            for entry in block["point_differences"]:
                entry["point_difference"] = 0.125
            for view in block["block_lengths"]:
                view["reason"] = "insufficient_nominal_blocks"

        def _point(pos: int, value: Any) -> Callable[[Dict[str, Any]], None]:
            def _apply(doc: Dict[str, Any]) -> None:
                entry = doc["uncertainty"]["point_differences"][pos]
                entry["point_difference"] = value(entry["point_difference"]) if callable(value) else value
            return _apply

        complement = "partitions.test.counts.requested_count: must be the admitted span"
        cases: List[Any] = [
            ("test_cutoff_date", good, lambda d: d["partitions"]["test"].update(cutoff_date="2022-01-05"), "partitions.test.cutoff_date"),
            ("development_cutoff_date", good, lambda d: d["chronological_cutoffs"].update(development_start="2022-01-02"), "partitions.development.cutoff_date"),
            ("test_index_not_mature_start", good, lambda d: d["partitions"]["test"].update(cutoff_index=2), "partitions.test.cutoff_index"),
            ("n_and_span_not_requested", good, lambda d: d["uncertainty"].update(n=2, mature_span_count=2), "summary.uncertainty: n and mature_span_count"),
            # One added slot is gapped, so requested still equals span minus gaps and the span check runs
            (
                "span_not_admitted_span",
                good,
                lambda d: d["admission_summary"].update(mature_test_end_index=5, mature_test_span_count=4, missing_vix_gap_count=1, union_gap_count=1),
                "summary.uncertainty: n and mature_span_count",
            ),
            ("scored_claims_comparison_unavailable", good, _claim_unavailable, "summary.uncertainty.reason: must be 'insufficient_nominal_blocks'"),
            ("unavailable_comparison_claims_floor", unavailable, _claim_floor, "summary.uncertainty.reason: must be 'comparison_unavailable'"),
            # Gap counts that do not complement the requested cohort in the admitted span
            ("gap_without_a_free_slot", good, lambda d: d["admission_summary"].update(missing_vix_gap_count=1, union_gap_count=1), complement),
            ("gapped_with_two_gaps", gapped, lambda d: d["admission_summary"].update(missing_vix_gap_count=2, union_gap_count=2), complement),
            ("gapped_gaps_removed", gapped, lambda d: d["admission_summary"].update(missing_vix_gap_count=0, union_gap_count=0), complement),
            ("all_gap_gaps_removed", all_gap, lambda d: d["admission_summary"].update(missing_vix_gap_count=0, union_gap_count=0), complement),
            # Signed TEST points against the stated TEST means (heuristic 0.4, frequency 0, logistic 2/3)
            ("frequency_point_sign_flipped", good, _point(0, lambda v: -v), "uncertainty.point_differences: heuristic_minus_frequency"),
            ("logistic_point_off_by_a_hundredth", good, _point(1, lambda v: v + 0.01), "uncertainty.point_differences: heuristic_minus_logistic"),
            ("point_just_beyond_tolerance", good, _point(0, lambda v: v + 2e-9), "uncertainty.point_differences: heuristic_minus_frequency"),
            ("gapped_point_sign_flipped", gapped, _point(1, lambda v: -v), "uncertainty.point_differences: heuristic_minus_logistic"),
        ]
        for name, base, mutate, expected in cases:
            doc = copy.deepcopy(base)
            mutate(doc)
            with self.subTest(case=name):
                with self.assertRaises(ValueError) as ctx:
                    validate_summary_document(doc)
                self.assertIn(expected, str(ctx.exception))
                self._assert_rejected_on_exact_bindings(doc, expected)


class TestHistoricalResultsValidation(_StudyResultsFixtures):
    """
    Validation and semantic relation unit tests for Historical S3 artifacts,
    schemas (Admission v2, Summary v3, Result v3, Run Manifest v3, Approval v1),
    withheld hashes, and H -> C -> A joins.
    """

    def setUp(self) -> None:
        super().setUp()
        self.config_id = {"raw_byte_count": 512, "sha256": "C" * 64}
        self.admission_id = {"raw_byte_count": 1024, "sha256": "A" * 64}
        self.approval_doc = {
            "schema_version": SCHEMA_VERSION_APPROVAL_V1,
            "decision_id": "decision-2026-test-001",
            "approved_by": "Synthetic test approver",
            "approved_at": "2026-11-09T00:00:00Z",
            "decision": "APPROVED_FOR_ONE_PRIVATE_STUDY",
            "config_identity": dict(self.config_id),
            "admission_identity": dict(self.admission_id),
            "source_use_evidence": [
                {
                    "input_refs": [{"role": "nifty", "file_index": 0}],
                    "evidence": [
                        {
                            "path": "/private/evidence.pdf",
                            "raw_byte_count": 100,
                            "sha256": "E" * 64,
                        }
                    ],
                    "note": "Provider terms",
                },
                {
                    "input_refs": [{"role": "vix", "file_index": 0}],
                    "evidence": [
                        {
                            "path": "/private/vix_evidence.pdf",
                            "raw_byte_count": 100,
                            "sha256": "F" * 64,
                        }
                    ],
                    "note": "VIX terms",
                },
            ],
            "calendar_evidence": {
                "evidence": [
                    {
                        "path": "/private/cal_evidence.pdf",
                        "raw_byte_count": 50,
                        "sha256": "1" * 64,
                    }
                ],
                "independent_source_note": "Verified trading holidays against exchange schedule",
            },
            "public_sharing_status": "NOT_CLEARED",
            "raw_file_hash_release": "WITHHELD",
        }

    def test_validate_approval_document(self) -> None:
        """Valid approval document succeeds; malformed or tampered documents fail closed."""
        validate_approval_document(self.approval_doc)

        # Missing required key
        doc = copy.deepcopy(self.approval_doc)
        del doc["decision"]
        with self.assertRaises(ValueError):
            validate_approval_document(doc)

        # Unknown key
        doc = copy.deepcopy(self.approval_doc)
        doc["extra_field"] = "bad"
        with self.assertRaises(ValueError):
            validate_approval_document(doc)

        # Bad schema version
        doc = copy.deepcopy(self.approval_doc)
        doc["schema_version"] = "nivesh-historical-admission-v2"
        with self.assertRaises(ValueError):
            validate_approval_document(doc)

        # Bad decision
        doc = copy.deepcopy(self.approval_doc)
        doc["decision"] = "REJECTED"
        with self.assertRaises(ValueError):
            validate_approval_document(doc)

        # Bad sharing_status
        doc = copy.deepcopy(self.approval_doc)
        doc["public_sharing_status"] = "PUBLIC"
        with self.assertRaises(ValueError):
            validate_approval_document(doc)

        # Bad hash_release
        doc = copy.deepcopy(self.approval_doc)
        doc["raw_file_hash_release"] = "RELEASED"
        with self.assertRaises(ValueError):
            validate_approval_document(doc)

        # Non-ISO date
        doc = copy.deepcopy(self.approval_doc)
        doc["approved_at"] = "invalid-date"
        with self.assertRaises(ValueError):
            validate_approval_document(doc)

        # Bad config identity
        doc = copy.deepcopy(self.approval_doc)
        doc["config_identity"]["raw_byte_count"] = -1
        with self.assertRaises(ValueError):
            validate_approval_document(doc)

        # Bad input_refs
        doc = copy.deepcopy(self.approval_doc)
        doc["source_use_evidence"][0]["input_refs"][0]["file_index"] = -1
        with self.assertRaises(ValueError):
            validate_approval_document(doc)

    def test_validate_admission_document_v2(self) -> None:
        """Admission v2 document verifies historical rule derivation and rejects violations."""
        # N=2220, E=2200, T=1400, D=1000
        adm_v2 = {
            "schema_version": SCHEMA_VERSION_ADMISSION_V2,
            "data_kind": DATA_KIND_HISTORICAL,
            "protocol_id": STUDY_PROTOCOL_ID,
            "date_selection_rule": DATE_SELECTION_RULE_HISTORICAL,
            "development_start": "2017-01-01",
            "test_start": "2019-01-01",
            "development_start_index": 1000,
            "inputs": {
                "nifty": {
                    "files": [
                        {
                            "raw_byte_count": 100,
                            "sha256": "1" * 64,
                            "record_count": 1200,
                            "observed_first_date": "2013-01-01",
                            "observed_last_date": "2018-01-01",
                        },
                        {
                            "raw_byte_count": 100,
                            "sha256": "2" * 64,
                            "record_count": 1020,
                            "observed_first_date": "2018-01-02",
                            "observed_last_date": "2023-01-01",
                        },
                    ],
                    "record_count": 2220,
                    "observed_first_date": "2013-01-01",
                    "observed_last_date": "2023-01-01",
                },
                "vix": {
                    "files": [
                        {
                            "raw_byte_count": 100,
                            "sha256": "3" * 64,
                            "record_count": 2220,
                            "observed_first_date": "2013-01-01",
                            "observed_last_date": "2023-01-01",
                        }
                    ],
                    "record_count": 2220,
                    "observed_first_date": "2013-01-01",
                    "observed_last_date": "2023-01-01",
                },
                "calendar": {
                    "raw_byte_count": 500,
                    "sha256": "4" * 64,
                    "session_count": 2220,
                },
            },
            "axis": {
                "session_count": 2220,
                "first_date": "2013-01-01",
                "last_date": "2023-01-01",
            },
            "mature_test_start_index": 1400,
            "mature_test_end_index": 2200,
            "mature_test_span_count": 800,
            "warmup_gap_positions": [],
            "warmup_gap_count": 0,
            "missing_vix_gap_positions": [],
            "missing_vix_gap_count": 0,
            "union_gap_positions": [],
            "union_gap_count": 0,
            "gap_digest": "0" * 64,
            "policy": ADMISSION_POLICY,
        }
        validate_admission_document(adm_v2)

        # N < 2220
        bad_n = copy.deepcopy(adm_v2)
        bad_n["axis"]["session_count"] = 2219
        with self.assertRaises(ValueError):
            validate_admission_document(bad_n)

        # Inverted development_start and test_start
        bad_dates = copy.deepcopy(adm_v2)
        bad_dates["development_start"] = "2020-01-01"
        bad_dates["test_start"] = "2019-01-01"
        with self.assertRaises(ValueError):
            validate_admission_document(bad_dates)

        # Wrong mature test span
        bad_span = copy.deepcopy(adm_v2)
        bad_span["mature_test_span_count"] = 799
        with self.assertRaises(ValueError):
            validate_admission_document(bad_span)

        # Wrong derivation: e != N - 20
        bad_e = copy.deepcopy(adm_v2)
        bad_e["mature_test_end_index"] = 2201
        with self.assertRaises(ValueError):
            validate_admission_document(bad_e)

    def test_validate_summary_document_v3(self) -> None:
        """Summary v3 enforces withheld raw file/calendar hashes and 3-key provenance identity."""
        summary_v3 = {
            "schema_version": SCHEMA_VERSION_SUMMARY_V3,
            "run_id": "run-historical-001",
            "study_id": "historical-test-study",
            "protocol_id": STUDY_PROTOCOL_ID,
            "data_kind": DATA_KIND_HISTORICAL,
            "development_status": DEVELOPMENT_STATUS_HISTORICAL,
            "claim_label": "Retrospective replay of the frozen current heuristic",
            "dataset_attribution": {
                "source_kind": SOURCE_KIND_HISTORICAL,
                "asset_label": "Admitted historical market data on the Nifty 50 price-index schema",
                "series_id": "^NSEI",
                "coverage_start_date": "2013-01-01",
                "coverage_end_date": "2023-01-01",
            },
            "replay_identity": {
                "claim_label": "Retrospective replay of the frozen current heuristic",
                "script": {"raw_byte_count": 100, "sha256": "1" * 64},
                "request": {"raw_byte_count": 100, "sha256": "2" * 64},
                "response": {"raw_byte_count": 100, "sha256": "3" * 64},
                "model_sha256": "4" * 64,
                "build_manifest_sha256": "5" * 64,
                "calculation_id": "calc-1",
            },
            "provenance_identity": {
                "config_sha256": "C" * 64,
                "admission_sha256": "A" * 64,
                "approval_sha256": "9" * 64,
            },
            "chronological_cutoffs": {
                "development_start": "2017-01-01",
                "test_start": "2019-01-01",
            },
            "admission_summary": {
                "mature_test_start_index": 1400,
                "mature_test_end_index": 2200,
                "mature_test_span_count": 800,
                # Zero requested origins: every one of the 800 admitted slots is a gap
                "warmup_gap_count": 0,
                "missing_vix_gap_count": 800,
                "union_gap_count": 800,
                "gap_digest": "0" * 64,
                "policy": ADMISSION_POLICY,
            },
            "fixed_definitions": {
                "classes": list(ORDERED_CLASSES),
                "neutral_band": "inclusive_half_percent",
                "horizon_sessions": 20,
                "primary_probability_metric": "mean_brier",
                "log_loss_zero_policy": "infinite_with_count_retention",
            },
            "partitions": {
                name: {
                    "partition": name,
                    "cutoff_index": 1000 if name == "development" else 1400,
                    "cutoff_date": "2017-01-01" if name == "development" else "2019-01-01",
                    "counts": {
                        "raw_partition_count": 0,
                        "eligible_count": 0,
                        "excluded_count": 0,
                        "requested_count": 0,
                        "exclusion_reason_counts": {},
                        "model_available_counts": {"heuristic": 0, "frequency": 0, "logistic": 0},
                    },
                    "comparison_status": STATUS_COMPARISON_UNAVAILABLE,
                    "comparison_unavailable_reasons": ["empty_partition"],
                    "method_states": {
                        "heuristic": {"available": True},
                        "frequency": {"available": False, "unavailable_reason": "no_fit_rows"},
                        "logistic": {"available": False, "unavailable_reason": "no_fit_rows", "failure_stage": None},
                    },
                    "metrics": None,
                }
                for name in ("development", "test")
            },
            # Requested 0 over the 800 admitted slots: the block counts the TEST cohort, not the span
            "uncertainty": _uncertainty_document(_valid_uncertainty_block(span=800)),
            "limitations": list(HISTORICAL_LIMITATIONS),
        }
        validate_summary_document(summary_v3)

        # Contaminated with raw file hash
        contaminated = copy.deepcopy(summary_v3)
        contaminated["provenance_identity"]["nifty_input_sha256"] = "F" * 64
        with self.assertRaises(ValueError):
            validate_summary_document(contaminated)

        # Missing approval_sha256
        missing_h = copy.deepcopy(summary_v3)
        del missing_h["provenance_identity"]["approval_sha256"]
        with self.assertRaises(ValueError):
            validate_summary_document(missing_h)

        # Comparison unavailable with 800 requested TEST origins (logistic not converged): n is the
        # requested count, the 800-slot span is the admitted one and no point estimate is kept
        unavailable = copy.deepcopy(summary_v3)
        unavailable["admission_summary"].update(missing_vix_gap_count=0, union_gap_count=0)
        test = unavailable["partitions"]["test"]
        test["counts"] = {
            "raw_partition_count": 820,
            "eligible_count": 800,
            "excluded_count": 20,
            "requested_count": 800,
            "exclusion_reason_counts": {"unknown_outcome": 20},
            "model_available_counts": {"heuristic": 800, "frequency": 800, "logistic": 0},
        }
        test["comparison_unavailable_reasons"] = ["logistic: not_converged"]
        test["method_states"] = {
            "heuristic": {"available": True},
            "frequency": {"available": True, "unavailable_reason": None},
            "logistic": {"available": False, "unavailable_reason": "not_converged", "failure_stage": "fit"},
        }
        unavailable["uncertainty"] = _uncertainty_document(_valid_uncertainty_block(n=800, span=800))
        validate_summary_document(copy.deepcopy(unavailable))
        self.assertEqual((unavailable["uncertainty"]["n"], unavailable["uncertainty"]["reason"]), (800, "comparison_unavailable"))
        self.assertEqual([p["point_difference"] for p in unavailable["uncertainty"]["point_differences"]], [None, None])

        # One admitted gap leaves 799 requested origins in the 800 slots, and comparison_unavailable
        # still outranks the gap, as in common_unavailable_reason
        gapped = copy.deepcopy(unavailable)
        gapped["admission_summary"].update(missing_vix_gap_count=1, union_gap_count=1)
        gapped["partitions"]["test"]["counts"].update(
            eligible_count=799,
            excluded_count=21,
            requested_count=799,
            exclusion_reason_counts={"missing_vix": 1, "unknown_outcome": 20},
            model_available_counts={"heuristic": 799, "frequency": 799, "logistic": 0},
        )
        gapped["uncertainty"]["n"] = 799
        validate_summary_document(copy.deepcopy(gapped))
        self.assertEqual(gapped["uncertainty"]["reason"], "comparison_unavailable")

        # The same gap under the full 800-origin cohort leaves requested above span minus gaps
        full_with_gap = copy.deepcopy(unavailable)
        full_with_gap["admission_summary"].update(missing_vix_gap_count=1, union_gap_count=1)
        with self.assertRaises(ValueError) as ctx:
            validate_summary_document(full_with_gap)
        self.assertIn("partitions.test.counts.requested_count: must be the admitted span 800 minus union_gap_count 1 (799), got 800", str(ctx.exception))

        def _window(doc: Dict[str, Any], start: int, development: int, span: int = 800) -> None:
            doc["admission_summary"].update(mature_test_start_index=start, mature_test_end_index=start + span, mature_test_span_count=span)
            doc["partitions"]["test"]["cutoff_index"] = start
            doc["partitions"]["development"]["cutoff_index"] = development

        def _span(doc: Dict[str, Any], span: int) -> None:
            _window(doc, 1400, 1000, span)
            doc["uncertainty"]["mature_span_count"] = span

        cases: List[Any] = [
            ("n_zero_with_requested_origins", lambda d: d["uncertainty"].update(n=0), "summary.uncertainty: n and mature_span_count"),
            ("uncertainty_span_not_admitted", lambda d: d["uncertainty"].update(mature_span_count=801), "summary.uncertainty: n and mature_span_count"),
            ("test_cutoff_date", lambda d: d["partitions"]["test"].update(cutoff_date="2019-01-02"), "partitions.test.cutoff_date"),
            ("development_cutoff_date", lambda d: d["partitions"]["development"].update(cutoff_date="2017-01-02"), "partitions.development.cutoff_date"),
            ("test_index_not_mature_start", lambda d: d["partitions"]["test"].update(cutoff_index=1401), "partitions.test.cutoff_index"),
            # 801, not 799: a block of n=800 over 799 slots would fail the uncertainty schema first
            ("span_not_800", lambda d: _span(d, 801), "requires 800 mature slots"),
            ("test_index_below_historical_minimum", lambda d: _window(d, 1399, 999), "TEST index of at least 1400"),
            ("development_index_not_test_minus_400", lambda d: _window(d, 1400, 999), "TEST index minus 400 (1000)"),
        ]
        for name, mutate, expected in cases:
            doc = copy.deepcopy(unavailable)
            mutate(doc)
            with self.subTest(case=name):
                with self.assertRaises(ValueError) as ctx:
                    validate_summary_document(doc)
                self.assertIn(expected, str(ctx.exception))

        # A later valid window (T=1401, D=1001) passes: 1400 is a minimum, not a fixed index
        later = copy.deepcopy(unavailable)
        _window(later, 1401, 1001)
        validate_summary_document(later)

    def test_validate_result_document_v3(self) -> None:
        """Result v3 requires approval_identity and valid multi-file inputs."""
        res_v3 = {
            "schema_version": SCHEMA_VERSION_RESULT_V3,
            "run_id": "run-historical-001",
            "study_id": "historical-test-study",
            "protocol_id": STUDY_PROTOCOL_ID,
            "data_kind": DATA_KIND_HISTORICAL,
            "development_status": DEVELOPMENT_STATUS_HISTORICAL,
            "claim_label": "Retrospective replay of the frozen current heuristic",
            "coverage_start_date": "2013-01-01",
            "coverage_end_date": "2023-01-01",
            "development_start": "2017-01-01",
            "test_start": "2019-01-01",
            "admission": {
                "schema_version": SCHEMA_VERSION_ADMISSION_V2,
                "data_kind": DATA_KIND_HISTORICAL,
                "protocol_id": STUDY_PROTOCOL_ID,
                "date_selection_rule": DATE_SELECTION_RULE_HISTORICAL,
                "development_start": "2017-01-01",
                "test_start": "2019-01-01",
                "development_start_index": 1000,
                "inputs": {
                    "nifty": {"files": [{"raw_byte_count": 100, "sha256": "1" * 64, "record_count": 2220, "observed_first_date": "2013-01-01", "observed_last_date": "2023-01-01"}], "record_count": 2220, "observed_first_date": "2013-01-01", "observed_last_date": "2023-01-01"},
                    "vix": {"files": [{"raw_byte_count": 100, "sha256": "2" * 64, "record_count": 2220, "observed_first_date": "2013-01-01", "observed_last_date": "2023-01-01"}], "record_count": 2220, "observed_first_date": "2013-01-01", "observed_last_date": "2023-01-01"},
                    "calendar": {"raw_byte_count": 50, "sha256": "3" * 64, "session_count": 2220},
                },
                "axis": {"session_count": 2220, "first_date": "2013-01-01", "last_date": "2023-01-01"},
                "mature_test_start_index": 1400,
                "mature_test_end_index": 2200,
                "mature_test_span_count": 800,
                "warmup_gap_positions": [],
                "warmup_gap_count": 0,
                "missing_vix_gap_positions": [],
                "missing_vix_gap_count": 0,
                "union_gap_positions": [],
                "union_gap_count": 0,
                "gap_digest": "0" * 64,
                "policy": ADMISSION_POLICY,
            },
            "config_identity": {"raw_byte_count": 100, "sha256": "C" * 64},
            "admission_identity": {"raw_byte_count": 100, "sha256": "A" * 64},
            "approval_identity": {"raw_byte_count": 100, "sha256": "9" * 64},
            "input_identities": {
                "nifty": {
                    "units": "index_points",
                    "source_kind": SOURCE_KIND_HISTORICAL,
                    "files": [{"path": "/p/n.csv", "raw_byte_count": 100, "sha256": "1" * 64, "record_count": 2220, "observed_first_date": "2013-01-01", "observed_last_date": "2023-01-01", "source_url": None, "requested_interval": None, "acquisition_time": None, "source_use_note": "test"}],
                },
                "vix": {
                    "units": "volatility_index_points",
                    "source_kind": SOURCE_KIND_HISTORICAL,
                    "files": [{"path": "/p/v.csv", "raw_byte_count": 100, "sha256": "2" * 64, "record_count": 2220, "observed_first_date": "2013-01-01", "observed_last_date": "2023-01-01", "source_url": None, "requested_interval": None, "acquisition_time": None, "source_use_note": "test"}],
                },
                "calendar": {"raw_byte_count": 50, "sha256": "3" * 64, "session_count": 2220},
            },
            "source_identities": copy.deepcopy(SOURCE_IDENTITIES),
            "runtime_identities": copy.deepcopy(RUNTIME_IDENTITIES),
            "model_identity": copy.deepcopy(MODEL_IDENTITY),
            "build_identity": dict(BUILD_IDENTITY),
            "replay_identity": {
                "claim_label": "Retrospective replay of the frozen current heuristic",
                "script": {"raw_byte_count": 100, "sha256": "1" * 64},
                "request": {"raw_byte_count": 100, "sha256": "2" * 64},
                "response": {"raw_byte_count": 100, "sha256": "3" * 64},
                "model_sha256": "4" * 64,
                "build_manifest_sha256": "5" * 64,
                "calculation_id": "calc-1",
            },
            "private_paths": {"config": "/p/config.json", "approval": "/p/approval.json"},
            "comparator_metadata": copy.deepcopy(COMPARATOR_METADATA),
            "partitions": {
                name: {
                    "partition": name,
                    "cutoff_index": 1000 if name == "development" else 1400,
                    "cutoff_date": "2017-01-01" if name == "development" else "2019-01-01",
                    "requested_indices": [],
                    "requested_dates": [],
                    "counts": {"raw_partition_count": 0, "eligible_count": 0, "excluded_count": 0, "requested_count": 0, "exclusion_reason_counts": {}, "model_available_counts": {"heuristic": 0, "frequency": 0, "logistic": 0}},
                    "comparison_status": STATUS_COMPARISON_UNAVAILABLE,
                    "comparison_unavailable_reasons": ["empty_partition"],
                    "method_states": {
                        "heuristic": {"available": True},
                        "frequency": {"available": False, "unavailable_reason": "no_fit_rows"},
                        "logistic": {"available": False, "unavailable_reason": "no_fit_rows", "failure_stage": None},
                    },
                    "frequency_block": {"method": "frequency", "partition": name, "fitting_indices": [], "cutoff_index": 1000 if name == "development" else 1400, "cutoff_date": "2017-01-01" if name == "development" else "2019-01-01", "requested_indices": [], "prediction_count": 0, "unavailable_reason": "no_fit_rows", "fit": None},
                    "logistic_block": {"method": "logistic", "partition": name, "fitting_indices": [], "cutoff_index": 1000 if name == "development" else 1400, "cutoff_date": "2017-01-01" if name == "development" else "2019-01-01", "class_counts": [0, 0, 0], "regime_counts": [0] * len(VALID_REGIMES), "requested_indices": [], "prediction_count": 0, "unavailable_reason": "no_fit_rows", "failure_stage": None, "fit": None},
                    "metrics": None,
                    "per_origin_records": [],
                }
                for name in ("development", "test")
            },
            "warnings": [],
            "input_warnings": [],
            "uncertainty": _uncertainty_document(_valid_uncertainty_block()),
            "limitations": list(HISTORICAL_LIMITATIONS),
        }
        validate_result_document(res_v3)

        # Missing approval_identity
        bad_res = copy.deepcopy(res_v3)
        del bad_res["approval_identity"]
        with self.assertRaises(ValueError):
            validate_result_document(bad_res)

    def test_validate_run_manifest_document_v3(self) -> None:
        """Run manifest v3 requires 13 artifacts and approval_identity."""
        artifacts = [{"path": name, "bytes": 10, "sha256": "0" * 64} for name in sorted(REQUIRED_MANIFEST_ARTIFACTS_V3)]
        man_v3 = {
            "schema_version": SCHEMA_VERSION_RUN_MANIFEST_V3,
            "run_id": "run-historical-001",
            "study_id": "historical-test-study",
            "protocol_id": STUDY_PROTOCOL_ID,
            "data_kind": DATA_KIND_HISTORICAL,
            "development_status": DEVELOPMENT_STATUS_HISTORICAL,
            "coverage_start_date": "2013-01-01",
            "coverage_end_date": "2023-01-01",
            "summary_schema_version": SCHEMA_VERSION_SUMMARY_V3,
            "artifacts": artifacts,
            "config_identity": {"raw_byte_count": 100, "sha256": "C" * 64},
            "admission_identity": {"raw_byte_count": 100, "sha256": "A" * 64},
            "approval_identity": {"raw_byte_count": 100, "sha256": "9" * 64},
            "input_identities": {
                "nifty": {
                    "units": "index_points",
                    "source_kind": SOURCE_KIND_HISTORICAL,
                    "files": [{"path": "/p/n.csv", "raw_byte_count": 100, "sha256": "1" * 64, "record_count": 2220, "observed_first_date": "2013-01-01", "observed_last_date": "2023-01-01", "source_url": None, "requested_interval": None, "acquisition_time": None, "source_use_note": "test"}],
                },
                "vix": {
                    "units": "volatility_index_points",
                    "source_kind": SOURCE_KIND_HISTORICAL,
                    "files": [{"path": "/p/v.csv", "raw_byte_count": 100, "sha256": "2" * 64, "record_count": 2220, "observed_first_date": "2013-01-01", "observed_last_date": "2023-01-01", "source_url": None, "requested_interval": None, "acquisition_time": None, "source_use_note": "test"}],
                },
                "calendar": {"raw_byte_count": 50, "sha256": "3" * 64, "session_count": 2220},
            },
            "source_identities": copy.deepcopy(SOURCE_IDENTITIES),
            "runtime_identities": copy.deepcopy(RUNTIME_IDENTITIES),
            "model_identity": copy.deepcopy(MODEL_IDENTITY),
            "build_identity": dict(BUILD_IDENTITY),
            "completed": True,
            "completion_timestamp": "2026-11-09T00:00:00Z",
        }
        validate_run_manifest_document(man_v3)

        # Missing historical-admission.json (only 12 artifacts)
        bad_artifacts = [a for a in artifacts if a["path"] != "historical-admission.json"]
        bad_man = copy.deepcopy(man_v3)
        bad_man["artifacts"] = bad_artifacts
        with self.assertRaises(ValueError):
            validate_run_manifest_document(bad_man)

        # Missing approval_identity
        bad_man2 = copy.deepcopy(man_v3)
        del bad_man2["approval_identity"]
        with self.assertRaises(ValueError):
            validate_run_manifest_document(bad_man2)

    def _write_valid_historical_run_dir(self, run_dir: Path) -> None:
        """
        Writes one coherent historical completed run at the rule minimum N=2220: D=1000, T=1400,
        E=2200, one scored DEV target at 1000 that both TEST refit pools keep, an 800-origin test
        cohort with logistic not converged (nothing is resampled), two
        Nifty originals and one VIX original bound identically by A, C and the result, and H
        naming the exact C and A bytes with every configured file referenced once.
        """
        n = 2220
        d_idx, t_idx, e_idx = n - 1220, n - 820, n - 20
        axis = tuple(self.d0 + datetime.timedelta(days=i) for i in range(n))
        origins = [EvaluationOrigin(origin_index=i, origin_date=axis[i], actual_class=ORDERED_CLASSES[i % 3]) for i in range(t_idx, e_idx)]
        indices = tuple(o.origin_index for o in origins)
        records = tuple(
            PerOriginRecord(
                origin_index=o.origin_index,
                origin_date=o.origin_date,
                origin_close="100.00",
                maturity_index=o.origin_index + 20,
                maturity_date=axis[o.origin_index + 20],
                maturity_close="101.00",
                actual_class=o.actual_class,
                score_state="unscored",
                heuristic_expected_direction="NEUTRAL / RANGE-BOUND",
                heuristic=MethodOriginRecord("available", (0.2, 0.5, 0.3)),
                frequency=MethodOriginRecord("available", (0.25, 0.5, 0.25)),
                logistic=MethodOriginRecord("unavailable", None),
            )
            for o in origins
        )
        # One eligible DEV target at D matures at D+20 < T, so the planner keeps it in the TEST refit
        dev_origin = EvaluationOrigin(origin_index=d_idx, origin_date=axis[d_idx], actual_class=OUTCOME_CLASS_BEAR)
        dev_comparison = score_comparison(
            [dev_origin],
            heuristic=[DummyPrediction(d_idx, axis[d_idx], self.h_preds[0].probabilities)],
            frequency=[DummyPrediction(d_idx, axis[d_idx], self.f_preds[0].probabilities)],
            logistic=[DummyPrediction(d_idx, axis[d_idx], self.l_preds[0].probabilities)],
        )
        # Listed pools only: past warmup and maturing strictly before D and T, development inside refit
        test_cutoff = dict(cutoff_index=t_idx, cutoff_date=axis[t_idx].isoformat(), fitting=RUN_REFIT_POOL + (d_idx,))
        test_part = PartitionResult(
            partition="test",
            cutoff_index=t_idx,
            cutoff_date=axis[t_idx],
            requested_indices=indices,
            requested_dates=tuple(o.origin_date for o in origins),
            counts=PartitionCounts(
                raw_partition_count=n - t_idx,
                eligible_count=800,
                excluded_count=20,
                requested_count=800,
                exclusion_reason_counts={"unknown_outcome": 20},
                model_available_counts={"heuristic": 800, "frequency": 800, "logistic": 0},
            ),
            heuristic_available=True,
            frequency_available=True,
            frequency_unavailable_reason=None,
            frequency_block=_frequency_block("test", indices, **test_cutoff),
            logistic_available=False,
            logistic_unavailable_reason="not_converged",
            logistic_failure_stage="fit",
            logistic_block=_logistic_block("test", indices, available=False, **test_cutoff),
            comparison_status=STATUS_COMPARISON_UNAVAILABLE,
            comparison_unavailable_reasons=("logistic: not_converged",),
            comparison_metrics=None,
            per_origin_records=records,
        )
        request = UncertaintyRequest(
            axis_dates=axis,
            test_start_index=t_idx,
            requested_keys=tuple(RequestedKey(o.origin_index, o.origin_date) for o in origins),
            comparison_status=STATUS_COMPARISON_UNAVAILABLE,
            method_available={"heuristic": True, "frequency": True, "logistic": False},
            method_rows=None,
            union_gap_positions=(),
        )
        raw_input = serialize_uncertainty_input(request)
        res = compute_uncertainty(
            dataclasses.replace(request, input_identity=self._bytes_identity(raw_input)),
            max_resample_positions=24000000,
            runtime_identity={
                "python_implementation": RUNTIME_IDENTITIES["python_implementation"],
                "python_version": RUNTIME_IDENTITIES["python_version"],
            },
        )

        def _file(digit: str, count: int, first: int, last: int) -> Dict[str, Any]:
            return {
                "raw_byte_count": 1000 + count,
                "sha256": digit * 64,
                "record_count": count,
                "observed_first_date": axis[first].isoformat(),
                "observed_last_date": axis[last].isoformat(),
            }

        files = {"nifty": [_file("1", 1200, 0, 1199), _file("2", n - 1200, 1200, n - 1)], "vix": [_file("3", n, 0, n - 1)]}
        units = {"nifty": "index_points", "vix": "volatility_index_points"}
        calendar = {"raw_byte_count": 5000, "sha256": "4" * 64, "session_count": n}
        adm_doc = {
            "schema_version": SCHEMA_VERSION_ADMISSION_V2,
            "data_kind": DATA_KIND_HISTORICAL,
            "protocol_id": STUDY_PROTOCOL_ID,
            "date_selection_rule": DATE_SELECTION_RULE_HISTORICAL,
            "development_start": axis[d_idx].isoformat(),
            "test_start": axis[t_idx].isoformat(),
            "development_start_index": d_idx,
            "inputs": {
                role: {
                    "files": entries,
                    "record_count": sum(e["record_count"] for e in entries),
                    "observed_first_date": entries[0]["observed_first_date"],
                    "observed_last_date": entries[-1]["observed_last_date"],
                }
                for role, entries in files.items()
            },
            "axis": {"session_count": n, "first_date": axis[0].isoformat(), "last_date": axis[-1].isoformat()},
            "mature_test_start_index": t_idx,
            "mature_test_end_index": e_idx,
            "mature_test_span_count": 800,
            "warmup_gap_positions": [],
            "warmup_gap_count": 0,
            "missing_vix_gap_positions": [],
            "missing_vix_gap_count": 0,
            "union_gap_positions": [],
            "union_gap_count": 0,
            "gap_digest": hashlib.sha256(b"[]").hexdigest().upper(),
            "policy": ADMISSION_POLICY,
        }
        adm_doc["inputs"]["calendar"] = dict(calendar)
        admission_bytes = serialize_strict_json(adm_doc)

        def _private(role: str, idx: int, entry: Mapping[str, Any]) -> Dict[str, Any]:
            return {
                "path": f"/synthetic/private/{role}-{idx}.csv",
                "raw_byte_count": entry["raw_byte_count"],
                "sha256": entry["sha256"],
                "source_url": f"https://synthetic.invalid/{role}-{idx}.csv",
                "requested_interval": None,
                "acquisition_time": None,
                "source_use_note": "Neutral pointer to the private approval record",
            }

        input_identities = {
            role: {
                "units": units[role],
                "source_kind": SOURCE_KIND_HISTORICAL,
                "files": [
                    dict(_private(role, i, e), record_count=e["record_count"], observed_first_date=e["observed_first_date"], observed_last_date=e["observed_last_date"])
                    for i, e in enumerate(entries)
                ],
            }
            for role, entries in files.items()
        }
        input_identities["calendar"] = dict(calendar)
        config_bytes = serialize_strict_json(
            {
                "schema_version": SCHEMA_VERSION_CONFIG_V3,
                "study_id": "historical-toy-study",
                "protocol_id": STUDY_PROTOCOL_ID,
                "data_kind": DATA_KIND_HISTORICAL,
                "development_status": DEVELOPMENT_STATUS_HISTORICAL,
                "development_start": axis[d_idx].isoformat(),
                "test_start": axis[t_idx].isoformat(),
                "date_selection_rule": DATE_SELECTION_RULE_HISTORICAL,
                "workspace_root": SAVED_WORKSPACE_LABEL,
                "allowed_output_parent": "/synthetic/runs",
                "timeout_seconds": SAVED_TIMEOUT_SECONDS,
                "inputs": dict(
                    {
                        role: {"units": units[role], "source_kind": SOURCE_KIND_HISTORICAL, "files": [_private(role, i, e) for i, e in enumerate(entries)]}
                        for role, entries in files.items()
                    },
                    calendar={"path": "/synthetic/private/calendar.json", "raw_byte_count": calendar["raw_byte_count"], "sha256": calendar["sha256"]},
                ),
                "admission": dict(self._bytes_identity(admission_bytes), path="/synthetic/private/admission.json"),
                # Saved bindings the live loader would accept: closed dependency set and the model pin
                "tools": _saved_tools(),
                "source_modules": SOURCE_IDENTITIES,
                "runtime": {
                    "python_version": RUNTIME_IDENTITIES["python_version"],
                    "python_implementation": RUNTIME_IDENTITIES["python_implementation"],
                    "dependency_versions": dict(RUNTIME_IDENTITIES["dependency_versions"]),
                },
                "uncertainty": {"protocol_id": UNCERTAINTY_PROTOCOL_ID, "max_resample_positions": 24000000},
            }
        )
        approval_doc = copy.deepcopy(self.approval_doc)
        approval_doc["config_identity"] = self._bytes_identity(config_bytes)
        approval_doc["admission_identity"] = self._bytes_identity(admission_bytes)
        approval_doc["source_use_evidence"][0]["input_refs"] = [{"role": "nifty", "file_index": 0}, {"role": "nifty", "file_index": 1}]
        approval_bytes = serialize_strict_json(approval_doc)

        sr = dataclasses.replace(
            self._study_result(
                development=self._partition("development", dev_comparison, [dev_origin], cutoff_index=d_idx, fitting=RUN_DEVELOPMENT_POOL),
                test=test_part,
                uncertainty=UncertaintyBlock.from_result(res),
            ),
            replay_identity=_captured_replay_identity(),
            study_id="historical-toy-study",
            data_kind=DATA_KIND_HISTORICAL,
            development_status=DEVELOPMENT_STATUS_HISTORICAL,
            coverage_start_date=axis[0],
            coverage_end_date=axis[-1],
            development_start=axis[d_idx],
            test_start=axis[t_idx],
            admission_inventory=adm_doc,
            config_identity=self._bytes_identity(config_bytes),
            admission_identity=self._bytes_identity(admission_bytes),
            input_identities=input_identities,
            approval_identity=self._bytes_identity(approval_bytes),
            private_paths={"config": "/synthetic/private/config.json", "approval": "/synthetic/private/approval.json"},
            limitations=HISTORICAL_LIMITATIONS,
        )
        summary_bytes = serialize_strict_json(build_panel_summary(sr))
        file_map = {
            "panel-summary.json": summary_bytes,
            "result.json": serialize_strict_json(build_result_document(sr)),
            "predictions.json": serialize_strict_json(build_predictions_document(sr)),
            "report.md": render_report_markdown(sr).encode("utf-8"),
            "admission.json": admission_bytes,
            "uncertainty-input.json": raw_input,
            "uncertainty-diagnostics.json": serialize_strict_json(build_uncertainty_diagnostics_document(res.diagnostics)),
            "config.json": config_bytes,
            "historical-admission.json": approval_bytes,
            **_replay_files(),
        }
        for name, data in file_map.items():
            (run_dir / name).write_bytes(data)
        self._rehash_historical(run_dir)

    def _rehash_historical(
        self,
        run_dir: Path,
        summary_mutate: Optional[Callable[[Dict[str, Any]], None]] = None,
        *,
        bind_config_to_admission: bool = True,
    ) -> None:
        """
        Recomputes every digest that names a changed artifact, in A -> C -> H -> result -> summary ->
        manifest order, so only the semantic relation under test can still object. C's own A
        binding is left alone only when that binding is the forgery under test.
        """

        def _read(name: str) -> Dict[str, Any]:
            return parse_strict_json_bytes((run_dir / name).read_bytes())

        admission_id = self._bytes_identity((run_dir / "admission.json").read_bytes())
        if bind_config_to_admission:
            config = _read("config.json")
            config["admission"].update(admission_id)
            (run_dir / "config.json").write_bytes(serialize_strict_json(config))
        config_id = self._bytes_identity((run_dir / "config.json").read_bytes())
        approval = _read("historical-admission.json")
        approval.update(config_identity=config_id, admission_identity=admission_id)
        (run_dir / "historical-admission.json").write_bytes(serialize_strict_json(approval))
        approval_id = self._bytes_identity((run_dir / "historical-admission.json").read_bytes())

        result = _read("result.json")
        result.update(config_identity=config_id, admission_identity=admission_id, approval_identity=approval_id)
        (run_dir / "result.json").write_bytes(serialize_strict_json(result))
        summary = _read("panel-summary.json")
        summary["provenance_identity"] = {"config_sha256": config_id["sha256"], "admission_sha256": admission_id["sha256"], "approval_sha256": approval_id["sha256"]}
        if summary_mutate is not None:
            summary_mutate(summary)
        (run_dir / "panel-summary.json").write_bytes(serialize_strict_json(summary))

        artifacts = []
        for name in sorted(REQUIRED_MANIFEST_ARTIFACTS_V3):
            data = (run_dir / name).read_bytes()
            artifacts.append({"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest().upper()})
        (run_dir / "run-manifest.json").write_bytes(
            serialize_strict_json(
                self._manifest_doc(
                    (run_dir / "panel-summary.json").read_bytes(),
                    study_id=result["study_id"],
                    data_kind=DATA_KIND_HISTORICAL,
                    development_status=DEVELOPMENT_STATUS_HISTORICAL,
                    coverage_start_date=datetime.date.fromisoformat(result["coverage_start_date"]),
                    coverage_end_date=datetime.date.fromisoformat(result["coverage_end_date"]),
                    artifacts=artifacts,
                    config_identity=config_id,
                    admission_identity=admission_id,
                    input_identities=result["input_identities"],
                    approval_identity=approval_id,
                )
            )
        )

    def test_semantic_relations_historical_pipeline(self) -> None:
        """
        A coherent 13-artifact historical run verifies; each rehashed contradiction then reaches the
        relation it names: closed mode, C labels and bindings, the second original file, H input
        reference coverage and the deterministic summary projection.
        """
        with tempfile.TemporaryDirectory() as tmp:
            template = Path(tmp) / "template" / "run-2026-test-001"
            template.mkdir(parents=True)
            self._write_valid_historical_run_dir(template)
            for check in (verify_study_artifacts_semantic_relations, verify_completed_run):
                ok, msg = check(template)
                self.assertTrue(ok, msg)
            files = {item.name: item.read_bytes() for item in template.iterdir()}
            admission = parse_strict_json_bytes(files["admission.json"])
            next_day = (datetime.date.fromisoformat(admission["test_start"]) + datetime.timedelta(days=1)).isoformat()

            def _synthetic_admission(docs: Dict[str, Dict[str, Any]]) -> None:
                v2 = docs["admission.json"]
                v1 = {key: v2[key] for key in v2 if key not in ("development_start_index",)}
                v1.update(schema_version=SCHEMA_VERSION_ADMISSION, data_kind=DATA_KIND_SYNTHETIC, date_selection_rule=DATE_SELECTION_RULE)
                v1["inputs"] = {
                    role: {key: v2["inputs"][role]["files"][0][key] for key in ("raw_byte_count", "sha256", "record_count")}
                    for role in ("nifty", "vix")
                }
                v1["inputs"]["calendar"] = v2["inputs"]["calendar"]
                docs["admission.json"] = v1
                docs["result.json"]["admission"] = v1

            def _second_file_count(docs: Dict[str, Dict[str, Any]]) -> None:
                for doc in (docs["admission.json"], docs["result.json"]["admission"]):
                    doc["inputs"]["nifty"]["files"][1]["record_count"] += 1
                    doc["inputs"]["nifty"]["record_count"] += 1

            def _refs(refs: List[Dict[str, Any]]) -> Callable[[Dict[str, Dict[str, Any]]], None]:
                return lambda docs: docs["historical-admission.json"]["source_use_evidence"][0].update(input_refs=refs)

            def _config(mutate: Callable[[Dict[str, Any]], None]) -> Callable[[Dict[str, Dict[str, Any]]], None]:
                return lambda docs: mutate(docs["config.json"])

            def _refit_without_development_target(docs: Dict[str, Dict[str, Any]]) -> None:
                # Both TEST lists drop the recorded DEV target 1000 together, with counts that still sum,
                # so warmup, maturity, method equality and DEV-pool containment all still pass
                result = docs["result.json"]
                self.assertEqual(result["partitions"]["development"]["requested_indices"], [1000])
                for method in ("frequency", "logistic"):
                    block = result["partitions"]["test"][f"{method}_block"]
                    self.assertIn(1000, block["fitting_indices"])
                    _set_pool(block, RUN_REFIT_POOL)

            nifty_files = lambda c: c["inputs"]["nifty"]["files"]  # noqa: E731
            cases: List[Any] = [
                ("admission_relabeled_synthetic", _synthetic_admission, None, "artifact mode"),
                ("config_rule_label", _config(lambda c: c.update(date_selection_rule=DATE_SELECTION_RULE)), None, "config.date_selection_rule"),
                ("config_test_start_label", _config(lambda c: c.update(test_start=next_day)), None, "config.test_start"),
                ("config_admission_binding", _config(lambda c: c["admission"].update(sha256="9" * 64)), None, "config.admission"),
                ("config_second_file_hash", _config(lambda c: nifty_files(c)[1].update(sha256="8" * 64)), None, "config.inputs.nifty.files[1]"),
                ("config_files_reordered", _config(lambda c: nifty_files(c).reverse()), None, "config.inputs.nifty.files[0]"),
                ("admission_second_file_count", _second_file_count, None, "admission.inputs.nifty.files[1]"),
                ("refit_omits_development_target", _refit_without_development_target, None, "refit pool omits recorded development targets [1000]"),
                ("H_omits_second_file", _refs([{"role": "nifty", "file_index": 0}]), None, "input_refs must cover"),
                ("H_repeats_first_file", _refs([{"role": "nifty", "file_index": 0}, {"role": "nifty", "file_index": 0}]), None, "input_refs must cover"),
                ("H_names_absent_file", _refs([{"role": "nifty", "file_index": 0}, {"role": "nifty", "file_index": 2}]), None, "input_refs must cover"),
                # The TEST cutoff date moves too, so the portable relations hold and only the projection objects
                (
                    "summary_test_start",
                    None,
                    lambda s: (s["chronological_cutoffs"].update(test_start=next_day), s["partitions"]["test"].update(cutoff_date=next_day)),
                    "panel-summary.json",
                ),
                ("summary_approval_digest", None, lambda s: s["provenance_identity"].update(approval_sha256="9" * 64), "panel-summary.json"),
                ("summary_gap_digest", None, lambda s: s["admission_summary"].update(gap_digest="E" * 64), "panel-summary.json"),
                ("summary_drops_holdout_caveat", None, lambda s: s["limitations"].pop(), "panel-summary.json"),
            ]
            for name, edit, summary_edit, expected in cases:
                run_dir = Path(tmp) / name / "run-2026-test-001"
                run_dir.mkdir(parents=True)
                for artifact, data in files.items():
                    (run_dir / artifact).write_bytes(data)
                if edit is not None:
                    docs = {artifact: parse_strict_json_bytes(files[artifact]) for artifact in ("admission.json", "config.json", "historical-admission.json", "result.json")}
                    edit(docs)
                    for artifact, doc in docs.items():
                        (run_dir / artifact).write_bytes(serialize_strict_json(doc))
                self._rehash_historical(run_dir, summary_edit, bind_config_to_admission=name != "config_admission_binding")
                with self.subTest(case=name):
                    for check in (verify_study_artifacts_semantic_relations, verify_completed_run):
                        ok, msg = check(run_dir)
                        self.assertFalse(ok)
                        self.assertIn(expected, msg)

            # Unrehashed byte drift still stops at the stale identity it breaks
            for artifact, expected in (("config.json", "config.json"), ("admission.json", "admission.json"), ("historical-admission.json", "historical-admission.json")):
                run_dir = Path(tmp) / f"stale_{artifact}" / "run-2026-test-001"
                run_dir.mkdir(parents=True)
                for name, data in files.items():
                    (run_dir / name).write_bytes(data + b"\n" if name == artifact else data)
                with self.subTest(stale=artifact):
                    ok, msg = verify_study_artifacts_semantic_relations(run_dir)
                    self.assertFalse(ok)
                    self.assertIn(expected, msg)

    def test_ui_treats_a_supported_schema_disagreement_as_stale_in_both_directions(self) -> None:
        """
        A genuinely valid synthetic-v2 summary and a coherent historical-v3 run summary, each
        with a descriptor carrying its exact bytes, hash, run, study and coverage. Only the
        supported schema pairing then decides between displayable and stale.
        """
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run-2026-test-001"
            run_dir.mkdir()
            self._write_valid_historical_run_dir(run_dir)
            self.assertTrue(verify_completed_run(run_dir)[0])
            v3_summary = (run_dir / "panel-summary.json").read_bytes()
            v3_manifest = (run_dir / "run-manifest.json").read_bytes()
        v2_summary, v2_manifest = self._bound_bytes()

        cases = (
            (SCHEMA_VERSION_SUMMARY_V2, v2_summary, v2_manifest, SCHEMA_VERSION_SUMMARY_V3),
            (SCHEMA_VERSION_SUMMARY_V3, v3_summary, v3_manifest, SCHEMA_VERSION_SUMMARY_V2),
        )
        for own_schema, raw_summary, raw_manifest, other_schema in cases:
            matching = build_candidate_descriptor(raw_summary, raw_manifest)
            with self.subTest(summary=own_schema, descriptor="matching"):
                self.assertEqual(json.loads(raw_summary.decode("utf-8"))["schema_version"], own_schema)
                state = evaluate_ui_display_state(raw_summary, matching)
                self.assertEqual(state["display_state"], UI_STATE_DISPLAYABLE, state["reason"])
                self.assertEqual(state["summary_data"]["schema_version"], own_schema)

            crossed = dataclasses.replace(matching, summary_schema_version=other_schema)
            with self.subTest(summary=own_schema, descriptor=other_schema):
                state = evaluate_ui_display_state(raw_summary, crossed)
                self.assertEqual(state["display_state"], UI_STATE_STALE)
                self.assertFalse(state["can_display_metrics"])
                self.assertIsNone(state["summary_data"])
                self.assertIn(other_schema, state["reason"])
                ok, msg = verify_promotion_binding(raw_summary, raw_manifest, crossed)
                self.assertFalse(ok)
                self.assertIn("summary_schema_version", msg)


if __name__ == "__main__":
    unittest.main()
