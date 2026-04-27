import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApp } from '../context/AppContext'

export default function ProtocolReview() {
  const { protocol, setProtocol } = useApp()
  const navigate = useNavigate()
  const [draft, setDraft] = useState(protocol ? JSON.stringify(protocol, null, 2) : '')
  const [parseError, setParseError] = useState(null)

  if (!protocol) {
    return (
      <div className="max-w-2xl mx-auto text-center py-20">
        <span className="material-symbols-outlined text-slate-300 text-6xl">article</span>
        <h2 className="text-2xl font-bold text-slate-700 mt-4">No Protocol Available</h2>
        <p className="text-slate-500 mt-2 mb-6">Please go back and submit a clinical question first.</p>
        <button onClick={() => navigate('/')} className="px-6 py-2 bg-[#0D9488] text-white rounded-lg font-semibold hover:bg-[#0F766E] transition-all">
          Back to Study Designer
        </button>
      </div>
    )
  }

  function handleApprove() {
    try {
      const parsed = JSON.parse(draft)
      setProtocol(parsed)
      navigate('/concepts')
    } catch {
      setParseError('Invalid JSON — please fix before continuing.')
    }
  }

  const obs = protocol.cohort_definition?.observation_window
  const fields = [
    { label: 'Study Type', value: protocol.study_type },
    { label: 'Condition', value: protocol.cohort_definition?.condition },
    { label: 'Outcome', value: protocol.outcome },
    { label: 'Observation Window', value: obs ? `${obs.start_date} to ${obs.end_date}` : 'N/A' },
    { label: 'Comparator', value: protocol.comparator ?? 'None' },
    { label: 'Min Prior Observation', value: protocol.analysis_parameters?.min_prior_obs_days + ' days' },
  ]

  return (
    <div className="max-w-6xl mx-auto">
      {/* Page header */}
      <div className="flex justify-between items-start mb-8">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="px-2 py-0.5 bg-emerald-100 text-emerald-800 text-[10px] font-bold rounded uppercase tracking-wide">Validation Phase</span>
          </div>
          <h2 className="text-3xl font-bold text-slate-900">Protocol Review</h2>
          <p className="text-slate-500 mt-1">Review the AI-generated protocol and validate OMOP concept mappings.</p>
        </div>
        <div className="flex gap-3">
          <button onClick={() => navigate('/')} className="px-4 py-2 border border-slate-200 bg-white text-slate-700 font-semibold rounded-lg hover:bg-slate-50 transition-colors flex items-center gap-2 text-sm">
            <span className="material-symbols-outlined text-sm">arrow_back</span>
            Back
          </button>
          <button onClick={handleApprove} className="px-4 py-2 bg-[#0D9488] text-white font-semibold rounded-lg hover:bg-[#0F766E] transition-colors flex items-center gap-2 text-sm shadow-sm">
            <span className="material-symbols-outlined text-sm">play_circle</span>
            Approve & Continue
          </button>
        </div>
      </div>

      {/* Split view */}
      <div className="grid grid-cols-12 gap-8">
        {/* Left: Protocol fields */}
        <div className="col-span-7 bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
          <div className="px-6 py-4 border-b border-slate-100 bg-slate-50/50 flex justify-between items-center">
            <h3 className="font-semibold text-slate-900 flex items-center gap-2">
              <span className="material-symbols-outlined text-teal-600">article</span>
              Structured Protocol Definition
            </h3>
            <span className="text-[11px] font-bold text-slate-400 bg-slate-100 px-2 py-1 rounded">AI GENERATED</span>
          </div>
          <div className="p-6 space-y-3">
            {fields.map(({ label, value }) => (
              <div key={label} className="flex gap-4 p-3 rounded-lg bg-slate-50 border border-slate-100">
                <div className="w-40 shrink-0">
                  <p className="text-xs font-bold text-slate-400 uppercase tracking-wider">{label}</p>
                </div>
                <p className="text-sm text-slate-800 font-medium">{value || '—'}</p>
              </div>
            ))}
          </div>
          {/* Edit section */}
          <div className="px-6 pb-6">
            <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Edit Protocol (optional)</p>
            <textarea
              value={draft}
              onChange={(e) => { setDraft(e.target.value); setParseError(null) }}
              rows={8}
              className="w-full font-mono text-xs bg-slate-50 border border-slate-200 rounded-lg p-3 focus:ring-2 focus:ring-teal-500/20 outline-none resize-none"
            />
            {parseError && (
              <p className="text-red-600 text-xs mt-1 flex items-center gap-1">
                <span className="material-symbols-outlined text-sm">error</span>
                {parseError}
              </p>
            )}
          </div>
        </div>

        {/* Right: AI insight card */}
        <div className="col-span-5 flex flex-col gap-6">
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
            <h3 className="font-semibold text-slate-900 flex items-center gap-2 mb-4">
              <span className="material-symbols-outlined text-[#0D9488]">verified</span>
              Protocol Summary
            </h3>
            <div className="space-y-3">
              <div className="flex items-center justify-between p-3 border border-slate-100 rounded-lg">
                <span className="text-sm text-slate-600">Study type</span>
                <span className="text-sm font-semibold text-slate-900 capitalize">{protocol.study_type?.replace('_', ' ')}</span>
              </div>
              <div className="flex items-center justify-between p-3 border border-slate-100 rounded-lg">
                <span className="text-sm text-slate-600">Concepts to validate</span>
                <span className="text-sm font-semibold text-teal-600">2 terms</span>
              </div>
              <div className="flex items-center justify-between p-3 border border-slate-100 rounded-lg">
                <span className="text-sm text-slate-600">Ready for execution</span>
                <span className="text-sm font-semibold text-amber-600">Pending review</span>
              </div>
            </div>
          </div>

          <div className="bg-gradient-to-br from-teal-600 to-teal-800 rounded-xl p-6 text-white shadow-lg relative overflow-hidden">
            <div className="absolute -right-4 -bottom-4 opacity-10">
              <span className="material-symbols-outlined text-9xl">psychology</span>
            </div>
            <div className="relative z-10">
              <div className="flex items-center gap-2 mb-3">
                <span className="material-symbols-outlined bg-white/20 p-1 rounded text-sm">lightbulb</span>
                <span className="text-xs font-bold uppercase tracking-widest text-teal-100">AI Insight</span>
              </div>
              <p className="text-sm font-medium leading-relaxed mb-4">
                Review the protocol fields carefully. Once approved, OMOP concept IDs will be validated against the ATHENA vocabulary before query execution.
              </p>
              <button onClick={handleApprove} className="text-xs font-bold bg-white text-teal-700 px-3 py-1.5 rounded flex items-center gap-1 hover:bg-teal-50 transition-colors">
                Approve & Validate
                <span className="material-symbols-outlined text-xs">arrow_forward</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
