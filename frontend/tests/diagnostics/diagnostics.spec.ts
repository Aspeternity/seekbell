import { expect, test, type Page } from '@playwright/test'
import { selectChoice } from '../select'
let cookies: Awaited<
  ReturnType<import('@playwright/test').APIRequestContext['storageState']>
>['cookies']
const pageErrors = new WeakMap<Page, string[]>()
test.beforeAll(async ({ request }) => {
  const info = await (await request.get('/api/auth/status')).json()
  const response = await request.post(info.initialized ? '/api/auth/login' : '/api/auth/setup', {
    headers: { 'X-CSRF-Token': info.csrf },
    data: { username: 'diagnosis_admin', password: 'Synthetic-Diagnosis-2026' },
  })
  expect(response.ok()).toBe(true)
  cookies = (await request.storageState()).cookies
})
test.beforeEach(async ({ page }) => {
  pageErrors.set(page, [])
  page.on('pageerror', (error) => pageErrors.get(page)!.push(error.message))
  await page.context().addCookies(cookies)
  await page.route('**/*', (route) => {
    if (new URL(route.request().url()).hostname !== '127.0.0.1')
      throw Error('Unexpected external browser request')
    return route.continue()
  })
})
test.afterEach(async ({ page }) => expect(pageErrors.get(page)).toEqual([]))
async function task(page: Page) {
  const workspace = await (await page.request.get('/api/manage/workspace')).json()
  return workspace.tasks.find((row: any) => row.name === '000 版块值修复示例')
}
async function sample(page: Page) {
  return (
    await (
      await page.request.get('/api/manage/history/posts?q=' + encodeURIComponent('诊断样本'))
    ).json()
  ).items[0].id as string
}
async function openPost(page: Page) {
  const id = await sample(page)
  await page.goto('/#/content/' + id)
  await expect(page.getByRole('heading', { name: '未命中原因', exact: true })).toBeVisible()
  return id
}
test('mouse selection has no thick focus outline and category choices save RSS identifiers', async ({
  page,
}) => {
  const current = await task(page)
  await page.goto('/#/task/' + current.id)
  const checkbox = page
    .locator('#task-website')
    .getByRole('checkbox', { name: 'NodeSeek', exact: false })
  await checkbox.uncheck()
  await checkbox.check()
  const label = checkbox.locator('..')
  await expect
    .poll(() => label.evaluate((element) => getComputedStyle(element).outlineStyle))
    .toBe('none')
  await page.locator('#task-description').focus()
  await page.keyboard.press('Tab')
  await expect(checkbox).toBeFocused()
  await expect
    .poll(() => label.evaluate((element) => getComputedStyle(element).outlineStyle))
    .toBe('solid')
  expect(
    await label.evaluate((element) => parseFloat(getComputedStyle(element).outlineWidth)),
  ).toBeLessThanOrEqual(1.1)
  await page.getByRole('button', { name: '修改 NodeSeek 版块范围' }).click()
  await expect(
    page.locator('.category-site-editor').getByRole('checkbox', { name: '交易', exact: true }),
  ).toBeChecked()
  await page.getByLabel('帖子标题').fill('vmiss tri offer')
  await page.getByLabel('样本版块').fill('交易')
  await page.getByRole('button', { name: '试匹配这条帖子', exact: true }).click()
  await expect(page.locator('.match-result')).toHaveClass(/yes/)
  await expect(page.locator('.match-result')).toContainText('版块符合范围')
  await page.getByRole('button', { name: '保存任务', exact: true }).click()
  await expect.poll(async () => (await task(page)).version).toBeGreaterThan(current.version)
  expect((await task(page)).rule.site_categories.nodeseek).toEqual({
    mode: 'specific',
    values: ['trade'],
  })
})
test('100 trial samples use a summary and ten-row modal pages without extra requests', async ({
  page,
}, info) => {
  const current = await task(page)
  let requests = 0
  page.on('request', (request) => {
    if (request.url().endsWith('/api/manage/rules/history')) requests++
  })
  await page.goto('/#/task/' + current.id)
  await page.getByRole('button', { name: '历史样本', exact: true }).click()
  await selectChoice(page.getByLabel('最多试算条数'), '100')
  await page.getByRole('button', { name: '试匹配本地历史', exact: true }).click()
  await expect(page.locator('.history-results')).toContainText('本次试算 100 条')
  await expect(page.locator('.history-results article')).toHaveCount(0)
  await page.getByRole('button', { name: '查看结果', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '历史试匹配结果', exact: true })
  await expect(dialog.locator('.trial-result-row')).toHaveCount(10)
  await dialog.getByRole('button', { name: '下一页试算结果', exact: true }).click()
  await expect(dialog.locator('.pagination')).toContainText('2 / 10')
  await dialog
    .getByRole('group', { name: '试算结果筛选' })
    .getByRole('button', { name: /^未命中/ })
    .click()
  expect(await dialog.locator('.trial-result-row').count()).toBeLessThanOrEqual(10)
  await expect(dialog.locator('.trial-result-row .result-pill')).toHaveText(
    Array(await dialog.locator('.trial-result-row').count()).fill('不命中'),
  )
  expect(requests).toBe(1)
  await page.screenshot({ path: info.outputPath('trial-results-paged.png'), fullPage: true })
  await dialog.press('Escape')
  await expect(dialog).toHaveCount(0)
  await expect(page.getByRole('button', { name: '查看结果', exact: true })).toBeFocused()
  await page.locator('#task-name').fill('草稿变化后旧试算失效')
  await expect(page.getByRole('button', { name: '查看结果', exact: true })).toHaveCount(0)
  expect((await task(page)).name).toBe(current.name)
})
test('101 decisions keep one reason card and a searchable bounded task picker', async ({
  page,
}, info) => {
  const detailRequests: string[] = []
  page.on('request', (request) => {
    if (/\/evaluations\/[^/]+\/\d+$/.test(request.url())) detailRequests.push(request.url())
  })
  await openPost(page)
  await expect(page.locator('.diagnosis-counts')).toContainText('未命中 101')
  await expect(page.locator('.diagnosis-task')).toHaveCount(1)
  await expect(page.locator('.diagnosis-cause')).toContainText('历史版块保存值与来源标识不一致')
  await page.getByRole('combobox', { name: '查看任务判定', exact: true }).click()
  await expect(page.getByRole('listbox', { name: '历史判定任务' }).getByRole('option')).toHaveCount(
    20,
  )
  await page.getByRole('textbox', { name: '搜索判定任务', exact: true }).fill('诊断任务 099')
  await expect(page.getByRole('listbox', { name: '历史判定任务' }).getByRole('option')).toHaveCount(
    1,
  )
  await page.getByRole('option', { name: /诊断任务 099/ }).click()
  await expect(page.locator('.diagnosis-task')).toContainText('诊断任务 099')
  await expect(page.locator('.diagnosis-cause')).toContainText('没有条件组满足关键词要求')
  expect(detailRequests).toHaveLength(2)
  await page.getByRole('combobox', { name: '查看任务判定', exact: true }).click()
  await page.getByRole('textbox', { name: '搜索判定任务', exact: true }).fill('%')
  await expect(page.getByText('没有找到对应任务。', { exact: true })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.locator('.diagnosis-task')).toContainText('诊断任务 099')
  expect(
    await page
      .locator('.post-diagnosis')
      .evaluate((element) => element.getBoundingClientRect().height),
  ).toBeLessThan(800)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page
    .locator('.support-panel')
    .screenshot({ path: info.outputPath('single-task-diagnosis.png') })
})
test('current-rule trial is explicit and leaves the historical verdict intact', async ({
  page,
}) => {
  const id = await openPost(page)
  await expect(page.locator('.diagnosis-task')).toContainText('当时配置 v1')
  const before = await (await page.request.get('/api/manage/history/posts/' + id)).json()
  await page.getByRole('button', { name: '用当前规则试算', exact: true }).click()
  await expect(page.locator('.diagnosis-current')).toContainText('当前规则试算')
  await expect(page.locator('.diagnosis-current .result-pill')).toHaveText('命中')
  await expect(page.locator('.diagnosis-cause')).toContainText('历史版块保存值与来源标识不一致')
  await expect(page.locator('.diagnosis-task')).toContainText('当时配置 v1')
  expect(await (await page.request.get('/api/manage/history/posts/' + id)).json()).toEqual(before)
  await page.getByRole('button', { name: '查看完整条件', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '完整匹配条件', exact: true })
  await expect(dialog).toContainText('全部包含词「vmiss」：已出现')
  await expect(dialog).toContainText('排除词「求购」：未出现')
  await expect(dialog).not.toContainText('all_of')
  await dialog.press('Escape')
})
test('switching content rejects a late historical detail', async ({ page }) => {
  const id = await sample(page)
  const baseline = (
    await (await page.request.get('/api/manage/history/posts?status=not_evaluated')).json()
  ).items[0].id
  let release = () => {},
    started = false,
    finish = () => {}
  const hold = new Promise<void>((resolve) => (release = resolve))
  const done = new Promise<void>((resolve) => (finish = resolve))
  await page.route('**/api/manage/history/posts/' + id + '/evaluations/*/*', async (route) => {
    const response = await route.fetch()
    started = true
    await hold
    await route.fulfill({ response }).catch(() => {})
    finish()
  })
  await page.goto('/#/content/' + id)
  await expect.poll(() => started).toBe(true)
  await expect(page.locator('.diagnosis-cause')).toHaveCount(0)
  await page.evaluate((key) => (location.hash = '/content/' + key), baseline)
  await expect(page.getByRole('heading', { name: '未参与匹配', exact: true })).toBeVisible()
  release()
  await done
  await expect(page.locator('.diagnosis-cause')).toHaveCount(0)
})
test('failed detail reads offer retry without inventing a reason', async ({ page }) => {
  const id = await sample(page)
  await page.route(
    '**/api/manage/history/posts/' + id + '/evaluations/*/*',
    (route) => route.fulfill({ status: 503, json: { detail: '合成判定读取失败' } }),
    { times: 1 },
  )
  await page.goto('/#/content/' + id)
  await expect(page.getByRole('alert')).toContainText('合成判定读取失败')
  await expect(page.locator('.diagnosis-cause')).toHaveCount(0)
  await page.getByRole('button', { name: '重新加载', exact: true }).click()
  await expect(page.locator('.diagnosis-cause')).toContainText('历史版块保存值与来源标识不一致')
})

test('diagnosis edit actions retain the task path through both nested entry points', async ({
  page,
}) => {
  const current = await task(page)
  await openPost(page)
  await page.getByRole('button', { name: '编辑任务', exact: true }).click()
  await expect(page).toHaveURL(new RegExp('/#/task/' + current.id + '$'))
  await expect(page.getByRole('heading', { name: '编辑监控任务', exact: true })).toBeVisible()
  await expect(page.locator('#task-name')).toHaveValue(current.name)
  await openPost(page)
  await page.getByRole('button', { name: '查看完整条件', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '完整匹配条件', exact: true })
  await dialog.getByRole('button', { name: current.name, exact: true }).click()
  await expect(dialog).toHaveCount(0)
  await expect(page).toHaveURL(new RegExp('/#/task/' + current.id + '$'))
  await expect(page.getByRole('heading', { name: '编辑监控任务', exact: true })).toBeVisible()
  await expect(page.locator('#task-name')).toHaveValue(current.name)
})

test('site rows isolate same category values, retain choices and save open edits', async ({
  page,
}, info) => {
  const auth = await (await page.request.get('/api/auth/status')).json()
  const headers = { 'X-CSRF-Token': auth.csrf }
  const workspace = await (await page.request.get('/api/manage/workspace')).json()
  if (!workspace.websites.some((site: any) => site.id === 'linuxdo'))
    expect(
      (
        await page.request.post('/api/manage/websites', {
          headers,
          data: { adapter_id: 'linuxdo' },
        })
      ).ok(),
    ).toBe(true)
  await page.route('**/api/manage/workspace', async (route) => {
    const response = await route.fetch()
    const data = await response.json()
    const site = data.websites.find((item: any) => item.id === 'linuxdo')
    site.categoryOptions = [
      { value: 'trade', label: '同值分类' },
      ...Array.from({ length: 100 }, (_, i) => ({
        value: 'scope-' + i,
        label: '合成版块 ' + String(i).padStart(3, '0'),
      })),
    ]
    await route.fulfill({ response, json: data })
  })
  const created = await page.request.post('/api/manage/tasks', {
    headers,
    data: {
      name: '按站范围 ' + info.project.name,
      website_ids: ['nodeseek', 'linuxdo'],
      target_ids: workspace.tasks[0].target_ids,
      rule: {
        site_categories: {
          nodeseek: { mode: 'specific', values: ['trade'] },
          linuxdo: { mode: 'all', values: [] },
        },
      },
    },
  })
  expect(created.ok()).toBe(true)
  const id = (await created.json()).id
  await page.goto('/#/task/' + id)
  const rows = page.locator('.task-category-scopes')
  await expect(rows.locator('.category-site')).toHaveCount(2)
  await expect(rows.locator('.category-site-editor')).toHaveCount(0)
  await page.getByRole('button', { name: '修改 LINUX DO 版块范围' }).click()
  let editor = rows.locator('.category-site-editor')
  await editor.getByRole('radio', { name: '指定版块', exact: true }).check()
  await expect(editor.getByRole('button', { name: '完成', exact: true })).toBeDisabled()
  await page.getByRole('button', { name: '保存任务', exact: true }).click()
  await expect(page.locator('[data-form-errors]')).toContainText('LINUX DO：请至少选择一个版块')
  expect(
    (await (await page.request.get('/api/manage/workspace')).json()).tasks.find(
      (row: any) => row.id === id,
    ).version,
  ).toBe(1)
  const options = editor.locator('.category-choice-list')
  expect(
    await options.evaluate(
      (element) => element.scrollHeight > element.clientHeight && element.clientHeight <= 232,
    ),
  ).toBe(true)
  await editor.getByRole('searchbox', { name: '搜索 LINUX DO 版块' }).fill('同值分类')
  await editor.getByRole('checkbox', { name: '同值分类', exact: true }).check()
  const categoryLabel = editor
    .getByRole('checkbox', { name: '同值分类', exact: true })
    .locator('..')
  expect(await categoryLabel.evaluate((element) => getComputedStyle(element).outlineStyle)).toBe(
    'none',
  )
  await editor.getByRole('searchbox', { name: '搜索 LINUX DO 版块' }).fill('合成版块 099')
  await editor.getByRole('checkbox', { name: '合成版块 099', exact: true }).check()
  await editor.getByRole('button', { name: '完成', exact: true }).click()
  await expect(page.locator('.category-summary')).toContainText('NodeSeek：交易')
  await expect(page.locator('.category-summary')).toContainText('LINUX DO：同值分类、合成版块 099')
  const linuxCheckbox = page
    .locator('#task-website')
    .getByRole('checkbox', { name: 'LINUX DO', exact: false })
  await linuxCheckbox.uncheck()
  await linuxCheckbox.check()
  await page.getByRole('button', { name: '修改 LINUX DO 版块范围' }).click()
  editor = rows.locator('.category-site-editor')
  await editor.getByRole('radio', { name: '全部版块', exact: true }).check()
  await editor.getByRole('button', { name: '取消', exact: true }).click()
  await expect(page.locator('.category-summary')).toContainText('同值分类、合成版块 099')
  await page.getByRole('button', { name: '修改 LINUX DO 版块范围' }).click()
  await rows.locator('.category-site-editor').getByRole('searchbox').fill('同值分类')
  await rows
    .locator('.category-site-editor')
    .getByRole('checkbox', { name: '同值分类', exact: true })
    .uncheck()
  // Saving the task includes open selector edits; "完成" is never a second save requirement.
  await page.getByRole('button', { name: '保存任务', exact: true }).click()
  await expect
    .poll(
      async () =>
        (await (await page.request.get('/api/manage/workspace')).json()).tasks.find(
          (row: any) => row.id === id,
        ).version,
    )
    .toBe(2)
  const saved = (await (await page.request.get('/api/manage/workspace')).json()).tasks.find(
    (row: any) => row.id === id,
  )
  expect(saved.rule.site_categories).toEqual({
    nodeseek: { mode: 'specific', values: ['trade'] },
    linuxdo: { mode: 'specific', values: ['scope-99'] },
  })
  await page.goto('/#/task/' + id)
  await expect(page.locator('.category-summary')).toContainText('NodeSeek：交易')
  await expect(page.locator('.category-summary')).toContainText('LINUX DO：合成版块 099')
  await page.getByRole('button', { name: '修改 NodeSeek 版块范围' }).click()
  await expect(
    rows.locator('.category-site-editor').getByRole('checkbox', { name: '交易', exact: true }),
  ).toBeChecked()
  await rows.screenshot({ path: info.outputPath('per-site-categories.png') })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})
test('a site with no observed categories stays honest and a newly selected site starts unrestricted', async ({
  page,
}) => {
  const current = await task(page)
  await page.route('**/api/manage/workspace', async (route) => {
    const response = await route.fetch()
    const data = await response.json()
    const linux = data.websites.find((site: any) => site.id === 'linuxdo')
    if (linux) linux.categoryOptions = []
    await route.fulfill({ response, json: data })
  })
  await page.goto('/#/task/' + current.id)
  const checkbox = page
    .locator('#task-website')
    .getByRole('checkbox', { name: 'LINUX DO', exact: false })
  await checkbox.check()
  await expect(page.locator('.category-summary')).toContainText('LINUX DO：全部版块')
  await page.getByRole('button', { name: '修改 LINUX DO 版块范围' }).click()
  const editor = page.locator('.category-site-editor')
  await editor.getByRole('radio', { name: '指定版块', exact: true }).check()
  await expect(editor).toContainText('尚无版块信息')
  await expect(editor.getByRole('button', { name: '完成', exact: true })).toBeDisabled()
  await editor.getByRole('button', { name: '取消', exact: true }).click()
  await expect(page.locator('.category-summary')).toContainText('LINUX DO：全部版块')
  await checkbox.uncheck()
})
