import { NavLink, Outlet } from 'react-router-dom'

const navLinks = [
  { to: '/', label: 'Study Designer', icon: 'auto_awesome', end: true },
  { to: '/protocol', label: 'Protocol Review', icon: 'fact_check' },
  { to: '/concepts', label: 'Concept Validation', icon: 'verified' },
  { to: '/results', label: 'Results Dashboard', icon: 'bar_chart' },
  { to: '/error', label: 'Error Log', icon: 'error' },
]

export default function Layout() {
  return (
    <div className="flex min-h-screen bg-slate-50">
      <aside className="fixed left-0 top-0 h-full w-64 border-r bg-slate-50 border-slate-200 flex flex-col py-4 px-3 z-50">
        <div className="mb-8 px-2">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-[#006a61] flex items-center justify-center rounded">
              <span className="material-symbols-outlined text-white text-lg">clinical_notes</span>
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tighter text-teal-600">RWE-Gen</h1>
              <p className="text-[10px] uppercase tracking-widest text-slate-500 font-bold">Clinical Pipeline</p>
            </div>
          </div>
        </div>
        <nav className="flex-1 space-y-1">
          {navLinks.map(({ to, label, icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                isActive
                  ? 'flex items-center gap-3 px-3 py-2 bg-white text-teal-600 font-semibold border-r-4 border-teal-600 transition-colors duration-150 rounded-l'
                  : 'flex items-center gap-3 px-3 py-2 text-slate-500 hover:bg-slate-100 hover:text-slate-900 transition-colors duration-150 rounded'
              }
            >
              <span className="material-symbols-outlined">{icon}</span>
              <span className="text-sm">{label}</span>
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="ml-64 flex-1 flex flex-col">
        <main className="flex-1 p-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
