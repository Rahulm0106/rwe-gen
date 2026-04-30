import { useEffect, useState } from 'react'

export default function PipelineProgress({ steps, visible }) {
  const [currentStep, setCurrentStep] = useState(0)

  useEffect(() => {
    if (!visible) { setCurrentStep(0); return }
    if (currentStep >= steps.length) return
    const timer = setTimeout(() => setCurrentStep(prev => prev + 1), 1200)
    return () => clearTimeout(timer)
  }, [visible, currentStep, steps.length])

  if (!visible) return null

  return (
    <div className="fixed inset-0 bg-black/20 backdrop-blur-sm z-50 flex items-center justify-center">
      <div className="bg-white rounded-2xl shadow-2xl p-8 w-full max-w-md mx-4">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-8 h-8 bg-teal-50 rounded-full flex items-center justify-center">
            <span className="material-symbols-outlined text-teal-600 text-sm">account_tree</span>
          </div>
          <h3 className="font-semibold text-slate-900">Pipeline Running</h3>
        </div>
        <div className="space-y-3">
          {steps.map((step, i) => (
            <div key={i} className="flex items-center gap-3">
              {i < currentStep ? (
                <span className="material-symbols-outlined text-emerald-500 text-lg shrink-0" style={{fontVariationSettings: "'FILL' 1"}}>check_circle</span>
              ) : i === currentStep ? (
                <div className="w-5 h-5 border-2 border-teal-500 border-t-transparent rounded-full animate-spin shrink-0"></div>
              ) : (
                <div className="w-5 h-5 rounded-full border-2 border-slate-200 shrink-0"></div>
              )}
              <span className={`text-sm ${i < currentStep ? 'text-slate-500 line-through' : i === currentStep ? 'text-slate-900 font-medium' : 'text-slate-400'}`}>
                {step}
              </span>
            </div>
          ))}
        </div>
        {currentStep >= steps.length && (
          <div className="mt-6 pt-4 border-t border-slate-100 flex items-center gap-2 text-emerald-600">
            <span className="material-symbols-outlined text-sm" style={{fontVariationSettings: "'FILL' 1"}}>check_circle</span>
            <span className="text-sm font-semibold">Complete!</span>
          </div>
        )}
      </div>
    </div>
  )
}
