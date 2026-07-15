// User and history related API functions

import api from './client';
import type { User } from '@/types/common';

export interface RegisterRequest {
  username: string;
  password: string;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface RegisterResponse {
  userId: string;
  username: string;
}

export const userApi = {
  register: (username: string, password: string) =>
    api.post<RegisterResponse>('/user/register', { username, password }),

  login: (username: string, password: string) =>
    api.post<RegisterResponse>('/user/login', { username, password }),

  getCurrent: () =>
    api.get<User>('/user'),

  getResume: () =>
    api.get<{ resume: string }>('/user/resume'),

  saveResume: (resume: string) =>
    api.put<{ status: string }>('/user/resume', { resume }),

  parseResume: (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.upload<{ resume: string }>('/user/resume/parse', formData);
  },
};
