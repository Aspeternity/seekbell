<script setup lang="ts">
import { ref } from 'vue'
import { formatTime, request } from '../store'
import { useRemote, resultLabels, kindLabels } from '../history'
import type { Page } from '../history'
import Pagination from './Pagination.vue'
import ReadRegion from './ReadRegion.vue'
interface Event {
  id: string
  label: string
  phase: string
  code: string | null
  at: number
  deliveries: Record<string, number>
}
interface Delivery {
  id: string
  target_name: string
  kind: string
  result: string
  error_code: string | null
  started_at: number | null
  finished_at: number | null
}
const showRecords = ref(false)
const eventPage = ref(1),
  selected = ref(''),
  detailPage = ref(1)
const events = useRemote(
  () => request<Page<Event>>('manage/alerts/history?page=' + eventPage.value),
  () => [eventPage.value],
  { cacheKey: () => 'alerts:events:' + eventPage.value, keepPrevious: true },
)
const details = useRemote(
  () =>
    selected.value
      ? request<Page<Delivery>>(
          'manage/alerts/history/' + selected.value + '?page=' + detailPage.value,
        )
      : Promise.resolve(undefined),
  () => [selected.value, detailPage.value],
  {
    cacheKey: () =>
      selected.value
        ? JSON.stringify(['alerts:detail', selected.value, detailPage.value])
        : undefined,
    keepPrevious: true,
    scope: () => selected.value,
  },
)
const labels: Record<string, string> = { ...resultLabels, pending: '等待发送', cancelled: '已取消' }
const stamp = (value: number | null) =>
  value ? formatTime(new Date(value * 1000).toISOString()) : '尚未记录'
function open(id: string) {
  selected.value = selected.value === id ? '' : id
  detailPage.value = 1
}
function reload() {
  events.reload()
  if (selected.value) details.reload()
}
defineExpose({ reload })
</script>
<template>
  <section class="panel settings-card settings-event-log">
    <div class="panel-heading">
      <div>
        <h2>系统事件与告警记录</h2>
        <p>故障、恢复及各告警目标的发送结果</p>
      </div>
      <button class="button" :aria-expanded="showRecords" @click="showRecords = !showRecords">
        {{ showRecords ? '收起告警记录' : '查看系统告警记录' }}
      </button>
    </div>
    <div v-if="showRecords" class="form-content">
      <ReadRegion
        :loading="events.loading.value"
        :error="events.error.value"
        :has-data="!!events.data.value"
        :stale="events.stale.value"
        :min-height="160"
        @retry="events.reload"
        ><template v-if="events.data.value">
          <p v-if="!events.data.value.total">尚无系统状态变化记录。</p>
          <article
            v-for="event in events.data.value.items"
            :key="event.id"
            class="history-evaluation system-event"
          >
            <strong>{{ event.phase === 'fault' ? '故障' : '恢复' }} · {{ event.label }}</strong>
            <p>
              {{ stamp(event.at) }} <span v-if="event.code"> · {{ event.code }}</span>
            </p>
            <p v-if="!Object.keys(event.deliveries).length">
              事件发生时未启用告警或未选择目标，未生成通知。
            </p>
            <p v-for="(count, result) in event.deliveries" :key="result">
              {{ labels[result] || result }}：{{ count }}
            </p>
            <button class="button" @click="open(event.id)">
              {{ selected === event.id ? '收起投递结果' : '查看各目标结果' }}
            </button>
            <template v-if="selected === event.id">
              <ReadRegion
                :loading="details.loading.value"
                :error="details.error.value"
                :has-data="!!details.data.value"
                :stale="details.stale.value"
                :min-height="160"
                @retry="details.reload"
                ><template v-if="details.data.value">
                  <p v-if="!details.data.value.total">没有对应的告警投递。</p>
                  <article
                    v-for="item in details.data.value.items"
                    :key="item.id"
                    class="alert-delivery"
                  >
                    <strong>{{ item.target_name }} · {{ kindLabels[item.kind] }}</strong>
                    <p>
                      {{ labels[item.result] || item.result }}
                      <span v-if="item.error_code"> · {{ item.error_code }}</span>
                    </p>
                    <p>开始 {{ stamp(item.started_at) }} · 完成 {{ stamp(item.finished_at) }}</p>
                  </article>
                  <Pagination
                    label="告警投递"
                    :page="detailPage"
                    :page-size="20"
                    :total="details.data.value.total"
                    @change="detailPage = $event"
                  /> </template
              ></ReadRegion>
            </template>
          </article>
          <Pagination
            label="系统事件"
            :page="eventPage"
            :page-size="20"
            :total="events.data.value.total"
            @change="eventPage = $event"
          /> </template
      ></ReadRegion>
    </div>
  </section>
</template>
