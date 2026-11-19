'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const WORKSPACE_ROOT = path.resolve(__dirname, '..', '..');

const REQUIRED_MODELS_PATH = 'public/data/market_intelligence/models.json';
const EXPECTED_MODELS_SHA256 = '87C4DB2A4EB3B40AE5F7499C977AB407FFE3C3BE367E4DAE8FD8AE1804F543CD';
const EXPECTED_20D_PLATT = [1.42, 0.02];

const VALID_REGIMES = new Set([
  'Bull',
  'Bear',
  'Correction',
  'Recovery',
  'Sideways',
  'High-volatility'
]);

const ALLOWED_ROOT_KEYS = new Set([
  'schema_version',
  'feature_protocol',
  'series_id',
  'asset',
  'horizon',
  'variant',
  'axis_start_date',
  'calendar_status',
  'missing_sessions',
  'extra_sessions',
  'nifty_provenance',
  'vix_provenance',
  'rows'
]);

const ALLOWED_ROW_KEYS = new Set([
  'origin_index',
  'origin_date',
  'origin_close',
  'vix_close',
  'feature_ready',
  'unready_reasons',
  'payload'
]);

const ALLOWED_PAYLOAD_KEYS = new Set([
  'ret_5d',
  'rsi_14',
  'macd_hist',
  'vol_30d',
  'rel_strength_20d',
  'drawdown',
  'market_regime'
]);

const ALLOWED_PROVENANCE_KEYS = new Set([
  'file_path',
  'raw_byte_count',
  'sha256',
  'record_count',
  'observed_first_date',
  'observed_last_date',
  'source_url',
  'requested_interval',
  'acquisition_time',
  'source_use_note'
]);

function sha256Buffer(buf) {
  return crypto.createHash('sha256').update(buf).digest('hex').toUpperCase();
}

function assertExactKeys(obj, allowedSet, objectLabel) {
  const actualKeys = Object.keys(obj);
  for (const k of actualKeys) {
    if (!allowedSet.has(k)) {
      throw new Error(`Unknown unexpected field "${k}" in ${objectLabel}`);
    }
  }
  for (const k of allowedSet) {
    if (!(k in obj)) {
      throw new Error(`Missing required field "${k}" in ${objectLabel}`);
    }
  }
}

function isValidGregorianDate(dateStr) {
  if (typeof dateStr !== 'string') return false;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) return false;
  const [y, m, d] = dateStr.split('-').map(Number);
  if (y < 1 || y > 9999 || m < 1 || m > 12 || d < 1 || d > 31) return false;
  const dt = new Date(Date.UTC(0, 0, 1));
  dt.setUTCFullYear(y, m - 1, d);
  return (
    dt.getUTCFullYear() === y &&
    dt.getUTCMonth() === m - 1 &&
    dt.getUTCDate() === d
  );
}

function isPlainPositiveDecimal(str) {
  if (typeof str !== 'string') return false;
  if (!/^\d+(\.\d+)?$/.test(str)) return false;
  // Reject all-zero strings
  const parts = str.split('.');
  const allZeros = parts.every(p => /^0+$/.test(p));
  return !allZeros;
}

function validateFileProvenance(p, label) {
  if (!p || typeof p !== 'object' || Array.isArray(p)) {
    throw new Error(`${label}: expected object`);
  }
  assertExactKeys(p, ALLOWED_PROVENANCE_KEYS, label);

  if (typeof p.file_path !== 'string') throw new Error(`${label}.file_path must be string`);
  if (!Number.isSafeInteger(p.raw_byte_count) || p.raw_byte_count < 0) {
    throw new Error(`${label}.raw_byte_count must be non-negative integer`);
  }
  if (typeof p.sha256 !== 'string' || !/^[0-9A-Fa-f]{64}$/.test(p.sha256)) {
    throw new Error(`${label}.sha256 must be 64-hex string`);
  }
  if (!Number.isSafeInteger(p.record_count) || p.record_count < 0) {
    throw new Error(`${label}.record_count must be non-negative integer`);
  }

  if (p.record_count === 0) {
    if (p.observed_first_date !== null || p.observed_last_date !== null) {
      throw new Error(`${label}: observed dates must be null when record_count is 0`);
    }
  } else {
    if (!isValidGregorianDate(p.observed_first_date) || !isValidGregorianDate(p.observed_last_date)) {
      throw new Error(`${label}: observed dates must be valid Gregorian dates when record_count > 0`);
    }
    if (p.observed_first_date > p.observed_last_date) {
      throw new Error(`${label}: observed_first_date must be <= observed_last_date`);
    }
  }

  if (p.source_url !== null && typeof p.source_url !== 'string') {
    throw new Error(`${label}.source_url must be string or null`);
  }
  if (p.source_use_note !== null && typeof p.source_use_note !== 'string') {
    throw new Error(`${label}.source_use_note must be string or null`);
  }
  if (p.requested_interval !== null) {
    if (!Array.isArray(p.requested_interval) || p.requested_interval.length !== 2) {
      throw new Error(`${label}.requested_interval must be null or 2-date array`);
    }
    if (!isValidGregorianDate(p.requested_interval[0]) || !isValidGregorianDate(p.requested_interval[1])) {
      throw new Error(`${label}.requested_interval entries must be valid Gregorian dates`);
    }
    if (p.requested_interval[0] > p.requested_interval[1]) {
      throw new Error(`${label}.requested_interval start date "${p.requested_interval[0]}" must be <= end date "${p.requested_interval[1]}"`);
    }
  }

  if (p.acquisition_time !== null) {
    if (typeof p.acquisition_time !== 'string') {
      throw new Error(`${label}.acquisition_time must be string or null`);
    }
    const isoRe = /^(\d{4}-\d{2}-\d{2})T(0[0-9]|1[0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](\.\d{1,6})?(Z|[+-](0[0-9]|1[0-9]|2[0-3]):[0-5][0-9])?$/;
    const match = isoRe.exec(p.acquisition_time);
    if (!match) {
      throw new Error(`${label}.acquisition_time must match acquisition timestamp grammar`);
    }
    const datePart = match[1];
    if (!isValidGregorianDate(datePart)) {
      throw new Error(`${label}.acquisition_time date prefix "${datePart}" is not a valid Gregorian date`);
    }
  }
}

function validateDateArray(arr, label) {
  if (!Array.isArray(arr)) {
    throw new Error(`${label} must be an array`);
  }
  let prev = null;
  for (let i = 0; i < arr.length; i++) {
    const d = arr[i];
    if (!isValidGregorianDate(d)) {
      throw new Error(`${label}[${i}] "${d}" is not a valid Gregorian date`);
    }
    if (prev !== null && d <= prev) {
      throw new Error(`${label} must be strictly sorted without duplicates; found "${d}" after "${prev}"`);
    }
    prev = d;
  }
}

function checkFiniteRecursively(obj, pathPrefix = 'root') {
  if (typeof obj === 'number') {
    if (!Number.isFinite(obj)) {
      throw new Error(`Nonfinite numeric encountered at ${pathPrefix}: ${obj}`);
    }
  } else if (Array.isArray(obj)) {
    for (let i = 0; i < obj.length; i++) {
      checkFiniteRecursively(obj[i], `${pathPrefix}[${i}]`);
    }
  } else if (obj !== null && typeof obj === 'object') {
    for (const [k, v] of Object.entries(obj)) {
      checkFiniteRecursively(v, `${pathPrefix}.${k}`);
    }
  }
}

function validateModelsContent(modelBuf, expectedHash = EXPECTED_MODELS_SHA256) {
  const modelSha256 = sha256Buffer(modelBuf);
  if (expectedHash !== null && modelSha256 !== expectedHash) {
    throw new Error(`Model file hash mismatch. Expected ${expectedHash}, got ${modelSha256}`);
  }

  const modelsJson = JSON.parse(modelBuf.toString('utf8'));
  const model20D = modelsJson['20D'];
  if (!model20D || !Array.isArray(model20D.platt_params) || model20D.platt_params.length !== 2) {
    throw new Error('Model 20D entry or platt_params missing');
  }
  if (model20D.platt_params[0] !== EXPECTED_20D_PLATT[0] || model20D.platt_params[1] !== EXPECTED_20D_PLATT[1]) {
    throw new Error(`20D Platt params mismatch. Expected ${EXPECTED_20D_PLATT}, got ${model20D.platt_params}`);
  }
  return { modelSha256, model20D };
}

function runReplay(inputFilePath) {
  if (!fs.existsSync(inputFilePath)) {
    throw new Error(`Input file not found: ${inputFilePath}`);
  }

  const rawBuffer = fs.readFileSync(inputFilePath);
  if (rawBuffer.length === 0) {
    throw new Error('Input file is physically empty (0 bytes)');
  }

  const requestSha256 = sha256Buffer(rawBuffer);
  const requestByteCount = rawBuffer.length;

  let text;
  try {
    const decoder = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true });
    text = decoder.decode(rawBuffer);
  } catch (err) {
    throw new Error(`Invalid UTF-8 encoding in input file: ${err.message}`);
  }
  // Ignore single leading UTF-8 BOM for parsing only; reject repeated BOMs
  if (text.charCodeAt(0) === 0xFEFF) {
    text = text.slice(1);
    if (text.charCodeAt(0) === 0xFEFF) {
      throw new Error('Input file contains repeated leading UTF-8 BOM');
    }
  }

  let doc;
  try {
    doc = JSON.parse(text);
  } catch (err) {
    throw new Error(`Malformed JSON in input file: ${err.message}`);
  }

  if (!doc || typeof doc !== 'object' || Array.isArray(doc)) {
    throw new Error('Input root must be a JSON object');
  }

  // Schema key strictness: reject unknown / missing top-level keys
  assertExactKeys(doc, ALLOWED_ROOT_KEYS, 'input root document');

  // Schema validation
  if (doc.schema_version !== 'nivesh-replay-input-v1') {
    throw new Error(`Invalid schema_version: "${doc.schema_version}". Expected "nivesh-replay-input-v1"`);
  }
  if (doc.feature_protocol !== 'nifty-close-features-v1') {
    throw new Error(`Invalid feature_protocol: "${doc.feature_protocol}". Expected "nifty-close-features-v1"`);
  }
  if (doc.series_id !== '^NSEI') {
    throw new Error(`Invalid series_id: "${doc.series_id}". Expected "^NSEI"`);
  }
  if (doc.asset !== '^NSEI') {
    throw new Error(`Invalid asset: "${doc.asset}". Expected "^NSEI"`);
  }
  if (doc.horizon !== '20D') {
    throw new Error(`Invalid horizon: "${doc.horizon}". Expected "20D"`);
  }
  if (doc.variant !== 'frozen-current-core-market-data-only-v1') {
    throw new Error(`Invalid variant: "${doc.variant}". Expected "frozen-current-core-market-data-only-v1"`);
  }

  if (!Array.isArray(doc.rows)) {
    throw new Error('Property "rows" must be an array');
  }

  if (doc.rows.length === 0) {
    if (doc.axis_start_date !== null) {
      throw new Error('axis_start_date must be null when rows array is empty');
    }
  } else {
    if (!isValidGregorianDate(doc.axis_start_date)) {
      throw new Error(`Invalid Gregorian axis_start_date: ${doc.axis_start_date}`);
    }
    if (doc.axis_start_date !== doc.rows[0].origin_date) {
      throw new Error(`axis_start_date "${doc.axis_start_date}" does not match first row date "${doc.rows[0].origin_date}"`);
    }
  }

  if (!['not_checked', 'matches_supplied_sessions', 'mismatch'].includes(doc.calendar_status)) {
    throw new Error(`Invalid calendar_status: ${doc.calendar_status}`);
  }

  // Calendar metadata invariants
  validateDateArray(doc.missing_sessions, 'missing_sessions');
  validateDateArray(doc.extra_sessions, 'extra_sessions');

  const missingSet = new Set(doc.missing_sessions);
  const extraSet = new Set(doc.extra_sessions);

  // Check disjointness
  for (const d of doc.missing_sessions) {
    if (extraSet.has(d)) {
      throw new Error(`Date "${d}" appears in both missing_sessions and extra_sessions`);
    }
  }

  if (doc.calendar_status !== 'mismatch') {
    if (doc.missing_sessions.length > 0 || doc.extra_sessions.length > 0) {
      throw new Error(`missing_sessions and extra_sessions must be empty unless calendar_status is "mismatch"`);
    }
  } else {
    if (doc.missing_sessions.length === 0 && doc.extra_sessions.length === 0) {
      throw new Error(`calendar_status is "mismatch" but missing_sessions and extra_sessions are both empty`);
    }
  }

  // Provenance checks
  if (!Array.isArray(doc.nifty_provenance) || !Array.isArray(doc.vix_provenance)) {
    throw new Error('nifty_provenance and vix_provenance must be arrays');
  }
  doc.nifty_provenance.forEach((p, idx) => validateFileProvenance(p, `nifty_provenance[${idx}]`));
  doc.vix_provenance.forEach((p, idx) => validateFileProvenance(p, `vix_provenance[${idx}]`));

  // Validate rows
  let prevDate = null;
  const indicesSeen = new Set();
  const axisDatesSet = new Set();

  for (let i = 0; i < doc.rows.length; i++) {
    const row = doc.rows[i];
    if (!row || typeof row !== 'object' || Array.isArray(row)) {
      throw new Error(`Row ${i} is not an object`);
    }

    assertExactKeys(row, ALLOWED_ROW_KEYS, `row[${i}]`);

    if (row.origin_index !== i) {
      throw new Error(`Row ${i} origin_index mismatch: expected ${i}, got ${row.origin_index}`);
    }
    if (indicesSeen.has(row.origin_index)) {
      throw new Error(`Duplicate origin_index: ${row.origin_index}`);
    }
    indicesSeen.add(row.origin_index);

    if (!isValidGregorianDate(row.origin_date)) {
      throw new Error(`Row ${i} origin_date "${row.origin_date}" is not a valid Gregorian date`);
    }
    if (axisDatesSet.has(row.origin_date)) {
      throw new Error(`Duplicate origin_date: ${row.origin_date}`);
    }
    axisDatesSet.add(row.origin_date);

    if (prevDate !== null && row.origin_date <= prevDate) {
      throw new Error(`Row ${i} date ${row.origin_date} not strictly increasing after ${prevDate}`);
    }
    prevDate = row.origin_date;

    if (!isPlainPositiveDecimal(row.origin_close)) {
      throw new Error(`Row ${i} (${row.origin_date}) origin_close "${row.origin_close}" must be a positive decimal string`);
    }

    if (row.vix_close !== null && !isPlainPositiveDecimal(row.vix_close)) {
      throw new Error(`Row ${i} (${row.origin_date}) vix_close "${row.vix_close}" must be a positive decimal string or null`);
    }

    if (typeof row.feature_ready !== 'boolean') {
      throw new Error(`Row ${i} feature_ready must be boolean`);
    }
    if (!Array.isArray(row.unready_reasons)) {
      throw new Error(`Row ${i} unready_reasons must be an array`);
    }

    // Readiness and unready reasons
    const expectedReasons = [];
    if (i < 200) expectedReasons.push('warmup');
    if (row.vix_close === null) expectedReasons.push('missing_vix');

    if (expectedReasons.length > 0) {
      if (row.feature_ready !== false) {
        throw new Error(`Row ${i} (${row.origin_date}) has unready conditions (${expectedReasons.join(',')}) but feature_ready is true`);
      }
      if (row.payload !== null) {
        throw new Error(`Row ${i} (${row.origin_date}) is unready but payload is not null`);
      }
      if (row.unready_reasons.length !== expectedReasons.length ||
          !expectedReasons.every((r, idx) => row.unready_reasons[idx] === r)) {
        throw new Error(`Row ${i} (${row.origin_date}) unready_reasons mismatch. Expected [${expectedReasons.join(',')}], got [${row.unready_reasons.join(',')}]`);
      }
    } else {
      if (row.feature_ready !== true) {
        throw new Error(`Row ${i} (${row.origin_date}) has no unready conditions but feature_ready is false`);
      }
      if (row.unready_reasons.length !== 0) {
        throw new Error(`Row ${i} (${row.origin_date}) is feature_ready but unready_reasons is not empty`);
      }
      if (!row.payload || typeof row.payload !== 'object' || Array.isArray(row.payload)) {
        throw new Error(`Row ${i} (${row.origin_date}) is ready but payload is missing or invalid`);
      }

      assertExactKeys(row.payload, ALLOWED_PAYLOAD_KEYS, `row[${i}].payload`);

      const p = row.payload;
      const numFields = ['ret_5d', 'rsi_14', 'macd_hist', 'vol_30d', 'rel_strength_20d', 'drawdown'];
      for (const f of numFields) {
        if (typeof p[f] !== 'number' || !Number.isFinite(p[f])) {
          throw new Error(`Row ${i} (${row.origin_date}) payload.${f} must be a finite number, got ${p[f]}`);
        }
      }
      if (!VALID_REGIMES.has(p.market_regime)) {
        throw new Error(`Row ${i} (${row.origin_date}) payload.market_regime "${p.market_regime}" is invalid`);
      }
    }
  }

  // Cross-check calendar dates with axis dates
  if (doc.calendar_status === 'mismatch') {
    for (const extraDate of doc.extra_sessions) {
      if (!axisDatesSet.has(extraDate)) {
        throw new Error(`Extra session date "${extraDate}" does not exist on the supplied axis`);
      }
    }
    for (const missingDate of doc.missing_sessions) {
      if (axisDatesSet.has(missingDate)) {
        throw new Error(`Missing session date "${missingDate}" illegally exists on the supplied axis`);
      }
    }
  }

  // Model validation
  const modelsFullPath = path.join(WORKSPACE_ROOT, REQUIRED_MODELS_PATH);
  if (!fs.existsSync(modelsFullPath)) {
    throw new Error(`Model file missing at ${REQUIRED_MODELS_PATH}`);
  }
  const modelStat = fs.statSync(modelsFullPath);
  const modelBuf = fs.readFileSync(modelsFullPath);
  const { modelSha256, model20D } = validateModelsContent(modelBuf);

  // Build manifest validation
  const candidateManifestPath = path.join(WORKSPACE_ROOT, 'build', 'prediction-eval', 'candidate', 'build-manifest.json');
  if (!fs.existsSync(candidateManifestPath)) {
    throw new Error(`Candidate build manifest not found at ${candidateManifestPath}. Run compilation first.`);
  }

  const { validateBuildManifest } = require('./compile_replay.cjs');
  const buildManifest = JSON.parse(fs.readFileSync(candidateManifestPath, 'utf8'));
  validateBuildManifest(buildManifest, 'candidate', WORKSPACE_ROOT);

  // Load candidate core
  const coreModulePath = path.join(WORKSPACE_ROOT, 'build', 'prediction-eval', 'candidate', 'src', 'engine', 'marketIntelligence', 'forecastCore.js');
  if (!fs.existsSync(coreModulePath)) {
    throw new Error(`Candidate core module missing at ${coreModulePath}`);
  }
  const { computeDirectionalForecastCore } = require(coreModulePath);

  // Compute forecasts for all rows
  const forecasts = [];
  for (let i = 0; i < doc.rows.length; i++) {
    const row = doc.rows[i];
    let fc = null;
    if (row.feature_ready) {
      fc = computeDirectionalForecastCore(row.payload, '20D', [], model20D.platt_params);

      // Verify probability conservation on each forecast
      const pSum = +(fc.probability_bullish + fc.probability_neutral + fc.probability_bearish).toFixed(6);
      if (Math.abs(pSum - 1.0) > 1e-12) {
        throw new Error(`Probability conservation violated at row ${i} (${row.origin_date}): sum is ${pSum}`);
      }
      if (fc.probability_bullish < 0 || fc.probability_bullish > 1 ||
          fc.probability_neutral < 0 || fc.probability_neutral > 1 ||
          fc.probability_bearish < 0 || fc.probability_bearish > 1) {
        throw new Error(`Probability bounds violated at row ${i} (${row.origin_date})`);
      }
    }
    forecasts.push({
      origin_index: row.origin_index,
      origin_date: row.origin_date,
      forecast: fc
    });
  }

  const outputDoc = {
    schema_version: 'nivesh-replay-output-v1',
    claim_label: 'Retrospective replay of the frozen current heuristic; market data only; not historically issued forecasts',
    computed_provenance: {
      request: {
        raw_byte_count: requestByteCount,
        sha256: requestSha256
      },
      model: {
        path: REQUIRED_MODELS_PATH,
        raw_byte_count: modelStat.size,
        sha256: modelSha256,
        platt_params: model20D.platt_params
      },
      build: buildManifest
    },
    declared_input: doc,
    forecasts
  };

  // Final recursive check for nonfinite numerics
  checkFiniteRecursively(outputDoc);

  // Emit JSON + newline to stdout
  process.stdout.write(JSON.stringify(outputDoc, null, 2) + '\n');
}

if (require.main === module) {
  const args = process.argv.slice(2);
  if (args.length !== 1) {
    process.stderr.write('Usage: node replay.cjs <input_file>\n');
    process.exit(1);
  }

  try {
    runReplay(path.resolve(args[0]));
    process.exit(0);
  } catch (err) {
    process.stderr.write(`Replay error: ${err.message}\n`);
    process.exit(1);
  }
}

module.exports = {
  runReplay,
  validateModelsContent
};
