import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApp } from '../context/AppContext'
import { validateConcepts } from '../services/api'

export default function Concepts() {
  const { protocol, setValidatedConcepts, setAppError } = useApp()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [validated, setValidated] = useState([])
  const [unmatched, setUnmatched] = useState([])

  useEffect(() => {
    if (!protocol) return
    validateConcepts(protocol)
      .then((data) => {
        setValidated(data.mapped || data.validated || [])
        setUnmatched(data.unmatched || [])
        console.log('validateConcepts response:', JSON.stringify(data, null, 2))
        setValidatedConcepts(data)
      })
      .catch((err) => {
        setAppError(err.message)
        navigate('/error')
      })
      .finally(() => setLoading(false))
  }, [])

  if (!protocol) {
    return (
      <div className="max-w-2xl mx-auto text-center py-20">
        <span className="material-symbols-outlined text-slate-300 text-6xl">verified</span>
        <h2 className="text-2xl font-bold text-slate-700 mt-4">No Protocol Found</h2>
        <p className="text-slate-500 mt-2 mb-6">Please go back and complete the protocol review first.</p>
        <button onClick={() => navigate('/protocol')} className="px-6 py-2 bg-[#0D9488] text-white rounded-lg font-semibold hover:bg-[#0F766E] transition-all">
          Back to Protocol Review
        </button>
      </div>
    )
  }

  const hasUnmatched = unmatched.length > 0
  const mappedPercent = validated.length + unmatched.length > 0
    ? Math.round((validated.length / (validated.length + unmatched.length)) * 100)
    : 0

  return (
    <div className="max-w-6xl mx-auto">
      {/* Page header */}
      <div className="flex justify-between items-start mb-8">
        <div>
          <h2 className="text-3xl font-bold text-slate-900">Concept Validation</h2>
          <p className="text-slate-500 mt-1">Clinical terms mapped to OMOP standard vocabulary via ATHENA.</p>
        </div>
        <div className="flex gap-3">
          <button onClick={() => navigate('/protocol')} className="px-4 py-2 border border-slate-200 bg-white text-slate-700 font-semibold rounded-lg hover:bg-slate-50 transition-colors flex items-center gap-2 text-sm">
            <span className="material-symbols-outlined text-sm">arrow_back</span>
            Back
          </button>
          <button
            onClick={() => navigate('/results')}
            disabled={loading || hasUnmatched}
            className="px-4 py-2 bg-[#0D9488] text-white font-semibold rounded-lg hover:bg-[#0F766E] disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2 text-sm shadow-sm"
          >
            <span className="material-symbols-outlined text-sm">play_circle</span>
            Execute Query
          </button>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-8">
        {/* Left: Concept table */}
        <div className="col-span-7 bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-100 flex justify-between items-center">
            <h3 className="font-semibold text-slate-900 flex items-center gap-2">
              <span className="material-symbols-outlined text-[#0D9488]">verified</span>
              Concept Validation
            </h3>
            {!loading && (
              <span className={`text-xs font-bold px-2 py-1 rounded ${hasUnmatched ? 'bg-rose-50 text-rose-600' : 'bg-emerald-50 text-emerald-600'}`}>
                {mappedPercent}% Mapped
              </span>
            )}
          </div>

          {loading ? (
            <div className="p-12 flex flex-col items-center justify-center gap-3">
              <div className="w-8 h-8 border-3 border-slate-200 border-t-teal-600 rounded-full animate-spin" style={{borderWidth: '3px'}}></div>
              <p className="text-sm text-slate-500">Validating concepts against ATHENA vocabulary...</p>
            </div>
          ) : (
            <>
              <table className="w-full text-left">
                <thead>
                  <tr className="bg-slate-50 text-[10px] font-bold text-slate-400 uppercase tracking-wider border-b border-slate-100">
                    <th className="px-6 py-3">Clinical Entity</th>
                    <th className="px-6 py-3">OMOP Concept ID</th>
                    <th className="px-6 py-3">Domain</th>
                    <th className="px-6 py-3 text-center">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {validated.map((c) => (
                    <tr key={c.concept_id} className="border-b border-slate-50 hover:bg-slate-50/50 transition-colors">
                      <td className="px-6 py-4">
                        <p className="font-semibold text-slate-900 text-sm">{c.name}</p>
                        <p className="text-[10px] text-slate-400">{c.vocabulary}</p>
                      </td>
                      <td className="px-6 py-4">
                        <span className="font-mono text-slate-500 text-sm">{c.concept_id}</span>
                      </td>
                      <td className="px-6 py-4 text-sm text-slate-600">{c.domain}</td>
                      <td className="px-6 py-4 text-center">
                        <span className="material-symbols-outlined text-emerald-500" style={{fontVariationSettings: "'FILL' 1"}}>check_circle</span>
                      </td>
                    </tr>
                  ))}
                  {unmatched.map((name) => (
                    <tr key={name} className="border-b border-slate-50 bg-rose-50/20 hover:bg-rose-50/40 transition-colors">
                      <td className="px-6 py-4">
                        <p className="font-semibold text-slate-900 text-sm">{name}</p>
                        <p className="text-[10px] text-slate-400">Unresolved</p>
                      </td>
                      <td className="px-6 py-4">
                        <span className="px-2 py-1 bg-rose-100 text-rose-600 rounded text-[10px] font-bold">UNMAPPED</span>
                      </td>
                      <td className="px-6 py-4 text-sm text-slate-400">—</td>
                      <td className="px-6 py-4 text-center">
                        <span className="material-symbols-outlined text-rose-500" style={{fontVariationSettings: "'FILL' 1"}}>error</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>

        {/* Right: Status cards */}
        <div className="col-span-5 space-y-6">
          {/* Status summary */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
            <h3 className="font-semibold text-slate-900 mb-4">Validation Status</h3>
            <div className="space-y-3">
              <div className="flex items-center justify-between p-3 border border-slate-100 rounded-lg">
                <span className="text-sm text-slate-600">Mapped concepts</span>
                <span className="text-sm font-bold text-emerald-600">{validated.length}</span>
              </div>
              <div className="flex items-center justify-between p-3 border border-slate-100 rounded-lg">
                <span className="text-sm text-slate-600">Unmapped concepts</span>
                <span className={`text-sm font-bold ${hasUnmatched ? 'text-rose-600' : 'text-slate-400'}`}>{unmatched.length}</span>
              </div>
              <div className="flex items-center justify-between p-3 border border-slate-100 rounded-lg">
                <span className="text-sm text-slate-600">Ready to execute</span>
                {loading ? (
                  <span className="text-sm font-bold text-amber-600">Validating...</span>
                ) : hasUnmatched ? (
                  <span className="text-sm font-bold text-rose-600">Blocked</span>
                ) : (
                  <span className="text-sm font-bold text-emerald-600">Yes</span>
                )}
              </div>
            </div>
          </div>

          {/* Warning or success */}
          {!loading && hasUnmatched && (
            <div className="bg-rose-50 border border-rose-200 rounded-xl p-4">
              <div className="flex items-start gap-3">
                <span className="material-symbols-outlined text-rose-500 mt-0.5">warning</span>
                <div>
                  <p className="text-sm font-semibold text-rose-800">Cannot Execute Query</p>
                  <p className="text-xs text-rose-600 mt-1">All concepts must be mapped before running the query. Resolve unmapped terms above.</p>
                </div>
              </div>
            </div>
          )}
          {!loading && !hasUnmatched && (
            <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4">
              <div className="flex items-start gap-3">
                <span className="material-symbols-outlined text-emerald-500 mt-0.5">check_circle</span>
                <div>
                  <p className="text-sm font-semibold text-emerald-800">All Concepts Validated</p>
                  <p className="text-xs text-emerald-600 mt-1">Ready to execute query against the OMOP database.</p>
                </div>
              </div>
            </div>
          )}

          {/* Bottom sticky bar hint */}
          <div className="bg-slate-900 rounded-xl p-4 text-white">
            <div className="flex items-center gap-2 mb-2">
              <div className={`w-2 h-2 rounded-full ${!loading && !hasUnmatched ? 'bg-emerald-500' : 'bg-amber-500'}`}></div>
              <span className="text-xs font-semibold">{!loading && !hasUnmatched ? 'Schema Ready' : 'Validation in Progress'}</span>
            </div>
            <p className="text-xs text-slate-400">Every concept ID is resolved before SQL execution. No null concept IDs will reach the database.</p>
          </div>
        </div>
      </div>
    </div>
  )
}
