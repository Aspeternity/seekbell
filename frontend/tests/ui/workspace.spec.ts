import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const credentials = { username: 'ui_admin', password: 'Synthetic-UI-2026-Password' }
async function headers(page: Page) {
  return { 'X-CSRF-Token': (await (await page.request.get('/api/auth/status')).json()).csrf }
}
async function workspace(page: Page) {
  return (await page.request.get('/api/manage/workspace')).json()
}
async function install(page: Page) {
  expect(
    (
      await page.request.post('/api/manage/websites', {
        headers: await headers(page),
        data: { adapter_id: 'nodeseek' },
      })
    ).ok(),
  ).toBe(true)
  await page.reload()
  await expect(page.locator('.sidebar')).toBeAttached()
}
test.beforeEach(async ({ page }) => {
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
  // This server owns a disposable, initially empty database; reset only that fixture.
  const data = await workspace(page),
    auth = await headers(page)
  for (const task of data.tasks)
    expect(
      (await page.request.delete('/api/manage/tasks/' + task.id, { headers: auth })).ok(),
    ).toBe(true)
  for (const target of data.targets)
    expect(
      (await page.request.delete('/api/manage/targets/' + target.id, { headers: auth })).ok(),
    ).toBe(true)
  if (data.websites.length)
    expect(
      (await page.request.delete('/api/manage/websites/nodeseek', { headers: auth })).ok(),
    ).toBe(true)
  await page.reload()
  await expect(page.locator('.sidebar')).toBeAttached()
})

test('the single real workspace covers routes, empty states and responsive navigation', async ({
  page,
}, info) => {
  test.setTimeout(90000)
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto('/#/task/new')
  await expect(page.getByRole('heading', { name: '先添加一个监控网站' })).toBeVisible()
  await install(page)
  const routes = [
    '/',
    '/websites',
    '/tasks',
    '/task/new',
    '/content',
    '/notifications/targets',
    '/notifications/deliveries',
    '/notifications/tests',
    '/notifications/manual',
    '/target/new',
    '/settings/preferences',
    '/settings/display',
    '/settings/retention',
    '/settings/alerts',
    '/settings/backup',
    '/settings/account',
    '/settings/about',
    '/missing',
  ]
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    for (const path of routes) {
      await page.goto('/#' + path)
      await expect(page.locator('#main-content h1')).toBeVisible()
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
        path + ' at ' + width,
      ).toBe(true)
    }
  }
  await page.setViewportSize(
    info.project.name === 'mobile' ? { width: 390, height: 844 } : { width: 1440, height: 1000 },
  )
  await page.goto('/#/')
  if (info.project.name === 'mobile') {
    await page.getByRole('button', { name: '打开导航' }).click()
    await expect(page.getByRole('button', { name: '关闭导航' })).toBeFocused()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('button', { name: '打开导航' })).toBeFocused()
  }
  expect(
    await page.evaluate(() =>
      Object.keys(localStorage).some((key) => key.startsWith('seekbell-demo')),
    ),
  ).toBe(false)
  await expect(page.getByRole('button', { name: '载入示例工作台' })).toHaveCount(0)
  expect(errors).toEqual([])
})

test('task tags, unsaved navigation and paused copies persist through real APIs', async ({
  page,
}, info) => {
  await install(page)
  const auth = await headers(page),
    targetName = '任务目标 ' + info.project.name
  const target = await page.request.post('/api/manage/targets', {
    headers: auth,
    data: {
      name: targetName,
      kind: 'webhook',
      enabled: false,
      config: { url: 'https://receiver.example.test/synthetic' },
    },
  })
  expect(target.ok()).toBe(true)
  await page.reload()
  await page.goto('/#/tasks')
  await page.getByRole('button', { name: '新建任务', exact: true }).click()
  await page.getByRole('button', { name: '保存任务', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('请填写任务名称')
  await expect(page.getByRole('alert')).toContainText('请至少选择一个通知目标')
  const name = '标签任务 ' + info.project.name
  await page.getByLabel('任务名称').fill(name)
  const input = page.getByLabel('条件组1全部包含', { exact: true })
  await input.fill('中文')
  await input.dispatchEvent('keydown', { key: 'Enter', isComposing: true })
  await expect(input.locator('..').locator('.tag')).toHaveCount(0)
  await input.press('Enter')
  await input.fill('中文')
  await input.press('Enter')
  await expect(input.locator('..').locator('.tag')).toHaveCount(1)
  await input.fill('RSS')
  await input.press(',')
  await input.fill('Linux')
  await page.getByLabel('任务名称').click()
  await expect(input.locator('..').locator('.tag')).toHaveCount(3)
  await page
    .locator('.target-options label')
    .filter({ hasText: targetName })
    .getByRole('checkbox')
    .check()
  await page.getByRole('button', { name: '保存任务', exact: true }).click()
  await expect(page).toHaveURL(/#\/tasks$/)
  let data = await workspace(page)
  expect(data.tasks[0].rule.groups[0].all_of).toEqual(['中文', 'RSS', 'Linux'])
  const row = page.locator('.task-management-row').filter({ hasText: name })
  await row.getByRole('button', { name: '复制' + name, exact: true }).click()
  await expect(page.locator('.task-management-row')).toHaveCount(2)
  data = await workspace(page)
  const copy = data.tasks.find((task: any) => task.name.endsWith(' · 副本'))
  expect(copy.enabled).toBe(false)
  expect(copy.rule).toEqual(data.tasks.find((task: any) => task.name === name).rule)
  await page.getByRole('button', { name: '编辑' + name, exact: true }).click()
  await page.getByLabel('任务名称').fill('未保存草稿')
  await page.getByRole('button', { name: '取消', exact: true }).click()
  await page.getByRole('dialog').getByRole('button', { name: '继续编辑', exact: true }).click()
  await expect(page.getByLabel('任务名称')).toHaveValue('未保存草稿')
  await page.getByRole('button', { name: '取消', exact: true }).click()
  await page
    .getByRole('dialog')
    .getByRole('button', { name: '放弃修改并离开', exact: true })
    .click()
  await page.getByRole('button', { name: '编辑' + name, exact: true }).click()
  await page.getByLabel('任务名称').fill('浏览器后退草稿')
  await page.goBack()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.getByRole('dialog').getByRole('button', { name: '继续编辑', exact: true }).click()
  await expect(page.getByLabel('任务名称')).toHaveValue('浏览器后退草稿')
  await page.getByRole('button', { name: '取消', exact: true }).click()
  await page
    .getByRole('dialog')
    .getByRole('button', { name: '放弃修改并离开', exact: true })
    .click()
  await page.getByRole('button', { name: '删除' + name, exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('已有命中与投递历史仍保留')
  await page.getByRole('dialog').getByRole('button', { name: '删除任务', exact: true }).click()
  await expect(page.getByRole('button', { name: '编辑' + name, exact: true })).toHaveCount(0)
  await page.reload()
  expect((await workspace(page)).tasks.map((task: any) => task.name)).toEqual([copy.name])
})

test('website catalog, configuration validation and unsaved close use the real installation', async ({
  page,
}) => {
  await page.goto('/#/websites')
  await page.getByRole('button', { name: '添加第一个网站', exact: true }).click()
  const panel = page.locator('.website-drawer')
  await expect(panel).toBeVisible()
  expect(
    await panel.evaluate((el) =>
      Math.abs(
        el.getBoundingClientRect().x + el.getBoundingClientRect().width / 2 - innerWidth / 2,
      ),
    ),
  ).toBeLessThan(3)
  await page.getByLabel('搜索内置网站').fill('不存在')
  await expect(panel.getByRole('heading', { name: '没有找到内置网站' })).toBeVisible()
  await panel.getByRole('button', { name: '清除搜索', exact: true }).click()
  await panel.getByRole('button', { name: '添加 NodeSeek', exact: true }).click()
  await expect(panel).not.toBeVisible()
  await page.getByRole('button', { name: '添加网站', exact: true }).click()
  await expect(panel.getByRole('button', { name: '已添加', exact: true })).toBeDisabled()
  await page.keyboard.press('Escape')
  await expect(panel).not.toBeVisible()
  await page.getByRole('button', { name: '配置 NodeSeek', exact: true }).click()
  await expect(panel).toBeVisible()
  expect(
    await panel.evaluate((el) => Math.abs(el.getBoundingClientRect().right - innerWidth)),
  ).toBeLessThan(3)
  const savedInterval = (await workspace(page)).websites[0].interval
  await page.getByLabel('共享采集间隔').fill('9')
  await panel.getByRole('button', { name: '保存设置', exact: true }).click()
  await expect(panel.getByRole('alert')).toContainText('10–3600')
  expect((await workspace(page)).websites[0].interval).toBe(savedInterval)
  const updatedInterval = savedInterval === 35 ? 45 : 35
  await page.getByLabel('共享采集间隔').fill(String(updatedInterval))
  await page.keyboard.press('Escape')
  await page
    .getByRole('dialog', { name: '关闭网站配置？' })
    .getByRole('button', { name: '继续编辑', exact: true })
    .click()
  await expect(page.getByLabel('共享采集间隔')).toHaveValue(String(updatedInterval))
  await panel.getByRole('button', { name: '保存设置', exact: true }).click()
  await expect.poll(async () => (await workspace(page)).websites[0].interval).toBe(updatedInterval)
  await panel.getByRole('button', { name: '关闭网站面板', exact: true }).click()
  await page.reload()
  await page.getByRole('button', { name: '配置 NodeSeek', exact: true }).click()
  await expect(page.getByLabel('共享采集间隔')).toHaveValue(String(updatedInterval))
  await page.getByLabel('共享采集间隔').fill(String(updatedInterval + 10))
  await panel.getByRole('button', { name: '关闭网站面板', exact: true }).click()
  await page
    .getByRole('dialog', { name: '关闭网站配置？' })
    .getByRole('button', { name: '放弃修改并关闭', exact: true })
    .click()
  expect((await workspace(page)).websites[0].interval).toBe(updatedInterval)
  await page.getByRole('button', { name: '配置 NodeSeek', exact: true }).click()
  await panel.getByRole('button', { name: '移除网站', exact: true }).click()
  await page
    .getByRole('dialog', { name: '移除 NodeSeek？' })
    .getByRole('button', { name: '确认移除', exact: true })
    .click()
  await expect(page.getByRole('heading', { name: '从第一个关心的网站开始' })).toBeVisible()
  expect((await workspace(page)).websites).toEqual([])
})

test('all four target forms validate and save encrypted configuration without browser secrets', async ({
  page,
}, info) => {
  for (const channel of ['Telegram Bot', 'Bark', 'SMTP', 'Webhook']) {
    await page.goto('/#/target/new')
    await page.getByRole('button', { name: channel, exact: true }).click()
    await page.getByRole('button', { name: '保存目标', exact: true }).click()
    await expect(page.getByRole('alert')).toContainText('请填写目标名称')
    await page.getByLabel('目标名称').fill(channel + ' UI ' + info.project.name)
    await page.getByRole('switch', { name: '启用通知目标', exact: true }).click()
    if (channel === 'Telegram Bot') {
      await page.getByLabel('Bot Token').fill('123456:synthetic_ui_token')
      await page.getByLabel('Chat ID').fill('-100123456')
    } else if (channel === 'Bark') {
      await page.getByLabel('设备 Key').fill('synthetic-ui-device')
    } else if (channel === 'SMTP') {
      await page.getByLabel('SMTP 服务器').fill('smtp.example.test')
      await page.getByLabel('发件地址').fill('sender@example.test')
      await page.getByLabel('收件地址').fill('reader@example.test')
      await page.getByLabel('连接安全').selectOption('plain')
      await page.getByRole('button', { name: '保存目标', exact: true }).click()
      await expect(page.getByRole('alert')).toContainText('明确确认')
      await page.getByRole('checkbox', { name: '我了解明文连接不加密，明确允许此配置' }).check()
    } else {
      await page.getByLabel('Webhook URL').fill('https://receiver.example.test/synthetic-ui-secret')
      await page.getByLabel('自定义请求头').fill('{"Host":"blocked"}')
      await page.getByRole('button', { name: '保存目标', exact: true }).click()
      await expect(page.getByRole('alert')).toContainText('不能包含保留头')
      await page.getByLabel('自定义请求头').fill('{"X-Synthetic-Key":"synthetic-ui-header"}')
    }
    await page.getByRole('button', { name: '保存目标', exact: true }).click()
    await expect(page).toHaveURL(/#\/notifications\/targets$/)
    const target = (await workspace(page)).targets.find(
      (target: any) => target.name === channel + ' UI ' + info.project.name,
    )
    expect(target.enabled).toBe(false)
  }
  await expect(page.locator('.notification-card')).toHaveCount(4)
  const publicData = JSON.stringify(await workspace(page))
  const browserData = await page.evaluate(() =>
    JSON.stringify({ ...localStorage, ...sessionStorage }),
  )
  for (const secret of [
    'synthetic_ui_token',
    'synthetic-ui-device',
    'synthetic-ui-secret',
    'synthetic-ui-header',
  ]) {
    expect(publicData).not.toContain(secret)
    expect(browserData).not.toContain(secret)
  }
})
