export interface Group {
  all: string[]
  any: string[]
}
export interface CategoryScope {
  mode: 'all' | 'specific'
  values: string[]
}
export interface Task {
  websiteIds: string[]
  id: string
  name: string
  description: string
  enabled: boolean
  scope: 'title' | 'summary' | 'title_summary'
  groups: Group[]
  exclude: string[]
  categoryScopes: Record<string, CategoryScope>
  authorsInclude: string[]
  authorsExclude: string[]
  caseSensitive: boolean
  wholeWord: boolean
  targets: string[]
  hits: number
  lastHit: string
  color: string
  icon: string
}
export interface Sample {
  websiteId?: string
  title: string
  summary: string | null
  author: string | null
  category: string | null
}
export function emptyTask(): Task {
  return {
    id: '',
    websiteIds: [],
    name: '',
    description: '',
    enabled: true,
    scope: 'title',
    groups: [{ all: [], any: [] }],
    exclude: [],
    categoryScopes: {},
    authorsInclude: [],
    authorsExclude: [],
    caseSensitive: false,
    wholeWord: false,
    targets: [],
    hits: 0,
    lastHit: '暂无命中',
    color: 'orange',
    icon: 'layers',
  }
}
export type Truth = 'yes' | 'no' | 'unknown'
export interface MatchResult {
  headline?: string
  status: Truth
  reasons: string[]
}
export const statusLabel: Record<Truth, string> = { yes: '命中', no: '不命中', unknown: '信息不足' }
