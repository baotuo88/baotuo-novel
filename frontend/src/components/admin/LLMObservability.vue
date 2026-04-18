<!-- AIMETA P=LLM观测面板_调用日志与成本估算|R=日志查询_聚合统计_趋势榜单_CSV导出|NR=不含业务写入|E=component:LLMObservability|X=ui|A=观测组件|D=vue,naive-ui|S=dom,net|RD=./README.ai -->
<template>
  <n-card :bordered="false" class="admin-card">
    <template #header>
      <div class="card-header">
        <span class="card-title">LLM 观测</span>
        <n-space :size="8">
          <n-button quaternary size="small" @click="resetFilters" :disabled="loading || exporting">重置</n-button>
          <n-button quaternary size="small" @click="exportCsv" :loading="exporting" :disabled="loading">导出 CSV</n-button>
          <n-button type="primary" size="small" @click="fetchData" :loading="loading">刷新</n-button>
        </n-space>
      </div>
    </template>

    <n-space vertical size="large">
      <n-alert v-if="error" type="error" closable @close="error = null">
        {{ error }}
      </n-alert>

      <n-grid :cols="gridCols" :x-gap="12" :y-gap="12">
        <n-gi>
          <n-select v-model:value="filters.hours" :options="hoursOptions" />
        </n-gi>
        <n-gi>
          <n-select v-model:value="filters.status_filter" :options="statusOptions" />
        </n-gi>
        <n-gi>
          <n-select v-model:value="filters.request_type" :options="requestTypeOptions" />
        </n-gi>
        <n-gi>
          <n-input
            v-model:value="filters.model"
            clearable
            placeholder="按模型精确筛选（可空）"
            @keyup.enter="fetchData"
          />
        </n-gi>
        <n-gi>
          <n-input
            v-model:value="filters.project_id"
            clearable
            placeholder="按项目ID筛选（可空）"
            @keyup.enter="fetchData"
          />
        </n-gi>
      </n-grid>

      <n-spin :show="loading">
        <n-tabs v-model:value="activeSection" type="line" animated class="obs-tabs">
          <n-tab-pane name="overview" tab="概览" />
          <n-tab-pane name="queue" tab="队列" />
          <n-tab-pane name="trend" tab="趋势" />
          <n-tab-pane name="logs" tab="明细" />
        </n-tabs>

        <div v-show="activeSection === 'overview'" class="obs-section">
        <n-grid :cols="summaryGridCols" :x-gap="12" :y-gap="12">
          <n-gi>
            <n-card :bordered="false" class="stat-card">
              <n-statistic label="总调用数" :value="summary?.total_calls ?? 0" />
            </n-card>
          </n-gi>
          <n-gi>
            <n-card :bordered="false" class="stat-card">
              <n-statistic label="成功率" :value="summary?.success_rate ?? 0">
                <template #suffix>%</template>
              </n-statistic>
            </n-card>
          </n-gi>
          <n-gi>
            <n-card :bordered="false" class="stat-card">
              <n-statistic label="平均时延" :value="summary?.avg_latency_ms ?? 0">
                <template #suffix>ms</template>
              </n-statistic>
            </n-card>
          </n-gi>
          <n-gi>
            <n-card :bordered="false" class="stat-card">
              <n-statistic label="估算成本" :value="summary?.total_estimated_cost_usd ?? 0">
                <template #prefix>$</template>
              </n-statistic>
            </n-card>
          </n-gi>
        </n-grid>

        <n-grid :cols="trendGridCols" :x-gap="12" :y-gap="12" class="section-grid">
          <n-gi>
            <n-card :bordered="false" size="small" class="section-card">
              <template #header>
                <div class="section-title">预算预警中心</div>
              </template>
              <n-space vertical size="small">
                <div class="budget-meta">
                  阈值：预警 ≥ {{ formatPercent(budgetAlerts?.warning_threshold ?? 0.5) }}，
                  严重 ≥ {{ formatPercent(budgetAlerts?.critical_threshold ?? 0.8) }}
                </div>
                <n-empty
                  v-if="!budgetAlerts?.global_alert && !budgetAlerts?.users?.length && !budgetAlerts?.projects?.length"
                  description="当前暂无预算预警"
                />
                <div v-else class="budget-global-row">
                  <n-tag
                    v-if="budgetAlerts?.global_alert"
                    :type="budgetLevelType(budgetAlerts.global_alert.level)"
                    bordered
                    size="small"
                  >
                    全局：{{ budgetLevelLabel(budgetAlerts.global_alert.level) }}
                  </n-tag>
                  <span v-if="budgetAlerts?.global_alert">
                    ${{ formatMoney(budgetAlerts.global_alert.spent_usd) }} /
                    ${{ formatMoney(budgetAlerts.global_alert.limit_usd) }}
                    ({{ formatPercent(budgetAlerts.global_alert.usage_ratio) }})
                  </span>
                </div>
              </n-space>
            </n-card>
          </n-gi>
          <n-gi>
            <n-card :bordered="false" size="small" class="section-card">
              <template #header>
                <div class="section-title">写作任务概览</div>
              </template>
              <n-space vertical size="small">
                <div class="budget-meta">
                  当前筛选：{{ taskStatusGroupOptionsLabel }} / 项目 {{ filters.project_id || '全部' }} / 用户
                  {{ queueUserId == null ? '全部' : queueUserId }}
                </div>
                <div class="queue-summary-row">
                  <n-tag size="small" type="warning" bordered>
                    总任务 {{ queueVisibleTotal }}
                  </n-tag>
                  <n-tag size="small" type="info" bordered>
                    排队 {{ taskQueue?.summary?.queued_count ?? 0 }}
                  </n-tag>
                  <n-tag size="small" type="warning" bordered>
                    运行中 {{ taskQueue?.summary?.running_count ?? 0 }}
                  </n-tag>
                  <n-tag size="small" type="error" bordered>
                    卡住 {{ taskQueue?.summary?.stale_running_count ?? 0 }}
                  </n-tag>
                  <n-tag size="small" type="error" bordered>
                    失败 {{ taskQueue?.summary?.failed_count ?? 0 }}
                  </n-tag>
                  <n-tag size="small" type="default" bordered>
                    已完成 {{ taskQueue?.summary?.completed_count ?? 0 }}
                  </n-tag>
                  <n-tag size="small" type="default" bordered>
                    心跳阈值 {{ heartbeatTimeoutMinutes }} 分钟
                  </n-tag>
                  <n-tag size="small" type="default" bordered>
                    {{ taskQueue?.summary?.recent_window_hours ?? 24 }}h 完成 {{ taskQueue?.summary?.recent_finished_count ?? 0 }}
                  </n-tag>
                  <n-tag
                    size="small"
                    bordered
                    :type="queueFailureRateType(taskQueue?.summary?.recent_failure_rate_percent)"
                  >
                    失败率 {{ Number(taskQueue?.summary?.recent_failure_rate_percent ?? 0).toFixed(2) }}%
                  </n-tag>
                  <n-tag size="small" type="default" bordered>
                    平均耗时 {{ formatDurationSeconds(taskQueue?.summary?.recent_avg_duration_seconds) }}
                  </n-tag>
                  <n-tag size="small" type="default" bordered>
                    P95 {{ formatDurationSeconds(taskQueue?.summary?.recent_p95_duration_seconds) }}
                  </n-tag>
                </div>
              </n-space>
            </n-card>
          </n-gi>
        </n-grid>

        <n-grid :cols="trendGridCols" :x-gap="12" :y-gap="12" class="section-grid">
          <n-gi>
            <n-card :bordered="false" size="small" class="section-card">
              <template #header>
                <div class="section-title">用户预算告警 Top</div>
              </template>
              <n-empty v-if="!budgetAlerts?.users?.length" description="暂无用户预算告警" />
              <n-data-table
                v-else
                :columns="budgetUserColumns"
                :data="budgetAlerts?.users || []"
                :pagination="{ pageSize: 8 }"
                :bordered="false"
                size="small"
              />
            </n-card>
          </n-gi>
          <n-gi>
            <n-card :bordered="false" size="small" class="section-card">
              <template #header>
                <div class="section-title">项目预算告警 Top</div>
              </template>
              <n-empty v-if="!budgetAlerts?.projects?.length" description="暂无项目预算告警" />
              <n-data-table
                v-else
                :columns="budgetProjectColumns"
                :data="budgetAlerts?.projects || []"
                :pagination="{ pageSize: 8 }"
                :bordered="false"
                size="small"
              />
            </n-card>
          </n-gi>
        </n-grid>
        </div>

        <div v-show="activeSection === 'queue'" class="obs-section">
        <n-card :bordered="false" size="small" class="section-card">
          <template #header>
            <div class="card-header">
              <div class="section-title">写作任务队列</div>
              <n-space :size="8">
                <n-select
                  v-model:value="taskStatusGroup"
                  :options="taskStatusOptions"
                  size="small"
                  style="width: 140px"
                />
                <n-input-number
                  v-model:value="queueUserId"
                  clearable
                  :min="1"
                  :precision="0"
                  size="small"
                  style="width: 120px"
                  placeholder="用户ID"
                />
                <n-input-number
                  v-model:value="staleThresholdMinutes"
                  :min="1"
                  :precision="0"
                  size="small"
                  style="width: 130px"
                  placeholder="卡住阈值(分)"
                />
                <n-space align="center" :size="4">
                  <span class="queue-control-label">仅卡住</span>
                  <n-switch v-model:value="queueOnlyStale" size="small" />
                </n-space>
                <n-button quaternary size="small" @click="fetchQueueOnly" :loading="queueLoading">
                  刷新队列
                </n-button>
              </n-space>
            </div>
          </template>
          <n-empty v-if="!queueRows.length" description="暂无匹配任务" />
          <n-data-table
            v-else
            :columns="queueColumns"
            :data="queueRows"
            :pagination="{ pageSize: 12 }"
            :bordered="false"
            size="small"
            :row-class-name="queueRowClassName"
          />
        </n-card>
        <n-card :bordered="false" size="small" class="section-card">
          <template #header>
            <div class="section-title">失败原因 Top</div>
          </template>
          <n-empty v-if="!(taskQueue?.failure_top?.length)" description="暂无失败记录" />
          <n-data-table
            v-else
            :columns="queueFailureColumns"
            :data="taskQueue?.failure_top || []"
            :pagination="{ pageSize: 8 }"
            :bordered="false"
            size="small"
          />
        </n-card>
        </div>

        <div v-show="activeSection === 'trend'" class="obs-section">
        <n-grid :cols="trendGridCols" :x-gap="12" :y-gap="12" class="section-grid">
          <n-gi>
            <n-card :bordered="false" size="small" class="section-card">
              <template #header>
                <div class="section-title">按模型小时趋势（Top5）</div>
              </template>
              <n-empty v-if="!modelTrendRows.length" description="暂无模型趋势数据" />
              <template v-else>
                <div class="chart-wrap">
                  <canvas ref="modelTrendCanvas" class="trend-chart"></canvas>
                </div>
                <n-data-table
                  :columns="modelTrendColumns"
                  :data="modelTrendRows"
                  :pagination="false"
                  :bordered="false"
                  size="small"
                />
              </template>
            </n-card>
          </n-gi>

          <n-gi>
            <n-card :bordered="false" size="small" class="section-card">
              <template #header>
                <div class="section-title">按用户小时趋势（Top5）</div>
              </template>
              <n-empty v-if="!userTrendRows.length" description="暂无用户趋势数据" />
              <template v-else>
                <div class="chart-wrap">
                  <canvas ref="userTrendCanvas" class="trend-chart"></canvas>
                </div>
                <n-data-table
                  :columns="userTrendColumns"
                  :data="userTrendRows"
                  :pagination="false"
                  :bordered="false"
                  size="small"
                />
              </template>
            </n-card>
          </n-gi>
        </n-grid>

        <n-card :bordered="false" size="small" class="section-card">
          <template #header>
            <div class="section-title">错误 TopN</div>
          </template>
          <n-empty v-if="!errorTop.length" description="当前筛选条件下没有错误记录" />
          <n-data-table
            v-else
            :columns="errorColumns"
            :data="errorTop"
            :pagination="{ pageSize: 12 }"
            :bordered="false"
            size="small"
          />
        </n-card>
        </div>

        <div v-show="activeSection === 'logs'" class="obs-section">
        <n-card :bordered="false" size="small" class="section-card">
          <template #header>
            <div class="section-title">调用明细（最新 100 条）</div>
          </template>
          <n-data-table
            :columns="logColumns"
            :data="logs"
            :pagination="{ pageSize: 20 }"
            :bordered="false"
            size="small"
            class="log-table"
          />
        </n-card>
        </div>
      </n-spin>
    </n-space>
  </n-card>
</template>

<script setup lang="ts">
import { computed, h, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import Chart from 'chart.js/auto'
import type { Chart as ChartInstance, ChartDataset } from 'chart.js'
import { useRouter } from 'vue-router'
import {
  NAlert,
  NButton,
  NCard,
  NDataTable,
  NEmpty,
  NGi,
  NGrid,
  NInput,
  NInputNumber,
  NSelect,
  NSpace,
  NSpin,
  NStatistic,
  NSwitch,
  NTabPane,
  NTabs,
  NTag,
  type DataTableColumns
} from 'naive-ui'

import {
  AdminAPI,
  type LLMBudgetAlertItem,
  type LLMBudgetAlertResponse,
  type LLMCallLog,
  type LLMCallSummary,
  type LLMErrorTopItem,
  type LLMGroupedTrendResponse,
  type WriterTaskFailureTopItem,
  type WriterTaskQueueItem,
  type WriterTaskQueueResponse
} from '@/api/admin'
import { useAlert } from '@/composables/useAlert'

interface TrendRow {
  row_key: string
  series_key: string
  total_calls: number
  [key: string]: string | number
}

const { showAlert } = useAlert()
const router = useRouter()

const loading = ref(false)
const exporting = ref(false)
const error = ref<string | null>(null)
const activeSection = ref<'overview' | 'queue' | 'trend' | 'logs'>('overview')
const logs = ref<LLMCallLog[]>([])
const summary = ref<LLMCallSummary | null>(null)
const trendByModel = ref<LLMGroupedTrendResponse | null>(null)
const trendByUser = ref<LLMGroupedTrendResponse | null>(null)
const errorTop = ref<LLMErrorTopItem[]>([])
const budgetAlerts = ref<LLMBudgetAlertResponse | null>(null)
const taskQueue = ref<WriterTaskQueueResponse | null>(null)
const queueLoading = ref(false)
const isMobile = ref(false)
const modelTrendCanvas = ref<HTMLCanvasElement | null>(null)
const userTrendCanvas = ref<HTMLCanvasElement | null>(null)
const taskStatusGroup = ref<'active' | 'failed' | 'all'>('active')
const queueUserId = ref<number | null>(null)
const staleThresholdMinutes = ref<number>(30)
const queueOnlyStale = ref(false)
const retryingChapterMap = ref<Record<number, boolean>>({})

const filters = reactive({
  hours: 24,
  status_filter: '',
  request_type: '',
  model: '',
  project_id: ''
})

const hoursOptions = [
  { label: '近 6 小时', value: 6 },
  { label: '近 24 小时', value: 24 },
  { label: '近 72 小时', value: 72 },
  { label: '近 7 天', value: 168 }
]

const statusOptions = [
  { label: '全部状态', value: '' },
  { label: '成功', value: 'success' },
  { label: '失败', value: 'error' }
]

const requestTypeOptions = [
  { label: '全部类型', value: '' },
  { label: '对话生成', value: 'chat' },
  { label: '摘要生成', value: 'summary' },
  { label: '向量生成', value: 'embedding' }
]

const updateLayout = () => {
  isMobile.value = window.innerWidth < 992
}

const gridCols = computed(() => (isMobile.value ? 1 : 5))
const summaryGridCols = computed(() => (isMobile.value ? 1 : 4))
const trendGridCols = computed(() => (isMobile.value ? 1 : 2))

const taskStatusOptions = [
  { label: '活跃任务', value: 'active' },
  { label: '失败任务', value: 'failed' },
  { label: '全部任务', value: 'all' }
]

const taskStatusGroupOptionsLabel = computed(() => {
  const found = taskStatusOptions.find((item) => item.value === taskStatusGroup.value)
  return found ? found.label : taskStatusGroup.value
})

const formatDateTime = (value: string) => {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

const formatMoney = (value?: number | null) => {
  if (value == null) return '--'
  return Number(value).toFixed(6)
}

const formatPercent = (value?: number | null) => {
  if (value == null) return '--'
  return `${(Number(value) * 100).toFixed(2)}%`
}

const budgetLevelLabel = (level: string) => {
  if (level === 'exceeded') return '超限'
  if (level === 'critical') return '严重'
  if (level === 'warning') return '预警'
  return '正常'
}

const budgetLevelType = (level: string): 'success' | 'warning' | 'error' | 'default' => {
  if (level === 'exceeded') return 'error'
  if (level === 'critical') return 'error'
  if (level === 'warning') return 'warning'
  if (level === 'ok') return 'success'
  return 'default'
}

const queueStateType = (state: string): 'success' | 'warning' | 'error' | 'default' => {
  if (state === 'active') return 'warning'
  if (state === 'failed') return 'error'
  if (state === 'done') return 'success'
  return 'default'
}

const queueStateLabel = (state: string) => {
  if (state === 'active') return '进行中'
  if (state === 'failed') return '失败'
  if (state === 'done') return '完成'
  return '其他'
}

const taskTypeLabel = (taskType: string) => {
  if (taskType === 'chapter_generation') return '章节生成'
  if (taskType === 'blueprint_generation') return '蓝图生成'
  return taskType
}

const formatHeartbeatAge = (seconds?: number | null) => {
  if (seconds == null) return '--'
  const total = Math.max(0, Number(seconds))
  if (!Number.isFinite(total)) return '--'
  if (total < 60) return `${Math.floor(total)}s`
  return `${Math.floor(total / 60)}m`
}

const formatDurationSeconds = (seconds?: number | null) => {
  if (seconds == null) return '--'
  const total = Math.max(0, Number(seconds))
  if (!Number.isFinite(total)) return '--'
  if (total < 60) return `${total.toFixed(1)}s`
  if (total < 3600) return `${(total / 60).toFixed(1)}m`
  return `${(total / 3600).toFixed(2)}h`
}

const queueFailureRateType = (failureRate?: number | null): 'success' | 'warning' | 'error' | 'default' => {
  const value = Number(failureRate || 0)
  if (!Number.isFinite(value)) return 'default'
  if (value >= 20) return 'error'
  if (value >= 8) return 'warning'
  return 'success'
}

const normalizedStaleThreshold = computed(() => {
  const value = Number(staleThresholdMinutes.value || 0)
  if (!Number.isFinite(value) || value < 1) return 1
  return Math.trunc(value)
})

const heartbeatTimeoutMinutes = computed(() => {
  const seconds = Number(taskQueue.value?.heartbeat_timeout_seconds || 0)
  if (!Number.isFinite(seconds) || seconds <= 0) return 0
  return Math.max(1, Math.ceil(seconds / 60))
})

const normalizedStaleThresholdSeconds = computed(() => normalizedStaleThreshold.value * 60)

const isQueueStale = (row: WriterTaskQueueItem) => {
  if (row.status !== 'running') return false
  const heartbeatAgeSeconds = Number(row.heartbeat_age_seconds || 0)
  return heartbeatAgeSeconds >= normalizedStaleThresholdSeconds.value
}

const queueRows = computed<WriterTaskQueueItem[]>(() => {
  let rows = taskQueue.value?.items || []
  if (queueUserId.value != null) {
    rows = rows.filter((item) => item.owner_user_id === queueUserId.value)
  }
  if (queueOnlyStale.value) {
    rows = rows.filter((item) => isQueueStale(item))
  }
  return rows
})

const queueVisibleTotal = computed(() => queueRows.value.length)

const canRetryQueueRow = (row: WriterTaskQueueItem) => (
  row.queue_state === 'failed'
  && row.task_type === 'chapter_generation'
  && row.chapter_id != null
)

const isRetryingChapter = (chapterId?: number | null) => {
  if (chapterId == null) return false
  return Boolean(retryingChapterMap.value[chapterId])
}

const jumpToTaskChapter = (row: WriterTaskQueueItem) => {
  if (row.chapter_number == null) {
    showAlert('蓝图任务暂无章节定位', 'info')
    return
  }
  router.push({
    name: 'admin-novel-detail',
    params: { id: row.project_id },
    query: {
      section: 'chapters',
      chapter: String(row.chapter_number)
    }
  })
}

const queueRowClassName = (row: WriterTaskQueueItem) => (isQueueStale(row) ? 'queue-stale-row' : '')

const retryQueueTask = async (row: WriterTaskQueueItem) => {
  if (!canRetryQueueRow(row)) {
    showAlert('仅失败的章节生成任务支持直接重试', 'info')
    return
  }
  const chapterId = Number(row.chapter_id)
  if (isRetryingChapter(chapterId)) {
    return
  }

  retryingChapterMap.value = { ...retryingChapterMap.value, [chapterId]: true }
  try {
    const result = await AdminAPI.retryWriterTask({
      chapter_id: chapterId,
      retry_mode: 'auto'
    })
    showAlert(result.message || '重试任务已投递', 'success')
    await fetchQueueOnly()
  } catch (err) {
    showAlert(err instanceof Error ? err.message : '重试任务投递失败', 'error')
  } finally {
    const nextMap = { ...retryingChapterMap.value }
    delete nextMap[chapterId]
    retryingChapterMap.value = nextMap
  }
}

const maxTrendBuckets = 10
const modelTrendBuckets = computed(() => trendByModel.value?.buckets.slice(-maxTrendBuckets) ?? [])
const userTrendBuckets = computed(() => trendByUser.value?.buckets.slice(-maxTrendBuckets) ?? [])

const buildTrendRows = (trend: LLMGroupedTrendResponse | null, buckets: string[]): TrendRow[] => {
  if (!trend) return []
  const startIndex = Math.max(0, trend.buckets.length - buckets.length)
  return trend.series.map((item) => {
    const row: TrendRow = {
      row_key: item.key,
      series_key: item.key,
      total_calls: item.total_calls
    }
    buckets.forEach((bucket, idx) => {
      row[bucket] = item.points[startIndex + idx] ?? 0
    })
    return row
  })
}

const modelTrendRows = computed(() => buildTrendRows(trendByModel.value, modelTrendBuckets.value))
const userTrendRows = computed(() => buildTrendRows(trendByUser.value, userTrendBuckets.value))

const trendPalette = ['#10b981', '#3b82f6', '#ef4444', '#8b5cf6', '#f59e0b']
let modelTrendChart: ChartInstance<'line'> | null = null
let userTrendChart: ChartInstance<'line'> | null = null

const formatUserKey = (value: string) => {
  if (value === 'anonymous') return '匿名'
  if (value.startsWith('user:')) return `用户 ${value.slice(5)}`
  return value
}

const destroyTrendCharts = () => {
  if (modelTrendChart) {
    modelTrendChart.destroy()
    modelTrendChart = null
  }
  if (userTrendChart) {
    userTrendChart.destroy()
    userTrendChart = null
  }
}

const createTrendDatasets = (
  trend: LLMGroupedTrendResponse,
  labelFormatter?: (label: string) => string
): ChartDataset<'line', number[]>[] => {
  return trend.series.map((series, index) => {
    const color = trendPalette[index % trendPalette.length]
    return {
      label: labelFormatter ? labelFormatter(series.key) : series.key,
      data: series.points,
      borderColor: color,
      backgroundColor: `${color}33`,
      tension: 0.35,
      borderWidth: 2,
      fill: false,
      pointRadius: 2,
      pointHoverRadius: 4
    }
  })
}

const renderTrendChart = (
  canvas: HTMLCanvasElement | null,
  chartRef: ChartInstance<'line'> | null,
  trend: LLMGroupedTrendResponse | null,
  labelFormatter?: (label: string) => string
): ChartInstance<'line'> | null => {
  if (!canvas || !trend || !trend.series.length || !trend.buckets.length) {
    if (chartRef) {
      chartRef.destroy()
    }
    return null
  }

  const labels = trend.buckets.map((bucket) => bucket.slice(6))
  const datasets = createTrendDatasets(trend, labelFormatter)

  if (chartRef) {
    chartRef.data.labels = labels
    chartRef.data.datasets = datasets
    chartRef.update()
    return chartRef
  }

  const ctx = canvas.getContext('2d')
  if (!ctx) return null

  return new Chart(ctx, {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: 'index',
        intersect: false
      },
      scales: {
        x: {
          grid: {
            color: 'rgba(148, 163, 184, 0.15)'
          }
        },
        y: {
          beginAtZero: true,
          ticks: {
            precision: 0
          },
          grid: {
            color: 'rgba(148, 163, 184, 0.15)'
          }
        }
      },
      plugins: {
        legend: {
          position: 'top',
          align: 'start'
        },
        tooltip: {
          callbacks: {
            label: (context) => `${context.dataset.label}: ${context.parsed.y} 次`
          }
        }
      }
    }
  }) as ChartInstance<'line'>
}

const refreshTrendCharts = async () => {
  await nextTick()
  modelTrendChart = renderTrendChart(
    modelTrendCanvas.value,
    modelTrendChart,
    trendByModel.value
  )
  userTrendChart = renderTrendChart(
    userTrendCanvas.value,
    userTrendChart,
    trendByUser.value,
    formatUserKey
  )
}

const modelTrendColumns = computed<DataTableColumns<TrendRow>>(() => {
  const columns: DataTableColumns<TrendRow> = [
    {
      title: '模型',
      key: 'series_key',
      width: 180,
      ellipsis: { tooltip: true }
    },
    {
      title: '总调用',
      key: 'total_calls',
      width: 90,
      align: 'center'
    }
  ]

  modelTrendBuckets.value.forEach((bucket) => {
    columns.push({
      title: bucket.slice(6),
      key: bucket,
      width: 84,
      align: 'center'
    })
  })

  return columns
})

const userTrendColumns = computed<DataTableColumns<TrendRow>>(() => {
  const columns: DataTableColumns<TrendRow> = [
    {
      title: '用户',
      key: 'series_key',
      width: 120,
      render: (row) => formatUserKey(String(row.series_key))
    },
    {
      title: '总调用',
      key: 'total_calls',
      width: 90,
      align: 'center'
    }
  ]

  userTrendBuckets.value.forEach((bucket) => {
    columns.push({
      title: bucket.slice(6),
      key: bucket,
      width: 84,
      align: 'center'
    })
  })

  return columns
})

const errorColumns: DataTableColumns<LLMErrorTopItem> = [
  {
    title: '错误类型',
    key: 'error_type',
    width: 140
  },
  {
    title: '次数',
    key: 'count',
    width: 80,
    align: 'center'
  },
  {
    title: '最近出现',
    key: 'latest_at',
    width: 170,
    render: (row) => formatDateTime(row.latest_at)
  },
  {
    title: '示例信息',
    key: 'sample_message',
    minWidth: 260,
    ellipsis: { tooltip: true }
  }
]

const logColumns: DataTableColumns<LLMCallLog> = [
  {
    title: '时间',
    key: 'created_at',
    width: 170,
    render: (row) => formatDateTime(row.created_at)
  },
  {
    title: '状态',
    key: 'status',
    width: 90,
    render: (row) =>
      h(
        NTag,
        { type: row.status === 'success' ? 'success' : 'error', bordered: false, size: 'small' },
        { default: () => (row.status === 'success' ? '成功' : '失败') }
      )
  },
  {
    title: '用户',
    key: 'user_id',
    width: 90,
    align: 'center',
    render: (row) => (row.user_id == null ? '-' : row.user_id)
  },
  {
    title: '项目',
    key: 'project_id',
    width: 120,
    ellipsis: { tooltip: true },
    render: (row) => row.project_id || '-'
  },
  { title: '类型', key: 'request_type', width: 90 },
  { title: '模型', key: 'model', width: 180, ellipsis: { tooltip: true } },
  { title: '提供方', key: 'provider', width: 120 },
  {
    title: '时延(ms)',
    key: 'latency_ms',
    width: 100,
    render: (row) => row.latency_ms ?? '--'
  },
  { title: '输入Token(估)', key: 'estimated_input_tokens', width: 130 },
  { title: '输出Token(估)', key: 'estimated_output_tokens', width: 130 },
  {
    title: '成本(USD 估)',
    key: 'estimated_cost_usd',
    width: 130,
    render: (row) => formatMoney(row.estimated_cost_usd)
  },
  {
    title: '错误信息',
    key: 'error_message',
    minWidth: 260,
    ellipsis: { tooltip: true },
    render: (row) => row.error_message || '--'
  }
]

const budgetUserColumns: DataTableColumns<LLMBudgetAlertItem> = [
  {
    title: '用户',
    key: 'scope_label',
    minWidth: 120,
    ellipsis: { tooltip: true }
  },
  {
    title: '使用率',
    key: 'usage_ratio',
    width: 90,
    render: (row) => formatPercent(row.usage_ratio)
  },
  {
    title: '已用/限额',
    key: 'spent',
    width: 180,
    render: (row) => `$${formatMoney(row.spent_usd)} / $${formatMoney(row.limit_usd)}`
  },
  {
    title: '等级',
    key: 'level',
    width: 90,
    render: (row) =>
      h(
        NTag,
        { type: budgetLevelType(row.level), bordered: false, size: 'small' },
        { default: () => budgetLevelLabel(row.level) }
      )
  }
]

const budgetProjectColumns: DataTableColumns<LLMBudgetAlertItem> = [
  {
    title: '项目',
    key: 'scope_label',
    minWidth: 180,
    ellipsis: { tooltip: true }
  },
  {
    title: '使用率',
    key: 'usage_ratio',
    width: 90,
    render: (row) => formatPercent(row.usage_ratio)
  },
  {
    title: '已用/限额',
    key: 'spent',
    width: 180,
    render: (row) => `$${formatMoney(row.spent_usd)} / $${formatMoney(row.limit_usd)}`
  },
  {
    title: '等级',
    key: 'level',
    width: 90,
    render: (row) =>
      h(
        NTag,
        { type: budgetLevelType(row.level), bordered: false, size: 'small' },
        { default: () => budgetLevelLabel(row.level) }
      )
  }
]

const queueColumns: DataTableColumns<WriterTaskQueueItem> = [
  {
    title: '状态',
    key: 'queue_state',
    width: 90,
    render: (row) =>
      h(
        NTag,
        { type: queueStateType(row.queue_state), bordered: false, size: 'small' },
        { default: () => queueStateLabel(row.queue_state) }
      )
  },
  {
    title: '任务类型',
    key: 'task_type',
    width: 110,
    render: (row) => taskTypeLabel(row.task_type)
  },
  {
    title: '流程状态',
    key: 'status',
    width: 120
  },
  {
    title: '项目',
    key: 'project_title',
    minWidth: 180,
    ellipsis: { tooltip: true }
  },
  {
    title: '章节',
    key: 'chapter_number',
    width: 90,
    render: (row) => (row.chapter_number == null ? '-' : `第${row.chapter_number}章`)
  },
  {
    title: '阶段',
    key: 'stage_label',
    width: 120,
    ellipsis: { tooltip: true },
    render: (row) => row.stage_label || '-'
  },
  {
    title: '进度',
    key: 'progress_percent',
    width: 88,
    align: 'center',
    render: (row) => `${row.progress_percent}%`
  },
  {
    title: '用户',
    key: 'owner_username',
    width: 100,
    render: (row) => row.owner_username || row.owner_user_id
  },
  {
    title: '心跳',
    key: 'heartbeat_age_seconds',
    width: 96,
    align: 'center',
    render: (row) =>
      row.status !== 'running'
        ? '-'
        : isQueueStale(row)
          ? h(
              NTag,
              { type: 'error', bordered: false, size: 'small' },
              { default: () => `卡住 ${formatHeartbeatAge(row.heartbeat_age_seconds)}` }
            )
          : formatHeartbeatAge(row.heartbeat_age_seconds)
  },
  {
    title: '运行(分钟)',
    key: 'age_minutes',
    width: 100
  },
  {
    title: '更新时间',
    key: 'updated_at',
    width: 168,
    render: (row) => formatDateTime(row.updated_at)
  },
  {
    title: '操作',
    key: 'actions',
    width: 164,
    align: 'center',
    render: (row) =>
      h(
        NSpace,
        { size: 6, justify: 'center' },
        {
          default: () => [
            h(
              NButton,
              {
                size: 'tiny',
                tertiary: true,
                type: 'primary',
                disabled: row.chapter_number == null,
                onClick: () => jumpToTaskChapter(row)
              },
              { default: () => '定位' }
            ),
            h(
              NButton,
              {
                size: 'tiny',
                tertiary: true,
                type: canRetryQueueRow(row) ? 'warning' : 'default',
                disabled: !canRetryQueueRow(row),
                loading: isRetryingChapter(row.chapter_id),
                onClick: () => retryQueueTask(row)
              },
              { default: () => '重试' }
            )
          ]
        }
      )
  }
]

const queueFailureColumns: DataTableColumns<WriterTaskFailureTopItem> = [
  {
    title: '次数',
    key: 'count',
    width: 72,
    align: 'center'
  },
  {
    title: '错误摘要',
    key: 'error_key',
    width: 260,
    ellipsis: { tooltip: true }
  },
  {
    title: '示例信息',
    key: 'sample_message',
    minWidth: 320,
    ellipsis: { tooltip: true }
  }
]

const fetchQueueOnly = async () => {
  queueLoading.value = true
  try {
    taskQueue.value = await AdminAPI.getWriterTaskQueue({
      limit: 80,
      status_group: taskStatusGroup.value,
      project_id: filters.project_id || undefined,
      user_id: queueUserId.value ?? undefined
    })
  } catch (err) {
    showAlert(err instanceof Error ? err.message : '加载任务队列失败', 'error')
  } finally {
    queueLoading.value = false
  }
}

const fetchData = async () => {
  loading.value = true
  error.value = null
  try {
    const [summaryData, logsData, modelTrend, userTrend, errorTopData, budgetData, queueData] = await Promise.all([
      AdminAPI.getLLMCallSummary(
        filters.hours,
        filters.status_filter || undefined,
        filters.request_type || undefined,
        filters.model || undefined,
        undefined,
        filters.project_id || undefined
      ),
      AdminAPI.listLLMCallLogs({
        limit: 100,
        hours: filters.hours,
        status_filter: filters.status_filter || undefined,
        request_type: filters.request_type || undefined,
        model: filters.model || undefined,
        project_id: filters.project_id || undefined
      }),
      AdminAPI.getLLMHourlyGroupedTrend({
        hours: filters.hours,
        group_by: 'model',
        limit: 5,
        status_filter: filters.status_filter || undefined,
        request_type: filters.request_type || undefined,
        model: filters.model || undefined,
        project_id: filters.project_id || undefined
      }),
      AdminAPI.getLLMHourlyGroupedTrend({
        hours: filters.hours,
        group_by: 'user',
        limit: 5,
        status_filter: filters.status_filter || undefined,
        request_type: filters.request_type || undefined,
        model: filters.model || undefined,
        project_id: filters.project_id || undefined
      }),
      AdminAPI.getLLMErrorTop({
        hours: filters.hours,
        limit: 10,
        request_type: filters.request_type || undefined,
        model: filters.model || undefined,
        project_id: filters.project_id || undefined
      }),
      AdminAPI.getLLMBudgetAlerts({
        limit_each: 8,
        only_alerting: true
      }),
      AdminAPI.getWriterTaskQueue({
        limit: 80,
        status_group: taskStatusGroup.value,
        project_id: filters.project_id || undefined,
        user_id: queueUserId.value ?? undefined
      })
    ])

    summary.value = summaryData
    logs.value = logsData
    trendByModel.value = modelTrend
    trendByUser.value = userTrend
    errorTop.value = errorTopData
    budgetAlerts.value = budgetData
    taskQueue.value = queueData
    await refreshTrendCharts()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '获取 LLM 观测数据失败'
  } finally {
    loading.value = false
  }
}

const buildExportFilename = () => {
  const now = new Date()
  const pad = (value: number) => String(value).padStart(2, '0')
  const timestamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`
  return `llm_call_logs_${timestamp}.csv`
}

const exportCsv = async () => {
  exporting.value = true
  try {
    const blob = await AdminAPI.exportLLMCallLogsCsv({
      hours: filters.hours,
      status_filter: filters.status_filter || undefined,
      request_type: filters.request_type || undefined,
      model: filters.model || undefined,
      project_id: filters.project_id || undefined,
      max_rows: 20000
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = buildExportFilename()
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    showAlert('CSV 导出成功', 'success')
  } catch (err) {
    showAlert(err instanceof Error ? err.message : 'CSV 导出失败', 'error')
  } finally {
    exporting.value = false
  }
}

const resetFilters = () => {
  filters.hours = 24
  filters.status_filter = ''
  filters.request_type = ''
  filters.model = ''
  filters.project_id = ''
  queueUserId.value = null
  staleThresholdMinutes.value = 30
  queueOnlyStale.value = false
  fetchData()
}

onMounted(() => {
  updateLayout()
  window.addEventListener('resize', updateLayout)
  void fetchData()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', updateLayout)
  destroyTrendCharts()
})

watch(
  () => [modelTrendRows.value.length, userTrendRows.value.length],
  () => {
    void refreshTrendCharts()
  }
)

watch(
  () => [taskStatusGroup.value, queueUserId.value],
  () => {
    void fetchQueueOnly()
  }
)
</script>

<style scoped>
.admin-card {
  width: 100%;
  box-sizing: border-box;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.card-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: #1f2937;
}

.stat-card {
  border-radius: 14px;
  background: linear-gradient(135deg, rgba(34, 197, 94, 0.08), rgba(34, 197, 94, 0));
}

.section-grid {
  margin-top: 4px;
}

.obs-tabs {
  margin-bottom: 8px;
}

.obs-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.section-card {
  border-radius: 14px;
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.06), rgba(59, 130, 246, 0));
}

.budget-meta {
  font-size: 12px;
  color: #6b7280;
}

.budget-global-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  color: #1f2937;
  font-size: 13px;
}

.queue-summary-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.queue-control-label {
  font-size: 12px;
  color: #6b7280;
}

.chart-wrap {
  height: 220px;
  margin-bottom: 12px;
  padding: 8px 8px 0;
  background: rgba(255, 255, 255, 0.55);
  border-radius: 12px;
}

.trend-chart {
  width: 100%;
  height: 100%;
}

.section-title {
  font-size: 0.98rem;
  font-weight: 600;
  color: #1f2937;
}

.log-table {
  margin-top: 2px;
}

:deep(.queue-stale-row td) {
  background: rgba(254, 242, 242, 0.7) !important;
}

@media (max-width: 991px) {
  .card-header {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
