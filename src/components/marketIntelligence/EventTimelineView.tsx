import React from 'react'
import { EventObservation } from '../../engine/marketIntelligence/types'
import { Calendar, ExternalLink, Zap, Award, BarChart2, ShieldCheck, AlertTriangle } from 'lucide-react'

interface EventTimelineViewProps {
  events: EventObservation[]
}

export const EventTimelineView: React.FC<EventTimelineViewProps> = ({ events }) => {
  if (events.length === 0) {
    return (
      <div className="p-6 rounded-3xl bg-slate-900/60 border border-slate-800 text-center text-xs text-slate-500">
        No recent material events recorded for this entity.
      </div>
    )
  }

  const getSurpriseBadge = (cat: string, pct: number) => {
    if (cat.includes('Better than Expected')) {
      return (
        <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
          ▲ {cat} (+{pct}%)
        </span>
      )
    } else if (cat.includes('Below Expected') || cat.includes('Worse')) {
      return (
        <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-rose-500/10 text-rose-400 border border-rose-500/30">
          ▼ {cat} ({pct}%)
        </span>
      )
    }
    return (
      <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-slate-500/10 text-slate-300 border border-slate-500/30">
        ◆ In Line with Expectations
      </span>
    )
  }

  return (
    <div className="p-6 rounded-3xl bg-slate-900/80 border border-white/[0.08] shadow-2xl space-y-4">
      <div className="flex items-center justify-between pb-3 border-b border-white/[0.06]">
        <div>
          <span className="text-[10px] uppercase font-bold tracking-widest text-emerald-400">
            Information State & Event Timeline
          </span>
          <h3 className="text-base font-bold text-white mt-0.5">
            Real Events & Information Surprise Reactions
          </h3>
        </div>
        <span className="text-xs text-slate-500">
          {events.length} Event{events.length > 1 ? 's' : ''} Tracked
        </span>
      </div>

      <div className="relative pl-6 space-y-6 before:absolute before:top-2 before:bottom-2 before:left-2.5 before:w-0.5 before:bg-white/[0.08]">
        {events.map((evt) => {
          const pubDate = new Date(evt.published_at).toLocaleDateString('en-IN', {
            day: 'numeric',
            month: 'short',
            year: 'numeric'
          })

          return (
            <div key={evt.event_id} className="relative group">
              {/* Timeline Node Icon */}
              <div className="absolute -left-6 top-1 w-3.5 h-3.5 rounded-full bg-slate-900 border-2 border-emerald-400 group-hover:scale-125 transition-transform" />

              <div className="p-4 rounded-2xl bg-white/[0.02] hover:bg-white/[0.04] border border-white/[0.06] transition-all space-y-2.5">
                {/* Event Header */}
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center space-x-2">
                    <span className="px-2 py-0.5 rounded-md bg-white/[0.04] border border-white/[0.08] text-[10px] font-mono font-bold uppercase tracking-wider text-slate-400">
                      {evt.event_type} • {evt.event_subtype.replace('_', ' ')}
                    </span>
                    <span className="text-[11px] text-slate-500 font-mono">{pubDate}</span>
                  </div>

                  {getSurpriseBadge(evt.surprise_category, evt.surprise_pct)}
                </div>

                {/* Event Headline */}
                <h4 className="text-sm font-bold text-white leading-snug">
                  {evt.title}
                </h4>

                {/* Source Provenance & Metrics */}
                <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-400 pt-1 border-t border-white/[0.04]">
                  <div className="flex items-center space-x-1.5">
                    <span className="text-slate-500">Source:</span>
                    <span className="text-slate-300 font-medium">{evt.source}</span>
                    <span className="text-slate-600">({evt.source_type})</span>
                  </div>

                  <div className="flex items-center space-x-3 text-[11px]">
                    {evt.actual_value !== 0 && (
                      <span className="font-mono">
                        Actual: <strong className="text-white">{evt.actual_value}</strong> vs Exp:{' '}
                        <strong className="text-slate-400">{evt.expected_value}</strong>
                      </span>
                    )}

                    {evt.source_url && evt.source_url !== '#' && (
                      <a
                        href={evt.source_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-emerald-400 hover:text-emerald-300 flex items-center space-x-0.5"
                      >
                        <span>Filing</span>
                        <ExternalLink className="w-2.5 h-2.5" />
                      </a>
                    )}
                  </div>
                </div>

                {/* Multi-Dimensional Sentiment Chips */}
                {evt.sentiment_dimensions && (
                  <div className="flex flex-wrap gap-2 pt-1 text-[10px] font-mono">
                    <span className="px-2 py-0.5 rounded bg-white/[0.02] border border-white/[0.04] text-slate-400">
                      Financial:{' '}
                      <strong
                        className={
                          evt.sentiment_dimensions.financial >= 0 ? 'text-emerald-400' : 'text-rose-400'
                        }
                      >
                        {evt.sentiment_dimensions.financial >= 0 ? '+' : ''}
                        {evt.sentiment_dimensions.financial}
                      </strong>
                    </span>
                    <span className="px-2 py-0.5 rounded bg-white/[0.02] border border-white/[0.04] text-slate-400">
                      Operational:{' '}
                      <strong className="text-slate-300">{evt.sentiment_dimensions.operational}</strong>
                    </span>
                    <span className="px-2 py-0.5 rounded bg-white/[0.02] border border-white/[0.04] text-slate-400">
                      Product/Brand:{' '}
                      <strong className="text-slate-300">
                        {((evt.sentiment_dimensions.product + evt.sentiment_dimensions.brand) / 2).toFixed(2)}
                      </strong>
                    </span>
                    <span className="px-2 py-0.5 rounded bg-white/[0.02] border border-white/[0.04] text-slate-400">
                      Attention Z-Score:{' '}
                      <strong className="text-cyan-400">{evt.attention_zscore}σ</strong>
                    </span>
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
