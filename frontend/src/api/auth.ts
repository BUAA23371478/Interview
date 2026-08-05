import { api } from './client'

export interface UserInfo {
  maoo_user_id: number
  username: string
  role: string
  level: string
  is_admin: boolean
}

export interface ProfileData {
  maoo_user_id: number
  total_interviews: number
  total_practices: number
  avg_score: number
  persistent_weaknesses: string[]
  tech_strengths: string[]
  radar_scores: Record<string, number>
  wrong_book: Array<Record<string, unknown>>
  learning_footprint: Array<Record<string, unknown>>
}

export interface WrongBookItem {
  id: number
  session_id: string
  topic: string
  question: string
  answer: string
  reference: string
  score: number
  reviewed: number
  note: string
  created_at: string | null
}

export const authApi = {
  me: () => api.get<UserInfo>('/auth/me'),
  profile: () => api.get<ProfileData>('/auth/profile'),
  updateProfile: (body: { tech_strengths?: string[]; radar_scores?: Record<string, number> }) =>
    api.put<ProfileData>('/auth/profile', body),
  level: () => api.get<{ maoo_user_id: number; level: string; role: string }>('/auth/level'),
  testLlm: (apiKey: string) => api.post<{ ok: boolean; model: string; response?: string; error?: string }>('/auth/test-llm', { api_key: apiKey }),
  wrongBook: () => api.get<{ ok: boolean; total: number; items: WrongBookItem[] }>('/auth/wrong-book'),
}
