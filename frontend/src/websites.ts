export interface WebsiteDefinition {
  id: string
  name: string
  description: string
  domain: string
  mark: string
  sourceLabel: string
  sourceUrl: string
  capabilities: string[]
  limits: string
}
export interface InstalledWebsite {
  id: string
  adapterId: string
  enabled: boolean
  interval: number
  health: 'pending' | 'healthy' | 'error'
  lastSuccess: string
  lastTest: string
}
export const websiteCatalog: WebsiteDefinition[] = [
  {
    id: 'nodeseek',
    name: 'NodeSeek',
    description: '技术交流、服务器优惠与自托管灵感',
    domain: 'nodeseek.com',
    mark: 'N',
    sourceLabel: '官方 RSS',
    sourceUrl: 'https://rss.nodeseek.com/',
    capabilities: ['新帖标题', 'RSS 摘要', '作者用户名', '版块信息'],
    limits: '仅使用 RSS 实际提供的信息；摘要可能缺失或截断。不读取全文、回帖或网页。',
  },
]
export function websiteDefinition(adapterId: string) {
  return websiteCatalog.find((item) => item.id === adapterId)
}
export function createWebsite(adapterId: string): InstalledWebsite {
  if (!websiteDefinition(adapterId)) throw new Error('尚未支持该网站适配器')
  return {
    id: adapterId,
    adapterId,
    enabled: false,
    interval: 10,
    health: 'pending',
    lastSuccess: '',
    lastTest: '',
  }
}
