import { expect, test, type Page } from '@playwright/test'
import type { Evaluation } from '../../src/history'
let cookies: Awaited<
  ReturnType<import('@playwright/test').APIRequestContext['storageState']>
>['cookies']
test.beforeAll(async ({ request }) => {
  const auth = await (await request.get('/api/auth/status')).json()
  const response = await request.post(auth.initialized ? '/api/auth/login' : '/api/auth/setup', {
    headers: { 'X-CSRF-Token': auth.csrf },
    data: { username: 'evaluation_admin', password: 'Synthetic-History-2026' },
  })
  expect(response.ok()).toBeTruthy()
  cookies = (await request.storageState()).cookies
})
test.beforeEach(async ({ page }) => {
  await page.context().addCookies(cookies)
  await page.route('**/*', (route) => {
    if (new URL(route.request().url()).hostname !== '127.0.0.1')
      throw Error('Unexpected external browser request')
    return route.continue()
  })
})
async function post(page: Page, status: string, index = 0) {
  const data = await (await page.request.get('/api/manage/history/posts?status=' + status)).json()
  return data.items[index].id as string
}
async function go(page: Page, id: string) {
  await page.goto('/#/content/' + id)
  await expect(page.getByRole('heading', { name: '任务匹配快照', exact: true })).toBeVisible()
}
test('matched tasks and reasons are primary, other decisions load only when expanded', async ({
  page,
}, info) => {
  let otherReads = 0
  page.on('request', (request) => {
    const url = new URL(request.url())
    if (url.pathname.endsWith('/evaluations') && url.searchParams.get('group') === 'other')
      otherReads++
  })
  await go(page, await post(page, 'match'))
  const rows = page.locator('.history-evaluation')
  await expect(rows).toHaveCount(1)
  await expect(rows.first()).toContainText('任务配置 v1')
  await expect(rows.first().locator('.result-pill')).toHaveText('命中')
  await expect(rows.first().locator('.evaluation-reasons')).toContainText('VPS')
  await expect(rows.first().locator('.evaluation-reasons')).not.toContainText('特别')
  await expect(page.locator('.match-result .evaluation-reasons, .match-result p')).toHaveCount(0)
  expect(otherReads).toBe(0)
  const expand = page.getByRole('button', { name: '查看其他任务判定（1）', exact: true })
  await expect(expand).toHaveAttribute('aria-expanded', 'false')
  await page
    .locator('.support-panel')
    .screenshot({ path: info.outputPath('evaluations-collapsed.png') })
  await expand.focus()
  await page.keyboard.press('Enter')
  await expect(rows).toHaveCount(2)
  expect(otherReads).toBe(1)
  const other = page.locator('#other-task-evaluations .history-evaluation')
  await expect(other).toContainText('特别标题关注 · 已删除')
  await expect(other.locator('button')).toHaveCount(0)
  await expect(other.locator('.result-pill')).toHaveText('不命中')
  await expect(other.locator('.evaluation-reasons')).toContainText('特别')
  const collapse = page.getByRole('button', { name: '收起其他任务判定（1）', exact: true })
  await expect(collapse).toHaveAttribute('aria-expanded', 'true')
  await expect(collapse.locator('svg')).toHaveCSS('transform', 'matrix(-1, 0, 0, -1, 0, 0)')
  await page
    .locator('.support-panel')
    .screenshot({ path: info.outputPath('evaluations-expanded.png') })
  await collapse.click()
  await expect(rows).toHaveCount(1)
  await page.setViewportSize({ width: 320, height: 900 })
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
    .toBe(true)
})
test('no matches and insufficient data show every decision while baseline remains empty', async ({
  page,
}) => {
  await go(page, await post(page, 'no_match'))
  const rows = page.locator('.history-evaluation')
  await expect(rows).toHaveCount(2)
  await expect(rows.locator('.result-pill')).toHaveText(['不命中', '不命中'])
  await expect(page.locator('.other-evaluations-toggle')).toHaveCount(0)
  await go(page, await post(page, 'insufficient_data'))
  await expect(rows).toHaveCount(2)
  await expect(rows.filter({ hasText: '信息不足' })).toContainText('摘要缺失')
  await expect(page.locator('.other-evaluations-toggle')).toHaveCount(0)
  await go(page, await post(page, 'not_evaluated'))
  await expect(rows).toHaveCount(0)
  await expect(page.getByText('基线帖子：首次采集时登记，未执行规则匹配或生成通知。')).toBeVisible()
})
function decision(name: string, status: 'match' | 'no_match'): Evaluation {
  return {
    task_id: name,
    version: 3,
    name,
    deleted: false,
    at: 1792368000,
    result: {
      status,
      reasons: [
        { code: 'all_of', truth: status === 'match' ? 'true' : 'false', term: name, group: 0 },
      ],
    },
  }
}
test('primary and other pagination remain independent and a failed expansion preserves matches', async ({
  page,
}) => {
  const id = await post(page, 'match')
  const matches = ['命中甲', '命中乙', '命中丙'].map((name) => decision(name, 'match'))
  const others = ['其他甲', '其他乙', '其他丙', '其他丁'].map((name) => decision(name, 'no_match'))
  let fail = true
  await page.route('**/api/manage/history/posts/' + id + '/evaluations?*', async (route) => {
    const url = new URL(route.request().url())
    const primary = url.searchParams.get('group') === 'primary'
    if (!primary && fail)
      return route.fulfill({ status: 503, json: { detail: '合成其他判定读取失败' } })
    const items = primary ? matches : others
    const pageNumber = Number(url.searchParams.get('page') || 1)
    await route.fulfill({
      json: {
        total: items.length,
        matched_total: 3,
        other_total: 4,
        page: pageNumber,
        page_size: 2,
        items: items.slice((pageNumber - 1) * 2, pageNumber * 2),
      },
    })
  })
  await go(page, id)
  await expect(page.locator('.history-evaluation')).toHaveCount(2)
  await page.getByRole('button', { name: '下一页命中任务判定', exact: true }).click()
  await expect(page.locator('.history-evaluation')).toHaveCount(1)
  await expect(page.locator('.history-evaluation')).toContainText('命中丙')
  await page.getByRole('button', { name: '查看其他任务判定（4）', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('合成其他判定读取失败')
  await expect(page.locator('.history-evaluation')).toContainText('命中丙')
  fail = false
  await page.getByRole('button', { name: '重新加载', exact: true }).click()
  await expect(page.locator('#other-task-evaluations .history-evaluation')).toHaveCount(2)
  await page.getByRole('button', { name: '下一页其他任务判定', exact: true }).click()
  await expect(page.locator('#other-task-evaluations')).toContainText('其他丙')
  await expect(page.locator('#other-task-evaluations')).not.toContainText('其他甲')
  await expect(page.locator('.history-evaluation').first()).toContainText('命中丙')
  await page.getByRole('button', { name: '收起其他任务判定（4）', exact: true }).click()
  await expect(page.locator('.history-evaluation')).toHaveCount(1)
})
test('collapse and changing content discard a late other-decision response', async ({ page }) => {
  const id = await post(page, 'match')
  const next = await post(page, 'no_match')
  let release = () => {},
    started = false,
    finished = () => {}
  const held = new Promise<void>((resolve) => (release = resolve))
  const done = new Promise<void>((resolve) => (finished = resolve))
  await page.route('**/api/manage/history/posts/' + id + '/evaluations?*', async (route) => {
    if (new URL(route.request().url()).searchParams.get('group') !== 'other')
      return route.continue()
    const response = await route.fetch()
    started = true
    await held
    await route.fulfill({ response }).catch(() => {})
    finished()
  })
  await go(page, id)
  await expect(page.locator('.history-evaluation')).toHaveCount(1)
  await page.getByRole('button', { name: '查看其他任务判定（1）', exact: true }).click()
  await expect.poll(() => started).toBe(true)
  await expect(page.locator('#other-task-evaluations').getByRole('status')).toHaveText('加载中…')
  await expect(page.locator('.history-evaluation')).toHaveCount(1)
  await page.getByRole('button', { name: '收起其他任务判定（1）', exact: true }).click()
  await page.evaluate((id) => (location.hash = '/content/' + id), next)
  await expect(page.locator('.history-evaluation')).toHaveCount(2)
  release()
  await done
  await expect(page.locator('.history-evaluation')).toHaveCount(2)
  await expect(page.locator('.history-evaluation .result-pill')).toHaveText(['不命中', '不命中'])
  await expect(page.locator('.other-evaluations-toggle')).toHaveCount(0)
})
