import { spawnSync } from 'node:child_process'
import fs from 'node:fs'
import net from 'node:net'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

export interface StackState {
  pgContainer: string
  pgPort: number
  appPid: number
  stubPid: number
  appPort: number
}
export const appPort = Number(process.env.PF_E2E_PORT || 18080)
export const stubPort = Number(process.env.PF_E2E_STUB_PORT || 18081)
export const baseURL = process.env.PF_E2E_BASE_URL || `http://127.0.0.1:${appPort}`

export async function pickFreePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = net.createServer()
    server.once('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const address = server.address()
      const port = typeof address === 'object' && address ? address.port : 0
      server.close(() => resolve(port))
    })
  })
}

export function repoAgentDir(): string {
  return fileURLToPath(new URL('../../../', import.meta.url))
}

export function frontendDir(): string {
  return fileURLToPath(new URL('../../', import.meta.url))
}

export function tempDir(): string {
  return path.join(frontendDir(), '.e2e-fullstack-tmp')
}

export function stateFile(): string {
  return path.join(tempDir(), 'state.json')
}

export function run(command: string, args: string[], options: { cwd?: string; env?: NodeJS.ProcessEnv } = {}): string {
  const result = spawnSync(command, args, {
    cwd: options.cwd,
    env: { ...process.env, ...options.env },
    encoding: 'utf8',
  })
  if (result.status !== 0) {
    throw new Error(
      `命令失败: ${command} ${args.join(' ')}\nstdout:\n${result.stdout ?? ''}\nstderr:\n${result.stderr ?? ''}`,
    )
  }
  return result.stdout
}

export async function waitForTcp(port: number, timeoutMs: number, label: string): Promise<void> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const ok = await new Promise<boolean>((resolve) => {
      const socket = net.createConnection({ host: '127.0.0.1', port }, () => {
        socket.destroy()
        resolve(true)
      })
      socket.on('error', () => resolve(false))
      socket.setTimeout(1000, () => {
        socket.destroy()
        resolve(false)
      })
    })
    if (ok) return
    await new Promise((resolve) => setTimeout(resolve, 300))
  }
  throw new Error(`${label} 在 ${timeoutMs}ms 内未就绪（127.0.0.1:${port}）`)
}

export async function waitForHttp(url: string, timeoutMs: number, label: string): Promise<void> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url)
      if (response.ok) return
    } catch {
      // 服务尚未监听：继续等待
    }
    await new Promise((resolve) => setTimeout(resolve, 500))
  }
  throw new Error(`${label} 在 ${timeoutMs}ms 内未返回 2xx（${url}）`)
}

export function findJar(): string {
  const targetDir = path.join(repoAgentDir(), 'target')
  if (!fs.existsSync(targetDir)) throw new Error(`未找到 Maven 产物目录: ${targetDir}`)
  const jars = fs
    .readdirSync(targetDir)
    .filter((name) => /^pf-agent-.*\.jar$/.test(name))
    .map((name) => path.join(targetDir, name))
    .sort((left, right) => fs.statSync(right).mtimeMs - fs.statSync(left).mtimeMs)
  if (jars.length === 0) {
    throw new Error('未找到 Spring Boot jar；先运行 npm run build && mvn -Dmaven.test.skip=true package')
  }
  return jars[0]
}

export function logTail(file: string, lines = 80): string {
  try {
    return fs.readFileSync(file, 'utf8').split('\n').slice(-lines).join('\n')
  } catch {
    return ''
  }
}

export function createTempData(): Record<string, string> {
  const dir = tempDir()
  fs.rmSync(dir, { recursive: true, force: true })
  const chunksDir = path.join(dir, 'chunks')
  const storesDir = path.join(dir, 'stores')
  const dataDir = path.join(dir, 'data')
  for (const target of [chunksDir, storesDir, dataDir]) fs.mkdirSync(target, { recursive: true })

  const modules = ['spells', 'classes', 'feat', 'race', 'trait', 'equipment', 'skill', 'rule']
  const chunkPaths: Record<string, string> = {}
  for (const module of modules) {
    const file = path.join(chunksDir, `${module}.jsonl`)
    fs.writeFileSync(file, '')
    chunkPaths[module] = file
  }
  return { dir, chunksDir, storesDir, dataDir, ...chunkPaths }
}

export function writeState(state: StackState): void {
  fs.writeFileSync(stateFile(), JSON.stringify(state, null, 2))
}

export function readState(): StackState | null {
  try {
    return JSON.parse(fs.readFileSync(stateFile(), 'utf8')) as StackState
  } catch {
    return null
  }
}
