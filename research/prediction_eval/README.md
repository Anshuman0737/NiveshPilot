# Prediction Evaluation Research Package

`research/prediction_eval` is an offline, inspectable package for evaluating twenty-session directional forecasts on the Nifty 50 Price Index (`nifty50_price_index`) with the India VIX (`india_vix`) as context. It provides deterministic, standard-library CSV loading and exact-date alignment, dated twenty-session outcome determination, point-in-time causal feature calculation with market regime classification, chronological split planning, fixed Laplace empirical class frequency baseline predictions, an optional fixed logistic regression comparator, standard-library three-class prediction scoring and multi-model comparison metrics, paired stationary-bootstrap uncertainty, an offline Node.js replay of the frozen production heuristic, and a study runner that binds every input, tool and artifact to exact bytes.

It evaluates; it does not trade. Trading signal generation, financial risk management and live market execution remain future capabilities, and hyperparameter search, probability recalibration and data acquisition are out of scope. Every test uses synthetic fixtures. Historical evaluation support supplies no data, calendar evidence or human approval; any real study needs separate authority.

## Contents

1. [Orientation: modules and data flow](#orientation-modules-and-data-flow)
2. [Running tests and tools](#running-tests-and-tools)
3. [Module reference](#module-reference)
   - [Inputs and alignment (`inputs.py`)](#inputs-and-alignment-inputspy)
   - [Twenty-session outcomes (`outcomes.py`)](#twenty-session-outcomes-outcomespy)
   - [Causal features (`features.py`)](#causal-features-featurespy)
   - [Chronological split planning (`splits.py`)](#chronological-split-planning-splitspy)
   - [Fixed Laplace frequency baseline (`frequency.py`)](#fixed-laplace-frequency-baseline-frequencypy)
   - [Fixed logistic regression comparator (`logistic.py`)](#fixed-logistic-regression-comparator-logisticpy)
   - [Three-class scoring and comparison (`metrics.py`)](#three-class-scoring-and-comparison-metricspy)
   - [Paired test-loss uncertainty (`uncertainty.py`)](#paired-test-loss-uncertainty-uncertaintypy)
   - [Replay wire serializer (`replay_export.py`)](#replay-wire-serializer-replay_exportpy)
   - [TypeScript replay core, compiler and offline CLI](#typescript-replay-core-compiler-and-offline-cli)
   - [Study runner and result contract (`study.py`, `study_results.py`)](#study-runner-and-result-contract-studypy-study_resultspy)
   - [Historical evaluation support](#historical-evaluation-support)
4. [Limitations, privacy and claims](#limitations-privacy-and-claims)

---

## Orientation: modules and data flow

| Module | Responsibility |
| :--- | :--- |
| `inputs.py` | Loads, validates and chronologically sorts CSV series; exact-date Nifty/VIX alignment |
| `outcomes.py` | Realized twenty-session labels (`BULL`, `BEAR`, `NEUTRAL`) |
| `features.py` | Origin-time causal features and market regime |
| `splits.py` | Chronological partitions, strict-before purging and the refit pool |
| `frequency.py` | Fixed Laplace-1 empirical class frequency baseline |
| `logistic.py` | Fixed L2 logistic comparator (optional scientific environment) |
| `metrics.py` | Three-class scoring and multi-model comparison |
| `uncertainty.py` | Paired stationary bootstrap of TEST Brier-loss differences |
| `replay_export.py`, `replay.cjs` | Python-to-Node replay of the frozen production heuristic |
| `study.py`, `study_results.py` | Configuration, admission, orchestration, artifacts, completion verification and UI display state |

Data flow: `inputs` loads and aligns the series; `outcomes` and `features` derive realized labels and origin-time inputs; `splits` plans partitions from both; `frequency`, `logistic` and the Node replay produce predictions; `metrics` scores them on a shared cohort; `uncertainty` quantifies TEST loss differences; `study` runs the whole sequence and `study_results` owns its artifacts. Outcomes are realized future labels that cannot be accessed at origin time, features are historical inputs available at origin time, and the two pipelines remain strictly isolated.

### Architectural Separation from Fund NAV Cleaner

This package operates independently from the mutual fund NAV cleaning pipeline in `research/clean_data.py`. The two modules serve distinct domains with contrasting integrity requirements:

| Property | Fund NAV Cleaner (`research/clean_data.py`) | Prediction Eval Input (`research/prediction_eval`) |
| :--- | :--- | :--- |
| **Primary Domain** | Mutual fund scheme daily NAVs | Market index series (`nifty50_price_index`, `india_vix`) |
| **Deduplication Policy** | Heuristic deduplication (`keep="last"`) | Zero tolerance: duplicate dates are fatal errors reporting both locations |
| **Numeric Representation** | Standard IEEE floating-point numbers | Exact `decimal.Decimal` preserving source precision in raw loader (`inputs.py`) and exact rational fractions in outcomes (`outcomes.py`); features layer (`features.py`) converts to standard IEEE binary64 `float` with finite guards for quantitative features matching TypeScript prediction engine schema |
| **Data Quality Policy** | Drops nonpositive NAV rows, keeps latest duplicate date, and flags abnormal jumps (>15% equity, >1% liquid) | Globally rejects duplicate dates, preserves strictly positive plain-decimal Closes, and emits advisory warnings for OHLC discrepancies without modifying Close |
| **Alignment Architecture** | Benchmark merge and forward-fill logic belong downstream in research/build_features.py | Direct exact-date pairing; never forward-fills or drops intermediate sessions |
| **Dependencies** | Requires `pandas`, `numpy`, and filesystem configs | Pure Python standard library with zero runtime dependencies for foundation modules; separate optional environment with pinned scikit-learn lock for logistic comparator |

---

## Running tests and tools

All tests rely on synthetic fixtures generated in isolated temporary directories and require zero live market data. Run every command from the repository root.

### Pure standard-library suites

The seven foundation modules run under the pure standard-library runner:

```powershell
python -E -B -S -m unittest -v research.prediction_eval.tests.test_inputs research.prediction_eval.tests.test_outcomes research.prediction_eval.tests.test_features research.prediction_eval.tests.test_splits research.prediction_eval.tests.test_frequency research.prediction_eval.tests.test_replay_export research.prediction_eval.tests.test_metrics
```

The study result contract and the pure study runner tests need no third-party package either:

```powershell
python -E -B -S -m unittest -v research.prediction_eval.tests.test_study_results research.prediction_eval.tests.test_study.TestStudyPure
```

* `-E`: Ignores all `PYTHON*` environment variables.
* `-B`: Prevents writing `.pyc` bytecode files.
* `-S`: Disables automatic site initialization (suppressing site-specific packages and site paths). The synthetic test command runs from the repository root; reliance on standard library modules alone is an implementation source property rather than an interpreter security sandbox.

### Logistic comparator environment

The comparator requires an isolated virtual environment containing the exact admitted distribution set for Windows AMD64 on CPython 3.12:

* `scikit-learn==1.9.1`
* `numpy==2.4.3`
* `scipy==1.17.1`
* `narwhals==2.28.0`
* `joblib==1.6.0`
* `threadpoolctl==3.7.0`
* `cloudpickle==3.1.2`

These requirements are locked with exact wheel hashes in `requirements-logistic.txt`. The foundation modules (`inputs.py`, `outcomes.py`, `features.py`, `splits.py`, `frequency.py`, `replay_export.py`) remain completely independent of external packages and continue to run under pure Python standard library flags (`-E -B -S`).

Run the dedicated logistic comparator test suite within the admitted virtual environment using strict warning flags:

```powershell
.\build\prediction-eval\venv-logistic\Scripts\python.exe -E -s -B -W error::FutureWarning -m unittest -v research.prediction_eval.tests.test_logistic
```

### Study integration tests and synthetic rehearsal

Run the study integration tests in the admitted logistic virtual environment with Node set:

```powershell
$env:NIVESH_EVAL_NODE = "C:\Program Files\nodejs\node.exe"
.\build\prediction-eval\venv-logistic\Scripts\python.exe -E -s -B -W error::FutureWarning -m unittest -v research.prediction_eval.tests.test_study
```

Run the dedicated 24M position synthetic rehearsal ($N=4748, n=800, B=10000$). Its configuration sets the 24000000 cap explicitly, and the test asserts that cap, all three block lengths available, $n=800$, $B=10000$ and 24000000 visited positions. It does not prove real optimizer difficulty, multi-file or approval overhead, real OS failure behavior or final real-run timing:

```powershell
$env:NIVESH_EVAL_NODE = "C:\Program Files\nodejs\node.exe"
.\build\prediction-eval\venv-logistic\Scripts\python.exe -E -s -B -W error::FutureWarning -m unittest -v research.prediction_eval.tests.test_study.TestS3Rehearsal.rehearse_full_size_synthetic
```

### Python-to-Node roundtrip

Run the cross-language Python-to-Node integration test suite:

```powershell
python -E -B -S -m unittest -v research.prediction_eval.tests.test_replay_roundtrip
```

It supports portable test-only environment controls:

* `NIVESH_EVAL_NODE`: Explicit path to native Node.js executable (falls back to `node` on `PATH`).
* `NIVESH_EVAL_WORK_DIR`: Dedicated working directory for exclusive request file creation.
* `NIVESH_EVAL_CHILD_LOG_DIR`: Destination directory for raw stdout/stderr logs and typed JSON child records.

### Node replay compiler, CLI and suites

* **Compile Candidate Replay Artifacts**:
  ```powershell
  node research/prediction_eval/compile_replay.cjs candidate
  ```
* **Execute Offline Replay CLI**:
  ```powershell
  node research/prediction_eval/replay.cjs path/to/input.json
  ```
* **Run Full Candidate Synthetic Unit Test Suite (Portable)**:
  ```powershell
  node --test --test-concurrency=1 research/prediction_eval/tests/test_replay.cjs
  ```
* **Run Supplemental Baseline vs Candidate Lifecycle Verification**:
  ```powershell
  node research/prediction_eval/tests/test_replay.cjs --verify-lifecycle 04360BA971E965BAF67F55229CB1621991856C9F069E4A5034167B5FCAB4E7C9
  ```

---

## Module reference

### Inputs and alignment (`inputs.py`)

#### `load_series(series_id, files)`

Loads, parses, validates, and chronologically sorts one or more CSV files for a declared series identifier.

```python
from research.prediction_eval.inputs import load_series, FileInputSpec

# Simple loading from one or more file paths
nifty_series = load_series(
    "nifty50_price_index",
    ["data/nifty_part1.csv", "data/nifty_part2.csv"]
)

# Loading with caller-declared provenance metadata
spec = FileInputSpec(
    file_path="data/india_vix.csv",
    source_url="https://example.com/vix.csv",
    source_use_note="Official exchange historical data extract"
)
vix_series = load_series("india_vix", spec)
```

* **Supported Series IDs**: Strictly `"nifty50_price_index"` and `"india_vix"`. Unsupported declared series identifiers are rejected. The loader validates only the caller-declared series identifier; successful parsing and cryptographic hashing identify raw bytes and schema validity, but do not authenticate the underlying financial instrument, provider authenticity, source rights, or calendar completeness. Caller declarations remain distinct from observed bytes and ranges.
* **Byte-Level Invariants**: Reads raw bytes once for cryptographic SHA-256 hashing and UTF-8 decoding (with automatic BOM stripping). Original files are never modified, rewritten, or normalized in place.
* **Schema Requirements**: Comma-separated CSV format. Headers are stripped and normalized via case-folding. Every record must match the header field count. Headers must uniquely include `Date` and `Close`. Blank records and empty or header-only files raise `InputValidationError`.
* **Failure Locations**: CSV parser errors identify the consumed physical line or multiline record span in both the message and `InputValidationError.line`, preserving the parser reason. Header-only errors identify the parsed header location or span. Empty files with no header have no invented header location.
* **Date Parsing**: Strictly accepts `dd-MMM-yyyy` or `dd MMM yyyy`: two ASCII day digits, three ASCII English month letters (case-insensitive), four ASCII year digits, and matching separators (two hyphens or two single ASCII spaces). Outer cell whitespace is stripped; mixed separators, doubled/internal non-ASCII spaces or tabs, trailing junk, and numeric formats are rejected. Both forms reject impossible calendar dates (such as `29-Feb-2023` or `31 Apr 2024`).
* **Close Price Parsing**: Strictly accepts positive plain decimal syntax (`[+-]?[0-9]+(?:\.[0-9]+)?` with value > 0). Values are retained as `decimal.Decimal` without floating-point conversion, rounding, or quantization.
* **Duplicate Rejection**: Duplicate dates within the same file or across multiple files are strictly rejected as `DuplicateDateError`, identifying both physical file paths and CSV line numbers.
* **Advisory OHLC Warnings**: When optional Open, High, or Low columns exist, discrepancies (such as Close outside Low/High bounds, Low exceeding High, or unparseable values) emit `InputWarning` entries without modifying the Close price or discarding the date.
* **Chronological View**: Records across all supplied files are exposed in strictly increasing date order.

#### `align_pair(nifty_series, vix_series, expected_sessions=None)`

Aligns India VIX daily observations onto the master chronological Nifty 50 date axis.

```python
from research.prediction_eval.inputs import align_pair

pair = align_pair(nifty_series, vix_series)

# Access aligned observations
for obs in pair.aligned_observations:
    # obs.date: datetime.date
    # obs.nifty_close: Decimal
    # obs.vix_close: Optional[Decimal] (None if missing on this trading date)
    pass
```

* **Master Sequence Ownership**: The Nifty 50 sequence owns the chronological axis. Intermediate Nifty sessions are never dropped or forward-filled.
* **Missing VIX Handling**: When an India VIX observation is absent on a Nifty trading date, the observation is retained with `vix_close = None`. The master sequence indices remain intact.
* **Asymmetric Date Visibility**: Dates present in Nifty but absent in VIX are exposed in `nifty_only_dates`. Dates present in VIX but absent in Nifty are exposed in `vix_only_dates` and are never appended to the master aligned axis.
* **Calendar Verification**: When an optional `expected_sessions` sequence of `datetime.date` objects is supplied:
  * Sequence must be strictly increasing with unique valid dates.
  * `calendar_status` reports `"matches_supplied_sessions"` if exact match, or `"mismatch"` otherwise, detailing `missing_sessions` and `extra_sessions`.
  * If omitted, `calendar_status` reports `"not_checked"`.

### Twenty-session outcomes (`outcomes.py`)

`compute_twenty_session_outcomes(series)` computes realized twenty-session forward outcomes and exact directional movement classifications (`BULL`, `BEAR`, `NEUTRAL`) for chronological Nifty 50 observations.

```python
from research.prediction_eval.inputs import load_series
from research.prediction_eval.outcomes import compute_twenty_session_outcomes

nifty_series = load_series("nifty50_price_index", "data/nifty50.csv")
outcome_series = compute_twenty_session_outcomes(nifty_series)

for outcome in outcome_series:
    # outcome.origin_index: int (positional index on supplied Nifty axis)
    # outcome.origin_date: datetime.date
    # outcome.origin_close: Decimal
    # outcome.is_mature: bool (True if horizon session i+20 exists)
    # outcome.status: "mature" | "unknown"
    # outcome.maturity_index: Optional[int] (origin_index + 20)
    # outcome.maturity_date: Optional[datetime.date]
    # outcome.maturity_close: Optional[Decimal]
    # outcome.outcome_class: Optional[str] ("BULL", "BEAR", "NEUTRAL", or None)
    pass
```

* **Positional Session Counting**: Future position is strictly positional `origin_index + 20` on the supplied sorted Nifty records. It is not calendar-day arithmetic; missing dates, holidays, or synthetic weekend trading sessions do not alter the positional sequence.
* **Independence from VIX**: Outcomes depend exclusively on the Nifty series. Missing VIX observations never filter, compress, forward-fill, or alter the outcome axis. The outcome API does not accept or require a VIX series.
* **Preservation and Unknown Tail**: Every origin observation is preserved. The final `min(20, N)` origins are explicitly unmatured (`is_mature = False`, `status = "unknown"`, with maturity fields and `outcome_class` as `None`). A sequence of length <= 20 has zero mature outcomes; a sequence of 21 has exactly one mature outcome (origin 0 at index 20).
* **Exact Classification**:
  * `BULL` if `(C20 / C0) - 1 > 0.005` (equivalently `200 * C20 > 201 * C0`).
  * `BEAR` if `(C20 / C0) - 1 < -0.005` (equivalently `200 * C20 < 199 * C0`).
  * `NEUTRAL` otherwise, including both exact boundaries `200 * C20 == 201 * C0` (+0.5%) and `200 * C20 == 199 * C0` (-0.5%).
* **Context-Independent Exact Numerics**: Uses standard-library `fractions.Fraction` exact rational representation. Class decisions are completely immune to ambient `decimal.Context` precision limits and rounding traps (such as `Inexact`, `Rounded`, or `Subnormal`), and avoid binary floating-point representation drift.
* **Role and Type Validation**: Requires a loader-produced `LoadedSeries` for `nifty50_price_index`. Supplying other series identifiers (such as `india_vix`) or invalid types raises `InputValidationError`.
* **Pure In-Memory API**: Operates strictly in memory with zero file I/O, network calls, or side effects. Outcome records are frozen immutable dataclasses.

### Causal features (`features.py`)

`compute_nifty_features(pair)` computes causal Nifty 50 quantitative features and market regime classifications for an aligned Nifty/VIX pair under protocol `nifty-close-features-v1`.

```python
from research.prediction_eval.inputs import align_pair, load_series
from research.prediction_eval.features import compute_nifty_features

nifty_series = load_series("nifty50_price_index", "data/nifty50.csv")
vix_series = load_series("india_vix", "data/india_vix.csv")
pair = align_pair(nifty_series, vix_series)

feature_series = compute_nifty_features(pair)

for rec in feature_series:
    # rec.origin_index: int (positional index on supplied Nifty axis)
    # rec.origin_date: datetime.date
    # rec.origin_close: Decimal
    # rec.vix_close: Optional[Decimal]
    # rec.feature_ready: bool (True if index >= 200 and VIX present)
    # rec.unready_reasons: Tuple[str, ...] ('warmup', 'missing_vix', or both)
    # rec.payload: Optional[PredictorPayload] (None when unready)
    if rec.feature_ready:
        payload = rec.payload
        # payload.ret_5d: float (5-session return ratio)
        # payload.rsi_14: float (14-period rolling RSI, 0.0 to 100.0)
        # payload.macd_hist: float (MACD histogram percentage points)
        # payload.vol_30d: float (30-session annualized volatility ratio, ddof=1)
        # payload.rel_strength_20d: float (0.0 for Nifty-vs-itself)
        # payload.drawdown: float (Peak-to-trough drawdown from dataset inception)
        # payload.market_regime: str ('Bull', 'Bear', 'Correction', 'Recovery', 'Sideways', 'High-volatility')
```

* **Causal Prefix Ownership**: At origin index $i$, price features use exclusively historical Nifty observations $0 \dots i$ and regime uses exact-date India VIX at index $i$. Future prices ($i+1 \dots$) and future outcome labels are never accessed or back-propagated.
* **Warmup Guard and Missing VIX**:
  * Origin indices $i < 200$ have `feature_ready = False`, `payload = None`, and include unready reason `'warmup'`.
  * The first mathematically possible feature-ready origin is index 200 (requiring 201 supplied closes: $i=0 \dots 200$).
  * If India VIX is absent at origin $i$, the row is retained with `feature_ready = False`, `payload = None`, and reason `'missing_vix'`.
  * When both conditions hold, reasons are exposed in deterministic order: `('warmup', 'missing_vix')`.
  * Missing VIX at origin $i$ affects exclusively origin $i$; price features and neighboring origin readiness are never corrupted or shifted.
* **Predictor Payload Schema**:
  * Exactly six numeric fields plus `market_regime` matching the `CorePredictorFeatures` interface (`src/engine/marketIntelligence/forecastCore.ts:9-17`), whose fields are read by `computeDirectionalForecastCore` (`forecastCore.ts:38-62`): `ret_5d`, `rsi_14`, `macd_hist`, `vol_30d`, `rel_strength_20d`, `drawdown`, and `market_regime`.
  * No fallback defaults are applied at calculation time: legitimate zero returns, volatility, and RSI remain `0.0`.
* **Formula Specifications (`nifty-close-features-v1`)**:
  * `ret_5d`: $C_i / C_{i-5} - 1.0$ (decimal ratio; $0.01$ denotes 1%).
  * `vol_30d`: Sample standard deviation ($\text{ddof}=1$) of the last 30 available consecutive one-session returns annualized by $\sqrt{252}$ (decimal ratio, not percentage points).
  * `drawdown`: $(C_i - \text{Peak}_i) / \text{Peak}_i$, where $\text{Peak}_i = \max(C_0 \dots C_i)$ from the first supplied observation.
  * `rsi_14`: Simple rolling arithmetic mean of gains and losses over the last 14 entries with a $10^{-9}$ denominator floor. Flat price history yields $\text{RSI} = 0.0$.
  * `macd_hist`: Recursive $\text{EMA}_{12}$ and $\text{EMA}_{26}$ seeded at $C_0$, with Signal line as recursive $\text{EMA}_9$ of MACD seeded at $0.0$. Histogram is $((\text{MACD} - \text{Signal}) / C_i) \times 100.0$ in percentage points.
  * `rel_strength_20d`: $0.0$ for this Nifty-versus-itself single-asset foundation.
* **Ordered Regime Classification**:
  Evaluated strictly in priority order for $i \ge 200$ with VIX present:
  1. `High-volatility` if $\text{VIX}_i > 26.0$.
  2. `Bear` if $C_i < \text{SMA}_{200}$ and $\text{SMA}_{50} < \text{SMA}_{200}$ and $\text{drawdown} < -0.15$.
  3. `Recovery` if $\text{drawdown} < -0.08$ and $C_i > \text{SMA}_{50}$ and $r_{20} > 0.02$.
  4. `Correction` if $C_i > \text{SMA}_{200}$ and $\text{drawdown} < -0.04$ and $r_{20} < -0.015$.
  5. `Bull` if $C_i > \text{SMA}_{200}$ and $\text{SMA}_{50} \ge \text{SMA}_{200}$ and $r_{20} \ge 0.0$.
  6. `Sideways` otherwise.
* **Immutable Output**: Per-origin records (`NiftyFeatureRecord`) and payload records (`PredictorPayload`) are frozen dataclasses.
* **Role and Type Validation**: Requires an `AlignedPair` with declared series roles `'nifty50_price_index'` and `'india_vix'`. Invalid types or swapped series raise `InputValidationError`.
* **Numeric Representation and Truthful Error Handling**:
  * Raw loader parses prices as exact `Decimal`. The features calculation layer converts prices and exact-date VIX to standard IEEE 754 binary64 `float` values to produce the numeric predictor payload fields.
  * Intermediate and derived arithmetic strictly guards against overflow and nonfinite numbers. Converting non-positive, NaN, underflow to 0.0, or infinite values raises contextual `InputValidationError`.
  * Intermediate calculations (such as stable trailing 50- and 200-session SMAs preserving subnormal and large finite values without premature underflow or overflow, rolling RSI gain/loss sums, and return squared deviations in 30-session volatility) compute valid finite values without premature overflow, and translate any unrepresentable arithmetic overflow into an explicit `InputValidationError` identifying the failing field, date, and origin index rather than emitting masked or false finite-looking categories.
* **Series Metadata and Summary Properties**:
  * `FeatureSeries` exposes top-level provenance and alignment metadata alongside origin records:
    * `protocol_id`: Identifier for the calculation protocol (`nifty-close-features-v1`).
    * `axis_start_date`: Date of the earliest origin on the master Nifty axis.
    * `calendar_status`: Alignment verification status (`matches_supplied_sessions`, `mismatch`, or `not_checked`).
    * `missing_sessions` and `extra_sessions`: Discrepancy date tuples.
    * `nifty_provenance` and `vix_provenance`: Cryptographic file provenance tuples.
    * Summary properties: `total_origins` (total origin count), `ready_count` (origins with feature readiness), `unready_count` (unready origin count), `ready_records`, `unready_records`, and `features` (alias for `records`).
* **Mathematical Readiness Boundary**:
  * Feature readiness reflects strictly mathematical availability on the supplied chronological observations (requiring 201 available trading sessions for the 200-session lookback window). It does not certify real-world exchange calendar completeness, source data authentication, or predictive forecasting efficacy.

### Chronological split planning (`splits.py`)

`build_split_plan` plans chronological evaluation partitions on common-date feature and twenty-session outcome series without model fitting, feature recomputation, or data downloading.

```python
import datetime
from research.prediction_eval.splits import build_split_plan

# Synthetic placeholder dates for illustration only: real cutoffs are chosen by the
# caller and must each be an exact member of the supplied origin axis
plan = build_split_plan(
    feature_series,
    outcome_series,
    development_start=datetime.date(2022, 1, 3),
    test_start=datetime.date(2023, 1, 2),
)

# Immutable index pools (original axis integers)
train_indices = plan.train_indices            # tuple of retained train origin indices
development_indices = plan.development_indices # tuple of retained dev origin indices
refit_indices = plan.refit_indices            # tuple of refit-eligible origin indices (< test_start)
test_indices = plan.test_indices              # tuple of retained test origin indices

# Origin decisions for every observation in the original sequence
for decision in plan.decisions:
    # decision.origin_index: int
    # decision.origin_date: datetime.date
    # decision.partition: "train" | "development" | "test"
    # decision.exclusion_reasons: Tuple[str, ...] (empty if retained)
    # decision.in_refit: bool (True if eligible for final refit pool)
    pass
```

* **Calendar Prerequisite**: Features `calendar_status` must be `"matches_supplied_sessions"` with empty discrepancy tuples (`missing_sessions=()`, `extra_sessions=()`). This verifies consistency with a caller-supplied session calendar; it does not authenticate exchange-calendar completeness, trading-day legitimacy, or source rights.
* **Axis Alignment**: Features and outcomes must share identical, strictly increasing origin dates, contiguous indices ($i = 0 \dots N-1$), and numerical Close agreement.
* **Boundary Dates**: Caller-supplied `development_start` ($D$) and `test_start` ($T$) dates must exist on the origin axis and satisfy $0 < D < T < N$, ensuring every raw partition is non-empty. Real study dates remain unselected until data coverage and protocol admission.
* **Base Exclusion Reasons**: Each decision lists base reasons in this fixed order: `'warmup'` (origin index below 200), `'missing_vix'` (no exact-date India VIX), then `'unknown_outcome'` (no observed session twenty positions ahead). One origin can carry several base reasons, so per-reason counts can overlap and are not distinct excluded-row counts. The partition purges below apply only to origins with no base reason.
* **Strict-Before Boundary Purging**:
  * **Train Partition** ($i < D$): Base-eligible rows require realized outcome labels strictly before development start ($\text{maturity\_index} < D$); otherwise excluded with reason `'label_crosses_development_boundary'`.
  * **Development Partition** ($D \le i < T$): Base-eligible rows require realized outcome labels strictly before test start ($\text{maturity\_index} < T$); otherwise excluded with reason `'label_crosses_test_boundary'`.
  * **Test Partition** ($i \ge T$): Retains all base-eligible rows; the final unknown tail is excluded with reason `'unknown_outcome'`.
* **Separate Final Refit Pool**: All base-eligible origins $i < T$ with $\text{maturity\_index} < T$, drawn from both train and development raw partitions. An origin purged at the development boundary (e.g. maturing at $D$) can re-enter refit if it matures strictly before test start ($T$). Test origins cannot enter either fitting pool.
* **Assigned-Partition Reasons versus Refit Membership**: `exclusion_reasons` describe only the origin's assigned raw partition, while `in_refit` is decided separately. A training origin excluded with `'label_crosses_development_boundary'` keeps that reason yet has `in_refit=True` when its label matures before $T$; a development origin excluded with `'label_crosses_test_boundary'` never enters refit.
* **Honest Empty Pools**: When all observations are unready or unknown, `SplitPlan` returns honest empty index tuples (`train_indices=()`, `development_indices=()`, `refit_indices=()`, `test_indices=()`).
* **Errors**: Malformed or inconsistent inputs raise `InputValidationError` (from `inputs.py`) before any plan is built. Its `field` attribute names the responsible input, for example `records`, `origin_date`, `calendar_status`, `development_start` or `maturity_index`, and the message includes the origin index or date where one applies.

### Fixed Laplace frequency baseline (`frequency.py`)

`build_frequency_predictions(features, outcomes, *, development_start, test_start)` generates deterministic, inspectable Laplace-smoothed empirical class frequency predictions for chronological evaluation partitions planned by `build_split_plan`, establishing the foundational empirical benchmark comparator.

```python
import datetime
from research.prediction_eval.frequency import build_frequency_predictions

# Synthetic placeholder dates for illustration only: real cutoffs are chosen by the
# caller and must each be an exact member of the supplied origin axis
result = build_frequency_predictions(
    feature_series,
    outcome_series,
    development_start=datetime.date(2022, 1, 3),
    test_start=datetime.date(2023, 1, 2),
)

# Top-level comparator metadata
method = result.method                         # "fixed-laplace1-frequency-v1"
alpha = result.alpha                           # 1.0
ordered_classes = result.classes               # ("BEAR", "NEUTRAL", "BULL")
series_id = result.series_id                   # "nifty50_price_index"
horizon = result.horizon_sessions              # 20
protocol = result.protocol_id                  # "nifty-close-features-v1"
outcome_def = result.outcome_definition        # "close-return-20-session-half-percent-neutral-inclusive-v1"
plan = result.plan                             # Canonical SplitPlan instance

# Development block (fitted strictly on plan.train_indices)
dev_block = result.development_block
dev_fit = dev_block.fit                        # FrequencyFit or None
dev_preds = dev_block.predictions              # tuple of FrequencyPrediction records
dev_reason = dev_block.unavailable_reason      # None or "no_fit_rows"

# Test block (fitted strictly on plan.refit_indices)
test_block = result.test_block
test_fit = test_block.fit                      # FrequencyFit or None
test_preds = test_block.predictions            # tuple of FrequencyPrediction records
test_reason = test_block.unavailable_reason    # None or "no_fit_rows"
```

* **Delegation to Canonical Plan**: Calls `build_split_plan` once with the exact caller cutoffs. Accepts no caller-supplied plan, custom fitting indices, prior distributions, smoothing parameters, or online update modes.
* **Two Independent Fixed Fits**:
  * **Development Block**: Fits strictly on `plan.train_indices` once; generates predictions for `plan.development_indices` in original order. The strict label cutoff is `plan.development_start_index` and `plan.development_start`. This fit is never updated with realized development outcomes when constructing the test refit.
  * **Test Block**: Fits strictly on `plan.refit_indices` once; generates predictions for `plan.test_indices` in original order. The strict label cutoff is `plan.test_start_index` and `plan.test_start`. This pool includes origins purged at the first boundary that become mature before test start; no test-origin or post-cutoff label ever enters either fit.
* **Laplace Smoothing ($\alpha = 1$)**: For class counts $c = (b, n, u)$ in fixed order (`BEAR`, `NEUTRAL`, `BULL`) and total fitting observations $N = b + n + u$, smoothed probabilities are $((b + 1) / (N + 3), (n + 1) / (N + 3), (u + 1) / (N + 3))$. Ratios are preserved as standard IEEE binary64 floats without display rounding, clipping, or renormalization, summing to 1 within absolute $10^{-12}$. In non-empty fitting pools, observing one, two, or all three classes remains valid after smoothing, with individual class counts permitted to be zero. A fitting pool with zero observations yields the unavailable 'no_fit_rows' state.
* **Unavailable Fitting and Empty Target States**:
  * **Zero Fitting Rows**: If a fitting pool has zero observations, `fit = None`, `unavailable_reason = "no_fit_rows"`, and `predictions = ()`, while retaining canonical requested target indices. Development unavailable state can coexist with a valid refit/test block.
  * **Empty Target Pool**: If a fitting pool is non-empty but the target pool has zero observations, `fit` is preserved, `predictions = ()`, and `unavailable_reason = None`.
* **Output Immutability and Provenance Boundary**: All returned structures (`FrequencyResult`, `FrequencyBlock`, `FrequencyFit`, `FrequencyPrediction`) are frozen immutable dataclasses. Source files, `FeatureSeries`, and `OutcomeSeries` are never mutated. `FileProvenance` references are not copied into prediction records; provenance tracking remains with the input caller.

### Fixed logistic regression comparator (`logistic.py`)

The `research.prediction_eval.logistic` module evaluates a fixed, inspectable L2-regularized multinomial logistic regression comparator using standardized numeric features and one-hot encoded market regimes, providing an inspectable learned comparator for offline evaluation against the chronological baseline. It needs the [admitted logistic environment](#logistic-comparator-environment).

```python
import datetime
from research.prediction_eval.logistic import build_logistic_predictions

# Synthetic placeholder dates for illustration only: real cutoffs are chosen by the
# caller and must each be an exact member of the supplied origin axis
logistic_result = build_logistic_predictions(
    features=feature_series,
    outcomes=outcome_series,
    development_start=datetime.date(2021, 10, 1),
    test_start=datetime.date(2022, 4, 1),
)

dev_block = logistic_result.development_block
test_block = logistic_result.test_block
```

* **Plan Delegation**: Delegates once to `build_split_plan` using exact caller cutoffs. Accepts no caller plan, fitting indices, or tuning knobs.
* **Shared Schema Validation**: Validates all selected fitting and target payloads across both blocks before assessing availability. Rejects unsupported types, booleans, and non-finites as `InputValidationError`.
* **Fixed Model Parameters**: Admitted scikit-learn 1.9.1 configuration with `l1_ratio=0.0`, `C=1.0`, solver `lbfgs`, `fit_intercept=True`, `tol=1e-6`, `max_iter=2000`, `class_weight=None`, `warm_start=False`, `verbose=0`.
* **Fitted State and Reconstruction**: `LogisticFit` records the scaler means, variances and scales, coefficients ($3 \times 12$), intercepts (3), and iteration count, with the declared class and feature order. This is enough to recompute every returned probability without production helpers; the synthetic tests do so to within $10^{-12}$.
* **Input Units and Standardization**: The six numeric inputs keep their existing `PredictorPayload` units: decimal-ratio returns, volatility and drawdown, RSI on a 0 to 100 scale, MACD histogram in percentage points, and the constant `0.0` Nifty-versus-itself relative strength. The comparator does not rescale them itself. Each block then standardizes them with a `StandardScaler` fitted only on that block's fitting rows, preserving actual scaler scale values (including unit scale on the constant zero relative strength), so coefficients apply to per-fit z-scores, not to the original units. The six regime indicators are appended unscaled in fixed `features.VALID_REGIMES` order.
* **Three-Class Study Policy**: A block is fitted only when its fitting rows contain all three classes; otherwise it returns `missing_training_classes`. This is a policy of this three-class study. Binary logistic regression is mathematically valid but outside this policy. No other minimum sample size is applied, and a successful fit does not establish statistical adequacy.
* **Returned Block Metadata**: Every returned block, available or not, keeps `partition`, `fitting_indices`, `requested_indices`, `cutoff_index`, `cutoff_date`, `class_counts` (`BEAR`, `NEUTRAL`, `BULL`) and `regime_counts` (`features.VALID_REGIMES` order). Both count tuples sum to the fitting-pool length, and an empty pool has zero counts. `fit` is `None` exactly when `unavailable_reason` is set, and an unavailable block has no predictions. `failure_stage` is `scaler`, `fit` or `prediction` for numerical failures and `None` otherwise. Invalid selected payloads, planner input errors and unexpected setup, dependency or programming errors raise instead of returning a block. Returned structures (`LogisticResult`, `LogisticBlock`, `LogisticFit`, `LogisticPrediction`) are frozen dataclasses.
* **Empty Targets**: A valid fit with no requested targets is kept with `predictions = ()`, and prediction is not attempted.
* **Raw Probabilities**: Probabilities are the estimator's raw binary64 values in `BEAR`, `NEUTRAL`, `BULL` order, checked to be finite, in $[0, 1]$ and summing to 1 within $10^{-12}$. They are not rounded, clipped or renormalized. Exact zeros are valid outputs, and any later scoring must handle them explicitly.
* **Serial Calls and Warning Ownership**: Warning filters change only around `estimator.fit` (narrowly scoped `warnings.catch_warnings(record=False)`), where `ConvergenceWarning` becomes an error that maps to `not_converged`, and the surrounding filters are restored on exit. Because Python warning filters are process-wide, comparator calls must run serially. Other warning categories follow the caller's policy: under the test command's `-W error::FutureWarning` a `FutureWarning` raises, and an enabled `RuntimeWarning` stays visible. Serial calls do not make the numerical libraries single-threaded. The comparator does not change BLAS or OpenMP thread pools; the caller controls them, and the dependency tests limit them to one thread with `threadpoolctl` while each test runs.
* **Closed Failure Modes**: The closed vocabulary (`no_fit_rows`, `missing_training_classes`, `not_converged`, `nonfinite_model_state`) has deterministic precedence. Blocks clearly distinguish simple data insufficiency (`no_fit_rows`, `missing_training_classes`) from numerical failure stages (`scaler`, `fit`, `prediction`). A prediction-stage failure discards that block's fit and all of its predictions.
* **Synthetic Oracle Diagnostic**: The nonconstant-fixture test prints one stdout line starting with `SYNTHETIC_ORACLE_DIAGNOSTIC: ` followed by a JSON object. For each block it records the cutoff, fitting and requested indices with their counts, class and regime counts, `n_iter`, the recorded scaler and model state, and the measured forward-reconstruction, gradient and negative-control values. It also records the fixed configuration, the feature, regime and class order, the NumPy, SciPy and scikit-learn versions, and the `threadpoolctl` thread-pool report, which includes local library paths.

### Three-class scoring and comparison (`metrics.py`)

The `research.prediction_eval.metrics` module provides standard-library scoring and comparison of heuristic, frequency, and logistic model predictions against realized three-class twenty-session outcomes.

```python
from research.prediction_eval.metrics import EvaluationOrigin, score_comparison

# Score three models across a shared validated origin cohort
comparison = score_comparison(
    origins=origins_cohort,
    heuristic=heuristic_predictions,
    frequency=frequency_predictions,
    logistic=logistic_predictions,
)

heuristic_metrics = comparison.heuristic
frequency_metrics = comparison.frequency
logistic_metrics = comparison.logistic
```

#### Mathematical and scoring policies

1. **Cohort Specification**: The scorer measures three prediction models (`heuristic`, `frequency`, `logistic`) against an explicit, caller-supplied sequence of $N$ `EvaluationOrigin` observations. Each origin contains a non-negative positional index, exact calendar date, and realized outcome class (`BEAR`, `NEUTRAL`, or `BULL`). Indices and dates must strictly increase. Upstream pipelines retain responsibility for establishing maturity, filtering, and canonical eligibility; the scorer does not reconstruct prices or impute missing dates.
2. **Three-Class Brier Score**: Computed per row as $\sum_{k=1}^3 (p_k - \mathbf{1}_{k=\text{actual}})^2$, where $k$ spans `BEAR`, `NEUTRAL`, and `BULL`. The model `mean_brier` is the arithmetic mean across all $N$ cohort rows. No binary half-scaling or division by 3 is applied, ensuring direct compatibility with raw multi-class probability vectors.
3. **Exact Log Loss Policy**: Evaluated as $-\ln(p_{\text{actual}})$. Positive binary64 floats, including subnormal values, are evaluated directly without flooring or artificial clipping. Non-actual zero probabilities remain finite. If the realized class has exact probability $0.0$ (including $-0.0$), the row record assigns `log_loss = None`, `log_loss_state = "infinite"`, and increments `zero_actual_probability_count`. If any row in the cohort is infinite, the model's `mean_log_loss` is `None` with `log_loss_state = "infinite"`. When all rows have positive realized probability, `mean_log_loss` is the arithmetic mean across all $N$ rows with `log_loss_state = "finite"`.
4. **Deterministic Tie Breaking and Predicted Class**: The predicted class is the exact first maximum in `BEAR`, `NEUTRAL`, `BULL` order. Near-tie tolerances are excluded. `tie_count` counts rows where at least two maximum components are exactly equal; equal non-maximum components do not increment ties.
5. **Confusion Matrix and Recall**: Confusion matrix rows represent realized actual classes, and columns represent predicted classes, ordered `(BEAR, NEUTRAL, BULL)`. `class_recall[k]` is the diagonal value divided by actual support for class $k$, or `None` if support is zero. `accuracy` is total diagonal count divided by $N$.
6. **Descriptive Reliability Calibration**: For each model and class, 10 bins partition probabilities $[0.0, 1.0]$ (30 bins per model, in class-major order). Interior edge transitions follow intervals $[0, 0.1), [0.1, 0.2), \dots, [0.9, 1.0]$ using `bisect_right` on the nine binary64 interior edges $(0.1, 0.2, \dots, 0.9)$, so that interior-edge equality enters the right bin. Exact $0.0$ maps to bin 0; exact $0.9$ and $1.0$ map to bin 9; `nextafter(0.9, 0.0)` maps to bin 8. Each bin records observation count, mean raw predicted probability, and empirical one-vs-rest observed frequency. Empty bins retain `count = 0` and `None` for both means. Per-class bin counts sum to $N$, and all 30 bins sum to $3N$. These fixed bins represent a descriptive reporting convention with sparse and dependent-observation limits across overlapping 20-session outcomes; they do not introduce sample-size thresholds or represent formal calibration curves.
7. **Empty Cohort Contract ($N=0$)**: Scored empty cohorts produce `status = "empty"`, `sample_count = 0`, support `(0, 0, 0)`, zero confusion matrix, `None` for recalls, accuracy, and mean losses, `log_loss_state = "empty"`, zero tie and zero-probability counts, and 30 empty reliability bins per method.

#### Upstream runner integration and error handling

* **Cohort Alignment**: Requires all four containers to be native lists or tuples of identical length $N$. Each model must supply exactly $N$ predictions aligned 1-to-1 with the cohort origins. If a method drops a row, reorders predictions, or diverges in index or date, `score_comparison` raises `InputValidationError` identifying the responsible field.
* **Upstream Unavailability**: If an upstream comparator is unavailable (for example, due to `no_fit_rows` or `missing_training_classes`), the comparison cannot proceed. Upstream runners must inspect block status and `unavailable_reason` before scoring; when any required model is unavailable, the runner must preserve that reason and all usable forecasts while skipping only the three-way comparison.
* **Probability Invariants**: Probabilities must be native 3-tuples of finite non-negative numbers in $[0.0, 1.0]$ summing to $1.0$ within an absolute tolerance of $10^{-12}$. Booleans, non-finite values, and huge integers are rejected before numeric conversion.
* **Pure Standard-Library Boundary**: The scoring module operates strictly in-memory using Python's standard library. It does not import NumPy, SciPy, or scikit-learn, and performs zero filesystem or network operations.
* **Immutability**: All returned structures (`ComparisonMetrics`, `ModelMetrics`, `RowScore`, `ReliabilityBin`, `EvaluationOrigin`) are frozen dataclasses with immutable tuple fields.

#### Inspectable synthetic scorecard diagnostic

A passing test exercises the three-class toy oracle and prints a single line to standard output:

```
SYNTHETIC_SCORECARD {"fixture_kind": "synthetic_probability_vectors_not_fitted_models", ...}
```

The diagnostic exports a compact scored cohort and summary subset for inspectable verification, including origin dates, class support, and per-model summary metrics (mean Brier, mean log loss, log loss state, accuracy, tie count, zero count, confusion, and recall). Individual `row_scores` and `reliability_bins` are omitted from the diagnostic to preserve a compact single-line representation. All dates and probabilities are explicitly synthetic fixtures; they do not represent historical market data or trading model efficacy.

### Paired test-loss uncertainty (`uncertainty.py`)

The `research/prediction_eval/uncertainty.py` module implements paired stationary bootstrap statistical uncertainty estimation for paired TEST-only Brier-loss differences under candidate protocol `nivesh-paired-stationary-brier-v1`.

#### Statistical target and operating choices

* **Paired TEST-Only Evaluation**: Compares differences $d_i = L_i(\text{heuristic}) - L_i(\text{comparator})$ on the identical ordered test origin cohort. Negative difference favors the heuristic; positive difference favors the comparator. Evaluates exactly two sign-defined pairs: `heuristic_minus_frequency` and `heuristic_minus_logistic`.
* **Point Estimates**: Preserves exact test-cohort sample mean difference $\frac{1}{n} \sum_{i=1}^n d_i$ computed via `math.fsum` over the accepted scorer's raw per-origin Brier losses. Never subtracts rounded aggregate means. When intervals are unavailable, point estimates are preserved whenever the test cohort was scored.
* **Stationary Block Bootstrap (`paired_stationary_bootstrap`)**:
  * Resamples paired session indices with geometric block lengths via Politis & Romano (1994) stationary bootstrap on circularized index series.
  * Probability of continuing current block: $1 - \frac{1}{L}$. Probability of starting a new uniform origin: $\frac{1}{L}$.
  * Block lengths evaluated: $L \in (20, 40, 60)$ simultaneously and equally. $L=20$ is overlap-motivated, not a minimum realized block length or assertion of dependence range.
  * Replicates: $B = 10,000$ resamples per block length.
  * Seeds: Fixed local `random.Random(20261103 + L)` per length ($20261123$ for $L=20$, $20261143$ for $L=40$, $20261163$ for $L=60$).
  * Sample size floor: Requires $n \ge 10L$ for each block length ($n \ge 200$ for $L=20$, $n \ge 400$ for $L=40$, $n \ge 600$ for $L=60$).
* **Linear Integer Quantile Interpolation (`linear_integer40_v1`)**:
  * Computes nominal 95% bootstrap confidence intervals ($q_1 = 1/40 = 2.5\%$, $q_2 = 39/40 = 97.5\%$).
  * For $B=10000$, indices on sorted bootstrap means $x_{(0)} \le \dots \le x_{(9999)}$:
    * $j = \lfloor 9999 \cdot 1/40 \rfloor = 249$, rem $= 39$. Lower bound: $x_{(249)} + \frac{39}{40} (x_{(250)} - x_{(249)})$.
    * $j = \lfloor 9999 \cdot 39/40 \rfloor = 9749$, rem $= 1$. Upper bound: $x_{(9749)} + \frac{1}{40} (x_{(9750)} - x_{(9749)})$.
* **Strict Resource Ceiling**:
  * `MAX_RESAMPLE_POSITIONS = 30000000`. If required positions exceed this ceiling or config limit, execution raises `UncertaintyResourceError` immediately before any RNG draws.
* **Caller-Owned Identities**: `compute_uncertainty` requires the written input's `{raw_byte_count, sha256}` on the request and a caller-verified `runtime_identity`, for every state and before any RNG work. It never substitutes a zero hash or measures the runtime itself. `serialize_uncertainty_input` needs no identity, because the identity is the hash of those bytes.
* **Precedence Order for Availability**:
  1. `comparison_unavailable`: One or more models unavailable $\to$ status `unavailable`, reason `comparison_unavailable`, null point differences and intervals.
  2. `empty_cohort`: Zero test origins $\to$ status `unavailable`, reason `empty_cohort`, null point differences and intervals.
  3. `non_contiguous_test_cohort`: Intervening missing sessions or non-contiguous test cohort $\to$ status `unavailable`, reason `non_contiguous_test_cohort`, point differences preserved, intervals null.
  4. Per-length floor: $n < 10L \to$ status `unavailable`, reason `insufficient_nominal_blocks`, point differences preserved, intervals null.
  5. `available`: All requirements met $\to$ status `available`, point differences and 95% confidence intervals populated.
* **Truthful Scientific Assumptions & Caveats**:
  * Conditions on frozen fitted models and evaluation protocol; does not capture refitting uncertainty or live deployment drift.
  * Assumes approximate stationarity and weak serial dependence; synthetic evaluation cannot establish live market coverage guarantees.
  * All intervals are marginal views; no simultaneous familywise coverage guarantee is asserted.

### Replay wire serializer (`replay_export.py`)

`serialize_replay_input(series: FeatureSeries) -> bytes` is a pure in-memory standard-library serializer mapping an origin-time `FeatureSeries` into deterministic, BOM-free UTF-8 wire JSON bytes ending with exactly one LF, under the `nivesh-replay-input-v1` protocol consumed by the offline Node.js replay CLI (`replay.cjs`). It is the transport bridge from the Python feature calculation engine (`features.py`) to that CLI.

```python
from research.prediction_eval.inputs import align_pair, load_series
from research.prediction_eval.features import compute_nifty_features
from research.prediction_eval.replay_export import serialize_replay_input

nifty_series = load_series("nifty50_price_index", "data/nifty50.csv")
vix_series = load_series("india_vix", "data/india_vix.csv")
pair = align_pair(nifty_series, vix_series)
feature_series = compute_nifty_features(pair)

# Returns deterministic BOM-free UTF-8 JSON bytes ending with exactly one LF
wire_bytes = serialize_replay_input(feature_series)
```

* **Fixed Wire Parameters**: Schema version `nivesh-replay-input-v1`, feature protocol `nifty-close-features-v1`, series ID `^NSEI`, asset `^NSEI`, horizon `20D`, variant `frozen-current-core-market-data-only-v1`.
* **Exact Key Strictness**: Maps exactly the 13 root fields, 7 row fields, 7 payload fields, and 10 provenance fields. No outcome, event, label, or metric fields are accepted or serialized.
* **Row and Axis Preservation**: Every origin observation is preserved in supplied order with contiguous 0-based indices and strictly increasing Gregorian dates (years 0001..9999). Warmup origins ($i < 200$) and missing-VIX origins retain their original position, date, and Close price with `payload = null`.
* **Decimal Fidelity**: Origin and VIX Close values are serialized as plain fixed-point decimal strings preserving exact source scale without floating-point conversion, rounding, or normalization. Positive exponents are represented in equivalent plain notation without exponent characters.
* **Numeric Representation**: Predictor values retain their units and finite IEEE binary64 float values, including zeros, subnormals, and extreme finite floats. Integer predictor values convert only if exactly representable in binary64; inexact or out-of-range integers fail with `InputValidationError`.
* **Timestamps**: Acquisition timestamps are formatted preserving minute-resolution offsets; sub-minute offsets are rejected.
* **Calendar and Provenance Preservation**: Calendar mismatch discrepancy sets are verified against the axis. Provenance metadata (file paths, hashes, byte counts, record counts, date ranges, URLs, intervals, and acquisition datetimes) are preserved accurately without external file or network access.
* **Zero Side Effects**: Zero I/O, file reading, network access, or subprocess execution.

Its unit tests (`tests/test_replay_export.py`) cover:

* Exact wire schema mapping, constants, immutability, and byte-level repeatability.
* Empty axis handling and warmup/ready boundaries (199/200, missing-VIX 205, combined warmup+missing reasons).
* Decimal scale preservation and context-precision independence.
* Binary64 float preservation, boolean rejection, and integer conversion limits (inexact and out-of-range integers).
* Date boundaries (0001..9999), naive/aware and low-year acquisition timestamps, sub-minute offset rejection, rejection of inverted requested intervals and of inverted or count-inconsistent observed ranges, and Unicode provenance.
* Boundary error handling with explicit `InputValidationError` field context, including calendar mismatches, inconsistent readiness or reason order, and malformed `unready_reasons` containers.

The cross-language integration tests (`tests/test_replay_roundtrip.py`, [command](#python-to-node-roundtrip)) execute the actual offline Node.js replay CLI (`replay.cjs`) from Python via standard-library subprocess execution (`shell=False`, 60-second timeout). They validate the complete pipeline on a loader-backed synthetic 207-origin Nifty/VIX dataset with calendar gaps, nonflat price movement, and missing VIX observations; echoed predictor values must equal the typed values exactly as binary64 numbers. They also validate transport wiring parity against the sealed scenario-03 baseline oracle (`fixtures/forecast-baseline.json`), and retain sequence-numbered child process records and raw stream captures for all CLI executions.

### TypeScript replay core, compiler and offline CLI

An isolated CommonJS compilation pipeline and strict offline CLI interface provide retrospective directional forecast replay on `^NSEI` / `20D` without live network, browser, or server dependencies. Commands are under [Node replay compiler, CLI and suites](#node-replay-compiler-cli-and-suites).

1. **Pure Calculation Core (`src/engine/marketIntelligence/forecastCore.ts`)**:
   - `computeDirectionalForecastCore(features, horizon, events, plattParams)`: Pure synchronous mathematical calculation extracted mechanically from the browser adapter.
   - Accepts typed feature view (`ret_5d`, `rsi_14`, `macd_hist`, `vol_30d`, `rel_strength_20d`, `drawdown`, `market_regime`), `ForecastHorizon`, `EventObservation[]`, and optional Platt parameter tuple `[A, B]`.
   - Zero I/O, system clock, randomness, mutable module state, or network provider imports.
   - Preserves component rounding to 1 decimal place before weighting, probability calibration via Platt scaling, residual neutral probability computation, direction classification thresholds, and driver attribution strings.

2. **Unchanged Async Browser Adapter (`src/engine/marketIntelligence/forecastEngine.ts`)**:
   - Retains exact public signatures for `loadTrainedModels()` and `computeDirectionalForecast()`.
   - Preserves fetch order (models before history), provider/model caches, retry semantics, and latest-price-row selection.
   - Delegates pure calculation directly to `computeDirectionalForecastCore()`.

3. **Isolated CommonJS Compiler (`research/prediction_eval/compile_replay.cjs`)**:
   - Compiles TypeScript via `tsconfig.replay.json` using the local locked TypeScript compiler without polluting root ESM configuration.
   - Supports explicit `baseline` and `candidate` modes with dedicated isolated output roots (`build/prediction-eval/baseline` and `build/prediction-eval/candidate`).
   - Enforces pre/post input stability across sources, support, and compiler binaries. The candidate support set includes the root `tsconfig.json`, because `tsconfig.replay.json` inherits its options; changing it makes the candidate build stale. The baseline set is unchanged so the sealed baseline manifest stays valid.
   - Checks inputs before any mutation: in baseline mode the original source hashes, and in both modes the readability of every declared source, support and compiler file. A failed check leaves existing outputs, including a sealed baseline build, untouched.
   - Enforces comprehensive caller preflight before any mutation: verifies workspace confinement, validates ancestor chains and absent leaves across all owned emitted targets, and strictly rejects symbolic links (including dangling entries and symlink directories).
   - Recursively inspects existing output trees before deletion or compilation to refuse unknown files, unexpected directories, or non-regular entries.
   - Safely invalidates only the exact owned emitted files (`expectedEmittedFiles`, `package.json`, `build-manifest.json`) prior to compilation to guarantee fresh emission.
   - Validates that post-compilation output directories contain only expected regular, non-symlink fresh artifacts.
   - Emits a cryptographic `build-manifest.json` tracking exact source, support, toolchain (Node executable size/hash/version and TypeScript version), and emitted artifact identities.
   - Ordinary compilation writes only the owned outputs above. Compiler child capture is opt-in through `compile(mode, { childLogDir })`: the directory must not exist yet, must stay inside the workspace without linked ancestors, and must be disjoint from the build output. It is validated before any mutation. Records are created exclusively (never replacing an earlier file), and a capture failure fails the compile instead of being ignored.

4. **Strict Offline Replay CLI (`research/prediction_eval/replay.cjs`)**:
   - Command: `node research/prediction_eval/replay.cjs <input_file>`
   - Accepts exactly one input JSON document adhering to `nivesh-replay-input-v1`.
   - Validates fatal UTF-8 encoding (allowing a single leading BOM for parsing only while preserving request hash integrity; repeated BOMs are strictly rejected).
   - Strictly validates Gregorian dates (years 0001..9999), ordered provenance interval, valid ISO acquisition timestamps, contiguous indices, decimal syntax, and feature readiness.
   - Verifies `public/data/market_intelligence/models.json` hash and extracts `20D` Platt parameters `[1.42, 0.02]` via pure `validateModelsContent` seam.
   - Guards against nonfinite calculation results, including finite-input intermediate and output arithmetic overflows.
   - Validates candidate build manifest against runtime process identity before invoking compiled pure core.
   - Outputs single deterministic `nivesh-replay-output-v1` document to stdout, reporting errors cleanly to stderr with non-zero exit and empty stdout.

5. **Synthetic Verification & Supplemental Lifecycle Suite (`research/prediction_eval/tests/test_replay.cjs`)**:
   - Portable default test suite: runs exclusively against candidate build artifacts and committed test fixtures without requiring baseline build prerequisites or private records.
   - 17 isolated synthetic scenarios (`fixtures/replay-cases.json`) capturing full forecast outputs and ordered fetch traces against the untouched compiled baseline adapter (`fixtures/forecast-baseline.json`). The golden file and its recorded fingerprints are sealed historical provenance; the suite only reads them and contains no capture or regeneration path.
   - Deep equality parity tests between candidate core and baseline capture.
   - A replay CLI value oracle: a ready synthetic row carrying the frozen scenario-03 features must produce exactly the sealed scenario-03 golden forecast (20D, 20 sessions, empty events, trained Platt pair `[1.42, 0.02]`). This checks the CLI's payload, horizon and model wiring only; it does not validate Python-generated features or forecasting accuracy.
   - Independent Platt scaling boundary tests and component pre-weighting rounding tests.
   - Pure model validation seam tests calling actual production model validation.
   - Instrumented module import safety verifying absence of side-effect fs writes, process spawns, or network calls during import.
   - Finite-input arithmetic overflow rejection, repeated-BOM rejection, and discriminating compiler preflight safety tests (exercising redirected ancestors with missing leaves, dangling link entries, and unknown output state rejection before mutation).
   - Fresh per-invocation directory isolation for all symlink tests with fail-fast setup error handling (unexpected setup errors fail; unsupported OS capabilities explicitly skip via `t.skip` with OS error code) and explicit `[ASSERTION-EXECUTED]` audit markers emitted to stdout when link safety assertions run.
   - Compiler ordering and capture tests on injected fresh scratch outputs only: baseline mode must reject the changed adapter before touching a valid owned output layout or launching the compiler; reused, output-nested or link-redirected capture slots are refused before mutation; an injected capture write fault must fail the compile without producing a build manifest.
   - Prospective child process recording of raw stdout, stderr and typed JSON invocation records for adapter workers, lifecycle workers, CLI invocations and import safety workers. Each test process uses a fresh run directory under `build/prediction-eval/test-work/`; records are sequence-numbered and created exclusively, and a recording failure fails the test.
   - Candidate lifecycle verification running 9 isolated cases (`cache-success`, `model-http-retry`, `model-fetch-throw-retry`, `model-json-reject-retry`, `history-http-retry`, `history-fetch-throw-retry`, `history-json-reject-retry`, `empty-history-cached`, `unexpected-url`). The three model variants and the three history variants share one per-family oracle for fetch sequence, cache reuse, first-call failure outcome and second-call recovery. All adapter cases require zero unauthorized fetch attempts. `unexpected-url` is different: after the adapter calls, the worker itself deliberately fetches an unlisted URL to prove the test's mock-fetch guard rejects it (nonzero exit, specific diagnostic, empty stdout). It checks the harness guard, not adapter behavior.
   - Supplemental lifecycle controller (`--verify-lifecycle`) running differential comparisons between sealed baseline build and candidate build. Per-call differential verification compares error recovery (HTTP non-ok, fetch throw, JSON rejection), cache behavior and the mock-guard probe against the sealed baseline build. Portable candidate lifecycle tests run the same 9 cases without baseline prerequisites, using fixed expected outcomes instead of a differential comparison.

### Study runner and result contract (`study.py`, `study_results.py`)

`study.py` owns orchestration, admission inventory and the replay transport adapter; `study_results.py` owns result DTOs, strict summary serialization, completion manifest binding and UI presentation evaluation. Together they provide an offline, inspectable execution pipeline for multi-model prediction evaluation.

Under configuration `nivesh-study-config-v2` the runner accepts synthetic data only: `data_kind` other than `synthetic` is rejected before any input is read, and output is labeled as a synthetic fixture. Historical support uses the separate `nivesh-study-config-v3` mode described in [Historical evaluation support](#historical-evaluation-support).

#### Strict configuration, frozen admission and early planner check

* **Strict Configuration**: `load_study_configuration_file` keeps the exact original bytes and requires every field, with no default. It rejects unknown or duplicate keys, nonfinite numbers including overflowing reals such as `1e999`, booleans in integer fields, relative or PATH-resolved paths, and unsupported schema, protocol, status or date-selection values. `timeout_seconds` must be a positive integer of at most 60; larger values are rejected, not capped.
* **Bound Identities**: The configuration carries expected bytes and SHA-256 for the Nifty, VIX and calendar inputs, the frozen admission record, the Node and Python executables, `replay.cjs`, the candidate build manifest, the model and every required source module, plus `FileInputSpec` provenance, units, runtime version and scientific dependency versions. Public source holds no run-specific binding. `replay.cjs` resolves its model and build itself, so any other configured path for them is rejected rather than silently executing the canonical files.
* **Input-Only Inventory**: `compute_admission_inventory` computes warmup positions ($i < 200$) and missing exact-date India VIX observations across the mature master test span $[T, N-20)$ directly from aligned observations. It performs union counting without double-counting and generates a deterministic SHA-256 digest of the ordered gap positions under the policy `nonzero_gaps_lead_to_unavailable_intervals`. It does not invoke outcomes, feature predictors, comparators, replay, or scoring.
* **Acyclic Admission Order**: `prepare_input_admission` builds the synthetic record from admitted inputs only. Freeze that record first, then write the configuration that binds its bytes. The record binds input, calendar, cutoff and policy identities but never the configuration, so neither file hashes the other in a cycle. Historical records come only from `prepare_historical_admission`.
* **Verification Before Science**: A run verifies identities, then validates the complete supplied record with closed native types (`validate_admission_document`), then compares it with the loaded inputs, all before outcomes or features exist. Types come first because equality is by value: `true` would pass for `1` and `263.0` for `263`, and bound bytes prove identity, not type. Results can never re-admit a date or gap.
* **Immediate Verification**: The runner constructs the canonical reference `SplitPlan` and immediately checks that $[T, N-20) \setminus \text{test\_indices}$ matches the frozen ordered gap list, count and digest before calling frequency, logistic, or Node replay. Any discrepancy halts execution immediately without producing predictions, scores, or completion manifests.

#### Replay transport adapter and field-aware validation

* **Wire Serialization**: Serializes complete `FeatureSeries` with `replay_export.serialize_replay_input` (null payloads for unready origins; no outcomes or realized returns enter replay).
* **Untrusted Process Execution**: Invokes the pinned Node runtime with `replay.cjs` using `shell=False`, strict workspace working directory, and timeout $\le 60\text{s}$, enforced at the adapter as well as the configuration. The child receives an explicit environment, not the parent's: `SYSTEMROOT`, `TEMP` and `TMP` on Windows, or `TMPDIR` on POSIX, each only when present. Settings such as `NODE_OPTIONS` or `NODE_V8_COVERAGE` therefore never reach it, the receipt's `declared_environment` records exactly the supplied mapping, and the parent environment is left unchanged. On timeout or capture failure the started child is killed and waited on within a bound; incomplete capture is never parsed.
* **Exact Response Schema**: `validate_replay_response` requires exact root, provenance, row and forecast key sets for all origins before any target is selected. Row keys and counts are exact non-boolean integers. Echoed model and build identities are compared field by field with the trusted bytes. The child's own preflight is counterevidence, not a substitute for this check.
* **Recursive Field-Aware Echo Comparison**: Compares returned `declared_input` against parsed request bytes:
  * Exact dictionary keys, sequence lengths, and array ordering.
  * Decimal Close strings compared as plain fixed-point text.
  * Strict distinction between booleans and integer counts (rejecting `bool` in integer fields).
  * Safe integer bounds ($0 \le x \le 2^{53}-1$) on origin indices, `raw_byte_count`, and `record_count`.
  * Numeric payload fields (`ret_5d`, `rsi_14`, `macd_hist`, `vol_30d`, `rel_strength_20d`, `drawdown`) compared by finite binary64 represented value, allowing JSON `0` versus `0.0` and signed zero equivalence (`+0.0 == -0.0`), while strictly excluding booleans.
  * Case-insensitive validation of 64-character hexadecimal SHA-256 strings.
* **Forecast Mapping**: Maps `probability_bearish`, `probability_neutral`, and `probability_bullish` to `(BEAR, NEUTRAL, BULL)` tuples, validated for every ready origin by the scorer's own full-precision validator ($| \sum p - 1.0 | \le 10^{-12}$). Preserves verbal `expected_direction` separately from the first-max scoring class.

#### Serial fit warning and threadpool ownership

* **Restored Threadpool Limits**: Restricts execution to single-threaded numerical computation with `threadpoolctl.threadpool_limits(limits=1)` around serial comparator fits.
* **Warning Filter Composition**: Sets `warnings.simplefilter("always")` first, followed by `warnings.filterwarnings("error", category=FutureWarning)` second (with normal prepend semantics). A raised `FutureWarning` immediately aborts the run without producing a completed manifest.
* **Warning Retention and Convergence Ownership**: Ordinary warnings (including repeated same-location warnings) are recorded. Handled inner `ConvergenceWarning => not_converged` exceptions in `logistic.py` remain owned by that module and are not re-emitted as uncaught warnings. Thread limits and warning filters are restored on success and exception. Even if an exception or `FutureWarning` aborts a later comparator, ordinary warnings emitted earlier remain retained and inspectable on the exception (`exc.captured_warnings`) and failure diagnostics without masking the failure.

#### Coverage counts and partial availability

* **Count Definitions**: All counts derive from canonical `SplitPlan.decisions`; there is no second eligibility rule. `raw_partition_count` is the decisions assigned to the partition, `eligible_count` the retained targets, `excluded_count` their difference, and `requested_count` the comparator targets (normally `eligible_count`). `exclusion_reason_counts` can overlap on one origin, so their sum may exceed the unique excluded count. The test unknown tail counts in raw coverage, not as a gap in the mature interval $[T, N-20)$.
* **Preserved Forecasts**: Per-origin records are built for every target independently of three-way scoring. An unavailable method has an explicit state and null probabilities; unscored rows keep null losses rather than invented values. Block pools, cutoffs, class and regime counts, reasons and failure stages survive even when `fit` is `None`.
* **Comparison States**: An unavailable fit gives `comparison_unavailable` and wins before the empty state. Only when all fits are available does an empty target follow the accepted empty scoring. No dummy method, single-model score or common-subset comparison exists.
* **Reconciliation**: Each comparator's returned plan, decisions, dates, fitting pools, cutoffs and requested keys are compared with the reference plan, including on unavailable blocks. Comparators keep their own single planner delegation.

#### Artifact hierarchy, completion manifest, and UI seam

* **Exclusive Run Roots**: Every study execution writes exclusively to a newly created run directory. `allowed_output_parent` is a required configuration field passed through `main`; `run_study` has no default for it. `run_study` first requires the configured `workspace_root` to be this package's actual root (failing on field `workspace_root`), because the protected roots come from it; a wrong root therefore creates no directory and no failure record. The run root must be a direct child of that parent, written without any `..` component (so `allowed/../allowed/run` is refused before normalization could make it look like a direct child), reached without a reparse point at any existing lexical component of either path (a regular parent below a linked ancestor is rejected), and not an alias of a bound input or inside source, served-asset (`public`, `dist`), model or build roots. Checks finish before the first write. They are static checks, not a race-free or deployment guarantee.
* **Written Artifacts**:
  1. `config.json`: exact original configuration bytes (`nivesh-study-config-v2`).
  2. `admission.json`: exact frozen admission record bytes (`nivesh-study-admission-v1`).
  3. `replay-request.json`: exact saved request wire bytes.
  4. `replay-response.json`, `replay-stderr.log`, `replay-invocation.json`: raw child streams and the typed native receipt.
  5. `uncertainty-input.json`: exact caller projection of TEST-only scores, axis alignment and admission gaps (`nivesh-uncertainty-input-v1`).
  6. `uncertainty-diagnostics.json`: exact diagnostics recording random stream fingerprints, direct call counts, and resource usage (`nivesh-uncertainty-diagnostics-v1`).
  7. `result.json`: private complete result (`nivesh-study-result-v2`): identities, per-origin forecasts, outcomes and loss states, returned fit and block state, comparator warnings, returned loader `input_warnings`, metrics, uncertainty block, and private paths.
  8. `predictions.json`: the same origin-level rows for both partitions.
  9. `panel-summary.json`: candidate aggregate summary adhering to `nivesh-evaluation-summary-v2`. An explicit whitelist with run, replay, provenance identity, and closed uncertainty summary; no rows, coefficients, paths or tracebacks.
  10. `report.md`: beginner-readable Markdown report rendered from the same result object, including statistical uncertainty intervals and caveats.
  11. `run-manifest.json`: written **LAST** after all required artifacts are validated, semantically checked, and hashed (`nivesh-study-run-manifest-v2`). Binds relative paths, byte counts, and SHA-256 hashes of the twelve artifact files above plus path-free config, admission, input, source, runtime, model and build identities, excluding its own hash. (A historical `nivesh-study-run-manifest-v3` also carries each original file's private path, URL and source-use note, so it stays private; see [Historical evaluation support](#historical-evaluation-support).)
  * *Per-Attempt Replay Evidence and Failure Diagnostics*: Each replay attempt claims its evidence by exclusive file creation inside the owned run root, so a prior or partial attempt is never overwritten. A later attempt in the same root uses ordinal names such as `replay-request-002.json` and `replay-invocation-002.json`. `NIVESH_EVAL_CHILD_LOG_DIR` grants this adapter no write authority: the value is neither passed to the child nor recorded in its receipt, and the roundtrip test's own child records are separate. Once the run root is owned, any failure writes one `failure-diagnostics.json` with the stage, primary error, retained warnings, returned loader warnings and partial artifact hashes, and leaves no `run-manifest.json` of its own: `run-manifest.json` is created exclusively, a caught write or close failure removes the partial file that call created and keeps the primary error (a failed removal is disclosed on that error), and a file that already existed is never overwritten or removed. A crash or a concurrent writer is outside this guarantee. Before the root is owned, failures reach only the caller. If the record itself cannot be written, the primary error survives and the write failure is disclosed to the caller.
  * *Loader Warnings*: Advisory `InputWarning` records are retained as each loader returns, in order and with repeats: `file_path`, `line`, `field`, `message` and `raw_value`. An earlier series keeps its warnings if a later loader or any downstream stage fails, and a loader that raised contributes none. They can hold raw file text and paths, so they stay in `result.json` and `failure-diagnostics.json`, never in the summary, report or UI data. The foundation's advisory policy is unchanged.
* **Closed Schemas**: `validate_summary_document`, `validate_result_document`, `validate_run_manifest_document`, `validate_uncertainty_input_document`, and `validate_uncertainty_diagnostics_document` reject unknown or missing fields, wrong types, nonfinite numbers and contradictory state/value combinations at every level. The DTOs apply the same rules at construction. Supported schema and protocol sets are constants in `study_results.py` and `uncertainty.py`.
* **Portable Summary Relations**: `validate_summary_document` and the TypeScript `validateSummaryDocument` also relate the summary's own blocks, using only facts it carries. Each partition `cutoff_date` must equal its `chronological_cutoffs` entry, and the TEST `cutoff_index` must equal `admission_summary.mature_test_start_index`. Uncertainty `n` must equal the TEST `requested_count` and `mature_span_count` the admitted span. The reason, per-length states and point nullability must follow from the TEST comparison status, that count and the admitted `union_gap_count`, through `common_unavailable_reason` (mirrored in `commonUnavailableReason`). A v3 summary must keep 800 mature slots, a TEST index of at least 1400 (T at N=2220) and a DEV index of TEST minus 400. The scored count is not inferred from the 800 slots. A v2 summary keeps the synthetic policy. Axis dates, rows and resampling stay private to the archive relations.
* **Metric Ranges and Row Coherence**: Recall, accuracy and reliability means and frequencies must lie in $[0, 1]$, mean and row Brier in $[0, 2]$, and log losses must be nonnegative with no ceiling. Recall and accuracy must agree with the confusion counts beside them, and model-available counts with each method's state. Private rows must conserve probability (`math.fsum` within $10^{-12}$), name the first maximum as the predicted class, and hold infinite log loss exactly when the actual class has zero probability. These are direct range and field relations: no loss is recomputed, the scorer stays the only metric owner, and bin means are not checked against bin edges. Signed zero, null, empty, infinite and tiny-positive states stay valid.
* **Checked Binding & Semantic Cross-Verification**: `verify_completion_binding` requires strict JSON, a valid summary, a complete manifest with unique typed entries, agreeing summary/manifest identities and the exact summary bytes and hash. `verify_promotion_binding` additionally requires a descriptor agreeing on run, study, protocol, supported schema, coverage and both byte counts and hashes. `verify_study_artifacts_semantic_relations` runs on the written files before the manifest exists and again in `verify_completed_run`. It requires canonical `uncertainty-input.json` bytes (sorted compact ASCII, one final LF), then relates the input axis, keys, availability, losses and gaps to `result.json` and `admission.json`, derives the uncertainty counts, states and full-cohort points from the saved cohort, and ties `uncertainty-diagnostics.json` counters, runtime and input identity, and `config.json` cap, runtime and expected sources, to the same run. It also relates the saved tool byte counts and hashes, the fixed model pin (compared case-insensitively, as the loader accepts it) and the closed required dependency versions to the result's runtime, model, build, replay and logistic metadata, without importing or querying any archived runtime. The build must be the candidate build, the two measured identities of `replay.cjs` (source module and replay script) must agree, and the logistic metadata must name exactly `numpy`, `scikit-learn` and `scipy`. Both partition cutoff dates must be the admitted axis dates at their indices. Each method block must keep its partition cutoff and list only fitting rows past the warmup whose labels mature strictly before it, with the development pool and every recorded development target inside the refit pool and one pool across methods; the archive cannot show a listed pool is complete. The replay streams are inventoried before this check: the saved request and response must match the result's captured identities, and request, stdout and stderr must match a typed receipt of one started, completely captured, untimed first attempt with exit 0. Its argv must be the recorded executable, the configured `replay.cjs` label and the recorded request; its executable, working directory and timeout must be the saved configuration's, and the timeout at most 60 seconds. Receipt paths are saved labels compared with other saved labels, not proof of content, so a moved archive still verifies. `predictions.json` must be the canonical bytes of the per-origin rows of `result.json`. It never reruns the bootstrap or rescoring, so index fingerprints stay opaque and `randrange_calls` gets bounds only, not exact restart authentication. Admission keeps the axis count and end dates, and persisted rows add the dates they name; other interior axis dates are bound by hash alone. `verify_completed_run` also checks every required file on disk and compares manifest provenance with `result.json`. Result and manifest source identities must be exactly the required module set. A run failure after summary write leaves no valid completion manifest and blocks promotion. A candidate descriptor stays private: matching hashes are consistency evidence, not publisher authentication, and nothing here approves a release.
* **UI Display State Precedence**: The later UI evaluates display state in strict precedence (`evaluate_ui_display_state`; a descriptor that fails `parse_release_descriptor` is `error`):
  1. Missing descriptor or summary artifact $\to$ `unavailable` (no metrics).
  2. Unparseable bytes $\to$ `error` (no metrics).
  3. Schema or protocol outside the supported constants $\to$ `unsupported_version` (no metrics). A matching unsupported summary and descriptor stay unsupported.
  4. Closed schema violation, including an impossible finite metric whose bytes are correctly bound $\to$ `error` (no metrics).
  5. Mismatched `run_id`, `study_id`, summary schema version or `coverage_end_date` $\to$ `stale` (no metrics). Two supported but different schemas (a v2 summary under a v3 descriptor, or the reverse) are a stale selection, as `verify_promotion_binding` already requires.
  6. Raw-byte count or SHA-256 digest mismatch, or digest failure $\to$ `error` (no metrics).
  7. Exact supported identity and cryptographic binding $\to$ `displayable`.
  The UI contract requires hashing raw fetched response bytes (never reserialized JSON). Inability to compute or compare digests fails closed with `error` and suppresses all numeric metrics.

### Historical evaluation support

The package supports retrospective historical evaluation under candidate configuration schema `nivesh-study-config-v3` and the same study protocol `nivesh-offline-study-v1` (`STUDY_PROTOCOL_ID`) as synthetic runs. Code support supplies no data, calendar evidence or human approval. The actual inputs, calendar, admission and authority for a real study must be established separately.

#### Closed compatibility dispatch

Configuration modes are strictly closed and enforced before any input file path access:

| Property | Synthetic V2 (`nivesh-study-config-v2`) | Historical V3 (`nivesh-study-config-v3`) |
| :--- | :--- | :--- |
| **`data_kind`** | `synthetic` | `historical` |
| **`development_status`** | `synthetic_development` | `retrospective_historical_evaluation` |
| **`date_selection_rule`** | `calendar_only_fixed_before_outcomes` | `calendar_tail800_dev400_min2220_v1` |
| **`source_kind`** | `synthetic_fixture` | `admitted_historical_market_data` |
| **Artifact Count** | 12 artifacts | 13 artifacts (includes `historical-admission.json`) |
| **Admission Schema** | `nivesh-study-admission-v1` | `nivesh-study-admission-v2` |
| **Admission Producer** | `prepare_input_admission` | `prepare_historical_admission` |
| **Approval Credential** | Strictly forbidden | Required external `BoundFile` (`nivesh-historical-admission-v1`) |
| **Summary Schema** | `nivesh-evaluation-summary-v2` | `nivesh-evaluation-summary-v3` (raw hashes withheld) |
| **Manifest Schema** | `nivesh-study-run-manifest-v2` | `nivesh-study-run-manifest-v3` |

Incompatible or mixed combinations (such as V2 with historical data, or V3 with synthetic data) fail closed on `data_kind` or `schema_version` before any input access.

#### Machine split rule (`calendar_tail800_dev400_min2220_v1`)

The historical split rule is derived strictly from the admitted Nifty 50 chronological trading session axis length $N$:
* $E = N - 20$ (Evaluation end origin)
* $T = N - 820$ (Test partition start origin)
* $D = N - 1220$ (Development partition start origin)
* **Constraints**: Requires $N \ge 2220$ and $D \ge 1000$. The mature test span $E - T$ is strictly 800 sessions.
* **Caller Date Verification**: If caller supplies `development_start` or `test_start`, exact match against derived dates is enforced; caller drift is rejected.
* **Single Rule Owner**: `study_results.historical_split_indices` is the only definition of this arithmetic. The runner (before outcomes, at stage `load_inputs`), the admission validator and the completed-run checker each still check it against their own actual axis or persisted values.
* **Resampling Cap**: A historical configuration must set `uncertainty.max_resample_positions` to exactly 24000000 ($B=10000 \times n=800 \times 3$ views). The engine hard ceiling stays 30000000 and the synthetic-v2 range is unchanged.

#### Multi-file ordered inputs

Historical market series are supplied as ordered file sequences:
* Files are parsed and validated via standard `load_series` preserving per-file provenance, record counts, and SHA-256 hashes.
* No dataset canonicalization or `provenance[0]` shortcuts. Duplicate file paths within or across series are strictly rejected.

#### Machine admission and human approval lifecycle ($A \to C \to H \to \text{Run}$)

1. **Machine Admission ($A$)**: `prepare_historical_admission` inspects input files, aligns against the master calendar, derives split cutoffs, records the mature test span of 800 sessions, and inventories gaps. It returns the `nivesh-study-admission-v2` record; the operator saves its exact bytes at a chosen private path, and a run copies them as `admission.json`.
2. **Configuration ($C$)**: the configuration file (`nivesh-study-config-v3`) binds those exact admission bytes and SHA-256. A run executes only the fields its own original bytes parse to: a direct-API configuration paired with other raw bytes is refused before a run root exists.
3. **Human Approval ($H$)**: External approval document (`nivesh-historical-admission-v1`) binds the raw configuration and admission bytes and hashes, and references every configured original file exactly once with its evidence. The direct API takes `approval=BoundFile(...)`. The CLI takes `--approval`, `--approval-bytes` and `--approval-sha256` together; the expected identity is never read from the approval file itself, a partial or malformed triple is refused before any run, and a synthetic configuration refuses any approval. Never stored as a configuration field. Hash and schema consistency do not authenticate the approver, consent or provider rights.
4. **Execution & Artifacts**: The pre-science stage `verify_human_approval` (after `verify_prerequisites`, before `load_inputs`) validates H and its C/A identities, evidence files and input references, then copies H. A run produces 13 verified artifacts: the 12 standard evaluation artifacts plus `historical-admission.json` (exact preserved approval document bytes).
5. **Completed-Run Verification**: `verify_study_artifacts_semantic_relations` (before the manifest and again in `verify_completed_run`) requires one closed mode across result, summary and admission, binds the saved historical configuration's mode, cutoffs, admission identity, calendar and every ordered original file to `result.json` and `admission.json`, repeats H's C/A identities and exact input-reference coverage, and requires `panel-summary.json` to equal its deterministic projection of `result.json`. It does not reread external evidence files. `verify_promotion_binding` remains a summary/manifest/descriptor hash-consistency check.

Historical privacy, withheld hashes and caveats are listed under [Limitations, privacy and claims](#limitations-privacy-and-claims).

---

## Limitations, privacy and claims

### Scope boundaries

1. **Predictive Modeling and Scoring Boundaries**: The foundation modules (`inputs.py`, `features.py`, `outcomes.py`, `splits.py`, `frequency.py`) load inputs, validate chronology, compute realized future outcome labels, compute causal point-in-time features, plan chronological evaluation partitions, and evaluate a fixed Laplace-smoothed empirical class frequency baseline. The optional logistic comparator (`logistic.py`) fits a fixed, non-tuned L2 logistic regression model against planned partitions. The metrics module (`metrics.py`) evaluates supplied predictions against realized outcomes across shared origin cohorts. Neither pipeline optimizes hyperparameters, repairs probability calibrations, or generates trading signals. Retrospective offline replay of the current production heuristic on historical market data is provided separately via the [TypeScript CLI](#typescript-replay-core-compiler-and-offline-cli).
2. **Future Data Boundary**: Outcomes represent realized future labels that cannot be accessed at origin time. Features represent historical inputs available at origin time. The two pipelines remain strictly isolated.
3. **No Data Acquisition**: Network calls, web scraping, and live market connections are outside the scope of this package.
4. **Calendar Verification Scope**: A `matches_supplied_sessions` status confirms only that observed dates match the caller-provided calendar list; it does not authenticate real-world exchange schedule completeness.
5. **Heuristic Regime Labels**: Market regime classifications are heuristic categories derived from trailing indicator rules; they are not financial advice or guarantees of market direction.
6. **Baseline Comparator Only**: The fixed Laplace frequency comparator provides an empirical historical benchmark prior against which prospective forecasting models are compared. It does not learn weights, optimize hyperparameters, consume numeric feature values, produce trading recommendations, or establish financial accuracy.
7. **Evaluation Architecture Only**: The split planner produces immutable index partitions and origin-retained decisions. Formal real-data admission, calendar authorization, model fitting, and prediction scoring are outside that module.

### Replay claims

* **Retrospective Heuristic Replay**: Offline replay evaluates the frozen current heuristic against historical market observations. It does not constitute historically issued forecasts or financial advice.
* **Retrospective Claim Label**: Replay CLI output explicitly carries the claim label: *"Retrospective replay of the frozen current heuristic; market data only; not historically issued forecasts"*.
* **Retrospective Golden Capture Qualification**: The 17 synthetic scenarios in `forecast-baseline.json` record the final forecast output and combined HTTP fetch traces of the compiled baseline adapter under synthetic conditions; they are not live market predictions.

### Synthetic verification scope

* **Transport Bridge Qualification**: Synthetic pass results establish tested serialization and subprocess execution integration between Python and Node.js. They do not constitute authentic market data, model training, financial accuracy, or live forecasting efficacy.
* **No Accuracy or Authenticity Claims**: Tested synthetic split results verify partition logic and strict-before purge arithmetic. They do not certify prediction accuracy, empirical leakage freedom on an unauthenticated dataset, financial or regulatory compliance, or complete experiment delivery.
* **No Publication or Financial Advice Clearance**: Frequency output probabilities represent smoothed historical class proportions under synthetic evaluation protocols. They do not constitute investment advice, trading signals, or audited market disclosures.
* **Logistic Synthetic Verification Only**: All logistic tests and examples use synthetic placeholder dates (e.g. `2021-01-04`) and synthetic price records. Passing tests show that the stated contracts and oracle bounds hold on these bounded synthetic fixtures in the admitted environment. They do not prove general numerical correctness, and they make no claim of market forecasting efficacy, calibration or financial accuracy.

### Historical privacy and withheld hashes

* `panel-summary.json` (`nivesh-evaluation-summary-v3`) withholds individual raw market CSV file hashes and calendar hashes; their release status is WITHHELD unless a later owner decision says otherwise.
* `provenance_identity` contains strictly 3 keys: `config_sha256`, `admission_sha256`, and `approval_sha256`. These, together with `replay_identity.request.sha256` and `replay_identity.response.sha256`, are data-derived digests that REQUIRE OWNER REVIEW and are NOT CLEARED FOR PUBLICATION; a summary candidate is not a public asset.
* `result.json`, `run-manifest.json`, configuration, admission, H, private human evidence, provider URLs, source-use notes, internal paths and replay payloads stay private.

### Historical caveats

Historical summaries carry the retrospective, end-of-day, returns/stationarity and interval caveats plus two more: there is no forecast accuracy guarantee, and the test window is not an untouched holdout, since the frozen heuristic, features and protocol were designed with access to historical market behavior.

## Historical evaluation UI integration, synthetic fixtures & test harness

### User Interface Architecture & Disclosure Boundary

* **Bounded Diagnostic Mount**: In `src/components/marketIntelligence/AssetDiagnosticView.tsx`, an inline historical evaluation disclosure is mounted strictly for `asset.symbol === '^NSEI'` immediately following the directional probability forecast hero in the left column.
* **Independent Fixed Protocol**: Historical evaluation represents an offline retrospective study on Nifty 50 over a fixed 20 trading sessions horizon (`close-return-20-session-half-percent-neutral-inclusive-v1`). Its content is strictly independent of live 1D/5D/20D/60D horizon selection and does not certify or alter live forecasts.
* **Separation of Presentation and Data Owner**: `HistoricalEvaluationPanel.tsx` owns the accessible disclosure interaction, loading lifecycle, and tabular presentation. Pure schema validation, cryptographic identity checks, and display state evaluation are owned by `src/engine/marketIntelligence/historicalEvaluation.ts`.
* **Honest Counts and Partition States**: Each partition header labels `requested_count` as requested origins. A scored session count appears only when that partition's comparison is scored, and it comes from the scored metrics' `sample_count`. Comparison-unavailable and empty cohorts read "Not scored" and show their own message and supplied reasons, for TEST and for the development reference prior, which is never pooled with TEST.
* **Reading Paired Differences**: The uncertainty section states that each value is the TEST mean Brier score difference, heuristic minus the named comparator, paired over the same scored sessions, and that negative values favour the heuristic. A scored TEST shows its full-cohort points with sign and four decimals whether or not any interval is available, so a below-floor or gapped cohort shows its points with the unavailable reason. Brackets are 95% percentile intervals from the declared paired stationary bootstrap, and 10,000 is the nominal replicate count for each eligible block length. With no eligible length the panel says no interval was resampled. The 20, 40 and 60 session block lengths are shown together with their own state. Empty and comparison-unavailable partitions show no point estimate. The summary validators require the requested TEST count to equal the mature TEST span minus admitted union gaps. For scored comparisons, they check each supplied paired Brier difference against the heuristic TEST mean minus the comparator TEST mean, within an absolute tolerance of `1e-9`. The study computes the scores and intervals offline.
* **JSON Artifact Requests**: The descriptor and summary requests both send `Accept: application/json` on the loader-owned abort signal. A 404 stays `unavailable`. A successful response that is not the expected JSON, such as an HTML page, stays a verification `error`. How a deployment host answers a missing file is a separate qualification.

### Strict Artifact Validation & State Precedence

* **Supported Schemas**: Declared in code: summary schemas `nivesh-evaluation-summary-v2` (synthetic) and `nivesh-evaluation-summary-v3` (historical), release descriptor schema `nivesh-study-release-descriptor-v1`, study protocol `nivesh-offline-study-v1`, and uncertainty protocol `nivesh-paired-stationary-brier-v1`.
* **Strict JSON Own Keys**: The strict parser defines every JSON member as an own property, so a member spelled `__proto__` (literally or through `\u` escapes) is seen and rejected by the closed-key checks instead of silently changing an object prototype. Duplicate keys remain errors.
* **State Precedence**:
  1. unavailable: missing release descriptor or summary artifact (e.g. 404).
  2. error: unparseable bytes, non-object root, or strict UTF-8/BOM/duplicate key violation.
  3. unsupported_version: independently undeclared summary or descriptor schema/protocol version.
  4. error: closed schema violation across root, attribution, replay identity, provenance, partitions, counts, metrics, or uncertainty blocks, including a broken portable relation between them.
  5. stale: mismatch between summary and descriptor on `run_id`, `study_id`, `summary_schema_version`, or `coverage_end_date`.
  6. error: byte count mismatch, crypto digest failure, or SHA-256 hash mismatch.
  7. displayable: exact cryptographic and structural verification established; only this state exposes summary metrics.
* **No False Substitution**: Empty cohorts, infinite log-loss states, and unavailable comparator intervals are displayed faithfully without zero substitution.
* **Byte Consistency Only**: Matching byte counts and SHA-256 digests show byte consistency with the selected descriptor. They are not publisher authentication or legal/source-use clearance.

### Synthetic Fixtures & Isolated Test Harness

* **Synthetic Fixtures**: Both fixtures are visibly labeled SYNTHETIC TEST FIXTURE / NOT MARKET RESULTS. Their aggregates are hand-authored schematic values, not outputs of the study pipeline.
  - `historical-evaluation.synthetic-v2.json` (`nivesh-evaluation-summary-v2`): three synthetic sessions per partition with fixed illustrative probability patterns, so its metrics and reliability bins agree with each other. Its scored, contiguous TEST cohort of 3 sessions is below every nominal-block floor (10 x block length), so every interval is `insufficient_nominal_blocks` while the point differences are kept.
  - `historical-evaluation.synthetic-v3.json` (`nivesh-evaluation-summary-v3`): fabricated contract test fixture with historical-looking schema tags and dates. Its metric values, confusion counts and reliability bins are illustrative placeholders that are not mutually derivable from per-session predictions, and its session counts are not calendar-realistic. Its development reference values differ from its TEST values so tests can tell the partitions apart. Its indices and counts keep the portable relations at the rule minimum (D=1000, T=1400, 800 gap-free mature slots, 800 scored TEST origins, DEV raw count T-D=400), so its available intervals belong to a contiguous cohort.
* **Isolated Browser Preview**: `historical-evaluation.preview.html` is a standalone Vite-served synthetic harness that drives the production panel and loader across 15 scenarios. They include the scored below-floor v2 case, a scored v2 case with one admitted gap (points without intervals), the available v3 positive, coherent `empty_cohort` and `comparison_unavailable` (800 requested, no points) states and the two development-partition states. It is not part of the application routes.
* **Targeted Test Suite**: `test_historical_evaluation.cjs` (native `node:test`) transpiles the two production modules into `NIVESH_UI_TEST_ROOT` when it is set, otherwise into the ignored repository cache `node_modules/.cache/nivesh-historical-evaluation-ui`. It checks strict JSON parsing (including raw `__proto__` members), schema rules, state precedence, byte and digest binding, loader errors, and partition-scoped SSR markup. SSR markup checks do not prove browser layout or overflow.