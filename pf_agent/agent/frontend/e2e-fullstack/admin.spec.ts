import {
  expect,
  test,
  type APIResponse,
  type BrowserContext,
  type Locator,
  type Page,
  type Response,
} from '@playwright/test'

const ADMIN_PASSWORD = 'pf-e2e-admin-password'
const USER_PASSWORD = 'pf-e2e-user-password'
const RESET_PASSWORD = 'pf-e2e-reset-password'

interface AdminUser {
  id: number
  username: string
  role: string
}

interface BrowserDiagnostics {
  pageErrors: string[]
  httpFailures: string[]
}

/** 页面级诊断：未捕获 JS 错误 + 非预期 404/500（只记录方法/URL/状态，不记录请求头或 token） */
function trackPage(page: Page, diagnostics: BrowserDiagnostics): void {
  page.on('pageerror', (error) => diagnostics.pageErrors.push(error.message))
  page.on('response', (response) => {
    const status = response.status()
    if (status === 404 || status === 500) {
      diagnostics.httpFailures.push(`${response.request().method()} ${response.url()} ${status}`)
    }
  })
}

/** 在创建页面之前挂 context 级监听，覆盖该 context 后续新建的所有 page */
function trackContext(context: BrowserContext, diagnostics: BrowserDiagnostics): void {
  context.on('page', (newPage) => trackPage(newPage, diagnostics))
}

async function adminLogin(page: Page, path = '/admin'): Promise<string> {
  // 无斜杠 /admin 与带斜杠 /admin/ 都必须可用：默认从无斜杠入口登录
  await page.goto(path)
  await page.locator('#gateUsername').fill('admin')
  await page.locator('#gatePassword').fill(ADMIN_PASSWORD)
  await page.locator('#gateSubmit').click()
  await expect(page.locator('#who')).toContainText('admin')
  await expect(page.locator('#console')).toBeVisible()
  // 先确认初始配置（注册开放），再进入关闭/开放切换流程，避免与配置加载竞态
  await expect(page.locator('#regState')).toHaveText('开放中')

  // token 只在此处读入，仅用于管理接口的 Authorization 头；不打印、不写日志
  const token = await page.evaluate(() => window.localStorage.getItem('pf.auth.token'))
  expect(token, '管理员登录后 localStorage 应存在 pf.auth.token').toBeTruthy()
  return token as string
}

async function adminRequest(
  page: Page,
  token: string,
  method: 'GET' | 'PUT' | 'DELETE',
  path: string,
  data?: Record<string, unknown>,
): Promise<APIResponse> {
  return page.request.fetch(`/api/admin${path}`, {
    method,
    headers: { Authorization: `Bearer ${token}` },
    ...(data === undefined ? {} : { data }),
  })
}

async function changeRole(
  page: Page,
  select: Locator,
  userId: number,
  role: 'admin' | 'user',
): Promise<Response> {
  const responsePromise = page.waitForResponse((response) => {
    if (response.request().method() !== 'PUT') return false
    if (response.status() !== 200) return false
    if (!response.url().endsWith(`/api/admin/users/${userId}/role`)) return false
    return (response.request().postDataJSON() as { role?: string } | null)?.role === role
  })
  await select.selectOption(role)
  return responsePromise
}

/** 不依赖页面 UI 的兜底清理：恢复注册开放，并删除按用户名找到的临时用户 */
async function cleanupAdminState(page: Page, token: string, username: string): Promise<void> {
  const restored = await adminRequest(page, token, 'PUT', '/settings/registration', { enabled: true })
  if (!restored.ok()) throw new Error(`恢复注册开关失败（HTTP ${restored.status()}）`)

  const listed = await adminRequest(page, token, 'GET', '/users')
  if (!listed.ok()) throw new Error(`读取用户列表失败（HTTP ${listed.status()}）`)
  const temp = ((await listed.json()) as AdminUser[]).find((user) => user.username === username)
  if (!temp) return

  const removed = await adminRequest(page, token, 'DELETE', `/users/${temp.id}`)
  if (!removed.ok()) throw new Error(`删除临时用户失败（HTTP ${removed.status()}）`)
}

async function openLoginDialog(page: Page): Promise<void> {
  await page.getByRole('button', { name: '登录 / 注册' }).click()
  await expect(page.locator('.modal')).toBeVisible()
}

test('管理员真实管理用户与注册开关', async ({ page, browser }) => {
  const diagnostics: BrowserDiagnostics = { pageErrors: [], httpFailures: [] }
  trackPage(page, diagnostics)

  const token = await adminLogin(page, '/admin')
  const username = `admin_e2e_${Date.now()}`

  try {
    // 带斜杠入口：同一浏览器上下文已带 token，应直接进入控制台
    await page.goto('/admin/')
    await expect(page.locator('#console')).toBeVisible()
    await expect(page.locator('#gate')).toBeHidden()
    await expect(page.locator('#who')).toContainText('admin')

    await page.locator('#newUsername').fill(username)
    await page.locator('#newUserPwd').fill(USER_PASSWORD)
    await page.locator('#createSubmit').click()

    const row = page.locator('#userRows tr', { hasText: username })
    await expect(row).toHaveCount(1)

    const listed = await adminRequest(page, token, 'GET', '/users')
    expect(listed.status()).toBe(200)
    const created = ((await listed.json()) as AdminUser[]).find((user) => user.username === username)
    expect(created, '新建用户应出现在用户列表').toBeTruthy()
    const userId = created!.id

    const roleSelect = row.locator('select.role-select')
    const promoted = await changeRole(page, roleSelect, userId, 'admin')
    expect(await promoted.json()).toMatchObject({ id: userId, role: 'admin' })
    await expect(roleSelect).toHaveValue('admin')

    const demoted = await changeRole(page, roleSelect, userId, 'user')
    expect(await demoted.json()).toMatchObject({ id: userId, role: 'user' })
    await expect(roleSelect).toHaveValue('user')

    await row.getByRole('button', { name: '重置密码' }).click()
    await page.locator('#resetPwd').fill(RESET_PASSWORD)
    await page.locator('#resetPwd2').fill(RESET_PASSWORD)
    await page.locator('#resetSubmit').click()
    await expect(page.locator('#resetModal')).not.toHaveClass(/open/)

    // 新密码可登录（但非管理员）：证明重置密码真实落库
    const userContext = await browser.newContext()
    trackContext(userContext, diagnostics)
    const userPage = await userContext.newPage()
    await userPage.goto('/admin/')
    await userPage.locator('#gateUsername').fill(username)
    await userPage.locator('#gatePassword').fill(RESET_PASSWORD)
    await userPage.locator('#gateSubmit').click()
    await expect(userPage.locator('#gateMsg')).toContainText('不是管理员')
    await userContext.close()

    // 关闭注册：前端隐藏入口，后端 403 拒绝注册
    await page.locator('#regToggle').uncheck()
    await expect(page.locator('#regState')).toHaveText('已关闭')

    const closedName = `admin_closed_${Date.now()}`
    const closed = await page.request.post('/api/auth/register', {
      data: { username: closedName, password: USER_PASSWORD },
    })
    expect(closed.status()).toBe(403)
    expect(await closed.json()).toMatchObject({ error: 'registration_closed' })

    const closedContext = await browser.newContext()
    trackContext(closedContext, diagnostics)
    const closedPage = await closedContext.newPage()
    await closedPage.goto('/')
    await openLoginDialog(closedPage)
    await expect(closedPage.getByRole('button', { name: '没有账号？注册' })).toHaveCount(0)
    await closedContext.close()

    // 重新开放：登录框恢复注册切换入口
    await page.locator('#regToggle').check()
    await expect(page.locator('#regState')).toHaveText('开放中')

    const openContext = await browser.newContext()
    trackContext(openContext, diagnostics)
    const openPage = await openContext.newPage()
    await openPage.goto('/')
    await openLoginDialog(openPage)
    await expect(openPage.getByRole('button', { name: '没有账号？注册' })).toHaveCount(1)
    await openContext.close()

    await row.getByRole('button', { name: '删除' }).click()
    await page.locator('#deleteSubmit').click()
    await expect(row).toHaveCount(0)

    await page.locator('#logout').click()
    await expect(page.locator('#gateMsg')).toContainText('已退出登录')

    expect(diagnostics.pageErrors, '页面不应出现未捕获 JS 错误').toEqual([])
    expect(diagnostics.httpFailures, '页面不应出现 404/500 响应').toEqual([])
  } finally {
    await cleanupAdminState(page, token, username)
  }
})
