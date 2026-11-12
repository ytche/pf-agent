import { expect, test } from '@playwright/test'
import { ask, expectAnswer, openHistory } from './support/actions'
import { installStubApi } from './support/stub-api'

test.describe('桌面端问答 SPA', () => {
  test('空会话欢迎、示例提问与来源默认 3 张、上标定位', async ({ page }) => {
    await installStubApi(page, { delayMs: 600 })
    await page.goto('/')

    await expect(page.locator('.welcome h2')).toHaveText('有什么规则问题？')
    await expect(page.locator('.example')).toHaveCount(4)

    await page.locator('.example').first().click()
    await expect(page.locator('.waiting')).toBeVisible()
    await expectAnswer(page)

    await expect(page.locator('.user-bubble')).toHaveText('借机攻击在什么情况下触发？')
    await expect(page.locator('.source-card')).toHaveCount(3)
    await expect(page.locator('.expand-sources')).toHaveText('查看全部 4 条')
    await expect(page.locator('.source-book').first()).toHaveText('核心规则书 1')
    await expect(page.locator('.source-abbr').first()).toHaveText('CRB1')

    await page.locator('sup.cite').first().click()
    await expect(page.locator('.source-card')).toHaveCount(4)
    await expect(page.locator('.source-card').nth(3)).toHaveClass(/cite-flash/)
  })

  test('多会话切换、置顶、重命名与永久删除', async ({ page }) => {
    await installStubApi(page)
    await page.goto('/')

    await ask(page, '问题一')
    await expectAnswer(page)
    await page.getByRole('button', { name: '新会话' }).click()
    await expect(page.locator('.welcome h2')).toBeVisible()
    await ask(page, '问题二')
    await expectAnswer(page)

    await openHistory(page)
    await expect(page.locator('.history-item')).toHaveCount(2)

    const firstItem = page.locator('.history-item', { hasText: '问题一' })
    await firstItem.hover()
    await firstItem.getByRole('button', { name: '置顶' }).click()
    await expect(page.locator('.history-item').first()).toContainText('问题一')

    const secondItem = page.locator('.history-item', { hasText: '问题二' })
    await secondItem.hover()
    await secondItem.getByRole('button', { name: '重命名' }).click()
    await page.locator('.rename-input').fill('改名会话')
    await page.getByRole('button', { name: '保存' }).click()
    await expect(page.locator('.history-item', { hasText: '改名会话' })).toHaveCount(1)

    const renamed = page.locator('.history-item', { hasText: '改名会话' })
    await renamed.hover()
    await renamed.getByRole('button', { name: '删除' }).click()
    await page.locator('.delete-confirm').getByRole('button', { name: '删除' }).click()
    await expect(page.locator('.history-item')).toHaveCount(1)
    await expect(page.locator('.history-item')).toContainText('问题一')
  })

  test('后台请求跨会话完成并显示未读，打开后清除', async ({ page }) => {
    await installStubApi(page, { delayMs: 1200 })
    await page.goto('/')

    await ask(page, '后台问题')
    await expect(page.locator('.waiting')).toBeVisible()
    await page.getByRole('button', { name: '新会话' }).click()
    await expect(page.locator('.welcome h2')).toBeVisible()
    await page.waitForTimeout(1500)

    await openHistory(page)
    await expect(page.locator('.history-item')).toHaveCount(1)
    const backgroundItem = page.locator('.history-item', { hasText: '后台问题' })
    await expect(backgroundItem.locator('.unread-dot')).toBeVisible()

    await backgroundItem.locator('.history-main').click()
    await expect(page.locator('.user-bubble')).toHaveText('后台问题')
    await expectAnswer(page)

    await openHistory(page)
    await expect(page.locator('.history-item', { hasText: '后台问题' }).locator('.unread-dot')).toHaveCount(0)
  })

  test('hash 路由刷新后恢复会话与来源', async ({ page }) => {
    await installStubApi(page)
    await page.goto('/')
    await ask(page, '刷新问题')
    await expectAnswer(page)
    expect(page.url()).toContain('#/c/')

    await page.reload()
    await expect(page.locator('.user-bubble')).toHaveText('刷新问题')
    await expectAnswer(page)
    await expect(page.locator('.source-card')).toHaveCount(3)
    await page.locator('sup.cite').first().click()
    await expect(page.locator('.source-card')).toHaveCount(4)
  })

  test('恶意 Markdown 与来源正文不执行脚本', async ({ page }) => {
    await installStubApi(page, {
      answer: () => ({
        answer:
          '<script>window.__pwned = 1</script>\n\n<img src=x onerror="window.__pwned = 1">\n\n[bad](javascript:window.__pwned=1) 正常引用 [#1]',
        sources: [
          {
            book: '核心规则书',
            tocPath: '战斗',
            content: '<img src=x onerror="window.__pwned = 1">来源正文',
          },
        ],
      }),
    })
    await page.goto('/')
    await ask(page, 'XSS 问题')
    await expectAnswer(page)

    expect(await page.evaluate(() => (window as unknown as { __pwned?: number }).__pwned)).toBeUndefined()
    await expect(page.locator('.answer-body script')).toHaveCount(0)
    await expect(page.locator('.answer-body img')).toHaveCount(0)
    await expect(page.locator('.source-content img')).toHaveCount(0)
    await expect(page.locator('.source-content').first()).toContainText('<img')

    const hrefs = await page.locator('.answer-body a').evaluateAll((links) =>
      links.map((link) => link.getAttribute('href') ?? ''),
    )
    hrefs.forEach((href) => expect(href.toLowerCase()).not.toContain('javascript:'))
  })

  test('宽表格在表格区域内滚动，长来源完整展示', async ({ page }) => {
    const columns = Array.from({ length: 14 }, (_, index) => `第 ${index + 1} 列表头`)
    const header = `| ${columns.join(' | ')} |`
    const divider = `| ${columns.map(() => '---').join(' | ')} |`
    const row = `| ${columns.map((_, index) => `单元格内容 ${index + 1}`).join(' | ')} |`
    const longSource = '这是一段用于验证来源完整展开的长文本。'.repeat(120)

    await installStubApi(page, {
      answer: () => ({
        answer: `${header}\n${divider}\n${row}\n\n表格很宽，但应在表格区域内滚动。`,
        sources: [{ book: '核心规则书', tocPath: '附录 / 长表格', content: longSource }],
      }),
    })
    await page.goto('/')
    await ask(page, '宽表格问题')
    await expectAnswer(page)

    const tableMetrics = await page.locator('.answer-body table').evaluate((table) => ({
      scrollWidth: table.scrollWidth,
      clientWidth: table.clientWidth,
    }))
    expect(tableMetrics.scrollWidth).toBeGreaterThan(tableMetrics.clientWidth)

    const sourceMetrics = await page.locator('.source-content').first().evaluate((element) => {
      const style = getComputedStyle(element)
      return {
        scrollHeight: element.scrollHeight,
        clientHeight: element.clientHeight,
        overflow: style.overflow,
        maxHeight: style.maxHeight,
        textLength: element.textContent?.length ?? 0,
      }
    })
    expect(sourceMetrics.textLength).toBeGreaterThan(1000)
    expect(sourceMetrics.scrollHeight).toBe(sourceMetrics.clientHeight)
    expect(sourceMetrics.overflow).toBe('visible')
    expect(sourceMetrics.maxHeight).toBe('none')

    const pageFits = await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 1,
    )
    expect(pageFits).toBe(true)
  })

  test('标错表单提交成功并显示记录结果', async ({ page }) => {
    await installStubApi(page)
    await page.goto('/')
    await ask(page, '标错问题')
    await expectAnswer(page)

    await page.getByRole('button', { name: '标错' }).click()
    await page.locator('.feedback-form select').selectOption('事实错误')
    await page.locator('.feedback-form textarea').first().fill('正确说法示例')
    await page.getByRole('button', { name: '提交标注' }).click()
    await expect(page.locator('.feedback-status')).toContainText('已记录标注')
  })

  test('匿名提问后登录认领、管理员入口与退出清缓存', async ({ page }) => {
    await installStubApi(page)
    await page.goto('/')
    await ask(page, '匿名问题')
    await expectAnswer(page)

    await page.getByRole('button', { name: '登录 / 注册' }).click()
    await page.locator('.modal input[autocomplete="username"]').fill('admin')
    await page.locator('.modal input[type="password"]').first().fill('password123')
    await page.locator('.modal').getByRole('button', { name: '登录', exact: true }).click()

    await expect(page.locator('.notice')).toContainText('认领')
    await expect(page.locator('.account-btn')).toContainText('admin')

    await page.locator('.account-btn').click()
    await expect(page.getByRole('menuitem', { name: '管理后台' })).toBeVisible()
    await page.getByRole('menuitem', { name: '退出登录' }).click()
    await expect(page.getByRole('button', { name: '登录 / 注册' })).toBeVisible()

    await openHistory(page)
    await expect(page.locator('.history-item')).toHaveCount(0)
    await expect(page.locator('.empty-note')).toHaveText('暂无历史会话')
  })
})
