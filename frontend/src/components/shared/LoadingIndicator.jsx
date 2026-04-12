export default function LoadingIndicator({ message = 'Loading…' }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', color: '#4a5568' }}>
      <span
        style={{
          display: 'inline-block',
          width: '20px',
          height: '20px',
          border: '3px solid #e2e8f0',
          borderTopColor: '#1e3a5f',
          borderRadius: '50%',
          animation: 'spin 0.75s linear infinite',
        }}
      />
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      <span>{message}</span>
    </div>
  )
}
