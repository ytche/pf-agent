import { expect, test } from '@playwright/test'
import { ask, expectAnswer, openHistory } from './support/actions'
import { installStubApi } from './support/stub-api'

test.describe('手机端问答 SPA', () => {
  test('历史为全屏页层，返回入口可关闭', async ({ page }) => {
    await installStubApi(page)
    await page.goto('/')
    await ask(page, '手机问题')
    await expectAnswer(page)

    await openHistory(page)
    const box = await page.locator('.drawer').boundingBox()
    expect(box).not.toBeNull()
    const viewport = page.viewportSize()
    expect(box!.width).toBeGreaterThanOrEqual((viewport?.width ?? 390) - 1)

    await page.locator('.drawer-close').click()
    await expect(page.locator('.drawer')).toHaveCount(0)
    await expect(page.locator('.user-bubble')).toHaveText('手机问题')
  })

  test('底部多行输入：Shift+Enter 换行，Enter 发送', async ({ page }) => {
    await installStubApi(page)
    await page.goto('/')

    const input = page.locator('.composer-input')
    await input.fill('第一行')
    await input.press('Shift+Enter')
    await input.type('第二行')
    await expect(input).toHaveValue('第一行\n第二行')

    await input.press('Enter')
    await expectAnswer(page)
    await expect(page.locator('.user-bubble')).toHaveText('第一行 第二行')
  })

  test('手机端来源展开与上标定位可用', async ({ page }) => {
    await installStubApi(page)
    await page.goto('/')
    await ask(page, '手机来源问题')
    await expectAnswer(page)

    await expect(page.locator('.source-card')).toHaveCount(3)
    await page.locator('sup.cite').first().click()
    await expect(page.locator('.source-card')).toHaveCount(4)
    await expect(page.locator('.source-card').nth(3)).toHaveClass(/cite-flash/)
  })

  test('手机端宽表格局部滚动不撑破页面', async ({ page }) => {
    const columns = Array.from({ length: 14 }, (_, index) => `第 ${index + 1} 列`)
    const header = `| ${columns.join(' | ')} |`
    const divider = `| ${columns.map(() => '---').join(' | ')} |`
    const row = `| ${columns.map((_, index) => `值 ${index + 1}`).join(' | ')} |`
    await installStubApi(page, {
      answer: () => ({
        answer: `${header}\n${divider}\n${row}`,
        sources: [{ book: '核心规则书', tocPath: '附录', content: '短来源' }],
      }),
    })
    await page.goto('/')
    await ask(page, '手机宽表格')
    await expectAnswer(page)

    const fits = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)
    expect(fits).toBe(true)
    const tableMetrics = await page.locator('.answer-body table').evaluate((table) => ({
      scrollWidth: table.scrollWidth,
      clientWidth: table.clientWidth,
    }))
    expect(tableMetrics.scrollWidth).toBeGreaterThan(tableMetrics.clientWidth)
  })
})
