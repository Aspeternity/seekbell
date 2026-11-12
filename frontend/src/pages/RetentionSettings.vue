<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { request } from '../store'
import { ago, stamp, useSettingsForm } from '../settings'
import Icon from '../components/Icon.vue'
import FormFeedback from '../components/FormFeedback.vue'
import ReadRegion from '../components/ReadRegion.vue'
import { untilShown } from '../viewReady'
import SettingsSaveBar from '../components/SettingsSaveBar.vue'
interface Overview {
  posts: number
  matched_posts: number
  deliveries: number
  earliest_at: number | null
}
interface Policy {
  days: number
  max_posts: number | null
  revision: number
  overview: Overview
}
interface Preview {
  posts: number
  records: number
}
// An empty limit field means no limit.
interface Draft {
  days: number
  max_posts: number | ''
}
const MAX_POSTS = 1000000
const emit = defineEmits<{ dirty: [value: boolean] }>()
const limitOf = (draft: Draft) => (draft.max_posts === '' ? null : draft.max_posts)
// Whether a draft can only remove history compared with what is saved.
const shrinks = (draft: Draft, saved: Policy) => {
  const limit = limitOf(draft)
  return (
    draft.days < saved.days ||
    (limit !== null && (saved.max_posts === null || limit < saved.max_posts))
  )
}
const count = (value: number) => value.toLocaleString('zh-CN')
const cleaning = ref(false)
const form = useSettingsForm<Policy, Draft>({
  name: '保留策略',
  read: () => request<Policy>('manage/retention'),
  write: (draft, saved) => {
    cleaning.value = shrinks(draft, saved)
    return request<Policy>('manage/retention', 'PUT', {
      days: draft.days,
      max_posts: limitOf(draft),
      revision: saved.revision,
    })
  },
  draftOf: ({ days, max_posts }) => ({ days, max_posts: max_posts ?? '' }),
  validate: (draft) => {
    if (!Number.isInteger(draft.days) || draft.days < 1 || draft.days > 365)
      return '保留天数应为 1–365 之间的整数。'
    const limit = limitOf(draft)
    if (limit !== null && (!Number.isInteger(limit) || limit < 1 || limit > MAX_POSTS))
      return '内容上限应为 1–1000000 之间的整数，留空表示不限。'
    return ''
  },
  confirmSave: async (draft, saved) => {
    if (!shrinks(draft, saved)) return undefined
    const query = new URLSearchParams({ days: String(draft.days) })
    const limit = limitOf(draft)
    if (limit !== null) query.set('max_posts', String(limit))
    let body = '超出范围的历史将被清理，无法恢复。'
    try {
      const preview = await request<Preview>('manage/retention/preview?' + query)
      if (!preview.posts && !preview.records) return undefined
      const parts = [
        preview.posts ? count(preview.posts) + ' 条内容' : '',
        preview.records ? count(preview.records) + ' 条通知、采集与问题记录' : '',
      ].filter(Boolean)
      body = '将清理约 ' + parts.join('和 ') + '，无法恢复。'
    } catch {
      // Without an estimate the general warning still protects the change.
    }
    return { body, label: '确认保存' }
  },
  dirty: (value) => emit('dirty', value),
})
const { saved, draft, busy, error, reloadable, done, dirty } = form
const doneText = computed(() =>
  cleaning.value ? '保留策略已保存，超出部分正在后台清理' : '保留策略已保存',
)
// The cleanup a shrinking save starts takes a few seconds in the background: follow
// the counts until two reads agree, so the figures do not stay at their pre-save value.
const FOLLOW_MS = 2000,
  FOLLOW_READS = 30
let following = 0
async function followCleanup() {
  const run = ++following
  let last = ''
  for (let i = 0; i < FOLLOW_READS; i++) {
    await new Promise((resolve) => setTimeout(resolve, FOLLOW_MS))
    if (run !== following || !saved.value) return
    let value: Policy
    try {
      value = await request<Policy>('manage/retention')
    } catch {
      return
    }
    // A newer save or read owns the figures now.
    if (run !== following || !saved.value || value.revision !== saved.value.revision) return
    saved.value = { ...saved.value, overview: value.overview }
    const current = JSON.stringify(value.overview)
    if (current === last) return
    last = current
  }
}
watch(done, (value) => {
  if (value && cleaning.value) void followCleanup()
  else following++
})
onBeforeUnmount(() => following++)
await untilShown(form.load())
</script>
<template>
  <section class="panel settings-card" aria-labelledby="retention-data-title">
    <div class="panel-heading">
      <h2 id="retention-data-title">现有数据</h2>
    </div>
    <FormFeedback v-if="!saved" :error="error" :retryable="reloadable" @retry="form.reload" />
    <ReadRegion :loading="busy && !saved" error="" :has-data="!!saved" :min-height="110">
      <div v-if="saved" class="form-content">
        <dl class="about-tiles retention-tiles">
          <div>
            <dt>
              <span class="about-tile-icon"><Icon name="inbox" :size="16" /></span>内容
            </dt>
            <dd>
              {{ count(saved.overview.posts) }} 条
              <small>命中 {{ count(saved.overview.matched_posts) }} 条</small>
            </dd>
          </div>
          <div>
            <dt>
              <span class="about-tile-icon"><Icon name="send" :size="16" /></span>通知
            </dt>
            <dd>{{ count(saved.overview.deliveries) }} 条</dd>
          </div>
          <div>
            <dt>
              <span class="about-tile-icon"><Icon name="clock" :size="16" /></span>最早内容
            </dt>
            <dd v-if="saved.overview.earliest_at">
              {{ ago(saved.overview.earliest_at) }}
              <small>{{ stamp(saved.overview.earliest_at) }}</small>
            </dd>
            <dd v-else>暂无内容</dd>
          </div>
        </dl>
      </div>
    </ReadRegion>
  </section>
  <section id="retention-settings" class="panel settings-card" aria-labelledby="retention-title">
    <div class="panel-heading">
      <h2 id="retention-title">保留策略</h2>
    </div>
    <FormFeedback v-if="saved" :error="error" :retryable="reloadable" @retry="form.reload" />
    <ReadRegion :loading="busy && !saved" error="" :has-data="!!saved" :min-height="120">
      <form v-if="saved" class="form-content form-stack" @submit.prevent="form.save">
        <div class="retention-fields">
          <div class="form-stack">
            <label class="field-label" for="retention-days">保留天数</label>
            <div class="unit-input">
              <input
                id="retention-days"
                v-model.number="draft.days"
                type="number"
                class="text-input"
                min="1"
                max="365"
                step="1"
                required
                :disabled="busy"
              /><span>天</span>
            </div>
          </div>
          <div class="form-stack">
            <label class="field-label" for="retention-limit">内容上限</label>
            <div class="unit-input">
              <input
                id="retention-limit"
                v-model.number="draft.max_posts"
                type="number"
                class="text-input"
                min="1"
                :max="MAX_POSTS"
                step="1"
                placeholder="不限"
                :disabled="busy"
              /><span>条</span>
            </div>
          </div>
        </div>
        <SettingsSaveBar
          :dirty="dirty"
          :busy="busy"
          :done="done"
          label="保存保留策略"
          :done-text="doneText"
          @discard="form.discard"
        />
      </form>
    </ReadRegion>
  </section>
</template>
