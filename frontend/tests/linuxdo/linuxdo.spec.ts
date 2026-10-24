import { expect, test, type Page } from '@playwright/test'
import { selectChoice } from '../select'

let cookies: Awaited<
  ReturnType<import('@playwright/test').APIRequestContext['storageState']>
>['cookies']
let csrf = ''
const errors = new WeakMap<Page, string[]>()
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
  await page.context().addCookies(cookies)
  const workspace = await (await page.request.get('/api/manage/workspace')).json()
  for (const task of workspace.tasks.filter((task: any) => task.website_id === 'linuxdo'))
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
  expect(reset.ok()).toBeTruthy()
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
  await selectChoice(picker, 'nodeseek')
  await page.getByText('更多匹配设置', { exact: true }).click()
  await page.getByLabel('包含作者', { exact: true }).fill('synthetic-user')
  await page.getByLabel('包含作者', { exact: true }).press('Enter')
  await selectChoice(picker, 'linuxdo')
  await expect(
    page.getByText('此网站 RSS 仅提供作者显示名，暂不支持精确用户名筛选。', { exact: true }),
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

test('late Linux DO replies cannot replace another sites current hotlist', async ({ page }) => {
  let release = () => {}
  const held = new Promise<void>((resolve) => (release = resolve))
  let started = false,
    finished = false
  await page.route('**/api/manage/hotlists/linuxdo?period=daily', async (route) => {
    const response = await route.fetch()
    started = true
    await held
    await route.fulfill({ response })
    finished = true
  })
  const hotlist = page.getByRole('region', { name: '社区热榜', exact: true })
  await hotlist.getByRole('button', { name: 'LINUX DO', exact: true }).click()
  await expect(hotlist.locator('.hotlist-row').first()).toContainText('LinuxDOhot')
  await hotlist.getByRole('button', { name: '每日', exact: true }).click()
  await expect.poll(() => started).toBe(true)
  await hotlist.getByRole('button', { name: 'NodeSeek', exact: true }).click()
  release()
  await expect.poll(() => finished).toBe(true)
  await expect(hotlist.locator('.hotlist-row').first()).toContainText('合成hot热榜帖子')
  await expect(hotlist.getByRole('button', { name: '实时', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  await page.unroute('**/api/manage/hotlists/linuxdo?period=daily')
})

test('Linux DO access errors are explicit and do not block NodeSeek', async ({ page }) => {
  await page.route('**/api/manage/hotlists/linuxdo?*', async (route) => {
    const response = await route.fetch()
    const data = await response.json()
    await route.fulfill({
      json: {
        ...data,
        items: [],
        status: 'unavailable',
        refreshing: false,
        error_code: 'access_challenge',
        fetched_at: null,
        source_updated_at: null,
        next_attempt_at: Date.now() / 1000 + 300,
      },
    })
  })
  const hotlist = page.getByRole('region', { name: '社区热榜', exact: true })
  await hotlist.getByRole('button', { name: 'LINUX DO', exact: true }).click()
  await expect(hotlist.getByText(/来源拒绝自动访问（403）/)).toBeVisible()
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

test('Linux DO loads only the selected period and automatically retries a short daily wait', async ({
  page,
}) => {
  const calls: string[] = []
  page.on('request', (request) => {
    const url = new URL(request.url())
    if (url.pathname === '/api/manage/hotlists/linuxdo')
      calls.push(url.searchParams.get('period') || '')
  })
  const hotlist = page.getByRole('region', { name: '社区热榜', exact: true })
  await hotlist.getByRole('button', { name: 'LINUX DO', exact: true }).click()
  await expect(hotlist.locator('.hotlist-row')).toHaveCount(5)
  await page.evaluate(
    () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
  )
  expect(calls.length).toBeGreaterThan(0)
  expect(calls.every((period) => period === 'hot')).toBe(true)
  let readyAt = 0
  await page.route('**/api/manage/hotlists/linuxdo?period=daily', async (route) => {
    const response = await route.fetch()
    const data = await response.json()
    if (!readyAt) readyAt = Date.now() + 1000
    if (Date.now() < readyAt)
      return route.fulfill({
        response,
        json: {
          ...data,
          status: 'waiting',
          error_code: 'source_cooldown',
          fetched_at: null,
          items: [],
          next_attempt_at: readyAt / 1000,
        },
      })
    return route.fulfill({ response, json: data })
  })
  await hotlist.getByRole('button', { name: '每日', exact: true }).click()
  await expect(
    hotlist.getByText('正在等待同站请求间隔，稍后自动重试。', { exact: true }),
  ).toBeVisible()
  await expect(hotlist.getByText('暂时无法获取榜单，请稍后重试。', { exact: true })).toHaveCount(0)
  await expect(hotlist.locator('.hotlist-row')).toHaveCount(5)
  await expect(hotlist.locator('.hotlist-row').first()).toContainText('LinuxDOdaily')
  expect(calls).not.toContain('weekly')
})
