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

export const authApi = {
  me: () => api.get<UserInfo>('/auth/me'),
  profile: () => api.get<ProfileData>('/auth/profile'),
  updateProfile: (body: { tech_strengths?: string[]; radar_scores?: Record<string, number> }) =>
    api.put<ProfileData>('/auth/profile', body),
  level: () => api.get<{ maoo_user_id: number; level: string; role: string }>('/auth/level'),
}
