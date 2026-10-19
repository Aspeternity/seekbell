import { expect, test } from '@playwright/test'
import { emptyTask, evaluate, initialTasks } from '../src/prototype/model'

test.beforeEach(async ({ page }) => {
  await page.route('**/*', (route) => {
    const url = new URL(route.request().url())
    if (
      url.hostname !== '127.0.0.1' ||
      url.pathname.startsWith('/api') ||
      url.pathname.startsWith('/health')
    )
      throw new Error('Unexpected backend/external request: ' + url.origin + url.pathname)
    return route.continue()
  })
  await page.goto('/prototype.html')
})

test('overview search, filters, toggle, range and local persistence', async ({ page }) => {
  await expect(page.getByRole('heading', { level: 1 })).toContainText('每一条在意的')
  await expect(page.locator('.task-row')).toHaveCount(4)
  await page.getByLabel('搜索任务').fill('不存在')
  await expect(page.getByText('没有找到匹配的任务')).toBeVisible()
  await page.getByRole('button', { name: '清除筛选' }).click()
  await page.getByLabel('筛选任务状态').selectOption('paused')
  await expect(page.locator('.task-row')).toHaveCount(1)
  await page.getByRole('switch', { name: '闲置设备好物启用状态' }).click()
  await expect(page.locator('.task-row')).toHaveCount(0)
  await page.getByLabel('筛选任务状态').selectOption('all')
  await page.reload()
  await expect(page.getByRole('switch', { name: '闲置设备好物启用状态' })).toBeChecked()
  await page.getByRole('button', { name: '7 天', exact: true }).click()
  await expect(page.getByText('合计 268 条')).toBeVisible()
})

test('create, validation, tags, targets and reload', async ({ page }) => {
  await page.getByRole('button', { name: '新建任务', exact: true }).click()
  await expect(page.getByRole('heading', { name: '新建监控任务' })).toBeVisible()
  await page.getByRole('button', { name: '保存任务', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('请填写任务名称')
  await expect(page.getByRole('alert')).toContainText('请至少选择一个通知目标')
  await page.getByLabel('任务名称').fill('测试任务')
  await page.getByLabel('条件组1全部包含', { exact: true }).fill('Docker compose')
  await page.getByLabel('条件组1全部包含', { exact: true }).press('Enter')
  await page.getByRole('checkbox', { name: '家庭服务 Webhook' }).check()
  await page.getByRole('button', { name: '保存任务', exact: true }).click()
  await expect(page.getByRole('heading', { level: 1 })).toContainText('每一条在意的')
  await page.reload()
  await expect(page.locator('.task-row')).toHaveCount(5)
  await page.getByRole('button', { name: '编辑测试任务', exact: true }).click()
  await expect(page.getByLabel('任务名称')).toHaveValue('测试任务')
  await expect(page.getByRole('checkbox', { name: '家庭服务 Webhook' })).toBeChecked()
  await expect(page.locator('.tag-input .tag').first()).toContainText('Docker compose')
})

test('editor tests match, exclusion, missing field and history without sending', async ({
  page,
}) => {
  await page.getByRole('button', { name: '编辑好价服务器雷达', exact: true }).click()
  await page.getByRole('button', { name: '试匹配这条帖子' }).click()
  await expect(page.locator('.match-result')).toHaveClass(/yes/)
  await page.getByLabel('帖子标题').fill('求购 DMIT 优惠')
  await page.getByRole('button', { name: '试匹配这条帖子' }).click()
  await expect(page.locator('.match-result')).toHaveClass(/no/)
  await page.getByRole('radio', { name: '标题 + 摘要 覆盖更多线索' }).check()
  await page.getByLabel('帖子标题').fill('DMIT 套餐更新')
  await page.getByRole('checkbox', { name: '模拟摘要字段缺失' }).check()
  await page.getByRole('button', { name: '试匹配这条帖子' }).click()
  await expect(page.locator('.match-result')).toHaveClass(/unknown/)
  await page.getByRole('button', { name: '历史样本', exact: true }).click()
  await page.getByRole('button', { name: '试匹配 5 条样本' }).click()
  await expect(page.locator('.history-results article')).toHaveCount(5)
  await expect(page.locator('.history-result-summary')).toContainText('命中 2 / 5 条')
})

test('unsaved edits require explicit discard and stay out of saved task', async ({ page }) => {
  await page.getByRole('button', { name: '编辑好价服务器雷达', exact: true }).click()
  await page.getByLabel('任务名称').fill('不保存的名字')
  await page.getByRole('button', { name: '返回概览' }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.getByRole('button', { name: '继续编辑' }).click()
  await expect(page.getByLabel('任务名称')).toHaveValue('不保存的名字')
  await page.getByRole('button', { name: '取消', exact: true }).click()
  await page.getByRole('button', { name: '放弃修改并离开' }).click()
  await expect(page.getByRole('button', { name: '编辑好价服务器雷达', exact: true })).toBeVisible()
  await expect(page.getByText('不保存的名字', { exact: true })).toHaveCount(0)
})

test('responsive screenshots, navigation and no runtime errors', async ({ page }, testInfo) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error' || message.type() === 'warning') errors.push(message.text())
  })
  await page.reload()
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('overview.png'), fullPage: true })
  if (testInfo.project.name === 'mobile') {
    await page.getByRole('button', { name: '打开导航' }).click()
    await expect(page.getByRole('button', { name: '关闭导航' })).toBeFocused()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('button', { name: '打开导航' })).toBeFocused()
    await page.getByRole('button', { name: '打开导航' }).click()
    await page.getByRole('button', { name: '监控任务', exact: false }).click()
  } else {
    await page.getByRole('button', { name: '编辑好价服务器雷达', exact: true }).click()
  }
  await expect(page.getByRole('heading', { name: '编辑监控任务' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('editor.png'), fullPage: true })
  for (const width of [320, 360, 390, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      'no overflow at ' + width,
    ).toBe(true)
  }
  expect(errors).toEqual([])
})

test('rule preview handles empty groups, field boundaries and precision', () => {
  const task = structuredClone(initialTasks[0]!)
  task.groups.push({ all: [], any: [] })
  expect(
    evaluate(task, { title: '无关帖子', summary: '', author: null, category: null }).status,
  ).toBe('no')
  task.scope = 'title_summary'
  task.exclude = []
  task.groups = [{ all: ['DMIT优惠'], any: [] }]
  expect(
    evaluate(task, { title: 'DMIT', summary: '优惠', author: null, category: null }).status,
  ).toBe('no')
  task.groups = [{ all: ['DMIT'], any: [] }]
  task.exclude = ['求购']
  expect(
    evaluate(task, { title: 'DMIT', summary: null, author: null, category: null }).status,
  ).toBe('unknown')
  task.scope = 'title'
  task.wholeWord = true
  expect(
    evaluate(task, { title: 'myDMIT', summary: '', author: null, category: null }).status,
  ).toBe('no')
  task.authorsInclude = ['Author']
  expect(
    evaluate(task, { title: 'DMIT', summary: '', author: 'author', category: null }).status,
  ).toBe('no')
  expect(
    evaluate(emptyTask(), { title: '任意', summary: null, author: null, category: null }).status,
  ).toBe('yes')
})
