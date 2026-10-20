<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { confirmAction, request, state } from './store'
interface Display {
  timezone: string
  revision: number
  available: string[]
}
let active = true
onBeforeUnmount(() => {
  active = false
})
const emit = defineEmits<{ dirty: [value: boolean] }>()
const saved = ref<Display | null>(null),
  timezone = ref('UTC'),
  error = ref(''),
  busy = ref(false),
  done = ref(false)
const dirty = computed(() => !!saved.value && saved.value.timezone !== timezone.value)
watch(dirty, (value) => emit('dirty', value), { immediate: true })
const supported = (zone: string) => {
  try {
    new Intl.DateTimeFormat('zh-CN', { timeZone: zone }).format()
    return true
  } catch {
    return false
  }
}
const zones = computed(() => (saved.value?.available || []).filter(supported))
const preview = computed(() =>
  supported(timezone.value)
    ? new Intl.DateTimeFormat('zh-CN', {
        timeZone: timezone.value,
        dateStyle: 'medium',
        timeStyle: 'short',
      }).format(new Date('2026-10-20T00:00:00Z'))
    : '当前浏览器不支持这个时区',
)
async function load() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  done.value = false
  try {
    const result = await request<Display>('manage/display')
    if (!active) return
    saved.value = result
    timezone.value = saved.value.timezone
    state.settings.timezone = saved.value.timezone
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    busy.value = false
  }
}
function reload() {
  if (dirty.value) confirmAction('重新读取时区？', '尚未保存的时区将丢失。', load, '放弃修改并读取')
  else load()
}
async function save() {
  if (busy.value || !saved.value || !dirty.value) return
  if (!zones.value.includes(timezone.value)) {
    error.value = '请选择有效且当前浏览器支持的时区。'
    return
  }
  busy.value = true
  error.value = ''
  done.value = false
  try {
    const result = await request<Display>('manage/display', 'PUT', {
      timezone: timezone.value,
      revision: saved.value.revision,
    })
    if (!active) return
    saved.value = result
    timezone.value = saved.value.timezone
    state.settings.timezone = saved.value.timezone
    done.value = true
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    busy.value = false
  }
}
onMounted(load)
</script>
<template>
  <section class="panel settings-card">
    <div class="panel-heading">
      <div>
        <h2>显示时区</h2>
        <p>让内容与投递时间符合你的习惯</p>
      </div>
    </div>
    <div v-if="error" class="form-errors" role="alert">{{ error }}</div>
    <form v-if="saved" class="form-content form-stack" @submit.prevent="save">
      <label for="display-timezone">显示时区</label>
      <select id="display-timezone" v-model="timezone" class="text-input" :disabled="busy">
        <option v-if="!supported(saved.timezone)" :value="saved.timezone">
          {{ saved.timezone }}（当前浏览器不支持）
        </option>
        <option v-for="zone in zones" :key="zone" :value="zone">{{ zone }}</option>
      </select>
      <p v-if="!supported(saved.timezone)" class="warning-note">
        当前浏览器不支持已保存时区，时间暂以 UTC 显示。请选择可用时区。
      </p>
      <p class="small-note">示例时刻 2026-10-20 00:00 UTC → {{ preview }}</p>
      <p>保存后，内容、投递、概览和系统事件按所选时区显示；日期筛选也按该时区计算。</p>
      <p class="small-note">
        数据仍以 UTC 保存。时区不会改变采集频率、历史保留时长或消息中的 UTC
        时间。首次创建管理员时使用浏览器时区，之后登录不会覆盖设置。
      </p>
      <div class="inline-form-footer">
        <span role="status">{{
          done ? '显示时区已保存' : dirty ? '有未保存的修改' : '使用已保存的时区'
        }}</span>
        <button class="button primary" :disabled="busy || !dirty">
          {{ busy ? '保存中…' : '保存显示时区' }}
        </button>
      </div>
      <button class="button" type="button" :disabled="busy" @click="reload">重新读取时区</button>
    </form>
    <div v-else class="form-content">
      <p>{{ busy ? '正在读取时区…' : '时区尚未读取。' }}</p>
      <button class="button" :disabled="busy" @click="load">重新读取时区</button>
    </div>
  </section>
</template>
