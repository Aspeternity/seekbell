import { expect, test, type Page } from '@playwright/test'

let cookies: Awaited<
  ReturnType<import('@playwright/test').APIRequestContext['storageState']>
>['cookies']
let csrf = ''
const errors = new WeakMap<Page, string[]>()
const writes = new WeakMap<Page, Set<unknown>>()
const headers = () => ({ 'X-CSRF-Token': csrf })

test.beforeAll(async ({ request }) => {
  const auth = await (await request.get('/api/auth/status')).json()
  const response = await request.post(auth.initialized ? '/api/auth/login' : '/api/auth/setup', {
    headers: { 'X-CSRF-Token': auth.csrf },
    data: { username: 'linuxdo_admin', password: 'Synthetic-Linuxdo-2026' },
  })
  expect(response.ok()).toBeTruthy()
  csrf = (await response.json()).csrf
  cookies = (await request.storageState()).cookies
})

test.beforeEach(async ({ page }) => {
  errors.set(page, [])
  page.on('pageerror', (error) => errors.get(page)!.push(error.message))
  const pending = new Set<unknown>()
  writes.set(page, pending)
  page.on('request', (request) => request.method() !== 'GET' && pending.add(request))
  for (const event of ['requestfinished', 'requestfailed'] as const)
    page.on(event, (request) => pending.delete(request))
  await page.context().addCookies(cookies)
  const workspace = await (await page.request.get('/api/manage/workspace')).json()
  for (const task of workspace.tasks.filter((task: any) => task.website_ids.includes('linuxdo')))
    expect(
      (await page.request.delete('/api/manage/tasks/' + task.id, { headers: headers() })).ok(),
    ).toBeTruthy()
  if (!workspace.websites.some((site: any) => site.id === 'linuxdo'))
    expect(
      (
        await page.request.post('/api/manage/websites', {
          headers: headers(),
          data: { adapter_id: 'linuxdo' },
        })
      ).ok(),
    ).toBeTruthy()
  const prefs = await (await page.request.get('/api/manage/overview-preferences')).json()
  expect(
    (
      await page.request.put('/api/manage/overview-preferences', {
        headers: headers(),
        data: {
          modules: ['tasks', 'matches', 'hotlist'].map((id) => ({ id, visible: true })),
          revision: prefs.revision,
        },
      })
    ).ok(),
  ).toBeTruthy()
  const reset = await page.request.put('/api/manage/hotlists/selection', {
    headers: headers(),
    data: { website_id: 'linuxdo', period: 'hot', revision: prefs.selection.revision },
  })
  expect(reset.status(), await reset.text()).toBe(200)
  expect(
    (
      await page.request.put('/api/manage/hotlists/selection', {
        headers: headers(),
        data: {
          website_id: 'nodeseek',
          period: 'realtime',
          revision: (await reset.json()).revision,
        },
      })
    ).ok(),
  ).toBeTruthy()
  await page.route('**/*', (route) => {
    if (new URL(route.request().url()).hostname !== '127.0.0.1')
      throw Error('Unexpected external browser request')
    return route.continue()
  })
  await page.goto('/')
  await expect(page.locator('.hotlist-row')).toHaveCount(5)
})

test.afterEach(async ({ page }) => {
  // Drain queued selection writes before the next test resets shared preferences. The
  // hotlist long poll stays open, so the network never becomes idle.
  await expect.poll(() => writes.get(page)!.size).toBe(0)
  expect(errors.get(page)).toEqual([])
})

async function noOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
}

test('catalog installs Linux DO paused with its own interval and capabilities', async ({
  page,
}, info) => {
  expect(
    (await page.request.delete('/api/manage/websites/linuxdo', { headers: headers() })).ok(),
  ).toBeTruthy()
  await page.reload()
  await page.goto('/#/websites')
  await page.getByRole('button', { name: '添加网站', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '添加内置网站', exact: true })
  await expect(dialog.getByRole('heading', { name: 'LINUX DO', exact: true })).toBeVisible()
  await dialog.getByRole('button', { name: '添加 LINUX DO', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  await page.getByRole('button', { name: '配置 LINUX DO', exact: true }).click()
  const config = page.getByRole('dialog', { name: 'LINUX DO 网站配置', exact: true })
  await expect(config.locator('#source-interval')).toHaveValue('60')
  await expect(config.locator('#source-interval')).toHaveAttribute('min', '60')
  await expect(
    config.getByRole('switch', { name: 'LINUX DO 采集启用状态', exact: true }),
  ).toHaveAttribute('aria-checked', 'false')
  await expect(config.getByText('作者显示名', { exact: true })).toBeVisible()
  await expect(config.getByText(/暂不支持精确用户名筛选/)).toBeVisible()
  await page.screenshot({ path: info.outputPath('linuxdo-website.png'), fullPage: true })
  await noOverflow(page)
})

test('task editor enforces Linux DO capabilities and saves a task for the selected site', async ({
  page,
}, info) => {
  await page.goto('/#/task/new')
  const picker = page.locator('#task-website')
  await picker.getByRole('checkbox', { name: 'NodeSeek', exact: false }).check()
  await page.getByText('更多匹配设置', { exact: true }).click()
  await page.getByLabel('包含作者', { exact: true }).fill('synthetic-user')
  await page.getByLabel('包含作者', { exact: true }).press('Enter')
  await picker.getByRole('checkbox', { name: 'NodeSeek', exact: false }).uncheck()
  await picker.getByRole('checkbox', { name: 'LINUX DO', exact: false }).check()
  await expect(
    page.getByText('所选网站中有 RSS 仅提供作者显示名的网站，暂不支持共同使用精确用户名筛选。', {
      exact: true,
    }),
  ).toBeVisible()
  await expect(page.getByLabel('包含作者', { exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: '清除作者条件', exact: true }).click()
  const name = 'Linux DO 浏览器任务 ' + info.project.name
  await page.locator('#task-name').fill(name)
  await page.locator('.target-options label').first().click()
  await page.getByRole('button', { name: '保存任务', exact: true }).click()
  await expect
    .poll(
      async () =>
        (await (await page.request.get('/api/manage/workspace')).json()).tasks.find(
          (task: any) => task.name === name,
        )?.website_id,
    )
    .toBe('linuxdo')
  const workspace = await (await page.request.get('/api/manage/workspace')).json()
  const task = workspace.tasks.find((task: any) => task.name === name)
  expect(task.rule.authors_include).toEqual([])
  expect(task.rule.authors_exclude).toEqual([])
  expect(workspace.websites.find((site: any) => site.id === 'linuxdo').enabled).toBe(false)
})

test('real multi-site hotlist capabilities selections times and original links persist', async ({
  page,
}, info) => {
  const hotlist = page.getByRole('region', { name: '社区热榜', exact: true })
  await hotlist.getByRole('button', { name: 'LINUX DO', exact: true }).click()
  await expect(hotlist.locator('.hotlist-row').first()).toContainText('LinuxDOhot')
  const periods = hotlist.getByRole('group', { name: '热榜周期' })
  await expect(periods.getByRole('button')).toHaveText(['热门', '每日', '每周'])
  await expect(hotlist.getByText(/获取于 ·/)).toBeVisible()
  await expect(hotlist.getByText(/来源更新 ·/)).toHaveCount(0)
  await expect(hotlist.locator('.hotlist-row').first()).toHaveAttribute(
    'href',
    'https://linux.do/t/topic/9800',
  )
  await expect(hotlist.locator('.hotlist-row').first()).toHaveAttribute('target', '_blank')
  await expect(hotlist.getByText(/条评论/)).toHaveCount(0)
  await periods.getByRole('button', { name: '每周', exact: true }).click()
  await expect(hotlist.locator('.hotlist-row').first()).toContainText('LinuxDOweekly')
  await hotlist.getByRole('button', { name: 'NodeSeek', exact: true }).click()
  await expect(periods.getByRole('button')).toHaveText(['实时', '每日', '每周'])
  await expect(hotlist.locator('.hotlist-row').first()).toContainText('合成hot热榜帖子')
  await hotlist.getByRole('button', { name: 'LINUX DO', exact: true }).click()
  await expect(periods.getByRole('button', { name: '每周', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  await expect
    .poll(
      async () =>
        (await (await page.request.get('/api/manage/overview-preferences')).json()).selection
          .website_id,
    )
    .toBe('linuxdo')
  await page.reload()
  await expect(page.locator('.hotlist-row').first()).toContainText('LinuxDOweekly')
  await page.screenshot({ path: info.outputPath('linuxdo-hotlist.png'), fullPage: true })
  await noOverflow(page)
})

test('switching between sites and periods is local and keeps each sites own list', async ({
  page,
}) => {
  const fresh: string[] = []
  page.on('request', (request) => {
    const url = new URL(request.url())
    if (url.pathname.startsWith('/api/manage/hotlists') && request.method() === 'GET')
      if (!url.searchParams.has('after')) fresh.push(url.pathname)
  })
  const hotlist = page.getByRole('region', { name: '社区热榜', exact: true })
  await hotlist.getByRole('button', { name: 'LINUX DO', exact: true }).click()
  await expect(hotlist.locator('.hotlist-row').first()).toContainText('LinuxDOhot')
  await hotlist.getByRole('button', { name: '每日', exact: true }).click()
  await expect(hotlist.locator('.hotlist-row').first()).toContainText('LinuxDOdaily')
  await hotlist.getByRole('button', { name: 'NodeSeek', exact: true }).click()
  await expect(hotlist.locator('.hotlist-row').first()).toContainText('合成hot热榜帖子')
  await expect(hotlist.getByRole('button', { name: '实时', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  expect(fresh).toEqual([])
})

test('Linux DO access errors are explicit and do not block NodeSeek', async ({ page }) => {
  await page.route(
    (url) => url.pathname === '/api/manage/hotlists',
    async (route) => {
      const response = await route.fetch().catch(() => undefined)
      if (!response) return
      const data = await response.json()
      for (const row of data.lists)
        if (row.website_id === 'linuxdo')
          Object.assign(row, {
            items: [],
            status: 'unavailable',
            refreshing: false,
            error_code: 'access_challenge',
            fetched_at: null,
            source_updated_at: null,
            next_attempt_at: Date.now() / 1000 + 300,
          })
      await route.fulfill({ json: data }).catch(() => {})
    },
  )
  await page.reload()
  const hotlist = page.getByRole('region', { name: '社区热榜', exact: true })
  await hotlist.getByRole('button', { name: 'LINUX DO', exact: true }).click()
  await expect(hotlist.getByText(/来源要求 Cloudflare 验证/)).toBeVisible()
  await expect(hotlist.locator('.hotlist-row')).toHaveCount(0)
  await hotlist.getByRole('button', { name: 'NodeSeek', exact: true }).click()
  await expect(hotlist.locator('.hotlist-row')).toHaveCount(5)
})

test('Linux DO connection checks explain limited early retry and retain server cooldown feedback', async ({
  page,
}) => {
  await page.goto('/#/websites')
  await page.getByRole('button', { name: '配置 LINUX DO', exact: true }).click()
  const config = page.getByRole('dialog', { name: 'LINUX DO 网站配置', exact: true })
  await expect(config.getByText(/每 60 秒最多测试一次/)).toBeVisible()
  let attempts = 0
  await page.route('**/api/manage/websites/linuxdo/connection-test', async (route) => {
    if (route.request().method() !== 'POST') return route.continue()
    attempts += 1
    if (attempts > 1)
      return route.fulfill({
        status: 429,
        headers: { 'Retry-After': '60' },
        json: { detail: '连接测试每 60 秒最多一次；约 60 秒后可再次测试。' },
      })
    const now = Date.now() / 1000
    return route.fulfill({
      json: {
        started_at: now,
        finished_at: now,
        next_attempt_at: now + 60,
        status: 'success',
        code: null,
        item_count: 1,
      },
    })
  })
  await config.getByRole('button', { name: '测试连接', exact: true }).click()
  await expect(page.getByText(/可提前验证连接，仍遵守站点要求的等待时间/)).toBeVisible()
  await page.getByRole('button', { name: '确认测试连接', exact: true }).click()
  await expect(config.getByText('RSS 连接与解析成功', { exact: true })).toBeVisible()
  await expect(config.getByText(/下次可测试时间：/)).toBeVisible()
  await config.getByRole('button', { name: '测试连接', exact: true }).click()
  await page.getByRole('button', { name: '确认测试连接', exact: true }).click()
  await expect(config.getByRole('alert')).toContainText('连接测试每 60 秒最多一次')
  await expect(config.locator('.match-result.yes')).toHaveCount(0)
  expect(attempts).toBe(2)
})

test('websites retain their add order across the catalog, overview and reload', async ({
  page,
}) => {
  await page.goto('/#/websites')
  await expect(page.locator('.website-card h2')).toHaveText(['NodeSeek', 'LINUX DO'])
  await page.reload()
  await expect(page.locator('.website-card h2')).toHaveText(['NodeSeek', 'LINUX DO'])
  await page.goto('/#/')
  const hotlist = page.getByRole('region', { name: '社区热榜', exact: true })
  await expect(hotlist.locator('.hotlist-site')).toHaveText(['NodeSeek', 'LINUX DO'])
})

test('a Linux DO list waiting for the shared request gap explains it and then fills in', async ({
  page,
}) => {
  let reads = 0,
    release = () => {}
  const held = new Promise<void>((resolve) => (release = resolve))
  await page.route(
    (url) => url.pathname === '/api/manage/hotlists',
    async (route) => {
      const read = ++reads
      if (read > 2) return route.continue()
      // The first two replies answer at once; the later ones are the real long poll.
      const url = new URL(route.request().url())
      url.searchParams.delete('after')
      const response = await route.fetch({ url: url.toString() }).catch(() => undefined)
      if (!response) return
      const data = await response.json()
      if (read === 1)
        Object.assign(
          data.lists.find((row: any) => row.website_id === 'linuxdo' && row.period === 'daily'),
          {
            status: 'waiting',
            refreshing: false,
            error_code: 'source_cooldown',
            fetched_at: null,
            source_updated_at: null,
            items: [],
            next_attempt_at: Date.now() / 1000 + 2,
          },
        )
      else await held
      await route.fulfill({ json: data }).catch(() => {})
    },
  )
  await page.reload()
  const hotlist = page.getByRole('region', { name: '社区热榜', exact: true })
  await hotlist.getByRole('button', { name: 'LINUX DO', exact: true }).click()
  await expect(hotlist.locator('.hotlist-row').first()).toContainText('LinuxDOhot')
  await hotlist.getByRole('button', { name: '每日', exact: true }).click()
  await expect(
    hotlist.getByText('正在等待同站请求间隔，稍后自动重试。', { exact: true }),
  ).toBeVisible()
  await expect(hotlist.getByText('暂时无法获取榜单，请稍后重试。', { exact: true })).toHaveCount(0)
  release()
  await expect(hotlist.locator('.hotlist-row')).toHaveCount(5)
  await expect(hotlist.locator('.hotlist-row').first()).toContainText('LinuxDOdaily')
})

test('editor section highlight follows scrolling back after a chapter jump', async ({ page }) => {
  await page.goto('/#/task/new')
  const nav = page.getByRole('navigation', { name: '编辑页章节', exact: true })
  const basic = nav.getByRole('button', { name: '01 基本信息', exact: true })
  const rules = nav.getByRole('button', { name: '02 匹配规则', exact: true })
  const delivery = nav.getByRole('button', { name: '03 通知目标', exact: true })
  await expect(basic).toHaveAttribute('aria-current', 'location')
  await rules.click()
  await expect(rules).toHaveAttribute('aria-current', 'location')
  await expect.poll(async () => (await page.locator('#rules').boundingBox())!.y).toBeLessThan(180)
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }))
  await expect(basic).toHaveAttribute('aria-current', 'location')
  await expect(rules).not.toHaveAttribute('aria-current', 'location')
  await delivery.click()
  await expect(delivery).toHaveAttribute('aria-current', 'location')
  await page.evaluate(() =>
    document.getElementById('rules')!.scrollIntoView({ behavior: 'instant' }),
  )
  await expect(rules).toHaveAttribute('aria-current', 'location')
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }))
  await expect(basic).toHaveAttribute('aria-current', 'location')
})

test('existing task can add and remove sites in place while retaining its rule and targets', async ({
  page,
}, info) => {
  const workspace = await (await page.request.get('/api/manage/workspace')).json()
  const original = {
    name: '多站原任务 ' + info.project.name,
    description: '保留这套规则和通知目标',
    website_id: 'nodeseek',
    enabled: false,
    rule: { groups: [{ all_of: ['VPS'], any_of: [] }], exclude: ['求购'] },
    target_ids: [workspace.targets[0].id],
  }
  const response = await page.request.post('/api/manage/tasks', {
    headers: headers(),
    data: original,
  })
  expect(response.ok()).toBe(true)
  const id = (await response.json()).id
  const before = (await (await page.request.get('/api/manage/workspace')).json()).tasks.find(
    (task: any) => task.id === id,
  )
  await page.reload()
  await page.goto('/#/task/' + id)
  const sites = page.locator('#task-website')
  const node = sites.getByRole('checkbox', { name: 'NodeSeek', exact: false })
  const linux = sites.getByRole('checkbox', { name: 'LINUX DO', exact: false })
  await expect(node).toBeChecked()
  await expect(linux).not.toBeChecked()
  await expect(linux).toBeEnabled()
  await node.uncheck()
  await page.getByRole('button', { name: '保存任务', exact: true }).click()
  await expect(page.locator('[data-form-errors]')).toContainText('请选择已添加的监控网站')
  await node.check()
  await linux.check()
  await page.getByRole('button', { name: '保存任务', exact: true }).click()
  await expect
    .poll(async () => {
      const rows = (await (await page.request.get('/api/manage/workspace')).json()).tasks
      return rows.find((task: any) => task.id === id)?.website_ids
    })
    .toEqual(['nodeseek', 'linuxdo'])
  const after = (await (await page.request.get('/api/manage/workspace')).json()).tasks.find(
    (task: any) => task.id === id,
  )
  for (const key of ['id', 'name', 'description', 'target_ids', 'enabled'])
    expect(after[key]).toEqual(before[key])
  const { site_categories: _oldScopes, ...beforeShared } = before.rule
  const { site_categories, ...afterShared } = after.rule
  expect(afterShared).toEqual(beforeShared)
  expect(site_categories).toEqual({
    nodeseek: { mode: 'all', values: [] },
    linuxdo: { mode: 'all', values: [] },
  })
  expect(after.version).toBe(2)
  await page.goto('/#/tasks')
  const row = page.locator('.task-management-row').filter({ hasText: original.name })
  await expect(row).toContainText('NodeSeek、LINUX DO')
  await page.goto('/#/task/' + id)
  await expect(node).toBeChecked()
  await expect(linux).toBeChecked()
  await page.screenshot({ path: info.outputPath('task-multiple-websites.png'), fullPage: true })
  await node.uncheck()
  await page.getByRole('button', { name: '保存任务', exact: true }).click()
  await expect
    .poll(async () => {
      const rows = (await (await page.request.get('/api/manage/workspace')).json()).tasks
      return rows.find((task: any) => task.id === id)?.website_ids
    })
    .toEqual(['linuxdo'])
  await noOverflow(page)
})

test('connection history is collapsed, dated and never treated as a current check', async ({
  page,
}, info) => {
  let posts = 0
  const old = Date.now() / 1000 - 2 * 86400
  await page.route('**/api/manage/websites/nodeseek/connection-test', (route) => {
    if (route.request().method() === 'POST') posts += 1
    return route.fulfill({
      json: {
        started_at: old,
        finished_at: old + 1,
        next_attempt_at: old + 3,
        status: 'success',
        code: null,
        item_count: 20,
      },
    })
  })
  await page.goto('/#/websites')
  const open = () => page.getByRole('button', { name: '配置 NodeSeek', exact: true }).click()
  await open()
  const panel = page.locator('.website-drawer')
  const history = panel.locator('.connection-history')
  await expect(history.locator('summary')).toContainText('上次测试 · 成功')
  await expect(history).not.toHaveAttribute('open', '')
  await expect(panel.locator('.match-result.yes')).toHaveCount(0)
  await expect(panel.getByText('本次尚未测试', { exact: false })).toBeVisible()
  await expect(panel.locator('.connection-cooldown')).toHaveCount(0)
  await history.locator('summary').click()
  await expect(history).toContainText('有效帖子 20 条')
  await expect(history).toContainText('仅代表当时的检查结果')
  await page.screenshot({ path: info.outputPath('connection-history.png'), fullPage: true })
  await panel.press('Escape')
  await open()
  await expect(history.locator('summary')).toContainText('上次测试 · 成功')
  await expect(history).not.toHaveAttribute('open', '')
  await panel.getByRole('button', { name: '测试连接', exact: true }).click()
  await page
    .getByRole('dialog', { name: '测试 NodeSeek 官方 RSS 连接？' })
    .getByRole('button', { name: '取消', exact: true })
    .click()
  expect(posts).toBe(0)
  await expect(panel.locator('.match-result.yes')).toHaveCount(0)
})

test('new checks replace old success and HTTP errors cannot leave a green result', async ({
  page,
}) => {
  await page.clock.install()
  const now = Date.now() / 1000
  let attempts = 0
  let release!: () => void
  const response = new Promise<void>((resolve) => {
    release = resolve
  })
  await page.route('**/api/manage/websites/linuxdo/connection-test', async (route) => {
    if (route.request().method() !== 'POST')
      return route.fulfill({
        json: {
          started_at: now - 86400,
          finished_at: now - 86400,
          next_attempt_at: now - 86340,
          status: 'success',
          code: null,
          item_count: 20,
        },
      })
    attempts += 1
    if (attempts === 1)
      return route.fulfill({
        json: {
          started_at: now,
          finished_at: now,
          next_attempt_at: now + 60,
          status: 'success',
          code: null,
          item_count: 1,
        },
      })
    await response
    return route.fulfill({
      status: 429,
      headers: { 'Retry-After': '60' },
      json: { detail: '连接测试每 60 秒最多一次；约 60 秒后可再次测试。' },
    })
  })
  await page.goto('/#/websites')
  await page.getByRole('button', { name: '配置 LINUX DO', exact: true }).click()
  const panel = page.locator('.website-drawer')
  await expect(panel.locator('.connection-history')).toBeVisible()
  const check = async () => {
    await panel.getByRole('button', { name: '测试连接', exact: true }).click()
    await page.getByRole('button', { name: '确认测试连接', exact: true }).click()
  }
  await check()
  await expect(panel.locator('.match-result.yes')).toContainText('有效帖子 1 条')
  await expect(panel.locator('.connection-cooldown')).toBeVisible()
  await check()
  try {
    await expect(panel.getByRole('button', { name: '测试中…', exact: true })).toBeDisabled()
    await expect(panel.getByText('正在检查 RSS 连接与解析…', { exact: true })).toBeVisible()
    await expect(panel.locator('.match-result')).toHaveCount(0)
  } finally {
    release()
  }
  await expect(panel.getByRole('alert')).toContainText('连接测试每 60 秒最多一次')
  await expect(panel.locator('.match-result.yes')).toHaveCount(0)
  await expect(panel.locator('.connection-history')).not.toHaveAttribute('open', '')
  await page.clock.fastForward(61_000)
  await expect(panel.locator('.connection-cooldown')).toHaveCount(0)
  expect(attempts).toBe(2)
})

test('late history and a check completed after closing cannot overwrite a new panel', async ({
  page,
}) => {
  const now = Date.now() / 1000
  let reads = 0
  let posts = 0
  let releaseHistory!: () => void
  let releasePost!: () => void
  const historyResponse = new Promise<void>((resolve) => {
    releaseHistory = resolve
  })
  const postResponse = new Promise<void>((resolve) => {
    releasePost = resolve
  })
  await page.route('**/api/manage/websites/nodeseek/connection-test', async (route) => {
    if (route.request().method() === 'GET') {
      reads += 1
      if (reads === 1) await historyResponse
      return route.fulfill({
        json: {
          started_at: now - 86400,
          finished_at: now - 86400,
          next_attempt_at: now - 86398,
          status: 'failure',
          code: 'http_403',
          item_count: null,
        },
      })
    }
    posts += 1
    if (posts === 2) await postResponse
    return route.fulfill({
      json: {
        started_at: now,
        finished_at: now,
        next_attempt_at: now + 2,
        status: 'success',
        code: null,
        item_count: 1,
      },
    })
  })
  await page.goto('/#/websites')
  const open = () => page.getByRole('button', { name: '配置 NodeSeek', exact: true }).click()
  const panel = page.locator('.website-drawer')
  const check = async () => {
    await panel.getByRole('button', { name: '测试连接', exact: true }).click()
    await page.getByRole('button', { name: '确认测试连接', exact: true }).click()
  }
  await open()
  await expect.poll(() => reads).toBe(1)
  await check()
  await expect(panel.locator('.match-result.yes')).toBeVisible()
  const historyArrived = page.waitForResponse(
    (res) => res.url().endsWith('/nodeseek/connection-test') && res.request().method() === 'GET',
  )
  releaseHistory()
  await historyArrived
  await expect(panel.locator('.match-result.yes')).toBeVisible()
  await expect(panel.locator('.connection-history')).toHaveCount(0)
  await check()
  await expect(panel.getByRole('button', { name: '测试中…', exact: true })).toBeDisabled()
  await panel.press('Escape')
  await open()
  await expect(panel.locator('.connection-history summary')).toContainText('上次测试 · 失败')
  const postArrived = page.waitForResponse(
    (res) => res.url().endsWith('/nodeseek/connection-test') && res.request().method() === 'POST',
  )
  releasePost()
  await postArrived
  await expect(panel.locator('.match-result.yes')).toHaveCount(0)
  await expect(panel.getByRole('button', { name: '测试连接', exact: true })).toBeEnabled()
  await panel.locator('.connection-history summary').click()
  await expect(panel.locator('.connection-history')).toContainText('当时拒绝访问（403）')
  await expect(panel.locator('.connection-history')).not.toContainText('正在退避')
  expect(posts).toBe(2)
})
