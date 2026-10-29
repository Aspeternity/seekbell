import { expect, test } from '@playwright/test'
const credentials = { username: 'retention_admin', password: 'Synthetic-Retention-2026' }
const now = Date.UTC(2026, 9, 20, 12) / 1000
test('retention confirms changes, handles stale revisions and cleans with the browser closed', async ({
  page,
  browser,
}, info) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
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
  const before = await (await page.request.get('/api/manage/history/posts')).json()
  const days = info.project.name === 'desktop' ? 15 : 1
  const expired = before.items.filter((post: any) => post.first_seen_at < now - days * 86400)
  expect(expired.length).toBeGreaterThan(0)
  await page.route(
    '**/api/manage/retention',
    (route) =>
      route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ detail: '合成策略读取失败' }),
      }),
    { times: 1 },
  )
  await page.goto('/#/settings/retention')
  await expect(page.getByRole('alert')).toContainText('合成策略读取失败')
  await page.getByRole('alert').getByRole('button', { name: '重新加载', exact: true }).click()
  const input = page.getByLabel('普通历史保留天数')
  await expect(input).toBeVisible()
  await input.fill(String(days))
  // Leaving a policy draft uses the existing unsaved-edit guard.
  await page.evaluate(() => (location.hash = '/settings/account'))
  await expect(page.getByRole('dialog')).toContainText('尚未保存')
  await page.getByRole('button', { name: '继续编辑', exact: true }).click()
  await expect(input).toHaveValue(String(days))
  const initial = await (await page.request.get('/api/manage/retention')).json()
  await page.getByRole('button', { name: '保存保留策略', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('已清理的数据无法恢复')
  await page.getByRole('button', { name: '取消', exact: true }).click()
  expect((await (await page.request.get('/api/manage/retention')).json()).days).toBe(initial.days)
  // Another browser saves while this editor still has an older revision.
  expect(
    (
      await page.request.put('/api/manage/retention', {
        headers,
        data: {
          days: 365,
          revision: initial.revision,
        },
      })
    ).ok(),
  ).toBe(true)
  await page.getByRole('button', { name: '保存保留策略', exact: true }).click()
  await page.getByRole('button', { name: '确认保存策略', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('其他页面改变')
  await expect(input).toHaveValue(String(days))
  await page.getByRole('alert').getByRole('button', { name: '重新加载', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('尚未保存的保留天数将丢失')
  await page.getByRole('button', { name: '放弃修改并读取', exact: true }).click()
  await expect(input).toHaveValue('365')
  await input.fill(String(days))
  await page.route(
    '**/api/manage/retention',
    (route) =>
      route.request().method() === 'PUT'
        ? route.fulfill({
            status: 503,
            contentType: 'application/json',
            body: JSON.stringify({ detail: '合成策略保存失败' }),
          })
        : route.continue(),
    { times: 1 },
  )
  await page.getByRole('button', { name: '保存保留策略', exact: true }).click()
  await page.getByRole('button', { name: '确认保存策略', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('合成策略保存失败')
  await expect(input).toHaveValue(String(days))
  await page.getByRole('button', { name: '保存保留策略', exact: true }).click()
  await page.getByRole('button', { name: '确认保存策略', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: '保留策略已保存' })).toBeVisible()
  expect(errors).toEqual([])
  await page.context().close()
  // No browser requests for a full cleanup wake interval.
  await new Promise((resolve) => setTimeout(resolve, 1200))
  const context = await browser.newContext({
    viewport: { width: info.project.name === 'mobile' ? 390 : 1440, height: 900 },
  })
  try {
    const reopened = await context.newPage()
    reopened.on('pageerror', (error) => errors.push(error.message))
    await reopened.goto('/')
    await reopened.getByLabel('管理员用户名').fill(credentials.username)
    await reopened.getByLabel('密码', { exact: true }).fill(credentials.password)
    await reopened.getByRole('button', { name: '登录工作空间', exact: true }).click()
    await expect(reopened.locator('.sidebar')).toBeAttached()
    const after = await (await reopened.request.get('/api/manage/history/posts')).json()
    expect(after.total).toBe(before.total - expired.length)
    expect(after.items.some((post: any) => post.title === '近期合成历史')).toBe(true)
    expect(after.items.filter((post: any) => post.first_seen_at < now - days * 86400)).toHaveLength(
      0,
    )
    await reopened.goto('/#/settings/retention')
    await expect(reopened.getByLabel('普通历史保留天数')).toHaveValue(String(days))
    await reopened.getByText(/^最近一批共清理 \d+ 条记录$/).click()
    await expect(reopened.getByLabel('最近一批清理数量')).toBeVisible()
    await expect(reopened.getByText('运行中', { exact: true })).toBeVisible()
    for (const width of [320, 390, 768, 1440]) {
      await reopened.setViewportSize({ width, height: 900 })
      expect(
        await reopened.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      ).toBe(true)
    }
    await reopened.setViewportSize({
      width: info.project.name === 'mobile' ? 390 : 1440,
      height: 900,
    })
    await reopened.screenshot({
      path: info.outputPath('retention-policy-status.png'),
      fullPage: true,
    })
    await reopened.goto('/#/content')
    await expect(reopened.locator('.content-row')).toHaveCount(after.total)
    await reopened.screenshot({ path: info.outputPath('retained-history.png'), fullPage: true })
    expect(errors).toEqual([])
  } finally {
    await context.close()
  }
})
