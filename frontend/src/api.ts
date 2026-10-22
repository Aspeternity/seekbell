export interface VersionInfo {
  name: 'SeekBell'
  version: string
  build_revision: string
  database_revision: string | null
}

const options = () => ({
  signal: AbortSignal.timeout(8000),
  cache: 'no-store' as const,
  credentials: 'same-origin' as const,
})

export async function loadVersionInfo(): Promise<VersionInfo> {
  try {
    const response = await fetch('/api/version', options())
    if (!response.ok) throw new Error()
    const data = await response.json()
    if (
      data?.name !== 'SeekBell' ||
      typeof data.version !== 'string' ||
      typeof data.build_revision !== 'string' ||
      !(typeof data.database_revision === 'string' || data.database_revision === null)
    )
      throw new Error()
    return data as VersionInfo
  } catch {
    throw new Error('无法读取版本信息，请检查服务后重试。')
  }
}

export async function loadReadiness(): Promise<'ok' | 'unavailable'> {
  try {
    const response = await fetch('/health/ready', options())
    const data = await response.json()
    if (response.status === 200 && data?.status === 'ok') return 'ok'
    if (response.status === 503 && data?.status === 'unavailable') return 'unavailable'
    throw new Error()
  } catch {
    throw new Error('无法读取就绪状态，请检查连接后重试。')
  }
}
