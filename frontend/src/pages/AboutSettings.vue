<script setup lang="ts">
import { computed, ref } from 'vue'
import Icon from '../components/Icon.vue'
import ReadRegion from '../components/ReadRegion.vue'
import { request } from '../store'
import { byteSize as size, stamp } from '../settings'
import { useRemote } from '../history'
import { untilShown } from '../viewReady'
interface About {
  version: string
  build_revision: string
  database_revision: string | null
  supported_websites: { id: string; name: string }[]
  timezone: string
  started_at: number
  environment: { python: string; system: string; container: boolean }
  storage: {
    database_bytes: number
    filesystem_free_bytes: number
    filesystem_total_bytes: number
  }
  checked_at: number
}
const about = useRemote(
  () => request<About>('manage/about'),
  () => [],
  { cacheKey: () => 'about:system' },
)
const repository = 'https://github.com/Aspeternity/seekbell'
const links = [
  {
    label: '使用文档',
    note: '部署、配置与日常使用',
    icon: 'book',
    href: repository + '/blob/main/README.md',
  },
  {
    label: '更新日志',
    note: '每个版本带来的变化',
    icon: 'clock',
    href: repository + '/blob/main/CHANGELOG.md',
  },
  { label: '项目主页', note: '源码仓库与发布版本', icon: 'code', href: repository },
  {
    label: '反馈问题',
    note: '报告问题或提出建议',
    icon: 'message',
    href: repository + '/issues',
  },
]
function duration(seconds: number) {
  const minutes = Math.floor(Math.max(0, seconds) / 60)
  const days = Math.floor(minutes / 1440),
    hours = Math.floor((minutes % 1440) / 60),
    rest = minutes % 60
  if (days) return `${days} 天 ${hours} 小时`
  if (hours) return `${hours} 小时 ${rest} 分钟`
  return minutes ? `${minutes} 分钟` : '不到 1 分钟'
}
function offset(timeZone: string) {
  try {
    const name = new Intl.DateTimeFormat('en-US', { timeZone, timeZoneName: 'longOffset' })
      .formatToParts(new Date())
      .find((part) => part.type === 'timeZoneName')?.value
    return name ? name.replace('GMT', 'UTC').replace(/^UTC$/, 'UTC+00:00') : ''
  } catch {
    return ''
  }
}
const diskUsed = computed(() => {
  const storage = about.data.value?.storage
  if (!storage?.filesystem_total_bytes) return 0
  const used = 1 - storage.filesystem_free_bytes / storage.filesystem_total_bytes
  return Math.min(100, Math.max(0, Math.round(used * 100)))
})
const development = computed(() => about.data.value?.build_revision === 'development')
const copied = ref('')
async function copyRevision() {
  copied.value = ''
  try {
    if (!navigator.clipboard?.writeText) throw new Error()
    await navigator.clipboard.writeText(about.data.value?.build_revision ?? '')
    copied.value = '已复制'
  } catch {
    copied.value = '复制失败，请手动选取'
  }
}
await untilShown(about.ready)
</script>
<template>
  <div class="settings-stack">
    <section class="panel about-card" aria-label="关于 SeekBell">
      <div class="about-hero">
        <span class="brand-icon"><Icon name="bell" :size="30" /><i /></span>
        <div class="about-hero-text">
          <h2>SeekBell<span class="brand-period">.</span></h2>
          <p>留意你关心的。</p>
          <div v-if="about.data.value" class="about-badges">
            <span class="about-version"
              >版本 <strong data-testid="app-version">{{ about.data.value.version }}</strong></span
            >
            <span class="small-badge neutral">{{
              development
                ? '本地开发构建'
                : '正式构建 · ' + about.data.value.build_revision.slice(0, 7)
            }}</span>
          </div>
        </div>
      </div>
      <nav class="about-links" aria-label="项目链接">
        <a
          v-for="link in links"
          :key="link.label"
          class="about-link"
          :href="link.href"
          target="_blank"
          rel="noopener noreferrer"
        >
          <span class="about-link-icon"><Icon :name="link.icon" :size="18" /></span>
          <span class="about-link-text">
            <strong>{{ link.label }}</strong>
            <small>{{ link.note }}</small>
          </span>
          <Icon class="about-link-arrow" name="external" :size="14" />
        </a>
      </nav>
    </section>
    <section class="panel settings-card about-system" aria-labelledby="about-system-title">
      <div class="panel-heading">
        <h2 id="about-system-title">系统信息</h2>
        <span v-if="about.data.value" class="small-note"
          >检查于 {{ stamp(about.data.value.checked_at) }}</span
        >
      </div>
      <div class="form-content">
        <ReadRegion
          :loading="about.loading.value"
          :error="about.error.value"
          :has-data="!!about.data.value"
          :min-height="220"
          @retry="about.reload"
        >
          <div v-if="about.data.value" class="about-body">
            <dl class="about-tiles">
              <div>
                <dt>
                  <span class="about-tile-icon"><Icon name="globe" :size="16" /></span>支持网站
                </dt>
                <dd class="about-chips">
                  <span v-for="site in about.data.value.supported_websites" :key="site.id">{{
                    site.name
                  }}</span>
                </dd>
              </div>
              <div>
                <dt>
                  <span class="about-tile-icon"><Icon name="clock" :size="16" /></span>显示时区
                </dt>
                <dd>
                  {{ about.data.value.timezone }}
                  <small>{{ offset(about.data.value.timezone) || '偏移未知' }}</small>
                </dd>
              </div>
              <div>
                <dt>
                  <span class="about-tile-icon"><Icon name="activity" :size="16" /></span>已运行
                </dt>
                <dd>
                  {{ duration(about.data.value.checked_at - about.data.value.started_at) }}
                  <small>启动于 {{ stamp(about.data.value.started_at) }}</small>
                </dd>
              </div>
              <div>
                <dt>
                  <span class="about-tile-icon"><Icon name="cpu" :size="16" /></span>运行环境
                </dt>
                <dd>
                  Python {{ about.data.value.environment.python }}
                  <small
                    >{{ about.data.value.environment.system }} ·
                    {{ about.data.value.environment.container ? '容器内运行' : '非容器' }}</small
                  >
                </dd>
              </div>
              <div class="about-storage">
                <dt>
                  <span class="about-tile-icon"><Icon name="database" :size="16" /></span>数据存储
                </dt>
                <dd>
                  数据库 {{ size(about.data.value.storage.database_bytes) }}
                  <span
                    class="about-meter"
                    role="meter"
                    aria-label="磁盘已用"
                    :aria-valuenow="diskUsed"
                    aria-valuemin="0"
                    aria-valuemax="100"
                    ><span :style="{ width: diskUsed + '%' }"
                  /></span>
                  <small
                    >磁盘可用 {{ size(about.data.value.storage.filesystem_free_bytes) }} /
                    {{ size(about.data.value.storage.filesystem_total_bytes) }}（已用
                    {{ diskUsed }}%）</small
                  >
                </dd>
              </div>
            </dl>
            <details class="about-build">
              <summary><Icon name="next" :size="14" />构建信息</summary>
              <dl>
                <div>
                  <dt>代码提交</dt>
                  <dd>
                    <code data-testid="build-revision">{{ about.data.value.build_revision }}</code>
                    <button class="text-link" type="button" @click="copyRevision">
                      <Icon name="copy" :size="13" />复制
                    </button>
                    <span v-if="copied" class="small-note" role="status">{{ copied }}</span>
                  </dd>
                </div>
                <div>
                  <dt>数据库结构版本</dt>
                  <dd>
                    <code data-testid="database-revision">{{
                      about.data.value.database_revision ?? '未记录迁移版本'
                    }}</code>
                  </dd>
                </div>
              </dl>
              <p v-if="development" class="small-note">本地开发构建，未固定代码提交版本。</p>
            </details>
          </div>
        </ReadRegion>
      </div>
    </section>
  </div>
</template>
