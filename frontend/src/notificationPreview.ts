export interface TelegramPreviewMessage {
  text: string
  entities: { type: string; offset: number; length: number }[]
  reply_markup?: { inline_keyboard: { text: string; url: string }[][] }
}
export interface NotificationPreviewOptions {
  include_summary: boolean
  summary_limit: number
  timezone: string
}
