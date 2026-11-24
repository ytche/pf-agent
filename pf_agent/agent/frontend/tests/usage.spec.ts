import { beforeEach, describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import UsageView from '@/components/UsageView.vue'
import type { UsageSummary } from '@/api/contract'
import { useAuthStore } from '@/stores/auth'
import { useConversationsStore } from '@/stores/conversations'
import { installFetch, json, type MockRequest } from './helpers/mock-api'

const BASE = '2026-11-13T02:00:00Z'

function summary(over: Partial<UsageSummary> = {}): UsageSummary {
  return {
    range: 'month',
    groupBy: 'day',
    scope: 'owner',
    timezone: 'Asia/Shanghai',
    formula: '预测 = 本月已用 + 最近 7 个自然日（含今天）日均 × 今天之后剩余天数',
    from: '2026-10-31T16:00:00Z',
    to: BASE,
    totals: {
      calls: 3,
      promptTokens: 300,
      completionTokens: 150,
      totalTokens: 450,
      cost: 12.34,
      currency: 'CNY',
      missingUsageCount: 2,
    },
    groups: [
      {
        key: '2026-11-13',
        label: '2026-11-13',
        calls: 3,
        promptTokens: 300,
        completionTokens: 150,
        totalTokens: 450,
        cost: 12.34,
        missingUsageCount: 2,
      },
    ],
    forecast: {
      timezone: 'Asia/Shanghai',
      monthToDateCost: 12.34,
      dailyAverageCost: 1.2,
      windowDays: 7,
      dataDays: 5,
      remainingDays: 17,
      predictedMonthCost: 20.5,
      formula: '预测 = 本月已用 + 最近 7 个自然日（含今天）日均 × 今天之后剩余天数',
    },
    ...over,
  }
}

function login(username = 'bob', admin = false): void {
  const auth = useAuthStore()
  auth.enabled = true
  auth.user = { uid: 7, username, nickname: username }
  auth.isAdmin = admin
}

async function mountView() {
  const wrapper = mount(UsageView)
  await flushPromises()
  return wrapper
}

let requests: MockRequest[]

beforeEach(() => {
  setActivePinia(createPinia())
  requests = []
})

describe('UsageView', () => {
  it('展示本月费用、预测与缺失用量提示', async () => {
    login('bob')
    const fetchMock = installFetch((request) => {
      requests.push(request)
      return json(200, summary())
    })

    const wrapper = await mountView()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(requests[0].path).toBe('/api/usage/summary')
    expect(requests[0].query.get('range')).toBe('month')
    const text = wrapper.text()
    expect(text).toContain('本月合计')
    expect(text).toContain('CNY 12.3400')
    expect(text).toContain('本月预测')
    expect(text).toContain('CNY 20.5000')
    expect(text).toContain('最近 7 个自然日日均')
    expect(text).toContain('2 次调用缺失用量')
    expect(text).toContain('2026-11-13')
  })

  it('小额费用用 6 位小数，不显示成 0.0000', async () => {
    login('bob')
    const base = summary()
    installFetch(() => json(200, {
      ...base,
      totals: { ...base.totals, cost: 0.0006 },
      groups: [{ ...base.groups[0], cost: 0.0006 }],
      forecast: {
        ...base.forecast,
        monthToDateCost: 0.0006,
        dailyAverageCost: 0.000085,
        predictedMonthCost: 0.002,
      },
    }))

    const wrapper = await mountView()

    expect(wrapper.text()).toContain('CNY 0.000600')
    expect(wrapper.text()).not.toContain('CNY 0.0000 ·')
  })

  it('管理员默认看全局并按用户分组', async () => {
    login('root', true)
    const fetchMock = installFetch((request) => {
      requests.push(request)
      return json(
        200,
        summary({
          scope: 'global',
          groupBy: 'owner',
          groups: [
            {
              key: '7',
              label: 'alice',
              calls: 2,
              promptTokens: 20,
              completionTokens: 10,
              totalTokens: 30,
              cost: 4,
              missingUsageCount: 0,
            },
          ],
        }),
      )
    })

    const wrapper = await mountView()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(requests[0].query.get('groupBy')).toBe('owner')
    expect(requests[0].query.get('conversationId')).toBeNull()
    const text = wrapper.text()
    expect(text).toContain('全局（管理员）')
    expect(text).toContain('按用户')
    expect(text).toContain('alice')
    expect(text).toContain('CNY 4.0000')
  })

  it('普通用户只查自己，不出现按用户分组', async () => {
    login('bob')
    const fetchMock = installFetch((request) => {
      requests.push(request)
      return json(200, summary())
    })

    const wrapper = await mountView()

    const query = requests[0].query
    expect(query.get('groupBy')).not.toBe('owner')
    expect(query.get('ownerId')).toBeNull()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const text = wrapper.text()
    expect(text).toContain('我的用量')
    expect(text).toContain('分日用量')
    expect(text).not.toContain('按用户')
  })

  it('匿名只查询当前会话，缺少会话时不发请求', async () => {
    const conversations = useConversationsStore()
    conversations.currentId = 'c1'
    installFetch((request) => {
      requests.push(request)
      return json(200, summary({ scope: 'conversation' }))
    })

    const wrapper = await mountView()

    expect(requests).toHaveLength(1)
    expect(requests[0].query.get('conversationId')).toBe('c1')
    expect(requests[0].query.get('groupBy')).toBe('day')
    expect(wrapper.text()).toContain('当前会话')

    conversations.currentId = null
    await flushPromises()
    const empty = mount(UsageView)
    await flushPromises()
    expect(empty.text()).toContain('匿名用量仅显示当前会话')
    expect(requests).toHaveLength(1)
  })

  it('403 只提示无权查看，不泄露他人用量', async () => {
    login('bob')
    installFetch(() => json(403, { error: 'forbidden', message: '无权查看' }))

    const wrapper = await mountView()

    const text = wrapper.text()
    expect(text).toContain('无权查看该用量')
    expect(text).not.toContain('CNY')
    expect(text).not.toContain('本月合计')
    expect(wrapper.find('.usage-groups').exists()).toBe(false)
  })
})
