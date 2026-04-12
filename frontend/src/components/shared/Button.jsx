const variants = {
  primary: { background: '#1e3a5f', color: '#fff', border: 'none' },
  secondary: { background: '#fff', color: '#1e3a5f', border: '1px solid #1e3a5f' },
  danger: { background: '#c53030', color: '#fff', border: 'none' },
}

export default function Button({ children, variant = 'primary', disabled = false, onClick, type = 'button', style = {} }) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      style={{
        ...variants[variant],
        padding: '0.5rem 1.25rem',
        borderRadius: '4px',
        fontSize: '0.95rem',
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.6 : 1,
        ...style,
      }}
    >
      {children}
    </button>
  )
}
