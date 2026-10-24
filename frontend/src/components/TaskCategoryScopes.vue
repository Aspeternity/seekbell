<script setup lang="ts">
import { computed, nextTick, ref, useId, watch } from 'vue'
import Icon from './Icon.vue'
import type { CategoryScope } from '../model'
import type { InstalledWebsite } from '../websites'
import { websiteName } from '../store'
const props = defineProps<{
  modelValue: Record<string, CategoryScope>
  websites: InstalledWebsite[]
}>()
const emit = defineEmits<{ 'update:modelValue': [value: Record<string, CategoryScope>] }>()
const id = useId()
const editing = ref<string | null>(null)
const query = ref('')
const original = ref<CategoryScope>({ mode: 'all', values: [] })
const remembered = ref<string[]>([])
const site = computed(() => props.websites.find((website) => website.id === editing.value))
const scope = computed<CategoryScope>(() =>
  editing.value ? scopeFor(editing.value) : { mode: 'all', values: [] },
)
function scopeFor(website: string): CategoryScope {
  return props.modelValue[website] || { mode: 'all', values: [] }
}
function choices(website: InstalledWebsite) {
  const options = new Map((website.categoryOptions || []).map((item) => [item.value, item]))
  for (const value of [
    ...scopeFor(website.id).values,
    ...(editing.value === website.id ? original.value.values : []),
  ])
    if (!options.has(value)) options.set(value, { value, label: value + '（已保存原值）' })
  return [...options.values()]
}
const options = computed(() => {
  if (!site.value) return []
  const needle = query.value.trim().toLocaleLowerCase()
  return choices(site.value).filter(
    (item) =>
      item.label.toLocaleLowerCase().includes(needle) ||
      item.value.toLocaleLowerCase().includes(needle),
  )
})
function summary(website: InstalledWebsite) {
  const current = scopeFor(website.id)
  if (current.mode === 'all') return '全部版块'
  if (!current.values.length) return '尚未选择版块'
  const options = choices(website)
  const names = current.values.map(
    (value) => options.find((item) => item.value === value)?.label || value,
  )
  return names.slice(0, 2).join('、') + (names.length > 2 ? ' 等 ' + names.length + ' 个' : '')
}
function update(value: CategoryScope) {
  if (editing.value) emit('update:modelValue', { ...props.modelValue, [editing.value]: value })
}
function begin(website: string) {
  if (editing.value === website) return
  editing.value = website
  const current = scopeFor(website)
  original.value = { mode: current.mode, values: [...current.values] }
  remembered.value = [...current.values]
  query.value = ''
}
function mode(value: 'all' | 'specific') {
  if (value === 'all') {
    remembered.value = [...scope.value.values]
    update({ mode: 'all', values: [] })
  } else update({ mode: 'specific', values: [...remembered.value] })
}
function toggle(value: string) {
  const values = scope.value.values.includes(value)
    ? scope.value.values.filter((item) => item !== value)
    : [...scope.value.values, value]
  remembered.value = values
  update({ mode: 'specific', values })
}
async function close(cancel = false) {
  if (!editing.value) return
  const previous = editing.value
  if (cancel) update({ mode: original.value.mode, values: [...original.value.values] })
  editing.value = null
  await nextTick()
  document.getElementById(id + '-trigger-' + previous)?.focus({ preventScroll: true })
}
watch(
  () => props.websites.map((website) => website.id),
  (ids) => {
    if (editing.value && !ids.includes(editing.value)) editing.value = null
  },
)
</script>
<template>
  <div class="task-category-scopes">
    <div class="category-heading">
      <strong>各网站版块范围</strong>
      <span>独立设置，默认全部版块</span>
    </div>
    <section
      v-for="website in websites"
      :key="website.id"
      class="category-site"
      :aria-label="websiteName(website.id) + '版块范围'"
    >
      <div class="category-site-heading">
        <span class="category-site-mark">{{ websiteName(website.id).slice(0, 1) }}</span>
        <div class="category-site-copy">
          <strong>{{ websiteName(website.id) }}</strong>
          <p
            :class="{
              'category-error':
                scopeFor(website.id).mode === 'specific' && !scopeFor(website.id).values.length,
            }"
          >
            {{ summary(website) }}
          </p>
        </div>
        <button
          :id="id + '-trigger-' + website.id"
          type="button"
          class="button small"
          :aria-label="'修改 ' + websiteName(website.id) + ' 版块范围'"
          :aria-expanded="editing === website.id"
          :aria-controls="id + '-panel-' + website.id"
          @click="begin(website.id)"
        >
          {{ editing === website.id ? '编辑中' : '修改' }}
        </button>
      </div>
      <div
        v-if="editing === website.id"
        :id="id + '-panel-' + website.id"
        class="category-site-editor"
        @keydown.esc.stop.prevent="close(true)"
      >
        <fieldset class="plain-fieldset category-mode">
          <legend class="sr-only">{{ websiteName(website.id) }}版块模式</legend>
          <label>
            <input
              type="radio"
              :name="id + '-mode'"
              :checked="scope.mode === 'all'"
              @change="mode('all')"
            />
            <span>全部版块</span>
          </label>
          <label>
            <input
              type="radio"
              :name="id + '-mode'"
              :checked="scope.mode === 'specific'"
              @change="mode('specific')"
            />
            <span>指定版块</span>
          </label>
        </fieldset>
        <template v-if="scope.mode === 'specific'">
          <label class="category-search">
            <Icon name="search" :size="16" />
            <input
              v-model="query"
              type="search"
              :aria-label="'搜索 ' + websiteName(website.id) + ' 版块'"
              :placeholder="'搜索 ' + websiteName(website.id) + ' 版块'"
            />
          </label>
          <div class="category-list-meta">
            <span aria-live="polite">已选 {{ scope.values.length }} 个</span>
            <span>{{
              website.id === 'nodeseek' ? '站点目录与 RSS 已见版块' : 'RSS 已见版块，可能不完整'
            }}</span>
          </div>
          <div
            class="category-choice-list"
            role="group"
            :aria-label="websiteName(website.id) + '版块选项'"
          >
            <label
              v-for="option in options"
              :key="option.value"
              class="category-choice"
              :class="{ selected: scope.values.includes(option.value) }"
            >
              <input
                type="checkbox"
                :checked="scope.values.includes(option.value)"
                :disabled="scope.values.length >= 64 && !scope.values.includes(option.value)"
                @change="toggle(option.value)"
              />
              <span>{{ option.label }}</span>
            </label>
            <p v-if="!options.length" class="small-note category-empty">
              {{
                choices(website).length
                  ? '没有找到对应版块。'
                  : '尚无版块信息，可先选择全部版块；采集到版块后会出现在这里。'
              }}
            </p>
          </div>
          <p v-if="!scope.values.length" class="category-error" role="alert">
            请至少选择一个版块，或切换到全部版块。
          </p>
          <p v-if="scope.values.length >= 64" class="small-note">每个网站最多选择 64 个版块。</p>
        </template>
        <p v-else class="small-note">不限制该网站 RSS 实际提供的版块，仍受来源覆盖范围限制。</p>
        <div class="category-edit-actions">
          <button type="button" class="button small" @click="close(true)">取消</button>
          <button
            type="button"
            class="button primary small"
            :disabled="scope.mode === 'specific' && !scope.values.length"
            @click="close()"
          >
            完成
          </button>
        </div>
      </div>
    </section>
  </div>
</template>
<style scoped>
.task-category-scopes {
  margin-top: 20px;
}
.category-heading {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 5px 12px;
  margin-bottom: 6px;
}
.category-heading strong {
  font-size: 13px;
  font-weight: 600;
}
.category-heading > span {
  font-size: 11px;
  color: var(--muted);
}
.category-site {
  border-top: 1px solid var(--border);
}
.category-site-heading {
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr) auto;
  gap: 11px;
  align-items: center;
  padding: 14px 0;
}
.category-site-mark {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  background: #f5f6f8;
  color: #66717d;
  font-weight: 600;
}
.category-site-copy {
  min-width: 0;
}
.category-site-copy > strong {
  font-weight: 600;
  font-size: 12px;
}
.category-site-copy > p {
  margin-top: 2px;
  font-size: 11px;
  color: var(--muted);
  overflow-wrap: anywhere;
}
.category-site-editor {
  padding: 0 0 15px 43px;
}
.category-mode {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 12px;
}
.category-mode label {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  min-height: 30px;
}
.category-search {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--border);
  border-radius: 7px;
  padding: 8px 10px;
  color: var(--muted);
}
.category-search:focus-within {
  border-color: #c88964;
  box-shadow: 0 0 0 2px #f7ebe2;
}
.category-search input {
  min-width: 0;
  width: 100%;
  border: 0;
  background: transparent;
  padding: 0;
}
.category-list-meta {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 5px 12px;
  font-size: 11px;
  color: var(--muted);
  margin: 9px 0 6px;
}
.category-choice-list {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 4px 8px;
  max-height: 230px;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 3px;
  scrollbar-gutter: stable;
}
.category-choice {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 7px;
  border: 1px solid transparent;
  border-radius: 6px;
  cursor: pointer;
}
.category-choice.selected {
  background: #fff3e9;
  border-color: #f1dbc9;
}
.category-choice:has(input:focus-visible),
.category-mode label:has(input:focus-visible) {
  outline: 1px solid #c88964;
  outline-offset: 2px;
}
.category-choice input:focus-visible,
.category-mode input:focus-visible {
  outline: none;
}
.category-choice > span {
  overflow-wrap: anywhere;
}
.category-empty {
  grid-column: 1 / -1;
  padding: 8px 0;
}
.category-error,
.category-site-copy > .category-error {
  color: #a54736;
  font-size: 11px;
}
.category-site-editor > .category-error {
  margin-top: 8px;
}
.category-edit-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 12px;
}
@media (max-width: 620px) {
  .category-site-editor {
    padding-left: 0;
  }
  .category-choice-list {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .category-search input {
    font-size: 16px;
  }
}
@media (pointer: coarse) {
  .category-choice,
  .category-mode label {
    min-height: 44px;
  }
}
</style>
