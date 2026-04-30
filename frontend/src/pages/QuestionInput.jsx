import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { generateProtocolStream } from '../services/api'
import { useApp } from '../context/AppContext'

const EVENT_ICONS = {
  received: 'connect_without_contact',
  interpretation_attempt: 'psychology',
  interpretation_completed: 'check_circle',
  protocol_built: 'article',
  schema_validated: 'verified',
  verification_started: 'rate_review',
  verification_attempt: 'model_training',
  verification_call_started: 'timer',
  verification_call_completed: 'task_alt',
  verification_parsing: 'data_object',
  verification_validating: 'fact_check',
  verification_reasoning_recovery: 'auto_fix_high',
  verification_formatter_started: 'format_shapes',
  verification_repair: 'build',
  verification_model_fallback: 'swap_horiz',
  verification_succeeded: 'check_circle',
  verification_completed: 'done_all',
  error: 'error',
}

const EVENT_COLORS = {
  interpretation_completed: 'text-emerald-600',
  protocol_built: 'text-emerald-600',
  schema_validated: 'text-emerald-600',
  verification_succeeded: 'text-emerald-600',
  verification_completed: 'text-emerald-600',
  verification_repair: 'text-amber-600',
  verification_model_fallback: 'text-amber-600',
  error: 'text-rose-600',
}

export default function QuestionInput() {
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [events, setEvents] = useState([])
  const [elapsed, setElapsed] = useState(null)
  const [timerStart, setTimerStart] = useState(null)
  const { setProtocol, setAppError } = useApp()
  const navigate = useNavigate()

  useEffect(() => {
    if (!timerStart) return
    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - timerStart) / 1000))
    }, 1000)
    return () => clearInterval(interval)
  }, [timerStart])

  function handleSubmit() {
    if (!question.trim() || loading) return
    setLoading(true)
    setEvents([])
    setElapsed(null)
    setTimerStart(null)

    generateProtocolStream(
      question,
      (event) => {
        setEvents(prev => [...prev, { ...event, timestamp: new Date().toLocaleTimeString() }])
        if (event.event === 'verification_call_started') {
          setTimerStart(Date.now())
        }
        if (event.event === 'verification_call_completed') {
          setTimerStart(null)
          setElapsed(null)
        }
      },
      (protocol) => {
        setProtocol(protocol)
        setLoading(false)
        navigate('/protocol')
      },
      (errMsg) => {
        setAppError(errMsg)
        setLoading(false)
        navigate('/error')
      }
    )
  }

  return (
    <div className="max-w-4xl mx-auto w-full space-y-8">
      {/* Header */}
      <div className="text-center space-y-2">
        <h2 className="text-4xl font-bold tracking-tight text-slate-900">Ask Your Clinical Question</h2>
        <p className="text-lg text-slate-500 max-w-2xl mx-auto">
          Describe your research question in plain English. Our AI pipeline will generate a structured study protocol automatically.
        </p>
      </div>

      {/* Input Card */}
      <div className="relative group">
        <div className="absolute -inset-1 bg-gradient-to-r from-teal-500 to-blue-500 rounded-xl blur opacity-10 group-hover:opacity-20 transition duration-1000"></div>
        <div className="relative bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
          <div className="p-6">
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Enter your clinical question in plain English..."
              rows={6}
              disabled={loading}
              className="w-full border-none focus:ring-0 text-xl text-slate-800 placeholder-slate-300 resize-none outline-none font-light disabled:opacity-50"
            />
            <p className="text-xs text-slate-400 mt-1">{question.length} characters</p>
          </div>
          <div className="bg-slate-50 border-t border-slate-100 px-6 py-4 flex justify-end">
            <button
              onClick={handleSubmit}
              disabled={loading || !question.trim()}
              className="bg-[#0D9488] hover:bg-[#0F766E] disabled:opacity-50 disabled:cursor-not-allowed text-white px-6 py-2 rounded-lg font-semibold flex items-center gap-2 transition-all shadow-md active:scale-95 text-sm"
            >
              {loading ? (
                <>
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
                  Generating...
                </>
              ) : (
                <>
                  Generate Protocol
                  <span className="material-symbols-outlined text-lg">auto_awesome</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Live SSE Event Timeline */}
      {events.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-100 flex justify-between items-center">
            <p className="text-xs font-bold text-slate-400 uppercase tracking-wider">Pipeline Status</p>
            {elapsed !== null && (
              <span className="text-xs text-teal-600 font-mono animate-pulse">{elapsed}s elapsed</span>
            )}
          </div>
          <div className="p-4 space-y-2 max-h-80 overflow-y-auto">
            {events.map((ev, i) => (
              <div key={i} className="flex items-start gap-3">
                <span
                  className={`material-symbols-outlined text-sm mt-0.5 shrink-0 ${EVENT_COLORS[ev.event] || 'text-slate-400'}`}
                  style={{ fontVariationSettings: "'FILL' 1" }}
                >
                  {EVENT_ICONS[ev.event] || 'radio_button_unchecked'}
                </span>
                <div className="flex-1 min-w-0">
                  <p className={`text-sm ${EVENT_COLORS[ev.event] || 'text-slate-700'}`}>
                    {ev.message}
                  </p>
                  {ev.model && (
                    <span className="text-[10px] font-mono text-slate-400">{ev.model}{ev.attempt ? ` (attempt ${ev.attempt}/${ev.max_attempts})` : ''}</span>
                  )}
                </div>
                <span className="text-[10px] text-slate-400 shrink-0">{ev.timestamp}</span>
              </div>
            ))}
            {loading && (
              <div className="flex items-center gap-2 text-slate-400 text-sm">
                <div className="w-3 h-3 border-2 border-teal-500 border-t-transparent rounded-full animate-spin"></div>
                <span>Processing...</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Info banner */}
      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-8 bg-slate-900 rounded-xl p-6 text-white relative overflow-hidden flex flex-col justify-between min-h-[160px]">
          <div className="z-10">
            <span className="bg-teal-500/20 text-teal-300 px-2 py-1 rounded text-[10px] font-bold tracking-widest uppercase mb-4 inline-block">Enterprise Ready</span>
            <h4 className="text-xl font-semibold mb-2">Accelerated Evidence Generation</h4>
            <p className="text-slate-400 text-sm max-w-lg">RWE-Gen automates cohort definition using validated clinical ontologies and OHDSI standards.</p>
          </div>
          <div className="z-10 mt-4 flex gap-4">
            <div className="flex items-center gap-2">
              <span className="material-symbols-outlined text-teal-400 text-sm">verified</span>
              <span className="text-xs font-semibold text-slate-300">OMOP CDM V5.4</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="material-symbols-outlined text-teal-400 text-sm">security</span>
              <span className="text-xs font-semibold text-slate-300">HIPAA Compliant</span>
            </div>
          </div>
          <div className="absolute right-[-20%] bottom-[-20%] w-64 h-64 bg-teal-500/10 rounded-full blur-3xl"></div>
        </div>
        <div className="col-span-4 bg-white border border-slate-200 rounded-xl p-6 flex flex-col items-center justify-center text-center">
          <div className="w-16 h-16 bg-slate-50 rounded-full flex items-center justify-center mb-4 border border-slate-100">
            <span className="material-symbols-outlined text-slate-400 text-3xl">history</span>
          </div>
          <h4 className="font-semibold text-slate-900 mb-1">Recent Studies</h4>
          <p className="text-slate-500 text-sm mb-4">Quickly access previously generated protocols.</p>
          <button className="w-full py-2 border border-slate-200 rounded-lg text-sm font-semibold hover:bg-slate-50 transition-colors">View Library</button>
        </div>
      </div>
    </div>
  )
}
