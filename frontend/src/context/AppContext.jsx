import { createContext, useContext, useState } from 'react'

const AppContext = createContext(null)

export function AppProvider({ children }) {
  const [protocol, setProtocol] = useState(null)
  const [validatedConcepts, setValidatedConcepts] = useState(null)
  const [results, setResults] = useState(null)
  const [appError, setAppError] = useState(null)
  const [pipelineEvents, setPipelineEvents] = useState([])

  return (
    <AppContext.Provider value={{
      protocol, setProtocol,
      validatedConcepts, setValidatedConcepts,
      results, setResults,
      appError, setAppError,
      pipelineEvents, setPipelineEvents,
    }}>
      {children}
    </AppContext.Provider>
  )
}

export function useApp() {
  return useContext(AppContext)
}
