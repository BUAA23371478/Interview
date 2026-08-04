// API 客户端：baseURL 指向平台前缀 /app/{slug}/api
// 身份：平台登录后 JWT 存在 localStorage 的 access_token / refresh_token
// 本地开发：Vite 代理 /app/interview-agent/api → 后端 8002，无平台头时后端用 DEV_USER

const SLUG = 'interview-agent'
export const API_BASE = `/app/${SLUG}/api`

export class ApiError extends Error {
  status: number
  code: string
  constructor(status: number, message: string, code = 'UNKNOWN') {
    super(message)
    this.status = status
    this.code = code
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const accessToken = localStorage.getItem('access_token')
  const headers: Record<string, string> = {
    Accept: 'application/json',
  }
  if (accessToken) {
    headers['Authorization'] = `Bearer ${accessToken}`
  }
  const opts: RequestInit = { method, headers }
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, opts)
  } catch {
    throw new ApiError(0, '网络连接失败', 'NETWORK_ERROR')
  }
  if (res.status === 401) {
    // 平台未登录 → 跳转平台登录页
    window.location.href = `/login?redirect=${encodeURIComponent(window.location.pathname)}`
    throw new ApiError(401, '请先登录', 'UNAUTHORIZED')
  }
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    throw new ApiError(
      res.status,
      (data as { message?: string }).message || '请求失败',
      (data as { code?: string }).code || 'UNKNOWN',
    )
  }
  return data as T
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, body),
  del: <T>(path: string) => request<T>('DELETE', path),
  upload: async <T>(path: string, formData: FormData): Promise<T> => {
    const accessToken = localStorage.getItem('access_token')
    const headers: Record<string, string> = {}
    if (accessToken) headers['Authorization'] = `Bearer ${accessToken}`
    let res: Response
    try {
      res = await fetch(`${API_BASE}${path}`, { method: 'POST', headers, body: formData })
    } catch {
      throw new ApiError(0, '网络连接失败', 'NETWORK_ERROR')
    }
    if (res.status === 401) {
      window.location.href = `/login?redirect=${encodeURIComponent(window.location.pathname)}`
      throw new ApiError(401, '请先登录', 'UNAUTHORIZED')
    }
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      throw new ApiError(res.status, (data as { message?: string }).message || '上传失败', 'UPLOAD_ERROR')
    }
    return data as T
  },
}
