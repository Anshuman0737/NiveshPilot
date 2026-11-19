"""
Prediction Evaluation Input Foundation.

Provides strict CSV loading and exact-date alignment for Nifty 50 price index
and India VIX series, ensuring deterministic, inspectable inputs for evaluation.

This research input owner is maintained separately from the fund NAV data cleaner
(research/clean_data.py) because evaluation requires strict historical price-index
integrity: absolute duplicate rejection rather than keep-last heuristics, exact
string and decimal validation without binary float drift, raw byte provenance
tracking, and exact-date cross-series alignment that preserves chronological master
sequences without forward-filling or row-position assumptions.
"""

from __future__ import annotations

import csv
import datetime
import decimal
from decimal import Decimal, InvalidOperation
import hashlib
import io
import os
from pathlib import Path
import re
from typing import List, Optional, Sequence, Set, Tuple, Union
from dataclasses import dataclass

SUPPORTED_SERIES_IDS: Set[str] = {"nifty50_price_index", "india_vix"}

_DATE_REGEX = re.compile(r"([0-9]{2})([- ])([A-Za-z]{3})\2([0-9]{4})")
_CLOSE_REGEX = re.compile(r"^[+-]?[0-9]+(?:\.[0-9]+)?$")

_MONTH_MAP = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


class InputValidationError(ValueError):
    """Base error for input validation, schema, encoding, or structure violations."""

    def __init__(
        self,
        message: str,
        *,
        file_path: Optional[str] = None,
        line: Optional[str] = None,
        field: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.file_path = file_path
        self.line = line
        self.field = field
        self.reason = reason


class DuplicateDateError(InputValidationError):
    """Raised when duplicate dates are encountered within or across input files."""
    pass


class CalendarValidationError(InputValidationError):
    """Raised when an invalid expected calendar sequence is supplied."""
    pass


@dataclass(frozen=True)
class FileInputSpec:
    """Declared caller metadata and file path for an input file."""

    file_path: Union[str, Path]
    source_url: Optional[str] = None
    requested_interval: Optional[Tuple[datetime.date, datetime.date]] = None
    acquisition_time: Optional[datetime.datetime] = None
    source_use_note: Optional[str] = None


@dataclass(frozen=True)
class FileProvenance:
    """Observed file properties alongside caller-declared provenance metadata."""

    file_path: str
    raw_byte_count: int
    sha256: str
    record_count: int
    observed_first_date: Optional[datetime.date]
    observed_last_date: Optional[datetime.date]
    source_url: Optional[str] = None
    requested_interval: Optional[Tuple[datetime.date, datetime.date]] = None
    acquisition_time: Optional[datetime.datetime] = None
    source_use_note: Optional[str] = None

    @property
    def requested_interval_matches(self) -> Optional[bool]:
        """True if observed date range equals requested interval, False if differing, None if unrequested."""
        if self.requested_interval is None:
            return None
        req_start, req_end = self.requested_interval
        return (self.observed_first_date == req_start) and (self.observed_last_date == req_end)


@dataclass(frozen=True)
class PriceRecord:
    """Single parsed daily observation with source location."""

    date: datetime.date
    close: Decimal
    source_file: str
    line: str


@dataclass(frozen=True)
class InputWarning:
    """Advisory diagnostic warning for ancillary data discrepancies."""

    file_path: str
    line: str
    field: str
    message: str
    raw_value: Optional[str] = None


@dataclass(frozen=True)
class LoadedSeries:
    """Chronologically sorted validated price series with full provenance."""

    series_id: str
    records: Tuple[PriceRecord, ...]
    provenance: Tuple[FileProvenance, ...]
    warnings: Tuple[InputWarning, ...]

    @property
    def dates(self) -> Tuple[datetime.date, ...]:
        return tuple(r.date for r in self.records)

    @property
    def first_date(self) -> Optional[datetime.date]:
        return self.records[0].date if self.records else None

    @property
    def last_date(self) -> Optional[datetime.date]:
        return self.records[-1].date if self.records else None

    @property
    def total_records(self) -> int:
        return len(self.records)


@dataclass(frozen=True)
class AlignedObservation:
    """Exact-date paired observation on the master Nifty calendar axis."""

    date: datetime.date
    nifty_close: Decimal
    vix_close: Optional[Decimal]


@dataclass(frozen=True)
class AlignedPair:
    """Exact-date alignment of Nifty 50 and India VIX series."""

    nifty_series: LoadedSeries
    vix_series: LoadedSeries
    aligned_observations: Tuple[AlignedObservation, ...]
    nifty_only_dates: Tuple[datetime.date, ...]
    vix_only_dates: Tuple[datetime.date, ...]
    calendar_status: str  # 'not_checked', 'matches_supplied_sessions', 'mismatch'
    missing_sessions: Tuple[datetime.date, ...]
    extra_sessions: Tuple[datetime.date, ...]
    expected_sessions: Optional[Tuple[datetime.date, ...]] = None


def _parse_date(raw_date: str, file_path: str, line_desc: str) -> datetime.date:
    """Parses dd-MMM-yyyy or dd MMM yyyy using invariant English calendar rules."""
    m = _DATE_REGEX.fullmatch(raw_date)
    if not m:
        raise InputValidationError(
            f"Invalid date format '{raw_date}' at {line_desc} in '{file_path}'. "
            "Expected explicit 'dd-MMM-yyyy' or 'dd MMM yyyy' "
            "(e.g. 01-Jan-2024 or 01 Jan 2024).",
            file_path=file_path,
            line=line_desc,
            field="Date",
            reason=f"Date '{raw_date}' does not match 'dd-MMM-yyyy' or 'dd MMM yyyy'",
        )
    day_str, _separator, month_str, year_str = m.groups()
    month_key = month_str.casefold()
    if month_key not in _MONTH_MAP:
        raise InputValidationError(
            f"Unknown English month '{month_str}' in date '{raw_date}' at {line_desc} in '{file_path}'.",
            file_path=file_path,
            line=line_desc,
            field="Date",
            reason=f"Unknown month '{month_str}'",
        )
    month = _MONTH_MAP[month_key]
    day = int(day_str)
    year = int(year_str)
    try:
        return datetime.date(year, month, day)
    except ValueError as e:
        raise InputValidationError(
            f"Impossible calendar date '{raw_date}' at {line_desc} in '{file_path}': {e}",
            file_path=file_path,
            line=line_desc,
            field="Date",
            reason=str(e),
        )


def _parse_close(raw_close: str, file_path: str, line_desc: str) -> Decimal:
    """Parses strictly positive plain decimal Close value preserving source precision."""
    if not _CLOSE_REGEX.match(raw_close):
        raise InputValidationError(
            f"Invalid Close format '{raw_close}' at {line_desc} in '{file_path}'. "
            "Expected invariant plain decimal syntax without commas, grouping, or exponent notation.",
            file_path=file_path,
            line=line_desc,
            field="Close",
            reason=f"Close '{raw_close}' does not match plain decimal syntax",
        )
    try:
        val = Decimal(raw_close)
    except (InvalidOperation, ValueError) as e:
        raise InputValidationError(
            f"Unparseable Close value '{raw_close}' at {line_desc} in '{file_path}': {e}",
            file_path=file_path,
            line=line_desc,
            field="Close",
            reason=str(e),
        )
    if not val.is_finite():
        raise InputValidationError(
            f"Non-finite Close value '{raw_close}' at {line_desc} in '{file_path}'.",
            file_path=file_path,
            line=line_desc,
            field="Close",
            reason="Close must be finite",
        )
    if val <= Decimal(0):
        raise InputValidationError(
            f"Non-positive Close value '{raw_close}' at {line_desc} in '{file_path}'. "
            "Close must be strictly positive.",
            file_path=file_path,
            line=line_desc,
            field="Close",
            reason=f"Close value {val} is not strictly positive",
        )
    return val


def _check_ohlc_advisory_warnings(
    row: List[str],
    open_idx: int,
    high_idx: int,
    low_idx: int,
    close_val: Decimal,
    file_path: str,
    line_desc: str,
) -> List[InputWarning]:
    """Inspects optional OHLC values and generates advisory warnings without mutating Close."""
    warnings: List[InputWarning] = []

    def _parse_ancillary(idx: int, field_name: str) -> Optional[Decimal]:
        if idx < 0 or idx >= len(row):
            return None
        raw = row[idx].strip()
        if not raw:
            warnings.append(
                InputWarning(
                    file_path=file_path,
                    line=line_desc,
                    field=field_name,
                    message=f"Missing or empty {field_name} value in OHLC record",
                    raw_value=row[idx],
                )
            )
            return None
        if not _CLOSE_REGEX.match(raw):
            warnings.append(
                InputWarning(
                    file_path=file_path,
                    line=line_desc,
                    field=field_name,
                    message=f"Malformed {field_name} value '{raw}'; expected plain decimal syntax",
                    raw_value=row[idx],
                )
            )
            return None
        try:
            val = Decimal(raw)
        except (InvalidOperation, ValueError) as e:
            warnings.append(
                InputWarning(
                    file_path=file_path,
                    line=line_desc,
                    field=field_name,
                    message=f"Unparseable {field_name} value '{raw}': {e}",
                    raw_value=row[idx],
                )
            )
            return None
        if not val.is_finite() or val <= Decimal(0):
            warnings.append(
                InputWarning(
                    file_path=file_path,
                    line=line_desc,
                    field=field_name,
                    message=f"Nonpositive or non-finite {field_name} value '{raw}'",
                    raw_value=row[idx],
                )
            )
            return None
        return val

    open_val = _parse_ancillary(open_idx, "Open") if open_idx >= 0 else None
    high_val = _parse_ancillary(high_idx, "High") if high_idx >= 0 else None
    low_val = _parse_ancillary(low_idx, "Low") if low_idx >= 0 else None

    if low_val is not None and high_val is not None:
        if low_val > high_val:
            warnings.append(
                InputWarning(
                    file_path=file_path,
                    line=line_desc,
                    field="Low/High",
                    message=f"Low ({low_val}) exceeds High ({high_val})",
                    raw_value=f"Low={low_val}, High={high_val}",
                )
            )

    if high_val is not None:
        if close_val > high_val:
            warnings.append(
                InputWarning(
                    file_path=file_path,
                    line=line_desc,
                    field="Close/High",
                    message=f"Close ({close_val}) exceeds High ({high_val})",
                    raw_value=f"Close={close_val}, High={high_val}",
                )
            )
        if open_val is not None and open_val > high_val:
            warnings.append(
                InputWarning(
                    file_path=file_path,
                    line=line_desc,
                    field="Open/High",
                    message=f"Open ({open_val}) exceeds High ({high_val})",
                    raw_value=f"Open={open_val}, High={high_val}",
                )
            )

    if low_val is not None:
        if close_val < low_val:
            warnings.append(
                InputWarning(
                    file_path=file_path,
                    line=line_desc,
                    field="Close/Low",
                    message=f"Close ({close_val}) is below Low ({low_val})",
                    raw_value=f"Close={close_val}, Low={low_val}",
                )
            )
        if open_val is not None and open_val < low_val:
            warnings.append(
                InputWarning(
                    file_path=file_path,
                    line=line_desc,
                    field="Open/Low",
                    message=f"Open ({open_val}) is below Low ({low_val})",
                    raw_value=f"Open={open_val}, Low={low_val}",
                )
            )

    return warnings


def load_series(
    series_id: str,
    files: Union[str, Path, FileInputSpec, Sequence[Union[str, Path, FileInputSpec]]],
) -> LoadedSeries:
    """
    Loads, validates, and sorts daily price-index records for a declared series.

    Parameters:
        series_id: Declared series identifier ('nifty50_price_index' or 'india_vix').
        files: One or more file paths or FileInputSpec objects.

    Returns:
        LoadedSeries containing chronologically sorted PriceRecord tuples and provenance.

    Raises:
        InputValidationError: On missing files, encoding errors, schema violations,
                              or malformed data.
        DuplicateDateError: On duplicate dates within or across files.
    """
    if series_id not in SUPPORTED_SERIES_IDS:
        raise InputValidationError(
            f"Unsupported series_id '{series_id}'. "
            f"Only {sorted(SUPPORTED_SERIES_IDS)} are supported.",
            field="series_id",
            reason=f"Series ID '{series_id}' is not supported",
        )

    if isinstance(files, (str, Path, FileInputSpec)):
        file_list = [files]
    else:
        file_list = list(files)

    if not file_list:
        raise InputValidationError(
            "At least one input file must be supplied to load_series.",
            reason="Empty file list supplied",
        )

    specs: List[FileInputSpec] = []
    for item in file_list:
        if isinstance(item, FileInputSpec):
            specs.append(item)
        elif isinstance(item, (str, Path)):
            specs.append(FileInputSpec(file_path=item))
        else:
            raise InputValidationError(
                f"Invalid file item {item!r}; expected str, Path, or FileInputSpec.",
                reason="Invalid item type in file list",
            )

    for spec in specs:
        if spec.requested_interval is not None:
            start_d, end_d = spec.requested_interval
            if not isinstance(start_d, datetime.date) or isinstance(start_d, datetime.datetime):
                raise InputValidationError(
                    f"Requested interval start {start_d!r} is not a datetime.date",
                    file_path=str(spec.file_path),
                    reason="Invalid requested interval start type",
                )
            if not isinstance(end_d, datetime.date) or isinstance(end_d, datetime.datetime):
                raise InputValidationError(
                    f"Requested interval end {end_d!r} is not a datetime.date",
                    file_path=str(spec.file_path),
                    reason="Invalid requested interval end type",
                )
            if start_d > end_d:
                raise InputValidationError(
                    f"Invalid requested_interval: start date {start_d} is after end date {end_d}",
                    file_path=str(spec.file_path),
                    reason="Requested interval start > end",
                )

    all_records: List[PriceRecord] = []
    all_provenance: List[FileProvenance] = []
    all_warnings: List[InputWarning] = []
    seen_dates: dict[datetime.date, Tuple[str, str]] = {}

    for spec in specs:
        path_str = str(spec.file_path)
        try:
            with open(spec.file_path, "rb") as f:
                raw_bytes = f.read()
        except OSError as e:
            raise InputValidationError(
                f"Cannot access file '{path_str}': {e}",
                file_path=path_str,
                reason=str(e),
            )

        raw_byte_count = len(raw_bytes)
        sha256_hash = hashlib.sha256(raw_bytes).hexdigest()

        if raw_byte_count == 0:
            raise InputValidationError(
                f"Empty CSV file: '{path_str}'",
                file_path=path_str,
                reason="File has 0 bytes",
            )

        if raw_bytes.startswith(b"\xef\xbb\xbf"):
            bytes_to_decode = raw_bytes[3:]
        else:
            bytes_to_decode = raw_bytes

        try:
            text = bytes_to_decode.decode("utf-8")
        except UnicodeDecodeError as e:
            raise InputValidationError(
                f"Invalid UTF-8 encoding in '{path_str}': {e}",
                file_path=path_str,
                reason=f"UnicodeDecodeError: {e}",
            )

        stream = io.StringIO(text, newline="")
        reader = csv.reader(stream, strict=True)

        header_row: Optional[List[str]] = None
        header_line_desc: Optional[str] = None
        normalized_headers: Optional[List[str]] = None
        date_idx: int = -1
        close_idx: int = -1
        open_idx: int = -1
        high_idx: int = -1
        low_idx: int = -1
        file_records: List[PriceRecord] = []

        while True:
            start_line = reader.line_num + 1
            try:
                row = next(reader)
            except StopIteration:
                break
            except csv.Error as e:
                end_line = reader.line_num
                line_desc = f"line {start_line}" if start_line == end_line else f"lines {start_line}-{end_line}"
                raise InputValidationError(
                    f"CSV formatting error in '{path_str}' at {line_desc}: {e}",
                    file_path=path_str,
                    line=line_desc,
                    reason=str(e),
                )
            end_line = reader.line_num
            line_desc = f"line {start_line}" if start_line == end_line else f"lines {start_line}-{end_line}"

            if not row or all(len(c.strip()) == 0 for c in row):
                if header_row is None:
                    raise InputValidationError(
                        f"Blank header record at {line_desc} in '{path_str}'",
                        file_path=path_str,
                        line=line_desc,
                        reason="Blank header row",
                    )
                raise InputValidationError(
                    f"Blank record at {line_desc} in '{path_str}'",
                    file_path=path_str,
                    line=line_desc,
                    reason="Blank record encountered",
                )

            if header_row is None:
                header_row = row
                header_line_desc = line_desc
                normalized_headers = [col.strip().casefold() for col in header_row]

                if any(len(h) == 0 for h in normalized_headers):
                    raise InputValidationError(
                        f"Empty header column at {line_desc} in '{path_str}'",
                        file_path=path_str,
                        line=line_desc,
                        reason="Empty header column name",
                    )

                seen_h: Set[str] = set()
                for h in normalized_headers:
                    if h in seen_h:
                        raise InputValidationError(
                            f"Duplicate normalized header column '{h}' at {line_desc} in '{path_str}'",
                            file_path=path_str,
                            line=line_desc,
                            reason=f"Duplicate header column '{h}'",
                        )
                    seen_h.add(h)

                if "date" not in normalized_headers:
                    raise InputValidationError(
                        f"Missing required 'Date' header column in '{path_str}'",
                        file_path=path_str,
                        line=line_desc,
                        field="Date",
                        reason="Missing required 'date' header",
                    )
                if "close" not in normalized_headers:
                    raise InputValidationError(
                        f"Missing required 'Close' header column in '{path_str}'",
                        file_path=path_str,
                        line=line_desc,
                        field="Close",
                        reason="Missing required 'close' header",
                    )

                date_idx = normalized_headers.index("date")
                close_idx = normalized_headers.index("close")
                if "open" in normalized_headers:
                    open_idx = normalized_headers.index("open")
                if "high" in normalized_headers:
                    high_idx = normalized_headers.index("high")
                if "low" in normalized_headers:
                    low_idx = normalized_headers.index("low")
                continue

            if len(row) != len(header_row):
                raise InputValidationError(
                    f"Record at {line_desc} has {len(row)} fields; expected {len(header_row)} in '{path_str}'",
                    file_path=path_str,
                    line=line_desc,
                    reason=f"Field count mismatch: expected {len(header_row)}, got {len(row)}",
                )

            raw_date = row[date_idx].strip()
            parsed_d = _parse_date(raw_date, path_str, line_desc)

            if parsed_d in seen_dates:
                prev_file, prev_line = seen_dates[parsed_d]
                raise DuplicateDateError(
                    f"Duplicate date {parsed_d.strftime('%d-%b-%Y')} at {line_desc} in '{path_str}'; "
                    f"previously encountered at {prev_line} in '{prev_file}'",
                    file_path=path_str,
                    line=line_desc,
                    field="Date",
                    reason=f"Duplicate date {parsed_d.isoformat()}",
                )
            seen_dates[parsed_d] = (path_str, line_desc)

            raw_close = row[close_idx].strip()
            close_val = _parse_close(raw_close, path_str, line_desc)

            if open_idx >= 0 or high_idx >= 0 or low_idx >= 0:
                row_warnings = _check_ohlc_advisory_warnings(
                    row,
                    open_idx,
                    high_idx,
                    low_idx,
                    close_val,
                    path_str,
                    line_desc,
                )
                all_warnings.extend(row_warnings)

            rec = PriceRecord(
                date=parsed_d,
                close=close_val,
                source_file=path_str,
                line=line_desc,
            )
            file_records.append(rec)

        if header_row is None:
            raise InputValidationError(
                f"Empty CSV file: '{path_str}'",
                file_path=path_str,
                reason="File contains no rows",
            )
        if not file_records:
            raise InputValidationError(
                f"Header-only CSV file with no data records at {header_line_desc}: '{path_str}'",
                file_path=path_str,
                line=header_line_desc,
                reason="Header row present but no data rows",
            )

        obs_first = min(r.date for r in file_records)
        obs_last = max(r.date for r in file_records)

        prov = FileProvenance(
            file_path=path_str,
            raw_byte_count=raw_byte_count,
            sha256=sha256_hash,
            record_count=len(file_records),
            observed_first_date=obs_first,
            observed_last_date=obs_last,
            source_url=spec.source_url,
            requested_interval=spec.requested_interval,
            acquisition_time=spec.acquisition_time,
            source_use_note=spec.source_use_note,
        )
        all_provenance.append(prov)
        all_records.extend(file_records)

    sorted_records = tuple(sorted(all_records, key=lambda r: r.date))

    return LoadedSeries(
        series_id=series_id,
        records=sorted_records,
        provenance=tuple(all_provenance),
        warnings=tuple(all_warnings),
    )


def align_pair(
    nifty_series: LoadedSeries,
    vix_series: LoadedSeries,
    expected_sessions: Optional[Sequence[datetime.date]] = None,
) -> AlignedPair:
    """
    Aligns India VIX observations to the master Nifty 50 chronological sequence.

    Parameters:
        nifty_series: LoadedSeries for 'nifty50_price_index'.
        vix_series: LoadedSeries for 'india_vix'.
        expected_sessions: Optional strictly increasing sequence of expected trading dates.

    Returns:
        AlignedPair containing aligned observations, asymmetric date sets, and calendar status.

    Raises:
        InputValidationError: If series IDs do not match required roles.
        CalendarValidationError: If supplied expected_sessions is not strictly increasing or invalid.
    """
    if nifty_series.series_id != "nifty50_price_index":
        raise InputValidationError(
            f"Invalid series for Nifty role: expected 'nifty50_price_index', got '{nifty_series.series_id}'",
            field="nifty_series.series_id",
            reason=f"Wrong series ID '{nifty_series.series_id}' for Nifty master sequence",
        )
    if vix_series.series_id != "india_vix":
        raise InputValidationError(
            f"Invalid series for VIX role: expected 'india_vix', got '{vix_series.series_id}'",
            field="vix_series.series_id",
            reason=f"Wrong series ID '{vix_series.series_id}' for VIX series",
        )

    vix_by_date = {rec.date: rec.close for rec in vix_series.records}
    nifty_date_set = {rec.date for rec in nifty_series.records}
    vix_date_set = set(vix_by_date.keys())

    aligned_observations: List[AlignedObservation] = []
    for n_rec in nifty_series.records:
        v_close = vix_by_date.get(n_rec.date)
        aligned_observations.append(
            AlignedObservation(
                date=n_rec.date,
                nifty_close=n_rec.close,
                vix_close=v_close,
            )
        )

    nifty_only_dates = tuple(sorted(nifty_date_set - vix_date_set))
    vix_only_dates = tuple(sorted(vix_date_set - nifty_date_set))

    if expected_sessions is not None:
        if not isinstance(expected_sessions, (list, tuple)):
            raise CalendarValidationError(
                "expected_sessions must be a sequence of datetime.date objects",
                field="expected_sessions",
                reason="Invalid expected_sessions collection type",
            )
        validated_expected: List[datetime.date] = []
        prev_date: Optional[datetime.date] = None
        for idx, item in enumerate(expected_sessions):
            if not isinstance(item, datetime.date) or isinstance(item, datetime.datetime):
                raise CalendarValidationError(
                    f"Invalid item at index {idx} in expected_sessions: {item!r} is not datetime.date",
                    field="expected_sessions",
                    reason=f"Item at index {idx} is not a datetime.date",
                )
            if prev_date is not None:
                if item <= prev_date:
                    raise CalendarValidationError(
                        f"expected_sessions must be strictly increasing with unique dates; "
                        f"found {item} after {prev_date} at index {idx}",
                        field="expected_sessions",
                        reason=f"Non-increasing or duplicate date {item} at index {idx}",
                    )
            prev_date = item
            validated_expected.append(item)

        expected_tuple: Optional[Tuple[datetime.date, ...]] = tuple(validated_expected)
        expected_set = set(expected_tuple)

        missing_sessions = tuple(sorted(expected_set - nifty_date_set))
        extra_sessions = tuple(sorted(nifty_date_set - expected_set))

        nifty_dates_tuple = tuple(rec.date for rec in nifty_series.records)
        if nifty_dates_tuple == expected_tuple:
            calendar_status = "matches_supplied_sessions"
        else:
            calendar_status = "mismatch"
    else:
        calendar_status = "not_checked"
        missing_sessions = ()
        extra_sessions = ()
        expected_tuple = None

    return AlignedPair(
        nifty_series=nifty_series,
        vix_series=vix_series,
        aligned_observations=tuple(aligned_observations),
        nifty_only_dates=nifty_only_dates,
        vix_only_dates=vix_only_dates,
        calendar_status=calendar_status,
        missing_sessions=missing_sessions,
        extra_sessions=extra_sessions,
        expected_sessions=expected_tuple,
    )
