/**
 * Historical Evaluation Data and State Management Owner.
 *
 * Implements strict, closed frontend validation and display state evaluation
 * for Nifty 50 historical evaluation artifacts.
 *
 * Supported schemas:
 *   - nivesh-evaluation-summary-v2 (synthetic development)
 *   - nivesh-evaluation-summary-v3 (retrospective historical evaluation)
 *   - nivesh-study-release-descriptor-v1
 *   - nivesh-offline-study-v1
 *   - nivesh-paired-stationary-brier-v1
 */

// --- Constants ---

export const SCHEMA_VERSION_SUMMARY_V2 = 'nivesh-evaluation-summary-v2'
export const SCHEMA_VERSION_SUMMARY_V3 = 'nivesh-evaluation-summary-v3'
export const SCHEMA_VERSION_RELEASE_DESCRIPTOR = 'nivesh-study-release-descriptor-v1'
export const STUDY_PROTOCOL_ID = 'nivesh-offline-study-v1'
export const UNCERTAINTY_PROTOCOL_ID = 'nivesh-paired-stationary-brier-v1'

export const SUPPORTED_SUMMARY_SCHEMA_VERSIONS = new Set<string>([
  SCHEMA_VERSION_SUMMARY_V2,
  SCHEMA_VERSION_SUMMARY_V3
])
export const SUPPORTED_PROTOCOL_IDS = new Set<string>([STUDY_PROTOCOL_ID])

export const DATA_KIND_SYNTHETIC = 'synthetic'
export const DATA_KIND_HISTORICAL = 'historical'
export const SUPPORTED_DATA_KINDS = new Set<string>([DATA_KIND_SYNTHETIC, DATA_KIND_HISTORICAL])

export const DEVELOPMENT_STATUS_SYNTHETIC = 'synthetic_development'
export const DEVELOPMENT_STATUS_HISTORICAL = 'retrospective_historical_evaluation'
export const SUPPORTED_DEVELOPMENT_STATUSES = new Set<string>([
  DEVELOPMENT_STATUS_SYNTHETIC,
  DEVELOPMENT_STATUS_HISTORICAL
])

export const SOURCE_KIND_SYNTHETIC = 'synthetic_fixture'
export const SOURCE_KIND_HISTORICAL = 'admitted_historical_market_data'
export const SUPPORTED_SOURCE_KINDS = new Set<string>([SOURCE_KIND_SYNTHETIC, SOURCE_KIND_HISTORICAL])

export const STATUS_SCORED = 'scored'
export const STATUS_EMPTY = 'empty'
export const STATUS_COMPARISON_UNAVAILABLE = 'comparison_unavailable'

export const UI_STATE_UNAVAILABLE = 'unavailable'
export const UI_STATE_ERROR = 'error'
export const UI_STATE_UNSUPPORTED_VERSION = 'unsupported_version'
export const UI_STATE_STALE = 'stale'
export const UI_STATE_DISPLAYABLE = 'displayable'

export const ORDERED_CLASSES = ['BEAR', 'NEUTRAL', 'BULL'] as const
export const MODEL_NAMES = ['heuristic', 'frequency', 'logistic'] as const
export const EXCLUSION_REASONS = [
  'warmup',
  'missing_vix',
  'unknown_outcome',
  'label_crosses_development_boundary',
  'label_crosses_test_boundary'
] as const

export const FREQUENCY_UNAVAILABLE_REASONS = ['no_fit_rows'] as const
export const LOGISTIC_UNAVAILABLE_REASONS = [
  'no_fit_rows',
  'missing_training_classes',
  'not_converged',
  'nonfinite_model_state'
] as const
export const LOGISTIC_FAILURE_STAGES = ['scaler', 'fit', 'prediction'] as const

export const UNCERTAINTY_METHOD = 'paired_stationary_bootstrap'
export const BOOTSTRAP_REPLICATES = 10000
export const NOMINAL_COVERAGE = 0.95
export const QUANTILE_RULE = 'linear_integer40_v1'
export const BLOCK_FLOOR_FACTOR = 10
export const BLOCK_LENGTHS = [20, 40, 60] as const
export const BLOCK_LENGTH_SEEDS: Record<number, number> = {
  20: 20261123,
  40: 20261143,
  60: 20261163
}
export const BLOCK_LENGTH_LABELS: Record<number, string> = {
  20: 'minimum, overlap-motivated setting; not a minimum realized block length',
  40: 'intermediate block length',
  60: 'long block length'
}

export const PAIR_HEURISTIC_MINUS_FREQUENCY = 'heuristic_minus_frequency'
export const PAIR_HEURISTIC_MINUS_LOGISTIC = 'heuristic_minus_logistic'
export const ORDERED_PAIR_IDS = [
  PAIR_HEURISTIC_MINUS_FREQUENCY,
  PAIR_HEURISTIC_MINUS_LOGISTIC
] as const

export const UNCERTAINTY_STATUS_AVAILABLE = 'available'
export const UNCERTAINTY_STATUS_PARTIALLY_AVAILABLE = 'partially_available'
export const UNCERTAINTY_STATUS_UNAVAILABLE = 'unavailable'
export const SUPPORTED_UNCERTAINTY_STATUSES = new Set<string>([
  UNCERTAINTY_STATUS_AVAILABLE,
  UNCERTAINTY_STATUS_PARTIALLY_AVAILABLE,
  UNCERTAINTY_STATUS_UNAVAILABLE
])

export const REASON_COMPARISON_UNAVAILABLE = 'comparison_unavailable'
export const REASON_EMPTY_COHORT = 'empty_cohort'
export const REASON_NON_CONTIGUOUS = 'non_contiguous_test_cohort'
export const REASON_INSUFFICIENT_BLOCKS = 'insufficient_nominal_blocks'
export const COMMON_UNAVAILABLE_REASONS = [
  REASON_COMPARISON_UNAVAILABLE,
  REASON_EMPTY_COHORT,
  REASON_NON_CONTIGUOUS
] as const
export const NO_POINT_REASONS = [REASON_COMPARISON_UNAVAILABLE, REASON_EMPTY_COHORT] as const
export const SUPPORTED_UNAVAILABLE_REASONS = new Set<string>([
  REASON_COMPARISON_UNAVAILABLE,
  REASON_EMPTY_COHORT,
  REASON_NON_CONTIGUOUS,
  REASON_INSUFFICIENT_BLOCKS
])

// Frozen historical window facts a portable v3 summary can check (calendar_tail800_dev400_min2220_v1):
// 800 mature TEST slots, DEV cutoff 400 sessions before TEST, and T >= 1400 (T at the minimum N=2220).
export const HISTORICAL_TEST_SPAN = 800
export const HISTORICAL_DEVELOPMENT_SPAN = 400
export const HISTORICAL_MIN_TEST_START_INDEX = 1400

// Absolute tolerance for a scored TEST point against the difference of its two stated TEST mean
// Briers, identical to study_results.PAIRED_POINT_TOLERANCE. Both are means over the same n scored
// sessions, so they differ only by rounding: below 4.5e-16 * n for Briers in [0, 2]. 1e-9 holds
// for any cohort under two million sessions and stays far below the 4-decimal display.
export const PAIRED_POINT_TOLERANCE = 1e-9
const PAIR_COMPARATORS: Record<string, 'frequency' | 'logistic'> = {
  heuristic_minus_frequency: 'frequency',
  heuristic_minus_logistic: 'logistic'
}

export const PROBABILITY_SUM_TOLERANCE = 1e-12
export const MAX_THREE_CLASS_BRIER = 2.0

const _SHA256_HEX_REGEX = /^[0-9A-Fa-f]{64}$/
const _IDENTIFIER_REGEX = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/
const _ISO_DATE_REGEX = /^[0-9]{4}-[0-9]{2}-[0-9]{2}$/

// --- Strict Types ---

export interface ReleaseDescriptor {
  schema_version: string
  run_id: string
  study_id: string
  protocol_id: string
  summary_schema_version: string
  coverage_end_date: string
  summary_bytes: number
  summary_sha256: string
  manifest_bytes: number
  manifest_sha256: string
}

export interface FileIdentity {
  raw_byte_count: number
  sha256: string
}

export interface ReplayIdentity {
  claim_label: string
  script: FileIdentity
  request: FileIdentity
  response: FileIdentity
  model_sha256: string
  build_manifest_sha256: string
  calculation_id: string
}

export interface DatasetAttribution {
  source_kind: string
  asset_label: string
  series_id: string
  coverage_start_date: string
  coverage_end_date: string
}

export interface ChronologicalCutoffs {
  development_start: string
  test_start: string
}

export interface AdmissionSummary {
  mature_test_start_index: number
  mature_test_end_index: number
  mature_test_span_count: number
  warmup_gap_count: number
  missing_vix_gap_count: number
  union_gap_count: number
  gap_digest: string
  policy: string
}

export interface FixedDefinitions {
  classes: string[]
  neutral_band: string
  horizon_sessions: number
  primary_probability_metric: string
  log_loss_zero_policy: string
}

export interface PartitionCounts {
  raw_partition_count: number
  eligible_count: number
  excluded_count: number
  requested_count: number
  exclusion_reason_counts: Record<string, number>
  model_available_counts: Record<string, number>
}

export interface ReliabilityBin {
  class_label: string
  bin_index: number
  count: number
  mean_probability: number | null
  observed_frequency: number | null
}

export interface ModelMetrics {
  mean_brier: number | null
  mean_log_loss: number | null
  log_loss_state: 'finite' | 'infinite' | 'empty'
  zero_actual_probability_count: number
  tie_count: number
  accuracy: number | null
  confusion: number[][]
  class_recall: (number | null)[]
  reliability_bins: ReliabilityBin[]
}

export interface PartitionMetrics {
  sample_count: number
  class_support: number[]
  status: string
  models: {
    heuristic: ModelMetrics
    frequency: ModelMetrics
    logistic: ModelMetrics
  }
}

export interface MethodStates {
  heuristic: { available: boolean }
  frequency: { available: boolean; unavailable_reason: string | null }
  logistic: { available: boolean; unavailable_reason: string | null; failure_stage: string | null }
}

export interface PartitionData {
  partition: 'development' | 'test'
  cutoff_index: number
  cutoff_date: string
  counts: PartitionCounts
  comparison_status: 'scored' | 'empty' | 'comparison_unavailable'
  comparison_unavailable_reasons: string[]
  method_states: MethodStates
  metrics: PartitionMetrics | null
}

export interface UncertaintyPairResult {
  pair_id: string
  lower: number | null
  upper: number | null
}

export interface UncertaintyBlockLengthResult {
  block_length: number
  label: string
  status: 'available' | 'unavailable'
  reason: string | null
  seed: number
  pairs: UncertaintyPairResult[]
}

export interface UncertaintyPointDifference {
  pair_id: string
  point_difference: number | null
}

export interface UncertaintyResult {
  protocol_id: string
  method: string
  status: 'available' | 'partially_available' | 'unavailable'
  reason: string | null
  n: number
  mature_span_count: number
  replicates: number
  nominal_coverage: number
  quantile_rule: string
  block_floor_factor: number
  point_differences: UncertaintyPointDifference[]
  block_lengths: UncertaintyBlockLengthResult[]
}

export interface HistoricalEvaluationSummary {
  schema_version: string
  run_id: string
  study_id: string
  protocol_id: string
  data_kind: string
  development_status: string
  claim_label: string
  dataset_attribution: DatasetAttribution
  replay_identity: ReplayIdentity
  provenance_identity: Record<string, string>
  chronological_cutoffs: ChronologicalCutoffs
  admission_summary: AdmissionSummary
  fixed_definitions: FixedDefinitions
  partitions: {
    development: PartitionData
    test: PartitionData
  }
  uncertainty: UncertaintyResult
  limitations: string[]
}

export interface UiDisplayState {
  display_state: 'unavailable' | 'error' | 'unsupported_version' | 'stale' | 'displayable'
  can_display_metrics: boolean
  reason: string
  summary_data: HistoricalEvaluationSummary | null
}

// --- Strict JSON Parser & Decoders ---

function failValidation(path: string, message: string): never {
  throw new Error(`${path}: ${message}`)
}

export function parseStrictJson(jsonText: string): unknown {
  let pos = 0
  const len = jsonText.length

  function skipWhitespace(): void {
    while (pos < len) {
      const ch = jsonText.charCodeAt(pos)
      if (ch === 0x20 || ch === 0x09 || ch === 0x0a || ch === 0x0d) {
        pos++
      } else {
        break
      }
    }
  }

  function parseValue(): unknown {
    skipWhitespace()
    if (pos >= len) {
      throw new Error('Unexpected end of JSON input')
    }
    const ch = jsonText[pos]
    if (ch === '{') return parseObject()
    if (ch === '[') return parseArray()
    if (ch === '"') return parseString()
    if (ch === 't' || ch === 'f') return parseBoolean()
    if (ch === 'n') return parseNull()
    if (ch === '-' || (ch >= '0' && ch <= '9')) return parseNumber()
    throw new Error(`Unexpected character in JSON: '${ch}' at position ${pos}`)
  }

  function parseObject(): Record<string, unknown> {
    pos++ // skip '{'
    const obj: Record<string, unknown> = {}
    const seen = new Set<string>()
    skipWhitespace()
    if (pos < len && jsonText[pos] === '}') {
      pos++
      return obj
    }
    while (pos < len) {
      skipWhitespace()
      if (pos >= len || jsonText[pos] !== '"') {
        throw new Error(`Expected string key in object at position ${pos}`)
      }
      const key = parseString()
      if (seen.has(key)) {
        throw new Error(`Duplicate JSON key: "${key}"`)
      }
      seen.add(key)
      skipWhitespace()
      if (pos >= len || jsonText[pos] !== ':') {
        throw new Error(`Expected ':' after key at position ${pos}`)
      }
      pos++ // skip ':'
      const val = parseValue()
      // Define an own data property so that every JSON member, including a key spelled
      // "__proto__" (literally or via \u escapes), stays visible to the closed-key checks.
      // Plain assignment would invoke the inherited __proto__ setter and hide the member.
      Object.defineProperty(obj, key, { value: val, enumerable: true, writable: true, configurable: true })
      skipWhitespace()
      if (pos >= len) {
        throw new Error('Unterminated object in JSON')
      }
      if (jsonText[pos] === '}') {
        pos++
        return obj
      }
      if (jsonText[pos] === ',') {
        pos++
      } else {
        throw new Error(`Expected ',' or '}' in object at position ${pos}`)
      }
    }
    throw new Error('Unterminated object in JSON')
  }

  function parseArray(): unknown[] {
    pos++ // skip '['
    const arr: unknown[] = []
    skipWhitespace()
    if (pos < len && jsonText[pos] === ']') {
      pos++
      return arr
    }
    while (pos < len) {
      const val = parseValue()
      arr.push(val)
      skipWhitespace()
      if (pos >= len) {
        throw new Error('Unterminated array in JSON')
      }
      if (jsonText[pos] === ']') {
        pos++
        return arr
      }
      if (jsonText[pos] === ',') {
        pos++
      } else {
        throw new Error(`Expected ',' or ']' in array at position ${pos}`)
      }
    }
    throw new Error('Unterminated array in JSON')
  }

  function parseString(): string {
    pos++ // skip leading '"'
    let start = pos
    let str = ''
    while (pos < len) {
      const ch = jsonText[pos]
      if (ch === '"') {
        str += jsonText.slice(start, pos)
        pos++
        return str
      }
      if (ch === '\\') {
        str += jsonText.slice(start, pos)
        pos++
        if (pos >= len) throw new Error('Unterminated escape sequence in string')
        const esc = jsonText[pos]
        if (esc === '"' || esc === '\\' || esc === '/') {
          str += esc
          pos++
        } else if (esc === 'b') {
          str += '\b'
          pos++
        } else if (esc === 'f') {
          str += '\f'
          pos++
        } else if (esc === 'n') {
          str += '\n'
          pos++
        } else if (esc === 'r') {
          str += '\r'
          pos++
        } else if (esc === 't') {
          str += '\t'
          pos++
        } else if (esc === 'u') {
          pos++
          if (pos + 4 > len) throw new Error('Incomplete unicode escape')
          const hex = jsonText.slice(pos, pos + 4)
          if (!/^[0-9A-Fa-f]{4}$/.test(hex)) throw new Error(`Invalid unicode escape: \\u${hex}`)
          str += String.fromCharCode(parseInt(hex, 16))
          pos += 4
        } else {
          throw new Error(`Invalid escape character: \\${esc}`)
        }
        start = pos
      } else {
        const code = jsonText.charCodeAt(pos)
        if (code < 0x20) {
          throw new Error(`Unescaped control character in string at position ${pos}`)
        }
        pos++
      }
    }
    throw new Error('Unterminated string in JSON')
  }

  function parseBoolean(): boolean {
    if (jsonText.startsWith('true', pos)) {
      pos += 4
      return true
    }
    if (jsonText.startsWith('false', pos)) {
      pos += 5
      return false
    }
    throw new Error(`Unexpected token at position ${pos}`)
  }

  function parseNull(): null {
    if (jsonText.startsWith('null', pos)) {
      pos += 4
      return null
    }
    throw new Error(`Unexpected token at position ${pos}`)
  }

  function parseNumber(): number {
    const start = pos
    if (jsonText[pos] === '-') pos++
    if (pos >= len) throw new Error('Invalid number')
    if (jsonText[pos] === '0') {
      pos++
    } else if (jsonText[pos] >= '1' && jsonText[pos] <= '9') {
      while (pos < len && jsonText[pos] >= '0' && jsonText[pos] <= '9') pos++
    } else {
      throw new Error(`Invalid number format at position ${pos}`)
    }
    if (pos < len && jsonText[pos] === '.') {
      pos++
      if (pos >= len || jsonText[pos] < '0' || jsonText[pos] > '9') {
        throw new Error(`Invalid decimal in number at position ${pos}`)
      }
      while (pos < len && jsonText[pos] >= '0' && jsonText[pos] <= '9') pos++
    }
    if (pos < len && (jsonText[pos] === 'e' || jsonText[pos] === 'E')) {
      pos++
      if (pos < len && (jsonText[pos] === '+' || jsonText[pos] === '-')) pos++
      if (pos >= len || jsonText[pos] < '0' || jsonText[pos] > '9') {
        throw new Error(`Invalid exponent in number at position ${pos}`)
      }
      while (pos < len && jsonText[pos] >= '0' && jsonText[pos] <= '9') pos++
    }
    const numStr = jsonText.slice(start, pos)
    const val = Number(numStr)
    if (!Number.isFinite(val)) {
      throw new Error(`Number out of finite range: ${numStr}`)
    }
    return val
  }

  const result = parseValue()
  skipWhitespace()
  if (pos < len) {
    throw new Error(`Unexpected trailing character '${jsonText[pos]}' at position ${pos}`)
  }
  return result
}

export function parseStrictJsonBytes(rawBytes: Uint8Array | ArrayBuffer): unknown {
  const bytes = rawBytes instanceof Uint8Array ? rawBytes : new Uint8Array(rawBytes)
  if (bytes.length >= 3 && bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf) {
    throw new Error('UTF-8 BOM is not permitted in strict JSON')
  }
  const decoder = new TextDecoder('utf-8', { fatal: true })
  let text: string
  try {
    text = decoder.decode(bytes)
  } catch (err: any) {
    throw new Error(`Strict JSON is not valid UTF-8: ${err.message}`)
  }
  return parseStrictJson(text)
}

// --- Structural Validation Helpers ---

function requireObject(value: unknown, expectedKeys: Set<string>, path: string): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    failValidation(path, `expected object, got ${Array.isArray(value) ? 'array' : typeof value}`)
  }
  const rec = value as Record<string, unknown>
  const actualKeys = Object.keys(rec)
  const actualKeySet = new Set(actualKeys)
  if (actualKeySet.size !== expectedKeys.size) {
    const missing = Array.from(expectedKeys).filter(k => !actualKeySet.has(k)).sort()
    const extra = actualKeys.filter(k => !expectedKeys.has(k)).sort()
    failValidation(path, `key mismatch; missing=[${missing.join(', ')}], unknown=[${extra.join(', ')}]`)
  }
  for (const k of actualKeys) {
    if (!expectedKeys.has(k)) {
      const missing = Array.from(expectedKeys).filter(ek => !actualKeySet.has(ek)).sort()
      const extra = actualKeys.filter(ek => !expectedKeys.has(ek)).sort()
      failValidation(path, `key mismatch; missing=[${missing.join(', ')}], unknown=[${extra.join(', ')}]`)
    }
  }
  return rec
}

function requireInt(value: unknown, path: string, minimum = 0): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value)) {
    failValidation(path, `expected non-boolean safe integer, got ${String(value)}`)
  }
  if (value < minimum) {
    failValidation(path, `expected integer >= ${minimum}, got ${value}`)
  }
  return value
}

function requireStr(value: unknown, path: string, allowEmpty = false): string {
  if (typeof value !== 'string' || (!allowEmpty && value.length === 0)) {
    failValidation(path, `expected non-empty string, got ${String(value)}`)
  }
  return value
}

function requireNumber(value: unknown, path: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    failValidation(path, `expected finite number, got ${String(value)}`)
  }
  return value
}

function requireFraction(value: unknown, path: string): number {
  const num = requireNumber(value, path)
  if (num < 0.0 || num > 1.0) {
    failValidation(path, `expected value in [0, 1], got ${num}`)
  }
  return num
}

function requireLoss(value: unknown, path: string, maximum?: number): number {
  const num = requireNumber(value, path)
  if (num < 0.0 || (maximum !== undefined && num > maximum)) {
    failValidation(path, `loss out of range: ${num}`)
  }
  return num
}

function requireSha(value: unknown, path: string): string {
  if (typeof value !== 'string' || !_SHA256_HEX_REGEX.test(value)) {
    failValidation(path, `expected 64-hex SHA-256, got ${String(value)}`)
  }
  return value
}

function requireDate(value: unknown, path: string): string {
  if (typeof value !== 'string' || !_ISO_DATE_REGEX.test(value)) {
    failValidation(path, `expected ISO date (YYYY-MM-DD), got ${String(value)}`)
  }
  const parts = value.split('-').map(Number)
  const d = new Date(parts[0], parts[1] - 1, parts[2])
  if (
    d.getFullYear() !== parts[0] ||
    d.getMonth() !== parts[1] - 1 ||
    d.getDate() !== parts[2]
  ) {
    failValidation(path, `invalid calendar date ${value}`)
  }
  return value
}

function requireEnum<T extends string>(value: unknown, allowed: readonly T[], path: string): T {
  if (typeof value !== 'string' || !allowed.includes(value as T)) {
    failValidation(path, `expected one of [${allowed.join(', ')}], got ${String(value)}`)
  }
  return value as T
}

function requireIdentifier(value: unknown, path: string): string {
  if (typeof value !== 'string' || !_IDENTIFIER_REGEX.test(value)) {
    failValidation(path, `expected portable identifier, got ${String(value)}`)
  }
  return value
}

function requireList(value: unknown, path: string, length?: number): unknown[] {
  if (!Array.isArray(value)) {
    failValidation(path, `expected array, got ${typeof value}`)
  }
  if (length !== undefined && value.length !== length) {
    failValidation(path, `expected ${length} entries, got ${value.length}`)
  }
  return value
}

function requireStatedRate(value: number, numerator: number, denominator: number, path: string): void {
  const expected = numerator / denominator
  if (Math.abs(value - expected) > PROBABILITY_SUM_TOLERANCE) {
    failValidation(path, `rate ${value} contradicts counts ${numerator}/${denominator} (${expected})`)
  }
}

// --- Closed Schema Validators ---

export function parseReleaseDescriptor(rawBytes: Uint8Array | ArrayBuffer): ReleaseDescriptor {
  const doc = parseStrictJsonBytes(rawBytes)
  const path = 'descriptor'
  const expectedKeys = new Set([
    'schema_version',
    'run_id',
    'study_id',
    'protocol_id',
    'summary_schema_version',
    'coverage_end_date',
    'summary_bytes',
    'summary_sha256',
    'manifest_bytes',
    'manifest_sha256'
  ])
  const obj = requireObject(doc, expectedKeys, path)

  if (obj.schema_version !== SCHEMA_VERSION_RELEASE_DESCRIPTOR) {
    failValidation(`${path}.schema_version`, `expected '${SCHEMA_VERSION_RELEASE_DESCRIPTOR}', got ${String(obj.schema_version)}`)
  }
  requireIdentifier(obj.run_id, `${path}.run_id`)
  requireIdentifier(obj.study_id, `${path}.study_id`)
  requireStr(obj.protocol_id, `${path}.protocol_id`)
  requireStr(obj.summary_schema_version, `${path}.summary_schema_version`)
  requireDate(obj.coverage_end_date, `${path}.coverage_end_date`)
  requireInt(obj.summary_bytes, `${path}.summary_bytes`, 1)
  requireSha(obj.summary_sha256, `${path}.summary_sha256`)
  requireInt(obj.manifest_bytes, `${path}.manifest_bytes`, 1)
  requireSha(obj.manifest_sha256, `${path}.manifest_sha256`)

  return obj as unknown as ReleaseDescriptor
}

export function validateFileIdentity(value: unknown, path: string): FileIdentity {
  const obj = requireObject(value, new Set(['raw_byte_count', 'sha256']), path)
  requireInt(obj.raw_byte_count, `${path}.raw_byte_count`)
  requireSha(obj.sha256, `${path}.sha256`)
  return obj as unknown as FileIdentity
}

export function validateReplayIdentity(value: unknown, path: string): ReplayIdentity {
  const expected = new Set([
    'claim_label',
    'script',
    'request',
    'response',
    'model_sha256',
    'build_manifest_sha256',
    'calculation_id'
  ])
  const obj = requireObject(value, expected, path)
  requireStr(obj.claim_label, `${path}.claim_label`)
  validateFileIdentity(obj.script, `${path}.script`)
  validateFileIdentity(obj.request, `${path}.request`)
  validateFileIdentity(obj.response, `${path}.response`)
  requireSha(obj.model_sha256, `${path}.model_sha256`)
  requireSha(obj.build_manifest_sha256, `${path}.build_manifest_sha256`)
  requireStr(obj.calculation_id, `${path}.calculation_id`)
  return obj as unknown as ReplayIdentity
}

export function validateAdmissionSummary(value: unknown, path: string): AdmissionSummary {
  const expected = new Set([
    'mature_test_start_index',
    'mature_test_end_index',
    'mature_test_span_count',
    'warmup_gap_count',
    'missing_vix_gap_count',
    'union_gap_count',
    'gap_digest',
    'policy'
  ])
  const obj = requireObject(value, expected, path)
  const start = requireInt(obj.mature_test_start_index, `${path}.mature_test_start_index`)
  const end = requireInt(obj.mature_test_end_index, `${path}.mature_test_end_index`)
  const span = requireInt(obj.mature_test_span_count, `${path}.mature_test_span_count`)
  if (end < start || span !== end - start) {
    failValidation(path, `mature span (${span}) does not match bounds ${start} to ${end}`)
  }
  const warmup = requireInt(obj.warmup_gap_count, `${path}.warmup_gap_count`)
  const missing = requireInt(obj.missing_vix_gap_count, `${path}.missing_vix_gap_count`)
  const union = requireInt(obj.union_gap_count, `${path}.union_gap_count`)
  if (union > span || union < Math.max(warmup, missing) || union > warmup + missing) {
    failValidation(path, 'gap union count is inconsistent with reason counts')
  }
  requireSha(obj.gap_digest, `${path}.gap_digest`)
  requireStr(obj.policy, `${path}.policy`)
  return obj as unknown as AdmissionSummary
}

export function validateCountsDocument(value: unknown, path: string): PartitionCounts {
  const expected = new Set([
    'raw_partition_count',
    'eligible_count',
    'excluded_count',
    'requested_count',
    'exclusion_reason_counts',
    'model_available_counts'
  ])
  const obj = requireObject(value, expected, path)
  const raw = requireInt(obj.raw_partition_count, `${path}.raw_partition_count`)
  const eligible = requireInt(obj.eligible_count, `${path}.eligible_count`)
  const excluded = requireInt(obj.excluded_count, `${path}.excluded_count`)
  const requested = requireInt(obj.requested_count, `${path}.requested_count`)

  if (excluded !== raw - eligible) {
    failValidation(path, 'excluded_count must equal raw_partition_count - eligible_count')
  }
  if (requested !== eligible) {
    failValidation(path, 'requested_count must equal eligible_count')
  }

  if (typeof obj.exclusion_reason_counts !== 'object' || obj.exclusion_reason_counts === null || Array.isArray(obj.exclusion_reason_counts)) {
    failValidation(`${path}.exclusion_reason_counts`, 'expected object')
  }
  const reasons = obj.exclusion_reason_counts as Record<string, unknown>
  let reasonSum = 0
  for (const [rName, rCount] of Object.entries(reasons)) {
    requireEnum(rName, EXCLUSION_REASONS, `${path}.exclusion_reason_counts key`)
    const cnt = requireInt(rCount, `${path}.exclusion_reason_counts[${rName}]`, 1)
    if (cnt > excluded) {
      failValidation(path, `reason ${rName} count exceeds unique exclusions`)
    }
    reasonSum += cnt
  }
  if (reasonSum < excluded) {
    failValidation(path, 'reason counts cannot cover unique exclusions')
  }

  const avail = requireObject(obj.model_available_counts, new Set(MODEL_NAMES), `${path}.model_available_counts`)
  for (const name of MODEL_NAMES) {
    const cnt = requireInt(avail[name], `${path}.model_available_counts.${name}`)
    if (cnt > requested) {
      failValidation(path, `${name} available count exceeds requested targets`)
    }
  }

  return obj as unknown as PartitionCounts
}

export function validateModelMetricsDocument(
  value: unknown,
  path: string,
  sampleCount: number,
  classSupport: number[]
): ModelMetrics {
  const expected = new Set([
    'mean_brier',
    'mean_log_loss',
    'log_loss_state',
    'zero_actual_probability_count',
    'tie_count',
    'accuracy',
    'confusion',
    'class_recall',
    'reliability_bins'
  ])
  const obj = requireObject(value, expected, path)
  const state = requireEnum(obj.log_loss_state, ['finite', 'infinite', 'empty'] as const, `${path}.log_loss_state`)
  const zeroCount = requireInt(obj.zero_actual_probability_count, `${path}.zero_actual_probability_count`)
  const tieCount = requireInt(obj.tie_count, `${path}.tie_count`)

  if (zeroCount > sampleCount || tieCount > sampleCount) {
    failValidation(path, 'row counters exceed sample_count')
  }

  if (sampleCount === 0) {
    if (state !== 'empty' || obj.mean_brier !== null || obj.mean_log_loss !== null || obj.accuracy !== null) {
      failValidation(path, 'an empty cohort must have null metrics and empty state')
    }
  } else {
    requireLoss(obj.mean_brier, `${path}.mean_brier`, MAX_THREE_CLASS_BRIER)
    requireFraction(obj.accuracy, `${path}.accuracy`)
    if (state === 'empty') {
      failValidation(path, 'a nonempty cohort cannot have empty log-loss state')
    }
    if (state === 'finite') {
      requireLoss(obj.mean_log_loss, `${path}.mean_log_loss`)
      if (zeroCount !== 0) {
        failValidation(path, 'finite log-loss state cannot have zero-probability rows')
      }
    } else {
      if (obj.mean_log_loss !== null) {
        failValidation(path, 'infinite log-loss state must keep mean_log_loss null')
      }
      if (zeroCount === 0) {
        failValidation(path, 'infinite log-loss state requires a zero-probability row')
      }
    }
  }

  const confusion = requireList(obj.confusion, `${path}.confusion`, 3) as number[][]
  let diagonalSum = 0
  for (let rIdx = 0; rIdx < 3; rIdx++) {
    const row = requireList(confusion[rIdx], `${path}.confusion[${rIdx}]`, 3) as number[]
    let rowSum = 0
    for (let cIdx = 0; cIdx < 3; cIdx++) {
      rowSum += requireInt(row[cIdx], `${path}.confusion[${rIdx}][${cIdx}]`)
      if (rIdx === cIdx) diagonalSum += row[cIdx]
    }
    if (rowSum !== classSupport[rIdx]) {
      failValidation(`${path}.confusion[${rIdx}]`, `row sum (${rowSum}) must equal class support (${classSupport[rIdx]})`)
    }
  }
  if (sampleCount > 0) {
    requireStatedRate(obj.accuracy as number, diagonalSum, sampleCount, `${path}.accuracy`)
  }

  const recalls = requireList(obj.class_recall, `${path}.class_recall`, 3)
  for (let idx = 0; idx < 3; idx++) {
    const rec = recalls[idx]
    if (classSupport[idx] === 0) {
      if (rec !== null) failValidation(`${path}.class_recall[${idx}]`, 'undefined recall must stay null')
    } else {
      requireFraction(rec, `${path}.class_recall[${idx}]`)
      requireStatedRate(rec as number, confusion[idx][idx], classSupport[idx], `${path}.class_recall[${idx}]`)
    }
  }

  const bins = requireList(obj.reliability_bins, `${path}.reliability_bins`, 30)
  for (let pos = 0; pos < 30; pos++) {
    const bPath = `${path}.reliability_bins[${pos}]`
    const bObj = requireObject(bins[pos], new Set(['class_label', 'bin_index', 'count', 'mean_probability', 'observed_frequency']), bPath)
    if (bObj.class_label !== ORDERED_CLASSES[Math.floor(pos / 10)] || bObj.bin_index !== pos % 10) {
      failValidation(bPath, 'bins must stay in class-major order')
    }
    const bCount = requireInt(bObj.count, `${bPath}.count`)
    if (bCount === 0) {
      if (bObj.mean_probability !== null || bObj.observed_frequency !== null) {
        failValidation(bPath, 'an empty bin must keep null means')
      }
    } else {
      requireFraction(bObj.mean_probability, `${bPath}.mean_probability`)
      requireFraction(bObj.observed_frequency, `${bPath}.observed_frequency`)
    }
  }
  for (let cPos = 0; cPos < 3; cPos++) {
    let cSum = 0
    for (let k = 0; k < 10; k++) {
      cSum += (bins[cPos * 10 + k] as { count: number }).count
    }
    if (cSum !== sampleCount) {
      failValidation(path, `bin counts for ${ORDERED_CLASSES[cPos]} (${cSum}) must equal sample_count (${sampleCount})`)
    }
  }

  return obj as unknown as ModelMetrics
}

export function validateMetricsDocument(
  value: unknown,
  path: string,
  comparisonStatus: string,
  requestedCount: number
): PartitionMetrics | null {
  if (comparisonStatus === STATUS_COMPARISON_UNAVAILABLE) {
    if (value !== null) {
      failValidation(path, 'comparison_unavailable must keep metrics null')
    }
    return null
  }
  const obj = requireObject(value, new Set(['sample_count', 'class_support', 'status', 'models']), path)
  const sampleCount = requireInt(obj.sample_count, `${path}.sample_count`)
  const supportList = requireList(obj.class_support, `${path}.class_support`, 3) as number[]
  let supportSum = 0
  for (let i = 0; i < 3; i++) {
    supportSum += requireInt(supportList[i], `${path}.class_support[${i}]`)
  }
  if (supportSum !== sampleCount) {
    failValidation(path, 'class support must sum to sample_count')
  }
  if (sampleCount !== requestedCount) {
    failValidation(path, 'sample_count must equal requested_count')
  }

  const expectedStatus = comparisonStatus === STATUS_SCORED ? 'scored' : 'empty'
  if (obj.status !== expectedStatus) {
    failValidation(path, `metric status '${String(obj.status)}' contradicts comparison status '${comparisonStatus}'`)
  }
  if ((comparisonStatus === STATUS_SCORED) !== (sampleCount > 0)) {
    failValidation(path, 'scored requires rows; empty requires none')
  }

  const modelsObj = requireObject(obj.models, new Set(MODEL_NAMES), `${path}.models`)
  for (const name of MODEL_NAMES) {
    validateModelMetricsDocument(modelsObj[name], `${path}.models.${name}`, sampleCount, supportList)
  }

  return obj as unknown as PartitionMetrics
}

export function validateMethodStatesDocument(value: unknown, path: string, comparisonStatus: string): MethodStates {
  const obj = requireObject(value, new Set(MODEL_NAMES), path)
  const h = requireObject(obj.heuristic, new Set(['available']), `${path}.heuristic`)
  const f = requireObject(obj.frequency, new Set(['available', 'unavailable_reason']), `${path}.frequency`)
  const l = requireObject(obj.logistic, new Set(['available', 'unavailable_reason', 'failure_stage']), `${path}.logistic`)

  if (typeof h.available !== 'boolean' || typeof f.available !== 'boolean' || typeof l.available !== 'boolean') {
    failValidation(path, 'method availability must be boolean')
  }
  if (h.available !== true) {
    failValidation(`${path}.heuristic`, 'heuristic forecast must be available')
  }

  if (f.available) {
    if (f.unavailable_reason !== null) failValidation(`${path}.frequency`, 'available method cannot carry a reason')
  } else {
    requireEnum(f.unavailable_reason, FREQUENCY_UNAVAILABLE_REASONS, `${path}.frequency.unavailable_reason`)
  }

  if (l.available) {
    if (l.unavailable_reason !== null || l.failure_stage !== null) {
      failValidation(`${path}.logistic`, 'available method cannot carry reason or failure stage')
    }
  } else {
    const reason = requireEnum(l.unavailable_reason, LOGISTIC_UNAVAILABLE_REASONS, `${path}.logistic.unavailable_reason`)
    if (reason === 'no_fit_rows' || reason === 'missing_training_classes') {
      if (l.failure_stage !== null) failValidation(`${path}.logistic`, `${reason} has no failure stage`)
    } else {
      requireEnum(l.failure_stage, LOGISTIC_FAILURE_STAGES, `${path}.logistic.failure_stage`)
    }
  }

  const allAvailable = f.available && l.available
  if (allAvailable === (comparisonStatus === STATUS_COMPARISON_UNAVAILABLE)) {
    failValidation(path, `method availability contradicts comparison status '${comparisonStatus}'`)
  }

  return obj as unknown as MethodStates
}

export function validateUncertaintyResultDocument(value: unknown): UncertaintyResult {
  const path = 'uncertainty'
  const expected = new Set([
    'protocol_id',
    'method',
    'status',
    'reason',
    'n',
    'mature_span_count',
    'replicates',
    'nominal_coverage',
    'quantile_rule',
    'block_floor_factor',
    'point_differences',
    'block_lengths'
  ])
  const doc = requireObject(value, expected, path)

  if (doc.protocol_id !== UNCERTAINTY_PROTOCOL_ID) {
    failValidation(`${path}.protocol_id`, `expected '${UNCERTAINTY_PROTOCOL_ID}', got ${String(doc.protocol_id)}`)
  }
  if (doc.method !== UNCERTAINTY_METHOD) {
    failValidation(`${path}.method`, `expected '${UNCERTAINTY_METHOD}', got ${String(doc.method)}`)
  }
  const topStatus = requireEnum(doc.status, [
    UNCERTAINTY_STATUS_AVAILABLE,
    UNCERTAINTY_STATUS_PARTIALLY_AVAILABLE,
    UNCERTAINTY_STATUS_UNAVAILABLE
  ] as const, `${path}.status`)

  const topReason = doc.reason
  if (topStatus === UNCERTAINTY_STATUS_AVAILABLE || topStatus === UNCERTAINTY_STATUS_PARTIALLY_AVAILABLE) {
    if (topReason !== null) failValidation(`${path}.reason`, 'available or partially available uncertainty must have reason null')
  } else {
    if (typeof topReason !== 'string' || !SUPPORTED_UNAVAILABLE_REASONS.has(topReason)) {
      failValidation(`${path}.reason`, `unavailable status requires supported reason, got ${String(topReason)}`)
    }
  }

  const n = requireInt(doc.n, `${path}.n`)
  const span = requireInt(doc.mature_span_count, `${path}.mature_span_count`)
  const replicates = requireInt(doc.replicates, `${path}.replicates`)
  if (replicates !== BOOTSTRAP_REPLICATES) {
    failValidation(`${path}.replicates`, `replicates must be ${BOOTSTRAP_REPLICATES}`)
  }
  const coverage = requireNumber(doc.nominal_coverage, `${path}.nominal_coverage`)
  if (coverage !== NOMINAL_COVERAGE) {
    failValidation(`${path}.nominal_coverage`, `nominal_coverage must be ${NOMINAL_COVERAGE}`)
  }
  if (doc.quantile_rule !== QUANTILE_RULE) {
    failValidation(`${path}.quantile_rule`, `quantile_rule must be '${QUANTILE_RULE}'`)
  }
  const floorFactor = requireInt(doc.block_floor_factor, `${path}.block_floor_factor`)
  if (floorFactor !== BLOCK_FLOOR_FACTOR) {
    failValidation(`${path}.block_floor_factor`, `block_floor_factor must be ${BLOCK_FLOOR_FACTOR}`)
  }

  const ptDiffs = requireList(doc.point_differences, `${path}.point_differences`, ORDERED_PAIR_IDS.length)
  for (let pos = 0; pos < ORDERED_PAIR_IDS.length; pos++) {
    const pId = ORDERED_PAIR_IDS[pos]
    const pEntry = requireObject(ptDiffs[pos], new Set(['pair_id', 'point_difference']), `${path}.point_differences[${pos}]`)
    if (pEntry.pair_id !== pId) {
      failValidation(`${path}.point_differences[${pos}]`, `pair_id must be ${pId}`)
    }
    const val = pEntry.point_difference
    if (val !== null) {
      requireNumber(val, `${path}.point_differences[${pos}].point_difference`)
      if ((val as number) < -2.0 || (val as number) > 2.0) {
        failValidation(`${path}.point_differences[${pos}]`, `point difference out of range [-2, 2]: ${val}`)
      }
    }
  }

  const blList = requireList(doc.block_lengths, `${path}.block_lengths`, BLOCK_LENGTHS.length)
  for (let pos = 0; pos < BLOCK_LENGTHS.length; pos++) {
    const L = BLOCK_LENGTHS[pos]
    const bEntry = requireObject(blList[pos], new Set(['block_length', 'label', 'status', 'reason', 'seed', 'pairs']), `${path}.block_lengths[${pos}]`)
    if (bEntry.block_length !== L) {
      failValidation(`${path}.block_lengths[${pos}].block_length`, `expected ${L}`)
    }
    if (bEntry.label !== BLOCK_LENGTH_LABELS[L]) {
      failValidation(`${path}.block_lengths[${pos}].label`, 'label mismatch')
    }
    if (bEntry.seed !== BLOCK_LENGTH_SEEDS[L]) {
      failValidation(`${path}.block_lengths[${pos}].seed`, 'seed mismatch')
    }
    const bStatus = requireEnum(bEntry.status, [UNCERTAINTY_STATUS_AVAILABLE, UNCERTAINTY_STATUS_UNAVAILABLE] as const, `${path}.block_lengths[${pos}].status`)
    if (bStatus === UNCERTAINTY_STATUS_AVAILABLE) {
      if (bEntry.reason !== null) failValidation(`${path}.block_lengths[${pos}]`, 'available block length must have reason null')
    } else {
      if (typeof bEntry.reason !== 'string' || !SUPPORTED_UNAVAILABLE_REASONS.has(bEntry.reason)) {
        failValidation(`${path}.block_lengths[${pos}]`, `unavailable block length requires supported reason, got ${String(bEntry.reason)}`)
      }
    }

    const pairs = requireList(bEntry.pairs, `${path}.block_lengths[${pos}].pairs`, ORDERED_PAIR_IDS.length)
    for (let pPos = 0; pPos < ORDERED_PAIR_IDS.length; pPos++) {
      const pairId = ORDERED_PAIR_IDS[pPos]
      const pairObj = requireObject(pairs[pPos], new Set(['pair_id', 'lower', 'upper']), `${path}.block_lengths[${pos}].pairs[${pPos}]`)
      if (pairObj.pair_id !== pairId) {
        failValidation(`${path}.block_lengths[${pos}].pairs[${pPos}]`, `pair_id must be ${pairId}`)
      }
      const lo = pairObj.lower
      const hi = pairObj.upper
      if (bStatus === UNCERTAINTY_STATUS_AVAILABLE) {
        if (lo === null || hi === null) {
          failValidation(`${path}.block_lengths[${pos}].pairs[${pPos}]`, 'available block length requires non-null bounds')
        }
        requireNumber(lo, `${path}.block_lengths[${pos}].pairs[${pPos}].lower`)
        requireNumber(hi, `${path}.block_lengths[${pos}].pairs[${pPos}].upper`)
        if ((lo as number) < -2.0 || (lo as number) > 2.0 || (hi as number) < -2.0 || (hi as number) > 2.0) {
          failValidation(`${path}.block_lengths[${pos}].pairs[${pPos}]`, `interval bounds out of range [-2, 2]: [${lo}, ${hi}]`)
        }
        if ((lo as number) > (hi as number)) {
          failValidation(`${path}.block_lengths[${pos}].pairs[${pPos}]`, `lower bound (${lo}) exceeds upper bound (${hi})`)
        }
      } else {
        if (lo !== null || hi !== null) {
          failValidation(`${path}.block_lengths[${pos}].pairs[${pPos}]`, 'unavailable block length requires null bounds')
        }
      }
    }
  }

  // Cross-state relations
  let availableCount = 0
  for (const b of blList as { status: string }[]) {
    if (b.status === UNCERTAINTY_STATUS_AVAILABLE) availableCount++
  }
  const expectedTopStatus =
    availableCount === BLOCK_LENGTHS.length
      ? UNCERTAINTY_STATUS_AVAILABLE
      : availableCount > 0
      ? UNCERTAINTY_STATUS_PARTIALLY_AVAILABLE
      : UNCERTAINTY_STATUS_UNAVAILABLE
  if (topStatus !== expectedTopStatus) {
    failValidation(path, `top status '${topStatus}' contradicts ${availableCount} available lengths`)
  }

  if (topReason && COMMON_UNAVAILABLE_REASONS.includes(topReason as any)) {
    for (const b of blList as { reason: string; block_length: number }[]) {
      if (b.reason !== topReason) {
        failValidation(path, `length ${b.block_length} reason contradicts common reason '${topReason}'`)
      }
    }
  } else {
    if (n === 0 || n !== span) {
      failValidation(path, `floor and available states need n == mature_span_count > 0, got n=${n}, span=${span}`)
    }
    const clearedLengths = new Set(BLOCK_LENGTHS.filter(L => n >= BLOCK_FLOOR_FACTOR * L))
    for (const b of blList as { reason: string | null; block_length: number }[]) {
      const expectedR = clearedLengths.has(b.block_length as any) ? null : REASON_INSUFFICIENT_BLOCKS
      if (b.reason !== expectedR) {
        failValidation(path, `length ${b.block_length} reason contradicts floor at n=${n}`)
      }
    }
  }

  if (topReason === REASON_EMPTY_COHORT && n !== 0) {
    failValidation(path, `empty_cohort requires n == 0, got ${n}`)
  }
  if (topReason === REASON_NON_CONTIGUOUS && !(n > 0 && n < span)) {
    failValidation(path, `non_contiguous_test_cohort requires 0 < n < mature_span_count, got n=${n}, span=${span}`)
  }
  if (n > span) {
    failValidation(path, `n (${n}) exceeds mature_span_count (${span})`)
  }

  const noPoint = Boolean(topReason && NO_POINT_REASONS.includes(topReason as any))
  for (const entry of ptDiffs as { pair_id: string; point_difference: number | null }[]) {
    if ((entry.point_difference === null) !== noPoint) {
      failValidation(path, `${entry.pair_id} point difference contradicts reason '${String(topReason)}'`)
    }
  }

  return doc as unknown as UncertaintyResult
}

// Mirrors uncertainty.common_unavailable_reason in the same precedence order: the reason that
// makes every block length unavailable, or null when the per-length floor decides.
export function commonUnavailableReason(comparisonStatus: string, n: number, gapCount: number): string | null {
  if (comparisonStatus === STATUS_COMPARISON_UNAVAILABLE) return REASON_COMPARISON_UNAVAILABLE
  if (comparisonStatus === STATUS_EMPTY || n === 0) return REASON_EMPTY_COHORT
  if (gapCount > 0) return REASON_NON_CONTIGUOUS
  return null
}

// Relates the closed portable blocks using only facts the summary carries, as the Python
// validator does: cutoff dates to the declared cutoffs, the TEST index to the mature start, the
// uncertainty count and span to TEST requested and the admitted span, and its reason, length
// states and point nullability to the TEST status, count and admitted gaps. A v3 summary also
// keeps the frozen historical window. The scored count is never inferred from the span.
function validateSummaryRelations(summary: HistoricalEvaluationSummary, schemaVer: string, path: string): void {
  const cutoffs = summary.chronological_cutoffs
  const admission = summary.admission_summary
  const dev = summary.partitions.development
  const test = summary.partitions.test
  if (dev.cutoff_date !== cutoffs.development_start) {
    failValidation(`${path}.partitions.development.cutoff_date`, 'must equal chronological_cutoffs.development_start')
  }
  if (test.cutoff_date !== cutoffs.test_start) {
    failValidation(`${path}.partitions.test.cutoff_date`, 'must equal chronological_cutoffs.test_start')
  }
  const start = admission.mature_test_start_index
  const span = admission.mature_test_span_count
  if (test.cutoff_index !== start) {
    failValidation(`${path}.partitions.test.cutoff_index`, `must equal admission_summary.mature_test_start_index ${start}`)
  }
  if (schemaVer === SCHEMA_VERSION_SUMMARY_V3) {
    if (span !== HISTORICAL_TEST_SPAN) {
      failValidation(`${path}.admission_summary.mature_test_span_count`, `v3 requires ${HISTORICAL_TEST_SPAN} mature slots, got ${span}`)
    }
    if (start < HISTORICAL_MIN_TEST_START_INDEX) {
      failValidation(`${path}.partitions.test.cutoff_index`, `v3 requires a TEST index of at least ${HISTORICAL_MIN_TEST_START_INDEX}, got ${start}`)
    }
    const devIndex = start - HISTORICAL_DEVELOPMENT_SPAN
    if (dev.cutoff_index !== devIndex) {
      failValidation(`${path}.partitions.development.cutoff_index`, `v3 requires the TEST index minus ${HISTORICAL_DEVELOPMENT_SPAN} (${devIndex})`)
    }
  }

  const requested = test.counts.requested_count
  const gaps = admission.union_gap_count
  // The requested keys and the admitted union gaps partition the mature span exactly, whatever
  // the comparator outcome
  if (requested !== span - gaps) {
    failValidation(
      `${path}.partitions.test.counts.requested_count`,
      `must be the admitted span ${span} minus union_gap_count ${gaps} (${span - gaps}), got ${requested}`
    )
  }

  const unc = summary.uncertainty
  if (unc.n !== requested || unc.mature_span_count !== span) {
    failValidation(
      `${path}.uncertainty`,
      `n and mature_span_count must be the TEST requested_count ${requested} and the admitted span ${span}, got ${unc.n} and ${unc.mature_span_count}`
    )
  }
  const commonReason = commonUnavailableReason(test.comparison_status, requested, gaps)
  const cleared: number[] = commonReason !== null ? [] : BLOCK_LENGTHS.filter(L => requested >= BLOCK_FLOOR_FACTOR * L)
  const expectedReason = commonReason !== null || cleared.length > 0 ? commonReason : REASON_INSUFFICIENT_BLOCKS
  if (unc.reason !== expectedReason) {
    failValidation(`${path}.uncertainty.reason`, `must be '${String(expectedReason)}' for the TEST comparison status, requested count and admitted gaps`)
  }
  for (const view of unc.block_lengths) {
    if ((view.status === UNCERTAINTY_STATUS_AVAILABLE) !== cleared.includes(view.block_length)) {
      failValidation(`${path}.uncertainty.block_lengths`, `length ${view.block_length} state contradicts the TEST cohort`)
    }
  }
  const noPoint = commonReason !== null && (NO_POINT_REASONS as readonly string[]).includes(commonReason)
  for (const entry of unc.point_differences) {
    if ((entry.point_difference === null) !== noPoint) {
      failValidation(`${path}.uncertainty.point_differences`, `${entry.pair_id} nullability contradicts the TEST comparison`)
    }
  }
  if (noPoint || test.metrics === null) return
  // A point exists only for a scored TEST with requested origins, whose means are finite. The
  // interval state does not matter: below-floor and gapped points are checked too.
  const models = test.metrics.models
  for (const entry of unc.point_differences) {
    const comparator = PAIR_COMPARATORS[entry.pair_id]
    const expected = (models.heuristic.mean_brier as number) - (models[comparator].mean_brier as number)
    if (Math.abs((entry.point_difference as number) - expected) > PAIRED_POINT_TOLERANCE) {
      failValidation(
        `${path}.uncertainty.point_differences`,
        `${entry.pair_id} ${String(entry.point_difference)} differs from the TEST mean Brier difference heuristic - ${comparator} (${String(expected)}) by more than ${PAIRED_POINT_TOLERANCE}`
      )
    }
  }
}

export function validateSummaryDocument(doc: unknown): HistoricalEvaluationSummary {
  const path = 'summary'
  const expectedKeys = new Set([
    'schema_version',
    'run_id',
    'study_id',
    'protocol_id',
    'data_kind',
    'development_status',
    'claim_label',
    'dataset_attribution',
    'replay_identity',
    'provenance_identity',
    'chronological_cutoffs',
    'admission_summary',
    'fixed_definitions',
    'partitions',
    'uncertainty',
    'limitations'
  ])
  const root = requireObject(doc, expectedKeys, path)

  const schemaVer = requireEnum(root.schema_version, Array.from(SUPPORTED_SUMMARY_SCHEMA_VERSIONS), `${path}.schema_version`)
  requireIdentifier(root.run_id, `${path}.run_id`)
  requireIdentifier(root.study_id, `${path}.study_id`)
  requireEnum(root.protocol_id, Array.from(SUPPORTED_PROTOCOL_IDS), `${path}.protocol_id`)

  if (schemaVer === SCHEMA_VERSION_SUMMARY_V3) {
    if (root.data_kind !== DATA_KIND_HISTORICAL) {
      failValidation(`${path}.data_kind`, `v3 requires '${DATA_KIND_HISTORICAL}', got '${String(root.data_kind)}'`)
    }
    if (root.development_status !== DEVELOPMENT_STATUS_HISTORICAL) {
      failValidation(`${path}.development_status`, `v3 requires '${DEVELOPMENT_STATUS_HISTORICAL}', got '${String(root.development_status)}'`)
    }
  } else {
    if (root.data_kind !== DATA_KIND_SYNTHETIC) {
      failValidation(`${path}.data_kind`, `v2 requires '${DATA_KIND_SYNTHETIC}', got '${String(root.data_kind)}'`)
    }
    if (root.development_status !== DEVELOPMENT_STATUS_SYNTHETIC) {
      failValidation(`${path}.development_status`, `v2 requires '${DEVELOPMENT_STATUS_SYNTHETIC}', got '${String(root.development_status)}'`)
    }
  }

  requireStr(root.claim_label, `${path}.claim_label`)

  // Dataset attribution
  const attr = requireObject(
    root.dataset_attribution,
    new Set(['source_kind', 'asset_label', 'series_id', 'coverage_start_date', 'coverage_end_date']),
    `${path}.dataset_attribution`
  )
  if (schemaVer === SCHEMA_VERSION_SUMMARY_V3) {
    requireEnum(attr.source_kind, [SOURCE_KIND_HISTORICAL], `${path}.dataset_attribution.source_kind`)
  } else {
    requireEnum(attr.source_kind, [SOURCE_KIND_SYNTHETIC], `${path}.dataset_attribution.source_kind`)
  }
  requireStr(attr.asset_label, `${path}.dataset_attribution.asset_label`)
  requireStr(attr.series_id, `${path}.dataset_attribution.series_id`)
  const covStart = requireDate(attr.coverage_start_date, `${path}.dataset_attribution.coverage_start_date`)
  const covEnd = requireDate(attr.coverage_end_date, `${path}.dataset_attribution.coverage_end_date`)
  if (covStart > covEnd) {
    failValidation(`${path}.dataset_attribution`, 'coverage start date must precede coverage end date')
  }

  // Replay identity
  validateReplayIdentity(root.replay_identity, `${path}.replay_identity`)

  // Provenance identity
  const expectedProvKeys =
    schemaVer === SCHEMA_VERSION_SUMMARY_V3
      ? new Set(['config_sha256', 'admission_sha256', 'approval_sha256'])
      : new Set(['config_sha256', 'admission_sha256', 'nifty_input_sha256', 'vix_input_sha256', 'calendar_sha256'])
  const prov = requireObject(root.provenance_identity, expectedProvKeys, `${path}.provenance_identity`)
  for (const k of Array.from(expectedProvKeys)) {
    requireSha(prov[k], `${path}.provenance_identity.${k}`)
  }

  // Chronological cutoffs
  const cutoffs = requireObject(root.chronological_cutoffs, new Set(['development_start', 'test_start']), `${path}.chronological_cutoffs`)
  const devStart = requireDate(cutoffs.development_start, `${path}.chronological_cutoffs.development_start`)
  const testStart = requireDate(cutoffs.test_start, `${path}.chronological_cutoffs.test_start`)
  if (devStart >= testStart) {
    failValidation(`${path}.chronological_cutoffs`, 'development_start must precede test_start')
  }

  // Admission summary
  validateAdmissionSummary(root.admission_summary, `${path}.admission_summary`)

  // Fixed definitions
  const defs = requireObject(
    root.fixed_definitions,
    new Set(['classes', 'neutral_band', 'horizon_sessions', 'primary_probability_metric', 'log_loss_zero_policy']),
    `${path}.fixed_definitions`
  )
  const classesList = requireList(defs.classes, `${path}.fixed_definitions.classes`, 3)
  for (let c = 0; c < 3; c++) {
    if (classesList[c] !== ORDERED_CLASSES[c]) {
      failValidation(`${path}.fixed_definitions.classes`, 'fixed class order changed')
    }
  }
  const horiz = requireInt(defs.horizon_sessions, `${path}.fixed_definitions.horizon_sessions`)
  if (horiz !== 20) {
    failValidation(`${path}.fixed_definitions.horizon_sessions`, 'horizon must be 20')
  }
  requireStr(defs.neutral_band, `${path}.fixed_definitions.neutral_band`)
  requireStr(defs.primary_probability_metric, `${path}.fixed_definitions.primary_probability_metric`)
  requireStr(defs.log_loss_zero_policy, `${path}.fixed_definitions.log_loss_zero_policy`)

  // Partitions
  const parts = requireObject(root.partitions, new Set(['development', 'test']), `${path}.partitions`)
  for (const pName of ['development', 'test'] as const) {
    const pPath = `${path}.partitions.${pName}`
    const pDoc = requireObject(
      parts[pName],
      new Set([
        'partition',
        'cutoff_index',
        'cutoff_date',
        'counts',
        'comparison_status',
        'comparison_unavailable_reasons',
        'method_states',
        'metrics'
      ]),
      pPath
    )
    if (pDoc.partition !== pName) {
      failValidation(`${pPath}.partition`, 'partition name mismatch')
    }
    requireInt(pDoc.cutoff_index, `${pPath}.cutoff_index`)
    requireDate(pDoc.cutoff_date, `${pPath}.cutoff_date`)

    const counts = validateCountsDocument(pDoc.counts, `${pPath}.counts`)
    const status = requireEnum(pDoc.comparison_status, [STATUS_SCORED, STATUS_EMPTY, STATUS_COMPARISON_UNAVAILABLE] as const, `${pPath}.comparison_status`)

    const unavailReasons = requireList(pDoc.comparison_unavailable_reasons, `${pPath}.comparison_unavailable_reasons`)
    for (let r = 0; r < unavailReasons.length; r++) {
      requireStr(unavailReasons[r], `${pPath}.comparison_unavailable_reasons[${r}]`)
    }
    if ((status === STATUS_COMPARISON_UNAVAILABLE) !== (unavailReasons.length > 0)) {
      failValidation(pPath, 'unavailable reasons must exist exactly when comparison is unavailable')
    }

    const methodStates = validateMethodStatesDocument(pDoc.method_states, `${pPath}.method_states`, status)

    // Method states vs counts
    for (const mName of MODEL_NAMES) {
      const expectedAvail = methodStates[mName].available ? counts.requested_count : 0
      if (counts.model_available_counts[mName] !== expectedAvail) {
        failValidation(`${pPath}.counts.model_available_counts.${mName}`, `expected ${expectedAvail} for its method state`)
      }
    }

    validateMetricsDocument(pDoc.metrics, `${pPath}.metrics`, status, counts.requested_count)
  }

  // Uncertainty
  validateUncertaintyResultDocument(root.uncertainty)

  // Cross-block relations, once every block is individually valid
  validateSummaryRelations(root as unknown as HistoricalEvaluationSummary, schemaVer, path)

  // Limitations
  const limits = requireList(root.limitations, `${path}.limitations`)
  if (limits.length === 0) {
    failValidation(`${path}.limitations`, 'limitations are required')
  }
  for (let lIdx = 0; lIdx < limits.length; lIdx++) {
    requireStr(limits[lIdx], `${path}.limitations[${lIdx}]`)
  }

  return root as unknown as HistoricalEvaluationSummary
}

// --- Precedence State Evaluator ---

function makeUiState(
  state: UiDisplayState['display_state'],
  reason: string,
  summaryDoc: HistoricalEvaluationSummary | null = null
): UiDisplayState {
  return {
    display_state: state,
    can_display_metrics: state === UI_STATE_DISPLAYABLE,
    reason,
    summary_data: state === UI_STATE_DISPLAYABLE ? summaryDoc : null
  }
}

export function evaluateUiDisplayState(
  rawSummaryBytes: Uint8Array | ArrayBuffer | null,
  descriptor: ReleaseDescriptor | null,
  computedShaOrDigestFn?: string | ((bytes: Uint8Array) => Promise<string> | string)
): Promise<UiDisplayState> | UiDisplayState {
  if (rawSummaryBytes === null || descriptor === null) {
    return makeUiState(UI_STATE_UNAVAILABLE, 'Missing release descriptor or summary artifact')
  }

  const bytes = rawSummaryBytes instanceof Uint8Array ? rawSummaryBytes : new Uint8Array(rawSummaryBytes)

  let summaryDoc: unknown
  try {
    summaryDoc = parseStrictJsonBytes(bytes)
  } catch (err: any) {
    return makeUiState(UI_STATE_ERROR, `Malformed summary JSON: ${err.message}`)
  }

  if (typeof summaryDoc !== 'object' || summaryDoc === null || Array.isArray(summaryDoc)) {
    return makeUiState(UI_STATE_ERROR, 'Summary root is not a JSON object')
  }

  const rec = summaryDoc as Record<string, unknown>
  const schemaVersion = rec.schema_version
  const protocolId = rec.protocol_id

  if (typeof schemaVersion !== 'string' || typeof protocolId !== 'string') {
    return makeUiState(UI_STATE_ERROR, 'Summary schema_version and protocol_id must be strings')
  }

  if (!SUPPORTED_SUMMARY_SCHEMA_VERSIONS.has(schemaVersion)) {
    return makeUiState(UI_STATE_UNSUPPORTED_VERSION, `Unsupported summary schema: ${schemaVersion}`)
  }
  if (!SUPPORTED_PROTOCOL_IDS.has(protocolId)) {
    return makeUiState(UI_STATE_UNSUPPORTED_VERSION, `Unsupported protocol: ${protocolId}`)
  }
  if (!SUPPORTED_SUMMARY_SCHEMA_VERSIONS.has(descriptor.summary_schema_version)) {
    return makeUiState(UI_STATE_UNSUPPORTED_VERSION, `Unsupported descriptor schema: ${descriptor.summary_schema_version}`)
  }
  if (!SUPPORTED_PROTOCOL_IDS.has(descriptor.protocol_id)) {
    return makeUiState(UI_STATE_UNSUPPORTED_VERSION, `Unsupported descriptor protocol: ${descriptor.protocol_id}`)
  }

  let typedSummary: HistoricalEvaluationSummary
  try {
    typedSummary = validateSummaryDocument(summaryDoc)
  } catch (err: any) {
    return makeUiState(UI_STATE_ERROR, `Malformed summary: ${err.message}`)
  }

  const parsedCovEnd = typedSummary.dataset_attribution.coverage_end_date
  if (
    typedSummary.run_id !== descriptor.run_id ||
    typedSummary.study_id !== descriptor.study_id ||
    typedSummary.schema_version !== descriptor.summary_schema_version ||
    parsedCovEnd !== descriptor.coverage_end_date
  ) {
    return makeUiState(
      UI_STATE_STALE,
      `Summary identity (${typedSummary.run_id}, ${typedSummary.study_id}, ${typedSummary.schema_version}, ${parsedCovEnd}) ` +
        `differs from selected descriptor (${descriptor.run_id}, ${descriptor.study_id}, ${descriptor.summary_schema_version}, ${descriptor.coverage_end_date})`
    )
  }

  if (bytes.byteLength !== descriptor.summary_bytes) {
    return makeUiState(
      UI_STATE_ERROR,
      `Byte count mismatch: expected ${descriptor.summary_bytes}, got ${bytes.byteLength}`
    )
  }

  const finishWithHash = (computedSha: string): UiDisplayState => {
    if (typeof computedSha !== 'string' || computedSha.toUpperCase() !== descriptor.summary_sha256.toUpperCase()) {
      return makeUiState(
        UI_STATE_ERROR,
        `SHA-256 digest mismatch: expected ${descriptor.summary_sha256}, got ${computedSha}`
      )
    }
    return makeUiState(
      UI_STATE_DISPLAYABLE,
      'Exact supported identity and cryptographic binding verified',
      typedSummary
    )
  }

  if (typeof computedShaOrDigestFn === 'string') {
    return finishWithHash(computedShaOrDigestFn)
  }

  if (typeof computedShaOrDigestFn === 'function') {
    try {
      const res = computedShaOrDigestFn(bytes)
      if (res instanceof Promise) {
        return res
          .then(finishWithHash)
          .catch(err => makeUiState(UI_STATE_ERROR, `Digest computation failed: ${err.message}`))
      }
      return finishWithHash(res)
    } catch (err: any) {
      return makeUiState(UI_STATE_ERROR, `Digest computation failed: ${err.message}`)
    }
  }

  // Default web crypto digest
  return defaultSha256(bytes)
    .then(finishWithHash)
    .catch(err => makeUiState(UI_STATE_ERROR, `Digest computation failed: ${err.message}`))
}

// --- Default Production Web Crypto Digest ---

export async function defaultSha256(bytes: Uint8Array): Promise<string> {
  if (
    typeof globalThis === 'undefined' ||
    !globalThis.crypto ||
    !globalThis.crypto.subtle ||
    typeof globalThis.crypto.subtle.digest !== 'function'
  ) {
    throw new Error('Web Cryptography API (crypto.subtle.digest) is not available')
  }
  const hashBuffer = await globalThis.crypto.subtle.digest('SHA-256', bytes as unknown as BufferSource)
  const hashArray = Array.from(new Uint8Array(hashBuffer))
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('').toUpperCase()
}

// --- Loader with Abort / Resource Guards ---

export interface LoadHistoricalEvaluationOptions {
  releaseUrl?: string
  summaryUrl?: string
  fetchFn?: typeof fetch
  digestFn?: (bytes: Uint8Array) => Promise<string> | string
  timeoutMs?: number
  signal?: AbortSignal
}

export const DEFAULT_RELEASE_URL = '/data/prediction-evaluation/release.json'
export const DEFAULT_SUMMARY_URL = '/data/prediction-evaluation/panel-summary.json'
export const DEFAULT_LOAD_TIMEOUT_MS = 15000

// Both artifacts are requested as JSON on the loader-owned signal. The header lets a dev server
// answer a missing file with its genuine 404; a successful non-JSON body is still an error below.
function artifactRequestInit(signal: AbortSignal): RequestInit {
  return { signal, headers: { Accept: 'application/json' } }
}

export async function loadHistoricalEvaluation(
  options: LoadHistoricalEvaluationOptions = {}
): Promise<UiDisplayState> {
  const {
    releaseUrl = DEFAULT_RELEASE_URL,
    summaryUrl = DEFAULT_SUMMARY_URL,
    fetchFn = globalThis.fetch,
    digestFn,
    timeoutMs = DEFAULT_LOAD_TIMEOUT_MS,
    signal
  } = options

  if (typeof fetchFn !== 'function') {
    return makeUiState(UI_STATE_ERROR, 'Fetch API is unavailable in current runtime')
  }

  const abortCtrl = new AbortController()
  const timeoutId = setTimeout(() => abortCtrl.abort(), timeoutMs)

  if (signal) {
    signal.addEventListener('abort', () => abortCtrl.abort(), { once: true })
  }

  try {
    // 1. Fetch release descriptor
    let releaseRes: Response
    try {
      releaseRes = await fetchFn(releaseUrl, artifactRequestInit(abortCtrl.signal))
    } catch (err: any) {
      if (err.name === 'AbortError') {
        return makeUiState(UI_STATE_ERROR, `Fetch aborted: ${err.message}`)
      }
      return makeUiState(UI_STATE_ERROR, `Network error loading release descriptor: ${err.message}`)
    }

    if (releaseRes.status === 404) {
      return makeUiState(UI_STATE_UNAVAILABLE, 'Release descriptor not found (404)')
    }
    if (!releaseRes.ok) {
      return makeUiState(UI_STATE_ERROR, `HTTP ${releaseRes.status} loading release descriptor`)
    }

    const releaseBytes = await releaseRes.arrayBuffer()
    let descriptor: ReleaseDescriptor
    try {
      descriptor = parseReleaseDescriptor(releaseBytes)
    } catch (err: any) {
      return makeUiState(UI_STATE_ERROR, `Malformed release descriptor: ${err.message}`)
    }

    // 2. Fetch summary document
    let summaryRes: Response
    try {
      summaryRes = await fetchFn(summaryUrl, artifactRequestInit(abortCtrl.signal))
    } catch (err: any) {
      if (err.name === 'AbortError') {
        return makeUiState(UI_STATE_ERROR, `Fetch aborted: ${err.message}`)
      }
      return makeUiState(UI_STATE_ERROR, `Network error loading summary artifact: ${err.message}`)
    }

    if (summaryRes.status === 404) {
      return makeUiState(UI_STATE_UNAVAILABLE, 'Summary artifact not found (404)')
    }
    if (!summaryRes.ok) {
      return makeUiState(UI_STATE_ERROR, `HTTP ${summaryRes.status} loading summary artifact`)
    }

    const summaryBytes = await summaryRes.arrayBuffer()

    return await evaluateUiDisplayState(summaryBytes, descriptor, digestFn)
  } catch (err: any) {
    return makeUiState(UI_STATE_ERROR, `Unexpected error evaluating display state: ${err.message}`)
  } finally {
    clearTimeout(timeoutId)
  }
}
