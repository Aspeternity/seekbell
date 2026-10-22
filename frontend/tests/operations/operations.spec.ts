import { expect, test } from '@playwright/test'
const credentials = { username: 'operations_admin', password: 'Synthetic-Operations-2026' }
test('draft history trials, confirmed source checks and dependency-safe deletion use real APIs', async ({
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
  await expect(page.locator('.sidebar')).toBeAttached()
  const headers = {
    'X-CSRF-Token': (await (await page.request.get('/api/auth/status')).json()).csrf,
  }
  const name = '合成成功操作 ' + info.project.name
  const created = await page.request.post('/api/manage/targets', {
    headers,
    data: {
      name,
      kind: 'webhook',
      enabled: false,
      config: { url: 'https://receiver.example.test/synthetic' },
    },
  })
  expect(created.ok()).toBe(true)
  const targetId = (await created.json()).id
  const taskCreated = await page.request.post('/api/manage/tasks', {
    headers,
    data: {
      name: '暂停关联 ' + info.project.name,
      website_id: 'nodeseek',
      enabled: false,
      rule: { groups: [{ all_of: ['VPS'] }] },
      target_ids: [targetId],
    },
  })
  expect(taskCreated.ok()).toBe(true)
  const taskId = (await taskCreated.json()).id
  const before = await (await page.request.get('/api/manage/history/posts?size=100')).json()
  await page.reload()
  await page.goto('/#/task/' + taskId)
  await expect(page.getByRole('heading', { name: '编辑监控任务' })).toBeVisible()
  await page.getByRole('radio', { name: '标题 + 摘要 覆盖更多线索' }).check()
  await expect(page.locator('.field-help')).toContainText(['摘要缺失时仅按标题判断'])
  await page.getByLabel('排除关键词', { exact: true }).fill('求购')
  await page.getByLabel('排除关键词', { exact: true }).press('Enter')
  await page.getByLabel('帖子标题').fill('VPS 合成优惠')
  await page.getByRole('checkbox', { name: '模拟摘要字段缺失' }).check()
  await page.getByRole('button', { name: '试匹配这条帖子' }).click()
  await expect(page.locator('.match-result')).toHaveClass(/yes/)
  await page.getByLabel('帖子标题').fill('求购 VPS 合成优惠')
  await page.getByRole('button', { name: '试匹配这条帖子' }).click()
  await expect(page.locator('.match-result')).toHaveClass(/no/)
  await page.getByLabel('帖子标题').fill('无关合成标题')
  await page.getByRole('button', { name: '试匹配这条帖子' }).click()
  await expect(page.locator('.match-result')).toHaveClass(/no/)
  await page.getByLabel('帖子标题').fill('VPS 合成优惠')
  await page.getByRole('checkbox', { name: '模拟摘要字段缺失' }).uncheck()
  await page.getByLabel('帖子摘要', { exact: true }).fill('求购')
  await page.getByRole('button', { name: '试匹配这条帖子' }).click()
  await expect(page.locator('.match-result')).toHaveClass(/no/)
  await page.getByLabel('帖子摘要', { exact: true }).fill('普通合成摘要')
  await page.getByRole('button', { name: '试匹配这条帖子' }).click()
  await expect(page.locator('.match-result')).toHaveClass(/yes/)
  await page.getByRole('radio', { name: '仅摘要' }).check()
  await page.getByRole('checkbox', { name: '模拟摘要字段缺失' }).check()
  await page.getByRole('button', { name: '试匹配这条帖子' }).click()
  await expect(page.locator('.match-result')).toHaveClass(/unknown/)
  await page.getByRole('button', { name: '历史样本', exact: true }).click()
  await expect(page.locator('.history-intro')).toContainText('本地已保存帖子')
  await expect(page.locator('.history-intro')).not.toContainText('合成历史样本')
  await page.getByLabel('最多试算条数').selectOption('100')
  await page.route(
    '**/api/manage/rules/history',
    (route) =>
      route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ detail: '合成试算暂不可用' }),
      }),
    { times: 1 },
  )
  await page.getByRole('button', { name: '试匹配本地历史', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('合成试算暂不可用')
  await page.getByRole('button', { name: '试匹配本地历史', exact: true }).click()
  await expect(page.locator('.history-results article')).toHaveCount(27)
  await expect(page.locator('.history-results')).toContainText('本地共 27 条；本次 27 条')
  await expect(page.locator('.history-results')).toContainText('首次发现时间')
  await expect(page.locator('.history-results')).toContainText('missing_summary')
  await expect(page.locator('.history-results img')).toHaveCount(0)
  expect(await (await page.request.get('/api/manage/history/posts?size=100')).json()).toEqual(
    before,
  )
  const saved = await (await page.request.get('/api/manage/workspace')).json()
  expect(saved.tasks.find((item: any) => item.id === taskId).rule.scope).toBe('title')
  await page.screenshot({ path: info.outputPath('local-history-trial.png'), fullPage: true })
  // Reload discards the intentionally unsaved draft.
  await page.reload()
  await page.goto('/#/websites')
  await page.getByRole('button', { name: '配置 NodeSeek', exact: true }).click()
  const drawer = page.locator('.website-drawer')
  await expect(drawer).toBeVisible()
  const previous = await (
    await page.request.get('/api/manage/websites/nodeseek/connection-test')
  ).json()
  if (previous)
    await expect
      .poll(() => Date.now() / 1000, { timeout: 15000 })
      .toBeGreaterThan(previous.next_attempt_at)
  await drawer.getByRole('button', { name: '测试连接', exact: true }).click()
  const confirm = page.getByRole('dialog', { name: '测试 NodeSeek 官方 RSS 连接？' })
  await expect(confirm).toContainText('不会启用网站')
  await confirm.getByRole('button', { name: '取消', exact: true }).click()
  expect(
    await (await page.request.get('/api/manage/websites/nodeseek/connection-test')).json(),
  ).toEqual(previous)
  await page.route(
    '**/api/manage/websites/nodeseek/connection-test',
    async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 300))
      await route.continue()
    },
    { times: 1 },
  )
  await drawer.getByRole('button', { name: '测试连接', exact: true }).click()
  await page.getByRole('button', { name: '确认测试连接', exact: true }).click()
  await expect(drawer.getByRole('button', { name: '测试中…', exact: true })).toBeDisabled()
  await expect(drawer).toContainText('RSS 连接与解析成功')
  await expect(drawer).toContainText('有效帖子 1 条')
  expect(await (await page.request.get('/api/manage/history/posts?size=100')).json()).toEqual(
    before,
  )
  const workspace = await (await page.request.get('/api/manage/workspace')).json()
  expect(workspace.websites[0].enabled).toBe(false)
  expect(workspace.websites[0].lastSuccess).toBeTruthy() // seeded collection success is unchanged
  await page.screenshot({ path: info.outputPath('website-connection-check.png'), fullPage: true })
  await page.reload()
  await page.getByRole('button', { name: '配置 NodeSeek', exact: true }).click()
  await expect(page.locator('.website-drawer')).toContainText('RSS 连接与解析成功')
  await page.reload()
  await page.goto('/#/notifications/targets')
  const card = page.locator('.notification-card').filter({ hasText: name })
  await card.getByRole('button', { name: '删除' + name, exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('暂停关联 ' + info.project.name)
  await expect(page.getByRole('dialog')).toContainText('保持暂停')
  await page.getByRole('dialog').getByRole('button', { name: '取消', exact: true }).click()
  expect((await page.request.delete('/api/manage/targets/' + targetId, { headers })).status()).toBe(
    409,
  )
  // Create a mocked explicit test so the removed target has immutable history.
  const preview = await (
    await page.request.get('/api/manage/targets/' + targetId + '/test-preview')
  ).json()
  const record = await page.request.post('/api/manage/targets/' + targetId + '/test', {
    headers,
    data: { request_id: crypto.randomUUID(), revision: preview.revision },
  })
  expect(record.ok()).toBe(true)
  const recordId = (await record.json()).id
  expect((await page.request.delete('/api/manage/tasks/' + taskId, { headers })).ok()).toBe(true)
  await page.reload()
  await card.getByRole('button', { name: '删除' + name, exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('任务规则和历史记录会保留')
  await page.getByRole('button', { name: '取消', exact: true }).click()
  await page.route(
    '**/api/manage/targets/' + targetId,
    (route) =>
      route.request().method() === 'DELETE'
        ? route.fulfill({
            status: 503,
            contentType: 'application/json',
            body: JSON.stringify({ detail: '合成删除失败' }),
          })
        : route.continue(),
    { times: 1 },
  )
  await card.getByRole('button', { name: '删除' + name, exact: true }).click()
  await page.getByRole('button', { name: '删除', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('合成删除失败')
  await expect(card).toBeVisible()
  await page.getByRole('dialog').getByRole('button', { name: '重新加载', exact: true }).click()
  await page.getByRole('dialog').getByRole('button', { name: '删除', exact: true }).click()
  await expect(card).toHaveCount(0)
  await page.reload()
  await expect(card).toHaveCount(0)
  const detail = await page.request.get('/api/manage/history/tests/' + recordId)
  expect(detail.ok()).toBe(true)
  expect((await detail.json()).target_name).toBe(name)
  await page.goto('/#/notifications/tests/' + recordId)
  await expect(page.getByRole('heading', { name: '目标测试详情' })).toBeVisible()
  await expect(page.locator('.reading-panel')).toContainText(name)
  await page.screenshot({ path: info.outputPath('deleted-target-history.png'), fullPage: true })
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
  expect(errors).toEqual([])
})
