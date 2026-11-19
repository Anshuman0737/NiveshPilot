"""
Prediction Evaluation Features Foundation.

Provides deterministic, inspectable, point-in-time quantitative feature calculation
and market regime classification for chronological Nifty 50 price-index series
paired with exact-date India VIX observations.

Architectural ownership:
    inputs.py owns raw CSV parsing, validation, provenance, and exact-date alignment.
    outcomes.py owns future-label timing and exact-band classification (+/-0.5%).
    features.py owns origin-time causal feature construction and regime classification.

Causal data boundary:
    Features use strictly historical observations on or before origin index i (0..i)
    and exact-date India VIX at index i. Future observations (i+1..) are never accessed,
    projected, or back-propagated. Future labels and outcomes remain entirely outside
    this module.
"""

from __future__ import annotations

import datetime
from decimal import Decimal, InvalidOperation
import math
from typing import List, Optional, Sequence, Tuple
from dataclasses import dataclass

from research.prediction_eval.inputs import (
    AlignedPair,
    FileProvenance,
    InputValidationError,
)

PROTOCOL_ID: str = "nifty-close-features-v1"
WARMUP_ORIGIN_INDEX: int = 200

REASON_WARMUP: str = "warmup"
REASON_MISSING_VIX: str = "missing_vix"

REGIME_HIGH_VOLATILITY: str = "High-volatility"
REGIME_BEAR: str = "Bear"
REGIME_RECOVERY: str = "Recovery"
REGIME_CORRECTION: str = "Correction"
REGIME_BULL: str = "Bull"
REGIME_SIDEWAYS: str = "Sideways"

VALID_REGIMES: Tuple[str, ...] = (
    REGIME_HIGH_VOLATILITY,
    REGIME_BEAR,
    REGIME_RECOVERY,
    REGIME_CORRECTION,
    REGIME_BULL,
    REGIME_SIDEWAYS,
)


@dataclass(frozen=True)
class PredictorPayload:
    """
    Typed immutable predictor payload matching the forecastEngine.ts consumer schema.

    Contains exactly six numeric fields plus market_regime:
        ret_5d: 5-session price return (decimal ratio, C_i / C_{i-5} - 1.0)
        rsi_14: 14-period relative strength index (0.0 to 100.0, rolling arithmetic mean)
        macd_hist: MACD histogram percentage points ((MACD - Signal) / C_i * 100.0)
        vol_30d: 30-session annualized sample volatility (ddof=1, decimal ratio)
        rel_strength_20d: 20-session relative strength vs benchmark (0.0 for Nifty-vs-itself)
        drawdown: Peak-to-trough drawdown from dataset inception ((C_i - Peak_i) / Peak_i)
        market_regime: Ordered heuristic regime label
    """

    ret_5d: float
    rsi_14: float
    macd_hist: float
    vol_30d: float
    rel_strength_20d: float
    drawdown: float
    market_regime: str

    def __post_init__(self) -> None:
        """Enforces schema consistency and nonfinite numeric rejection."""
        numeric_fields = {
            "ret_5d": self.ret_5d,
            "rsi_14": self.rsi_14,
            "macd_hist": self.macd_hist,
            "vol_30d": self.vol_30d,
            "rel_strength_20d": self.rel_strength_20d,
            "drawdown": self.drawdown,
        }
        for field_name, value in numeric_fields.items():
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(
                    f"PredictorPayload field '{field_name}' must be a finite float, got {value!r}"
                )
        if self.market_regime not in VALID_REGIMES:
            raise ValueError(
                f"Invalid market_regime '{self.market_regime}'; expected one of {VALID_REGIMES}"
            )


@dataclass(frozen=True)
class NiftyFeatureRecord:
    """
    Inspectable per-origin feature record for a single Nifty 50 observation.

    Retains the origin position index, date, original Decimal Close, and aligned VIX Close.
    Exposes feature_ready status, predictor payload (None when unready), and deterministic
    unready reasons ('warmup', 'missing_vix', or both).
    """

    origin_index: int
    origin_date: datetime.date
    origin_close: Decimal
    vix_close: Optional[Decimal]
    feature_ready: bool
    payload: Optional[PredictorPayload]
    unready_reasons: Tuple[str, ...]

    def __post_init__(self) -> None:
        """Enforces invariant consistency between readiness and payload availability."""
        if self.feature_ready:
            if self.payload is None:
                raise ValueError("Feature-ready record must contain a non-None PredictorPayload.")
            if self.unready_reasons:
                raise ValueError(
                    f"Feature-ready record must have empty unready_reasons, got {self.unready_reasons}"
                )
        else:
            if self.payload is not None:
                raise ValueError("Unready feature record cannot contain a PredictorPayload.")
            if not self.unready_reasons:
                raise ValueError("Unready feature record must state at least one unready reason.")

    @property
    def date(self) -> datetime.date:
        """Convenience property for origin date."""
        return self.origin_date

    @property
    def close(self) -> Decimal:
        """Convenience property for origin Close."""
        return self.origin_close

    @property
    def index(self) -> int:
        """Convenience property for origin position index."""
        return self.origin_index

    @property
    def reasons(self) -> Tuple[str, ...]:
        """Convenience property for unready reasons tuple."""
        return self.unready_reasons

    @property
    def unready_reason(self) -> Optional[str]:
        """Convenience property for primary unready reason."""
        return self.unready_reasons[0] if self.unready_reasons else None


OriginFeatureRecord = NiftyFeatureRecord


@dataclass(frozen=True)
class FeatureSeries:
    """
    Immutable chronological sequence of origin feature records for an aligned Nifty/VIX pair.

    Encapsulates origin-retained records, dataset start metadata, calendar status,
    and source provenance under immutable ownership.
    """

    protocol_id: str
    axis_start_date: Optional[datetime.date]
    records: Tuple[NiftyFeatureRecord, ...]
    calendar_status: str
    missing_sessions: Tuple[datetime.date, ...]
    extra_sessions: Tuple[datetime.date, ...]
    nifty_provenance: Tuple[FileProvenance, ...]
    vix_provenance: Tuple[FileProvenance, ...]

    def __len__(self) -> int:
        return len(self.records)

    def __iter__(self):
        return iter(self.records)

    def __getitem__(self, index: int) -> NiftyFeatureRecord:
        return self.records[index]

    @property
    def features(self) -> Tuple[NiftyFeatureRecord, ...]:
        """Alias for records sequence."""
        return self.records

    @property
    def total_origins(self) -> int:
        """Total number of origin observations in the series."""
        return len(self.records)

    @property
    def ready_count(self) -> int:
        """Number of origins with complete feature readiness."""
        return sum(1 for r in self.records if r.feature_ready)

    @property
    def unready_count(self) -> int:
        """Number of origins with unready status (warmup or missing VIX)."""
        return sum(1 for r in self.records if not r.feature_ready)

    @property
    def ready_records(self) -> Tuple[NiftyFeatureRecord, ...]:
        """Subset of feature-ready records."""
        return tuple(r for r in self.records if r.feature_ready)

    @property
    def unready_records(self) -> Tuple[NiftyFeatureRecord, ...]:
        """Subset of unready records."""
        return tuple(r for r in self.records if not r.feature_ready)


NiftyFeatureSeries = FeatureSeries


def _compute_stable_mean(window: Sequence[float], count: int) -> float:
    """
    Computes arithmetic mean over a trailing window of positive finite floats.

    Preserves precision for tiny positive values (avoiding premature per-term underflow
    to 0.0 when dividing subnormal floats by count) while protecting large finite values
    from premature intermediate sum overflow to infinity.
    """
    try:
        raw_sum = sum(window)
        if math.isfinite(raw_sum):
            return raw_sum / float(count)
    except (OverflowError, ValueError):
        pass
    # If the unscaled sum overflows (large values near float max),
    # compute sum of pre-scaled terms where each term is far above underflow.
    return sum(c / float(count) for c in window)


def compute_nifty_features(pair: AlignedPair) -> FeatureSeries:
    """
    Computes causal Nifty 50 features and market regime classifications for an aligned pair.

    Parameters:
        pair: AlignedPair produced by align_pair for 'nifty50_price_index' and 'india_vix'.

    Returns:
        FeatureSeries containing one immutable NiftyFeatureRecord for every supplied Nifty origin.

    Raises:
        InputValidationError: If the input is not an AlignedPair, series roles are incorrect,
                              or numeric values cannot be converted to finite positive floats.

    Invariants:
        1. Causal prefix isolation: origin i uses only prices 0..i and exact-date VIX at i.
           Future prices and outcomes (i+1..) are never accessed.
        2. Session ownership: exactly one output record per supplied Nifty origin.
        3. Warmup guard: origins i < 200 have feature_ready=False and payload=None.
           First possible ready index is 200 (requiring 201 supplied closes and exact-date VIX).
        4. Missing VIX handling: missing VIX at origin i marks only origin i unready without
           shifting or corrupting price features or other origins.
        5. Zero-value fidelity: legitimate 0.0 returns, volatility, and RSI remain 0.0.
    """
    if not isinstance(pair, AlignedPair):
        raise InputValidationError(
            f"Expected AlignedPair instance, got {type(pair).__name__}",
            field="pair",
            reason=f"Input must be an AlignedPair instance, got {type(pair).__name__}",
        )

    if pair.nifty_series.series_id != "nifty50_price_index":
        raise InputValidationError(
            f"Invalid series for Nifty role: expected 'nifty50_price_index', got '{pair.nifty_series.series_id}'",
            field="pair.nifty_series.series_id",
            reason=f"Wrong series ID '{pair.nifty_series.series_id}' for Nifty sequence",
        )

    if pair.vix_series.series_id != "india_vix":
        raise InputValidationError(
            f"Invalid series for VIX role: expected 'india_vix', got '{pair.vix_series.series_id}'",
            field="pair.vix_series.series_id",
            reason=f"Wrong series ID '{pair.vix_series.series_id}' for VIX series",
        )

    observations = pair.aligned_observations
    total_obs = len(observations)

    if total_obs == 0:
        return FeatureSeries(
            protocol_id=PROTOCOL_ID,
            axis_start_date=None,
            records=(),
            calendar_status=pair.calendar_status,
            missing_sessions=pair.missing_sessions,
            extra_sessions=pair.extra_sessions,
            nifty_provenance=pair.nifty_series.provenance,
            vix_provenance=pair.vix_series.provenance,
        )

    axis_start_date = observations[0].date

    # Validate and convert all Nifty Close prices to binary64 floats
    nifty_closes_float: List[float] = []
    for idx, obs in enumerate(observations):
        try:
            c_flt = float(obs.nifty_close)
        except (ValueError, OverflowError, InvalidOperation) as exc:
            raise InputValidationError(
                f"Failed to convert nifty_close to float at origin index {idx} ({obs.date}): {obs.nifty_close}",
                field="nifty_close",
                reason=str(exc),
            ) from exc
        if not math.isfinite(c_flt) or c_flt <= 0.0:
            raise InputValidationError(
                f"Nonfinite or nonpositive nifty_close {c_flt} at origin index {idx} ({obs.date})",
                field="nifty_close",
                reason=f"Invalid Close float value: {c_flt}",
            )
        nifty_closes_float.append(c_flt)

    # 1. One-session returns: r_i = C_i / C_{i-1} - 1.0 (unavailable at i=0)
    one_session_returns: List[Optional[float]] = [None]
    for i in range(1, total_obs):
        try:
            r_i = (nifty_closes_float[i] / nifty_closes_float[i - 1]) - 1.0
            if not math.isfinite(r_i):
                raise InputValidationError(
                    f"Nonfinite 1-session return at origin index {i} ({observations[i].date})",
                    field="ret_1d",
                    reason=f"Calculated return value: {r_i}",
                )
        except (OverflowError, ValueError) as exc:
            raise InputValidationError(
                f"Numeric overflow calculating 1-session return at origin index {i} ({observations[i].date})",
                field="ret_1d",
                reason=str(exc),
            ) from exc
        one_session_returns.append(r_i)

    # 2. Drawdowns from dataset start running peak: (C_i - Peak_i) / Peak_i
    drawdowns: List[float] = []
    running_peak = nifty_closes_float[0]
    for i in range(total_obs):
        c_i = nifty_closes_float[i]
        if c_i > running_peak:
            running_peak = c_i
        try:
            dd = (c_i - running_peak) / running_peak
            if not math.isfinite(dd):
                raise InputValidationError(
                    f"Nonfinite drawdown at origin index {i} ({observations[i].date})",
                    field="drawdown",
                    reason=f"Calculated drawdown value: {dd}",
                )
        except (OverflowError, ValueError) as exc:
            raise InputValidationError(
                f"Numeric overflow calculating drawdown at origin index {i} ({observations[i].date})",
                field="drawdown",
                reason=str(exc),
            ) from exc
        drawdowns.append(dd)

    # 3. Simple rolling 14-period RSI
    # delta_0 contributes zero gain/loss; delta_i = C_i - C_{i-1}
    gains: List[float] = [0.0]
    losses: List[float] = [0.0]
    for i in range(1, total_obs):
        try:
            delta = nifty_closes_float[i] - nifty_closes_float[i - 1]
            if not math.isfinite(delta):
                raise InputValidationError(
                    f"Nonfinite price delta at origin index {i} ({observations[i].date})",
                    field="rsi_14",
                    reason=f"Calculated delta value: {delta}",
                )
        except (OverflowError, ValueError) as exc:
            raise InputValidationError(
                f"Numeric overflow calculating price delta at origin index {i} ({observations[i].date})",
                field="rsi_14",
                reason=str(exc),
            ) from exc
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))

    # 4. MACD Histogram: recursive EMA12, EMA26, and Signal EMA9
    alpha12 = 2.0 / (12.0 + 1.0)
    alpha26 = 2.0 / (26.0 + 1.0)
    alpha9 = 2.0 / (9.0 + 1.0)

    ema12_val = nifty_closes_float[0]
    ema26_val = nifty_closes_float[0]
    macd_val = 0.0
    signal_val = 0.0

    macd_hist_series: List[float] = [0.0]
    for i in range(1, total_obs):
        c_i = nifty_closes_float[i]
        try:
            ema12_val = (1.0 - alpha12) * ema12_val + alpha12 * c_i
            ema26_val = (1.0 - alpha26) * ema26_val + alpha26 * c_i
            macd_val = ema12_val - ema26_val
            signal_val = (1.0 - alpha9) * signal_val + alpha9 * macd_val
            hist_val = ((macd_val - signal_val) / c_i) * 100.0
            if not math.isfinite(hist_val):
                raise InputValidationError(
                    f"Nonfinite MACD histogram at origin index {i} ({observations[i].date})",
                    field="macd_hist",
                    reason=f"Calculated MACD histogram value: {hist_val}",
                )
        except (OverflowError, ValueError) as exc:
            raise InputValidationError(
                f"Numeric overflow calculating MACD histogram at origin index {i} ({observations[i].date})",
                field="macd_hist",
                reason=str(exc),
            ) from exc
        macd_hist_series.append(hist_val)

    records: List[NiftyFeatureRecord] = []
    for i in range(total_obs):
        obs = observations[i]
        is_warmup = i < WARMUP_ORIGIN_INDEX
        is_missing_vix = obs.vix_close is None

        # Determine deterministic unready reasons in order: warmup, then missing_vix when both
        if is_warmup and is_missing_vix:
            unready_reasons = (REASON_WARMUP, REASON_MISSING_VIX)
        elif is_warmup:
            unready_reasons = (REASON_WARMUP,)
        elif is_missing_vix:
            unready_reasons = (REASON_MISSING_VIX,)
        else:
            unready_reasons = ()

        if unready_reasons:
            records.append(
                NiftyFeatureRecord(
                    origin_index=i,
                    origin_date=obs.date,
                    origin_close=obs.nifty_close,
                    vix_close=obs.vix_close,
                    feature_ready=False,
                    payload=None,
                    unready_reasons=unready_reasons,
                )
            )
            continue

        # Origin is ready (i >= 200 with exact-date VIX present)
        # Validate VIX Close
        try:
            vix_flt = float(obs.vix_close)  # type: ignore[arg-type]
        except (ValueError, OverflowError, InvalidOperation) as exc:
            raise InputValidationError(
                f"Failed to convert vix_close to float at origin index {i} ({obs.date}): {obs.vix_close}",
                field="vix_close",
                reason=str(exc),
            ) from exc
        if not math.isfinite(vix_flt) or vix_flt <= 0.0:
            raise InputValidationError(
                f"Nonfinite or nonpositive vix_close {vix_flt} at origin index {i} ({obs.date})",
                field="vix_close",
                reason=f"Invalid VIX float value: {vix_flt}",
            )

        # 5-session return: C_i / C_{i-5} - 1.0 (available since i >= 200 >= 5)
        try:
            ret_5d = (nifty_closes_float[i] / nifty_closes_float[i - 5]) - 1.0
            if not math.isfinite(ret_5d):
                raise InputValidationError(
                    f"Nonfinite ret_5d at origin index {i} ({obs.date})",
                    field="ret_5d",
                    reason=f"Calculated ret_5d value: {ret_5d}",
                )
        except (OverflowError, ValueError) as exc:
            raise InputValidationError(
                f"Numeric overflow calculating ret_5d at origin index {i} ({obs.date})",
                field="ret_5d",
                reason=str(exc),
            ) from exc

        # 14-period RSI arithmetic rolling mean over last 14 entries (i-13..i)
        # Sum pre-scaled entries to avoid premature overflow of intermediate sum
        try:
            slice_gains = gains[i - 13 : i + 1]
            slice_losses = losses[i - 13 : i + 1]
            mean_gain = sum(g / 14.0 for g in slice_gains)
            mean_loss = sum(l / 14.0 for l in slice_losses)
            if not math.isfinite(mean_gain) or not math.isfinite(mean_loss):
                raise InputValidationError(
                    f"Nonfinite mean gain or loss for rsi_14 at origin index {i} ({obs.date})",
                    field="rsi_14",
                    reason=f"mean_gain={mean_gain}, mean_loss={mean_loss}",
                )
            rs = mean_gain / max(1e-9, mean_loss)
            if not math.isfinite(rs):
                raise InputValidationError(
                    f"Nonfinite relative strength ratio for rsi_14 at origin index {i} ({obs.date})",
                    field="rsi_14",
                    reason=f"Calculated RS value: {rs}",
                )
            rsi_14 = 100.0 - (100.0 / (1.0 + rs))
            if not math.isfinite(rsi_14):
                raise InputValidationError(
                    f"Nonfinite rsi_14 at origin index {i} ({obs.date})",
                    field="rsi_14",
                    reason=f"Calculated rsi_14 value: {rsi_14}",
                )
        except (OverflowError, ValueError) as exc:
            raise InputValidationError(
                f"Numeric overflow or arithmetic failure calculating rsi_14 at origin index {i} ({obs.date})",
                field="rsi_14",
                reason=str(exc),
            ) from exc

        # 30-session annualized sample volatility (ddof=1) of consecutive 1-session returns
        # Returns from i-29 to i (30 consecutive one-session returns, all non-None)
        window_rets = [r for r in one_session_returns[i - 29 : i + 1] if r is not None]
        if len(window_rets) != 30:
            raise InputValidationError(
                f"Expected 30 returns for vol_30d window at origin index {i}, got {len(window_rets)}",
                field="vol_30d",
                reason=f"Window return count mismatch: {len(window_rets)}",
            )
        try:
            mean_r = sum(r / 30.0 for r in window_rets)
            if not math.isfinite(mean_r):
                raise InputValidationError(
                    f"Nonfinite mean return for vol_30d at origin index {i} ({obs.date})",
                    field="vol_30d",
                    reason=f"Calculated mean_r value: {mean_r}",
                )
            sample_var = sum(((r - mean_r) ** 2) / 29.0 for r in window_rets)
            if sample_var < 0.0:
                sample_var = 0.0
            vol_30d = math.sqrt(sample_var * 252.0)
            if not math.isfinite(vol_30d):
                raise InputValidationError(
                    f"Nonfinite vol_30d at origin index {i} ({obs.date})",
                    field="vol_30d",
                    reason=f"Calculated vol_30d value: {vol_30d}",
                )
        except (OverflowError, ValueError) as exc:
            raise InputValidationError(
                f"Numeric overflow or arithmetic failure calculating vol_30d at origin index {i} ({obs.date})",
                field="vol_30d",
                reason=str(exc),
            ) from exc

        # Relative strength 20d: 0.0 for Nifty-vs-itself
        rel_strength_20d = 0.0

        # Drawdown and MACD Histogram from causal series
        drawdown_val = drawdowns[i]
        macd_hist_val = macd_hist_series[i]

        # Regime classification: trailing SMA50, SMA200, r20, drawdown, and VIX
        p = nifty_closes_float[i]
        try:
            sma50 = _compute_stable_mean(nifty_closes_float[i - 49 : i + 1], 50)
            if not math.isfinite(sma50):
                raise InputValidationError(
                    f"Nonfinite sma50 at origin index {i} ({obs.date})",
                    field="sma50",
                    reason=f"Calculated sma50 value: {sma50}",
                )
        except (OverflowError, ValueError) as exc:
            raise InputValidationError(
                f"Numeric overflow calculating sma50 at origin index {i} ({obs.date})",
                field="sma50",
                reason=str(exc),
            ) from exc

        try:
            sma200 = _compute_stable_mean(nifty_closes_float[i - 199 : i + 1], 200)
            if not math.isfinite(sma200):
                raise InputValidationError(
                    f"Nonfinite sma200 at origin index {i} ({obs.date})",
                    field="sma200",
                    reason=f"Calculated sma200 value: {sma200}",
                )
        except (OverflowError, ValueError) as exc:
            raise InputValidationError(
                f"Numeric overflow calculating sma200 at origin index {i} ({obs.date})",
                field="sma200",
                reason=str(exc),
            ) from exc

        try:
            r20 = (nifty_closes_float[i] / nifty_closes_float[i - 20]) - 1.0
            if not math.isfinite(r20):
                raise InputValidationError(
                    f"Nonfinite 20-session return at origin index {i} ({obs.date})",
                    field="ret_20d",
                    reason=f"Calculated ret_20d value: {r20}",
                )
        except (OverflowError, ValueError) as exc:
            raise InputValidationError(
                f"Numeric overflow calculating ret_20d at origin index {i} ({obs.date})",
                field="ret_20d",
                reason=str(exc),
            ) from exc

        if vix_flt > 26.0:
            regime = REGIME_HIGH_VOLATILITY
        elif p < sma200 and sma50 < sma200 and drawdown_val < -0.15:
            regime = REGIME_BEAR
        elif drawdown_val < -0.08 and p > sma50 and r20 > 0.02:
            regime = REGIME_RECOVERY
        elif p > sma200 and drawdown_val < -0.04 and r20 < -0.015:
            regime = REGIME_CORRECTION
        elif p > sma200 and sma50 >= sma200 and r20 >= 0.0:
            regime = REGIME_BULL
        else:
            regime = REGIME_SIDEWAYS

        payload = PredictorPayload(
            ret_5d=ret_5d,
            rsi_14=rsi_14,
            macd_hist=macd_hist_val,
            vol_30d=vol_30d,
            rel_strength_20d=rel_strength_20d,
            drawdown=drawdown_val,
            market_regime=regime,
        )

        records.append(
            NiftyFeatureRecord(
                origin_index=i,
                origin_date=obs.date,
                origin_close=obs.nifty_close,
                vix_close=obs.vix_close,
                feature_ready=True,
                payload=payload,
                unready_reasons=(),
            )
        )

    return FeatureSeries(
        protocol_id=PROTOCOL_ID,
        axis_start_date=axis_start_date,
        records=tuple(records),
        calendar_status=pair.calendar_status,
        missing_sessions=pair.missing_sessions,
        extra_sessions=pair.extra_sessions,
        nifty_provenance=pair.nifty_series.provenance,
        vix_provenance=pair.vix_series.provenance,
    )
