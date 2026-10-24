import { expect, test, type Page } from '@playwright/test'
import { selectChoice } from '../select'
const credentials = { username: 'stability_admin', password: 'Synthetic-Stability-2026' }
function gate() {
  let release = () => {}
  const promise = new Promise<void>((resolve) => (release = resolve))
  return { promise, release }
}
async function login(page: Page) {
  await page.route('**/*', (route) => {
    if (new URL(route.request().url()).hostname !== '127.0.0.1')
      throw Error('Unexpected external request')
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
    .getByRole('button', { name: initialized ? '登录工作空间' : '创建管理员并进入', exact: true })
    .click()
  await expect(page.getByTestId('overview-matches')).toContainText('24条')
}
async function nav(page: Page, path: string) {
  await page.evaluate((path) => (location.hash = path), path)
}

test('date triggers share one boundary and custom select menus follow existing colors and keyboard rules', async ({
  page,
}, info) => {
  await login(page)
  for (const tab of ['posts', 'deliveries', 'manual', 'tests']) {
    await nav(page, tab === 'posts' ? '/content' : '/notifications/' + tab)
    const control = page.getByRole('button', {
      name: tab === 'posts' ? '发现日期' : '记录日期',
      exact: true,
    })
    const menu = page.getByRole('dialog', {
      name: tab === 'posts' ? '发现日期范围' : '记录日期范围',
      exact: true,
    })
    await control.click()
    await expect(menu).toBeVisible()
    await control.click()
    await expect(menu).toHaveCount(0)
    await control.click()
    await expect(menu).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(menu).toHaveCount(0)
    await expect(control).toBeFocused()
    expect(await page.locator('select').count()).toBe(0)
  }
  await nav(page, '/content')
  const control = page.getByRole('combobox', { name: '匹配结果', exact: true })
  await control.click()
  const menu = page.getByRole('listbox', { name: '匹配结果', exact: true })
  await expect(menu.getByRole('option', { selected: true })).toHaveCSS('color', 'rgb(183, 94, 50)')
  await page.keyboard.press('End')
  await page.keyboard.press('Enter')
  await expect(control).toHaveAttribute('data-value', 'unrecorded')
  await control.click()
  await control.click()
  await expect(menu).toHaveCount(0)
  await control.focus()
  await page.keyboard.press('Space')
  await expect(menu).toBeVisible()
  await page.mouse.click(page.viewportSize()!.width - 2, 2)
  await expect(menu).toHaveCount(0)
  await control.click()
  const bounds = (await menu.boundingBox())!
  expect(bounds.x).toBeGreaterThanOrEqual(0)
  expect(bounds.x + bounds.width).toBeLessThanOrEqual(page.viewportSize()!.width + 1)
  await page.screenshot({ path: info.outputPath('shared-select.png') })
})

test('notification tabs preserve their shell and filtering commits a complete snapshot without an empty frame', async ({
  page,
}, info) => {
  await login(page)
  await nav(page, '/notifications/targets')
  const tabs = page.getByRole('navigation', { name: '通知管理分类' })
  await expect(tabs).toBeVisible()
  await page.evaluate(() => {
    ;(window as any).__heading = document.querySelector('.page-heading')
    ;(window as any).__tabs = document.querySelector('[aria-label="通知管理分类"]')
  })
  await tabs.getByRole('button', { name: /^投递记录/ }).click()
  await expect(page.locator('.delivery-row')).toHaveCount(20)
  expect(
    await page.evaluate(() => ({
      heading: (window as any).__heading === document.querySelector('.page-heading'),
      tabs: (window as any).__tabs === document.querySelector('[aria-label="通知管理分类"]'),
    })),
  ).toEqual({ heading: true, tabs: true })
  const held = gate()
  let began = false
  await page.route(/\/api\/manage\/history\/deliveries(?:\?|$)/, async (route) => {
    if (new URL(route.request().url()).searchParams.get('q') !== '%_') return route.fallback()
    const response = await route.fetch()
    began = true
    await held.promise
    await route.fulfill({ response })
  })
  await page.evaluate(() => {
    ;(window as any).__frames = []
    ;(window as any).__sample = true
    const sample = () => {
      if (!(window as any).__sample) return
      ;(window as any).__frames.push(document.querySelectorAll('.delivery-row').length)
      requestAnimationFrame(sample)
    }
    requestAnimationFrame(sample)
  })
  const search = page.getByRole('textbox', { name: '搜索投递记录', exact: true })
  const before = await search.boundingBox()
  await search.fill('%_')
  await expect.poll(() => began).toBe(true)
  await expect(page.locator('.delivery-row')).toHaveCount(20)
  await expect(page.locator('.read-snapshot')).toHaveAttribute('inert', '')
  await expect(page.locator('.remote-feedback')).toContainText('上次结果')
  expect(Math.abs((await search.boundingBox())!.y - before!.y)).toBeLessThan(1)
  const frames = await page.evaluate(() => {
    ;(window as any).__sample = false
    return (window as any).__frames as number[]
  })
  expect(frames.length).toBeGreaterThan(2)
  expect(frames.every((count) => count === 20)).toBe(true)
  held.release()
  await expect(page.locator('.delivery-row')).toHaveCount(1)
  await expect(page.locator('.pagination')).toContainText('共 1 条')
  await expect(page.locator('.read-snapshot')).not.toHaveAttribute('inert', '')
  await tabs.getByRole('button', { name: /^测试记录/ }).click()
  await expect(page.locator('.delivery-row')).toHaveCount(2)
  await tabs.getByRole('button', { name: /^投递记录/ }).click()
  await expect(page.locator('.delivery-row')).toHaveCount(20)
  await page.screenshot({ path: info.outputPath('notification-stability.png') })
})

test('initial detail reads start immediately and overview query controls remain usable while old data is isolated', async ({
  page,
}) => {
  await login(page)
  await nav(page, '/notifications/deliveries')
  await expect(page.locator('.delivery-row')).toHaveCount(20)
  const detail = gate()
  let began = false
  await page.route(/\/api\/manage\/history\/deliveries\/[^/?]+(?:\?|$)/, async (route) => {
    const response = await route.fetch()
    began = true
    await detail.promise
    await route.fulfill({ response })
  })
  await page.clock.install()
  await page.clock.pauseAt(new Date())
  await page.locator('.delivery-row .task-title').first().click()
  await expect.poll(() => began).toBe(true)
  await expect(page.locator('.read-placeholder')).toHaveCount(0)
  await expect(page.locator('.remote-feedback')).toHaveCount(0)
  await page.clock.runFor(199)
  await expect(page.locator('.read-placeholder')).toHaveCount(0)
  await expect(page.locator('.remote-feedback')).toHaveCount(0)
  await page.clock.runFor(1)
  await expect(page.locator('.read-placeholder')).toBeVisible()
  await expect(page.locator('.remote-feedback')).toContainText('加载中')
  detail.release()
  await expect(page.getByRole('heading', { name: '投递详情', exact: true })).toBeVisible()
  await page.clock.resume()
  await nav(page, '/')
  await expect(page.getByTestId('overview-matches')).toContainText('24条')
  const range = gate()
  let started = false
  await page.route('**/api/manage/overview?range=7d', async (route) => {
    const response = await route.fetch()
    started = true
    await range.promise
    await route.fulfill({ response })
  })
  await page.getByRole('button', { name: '7 天', exact: true }).click()
  await expect.poll(() => started).toBe(true)
  await expect(page.locator('.stats-grid')).toHaveCount(1)
  await page.getByRole('button', { name: '24 小时', exact: true }).click()
  await expect(page.getByRole('button', { name: '24 小时', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  range.release()
  await expect(page.locator('.chart-point')).toHaveCount(24)
  await expect(page.getByTestId('overview-matches')).toContainText('24条')
})

test('select menus retain scroll and values while task websites use independent checkboxes', async ({
  page,
}, info) => {
  await login(page)
  await expect(page.locator('body')).toHaveCSS(
    'font-size',
    info.project.name === 'mobile' ? '14px' : '13px',
  )
  const font = await page.locator('body').evaluate((el) => getComputedStyle(el).fontFamily)
  expect(font).toContain('Inter')
  let checked = 0
  async function check(name: string) {
    const control = page.getByRole('combobox', { name, exact: true })
    await expect(control).toBeEnabled()
    const value = await control.getAttribute('data-value')
    // Place the trigger clear of fixed mobile editor actions before measuring popup movement.
    await control.evaluate((el) => el.scrollIntoView({ block: 'center' }))
    const before = await page.evaluate(() => scrollY)
    await control.click()
    const menu = page.locator(
      '[id=' + JSON.stringify(await control.getAttribute('aria-controls')) + ']',
    )
    await expect(menu).toBeVisible()
    await expect(menu.getByRole('option').first()).toHaveCSS('border-radius', '5px')
    await page.keyboard.press('Escape')
    await expect(control).toBeFocused()
    expect(await page.evaluate(() => scrollY)).toBe(before)
    await expect(control).toHaveAttribute('data-value', value!)
    expect(await page.locator('body').evaluate((el) => getComputedStyle(el).fontFamily)).toBe(font)
    checked++
  }
  for (const [path, names] of [
    ['/', ['筛选任务状态']],
    ['/websites', ['筛选网站状态']],
    ['/content', ['匹配结果', '关联任务', '历史网站', '版块筛选']],
    ['/notifications/targets', ['通知渠道筛选']],
    ['/notifications/deliveries', ['投递状态筛选', '投递目标筛选', '结果未知筛选']],
    ['/settings/preferences', ['显示时区']],
    ['/settings/display', ['显示时区']],
    ['/task/new', []],
  ] as [string, string[]][]) {
    await nav(page, path)
    for (const name of names) await check(name)
    await expect(page.locator('select')).toHaveCount(0)
  }
  const website = page
    .locator('#task-website')
    .getByRole('checkbox', { name: 'NodeSeek', exact: false })
  await expect(website).toBeEnabled()
  await website.uncheck()
  await website.check()
  await expect(website).toBeChecked()
  await expect(page.locator('.task-category-scopes')).toContainText('全部版块')
  await page.getByRole('button', { name: '历史样本', exact: true }).click()
  await check('最多试算条数')
  await selectChoice(page.getByRole('combobox', { name: '最多试算条数', exact: true }), '100')
  await expect(page.getByRole('combobox', { name: '最多试算条数', exact: true })).toHaveAttribute(
    'data-value',
    '100',
  )
  await nav(page, '/target/new')
  await page.getByRole('button', { name: 'SMTP', exact: true }).click()
  await check('连接安全')
  await page.getByRole('button', { name: 'Webhook', exact: true }).click()
  await check('成功判定')
  expect(checked).toBe(15)
  await page.screenshot({ path: info.outputPath('all-controls.png') })
})
