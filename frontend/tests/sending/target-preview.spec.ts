import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
const credentials = { username: 'sending_admin', password: 'Synthetic-Sending-2026' }
function gate() {
  let release = () => {}
  const promise = new Promise<void>((resolve) => (release = resolve))
  return { promise, release }
}
async function backToTargets(page: Page) {
  await page.getByRole('button', { name: '取消', exact: true }).click()
  const discard = page.getByRole('button', { name: '放弃修改并离开', exact: true })
  await expect
    .poll(async () => (await discard.isVisible()) || page.url().includes('#/notifications/targets'))
    .toBe(true)
  if (await discard.isVisible()) await discard.click()
  await expect(page.getByRole('heading', { name: '通知管理', exact: true })).toBeVisible()
}
test('Telegram preview shares real formatting and target cards open without hijacking controls', async ({
  page,
}, info) => {
  const errors: string[] = []
  const previewRequests: { method: string; url: string; body: string | null }[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('request', (request) => {
    if (request.url().includes('/notification-preview/telegram'))
      previewRequests.push({
        method: request.method(),
        url: request.url(),
        body: request.postData(),
      })
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
  const headers = {
    'X-CSRF-Token': (await (await page.request.get('/api/auth/status')).json()).csrf,
  }
  const before = await (await page.request.get('/api/manage/workspace')).json()
  const beforeTests = (await (await page.request.get('/api/manage/history/tests')).json()).total
  await page.goto('/#/target/new')
  const preview = page.locator('.message-preview')
  const summary = page.getByRole('switch', { name: '包含 RSS 摘要', exact: true })
  const limit = page.getByLabel('摘要最大长度', { exact: true })
  await expect(preview.locator('.small-badge')).toHaveText('SEEKBELL')
  await expect(preview.locator('h3')).toHaveText('DMIT 洛杉矶套餐补货')
  await expect(preview.locator('h3')).toHaveCSS('font-weight', '600')
  await expect(preview).toContainText('NodeSeek · 情报 · 作者：cloud_note')
  await expect(preview).toContainText('命中任务：好价服务器雷达')
  await expect(preview).toContainText('发布时间：')
  await expect(preview).not.toContainText('发现时间')
  await expect(preview).not.toContainText('🎯')
  await expect(preview).not.toContainText('🕒')
  const compare = async (include: boolean, length: number) => {
    const expected = await (
      await page.request.get('/api/manage/notification-preview/telegram', {
        params: { include_summary: include, summary_limit: length },
      })
    ).json()
    const title = expected.text.slice(0, expected.entities[0].length)
    await expect(preview.locator('h3')).toHaveText(title)
    await expect
      .poll(async () => (await preview.locator('.telegram-preview-body').textContent())?.trim())
      .toBe(expected.text.slice(title.length + 2))
    await expect(preview.locator('.telegram-preview-link')).toHaveText(
      expected.reply_markup.inline_keyboard[0][0].text,
    )
  }
  await expect(summary).toHaveAttribute('aria-checked', 'false')
  await compare(false, 0)
  await summary.click()
  await compare(true, Number(await limit.inputValue()))
  await page.getByLabel('Bot Token').fill('123456:synthetic-preview-private-value')
  await page.getByLabel('Chat ID').fill('-100987654321')
  await summary.click()
  await compare(false, 0)
  await expect(preview).not.toContainText('摘要：')
  await summary.click()
  await limit.fill('7')
  await compare(true, 7)
  const count = previewRequests.length
  await limit.fill('1001')
  await expect(preview.getByRole('alert')).toContainText('摘要长度应为')
  expect(previewRequests).toHaveLength(count)
  await page.route(
    '**/api/manage/notification-preview/telegram?*',
    (route) => route.fulfill({ status: 503, json: { detail: '合成预览失败' } }),
    { times: 1 },
  )
  await limit.fill('9')
  await expect(preview.getByRole('alert')).toContainText('当前保留上次预览')
  await preview.getByRole('button', { name: '重新生成预览', exact: true }).click()
  await compare(true, 9)
  await expect(preview.getByRole('alert')).toHaveCount(0)

  const held = gate()
  const completed = gate()
  let began = false
  await page.route('**/api/manage/notification-preview/telegram?*', async (route) => {
    if (new URL(route.request().url()).searchParams.get('summary_limit') !== '4')
      return route.fallback()
    const response = await route.fetch()
    began = true
    await held.promise
    await route.fulfill({ response })
    completed.release()
  })
  await limit.fill('4')
  await expect.poll(() => began).toBe(true)
  await limit.fill('11')
  await compare(true, 11)
  held.release()
  await completed.promise
  await compare(true, 11)

  const display = await (await page.request.get('/api/manage/display')).json()
  const zone = display.timezone === 'Asia/Tokyo' ? 'UTC' : 'Asia/Tokyo'
  expect(
    (
      await page.request.put('/api/manage/display', {
        headers,
        data: { timezone: zone, revision: display.revision },
      })
    ).ok(),
  ).toBe(true)
  await limit.fill('12')
  await compare(true, 12)
  await expect(preview).toContainText(
    zone === 'Asia/Tokyo' ? '2026-10-22 19:40:33' : '2026-10-22 10:40:33',
  )
  const current = await (await page.request.get('/api/manage/display')).json()
  expect(
    (
      await page.request.put('/api/manage/display', {
        headers,
        data: { timezone: display.timezone, revision: current.revision },
      })
    ).ok(),
  ).toBe(true)
  await limit.fill('160')
  await compare(true, 160)
  await preview.screenshot({ path: info.outputPath('telegram-preview.png') })
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
  await page.setViewportSize(
    info.project.name === 'mobile' ? { width: 390, height: 844 } : { width: 1440, height: 1000 },
  )
  expect((await (await page.request.get('/api/manage/workspace')).json()).targets).toEqual(
    before.targets,
  )
  expect((await (await page.request.get('/api/manage/history/tests')).json()).total).toBe(
    beforeTests,
  )
  expect(previewRequests.length).toBeGreaterThan(5)
  expect(
    previewRequests.every((request) => request.method === 'GET' && request.body === null),
  ).toBe(true)
  expect(JSON.stringify(previewRequests)).not.toContain('synthetic-preview-private-value')
  expect(JSON.stringify(previewRequests)).not.toContain('-100987654321')
  await backToTargets(page)

  const name = '合成卡片目标 ' + info.project.name
  const created = await page.request.post('/api/manage/targets', {
    headers,
    data: {
      name,
      kind: 'telegram',
      enabled: true,
      config: { bot_token: '123456:synthetic-secret', chat_id: '-100123' },
    },
  })
  expect(created.ok()).toBe(true)
  const id = (await created.json()).id
  try {
    await page.reload()
    const card = page.locator('.notification-card').filter({ hasText: name })
    await expect(card).toHaveCount(1)
    await card.locator('.credential-status').click()
    await expect(page).toHaveURL(new RegExp('/target/' + id))
    await expect(page.getByLabel('目标名称')).toHaveValue(name)
    await backToTargets(page)
    const bounds = await card.boundingBox()
    await card.click({ position: { x: bounds!.width - 8, y: bounds!.height / 2 } })
    await expect(page.getByRole('heading', { name: '编辑通知目标', exact: true })).toBeVisible()
    await backToTargets(page)
    await card.getByRole('button', { name, exact: true }).focus()
    await page.keyboard.press('Enter')
    await expect(page.getByRole('heading', { name: '编辑通知目标', exact: true })).toBeVisible()
    await backToTargets(page)
    await card.getByRole('button', { name: '编辑', exact: true }).click()
    await expect(page.getByRole('heading', { name: '编辑通知目标', exact: true })).toBeVisible()
    await backToTargets(page)

    const toggle = card.getByRole('switch')
    await toggle.click()
    await expect(toggle).toHaveAttribute('aria-checked', 'false')
    await expect(page).toHaveURL(/notifications\/targets/)
    await card.getByRole('button', { name: '测试', exact: true }).click()
    await expect(page.getByRole('dialog')).toContainText('暂停目标也可测试')
    await expect(page).toHaveURL(/notifications\/targets/)
    await page.getByRole('dialog').getByRole('button', { name: '取消', exact: true }).click()
    await card.getByRole('button', { name: '删除' + name, exact: true }).click()
    await expect(page.getByRole('dialog')).toContainText('任务规则和历史记录会保留')
    await expect(page).toHaveURL(/notifications\/targets/)
    await page.getByRole('dialog').getByRole('button', { name: '取消', exact: true }).click()
    const text = card.locator('.credential-status')
    await text.evaluate((element) => {
      const selection = window.getSelection()!
      selection.removeAllRanges()
      const range = document.createRange()
      range.selectNodeContents(element)
      selection.addRange(range)
    })
    await text.dispatchEvent('click', { button: 0 })
    await expect(page).toHaveURL(/notifications\/targets/)
    await page.evaluate(() => window.getSelection()?.removeAllRanges())
    await card.dispatchEvent('click', { button: 2 })
    await expect(page).toHaveURL(/notifications\/targets/)
    await card.screenshot({ path: info.outputPath('target-card-clickable.png') })
    expect((await (await page.request.get('/api/manage/history/tests')).json()).total).toBe(
      beforeTests,
    )
    expect(errors).toEqual([])
  } finally {
    expect((await page.request.delete('/api/manage/targets/' + id, { headers })).ok()).toBe(true)
  }
})
