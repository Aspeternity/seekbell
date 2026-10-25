<script setup lang="ts">
import { formatTime } from '../store'
import type { ConnectionCheck } from '../shared'

defineProps<{ result: ConnectionCheck; historical?: boolean }>()
const time = (value: number) => formatTime(new Date(value * 1000).toISOString())
</script>
<template>
  <div
    class="match-result"
    :class="historical ? 'connection-past' : result.status === 'success' ? 'yes' : 'unknown'"
    :role="historical ? undefined : 'status'"
  >
    <strong>
      {{ historical ? '当时结果：' : ''
      }}{{
        result.status === 'success'
          ? 'RSS 连接与解析成功'
          : result.status === 'failure'
            ? '连接测试失败'
            : result.status === 'deferred'
              ? '连接测试已延后'
              : '连接测试未完成'
      }}
    </strong>
    <p v-if="result.status === 'success'">有效帖子 {{ result.item_count }} 条，仅检查，未入库。</p>
    <p v-else-if="result.status === 'deferred'">
      {{ historical ? '当时' : '当前' }}来源正在处理其他请求或等待请求间隔。
    </p>
    <p v-else-if="result.code === 'access_challenge'">
      来源要求 Cloudflare 验证，{{
        historical ? '当时未能自动读取。' : '当前无法自动读取，稍后可重试。'
      }}
    </p>
    <p v-else-if="result.code === 'http_403'">
      来源{{ historical ? '当时' : '' }}拒绝访问（403）。
    </p>
    <p v-else-if="result.code === 'http_429'">
      来源{{ historical ? '当时' : '' }}请求受限（429）。
    </p>
    <p v-else-if="result.status === 'unknown'">检查未完成，无法确定连接状态，请重新测试。</p>
    <p v-else>诊断代码：{{ result.code }}</p>
    <p>{{ historical ? '测试时间' : '本次测试' }}：{{ time(result.started_at) }}</p>
  </div>
</template>
<style scoped>
.connection-past {
  background: var(--surface);
  border-color: var(--border);
  color: var(--muted);
}
</style>
