<script setup lang="ts">
import { computed } from 'vue'
import { useRemote } from '../history'
import { request } from '../store'
import { byteSize, stamp } from '../settings'
import ReadRegion from './ReadRegion.vue'
interface Storage {
  database_bytes: number
  backup_bytes: number
  backup_count: number
  filesystem_total_bytes: number
  filesystem_free_bytes: number
  checked_at: number
}
const data = useRemote(
  () => request<Storage>('manage/storage'),
  () => [],
  { cacheKey: () => 'settings:storage' },
)
const used = computed(() => {
  const storage = data.data.value
  if (!storage?.filesystem_total_bytes) return 0
  return Math.round((1 - storage.filesystem_free_bytes / storage.filesystem_total_bytes) * 100)
})
</script>
<template>
  <section class="panel settings-card" aria-labelledby="storage-title">
    <div class="panel-heading">
      <h2 id="storage-title">存储占用</h2>
      <button class="button" type="button" :disabled="data.loading.value" @click="data.reload()">
        刷新
      </button>
    </div>
    <div class="form-content form-stack">
      <ReadRegion
        :loading="data.loading.value"
        :error="data.error.value"
        :has-data="!!data.data.value"
        :min-height="90"
        @retry="data.reload"
      >
        <div v-if="data.data.value" class="form-stack">
          <dl class="detail-grid settings-metrics">
            <div>
              <dt>数据库</dt>
              <dd>{{ byteSize(data.data.value.database_bytes) }}</dd>
            </div>
            <div>
              <dt>备份</dt>
              <dd>
                {{
                  data.data.value.backup_count
                    ? data.data.value.backup_count +
                      ' 份 · ' +
                      byteSize(data.data.value.backup_bytes)
                    : '无'
                }}
                <a class="text-link" href="#/settings/backup?section=list">到备份页管理</a>
              </dd>
            </div>
            <div>
              <dt>磁盘可用 / 总量</dt>
              <dd>
                {{ byteSize(data.data.value.filesystem_free_bytes) }} /
                {{ byteSize(data.data.value.filesystem_total_bytes) }}（已用 {{ used }}%）
              </dd>
            </div>
          </dl>
          <p class="small-note">
            检查于 {{ stamp(data.data.value.checked_at) }} · 磁盘可用低于 500 MiB
            时会在运行中心提示并发送系统告警
          </p>
        </div>
      </ReadRegion>
    </div>
  </section>
</template>
