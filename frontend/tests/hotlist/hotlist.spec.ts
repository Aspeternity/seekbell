import { expect, test, type Page } from '@playwright/test'
let cookies: Awaited<
  ReturnType<import('@playwright/test').APIRequestContext['storageState']>
>['cookies']
let csrf = ''
const defaults = () => [
  { id: 'tasks', visible: true },
  { id: 'matches', visible: true },
  { id: 'hotlist', visible: true },
]
test.beforeAll(async ({ request }) => {
  const auth = await (await request.get('/api/auth/status')).json()
  const response = await request.post(auth.initialized ? '/api/auth/login' : '/api/auth/setup', {
    headers: { 'X-CSRF-Token': auth.csrf },
    data: { username: 'hotlist_admin', password: 'Synthetic-Hotlist-2026' },
  })
  expect(response.ok()).toBeTruthy()
  csrf = (await response.json()).csrf
  cookies = (await request.storageState()).cookies
})
test.beforeEach(async ({ page }) => {
  await page.context().addCookies(cookies)
  const prefs = await (await page.request.get('/api/manage/overview-preferences')).json()
  await page.request.put('/api/manage/overview-preferences', {
    headers: { 'X-CSRF-Token': csrf },
    data: { modules: defaults(), revision: prefs.revision },
  })
  const selection = prefs.selection
  await page.request.put('/api/manage/hotlists/selection', {
    headers: { 'X-CSRF-Token': csrf },
    data: { website_id: 'nodeseek', period: 'realtime', revision: selection.revision },
  })
  await page.route('**/*', (route) => {
    if (new URL(route.request().url()).hostname !== '127.0.0.1')
      throw Error('Unexpected external browser request')
    return route.continue()
  })
  await page.goto('/')
  await expect(page.locator('.hotlist-row')).toHaveCount(5)
  await expect(page.getByRole('button', { name: '自定义显示', exact: true })).toHaveCount(0)
})
async function settings(page: Page) {
  const menu = page.getByRole('button', { name: '打开导航', exact: true })
  if (await menu.isVisible()) await menu.click()
  await page.getByRole('button', { name: '系统设置', exact: true }).click()
  const heading = page.getByRole('heading', { name: '概览显示模块', exact: true })
  await heading.scrollIntoViewIfNeeded()
  await expect(heading).toBeVisible()
}
async function save(page: Page) {
  await page.getByRole('button', { name: '保存偏好设置', exact: true }).click()
  await expect(page.getByText('设置已保存', { exact: true })).toBeVisible()
}
async function home(page: Page) {
  await page.evaluate(() => (location.hash = '/'))
  await expect(page.getByTestId('overview-matches')).toBeVisible()
}
test('layout order visibility persist after reload and are shared with another browser', async ({
  page,
  browser,
}) => {
  await settings(page)
  await page.getByRole('button', { name: '上移社区热榜', exact: true }).click()
  await page.getByRole('button', { name: '上移社区热榜', exact: true }).click()
  await page.getByRole('switch', { name: '显示最近命中', exact: true }).click()
  await save(page)
  await home(page)
  expect(
    await page
      .locator('[data-overview-module]')
      .evaluateAll((rows) => rows.map((row) => row.getAttribute('data-overview-module'))),
  ).toEqual(['hotlist', 'tasks'])
  await page.reload()
  await expect(page.locator('[data-overview-module="matches"]')).toHaveCount(0)
  const context = await browser.newContext({ storageState: { cookies, origins: [] } })
  const other = await context.newPage()
  await other.goto('http://127.0.0.1:8028/')
  await expect(other.locator('.hotlist-row')).toHaveCount(5)
  expect(
    await other
      .locator('[data-overview-module]')
      .evaluateAll((rows) => rows.map((row) => row.getAttribute('data-overview-module'))),
  ).toEqual(['hotlist', 'tasks'])
  await context.close()
})
test('all modules can be hidden without losing fixed metrics and default restore is a draft', async ({
  page,
}) => {
  await settings(page)
  for (const name of ['监控任务', '最近命中', '社区热榜'])
    await page.getByRole('switch', { name: '显示' + name, exact: true }).click()
  await save(page)
  let reads = 0
  await page.route('**/api/manage/hotlists/nodeseek?*', async (route) => {
    reads++
    await route.continue()
  })
  await home(page)
  await expect(page.locator('[data-overview-module]')).toHaveCount(0)
  expect(reads).toBe(0)
  await expect(
    page.getByText('内容模块已隐藏，可在系统设置中恢复。', { exact: true }),
  ).toBeVisible()
  await settings(page)
  await page.getByRole('button', { name: '恢复默认布局', exact: true }).click()
  const prefs = await (await page.request.get('/api/manage/overview-preferences')).json()
  expect(prefs.modules.every((row: any) => !row.visible)).toBeTruthy()
  await save(page)
  await home(page)
  await expect(page.locator('.hotlist-row')).toHaveCount(5)
})
test('period changes discard late responses and remember last selection', async ({ page }) => {
  let release = () => {}
  const held = new Promise<void>((resolve) => (release = resolve))
  await page.route('**/api/manage/hotlists/nodeseek?period=daily', async (route) => {
    const response = await route.fetch()
    await held
    await route.fulfill({ response })
  })
  const periods = page.getByRole('group', { name: '热榜周期' })
  await periods.getByRole('button', { name: '每日', exact: true }).click()
  await periods.getByRole('button', { name: '每周', exact: true }).click()
  await expect(page.locator('.hotlist-row').first()).toContainText('weekly')
  release()
  await expect(page.locator('.hotlist-row').first()).toContainText('weekly')
  const expand = page.getByRole('button', { name: '展开更多', exact: true })
  await expect(expand).toHaveAttribute('aria-expanded', 'false')
  await expect(expand.locator('svg')).toHaveCSS('transform', 'none')
  await expand.click()
  await expect(page.locator('.hotlist-row')).toHaveCount(10)
  const collapse = page.getByRole('button', { name: '收起', exact: true })
  await expect(collapse).toHaveAttribute('aria-expanded', 'true')
  await expect(collapse.locator('svg')).toHaveCSS('transform', 'matrix(-1, 0, 0, -1, 0, 0)')
  await collapse.click()
  await expect(page.locator('.hotlist-row')).toHaveCount(5)
  await expect(expand.locator('svg')).toHaveCSS('transform', 'none')
  await expect
    .poll(
      async () =>
        (await (await page.request.get('/api/manage/overview-preferences')).json()).selection
          .periods.nodeseek,
    )
    .toBe('weekly')
  await page.reload()
  await expect(periods.getByRole('button', { name: '每周', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  await expect(page.locator('.hotlist-row')).toHaveCount(5)
})
test('first period read shows feedback and a visited period displays its own cache during refresh', async ({
  page,
}) => {
  let release = () => {}
  let started = 0
  const held = new Promise<void>((resolve) => (release = resolve))
  await page.route('**/api/manage/hotlists/nodeseek?period=daily', async (route) => {
    const response = await route.fetch()
    started++
    await held
    await route.fulfill({ response })
  })
  const periods = page.getByRole('group', { name: '热榜周期' })
  const hotlist = page.getByRole('region', { name: '社区热榜', exact: true })
  await periods.getByRole('button', { name: '每日', exact: true }).click()
  await expect.poll(() => started).toBe(1)
  await expect(hotlist.getByRole('status')).toHaveText('加载中…')
  await expect(hotlist.locator('.read-placeholder')).toBeVisible()
  await expect(page.locator('.hotlist-row')).toHaveCount(0)
  release()
  await expect(page.locator('.hotlist-row').first()).toContainText('daily')
  await periods.getByRole('button', { name: '实时', exact: true }).click()
  await expect(page.locator('.hotlist-row').first()).toContainText('合成hot热榜帖子')

  const refresh = new Promise<void>((resolve) => (release = resolve))
  let refreshing = false
  await page.unroute('**/api/manage/hotlists/nodeseek?period=daily')
  await page.route('**/api/manage/hotlists/nodeseek?period=daily', async (route) => {
    const response = await route.fetch()
    refreshing = true
    await refresh
    await route.fulfill({ response })
  })
  await periods.getByRole('button', { name: '每日', exact: true }).click()
  await expect.poll(() => refreshing).toBe(true)
  await expect(page.locator('.hotlist-row').first()).toContainText('daily')
  await expect(page.locator('.hotlist-row')).toHaveCount(5)
  await expect(hotlist.locator('.read-placeholder')).toHaveCount(0)
  release()
})
test('site switching uses only capabilities of selected source and restores per-site period', async ({
  page,
}) => {
  await page.route('**/api/manage/overview-preferences', async (route) => {
    if (route.request().method() !== 'GET') return route.continue()
    const response = await route.fetch()
    const data = await response.json()
    data.sources.push({
      ...data.sources[0],
      website_id: 'fixture',
      name: '合成论坛',
      default_period: 'daily',
      periods: [{ id: 'daily', label: '每日' }],
    })
    await route.fulfill({ json: data })
  })
  await page.route('**/api/manage/hotlists/selection', (route) =>
    route.fulfill({ json: { revision: 5 } }),
  )
  await page.route('**/api/manage/hotlists/fixture?period=daily', (route) =>
    route.fulfill({
      json: {
        website_id: 'fixture',
        period: 'daily',
        status: 'ready',
        error_code: null,
        source_updated_at: 1792400000,
        fetched_at: 1792400000,
        next_attempt_at: Date.now() / 1000 + 600,
        items: [
          {
            id: 'fixture-1',
            rank: 1,
            title: '合成论坛自己的榜单',
            url: 'https://www.nodeseek.com/post-8800-1',
            author: null,
            category: null,
            comments: null,
            views: null,
          },
        ],
      },
    }),
  )
  await page.reload()
  await page
    .getByRole('group', { name: '热榜周期' })
    .getByRole('button', { name: '每周', exact: true })
    .click()
  await expect(page.locator('.hotlist-row').first()).toContainText('weekly')
  await page
    .getByRole('navigation', { name: '热榜网站' })
    .getByRole('button', { name: '合成论坛', exact: true })
    .click()
  await expect(page.locator('.hotlist-row')).toContainText('合成论坛自己的榜单')
  await expect(page.getByRole('group', { name: '热榜周期' })).toHaveCount(0)
  await page
    .getByRole('navigation', { name: '热榜网站' })
    .getByRole('button', { name: 'NodeSeek', exact: true })
    .click()
  await expect(page.locator('.hotlist-row').first()).toContainText('weekly')
  await expect(page.getByRole('button', { name: '每周', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
})
test('layout conflict preserves draft and keyboard ordering is accessible', async ({ page }) => {
  await settings(page)
  await page.getByRole('button', { name: '拖动排序社区热榜', exact: true }).focus()
  await page.keyboard.press('ArrowUp')
  await expect(page.locator('[data-module]').nth(1)).toHaveAttribute('data-module', 'hotlist')
  const prefs = await (await page.request.get('/api/manage/overview-preferences')).json()
  const modules = defaults()
  modules[0]!.visible = false
  await page.request.put('/api/manage/overview-preferences', {
    headers: { 'X-CSRF-Token': csrf },
    data: { modules, revision: prefs.revision },
  })
  await page.getByRole('button', { name: '保存偏好设置', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('概览布局已在其他页面改变')
  await expect(page.locator('[data-module]').nth(1)).toHaveAttribute('data-module', 'hotlist')
})
test('failed refresh keeps same-source snapshot and 320px layout fits', async ({ page }, info) => {
  await page.locator('.hotlist-panel').screenshot({ path: info.outputPath('hotlist-ready.png') })
  await page.route('**/api/manage/hotlists/nodeseek?period=realtime', async (route) => {
    const response = await route.fetch()
    const data = await response.json()
    data.status = 'stale'
    data.error_code = 'source_unavailable'
    await route.fulfill({ json: data })
  })
  await page.reload()
  await expect(
    page.getByRole('status').filter({ hasText: '更新失败，当前显示上次榜单。' }),
  ).toBeVisible()
  await expect(page.locator('.hotlist-row')).toHaveCount(5)
  await page.locator('.hotlist-panel').screenshot({ path: info.outputPath('hotlist-full.png') })
  await page.setViewportSize({ width: 320, height: 900 })
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
    .toBeTruthy()
  await page.locator('.hotlist-panel').screenshot({ path: info.outputPath('hotlist-320.png') })
  await settings(page)
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
    .toBeTruthy()
  await page
    .locator('.overview-module-settings')
    .screenshot({ path: info.outputPath('module-settings-320.png') })
})

test('pointer handle can reorder with mouse and touch', async ({ page }, info) => {
  await settings(page)
  const handle = page.getByRole('button', { name: '拖动排序社区热榜', exact: true })
  await handle.scrollIntoViewIfNeeded()
  const from = (await handle.boundingBox())!
  const to = (await page.locator('[data-module="tasks"]').boundingBox())!
  if (info.project.name === 'mobile') {
    const cdp = await page.context().newCDPSession(page)
    await cdp.send('Input.dispatchTouchEvent', {
      type: 'touchStart',
      touchPoints: [{ x: from.x + from.width / 2, y: from.y + from.height / 2 }],
    })
    await cdp.send('Input.dispatchTouchEvent', {
      type: 'touchMove',
      touchPoints: [{ x: from.x + from.width / 2, y: to.y + to.height / 2 }],
    })
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
    await cdp.detach()
  } else {
    await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2)
    await page.mouse.down()
    await page.mouse.move(from.x + from.width / 2, to.y + to.height / 2, { steps: 12 })
    await page.mouse.up()
  }
  await expect(page.locator('[data-module]').first()).toHaveAttribute('data-module', 'hotlist')
  await page
    .locator('.overview-module-settings')
    .screenshot({ path: info.outputPath('module-settings-full.png') })
})

test('no supported installed source has an actionable empty state', async ({ page }) => {
  await page.route('**/api/manage/overview-preferences', async (route) => {
    const response = await route.fetch()
    const data = await response.json()
    data.sources = []
    await route.fulfill({ json: data })
  })
  let reads = 0
  await page.route('**/api/manage/hotlists/nodeseek?*', async (route) => {
    reads++
    await route.continue()
  })
  await page.reload()
  await expect(
    page.getByRole('heading', { name: '还没有可展示热榜的网站', exact: true }),
  ).toBeVisible()
  expect(reads).toBe(0)
  await page.getByRole('button', { name: '管理网站', exact: true }).click()
  await expect(page.getByRole('heading', { name: '监控网站', exact: true })).toBeVisible()
})
