import { expect, test, type Page } from '@playwright/test'
import { selectChoice } from '../select'
const credentials = { username: 'first_entry_admin', password: 'Synthetic-Stability-2026' }
function gate() {
  let release = () => {}
  const promise = new Promise<void>((resolve) => (release = resolve))
  return { promise, release }
}
async function login(page: Page) {
  await page.route('**/*', (route) => {
    if (new URL(route.request().url()).hostname !== '127.0.0.1')
      throw Error('Unexpected external request')
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
    .getByRole('button', { name: initialized ? '登录工作空间' : '创建管理员并进入', exact: true })
    .click()
  await expect(page.getByTestId('overview-matches')).toContainText('24条')
}
async function nav(page: Page, path: string) {
  await page.evaluate((path) => (location.hash = path), path)
}

test('cold notification menus commit complete panes and preloads merge without exposing placeholder frames', async ({
  page,
}, info) => {
  await login(page)
  const held = { deliveries: gate(), manual: gate(), tests: gate() }
  const requests: Record<string, number> = { deliveries: 0, manual: 0, tests: 0, options: 0 }
  await page.route(
    /\/api\/manage\/history\/(deliveries|manual|tests|options)(?:\?|$)/,
    async (route) => {
      const tab = new URL(route.request().url()).pathname.split('/').at(-1)!
      requests[tab]++
      const response = await route.fetch()
      if (tab in held) await held[tab as keyof typeof held].promise
      await route.fulfill({ response })
    },
  )
  await nav(page, '/notifications/targets')
  const tabs = page.getByRole('navigation', { name: '通知管理分类' })
  await expect(tabs).toBeVisible()
  await expect.poll(() => requests).toEqual({ deliveries: 1, manual: 1, tests: 1, options: 1 })
  await page.evaluate(() => {
    ;(window as any).__coldFrames = []
    ;(window as any).__coldSampling = true
    const sample = () => {
      if (!(window as any).__coldSampling) return
      ;(window as any).__coldFrames.push({
        placeholder: document.querySelectorAll('.read-placeholder').length,
        active: document.querySelector('[aria-label="通知管理分类"] [aria-current="page"]')
          ?.textContent,
        rows: document.querySelectorAll('.delivery-row').length,
      })
      requestAnimationFrame(sample)
    }
    requestAnimationFrame(sample)
  })
  await tabs.getByRole('button', { name: /^投递记录/ }).click()
  await expect(tabs.getByRole('button', { name: /^通知目标/ })).toHaveAttribute(
    'aria-current',
    'page',
  )
  await expect(page.getByRole('textbox', { name: '搜索通知目标', exact: true })).toBeVisible()
  await expect(page.locator('.notification-switch-feedback')).toContainText('正在读取投递记录')
  await expect(page.locator('.read-placeholder')).toHaveCount(0)
  held.deliveries.release()
  await expect(page.locator('.delivery-row')).toHaveCount(20)
  await expect(tabs.getByRole('button', { name: /^投递记录/ })).toHaveAttribute(
    'aria-current',
    'page',
  )
  await tabs.getByRole('button', { name: /^手动重发/ }).click()
  await expect(tabs.getByRole('button', { name: /^投递记录/ })).toHaveAttribute(
    'aria-current',
    'page',
  )
  await expect(page.locator('.delivery-row')).toHaveCount(20)
  held.manual.release()
  await expect(tabs.getByRole('button', { name: /^手动重发/ })).toHaveAttribute(
    'aria-current',
    'page',
  )
  await expect(page.getByRole('heading', { name: '这里还没有记录' })).toBeVisible()
  await tabs.getByRole('button', { name: /^测试记录/ }).click()
  await expect(tabs.getByRole('button', { name: /^手动重发/ })).toHaveAttribute(
    'aria-current',
    'page',
  )
  held.tests.release()
  await expect(page.locator('.delivery-row')).toHaveCount(2)
  await expect(tabs.getByRole('button', { name: /^测试记录/ })).toHaveAttribute(
    'aria-current',
    'page',
  )
  const frames = await page.evaluate(() => {
    ;(window as any).__coldSampling = false
    return (window as any).__coldFrames as { placeholder: number; active: string; rows: number }[]
  })
  expect(frames.length).toBeGreaterThan(3)
  expect(frames.every((frame) => frame.placeholder === 0)).toBe(true)
  expect(frames.every((frame) => !frame.active?.includes('手动重发') || frame.rows === 0)).toBe(
    true,
  )
  expect(frames.every((frame) => !frame.active?.includes('测试记录') || frame.rows === 2)).toBe(
    true,
  )
  expect(requests).toEqual({ deliveries: 1, manual: 1, tests: 1, options: 1 })
  await page.screenshot({ path: info.outputPath('cold-notification-complete.png') })
})

test('cold menu failures retain the original pane, retry once, and rapid navigation rejects late commits', async ({
  page,
}) => {
  await login(page)
  const manual = gate(),
    tests = gate()
  let first = true,
    began = false
  await page.route(/\/api\/manage\/history\/manual(?:\?|$)/, async (route) => {
    began = true
    if (first) return route.fulfill({ status: 503, json: { detail: '合成读取失败' } })
    const response = await route.fetch()
    await manual.promise
    await route.fulfill({ response })
  })
  await page.route(/\/api\/manage\/history\/tests(?:\?|$)/, async (route) => {
    const response = await route.fetch()
    await tests.promise
    await route.fulfill({ response })
  })
  await nav(page, '/notifications/targets')
  const tabs = page.getByRole('navigation', { name: '通知管理分类' })
  await expect.poll(() => began).toBe(true)
  await tabs.getByRole('button', { name: /^手动重发/ }).click()
  await expect(page.locator('.notification-switch-feedback').getByRole('alert')).toContainText(
    '合成读取失败',
  )
  await expect(tabs.getByRole('button', { name: /^通知目标/ })).toHaveAttribute(
    'aria-current',
    'page',
  )
  first = false
  await page
    .locator('.notification-switch-feedback')
    .getByRole('button', { name: '重新加载' })
    .click()
  await tabs.getByRole('button', { name: /^测试记录/ }).click()
  manual.release()
  await expect(tabs.getByRole('button', { name: /^通知目标/ })).toHaveAttribute(
    'aria-current',
    'page',
  )
  tests.release()
  await expect(tabs.getByRole('button', { name: /^测试记录/ })).toHaveAttribute(
    'aria-current',
    'page',
  )
  await expect(page.locator('.delivery-row')).toHaveCount(2)
  await expect(page.locator('.notification-switch-feedback').getByRole('alert')).toHaveCount(0)
})

test('short labels fit with classic scrollbar geometry and wide toolbars allocate usable filter widths', async ({
  page,
}, info) => {
  await login(page)
  await page.route(/\/api\/manage\/history\/options(?:\?|$)/, async (route) => {
    const response = await route.fetch()
    const json = await response.json()
    json.category_options = Array.from({ length: 12 }, (_, i) => ({
      website_id: 'nodeseek',
      value: 'synthetic-' + i,
      label: '版块' + i,
    }))
    await route.fulfill({ response, json })
  })
  await page.addStyleTag({
    content:
      '.app-select-menu {scrollbar-gutter:stable} .app-select-menu::-webkit-scrollbar {width:15px}',
  })
  await nav(page, '/content')
  if (info.project.name === 'desktop') {
    const result = await page.getByRole('combobox', { name: '匹配结果', exact: true }).boundingBox()
    const date = await page.getByRole('button', { name: '发现日期', exact: true }).boundingBox()
    expect(Math.abs(result!.y - date!.y)).toBeLessThan(1)
  }
  const category = page.getByRole('combobox', { name: '版块筛选', exact: true })
  await category.click()
  const menu = page.getByRole('listbox', { name: '版块筛选', exact: true })
  await expect(menu.getByRole('option')).toHaveCount(13)
  const geometry = await menu
    .getByRole('option', { name: '全部版块', exact: true })
    .locator('span')
    .evaluate((el) => ({
      height: el.getBoundingClientRect().height,
      line: parseFloat(getComputedStyle(el).lineHeight),
      scale: parseFloat(getComputedStyle(document.querySelector('.app-select-popover')!).zoom) || 1,
    }))
  expect(geometry.height).toBeLessThanOrEqual(geometry.line * geometry.scale + 1)
  const rect = (await menu.boundingBox())!
  expect(rect.width).toBeGreaterThanOrEqual(159)
  expect(rect.x).toBeGreaterThanOrEqual(0)
  expect(rect.x + rect.width).toBeLessThanOrEqual(page.viewportSize()!.width + 1)
  await page.screenshot({ path: info.outputPath('category-one-line.png') })
  await page.keyboard.press('Escape')
  for (const name of ['匹配结果', '关联任务', '历史网站', '版块筛选']) {
    const label = page.getByRole('combobox', { name, exact: true }).locator('.app-select-label')
    expect(await label.evaluate((el) => el.scrollWidth <= el.clientWidth + 1)).toBe(true)
  }
  await nav(page, '/notifications/targets')
  const channel = page.getByRole('combobox', { name: '通知渠道筛选', exact: true })
  await selectChoice(channel, 'telegram')
  await expect(channel).toHaveText('Telegram Bot')
  expect(
    await channel
      .locator('.app-select-label')
      .evaluate((el) => el.scrollWidth <= el.clientWidth + 1),
  ).toBe(true)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('channel-label-complete.png') })
})

test('direct record entry starts immediately and delays every loading visual until 200ms', async ({
  page,
}) => {
  await login(page)
  const held = gate()
  let began = false
  await page.route(/\/api\/manage\/history\/deliveries(?:\?|$)/, async (route) => {
    const response = await route.fetch()
    began = true
    await held.promise
    await route.fulfill({ response })
  })
  await page.clock.install()
  await page.clock.pauseAt(new Date())
  await nav(page, '/notifications/deliveries')
  await expect.poll(() => began).toBe(true)
  await expect(page.locator('.read-placeholder')).toHaveCount(0)
  await expect(page.locator('.remote-feedback')).toHaveCount(0)
  await page.clock.runFor(199)
  await expect(page.locator('.read-placeholder')).toHaveCount(0)
  await expect(page.locator('.remote-feedback')).toHaveCount(0)
  await page.clock.runFor(1)
  await expect(page.locator('.read-placeholder')).toBeVisible()
  await expect(page.locator('.remote-feedback')).toContainText('加载中')
  held.release()
  await expect(page.locator('.delivery-row')).toHaveCount(20)
  await expect(page.locator('.read-placeholder')).toHaveCount(0)
  await page.clock.resume()
})
