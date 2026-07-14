// Interview mode API functions

import api from './client';
import type {
  InterviewReport,
  InterviewSessionDetail,
  InterviewSessionSummary,
} from '@/types/interview';

export interface InterviewCreateRequest {
  jd: string;
  resume: string;
  total_rounds: number;
}

export interface InterviewCreateResponse {
  sessionId: string;
}

export interface InterviewStatusResponse {
  currentRound: number;
  totalRounds: number;
  phase: string;
}

export const interviewApi = {
  create: (data: InterviewCreateRequest) =>
    api.post<InterviewCreateResponse>('/interview/create', data),

  submitAnswer: (sessionId: string, answer: string) =>
    api.post<void>(`/interview/${sessionId}/answer`, { answer }),

  getReport: (sessionId: string) =>
    api.get<InterviewReport>(`/interview/${sessionId}/report`),

  getStatus: (sessionId: string) =>
    api.get<InterviewStatusResponse>(`/interview/${sessionId}/status`),

  getStreamUrl: (sessionId: string) =>
    `/interview/${sessionId}/stream`,

  getHistory: (page: number = 1, limit: number = 20) =>
    api.get<{ records: InterviewSessionSummary[]; total: number; page: number }>(
      `/history/interview?page=${page}&limit=${limit}`
    ),

  getSessionDetail: (interviewId: string) =>
    api.get<InterviewSessionDetail>(`/history/interview/${interviewId}`),

  deleteSession: (sessionId: string) =>
    api.delete<void>(`/history/interview/${sessionId}`),
};
