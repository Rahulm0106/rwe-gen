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
      <div className="max-w-2xl mx-auto text-center py-20">
        <div className="w-12 h-12 border-4 border-slate-200 border-t-teal-600 rounded-full animate-spin mx-auto"></div>
        <h2 className="text-xl font-semibold text-slate-700 mt-6">Running Query Against Database...</h2>
        <p className="text-slate-500 mt-2">Executing SQL templates against OMOP CDM</p>
        <div className="mt-6 space-y-2 text-sm text-slate-400">
          <p className="flex items-center justify-center gap-2"><span className="material-symbols-outlined text-teal-500 text-sm">check_circle</span> Protocol validated</p>
          <p className="flex items-center justify-center gap-2"><span className="material-symbols-outlined text-teal-500 text-sm">check_circle</span> Concepts mapped</p>
          <p className="flex items-center justify-center gap-2"><span className="w-4 h-4 border-2 border-slate-300 border-t-teal-500 rounded-full animate-spin inline-block"></span> Querying PostgreSQL...</p>
        </div>
      </div>
    )
  }

  const ageGroups = Object.entries(data.demographics?.age_groups || {})
  const sexGroups = Object.entries(data.demographics?.sex || {})
  const total = data.cohort_size || 1

  return (
    <div className="max-w-6xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex justify-between items-end">
        <div>
          <h2 className="text-3xl font-bold text-slate-900">Study Results Dashboard</h2>
          <p className="text-slate-500 mt-1">Primary Cohort Analysis: {protocol.cohort_definition?.condition}</p>
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
            <span className="text-xs font-bold uppercase tracking-widest text-slate-400">Total Cohort Size</span>
            <span className="material-symbols-outlined text-teal-600">groups</span>
          </div>
          <div className="text-3xl font-bold text-slate-900">{data.cohort_size?.toLocaleString()}</div>
          <div className="flex items-center gap-1 mt-2 text-emerald-600 text-xs font-bold">
            <span className="material-symbols-outlined text-xs">check_circle</span>
            From PostgreSQL
          </div>
        </div>
        <div className="bg-white p-6 border border-slate-200 rounded-xl shadow-sm">
          <div className="flex justify-between items-start mb-2">
            <span className="text-xs font-bold uppercase tracking-widest text-slate-400">Incidence Rate</span>
            <span className="material-symbols-outlined text-teal-600">monitoring</span>
          </div>
          <div className="text-3xl font-bold text-slate-900">
            {data.incidence_rate != null ? data.incidence_rate : 'N/A'}
          </div>
          <div className="text-slate-400 text-xs mt-2">{data.incidence_rate_unit || '—'}</div>
        </div>
        <div className="bg-white p-6 border border-slate-200 rounded-xl shadow-sm">
          <div className="flex justify-between items-start mb-2">
            <span className="text-xs font-bold uppercase tracking-widest text-slate-400">Study Type</span>
            <span className="material-symbols-outlined text-teal-600">science</span>
          </div>
          <div className="text-lg font-bold text-slate-900 capitalize">{protocol.study_type?.replace('_', ' ')}</div>
          <div className="text-slate-400 text-xs mt-2">OMOP CDM V5.4</div>
        </div>
        <div className="bg-white p-6 border border-slate-200 rounded-xl shadow-sm">
          <div className="flex justify-between items-start mb-2">
            <span className="text-xs font-bold uppercase tracking-widest text-slate-400">Query Time</span>
            <span className="material-symbols-outlined text-teal-600">timer</span>
          </div>
          <div className="text-3xl font-bold text-slate-900">{data.query_time_ms}</div>
          <div className="text-slate-400 text-xs mt-2">milliseconds</div>
        </div>
      </div>

      {/* Demographics table + incidence */}
      <div className="grid grid-cols-12 gap-6">
        <div className="col-span-7 bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
          <div className="px-6 py-4 border-b border-slate-100 flex justify-between items-center">
            <h3 className="font-semibold text-slate-900">Demographics Baseline</h3>
            <span className="text-xs text-slate-400">* All figures from PostgreSQL</span>
          </div>
          <table className="w-full text-left">
            <thead>
              <tr className="bg-slate-50 text-slate-500 border-b border-slate-200 text-xs font-semibold uppercase tracking-wider">
                <th className="px-6 py-3">Characteristic</th>
                <th className="px-6 py-3">Count</th>
                <th className="px-6 py-3">Percentage</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-sm">
              {ageGroups.map(([group, count]) => (
                <tr key={group} className="hover:bg-slate-50 transition-colors">
                  <td className="px-6 py-3 text-slate-700 font-medium">Age {group}</td>
                  <td className="px-6 py-3 text-slate-600">{count?.toLocaleString()}</td>
                  <td className="px-6 py-3">
                    <div className="flex items-center gap-3">
                      <span className="w-8 text-slate-600">{Math.round((count / total) * 100)}%</span>
                      <div className="flex-1 h-1.5 bg-slate-100 rounded-full">
                        <div className="bg-teal-500 h-1.5 rounded-full" style={{ width: `${Math.round((count / total) * 100)}%` }}></div>
                      </div>
                    </div>
                  </td>
                </tr>
              ))}
              {sexGroups.map(([group, count]) => (
                <tr key={group} className="hover:bg-slate-50 transition-colors">
                  <td className="px-6 py-3 text-slate-700 font-medium capitalize">Gender: {group}</td>
                  <td className="px-6 py-3 text-slate-600">{count?.toLocaleString()}</td>
                  <td className="px-6 py-3">
                    <div className="flex items-center gap-3">
                      <span className="w-8 text-slate-600">{Math.round((count / total) * 100)}%</span>
                      <div className="flex-1 h-1.5 bg-slate-100 rounded-full">
                        <div className="bg-teal-600 h-1.5 rounded-full" style={{ width: `${Math.round((count / total) * 100)}%` }}></div>
                      </div>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Right stats */}
        <div className="col-span-5 flex flex-col gap-6">
          <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm flex-1">
            <h3 className="font-semibold text-slate-900 mb-4">Cohort Breakdown</h3>
            <div className="space-y-3">
              {ageGroups.map(([group, count]) => (
                <div key={group} className="flex items-center justify-between">
                  <span className="text-sm text-slate-600">Age {group}</span>
                  <div className="flex items-center gap-2">
                    <div className="w-24 h-1.5 bg-slate-100 rounded-full">
                      <div className="bg-teal-500 h-1.5 rounded-full" style={{ width: `${Math.round((count / total) * 100)}%` }}></div>
                    </div>
                    <span className="text-xs font-bold text-slate-500 w-8">{Math.round((count / total) * 100)}%</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
          {/* Golden rule note */}
          <div className="bg-slate-900 rounded-xl p-4 text-white">
            <div className="flex items-center gap-2 mb-2">
              <span className="material-symbols-outlined text-teal-400 text-sm">verified</span>
              <span className="text-xs font-bold uppercase tracking-widest text-teal-300">Golden Rule</span>
            </div>
            <p className="text-xs text-slate-400 leading-relaxed">Zero LLM-estimated numbers. Every value shown is traceable to a PostgreSQL query result.</p>
          </div>
        </div>
      </div>
    </div>
  )
}
