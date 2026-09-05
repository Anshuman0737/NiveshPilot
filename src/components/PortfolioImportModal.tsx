import React, { useState, useRef } from 'react'
import { Holding, FundSnapshot } from '../engine/types'
import {
  parsePortfolioText,
  parsePdfFile,
  parseScreenshotImage,
  SAMPLE_PORTFOLIO_PRESETS,
  ParsedPortfolioResult
} from '../engine/portfolioParser'
import {
  X,
  FileText,
  Camera,
  Clipboard,
  Sparkles,
  ShieldCheck,
  UploadCloud,
  CheckCircle,
  AlertCircle,
  ArrowRight
} from 'lucide-react'

interface PortfolioImportModalProps {
  isOpen: boolean
  onClose: () => void
  onImport: (holdings: Holding[]) => void
  knownFunds: FundSnapshot[]
}

type TabType = 'pdf' | 'screenshot' | 'text' | 'presets'

export const PortfolioImportModal: React.FC<PortfolioImportModalProps> = ({
  isOpen,
  onClose,
  onImport,
  knownFunds
}) => {
  const [activeTab, setActiveTab] = useState<TabType>('pdf')
  const [isProcessing, setIsProcessing] = useState(false)
  const [parseResult, setParseResult] = useState<ParsedPortfolioResult | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [pastedText, setPastedText] = useState('')

  const fileInputRef = useRef<HTMLInputElement>(null)
  const imageInputRef = useRef<HTMLInputElement>(null)

  if (!isOpen) return null

  const formatINR = (val: number) =>
    new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(val)

  const handlePdfUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setIsProcessing(true)
    setErrorMsg(null)
    try {
      const result = await parsePdfFile(file, knownFunds)
      setParseResult(result)
    } catch (err: any) {
      setErrorMsg('Could not parse PDF. Try pasting text or select a preset.')
    } finally {
      setIsProcessing(false)
    }
  }

  const handleScreenshotUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setIsProcessing(true)
    setErrorMsg(null)
    try {
      const result = await parseScreenshotImage(file, knownFunds)
      setParseResult(result)
    } catch (err: any) {
      setErrorMsg('Could not process screenshot. Try uploading a clearer image or paste text.')
    } finally {
      setIsProcessing(false)
    }
  }

  const handleParseText = () => {
    if (!pastedText.trim()) {
      setErrorMsg('Please paste some statement text or fund holdings first.')
      return
    }
    setIsProcessing(true)
    setErrorMsg(null)
    try {
      const result = parsePortfolioText(pastedText, knownFunds)
      setParseResult(result)
    } catch (err: any) {
      setErrorMsg('Failed to extract funds. Try using one of our sample presets.')
    } finally {
      setIsProcessing(false)
    }
  }

  const handleSelectPreset = (key: string) => {
    const preset = SAMPLE_PORTFOLIO_PRESETS[key]
    if (preset) {
      setParseResult({
        holdings: preset.holdings,
        source: 'preset',
        schemesDetectedCount: preset.holdings.length,
        unrecognizedSchemesCount: 0,
        rawTextPreview: preset.title
      })
      setErrorMsg(null)
    }
  }

  const handleApply = () => {
    if (parseResult && parseResult.holdings.length > 0) {
      onImport(parseResult.holdings)
      onClose()
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-navy-950/85 backdrop-blur-md animate-fade-in">
      <div className="w-full max-w-2xl bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow-2xl overflow-hidden max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-slate-800">
          <div>
            <div className="inline-flex items-center space-x-1.5 px-2.5 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-[11px] font-bold uppercase tracking-wider mb-1">
              <Sparkles className="w-3 h-3" />
              <span>Smart Portfolio Import</span>
            </div>
            <h3 className="text-xl font-extrabold text-white tracking-tight">
              Import Existing Investments
            </h3>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-slate-400 hover:text-white rounded-xl hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Client-Side Privacy Guarantee Banner */}
        <div className="my-4 p-3 rounded-2xl bg-emerald-950/30 border border-emerald-800/40 flex items-start space-x-3">
          <ShieldCheck className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
          <div className="text-xs text-slate-300 leading-relaxed">
            <strong className="text-emerald-300 font-semibold">100% Client-Side Private (₹0 Cost):</strong>{' '}
            Your statement files and numbers never leave your device. All parsing runs directly in your local browser sandbox. Zero broker passwords required.
          </div>
        </div>

        {/* Tab Selector */}
        <div className="grid grid-cols-4 gap-1 p-1 bg-slate-950 rounded-2xl border border-slate-800 mb-4">
          <button
            onClick={() => { setActiveTab('pdf'); setParseResult(null); setErrorMsg(null); }}
            className={`flex items-center justify-center space-x-1.5 py-2 px-2 rounded-xl text-xs font-bold transition-all ${
              activeTab === 'pdf'
                ? 'bg-indigo-600 text-white shadow-lg'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <FileText className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">PDF CAS</span>
            <span className="sm:hidden">PDF</span>
          </button>

          <button
            onClick={() => { setActiveTab('screenshot'); setParseResult(null); setErrorMsg(null); }}
            className={`flex items-center justify-center space-x-1.5 py-2 px-2 rounded-xl text-xs font-bold transition-all ${
              activeTab === 'screenshot'
                ? 'bg-indigo-600 text-white shadow-lg'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Camera className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Screenshot</span>
            <span className="sm:hidden">Image</span>
          </button>

          <button
            onClick={() => { setActiveTab('text'); setParseResult(null); setErrorMsg(null); }}
            className={`flex items-center justify-center space-x-1.5 py-2 px-2 rounded-xl text-xs font-bold transition-all ${
              activeTab === 'text'
                ? 'bg-indigo-600 text-white shadow-lg'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Clipboard className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Paste Text</span>
            <span className="sm:hidden">Text</span>
          </button>

          <button
            onClick={() => { setActiveTab('presets'); setParseResult(null); setErrorMsg(null); }}
            className={`flex items-center justify-center space-x-1.5 py-2 px-2 rounded-xl text-xs font-bold transition-all ${
              activeTab === 'presets'
                ? 'bg-indigo-600 text-white shadow-lg'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Presets</span>
            <span className="sm:hidden">Demo</span>
          </button>
        </div>

        {/* Tab Contents */}
        <div className="flex-1 overflow-y-auto pr-1 space-y-4">
          {/* Tab 1: PDF Upload */}
          {activeTab === 'pdf' && (
            <div className="space-y-3">
              <div
                onClick={() => fileInputRef.current?.click()}
                className="border-2 border-dashed border-slate-700 hover:border-indigo-500 rounded-2xl p-6 text-center cursor-pointer bg-slate-950/50 hover:bg-indigo-950/10 transition-all"
              >
                <UploadCloud className="w-10 h-10 text-indigo-400 mx-auto mb-2 animate-pulse" />
                <h4 className="text-sm font-bold text-white mb-1">
                  Upload CAMS or KFintech CAS Statement (.pdf)
                </h4>
                <p className="text-xs text-slate-400 max-w-sm mx-auto mb-3">
                  Standard Consolidated Account Statement (CAS) from CAMS/KFintech or broker report.
                </p>
                <span className="inline-block px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold">
                  Select PDF File
                </span>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf"
                  className="hidden"
                  onChange={handlePdfUpload}
                />
              </div>
            </div>
          )}

          {/* Tab 2: Screenshot Upload */}
          {activeTab === 'screenshot' && (
            <div className="space-y-3">
              <div
                onClick={() => imageInputRef.current?.click()}
                className="border-2 border-dashed border-slate-700 hover:border-indigo-500 rounded-2xl p-6 text-center cursor-pointer bg-slate-950/50 hover:bg-indigo-950/10 transition-all"
              >
                <Camera className="w-10 h-10 text-indigo-400 mx-auto mb-2" />
                <h4 className="text-sm font-bold text-white mb-1">
                  Upload Broker App Screenshot (.png, .jpg)
                </h4>
                <p className="text-xs text-slate-400 max-w-sm mx-auto mb-3">
                  Snap of your Groww, Zerodha Coin, INDmoney, or Kuvera mutual fund portfolio screen.
                </p>
                <span className="inline-block px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold">
                  Select Screenshot Image
                </span>
                <input
                  ref={imageInputRef}
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={handleScreenshotUpload}
                />
              </div>
            </div>
          )}

          {/* Tab 3: Paste Text */}
          {activeTab === 'text' && (
            <div className="space-y-3">
              <label className="block text-xs font-semibold text-slate-400">
                Paste Email Summary, Statement Rows, or Scheme List:
              </label>
              <textarea
                value={pastedText}
                onChange={(e) => setPastedText(e.target.value)}
                placeholder={"Example:\nParag Parikh Flexi Cap Fund - Invested: ₹60,000, Current: ₹72,000\nHDFC Mid-Cap Opportunities Fund - Invested: ₹40,000, Current: ₹48,000\nMirae Asset Large Cap Fund - ₹50,000"}
                className="w-full h-32 p-3 rounded-2xl bg-slate-950 border border-slate-800 text-xs text-white placeholder-slate-600 focus:outline-none focus:border-indigo-500 font-mono leading-relaxed resize-none"
              />
              <button
                onClick={handleParseText}
                disabled={isProcessing}
                className="w-full py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-bold text-xs transition-colors"
              >
                {isProcessing ? 'Parsing Statement...' : 'Extract Holdings From Text'}
              </button>
            </div>
          )}

          {/* Tab 4: 1-Click Presets */}
          {activeTab === 'presets' && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              {Object.entries(SAMPLE_PORTFOLIO_PRESETS).map(([key, item]) => (
                <div
                  key={key}
                  onClick={() => handleSelectPreset(key)}
                  className="p-3.5 rounded-2xl bg-slate-950 border border-slate-800 hover:border-indigo-500/50 cursor-pointer transition-all text-left group"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-bold text-white group-hover:text-indigo-300">
                      {item.title}
                    </span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">
                      {item.holdings.length} funds
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400 line-clamp-2 leading-relaxed">
                    {item.desc}
                  </p>
                </div>
              ))}
            </div>
          )}

          {/* Error Message */}
          {errorMsg && (
            <div className="p-3 rounded-xl bg-rose-950/40 border border-rose-900/50 text-rose-300 text-xs flex items-center space-x-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}

          {/* Extracted Holdings Preview */}
          {parseResult && parseResult.holdings.length > 0 && (
            <div className="p-4 rounded-2xl bg-slate-950 border border-emerald-800/40 mt-3">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center space-x-2 text-emerald-400 text-xs font-bold">
                  <CheckCircle className="w-4 h-4" />
                  <span>{parseResult.schemesDetectedCount} Mutual Funds Detected</span>
                </div>
                <span className="text-xs text-slate-400">
                  Total:{' '}
                  <strong className="text-white">
                    {formatINR(
                      parseResult.holdings.reduce((acc, h) => acc + h.currentValue, 0)
                    )}
                  </strong>
                </span>
              </div>

              <div className="space-y-2 max-h-40 overflow-y-auto pr-1">
                {parseResult.holdings.map((h, idx) => (
                  <div
                    key={idx}
                    className="p-2.5 rounded-xl bg-slate-900 border border-slate-800/80 flex items-center justify-between text-xs"
                  >
                    <div>
                      <div className="font-bold text-white">{h.fundName}</div>
                      <div className="text-[11px] text-slate-400">{h.category}</div>
                    </div>
                    <div className="text-right">
                      <div className="font-bold text-emerald-400">{formatINR(h.currentValue)}</div>
                      <div className="text-[10px] text-slate-500">Inv: {formatINR(h.investedAmount)}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Footer CTAs */}
        <div className="pt-4 border-t border-slate-800 mt-4 flex items-center justify-end space-x-3">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-400 hover:text-white transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleApply}
            disabled={!parseResult || parseResult.holdings.length === 0}
            className="px-5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 disabled:hover:bg-emerald-600 text-white font-bold text-xs flex items-center space-x-1.5 transition-all shadow-lg shadow-emerald-950/40"
          >
            <span>Import & Optimize Portfolio</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  )
}
