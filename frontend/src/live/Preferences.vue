<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import Icon from '../prototype/components/Icon.vue'
import Toggle from '../prototype/components/Toggle.vue'
import { state, request, confirmAction, refresh } from './store'
const emit = defineEmits<{ dirty: [value: boolean] }>()
let active = true
onBeforeUnmount(() => {
  active = false
})
const draft = reactive({ ...state.settings, alertTargets: [...state.settings.alertTargets] })
const baseline = ref(JSON.stringify(draft))
const loaded = ref(false),
  busy = ref(false),
  errors = ref<string[]>([])
const revisions = reactive({ display: 0, retention: 0, alerts: 0 })
const zones = ref<string[]>([])
const zoneLabels: Record<string, string> = {
  'Asia/Shanghai': '中国标准时间 · Asia/Shanghai',
  UTC: '协调世界时 · UTC',
  'Asia/Tokyo': '日本标准时间 · Asia/Tokyo',
  'America/Los_Angeles': '洛杉矶 · America/Los_Angeles',
}
const dirty = computed(() => loaded.value && JSON.stringify(draft) !== baseline.value)
watch(dirty, (value) => emit('dirty', value))
async function load() {
  if (busy.value) return
  busy.value = true
  errors.value = []
  try {
    const [display, retention, alerts] = await Promise.all([
      request('manage/display'),
      request('manage/retention'),
      request('manage/alerts'),
    ])
    if (!active) return
    revisions.display = display.revision
    revisions.retention = retention.revision
    revisions.alerts = alerts.revision
    zones.value = display.available
    Object.assign(draft, {
      ...state.settings,
      timezone: display.timezone,
      retention: retention.days,
      recoveryAlerts: alerts.enabled,
      alertTargets: [...alerts.target_ids],
    })
    baseline.value = JSON.stringify(draft)
    loaded.value = true
  } catch (error) {
    if (active) errors.value = [(error as Error).message]
  } finally {
    busy.value = false
  }
}
function reload() {
  const read = async () => {
    if (busy.value) return
    busy.value = true
    errors.value = []
    try {
      await refresh()
      if (!active) return
    } catch (error) {
      if (active) errors.value = [(error as Error).message]
      return
    } finally {
      busy.value = false
    }
    if (active) await load()
  }
  if (dirty.value)
    confirmAction('重新读取偏好设置？', '尚未保存的偏好修改将丢失。', read, '放弃修改并读取')
  else read()
}
function save() {
  if (busy.value || !loaded.value) return
  errors.value = []
  if (!draft.workspaceName.trim() || draft.workspaceName.trim().length > 24)
    errors.value.push('工作空间名称应为1–24个字符。')
  if (draft.workspaceDescription.trim().length > 40) errors.value.push('工作空间说明最多40个字符。')
  if (!zones.value.includes(draft.timezone)) errors.value.push('请选择有效的显示时区。')
  if (!Number.isInteger(draft.retention) || draft.retention < 1 || draft.retention > 365)
    errors.value.push('保留天数应为1–365之间的整数。')
  if (draft.recoveryAlerts && !draft.alertTargets.length)
    errors.value.push('启用告警需至少选择一个通知目标。')
  if (errors.value.length || !dirty.value) return
  const prior = JSON.parse(baseline.value)
  if (
    draft.retention !== prior.retention ||
    draft.recoveryAlerts !== prior.recoveryAlerts ||
    JSON.stringify(draft.alertTargets) !== JSON.stringify(prior.alertTargets)
  ) {
    confirmAction(
      '保存偏好设置？',
      (draft.retention !== prior.retention
        ? '保存后会清理超过' + draft.retention + '天的普通历史；已清理的数据无法通过改回天数恢复。'
        : '') +
        (draft.recoveryAlerts !== prior.recoveryAlerts ||
        JSON.stringify(draft.alertTargets) !== JSON.stringify(prior.alertTargets)
          ? '告警设置会影响之后的故障与恢复通知，在途消息无法撤回。'
          : ''),
      persist,
      '确认保存设置',
    )
  } else persist()
}
async function persist() {
  if (busy.value || !active) return
  busy.value = true
  errors.value = []
  const before = baseline.value
  const prior = JSON.parse(baseline.value)
  const remember = (values: object) => {
    Object.assign(prior, values)
    baseline.value = JSON.stringify(prior)
  }
  try {
    if (
      draft.workspaceName !== prior.workspaceName ||
      draft.workspaceDescription !== prior.workspaceDescription
    ) {
      const name = draft.workspaceName.trim()
      const description = draft.workspaceDescription.trim()
      await request('manage/workspace', 'PUT', { name, description })
      if (!active) return
      state.settings.workspaceName = name
      state.settings.workspaceDescription = description
      draft.workspaceName = name
      draft.workspaceDescription = description
      remember({
        workspaceName: draft.workspaceName,
        workspaceDescription: draft.workspaceDescription,
      })
    }
    if (draft.timezone !== prior.timezone) {
      const value = await request('manage/display', 'PUT', {
        timezone: draft.timezone,
        revision: revisions.display,
      })
      if (!active) return
      revisions.display = value.revision
      state.settings.timezone = value.timezone
      draft.timezone = value.timezone
      remember({ timezone: value.timezone })
    }
    if (draft.retention !== prior.retention) {
      const value = await request('manage/retention', 'PUT', {
        days: draft.retention,
        revision: revisions.retention,
      })
      if (!active) return
      revisions.retention = value.revision
      state.settings.retention = value.days
      draft.retention = value.days
      remember({ retention: value.days })
    }
    if (
      draft.recoveryAlerts !== prior.recoveryAlerts ||
      JSON.stringify(draft.alertTargets) !== JSON.stringify(prior.alertTargets)
    ) {
      const value = await request('manage/alerts', 'PUT', {
        enabled: draft.recoveryAlerts,
        target_ids: draft.alertTargets,
        revision: revisions.alerts,
      })
      if (!active) return
      revisions.alerts = value.revision
      state.settings.recoveryAlerts = value.enabled
      state.settings.alertTargets = [...value.target_ids]
      draft.recoveryAlerts = value.enabled
      draft.alertTargets = [...value.target_ids]
      remember({ recoveryAlerts: value.enabled, alertTargets: [...value.target_ids] })
    }
  } catch (error) {
    if (active)
      errors.value = [
        (baseline.value !== before ? '部分设置已保存；未完成的修改仍保留。' : '') +
          (error as Error).message,
      ]
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
        <h2>工作空间与偏好</h2>
        <p>让这片信息空间，有自己的名字</p>
      </div>
      <Icon name="clock" :size="19" />
    </div>
    <div v-if="errors.length" class="form-errors" role="alert">
      <p v-for="error in errors" :key="error">{{ error }}</p>
      <button class="button" :disabled="busy" @click="reload">重新读取偏好设置</button>
    </div>
    <form class="form-content form-stack" @submit.prevent="save">
      <fieldset class="plain-fieldset form-stack" :disabled="busy || !loaded">
        <h3>工作空间</h3>
        <p class="small-note">名称与说明显示在左侧导航顶部，方便识别你的工作空间。</p>
        <div class="workspace-settings-fields">
          <label for="workspace-name">工作空间名称</label>
          <input
            id="workspace-name"
            v-model="draft.workspaceName"
            class="text-input"
            maxlength="24"
            placeholder="例如：我的信息雷达"
            :aria-invalid="errors.length > 0 && !draft.workspaceName.trim()"
          />
          <p class="small-note">最多 24 个字符。</p>
          <label for="workspace-description">工作空间说明 <span class="optional">选填</span></label>
          <input
            id="workspace-description"
            v-model="draft.workspaceDescription"
            class="text-input"
            maxlength="40"
            placeholder="例如：技术、好价与日常关注"
          />
        </div>
        <div class="workspace-preview" aria-label="工作空间外观预览">
          <span class="workspace-icon" aria-hidden="true">{{
            draft.workspaceName.trim() === '个人工作空间'
              ? 'S'
              : Array.from(draft.workspaceName.trim())[0]?.toUpperCase() || 'S'
          }}</span>
          <span class="workspace-copy"
            ><strong :title="draft.workspaceName">{{
              draft.workspaceName.trim() || '工作空间名称'
            }}</strong
            ><small v-if="draft.workspaceDescription.trim()" :title="draft.workspaceDescription">{{
              draft.workspaceDescription.trim()
            }}</small></span
          >
          <span class="workspace-dot" aria-hidden="true" />
        </div>
        <p class="small-note">上方为外观预览，保存后同步到导航；此名称不会更改管理员登录账号。</p>
        <div class="subtle-divider" />
        <h3>时间与历史</h3>

        <label
          >显示时区<select v-model="draft.timezone" class="text-input" aria-label="显示时区">
            <option v-for="zone in zones" :key="zone" :value="zone">
              {{ zoneLabels[zone] || zone }}
            </option>
          </select></label
        >
        <p class="small-note">帖子与投递存储 UTC，展示按所选时区转换。</p>
        <label
          >普通历史保留天数
          <div class="unit-input">
            <input
              aria-label="普通历史保留天数"
              v-model.number="draft.retention"
              type="number"
              min="1"
              max="365"
              class="text-input"
              required
            /><span>天</span>
          </div></label
        >
        <div class="info-note">
          <Icon name="shield" :size="18" />
          <p>独立去重标识不随普通历史删除。后台按已保存策略清理过期普通历史。</p>
        </div>
        <div class="subtle-divider" />
        <h3>系统告警</h3>
        <div class="setting-row no-border">
          <div>
            <strong>故障与恢复通知</strong><small>每次状态变化通知一次，避免每轮重复。</small>
          </div>
          <Toggle
            v-model="draft.recoveryAlerts"
            label="故障与恢复通知"
            :disabled="busy || !loaded"
          />
        </div>
        <fieldset class="plain-fieldset">
          <legend class="field-label">告警通知目标</legend>
          <div class="form-stack">
            <label v-for="target in state.targets" :key="target.id" class="check-label"
              ><input v-model="draft.alertTargets" type="checkbox" :value="target.id" />{{
                target.name
              }}<span class="small-badge neutral">{{
                target.enabled ? '已启用' : '已暂停'
              }}</span></label
            >
          </div>
        </fieldset>
      </fieldset>
      <div class="inline-form-footer">
        <span>{{ !loaded ? '正在读取设置…' : dirty ? '有未保存的修改' : '设置已保存' }}</span
        ><button class="button primary" type="submit" :disabled="busy || !loaded">
          {{ busy ? '保存中…' : '保存偏好设置' }}
        </button>
      </div>
    </form>
  </section>
</template>
