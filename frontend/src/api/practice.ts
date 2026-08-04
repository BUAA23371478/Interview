import { api } from './client'

export interface PracticeStartReq {
  topic: string
  difficulty?: string
  company_style?: string
  total_rounds?: number
}

export interface PracticeStartResp {
  session_id: string
  question: string
  question_index: number
  total_rounds: number
  difficulty: string
  topic: string
}

export interface PracticeAnswerResp {
  session_id: string
  finished: boolean
  score: number
  is_correct: boolean
  feedback: string
  correct_points?: string[]
  missing_points?: string[]
  reference: string
  question: string
  question_index: number
  total_rounds: number
  difficulty: string
  report?: PracticeReport | null
}

export interface PracticeReport {
  mode: string
  topic: string
  company_style: string
  total_questions: number
  avg_score: number
  accuracy: number
  overall_score: number
  topic_performance: Array<{ topic: string; avg_score: number; count: number }>
  weaknesses: string[]
  recommendation: string
}

export const practiceApi = {
  start: (body: PracticeStartReq) => api.post<PracticeStartResp>('/practice/start', body),
  answer: (sessionId: string, answer: string) =>
    api.post<PracticeAnswerResp>('/practice/answer', { session_id: sessionId, answer }),
  current: (sessionId: string) =>
    api.get<PracticeAnswerResp & { finished: boolean }>(`/practice/current/${sessionId}`),
  report: (sessionId: string) =>
    api.get<{ session_id: string; mode: string; final_report: PracticeReport }>(`/practice/report/${sessionId}`),
  history: () => api.get<{ ok: boolean; items: unknown[] }>('/practice/history'),
}
