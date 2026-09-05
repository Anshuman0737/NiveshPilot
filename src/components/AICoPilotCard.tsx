import React, { useState, useEffect } from 'react'
import {
  Bot,
  Sparkles,
  ShieldAlert,
  CheckCircle2,
  AlertTriangle,
  Send,
  Sliders,
  RotateCw,
  HelpCircle,
  MessageSquare,
  ChevronDown,
  ChevronUp
} from 'lucide-react'
import { EvidenceObject, FundSnapshot, SuitabilityProfile } from '../engine/types'
import {
  AIAuditResult,
  auditDecision,
  askCoPilot,
  getAIConfig
} from '../engine/aiService'

interface AICoPilotCardProps {
  evidence: EvidenceObject
  fund: FundSnapshot
  profile: SuitabilityProfile
  onOpenSettings: () => void
}

export const AICoPilotCard: React.FC<AICoPilotCardProps> = ({
  evidence,
  fund,
  profile,
  onOpenSettings
}) => {
  const [audit, setAudit] = useState<AIAuditResult | null>(null)
  const [isLoadingAudit, setIsLoadingAudit] = useState<boolean>(true)
  const [isOpenChat, setIsOpenChat] = useState<boolean>(false)
  const [question, setQuestion] = useState<string>('')
  const [answer, setAnswer] = useState<string | null>(null)
  const [isAsking, setIsAsking] = useState<boolean>(false)

  // Quick question chips
  const quickQuestions = [
    'Why park cash in a liquid fund?',
    'What if the market drops 10% tomorrow?',
    'Why not invest 100% lump sum today?',
    'Explain this plan in simple Hinglish'
  ]

  // Re-run audit when inputs change
  useEffect(() => {
    let isCancelled = false
    setIsLoadingAudit(true)

    auditDecision(evidence, fund, profile)
      .then((res) => {
        if (!isCancelled) {
          setAudit(res)
          setIsLoadingAudit(false)
        }
      })
      .catch(() => {
        if (!isCancelled) setIsLoadingAudit(false)
      })

    return () => {
      isCancelled = true
    }
  }, [evidence, fund, profile])

  const handleAskQuestion = async (queryText: string) => {
    if (!queryText.trim() || isAsking) return
    setIsAsking(true)
    setAnswer(null)
    setIsOpenChat(true)

    try {
      const res = await askCoPilot(queryText, { evidence, fund, profile })
      setAnswer(res)
    } catch (e: any) {
      setAnswer('Could not reach AI co-pilot. Please check your AI settings.')
    } finally {
      setIsAsking(false)
    }
  }

  const currentConfig = getAIConfig()
  const providerLabel =
    currentConfig.provider === 'ollama'
      ? `Local Ollama (${currentConfig.ollamaModel})`
      : currentConfig.provider === 'groq'
      ? `Groq Cloud (${currentConfig.groqModel.split('-')[0]})`
      : 'Offline Heuristics'

  return (
    <div className="rounded-2xl bg-slate-950/70 border border-slate-800/80 p-5 shadow-xl transition-all">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4 pb-3 border-b border-slate-800/80">
        <div className="flex items-center space-x-2.5">
          <div className="p-2 rounded-xl bg-teal-500/10 text-teal-400 border border-teal-500/20">
            <Bot className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h4 className="text-sm font-bold text-white">AI Co-Pilot & Decision Audit</h4>
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700">
                {providerLabel}
              </span>
            </div>
            <p className="text-[11px] text-slate-400">
              Adversarial second opinion stress-testing the quantitative recommendation.
            </p>
          </div>
        </div>

        <button
          onClick={onOpenSettings}
          className="px-2.5 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-300 text-xs font-semibold flex items-center space-x-1.5 transition-all border border-slate-800 self-start sm:self-auto"
        >
          <Sliders className="w-3.5 h-3.5 text-teal-400" />
          <span>Configure AI</span>
        </button>
      </div>

      {/* Audit Results */}
      {isLoadingAudit ? (
        <div className="py-6 flex items-center justify-center space-x-2 text-xs text-slate-400">
          <RotateCw className="w-4 h-4 animate-spin text-teal-400" />
          <span>Auditing decision against risk constraints...</span>
        </div>
      ) : audit ? (
        <div className="space-y-4">
          {/* Confidence Score & Behavioral Check Banner */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {/* Confidence Score */}
            <div className="p-3.5 rounded-xl bg-slate-900 border border-slate-800 flex flex-col justify-between">
              <span className="text-[11px] text-slate-400 uppercase font-semibold tracking-wider">
                AI Confidence Rating
              </span>
              <div className="flex items-baseline space-x-2 mt-1">
                <span
                  className={`text-2xl font-black ${
                    audit.confidencePct >= 80
                      ? 'text-emerald-400'
                      : audit.confidencePct >= 65
                      ? 'text-amber-400'
                      : 'text-rose-400'
                  }`}
                >
                  {audit.confidencePct}%
                </span>
                <span
                  className={`text-xs font-bold px-2 py-0.5 rounded-md border ${
                    audit.confidenceLevel === 'High'
                      ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30'
                      : audit.confidenceLevel === 'Moderate'
                      ? 'bg-amber-500/10 text-amber-300 border-amber-500/30'
                      : 'bg-rose-500/10 text-rose-300 border-rose-500/30'
                  }`}
                >
                  {audit.confidenceLevel}
                </span>
              </div>
              <span className="text-[10px] text-slate-500 mt-1">
                Calibrated across 4 risk vectors
              </span>
            </div>

            {/* Behavioral Alignment */}
            <div className="sm:col-span-2 p-3.5 rounded-xl bg-slate-900 border border-slate-800">
              <div className="flex items-center space-x-1.5 text-xs font-bold text-slate-300 mb-1">
                {audit.behavioralCheck.aligned ? (
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                ) : (
                  <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                )}
                <span>Psychological & Risk Alignment</span>
              </div>
              <p className="text-xs text-slate-300 leading-relaxed">
                {audit.behavioralCheck.note}
              </p>
              {audit.suggestedAdjustment && (
                <div className="mt-2 text-[11px] font-semibold text-amber-300 bg-amber-500/10 px-2.5 py-1 rounded-lg border border-amber-500/20">
                  {audit.suggestedAdjustment}
                </div>
              )}
            </div>
          </div>

          {/* Adversarial Red-Teaming Checklist */}
          <div className="p-3.5 rounded-xl bg-slate-900 border border-slate-800">
            <div className="flex items-center space-x-1.5 text-xs font-bold text-slate-300 uppercase tracking-wider mb-2">
              <ShieldAlert className="w-3.5 h-3.5 text-amber-400" />
              <span>Adversarial Pre-Mortem (What Could Go Wrong)</span>
            </div>
            <ul className="space-y-1.5 text-xs text-slate-300">
              {audit.redTeamRisks.map((risk, idx) => (
                <li key={idx} className="flex items-start space-x-2">
                  <span className="text-amber-400 font-bold">•</span>
                  <span>{risk}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}

      {/* Interactive "Ask Your Co-Pilot" Box */}
      <div className="mt-4 pt-3 border-t border-slate-800/80">
        <div className="flex items-center justify-between mb-2.5">
          <div className="flex items-center space-x-1.5 text-xs font-bold text-teal-400">
            <MessageSquare className="w-3.5 h-3.5" />
            <span>Ask Your AI Co-Pilot Anything</span>
          </div>

          <button
            onClick={() => setIsOpenChat(!isOpenChat)}
            className="text-[11px] font-semibold text-slate-400 hover:text-white flex items-center space-x-1"
          >
            <span>{isOpenChat ? 'Hide Q&A' : 'Open Q&A'}</span>
            {isOpenChat ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </button>
        </div>

        {/* Quick Question Chips */}
        <div className="flex flex-wrap gap-1.5 mb-3">
          {quickQuestions.map((q, idx) => (
            <button
              key={idx}
              onClick={() => {
                setQuestion(q)
                handleAskQuestion(q)
              }}
              className="text-[11px] px-2.5 py-1 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-300 hover:text-white border border-slate-800 transition-all text-left"
            >
              {q}
            </button>
          ))}
        </div>

        {/* Interactive Chat Input & Answer Display */}
        {isOpenChat && (
          <div className="space-y-3 animate-fadeIn">
            {/* Answer Display */}
            {isAsking ? (
              <div className="p-3.5 rounded-xl bg-slate-900 border border-slate-800 text-xs text-slate-400 flex items-center space-x-2">
                <RotateCw className="w-4 h-4 animate-spin text-teal-400" />
                <span>Thinking through market context...</span>
              </div>
            ) : answer ? (
              <div className="p-4 rounded-xl bg-slate-900 border border-teal-500/30 text-xs text-slate-200 leading-relaxed shadow-lg">
                <div className="text-[10px] font-bold text-teal-400 uppercase tracking-wider mb-1 flex items-center space-x-1">
                  <Sparkles className="w-3 h-3" />
                  <span>AI Co-Pilot Answer</span>
                </div>
                <div className="whitespace-pre-line">{answer}</div>
              </div>
            ) : null}

            {/* Input form */}
            <div className="flex items-center space-x-2">
              <input
                type="text"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleAskQuestion(question)
                }}
                placeholder="Ask a question about this recommendation (e.g., 'What if Nifty drops 10%?')"
                className="flex-grow bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-teal-500"
              />
              <button
                onClick={() => handleAskQuestion(question)}
                disabled={isAsking || !question.trim()}
                className="px-3.5 py-2 rounded-xl bg-teal-600 hover:bg-teal-500 text-white text-xs font-semibold flex items-center space-x-1 disabled:opacity-50 transition-all shrink-0"
              >
                <span>Ask</span>
                <Send className="w-3 h-3" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
