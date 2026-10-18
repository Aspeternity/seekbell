<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  NAlert,
  NButton,
  NCard,
  NCheckbox,
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  NSwitch,
  NTag,
} from 'naive-ui'
import {
  channelNames,
  fieldLabels,
  getSchemas,
  getTargets,
  getTarget,
  message,
  write,
} from '../management'
import type { Channel, FieldSchema, Schemas, Target } from '../management'

const props = defineProps<{ csrf: string }>()
const targets = ref<Target[]>([])
const schemas = ref<Schemas | null>(null)
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const warning = ref('')
const editing = ref<Target | null>(null)
const formOpen = ref(false)
const name = ref('')
const kind = ref<Channel>('bark')
const enabled = ref(false)
type Value = string | number | boolean | null
const values = ref<Record<string, Value>>({})
const resets = ref<string[]>([])
const fields = computed(() => Object.entries(schemas.value?.[kind.value].properties ?? {}))
const channels = Object.entries(channelNames).map(([value, label]) => ({ value, label }))

function optionLabel(value: string): string {
  const labels: Record<string, string> = {
    json_ok: 'JSON 中 ok 为 true',
    status: 'HTTP 2xx',
    tls: '隐式 TLS',
    starttls: 'STARTTLS',
    plain: '明文',
  }
  return labels[value] ?? value
}
function fieldType(schema: FieldSchema): string | undefined {
  return schema.type ?? schema.anyOf?.find((p) => p.type !== 'null')?.type
}
function text(key: string): string {
  return String(values.value[key] ?? '')
}
function number(key: string): number | null {
  const value = values.value[key]
  return typeof value === 'number' ? value : null
}
function clearSecrets() {
  for (const [key, field] of fields.value) if (field.writeOnly) values.value[key] = ''
  resets.value = []
}
function resetValues(target: Target | null = null) {
  values.value = {}
  resets.value = []
  for (const [key, field] of fields.value) {
    const value = target?.config[key] ?? field.default
    values.value[key] = field.writeOnly
      ? ''
      : typeof value === 'object'
        ? null
        : ((value as Value) ?? null)
  }
}
function start(target: Target | null = null) {
  editing.value = target
  name.value = target?.name ?? ''
  kind.value = target?.kind ?? 'bark'
  enabled.value = target?.enabled ?? false
  error.value = notice.value = warning.value = ''
  resetValues(target)
  formOpen.value = true
}
function changeKind(value: Channel) {
  kind.value = value
  resetValues()
}
function cancel() {
  clearSecrets()
  formOpen.value = false
  editing.value = null
}

async function edit(target: Target) {
  busy.value = true
  error.value = ''
  try {
    start(await getTarget(target.id))
  } catch (cause) {
    error.value = message(cause)
  } finally {
    busy.value = false
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    ;[schemas.value, targets.value] = await Promise.all([getSchemas(), getTargets()])
  } catch (cause) {
    error.value = message(cause)
  } finally {
    loading.value = false
  }
}
async function save() {
  if (!schemas.value || busy.value) return
  error.value = notice.value = warning.value = ''
  busy.value = true
  try {
    const config: Record<string, unknown> = {}
    for (const [key, field] of fields.value) {
      if (resets.value.includes(key)) {
        config[key] = field.default
        continue
      }
      const value = values.value[key]
      if (field.writeOnly && (value === '' || value === null || value === undefined)) continue
      config[key] = fieldType(field) === 'object' ? JSON.parse(String(value || '{}')) : value
    }
    const response = editing.value
      ? await write<Target>(
          '/targets/' + editing.value.id,
          'PUT',
          {
            name: name.value,
            config,
            expected_revision: editing.value.revision,
          },
          props.csrf,
        )
      : await write<Target>(
          '/targets',
          'POST',
          { name: name.value, kind: kind.value, enabled: enabled.value, config },
          props.csrf,
        )
    cancel()
    targets.value = await getTargets()
    notice.value = '通知目标已保存。'
    if (response.duplicate_ids?.length)
      warning.value = '检测到相同接收端的其他目标；任务选择时请避免重复通知。'
  } catch (cause) {
    error.value = cause instanceof SyntaxError ? '请求头必须是有效的 JSON 对象。' : message(cause)
  } finally {
    clearSecrets()
    busy.value = false
  }
}
async function toggle(target: Target) {
  busy.value = true
  error.value = notice.value = ''
  try {
    await write(
      '/targets/' + target.id + '/enabled',
      'PUT',
      { enabled: !target.enabled },
      props.csrf,
    )
    targets.value = await getTargets()
    notice.value = '目标状态已更新；重新启用不会恢复已取消的消息。'
  } catch (cause) {
    error.value = message(cause)
  } finally {
    busy.value = false
  }
}
onMounted(load)
</script>

<template>
  <section aria-label="通知目标管理" :aria-busy="loading || busy">
    <div class="panel-heading">
      <h2>通知目标</h2>
      <div class="actions">
        <NButton :loading="loading" :disabled="busy" @click="load">刷新目标</NButton>
        <NButton type="primary" :disabled="busy || !schemas" @click="start()">新建通知目标</NButton>
      </div>
    </div>
    <p class="muted">支持四种渠道。目标停用后停止发送与重试；重新启用不会补发已取消的消息。</p>
    <NAlert v-if="error" type="error" role="alert" class="notice">{{ error }}</NAlert>
    <NAlert v-if="notice" type="success" role="status" class="notice">{{ notice }}</NAlert>
    <NAlert v-if="warning" type="warning" role="status" class="notice">{{ warning }}</NAlert>
    <NCard v-if="formOpen" :title="editing ? '编辑通知目标' : '新建通知目标'" class="editor-card">
      <NForm @submit.prevent="save">
        <NFormItem label="目标名称" :label-props="{ for: 'target-name' }">
          <NInput
            v-model:value="name"
            :maxlength="200"
            :disabled="busy"
            :input-props="{ id: 'target-name', required: true }"
          />
        </NFormItem>
        <NFormItem label="渠道" :label-props="{ for: 'target-channel' }">
          <select
            id="target-channel"
            :value="kind"
            class="native-select"
            :disabled="busy || !!editing"
            @change="changeKind(($event.target as HTMLSelectElement).value as Channel)"
          >
            <option v-for="option in channels" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>
        </NFormItem>
        <NFormItem v-if="!editing" label="启用目标">
          <NSwitch v-model:value="enabled" :disabled="busy" aria-label="启用目标" />
        </NFormItem>
        <p class="muted">
          敏感配置保存后不回传。编辑时留空保留原值；勾选“恢复默认值”可清空可选凭据或恢复渠道默认。
        </p>
        <div class="form-grid">
          <NFormItem
            v-for="[key, field] in fields"
            :key="key"
            :label="fieldLabels[key] ?? key"
            :label-props="{ for: 'target-' + key }"
          >
            <div class="schema-field">
              <NSwitch
                v-if="fieldType(field) === 'boolean'"
                :value="Boolean(values[key])"
                :disabled="busy"
                :aria-label="fieldLabels[key]"
                @update:value="values[key] = $event"
              />
              <select
                v-else-if="field.enum"
                :id="'target-' + key"
                :value="text(key)"
                class="native-select"
                :disabled="busy"
                @change="values[key] = ($event.target as HTMLSelectElement).value"
              >
                <option v-for="option in field.enum" :key="option" :value="option">
                  {{ optionLabel(option) }}
                </option>
              </select>
              <NInputNumber
                v-else-if="fieldType(field) === 'integer'"
                :value="number(key)"
                :min="field.minimum"
                :max="field.maximum"
                :precision="0"
                :disabled="busy"
                :input-props="{ id: 'target-' + key }"
                @update:value="values[key] = $event"
              />
              <NInput
                v-else
                :value="text(key)"
                :type="
                  fieldType(field) === 'object' ? 'textarea' : field.writeOnly ? 'password' : 'text'
                "
                show-password-on="click"
                :maxlength="field.maxLength"
                :disabled="busy || resets.includes(key)"
                :placeholder="
                  editing?.configured_secrets.includes(key)
                    ? '已配置，留空保留'
                    : field.default !== undefined
                      ? '可留空使用默认值'
                      : '请输入'
                "
                :input-props="{
                  id: 'target-' + key,
                  autocomplete: 'off',
                  required:
                    schemas?.[kind].required?.includes(key) &&
                    !editing?.configured_secrets.includes(key),
                }"
                @update:value="values[key] = $event"
              />
              <NCheckbox
                v-if="editing && field.writeOnly && field.default !== undefined"
                :checked="resets.includes(key)"
                :disabled="busy"
                @update:checked="
                  (value) => (resets = value ? [...resets, key] : resets.filter((k) => k !== key))
                "
                >恢复默认值</NCheckbox
              >
            </div>
          </NFormItem>
        </div>
        <div class="actions">
          <NButton type="primary" attr-type="submit" :loading="busy">保存通知目标</NButton>
          <NButton :disabled="busy" @click="cancel">取消编辑</NButton>
        </div>
      </NForm>
    </NCard>
    <p v-if="!loading && !targets.length" class="empty">
      还没有通知目标。先创建一个目标，再为监控任务选择接收端。
    </p>
    <NCard v-for="target in targets" :key="target.id" :title="target.name" class="record-card">
      <div class="record-meta">
        <NTag>{{ channelNames[target.kind] }}</NTag
        ><NTag :type="target.enabled ? 'success' : 'default'">{{
          target.enabled ? '已启用' : '已停用'
        }}</NTag>
      </div>
      <p class="muted">
        {{
          target.configured_secrets.length
            ? '敏感配置已保存，编辑时不会显示原值。'
            : '尚未保存敏感配置。'
        }}
      </p>
      <div class="actions">
        <NButton :disabled="busy || formOpen" @click="edit(target)">编辑 {{ target.name }}</NButton>
        <NButton :disabled="busy || formOpen" @click="toggle(target)"
          >{{ target.enabled ? '停用' : '启用' }} {{ target.name }}</NButton
        >
      </div>
    </NCard>
    <p class="muted">本检查点提供配置管理；目标发送测试与投递记录将在后续接入。</p>
  </section>
</template>
