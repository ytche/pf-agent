import { spawnSync } from 'node:child_process'
import fs from 'node:fs'
import { readState, tempDir } from './support/stack'

function killPid(pid: number): void {
  try {
    process.kill(pid, 'SIGTERM')
  } catch {
    return
  }
  const deadline = Date.now() + 10_000
  while (Date.now() < deadline) {
    try {
      process.kill(pid, 0)
    } catch {
      return
    }
    spawnSync('sleep', ['0.2'])
  }
  try {
    process.kill(pid, 'SIGKILL')
  } catch {
    // 已退出
  }
}

export default async function globalTeardown(): Promise<void> {
  const state = readState()
  if (state) {
    killPid(state.appPid)
    killPid(state.stubPid)
    spawnSync('docker', ['rm', '-f', state.pgContainer], { stdio: 'ignore' })
  }
  fs.rmSync(tempDir(), { recursive: true, force: true })
}
