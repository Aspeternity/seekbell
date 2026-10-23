import { selectChoice } from '../select'
import { expect, test } from '@playwright/test'
const credentials = { username: 'history_admin', password: 'Synthetic-History-2026' }
test('stored history filters, pages, snapshots, uncertainty and read errors remain accurate', async ({
  page,
}, info) => {
  const errors: string[] = [],
    bodies: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  page.on('response', async (response) => {
    if (response.url().includes('/api/manage/history/'))
      bodies.push(await response.text().catch(() => ''))
  })
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
  await page.goto('/#/content')
  await expect(page.locator('.content-row')).toHaveCount(20)
  await page.getByLabel('下一页内容', { exact: true }).click()
  await expect(page.locator('.content-row')).toHaveCount(7)
  await page.getByLabel('搜索内容').fill('%_')
  await expect(page.locator('.content-row')).toHaveCount(1)
  await expect(page.locator('.content-row')).toContainText('<img src=x')
  await expect(page.locator('.content-row img')).toHaveCount(0)
  await page.screenshot({ path: info.outputPath('history-content.png'), fullPage: true })
  await page.locator('.content-title').click()
  await expect(page.getByRole('heading', { name: '为什么会得到这个结果？' })).toBeVisible()
  await expect(page.locator('.history-evaluation')).toHaveCount(1)
  await page.getByRole('button', { name: '查看其他任务判定（1）', exact: true }).click()
  await expect(page.locator('.history-evaluation')).toHaveCount(2)
  await expect(page.locator('.history-evaluation').filter({ hasText: '摘要关注' })).toContainText(
    '任务配置 v1',
  )
  await expect(page.getByRole('link', { name: '打开原帖' })).toHaveAttribute(
    'href',
    'https://www.nodeseek.com/post-8005-1',
  )
  const spacing = await page.locator('.original-post-link').evaluate((button) => {
    const note = button.previousElementSibling!.getBoundingClientRect()
    const scale =
      parseFloat(
        getComputedStyle(document.documentElement).getPropertyValue('--workspace-scale'),
      ) || 1
    return (button.getBoundingClientRect().top - note.bottom) / scale
  })
  expect(spacing).toBeCloseTo(16, 0)
  await page.screenshot({ path: info.outputPath('post-detail-spacing.png'), fullPage: true })
  expect(await page.evaluate(() => Reflect.get(window, 'historyInjected'))).toBeUndefined()
  await page.goto('/#/content')
  await selectChoice(page.getByLabel('匹配结果', { exact: true }), 'insufficient_data')
  await expect(page.locator('.content-row')).toHaveCount(1)
  await page.locator('.content-title').click()
  await expect(page.locator('.history-evaluation').filter({ hasText: '摘要关注' })).toHaveCount(1)
  await expect(page.locator('.history-evaluation').filter({ hasText: '特别标题关注' })).toHaveCount(
    1,
  )
  await expect(page.getByText('来源未提供摘要，无法据此推断完整内容。')).toBeVisible()
  await expect(page.locator('.support-panel')).toContainText('摘要缺失')
  await page.goto('/#/content')
  await selectChoice(page.getByLabel('关联任务', { exact: true }), { label: '当前任务名称' })
  await selectChoice(page.getByLabel('匹配结果', { exact: true }), 'no_match')
  await expect(page.locator('.content-row')).toHaveCount(2)
  await expect(page.locator('.content-row').filter({ hasText: '特别结果' })).toContainText('不命中')
  await selectChoice(page.getByLabel('关联任务', { exact: true }), '')
  await selectChoice(page.getByLabel('匹配结果', { exact: true }), 'not_evaluated')
  await expect(page.locator('.content-row')).toHaveCount(1)
  await page.locator('.content-title').click()
  await expect(page.getByText('基线帖子：首次采集时登记，未执行规则匹配或生成通知。')).toBeVisible()
  await page.goto('/#/content')
  await page.route(
    /\/api\/manage\/history\/posts(?:\?|$)/,
    (route) =>
      route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ detail: '合成查询故障，请重试。' }),
      }),
    { times: 1 },
  )
  await page.getByLabel('搜索内容').fill('不存在的内容')
  await expect(page.getByRole('alert')).toContainText('合成查询故障')
  await expect(page.getByRole('alert')).toContainText('上次结果')
  await expect(page.locator('.content-row')).toHaveCount(20)
  await page.getByRole('button', { name: '重新加载', exact: true }).click()
  await expect(page.getByText('没有符合条件的内容', { exact: true })).toBeVisible()
  await page.getByLabel('搜索内容').fill('')
  await expect(page.locator('.content-row')).toHaveCount(20)
  let release = () => {},
    started = () => {},
    finished = () => {}
  const gate = new Promise<void>((resolve) => (release = resolve))
  const began = new Promise<void>((resolve) => (started = resolve))
  const done = new Promise<void>((resolve) => (finished = resolve))
  await page.route(/\/api\/manage\/history\/posts(?:\?|$)/, async (route) => {
    if (new URL(route.request().url()).searchParams.get('q') !== 'slow-result')
      return route.continue()
    const response = await route.fetch()
    started()
    await gate
    await route.fulfill({ response })
    finished()
  })
  await page.getByLabel('搜索内容').fill('slow-result')
  await began
  await page.getByLabel('搜索内容').fill('%_')
  await expect(page.locator('.content-row')).toHaveCount(1)
  release()
  await done
  await page.evaluate(() => new Promise(requestAnimationFrame))
  await expect(page.locator('.content-row')).toHaveCount(1)
  await page.goto('/#/notifications/deliveries')
  await expect(page.locator('.delivery-row')).toHaveCount(20)
  await page.getByLabel('下一页投递记录', { exact: true }).click()
  await expect(page.locator('.delivery-row')).toHaveCount(4)
  await selectChoice(page.getByLabel('投递状态筛选'), 'sent')
  await selectChoice(page.getByLabel('结果未知筛选'), 'true')
  await expect(page.locator('.delivery-row')).toHaveCount(2)
  await expect(page.locator('.delivery-row').first()).toContainText('历史 Webhook 名称')
  await page
    .locator('.delivery-row')
    .filter({ hasText: '<img src=x' })
    .locator('.task-title')
    .click()
  await expect(page.getByRole('heading', { name: '投递详情', exact: true })).toBeVisible()
  await expect(
    page.getByText('曾有结果未知，接收端可能重复收到；后续成功不会抹去这项记录。'),
  ).toBeVisible()
  await expect(page.locator('.delivery-timeline')).toContainText('迟到结果：渠道已接受')
  await expect(page.locator('.delivery-timeline')).toContainText('结果未知')
  await expect(page.locator('.reading-panel').first()).toContainText('成功')
  await page.screenshot({ path: info.outputPath('history-delivery.png'), fullPage: true })
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
  await page.setViewportSize(
    info.project.name === 'mobile' ? { width: 390, height: 844 } : { width: 1440, height: 1000 },
  )
  await page.getByRole('button', { name: '查看关联内容', exact: true }).click()
  await page.reload()
  await expect(page.getByRole('heading', { name: '为什么会得到这个结果？' })).toBeVisible()
  await page.goto('/#/notifications/tests')
  await expect(page.locator('.delivery-row')).toHaveCount(2)
  await page.getByLabel('查看投递history-test-unknown', { exact: true }).click()
  await expect(page.getByRole('heading', { name: '目标测试详情' })).toBeVisible()
  await expect(page.locator('.reading-panel')).toContainText('结果未知')
  await expect(page.locator('.reading-panel')).toContainText('不运行或重发测试')
  await page.goto('/#/content/missing-content-key')
  await expect(page.getByRole('alert')).toContainText('内容不存在')
  expect(bodies.length).toBeGreaterThan(10)
  expect(bodies.join('')).not.toContain('synthetic-private-history-value')
  expect(bodies.join('')).not.toContain('config_ciphertext')
  expect(bodies.join('')).not.toContain('lease_token')
  expect(errors).toEqual([])
})
