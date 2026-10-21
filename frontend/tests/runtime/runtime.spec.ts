import { expect, test } from '@playwright/test'
const credentials = { username: 'runtime_admin', password: 'Synthetic-Runtime-2026' }
test('service discovers and delivers after browser closure, without rebuilding baseline', async ({
  page,
  browser,
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
  await expect(page.locator('.sidebar')).toBeAttached()
  const csrf = (await (await page.request.get('/api/auth/status')).json()).csrf
  const headers = { 'X-CSRF-Token': csrf }
  const workspace = await (await page.request.get('/api/manage/workspace')).json()
  for (const task of workspace.tasks)
    expect((await page.request.delete('/api/manage/tasks/' + task.id, { headers })).ok()).toBe(true)
  if (workspace.websites.length)
    expect((await page.request.delete('/api/manage/websites/nodeseek', { headers })).ok()).toBe(
      true,
    )
  expect(
    (
      await page.request.post('/api/manage/websites', { headers, data: { adapter_id: 'nodeseek' } })
    ).ok(),
  ).toBe(true)
  const response = await page.request.post('/api/manage/targets', {
    headers,
    data: {
      name: 'Synthetic runtime ' + info.project.name,
      kind: 'webhook',
      enabled: true,
      config: { url: 'https://receiver.example.test/synthetic-runtime' },
    },
  })
  expect(response.ok()).toBe(true)
  const target = (await response.json()).id
  expect(
    (
      await page.request.post('/api/manage/tasks', {
        headers,
        data: {
          name: '后台持续关注 ' + info.project.name,
          website_id: 'nodeseek',
          enabled: true,
          rule: { groups: [{ all_of: ['VPS'] }] },
          target_ids: [target],
        },
      })
    ).ok(),
  ).toBe(true)
  expect(
    (
      await page.request.put('/api/manage/websites/nodeseek', {
        headers,
        data: { enabled: true, interval: 10 },
      })
    ).ok(),
  ).toBe(true)
  await expect
    .poll(
      async () =>
        (await (await page.request.get('/api/manage/overview')).json()).sources[0].last_success_at,
    )
    .not.toBeNull()
  const initial = (
    await (await page.request.get('/api/manage/history/deliveries?target_id=' + target)).json()
  ).total
  expect(initial).toBe(0)
  const api = await playwright.request.newContext({
    baseURL: 'http://127.0.0.1:8014',
    storageState: await page.context().storageState(),
  })
  await page.context().close()
  // No browser or API polling during the configured RSS interval.
  await new Promise((resolve) => setTimeout(resolve, 10500))
  try {
    await expect
      .poll(
        async () =>
          (
            await (
              await api.get('/api/manage/history/deliveries?target_id=' + target + '&status=sent')
            ).json()
          ).total,
        { timeout: 5000 },
      )
      .toBe(1)
    const delivery = (
      await (await api.get('/api/manage/history/deliveries?target_id=' + target)).json()
    ).items[0]
    expect(delivery.attempt_count).toBe(1)
    expect((await (await api.get('/api/manage/runtime')).json()).status).toBe('running')
    const context = await browser.newContext()
    try {
      const reopened = await context.newPage()
      reopened.on('pageerror', (e) => errors.push(e.message))
      await reopened.route('**/*', (route) => {
        if (new URL(route.request().url()).hostname !== '127.0.0.1')
          throw new Error('Unexpected external request')
        return route.continue()
      })
      await reopened.goto('/#/login')
      await reopened.getByLabel('管理员用户名').fill(credentials.username)
      await reopened.getByLabel('密码', { exact: true }).fill(credentials.password)
      await reopened.getByRole('button', { name: '登录工作空间' }).click()
      await expect(reopened.getByTestId('overview-delivered')).toBeVisible()
      const snapshot = await (await reopened.request.get('/api/manage/overview')).json()
      expect(snapshot.runtime_active).toBe(true)
      await expect(reopened.getByTestId('overview-delivered')).toContainText(
        String(snapshot.window.delivered) + '次',
      )
      await reopened.screenshot({ path: info.outputPath('runtime-overview.png'), fullPage: true })
      await reopened.goto('/#/notifications/deliveries/' + delivery.id)
      await expect(reopened.getByRole('heading', { name: '投递详情', exact: true })).toBeVisible()
      await expect(reopened.locator('.delivery-timeline')).toContainText('渠道已接受')
      await reopened.screenshot({ path: info.outputPath('automatic-delivery.png'), fullPage: true })
      await reopened.goto('/#/websites')
      await expect(reopened.locator('.website-card')).toContainText('采集正常')
      await reopened.getByRole('switch', { name: 'NodeSeek 采集启用状态', exact: true }).click()
      await reopened.getByRole('button', { name: '暂停网站', exact: true }).click()
      await expect(reopened.locator('.website-card')).toContainText('已暂停')
      for (const width of [320, 390, 768, 1440]) {
        await reopened.setViewportSize({ width, height: 900 })
        expect(
          await reopened.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
        ).toBe(true)
      }
    } finally {
      await context.close()
    }
  } finally {
    await api.dispose()
  }
  expect(errors).toEqual([])
})
