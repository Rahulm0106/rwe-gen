export default function Card({ children, title, style = {} }) {
  return (
    <div
      style={{
        background: '#fff',
        border: '1px solid #e2e8f0',
        borderRadius: '8px',
        padding: '1.5rem',
        boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
        ...style,
      }}
    >
      {title && (
        <h2 style={{ margin: '0 0 1rem', fontSize: '1.1rem', color: '#1e3a5f' }}>{title}</h2>
      )}
      {children}
    </div>
  )
}
