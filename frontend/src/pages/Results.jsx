import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApp } from '../context/AppContext'
import { executeQuery } from '../services/api'

export default function Results() {
  const { protocol, validatedConcepts, setResults, setAppError, setProtocol, setValidatedConcepts } = useApp()
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!protocol || !validatedConcepts) return
    executeQuery(
      validatedConcepts?.protocol || protocol,
      validatedConcepts?.mapped || []
    )
      .then((res) => { setData(res); setResults(res) })
      .catch((err) => { setAppError(err.message); navigate('/error') })
      .finally(() => setLoading(false))
  }, [])

  if (!protocol || !validatedConcepts) {
    return (
      <div className="max-w-2xl mx-auto text-center py-20">
        <span className="material-symbols-outlined text-slate-300 text-6xl">bar_chart</span>
        <h2 className="text-2xl font-bold text-slate-700 mt-4">No Data Available</h2>
        <p className="text-slate-500 mt-2 mb-6">Please complete the full pipeline first.</p>
        <button onClick={() => navigate('/')} className="px-6 py-2 bg-[#0D9488] text-white rounded-lg font-semibold hover:bg-[#0F766E] transition-all">
          Start New Study
        </button>
      </div>
    )
  }

  function handleStartOver() {
    setProtocol(null); setValidatedConcepts(null); setResults(null); setAppError(null)
    navigate('/')
  }

  if (loading) {
    return (
      <div className="max-w-6xl mx-auto space-y-8">
        <div className="flex justify-between items-end">
          <div>
            <h2 className="text-3xl font-bold text-slate-900">Study Results Dashboard</h2>
            <p className="text-slate-500 mt-1">Running query against OMOP database...</p>
          </div>
        </div>
        {/* Query Execution Status */}
        <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
          <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4">Query Execution Status</p>
          <div className="space-y-3">
            {[
              { layer: 'API Gateway', label: 'FastAPI received request at /execute-query', done: true },
              { layer: 'Protocol', label: 'Validated protocol loaded — ready_for_execution: true', done: true },
              { layer: 'SQL Engine', label: 'Selecting template: ' + (protocol?.execution?.sql_template || 'cohort_characterization'), done: false, active: true },
              { layer: 'PostgreSQL', label: 'Executing parameterized SQL against OMOP CDM v5.4', done: false },
              { layer: 'Aggregator', label: 'Computing demographics, age groups, incidence rates', done: false },
            ].map((step, i) => (
              <div key={i} className="flex items-center gap-3">
                <div className="w-24 shrink-0">
                  <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 bg-slate-100 text-slate-500 rounded">{step.layer}</span>
                </div>
                {step.done ? (
                  <span className="material-symbols-outlined text-emerald-500 text-lg shrink-0" style={{fontVariationSettings: "'FILL' 1"}}>check_circle</span>
                ) : step.active ? (
                  <div className="w-5 h-5 border-2 border-teal-500 border-t-transparent rounded-full animate-spin shrink-0"></div>
                ) : (
                  <div className="w-5 h-5 rounded-full border-2 border-slate-200 shrink-0"></div>
                )}
                <span className={`text-sm ${step.done ? 'text-emerald-600' : step.active ? 'text-slate-900 font-semibold' : 'text-slate-400'}`}>
                  {step.label}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  // Parse the real response
  const templateName = data?.template_name || 'cohort_characterization'
  const cohort = data?.cohorts?.[0] || {}
  const queryTimeMs = data?.query_time_ms || 0

  // Build display metrics based on template
  const isCharacterization = templateName === 'cohort_characterization'
  const isIncidence = templateName === 'incidence_analysis'
  const isLabValue = templateName === 'lab_value_summary'

  return (
    <div className="max-w-6xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex justify-between items-end">
        <div>
          <h2 className="text-3xl font-bold text-slate-900">Study Results Dashboard</h2>
          <p className="text-slate-500 mt-1">Primary Cohort Analysis: {protocol?.target_cohort?.label || protocol?.cohort_definition?.condition}</p>
        </div>
        <button onClick={handleStartOver} className="flex items-center gap-2 px-4 py-2 border border-slate-300 bg-white text-slate-700 font-semibold rounded-lg hover:bg-slate-50 transition-colors shadow-sm text-sm">
          <span className="material-symbols-outlined text-sm">add</span>
          New Study
        </button>
      </div>

      {/* Top metric cards */}
      <div className="grid grid-cols-4 gap-6">
        <div className="bg-white p-6 border border-slate-200 rounded-xl shadow-sm">
          <div className="flex justify-between items-start mb-2">
            <span className="text-xs font-bold uppercase tracking-widest text-slate-400">Cohort Size</span>
            <span className="material-symbols-outlined text-teal-600">groups</span>
          </div>
          <div className="text-3xl font-bold text-slate-900">{cohort.cohort_size?.toLocaleString() ?? '—'}</div>
          <div className="flex items-center gap-1 mt-2 text-emerald-600 text-xs font-bold">
            <span className="material-symbols-outlined text-xs">check_circle</span>
            From PostgreSQL
          </div>
        </div>

        {isCharacterization && (
          <>
            <div className="bg-white p-6 border border-slate-200 rounded-xl shadow-sm">
              <div className="flex justify-between items-start mb-2">
                <span className="text-xs font-bold uppercase tracking-widest text-slate-400">Mean Age</span>
                <span className="material-symbols-outlined text-teal-600">calendar_today</span>
              </div>
              <div className="text-3xl font-bold text-slate-900">{cohort.mean_age_at_index != null ? Number(cohort.mean_age_at_index).toFixed(2) : '—'}</div>
              <div className="text-slate-400 text-xs mt-2">years at index date</div>
            </div>
            <div className="bg-white p-6 border border-slate-200 rounded-xl shadow-sm">
              <div className="flex justify-between items-start mb-2">
                <span className="text-xs font-bold uppercase tracking-widest text-slate-400">Female</span>
                <span className="material-symbols-outlined text-teal-600">person</span>
              </div>
              <div className="text-3xl font-bold text-slate-900">{cohort.female_count?.toLocaleString() ?? '—'}</div>
              <div className="text-slate-400 text-xs mt-2">patients</div>
            </div>
            <div className="bg-white p-6 border border-slate-200 rounded-xl shadow-sm">
              <div className="flex justify-between items-start mb-2">
                <span className="text-xs font-bold uppercase tracking-widest text-slate-400">Male</span>
                <span className="material-symbols-outlined text-teal-600">person</span>
              </div>
              <div className="text-3xl font-bold text-slate-900">{cohort.male_count?.toLocaleString() ?? '—'}</div>
              <div className="text-slate-400 text-xs mt-2">patients</div>
            </div>
          </>
        )}

        {isIncidence && (
          <>
            <div className="bg-white p-6 border border-slate-200 rounded-xl shadow-sm">
              <div className="flex justify-between items-start mb-2">
                <span className="text-xs font-bold uppercase tracking-widest text-slate-400">Event Count</span>
                <span className="material-symbols-outlined text-teal-600">monitoring</span>
              </div>
              <div className="text-3xl font-bold text-slate-900">{cohort.event_count?.toLocaleString() ?? '—'}</div>
              <div className="text-slate-400 text-xs mt-2">events observed</div>
            </div>
            <div className="bg-white p-6 border border-slate-200 rounded-xl shadow-sm">
              <div className="flex justify-between items-start mb-2">
                <span className="text-xs font-bold uppercase tracking-widest text-slate-400">Incidence Rate</span>
                <span className="material-symbols-outlined text-teal-600">analytics</span>
              </div>
              <div className="text-3xl font-bold text-slate-900">
                {cohort.incidence_per_person_day != null
                  ? (cohort.incidence_per_person_day * 1000).toFixed(2)
                  : '—'}
              </div>
              <div className="text-slate-400 text-xs mt-2">per 1000 person-days</div>
            </div>
            <div className="bg-white p-6 border border-slate-200 rounded-xl shadow-sm">
              <div className="flex justify-between items-start mb-2">
                <span className="text-xs font-bold uppercase tracking-widest text-slate-400">Person Time</span>
                <span className="material-symbols-outlined text-teal-600">timer</span>
              </div>
              <div className="text-3xl font-bold text-slate-900">
                {cohort.person_time_days != null
                  ? Math.round(cohort.person_time_days / 365).toLocaleString()
                  : '—'}
              </div>
              <div className="text-slate-400 text-xs mt-2">person-years</div>
            </div>
          </>
        )}

        <div className="bg-white p-6 border border-slate-200 rounded-xl shadow-sm">
          <div className="flex justify-between items-start mb-2">
            <span className="text-xs font-bold uppercase tracking-widest text-slate-400">Query Time</span>
            <span className="material-symbols-outlined text-teal-600">timer</span>
          </div>
          <div className="text-3xl font-bold text-slate-900">{queryTimeMs}</div>
          <div className="text-slate-400 text-xs mt-2">milliseconds</div>
        </div>
      </div>

      {/* Cohort details table */}
      <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100 flex justify-between items-center">
          <h3 className="font-semibold text-slate-900">Cohort Results</h3>
          <span className="text-xs text-slate-400">* All figures sourced directly from PostgreSQL</span>
        </div>
        <table className="w-full text-left">
          <thead>
            <tr className="bg-slate-50 text-slate-500 border-b border-slate-200 text-xs font-semibold uppercase tracking-wider">
              <th className="px-6 py-3">Cohort</th>
              <th className="px-6 py-3">Size</th>
              {isCharacterization && <><th className="px-6 py-3">Mean Age</th><th className="px-6 py-3">Female</th><th className="px-6 py-3">Male</th></>}
              {isIncidence && <><th className="px-6 py-3">Events</th><th className="px-6 py-3">Person-Years</th><th className="px-6 py-3">Rate/1000 p-d</th></>}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 text-sm">
            {(data?.cohorts || []).map((c, i) => (
              <tr key={i} className="hover:bg-slate-50 transition-colors">
                <td className="px-6 py-4 font-medium text-slate-700 capitalize">{c.population_label || 'Target Cohort'}</td>
                <td className="px-6 py-4 text-slate-600">{c.cohort_size?.toLocaleString() ?? '—'}</td>
                {isCharacterization && <>
                  <td className="px-6 py-4 text-slate-600">{c.mean_age_at_index != null ? Number(c.mean_age_at_index).toFixed(2) : '—'}</td>
                  <td className="px-6 py-4 text-slate-600">{c.female_count?.toLocaleString() ?? '—'}</td>
                  <td className="px-6 py-4 text-slate-600">{c.male_count?.toLocaleString() ?? '—'}</td>
                </>}
                {isIncidence && <>
                  <td className="px-6 py-4 text-slate-600">{c.event_count?.toLocaleString() ?? '—'}</td>
                  <td className="px-6 py-4 text-slate-600">{c.person_time_days != null ? Math.round(c.person_time_days / 365).toLocaleString() : '—'}</td>
                  <td className="px-6 py-4 text-slate-600">{c.incidence_per_person_day != null ? (c.incidence_per_person_day * 1000).toFixed(4) : '—'}</td>
                </>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Golden rule */}
      <div className="bg-slate-900 rounded-xl p-4 text-white flex items-center gap-3">
        <span className="material-symbols-outlined text-teal-400 text-sm">verified</span>
        <p className="text-xs text-slate-400">Zero LLM-estimated numbers. Every value shown is traceable to a PostgreSQL query result against OMOP CDM v5.4.</p>
      </div>
    </div>
  )
}
