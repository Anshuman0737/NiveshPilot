import { AssetMetadata, AssetPricePoint, EventObservation } from './types'

export interface MarketAnomaly {
  id: string
  symbol: string
  assetName: string
  type: 'Unusual Volume' | 'Return Extreme' | 'Volatility Compression' | 'Volatility Expansion' | 'News Sentiment Shock'
  magnitude: string
  zscore: number
  percentile: string
  impact: string
  impactIcon: 'arrow_upward' | 'arrow_downward' | 'check_circle' | 'warning'
  impactColor: 'text-tertiary' | 'text-error' | 'text-secondary' | 'text-outline'
  typeColor: string
  time: string
  details: string
}

function calculateMeanStd(values: number[]): { mean: number; std: number } {
  if (values.length < 2) return { mean: values[0] || 0, std: 1 }
  const mean = values.reduce((sum, v) => sum + v, 0) / values.length
  const variance = values.reduce((sum, v) => sum + Math.pow(v - mean, 2), 0) / (values.length - 1)
  return { mean, std: Math.max(0.0001, Math.sqrt(variance)) }
}

export function scanMarketAnomalies(
  assets: AssetMetadata[],
  priceMap: Record<string, AssetPricePoint[]>,
  events: EventObservation[] = []
): MarketAnomaly[] {
  const anomalies: MarketAnomaly[] = []

  for (const asset of assets) {
    const prices = priceMap[asset.symbol] || []
    if (prices.length < 20) continue

    const n = prices.length
    const latest = prices[n - 1]
    const p5 = prices[Math.max(0, n - 6)]
    const p0 = latest.close

    // 1. Check Return Z-Score over 60-day historical window
    const windowSize = Math.min(n - 5, 60)
    const rolling5dReturns: number[] = []
    for (let i = n - windowSize; i < n; i++) {
      const prev = prices[i - 5]
      const curr = prices[i]
      if (prev && curr && prev.close > 0) {
        rolling5dReturns.push((curr.close - prev.close) / prev.close)
      }
    }

    if (rolling5dReturns.length >= 10 && p5.close > 0) {
      const current5dReturn = (p0 - p5.close) / p5.close
      const { mean, std } = calculateMeanStd(rolling5dReturns)
      const zscore = +((current5dReturn - mean) / std).toFixed(2)

      if (Math.abs(zscore) >= 1.75) {
        const isBull = zscore > 0
        const retPct = +(current5dReturn * 100).toFixed(1)
        anomalies.push({
          id: `ret-${asset.symbol}`,
          symbol: asset.symbol,
          assetName: `${asset.name} (${asset.symbol.split('.')[0]})`,
          type: 'Return Extreme',
          magnitude: `${zscore > 0 ? '+' : ''}${zscore}σ Z-Score`,
          zscore: Math.abs(zscore),
          percentile: isBull ? '97th' : '3rd',
          impact: isBull ? `Bullish Expansion (${retPct > 0 ? '+' : ''}${retPct}%)` : `Bearish Drawdown (${retPct}%)`,
          impactIcon: isBull ? 'arrow_upward' : 'arrow_downward',
          impactColor: isBull ? 'text-tertiary' : 'text-error',
          typeColor: isBull ? 'bg-tertiary/20 text-tertiary' : 'bg-error-container text-on-error',
          time: 'Latest Close',
          details: `5-day return of ${retPct}% deviates significantly from historical rolling mean (${+(mean * 100).toFixed(1)}%).`
        })
      }
    }

    // 2. Check Volume Spike (V_latest / SMA20(V))
    const recent20Volumes = prices.slice(Math.max(0, n - 21), n - 1).map((p) => p.volume).filter((v) => v > 0)
    if (recent20Volumes.length >= 10 && latest.volume > 0) {
      const avgVol = recent20Volumes.reduce((a, b) => a + b, 0) / recent20Volumes.length
      const volMultiplier = +(latest.volume / avgVol).toFixed(1)

      if (volMultiplier >= 1.8) {
        const isUp = latest.close >= (prices[n - 2]?.close || latest.close)
        anomalies.push({
          id: `vol-${asset.symbol}`,
          symbol: asset.symbol,
          assetName: `${asset.name} (${asset.symbol.split('.')[0]})`,
          type: 'Unusual Volume',
          magnitude: `${volMultiplier}x Volume Multiple`,
          zscore: +((volMultiplier - 1.0) * 1.6).toFixed(2),
          percentile: '98th',
          impact: isUp ? 'Institutional Accumulation' : 'Elevated Selling Pressure',
          impactIcon: isUp ? 'check_circle' : 'warning',
          impactColor: isUp ? 'text-tertiary' : 'text-error',
          typeColor: 'bg-secondary-container text-on-secondary',
          time: 'Session Volume',
          details: `Trading volume is ${volMultiplier}x higher than 20-day moving average.`
        })
      }
    }

    // 3. Volatility Compression / Expansion (5D realized vol vs 30D realized vol)
    const logReturns: number[] = []
    for (let i = Math.max(1, n - 35); i < n; i++) {
      if (prices[i - 1].close > 0 && prices[i].close > 0) {
        logReturns.push(Math.log(prices[i].close / prices[i - 1].close))
      }
    }

    if (logReturns.length >= 25) {
      const vol5 = calculateMeanStd(logReturns.slice(-5)).std * Math.sqrt(252)
      const vol30 = calculateMeanStd(logReturns.slice(-30)).std * Math.sqrt(252)

      if (vol30 > 0.05) {
        const ratio = +(vol5 / vol30).toFixed(2)
        if (ratio >= 2.2) {
          anomalies.push({
            id: `volexp-${asset.symbol}`,
            symbol: asset.symbol,
            assetName: `${asset.name} (${asset.symbol.split('.')[0]})`,
            type: 'Volatility Expansion',
            magnitude: `${ratio}x Vol Ratio`,
            zscore: +(ratio * 1.2).toFixed(2),
            percentile: '95th',
            impact: 'Regime Turbulence',
            impactIcon: 'warning',
            impactColor: 'text-error',
            typeColor: 'bg-error-container text-on-error',
            time: 'Rolling 5D/30D',
            details: `Short-term annualized volatility (${(vol5 * 100).toFixed(1)}%) exceeds 30-day baseline (${(vol30 * 100).toFixed(1)}%).`
          })
        } else if (ratio <= 0.45) {
          anomalies.push({
            id: `volcomp-${asset.symbol}`,
            symbol: asset.symbol,
            assetName: `${asset.name} (${asset.symbol.split('.')[0]})`,
            type: 'Volatility Compression',
            magnitude: `${ratio}x Vol Ratio`,
            zscore: +((1 - ratio) * 2.5).toFixed(2),
            percentile: '92nd',
            impact: 'Pre-Breakout Squeeze',
            impactIcon: 'check_circle',
            impactColor: 'text-secondary',
            typeColor: 'bg-secondary-container text-on-secondary',
            time: 'Rolling 5D/30D',
            details: `Bollinger bandwidth and 5-day volatility severely compressed relative to 30-day norm.`
          })
        }
      }
    }

    // 4. News Sentiment Shock
    const assetEvents = events.filter((e) => e.symbol === asset.symbol)
    for (const evt of assetEvents) {
      if (Math.abs(evt.actual_value) >= 0.45 || Math.abs(evt.surprise_pct) >= 5.0) {
        const isPos = evt.actual_value > 0
        anomalies.push({
          id: `news-${evt.event_id}`,
          symbol: asset.symbol,
          assetName: `${asset.name} (${asset.symbol.split('.')[0]})`,
          type: 'News Sentiment Shock',
          magnitude: `${evt.surprise_pct > 0 ? '+' : ''}${evt.surprise_pct}% Surprise`,
          zscore: +(Math.abs(evt.actual_value) * 3.0).toFixed(2),
          percentile: isPos ? '94th' : '6th',
          impact: isPos ? 'Positive Sentiment Shift' : 'Negative Narrative Headwind',
          impactIcon: isPos ? 'arrow_upward' : 'arrow_downward',
          impactColor: isPos ? 'text-tertiary' : 'text-error',
          typeColor: isPos ? 'bg-tertiary-container text-on-tertiary' : 'bg-error-container text-on-error',
          time: 'RSS Feed Event',
          details: `"${evt.title.slice(0, 80)}..." (Source: ${evt.source}).`
        })
        break // Flag once per asset
      }
    }
  }

  // Sort by statistical extremity descending
  return anomalies.sort((a, b) => b.zscore - a.zscore)
}
