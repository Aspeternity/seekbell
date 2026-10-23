<script setup lang="ts">
import Icon from './Icon.vue'
import { formatTime } from '../store'
import { postLabels, reasonText, resultClass, type Evaluation } from '../history'
defineProps<{ evaluation: Evaluation }>()
const emit = defineEmits<{ navigate: [path: string] }>()
</script>
<template>
  <article class="snapshot-task history-evaluation">
    <div class="evaluation-copy">
      <div class="evaluation-heading">
        <Icon name="layers" :size="16" />
        <button
          v-if="!evaluation.deleted"
          class="text-link"
          @click="emit('navigate', '/task/' + evaluation.task_id)"
        >
          {{ evaluation.name }}
        </button>
        <strong v-else>{{ evaluation.name }} · 已删除</strong>
      </div>
      <p class="small-note">
        任务配置 v{{ evaluation.version }} ·
        {{ formatTime(new Date(evaluation.at * 1000).toISOString()) }}
      </p>
      <span class="result-pill" :class="resultClass(evaluation.result.status)">{{
        postLabels[evaluation.result.status]
      }}</span>
      <ul v-if="evaluation.result.reasons.length" class="evaluation-reasons">
        <li v-for="(reason, index) in evaluation.result.reasons" :key="index">
          {{ reasonText(reason) }}
        </li>
      </ul>
      <p v-else class="small-note">未设置筛选条件，或旧记录未留下原因。</p>
    </div>
  </article>
</template>
<style scoped>
.evaluation-copy {
  min-width: 0;
  width: 100%;
}
.evaluation-heading {
  display: flex;
  align-items: flex-start;
  gap: 5px;
  overflow-wrap: anywhere;
}
.evaluation-heading svg {
  flex-shrink: 0;
}
.evaluation-heading button {
  text-align: left;
  white-space: normal;
  overflow-wrap: anywhere;
}
.evaluation-copy > .small-note {
  margin: 8px 0;
}
.evaluation-reasons {
  list-style: none;
  padding: 0;
  margin: 12px 0 0;
  line-height: 1.8;
  overflow-wrap: anywhere;
}
.evaluation-reasons li + li {
  margin-top: 4px;
}
</style>
