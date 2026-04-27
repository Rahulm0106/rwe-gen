import { createContext, useContext, useState } from 'react'

const AppContext = createContext(null)

export function AppProvider({ children }) {
  const [protocol, setProtocol] = useState(null)
  const [validatedConcepts, setValidatedConcepts] = useState(null)
  const [results, setResults] = useState(null)
  const [appError, setAppError] = useState(null)

  return (
    <AppContext.Provider value={{
      protocol, setProtocol,
      validatedConcepts, setValidatedConcepts,
      results, setResults,
      appError, setAppError,
    }}>
      {children}
    </AppContext.Provider>
  )
}

export function useApp() {
  return useContext(AppContext)
}
