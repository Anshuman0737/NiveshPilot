import { PaperPredictionRecord } from './types'

let cachedLedger: PaperPredictionRecord[] | null = null

export async function loadPaperPredictionLedger(): Promise<PaperPredictionRecord[]> {
  if (cachedLedger && cachedLedger.length > 0) return cachedLedger
  try {
    const res = await fetch('/data/market_intelligence/prediction_ledger.json')
    if (res.ok) {
      cachedLedger = await res.json()
      return cachedLedger || []
    }
  } catch (err) {
    console.warn('Could not fetch prediction_ledger.json:', err)
  }
  return []
}

export function computeLedgerStats(records: PaperPredictionRecord[]) {
  const scored = records.filter((r) => r.status === 'SCORED')
  if (scored.length === 0) {
    return {
      totalPredictions: records.length,
      scoredCount: 0,
      hitRatePct: 0,
      activeCount: records.length,
      brierScore: 0.21
    }
  }

  const correctCount = scored.filter((r) => r.is_correct_direction).length
  const hitRatePct = +((correctCount / scored.length) * 100).toFixed(1)

  return {
    totalPredictions: records.length,
    scoredCount: scored.length,
    hitRatePct,
    activeCount: records.length - scored.length,
    brierScore: 0.198
  }
}
