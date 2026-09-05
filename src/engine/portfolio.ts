import { Holding } from './types'
import { FUND_TOP_STOCK_HOLDINGS } from './liveMfService'
import { LiveQuote } from './liveMarketService'

export interface OverlapPair {
  fund1: string
  fund2: string
  overlapPct: number
  commonStocks: string[]
  advice: string
}

export interface ConsolidatedStockHolding {
  symbol: string
  name: string
  totalWeightPct: number
  totalValue: number
  heldByFunds: string[]
  sector: string
  livePrice: number
  changePct: number
}

export interface MarketCapBifurcation {
  largeCapPct: number
  midCapPct: number
  smallCapPct: number
  debtPct: number
}

export interface ConsolidatedSector {
  sector: string
  weightPct: number
  value: number
}

export interface PortfolioHealthReport {
  totalInvested: number
  totalCurrentValue: number
  totalGainPct: number
  equityExposurePct: number
  debtExposurePct: number
  categoryBreakdown: { [category: string]: number }
  diversificationStatus: 'Healthy' | 'Concentrated' | 'Over-fragmented'
  diversificationAdvice: string
  overlapPairs: OverlapPair[]
  highOverlapDetected: boolean
  maxCategoryExposure: { category: string; pct: number }
  consolidatedStocks: ConsolidatedStockHolding[]
  marketCapBifurcation: MarketCapBifurcation
  consolidatedSectors: ConsolidatedSector[]
}

// Representative portfolio holdings overlap data for Indian mutual funds
const FUND_TOP_HOLDINGS: { [fundId: string]: { [stock: string]: number } } = {
  MIRAE_LARGE: {
    'HDFC Bank': 9.8,
    'ICICI Bank': 8.5,
    'Reliance Industries': 8.2,
    'Infosys': 6.8,
    'TCS': 4.5,
    'Larsen & Toubro': 4.2,
    'Axis Bank': 3.8,
    'Bharti Airtel': 3.5
  },
  PPFAS_FLEXI: {
    'HDFC Bank': 8.2,
    'Bajaj Holdings': 7.1,
    'Power Grid Corp': 5.8,
    'ITC': 5.5,
    'ICICI Bank': 5.2,
    'Coal India': 4.8,
    'Alphabet (Google)': 4.5,
    'Microsoft': 4.1
  },
  HDFC_MIDCAP: {
    'Indian Hotels': 4.2,
    'Tata Technologies': 3.8,
    'Federal Bank': 3.5,
    'Max Financial': 3.2,
    'Coforge': 3.1,
    'Apollo Tyres': 2.9,
    'Balkrishna Industries': 2.7
  },
  NIPPON_SMALL: {
    'Tube Investments': 3.2,
    'HDFC Bank': 2.8,
    'KPIT Technologies': 2.5,
    'Carborundum Universal': 2.2,
    'Multi Commodity Exchange': 2.1,
    'Apar Industries': 2.0
  },
  ICICI_HYBRID: {
    'ICICI Bank': 6.5,
    'Reliance Industries': 5.8,
    'HDFC Bank': 5.4,
    'Infosys': 4.2,
    'Bharti Airtel': 3.5,
    'GOI Sovereign Bonds': 28.0
  },
  SBI_LIQUID: {
    'Treasury Bills 91D': 35.0,
    'Treasury Bills 182D': 25.0,
    'Commercial Papers (AAA)': 20.0,
    'Triparty Repo (TREPS)': 20.0
  }
}

export function computePortfolioOverlap(fundId1: string, fundId2: string): OverlapPair {
  const h1 = FUND_TOP_HOLDINGS[fundId1] || {}
  const h2 = FUND_TOP_HOLDINGS[fundId2] || {}

  const stocks1 = Object.keys(h1)
  const stocks2 = Object.keys(h2)

  let commonWeight = 0
  const commonStocks: string[] = []

  for (const s of stocks1) {
    if (s in h2) {
      commonStocks.push(s)
      commonWeight += Math.min(h1[s], h2[s]) * 2 // Weight overlap proxy
    }
  }

  // Base overlap baseline if same category
  const baseOverlap = (stocks1.length === 0 || stocks2.length === 0) ? 15 : Math.round(commonWeight)
  const overlapPct = Math.min(85, Math.max(10, baseOverlap))

  let advice = 'Low portfolio overlap. These funds provide complementary sector exposure.'
  if (overlapPct >= 50) {
    advice =
      'High overlap (>50%). Owning both funds provides redundant exposure to the same underlying large-cap companies with duplicate expense ratios.'
  } else if (overlapPct >= 30) {
    advice = 'Moderate overlap. Acceptable if intentional, but watch out for duplicate top weights.'
  }

  return {
    fund1: fundId1,
    fund2: fundId2,
    overlapPct,
    commonStocks,
    advice
  }
}

export function analyzePortfolioHealth(
  holdings: Holding[],
  liveQuotes: LiveQuote[] = []
): PortfolioHealthReport {
  if (holdings.length === 0) {
    return {
      totalInvested: 0,
      totalCurrentValue: 0,
      totalGainPct: 0,
      equityExposurePct: 0,
      debtExposurePct: 0,
      categoryBreakdown: {},
      diversificationStatus: 'Healthy',
      diversificationAdvice: 'Add your holdings to inspect concentration, overlap, and asset allocation.',
      overlapPairs: [],
      highOverlapDetected: false,
      maxCategoryExposure: { category: 'None', pct: 0 },
      consolidatedStocks: [],
      marketCapBifurcation: { largeCapPct: 0, midCapPct: 0, smallCapPct: 0, debtPct: 0 },
      consolidatedSectors: []
    }
  }

  let totalInvested = 0
  let totalCurrentValue = 0
  const catTotals: { [cat: string]: number } = {}

  for (const h of holdings) {
    totalInvested += h.investedAmount
    totalCurrentValue += h.currentValue
    const cat = h.category || 'Equity'
    catTotals[cat] = (catTotals[cat] || 0) + h.currentValue
  }

  const totalGainPct =
    totalInvested > 0 ? Math.round(((totalCurrentValue - totalInvested) / totalInvested) * 1000) / 10 : 0

  const categoryBreakdown: { [category: string]: number } = {}
  let maxCat = 'None'
  let maxCatPct = 0

  for (const [cat, val] of Object.entries(catTotals)) {
    const pct = Math.round((val / totalCurrentValue) * 100)
    categoryBreakdown[cat] = pct
    if (pct > maxCatPct) {
      maxCatPct = pct
      maxCat = cat
    }
  }

  // Equity vs Debt estimation
  const liquidVal = catTotals['Liquid Fund'] || 0
  const hybridVal = (catTotals['Aggressive Hybrid Fund'] || 0) * 0.35 // ~35% debt in hybrid
  const debtTotal = liquidVal + hybridVal
  const debtExposurePct = Math.round((debtTotal / totalCurrentValue) * 100)
  const equityExposurePct = 100 - debtExposurePct

  // Check pairwise overlaps
  const overlapPairs: OverlapPair[] = []
  let highOverlapDetected = false

  for (let i = 0; i < holdings.length; i++) {
    for (let j = i + 1; j < holdings.length; j++) {
      const pair = computePortfolioOverlap(holdings[i].fundId, holdings[j].fundId)
      overlapPairs.push(pair)
      if (pair.overlapPct >= 50) {
        highOverlapDetected = true
      }
    }
  }

  // 1. Institutional Consolidated Stock Exposure (ICICI Direct Style)
  const quoteMap = new Map<string, LiveQuote>()
  liveQuotes.forEach((q) => quoteMap.set(q.symbol, q))

  const stockMap: Record<
    string,
    { symbol: string; name: string; totalWeight: number; heldByFunds: Set<string>; sector: string }
  > = {}

  for (const h of holdings) {
    const holdingPortRatio = totalCurrentValue > 0 ? h.currentValue / totalCurrentValue : 0
    const stockHoldings = FUND_TOP_STOCK_HOLDINGS[h.fundId] || FUND_TOP_STOCK_HOLDINGS.PPFAS_FLEXI

    for (const item of stockHoldings) {
      if (!stockMap[item.symbol]) {
        stockMap[item.symbol] = {
          symbol: item.symbol,
          name: item.name,
          totalWeight: 0,
          heldByFunds: new Set<string>(),
          sector: item.sector
        }
      }
      stockMap[item.symbol].totalWeight += item.weight * holdingPortRatio
      stockMap[item.symbol].heldByFunds.add(h.fundName)
    }
  }

  const consolidatedStocks: ConsolidatedStockHolding[] = Object.values(stockMap)
    .map((s) => {
      const roundedWeight = +s.totalWeight.toFixed(2)
      const quote = quoteMap.get(s.symbol)
      return {
        symbol: s.symbol,
        name: s.name,
        totalWeightPct: roundedWeight,
        totalValue: Math.round((roundedWeight / 100) * totalCurrentValue),
        heldByFunds: Array.from(s.heldByFunds),
        sector: s.sector,
        livePrice: quote ? quote.price : 1450.0,
        changePct: quote ? quote.changePct : 0.45
      }
    })
    .sort((a, b) => b.totalWeightPct - a.totalWeightPct)
    .slice(0, 10)

  // 2. Institutional Market Cap Bifurcation (ICICI Direct Style)
  // Large Cap % (Top 100), Mid Cap % (101-250), Small Cap % (251+), Debt/Liquid %
  let largeCapWeighted = 0
  let midCapWeighted = 0
  let smallCapWeighted = 0
  let debtWeighted = 0

  for (const h of holdings) {
    const ratio = totalCurrentValue > 0 ? h.currentValue / totalCurrentValue : 0
    const cat = (h.category || '').toLowerCase()

    if (cat.includes('large cap')) {
      largeCapWeighted += 0.92 * ratio
      midCapWeighted += 0.05 * ratio
      debtWeighted += 0.03 * ratio
    } else if (cat.includes('flexi cap')) {
      largeCapWeighted += 0.65 * ratio
      midCapWeighted += 0.18 * ratio
      smallCapWeighted += 0.10 * ratio
      debtWeighted += 0.07 * ratio
    } else if (cat.includes('mid cap')) {
      midCapWeighted += 0.72 * ratio
      largeCapWeighted += 0.15 * ratio
      smallCapWeighted += 0.10 * ratio
      debtWeighted += 0.03 * ratio
    } else if (cat.includes('small cap')) {
      smallCapWeighted += 0.75 * ratio
      midCapWeighted += 0.18 * ratio
      debtWeighted += 0.07 * ratio
    } else if (cat.includes('hybrid')) {
      largeCapWeighted += 0.45 * ratio
      midCapWeighted += 0.15 * ratio
      debtWeighted += 0.35 * ratio
      smallCapWeighted += 0.05 * ratio
    } else if (cat.includes('liquid') || cat.includes('debt')) {
      debtWeighted += 1.0 * ratio
    } else {
      largeCapWeighted += 0.60 * ratio
      midCapWeighted += 0.25 * ratio
      smallCapWeighted += 0.10 * ratio
      debtWeighted += 0.05 * ratio
    }
  }

  const marketCapBifurcation: MarketCapBifurcation = {
    largeCapPct: Math.round(largeCapWeighted * 100),
    midCapPct: Math.round(midCapWeighted * 100),
    smallCapPct: Math.round(smallCapWeighted * 100),
    debtPct: Math.round(debtWeighted * 100)
  }

  // 3. Consolidated Sector Allocation
  const sectorWeightMap: Record<string, number> = {}
  for (const cs of Object.values(stockMap)) {
    sectorWeightMap[cs.sector] = (sectorWeightMap[cs.sector] || 0) + cs.totalWeight
  }

  const consolidatedSectors: ConsolidatedSector[] = Object.entries(sectorWeightMap)
    .map(([sector, weight]) => {
      const roundedWeight = +weight.toFixed(1)
      return {
        sector,
        weightPct: roundedWeight,
        value: Math.round((roundedWeight / 100) * totalCurrentValue)
      }
    })
    .sort((a, b) => b.weightPct - a.weightPct)
    .slice(0, 8)

  // Diversification status
  let status: 'Healthy' | 'Concentrated' | 'Over-fragmented' = 'Healthy'
  let advice =
    'Your portfolio displays a well-balanced distribution across fund styles with reasonable asset segregation.'

  if (holdings.length > 7) {
    status = 'Over-fragmented'
    advice =
      'Owning more than 5–7 mutual funds creates unnecessary complexity without meaningful risk reduction. High likelihood of portfolio overlap and benchmark hugging.'
  } else if (maxCatPct > 70 && holdings.length > 1) {
    status = 'Concentrated'
    advice = `High category concentration: ${maxCatPct}% of your portfolio is in ${maxCat}. Consider balancing across diversified market caps or debt buffers.`
  } else if (highOverlapDetected) {
    status = 'Concentrated'
    advice =
      'Significant overlap detected between your holdings. Multiple funds are holding almost identical top 10 stocks (e.g. HDFC Bank, ICICI Bank, Reliance).'
  }

  return {
    totalInvested,
    totalCurrentValue,
    totalGainPct,
    equityExposurePct,
    debtExposurePct,
    categoryBreakdown,
    diversificationStatus: status,
    diversificationAdvice: advice,
    overlapPairs,
    highOverlapDetected,
    maxCategoryExposure: { category: maxCat, pct: maxCatPct },
    consolidatedStocks,
    marketCapBifurcation,
    consolidatedSectors
  }
}

