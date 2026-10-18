export interface VersionInfo {
  name: 'SeekBell'
  version: string
  build_revision: string
  database_revision: string | null
}

export interface AuthState {
  initialized: boolean
  authenticated: boolean
  username: string | null
  csrf_token: string
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...options,
    credentials: 'same-origin',
    signal: AbortSignal.timeout(8000),
    cache: 'no-store',
  })
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null)
    const detail =
      typeof body === 'object' &&
      body !== null &&
      'detail' in body &&
      typeof body.detail === 'string'
        ? body.detail
        : '请求失败，请稍后重试。'
    throw new ApiError(detail, response.status)
  }
  return response.status === 204 ? (undefined as T) : (response.json() as Promise<T>)
}

export function loadAuth(): Promise<AuthState> {
  return request('/api/auth/state')
}

export function authenticate(
  action: 'setup' | 'login',
  credentials: { username: string; password: string },
  csrfToken: string,
): Promise<AuthState> {
  return request(`/api/auth/${action}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
    body: JSON.stringify(credentials),
  })
}

export function logout(csrfToken: string): Promise<void> {
  return request('/api/auth/logout', {
    method: 'POST',
    headers: { 'X-CSRF-Token': csrfToken },
  })
}

export async function loadSystemInfo(): Promise<VersionInfo> {
  const [version] = await Promise.all([
    request<VersionInfo>('/api/version'),
    request('/health/ready'),
  ])
  return version
}
