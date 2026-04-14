import { useNavigate } from 'react-router-dom'
import Card from '../components/shared/Card'
import Button from '../components/shared/Button'

export default function Results() {
  const navigate = useNavigate()

  return (
    <div style={{ maxWidth: '720px' }}>
      <Card title="Query Results" style={{ marginBottom: '1rem' }}>
        <p style={{ color: '#4a5568' }}>Cohort size, demographics, and outcome rates will appear below.</p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', marginTop: '1rem' }}>
          {['Cohort Size', 'Median Age', 'Outcome Rate'].map((label) => (
            <div key={label} style={{ background: '#f7fafc', border: '1px solid #e2e8f0', borderRadius: '6px', padding: '1rem', textAlign: 'center' }}>
              <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#1e3a5f' }}>—</div>
              <div style={{ fontSize: '0.85rem', color: '#718096', marginTop: '0.25rem' }}>{label}</div>
            </div>
          ))}
        </div>
      </Card>
      <Card title="Data Table">
        <div style={{ color: '#718096', padding: '2rem 0', textAlign: 'center' }}>
          Detailed results table will populate here.
        </div>
      </Card>
      <div style={{ marginTop: '1rem' }}>
        <Button variant="secondary" onClick={() => navigate('/')}>Start New Query</Button>
      </div>
    </div>
  )
}
