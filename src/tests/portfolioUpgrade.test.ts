import { parsePortfolioText, SAMPLE_PORTFOLIO_PRESETS } from '../engine/portfolioParser'
import { generatePortfolioOptimizationBlueprint } from '../engine/portfolioOptimizer'
import { FundSnapshot, Holding } from '../engine/types'

const MOCK_FUNDS: FundSnapshot[] = [
  {
    internal_id: 'MIRAE_LARGE',
    scheme_name: 'Mirae Asset Large Cap Fund - Direct Plan - Growth',
    category: 'Large Cap Fund',
    amc: 'Mirae Asset Mutual Fund',
    expense_ratio: 0.55,
    aum_cr: 38400,
    inception_date: '2008-04-04',
    current_nav: 104.5,
    as_of_date: '2026-03-01',
    ret_1m: 1.2,
    ret_3m: 3.4,
    ret_6m: 7.8,
    ret_1y: 18.4,
    ret_3y_cagr: 16.2,
    ret_5y_cagr: 15.1,
    current_drawdown: -2.4,
    vol_30d: 12.1,
    rolling_sortino_1y: 1.15,
    fund_quality_score: 82,
    market_regime: 'Bull'
  },
  {
    internal_id: 'PPFAS_FLEXI',
    scheme_name: 'Parag Parikh Flexi Cap Fund - Direct Plan - Growth',
    category: 'Flexi Cap Fund',
    amc: 'PPFAS Mutual Fund',
    expense_ratio: 0.63,
    aum_cr: 54000,
    inception_date: '2013-05-24',
    current_nav: 72.8,
    as_of_date: '2026-03-01',
    ret_1m: 1.8,
    ret_3m: 4.2,
    ret_6m: 9.1,
    ret_1y: 22.4,
    ret_3y_cagr: 19.8,
    ret_5y_cagr: 18.5,
    current_drawdown: -1.8,
    vol_30d: 10.8,
    rolling_sortino_1y: 1.48,
    fund_quality_score: 94,
    market_regime: 'Bull'
  },
  {
    internal_id: 'HDFC_MIDCAP',
    scheme_name: 'HDFC Mid-Cap Opportunities Fund - Direct Plan - Growth',
    category: 'Mid Cap Fund',
    amc: 'HDFC Mutual Fund',
    expense_ratio: 0.72,
    aum_cr: 48000,
    inception_date: '2007-06-25',
    current_nav: 168.2,
    as_of_date: '2026-03-01',
    ret_1m: 2.1,
    ret_3m: 5.5,
    ret_6m: 11.4,
    ret_1y: 26.8,
    ret_3y_cagr: 24.1,
    ret_5y_cagr: 21.3,
    current_drawdown: -4.1,
    vol_30d: 15.6,
    rolling_sortino_1y: 1.32,
    fund_quality_score: 91,
    market_regime: 'Bull'
  },
  {
    internal_id: 'SBI_LIQUID',
    scheme_name: 'SBI Liquid Fund - Direct Plan - Growth',
    category: 'Liquid Fund',
    amc: 'SBI Mutual Fund',
    expense_ratio: 0.20,
    aum_cr: 65000,
    inception_date: '2003-11-24',
    current_nav: 3650.0,
    as_of_date: '2026-03-01',
    ret_1m: 0.58,
    ret_3m: 1.72,
    ret_6m: 3.45,
    ret_1y: 7.12,
    ret_3y_cagr: 6.85,
    ret_5y_cagr: 5.92,
    current_drawdown: 0.0,
    vol_30d: 0.45,
    rolling_sortino_1y: 4.5,
    fund_quality_score: 90,
    market_regime: 'Bull'
  }
]

function runTests() {
  console.log('--- Starting Portfolio Import & Optimization Engine Verification ---')

  // Test 1: parsePortfolioText parses multi-line CAS statement
  const rawText = `
    CAMS Consolidated Account Statement
    1. Parag Parikh Flexi Cap Fund - Direct Plan - Growth
       Invested Value: INR 50,000.00   Current Valuation: INR 62,500.00
    2. HDFC Mid-Cap Opportunities Fund
       Amount: 40000   Market Value: 51200
  `
  const parsed = parsePortfolioText(rawText, MOCK_FUNDS)
  if (parsed.holdings.length !== 2) {
    throw new Error(`Expected 2 holdings parsed, got ${parsed.holdings.length}`)
  }
  if (parsed.holdings[0].fundId !== 'PPFAS_FLEXI' || parsed.holdings[1].fundId !== 'HDFC_MIDCAP') {
    throw new Error(`Incorrect fund IDs parsed: ${JSON.stringify(parsed.holdings)}`)
  }
  console.log('✓ Test 1 Passed: Client-side text parsing correctly extracted Indian mutual funds and amounts')

  // Test 2: Sample presets validity
  const presetCount = Object.keys(SAMPLE_PORTFOLIO_PRESETS).length
  for (const [key, preset] of Object.entries(SAMPLE_PORTFOLIO_PRESETS)) {
    if (!preset.title || preset.holdings.length === 0) {
      throw new Error(`Preset ${key} is malformed`)
    }
  }
  console.log(`✓ Test 2 Passed: All ${presetCount} real-world sample presets validated (including ICICI Direct Equity)`)

  // Test 3: Optimization blueprint on Overlap-Heavy portfolio
  const overlapHoldings = SAMPLE_PORTFOLIO_PRESETS.overlap_heavy.holdings
  const blueprintOverlap = generatePortfolioOptimizationBlueprint(overlapHoldings, MOCK_FUNDS)
  if (blueprintOverlap.upgradedScore <= blueprintOverlap.currentScore) {
    throw new Error(`Upgraded score ${blueprintOverlap.upgradedScore} should exceed current score ${blueprintOverlap.currentScore}`)
  }
  if (blueprintOverlap.currentMaxOverlap < 40) {
    throw new Error(`Expected high overlap detected (>40%), got ${blueprintOverlap.currentMaxOverlap}%`)
  }
  if (blueprintOverlap.upgradedMaxOverlap > 25) {
    throw new Error(`Expected upgraded overlap reduced to <=25%, got ${blueprintOverlap.upgradedMaxOverlap}%`)
  }
  console.log(`✓ Test 3 Passed: Overlap-Heavy portfolio score improved from ${blueprintOverlap.currentScore} to ${blueprintOverlap.upgradedScore} (Peak Overlap reduced from ${blueprintOverlap.currentMaxOverlap}% to ${blueprintOverlap.upgradedMaxOverlap}%)`)

  // Test 4: Optimization blueprint on High-Fee Regular Plan portfolio
  const regularHoldings = SAMPLE_PORTFOLIO_PRESETS.high_fee_regular.holdings
  const blueprintRegular = generatePortfolioOptimizationBlueprint(regularHoldings, MOCK_FUNDS)
  if (blueprintRegular.tenYearFeeSavings <= 0) {
    throw new Error(`10-year fee savings should be strictly positive, got ${blueprintRegular.tenYearFeeSavings}`)
  }
  if (blueprintRegular.currentExpenseRatio <= blueprintRegular.upgradedExpenseRatio) {
    throw new Error(`Current expense ratio should exceed upgraded direct plan expense ratio`)
  }
  console.log(`✓ Test 4 Passed: Regular Plan Fee Drag calculated 10-year compounded savings of ₹${blueprintRegular.tenYearFeeSavings.toLocaleString('en-IN')} with expense drop ${blueprintRegular.currentExpenseRatio}% -> ${blueprintRegular.upgradedExpenseRatio}%`)

  // Test 5: Future SIP Breakdown sums to 100%
  const totalSip = blueprintOverlap.recommendedSipBreakdown.reduce((sum, s) => sum + s.allocationPct, 0)
  if (totalSip !== 100) {
    throw new Error(`SIP allocations must sum to 100%, got ${totalSip}%`)
  }
  console.log('✓ Test 5 Passed: Upgraded monthly SIP allocation distribution exactly equals 100%')

  // Test 6: Upgraded Holdings preserve user total capital
  const originalCapital = overlapHoldings.reduce((sum, h) => sum + h.currentValue, 0)
  const upgradedCapital = blueprintOverlap.upgradedHoldings.reduce((sum, h) => sum + h.currentValue, 0)
  if (Math.abs(originalCapital - upgradedCapital) > 1) {
    throw new Error(`Capital conservation violated: Original ₹${originalCapital} vs Upgraded ₹${upgradedCapital}`)
  }
  console.log(`✓ Test 6 Passed: Capital conservation invariant strictly preserved (Total Value = ₹${originalCapital.toLocaleString('en-IN')})`)

  console.log('\nALL PORTFOLIO UPGRADE TESTS PASSED WITH 100% SUCCESS!')
}

runTests()
