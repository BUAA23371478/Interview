// Common type definitions shared across the application

export interface User {
  userId: string;
  username: string;
}

export interface ApiError {
  code: string;
  message: string;
}

export interface PaginatedResponse<T> {
  records: T[];
  total: number;
  page: number;
}
