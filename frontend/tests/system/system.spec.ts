import { selectChoice } from '../select'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
const credentials = { username: 'system_admin', password: 'Synthetic-System-2026' }
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
  await expect(page.locator('.sidebar')).toBeAttached()
  const headers = {
    'X-CSRF-Token': (await (await page.request.get('/api/auth/status')).json()).csrf,
  }
  return { headers, initialized }
}
test('browser timezone initializes once and the general editor preserves conflicts and calendar-day filters', async ({
  page,
  browser,
}, info) => {
  const { headers, initialized } = await login(page)
  const initial = await (await page.request.get('/api/manage/display')).json()
  if (!initialized) expect(initial.timezone).toBe('Asia/Tokyo')
  expect(
    (
      await page.request.put('/api/manage/display', {
        headers,
        data: { timezone: 'UTC', revision: initial.revision },
      })
    ).ok(),
  ).toBe(true)
  await page.reload()
  const before = await (await page.request.get('/api/manage/history/posts')).json()
  await page.goto('/#/settings/display')
  const input = page.getByLabel('显示时区', { exact: true })
  await expect(input).toHaveAttribute('data-value', 'UTC')
  await selectChoice(input, 'America/Los_Angeles')
  await page.evaluate(() => (location.hash = '/settings/account'))
  await expect(page.getByRole('dialog')).toContainText('尚未保存')
  await page.getByRole('button', { name: '继续编辑', exact: true }).click()
  const current = await (await page.request.get('/api/manage/display')).json()
  expect(
    (
      await page.request.put('/api/manage/display', {
        headers,
        data: { timezone: 'Asia/Tokyo', revision: current.revision },
      })
    ).ok(),
  ).toBe(true)
  await page.getByRole('button', { name: '保存通用设置', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('其他页面改变')
  await expect(input).toHaveAttribute('data-value', 'America/Los_Angeles')
  await page.getByRole('alert').getByRole('button', { name: '重新加载', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('尚未保存')
  await page.getByRole('button', { name: '放弃修改并读取', exact: true }).click()
  await expect(input).toHaveAttribute('data-value', 'Asia/Tokyo')
  await selectChoice(input, 'America/Los_Angeles')
  await page.route(
    '**/api/manage/preferences',
    (route) =>
      route.request().method() === 'PUT'
        ? route.fulfill({ status: 503, json: { detail: '合成时区保存失败' } })
        : route.continue(),
    { times: 1 },
  )
  await page.getByRole('button', { name: '保存通用设置', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('合成时区保存失败')
  await expect(input).toHaveAttribute('data-value', 'America/Los_Angeles')
  await page.getByRole('button', { name: '保存通用设置', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: '通用设置已保存' })).toBeVisible()
  expect(await (await page.request.get('/api/manage/history/posts')).json()).toEqual(before)
  await page.screenshot({ path: info.outputPath('timezone-settings.png'), fullPage: true })
  const context = await browser.newContext({ timezoneId: 'UTC' })
  try {
    const other = await context.newPage()
    await login(other)
    expect(
      (await (await other.request.get('/api/manage/workspace')).json()).settings.timezone,
    ).toBe('America/Los_Angeles')
  } finally {
    await context.close()
  }
  await page.goto('/#/content')
  await page.getByRole('button', { name: '发现日期', exact: true }).click()
  await page.getByLabel('开始日期', { exact: true }).fill('2026-10-18')
  await page.getByLabel('结束日期', { exact: true }).fill('2026-10-18')
  await page.getByRole('button', { name: '应用', exact: true }).click()
  await expect(page.locator('.content-row')).toHaveCount(1)
  await expect(page.locator('.content-row')).toContainText('时区边界夜帖')
  const utc = await (
    await page.request.get('/api/manage/history/posts?discovered_on=2026-10-18&timezone=UTC')
  ).json()
  expect(utc.total).toBe(0)
  await page.screenshot({ path: info.outputPath('timezone-day-filter.png'), fullPage: true })
})
test('confirmed independent alerts record a single fault and recovery even when all channels fail', async ({
  page,
}, info) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  const { headers } = await login(page)
  const settings = await (await page.request.get('/api/manage/alerts')).json()
  expect(
    (
      await page.request.put('/api/manage/alerts', {
        headers,
        data: { enabled: false, target_ids: [], revision: settings.revision },
      })
    ).ok(),
  ).toBe(true)
  const names = ['合成未知 ' + info.project.name, '合成失败 ' + info.project.name]
  const ids: string[] = []
  for (const name of names) {
    const response = await page.request.post('/api/manage/targets', {
      headers,
      data: {
        name,
        kind: 'webhook',
        enabled: true,
        config: { url: 'https://receiver.example.test/synthetic-system-secret' },
      },
    })
    expect(response.ok()).toBe(true)
    ids.push((await response.json()).id)
  }
  await page.reload()
  const before = await (await page.request.get('/api/manage/alerts/history')).json()
  await page.goto('/#/settings/alerts')
  await page.getByLabel('启用故障与恢复告警').click()
  for (const name of names) await page.getByRole('checkbox', { name: new RegExp(name) }).check()
  await page.getByRole('button', { name: '保存告警设置', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('不会补发过去事件')
  await page.getByRole('button', { name: '取消', exact: true }).click()
  expect((await (await page.request.get('/api/manage/alerts')).json()).enabled).toBe(false)
  await page.getByRole('button', { name: '保存告警设置', exact: true }).click()
  await page.getByRole('button', { name: '确认保存告警', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: '系统告警设置已保存' })).toBeVisible()
  expect((await page.request.delete('/api/manage/targets/' + ids[0], { headers })).status()).toBe(
    409,
  )
  expect(
    (
      await page.request.put('/api/manage/websites/nodeseek', {
        headers,
        data: { enabled: true, interval: 10 },
      })
    ).ok(),
  ).toBe(true)
  await expect
    .poll(async () => (await (await page.request.get('/api/manage/alerts/history')).json()).total)
    .toBe(before.total + 2)
  await expect
    .poll(async () => {
      const events = (
        await (await page.request.get('/api/manage/alerts/history')).json()
      ).items.slice(0, 2)
      return events.every(
        (event: any) => event.deliveries.unknown === 1 && event.deliveries.permanent_error === 1,
      )
    })
    .toBe(true)
  expect(
    (
      await page.request.put('/api/manage/websites/nodeseek', {
        headers,
        data: { enabled: false, interval: 10 },
      })
    ).ok(),
  ).toBe(true)
  const captured = await (await page.request.get('/api/manage/alerts/history')).json()
  expect(captured.items.slice(0, 2).map((event: any) => event.phase)).toEqual(['recovery', 'fault'])
  // Faults and alert records live under About & Diagnostics; settings stay on the alerts tab.
  await page.goto('/#/settings/about')
  await Promise.all([
    page.waitForResponse((response) =>
      response.url().includes('/api/manage/alerts/history?page=1'),
    ),
    page.getByRole('button', { name: '刷新运行信息', exact: true }).click(),
  ])
  await page.getByRole('button', { name: '查看系统告警记录', exact: true }).click()
  await expect(
    page
      .locator('.read-region')
      .filter({ has: page.locator('.system-event') })
      .first(),
  ).toHaveAttribute('aria-busy', 'false')
  await expect(page.getByText('当前没有已记录的故障。')).toBeVisible()
  const newest = page.locator('.system-event').first()
  await expect(newest).toContainText('恢复')
  await newest.getByRole('button', { name: '查看各目标结果' }).click()
  await expect(newest.locator('.alert-delivery')).toHaveCount(2)
  await expect(newest).toContainText('结果未知')
  await expect(newest).toContainText('明确拒绝')
  await expect(newest).toContainText('synthetic_timeout')
  const detail = await page.request.get('/api/manage/alerts/history/' + captured.items[0].id)
  expect(await detail.text()).not.toContain('synthetic-system-secret')
  await page.screenshot({ path: info.outputPath('system-alert-results.png'), fullPage: true })
  await page.getByLabel('下一页系统事件', { exact: true }).click()
  await expect(page.locator('.system-event').first()).toContainText('合成历史事件')
  await page.goto('/#/settings/alerts')
  await expect(page.getByLabel('启用故障与恢复告警')).toHaveAttribute('aria-checked', 'true')
  for (const name of names)
    await expect(page.getByRole('checkbox', { name: new RegExp(name) })).toBeChecked()
  expect((await (await page.request.get('/api/manage/alerts/history')).json()).total).toBe(
    before.total + 2,
  )
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
  expect(errors).toEqual([])
})
