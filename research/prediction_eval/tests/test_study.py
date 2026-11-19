"""
Unit and Integration Tests for Offline Prediction Study Runner, Replay Adapter, and Lifecycle.

Classes:
  - TestStudyPure: Standard library tests (-E -B -S importable) covering configuration validation,
    input-only admission, the frozen-plan check, full replay response rejection through the real
    adapter with an in-process transport, native capture failures, exclusive attempts, output
    containment, coverage counts, partial availability and comparator reconciliation.
  - TestStudyIntegration: Scientific tests (require the logistic venv and the pinned candidate
    Node build) covering warning/thread ownership, real end-to-end runs through main, persisted
    independent oracles, gap composition, identity drift and failure lifecycle. A missing
    prerequisite is an error here, never a skip, and Node is never resolved from PATH.

Oracles are stated independently of the implementation: expected counts come from the planner
policy, labels from exact rational arithmetic on the fixture closes. Tests mutate only the files
they generate; drift in real sources or tools is simulated by changing the expected identity.
"""

from __future__ import annotations

import contextlib
import copy
import datetime
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple
import unittest
from unittest.mock import patch
import warnings

from research.prediction_eval.inputs import (
    align_pair,
    AlignedObservation,
    AlignedPair,
    FileInputSpec,
    InputValidationError,
    InputWarning,
    load_series,
    LoadedSeries,
)
from research.prediction_eval.features import (
    compute_nifty_features,
    FeatureSeries,
    NiftyFeatureRecord,
    PredictorPayload,
    PROTOCOL_ID as FEATURES_PROTOCOL_ID,
    REASON_WARMUP,
    REGIME_BULL,
    VALID_REGIMES,
    WARMUP_ORIGIN_INDEX,
)
from research.prediction_eval.outcomes import (
    compute_twenty_session_outcomes,
    HORIZON_SESSIONS,
    OUTCOME_CLASS_BEAR,
    OUTCOME_CLASS_BULL,
    OUTCOME_CLASS_NEUTRAL,
    TwentySessionOutcome,
)
from research.prediction_eval.replay_export import serialize_replay_input
from research.prediction_eval.splits import (
    build_split_plan,
    OriginSplitDecision,
    SplitPlan,
)
from research.prediction_eval.frequency import (
    build_frequency_predictions,
    FrequencyBlock,
    FrequencyPrediction,
)
import research.prediction_eval.study as study_mod
from research.prediction_eval.study import (
    _compare_field_aware_recursive,
    _evaluate_partition,
    _reconcile_comparator_blocks,
    _require_configuration_from_its_bytes,
    _resolve_contained_output,
    _RunLifecycle,
    ADMISSION_POLICY,
    BoundFile,
    compute_admission_inventory,
    DATA_KIND_HISTORICAL,
    DATA_KIND_SYNTHETIC,
    DATE_SELECTION_RULE,
    DATE_SELECTION_RULE_HISTORICAL,
    derive_historical_split_cutoffs,
    EXPECTED_BUILD_MANIFEST_PATH,
    EXPECTED_BUILD_SCHEMA_VERSION,
    EXPECTED_MODELS_PATH,
    EXPECTED_MODELS_SHA256,
    EXPECTED_REPLAY_SCRIPT_PATH,
    HeuristicPrediction,
    HISTORICAL_MAX_RESAMPLE_POSITIONS,
    load_study_configuration,
    load_study_configuration_file,
    main,
    parse_cli_args,
    parse_strict_json,
    prepare_historical_admission,
    prepare_input_admission,
    REPLAY_CLAIM_LABEL,
    REQUIRED_DEPENDENCIES,
    REQUIRED_SOURCE_MODULES,
    run_replay_adapter,
    run_study,
    STUDY_SCHEMA_VERSION_V2,
    STUDY_SCHEMA_VERSION_V3,
    SUPPORTED_CONFIG_MODES,
    verify_admission_against_reference_plan,
)
from research.prediction_eval.study_results import (
    build_candidate_descriptor,
    FAILURE_RECORD_NAME,
    HISTORICAL_LIMITATIONS,
    release_descriptor_document,
    REQUIRED_APPROVAL_KEYS,
    REQUIRED_MANIFEST_ARTIFACTS_V3,
    SCHEMA_VERSION_ADMISSION_V2,
    SCHEMA_VERSION_APPROVAL_V1,
    SCHEMA_VERSION_RESULT_V3,
    SCHEMA_VERSION_RUN_MANIFEST_V3,
    SCHEMA_VERSION_SUMMARY_V3,
    serialize_strict_json,
    STATUS_COMPARISON_UNAVAILABLE,
    STATUS_EMPTY,
    STATUS_SCORED,
    STUDY_PROTOCOL_ID,
    validate_admission_document,
    validate_approval_document,
    validate_result_document,
    validate_summary_document,
    verify_completed_run,
    verify_completion_binding,
    verify_promotion_binding,
)
# One validated ledger owner serves both gates; each call names its own gate budget
from research.prediction_eval.tests.test_uncertainty import (
    _complete_sampling_call,
    _reserve_sampling_budget,
)
import research.prediction_eval.uncertainty as uncertainty_mod
from research.prediction_eval.uncertainty import UncertaintyResourceError

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent
CHILD_ENV = "NIVESH_EVAL_CHILD_LOG_DIR"
INTEGRATION_BUDGET = 40000000
UNCERTAINTY_MODULE = "research/prediction_eval/uncertainty.py"

# Stated here, not derived from production, so a dropped or added module fails this oracle
EXPECTED_SOURCE_MODULES = frozenset(
    {
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
    }
)

_FILE_IDENTITY_CACHE: Dict[str, Dict[str, Any]] = {}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _identity(path: Path) -> Dict[str, Any]:
    data = Path(path).read_bytes()
    return {"raw_byte_count": len(data), "sha256": _sha(data)}


def _frozen_identity(path: Path) -> Dict[str, Any]:
    """Identity of an immutable tool file, cached because node.exe is large."""
    key = str(path)
    if key not in _FILE_IDENTITY_CACHE:
        _FILE_IDENTITY_CACHE[key] = _identity(Path(path))
    return _FILE_IDENTITY_CACHE[key]


def _bound(path: Path, identity: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    entry = dict(identity if identity is not None else _identity(path))
    entry["path"] = str(path)
    return entry


def _session_dates(total_sessions: int) -> List[datetime.date]:
    dates: List[datetime.date] = []
    cur = datetime.date(2021, 1, 4)
    while len(dates) < total_sessions:
        if cur.weekday() < 5 and cur != datetime.date(2021, 1, 26):
            dates.append(cur)
        cur += datetime.timedelta(days=1)
    return dates


def _wave_close(idx: int) -> str:
    return f"{15000.0 + math.sin(idx / 4.0) * 300.0:.2f}"


def _write_inputs(
    directory: Path,
    *,
    total_sessions: int = 290,
    close_fn: Callable[[int], str] = _wave_close,
    missing_vix: Sequence[int] = (),
) -> SimpleNamespace:
    """Writes synthetic Nifty, VIX and calendar files; returns their paths, dates and closes."""
    directory.mkdir(parents=True, exist_ok=False)
    dates = _session_dates(total_sessions)
    closes = [close_fn(idx) for idx in range(total_sessions)]
    nifty_lines = ["Date,Close"]
    vix_lines = ["Date,Close"]
    for idx, d in enumerate(dates):
        date_str = d.strftime("%d-%b-%Y")
        nifty_lines.append(f"{date_str},{closes[idx]}")
        if idx not in missing_vix:
            vix_lines.append(f"{date_str},{15.0 + math.cos(idx / 5.0) * 2.0:.2f}")
    nifty_path = directory / "nifty_synthetic.csv"
    vix_path = directory / "vix_synthetic.csv"
    calendar_path = directory / "calendar_synthetic.json"
    nifty_path.write_text("\n".join(nifty_lines) + "\n", encoding="utf-8")
    vix_path.write_text("\n".join(vix_lines) + "\n", encoding="utf-8")
    calendar_path.write_text(json.dumps({"sessions": [d.isoformat() for d in dates]}, indent=2), encoding="utf-8")
    return SimpleNamespace(nifty=nifty_path, vix=vix_path, calendar=calendar_path, dates=dates, closes=closes)


def _add_open_column(path: Path, overrides: Mapping[int, str]) -> None:
    """Gives a generated CSV a valid Open column, then the raw cells at the given data rows."""
    header, *rows = path.read_text(encoding="utf-8").splitlines()
    lines = [f"{header},Open"]
    for position, row in enumerate(rows):
        lines.append(f"{row},{overrides.get(position, row.split(',')[1])}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _input_binding(path: Path, units: str) -> Dict[str, Any]:
    entry = _bound(path)
    entry.update(
        {
            "units": units,
            "source_kind": "synthetic_fixture",
            "source_url": None,
            "requested_interval": None,
            "acquisition_time": None,
            "source_use_note": "Generated synthetic test fixture",
        }
    )
    return entry


def _valid_config_dict(root: Path) -> Dict[str, Any]:
    """A structurally valid configuration whose identities are placeholders."""
    placeholder = {"raw_byte_count": 10, "sha256": "A" * 64}

    def _file(name: str) -> Dict[str, Any]:
        return dict(placeholder, path=str(root / name))

    def _series(name: str, units: str) -> Dict[str, Any]:
        return dict(
            _file(name),
            units=units,
            source_kind="synthetic_fixture",
            source_url=None,
            requested_interval=None,
            acquisition_time=None,
            source_use_note="Generated synthetic test fixture",
        )

    return {
        "schema_version": STUDY_SCHEMA_VERSION_V2,
        "study_id": "study-s1",
        "protocol_id": STUDY_PROTOCOL_ID,
        "data_kind": "synthetic",
        "development_status": "synthetic_development",
        "development_start": "2023-01-02",
        "test_start": "2023-06-01",
        "date_selection_rule": DATE_SELECTION_RULE,
        "workspace_root": str(WORKSPACE_ROOT),
        "allowed_output_parent": str(root),
        "timeout_seconds": 30,
        "inputs": {
            "nifty": _series("nifty.csv", "index_points"),
            "vix": _series("vix.csv", "volatility_index_points"),
            "calendar": _file("calendar.json"),
        },
        "admission": _file("admission.json"),
        "tools": {
            "node_executable": _file("node.exe"),
            "python_executable": _file("python.exe"),
            "replay_script": _file("replay.cjs"),
            "candidate_build_manifest": _file("build.json"),
            "models": dict(_file("models.json"), sha256=EXPECTED_MODELS_SHA256),
        },
        "source_modules": {rel: dict(placeholder) for rel in REQUIRED_SOURCE_MODULES},
        "runtime": {
            "python_version": "3.12.0",
            "python_implementation": "CPython",
            "dependency_versions": {name: "1.0" for name in REQUIRED_DEPENDENCIES},
        },
        "uncertainty": {
            "protocol_id": "nivesh-paired-stationary-brier-v1",
            "max_resample_positions": 30000000,
        },
    }


def _make_ready_series() -> FeatureSeries:
    """A valid 201-row series: origins 0..199 are warmup and origin 200 is ready."""
    payload = PredictorPayload(
        ret_5d=0.01,
        rsi_14=55.0,
        macd_hist=0.5,
        vol_30d=0.15,
        rel_strength_20d=0.0,
        drawdown=-0.02,
        market_regime=REGIME_BULL,
    )
    records = []
    d = datetime.date(2024, 1, 1)
    for i in range(201):
        ready = i == 200
        records.append(
            NiftyFeatureRecord(
                origin_index=i,
                origin_date=d,
                origin_close=Decimal("20000.00"),
                vix_close=Decimal("15.00"),
                feature_ready=ready,
                payload=payload if ready else None,
                unready_reasons=() if ready else (REASON_WARMUP,),
            )
        )
        d += datetime.timedelta(days=1)
    return FeatureSeries(
        protocol_id=FEATURES_PROTOCOL_ID,
        axis_start_date=records[0].origin_date,
        records=tuple(records),
        calendar_status="not_checked",
        missing_sessions=(),
        extra_sessions=(),
        nifty_provenance=(),
        vix_provenance=(),
    )


TRUSTED_MODEL = {
    "path": EXPECTED_MODELS_PATH,
    "raw_byte_count": 41399,
    "sha256": EXPECTED_MODELS_SHA256,
    "platt_params": [1.42, 0.02],
}
TRUSTED_BUILD = {
    "schema_version": EXPECTED_BUILD_SCHEMA_VERSION,
    "mode": "candidate",
    "calculation_id": "preserved-directional-core-v1",
    "source_files": [{"path": "src/a.ts", "bytes": 12, "sha256": "B" * 64}],
    "toolchain": {"node_version": "v22.0.0", "node_executable": {"bytes": 99, "sha256": "C" * 64}},
    "compiler_exit": 0,
}


def _ready_forecast() -> Dict[str, Any]:
    return {
        "horizon": "20D",
        "days": 20,
        "probability_bullish": 0.46,
        "probability_neutral": 0.2,
        "probability_bearish": 0.34,
        "expected_direction": "NEUTRAL / RANGE-BOUND",
        "expected_return_pct": 0.38,
        "confidence": "LOW",
        "signal_quality": 5.1,
        "model_disagreement": {
            "components": {"technical": 22.8, "fundamental": 2.4, "event_news": 0, "macro_regime": 35, "cross_asset": 12},
            "dispersion_std": 12.5,
            "consensus_level": "High Consensus",
        },
        "top_bullish_drivers": ["a"],
        "top_bearish_drivers": ["b"],
    }


def _response_doc(series: FeatureSeries) -> Dict[str, Any]:
    """A faithful response to the exact request bytes of series."""
    request_bytes = serialize_replay_input(series)
    forecasts = [
        {
            "origin_index": rec.origin_index,
            "origin_date": rec.origin_date.isoformat(),
            "forecast": _ready_forecast() if rec.feature_ready else None,
        }
        for rec in series.records
    ]
    return {
        "schema_version": "nivesh-replay-output-v1",
        "claim_label": REPLAY_CLAIM_LABEL,
        "computed_provenance": {
            "request": {"raw_byte_count": len(request_bytes), "sha256": _sha(request_bytes)},
            "model": json.loads(json.dumps(TRUSTED_MODEL)),
            "build": json.loads(json.dumps(TRUSTED_BUILD)),
        },
        "declared_input": json.loads(request_bytes.decode("utf-8")),
        "forecasts": forecasts,
    }


class _FakeProcess:
    """In-process transport: no executable is launched."""

    def __init__(self, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0, errors: Sequence[Exception] = ()) -> None:
        self._stdout = stdout
        self._stderr = stderr
        self._final = returncode
        self._errors = list(errors)
        self.returncode: Optional[int] = None
        self.killed = False
        self.waited = False

    def communicate(self, timeout: Optional[float] = None) -> Tuple[bytes, bytes]:
        if self._errors:
            raise self._errors.pop(0)
        self.returncode = self._final
        return self._stdout, self._stderr

    def kill(self) -> None:
        self.killed = True
        self._final = -9

    def wait(self, timeout: Optional[float] = None) -> int:
        self.waited = True
        self.returncode = self._final
        return self._final


class TestStudyPure(unittest.TestCase):
    """Pure standard-library tests for study runner components (stdlib -E -B -S)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        env_patch = patch.dict(os.environ)
        env_patch.start()
        self.addCleanup(env_patch.stop)
        os.environ.pop(CHILD_ENV, None)

    def _adapt(
        self,
        series: FeatureSeries,
        process: Any,
        work_name: str = "work",
        timeout_seconds: int = 30,
    ) -> Tuple[Dict[int, HeuristicPrediction], Dict[str, Any]]:
        with patch.object(study_mod.subprocess, "Popen", return_value=process):
            return run_replay_adapter(
                series,
                node_executable=str(self.root / "node.exe"),
                replay_script=str(self.root / "replay.cjs"),
                workspace_root=str(self.root),
                work_dir=self.root / work_name,
                timeout_seconds=timeout_seconds,
                trusted_model=TRUSTED_MODEL,
                trusted_build_manifest=TRUSTED_BUILD,
            )

    def test_cli_argument_parser(self) -> None:
        """Verifies CLI argument parsing for --config and --output-dir."""
        args = parse_cli_args(["--config", "conf.json", "--output-dir", "out_dir"])
        self.assertEqual(args.config, "conf.json")
        self.assertEqual(args.output_dir, "out_dir")

        with self.assertRaises(SystemExit):
            parse_cli_args(["--config", "conf.json"])

    def test_main_in_process_rejects_before_any_write(self) -> None:
        """Actual main returns 1 on bad input and creates no run directory."""
        run_dir = self.root / "run_main"

        self.assertEqual(main(["--config", str(self.root / "absent.json"), "--output-dir", str(run_dir)]), 1)

        cases = {
            "unknown_key": dict(_valid_config_dict(self.root), surprise=1),
            "historical": dict(_valid_config_dict(self.root), data_kind="historical"),
            "timeout_above_limit": dict(_valid_config_dict(self.root), timeout_seconds=61),
            "legacy_v1": dict(_valid_config_dict(self.root), schema_version="nivesh-study-config-v1"),
            "cap_above_ceiling": dict(
                _valid_config_dict(self.root),
                uncertainty={"protocol_id": "nivesh-paired-stationary-brier-v1", "max_resample_positions": 30000001},
            ),
        }
        for name, doc in cases.items():
            config_path = self.root / f"{name}.json"
            config_path.write_text(json.dumps(doc), encoding="utf-8")
            with self.subTest(case=name):
                self.assertEqual(main(["--config", str(config_path), "--output-dir", str(run_dir)]), 1)
                self.assertFalse(run_dir.exists())

        # Duplicate keys never reach the schema
        duplicate = self.root / "duplicate.json"
        duplicate.write_text('{"study_id": "a", "study_id": "b"}', encoding="utf-8")
        self.assertEqual(main(["--config", str(duplicate), "--output-dir", str(run_dir)]), 1)
        self.assertFalse(run_dir.exists())

    def test_configuration_validation(self) -> None:
        """Verifies strict configuration parsing, type checks, and unknown key rejection."""
        valid_dict = _valid_config_dict(self.root)
        cfg = load_study_configuration(valid_dict)
        self.assertEqual(cfg.study_id, "study-s1")
        self.assertEqual(cfg.timeout_seconds, 30)
        self.assertEqual(cfg.development_start, datetime.date(2023, 1, 2))

        # Rejection of historical data_kind in S1
        bad_hist = dict(valid_dict, data_kind="historical")
        with self.assertRaises(InputValidationError) as ctx:
            load_study_configuration(bad_hist)
        self.assertEqual(ctx.exception.field, "data_kind")

        # Rejection of legacy v1 schema before key checks
        bad_v1 = dict(valid_dict, schema_version="nivesh-study-config-v1")
        bad_v1.pop("uncertainty", None)
        with self.assertRaises(InputValidationError) as ctx:
            load_study_configuration(bad_v1)
        self.assertEqual(ctx.exception.field, "schema_version")

        # Rejection of boolean in integer field
        bad_bool = dict(valid_dict, timeout_seconds=True)
        with self.assertRaises(InputValidationError) as ctx:
            load_study_configuration(bad_bool)
        self.assertEqual(ctx.exception.field, "timeout_seconds")

        # Rejection of unknown keys
        bad_key = dict(valid_dict, extra_unrecognized_key="surprise")
        with self.assertRaises(InputValidationError) as ctx:
            load_study_configuration(bad_key)
        self.assertEqual(ctx.exception.field, "extra_unrecognized_key")

        # Rejection of invalid chronological order
        bad_dates = dict(valid_dict, development_start="2023-06-01", test_start="2023-01-02")
        with self.assertRaises(InputValidationError) as ctx:
            load_study_configuration(bad_dates)
        self.assertEqual(ctx.exception.field, "development_start")

    def test_configuration_rejects_each_unbound_or_implicit_value(self) -> None:
        """Every field below would otherwise admit an implicit default, PATH or CWD dependency."""

        def _with(path: Sequence[str], value: Any) -> Dict[str, Any]:
            doc = json.loads(json.dumps(_valid_config_dict(self.root)))
            target = doc
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            return doc

        def _without(path: Sequence[str]) -> Dict[str, Any]:
            doc = json.loads(json.dumps(_valid_config_dict(self.root)))
            target = doc
            for key in path[:-1]:
                target = target[key]
            del target[path[-1]]
            return doc

        cases = {
            "timeout_61": _with(["timeout_seconds"], 61),
            "timeout_zero": _with(["timeout_seconds"], 0),
            "timeout_float": _with(["timeout_seconds"], 30.0),
            "node_on_path": _with(["tools", "node_executable", "path"], "node"),
            "relative_input": _with(["inputs", "nifty", "path"], "nifty.csv"),
            "relative_parent": _with(["allowed_output_parent"], "runs"),
            "wrong_protocol": _with(["protocol_id"], "proto"),
            "wrong_status": _with(["development_status"], "released"),
            "non_string_study": _with(["study_id"], 5),
            "unsafe_study": _with(["study_id"], "../evil"),
            "wrong_rule": _with(["date_selection_rule"], "looked_at_results"),
            "wrong_units": _with(["inputs", "vix", "units"], "percent"),
            "not_synthetic_source": _with(["inputs", "nifty", "source_kind"], "exchange"),
            "bad_sha": _with(["admission", "sha256"], "not-hex"),
            "bool_byte_count": _with(["admission", "raw_byte_count"], True),
            "unpinned_model": _with(["tools", "models", "sha256"], "B" * 64),
            "missing_timeout": _without(["timeout_seconds"]),
            "missing_parent": _without(["allowed_output_parent"]),
            "missing_admission": _without(["admission"]),
            "missing_module": _without(["source_modules", "research/prediction_eval/study.py"]),
            "missing_dependency": _without(["runtime", "dependency_versions", "numpy"]),
            "unknown_nested": _with(["tools", "extra"], {}),
            "missing_uncertainty_source": _without(["source_modules", UNCERTAINTY_MODULE]),
            "extra_source_module": _with(["source_modules", "research/prediction_eval/extra.py"], {"raw_byte_count": 1, "sha256": "A" * 64}),
            "bad_uncertainty_source_hash": _with(["source_modules", UNCERTAINTY_MODULE, "sha256"], "not-hex"),
            "missing_uncertainty_block": _without(["uncertainty"]),
            "missing_uncertainty_protocol": _without(["uncertainty", "protocol_id"]),
            "missing_uncertainty_cap": _without(["uncertainty", "max_resample_positions"]),
            "unknown_uncertainty_key": _with(["uncertainty", "replicates"], 100),
            "wrong_uncertainty_protocol": _with(["uncertainty", "protocol_id"], "other"),
        }
        for name, doc in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(InputValidationError):
                    load_study_configuration(doc)

        for cap in (0, -1, 30000001, True, False, 1.0, 30000000.0, "1", None, [1]):
            with self.subTest(cap=cap):
                with self.assertRaises(InputValidationError) as ctx:
                    load_study_configuration(_with(["uncertainty", "max_resample_positions"], cap))
                self.assertEqual(ctx.exception.field, "uncertainty.max_resample_positions")

        for cap in (1, 30000000):
            config = load_study_configuration(_with(["uncertainty", "max_resample_positions"], cap))
            self.assertEqual(config.uncertainty["max_resample_positions"], cap)

    def test_required_source_modules_are_the_stated_literal_set(self) -> None:
        self.assertEqual(set(REQUIRED_SOURCE_MODULES), set(EXPECTED_SOURCE_MODULES))
        self.assertEqual(len(REQUIRED_SOURCE_MODULES), len(EXPECTED_SOURCE_MODULES))
        self.assertIn(UNCERTAINTY_MODULE, REQUIRED_SOURCE_MODULES)

    def test_version_refusal_is_truthful_and_ordered_after_data_kind(self) -> None:
        """
        Under the closed compatibility table (schema_version, data_kind, development_status,
        date_selection_rule, source_kind), schema_version is validated first to select the expected mode.
        Unknown or unsupported schema versions fail on schema_version before any other field.
        Known schema versions then validate that data_kind matches that mode.
        """
        valid = _valid_config_dict(self.root)
        legacy = {key: value for key, value in valid.items() if key != "uncertainty"}

        for name, doc in {
            "literal_v1": dict(legacy, schema_version="nivesh-study-config-v1"),
            "missing": {key: value for key, value in legacy.items() if key != "schema_version"},
            "not_text": dict(legacy, schema_version=2),
        }.items():
            with self.subTest(case=name):
                with self.assertRaises(InputValidationError) as ctx:
                    load_study_configuration(doc)
                self.assertEqual(ctx.exception.field, "schema_version")
                self.assertIn("Unsupported configuration schema_version", str(ctx.exception))

        # A v1 document with data_kind="historical" fails on schema_version under the closed compatibility table
        with self.assertRaises(InputValidationError) as ctx:
            load_study_configuration(dict(legacy, schema_version="nivesh-study-config-v1", data_kind="historical"))
        self.assertEqual(ctx.exception.field, "schema_version")

        # Incompatible combinations with known schema versions fail on data_kind:
        with self.assertRaises(InputValidationError) as ctx:
            load_study_configuration(dict(valid, schema_version=STUDY_SCHEMA_VERSION_V2, data_kind="historical"))
        self.assertEqual(ctx.exception.field, "data_kind")

        with self.assertRaises(InputValidationError) as ctx:
            load_study_configuration(dict(valid, schema_version=STUDY_SCHEMA_VERSION_V3, data_kind="synthetic"))
        self.assertEqual(ctx.exception.field, "data_kind")

    def test_strict_json_rejects_overflowing_real(self) -> None:
        """1e999 parses to infinity without ever being a NaN or Infinity token."""
        with self.assertRaises(ValueError):
            parse_strict_json('{"key": 1e999}')
        with self.assertRaises(ValueError):
            parse_strict_json('{"key": 1, "key": 2}')

    def test_input_only_admission_gap_inventory(self) -> None:
        """
        Verifies that input-only admission computes warmup and missing-VIX gap union
        strictly on mature test span [T, N-20) without invoking outcomes or predictors.
        """
        # Create 250 synthetic observations
        start_date = datetime.date(2020, 1, 1)
        observations = []
        cur = start_date
        idx = 0
        while len(observations) < 250:
            if cur.weekday() < 5:
                # Missing VIX at origin 210 and 215
                vix_close = None if idx in (210, 215) else Decimal("15.00")
                observations.append(
                    AlignedObservation(
                        date=cur,
                        nifty_close=Decimal("15000.00"),
                        vix_close=vix_close,
                    )
                )
                idx += 1
            cur += datetime.timedelta(days=1)

        n_series = LoadedSeries("nifty50_price_index", (), (), ())
        v_series = LoadedSeries("india_vix", (), (), ())
        aligned = AlignedPair(
            nifty_series=n_series,
            vix_series=v_series,
            aligned_observations=tuple(observations),
            nifty_only_dates=(),
            vix_only_dates=(),
            calendar_status="matches_supplied_sessions",
            missing_sessions=(),
            extra_sessions=(),
        )

        test_start_date = observations[195].date
        inv = compute_admission_inventory(aligned, test_start=test_start_date)

        # Span is [195, 230)
        self.assertEqual(inv["mature_test_start_index"], 195)
        self.assertEqual(inv["mature_test_end_index"], 230)
        self.assertEqual(inv["mature_test_span_count"], 35)

        # Warmup gaps: 195, 196, 197, 198, 199 (5 gaps)
        self.assertEqual(inv["warmup_gap_positions"], (195, 196, 197, 198, 199))
        self.assertEqual(inv["warmup_gap_count"], 5)

        # Missing VIX gaps: 210, 215 (2 gaps)
        self.assertEqual(inv["missing_vix_gap_positions"], (210, 215))
        self.assertEqual(inv["missing_vix_gap_count"], 2)

        # Union gaps: 195, 196, 197, 198, 199, 210, 215 (7 gaps)
        self.assertEqual(inv["union_gap_positions"], (195, 196, 197, 198, 199, 210, 215))
        self.assertEqual(inv["union_gap_count"], 7)

        # Digest should be deterministic SHA-256
        self.assertTrue(isinstance(inv["gap_digest"], str) and len(inv["gap_digest"]) == 64)

    def test_mature_gap_reasons_overlap_without_double_counting(self) -> None:
        """A warmup origin with missing VIX counts once in the union and once per reason."""
        fixture = _write_inputs(self.root / "overlap", total_sessions=230, missing_vix=(197, 205))
        nifty = load_series("nifty50_price_index", fixture.nifty)
        vix = load_series("india_vix", fixture.vix)
        aligned = align_pair(nifty, vix, expected_sessions=fixture.dates)
        inv = compute_admission_inventory(aligned, test_start=fixture.dates[195])

        self.assertEqual(inv["warmup_gap_positions"], (195, 196, 197, 198, 199))
        self.assertEqual(inv["missing_vix_gap_positions"], (197, 205))
        self.assertEqual(inv["union_gap_positions"], (195, 196, 197, 198, 199, 205))
        self.assertEqual((inv["warmup_gap_count"], inv["missing_vix_gap_count"], inv["union_gap_count"]), (5, 2, 6))

    def test_admission_preparation_is_input_only(self) -> None:
        """Preparation succeeds with every outcome, feature, replay and scoring owner disabled."""
        fixture = _write_inputs(self.root / "inputs", missing_vix=(272,))

        def _forbidden(*args: Any, **kwargs: Any) -> None:
            raise AssertionError("input-only admission reached a forbidden owner")

        with patch.object(study_mod, "compute_twenty_session_outcomes", _forbidden), patch.object(
            study_mod, "compute_nifty_features", _forbidden
        ), patch.object(study_mod, "build_split_plan", _forbidden), patch.object(
            study_mod, "build_frequency_predictions", _forbidden
        ), patch.object(study_mod, "run_replay_adapter", _forbidden), patch.object(
            study_mod, "score_comparison", _forbidden
        ):
            record = prepare_input_admission(
                nifty_spec=FileInputSpec(file_path=fixture.nifty),
                vix_spec=FileInputSpec(file_path=fixture.vix),
                calendar_path=fixture.calendar,
                development_start=fixture.dates[235],
                test_start=fixture.dates[260],
            )

        # N=290, T=260: mature span [260, 270); 272 lies in the unknown tail, outside that span
        self.assertEqual(record["mature_test_start_index"], 260)
        self.assertEqual(record["mature_test_end_index"], 270)
        self.assertEqual(record["union_gap_positions"], [])
        self.assertEqual(record["policy"], ADMISSION_POLICY)
        self.assertEqual(record["inputs"]["nifty"]["sha256"], _sha(fixture.nifty.read_bytes()))
        self.assertEqual(record["inputs"]["calendar"]["sha256"], _sha(fixture.calendar.read_bytes()))
        self.assertNotIn("config", json.dumps(sorted(record.keys())))

    def test_admission_check_against_reference_plan(self) -> None:
        """Verifies early mismatch detection between admission inventory and reference plan."""
        frozen_gaps = [205]
        inv = {
            "mature_test_start_index": 200,
            "mature_test_end_index": 220,
            "union_gap_positions": frozen_gaps,
            "union_gap_count": 1,
            "gap_digest": _sha(json.dumps(frozen_gaps, separators=(",", ":")).encode("utf-8")),
        }

        def _plan(test_indices: Sequence[int]) -> SplitPlan:
            return SplitPlan(
                development_start=datetime.date(2022, 1, 1),
                test_start=datetime.date(2022, 6, 1),
                development_start_index=100,
                test_start_index=200,
                train_indices=(),
                development_indices=(),
                refit_indices=(),
                test_indices=tuple(test_indices),
                decisions=(),
            )

        # Mock SplitPlan where test_indices has 205 (so 205 was NOT excluded)
        # That means actual excluded in span is empty, but expected is (205,) -> mismatch!
        with self.assertRaises(InputValidationError) as ctx:
            verify_admission_against_reference_plan(inv, _plan(range(200, 220)))
        self.assertEqual(ctx.exception.field, "admission_inventory")

        # The planner agreeing with the frozen list passes
        verify_admission_against_reference_plan(inv, _plan([i for i in range(200, 220) if i != 205]))

        # A frozen digest or count that does not describe the same positions fails
        for key, value in (("gap_digest", "F" * 64), ("union_gap_count", 2)):
            with self.subTest(field=key):
                with self.assertRaises(InputValidationError):
                    verify_admission_against_reference_plan(dict(inv, **{key: value}), _plan([i for i in range(200, 220) if i != 205]))

        # Each substitution equals the frozen value, so only the native type can reject it
        for key, value in (
            ("union_gap_count", True),
            ("union_gap_count", 1.0),
            ("union_gap_positions", [205.0]),
            ("mature_test_start_index", 200.0),
            ("mature_test_end_index", 220.0),
        ):
            with self.subTest(field=key, value=value):
                with self.assertRaises(InputValidationError) as ctx:
                    verify_admission_against_reference_plan(dict(inv, **{key: value}), _plan([i for i in range(200, 220) if i != 205]))
                self.assertIn("native integer", str(ctx.exception))

    def test_replay_adapter_field_aware_echo_validation(self) -> None:
        """Verifies field-aware comparison for numbers, booleans, Close strings, and SHA."""
        expected = {
            "origin_index": 5,
            "origin_close": "18000.50",
            "feature_ready": True,
            "sha256": "87C4DB2A4EB3B40AE5F7499C977AB407FFE3C3BE367E4DAE8FD8AE1804F543CD",
            "payload": {
                "ret_5d": 0.015,
                "rsi_14": 55.0,
                "rel_strength_20d": 0,  # integer 0
            },
        }

        # Happy path with case-insensitive SHA, float 0.0 vs int 0 in payload
        actual_ok = {
            "origin_index": 5,
            "origin_close": "18000.50",
            "feature_ready": True,
            "sha256": "87c4db2a4eb3b40ae5f7499c977ab407ffe3c3be367e4dae8fd8ae1804f543cd",
            "payload": {
                "ret_5d": 0.015,
                "rsi_14": 55.0,
                "rel_strength_20d": 0.0,  # float 0.0 == 0
            },
        }
        # Should not raise
        _compare_field_aware_recursive(actual_ok, expected)

        # Reject boolean substitution for integer count
        actual_bool_idx = dict(actual_ok, origin_index=True)
        with self.assertRaises(ValueError):
            _compare_field_aware_recursive(actual_bool_idx, expected)

        # Reject boolean substitution in payload numeric field
        actual_bool_payload = dict(actual_ok, payload=dict(actual_ok["payload"], ret_5d=True))
        with self.assertRaises(ValueError):
            _compare_field_aware_recursive(actual_bool_payload, expected)

        # Reject modified Close string
        actual_bad_close = dict(actual_ok, origin_close="18000.51")
        with self.assertRaises(ValueError):
            _compare_field_aware_recursive(actual_bad_close, expected)

    def test_parse_strict_json_rejects_non_finite_tokens(self) -> None:
        """Verifies parse_strict_json rejects NaN, Infinity, -Infinity at parse time."""
        with self.assertRaises(ValueError):
            parse_strict_json('{"key": NaN}')
        with self.assertRaises(ValueError):
            parse_strict_json('{"key": Infinity}')
        with self.assertRaises(ValueError):
            parse_strict_json('{"key": -Infinity}')

    def test_adapter_accepts_faithful_response_and_maps_probabilities(self) -> None:
        """Maps bearish/neutral/bullish explicitly and keeps verbal direction separate."""
        series = _make_ready_series()
        response = json.dumps(_response_doc(series)).encode("utf-8")
        predictions, evidence = self._adapt(series, _FakeProcess(stdout=response))

        self.assertEqual(sorted(predictions), [200])
        self.assertEqual(predictions[200].probabilities, (0.34, 0.2, 0.46))
        self.assertEqual(predictions[200].expected_direction, "NEUTRAL / RANGE-BOUND")
        self.assertEqual(evidence["response"], {"raw_byte_count": len(response), "sha256": _sha(response)})
        self.assertEqual(evidence["immediate_child_exit"], 0)

    def test_adapter_tolerates_only_declared_representation_differences(self) -> None:
        """0 for 0.0, integral payload values, SHA case and int 0/1 probabilities are valid wire forms."""
        series = _make_ready_series()
        doc = _response_doc(series)
        payload = doc["declared_input"]["rows"][200]["payload"]
        payload["rel_strength_20d"] = 0
        payload["rsi_14"] = 55
        doc["computed_provenance"]["request"]["sha256"] = doc["computed_provenance"]["request"]["sha256"].lower()
        doc["computed_provenance"]["model"]["sha256"] = doc["computed_provenance"]["model"]["sha256"].lower()
        doc["computed_provenance"]["build"]["source_files"][0]["sha256"] = "b" * 64
        forecast = doc["forecasts"][200]["forecast"]
        forecast["probability_bullish"], forecast["probability_neutral"], forecast["probability_bearish"] = 1, 0, 0

        predictions, _ = self._adapt(series, _FakeProcess(stdout=json.dumps(doc).encode("utf-8")))
        self.assertEqual(predictions[200].probabilities, (0.0, 0.0, 1.0))

    def test_adapter_rejects_every_malformed_response(self) -> None:
        """Each mutation breaks exactly one contract; all go through the real adapter."""
        series = _make_ready_series()

        def _set(path: Sequence[Any], value: Any) -> Callable[[Dict[str, Any]], None]:
            def _apply(doc: Dict[str, Any]) -> None:
                target = doc
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value

            return _apply

        def _delete(path: Sequence[Any]) -> Callable[[Dict[str, Any]], None]:
            def _apply(doc: Dict[str, Any]) -> None:
                target = doc
                for key in path[:-1]:
                    target = target[key]
                del target[path[-1]]

            return _apply

        def _swap_rows(doc: Dict[str, Any]) -> None:
            doc["forecasts"][3], doc["forecasts"][4] = doc["forecasts"][4], doc["forecasts"][3]

        ready = ["forecasts", 200, "forecast"]
        prov = ["computed_provenance"]
        mutations = {
            "unknown_root_key": _set(["extra"], 1),
            "missing_root_key": _delete(["claim_label"]),
            "wrong_schema": _set(["schema_version"], "nivesh-replay-output-v2"),
            "wrong_claim": _set(["claim_label"], "Accurate forecast"),
            "unknown_provenance_key": _set(prov + ["extra"], {}),
            "request_extra_key": _set(prov + ["request", "extra"], 1),
            "request_count_float": lambda d: d["computed_provenance"]["request"].update(raw_byte_count=float(d["computed_provenance"]["request"]["raw_byte_count"])),
            "request_count_wrong": lambda d: d["computed_provenance"]["request"].update(raw_byte_count=1),
            "request_sha_wrong": _set(prov + ["request", "sha256"], "D" * 64),
            "request_sha_not_hex": _set(prov + ["request", "sha256"], "zz"),
            "model_sha_drift": _set(prov + ["model", "sha256"], "D" * 64),
            "model_path_drift": _set(prov + ["model", "path"], "other/models.json"),
            "model_count_bool": _set(prov + ["model", "raw_byte_count"], True),
            "model_platt_drift": _set(prov + ["model", "platt_params"], [1.42, 0.03]),
            "model_extra_key": _set(prov + ["model", "extra"], 1),
            "build_source_hash_drift": _set(prov + ["build", "source_files", 0, "sha256"], "D" * 64),
            "build_tool_hash_drift": _set(prov + ["build", "toolchain", "node_executable", "sha256"], "D" * 64),
            "build_node_version_drift": _set(prov + ["build", "toolchain", "node_version"], "v0.0.0"),
            "build_exit_bool": _set(prov + ["build", "compiler_exit"], False),
            "build_bytes_float": _set(prov + ["build", "source_files", 0, "bytes"], 12.0),
            "build_schema_drift": _set(prov + ["build", "schema_version"], "other"),
            "build_extra_key": _set(prov + ["build", "extra"], 1),
            "echo_changed_number": _set(["declared_input", "rows", 200, "payload", "rsi_14"], 55.5),
            "echo_number_beyond_binary64": _set(["declared_input", "rows", 200, "payload", "rsi_14"], 10 ** 400),
            "echo_integer_binary64_would_round": _set(["declared_input", "rows", 200, "payload", "ret_5d"], 2 ** 53 + 1),
            "forecast_number_beyond_binary64": _set(ready + ["signal_quality"], 10 ** 400),
            "echo_bool_number": _set(["declared_input", "rows", 200, "payload", "rsi_14"], True),
            "echo_changed_close": _set(["declared_input", "rows", 3, "origin_close"], "20000.01"),
            "echo_bool_index": _set(["declared_input", "rows", 1, "origin_index"], True),
            "echo_extra_key": _set(["declared_input", "extra"], 1),
            "row_index_true": _set(["forecasts", 1, "origin_index"], True),
            "row_index_false": _set(["forecasts", 0, "origin_index"], False),
            "row_index_float": _set(["forecasts", 1, "origin_index"], 1.0),
            "row_wrong_date": _set(["forecasts", 3, "origin_date"], "1999-01-01"),
            "row_extra_key": _set(["forecasts", 3, "extra"], 1),
            "row_missing_key": _delete(["forecasts", 3, "origin_date"]),
            "rows_reordered": _swap_rows,
            "row_removed": lambda d: d["forecasts"].pop(),
            "row_added": lambda d: d["forecasts"].append(dict(d["forecasts"][-1])),
            "unready_has_forecast": _set(["forecasts", 3, "forecast"], _ready_forecast()),
            "ready_null_forecast": _set(ready, None),
            "forecast_extra_key": _set(ready + ["direction"], "BULL"),
            "forecast_missing_key": _delete(ready + ["confidence"]),
            "forecast_wrong_horizon": _set(ready + ["horizon"], "5D"),
            "forecast_days_bool": _set(ready + ["days"], True),
            "forecast_bad_direction": _set(ready + ["expected_direction"], "UP"),
            "forecast_bad_confidence": _set(ready + ["confidence"], "CERTAIN"),
            "forecast_component_extra": _set(ready + ["model_disagreement", "components", "extra"], 1),
            "probability_bool": _set(ready + ["probability_bullish"], True),
            "probability_string": _set(ready + ["probability_neutral"], "0.2"),
            "probability_negative": _set(ready + ["probability_bearish"], -0.34),
            "probability_sum_off": _set(ready + ["probability_bullish"], 0.47),
            "probability_tiny_sum_off": _set(ready + ["probability_bullish"], 0.46 + 1e-9),
        }
        for name, mutate in mutations.items():
            doc = _response_doc(series)
            mutate(doc)
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    self._adapt(series, _FakeProcess(stdout=json.dumps(doc).encode("utf-8")), work_name=f"bad_{name}")

        faithful = json.dumps(_response_doc(series))
        raw_cases = {
            "duplicate_key": faithful.replace('{"schema_version":', '{"schema_version": "x", "schema_version":', 1),
            "nan_token": faithful.replace('"probability_bullish": 0.46', '"probability_bullish": NaN'),
            "infinity_token": faithful.replace('"probability_bullish": 0.46', '"probability_bullish": Infinity'),
            "overflow_real": faithful.replace('"probability_bullish": 0.46', '"probability_bullish": 1e999'),
            "not_object": "[]",
            "truncated": faithful[:100],
        }
        for name, text in raw_cases.items():
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    self._adapt(series, _FakeProcess(stdout=text.encode("utf-8")), work_name=f"raw_{name}")

        with self.assertRaises(ValueError):
            self._adapt(series, _FakeProcess(stdout=b"\xff\xfe"), work_name="raw_not_utf8")

    def test_adapter_timeout_boundary_is_enforced_without_launching(self) -> None:
        """The callable adapter cannot bypass the configured resource ceiling."""
        series = _make_ready_series()
        for bad in (61, 0, True, 30.0):
            with self.subTest(timeout=bad):
                with patch.object(study_mod.subprocess, "Popen") as popen:
                    with self.assertRaises(InputValidationError):
                        run_replay_adapter(
                            series,
                            node_executable=str(self.root / "node.exe"),
                            replay_script=str(self.root / "replay.cjs"),
                            workspace_root=str(self.root),
                            work_dir=self.root / "never",
                            timeout_seconds=bad,
                            trusted_model=TRUSTED_MODEL,
                            trusted_build_manifest=TRUSTED_BUILD,
                        )
                popen.assert_not_called()
        self.assertFalse((self.root / "never").exists())

    def test_adapter_rejects_path_resolved_node_without_launching(self) -> None:
        """A bare executable name would be resolved through PATH."""
        with patch.object(study_mod.subprocess, "Popen") as popen:
            with self.assertRaises(InputValidationError):
                run_replay_adapter(
                    _make_ready_series(),
                    node_executable="node",
                    replay_script=str(self.root / "replay.cjs"),
                    workspace_root=str(self.root),
                    work_dir=self.root / "never",
                    timeout_seconds=30,
                    trusted_model=TRUSTED_MODEL,
                    trusted_build_manifest=TRUSTED_BUILD,
                )
        popen.assert_not_called()

    def _receipt(self, work_name: str) -> Dict[str, Any]:
        return json.loads((self.root / work_name / "replay-invocation.json").read_text(encoding="utf-8"))

    def test_timeout_kills_child_and_keeps_truthful_receipt(self) -> None:
        series = _make_ready_series()
        expired = subprocess.TimeoutExpired(cmd="node", timeout=30)
        process = _FakeProcess(stdout=b"partial", stderr=b"late", errors=[expired])

        with self.assertRaises(RuntimeError) as ctx:
            self._adapt(series, process, work_name="timeout")

        self.assertIn("timed out", str(ctx.exception))
        self.assertTrue(process.killed)
        receipt = self._receipt("timeout")
        self.assertTrue(receipt["timed_out"])
        self.assertEqual(receipt["capture_state"], "drained_after_kill")
        self.assertEqual(receipt["immediate_child_exit"], -9)
        self.assertEqual((self.root / "timeout" / "replay-response.json").read_bytes(), b"partial")
        self.assertEqual((self.root / "timeout" / "replay-stderr.log").read_bytes(), b"late")

    def test_child_that_survives_kill_is_reported_incomplete(self) -> None:
        """A stuck drain ends in a bounded wait, and incomplete capture is never parsed."""
        series = _make_ready_series()
        expired = subprocess.TimeoutExpired(cmd="node", timeout=30)
        stuck = subprocess.TimeoutExpired(cmd="node", timeout=5)
        process = _FakeProcess(errors=[expired, stuck])

        with self.assertRaises(RuntimeError):
            self._adapt(series, process, work_name="stuck")

        self.assertTrue(process.killed)
        self.assertTrue(process.waited)
        receipt = self._receipt("stuck")
        self.assertEqual(receipt["capture_state"], "incomplete")
        self.assertIn("post-kill capture failed", receipt["capture_error"])

    def test_generic_capture_error_terminates_child_and_preserves_primary(self) -> None:
        series = _make_ready_series()
        process = _FakeProcess(errors=[OSError("pipe broke")])

        with self.assertRaises(RuntimeError) as ctx:
            self._adapt(series, process, work_name="capture")

        self.assertIn("pipe broke", str(ctx.exception))
        self.assertIsInstance(ctx.exception.__cause__, OSError)
        self.assertTrue(process.killed)
        receipt = self._receipt("capture")
        self.assertEqual(receipt["capture_state"], "error")
        self.assertIn("pipe broke", receipt["capture_error"])

    def test_launch_failure_has_receipt_without_exit(self) -> None:
        series = _make_ready_series()
        with patch.object(study_mod.subprocess, "Popen", side_effect=FileNotFoundError("no node")):
            with self.assertRaises(RuntimeError) as ctx:
                run_replay_adapter(
                    series,
                    node_executable=str(self.root / "node.exe"),
                    replay_script=str(self.root / "replay.cjs"),
                    workspace_root=str(self.root),
                    work_dir=self.root / "launch",
                    timeout_seconds=30,
                    trusted_model=TRUSTED_MODEL,
                    trusted_build_manifest=TRUSTED_BUILD,
                )
        self.assertIn("Failed to launch", str(ctx.exception))
        receipt = self._receipt("launch")
        self.assertEqual(receipt["launch_state"], "failed")
        self.assertIsNone(receipt["immediate_child_exit"])
        self.assertIsNone(receipt["stdout"])

    def test_nonzero_exit_retains_streams_and_is_not_parsed(self) -> None:
        series = _make_ready_series()
        response = json.dumps(_response_doc(series)).encode("utf-8")
        with self.assertRaises(RuntimeError) as ctx:
            self._adapt(series, _FakeProcess(stdout=response, stderr=b"Replay error: x", returncode=1), work_name="exit")
        self.assertIn("exited with code 1", str(ctx.exception))
        self.assertEqual(self._receipt("exit")["immediate_child_exit"], 1)
        self.assertEqual((self.root / "exit" / "replay-stderr.log").read_bytes(), b"Replay error: x")

    def test_attempts_are_claimed_exclusively(self) -> None:
        """A prior attempt keeps its bytes; ordinal naming alone would not guarantee this."""
        series = _make_ready_series()
        response = json.dumps(_response_doc(series)).encode("utf-8")
        work = self.root / "attempts"
        work.mkdir()
        prior = work / "replay-request.json"
        prior.write_bytes(b"earlier attempt")

        self._adapt(series, _FakeProcess(stdout=response), work_name="attempts")

        self.assertEqual(prior.read_bytes(), b"earlier attempt")
        self.assertEqual((work / "replay-request-002.json").read_bytes(), serialize_replay_input(series))
        self.assertEqual((work / "replay-response-002.json").read_bytes(), response)
        receipt = json.loads((work / "replay-invocation-002.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["attempt"], 2)

    def test_partial_prior_attempt_blocks_rather_than_overwrites(self) -> None:
        """A stray response from a partial attempt fails loudly and keeps its bytes."""
        series = _make_ready_series()
        response = json.dumps(_response_doc(series)).encode("utf-8")
        work = self.root / "partial"
        work.mkdir()
        stray = work / "replay-response.json"
        stray.write_bytes(b"partial evidence")

        with self.assertRaises(RuntimeError) as ctx:
            self._adapt(series, _FakeProcess(stdout=response), work_name="partial")

        self.assertIn("Failed to record replay evidence", str(ctx.exception))
        self.assertEqual(stray.read_bytes(), b"partial evidence")

    def test_owned_root_keeps_exclusive_evidence_for_each_attempt(self) -> None:
        """Two attempts in one owned root keep separate request, stream and receipt files."""
        series = _make_ready_series()
        response = json.dumps(_response_doc(series)).encode("utf-8")

        self._adapt(series, _FakeProcess(stdout=response), work_name="owned")
        self._adapt(series, _FakeProcess(stdout=response, stderr=b"second attempt"), work_name="owned")

        work = self.root / "owned"
        for suffix in ("", "-002"):
            for stem, extension in (("request", "json"), ("response", "json"), ("stderr", "log"), ("invocation", "json")):
                self.assertTrue((work / f"replay-{stem}{suffix}.{extension}").exists(), f"{stem}{suffix}")
        self.assertEqual((work / "replay-stderr.log").read_bytes(), b"")
        self.assertEqual((work / "replay-stderr-002.log").read_bytes(), b"second attempt")
        first = json.loads((work / "replay-invocation.json").read_text(encoding="utf-8"))
        second = json.loads((work / "replay-invocation-002.json").read_text(encoding="utf-8"))
        self.assertEqual((first["attempt"], second["attempt"]), (1, 2))
        self.assertEqual(second["request"]["path"], str(work / "replay-request-002.json"))

    def test_inherited_child_log_dir_grants_no_write_authority(self) -> None:
        """An environment value names no destination, on success or on any failure path."""
        series = _make_ready_series()
        response = json.dumps(_response_doc(series)).encode("utf-8")
        outside = self.root / "outside" / "children"
        os.environ[CHILD_ENV] = str(outside)
        expired = subprocess.TimeoutExpired(cmd="node", timeout=30)

        self._adapt(series, _FakeProcess(stdout=response), work_name="success")

        failures = {
            "timeout": _FakeProcess(errors=[expired]),
            "capture": _FakeProcess(errors=[OSError("pipe broke")]),
            "exit": _FakeProcess(stderr=b"Replay error: x", returncode=1),
        }
        for name, process in failures.items():
            with self.subTest(case=name):
                with self.assertRaises(RuntimeError):
                    self._adapt(series, process, work_name=name)
                self.assertTrue((self.root / name / "replay-invocation.json").exists())

        with patch.object(study_mod.subprocess, "Popen", side_effect=FileNotFoundError("no node")):
            with self.assertRaises(RuntimeError):
                run_replay_adapter(
                    series,
                    node_executable=str(self.root / "node.exe"),
                    replay_script=str(self.root / "replay.cjs"),
                    workspace_root=str(self.root),
                    work_dir=self.root / "launch",
                    timeout_seconds=30,
                    trusted_model=TRUSTED_MODEL,
                    trusted_build_manifest=TRUSTED_BUILD,
                )
        self.assertTrue((self.root / "launch" / "replay-invocation.json").exists())

        self.assertFalse((self.root / "outside").exists())
        # The value is not passed to the child, so the receipt of the supplied mapping omits it
        self.assertNotIn(CHILD_ENV, self._receipt("success")["declared_environment"])
        self.assertEqual(os.environ[CHILD_ENV], str(outside))

    def test_replay_child_gets_only_the_declared_environment(self) -> None:
        """
        Synthetic sentinels stand in for runtime-affecting settings. The child mapping holds only
        SYSTEMROOT, TEMP and TMP on Windows, or TMPDIR on POSIX, when present; the receipt records
        exactly that mapping, and the parent environment is unchanged.
        """
        series = _make_ready_series()
        response = json.dumps(_response_doc(series)).encode("utf-8")
        sentinels = {
            "NODE_OPTIONS": "--require=nivesh-absent-sentinel-preload",
            "NODE_V8_COVERAGE": str(self.root / "coverage-sentinel"),
            "NODE_PATH": str(self.root / "node-path-sentinel"),
            "NODE_ENV": "sentinel",
            CHILD_ENV: str(self.root / "children-sentinel"),
            "NIVESH_EVAL_WORK_DIR": str(self.root / "work-sentinel"),
            "NIVESH_SYNTHETIC_SECRET_SENTINEL": "not-for-the-child",
        }
        admitted = {
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", str(self.root / "systemroot-sentinel")),
            "TEMP": str(self.root / "temp-sentinel"),
            "TMP": str(self.root / "tmp-sentinel"),
            "TMPDIR": str(self.root / "tmpdir-sentinel"),
        }
        expected_names = ("SYSTEMROOT", "TEMP", "TMP") if os.name == "nt" else ("TMPDIR",)
        os.environ.update(sentinels)
        os.environ.update(admitted)

        for case, absent in (("all_present", None), ("tmp_absent", "TMP" if os.name == "nt" else "TMPDIR")):
            with self.subTest(case=case):
                if absent is not None:
                    os.environ.pop(absent)
                parent_before = dict(os.environ)
                with patch.object(study_mod.subprocess, "Popen", return_value=_FakeProcess(stdout=response)) as popen:
                    run_replay_adapter(
                        series,
                        node_executable=str(self.root / "node.exe"),
                        replay_script=str(self.root / "replay.cjs"),
                        workspace_root=str(self.root),
                        work_dir=self.root / f"env_{case}",
                        timeout_seconds=30,
                        trusted_model=TRUSTED_MODEL,
                        trusted_build_manifest=TRUSTED_BUILD,
                    )
                kwargs = popen.call_args.kwargs
                expected = {name: admitted[name] for name in expected_names if name != absent}
                self.assertEqual(kwargs["env"], expected)
                self.assertEqual(self._receipt(f"env_{case}")["declared_environment"], expected)
                for name in sentinels:
                    self.assertNotIn(name, kwargs["env"])
                self.assertEqual(dict(os.environ), parent_before)
                self.assertIs(kwargs["shell"], False)
                self.assertEqual(popen.call_args.args[0][0], str(self.root / "node.exe"))
                self.assertEqual((kwargs["stdout"], kwargs["stderr"]), (subprocess.PIPE, subprocess.PIPE))

    def test_wrong_workspace_root_refuses_before_any_directory_or_record(self) -> None:
        """The configured root names the protected roots, so a wrong one stops before the resolver."""
        allowed = self.root / "allowed_ws"
        allowed.mkdir()
        doc = _valid_config_dict(self.root)
        doc["workspace_root"] = str(self.root)
        doc["allowed_output_parent"] = str(allowed)
        config = load_study_configuration(doc)
        run_dir = allowed / "run_wrong_workspace"

        with patch.object(study_mod, "_resolve_contained_output", side_effect=AssertionError("resolved first")), patch.object(
            study_mod, "_write_exclusive", side_effect=AssertionError("wrote first")
        ):
            with self.assertRaises(InputValidationError) as ctx:
                run_study(config, run_dir, allowed_parent=allowed)
        self.assertEqual(ctx.exception.field, "workspace_root")
        self.assertFalse(run_dir.exists())
        self.assertEqual(list(allowed.iterdir()), [])

    def test_served_public_and_dist_roots_are_refused_for_a_valid_root(self) -> None:
        """
        A scratch package root stands in for the actual one, so the real served directories are
        never touched: run_study accepts that root, then refuses public/<id> and dist/<id>.
        """
        fake_root = self.root / "fake_package"
        module_file = fake_root / "research" / "prediction_eval" / "study.py"
        for served in ("public", "dist"):
            parent = fake_root / served
            parent.mkdir(parents=True)
            doc = _valid_config_dict(self.root)
            doc["workspace_root"] = str(fake_root)
            doc["allowed_output_parent"] = str(parent)
            config = load_study_configuration(doc)
            with self.subTest(root=served):
                with patch.object(study_mod, "__file__", str(module_file)), patch.object(
                    study_mod, "_verify_run_prerequisites", side_effect=AssertionError("ran after refusal")
                ):
                    with self.assertRaises(ValueError) as ctx:
                        run_study(config, parent / "run_served", allowed_parent=parent)
                self.assertIn("protected root", str(ctx.exception))
                self.assertIn(served, str(ctx.exception))
                self.assertEqual(list(parent.iterdir()), [])

        # A not-yet-built served root is refused as the run root itself, not only beneath it
        bare_root = self.root / "bare_package"
        bare_root.mkdir()
        for served in ("public", "dist"):
            with self.subTest(served_root_itself=served):
                with self.assertRaises(ValueError) as ctx:
                    _resolve_contained_output(bare_root / served, bare_root, [], str(bare_root))
                self.assertIn("protected root", str(ctx.exception))
                self.assertFalse((bare_root / served).exists())

        # The passed-root resolver keeps its semantics: the same names elsewhere stay allowed
        elsewhere = self.root / "elsewhere_parent"
        elsewhere.mkdir()
        self.assertEqual(
            _resolve_contained_output(elsewhere / "dist", elsewhere, [], str(fake_root)),
            (elsewhere / "dist").resolve(),
        )

    def test_output_directory_containment_and_collision(self) -> None:
        """Verifies that run_study rejects collision on existing output directory and traversal escapes."""
        allowed = self.root / "allowed_root"
        allowed.mkdir()
        existing_dir = allowed / "run_exists"
        existing_dir.mkdir()

        doc = _valid_config_dict(self.root)
        doc["allowed_output_parent"] = str(allowed)
        config = load_study_configuration(doc)

        # Rejection on existing directory
        with self.assertRaises(ValueError) as ctx:
            run_study(config, existing_dir, allowed_parent=allowed)
        self.assertIn("already exists", str(ctx.exception))

        # Rejection on directory traversal escape: the lexical refusal fires before normalization
        escaped_path = allowed / "sub" / ".." / ".." / "escaped_run"
        with self.assertRaises(ValueError) as ctx:
            run_study(config, escaped_path, allowed_parent=allowed)
        self.assertIn("parent traversal", str(ctx.exception))
        self.assertFalse((self.root / "escaped_run").exists())

        # Canonical containment still refuses a net escape that has no traversal component
        with self.assertRaises(ValueError) as ctx:
            run_study(config, self.root / "escaped_run", allowed_parent=allowed)
        self.assertIn("escapes allowed parent", str(ctx.exception))
        self.assertFalse((self.root / "escaped_run").exists())

        # The parent cannot be vacuous: omitted, or anything but the configured one
        with self.assertRaises(TypeError):
            run_study(config, allowed / "run_new")  # type: ignore[call-arg]
        for bad_parent in (None, self.root):
            with self.subTest(parent=bad_parent):
                with self.assertRaises(ValueError):
                    run_study(config, allowed / "run_new", allowed_parent=bad_parent)  # type: ignore[arg-type]
        self.assertFalse((allowed / "run_new").exists())

    def test_lexical_reentry_is_refused_before_the_run_root_exists(self) -> None:
        """
        allowed/../allowed/run normalizes to a direct child of allowed, so only the lexical
        check can refuse it; nothing is created, and the plain child stays an accepted control.
        """
        allowed = self.root / "allowed_reentry"
        allowed.mkdir()
        doc = _valid_config_dict(self.root)
        doc["allowed_output_parent"] = str(allowed)
        config = load_study_configuration(doc)
        reentry = allowed / ".." / allowed.name / "run_reentry"
        self.assertEqual(Path(os.path.normpath(reentry)), allowed / "run_reentry")

        with patch.object(study_mod, "_verify_run_prerequisites", side_effect=AssertionError("ran after refusal")), patch.object(
            study_mod, "_write_exclusive", side_effect=AssertionError("wrote after refusal")
        ):
            with self.assertRaises(ValueError) as ctx:
                run_study(config, reentry, allowed_parent=allowed)
        self.assertIn("parent traversal", str(ctx.exception))
        self.assertEqual(list(allowed.iterdir()), [])
        with self.assertRaises(ValueError):
            _resolve_contained_output(reentry, allowed, [], str(self.root / "ws"))
        self.assertEqual(list(allowed.iterdir()), [])
        self.assertEqual(_resolve_contained_output(allowed / "run_reentry", allowed, [], str(self.root / "ws")), (allowed / "run_reentry").resolve())
        self.assertEqual(list(allowed.iterdir()), [])

    def test_completion_manifest_publication_never_leaves_a_partial_file(self) -> None:
        """
        A caught write or close failure after creation removes this call's partial file and keeps
        the primary error; a pre-existing file keeps its bytes; a valid publication is complete.
        """
        publish = study_mod._publish_completion_manifest
        root = self.root / "publication"
        root.mkdir()
        data = b'{"completed": true}\n'
        real_open = open

        # Valid completion control
        good = root / "good.json"
        publish(good, data)
        self.assertEqual(good.read_bytes(), data)

        # Collision control: an existing file is neither written nor removed
        existing = root / "existing.json"
        existing.write_bytes(b"prior bytes")
        with self.assertRaises(FileExistsError):
            publish(existing, data)
        self.assertEqual(existing.read_bytes(), b"prior bytes")

        class _Partial:
            """Writes part of the bytes to the real file, then fails like a full disk or a bad close."""

            def __init__(self, path: Any, mode: str, fail_on: str) -> None:
                self._handle = real_open(path, mode)
                self._fail_on = fail_on

            def write(self, payload: bytes) -> int:
                self._handle.write(payload[:5])
                self._handle.flush()
                if self._fail_on == "write":
                    raise OSError("disk full after creation")
                return len(payload)

            def close(self) -> None:
                self._handle.close()
                if self._fail_on == "close":
                    raise OSError("close failed after creation")

        for fail_on in ("write", "close"):
            target = root / f"partial_{fail_on}.json"
            with self.subTest(failure=fail_on):
                with patch.object(study_mod, "open", lambda path, mode, f=fail_on: _Partial(path, mode, f), create=True):
                    with self.assertRaises(OSError) as ctx:
                        publish(target, data)
                self.assertIn("after creation", str(ctx.exception))
                self.assertFalse(target.exists())
                self.assertFalse(hasattr(ctx.exception, "manifest_cleanup_error"))

        # A failed removal keeps the primary error and discloses the cleanup failure on it
        stuck = root / "stuck.json"
        with patch.object(study_mod, "open", lambda path, mode: _Partial(path, mode, "write"), create=True), patch.object(
            study_mod.os, "unlink", side_effect=PermissionError("locked by another process")
        ):
            with self.assertRaises(OSError) as ctx:
                publish(stuck, data)
        self.assertEqual(str(ctx.exception), "disk full after creation")
        self.assertIn("locked by another process", ctx.exception.manifest_cleanup_error)  # type: ignore[attr-defined]
        self.assertEqual(stuck.read_bytes(), data[:5])

    def test_containment_rejects_each_unsafe_location_before_writing(self) -> None:
        allowed = self.root / "allowed"
        allowed.mkdir()
        (allowed / "inner").mkdir()
        input_file = allowed / "nifty.csv"
        input_file.write_text("x", encoding="utf-8")

        def _resolve(output: Path, parent: Any = allowed) -> Path:
            return _resolve_contained_output(output, parent, [str(input_file)], str(self.root / "ws"))

        self.assertEqual(_resolve(allowed / "run_ok"), (allowed / "run_ok").resolve())

        cases = {
            "the_parent_itself": allowed,
            "nested_child": allowed / "inner" / "run",
            "sibling_escape": self.root / "elsewhere" / "run",
            "bound_input_alias": input_file,
            "non_portable_name": allowed / "bad name",
        }
        for name, output in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    _resolve(output)

        with self.assertRaises(ValueError):
            _resolve(Path("relative_run"))
        with self.assertRaises(ValueError):
            _resolve(allowed / "run_ok", None)
        with self.assertRaises(ValueError):
            _resolve(allowed / "run_ok", self.root / "absent")

        # Protected source, model and build roots stay unwritable even if a parent contains them
        workspace = self.root / "ws"
        workspace.mkdir()
        with self.assertRaises(ValueError) as ctx:
            _resolve_contained_output(workspace / "research", workspace, [], str(workspace))
        self.assertIn("protected root", str(ctx.exception))

    def test_containment_rejects_reparse_points(self) -> None:
        """Link detection is injected: creating a real junction is an OS-level experiment."""
        allowed = self.root / "allowed"
        allowed.mkdir()
        with patch.object(study_mod, "_is_reparse_or_link", return_value=True):
            with self.assertRaises(ValueError) as ctx:
                _resolve_contained_output(allowed / "run", allowed, [], str(self.root / "ws"))
        self.assertIn("reparse point", str(ctx.exception))

    @staticmethod
    def _links_only(*linked: Path) -> Callable[[Any], bool]:
        """Reports only the named lexical paths as links; every other component stays regular."""
        keys = {os.path.normcase(str(path)) for path in linked}
        return lambda path: os.path.normcase(str(path)) in keys

    def test_linked_ancestor_of_a_regular_parent_stops_the_actual_callers(self) -> None:
        """
        Resolving both paths through a shared link keeps them related, so a regular parent below
        a linked ancestor passes every leaf and prefix check. Injection stands in for a junction.
        """
        anchor = self.root / "linked_anchor"
        parent = anchor / "regular" / "runs"
        parent.mkdir(parents=True)
        run_dir = parent / "run_new"

        doc = _valid_config_dict(self.root)
        doc["allowed_output_parent"] = str(parent)
        config_path = self.root / "config.json"
        config_path.write_text(json.dumps(doc), encoding="utf-8")
        config = load_study_configuration(doc)

        # Control: with no link the same paths are accepted, so the ancestor is the only cause
        self.assertEqual(_resolve_contained_output(run_dir, parent, [], str(self.root / "ws")), run_dir.resolve())

        with patch.object(study_mod, "_is_reparse_or_link", self._links_only(anchor)), patch.object(
            study_mod, "_verify_run_prerequisites"
        ) as prerequisites, patch.object(study_mod, "_write_exclusive") as writer:
            with self.assertRaises(ValueError) as ctx:
                run_study(config, run_dir, allowed_parent=parent)
            self.assertEqual(main(["--config", str(config_path), "--output-dir", str(run_dir)]), 1)

        self.assertIn("reparse point", str(ctx.exception))
        self.assertIn(str(anchor), str(ctx.exception))
        prerequisites.assert_not_called()
        writer.assert_not_called()
        self.assertFalse(run_dir.exists())
        self.assertEqual(list(parent.iterdir()), [])

    def test_containment_checks_lexical_components_before_resolving(self) -> None:
        allowed = self.root / "allowed"
        (allowed / "inner").mkdir(parents=True)
        workspace = str(self.root / "ws")

        cases = {
            "immediate_parent": (allowed, allowed / "run"),
            "link_collapsed_by_dotdot": (allowed / "inner", allowed / "inner" / ".." / "run"),
            "dangling_leaf": (allowed / "run", allowed / "run"),
        }
        for name, (linked, output) in cases.items():
            with self.subTest(case=name):
                with patch.object(study_mod, "_is_reparse_or_link", self._links_only(linked)):
                    with patch.object(Path, "resolve", side_effect=AssertionError("resolved before the link check")):
                        with self.assertRaises(ValueError) as ctx:
                            _resolve_contained_output(output, allowed, [], workspace)
                self.assertIn("reparse point", str(ctx.exception))

    def test_failure_record_write_failure_preserves_primary_error(self) -> None:
        run_root = self.root / "run_storage"
        run_root.mkdir()
        lifecycle = _RunLifecycle(run_root)
        lifecycle.enter("scoring")
        primary = ValueError("primary failure")

        with patch.object(study_mod, "_write_exclusive", side_effect=OSError("disk full")):
            lifecycle.record_failure(primary)

        self.assertEqual(str(primary), "primary failure")
        self.assertIn("disk full", primary.failure_record_error)  # type: ignore[attr-defined]
        self.assertFalse((run_root / FAILURE_RECORD_NAME).exists())

    def test_failure_record_keeps_returned_input_warnings_in_order_with_repeats(self) -> None:
        run_root = self.root / "run_input_warnings"
        run_root.mkdir()
        lifecycle = _RunLifecycle(run_root)
        repeated = InputWarning("a.csv", "line 3", "Open", "Malformed Open value 'x'", "x")
        empty_cell = InputWarning("a.csv", "line 4", "Open", "Missing or empty Open value in OHLC record", "")
        no_raw = InputWarning("b.csv", "lines 5-6", "High", "Unusable High")

        lifecycle.retain_input_warnings(LoadedSeries("nifty50_price_index", (), (), (repeated, empty_cell, repeated)))
        lifecycle.retain_input_warnings(LoadedSeries("india_vix", (), (), (no_raw,)))
        lifecycle.enter("scoring")
        lifecycle.record_failure(ValueError("later failure"))

        record = json.loads((run_root / FAILURE_RECORD_NAME).read_text(encoding="utf-8"))
        first = {"file_path": "a.csv", "line": "line 3", "field": "Open", "message": "Malformed Open value 'x'", "raw_value": "x"}
        self.assertEqual(
            record["input_warnings"],
            [
                first,
                {"file_path": "a.csv", "line": "line 4", "field": "Open", "message": "Missing or empty Open value in OHLC record", "raw_value": ""},
                first,
                {"file_path": "b.csv", "line": "lines 5-6", "field": "High", "message": "Unusable High", "raw_value": None},
            ],
        )

    def _planned(self, *, close_fn: Callable[[int], str] = _wave_close, missing_vix: Sequence[int] = ()) -> SimpleNamespace:
        fixture = _write_inputs(self.root / "planned", close_fn=close_fn, missing_vix=missing_vix)
        nifty = load_series("nifty50_price_index", fixture.nifty)
        vix = load_series("india_vix", fixture.vix)
        aligned = align_pair(nifty, vix, expected_sessions=fixture.dates)
        features = compute_nifty_features(aligned)
        outcomes = compute_twenty_session_outcomes(nifty)
        d_date, t_date = fixture.dates[235], fixture.dates[260]
        plan = build_split_plan(features, outcomes, development_start=d_date, test_start=t_date)
        frequency = build_frequency_predictions(features, outcomes, development_start=d_date, test_start=t_date)
        return SimpleNamespace(fixture=fixture, features=features, outcomes=outcomes, plan=plan, frequency=frequency)

    @staticmethod
    def _unavailable_logistic(plan: SplitPlan, partition: str, targets: Tuple[int, ...], pool: Tuple[int, ...], cutoff: int, cutoff_date: datetime.date) -> SimpleNamespace:
        return SimpleNamespace(
            partition=partition,
            fitting_indices=pool,
            cutoff_index=cutoff,
            cutoff_date=cutoff_date,
            class_counts=(len(pool), 0, 0),
            regime_counts=(len(pool), 0, 0, 0, 0, 0),
            requested_indices=targets,
            fit=None,
            predictions=(),
            unavailable_reason="missing_training_classes",
            failure_stage=None,
        )

    def _heuristic_map(self, features: FeatureSeries, targets: Sequence[int]) -> Dict[int, HeuristicPrediction]:
        return {
            i: HeuristicPrediction(i, features.records[i].origin_date, (0.34, 0.2, 0.46), "NEUTRAL / RANGE-BOUND")
            for i in targets
        }

    def test_partition_counts_follow_planner_policy_with_overlapping_reasons(self) -> None:
        """
        N=290, D=235, T=260. Raw development is T-D=25 and raw test is N-T=30. A label must mature
        strictly before T, so development retains D..T-21 (5 origins); the last 20 test origins have
        no outcome, so test retains T..N-21 (10). A missing VIX at 275 joins the unknown tail, so
        it adds a reason but no unique exclusion; one at 262 removes a retained origin.
        """
        ctx = self._planned(missing_vix=(262, 275))
        plan = ctx.plan
        pool = plan.refit_indices
        part = _evaluate_partition(
            "test",
            plan.test_indices,
            plan,
            ctx.outcomes,
            self._heuristic_map(ctx.features, plan.test_indices),
            ctx.frequency.test_block,
            self._unavailable_logistic(plan, "test", plan.test_indices, pool, plan.test_start_index, plan.test_start),
        )
        self.assertEqual(part.counts.raw_partition_count, 30)
        self.assertEqual(part.counts.eligible_count, 9)
        self.assertEqual(part.counts.requested_count, 9)
        self.assertEqual(part.counts.excluded_count, 21)
        self.assertEqual(part.counts.exclusion_reason_counts, {"missing_vix": 2, "unknown_outcome": 20})

        dev = _evaluate_partition(
            "development",
            plan.development_indices,
            plan,
            ctx.outcomes,
            self._heuristic_map(ctx.features, plan.development_indices),
            ctx.frequency.development_block,
            self._unavailable_logistic(plan, "development", plan.development_indices, plan.train_indices, plan.development_start_index, plan.development_start),
        )
        self.assertEqual(
            (dev.counts.raw_partition_count, dev.counts.eligible_count, dev.counts.excluded_count),
            (25, 5, 20),
        )
        self.assertEqual(dev.counts.exclusion_reason_counts, {"label_crosses_test_boundary": 20})

    def test_unavailable_method_keeps_usable_forecasts_without_scoring(self) -> None:
        ctx = self._planned()
        plan = ctx.plan
        targets = plan.test_indices

        with patch.object(study_mod, "score_comparison", side_effect=AssertionError("no three-way score")):
            part = _evaluate_partition(
                "test",
                targets,
                plan,
                ctx.outcomes,
                self._heuristic_map(ctx.features, targets),
                ctx.frequency.test_block,
                self._unavailable_logistic(plan, "test", targets, plan.refit_indices, plan.test_start_index, plan.test_start),
            )

        self.assertEqual(part.comparison_status, STATUS_COMPARISON_UNAVAILABLE)
        self.assertEqual(part.comparison_unavailable_reasons, ("logistic: missing_training_classes",))
        self.assertIsNone(part.comparison_metrics)
        self.assertEqual(part.counts.model_available_counts, {"heuristic": 10, "frequency": 10, "logistic": 0})
        self.assertEqual(len(part.per_origin_records), 10)
        row = part.per_origin_records[0]
        self.assertEqual(row.score_state, "unscored")
        self.assertEqual(row.heuristic.probabilities, (0.34, 0.2, 0.46))
        self.assertEqual(row.frequency.probabilities, ctx.frequency.test_block.predictions[0].probabilities)
        self.assertEqual(row.logistic.forecast_state, "unavailable")
        self.assertIsNone(row.logistic.probabilities)
        self.assertIsNone(row.frequency.brier)
        self.assertEqual(part.logistic_block["class_counts"], [len(plan.refit_indices), 0, 0])

    def test_unavailable_fit_wins_before_empty_status(self) -> None:
        """An empty target with an unavailable fit is not a genuine empty comparison."""
        ctx = self._planned(missing_vix=tuple(range(235, 240)))
        plan = ctx.plan
        self.assertEqual(plan.development_indices, ())

        part = _evaluate_partition(
            "development",
            (),
            plan,
            ctx.outcomes,
            {},
            ctx.frequency.development_block,
            self._unavailable_logistic(plan, "development", (), plan.train_indices, plan.development_start_index, plan.development_start),
        )
        self.assertEqual(part.comparison_status, STATUS_COMPARISON_UNAVAILABLE)

    def test_missing_heuristic_for_target_fails_the_run(self) -> None:
        """A validated replay covers every ready origin, so a gap here is a defect, not insufficiency."""
        ctx = self._planned()
        plan = ctx.plan
        with self.assertRaises(ValueError):
            _evaluate_partition(
                "test",
                plan.test_indices,
                plan,
                ctx.outcomes,
                {},
                ctx.frequency.test_block,
                self._unavailable_logistic(plan, "test", plan.test_indices, plan.refit_indices, plan.test_start_index, plan.test_start),
            )

    def test_reconciliation_compares_plans_blocks_pools_and_keys(self) -> None:
        ctx = self._planned()
        plan = ctx.plan

        def _logistic(**changes: Any) -> SimpleNamespace:
            dev = self._unavailable_logistic(plan, "development", plan.development_indices, plan.train_indices, plan.development_start_index, plan.development_start)
            test = self._unavailable_logistic(plan, "test", plan.test_indices, plan.refit_indices, plan.test_start_index, plan.test_start)
            for key, value in changes.items():
                setattr(test, key, value)
            return SimpleNamespace(plan=plan, development_block=dev, test_block=test)

        _reconcile_comparator_blocks(plan, ctx.frequency, _logistic())

        cases = {
            "requested_keys": _logistic(requested_indices=plan.test_indices[:-1]),
            "fitting_pool": _logistic(fitting_indices=plan.train_indices),
            "cutoff_index": _logistic(cutoff_index=plan.test_start_index + 1),
            "cutoff_date": _logistic(cutoff_date=plan.development_start),
            "partition": _logistic(partition="development"),
            "predictions_on_unavailable": _logistic(predictions=(object(),)),
        }
        for name, log_res in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(InputValidationError):
                    _reconcile_comparator_blocks(plan, ctx.frequency, log_res)

        decisions = list(plan.decisions)
        decisions[5] = OriginSplitDecision(5, decisions[5].origin_date, "development", (), False)
        altered_plan = SplitPlan(**{**plan.__dict__, "decisions": tuple(decisions)})
        with self.assertRaises(InputValidationError):
            _reconcile_comparator_blocks(plan, SimpleNamespace(**{**ctx.frequency.__dict__, "plan": altered_plan}), _logistic())

        moved_date = plan.test_start + datetime.timedelta(days=1)
        altered_dates = SplitPlan(**{**plan.__dict__, "test_start": moved_date})
        with self.assertRaises(InputValidationError):
            _reconcile_comparator_blocks(plan, ctx.frequency, SimpleNamespace(**{**_logistic().__dict__, "plan": altered_dates}))

        bad_block = FrequencyBlock(
            partition="test",
            requested_indices=plan.test_indices,
            fit=ctx.frequency.test_block.fit,
            predictions=tuple(
                FrequencyPrediction(p.origin_index + 1, p.origin_date, p.probabilities)
                for p in ctx.frequency.test_block.predictions
            ),
            unavailable_reason=None,
        )
        with self.assertRaises(InputValidationError):
            _reconcile_comparator_blocks(plan, SimpleNamespace(**{**ctx.frequency.__dict__, "test_block": bad_block}), _logistic())

    def test_derive_historical_split_cutoffs(self) -> None:
        """Verifies deterministic calendar_tail800_dev400_min2220_v1 split cutoffs and caller verification."""
        dates = _session_dates(2500)
        e_exp = dates[2500 - 20]
        t_exp = dates[2500 - 820]
        d_exp = dates[2500 - 1220]

        d_calc, t_calc, e_calc = derive_historical_split_cutoffs(dates)
        self.assertEqual(d_calc, d_exp)
        self.assertEqual(t_calc, t_exp)
        self.assertEqual(e_calc, e_exp)

        # Successful caller verification
        d_ret, t_ret, e_ret = derive_historical_split_cutoffs(
            dates, expected_development_start=d_exp, expected_test_start=t_exp
        )
        self.assertEqual((d_ret, t_ret, e_ret), (d_exp, t_exp, e_exp))

        # Caller drift rejection
        with self.assertRaises(InputValidationError) as ctx:
            derive_historical_split_cutoffs(dates, expected_development_start=dates[0], expected_test_start=t_exp)
        self.assertEqual(ctx.exception.field, "development_start")
        self.assertIn("development_start mismatch", str(ctx.exception))

        with self.assertRaises(InputValidationError) as ctx:
            derive_historical_split_cutoffs(dates, expected_development_start=d_exp, expected_test_start=dates[0])
        self.assertEqual(ctx.exception.field, "test_start")
        self.assertIn("test_start mismatch", str(ctx.exception))

        # Unsupported rule
        with self.assertRaises(InputValidationError) as ctx:
            derive_historical_split_cutoffs(dates, rule="unsupported_rule")
        self.assertEqual(ctx.exception.field, "date_selection_rule")

        # Insufficient sessions (N < 2220)
        short_dates = _session_dates(2219)
        with self.assertRaises(InputValidationError) as ctx:
            derive_historical_split_cutoffs(short_dates)
        self.assertEqual(ctx.exception.field, "date_selection_rule")
        self.assertIn("requires at least 2220 trading sessions", str(ctx.exception))

        # Exact boundary N = 2220
        min_dates = _session_dates(2220)
        d_min, t_min, e_min = derive_historical_split_cutoffs(min_dates)
        self.assertEqual(d_min, min_dates[1000])
        self.assertEqual(t_min, min_dates[1400])
        self.assertEqual(e_min, min_dates[2200])

        # Non-increasing dates
        bad_dates = list(dates[:100])
        bad_dates[50], bad_dates[51] = bad_dates[51], bad_dates[50]
        with self.assertRaises(InputValidationError) as ctx:
            derive_historical_split_cutoffs(bad_dates)
        self.assertEqual(ctx.exception.field, "dates")

    def test_cli_argument_parser_historical_approval(self) -> None:
        """Verifies CLI argument parsing for optional approval flags."""
        args = parse_cli_args([
            "--config", "conf.json",
            "--output-dir", "out_dir",
            "--approval", "approval.json",
            "--approval-bytes", "1024",
            "--approval-sha256", "A" * 64,
        ])
        self.assertEqual(args.config, "conf.json")
        self.assertEqual(args.output_dir, "out_dir")
        self.assertEqual(args.approval, "approval.json")
        self.assertEqual(args.approval_bytes, 1024)
        self.assertEqual(args.approval_sha256, "A" * 64)

    def test_load_study_configuration_historical_v3(self) -> None:
        """Verifies loading of V3 historical configuration with multi-file inputs."""
        valid_synth = _valid_config_dict(self.root)
        f1 = str((self.root / "nifty_part1.csv").resolve())
        f2 = str((self.root / "nifty_part2.csv").resolve())
        v1 = str((self.root / "vix_part1.csv").resolve())
        v2 = str((self.root / "vix_part2.csv").resolve())

        hist_doc: Dict[str, Any] = {
            "schema_version": STUDY_SCHEMA_VERSION_V3,
            "study_id": "historical-v3-unit",
            "protocol_id": STUDY_PROTOCOL_ID,
            "data_kind": DATA_KIND_HISTORICAL,
            "development_status": "retrospective_historical_evaluation",
            "date_selection_rule": DATE_SELECTION_RULE_HISTORICAL,
            "development_start": "2020-01-01",
            "test_start": "2021-01-01",
            "workspace_root": str(self.root),
            "allowed_output_parent": str(self.root),
            "timeout_seconds": 30,
            "inputs": {
                "nifty": {
                    "units": "index_points",
                    "source_kind": "admitted_historical_market_data",
                    "files": [
                        {"path": f1, "source_url": None, "requested_interval": None, "acquisition_time": None, "source_use_note": "n1", "raw_byte_count": 100, "sha256": "1" * 64},
                        {"path": f2, "source_url": None, "requested_interval": None, "acquisition_time": None, "source_use_note": "n2", "raw_byte_count": 200, "sha256": "2" * 64},
                    ],
                },
                "vix": {
                    "units": "volatility_index_points",
                    "source_kind": "admitted_historical_market_data",
                    "files": [
                        {"path": v1, "source_url": None, "requested_interval": None, "acquisition_time": None, "source_use_note": "v1", "raw_byte_count": 150, "sha256": "3" * 64},
                        {"path": v2, "source_url": None, "requested_interval": None, "acquisition_time": None, "source_use_note": "v2", "raw_byte_count": 250, "sha256": "4" * 64},
                    ],
                },
                "calendar": {"path": str(self.root / "calendar.json"), "raw_byte_count": 300, "sha256": "5" * 64},
            },
            "admission": {"path": str(self.root / "admission.json"), "raw_byte_count": 400, "sha256": "6" * 64},
            "tools": valid_synth["tools"],
            "source_modules": valid_synth["source_modules"],
            "runtime": valid_synth["runtime"],
            "uncertainty": {"protocol_id": "nivesh-paired-stationary-brier-v1", "max_resample_positions": 24000000},
        }

        config = load_study_configuration(hist_doc)
        self.assertEqual(config.schema_version, STUDY_SCHEMA_VERSION_V3)
        self.assertEqual(config.data_kind, DATA_KIND_HISTORICAL)
        self.assertEqual(len(config.nifty_input.files), 2)
        self.assertEqual(len(config.vix_input.files), 2)

        # One gap-free study is 10000 x 800 x 3 = 24000000 positions; historical takes exactly that
        self.assertEqual(HISTORICAL_MAX_RESAMPLE_POSITIONS, 10000 * 800 * 3)
        for cap in (30000000, 23999999, 24000001):
            with self.subTest(historical_cap=cap):
                with self.assertRaises(InputValidationError) as ctx:
                    load_study_configuration(dict(hist_doc, uncertainty={"protocol_id": "nivesh-paired-stationary-brier-v1", "max_resample_positions": cap}))
                self.assertEqual(ctx.exception.field, "uncertainty.max_resample_positions")
        # The synthetic-v2 range is unchanged
        self.assertEqual(load_study_configuration(valid_synth).uncertainty["max_resample_positions"], 30000000)

        # Config must not contain approval credential
        bad_approval = dict(hist_doc, approval={"path": "a.json", "raw_byte_count": 1, "sha256": "7" * 64})
        with self.assertRaises(InputValidationError) as ctx:
            load_study_configuration(bad_approval)
        self.assertEqual(ctx.exception.field, "approval")
        self.assertIn("Unknown configuration key: 'approval'", str(ctx.exception))

        # Duplicate file path rejection
        dup_inputs = copy.deepcopy(hist_doc["inputs"])
        dup_inputs["nifty"]["files"][1]["path"] = f1
        with self.assertRaises(InputValidationError) as ctx:
            load_study_configuration(dict(hist_doc, inputs=dup_inputs))
        self.assertEqual(ctx.exception.field, "inputs.nifty.files[1].path")
        self.assertIn("Duplicate input path", str(ctx.exception))

        # Cross-series duplicate file path rejection
        cross_dup = copy.deepcopy(hist_doc["inputs"])
        cross_dup["vix"]["files"][0]["path"] = f1
        with self.assertRaises(InputValidationError) as ctx:
            load_study_configuration(dict(hist_doc, inputs=cross_dup))
        self.assertIn("Duplicate input path across input series", str(ctx.exception))

        # Empty files list rejection
        empty_files = copy.deepcopy(hist_doc["inputs"])
        empty_files["nifty"]["files"] = []
        with self.assertRaises(InputValidationError) as ctx:
            load_study_configuration(dict(hist_doc, inputs=empty_files))
        self.assertIn("must be a non-empty list", str(ctx.exception))

    def test_prepare_historical_admission_unit(self) -> None:
        """Verifies prepare_historical_admission builds valid admission-v2 record with file provenance."""
        in_dir = self.root / "hist_adm_inputs"
        in_dir.mkdir(parents=True)
        dates = _session_dates(2300)
        cal_path = in_dir / "calendar.json"
        cal_path.write_text(json.dumps({"sessions": [d.isoformat() for d in dates]}), encoding="utf-8")

        # Two nifty files (1200 + 1100 = 2300)
        nifty1 = in_dir / "nifty1.csv"
        nifty2 = in_dir / "nifty2.csv"
        nlines1 = ["Date,Close"] + [f"{dates[i].strftime('%d-%b-%Y')},{15000.0 + i:.2f}" for i in range(1200)]
        nlines2 = ["Date,Close"] + [f"{dates[i].strftime('%d-%b-%Y')},{15000.0 + i:.2f}" for i in range(1200, 2300)]
        nifty1.write_text("\n".join(nlines1) + "\n", encoding="utf-8")
        nifty2.write_text("\n".join(nlines2) + "\n", encoding="utf-8")

        # Two vix files (1200 + 1100 = 2300)
        vix1 = in_dir / "vix1.csv"
        vix2 = in_dir / "vix2.csv"
        vlines1 = ["Date,Close"] + [f"{dates[i].strftime('%d-%b-%Y')},{16.0:.2f}" for i in range(1200)]
        vlines2 = ["Date,Close"] + [f"{dates[i].strftime('%d-%b-%Y')},{16.0:.2f}" for i in range(1200, 2300)]
        vix1.write_text("\n".join(vlines1) + "\n", encoding="utf-8")
        vix2.write_text("\n".join(vlines2) + "\n", encoding="utf-8")

        n_specs = [
            FileInputSpec(file_path=str(nifty1), source_use_note="n1"),
            FileInputSpec(file_path=str(nifty2), source_use_note="n2"),
        ]
        v_specs = [
            FileInputSpec(file_path=str(vix1), source_use_note="v1"),
            FileInputSpec(file_path=str(vix2), source_use_note="v2"),
        ]

        adm_doc = prepare_historical_admission(
            nifty_specs=n_specs,
            vix_specs=v_specs,
            calendar_path=cal_path,
        )

        self.assertEqual(adm_doc["schema_version"], SCHEMA_VERSION_ADMISSION_V2)
        self.assertEqual(adm_doc["data_kind"], DATA_KIND_HISTORICAL)
        self.assertEqual(adm_doc["mature_test_span_count"], 800)
        self.assertEqual(len(adm_doc["inputs"]["nifty"]["files"]), 2)
        self.assertEqual(len(adm_doc["inputs"]["vix"]["files"]), 2)

        # Validate with official study_results validator
        validate_admission_document(adm_doc)

        # Non-existent file rejection
        bad_specs = [
            FileInputSpec(file_path=str(in_dir / "nonexistent.csv"), source_use_note="n1"),
            FileInputSpec(file_path=str(nifty2), source_use_note="n2"),
        ]
        with self.assertRaises(InputValidationError):
            prepare_historical_admission(nifty_specs=bad_specs, vix_specs=v_specs, calendar_path=cal_path)

    def test_run_study_approval_enforcement(self) -> None:
        """Verifies run_study enforces external approval document checks for historical runs and forbids it for synthetic."""
        synth_doc = _valid_config_dict(self.root)
        synth_cfg = load_study_configuration(synth_doc)

        dummy_bound_file = BoundFile(path="approval.json", raw_byte_count=100, sha256="A" * 64)

        # Synthetic study forbids approval
        with self.assertRaises(InputValidationError) as ctx:
            run_study(synth_cfg, self.root / "out_synth_appr", allowed_parent=self.root, approval=dummy_bound_file)
        self.assertEqual(ctx.exception.field, "approval")
        self.assertIn("Human approval must not be provided for synthetic study", str(ctx.exception))

        # Construct minimal V3 historical config
        f1 = str((self.root / "nifty.csv").resolve())
        v1 = str((self.root / "vix.csv").resolve())
        Path(f1).write_text("Date,Close\n01-Jan-2020,15000\n", encoding="utf-8")
        Path(v1).write_text("Date,Close\n01-Jan-2020,15\n", encoding="utf-8")
        cal_path = (self.root / "calendar.json").resolve()
        cal_path.write_text('{"sessions": ["2020-01-01"]}', encoding="utf-8")
        adm_path = (self.root / "admission.json").resolve()
        adm_path.write_text('{"schema_version": "nivesh-study-admission-v2"}', encoding="utf-8")

        hist_doc = dict(
            synth_doc,
            schema_version=STUDY_SCHEMA_VERSION_V3,
            data_kind=DATA_KIND_HISTORICAL,
            development_status="retrospective_historical_evaluation",
            date_selection_rule=DATE_SELECTION_RULE_HISTORICAL,
            inputs={
                "nifty": {
                    "units": "index_points",
                    "source_kind": "admitted_historical_market_data",
                    "files": [{"path": f1, "source_url": None, "requested_interval": None, "acquisition_time": None, "source_use_note": "n", "raw_byte_count": len(Path(f1).read_bytes()), "sha256": hashlib.sha256(Path(f1).read_bytes()).hexdigest().upper()}],
                },
                "vix": {
                    "units": "volatility_index_points",
                    "source_kind": "admitted_historical_market_data",
                    "files": [{"path": v1, "source_url": None, "requested_interval": None, "acquisition_time": None, "source_use_note": "v", "raw_byte_count": len(Path(v1).read_bytes()), "sha256": hashlib.sha256(Path(v1).read_bytes()).hexdigest().upper()}],
                },
                "calendar": {"path": str(cal_path), "raw_byte_count": len(cal_path.read_bytes()), "sha256": hashlib.sha256(cal_path.read_bytes()).hexdigest().upper()},
            },
            admission={"path": str(adm_path), "raw_byte_count": len(adm_path.read_bytes()), "sha256": hashlib.sha256(adm_path.read_bytes()).hexdigest().upper()},
            uncertainty={"protocol_id": "nivesh-paired-stationary-brier-v1", "max_resample_positions": 24000000},
        )
        hist_config_path = self.root / "hist_config.json"
        hist_cfg_bytes = json.dumps(hist_doc, indent=2).encode("utf-8")
        hist_config_path.write_bytes(hist_cfg_bytes)
        hist_cfg = load_study_configuration_file(hist_config_path)

        # Historical study requires approval
        with self.assertRaises(InputValidationError) as ctx:
            run_study(hist_cfg, self.root / "out_hist_no_appr", allowed_parent=self.root, approval=None)
        self.assertEqual(ctx.exception.field, "approval")
        self.assertIn("Human approval BoundFile is required for historical study execution", str(ctx.exception))

        # Approval config sha mismatch
        appr_doc = {
            "schema_version": SCHEMA_VERSION_APPROVAL_V1,
            "decision_id": "dec-1",
            "approved_by": "Synthetic test approver",
            "approved_at": "2026-11-09T10:00:00Z",
            "decision": "APPROVED_FOR_ONE_PRIVATE_STUDY",
            "config_identity": {
                "raw_byte_count": len(hist_cfg_bytes),
                "sha256": "9" * 64,  # Mismatched SHA
            },
            "admission_identity": {
                "raw_byte_count": hist_cfg.admission.raw_byte_count,
                "sha256": hist_cfg.admission.sha256,
            },
            "source_use_evidence": [
                {
                    "input_refs": [{"role": "nifty", "file_index": 0}],
                    "evidence": [{"path": f1, "raw_byte_count": len(Path(f1).read_bytes()), "sha256": hashlib.sha256(Path(f1).read_bytes()).hexdigest().upper()}],
                    "note": "nifty note",
                },
                {
                    "input_refs": [{"role": "vix", "file_index": 0}],
                    "evidence": [{"path": v1, "raw_byte_count": len(Path(v1).read_bytes()), "sha256": hashlib.sha256(Path(v1).read_bytes()).hexdigest().upper()}],
                    "note": "vix note",
                },
            ],
            "calendar_evidence": {
                "evidence": [{"path": str(cal_path), "raw_byte_count": len(cal_path.read_bytes()), "sha256": hashlib.sha256(cal_path.read_bytes()).hexdigest().upper()}],
                "independent_source_note": "calendar note",
            },
            "raw_file_hash_release": "WITHHELD",
            "public_sharing_status": "NOT_CLEARED",
        }
        appr_path = self.root / "approval.json"
        appr_bytes = json.dumps(appr_doc).encode("utf-8")
        appr_path.write_bytes(appr_bytes)
        appr_bound = BoundFile(path=str(appr_path), raw_byte_count=len(appr_bytes), sha256=hashlib.sha256(appr_bytes).hexdigest().upper())

        with patch.object(study_mod, "_verify_run_prerequisites"):
            with self.assertRaises(InputValidationError) as ctx:
                run_study(hist_cfg, self.root / "out_hist_mismatch", allowed_parent=self.root, approval=appr_bound)
        self.assertEqual(ctx.exception.field, "approval.config_identity")
        self.assertIn("Human approval config_identity mismatch", str(ctx.exception))

    def test_cli_approval_identity_is_an_external_complete_pin(self) -> None:
        """
        The approval byte count and SHA-256 come only from the command line: all three flags or
        none. Partial and malformed pins refuse before any run, and a synthetic configuration
        refuses a complete approval triple before a root exists.
        """
        config_path = self.root / "cli_config.json"
        config_path.write_text(json.dumps(_valid_config_dict(self.root)), encoding="utf-8")
        approval_path = self.root / "cli_approval.json"
        approval_path.write_bytes(b'{"not": "an identity source"}\n')
        run_dir = self.root / "run_cli"
        base = ["--config", str(config_path), "--output-dir", str(run_dir)]
        path_flag = ["--approval", str(approval_path)]
        bytes_flag = ["--approval-bytes", "5"]
        sha_flag = ["--approval-sha256", "b" * 64]

        refused = {
            "path_only": path_flag,
            "path_and_bytes": path_flag + bytes_flag,
            "path_and_sha": path_flag + sha_flag,
            "bytes_only": bytes_flag,
            "sha_only": sha_flag,
            "bytes_and_sha": bytes_flag + sha_flag,
            "malformed_sha": path_flag + bytes_flag + ["--approval-sha256", "not-hex"],
            "negative_bytes": path_flag + ["--approval-bytes", "-1"] + sha_flag,
        }
        with patch.object(study_mod, "run_study") as runner:
            for name, flags in refused.items():
                with self.subTest(case=name):
                    self.assertEqual(main(base + flags), 1)
            runner.assert_not_called()

            # A complete triple reaches the runner with the command-line pin, never the file's own identity
            self.assertEqual(main(base + path_flag + bytes_flag + sha_flag), 0)
        runner.assert_called_once()
        bound = runner.call_args.kwargs["approval"]
        self.assertEqual(bound, BoundFile(path=str(approval_path.resolve()), raw_byte_count=5, sha256="B" * 64))
        file_bytes = approval_path.read_bytes()
        self.assertNotEqual((bound.raw_byte_count, bound.sha256), (len(file_bytes), _sha(file_bytes)))
        self.assertFalse(run_dir.exists())

        # Without the stand-in, the actual runner refuses any approval for a synthetic configuration
        self.assertEqual(main(base + path_flag + bytes_flag + sha_flag), 1)
        self.assertFalse(run_dir.exists())

    def test_direct_api_runs_only_the_configuration_its_bytes_parse_to(self) -> None:
        """A parsed dictionary paired with other raw bytes is refused before a root or any prerequisite."""
        doc = _valid_config_dict(self.root)
        config_path = self.root / "dto_config.json"
        raw = json.dumps(doc).encode("utf-8")
        config_path.write_bytes(raw)
        run_dir = self.root / "run_dto"

        # Value-equal reformatting parses to the same fields, so it stays a valid pairing
        reformatted = json.dumps(doc, indent=4, sort_keys=True).encode("utf-8")
        _require_configuration_from_its_bytes(load_study_configuration(doc, config_path=str(config_path), config_bytes=reformatted))
        _require_configuration_from_its_bytes(load_study_configuration_file(config_path))

        changes = {
            "timeout": {"timeout_seconds": 31},
            "test_start": {"test_start": "2023-06-02"},
            "admission": {"admission": dict(doc["admission"], sha256="B" * 64)},
        }
        for name, change in changes.items():
            foreign = load_study_configuration(dict(doc, **change), config_path=str(config_path), config_bytes=raw)
            with self.subTest(field=name):
                with patch.object(study_mod, "_verify_run_prerequisites") as prerequisites:
                    with self.assertRaises(InputValidationError) as ctx:
                        run_study(foreign, run_dir, allowed_parent=self.root)
                self.assertEqual(ctx.exception.field, "config")
                self.assertIn("strict parse of its original bytes", str(ctx.exception))
                prerequisites.assert_not_called()
                self.assertFalse(run_dir.exists())


class _StudyIntegrationBase(unittest.TestCase):
    """Base test case providing setup and fixture helpers for study integration and rehearsal without test methods."""

    @classmethod
    def setUpClass(cls) -> None:
        # Scientific packages are imported here to guarantee lazy top-level purity. A missing
        # prerequisite must error: this gate never turns absent dependencies into a skip.
        import threadpoolctl
        import sklearn
        import numpy
        import scipy

        cls.dependency_versions = {
            "numpy": numpy.__version__,
            "scikit-learn": sklearn.__version__,
            "scipy": scipy.__version__,
            "threadpoolctl": threadpoolctl.__version__,
        }

    def setUp(self) -> None:
        eval_work = os.environ.get("NIVESH_EVAL_WORK_DIR")
        if eval_work:
            # Retained for evidence: each test owns a fresh directory under the gate root
            self.work_parent = (Path(eval_work) / "study_integration" / self._testMethodName).resolve()
            self.work_parent.mkdir(parents=True, exist_ok=False)
        else:
            tmp = tempfile.TemporaryDirectory()
            self.addCleanup(tmp.cleanup)
            self.work_parent = Path(tmp.name).resolve()

        node = os.environ.get("NIVESH_EVAL_NODE")
        if not node or not Path(node).is_absolute() or not Path(node).is_file():
            self.fail(f"NIVESH_EVAL_NODE must name the pinned absolute Node executable, got {node!r}")
        self.node_exe = node
        self.replay_script = str(WORKSPACE_ROOT / "research" / "prediction_eval" / "replay.cjs")
        self.build_manifest = WORKSPACE_ROOT / "build" / "prediction-eval" / "candidate" / "build-manifest.json"
        self.models_path = WORKSPACE_ROOT / "public" / "data" / "market_intelligence" / "models.json"
        self._fixture_count = 0

    def _fixture(self, **kwargs: Any) -> SimpleNamespace:
        self._fixture_count += 1
        return _write_inputs(self.work_parent / f"inputs_{self._fixture_count}", **kwargs)

    def _generate_synthetic_csv_data(self, total_sessions: int = 290) -> Tuple[Path, Path, Path]:
        """Generates synthetic Nifty and VIX CSV files with all three classes in train and refit."""
        fixture = self._fixture(total_sessions=total_sessions)
        return fixture.nifty, fixture.vix, fixture.calendar

    def _write_config(
        self,
        fixture: SimpleNamespace,
        *,
        d_index: int = 235,
        t_index: int = 260,
        mutate: Optional[Callable[[Dict[str, Any]], None]] = None,
        admission_mutate: Optional[Callable[[Dict[str, Any]], None]] = None,
        timeout_seconds: int = 60,
    ) -> Path:
        """Freezes the input-only admission record first, then binds its bytes in the configuration."""
        directory = fixture.nifty.parent
        record = prepare_input_admission(
            nifty_spec=FileInputSpec(file_path=str(fixture.nifty), source_use_note="Generated synthetic test fixture"),
            vix_spec=FileInputSpec(file_path=str(fixture.vix), source_use_note="Generated synthetic test fixture"),
            calendar_path=fixture.calendar,
            development_start=fixture.dates[d_index],
            test_start=fixture.dates[t_index],
        )
        if admission_mutate is not None:
            admission_mutate(record)
        admission_path = directory / "admission.json"
        admission_path.write_bytes(json.dumps(record, indent=2).encode("utf-8") + b"\n")

        doc: Dict[str, Any] = {
            "schema_version": STUDY_SCHEMA_VERSION_V2,
            "study_id": "synthetic-e2e-study",
            "protocol_id": STUDY_PROTOCOL_ID,
            "data_kind": "synthetic",
            "development_status": "synthetic_development",
            "development_start": fixture.dates[d_index].isoformat(),
            "test_start": fixture.dates[t_index].isoformat(),
            "date_selection_rule": DATE_SELECTION_RULE,
            "workspace_root": str(WORKSPACE_ROOT),
            "allowed_output_parent": str(self.work_parent),
            "timeout_seconds": timeout_seconds,
            "inputs": {
                "nifty": _input_binding(fixture.nifty, "index_points"),
                "vix": _input_binding(fixture.vix, "volatility_index_points"),
                "calendar": _bound(fixture.calendar),
            },
            "admission": _bound(admission_path),
            "tools": {
                "node_executable": _bound(Path(self.node_exe), _frozen_identity(Path(self.node_exe))),
                "python_executable": _bound(Path(sys.executable), _frozen_identity(Path(sys.executable))),
                "replay_script": _bound(Path(self.replay_script)),
                "candidate_build_manifest": _bound(self.build_manifest),
                "models": _bound(self.models_path),
            },
            "source_modules": {rel: _identity(WORKSPACE_ROOT / rel) for rel in REQUIRED_SOURCE_MODULES},
            "runtime": {
                "python_version": platform.python_version(),
                "python_implementation": platform.python_implementation(),
                "dependency_versions": dict(self.dependency_versions),
            },
            "uncertainty": {
                "protocol_id": "nivesh-paired-stationary-brier-v1",
                "max_resample_positions": 30000000,
            },
        }
        if mutate is not None:
            mutate(doc)
        config_path = directory / "config.json"
        config_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        return config_path

    def _run(self, config_path: Path, run_name: str) -> Path:
        run_dir = self.work_parent / run_name
        config = load_study_configuration_file(config_path)
        run_study(config, run_dir, allowed_parent=config.allowed_output_parent)
        return run_dir

    def _failure(self, run_dir: Path) -> Dict[str, Any]:
        self.assertFalse((run_dir / "run-manifest.json").exists())
        ok, _ = verify_completed_run(run_dir)
        self.assertFalse(ok)
        return json.loads((run_dir / FAILURE_RECORD_NAME).read_text(encoding="utf-8"))

    @staticmethod
    def _json(path: Path) -> Dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _assert_uncertainty_binds_test_rows(self, run_dir: Path) -> Dict[str, Any]:
        """
        Independent join on the saved bytes: the input holds exactly the TEST scorer rows, and each
        point is fsum of their per-origin differences over n, not a difference of rounded means.
        """
        result = self._json(run_dir / "result.json")
        saved = self._json(run_dir / "uncertainty-input.json")
        block = self._json(run_dir / "panel-summary.json")["uncertainty"]
        self.assertEqual(block, result["uncertainty"])
        rows = result["partitions"]["test"]["per_origin_records"]
        development = {row["origin_index"] for row in result["partitions"]["development"]["per_origin_records"]}

        self.assertEqual(saved["requested_keys"], [{"origin_index": r["origin_index"], "origin_date": r["origin_date"]} for r in rows])
        self.assertFalse(development & {key["origin_index"] for key in saved["requested_keys"]})
        self.assertEqual(saved["union_gap_positions"], result["admission"]["union_gap_positions"])
        self.assertEqual(block["n"], len(rows))
        self.assertEqual(block["mature_span_count"], result["admission"]["mature_test_span_count"])

        if saved["comparison_status"] == STATUS_COMPARISON_UNAVAILABLE:
            self.assertIsNone(saved["method_rows"])
            self.assertEqual([p["point_difference"] for p in block["point_differences"]], [None, None])
            return block
        for model in ("heuristic", "frequency", "logistic"):
            self.assertEqual(
                saved["method_rows"][model],
                [{"origin_index": r["origin_index"], "origin_date": r["origin_date"], "brier": r[model]["brier"]} for r in rows],
            )
        if not rows:
            self.assertEqual([p["point_difference"] for p in block["point_differences"]], [None, None])
            return block
        for entry, comparator in zip(block["point_differences"], ("frequency", "logistic")):
            expected = math.fsum(r["heuristic"]["brier"] - r[comparator]["brier"] for r in rows) / len(rows)
            self.assertEqual(entry["point_difference"], expected)
        return block

    @staticmethod
    def _rewrite_rehashed(run_dir: Path, name: str, data: bytes) -> None:
        """Writes one artifact and its manifest entry, so only a semantic relation can object."""
        (run_dir / name).write_bytes(data)
        manifest = json.loads((run_dir / "run-manifest.json").read_text(encoding="utf-8"))
        entry = next(item for item in manifest["artifacts"] if item["path"] == name)
        entry.update(bytes=len(data), sha256=_sha(data))
        (run_dir / "run-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    def _trusted_replay(self) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        model_bytes = self.models_path.read_bytes()
        model = {
            "path": EXPECTED_MODELS_PATH,
            "raw_byte_count": len(model_bytes),
            "sha256": _sha(model_bytes),
            "platt_params": [1.42, 0.02],
        }
        return model, json.loads(self.build_manifest.read_text(encoding="utf-8"))


class TestStudyIntegration(_StudyIntegrationBase):
    """Integration tests requiring the scientific virtual environment and candidate Node build."""

    def test_warning_and_threadpool_ownership(self) -> None:
        """
        Verifies:
          1. Caller-owned restored single-thread threadpool context.
          2. warnings.catch_warnings(record=True) with simplefilter('always') first,
             filterwarnings('error', category=FutureWarning) second.
          3. Same-location ordinary warning emitted in both fits captured twice.
          4. Normally ignored warning category captured.
          5. FutureWarning raises error and fails run.
          6. Restoration of filters and thread limits on success/failure.
        """
        import threadpoolctl
        from research.prediction_eval.study import _execute_serial_comparators

        nifty_path, vix_path, cal_path = self._generate_synthetic_csv_data(290)
        nifty_loaded = load_series("nifty50_price_index", str(nifty_path))
        vix_loaded = load_series("india_vix", str(vix_path))
        with open(cal_path, "r", encoding="utf-8") as f:
            expected_sessions = [datetime.date.fromisoformat(d) for d in json.load(f)["sessions"]]
        aligned = align_pair(nifty_loaded, vix_loaded, expected_sessions=expected_sessions)
        outcomes = compute_twenty_session_outcomes(nifty_loaded)
        features = compute_nifty_features(aligned)

        dev_start = aligned.aligned_observations[235].date
        test_start = aligned.aligned_observations[260].date

        # State before execution
        initial_filters = list(warnings.filters)

        # Shared emission function to generate warnings at the exact same location in both fits
        def _emit_shared_diagnostic_warnings() -> None:
            warnings.warn("Same-location test warning", UserWarning, stacklevel=1)
            warnings.warn("Normally ignored test warning", DeprecationWarning, stacklevel=1)

        real_freq = study_mod.build_frequency_predictions

        # Import logistic to get real_log
        from research.prediction_eval.logistic import build_logistic_predictions as real_log

        inside_threads: List[List[int]] = []

        def _wrapped_freq(*args, **kwargs):
            inside_threads.append([pool["num_threads"] for pool in threadpoolctl.threadpool_info()])
            _emit_shared_diagnostic_warnings()
            return real_freq(*args, **kwargs)

        def _wrapped_log(*args, **kwargs):
            _emit_shared_diagnostic_warnings()
            return real_log(*args, **kwargs)

        with threadpoolctl.threadpool_limits(limits=2):
            threads_before = threadpoolctl.threadpool_info()
            with patch("research.prediction_eval.study.build_frequency_predictions", side_effect=_wrapped_freq):
                with patch("research.prediction_eval.logistic.build_logistic_predictions", side_effect=_wrapped_log):
                    freq_res, log_res, captured_warns = _execute_serial_comparators(
                        features, outcomes, development_start=dev_start, test_start=test_start
                    )
            # Thread limits are restored to the caller's state on success
            self.assertEqual(threadpoolctl.threadpool_info(), threads_before)

        self.assertTrue(inside_threads and all(n == 1 for n in inside_threads[0]))

        # Verify same-location UserWarning is captured exactly twice with identical filename and lineno
        same_loc_warns = [w for w in captured_warns if w["message"] == "Same-location test warning"]
        self.assertEqual(len(same_loc_warns), 2)
        self.assertEqual(same_loc_warns[0]["filename"], same_loc_warns[1]["filename"])
        self.assertEqual(same_loc_warns[0]["lineno"], same_loc_warns[1]["lineno"])
        self.assertEqual(same_loc_warns[0]["category"], "UserWarning")

        # Verify normally ignored DeprecationWarning is captured
        dep_warns = [w for w in captured_warns if w["message"] == "Normally ignored test warning"]
        self.assertEqual(len(dep_warns), 2)
        self.assertEqual(dep_warns[0]["category"], "DeprecationWarning")

        # Verify inner ConvergenceWarning is not in captured_warns
        self.assertNotIn("ConvergenceWarning", [w["category"] for w in captured_warns])

        # Verify warning filters restored on success
        self.assertEqual(warnings.filters, initial_filters)

        # Test failure path: ordinary warning emitted during frequency fit, then logistic fit raises
        def _warn_freq(*args, **kwargs):
            warnings.warn("Pre-failure ordinary warning", UserWarning, stacklevel=1)
            return real_freq(*args, **kwargs)

        def _failing_future_warn_log(*args, **kwargs):
            warnings.warn("Imminent breaking change in future version", FutureWarning, stacklevel=1)
            return real_log(*args, **kwargs)

        with threadpoolctl.threadpool_limits(limits=2):
            threads_before = threadpoolctl.threadpool_info()
            with patch("research.prediction_eval.study.build_frequency_predictions", side_effect=_warn_freq):
                with patch("research.prediction_eval.logistic.build_logistic_predictions", side_effect=_failing_future_warn_log):
                    with self.assertRaises(FutureWarning) as ctx:
                        _execute_serial_comparators(
                            features, outcomes, development_start=dev_start, test_start=test_start
                        )
                    # Verify ordinary warning emitted before failure was captured and preserved on exception
                    exc = ctx.exception
                    self.assertTrue(hasattr(exc, "captured_warnings"), "Exception missing captured_warnings")
                    exc_warns = getattr(exc, "captured_warnings")
                    self.assertTrue(any(w["message"] == "Pre-failure ordinary warning" for w in exc_warns),
                                    "Pre-failure ordinary warning was not retained on exception")
            # Thread limits are restored on failure as well
            self.assertEqual(threadpoolctl.threadpool_info(), threads_before)

        # Verify filters restored after exception
        self.assertEqual(warnings.filters, initial_filters)

        # Test failure path with arbitrary Exception: verify original category/message and ordinary warnings retained
        def _crashed_log(*args, **kwargs):
            raise RuntimeError("Logistic solver crashed unexpectedly")

        with patch("research.prediction_eval.study.build_frequency_predictions", side_effect=_warn_freq):
            with patch("research.prediction_eval.logistic.build_logistic_predictions", side_effect=_crashed_log):
                with self.assertRaises(RuntimeError) as ctx:
                    _execute_serial_comparators(
                        features, outcomes, development_start=dev_start, test_start=test_start
                    )
                exc = ctx.exception
                self.assertEqual(str(exc), "Logistic solver crashed unexpectedly")
                exc_warns = getattr(exc, "captured_warnings", [])
                self.assertTrue(any(w["message"] == "Pre-failure ordinary warning" for w in exc_warns))

        # Verify filters restored after exception
        self.assertEqual(warnings.filters, initial_filters)

    def test_handled_convergence_stays_owned_by_logistic(self) -> None:
        """A non-converged fit is block state, not a recorded warning, and restores filters."""
        from sklearn.exceptions import ConvergenceWarning
        from sklearn.linear_model import LogisticRegression

        fixture = self._fixture()
        config_path = self._write_config(fixture)
        filters_before = list(warnings.filters)
        real_fit = LogisticRegression.fit

        def _non_converging(self_clf, X, y):
            warnings.warn("Optimization failed to converge", ConvergenceWarning)
            return real_fit(self_clf, X, y)

        with patch.object(LogisticRegression, "fit", _non_converging):
            run_dir = self._run(config_path, "run_not_converged")

        self.assertEqual(warnings.filters, filters_before)
        result = self._json(run_dir / "result.json")
        block = result["partitions"]["test"]["logistic_block"]
        self.assertEqual(block["unavailable_reason"], "not_converged")
        self.assertEqual(block["failure_stage"], "fit")
        self.assertIsNone(block["fit"])
        self.assertEqual(len(block["fitting_indices"]), 40)
        self.assertEqual(sum(block["class_counts"]), 40)
        self.assertEqual(result["partitions"]["test"]["comparison_status"], STATUS_COMPARISON_UNAVAILABLE)
        self.assertNotIn("ConvergenceWarning", [w["category"] for w in result["warnings"]])
        summary = self._json(run_dir / "panel-summary.json")
        self.assertEqual(summary["partitions"]["test"]["method_states"]["logistic"]["failure_stage"], "fit")

    def test_end_to_end_synthetic_study_through_main(self) -> None:
        """
        End-to-end integration test through the actual main:
          synthetic loader -> frozen admission -> exporter -> pinned Node replay -> adapter ->
          real frequency & logistic -> accepted scorer -> persisted artifacts -> promotion seam.
        """
        fixture = self._fixture()
        config_path = self._write_config(fixture)
        run_dir = self.work_parent / "run_e2e_001"

        with patch.object(study_mod, "compute_uncertainty", wraps=study_mod.compute_uncertainty) as engine:
            exit_code = main(["--config", str(config_path), "--output-dir", str(run_dir)])
        self.assertEqual(exit_code, 0)

        # The caller hands the engine its verified runtime and the identity of the written bytes
        self.assertEqual(engine.call_count, 1)
        self.assertEqual(
            engine.call_args.kwargs["runtime_identity"],
            {"python_implementation": platform.python_implementation(), "python_version": platform.python_version()},
        )
        self.assertEqual(engine.call_args.args[0].input_identity, _identity(run_dir / "uncertainty-input.json"))

        # Verify artifacts exist on disk
        for name in (
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
            "run-manifest.json",
        ):
            self.assertTrue((run_dir / name).exists(), name)
        self.assertFalse((run_dir / FAILURE_RECORD_NAME).exists())

        # config.json and admission.json are the exact frozen bytes, not a reserialization
        self.assertEqual((run_dir / "config.json").read_bytes(), config_path.read_bytes())
        self.assertEqual((run_dir / "admission.json").read_bytes(), (config_path.parent / "admission.json").read_bytes())

        # Completion and promotion seams on the written bytes
        summary_bytes = (run_dir / "panel-summary.json").read_bytes()
        manifest_bytes = (run_dir / "run-manifest.json").read_bytes()
        ok, msg = verify_completed_run(run_dir)
        self.assertTrue(ok, msg)
        ok, msg = verify_completion_binding(summary_bytes, manifest_bytes)
        self.assertTrue(ok, msg)
        ok, msg = verify_promotion_binding(summary_bytes, manifest_bytes, build_candidate_descriptor(summary_bytes, manifest_bytes))
        self.assertTrue(ok, msg)

        result = self._json(run_dir / "result.json")
        summary = json.loads(summary_bytes.decode("utf-8"))
        manifest = json.loads(manifest_bytes.decode("utf-8"))
        validate_result_document(result)
        validate_summary_document(summary)

        # Ensure intended scored blocks actually scored with all training classes
        for name in ("development", "test"):
            part = result["partitions"][name]
            self.assertEqual(part["comparison_status"], STATUS_SCORED)
            self.assertTrue(all(count > 0 for count in part["logistic_block"]["class_counts"]), part["logistic_block"]["class_counts"])
            self.assertIsNotNone(part["logistic_block"]["fit"])
            self.assertEqual(len(part["logistic_block"]["fit"]["coefficients"]), 3)

        # Coverage from the stated policy, N=290, D=235, T=260, horizon 20
        n, d, t = 290, 235, 260
        counts = {name: summary["partitions"][name]["counts"] for name in ("development", "test")}
        self.assertEqual(counts["development"]["raw_partition_count"], t - d)
        self.assertEqual(counts["development"]["eligible_count"], (t - HORIZON_SESSIONS) - d)
        self.assertEqual(counts["development"]["excluded_count"], HORIZON_SESSIONS)
        self.assertEqual(counts["test"]["raw_partition_count"], n - t)
        self.assertEqual(counts["test"]["eligible_count"], (n - HORIZON_SESSIONS) - t)
        self.assertEqual(counts["test"]["excluded_count"], HORIZON_SESSIONS)
        self.assertEqual(counts["test"]["exclusion_reason_counts"], {"unknown_outcome": HORIZON_SESSIONS})

        # Persisted oracles from fixture closes and persisted probabilities, not from the scorer
        for name in ("development", "test"):
            part = result["partitions"][name]
            metrics = summary["partitions"][name]["metrics"]
            rows = part["per_origin_records"]
            self.assertEqual([r["origin_index"] for r in rows], part["requested_indices"])
            for model in ("heuristic", "frequency", "logistic"):
                confusion = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
                briers: List[float] = []
                bins = [[0] * 10 for _ in range(3)]
                for row in rows:
                    origin = row["origin_index"]
                    c0 = Fraction(fixture.closes[origin])
                    c20 = Fraction(fixture.closes[origin + 20])
                    expected_class = "BULL" if 200 * c20 > 201 * c0 else ("BEAR" if 200 * c20 < 199 * c0 else "NEUTRAL")
                    self.assertEqual(row["actual_class"], expected_class)
                    self.assertEqual(row["maturity_index"], origin + 20)

                    actual = ("BEAR", "NEUTRAL", "BULL").index(expected_class)
                    probabilities = row[model]["probabilities"]
                    expected_brier = sum((p - (1.0 if k == actual else 0.0)) ** 2 for k, p in enumerate(probabilities))
                    self.assertAlmostEqual(row[model]["brier"], expected_brier, places=12)
                    briers.append(expected_brier)
                    self.assertAlmostEqual(row[model]["log_loss"], -math.log(probabilities[actual]), places=12)
                    self.assertEqual(row[model]["log_loss_state"], "finite")

                    predicted = probabilities.index(max(probabilities))
                    self.assertEqual(row[model]["predicted_class"], ("BEAR", "NEUTRAL", "BULL")[predicted])
                    confusion[actual][predicted] += 1
                    for k, p in enumerate(probabilities):
                        bins[k][min(9, sum(1 for edge in range(1, 10) if p >= edge / 10.0))] += 1

                model_metrics = metrics["models"][model]
                self.assertEqual(model_metrics["confusion"], confusion)
                self.assertAlmostEqual(model_metrics["mean_brier"], sum(briers) / len(briers), places=12)
                self.assertEqual([b["count"] for b in model_metrics["reliability_bins"]], bins[0] + bins[1] + bins[2])

        # Heuristic rows keep the verbal direction apart from the first-max class
        self.assertIn(
            result["partitions"]["test"]["per_origin_records"][0]["heuristic"]["expected_direction"],
            ("STRONGLY BULLISH", "MODERATELY BULLISH", "NEUTRAL / RANGE-BOUND", "MODERATELY BEARISH", "STRONGLY BEARISH"),
        )

        # Identities are measured bytes, from the real files
        self.assertEqual(result["input_identities"]["nifty"]["sha256"], _sha(fixture.nifty.read_bytes()))
        self.assertEqual(result["input_identities"]["calendar"]["sha256"], _sha(fixture.calendar.read_bytes()))
        self.assertEqual(result["config_identity"]["sha256"], _sha(config_path.read_bytes()))
        for rel in REQUIRED_SOURCE_MODULES:
            self.assertEqual(result["source_identities"][rel], _identity(WORKSPACE_ROOT / rel))
        self.assertEqual(result["model_identity"]["sha256"], EXPECTED_MODELS_SHA256)
        self.assertEqual(result["build_identity"]["sha256"], _sha(self.build_manifest.read_bytes()))
        self.assertEqual(result["runtime_identities"]["dependency_versions"], self.dependency_versions)
        self.assertEqual(result["replay_identity"]["response"], _identity(run_dir / "replay-response.json"))
        self.assertEqual(result["comparator_metadata"]["logistic"]["configuration"]["max_iter"], 2000)
        self.assertEqual(result["comparator_metadata"]["frequency"]["alpha"], 1.0)
        self.assertEqual(manifest["source_identities"], result["source_identities"])
        self.assertEqual(manifest["input_identities"], result["input_identities"])
        self.assertEqual(manifest["runtime_identities"], result["runtime_identities"])
        self.assertEqual(summary["run_id"], "run_e2e_001")
        self.assertEqual(summary["replay_identity"], result["replay_identity"])

        # Native receipt of the real child
        receipt = self._json(run_dir / "replay-invocation.json")
        self.assertEqual(receipt["immediate_child_exit"], 0)
        self.assertEqual(receipt["capture_state"], "complete")
        self.assertFalse(receipt["shell"])
        self.assertEqual(receipt["exe"], self.node_exe)
        self.assertEqual(receipt["cwd"], str(WORKSPACE_ROOT))

        # The aggregate is a whitelist: no rows, coefficients, closes or absolute paths
        summary_text = summary_bytes.decode("utf-8")
        for forbidden in ("per_origin_records", "coefficients", "origin_close", str(WORKSPACE_ROOT).replace("\\", "\\\\"), "numeric_means"):
            self.assertNotIn(forbidden, summary_text)
        manifest_text = manifest_bytes.decode("utf-8")
        self.assertNotIn(str(WORKSPACE_ROOT).replace("\\", "\\\\"), manifest_text)
        self.assertEqual(summary["uncertainty"]["status"], "unavailable")
        self.assertEqual(summary["dataset_attribution"]["source_kind"], "synthetic_fixture")

        # n=10 is below every floor: full-cohort points stay, and every length says why it has none
        block = self._assert_uncertainty_binds_test_rows(run_dir)
        self.assertEqual((block["n"], block["reason"]), (10, "insufficient_nominal_blocks"))
        self.assertEqual([view["reason"] for view in block["block_lengths"]], ["insufficient_nominal_blocks"] * 3)
        for view in block["block_lengths"]:
            self.assertEqual([(p["lower"], p["upper"]) for p in view["pairs"]], [(None, None), (None, None)])
        self.assertEqual(result["source_identities"][UNCERTAINTY_MODULE], _identity(WORKSPACE_ROOT / UNCERTAINTY_MODULE))
        self.assertEqual(set(manifest["source_identities"]), set(EXPECTED_SOURCE_MODULES))
        diagnostics = self._json(run_dir / "uncertainty-diagnostics.json")
        self.assertEqual(diagnostics["input_identity"], _identity(run_dir / "uncertainty-input.json"))
        self.assertEqual(diagnostics["resource"], {"max_resample_positions": 30000000, "required_positions": 0, "visited_positions": 0})
        self.assertEqual(diagnostics["runtime_identity"]["python_version"], platform.python_version())

        report = (run_dir / "report.md").read_text(encoding="utf-8")
        self.assertIn("Raw Partition Origins: 30", report)
        self.assertIn("Excluded Observations: 20", report)

    def test_repeat_semantic_results(self) -> None:
        """Verifies deterministic semantic outputs under identical frozen inputs into separate roots with n620 all-length available cohort."""
        fixture = self._fixture(total_sessions=900)
        config_path = self._write_config(fixture, d_index=235, t_index=260)

        # Local RNG constructions are observed through the engine's own module reference
        real_random = uncertainty_mod.random.Random
        constructed: List[int] = []

        def _recording_random(seed: int) -> Any:
            constructed.append(seed)
            return real_random(seed)

        # Phase 1: Reserve budget before run 1
        _reserve_sampling_budget("test_repeat_semantic_results_run1", 18600000, budget=INTEGRATION_BUDGET)
        with patch.object(uncertainty_mod, "random", SimpleNamespace(Random=_recording_random)):
            run_dir_1 = self._run(config_path, "run_repeat_001")
        # Phase 2: Complete run 1 after observing diagnostics evidence
        diag_1 = self._json(run_dir_1 / "uncertainty-diagnostics.json")
        visited_1 = sum(item["sampled_positions"] for item in diag_1["lengths"])
        _complete_sampling_call("test_repeat_semantic_results_run1", visited_1, budget=INTEGRATION_BUDGET)
        self.assertEqual(constructed, [20261123, 20261143, 20261163])

        # Phase 1: Reserve budget before run 2
        _reserve_sampling_budget("test_repeat_semantic_results_run2", 18600000, budget=INTEGRATION_BUDGET)
        run_dir_2 = self._run(config_path, "run_repeat_002")
        # Phase 2: Complete run 2 after observing diagnostics evidence
        diag_2 = self._json(run_dir_2 / "uncertainty-diagnostics.json")
        visited_2 = sum(item["sampled_positions"] for item in diag_2["lengths"])
        _complete_sampling_call("test_repeat_semantic_results_run2", visited_2, budget=INTEGRATION_BUDGET)

        doc_1 = self._json(run_dir_1 / "panel-summary.json")
        doc_2 = self._json(run_dir_2 / "panel-summary.json")

        # Semantic equality: partitions and metrics match identically
        self.assertEqual(doc_1["partitions"], doc_2["partitions"])
        self.assertEqual(doc_1["admission_summary"], doc_2["admission_summary"])
        self.assertEqual(doc_1["fixed_definitions"], doc_2["fixed_definitions"])
        self.assertEqual(doc_1["replay_identity"], doc_2["replay_identity"])
        self.assertNotEqual(doc_1["run_id"], doc_2["run_id"])
        self.assertEqual((run_dir_1 / "predictions.json").read_bytes(), (run_dir_2 / "predictions.json").read_bytes())

        # S2 n620 all-length check: all three block lengths available and identical
        u1 = doc_1["uncertainty"]
        u2 = doc_2["uncertainty"]
        self.assertEqual(u1, u2)
        self.assertEqual(u1["status"], "available")
        self.assertIsNone(u1["reason"])
        self.assertEqual(u1["n"], 620)
        self.assertEqual(len(u1["block_lengths"]), 3)
        for bl in u1["block_lengths"]:
            self.assertEqual(bl["status"], "available")
            self.assertIsNone(bl["reason"])
            self.assertIn(bl["block_length"], (20, 40, 60))
            self.assertEqual(len(bl["pairs"]), 2)
            for pair in bl["pairs"]:
                self.assertIsNotNone(pair["lower"])
                self.assertIsNotNone(pair["upper"])
                self.assertLessEqual(pair["lower"], pair["upper"])

        self.assertEqual(
            (run_dir_1 / "uncertainty-input.json").read_bytes(),
            (run_dir_2 / "uncertainty-input.json").read_bytes(),
        )
        self.assertEqual(
            (run_dir_1 / "uncertainty-diagnostics.json").read_bytes(),
            (run_dir_2 / "uncertainty-diagnostics.json").read_bytes(),
        )

        # The same two runs are the completion, promotion and available-counter oracles
        summary_bytes = (run_dir_2 / "panel-summary.json").read_bytes()
        manifest_bytes = (run_dir_2 / "run-manifest.json").read_bytes()
        ok, msg = verify_completed_run(run_dir_2)
        self.assertTrue(ok, msg)
        ok, msg = verify_promotion_binding(summary_bytes, manifest_bytes, build_candidate_descriptor(summary_bytes, manifest_bytes))
        self.assertTrue(ok, msg)
        self._assert_uncertainty_binds_test_rows(run_dir_2)

        self.assertEqual(diag_2["resource"], {"max_resample_positions": 30000000, "required_positions": 18600000, "visited_positions": 18600000})
        for length in diag_2["lengths"]:
            self.assertEqual(length["replicates_completed"], 10000)
            self.assertEqual(length["sampled_positions"], 6200000)
            self.assertEqual(length["random_calls"], 6190000)
            self.assertGreater(length["randrange_calls"], 10000)
            self.assertRegex(length["index_stream_sha256"], r"\A[0-9A-F]{64}\Z")
        self.assertEqual(len({length["index_stream_sha256"] for length in diag_2["lengths"]}), 3)

        def _counter(pos: int, **changes: Any) -> Callable[[Dict[str, Any]], None]:
            return lambda doc: doc["lengths"][pos].update(changes)

        def _block(doc: Dict[str, Any], **changes: Any) -> None:
            doc["uncertainty"].update(changes)

        def _unavailable_top_length(doc: Dict[str, Any]) -> None:
            view = doc["uncertainty"]["block_lengths"][2]
            view.update(status="unavailable", reason="insufficient_nominal_blocks")
            for pair in view["pairs"]:
                pair.update(lower=None, upper=None)
            doc["uncertainty"]["status"] = "partially_available"

        counters: Dict[str, Tuple[str, Callable[[Dict[str, Any]], None], str]] = {
            "random_calls": ("uncertainty-diagnostics.json", _counter(0, random_calls=6189999), "random_calls"),
            "randrange_below_initial": ("uncertainty-diagnostics.json", _counter(1, randrange_calls=9999), "randrange_calls"),
            "sampled_positions": ("uncertainty-diagnostics.json", _counter(2, sampled_positions=6210000, random_calls=6200000), "visited_positions"),
            "missing_fingerprint": ("uncertainty-diagnostics.json", _counter(0, index_stream_sha256=None), "index_stream_sha256"),
            "lower_case_fingerprint": ("uncertainty-diagnostics.json", _counter(0, index_stream_sha256="a" * 64), "index_stream_sha256"),
            "seed_swap": ("uncertainty-diagnostics.json", _counter(0, seed=20261143), "seed"),
            "required": ("uncertainty-diagnostics.json", lambda doc: doc["resource"].update(required_positions=18599999), "required_positions"),
            "n_in_both": ("result.json", lambda doc: _block(doc, n=619), "n == mature_span_count"),
            "length_dropped_in_result": ("result.json", _unavailable_top_length, "contradicts its floor"),
        }
        tamper_parent = self.work_parent / "tamper_copy"
        tamper_parent.mkdir()
        tamper_dir = tamper_parent / run_dir_2.name
        tamper_dir.mkdir()
        for item in run_dir_2.iterdir():
            (tamper_dir / item.name).write_bytes(item.read_bytes())
        for name, (artifact, mutate, expected) in counters.items():
            original = (tamper_dir / artifact).read_bytes()
            original_manifest = (tamper_dir / "run-manifest.json").read_bytes()
            doc = json.loads(original.decode("utf-8"))
            mutate(doc)
            self._rewrite_rehashed(tamper_dir, artifact, json.dumps(doc, indent=2).encode("utf-8") + b"\n")
            with self.subTest(case=name):
                ok, msg = verify_completed_run(tamper_dir)
                self.assertFalse(ok)
                self.assertIn(expected, msg)
            (tamper_dir / artifact).write_bytes(original)
            (tamper_dir / "run-manifest.json").write_bytes(original_manifest)
        ok, msg = verify_completed_run(tamper_dir)
        self.assertTrue(ok, msg)

    def test_cap_one_refuses_at_the_actual_caller_before_any_rng(self) -> None:
        """n=200 clears L20, so a valid run needs 2000000 positions; cap 1 must refuse them."""

        def _forbidden_random(seed: int) -> Any:
            raise AssertionError(f"RNG constructed with seed {seed}")

        def _cap_one(doc: Dict[str, Any]) -> None:
            doc["uncertainty"]["max_resample_positions"] = 1

        config = load_study_configuration_file(self._write_config(self._fixture(total_sessions=480), mutate=_cap_one))
        run_dir = self.work_parent / "run_cap_one"
        with patch.object(uncertainty_mod, "random", SimpleNamespace(Random=_forbidden_random)):
            with self.assertRaises(UncertaintyResourceError) as ctx:
                run_study(config, run_dir, allowed_parent=config.allowed_output_parent)

        self.assertEqual(ctx.exception.required_positions, 2000000)
        self.assertEqual(ctx.exception.max_positions, 1)
        failure = self._failure(run_dir)
        self.assertEqual(failure["stage"], "uncertainty")
        self.assertEqual(failure["error_type"], "UncertaintyResourceError")
        self.assertTrue((run_dir / "uncertainty-input.json").exists())
        self.assertIn("uncertainty-input.json", [a["path"] for a in failure["partial_artifacts"]])
        for name in ("uncertainty-diagnostics.json", "result.json", "panel-summary.json"):
            self.assertFalse((run_dir / name).exists(), name)

    def test_inconsistent_artifacts_stop_before_the_manifest(self) -> None:
        """A projection or counter fault that hashes cleanly still leaves no completion."""
        real_serialize = study_mod.serialize_uncertainty_input
        real_diagnostics = study_mod.build_uncertainty_diagnostics_document

        def _wrong_saved_loss(request: Any) -> bytes:
            doc = json.loads(real_serialize(request).decode("ascii"))
            doc["method_rows"]["heuristic"][0]["brier"] = 0.125
            text = json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            return text.encode("ascii") + b"\n"

        def _wrong_required_count(diagnostics: Any) -> Dict[str, Any]:
            doc = real_diagnostics(diagnostics)
            doc["resource"]["required_positions"] = 1
            return doc

        real_adapter = study_mod.run_replay_adapter
        real_predictions = study_mod.build_predictions_document

        def _response_changed_after_capture(*args: Any, **kwargs: Any) -> Any:
            # Simulated drift between the real child's capture and the inventory before the manifest
            returned = real_adapter(*args, **kwargs)
            response = Path(kwargs["work_dir"]) / "replay-response.json"
            response.write_bytes(response.read_bytes() + b" ")
            return returned

        def _wrong_prediction_row(result: Any) -> Dict[str, Any]:
            doc = real_predictions(result)
            doc["test"][0]["origin_close"] = "0.00"
            return doc

        cases = (
            ("saved_loss", patch.object(study_mod, "serialize_uncertainty_input", _wrong_saved_loss), "loss mismatch"),
            ("required_count", patch.object(study_mod, "build_uncertainty_diagnostics_document", _wrong_required_count), "required_positions"),
            ("replay_response", patch.object(study_mod, "run_replay_adapter", _response_changed_after_capture), "result.replay_identity.response"),
            ("predictions", patch.object(study_mod, "build_predictions_document", _wrong_prediction_row), "predictions.json"),
        )
        for name, injected, expected in cases:
            with self.subTest(case=name):
                config = load_study_configuration_file(self._write_config(self._fixture()))
                run_dir = self.work_parent / f"run_inconsistent_{name}"
                with injected:
                    with self.assertRaises(RuntimeError) as ctx:
                        run_study(config, run_dir, allowed_parent=config.allowed_output_parent)
                self.assertIn(expected, str(ctx.exception))
                failure = self._failure(run_dir)
                self.assertEqual(failure["stage"], "verify_artifacts")
                self.assertTrue((run_dir / "report.md").exists())
                self.assertTrue((run_dir / "replay-invocation.json").exists())

    def test_empty_mature_test_cohort_completes_with_both_uncertainty_artifacts(self) -> None:
        """Every mature test origin lacks VIX: the cohort is empty, not a gap with points."""
        fixture = self._fixture(missing_vix=tuple(range(260, 270)))
        run_dir = self._run(self._write_config(fixture), "run_empty_test")

        ok, msg = verify_completed_run(run_dir)
        self.assertTrue(ok, msg)
        block = self._assert_uncertainty_binds_test_rows(run_dir)
        self.assertEqual((block["reason"], block["n"], block["mature_span_count"]), ("empty_cohort", 0, 10))
        self.assertEqual([view["reason"] for view in block["block_lengths"]], ["empty_cohort"] * 3)
        saved = self._json(run_dir / "uncertainty-input.json")
        self.assertEqual(saved["comparison_status"], STATUS_EMPTY)
        self.assertEqual(saved["union_gap_positions"], list(range(260, 270)))

    def test_gap_keeps_original_horizon_and_label(self) -> None:
        """
        Origin 262 closes at 100.00, origin+20 at 99.40 and origin+21 at 101.00, with VIX missing at
        origin+10. The label stays BEAR at exactly i+20: a compressed horizon would reach 101.00.
        """
        overrides = {262: "100.00", 282: "99.40", 283: "101.00"}
        fixture = self._fixture(close_fn=lambda i: overrides.get(i, _wave_close(i)), missing_vix=(272,))
        config_path = self._write_config(fixture, d_index=235, t_index=260)
        run_dir = self._run(config_path, "run_gap")

        result = self._json(run_dir / "result.json")
        test_part = result["partitions"]["test"]
        row = next(r for r in test_part["per_origin_records"] if r["origin_index"] == 262)
        self.assertEqual(row["actual_class"], OUTCOME_CLASS_BEAR)
        self.assertEqual(row["maturity_index"], 282)
        self.assertEqual(row["maturity_date"], fixture.dates[282].isoformat())
        self.assertEqual(row["maturity_close"], "99.40")

        # N=290: mature span [260,270) has no VIX gap; 272 sits in the unknown tail, adding a reason only
        self.assertEqual(result["admission"]["union_gap_positions"], [])
        self.assertEqual(test_part["counts"]["exclusion_reason_counts"], {"missing_vix": 1, "unknown_outcome": 20})
        self.assertEqual(test_part["counts"]["excluded_count"], 20)

    def test_mature_gap_is_frozen_and_reaches_summary(self) -> None:
        """A VIX gap inside the mature span is admitted before results and excluded by the planner."""
        fixture = self._fixture(missing_vix=(263,))
        config_path = self._write_config(fixture)
        run_dir = self._run(config_path, "run_mature_gap")

        summary = self._json(run_dir / "panel-summary.json")
        self.assertEqual(summary["admission_summary"]["union_gap_count"], 1)
        self.assertEqual(summary["partitions"]["test"]["counts"]["eligible_count"], 9)
        self.assertEqual(summary["partitions"]["test"]["counts"]["excluded_count"], 21)
        self.assertEqual(
            self._json(run_dir / "result.json")["partitions"]["test"]["requested_indices"],
            [i for i in range(260, 270) if i != 263],
        )

        # The gap removes every interval, not the full-cohort points of the origins that remain
        ok, msg = verify_completed_run(run_dir)
        self.assertTrue(ok, msg)
        block = self._assert_uncertainty_binds_test_rows(run_dir)
        self.assertEqual((block["status"], block["reason"], block["n"], block["mature_span_count"]), ("unavailable", "non_contiguous_test_cohort", 9, 10))
        self.assertEqual([view["reason"] for view in block["block_lengths"]], ["non_contiguous_test_cohort"] * 3)
        self.assertEqual(self._json(run_dir / "uncertainty-input.json")["union_gap_positions"], [263])
        self.assertIsNotNone(summary["partitions"]["test"]["metrics"])

    def test_strict_purges_survive_composition(self) -> None:
        """
        D=235: origin D-20=215 matures exactly at D, so train stops at 214. T=260: origin T-20=240
        matures exactly at T, so development stops at 239 and the refit pool stops at 239 as well.
        """
        fixture = self._fixture()
        run_dir = self._run(self._write_config(fixture), "run_purges")
        result = self._json(run_dir / "result.json")

        dev = result["partitions"]["development"]
        test = result["partitions"]["test"]
        self.assertEqual(dev["frequency_block"]["fitting_indices"], list(range(200, 215)))
        self.assertEqual(dev["logistic_block"]["fitting_indices"], list(range(200, 215)))
        self.assertEqual(dev["requested_indices"], list(range(235, 240)))
        self.assertEqual(dev["requested_dates"], [fixture.dates[i].isoformat() for i in range(235, 240)])
        self.assertEqual(test["frequency_block"]["fitting_indices"], list(range(200, 240)))
        self.assertEqual(test["logistic_block"]["fitting_indices"], list(range(200, 240)))
        self.assertEqual(test["requested_indices"], list(range(260, 270)))
        self.assertEqual(dev["frequency_block"]["cutoff_date"], fixture.dates[235].isoformat())
        self.assertEqual(test["logistic_block"]["cutoff_index"], 260)

    def test_future_data_cannot_change_earlier_replay_or_development(self) -> None:
        """Changing closes at or after T leaves pre-T replay forecasts and development rows identical."""
        base = self._fixture()
        perturbed = self._fixture(close_fn=lambda i: _wave_close(i) if i < 260 else f"{float(_wave_close(i)) * 0.5:.2f}")

        base_dir = self._run(self._write_config(base), "run_future_base")
        pert_dir = self._run(self._write_config(perturbed), "run_future_pert")

        base_replay = self._json(base_dir / "replay-response.json")
        pert_replay = self._json(pert_dir / "replay-response.json")
        self.assertEqual(base_replay["forecasts"][:260], pert_replay["forecasts"][:260])

        base_result = self._json(base_dir / "result.json")
        pert_result = self._json(pert_dir / "result.json")
        self.assertEqual(
            base_result["partitions"]["development"]["per_origin_records"],
            pert_result["partitions"]["development"]["per_origin_records"],
        )
        self.assertEqual(
            base_result["partitions"]["development"]["logistic_block"],
            pert_result["partitions"]["development"]["logistic_block"],
        )
        # The refit pool ends before T as well, so the test-block fit is unchanged even though
        # the test rows themselves may differ
        self.assertEqual(
            base_result["partitions"]["test"]["logistic_block"]["fit"],
            pert_result["partitions"]["test"]["logistic_block"]["fit"],
        )

    def test_missing_class_fit_keeps_usable_forecasts_through_a_real_run(self) -> None:
        """
        Flat closes label every origin NEUTRAL, so logistic has missing classes while heuristic
        and frequency stay usable. Laplace-1 on n NEUTRAL rows gives (1, n+1, 1) / (n+3).
        """
        fixture = self._fixture(close_fn=lambda i: "15000.00")
        config_path = self._write_config(fixture)

        real_score = study_mod.score_comparison
        with patch.object(study_mod, "score_comparison", side_effect=real_score) as scorer:
            run_dir = self._run(config_path, "run_partial")
        scorer.assert_not_called()

        ok, msg = verify_completed_run(run_dir)
        self.assertTrue(ok, msg)
        result = self._json(run_dir / "result.json")
        for name, n in (("development", 15), ("test", 40)):
            part = result["partitions"][name]
            self.assertEqual(part["comparison_status"], STATUS_COMPARISON_UNAVAILABLE)
            self.assertIsNone(part["metrics"])
            self.assertEqual(part["comparison_unavailable_reasons"], ["logistic: missing_training_classes"])
            block = part["logistic_block"]
            self.assertIsNone(block["fit"])
            self.assertIsNone(block["failure_stage"])
            self.assertEqual(block["class_counts"], [0, n, 0])
            self.assertEqual(len(block["fitting_indices"]), n)
            self.assertEqual(part["frequency_block"]["fit"]["class_counts"], [0, n, 0])
            self.assertGreater(len(part["per_origin_records"]), 0)
            for row in part["per_origin_records"]:
                self.assertEqual(row["score_state"], "unscored")
                self.assertEqual(row["actual_class"], OUTCOME_CLASS_NEUTRAL)
                self.assertEqual(row["logistic"]["forecast_state"], "unavailable")
                self.assertIsNone(row["logistic"]["probabilities"])
                self.assertEqual(row["frequency"]["probabilities"], [1 / (n + 3), (n + 1) / (n + 3), 1 / (n + 3)])
                self.assertEqual(row["heuristic"]["forecast_state"], "available")
                self.assertIsNotNone(row["heuristic"]["probabilities"])
                self.assertIsNone(row["frequency"]["brier"])
                self.assertIsNone(row["heuristic"]["log_loss"])

        summary = self._json(run_dir / "panel-summary.json")
        self.assertIsNone(summary["partitions"]["test"]["metrics"])
        self.assertEqual(summary["partitions"]["test"]["counts"]["model_available_counts"], {"heuristic": 10, "frequency": 10, "logistic": 0})
        self.assertIn("logistic: missing_training_classes", (run_dir / "report.md").read_text(encoding="utf-8"))

        block = self._assert_uncertainty_binds_test_rows(run_dir)
        self.assertEqual((block["reason"], block["n"]), ("comparison_unavailable", 10))
        saved = self._json(run_dir / "uncertainty-input.json")
        self.assertEqual(saved["method_available"], {"heuristic": True, "frequency": True, "logistic": False})

    def test_genuine_empty_target_follows_accepted_empty_scoring(self) -> None:
        """All fits available with no eligible development origin is empty, not unavailable."""
        fixture = self._fixture(missing_vix=tuple(range(235, 240)))
        run_dir = self._run(self._write_config(fixture), "run_empty")

        summary = self._json(run_dir / "panel-summary.json")
        development = summary["partitions"]["development"]
        self.assertEqual(development["comparison_status"], STATUS_EMPTY)
        self.assertEqual(development["comparison_unavailable_reasons"], [])
        self.assertEqual(development["counts"]["eligible_count"], 0)
        self.assertEqual(development["counts"]["excluded_count"], 25)
        metrics = development["metrics"]
        self.assertEqual(metrics["status"], "empty")
        self.assertEqual(metrics["sample_count"], 0)
        for model in metrics["models"].values():
            self.assertIsNone(model["mean_brier"])
            self.assertEqual(model["log_loss_state"], "empty")
            self.assertEqual(model["class_recall"], [None, None, None])
        self.assertEqual(summary["partitions"]["test"]["comparison_status"], STATUS_SCORED)

    def test_identity_and_admission_drift_stop_before_scientific_work(self) -> None:
        """Every case fails before outcomes exist; drift is simulated only in generated files or expected values."""

        def _forbidden(*args: Any, **kwargs: Any) -> None:
            raise AssertionError("scientific work ran after failed verification")

        def _source_drift(doc: Dict[str, Any]) -> None:
            doc["source_modules"]["research/prediction_eval/metrics.py"]["sha256"] = "D" * 64

        def _uncertainty_source_drift(doc: Dict[str, Any]) -> None:
            doc["source_modules"][UNCERTAINTY_MODULE]["sha256"] = "D" * 64

        def _uncertainty_source_size_drift(doc: Dict[str, Any]) -> None:
            doc["source_modules"][UNCERTAINTY_MODULE]["raw_byte_count"] += 1

        def _model_alternative(doc: Dict[str, Any]) -> None:
            doc["tools"]["models"]["path"] = str(Path(doc["admission"]["path"]).parent / "models.json")

        def _build_alternative(doc: Dict[str, Any]) -> None:
            doc["tools"]["candidate_build_manifest"]["path"] = str(Path(doc["admission"]["path"]).parent / "build.json")

        def _node_drift(doc: Dict[str, Any]) -> None:
            doc["tools"]["node_executable"]["sha256"] = "D" * 64

        def _runtime_drift(doc: Dict[str, Any]) -> None:
            doc["runtime"]["python_version"] = "3.0.0"

        def _workspace_drift(doc: Dict[str, Any]) -> None:
            doc["workspace_root"] = str(Path(doc["admission"]["path"]).parent)

        def _forged_gap(record: Dict[str, Any]) -> None:
            record["union_gap_positions"] = [263]
            record["union_gap_count"] = 1

        def _forged_cutoff(record: Dict[str, Any]) -> None:
            record["test_start"] = "2021-01-05"

        def _coherent_forged_gap(record: Dict[str, Any]) -> None:
            # Internally consistent, so only the input-only comparison can reject it
            record["missing_vix_gap_positions"] = [263]
            record["missing_vix_gap_count"] = 1
            record["union_gap_positions"] = [263]
            record["union_gap_count"] = 1

        def _coherent_forged_cutoff(record: Dict[str, Any]) -> None:
            record["test_start"] = record["axis"]["last_date"]

        cases = [
            ("source_hash", {"mutate": _source_drift}, "verify_prerequisites"),
            ("uncertainty_source_hash", {"mutate": _uncertainty_source_drift}, "verify_prerequisites"),
            ("uncertainty_source_size", {"mutate": _uncertainty_source_size_drift}, "verify_prerequisites"),
            ("model_path", {"mutate": _model_alternative}, "verify_prerequisites"),
            ("build_path", {"mutate": _build_alternative}, "verify_prerequisites"),
            ("node_hash", {"mutate": _node_drift}, "verify_prerequisites"),
            ("runtime", {"mutate": _runtime_drift}, "verify_prerequisites"),
            ("forged_gap_list", {"admission_mutate": _forged_gap}, "verify_admission"),
            ("forged_cutoff", {"admission_mutate": _forged_cutoff}, "verify_admission"),
            ("coherent_forged_gap", {"admission_mutate": _coherent_forged_gap}, "verify_admission"),
            ("coherent_forged_cutoff", {"admission_mutate": _coherent_forged_cutoff}, "verify_admission"),
        ]
        for name, kwargs, stage in cases:
            with self.subTest(case=name):
                config_path = self._write_config(self._fixture(), **kwargs)
                run_dir = self.work_parent / f"run_drift_{name}"
                config = load_study_configuration_file(config_path)
                with patch.object(study_mod, "compute_twenty_session_outcomes", _forbidden), patch.object(
                    study_mod, "compute_nifty_features", _forbidden
                ), patch.object(study_mod, "run_replay_adapter", _forbidden):
                    with self.assertRaises(InputValidationError):
                        run_study(config, run_dir, allowed_parent=config.allowed_output_parent)
                failure = self._failure(run_dir)
                self.assertEqual(failure["stage"], stage)
                self.assertEqual(failure["error_type"], "InputValidationError")
                self.assertFalse((run_dir / "result.json").exists())
                self.assertFalse((run_dir / "predictions.json").exists())

        # A wrong workspace would name the wrong protected roots, so it refuses before any directory
        # or failure record exists, under the same meaningful field
        config = load_study_configuration_file(self._write_config(self._fixture(), mutate=_workspace_drift))
        run_dir = self.work_parent / "run_drift_workspace"
        with patch.object(study_mod, "compute_twenty_session_outcomes", _forbidden), patch.object(
            study_mod, "run_replay_adapter", _forbidden
        ):
            with self.assertRaises(InputValidationError) as ctx:
                run_study(config, run_dir, allowed_parent=config.allowed_output_parent)
        self.assertEqual(ctx.exception.field, "workspace_root")
        self.assertFalse(run_dir.exists())
        self.assertFalse((run_dir / FAILURE_RECORD_NAME).exists())

    def test_type_equal_admission_substitutions_stop_before_scientific_work(self) -> None:
        """
        One mature gap gives real counts of 1 and 0 to substitute. Bytes are bound by the config, so
        file identity passes, and value-equal cases compare equal to the genuine record.
        """

        def _forbidden(*args: Any, **kwargs: Any) -> None:
            raise AssertionError("scientific work ran on a malformed admission record")

        value_equal: Dict[str, Callable[[Dict[str, Any]], None]] = {
            "union_count_true": lambda r: r.update(union_gap_count=True),
            "union_count_float": lambda r: r.update(union_gap_count=1.0),
            "missing_count_true": lambda r: r.update(missing_vix_gap_count=True),
            "warmup_count_false": lambda r: r.update(warmup_gap_count=False),
            "union_position_float": lambda r: r.update(union_gap_positions=[263.0]),
            "missing_position_float": lambda r: r.update(missing_vix_gap_positions=[263.0]),
            "start_float": lambda r: r.update(mature_test_start_index=260.0),
            "end_float": lambda r: r.update(mature_test_end_index=270.0),
            "span_float": lambda r: r.update(mature_test_span_count=10.0),
            "nested_axis_float": lambda r: r["axis"].update(session_count=290.0),
            "nested_calendar_float": lambda r: r["inputs"]["calendar"].update(session_count=290.0),
            "nested_record_float": lambda r: r["inputs"]["vix"].update(record_count=float(r["inputs"]["vix"]["record_count"])),
            "nested_bytes_float": lambda r: r["inputs"]["nifty"].update(raw_byte_count=float(r["inputs"]["nifty"]["raw_byte_count"])),
        }
        structural: Dict[str, Callable[[Dict[str, Any]], None]] = {
            "unknown_key": lambda r: r.update(extra=1),
            "unknown_nested_key": lambda r: r["axis"].update(extra=1),
            "missing_key": lambda r: r.pop("policy"),
        }

        for name, mutate, equal in [(n, m, True) for n, m in value_equal.items()] + [(n, m, False) for n, m in structural.items()]:

            def _apply(record: Dict[str, Any]) -> None:
                genuine = copy.deepcopy(record)
                mutate(record)
                if equal:
                    self.assertEqual(record, genuine)

            with self.subTest(case=name):
                config_path = self._write_config(self._fixture(missing_vix=(263,)), admission_mutate=_apply)
                run_dir = self.work_parent / f"run_typed_{name}"
                config = load_study_configuration_file(config_path)
                with patch.object(study_mod, "compute_twenty_session_outcomes", _forbidden), patch.object(
                    study_mod, "compute_nifty_features", _forbidden
                ), patch.object(study_mod, "build_split_plan", _forbidden), patch.object(
                    study_mod, "run_replay_adapter", _forbidden
                ), patch.object(study_mod, "_execute_serial_comparators", _forbidden):
                    with self.assertRaises(InputValidationError) as ctx:
                        run_study(config, run_dir, allowed_parent=config.allowed_output_parent)
                self.assertIn("Frozen admission record is malformed", str(ctx.exception))
                failure = self._failure(run_dir)
                self.assertEqual(failure["stage"], "verify_admission")
                self.assertEqual(failure["error_type"], "InputValidationError")
                for artifact in ("admission.json", "replay-request.json", "result.json", "panel-summary.json"):
                    self.assertFalse((run_dir / artifact).exists(), artifact)

    def _fixture_with_input_warnings(self) -> SimpleNamespace:
        """
        Nifty data rows 3, 7 and 9 hold two equal malformed cells and one empty cell; VIX row 5 holds
        one more. Closes stay valid, so the foundation's advisory policy admits every row.
        """
        fixture = self._fixture()
        _add_open_column(fixture.nifty, {3: "bad-open", 7: "bad-open", 9: ""})
        _add_open_column(fixture.vix, {5: "other-bad"})
        return fixture

    @staticmethod
    def _expected_nifty_warnings(fixture: SimpleNamespace) -> List[Dict[str, Any]]:
        # A data row at position p is physical line p + 2, below the one header line
        path = str(fixture.nifty)
        malformed = "Malformed Open value 'bad-open'; expected plain decimal syntax"
        return [
            {"file_path": path, "line": "line 5", "field": "Open", "message": malformed, "raw_value": "bad-open"},
            {"file_path": path, "line": "line 9", "field": "Open", "message": malformed, "raw_value": "bad-open"},
            {"file_path": path, "line": "line 11", "field": "Open", "message": "Missing or empty Open value in OHLC record", "raw_value": ""},
        ]

    @staticmethod
    def _expected_vix_warnings(fixture: SimpleNamespace) -> List[Dict[str, Any]]:
        message = "Malformed Open value 'other-bad'; expected plain decimal syntax"
        return [{"file_path": str(fixture.vix), "line": "line 7", "field": "Open", "message": message, "raw_value": "other-bad"}]

    def test_returned_input_warnings_persist_privately_on_success(self) -> None:
        fixture = self._fixture_with_input_warnings()
        run_dir = self._run(self._write_config(fixture), "run_input_warnings")

        ok, msg = verify_completed_run(run_dir)
        self.assertTrue(ok, msg)
        result = self._json(run_dir / "result.json")
        validate_result_document(result)
        self.assertEqual(result["input_warnings"], self._expected_nifty_warnings(fixture) + self._expected_vix_warnings(fixture))

        for name in ("panel-summary.json", "report.md", "predictions.json", "run-manifest.json"):
            text = (run_dir / name).read_text(encoding="utf-8")
            with self.subTest(artifact=name):
                self.assertNotIn("bad-open", text)
                self.assertNotIn("other-bad", text)

    def test_earlier_input_warnings_survive_a_later_loader_failure(self) -> None:
        """The VIX file also holds a bad cell, but a loader that raised returned nothing to retain."""
        fixture = self._fixture_with_input_warnings()
        config_path = self._write_config(fixture)
        config = load_study_configuration_file(config_path)
        run_dir = self.work_parent / "run_vix_loader_failure"
        real_load = study_mod.load_series

        def _failing_vix(series_id: str, spec: Any) -> LoadedSeries:
            if series_id == "india_vix":
                raise InputValidationError("vix loader failed", field="vix", reason="injected")
            return real_load(series_id, spec)

        with patch.object(study_mod, "load_series", _failing_vix):
            with self.assertRaises(InputValidationError) as ctx:
                run_study(config, run_dir, allowed_parent=config.allowed_output_parent)

        self.assertIn("vix loader failed", str(ctx.exception))
        failure = self._failure(run_dir)
        self.assertEqual(failure["stage"], "load_inputs")
        self.assertEqual(failure["input_warnings"], self._expected_nifty_warnings(fixture))

    def test_input_warnings_survive_each_downstream_failure(self) -> None:
        def _forged_cutoff(record: Dict[str, Any]) -> None:
            record["test_start"] = record["axis"]["last_date"]

        def _renderer(*args: Any, **kwargs: Any) -> str:
            raise RuntimeError("renderer failed")

        def _aligner(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("alignment failed")

        def _scorer(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("scorer failed")

        cases = [
            ("alignment", "load_inputs", patch.object(study_mod, "align_pair", _aligner), None),
            ("admission", "verify_admission", None, _forged_cutoff),
            ("scoring", "scoring", patch.object(study_mod, "score_comparison", _scorer), None),
            ("render", "render_report", patch.object(study_mod, "render_report_markdown", _renderer), None),
        ]
        for name, stage, injected, admission_mutate in cases:
            with self.subTest(case=name):
                fixture = self._fixture_with_input_warnings()
                config = load_study_configuration_file(self._write_config(fixture, admission_mutate=admission_mutate))
                run_dir = self.work_parent / f"run_warnings_{name}"
                with injected if injected is not None else contextlib.nullcontext():
                    with self.assertRaises(Exception):
                        run_study(config, run_dir, allowed_parent=config.allowed_output_parent)
                failure = self._failure(run_dir)
                self.assertEqual(failure["stage"], stage)
                self.assertEqual(
                    failure["input_warnings"],
                    self._expected_nifty_warnings(fixture) + self._expected_vix_warnings(fixture),
                )

    def test_diagnostic_storage_failure_keeps_the_primary_error_with_input_warnings(self) -> None:
        fixture = self._fixture_with_input_warnings()
        config = load_study_configuration_file(self._write_config(fixture))
        run_dir = self.work_parent / "run_warning_storage"
        real_write = study_mod._write_exclusive

        def _no_failure_record(path: Path, data: bytes) -> None:
            if path.name == FAILURE_RECORD_NAME:
                raise OSError("disk full at diagnostics")
            real_write(path, data)

        with patch.object(study_mod, "_write_exclusive", _no_failure_record), patch.object(
            study_mod, "render_report_markdown", side_effect=RuntimeError("renderer failed")
        ):
            with self.assertRaises(RuntimeError) as ctx:
                run_study(config, run_dir, allowed_parent=config.allowed_output_parent)

        self.assertEqual(str(ctx.exception), "renderer failed")
        self.assertIn("disk full at diagnostics", ctx.exception.failure_record_error)  # type: ignore[attr-defined]
        self.assertFalse((run_dir / FAILURE_RECORD_NAME).exists())
        self.assertFalse((run_dir / "run-manifest.json").exists())

    def test_input_drift_after_binding_blocks_completion(self) -> None:
        """Each generated file changed after the configuration froze it stops the run early."""

        def _forbidden(*args: Any, **kwargs: Any) -> None:
            raise AssertionError("scientific work ran on drifted inputs")

        def _append(path: Path) -> None:
            path.write_bytes(path.read_bytes() + b"\n")

        for name, pick, stage in (
            ("nifty", lambda f: f.nifty, "load_inputs"),
            ("vix", lambda f: f.vix, "load_inputs"),
            ("calendar", lambda f: f.calendar, "load_inputs"),
            ("admission", lambda f: f.nifty.parent / "admission.json", "verify_admission"),
        ):
            with self.subTest(case=name):
                fixture = self._fixture()
                config_path = self._write_config(fixture)
                config = load_study_configuration_file(config_path)
                target = pick(fixture)
                _append(target)
                run_dir = self.work_parent / f"run_input_drift_{name}"
                with patch.object(study_mod, "compute_twenty_session_outcomes", _forbidden):
                    with self.assertRaises(Exception):
                        run_study(config, run_dir, allowed_parent=config.allowed_output_parent)
                self.assertEqual(self._failure(run_dir)["stage"], stage)

        # A configuration changed after load is the same drift one level up
        fixture = self._fixture()
        config_path = self._write_config(fixture)
        config = load_study_configuration_file(config_path)
        _append(config_path)
        run_dir = self.work_parent / "run_config_drift"
        with self.assertRaises(InputValidationError):
            run_study(config, run_dir, allowed_parent=config.allowed_output_parent)
        self.assertEqual(self._failure(run_dir)["stage"], "verify_prerequisites")

    def test_plan_mismatch_blocks_replay_and_comparators(self) -> None:
        """The frozen gap list is compared with the plan before either predictor path starts."""
        config_path = self._write_config(self._fixture())
        run_dir = self.work_parent / "run_plan_mismatch"
        config = load_study_configuration_file(config_path)
        real_plan = study_mod.build_split_plan

        def _plan_with_extra_gap(*args: Any, **kwargs: Any) -> SplitPlan:
            plan = real_plan(*args, **kwargs)
            return SplitPlan(**{**plan.__dict__, "test_indices": plan.test_indices[1:]})

        with patch.object(study_mod, "build_split_plan", _plan_with_extra_gap), patch.object(
            study_mod, "run_replay_adapter"
        ) as replay, patch.object(study_mod, "_execute_serial_comparators") as comparators:
            with self.assertRaises(InputValidationError) as ctx:
                run_study(config, run_dir, allowed_parent=config.allowed_output_parent)

        self.assertEqual(ctx.exception.field, "admission_inventory")
        replay.assert_not_called()
        comparators.assert_not_called()
        self.assertEqual(self._failure(run_dir)["stage"], "verify_plan_admission")
        for name in ("replay-request.json", "predictions.json", "result.json", "panel-summary.json"):
            self.assertFalse((run_dir / name).exists(), name)

    def test_future_warning_failure_retains_warnings_and_stage(self) -> None:
        config_path = self._write_config(self._fixture())
        run_dir = self.work_parent / "run_future_warning"
        config = load_study_configuration_file(config_path)
        real_freq = study_mod.build_frequency_predictions

        def _warn_freq(*args: Any, **kwargs: Any) -> Any:
            warnings.warn("Pre-failure ordinary warning", UserWarning, stacklevel=1)
            return real_freq(*args, **kwargs)

        def _future_log(*args: Any, **kwargs: Any) -> None:
            warnings.warn("Imminent breaking change", FutureWarning, stacklevel=1)

        with patch.object(study_mod, "build_frequency_predictions", _warn_freq):
            with patch("research.prediction_eval.logistic.build_logistic_predictions", _future_log):
                with self.assertRaises(FutureWarning):
                    run_study(config, run_dir, allowed_parent=config.allowed_output_parent)

        failure = self._failure(run_dir)
        self.assertEqual(failure["stage"], "comparators")
        self.assertEqual(failure["error_type"], "FutureWarning")
        self.assertIn("Imminent breaking change", failure["error_message"])
        self.assertIn("Pre-failure ordinary warning", [w["message"] for w in failure["captured_warnings"]])
        self.assertIn("replay-response.json", [a["path"] for a in failure["partial_artifacts"]])

    def test_ordinary_warnings_persist_on_success(self) -> None:
        config_path = self._write_config(self._fixture())
        real_freq = study_mod.build_frequency_predictions

        def _warn_freq(*args: Any, **kwargs: Any) -> Any:
            warnings.warn("Persisted ordinary warning", DeprecationWarning, stacklevel=1)
            return real_freq(*args, **kwargs)

        with patch.object(study_mod, "build_frequency_predictions", _warn_freq):
            run_dir = self._run(config_path, "run_warnings")

        result = self._json(run_dir / "result.json")
        self.assertIn("Persisted ordinary warning", [w["message"] for w in result["warnings"]])
        # Process diagnostics stay out of the portable aggregate
        self.assertNotIn("Persisted ordinary warning", (run_dir / "panel-summary.json").read_text(encoding="utf-8"))

    def test_failure_after_summary_leaves_no_completion_manifest(self) -> None:
        config_path = self._write_config(self._fixture())
        run_dir = self.work_parent / "run_post_summary"
        config = load_study_configuration_file(config_path)

        with patch.object(study_mod, "render_report_markdown", side_effect=RuntimeError("renderer failed")):
            with self.assertRaises(RuntimeError):
                run_study(config, run_dir, allowed_parent=config.allowed_output_parent)

        self.assertTrue((run_dir / "panel-summary.json").exists())
        failure = self._failure(run_dir)
        self.assertEqual(failure["stage"], "render_report")
        self.assertIn("panel-summary.json", [a["path"] for a in failure["partial_artifacts"]])

    def test_manifest_writer_failure_leaves_no_completion_manifest(self) -> None:
        """
        The completion file is created, half written, then the disk fails: the run removes the
        partial file it created and records the failure. A pre-existing completion file is a
        collision: its bytes stay exactly as they were.
        """
        real_open = open
        written: List[bytes] = []

        class _FailingAfterCreation:
            def __init__(self, path: Any, mode: str) -> None:
                self._handle = real_open(path, mode)

            def write(self, payload: bytes) -> int:
                self._handle.write(payload[: len(payload) // 2])
                self._handle.flush()
                written.append(payload)
                raise OSError("disk full at finalization")

            def close(self) -> None:
                self._handle.close()

        def _open(path: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
            if Path(path).name == "run-manifest.json":
                return _FailingAfterCreation(path, mode)
            return real_open(path, mode, *args, **kwargs)

        config = load_study_configuration_file(self._write_config(self._fixture()))
        run_dir = self.work_parent / "run_manifest_fail"
        with patch.object(study_mod, "open", _open, create=True):
            with self.assertRaises(OSError) as ctx:
                run_study(config, run_dir, allowed_parent=config.allowed_output_parent)
        self.assertEqual(str(ctx.exception), "disk full at finalization")
        self.assertEqual(len(written), 1)
        failure = self._failure(run_dir)
        self.assertEqual(failure["stage"], "finalize_manifest")
        self.assertEqual(failure["error_message"], "disk full at finalization")
        self.assertNotIn("run-manifest.json", [a["path"] for a in failure["partial_artifacts"]])

        # Collision control: another writer's file is never opened for writing or removed
        real_build = study_mod.build_run_manifest
        prior = b"pre-existing completion bytes from another writer\n"

        def _occupied(**kwargs: Any) -> Dict[str, Any]:
            doc = real_build(**kwargs)
            (self.work_parent / "run_manifest_collision" / "run-manifest.json").write_bytes(prior)
            return doc

        config = load_study_configuration_file(self._write_config(self._fixture()))
        collision_dir = self.work_parent / "run_manifest_collision"
        with patch.object(study_mod, "build_run_manifest", _occupied):
            with self.assertRaises(FileExistsError):
                run_study(config, collision_dir, allowed_parent=config.allowed_output_parent)
        self.assertEqual((collision_dir / "run-manifest.json").read_bytes(), prior)
        collision = json.loads((collision_dir / FAILURE_RECORD_NAME).read_text(encoding="utf-8"))
        self.assertEqual(collision["stage"], "finalize_manifest")
        ok, _ = verify_completed_run(collision_dir)
        self.assertFalse(ok)

    def test_tampered_artifact_fails_completed_run_check(self) -> None:
        run_dir = self._run(self._write_config(self._fixture()), "run_tampered")
        ok, msg = verify_completed_run(run_dir)
        self.assertTrue(ok, msg)

        report = run_dir / "report.md"
        report.write_bytes(report.read_bytes() + b" ")
        ok, msg = verify_completed_run(run_dir)
        self.assertFalse(ok)
        self.assertIn("report.md", msg)

    def test_replay_adapter_distinct_receipts_retention(self) -> None:
        """
        Verifies B2: Each actual S1 Node replay attempt retains exclusive, unique receipts and raw
        stream files in its owned root without overwriting earlier attempts, and an inherited
        NIVESH_EVAL_CHILD_LOG_DIR value gains no write authority over a real child run.
        """
        nifty_path, vix_path, cal_path = self._generate_synthetic_csv_data(290)
        nifty_loaded = load_series("nifty50_price_index", str(nifty_path))
        vix_loaded = load_series("india_vix", str(vix_path))
        with open(cal_path, "r", encoding="utf-8") as f:
            expected_sessions = [datetime.date.fromisoformat(d) for d in json.load(f)["sessions"]]
        aligned = align_pair(nifty_loaded, vix_loaded, expected_sessions=expected_sessions)
        features = compute_nifty_features(aligned)

        outside_dir = self.work_parent / "outside_children"
        work_dir = self.work_parent / "replay_call"
        trusted_model, trusted_build = self._trusted_replay()

        with patch.dict(os.environ, {CHILD_ENV: str(outside_dir)}):
            # First attempt
            h1, prov1 = run_replay_adapter(
                features,
                node_executable=self.node_exe,
                replay_script=self.replay_script,
                workspace_root=str(WORKSPACE_ROOT),
                work_dir=work_dir,
                timeout_seconds=60,
                trusted_model=trusted_model,
                trusted_build_manifest=trusted_build,
            )
            self.assertGreater(len(h1), 0)

            # Second attempt in the same owned root
            h2, prov2 = run_replay_adapter(
                features,
                node_executable=self.node_exe,
                replay_script=self.replay_script,
                workspace_root=str(WORKSPACE_ROOT),
                work_dir=work_dir,
                timeout_seconds=60,
                trusted_model=trusted_model,
                trusted_build_manifest=trusted_build,
            )
            self.assertGreater(len(h2), 0)

        self.assertFalse(outside_dir.exists())

        # Verify the owned root contains distinct per-attempt receipts
        rec1_path = work_dir / "replay-invocation.json"
        rec2_path = work_dir / "replay-invocation-002.json"
        self.assertTrue(rec1_path.exists())
        self.assertTrue(rec2_path.exists())

        self.assertTrue((work_dir / "replay-response.json").exists())
        self.assertTrue((work_dir / "replay-response-002.json").exists())
        self.assertTrue((work_dir / "replay-stderr.log").exists())
        self.assertTrue((work_dir / "replay-stderr-002.log").exists())
        self.assertTrue((work_dir / "replay-request.json").exists())
        self.assertTrue((work_dir / "replay-request-002.json").exists())

        # Read both receipts and verify metadata
        doc1 = json.loads(rec1_path.read_text(encoding="utf-8"))
        doc2 = json.loads(rec2_path.read_text(encoding="utf-8"))

        self.assertEqual(doc1["attempt"], 1)
        self.assertEqual(doc2["attempt"], 2)
        self.assertEqual(doc1["immediate_child_exit"], 0)
        self.assertEqual(doc2["immediate_child_exit"], 0)
        self.assertEqual(doc1["launch_state"], "started")
        self.assertEqual(doc2["launch_state"], "started")
        self.assertEqual(doc1["capture_state"], "complete")
        self.assertEqual(doc2["capture_state"], "complete")
        self.assertFalse(doc1["timed_out"])
        self.assertFalse(doc2["timed_out"])
        self.assertGreater(doc1["duration_seconds"], 0)
        self.assertGreater(doc2["duration_seconds"], 0)

        # Each receipt names its own request, and the child read that exact attempt's file
        self.assertEqual(doc1["request"]["path"], str(work_dir.resolve() / "replay-request.json"))
        self.assertEqual(doc2["request"]["path"], str(work_dir.resolve() / "replay-request-002.json"))
        self.assertEqual(doc1["argv"][-1], doc1["request"]["path"])
        self.assertEqual(doc2["argv"][-1], doc2["request"]["path"])

    def test_real_run_through_main_writes_replay_evidence_only_in_its_run_root(self) -> None:
        config_path = self._write_config(self._fixture())
        run_dir = self.work_parent / "run_owned_evidence"
        outside_dir = self.work_parent / "outside_run_children"
        coverage_dir = self.work_parent / "outside_node_coverage"
        # Inherited, either sentinel changes the real child: an unresolvable preload stops Node,
        # and a coverage directory receives files at exit. Neither may reach the child.
        sentinels = {
            CHILD_ENV: str(outside_dir),
            "NODE_OPTIONS": "--require=nivesh-absent-sentinel-preload",
            "NODE_V8_COVERAGE": str(coverage_dir),
        }

        with patch.dict(os.environ, sentinels):
            expected_names = ("SYSTEMROOT", "TEMP", "TMP") if os.name == "nt" else ("TMPDIR",)
            expected_env = {name: os.environ[name] for name in expected_names if name in os.environ}
            self.assertEqual(main(["--config", str(config_path), "--output-dir", str(run_dir)]), 0)

        self.assertFalse(outside_dir.exists())
        self.assertFalse(coverage_dir.exists())
        ok, msg = verify_completed_run(run_dir)
        self.assertTrue(ok, msg)
        receipt = self._json(run_dir / "replay-invocation.json")
        self.assertEqual(receipt["attempt"], 1)
        self.assertEqual(receipt["stdout"]["path"], str(run_dir / "replay-response.json"))
        self.assertEqual(receipt["declared_environment"], expected_env)
        if os.name == "nt":
            self.assertIn("SYSTEMROOT", receipt["declared_environment"])

        # After completion, a rehashed manifest cannot hide a contradicted replay or predictions join
        originals = {name: (run_dir / name).read_bytes() for name in ("replay-stderr.log", "predictions.json", "run-manifest.json")}
        for name, data, expected in (
            ("replay-stderr.log", originals["replay-stderr.log"] + b"late\n", "replay-invocation.stderr"),
            ("predictions.json", originals["predictions.json"].replace(b'"origin_close": "', b'"origin_close": "9', 1), "predictions.json"),
        ):
            with self.subTest(completed_run_join=name):
                self.assertNotEqual(data, originals[name])
                self._rewrite_rehashed(run_dir, name, data)
                ok, msg = verify_completed_run(run_dir)
                self.assertFalse(ok)
                self.assertIn(expected, msg)
                for restore in (name, "run-manifest.json"):
                    (run_dir / restore).write_bytes(originals[restore])
        ok, msg = verify_completed_run(run_dir)
        self.assertTrue(ok, msg)

    def test_replay_adapter_evidence_write_failure_blocks_completion(self) -> None:
        """
        Verifies B2: Any failure to write replay evidence prevents successful completion,
        writes failure-diagnostics.json, and leaves no run-manifest.json.
        """
        config_path = self._write_config(self._fixture())
        run_output_dir = self.work_parent / "run_evidence_failure_injected"
        config = load_study_configuration_file(config_path)

        orig_write = study_mod._write_exclusive

        def _faulty_write(path: Path, data: bytes) -> None:
            if "replay-response" in path.name:
                raise IOError("Injected disk I/O failure during replay evidence persistence")
            orig_write(path, data)

        with patch.object(study_mod, "_write_exclusive", _faulty_write):
            with self.assertRaises(RuntimeError) as ctx:
                run_study(config, run_output_dir, allowed_parent=config.allowed_output_parent)

            self.assertIn("Failed to record replay evidence", str(ctx.exception))

        # Crucial B2 requirement: incomplete capture/evidence must NOT produce run-manifest.json
        self.assertFalse((run_output_dir / "run-manifest.json").exists())
        self.assertTrue((run_output_dir / FAILURE_RECORD_NAME).exists())

        # Inspect failure diagnostics content
        diag_doc = json.loads((run_output_dir / FAILURE_RECORD_NAME).read_text(encoding="utf-8"))
        self.assertEqual(diag_doc["error_type"], "RuntimeError")
        self.assertIn("Failed to record replay evidence", diag_doc["error_message"])
        self.assertEqual(diag_doc["stage"], "replay")

    def _write_historical_fixture(
        self,
        name: str,
        *,
        total_sessions: int = 2250,
        gap_idx: int = 1435,
        config_mutate: Optional[Callable[[Dict[str, Any], List[datetime.date]], None]] = None,
        approval_mutate: Optional[Callable[[Dict[str, Any]], None]] = None,
        admission_bytes: Optional[bytes] = None,
    ) -> SimpleNamespace:
        """
        Writes synthetic two-part Nifty and VIX originals, A, C and then H naming the final C bytes.

        VIX is missing at gap_idx inside the mature span, so uncertainty stays unavailable and no
        bootstrap position is sampled. Mutations apply to C or H before H binds them, so each
        refusal reaches its own guard instead of a stale identity.
        """
        in_dir = self.work_parent / name
        in_dir.mkdir(parents=True)
        dates = _session_dates(total_sessions)
        cal_path = in_dir / "calendar.json"
        cal_path.write_text(json.dumps({"sessions": [d.isoformat() for d in dates]}), encoding="utf-8")

        def _vix(i: int) -> str:
            return f"{15.0 + math.cos(i / 5.0) * 2.0:.2f}"

        parts = {
            "nifty": [(in_dir / "nifty_part1.csv", range(0, 1200)), (in_dir / "nifty_part2.csv", range(1200, total_sessions))],
            "vix": [(in_dir / "vix_part1.csv", range(0, 1200)), (in_dir / "vix_part2.csv", range(1200, total_sessions))],
        }
        for role, files in parts.items():
            for path, rows in files:
                lines = ["Date,Close"] + [
                    f"{dates[i].strftime('%d-%b-%Y')},{_wave_close(i) if role == 'nifty' else _vix(i)}"
                    for i in rows
                    if role == "nifty" or i != gap_idx
                ]
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        def _note(role: str, idx: int) -> str:
            return f"synthetic-private-note-{role}-part-{idx + 1}"

        def _url(role: str, idx: int) -> str:
            return f"https://synthetic.invalid/private/{role}-part-{idx + 1}.csv"

        if admission_bytes is None:
            record = prepare_historical_admission(
                nifty_specs=[FileInputSpec(file_path=str(p), source_url=_url("nifty", i), source_use_note=_note("nifty", i)) for i, (p, _) in enumerate(parts["nifty"])],
                vix_specs=[FileInputSpec(file_path=str(p), source_url=_url("vix", i), source_use_note=_note("vix", i)) for i, (p, _) in enumerate(parts["vix"])],
                calendar_path=cal_path,
            )
            admission_bytes = json.dumps(record, indent=2).encode("utf-8") + b"\n"
        adm_path = in_dir / "admission-input.json"
        adm_path.write_bytes(admission_bytes)

        def _bound_spec(path: Path, identity: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
            entry = dict(identity if identity is not None else _identity(path))
            entry["path"] = str(path.resolve())
            return entry

        def _file_binding(role: str, idx: int, path: Path) -> Dict[str, Any]:
            return dict(
                _bound_spec(path),
                source_url=_url(role, idx),
                requested_interval=None,
                acquisition_time=None,
                source_use_note=_note(role, idx),
            )

        config_doc: Dict[str, Any] = {
            "schema_version": STUDY_SCHEMA_VERSION_V3,
            "study_id": "historical-e2e-study",
            "protocol_id": STUDY_PROTOCOL_ID,
            "data_kind": DATA_KIND_HISTORICAL,
            "development_status": "retrospective_historical_evaluation",
            "date_selection_rule": DATE_SELECTION_RULE_HISTORICAL,
            "development_start": dates[total_sessions - 1220].isoformat(),
            "test_start": dates[total_sessions - 820].isoformat(),
            "workspace_root": str(WORKSPACE_ROOT),
            "allowed_output_parent": str(self.work_parent),
            "timeout_seconds": 60,
            "inputs": {
                "nifty": {"units": "index_points", "source_kind": "admitted_historical_market_data", "files": [_file_binding("nifty", i, p) for i, (p, _) in enumerate(parts["nifty"])]},
                "vix": {"units": "volatility_index_points", "source_kind": "admitted_historical_market_data", "files": [_file_binding("vix", i, p) for i, (p, _) in enumerate(parts["vix"])]},
                "calendar": _bound_spec(cal_path),
            },
            "admission": _bound_spec(adm_path),
            "tools": {
                "node_executable": _bound_spec(Path(self.node_exe), _frozen_identity(Path(self.node_exe))),
                "python_executable": _bound_spec(Path(sys.executable), _frozen_identity(Path(sys.executable))),
                "replay_script": _bound_spec(Path(self.replay_script)),
                "candidate_build_manifest": _bound_spec(self.build_manifest),
                "models": _bound_spec(self.models_path),
            },
            "source_modules": {rel: _identity(WORKSPACE_ROOT / rel) for rel in REQUIRED_SOURCE_MODULES},
            "runtime": {
                "python_version": platform.python_version(),
                "python_implementation": platform.python_implementation(),
                "dependency_versions": dict(self.dependency_versions),
            },
            "uncertainty": {"protocol_id": "nivesh-paired-stationary-brier-v1", "max_resample_positions": 24000000},
        }
        if config_mutate is not None:
            config_mutate(config_doc, dates)
        config_path = in_dir / "config.json"
        config_bytes = json.dumps(config_doc, indent=2).encode("utf-8") + b"\n"
        config_path.write_bytes(config_bytes)

        evidence = {
            name: in_dir / f"{name}-evidence.txt"
            for name in ("nifty-terms", "vix-terms", "calendar-source")
        }
        for name, path in evidence.items():
            path.write_text(f"synthetic {name} evidence placeholder\n", encoding="utf-8")
        approval_doc: Dict[str, Any] = {
            "schema_version": SCHEMA_VERSION_APPROVAL_V1,
            "decision_id": "synthetic-decision-e2e-001",
            "approved_by": "Synthetic Approver Placeholder",
            "approved_at": "2026-11-09T12:00:00+00:00",
            "decision": "APPROVED_FOR_ONE_PRIVATE_STUDY",
            "config_identity": _identity(config_path),
            "admission_identity": _identity(adm_path),
            "source_use_evidence": [
                {
                    "input_refs": [{"role": "nifty", "file_index": 0}, {"role": "nifty", "file_index": 1}],
                    "evidence": [_bound_spec(evidence["nifty-terms"])],
                    "note": "synthetic-private-source-use-note-nifty",
                },
                {
                    "input_refs": [{"role": "vix", "file_index": 0}, {"role": "vix", "file_index": 1}],
                    "evidence": [_bound_spec(evidence["vix-terms"])],
                    "note": "synthetic-private-source-use-note-vix",
                },
            ],
            "calendar_evidence": {
                "evidence": [_bound_spec(evidence["calendar-source"])],
                "independent_source_note": "synthetic-private-calendar-note",
            },
            "public_sharing_status": "NOT_CLEARED",
            "raw_file_hash_release": "WITHHELD",
        }
        if approval_mutate is not None:
            approval_mutate(approval_doc)
        approval_path = in_dir / "approval.json"
        approval_bytes = json.dumps(approval_doc, indent=2).encode("utf-8") + b"\n"
        approval_path.write_bytes(approval_bytes)
        return SimpleNamespace(
            in_dir=in_dir,
            dates=dates,
            parts=parts,
            calendar=cal_path,
            admission=adm_path,
            config_path=config_path,
            config_bytes=config_bytes,
            approval_path=approval_path,
            approval_bytes=approval_bytes,
            approval_doc=approval_doc,
            approval_bound=BoundFile(path=str(approval_path.resolve()), raw_byte_count=len(approval_bytes), sha256=_sha(approval_bytes)),
            private_texts=[_note(r, i) for r in parts for i in range(2)]
            + [_url(r, i) for r in parts for i in range(2)]
            + [
                approval_doc["decision_id"],
                approval_doc["approved_by"],
                "synthetic-private-source-use-note-nifty",
                "synthetic-private-calendar-note",
                str(in_dir).replace("\\", "\\\\"),
            ],
        )

    def test_historical_pipeline_full_e2e_through_main(self) -> None:
        """
        Positive historical run through main with the complete external approval triple: 13
        artifacts and zero sampled positions. Counts follow the rule independently at N=2250
        (D=1030, T=1430, E=2230) with the one VIX gap at 1435, and the serialized summary and
        descriptor carry none of the private notes, URLs, approver, decision, paths or raw hashes.
        """
        fx = self._write_historical_fixture("hist_e2e")
        run_dir = self.work_parent / "run_historical_e2e"
        exit_code = main(
            [
                "--config", str(fx.config_path),
                "--output-dir", str(run_dir),
                "--approval", str(fx.approval_path),
                "--approval-bytes", str(len(fx.approval_bytes)),
                "--approval-sha256", _sha(fx.approval_bytes),
            ]
        )
        self.assertEqual(exit_code, 0)
        ok, msg = verify_completed_run(run_dir)
        self.assertTrue(ok, msg)
        self.assertEqual((run_dir / "historical-admission.json").read_bytes(), fx.approval_bytes)
        self.assertEqual((run_dir / "config.json").read_bytes(), fx.config_bytes)

        manifest = self._json(run_dir / "run-manifest.json")
        self.assertEqual(manifest["schema_version"], SCHEMA_VERSION_RUN_MANIFEST_V3)
        self.assertEqual({a["path"] for a in manifest["artifacts"]}, REQUIRED_MANIFEST_ARTIFACTS_V3)
        self.assertEqual(self._json(run_dir / "uncertainty-diagnostics.json")["resource"]["visited_positions"], 0)

        n, d, t, e = 2250, 1030, 1430, 2230
        admission = self._json(run_dir / "admission.json")
        self.assertEqual(
            (admission["development_start_index"], admission["mature_test_start_index"], admission["mature_test_end_index"], admission["mature_test_span_count"]),
            (n - 1220, n - 820, n - 20, 800),
        )
        self.assertEqual((d, t, e), (n - 1220, n - 820, n - 20))
        self.assertEqual((admission["union_gap_positions"], admission["missing_vix_gap_positions"], admission["warmup_gap_positions"]), ([1435], [1435], []))
        self.assertEqual([len(admission["inputs"][role]["files"]) for role in ("nifty", "vix")], [2, 2])

        summary_bytes = (run_dir / "panel-summary.json").read_bytes()
        summary = json.loads(summary_bytes.decode("utf-8"))
        result = self._json(run_dir / "result.json")
        self.assertEqual(summary["chronological_cutoffs"], {"development_start": fx.dates[d].isoformat(), "test_start": fx.dates[t].isoformat()})
        dev, test = summary["partitions"]["development"], summary["partitions"]["test"]
        self.assertEqual((dev["cutoff_index"], test["cutoff_index"]), (d, t))
        # Development keeps D..T-21; test keeps T..E-1 except the gap; train i+20<D; refit i+20<T
        self.assertEqual((dev["counts"]["raw_partition_count"], dev["counts"]["eligible_count"]), (t - d, (t - 20) - d))
        self.assertEqual((test["counts"]["raw_partition_count"], test["counts"]["eligible_count"]), (n - t, (e - t) - 1))
        self.assertEqual(test["counts"]["exclusion_reason_counts"], {"missing_vix": 1, "unknown_outcome": 20})
        self.assertEqual(len(result["partitions"]["development"]["frequency_block"]["fitting_indices"]), (d - 20) - 200)
        self.assertEqual(len(result["partitions"]["test"]["frequency_block"]["fitting_indices"]), (t - 20) - 200)
        self.assertEqual((summary["uncertainty"]["reason"], summary["uncertainty"]["n"], summary["uncertainty"]["mature_span_count"]), ("non_contiguous_test_cohort", 799, 800))

        self.assertEqual(summary["schema_version"], SCHEMA_VERSION_SUMMARY_V3)
        self.assertEqual(set(summary["provenance_identity"]), {"config_sha256", "admission_sha256", "approval_sha256"})
        self.assertEqual(summary["provenance_identity"]["approval_sha256"], _sha(fx.approval_bytes))
        self.assertEqual(summary["limitations"], list(HISTORICAL_LIMITATIONS))
        self.assertTrue(any("not an untouched holdout" in item for item in summary["limitations"]))
        self.assertTrue(any("No forecast accuracy guarantee" in item for item in summary["limitations"]))

        # Serialized public candidates: summary bytes and the private descriptor document
        descriptor_bytes = serialize_strict_json(release_descriptor_document(build_candidate_descriptor(summary_bytes, (run_dir / "run-manifest.json").read_bytes())))
        raw_digests = [_identity(path)["sha256"] for files in fx.parts.values() for path, _ in files] + [_identity(fx.calendar)["sha256"]]
        result_text = (run_dir / "result.json").read_text(encoding="utf-8")
        for text_name, text in (("panel-summary.json", summary_bytes.decode("utf-8")), ("descriptor", descriptor_bytes.decode("utf-8"))):
            for forbidden in fx.private_texts + raw_digests:
                with self.subTest(artifact=text_name, forbidden=forbidden[:40]):
                    self.assertNotIn(forbidden, text)
        # The same private facts stay bound in the private result
        for kept in (fx.private_texts[0], fx.private_texts[4], raw_digests[1]):
            self.assertIn(kept, result_text)

    def test_historical_refusals_stop_before_science_at_named_stages(self) -> None:
        """
        Each case changes one fact under otherwise valid bindings; H names the final C bytes, so
        the intended guard fires. No outcome, feature or replay owner is reached.
        """

        def _forbidden(*args: Any, **kwargs: Any) -> None:
            raise AssertionError("historical scientific work ran after a failed pre-science check")

        def _second_file(key: str, value: Any) -> Callable[[Dict[str, Any], List[datetime.date]], None]:
            def _apply(doc: Dict[str, Any], dates: List[datetime.date]) -> None:
                entry = doc["inputs"]["nifty"]["files"][1]
                entry[key] = value(entry[key]) if callable(value) else value
            return _apply

        def _reorder(doc: Dict[str, Any], dates: List[datetime.date]) -> None:
            doc["inputs"]["nifty"]["files"].reverse()

        def _shift(key: str, index: int) -> Callable[[Dict[str, Any], List[datetime.date]], None]:
            return lambda doc, dates: doc.update({key: dates[index].isoformat()})

        def _drop_ref(doc: Dict[str, Any]) -> None:
            doc["source_use_evidence"][0]["input_refs"].pop()

        def _approval(key: str, value: Any) -> Callable[[Dict[str, Any]], None]:
            return lambda doc: doc.update({key: value})

        cases = [
            ("second_file_sha", {"config_mutate": _second_file("sha256", "0" * 64)}, "load_inputs", "inputs.nifty.files[1]"),
            ("second_file_bytes", {"config_mutate": _second_file("raw_byte_count", lambda v: v + 1)}, "load_inputs", "inputs.nifty.files[1]"),
            ("files_reordered_against_A", {"config_mutate": _reorder}, "verify_admission", "admission"),
            ("test_start_plus_one", {"config_mutate": _shift("test_start", 1431)}, "load_inputs", "test_start"),
            ("development_start_plus_one", {"config_mutate": _shift("development_start", 1031)}, "load_inputs", "development_start"),
            ("sessions_2219", {"total_sessions": 2219, "admission_bytes": b"{}\n"}, "load_inputs", "date_selection_rule"),
            ("wrong_admission_in_H", {"approval_mutate": _approval("admission_identity", {"raw_byte_count": 1, "sha256": "0" * 64})}, "verify_human_approval", "approval.admission_identity"),
            ("H_misses_second_file", {"approval_mutate": _drop_ref}, "verify_human_approval", "approval.source_use_evidence"),
            ("H_not_an_approval", {"approval_mutate": _approval("decision", "REJECTED")}, "verify_human_approval", None),
        ]
        for name, kwargs, stage, field in cases:
            with self.subTest(case=name):
                fx = self._write_historical_fixture(f"hist_refuse_{name}", **kwargs)
                self._assert_historical_refusal(load_study_configuration_file(fx.config_path), fx.approval_bound, f"run_refuse_{name}", stage, field)

        # The external pin itself: the right file under a different expected identity
        fx = self._write_historical_fixture("hist_refuse_pin")
        wrong_pin = BoundFile(path=fx.approval_bound.path, raw_byte_count=fx.approval_bound.raw_byte_count, sha256="0" * 64)
        self._assert_historical_refusal(load_study_configuration_file(fx.config_path), wrong_pin, "run_refuse_pin", "verify_human_approval", "approval")

        # Value-equal reformatted C: H approved the original bytes, not equivalent values
        fx = self._write_historical_fixture("hist_refuse_reformatted")
        fx.config_path.write_bytes(json.dumps(json.loads(fx.config_bytes.decode("utf-8")), indent=4).encode("utf-8") + b"\n")
        self.assertEqual(json.loads(fx.config_path.read_bytes()), json.loads(fx.config_bytes))
        self._assert_historical_refusal(load_study_configuration_file(fx.config_path), fx.approval_bound, "run_refuse_reformatted", "verify_human_approval", "approval.config_identity")

    def _assert_historical_refusal(self, config: Any, approval: BoundFile, run_name: str, stage: str, field: Optional[str]) -> None:
        run_dir = self.work_parent / run_name
        with patch.object(study_mod, "compute_twenty_session_outcomes", side_effect=AssertionError("outcomes reached")), patch.object(
            study_mod, "compute_nifty_features", side_effect=AssertionError("features reached")
        ), patch.object(study_mod, "run_replay_adapter", side_effect=AssertionError("replay reached")):
            with self.assertRaises(ValueError) as ctx:
                run_study(config, run_dir, allowed_parent=config.allowed_output_parent, approval=approval)
        self.assertNotIsInstance(ctx.exception, AssertionError)
        if field is not None:
            self.assertIsInstance(ctx.exception, InputValidationError)
            self.assertEqual(ctx.exception.field, field)
        failure = self._failure(run_dir)
        self.assertEqual(failure["stage"], stage)
        for artifact in ("result.json", "panel-summary.json", "replay-request.json", "uncertainty-input.json"):
            self.assertFalse((run_dir / artifact).exists(), artifact)


class TestS3Rehearsal(_StudyIntegrationBase):
    """
    Dedicated explicit selector class for S3 synthetic-v2 full-science rehearsal.
    Non-test_ method name excludes ordinary module discovery.
    """

    def rehearse_full_size_synthetic(self) -> None:
        """
        ONE synthetic-v2 full science run, N4748, E4728, T3928, D3528, n800, gapfree,
        all 3 methods/L views available, B10000, 24M actual positions.
        """
        # Phase 1: Reserve 24M sampling budget before run
        _reserve_sampling_budget("synthetic-rehearsal", 24000000, budget=24000000)

        # Generate full-size gap-free synthetic fixture (N = 4748)
        fixture = self._fixture(total_sessions=4748)
        d_idx = 3528
        t_idx = 3928
        # Test cohort span: E - T = (4748 - 20) - 3928 = 4728 - 3928 = 800 sessions

        # Synthetic arithmetic: 10,000 replicates x 800 TEST origins x 3 block lengths = 24,000,000 positions, below the 30M engine hard cap
        def _cap_24m(doc: Dict[str, Any]) -> None:
            doc["uncertainty"]["max_resample_positions"] = 24000000

        config_path = self._write_config(fixture, d_index=d_idx, t_index=t_idx, mutate=_cap_24m)
        run_dir = self.work_parent / "rehearsal_full"

        config = load_study_configuration_file(config_path)
        self.assertEqual(config.uncertainty["max_resample_positions"], 24000000)
        res = run_study(config, run_dir, allowed_parent=config.allowed_output_parent)
        self.assertIsNotNone(res)

        # Phase 2: Verify visited positions from diagnostics and complete call in ledger
        diag = self._json(run_dir / "uncertainty-diagnostics.json")
        visited = diag["resource"]["visited_positions"]
        self.assertEqual(diag["resource"], {"max_resample_positions": 24000000, "required_positions": 24000000, "visited_positions": 24000000})
        self.assertEqual(visited, 10000 * 800 * 3)

        # Each of the three block lengths (20, 40, 60) completed 10000 replicates of 800 positions
        self.assertEqual([item["block_length"] for item in diag["lengths"]], [20, 40, 60])
        for item in diag["lengths"]:
            self.assertEqual(item["replicates_completed"], 10000)
            self.assertEqual(item["sampled_positions"], 8000000)

        _complete_sampling_call("synthetic-rehearsal", visited, budget=24000000)

        # Gap-free n800 clears every floor, so all three views are available with bounds
        block = self._json(run_dir / "panel-summary.json")["uncertainty"]
        self.assertEqual((block["status"], block["reason"], block["n"], block["mature_span_count"], block["replicates"]), ("available", None, 800, 800, 10000))
        self.assertEqual([view["block_length"] for view in block["block_lengths"]], [20, 40, 60])
        for view in block["block_lengths"]:
            self.assertEqual((view["status"], view["reason"]), ("available", None))
            for pair in view["pairs"]:
                self.assertLessEqual(pair["lower"], pair["upper"])
        self.assertEqual(self._json(run_dir / "admission.json")["union_gap_positions"], [])

        # Verify completed run
        ok, msg = verify_completed_run(run_dir)
        self.assertTrue(ok, msg)

        # Report markdown exists and contains expected sections
        report = (run_dir / "report.md").read_text(encoding="utf-8")
        self.assertIn("# Prediction Evaluation Study Report:", report)
        self.assertIn("Mature Test Span:", report)
        self.assertIn("(800 sessions)", report)


if __name__ == "__main__":
    unittest.main()
