import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
const credentials = { username: 'history_admin', password: 'Synthetic-History-2026' }
function gate() {
  let release = () => {}
  const promise = new Promise<void>((resolve) => (release = resolve))
  return { promise, release }
}
async function navigate(page: Page, path: string) {
  await page.evaluate((path) => (location.hash = path), path)
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
    .getByRole('button', { name: initialized ? '登录工作空间' : '创建管理员并进入' })
    .click()
  await expect(page.getByTestId('overview-matches')).toContainText('24条')
}
test('cold entry keeps the heading and all filter geometry stable while options arrive separately', async ({
  page,
}) => {
  await login(page)
  const options = gate(),
    listing = gate()
  await page.route('**/api/manage/history/options', async (route) => {
    const response = await route.fetch(),
      data = await response.json()
    data.tasks[0].name = '很长的任务名称'.repeat(10)
    await options.promise
    await route.fulfill({ json: data })
  })
  await page.route(/\/api\/manage\/history\/posts(?:\?|$)/, async (route) => {
    const response = await route.fetch()
    await listing.promise
    await route.fulfill({ response })
  })
  await navigate(page, '/content')
  const input = page.getByLabel('搜索内容', { exact: true })
  await expect(input).toBeVisible()
  const start = await input.boundingBox()
  await expect(page.locator('.page-heading > .small-badge')).toHaveCount(1)
  options.release()
  await expect(page.getByLabel('关联任务').locator('option')).toHaveCount(2)
  let box = (await input.boundingBox())!
  expect(Math.abs(box.y - start!.y)).toBeLessThan(1)
  expect(Math.abs(box.width - start!.width)).toBeLessThan(1)
  await expect(page.getByRole('button', { name: '发现日期', exact: true })).toHaveText('全部日期')
  box = (await input.boundingBox())!
  expect(Math.abs(box.y - start!.y)).toBeLessThan(1)
  expect(Math.abs(box.width - start!.width)).toBeLessThan(1)
  listing.release()
  await expect(page.locator('.content-row')).toHaveCount(20)
  expect(Math.abs((await input.boundingBox())!.y - start!.y)).toBeLessThan(1)
})
test('filtering retains one inert result snapshot and commits counts and rows together without a blank frame', async ({
  page,
}, info) => {
  await login(page)
  await navigate(page, '/content')
  await expect(page.locator('.content-row')).toHaveCount(20)
  const metrics = await page.locator('.metric-strip strong').allTextContents()
  const input = page.getByLabel('搜索内容')
  await page.evaluate(() => window.scrollTo(0, 150))
  const before = await input.boundingBox()
  const rowBefore = await page.locator('.content-row').first().boundingBox()
  const held = gate()
  let started = false
  await page.route(/\/api\/manage\/history\/posts(?:\?|$)/, async (route) => {
    if (new URL(route.request().url()).searchParams.get('q') !== '%_') return route.fallback()
    const response = await route.fetch()
    started = true
    await held.promise
    await route.fulfill({ response })
  })
  await input.fill('%_')
  await expect.poll(() => started).toBe(true)
  await expect(page.locator('.content-row')).toHaveCount(20)
  await expect(page.locator('.metric-strip strong')).toHaveText(metrics)
  await expect(page.locator('.content-result-snapshot')).toHaveAttribute('inert', '')
  const pending = await input.boundingBox()
  expect(Math.abs(pending!.y - before!.y)).toBeLessThan(1)
  await expect(page.locator('.remote-feedback')).toContainText('上次结果')
  const first = await page.locator('.content-row').first().boundingBox()
  await page.screenshot({ path: info.outputPath('retained-filter-results.png'), fullPage: true })
  expect(first!.height).toBe(rowBefore!.height)
  expect(Math.abs(first!.y - rowBefore!.y)).toBeLessThan(1)
  held.release()
  await expect(page.locator('.content-row')).toHaveCount(1)
  await expect(page.locator('.metric-strip strong').first()).toHaveText('1')
  await expect(page.locator('.content-result-snapshot')).not.toHaveAttribute('inert', '')
  await expect(page.locator('.remote-feedback')).toHaveCount(0)
  await page.route(
    /\/api\/manage\/history\/posts(?:\?|$)/,
    (route) => route.fulfill({ status: 503, json: { detail: '合成新筛选失败' } }),
    { times: 1 },
  )
  await input.fill('missing-new-query')
  await expect(page.getByRole('alert')).toContainText('上次结果')
  await expect(page.locator('.content-row')).toHaveCount(1)
  await expect(page.locator('.metric-strip strong').first()).toHaveText('1')
  await page.getByRole('button', { name: '重新加载', exact: true }).click()
  await expect(page.getByText('没有符合条件的内容', { exact: true })).toBeVisible()
  const late = gate()
  let lateStarted = false
  await page.route(/\/api\/manage\/history\/posts(?:\?|$)/, async (route) => {
    if (new URL(route.request().url()).searchParams.get('q') !== '读取样本') return route.fallback()
    const response = await route.fetch()
    lateStarted = true
    await late.promise
    await route.fulfill({ response })
  })
  await input.fill('读取样本')
  await expect.poll(() => lateStarted).toBe(true)
  await input.fill('%_')
  await expect(page.locator('.content-row')).toHaveCount(1)
  const finished = page.waitForResponse(
    (response) => new URL(response.url()).searchParams.get('q') === '读取样本',
  )
  late.release()
  await finished
  await page.evaluate(() => new Promise(requestAnimationFrame))
  await expect(page.locator('.content-row')).toHaveCount(1)
  await expect(page.locator('.metric-strip strong').first()).toHaveText('1')
})
test('post rows label publication time separately and fall back honestly when RSS omits it', async ({
  page,
}) => {
  await login(page)
  let source: any
  await page.route(/\/api\/manage\/history\/posts(?:\?|$)/, async (route) => {
    const response = await route.fetch(),
      data = await response.json()
    source = data.items[0]
    source.published_at = source.first_seen_at - 7200
    data.items[1].published_at = null
    await route.fulfill({ json: data })
  })
  await navigate(page, '/content')
  await expect(page.locator('.content-row')).toHaveCount(20)
  const first = page.locator('.content-row').first().locator('time')
  await expect(first).toContainText('发布')
  await expect(first).toHaveAttribute(
    'datetime',
    new Date(source.published_at * 1000).toISOString(),
  )
  await expect(first).toHaveAttribute('title', /首次发现/)
  await expect(page.locator('.content-row').nth(1).locator('time')).toContainText('发现')
  await expect(page.getByLabel('发现日期')).toBeVisible()
})

test('complete result labels fit and every noninteractive part of a post opens its details', async ({
  page,
}, info) => {
  await login(page)
  await navigate(page, '/content')
  await expect(page.locator('.content-row')).toHaveCount(20)
  await expect(page.locator('.metric-strip')).not.toContainText('时间显示')
  await expect(page.locator('.metric-strip button, .metric-strip a')).toHaveCount(0)
  const select = page.getByLabel('匹配结果', { exact: true })
  for (const option of ['all', 'unrecorded']) {
    await select.selectOption(option)
    const fit = await select.evaluate((node: HTMLSelectElement) => {
      const style = getComputedStyle(node),
        canvas = document.createElement('canvas')
      const context = canvas.getContext('2d')!
      context.font = style.font
      return (
        node.clientWidth -
        parseFloat(style.paddingLeft) -
        parseFloat(style.paddingRight) -
        context.measureText(node.selectedOptions[0]!.text).width
      )
    })
    expect(fit).toBeGreaterThanOrEqual(18)
  }
  await select.selectOption('all')
  for (const part of [
    '.content-excerpt',
    '.content-row-meta',
    '.result-pill',
    'time',
    'blank',
    '.content-title',
  ]) {
    await expect(page.locator('.content-row')).toHaveCount(20)
    const row = page.locator('.content-row').first()
    const title = await row.locator('.content-title').textContent()
    if (part === 'blank') {
      const box = (await row.boundingBox())!
      await row.click({ position: { x: box.width - 5, y: box.height - 5 } })
    } else await row.locator(part).click()
    await expect(page.locator('h1.article-heading')).toContainText(title!.trim())
    await page.getByRole('button', { name: '返回内容列表', exact: true }).click()
  }
  const row = page.locator('.content-row').first()
  await row.locator('.content-excerpt').evaluate((el) => {
    const range = document.createRange()
    range.selectNodeContents(el)
    window.getSelection()!.removeAllRanges()
    window.getSelection()!.addRange(range)
  })
  await row.locator('.content-excerpt').dispatchEvent('click', { button: 0 })
  await expect(page.locator('h1')).toHaveText('内容与命中')
  await page.evaluate(() => window.getSelection()?.removeAllRanges())
  await row.locator('.content-excerpt').dispatchEvent('click', { button: 0, ctrlKey: true })
  await row.locator('.content-excerpt').dispatchEvent('click', { button: 2 })
  await expect(page.locator('h1')).toHaveText('内容与命中')
  await row.locator('.content-title').focus()
  await row.locator('.content-title').press('Enter')
  await expect(page.locator('h1.article-heading')).toBeVisible()
  await page.getByRole('button', { name: '返回内容列表', exact: true }).click()
  await page.screenshot({ path: info.outputPath('content-approved-fixes.png'), fullPage: true })
})
