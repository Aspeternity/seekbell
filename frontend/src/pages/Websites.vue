<script setup lang="ts">
import AppSelect from '../components/AppSelect.vue'
import WebsiteHotlistSettings from '../components/WebsiteHotlistSettings.vue'
import WebsiteConnectionTest from '../components/WebsiteConnectionTest.vue'
import { hotlistDraft, hotlistInput, hotlistError } from '../hotlistSettings'
import type { HotlistDraft } from '../hotlistSettings'
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import Icon from '../components/Icon.vue'
import Toggle from '../components/Toggle.vue'
import {
  state,
  runtime,
  saveWebsite,
  notify,
  formatTime,
  confirmAction,
  addWebsite,
  removeWebsite,
} from '../store'
import { websiteCatalog, websiteDefinition } from '../websites'
import type { InstalledWebsite } from '../websites'
const emit = defineEmits<{
  dirty: [value: boolean]
  navigate: [path: string]
}>()
const mutating = ref(false)
const search = ref(''),
  filter = ref('all'),
  catalogSearch = ref('')
const panel = ref<HTMLDialogElement>(),
  mode = ref<'catalog' | 'detail'>('catalog'),
  selectedId = ref('')
const draft = reactive({ interval: 10, hotlist: null as HotlistDraft | null })
const baseline = ref(''),
  error = ref('')
const selected = computed(() => state.websites.find((w) => w.id === selectedId.value))
const definition = computed(() => websiteDefinition(selected.value?.adapterId || ''))
const dirty = computed(() => !!selected.value && JSON.stringify(draft) !== baseline.value)
watch(dirty, (value) => emit('dirty', value))
watch(error, async (value) => {
  if (!value) return
  await nextTick()
  panel.value?.querySelector<HTMLElement>('[role="alert"]')?.scrollIntoView({ block: 'nearest' })
})
const status = (w: InstalledWebsite) =>
  !w.enabled
    ? '已暂停'
    : !runtime.active
      ? '后台未运行'
      : w.health === 'error'
        ? '连接异常'
        : w.health === 'healthy'
          ? '采集正常'
          : '等待首次采集'
const statusClass = (w: InstalledWebsite) =>
  !w.enabled || !runtime.active ? 'neutral' : w.health === 'healthy' ? 'yes' : 'unknown'
const linked = (id: string) => state.tasks.filter((t) => t.websiteIds.includes(id))
const visible = computed(() =>
  state.websites.filter((w) => {
    const info = websiteDefinition(w.adapterId)
    return (
      (info?.name + ' ' + info?.domain).toLowerCase().includes(search.value.trim().toLowerCase()) &&
      (filter.value === 'all' ||
        (filter.value === 'enabled'
          ? w.enabled
          : filter.value === 'paused'
            ? !w.enabled
            : w.enabled && w.health === 'error'))
    )
  }),
)
const available = computed(() =>
  websiteCatalog.filter((w) =>
    (w.name + ' ' + w.description).toLowerCase().includes(catalogSearch.value.trim().toLowerCase()),
  ),
)
async function show() {
  await nextTick()
  panel.value?.showModal()
  document.body.classList.add('website-panel-open')
}
function catalog() {
  mode.value = 'catalog'
  selectedId.value = ''
  catalogSearch.value = ''
  show()
}
function detail(w: InstalledWebsite) {
  selectedId.value = w.id
  mode.value = 'detail'
  draft.interval = w.interval
  draft.hotlist = hotlistDraft(w.hotlist)
  baseline.value = JSON.stringify(draft)
  error.value = ''
  show()
}
function close() {
  panel.value?.close()
  document.body.classList.remove('website-panel-open')
  selectedId.value = ''
  emit('dirty', false)
}
function requestClose() {
  if (dirty.value)
    confirmAction(
      '关闭网站配置？',
      '你有尚未保存的网站配置。关闭后，这些修改将丢失。',
      close,
      '放弃修改并关闭',
      '继续编辑',
    )
  else close()
}
async function install(id: string) {
  if (mutating.value) return
  mutating.value = true
  error.value = ''
  try {
    const w = await addWebsite(id)
    if (w) close()
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    mutating.value = false
  }
}
async function save() {
  if (mutating.value) return
  if (!selected.value) return
  if (
    !Number.isInteger(draft.interval) ||
    draft.interval < (definition.value?.minimumInterval || 10) ||
    draft.interval > 3600
  ) {
    error.value =
      '采集间隔应为 ' + (definition.value?.minimumInterval || 10) + '–3600 之间的整数秒。'
    return
  }
  if (selected.value.hotlist && draft.hotlist) {
    error.value = hotlistError(selected.value.hotlist, draft.hotlist)
    if (error.value) return
  }
  mutating.value = true
  try {
    await saveWebsite(
      selected.value,
      draft.interval,
      selected.value.enabled,
      draft.hotlist ? hotlistInput(draft.hotlist) : undefined,
    )
    baseline.value = JSON.stringify(draft)
    error.value = ''
    notify('网站配置已保存到服务端，将按启停状态采集。')
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    mutating.value = false
  }
}
function toggle(w: InstalledWebsite, enabled: boolean) {
  const apply = async () => {
    if (mutating.value) return
    mutating.value = true
    try {
      await saveWebsite(w, w.interval, enabled)
    } catch (e) {
      notify((e as Error).message)
      return
    } finally {
      mutating.value = false
    }
  }
  if (enabled) apply()
  else
    confirmAction(
      '暂停 ' + websiteDefinition(w.adapterId)?.name + ' 采集？',
      '只影响这个网站的关联任务，其他网站继续运行。恢复时重建当下基线，不补发暂停期间内容。',
      apply,
      '暂停网站',
    )
}
function remove() {
  const w = selected.value
  if (!w) return
  if (linked(w.id).length) {
    notify('请先移除该网站关联的监控任务。')
    return
  }
  confirmAction(
    '移除 ' + definition.value?.name + '？',
    '移除该网站的采集配置，已有内容与投递历史保留。之后可以从内置网站库重新添加。',
    async () => {
      if (mutating.value) return
      mutating.value = true
      try {
        if (await removeWebsite(w.id)) close()
      } catch (e) {
        error.value = (e as Error).message
      } finally {
        mutating.value = false
      }
    },
    '确认移除',
  )
}
function tasks() {
  const navigate = () => {
    close()
    emit('navigate', '/tasks')
  }
  if (dirty.value)
    confirmAction(
      '离开网站配置？',
      '未保存的网站配置将丢失。',
      navigate,
      '放弃修改并离开',
      '继续编辑',
    )
  else navigate()
}
onBeforeUnmount(() => document.body.classList.remove('website-panel-open'))
</script>
<template>
  <section class="page-heading">
    <div>
      <p class="eyebrow">YOUR SOURCES, YOUR WORLD</p>
      <h1 tabindex="-1">监控网站</h1>
      <p class="subtitle">把关注的网站放在一起，让每一份信息各有来处。</p>
    </div>
    <button class="button primary" @click="catalog"><Icon name="plus" :size="18" />添加网站</button>
  </section>
  <div class="website-summary">
    <div>
      <span class="icon-tile orange"><Icon name="globe" /></span
      ><span
        ><strong>{{ state.websites.length }}</strong> 个已添加网站</span
      >
    </div>
    <span
      ><i class="status-dot green-dot" />{{
        state.websites.filter((w) => w.enabled).length
      }}
      个已启用</span
    >
    <span
      ><i class="status-dot" />{{ state.websites.filter((w) => !w.enabled).length }} 个已暂停</span
    >
    <p>独立配置 · 按需添加</p>
  </div>
  <section v-if="!state.websites.length" class="panel website-empty">
    <div class="empty-orbit" aria-hidden="true">
      <span><Icon name="globe" :size="36" /></span><i /><b />
    </div>
    <p class="eyebrow">START WITH WHAT MATTERS</p>
    <h2>从第一个关心的网站开始</h2>
    <p>SeekBell 不会默认添加任何网站。<br />从内置网站库选择需要的来源，再为它创建监控任务。</p>
    <button class="button primary" @click="catalog">
      <Icon name="plus" :size="18" />添加第一个网站
    </button>
    <div class="website-onboarding">
      <span><b>01</b>选择网站</span><Icon name="arrow" :size="15" /><span><b>02</b>配置采集</span
      ><Icon name="arrow" :size="15" /><span><b>03</b>创建任务</span>
    </div>
  </section>
  <template v-else>
    <div class="filter-toolbar free-toolbar website-toolbar">
      <label class="search-input"
        ><Icon name="search" :size="17" /><input
          v-model="search"
          aria-label="搜索已添加网站"
          placeholder="搜索网站名称或域名…"
      /></label>
      <AppSelect
        v-model="filter"
        class="text-input"
        aria-label="筛选网站状态"
        :options="[
          { value: 'all', label: '全部状态' },
          { value: 'enabled', label: '已启用' },
          { value: 'paused', label: '已暂停' },
          { value: 'error', label: '连接异常' },
        ]"
      />
      <span class="muted">{{ visible.length }} 个网站</span>
    </div>
    <div class="website-grid">
      <article v-for="w in visible" :key="w.id" class="panel website-card">
        <button
          class="website-card-main"
          :aria-label="'配置 ' + websiteDefinition(w.adapterId)?.name"
          @click="detail(w)"
        >
          <div class="website-card-top">
            <span class="source-logo large"
              >{{ websiteDefinition(w.adapterId)?.mark }}<span>›</span></span
            ><span class="result-pill" :class="statusClass(w)"
              ><i class="status-dot" />{{ status(w) }}</span
            >
          </div>
          <h2>{{ websiteDefinition(w.adapterId)?.name }}</h2>
          <p class="website-domain">{{ websiteDefinition(w.adapterId)?.domain }}</p>
          <p class="website-description">{{ websiteDefinition(w.adapterId)?.description }}</p>
          <div class="chip-line">
            <span class="plain-chip">{{ websiteDefinition(w.adapterId)?.sourceLabel }}</span
            ><span class="plain-chip">内置适配</span>
          </div>
          <dl class="website-card-facts">
            <div>
              <dt>采集间隔</dt>
              <dd>{{ w.interval }}<small> 秒</small></dd>
            </div>
            <div>
              <dt>关联任务</dt>
              <dd>{{ linked(w.id).length }}<small> 个</small></dd>
            </div>
          </dl>
          <p class="website-last">
            <Icon name="clock" :size="14" />{{
              w.lastSuccess ? '最近成功 ' + formatTime(w.lastSuccess) : '尚无采集记录'
            }}
          </p>
        </button>
        <div class="website-card-footer">
          <label
            ><Toggle
              :model-value="w.enabled"
              :label="websiteDefinition(w.adapterId)?.name + ' 采集启用状态'"
              @update:model-value="(value) => toggle(w, value)"
            /><span>{{ w.enabled ? '已启用' : '已暂停' }}</span></label
          ><button
            class="text-link"
            :aria-label="'查看 ' + websiteDefinition(w.adapterId)?.name + ' 配置'"
            @click="detail(w)"
          >
            查看配置<Icon name="arrow" :size="15" />
          </button>
        </div>
      </article>
      <button v-if="!search && filter === 'all'" class="website-add-card" @click="catalog">
        <span class="add-round"><Icon name="plus" :size="25" /></span><strong>添加监控网站</strong
        ><span>从内置网站库选择新的关注</span>
      </button>
    </div>
    <div v-if="!visible.length" class="panel empty-state">
      <Icon name="search" :size="28" />
      <h3>没有匹配的网站</h3>
      <p>换一个关键词，或查看全部状态。</p>
      <button class="button" @click="((search = ''), (filter = 'all'))">清除筛选</button>
    </div>
  </template>
  <div class="website-bottom-note">
    <Icon name="shield" :size="19" />
    <p>
      每个网站独立采集，同一网站下的任务共享来源。<br /><span
        >当前可添加 NodeSeek 和 LINUX DO；各网站的能力与来源限制可在配置中查看。</span
      >
    </p>
  </div>

  <dialog
    ref="panel"
    class="website-drawer"
    :class="{ 'website-catalog-modal': mode === 'catalog' }"
    :aria-label="mode === 'catalog' ? '添加内置网站' : (definition?.name || '') + ' 网站配置'"
    @cancel.prevent="requestClose"
    @click="
      (event) => {
        if (event.target === panel) requestClose()
      }
    "
  >
    <div class="website-drawer-shell">
      <header class="website-drawer-header">
        <div>
          <p class="eyebrow">
            {{ mode === 'catalog' ? 'BUILT FOR SEEKBELL' : 'WEBSITE SETTINGS' }}
          </p>
          <h2>{{ mode === 'catalog' ? '添加内置网站' : definition?.name }}</h2>
        </div>
        <button class="icon-button" aria-label="关闭网站面板" @click="requestClose">
          <Icon name="close" :size="21" />
        </button>
      </header>
      <p v-if="error && mode === 'catalog'" class="form-errors" role="alert">{{ error }}</p>
      <div v-if="mode === 'catalog'" class="website-drawer-body">
        <p class="drawer-intro">选择你真正关注的网站。添加后可独立调整采集频率，随时暂停或移除。</p>
        <label class="search-input catalog-search"
          ><Icon name="search" :size="17" /><input
            v-model="catalogSearch"
            aria-label="搜索内置网站"
            placeholder="搜索内置网站…"
        /></label>
        <div class="catalog-caption">
          <span>可用网站</span><span>{{ available.length }} 个</span>
        </div>
        <div class="website-catalog-grid">
          <article v-for="item in available" :key="item.id" class="catalog-card">
            <div class="catalog-identity">
              <span class="source-logo">{{ item.mark }}<span>›</span></span>
              <div>
                <h3>{{ item.name }}</h3>
                <p>{{ item.domain }}</p>
              </div>
              <span class="small-badge neutral">内置</span>
            </div>
            <p>{{ item.description }}</p>
            <div class="chip-line">
              <span v-for="cap in item.capabilities" :key="cap" class="plain-chip">{{ cap }}</span>
            </div>
            <div class="catalog-action">
              <span><Icon name="rss" :size="15" />{{ item.sourceLabel }}</span
              ><button
                class="button primary"
                :disabled="mutating || state.websites.some((w) => w.adapterId === item.id)"
                @click="install(item.id)"
              >
                {{
                  state.websites.some((w) => w.adapterId === item.id)
                    ? '已添加'
                    : '添加 ' + item.name
                }}
              </button>
            </div>
          </article>
        </div>
        <div v-if="!available.length" class="empty-state">
          <Icon name="search" :size="26" />
          <h3>没有找到内置网站</h3>
          <p>当前仅提供已完成适配的网站。</p>
          <button class="button" @click="catalogSearch = ''">清除搜索</button>
        </div>
        <div class="catalog-future">
          <Icon name="layers" :size="22" />
          <div>
            <strong>让更多关注，陆续加入</strong>
            <p>网站库会随适配能力扩展。这里不接受任意网址，也不会把尚未支持的网站列为可用。</p>
          </div>
        </div>
      </div>
      <template v-else-if="selected && definition">
        <div class="website-drawer-body">
          <p v-if="error" class="form-errors" role="alert">{{ error }}</p>
          <div class="drawer-website-status">
            <div>
              <span class="result-pill" :class="statusClass(selected)"
                ><i class="status-dot" />{{ status(selected) }}</span
              >
              <p>{{ definition.description }}</p>
            </div>
            <Toggle
              :model-value="selected.enabled"
              :label="definition.name + ' 采集启用状态'"
              @update:model-value="(value) => toggle(selected!, value)"
            />
          </div>
          <section class="drawer-section">
            <h3>网站与来源</h3>
            <div class="website-source">
              <Icon name="rss" :size="20" />
              <div>
                <strong>{{ definition.sourceLabel }}</strong>
                <p>{{ definition.sourceUrl }}</p>
              </div>
            </div>
            <div class="chip-line">
              <span v-for="cap in definition.capabilities" :key="cap" class="plain-chip">{{
                cap
              }}</span>
            </div>
            <p class="field-help">{{ definition.limits }}</p>
          </section>
          <section class="drawer-section">
            <h3>采集配置</h3>
            <label class="field-label" for="source-interval">共享采集间隔</label>
            <div class="unit-input">
              <input
                id="source-interval"
                v-model.number="draft.interval"
                :disabled="mutating"
                class="text-input"
                type="number"
                :min="definition.minimumInterval"
                max="3600"
                step="1"
                :aria-invalid="!!error"
              /><span>秒</span>
            </div>
            <p class="field-help">
              仅作用于 {{ definition.name }}，该网站下的全部任务共享此频率。{{
                definition.defaultInterval
              }}
              秒为候选默认值，不代表官方限频保证。
            </p>
            <div class="info-note">
              <Icon name="shield" :size="17" />
              <p>
                启用后由服务端采集官方
                RSS。首次启用或暂停后恢复时只建立基线，不补发历史；关闭浏览器仍会运行。
              </p>
            </div>
          </section>
          <WebsiteHotlistSettings
            v-if="selected.hotlist && draft.hotlist"
            v-model="draft.hotlist"
            :config="selected.hotlist"
            :disabled="mutating"
          />
          <WebsiteConnectionTest
            :key="selected.id"
            :website-id="selected.id"
            :name="definition.name"
          />
          <section class="drawer-section">
            <div class="drawer-section-title">
              <h3>
                关联任务 <span class="count-badge">{{ linked(selected.id).length }}</span>
              </h3>
              <button class="text-link" @click="tasks">
                管理任务<Icon name="arrow" :size="14" />
              </button>
            </div>
            <p v-if="!linked(selected.id).length" class="field-help">
              还没有关联任务。添加任务时，选择这个网站作为监控来源。
            </p>
            <div v-for="t in linked(selected.id)" :key="t.id" class="website-linked-task">
              <Icon :name="t.icon" :size="16" /><span>{{ t.name }}</span
              ><span class="muted">{{ t.enabled ? '已启用' : '已暂停' }}</span>
            </div>
          </section>
          <section class="website-remove">
            <div>
              <h3>移除网站</h3>
              <p>
                {{
                  linked(selected.id).length
                    ? '请先移除关联任务，再移除网站。历史记录会保留。'
                    : '已有内容与投递历史保留，之后可以重新添加。'
                }}
              </p>
            </div>
            <button
              class="button danger-text"
              :disabled="!!linked(selected.id).length"
              @click="remove"
            >
              移除网站
            </button>
          </section>
        </div>
        <footer class="website-drawer-footer">
          <span>{{ dirty ? '有未保存的修改' : '设置已保存' }}</span
          ><button class="button" @click="requestClose">关闭</button
          ><button class="button primary" :disabled="mutating" @click="save">
            <Icon name="check" :size="16" />保存设置
          </button>
        </footer>
      </template>
    </div>
  </dialog>
</template>
