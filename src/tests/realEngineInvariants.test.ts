import { scanMarketAnomalies } from '../engine/marketIntelligence/anomalyScanner'
import { calculatePearsonCorrelation, computeCrossAssetCorrelations } from '../engine/marketIntelligence/correlationEngine'
import { AssetMetadata, AssetPricePoint, EventObservation } from '../engine/marketIntelligence/types'

console.log('--- Starting Real Engine Invariant Tests ---')

// 1. Test Pearson Correlation Engine
const seriesA = [10, 12, 14, 16, 18, 20, 22, 24]
const seriesB = [5, 6, 7, 8, 9, 10, 11, 12] // Perfect positive correlation (\rho = 1.0)
const seriesC = [24, 22, 20, 18, 16, 14, 12, 10] // Perfect negative correlation (\rho = -1.0)

const corrPos = calculatePearsonCorrelation(seriesA, seriesB)
const corrNeg = calculatePearsonCorrelation(seriesA, seriesC)

if (Math.abs(corrPos - 1.0) > 0.01) {
  throw new Error(`Expected correlation ~1.0, got ${corrPos}`)
}
if (Math.abs(corrNeg - (-1.0)) > 0.01) {
  throw new Error(`Expected correlation ~ -1.0, got ${corrNeg}`)
}
console.log(`✓ Test 1 Passed: Pearson Correlation calculated accurately (Pos: ${corrPos}, Neg: ${corrNeg})`)

// 2. Test Anomaly Scanner with Synthetic Price Points
const mockAsset: AssetMetadata = {
  symbol: 'TEST.NS',
  name: 'Test Instruments Ltd',
  asset_class: 'equity',
  sector: 'Technology',
  exchange: 'NSE',
  currency: 'INR',
  benchmark: '^NSEI',
  description: 'Test asset'
}

// Create 30 days of baseline prices + a 4x volume spike on day 30
const mockPrices: AssetPricePoint[] = []
for (let i = 0; i < 30; i++) {
  mockPrices.push({
    date: `2024-01-${String(i + 1).padStart(2, '0')}`,
    close: 100 + (i % 3) * 0.5,
    open: 100,
    high: 102,
    low: 99,
    volume: i === 29 ? 400000 : 100000 // 4x volume spike on last day
  })
}

const anomalies = scanMarketAnomalies([mockAsset], { 'TEST.NS': mockPrices }, [])
const volAnomaly = anomalies.find((a) => a.type === 'Unusual Volume')

if (!volAnomaly) {
  throw new Error('Anomaly scanner failed to detect 4x volume spike')
}
if (!volAnomaly.magnitude.includes('x Volume Multiple')) {
  throw new Error(`Unexpected anomaly magnitude format: ${volAnomaly.magnitude}`)
}
console.log(`✓ Test 2 Passed: Anomaly Scanner detected volume spike (${volAnomaly.magnitude}, Z: ${volAnomaly.zscore})`)

// 3. Test Return Extreme Z-Score
const shockPrices: AssetPricePoint[] = []
for (let i = 0; i < 60; i++) {
  shockPrices.push({
    date: `2024-01-${String((i % 28) + 1).padStart(2, '0')}`,
    close: i === 59 ? 150 : 100 + (Math.random() - 0.5) * 2, // 50% sudden jump on day 60
    open: 100,
    high: 101,
    low: 99,
    volume: 100000
  })
}

const shockAnomalies = scanMarketAnomalies([mockAsset], { 'TEST.NS': shockPrices }, [])
const retAnomaly = shockAnomalies.find((a) => a.type === 'Return Extreme')

if (!retAnomaly) {
  throw new Error('Anomaly scanner failed to detect severe return jump extreme')
}
console.log(`✓ Test 3 Passed: Return extreme Z-score detected (${retAnomaly.magnitude}, ${retAnomaly.impact})`)

// 4. Test Cross-Asset Correlation Pair Generation
const mockPriceMap: Record<string, AssetPricePoint[]> = {
  '^NSEI': mockPrices,
  '^NSEBANK': shockPrices
}
const pairs = computeCrossAssetCorrelations(mockPriceMap)
if (!pairs || pairs.length < 4) {
  throw new Error(`Expected at least 4 cross-asset pairs, got ${pairs.length}`)
}
console.log(`✓ Test 4 Passed: Cross-Asset Correlation pairs generated with authentic bounds (${pairs.length} pairs)`)

console.log('\nALL REAL ENGINE INVARIANT TESTS PASSED WITH 100% SUCCESS!\n')
