import { defineConfig, devices } from '@playwright/test'

const baseURL = process.env.PF_E2E_BASE_URL || 'http://127.0.0.1:18080'

/**
 * 全栈 E2E：真实 Spring Boot 后端 + 真实 PostgreSQL（Docker 启动，等价 Testcontainers 的
 * 一次性数据库）+ 打桩 ChatModel（OpenAI 兼容 stub）。
 *
 * 前置：npm run build 且 mvn -Dmaven.test.skip=true package（npm 的
 * pretest:e2e:fullstack 脚本已串起）；需要 Docker 与 Java 17。
 */
export default defineConfig({
  testDir: './e2e-fullstack',
  testMatch: /.*\.spec\.ts/,
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: process.env.CI ? [['list'], ['github']] : [['list']],
  globalSetup: './e2e-fullstack/global-setup.ts',
  globalTeardown: './e2e-fullstack/global-teardown.ts',
  use: {
    baseURL,
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'fullstack',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 900 } },
    },
  ],
})
