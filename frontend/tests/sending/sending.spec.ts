import { expect, test } from '@playwright/test'
const credentials = { username: 'sending_admin', password: 'Synthetic-Sending-2026' }
test('explicit tests and resends confirm intent, recover lost responses and preserve automatic records', async ({
  page,
}, info) => {
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  await page.addInitScript(() =>
    Object.defineProperty(Crypto.prototype, 'randomUUID', { value: undefined, configurable: true }),
  )
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
  const created = await page.request.post('/api/manage/targets', {
    headers,
    data: {
      name: '合成未知 ' + info.project.name,
      kind: 'webhook',
      enabled: false,
      config: { url: 'https://receiver.example.test/synthetic-private-sending-value' },
    },
  })
  expect(created.ok()).toBe(true)
  const targetId = (await created.json()).id
  const beforeTests = (await (await page.request.get('/api/manage/history/tests')).json()).total
  await page.goto('/#/notifications/targets')
  await page.reload()
  const card = page
    .locator('.notification-card')
    .filter({ hasText: '合成未知 ' + info.project.name })
  await card.getByRole('button', { name: '测试', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('暂停目标也可测试')
  expect((await (await page.request.get('/api/manage/history/tests')).json()).total).toBe(
    beforeTests,
  )
  const bodies: any[] = []
  await page.route(
    '**/api/manage/targets/' + targetId + '/test',
    async (route) => {
      bodies.push(route.request().postDataJSON())
      const response = await route.fetch()
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ detail: '合成响应丢失，请查询本次操作' }),
      })
    },
    { times: 1 },
  )
  await page.getByRole('button', { name: '确认发送测试消息', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('合成响应丢失')
  await page.route(
    '**/api/manage/targets/' + targetId + '/test',
    (route) => {
      bodies.push(route.request().postDataJSON())
      return route.continue()
    },
    { times: 1 },
  )
  await page.getByRole('button', { name: '查询或重试本次操作', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: '结果未知' })).toBeVisible()
  expect(bodies).toHaveLength(2)
  expect(bodies[0].request_id).toBe(bodies[1].request_id)
  expect((await (await page.request.get('/api/manage/history/tests')).json()).total).toBe(
    beforeTests + 1,
  )
  await page.screenshot({ path: info.outputPath('test-unknown.png'), fullPage: true })
  await page.getByRole('button', { name: '查看记录', exact: true }).click()
  await expect(page.getByRole('heading', { name: '目标测试详情' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: '目标测试详情' })).toBeVisible()
  const current = workspace.targets[0]
  const update = async (name: string) =>
    page.request.put('/api/manage/targets/' + current.id, {
      headers,
      data: { name, kind: current.kind, enabled: true, config: {} },
    })
  expect((await update('合成成功当前目标')).ok()).toBe(true)
  const deliveries = await (
    await page.request.get('/api/manage/history/deliveries?status=sent')
  ).json()
  const source = deliveries.items[0]
  const original = await (
    await page.request.get('/api/manage/history/deliveries/' + source.id)
  ).json()
  const beforeManual = (await (await page.request.get('/api/manage/history/manual')).json()).total
  await page.goto('/#/notifications/deliveries/' + source.id)
  await page.getByRole('button', { name: '手动重发', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('原投递曾有结果未知')
  await expect(page.getByRole('dialog')).toContainText('合成成功当前目标')
  await page.getByRole('button', { name: '取消', exact: true }).click()
  expect((await (await page.request.get('/api/manage/history/manual')).json()).total).toBe(
    beforeManual,
  )
  await page.getByRole('button', { name: '手动重发', exact: true }).click()
  await expect(page.getByRole('button', { name: '确认手动重发', exact: true })).toBeVisible()
  expect((await update('合成成功最新配置')).ok()).toBe(true)
  await page.getByRole('button', { name: '确认手动重发', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('目标配置已改变')
  await page.getByRole('button', { name: '取消', exact: true }).click()
  await page.getByRole('button', { name: '手动重发', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('合成成功最新配置')
  await page.getByRole('button', { name: '确认手动重发', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: '渠道已接受' })).toBeVisible()
  await page.getByRole('button', { name: '查看记录', exact: true }).click()
  await expect(page.getByRole('heading', { name: '手动重发详情' })).toBeVisible()
  await expect(page.locator('.reading-panel')).toContainText('合成成功最新配置')
  await expect(page.locator('.reading-panel')).toContainText('不改变自动去重')
  await page.reload()
  await expect(page.getByRole('heading', { name: '手动重发详情' })).toBeVisible()
  await page.screenshot({ path: info.outputPath('manual-result.png'), fullPage: true })
  expect((await (await page.request.get('/api/manage/history/manual')).json()).total).toBe(
    beforeManual + 1,
  )
  const after = await (await page.request.get('/api/manage/history/deliveries/' + source.id)).json()
  expect(after).toEqual(original)
  expect((await (await page.request.get('/api/manage/history/deliveries')).json()).total).toBe(24)
  expect(
    (await (await page.request.get('/api/manage/overview?range=7d')).json()).window.delivered,
  ).toBe(2)
  await page.getByRole('button', { name: '查看原投递', exact: true }).click()
  await expect(page.getByRole('heading', { name: '投递详情', exact: true })).toBeVisible()
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
  expect(errors).toEqual([])
})
