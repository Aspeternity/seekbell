import { expect } from '@playwright/test'
import type { Page, TestInfo } from '@playwright/test'
import type { OverviewData } from '../../src/live/overview'

export async function checkCollection(page: Page, info: TestInfo, data: OverviewData) {
  const card = page.locator('.collection-card')
  const real = data.sources[0]!
  await expect(card.locator('h3')).toHaveText(real.name)
  await expect(card.locator('.source-data dt')).toHaveText([
    '最近成功采集',
    '采集间隔',
    '本日发现新帖',
  ])
  await expect(card.locator('.source-data dd').nth(1)).toContainText(String(real.interval_seconds))
  await expect(card.locator('.source-data dd').nth(2)).toContainText(String(real.today_posts))
  await expect(card.locator('.uptime-bars i')).toHaveCount(30)
  await expect(card.locator('.uptime-bars i:not(.is-empty)')).toHaveCount(real.recent_runs.length)
  await expect(card.locator('.collection-summary')).toHaveCount(0)
  await expect(card.getByRole('button', { name: '下一个网站', exact: true })).toHaveCount(0)

  await card.screenshot({ path: info.outputPath('collection-single.png') })

  // Future-site fixtures exercise the presentation without shipping new adapters.
  let sources: OverviewData['sources'] = Array.from({ length: 6 }, (_, i) => ({
    ...real,
    website_id: 'fixture-' + i,
    source_id: 'fixture-source-' + i,
    name: '测试网站 ' + (i + 1),
    enabled: true,
    failures: i === 2 ? 1 : 0,
    interval_seconds: 30 + i,
    today_posts: 100 + i,
    last_success_at: data.end - 60,
    recent_runs: [],
  }))
  const pattern = '**/api/manage/overview*'
  await page.route(pattern, (route) => route.fulfill({ json: { ...data, sources } }))
  const refresh = async () => {
    await page.getByRole('button', { name: '刷新概览', exact: true }).click()
    await expect(page.getByRole('button', { name: '刷新概览', exact: true })).toBeEnabled()
  }
  await refresh()
  await expect(card.locator('.collection-summary')).toContainText('6 个网站')
  await card.getByRole('button', { name: '查看 1 个异常网站', exact: true }).click()
  await expect(card.locator('h3')).toHaveText('测试网站 3')
  await expect(card.locator('.collection-health')).toHaveText('异常')
  await expect(card.getByRole('dialog')).toHaveCount(0)
  await card.screenshot({ path: info.outputPath('collection-multiple.png') })
  await expect(card.locator('.uptime-label')).toContainText('暂无记录')
  await card.getByRole('button', { name: '下一个网站', exact: true }).click()
  await expect(card.locator('h3')).toHaveText('测试网站 4')
  await expect(card.locator('.source-data dd').nth(1)).toContainText('33')
  await expect(card.locator('.source-data dd').nth(2)).toContainText('103')
  await expect(card.locator('.collection-health')).toHaveText('正常')

  sources = sources.map((source, i) => ({
    ...source,
    failures: i === 1 || i === 2 || i === 4 ? 2 : 0,
  }))
  await refresh()
  await expect(card.locator('h3')).toHaveText('测试网站 4') // Refresh preserves selection.
  const trigger = card.getByRole('button', { name: '查看 3 个异常网站', exact: true })
  await trigger.click()
  const popup = card.getByRole('dialog', { name: '异常网站', exact: true })
  await expect(popup.getByRole('button')).toHaveCount(3)
  await expect(popup.getByRole('button').first()).toBeFocused()
  await card.screenshot({ path: info.outputPath('collection-errors-card.png') })
  await page.screenshot({ path: info.outputPath('collection-errors.png'), fullPage: true })
  await page.keyboard.press('Escape')
  await expect(popup).not.toBeVisible()
  await expect(trigger).toBeFocused()
  await trigger.click()
  await page.getByRole('heading', { name: '采集状态', exact: true }).click()
  await expect(popup).not.toBeVisible()
  await trigger.click()
  await page.locator('h1').click()
  await expect(popup).not.toBeVisible()
  await trigger.click()
  await popup.getByRole('button', { name: '测试网站 5 异常', exact: false }).click()
  await expect(card.locator('h3')).toHaveText('测试网站 5')
  await expect(popup).not.toBeVisible()
  await expect(trigger).toBeFocused()
  await card.getByRole('button', { name: '下一个网站', exact: true }).click()
  await card.getByRole('button', { name: '下一个网站', exact: true }).click()
  await expect(card.locator('h3')).toHaveText('测试网站 1')
  await card.getByRole('button', { name: '上一个网站', exact: true }).click()
  await expect(card.locator('h3')).toHaveText('测试网站 6')
  for (const width of [320, 390, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    await trigger.click()
    expect(await card.evaluate((e) => e.scrollWidth <= e.clientWidth)).toBe(true)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.keyboard.press('Escape')
  }
  sources = sources
    .slice(0, 2)
    .map((source, i) => ({ ...source, enabled: i === 0, failures: i === 1 ? 1 : 0 }))
  await refresh()
  await expect(card.locator('h3')).toHaveText('测试网站 1') // Removed selection falls back safely.
  await expect(card.locator('.collection-summary')).toContainText('0 个异常')
  await card.getByRole('button', { name: '下一个网站', exact: true }).click()
  await expect(card.locator('.collection-health')).toHaveText('已暂停')
  await page.unroute(pattern)
  await page.setViewportSize(
    info.project.name === 'mobile' ? { width: 390, height: 844 } : { width: 1440, height: 1000 },
  )
  await refresh()
  await expect(card.locator('h3')).toHaveText(real.name)
  await expect(card.locator('.collection-summary')).toHaveCount(0)
}

export async function checkWebsitePicker(page: Page, info: TestInfo) {
  await page.goto('/#/task/new')
  const picker = page.locator('.task-website-picker')
  await expect(picker).toContainText('NodeSeek')
  const description = await page.locator('#task-description').boundingBox()
  const label = await page.locator('label[for="task-website"]').boundingBox()
  expect(label!.y - description!.y - description!.height).toBeGreaterThanOrEqual(20)
  await picker.click()
  const menu = page.locator('.task-website-menu')
  await expect(menu).toBeVisible()
  const option = menu.getByRole('option').first()
  await expect(option).toContainText('NodeSeek')
  // The menu stays in the same scaled form coordinate system.
  await expect
    .poll(async () => {
      const control = await picker.boundingBox()
      const popup = await menu.boundingBox()
      return Math.max(Math.abs(popup!.x - control!.x), Math.abs(popup!.width - control!.width))
    })
    .toBeLessThan(3)
  const input = await picker.boundingBox()
  const dropdown = await menu.boundingBox()
  expect(dropdown!.y - input!.y - input!.height).toBeGreaterThanOrEqual(-1)
  expect(dropdown!.y - input!.y - input!.height).toBeLessThan(12)
  expect(await option.evaluate((e) => getComputedStyle(e).color)).toBe('rgb(183, 94, 50)')
  await page.locator('#basic').screenshot({ path: info.outputPath('task-website-field.png') })
  await page.screenshot({ path: info.outputPath('task-website-picker.png'), fullPage: true })
  const viewport = page.viewportSize()!
  for (const width of [320, 390, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    await expect
      .poll(async () => {
        const input = await picker.boundingBox()
        const popup = await menu.boundingBox()
        return Math.max(Math.abs(popup!.x - input!.x), Math.abs(popup!.width - input!.width))
      })
      .toBeLessThan(3)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
  await page.keyboard.press('Escape')
  await expect(menu).not.toBeVisible()
  await page.setViewportSize(viewport)
  await page.locator('h1').click()
}
