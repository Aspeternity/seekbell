import { expect, test } from '@playwright/test'
const credentials = { username: 'history_admin', password: 'Synthetic-History-2026' }

test('production pages preserve the approved UI while using real persisted data', async ({
  page,
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
  await expect(page.getByRole('heading', { name: '每一条在意的，都不错过。' })).toBeVisible()
  await expect(
    page.getByText('让 SeekBell 留意新帖，把时间留给更重要的事。', { exact: true }),
  ).toBeVisible()
  await expect(page.locator('.chart-panel .segmented')).toBeVisible()
  await expect(page.locator('.stat-card .mini-chart')).toHaveCount(1)
  await expect(page.locator('.mini-bars i')).toHaveCount(9)
  await expect(page.locator('.trend-chart polygon')).toHaveCount(1)
  const overview = await (await page.request.get('/api/manage/overview')).json()
  await expect(page.locator('.tasks-panel .task-row')).toHaveCount(overview.tasks.length)
  for (const row of overview.tasks) {
    const workspace = await (await page.request.get('/api/manage/workspace')).json()
    const task = workspace.tasks.find((task: any) => task.id === row.id)
    const element = page.locator('.tasks-panel .task-row').filter({ hasText: task.name })
    await expect(element.locator('.task-hits')).toContainText(String(row.matches))
    await expect(element.getByRole('switch')).toHaveAttribute('aria-checked', String(task.enabled))
  }
  await page.screenshot({ path: info.outputPath('approved-overview.png'), fullPage: true })
  await page.goto('/#/notifications/targets')
  const total = await (await page.request.get('/api/manage/history/deliveries?page_size=1')).json()
  await expect(
    page.locator('.page-tabs button').filter({ hasText: '投递记录' }).locator('span'),
  ).toHaveText(String(total.total))
  const target = page.locator('.notification-card').first()
  await expect(target.locator('.notification-card-actions .icon-button svg')).toHaveCount(1)
  await page.screenshot({ path: info.outputPath('approved-targets.png'), fullPage: true })
  await page.goto('/#/notifications/deliveries')
  await expect(page.getByText('把关心的消息，送到你习惯的地方。', { exact: true })).toBeVisible()
  await page.screenshot({ path: info.outputPath('approved-records.png'), fullPage: true })
  await page.goto('/#/settings/preferences')
  await expect(page.locator('.page-tabs button')).toHaveText([
    '偏好与保留',
    '管理员',
    '备份与恢复',
    '关于',
  ])
  await expect(page.locator('.settings-aside')).toBeVisible()
  await expect(page.getByLabel('显示时区', { exact: true })).toBeEnabled()
  await expect(page.getByLabel('普通历史保留天数', { exact: true })).toBeEnabled()
  await expect(page.getByRole('switch', { name: '故障与恢复通知', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '保存偏好设置', exact: true })).toHaveCount(1)
  await page.screenshot({ path: info.outputPath('approved-preferences.png'), fullPage: true })

  // A later preference write failing must retain remaining drafts and not replay
  // an already successful workspace write when the user retries.
  const original = await (await page.request.get('/api/manage/workspace')).json()
  const display = await (await page.request.get('/api/manage/display')).json()
  const nextZone = display.timezone === 'UTC' ? 'Asia/Shanghai' : 'UTC'
  const writes: string[] = []
  page.on('request', (request) => {
    if (request.method() === 'PUT') writes.push(new URL(request.url()).pathname)
  })
  await page.getByLabel('工作空间名称', { exact: true }).fill('UI验收-' + info.project.name)
  await page.getByLabel('显示时区', { exact: true }).selectOption(nextZone)
  await page.route(
    '**/api/manage/display',
    (route) =>
      route.request().method() === 'PUT'
        ? route.fulfill({ status: 503, json: { detail: '合成偏好保存失败' } })
        : route.continue(),
    { times: 1 },
  )
  await page.getByRole('button', { name: '保存偏好设置', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('合成偏好保存失败')
  await expect(page.getByLabel('显示时区', { exact: true })).toHaveValue(nextZone)
  expect(writes.filter((path) => path === '/api/manage/workspace')).toHaveLength(1)
  await page.getByRole('button', { name: '保存偏好设置', exact: true }).click()
  await expect
    .poll(async () => (await (await page.request.get('/api/manage/display')).json()).timezone)
    .toBe(nextZone)
  expect(writes.filter((path) => path === '/api/manage/workspace')).toHaveLength(1)
  await page.getByLabel('工作空间名称', { exact: true }).fill(original.settings.workspaceName)
  await page.getByLabel('显示时区', { exact: true }).selectOption(display.timezone)
  await page.getByRole('button', { name: '保存偏好设置', exact: true }).click()
  await expect(page.locator('.workspace-label')).toContainText(original.settings.workspaceName)

  const previous = await (await page.request.get('/api/manage/display')).json()
  await page.getByLabel('显示时区', { exact: true }).selectOption(nextZone)
  const csrf = (await (await page.request.get('/api/auth/status')).json()).csrf
  const otherZone = ['UTC', 'Asia/Shanghai', 'Asia/Tokyo'].find(
    (zone) => zone !== previous.timezone && zone !== nextZone,
  )!
  expect(
    (
      await page.request.put('/api/manage/display', {
        headers: { 'X-CSRF-Token': csrf },
        data: { timezone: otherZone, revision: previous.revision },
      })
    ).ok(),
  ).toBe(true)
  await page.getByRole('button', { name: '保存偏好设置', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('其他页面改变')
  await expect(page.getByLabel('显示时区', { exact: true })).toHaveValue(nextZone)
  await page.getByRole('button', { name: '重新读取偏好设置', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('尚未保存')
  await page.getByRole('button', { name: '放弃修改并读取', exact: true }).click()
  await expect(page.getByLabel('显示时区', { exact: true })).toHaveValue(otherZone)
  await page.getByLabel('显示时区', { exact: true }).selectOption(display.timezone)
  await page.getByRole('button', { name: '保存偏好设置', exact: true }).click()
  await expect
    .poll(async () => (await (await page.request.get('/api/manage/display')).json()).timezone)
    .toBe(display.timezone)

  await page.getByRole('button', { name: '关于', exact: true }).click()
  await expect(page.locator('.about-card .brand-icon')).toBeVisible()
  await expect(page.getByTestId('build-revision')).toBeVisible()
  await page.screenshot({ path: info.outputPath('approved-about.png'), fullPage: true })
  await page.getByRole('button', { name: '备份与恢复', exact: true }).click()
  await expect(page.getByRole('heading', { name: '导出备份', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: '从文件恢复', exact: true })).toBeVisible()
  await expect(page.locator('.backup-summary')).toBeVisible()
  const posts = await (await page.request.get('/api/manage/history/posts?page_size=1')).json()
  await expect(page.locator('.backup-summary strong').nth(2)).toHaveText(String(posts.total))
  await expect(page.locator('.upload-zone')).toBeVisible()
  await page.screenshot({ path: info.outputPath('approved-backup.png'), fullPage: true })
  for (const path of [
    '/',
    '/tasks',
    '/content',
    '/notifications/targets',
    '/notifications/deliveries',
    '/settings/preferences',
    '/settings/account',
    '/settings/backup',
    '/settings/about',
  ]) {
    await page.goto('/#' + path)
    await expect(page.locator('h1')).toBeVisible()
    for (const width of [320, 390, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: 900 })
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
        path + ' at ' + width,
      ).toBe(true)
    }
  }
  expect(errors).toEqual([])
})
