/**
 * Standalone Node.js Test Suite for Historical Evaluation UI & Validation Pipeline.
 *
 * Requirements:
 * - Uses node:test and node:assert only.
 * - Transpiles the two production TS/TSX modules into NIVESH_UI_TEST_ROOT when it is set,
 *   otherwise into the ignored repository cache node_modules/.cache/nivesh-historical-evaluation-ui,
 *   so the compiled panel resolves React from the repository's own node_modules.
 * - Verifies pure validation, strict JSON decoding, error states, precedence,
 *   and SSR presentation markup. SSR markup checks do not prove browser layout.
 */

const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const crypto = require('node:crypto')
const ts = require('typescript')

// Repository root (research/prediction_eval/tests -> repository) and compiled-output root
const repoRoot = path.resolve(__dirname, '../../..')
const testRoot =
  process.env.NIVESH_UI_TEST_ROOT ||
  path.join(repoRoot, 'node_modules', '.cache', 'nivesh-historical-evaluation-ui')

// 1. Transpile production modules into testRoot
fs.mkdirSync(path.join(testRoot, 'src/engine/marketIntelligence'), { recursive: true })
fs.mkdirSync(path.join(testRoot, 'src/components/marketIntelligence'), { recursive: true })
fs.writeFileSync(path.join(testRoot, 'package.json'), JSON.stringify({ type: 'commonjs' }))

const engineSrcPath = path.join(repoRoot, 'src/engine/marketIntelligence/historicalEvaluation.ts')
const engineOutPath = path.join(testRoot, 'src/engine/marketIntelligence/historicalEvaluation.js')
const engineTs = fs.readFileSync(engineSrcPath, 'utf8')
const engineJs = ts.transpileModule(engineTs, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
    esModuleInterop: true
  }
}).outputText
fs.writeFileSync(engineOutPath, engineJs)

const panelSrcPath = path.join(repoRoot, 'src/components/marketIntelligence/HistoricalEvaluationPanel.tsx')
const panelOutPath = path.join(testRoot, 'src/components/marketIntelligence/HistoricalEvaluationPanel.js')
const panelTs = fs.readFileSync(panelSrcPath, 'utf8')
const panelJs = ts.transpileModule(panelTs, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
    jsx: ts.JsxEmit.React,
    esModuleInterop: true
  }
}).outputText
fs.writeFileSync(panelOutPath, panelJs)

// 2. Require the compiled production modules
const histEval = require(engineOutPath)
const panelMod = require(panelOutPath)
const React = require('react')
const ReactDOMServer = require('react-dom/server')

// Helpers
function computeSha256(buf) {
  return crypto.createHash('sha256').update(buf).digest('hex').toUpperCase()
}

const v2FixturePath = path.join(__dirname, 'fixtures/historical-evaluation.synthetic-v2.json')
const v3FixturePath = path.join(__dirname, 'fixtures/historical-evaluation.synthetic-v3.json')
const v2RawBytes = fs.readFileSync(v2FixturePath)
const v3RawBytes = fs.readFileSync(v3FixturePath)

function makeDescriptor(rawBytes, summaryObj) {
  const hash = computeSha256(rawBytes)
  return {
    schema_version: histEval.SCHEMA_VERSION_RELEASE_DESCRIPTOR,
    run_id: summaryObj.run_id,
    study_id: summaryObj.study_id,
    protocol_id: summaryObj.protocol_id,
    summary_schema_version: summaryObj.schema_version,
    coverage_end_date: summaryObj.dataset_attribution.coverage_end_date,
    summary_bytes: rawBytes.byteLength,
    summary_sha256: hash,
    manifest_bytes: 1024,
    manifest_sha256: hash
  }
}

// Turns a partition into the contract's empty-cohort shape (0 rows, null metrics).
function emptyPartition(partition) {
  partition.counts.raw_partition_count = 0
  partition.counts.eligible_count = 0
  partition.counts.excluded_count = 0
  partition.counts.requested_count = 0
  partition.counts.exclusion_reason_counts = {}
  partition.counts.model_available_counts = { heuristic: 0, frequency: 0, logistic: 0 }
  partition.comparison_status = 'empty'
  partition.metrics.sample_count = 0
  partition.metrics.class_support = [0, 0, 0]
  partition.metrics.status = 'empty'
  for (const m of ['heuristic', 'frequency', 'logistic']) {
    const model = partition.metrics.models[m]
    model.mean_brier = null
    model.mean_log_loss = null
    model.log_loss_state = 'empty'
    model.accuracy = null
    model.confusion = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
    model.class_recall = [null, null, null]
    model.reliability_bins = model.reliability_bins.map((b) => ({
      ...b,
      count: 0,
      mean_probability: null,
      observed_frequency: null
    }))
  }
}

// Uncertainty block for a common reason that makes every block length unavailable at once.
function commonUnavailableUncertainty(uncertainty, reason, n) {
  uncertainty.status = 'unavailable'
  uncertainty.reason = reason
  uncertainty.n = n
  uncertainty.point_differences = [
    { pair_id: 'heuristic_minus_frequency', point_difference: null },
    { pair_id: 'heuristic_minus_logistic', point_difference: null }
  ]
  uncertainty.block_lengths = uncertainty.block_lengths.map((b) => ({
    ...b,
    status: 'unavailable',
    reason,
    pairs: [
      { pair_id: 'heuristic_minus_frequency', lower: null, upper: null },
      { pair_id: 'heuristic_minus_logistic', lower: null, upper: null }
    ]
  }))
}

// TEST comparison unavailable (logistic not converged) with the coherent common uncertainty reason.
// n stays the nonzero requested count; no point estimate is kept.
function makeTestComparisonUnavailable(obj) {
  obj.partitions.test.comparison_status = 'comparison_unavailable'
  obj.partitions.test.comparison_unavailable_reasons = ['logistic: not_converged']
  obj.partitions.test.method_states.logistic.available = false
  obj.partitions.test.method_states.logistic.unavailable_reason = 'not_converged'
  obj.partitions.test.method_states.logistic.failure_stage = 'fit'
  obj.partitions.test.counts.model_available_counts.logistic = 0
  obj.partitions.test.metrics = null
  commonUnavailableUncertainty(obj.uncertainty, 'comparison_unavailable', obj.partitions.test.counts.requested_count)
  return obj
}

// Scored TEST with one admitted missing-VIX gap, derived from v2: the same 3 scored sessions in a
// 4-slot mature span keep their full-cohort points and take non_contiguous_test_cohort intervals.
function makeTestGappedFromV2(obj) {
  const admission = obj.admission_summary
  admission.mature_test_end_index += 1
  admission.mature_test_span_count += 1
  admission.missing_vix_gap_count = 1
  admission.union_gap_count = 1
  const counts = obj.partitions.test.counts
  counts.raw_partition_count += 1
  counts.excluded_count += 1
  counts.exclusion_reason_counts = { ...counts.exclusion_reason_counts, missing_vix: 1 }
  const unc = obj.uncertainty
  unc.mature_span_count = admission.mature_test_span_count
  unc.reason = 'non_contiguous_test_cohort'
  unc.block_lengths = unc.block_lengths.map((b) => ({ ...b, status: 'unavailable', reason: 'non_contiguous_test_cohort' }))
  return obj
}

// Empty TEST derived from v2 that keeps its 3 mature slots, all of them admitted gaps:
// 0 requested = 3 slots - 3 gaps, with the common empty_cohort reason and no point.
function makeTestAllGapFromV2(obj) {
  emptyPartition(obj.partitions.test)
  obj.admission_summary.missing_vix_gap_count = obj.admission_summary.mature_test_span_count
  obj.admission_summary.union_gap_count = obj.admission_summary.mature_test_span_count
  commonUnavailableUncertainty(obj.uncertainty, 'empty_cohort', 0)
  return obj
}

// Empty TEST cohort derived from v2: no mature span and the common empty_cohort reason.
function makeTestEmptyFromV2(obj) {
  emptyPartition(obj.partitions.test)
  obj.admission_summary.mature_test_end_index = obj.admission_summary.mature_test_start_index
  obj.admission_summary.mature_test_span_count = 0
  obj.uncertainty.mature_span_count = 0
  commonUnavailableUncertainty(obj.uncertainty, 'empty_cohort', 0)
  return obj
}

// Runs a modified summary through the production pipeline on its own exact bytes.
async function displayableStateFor(obj) {
  const raw = Buffer.from(JSON.stringify(obj))
  const state = await histEval.evaluateUiDisplayState(raw, makeDescriptor(raw, obj), computeSha256)
  assert.equal(state.display_state, histEval.UI_STATE_DISPLAYABLE, state.reason)
  return state
}

function renderPanel(displayState, initiallyExpanded = true) {
  return ReactDOMServer.renderToStaticMarkup(
    React.createElement(panelMod.HistoricalEvaluationPanel, {
      initialDisplayState: displayState,
      initiallyExpanded
    })
  )
}

// Returns the markup of the single <div> region carrying the given aria-label.
function extractRegion(html, label) {
  const marker = `aria-label="${label}"`
  const at = html.indexOf(marker)
  assert.notEqual(at, -1, `region "${label}" was not rendered`)
  assert.equal(html.indexOf(marker, at + 1), -1, `region "${label}" was rendered more than once`)
  const start = html.lastIndexOf('<div', at)
  const tagRe = /<div\b|<\/div>/g
  tagRe.lastIndex = start
  let depth = 0
  let m
  while ((m = tagRe.exec(html)) !== null) {
    depth += m[0] === '</div>' ? -1 : 1
    if (depth === 0) return html.slice(start, m.index + '</div>'.length)
  }
  throw new Error(`unterminated region "${label}"`)
}

// Visible text with tags removed and whitespace collapsed.
function textOf(html) {
  return html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
}

// Cell texts of the single body row (<tr> without attributes) whose markup contains rowLabel.
function rowCells(regionHtml, rowLabel) {
  const rows = (regionHtml.match(/<tr>[\s\S]*?<\/tr>/g) || []).filter((r) => r.includes(rowLabel))
  assert.equal(rows.length, 1, `expected exactly one row containing "${rowLabel}"`)
  return [...rows[0].matchAll(/<td[^>]*>([\s\S]*?)<\/td>/g)].map((c) => textOf(c[1]))
}

function injectAfterFirst(text, anchor, insertion) {
  const at = text.indexOf(anchor)
  assert.notEqual(at, -1, `anchor ${anchor} not found`)
  return text.slice(0, at + anchor.length) + insertion + text.slice(at + anchor.length)
}

// --- Test Suites ---

test('Strict JSON parsing & encoding rules', async (t) => {
  await t.test('rejects duplicate keys in JSON object', () => {
    assert.throws(
      () => histEval.parseStrictJson('{"a": 1, "a": 2}'),
      /Duplicate JSON key: "a"/
    )
  })

  await t.test('rejects non-finite number tokens', () => {
    assert.throws(() => histEval.parseStrictJson('{"a": NaN}'))
    assert.throws(() => histEval.parseStrictJson('{"a": Infinity}'))
    assert.throws(() => histEval.parseStrictJson('{"a": -Infinity}'))
  })

  await t.test('rejects overflowing floats', () => {
    assert.throws(() => histEval.parseStrictJson('{"a": 1e999}'), /Number out of finite range/)
  })

  await t.test('rejects UTF-8 BOM', () => {
    const bomBytes = Buffer.from([0xef, 0xbb, 0xbf, 0x7b, 0x22, 0x61, 0x22, 0x3a, 0x31, 0x7d])
    assert.throws(
      () => histEval.parseStrictJsonBytes(bomBytes),
      /UTF-8 BOM is not permitted/
    )
  })

  await t.test('rejects invalid UTF-8 byte sequences', () => {
    const invalidBytes = Buffer.from([0xff, 0xff, 0xff])
    assert.throws(
      () => histEval.parseStrictJsonBytes(invalidBytes),
      /Strict JSON is not valid UTF-8/
    )
  })

  await t.test('rejects non-object root', async () => {
    const rawArr = Buffer.from('[1, 2, 3]')
    const desc = {
      schema_version: histEval.SCHEMA_VERSION_RELEASE_DESCRIPTOR,
      run_id: 'run-1',
      study_id: 'study-1',
      protocol_id: histEval.STUDY_PROTOCOL_ID,
      summary_schema_version: histEval.SCHEMA_VERSION_SUMMARY_V3,
      coverage_end_date: '2024-06-28',
      summary_bytes: rawArr.byteLength,
      summary_sha256: computeSha256(rawArr),
      manifest_bytes: 100,
      manifest_sha256: computeSha256(rawArr)
    }
    const state = await histEval.evaluateUiDisplayState(rawArr, desc, computeSha256)
    assert.equal(state.display_state, histEval.UI_STATE_ERROR)
    assert.match(state.reason, /Summary root is not a JSON object/)
  })
})

test('JSON own-key preservation: raw "__proto__" members stay visible to closed schemas', async (t) => {
  const v3Text = v3RawBytes.toString('utf8')
  const cleanSummary = histEval.parseStrictJsonBytes(v3RawBytes)
  const escapedProto = '"\\u005f\\u005fproto\\u005f\\u005f"' // JSON text spelling of "__proto__" via escapes

  await t.test('literal "__proto__" key is an own enumerable member and leaves prototypes untouched', () => {
    const doc = histEval.parseStrictJson('{"__proto__": {"polluted": true}, "a": 1}')
    assert.deepEqual(Object.keys(doc), ['__proto__', 'a'])
    assert.equal(Object.getPrototypeOf(doc), Object.prototype)
    assert.equal(doc.polluted, undefined)
    assert.equal({}.polluted, undefined)
    assert.equal(Object.getOwnPropertyDescriptor(doc, '__proto__').value.polluted, true)
  })

  await t.test('escaped "__proto__" key spelling decodes to the same own member', () => {
    const doc = histEval.parseStrictJson(`{${escapedProto}: 1}`)
    assert.deepEqual(Object.keys(doc), ['__proto__'])
    assert.equal(Object.getPrototypeOf(doc), Object.prototype)
  })

  await t.test('duplicate "__proto__" members are still rejected, including literal plus escaped spelling', () => {
    assert.throws(() => histEval.parseStrictJson('{"__proto__": 1, "__proto__": 2}'), /Duplicate JSON key: "__proto__"/)
    assert.throws(() => histEval.parseStrictJson(`{"__proto__": 1, ${escapedProto}: 2}`), /Duplicate JSON key: "__proto__"/)
  })

  const summaryCases = [
    {
      name: 'literal key at summary root',
      text: injectAfterFirst(v3Text, '{', '"__proto__": {"schema_version": "nivesh-evaluation-summary-v3"}, '),
      expected: /^Malformed summary: summary: key mismatch; missing=\[\], unknown=\[__proto__\]$/
    },
    {
      name: 'escaped key at summary root',
      text: injectAfterFirst(v3Text, '{', `${escapedProto}: {}, `),
      expected: /^Malformed summary: summary: key mismatch; missing=\[\], unknown=\[__proto__\]$/
    },
    {
      name: 'literal key nested in development counts.model_available_counts',
      text: injectAfterFirst(v3Text, '"model_available_counts": {', '"__proto__": {"heuristic": 200}, '),
      expected: /summary\.partitions\.development\.counts\.model_available_counts: key mismatch; missing=\[\], unknown=\[__proto__\]/
    },
    {
      name: 'escaped key nested in the uncertainty block',
      text: injectAfterFirst(v3Text, '"uncertainty": {', `${escapedProto}: {"status": "available"}, `),
      expected: /uncertainty: key mismatch; missing=\[\], unknown=\[__proto__\]/
    }
  ]

  for (const c of summaryCases) {
    await t.test(`rejects raw summary bytes with ${c.name} although bytes and hash are correctly bound`, async () => {
      const raw = Buffer.from(c.text, 'utf8')
      const desc = makeDescriptor(raw, cleanSummary)
      assert.equal(desc.summary_bytes, raw.byteLength)
      assert.equal(desc.summary_sha256, computeSha256(raw))
      const state = await histEval.evaluateUiDisplayState(raw, desc, computeSha256)
      assert.equal(state.display_state, histEval.UI_STATE_ERROR)
      assert.equal(state.summary_data, null)
      assert.match(state.reason, c.expected)
    })
  }

  await t.test('positive control: the unmodified raw v3 bytes still evaluate to displayable', async () => {
    const state = await histEval.evaluateUiDisplayState(v3RawBytes, makeDescriptor(v3RawBytes, cleanSummary), computeSha256)
    assert.equal(state.display_state, histEval.UI_STATE_DISPLAYABLE)
  })

  const descriptorText = JSON.stringify(makeDescriptor(v3RawBytes, cleanSummary))

  await t.test('rejects a raw release descriptor with a literal or escaped "__proto__" member', () => {
    for (const insertion of ['"__proto__": {"run_id": "run-2026-synthetic-003"}, ', `${escapedProto}: 1, `]) {
      const raw = Buffer.from(injectAfterFirst(descriptorText, '{', insertion), 'utf8')
      assert.throws(
        () => histEval.parseReleaseDescriptor(raw),
        /^Error: descriptor: key mismatch; missing=\[\], unknown=\[__proto__\]$/
      )
    }
    // Positive control: the same descriptor text without the member parses
    assert.equal(histEval.parseReleaseDescriptor(Buffer.from(descriptorText, 'utf8')).run_id, 'run-2026-synthetic-003')
  })

  await t.test('loader reports a "__proto__" descriptor member as a malformed descriptor error', async () => {
    const badDescriptor = Buffer.from(injectAfterFirst(descriptorText, '{', '"__proto__": {}, '), 'utf8')
    const mockFetch = async (url) => {
      if (url.includes('release.json')) return new Response(badDescriptor, { status: 200 })
      return new Response(v3RawBytes, { status: 200 })
    }
    const state = await histEval.loadHistoricalEvaluation({ fetchFn: mockFetch, digestFn: computeSha256 })
    assert.equal(state.display_state, histEval.UI_STATE_ERROR)
    assert.match(state.reason, /^Malformed release descriptor: descriptor: key mismatch; missing=\[\], unknown=\[__proto__\]$/)
  })
})

test('Positive control validation: Synthetic v2 & v3 fixtures', async (t) => {
  await t.test('v2 fixture passes closed validation and evaluates to displayable', async () => {
    const doc = histEval.parseStrictJsonBytes(v2RawBytes)
    const summary = histEval.validateSummaryDocument(doc)
    assert.equal(summary.schema_version, histEval.SCHEMA_VERSION_SUMMARY_V2)
    assert.equal(summary.data_kind, 'synthetic')
    assert.equal(summary.development_status, 'synthetic_development')

    const desc = makeDescriptor(v2RawBytes, summary)
    const state = await histEval.evaluateUiDisplayState(v2RawBytes, desc, computeSha256)
    assert.equal(state.display_state, histEval.UI_STATE_DISPLAYABLE)
    assert.equal(state.can_display_metrics, true)
    assert.notEqual(state.summary_data, null)
    assert.equal(state.summary_data.partitions.test.counts.requested_count, 3)
    assert.equal(state.summary_data.partitions.test.metrics.models.heuristic.mean_brier, 0.24)
  })

  await t.test('v2 scored TEST cohort of 3 contiguous sessions follows the nominal-block floor', () => {
    const summary = histEval.parseStrictJsonBytes(v2RawBytes)
    assert.equal(summary.partitions.test.comparison_status, 'scored')
    assert.equal(summary.admission_summary.mature_test_span_count, 3)
    assert.equal(summary.uncertainty.n, 3)
    assert.equal(summary.uncertainty.mature_span_count, 3)
    assert.equal(summary.uncertainty.status, 'unavailable')
    assert.equal(summary.uncertainty.reason, 'insufficient_nominal_blocks')
    assert.deepEqual(summary.uncertainty.block_lengths.map((b) => [b.block_length, b.status, b.reason]), [
      [20, 'unavailable', 'insufficient_nominal_blocks'],
      [40, 'unavailable', 'insufficient_nominal_blocks'],
      [60, 'unavailable', 'insufficient_nominal_blocks']
    ])
    // Scored, contiguous, below every floor: point differences are kept, intervals are not
    assert.deepEqual(summary.uncertainty.point_differences.map((p) => p.point_difference), [-0.3, 0.18])
  })

  await t.test('v3 fixture passes closed validation and evaluates to displayable', async () => {
    const doc = histEval.parseStrictJsonBytes(v3RawBytes)
    const summary = histEval.validateSummaryDocument(doc)
    assert.equal(summary.schema_version, histEval.SCHEMA_VERSION_SUMMARY_V3)
    assert.equal(summary.data_kind, 'historical')
    assert.equal(summary.development_status, 'retrospective_historical_evaluation')
    assert.match(summary.claim_label, /SYNTHETIC TEST FIXTURE \/ NOT MARKET RESULTS/)

    const desc = makeDescriptor(v3RawBytes, summary)
    const state = await histEval.evaluateUiDisplayState(v3RawBytes, desc, computeSha256)
    assert.equal(state.display_state, histEval.UI_STATE_DISPLAYABLE)
    assert.equal(state.can_display_metrics, true)
    assert.notEqual(state.summary_data, null)
    assert.equal(state.summary_data.partitions.test.counts.requested_count, 800)
    assert.equal(state.summary_data.uncertainty.status, 'available')
    assert.equal(state.summary_data.uncertainty.block_lengths.length, 3)
  })

  await t.test('v3 positive keeps the frozen window: 800 mature slots from T=1400, DEV at T-400, n = TEST requested', () => {
    const summary = histEval.parseStrictJsonBytes(v3RawBytes)
    // Stated oracle, independent of the validator constants
    assert.deepEqual(
      [summary.admission_summary.mature_test_start_index, summary.admission_summary.mature_test_end_index, summary.admission_summary.mature_test_span_count],
      [1400, 2200, 800]
    )
    assert.equal(summary.partitions.test.cutoff_index, 1400)
    assert.equal(summary.partitions.development.cutoff_index, 1000)
    assert.equal(summary.partitions.test.cutoff_date, summary.chronological_cutoffs.test_start)
    assert.equal(summary.partitions.development.cutoff_date, summary.chronological_cutoffs.development_start)
    assert.deepEqual([summary.uncertainty.n, summary.uncertainty.mature_span_count], [800, 800])
    assert.equal(summary.admission_summary.union_gap_count, 0)
  })
})

test('Independent declared support & unsupported versions', async (t) => {
  const summaryObj = histEval.parseStrictJsonBytes(v3RawBytes)

  await t.test('unsupported summary schema version produces unsupported_version', async () => {
    const modified = { ...summaryObj, schema_version: 'nivesh-evaluation-summary-v99' }
    const raw = Buffer.from(JSON.stringify(modified))
    const desc = makeDescriptor(raw, modified)
    desc.summary_schema_version = 'nivesh-evaluation-summary-v99'

    const state = await histEval.evaluateUiDisplayState(raw, desc, computeSha256)
    assert.equal(state.display_state, histEval.UI_STATE_UNSUPPORTED_VERSION)
    assert.equal(state.can_display_metrics, false)
    assert.equal(state.summary_data, null)
    assert.match(state.reason, /Unsupported summary schema/)
  })

  await t.test('unsupported protocol ID produces unsupported_version', async () => {
    const modified = { ...summaryObj, protocol_id: 'nivesh-offline-study-v99' }
    const raw = Buffer.from(JSON.stringify(modified))
    const desc = makeDescriptor(raw, modified)

    const state = await histEval.evaluateUiDisplayState(raw, desc, computeSha256)
    assert.equal(state.display_state, histEval.UI_STATE_UNSUPPORTED_VERSION)
    assert.equal(state.can_display_metrics, false)
    assert.match(state.reason, /Unsupported protocol/)
  })

  await t.test('unsupported descriptor summary schema produces unsupported_version', async () => {
    const desc = makeDescriptor(v3RawBytes, summaryObj)
    desc.summary_schema_version = 'nivesh-evaluation-summary-v99'

    const state = await histEval.evaluateUiDisplayState(v3RawBytes, desc, computeSha256)
    assert.equal(state.display_state, histEval.UI_STATE_UNSUPPORTED_VERSION)
    assert.equal(state.can_display_metrics, false)
    assert.match(state.reason, /Unsupported descriptor schema/)
  })
})

test('Stale identity mismatch discrimination', async (t) => {
  const summaryObj = histEval.parseStrictJsonBytes(v3RawBytes)

  await t.test('run_id mismatch produces stale', async () => {
    const desc = makeDescriptor(v3RawBytes, summaryObj)
    desc.run_id = 'different-run-id'
    const state = await histEval.evaluateUiDisplayState(v3RawBytes, desc, computeSha256)
    assert.equal(state.display_state, histEval.UI_STATE_STALE)
    assert.equal(state.can_display_metrics, false)
    assert.equal(state.summary_data, null)
  })

  await t.test('study_id mismatch produces stale', async () => {
    const desc = makeDescriptor(v3RawBytes, summaryObj)
    desc.study_id = 'different-study-id'
    const state = await histEval.evaluateUiDisplayState(v3RawBytes, desc, computeSha256)
    assert.equal(state.display_state, histEval.UI_STATE_STALE)
    assert.equal(state.can_display_metrics, false)
  })

  await t.test('summary_schema_version mismatch produces stale', async () => {
    const desc = makeDescriptor(v3RawBytes, summaryObj)
    desc.summary_schema_version = histEval.SCHEMA_VERSION_SUMMARY_V2 // supported but mismatched
    const state = await histEval.evaluateUiDisplayState(v3RawBytes, desc, computeSha256)
    assert.equal(state.display_state, histEval.UI_STATE_STALE)
    assert.equal(state.can_display_metrics, false)
  })

  await t.test('coverage_end_date mismatch produces stale', async () => {
    const desc = makeDescriptor(v3RawBytes, summaryObj)
    desc.coverage_end_date = '2025-01-01'
    const state = await histEval.evaluateUiDisplayState(v3RawBytes, desc, computeSha256)
    assert.equal(state.display_state, histEval.UI_STATE_STALE)
    assert.equal(state.can_display_metrics, false)
  })
})

test('Cryptographic & byte-identity checks', async (t) => {
  const summaryObj = histEval.parseStrictJsonBytes(v3RawBytes)

  await t.test('byte-different semantically equivalent reserialization fails digest', async () => {
    // Reformatting JSON changes raw bytes and SHA-256
    const reserialized = Buffer.from(JSON.stringify(summaryObj, null, 4))
    const desc = makeDescriptor(v3RawBytes, summaryObj) // bound to original bytes

    const state = await histEval.evaluateUiDisplayState(reserialized, desc, computeSha256)
    assert.equal(state.display_state, histEval.UI_STATE_ERROR)
    assert.equal(state.can_display_metrics, false)
    assert.match(state.reason, /Byte count mismatch|SHA-256 digest mismatch/)
  })

  await t.test('summary_bytes mismatch produces error', async () => {
    const desc = makeDescriptor(v3RawBytes, summaryObj)
    desc.summary_bytes += 10
    const state = await histEval.evaluateUiDisplayState(v3RawBytes, desc, computeSha256)
    assert.equal(state.display_state, histEval.UI_STATE_ERROR)
    assert.match(state.reason, /Byte count mismatch/)
  })

  await t.test('summary_sha256 mismatch produces error', async () => {
    const desc = makeDescriptor(v3RawBytes, summaryObj)
    desc.summary_sha256 = '0000000000000000000000000000000000000000000000000000000000000000'
    const state = await histEval.evaluateUiDisplayState(v3RawBytes, desc, computeSha256)
    assert.equal(state.display_state, histEval.UI_STATE_ERROR)
    assert.match(state.reason, /SHA-256 digest mismatch/)
  })

  await t.test('failing digestFn produces error and hides metrics', async () => {
    const desc = makeDescriptor(v3RawBytes, summaryObj)
    const failingDigest = () => {
      throw new Error('Crypto hardware device error')
    }
    const state = await histEval.evaluateUiDisplayState(v3RawBytes, desc, failingDigest)
    assert.equal(state.display_state, histEval.UI_STATE_ERROR)
    assert.equal(state.can_display_metrics, false)
    assert.equal(state.summary_data, null)
    assert.match(state.reason, /Digest computation failed: Crypto hardware device error/)
  })
})

test('Closed schema validation rules & nested relations', async (t) => {
  const getCleanV3 = () => JSON.parse(v3RawBytes.toString('utf8'))

  await t.test('rejects missing root key', () => {
    const obj = getCleanV3()
    delete obj.claim_label
    assert.throws(() => histEval.validateSummaryDocument(obj), /missing=\[claim_label\]/)
  })

  await t.test('rejects unexpected extra root key', () => {
    const obj = getCleanV3()
    obj.unauthorized_extra_field = 'forbidden'
    assert.throws(() => histEval.validateSummaryDocument(obj), /unknown=\[unauthorized_extra_field\]/)
  })

  await t.test('rejects counts where excluded != raw - eligible', () => {
    const obj = getCleanV3()
    obj.partitions.test.counts.excluded_count = 100 // raw=820, eligible=800 -> must be 20
    assert.throws(
      () => histEval.validateSummaryDocument(obj),
      /excluded_count must equal raw_partition_count - eligible_count/
    )
  })

  await t.test('rejects counts where requested != eligible', () => {
    const obj = getCleanV3()
    obj.partitions.test.counts.requested_count = 799
    assert.throws(
      () => histEval.validateSummaryDocument(obj),
      /requested_count must equal eligible_count/
    )
  })

  await t.test('rejects exclusion count exceeding excluded_count', () => {
    const obj = getCleanV3()
    obj.partitions.test.counts.exclusion_reason_counts.unknown_outcome = 21 // excluded=20
    assert.throws(
      () => histEval.validateSummaryDocument(obj),
      /reason unknown_outcome count exceeds unique exclusions/
    )
  })

  await t.test('rejects class support not summing to sample_count', () => {
    const obj = getCleanV3()
    obj.partitions.test.metrics.class_support = [280, 240, 279] // sample_count=800
    assert.throws(
      () => histEval.validateSummaryDocument(obj),
      /class support must sum to sample_count/
    )
  })

  await t.test('rejects accuracy that contradicts confusion matrix diagonal', () => {
    const obj = getCleanV3()
    obj.partitions.test.metrics.models.heuristic.accuracy = 0.99 // diagonal sum = 588 / 800 = 0.735
    assert.throws(
      () => histEval.validateSummaryDocument(obj),
      /contradicts counts 588\/800/
    )
  })

  await t.test('rejects Brier score exceeding 2.0 ceiling', () => {
    const obj = getCleanV3()
    obj.partitions.test.metrics.models.heuristic.mean_brier = 2.01
    assert.throws(
      () => histEval.validateSummaryDocument(obj),
      /loss out of range: 2.01/
    )
  })

  await t.test('rejects negative Brier score', () => {
    const obj = getCleanV3()
    obj.partitions.test.metrics.models.heuristic.mean_brier = -0.01
    assert.throws(
      () => histEval.validateSummaryDocument(obj),
      /loss out of range: -0.01/
    )
  })

  await t.test('rejects inverted uncertainty bounds (lower > upper)', () => {
    const obj = getCleanV3()
    obj.uncertainty.block_lengths[0].pairs[0].lower = 0.05
    obj.uncertainty.block_lengths[0].pairs[0].upper = -0.05
    assert.throws(
      () => histEval.validateSummaryDocument(obj),
      /lower bound \(0.05\) exceeds upper bound \(-0.05\)/
    )
  })

  await t.test('rejects non-integer counter value', () => {
    const obj = getCleanV3()
    obj.partitions.test.counts.raw_partition_count = 650.5
    assert.throws(
      () => histEval.validateSummaryDocument(obj),
      /expected non-boolean safe integer, got 650.5/
    )
  })

  await t.test('common unavailable reason mirrors the Python precedence', () => {
    const r = histEval.commonUnavailableReason
    assert.equal(r('comparison_unavailable', 0, 5), 'comparison_unavailable')
    assert.equal(r('comparison_unavailable', 800, 0), 'comparison_unavailable')
    assert.equal(r('empty', 0, 3), 'empty_cohort')
    assert.equal(r('scored', 0, 0), 'empty_cohort')
    assert.equal(r('scored', 3, 1), 'non_contiguous_test_cohort')
    assert.equal(r('scored', 3, 0), null)
  })

  // Each negative keeps every block individually valid, so only the cross-block relation can reject it
  const getCleanV2 = () => JSON.parse(v2RawBytes.toString('utf8'))
  const shiftWindow = (obj, start, devIndex, span = 800) => {
    obj.admission_summary.mature_test_start_index = start
    obj.admission_summary.mature_test_end_index = start + span
    obj.admission_summary.mature_test_span_count = span
    obj.partitions.test.cutoff_index = start
    obj.partitions.development.cutoff_index = devIndex
  }
  const relationCases = [
    ['TEST cutoff date differs from the declared test start', getCleanV3, (o) => { o.partitions.test.cutoff_date = '2023-01-03' }, /summary\.partitions\.test\.cutoff_date: must equal chronological_cutoffs\.test_start/],
    ['DEV cutoff date differs from the declared development start', getCleanV3, (o) => { o.chronological_cutoffs.development_start = '2022-01-04' }, /summary\.partitions\.development\.cutoff_date: must equal chronological_cutoffs\.development_start/],
    ['TEST index differs from the mature start', getCleanV3, (o) => { o.partitions.test.cutoff_index = 1401 }, /summary\.partitions\.test\.cutoff_index: must equal admission_summary\.mature_test_start_index 1400/],
    // Comparison-unavailable base: an available block needs n == span, so n=800 over 801 would fail the block schema first
    ['v3 span other than 800 slots', () => makeTestComparisonUnavailable(getCleanV3()), (o) => { shiftWindow(o, 1400, 1000, 801); o.uncertainty.mature_span_count = 801 }, /v3 requires 800 mature slots, got 801/],
    ['v3 TEST index below the historical minimum', getCleanV3, (o) => shiftWindow(o, 1399, 999), /v3 requires a TEST index of at least 1400, got 1399/],
    ['v3 DEV index other than TEST minus 400', getCleanV3, (o) => shiftWindow(o, 1400, 999), /v3 requires the TEST index minus 400 \(1000\)/],
    ['uncertainty n differs from TEST requested', () => makeTestComparisonUnavailable(getCleanV3()), (o) => { o.uncertainty.n = 0 }, /n and mature_span_count must be the TEST requested_count 800 and the admitted span 800, got 0 and 800/],
    // The added slot is gapped, so requested still equals span minus gaps and the span check runs
    ['uncertainty span differs from the admitted span', getCleanV2, (o) => { Object.assign(o.admission_summary, { mature_test_end_index: 5, mature_test_span_count: 4, missing_vix_gap_count: 1, union_gap_count: 1 }) }, /n and mature_span_count must be the TEST requested_count 3 and the admitted span 4, got 3 and 3/],
    ['scored TEST claiming comparison_unavailable intervals', getCleanV3, (o) => commonUnavailableUncertainty(o.uncertainty, 'comparison_unavailable', 800), /summary\.uncertainty\.reason: must be 'null'/],
    // A schema-valid available block (n == span, points present) on a failed comparator
    ['comparison-unavailable TEST claiming available intervals', () => makeTestComparisonUnavailable(getCleanV3()), (o) => { o.uncertainty = getCleanV3().uncertainty }, /summary\.uncertainty\.reason: must be 'comparison_unavailable'/],
    // Gap counts that do not complement the requested cohort in the admitted span
    ['a gap without a free slot', getCleanV2, (o) => { o.admission_summary.missing_vix_gap_count = 1; o.admission_summary.union_gap_count = 1 }, /summary\.partitions\.test\.counts\.requested_count: must be the admitted span 3 minus union_gap_count 1 \(2\), got 3/],
    ['three scored sessions over four slots with two gaps', () => makeTestGappedFromV2(getCleanV2()), (o) => { o.admission_summary.missing_vix_gap_count = 2; o.admission_summary.union_gap_count = 2 }, /requested_count: must be the admitted span 4 minus union_gap_count 2 \(2\), got 3/],
    ['gapped cohort with its gaps removed', () => makeTestGappedFromV2(getCleanV2()), (o) => { o.admission_summary.missing_vix_gap_count = 0; o.admission_summary.union_gap_count = 0 }, /requested_count: must be the admitted span 4 minus union_gap_count 0 \(4\), got 3/],
    ['zero-origin cohort without its gaps', () => makeTestAllGapFromV2(getCleanV2()), (o) => { o.admission_summary.missing_vix_gap_count = 0; o.admission_summary.union_gap_count = 0 }, /requested_count: must be the admitted span 3 minus union_gap_count 0 \(3\), got 0/],
    ['comparison-unavailable 800 requested with one gap', () => makeTestComparisonUnavailable(getCleanV3()), (o) => { o.admission_summary.missing_vix_gap_count = 1; o.admission_summary.union_gap_count = 1 }, /requested_count: must be the admitted span 800 minus union_gap_count 1 \(799\), got 800/],
    // Signed TEST points against the stated TEST means
    ['a below-floor frequency point with its sign flipped (+0.30 for -0.30)', getCleanV2, (o) => { o.uncertainty.point_differences[0].point_difference = 0.3 }, /summary\.uncertainty\.point_differences: heuristic_minus_frequency 0\.3 differs from the TEST mean Brier difference heuristic - frequency/],
    ['a gapped logistic point with its sign flipped', () => makeTestGappedFromV2(getCleanV2()), (o) => { o.uncertainty.point_differences[1].point_difference = -0.18 }, /heuristic_minus_logistic -0\.18 differs from the TEST mean Brier difference heuristic - logistic/],
    ['an available logistic point off by a hundredth', getCleanV3, (o) => { o.uncertainty.point_differences[1].point_difference = -0.0261 }, /heuristic_minus_logistic -0\.0261 differs/],
    // -0.0511 is the DEV heuristic minus frequency difference (0.2611 - 0.3122); TEST decides
    ['an available frequency point taken from the DEV means', getCleanV3, (o) => { o.uncertainty.point_differences[0].point_difference = -0.0511 }, /heuristic_minus_frequency -0\.0511 differs/],
    ['a point just beyond the shared tolerance', getCleanV2, (o) => { o.uncertainty.point_differences[0].point_difference = -0.3 + 2e-9 }, /heuristic_minus_frequency -0\.29999999\d* differs/]
  ]
  for (const [name, base, mutate, expected] of relationCases) {
    await t.test(`rejects ${name}`, async () => {
      const obj = base()
      histEval.validateSummaryDocument(JSON.parse(JSON.stringify(obj))) // the unmutated base is valid
      mutate(obj)
      assert.throws(() => histEval.validateSummaryDocument(obj), expected)
      // The same bytes, exactly bound, are a verification error at the UI seam
      const raw = Buffer.from(JSON.stringify(obj))
      const state = await histEval.evaluateUiDisplayState(raw, makeDescriptor(raw, obj), computeSha256)
      assert.equal(state.display_state, histEval.UI_STATE_ERROR)
      assert.equal(state.summary_data, null)
      assert.match(state.reason, expected)
    })
  }

  await t.test('paired points match the stated TEST means on both pairs, with signed and near-zero arithmetic, inside one tolerance', () => {
    assert.equal(histEval.PAIRED_POINT_TOLERANCE, 1e-9)
    // Fixture oracles: v2 below floor 0.24 - 0.54 = -0.30 and 0.24 - 0.06 = 0.18; v3 available
    // 0.2854 - 0.3204 = -0.0350 and 0.2854 - 0.3015 = -0.0161; the gapped v2 keeps the v2 points
    for (const [label, doc, points] of [
      ['v2 below floor', getCleanV2(), [-0.3, 0.18]],
      ['v2 gapped', makeTestGappedFromV2(getCleanV2()), [-0.3, 0.18]],
      ['v3 available', getCleanV3(), [-0.035, -0.0161]]
    ]) {
      const summary = histEval.validateSummaryDocument(doc)
      assert.deepEqual(summary.uncertainty.point_differences.map((p) => [p.pair_id, p.point_difference]), [
        ['heuristic_minus_frequency', points[0]],
        ['heuristic_minus_logistic', points[1]]
      ], label)
    }
    // Equal stated means admit a zero or negative-zero point; a point inside the tolerance passes
    for (const [label, mean, point] of [['zero', 0.24, 0], ['negative zero', 0.24, -0], ['inside tolerance', null, -0.3 + 5e-10]]) {
      const doc = getCleanV2()
      if (mean !== null) doc.partitions.test.metrics.models.frequency.mean_brier = mean
      doc.uncertainty.point_differences[0].point_difference = point
      histEval.validateSummaryDocument(doc)
      assert.ok(label)
    }
  })

  await t.test('accepts the coherent controls: gapped v2, all-gap v2, comparison unavailable with 800 or 799 requested, a later v3 window', () => {
    const gapped = histEval.validateSummaryDocument(makeTestGappedFromV2(getCleanV2()))
    assert.equal(gapped.uncertainty.reason, 'non_contiguous_test_cohort')
    assert.deepEqual(gapped.uncertainty.point_differences.map((p) => p.point_difference), [-0.3, 0.18])
    const allGap = histEval.validateSummaryDocument(makeTestAllGapFromV2(getCleanV2()))
    assert.deepEqual([allGap.partitions.test.counts.requested_count, allGap.admission_summary.mature_test_span_count, allGap.admission_summary.union_gap_count, allGap.uncertainty.reason], [0, 3, 3, 'empty_cohort'])
    const unavailable = histEval.validateSummaryDocument(makeTestComparisonUnavailable(getCleanV3()))
    assert.deepEqual([unavailable.uncertainty.n, unavailable.uncertainty.reason], [800, 'comparison_unavailable'])
    // One admitted gap leaves 799 requested origins in the 800 slots; comparison_unavailable still outranks it
    const oneGap = makeTestComparisonUnavailable(getCleanV3())
    Object.assign(oneGap.admission_summary, { missing_vix_gap_count: 1, union_gap_count: 1 })
    Object.assign(oneGap.partitions.test.counts, {
      eligible_count: 799,
      excluded_count: 21,
      requested_count: 799,
      exclusion_reason_counts: { missing_vix: 1, unknown_outcome: 20 },
      model_available_counts: { heuristic: 799, frequency: 799, logistic: 0 }
    })
    oneGap.uncertainty.n = 799
    assert.equal(histEval.validateSummaryDocument(oneGap).uncertainty.reason, 'comparison_unavailable')
    const later = getCleanV3()
    shiftWindow(later, 1401, 1001)
    histEval.validateSummaryDocument(later)
    // v2 keeps the synthetic policy: a 3-slot window from index 1 is not held to the v3 window
    histEval.validateSummaryDocument(getCleanV2())
  })
})

test('Honest representation of special states: Infinite log-loss, empty cohort, comparison unavailable', async (t) => {
  await t.test('infinite log-loss state preserves null mean and flag', async () => {
    const obj = JSON.parse(v3RawBytes.toString('utf8'))
    obj.partitions.test.metrics.models.heuristic.log_loss_state = 'infinite'
    obj.partitions.test.metrics.models.heuristic.mean_log_loss = null
    obj.partitions.test.metrics.models.heuristic.zero_actual_probability_count = 1

    const raw = Buffer.from(JSON.stringify(obj))
    const desc = makeDescriptor(raw, obj)
    const state = await histEval.evaluateUiDisplayState(raw, desc, computeSha256)
    assert.equal(state.display_state, histEval.UI_STATE_DISPLAYABLE)
    assert.equal(state.summary_data.partitions.test.metrics.models.heuristic.log_loss_state, 'infinite')
    assert.equal(state.summary_data.partitions.test.metrics.models.heuristic.mean_log_loss, null)
  })

  await t.test('comparison unavailable partition preserves null metrics, reasons and the common uncertainty reason', async () => {
    const obj = makeTestComparisonUnavailable(JSON.parse(v3RawBytes.toString('utf8')))

    const raw = Buffer.from(JSON.stringify(obj))
    const desc = makeDescriptor(raw, obj)
    const state = await histEval.evaluateUiDisplayState(raw, desc, computeSha256)
    assert.equal(state.display_state, histEval.UI_STATE_DISPLAYABLE)
    assert.equal(state.summary_data.partitions.test.comparison_status, 'comparison_unavailable')
    assert.equal(state.summary_data.partitions.test.metrics, null)
    assert.deepEqual(state.summary_data.partitions.test.comparison_unavailable_reasons, ['logistic: not_converged'])
    assert.equal(state.summary_data.uncertainty.reason, 'comparison_unavailable')
    assert.deepEqual(state.summary_data.uncertainty.point_differences.map((p) => p.point_difference), [null, null])
  })

  await t.test('empty cohort partition preserves 0 counts, null metrics and the empty_cohort reason', async () => {
    const obj = makeTestEmptyFromV2(JSON.parse(v2RawBytes.toString('utf8')))

    const raw = Buffer.from(JSON.stringify(obj))
    const desc = makeDescriptor(raw, obj)
    const state = await histEval.evaluateUiDisplayState(raw, desc, computeSha256)
    assert.equal(state.display_state, histEval.UI_STATE_DISPLAYABLE)
    assert.equal(state.summary_data.partitions.test.comparison_status, 'empty')
    assert.equal(state.summary_data.partitions.test.counts.requested_count, 0)
    assert.equal(state.summary_data.partitions.test.metrics.models.heuristic.mean_brier, null)
    assert.equal(state.summary_data.uncertainty.reason, 'empty_cohort')
    assert.equal(state.summary_data.uncertainty.n, 0)
    assert.deepEqual(state.summary_data.uncertainty.block_lengths.map((b) => b.reason), ['empty_cohort', 'empty_cohort', 'empty_cohort'])
  })
})

test('Loader API: 404, 500, network error, and cancellation', async (t) => {
  await t.test('missing release (404) returns unavailable state', async () => {
    const mockFetch = async (url) => {
      if (url.includes('release.json')) {
        return new Response('Not Found', { status: 404 })
      }
      return new Response('{}', { status: 200 })
    }
    const state = await histEval.loadHistoricalEvaluation({ fetchFn: mockFetch })
    assert.equal(state.display_state, histEval.UI_STATE_UNAVAILABLE)
    assert.equal(state.can_display_metrics, false)
    assert.match(state.reason, /404/)
  })

  await t.test('HTTP 500 on summary returns error state', async () => {
    const desc = makeDescriptor(v3RawBytes, histEval.parseStrictJsonBytes(v3RawBytes))
    const descBytes = Buffer.from(JSON.stringify(desc))

    const mockFetch = async (url) => {
      if (url.includes('release.json')) {
        return new Response(descBytes, { status: 200 })
      }
      return new Response('Server Error', { status: 500 })
    }
    const state = await histEval.loadHistoricalEvaluation({ fetchFn: mockFetch })
    assert.equal(state.display_state, histEval.UI_STATE_ERROR)
    assert.equal(state.can_display_metrics, false)
    assert.match(state.reason, /HTTP 500/)
  })

  await t.test('aborted fetch returns error state without unhandled exception', async () => {
    const abortCtrl = new AbortController()
    const mockFetch = async () => {
      const err = new Error('The operation was aborted')
      err.name = 'AbortError'
      throw err
    }
    const state = await histEval.loadHistoricalEvaluation({
      fetchFn: mockFetch,
      signal: abortCtrl.signal
    })
    assert.equal(state.display_state, histEval.UI_STATE_ERROR)
    assert.match(state.reason, /Fetch aborted/)
  })

  const v3Descriptor = Buffer.from(JSON.stringify(makeDescriptor(v3RawBytes, histEval.parseStrictJsonBytes(v3RawBytes))))
  const htmlPage = '<!doctype html><html><head><title>App</title></head><body><div id="root"></div></body></html>'
  const htmlResponse = () => new Response(htmlPage, { status: 200, headers: { 'Content-Type': 'text/html' } })

  // Records each request and answers from the given per-artifact responders
  function recordingFetch(onRelease, onSummary) {
    const calls = []
    const fetchFn = async (url, init) => {
      calls.push({ url, init })
      return url.includes('release.json') ? onRelease() : onSummary()
    }
    return { calls, fetchFn }
  }

  function assertJsonRequest(call, signal) {
    assert.equal(new Headers(call.init.headers).get('accept'), 'application/json')
    assert.ok(call.init.signal instanceof AbortSignal)
    if (signal) assert.equal(call.init.signal, signal)
  }

  await t.test('both artifact requests ask for JSON on one loader-owned signal, and good bytes bind exactly', async () => {
    const caller = new AbortController()
    const { calls, fetchFn } = recordingFetch(
      () => new Response(v3Descriptor, { status: 200 }),
      () => new Response(v3RawBytes, { status: 200 })
    )
    const state = await histEval.loadHistoricalEvaluation({ fetchFn, digestFn: computeSha256, signal: caller.signal })
    assert.equal(state.display_state, histEval.UI_STATE_DISPLAYABLE, state.reason)
    assert.equal(state.summary_data.run_id, 'run-2026-synthetic-003')
    assert.deepEqual(calls.map((c) => c.url), [histEval.DEFAULT_RELEASE_URL, histEval.DEFAULT_SUMMARY_URL])
    assertJsonRequest(calls[0])
    assertJsonRequest(calls[1], calls[0].init.signal)
    // The loader owns its controller: the caller's signal is linked, not passed through
    assert.notEqual(calls[0].init.signal, caller.signal)
    assert.equal(calls[0].init.signal.aborted, false)
  })

  await t.test('one changed summary byte still fails the raw-byte binding after a JSON request', async () => {
    const { calls, fetchFn } = recordingFetch(
      () => new Response(v3Descriptor, { status: 200 }),
      () => new Response(Buffer.concat([v3RawBytes, Buffer.from(' ')]), { status: 200 })
    )
    const state = await histEval.loadHistoricalEvaluation({ fetchFn, digestFn: computeSha256 })
    assert.equal(state.display_state, histEval.UI_STATE_ERROR)
    assert.match(state.reason, /Byte count mismatch/)
    assert.equal(calls.length, 2)
  })

  await t.test('missing release (404) after a JSON request stays unavailable and fetches no summary', async () => {
    const { calls, fetchFn } = recordingFetch(() => new Response('Not Found', { status: 404 }), () => assert.fail('summary must not be fetched'))
    const state = await histEval.loadHistoricalEvaluation({ fetchFn })
    assert.equal(state.display_state, histEval.UI_STATE_UNAVAILABLE)
    assert.match(state.reason, /Release descriptor not found \(404\)/)
    assert.equal(calls.length, 1)
    assertJsonRequest(calls[0])
  })

  await t.test('missing summary (404) behind a valid descriptor stays unavailable', async () => {
    const { calls, fetchFn } = recordingFetch(() => new Response(v3Descriptor, { status: 200 }), () => new Response('Not Found', { status: 404 }))
    const state = await histEval.loadHistoricalEvaluation({ fetchFn })
    assert.equal(state.display_state, histEval.UI_STATE_UNAVAILABLE)
    assert.match(state.reason, /Summary artifact not found \(404\)/)
    assert.equal(calls.length, 2)
    assertJsonRequest(calls[1], calls[0].init.signal)
  })

  await t.test('a successful HTML descriptor response is a verification error, not unavailable', async () => {
    const { fetchFn } = recordingFetch(htmlResponse, () => assert.fail('summary must not be fetched'))
    const state = await histEval.loadHistoricalEvaluation({ fetchFn })
    assert.equal(state.display_state, histEval.UI_STATE_ERROR)
    assert.equal(state.summary_data, null)
    assert.match(state.reason, /^Malformed release descriptor: /)
  })

  await t.test('a successful HTML summary response is a verification error, not unavailable', async () => {
    const { fetchFn } = recordingFetch(() => new Response(v3Descriptor, { status: 200 }), htmlResponse)
    const state = await histEval.loadHistoricalEvaluation({ fetchFn, digestFn: computeSha256 })
    assert.equal(state.display_state, histEval.UI_STATE_ERROR)
    assert.equal(state.summary_data, null)
    assert.match(state.reason, /^Malformed summary JSON: /)
  })

  // A request that settles only when its own signal aborts
  function hangingFetch(calls, onStart) {
    return (url, init) =>
      new Promise((resolve, reject) => {
        calls.push({ url, init })
        init.signal.addEventListener('abort', () => {
          const err = new Error('The operation was aborted')
          err.name = 'AbortError'
          reject(err)
        }, { once: true })
        if (onStart) onStart()
      })
  }

  await t.test('caller abort reaches the owned signal of the JSON request', async () => {
    const caller = new AbortController()
    const calls = []
    const state = await histEval.loadHistoricalEvaluation({ fetchFn: hangingFetch(calls, () => caller.abort()), signal: caller.signal })
    assert.equal(state.display_state, histEval.UI_STATE_ERROR)
    assert.match(state.reason, /^Fetch aborted: /)
    assert.equal(calls.length, 1)
    assertJsonRequest(calls[0])
    assert.notEqual(calls[0].init.signal, caller.signal)
    assert.equal(calls[0].init.signal.aborted, true)
  })

  await t.test('timeout aborts the owned signal of the JSON request', async () => {
    const calls = []
    const state = await histEval.loadHistoricalEvaluation({ fetchFn: hangingFetch(calls), timeoutMs: 5 })
    assert.equal(state.display_state, histEval.UI_STATE_ERROR)
    assert.match(state.reason, /^Fetch aborted: /)
    assert.equal(calls.length, 1)
    assertJsonRequest(calls[0])
    assert.equal(calls[0].init.signal.aborted, true)
  })
})

test('React Presentation Component SSR Render Tests', async (t) => {
  const summaryObj = histEval.parseStrictJsonBytes(v3RawBytes)
  const verifiedV3 = {
    display_state: histEval.UI_STATE_DISPLAYABLE,
    can_display_metrics: true,
    reason: 'Verified',
    summary_data: summaryObj
  }

  await t.test('renders displayable state with complete table, CIs, and disclosure semantics', () => {
    const html = renderPanel(verifiedV3)

    // Check accessible disclosure button
    assert.match(html, /aria-expanded="true"/)
    assert.match(html, /Historical Evaluation/)
    assert.match(html, /NIFTY 50 PRICE INDEX · Fixed 20 Trading Sessions/)

    // Check synthetic notice badge
    assert.match(html, /SYNTHETIC TEST FIXTURE \/ NOT MARKET RESULTS/)

    // Check primary test comparison table labels
    assert.match(html, /Out-of-Sample Test Partition Comparison/)
    assert.match(html, /Brier Score/)
    assert.match(html, /Log Loss/)
    assert.match(html, /Lower is better/)
    assert.match(html, /Frozen Heuristic Replay/)

    // Check 95% bootstrap uncertainty section
    assert.match(html, /Paired Stationary Bootstrap Uncertainty/)
    assert.match(html, /10,000 Nominal Replicates per Eligible Length/)

    // Check development partition separately labeled
    assert.match(html, /Development Partition \(Reference Prior · Never Pooled with Test\)/)

    // Check methodology limitations & disclosures
    assert.match(html, /Methodology Limitations &amp; Disclosures/)
    assert.match(html, /Frozen historical heuristic replay with event inputs zeroed/)
  })

  await t.test('TEST comparator rows carry exactly the TEST Brier, log loss and accuracy values', () => {
    const testRegion = extractRegion(renderPanel(verifiedV3), 'Test partition comparison')
    // Accuracies are the 800-row diagonals 588, 504 and 568 over 800
    assert.deepEqual(rowCells(testRegion, 'Frozen Heuristic Replay'), ['Frozen Heuristic Replay', '0.2854', '0.5218', '73.5%'])
    assert.deepEqual(rowCells(testRegion, 'Frequency Baseline (Laplace)'), ['Frequency Baseline (Laplace)', '0.3204', '0.6542', '63.0%'])
    assert.deepEqual(rowCells(testRegion, 'Logistic Baseline (Multinomial)'), ['Logistic Baseline (Multinomial)', '0.3015', '0.5891', '71.0%'])
    // The distinct DEV reference values must not appear inside the TEST comparison
    assert.doesNotMatch(testRegion, /0\.2611|0\.3122|0\.2978|0\.4987|0\.6411|0\.5733/)
  })

  await t.test('DEV reference card carries exactly the DEV Brier values and none of the TEST values', () => {
    const devRegion = extractRegion(renderPanel(verifiedV3), 'Development partition reference')
    const devText = textOf(devRegion)
    assert.match(devText, /Heuristic Brier: 0\.2611/)
    assert.match(devText, /Frequency Brier: 0\.3122/)
    assert.match(devText, /Logistic Brier: 0\.2978/)
    assert.match(devText, /Cutoff: 2022-01-03 · Requested: 200 Sessions · Scored: 200 Sessions/)
    assert.doesNotMatch(devRegion, /0\.2854|0\.3204|0\.3015/)
    // Scored DEV control: neither non-scored DEV message is shown
    assert.doesNotMatch(devText, /Development Comparison Unavailable|Empty development cohort/)
  })

  await t.test('scored TEST header reports requested origins and the scored count from scored metrics', () => {
    const testText = textOf(extractRegion(renderPanel(verifiedV3), 'Test partition comparison'))
    assert.match(testText, /Cutoff: 2023-01-02 · Requested: 800 Sessions · Scored: 800 Sessions/)
  })

  await t.test('comparison-unavailable TEST header labels requested origins without claiming any scored sessions', async () => {
    const state = await displayableStateFor(makeTestComparisonUnavailable(JSON.parse(v3RawBytes.toString('utf8'))))
    const html = renderPanel(state)
    const testRegion = extractRegion(html, 'Test partition comparison')
    const testText = textOf(testRegion)
    assert.match(testText, /Cutoff: 2023-01-02 · Requested: 800 Sessions · Not scored \(comparison unavailable\)/)
    assert.doesNotMatch(testText, /Scored: \d/)
    assert.match(testText, /Comparison Unavailable: logistic: not_converged/)
    assert.doesNotMatch(testRegion, /Frozen Heuristic Replay|0\.2854/)
    // A failed comparator keeps no point estimate: no difference rows and no numbers
    const uncText = textOf(extractRegion(html, 'Test partition paired uncertainty'))
    assert.match(uncText, /Intervals unavailable: Test partition comparison is unavailable\./)
    assert.doesNotMatch(uncText, /mean Brier difference|-0\.0350|-0\.0161|\[-?\d+\.\d/)
  })

  await t.test('empty TEST header reports zero requested origins and no scored sessions', async () => {
    const state = await displayableStateFor(makeTestEmptyFromV2(JSON.parse(v2RawBytes.toString('utf8'))))
    const html = renderPanel(state)
    const testText = textOf(extractRegion(html, 'Test partition comparison'))
    assert.match(testText, /Requested: 0 Sessions · Not scored \(empty cohort\)/)
    assert.doesNotMatch(testText, /Scored: \d/)
    assert.match(testText, /Empty test cohort \(0 eligible sessions\)\./)
    const uncText = textOf(extractRegion(html, 'Test partition paired uncertainty'))
    assert.match(uncText, /Intervals unavailable: Test partition comparison is empty\./)
    assert.doesNotMatch(uncText, /mean Brier difference|-0\.3000|0\.1800/)
  })

  await t.test('DEV comparison-unavailable state shows its own message and reasons while TEST stays scored', async () => {
    const obj = JSON.parse(v3RawBytes.toString('utf8'))
    const dev = obj.partitions.development
    dev.comparison_status = 'comparison_unavailable'
    dev.comparison_unavailable_reasons = ['logistic: missing_training_classes']
    dev.method_states.logistic = { available: false, unavailable_reason: 'missing_training_classes', failure_stage: null }
    dev.counts.model_available_counts.logistic = 0
    dev.metrics = null
    const html = renderPanel(await displayableStateFor(obj))

    const devText = textOf(extractRegion(html, 'Development partition reference'))
    assert.match(devText, /Development Comparison Unavailable: logistic: missing_training_classes/)
    assert.match(devText, /Requested: 200 Sessions · Not scored \(comparison unavailable\)/)
    assert.doesNotMatch(devText, /Heuristic Brier|Scored: \d|Empty development cohort/)

    const testRegion = extractRegion(html, 'Test partition comparison')
    assert.match(textOf(testRegion), /Requested: 800 Sessions · Scored: 800 Sessions/)
    assert.deepEqual(rowCells(testRegion, 'Frozen Heuristic Replay'), ['Frozen Heuristic Replay', '0.2854', '0.5218', '73.5%'])
    assert.doesNotMatch(testRegion, /missing_training_classes|Development Comparison Unavailable/)
  })

  await t.test('DEV empty state shows its own empty message while TEST stays scored', async () => {
    const obj = JSON.parse(v3RawBytes.toString('utf8'))
    emptyPartition(obj.partitions.development)
    const html = renderPanel(await displayableStateFor(obj))

    const devText = textOf(extractRegion(html, 'Development partition reference'))
    assert.match(devText, /Empty development cohort \(0 eligible sessions\)\./)
    assert.match(devText, /Requested: 0 Sessions · Not scored \(empty cohort\)/)
    assert.doesNotMatch(devText, /Heuristic Brier|Scored: \d|Development Comparison Unavailable/)

    const testRegion = extractRegion(html, 'Test partition comparison')
    assert.match(textOf(testRegion), /Requested: 800 Sessions · Scored: 800 Sessions/)
    assert.doesNotMatch(textOf(testRegion), /Empty test cohort|Empty development cohort/)
  })

  await t.test('uncertainty section explains mean Brier differences, sign and percentile intervals for all three block lengths', () => {
    const region = extractRegion(renderPanel(verifiedV3), 'Test partition paired uncertainty')
    const text = textOf(region)
    assert.match(text, /Paired Stationary Bootstrap Uncertainty \(95% Percentile Intervals\)/)
    assert.match(text, /TEST-partition mean Brier score difference, heuristic minus the named comparator, paired over the same scored sessions/)
    assert.match(text, /Negative values favour the heuristic \(lower Brier is better\); positive values favour the comparator\./)
    assert.match(text, /Brackets show 95% percentile intervals from 10,000 nominal paired stationary-bootstrap replicates per eligible block length; a percentile interval need not contain the point difference\./)
    assert.doesNotMatch(text, /Intervals unavailable|No block length is eligible/)
    assert.match(text, /Heuristic − Frequency \(mean Brier difference\): -0\.0350/)
    assert.match(text, /Heuristic − Logistic \(mean Brier difference\): -0\.0161/)
    assert.match(text, /Heuristic − Frequency \[95% percentile interval\]/)
    const expectedRows = [
      ['20 Sessions', '[-0.0620, -0.0120]', '[-0.0450, 0.0150]'],
      ['40 Sessions', '[-0.0710, -0.0080]', '[-0.0520, 0.0210]'],
      ['60 Sessions', '[-0.0780, -0.0030]', '[-0.0580, 0.0260]']
    ]
    for (const [label, freqInterval, logInterval] of expectedRows) {
      const cells = rowCells(region, label)
      assert.equal(cells[1], 'Available')
      assert.deepEqual(cells.slice(2), [freqInterval, logInterval])
    }
  })

  await t.test('v2 scored TEST below every nominal-block floor shows its unavailable interval reason', async () => {
    const state = await displayableStateFor(histEval.parseStrictJsonBytes(v2RawBytes))
    const html = renderPanel(state)
    const testRegion = extractRegion(html, 'Test partition comparison')
    assert.match(textOf(testRegion), /Requested: 3 Sessions · Scored: 3 Sessions/)
    assert.deepEqual(rowCells(testRegion, 'Frozen Heuristic Replay'), ['Frozen Heuristic Replay', '0.2400', '0.5108', '100.0%'])
    const region = extractRegion(html, 'Test partition paired uncertainty')
    const text = textOf(region)
    assert.match(text, /Intervals unavailable: insufficient_nominal_blocks \(the scored cohort has fewer than 10 nominal blocks at every block length\)/)
    // The full-cohort points are shown with sign and 4 decimals although no interval exists
    assert.match(text, /Heuristic − Frequency \(mean Brier difference\): -0\.3000/)
    assert.match(text, /Heuristic − Logistic \(mean Brier difference\): 0\.1800/)
    assert.match(text, /No block length is eligible, so no interval was resampled\./)
    assert.doesNotMatch(text, /Brackets show|percentile intervals from/)
    for (const label of ['20 Sessions', '40 Sessions', '60 Sessions']) {
      assert.deepEqual(rowCells(region, label).slice(1), ['insufficient_nominal_blocks', 'N/A', 'N/A'])
    }
  })

  await t.test('scored TEST with an admitted gap shows its points and the non-contiguous reason without bounds', async () => {
    const state = await displayableStateFor(makeTestGappedFromV2(histEval.parseStrictJsonBytes(v2RawBytes)))
    const html = renderPanel(state)
    assert.match(textOf(extractRegion(html, 'Test partition comparison')), /Requested: 3 Sessions · Scored: 3 Sessions/)
    const region = extractRegion(html, 'Test partition paired uncertainty')
    const text = textOf(region)
    assert.match(text, /Heuristic − Frequency \(mean Brier difference\): -0\.3000/)
    assert.match(text, /Heuristic − Logistic \(mean Brier difference\): 0\.1800/)
    assert.match(text, /Intervals unavailable: non_contiguous_test_cohort \(admitted gaps leave the scored TEST cohort non-contiguous, so no length is resampled\)/)
    assert.doesNotMatch(text, /Brackets show|\[-?\d+\.\d|Available/)
    for (const label of ['20 Sessions', '40 Sessions', '60 Sessions']) {
      assert.deepEqual(rowCells(region, label).slice(1), ['non_contiguous_test_cohort', 'N/A', 'N/A'])
    }
  })

  await t.test('renders unavailable state with honest explanation and no numbers', () => {
    const html = renderPanel({
      display_state: histEval.UI_STATE_UNAVAILABLE,
      can_display_metrics: false,
      reason: 'No release descriptor found (404)',
      summary_data: null
    })

    assert.match(html, /Historical Evaluation Unavailable/)
    assert.match(html, /No verified evaluation release is currently published for Nifty 50/)
    assert.doesNotMatch(html, /Brier Score/)
    assert.doesNotMatch(html, /0\.2854/)
    assert.doesNotMatch(html, /mean Brier difference|Paired Stationary Bootstrap/)
  })

  await t.test('renders error state with honest failure notice and no numbers', () => {
    const html = renderPanel({
      display_state: histEval.UI_STATE_ERROR,
      can_display_metrics: false,
      reason: 'SHA-256 digest mismatch',
      summary_data: null
    })

    assert.match(html, /Evaluation Verification Error/)
    assert.match(html, /SHA-256 digest mismatch/)
    assert.doesNotMatch(html, /Brier Score/)
  })

  await t.test('renders collapsed state hiding details', () => {
    const html = renderPanel(verifiedV3, false)

    assert.match(html, /aria-expanded="false"/)
    assert.match(html, /EXPAND/)
    assert.doesNotMatch(html, /Out-of-Sample Test Partition Comparison/)
  })

  await t.test('reconciles comparison_unavailable test partition by suppressing test comparator point differences and uncertainty intervals', () => {
    // Intentionally construct an inconsistent object where test comparison is unavailable
    // but uncertainty payload has leftover numeric values
    const inconsistentSummary = JSON.parse(JSON.stringify(summaryObj))
    inconsistentSummary.partitions.test.comparison_status = 'comparison_unavailable'
    inconsistentSummary.partitions.test.comparison_unavailable_reasons = ['logistic: not_converged']
    inconsistentSummary.partitions.test.method_states.logistic.available = false
    inconsistentSummary.partitions.test.metrics = null
    inconsistentSummary.uncertainty.status = 'available'
    inconsistentSummary.uncertainty.point_differences = [
      { pair_id: 'heuristic_minus_frequency', point_difference: -0.035 },
      { pair_id: 'heuristic_minus_logistic', point_difference: -0.0161 }
    ]
    inconsistentSummary.uncertainty.block_lengths = [
      {
        block_length: 20,
        label: 'minimum',
        status: 'available',
        reason: null,
        seed: 20261123,
        pairs: [
          { pair_id: 'heuristic_minus_frequency', lower: -0.062, upper: -0.012 },
          { pair_id: 'heuristic_minus_logistic', lower: -0.045, upper: 0.015 }
        ]
      }
    ]

    const html = renderPanel({
      display_state: histEval.UI_STATE_DISPLAYABLE,
      can_display_metrics: true,
      reason: 'Verified',
      summary_data: inconsistentSummary
    })

    // Assert test comparison unavailable banner is rendered
    assert.match(html, /Comparison Unavailable/)
    assert.match(html, /logistic: not_converged/)
    assert.doesNotMatch(textOf(extractRegion(html, 'Test partition comparison')), /Scored: \d/)

    // Assert presentation invariant: uncertainty intervals are honestly labeled unavailable,
    // NOT displaying numeric test point differences or CI bounds
    assert.match(html, /Intervals unavailable: Test partition comparison is unavailable/)
    assert.doesNotMatch(html, /-0\.0161/)
    assert.doesNotMatch(html, /-0\.0450/)

    // Assert DEV reference metrics remain visible and distinct
    assert.match(html, /Development Partition \(Reference Prior · Never Pooled with Test\)/)
    assert.match(textOf(extractRegion(html, 'Development partition reference')), /Heuristic Brier: 0\.2611/)
  })

  await t.test('markup only: the error reason paragraph keeps both full unbroken digests and carries the wrap utilities (browser layout and overflow are not proven here)', () => {
    const expectedDigest = '0000000000000000000000000000000000000000000000000000000000000000'
    const gotDigest = '2a8f8e1234567890abcdef1234567890abcdef1234567890abcdef1234567890'
    const longHashReason = `Summary SHA-256 mismatch: expected ${expectedDigest}, got ${gotDigest}`
    const html = renderPanel({
      display_state: histEval.UI_STATE_ERROR,
      can_display_metrics: false,
      reason: longHashReason,
      summary_data: null
    })

    const reasonParagraphs = (html.match(/<p\b[^>]*>Reason: [\s\S]*?<\/p>/g) || [])
    assert.equal(reasonParagraphs.length, 1)
    assert.equal(textOf(reasonParagraphs[0]), `Reason: ${longHashReason}`)
    assert.match(reasonParagraphs[0], /break-words break-all/)
  })
})
