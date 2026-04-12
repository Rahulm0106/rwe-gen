import { useNavigate } from 'react-router-dom'
import Card from '../components/shared/Card'
import Button from '../components/shared/Button'

export default function ProtocolReview() {
  const navigate = useNavigate()

  return (
    <Card title="Protocol Review" style={{ maxWidth: '720px' }}>
      <p style={{ color: '#4a5568' }}>Review and approve the generated study protocol before proceeding.</p>
      <div style={{ background: '#f7fafc', border: '1px solid #e2e8f0', borderRadius: '4px', padding: '1rem', marginTop: '1rem', minHeight: '200px', color: '#718096' }}>
        Protocol details will appear here once generated.
      </div>
      <div style={{ marginTop: '1.25rem', display: 'flex', gap: '0.75rem' }}>
        <Button onClick={() => navigate('/concepts')}>Approve &amp; Continue</Button>
        <Button variant="secondary" onClick={() => navigate('/')}>Back</Button>
      </div>
    </Card>
  )
}
