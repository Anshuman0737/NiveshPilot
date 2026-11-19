"""
Unit and component tests for the pure S2 uncertainty engine (test_uncertainty.py).

Verifies:
  - Exact hand loss expectations and shared paired positions.
  - Scripted RNG continuation, restart on U < 1/L, and wrap behavior.
  - Linear integer 40th quantile interpolation and endpoint ownership.
  - Literal position stream fingerprint byte encoding.
  - Full precedence order: comparison_unavailable > empty_cohort > non_contiguous > floor > available.
  - Validation before unavailability (rejecting malformed types, keys, and contradictions).
  - Public n400 fixed-protocol oracle observing seeds 20261123/20261143, 1 local construction/L,
    B=10000 initial randrange calls and 3990000 direct random() calls/L.
  - Hard cap MAX_RESAMPLE_POSITIONS=30000000 and gate budget enforcement via test ledger.
"""

from __future__ import annotations

import copy
import dataclasses
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import random
import struct
import tempfile
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
import unittest

import research.prediction_eval.uncertainty as uncertainty_module
from research.prediction_eval.uncertainty import (
    BLOCK_FLOOR_FACTOR,
    BLOCK_LENGTH_LABELS,
    BLOCK_LENGTH_SEEDS,
    BLOCK_LENGTHS,
    BOOTSTRAP_REPLICATES,
    BrierRow,
    FINGERPRINT_PREFIX,
    HORIZON_SESSIONS,
    MAX_RESAMPLE_POSITIONS,
    NOMINAL_COVERAGE,
    ORDERED_PAIR_IDS,
    PAIR_HEURISTIC_MINUS_FREQUENCY,
    PAIR_HEURISTIC_MINUS_LOGISTIC,
    QUANTILE_RULE,
    REASON_COMPARISON_UNAVAILABLE,
    REASON_EMPTY_COHORT,
    REASON_INSUFFICIENT_BLOCKS,
    REASON_NON_CONTIGUOUS,
    RequestedKey,
    SCHEMA_VERSION_UNCERTAINTY_DIAGNOSTICS,
    SCHEMA_VERSION_UNCERTAINTY_INPUT,
    UNCERTAINTY_METHOD,
    UNCERTAINTY_PROTOCOL_ID,
    UNCERTAINTY_STATUS_AVAILABLE,
    UNCERTAINTY_STATUS_PARTIALLY_AVAILABLE,
    UNCERTAINTY_STATUS_UNAVAILABLE,
    UncertaintyRequest,
    UncertaintyResourceError,
    UncertaintyValidationError,
    build_uncertainty_diagnostics_document,
    build_uncertainty_input_document,
    compute_paired_replicate_means,
    compute_sampled_position_fingerprint,
    compute_uncertainty,
    generate_stationary_indices,
    linear_integer40_quantile,
    parse_uncertainty_input,
    serialize_uncertainty_input,
    uncertainty_result_to_document,
    validate_uncertainty_diagnostics_document,
    validate_uncertainty_input_document,
    validate_uncertainty_request,
    validate_uncertainty_result_document,
)


LEDGER_KEYS = {"gate_budget", "calls", "total_reserved_positions", "total_visited_positions"}
LEDGER_CALL_KEYS = {
    "call_id",
    "test_name",
    "test_id",
    "required_positions",
    "reserved_positions",
    "visited_positions",
    "status",
    "reserved_at",
}


def _is_count(value: Any) -> bool:
    return type(value) is int and value >= 0


def _read_validated_ledger(ledger_path: Path, budget: int) -> Dict[str, Any]:
    """Loads an existing ledger and refuses any schema, count or total it cannot account for."""
    raw_text = ledger_path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw_text)
    except ValueError as e:
        raise RuntimeError(f"Corrupt sampling ledger JSON: {ledger_path}") from e
    if type(data) is not dict or set(data.keys()) != LEDGER_KEYS:
        raise RuntimeError(f"Sampling ledger schema mismatch: {ledger_path}")
    for key in ("gate_budget", "total_reserved_positions", "total_visited_positions"):
        if not _is_count(data[key]):
            raise RuntimeError(f"Sampling ledger {key} must be a native non-negative count: {data[key]!r}")
    if data["gate_budget"] != budget:
        raise RuntimeError(f"Sampling ledger budget {data['gate_budget']} differs from gate budget {budget}")
    calls = data["calls"]
    if type(calls) is not list:
        raise RuntimeError("Sampling ledger calls must be a list")
    reserved = 0
    visited = 0
    for call in calls:
        if type(call) is not dict or not LEDGER_CALL_KEYS <= set(call.keys()):
            raise RuntimeError(f"Sampling ledger call schema mismatch: {call!r}")
        if not _is_count(call["required_positions"]) or not _is_count(call["reserved_positions"]):
            raise RuntimeError(f"Sampling ledger call counts must be native non-negative counts: {call!r}")
        if call["status"] == "completed":
            if not _is_count(call["visited_positions"]):
                raise RuntimeError(f"Completed sampling call needs an observed count: {call!r}")
            visited += call["visited_positions"]
        elif call["status"] != "incomplete" or call["visited_positions"] != "unknown":
            raise RuntimeError(f"Incomplete sampling call must stay unknown: {call!r}")
        reserved += call["reserved_positions"]
    if reserved != data["total_reserved_positions"] or visited != data["total_visited_positions"]:
        raise RuntimeError(f"Sampling ledger totals contradict its calls: {reserved}, {visited}")
    if reserved > budget:
        raise RuntimeError(f"Sampling ledger already exceeds its budget: {reserved} > {budget}")
    return data


def _reserve_sampling_budget(
    call_id: str,
    required_positions: int,
    budget: int = 20000000,
    ledger_path_override: Optional[Path] = None,
) -> None:
    ledger_path_str = os.environ.get("NIVESH_EVAL_S2_TEST_LEDGER")
    if not ledger_path_str and ledger_path_override is None:
        return
    ledger_path = ledger_path_override or Path(ledger_path_str)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    data: Dict[str, Any] = {
        "gate_budget": budget,
        "calls": [],
        "total_reserved_positions": 0,
        "total_visited_positions": 0,
    }
    if ledger_path.exists():
        data = _read_validated_ledger(ledger_path, budget)
    current_reserved = data["total_reserved_positions"]
    if current_reserved + required_positions > budget:
        raise RuntimeError(f"Gate sampling budget exceeded: {current_reserved + required_positions} > {budget}")
    data["total_reserved_positions"] = current_reserved + required_positions
    call_rec = {
        "call_id": call_id,
        "test_name": call_id,
        "test_id": call_id,
        "required_positions": required_positions,
        "reserved_positions": required_positions,
        "visited_positions": "unknown",
        "status": "incomplete",
        "reserved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    data.setdefault("calls", []).append(call_rec)
    ledger_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _complete_sampling_call(
    call_id: str,
    visited_positions: int,
    ledger_path_override: Optional[Path] = None,
    budget: int = 20000000,
) -> None:
    ledger_path_str = os.environ.get("NIVESH_EVAL_S2_TEST_LEDGER")
    if not ledger_path_str and ledger_path_override is None:
        return
    ledger_path = ledger_path_override or Path(ledger_path_str)
    if not ledger_path.exists():
        raise RuntimeError(f"Sampling ledger missing on completion: {ledger_path}")
    data = _read_validated_ledger(ledger_path, budget)
    if not _is_count(visited_positions):
        raise RuntimeError(f"Observed visited positions must be a native count: {visited_positions!r}")
    calls = data["calls"]
    target = None
    for c in reversed(calls):
        if c.get("call_id") == call_id and c.get("status") == "incomplete":
            target = c
            break
    if target is None:
        raise RuntimeError(f"No incomplete sampling call found for call_id '{call_id}'")
    target["visited_positions"] = visited_positions
    target["status"] = "completed"
    target["completed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    data["total_visited_positions"] += visited_positions
    ledger_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


TEST_INPUT_IDENTITY: Dict[str, Any] = {"raw_byte_count": 500, "sha256": "A" * 64}
TEST_RUNTIME: Dict[str, str] = {"python_implementation": "CPython", "python_version": "3.12.10"}


class ScriptedRng:
    """
    Deterministic stand-in for the two RNG methods the protocol may call.

    Each replicate of n positions starts at r % n, continues by one for restart_step - 1 steps,
    restarts once at (7 * r) % n and continues to its end. U is the literal 1/L at every
    continuation, so a <= comparison would restart, and 0.0 at the single restart.
    """

    def __init__(self, n: int, block_length: int, restart_step: int) -> None:
        self.n = n
        self.continue_u = 1.0 / block_length
        self.restart_step = restart_step
        self.replicate = 0
        self.step = 0
        self.random_calls = 0
        self.initial_calls = 0
        self.restart_calls = 0

    def randrange(self, stop: int) -> int:
        if stop != self.n:
            raise AssertionError(f"randrange bound {stop} is not n={self.n}")
        if self.step == self.restart_step:
            self.restart_calls += 1
            return (7 * self.replicate) % self.n
        self.initial_calls += 1
        return self.replicate % self.n

    def random(self) -> float:
        self.random_calls += 1
        self.step += 1
        value = 0.0 if self.step == self.restart_step else self.continue_u
        if self.step == self.n - 1:
            self.step = 0
            self.replicate += 1
        return value


def _scripted_positions(replicate: int, n: int, restart_step: int) -> List[int]:
    """The literal positions ScriptedRng prescribes, stated without the production sampler."""
    first = [(replicate + i) % n for i in range(restart_step)]
    second = [((7 * replicate) % n + i) % n for i in range(n - restart_step)]
    return first + second


class TestUncertaintyPure(unittest.TestCase):
    """Component, validation, quantile, fingerprint and oracle unit tests."""

    def _compute(self, request: UncertaintyRequest, cap: int = 100000, **kwargs: Any) -> Any:
        """A public call with valid identities, so a test fails only on its own subject."""
        if request.input_identity is None:
            request = dataclasses.replace(request, input_identity=dict(TEST_INPUT_IDENTITY))
        return compute_uncertainty(request, max_resample_positions=cap, runtime_identity=dict(TEST_RUNTIME), **kwargs)

    def _make_axis_dates(self, count: int, start_date: datetime.date = datetime.date(2023, 1, 1)) -> Tuple[datetime.date, ...]:
        dates = []
        cur = start_date
        for _ in range(count):
            dates.append(cur)
            cur += datetime.timedelta(days=1)
        return tuple(dates)

    def _make_keys_and_rows(
        self,
        axis_dates: Sequence[datetime.date],
        indices: Sequence[int],
        h_scores: Sequence[float],
        f_scores: Sequence[float],
        l_scores: Sequence[float],
    ) -> Tuple[Tuple[RequestedKey, ...], Dict[str, Tuple[BrierRow, ...]]]:
        keys = tuple(RequestedKey(idx, axis_dates[idx]) for idx in indices)
        rows = {
            "heuristic": tuple(BrierRow(idx, axis_dates[idx], float(s)) for idx, s in zip(indices, h_scores)),
            "frequency": tuple(BrierRow(idx, axis_dates[idx], float(s)) for idx, s in zip(indices, f_scores)),
            "logistic": tuple(BrierRow(idx, axis_dates[idx], float(s)) for idx, s in zip(indices, l_scores)),
        }
        return keys, rows

    def test_hand_losses_brier_difference_and_shared_pairs(self) -> None:
        """
        Hand losses [0, 1, 2] vs [1, 1, 1] gives d = [-1, 0, 1], point mean 0.
        Prescribed [0, 0, 2] replicate mean = -1/3.
        Both pairs share exact draws; sign reversal differs.
        Exercises production compute_paired_replicate_means and compute_uncertainty.
        """
        # 3 points: indices 0, 1, 2. To satisfy mature span, N=23, T=0 -> span [0, 3)
        dates = self._make_axis_dates(23)
        indices = (0, 1, 2)
        h_losses = [0.0, 1.0, 2.0]
        f_losses = [1.0, 1.0, 1.0]
        l_losses = [1.0, 1.0, 1.0]

        keys, rows = self._make_keys_and_rows(dates, indices, h_losses, f_losses, l_losses)

        # Direct verification of point difference calculation
        d_hf = [h - f for h, f in zip(h_losses, f_losses)]
        d_hl = [h - l for h, l in zip(h_losses, l_losses)]
        self.assertEqual(d_hf, [-1.0, 0.0, 1.0])
        self.assertEqual(d_hl, [-1.0, 0.0, 1.0])
        self.assertEqual(math.fsum(d_hf) / 3.0, 0.0)

        # Three prescribed kernel calls of three positions each, accounted before they run
        _reserve_sampling_budget("test_hand_losses_kernel", 9, budget=20000000)

        # Prescribed sample positions [0, 0, 2] exercised via production compute_paired_replicate_means
        prescribed_pos = [0, 0, 2]
        mean_hf, mean_hl = compute_paired_replicate_means(d_hf, d_hl, prescribed_pos)
        self.assertAlmostEqual(mean_hf, -1.0 / 3.0, places=12)
        self.assertAlmostEqual(mean_hl, -1.0 / 3.0, places=12)
        self.assertEqual(mean_hf, mean_hl)

        # Sign reversal (frequency - heuristic) via production compute_paired_replicate_means gives +1/3
        d_fh = [f - h for h, f in zip(h_losses, f_losses)]
        mean_fh, _ = compute_paired_replicate_means(d_fh, d_hl, prescribed_pos)
        self.assertAlmostEqual(mean_fh, 1.0 / 3.0, places=12)
        self.assertAlmostEqual(mean_fh, -mean_hf, places=12)

        # Independent draws would not share positions and would differ in general
        indep_pos = [1, 2, 2]
        _, mean_hl_indep = compute_paired_replicate_means(d_hf, d_hl, indep_pos)
        self.assertNotEqual(mean_hf, mean_hl_indep)
        _complete_sampling_call("test_hand_losses_kernel", 9)

        # Full production compute_uncertainty call exercising hand losses request
        req = UncertaintyRequest(
            axis_dates=dates,
            test_start_index=0,
            requested_keys=keys,
            comparison_status="scored",
            method_available={"heuristic": True, "frequency": True, "logistic": True},
            method_rows=rows,
            union_gap_positions=(),
            input_identity={"raw_byte_count": 500, "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"},
        )
        res = self._compute(req, MAX_RESAMPLE_POSITIONS)
        self.assertEqual(res.status, UNCERTAINTY_STATUS_UNAVAILABLE)
        self.assertEqual(res.reason, REASON_INSUFFICIENT_BLOCKS)
        self.assertEqual(len(res.point_differences), 2)
        self.assertEqual(res.point_differences[0].pair_id, PAIR_HEURISTIC_MINUS_FREQUENCY)
        self.assertAlmostEqual(res.point_differences[0].point_difference, 0.0, places=12)
        self.assertEqual(res.point_differences[1].pair_id, PAIR_HEURISTIC_MINUS_LOGISTIC)
        self.assertAlmostEqual(res.point_differences[1].point_difference, 0.0, places=12)

    def test_quantile_integer_interpolation(self) -> None:
        """
        Quantile [0, 10, 20, 30, 40] gives 1.0 and 39.0 on 40ths.
        Endpoints q0/q1, single value, and equal neighbors exercise branches.
        """
        x = [0.0, 10.0, 20.0, 30.0, 40.0]
        # q = 1/40 (2.5%) -> (5 - 1) * 1 = 4 -> j = 0, rem = 4 -> w = 4/40 = 0.1 -> 0 + 0.1*(10 - 0) = 1.0
        q_lower = linear_integer40_quantile(x, 1, 40)
        self.assertAlmostEqual(q_lower, 1.0, places=12)

        # q = 39/40 (97.5%) -> (5 - 1) * 39 = 156 -> j = 3, rem = 36 -> w = 36/40 = 0.9 -> 30 + 0.9*10 = 39.0
        q_upper = linear_integer40_quantile(x, 39, 40)
        self.assertAlmostEqual(q_upper, 39.0, places=12)

        # Nearest index would give 0 and 40; linear interpolation differs
        self.assertNotEqual(q_lower, 0.0)
        self.assertNotEqual(q_upper, 40.0)

        # Endpoint q0 -> 0.0
        self.assertAlmostEqual(linear_integer40_quantile(x, 0, 40), 0.0, places=12)
        # Endpoint q1 -> 40.0
        self.assertAlmostEqual(linear_integer40_quantile(x, 40, 40), 40.0, places=12)

        # Single value
        self.assertAlmostEqual(linear_integer40_quantile([5.5], 1, 40), 5.5, places=12)

        # Equal neighbors
        equal_vals = [2.0, 2.0, 2.0, 2.0]
        self.assertAlmostEqual(linear_integer40_quantile(equal_vals, 1, 40), 2.0, places=12)
        self.assertAlmostEqual(linear_integer40_quantile(equal_vals, 39, 40), 2.0, places=12)

    def test_scripted_rng_continuation_restart_and_boundary(self) -> None:
        """
        Supplies U exactly 1/L (0.05 for L20) and asserts continuation / no restart draw.
        Rule is U < 1/L, not <=.
        Exercises production generate_stationary_indices with boundary continuation,
        below-threshold restart, wrap-around, and stream continuation across replicates.
        """
        # Fake RNG supplying predetermined sequence of random() and randrange()
        class FakeRNG:
            def __init__(self, u_sequence: List[float], randrange_sequence: List[int]):
                self.u_seq = list(u_sequence)
                self.rr_seq = list(randrange_sequence)
                self.random_call_count = 0
                self.randrange_call_count = 0

            def random(self) -> float:
                self.random_call_count += 1
                if not self.u_seq:
                    raise IndexError("FakeRNG ran out of random() draws")
                return self.u_seq.pop(0)

            def randrange(self, stop: int) -> int:
                self.randrange_call_count += 1
                if not self.rr_seq:
                    raise IndexError("FakeRNG ran out of randrange() draws")
                return self.rr_seq.pop(0)

        # For L = 20: 1/L = 0.05.
        # Boundary test:
        # Replicate 1: n = 5, L = 20.
        # Initial pos = 3 (randrange #1).
        # Draw 1: u = 0.05 -> continuation (0.05 is NOT < 0.05!) -> pos = (3 + 1) % 5 = 4.
        # Draw 2: u = 0.99 -> continuation -> pos = (4 + 1) % 5 = 0 (wrap-around!).
        # Draw 3: u = 0.049 -> restart (0.049 < 0.05) -> calls randrange -> pos = 2 (randrange #2).
        # Draw 4: u = 0.05 -> continuation (boundary!) -> pos = (2 + 1) % 5 = 3.
        # Replicate 2 (stream continuation):
        # Initial pos = 1 (randrange #3).
        # Draw 5: u = 0.02 -> restart (0.02 < 0.05) -> calls randrange -> pos = 4 (randrange #4).
        # Draw 6: u = 0.50 -> continuation -> pos = (4 + 1) % 5 = 0 (wrap-around!).
        # Draw 7: u = 0.50 -> continuation -> pos = (0 + 1) % 5 = 1.
        # Draw 8: u = 0.50 -> continuation -> pos = (1 + 1) % 5 = 2.
        fake = FakeRNG(
            u_sequence=[0.05, 0.99, 0.049, 0.05, 0.02, 0.50, 0.50, 0.50],
            randrange_sequence=[3, 2, 1, 4],
        )

        n = 5
        L = 20

        # Two scripted kernel calls of n positions each, accounted before they run
        _reserve_sampling_budget("test_scripted_kernel", 2 * n, budget=20000000)

        # Replicate 1 via production generate_stationary_indices
        indices1, restarts1 = generate_stationary_indices(fake, n=n, L=L)
        self.assertEqual(indices1, [3, 4, 0, 2, 3])
        self.assertEqual(restarts1, 1)
        self.assertEqual(fake.random_call_count, 4)
        self.assertEqual(fake.randrange_call_count, 2)

        # Replicate 2 (stream continuation on same RNG instance)
        indices2, restarts2 = generate_stationary_indices(fake, n=n, L=L)
        self.assertEqual(indices2, [1, 4, 0, 1, 2])
        self.assertEqual(restarts2, 1)
        self.assertEqual(fake.random_call_count, 8)
        self.assertEqual(fake.randrange_call_count, 4)
        _complete_sampling_call("test_scripted_kernel", len(indices1) + len(indices2))

    def test_fingerprint_literal_encoding(self) -> None:
        """
        Validates index stream fingerprint computation against literal manual encoding bytes.
        """
        input_sha = "A" * 64
        block_length = 20
        replicates = 2
        n = 3
        seed = 20261123

        # Manual stream: replicate 0 -> [1, 2, 0]; replicate 1 -> [0, 1, 1]
        replicates_data = [
            (0, [1, 2, 0]),
            (1, [0, 1, 1]),
        ]

        expected_hasher = hashlib.sha256()
        expected_hasher.update(b"NIVESHPILOT_S2_SB_INDEX_V1\x00")
        expected_hasher.update(bytes.fromhex(input_sha))
        expected_hasher.update(struct.pack(">QQQQ", block_length, replicates, n, seed))
        for r, pos_list in replicates_data:
            expected_hasher.update(struct.pack(">Q", r))
            for p in pos_list:
                expected_hasher.update(struct.pack(">Q", p))
        expected_sha = expected_hasher.hexdigest().upper()

        actual_sha = compute_sampled_position_fingerprint(
            input_sha, block_length, replicates, n, seed, replicates_data
        )
        self.assertEqual(actual_sha, expected_sha)
        self.assertEqual(len(actual_sha), 64)

    def test_validation_precedence_and_error_truth(self) -> None:
        """
        Validates that malformed data raises UncertaintyValidationError before unavailability.
        """
        dates = self._make_axis_dates(30)
        keys = tuple(RequestedKey(i, dates[i]) for i in range(5, 10))
        h_rows = tuple(BrierRow(i, dates[i], 0.5) for i in range(5, 10))
        f_rows = tuple(BrierRow(i, dates[i], 0.4) for i in range(5, 10))
        l_rows = tuple(BrierRow(i, dates[i], 0.3) for i in range(5, 10))
        valid_rows = {"heuristic": h_rows, "frequency": f_rows, "logistic": l_rows}
        valid_avail = {"heuristic": True, "frequency": True, "logistic": True}

        # 1. bool in integer test_start_index
        bad_req = UncertaintyRequest(
            axis_dates=dates,
            test_start_index=True,  # type: ignore
            requested_keys=keys,
            comparison_status="scored",
            method_available=valid_avail,
            method_rows=valid_rows,
            union_gap_positions=(),
        )
        with self.assertRaises(UncertaintyValidationError):
            self._compute(bad_req, 1000)

        # 2. float in test_start_index
        bad_req = UncertaintyRequest(
            axis_dates=dates,
            test_start_index=5.0,  # type: ignore
            requested_keys=keys,
            comparison_status="scored",
            method_available=valid_avail,
            method_rows=valid_rows,
            union_gap_positions=(),
        )
        with self.assertRaises(UncertaintyValidationError):
            self._compute(bad_req, 1000)

        # 3. Bad dates order
        bad_dates = (datetime.date(2023, 1, 2), datetime.date(2023, 1, 1))
        bad_req = UncertaintyRequest(
            axis_dates=bad_dates,
            test_start_index=0,
            requested_keys=(),
            comparison_status="empty",
            method_available=valid_avail,
            method_rows={"heuristic": (), "frequency": (), "logistic": ()},
            union_gap_positions=(),
        )
        with self.assertRaises(UncertaintyValidationError):
            self._compute(bad_req, 1000)

        # 4. Out-of-order requested keys
        out_of_order_keys = (RequestedKey(6, dates[6]), RequestedKey(5, dates[5]))
        bad_req = UncertaintyRequest(
            axis_dates=dates,
            test_start_index=5,
            requested_keys=out_of_order_keys,
            comparison_status="scored",
            method_available=valid_avail,
            method_rows=valid_rows,
            union_gap_positions=(),
        )
        with self.assertRaises(UncertaintyValidationError):
            self._compute(bad_req, 1000)

        # 5. Non-finite loss value (NaN)
        with self.assertRaises(UncertaintyValidationError):
            BrierRow(5, dates[5], float("nan"))

        # 6. Loss outside [0, 2]
        with self.assertRaises(UncertaintyValidationError):
            BrierRow(5, dates[5], 2.01)

        # 7. Comparison status contradiction: comparison_unavailable but all methods available
        bad_req = UncertaintyRequest(
            axis_dates=dates,
            test_start_index=5,
            requested_keys=keys,
            comparison_status="comparison_unavailable",
            method_available=valid_avail,  # all True!
            method_rows=None,
            union_gap_positions=(),
        )
        with self.assertRaises(UncertaintyValidationError):
            self._compute(bad_req, 1000)

        # 8. Comparison status contradiction: scored but method_rows has None
        bad_req = UncertaintyRequest(
            axis_dates=dates,
            test_start_index=5,
            requested_keys=keys,
            comparison_status="scored",
            method_available=valid_avail,
            method_rows=None,
            union_gap_positions=(),
        )
        with self.assertRaises(UncertaintyValidationError):
            self._compute(bad_req, 1000)

    def test_precedence_transitions(self) -> None:
        """
        Tests the 5 precedence transitions:
          1. comparison_unavailable
          2. empty_cohort
          3. non_contiguous_test_cohort
          4. insufficient_nominal_blocks
          5. available
        """
        dates = self._make_axis_dates(50)
        # mature test span: [10, 30) -> 20 sessions
        T = 10
        mature_indices = list(range(10, 30))

        # 1. comparison_unavailable: frequency is unavailable
        keys, rows = self._make_keys_and_rows(
            dates, mature_indices, [0.5] * 20, [0.5] * 20, [0.5] * 20
        )
        avail = {"heuristic": True, "frequency": False, "logistic": True}
        req1 = UncertaintyRequest(
            axis_dates=dates,
            test_start_index=T,
            requested_keys=keys,
            comparison_status="comparison_unavailable",
            method_available=avail,
            method_rows=None,
            union_gap_positions=(),
        )
        res1 = self._compute(req1)
        self.assertEqual(res1.status, UNCERTAINTY_STATUS_UNAVAILABLE)
        self.assertEqual(res1.reason, REASON_COMPARISON_UNAVAILABLE)
        self.assertIsNone(res1.point_differences[0].point_difference)
        self.assertIsNone(res1.point_differences[1].point_difference)
        for bl in res1.block_lengths:
            self.assertEqual(bl.status, UNCERTAINTY_STATUS_UNAVAILABLE)
            self.assertEqual(bl.reason, REASON_COMPARISON_UNAVAILABLE)

        # 2. empty_cohort: 0 requested keys
        avail_all = {"heuristic": True, "frequency": True, "logistic": True}
        req2 = UncertaintyRequest(
            axis_dates=dates,
            test_start_index=T,
            requested_keys=(),
            comparison_status="empty",
            method_available=avail_all,
            method_rows={"heuristic": (), "frequency": (), "logistic": ()},
            union_gap_positions=tuple(mature_indices),
        )
        res2 = self._compute(req2)
        self.assertEqual(res2.status, UNCERTAINTY_STATUS_UNAVAILABLE)
        self.assertEqual(res2.reason, REASON_EMPTY_COHORT)
        self.assertIsNone(res2.point_differences[0].point_difference)

        # 3. non_contiguous_test_cohort: has gap position 15
        kept_indices = [i for i in mature_indices if i != 15]
        keys3, rows3 = self._make_keys_and_rows(
            dates, kept_indices, [0.6] * 19, [0.4] * 19, [0.3] * 19
        )
        req3 = UncertaintyRequest(
            axis_dates=dates,
            test_start_index=T,
            requested_keys=keys3,
            comparison_status="scored",
            method_available=avail_all,
            method_rows=rows3,
            union_gap_positions=(15,),
        )
        res3 = self._compute(req3)
        self.assertEqual(res3.status, UNCERTAINTY_STATUS_UNAVAILABLE)
        self.assertEqual(res3.reason, REASON_NON_CONTIGUOUS)
        # Point differences are preserved!
        self.assertIsNotNone(res3.point_differences[0].point_difference)
        self.assertAlmostEqual(res3.point_differences[0].point_difference, 0.2, places=12)
        self.assertAlmostEqual(res3.point_differences[1].point_difference, 0.3, places=12)
        for bl in res3.block_lengths:
            self.assertEqual(bl.status, UNCERTAINTY_STATUS_UNAVAILABLE)
            self.assertEqual(bl.reason, REASON_NON_CONTIGUOUS)

        # 4. insufficient_nominal_blocks: contiguous, but n=20 < 10*L for all L in (20, 40, 60)
        req4 = UncertaintyRequest(
            axis_dates=dates,
            test_start_index=T,
            requested_keys=keys,
            comparison_status="scored",
            method_available=avail_all,
            method_rows=rows,
            union_gap_positions=(),
        )
        res4 = self._compute(req4)
        self.assertEqual(res4.status, UNCERTAINTY_STATUS_UNAVAILABLE)
        self.assertEqual(res4.reason, REASON_INSUFFICIENT_BLOCKS)
        self.assertIsNotNone(res4.point_differences[0].point_difference)
        for bl in res4.block_lengths:
            self.assertEqual(bl.status, UNCERTAINTY_STATUS_UNAVAILABLE)
            self.assertEqual(bl.reason, REASON_INSUFFICIENT_BLOCKS)

    def _contiguous_request(self, n: int) -> UncertaintyRequest:
        """A scored cohort filling its whole mature span: N = n + 20, T = 0."""
        dates = self._make_axis_dates(n + HORIZON_SESSIONS)
        keys, rows = self._make_keys_and_rows(dates, range(n), [0.5] * n, [0.5] * n, [0.5] * n)
        return UncertaintyRequest(
            axis_dates=dates,
            test_start_index=0,
            requested_keys=keys,
            comparison_status="scored",
            method_available={"heuristic": True, "frequency": True, "logistic": True},
            method_rows=rows,
            union_gap_positions=(),
        )

    @staticmethod
    def _forbidden_rng(seed: int) -> Any:
        raise AssertionError(f"RNG constructed with seed {seed}")

    def test_floor_transitions_independent_per_length(self) -> None:
        """
        Each n=10L-1/n=10L boundary, read from the operation count a cap of 1 refuses, so no
        boundary needs a full run. Counts are literal: B times n times the lengths cleared.
        """
        res199 = self._compute(self._contiguous_request(199), 1, rng_factory=self._forbidden_rng)
        self.assertEqual(res199.status, UNCERTAINTY_STATUS_UNAVAILABLE)
        self.assertEqual(res199.reason, REASON_INSUFFICIENT_BLOCKS)
        self.assertEqual([view.reason for view in res199.block_lengths], [REASON_INSUFFICIENT_BLOCKS] * 3)
        self.assertEqual(res199.diagnostics.resource["required_positions"], 0)

        for n, required in ((200, 2000000), (399, 3990000), (400, 8000000), (599, 11980000), (600, 18000000)):
            with self.subTest(n=n):
                with self.assertRaises(UncertaintyResourceError) as ctx:
                    self._compute(self._contiguous_request(n), 1, rng_factory=self._forbidden_rng)
                self.assertEqual(ctx.exception.required_positions, required)
                self.assertEqual(ctx.exception.max_positions, 1)

    def test_resource_cap_validation_and_refusal(self) -> None:
        """Rejects, never clamps, a bad cap, even on a request that needs no sampling."""
        dates = self._make_axis_dates(25)
        keys, rows = self._make_keys_and_rows(dates, (0,), [0.5], [0.5], [0.5])
        req = UncertaintyRequest(
            axis_dates=dates,
            test_start_index=0,
            requested_keys=keys,
            comparison_status="scored",
            method_available={"heuristic": True, "frequency": True, "logistic": True},
            method_rows=rows,
            union_gap_positions=tuple(range(1, 5)),
        )

        for bad_cap in (0, -1, 30000001, True, False, 100.5, 1000.0, "1000", None):
            with self.subTest(cap=bad_cap):
                with self.assertRaises(UncertaintyValidationError):
                    self._compute(req, bad_cap)  # type: ignore[arg-type]

        # A malformed request stays a validation error whatever the cap would have refused
        bad_request = dataclasses.replace(self._contiguous_request(200), union_gap_positions=(3,))
        with self.assertRaises(UncertaintyValidationError):
            self._compute(bad_request, 1, rng_factory=self._forbidden_rng)

    def test_production_encoding_cap_boundary_and_endpoints_on_a_scripted_stream(self) -> None:
        """
        One public call on a literal position stream, n=200 so only L20 clears. The expected
        bytes, means and endpoints come from _scripted_positions and the stated encoding, never
        from production helpers, so the inline encoder and the sort/quantile steps are both
        bound. The same request refuses one position below the cap it then runs exactly at.
        """
        n = 200
        restart_step = 100
        required = 2000000
        dates = self._make_axis_dates(n + HORIZON_SESSIONS)
        h_losses = [(i % 8) / 8.0 for i in range(n)]
        f_losses = [0.25] * n
        l_losses = [((3 * i) % 16) / 16.0 for i in range(n)]
        keys, rows = self._make_keys_and_rows(dates, range(n), h_losses, f_losses, l_losses)
        input_sha = "C" * 64
        req = UncertaintyRequest(
            axis_dates=dates,
            test_start_index=0,
            requested_keys=keys,
            comparison_status="scored",
            method_available={"heuristic": True, "frequency": True, "logistic": True},
            method_rows=rows,
            union_gap_positions=(),
            input_identity={"raw_byte_count": 77, "sha256": input_sha},
        )

        with self.assertRaises(UncertaintyResourceError) as ctx:
            self._compute(req, required - 1, rng_factory=self._forbidden_rng)
        self.assertEqual(ctx.exception.required_positions, required)

        constructed: List[Tuple[int, ScriptedRng]] = []

        def _factory(seed: int) -> ScriptedRng:
            rng = ScriptedRng(n, 20, restart_step)
            constructed.append((seed, rng))
            return rng

        _reserve_sampling_budget("test_scripted_public_call", required, budget=20000000)
        res = self._compute(req, required, rng_factory=_factory)
        diag = res.diagnostics.lengths[0]
        _complete_sampling_call("test_scripted_public_call", diag.sampled_positions)

        self.assertEqual([seed for seed, _ in constructed], [20261123])
        rng = constructed[0][1]
        self.assertEqual(rng.initial_calls, 10000)
        self.assertEqual(rng.restart_calls, 10000)
        self.assertEqual(rng.random_calls, 1990000)
        self.assertEqual(diag.random_calls, 1990000)
        self.assertEqual(diag.randrange_calls, 20000)
        self.assertEqual(diag.sampled_positions, required)
        self.assertEqual(res.diagnostics.resource["required_positions"], required)
        self.assertEqual(res.diagnostics.resource["visited_positions"], required)
        self.assertEqual(res.diagnostics.resource["max_resample_positions"], required)

        expected = hashlib.sha256()
        expected.update(b"NIVESHPILOT_S2_SB_INDEX_V1\x00")
        expected.update(b"\xcc" * 32)
        expected.update((20).to_bytes(8, "big"))
        expected.update((10000).to_bytes(8, "big"))
        expected.update((200).to_bytes(8, "big"))
        expected.update((20261123).to_bytes(8, "big"))
        d_hf = [h - f for h, f in zip(h_losses, f_losses)]
        d_hl = [h - l for h, l in zip(h_losses, l_losses)]
        means_hf: List[float] = []
        means_hl: List[float] = []
        for replicate in range(10000):
            positions = _scripted_positions(replicate, n, restart_step)
            expected.update(replicate.to_bytes(8, "big"))
            expected.update(b"".join(position.to_bytes(8, "big") for position in positions))
            means_hf.append(math.fsum(d_hf[p] for p in positions) / n)
            means_hl.append(math.fsum(d_hl[p] for p in positions) / n)
        self.assertEqual(diag.index_stream_sha256, expected.hexdigest().upper())

        # B=10000: h = 9999/40 gives j=249, w=39/40; h = 9999*39/40 gives j=9749, w=1/40
        for pair, means in zip(res.block_lengths[0].pairs, (sorted(means_hf), sorted(means_hl))):
            self.assertAlmostEqual(pair.lower, means[249] + (39 / 40) * (means[250] - means[249]), places=12)
            self.assertAlmostEqual(pair.upper, means[9749] + (1 / 40) * (means[9750] - means[9749]), places=12)
        self.assertNotEqual(res.block_lengths[0].pairs[0].lower, res.block_lengths[0].pairs[1].lower)

        self.assertEqual(res.status, UNCERTAINTY_STATUS_PARTIALLY_AVAILABLE)
        self.assertAlmostEqual(res.point_differences[0].point_difference, math.fsum(d_hf) / n, places=12)
        self.assertAlmostEqual(res.point_differences[1].point_difference, math.fsum(d_hl) / n, places=12)
        self.assertEqual([view.status for view in res.block_lengths[1:]], [UNCERTAINTY_STATUS_UNAVAILABLE] * 2)
        self.assertEqual(res.diagnostics.lengths[1].seed, 20261143)
        self.assertIsNone(res.diagnostics.lengths[2].index_stream_sha256)
        validate_uncertainty_result_document(uncertainty_result_to_document(res))
        validate_uncertainty_diagnostics_document(build_uncertainty_diagnostics_document(res.diagnostics))

    def test_computation_identities_are_required_before_any_state_or_rng(self) -> None:
        """No state falls back to a zero hash, a blank identity or a measured runtime."""
        unavailable = dataclasses.replace(
            self._contiguous_request(30),
            comparison_status="comparison_unavailable",
            method_available={"heuristic": True, "frequency": False, "logistic": True},
            method_rows=None,
        )
        cases = {
            "missing": None,
            "empty": {},
            "not_mapping": "A" * 64,
            "no_hash": {"raw_byte_count": 10},
            "no_count": {"sha256": "A" * 64},
            "extra_key": {"raw_byte_count": 10, "sha256": "A" * 64, "path": "x"},
            "short_hash": {"raw_byte_count": 10, "sha256": "A" * 63},
            "not_hex": {"raw_byte_count": 10, "sha256": "Z" * 64},
            "hash_not_text": {"raw_byte_count": 10, "sha256": 5},
            "bool_count": {"raw_byte_count": True, "sha256": "A" * 64},
            "float_count": {"raw_byte_count": 10.0, "sha256": "A" * 64},
            "negative_count": {"raw_byte_count": -1, "sha256": "A" * 64},
        }
        for state, base in (("unavailable", unavailable), ("available", self._contiguous_request(200))):
            for name, identity in cases.items():
                with self.subTest(state=state, identity=name):
                    with self.assertRaises(UncertaintyValidationError):
                        compute_uncertainty(
                            dataclasses.replace(base, input_identity=identity),
                            max_resample_positions=MAX_RESAMPLE_POSITIONS,
                            runtime_identity=dict(TEST_RUNTIME),
                            rng_factory=self._forbidden_rng,
                        )

        with_identity = dataclasses.replace(self._contiguous_request(200), input_identity=dict(TEST_INPUT_IDENTITY))
        for runtime in (
            None,
            {},
            {"python_implementation": "CPython"},
            {"python_implementation": "CPython", "python_version": ""},
            {"python_implementation": "CPython", "python_version": 3},
            dict(TEST_RUNTIME, rng_api="x"),
        ):
            with self.subTest(runtime=runtime):
                with self.assertRaises(UncertaintyValidationError):
                    compute_uncertainty(
                        with_identity,
                        max_resample_positions=MAX_RESAMPLE_POSITIONS,
                        runtime_identity=runtime,  # type: ignore[arg-type]
                        rng_factory=self._forbidden_rng,
                    )

        # The caller's labels are what diagnostics record, in both diagnostics paths
        labels = {"python_implementation": "ReportedPython", "python_version": "9.9.9"}
        identified = dataclasses.replace(unavailable, input_identity=dict(TEST_INPUT_IDENTITY))
        floored = dataclasses.replace(self._contiguous_request(30), input_identity=dict(TEST_INPUT_IDENTITY))
        for request in (identified, floored):
            diagnostics = compute_uncertainty(request, max_resample_positions=1, runtime_identity=labels).diagnostics
            self.assertEqual(diagnostics.runtime_identity["python_implementation"], "ReportedPython")
            self.assertEqual(diagnostics.runtime_identity["python_version"], "9.9.9")
            self.assertEqual(diagnostics.input_identity, TEST_INPUT_IDENTITY)
        self.assertFalse(hasattr(uncertainty_module, "platform"))

        # The pre-hash domain path needs no identity: it produces the bytes the identity hashes
        raw = serialize_uncertainty_input(self._contiguous_request(30))
        self.assertIsNone(parse_uncertainty_input(raw).input_identity)
        self.assertNotIn(b"input_identity", raw)

    def test_key_axis_and_gap_negatives_stay_errors_in_every_state(self) -> None:
        """No truncation, intersection or reordering of model rows, and no unknown-tail key."""
        dates = self._make_axis_dates(30)
        indices = list(range(5, 10))
        keys, rows = self._make_keys_and_rows(dates, indices, [0.5] * 5, [0.4] * 5, [0.3] * 5)
        good = UncertaintyRequest(
            axis_dates=dates,
            test_start_index=5,
            requested_keys=keys,
            comparison_status="scored",
            method_available={"heuristic": True, "frequency": True, "logistic": True},
            method_rows=rows,
            union_gap_positions=(),
        )
        self.assertEqual(self._compute(good).reason, REASON_INSUFFICIENT_BLOCKS)

        def _rows(**changes: Tuple[BrierRow, ...]) -> Dict[str, Tuple[BrierRow, ...]]:
            return dict(rows, **changes)

        duplicate_keys = (keys[0], keys[0], keys[2], keys[3], keys[4])
        tail_key = RequestedKey(10, dates[10])
        unavailable_dates = dataclasses.replace(
            good,
            comparison_status="comparison_unavailable",
            method_available={"heuristic": True, "frequency": True, "logistic": False},
            method_rows=None,
        )
        cases = {
            "short_model_rows": dataclasses.replace(good, method_rows=_rows(logistic=rows["logistic"][:-1])),
            "long_model_rows": dataclasses.replace(good, method_rows=_rows(frequency=rows["frequency"] + (BrierRow(10, dates[10], 0.4),))),
            "shifted_model_keys": dataclasses.replace(good, method_rows=_rows(logistic=tuple(BrierRow(i + 1, dates[i + 1], 0.3) for i in indices))),
            "reordered_model_rows": dataclasses.replace(good, method_rows=_rows(frequency=tuple(reversed(rows["frequency"])))),
            "wrong_row_date": dataclasses.replace(good, method_rows=_rows(heuristic=(BrierRow(5, dates[6], 0.5),) + rows["heuristic"][1:])),
            "duplicate_keys": dataclasses.replace(good, requested_keys=duplicate_keys),
            "key_date_off_axis": dataclasses.replace(good, requested_keys=(RequestedKey(5, dates[6]),) + keys[1:]),
            "unknown_tail_key": dataclasses.replace(good, requested_keys=keys + (tail_key,)),
            "development_key": dataclasses.replace(good, requested_keys=(RequestedKey(4, dates[4]),) + keys),
            "gap_not_listed": dataclasses.replace(good, requested_keys=keys[:-1], method_rows={m: r[:-1] for m, r in rows.items()}),
            "listed_gap_is_requested": dataclasses.replace(good, union_gap_positions=(7,)),
            "gap_in_unknown_tail": dataclasses.replace(good, union_gap_positions=(10,)),
            "bool_gap": dataclasses.replace(good, union_gap_positions=(True,)),
            "unavailable_listing_bad_gap": dataclasses.replace(unavailable_dates, union_gap_positions=(7,)),
            "unavailable_with_rows": dataclasses.replace(unavailable_dates, method_rows=rows),
            "empty_with_text_rows": dataclasses.replace(
                good,
                requested_keys=(),
                comparison_status="empty",
                method_rows={"heuristic": "", "frequency": (), "logistic": ()},
                union_gap_positions=tuple(indices),
            ),
            "datetime_axis": dataclasses.replace(good, axis_dates=(datetime.datetime(2023, 1, 1),) + dates[1:]),
            "string_availability": dataclasses.replace(good, method_available={"heuristic": True, "frequency": 1, "logistic": True}),
            "unknown_status": dataclasses.replace(good, comparison_status=["scored"]),
        }
        for name, request in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(UncertaintyValidationError):
                    self._compute(request)

        for build in (
            lambda: RequestedKey(True, dates[5]),
            lambda: RequestedKey(5.0, dates[5]),
            lambda: BrierRow(5, dates[5], True),
            lambda: BrierRow(5, dates[5], "0.5"),
            lambda: BrierRow(5, dates[5], 10 ** 400),
            lambda: BrierRow(5, dates[5], float("inf")),
        ):
            with self.assertRaises(UncertaintyValidationError):
                build()

        # N/T/horizon boundary: the last mature origin is N-21, and N-20 is unknown tail
        last = RequestedKey(9, dates[9])
        self.assertEqual(self._compute(good).mature_span_count, 5)
        self.assertEqual(good.requested_keys[-1], last)

        # An all-gap mature span is empty, and a span with no mature origin needs no gaps
        all_gaps = dataclasses.replace(
            good,
            requested_keys=(),
            comparison_status="empty",
            method_rows={"heuristic": (), "frequency": (), "logistic": ()},
            union_gap_positions=tuple(indices),
        )
        self.assertEqual(self._compute(all_gaps).reason, REASON_EMPTY_COHORT)
        no_span = dataclasses.replace(all_gaps, test_start_index=10, union_gap_positions=())
        result = self._compute(no_span)
        self.assertEqual((result.reason, result.n, result.mature_span_count), (REASON_EMPTY_COHORT, 0, 0))

    def test_input_bytes_are_closed_canonical_and_never_coerced(self) -> None:
        """Every mutated document is re-encoded canonically, so only its content can reject it."""
        dates = self._make_axis_dates(25)
        keys, rows = self._make_keys_and_rows(dates, (0, 1, 2), [0.1, -0.0, 5e-324], [2.0, 0.5, 0.75], [0.25, 1.0, 0.0])
        req = UncertaintyRequest(
            axis_dates=dates,
            test_start_index=0,
            requested_keys=keys,
            comparison_status="scored",
            method_available={"heuristic": True, "frequency": True, "logistic": True},
            method_rows=rows,
            union_gap_positions=(3, 4),
        )
        raw = serialize_uncertainty_input(req)
        self.assertTrue(raw.endswith(b"}\n"))
        self.assertIn(b'"brier":-0.0', raw)
        self.assertIn(b'"brier":5e-324', raw)
        parsed = parse_uncertainty_input(raw)
        self.assertEqual(serialize_uncertainty_input(parsed), raw)
        self.assertEqual(parsed.method_rows["heuristic"][2].brier, 5e-324)
        self.assertEqual(math.copysign(1.0, parsed.method_rows["heuristic"][1].brier), -1.0)

        good = json.loads(raw.decode("ascii"))

        def _encode(doc: Dict[str, Any]) -> bytes:
            return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii") + b"\n"

        self.assertEqual(_encode(good), raw)

        row = lambda d: d["method_rows"]["heuristic"][0]  # noqa: E731
        cases: Dict[str, Callable[[Dict[str, Any]], None]] = {
            "unknown_root": lambda d: d.update(extra=1),
            "missing_root": lambda d: d.pop("method_available"),
            "wrong_schema": lambda d: d.update(schema_version="nivesh-uncertainty-input-v2"),
            "wrong_protocol": lambda d: d.update(protocol_id="other"),
            "unknown_key_field": lambda d: d["requested_keys"][0].update(extra=1),
            "unknown_row_field": lambda d: row(d).update(extra=1),
            "missing_row_field": lambda d: row(d).pop("brier"),
            "unknown_model": lambda d: d["method_rows"].update(other=[]),
            "missing_model": lambda d: d["method_rows"].pop("logistic"),
            "unknown_availability": lambda d: d["method_available"].update(other=True),
            "null_rows_while_scored": lambda d: d.update(method_rows=None),
            "extra_tail_row": lambda d: d["method_rows"]["logistic"].append(dict(d["method_rows"]["logistic"][-1])),
            "start_bool": lambda d: d.update(test_start_index=False),
            "start_float": lambda d: d.update(test_start_index=0.0),
            "start_text": lambda d: d.update(test_start_index="0"),
            "gap_float": lambda d: d.update(union_gap_positions=[3.0, 4]),
            "gap_bool": lambda d: d.update(union_gap_positions=[True, 4]),
            "gaps_not_list": lambda d: d.update(union_gap_positions="34"),
            "key_index_bool": lambda d: d["requested_keys"][1].update(origin_index=True),
            "key_index_float": lambda d: d["requested_keys"][0].update(origin_index=0.0),
            "row_index_text": lambda d: row(d).update(origin_index="0"),
            "brier_bool": lambda d: d["method_rows"]["logistic"][2].update(brier=False),
            "brier_text": lambda d: row(d).update(brier="0.1"),
            "brier_null": lambda d: row(d).update(brier=None),
            "brier_above_range": lambda d: row(d).update(brier=2.5),
            "availability_int": lambda d: d["method_available"].update(frequency=1),
            "availability_text": lambda d: d["method_available"].update(frequency="yes"),
            "status_list": lambda d: d.update(comparison_status=["scored"]),
            "compact_date": lambda d: d["axis_dates"].__setitem__(0, "20230101"),
            "impossible_date": lambda d: d["axis_dates"].__setitem__(1, "2023-02-30"),
            "date_number": lambda d: d["axis_dates"].__setitem__(0, 20230101),
            "keys_not_list": lambda d: d.update(requested_keys={}),
            "root_is_list": lambda d: d.clear(),
        }
        for name, mutate in cases.items():
            doc = copy.deepcopy(good)
            mutate(doc)
            with self.subTest(case=name):
                with self.assertRaises(UncertaintyValidationError):
                    parse_uncertainty_input(_encode(doc))
                with self.assertRaises(UncertaintyValidationError):
                    validate_uncertainty_input_document(doc)

        text = raw.decode("ascii")
        noncanonical = {
            "pretty": json.dumps(good, sort_keys=True, indent=2, ensure_ascii=True).encode("ascii") + b"\n",
            "unsorted": json.dumps(dict(reversed(list(good.items()))), separators=(",", ":"), ensure_ascii=True).encode("ascii") + b"\n",
            "no_final_lf": raw[:-1],
            "two_final_lf": raw + b"\n",
            "crlf": raw[:-1] + b"\r\n",
            "bom": b"\xef\xbb\xbf" + raw,
            "leading_space": b" " + raw,
            "number_spelling": text.replace('"brier":0.25', '"brier":0.250', 1).encode("ascii"),
            "not_utf8": b"\xff\xfe",
            "duplicate_key": raw.replace(b'{"axis_dates"', b'{"axis_dates":[],"axis_dates"', 1),
            "nan_token": raw.replace(b'"brier":0.25', b'"brier":NaN', 1),
        }
        for name, data in noncanonical.items():
            with self.subTest(case=name):
                self.assertNotEqual(data, raw)
                with self.assertRaises(UncertaintyValidationError):
                    parse_uncertainty_input(data)

    @staticmethod
    def _result_document(n: int, span: int, reason: Optional[str], cleared: Sequence[int], *, points: bool = True) -> Dict[str, Any]:
        """A closed block stated literally, so available states need no sampling."""
        views = []
        for L in (20, 40, 60):
            available = L in cleared
            views.append(
                {
                    "block_length": L,
                    "label": BLOCK_LENGTH_LABELS[L],
                    "status": "available" if available else "unavailable",
                    "reason": None if available else (reason or REASON_INSUFFICIENT_BLOCKS),
                    "seed": 20261103 + L,
                    "pairs": [
                        {"pair_id": pair, "lower": -0.25 if available else None, "upper": 0.5 if available else None}
                        for pair in ("heuristic_minus_frequency", "heuristic_minus_logistic")
                    ],
                }
            )
        status = {3: "available", 0: "unavailable"}.get(len(cleared), "partially_available")
        return {
            "protocol_id": UNCERTAINTY_PROTOCOL_ID,
            "method": UNCERTAINTY_METHOD,
            "status": status,
            "reason": reason,
            "n": n,
            "mature_span_count": span,
            "replicates": 10000,
            "nominal_coverage": 0.95,
            "quantile_rule": "linear_integer40_v1",
            "block_floor_factor": 10,
            "point_differences": [
                {"pair_id": pair, "point_difference": 0.125 if points else None}
                for pair in ("heuristic_minus_frequency", "heuristic_minus_logistic")
            ],
            "block_lengths": views,
        }

    def test_result_document_states_are_closed_and_coherent(self) -> None:
        valid = {
            "full": self._result_document(620, 620, None, (20, 40, 60)),
            "partial_l20": self._result_document(200, 200, None, (20,)),
            "partial_l40": self._result_document(400, 400, None, (20, 40)),
            "partial_top_of_l40": self._result_document(599, 599, None, (20, 40)),
            "floor": self._result_document(199, 199, REASON_INSUFFICIENT_BLOCKS, ()),
            "gap_above_floor": self._result_document(619, 620, REASON_NON_CONTIGUOUS, ()),
            "comparison_unavailable": self._result_document(620, 620, REASON_COMPARISON_UNAVAILABLE, (), points=False),
            "unavailable_without_rows": self._result_document(0, 0, REASON_COMPARISON_UNAVAILABLE, (), points=False),
            "empty": self._result_document(0, 5, REASON_EMPTY_COHORT, (), points=False),
            "empty_without_span": self._result_document(0, 0, REASON_EMPTY_COHORT, (), points=False),
        }
        for name, doc in valid.items():
            with self.subTest(valid=name):
                validate_uncertainty_result_document(doc)

        # A percentile interval need not contain the point, and signed zero is a real value
        outside = self._result_document(620, 620, None, (20, 40, 60))
        outside["point_differences"][0]["point_difference"] = 1.75
        outside["point_differences"][1]["point_difference"] = -0.0
        validate_uncertainty_result_document(outside)

        full = lambda: self._result_document(620, 620, None, (20, 40, 60))  # noqa: E731
        floor = lambda: self._result_document(199, 199, REASON_INSUFFICIENT_BLOCKS, ())  # noqa: E731
        gap = lambda: self._result_document(619, 620, REASON_NON_CONTIGUOUS, ())  # noqa: E731
        missing = lambda: self._result_document(620, 620, REASON_COMPARISON_UNAVAILABLE, (), points=False)  # noqa: E731

        def _set(doc: Dict[str, Any], **changes: Any) -> Dict[str, Any]:
            doc.update(changes)
            return doc

        def _view(doc: Dict[str, Any], pos: int, **changes: Any) -> Dict[str, Any]:
            doc["block_lengths"][pos].update(changes)
            return doc

        def _point(doc: Dict[str, Any], pos: int, value: Any) -> Dict[str, Any]:
            doc["point_differences"][pos]["point_difference"] = value
            return doc

        def _bound(doc: Dict[str, Any], key: str, value: Any) -> Dict[str, Any]:
            doc["block_lengths"][0]["pairs"][0][key] = value
            return doc

        contradictions = {
            "top_available_lengths_unavailable": _set(floor(), status="available", reason=None),
            "top_partial_lengths_unavailable": _set(floor(), status="partially_available", reason=None),
            "top_unavailable_length_available": _set(full(), status="unavailable", reason=REASON_INSUFFICIENT_BLOCKS),
            "top_available_one_length_unavailable": _set(self._result_document(400, 400, None, (20, 40)), status="available"),
            "top_partial_all_available": _set(full(), status="partially_available"),
            "available_top_reason": _set(full(), reason=REASON_INSUFFICIENT_BLOCKS),
            "unknown_top_reason": _set(floor(), reason="comparison unavailable"),
            "numeric_top_reason": _set(floor(), reason=1),
            "null_unavailable_reason": _set(floor(), reason=None),
            "length_reason_on_available": _view(full(), 0, reason="x"),
            "unknown_length_reason": _view(floor(), 0, reason="x"),
            "null_length_reason": _view(floor(), 1, reason=None),
            "length_reason_differs_from_common": _view(gap(), 2, reason=REASON_INSUFFICIENT_BLOCKS),
            "floor_reason_on_common_state": _view(missing(), 0, reason=REASON_EMPTY_COHORT),
            "l60_available_below_floor": self._result_document(100, 100, None, (20, 40, 60)),
            "l20_unavailable_above_floor": self._result_document(200, 200, REASON_INSUFFICIENT_BLOCKS, ()),
            "l60_unavailable_at_floor": self._result_document(600, 600, None, (20, 40)),
            "partial_skips_a_length": self._result_document(400, 400, None, (20, 60)),
            "floor_with_gapped_count": self._result_document(199, 200, REASON_INSUFFICIENT_BLOCKS, ()),
            "available_with_gapped_count": self._result_document(620, 621, None, (20, 40, 60)),
            "available_at_zero": self._result_document(0, 0, None, (20, 40, 60)),
            "gap_without_gap": self._result_document(620, 620, REASON_NON_CONTIGUOUS, ()),
            "gap_with_empty_cohort": self._result_document(0, 620, REASON_NON_CONTIGUOUS, ()),
            "empty_with_rows": self._result_document(3, 5, REASON_EMPTY_COHORT, (), points=False),
            "n_above_span": self._result_document(6, 5, REASON_COMPARISON_UNAVAILABLE, (), points=False),
            "null_point_while_available": _point(full(), 0, None),
            "null_point_at_floor": _point(floor(), 1, None),
            "null_point_on_gap": _point(gap(), 0, None),
            "point_on_comparison_unavailable": _point(missing(), 0, 0.0),
            "point_on_empty": _point(self._result_document(0, 5, REASON_EMPTY_COHORT, (), points=False), 1, 0.0),
            "point_outside_range": _point(full(), 0, 2.5),
            "bound_outside_range": _bound(full(), "upper", 2.5),
            "inverted_bounds": _bound(full(), "lower", 0.75),
            "missing_bound": _bound(full(), "lower", None),
            "bound_on_unavailable": _bound(floor(), "lower", 0.0),
            "float_block_length": _view(full(), 0, block_length=20.0),
            "float_seed": _view(full(), 0, seed=20261123.0),
            "float_n": _set(full(), n=620.0),
            "bool_n": _set(self._result_document(1, 1, REASON_INSUFFICIENT_BLOCKS, ()), n=True),
            "int_coverage": _set(full(), nominal_coverage=1),
            "extra_view_key": _view(full(), 0, extra=1),
        }
        for name, doc in contradictions.items():
            with self.subTest(contradiction=name):
                with self.assertRaises(UncertaintyValidationError):
                    validate_uncertainty_result_document(doc)

        # Malformed values must be a domain error, not a raw TypeError or OverflowError
        malformed = {
            "list_status": _set(full(), status=[]),
            "object_status": _set(full(), status={}),
            "huge_point": _point(full(), 0, 10 ** 400),
            "huge_lower": _bound(full(), "lower", 10 ** 400),
            "huge_upper": _bound(full(), "upper", -(10 ** 400)),
            "list_length_status": _view(full(), 0, status=[]),
            "list_reason": _set(floor(), reason=[]),
            "object_length_reason": _view(floor(), 0, reason={}),
            "huge_n": _set(full(), n=10 ** 400),
            "huge_coverage": _set(full(), nominal_coverage=10 ** 400),
        }
        for name, doc in malformed.items():
            with self.subTest(malformed=name):
                with self.assertRaises(UncertaintyValidationError):
                    validate_uncertainty_result_document(doc)

    @staticmethod
    def _diagnostics_document() -> Dict[str, Any]:
        """L20 and L40 available at n=400, L60 unused. No sampling: every counter is literal."""
        used = {"replicates_completed": 10000, "sampled_positions": 4000000, "random_calls": 3990000}
        return {
            "schema_version": SCHEMA_VERSION_UNCERTAINTY_DIAGNOSTICS,
            "protocol_id": UNCERTAINTY_PROTOCOL_ID,
            "input_identity": {"raw_byte_count": 100, "sha256": "A" * 64},
            "runtime_identity": dict(TEST_RUNTIME, rng_api="python.random.Random/randrange/random on pinned runtime"),
            "resource": {"max_resample_positions": 30000000, "required_positions": 8000000, "visited_positions": 8000000},
            "lengths": [
                dict(used, block_length=20, seed=20261123, randrange_calls=209500, index_stream_sha256="B" * 64),
                dict(used, block_length=40, seed=20261143, randrange_calls=109750, index_stream_sha256="C" * 64),
                {
                    "block_length": 60,
                    "seed": 20261163,
                    "replicates_completed": 0,
                    "sampled_positions": 0,
                    "random_calls": 0,
                    "randrange_calls": 0,
                    "index_stream_sha256": None,
                },
            ],
        }

    def test_diagnostics_document_counters_are_coherent(self) -> None:
        validate_uncertainty_diagnostics_document(self._diagnostics_document())

        def _length(pos: int, **changes: Any) -> Callable[[Dict[str, Any]], None]:
            return lambda d: d["lengths"][pos].update(changes)

        def _resource(**changes: Any) -> Callable[[Dict[str, Any]], None]:
            return lambda d: d["resource"].update(changes)

        cases: Dict[str, Callable[[Dict[str, Any]], None]] = {
            "unknown_root": lambda d: d.update(extra=1),
            "runtime_blank": lambda d: d["runtime_identity"].update(python_version=""),
            "runtime_number": lambda d: d["runtime_identity"].update(python_implementation=3),
            "rng_label": lambda d: d["runtime_identity"].update(rng_api="other"),
            "identity_bool": lambda d: d["input_identity"].update(raw_byte_count=True),
            "identity_hash": lambda d: d["input_identity"].update(sha256="x"),
            "required_differs": _resource(required_positions=7999999),
            "visited_differs": _resource(visited_positions=7999999),
            "required_above_cap": _resource(max_resample_positions=7999999),
            "cap_zero": _resource(max_resample_positions=0),
            "cap_above_ceiling": _resource(max_resample_positions=30000001),
            "cap_bool": _resource(max_resample_positions=True),
            "partial_replicates": _length(0, replicates_completed=9999),
            "sampled_not_multiple": _length(0, sampled_positions=4000001),
            "random_calls_short": _length(0, random_calls=3989999),
            "randrange_below_initial": _length(0, randrange_calls=9999),
            "randrange_above_possible": _length(0, randrange_calls=4000001),
            "fingerprint_missing": _length(0, index_stream_sha256=None),
            "fingerprint_lower": _length(0, index_stream_sha256="b" * 64),
            "fingerprint_short": _length(0, index_stream_sha256="B"),
            "unused_sampled": _length(2, sampled_positions=1),
            "unused_random": _length(2, random_calls=1),
            "unused_randrange": _length(2, randrange_calls=1),
            "unused_fingerprint": _length(2, index_stream_sha256="D" * 64),
            "float_block_length": _length(0, block_length=20.0),
            "float_seed": _length(0, seed=20261123.0),
            "bool_counter": _length(2, random_calls=False),
            "wrong_seed": _length(1, seed=20261123),
        }
        for name, mutate in cases.items():
            doc = self._diagnostics_document()
            mutate(doc)
            with self.subTest(case=name):
                with self.assertRaises(UncertaintyValidationError):
                    validate_uncertainty_diagnostics_document(doc)

    def test_serialization_and_document_validation(self) -> None:
        """
        Validates canonical compact ASCII serialization of uncertainty-input.json and
        roundtrip parsing and document validation.
        """
        dates = self._make_axis_dates(25)
        keys, rows = self._make_keys_and_rows(dates, (0, 1, 2), [0.1, 0.2, 0.3], [0.4, 0.5, 0.6], [0.7, 0.8, 0.9])
        req = UncertaintyRequest(
            axis_dates=dates,
            test_start_index=0,
            requested_keys=keys,
            comparison_status="scored",
            method_available={"heuristic": True, "frequency": True, "logistic": True},
            method_rows=rows,
            union_gap_positions=(3, 4),
        )

        raw = serialize_uncertainty_input(req)
        # Check strict format: compact ASCII, ending with single \n
        self.assertTrue(raw.endswith(b"\n"))
        self.assertNotIn(b" ", raw)
        self.assertNotIn(b"\r", raw)

        parsed_req = parse_uncertainty_input(raw)
        self.assertEqual(parsed_req.test_start_index, req.test_start_index)
        self.assertEqual(len(parsed_req.requested_keys), len(req.requested_keys))
        self.assertEqual(parsed_req.comparison_status, req.comparison_status)

        # Test validation of input doc
        doc = build_uncertainty_input_document(req)
        validate_uncertainty_input_document(doc)

        # Set input_identity with exact raw bytes and hash
        raw_hash = hashlib.sha256(raw).hexdigest().upper()
        req_with_id = UncertaintyRequest(
            axis_dates=dates,
            test_start_index=0,
            requested_keys=keys,
            comparison_status="scored",
            method_available={"heuristic": True, "frequency": True, "logistic": True},
            method_rows=rows,
            union_gap_positions=(3, 4),
            input_identity={"raw_byte_count": len(raw), "sha256": raw_hash},
        )

        # Test validation of diagnostics doc
        res = self._compute(req_with_id)
        self.assertIsNotNone(res.diagnostics)
        diag_doc = build_uncertainty_diagnostics_document(res.diagnostics)
        validate_uncertainty_diagnostics_document(diag_doc)

        # Test validation of statistical uncertainty result doc
        res_doc = uncertainty_result_to_document(res)
        validate_uncertainty_result_document(res_doc)

    def test_public_n400_oracle(self) -> None:
        """
        Public n=400 fixed-protocol oracle case:
          - N = 440, T = 20 -> mature span [20, 420) has length 400.
          - n = 400 clears L20 and L40, but not L60 (floor 600).
          - Required positions = 10000 * 400 * 2 = 8,000,000.
          - Transparent recording proxy observes:
              - Available L20 and L40 seeds: LITERAL 20261123, 20261143
              - Exactly one local construction per length
              - Exactly 10000 initial randrange calls per length, told from restart calls by the
                draw before them: a restart directly follows a U below 1/L
              - Exactly 3990000 direct random() calls per length
          - Run twice (16M total positions) to verify deterministic reproduction and ledger.
        """
        class RecordingRandomProxy:
            def __init__(self, seed: int):
                self.seed = seed
                self.native_rng = random.Random(seed)
                self.restart_threshold = 1.0 / (seed - 20261103)
                self.random_calls = 0
                self.randrange_calls = 0
                self.initial_calls = 0
                self.restart_calls = 0
                self.below_threshold = 0
                self.last_u_restarts = False
                self.randoms_since_initial = 0
                self.initial_positions_ok = True

            def random(self) -> float:
                self.random_calls += 1
                self.randoms_since_initial += 1
                value = self.native_rng.random()
                self.last_u_restarts = value < self.restart_threshold
                self.below_threshold += self.last_u_restarts
                return value

            def randrange(self, stop: int) -> int:
                self.randrange_calls += 1
                if self.last_u_restarts:
                    self.restart_calls += 1
                else:
                    self.initial_calls += 1
                    # A replicate of 400 positions draws 399 U values between its initial calls
                    self.initial_positions_ok &= self.randoms_since_initial in (0, 399)
                    self.randoms_since_initial = 0
                self.last_u_restarts = False
                return self.native_rng.randrange(stop)

        recorded_proxies: List[RecordingRandomProxy] = []

        def recording_factory(seed: int) -> RecordingRandomProxy:
            proxy = RecordingRandomProxy(seed)
            recorded_proxies.append(proxy)
            return proxy

        dates = self._make_axis_dates(440)
        indices = list(range(20, 420))
        # Constant losses give point differences 0.0 and known intervals [0.0, 0.0]
        keys, rows = self._make_keys_and_rows(
            dates, indices, [0.5] * 400, [0.5] * 400, [0.5] * 400
        )
        fake_sha = "B" * 64
        req = UncertaintyRequest(
            axis_dates=dates,
            test_start_index=20,
            requested_keys=keys,
            comparison_status="scored",
            method_available={"heuristic": True, "frequency": True, "logistic": True},
            method_rows=rows,
            union_gap_positions=(),
            input_identity={"raw_byte_count": 1234, "sha256": fake_sha},
        )

        required_pos = BOOTSTRAP_REPLICATES * 400 * 2  # 8,000,000

        # Phase 1: Reserve budget before Run 1
        _reserve_sampling_budget("test_public_n400_oracle_run1", required_pos, budget=20000000)

        random.seed(20260101)
        global_state = random.getstate()

        # Run 1
        res1 = self._compute(req, MAX_RESAMPLE_POSITIONS, rng_factory=recording_factory)

        # Phase 2: Complete reservation after observing Run 1 evidence
        self.assertIsNotNone(res1.diagnostics)
        observed1 = sum(d.sampled_positions for d in res1.diagnostics.lengths)
        _complete_sampling_call("test_public_n400_oracle_run1", observed1)

        # Verify proxy call observations
        self.assertEqual(len(recorded_proxies), 2)  # Only L20 and L40 constructed!
        p20, p40 = recorded_proxies

        self.assertEqual(p20.seed, 20261123)
        self.assertEqual(p40.seed, 20261143)

        # Direct API calls count
        self.assertEqual(p20.random_calls, 3990000)  # 10000 * 399
        self.assertEqual(p40.random_calls, 3990000)

        # Total randrange includes restarts, so initial calls are observed apart from them
        for proxy, diagnostics in ((p20, res1.diagnostics.lengths[0]), (p40, res1.diagnostics.lengths[1])):
            self.assertEqual(proxy.initial_calls, 10000)
            self.assertTrue(proxy.initial_positions_ok)
            self.assertEqual(proxy.restart_calls, proxy.below_threshold)
            self.assertGreater(proxy.restart_calls, 0)
            self.assertEqual(proxy.randrange_calls, 10000 + proxy.restart_calls)
            self.assertEqual(diagnostics.randrange_calls, proxy.randrange_calls)
        self.assertNotEqual(p20.restart_calls, p40.restart_calls)

        # The bootstrap owns local RNGs only: the caller's global stream does not move
        self.assertEqual(random.getstate(), global_state)

        # Verify result statuses
        self.assertEqual(res1.status, UNCERTAINTY_STATUS_PARTIALLY_AVAILABLE)
        self.assertIsNone(res1.reason)
        self.assertEqual(res1.block_lengths[0].status, UNCERTAINTY_STATUS_AVAILABLE)
        self.assertEqual(res1.block_lengths[1].status, UNCERTAINTY_STATUS_AVAILABLE)
        self.assertEqual(res1.block_lengths[2].status, UNCERTAINTY_STATUS_UNAVAILABLE)
        self.assertEqual(res1.block_lengths[2].reason, REASON_INSUFFICIENT_BLOCKS)

        # Equal losses give exactly 0.0 endpoints
        self.assertAlmostEqual(res1.block_lengths[0].pairs[0].lower, 0.0, places=12)
        self.assertAlmostEqual(res1.block_lengths[0].pairs[0].upper, 0.0, places=12)

        # Diagnostics counters
        self.assertIsNotNone(res1.diagnostics)
        d20 = res1.diagnostics.lengths[0]
        self.assertEqual(d20.replicates_completed, 10000)
        self.assertEqual(d20.sampled_positions, 4000000)
        self.assertEqual(d20.random_calls, 3990000)
        self.assertIsNotNone(d20.index_stream_sha256)

        d60 = res1.diagnostics.lengths[2]
        self.assertEqual(d60.replicates_completed, 0)
        self.assertEqual(d60.sampled_positions, 0)
        self.assertIsNone(d60.index_stream_sha256)

        # Run 2: semantic repeat (8M + 8M = 16M <= 20M budget)
        _reserve_sampling_budget("test_public_n400_oracle_run2", required_pos, budget=20000000)
        recorded_proxies.clear()
        res2 = self._compute(req, MAX_RESAMPLE_POSITIONS, rng_factory=recording_factory)

        # Phase 2: Complete reservation after observing Run 2 evidence
        self.assertIsNotNone(res2.diagnostics)
        observed2 = sum(d.sampled_positions for d in res2.diagnostics.lengths)
        _complete_sampling_call("test_public_n400_oracle_run2", observed2)

        # Verify deterministic match across repeat
        self.assertEqual(res1.block_lengths[0].pairs[0].lower, res2.block_lengths[0].pairs[0].lower)
        self.assertEqual(res1.block_lengths[0].pairs[0].upper, res2.block_lengths[0].pairs[0].upper)
        self.assertEqual(
            res1.diagnostics.lengths[0].index_stream_sha256,
            res2.diagnostics.lengths[0].index_stream_sha256,
        )

    def test_ledger_budget_overflow_refused(self) -> None:
        """Ledger helper enforces cumulative budget before work; overflow is rejected."""
        with tempfile.TemporaryDirectory() as td:
            ledger_file = Path(td) / "ledger.json"
            _reserve_sampling_budget("call1", 60, budget=100, ledger_path_override=ledger_file)
            _complete_sampling_call("call1", 60, ledger_path_override=ledger_file, budget=100)
            with self.assertRaises(RuntimeError) as cm:
                _reserve_sampling_budget("call2", 50, budget=100, ledger_path_override=ledger_file)
            self.assertIn("Gate sampling budget exceeded", str(cm.exception))
            data = json.loads(ledger_file.read_text(encoding="utf-8"))
            self.assertEqual(data["total_reserved_positions"], 60)
            self.assertEqual(len(data["calls"]), 1)

    def test_ledger_inconsistent_existing_state_is_refused_before_admission(self) -> None:
        """Parseable but unaccountable ledgers fail closed, with no new work admitted or written."""
        good_call = {
            "call_id": "c1",
            "test_name": "c1",
            "test_id": "c1",
            "required_positions": 60,
            "reserved_positions": 60,
            "visited_positions": 60,
            "status": "completed",
            "reserved_at": "2026-11-06T00:00:00+00:00",
        }
        open_call = dict(good_call, call_id="c2", visited_positions="unknown", status="incomplete")

        def _ledger(calls: List[Dict[str, Any]], reserved: Any, visited: Any, budget: Any = 100) -> Dict[str, Any]:
            return {"gate_budget": budget, "calls": calls, "total_reserved_positions": reserved, "total_visited_positions": visited}

        self.assertEqual(_ledger([good_call], 60, 60)["gate_budget"], 100)
        cases: Dict[str, Any] = {
            "declared_zero_with_calls": _ledger([good_call], 0, 60),
            "declared_above_calls": _ledger([good_call], 90, 60),
            "visited_total_differs": _ledger([good_call], 60, 0),
            "budget_differs": _ledger([good_call], 60, 60, 200),
            "budget_bool": _ledger([good_call], 60, 60, True),
            "reserved_float": _ledger([good_call], 60.0, 60),
            "reserved_bool": _ledger([], False, 0),
            "reserved_negative": _ledger([], -1, 0),
            "reserved_text": _ledger([], "0", 0),
            "calls_not_list": _ledger({}, 0, 0),
            "call_not_object": _ledger(["c1"], 0, 0),
            "call_field_missing": _ledger([{k: v for k, v in good_call.items() if k != "reserved_positions"}], 60, 60),
            "call_count_float": _ledger([dict(good_call, reserved_positions=60.0)], 60, 60),
            "call_count_bool": _ledger([dict(good_call, required_positions=True)], 60, 60),
            "call_count_negative": _ledger([dict(good_call, reserved_positions=-60)], -60, 60),
            "completed_unknown": _ledger([dict(good_call, visited_positions="unknown")], 60, 0),
            "incomplete_with_count": _ledger([dict(open_call, visited_positions=60)], 60, 0),
            "unknown_status": _ledger([dict(good_call, status="done")], 60, 60),
            "already_over_budget": _ledger([dict(good_call, reserved_positions=101, visited_positions=101)], 101, 101),
            "unknown_root_key": dict(_ledger([good_call], 60, 60), extra=1),
            "missing_root_key": {"gate_budget": 100, "calls": []},
            "root_not_object": [],
        }
        with tempfile.TemporaryDirectory() as td:
            for name, doc in cases.items():
                ledger_file = Path(td) / f"{name}.json"
                text = json.dumps(doc)
                ledger_file.write_text(text, encoding="utf-8")
                with self.subTest(case=name):
                    with self.assertRaises(RuntimeError):
                        _reserve_sampling_budget("new", 10, budget=100, ledger_path_override=ledger_file)
                    with self.assertRaises(RuntimeError):
                        _complete_sampling_call("c2", 10, ledger_path_override=ledger_file, budget=100)
                    self.assertEqual(ledger_file.read_text(encoding="utf-8"), text)

            # Controls: the same shapes that account exactly are admitted
            ledger_file = Path(td) / "valid.json"
            ledger_file.write_text(json.dumps(_ledger([good_call, open_call], 120, 60, 200)), encoding="utf-8")
            _reserve_sampling_budget("new", 10, budget=200, ledger_path_override=ledger_file)
            data = json.loads(ledger_file.read_text(encoding="utf-8"))
            self.assertEqual(data["total_reserved_positions"], 130)
            self.assertEqual(data["calls"][-1]["visited_positions"], "unknown")
            self.assertEqual(data["calls"][-1]["status"], "incomplete")

            # Completion needs an observed native count and an open call of that name
            for bad_visited in (True, 1.5, "10", -1):
                with self.assertRaises(RuntimeError):
                    _complete_sampling_call("new", bad_visited, ledger_path_override=ledger_file, budget=200)
            with self.assertRaises(RuntimeError):
                _complete_sampling_call("absent", 10, ledger_path_override=ledger_file, budget=200)

    def test_ledger_corrupt_file_rejected(self) -> None:
        """Ledger helper rejects corrupt JSON rather than silently resetting."""
        with tempfile.TemporaryDirectory() as td:
            ledger_file = Path(td) / "ledger.json"
            ledger_file.write_text("{corrupt json", encoding="utf-8")
            with self.assertRaises(RuntimeError) as cm:
                _reserve_sampling_budget("call1", 10, budget=100, ledger_path_override=ledger_file)
            self.assertIn("Corrupt sampling ledger JSON", str(cm.exception))

    def test_ledger_two_phase_lifecycle(self) -> None:
        """Ledger helper tracks incomplete reservation before work and completed only after evidence."""
        with tempfile.TemporaryDirectory() as td:
            ledger_file = Path(td) / "ledger.json"
            _reserve_sampling_budget("c_alpha", 500, budget=1000, ledger_path_override=ledger_file)
            d1 = json.loads(ledger_file.read_text(encoding="utf-8"))
            self.assertEqual(d1["total_reserved_positions"], 500)
            self.assertEqual(d1["total_visited_positions"], 0)
            self.assertEqual(len(d1["calls"]), 1)
            c1 = d1["calls"][0]
            self.assertEqual(c1["call_id"], "c_alpha")
            self.assertEqual(c1["status"], "incomplete")
            self.assertEqual(c1["visited_positions"], "unknown")

            _complete_sampling_call("c_alpha", 500, ledger_path_override=ledger_file, budget=1000)
            d2 = json.loads(ledger_file.read_text(encoding="utf-8"))
            self.assertEqual(d2["total_reserved_positions"], 500)
            self.assertEqual(d2["total_visited_positions"], 500)
            c2 = d2["calls"][0]
            self.assertEqual(c2["status"], "completed")
            self.assertEqual(c2["visited_positions"], 500)


if __name__ == "__main__":
    unittest.main()
