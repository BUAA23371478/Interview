import { api } from './client'

export interface InterviewStartReq {
  jd_text: string
  resume_text?: string
  total_rounds?: number
  difficulty?: string
}

export interface InterviewAnswerReq {
  session_id: string
  answer: string
}

export interface InterviewStartResp {
  session_id: string
  question: string
  question_index: number
  total_rounds: number
  difficulty: string
  jd_title: string
}

export interface InterviewReport {
  overall_score: number
  recommendation: string
  dimension_scores: Record<string, number>
  strengths: string[]
  weaknesses: string[]
  highlights: Array<{ round: number; reason: string }>
  concerns: string[]
  topic_performance: Array<{ topic: string; performance: string; comment: string }>
  summary: string
  interviewer_comment: string
}

export interface StudyPlan {
  overall_advice: string
  weeks: Array<{ week: number; theme: string; goals: string[]; daily_hours: number; resources: string[] }>
  practice_projects: string[]
  mock_interview_tips: string[]
}

export interface InterviewAnswerResp {
  session_id: string
  interview_finished: boolean
  should_followup: boolean
  question: string
  question_index: number
  total_rounds: number
  difficulty: string
  score?: number
  final_report?: InterviewReport | null
  study_plan?: StudyPlan | null
}

export interface HistoryItem {
  session_id: string
  mode: string
  status: string
  created_at: string | null
  summary: Record<string, unknown>
}

export const interviewApi = {
  start: (body: InterviewStartReq) => api.post<InterviewStartResp>('/interview/start', body),
  answer: (body: InterviewAnswerReq) => api.post<InterviewAnswerResp>('/interview/answer', body),
  report: (sessionId: string) =>
    api.get<{ session_id: string; mode: string; final_report: InterviewReport; study_plan?: StudyPlan }>(
      `/interview/report/${sessionId}`,
    ),
  history: () => api.get<{ ok: boolean; items: HistoryItem[] }>('/interview/history'),
}
