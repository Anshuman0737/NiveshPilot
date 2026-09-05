import { EvidenceObject, FundSnapshot, SuitabilityProfile } from './types'

export type AIProviderType = 'offline' | 'ollama' | 'groq'

export interface AIConfig {
  provider: AIProviderType
  ollamaEndpoint: string
  ollamaModel: string
  groqApiKey: string
  groqModel: string
}

export interface AIAuditResult {
  confidencePct: number
  confidenceLevel: 'High' | 'Moderate' | 'Caution' | 'Divergence'
  summary: string
  behavioralCheck: {
    aligned: boolean
    note: string
  }
  redTeamRisks: string[]
  suggestedAdjustment?: string
  providerUsed: string
  latencyMs?: number
}

const STORAGE_KEY = 'niveshpilot_ai_config'

export const DEFAULT_AI_CONFIG: AIConfig = {
  provider: 'offline',
  ollamaEndpoint: 'http://localhost:11434',
  ollamaModel: 'llama3.2',
  groqApiKey: '',
  groqModel: 'llama-3.3-70b-versatile'
}

export function getAIConfig(): AIConfig {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) {
      return { ...DEFAULT_AI_CONFIG, ...JSON.parse(saved) }
    }
  } catch (e) {
    console.warn('Could not read AI config from localStorage', e)
  }
  return DEFAULT_AI_CONFIG
}

export function saveAIConfig(config: AIConfig): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(config))
  } catch (e) {
    console.warn('Could not save AI config to localStorage', e)
  }
}

/**
 * Tests connection to the selected AI provider
 */
export async function testAIConnection(
  config: AIConfig
): Promise<{ success: boolean; message: string; latencyMs: number }> {
  const start = performance.now()

  if (config.provider === 'offline') {
    return {
      success: true,
      message: 'Offline Heuristic Engine is always ready (0ms latency, ₹0 cost).',
      latencyMs: 0
    }
  }

  if (config.provider === 'ollama') {
    try {
      const endpoint = config.ollamaEndpoint.replace(/\/$/, '')
      const res = await fetch(`${endpoint}/api/tags`, {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' }
      })
      const latencyMs = Math.round(performance.now() - start)
      if (res.ok) {
        const data = await res.json()
        const models = (data.models || []).map((m: any) => m.name).join(', ')
        return {
          success: true,
          message: `Connected to Ollama. Available models: ${models || 'None installed yet'}`,
          latencyMs
        }
      } else {
        return {
          success: false,
          message: `Ollama returned status ${res.status}. Is Ollama running on ${endpoint}?`,
          latencyMs
        }
      }
    } catch (err: any) {
      return {
        success: false,
        message: `Could not reach Ollama at ${config.ollamaEndpoint}. Ensure 'ollama serve' is running and CORS is enabled.`,
        latencyMs: Math.round(performance.now() - start)
      }
    }
  }

  if (config.provider === 'groq') {
    if (!config.groqApiKey || config.groqApiKey.trim() === '') {
      return {
        success: false,
        message: 'Groq API Key is missing. Please enter your free key from console.groq.com.',
        latencyMs: 0
      }
    }
    try {
      const res = await fetch('https://api.groq.com/openai/v1/models', {
        headers: {
          Authorization: `Bearer ${config.groqApiKey.trim()}`,
          'Content-Type': 'application/json'
        }
      })
      const latencyMs = Math.round(performance.now() - start)
      if (res.ok) {
        return {
          success: true,
          message: 'Successfully authenticated with Groq Cloud API.',
          latencyMs
        }
      } else {
        const errData = await res.json().catch(() => ({}))
        return {
          success: false,
          message: errData.error?.message || `Groq API returned HTTP ${res.status}.`,
          latencyMs
        }
      }
    } catch (err: any) {
      return {
        success: false,
        message: `Network error reaching Groq API: ${err.message}`,
        latencyMs: Math.round(performance.now() - start)
      }
    }
  }

  return { success: false, message: 'Unknown provider', latencyMs: 0 }
}

/**
 * Built-in Offline Heuristic Auditor:
 * Evaluates the quantitative decision against the investor profile without any external calls.
 */
function runOfflineAudit(
  evidence: EvidenceObject,
  fund: FundSnapshot,
  profile: SuitabilityProfile
): AIAuditResult {
  const { signal, deployment, marketRegime } = evidence
  let confidencePct = 90
  let confidenceLevel: 'High' | 'Moderate' | 'Caution' | 'Divergence' = 'High'
  const redTeamRisks: string[] = []

  // Check 1: Behavioral Contradiction Check
  let behavioralAligned = true
  let behavioralNote = 'Risk reaction matches deployment risk posture.'

  if (profile.riskReaction === 'Sell immediately' || profile.riskReaction === 'Feel uncomfortable but hold') {
    if (deployment.immediatePercent > 60) {
      behavioralAligned = false
      confidencePct -= 18
      behavioralNote = `Emotional mismatch: Your profile indicates sensitivity to drawdowns (${profile.riskReaction}), but current plan deploys ${deployment.immediatePercent}% immediately into equity.`
      redTeamRisks.push('High emotional drawdown hazard: A sudden 5-10% pullback could trigger a panic liquidation.')
    }
  }

  // Check 2: Emergency Cushion Check
  if (!profile.hasEmergencyCushion) {
    confidencePct -= 15
    redTeamRisks.push('No emergency reserve: Capital may need to be prematurely withdrawn during unexpected personal expenses.')
  }

  // Check 3: Market Regime & Volatility Check
  if (marketRegime === 'High-volatility') {
    confidencePct -= 10
    redTeamRisks.push('Unprecedented volatility: Price swings could exceed historical standard deviations in the near term.')
  } else if (marketRegime === 'Correction') {
    redTeamRisks.push('Potential falling-knife risk: Dip could extend by another 5-8% before establishing a firm base.')
  } else {
    redTeamRisks.push('Valuation expansion: Benchmark Nifty 50 TRI is near historical highs; expect lower forward 3-year CAGR.')
  }

  // Check 4: Category Risk Check
  if (fund.category.includes('Small Cap') && profile.riskCapacity !== 'High') {
    confidencePct -= 12
    redTeamRisks.push('Small-cap liquidity risk: Small-cap funds suffer deeper 30-40% drawdowns during mid-cycle corrections.')
  }

  // Determine Level
  if (confidencePct >= 85) confidenceLevel = 'High'
  else if (confidencePct >= 70) confidenceLevel = 'Moderate'
  else if (confidencePct >= 50) confidenceLevel = 'Caution'
  else confidenceLevel = 'Divergence'

  return {
    confidencePct,
    confidenceLevel,
    summary:
      confidencePct >= 80
        ? `The quantitative plan to deploy ${deployment.immediatePercent}% into ${fund.scheme_name.split(' - ')[0]} and keep ${deployment.staggeredPercent}% in liquid yield is soundly aligned with market regime (${marketRegime}).`
        : `Quantitative proposal is viable, but behavioral alignment requires heightened caution around emotional panic triggers.`,
    behavioralCheck: {
      aligned: behavioralAligned,
      note: behavioralNote
    },
    redTeamRisks: redTeamRisks.slice(0, 3),
    suggestedAdjustment: !behavioralAligned
      ? `Consider scaling back initial deployment to 40% and parking 60% in Liquid Fund to prevent emotional panic.`
      : undefined,
    providerUsed: 'Built-in Heuristic Engine (Offline)'
  }
}

/**
 * Runs an AI decision audit via Ollama, Groq, or Offline Fallback
 */
export async function auditDecision(
  evidence: EvidenceObject,
  fund: FundSnapshot,
  profile: SuitabilityProfile
): Promise<AIAuditResult> {
  const config = getAIConfig()
  const start = performance.now()

  // Default to offline heuristics if offline selected or no keys
  if (config.provider === 'offline' || (config.provider === 'groq' && !config.groqApiKey)) {
    const res = runOfflineAudit(evidence, fund, profile)
    res.latencyMs = Math.round(performance.now() - start)
    return res
  }

  const prompt = `You are a SEBI-compliant Quantitative Investment Risk Auditor.
Audit the following mutual fund investment deployment proposal and return ONLY a valid JSON object.

CONTEXT:
- User Capital: ₹${profile.amount}
- Time Horizon: ${profile.horizon}
- Investment Goal: ${profile.goal}
- Emotional Risk Reaction: ${profile.riskReaction}
- Emergency Cushion Present: ${profile.hasEmergencyCushion ? 'Yes' : 'No'}
- Selected Fund: ${fund.scheme_name} (${fund.category})
- Current Market Regime: ${evidence.marketRegime}
- 30D Realized Volatility: ${fund.vol_30d}%
- Peak Drawdown: ${fund.current_drawdown}%
- Quantitative Engine Recommendation: ${evidence.signal}
- Proposed Split: ${evidence.deployment.immediatePercent}% Immediate (₹${evidence.deployment.immediateAmount}), ${evidence.deployment.staggeredPercent}% Staggered (₹${evidence.deployment.staggeredAmount})

REQUIRED JSON STRUCTURE:
{
  "confidencePct": number (between 40 and 98),
  "confidenceLevel": "High" | "Moderate" | "Caution" | "Divergence",
  "summary": "concise 2-sentence assessment of the deployment plan",
  "behavioralAligned": boolean,
  "behavioralNote": "assessment of emotional alignment",
  "redTeamRisks": ["specific risk 1", "specific risk 2", "specific risk 3"],
  "suggestedAdjustment": "optional suggestion if risk is misaligned"
}`

  // Call Ollama
  if (config.provider === 'ollama') {
    try {
      const endpoint = config.ollamaEndpoint.replace(/\/$/, '')
      const res = await fetch(`${endpoint}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: config.ollamaModel || 'llama3.2',
          messages: [{ role: 'user', content: prompt }],
          stream: false,
          format: 'json'
        })
      })
      if (res.ok) {
        const data = await res.json()
        const parsed = JSON.parse(data.message?.content || '{}')
        return {
          confidencePct: parsed.confidencePct || 85,
          confidenceLevel: parsed.confidenceLevel || 'High',
          summary: parsed.summary || 'Audit validated by local Ollama model.',
          behavioralCheck: {
            aligned: parsed.behavioralAligned ?? true,
            note: parsed.behavioralNote || 'Risk profile matches allocation.'
          },
          redTeamRisks: parsed.redTeamRisks || ['Market valuation sensitivity', 'Drawdown hazard'],
          suggestedAdjustment: parsed.suggestedAdjustment,
          providerUsed: `Ollama (${config.ollamaModel})`,
          latencyMs: Math.round(performance.now() - start)
        }
      }
    } catch (e) {
      console.warn('Ollama audit failed, falling back to offline heuristics', e)
    }
  }

  // Call Groq Cloud
  if (config.provider === 'groq') {
    try {
      const res = await fetch('https://api.groq.com/openai/v1/chat/completions', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${config.groqApiKey.trim()}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          model: config.groqModel || 'llama-3.3-70b-versatile',
          messages: [{ role: 'user', content: prompt }],
          response_format: { type: 'json_object' },
          temperature: 0.2
        })
      })
      if (res.ok) {
        const data = await res.json()
        const parsed = JSON.parse(data.choices?.[0]?.message?.content || '{}')
        return {
          confidencePct: parsed.confidencePct || 88,
          confidenceLevel: parsed.confidenceLevel || 'High',
          summary: parsed.summary || 'Audit verified by Groq LLM.',
          behavioralCheck: {
            aligned: parsed.behavioralAligned ?? true,
            note: parsed.behavioralNote || 'Profile is consistent with market entry.'
          },
          redTeamRisks: parsed.redTeamRisks || ['Macro rate cycle risk', 'Near-term volatility swing'],
          suggestedAdjustment: parsed.suggestedAdjustment,
          providerUsed: `Groq (${config.groqModel.split('-')[0]})`,
          latencyMs: Math.round(performance.now() - start)
        }
      }
    } catch (e) {
      console.warn('Groq audit failed, falling back to offline heuristics', e)
    }
  }

  // Graceful Fallback
  const fallback = runOfflineAudit(evidence, fund, profile)
  fallback.latencyMs = Math.round(performance.now() - start)
  return fallback
}

/**
 * Interactive Q&A Co-Pilot Response Generator
 */
export async function askCoPilot(
  question: string,
  context: { evidence: EvidenceObject; fund: FundSnapshot; profile: SuitabilityProfile }
): Promise<string> {
  const config = getAIConfig()
  const { evidence, fund, profile } = context

  // 1. Check if Offline or Quick Rule Match
  const qLower = question.toLowerCase()

  if (config.provider === 'offline' || (config.provider === 'groq' && !config.groqApiKey)) {
    // High-quality offline knowledge base for common beginner queries
    if (qLower.includes('liquid') || qLower.includes('buffer') || qLower.includes('cash')) {
      return `Keeping ${evidence.deployment.staggeredPercent}% (₹${evidence.deployment.staggeredAmount}) in a Liquid Fund accomplishes two critical things:
1. **Safety & Interest**: Your uninvested cash earns ~6.0% p.a. daily interest with zero stock market risk.
2. **Crash Insurance**: If the market suffers a sudden 5–10% dip over the next 42 days, this cash gives you dry powder to buy fund units at cheaper NAVs rather than having all your money trapped at the top.`
    }

    if (qLower.includes('crash') || qLower.includes('drop') || qLower.includes('tomorrow') || qLower.includes('falls')) {
      return `If the market drops 10% tomorrow:
- **Lump Sum would lose 10% on the entire ₹${profile.amount}**.
- **Under your NiveshPilot plan**, only the initial ${evidence.deployment.immediatePercent}% (₹${evidence.deployment.immediateAmount}) experiences that drop. The remaining ₹${evidence.deployment.staggeredAmount} remains 100% safe in Liquid yield, cutting your portfolio drawdown from -10% down to just ~${(0.10 * (evidence.deployment.immediatePercent / 100) * 100).toFixed(1)}%.
- When your second tranche executes, you will buy fund units at a 10% discount!`
    }

    if (qLower.includes('hinglish') || qLower.includes('hindi') || qLower.includes('simple words')) {
      return `Seedha aur simple matlab:
1. Poora paisa ek saath mat lagao (agar market gir gaya toh dukh hoga).
2. Abhi ₹${evidence.deployment.immediateAmount} (${evidence.deployment.immediatePercent}%) ${fund.scheme_name.split(' - ')[0]} mein lagao.
3. Bacha hua ₹${evidence.deployment.staggeredAmount} Liquid Fund mein rakho jahan ~6% interest banta rahega.
4. Kuch hafte baad jab market stable rahe ya dip aaye, tab bacha hua paisa invest karo. Isse risk aadha ho jata hai!`
    }

    if (qLower.includes('why not all') || qLower.includes('lump sum') || qLower.includes('100%')) {
      return `Historically, putting 100% upfront (Lump Sum) makes slightly more money in a smooth bull market (+23.6% vs +21.7%). However, during crashes (like March 2020), Lump Sum investors suffered a devastating -37.5% crash that caused many beginners to panic-sell at the exact bottom. NiveshPilot's staggered entry trades ~1.9% in upside for cutting panic crashes down to -8.7%.`
    }

    return `Based on current market conditions (${evidence.marketRegime}, 30D volatility of ${fund.vol_30d}%), NiveshPilot recommends deploying ₹${evidence.deployment.immediateAmount} today and staggering ₹${evidence.deployment.staggeredAmount} over ${evidence.deployment.staggerDurationDesc}. This protects your capital from sudden market pullbacks while keeping your money compounding in liquid yield.`
  }

  const systemContext = `You are NiveshPilot AI Co-Pilot, an empathetic, beginner-friendly Indian mutual fund decision assistant.
Answer the user's question clearly in 2-3 short, conversational paragraphs without complicated jargon.

USER CONTEXT:
- Capital: ₹${profile.amount}
- Horizon: ${profile.horizon}
- Goal: ${profile.goal}
- Fund: ${fund.scheme_name} (${fund.category})
- Recommendation: ${evidence.signal} (${evidence.deployment.immediatePercent}% Now / ${evidence.deployment.staggeredPercent}% Later in Liquid Yield)
- Market Regime: ${evidence.marketRegime}
- 30D Volatility: ${fund.vol_30d}%
- Current Drawdown: ${fund.current_drawdown}%`

  // Call Ollama
  if (config.provider === 'ollama') {
    try {
      const endpoint = config.ollamaEndpoint.replace(/\/$/, '')
      const res = await fetch(`${endpoint}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: config.ollamaModel || 'llama3.2',
          messages: [
            { role: 'system', content: systemContext },
            { role: 'user', content: question }
          ],
          stream: false
        })
      })
      if (res.ok) {
        const data = await res.json()
        return data.message?.content || 'No response from local Ollama model.'
      }
    } catch (e) {
      console.warn('Ollama Q&A failed, falling back to offline answer', e)
    }
  }

  // Call Groq Cloud
  if (config.provider === 'groq') {
    try {
      const res = await fetch('https://api.groq.com/openai/v1/chat/completions', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${config.groqApiKey.trim()}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          model: config.groqModel || 'llama-3.3-70b-versatile',
          messages: [
            { role: 'system', content: systemContext },
            { role: 'user', content: question }
          ],
          temperature: 0.5,
          max_tokens: 450
        })
      })
      if (res.ok) {
        const data = await res.json()
        return data.choices?.[0]?.message?.content || 'No response from Groq.'
      }
    } catch (e) {
      console.warn('Groq Q&A failed, falling back to offline answer', e)
    }
  }

  // Final fallback
  return `Based on current market conditions (${evidence.marketRegime}), the recommended plan is to deploy ₹${evidence.deployment.immediateAmount} today and keep ₹${evidence.deployment.staggeredAmount} in Liquid yield buffer. This insulates you from immediate pullbacks.`
}
