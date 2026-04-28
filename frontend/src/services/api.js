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
