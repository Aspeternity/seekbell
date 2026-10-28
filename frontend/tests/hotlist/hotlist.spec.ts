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
  await page.clock.install()
  let release = () => {}
  let started = 0
  const held = new Promise<void>((resolve) => (release = resolve))
  await page.route('**/api/manage/hotlists/nodeseek?period=daily', async (route) => {
    const response = await route.fetch()
    started++
    await held
    await route.fulfill({ response })
  })
  await page.reload()
  await expect(page.locator('.hotlist-row')).toHaveCount(5)
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
  await page.clock.runFor(250)
  await expect(hotlist.locator('.read-placeholder')).toHaveCount(0)
  await expect(hotlist.getByRole('status')).toHaveCount(0)
  await expect(hotlist.locator('[inert]')).toHaveCount(0)
  await hotlist.getByRole('button', { name: '展开更多', exact: true }).click()
  await expect(hotlist.locator('.hotlist-row')).toHaveCount(10)
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

test('visible hotlist reads only its selected period without changing the saved selection', async ({
  page,
}) => {
  const before = (await (await page.request.get('/api/manage/overview-preferences')).json())
    .selection
  const reads = new Set<string>()
  await page.route('**/api/manage/hotlists/nodeseek?*', async (route) => {
    const response = await route.fetch()
    await route.fulfill({ response })
    reads.add(new URL(route.request().url()).searchParams.get('period')!)
  })
  await page.reload()
  await expect.poll(() => Array.from(reads).sort()).toEqual(['realtime'])
  const after = (await (await page.request.get('/api/manage/overview-preferences')).json())
    .selection
  expect(after).toEqual(before)
  await page.getByRole('button', { name: '每周', exact: true }).click()
  await expect(page.locator('.hotlist-row').first()).toContainText('weekly')
  expect(Array.from(reads).sort()).toEqual(['realtime', 'weekly'])
})

test('hotlist rows open original posts from metadata and with the keyboard', async ({ page }) => {
  await page
    .context()
    .route('https://www.nodeseek.com/**', (route) =>
      route.fulfill({ contentType: 'text/html', body: '<p>Synthetic original post</p>' }),
    )
  const row = page.locator('.hotlist-row').first()
  await expect(row).toHaveAttribute('target', '_blank')
  await expect(row).toHaveAttribute('rel', 'noopener noreferrer')
  const url = await row.getAttribute('href')
  for (const keyboard of [false, true]) {
    const popup = page.waitForEvent('popup')
    if (keyboard) {
      await row.focus()
      await page.keyboard.press('Enter')
    } else await row.locator('.hotlist-copy p').click()
    const post = await popup
    await expect(post).toHaveURL(url!)
    await post.close()
  }
})

test('recent matches are whole-row links and explain the historical task version', async ({
  page,
}) => {
  const row = page.locator('.activity-row').first()
  await expect(row).toHaveRole('link')
  await expect(row).toContainText('任务配置 v')
  await expect(row.locator('[title]')).toHaveAttribute(
    'title',
    '命中时使用的任务配置版本，历史记录保留原版本。',
  )
  const href = (await row.getAttribute('href'))!
  await row.locator('time').click()
  await expect(page).toHaveURL('http://127.0.0.1:8028/' + href)
  await expect(page.getByRole('heading', { name: '命中依据' })).toBeVisible()
  await page.goto('/')
  await row.focus()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL('http://127.0.0.1:8028/' + href)
  await page.route('**/api/manage/overview?*', async (route) => {
    const response = await route.fetch()
    const data = await response.json()
    data.recent_matches[0].post_id = null
    data.recent_matches[0].title = null
    await route.fulfill({ json: data })
  })
  await page.goto('/')
  await expect(row).toContainText('原内容已清理')
  await expect(row).not.toHaveAttribute('href')
  await expect(row).not.toHaveRole('link')
})

test('background refresh silently replaces the list without blocking links or expansion', async ({
  page,
}, info) => {
  await page.clock.install()
  await page.clock.pauseAt(new Date())
  let reads = 0
  let release = () => {}
  const held = new Promise<void>((resolve) => (release = resolve))
  await page.route('**/api/manage/hotlists/nodeseek?period=realtime', async (route) => {
    const read = ++reads
    const response = await route.fetch()
    const data = await response.json()
    if (read === 2) {
      await held
      data.items[0].title = '后台更新后的榜首'
    }
    await route.fulfill({
      json: {
        ...data,
        refreshing: read === 1,
        next_attempt_at: (await page.evaluate(() => Date.now())) / 1000 + (read === 1 ? 2 : 600),
      },
    })
  })
  await page.reload()
  const hotlist = page.getByRole('region', { name: '社区热榜', exact: true })
  await expect(hotlist.locator('.hotlist-row')).toHaveCount(5)
  await expect(hotlist.getByRole('status')).toHaveCount(0)
  const title = await hotlist.locator('.hotlist-title').first().textContent()
  await page.clock.fastForward(2200)
  await expect.poll(() => reads).toBe(2)
  await page.clock.runFor(250)
  await expect(hotlist.getByRole('status')).toHaveCount(0)
  await expect(hotlist.locator('.read-placeholder, [inert]')).toHaveCount(0)
  await expect(hotlist.locator('.hotlist-title').first()).toHaveText(title!)
  await hotlist.getByRole('button', { name: '展开更多', exact: true }).click()
  await expect(hotlist.locator('.hotlist-row')).toHaveCount(10)
  const row = hotlist.locator('.hotlist-row').first()
  await row.click({ trial: true })
  await row.focus()
  await expect(row).toBeFocused()
  await hotlist.screenshot({ path: info.outputPath('hotlist-silent-refresh.png') })
  release()
  await expect(hotlist.locator('.hotlist-title').first()).toHaveText('后台更新后的榜首')
  await expect(hotlist.locator('.hotlist-row')).toHaveCount(10)
  await expect(hotlist.getByRole('status')).toHaveCount(0)
  await page.clock.fastForward(3000)
  expect(reads).toBe(2)
})

for (const code of ['source_busy', 'source_cooldown', 'collection_priority']) {
  test(
    'cached hotlist silently waits for ' + code + ' and updates on schedule',
    async ({ page }) => {
      await page.clock.install()
      let reads = 0
      await page.route('**/api/manage/hotlists/nodeseek?period=realtime', async (route) => {
        const read = ++reads
        const response = await route.fetch()
        const data = await response.json()
        if (read > 1) data.items[0].title = '等待后更新的榜首'
        await route.fulfill({
          json: {
            ...data,
            status: read === 1 ? 'waiting' : 'ready',
            error_code: read === 1 ? code : null,
            next_attempt_at:
              (await page.evaluate(() => Date.now())) / 1000 + (read === 1 ? 2 : 600),
          },
        })
      })
      await page.reload()
      const hotlist = page.getByRole('region', { name: '社区热榜', exact: true })
      await expect(hotlist.locator('.hotlist-row')).toHaveCount(5)
      await expect(hotlist.getByRole('status')).toHaveCount(0)
      await page.clock.fastForward(2200)
      await expect(hotlist.locator('.hotlist-title').first()).toHaveText('等待后更新的榜首')
      await expect(hotlist.getByRole('status')).toHaveCount(0)
      expect(reads).toBe(2)
    },
  )
}

for (const state of ['ready', 'waiting']) {
  test(
    'an empty successful hotlist stays visible during ' + state + ' refresh',
    async ({ page }) => {
      await page.clock.install()
      await page.clock.pauseAt(new Date())
      let reads = 0
      await page.route('**/api/manage/hotlists/nodeseek?period=realtime', async (route) => {
        const read = ++reads
        const response = await route.fetch()
        const data = await response.json()
        await route.fulfill({
          json: {
            ...data,
            items: read === 1 ? [] : data.items,
            status: read === 1 ? state : 'ready',
            refreshing: read === 1 && state === 'ready',
            error_code: read === 1 && state === 'waiting' ? 'source_cooldown' : null,
            next_attempt_at:
              (await page.evaluate(() => Date.now())) / 1000 + (read === 1 ? 2 : 600),
          },
        })
      })
      await page.reload()
      const hotlist = page.getByRole('region', { name: '社区热榜', exact: true })
      await expect(hotlist.getByText('当前榜单还没有帖子。', { exact: true })).toBeVisible()
      await expect(hotlist.getByRole('status')).toHaveCount(0)
      await expect(hotlist.locator('.read-placeholder')).toHaveCount(0)
      await page.clock.fastForward(2200)
      await expect(hotlist.locator('.hotlist-row')).toHaveCount(5)
      await expect(hotlist.getByText('当前榜单还没有帖子。', { exact: true })).toHaveCount(0)
      expect(reads).toBe(2)
    },
  )
}

async function websitePanel(page: Page, site: string) {
  await page.goto('/#/websites')
  await page.getByRole('button', { name: '查看 ' + site + ' 配置', exact: true }).click()
  return page.getByRole('dialog', { name: site + ' 网站配置', exact: true })
}
test('website hotlist intervals save independently and restore recommended settings', async ({
  page,
}, testInfo) => {
  const dialog = await websitePanel(page, 'NodeSeek')
  const section = dialog.getByRole('region', { name: '社区热榜配置', exact: true })
  await expect(section.getByText('第三方 NodeSeek 热榜', { exact: true })).toBeVisible()
  await expect(section.getByText('每 10 分钟更新', { exact: true })).toBeVisible()
  await expect(section.getByText('每 30 分钟更新', { exact: true })).toBeVisible()
  await expect(section.getByText('每 60 分钟更新', { exact: true })).toBeVisible()
  const sourceInterval = await dialog.locator('#source-interval').inputValue()
  await section.getByRole('combobox', { name: '热榜刷新设置' }).click()
  await page.getByRole('option', { name: '自定义', exact: true }).click()
  await section.getByRole('spinbutton', { name: '实时榜刷新间隔' }).fill('20')
  await section.getByRole('spinbutton', { name: '每日榜刷新间隔' }).fill('45')
  await section.getByRole('spinbutton', { name: '每周榜刷新间隔' }).fill('120')
  await expect(dialog.getByText('有未保存的修改', { exact: true })).toBeVisible()
  await dialog.getByRole('button', { name: '保存设置', exact: true }).click()
  await expect(dialog.getByText('设置已保存', { exact: true })).toBeVisible()
  const websites = (await (await page.request.get('/api/manage/workspace')).json()).websites
  const saved = websites.find((row: { id: string }) => row.id === 'nodeseek')
  expect(saved.interval).toBe(Number(sourceInterval))
  expect(saved.hotlist.mode).toBe('custom')
  expect(
    saved.hotlist.periods.map((p: { interval_seconds: number }) => p.interval_seconds),
  ).toEqual([1200, 2700, 7200])
  await page.reload()
  await page.getByRole('button', { name: '查看 NodeSeek 配置', exact: true }).click()
  await expect(section.getByRole('spinbutton', { name: '实时榜刷新间隔' })).toHaveValue('20')
  await expect(section.getByRole('spinbutton', { name: '每日榜刷新间隔' })).toHaveValue('45')
  await expect(section.getByRole('spinbutton', { name: '每周榜刷新间隔' })).toHaveValue('120')
  const mode = section.getByRole('combobox', { name: '热榜刷新设置' })
  await mode.focus()
  await page.keyboard.press('ArrowDown')
  await expect(dialog.getByRole('listbox', { name: '热榜刷新设置' })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(mode).toHaveAttribute('aria-expanded', 'false')
  await expect(dialog).toBeVisible()
  await section.scrollIntoViewIfNeeded()
  expect(await section.evaluate((el) => el.scrollWidth <= el.clientWidth + 1)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('website-hotlist-custom.png') })
  await section.getByRole('button', { name: '恢复推荐', exact: true }).click()
  await expect(section.getByRole('spinbutton')).toHaveCount(0)
  await expect(section.getByText('每 10 分钟更新', { exact: true })).toBeVisible()
  await dialog.getByRole('button', { name: '保存设置', exact: true }).click()
  await expect(dialog.getByText('设置已保存', { exact: true })).toBeVisible()
})

test('Linux DO displays its supported periods and validates drafts before saving', async ({
  page,
}) => {
  await page.goto('/#/websites')
  if (!(await page.getByRole('button', { name: '查看 LINUX DO 配置', exact: true }).count())) {
    await page.getByRole('button', { name: '添加网站', exact: true }).click()
    await page.getByRole('button', { name: '添加 LINUX DO', exact: true }).click()
    await expect(page.getByRole('dialog', { name: '添加内置网站', exact: true })).not.toBeVisible()
  }
  const dialog = await websitePanel(page, 'LINUX DO')
  const section = dialog.getByRole('region', { name: '社区热榜配置', exact: true })
  await expect(section.getByText('LINUX DO 官方 RSS', { exact: true })).toBeVisible()
  await expect(section.getByText('热门榜', { exact: true })).toBeVisible()
  await expect(section.getByText('实时榜', { exact: true })).toHaveCount(0)
  await expect(section.getByText('每 15 分钟更新', { exact: true })).toBeVisible()
  await section.getByRole('combobox', { name: '热榜刷新设置' }).click()
  await page.getByRole('option', { name: '自定义', exact: true }).click()
  await section.getByRole('spinbutton', { name: '每周榜刷新间隔' }).fill('5')
  let writes = 0
  page.on('request', (request) => {
    if (request.method() === 'PUT' && request.url().endsWith('/api/manage/websites/linuxdo'))
      writes++
  })
  await dialog.getByRole('button', { name: '保存设置', exact: true }).click()
  await expect(dialog.getByRole('alert')).toContainText('每周榜刷新间隔应为 30–1440')
  await expect(dialog.getByRole('alert')).toBeInViewport()
  expect(writes).toBe(0)
  await dialog.getByRole('button', { name: '关闭网站面板', exact: true }).click()
  await expect(page.getByRole('button', { name: '继续编辑', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '继续编辑', exact: true }).click()
  await expect(section.getByRole('spinbutton', { name: '每周榜刷新间隔' })).toHaveValue('5')
  await section.getByRole('button', { name: '恢复推荐', exact: true }).click()
  await dialog.getByRole('button', { name: '关闭网站面板', exact: true }).click()
  await expect(dialog).not.toBeVisible()
})

test('long hotlist backoff shows timing and avoids the old ten-minute status poll', async ({
  page,
}) => {
  await page.clock.install()
  let reads = 0
  let completed = 0
  await page.route('**/api/manage/hotlists/nodeseek?period=realtime', async (route) => {
    const response = await route.fetch()
    reads++
    await route.fulfill({
      json: {
        ...(await response.json()),
        refreshing: false,
        status: 'stale',
        error_code: 'http_429',
        next_attempt_at: (await page.evaluate(() => Date.now())) / 1000 + 3600,
      },
    })
    completed++
  })
  await page.reload()
  const hotlist = page.getByRole('region', { name: '社区热榜', exact: true })
  await expect(hotlist.getByRole('status')).toContainText('来源请求受限（429）')
  await expect(hotlist.getByRole('status')).toContainText('预计')
  await expect(hotlist.getByRole('status')).toContainText('上次成功获取')
  await expect(hotlist.getByText('正在后台更新，当前显示上次榜单。')).toHaveCount(0)
  await page.clock.fastForward(600100)
  expect(reads).toBe(1)
  await page.clock.fastForward(3000100)
  await expect.poll(() => reads).toBe(2)
  await expect.poll(() => completed).toBe(2)
})

test('a failed background status read shows an error and recovers after a local retry', async ({
  page,
}) => {
  await page.clock.install()
  let reads = 0
  let completed = 0
  await page.route('**/api/manage/hotlists/nodeseek?period=realtime', async (route) => {
    const read = ++reads
    if (read === 2) return route.abort('failed')
    const response = await route.fetch()
    await route.fulfill({
      json: {
        ...(await response.json()),
        refreshing: read === 1,
        next_attempt_at: (await page.evaluate(() => Date.now())) / 1000 + (read === 1 ? 2 : 600),
      },
    })
    completed++
  })
  await page.reload()
  const hotlist = page.getByRole('region', { name: '社区热榜', exact: true })
  const updating = hotlist.getByText('正在后台更新，当前显示上次榜单。', { exact: true })
  await expect.poll(() => completed).toBe(1)
  await expect(hotlist.locator('.hotlist-row')).toHaveCount(5)
  await expect(updating).toHaveCount(0)
  await page.clock.fastForward(2200)
  await expect(hotlist.getByRole('alert')).toContainText('刷新失败，当前显示上次结果。')
  await expect(updating).toHaveCount(0)
  await expect(hotlist.locator('.hotlist-row')).toHaveCount(5)
  await page.clock.fastForward(15100)
  await expect.poll(() => reads).toBe(3)
  // The visible cached rows do not prove the final mocked response has finished.
  await expect.poll(() => completed).toBe(2)
  await expect(hotlist.locator('.hotlist-row')).toHaveCount(5)
  await expect(hotlist.getByRole('alert')).toHaveCount(0)
  await expect(hotlist.getByRole('status')).toHaveCount(0)
})

test('website hotlist controls follow supplied capabilities and omit unsupported sites', async ({
  page,
}) => {
  let supported = true
  await page.route('**/api/manage/workspace', async (route) => {
    const response = await route.fetch()
    const data = await response.json()
    const website = data.websites.find((row: { id: string }) => row.id === 'nodeseek')
    website.hotlist = supported
      ? {
          ...website.hotlist,
          periods: website.hotlist.periods.filter(
            (period: { id: string }) => period.id === 'daily',
          ),
        }
      : null
    await route.fulfill({ response, json: data })
  })
  await page.reload()
  const dialog = await websitePanel(page, 'NodeSeek')
  const section = dialog.getByRole('region', { name: '社区热榜配置', exact: true })
  await expect(section.getByText('每日榜', { exact: true })).toBeVisible()
  await expect(section.getByText('实时榜', { exact: true })).toHaveCount(0)
  await expect(section.getByText('每周榜', { exact: true })).toHaveCount(0)
  await dialog.getByRole('button', { name: '关闭网站面板', exact: true }).click()
  supported = false
  await page.reload()
  await page.getByRole('button', { name: '查看 NodeSeek 配置', exact: true }).click()
  await expect(section).toHaveCount(0)
  await expect(dialog.getByRole('heading', { name: '采集配置', exact: true })).toBeVisible()
})

test('website hotlist menu remains next to its trigger in a scrolled scaled dialog', async ({
  page,
}, info) => {
  await page.setViewportSize({ width: 2560, height: 1400 })
  const dialog = await websitePanel(page, 'NodeSeek')
  const control = dialog.getByRole('combobox', { name: '热榜刷新设置' })
  const menu = dialog.getByRole('listbox', { name: '热榜刷新设置' })
  await control.scrollIntoViewIfNeeded()
  await control.click()
  await expect(menu).toBeVisible()
  const a = (await control.boundingBox())!,
    b = (await menu.boundingBox())!
  await page.screenshot({ path: info.outputPath('scaled-dialog-menu.png') })
  expect(Math.abs(a.x - b.x)).toBeLessThanOrEqual(3)
  expect(b.y - a.y - a.height).toBeGreaterThanOrEqual(0)
  expect(b.y - a.y - a.height).toBeLessThanOrEqual(15)
  await page.keyboard.press('Escape')
  await page.evaluate(() => document.documentElement.style.setProperty('--workspace-scale', '1.25'))
  await control.click()
  await expect(menu).toBeVisible()
  const c = (await control.boundingBox())!,
    d = (await menu.boundingBox())!
  expect(Math.abs(c.x - d.x)).toBeLessThanOrEqual(3)
  expect(d.y - c.y - c.height).toBeLessThanOrEqual(15)
  const distance = async () => {
    const target = (await control.boundingBox())!,
      popup = (await menu.boundingBox())!
    return Math.min(
      Math.abs(popup.y - target.y - target.height),
      Math.abs(target.y - popup.y - popup.height),
    )
  }
  await dialog.locator('.website-drawer-body').evaluate((el) => el.scrollBy(0, 80))
  await expect.poll(distance).toBeLessThanOrEqual(15)
  await page.evaluate(() => document.documentElement.style.removeProperty('--workspace-scale'))
  await page.setViewportSize({ width: 390, height: 844 })
  await expect.poll(distance).toBeLessThanOrEqual(15)
  await menu.getByRole('option', { name: '自定义', exact: true }).click()
  await expect(dialog.getByRole('spinbutton', { name: '实时榜刷新间隔' })).toBeVisible()
})

test('origin cooldown explains that an unattempted hotlist waits while actual challenges report the right cause', async ({
  page,
}) => {
  let waiting = true
  await page.route('**/api/manage/hotlists/nodeseek?period=realtime', async (route) => {
    const response = await route.fetch()
    await route.fulfill({
      json: {
        ...(await response.json()),
        status: waiting ? 'waiting' : 'stale',
        error_code: 'access_challenge',
        refreshing: false,
        next_attempt_at: Date.now() / 1000 + 300,
      },
    })
  })
  await page.reload()
  const hotlist = page.getByRole('region', { name: '社区热榜', exact: true })
  await expect(hotlist.getByRole('status')).toContainText('本次榜单更新已延后')
  await expect(hotlist.getByRole('status')).not.toContainText('更新失败')
  await expect(hotlist.locator('.hotlist-row')).toHaveCount(5)
  waiting = false
  await page.reload()
  await expect(hotlist.getByRole('status')).toContainText('来源要求 Cloudflare 验证')
  await expect(hotlist.getByRole('status')).not.toContainText('429')
  await expect(hotlist.getByRole('status')).not.toContainText('403')
})
