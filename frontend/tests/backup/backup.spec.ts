import { expect, test } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { gunzipSync } from 'node:zlib'
const credentials = { username: 'backup_browser_admin', password: 'Synthetic-Backup-Admin-2026' }
/** Member names of an uncompressed USTAR stream: each header names the file at offset 0. */
function tarNames(data: Buffer) {
  const names: string[] = []
  let offset = 0
  while (offset + 512 <= data.length && data[offset] !== 0) {
    names.push(
      data
        .subarray(offset, offset + 100)
        .toString()
        .split(String.fromCharCode(0))[0]!,
    )
    const size = parseInt(data.subarray(offset + 124, offset + 136).toString(), 8)
    offset += 512 + Math.ceil(size / 512) * 512
  }
  return names
}
test('back up on the server, download, import, restore and undo from settings and first run', async ({
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
  await page.goto('/#/settings/backup')
  await expect(page.locator('.backup-health')).toContainText('还没有备份')
  await expect(page.locator('.backup-directory')).toContainText('/backups')

  // The status card only reports; actions sit on the list, which comes last.
  await expect(page.locator('#backup-settings').getByRole('button')).toHaveCount(1)
  expect(
    await page.evaluate(() =>
      [...document.querySelectorAll('.settings-stack > section')].map((section) => section.id),
    ),
  ).toEqual(['backup-settings', 'backup-schedule', 'backup-list'])

  // Automatic backups are on by default: daily at 03:00 in the display timezone, keep 7.
  // Only the next run is shown, once, in the automatic backup card heading; no hint text.
  await expect(page.locator('.backup-next')).toHaveCount(1)
  await expect(page.locator('#backup-schedule .settings-details')).toHaveCount(0)
  await expect(page.locator('#backup-schedule .backup-next')).toHaveText(/^下次 .*03:00$/)
  const automatic = page.locator('#backup-schedule')
  await expect(automatic.getByRole('switch', { name: '启用自动备份' })).toHaveAttribute(
    'aria-checked',
    'true',
  )
  await expect(automatic.getByLabel('小时')).toHaveText('03')
  await expect(automatic.getByLabel('分钟')).toHaveText('00')
  // Time is picked from styled hour and minute lists, not the browser's native picker.
  await expect(automatic.locator('input[type="time"]')).toHaveCount(0)
  await expect(automatic.getByLabel('自动备份保留份数')).toHaveValue('7')
  // How often is one list, so switching daily/weekly never shifts the fields beside it.
  const timeLeft = (await automatic.getByLabel('小时').boundingBox())!.x
  await automatic.getByLabel('频率').click()
  await page.getByRole('option', { name: '每周日', exact: true }).click()
  expect((await automatic.getByLabel('小时').boundingBox())!.x).toBe(timeLeft)
  await automatic.getByLabel('小时').click()
  await page.getByRole('option', { name: '04', exact: true }).click()
  await automatic.getByLabel('分钟').click()
  await page.getByRole('option', { name: '30', exact: true }).click()
  await automatic.getByLabel('自动备份保留份数').fill('3')
  // An unsaved schedule is a draft: leaving asks first.
  await page.evaluate(() => (location.hash = '/settings/account'))
  await expect(page.getByRole('dialog').filter({ hasText: '尚未保存' })).toBeVisible()
  await page.getByRole('button', { name: '继续编辑', exact: true }).click()
  await automatic.getByRole('button', { name: '保存自动备份', exact: true }).click()
  await expect(automatic.getByRole('status')).toContainText('自动备份设置已保存')
  await expect(page.locator('.backup-next')).toHaveText(/^下次 .*04:30$/)
  const saved = (await (await page.request.get('/api/manage/backups/schedule')).json()) as {
    frequency: string
    weekday: number
    minute: number
    keep: number
  }
  expect([saved.frequency, saved.weekday, saved.minute, saved.keep]).toEqual(['weekly', 6, 270, 3])
  await automatic.getByRole('switch', { name: '启用自动备份' }).click()
  await automatic.getByRole('button', { name: '保存自动备份', exact: true }).click()
  await expect(page.locator('.backup-next')).toHaveText('已关闭')
  await automatic.getByRole('switch', { name: '启用自动备份' }).click()
  await automatic.getByRole('button', { name: '保存自动备份', exact: true }).click()
  await expect(page.locator('.backup-next')).toHaveText(/^下次 .*04:30$/)

  // Back up now: the archive stays on the server and appears in the list.
  // Back up now asks for an optional name first.
  await page
    .locator('.backup-heading-actions')
    .getByRole('button', { name: '立即备份', exact: true })
    .click()
  const naming = page.getByRole('dialog', { name: '立即备份', exact: true })
  // Clicking its padding keeps it open; clicking outside closes it without backing up.
  const namingBox = (await naming.boundingBox())!
  await page.mouse.click(namingBox.x + 6, namingBox.y + 6)
  await expect(naming).toBeVisible()
  await page.mouse.click(5, 5)
  await expect(naming).toHaveCount(0)
  expect((await (await page.request.get('/api/manage/backups')).json()).backups).toEqual([])
  await page
    .locator('.backup-heading-actions')
    .getByRole('button', { name: '立即备份', exact: true })
    .click()
  await naming.getByLabel('名称（选填）').fill('调整规则前')
  await naming.getByRole('button', { name: '备份', exact: true }).click()
  await expect(
    page.getByRole('status').filter({ hasText: '备份已生成并保存在服务器' }),
  ).toBeVisible()
  await expect(naming).toHaveCount(0)
  await expect(page.locator('.backup-health')).toContainText('分钟前')
  const rows = page.locator('.backup-list > li')
  await expect(rows).toHaveCount(1)
  await expect(rows.first()).toContainText('调整规则前')
  await expect(rows.first()).toContainText('手动')
  const name = (await (await page.request.get('/api/manage/backups')).json()).backups[0].id
  // Renaming later; an empty name falls back to the backup time.
  await rows
    .first()
    .getByRole('button', { name: '重命名 ' + name })
    .click()
  const renaming = page.getByRole('dialog', { name: '重命名备份', exact: true })
  await expect(renaming.getByLabel('名称（选填）')).toHaveValue('调整规则前')
  await renaming.getByLabel('名称（选填）').fill('升级前留底')
  await renaming.getByRole('button', { name: '保存', exact: true }).click()
  await expect(rows.first().locator('strong')).toHaveText('升级前留底')

  // Downloading never asks for the password; it starts at once.
  const downloading = page.waitForEvent('download')
  await rows
    .first()
    .getByRole('button', { name: '下载 ' + name })
    .click()
  const downloaded = await downloading
  expect(downloaded.suggestedFilename()).toBe(name)
  const path = info.outputPath(name)
  await downloaded.saveAs(path)
  const archive = await readFile(path)
  expect(tarNames(gunzipSync(archive))).toEqual([
    'manifest.json',
    'seekbell.sqlite3',
    'credentials.key',
  ])
  expect(gunzipSync(archive).includes(Buffer.from(credentials.username))).toBe(false)

  // Change the live workspace after the backup, then restore the uploaded file.
  const csrf = (await (await page.request.get('/api/auth/status')).json()).csrf
  const general = await (await page.request.get('/api/manage/preferences')).json()
  await page.request.put('/api/manage/preferences', {
    headers: { 'X-CSRF-Token': csrf },
    data: {
      name: '恢复前修改',
      description: '',
      timezone: general.timezone,
      workspace_revision: general.workspace_revision,
      display_revision: general.display_revision,
    },
  })
  await page.reload()
  await expect(page.locator('.workspace-label')).toContainText('恢复前修改')
  // Import keeps a checked file in the list; a damaged file is refused and nothing is added.
  const importing = page.locator('.backup-heading-actions').getByRole('button', { name: '导入' })
  async function importFile(file: string | { name: string; mimeType: string; buffer: Buffer }) {
    const choosing = page.waitForEvent('filechooser')
    await importing.click()
    await (await choosing).setFiles(file)
  }
  await importFile({
    name: 'broken.tar.gz',
    mimeType: 'application/gzip',
    buffer: Buffer.from('not a backup'),
  })
  await expect(
    page.getByRole('status').filter({ hasText: '不是有效的 SeekBell 备份文件' }),
  ).toBeVisible()
  await expect(rows).toHaveCount(1)
  // The same bytes as a backup already in the list are not stored twice.
  await importFile(path)
  await expect(page.getByRole('status').filter({ hasText: '这份备份已在列表中' })).toBeVisible()
  await expect(rows).toHaveCount(1)
  // A file from elsewhere: the original is gone from this server, so it is added.
  await page.request.delete('/api/manage/backups/' + name, { headers: { 'X-CSRF-Token': csrf } })
  await page.reload()
  await expect(rows).toHaveCount(0)
  await importFile(path)
  await expect(page.getByRole('status').filter({ hasText: '备份已导入' })).toBeVisible()
  await expect(rows).toHaveCount(1)
  await expect(rows.first().locator('.small-badge')).toHaveText('导入')
  // An imported file is not a backup of this workspace.
  await expect(page.locator('.backup-health')).toContainText('还没有备份')
  const imported = (await (await page.request.get('/api/manage/backups')).json()).backups[0].id
  expect(imported).toMatch(/-imported\.tar\.gz$/)
  await rows
    .first()
    .getByRole('button', { name: '重命名 ' + imported })
    .click()
  await renaming.getByLabel('名称（选填）').fill('迁移来的备份')
  await renaming.getByRole('button', { name: '保存', exact: true }).click()
  await expect(rows.first().locator('strong')).toHaveText('迁移来的备份')

  // Every restore starts from a row: the wizard opens on the check step.
  await rows
    .first()
    .getByRole('button', { name: '恢复 ' + imported })
    .click()
  const drawer = page.getByRole('dialog', { name: '恢复备份' })
  // The wizard is a centered dialog, not a side drawer.
  const box = (await drawer.boundingBox())!
  const width = page.viewportSize()!.width
  expect(Math.abs(box.x + box.width / 2 - width / 2)).toBeLessThan(2)
  await expect(drawer.locator('[aria-current="step"]')).toContainText('检查内容')
  await expect(drawer.getByLabel('备份文件', { exact: true })).toHaveCount(0)
  const review = drawer.getByRole('region', { name: '检查备份内容' })
  await expect(review).toContainText('个人工作空间')
  await expect(review.getByRole('table')).toContainText('当前')
  await page.screenshot({ path: info.outputPath('backup-inspect.png') })
  await drawer.getByRole('button', { name: '下一步', exact: true }).click()
  const confirm = drawer.getByRole('form', { name: '确认恢复', exact: true })
  await expect(confirm).toContainText('恢复前会先自动备份当前数据')
  await expect(confirm.getByLabel('当前管理员密码', { exact: true })).toHaveCount(0)
  await expect(confirm.getByRole('checkbox', { name: '恢复后暂停采集和通知' })).toBeChecked()
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
  await page.setViewportSize({ width: 1440, height: 900 })
  await confirm.getByRole('button', { name: '恢复备份', exact: true }).click()
  // The current administrator stays signed in on the restored workspace.
  await expect(page.getByText('备份已恢复，采集和通知已暂停')).toBeVisible()
  await expect(page.locator('.workspace-label')).toContainText('个人工作空间')
  await expect(page.locator('.sidebar')).toBeAttached()

  // The replaced data became a pre-restore backup: restoring it undoes the restore.
  await page.goto('/#/settings/backup')
  await expect(rows).toHaveCount(2)
  await expect(rows.first()).toContainText('恢复前')
  // Names live beside the archives, so a restore keeps them.
  await expect(rows.last()).toContainText('迁移来的备份')
  const previous = (await (await page.request.get('/api/manage/backups')).json()).backups[0].id
  await rows
    .first()
    .getByRole('button', { name: '恢复 ' + previous })
    .click()
  await expect(drawer.getByRole('region', { name: '检查备份内容' })).toContainText('恢复前修改')
  await drawer.getByRole('button', { name: '下一步', exact: true }).click()
  await confirm.getByRole('checkbox', { name: '恢复后暂停采集和通知' }).uncheck()
  await confirm.getByRole('button', { name: '恢复备份', exact: true }).click()
  await expect(page.getByText('备份已恢复。')).toBeVisible()
  await expect(page.locator('.workspace-label')).toContainText('恢复前修改')

  // Deleting asks in a centered dialog without a password; the data page counts what is kept.
  await page.goto('/#/settings/backup')
  await expect(rows).toHaveCount(3)
  const oldest = rows.last()
  await oldest.getByRole('button', { name: /^删除 / }).click()
  const removal = page.getByRole('dialog', { name: '删除备份？', exact: true })
  await expect(removal).toContainText('删除后无法恢复。')
  await expect(removal.getByRole('textbox')).toHaveCount(0)
  await removal.getByRole('button', { name: '取消', exact: true }).click()
  await expect(rows).toHaveCount(3)
  await oldest.getByRole('button', { name: /^删除 / }).click()
  await removal.getByRole('button', { name: '删除', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: '备份已删除' })).toBeVisible()
  await expect(rows).toHaveCount(2)
  await page.goto('/#/settings/data')
  await expect(page.locator('.settings-metrics')).toContainText('2 份')
  await page.getByRole('link', { name: '到备份页管理', exact: true }).click()
  await expect(page).toHaveURL(/\/settings\/backup\?section=list$/)
  await expect(page.getByRole('heading', { name: '备份列表', exact: true })).toBeInViewport()

  // A fresh installation restores the same file from its first-run page.
  const fresh = 'http://127.0.0.1:' + (info.project.name === 'desktop' ? 8020 : 8021)
  const other = await page.context().browser()!.newPage()
  await other.goto(fresh + '/')
  await other.getByRole('button', { name: '已有备份？从备份恢复' }).click()
  await expect(other.getByRole('heading', { name: '从备份恢复' })).toBeVisible()
  const setupChoose = other.getByRole('form', { name: '选择备份文件', exact: true })
  await setupChoose.getByLabel('备份文件', { exact: true }).setInputFiles(path)
  await setupChoose.getByRole('button', { name: '检查备份', exact: true }).click()
  const setupReview = other.getByRole('region', { name: '检查备份内容' })
  await expect(setupReview).toContainText('备份中的内容')
  await expect(setupReview.getByRole('table')).not.toContainText('当前')
  await other.getByRole('button', { name: '下一步', exact: true }).click()
  const setup = other.getByRole('form', { name: '确认恢复', exact: true })
  await expect(setup.getByLabel('当前管理员密码', { exact: true })).toHaveCount(0)
  // A fresh installation chooses its administrator; the backup carries none.
  await setup.getByLabel('管理员用户名', { exact: true }).fill('fresh_browser_admin')
  await setup.getByLabel('设置密码', { exact: true }).fill(credentials.password)
  await setup.getByLabel('确认密码', { exact: true }).fill('Mismatched-Synthetic-Password')
  await setup.getByRole('button', { name: '恢复备份', exact: true }).click()
  await expect(other.getByRole('alert')).toContainText('两次输入的密码不一致')
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
