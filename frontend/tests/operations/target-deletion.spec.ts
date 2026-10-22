import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
const credentials = { username: 'operations_admin', password: 'Synthetic-Operations-2026' }
async function session(page: Page) {
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
  return { 'X-CSRF-Token': (await (await page.request.get('/api/auth/status')).json()).csrf }
}
test('target deletion shows only sole-target tasks, confirms fresh impact and preserves other tasks', async ({
  page,
}, info) => {
  const headers = await session(page)
  const tasks: string[] = [],
    targets: string[] = []
  const base = '删除验收 ' + info.project.name
  async function target(name: string) {
    const response = await page.request.post('/api/manage/targets', {
      headers,
      data: {
        name,
        kind: 'webhook',
        enabled: false,
        config: { url: 'https://receiver.example.test/synthetic' },
      },
    })
    expect(response.ok()).toBe(true)
    const id = (await response.json()).id
    targets.push(id)
    return id
  }
  async function task(name: string, ids: string[], enabled: boolean) {
    const response = await page.request.post('/api/manage/tasks', {
      headers,
      data: {
        name,
        description: '保留规则',
        website_id: 'nodeseek',
        enabled,
        rule: { groups: [{ all_of: ['VPS'] }] },
        target_ids: ids,
      },
    })
    expect(response.ok()).toBe(true)
    const id = (await response.json()).id
    tasks.push(id)
    return id
  }
  try {
    const old = await target(base),
      other = await target(base + ' 其他')
    const active = await task(base + ' 唯一启用', [old], true)
    const paused = await task(base + ' 唯一暂停', [old], false)
    const multiple = await task(base + ' 多目标启用', [old, other], true)
    const multiplePaused = await task(base + ' 多目标暂停', [old, other], false)
    await page.reload()
    await page.goto('/#/notifications/targets')
    const card = page
      .locator('.notification-card')
      .filter({ has: page.getByRole('button', { name: base, exact: true }) })
    const trigger = card.getByRole('button', { name: '删除' + base, exact: true })
    await trigger.click()
    const dialog = page.getByRole('dialog', { name: '删除「' + base + '」？', exact: true })
    const list = dialog.getByRole('list', { name: '删除后没有通知目标的任务' })
    await expect(list.getByRole('listitem')).toHaveCount(2)
    await expect(list).toContainText(base + ' 唯一启用')
    await expect(list).toContainText('删除后暂停')
    await expect(list).toContainText(base + ' 唯一暂停')
    await expect(list).toContainText('保持暂停')
    await expect(dialog).not.toContainText('多目标')
    await expect(dialog).not.toContainText('个关联任务')
    await page.keyboard.press('Escape')
    await expect(dialog).toHaveCount(0)
    await expect(trigger).toBeFocused()
    await trigger.click()
    await expect(list.getByRole('listitem')).toHaveCount(2)
    const late = await task(base + ' 新关联', [old], true)
    await dialog.getByRole('button', { name: '删除', exact: true }).click()
    await expect(dialog.getByRole('alert')).toContainText('关联配置已更新')
    await expect(dialog.getByRole('button', { name: '删除', exact: true })).toBeDisabled()
    await dialog.getByRole('button', { name: '重新加载', exact: true }).click()
    await expect(list.getByRole('listitem')).toHaveCount(3)
    let deletes = 0
    let release = () => {}
    const pending = new Promise<void>((resolve) => (release = resolve))
    await page.route('**/api/manage/targets/' + old, async (route) => {
      if (route.request().method() === 'DELETE') {
        deletes++
        await pending
      }
      await route.continue()
    })
    const remove = dialog.getByRole('button', { name: /^(删除|正在删除…)$/ })
    try {
      await remove.click()
      await expect(remove).toBeDisabled()
      await remove.dispatchEvent('click')
      await page.keyboard.press('Escape')
      await expect(dialog).toBeVisible()
    } finally {
      release()
    }
    await expect(card).toHaveCount(0)
    await expect(dialog).toHaveCount(0)
    expect(deletes).toBe(1)
    const workspace = await (await page.request.get('/api/manage/workspace')).json()
    for (const id of [active, paused, late]) {
      const item = workspace.tasks.find((row: any) => row.id === id)
      expect(item.enabled).toBe(false)
      expect(item.target_ids).toEqual([])
      expect(item.description).toBe('保留规则')
    }
    for (const [id, enabled] of [
      [multiple, true],
      [multiplePaused, false],
    ]) {
      const item = workspace.tasks.find((row: any) => row.id === id)
      expect(item.enabled).toBe(enabled)
      expect(item.target_ids).toEqual([other])
    }
    await page.goto('/#/tasks')
    const toggle = page.getByRole('switch', { name: base + ' 唯一启用启用状态', exact: true })
    await toggle.click()
    await expect(
      page.getByRole('status').filter({ hasText: '请先为任务选择通知目标' }),
    ).toBeVisible()
    await expect(toggle).toHaveAttribute('aria-checked', 'false')
    await page.reload()
    await expect(toggle).toHaveAttribute('aria-checked', 'false')
  } finally {
    for (const id of tasks)
      expect((await page.request.delete('/api/manage/tasks/' + id, { headers })).ok()).toBe(true)
    for (const id of targets)
      expect((await page.request.delete('/api/manage/targets/' + id, { headers })).ok()).toBe(true)
  }
})
test('deletion impact list scrolls, escapes task names and handles preview errors without writes', async ({
  page,
}, info) => {
  test.setTimeout(60000)
  const headers = await session(page),
    taskIds: string[] = []
  const name = '长名单 ' + info.project.name
  const created = await page.request.post('/api/manage/targets', {
    headers,
    data: {
      name,
      kind: 'webhook',
      enabled: false,
      config: { url: 'https://receiver.example.test/synthetic' },
    },
  })
  const target = (await created.json()).id
  try {
    for (let i = 0; i < 28; i++) {
      const response = await page.request.post('/api/manage/tasks', {
        headers,
        data: {
          name:
            i === 0
              ? '<img src=x onerror=window.deletedInjected=true>'
              : '合成任务-' + i + '-'.repeat(60),
          description: '',
          website_id: 'nodeseek',
          enabled: i % 2 === 0,
          rule: {},
          target_ids: [target],
        },
      })
      expect(response.ok()).toBe(true)
      taskIds.push((await response.json()).id)
    }
    const before = await (await page.request.get('/api/manage/workspace')).json()
    await page.reload()
    await page.goto('/#/notifications/targets')
    await page.route(
      '**/api/manage/targets/' + target + '/delete-preview',
      (route) =>
        route.fulfill({
          status: 503,
          contentType: 'application/json',
          body: JSON.stringify({ detail: '合成读取失败' }),
        }),
      { times: 1 },
    )
    await page.getByRole('button', { name: '删除' + name, exact: true }).click()
    const dialog = page.getByRole('dialog', { name: '删除「' + name + '」？', exact: true })
    await expect(dialog.getByRole('alert')).toContainText('合成读取失败')
    await expect(dialog.getByRole('button', { name: '删除', exact: true })).toBeDisabled()
    await dialog.getByRole('button', { name: '重新加载', exact: true }).click()
    const list = dialog.getByRole('list', { name: '删除后没有通知目标的任务' })
    await expect(list.getByRole('listitem')).toHaveCount(28)
    await expect(dialog.locator('img')).toHaveCount(0)
    expect(await list.evaluate((element) => element.scrollHeight > element.clientHeight)).toBe(true)
    for (const width of [320, 390, 768, 1440]) {
      await page.setViewportSize({ width, height: 900 })
      expect(await dialog.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(
        true,
      )
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      )
    }
    await page.setViewportSize(
      info.project.name === 'mobile' ? { width: 390, height: 844 } : { width: 1440, height: 1000 },
    )
    await page.screenshot({ path: info.outputPath('target-delete-impact.png'), fullPage: true })
    await dialog.getByRole('button', { name: '取消', exact: true }).click()
    expect((await (await page.request.get('/api/manage/workspace')).json()).tasks).toEqual(
      before.tasks,
    )
  } finally {
    for (const id of taskIds)
      expect((await page.request.delete('/api/manage/tasks/' + id, { headers })).ok()).toBe(true)
    expect((await page.request.delete('/api/manage/targets/' + target, { headers })).ok()).toBe(
      true,
    )
  }
})
