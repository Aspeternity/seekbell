import { expect, test } from '@playwright/test'

const username = 'synthetic-browser-admin'
const password = 'synthetic browser long passphrase'
const origin = 'http://127.0.0.1:18765'

test('桌面和手机完成初始化、刷新、退出、错误密码与重新登录', async ({ browser }, testInfo) => {
  for (const width of [1280, 390]) {
    const context = await browser.newContext({ viewport: { width, height: 844 } })
    const external: string[] = []
    await context.route('**/*', async (route) => {
      if (new URL(route.request().url()).origin !== origin) {
        external.push(route.request().url())
        await route.abort()
      } else {
        await route.continue()
      }
    })
    const page = await context.newPage()
    const errors: string[] = []
    page.on('pageerror', (error) => errors.push(error.message))
    await page.goto('/')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(
      width === 1280 ? '创建你的管理员账号。' : '登录 SeekBell。',
    )
    await page.getByLabel('用户名', { exact: true }).fill(username)
    await page.getByLabel('密码', { exact: true }).fill(password)
    if (width === 1280) {
      await page.getByLabel('再次输入密码', { exact: true }).fill('a different long password')
      await page.getByRole('button', { name: '创建并登录' }).click()
      await expect(page.getByRole('alert')).toContainText('两次输入的密码不一致')
      await page.getByLabel('再次输入密码', { exact: true }).fill(password)
    }
    await page
      .getByRole('button', { name: width === 1280 ? '创建并登录' : '登录', exact: true })
      .click()
    await expect(page.getByRole('button', { name: '退出登录' })).toBeVisible()
    await page.getByRole('button', { name: '运行信息', exact: true }).click()
    await expect(page.getByText('browser-synthetic', { exact: true })).toBeVisible()
    await page.reload()
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('欢迎回来。')
    await page.getByRole('button', { name: '运行信息', exact: true }).click()
    await expect(page.locator('[aria-busy="true"]')).toHaveCount(0)
    expect(await page.evaluate(() => document.cookie)).not.toContain('seekbell_session')
    await page.screenshot({ path: testInfo.outputPath(`auth-${width}.png`), fullPage: true })
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      width,
    )
    await page.getByRole('button', { name: '退出登录' }).click()
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('登录 SeekBell。')
    await page.getByLabel('用户名', { exact: true }).fill(username)
    await page.getByLabel('密码', { exact: true }).fill('synthetic wrong long password')
    await page.getByRole('button', { name: '登录', exact: true }).click()
    await expect(page.getByRole('alert')).toContainText('用户名或密码不正确')
    await expect(page.getByLabel('密码', { exact: true })).toHaveValue('')
    await page.getByLabel('密码', { exact: true }).fill(password)
    await page.getByRole('button', { name: '登录', exact: true }).click()
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('欢迎回来。')
    await page.getByRole('button', { name: '退出登录' }).click()
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('登录 SeekBell。')
    expect(errors).toEqual([])
    expect(external).toEqual([])
    await context.close()
  }
})

test('会话失效时回到登录入口并给出提示', async ({ page, context }) => {
  await context.route('**/*', (route) =>
    new URL(route.request().url()).origin === origin ? route.continue() : route.abort(),
  )
  await page.goto('/')
  await page.getByLabel('用户名', { exact: true }).fill(username)
  await page.getByLabel('密码', { exact: true }).fill(password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await page.getByRole('button', { name: '监控任务', exact: true }).click()
  await expect(page.getByRole('button', { name: '刷新任务', exact: true })).toBeVisible()
  await expect(page.locator('[aria-busy="true"]')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '退出登录' })).toBeEnabled()
  await context.clearCookies()
  await page.getByRole('button', { name: '刷新任务', exact: true }).click()
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('登录 SeekBell。')
  await expect(page.getByRole('alert')).toContainText('会话已过期')
})

test('浏览器请求不能绕过登录的CSRF校验', async ({ request }) => {
  const state = await request.get('/api/auth/state')
  expect(state.ok()).toBeTruthy()
  const response = await request.post('/api/auth/login', { data: { username, password } })
  expect(response.status()).toBe(403)
  expect((await request.get('/api/auth/state')).ok()).toBeTruthy()
})

test('四渠道配置和任务编辑、复制、暂停、两类试匹配在浏览器中可用', async ({
  page,
  context,
}, testInfo) => {
  test.setTimeout(60000)
  const responses: string[] = []
  await context.route('**/*', (route) =>
    new URL(route.request().url()).origin === origin ? route.continue() : route.abort(),
  )
  page.on('response', (response) => {
    if (response.url().includes('/api/manage/'))
      void response
        .text()
        .then((value) => responses.push(value))
        .catch(() => {})
  })
  const pageErrors: string[] = []
  page.on('pageerror', (error) => pageErrors.push(error.message))
  await page.goto('/')
  await page.getByLabel('用户名', { exact: true }).fill(username)
  await page.getByLabel('密码', { exact: true }).fill(password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.locator('[aria-busy="true"]')).toHaveCount(0)
  await page.getByRole('button', { name: '通知管理', exact: true }).click()
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole('button', { name: '新建通知目标', exact: true }).click()
  await page.getByLabel('目标名称', { exact: true }).fill('手机 Bark')
  await page.getByLabel('设备密钥', { exact: true }).fill('synthetic-device-private')
  await page.getByRole('switch', { name: '启用目标', exact: true }).click()
  await page.getByRole('button', { name: '保存通知目标', exact: true }).click()
  await expect(page.getByRole('button', { name: '编辑 手机 Bark', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '编辑 手机 Bark', exact: true }).click()
  await expect(page.getByLabel('设备密钥', { exact: true })).toHaveValue('')
  const session = await (await context.request.get('/api/auth/state')).json()
  const targetList = await (await context.request.get('/api/manage/targets')).json()
  const competing = await context.request.put('/api/manage/targets/' + targetList[0].id, {
    headers: { 'X-CSRF-Token': session.csrf_token },
    data: { name: '另一个页面修改', config: {}, expected_revision: targetList[0].revision },
  })
  expect(competing.status()).toBe(200)
  await page.getByLabel('目标名称', { exact: true }).fill('过时草稿')
  await page.getByRole('button', { name: '保存通知目标', exact: true }).click()
  await expect(
    page.getByText('配置已被修改，请重新打开编辑后重试。', { exact: true }),
  ).toBeVisible()
  await page.getByRole('button', { name: '取消编辑', exact: true }).click()
  await page.getByRole('button', { name: '编辑 手机 Bark', exact: true }).click()
  await expect(page.getByLabel('目标名称', { exact: true })).toHaveValue('另一个页面修改')
  await page.getByLabel('目标名称', { exact: true }).fill('编辑过的 Bark')
  await page.getByRole('button', { name: '保存通知目标', exact: true }).click()
  await page.getByRole('button', { name: '停用 编辑过的 Bark', exact: true }).click()
  await page.getByRole('button', { name: '启用 编辑过的 Bark', exact: true }).click()

  for (const channel of ['webhook', 'telegram', 'smtp']) {
    await page.getByRole('button', { name: '新建通知目标', exact: true }).click()
    await page.getByLabel('目标名称', { exact: true }).fill('synthetic ' + channel)
    await page.getByLabel('渠道', { exact: true }).selectOption(channel)
    if (channel === 'webhook') {
      await page
        .getByLabel('Webhook 地址', { exact: true })
        .fill('https://receiver.example.invalid/private')
      await page.getByLabel('自定义请求头（JSON）', { exact: true }).fill('{invalid')
      await page.getByRole('button', { name: '保存通知目标', exact: true }).click()
      await expect(page.getByText('请求头必须是有效的 JSON 对象。', { exact: true })).toBeVisible()
      await page
        .getByLabel('Webhook 地址', { exact: true })
        .fill('https://receiver.example.invalid/private')
      await page
        .getByLabel('自定义请求头（JSON）', { exact: true })
        .fill('{"Authorization":"synthetic-private-header"}')
    } else if (channel === 'telegram') {
      await page.getByLabel('Bot 令牌', { exact: true }).fill('123:synthetic-private-token')
      await page.getByLabel('聊天 ID', { exact: true }).fill('-100123')
    } else {
      await page.getByLabel('邮件服务器', { exact: true }).fill('smtp.example.invalid')
      await page.getByLabel('发件地址', { exact: true }).fill('sender@example.invalid')
      await page.getByLabel('收件地址', { exact: true }).fill('recipient@example.invalid')
    }
    await page.getByRole('button', { name: '保存通知目标', exact: true }).click()
    await expect(
      page.getByRole('button', { name: '编辑 synthetic ' + channel, exact: true }),
    ).toBeVisible()
  }
  await expect(page.locator('[aria-busy="true"]')).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.screenshot({ path: testInfo.outputPath('targets-mobile.png'), fullPage: true })
  await page.getByRole('button', { name: '监控任务', exact: true }).click()
  await page.getByRole('button', { name: '新建监控任务', exact: true }).click()
  await page
    .getByLabel('任务名称', { exact: true })
    .fill('<img src=x onerror="window.injected=true">')
  await page.getByRole('checkbox', { name: '编辑过的 Bark', exact: true }).check()
  await expect(page.getByText('当前没有筛选限制，将匹配全部新帖。', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '添加条件组', exact: true }).click()
  await page.getByRole('button', { name: '添加组 1 全部包含标签', exact: true }).click()
  await page.getByLabel('条件组 1 全部包含标签', { exact: true }).fill('VPS synthetic')
  await page.getByLabel('条件组 1 全部包含标签', { exact: true }).press('Enter')
  await expect(page.getByRole('button', { name: '保存监控任务', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '添加组 1 至少包含一个标签', exact: true }).click()
  await page.getByLabel('条件组 1 至少包含一个标签', { exact: true }).fill('offer')
  await page.getByLabel('条件组 1 至少包含一个标签', { exact: true }).press('Enter')
  await page.getByRole('button', { name: '添加排除词标签', exact: true }).click()
  await page.getByLabel('排除词标签', { exact: true }).fill('已出')
  await page.getByLabel('排除词标签', { exact: true }).press('Enter')
  await page.getByLabel('匹配范围', { exact: true }).selectOption('title_summary')
  await page.getByLabel('模拟标题', { exact: true }).fill('VPS synthetic offer')
  await page.getByRole('button', { name: '模拟试匹配', exact: true }).click()
  await expect(page.getByText('信息不足', { exact: true })).toBeVisible()
  await page.getByRole('switch', { name: '摘要已知', exact: true }).click()
  await page.getByRole('button', { name: '模拟试匹配', exact: true }).click()
  await expect(page.getByText('命中', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '本地历史试匹配', exact: true }).click()
  await expect(page.getByText('本次样本 2 条 / 本地共 2 条', { exact: true })).toBeVisible()
  await expect(page.locator('[aria-busy="true"]')).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.screenshot({ path: testInfo.outputPath('task-editor-mobile.png'), fullPage: true })
  await page.getByRole('button', { name: '保存监控任务', exact: true }).click()
  await page
    .getByRole('button', { name: '编辑 <img src=x onerror="window.injected=true">', exact: true })
    .click()
  expect(await page.evaluate(() => 'injected' in window)).toBe(false)
  await expect(page.getByText('VPS synthetic', { exact: true })).toBeVisible()
  await page.getByLabel('任务名称', { exact: true }).fill('更新监控')
  await page.getByRole('button', { name: '保存监控任务', exact: true }).click()
  await page.getByRole('button', { name: '复制 更新监控', exact: true }).click()
  await expect(page.getByLabel('任务名称', { exact: true })).toHaveValue('更新监控 副本')
  await expect(page.getByRole('switch', { name: '启用任务', exact: true })).not.toBeChecked()
  await page.getByRole('button', { name: '保存监控任务', exact: true }).click()
  await page.getByRole('button', { name: '暂停 更新监控', exact: true }).click()
  await page.getByRole('button', { name: '恢复 更新监控', exact: true }).click()
  page.once('dialog', (dialog) => void dialog.accept())
  await page.getByRole('button', { name: '删除 更新监控 副本', exact: true }).click()
  await expect(page.getByRole('button', { name: '编辑 更新监控 副本', exact: true })).toHaveCount(0)
  expect(await page.evaluate(() => 'injected' in window)).toBe(false)
  expect(responses.join('')).not.toContain('synthetic-device-private')
  expect(responses.join('')).not.toContain('synthetic-private-header')
  expect(responses.join('')).not.toContain('synthetic-private-token')
  expect(pageErrors).toEqual([])
})

test('网站连接、后台启停、概览和本地内容命中在手机中可用', async ({ page, context }, testInfo) => {
  test.setTimeout(60000)
  const external: string[] = []
  const errors: string[] = []
  await context.route('**/*', (route) => {
    if (new URL(route.request().url()).origin !== origin) {
      external.push(route.request().url())
      return route.abort()
    }
    return route.continue()
  })
  page.on('pageerror', (error) => errors.push(error.message))
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  await page.getByLabel('用户名', { exact: true }).fill(username)
  await page.getByLabel('密码', { exact: true }).fill(password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByText('后台调度运行中', { exact: true })).toBeVisible()
  await expect(page.getByText('来源已暂停', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '监控网站', exact: true }).click()
  await expect(page.getByText('尚未建立基线', { exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: '测试 RSS 连接', exact: true }).click()
  await expect(page.getByText('连接测试成功：返回 2 条', { exact: false })).toBeVisible()
  const before = await (await context.request.get('/api/manage/overview')).json()
  expect(before.counts.posts).toBe(2)
  expect(before.site.needs_baseline).toBe(true)
  await page.getByLabel('采集间隔（秒）', { exact: true }).fill('1')
  await page.getByRole('switch', { name: '启用网站采集', exact: true }).click()
  await page.getByRole('button', { name: '保存网站设置', exact: true }).click()
  await expect(page.getByText('网站设置已保存。', { exact: false })).toBeVisible()
  await expect
    .poll(
      async () => {
        const info = await (await context.request.get('/api/manage/overview')).json()
        return [info.counts.posts, info.counts.hits, info.counts.deliveries.sent]
      },
      { timeout: 15000 },
    )
    .toEqual([3, 1, 1])
  await page.getByRole('button', { name: '重新读取设置', exact: true }).click()
  await expect(page.getByText('基线已建立', { exact: true })).toBeVisible()
  await expect(page.getByText('最近 RSS 窗口：3 条 · 连续失败 0 次', { exact: true })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('site-mobile.png'), fullPage: true })
  await page.getByRole('switch', { name: '启用网站采集', exact: true }).click()
  await page.getByRole('button', { name: '保存网站设置', exact: true }).click()
  await expect(page.getByText('来源已暂停', { exact: true })).toBeVisible()
  await expect(page.getByText('恢复时需要重建基线', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '内容与命中', exact: true }).click()
  await expect(page.getByText('符合筛选 3 条 · 当前显示 3 条', { exact: true })).toBeVisible()
  await page.getByRole('switch', { name: '仅显示有命中的帖子', exact: true }).click()
  await page.getByLabel('命中任务', { exact: true }).selectOption({ label: '更新监控' })
  await page.getByRole('button', { name: '筛选内容', exact: true }).click()
  await expect(page.getByText('符合筛选 1 条 · 当前显示 1 条', { exact: true })).toBeVisible()
  await expect(
    page.getByRole('link', { name: 'VPS synthetic offer 9003', exact: true }),
  ).toHaveAttribute('href', 'https://www.nodeseek.com/post-9003-1')
  await expect(page.getByText('更新监控 · 规则版本 2', { exact: true })).toBeVisible()
  await expect(page.getByText('Synthetic known summary', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.screenshot({ path: testInfo.outputPath('content-mobile.png'), fullPage: true })
  await page.getByLabel('作者精确匹配', { exact: true }).fill('missing-author')
  await page.getByRole('button', { name: '筛选内容', exact: true }).click()
  await expect(page.getByText('没有符合筛选的本地帖子。', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '概览', exact: true }).click()
  await expect(page.getByText('最近窗口：3 条 · 连续失败 0 次', { exact: true })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('overview-mobile.png'), fullPage: true })
  expect(errors).toEqual([])
  expect(external).toEqual([])
})

test('通知管理确认测试发送、查询尝试和独立手动重发', async ({ page, context }, testInfo) => {
  test.setTimeout(60000)
  const external: string[] = []
  const errors: string[] = []
  const responses: string[] = []
  await context.route('**/*', (route) => {
    if (new URL(route.request().url()).origin !== origin) {
      external.push(route.request().url())
      return route.abort()
    }
    return route.continue()
  })
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('response', (response) => {
    if (response.url().includes('/api/manage/'))
      void response
        .text()
        .then((value) => responses.push(value))
        .catch(() => {})
  })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  await page.getByLabel('用户名', { exact: true }).fill(username)
  await page.getByLabel('密码', { exact: true }).fill(password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await page.getByRole('button', { name: '通知管理', exact: true }).click()
  await page.getByRole('button', { name: '测试通知 编辑过的 Bark', exact: true }).click()
  await expect(page.getByText('确认发送测试通知', { exact: true })).toBeVisible()
  expect((await (await context.request.get('/api/manage/deliveries?kind=test')).json()).total).toBe(
    0,
  )
  await page.getByRole('button', { name: '取消发送', exact: true }).click()
  await page.getByRole('button', { name: '测试通知 编辑过的 Bark', exact: true }).click()
  const bodyPromise = page.waitForRequest(
    (request) => request.url().endsWith('/test') && request.method() === 'POST',
  )
  await page.getByRole('button', { name: '确认发送测试', exact: true }).click()
  const posted = await bodyPromise
  await expect(
    page.getByText('渠道接受（bark_accepted）。成功仅代表渠道接受，不代表已阅读。', {
      exact: true,
    }),
  ).toBeVisible()
  const session = await (await context.request.get('/api/auth/state')).json()
  const repeated = await context.request.post(posted.url(), {
    headers: { 'X-CSRF-Token': session.csrf_token },
    data: posted.postDataJSON(),
  })
  expect(repeated.status()).toBe(200)
  await page.getByRole('tab', { name: '投递记录', exact: true }).click()
  await expect(page.getByText('符合筛选 1 条', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '查看详情', exact: true }).click()
  await expect(page.getByText('尝试 1：渠道接受', { exact: false })).toBeVisible()
  const before = await (await context.request.get('/api/manage/deliveries')).json()
  expect(before.items[0].status).toBe('sent')
  await page.getByRole('button', { name: '手动重发 编辑过的 Bark', exact: true }).click()
  await expect(page.getByText('确认手动重发', { exact: true })).toBeVisible()
  expect(
    (await (await context.request.get('/api/manage/deliveries?kind=manual')).json()).total,
  ).toBe(0)
  await page.getByRole('button', { name: '确认重发一次', exact: true }).click()
  await expect(page.getByLabel('记录类别', { exact: true })).toHaveValue('manual')
  await expect(
    page.getByText('【手动重发】VPS synthetic offer 9003', { exact: true }),
  ).toBeVisible()
  const after = await (await context.request.get('/api/manage/deliveries')).json()
  expect(after.items).toEqual(before.items)
  await page.getByRole('button', { name: '查看详情', exact: true }).click()
  await expect(page.getByRole('button', { name: '查看原自动记录', exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.screenshot({ path: testInfo.outputPath('manual-delivery-mobile.png'), fullPage: true })
  await page.getByRole('button', { name: '查看原自动记录', exact: true }).click()
  await expect(page.getByText('尝试 1：渠道接受', { exact: false })).toBeVisible()
  await page.getByLabel('记录类别', { exact: true }).selectOption('test')
  await expect(page.getByText('符合筛选 1 条', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '查看详情', exact: true }).click()
  await expect(page.getByText('SeekBell 通知测试', { exact: true })).toHaveCount(2)
  await page.screenshot({ path: testInfo.outputPath('target-test-mobile.png'), fullPage: true })
  expect(responses.join('')).not.toContain('synthetic-device-private')
  expect(responses.join('')).not.toContain('config_ciphertext')
  expect(errors).toEqual([])
  expect(external).toEqual([])
})
