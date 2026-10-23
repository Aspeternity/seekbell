import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const credentials = { username: 'history_admin', password: 'Synthetic-History-2026' }
function gate() {
  let release = () => {}
  const promise = new Promise<void>((resolve) => (release = resolve))
  return { promise, release }
}
async function navigate(page: Page, path: string) {
  await page.evaluate((path) => (location.hash = path), path)
}
async function login(page: Page) {
  await page.route('**/*', (route) => {
    if (new URL(route.request().url()).hostname !== '127.0.0.1')
      throw new Error('Unexpected external request')
    return route.continue()
  })
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
  await expect(page.getByTestId('overview-matches')).toContainText('24条')
}

test('content requests start immediately, share one delayed indicator and isolate cached queries', async ({
  page,
}, info) => {
  await login(page)
  await page.clock.install()
  await page.clock.pauseAt(new Date())
  const initial = gate()
  let started = 0
  for (const pattern of [
    '**/api/manage/history/options',
    /\/api\/manage\/history\/posts(?:\?|$)/,
  ]) {
    await page.route(pattern, async (route) => {
      const response = await route.fetch()
      started++
      await initial.promise
      await route.fulfill({ response })
    })
  }
  await navigate(page, '/content')
  // With browser time paused, reaching both requests proves there is no initial 180ms delay.
  await expect.poll(() => started).toBe(2)
  await expect(page.locator('.remote-feedback')).toHaveCount(0)
  await page.clock.runFor(199)
  await expect(page.locator('.remote-feedback')).toHaveCount(0)
  await page.clock.runFor(1)
  await expect(page.locator('.remote-feedback')).toHaveCount(1)
  await expect(page.locator('.remote-feedback')).toHaveText('加载中…')
  initial.release()
  await expect(page.locator('.content-row')).toHaveCount(20)
  await expect(page.locator('.remote-feedback')).toHaveCount(0)
  await page.clock.resume()

  const refresh = gate()
  let refreshStarted = false
  let fail = true
  await page.route(/\/api\/manage\/history\/posts(?:\?|$)/, async (route) => {
    const response = await route.fetch()
    refreshStarted = true
    await refresh.promise
    if (fail) return route.fulfill({ status: 503, json: { detail: '合成内容刷新失败' } })
    return route.fulfill({ response })
  })
  await navigate(page, '/tasks')
  await navigate(page, '/content')
  await expect.poll(() => refreshStarted).toBe(true)
  await expect(page.locator('.content-row')).toHaveCount(20)
  await expect(page.locator('.remote-feedback')).toHaveText('正在更新…')
  await page.screenshot({ path: info.outputPath('content-background-refresh.png'), fullPage: true })
  refresh.release()
  await expect(page.getByRole('alert')).toContainText('合成内容刷新失败')
  await expect(page.getByRole('alert')).toContainText('刷新失败，当前显示上次结果。')
  await expect(page.locator('.content-row')).toHaveCount(20)
  fail = false
  await page.getByRole('button', { name: '重新加载', exact: true }).click()
  await expect(page.getByRole('alert')).toHaveCount(0)
  await expect(page.locator('.remote-feedback')).toHaveCount(0)

  const filter = gate()
  let filterStarted = false
  await page.route(/\/api\/manage\/history\/posts(?:\?|$)/, async (route) => {
    if (new URL(route.request().url()).searchParams.get('q') !== '%_') return route.fallback()
    const response = await route.fetch()
    filterStarted = true
    await filter.promise
    await route.fulfill({ response })
  })
  await page.getByLabel('搜索内容').fill('%_')
  await expect.poll(() => filterStarted).toBe(true)
  await expect(page.locator('.content-row')).toHaveCount(20)
  await expect(page.locator('.read-snapshot')).toHaveAttribute('inert', '')
  await expect(page.locator('.empty-state')).toHaveCount(0)
  await expect(page.locator('.remote-feedback')).toHaveCount(1)
  filter.release()
  await expect(page.locator('.content-row')).toHaveCount(1)
  await expect(page.locator('.content-row')).toContainText('<img src=x')
  await page.getByLabel('搜索内容').fill('')
  await expect(page.locator('.content-row')).toHaveCount(20)
  expect(
    await page.evaluate(() =>
      Object.keys(localStorage).filter((key) => key.startsWith('seekbell')),
    ),
  ).toEqual([])
})

test('overview keeps results on refresh errors and logout discards cache and late responses', async ({
  page,
}, info) => {
  await login(page)
  await navigate(page, '/content')
  await expect(page.locator('.content-row')).toHaveCount(20)

  const overview = gate()
  let began = false
  let fail = true
  await page.route('**/api/manage/overview?*', async (route) => {
    const response = await route.fetch()
    began = true
    await overview.promise
    if (fail) return route.fulfill({ status: 503, json: { detail: '合成概览刷新失败' } })
    const data = await response.json()
    data.window.matches = 42
    return route.fulfill({ json: data })
  })
  await navigate(page, '/')
  await expect.poll(() => began).toBe(true)
  await expect(page.getByTestId('overview-matches')).toContainText('24条')
  await expect(page.locator('.remote-feedback')).toHaveText('正在更新…')
  overview.release()
  await expect(page.getByRole('alert')).toContainText('合成概览刷新失败')
  await expect(page.getByRole('alert')).toContainText('刷新失败，当前显示上次结果。')
  await expect(page.getByTestId('overview-matches')).toContainText('24条')
  fail = false
  await page.getByRole('button', { name: '重新加载', exact: true }).click()
  await expect(page.getByTestId('overview-matches')).toContainText('42条')
  await expect(page.getByRole('alert')).toHaveCount(0)

  const range = gate()
  let rangeBegan = false
  await page.route('**/api/manage/overview?range=7d', async (route) => {
    const response = await route.fetch()
    rangeBegan = true
    await range.promise
    await route.fulfill({ response })
  })
  await page.getByRole('button', { name: '7 天', exact: true }).click()
  await expect.poll(() => rangeBegan).toBe(true)
  await expect(page.locator('.stats-grid')).toHaveCount(1)
  await expect(page.locator('.read-snapshot')).toHaveAttribute('aria-label', /上次结果/)
  await expect(page.locator('.remote-feedback')).toContainText('上次结果')
  range.release()
  await expect(page.locator('.chart-point')).toHaveCount(7)

  // Hold a successful response across logout; it must not repopulate session memory.
  const late = gate()
  let lateBegan = false
  await page.route(/\/api\/manage\/history\/posts(?:\?|$)/, async (route) => {
    const response = await route.fetch()
    lateBegan = true
    await late.promise
    await route.fulfill({ response })
  })
  await navigate(page, '/content')
  await expect.poll(() => lateBegan).toBe(true)
  await expect(page.locator('.content-row')).toHaveCount(20)
  if (info.project.name === 'mobile')
    await page.getByRole('button', { name: '打开导航', exact: true }).click()
  await page.locator('.profile-logout').click()
  await expect(page.getByRole('button', { name: '登录工作空间' })).toBeVisible()
  late.release()

  const fresh = gate()
  let freshOverview = false
  await page.route('**/api/manage/overview?*', async (route) => {
    const response = await route.fetch()
    freshOverview = true
    await fresh.promise
    await route.fulfill({ response })
  })
  await page.getByLabel('管理员用户名').fill(credentials.username)
  await page.getByLabel('密码', { exact: true }).fill(credentials.password)
  await page.getByRole('button', { name: '登录工作空间', exact: true }).click()
  await expect.poll(() => freshOverview).toBe(true)
  await expect(page.locator('.stats-grid')).toHaveCount(0)
  fresh.release()
  await expect(page.getByTestId('overview-matches')).toContainText('24条')

  const freshContent = gate()
  let freshContentBegan = false
  await page.route(/\/api\/manage\/history\/posts(?:\?|$)/, async (route) => {
    const response = await route.fetch()
    freshContentBegan = true
    await freshContent.promise
    await route.fulfill({ response })
  })
  await navigate(page, '/content')
  await expect.poll(() => freshContentBegan).toBe(true)
  await expect(page.locator('.content-row')).toHaveCount(0)
  freshContent.release()
  await expect(page.locator('.content-row')).toHaveCount(20)
  await page.screenshot({ path: info.outputPath('content-fresh-session.png'), fullPage: true })
})
