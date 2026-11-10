import { expect, test, type Page } from '@playwright/test'
const credentials = { username: 'system_admin', password: 'Synthetic-System-2026' }
let cookies: Awaited<
  ReturnType<import('@playwright/test').APIRequestContext['storageState']>
>['cookies']
test.beforeAll(async ({ request }) => {
  const auth = await (await request.get('/api/auth/status')).json()
  const response = await request.post(auth.initialized ? '/api/auth/login' : '/api/auth/setup', {
    headers: { 'X-CSRF-Token': auth.csrf },
    data: credentials,
  })
  expect(response.ok()).toBe(true)
  cookies = (await request.storageState()).cookies
})
test.beforeEach(async ({ page }) => {
  await page.context().addCookies(cookies)
  await page.route('**/*', (route) => {
    if (new URL(route.request().url()).hostname !== '127.0.0.1')
      throw Error('Unexpected external request')
    return route.continue()
  })
})
async function category(page: Page, value: string, label: string) {
  await page
    .getByRole('navigation', { name: '设置分类', exact: true })
    .getByRole('button', { name: label, exact: true })
    .click()
  await expect(page).toHaveURL(new RegExp('/settings/' + value + '$'))
}
test('all six categories remain reachable across phone tablet and desktop', async ({
  page,
}, info) => {
  await page.goto('/#/settings/preferences')
  const rows = [
    ['preferences', '通用', '通用设置'],
    ['alerts', '告警', '系统告警'],
    ['data', '数据', '历史保留'],
    ['backup', '备份', '备份状态'],
    ['account', '账户', '管理员用户名'],
    ['about', '关于', 'SeekBell.'],
  ]
  for (const width of [320, 390, 768, 900, 1100, 1280, 1440, 1920]) {
    await page.setViewportSize({ width, height: 900 })
    for (const [value, label, heading] of rows) {
      await category(page, value!, label!)
      await expect(page.getByRole('heading', { name: heading!, exact: true })).toBeVisible()
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
        label + ' at ' + width,
      ).toBe(true)
      const navigation = page.getByRole('navigation', { name: '设置分类', exact: true })
      await expect(navigation).toBeVisible()
      // Keep the user-approved horizontal navigation above the content.
      // Six short labels fit every width without scrolling the tab bar.
      expect(
        await navigation.evaluate((nav) => nav.scrollWidth <= nav.clientWidth),
        label + ' tabs fit at ' + width,
      ).toBe(true)
      const geometry = await navigation.evaluate((nav) => {
        const bounds = nav.getBoundingClientRect()
        const buttons = [...nav.querySelectorAll('button')].map((button) =>
          button.getBoundingClientRect(),
        )
        const content = document.querySelector('.settings-content')!.getBoundingClientRect()
        return {
          sameRow: buttons.every((button) => Math.abs(button.top - buttons[0]!.top) < 1),
          aboveContent: bounds.bottom <= content.top,
        }
      })
      expect(geometry, label + ' horizontal layout at ' + width).toEqual({
        sameRow: true,
        aboveContent: true,
      })
      await expect(async () => {
        const visible = await navigation.locator('[aria-current="page"]').evaluate((button) => {
          const bounds = button.getBoundingClientRect()
          const nav = button.parentElement!.getBoundingClientRect()
          return bounds.left >= nav.left - 1 && bounds.right <= nav.right + 1
        })
        expect(visible).toBe(true)
      }).toPass()
      if (width === 1440) {
        await expect(page.locator('.settings-content .read-region[aria-busy="true"]')).toHaveCount(
          0,
        )
        await page.mouse.move(0, 0)
        await page.screenshot({
          path: info.outputPath('settings-' + value + '-desktop.png'),
          fullPage: true,
          animations: 'disabled',
        })
      }
    }
  }
  await page.setViewportSize({ width: 1440, height: 1000 })
  // Addresses of the former seven categories land on the section that replaced them;
  // the backup address is a category again.
  for (const [old, current, heading] of [
    ['overview', 'preferences?section=overview-modules', '概览显示模块'],
    ['retention', 'data?section=retention', '历史保留'],
    ['backup', 'backup', '备份状态'],
  ]) {
    await page.goto('/#/settings/' + old)
    await expect(page).toHaveURL(new RegExp('/settings/' + current!.replace('?', '\\?') + '$'))
    await expect(page.getByRole('heading', { name: heading!, exact: true })).toBeInViewport()
  }
  await page.goto('/#/settings/display')
  await expect(page.getByRole('heading', { name: '通用设置', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '保存通用设置', exact: true })).toBeDisabled()
  await page.evaluate(() => {
    window.scrollTo(0, 0)
    document.querySelector<HTMLElement>('.page-heading h1')?.focus({ preventScroll: true })
  })
  await page.screenshot({
    path: info.outputPath('settings-general-desktop.png'),
    fullPage: true,
    animations: 'disabled',
  })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({
    path: info.outputPath('settings-general-mobile.png'),
    fullPage: true,
    animations: 'disabled',
  })
})
test('a failed unrelated section cannot disable general settings and validation focuses the field', async ({
  page,
}) => {
  let unrelated = 0
  await page.route('**/api/manage/alerts', (route) => {
    unrelated++
    return route.fulfill({ status: 503, json: { detail: '合成告警读取失败' } })
  })
  await page.goto('/#/settings/preferences')
  const input = page.getByLabel('工作空间名称', { exact: true })
  await expect(input).toBeEnabled()
  expect(unrelated).toBe(0)
  await input.fill('')
  await page.getByRole('button', { name: '保存通用设置', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('工作空间名称应为')
  await expect(input).toBeFocused()
  // Reading again cannot fix a validation error, so no reload is offered.
  await expect(page.getByRole('alert').getByRole('button')).toHaveCount(0)
  expect(
    await input.evaluate(
      (el) =>
        el.getBoundingClientRect().top >= 0 && el.getBoundingClientRect().bottom <= innerHeight,
    ),
  ).toBe(true)
  expect(unrelated).toBe(0)
})
for (const tab of ['preferences', 'retention', 'alerts']) {
  test(tab + ' conflict reload asks before discarding its draft', async ({ page }) => {
    if (tab === 'alerts') {
      const auth = await (await page.request.get('/api/auth/status')).json()
      await page.request.post('/api/manage/targets', {
        headers: { 'X-CSRF-Token': auth.csrf },
        data: {
          name: '合成暂停告警目标',
          kind: 'webhook',
          enabled: false,
          config: { url: 'https://receiver.example.test/synthetic-settings' },
        },
      })
    }
    await page.goto('/#/settings/' + (tab === 'retention' ? 'data' : tab))
    let input = page.getByLabel('工作空间名称', { exact: true })
    let value = '',
      old = ''
    if (tab === 'preferences') {
      old = await input.inputValue()
      value = old + '-草稿'
      await input.fill(value)
    }
    if (tab === 'retention') {
      input = page.getByLabel('历史保留天数', { exact: true })
      old = await input.inputValue()
      value = String(Number(old) > 1 ? Number(old) - 1 : 2)
      await input.fill(value)
    }
    if (tab === 'alerts') {
      input = page.getByRole('switch', { name: '启用故障与恢复告警', exact: true })
      old = (await input.getAttribute('aria-checked'))!
      await input.click()
      value = old === 'true' ? 'false' : 'true'
      if (value === 'true')
        await page.locator('.settings-card form input[type="checkbox"]').first().check()
    }
    await page.route('**/api/manage/' + tab, (route) =>
      route.request().method() === 'PUT'
        ? route.fulfill({ status: 409, json: { detail: '合成保存冲突' } })
        : route.continue(),
    )
    const saveLabel =
      tab === 'preferences' ? '保存通用设置' : tab === 'retention' ? '保存保留策略' : '保存告警设置'
    await page.getByRole('button', { name: saveLabel, exact: true }).click()
    // Only turning alerts off or shortening retention asks first.
    if (tab === 'alerts' ? value === 'false' : tab === 'retention' && Number(value) < Number(old))
      await page
        .getByRole('button', {
          name: tab === 'alerts' ? '关闭告警' : '确认保存策略',
          exact: true,
        })
        .click()
    await expect(page.getByRole('alert')).toContainText('合成保存冲突')
    await page.getByRole('alert').getByRole('button', { name: '重新加载', exact: true }).click()
    await expect(page.getByRole('dialog')).toContainText('尚未保存')
    await page.getByRole('button', { name: '取消', exact: true }).click()
    if (tab === 'alerts') await expect(input).toHaveAttribute('aria-checked', value)
    else await expect(input).toHaveValue(value)
    await page.getByRole('alert').getByRole('button', { name: '重新加载', exact: true }).click()
    await page.getByRole('button', { name: '放弃修改并读取', exact: true }).click()
    if (tab === 'alerts') await expect(input).toHaveAttribute('aria-checked', old)
    else await expect(input).toHaveValue(old)
  })
}
test('maintenance preview is read only', async ({ page }) => {
  await page.goto('/#/settings/data')
  await expect(page.getByRole('heading', { name: '存储占用', exact: true })).toBeVisible()
  const before = await (await page.request.get('/api/manage/retention')).json()
  await page.getByRole('button', { name: '预览清理影响', exact: true }).click()
  await expect(page.getByText(/不会删除任何记录/)).toBeVisible()
  // The same button closes the estimate and a second open reads it again.
  await page.getByRole('button', { name: '收起预览', exact: true }).click()
  await expect(page.getByText(/不会删除任何记录/)).toHaveCount(0)
  await Promise.all([
    page.waitForResponse((response) => response.url().includes('/api/manage/retention/preview')),
    page.getByRole('button', { name: '预览清理影响', exact: true }).click(),
  ])
  await expect(page.getByText(/不会删除任何记录/)).toBeVisible()
  const after = await (await page.request.get('/api/manage/retention')).json()
  expect(after.days).toBe(before.days)
  expect(after.revision).toBe(before.revision)
})
test('timezone picker groups common zones and previews the offset without a search box', async ({
  page,
}) => {
  await page.goto('/#/settings/preferences')
  await expect(page.locator('#timezone-search')).toHaveCount(0)
  const select = page.getByRole('combobox', { name: '显示时区', exact: true })
  const preview = page.locator('.timezone-preview')
  await expect(preview).toContainText(/UTC[+-]\d/)
  // The current-time field matches the select's height and, when side by side, its row.
  const [field, output] = await Promise.all([select.boundingBox(), preview.boundingBox()])
  expect(Math.abs(field!.height - output!.height)).toBeLessThan(1)
  if (output!.x > field!.x) expect(Math.abs(field!.y - output!.y)).toBeLessThan(1)
  await select.click()
  const menu = page.locator(
    '[id=' + JSON.stringify(await select.getAttribute('aria-controls')) + ']',
  )
  await expect(menu.locator('.app-select-group')).toHaveText(['常用时区', '全部时区'])
  await expect(menu.getByRole('option').first()).toHaveAttribute('data-value', 'Asia/Shanghai')
  await select.press('Escape')
})
test('storage refresh keeps an unsaved retention draft', async ({ page }) => {
  await page.goto('/#/settings/data')
  const input = page.getByLabel('历史保留天数', { exact: true })
  const old = Number(await input.inputValue())
  const value = String(old < 365 ? old + 1 : old - 1)
  await input.fill(value)
  await Promise.all([
    page.waitForResponse((response) => response.url().endsWith('/api/manage/storage')),
    page.getByRole('button', { name: '刷新', exact: true }).click(),
  ])
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(input).toHaveValue(value)
  await expect(page.getByRole('status').filter({ hasText: '有未保存的修改' })).toBeVisible()
})
test('alert delay is saved and a test alert reports each chosen target', async ({ page }, info) => {
  const name = '合成测试告警目标 ' + info.project.name
  const auth = await (await page.request.get('/api/auth/status')).json()
  const headers = { 'X-CSRF-Token': auth.csrf }
  const created = await page.request.post('/api/manage/targets', {
    headers,
    data: {
      name,
      kind: 'webhook',
      enabled: true,
      config: { url: 'https://receiver.example.test/synthetic-alert-test' },
    },
  })
  expect(created.ok()).toBe(true)
  const before = await (await page.request.get('/api/manage/alerts')).json()
  await page.goto('/#/settings/alerts')
  const test = page.getByRole('button', { name: '发送测试告警', exact: true })
  await page.getByRole('radio', { name: '持续 5 分钟', exact: true }).check()
  await expect(page.getByText('5 分钟内自行恢复的故障不通知')).toBeVisible()
  await page.getByRole('checkbox', { name: new RegExp(name) }).check()
  // The draft selection can be tested before anything is saved.
  await test.click()
  await expect(page.getByRole('dialog')).toContainText('真实发送')
  await page.getByRole('button', { name: '发送测试', exact: true }).click()
  const results = page.getByRole('list', { name: '测试结果', exact: true }).getByRole('listitem')
  // Targets saved by other checks are tested too; this one must be among them, once.
  await expect(results.filter({ hasText: name })).toHaveCount(1)
  expect((await (await page.request.get('/api/manage/alerts')).json()).revision).toBe(
    before.revision,
  )
  // Saving without turning alerts off needs no confirmation.
  await page.getByRole('button', { name: '保存告警设置', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: '系统告警设置已保存' })).toBeVisible()
  const saved = await (await page.request.get('/api/manage/alerts')).json()
  expect(saved.delay_seconds).toBe(300)
  expect(saved.enabled).toBe(before.enabled)
  await page.getByRole('radio', { name: '立即', exact: true }).check()
  await page.getByRole('checkbox', { name: new RegExp(name) }).uncheck()
  await page.getByRole('button', { name: '保存告警设置', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: '系统告警设置已保存' })).toBeVisible()
})
test('account page separates the username from the password and keeps both sign-out actions', async ({
  page,
}) => {
  await page.goto('/#/settings/account')
  const rename = page.getByRole('form', { name: '修改用户名', exact: true })
  const secret = page.getByRole('form', { name: '修改密码', exact: true })
  await expect(rename.getByRole('button', { name: '更新用户名', exact: true })).toBeDisabled()
  await expect(secret.getByRole('button', { name: '更新密码', exact: true })).toBeDisabled()
  await secret.getByLabel('当前密码', { exact: true }).fill(credentials.password)
  await secret.getByLabel('新密码', { exact: true }).fill('Synthetic-Mismatch-1')
  await secret.getByLabel('确认新密码', { exact: true }).fill('Synthetic-Mismatch-2')
  await secret.getByRole('button', { name: '更新密码', exact: true }).click()
  const alert = page.getByRole('alert')
  await expect(alert).toContainText('两次输入的新密码不一致')
  await expect(alert.getByRole('button')).toHaveCount(0)
  const main = page.locator('#main-content')
  await expect(main.getByRole('button', { name: '退出其他会话', exact: true })).toBeVisible()
  await expect(main.getByRole('button', { name: '退出登录', exact: true })).toHaveCount(1)
  await expect(main.getByText('当前会话到期')).toBeVisible()
})
test('the sign-in page offers to stay signed in', async ({ browser }) => {
  const context = await browser.newContext()
  const page = await context.newPage()
  // The request is inspected and dropped, so the shared sign-in rate limit is left alone.
  let sent: { remember?: boolean } | undefined
  await page.route('**/api/auth/login', (route) => {
    sent = route.request().postDataJSON()
    return route.abort()
  })
  await page.goto('/#/login')
  const remember = page.getByRole('checkbox', { name: /保持登录 30 天/ })
  await expect(remember).not.toBeChecked()
  await page.getByLabel('管理员用户名').fill(credentials.username)
  await page.getByLabel('密码', { exact: true }).fill(credentials.password)
  await remember.check()
  await page.getByRole('button', { name: '登录工作空间' }).click()
  await expect.poll(() => sent?.remember).toBe(true)
  await context.close()
})
