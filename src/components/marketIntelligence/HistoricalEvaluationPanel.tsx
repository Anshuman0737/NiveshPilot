import React, { useState, useEffect } from 'react'
import {
  loadHistoricalEvaluation,
  UiDisplayState,
  HistoricalEvaluationSummary,
  DEFAULT_RELEASE_URL,
  DEFAULT_SUMMARY_URL
} from '../../engine/marketIntelligence/historicalEvaluation'

export interface HistoricalEvaluationPanelProps {
  releaseUrl?: string
  summaryUrl?: string
  fetchFn?: typeof fetch
  digestFn?: (bytes: Uint8Array) => Promise<string> | string
  initiallyExpanded?: boolean
  initialDisplayState?: UiDisplayState | null
}

type PartitionView = HistoricalEvaluationSummary['partitions']['test']

// Plain readings of the reasons that leave a scored cohort with points but without intervals.
const INTERVAL_REASON_TEXT: Record<string, string> = {
  insufficient_nominal_blocks: 'the scored cohort has fewer than 10 nominal blocks at every block length',
  non_contiguous_test_cohort: 'admitted gaps leave the scored TEST cohort non-contiguous, so no length is resampled'
}

function intervalReasonLabel(reason: string | null): string {
  if (!reason) return 'Not cleared'
  const text = INTERVAL_REASON_TEXT[reason]
  return text ? `${reason} (${text})` : reason
}

// Requested origins are not scored results: a scored count comes only from scored metrics.
function partitionCountLabel(partition: PartitionView): string {
  const requested = `Requested: ${partition.counts.requested_count} Sessions`
  if (partition.comparison_status === 'scored' && partition.metrics) {
    return `${requested} · Scored: ${partition.metrics.sample_count} Sessions`
  }
  if (partition.comparison_status === 'comparison_unavailable') {
    return `${requested} · Not scored (comparison unavailable)`
  }
  return `${requested} · Not scored (empty cohort)`
}

export const HistoricalEvaluationPanel: React.FC<HistoricalEvaluationPanelProps> = ({
  releaseUrl = DEFAULT_RELEASE_URL,
  summaryUrl = DEFAULT_SUMMARY_URL,
  fetchFn,
  digestFn,
  initiallyExpanded = false,
  initialDisplayState = null
}) => {
  const [isExpanded, setIsExpanded] = useState<boolean>(initiallyExpanded)
  const [displayState, setDisplayState] = useState<UiDisplayState | null>(initialDisplayState)
  const [isLoading, setIsLoading] = useState<boolean>(!initialDisplayState)

  useEffect(() => {
    if (initialDisplayState) {
      setDisplayState(initialDisplayState)
      setIsLoading(false)
      return
    }

    let isCancelled = false
    const abortCtrl = new AbortController()
    setIsLoading(true)

    loadHistoricalEvaluation({
      releaseUrl,
      summaryUrl,
      fetchFn,
      digestFn,
      signal: abortCtrl.signal
    })
      .then((state) => {
        if (!isCancelled) {
          setDisplayState(state)
          setIsLoading(false)
        }
      })
      .catch((err: any) => {
        if (!isCancelled) {
          setDisplayState({
            display_state: 'error',
            can_display_metrics: false,
            reason: err?.message || 'Failed to evaluate historical release',
            summary_data: null
          })
          setIsLoading(false)
        }
      })

    return () => {
      isCancelled = true
      abortCtrl.abort()
    }
  }, [releaseUrl, summaryUrl, fetchFn, digestFn, initialDisplayState])

  const summary: HistoricalEvaluationSummary | null =
    displayState?.display_state === 'displayable' ? displayState.summary_data : null

  return (
    <section
      aria-label="Historical evaluation"
      className="bg-surface-container-low border border-outline-variant/40 rounded p-space-sm sm:p-space-base shadow-sm text-on-surface min-w-0 max-w-full"
    >
      {/* Header & Disclosure Button */}
      <button
        type="button"
        aria-expanded={isExpanded}
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between gap-2 text-left cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-primary rounded py-0.5"
      >
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-primary text-[20px]">history_edu</span>
          <div>
            <h2 className="font-headline-md text-headline-md uppercase tracking-wide text-on-surface">
              Historical Evaluation
            </h2>
            <p className="text-xs text-on-surface-variant font-data-mono-compact">
              NIFTY 50 PRICE INDEX · Fixed 20 Trading Sessions · Retrospective Replay
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="font-label-caps text-label-caps px-2 py-0.5 rounded bg-surface-container-high text-on-surface-variant font-semibold">
            {isExpanded ? 'COLLAPSE' : 'EXPAND'}
          </span>
          <span className="material-symbols-outlined text-on-surface-variant text-[20px]">
            {isExpanded ? 'expand_less' : 'expand_more'}
          </span>
        </div>
      </button>

      {/* Expanded Content Area */}
      {isExpanded && (
        <div className="mt-space-sm pt-space-sm border-t border-outline-variant/30 space-y-space-sm min-w-0 max-w-full">
          {/* Loading State */}
          {isLoading && (
            <div className="p-4 bg-surface-container rounded text-center text-on-surface-variant font-body-compact text-body-compact">
              <span className="material-symbols-outlined animate-spin text-[20px] text-primary align-middle mr-2">
                progress_activity
              </span>
              <span>Verifying release descriptor and cryptographic binding...</span>
            </div>
          )}

          {/* Unavailable State */}
          {!isLoading && displayState?.display_state === 'unavailable' && (
            <div className="p-3 bg-surface-container rounded border border-outline-variant/30 text-on-surface-variant font-body-compact text-xs space-y-1 min-w-0 max-w-full">
              <div className="flex items-center gap-1.5 text-on-surface font-semibold">
                <span className="material-symbols-outlined text-secondary text-[16px]">info</span>
                <span>Historical Evaluation Unavailable</span>
              </div>
              <p>No verified evaluation release is currently published for Nifty 50.</p>
              <p className="text-on-surface-variant/70 font-data-mono-compact break-words break-all [overflow-wrap:anywhere]">
                Status: {displayState.reason}
              </p>
            </div>
          )}

          {/* Error State */}
          {!isLoading && displayState?.display_state === 'error' && (
            <div className="p-3 bg-error/10 rounded border border-error/40 text-error font-body-compact text-xs space-y-1 min-w-0 max-w-full">
              <div className="flex items-center gap-1.5 font-semibold">
                <span className="material-symbols-outlined text-[16px]">error</span>
                <span>Evaluation Verification Error</span>
              </div>
              <p>Evaluation artifact failed strict integrity or schema validation.</p>
              <p className="font-data-mono-compact text-error/90 break-words break-all [overflow-wrap:anywhere]">
                Reason: {displayState.reason}
              </p>
            </div>
          )}

          {/* Unsupported Version State */}
          {!isLoading && displayState?.display_state === 'unsupported_version' && (
            <div className="p-3 bg-surface-container rounded border border-outline-variant/40 text-on-surface-variant font-body-compact text-xs space-y-1 min-w-0 max-w-full">
              <div className="flex items-center gap-1.5 text-on-surface font-semibold">
                <span className="material-symbols-outlined text-secondary text-[16px]">warning</span>
                <span>Unsupported Evaluation Version</span>
              </div>
              <p>The released artifact requires a study protocol version not supported by this interface.</p>
              <p className="font-data-mono-compact text-on-surface-variant/80 break-words break-all [overflow-wrap:anywhere]">
                Reason: {displayState.reason}
              </p>
            </div>
          )}

          {/* Stale State */}
          {!isLoading && displayState?.display_state === 'stale' && (
            <div className="p-3 bg-surface-container rounded border border-outline-variant/40 text-on-surface-variant font-body-compact text-xs space-y-1 min-w-0 max-w-full">
              <div className="flex items-center gap-1.5 text-on-surface font-semibold">
                <span className="material-symbols-outlined text-secondary text-[16px]">update</span>
                <span>Stale Descriptor Binding</span>
              </div>
              <p>Summary artifact identity does not match the active release descriptor.</p>
              <p className="font-data-mono-compact text-on-surface-variant/80 break-words break-all [overflow-wrap:anywhere]">
                Reason: {displayState.reason}
              </p>
            </div>
          )}

          {/* Displayable State */}
          {!isLoading && displayState?.display_state === 'displayable' && summary && (
            <div className="space-y-space-sm text-xs">
              {/* Scope & Attribution Banner */}
              <div className="p-2.5 bg-surface-container rounded border border-outline-variant/30 space-y-1.5">
                {(summary.data_kind === 'synthetic' ||
                  summary.claim_label.includes('SYNTHETIC') ||
                  summary.limitations.some((l) => l.includes('SYNTHETIC'))) && (
                  <div className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-tertiary-container text-on-tertiary-container font-label-caps text-label-caps font-bold">
                    <span className="material-symbols-outlined text-[14px]">science</span>
                    <span>SYNTHETIC TEST FIXTURE / NOT MARKET RESULTS</span>
                  </div>
                )}

                <div className="font-medium text-on-surface">{summary.claim_label}</div>

                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2 pt-1 font-data-mono-compact text-on-surface-variant border-t border-outline-variant/20">
                  <div>
                    <span className="text-on-surface-variant/70 block">SERIES & ASSET</span>
                    <span className="text-on-surface font-semibold">
                      {summary.dataset_attribution.asset_label} ({summary.dataset_attribution.series_id})
                    </span>
                  </div>
                  <div>
                    <span className="text-on-surface-variant/70 block">COVERAGE WINDOW</span>
                    <span className="text-on-surface">
                      {summary.dataset_attribution.coverage_start_date} → {summary.dataset_attribution.coverage_end_date}
                    </span>
                  </div>
                  <div>
                    <span className="text-on-surface-variant/70 block">CHRONOLOGICAL CUTOFF</span>
                    <span className="text-on-surface">
                      Test: {summary.chronological_cutoffs.test_start}
                    </span>
                  </div>
                  <div>
                    <span className="text-on-surface-variant/70 block">FIXED HORIZON</span>
                    <span className="text-on-surface font-semibold">
                      {summary.fixed_definitions.horizon_sessions} Sessions (Class: {summary.fixed_definitions.classes.join(', ')})
                    </span>
                  </div>
                </div>
              </div>

              {/* PRIMARY COMPARISON: TEST PARTITION */}
              <div
                role="region"
                aria-label="Test partition comparison"
                className="p-2.5 bg-surface-container rounded border border-outline-variant/30 space-y-2"
              >
                <div className="flex flex-wrap items-center justify-between gap-1 pb-1 border-b border-outline-variant/20">
                  <span className="font-headline-md text-headline-md uppercase text-on-surface">
                    Out-of-Sample Test Partition Comparison
                  </span>
                  <span className="font-data-mono-compact text-on-surface-variant">
                    {`Cutoff: ${summary.partitions.test.cutoff_date} · ${partitionCountLabel(summary.partitions.test)}`}
                  </span>
                </div>

                {/* Cohort Accounting */}
                <div className="flex flex-wrap items-center gap-3 text-on-surface-variant font-data-mono-compact text-[11px]">
                  <span>Raw: <strong>{summary.partitions.test.counts.raw_partition_count}</strong></span>
                  <span>Eligible: <strong>{summary.partitions.test.counts.eligible_count}</strong></span>
                  <span>Excluded: <strong>{summary.partitions.test.counts.excluded_count}</strong></span>
                  {Object.keys(summary.partitions.test.counts.exclusion_reason_counts).length > 0 && (
                    <span className="text-on-surface-variant/80">
                      Reasons: {Object.entries(summary.partitions.test.counts.exclusion_reason_counts).map(([r, c]) => `${r}: ${c}`).join(', ')}
                    </span>
                  )}
                </div>

                {/* Scored Test Comparator Table */}
                {summary.partitions.test.comparison_status === 'scored' && summary.partitions.test.metrics && (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse font-data-mono-compact text-xs">
                      <thead>
                        <tr className="border-b border-outline-variant/30 text-on-surface-variant">
                          <th className="py-1.5 pr-2 font-semibold">Comparator</th>
                          <th className="py-1.5 px-2 font-semibold text-right">
                            Brier Score <span className="text-[10px] font-normal">(Lower is better)</span>
                          </th>
                          <th className="py-1.5 px-2 font-semibold text-right">
                            Log Loss <span className="text-[10px] font-normal">(Lower is better)</span>
                          </th>
                          <th className="py-1.5 pl-2 font-semibold text-right">
                            Accuracy <span className="text-[10px] font-normal">(Secondary)</span>
                          </th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-outline-variant/20">
                        <tr>
                          <td className="py-1.5 pr-2 text-on-surface font-semibold">
                            Frozen Heuristic Replay
                          </td>
                          <td className="py-1.5 px-2 text-right text-primary font-bold">
                            {summary.partitions.test.metrics.models.heuristic.mean_brier !== null
                              ? summary.partitions.test.metrics.models.heuristic.mean_brier.toFixed(4)
                              : 'N/A'}
                          </td>
                          <td className="py-1.5 px-2 text-right">
                            {summary.partitions.test.metrics.models.heuristic.log_loss_state === 'infinite'
                              ? 'Infinite (zero actual prob)'
                              : summary.partitions.test.metrics.models.heuristic.mean_log_loss !== null
                              ? summary.partitions.test.metrics.models.heuristic.mean_log_loss.toFixed(4)
                              : 'N/A'}
                          </td>
                          <td className="py-1.5 pl-2 text-right text-on-surface-variant">
                            {summary.partitions.test.metrics.models.heuristic.accuracy !== null
                              ? `${(summary.partitions.test.metrics.models.heuristic.accuracy * 100).toFixed(1)}%`
                              : 'N/A'}
                          </td>
                        </tr>

                        <tr>
                          <td className="py-1.5 pr-2 text-on-surface">
                            Frequency Baseline (Laplace)
                          </td>
                          <td className="py-1.5 px-2 text-right">
                            {summary.partitions.test.metrics.models.frequency.mean_brier !== null
                              ? summary.partitions.test.metrics.models.frequency.mean_brier.toFixed(4)
                              : 'N/A'}
                          </td>
                          <td className="py-1.5 px-2 text-right">
                            {summary.partitions.test.metrics.models.frequency.log_loss_state === 'infinite'
                              ? 'Infinite'
                              : summary.partitions.test.metrics.models.frequency.mean_log_loss !== null
                              ? summary.partitions.test.metrics.models.frequency.mean_log_loss.toFixed(4)
                              : 'N/A'}
                          </td>
                          <td className="py-1.5 pl-2 text-right text-on-surface-variant">
                            {summary.partitions.test.metrics.models.frequency.accuracy !== null
                              ? `${(summary.partitions.test.metrics.models.frequency.accuracy * 100).toFixed(1)}%`
                              : 'N/A'}
                          </td>
                        </tr>

                        <tr>
                          <td className="py-1.5 pr-2 text-on-surface">
                            Logistic Baseline (Multinomial)
                          </td>
                          <td className="py-1.5 px-2 text-right">
                            {summary.partitions.test.metrics.models.logistic.mean_brier !== null
                              ? summary.partitions.test.metrics.models.logistic.mean_brier.toFixed(4)
                              : 'N/A'}
                          </td>
                          <td className="py-1.5 px-2 text-right">
                            {summary.partitions.test.metrics.models.logistic.log_loss_state === 'infinite'
                              ? 'Infinite'
                              : summary.partitions.test.metrics.models.logistic.mean_log_loss !== null
                              ? summary.partitions.test.metrics.models.logistic.mean_log_loss.toFixed(4)
                              : 'N/A'}
                          </td>
                          <td className="py-1.5 pl-2 text-right text-on-surface-variant">
                            {summary.partitions.test.metrics.models.logistic.accuracy !== null
                              ? `${(summary.partitions.test.metrics.models.logistic.accuracy * 100).toFixed(1)}%`
                              : 'N/A'}
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                )}

                {/* Comparison Unavailable State */}
                {summary.partitions.test.comparison_status === 'comparison_unavailable' && (
                  <div className="p-2 bg-surface-container-high rounded text-on-surface-variant font-data-mono-compact break-words">
                    Comparison Unavailable:{' '}
                    {summary.partitions.test.comparison_unavailable_reasons.join('; ') || 'Comparator unavailable'}
                  </div>
                )}

                {/* Empty State */}
                {summary.partitions.test.comparison_status === 'empty' && (
                  <div className="p-2 bg-surface-container-high rounded text-on-surface-variant font-data-mono-compact break-words">
                    Empty test cohort (0 eligible sessions).
                  </div>
                )}
              </div>

              {/* STATISTICAL UNCERTAINTY (PAIRED STATIONARY BOOTSTRAP) */}
              <div
                role="region"
                aria-label="Test partition paired uncertainty"
                className="p-2.5 bg-surface-container rounded border border-outline-variant/30 space-y-2 min-w-0 max-w-full"
              >
                <div className="flex flex-wrap items-center justify-between gap-1 pb-1 border-b border-outline-variant/20">
                  <span className="font-headline-md text-headline-md uppercase text-on-surface">
                    Paired Stationary Bootstrap Uncertainty (95% Percentile Intervals)
                  </span>
                  <span className="font-data-mono-compact text-on-surface-variant">
                    {summary.uncertainty.replicates.toLocaleString()} Nominal Replicates per Eligible Length · Nominal Coverage {(summary.uncertainty.nominal_coverage * 100).toFixed(0)}%
                  </span>
                </div>

                {summary.partitions.test.comparison_status !== 'scored' ? (
                  <div className="text-on-surface-variant font-data-mono-compact break-words">
                    Intervals unavailable: Test partition comparison is {summary.partitions.test.comparison_status === 'empty' ? 'empty' : 'unavailable'}.
                  </div>
                ) : (
                  <>
                    {/* How to read the differences and intervals. A scored cohort keeps its full-cohort
                        points whether or not any block length cleared its floor. */}
                    <p className="text-on-surface-variant font-body-compact text-xs leading-relaxed">
                      Each value is the TEST-partition mean Brier score difference, heuristic minus the named
                      comparator, paired over the same scored sessions. Negative values favour the heuristic
                      (lower Brier is better); positive values favour the comparator.
                      {summary.uncertainty.block_lengths.some((b) => b.status === 'available')
                        ? ` Brackets show 95% percentile intervals from ${summary.uncertainty.replicates.toLocaleString()} nominal paired stationary-bootstrap replicates per eligible block length; a percentile interval need not contain the point difference.`
                        : ' No block length is eligible, so no interval was resampled.'}
                    </p>

                    {/* Point Differences */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 font-data-mono-compact">
                      {summary.uncertainty.point_differences.map((pd) => {
                        const isFreq = pd.pair_id === 'heuristic_minus_frequency'
                        const isAvailable = isFreq
                          ? (summary.partitions.test.method_states?.frequency?.available ?? true)
                          : (summary.partitions.test.method_states?.logistic?.available ?? true)
                        return (
                          <div key={pd.pair_id} className="p-1.5 bg-surface-container-high rounded flex justify-between">
                            <span className="text-on-surface-variant">
                              {isFreq ? 'Heuristic − Frequency' : 'Heuristic − Logistic'} (mean Brier difference):
                            </span>
                            <span className="font-bold text-on-surface">
                              {isAvailable && pd.point_difference !== null ? pd.point_difference.toFixed(4) : 'N/A'}
                            </span>
                          </div>
                        )
                      })}
                    </div>

                    {summary.uncertainty.status === 'unavailable' && (
                      <div className="text-on-surface-variant font-data-mono-compact break-words">
                        Intervals unavailable: {intervalReasonLabel(summary.uncertainty.reason)}
                      </div>
                    )}

                    {/* Block Lengths Comparison (All 20/40/60 shown together, eligible or not) */}
                    <div className="overflow-x-auto">
                      <table className="w-full text-left border-collapse font-data-mono-compact text-xs">
                        <thead>
                          <tr className="border-b border-outline-variant/30 text-on-surface-variant">
                            <th className="py-1 pr-2 font-semibold">Block Length</th>
                            <th className="py-1 px-2 font-semibold">Status</th>
                            <th className="py-1 px-2 font-semibold text-right">Heuristic − Frequency [95% percentile interval]</th>
                            <th className="py-1 pl-2 font-semibold text-right">Heuristic − Logistic [95% percentile interval]</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-outline-variant/20">
                          {summary.uncertainty.block_lengths.map((b) => {
                            const pFreq = b.pairs.find((p) => p.pair_id === 'heuristic_minus_frequency')
                            const pLog = b.pairs.find((p) => p.pair_id === 'heuristic_minus_logistic')
                            const freqAvail = summary.partitions.test.method_states?.frequency?.available ?? true
                            const logAvail = summary.partitions.test.method_states?.logistic?.available ?? true
                            return (
                              <tr key={b.block_length}>
                                <td className="py-1 pr-2 text-on-surface">
                                  <strong>{b.block_length} Sessions</strong>
                                  <span className="text-[10px] text-on-surface-variant block">{b.label}</span>
                                </td>
                                <td className="py-1 px-2 text-on-surface-variant">
                                  {b.status === 'available' ? (
                                    <span className="text-tertiary font-semibold">Available</span>
                                  ) : (
                                    <span className="break-words">{b.reason || 'Unavailable'}</span>
                                  )}
                                </td>
                                <td className="py-1 px-2 text-right">
                                  {b.status === 'available' && freqAvail && pFreq && pFreq.lower !== null && pFreq.upper !== null
                                    ? `[${pFreq.lower.toFixed(4)}, ${pFreq.upper.toFixed(4)}]`
                                    : 'N/A'}
                                </td>
                                <td className="py-1 pl-2 text-right">
                                  {b.status === 'available' && logAvail && pLog && pLog.lower !== null && pLog.upper !== null
                                    ? `[${pLog.lower.toFixed(4)}, ${pLog.upper.toFixed(4)}]`
                                    : 'N/A'}
                                </td>
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                    </div>
                  </>
                )}
              </div>

              {/* DEVELOPMENT PARTITION (SEPARATELY LABELED · NEVER POOLED) */}
              <div
                role="region"
                aria-label="Development partition reference"
                className="p-2.5 bg-surface-container rounded border border-outline-variant/30 space-y-1"
              >
                <div className="flex flex-wrap items-center justify-between gap-1">
                  <span className="font-headline-md text-headline-md uppercase text-on-surface">
                    Development Partition (Reference Prior · Never Pooled with Test)
                  </span>
                  <span className="font-data-mono-compact text-on-surface-variant">
                    {`Cutoff: ${summary.partitions.development.cutoff_date} · ${partitionCountLabel(summary.partitions.development)}`}
                  </span>
                </div>

                {/* Development Comparison Unavailable State */}
                {summary.partitions.development.comparison_status === 'comparison_unavailable' && (
                  <div className="p-2 bg-surface-container-high rounded text-on-surface-variant font-data-mono-compact break-words">
                    Development Comparison Unavailable:{' '}
                    {summary.partitions.development.comparison_unavailable_reasons.join('; ') || 'Comparator unavailable'}
                  </div>
                )}

                {/* Development Empty State */}
                {summary.partitions.development.comparison_status === 'empty' && (
                  <div className="p-2 bg-surface-container-high rounded text-on-surface-variant font-data-mono-compact break-words">
                    Empty development cohort (0 eligible sessions).
                  </div>
                )}
                {summary.partitions.development.comparison_status === 'scored' && summary.partitions.development.metrics && (
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 font-data-mono-compact pt-1">
                    <div className="p-1.5 bg-surface-container-high rounded flex justify-between">
                      <span className="text-on-surface-variant">Heuristic Brier:</span>
                      <span className="font-bold text-on-surface">
                        {summary.partitions.development.metrics.models.heuristic.mean_brier !== null
                          ? summary.partitions.development.metrics.models.heuristic.mean_brier.toFixed(4)
                          : 'N/A'}
                      </span>
                    </div>
                    <div className="p-1.5 bg-surface-container-high rounded flex justify-between">
                      <span className="text-on-surface-variant">Frequency Brier:</span>
                      <span className="text-on-surface">
                        {summary.partitions.development.metrics.models.frequency.mean_brier !== null
                          ? summary.partitions.development.metrics.models.frequency.mean_brier.toFixed(4)
                          : 'N/A'}
                      </span>
                    </div>
                    <div className="p-1.5 bg-surface-container-high rounded flex justify-between">
                      <span className="text-on-surface-variant">Logistic Brier:</span>
                      <span className="text-on-surface">
                        {summary.partitions.development.metrics.models.logistic.mean_brier !== null
                          ? summary.partitions.development.metrics.models.logistic.mean_brier.toFixed(4)
                          : 'N/A'}
                      </span>
                    </div>
                  </div>
                )}
              </div>

              {/* STUDY LIMITATIONS & GOVERNANCE DISCLOSURES */}
              <div className="p-2.5 bg-surface-container rounded border border-outline-variant/30 space-y-1.5">
                <span className="font-headline-md text-headline-md uppercase text-on-surface block">
                  Methodology Limitations & Disclosures
                </span>
                <ul className="list-disc list-inside space-y-1 text-on-surface-variant font-body-compact text-xs">
                  {summary.limitations.map((limit, idx) => (
                    <li key={idx}>{limit}</li>
                  ))}
                  <li>Frozen historical heuristic replay with event inputs zeroed for offline comparator reference.</li>
                  <li>Offline comparator baselines (uncalibrated Laplace frequency and multinomial logistic) do not constitute trading strategies.</li>
                  <li>Historical evaluation results do not guarantee future forecasting efficacy or trading returns.</li>
                  <li>The test window is not an untouched holdout because the frozen heuristic and protocol were developed with prior knowledge of historical market series.</li>
                  <li>This research disclosure does not infer trading performance, execution slippage, financial suitability, or deployed model improvement.</li>
                </ul>
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
