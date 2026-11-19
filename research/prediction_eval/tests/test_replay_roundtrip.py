"""
Cross-language integration tests for Python-to-Node replay execution.

Validates the actual process boundary between the Python FeatureSeries serializer
and the offline Node.js replay CLI (replay.cjs):
1. Loader-backed synthetic 207-origin Nifty/VIX pipeline:
   CSV generation -> load_series -> align_pair -> compute_nifty_features -> serialize_replay_input.
   Executes replay CLI, validates request hashing, model/build bindings, retrospective claim label,
   input semantic equality, null forecasts for warmup/missing-VIX origins, and valid ready forecasts.
2. Synthetic golden oracle parity:
   Reconstructs the frozen scenario-03-horizon-20d-shipped ready payload into a typed FeatureSeries,
   invokes replay CLI, and asserts deep forecast equality with sealed forecast-baseline.json.
3. Execution evidence:
   Captures raw stdout/stderr streams and typed invocation records under assigned child evidence root.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple
import unittest

from research.prediction_eval.inputs import (
    FileInputSpec,
    load_series,
    align_pair,
)
from research.prediction_eval.features import (
    compute_nifty_features,
    FeatureSeries,
    NiftyFeatureRecord,
    PredictorPayload,
    PROTOCOL_ID as FEATURES_PROTOCOL_ID,
    REASON_WARMUP,
    REASON_MISSING_VIX,
)
from research.prediction_eval.replay_export import (
    serialize_replay_input,
)

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent
REPLAY_CLI_PATH = WORKSPACE_ROOT / "research" / "prediction_eval" / "replay.cjs"
MODELS_PATH = WORKSPACE_ROOT / "public" / "data" / "market_intelligence" / "models.json"
CANDIDATE_MANIFEST_PATH = (
    WORKSPACE_ROOT / "build" / "prediction-eval" / "candidate" / "build-manifest.json"
)
REPLAY_CASES_PATH = (
    WORKSPACE_ROOT / "research" / "prediction_eval" / "tests" / "fixtures" / "replay-cases.json"
)
FORECAST_BASELINE_PATH = (
    WORKSPACE_ROOT / "research" / "prediction_eval" / "tests" / "fixtures" / "forecast-baseline.json"
)

EXPECTED_MODELS_SHA256 = "87C4DB2A4EB3B40AE5F7499C977AB407FFE3C3BE367E4DAE8FD8AE1804F543CD"
EXPECTED_CLAIM_LABEL = (
    "Retrospective replay of the frozen current heuristic; market data only; "
    "not historically issued forecasts"
)


def _compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


class TestReplayRoundtrip(unittest.TestCase):
    """Integration test suite executing actual Node.js replay CLI from Python."""

    _child_sequence: int = 0

    def setUp(self) -> None:
        # Resolve Node.js binary
        env_node = os.environ.get("NIVESH_EVAL_NODE")
        if env_node:
            node_path = Path(env_node)
            if not node_path.is_file():
                self.fail(f"NIVESH_EVAL_NODE points to non-existent executable: {env_node}")
            self.node_exe = str(node_path)
        else:
            found = shutil.which("node")
            if not found:
                self.fail("Node executable not found on PATH and NIVESH_EVAL_NODE is not set")
            self.node_exe = found

        # Resolve work directory
        env_work = os.environ.get("NIVESH_EVAL_WORK_DIR")
        if env_work:
            self.work_dir = Path(env_work)
            self.work_dir.mkdir(parents=True, exist_ok=True)
            self._temp_work_dir = None
        else:
            self._temp_work_dir = tempfile.TemporaryDirectory()
            self.work_dir = Path(self._temp_work_dir.name)

        # Resolve child log directory
        env_child = os.environ.get("NIVESH_EVAL_CHILD_LOG_DIR")
        if env_child:
            self.child_log_dir = Path(env_child)
            self.child_log_dir.mkdir(parents=True, exist_ok=True)
            self._temp_child_dir = None
        else:
            self._temp_child_dir = tempfile.TemporaryDirectory()
            self.child_log_dir = Path(self._temp_child_dir.name)

    def tearDown(self) -> None:
        if self._temp_work_dir is not None:
            self._temp_work_dir.cleanup()
        if self._temp_child_dir is not None:
            self._temp_child_dir.cleanup()

    def _execute_node_child(
        self,
        request_path: Path,
        label: str,
    ) -> Tuple[int, bytes, bytes, Dict[str, Any]]:
        """
        Executes replay.cjs with strict timeout and captures raw streams and typed record.
        """
        TestReplayRoundtrip._child_sequence += 1
        seq_num = TestReplayRoundtrip._child_sequence
        stem = f"node-child-{seq_num:03d}"

        stdout_log_path = self.child_log_dir / f"{stem}.stdout.log"
        stderr_log_path = self.child_log_dir / f"{stem}.stderr.log"
        record_json_path = self.child_log_dir / f"{stem}.json"

        req_bytes = request_path.read_bytes()
        req_sha256 = _compute_sha256(req_bytes)

        start_utc = datetime.datetime.now(datetime.timezone.utc)
        start_time = time.perf_counter()

        argv = [self.node_exe, str(REPLAY_CLI_PATH), str(request_path)]
        timed_out = False
        error_msg: Optional[str] = None
        stdout_bytes = b""
        stderr_bytes = b""
        exit_code = -1

        try:
            proc = subprocess.run(
                argv,
                cwd=str(WORKSPACE_ROOT),
                shell=False,
                capture_output=True,
                timeout=60,
            )
            exit_code = proc.returncode
            stdout_bytes = proc.stdout
            stderr_bytes = proc.stderr
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            error_msg = f"Child process timed out after 60 seconds: {exc}"
            stdout_bytes = exc.stdout or b""
            stderr_bytes = exc.stderr or b""
            exit_code = -1
        except Exception as exc:
            error_msg = f"Process execution failure: {exc}"
            exit_code = -1

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        end_utc = datetime.datetime.now(datetime.timezone.utc)

        # Write child execution logs using exclusive creation mode ('xb' / 'x')
        with stdout_log_path.open("xb") as f:
            f.write(stdout_bytes)
        with stderr_log_path.open("xb") as f:
            f.write(stderr_bytes)

        model_sha256 = (
            _compute_sha256(MODELS_PATH.read_bytes()) if MODELS_PATH.is_file() else None
        )
        manifest_sha256 = (
            _compute_sha256(CANDIDATE_MANIFEST_PATH.read_bytes())
            if CANDIDATE_MANIFEST_PATH.is_file()
            else None
        )

        record_data = {
            "sequence": seq_num,
            "label": label,
            "executable": self.node_exe,
            "argv": argv,
            "cwd": str(WORKSPACE_ROOT),
            "started_at_utc": start_utc.isoformat(),
            "completed_at_utc": end_utc.isoformat(),
            "duration_ms": duration_ms,
            "status": "PASS" if exit_code == 0 else "FAIL",
            "exit_code": exit_code,
            "signal": None,
            "timed_out": timed_out,
            "error": error_msg,
            "request_path": str(request_path),
            "request_bytes": len(req_bytes),
            "request_sha256": req_sha256,
            "stdout_bytes": len(stdout_bytes),
            "stdout_sha256": _compute_sha256(stdout_bytes),
            "stderr_bytes": len(stderr_bytes),
            "stderr_sha256": _compute_sha256(stderr_bytes),
            "bindings": {
                "replay_cjs": {
                    "path": str(REPLAY_CLI_PATH),
                    "sha256": _compute_sha256(REPLAY_CLI_PATH.read_bytes()),
                },
                "models_json": {
                    "path": str(MODELS_PATH),
                    "sha256": model_sha256,
                },
                "candidate_manifest": {
                    "path": str(CANDIDATE_MANIFEST_PATH),
                    "sha256": manifest_sha256,
                },
            },
        }

        with record_json_path.open("x", encoding="utf-8") as f:
            f.write(json.dumps(record_data, indent=2))
        return exit_code, stdout_bytes, stderr_bytes, record_data

    def test_loader_backed_roundtrip(self) -> None:
        """
        Executes end-to-end Python-to-Node roundtrip using a synthetic 207-origin dataset.

        Covers:
        - Nonuniform supplied dates (weekday sequence with gaps)
        - Nonflat price movement (fluctuating trend)
        - Missing VIX at origin 205 after warmup
        - Full loader provenance with optional declared metadata
        - Preservation of axis and unready/ready forecasts
        - Retrospective claim label, request hash verification, and model/build bindings
        """
        csv_dir = self.work_dir / "csv_input"
        csv_dir.mkdir(parents=True, exist_ok=True)
        nifty_csv_path = csv_dir / "nifty50_synthetic.csv"
        vix_csv_path = csv_dir / "india_vix_synthetic.csv"

        # Generate 207 trading dates starting 2023-01-02, introducing a calendar holiday gap
        dates: List[datetime.date] = []
        curr = datetime.date(2023, 1, 2)
        while len(dates) < 207:
            if curr.weekday() < 5 and curr != datetime.date(2023, 1, 26):  # skip Republic Day
                dates.append(curr)
            curr += datetime.timedelta(days=1)

        # Generate nonflat Nifty Close prices and VIX observations
        nifty_lines = ["Date,Close,Open,High,Low"]
        vix_lines = ["Date,Close"]

        base_price = 18000.0
        for idx, d in enumerate(dates):
            date_str = d.strftime("%d-%b-%Y")
            # Nonflat price motion with trend and oscillations
            cycle = math.sin(idx / 10.0) * 300.0
            trend = idx * 15.0
            price = base_price + trend + cycle
            nifty_lines.append(f"{date_str},{price:.2f},{price-10:.2f},{price+20:.2f},{price-20:.2f}")

            # Missing VIX at origin 205
            if idx != 205:
                vix_val = 14.0 + math.cos(idx / 8.0) * 2.0
                vix_lines.append(f"{date_str},{vix_val:.2f}")

        nifty_csv_path.write_text("\n".join(nifty_lines) + "\n", encoding="utf-8")
        vix_csv_path.write_text("\n".join(vix_lines) + "\n", encoding="utf-8")

        # Load series with provenance
        acq_time = datetime.datetime(2024, 1, 15, 12, 0, 0, tzinfo=datetime.timezone.utc)
        nifty_spec = FileInputSpec(
            file_path=str(nifty_csv_path),
            source_url="https://example.com/nifty50.csv",
            source_use_note="Synthetic Nifty 50 research extract",
            requested_interval=(dates[0], dates[-1]),
            acquisition_time=acq_time,
        )
        vix_spec = FileInputSpec(
            file_path=str(vix_csv_path),
            source_url="https://example.com/vix.csv",
            source_use_note="Synthetic India VIX research extract",
            requested_interval=(dates[0], dates[-1]),
            acquisition_time=acq_time,
        )

        nifty_loaded = load_series("nifty50_price_index", nifty_spec)
        vix_loaded = load_series("india_vix", vix_spec)
        pair = align_pair(nifty_loaded, vix_loaded)
        feature_series = compute_nifty_features(pair)

        self.assertEqual(len(feature_series), 207)
        self.assertEqual(feature_series.unready_count, 201)  # 200 warmup (0..199) + 1 missing VIX (205)
        self.assertEqual(feature_series.ready_count, 6)      # 200, 201, 202, 203, 204, 206

        # Serialize FeatureSeries to wire JSON bytes
        wire_bytes = serialize_replay_input(feature_series)

        # Write request exclusively
        req_path = self.work_dir / "req-loader-backed.json"
        with open(req_path, "xb") as f:
            f.write(wire_bytes)

        # Execute Node.js replay CLI
        exit_code, stdout_bytes, stderr_bytes, record = self._execute_node_child(
            req_path, "loader-backed-roundtrip"
        )
        self.assertEqual(
            exit_code, 0, f"replay.cjs failed with code {exit_code}: {stderr_bytes.decode('utf-8', 'replace')}"
        )

        # Parse entire stdout document
        out_doc = json.loads(stdout_bytes.decode("utf-8"))

        # 1. Assert computed provenance
        comp_prov = out_doc["computed_provenance"]
        self.assertEqual(comp_prov["request"]["raw_byte_count"], len(wire_bytes))
        self.assertEqual(comp_prov["request"]["sha256"], _compute_sha256(wire_bytes))
        self.assertEqual(comp_prov["model"]["sha256"], EXPECTED_MODELS_SHA256)
        self.assertEqual(comp_prov["model"]["platt_params"], [1.42, 0.02])

        candidate_build_manifest = json.loads(CANDIDATE_MANIFEST_PATH.read_text(encoding="utf-8"))
        self.assertEqual(comp_prov["build"], candidate_build_manifest)

        # 2. Assert claim label
        self.assertEqual(out_doc["claim_label"], EXPECTED_CLAIM_LABEL)

        # 3. Assert independent return & zero expectation on typed FeatureSeries
        c200 = float(feature_series.records[200].origin_close)
        c195 = float(feature_series.records[195].origin_close)
        expected_ret_5d = (c200 / c195) - 1.0
        self.assertAlmostEqual(feature_series.records[200].payload.ret_5d, expected_ret_5d, places=7)
        self.assertEqual(feature_series.records[200].payload.rel_strength_20d, 0.0)

        # 4. Assert declared_input matches typed FeatureSeries directly (non-tautological)
        decl_in = out_doc["declared_input"]
        self.assertEqual(decl_in["schema_version"], "nivesh-replay-input-v1")
        self.assertEqual(decl_in["feature_protocol"], feature_series.protocol_id)
        self.assertEqual(decl_in["series_id"], "^NSEI")
        self.assertEqual(decl_in["asset"], "^NSEI")
        self.assertEqual(decl_in["horizon"], "20D")
        self.assertEqual(decl_in["variant"], "frozen-current-core-market-data-only-v1")
        self.assertEqual(decl_in["axis_start_date"], feature_series.axis_start_date.isoformat())
        self.assertEqual(decl_in["calendar_status"], feature_series.calendar_status)
        self.assertEqual(decl_in["missing_sessions"], [d.isoformat() for d in feature_series.missing_sessions])
        self.assertEqual(decl_in["extra_sessions"], [d.isoformat() for d in feature_series.extra_sessions])

        # Verify declared provenance against loader inputs (all 10 fields for both sources)
        self.assertEqual(len(decl_in["nifty_provenance"]), 1)
        self.assertEqual(len(decl_in["vix_provenance"]), 1)

        np0 = decl_in["nifty_provenance"][0]
        self.assertEqual(np0["file_path"], str(nifty_csv_path))
        self.assertEqual(np0["raw_byte_count"], nifty_csv_path.stat().st_size)
        self.assertEqual(np0["sha256"], nifty_loaded.provenance[0].sha256)
        self.assertEqual(np0["sha256"].upper(), _compute_sha256(nifty_csv_path.read_bytes()))
        self.assertEqual(np0["record_count"], 207)
        self.assertEqual(np0["observed_first_date"], dates[0].isoformat())
        self.assertEqual(np0["observed_last_date"], dates[-1].isoformat())
        self.assertEqual(np0["source_url"], "https://example.com/nifty50.csv")
        self.assertEqual(np0["source_use_note"], "Synthetic Nifty 50 research extract")
        self.assertEqual(np0["requested_interval"], [dates[0].isoformat(), dates[-1].isoformat()])
        self.assertEqual(np0["acquisition_time"], "2024-01-15T12:00:00+00:00")

        vp0 = decl_in["vix_provenance"][0]
        self.assertEqual(vp0["file_path"], str(vix_csv_path))
        self.assertEqual(vp0["raw_byte_count"], vix_csv_path.stat().st_size)
        self.assertEqual(vp0["sha256"], vix_loaded.provenance[0].sha256)
        self.assertEqual(vp0["sha256"].upper(), _compute_sha256(vix_csv_path.read_bytes()))
        self.assertEqual(vp0["record_count"], 206)  # index 205 missing
        self.assertEqual(vp0["observed_first_date"], dates[0].isoformat())
        self.assertEqual(vp0["observed_last_date"], dates[-1].isoformat())
        self.assertEqual(vp0["source_url"], "https://example.com/vix.csv")
        self.assertEqual(vp0["source_use_note"], "Synthetic India VIX research extract")
        self.assertEqual(vp0["requested_interval"], [dates[0].isoformat(), dates[-1].isoformat()])
        self.assertEqual(vp0["acquisition_time"], "2024-01-15T12:00:00+00:00")

        # Verify all 207 rows directly against typed FeatureSeries records
        decl_rows = decl_in["rows"]
        self.assertEqual(len(decl_rows), 207)
        for idx, rec in enumerate(feature_series.records):
            r = decl_rows[idx]
            self.assertEqual(r["origin_index"], rec.origin_index)
            self.assertEqual(r["origin_date"], rec.origin_date.isoformat())
            self.assertEqual(r["origin_close"], f"{rec.origin_close:f}")
            expected_vix = f"{rec.vix_close:f}" if rec.vix_close is not None else None
            self.assertEqual(r["vix_close"], expected_vix)
            self.assertEqual(r["feature_ready"], rec.feature_ready)
            self.assertEqual(r["unready_reasons"], list(rec.unready_reasons))
            if rec.feature_ready:
                self.assertIsNotNone(r["payload"])
                p = r["payload"]
                for name in ("ret_5d", "rsi_14", "macd_hist", "vol_30d", "rel_strength_20d", "drawdown"):
                    echoed = p[name]
                    self.assertIsInstance(echoed, (int, float), name)
                    self.assertNotIsInstance(echoed, bool, name)
                    # Exact equality in the binary64 domain: JSON.stringify may print an
                    # integer-valued Number without a fraction, which Python decodes as int, and
                    # it prints -0 as 0; float() maps both back to the transported double.
                    self.assertEqual(float(echoed), getattr(rec.payload, name), f"row {idx} {name}")
                self.assertEqual(p["market_regime"], rec.payload.market_regime)
            else:
                self.assertIsNone(r["payload"])

        # 5. Assert forecasts structure and origin association
        forecasts = out_doc["forecasts"]
        self.assertEqual(len(forecasts), 207)

        # Origins 0..199: warmup -> forecast is null
        for i in range(200):
            self.assertEqual(forecasts[i]["origin_index"], i)
            self.assertEqual(forecasts[i]["origin_date"], dates[i].isoformat())
            self.assertIsNone(forecasts[i]["forecast"], f"Warmup origin {i} forecast must be null")

        # Origin 205: missing VIX -> forecast is null
        self.assertEqual(forecasts[205]["origin_index"], 205)
        self.assertEqual(forecasts[205]["origin_date"], dates[205].isoformat())
        self.assertIsNone(forecasts[205]["forecast"], "Missing VIX origin 205 forecast must be null")

        # Ready origins: 200..204 and 206 -> valid DirectionalForecast
        for i in [200, 201, 202, 203, 204, 206]:
            self.assertEqual(forecasts[i]["origin_index"], i)
            self.assertEqual(forecasts[i]["origin_date"], dates[i].isoformat())
            fc = forecasts[i]["forecast"]
            self.assertIsNotNone(fc, f"Ready origin {i} must have non-null forecast")
            self.assertEqual(fc["horizon"], "20D")
            self.assertEqual(fc["days"], 20)
            self.assertIn(
                fc["expected_direction"],
                {
                    "STRONGLY BULLISH",
                    "MODERATELY BULLISH",
                    "NEUTRAL / RANGE-BOUND",
                    "MODERATELY BEARISH",
                    "STRONGLY BEARISH",
                },
            )

            pb = fc["probability_bullish"]
            pn = fc["probability_neutral"]
            pa = fc["probability_bearish"]
            self.assertTrue(0.0 <= pb <= 1.0)
            self.assertTrue(0.0 <= pn <= 1.0)
            self.assertTrue(0.0 <= pa <= 1.0)
            self.assertAlmostEqual(pb + pn + pa, 1.0, places=5)

    def test_scenario_03_golden_oracle(self) -> None:
        """
        Validates transport wiring parity against the sealed scenario-03 golden baseline.

        Extracts the frozen scenario-03 feature payload, wraps it in a typed FeatureSeries,
        executes replay.cjs, and verifies deep equality against forecast-baseline.json.
        """
        cases_data = json.loads(REPLAY_CASES_PATH.read_text(encoding="utf-8"))
        baseline_data = json.loads(FORECAST_BASELINE_PATH.read_text(encoding="utf-8"))

        scenario_id = "scenario-03-horizon-20d-shipped"
        scenario = next((s for s in cases_data["scenarios"] if s["id"] == scenario_id), None)
        baseline_result = next((r for r in baseline_data["results"] if r["id"] == scenario_id), None)

        self.assertIsNotNone(scenario, f"Scenario {scenario_id} not found in cases fixture")
        self.assertIsNotNone(baseline_result, f"Result {scenario_id} not found in baseline fixture")
        expected_forecast = baseline_result["forecast"]

        # Extract latest price row payload from fixture
        price_rows = scenario["prices_fixture"][scenario["asset"]["symbol"]]
        latest_row = price_rows[-1]

        payload = PredictorPayload(
            ret_5d=latest_row["ret_5d"],
            rsi_14=latest_row["rsi_14"],
            macd_hist=latest_row["macd_hist"],
            vol_30d=latest_row["vol_30d"],
            rel_strength_20d=latest_row["rel_strength_20d"],
            drawdown=latest_row["drawdown"],
            market_regime=latest_row["market_regime"],
        )

        # Construct a synthetic 201-row FeatureSeries (200 warmup + 1 ready at index 200)
        records: List[NiftyFeatureRecord] = []
        d = datetime.date(2025, 1, 1)
        one_day = datetime.timedelta(days=1)

        for i in range(201):
            is_ready = (i == 200)
            records.append(
                NiftyFeatureRecord(
                    origin_index=i,
                    origin_date=d,
                    origin_close=Decimal("25000.00"),
                    vix_close=Decimal("14.50"),
                    feature_ready=is_ready,
                    payload=payload if is_ready else None,
                    unready_reasons=() if is_ready else (REASON_WARMUP,),
                )
            )
            d += one_day

        series = FeatureSeries(
            protocol_id=FEATURES_PROTOCOL_ID,
            axis_start_date=records[0].origin_date,
            records=tuple(records),
            calendar_status="not_checked",
            missing_sessions=(),
            extra_sessions=(),
            nifty_provenance=(),
            vix_provenance=(),
        )

        wire_bytes = serialize_replay_input(series)
        req_path = self.work_dir / "req-golden-oracle.json"
        with open(req_path, "xb") as f:
            f.write(wire_bytes)

        exit_code, stdout_bytes, stderr_bytes, record = self._execute_node_child(
            req_path, "golden-oracle-scenario-03"
        )
        self.assertEqual(
            exit_code, 0, f"replay.cjs failed with code {exit_code}: {stderr_bytes.decode('utf-8', 'replace')}"
        )

        out_doc = json.loads(stdout_bytes.decode("utf-8"))
        forecasts = out_doc["forecasts"]
        self.assertEqual(len(forecasts), 201)

        for i in range(200):
            self.assertIsNone(forecasts[i]["forecast"], f"Warmup origin {i} forecast must be null")

        actual_fc = forecasts[200]["forecast"]
        self.assertIsNotNone(actual_fc, "Origin 200 must contain ready forecast")

        # Compare complete CLI forecast against sealed baseline forecast
        self.assertEqual(actual_fc, expected_forecast)


if __name__ == "__main__":
    unittest.main()
