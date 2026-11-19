"""
Prediction Evaluation Replay Export.

Provides deterministic, standard-library serialization of origin-time FeatureSeries
into the wire JSON specification (nivesh-replay-input-v1) consumed by the offline
Node.js replay CLI (replay.cjs).

Architectural ownership:
    inputs.py owns raw CSV loading, validation, and date alignment.
    outcomes.py owns future-label timing and exact classification (+/-0.5%).
    features.py owns origin-time feature construction and regime classification.
    replay_export.py owns typed FeatureSeries serialization to wire JSON bytes.

Execution boundary:
    Operates strictly in memory with zero file, network, subprocess, or model access.
    Constructs and validates the complete wire document before returning UTF-8 bytes.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
import json
import math
import re
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from research.prediction_eval.inputs import (
    FileProvenance,
    InputValidationError,
)
from research.prediction_eval.features import (
    FeatureSeries,
    NiftyFeatureRecord,
    PredictorPayload,
    PROTOCOL_ID as FEATURES_PROTOCOL_ID,
    VALID_REGIMES,
    REASON_WARMUP,
    REASON_MISSING_VIX,
)

SCHEMA_VERSION: str = "nivesh-replay-input-v1"
FEATURE_PROTOCOL: str = "nifty-close-features-v1"
SERIES_ID: str = "^NSEI"
ASSET: str = "^NSEI"
HORIZON: str = "20D"
VARIANT: str = "frozen-current-core-market-data-only-v1"

VALID_CALENDAR_STATUSES: Set[str] = {
    "not_checked",
    "matches_supplied_sessions",
    "mismatch",
}

_PLAIN_DECIMAL_REGEX = re.compile(r"^\d+(\.\d+)?$")
_SHA256_HEX_REGEX = re.compile(r"\A[0-9A-Fa-f]{64}\Z")
_ACQUISITION_TIME_REGEX = re.compile(
    r"^(\d{4}-\d{2}-\d{2})T(0[0-9]|1[0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](\.\d{1,6})?(Z|[+-](0[0-9]|1[0-9]|2[0-3]):[0-5][0-9])?$"
)

SAFE_INTEGER_MAX: int = 9007199254740991  # 2^53 - 1


def _validate_clean_string(val: Any, field_name: str) -> str:
    """Validates that a field is a string and contains no unencodable surrogates."""
    if not isinstance(val, str):
        raise InputValidationError(
            f"Field '{field_name}' must be a string, got {type(val).__name__}",
            field=field_name,
            reason=f"Expected str, got {type(val).__name__}",
        )
    try:
        val.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise InputValidationError(
            f"Field '{field_name}' contains unencodable characters (surrogates): {exc}",
            field=field_name,
            reason=f"Unencodable text in {field_name}",
        ) from exc
    return val


def _format_decimal(val: Any, field_name: str, origin_index: Optional[int] = None) -> str:
    """
    Formats a strictly positive Decimal object as a plain fixed-point string.

    Preserves stored scale and value without float conversion, context-dependent
    rounding, or fractional-scale normalization. Positive exponents are represented
    in equivalent plain decimal notation without scientific exponent syntax.
    """
    row_ctx = f" at row {origin_index}" if origin_index is not None else ""
    if isinstance(val, bool) or not isinstance(val, Decimal):
        raise InputValidationError(
            f"Field '{field_name}'{row_ctx} must be a Decimal, got {type(val).__name__}",
            field=field_name,
            reason=f"Expected Decimal, got {type(val).__name__}",
        )
    if not val.is_finite() or val <= 0:
        raise InputValidationError(
            f"Field '{field_name}'{row_ctx} must be a finite strictly positive Decimal, got {val}",
            field=field_name,
            reason=f"Nonpositive or nonfinite Decimal: {val}",
        )

    sign, digits, exp = val.as_tuple()
    if sign != 0 or not any(digits):
        raise InputValidationError(
            f"Field '{field_name}'{row_ctx} must be strictly positive, got {val}",
            field=field_name,
            reason=f"Nonpositive Decimal: {val}",
        )

    digits_str = "".join(str(d) for d in digits)
    if exp >= 0:
        formatted = digits_str + ("0" * exp)
    else:
        num_digits = len(digits_str)
        neg_exp = -exp
        if neg_exp < num_digits:
            formatted = digits_str[:-neg_exp] + "." + digits_str[-neg_exp:]
        else:
            formatted = "0." + ("0" * (neg_exp - num_digits)) + digits_str

    if not _PLAIN_DECIMAL_REGEX.match(formatted):
        raise InputValidationError(
            f"Formatted decimal '{formatted}' for '{field_name}'{row_ctx} does not match plain positive decimal syntax",
            field=field_name,
            reason=f"Invalid plain decimal representation: '{formatted}'",
        )

    # Reject all-zero decimal strings (e.g. "0.00")
    parts = formatted.split(".")
    if all(set(p) == {"0"} for p in parts):
        raise InputValidationError(
            f"Field '{field_name}'{row_ctx} must be strictly positive, got all-zero string '{formatted}'",
            field=field_name,
            reason="All-zero decimal string",
        )

    return formatted


def _validate_and_format_date(
    d: Any,
    field_name: str,
    origin_index: Optional[int] = None,
) -> str:
    """Validates and formats a Gregorian date string within years 0001-9999."""
    row_ctx = f" at row {origin_index}" if origin_index is not None else ""
    if isinstance(d, datetime.datetime) or not isinstance(d, datetime.date):
        raise InputValidationError(
            f"Field '{field_name}'{row_ctx} must be datetime.date (not datetime), got {type(d).__name__}",
            field=field_name,
            reason=f"Expected datetime.date, got {type(d).__name__}",
        )
    if not (1 <= d.year <= 9999):
        raise InputValidationError(
            f"Field '{field_name}'{row_ctx} year {d.year} is outside valid Gregorian range 0001-9999",
            field=field_name,
            reason=f"Invalid Gregorian year: {d.year}",
        )
    return d.isoformat()


def _validate_safe_integer(val: Any, field_name: str) -> int:
    """Validates a nonnegative safe integer matching IEEE 754 safe bounds (0..2^53-1)."""
    if isinstance(val, bool) or not isinstance(val, int):
        raise InputValidationError(
            f"Field '{field_name}' must be an integer, got {type(val).__name__}",
            field=field_name,
            reason=f"Expected int, got {type(val).__name__}",
        )
    if val < 0 or val > SAFE_INTEGER_MAX:
        raise InputValidationError(
            f"Field '{field_name}' must be a nonnegative safe integer (0..{SAFE_INTEGER_MAX}), got {val}",
            field=field_name,
            reason=f"Integer {val} out of safe bounds [0, {SAFE_INTEGER_MAX}]",
        )
    return val


def _validate_numeric_predictor(val: Any, field_name: str, origin_index: int) -> float:
    """
    Validates a numeric predictor field, ensuring finite IEEE binary64 representation.

    Rejects booleans, non-numeric types, nonfinite numbers, and integers that cannot
    be represented exactly in binary64 without precision loss.
    """
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        raise InputValidationError(
            f"Predictor '{field_name}' at row {origin_index} must be numeric, got {type(val).__name__}",
            field=field_name,
            reason=f"Expected float or exact int, got {type(val).__name__}",
        )
    if isinstance(val, int):
        try:
            flt_val = float(val)
        except OverflowError as exc:
            raise InputValidationError(
                f"Integer predictor '{field_name}' at row {origin_index} exceeds the finite binary64 range",
                field=field_name,
                reason="Integer too large for binary64 conversion",
            ) from exc
        if int(flt_val) != val:
            raise InputValidationError(
                f"Integer predictor '{field_name}' at row {origin_index} ({val}) cannot be represented exactly in binary64",
                field=field_name,
                reason="Inexact integer to binary64 conversion",
            )
        return flt_val

    if not math.isfinite(val):
        raise InputValidationError(
            f"Predictor '{field_name}' at row {origin_index} must be finite, got {val}",
            field=field_name,
            reason=f"Nonfinite float: {val}",
        )
    return float(val)


def _format_acquisition_time(dt: Any, field_name: str) -> Optional[str]:
    """
    Formats caller-declared acquisition datetime to wire acquisition_time grammar.

    Supports ISO seconds, optional 1-6 microsecond digits, and optional Z or minute-offset.
    Naive datetimes are preserved as timezone-unknown (no offset). Sub-minute offsets are rejected.
    """
    if dt is None:
        return None
    if not isinstance(dt, datetime.datetime):
        raise InputValidationError(
            f"Field '{field_name}' must be datetime.datetime or None, got {type(dt).__name__}",
            field=field_name,
            reason=f"Expected datetime.datetime, got {type(dt).__name__}",
        )
    if not (1 <= dt.year <= 9999):
        raise InputValidationError(
            f"Field '{field_name}' year {dt.year} is outside valid Gregorian range 0001-9999",
            field=field_name,
            reason=f"Invalid Gregorian year: {dt.year}",
        )

    base_time = (
        f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}T"
        f"{dt.hour:02d}:{dt.minute:02d}:{dt.second:02d}"
    )
    if dt.microsecond > 0:
        base_time += f".{dt.microsecond:06d}"

    if dt.tzinfo is None:
        formatted = base_time
    else:
        offset = dt.utcoffset()
        if offset is None:
            formatted = base_time
        else:
            total_seconds = offset.total_seconds()
            int_seconds = int(total_seconds)
            if total_seconds != int_seconds or int_seconds % 60 != 0:
                raise InputValidationError(
                    f"Field '{field_name}' contains unsupported sub-minute timezone offset ({total_seconds}s)",
                    field=field_name,
                    reason=f"Sub-minute offset: {total_seconds}s",
                )
            total_minutes = int_seconds // 60
            if not (-1439 <= total_minutes <= 1439):
                raise InputValidationError(
                    f"Field '{field_name}' timezone offset ({total_minutes}m) exceeds 24-hour range",
                    field=field_name,
                    reason=f"Offset out of bounds: {total_minutes}m",
                )
            sign = "+" if total_minutes >= 0 else "-"
            abs_mins = abs(total_minutes)
            hours = abs_mins // 60
            mins = abs_mins % 60
            offset_str = f"{sign}{hours:02d}:{mins:02d}"
            formatted = base_time + offset_str

    if not _ACQUISITION_TIME_REGEX.match(formatted):
        raise InputValidationError(
            f"Field '{field_name}' formatted timestamp '{formatted}' does not match acquisition grammar",
            field=field_name,
            reason=f"Regex match failure for timestamp: {formatted}",
        )
    return formatted


def _serialize_file_provenance(
    provenance_seq: Sequence[Any],
    label: str,
) -> List[Dict[str, Any]]:
    """Serializes and validates a sequence of FileProvenance objects to wire format."""
    if not isinstance(provenance_seq, (list, tuple)):
        raise InputValidationError(
            f"Provenance field '{label}' must be a sequence, got {type(provenance_seq).__name__}",
            field=label,
            reason=f"Expected sequence, got {type(provenance_seq).__name__}",
        )

    out: List[Dict[str, Any]] = []
    for idx, p in enumerate(provenance_seq):
        item_label = f"{label}[{idx}]"
        if not isinstance(p, FileProvenance):
            raise InputValidationError(
                f"Provenance item {item_label} must be FileProvenance, got {type(p).__name__}",
                field=item_label,
                reason=f"Expected FileProvenance, got {type(p).__name__}",
            )

        file_path_str = _validate_clean_string(p.file_path, f"{item_label}.file_path")

        raw_bytes = _validate_safe_integer(p.raw_byte_count, f"{item_label}.raw_byte_count")

        if not isinstance(p.sha256, str) or not _SHA256_HEX_REGEX.fullmatch(p.sha256):
            raise InputValidationError(
                f"Field '{item_label}.sha256' must be a 64-hexadecimal string, got {p.sha256!r}",
                field=f"{item_label}.sha256",
                reason=f"Invalid SHA256 hex string: {p.sha256!r}",
            )

        rec_count = _validate_safe_integer(p.record_count, f"{item_label}.record_count")

        if rec_count == 0:
            if p.observed_first_date is not None or p.observed_last_date is not None:
                raise InputValidationError(
                    f"{item_label}: observed dates must be null when record_count is 0",
                    field=item_label,
                    reason="Non-null observed dates with record_count 0",
                )
            first_date_str: Optional[str] = None
            last_date_str: Optional[str] = None
        else:
            if p.observed_first_date is None or p.observed_last_date is None:
                raise InputValidationError(
                    f"{item_label}: observed dates must be non-null when record_count > 0",
                    field=item_label,
                    reason="Null observed date with record_count > 0",
                )
            first_date_str = _validate_and_format_date(
                p.observed_first_date, f"{item_label}.observed_first_date"
            )
            last_date_str = _validate_and_format_date(
                p.observed_last_date, f"{item_label}.observed_last_date"
            )
            if p.observed_first_date > p.observed_last_date:
                raise InputValidationError(
                    f"{item_label}: observed_first_date ({first_date_str}) must be <= observed_last_date ({last_date_str})",
                    field=item_label,
                    reason="Inverted observed date range",
                )

        source_url_str: Optional[str] = None
        if p.source_url is not None:
            source_url_str = _validate_clean_string(p.source_url, f"{item_label}.source_url")

        source_use_note_str: Optional[str] = None
        if p.source_use_note is not None:
            source_use_note_str = _validate_clean_string(
                p.source_use_note, f"{item_label}.source_use_note"
            )

        req_interval_list: Optional[List[str]] = None
        if p.requested_interval is not None:
            if (
                not isinstance(p.requested_interval, (list, tuple))
                or len(p.requested_interval) != 2
            ):
                raise InputValidationError(
                    f"Field '{item_label}.requested_interval' must be a 2-date sequence or None",
                    field=f"{item_label}.requested_interval",
                    reason="Invalid requested_interval structure",
                )
            req_start = _validate_and_format_date(
                p.requested_interval[0], f"{item_label}.requested_interval[0]"
            )
            req_end = _validate_and_format_date(
                p.requested_interval[1], f"{item_label}.requested_interval[1]"
            )
            if p.requested_interval[0] > p.requested_interval[1]:
                raise InputValidationError(
                    f"{item_label}.requested_interval start date '{req_start}' must be <= end date '{req_end}'",
                    field=f"{item_label}.requested_interval",
                    reason=f"Inverted requested interval: {req_start} > {req_end}",
                )
            req_interval_list = [req_start, req_end]

        acq_time_str = _format_acquisition_time(
            p.acquisition_time, f"{item_label}.acquisition_time"
        )

        out.append(
            {
                "file_path": file_path_str,
                "raw_byte_count": raw_bytes,
                "sha256": p.sha256,
                "record_count": rec_count,
                "observed_first_date": first_date_str,
                "observed_last_date": last_date_str,
                "source_url": source_url_str,
                "requested_interval": req_interval_list,
                "acquisition_time": acq_time_str,
                "source_use_note": source_use_note_str,
            }
        )

    return out


def _validate_date_sequence(
    seq: Sequence[Any],
    label: str,
) -> List[str]:
    """Validates that a date sequence consists of strictly increasing Gregorian dates."""
    if not isinstance(seq, (list, tuple)):
        raise InputValidationError(
            f"Field '{label}' must be a sequence of dates, got {type(seq).__name__}",
            field=label,
            reason=f"Expected sequence, got {type(seq).__name__}",
        )
    formatted_dates: List[str] = []
    prev_date: Optional[datetime.date] = None
    for idx, d in enumerate(seq):
        date_str = _validate_and_format_date(d, f"{label}[{idx}]")
        if prev_date is not None and d <= prev_date:
            raise InputValidationError(
                f"Field '{label}' must be strictly increasing without duplicates; found '{date_str}' after '{prev_date.isoformat()}'",
                field=label,
                reason=f"Date ordering violation: {date_str} <= {prev_date.isoformat()}",
            )
        prev_date = d
        formatted_dates.append(date_str)
    return formatted_dates


def serialize_replay_input(series: FeatureSeries) -> bytes:
    """
    Serializes an origin-time FeatureSeries into wire JSON bytes (nivesh-replay-input-v1).

    Parameters:
        series: FeatureSeries instance produced by compute_nifty_features.

    Returns:
        Deterministic, BOM-free UTF-8 encoded JSON bytes ending with exactly one newline.

    Raises:
        InputValidationError: If input is not a FeatureSeries, fields violate wire contracts,
                              or internal consistency constraints are breached.

    Invariants:
        1. Fixed parameters: feature_protocol=nifty-close-features-v1, series_id=^NSEI,
           asset=^NSEI, horizon=20D, variant=frozen-current-core-market-data-only-v1.
        2. Exact wire mapping: exactly the 13 root fields, 7 row fields, 7 payload fields,
           and 10 provenance fields. No event, outcome, return-at-t+20, or metric fields.
        3. Row preservation: every origin row is retained in supplied order with contiguous
           indices and increasing Gregorian dates. Warmup (i < 200) and missing-VIX rows
           preserve original dates and Closes with payload=None.
        4. Numeric fidelity: Origin and VIX Closes are formatted as plain fixed-point decimal
           strings preserving precision and positive exponents without float conversion.
           Predictor floats remain finite standard IEEE binary64.
        5. Calendar and provenance preservation: metadata and provenance arrays are carried
           accurately without external validation, file reading, or network fetching.
    """
    if not isinstance(series, FeatureSeries):
        raise InputValidationError(
            f"Expected FeatureSeries instance, got {type(series).__name__}",
            field="series",
            reason=f"Input must be FeatureSeries, got {type(series).__name__}",
        )

    if series.protocol_id != FEATURES_PROTOCOL_ID:
        raise InputValidationError(
            f"Invalid protocol_id: expected '{FEATURES_PROTOCOL_ID}', got '{series.protocol_id}'",
            field="series.protocol_id",
            reason=f"Unexpected protocol: {series.protocol_id}",
        )

    if (
        not isinstance(series.calendar_status, str)
        or series.calendar_status not in VALID_CALENDAR_STATUSES
    ):
        raise InputValidationError(
            f"Invalid calendar_status '{series.calendar_status}'; expected one of {VALID_CALENDAR_STATUSES}",
            field="series.calendar_status",
            reason=f"Invalid calendar_status: {series.calendar_status}",
        )

    # Validate missing and extra calendar session sequences
    formatted_missing = _validate_date_sequence(series.missing_sessions, "missing_sessions")
    formatted_extra = _validate_date_sequence(series.extra_sessions, "extra_sessions")

    # Calendar status invariants
    missing_set = set(series.missing_sessions)
    extra_set = set(series.extra_sessions)
    disjoint_check = missing_set & extra_set
    if disjoint_check:
        sample_dup = sorted(d.isoformat() for d in disjoint_check)[0]
        raise InputValidationError(
            f"Date '{sample_dup}' appears in both missing_sessions and extra_sessions",
            field="calendar_sessions",
            reason=f"Overlapping session date: {sample_dup}",
        )

    if series.calendar_status != "mismatch":
        if len(series.missing_sessions) > 0 or len(series.extra_sessions) > 0:
            raise InputValidationError(
                f"missing_sessions and extra_sessions must be empty when calendar_status is '{series.calendar_status}'",
                field="calendar_status",
                reason=f"Non-empty discrepancy lists with calendar_status '{series.calendar_status}'",
            )
    else:
        if len(series.missing_sessions) == 0 and len(series.extra_sessions) == 0:
            raise InputValidationError(
                "calendar_status is 'mismatch' but missing_sessions and extra_sessions are both empty",
                field="calendar_status",
                reason="Mismatch status with empty discrepancy lists",
            )

    # Validate and serialize provenance
    nifty_prov = _serialize_file_provenance(series.nifty_provenance, "nifty_provenance")
    vix_prov = _serialize_file_provenance(series.vix_provenance, "vix_provenance")

    # Validate and serialize rows
    records = series.records
    if not isinstance(records, (list, tuple)):
        raise InputValidationError(
            f"Field 'series.records' must be a sequence, got {type(records).__name__}",
            field="series.records",
            reason=f"Expected sequence, got {type(records).__name__}",
        )
    total_rows = len(records)

    if total_rows == 0:
        if series.axis_start_date is not None:
            raise InputValidationError(
                "axis_start_date must be null when records sequence is empty",
                field="axis_start_date",
                reason="Non-null axis_start_date on empty series",
            )
        axis_start_str: Optional[str] = None
        rows_list: List[Dict[str, Any]] = []

        if series.calendar_status == "mismatch" and len(series.extra_sessions) > 0:
            raise InputValidationError(
                "Extra session dates cannot exist when the axis is empty",
                field="extra_sessions",
                reason="Extra sessions declared on empty axis",
            )
    else:
        if series.axis_start_date is None:
            raise InputValidationError(
                "axis_start_date must be non-null when records sequence is non-empty",
                field="axis_start_date",
                reason="Null axis_start_date on non-empty series",
            )
        axis_start_str = _validate_and_format_date(series.axis_start_date, "axis_start_date")

        first_rec = records[0]
        if not isinstance(first_rec, NiftyFeatureRecord):
            raise InputValidationError(
                f"Row at index 0 is not NiftyFeatureRecord, got {type(first_rec).__name__}",
                field="rows[0]",
                reason=f"Expected NiftyFeatureRecord, got {type(first_rec).__name__}",
            )
        first_date_str = _validate_and_format_date(first_rec.origin_date, "origin_date", 0)
        if series.axis_start_date != first_rec.origin_date:
            raise InputValidationError(
                f"axis_start_date '{axis_start_str}' does not match first record date '{first_date_str}'",
                field="axis_start_date",
                reason="axis_start_date mismatch with first row date",
            )

        rows_list = []
        prev_date: Optional[datetime.date] = None
        axis_dates_set: Set[datetime.date] = set()

        for idx, rec in enumerate(records):
            if not isinstance(rec, NiftyFeatureRecord):
                raise InputValidationError(
                    f"Row at index {idx} is not NiftyFeatureRecord, got {type(rec).__name__}",
                    field=f"rows[{idx}]",
                    reason=f"Expected NiftyFeatureRecord, got {type(rec).__name__}",
                )

            # Validate origin_index type and bounds using safe integer rules before comparison
            _validate_safe_integer(rec.origin_index, f"rows[{idx}].origin_index")

            if rec.origin_index != idx:
                raise InputValidationError(
                    f"Row {idx} origin_index mismatch: expected {idx}, got {rec.origin_index}",
                    field="origin_index",
                    reason=f"Index mismatch at row {idx}: {rec.origin_index}",
                )

            row_date_str = _validate_and_format_date(rec.origin_date, "origin_date", idx)

            if rec.origin_date in axis_dates_set:
                raise InputValidationError(
                    f"Duplicate origin_date '{row_date_str}' at row {idx}",
                    field="origin_date",
                    reason=f"Duplicate date on axis: {row_date_str}",
                )
            axis_dates_set.add(rec.origin_date)

            if prev_date is not None and rec.origin_date <= prev_date:
                raise InputValidationError(
                    f"Row {idx} date '{row_date_str}' is not strictly increasing after '{prev_date.isoformat()}'",
                    field="origin_date",
                    reason=f"Non-increasing date sequence: {row_date_str} <= {prev_date.isoformat()}",
                )
            prev_date = rec.origin_date

            origin_close_str = _format_decimal(rec.origin_close, "origin_close", idx)
            vix_close_str = (
                _format_decimal(rec.vix_close, "vix_close", idx)
                if rec.vix_close is not None
                else None
            )

            # Invariant check: feature readiness and unready reasons
            is_warmup = idx < 200
            is_missing_vix = rec.vix_close is None

            expected_reasons: List[str] = []
            if is_warmup:
                expected_reasons.append(REASON_WARMUP)
            if is_missing_vix:
                expected_reasons.append(REASON_MISSING_VIX)

            expected_ready = len(expected_reasons) == 0

            if not isinstance(rec.feature_ready, bool):
                raise InputValidationError(
                    f"Row {idx} feature_ready must be a boolean, got {type(rec.feature_ready).__name__}",
                    field="feature_ready",
                    reason=f"Non-boolean feature_ready at row {idx}",
                )

            if rec.feature_ready != expected_ready:
                raise InputValidationError(
                    f"Row {idx} ({row_date_str}) feature_ready mismatch: expected {expected_ready}, got {rec.feature_ready}",
                    field="feature_ready",
                    reason=f"Readiness mismatch: expected {expected_ready}, got {rec.feature_ready}",
                )

            # NiftyFeatureRecord only checks reasons for truthiness, so a manually composed ready
            # row can carry None or a non-sequence; reject the shape before converting it.
            if not isinstance(rec.unready_reasons, (list, tuple)) or not all(
                isinstance(r, str) for r in rec.unready_reasons
            ):
                raise InputValidationError(
                    f"Row {idx} ({row_date_str}) unready_reasons must be a sequence of reason strings, got {type(rec.unready_reasons).__name__}",
                    field="unready_reasons",
                    reason=f"Malformed unready_reasons container at row {idx}",
                )

            if tuple(rec.unready_reasons) != tuple(expected_reasons):
                raise InputValidationError(
                    f"Row {idx} ({row_date_str}) unready_reasons mismatch: expected {tuple(expected_reasons)}, got {rec.unready_reasons}",
                    field="unready_reasons",
                    reason=f"Reason mismatch at row {idx}",
                )

            payload_dict: Optional[Dict[str, Any]] = None
            if not rec.feature_ready:
                if rec.payload is not None:
                    raise InputValidationError(
                        f"Row {idx} ({row_date_str}) is unready but payload is not None",
                        field="payload",
                        reason=f"Unready row {idx} contains non-None payload",
                    )
            else:
                if rec.payload is None or not isinstance(rec.payload, PredictorPayload):
                    raise InputValidationError(
                        f"Row {idx} ({row_date_str}) is feature_ready but payload is invalid: {type(rec.payload).__name__}",
                        field="payload",
                        reason=f"Ready row {idx} has missing or invalid payload",
                    )

                p = rec.payload
                ret_5d = _validate_numeric_predictor(p.ret_5d, "ret_5d", idx)
                rsi_14 = _validate_numeric_predictor(p.rsi_14, "rsi_14", idx)
                macd_hist = _validate_numeric_predictor(p.macd_hist, "macd_hist", idx)
                vol_30d = _validate_numeric_predictor(p.vol_30d, "vol_30d", idx)
                rel_strength_20d = _validate_numeric_predictor(
                    p.rel_strength_20d, "rel_strength_20d", idx
                )
                drawdown = _validate_numeric_predictor(p.drawdown, "drawdown", idx)

                if p.market_regime not in VALID_REGIMES:
                    raise InputValidationError(
                        f"Row {idx} ({row_date_str}) market_regime '{p.market_regime}' is invalid; expected one of {VALID_REGIMES}",
                        field="market_regime",
                        reason=f"Invalid regime label: '{p.market_regime}'",
                    )

                payload_dict = {
                    "ret_5d": ret_5d,
                    "rsi_14": rsi_14,
                    "macd_hist": macd_hist,
                    "vol_30d": vol_30d,
                    "rel_strength_20d": rel_strength_20d,
                    "drawdown": drawdown,
                    "market_regime": p.market_regime,
                }

            rows_list.append(
                {
                    "origin_index": rec.origin_index,
                    "origin_date": row_date_str,
                    "origin_close": origin_close_str,
                    "vix_close": vix_close_str,
                    "feature_ready": rec.feature_ready,
                    "unready_reasons": list(rec.unready_reasons),
                    "payload": payload_dict,
                }
            )

        # Cross-check calendar dates against axis dates when mismatch
        if series.calendar_status == "mismatch":
            for extra_d in series.extra_sessions:
                if extra_d not in axis_dates_set:
                    raise InputValidationError(
                        f"Extra session date '{extra_d.isoformat()}' does not exist on the supplied axis",
                        field="extra_sessions",
                        reason=f"Extra session date '{extra_d.isoformat()}' not on axis",
                    )
            for missing_d in series.missing_sessions:
                if missing_d in axis_dates_set:
                    raise InputValidationError(
                        f"Missing session date '{missing_d.isoformat()}' illegally exists on the supplied axis",
                        field="missing_sessions",
                        reason=f"Missing session date '{missing_d.isoformat()}' found on axis",
                    )

    doc: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "feature_protocol": FEATURE_PROTOCOL,
        "series_id": SERIES_ID,
        "asset": ASSET,
        "horizon": HORIZON,
        "variant": VARIANT,
        "axis_start_date": axis_start_str,
        "calendar_status": series.calendar_status,
        "missing_sessions": formatted_missing,
        "extra_sessions": formatted_extra,
        "nifty_provenance": nifty_prov,
        "vix_provenance": vix_prov,
        "rows": rows_list,
    }

    # Strict JSON serialization: deterministic, BOM-free, UTF-8, exactly one final LF
    try:
        json_text = json.dumps(doc, indent=2, ensure_ascii=False, allow_nan=False)
        json_bytes = json_text.encode("utf-8")
    except (ValueError, OverflowError, UnicodeEncodeError) as exc:
        raise InputValidationError(
            f"Failed to serialize replay document to JSON: {exc}",
            field="document",
            reason=str(exc),
        ) from exc

    return json_bytes + b"\n"
