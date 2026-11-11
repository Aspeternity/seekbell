import { expect, test, type Page } from '@playwright/test'

const credentials = { username: 'operations_admin', password: 'Synthetic-Operations-2026' }
const now = Math.floor(Date.now() / 1000)
const guide = (summary: string, handling: string, verify: string | null) => ({
  stage: 'fetch',
  summary,
  causes: ['论坛暂时无法访问或响应缓慢'],
  steps: ['在浏览器确认论坛能否打开'],
  handling,
  verify,
  known: true,
})
const node = (label: string, tone: string, detail: string | null = null) => ({
  state: label,
  tone,
  label,
  detail,
  at: null,
})
const problem = (fields: Record<string, unknown>) => ({
  kind: 'source',
  stage: 'fetch',
  since: now - 720,
  hint: null,
  next_attempt_at: null,
  failures: null,
  guide: guide('连接超时', 'auto_retry', 'rss_test'),
  ...fields,
})
const busy = {
  checked_at: now,
  runtime: { active: true, status: 'running', code: null },
  problems: [
    problem({
      key: 'delivery:a',
      kind: 'delivery',
      stage: 'config',
      event_id: 'event-action',
      label: '自动通知：合成 Webhook',
      code: 'target_credentials_invalid',
      summary: '目标配置无法解密或已失效',
      status: 'action',
      hint: '修改目标配置后，下次发送成功时恢复',
    }),
    problem({
      key: 'source:nodeseek-rss',
      event_id: 'event-retry',
      label: 'NodeSeek 官方 RSS',
      code: 'timeout',
      summary: '连接超时',
      status: 'auto_retry',
      failures: 5,
      next_attempt_at: now + 180,
    }),
    problem({
      key: 'delivery:b',
      kind: 'delivery',
      stage: 'send',
      event_id: null,
      label: '自动通知：合成 Bark',
      code: 'bark_rejected',
      summary: '通知服务拒绝了请求',
      status: 'verifying',
      hint: '目标测试已通过，下次真实发送成功后恢复',
    }),
  ],
  sources: [
    {
      website_id: 'nodeseek',
      source_id: 'nodeseek-rss',
      name: 'NodeSeek',
      enabled: true,
      schedule: node('正常', 'ok', '已启用'),
      fetch: node('失败', 'fail', 'timeout'),
      parse: node('无新输入', 'none'),
      latest: node('无新输入', 'none'),
      last_success_at: now - 780,
      next_attempt_at: now + 180,
      gap_at: null,
    },
    {
      website_id: 'linuxdo',
      source_id: 'linuxdo-rss',
      name: 'LINUX DO',
      enabled: true,
      schedule: node('正常', 'ok', '已启用'),
      fetch: node('正常', 'ok'),
      parse: node('正常', 'ok', '30 条'),
      latest: node('完成', 'ok', '新帖 3 · 命中 2 · 入队 2'),
      last_success_at: now - 40,
      next_attempt_at: now + 20,
      gap_at: now - 3600,
    },
  ],
  targets: [
    {
      id: 'a',
      name: '合成 Webhook',
      kind: 'webhook',
      status: 'enabled',
      queue: { pending: 0, retry: 2, earliest_at: now + 300 },
      sending: 0,
      expired_leases: 0,
      uncertain: 1,
      last: { result: 'permanent_error', code: 'target_credentials_invalid', at: now - 700 },
    },
    {
      id: 'c',
      name: '合成 暂停目标',
      kind: 'bark',
      status: 'paused',
      queue: { pending: 0, retry: 0, earliest_at: null },
      sending: 0,
      expired_leases: 0,
      uncertain: 0,
      last: null,
    },
  ],
  hotlists: [
    {
      website_id: 'linuxdo',
      name: 'LINUX DO',
      lists: [
        {
          ...node('刷新失败，旧数据仍可看', 'warn', 'http_429'),
          period: 'daily',
          period_label: '每日',
        },
        { ...node('正常', 'ok'), period: 'hot', period_label: '热门' },
      ],
    },
  ],
  services: [
    { id: 'collection', name: '采集', state: 'running', last_loop_at: now - 2 },
    {
      id: 'delivery',
      name: '投递',
      state: 'stopped_with',
      last_loop_at: null,
      stopped_with: '采集',
    },
    { id: 'retention', name: '历史清理', state: 'running', last_loop_at: now - 1 },
    { id: 'alerts', name: '系统告警', state: 'running', last_loop_at: now - 1 },
  ],
  alerts: { enabled: true, ready_targets: 1 },
}
const clear = { ...busy, problems: [], alerts: { enabled: false, ready_targets: 0 } }
const rows = {
  total: 1,
  page: 1,
  page_size: 20,
  items: [
    {
      id: 'event-history',
      kind: 'source',
      label: 'LINUX DO 官方 RSS',
      code: 'http_429',
      summary: '请求受限（429）',
      status: 'recovered',
      started_at: now - 7200,
      ended_at: now - 6000,
      alerts: { success: 1 },
    },
  ],
}
const detail = {
  id: 'event-retry',
  kind: 'source',
  label: 'NodeSeek 官方 RSS',
  status: 'ongoing',
  handling: 'auto_retry',
  hint: null,
  next_attempt_at: now + 180,
  first_code: 'timeout',
  code: 'timeout',
  started_at: now - 720,
  ended_at: null,
  failures: 5,
  guide: guide('连接超时', 'auto_retry', 'rss_test'),
  recent: [
    { at: now - 60, tone: 'fail', label: '失败', text: 'timeout' },
    { at: now - 780, tone: 'ok', label: '成功', text: '30 条 · 新帖 1 · 命中 0' },
  ],
  alerts: [
    {
      phase: 'fault',
      target_name: '合成 Telegram',
      kind: 'telegram',
      result: 'success',
      error_code: null,
      finished_at: now - 715,
    },
  ],
  verify: { kind: 'rss_test', website_id: 'nodeseek' },
  crash: null,
}

async function enter(page: Page, status: unknown) {
  let current = status
  const unexpected: string[] = []
  await page.route('**/*', (route) => {
    const url = new URL(route.request().url())
    if (url.hostname !== '127.0.0.1') unexpected.push(url.href)
    return url.hostname === '127.0.0.1' ? route.continue() : route.abort()
  })
  const reads = { status: 0, problems: [] as URL[] }
  await page.route('**/api/manage/operations/status', (route) => {
    reads.status++
    return route.fulfill({ json: current })
  })
  await page.route('**/api/manage/operations/problems?*', (route) => {
    reads.problems.push(new URL(route.request().url()))
    return route.fulfill({ json: rows })
  })
  await page.route('**/api/manage/operations/problems/event-*', (route) =>
    route.fulfill({ json: detail }),
  )
  await page.goto('/')
  const initialized = (await (await page.request.get('/api/auth/status')).json()).initialized
  await page.getByLabel('管理员用户名').fill(credentials.username)
  await page
    .getByLabel(initialized ? '密码' : '设置密码', { exact: true })
    .fill(credentials.password)
  if (!initialized) await page.getByLabel('确认密码', { exact: true }).fill(credentials.password)
  await page
    .getByRole('button', { name: initialized ? '登录工作空间' : '创建管理员并进入' })
    .click()
  await expect(page.locator('.sidebar')).toBeAttached()
  await page.evaluate(() => (location.hash = '/operations/status'))
  await expect(page.getByRole('heading', { name: '运行中心', exact: true })).toBeVisible()
  return { reads, unexpected, show: (next: unknown) => (current = next) }
}

test('operations center explains problems, stays calm when healthy and keeps old addresses', async ({
  page,
}, info) => {
  const { reads, unexpected, show } = await enter(page, busy)
  const problems = page.getByRole('region', { name: /当前问题/ })
  const cards = problems.locator('.ops-problem')
  await expect(cards).toHaveCount(3)
  await expect(cards.nth(0)).toContainText('需要处理')
  await expect(cards.nth(0)).toContainText('修改目标配置后，下次发送成功时恢复')
  await expect(cards.nth(1)).toContainText('自动重试中')
  await expect(cards.nth(1)).toContainText('连续失败 5 次')
  await expect(cards.nth(2)).toContainText('等待验证')

  const nodeseek = page.locator('.ops-row', { hasText: 'NodeSeek' })
  await expect(nodeseek.locator('.ops-step.blocked')).toHaveCount(1)
  await expect(nodeseek.locator('.ops-step.blocked')).toContainText('timeout')
  // The overview counts what needs attention before any section is read.
  const overview = page.getByRole('region', { name: '3 个问题待处理' })
  await expect(overview.locator('.ops-tiles > div')).toHaveCount(4)
  await expect(overview.locator('.ops-tiles')).toContainText('1 个网站异常')
  await expect(overview.locator('.ops-tiles')).toContainText('1 个目标异常')
  await expect(overview.locator('.ops-tiles')).toContainText('1 个异常')
  await expect(page.locator('.ops-row', { hasText: '合成 暂停目标' })).toContainText('已暂停')
  await expect(page.getByText('随采集停止', { exact: true })).toBeVisible()
  await expect(page.getByText('每日：刷新失败，旧数据仍可看 · http_429')).toBeVisible()
  await page.screenshot({ path: info.outputPath('operations-status.png'), fullPage: true })

  await cards.nth(1).getByRole('button', { name: '查看详情' }).click()
  const drawer = page.getByRole('dialog', { name: /问题详情/ })
  await expect(drawer).toContainText('论坛暂时无法访问或响应缓慢')
  await expect(drawer).toContainText('故障通知 · 合成 Telegram')
  await expect(drawer.getByRole('button', { name: '打开连接测试' })).toBeVisible()
  await page.screenshot({ path: info.outputPath('operations-drawer.png'), fullPage: true })
  await page.keyboard.press('Escape')
  await expect(drawer).toHaveCount(0)

  // A fault without an event row still explains itself from the current snapshot.
  await cards.nth(2).getByRole('button', { name: '查看详情' }).click()
  await expect(drawer).toContainText('目标测试已通过')
  await drawer.getByRole('button', { name: '关闭问题详情' }).click()

  expect(reads.problems[0]!.searchParams.get('show_short')).toBe('false')
  const before = reads.problems.length
  await page.getByLabel('显示 1 分钟内自动恢复的问题').check()
  await expect.poll(() => reads.problems.length).toBe(before + 1)
  expect(reads.problems.at(-1)!.searchParams.get('show_short')).toBe('true')
  await expect(page.locator('.ops-history-row').first()).toContainText('请求受限（429）')
  await expect(page.locator('.ops-history-row').first()).toContainText('已发送 1')

  const seen = reads.status
  await page.getByRole('button', { name: '刷新', exact: true }).click()
  await expect.poll(() => reads.status).toBe(seen + 1)
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }

  // Healthy: one calm line, a warning about disabled alerts, and collapsed phone rows.
  show(clear)
  await page.getByRole('button', { name: '刷新', exact: true }).click()
  await expect(page.getByRole('heading', { name: '有需要留意的状态' })).toBeVisible()
  await expect(page.locator('.ops-overview')).toContainText('当前没有需要处理的问题')
  await expect(page.getByText(/系统告警未启用或没有可用目标/)).toBeVisible()
  await expect(page.locator('.ops-problem')).toHaveCount(0)
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.locator('.ops-head').first()).toBeHidden()
  const healthy = page.locator('.ops-row', { hasText: 'LINUX DO' })
  await expect(healthy.locator('.ops-row-body')).toBeHidden()
  await healthy.locator('.ops-toggle').click()
  await expect(healthy.locator('.ops-row-body')).toBeVisible()
  await expect(
    page.locator('.ops-row', { hasText: 'NodeSeek' }).locator('.ops-row-body'),
  ).toBeVisible()
  await page.screenshot({ path: info.outputPath('operations-phone.png'), fullPage: true })

  // Old addresses land in the operations center, and tabs keep their place.
  const tabs = page.getByRole('navigation', { name: '运行中心分类', exact: true })
  for (const [from, to, label] of [
    ['/content', '/operations/content', '内容记录'],
    ['/notifications/manual', '/operations/manual', '通知记录'],
    ['/settings/diagnostics', '/operations/status', '运行状态'],
  ] as const) {
    await page.evaluate((path) => (location.hash = path), from)
    await expect(page).toHaveURL(new RegExp('#' + to + '$'))
    await expect(tabs.getByRole('button', { name: label, exact: true })).toHaveAttribute(
      'aria-current',
      'page',
    )
  }
  await page.evaluate(() => (location.hash = '/notifications/targets'))
  await expect(page).toHaveURL(/#\/notifications\/targets$/)
  await expect(page.getByRole('heading', { name: '通知目标', exact: true })).toBeVisible()
  await page.evaluate(() => (location.hash = '/websites/nodeseek'))
  const panel = page.getByRole('dialog', { name: /网站配置/ })
  await expect(panel).toBeVisible()
  await panel.getByRole('button', { name: '关闭网站面板', exact: true }).click()
  await expect(page).toHaveURL(/#\/websites$/)
  await expect(panel).toHaveCount(0)
  const filtered = page.waitForRequest(
    (request) => new URL(request.url()).searchParams.get('target_id') === 'a',
  )
  await page.evaluate(() => (location.hash = '/operations/deliveries?target=a'))
  await filtered
  await page.evaluate(() => (location.hash = '/settings/preferences'))
  await expect(page.locator('.settings-categories')).not.toContainText('诊断')
  expect(unexpected).toEqual([])
})
