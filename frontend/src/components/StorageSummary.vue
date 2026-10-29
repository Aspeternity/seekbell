<script setup lang="ts">
import { useRemote } from '../history'
import { request, formatTime } from '../store'
import ReadRegion from './ReadRegion.vue'
interface Storage {
  database_bytes: number
  wal_bytes: number
  restore_bytes: number
  filesystem_total_bytes: number
  filesystem_free_bytes: number
  checked_at: number
}
const data = useRemote(
  () => request<Storage>('manage/storage'),
  () => [],
  { cacheKey: () => 'settings:storage' },
)
const size = (bytes: number) =>
  bytes >= 1024 ** 3
    ? (bytes / 1024 ** 3).toFixed(2) + ' GiB'
    : (bytes / 1024 ** 2).toFixed(2) + ' MiB'
defineExpose({ reload: data.reload })
</script>
<template>
  <ReadRegion
    :loading="data.loading.value"
    :error="data.error.value"
    :has-data="!!data.data.value"
    :min-height="120"
    @retry="data.reload"
  >
    <div v-if="data.data.value" class="form-stack">
      <dl class="detail-grid settings-metrics">
        <div>
          <dt>数据库</dt>
          <dd>{{ size(data.data.value.database_bytes) }}</dd>
        </div>
        <div>
          <dt>写入日志（WAL）</dt>
          <dd>{{ size(data.data.value.wal_bytes) }}</dd>
        </div>
        <div>
          <dt>独立恢复副本</dt>
          <dd>{{ size(data.data.value.restore_bytes) }}</dd>
        </div>
        <div>
          <dt>文件系统可用 / 总量</dt>
          <dd>
            {{ size(data.data.value.filesystem_free_bytes) }} /
            {{ size(data.data.value.filesystem_total_bytes) }}
          </dd>
        </div>
      </dl>
      <p class="small-note">
        检查于
        {{
          formatTime(new Date(data.data.value.checked_at * 1000).toISOString())
        }}。浏览器已下载的备份文件不计入服务端占用；清理历史不一定立即缩小数据库文件。
      </p>
    </div>
  </ReadRegion>
</template>
