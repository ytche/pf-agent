import { expect, test, type Page, type Route } from '@playwright/test'
import { ask, expectAnswer } from './support/actions'
import { installStubApi } from './support/stub-api'

interface UsageExpectation {
  scope: 'global' | 'owner' | 'conversation'
  groupBy: 'day' | 'owner'
  cost: number
  predicted: number
  groups?: Array<{ key: string; label: string; cost: number }>
  status?: number
}

function usageBody(expectation: UsageExpectation) {
  return {
    range: 'month',
    groupBy: expectation.groupBy,
    scope: expectation.scope,
    timezone: 'Asia/Shanghai',
    formula: '预测 = 本月已用 + 最近 7 个自然日（含今天）日均 × 今天之后剩余天数；无成本日按 0 计入，历史不足 7 天按实际天数，无历史时等于本月已用',
    from: '2026-10-31T16:00:00Z',
    to: '2026-11-13T02:00:00Z',
    totals: {
      calls: 3,
      promptTokens: 300,
      completionTokens: 150,
      totalTokens: 450,
      cost: expectation.cost,
      currency: 'CNY',
      missingUsageCount: 1,
    },
    groups: (expectation.groups ?? [
      { key: '2026-11-13', label: '2026-11-13', cost: expectation.cost },
    ]).map((group) => ({
      key: group.key,
      label: group.label,
      calls: 2,
      promptTokens: 20,
      completionTokens: 10,
      totalTokens: 30,
      cost: group.cost,
      missingUsageCount: 0,
    })),
    forecast: {
      timezone: 'Asia/Shanghai',
      monthToDateCost: expectation.cost,
      dailyAverageCost: expectation.cost / 7,
      windowDays: 7,
      dataDays: 5,
      remainingDays: 17,
      predictedMonthCost: expectation.predicted,
      formula: '预测 = 本月已用 + 最近 7 个自然日（含今天）日均 × 今天之后剩余天数',
    },
  }
}

/** 在 stub-api 之后注册，Playwright 后注册的路由优先命中 */
async function stubUsage(page: Page, expectation: UsageExpectation) {
  const queries: URLSearchParams[] = []
  await page.route('**/api/usage/summary**', (route: Route) => {
    const url = new URL(route.request().url())
    queries.push(url.searchParams)
    if (expectation.status) {
      return route.fulfill({
        status: expectation.status,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ error: 'forbidden', message: '无权查看' }),
      })
    }
    return route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(usageBody(expectation)),
    })
  })
  return queries
}

async function loginAs(page: Page, username: string): Promise<void> {
  await page.goto('/')
  await page.getByRole('button', { name: '登录 / 注册' }).click()
  await page.locator('.modal input[autocomplete="username"]').fill(username)
  await page.locator('.modal input[type="password"]').first().fill('password123')
  await page.locator('.modal').getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.locator('.account-btn')).toContainText(username)
}

test.describe('用量页（stub /api/usage/summary）', () => {
  test('匿名只查当前会话', async ({ page }) => {
    await installStubApi(page)
    const queries = await stubUsage(page, {
      scope: 'conversation',
      groupBy: 'day',
      cost: 1.2,
      predicted: 3.6,
    })

    await page.goto('/')
    await ask(page, '匿名用量问题')
    await expectAnswer(page)
    await page.getByRole('link', { name: '用量' }).click()

    await expect(page.locator('.usage-view')).toBeVisible()
    await expect(page.locator('.usage-sub')).toContainText('当前会话')
    await expect(page.locator('.usage-total-cost')).toHaveText('CNY 1.2000')
    await expect(page.locator('.usage-predicted-cost')).toHaveText('CNY 3.6000')
    expect(queries).toHaveLength(1)
    expect(queries[0].get('conversationId')).toBeTruthy()
    expect(queries[0].get('groupBy')).toBe('day')
  })

  test('个人视图只显示自己的用量，不出现按用户分组', async ({ page }) => {
    await installStubApi(page)
    const queries = await stubUsage(page, {
      scope: 'owner',
      groupBy: 'day',
      cost: 2.5,
      predicted: 5,
    })

    await loginAs(page, 'bob')
    await page.getByRole('link', { name: '用量' }).click()

    await expect(page.locator('.usage-sub')).toContainText('我的用量')
    await expect(page.locator('.usage-total-cost')).toHaveText('CNY 2.5000')
    await expect(page.locator('.usage-groups h2')).toHaveText('分日用量')
    expect(queries[0].get('groupBy')).toBe('day')
    expect(queries[0].get('conversationId')).toBeNull()
  })

  test('管理员看全局并按用户分组', async ({ page }) => {
    await installStubApi(page)
    const queries = await stubUsage(page, {
      scope: 'global',
      groupBy: 'owner',
      cost: 9,
      predicted: 20,
      groups: [
        { key: '7', label: 'alice', cost: 4 },
        { key: '8', label: 'carol', cost: 5 },
      ],
    })

    await loginAs(page, 'admin')
    await page.getByRole('link', { name: '用量' }).click()

    await expect(page.locator('.usage-sub')).toContainText('全局（管理员）')
    await expect(page.locator('.usage-groups h2')).toHaveText('按用户')
    await expect(page.locator('.usage-group-label')).toHaveText(['alice', 'carol'])
    await expect(page.locator('.usage-group-cost').first()).toHaveText('CNY 4.0000')
    expect(queries[0].get('groupBy')).toBe('owner')
  })

  test('窄屏顶栏不挤压，可返回对话', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await installStubApi(page)
    await stubUsage(page, { scope: 'conversation', groupBy: 'day', cost: 0.0006, predicted: 0.002 })

    await page.goto('/')
    await ask(page, '窄屏用量')
    await expectAnswer(page)
    await expect(page.locator('.brand-sub')).toBeHidden()
    await page.getByRole('link', { name: '用量' }).click()

    await expect(page.locator('.usage-total-cost')).toHaveText('CNY 0.000600')
    const fits = await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 1,
    )
    expect(fits).toBe(true)

    await page.getByRole('link', { name: '返回对话' }).click()
    await expect(page.locator('.usage-view')).toHaveCount(0)
    await expect(page.locator('.user-bubble')).toHaveText('窄屏用量')
  })

  test('403 只提示无权查看且不渲染任何他人数据', async ({ page }) => {
    await installStubApi(page)
    await stubUsage(page, {
      scope: 'owner',
      groupBy: 'day',
      cost: 0,
      predicted: 0,
      status: 403,
    })

    await loginAs(page, 'bob')
    await page.getByRole('link', { name: '用量' }).click()

    await expect(page.locator('.usage-error')).toHaveText('无权查看该用量')
    await expect(page.locator('.usage-total-cost')).toHaveCount(0)
    await expect(page.locator('.usage-groups')).toHaveCount(0)
    await expect(page.locator('.usage-view')).not.toContainText('CNY')
  })
})
