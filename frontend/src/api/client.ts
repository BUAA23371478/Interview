// HTTP client wrapper with fetch

const BASE_URL = '/api';

function getUserId(): string | null {
  return localStorage.getItem('userId');
}

interface RequestOptions {
  method?: string;
  headers?: Record<string, string>;
  body?: unknown;
  timeout?: number;
}

export class ApiError extends Error {
  code: string;
  status: number;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
    this.name = 'ApiError';
  }
}

async function request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, timeout = 30000 } = options;

  const headers: Record<string, string> = {
    ...(options.headers || {}),
  };
  // 仅当 body 不是 FormData 时设置 JSON Content-Type
  if (!(body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }

  const userId = getUserId();
  if (userId && !headers['X-User-Id']) {
    headers['X-User-Id'] = userId;
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(`${BASE_URL}${endpoint}`, {
      method,
      headers,
      body: body instanceof FormData ? body : (body ? JSON.stringify(body) : undefined),
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({
        code: 'UNKNOWN',
        message: `HTTP ${response.status}`,
      }));
      throw new ApiError(
        response.status,
        errorData.code || 'UNKNOWN',
        errorData.message || `请求失败 (${response.status})`
      );
    }

    const data = await response.json();
    return data as T;
  } catch (error) {
    clearTimeout(timeoutId);
    if (error instanceof ApiError) {
      throw error;
    }
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError(0, 'TIMEOUT', '请求超时，请重试');
    }
    throw new ApiError(0, 'NETWORK_ERROR', '网络连接失败，请检查网络');
  }
}

export const api = {
  get: <T>(endpoint: string, options?: RequestOptions) =>
    request<T>(endpoint, { ...options, method: 'GET' }),

  post: <T>(endpoint: string, body?: unknown, options?: RequestOptions) =>
    request<T>(endpoint, { ...options, method: 'POST', body }),

  put: <T>(endpoint: string, body?: unknown, options?: RequestOptions) =>
    request<T>(endpoint, { ...options, method: 'PUT', body }),

  delete: <T>(endpoint: string, options?: RequestOptions) =>
    request<T>(endpoint, { ...options, method: 'DELETE' }),

  upload: <T>(endpoint: string, formData: FormData, options?: RequestOptions) => {
    const headers: Record<string, string> = {};
    const userId = getUserId();
    if (userId) headers['X-User-Id'] = userId;
    // 不设 Content-Type，让浏览器自动生成 multipart boundary
    const mergedOptions = { ...options, method: 'POST' as const, body: formData, headers };
    return request<T>(endpoint, mergedOptions);
  },
};

export default api;
