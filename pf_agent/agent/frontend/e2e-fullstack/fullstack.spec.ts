import { expect, test, type Page } from '@playwright/test'
import { ask, expectAnswer, openHistory } from '../e2e/support/actions'

async function register(page: Page, username: string): Promise<void> {
  await page.getByRole('button', { name: '登录 / 注册' }).click()
  await page.getByRole('button', { name: '没有账号？注册' }).click()
  await page.locator('.modal input[autocomplete="username"]').fill(username)
  const passwords = page.locator('.modal input[type="password"]')
  await passwords.nth(0).fill('password123')
  await passwords.nth(1).fill('password123')
  await page.locator('.modal').getByRole('button', { name: '注册并登录' }).click()
  await expect(page.locator('.account-btn')).toContainText(username)
  // onLoggedIn 会重置并重新打开会话；等待恢复结束（Composer 在 restoring 时禁用）
  await expect(page.locator('.composer-input')).toBeEnabled()
}

async function submitLogin(page: Page, username: string): Promise<void> {
  await page.locator('.modal input[autocomplete="username"]').fill(username)
  await page.locator('.modal input[type="password"]').first().fill('password123')
  await page.locator('.modal').getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.locator('.account-btn')).toContainText(username)
  await expect(page.locator('.composer-input')).toBeEnabled()
}

test.describe('全栈（真实 Spring + PostgreSQL + 打桩 ChatModel）', () => {
  test('首页由 Spring 提供；匿名提问得到真实引用快照，登录后认领', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('.welcome h2')).toHaveText('有什么规则问题？')

    await ask(page, '法师 1 环法术有哪些')
    await expectAnswer(page)

    // 打桩模型调用 getSpellList → 真实后端收集清单页来源 → cited-only [#1] 快照
    await expect(page.locator('sup.cite')).toHaveCount(1)
    await expect(page.locator('.source-card')).toHaveCount(1)
    const source = page.locator('.source-card').first()
    await expect(source).toContainText('法师法术列表')
    await expect(source).toContainText('职业 → 核心职业 → 法师 → 法术列表')
    await expect(source.locator('.source-content')).toContainText('法师法术列表；本职业收录 0~9 环法术共 2 条')
    await expect(page.locator('.turn-assistant')).toContainText('燃烧之手')

    const username = `claim_${Date.now()}`
    await register(page, username)
    await expect(page.locator('.notice')).toContainText('认领')

    await openHistory(page)
    await expect(page.locator('.history-item')).toHaveCount(1)
    await page.locator('.history-item .history-main').click()
    await expect(page.locator('.turn-assistant')).toHaveCount(1)
    await expect(page.locator('.source-card')).toHaveCount(1)
  })

  test('匿名请求携带非法 token 收到 401：清 token、保留问题，取消后可按匿名重试', async ({ page }) => {
    await page.goto('/')
    await page.evaluate(() => window.localStorage.setItem('pf.auth.token', 'invalid-token'))

    await ask(page, '法师 1 环法术有哪些')
    await expect(page.locator('.turn-error')).toContainText('登录状态已失效')
    await expect(page.locator('.modal')).toBeVisible()
    await expect(page.locator('.user-bubble')).toHaveCount(1)
    await expect
      .poll(() => page.evaluate(() => window.localStorage.getItem('pf.auth.token')))
      .toBeNull()

    await page.locator('.modal').getByRole('button', { name: '取消' }).click()
    await expect(page.locator('.turn-error-actions').getByRole('button', { name: '重试（匿名）' })).toBeVisible()
    await page.getByRole('button', { name: '重试（匿名）' }).click()
    await expectAnswer(page)
    await expect(page.locator('.source-card')).toHaveCount(1)
    await expect(page.locator('.turn-error')).toHaveCount(0)
  })

  test('登录态 401：重新登录后恢复未落库问题并手动重试成功', async ({ page }) => {
    await page.goto('/')
    const username = `retry_${Date.now()}`
    await register(page, username)
    await ask(page, '法师 1 环法术有哪些')
    await expectAnswer(page)

    await page.evaluate(() => window.localStorage.setItem('pf.auth.token', 'invalid-token'))
    await ask(page, '法师 1 环法术有哪些')
    await expect(page.locator('.modal')).toBeVisible()
    await expect(page.locator('.turn-error')).toContainText('登录状态已失效')
    // 账号会话上匿名重试会 404，不应展示该入口；只保留登录
    await expect(page.locator('.turn-error-actions').getByRole('button', { name: '重试（匿名）' })).toHaveCount(0)
    await expect(page.locator('.turn-error-actions').getByRole('button', { name: '登录', exact: true })).toBeVisible()

    await submitLogin(page, username)
    await expect(page.locator('.turn-error')).toContainText('已恢复登录前未完成的提问')
    await expect(page.locator('.user-bubble')).toHaveCount(2)
    await expect(page.locator('.user-bubble').nth(1)).toHaveText('法师 1 环法术有哪些')

    await page.getByRole('button', { name: '重试', exact: true }).click()
    await expect(page.locator('.turn-assistant')).toHaveCount(2)
    await expect(page.locator('.turn-error')).toHaveCount(0)
    await expect(page.locator('.source-card')).toHaveCount(2)
  })

  test('删除进行中的会话：晚到结果返回 410，不复活、刷新不回填', async ({ page }) => {
    await page.goto('/')
    await ask(page, '法师 1 环法术有哪些')
    await expectAnswer(page)

    await ask(page, '删除中的后台问题')
    await expect(page.locator('.waiting')).toBeVisible()
    await page.getByRole('button', { name: '新会话' }).click()
    await expect(page.locator('.welcome h2')).toBeVisible()

    await openHistory(page)
    const pendingItem = page.locator('.history-item', { hasText: '法师 1 环法术有哪些' })
    await expect(pendingItem).toHaveCount(1)
    await expect(pendingItem).toContainText('回答中')

    const gone = page.waitForResponse(
      (response) => response.url().includes('/api/chat') && response.status() === 410,
      { timeout: 30_000 },
    )
    await pendingItem.hover()
    await pendingItem.getByRole('button', { name: '删除' }).click()
    await page.locator('.delete-confirm').getByRole('button', { name: '删除' }).click()
    await gone

    // 删除后抽屉仍保持打开，先确认列表不复活，再用 Esc 关闭
    await expect(page.locator('.history-item')).toHaveCount(0)
    await expect(page.locator('.empty-note')).toHaveText('暂无历史会话')
    await page.keyboard.press('Escape')
    await expect(page.locator('.drawer')).toHaveCount(0)
    await expect(page.locator('.welcome h2')).toBeVisible()

    await page.reload()
    await openHistory(page)
    await expect(page.locator('.history-item')).toHaveCount(0)
  })
})
