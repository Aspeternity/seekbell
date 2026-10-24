import type { Evaluation, Page, PostStatus } from './history'
export interface EvaluationOption {
  key: string
  task_id: string
  version: number
  name: string
  deleted: boolean
  status: PostStatus
  at: number
}
export interface EvaluationOptions extends Page<EvaluationOption> {
  counts: Partial<Record<PostStatus, number>>
  recorded_total: number
  preferred: EvaluationOption | null
}
export interface Explanation {
  headline: string
  blockers: string[]
  checks: {
    code: string
    label: string
    state: 'passed' | 'blocked' | 'unknown'
    message: string
  }[]
}
export interface DiagnosisDetail extends Evaluation {
  explanation: Explanation
  rule: {
    scope: string
    categories: string[]
    authors_include: string[]
    authors_exclude: string[]
  } | null
  category: {
    actual: string | null
    label: string | null
    expected: { value: string; label: string }[]
    legacy_mismatch: boolean
  }
  author: string | null
}
export interface CurrentRuleTrial {
  task_id: string
  version: number
  name: string
  historical: false
  applicable: boolean
  result: Evaluation['result'] | null
  explanation: Explanation | null
  message: string
}
