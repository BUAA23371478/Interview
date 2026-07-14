// Practice mode API functions

import api from './client';
import type {
  PracticeSessionDetail,
  PracticeSessionSummary,
  PracticeStats,
} from '@/types/practice';

export interface PracticeStartResponse {
  sessionId: string;
}

export interface PracticeStatusResponse {
  phase: string;
  difficulty: number;
  questionIndex: number;
  topic: string;
}

export const practiceApi = {
  start: (topic: string, maxQuestions: number = 20) =>
    api.post<PracticeStartResponse>('/practice/start', { topic, max_questions: maxQuestions }),

  submitAnswer: (sessionId: string, answer: string, timeSpent: number) =>
    api.post<void>(`/practice/${sessionId}/answer`, { answer, time_spent_seconds: timeSpent }),

  nextQuestion: (sessionId: string) =>
    api.post<void>(`/practice/${sessionId}/next`),

  getStatus: (sessionId: string) =>
    api.get<PracticeStatusResponse>(`/practice/${sessionId}/status`),

  getStreamUrl: (sessionId: string) =>
    `/practice/${sessionId}/stream`,

  getHistory: (page: number = 1, limit: number = 20) =>
    api.get<{ records: PracticeSessionSummary[]; total: number; page: number }>(
      `/history/practice?page=${page}&limit=${limit}`
    ),

  getSessionDetail: (sessionId: string) =>
    api.get<PracticeSessionDetail>(`/history/practice/${sessionId}`),

  getStats: () =>
    api.get<PracticeStats>('/history/practice/stats'),

  deleteSession: (sessionId: string) =>
    api.delete<void>(`/history/practice/${sessionId}`),

  skipQuestion: (sessionId: string) =>
    api.post<void>(`/practice/${sessionId}/skip`),
};
