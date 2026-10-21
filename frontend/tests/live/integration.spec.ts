import { expect, test } from '@playwright/test'
const credentials = { username: 'browser_admin', password: 'Synthetic-2026-Password' }
test('real setup, login, website, task, workspace and a fresh browser retain server data', async ({
  page,
  browser,
}, info) => {
  const failures: string[] = []
  page.on('pageerror', (e) => failures.push(e.message))
  await page.route('**/*', (route) => {
    const url = new URL(route.request().url())
    if (url.hostname !== '127.0.0.1') throw new Error('Unexpected external request')
    return route.continue()
  })
  await page.goto('/')
  const status = await page.request.get('/api/auth/status')
  const first = !(await status.json()).initialized
  if (first) {
    await expect(page.getByRole('heading', { name: '欢迎来到 SeekBell' })).toBeVisible()
    await page.getByLabel('管理员用户名').fill(credentials.username)
    await page.getByLabel('设置密码', { exact: true }).fill(credentials.password)
    await page.getByLabel('确认密码', { exact: true }).fill(credentials.password)
    await page.getByRole('button', { name: '创建管理员并进入' }).click()
  } else {
    await page.getByLabel('管理员用户名').fill(credentials.username)
    await page.getByLabel('密码', { exact: true }).fill(credentials.password)
    await page.getByRole('button', { name: '登录工作空间' }).click()
  }
  await expect(page.locator('.sidebar')).toBeAttached()
  await expect(page.locator('.demo-badge')).toContainText('本地数据')
  const csrf = (await (await page.request.get('/api/auth/status')).json()).csrf
  const headers = { 'X-CSRF-Token': csrf }
  // Each project starts without installed websites; only this disposable server is changed.
  const prior = await (await page.request.get('/api/manage/workspace')).json()
  if (first) expect(prior.websites).toEqual([])
  for (const task of prior.tasks)
    await page.request.delete('/api/manage/tasks/' + task.id, { headers })
  if (prior.websites.length) await page.request.delete('/api/manage/websites/nodeseek', { headers })
  await page.goto('/#/websites')
  await page.reload()
  await expect(page.locator('.website-card')).toHaveCount(0)
  await page.getByRole('button', { name: '添加第一个网站' }).click()
  const panel = page.locator('.website-drawer')
  await expect(panel).toBeVisible()
  expect(
    await panel.evaluate((e) => {
      const r = e.getBoundingClientRect()
      return Math.abs(r.x + r.width / 2 - innerWidth / 2) < 3
    }),
  ).toBe(true)
  await page.screenshot({ path: info.outputPath('live-catalog.png') })
  await page.getByRole('button', { name: '添加 NodeSeek', exact: true }).click()
  await expect(panel).not.toBeVisible()
  await expect(page.locator('.website-card')).toHaveCount(1)
  await page.getByRole('button', { name: '配置 NodeSeek', exact: true }).click()
  await expect(panel).toBeVisible()
  expect(
    await panel.evaluate((e) => Math.abs(e.getBoundingClientRect().right - innerWidth) < 3),
  ).toBe(true)
  await page.getByLabel('共享采集间隔').fill('25')
  await page.getByRole('button', { name: '保存设置', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('网站配置已保存')
  await page.screenshot({ path: info.outputPath('live-website.png') })
  await page.getByRole('button', { name: '关闭网站面板' }).click()
  await page.reload()
  await expect(page.locator('.website-card')).toContainText('25')
  const name = '浏览器目标-' + info.project.name
  await page.goto('/#/target/new')
  await page.getByRole('button', { name: 'Webhook', exact: true }).click()
  await page.locator('#target-name').fill(name)
  await page.getByLabel('Webhook URL').fill('https://receiver.example.test/synthetic-private-path')
  await page.getByRole('button', { name: '保存目标', exact: true }).click()
  await expect(page).toHaveURL(/notifications\/targets/)
  await expect(page.locator('.target-card-title').filter({ hasText: name })).toBeVisible()
  await page.goto('/#/task/new')
  await page.locator('#task-name').fill('真实任务-' + info.project.name)
  await page.locator('#task-description').fill('此备注必须由数据库保留')
  await page.getByLabel('条件组1全部包含').fill('STRASSE')
  await page.getByLabel('条件组1全部包含').press('Enter')
  await page.locator('.target-options label').filter({ hasText: name }).click()
  await page.locator('#sample-title').fill('Straße')
  await page.getByRole('button', { name: '试匹配这条帖子' }).click()
  await expect(page.locator('.match-result')).toContainText('命中')
  await page.route(
    '**/api/manage/tasks',
    (route) =>
      route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ detail: '合成服务故障，请重试。' }),
      }),
    { times: 1 },
  )
  await page.getByRole('button', { name: '保存任务', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('合成服务故障')
  await expect(page.locator('#task-name')).toHaveValue('真实任务-' + info.project.name)
  await page.getByRole('button', { name: '保存任务', exact: true }).click()
  await expect(page).not.toHaveURL(/task\/new/)
  await page.goto('/#/tasks')
  await expect(page.locator('.management-row')).toContainText('真实任务-' + info.project.name)
  await page.reload()
  await expect(page.locator('.management-row')).toContainText('此备注必须由数据库保留')
  const taskRow = page
    .locator('.task-management-row')
    .filter({ hasText: '真实任务-' + info.project.name })
  await expect(
    taskRow.getByRole('button', { name: '编辑真实任务-' + info.project.name, exact: true }),
  ).toBeVisible()
  await taskRow.locator('.management-copy > p').click()
  await expect(page.getByLabel('任务名称')).toHaveValue('真实任务-' + info.project.name)
  await page.getByRole('button', { name: '取消', exact: true }).click()
  await expect(page).toHaveURL(/#\/tasks$/)
  await page.goto('/#/settings/preferences')
  const workspace = '我的关注空间-' + info.project.name
  await page.getByLabel('工作空间名称').fill(workspace)
  await page.getByLabel('工作空间说明').fill('真实保存，刷新保留')
  await page.getByRole('button', { name: '保存偏好设置' }).click()
  await expect(page.locator('.workspace-label')).toContainText(workspace)
  await page.reload()
  await expect(page.locator('.workspace-label')).toContainText(workspace)
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
  await page.setViewportSize(
    info.project.name === 'mobile' ? { width: 390, height: 844 } : { width: 1440, height: 1000 },
  )
  await page.screenshot({ path: info.outputPath('live-workspace.png'), fullPage: true })
  expect(
    await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage })),
  ).not.toContain('synthetic-private-path')
  expect(
    await page.evaluate(() => Object.keys(localStorage).some((k) => k.startsWith('seekbell-demo'))),
  ).toBe(false)
  expect(await page.evaluate(() => document.cookie)).not.toContain('seekbell_session')
  await page.goto('/#/settings/account')
  await page.locator('#main-content').getByRole('button', { name: '退出登录', exact: true }).click()
  await expect(page.getByRole('heading', { name: '欢迎回来' })).toBeVisible()
  expect((await page.request.get('/api/manage/workspace')).status()).toBe(401)
  const context = await browser.newContext()
  const fresh = await context.newPage()
  await fresh.goto('http://127.0.0.1:8011/')
  await fresh.getByLabel('管理员用户名').fill(credentials.username)
  await fresh.getByLabel('密码', { exact: true }).fill(credentials.password)
  await fresh.getByRole('button', { name: '登录工作空间' }).click()
  await expect(fresh.locator('.workspace-label')).toContainText(workspace)
  await fresh.goto('http://127.0.0.1:8011/#/tasks')
  await expect(fresh.locator('.management-row')).toContainText('真实任务-' + info.project.name)
  await context.close()
  expect(failures).toEqual([])
})
