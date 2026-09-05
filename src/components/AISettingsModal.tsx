import React, { useState, useEffect } from 'react'
import {
  X,
  Cpu,
  Shield,
  Zap,
  CheckCircle2,
  AlertCircle,
  Eye,
  EyeOff,
  ExternalLink,
  Server,
  Terminal,
  RotateCw
} from 'lucide-react'
import {
  AIConfig,
  AIProviderType,
  getAIConfig,
  saveAIConfig,
  testAIConnection
} from '../engine/aiService'

interface AISettingsModalProps {
  isOpen: boolean
  onClose: () => void
  onConfigUpdated?: (config: AIConfig) => void
}

export const AISettingsModal: React.FC<AISettingsModalProps> = ({
  isOpen,
  onClose,
  onConfigUpdated
}) => {
  const [config, setConfig] = useState<AIConfig>(getAIConfig())
  const [showGroqKey, setShowGroqKey] = useState<boolean>(false)
  const [isTesting, setIsTesting] = useState<boolean>(false)
  const [testResult, setTestResult] = useState<{
    success: boolean
    message: string
    latencyMs: number
  } | null>(null)

  useEffect(() => {
    if (isOpen) {
      setConfig(getAIConfig())
      setTestResult(null)
    }
  }, [isOpen])

  if (!isOpen) return null

  const handleSelectProvider = (provider: AIProviderType) => {
    const updated = { ...config, provider }
    setConfig(updated)
    setTestResult(null)
  }

  const handleTestConnection = async () => {
    setIsTesting(true)
    setTestResult(null)
    try {
      const res = await testAIConnection(config)
      setTestResult(res)
    } catch (e: any) {
      setTestResult({
        success: false,
        message: e.message || 'Connection test failed',
        latencyMs: 0
      })
    } finally {
      setIsTesting(false)
    }
  }

  const handleSave = () => {
    saveAIConfig(config)
    if (onConfigUpdated) onConfigUpdated(config)
    onClose()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md animate-fadeIn">
      <div className="w-full max-w-2xl rounded-3xl bg-slate-900 border border-slate-800 shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="px-6 py-5 border-b border-slate-800 flex items-center justify-between bg-slate-950/60">
          <div className="flex items-center space-x-3">
            <div className="p-2 rounded-xl bg-teal-500/10 border border-teal-500/20 text-teal-400">
              <Cpu className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-lg font-bold text-white">AI Co-Pilot & Model Settings</h3>
              <p className="text-xs text-slate-400">
                Choose your AI provider for decision auditing, risk checks, and Q&A.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 overflow-y-auto space-y-6 flex-grow">
          {/* Provider Selection Cards */}
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3">
              Select AI Provider
            </label>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {/* Option 1: Built-in Offline */}
              <button
                type="button"
                onClick={() => handleSelectProvider('offline')}
                className={`p-4 rounded-2xl border text-left transition-all ${
                  config.provider === 'offline'
                    ? 'bg-teal-500/10 border-teal-500 text-white shadow-lg shadow-teal-950/30'
                    : 'bg-slate-950/60 border-slate-800 text-slate-300 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="p-1.5 rounded-lg bg-teal-500/20 text-teal-300">
                    <Shield className="w-4 h-4" />
                  </span>
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-slate-800 text-slate-300">
                    Built-in
                  </span>
                </div>
                <div className="font-bold text-sm text-white">Offline Rules</div>
                <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">
                  100% Free, zero setup, 0ms latency. Runs quantitative heuristics offline.
                </p>
              </button>

              {/* Option 2: Local Ollama */}
              <button
                type="button"
                onClick={() => handleSelectProvider('ollama')}
                className={`p-4 rounded-2xl border text-left transition-all ${
                  config.provider === 'ollama'
                    ? 'bg-emerald-500/10 border-emerald-500 text-white shadow-lg shadow-emerald-950/30'
                    : 'bg-slate-950/60 border-slate-800 text-slate-300 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="p-1.5 rounded-lg bg-emerald-500/20 text-emerald-300">
                    <Server className="w-4 h-4" />
                  </span>
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300">
                    Private
                  </span>
                </div>
                <div className="font-bold text-sm text-white">Local Ollama</div>
                <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">
                  Runs on your laptop. Zero data leaves your computer. Absolute privacy.
                </p>
              </button>

              {/* Option 3: Groq Cloud */}
              <button
                type="button"
                onClick={() => handleSelectProvider('groq')}
                className={`p-4 rounded-2xl border text-left transition-all ${
                  config.provider === 'groq'
                    ? 'bg-indigo-500/10 border-indigo-500 text-white shadow-lg shadow-indigo-950/30'
                    : 'bg-slate-950/60 border-slate-800 text-slate-300 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="p-1.5 rounded-lg bg-indigo-500/20 text-indigo-300">
                    <Zap className="w-4 h-4" />
                  </span>
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300">
                    Free Tier
                  </span>
                </div>
                <div className="font-bold text-sm text-white">Groq Cloud</div>
                <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">
                  Ultra-fast Llama 3.3 (500 tokens/sec). Requires free API key.
                </p>
              </button>
            </div>
          </div>

          {/* Provider Details & Configuration */}
          {config.provider === 'ollama' && (
            <div className="p-4 rounded-2xl bg-slate-950/80 border border-slate-800 space-y-4 animate-fadeIn">
              <div className="flex items-center space-x-2 text-xs font-bold text-emerald-400">
                <Terminal className="w-4 h-4" />
                <span>Local Ollama Configuration</span>
              </div>

              <div className="space-y-3 text-xs">
                <div>
                  <label className="block text-slate-400 mb-1">Ollama API Endpoint</label>
                  <input
                    type="text"
                    value={config.ollamaEndpoint}
                    onChange={(e) => setConfig({ ...config, ollamaEndpoint: e.target.value })}
                    placeholder="http://localhost:11434"
                    className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-white text-xs focus:outline-none focus:border-emerald-500"
                  />
                  <span className="text-[10px] text-slate-500 mt-0.5 block">
                    Default is http://localhost:11434. Make sure Ollama is running.
                  </span>
                </div>

                <div>
                  <label className="block text-slate-400 mb-1">Model Name</label>
                  <select
                    value={config.ollamaModel}
                    onChange={(e) => setConfig({ ...config, ollamaModel: e.target.value })}
                    className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-white text-xs focus:outline-none focus:border-emerald-500"
                  >
                    <option value="llama3.2">llama3.2 (Fast & Recommended)</option>
                    <option value="deepseek-r1:8b">deepseek-r1:8b (Reasoning Specialist)</option>
                    <option value="qwen2.5:7b">qwen2.5:7b (Strong Structured Reasoning)</option>
                    <option value="mistral">mistral:7b (General Intelligence)</option>
                  </select>
                </div>
              </div>
            </div>
          )}

          {config.provider === 'groq' && (
            <div className="p-4 rounded-2xl bg-slate-950/80 border border-slate-800 space-y-4 animate-fadeIn">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2 text-xs font-bold text-indigo-400">
                  <Zap className="w-4 h-4" />
                  <span>Groq Cloud Configuration</span>
                </div>
                <a
                  href="https://console.groq.com/keys"
                  target="_blank"
                  rel="noreferrer"
                  className="text-[11px] font-semibold text-indigo-400 hover:text-indigo-300 flex items-center space-x-1"
                >
                  <span>Get Free Key</span>
                  <ExternalLink className="w-3 h-3" />
                </a>
              </div>

              <div className="space-y-3 text-xs">
                <div>
                  <label className="block text-slate-400 mb-1">Groq API Key</label>
                  <div className="relative">
                    <input
                      type={showGroqKey ? 'text' : 'password'}
                      value={config.groqApiKey}
                      onChange={(e) => setConfig({ ...config, groqApiKey: e.target.value })}
                      placeholder="gsk_..."
                      className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 pr-10 text-white text-xs focus:outline-none focus:border-indigo-500"
                    />
                    <button
                      type="button"
                      onClick={() => setShowGroqKey(!showGroqKey)}
                      className="absolute right-3 top-2.5 text-slate-400 hover:text-white"
                    >
                      {showGroqKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                  <span className="text-[10px] text-slate-500 mt-0.5 block">
                    Your key is stored locally in your browser's localStorage and never transmitted to our backend.
                  </span>
                </div>

                <div>
                  <label className="block text-slate-400 mb-1">Groq Model</label>
                  <select
                    value={config.groqModel}
                    onChange={(e) => setConfig({ ...config, groqModel: e.target.value })}
                    className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-white text-xs focus:outline-none focus:border-indigo-500"
                  >
                    <option value="llama-3.3-70b-versatile">
                      llama-3.3-70b-versatile (Flagship ~500 t/s)
                    </option>
                    <option value="deepseek-r1-distill-llama-70b">
                      deepseek-r1-distill-llama-70b (Deep Reasoning)
                    </option>
                    <option value="llama-3.1-8b-instant">
                      llama-3.1-8b-instant (Fastest ~800 t/s)
                    </option>
                  </select>
                </div>
              </div>
            </div>
          )}

          {config.provider === 'offline' && (
            <div className="p-4 rounded-2xl bg-slate-950/80 border border-slate-800 space-y-2 text-xs text-slate-300">
              <div className="flex items-center space-x-2 font-bold text-teal-400">
                <CheckCircle2 className="w-4 h-4" />
                <span>Deterministic Heuristic Mode Active</span>
              </div>
              <p className="text-slate-400 leading-relaxed text-[11px]">
                NiveshPilot is running with 100% offline built-in heuristics. You get instantaneous
                responses, mathematical consistency, zero network latency, and complete privacy
                without needing any third-party model setup.
              </p>
            </div>
          )}

          {/* Connection Test Result Box */}
          {testResult && (
            <div
              className={`p-3 rounded-xl border text-xs flex items-start space-x-2.5 ${
                testResult.success
                  ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
                  : 'bg-rose-500/10 border-rose-500/30 text-rose-300'
              }`}
            >
              {testResult.success ? (
                <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5 text-emerald-400" />
              ) : (
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-rose-400" />
              )}
              <div className="flex-grow">
                <div className="font-semibold">
                  {testResult.success ? 'Connection Successful' : 'Connection Failed'}
                  {testResult.latencyMs > 0 && ` (${testResult.latencyMs}ms)`}
                </div>
                <div className="text-[11px] opacity-90 mt-0.5">{testResult.message}</div>
              </div>
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="px-6 py-4 border-t border-slate-800 bg-slate-950/80 flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={handleTestConnection}
            disabled={isTesting}
            className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold transition-all flex items-center space-x-2 disabled:opacity-50 border border-slate-700"
          >
            <RotateCw className={`w-3.5 h-3.5 ${isTesting ? 'animate-spin' : ''}`} />
            <span>{isTesting ? 'Testing...' : 'Test Connection'}</span>
          </button>

          <div className="flex items-center space-x-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl bg-transparent hover:bg-slate-800 text-slate-400 hover:text-white text-xs font-semibold transition-all"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSave}
              className="px-5 py-2 rounded-xl bg-teal-600 hover:bg-teal-500 text-white text-xs font-bold transition-all shadow-lg shadow-teal-900/30"
            >
              Save Settings
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
