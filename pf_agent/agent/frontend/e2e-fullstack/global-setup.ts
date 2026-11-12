import { spawn, spawnSync, type ChildProcess } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import {
  appPort,
  baseURL,
  createTempData,
  findJar,
  frontendDir,
  logTail,
  pickFreePort,
  repoAgentDir,
  stubPort,
  tempDir,
  waitForHttp,
  waitForTcp,
  writeState,
} from './support/stack'

function dockerReady(container: string): boolean {
  return spawnSync('docker', ['exec', container, 'pg_isready', '-U', 'pf_agent', '-d', 'pf_agent']).status === 0
}

function dockerLogs(container: string): string {
  const result = spawnSync('docker', ['logs', '--tail', '200', container], { encoding: 'utf8' })
  return `${result.stdout ?? ''}\n${result.stderr ?? ''}`
}

/**
 * entrypoint 最终服务器就绪：初始化阶段会先起临时服务器（也会打 "ready to accept connections"），
 * 必须在 "PostgreSQL init process complete" 之后再次出现该日志，才算最终服务器。
 */
function finalServerReady(logs: string): boolean {
  const initDone = logs.lastIndexOf('PostgreSQL init process complete')
  if (initDone < 0) return false
  return logs.indexOf('database system is ready to accept connections', initDone) >= 0
}

function killPid(pid: number | undefined): void {
  if (!pid) return
  try {
    process.kill(pid, 'SIGKILL')
  } catch {
    // 已退出
  }
}

export default async function globalSetup(): Promise<void> {
  const data = createTempData()
  const jar = findJar()
  const container = `pf-m25-e2e-pg-${process.pid}-${Date.now()}`
  const pgPort = await pickFreePort()
  const stubScript = path.join(frontendDir(), 'e2e-fullstack', 'support', 'stub-model-server.mjs')
  const appLogPath = path.join(data.dir, 'app.log')

  let stub: ChildProcess | undefined
  let app: ChildProcess | undefined
  const cleanup = (): void => {
    killPid(app?.pid)
    killPid(stub?.pid)
    spawnSync('docker', ['rm', '-f', container], { stdio: 'ignore' })
  }

  const pgStart = Date.now()
  spawnSync('docker', ['rm', '-f', container], { stdio: 'ignore' })
  const pgRun = spawnSync(
    'docker',
    [
      'run', '-d', '--rm', '--name', container,
      '-e', 'POSTGRES_USER=pf_agent',
      '-e', 'POSTGRES_PASSWORD=pf_agent',
      '-e', 'POSTGRES_DB=pf_agent',
      '-p', `${pgPort}:5432`,
      'postgres:16-alpine',
    ],
    { encoding: 'utf8' },
  )
  if (pgRun.status !== 0) {
    throw new Error(`启动 PostgreSQL 容器失败（需要 Docker）:\n${pgRun.stderr}`)
  }

  // 就绪判定：连续 3 次 pg_isready 成功（间隔 500ms），且看到 entrypoint 最终服务器日志；
  // 日志格式异常时回退为「3 次成功且已运行 >=2s」，避免 initdb 临时服务器窗口误判。
  let consecutive = 0
  let finalLogSeen = false
  let pgStable = false
  const pgDeadline = Date.now() + 90_000
  while (Date.now() < pgDeadline) {
    const inspect = spawnSync('docker', ['inspect', '-f', '{{.State.Running}}', container], { encoding: 'utf8' })
    if (inspect.status !== 0 || inspect.stdout.trim() !== 'true') {
      const logs = dockerLogs(container)
      cleanup()
      throw new Error(`PostgreSQL 容器未保持运行（${Date.now() - pgStart}ms）:\n${logs}`)
    }

    const logs = dockerLogs(container)
    if (finalServerReady(logs)) finalLogSeen = true
    consecutive = dockerReady(container) ? consecutive + 1 : 0

    const elapsed = Date.now() - pgStart
    if (finalLogSeen && consecutive >= 1) {
      pgStable = true
      break
    }
    if (consecutive >= 3 && elapsed >= 2_000) {
      pgStable = true
      break
    }
    await new Promise((resolve) => setTimeout(resolve, 500))
  }
  const pgElapsed = Date.now() - pgStart
  if (!pgStable) {
    const logs = dockerLogs(container)
    cleanup()
    throw new Error(`PostgreSQL 容器 ${pgElapsed}ms 内未稳定就绪（连续成功 ${consecutive} 次）:\n${logs.slice(-4000)}`)
  }

  try {
    const stubLog = fs.openSync(path.join(data.dir, 'stub.log'), 'a')
    stub = spawn(process.execPath, [stubScript], {
      env: { ...process.env, STUB_MODEL_PORT: String(stubPort) },
      detached: true,
      stdio: ['ignore', stubLog, stubLog],
    })
    stub.unref()
    await waitForTcp(stubPort, 15_000, '打桩 ChatModel')

    const appLog = fs.openSync(appLogPath, 'a')
    const env: NodeJS.ProcessEnv = {
      ...process.env,
      SERVER_PORT: String(appPort),
      SPRING_DATASOURCE_URL: `jdbc:postgresql://127.0.0.1:${pgPort}/pf_agent`,
      SPRING_DATASOURCE_USERNAME: 'pf_agent',
      SPRING_DATASOURCE_PASSWORD: 'pf_agent',
      PF_CHAT_MEMORY: 'jdbc',
      PF_AUTH_ENABLED: 'true',
      PF_AUTH_JWT_SECRET: 'pf-m25-e2e-jwt-secret-please-change-0123456789',
      PF_RATE_LIMIT_ENABLED: 'false',
      PF_QUOTA_ENABLED: 'false',
      SPRING_AI_OPENAI_BASE_URL: `http://127.0.0.1:${stubPort}`,
      SPRING_AI_OPENAI_API_KEY: 'stub-key',
      SPRING_AI_OPENAI_CHAT_OPTIONS_MODEL: 'stub-model',
      SPRING_AI_RETRY_MAX_ATTEMPTS: '1',
      PF_SEARCH_CHAT_TIMEOUT: '30s',
      PF_TELEMETRY_IMPORT_ENABLED: 'false',
      PF_CHUNKS_SPELLSPATH: data.spells,
      PF_CHUNKS_CLASSESPATH: data.classes,
      PF_CHUNKS_FEATPATH: data.feat,
      PF_CHUNKS_RACEPATH: data.race,
      PF_CHUNKS_TRAITPATH: data.trait,
      PF_CHUNKS_EQUIPMENTPATH: data.equipment,
      PF_CHUNKS_SKILLPATH: data.skill,
      PF_CHUNKS_RULEPATH: data.rule,
      PF_STORES_SPELLFILEPATH: path.join(data.storesDir, 'spells.json'),
      PF_STORES_CLASSFILEPATH: path.join(data.storesDir, 'classes.json'),
      PF_STORES_FEATFILEPATH: path.join(data.storesDir, 'feat.json'),
      PF_STORES_RACEFILEPATH: path.join(data.storesDir, 'race.json'),
      PF_STORES_TRAITFILEPATH: path.join(data.storesDir, 'trait.json'),
      PF_STORES_EQUIPMENTFILEPATH: path.join(data.storesDir, 'equipment.json'),
      PF_STORES_SKILLFILEPATH: path.join(data.storesDir, 'skill.json'),
      PF_STORES_RULEFILEPATH: path.join(data.storesDir, 'rule.json'),
      PF_SPELLLISTS_FILEPATH: path.join(frontendDir(), 'e2e-fullstack', 'fixture', 'spell_lists.json'),
      PF_SPELLLISTS_UNIONFILEPATH: path.join(data.dir, 'no-union.json'),
      PF_CLASSTABLES_FILEPATH: path.join(data.dir, 'no-class-tables.json'),
      PF_LISTEXPORTS_FEATFILEPATH: path.join(data.dir, 'no-feat.json'),
      PF_LISTEXPORTS_RACEFILEPATH: path.join(data.dir, 'no-race.json'),
      PF_LISTEXPORTS_EQUIPMENTFILEPATH: path.join(data.dir, 'no-equipment.json'),
      PF_FEEDBACK_FILEPATH: path.join(data.dataDir, 'annotations.jsonl'),
      PF_GAPS_FILEPATH: path.join(data.dataDir, 'gaps.jsonl'),
      PF_TOOLS_FILEPATH: path.join(data.dataDir, 'tools.jsonl'),
    }
    app = spawn('java', ['-jar', jar], {
      cwd: repoAgentDir(),
      env,
      detached: true,
      stdio: ['ignore', appLog, appLog],
    })
    app.unref()

    await waitForHttp(`${baseURL}/api/health`, 120_000, 'Spring Boot（真实后端）')
  } catch (error) {
    const appTail = logTail(appLogPath)
    cleanup()
    throw new Error(`${(error as Error).message}\n应用日志尾部:\n${appTail}`)
  }

  writeState({
    pgContainer: container,
    pgPort,
    appPid: app.pid!,
    stubPid: stub.pid!,
    appPort,
  })
}
