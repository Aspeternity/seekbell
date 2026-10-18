export interface VersionInfo {
  name: 'SeekBell'
  version: string
  build_revision: string
  database_revision: string | null
}

export async function loadSystemInfo(): Promise<VersionInfo> {
  const signal = AbortSignal.timeout(8000)
  const [version, ready] = await Promise.all([
    fetch('/api/version', { signal, cache: 'no-store' }),
    fetch('/health/ready', { signal, cache: 'no-store' }),
  ])
  if (!version.ok || !ready.ok) {
    throw new Error('服务暂未就绪，请检查后端运行状态后重试。')
  }
  return version.json() as Promise<VersionInfo>
}
