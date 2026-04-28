import { useNavigate } from 'react-router-dom'
import { useApp } from '../context/AppContext'

export default function ErrorScreen() {
  const { appError, setAppError } = useApp()
  const navigate = useNavigate()

  const message = appError ?? 'An unexpected error occurred.'

  const failurePoint = message.includes('PROTOCOL_GENERATION_FAILED')
    ? 'Protocol Generation'
    : message.includes('CONCEPT_VALIDATION_FAILED')
    ? 'Concept Validation'
    : message.includes('QUERY_EXECUTION_FAILED')
    ? 'Query Execution'
    : 'Unknown'

  function handleStartOver() {
    setAppError(null)
    navigate('/')
  }

  return (
    <div className="max-w-2xl mx-auto py-12">
      {/* Error card */}
      <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
        {/* Red top bar */}
        <div className="h-1.5 bg-rose-500 w-full"></div>
        <div className="p-8">
          {/* Icon + title */}
          <div className="flex items-center gap-4 mb-6">
            <div className="w-12 h-12 bg-rose-50 rounded-full flex items-center justify-center">
              <span className="material-symbols-outlined text-rose-500 text-2xl" style={{fontVariationSettings: "'FILL' 1"}}>error</span>
            </div>
            <div>
              <h2 className="text-xl font-bold text-slate-900">Something Went Wrong</h2>
              <p className="text-sm text-slate-500 mt-0.5">The pipeline encountered an error and could not continue.</p>
            </div>
          </div>

          {/* Failure point badge */}
          <div className="mb-4">
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-rose-100 text-rose-700 rounded-lg text-xs font-bold uppercase tracking-wider">
              <span className="material-symbols-outlined text-xs">location_on</span>
              Failure point: {failurePoint}
            </span>
          </div>

          {/* Error message */}
          <div className="bg-slate-50 border border-slate-200 rounded-lg p-4 mb-6">
            <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">Error Details</p>
            <p className="text-sm text-slate-700 font-mono">{message}</p>
          </div>

          {/* Help text */}
          <p className="text-sm text-slate-500 mb-6">
            Make sure the backend is running at{' '}
            <code className="bg-slate-100 px-1.5 py-0.5 rounded text-xs font-mono">http://localhost:8000</code>
            {' '}and try again.
          </p>

          {/* Buttons */}
          <div className="flex gap-3">
            <button
              onClick={() => navigate(-1)}
              className="flex-1 py-2.5 bg-[#0D9488] text-white font-semibold rounded-lg hover:bg-[#0F766E] transition-all flex items-center justify-center gap-2 text-sm shadow-sm"
            >
              <span className="material-symbols-outlined text-sm">refresh</span>
              Retry
            </button>
            <button
              onClick={handleStartOver}
              className="flex-1 py-2.5 border border-slate-200 bg-white text-slate-700 font-semibold rounded-lg hover:bg-slate-50 transition-colors flex items-center justify-center gap-2 text-sm"
            >
              <span className="material-symbols-outlined text-sm">home</span>
              Start Over
            </button>
          </div>
        </div>
      </div>

      {/* Pipeline status */}
      <div className="mt-6 bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
        <h3 className="font-semibold text-slate-900 mb-4 flex items-center gap-2">
          <span className="material-symbols-outlined text-slate-400">account_tree</span>
          Pipeline Status
        </h3>
        <div className="space-y-3">
          {[
            { label: 'Study Designer', icon: 'auto_awesome', status: 'complete' },
            { label: 'Protocol Review', icon: 'fact_check', status: failurePoint === 'Protocol Generation' ? 'error' : 'complete' },
            { label: 'Concept Validation', icon: 'verified', status: failurePoint === 'Concept Validation' ? 'error' : failurePoint === 'Query Execution' ? 'complete' : 'pending' },
            { label: 'Query Execution', icon: 'bar_chart', status: failurePoint === 'Query Execution' ? 'error' : 'pending' },
          ].map(({ label, icon, status }) => (
            <div key={label} className="flex items-center gap-3">
              <span className="material-symbols-outlined text-slate-400 text-sm">{icon}</span>
              <span className="text-sm text-slate-600 flex-1">{label}</span>
              {status === 'complete' && <span className="material-symbols-outlined text-emerald-500 text-sm" style={{fontVariationSettings: "'FILL' 1"}}>check_circle</span>}
              {status === 'error' && <span className="material-symbols-outlined text-rose-500 text-sm" style={{fontVariationSettings: "'FILL' 1"}}>error</span>}
              {status === 'pending' && <span className="w-3 h-3 rounded-full bg-slate-200"></span>}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
