import { expect, test } from '@playwright/test'

const credentials = { username: 'browser_admin', password: 'Synthetic-2026-Password' }
test('sidebar logout protects drafts, retries failures and revokes the server session', async ({
  page,
  browser,
}, info) => {
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
  await expect(page.getByRole('button', { name: '管理员设置', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '设置工作空间', exact: true })).toHaveCount(0)
  await expect(page.locator('.profile-copy')).toContainText(credentials.username)
  await expect(page.locator('.profile').getByRole('button', { includeHidden: true })).toHaveCount(1)
  await expect(page.locator('button.overview-website-row')).toHaveCount(0)
  await page.goto('/#/settings/preferences')
  const draft = '未保存-' + info.project.name
  await page.getByLabel('工作空间名称', { exact: true }).fill(draft)
  const openMenu = async () => {
    if (info.project.name === 'mobile')
      await page.getByRole('button', { name: '打开导航', exact: true }).click()
  }
  await openMenu()
  await page.locator('.profile').screenshot({ path: info.outputPath('account-exit.png') })
  const exit = page.locator('.profile').getByRole('button', { name: '退出登录', exact: true })
  await expect(exit).toHaveAttribute('title', '退出登录')
  const replay = await browser.newContext({ storageState: await page.context().storageState() })
  try {
    await exit.click()
    await page.getByRole('button', { name: '继续编辑', exact: true }).click()
    expect((await page.request.get('/api/manage/workspace')).status()).toBe(200)
    await expect(page.getByLabel('工作空间名称', { exact: true })).toHaveValue(draft)
    // Keep the mobile drawer open after cancelling; only the explicit exit acts.
    await page.route(
      '**/api/auth/logout',
      (route) => route.fulfill({ status: 503, json: { detail: '合成注销暂不可用' } }),
      { times: 1 },
    )
    await exit.click()
    await page.getByRole('button', { name: '退出并放弃修改', exact: true }).click()
    await expect(
      page.getByRole('status').filter({ hasText: '退出登录失败：合成注销暂不可用' }),
    ).toBeVisible()
    await expect(exit).toBeEnabled()
    expect((await page.request.get('/api/manage/workspace')).status()).toBe(200)
    await expect(page.getByLabel('工作空间名称', { exact: true })).toHaveValue(draft)
    // Delay the real request long enough to verify duplicate-click prevention.
    await page.route(
      '**/api/auth/logout',
      async (route) => {
        await new Promise((resolve) => setTimeout(resolve, 250))
        await route.continue()
      },
      { times: 1 },
    )
    await page.screenshot({ path: info.outputPath('sidebar-exit.png'), fullPage: true })
    await exit.click()
    await page.getByRole('button', { name: '退出并放弃修改', exact: true }).click()
    await expect(page.locator('.profile-logout')).toBeDisabled()
    await expect(page.getByRole('heading', { name: '欢迎回来', exact: true })).toBeVisible()
    expect((await page.request.get('/api/manage/workspace')).status()).toBe(401)
    // A copied cookie from before logout must also lose access.
    expect((await replay.request.get('http://127.0.0.1:8011/api/manage/workspace')).status()).toBe(
      401,
    )
    await page.reload()
    await expect(page.getByRole('heading', { name: '欢迎回来', exact: true })).toBeVisible()
    await page.getByLabel('管理员用户名').fill(credentials.username)
    await page.getByLabel('密码', { exact: true }).fill(credentials.password)
    await page.getByRole('button', { name: '登录工作空间', exact: true }).click()
    await expect(page.getByTestId('overview-matches')).toBeVisible()
    await page.goto('/#/settings/preferences')
    await expect(page.getByLabel('工作空间名称', { exact: true })).not.toHaveValue(draft)
    await openMenu()
    await exit.click()
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await expect(page.getByRole('heading', { name: '欢迎回来', exact: true })).toBeVisible()
  } finally {
    await replay.close()
  }
})
