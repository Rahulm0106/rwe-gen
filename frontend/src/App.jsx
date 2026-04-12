import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import QuestionInput from './pages/QuestionInput'
import ProtocolReview from './pages/ProtocolReview'
import Concepts from './pages/Concepts'
import Results from './pages/Results'
import ErrorScreen from './pages/ErrorScreen'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<QuestionInput />} />
          <Route path="protocol" element={<ProtocolReview />} />
          <Route path="concepts" element={<Concepts />} />
          <Route path="results" element={<Results />} />
          <Route path="error" element={<ErrorScreen />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
