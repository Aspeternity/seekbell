<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import AppSelect from './AppSelect.vue'
import Icon from './Icon.vue'
import ReadRegion from './ReadRegion.vue'
import { request, formatTime } from '../store'
import { useRemote } from '../history'
import { readSessionRevision } from '../readCache'
import type { HotlistData, OverviewPreferences } from '../overviewPreferences'
const emit = defineEmits<{ navigate: [path: string] }>()
const catalog = useRemote(
  () => request<OverviewPreferences>('manage/overview-preferences'),
  () => [],
  { cacheKey: () => 'overview-preferences' },
)
const site = ref(''),
  period = ref(''),
  expanded = ref(false),
  choiceError = ref('')
const source = computed(() =>
  catalog.data.value?.sources.find((row) => row.website_id === site.value),
)
const periods = ref<Record<string, string>>({})
let selectionRevision = 1,
  active = true,
  saving = false
let desired: { website_id: string; period: string } | undefined
let timer: ReturnType<typeof setTimeout> | undefined
watch(catalog.data, (value) => {
  if (!value) return
  selectionRevision = value.selection.revision
  periods.value = { ...value.selection.periods }
  if (!value.sources.some((row) => row.website_id === site.value)) {
    site.value =
      value.sources.find((row) => row.website_id === value.selection.website_id)?.website_id ||
      value.sources[0]?.website_id ||
      ''
    period.value =
      value.sources
        .find((row) => row.website_id === site.value)
        ?.periods.find((row) => row.id === periods.value[site.value])?.id ||
      source.value?.default_period ||
      ''
  }
})
const cacheKey = (website: string, value: string) => 'hotlist:' + website + ':' + value
const read = (website: string, value: string) =>
  request<HotlistData>(
    'manage/hotlists/' + encodeURIComponent(website) + '?period=' + encodeURIComponent(value),
  )
const remote = useRemote(
  () => (source.value ? read(site.value, period.value) : Promise.resolve(null)),
  () => [site.value, period.value],
  { cacheKey: () => (source.value ? cacheKey(site.value, period.value) : undefined) },
)
const snapshot = computed(() =>
  remote.data.value?.website_id === site.value && remote.data.value?.period === period.value
    ? remote.data.value
    : null,
)
// An empty successful list is also a snapshot; routine reads must stay silent.
const hasSnapshot = computed(() => snapshot.value?.fetched_at != null)
const showWaiting = computed(
  () =>
    snapshot.value?.status === 'waiting' &&
    (!hasSnapshot.value ||
      !['source_busy', 'source_cooldown', 'collection_priority'].includes(
        snapshot.value.error_code || '',
      )),
)
const stamp = (at: number | null) =>
  at === null ? '来源未提供' : formatTime(new Date(at * 1000).toISOString())
const selectedLabel = computed(
  () => source.value?.periods.find((row) => row.id === period.value)?.label || '',
)
const items = computed(() => snapshot.value?.items.slice(0, expanded.value ? 10 : 5) || [])
function schedule() {
  clearTimeout(timer)
  const data = snapshot.value
  if (!active || !source.value || document.hidden || !data || remote.loading.value) return
  timer = setTimeout(
    () => remote.reload(),
    remote.error.value
      ? 15000
      : Math.max(1000, Math.min(86400000, data.next_attempt_at * 1000 - Date.now() + 100)),
  )
}
// Short status reads stay within SeekBell; the server owns upstream cadence.
watch([snapshot, () => remote.error.value], schedule)
function visibility() {
  if (!document.hidden && source.value) remote.reload()
  else clearTimeout(timer)
}
document.addEventListener('visibilitychange', visibility)
async function persistChoice() {
  if (saving || !active) return
  saving = true
  const session = readSessionRevision.value
  try {
    while (desired && active && session === readSessionRevision.value) {
      const next = desired
      desired = undefined
      try {
        const result = await request<{ revision: number }>('manage/hotlists/selection', 'PUT', {
          ...next,
          revision: selectionRevision,
        })
        if (active && session === readSessionRevision.value) {
          selectionRevision = result.revision
          choiceError.value = ''
        }
      } catch {
        if (active && session === readSessionRevision.value) {
          choiceError.value = '当前选择尚未保存，可重试。'
          const latest = await request<OverviewPreferences>('manage/overview-preferences')
          if (active) selectionRevision = latest.selection.revision
        }
      }
    }
  } catch {
    if (active) choiceError.value = '当前选择尚未保存，可重试。'
  } finally {
    saving = false
  }
}
function saveCurrent() {
  desired = { website_id: site.value, period: period.value }
  void persistChoice()
}
function selectSite(value: string) {
  if (value === site.value) return
  site.value = value
  const current = source.value!
  period.value =
    current.periods.find((row) => row.id === periods.value[value])?.id || current.default_period
  expanded.value = false
  saveCurrent()
}
function selectPeriod(value: string) {
  if (value === period.value) return
  period.value = value
  periods.value = { ...periods.value, [site.value]: value }
  expanded.value = false
  saveCurrent()
}
onBeforeUnmount(() => {
  active = false
  desired = undefined
  clearTimeout(timer)
  document.removeEventListener('visibilitychange', visibility)
})
</script>
<template>
  <section class="panel hotlist-panel" aria-label="社区热榜" data-overview-module="hotlist">
    <div class="panel-heading">
      <div>
        <h2>社区热榜</h2>
        <p>看看社区正在聊什么</p>
      </div>
      <Icon name="spark" :size="20" />
    </div>
    <ReadRegion
      :loading="catalog.loading.value && !catalog.data.value"
      :error="catalog.error.value"
      :has-data="!!catalog.data.value"
      :min-height="170"
      @retry="catalog.reload"
    >
      <template v-if="catalog.data.value">
        <div v-if="!catalog.data.value.sources.length" class="empty-state">
          <Icon name="globe" :size="28" />
          <h3>还没有可展示热榜的网站</h3>
          <p>添加支持热榜的内置网站后，在这里查看社区动态。</p>
          <button class="button" @click="emit('navigate', '/websites')">管理网站</button>
        </div>
        <template v-else>
          <nav
            v-if="catalog.data.value.sources.length > 1 && catalog.data.value.sources.length <= 4"
            class="hotlist-sites"
            aria-label="热榜网站"
          >
            <button
              v-for="item in catalog.data.value.sources"
              :key="item.website_id"
              class="hotlist-site"
              :class="{ active: site === item.website_id }"
              :aria-pressed="site === item.website_id"
              @click="selectSite(item.website_id)"
            >
              {{ item.name }}
            </button>
          </nav>
          <div v-else class="hotlist-sites">
            <AppSelect
              v-if="catalog.data.value.sources.length > 4"
              :model-value="site"
              :options="
                catalog.data.value.sources.map((row) => ({
                  value: row.website_id,
                  label: row.name,
                }))
              "
              aria-label="选择热榜网站"
              @update:model-value="selectSite"
            />
            <span v-else class="hotlist-single-site"
              ><span class="hotlist-site-mark">{{ source?.name.slice(0, 1) }}</span
              >{{ source?.name }}</span
            >
          </div>
          <div class="hotlist-toolbar">
            <div
              v-if="source && source.periods.length > 1"
              class="segmented compact"
              role="group"
              aria-label="热榜周期"
            >
              <button
                v-for="item in source.periods"
                :key="item.id"
                :class="{ active: period === item.id }"
                :aria-pressed="period === item.id"
                @click="selectPeriod(item.id)"
              >
                {{ item.label }}
              </button>
            </div>
            <span v-else>{{ selectedLabel }}</span>
            <span v-if="snapshot?.source_updated_at" class="small-note"
              >来源更新 · {{ stamp(snapshot.source_updated_at) }}</span
            >
            <span v-else-if="snapshot?.fetched_at" class="small-note"
              >获取于 · {{ stamp(snapshot.fetched_at) }}</span
            >
          </div>
          <ReadRegion
            :loading="remote.loading.value && !hasSnapshot"
            :error="remote.error.value"
            :has-data="!!snapshot"
            :min-height="210"
            @retry="remote.reload"
          >
            <template v-if="snapshot">
              <p v-if="showWaiting" class="small-note hotlist-updating" role="status">
                <span>{{
                  snapshot.error_code === 'collection_priority'
                    ? '优先完成新帖采集，随后更新榜单。'
                    : snapshot.error_code === 'access_challenge'
                      ? '本站请求遇到 Cloudflare 验证，本次榜单更新已延后。'
                      : snapshot.error_code === 'http_429'
                        ? '本站请求受限（429），本次榜单更新已延后。'
                        : snapshot.error_code === 'http_403'
                          ? '本站来源拒绝访问，本次榜单更新已延后。'
                          : '正在等待同站请求间隔，稍后自动重试。'
                }}</span>
                <span>预计 {{ stamp(snapshot.next_attempt_at) }} 后重试。</span>
              </p>
              <p
                v-else-if="snapshot.status === 'stale' || snapshot.status === 'unavailable'"
                class="info-note"
                role="status"
              >
                {{
                  snapshot.status === 'stale'
                    ? '更新失败，当前显示上次榜单。'
                    : '暂时无法获取榜单，请稍后重试。'
                }}
                <span v-if="snapshot.error_code === 'access_challenge'">
                  来源要求 Cloudflare 验证，暂时无法自动更新，稍后重试。
                </span>
                <span v-else-if="snapshot.error_code === 'http_403'">
                  来源拒绝自动访问（403），正在退避。
                </span>
                <span v-else-if="snapshot.error_code === 'http_429'"
                  >来源请求受限（429），正在等待允许重试。</span
                >
                <span>预计 {{ stamp(snapshot.next_attempt_at) }} 后重试。</span>
                <span v-if="snapshot.fetched_at"
                  >上次成功获取：{{ stamp(snapshot.fetched_at) }}。</span
                >
                <button class="text-link" :disabled="remote.loading.value" @click="remote.reload">
                  重试
                </button>
              </p>
              <ol v-if="items.length" class="hotlist-list">
                <li v-for="item in items" :key="item.id">
                  <a class="hotlist-row" :href="item.url" target="_blank" rel="noopener noreferrer">
                    <span class="hotlist-rank" :class="{ leading: item.rank <= 3 }">{{
                      String(item.rank).padStart(2, '0')
                    }}</span>
                    <div class="hotlist-copy">
                      <span class="hotlist-title" :title="item.title">{{ item.title }}</span>
                      <p>
                        <span v-if="item.category">{{ item.category }}</span
                        ><span v-if="item.author">{{ item.author }}</span
                        ><span v-if="item.comments !== null"
                          >{{ item.comments.toLocaleString() }} 条评论</span
                        >
                      </p>
                    </div>
                  </a>
                </li>
              </ol>
              <div v-else-if="hasSnapshot" class="empty-state">
                <p>当前榜单还没有帖子。</p>
              </div>
            </template>
          </ReadRegion>
          <div class="hotlist-footer">
            <a v-if="source" :href="source.provider_url" target="_blank" rel="noopener noreferrer"
              >来源：{{ source.provider }} · {{ selectedLabel }}</a
            ><button
              v-if="snapshot && snapshot.items.length > 5"
              class="text-link hotlist-expand"
              :aria-expanded="expanded"
              @click="expanded = !expanded"
            >
              {{ expanded ? '收起' : '展开更多' }}<Icon name="down" :size="14" />
            </button>
          </div>
          <p v-if="choiceError" class="small-note" role="status">
            {{ choiceError }} <button class="text-link" @click="saveCurrent">重试保存选择</button>
          </p>
        </template>
      </template>
    </ReadRegion>
  </section>
</template>
<style scoped>
.hotlist-sites {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 0 22px 14px;
  border-bottom: 1px solid #e9ebee;
}
.hotlist-site {
  border: 0;
  background: transparent;
  border-radius: 6px;
  padding: 7px 12px;
  color: #6f7885;
  font: inherit;
}
.hotlist-site.active {
  color: #b75e32;
  background: #f9ebe2;
}
.hotlist-single-site {
  display: flex;
  align-items: center;
  gap: 9px;
  font-weight: 600;
}
.hotlist-site-mark {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: 6px;
  background: #f9ebe2;
  color: #b75e32;
  font-size: 13px;
}
.hotlist-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding: 16px 22px 10px;
}
.hotlist-list {
  list-style: none;
  padding: 0 22px;
  margin: 0;
}
.hotlist-updating {
  padding: 0 22px;
}
.hotlist-row {
  color: inherit;
  text-decoration: none;
  display: flex;
  gap: 14px;
  padding: 16px 0;
  border-bottom: 1px solid #f0f1f3;
}
.hotlist-row:hover {
  background: #fafbfc;
}
.hotlist-row:focus-visible {
  outline: 2px solid #b75e32;
  outline-offset: -2px;
}
.hotlist-rank {
  min-width: 23px;
  color: #8b929c;
  font-variant-numeric: tabular-nums;
}
.hotlist-rank.leading {
  color: #b75e32;
}
.hotlist-copy {
  min-width: 0;
  flex: 1;
}
.hotlist-title {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  overflow-wrap: anywhere;
  color: #292e35;
  text-decoration: none;
}
.hotlist-row:hover .hotlist-title {
  color: #b75e32;
}
.hotlist-copy p {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  color: #6f7885;
  font-size: 12px;
  margin: 6px 0 0;
}
.hotlist-copy p:empty {
  display: none;
}
.hotlist-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding: 16px 22px;
}
.hotlist-expand[aria-expanded='true'] svg {
  transform: rotate(180deg);
}
.hotlist-footer > a {
  color: #6f7885;
  text-decoration: none;
  font-size: 12px;
  overflow-wrap: anywhere;
}
.hotlist-panel > .read-region {
  border-radius: 0 0 12px 12px;
}
@media (max-width: 600px) {
  .hotlist-toolbar,
  .hotlist-footer {
    padding: 14px 16px;
  }
  .hotlist-sites {
    padding: 0 16px 12px;
  }
  .hotlist-list {
    padding: 0 16px;
  }
  .hotlist-updating {
    padding: 0 16px;
  }
  .hotlist-row {
    gap: 10px;
  }
  .hotlist-copy p {
    gap: 8px;
  }
}
</style>
