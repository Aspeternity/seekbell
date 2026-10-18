<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { NAlert, NButton, NCard, NForm, NFormItem, NInput, NSwitch, NTag } from 'naive-ui'
import { getContent, getHistoricalTasks, localDate, message, reasonText } from '../management'
import type { ContentPage, HistoricalTask } from '../management'

const loading = ref(false)
const error = ref('')
const query = ref('')
const author = ref('')
const category = ref('')
const taskId = ref('')
const matchedOnly = ref(false)
const offset = ref(0)
const limit = 20
const result = ref<ContentPage | null>(null)
const tasks = ref<HistoricalTask[]>([])
async function load() {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try {
    result.value = await getContent(
      new URLSearchParams({
        offset: String(offset.value),
        limit: String(limit),
        query: query.value.trim(),
        author: author.value.trim(),
        category: category.value.trim(),
        matched_only: String(matchedOnly.value),
        ...(taskId.value ? { task_id: taskId.value } : {}),
      }),
    )
  } catch (cause) {
    error.value = message(cause)
  } finally {
    loading.value = false
  }
}
async function search() {
  offset.value = 0
  await load()
}
async function page(delta: number) {
  offset.value += delta * limit
  await load()
}
onMounted(async () => {
  try {
    tasks.value = await getHistoricalTasks()
  } catch (cause) {
    error.value = message(cause)
  }
  await load()
})
</script>

<template>
  <section aria-label="内容与命中记录" :aria-busy="loading">
    <div class="panel-heading">
      <h2>内容与命中</h2>
      <NButton :loading="loading" @click="load">刷新内容</NButton>
    </div>
    <p class="muted">
      只查看本地保留帖子与历史命中，不访问论坛、不补发通知。时间按系统显示时区显示。
    </p>
    <NAlert v-if="error" type="error" role="alert" class="notice">{{ error }}</NAlert>
    <NForm @submit.prevent="search">
      <div class="form-grid">
        <NFormItem label="标题包含" :label-props="{ for: 'content-query' }"
          ><NInput
            v-model:value="query"
            :disabled="loading"
            :maxlength="200"
            :input-props="{ id: 'content-query' }"
        /></NFormItem>
        <NFormItem label="作者精确匹配" :label-props="{ for: 'content-author' }"
          ><NInput
            v-model:value="author"
            :disabled="loading"
            :maxlength="500"
            :input-props="{ id: 'content-author' }"
        /></NFormItem>
        <NFormItem label="版块精确匹配" :label-props="{ for: 'content-category' }"
          ><NInput
            v-model:value="category"
            :disabled="loading"
            :maxlength="500"
            :input-props="{ id: 'content-category' }"
        /></NFormItem>
        <NFormItem label="命中任务" :label-props="{ for: 'content-task' }"
          ><select id="content-task" v-model="taskId" class="native-select" :disabled="loading">
            <option value="">全部任务</option>
            <option v-for="task in tasks" :key="task.id" :value="task.id">
              {{ task.name }}{{ task.deleted ? '（已删除）' : '' }}
            </option>
          </select></NFormItem
        >
        <NFormItem label="仅显示有命中的帖子"
          ><NSwitch v-model:value="matchedOnly" :disabled="loading" aria-label="仅显示有命中的帖子"
        /></NFormItem>
      </div>
      <NButton type="primary" attr-type="submit" :loading="loading">筛选内容</NButton>
    </NForm>
    <template v-if="result">
      <div class="panel-heading">
        <p>符合筛选 {{ result.total }} 条 · 当前显示 {{ result.items.length }} 条</p>
        <div class="actions">
          <NButton :disabled="loading || offset === 0" @click="page(-1)">上一页</NButton
          ><NButton
            :disabled="loading || offset + result.items.length >= result.total"
            @click="page(1)"
            >下一页</NButton
          >
        </div>
      </div>
      <p v-if="!result.items.length" class="empty">没有符合筛选的本地帖子。</p>
      <NCard v-for="post in result.items" :key="post.external_post_id" class="record-card">
        <h3>
          <a v-if="post.url" :href="post.url" target="_blank" rel="noopener noreferrer">{{
            post.title
          }}</a
          ><span v-else>{{ post.title }}</span>
        </h3>
        <div class="record-meta">
          <NTag>作者：{{ post.author ?? '未知' }}</NTag
          ><NTag>版块：{{ post.category ?? '未知' }}</NTag>
        </div>
        <p class="muted">
          首次发现：{{ localDate(post.first_seen_at) }} · 发布时间：{{
            post.published_at === null ? 'RSS 未提供' : localDate(post.published_at)
          }}
        </p>
        <p class="post-text">
          {{
            post.summary === null
              ? 'RSS 未提供摘要。'
              : post.summary === ''
                ? '摘要为空。'
                : post.summary
          }}
        </p>
        <NAlert v-if="post.display_truncated" type="info" class="notice"
          >此处显示已截短；规则仍按实际收到的原字段匹配，不代表全文。</NAlert
        >
        <p v-if="!post.hits.length" class="muted">
          没有命中记录：可能为基线帖子、无命中或字段不足，不能据此判断为确定“不命中”。
        </p>
        <div v-for="hit in post.hits" :key="hit.task_id + ':' + hit.version" class="history-item">
          <strong
            >{{ hit.name }} · 规则版本 {{ hit.version
            }}{{ hit.deleted ? '（任务已删除）' : '' }}</strong
          >
          <p>{{ reasonText(hit.reason) }}</p>
          <p class="muted">命中时间：{{ localDate(hit.matched_at) }}</p>
        </div>
      </NCard>
    </template>
  </section>
</template>
