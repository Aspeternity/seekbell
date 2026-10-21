import { expect, test } from '@playwright/test'
const credentials = { username: 'tls_browser_admin', password: 'Synthetic-TLS-Browser-2026' }
test('real TLS proxy preserves secure sessions, configuration and logout', async ({
  page,
  context,
}, info) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.route('**/*', (route) => {
    if (new URL(route.request().url()).hostname !== '127.0.0.1')
      throw new Error('Unexpected external request')
    return route.continue()
  })
  await page.goto('/')
  const initial = await (await page.request.get('/api/auth/status')).json()
  await page.getByLabel('管理员用户名').fill(credentials.username)
  await page
    .getByLabel(initial.initialized ? '密码' : '设置密码', { exact: true })
    .fill(credentials.password)
  if (!initial.initialized)
    await page.getByLabel('确认密码', { exact: true }).fill(credentials.password)
  await page
    .getByRole('button', { name: initial.initialized ? '登录工作空间' : '创建管理员并进入' })
    .click()
  await expect(page.locator('.sidebar')).toBeAttached()
  expect(await page.evaluate(() => window.isSecureContext)).toBe(true)
  const session = (await context.cookies()).find((cookie) => cookie.name === 'seekbell_session')
  expect(session?.secure).toBe(true)
  expect(session?.httpOnly).toBe(true)
  expect(session?.sameSite).toBe('Strict')
  await page.goto('/#/settings/preferences')
  const workspace = 'TLS ' + info.project.name
  await page.getByLabel('工作空间名称', { exact: true }).fill(workspace)
  await page.getByRole('button', { name: '保存偏好设置' }).click()
  await expect(page.locator('.sidebar .workspace-copy strong')).toHaveText(workspace)
  await page.reload()
  await expect(page.getByLabel('工作空间名称', { exact: true })).toHaveValue(workspace)
  await page.screenshot({ path: info.outputPath('tls-workspace.png'), fullPage: true })
  const auth = await (await page.request.get('/api/auth/status')).json()
  const rejected = await page.request.post('/api/auth/logout', {
    headers: { 'X-CSRF-Token': auth.csrf, Origin: 'https://other.example.test' },
  })
  expect(rejected.status()).toBe(403)
  await page.getByRole('button', { name: '管理员', exact: true }).click()
  await page.locator('#main-content').getByRole('button', { name: '退出登录', exact: true }).click()
  await expect(page.getByRole('heading', { name: '欢迎回来' })).toBeVisible()
  await page.getByLabel('管理员用户名').fill(credentials.username)
  await page.getByLabel('密码', { exact: true }).fill(credentials.password)
  await page.getByRole('button', { name: '登录工作空间' }).click()
  await expect(page.locator('.sidebar .workspace-copy strong')).toHaveText(workspace)
  expect(errors).toEqual([])
})
