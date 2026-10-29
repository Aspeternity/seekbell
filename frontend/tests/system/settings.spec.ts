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
test('all seven categories remain reachable across phone tablet and desktop', async ({
  page,
}, info) => {
  await page.goto('/#/settings/preferences')
  const rows = [
    ['preferences', '通用', '通用设置'],
    ['overview', '概览', '概览显示模块'],
    ['alerts', '系统告警', '系统故障与恢复告警'],
    ['retention', '历史与存储', '历史保留策略'],
    ['backup', '备份与恢复', '导出备份'],
    ['account', '账户与安全', '管理员资料'],
    ['about', '关于与诊断', '诊断与帮助'],
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
  await page.goto('/#/settings/preferences?section=overview-modules')
  await expect(page.getByRole('heading', { name: '概览显示模块', exact: true })).toBeVisible()
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
  expect(
    await input.evaluate(
      (el) =>
        el.getBoundingClientRect().top >= 0 && el.getBoundingClientRect().bottom <= innerHeight,
    ),
  ).toBe(true)
  expect(unrelated).toBe(0)
})
for (const tab of ['preferences', 'retention', 'alerts']) {
  test(tab + ' error retry asks before discarding its draft', async ({ page }) => {
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
    await page.goto('/#/settings/' + tab)
    let input = page.getByLabel('工作空间名称', { exact: true })
    let value = '',
      old = ''
    if (tab === 'preferences') {
      old = await input.inputValue()
      value = old + '-草稿'
      await input.fill(value)
    }
    if (tab === 'retention') {
      input = page.getByLabel('普通历史保留天数', { exact: true })
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
        ? route.fulfill({ status: 503, json: { detail: '合成保存失败' } })
        : route.continue(),
    )
    const saveLabel =
      tab === 'preferences' ? '保存通用设置' : tab === 'retention' ? '保存保留策略' : '保存告警设置'
    await page.getByRole('button', { name: saveLabel, exact: true }).click()
    if (tab === 'alerts' || (tab === 'retention' && Number(value) < Number(old)))
      await page
        .getByRole('button', {
          name: tab === 'alerts' ? '确认保存告警' : '确认保存策略',
          exact: true,
        })
        .click()
    await expect(page.getByRole('alert')).toContainText('合成保存失败')
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
test('maintenance preview is read only and diagnostics provide a copy fallback', async ({
  page,
}) => {
  await page.goto('/#/settings/retention')
  await expect(page.getByRole('heading', { name: '存储占用', exact: true })).toBeVisible()
  const before = await (await page.request.get('/api/manage/retention')).json()
  await page.getByRole('button', { name: '预览清理影响', exact: true }).click()
  await expect(page.getByText(/这是只读估算/)).toBeVisible()
  const after = await (await page.request.get('/api/manage/retention')).json()
  expect(after.days).toBe(before.days)
  expect(after.revision).toBe(before.revision)
  await page.goto('/#/settings/about')
  await page.getByRole('button', { name: '复制诊断摘要', exact: true }).click()
  const summary = page.getByRole('textbox', { name: '诊断摘要', exact: true })
  await expect(summary).toBeVisible()
  const data = JSON.parse(await summary.inputValue())
  expect(data.supported_websites).toHaveLength(2)
  expect(Object.keys(data)).not.toContain('csrf')
  expect(Object.keys(data)).not.toContain('password')
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
test('storage status refresh keeps an unsaved retention draft', async ({ page }) => {
  await page.goto('/#/settings/retention')
  const input = page.getByLabel('普通历史保留天数', { exact: true })
  const old = Number(await input.inputValue())
  const value = String(old < 365 ? old + 1 : old - 1)
  await input.fill(value)
  await Promise.all([
    page.waitForResponse(
      (response) =>
        response.url().endsWith('/api/manage/retention') && response.request().method() === 'GET',
    ),
    page.getByRole('button', { name: '刷新状态', exact: true }).click(),
  ])
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(input).toHaveValue(value)
  await expect(page.getByRole('status').filter({ hasText: '有未保存的修改' })).toBeVisible()
})
