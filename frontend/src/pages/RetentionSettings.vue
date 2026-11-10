<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { request } from '../store'
import { stamp, useSettingsForm } from '../settings'
import RetentionPreview from '../components/RetentionPreview.vue'
import FormFeedback from '../components/FormFeedback.vue'
import ReadRegion from '../components/ReadRegion.vue'
import SettingsSaveBar from '../components/SettingsSaveBar.vue'
interface Policy {
  days: number
  revision: number
  next_run_at: number
  last_run_at: number | null
  last_counts: Record<string, number>
}
const emit = defineEmits<{ dirty: [value: boolean] }>()
const labels: Record<string, string> = {
  posts: '帖子',
  evaluations: '规则判定',
  hits: '命中记录',
  deliveries: '自动投递',
  attempts: '投递尝试',
  tests: '目标测试',
  manual: '手动重发',
  source_runs: '采集记录',
  system_events: '系统事件',
  alerts: '告警投递',
}
const form = useSettingsForm<Policy, { days: number }>({
  name: '保留策略',
  read: () => request<Policy>('manage/retention'),
  write: (draft, saved) =>
    request<Policy>('manage/retention', 'PUT', { days: draft.days, revision: saved.revision }),
  draftOf: ({ days }) => ({ days }),
  validate: ({ days }) =>
    Number.isInteger(days) && days >= 1 && days <= 365 ? '' : '保留天数应为1–365之间的整数。',
  confirmSave: (draft, saved) =>
    draft.days < saved.days
      ? {
          body: '缩短为' + draft.days + '天后，超过期限的历史将被清理，已清理的数据无法恢复。',
          label: '确认保存策略',
        }
      : undefined,
  dirty: (value) => emit('dirty', value),
})
const { saved, draft, busy, error, reloadable, done, dirty } = form
const cleaned = computed(() =>
  Object.values(saved.value?.last_counts || {}).reduce((sum, count) => sum + count, 0),
)
onMounted(form.load)
</script>
<template>
  <section id="retention-settings" class="panel settings-card">
    <div class="panel-heading">
      <div>
        <h2>历史保留</h2>
        <p>超过期限的历史记录由后台每小时自动清理</p>
      </div>
    </div>
    <FormFeedback :error="error" :retryable="reloadable" @retry="form.reload" />
    <ReadRegion :loading="busy && !saved" error="" :has-data="!!saved" :min-height="260">
      <form v-if="saved" class="form-content form-stack" @submit.prevent="form.save">
        <section class="settings-section" aria-labelledby="retention-days-title">
          <div class="settings-section-heading">
            <h3 id="retention-days-title">保留期限</h3>
          </div>
          <div class="form-stack">
            <label for="retention-days">历史保留天数</label>
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
            <p class="small-note">1–365 天，默认 30 天。去重记录始终保留，旧帖不会重复推送。</p>
            <details class="settings-details">
              <summary>清理哪些记录</summary>
              <p class="small-note">
                帖子、判定、命中、已完成的投递与测试、采集记录和系统事件。待发送、重试中和未完成的操作及其依赖暂不清理，投递从完成时开始计算保留期。
              </p>
            </details>
            <RetentionPreview :days="draft.days" />
            <p v-if="!saved.last_run_at" class="small-note">尚未执行过清理。</p>
            <p v-else-if="!cleaned" class="small-note">
              最近一次清理于 {{ stamp(saved.last_run_at) }}，没有需要清理的记录。
            </p>
            <details v-else class="settings-details">
              <summary>
                最近一次清理于 {{ stamp(saved.last_run_at) }}，共 {{ cleaned }} 条记录
              </summary>
              <dl class="detail-grid retention-counts" aria-label="最近一批清理数量">
                <div v-for="(label, key) in labels" :key="key">
                  <dt>{{ label }}</dt>
                  <dd>{{ saved.last_counts[key] || 0 }}</dd>
                </div>
              </dl>
            </details>
          </div>
        </section>
        <SettingsSaveBar
          :dirty="dirty"
          :busy="busy"
          :done="done"
          label="保存保留策略"
          done-text="保留策略已保存"
          @discard="form.discard"
        />
      </form>
    </ReadRegion>
  </section>
</template>
