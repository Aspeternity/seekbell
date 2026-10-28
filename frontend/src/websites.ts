import type { HotlistConfiguration } from './hotlistSettings'
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
  defaultInterval: number
  minimumInterval: number
  authorFilter: boolean
}
export interface InstalledWebsite {
  hotlist?: HotlistConfiguration | null
  categoryOptions: { value: string; label: string }[]
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
    defaultInterval: 10,
    minimumInterval: 10,
    authorFilter: true,
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
  {
    id: 'linuxdo',
    name: 'LINUX DO',
    description: '开发交流、开源工具与技术社区动态',
    domain: 'linux.do',
    mark: 'L',
    sourceLabel: '官方 RSS',
    sourceUrl: 'https://linux.do/latest.rss?order=created',
    capabilities: ['新帖标题', 'RSS 摘要', '作者显示名', '版块信息', '社区热榜'],
    limits:
      '仅覆盖公开 RSS 提供的主题，不包含权限帖子或回帖。作者为显示名，暂不支持精确用户名筛选；来源可能拒绝访问。',
    defaultInterval: 60,
    minimumInterval: 60,
    authorFilter: false,
  },
]
export function websiteDefinition(adapterId: string) {
  return websiteCatalog.find((item) => item.id === adapterId)
}
export function createWebsite(adapterId: string): InstalledWebsite {
  if (!websiteDefinition(adapterId)) throw new Error('尚未支持该网站适配器')
  return {
    id: adapterId,
    categoryOptions: [],
    adapterId,
    enabled: false,
    interval: websiteDefinition(adapterId)!.defaultInterval,
    health: 'pending',
    lastSuccess: '',
    lastTest: '',
  }
}
