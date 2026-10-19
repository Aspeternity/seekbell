import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { readFile } from 'node:fs/promises'

async function go(page: Page, path: string) {
  await page.goto('/prototype.html#' + path)
  await expect(page.locator('h1')).toBeVisible()
}
test.beforeEach(async ({ page }) => {
  await page.route('**/*', (route) => {
    const url = new URL(route.request().url())
    if (
      url.hostname !== '127.0.0.1' ||
      url.pathname.startsWith('/api') ||
      url.pathname.startsWith('/health')
    )
      throw new Error('Unexpected live request ' + url.origin + url.pathname)
    return route.continue()
  })
  await page.goto('/prototype.html#/')
  await page.getByRole('button', { name: '载入示例工作台', exact: true }).click()
  await page.getByRole('button', { name: '确认载入', exact: true }).click()
})

test('all pages render without errors, remain responsive and provide review screenshots', async ({
  page,
}, info) => {
  test.setTimeout(90000)
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  page.on('console', (m) => {
    if (['warning', 'error'].includes(m.type())) errors.push(m.text())
  })
  const routes = [
    ['overview', '/'],
    ['tasks', '/tasks'],
    ['websites', '/websites'],
    ['content', '/content'],
    ['content-detail', '/content/post-1'],
    ['targets', '/notifications/targets'],
    ['deliveries', '/notifications/deliveries'],
    ['delivery-detail', '/notifications/deliveries/d-4'],
    ['tests', '/notifications/tests'],
    ['target-telegram', '/target/telegram'],
    ['target-bark', '/target/bark'],
    ['target-smtp', '/target/smtp'],
    ['target-webhook', '/target/webhook'],
    ['preferences', '/settings/preferences'],
    ['account', '/settings/account'],
    ['backup', '/settings/backup'],
    ['about', '/settings/about'],
    ['not-found', '/does-not-exist'],
    ['setup', '/setup'],
    ['login', '/login'],
  ]
  for (const [name, path] of routes) {
    await go(page, path!)
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      name,
    ).toBe(true)
    await page.screenshot({ path: info.outputPath(name + '.png'), fullPage: true })
    const original = page.viewportSize()!
    for (const width of [320, 768, 1024]) {
      await page.setViewportSize({ width, height: 900 })
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
        name + ' at ' + width,
      ).toBe(true)
    }
    await page.setViewportSize(original)
  }
  expect(errors).toEqual([])
})

test('task list copies, saves, deletes and preserves historical snapshots', async ({ page }) => {
  await go(page, '/tasks')
  await page.getByRole('button', { name: '复制好价服务器雷达', exact: true }).click()
  await expect(page.getByLabel('任务名称')).toHaveValue('好价服务器雷达 · 副本')
  await expect(page.getByRole('switch', { name: '启用任务', exact: true })).not.toBeChecked()
  await page.getByRole('button', { name: '保存任务', exact: true }).click()
  await expect(page).toHaveURL(/#\/tasks$/)
  await expect(page.locator('.management-row')).toHaveCount(5)
  await page.getByRole('button', { name: '删除好价服务器雷达 · 副本', exact: true }).click()
  await page.getByRole('button', { name: '删除任务', exact: true }).click()
  await expect(page.locator('.management-row')).toHaveCount(4)
  await page.getByRole('button', { name: '删除好价服务器雷达', exact: true }).click()
  await page.getByRole('button', { name: '删除任务', exact: true }).click()
  await go(page, '/content/post-1')
  await expect(page.getByText('好价服务器雷达 · 已删除')).toBeVisible()
  await page.reload()
  await expect(page.getByText('好价服务器雷达 · 已删除')).toBeVisible()
})

test('source settings persist and source state is linked to overview', async ({ page }) => {
  await go(page, '/websites')
  await page.getByRole('button', { name: '配置 NodeSeek', exact: true }).click()
  await page.getByLabel('共享采集间隔').fill('25')
  await page.getByRole('button', { name: '保存设置', exact: true }).click()
  await page.reload()
  await page.getByRole('button', { name: '配置 NodeSeek', exact: true }).click()
  await expect(page.getByLabel('共享采集间隔')).toHaveValue('25')
  await page
    .locator('.website-drawer')
    .getByRole('switch', { name: 'NodeSeek 采集启用状态' })
    .click()
  await page.getByRole('button', { name: '暂停网站', exact: true }).click()
  await go(page, '/')
  await expect(page.getByText('部分网站已暂停，关联任务暂不采集新帖。')).toBeVisible()
  await page.getByRole('button', { name: '查看网站', exact: true }).click()
  await page.getByRole('button', { name: '配置 NodeSeek', exact: true }).click()
  await page
    .locator('.website-drawer')
    .getByRole('switch', { name: 'NodeSeek 采集启用状态' })
    .click()
  await page.getByLabel('模拟场景').selectOption('error')
  await page.getByRole('button', { name: '测试连接（模拟）' }).click()
  await expect(page.locator('.match-result[role=status]')).toContainText('模拟连接失败')
  await go(page, '/')
  await expect(page.getByText('来源连接异常，请检查采集设置。')).toBeVisible()
})

test('content filters, pagination and details link to delivery records', async ({ page }) => {
  await go(page, '/content')
  await expect(page.locator('.content-row')).toHaveCount(5)
  await page.getByRole('button', { name: '下一页内容' }).click()
  await expect(page.locator('.content-row')).toHaveCount(1)
  await page.getByLabel('匹配结果', { exact: true }).selectOption('unknown')
  await expect(page.locator('.content-row')).toHaveCount(1)
  await page.getByLabel('发现日期').selectOption('2026-10-18')
  await expect(page.getByRole('heading', { name: '没有符合条件的内容' })).toBeVisible()
  await page.getByRole('button', { name: '清除筛选' }).click()
  await page.getByLabel('搜索内容').fill('DMIT 洛杉矶')
  await page.locator('.content-title').click()
  await expect(page.getByRole('heading', { name: 'RSS 内容快照' })).toBeVisible()
  await page.locator('.compact-record .result-pill').first().click()
  await expect(page.getByRole('heading', { name: '投递详情', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '查看关联内容' }).click()
  await expect(page.getByRole('heading', { name: 'RSS 内容快照' })).toBeVisible()
})

test('four channel forms validate and save while keeping credentials out of storage', async ({
  page,
}) => {
  const marker = 'PrivateDemo-Only-927'
  for (const channel of ['Telegram Bot', 'Bark', 'SMTP', 'Webhook']) {
    await go(page, '/target/new')
    await page.getByRole('button', { name: channel, exact: true }).click()
    await page.getByRole('button', { name: '保存目标', exact: true }).click()
    await expect(page.getByRole('alert')).toContainText('请填写目标名称')
    await page.getByLabel('目标名称').fill('新建 ' + channel)
    if (channel === 'Telegram Bot') {
      await page.getByLabel('Bot Token').fill('123456:' + marker)
      await page.getByLabel('Chat ID').fill('-100123456')
    } else if (channel === 'Bark') {
      await page.getByLabel('设备 Key').fill(marker)
    } else if (channel === 'SMTP') {
      await page.getByLabel('SMTP 服务器').fill('smtp.example.test')
      await page.getByLabel('发件地址').fill('sender@example.test')
      await page.getByLabel('收件地址').fill('reader@example.test')
      await page.getByLabel('连接安全').selectOption('plain')
      await page.getByRole('button', { name: '保存目标', exact: true }).click()
      await expect(page.getByRole('alert')).toContainText('明文 SMTP')
      await page.getByRole('checkbox', { name: '我了解明文连接不加密，明确允许此配置' }).check()
    } else {
      await page.getByLabel('Webhook URL').fill('javascript:alert(1)')
      await page.getByRole('button', { name: '保存目标', exact: true }).click()
      await expect(page.getByRole('alert')).toContainText('HTTP(S)')
      await page.getByLabel('Webhook URL').fill('https://example.test/notify/' + marker)
      await page.getByLabel('自定义请求头').fill('{"X-Demo-Key":"' + marker + '"}')
    }
    await page.getByRole('button', { name: '保存目标', exact: true }).click()
    await expect(page).toHaveURL(/notifications\/targets$/)
    await expect(page.getByRole('button', { name: '新建 ' + channel, exact: true })).toBeVisible()
  }
  const stored = await page.evaluate(() => JSON.stringify(localStorage))
  expect(stored).not.toContain(marker)
  expect(stored).not.toContain('sender@example.test')
  expect(stored).not.toContain('smtp.example.test')
  await go(page, '/task/new')
  await expect(page.getByRole('checkbox', { name: '新建 Webhook Webhook' })).toBeVisible()
})

test('target test, uncertain resend and disabled target cancellation keep distinct records', async ({
  page,
}) => {
  await go(page, '/notifications/targets')
  await page
    .locator('.notification-card')
    .filter({ hasText: '家庭服务' })
    .getByRole('button', { name: '测试', exact: true })
    .click()
  await page.getByLabel('模拟结果', { exact: true }).selectOption('unknown')
  await page.getByRole('button', { name: '运行模拟测试' }).click()
  await expect(page.getByRole('dialog')).not.toBeVisible()
  await go(page, '/notifications/tests')
  await expect(page.locator('.delivery-row')).toHaveCount(1)
  await expect(page.locator('.delivery-row')).toContainText('结果未知')
  await go(page, '/notifications/deliveries/d-4')
  await page.getByRole('button', { name: '手动重发（模拟）' }).click()
  await expect(page.getByRole('dialog')).toContainText('重发可能重复')
  await page.getByRole('button', { name: '确认模拟重发' }).click()
  await go(page, '/notifications/deliveries')
  await expect(page.locator('.delivery-row')).toHaveCount(6)
  await expect(page.locator('.delivery-row').filter({ hasText: '手动重发' })).toHaveCount(1)
  await go(page, '/notifications/targets')
  await page.getByRole('switch', { name: '我的 iPhone启用状态' }).click()
  await go(page, '/notifications/deliveries/d-3')
  await expect(page.locator('.reading-panel')).toContainText('已取消')
  await expect(page.getByRole('button', { name: '手动重发（模拟）' })).toHaveCount(0)
  await go(page, '/notifications/targets')
  await page.getByRole('switch', { name: '我的 iPhone启用状态' }).click()
  await go(page, '/notifications/deliveries/d-3')
  await expect(page.locator('.reading-panel')).toContainText('已取消')
})

test('preferences, safe backup export and validated restore work end to end', async ({ page }) => {
  await go(page, '/settings/preferences')
  await page.getByLabel('显示时区').selectOption('UTC')
  await page.getByLabel('普通历史保留天数').fill('60')
  await page.getByRole('button', { name: '保存偏好设置' }).click()
  await go(page, '/content/post-1')
  await expect(page.locator('.subtitle')).toContainText('06:28')
  await go(page, '/settings/backup')
  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: '下载演示备份' }).click()
  const download = await downloadPromise
  const raw = await readFile((await download.path())!, 'utf8')
  const backup = JSON.parse(raw)
  expect(backup.kind).toBe('seekbell-demo-backup')
  expect(backup.data.settings.retention).toBe(60)
  expect(raw).not.toContain('digest')
  const input = page.getByLabel('选择演示备份文件')
  await input.setInputFiles({
    name: 'invalid.json',
    mimeType: 'application/json',
    buffer: Buffer.from('{"kind":"seekbell-demo-backup","data":{}}'),
  })
  await expect(page.getByRole('alert')).toContainText('不是兼容')
  backup.data.tasks[0].name = '从备份恢复的任务'
  backup.data.targets[0].bot_token = 'must-not-persist'
  await input.setInputFiles({
    name: 'valid.json',
    mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify(backup)),
  })
  await page.getByRole('button', { name: '确认恢复这份备份' }).click()
  await page.getByRole('button', { name: '确认恢复', exact: true }).click()
  await go(page, '/tasks')
  await expect(page.getByRole('button', { name: '从备份恢复的任务', exact: true })).toBeVisible()
  expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toContain('must-not-persist')
  await page.reload()
  await expect(page.getByRole('button', { name: '从备份恢复的任务', exact: true })).toBeVisible()
})

test('initialize unique administrator, login failure, password change and logout', async ({
  page,
}) => {
  await go(page, '/setup')
  await page.getByLabel('管理员用户名').fill('demo_admin')
  await page.getByLabel('设置演示密码').fill('ExamplePass!123')
  await page.getByLabel('确认密码', { exact: true }).fill('mismatch')
  await page.getByRole('button', { name: '创建管理员并进入' }).click()
  await expect(page.getByRole('alert')).toContainText('不一致')
  await page.getByLabel('确认密码', { exact: true }).fill('ExamplePass!123')
  await page.getByRole('button', { name: '创建管理员并进入' }).click()
  await expect(page).toHaveURL(/#\/$/)
  await go(page, '/setup')
  await expect(page.getByRole('heading', { name: '管理员已经就绪' })).toBeVisible()
  await page.getByRole('button', { name: '前往登录' }).click()
  await page.getByLabel('演示密码', { exact: true }).fill('wrong-password')
  await page.getByRole('button', { name: '登录工作空间' }).click()
  await expect(page.getByRole('alert')).toContainText('不正确')
  await page.getByLabel('演示密码', { exact: true }).fill('ExamplePass!123')
  await page.getByRole('button', { name: '登录工作空间' }).click()
  await go(page, '/settings/account')
  await page.getByLabel('当前演示密码').fill('ExamplePass!123')
  await page.getByLabel('新密码 不修改则留空').fill('AnotherDemo!456')
  await page.getByLabel('确认新密码').fill('AnotherDemo!456')
  await page.getByRole('button', { name: '更新管理员资料' }).click()
  await expect(page.getByRole('status')).toContainText('已更新')
  await page.getByRole('button', { name: '退出演示登录' }).click()
  await go(page, '/tasks')
  await expect(page).toHaveURL(/#\/login$/)
  await page.getByLabel('演示密码', { exact: true }).fill('AnotherDemo!456')
  await page.getByRole('button', { name: '登录工作空间' }).click()
  await expect(page).toHaveURL(/#\/$/)
  const storage = await page.evaluate(() => JSON.stringify(localStorage))
  expect(storage).not.toContain('ExamplePass!123')
  expect(storage).not.toContain('AnotherDemo!456')
})

test('unsaved settings are guarded on browser back and corrupt storage falls back', async ({
  page,
}) => {
  await go(page, '/tasks')
  if ((page.viewportSize()?.width || 0) < 761)
    await page.getByRole('button', { name: '打开导航' }).click()
  await page.getByRole('button', { name: '监控网站', exact: true }).click()
  await page.getByRole('button', { name: '配置 NodeSeek', exact: true }).click()
  await page.getByLabel('共享采集间隔').fill('77')
  await page.goBack()
  await expect(page.locator('.dialog[open]')).toContainText('尚未保存')
  await page.getByRole('button', { name: '继续编辑' }).click()
  await expect(page.getByLabel('共享采集间隔')).toHaveValue('77')
  await page.evaluate(() => localStorage.setItem('seekbell-demo-v3', '{"broken":true}'))
  page.on('dialog', (dialog) => dialog.accept())
  await page.reload()
  await expect(page.getByRole('heading', { name: '从第一个关心的网站开始' })).toBeVisible()
  await expect(page.getByRole('status')).toContainText('恢复默认')
})
