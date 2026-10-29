<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import AppSelect from './AppSelect.vue'
const props = defineProps<{ modelValue: string; available: string[]; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
function choose(value: string) {
  emit('update:modelValue', value)
}
const names: Record<string, string> = {
  'Asia/Shanghai': '中国标准时间 · 上海 · Asia/Shanghai',
  UTC: '协调世界时 · UTC',
  'Asia/Tokyo': '日本标准时间 · 东京 · Asia/Tokyo',
  'America/Los_Angeles': '洛杉矶 · America/Los_Angeles',
  'Europe/London': '伦敦 · Europe/London',
}
const supported = (zone: string) => {
  try {
    new Intl.DateTimeFormat('zh-CN', { timeZone: zone }).format()
    return true
  } catch {
    return false
  }
}
// Common zones lead the list; the rest keep the server's IANA order so
// keyboard type-ahead by region prefix (for example "Asia/") still works.
const options = computed(() => {
  const common = Object.keys(names).filter((zone) => props.available.includes(zone))
  const rest = props.available.filter((zone) => !common.includes(zone))
  if (props.modelValue && !props.available.includes(props.modelValue))
    rest.unshift(props.modelValue)
  return [
    ...common.map((zone) => ({ zone, group: '常用时区' })),
    ...rest.map((zone) => ({ zone, group: '全部时区' })),
  ].map(({ zone, group }) => ({
    value: zone,
    label: (names[zone] || zone) + (supported(zone) ? '' : '（浏览器不支持）'),
    disabled: !supported(zone),
    group,
  }))
})
const now = ref(new Date())
const clock = window.setInterval(() => (now.value = new Date()), 30_000)
onBeforeUnmount(() => window.clearInterval(clock))
const preview = computed(() => {
  if (!supported(props.modelValue)) return '当前浏览器不支持，网页时间暂以 UTC 显示'
  const time = new Intl.DateTimeFormat('zh-CN', {
    timeZone: props.modelValue,
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(now.value)
  const offset = new Intl.DateTimeFormat('en-US', {
    timeZone: props.modelValue,
    timeZoneName: 'shortOffset',
  })
    .formatToParts(now.value)
    .find((part) => part.type === 'timeZoneName')
    ?.value.replace(/^GMT/, 'UTC')
  return offset ? time + ' · ' + (offset === 'UTC' ? 'UTC+0' : offset) : time
})
</script>
<template>
  <div id="timezone-settings" class="form-stack">
    <div class="general-fields-grid">
      <div class="form-stack">
        <label for="display-timezone">显示时区</label>
        <AppSelect
          id="display-timezone"
          :model-value="modelValue"
          :options="options"
          :disabled="disabled"
          aria-label="显示时区"
          @update:model-value="choose"
        />
      </div>
      <div class="form-stack">
        <span id="timezone-preview-label" class="timezone-preview-label">当前时间</span>
        <output class="timezone-preview" aria-labelledby="timezone-preview-label">{{
          preview
        }}</output>
      </div>
    </div>
    <p class="small-note">
      网页、日期筛选及之后发送的 Telegram、Bark、邮件通知按所选时区显示；数据和 Webhook 保持
      UTC，时区不影响采集频率或历史保留时长。
    </p>
  </div>
</template>
