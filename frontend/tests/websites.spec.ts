import { expect, test } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.route('**/*', (route) => {
    const url = new URL(route.request().url())
    if (
      url.hostname !== '127.0.0.1' ||
      url.pathname.startsWith('/api') ||
      url.pathname.startsWith('/health')
    )
      throw new Error('Unexpected real request')
    return route.continue()
  })
  await page.goto('/prototype.html#/websites')
})

test('fresh workspace, catalog, website configuration and removal are complete', async ({
  page,
}, info) => {
  test.setTimeout(60000)
  await expect(page.getByRole('heading', { name: '从第一个关心的网站开始' })).toBeVisible()
  await expect(page.locator('.website-card')).toHaveCount(0)
  await page.screenshot({ path: info.outputPath('websites-empty.png'), fullPage: true })
  await page.getByRole('button', { name: '添加第一个网站' }).click()
  const drawer = page.locator('.website-drawer')
  await expect(drawer).toBeVisible()
  await expect(page.locator('.catalog-card')).toHaveCount(1)
  await page.screenshot({ path: info.outputPath('websites-catalog.png'), fullPage: false })
  await page.getByLabel('搜索内置网站').fill('不存在')
  await expect(page.getByText('没有找到内置网站')).toBeVisible()
  await page.getByRole('button', { name: '清除搜索' }).click()
  await page.getByRole('button', { name: '添加 NodeSeek', exact: true }).click()
  await expect(drawer).not.toBeVisible()
  await page.goto('/prototype.html#/task/new')
  await expect(page.getByRole('combobox', { name: '监控网站', exact: true })).toBeVisible({
    timeout: 15000,
  })
  await expect(page.getByRole('combobox', { name: '监控网站', exact: true })).toContainText(
    'NodeSeek',
  )
  const empty = page.locator('.target-empty')
  const notice = await empty.locator('.warning-note').boundingBox()
  const add = await empty.getByRole('button', { name: '添加通知目标', exact: true }).boundingBox()
  const explanation = await page.locator('.target-explanation').boundingBox()
  expect(add!.y - notice!.y - notice!.height).toBeGreaterThanOrEqual(11.5)
  expect(explanation!.y - add!.y - add!.height).toBeGreaterThanOrEqual(15.5)
  await page
    .locator('#delivery')
    .screenshot({ path: info.outputPath('task-empty-notifications.png') })
  await page.goto('/prototype.html#/websites')
  await page.getByRole('button', { name: '配置 NodeSeek', exact: true }).click()
  await expect(page.getByLabel('共享采集间隔')).toHaveValue('10')
  await expect(drawer.getByRole('switch')).not.toBeChecked()
  await page.getByLabel('共享采集间隔').fill('9')
  await page.getByRole('button', { name: '保存设置', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('10–3600')
  await page.getByLabel('共享采集间隔').fill('30')
  await page.keyboard.press('Escape')
  await expect(page.locator('.dialog[open]')).toContainText('尚未保存')
  await page.getByRole('button', { name: '继续编辑', exact: true }).click()
  await expect(page.getByLabel('共享采集间隔')).toHaveValue('30')
  await page.getByRole('button', { name: '保存设置', exact: true }).click()
  await drawer.getByRole('switch').click()
  await page.getByRole('button', { name: '测试连接（模拟）' }).click()
  await expect(drawer.locator('.match-result')).toContainText('模拟连接成功')
  await drawer.locator('.website-drawer-body').evaluate((e) => e.scrollTo(0, 0))
  await page.screenshot({ path: info.outputPath('websites-config.png'), fullPage: false })
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    expect(await drawer.evaluate((e) => e.scrollWidth <= e.clientWidth)).toBe(true)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
  await page.getByRole('button', { name: '关闭网站面板' }).click()
  await expect(page.getByRole('button', { name: '添加第一个网站' })).toHaveCount(0)
  await page.reload()
  await expect(page.locator('.website-card')).toContainText('30')
  await page.getByRole('button', { name: '添加网站', exact: true }).click()
  await expect(page.getByRole('button', { name: '已添加', exact: true })).toBeDisabled()
  await page.keyboard.press('Escape')
  await expect(drawer).not.toBeVisible()
  await expect(page.getByRole('button', { name: '添加网站', exact: true })).toBeFocused()
  await page.getByLabel('搜索已添加网站').fill('none')
  await expect(page.getByText('没有匹配的网站')).toBeVisible()
  await page.getByRole('button', { name: '清除筛选' }).click()
  await page.getByRole('button', { name: '配置 NodeSeek', exact: true }).click()
  await page.getByRole('button', { name: '移除网站', exact: true }).click()
  await page.getByRole('button', { name: '确认移除', exact: true }).click()
  await expect(page.getByRole('heading', { name: '从第一个关心的网站开始' })).toBeVisible()
  await page.reload()
  await expect(page.locator('.website-card')).toHaveCount(0)
  await page.goto('/prototype.html#/task/new')
  await expect(page.getByRole('heading', { name: '先添加一个监控网站' })).toBeVisible()
  await page.goto('/prototype.html#/')
  await expect(page.getByText('合计 0 条')).toBeVisible()
  await expect(page.locator('.activity-row')).toHaveCount(0)
})

test('existing v2 work migrates without loss and attached tasks prevent removal', async ({
  page,
}, info) => {
  await page.getByRole('button', { name: '载入示例工作台', exact: true }).click()
  await page.getByRole('button', { name: '确认载入', exact: true }).click()
  await page.evaluate(() => {
    const data = JSON.parse(localStorage.getItem('seekbell-demo-v3')!)
    const source = { ...data.websites[0], interval: 45 }
    delete source.id
    delete source.adapterId
    const legacy = { ...data, version: 2, source }
    delete legacy.websites
    delete legacy.settings.workspaceName
    delete legacy.settings.workspaceDescription
    legacy.tasks.forEach((t: Record<string, unknown>) => {
      delete t.websiteId
    })
    legacy.posts.forEach((p: Record<string, unknown>) => {
      delete p.websiteId
    })
    legacy.tasks[0].name = '保留我的旧任务'
    localStorage.setItem('seekbell-demo-v2', JSON.stringify(legacy))
    localStorage.removeItem('seekbell-demo-v3')
  })
  await page.reload()
  await page.screenshot({ path: info.outputPath('websites-cards.png'), fullPage: true })
  await page.getByRole('button', { name: '配置 NodeSeek', exact: true }).click()
  await expect(page.getByLabel('共享采集间隔')).toHaveValue('45')
  await expect(page.locator('.website-linked-task')).toHaveCount(4)
  await expect(page.locator('.website-linked-task').first()).toContainText('保留我的旧任务')
  await expect(page.getByRole('button', { name: '移除网站', exact: true })).toBeDisabled()
  await page.getByLabel('共享采集间隔').fill('60')
  await page.getByRole('button', { name: '关闭网站面板' }).click()
  await page.getByRole('button', { name: '放弃修改并关闭' }).click()
  await page.getByRole('button', { name: '配置 NodeSeek', exact: true }).click()
  await expect(page.getByLabel('共享采集间隔')).toHaveValue('45')
  await page.getByRole('button', { name: '管理任务', exact: true }).click()
  await expect(page.locator('.management-row')).toHaveCount(4)
  await page.getByRole('button', { name: '保留我的旧任务', exact: true }).click()
  await expect(page.locator('.task-website-picker')).toContainText('NodeSeek')
  await expect(page.getByRole('combobox', { name: '监控网站', exact: true })).toBeDisabled()
})

test('future built-in adapters keep independent settings in the same card layout', async ({
  page,
}) => {
  test.setTimeout(60000)
  // Test-only catalog fixtures. No additional adapters or unsupported sites are shipped.
  await page.route('**/src/prototype/websites*', async (route) => {
    const response = await route.fetch()
    await route.fulfill({
      response,
      body:
        (await response.text()) +
        "\n; for (let i = 2; i <= 4; i++) websiteCatalog.push({ ...websiteCatalog[0], id: 'fixture-' + i, name: '适配测试 ' + i, domain: 'fixture-' + i + '.test', sourceUrl: 'https://fixture-' + i + '.test/rss' });",
    })
  })
  await page.reload()
  for (const name of ['NodeSeek', '适配测试 2', '适配测试 3', '适配测试 4']) {
    await page.getByRole('button', { name: '添加网站', exact: true }).click()
    await page.getByRole('button', { name: '添加 ' + name, exact: true }).click()
    await expect(page.locator('.website-drawer')).not.toBeVisible()
  }
  await expect(page.locator('.website-card')).toHaveCount(4)
  await page.getByRole('button', { name: '配置 适配测试 2', exact: true }).click()
  await page.getByLabel('共享采集间隔').fill('90')
  await page.getByRole('button', { name: '保存设置', exact: true }).click()
  await page.locator('.website-drawer').getByRole('switch').click()
  await page.getByLabel('模拟场景').selectOption('error')
  await page.getByRole('button', { name: '测试连接（模拟）' }).click()
  await expect(page.locator('.match-result')).toContainText('模拟连接失败')
  await page.getByRole('button', { name: '关闭网站面板' }).click()
  const records = await page.evaluate(
    () => JSON.parse(localStorage.getItem('seekbell-demo-v3')!).websites,
  )
  expect(records[0]).toMatchObject({ interval: 10, enabled: false, health: 'pending' })
  expect(records[1]).toMatchObject({ interval: 90, enabled: true, health: 'error' })
  expect(records[2]).toMatchObject({ interval: 10, enabled: false, health: 'pending' })
  await page.getByLabel('筛选网站状态').selectOption('error')
  await expect(page.locator('.website-card')).toHaveCount(1)
  await expect(page.locator('.website-card')).toContainText('适配测试 2')
  await page.getByLabel('筛选网站状态').selectOption('all')
  for (const width of [320, 390, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
  await page.goto('/prototype.html#/task/new')
  await expect(page.getByRole('combobox', { name: '监控网站', exact: true })).toBeVisible({
    timeout: 15000,
  })
  const picker = page.getByRole('combobox', { name: '监控网站', exact: true })
  await expect(picker).toHaveText('请选择监控网站')
  await expect(page.locator('.editor-title-line')).toContainText('待选择网站')
  await expect(page.locator('.rule-summary')).toContainText('请选择监控网站')
  await expect(page.locator('.rule-summary')).not.toContainText('NodeSeek')
  await expect(
    page.getByText('该网站已暂停。任务可以保存，启用网站后才会采集新帖。', { exact: true }),
  ).toHaveCount(0)
  await page.getByRole('button', { name: '保存任务', exact: true }).click()
  await expect(page.locator('[data-form-errors]')).toContainText('请选择已添加的监控网站')
  expect(
    await page.evaluate(() => JSON.parse(localStorage.getItem('seekbell-demo-v3')!).tasks.length),
  ).toBe(0)
  await picker.click()
  const menu = page.locator('.task-website-menu')
  await expect(menu.getByRole('option')).toHaveCount(4)
  await menu.getByRole('option', { name: '适配测试 2', exact: true }).click()
  await expect(picker).toContainText('适配测试 2')
  await picker.click()
  await page.keyboard.press('ArrowDown')
  await page.keyboard.press('Enter')
  await expect(picker).toContainText('适配测试 3')
  await picker.click()
  await page.keyboard.press('Escape')
  await expect(menu).not.toBeVisible()
  await page.locator('#task-name').click()
  await expect(menu).not.toBeVisible()
})

test('workspace identity saves, validates, persists and upgrades older settings', async ({
  page,
}, info) => {
  await page.goto('/prototype.html#/settings/preferences')
  await page.getByLabel('工作空间名称', { exact: true }).fill('   ')
  await page.getByRole('button', { name: '保存偏好设置', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('不能只包含空格')
  await page.getByLabel('工作空间名称', { exact: true }).fill('Asp 的信息雷达')
  await page.getByLabel('工作空间说明 选填', { exact: true }).fill('技术、好价与日常关注')
  await expect(page.locator('.workspace-preview')).toContainText('Asp 的信息雷达')
  await expect(page.locator('.workspace-label')).toContainText('个人工作空间')
  await page.getByRole('button', { name: '保存偏好设置', exact: true }).click()
  await expect(page.locator('.workspace-label')).toContainText('Asp 的信息雷达')
  await expect(page.locator('.workspace-label .workspace-icon')).toHaveText('A')
  await page.reload()
  await expect(page.getByLabel('工作空间名称', { exact: true })).toHaveValue('Asp 的信息雷达')
  await expect(page.locator('.workspace-label')).toContainText('技术、好价与日常关注')
  await page.locator('h1').focus()
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: info.outputPath('workspace-settings.png'), fullPage: true })
  if ((page.viewportSize()?.width || 0) < 761)
    await page.getByRole('button', { name: '打开导航' }).click()
  await expect(page.getByRole('button', { name: '设置工作空间', exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: '系统设置', exact: true }).click()
  await expect(page).toHaveURL(/#\/settings\/preferences$/)
  await page
    .getByLabel('工作空间名称', { exact: true })
    .fill('这是一个用于验证侧栏省略显示的很长工作空间名称')
  await page.getByLabel('工作空间说明 选填', { exact: true }).fill('')
  await page.getByRole('button', { name: '保存偏好设置', exact: true }).click()
  await expect(page.locator('.workspace-label small')).toHaveCount(0)
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
  await page.evaluate(() => {
    const data = JSON.parse(localStorage.getItem('seekbell-demo-v3')!)
    delete data.settings.workspaceName
    delete data.settings.workspaceDescription
    data.settings.retention = 75
    localStorage.setItem('seekbell-demo-v3', JSON.stringify(data))
  })
  await page.reload()
  await expect(page.getByLabel('工作空间名称', { exact: true })).toHaveValue('个人工作空间')
  await expect(page.getByLabel('普通历史保留天数')).toHaveValue('75')
})

test('catalog is centered on desktop and configuration remains a separate right drawer', async ({
  page,
}) => {
  await page.getByRole('button', { name: '添加网站', exact: true }).click()
  const dialog = page.locator('.website-drawer')
  for (const width of [320, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    const bounds = await dialog.boundingBox()
    expect(bounds).not.toBeNull()
    if (width > 760) {
      expect(Math.abs(bounds!.x + bounds!.width / 2 - width / 2)).toBeLessThan(2)
      expect(Math.abs(bounds!.y + bounds!.height / 2 - 450)).toBeLessThan(2)
      expect(bounds!.height).toBeLessThanOrEqual(765)
    } else {
      expect(bounds!.width).toBe(width)
      expect(bounds!.height).toBe(900)
    }
    expect(await dialog.evaluate((e) => e.scrollWidth <= e.clientWidth)).toBe(true)
  }
  await page.getByRole('button', { name: '添加 NodeSeek', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  await expect(page.locator('.website-card')).toHaveCount(1)
  await page.getByRole('button', { name: '配置 NodeSeek', exact: true }).click()
  const bounds = await dialog.boundingBox()
  expect(Math.abs(bounds!.x + bounds!.width - 1440)).toBeLessThan(2)
  expect(bounds!.width).toBeCloseTo(638, 0)
  expect(Math.abs(bounds!.height - 900)).toBeLessThan(2)
  await expect(dialog).not.toHaveClass(/website-catalog-modal/)
})
