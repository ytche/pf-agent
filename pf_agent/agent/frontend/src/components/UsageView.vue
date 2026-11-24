<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api, ApiError } from '@/api/client'
import type { UsageRange, UsageSummary } from '@/api/contract'
import { useAuthStore } from '@/stores/auth'
import { useConversationsStore } from '@/stores/conversations'

const auth = useAuthStore()
const conversations = useConversationsStore()

const range = ref<UsageRange>('month')
const summary = ref<UsageSummary | null>(null)
const loading = ref(false)
const error = ref('')
let requestSeq = 0

const ranges: Array<{ value: UsageRange; label: string }> = [
  { value: 'month', label: '本月' },
  { value: 'today', label: '今天' },
  { value: 'all', label: '全部' },
]

/** 匿名只能查看当前会话：没有当前会话时不发请求 */
const needsConversation = computed(() => !auth.isLoggedIn && !conversations.currentId)

const scopeLabel = computed(() => {
  switch (summary.value?.scope) {
    case 'global':
      return '全局（管理员）'
    case 'owner':
      return auth.isAdmin ? '按用户筛选' : '我的用量'
    case 'conversation':
      return '当前会话'
    default:
      return auth.isAdmin ? '全局（管理员）' : auth.isLoggedIn ? '我的用量' : '当前会话'
  }
})

const groupTitle = computed(() => {
  switch (summary.value?.groupBy) {
    case 'owner':
      return '按用户'
    case 'conversation':
      return '分会话用量'
    default:
      return '分日用量'
  }
})

function money(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  const currency = summary.value?.totals.currency ?? 'CNY'
  // 小额费用（< 0.01）用 6 位小数，避免四舍五入后显示成 0.0000
  const digits = value !== 0 && Math.abs(value) < 0.01 ? 6 : 4
  return `${currency} ${value.toFixed(digits)}`
}

function tokenCount(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : value.toLocaleString('zh-CN')
}

function errorText(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 403) return '无权查看该用量'
    if (err.status === 404) return '会话不存在或无权查看'
    if (err.status === 503) return '用量统计不可用（当前运行模式未启用）'
    return err.message
  }
  return '网络异常，请稍后重试'
}

async function load(): Promise<void> {
  const seq = ++requestSeq
  error.value = ''
  if (needsConversation.value) {
    summary.value = null
    loading.value = false
    return
  }
  loading.value = true
  try {
    const result = await api.usageSummary({
      range: range.value,
      // 管理员按用户分组；普通用户与匿名只看自己的分日数据（后端也会拒绝越权分组）
      groupBy: auth.isAdmin ? 'owner' : 'day',
      conversationId: auth.isLoggedIn ? null : conversations.currentId,
    })
    if (seq !== requestSeq) return
    summary.value = result
  } catch (err) {
    if (seq !== requestSeq) return
    summary.value = null
    error.value = errorText(err)
  } finally {
    if (seq === requestSeq) loading.value = false
  }
}

watch(
  [() => auth.isLoggedIn, () => auth.isAdmin, () => conversations.currentId, range],
  () => {
    void load()
  },
  { immediate: true },
)
</script>

<template>
  <section class="usage-view">
    <header class="usage-head">
      <div>
        <h1>用量与费用</h1>
        <p class="usage-sub">{{ scopeLabel }} · 时区 {{ summary?.timezone ?? 'Asia/Shanghai' }} · 仅统计 DeepSeek 调用</p>
      </div>
      <div class="usage-head-actions">
        <a class="ghost small usage-back" href="#/">返回对话</a>
        <div class="usage-ranges" role="group" aria-label="统计范围">
          <button
            v-for="item in ranges"
            :key="item.value"
            type="button"
            :class="range === item.value ? 'primary small' : 'ghost small'"
            :aria-pressed="range === item.value"
            @click="range = item.value"
          >
            {{ item.label }}
          </button>
        </div>
      </div>
    </header>

    <p v-if="loading" class="loading-note">正在加载用量…</p>
    <div v-else-if="error" class="load-error usage-error" role="alert">{{ error }}</div>
    <p v-else-if="needsConversation" class="empty-note">匿名用量仅显示当前会话，请先开始一次问答。</p>

    <template v-else-if="summary">
      <div class="usage-cards">
        <article class="usage-card">
          <span class="usage-label">{{ range === 'month' ? '本月合计' : '区间合计' }}</span>
          <strong class="usage-total-cost">{{ money(summary.totals.cost) }}</strong>
          <span class="usage-meta">
            {{ tokenCount(summary.totals.totalTokens) }} tokens · {{ summary.totals.calls }} 次调用
          </span>
        </article>
        <article class="usage-card usage-forecast">
          <span class="usage-label">本月预测</span>
          <strong class="usage-predicted-cost">{{ money(summary.forecast.predictedMonthCost) }}</strong>
          <span class="usage-meta">
            已用 {{ money(summary.forecast.monthToDateCost) }} · 最近 {{ summary.forecast.windowDays }} 个自然日日均
            {{ money(summary.forecast.dailyAverageCost) }} · 剩余 {{ summary.forecast.remainingDays }} 天
          </span>
          <p class="usage-formula">{{ summary.forecast.formula }}</p>
        </article>
      </div>

      <p v-if="summary.totals.missingUsageCount > 0" class="usage-missing" role="status">
        {{ summary.totals.missingUsageCount }} 次调用缺失用量，token 与费用未计入（不按 0 处理）
      </p>

      <section v-if="summary.groups.length > 0" class="usage-groups">
        <h2>{{ groupTitle }}</h2>
        <ul>
          <li v-for="group in summary.groups" :key="group.key" class="usage-group-row">
            <span class="usage-group-label">{{ group.label }}</span>
            <span class="usage-group-cost">{{ money(group.cost) }}</span>
            <span class="usage-group-meta">
              {{ tokenCount(group.totalTokens) }} tokens · {{ group.calls }} 次
              <template v-if="group.missingUsageCount > 0"> · {{ group.missingUsageCount }} 次缺失</template>
            </span>
          </li>
        </ul>
      </section>
      <p v-else class="empty-note">该范围内暂无用量记录。</p>
    </template>
  </section>
</template>

<style scoped>
.usage-view {
  width: 100%;
  max-width: 780px;
  margin: 0 auto;
  padding: 24px 20px 60px;
  overflow-y: auto;
}

.usage-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.usage-head h1 {
  margin: 0;
  font-size: 20px;
}

.usage-sub {
  margin: 6px 0 0;
  color: var(--muted);
  font-size: 12.5px;
}

.usage-head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.usage-back {
  text-decoration: none;
}

.usage-ranges {
  display: flex;
  gap: 6px;
}

.usage-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 14px;
  margin-top: 20px;
}

.usage-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 16px 18px;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: var(--surface);
}

.usage-label {
  font-size: 12.5px;
  color: var(--muted);
}

.usage-card strong {
  font-size: 24px;
  font-variant-numeric: tabular-nums;
}

.usage-meta {
  font-size: 12.5px;
  color: var(--muted);
}

.usage-formula {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.5;
}

.usage-missing {
  margin: 14px 0 0;
  padding: 10px 14px;
  border-radius: 12px;
  background: #fff8e6;
  border: 1px solid #f2dfae;
  color: #7a5a00;
  font-size: 13px;
}

.usage-groups {
  margin-top: 24px;
}

.usage-groups h2 {
  font-size: 15px;
  margin: 0 0 10px;
}

.usage-groups ul {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.usage-group-row {
  display: grid;
  grid-template-columns: minmax(120px, 1fr) auto;
  gap: 4px 14px;
  padding: 10px 14px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
  font-size: 13.5px;
}

.usage-group-label {
  font-weight: 600;
}

.usage-group-cost {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.usage-group-meta {
  grid-column: 1 / -1;
  color: var(--muted);
  font-size: 12.5px;
}

@media (max-width: 520px) {
  .usage-view {
    padding: 16px 12px 40px;
  }

  .usage-head {
    gap: 8px;
  }

  .usage-head h1 {
    font-size: 18px;
  }

  .usage-sub {
    font-size: 12px;
  }

  .usage-cards {
    margin-top: 14px;
  }

  .usage-card {
    padding: 14px;
  }

  .usage-card strong {
    font-size: 20px;
  }
}
</style>
