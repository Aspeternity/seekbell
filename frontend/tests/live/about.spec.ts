import { expect, test } from '@playwright/test'

const credentials = { username: 'browser_admin', password: 'Synthetic-2026-Password' }
test('about and diagnostics stay independent, retry safely and perform no configuration writes', async ({
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
  const original = await (await page.request.get('/api/version')).json()
  const workspace = await (await page.request.get('/api/manage/workspace')).json()
  const writes: string[] = []
  page.on('request', (request) => {
    if (request.method() !== 'GET') writes.push(request.method() + ' ' + request.url())
  })
  await page.goto('/#/settings/preferences')
  await page.goto('/#/settings/about')
  const about = page.getByRole('region', { name: '关于 SeekBell', exact: true })
  await expect(page.getByTestId('app-version')).toHaveText(original.version)
  const facts = page.getByRole('region', { name: '系统信息', exact: true })
  await expect(facts).toContainText('NodeSeek')
  await expect(facts).toContainText('LINUX DO')
  await expect(facts).toContainText('UTC')
  await expect(facts).toContainText('已运行')
  await expect(facts).toContainText('Python ')
  await expect(page.getByTestId('build-revision')).toBeHidden()
  await facts.getByText('构建信息', { exact: true }).click()
  await expect(page.getByTestId('build-revision')).toHaveText(original.build_revision)
  await expect(page.getByTestId('database-revision')).toHaveText(original.database_revision)
  await expect(page.getByText('本地开发构建，未固定代码提交版本。')).toBeVisible()
  for (const name of ['使用文档', '更新日志', '项目主页', '反馈问题'])
    await expect(about.getByRole('link', { name: new RegExp('^' + name) })).toHaveAttribute(
      'target',
      '_blank',
    )
  await expect(about.getByRole('button', { name: '复制诊断摘要' })).toHaveCount(0)
  await expect(page.getByRole('region', { name: '服务状态', exact: true })).toHaveCount(0)
  await page.reload()
  await expect(page.getByTestId('app-version')).toHaveText(original.version)
  const category = page.getByRole('combobox', { name: '设置分类', exact: true })
  if (await category.isVisible()) await expect(category).toHaveAttribute('data-value', 'about')
  else {
    const selected = page
      .getByRole('navigation', { name: '设置分类', exact: true })
      .getByRole('button', { name: '关于', exact: true })
    await expect(selected).toBeInViewport({ ratio: 1 })
    await expect(selected).toHaveAttribute('aria-current', 'page')
  }
  // The existing compact mobile header intentionally hides the help control.
  if (info.project.name === 'desktop') {
    await page.getByRole('button', { name: '使用说明', exact: true }).click()
    await expect(page.getByRole('dialog')).toContainText('关闭浏览器不影响后台监控')
    await expect(page.getByRole('dialog')).toContainText('备份可在系统设置中直接恢复')
    await page.getByRole('button', { name: '知道了', exact: true }).click()
  }

  // A failed read is shown in place with a retry, and never invents values.
  const real = await (await page.request.get('/api/manage/about')).json()
  await page.route('**/api/manage/about', (route) => route.fulfill({ status: 503, json: {} }))
  await page.reload()
  await expect(facts.getByRole('alert')).toBeVisible()
  await expect(page.getByTestId('app-version')).toHaveCount(0)
  const fixed = '0123456789abcdef'.repeat(4)
  await page.unroute('**/api/manage/about')
  await page.route('**/api/manage/about', (route) =>
    route.fulfill({ json: { ...real, build_revision: fixed, database_revision: null } }),
  )
  await facts.getByRole('button', { name: '重新加载', exact: true }).click()
  await facts.getByText('构建信息', { exact: true }).click()
  await expect(page.getByTestId('build-revision')).toHaveText(fixed)
  await expect(page.getByTestId('database-revision')).toHaveText('未记录迁移版本')
  await expect(page.getByText('本地开发构建，未固定代码提交版本。')).toHaveCount(0)
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
  await page.unroute('**/api/manage/about')
  await page.reload()
  await facts.getByText('构建信息', { exact: true }).click()
  await expect(page.getByTestId('build-revision')).toHaveText(original.build_revision)
  await page.setViewportSize(
    info.project.name === 'mobile' ? { width: 390, height: 844 } : { width: 1440, height: 1000 },
  )
  await page.screenshot({ path: info.outputPath('about-version.png'), fullPage: true })

  // Diagnostics keeps the readiness/runtime status that used to share the About page.
  await page.goto('/#/settings/diagnostics')
  await expect(page.getByText('已就绪', { exact: true })).toBeVisible()
  await page.route('**/health/ready', (route) =>
    route.fulfill({
      status: 503,
      json: { status: 'unavailable' },
    }),
  )
  await page.route('**/api/manage/runtime', (route) =>
    route.fulfill({
      json: { active: false, status: 'failed', code: 'delivery_stopped' },
    }),
  )
  await page.getByRole('button', { name: '刷新运行信息', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('未就绪')
  await expect(page.getByText('异常停止', { exact: true })).toBeVisible()
  await expect(page.getByText('delivery_stopped', { exact: true })).toBeVisible()
  await expect(page.getByText('已就绪', { exact: true })).toHaveCount(0)
  await page.screenshot({ path: info.outputPath('diagnostics-unready.png'), fullPage: true })
  // A malformed health response must never be presented as ready.
  await page.unroute('**/health/ready')
  await page.route('**/health/ready', (route) => route.fulfill({ json: { status: 'unexpected' } }))
  await page.getByRole('button', { name: '刷新运行信息', exact: true }).click()
  const status = page.getByRole('region', { name: '服务状态', exact: true })
  await expect(status.getByRole('alert').filter({ hasText: '无法读取就绪状态' })).toContainText(
    '上次结果',
  )
  await expect(page.getByText('已就绪', { exact: true })).toHaveCount(0)
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
  await page.unroute('**/health/ready')
  await page.unroute('**/api/manage/runtime')
  await page.getByRole('button', { name: '刷新运行信息', exact: true }).click()
  await expect(page.getByText('已就绪', { exact: true })).toBeVisible()
  expect(await (await page.request.get('/api/manage/workspace')).json()).toEqual(workspace)
  expect(writes).toEqual([])

  await page.goto('/#/settings/backup')
  await expect(page.getByRole('button', { name: '生成并下载加密备份' })).toBeVisible()
  await page.getByRole('button', { name: '恢复备份', exact: true }).click()
  await expect(
    page
      .getByRole('form', { name: '从文件恢复', exact: true })
      .getByRole('button', { name: '恢复备份', exact: true }),
  ).toBeDisabled()
  await page.goto('/#/settings/unknown')
  await expect(page.getByRole('heading', { name: '这条线索暂时不在这里' })).toBeVisible()
  await page.goto('/#/settings/about')
  await expect(page.getByTestId('app-version')).toHaveText(original.version)
  // Session expiry on the authenticated About read still returns to login.
  await page.route('**/api/manage/about', (route) =>
    route.fulfill({
      status: 401,
      json: { detail: '请重新登录。' },
    }),
  )
  await page.reload()
  await expect(page.getByRole('heading', { name: '欢迎回来' })).toBeVisible()
  expect(errors).toEqual([])
})
