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
async function go(page: Page, id: string, heading = '命中依据') {
  await page.goto('/#/content/' + id)
  await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible()
}
test('one match shows only its own evidence even with nine other decisions', async ({
  page,
}, info) => {
  const groups: string[] = []
  await page.route('**/api/manage/history/posts/*/evaluations?*', async (route) => {
    const group = new URL(route.request().url()).searchParams.get('group')!
    groups.push(group)
    expect(group).toBe('matched')
    const response = await route.fetch()
    const data = await response.json()
    data.other_total = 9
    await route.fulfill({ json: data })
  })
  await go(page, await post(page, 'match'))
  const rows = page.locator('.history-evaluation')
  await expect(rows).toHaveCount(1)
  await expect(rows.first()).toContainText('任务配置 v1')
  await expect(rows.first().locator('.result-pill')).toHaveText('命中')
  await expect(rows.first().locator('.evaluation-reasons')).toContainText('VPS')
  await expect(rows.first().locator('.evaluation-reasons')).not.toContainText('特别')
  await expect(page.getByRole('button', { name: /其他任务判定/ })).toHaveCount(1)
  await expect(page.getByText('特别标题关注', { exact: true })).toHaveCount(0)
  await expect(page.getByLabel('下一页命中任务判定', { exact: true })).toHaveCount(0)
  expect(groups).toEqual(['matched'])
  await page.locator('.support-panel').screenshot({ path: info.outputPath('matched-evidence.png') })
  await page.setViewportSize({ width: 320, height: 900 })
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
    .toBe(true)
})
test('non-matches show a single saved reason while missing states stay honest', async ({
  page,
}) => {
  for (const [status, heading] of [
    ['no_match', '未命中原因'],
    ['insufficient_data', '判定信息不足'],
    ['not_evaluated', '未参与匹配'],
  ]) {
    await go(page, await post(page, status!), heading)
    await expect(page.locator('.history-evaluation')).toHaveCount(0)
    if (status === 'not_evaluated') {
      await expect(
        page.getByText('首次采集基线：只登记帖子，未执行规则匹配或生成通知。', { exact: true }),
      ).toBeVisible()
    } else {
      await expect(page.locator('.diagnosis-task')).toHaveCount(1)
      await expect(page.locator('.diagnosis-cause')).toBeVisible()
    }
  }
  const id = await post(page, 'no_match')
  await page.route('**/api/manage/history/posts/' + id, async (route) => {
    const response = await route.fetch()
    const data = await response.json()
    data.baseline = null
    data.status = 'unrecorded'
    await route.fulfill({ json: data })
  })
  await go(page, id, '暂无判定记录')
  await expect(
    page.getByText('没有保存当时的任务判定，无法还原原因；不会用当前规则替代历史结果。', {
      exact: true,
    }),
  ).toBeVisible()
  await expect(page.locator('.diagnosis-cause')).toHaveCount(0)
})
function decision(name: string, deleted = false): Evaluation {
  return {
    task_id: name,
    version: 3,
    name,
    deleted,
    at: 1792368000,
    result: { status: 'match', reasons: [{ code: 'all_of', truth: 'true', term: name, group: 0 }] },
  }
}
test('multiple matches paginate, keep deleted snapshots and expose retry without a false empty state', async ({
  page,
}) => {
  const id = await post(page, 'match')
  const matches = [decision('命中甲'), decision('命中乙', true), decision('命中丙')]
  let fail = true
  await page.route('**/api/manage/history/posts/' + id + '/evaluations?*', async (route) => {
    const url = new URL(route.request().url())
    expect(url.searchParams.get('group')).toBe('matched')
    const pageNumber = Number(url.searchParams.get('page') || 1)
    if (pageNumber === 2 && fail)
      return route.fulfill({ status: 503, json: { detail: '合成命中依据读取失败' } })
    await route.fulfill({
      json: {
        total: 3,
        matched_total: 3,
        other_total: 9,
        page: pageNumber,
        page_size: 2,
        items: matches.slice((pageNumber - 1) * 2, pageNumber * 2),
      },
    })
  })
  await go(page, id)
  await expect(page.locator('.history-evaluation')).toHaveCount(2)
  const deleted = page.locator('.history-evaluation').filter({ hasText: '命中乙 · 已删除' })
  await expect(deleted).toContainText('任务配置 v3')
  await expect(deleted.locator('button')).toHaveCount(0)
  await expect(deleted.locator('.evaluation-reasons')).toContainText('命中乙')
  await page.getByRole('button', { name: '下一页命中任务判定', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('合成命中依据读取失败')
  await expect(page.getByText('该内容未命中任何任务。', { exact: true })).toHaveCount(0)
  fail = false
  await page.getByRole('button', { name: '重新加载', exact: true }).click()
  await expect(page.locator('.history-evaluation')).toHaveCount(1)
  await expect(page.locator('.history-evaluation')).toContainText('命中丙')
  await expect(page.getByRole('button', { name: /其他任务判定/ })).toHaveCount(1)
})
test('cold reads do not pretend to be no match and changing content rejects late evidence', async ({
  page,
}) => {
  const id = await post(page, 'match')
  const next = await post(page, 'no_match')
  let release = () => {},
    started = false,
    finished = () => {}
  const held = new Promise<void>((resolve) => (release = resolve))
  const done = new Promise<void>((resolve) => (finished = resolve))
  await page.route('**/api/manage/history/posts/' + id + '/evaluations?*', async (route) => {
    const response = await route.fetch()
    started = true
    await held
    await route.fulfill({ response }).catch(() => {})
    finished()
  })
  await go(page, id)
  await expect.poll(() => started).toBe(true)
  await expect(page.locator('.support-panel').getByRole('status')).toHaveText('加载中…')
  await expect(page.getByText('该内容未命中任何任务。', { exact: true })).toHaveCount(0)
  await page.evaluate((id) => (location.hash = '/content/' + id), next)
  await expect(page.getByRole('heading', { name: '未命中原因', exact: true })).toBeVisible()
  release()
  await done
  await expect(page.locator('.history-evaluation')).toHaveCount(0)
  await expect(page.getByRole('heading', { name: '未命中原因', exact: true })).toBeVisible()
  await page.unroute('**/api/manage/history/posts/' + id + '/evaluations?*')
  await page.evaluate((id) => (location.hash = '/content/' + id), id)
  await expect(page.locator('.history-evaluation')).toHaveCount(1)
})
