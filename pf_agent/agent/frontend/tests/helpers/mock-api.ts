import { vi } from 'vitest'

export interface MockRequest {
  method: string
  path: string
  query: URLSearchParams
  body: any
}

export type MockHandler = (request: MockRequest) => Response | Promise<Response>

export function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

export function empty(status = 204): Response {
  return new Response(null, { status })
}

export function installFetch(handler: MockHandler) {
  const mock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, 'http://localhost')
    const method = (init?.method ?? 'GET').toUpperCase()
    const body = init?.body ? JSON.parse(String(init.body)) : null
    return handler({ method, path: url.pathname, query: url.searchParams, body })
  })
  vi.stubGlobal('fetch', mock)
  return mock
}
