import { SuitabilityProfile } from '../types'
import { AssetMetadata, DirectionalForecast } from './types'

export interface SuitabilityBridgeResult {
  isPermittedBySuitability: boolean
  badge: 'SUITABLE' | 'CAUTION' | 'RESTRICTED'
  message: string
}

export function evaluateAssetSuitability(
  asset: AssetMetadata,
  forecast: DirectionalForecast | null,
  profile: SuitabilityProfile
): SuitabilityBridgeResult {
  // 1. Emergency reserve or short horizon gate
  if (profile.goal === 'Emergency reserve' || profile.horizon === '<1Y') {
    if (asset.asset_class === 'equity' || asset.asset_class === 'commodity') {
      return {
        isPermittedBySuitability: false,
        badge: 'RESTRICTED',
        message:
          'Market forecast is favorable, but direct equity or commodity exposure is unsuitable for your <1-year horizon or emergency fund objective. Capital preservation in Liquid funds is strongly recommended.'
      }
    }
  }

  // 2. High risk aversion gate
  if (profile.riskCapacity === 'Low' && profile.riskReaction === 'Sell immediately') {
    if (asset.asset_class === 'equity' || asset.asset_class === 'commodity') {
      return {
        isPermittedBySuitability: false,
        badge: 'CAUTION',
        message:
          'Elevated volatility risk. Even with a positive directional probability, this asset carries cyclical pullbacks that conflict with your low risk capacity.'
      }
    }
  }

  // 3. Asset aligns with profile
  if (forecast && forecast.probability_bullish >= 0.55) {
    return {
      isPermittedBySuitability: true,
      badge: 'SUITABLE',
      message: `Asset aligns with your ${profile.horizon} horizon and ${profile.goal} objective.`
    }
  }

  return {
    isPermittedBySuitability: true,
    badge: 'SUITABLE',
    message: `Permitted under your ${profile.riskCapacity} risk capacity profile.`
  }
}
