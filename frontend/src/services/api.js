import axios from 'axios'

const USE_MOCK = false

const client = axios.create({
  baseURL: 'http://localhost:8000',
  headers: { 'Content-Type': 'application/json' },
  timeout: 600000,
})

/**
 * Submit a clinical question and receive a generated study protocol.
 * @param {string} question - Free-text clinical question
 * @returns {Promise<{ protocol: object }>}
 */
export function generateProtocol(question) {
  return client.post('/generate-protocol', { question }).then((r) => r.data)
}

export function validateConcepts(protocol) {
  if (USE_MOCK) {
    return Promise.resolve({
      validated: [
        { name: 'Type 2 diabetes mellitus', concept_id: 201826, domain: 'Condition', vocabulary: 'SNOMED', matched: true },
        { name: 'CKD progression', concept_id: 193782, domain: 'Condition', vocabulary: 'SNOMED', matched: true }
      ],
      unmatched: [],
      mapped: [],
      ambiguous: []
    })
  }
  return client.post('/validate-concepts', { protocol }).then((r) => r.data)
}

export function executeQuery(protocol, validatedConcepts) {
  if (USE_MOCK) {
    return Promise.resolve({
      cohort_size: 4821,
      demographics: {
        age_groups: { '18-30': 312, '31-45': 987, '46-60': 1654, '61+': 1868 },
        sex: { male: 2341, female: 2456, other: 24 }
      },
      incidence_rate: 42.3,
      incidence_rate_unit: 'per 1000 person-years',
      query_time_ms: 847
    })
  }
  return client.post('/execute-query', {
    protocol: protocol,
    validated_concepts: validatedConcepts
  }).then((r) => r.data)
}

export async function generateProtocolStream(question, verify, onEvent, onDone, onError) {
  if (USE_MOCK) {
    const mockEvents = [
      { event: 'received', message: 'Connected to pipeline' },
      { event: 'interpretation_attempt', model: 'zai-org-glm-5', attempt: 1, max_attempts: 2, message: 'Interpreting question with zai-org-glm-5 (attempt 1/2)' },
      { event: 'interpretation_completed', message: 'Interpretation parsed and validated' },
      { event: 'protocol_built', message: 'Built draft protocol from interpretation' },
      { event: 'schema_validated', message: 'Draft protocol passes schema validation' },
    ]
    let i = 0
    const interval = setInterval(() => {
      if (i < mockEvents.length) {
        onEvent(mockEvents[i])
        i++
      } else {
        clearInterval(interval)
        onDone({
          study_type: 'cohort_characterization',
          cohort_definition: {
            condition: 'Type 2 diabetes mellitus',
            drug: null,
            observation_window: { start_date: '2020-01-01', end_date: '2023-12-31' }
          },
          target_cohort: {
            label: 'Adults with type 2 diabetes treated with metformin in the last 5 years',
            demographic_filters: { age: { min: 18, max: null }, sex: ['male', 'female', 'unknown'] }
          },
          comparator: { enabled: false, label: null },
          outcome: { required: false, label: null },
          time_windows: { calendar_window: { start_date: '2020-01-01', end_date: '2023-12-31' } },
          normalized_question: 'Characterize adults aged 18 or older with type 2 diabetes treated with metformin.',
          original_question: question,
          execution: { sql_template: 'cohort_characterization', ready_for_execution: false },
          concept_sets: [
            { concept_ref: 'concept_1', raw_text: 'type 2 diabetes', domain: 'condition', mapping: { status: 'unmapped' } },
            { concept_ref: 'concept_2', raw_text: 'metformin', domain: 'drug', mapping: { status: 'unmapped' } }
          ],
          protocol_status: 'needs_mapping',
          issues: { warnings: [], blocking_errors: [] },
          assumptions: []
        })
      }
    }, 600)
    return
  }

  try {
    const response = await fetch('http://localhost:8000/generate-protocol/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, verify }),
    })

    if (!response.ok) {
      const err = await response.json()
      onError(err.message || 'Request failed')
      return
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()

      let eventName = ''
      let dataLine = ''

      for (const line of lines) {
        if (line.startsWith('event:')) {
          eventName = line.replace('event:', '').trim()
        } else if (line.startsWith('data:')) {
          dataLine = line.replace('data:', '').trim()
        } else if (line === '' && eventName && dataLine) {
          if (eventName === ':keepalive') {
            eventName = ''
            dataLine = ''
            continue
          }
          try {
            const payload = JSON.parse(dataLine)
            if (eventName === 'done') {
              onDone(payload)
            } else if (eventName === 'error') {
              onError(payload.message || 'Pipeline error')
            } else {
              onEvent({ event: eventName, ...payload })
            }
          } catch {}
          eventName = ''
          dataLine = ''
        }
      }
    }
  } catch (err) {
    onError(err.message || 'Connection failed')
  }
}
