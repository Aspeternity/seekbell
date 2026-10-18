import { expect, test } from '@playwright/test'

const username = 'synthetic-browser-admin'
const password = 'synthetic browser long passphrase'
const origin = 'http://127.0.0.1:18765'

test('桌面和手机完成初始化、刷新、退出、错误密码与重新登录', async ({ browser }, testInfo) => {
  for (const width of [1280, 390]) {
    const context = await browser.newContext({ viewport: { width, height: 844 } })
    const external: string[] = []
    await context.route('**/*', async (route) => {
      if (new URL(route.request().url()).origin !== origin) {
        external.push(route.request().url())
        await route.abort()
      } else {
        await route.continue()
      }
    })
    const page = await context.newPage()
    const errors: string[] = []
    page.on('pageerror', (error) => errors.push(error.message))
    await page.goto('/')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(
      width === 1280 ? '创建你的管理员账号。' : '登录 SeekBell。',
    )
    await page.getByLabel('用户名', { exact: true }).fill(username)
    await page.getByLabel('密码', { exact: true }).fill(password)
    if (width === 1280) {
      await page.getByLabel('再次输入密码', { exact: true }).fill('a different long password')
      await page.getByRole('button', { name: '创建并登录' }).click()
      await expect(page.getByRole('alert')).toContainText('两次输入的密码不一致')
      await page.getByLabel('再次输入密码', { exact: true }).fill(password)
    }
    await page
      .getByRole('button', { name: width === 1280 ? '创建并登录' : '登录', exact: true })
      .click()
    await expect(page.getByRole('button', { name: '退出登录' })).toBeVisible()
    await expect(page.getByText('browser-synthetic', { exact: true })).toBeVisible()
    await page.reload()
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('欢迎回来。')
    await expect(page.locator('[aria-busy="true"]')).toHaveCount(0)
    expect(await page.evaluate(() => document.cookie)).not.toContain('seekbell_session')
    await page.screenshot({ path: testInfo.outputPath(`auth-${width}.png`), fullPage: true })
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      width,
    )
    await page.getByRole('button', { name: '退出登录' }).click()
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('登录 SeekBell。')
    await page.getByLabel('用户名', { exact: true }).fill(username)
    await page.getByLabel('密码', { exact: true }).fill('synthetic wrong long password')
    await page.getByRole('button', { name: '登录', exact: true }).click()
    await expect(page.getByRole('alert')).toContainText('用户名或密码不正确')
    await expect(page.getByLabel('密码', { exact: true })).toHaveValue('')
    await page.getByLabel('密码', { exact: true }).fill(password)
    await page.getByRole('button', { name: '登录', exact: true }).click()
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('欢迎回来。')
    await page.getByRole('button', { name: '退出登录' }).click()
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('登录 SeekBell。')
    expect(errors).toEqual([])
    expect(external).toEqual([])
    await context.close()
  }
})

test('会话失效时回到登录入口并给出提示', async ({ page, context }) => {
  await context.route('**/*', (route) =>
    new URL(route.request().url()).origin === origin ? route.continue() : route.abort(),
  )
  await page.goto('/')
  await page.getByLabel('用户名', { exact: true }).fill(username)
  await page.getByLabel('密码', { exact: true }).fill(password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('button', { name: '退出登录' })).toBeVisible()
  await context.clearCookies()
  await page.getByRole('button', { name: '退出登录' }).click()
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('登录 SeekBell。')
  await expect(page.getByRole('alert')).toContainText('会话已过期')
})

test('浏览器请求不能绕过登录的CSRF校验', async ({ request }) => {
  const state = await request.get('/api/auth/state')
  expect(state.ok()).toBeTruthy()
  const response = await request.post('/api/auth/login', { data: { username, password } })
  expect(response.status()).toBe(403)
  expect((await request.get('/api/auth/state')).ok()).toBeTruthy()
})
