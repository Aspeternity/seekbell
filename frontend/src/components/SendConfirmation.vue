<script setup lang="ts">
import { ref } from 'vue'
import { NAlert, NButton, NCard } from 'naive-ui'
import { channelNames, message, newRequestId, write } from '../management'
import type { ExplicitResult, Target } from '../management'
const props = defineProps<{
  csrf: string
  mode: 'test' | 'manual'
  resourceId: string
  target: Pick<Target, 'id' | 'name' | 'kind' | 'revision' | 'enabled'>
  title?: string
}>()
const emit = defineEmits<{ cancel: []; done: [value: ExplicitResult]; busy: [value: boolean] }>()
const requestId = newRequestId()
const busy = ref(false)
const error = ref('')
async function send() {
  if (busy.value) return
  busy.value = true
  emit('busy', true)
  error.value = ''
  try {
    const result = await write<ExplicitResult>(
      props.mode === 'test'
        ? '/targets/' + props.resourceId + '/test'
        : '/deliveries/' + props.resourceId + '/resend',
      'POST',
      { request_id: requestId, expected_revision: props.target.revision, confirmed: true },
      props.csrf,
    )
    emit('done', result)
  } catch (cause) {
    error.value =
      message(cause) +
      ' 若响应丢失，可用同一确认操作重试；请先查看记录，取消后重新确认会创建一次新发送。'
  } finally {
    busy.value = false
    emit('busy', false)
  }
}
</script>
<template>
  <NCard
    :title="mode === 'test' ? '确认发送测试通知' : '确认手动重发'"
    class="editor-card"
    aria-label="发送确认"
  >
    <NAlert v-if="error" type="error" class="notice">{{ error }}</NAlert>
    <p>
      目标：{{ target.name }} · {{ channelNames[target.kind] }} · 配置版本 {{ target.revision }}
    </p>
    <p v-if="title" class="post-text">原通知：{{ title }}</p>
    <p v-if="mode === 'test'">
      将向已保存的目标发送固定测试内容。测试不需要启用目标，不改变自动去重记录。
    </p>
    <p v-else>
      使用原通知内容与当前目标配置，标题标记“手动重发”，创建独立发送记录；不会重置或修复原自动投递状态。
    </p>
    <p class="muted">
      本次只尝试一次，不自动重试。结果未知时接收端可能已经收到，再次发送可能重复；SMTP
      成功仅表示邮件服务器接受。
    </p>
    <div class="actions">
      <NButton type="primary" :loading="busy" @click="send">{{
        mode === 'test' ? '确认发送测试' : '确认重发一次'
      }}</NButton
      ><NButton :disabled="busy" @click="emit('cancel')">取消发送</NButton>
    </div>
  </NCard>
</template>
