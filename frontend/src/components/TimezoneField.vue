<script setup lang="ts">
import { computed, ref } from 'vue'
import AppSelect from './AppSelect.vue'
const props = defineProps<{ modelValue: string; available: string[]; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
function choose(value: string) {
  emit('update:modelValue', value)
}
const search = ref('')
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
const options = computed(() => {
  const term = search.value.trim().toLocaleLowerCase()
  const available = [
    ...new Set([
      props.modelValue,
      ...Object.keys(names).filter((zone) => props.available.includes(zone)),
      ...props.available,
    ]),
  ]
  return available
    .filter(
      (zone) =>
        zone === props.modelValue ||
        !term ||
        (names[zone] || zone).toLocaleLowerCase().includes(term),
    )
    .map((zone) => ({
      value: zone,
      label: (names[zone] || zone) + (supported(zone) ? '' : '（浏览器不支持）'),
      disabled: !supported(zone),
    }))
})
const now = new Date()
const preview = computed(() =>
  supported(props.modelValue)
    ? new Intl.DateTimeFormat('zh-CN', {
        timeZone: props.modelValue,
        dateStyle: 'medium',
        timeStyle: 'short',
      }).format(now)
    : '当前浏览器不支持，网页时间暂以 UTC 显示',
)
</script>
<template>
  <div id="timezone-settings" class="form-stack">
    <div class="general-fields-grid">
      <div class="form-stack">
        <label for="timezone-search">搜索时区</label>
        <input
          id="timezone-search"
          v-model="search"
          class="text-input"
          type="search"
          placeholder="城市、中文名称或 IANA 时区"
          :disabled="disabled"
        />
      </div>
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
    </div>
    <p class="small-note">当前时刻预览：{{ preview }}</p>
    <p class="small-note">
      网页、日期筛选及之后发送的 Telegram、Bark、邮件通知按所选时区显示。数据和 Webhook 时间保持
      UTC；时区不改变采集频率或历史保留时长。
    </p>
  </div>
</template>
