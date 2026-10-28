import { selectChoice, readChoices } from '../select'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const credentials = { username: 'history_admin', password: 'Synthetic-History-2026' }
function gate() {
  let release = () => {}
  const promise = new Promise<void>((resolve) => (release = resolve))
  return { promise, release }
}
async function pauseClock(page: Page) {
  const pausedAt = new Date()
  // Install before the pause target so process latency cannot put it in the past.
  await page.clock.install({ time: new Date(pausedAt.getTime() - 60_000) })
  await page.clock.pauseAt(pausedAt)
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

test('content filters preserve geometry, task notes are inset and post details avoid loading flashes', async ({
  page,
}, info) => {
  await login(page)
  await navigate(page, '/content')
  await expect(page.locator('.content-row')).toHaveCount(20)
  const search = page.getByLabel('搜索内容', { exact: true })
  await page.evaluate(() => window.scrollTo(0, 150))
  const start = (await search.boundingBox())!
  const hold = gate()
  let started = false
  await page.route(/\/api\/manage\/history\/posts(?:\?|$)/, async (route) => {
    if (new URL(route.request().url()).searchParams.get('q') !== 'uncached-layout-query')
      return route.continue()
    const response = await route.fetch()
    started = true
    await hold.promise
    await route.fulfill({ response })
  })
  await search.fill('uncached-layout-query')
  await expect.poll(() => started).toBe(true)
  await expect(page.locator('.metric-strip')).toHaveCount(1)
  expect(Math.abs((await search.boundingBox())!.y - start.y)).toBeLessThan(1)
  await expect(page.locator('.content-row')).toHaveCount(20)
  hold.release()
  await expect(page.getByText('没有符合条件的内容', { exact: true })).toBeVisible()
  await search.fill('')
  await expect(page.locator('.content-row')).toHaveCount(20)
  const selectHold = gate()
  let selectStarted = false
  await page.route(/\/api\/manage\/history\/posts(?:\?|$)/, async (route) => {
    if (new URL(route.request().url()).searchParams.get('status') !== 'no_match')
      return route.fallback()
    const response = await route.fetch()
    selectStarted = true
    await selectHold.promise
    await route.fulfill({ response })
  })
  const beforeSelect = (await search.boundingBox())!
  await selectChoice(page.getByLabel('匹配结果', { exact: true }), 'no_match')
  await expect.poll(() => selectStarted).toBe(true)
  await expect(page.locator('.metric-strip')).toHaveCount(1)
  expect(Math.abs((await search.boundingBox())!.y - beforeSelect.y)).toBeLessThan(1)
  selectHold.release()
  await expect(page.locator('.content-row')).toHaveCount(1)
  await selectChoice(page.getByLabel('匹配结果', { exact: true }), 'all')
  await expect(page.locator('.content-row')).toHaveCount(20)
  await selectChoice(page.getByLabel('关联任务', { exact: true }), { label: '当前任务名称' })
  const note = page.getByText('匹配结果按所选任务的历史判定筛选；详情可查看其他任务。', {
    exact: true,
  })
  await expect(note).toBeVisible()
  const inset = await note.evaluate((el) => {
    const range = document.createRange()
    range.selectNodeContents(el)
    const box = range.getBoundingClientRect()
    const panel = el.closest('.panel')!.getBoundingClientRect()
    return box.left - panel.left
  })
  expect(inset).toBeGreaterThan(12)
  await page.screenshot({ path: info.outputPath('content-task-note.png'), fullPage: true })
  await selectChoice(page.getByLabel('关联任务', { exact: true }), '')
  await expect(page.locator('.content-row')).toHaveCount(20)
  const detail = gate()
  let detailStarted = false
  await page.route(/\/api\/manage\/history\/posts\/[^/?]+$/, async (route) => {
    const response = await route.fetch()
    detailStarted = true
    await detail.promise
    await route.fulfill({ response })
  })
  await pauseClock(page)
  await page.locator('.content-title').first().click()
  await expect.poll(() => detailStarted).toBe(true)
  await expect(page.getByText('正在读取服务端记录…', { exact: true })).toHaveCount(0)
  await page.clock.runFor(199)
  await expect(page.locator('.remote-feedback')).toHaveCount(0)
  await page.clock.runFor(1)
  await expect(page.locator('.remote-feedback')).toContainText('加载中…')
  detail.release()
  await expect(page.getByRole('heading', { name: '命中依据' })).toBeVisible()
  await expect(page.locator('.remote-feedback')).toHaveCount(0)
  await page.clock.resume()
})

test('approved date ranges cover all four lists, compose with filters and cancel without applying', async ({
  page,
}, info) => {
  await login(page)
  for (const tab of ['posts', 'deliveries', 'manual', 'tests']) {
    const path = tab === 'posts' ? '/content' : '/notifications/' + tab
    const label = tab === 'posts' ? '发现日期' : '记录日期'
    await navigate(page, path)
    const date = page.getByRole('button', { name: label, exact: true })
    await expect(date).toHaveText('全部日期')
    const requests: URL[] = []
    const capture = (request: import('@playwright/test').Request) => {
      const url = new URL(request.url())
      if (url.pathname === '/api/manage/history/' + tab) requests.push(url)
    }
    page.on('request', capture)
    await date.click()
    const menu = page.getByRole('dialog', { name: label + '范围', exact: true })
    await expect(menu).toBeVisible()
    await date.click()
    await expect(menu).toHaveCount(0)
    await date.click()
    await expect(menu).toBeVisible()
    await menu.getByRole('button', { name: '应用', exact: true }).focus()
    await menu.getByRole('button', { name: '应用', exact: true }).press('Tab')
    await expect(menu).toHaveCount(0)
    await date.click()
    await expect(menu.getByLabel('开始日期')).toBeFocused()
    const menuBox = (await menu.boundingBox())!
    expect(menuBox.x).toBeGreaterThanOrEqual(0)
    expect(menuBox.x + menuBox.width).toBeLessThanOrEqual(page.viewportSize()!.width + 1)
    await page.screenshot({ path: info.outputPath('date-popup-' + tab + '.png'), fullPage: false })
    const before = requests.length
    await menu.getByLabel('开始日期').fill('2026-10-18')
    await menu.getByLabel('结束日期').fill('2026-10-19')
    await menu.getByRole('button', { name: '取消', exact: true }).click()
    await expect(menu).toHaveCount(0)
    await expect(date).toHaveText('全部日期')
    expect(requests).toHaveLength(before)

    const search = page.getByLabel(tab === 'posts' ? '搜索内容' : '搜索投递记录', { exact: true })
    await search.fill(tab === 'posts' ? '%_' : '历史')
    await expect.poll(() => requests.some((url) => url.searchParams.has('q'))).toBe(true)
    const status = page.getByLabel(tab === 'posts' ? '匹配结果' : '投递状态筛选', { exact: true })
    const filter = tab === 'posts' ? 'match' : tab === 'deliveries' ? 'pending' : 'success'
    await selectChoice(status, filter)
    await expect
      .poll(() => requests.some((url) => url.searchParams.get('status') === filter))
      .toBe(true)
    if (tab === 'posts') {
      await search.fill('')
      await selectChoice(status, 'all')
      await expect(page.locator('.content-row')).toHaveCount(20)
      await page.getByRole('button', { name: '下一页内容', exact: true }).click()
      await expect.poll(() => requests.at(-1)?.searchParams.get('page')).toBe('2')
    }
    await date.click()
    await menu.getByRole('button', { name: '应用', exact: true }).click()
    await expect(menu.getByRole('alert')).toContainText('开始日期和结束日期')
    await menu.getByLabel('开始日期').fill('2026-10-20')
    await menu.getByLabel('结束日期').fill('2026-10-19')
    await menu.getByRole('button', { name: '应用', exact: true }).click()
    await expect(menu.getByRole('alert')).toContainText('不能晚于')
    await menu.getByLabel('开始日期').fill('2026-10-18')
    const response = page.waitForResponse((response) => {
      const url = new URL(response.url())
      return (
        url.pathname === '/api/manage/history/' + tab &&
        url.searchParams.get('date_from') === '2026-10-18'
      )
    })
    const geometry = await search.boundingBox()
    await menu.getByRole('button', { name: '应用', exact: true }).click()
    const applied = await response
    expect(applied.ok()).toBe(true)
    const params = new URL(applied.url()).searchParams
    expect(params.get('date_to')).toBe('2026-10-19')
    expect(params.get('page')).toBe('1')
    expect(params.get('status')).toBe(tab === 'posts' ? 'all' : filter)
    expect(params.get('q')).toBe(tab === 'posts' ? null : '历史')
    expect(params.has('discovered_on')).toBe(false)
    await expect(date).toHaveText('2026/10/18 – 2026/10/19')
    expect(Math.abs((await search.boundingBox())!.width - geometry!.width)).toBeLessThan(1)
    await date.click()
    await menu.getByLabel('开始日期').fill('2026-10-19')
    await menu.getByRole('button', { name: '应用', exact: true }).click()
    await expect(date).toHaveText('2026/10/19')
    await date.click()
    await menu.getByLabel('开始日期').fill('2020-01-01')
    await menu.getByLabel('结束日期').fill('2020-01-02')
    await menu.getByRole('button', { name: '应用', exact: true }).click()
    await expect(page.locator('.content-row, .delivery-row')).toHaveCount(0)
    await expect(page.locator('.empty-state')).toBeVisible()
    await page.screenshot({ path: info.outputPath('date-range-' + tab + '.png'), fullPage: true })
    await date.click()
    await expect(menu.getByLabel('开始日期')).toHaveValue('2020-01-01')
    await menu.getByRole('button', { name: '清除', exact: true }).click()
    await expect(date).toHaveText('全部日期')
    await date.click()
    await menu.getByLabel('开始日期').fill('2020-01-01')
    await menu.getByLabel('开始日期').press('Escape')
    await expect(menu).toHaveCount(0)
    await expect(date).toBeFocused()
    await expect(date).toHaveText('全部日期')
    await date.click()
    await page.mouse.click(page.viewportSize()!.width - 2, 2)
    await expect(menu).toHaveCount(0)
    page.off('request', capture)
  }
  await navigate(page, '/content')
  expect((await readChoices(page.getByLabel('关联任务'))).join('')).not.toContain('已删除')
  await navigate(page, '/websites')
  const input = page.getByLabel('搜索已添加网站')
  const shell = page.locator('.search-input').filter({ has: input })
  const status = page.getByRole('combobox', { name: '筛选网站状态' })
  const searchBox = (await shell.boundingBox())!
  const selectBox = (await status.boundingBox())!
  expect(Math.abs(searchBox.height - selectBox.height)).toBeLessThan(1)
  if (info.project.name === 'mobile') {
    await expect(input).toHaveCSS('font-size', '16px')
    expect(searchBox.width).toBeGreaterThan(selectBox.width)
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('notification counts are immediate, shared across tabs and retained during refresh failures', async ({
  page,
}) => {
  await login(page)
  const initial = gate()
  let started = 0
  let totals = { deliveries: 24, manual: 0, tests: 2 }
  let waiting: ReturnType<typeof gate> | undefined = initial
  let fail = false
  await page.route('**/api/manage/history/counts', async (route) => {
    started++
    const snapshot = { ...totals },
      hold = waiting
    if (hold) await hold.promise
    if (fail) return route.fulfill({ status: 503, json: { detail: '合成计数刷新失败' } })
    await route.fulfill({ json: snapshot })
  })
  await pauseClock(page)
  await navigate(page, '/notifications/targets')
  await expect.poll(() => started).toBe(1)
  const nav = page.getByRole('navigation', { name: '通知管理分类' })
  const deliveries = nav.getByRole('button', { name: /^投递记录/ }).locator('span')
  await expect(deliveries).toHaveText('')
  await expect(nav).not.toContainText('—')
  await nav.getByRole('button', { name: /^投递记录/ }).click()
  // Keep the first count request pending until the async tab transition commits.
  await expect(nav.getByRole('button', { name: /^投递记录/ })).toHaveAttribute(
    'aria-current',
    'page',
  )
  expect(started).toBe(1)
  waiting = undefined
  initial.release()
  await expect(deliveries).toHaveText('24')
  await page.clock.resume()

  const refresh = gate()
  waiting = refresh
  totals = { deliveries: 26, manual: 1, tests: 3 }
  await nav.getByRole('button', { name: /^手动重发/ }).click()
  await expect.poll(() => started).toBe(2)
  await expect(deliveries).toHaveText('24')
  await expect(nav).not.toContainText('—')
  waiting = undefined
  refresh.release()
  await expect(deliveries).toHaveText('26')

  fail = true
  await nav.getByRole('button', { name: /^测试记录/ }).click()
  await expect(page.getByRole('alert')).toContainText('合成计数刷新失败')
  await expect(deliveries).toHaveText('26')
  fail = false
  await page.getByRole('button', { name: '重新加载', exact: true }).click()
  await expect(page.getByRole('alert')).toHaveCount(0)
  await nav.getByRole('button', { name: /^通知目标/ }).click()
  await expect(page.locator('.notification-card')).toHaveCount(1)
  totals = { deliveries: 27, manual: 1, tests: 3 }
  const toggle = page.locator('.notification-card').getByRole('switch')
  await toggle.click()
  await expect(deliveries).toHaveText('27')
  await toggle.click()
  await expect(toggle).toHaveAttribute('aria-checked', 'true')
  const late = gate()
  waiting = late
  const previous = started
  await nav.getByRole('button', { name: /^投递记录/ }).click()
  await expect.poll(() => started).toBeGreaterThan(previous)
  if (page.viewportSize()!.width <= 760)
    await page.getByRole('button', { name: '打开导航', exact: true }).click()
  await page.locator('.profile-logout').click()
  await expect(page.getByRole('button', { name: '登录工作空间' })).toBeVisible()
  const fresh = gate()
  waiting = fresh
  totals = { deliveries: 31, manual: 2, tests: 4 }
  await page.getByLabel('管理员用户名').fill(credentials.username)
  await page.getByLabel('密码', { exact: true }).fill(credentials.password)
  await page.getByRole('button', { name: '登录工作空间', exact: true }).click()
  await expect(page.getByTestId('overview-matches')).toBeVisible()
  await navigate(page, '/notifications/targets')
  await expect(deliveries).toHaveText('')
  late.release()
  await expect(deliveries).toHaveText('')
  waiting = undefined
  fresh.release()
  await expect(deliveries).toHaveText('31')
})
