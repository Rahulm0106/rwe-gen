import axios from 'axios'

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

/**
 * Validate and map extracted clinical concepts.
 * @param {object[]} concepts - Array of concept objects to validate
 * @returns {Promise<{ concepts: object[] }>}
 */
export function validateConcepts(concepts) {
  return client.post('/validate-concepts', { concepts }).then((r) => r.data)
}

/**
 * Execute a cohort query against the backend database.
 * @param {object} protocol - Approved protocol payload
 * @param {object[]} validatedConcepts - Validated concept mappings
 * @returns {Promise<{ results: object }>}
 */
export function executeQuery(protocol, validatedConcepts) {
  return client.post('/execute-query', { protocol, validated_concepts: validatedConcepts }).then((r) => r.data)
}
