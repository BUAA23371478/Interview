import { Outlet, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import HomePage from './pages/HomePage'
import InterviewSetup from './pages/InterviewSetup'
import InterviewSession from './pages/InterviewSession'
import InterviewReport from './pages/InterviewReport'
import PracticeSetup from './pages/PracticeSetup'
import PracticeSession from './pages/PracticeSession'
import KnowledgeBase from './pages/KnowledgeBase'
import ReviewCenter from './pages/ReviewCenter'
import Profile from './pages/Profile'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<HomePage />} />
        <Route path="interview/setup" element={<InterviewSetup />} />
        <Route path="interview/session/:sessionId" element={<InterviewSession />} />
        <Route path="interview/report/:sessionId" element={<InterviewReport />} />
        <Route path="practice/setup" element={<PracticeSetup />} />
        <Route path="practice/session/:sessionId" element={<PracticeSession />} />
        <Route path="knowledge" element={<KnowledgeBase />} />
        <Route path="review" element={<ReviewCenter />} />
        <Route path="profile" element={<Profile />} />
      </Route>
    </Routes>
  )
}
