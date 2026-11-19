import {
  AssetMetadata,
  DirectionalForecast,
  ForecastHorizon,
  EventObservation
} from './types'
import { loadHistoricalPrices } from './providers/MarketDataProvider'
import { computeDirectionalForecastCore } from './forecastCore'

export { computeDirectionalForecastCore } from './forecastCore'

interface ModelExportPayload {
  horizon: ForecastHorizon
  trading_days: number
  weights: any
  platt_params: [number, number]
  latest_forecasts: Record<string, any>
}

let cachedModels: Record<string, ModelExportPayload> | null = null

export async function loadTrainedModels(): Promise<Record<string, ModelExportPayload> | null> {
  if (cachedModels) return cachedModels
  try {
    const res = await fetch('/data/market_intelligence/models.json')
    if (res.ok) {
      cachedModels = await res.json()
      return cachedModels
    }
  } catch (err) {
    console.warn('Could not fetch /data/market_intelligence/models.json:', err)
  }
  return null
}

export async function computeDirectionalForecast(
  asset: AssetMetadata,
  horizon: ForecastHorizon,
  events: EventObservation[]
): Promise<DirectionalForecast | null> {
  // Preserving models-before-history await/fetch order
  const models = await loadTrainedModels()
  const model = models ? models[horizon] : null

  // Retrieve point-in-time features for asset
  const hist = await loadHistoricalPrices(asset.symbol)
  const lastFeat = hist.length > 0 ? hist[hist.length - 1] : null

  if (!lastFeat) {
    // Insufficient data fallback
    return null
  }

  return computeDirectionalForecastCore(
    lastFeat,
    horizon,
    events,
    model?.platt_params || null
  )
}
