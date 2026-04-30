import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApp } from '../context/AppContext'

export default function ProtocolReview() {
  const { protocol, setProtocol } = useApp()
  const navigate = useNavigate()
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

  function safeStr(val) {
    if (val === null || val === undefined) return '—'
    if (typeof val === 'string') return val
    if (typeof val === 'number') return String(val)
    if (typeof val === 'object') {
      if (val.label) return val.label
      if (val.name) return val.name
      if (val.condition) return val.condition
      return JSON.stringify(val)
    }
    return String(val)
  }

  const targetCohort = protocol.target_cohort || protocol.cohort_definition
  const obsWindow = targetCohort?.observation_window || protocol.observation_window || protocol.time_windows?.calendar_window
  const outcome = protocol.outcome_cohort || protocol.outcome

  const [editableFields, setEditableFields] = useState({
    study_type: safeStr(protocol.study_type),
    condition: safeStr(targetCohort?.label || targetCohort?.condition || targetCohort?.name),
    outcome: outcome?.required === false ? 'Not specified' : safeStr(outcome?.label || outcome?.name || outcome?.condition || outcome),
    comparator: protocol.comparator?.enabled ? safeStr(protocol.comparator?.label || protocol.comparator?.definition) : 'None',
    original_question: safeStr(protocol.original_question),
  })

  function handleApprove() {
    const updated = {
      ...protocol,
      study_type: editableFields.study_type,
      original_question: editableFields.original_question,
    }
    setProtocol(updated)
    navigate('/concepts')
  }

  return (
    <div className="max-w-6xl mx-auto">
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

      <div className="grid grid-cols-12 gap-8">
        <div className="col-span-7 bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
          <div className="px-6 py-4 border-b border-slate-100 bg-slate-50/50 flex justify-between items-center">
            <h3 className="font-semibold text-slate-900 flex items-center gap-2">
              <span className="material-symbols-outlined text-teal-600">article</span>
              Structured Protocol Definition
            </h3>
            <span className="text-[11px] font-bold text-slate-400 bg-slate-100 px-2 py-1 rounded">AI GENERATED</span>
          </div>

          <div className="px-6 pb-6 pt-6">
            <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4">Review & Edit Protocol</p>
            <div className="space-y-4">

              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1">Study Type</label>
                <select
                  value={editableFields.study_type}
                  onChange={(e) => setEditableFields(prev => ({ ...prev, study_type: e.target.value }))}
                  className="w-full text-sm text-slate-800 bg-white border border-slate-200 rounded-lg px-3 py-2 focus:ring-2 focus:ring-teal-500/20 outline-none"
                >
                  <option value="cohort_characterization">Cohort Characterization</option>
                  <option value="incidence_analysis">Incidence Analysis</option>
                  <option value="lab_value_summary">Lab Value Summary</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1">AI Interpreted Question <span className="text-slate-400 font-normal">(read-only)</span></label>
                <p className="text-sm text-slate-600 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2">{protocol?.normalized_question || '—'}</p>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1">Patient Population</label>
                <textarea
                  value={editableFields.condition}
                  onChange={(e) => setEditableFields(prev => ({ ...prev, condition: e.target.value }))}
                  rows={2}
                  className="w-full text-sm text-slate-800 bg-white border border-slate-200 rounded-lg px-3 py-2 focus:ring-2 focus:ring-teal-500/20 outline-none resize-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-500 mb-1">Minimum Age (years)</label>
                  <input
                    type="number"
                    value={protocol?.target_cohort?.demographic_filters?.age?.min ?? ''}
                    onChange={(e) => {
                      const updated = JSON.parse(JSON.stringify(protocol))
                      if (updated.target_cohort?.demographic_filters?.age) {
                        updated.target_cohort.demographic_filters.age.min = Number(e.target.value)
                        setProtocol(updated)
                      }
                    }}
                    className="w-full text-sm text-slate-800 bg-white border border-slate-200 rounded-lg px-3 py-2 focus:ring-2 focus:ring-teal-500/20 outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-500 mb-1">Maximum Age (years)</label>
                  <input
                    type="number"
                    value={protocol?.target_cohort?.demographic_filters?.age?.max ?? ''}
                    onChange={(e) => {
                      const updated = JSON.parse(JSON.stringify(protocol))
                      if (updated.target_cohort?.demographic_filters?.age) {
                        updated.target_cohort.demographic_filters.age.max = Number(e.target.value) || null
                        setProtocol(updated)
                      }
                    }}
                    placeholder="No limit"
                    className="w-full text-sm text-slate-800 bg-white border border-slate-200 rounded-lg px-3 py-2 focus:ring-2 focus:ring-teal-500/20 outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-2">Sex Filter</label>
                <div className="flex gap-4">
                  {['male', 'female', 'unknown'].map(sex => (
                    <label key={sex} className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={protocol?.target_cohort?.demographic_filters?.sex?.includes(sex) ?? true}
                        onChange={(e) => {
                          const updated = JSON.parse(JSON.stringify(protocol))
                          const current = updated.target_cohort?.demographic_filters?.sex || []
                          updated.target_cohort.demographic_filters.sex = e.target.checked
                            ? [...current, sex]
                            : current.filter(s => s !== sex)
                          setProtocol(updated)
                        }}
                        className="rounded border-slate-300 text-teal-600"
                      />
                      <span className="text-sm text-slate-700 capitalize">{sex}</span>
                    </label>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-500 mb-1">Study Period Start</label>
                  <input
                    type="date"
                    value={protocol?.time_windows?.calendar_window?.start_date || ''}
                    onChange={(e) => {
                      const updated = JSON.parse(JSON.stringify(protocol))
                      if (updated.time_windows?.calendar_window) {
                        updated.time_windows.calendar_window.start_date = e.target.value
                        setProtocol(updated)
                      }
                    }}
                    className="w-full text-sm text-slate-800 bg-white border border-slate-200 rounded-lg px-3 py-2 focus:ring-2 focus:ring-teal-500/20 outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-500 mb-1">Study Period End</label>
                  <input
                    type="date"
                    value={protocol?.time_windows?.calendar_window?.end_date || ''}
                    onChange={(e) => {
                      const updated = JSON.parse(JSON.stringify(protocol))
                      if (updated.time_windows?.calendar_window) {
                        updated.time_windows.calendar_window.end_date = e.target.value
                        setProtocol(updated)
                      }
                    }}
                    className="w-full text-sm text-slate-800 bg-white border border-slate-200 rounded-lg px-3 py-2 focus:ring-2 focus:ring-teal-500/20 outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1">Outcome of Interest</label>
                <input
                  type="text"
                  value={editableFields.outcome}
                  onChange={(e) => setEditableFields(prev => ({ ...prev, outcome: e.target.value }))}
                  placeholder="Not specified"
                  className="w-full text-sm text-slate-800 bg-white border border-slate-200 rounded-lg px-3 py-2 focus:ring-2 focus:ring-teal-500/20 outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1">Comparator Group</label>
                <input
                  type="text"
                  value={editableFields.comparator}
                  onChange={(e) => setEditableFields(prev => ({ ...prev, comparator: e.target.value }))}
                  placeholder="None"
                  className="w-full text-sm text-slate-800 bg-white border border-slate-200 rounded-lg px-3 py-2 focus:ring-2 focus:ring-teal-500/20 outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1">SQL Template <span className="text-slate-400 font-normal">(read-only)</span></label>
                <p className="text-sm text-slate-600 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 font-mono">{protocol?.execution?.sql_template || '—'}</p>
              </div>

              {protocol?.issues?.warnings?.length > 0 && (
                <div>
                  <label className="block text-xs font-semibold text-slate-500 mb-2">
                    AI Warnings <span className="text-slate-400 font-normal">(read-only)</span>
                  </label>
                  <div className="space-y-2">
                    {protocol.issues.warnings.map((w, i) => (
                      <div key={i} className="flex items-start gap-2 text-sm text-slate-600 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2">
                        <span className="material-symbols-outlined text-amber-500 text-sm mt-0.5 shrink-0">warning</span>
                        <div>
                          <span className="font-semibold text-amber-700 text-xs uppercase tracking-wide">{w.code}: </span>
                          <span>{w.message}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {protocol?.assumptions?.length > 0 && (
                <div>
                  <label className="block text-xs font-semibold text-slate-500 mb-2">
                    AI Assumptions <span className="text-slate-400 font-normal">(read-only)</span>
                  </label>
                  <div className="space-y-2">
                    {protocol.assumptions.map((a, i) => (
                      <div key={i} className="flex items-start gap-2 text-sm text-slate-600 bg-blue-50 border border-blue-100 rounded-lg px-3 py-2">
                        <span className="material-symbols-outlined text-blue-500 text-sm mt-0.5 shrink-0">info</span>
                        <span>{a}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

            </div>
            {parseError && (
              <p className="text-red-600 text-xs mt-3 flex items-center gap-1">
                <span className="material-symbols-outlined text-sm">error</span>
                {parseError}
              </p>
            )}
          </div>
        </div>

        <div className="col-span-5 flex flex-col gap-6">
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
            <h3 className="font-semibold text-slate-900 flex items-center gap-2 mb-4">
              <span className="material-symbols-outlined text-[#0D9488]">verified</span>
              Protocol Summary
            </h3>
            <div className="space-y-3">
              <div className="flex items-center justify-between p-3 border border-slate-100 rounded-lg">
                <span className="text-sm text-slate-600">Study type</span>
                <span className="text-sm font-semibold text-slate-900 capitalize">{editableFields.study_type?.replace(/_/g, ' ')}</span>
              </div>
              <div className="flex items-center justify-between p-3 border border-slate-100 rounded-lg">
                <span className="text-sm text-slate-600">Concepts to validate</span>
                <span className="text-sm font-semibold text-teal-600">{protocol?.concept_sets?.length || 2} terms</span>
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
