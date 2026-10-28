<script setup lang="ts">
import AppSelect from './AppSelect.vue'
import type { HotlistConfiguration, HotlistDraft } from '../hotlistSettings'
const props = defineProps<{
  config: HotlistConfiguration
  modelValue: HotlistDraft
  disabled?: boolean
}>()
const emit = defineEmits<{ 'update:modelValue': [value: HotlistDraft] }>()
function mode(value: 'recommended' | 'custom') {
  emit('update:modelValue', {
    mode: value,
    minutes:
      value === 'recommended'
        ? Object.fromEntries(props.config.periods.map((p) => [p.id, p.recommended_seconds / 60]))
        : { ...props.modelValue.minutes },
  })
}
function minutes(id: string, event: Event) {
  emit('update:modelValue', {
    ...props.modelValue,
    minutes: {
      ...props.modelValue.minutes,
      [id]: Number((event.target as HTMLInputElement).value),
    },
  })
}
</script>
<template>
  <section class="drawer-section website-hotlist-settings" aria-label="社区热榜配置">
    <div class="drawer-section-title">
      <h3>社区热榜</h3>
      <button
        v-if="modelValue.mode === 'custom'"
        class="text-link"
        :disabled="disabled"
        @click="mode('recommended')"
      >
        恢复推荐
      </button>
    </div>
    <p class="field-help hotlist-provider">
      来源：<a :href="config.provider_url" target="_blank" rel="noopener noreferrer">{{
        config.provider
      }}</a>
    </p>
    <label class="field-label" for="hotlist-refresh-mode">刷新设置</label>
    <AppSelect
      id="hotlist-refresh-mode"
      aria-label="热榜刷新设置"
      :model-value="modelValue.mode"
      :options="[
        { value: 'recommended', label: '使用推荐设置' },
        { value: 'custom', label: '自定义' },
      ]"
      :disabled="disabled"
      @update:model-value="mode"
    />
    <div class="hotlist-period-settings">
      <div v-for="period in config.periods" :key="period.id" class="hotlist-period-setting">
        <label :for="'hotlist-interval-' + period.id">{{ period.label }}榜</label>
        <span v-if="modelValue.mode === 'recommended'" class="hotlist-recommended">
          每 {{ period.recommended_seconds / 60 }} 分钟更新
        </span>
        <div v-else class="hotlist-custom-period">
          <div class="unit-input">
            <input
              :id="'hotlist-interval-' + period.id"
              class="text-input"
              type="number"
              inputmode="numeric"
              :aria-label="period.label + '榜刷新间隔'"
              :value="modelValue.minutes[period.id]"
              :min="period.minimum_seconds / 60"
              max="1440"
              step="1"
              :disabled="disabled"
              @input="minutes(period.id, $event)"
            /><span>分钟</span>
          </div>
          <span class="small-note">至少 {{ period.minimum_seconds / 60 }} 分钟</span>
        </div>
      </div>
    </div>
    <p class="field-help">
      仅在查看该榜单时按间隔更新，多个页面共用结果。此设置独立于新帖采集，不影响任务推送；
      来源限流时会延后重试。
    </p>
  </section>
</template>
<style scoped>
.hotlist-provider {
  margin-bottom: 18px;
}
.hotlist-provider a {
  color: var(--accent);
  overflow-wrap: anywhere;
}
.hotlist-period-settings {
  margin-top: 14px;
}
.hotlist-period-setting {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 14px 0;
  border-bottom: 1px solid #eff0f2;
}
.hotlist-period-setting:last-child {
  border-bottom: 0;
}
.hotlist-period-setting > label {
  font-size: 13px;
  color: #4d5762;
}
.hotlist-recommended {
  font-size: 13px;
  color: #6f7885;
}
.hotlist-custom-period {
  display: grid;
  gap: 6px;
}
.hotlist-custom-period .text-input {
  width: 110px;
  min-width: 0;
}
.hotlist-custom-period .small-note {
  margin: 0;
}
</style>
