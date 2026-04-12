import { NavLink, Outlet } from 'react-router-dom'

const navLinks = [
  { to: '/', label: 'Question' },
  { to: '/protocol', label: 'Protocol' },
  { to: '/concepts', label: 'Concepts' },
  { to: '/results', label: 'Results' },
  { to: '/error', label: 'Error' },
]

export default function Layout() {
  return (
    <div style={{ fontFamily: 'sans-serif', minHeight: '100vh' }}>
      <nav style={{ background: '#1e3a5f', padding: '0.75rem 1.5rem', display: 'flex', gap: '1.5rem', alignItems: 'center' }}>
        <span style={{ color: '#fff', fontWeight: 700, marginRight: '1rem' }}>RWE Generator</span>
        {navLinks.map(({ to, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            style={({ isActive }) => ({
              color: isActive ? '#90cdf4' : '#cbd5e0',
              textDecoration: 'none',
              fontWeight: isActive ? 600 : 400,
            })}
          >
            {label}
          </NavLink>
        ))}
      </nav>
      <main style={{ padding: '2rem 1.5rem' }}>
        <Outlet />
      </main>
    </div>
  )
}
