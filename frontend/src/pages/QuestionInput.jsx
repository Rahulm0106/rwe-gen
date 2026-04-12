import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Card from '../components/shared/Card'
import Button from '../components/shared/Button'
import LoadingIndicator from '../components/shared/LoadingIndicator'
import { generateProtocol } from '../services/api'

export default function QuestionInput() {
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const navigate = useNavigate()

  async function handleSubmit(e) {
    e.preventDefault()
    if (!question.trim()) return
    setLoading(true)
    setError(null)
    try {
      await generateProtocol(question)
      navigate('/protocol')
    } catch (err) {
      setError(err.message)
      navigate('/error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card title="Enter Clinical Question" style={{ maxWidth: '640px' }}>
      <form onSubmit={handleSubmit}>
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="e.g. What is the 1-year mortality rate in patients with HFrEF initiated on SGLT2 inhibitors?"
          rows={5}
          style={{ width: '100%', padding: '0.75rem', fontSize: '0.95rem', border: '1px solid #cbd5e0', borderRadius: '4px', resize: 'vertical', boxSizing: 'border-box' }}
        />
        <div style={{ marginTop: '1rem', display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          <Button type="submit" disabled={loading || !question.trim()}>
            Generate Protocol
          </Button>
          {loading && <LoadingIndicator message="Generating…" />}
        </div>
        {error && <p style={{ color: '#c53030', marginTop: '0.75rem' }}>{error}</p>}
      </form>
    </Card>
  )
}
