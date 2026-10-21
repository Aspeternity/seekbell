import { expect, test } from '@playwright/test'
const credentials = { username: 'history_admin', password: 'Synthetic-History-2026' }
test('real overview and administrator forms preserve records and rotate sessions', async ({
  page,
  playwright,
}, info) => {
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
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
  await expect(page.getByRole('button', { name: '新建任务', exact: true })).toHaveCount(0)
  await expect(page.getByTestId('overview-matches')).toHaveText('24条')
  await expect(page.getByTestId('overview-delivered')).toHaveText('2次')
  await expect(page.getByTestId('overview-attention')).toHaveText('3次')
  await expect(
    page.getByText('后台采集与通知发送尚未启动。已启用的配置不会自动执行。'),
  ).toBeVisible()
  await expect(page.locator('.overview-source')).toContainText('配置已暂停')
  await expect(page.locator('.overview-source')).toContainText('10/19')
  await expect(page.locator('.activity-row')).toHaveCount(5)
  await expect(page.locator('.activity-row').first()).toContainText('摘要关注')
  await page.getByRole('button', { name: '7 天', exact: true }).click()
  await expect(page.locator('.chart-point')).toHaveCount(7)
  await expect(page.getByTestId('overview-matches')).toHaveText('24条')
  await page.route(
    '**/api/manage/overview?*',
    (route) =>
      route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ detail: '合成统计故障' }),
      }),
    { times: 1 },
  )
  await page.getByRole('button', { name: '刷新概览', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('合成统计故障')
  await expect(page.locator('.stats-grid')).toHaveCount(0)
  await page.getByRole('button', { name: '重新加载', exact: true }).click()
  await expect(page.getByTestId('overview-matches')).toHaveText('24条')
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
  await page.setViewportSize(
    info.project.name === 'mobile' ? { width: 390, height: 844 } : { width: 1440, height: 1000 },
  )
  await page.screenshot({ path: info.outputPath('overview.png'), fullPage: true })
  await page.locator('.activity-row').first().locator('.activity-copy button').click()
  await expect(page.getByRole('heading', { name: '当时的规则判定' })).toBeVisible()
  await page.goto('/#/settings/account')
  await expect(page.getByLabel('管理员用户名')).toHaveValue(credentials.username)
  await page.getByLabel('新密码 留空保留原密码').fill('Synthetic-Updated-2026')
  await page.getByLabel('确认新密码', { exact: true }).fill('Synthetic-Different-2026')
  await page.getByLabel('当前密码', { exact: true }).fill(credentials.password)
  await page.getByRole('button', { name: '保存管理员资料', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('两次输入的新密码不一致')
  await page.goto('/#/content')
  await expect(page.getByRole('dialog')).toContainText('尚未保存')
  await page.getByRole('button', { name: '继续编辑', exact: true }).click()
  await expect(page.getByLabel('当前密码', { exact: true })).toHaveValue(credentials.password)
  // Exercise the full change once; mobile checks the same form, layout and guard.
  if (info.project.name === 'desktop') {
    const other = await playwright.request.newContext({ baseURL: 'http://127.0.0.1:8012' })
    try {
      const preauth = await (await other.get('/api/auth/status')).json()
      const login = await other.post('/api/auth/login', {
        data: credentials,
        headers: { 'X-CSRF-Token': preauth.csrf },
      })
      expect(login.ok()).toBe(true)
      await page.getByLabel('管理员用户名').fill('updated_admin')
      await page.getByLabel('确认新密码', { exact: true }).fill('Synthetic-Updated-2026')
      await page.getByLabel('当前密码', { exact: true }).fill('Synthetic-Incorrect-2026')
      await page.getByRole('button', { name: '保存管理员资料', exact: true }).click()
      await expect(page.getByRole('alert')).toContainText('当前密码不正确')
      await expect(page.getByLabel('管理员用户名')).toHaveValue('updated_admin')
      await page.getByLabel('当前密码', { exact: true }).fill(credentials.password)
      await page.getByRole('button', { name: '保存管理员资料', exact: true }).click()
      await expect(page.getByRole('status').filter({ hasText: '管理员资料已保存' })).toBeVisible()
      await expect(page.getByLabel('当前密码', { exact: true })).toHaveValue('')
      await expect(page.getByLabel('新密码 留空保留原密码')).toHaveValue('')
      expect((await other.get('/api/manage/workspace')).status()).toBe(401)
      // Restore through a second mutation before reload: requires the fresh CSRF.
      await page.getByLabel('管理员用户名').fill(credentials.username)
      await page.getByLabel('当前密码', { exact: true }).fill('Synthetic-Updated-2026')
      await page.getByLabel('新密码 留空保留原密码').fill(credentials.password)
      await page.getByLabel('确认新密码', { exact: true }).fill(credentials.password)
      await page.getByRole('button', { name: '保存管理员资料', exact: true }).click()
      await expect(page.getByRole('status').filter({ hasText: '管理员资料已保存' })).toBeVisible()
      await page.reload()
      await expect(page.getByLabel('管理员用户名')).toHaveValue(credentials.username)
      expect((await (await page.request.get('/api/manage/history/posts')).json()).total).toBe(27)
      await page.screenshot({ path: info.outputPath('administrator.png'), fullPage: true })
      await page
        .locator('#main-content')
        .getByRole('button', { name: '退出登录', exact: true })
        .click()
      await expect(page.getByRole('button', { name: '登录工作空间' })).toBeVisible()
      await page.getByLabel('管理员用户名').fill(credentials.username)
      await page.getByLabel('密码', { exact: true }).fill(credentials.password)
      await page.getByRole('button', { name: '登录工作空间' }).click()
      await expect(page.getByTestId('overview-matches')).toHaveText('24条')
    } finally {
      await other.dispose()
    }
  } else {
    await page.screenshot({ path: info.outputPath('administrator.png'), fullPage: true })
  }
  expect(
    await page.evaluate(() =>
      Object.keys(localStorage).filter((key) => key.startsWith('seekbell')),
    ),
  ).toEqual([])
  expect(errors).toEqual([])
})
