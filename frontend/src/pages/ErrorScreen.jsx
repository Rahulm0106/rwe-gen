import { useNavigate } from 'react-router-dom'
import Card from '../components/shared/Card'
import Button from '../components/shared/Button'

export default function ErrorScreen() {
  const navigate = useNavigate()

  return (
    <Card title="Something went wrong" style={{ maxWidth: '520px', borderLeft: '4px solid #c53030' }}>
      <p style={{ color: '#4a5568' }}>
        An error occurred while processing your request. Please check that the backend is running at{' '}
        <code style={{ background: '#f7fafc', padding: '0.1rem 0.3rem', borderRadius: '3px' }}>http://localhost:8000</code>{' '}
        and try again.
      </p>
      <div style={{ marginTop: '1.25rem', display: 'flex', gap: '0.75rem' }}>
        <Button onClick={() => navigate('/')}>Start Over</Button>
        <Button variant="secondary" onClick={() => navigate(-1)}>Go Back</Button>
      </div>
    </Card>
  )
}
