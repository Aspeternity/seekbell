import type { Task, Sample, Truth } from './model'
import type { InstalledWebsite } from './websites'
export type Channel = 'telegram' | 'bark' | 'smtp' | 'webhook'
export type DeliveryStatus = 'success' | 'retrying' | 'failed' | 'unknown' | 'cancelled'
export interface Target {
  id: string
  name: string
  channel: Channel
  type: string
  icon: string
  color: string
  enabled: boolean
  configured: boolean
  summary: boolean
  summaryLimit: number
  group: string
  security: 'tls' | 'starttls' | 'plain'
  port: number
  responseMode: 'json_ok' | 'status'
  lastTest: string
}
export interface Post extends Sample {
  websiteId: string
  id: string
  time: string
  taskIds: string[]
  taskNames: string[]
  status: Truth
  reasons: string[]
  originalUrl: string | null
}
export interface Delivery {
  id: string
  postId: string | null
  title: string
  targetId: string
  targetName: string
  channel: Channel
  status: DeliveryStatus
  time: string
  attempts: number
  manual: boolean
  test: boolean
  reason: string
}
export interface DemoState {
  version: 3
  tasks: Task[]
  targets: Target[]
  posts: Post[]
  deliveries: Delivery[]
  websites: InstalledWebsite[]
  settings: {
    workspaceName: string
    workspaceDescription: string
    timezone: string
    retention: number
    alertTargets: string[]
    recoveryAlerts: boolean
  }
}
export const channelMeta = {
  telegram: {
    type: 'Telegram Bot',
    icon: 'send',
    color: 'blue',
    description: '把新消息送到你的 Telegram 对话',
  },
  bark: { type: 'Bark', icon: 'phone', color: 'purple', description: '让 iPhone 第一时间告诉你' },
  smtp: { type: 'SMTP', icon: 'mail', color: 'orange', description: '通过你自己的邮件服务发送' },
  webhook: {
    type: 'Webhook',
    icon: 'code',
    color: 'green',
    description: '连接你的自动化与自托管服务',
  },
} as const
export const deliveryLabels: Record<DeliveryStatus, string> = {
  success: '成功',
  retrying: '等待重试',
  failed: '失败',
  unknown: '结果未知',
  cancelled: '已取消',
}
export const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value))
export function newTarget(channel: Channel = 'telegram'): Target {
  return {
    id: '',
    name: '',
    channel,
    ...channelMeta[channel],
    enabled: true,
    configured: false,
    summary: false,
    summaryLimit: 300,
    group: 'SeekBell',
    security: 'tls',
    port: 465,
    responseMode: 'json_ok',
    lastTest: '',
  }
}
