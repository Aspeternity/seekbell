export interface BackupRecord {
  id: string
  kind: string
  result: string
  at: number
  archive_bytes: number | null
  application_version: string
  database_revision: string
}
/** Data a restore set aside on the server: the replaced workspace or a verification copy. */
export interface Leftover {
  id: string
  kind: 'previous' | 'candidate'
  at: number
  bytes: number
}
export interface BackupStatus {
  confirm_seconds: number
  leftovers: Leftover[]
  max_archive_bytes: number
  records: BackupRecord[]
}
