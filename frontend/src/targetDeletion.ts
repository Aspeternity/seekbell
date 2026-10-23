export interface TargetDeletePreview {
  target_name: string
  confirmation: string
  tasks: { id: string; name: string; enabled: boolean }[]
  alerts_disabled: boolean
}
