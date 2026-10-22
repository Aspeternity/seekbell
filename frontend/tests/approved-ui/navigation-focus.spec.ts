import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const credentials = { username: 'history_admin', password: 'Synthetic-History-2026' }
async function session(page: Page) {
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
}

test('notification tabs preserve destinations through clicks, history and reload', async ({
  page,
}) => {
  await session(page)
  await page.goto('/#/notifications/targets')
  const tabs = page.getByRole('navigation', { name: '通知管理分类' })
  const routes = [
    ['通知目标', 'targets'],
    ['投递记录', 'deliveries'],
    ['手动重发', 'manual'],
    ['测试记录', 'tests'],
    ['通知目标', 'targets'],
  ]
  for (const [label, path] of routes) {
    const button = tabs.getByRole('button', { name: new RegExp('^' + label) })
    await button.click()
    await expect(page).toHaveURL(new RegExp('#/notifications/' + path + '$'))
    await expect(button).toHaveAttribute('aria-current', 'page')
    await expect(page.getByRole('heading', { name: '通知管理', exact: true })).toBeVisible()
    await expect(page.getByText('这条线索暂时不在这里', { exact: true })).toHaveCount(0)
  }
  await page.goBack()
  await expect(page).toHaveURL(/#\/notifications\/tests$/)
  await expect(tabs.getByRole('button', { name: /^测试记录/ })).toHaveAttribute(
    'aria-current',
    'page',
  )
  await page.reload()
  await expect(tabs.getByRole('button', { name: /^测试记录/ })).toHaveAttribute(
    'aria-current',
    'page',
  )
  await page.goForward()
  await expect(page).toHaveURL(/#\/notifications\/targets$/)
})

test('search and select focus stays on the full control without an inner orange outline', async ({
  page,
}, info) => {
  await session(page)
  for (const [path, label, select] of [
    ['/websites', '搜索已添加网站', '筛选网站状态'],
    ['/', '搜索任务', '筛选任务状态'],
    ['/content', '搜索内容', '匹配结果'],
    ['/tasks', '搜索全部任务', ''],
    ['/notifications/targets', '搜索通知目标', '通知渠道筛选'],
    ['/notifications/deliveries', '搜索投递记录', '投递状态筛选'],
  ]) {
    await page.goto('/#' + path)
    const input = page.getByRole('textbox', { name: label, exact: true })
    const shell = page.locator('.search-input').filter({ has: input })
    await expect(input).toBeVisible()
    await page.locator('h1').focus()
    await expect(page.locator('h1')).toHaveCSS('outline-style', 'none')
    const border = await shell.evaluate((el) => getComputedStyle(el).borderColor)
    await input.click()
    await expect(input).toBeFocused()
    await expect(input).toHaveCSS('outline-style', 'none')
    await expect
      .poll(() => shell.evaluate((el) => getComputedStyle(el).borderColor))
      .not.toBe(border)
    const bounds = await input.boundingBox()
    const outer = await shell.boundingBox()
    expect(bounds!.x).toBeGreaterThan(outer!.x)
    expect(bounds!.x + bounds!.width).toBeLessThan(outer!.x + outer!.width)
    if (path === '/websites' || path === '/notifications/targets')
      await page.screenshot({
        path: info.outputPath(
          path.includes('websites') ? 'website-search-focus.png' : 'target-search-focus.png',
        ),
        fullPage: true,
      })
    if (select) {
      const control = page.getByRole('combobox', { name: select, exact: true })
      await control.focus()
      await expect(control).toBeFocused()
      await expect(control).toHaveCSS('outline-style', 'none')
      await expect(control).not.toHaveCSS('box-shadow', 'none')
      await page.keyboard.press('Tab')
      await page.keyboard.press('Shift+Tab')
      await expect(control).toBeFocused()
    }
  }
})

test('overview task information and whitespace open configuration while switches and selection stay independent', async ({
  page,
}, info) => {
  await session(page)
  const workspace = await (await page.request.get('/api/manage/workspace')).json()
  const task = workspace.tasks[0]
  const row = page
    .locator('.task-row')
    .filter({ has: page.getByRole('button', { name: new RegExp(task.name) }) })
  const editor = page.getByRole('textbox', { name: '任务名称', exact: false })
  for (const part of ['.target-icons', '.task-hits']) {
    await page.goto('/#/')
    await expect(row).toBeVisible()
    const cell = row.locator(part)
    const box = await cell.boundingBox()
    await cell.click({ position: { x: box!.width - 2, y: box!.height / 2 } })
    await expect(page).toHaveURL(new RegExp('#/task/' + task.id + '$'))
    await expect(editor).toHaveValue(task.name)
    await page.getByRole('button', { name: '取消', exact: true }).click()
    await expect(page).toHaveURL(/#\/$/)
  }
  const bounds = await row.boundingBox()
  await row.click({ position: { x: bounds!.width / 2, y: bounds!.height - 2 } })
  await expect(page).toHaveURL(new RegExp('#/task/' + task.id + '$'))
  await page.getByRole('button', { name: '取消', exact: true }).click()
  await row.locator('.task-name').focus()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(new RegExp('#/task/' + task.id + '$'))
  await page.getByRole('button', { name: '取消', exact: true }).click()
  await row.locator('.task-hits').click({ modifiers: ['Control'] })
  await expect(page).toHaveURL(/#\/$/)
  const text = await row.locator('.task-hits').evaluate((el) => {
    const range = document.createRange()
    range.selectNodeContents(el.firstChild!)
    const rect = range.getBoundingClientRect()
    return { x: rect.x, y: rect.y, width: rect.width, height: rect.height }
  })
  await page.mouse.move(text.x - 1, text.y + text.height / 2)
  await page.mouse.down()
  await page.mouse.move(text.x + text.width + 1, text.y + text.height / 2, { steps: 8 })
  await page.mouse.up()
  expect(await page.evaluate(() => window.getSelection()?.toString())).toBeTruthy()
  await expect(page).toHaveURL(/#\/$/)
  await page.evaluate(() => window.getSelection()?.removeAllRanges())
  const toggle = row.getByRole('switch')
  const enabled = await toggle.getAttribute('aria-checked')
  await toggle.click()
  await expect(toggle).toHaveAttribute('aria-checked', enabled === 'true' ? 'false' : 'true')
  await expect(page).toHaveURL(/#\/$/)
  await toggle.click()
  await expect(toggle).toHaveAttribute('aria-checked', enabled!)
  await page.screenshot({ path: info.outputPath('overview-task-row.png'), fullPage: true })
  await row.getByRole('button', { name: '编辑' + task.name, exact: true }).click()
  await expect(page).toHaveURL(new RegExp('#/task/' + task.id + '$'))
})
