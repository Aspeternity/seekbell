import { expect, test } from '@playwright/test'
import { readFile } from 'node:fs/promises'
const credentials = { username: 'backup_browser_admin', password: 'Synthetic-Backup-Admin-2026' }
const password = 'Synthetic-Browser-Backup-2026'
test('encrypted download, errors and independent restore preserve the active workspace', async ({
  page,
}, info) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.route('**/*', (route) => {
    if (new URL(route.request().url()).hostname !== '127.0.0.1')
      throw new Error('Unexpected external request')
    return route.continue()
  })
  await page.goto('/')
  await page.getByLabel('管理员用户名').fill(credentials.username)
  await page.getByLabel('设置密码', { exact: true }).fill(credentials.password)
  await page.getByLabel('确认密码', { exact: true }).fill(credentials.password)
  await page.getByRole('button', { name: '创建管理员并进入' }).click()
  await expect(page.locator('.sidebar')).toBeAttached()
  const before = await (await page.request.get('/api/manage/workspace')).json()
  await page.goto('/#/settings/preferences')
  await page.goto('/#/settings/backup')
  await expect(page.getByRole('button', { name: '生成并下载加密备份' })).toBeEnabled()
  await page.getByLabel('当前管理员密码', { exact: true }).fill(credentials.password)
  await page.getByLabel('备份加密口令', { exact: true }).fill(password)
  await page.getByLabel('确认下载口令', { exact: true }).fill('Mismatched-Synthetic-Password')
  await page.getByRole('button', { name: '生成并下载加密备份' }).click()
  await expect(page.getByRole('alert')).toContainText('两次备份口令不一致')
  await page.evaluate(() => (location.hash = '/settings/account'))
  await expect(page.getByRole('dialog')).toContainText('尚未保存')
  await page.getByRole('button', { name: '继续编辑', exact: true }).click()
  await page.getByLabel('确认下载口令', { exact: true }).fill(password)
  const downloading = page.waitForEvent('download')
  await page.getByRole('button', { name: '生成并下载加密备份' }).click()
  const downloaded = await downloading
  const path = info.outputPath(downloaded.suggestedFilename())
  await downloaded.saveAs(path)
  const encrypted = await readFile(path)
  expect(encrypted.subarray(0, 16).toString()).toBe('SEEKBELL-BACKUP' + String.fromCharCode(1))
  expect(encrypted.includes(Buffer.from('SQLite format'))).toBe(false)
  expect(encrypted.includes(Buffer.from(credentials.password))).toBe(false)
  await expect(page.getByLabel('当前管理员密码', { exact: true })).toHaveValue('')
  await expect(page.getByLabel('备份加密口令', { exact: true })).toHaveValue('')
  await page.getByRole('button', { name: '恢复验证', exact: true }).click()
  await page.getByLabel('加密备份文件', { exact: true }).setInputFiles(path)
  await page.getByLabel('当前管理员密码（恢复验证）', { exact: true }).fill(credentials.password)
  await page.getByLabel('所选备份的加密口令', { exact: true }).fill('Incorrect-Synthetic-Password')
  await page.getByLabel('备份中的管理员用户名', { exact: true }).fill(credentials.username)
  await page.getByLabel('备份中的管理员密码', { exact: true }).fill(credentials.password)
  await page.getByRole('checkbox').check()
  await page.getByRole('button', { name: '验证并生成独立恢复副本' }).click()
  await expect(page.getByRole('alert')).toContainText('备份口令错误或文件损坏')
  expect((await (await page.request.get('/api/manage/backups')).json()).candidate_available).toBe(
    false,
  )
  await page.getByLabel('当前管理员密码（恢复验证）', { exact: true }).fill(credentials.password)
  await page.getByLabel('所选备份的加密口令', { exact: true }).fill(password)
  await page.getByLabel('备份中的管理员密码', { exact: true }).fill(credentials.password)
  await page.getByRole('button', { name: '验证并生成独立恢复副本' }).click()
  await expect(page.getByRole('status').filter({ hasText: '独立恢复副本已生成' })).toBeVisible()
  await expect(page.getByRole('status').filter({ hasText: '已有独立恢复副本' })).toBeVisible()
  expect(await (await page.request.get('/api/manage/workspace')).json()).toEqual(before)
  expect((await (await page.request.get('/api/auth/status')).json()).authenticated).toBe(true)
  await page.screenshot({ path: info.outputPath('backup-restored.png'), fullPage: true })
  await page.reload()
  await expect(page.getByRole('status').filter({ hasText: '已有独立恢复副本' })).toBeVisible()
  await expect(page.getByRole('button', { name: '验证并生成独立恢复副本' })).toHaveCount(0)
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
  expect(
    await page.evaluate(() =>
      Object.values(localStorage).some((value) => value.includes('Synthetic-')),
    ),
  ).toBe(false)
  expect(errors).toEqual([])
})
