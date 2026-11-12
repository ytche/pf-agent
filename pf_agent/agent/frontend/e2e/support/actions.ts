import { expect, type Page } from '@playwright/test'

export async function ask(page: Page, question: string): Promise<void> {
  const input = page.locator('.composer-input')
  await input.fill(question)
  await input.press('Enter')
}

export async function expectAnswer(page: Page, count = 1): Promise<void> {
  await expect(page.locator('.turn-assistant')).toHaveCount(count, { timeout: 10_000 })
}

export async function openHistory(page: Page): Promise<void> {
  await page.getByRole('button', { name: '历史', exact: true }).click()
}
