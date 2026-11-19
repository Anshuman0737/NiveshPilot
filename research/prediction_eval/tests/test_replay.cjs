'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const child_process = require('child_process');
const assert = require('node:assert');
const test = require('node:test');

const WORKSPACE_ROOT = path.resolve(__dirname, '..', '..', '..');
const CASES_PATH = path.join(__dirname, 'fixtures', 'replay-cases.json');
const GOLDEN_PATH = path.join(__dirname, 'fixtures', 'forecast-baseline.json');
// Fresh per-process run directory: repeated suite runs never reuse or overwrite
// earlier synthetic requests or child records.
const TEST_WORK_ROOT = path.join(WORKSPACE_ROOT, 'build', 'prediction-eval', 'test-work', 'final-writing-stabilization-1');
const TEST_RUN_ID = `run-${Date.now().toString(36)}-${process.pid}-${crypto.randomBytes(4).toString('hex')}`;
const TEST_WORK_DIR = path.join(TEST_WORK_ROOT, TEST_RUN_ID);
const CHILD_LOG_DIR = path.join(TEST_WORK_DIR, 'child-logs');

const MODEL_RETRY_CASE_IDS = ['model-http-retry', 'model-fetch-throw-retry', 'model-json-reject-retry'];
const HISTORY_RETRY_CASE_IDS = ['history-http-retry', 'history-fetch-throw-retry', 'history-json-reject-retry'];

const LIFECYCLE_CASE_IDS = [
  'cache-success',
  'model-http-retry',
  'model-fetch-throw-retry',
  'model-json-reject-retry',
  'history-http-retry',
  'history-fetch-throw-retry',
  'history-json-reject-retry',
  'empty-history-cached',
  'unexpected-url'
];

function sha256Buffer(buf) {
  return crypto.createHash('sha256').update(buf).digest('hex').toUpperCase();
}

function sha256File(filePath) {
  return sha256Buffer(fs.readFileSync(filePath));
}

// Creates a test-owned scratch directory through the compiler's workspace/link guard,
// checked before and after creation; failures propagate to the calling test.
function ensureOwnedScratchDir(dir) {
  const { verifyPathWithinWorkspace } = require('../compile_replay.cjs');
  verifyPathWithinWorkspace(dir);
  fs.mkdirSync(dir, { recursive: true });
  verifyPathWithinWorkspace(dir);
}

let childRecordSeq = 0;

function spawnAndRecordChild(label, exe, argv, options = {}) {
  ensureOwnedScratchDir(CHILD_LOG_DIR);
  const startUtc = new Date().toISOString();
  const child = child_process.spawnSync(exe, argv, {
    cwd: WORKSPACE_ROOT,
    stdio: ['ignore', 'pipe', 'pipe'],
    encoding: 'utf8',
    ...options
  });
  const endUtc = new Date().toISOString();

  // Sequence prefix keeps repeated labels in one run from replacing each other
  childRecordSeq += 1;
  const safeLabel = `${String(childRecordSeq).padStart(3, '0')}-${label.replace(/[^a-zA-Z0-9_-]/g, '_')}`;
  const stdoutBuf = Buffer.from(child.stdout || '', 'utf8');
  const stderrBuf = Buffer.from(child.stderr || '', 'utf8');
  const stdoutPath = path.join(CHILD_LOG_DIR, `${safeLabel}.stdout.log`);
  const stderrPath = path.join(CHILD_LOG_DIR, `${safeLabel}.stderr.log`);
  const recordPath = path.join(CHILD_LOG_DIR, `${safeLabel}.json`);

  let parsedResponse = null;
  let fetchTrace = null;
  if (child.stdout && child.stdout.trim().length > 0) {
    try {
      parsedResponse = JSON.parse(child.stdout.trim());
      if (parsedResponse) {
        if (Array.isArray(parsedResponse.fetch_trace)) {
          fetchTrace = parsedResponse.fetch_trace;
        } else if (parsedResponse.candidate && Array.isArray(parsedResponse.candidate.fetchTrace)) {
          fetchTrace = parsedResponse.candidate.fetchTrace;
        }
      }
    } catch {}
  }

  // Required evidence: exclusive-create writes, and any recording failure fails the caller
  fs.writeFileSync(stdoutPath, stdoutBuf, { flag: 'wx' });
  fs.writeFileSync(stderrPath, stderrBuf, { flag: 'wx' });

  const record = {
    label,
    scenario_identity: options.scenarioIdentity || options.caseId || null,
    start_utc: startUtc,
    end_utc: endUtc,
    exe,
    argv,
    cwd: options.cwd || WORKSPACE_ROOT,
    immediate_status: child.status,
    immediate_native_exit: child.status,
    signal: child.signal,
    error: child.error ? child.error.message : null,
    stdout_path: stdoutPath,
    stdout_bytes: stdoutBuf.length,
    stdout_sha256: sha256Buffer(stdoutBuf),
    stderr_path: stderrPath,
    stderr_bytes: stderrBuf.length,
    stderr_sha256: sha256Buffer(stderrBuf),
    parsed_response: parsedResponse,
    fetch_trace: fetchTrace
  };
  fs.writeFileSync(recordPath, JSON.stringify(record, null, 2) + '\n', { encoding: 'utf8', flag: 'wx' });

  return child;
}

function runReplayCli(label, reqPath, extraOptions = {}) {
  const replayCli = path.join(WORKSPACE_ROOT, 'research', 'prediction_eval', 'replay.cjs');
  return spawnAndRecordChild('cli-' + label, process.execPath, [replayCli, reqPath], {
    cwd: WORKSPACE_ROOT,
    ...extraOptions
  });
}

// ---------------------------------------------------------------------------
// Worker entrypoint: isolated scenario execution with mock fetch
// ---------------------------------------------------------------------------
async function runAdapterWorker(mode, scenarioId) {
  const casesData = JSON.parse(fs.readFileSync(CASES_PATH, 'utf8'));
  const scenario = casesData.scenarios.find(s => s.id === scenarioId);
  if (!scenario) {
    throw new Error(`Scenario "${scenarioId}" not found in ${CASES_PATH}`);
  }

  const fetchTrace = [];
  let modelFailuresRemaining = scenario.model_failures || 0;
  let historyFailuresRemaining = scenario.history_failures || 0;

  // Mock global.fetch isolated to this process
  global.fetch = async (url) => {
    const urlStr = String(url);
    fetchTrace.push(urlStr);

    if (urlStr === '/data/market_intelligence/models.json') {
      if (modelFailuresRemaining > 0) {
        modelFailuresRemaining--;
        return {
          ok: false,
          status: 500,
          json: async () => { throw new Error('Simulated HTTP 500 on models.json'); }
        };
      }
      return {
        ok: true,
        status: 200,
        json: async () => JSON.parse(JSON.stringify(scenario.models_fixture))
      };
    }

    if (urlStr === '/data/market_intelligence/historical_prices.json') {
      if (historyFailuresRemaining > 0) {
        historyFailuresRemaining--;
        return {
          ok: false,
          status: 500,
          json: async () => { throw new Error('Simulated HTTP 500 on historical_prices.json'); }
        };
      }
      return {
        ok: true,
        status: 200,
        json: async () => JSON.parse(JSON.stringify(scenario.prices_fixture))
      };
    }

    throw new Error(`Unexpected unauthorized fetch to URL: "${urlStr}"`);
  };

  const adapterPath = path.join(WORKSPACE_ROOT, 'build', 'prediction-eval', mode, 'src', 'engine', 'marketIntelligence', 'forecastEngine.js');
  if (!fs.existsSync(adapterPath)) {
    throw new Error(`Compiled adapter not found at ${adapterPath}`);
  }

  const engine = require(adapterPath);
  const repeatCount = scenario.repeat_calls || 1;
  let lastForecast = null;

  for (let i = 0; i < repeatCount; i++) {
    lastForecast = await engine.computeDirectionalForecast(scenario.asset, scenario.horizon, scenario.events || []);
  }

  return {
    id: scenarioId,
    forecast: lastForecast,
    fetch_trace: fetchTrace
  };
}

// ---------------------------------------------------------------------------
// Supplemental Lifecycle Worker
// ---------------------------------------------------------------------------
async function runLifecycleWorker(mode, caseId, expectedBaselineHash) {
  if (mode !== 'baseline' && mode !== 'candidate') {
    throw new Error(`Invalid lifecycle mode: "${mode}"`);
  }
  if (!LIFECYCLE_CASE_IDS.includes(caseId)) {
    throw new Error(`Unknown lifecycle case ID: "${caseId}"`);
  }

  if (mode === 'baseline') {
    const EXPECTED_HASH = '04360BA971E965BAF67F55229CB1621991856C9F069E4A5034167B5FCAB4E7C9';
    if (expectedBaselineHash !== EXPECTED_HASH) {
      throw new Error(`Baseline manifest hash mismatch in worker: expected ${EXPECTED_HASH}, got ${expectedBaselineHash}`);
    }
    const manifestPath = path.join(WORKSPACE_ROOT, 'build', 'prediction-eval', 'baseline', 'build-manifest.json');
    if (!fs.existsSync(manifestPath)) {
      throw new Error(`Baseline build manifest missing at ${manifestPath}`);
    }
    const actualHash = sha256File(manifestPath);
    if (actualHash !== EXPECTED_HASH) {
      throw new Error(`Baseline build manifest hash on disk mismatch: ${actualHash}`);
    }
  }

  const standardAsset = {
    symbol: '^NSEI',
    name: 'NIFTY 50',
    type: 'index',
    tradingHours: '09:15 - 15:30 IST'
  };
  const standardHorizon = '20D';
  const standardEvents = [];

  const validModelsFixture = {
    '20D': {
      horizon: '20D',
      trading_days: 20,
      weights: { technical: 0.35, momentum: 0.25, volatility: 0.2, regime: 0.2 },
      platt_params: [1.42, 0.02],
      latest_forecasts: {}
    }
  };

  const validPricesFixture = {
    '^NSEI': [
      {
        date: '2026-01-01',
        open: 24000, high: 24100, low: 23900, close: 24050, volume: 100000,
        ret_5d: 0.01, rsi_14: 55, macd_hist: 0.2, vol_30d: 0.14, rel_strength_20d: 0.01, drawdown: -0.01,
        market_regime: 'Bull'
      }
    ]
  };

  const fetchTrace = [];
  let unexpectedUrlCount = 0;
  let callFetches = [];

  let modelFailCount = 0;
  let historyFailCount = 0;

  if (MODEL_RETRY_CASE_IDS.includes(caseId)) {
    modelFailCount = 1;
  }
  if (HISTORY_RETRY_CASE_IDS.includes(caseId)) {
    historyFailCount = 1;
  }

  global.fetch = async (url) => {
    const urlStr = String(url);
    fetchTrace.push(urlStr);
    callFetches.push(urlStr);

    if (urlStr === '/data/market_intelligence/models.json') {
      if (modelFailCount > 0) {
        modelFailCount--;
        if (caseId === 'model-http-retry') {
          return {
            ok: false,
            status: 500,
            json: async () => { throw new Error('HTTP 500'); }
          };
        } else if (caseId === 'model-fetch-throw-retry') {
          throw new TypeError('Failed to fetch models: network offline');
        } else if (caseId === 'model-json-reject-retry') {
          return {
            ok: true,
            status: 200,
            json: async () => { throw new SyntaxError('Unexpected token < in JSON at position 0'); }
          };
        }
      }
      return {
        ok: true,
        status: 200,
        json: async () => JSON.parse(JSON.stringify(validModelsFixture))
      };
    }

    if (urlStr === '/data/market_intelligence/historical_prices.json') {
      if (historyFailCount > 0) {
        historyFailCount--;
        if (caseId === 'history-http-retry') {
          return {
            ok: false,
            status: 500,
            json: async () => { throw new Error('HTTP 500'); }
          };
        } else if (caseId === 'history-fetch-throw-retry') {
          throw new TypeError('Failed to fetch history: network offline');
        } else if (caseId === 'history-json-reject-retry') {
          return {
            ok: true,
            status: 200,
            json: async () => { throw new SyntaxError('Unexpected token < in JSON at position 0'); }
          };
        }
      }

      if (caseId === 'empty-history-cached') {
        return {
          ok: true,
          status: 200,
          json: async () => ({ '^NSEI': [] })
        };
      }

      return {
        ok: true,
        status: 200,
        json: async () => JSON.parse(JSON.stringify(validPricesFixture))
      };
    }

    unexpectedUrlCount++;
    throw new Error(`Unexpected unauthorized fetch to URL: "${urlStr}"`);
  };

  const adapterPath = path.join(WORKSPACE_ROOT, 'build', 'prediction-eval', mode, 'src', 'engine', 'marketIntelligence', 'forecastEngine.js');
  if (!fs.existsSync(adapterPath)) {
    throw new Error(`Compiled adapter not found at ${adapterPath}`);
  }

  const engine = require(adapterPath);
  const calls = [];

  const repeatCount = 2;
  for (let i = 0; i < repeatCount; i++) {
    callFetches = [];
    const fc = await engine.computeDirectionalForecast(standardAsset, standardHorizon, standardEvents);
    calls.push({
      call_index: i,
      forecast: fc,
      fetch_calls: [...callFetches]
    });
  }

  if (caseId === 'unexpected-url') {
    // Intentional unauthorized synthetic probe MUST cause child nonzero with empty success stdout and specific diagnostic
    await global.fetch('/unauthorized_endpoint');
  }

  return {
    case_id: caseId,
    mode: mode,
    calls: calls,
    fetch_trace: fetchTrace,
    unexpected_url_attempts: unexpectedUrlCount
  };
}

// ---------------------------------------------------------------------------
// Supplemental Lifecycle Controller
// ---------------------------------------------------------------------------
async function verifyLifecycle(expectedBaselineHash) {
  const EXPECTED_HASH = '04360BA971E965BAF67F55229CB1621991856C9F069E4A5034167B5FCAB4E7C9';
  if (expectedBaselineHash !== EXPECTED_HASH) {
    throw new Error(`verifyLifecycle expected baseline manifest hash mismatch: expected ${EXPECTED_HASH}, got ${expectedBaselineHash}`);
  }

  const { validateBuildManifest } = require('../compile_replay.cjs');

  const baselineManifestPath = path.join(WORKSPACE_ROOT, 'build', 'prediction-eval', 'baseline', 'build-manifest.json');
  if (!fs.existsSync(baselineManifestPath)) {
    throw new Error(`Baseline build manifest missing at ${baselineManifestPath}`);
  }
  const actualBaselineHash = sha256File(baselineManifestPath);
  if (actualBaselineHash !== EXPECTED_HASH) {
    throw new Error(`Baseline manifest hash mismatch on disk: expected ${EXPECTED_HASH}, got ${actualBaselineHash}`);
  }
  const baselineManifest = JSON.parse(fs.readFileSync(baselineManifestPath, 'utf8'));
  validateBuildManifest(baselineManifest, 'baseline', WORKSPACE_ROOT);

  const candidateManifestPath = path.join(WORKSPACE_ROOT, 'build', 'prediction-eval', 'candidate', 'build-manifest.json');
  if (!fs.existsSync(candidateManifestPath)) {
    throw new Error(`Candidate build manifest missing at ${candidateManifestPath}`);
  }
  const candidateManifest = JSON.parse(fs.readFileSync(candidateManifestPath, 'utf8'));
  validateBuildManifest(candidateManifest, 'candidate', WORKSPACE_ROOT);

  const caseResults = [];

  for (const caseId of LIFECYCLE_CASE_IDS) {
    const baselineChild = spawnAndRecordChild('lifecycle-diff-baseline-' + caseId, process.execPath, [
      __filename,
      '--lifecycle-worker',
      'baseline',
      caseId,
      EXPECTED_HASH
    ]);

    const candidateChild = spawnAndRecordChild('lifecycle-diff-candidate-' + caseId, process.execPath, [
      __filename,
      '--lifecycle-worker',
      'candidate',
      caseId
    ]);

    if (caseId === 'unexpected-url') {
      assert.strictEqual(baselineChild.status, 1, `Baseline worker should exit 1 for unexpected-url, got ${baselineChild.status}`);
      assert.strictEqual(candidateChild.status, 1, `Candidate worker should exit 1 for unexpected-url, got ${candidateChild.status}`);
      assert.strictEqual(baselineChild.stdout, '', 'Baseline stdout must be empty on unexpected-url');
      assert.strictEqual(candidateChild.stdout, '', 'Candidate stdout must be empty on unexpected-url');
      assert.match(baselineChild.stderr, /Unexpected unauthorized fetch to URL: "\/unauthorized_endpoint"/);
      assert.match(candidateChild.stderr, /Unexpected unauthorized fetch to URL: "\/unauthorized_endpoint"/);

      caseResults.push({
        case_id: caseId,
        guard_enforced: true,
        baseline_exit: baselineChild.status,
        candidate_exit: candidateChild.status,
        matched: true
      });
    } else {
      if (baselineChild.status !== 0) {
        throw new Error(`Baseline lifecycle worker failed for case "${caseId}" (exit ${baselineChild.status}):\n${baselineChild.stderr}`);
      }
      if (candidateChild.status !== 0) {
        throw new Error(`Candidate lifecycle worker failed for case "${caseId}" (exit ${candidateChild.status}):\n${candidateChild.stderr}`);
      }
      const baselineOut = JSON.parse(baselineChild.stdout);
      const candidateOut = JSON.parse(candidateChild.stdout);

      assert.strictEqual(baselineOut.unexpected_url_attempts, 0, `Baseline unexpected_url_attempts must be 0 for ${caseId}`);
      assert.strictEqual(candidateOut.unexpected_url_attempts, 0, `Candidate unexpected_url_attempts must be 0 for ${caseId}`);

      assert.strictEqual(candidateOut.calls.length, baselineOut.calls.length, `Call count mismatch for case ${caseId}`);
      for (let c = 0; c < baselineOut.calls.length; c++) {
        assert.deepStrictEqual(candidateOut.calls[c].forecast, baselineOut.calls[c].forecast, `Call ${c} forecast mismatch in case ${caseId}`);
        assert.deepStrictEqual(candidateOut.calls[c].fetch_calls, baselineOut.calls[c].fetch_calls, `Call ${c} fetch calls mismatch in case ${caseId}`);
      }

      assert.deepStrictEqual(candidateOut.fetch_trace, baselineOut.fetch_trace, `Fetch trace mismatch in case ${caseId}`);
      assert.strictEqual(candidateOut.unexpected_url_attempts, baselineOut.unexpected_url_attempts, `Unexpected URL count mismatch in case ${caseId}`);

      caseResults.push({
        case_id: caseId,
        calls_compared: baselineOut.calls.length,
        fetch_trace_length: baselineOut.fetch_trace.length,
        unexpected_url_attempts: 0,
        matched: true
      });
    }
  }

  const resultDoc = {
    schema_version: 'nivesh-replay-supplemental-lifecycle-v1',
    calculation_id: 'preserved-directional-core-v1',
    baseline_manifest_hash: EXPECTED_HASH,
    candidate_manifest_hash: sha256File(candidateManifestPath),
    cases_verified: caseResults.length,
    all_matched: true,
    case_results: caseResults
  };

  return resultDoc;
}

// ---------------------------------------------------------------------------
// CLI Dispatch for all child workers and lifecycle runners
// ---------------------------------------------------------------------------
if (process.argv.includes('--adapter-worker')) {
  const modeIdx = process.argv.indexOf('--adapter-worker') + 1;
  const mode = process.argv[modeIdx];
  const scId = process.argv[modeIdx + 1];

  runAdapterWorker(mode, scId)
    .then((res) => {
      process.stdout.write(JSON.stringify(res) + '\n');
      process.exit(0);
    })
    .catch((err) => {
      process.stderr.write(`Adapter worker error: ${err.message}\n${err.stack}\n`);
      process.exit(1);
    });
  return;
}

if (process.argv.includes('--lifecycle-worker')) {
  const modeIdx = process.argv.indexOf('--lifecycle-worker') + 1;
  const mode = process.argv[modeIdx];
  const caseId = process.argv[modeIdx + 1];
  const expectedBaselineHash = process.argv[modeIdx + 2];

  runLifecycleWorker(mode, caseId, expectedBaselineHash)
    .then((res) => {
      process.stdout.write(JSON.stringify(res) + '\n');
      process.exit(0);
    })
    .catch((err) => {
      process.stderr.write(`Lifecycle worker error: ${err.message}\n${err.stack}\n`);
      process.exit(1);
    });
  return;
}

if (process.argv.includes('--verify-lifecycle')) {
  const hashIdx = process.argv.indexOf('--verify-lifecycle') + 1;
  const expectedHash = process.argv[hashIdx];

  verifyLifecycle(expectedHash)
    .then((doc) => {
      process.stdout.write(JSON.stringify(doc, null, 2) + '\n');
      process.exit(0);
    })
    .catch((err) => {
      process.stderr.write(`Supplemental lifecycle verification error: ${err.message}\n${err.stack}\n`);
      process.exit(1);
    });
  return;
}

if (process.argv.includes('--import-safety-worker')) {
  let stdoutCaptured = '';
  let stderrCaptured = '';
  const origStdout = process.stdout.write;
  const origStderr = process.stderr.write;
  process.stdout.write = (chunk, ...args) => { stdoutCaptured += chunk; return true; };
  process.stderr.write = (chunk, ...args) => { stderrCaptured += chunk; return true; };

  // Instrument mutating fs methods
  const fsMutations = ['writeFileSync', 'appendFileSync', 'unlinkSync', 'mkdirSync', 'rmdirSync', 'rmSync', 'renameSync'];
  for (const m of fsMutations) {
    fs[m] = () => { throw new Error(`Forbidden side-effect fs.${m} called during module import`); };
  }

  // Instrument child_process execution methods
  const cpMethods = ['spawn', 'spawnSync', 'exec', 'execSync', 'fork', 'execFile', 'execFileSync'];
  for (const m of cpMethods) {
    child_process[m] = () => { throw new Error(`Forbidden side-effect child_process.${m} called during module import`); };
  }

  // Instrument network
  const http = require('http');
  const https = require('https');
  const net = require('net');
  const tls = require('tls');
  const dgram = require('dgram');
  http.request = () => { throw new Error('Forbidden side-effect http.request called during module import'); };
  https.request = () => { throw new Error('Forbidden side-effect https.request called during module import'); };
  net.connect = () => { throw new Error('Forbidden side-effect net.connect called during module import'); };
  net.createConnection = () => { throw new Error('Forbidden side-effect net.createConnection called during module import'); };
  tls.connect = () => { throw new Error('Forbidden side-effect tls.connect called during module import'); };
  dgram.createSocket = () => { throw new Error('Forbidden side-effect dgram.createSocket called during module import'); };
  global.fetch = () => { throw new Error('Forbidden side-effect global.fetch called during module import'); };

  try {
    const cr = require('../compile_replay.cjs');
    const rp = require('../replay.cjs');
    process.stdout.write = origStdout;
    process.stderr.write = origStderr;

    if (stdoutCaptured.length > 0 || stderrCaptured.length > 0) {
      throw new Error(`Import produced unexpected side effect output:\nstdout: ${stdoutCaptured}\nstderr: ${stderrCaptured}`);
    }
    if (typeof cr.compile !== 'function' || typeof rp.runReplay !== 'function') {
      throw new Error('Exported functions missing from imported modules');
    }
    process.stdout.write(JSON.stringify({ import_safety: 'passed' }) + '\n');
    process.exit(0);
  } catch (err) {
    process.stdout.write = origStdout;
    process.stderr.write = origStderr;
    process.stderr.write(`Import safety error: ${err.message}\n`);
    process.exit(1);
  }
  return;
}

// ---------------------------------------------------------------------------
// Test Suite: Node Test Runner Integration
// ---------------------------------------------------------------------------

test('golden replay parity across all synthetic scenarios', async () => {
  assert.ok(fs.existsSync(GOLDEN_PATH), `Golden baseline missing at ${GOLDEN_PATH}`);
  const golden = JSON.parse(fs.readFileSync(GOLDEN_PATH, 'utf8'));
  const casesData = JSON.parse(fs.readFileSync(CASES_PATH, 'utf8'));

  assert.strictEqual(golden.results.length, casesData.scenarios.length);

  for (const expected of golden.results) {
    const workerArgs = [
      __filename,
      '--adapter-worker',
      'candidate',
      expected.id
    ];

    const child = spawnAndRecordChild('adapter-candidate-' + expected.id, process.execPath, workerArgs, {
      scenarioIdentity: expected.id
    });

    assert.strictEqual(child.status, 0, `Candidate worker failed for ${expected.id}: ${child.stderr}`);
    const actual = JSON.parse(child.stdout);

    assert.deepStrictEqual(actual.forecast, expected.forecast, `Forecast mismatch in scenario ${expected.id}`);
    assert.deepStrictEqual(actual.fetch_trace, expected.fetch_trace, `Fetch trace mismatch in scenario ${expected.id}`);
  }
});

test('independent Platt probability and category boundary table', () => {
  const corePath = path.join(WORKSPACE_ROOT, 'build', 'prediction-eval', 'candidate', 'src', 'engine', 'marketIntelligence', 'forecastCore.js');
  assert.ok(fs.existsSync(corePath), `Candidate core build artifact must exist at ${corePath}`);
  const { computeDirectionalForecastCore } = require(corePath);

  // Independent synthetic table from contract section 8
  // Platt A=0, testing literal B values
  const table = [
    { B: 0, bull: 0.40, neu: 0.20, bear: 0.40, dir: 'NEUTRAL / RANGE-BOUND' },
    { B: 0.6190392084062236, bull: 0.53, neu: 0.19, bear: 0.28, dir: 'NEUTRAL / RANGE-BOUND' },
    { B: 0.6632942174102643, bull: 0.54, neu: 0.18, bear: 0.28, dir: 'MODERATELY BULLISH' },
    { B: 1.265666373331276, bull: 0.64, neu: 0.18, bear: 0.18, dir: 'MODERATELY BULLISH' },
    { B: 1.3249254147435987, bull: 0.65, neu: 0.18, bear: 0.17, dir: 'STRONGLY BULLISH' },
    { B: -0.6190392084062235, bull: 0.28, neu: 0.19, bear: 0.53, dir: 'NEUTRAL / RANGE-BOUND' },
    { B: -0.663294217410264, bull: 0.28, neu: 0.18, bear: 0.54, dir: 'MODERATELY BEARISH' },
    { B: -1.2656663733312759, bull: 0.18, neu: 0.18, bear: 0.64, dir: 'MODERATELY BEARISH' },
    { B: -1.3249254147435987, bull: 0.17, neu: 0.18, bear: 0.65, dir: 'STRONGLY BEARISH' }
  ];

  const dummyFeatures = {
    ret_5d: 0.0,
    rsi_14: 50.0,
    macd_hist: 0.0,
    vol_30d: 0.14,
    rel_strength_20d: 0.0,
    drawdown: 0.0,
    market_regime: 'Bull'
  };

  for (const row of table) {
    // Directly invoking computeDirectionalForecastCore with customPlattParams [0, row.B]
    // logit = 0 * rawLogit + row.B = row.B
    const fc = computeDirectionalForecastCore(dummyFeatures, '20D', [], [0, row.B]);

    assert.strictEqual(fc.probability_bullish, row.bull, `pBull mismatch for B=${row.B}`);
    assert.strictEqual(fc.probability_neutral, row.neu, `pNeutral mismatch for B=${row.B}`);
    assert.strictEqual(fc.probability_bearish, row.bear, `pBear mismatch for B=${row.B}`);
    assert.strictEqual(fc.expected_direction, row.dir, `Direction mismatch for B=${row.B}`);
  }
});

test('independent component pre-weighting rounding oracle', () => {
  const corePath = path.join(WORKSPACE_ROOT, 'build', 'prediction-eval', 'candidate', 'src', 'engine', 'marketIntelligence', 'forecastCore.js');
  assert.ok(fs.existsSync(corePath), `Candidate core build artifact must exist at ${corePath}`);
  const { computeDirectionalForecastCore } = require(corePath);

  // Verifies that components are rounded to 1 decimal place before weighting
  // technical = (r5 * 400.0) + ((rsi - 50.0) * 0.8) + (macd * 35.0) - ((vol - 0.14) * 60.0)
  // Let r5=0.01234, rsi=55.123, macd=0.234, vol=0.145
  // r5*400 = 4.936
  // (55.123 - 50)*0.8 = 4.0984
  // 0.234*35 = 8.19
  // (0.145 - 0.14)*60 = 0.3
  // Sum = 4.936 + 4.0984 + 8.19 - 0.3 = 16.9244
  // Rounded: +16.9244.toFixed(1) = 16.9
  const unrounded = 4.936 + 4.0984 + 8.19 - 0.3;
  const rounded = +unrounded.toFixed(1);
  assert.strictEqual(rounded, 16.9);
  assert.notStrictEqual(unrounded, rounded);

  const testFeatures = {
    ret_5d: 0.01234,
    rsi_14: 55.123,
    macd_hist: 0.234,
    vol_30d: 0.145,
    rel_strength_20d: 0.0,
    drawdown: -0.05,
    market_regime: 'Bull'
  };

  const fc = computeDirectionalForecastCore(testFeatures, '20D', [], [1.0, 0.0]);
  assert.strictEqual(fc.model_disagreement.components.technical, 16.9, 'technical component must be rounded to 1 decimal place');
  assert.notStrictEqual(fc.model_disagreement.components.technical, unrounded, 'technical component must not preserve unrounded float');
});

test('pure core input immutability and lack of side effects', () => {
  const corePath = path.join(WORKSPACE_ROOT, 'build', 'prediction-eval', 'candidate', 'src', 'engine', 'marketIntelligence', 'forecastCore.js');
  assert.ok(fs.existsSync(corePath), `Candidate core build artifact must exist at ${corePath}`);
  const { computeDirectionalForecastCore } = require(corePath);

  const inputFeatures = {
    ret_5d: 0.02,
    rsi_14: 55.0,
    macd_hist: 0.3,
    vol_30d: 0.15,
    rel_strength_20d: 0.01,
    drawdown: -0.02,
    market_regime: 'Bull'
  };
  Object.freeze(inputFeatures);

  const events = [];
  Object.freeze(events);

  const plattParams = [1.42, 0.02];
  Object.freeze(plattParams);

  const fc = computeDirectionalForecastCore(inputFeatures, '20D', events, plattParams);
  assert.ok(fc, 'Forecast should be non-null');
  assert.strictEqual(fc.horizon, '20D');
  assert.strictEqual(fc.days, 20);
  assert.ok(typeof fc.probability_bullish === 'number');
});

test('build manifest schema and file identity validation', () => {
  const { validateBuildManifest } = require('../compile_replay.cjs');
  const candidateManifestPath = path.join(WORKSPACE_ROOT, 'build', 'prediction-eval', 'candidate', 'build-manifest.json');
  assert.ok(fs.existsSync(candidateManifestPath), `Candidate build manifest must exist at ${candidateManifestPath}`);

  const manifest = JSON.parse(fs.readFileSync(candidateManifestPath, 'utf8'));
  assert.doesNotThrow(() => validateBuildManifest(manifest, 'candidate', WORKSPACE_ROOT));

  // Verify rejection of runtime identity mismatches
  assert.throws(
    () => validateBuildManifest({ ...manifest, toolchain: { ...manifest.toolchain, node_version: 'v0.0.0' } }, 'candidate', WORKSPACE_ROOT),
    /Toolchain node_version mismatch/
  );

  assert.throws(
    () => validateBuildManifest({ ...manifest, toolchain: { ...manifest.toolchain, node_executable: { ...manifest.toolchain.node_executable, bytes: 999 } } }, 'candidate', WORKSPACE_ROOT),
    /Toolchain node_executable size mismatch/
  );

  assert.throws(
    () => validateBuildManifest({ ...manifest, toolchain: { ...manifest.toolchain, node_executable: { ...manifest.toolchain.node_executable, sha256: '0'.repeat(64) } } }, 'candidate', WORKSPACE_ROOT),
    /Toolchain node_executable sha256 mismatch/
  );

  assert.throws(
    () => validateBuildManifest({ ...manifest, toolchain: { ...manifest.toolchain, typescript_version: '0.0.1' } }, 'candidate', WORKSPACE_ROOT),
    /Toolchain typescript_version mismatch/
  );

  assert.throws(
    () => validateBuildManifest({ ...manifest, unexpected_root_key: 'invalid' }, 'candidate', WORKSPACE_ROOT),
    /Unexpected unknown key "unexpected_root_key"/
  );

  assert.throws(
    () => validateBuildManifest({ ...manifest, toolchain: { ...manifest.toolchain, unexpected_tool_key: 'invalid' } }, 'candidate', WORKSPACE_ROOT),
    /Unexpected unknown key "unexpected_tool_key"/
  );
});

test('wire protocol CLI 207-row supplied axis with unready and ready origins', async () => {
  const replayCli = path.join(WORKSPACE_ROOT, 'research', 'prediction_eval', 'replay.cjs');
  assert.ok(fs.existsSync(replayCli), `replay.cjs must exist at ${replayCli}`);

  ensureOwnedScratchDir(TEST_WORK_DIR);

  // Generate synthetic 207-row request (indices 0..206, missing vix at 205)
  const rows = [];
  let d = new Date('2025-01-01T00:00:00Z');
  for (let i = 0; i <= 206; i++) {
    const dtStr = d.toISOString().slice(0, 10);
    const isUnready = (i < 200 || i === 205);
    const reasons = [];
    if (i < 200) reasons.push('warmup');
    if (i === 205) reasons.push('missing_vix');

    const vixClose = (i === 205) ? null : '14.50';
    const payload = isUnready ? null : {
      ret_5d: 0.01,
      rsi_14: 55.0,
      macd_hist: 0.2,
      vol_30d: 0.14,
      rel_strength_20d: 0.0,
      drawdown: -0.01,
      market_regime: 'Bull'
    };

    rows.push({
      origin_index: i,
      origin_date: dtStr,
      origin_close: '24000.50',
      vix_close: vixClose,
      feature_ready: !isUnready,
      unready_reasons: reasons,
      payload
    });

    d.setUTCDate(d.getUTCDate() + 1);
  }

  const reqDoc = {
    schema_version: 'nivesh-replay-input-v1',
    feature_protocol: 'nifty-close-features-v1',
    series_id: '^NSEI',
    asset: '^NSEI',
    horizon: '20D',
    variant: 'frozen-current-core-market-data-only-v1',
    axis_start_date: rows[0].origin_date,
    calendar_status: 'matches_supplied_sessions',
    missing_sessions: [],
    extra_sessions: [],
    nifty_provenance: [],
    vix_provenance: [],
    rows
  };

  const reqPath = path.join(TEST_WORK_DIR, 'req-207-rows.json');
  fs.writeFileSync(reqPath, JSON.stringify(reqDoc, null, 2), 'utf8');

  const child = runReplayCli('207-rows', reqPath);

  assert.strictEqual(child.status, 0, `CLI failed on 207-row input: ${child.stderr}`);
  const outDoc = JSON.parse(child.stdout);
  assert.strictEqual(outDoc.schema_version, 'nivesh-replay-output-v1');
  assert.strictEqual(outDoc.forecasts.length, 207);

  // Check origins 0..199 are unready (forecast=null)
  assert.strictEqual(outDoc.forecasts[0].forecast, null);
  assert.strictEqual(outDoc.forecasts[199].forecast, null);

  // Check origin 200 is ready
  assert.ok(outDoc.forecasts[200].forecast !== null);
  assert.strictEqual(outDoc.forecasts[200].forecast.horizon, '20D');

  // Check origin 205 is unready (missing_vix)
  assert.strictEqual(outDoc.forecasts[205].forecast, null);

  // Check origin 206 is ready
  assert.ok(outDoc.forecasts[206].forecast !== null);
});

test('wire protocol CLI ready-row forecast equals sealed baseline golden oracle', async () => {
  // Synthetic wiring evidence only: the frozen scenario-03 feature row and the forecast
  // captured from the untouched baseline adapter. Expected values never come from the
  // candidate core; this does not validate Python-generated features or forecast accuracy.
  const scenarioId = 'scenario-03-horizon-20d-shipped';
  const casesData = JSON.parse(fs.readFileSync(CASES_PATH, 'utf8'));
  const golden = JSON.parse(fs.readFileSync(GOLDEN_PATH, 'utf8'));
  const scenario = casesData.scenarios.find(s => s.id === scenarioId);
  const expected = golden.results.find(r => r.id === scenarioId);
  assert.ok(scenario && expected && expected.forecast, `Sealed scenario ${scenarioId} and its golden forecast must exist`);

  // The golden was captured under exactly the replay variant's conditions
  assert.strictEqual(scenario.horizon, '20D');
  assert.deepStrictEqual(scenario.events, []);
  assert.deepStrictEqual(scenario.models_fixture['20D'].platt_params, [1.42, 0.02]);

  const priceRows = scenario.prices_fixture[scenario.asset.symbol];
  const latest = priceRows[priceRows.length - 1];
  const payloadKeys = ['ret_5d', 'rsi_14', 'macd_hist', 'vol_30d', 'rel_strength_20d', 'drawdown', 'market_regime'];
  const payload = {};
  for (const k of payloadKeys) {
    assert.notStrictEqual(latest[k], undefined, `Scenario feature ${k} must be present`);
    payload[k] = latest[k];
  }

  const rows = [];
  const d = new Date('2025-01-01T00:00:00Z');
  for (let i = 0; i <= 200; i++) {
    const isReady = (i === 200);
    rows.push({
      origin_index: i,
      origin_date: d.toISOString().slice(0, 10),
      origin_close: '25000.00',
      vix_close: '14.50',
      feature_ready: isReady,
      unready_reasons: isReady ? [] : ['warmup'],
      payload: isReady ? payload : null
    });
    d.setUTCDate(d.getUTCDate() + 1);
  }

  const reqDoc = {
    schema_version: 'nivesh-replay-input-v1',
    feature_protocol: 'nifty-close-features-v1',
    series_id: '^NSEI',
    asset: '^NSEI',
    horizon: '20D',
    variant: 'frozen-current-core-market-data-only-v1',
    axis_start_date: rows[0].origin_date,
    calendar_status: 'not_checked',
    missing_sessions: [],
    extra_sessions: [],
    nifty_provenance: [],
    vix_provenance: [],
    rows
  };

  ensureOwnedScratchDir(TEST_WORK_DIR);
  const reqPath = path.join(TEST_WORK_DIR, 'req-golden-oracle.json');
  fs.writeFileSync(reqPath, JSON.stringify(reqDoc, null, 2), { encoding: 'utf8', flag: 'wx' });

  const child = runReplayCli('golden-oracle', reqPath);
  assert.strictEqual(child.status, 0, `CLI failed on golden-oracle input: ${child.stderr}`);
  const outDoc = JSON.parse(child.stdout);

  assert.strictEqual(outDoc.forecasts.length, 201);
  for (let i = 0; i < 200; i++) {
    assert.strictEqual(outDoc.forecasts[i].forecast, null, `Warmup origin ${i} must have a null forecast`);
  }
  assert.deepStrictEqual(outDoc.declared_input.rows[200].payload, payload);
  assert.deepStrictEqual(outDoc.computed_provenance.model.platt_params, [1.42, 0.02]);
  assert.strictEqual(outDoc.computed_provenance.model.sha256, '87C4DB2A4EB3B40AE5F7499C977AB407FFE3C3BE367E4DAE8FD8AE1804F543CD');

  const fc = outDoc.forecasts[200].forecast;
  assert.strictEqual(fc.horizon, '20D');
  assert.strictEqual(fc.days, 20);
  assert.deepStrictEqual(fc, expected.forecast, 'Replay CLI forecast must equal the sealed baseline-adapter forecast');
});

test('wire protocol CLI empty axis and empty file validation', async () => {
  const replayCli = path.join(WORKSPACE_ROOT, 'research', 'prediction_eval', 'replay.cjs');
  assert.ok(fs.existsSync(replayCli), `replay.cjs must exist at ${replayCli}`);

  ensureOwnedScratchDir(TEST_WORK_DIR);

  // 1. Physically empty file fails
  const emptyFilePath = path.join(TEST_WORK_DIR, 'empty-file.json');
  fs.writeFileSync(emptyFilePath, '', 'utf8');
  const resEmpty = runReplayCli('empty-file', emptyFilePath);
  assert.notStrictEqual(resEmpty.status, 0, 'Physically empty file must fail');
  assert.strictEqual(resEmpty.stdout, '', 'Stdout must be empty on physical empty failure');

  // 2. Empty-axis JSON valid with axis_start_date null
  const emptyAxisDoc = {
    schema_version: 'nivesh-replay-input-v1',
    feature_protocol: 'nifty-close-features-v1',
    series_id: '^NSEI',
    asset: '^NSEI',
    horizon: '20D',
    variant: 'frozen-current-core-market-data-only-v1',
    axis_start_date: null,
    calendar_status: 'not_checked',
    missing_sessions: [],
    extra_sessions: [],
    nifty_provenance: [],
    vix_provenance: [],
    rows: []
  };
  const emptyAxisPath = path.join(TEST_WORK_DIR, 'empty-axis.json');
  fs.writeFileSync(emptyAxisPath, JSON.stringify(emptyAxisDoc, null, 2), 'utf8');
  const resAxis = runReplayCli('empty-axis', emptyAxisPath);
  assert.strictEqual(resAxis.status, 0, `Empty axis should succeed: ${resAxis.stderr}`);
  const axisOut = JSON.parse(resAxis.stdout);
  assert.strictEqual(axisOut.forecasts.length, 0);
});

test('wire protocol CLI malformed JSON and duplicate row validation', async () => {
  const replayCli = path.join(WORKSPACE_ROOT, 'research', 'prediction_eval', 'replay.cjs');
  assert.ok(fs.existsSync(replayCli), `replay.cjs must exist at ${replayCli}`);

  ensureOwnedScratchDir(TEST_WORK_DIR);

  // 1. Malformed JSON
  const badJsonPath = path.join(TEST_WORK_DIR, 'bad.json');
  fs.writeFileSync(badJsonPath, '{ invalid json', 'utf8');
  const resBad = runReplayCli('bad-json', badJsonPath);
  assert.notStrictEqual(resBad.status, 0, 'Malformed JSON must fail');
  assert.strictEqual(resBad.stdout, '', 'Stdout must be empty on malformed JSON failure');

  // 2. Duplicate row indices
  const dupDoc = {
    schema_version: 'nivesh-replay-input-v1',
    feature_protocol: 'nifty-close-features-v1',
    series_id: '^NSEI',
    asset: '^NSEI',
    horizon: '20D',
    variant: 'frozen-current-core-market-data-only-v1',
    axis_start_date: '2026-01-01',
    calendar_status: 'matches_supplied_sessions',
    missing_sessions: [],
    extra_sessions: [],
    nifty_provenance: [],
    vix_provenance: [],
    rows: [
      {
        origin_index: 0,
        origin_date: '2026-01-01',
        origin_close: '24000.0',
        vix_close: '14.0',
        feature_ready: false,
        unready_reasons: ['warmup'],
        payload: null
      },
      {
        origin_index: 0, // Duplicate index!
        origin_date: '2026-01-02',
        origin_close: '24100.0',
        vix_close: '14.0',
        feature_ready: false,
        unready_reasons: ['warmup'],
        payload: null
      }
    ]
  };
  const dupPath = path.join(TEST_WORK_DIR, 'dup-index.json');
  fs.writeFileSync(dupPath, JSON.stringify(dupDoc, null, 2), 'utf8');
  const resDup = runReplayCli('dup-index', dupPath);
  assert.notStrictEqual(resDup.status, 0, 'Duplicate origin_index must fail');
  assert.strictEqual(resDup.stdout, '', 'Stdout must be empty on duplicate origin_index failure');
});

test('wire protocol CLI extreme nonfinite arithmetic failure handling', async () => {
  const replayCli = path.join(WORKSPACE_ROOT, 'research', 'prediction_eval', 'replay.cjs');
  assert.ok(fs.existsSync(replayCli), `replay.cjs must exist at ${replayCli}`);

  ensureOwnedScratchDir(TEST_WORK_DIR);

  // Build 201 rows where row 200 is feature_ready: true, but contains nonfinite numeric in payload
  const rows = [];
  let d = new Date('2025-01-01T00:00:00Z');
  for (let i = 0; i <= 200; i++) {
    const dtStr = d.toISOString().slice(0, 10);
    const isReady = (i === 200);
    rows.push({
      origin_index: i,
      origin_date: dtStr,
      origin_close: '24000.0',
      vix_close: '14.0',
      feature_ready: isReady,
      unready_reasons: isReady ? [] : ['warmup'],
      payload: isReady ? {
        ret_5d: '__REPLACE_NONFINITE__',
        rsi_14: 50.0,
        macd_hist: 0.0,
        vol_30d: 0.15,
        rel_strength_20d: 0.0,
        drawdown: 0.0,
        market_regime: 'Bull'
      } : null
    });
    d.setUTCDate(d.getUTCDate() + 1);
  }

  const nonfiniteDoc = {
    schema_version: 'nivesh-replay-input-v1',
    feature_protocol: 'nifty-close-features-v1',
    series_id: '^NSEI',
    asset: '^NSEI',
    horizon: '20D',
    variant: 'frozen-current-core-market-data-only-v1',
    axis_start_date: rows[0].origin_date,
    calendar_status: 'matches_supplied_sessions',
    missing_sessions: [],
    extra_sessions: [],
    nifty_provenance: [],
    vix_provenance: [],
    rows
  };

  const nonfinitePath = path.join(TEST_WORK_DIR, 'nonfinite.json');
  fs.writeFileSync(nonfinitePath, JSON.stringify(nonfiniteDoc).replace('"__REPLACE_NONFINITE__"', '1e999'), 'utf8');

  const resNonfinite = runReplayCli('nonfinite', nonfinitePath);
  assert.notStrictEqual(resNonfinite.status, 0, 'Nonfinite float in ready payload must fail at CLI');
  assert.strictEqual(resNonfinite.stdout, '', 'Stdout must be empty on nonfinite failure');
  assert.match(resNonfinite.stderr, /(?:Nonfinite numeric encountered|must be a finite number)/);
});

test('wire protocol CLI model file integrity and Platt parameter validation', async () => {
  const replayCli = path.join(WORKSPACE_ROOT, 'research', 'prediction_eval', 'replay.cjs');
  assert.ok(fs.existsSync(replayCli), `replay.cjs must exist at ${replayCli}`);

  const { validateModelsContent } = require('../replay.cjs');
  const modelsPath = path.join(WORKSPACE_ROOT, 'public', 'data', 'market_intelligence', 'models.json');
  assert.ok(fs.existsSync(modelsPath), 'models.json must exist');
  const hash = sha256File(modelsPath);
  assert.strictEqual(hash, '87C4DB2A4EB3B40AE5F7499C977AB407FFE3C3BE367E4DAE8FD8AE1804F543CD');

  const modelsBuf = fs.readFileSync(modelsPath);
  const rawModels = JSON.parse(modelsBuf.toString('utf8'));
  const { modelSha256, model20D } = validateModelsContent(modelsBuf);
  assert.strictEqual(modelSha256, hash);
  assert.deepStrictEqual(model20D.platt_params, [1.42, 0.02]);

  // Synthetic model buffer rejection calling the actual validation seam:
  // 1. Without matching hash, fails hash check
  const badPlattDoc = { ...rawModels, '20D': { ...rawModels['20D'], platt_params: [0.0, 0.0] } };
  const badPlattBuf = Buffer.from(JSON.stringify(badPlattDoc), 'utf8');
  assert.throws(() => validateModelsContent(badPlattBuf), /Model file hash mismatch/);

  // 2. With matching hash passed, fails Platt parameter validation
  const badPlattHash = sha256Buffer(badPlattBuf);
  assert.throws(() => validateModelsContent(badPlattBuf, badPlattHash), /20D Platt params mismatch/);

  // 3. With missing 20D horizon, fails structure validation
  const badHorizonDoc = { '10D': rawModels['20D'] };
  const badHorizonBuf = Buffer.from(JSON.stringify(badHorizonDoc), 'utf8');
  const badHorizonHash = sha256Buffer(badHorizonBuf);
  assert.throws(() => validateModelsContent(badHorizonBuf, badHorizonHash), /Model 20D entry or platt_params missing/);
});

test('wire protocol CLI finite-input arithmetic overflow handling', async () => {
  const replayCli = path.join(WORKSPACE_ROOT, 'research', 'prediction_eval', 'replay.cjs');
  assert.ok(fs.existsSync(replayCli), `replay.cjs must exist at ${replayCli}`);

  ensureOwnedScratchDir(TEST_WORK_DIR);

  const rows = [];
  let d = new Date('2025-01-01T00:00:00Z');
  for (let i = 0; i < 205; i++) {
    const dtStr = d.toISOString().slice(0, 10);
    const isReady = (i >= 200);
    const isOverflowRow = (i === 204);
    rows.push({
      origin_index: i,
      origin_date: dtStr,
      origin_close: '24000.0',
      vix_close: '14.0',
      feature_ready: isReady,
      unready_reasons: isReady ? [] : ['warmup'],
      payload: isReady ? {
        ret_5d: isOverflowRow ? 1e308 : 0.01,
        rsi_14: 50.0,
        macd_hist: isOverflowRow ? -1e308 : 0.0,
        vol_30d: 0.15,
        rel_strength_20d: 0.0,
        drawdown: 0.0,
        market_regime: 'Bull'
      } : null
    });
    d.setUTCDate(d.getUTCDate() + 1);
  }

  for (const r of rows) {
    if (r.payload) {
      assert.ok(Number.isFinite(r.payload.ret_5d));
      assert.ok(Number.isFinite(r.payload.macd_hist));
    }
  }

  const overflowDoc = {
    schema_version: 'nivesh-replay-input-v1',
    feature_protocol: 'nifty-close-features-v1',
    series_id: '^NSEI',
    asset: '^NSEI',
    horizon: '20D',
    variant: 'frozen-current-core-market-data-only-v1',
    axis_start_date: rows[0].origin_date,
    calendar_status: 'matches_supplied_sessions',
    missing_sessions: [],
    extra_sessions: [],
    nifty_provenance: [],
    vix_provenance: [],
    rows
  };

  const overflowPath = path.join(TEST_WORK_DIR, 'finite-overflow.json');
  fs.writeFileSync(overflowPath, JSON.stringify(overflowDoc, null, 2), 'utf8');

  const res = runReplayCli('overflow', overflowPath);

  assert.notStrictEqual(res.status, 0, 'Finite-input arithmetic overflow must fail at CLI');
  assert.strictEqual(res.stdout, '', 'Stdout must be empty on arithmetic overflow');
  assert.match(res.stderr, /Nonfinite numeric encountered/);
});

test('wire protocol CLI build manifest traversal and safety validation', () => {
  const { validateBuildManifest, assertSafeRelativePath } = require('../compile_replay.cjs');

  // assertSafeRelativePath checks
  assert.throws(() => assertSafeRelativePath('../evil.ts'), /Directory traversal/);
  assert.throws(() => assertSafeRelativePath('a/../../b.ts'), /Directory traversal/);
  assert.throws(() => assertSafeRelativePath('/root/file.ts'), /Absolute paths/);
  assert.throws(() => assertSafeRelativePath('C:\\Windows\\win.ini'), /Absolute paths/);
  assert.throws(() => assertSafeRelativePath('.'), /Directory traversal/);
  assert.throws(() => assertSafeRelativePath(''), /Invalid path/);
  assert.doesNotThrow(() => assertSafeRelativePath('src/engine/marketIntelligence/forecastCore.ts'));

  // Test traversal path rejection in validateBuildManifest
  const fakeManifest = {
    schema_version: 'nivesh-replay-build-v1',
    mode: 'candidate',
    calculation_id: 'preserved-directional-core-v1',
    compiler_exit: 0,
    source_files: [{ path: '../evil.ts', bytes: 10, sha256: '0000000000000000000000000000000000000000000000000000000000000000' }],
    support_files: [],
    emitted_files: [],
    toolchain: {
      node_version: process.version,
      node_executable: { bytes: 10, sha256: '0000000000000000000000000000000000000000000000000000000000000000' },
      typescript_version: '5.9.3',
      compiler_files: []
    },
    package_boundary: { path: 'package.json', bytes: 10, sha256: '0000000000000000000000000000000000000000000000000000000000000000' }
  };
  assert.throws(() => validateBuildManifest(fakeManifest, 'candidate', WORKSPACE_ROOT));
});

test('wire protocol CLI schema validation and unknown key rejection', async () => {
  const replayCli = path.join(WORKSPACE_ROOT, 'research', 'prediction_eval', 'replay.cjs');
  assert.ok(fs.existsSync(replayCli), `replay.cjs must exist at ${replayCli}`);

  ensureOwnedScratchDir(TEST_WORK_DIR);

  const validDoc = {
    schema_version: 'nivesh-replay-input-v1',
    feature_protocol: 'nifty-close-features-v1',
    series_id: '^NSEI',
    asset: '^NSEI',
    horizon: '20D',
    variant: 'frozen-current-core-market-data-only-v1',
    axis_start_date: null,
    calendar_status: 'not_checked',
    missing_sessions: [],
    extra_sessions: [],
    nifty_provenance: [],
    vix_provenance: [],
    rows: []
  };

  // 1. Unknown root key rejection
  const badRoot = { ...validDoc, unknown_root_key: 'forbidden' };
  const badRootPath = path.join(TEST_WORK_DIR, 'bad-root-key.json');
  fs.writeFileSync(badRootPath, JSON.stringify(badRoot, null, 2), 'utf8');
  const resBadRoot = runReplayCli('bad-root-key', badRootPath);
  assert.notStrictEqual(resBadRoot.status, 0, 'Unknown root key must fail');
  assert.strictEqual(resBadRoot.stdout, '', 'Stdout must be empty on unknown root key');
  assert.match(resBadRoot.stderr, /Unknown unexpected field "unknown_root_key"/);

  // 2. Unknown row key rejection
  const badRowDoc = {
    ...validDoc,
    axis_start_date: '2026-01-01',
    calendar_status: 'matches_supplied_sessions',
    rows: [{
      origin_index: 0,
      origin_date: '2026-01-01',
      origin_close: '24000.0',
      vix_close: '14.0',
      feature_ready: false,
      unready_reasons: ['warmup'],
      payload: null,
      forbidden_row_field: true
    }]
  };
  const badRowPath = path.join(TEST_WORK_DIR, 'bad-row-key.json');
  fs.writeFileSync(badRowPath, JSON.stringify(badRowDoc, null, 2), 'utf8');
  const resBadRow = runReplayCli('bad-row-key', badRowPath);
  assert.notStrictEqual(resBadRow.status, 0, 'Unknown row key must fail');
  assert.strictEqual(resBadRow.stdout, '', 'Stdout must be empty on unknown row key');
  assert.match(resBadRow.stderr, /Unknown unexpected field "forbidden_row_field"/);

  // 3. Unknown payload key rejection
  const badPayloadRows = [];
  let curD = new Date('2025-01-01T00:00:00Z');
  for (let i = 0; i <= 200; i++) {
    const dtStr = curD.toISOString().slice(0, 10);
    const isReady = (i === 200);
    badPayloadRows.push({
      origin_index: i,
      origin_date: dtStr,
      origin_close: '24000.0',
      vix_close: '14.0',
      feature_ready: isReady,
      unready_reasons: isReady ? [] : ['warmup'],
      payload: isReady ? {
        ret_5d: 0.01,
        rsi_14: 50.0,
        macd_hist: 0.0,
        vol_30d: 0.15,
        rel_strength_20d: 0.0,
        drawdown: 0.0,
        market_regime: 'Bull',
        unknown_feature: 999
      } : null
    });
    curD.setUTCDate(curD.getUTCDate() + 1);
  }
  const badPayloadDoc = {
    ...validDoc,
    axis_start_date: badPayloadRows[0].origin_date,
    calendar_status: 'matches_supplied_sessions',
    rows: badPayloadRows
  };
  const badPayloadPath = path.join(TEST_WORK_DIR, 'bad-payload-key.json');
  fs.writeFileSync(badPayloadPath, JSON.stringify(badPayloadDoc, null, 2), 'utf8');
  const resBadPayload = runReplayCli('bad-payload-key', badPayloadPath);
  assert.notStrictEqual(resBadPayload.status, 0, 'Unknown payload key must fail');
  assert.strictEqual(resBadPayload.stdout, '', 'Stdout must be empty on unknown payload key');
  assert.match(resBadPayload.stderr, /Unknown unexpected field "unknown_feature"/);

  // 4. Unknown provenance key rejection
  const badProvDoc = {
    ...validDoc,
    nifty_provenance: [{
      file_path: 'nifty.csv',
      raw_byte_count: 100,
      sha256: '0000000000000000000000000000000000000000000000000000000000000000',
      record_count: 0,
      observed_first_date: null,
      observed_last_date: null,
      source_url: null,
      requested_interval: null,
      acquisition_time: null,
      source_use_note: null,
      extra_prov_key: 123
    }]
  };
  const badProvPath = path.join(TEST_WORK_DIR, 'bad-prov-key.json');
  fs.writeFileSync(badProvPath, JSON.stringify(badProvDoc, null, 2), 'utf8');
  const resBadProv = runReplayCli('bad-prov-key', badProvPath);
  assert.notStrictEqual(resBadProv.status, 0, 'Unknown provenance key must fail');
  assert.strictEqual(resBadProv.stdout, '', 'Stdout must be empty on unknown provenance key');
  assert.match(resBadProv.stderr, /Unknown unexpected field "extra_prov_key"/);
});

test('wire protocol CLI calendar metadata invariant validation', async () => {
  const replayCli = path.join(WORKSPACE_ROOT, 'research', 'prediction_eval', 'replay.cjs');
  assert.ok(fs.existsSync(replayCli), `replay.cjs must exist at ${replayCli}`);

  ensureOwnedScratchDir(TEST_WORK_DIR);

  const baseDoc = {
    schema_version: 'nivesh-replay-input-v1',
    feature_protocol: 'nifty-close-features-v1',
    series_id: '^NSEI',
    asset: '^NSEI',
    horizon: '20D',
    variant: 'frozen-current-core-market-data-only-v1',
    axis_start_date: '2026-01-02',
    calendar_status: 'matches_supplied_sessions',
    missing_sessions: [],
    extra_sessions: [],
    nifty_provenance: [],
    vix_provenance: [],
    rows: [{
      origin_index: 0,
      origin_date: '2026-01-02',
      origin_close: '24000.0',
      vix_close: '14.0',
      feature_ready: false,
      unready_reasons: ['warmup'],
      payload: null
    }]
  };

  // 1. matches_supplied_sessions with missing_sessions must fail
  const badStatusDoc = { ...baseDoc, missing_sessions: ['2026-01-01'] };
  const p1 = path.join(TEST_WORK_DIR, 'cal-bad-status.json');
  fs.writeFileSync(p1, JSON.stringify(badStatusDoc, null, 2), 'utf8');
  const r1 = runReplayCli('cal-bad-status', p1);
  assert.notStrictEqual(r1.status, 0, 'matches_supplied_sessions with missing sessions must fail');
  assert.strictEqual(r1.stdout, '');
  assert.match(r1.stderr, /missing_sessions and extra_sessions must be empty unless calendar_status is "mismatch"/);

  // 2. Invalid date format in missing_sessions (e.g. 2026-02-30) under calendar_status: mismatch
  const badDateDoc = { ...baseDoc, calendar_status: 'mismatch', missing_sessions: ['2026-02-30'] };
  const p2 = path.join(TEST_WORK_DIR, 'cal-bad-date.json');
  fs.writeFileSync(p2, JSON.stringify(badDateDoc, null, 2), 'utf8');
  const r2 = runReplayCli('cal-bad-date', p2);
  assert.notStrictEqual(r2.status, 0, 'Invalid Gregorian calendar date must fail');
  assert.strictEqual(r2.stdout, '');
  assert.match(r2.stderr, /missing_sessions\[0\] "2026-02-30" is not a valid Gregorian date/);

  // 3. Missing session present in rows must fail under calendar_status: mismatch
  const dupMissingDoc = { ...baseDoc, calendar_status: 'mismatch', missing_sessions: ['2026-01-02'] };
  const p3 = path.join(TEST_WORK_DIR, 'cal-missing-in-rows.json');
  fs.writeFileSync(p3, JSON.stringify(dupMissingDoc, null, 2), 'utf8');
  const r3 = runReplayCli('cal-missing-in-rows', p3);
  assert.notStrictEqual(r3.status, 0, 'Missing session date present in rows must fail');
  assert.strictEqual(r3.stdout, '');
  assert.match(r3.stderr, /Missing session date "2026-01-02" illegally exists on the supplied axis/);

  // 4. Extra session NOT present in rows must fail under calendar_status: mismatch
  const extraNotDoc = { ...baseDoc, calendar_status: 'mismatch', extra_sessions: ['2026-01-05'] };
  const p4 = path.join(TEST_WORK_DIR, 'cal-extra-not-in-rows.json');
  fs.writeFileSync(p4, JSON.stringify(extraNotDoc, null, 2), 'utf8');
  const r4 = runReplayCli('cal-extra-not-in-rows', p4);
  assert.notStrictEqual(r4.status, 0, 'Extra session not in rows must fail');
  assert.strictEqual(r4.stdout, '');
  assert.match(r4.stderr, /Extra session date "2026-01-05" does not exist on the supplied axis/);

  // 5. Unsorted / duplicate sessions must fail under calendar_status: mismatch
  const unsortedDoc = { ...baseDoc, calendar_status: 'mismatch', missing_sessions: ['2026-01-05', '2026-01-01'] };
  const p5 = path.join(TEST_WORK_DIR, 'cal-unsorted.json');
  fs.writeFileSync(p5, JSON.stringify(unsortedDoc, null, 2), 'utf8');
  const r5 = runReplayCli('cal-unsorted', p5);
  assert.notStrictEqual(r5.status, 0, 'Unsorted missing sessions must fail');
  assert.strictEqual(r5.stdout, '');
  assert.match(r5.stderr, /missing_sessions must be strictly sorted without duplicates/);

  // 6. Overlapping missing and extra sessions must fail under calendar_status: mismatch
  const overlapDoc = { ...baseDoc, calendar_status: 'mismatch', missing_sessions: ['2026-01-01'], extra_sessions: ['2026-01-01', '2026-01-02'] };
  const p6 = path.join(TEST_WORK_DIR, 'cal-overlap.json');
  fs.writeFileSync(p6, JSON.stringify(overlapDoc, null, 2), 'utf8');
  const r6 = runReplayCli('cal-overlap', p6);
  assert.notStrictEqual(r6.status, 0, 'Overlapping missing and extra sessions must fail');
  assert.strictEqual(r6.stdout, '');
  assert.match(r6.stderr, /Date "2026-01-01" appears in both missing_sessions and extra_sessions/);

  // 7. Valid mismatch control: extra session present on axis (2026-01-02), missing session absent from axis (2026-01-01)
  const validMismatchDoc = { ...baseDoc, calendar_status: 'mismatch', missing_sessions: ['2026-01-01'], extra_sessions: ['2026-01-02'] };
  const p7 = path.join(TEST_WORK_DIR, 'cal-valid-mismatch.json');
  fs.writeFileSync(p7, JSON.stringify(validMismatchDoc, null, 2), 'utf8');
  const r7 = runReplayCli('cal-valid-mismatch', p7);
  assert.strictEqual(r7.status, 0, `Valid mismatch control should succeed: ${r7.stderr}`);
  const out7 = JSON.parse(r7.stdout);
  assert.strictEqual(out7.schema_version, 'nivesh-replay-output-v1');
});

test('wire protocol CLI duplicate property handling', async () => {
  const replayCli = path.join(WORKSPACE_ROOT, 'research', 'prediction_eval', 'replay.cjs');
  assert.ok(fs.existsSync(replayCli), `replay.cjs must exist at ${replayCli}`);

  ensureOwnedScratchDir(TEST_WORK_DIR);

  // Standard JSON last-wins duplicate key
  const rawJson = `{
    "schema_version": "nivesh-replay-input-v1",
    "feature_protocol": "nifty-close-features-v1",
    "series_id": "^NSEI",
    "asset": "^NSEI",
    "horizon": "5D",
    "horizon": "20D",
    "variant": "frozen-current-core-market-data-only-v1",
    "axis_start_date": null,
    "calendar_status": "not_checked",
    "missing_sessions": [],
    "extra_sessions": [],
    "nifty_provenance": [],
    "vix_provenance": [],
    "rows": []
  }`;

  const dupPropPath = path.join(TEST_WORK_DIR, 'dup-property.json');
  fs.writeFileSync(dupPropPath, rawJson, 'utf8');

  const res = runReplayCli('dup-property', dupPropPath);
  assert.strictEqual(res.status, 0, `Duplicate property with valid last-win should succeed: ${res.stderr}`);
  const outDoc = JSON.parse(res.stdout);
  assert.strictEqual(outDoc.schema_version, 'nivesh-replay-output-v1');
});

test('wire protocol CLI fatal UTF-8 rejection', async () => {
  const replayCli = path.join(WORKSPACE_ROOT, 'research', 'prediction_eval', 'replay.cjs');
  assert.ok(fs.existsSync(replayCli), `replay.cjs must exist at ${replayCli}`);

  ensureOwnedScratchDir(TEST_WORK_DIR);

  // Write invalid UTF-8 bytes: 0xFF, 0xFE are invalid UTF-8 sequence
  const invalidUtf8Buf = Buffer.from([
    0x7B, 0x22, 0x73, 0x63, 0x68, 0x65, 0x6D, 0x61, 0x5F, 0x76, 0x65, 0x72, 0x73, 0x69, 0x6F, 0x6E,
    0x22, 0x3A, 0x20, 0x22, 0xFF, 0xFE, 0x22, 0x7D
  ]);
  const invalidUtf8Path = path.join(TEST_WORK_DIR, 'invalid-utf8.json');
  fs.writeFileSync(invalidUtf8Path, invalidUtf8Buf);

  const res = runReplayCli('invalid-utf8', invalidUtf8Path);

  assert.notStrictEqual(res.status, 0, 'Invalid UTF-8 bytes must be rejected');
  assert.strictEqual(res.stdout, '', 'Stdout must be empty on invalid UTF-8 rejection');
  assert.match(res.stderr, /Invalid UTF-8 encoding in input file/);
});

test('wire protocol CLI single leading BOM allowed', async () => {
  const replayCli = path.join(WORKSPACE_ROOT, 'research', 'prediction_eval', 'replay.cjs');
  assert.ok(fs.existsSync(replayCli), `replay.cjs must exist at ${replayCli}`);

  ensureOwnedScratchDir(TEST_WORK_DIR);

  const validJson = JSON.stringify({
    schema_version: 'nivesh-replay-input-v1',
    feature_protocol: 'nifty-close-features-v1',
    series_id: '^NSEI',
    asset: '^NSEI',
    horizon: '20D',
    variant: 'frozen-current-core-market-data-only-v1',
    axis_start_date: null,
    calendar_status: 'not_checked',
    missing_sessions: [],
    extra_sessions: [],
    nifty_provenance: [],
    vix_provenance: [],
    rows: []
  }, null, 2);

  const bomBuf = Buffer.concat([Buffer.from([0xEF, 0xBB, 0xBF]), Buffer.from(validJson, 'utf8')]);
  const bomPath = path.join(TEST_WORK_DIR, 'leading-bom.json');
  fs.writeFileSync(bomPath, bomBuf);

  const res = runReplayCli('leading-bom', bomPath);

  assert.strictEqual(res.status, 0, `Leading BOM should be accepted: ${res.stderr}`);
  const outDoc = JSON.parse(res.stdout);
  assert.strictEqual(outDoc.schema_version, 'nivesh-replay-output-v1');
  assert.strictEqual(outDoc.computed_provenance.request.sha256, sha256Buffer(bomBuf));
  assert.strictEqual(outDoc.computed_provenance.request.raw_byte_count, bomBuf.length);
});

test('wire protocol CLI repeated-BOM rejection', async () => {
  const replayCli = path.join(WORKSPACE_ROOT, 'research', 'prediction_eval', 'replay.cjs');
  assert.ok(fs.existsSync(replayCli), `replay.cjs must exist at ${replayCli}`);

  ensureOwnedScratchDir(TEST_WORK_DIR);

  const validJson = JSON.stringify({
    schema_version: 'nivesh-replay-input-v1',
    feature_protocol: 'nifty-close-features-v1',
    series_id: '^NSEI',
    asset: '^NSEI',
    horizon: '20D',
    variant: 'frozen-current-core-market-data-only-v1',
    axis_start_date: null,
    calendar_status: 'not_checked',
    missing_sessions: [],
    extra_sessions: [],
    nifty_provenance: [],
    vix_provenance: [],
    rows: []
  }, null, 2);

  const doubleBomBuf = Buffer.concat([
    Buffer.from([0xEF, 0xBB, 0xBF, 0xEF, 0xBB, 0xBF]),
    Buffer.from(validJson, 'utf8')
  ]);
  const doubleBomPath = path.join(TEST_WORK_DIR, 'repeated-bom.json');
  fs.writeFileSync(doubleBomPath, doubleBomBuf);

  const res = runReplayCli('repeated-bom', doubleBomPath);

  assert.notStrictEqual(res.status, 0, 'Repeated BOM must fail at CLI');
  assert.strictEqual(res.stdout, '', 'Stdout must be empty on repeated BOM failure');
  assert.match(res.stderr, /repeated leading UTF-8 BOM/);
});

test('wire protocol CLI provenance requested_interval ordering and date checks', async () => {
  const replayCli = path.join(WORKSPACE_ROOT, 'research', 'prediction_eval', 'replay.cjs');
  assert.ok(fs.existsSync(replayCli), `replay.cjs must exist at ${replayCli}`);

  ensureOwnedScratchDir(TEST_WORK_DIR);

  const baseProvDoc = {
    schema_version: 'nivesh-replay-input-v1',
    feature_protocol: 'nifty-close-features-v1',
    series_id: '^NSEI',
    asset: '^NSEI',
    horizon: '20D',
    variant: 'frozen-current-core-market-data-only-v1',
    axis_start_date: null,
    calendar_status: 'not_checked',
    missing_sessions: [],
    extra_sessions: [],
    nifty_provenance: [{
      file_path: 'nifty.csv',
      raw_byte_count: 100,
      sha256: '0000000000000000000000000000000000000000000000000000000000000000',
      record_count: 0,
      observed_first_date: null,
      observed_last_date: null,
      source_url: null,
      requested_interval: ['2026-02-02', '2026-02-01'], // Unordered!
      acquisition_time: null,
      source_use_note: null
    }],
    vix_provenance: [],
    rows: []
  };

  // 1. Unordered interval
  const p1 = path.join(TEST_WORK_DIR, 'unordered-interval.json');
  fs.writeFileSync(p1, JSON.stringify(baseProvDoc, null, 2), 'utf8');
  const r1 = runReplayCli('prov-unordered-interval', p1);
  assert.notStrictEqual(r1.status, 0);
  assert.strictEqual(r1.stdout, '');
  assert.match(r1.stderr, /requested_interval start date .* must be <= end date/);

  // 2. Invalid date in interval (2026-02-30)
  const badDateProvDoc = {
    ...baseProvDoc,
    nifty_provenance: [{
      ...baseProvDoc.nifty_provenance[0],
      requested_interval: ['2026-02-30', '2026-03-01']
    }]
  };
  const p2 = path.join(TEST_WORK_DIR, 'bad-date-interval.json');
  fs.writeFileSync(p2, JSON.stringify(badDateProvDoc, null, 2), 'utf8');
  const r2 = runReplayCli('prov-bad-date-interval', p2);
  assert.notStrictEqual(r2.status, 0);
  assert.strictEqual(r2.stdout, '');
  assert.match(r2.stderr, /requested_interval entries must be valid Gregorian dates/);

  // 3. Valid ordered interval
  const validProvDoc = {
    ...baseProvDoc,
    nifty_provenance: [{
      ...baseProvDoc.nifty_provenance[0],
      requested_interval: ['2026-01-01', '2026-02-01']
    }]
  };
  const p3 = path.join(TEST_WORK_DIR, 'valid-interval.json');
  fs.writeFileSync(p3, JSON.stringify(validProvDoc, null, 2), 'utf8');
  const r3 = runReplayCli('prov-valid-interval', p3);
  assert.strictEqual(r3.status, 0, `Valid interval should succeed: ${r3.stderr}`);
});

test('wire protocol CLI provenance acquisition_time validation', async () => {
  const replayCli = path.join(WORKSPACE_ROOT, 'research', 'prediction_eval', 'replay.cjs');
  assert.ok(fs.existsSync(replayCli), `replay.cjs must exist at ${replayCli}`);

  ensureOwnedScratchDir(TEST_WORK_DIR);

  const baseProvDoc = {
    schema_version: 'nivesh-replay-input-v1',
    feature_protocol: 'nifty-close-features-v1',
    series_id: '^NSEI',
    asset: '^NSEI',
    horizon: '20D',
    variant: 'frozen-current-core-market-data-only-v1',
    axis_start_date: null,
    calendar_status: 'not_checked',
    missing_sessions: [],
    extra_sessions: [],
    nifty_provenance: [{
      file_path: 'nifty.csv',
      raw_byte_count: 100,
      sha256: '0000000000000000000000000000000000000000000000000000000000000000',
      record_count: 0,
      observed_first_date: null,
      observed_last_date: null,
      source_url: null,
      requested_interval: null,
      acquisition_time: '2026-02-30T10:00:00Z', // Invalid calendar date!
      source_use_note: null
    }],
    vix_provenance: [],
    rows: []
  };

  const p1 = path.join(TEST_WORK_DIR, 'bad-acq-date.json');
  fs.writeFileSync(p1, JSON.stringify(baseProvDoc, null, 2), 'utf8');
  const r1 = runReplayCli('prov-bad-acq-date', p1);
  assert.notStrictEqual(r1.status, 0);
  assert.strictEqual(r1.stdout, '');
  assert.match(r1.stderr, /acquisition_time date prefix "2026-02-30" is not a valid Gregorian date/);

  // Valid acquisition_time
  const validAcqDoc = {
    ...baseProvDoc,
    nifty_provenance: [{
      ...baseProvDoc.nifty_provenance[0],
      acquisition_time: '2026-02-28T10:00:00.123456Z'
    }]
  };
  const p2 = path.join(TEST_WORK_DIR, 'valid-acq-date.json');
  fs.writeFileSync(p2, JSON.stringify(validAcqDoc, null, 2), 'utf8');
  const r2 = runReplayCli('prov-valid-acq-date', p2);
  assert.strictEqual(r2.status, 0, `Valid acquisition time should succeed: ${r2.stderr}`);
});

test('wire protocol CLI year 0001-9999 safe date support', async () => {
  const replayCli = path.join(WORKSPACE_ROOT, 'research', 'prediction_eval', 'replay.cjs');
  assert.ok(fs.existsSync(replayCli), `replay.cjs must exist at ${replayCli}`);

  ensureOwnedScratchDir(TEST_WORK_DIR);

  const year99Doc = {
    schema_version: 'nivesh-replay-input-v1',
    feature_protocol: 'nifty-close-features-v1',
    series_id: '^NSEI',
    asset: '^NSEI',
    horizon: '20D',
    variant: 'frozen-current-core-market-data-only-v1',
    axis_start_date: null,
    calendar_status: 'not_checked',
    missing_sessions: [],
    extra_sessions: [],
    nifty_provenance: [{
      file_path: 'nifty.csv',
      raw_byte_count: 100,
      sha256: '0000000000000000000000000000000000000000000000000000000000000000',
      record_count: 0,
      observed_first_date: null,
      observed_last_date: null,
      source_url: null,
      requested_interval: ['0099-01-01', '0099-01-02'],
      acquisition_time: '0099-01-02T12:00:00Z',
      source_use_note: null
    }],
    vix_provenance: [],
    rows: []
  };

  const p = path.join(TEST_WORK_DIR, 'year-99-date.json');
  fs.writeFileSync(p, JSON.stringify(year99Doc, null, 2), 'utf8');
  const r = runReplayCli('prov-year-99-date', p);
  assert.strictEqual(r.status, 0, `Year 0099 Gregorian date should succeed: ${r.stderr}`);
  const out = JSON.parse(r.stdout);
  assert.strictEqual(out.schema_version, 'nivesh-replay-output-v1');
});

test('wire protocol CLI late-invalid-row stdout empty check', async () => {
  const replayCli = path.join(WORKSPACE_ROOT, 'research', 'prediction_eval', 'replay.cjs');
  assert.ok(fs.existsSync(replayCli), `replay.cjs must exist at ${replayCli}`);

  ensureOwnedScratchDir(TEST_WORK_DIR);

  // 205 rows, row 204 has non-positive decimal origin_close
  const rows = [];
  let d = new Date('2025-01-01T00:00:00Z');
  for (let i = 0; i < 205; i++) {
    const dtStr = d.toISOString().slice(0, 10);
    const isReady = (i >= 200);
    rows.push({
      origin_index: i,
      origin_date: dtStr,
      origin_close: (i === 204) ? 'invalid_decimal' : '24000.0',
      vix_close: '14.0',
      feature_ready: isReady,
      unready_reasons: isReady ? [] : ['warmup'],
      payload: isReady ? {
        ret_5d: 0.01,
        rsi_14: 50.0,
        macd_hist: 0.0,
        vol_30d: 0.15,
        rel_strength_20d: 0.0,
        drawdown: 0.0,
        market_regime: 'Bull'
      } : null
    });
    d.setUTCDate(d.getUTCDate() + 1);
  }

  const lateInvalidDoc = {
    schema_version: 'nivesh-replay-input-v1',
    feature_protocol: 'nifty-close-features-v1',
    series_id: '^NSEI',
    asset: '^NSEI',
    horizon: '20D',
    variant: 'frozen-current-core-market-data-only-v1',
    axis_start_date: rows[0].origin_date,
    calendar_status: 'matches_supplied_sessions',
    missing_sessions: [],
    extra_sessions: [],
    nifty_provenance: [],
    vix_provenance: [],
    rows
  };

  const p = path.join(TEST_WORK_DIR, 'late-invalid-row.json');
  fs.writeFileSync(p, JSON.stringify(lateInvalidDoc, null, 2), 'utf8');

  const r = runReplayCli('late-invalid-row', p);
  assert.notStrictEqual(r.status, 0, 'Late invalid row must fail');
  assert.strictEqual(r.stdout, '', 'Stdout must remain strictly empty even when early rows are processed');
  assert.match(r.stderr, /must be a positive decimal string/);
});

test('import safety of compile_replay and replay modules', async () => {
  const child = spawnAndRecordChild('import-safety-worker', process.execPath, [__filename, '--import-safety-worker']);

  assert.strictEqual(child.status, 0, `Import safety worker failed: ${child.stderr}`);
  const res = JSON.parse(child.stdout);
  assert.strictEqual(res.import_safety, 'passed');
});

test('candidate lifecycle verification across 9 cases', async () => {
  const { validateBuildManifest } = require('../compile_replay.cjs');
  const candidateManifestPath = path.join(WORKSPACE_ROOT, 'build', 'prediction-eval', 'candidate', 'build-manifest.json');
  assert.ok(fs.existsSync(candidateManifestPath), `Candidate build manifest missing at ${candidateManifestPath}`);
  const candidateManifest = JSON.parse(fs.readFileSync(candidateManifestPath, 'utf8'));
  validateBuildManifest(candidateManifest, 'candidate', WORKSPACE_ROOT);

  for (const caseId of LIFECYCLE_CASE_IDS) {
    const candidateChild = spawnAndRecordChild('lifecycle-candidate-' + caseId, process.execPath, [
      __filename,
      '--lifecycle-worker',
      'candidate',
      caseId
    ], { caseId });

    if (caseId === 'unexpected-url') {
      assert.strictEqual(candidateChild.status, 1, `Candidate worker should exit 1 for unexpected-url, got ${candidateChild.status}`);
      assert.strictEqual(candidateChild.stdout, '', 'Candidate stdout must be empty on unexpected-url');
      assert.match(candidateChild.stderr, /Unexpected unauthorized fetch to URL: "\/unauthorized_endpoint"/);
    } else {
      assert.strictEqual(candidateChild.status, 0, `Candidate lifecycle worker failed for case "${caseId}" (exit ${candidateChild.status}):\n${candidateChild.stderr}`);
      const candidateOut = JSON.parse(candidateChild.stdout);
      assert.strictEqual(candidateOut.case_id, caseId);
      assert.strictEqual(candidateOut.mode, 'candidate');
      assert.strictEqual(candidateOut.unexpected_url_attempts, 0, `Candidate unexpected_url_attempts must be 0 for ${caseId}`);
      assert.strictEqual(candidateOut.calls.length, 2, `Expected 2 calls for case ${caseId}`);

      const MODELS_URL = '/data/market_intelligence/models.json';
      const HISTORY_URL = '/data/market_intelligence/historical_prices.json';
      // Probabilities for the worker's fixed ^NSEI row: default Platt [1.25, -0.05]
      // gives 0.49/0.32, trained 20D Platt [1.42, 0.02] gives 0.52/0.29.
      const assertProbabilities = (forecast, bull, bear, label) => {
        assert.ok(forecast !== null, `${label}: forecast must not be null`);
        assert.strictEqual(forecast.horizon, '20D', `${label}: horizon`);
        assert.strictEqual(forecast.probability_bullish, bull, `${label}: probability_bullish`);
        assert.strictEqual(forecast.probability_bearish, bear, `${label}: probability_bearish`);
      };

      if (caseId === 'cache-success') {
        assert.deepStrictEqual(candidateOut.calls[0].fetch_calls, [MODELS_URL, HISTORY_URL]);
        assert.deepStrictEqual(candidateOut.calls[1].fetch_calls, []);
        assertProbabilities(candidateOut.calls[0].forecast, 0.52, 0.29, `${caseId} call 0`);
        assert.deepStrictEqual(candidateOut.calls[0].forecast, candidateOut.calls[1].forecast);
      } else if (MODEL_RETRY_CASE_IDS.includes(caseId)) {
        // Every model failure variant (HTTP non-ok, fetch throw, JSON rejection) must
        // leave the model cache empty: call 0 falls back to default Platt with history
        // fetched and cached; call 1 refetches only models and recovers trained Platt.
        assert.deepStrictEqual(candidateOut.calls[0].fetch_calls, [MODELS_URL, HISTORY_URL]);
        assert.deepStrictEqual(candidateOut.calls[1].fetch_calls, [MODELS_URL]);
        assertProbabilities(candidateOut.calls[0].forecast, 0.49, 0.32, `${caseId} call 0 (default Platt)`);
        assertProbabilities(candidateOut.calls[1].forecast, 0.52, 0.29, `${caseId} call 1 (trained Platt)`);
      } else if (HISTORY_RETRY_CASE_IDS.includes(caseId)) {
        // Every history failure variant must leave the history cache empty: call 0
        // returns null with models cached; call 1 refetches only history and recovers.
        assert.deepStrictEqual(candidateOut.calls[0].fetch_calls, [MODELS_URL, HISTORY_URL]);
        assert.strictEqual(candidateOut.calls[0].forecast, null, `${caseId} call 0 must be null`);
        assert.deepStrictEqual(candidateOut.calls[1].fetch_calls, [HISTORY_URL]);
        assertProbabilities(candidateOut.calls[1].forecast, 0.52, 0.29, `${caseId} call 1 (recovered)`);
      } else if (caseId === 'empty-history-cached') {
        assert.strictEqual(candidateOut.calls[0].forecast, null, 'Empty history must yield null forecast');
        assert.strictEqual(candidateOut.calls[1].forecast, null, 'Cached empty history must yield null forecast');
      } else {
        assert.fail(`No portable lifecycle oracle defined for case ${caseId}`);
      }
    }
  }
});

test('compiler ancestry traversal and symlink safety verification', (t) => {
  const { verifyPathWithinWorkspace, safeWriteFile } = require('../compile_replay.cjs');

  assert.doesNotThrow(() => verifyPathWithinWorkspace(path.join(WORKSPACE_ROOT, 'build')));
  assert.doesNotThrow(() => verifyPathWithinWorkspace(path.join(WORKSPACE_ROOT, 'research', 'prediction_eval')));

  assert.throws(() => verifyPathWithinWorkspace(path.join(WORKSPACE_ROOT, '..', 'escaped')), /resolves outside workspace/);
  assert.throws(() => verifyPathWithinWorkspace('C:\\Windows\\System32'), /resolves outside workspace/);

  const testRunId = Date.now().toString(36) + '-' + crypto.randomBytes(4).toString('hex');
  const safeWorkDir = path.join(TEST_WORK_DIR, `safe-traversal-${testRunId}`);
  fs.mkdirSync(safeWorkDir, { recursive: true });

  const testSafePath = path.join(safeWorkDir, 'safe-write-test.txt');
  safeWriteFile(testSafePath, 'hello safe write');
  assert.strictEqual(fs.readFileSync(testSafePath, 'utf8'), 'hello safe write');

  assert.throws(() => safeWriteFile(path.join(WORKSPACE_ROOT, '..', 'evil.txt'), 'data'), /resolves outside workspace/);

  // Symlink write rejection check using fresh per-invocation owned paths
  const probeSrc = path.join(safeWorkDir, 'symlink_probe_src.txt');
  const probeDst = path.join(safeWorkDir, 'symlink_probe_dst.txt');
  fs.writeFileSync(probeSrc, 'test data');

  let symlinksSupported = false;
  try {
    fs.symlinkSync(probeSrc, probeDst, 'file');
    symlinksSupported = true;
  } catch (err) {
    if (err.code === 'EPERM' || err.code === 'ENOSYS') {
      t.skip(`Symlink creation unsupported on this OS / environment (code: ${err.code}, syscall: ${err.syscall})`);
      return;
    }
    throw new Error(`Unexpected error during symlink test setup: ${err.message} (code: ${err.code})`);
  }

  assert.ok(symlinksSupported, 'Symlink must be supported to execute decisive assertions');
  assert.ok(fs.lstatSync(probeDst).isSymbolicLink(), 'Target must be an actual symbolic link');

  assert.throws(() => safeWriteFile(probeDst, 'overwrite via link'), /or its ancestor is a symbolic link/);

  process.stdout.write('[ASSERTION-EXECUTED] compiler ancestry traversal and symlink safety verification\n');
});

test('compiler guard admits a nested checkout and still refuses escapes and links', (t) => {
  // A byte-identical copy of the current compiler, loaded from a fake checkout nested
  // below ordinary scratch directories, derives its own WORKSPACE_ROOT there. This
  // exercises the real guard with parents above the root that are not volume roots.
  const sourceCompiler = path.join(WORKSPACE_ROOT, 'research', 'prediction_eval', 'compile_replay.cjs');
  const fixtureRoot = path.join(TEST_WORK_DIR, 'nested');
  const checkoutRoot = path.join(fixtureRoot, 'parent', 'NiveshPilot');
  const outsideDir = path.join(fixtureRoot, 'outside-checkout');
  const copyPath = path.join(checkoutRoot, 'research', 'prediction_eval', 'compile_replay.cjs');
  ensureOwnedScratchDir(path.dirname(copyPath));
  ensureOwnedScratchDir(outsideDir);
  fs.copyFileSync(sourceCompiler, copyPath, fs.constants.COPYFILE_EXCL);
  assert.strictEqual(sha256File(copyPath), sha256File(sourceCompiler), 'Fixture compiler must be a byte-identical copy');
  const nested = require(copyPath);

  // Legitimate paths: the default candidate output (missing), an existing valid owned
  // output tree, and a new file written through safeWriteFile.
  const defaultOut = path.join(checkoutRoot, 'build', 'prediction-eval', 'candidate');
  assert.strictEqual(nested.verifyPathWithinWorkspace(defaultOut), defaultOut);

  const existingOut = path.join(checkoutRoot, 'build', 'prediction-eval', 'existing');
  const owned = [...nested.getExpectedSets('candidate').emitted_files, 'package.json', 'build-manifest.json'];
  for (const rel of owned) {
    const full = path.join(existingOut, rel);
    ensureOwnedScratchDir(path.dirname(full));
    fs.writeFileSync(full, `sentinel:${rel}`, { flag: 'wx' });
  }
  assert.doesNotThrow(() => nested.preflightOutputDirectory(existingOut, owned));
  assertOwnedSentinels(existingOut, owned);

  const safeTarget = path.join(checkoutRoot, 'build', 'safe-write.txt');
  nested.safeWriteFile(safeTarget, 'nested safe write');
  assert.strictEqual(fs.readFileSync(safeTarget, 'utf8'), 'nested safe write');

  // Escapes stay refused, including an existing owned directory outside the fake checkout
  assert.throws(() => nested.verifyPathWithinWorkspace(path.join(checkoutRoot, '..', 'escaped')), /resolves outside workspace/);
  assert.throws(() => nested.verifyPathWithinWorkspace(outsideDir), /resolves outside workspace/);
  const outsideTarget = path.join(outsideDir, 'escape.txt');
  assert.throws(() => nested.safeWriteFile(outsideTarget, 'data'), /resolves outside workspace/);
  assert.strictEqual(fs.existsSync(outsideTarget), false);

  // Unknown output-tree entries stay refused
  const unknownOut = path.join(checkoutRoot, 'build', 'prediction-eval', 'unknown');
  ensureOwnedScratchDir(unknownOut);
  fs.writeFileSync(path.join(unknownOut, 'rogue_output.js'), 'rogue', { flag: 'wx' });
  assert.throws(() => nested.preflightOutputDirectory(unknownOut, owned), /Output directory contains an unexpected file: rogue_output\.js/);

  // Links between fresh scratch paths: a redirected ancestor with a missing leaf (target
  // outside the fake checkout) and a dangling link entry inside an output tree.
  const redirectedOut = path.join(checkoutRoot, 'build', 'prediction-eval', 'redirected');
  const danglingOut = path.join(checkoutRoot, 'build', 'prediction-eval', 'dangling');
  const danglingLink = path.join(danglingOut, 'dangling.js');
  ensureOwnedScratchDir(danglingOut);
  try {
    fs.symlinkSync(outsideDir, redirectedOut, 'dir');
    fs.symlinkSync(path.join(danglingOut, 'missing-target.js'), danglingLink, 'file');
  } catch (err) {
    if (err.code === 'EPERM' || err.code === 'ENOSYS') {
      t.skip(`Symlink creation unsupported on this OS / environment (code: ${err.code}, syscall: ${err.syscall}); non-link cases executed`);
      return;
    }
    throw new Error(`Unexpected error during nested-checkout symlink setup: ${err.message} (code: ${err.code})`);
  }
  assert.ok(fs.lstatSync(redirectedOut).isSymbolicLink(), 'Redirected output must be an actual symbolic link');
  assert.ok(fs.lstatSync(danglingLink).isSymbolicLink(), 'Dangling entry must be an actual symbolic link');

  const missingLeaf = path.join(redirectedOut, 'src', 'engine', 'marketIntelligence', 'forecastCore.js');
  assert.throws(() => nested.verifyPathWithinWorkspace(missingLeaf), /or its ancestor is a symbolic link/);
  assert.throws(() => nested.preflightOutputDirectory(redirectedOut, owned), /or its ancestor is a symbolic link/);
  assert.throws(() => nested.safeWriteFile(path.join(redirectedOut, 'package.json'), 'data'), /or its ancestor is a symbolic link/);
  assert.strictEqual(fs.existsSync(path.join(outsideDir, 'package.json')), false, 'No write may land behind the redirected ancestor');
  assert.throws(() => nested.verifyPathWithinWorkspace(danglingLink), /or its ancestor is a symbolic link/);
  assert.throws(() => nested.preflightOutputDirectory(danglingOut, owned), /Output directory contains a symbolic link entry/);
  process.stdout.write('[ASSERTION-EXECUTED] nested checkout link refusals\n');
});

test('compiler output preflight refusal on redirected ancestors and missing leaves', (t) => {
  const { compile, preflightOutputDirectory, getExpectedSets } = require('../compile_replay.cjs');
  const testRunId = Date.now().toString(36) + '-' + crypto.randomBytes(4).toString('hex');
  const testRoot = path.join(TEST_WORK_DIR, `preflight-redirected-${testRunId}`);
  fs.mkdirSync(testRoot, { recursive: true });

  const realTargetDir = path.join(testRoot, 'real-target-dir');
  const redirectedSrcDir = path.join(testRoot, 'src');
  fs.mkdirSync(realTargetDir, { recursive: true });

  let symlinksSupported = false;
  try {
    fs.symlinkSync(realTargetDir, redirectedSrcDir, 'dir');
    symlinksSupported = true;
  } catch (err) {
    if (err.code === 'EPERM' || err.code === 'ENOSYS') {
      t.skip(`Directory symlink creation unsupported on this OS / environment (code: ${err.code}, syscall: ${err.syscall})`);
      return;
    }
    throw new Error(`Unexpected error during directory symlink test setup: ${err.message} (code: ${err.code})`);
  }

  assert.ok(symlinksSupported, 'Symlink must be supported to execute decisive assertions');
  assert.ok(fs.lstatSync(redirectedSrcDir).isSymbolicLink(), 'redirectedSrcDir must be an actual symbolic link');

  const canaryPath = path.join(testRoot, 'package.json');
  fs.writeFileSync(canaryPath, JSON.stringify({ type: 'commonjs', canary: 'before-preflight' }));

  const { emitted_files } = getExpectedSets('candidate');
  const ownedEmittedFiles = [...emitted_files, 'package.json', 'build-manifest.json'];

  // Notice: src is a symlink, but leaf src/engine/marketIntelligence/forecastCore.js is MISSING!
  // Preflight must reject because ancestor src is a symbolic link!
  assert.throws(
    () => preflightOutputDirectory(testRoot, ownedEmittedFiles),
    /or its ancestor is a symbolic link/
  );

  // Also verify compile() entrypoint rejects through actual caller BEFORE mutation
  assert.throws(
    () => compile('candidate', { outDir: testRoot }),
    /or its ancestor is a symbolic link/
  );

  // Verify canary is completely unmutated (no deletion, no rewrite before refusal)
  assert.strictEqual(
    fs.readFileSync(canaryPath, 'utf8'),
    JSON.stringify({ type: 'commonjs', canary: 'before-preflight' })
  );

  process.stdout.write('[ASSERTION-EXECUTED] compiler output preflight refusal on redirected ancestors and missing leaves\n');
});

test('compiler output preflight refusal on dangling symlink entries', (t) => {
  const { compile, preflightOutputDirectory, verifyPathWithinWorkspace, getExpectedSets } = require('../compile_replay.cjs');
  const testRunId = Date.now().toString(36) + '-' + crypto.randomBytes(4).toString('hex');
  const testRoot = path.join(TEST_WORK_DIR, `preflight-dangling-${testRunId}`);
  fs.mkdirSync(testRoot, { recursive: true });

  const nonExistentPath = path.join(testRoot, 'non-existent-target.txt');
  const danglingLinkPath = path.join(testRoot, 'dangling-link.js');

  let symlinksSupported = false;
  try {
    fs.symlinkSync(nonExistentPath, danglingLinkPath, 'file');
    symlinksSupported = true;
  } catch (err) {
    if (err.code === 'EPERM' || err.code === 'ENOSYS') {
      t.skip(`Dangling symlink creation unsupported on this OS / environment (code: ${err.code}, syscall: ${err.syscall})`);
      return;
    }
    throw new Error(`Unexpected error during dangling symlink test setup: ${err.message} (code: ${err.code})`);
  }

  assert.ok(symlinksSupported, 'Symlink must be supported to execute decisive assertions');
  assert.ok(fs.lstatSync(danglingLinkPath).isSymbolicLink(), 'Target must be an actual symbolic link');

  // Verify existsSync is false on dangling symlink, but verifyPathWithinWorkspace detects it
  assert.strictEqual(fs.existsSync(danglingLinkPath), false);
  assert.throws(
    () => verifyPathWithinWorkspace(danglingLinkPath),
    /or its ancestor is a symbolic link/
  );

  const canaryPath = path.join(testRoot, 'package.json');
  fs.writeFileSync(canaryPath, JSON.stringify({ type: 'commonjs', canary: 'before-dangle-check' }));

  const { emitted_files } = getExpectedSets('candidate');
  const ownedEmittedFiles = [...emitted_files, 'package.json', 'build-manifest.json'];

  assert.throws(
    () => preflightOutputDirectory(testRoot, ownedEmittedFiles),
    /Output directory contains a symbolic link entry/
  );

  assert.throws(
    () => compile('candidate', { outDir: testRoot }),
    /Output directory contains a symbolic link entry/
  );

  // Verify canary is completely unmutated
  assert.strictEqual(
    fs.readFileSync(canaryPath, 'utf8'),
    JSON.stringify({ type: 'commonjs', canary: 'before-dangle-check' })
  );

  process.stdout.write('[ASSERTION-EXECUTED] compiler output preflight refusal on dangling symlink entries\n');
});

test('compiler output preflight refusal on unknown output files and directories', () => {
  const { compile, preflightOutputDirectory, getExpectedSets } = require('../compile_replay.cjs');
  const testRoot = path.join(TEST_WORK_DIR, 'preflight-unknown-state');
  fs.mkdirSync(testRoot, { recursive: true });

  const { emitted_files } = getExpectedSets('candidate');
  const ownedEmittedFiles = [...emitted_files, 'package.json', 'build-manifest.json'];

  const canaryPath = path.join(testRoot, 'package.json');
  fs.writeFileSync(canaryPath, JSON.stringify({ type: 'commonjs', canary: 'safe' }));

  // Case 1: Unknown file in output root
  const unknownFile = path.join(testRoot, 'rogue_output.js');
  fs.writeFileSync(unknownFile, 'console.log("rogue");');

  assert.throws(
    () => preflightOutputDirectory(testRoot, ownedEmittedFiles),
    /Output directory contains an unexpected file: rogue_output\.js/
  );

  assert.throws(
    () => compile('candidate', { outDir: testRoot }),
    /Output directory contains an unexpected file: rogue_output\.js/
  );

  assert.strictEqual(
    fs.readFileSync(canaryPath, 'utf8'),
    JSON.stringify({ type: 'commonjs', canary: 'safe' })
  );
  fs.unlinkSync(unknownFile);

  // Case 2: Unknown directory in output root
  const unknownDir = path.join(testRoot, 'rogue_dir');
  fs.mkdirSync(unknownDir, { recursive: true });

  assert.throws(
    () => preflightOutputDirectory(testRoot, ownedEmittedFiles),
    /Output directory contains an unexpected directory: rogue_dir/
  );

  assert.throws(
    () => compile('candidate', { outDir: testRoot }),
    /Output directory contains an unexpected directory: rogue_dir/
  );

  assert.strictEqual(
    fs.readFileSync(canaryPath, 'utf8'),
    JSON.stringify({ type: 'commonjs', canary: 'safe' })
  );
  fs.rmdirSync(unknownDir);
  fs.unlinkSync(canaryPath);
  fs.rmdirSync(testRoot);
});

test('compiler output preflight passes on valid owned tree without mutation', () => {
  const { preflightOutputDirectory, getExpectedSets } = require('../compile_replay.cjs');
  const testRoot = path.join(TEST_WORK_DIR, 'preflight-valid-state');
  fs.mkdirSync(testRoot, { recursive: true });

  const { emitted_files } = getExpectedSets('candidate');
  const ownedEmittedFiles = [...emitted_files, 'package.json', 'build-manifest.json'];

  // Create valid directory tree with valid owned files
  for (const rel of ownedEmittedFiles) {
    const full = path.join(testRoot, rel);
    fs.mkdirSync(path.dirname(full), { recursive: true });
    fs.writeFileSync(full, 'dummy valid content');
  }

  // Preflight must pass cleanly
  assert.doesNotThrow(() => preflightOutputDirectory(testRoot, ownedEmittedFiles));

  // Verify none of the files were unlinked during preflight
  for (const rel of ownedEmittedFiles) {
    const full = path.join(testRoot, rel);
    assert.strictEqual(fs.readFileSync(full, 'utf8'), 'dummy valid content');
    fs.unlinkSync(full);
  }

  // Clean up directories
  const dirs = [
    path.join(testRoot, 'src', 'engine', 'marketIntelligence', 'providers'),
    path.join(testRoot, 'src', 'engine', 'marketIntelligence'),
    path.join(testRoot, 'src', 'engine'),
    path.join(testRoot, 'src'),
    testRoot
  ];
  for (const d of dirs) {
    try { fs.rmdirSync(d); } catch {}
  }
});

test('wire protocol CLI build manifest freshness and invalidation check', () => {
  const { validateBuildManifest } = require('../compile_replay.cjs');
  const candidateManifestPath = path.join(WORKSPACE_ROOT, 'build', 'prediction-eval', 'candidate', 'build-manifest.json');
  assert.ok(fs.existsSync(candidateManifestPath), 'Candidate manifest must exist');
  const validManifest = JSON.parse(fs.readFileSync(candidateManifestPath, 'utf8'));

  const badEmitManifest = JSON.parse(JSON.stringify(validManifest));
  badEmitManifest.emitted_files[0].sha256 = '0000000000000000000000000000000000000000000000000000000000000000';
  assert.throws(() => validateBuildManifest(badEmitManifest, 'candidate', WORKSPACE_ROOT), /Emitted file hash mismatch/);

  const badExitManifest = JSON.parse(JSON.stringify(validManifest));
  badExitManifest.compiler_exit = 1;
  assert.throws(() => validateBuildManifest(badExitManifest, 'candidate', WORKSPACE_ROOT), /Manifest compiler_exit is nonzero/);

  const badCalcManifest = JSON.parse(JSON.stringify(validManifest));
  badCalcManifest.calculation_id = 'wrong-calculation-id';
  assert.throws(() => validateBuildManifest(badCalcManifest, 'candidate', WORKSPACE_ROOT), /Invalid manifest calculation_id/);
});

// Seeds a VALID owned output layout with sentinel bytes, so output preflight accepts it
// and only the ordering of input checks versus invalidation decides whether it survives.
function seedOwnedOutputLayout(outDir, mode) {
  const { getExpectedSets } = require('../compile_replay.cjs');
  const owned = [...getExpectedSets(mode).emitted_files, 'package.json', 'build-manifest.json'];
  for (const rel of owned) {
    const full = path.join(outDir, rel);
    ensureOwnedScratchDir(path.dirname(full));
    fs.writeFileSync(full, `sentinel:${rel}`, { flag: 'wx' });
  }
  return owned;
}

function assertOwnedSentinels(outDir, owned) {
  for (const rel of owned) {
    assert.strictEqual(fs.readFileSync(path.join(outDir, rel), 'utf8'), `sentinel:${rel}`, `Owned output ${rel} must be untouched`);
  }
}

test('baseline compile refuses changed original sources before touching outputs or launching the compiler', () => {
  const { compile, STARTING_HASHES } = require('../compile_replay.cjs');
  const adapterRel = 'src/engine/marketIntelligence/forecastEngine.ts';
  // Reachability precondition: the extracted adapter no longer matches the original
  assert.notStrictEqual(sha256File(path.join(WORKSPACE_ROOT, adapterRel)), STARTING_HASHES[adapterRel]);

  // Injected fresh scratch output only; the sealed real baseline root is never used here
  const testRoot = path.join(TEST_WORK_DIR, 'baseline-refusal');
  const outDir = path.join(testRoot, 'out');
  const captureDir = path.join(testRoot, 'capture');
  const owned = seedOwnedOutputLayout(outDir, 'baseline');

  const spawnCalls = [];
  const originalSpawnSync = child_process.spawnSync;
  child_process.spawnSync = (...args) => {
    spawnCalls.push(args);
    throw new Error('Compiler launch is forbidden in the baseline refusal test');
  };
  try {
    assert.throws(
      () => compile('baseline', { outDir, childLogDir: captureDir }),
      /Baseline check failed: hash mismatch for src\/engine\/marketIntelligence\/forecastEngine\.ts/
    );
  } finally {
    child_process.spawnSync = originalSpawnSync;
  }

  assert.strictEqual(spawnCalls.length, 0, 'Compiler must not be launched');
  assertOwnedSentinels(outDir, owned);
  assert.strictEqual(fs.existsSync(captureDir), false, 'Capture slot must not be created');
});

test('compiler child capture is opt-in, fresh, confined and fails loudly', (t) => {
  const { compile } = require('../compile_replay.cjs');
  const testRoot = path.join(TEST_WORK_DIR, 'capture-safety');

  const spawnCalls = [];
  const originalSpawnSync = child_process.spawnSync;
  const originalWriteFileSync = fs.writeFileSync;
  // In-memory compiler stand-in: no real tsc launch, so outputs stay in scratch
  child_process.spawnSync = (...args) => {
    spawnCalls.push(args);
    return { status: 0, signal: null, stdout: '', stderr: '' };
  };
  try {
    // 1. Reused capture directory is refused before any output mutation or launch
    const outReuse = path.join(testRoot, 'out-reuse');
    const owned = seedOwnedOutputLayout(outReuse, 'candidate');
    const existingCapture = path.join(testRoot, 'existing-capture');
    ensureOwnedScratchDir(existingCapture);
    assert.throws(
      () => compile('candidate', { outDir: outReuse, childLogDir: existingCapture }),
      /childLogDir already exists; capture requires a fresh directory/
    );

    // 2. A capture slot inside the build output is refused the same way
    assert.throws(
      () => compile('candidate', { outDir: outReuse, childLogDir: path.join(outReuse, 'logs') }),
      /childLogDir must be disjoint from the build output directory/
    );
    assertOwnedSentinels(outReuse, owned);
    assert.strictEqual(spawnCalls.length, 0, 'Refused capture must not launch the compiler');

    // 3. An injected capture write fault fails the compile; no build manifest is produced
    const outFault = path.join(testRoot, 'out-fault');
    const faultCapture = path.join(testRoot, 'fault-capture');
    fs.writeFileSync = (file, ...rest) => {
      if (path.resolve(String(file)).startsWith(faultCapture + path.sep)) {
        const err = new Error('injected capture write fault');
        err.code = 'EIO';
        throw err;
      }
      return originalWriteFileSync(file, ...rest);
    };
    assert.throws(
      () => compile('candidate', { outDir: outFault, childLogDir: faultCapture }),
      /Compiler child capture failed in .*injected capture write fault/
    );
    fs.writeFileSync = originalWriteFileSync;
    assert.strictEqual(spawnCalls.length, 1, 'Capture is written after the single compiler launch');
    assert.strictEqual(fs.existsSync(path.join(outFault, 'build-manifest.json')), false);

    // 4. A capture slot below a linked ancestor is refused (link between fresh scratch paths)
    const outLinked = path.join(testRoot, 'out-linked');
    const ownedLinked = seedOwnedOutputLayout(outLinked, 'candidate');
    const realCaptureParent = path.join(testRoot, 'real-capture-parent');
    const linkedCaptureParent = path.join(testRoot, 'linked-capture-parent');
    ensureOwnedScratchDir(realCaptureParent);
    try {
      fs.symlinkSync(realCaptureParent, linkedCaptureParent, 'dir');
    } catch (err) {
      if (err.code === 'EPERM' || err.code === 'ENOSYS') {
        t.skip(`Directory symlink creation unsupported on this OS / environment (code: ${err.code}, syscall: ${err.syscall}); cases 1-3 executed`);
        return;
      }
      throw new Error(`Unexpected error during capture symlink setup: ${err.message} (code: ${err.code})`);
    }
    assert.ok(fs.lstatSync(linkedCaptureParent).isSymbolicLink(), 'Capture parent must be an actual symbolic link');
    assert.throws(
      () => compile('candidate', { outDir: outLinked, childLogDir: path.join(linkedCaptureParent, 'compiler') }),
      /or its ancestor is a symbolic link/
    );
    assertOwnedSentinels(outLinked, ownedLinked);
    assert.strictEqual(spawnCalls.length, 1, 'Linked capture refusal must not launch the compiler');
    process.stdout.write('[ASSERTION-EXECUTED] compiler child capture linked-ancestor refusal\n');
  } finally {
    child_process.spawnSync = originalSpawnSync;
    fs.writeFileSync = originalWriteFileSync;
  }
});

test('candidate build manifest binds the inherited root tsconfig without changing the baseline set', () => {
  const { validateBuildManifest, getExpectedSets, getFileRecord } = require('../compile_replay.cjs');
  const replayConfig = JSON.parse(fs.readFileSync(path.join(WORKSPACE_ROOT, 'research', 'prediction_eval', 'tsconfig.replay.json'), 'utf8'));
  assert.strictEqual(replayConfig.extends, '../../tsconfig.json', 'Replay config must inherit the root config');

  assert.ok(getExpectedSets('candidate').support_files.includes('tsconfig.json'));
  // Historical baseline canonical set is unchanged so the sealed manifest stays valid
  assert.deepStrictEqual(getExpectedSets('baseline').support_files, [
    'package-lock.json',
    'package.json',
    'research/prediction_eval/compile_replay.cjs',
    'research/prediction_eval/tsconfig.replay.json'
  ]);

  const candidateManifestPath = path.join(WORKSPACE_ROOT, 'build', 'prediction-eval', 'candidate', 'build-manifest.json');
  const manifest = JSON.parse(fs.readFileSync(candidateManifestPath, 'utf8'));
  assert.deepStrictEqual(manifest.support_files.find(r => r.path === 'tsconfig.json'), getFileRecord('tsconfig.json'));
  assert.doesNotThrow(() => validateBuildManifest(manifest, 'candidate', WORKSPACE_ROOT));

  // Owned scratch copies only: the root config itself is never modified
  const scratchDir = path.join(TEST_WORK_DIR, 'inherited-config');
  ensureOwnedScratchDir(scratchDir);

  const stale = JSON.parse(JSON.stringify(manifest));
  stale.support_files.find(r => r.path === 'tsconfig.json').sha256 = '0'.repeat(64);
  const stalePath = path.join(scratchDir, 'stale-root-config-manifest.json');
  fs.writeFileSync(stalePath, JSON.stringify(stale, null, 2) + '\n', { encoding: 'utf8', flag: 'wx' });
  assert.throws(
    () => validateBuildManifest(JSON.parse(fs.readFileSync(stalePath, 'utf8')), 'candidate', WORKSPACE_ROOT),
    /Support file hash mismatch for tsconfig\.json/
  );

  const unbound = JSON.parse(JSON.stringify(manifest));
  unbound.support_files = unbound.support_files.filter(r => r.path !== 'tsconfig.json');
  const unboundPath = path.join(scratchDir, 'unbound-root-config-manifest.json');
  fs.writeFileSync(unboundPath, JSON.stringify(unbound, null, 2) + '\n', { encoding: 'utf8', flag: 'wx' });
  assert.throws(
    () => validateBuildManifest(JSON.parse(fs.readFileSync(unboundPath, 'utf8')), 'candidate', WORKSPACE_ROOT),
    /manifest\.support_files paths do not match canonical set/
  );
});
