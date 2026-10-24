<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import ResultDialog from './ResultDialog.vue'
import Pagination from './Pagination.vue'
import { statusLabel } from '../model'
import type { MatchResult, Sample } from '../model'
import { websiteName } from '../store'
const props = defineProps<{ items: { sample: Sample; result: MatchResult }[] }>()
const emit = defineEmits<{ close: [] }>()
const filter = ref('all'),
  page = ref(1)
const filtered = computed(() =>
  props.items.filter((item) => filter.value === 'all' || item.result.status === filter.value),
)
const visible = computed(() => filtered.value.slice((page.value - 1) * 10, page.value * 10))
watch(filter, () => (page.value = 1))
</script>
<template>
  <ResultDialog title="历史试匹配结果" @close="emit('close')">
    <p class="trial-dialog-note">使用本次试算的规则与样本；筛选、翻页不会重新试算或发送通知。</p>
    <div class="trial-result-filters" role="group" aria-label="试算结果筛选">
      <button
        v-for="item in [
          { value: 'all', label: '全部' },
          { value: 'yes', label: '命中' },
          { value: 'no', label: '未命中' },
          { value: 'unknown', label: '信息不足' },
        ]"
        :key="item.value"
        type="button"
        :class="{ selected: filter === item.value }"
        :aria-pressed="filter === item.value"
        @click="filter = item.value"
      >
        {{ item.label }}
        {{
          item.value === 'all'
            ? items.length
            : items.filter((row) => row.result.status === item.value).length
        }}
      </button>
    </div>
    <div class="trial-result-list">
      <article
        v-for="(item, index) in visible"
        :key="(page - 1) * 10 + index"
        class="trial-result-row"
      >
        <div class="trial-result-heading">
          <span class="result-pill" :class="item.result.status">{{
            statusLabel[item.result.status]
          }}</span>
          <span v-if="item.sample.websiteId" class="plain-chip">{{
            websiteName(item.sample.websiteId)
          }}</span>
          <strong>{{ item.sample.title }}</strong>
        </div>
        <p v-if="item.result.headline">{{ item.result.headline }}</p>
        <details>
          <summary>查看详细原因</summary>
          <ul>
            <li v-for="(reason, i) in item.result.reasons" :key="i">{{ reason }}</li>
          </ul>
        </details>
      </article>
      <p v-if="!filtered.length" role="status">本次样本中没有此类结果。</p>
    </div>
    <template #footer>
      <Pagination
        :page="page"
        :total="filtered.length"
        :page-size="10"
        label="试算结果"
        @change="page = $event"
      />
    </template>
  </ResultDialog>
</template>
<style scoped>
.trial-dialog-note {
  color: #737e8c;
  font-size: 12px;
  margin: 0 0 16px;
}
.trial-result-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 15px;
}
.trial-result-filters button {
  padding: 7px 11px;
  border: 1px solid #e4e8ec;
  border-radius: 6px;
  background: #fff;
  color: #6c7886;
}
.trial-result-filters button.selected {
  border-color: #dbad90;
  color: var(--accent);
  background: #fdf8f4;
}
.trial-result-row {
  padding: 14px 0;
  border-bottom: 1px solid #eceff2;
}
.trial-result-heading {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.trial-result-heading strong {
  flex-basis: 100%;
  font-size: 13px;
  overflow-wrap: anywhere;
}
.trial-result-row p,
.trial-result-row details {
  font-size: 12px;
  line-height: 1.8;
  margin: 8px 0;
}
.trial-result-row summary {
  color: var(--accent);
  cursor: pointer;
}
.trial-result-row ul {
  padding-left: 20px;
}
</style>
