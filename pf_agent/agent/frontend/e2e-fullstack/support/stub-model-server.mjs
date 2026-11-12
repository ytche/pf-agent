#!/usr/bin/env node
// 全栈 E2E 打桩 ChatModel：OpenAI 兼容 /chat/completions。
// 第一轮返回 getSpellList 工具调用（打桩模型决定调用检索工具），
// 收到工具结果后返回带 [#1] 引用的最终回答，让真实后端走完 cited-only 快照链路。
import http from 'node:http'

const PORT = Number(process.env.STUB_MODEL_PORT || 18081)

function completion(body) {
  const messages = Array.isArray(body?.messages) ? body.messages : []
  const hasToolResult = messages.some((message) => message?.role === 'tool')
  const created = Math.floor(Date.now() / 1000)
  const base = {
    id: `chatcmpl-stub-${Date.now()}`,
    object: 'chat.completion',
    created,
    model: body?.model || 'stub-model',
  }
  if (!hasToolResult) {
    return {
      ...base,
      choices: [
        {
          index: 0,
          message: {
            role: 'assistant',
            content: null,
            tool_calls: [
              {
                id: 'call_get_spell_list',
                type: 'function',
                function: {
                  name: 'getSpellList',
                  arguments: JSON.stringify({ className: '法师', level: 1, offset: 0, limit: 20 }),
                },
              },
            ],
          },
          finish_reason: 'tool_calls',
        },
      ],
      usage: { prompt_tokens: 10, completion_tokens: 5, total_tokens: 15 },
    }
  }
  return {
    ...base,
    choices: [
      {
        index: 0,
        message: {
          role: 'assistant',
          content: '法师 1 环法术包括燃烧之手与魔法警报 [#1]。',
        },
        finish_reason: 'stop',
      },
    ],
    usage: { prompt_tokens: 20, completion_tokens: 12, total_tokens: 32 },
  }
}

const server = http.createServer((req, res) => {
  if (req.method !== 'POST' || !req.url?.endsWith('/chat/completions')) {
    res.writeHead(404, { 'Content-Type': 'application/json' })
    res.end(JSON.stringify({ error: 'not found' }))
    return
  }
  let raw = ''
  req.on('data', (chunk) => {
    raw += chunk
  })
  req.on('end', () => {
    let body = {}
    try {
      body = raw ? JSON.parse(raw) : {}
    } catch {
      res.writeHead(400, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ error: 'invalid json' }))
      return
    }
    // 可选的问答延迟：用于验证后台完成/删除竞态（由测试通过 header 或问题内容触发）
    const question = (body?.messages ?? [])
      .filter((message) => message?.role === 'user')
      .map((message) => String(message.content ?? ''))
      .join(' ')
    const slow = /SLOW|后台|删除/.test(question)
    const respond = () => {
      res.writeHead(200, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify(completion(body)))
    }
    if (slow) setTimeout(respond, 1500)
    else respond()
  })
})

server.listen(PORT, '127.0.0.1', () => {
  console.log(`[stub-model] listening on http://127.0.0.1:${PORT}`)
})

for (const signal of ['SIGTERM', 'SIGINT']) {
  process.on(signal, () => {
    server.close(() => process.exit(0))
  })
}
