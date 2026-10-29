import { expect, test } from '@playwright/test'
import { readFile } from 'node:fs/promises'
const credentials = { username: 'backup_browser_admin', password: 'Synthetic-Backup-Admin-2026' }
const password = 'Synthetic-Browser-Backup-2026'
test('encrypted download and in-place restore from settings and the first-run page', async ({
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
  const exportForm = page.getByRole('form', { name: '导出备份', exact: true })
  await expect(page.getByRole('button', { name: '生成并下载加密备份' })).toBeEnabled()
  // The password was just entered at sign-in, so it is not asked again yet.
  await expect(exportForm.getByLabel('当前管理员密码', { exact: true })).toHaveCount(0)
  await exportForm.getByLabel('备份口令', { exact: true }).fill(password)
  await exportForm.getByLabel('确认备份口令', { exact: true }).fill('Mismatched-Synthetic-Password')
  await page.getByRole('button', { name: '生成并下载加密备份' }).click()
  await expect(page.getByRole('alert')).toContainText('两次备份口令不一致')
  await page.evaluate(() => (location.hash = '/settings/account'))
  await expect(page.getByRole('dialog')).toContainText('尚未保存')
  await page.getByRole('button', { name: '继续编辑', exact: true }).click()
  await exportForm.getByLabel('确认备份口令', { exact: true }).fill(password)
  const downloading = page.waitForEvent('download')
  await page.getByRole('button', { name: '生成并下载加密备份' }).click()
  const downloaded = await downloading
  const path = info.outputPath(downloaded.suggestedFilename())
  await downloaded.saveAs(path)
  const encrypted = await readFile(path)
  expect(encrypted.subarray(0, 16).toString()).toBe('SEEKBELL-BACKUP' + String.fromCharCode(1))
  expect(encrypted.includes(Buffer.from('SQLite format'))).toBe(false)
  expect(encrypted.includes(Buffer.from(credentials.password))).toBe(false)
  await expect(exportForm.getByLabel('备份口令', { exact: true })).toHaveValue('')
  // Change the live workspace after the backup, then restore it in place.
  const csrf = (await (await page.request.get('/api/auth/status')).json()).csrf
  await page.request.put('/api/manage/workspace', {
    headers: { 'X-CSRF-Token': csrf },
    data: { name: '恢复前修改', description: '' },
  })
  await page.reload()
  await expect(page.locator('.workspace-label')).toContainText('恢复前修改')
  await page.getByRole('button', { name: '恢复备份', exact: true }).click()
  const form = page.getByRole('form', { name: '从文件恢复', exact: true })
  await form.getByLabel('加密备份文件', { exact: true }).setInputFiles(path)
  await form.getByLabel('备份口令', { exact: true }).fill('Incorrect-Synthetic-Password')
  await expect(form.getByLabel('当前管理员密码', { exact: true })).toHaveCount(0)
  await expect(form.getByLabel('管理员用户名', { exact: true })).toHaveCount(0)
  await expect(form.getByRole('checkbox', { name: '恢复后暂停采集和通知' })).toBeChecked()
  await form.getByRole('button', { name: '恢复备份', exact: true }).click()
  await page.getByRole('button', { name: '确认恢复', exact: true }).click()
  await expect(form.getByRole('alert')).toContainText('备份口令错误或文件损坏')
  await expect(page.locator('.workspace-label')).toContainText('恢复前修改')
  await page.screenshot({ path: info.outputPath('backup-restore-form.png'), fullPage: true })
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
  await page.setViewportSize({ width: 1440, height: 900 })
  await form.getByLabel('备份口令', { exact: true }).fill(password)
  await form.getByRole('button', { name: '恢复备份', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('管理员账号保持不变')
  await page.getByRole('button', { name: '确认恢复', exact: true }).click()
  // The current administrator stays signed in on the restored workspace.
  await expect(page.getByText('备份已恢复，采集和通知已暂停')).toBeVisible()
  await expect(page.locator('.workspace-label')).toContainText('个人工作空间')
  await expect(page.locator('.sidebar')).toBeAttached()
  await page.goto('/#/settings/backup')
  await expect(page.locator('.backup-records li').first()).toContainText('已恢复')

  // A fresh installation restores the same file from its first-run page.
  const fresh = 'http://127.0.0.1:' + (info.project.name === 'desktop' ? 8020 : 8021)
  const other = await page.context().browser()!.newPage()
  await other.goto(fresh + '/')
  await other.getByRole('button', { name: '已有备份？从备份恢复' }).click()
  await expect(other.getByRole('heading', { name: '从备份恢复' })).toBeVisible()
  const setup = other.getByRole('form', { name: '从文件恢复', exact: true })
  await expect(setup.getByLabel('当前管理员密码', { exact: true })).toHaveCount(0)
  await setup.getByLabel('加密备份文件', { exact: true }).setInputFiles(path)
  await setup.getByLabel('备份口令', { exact: true }).fill(password)
  // A fresh installation chooses its administrator; the backup's own is not needed.
  await setup.getByLabel('管理员用户名', { exact: true }).fill('fresh_browser_admin')
  await setup.getByLabel('设置密码', { exact: true }).fill(credentials.password)
  await setup.getByLabel('确认密码', { exact: true }).fill('Mismatched-Synthetic-Password')
  await setup.getByRole('button', { name: '恢复备份', exact: true }).click()
  await expect(setup.getByRole('alert')).toContainText('两次输入的密码不一致')
  await setup.getByLabel('确认密码', { exact: true }).fill(credentials.password)
  await setup.getByRole('checkbox', { name: '恢复后暂停采集和通知' }).uncheck()
  await setup.getByRole('button', { name: '恢复备份', exact: true }).click()
  await expect(other.locator('.workspace-label')).toContainText('个人工作空间')
  expect((await (await other.request.get(fresh + '/api/auth/status')).json()).username).toBe(
    'fresh_browser_admin',
  )
  await other.close()
  expect(
    await page.evaluate(() =>
      Object.values(localStorage).some((value) => value.includes('Synthetic-')),
    ),
  ).toBe(false)
  expect(errors).toEqual([])
})
