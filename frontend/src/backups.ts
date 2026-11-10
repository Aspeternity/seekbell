export type BackupKind = 'manual' | 'auto' | 'pre-restore' | 'pre-upgrade'
/** What a workspace holds; null when an older backup lacks the table. */
export interface BackupContents {
  workspace: string | null
  websites: number | null
  tasks: number | null
  targets: number | null
  posts: number | null
}
/** One archive in the server-side backup library; unreadable files only offer deletion. */
export interface BackupEntry {
  id: string
  /** Optional name the user gave it; stored beside the archives, at most 40 characters. */
  name: string | null
  valid: boolean
  kind: BackupKind | null
  at: number
  bytes: number
  application_version: string | null
  database_revision: string | null
  summary: BackupContents | null
}
/** Automatic backups: a daily or weekly slot in the display timezone. */
export interface BackupSchedule {
  enabled: boolean
  frequency: 'daily' | 'weekly'
  /** Monday is 0; only used weekly. */
  weekday: number
  /** Minutes after local midnight. */
  minute: number
  keep: number
  revision: number
  timezone: string
  next_run_at: number | null
  last_attempt_at: number | null
  last_error: string | null
}
/** The status card colour: failed and overdue are orange, none is grey. */
export type BackupHealth = 'protected' | 'overdue' | 'failed' | 'none'
export interface BackupStatus {
  confirm_seconds: number
  health: BackupHealth
  schedule: BackupSchedule
  max_upload_bytes: number
  directory: string
  free_bytes: number
  total_bytes: number
  backups: BackupEntry[]
}
/** A verified archive waiting for confirmation; `current` is null on a fresh installation. */
export interface Inspection {
  stage: string
  backup: {
    kind: BackupKind
    created_at: string
    application_version: string
    summary: BackupContents
    upgrade: boolean
  }
  current: BackupContents | null
}
export const kindLabels: Record<BackupKind, string> = {
  manual: '手动',
  auto: '自动',
  'pre-restore': '恢复前',
  'pre-upgrade': '升级前',
}
export const contentRows: { key: keyof BackupContents; label: string }[] = [
  { key: 'websites', label: '网站' },
  { key: 'tasks', label: '监控任务' },
  { key: 'targets', label: '通知目标' },
  { key: 'posts', label: '已采集内容' },
]
export const count = (value: number | null | undefined) => (value == null ? '—' : String(value))
export function contentsText(summary: BackupContents | null) {
  if (!summary) return ''
  return [
    count(summary.websites) + ' 站',
    count(summary.tasks) + ' 任务',
    count(summary.targets) + ' 目标',
  ].join(' · ')
}
/** The newest readable backup, if any. */
export function latestBackup(rows: BackupEntry[]) {
  return rows.find((row) => row.valid)
}
export const STALE_DAYS = 30
export const WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
export const clockText = (minute: number) =>
  String(Math.floor(minute / 60)).padStart(2, '0') + ':' + String(minute % 60).padStart(2, '0')
/** "HH:MM" to minutes after midnight; NaN when it is not a valid time. */
export function clockMinute(text: string) {
  const match = /^([01]\d|2[0-3]):([0-5]\d)$/.exec(text)
  return match ? Number(match[1]) * 60 + Number(match[2]) : NaN
}
export const MAX_NAME = 40
