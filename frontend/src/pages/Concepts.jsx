import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Card from '../components/shared/Card'
import Button from '../components/shared/Button'
import LoadingIndicator from '../components/shared/LoadingIndicator'
import { validateConcepts } from '../services/api'

export default function Concepts() {
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  async function handleValidate() {
    setLoading(true)
    try {
      await validateConcepts([])
      navigate('/results')
    } catch {
      navigate('/error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card title="Clinical Concepts" style={{ maxWidth: '720px' }}>
      <p style={{ color: '#4a5568' }}>Extracted clinical concepts mapped to standard terminologies.</p>
      <div style={{ background: '#f7fafc', border: '1px solid #e2e8f0', borderRadius: '4px', padding: '1rem', marginTop: '1rem', minHeight: '160px', color: '#718096' }}>
        Concept mappings will appear here.
      </div>
      <div style={{ marginTop: '1.25rem', display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
        <Button onClick={handleValidate} disabled={loading}>Validate &amp; Run Query</Button>
        <Button variant="secondary" onClick={() => navigate('/protocol')}>Back</Button>
        {loading && <LoadingIndicator message="Validating…" />}
      </div>
    </Card>
  )
}
