import { api } from './client'

export interface KnowledgeDoc {
  id: number
  maoo_user_id: number
  filename: string
  title: string
  category: string
  file_type: string
  file_size: number
  char_count: number
  status: string
  is_seed: boolean
  review_note: string
  chunk_count: number
  created_at: string | null
}

export interface SearchHit {
  id: string
  content: string
  doc_title: string
  category: string
  score: number
}

export interface ReviewItem extends KnowledgeDoc {
  review_logs: Array<{
    action: string
    reviewer_role: string
    reviewer_id: number
    note: string
    ai_precheck: Record<string, unknown>
    created_at: string | null
  }>
  ai_precheck: Record<string, unknown> | null
}

export interface UploadResult {
  ok: boolean
  doc_id?: number
  filename: string
  status: string
  message: string
  ai_precheck?: Record<string, unknown> | null
}

export const kbApi = {
  categories: () => api.get<{ ok: boolean; categories: string[] }>('/kb/categories'),
  docs: (page = 1, limit = 50, status?: string, category?: string) => {
    let p = `/kb/docs?page=${page}&limit=${limit}`
    if (status) p += `&status=${encodeURIComponent(status)}`
    if (category) p += `&category=${encodeURIComponent(category)}`
    return api.get<{ ok: boolean; total: number; page: number; limit: number; items: KnowledgeDoc[] }>(p)
  },
  search: (q: string, topK = 5, category?: string) => {
    let p = `/kb/search?q=${encodeURIComponent(q)}&top_k=${topK}`
    if (category) p += `&category=${encodeURIComponent(category)}`
    return api.get<{ ok: boolean; query: string; total: number; items: SearchHit[] }>(p)
  },
  upload: (file: File, category = '', title = '') => {
    const fd = new FormData()
    fd.append('file', file)
    if (category) fd.append('category', category)
    if (title) fd.append('title', title)
    return api.upload<UploadResult>('/kb/upload', fd)
  },
  pending: (page = 1, limit = 50) =>
    api.get<{ total: number; page: number; limit: number; items: ReviewItem[] }>(
      `/kb/pending?page=${page}&limit=${limit}`,
    ),
  review: (docId: number, action: 'approve' | 'reject', note = '') =>
    api.post<{ ok: boolean; message: string; doc_id?: number; status?: string }>(`/kb/review/${docId}`, {
      action,
      note,
    }),
  remove: (docId: number) => api.del<{ ok: boolean; message: string }>(`/kb/${docId}`),
}
