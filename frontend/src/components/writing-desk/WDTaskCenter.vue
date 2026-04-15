<template>
  <Teleport to="body">
    <div v-if="show" class="md-dialog-overlay" @click.self="emit('close')">
      <div class="md-dialog m3-task-center-dialog flex flex-col">
        <div class="p-5 border-b flex items-center justify-between" style="border-bottom-color: var(--md-outline-variant);">
          <div>
            <h3 class="md-title-large font-semibold">写作任务中心</h3>
            <p class="md-body-small md-on-surface-variant mt-1">查看生成进度、失败原因并快速重试</p>
          </div>
          <button class="md-icon-btn md-ripple" @click="emit('close')">
            <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"></path>
            </svg>
          </button>
        </div>

        <div class="p-5 border-b flex flex-wrap items-center gap-3" style="border-bottom-color: var(--md-outline-variant);">
          <div class="task-stat">
            <span class="task-stat-label">总任务</span>
            <span class="task-stat-value">{{ queue.total }}</span>
          </div>
          <div class="task-stat">
            <span class="task-stat-label">进行中</span>
            <span class="task-stat-value">{{ queue.active_count }}</span>
          </div>
          <div class="task-stat">
            <span class="task-stat-label">失败</span>
            <span class="task-stat-value">{{ queue.failed_count }}</span>
          </div>
          <div class="task-stat">
            <span class="task-stat-label">完成</span>
            <span class="task-stat-value">{{ queue.done_count }}</span>
          </div>
          <div class="task-stat">
            <span class="task-stat-label">同步</span>
            <span class="task-stat-value">{{ streamConnected ? '实时' : '轮询' }}</span>
          </div>

          <div class="task-filter-group">
            <label class="md-text-field-label">筛选</label>
            <select v-model="statusGroup" class="md-select">
              <option value="all">全部</option>
              <option value="active">进行中</option>
              <option value="failed">失败</option>
            </select>
          </div>

          <button class="md-btn md-btn-tonal md-ripple ml-auto" :disabled="loading" @click="fetchTasks">
            {{ loading ? '刷新中...' : '刷新' }}
          </button>
        </div>

        <div class="flex-1 overflow-auto p-4">
          <div v-if="loading" class="md-body-medium md-on-surface-variant py-8 text-center">正在加载任务...</div>
          <div v-else-if="!queue.items.length" class="md-body-medium md-on-surface-variant py-8 text-center">暂无任务</div>
          <div v-else class="task-list">
            <div
              v-for="item in queue.items"
              :key="item.task_id"
              :class="[
                'task-card',
                item.chapter_number === selectedChapterNumber ? 'task-card-active' : ''
              ]"
            >
              <div class="task-card-head">
                <div class="task-title-wrap">
                  <h4 class="md-title-small font-semibold">第{{ item.chapter_number }}章</h4>
                  <span class="task-stage">{{ item.stage_label }}</span>
                </div>
                <span :class="['task-state-chip', `task-state-${item.queue_state}`]">
                  {{ queueStateLabel(item.queue_state) }}
                </span>
              </div>

              <div class="task-progress">
                <div class="task-progress-bar" :style="{ width: `${item.progress_percent}%` }"></div>
              </div>
              <div class="md-body-small md-on-surface-variant mt-1">{{ item.status_message }}</div>
              <div class="md-body-small md-on-surface-variant mt-1">状态：{{ item.status }} · {{ item.word_count }} 字 · {{ item.age_minutes }} 分钟前更新</div>

              <div v-if="item.error_message" class="task-error mt-2">
                {{ item.error_message }}
              </div>

              <div class="task-actions mt-3">
                <button class="md-btn md-btn-text md-ripple" @click="emit('jumpChapter', item.chapter_number)">
                  定位章节
                </button>
                <button
                  class="md-btn md-btn-outlined md-ripple"
                  :disabled="!item.can_cancel || actionLoading[item.task_id]"
                  @click="cancelTask(item)"
                >
                  取消
                </button>
                <button
                  class="md-btn md-btn-filled md-ripple"
                  :disabled="!item.can_retry || actionLoading[item.task_id]"
                  @click="retryTask(item)"
                >
                  重试
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { onUnmounted, reactive, ref, watch } from 'vue'
import { NovelAPI, type WriterTaskCenterItem, type WriterTaskCenterResponse } from '@/api/novel'
import { globalAlert } from '@/composables/useAlert'
import { useAuthStore } from '@/stores/auth'

interface Props {
  show: boolean
  projectId?: string
  selectedChapterNumber?: number | null
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'jumpChapter', chapterNumber: number): void
  (e: 'taskUpdated', chapterNumber?: number): void
}>()

const loading = ref(false)
const statusGroup = ref<'all' | 'active' | 'failed'>('all')
const actionLoading = reactive<Record<string, boolean>>({})
const streamConnected = ref(false)
const streamFallbackMode = ref(false)
const queue = ref<WriterTaskCenterResponse>({
  total: 0,
  active_count: 0,
  failed_count: 0,
  done_count: 0,
  items: []
})
let timer: number | null = null
let reconnectTimer: number | null = null
let streamAbortController: AbortController | null = null

const queueStateLabel = (state: string) => {
  if (state === 'active') return '进行中'
  if (state === 'failed') return '失败'
  if (state === 'done') return '已完成'
  return '其他'
}

const authStore = useAuthStore()

const shouldKeepStreaming = () => Boolean(props.show && props.projectId)

const stopAutoRefresh = () => {
  if (timer) {
    window.clearInterval(timer)
    timer = null
  }
}

const startAutoRefresh = () => {
  if (!streamFallbackMode.value) return
  stopAutoRefresh()
  timer = window.setInterval(() => {
    void fetchTasks()
  }, 6000)
}

const stopReconnect = () => {
  if (reconnectTimer) {
    window.clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
}

const stopTaskStream = () => {
  stopReconnect()
  if (streamAbortController) {
    streamAbortController.abort()
    streamAbortController = null
  }
  streamConnected.value = false
}

const scheduleReconnect = () => {
  if (!shouldKeepStreaming()) return
  stopReconnect()
  reconnectTimer = window.setTimeout(() => {
    void startTaskStream()
  }, 2500)
}

const processSseEvent = (block: string) => {
  const lines = block.split('\n')
  let eventName = 'message'
  const dataLines: string[] = []
  for (const line of lines) {
    if (line.startsWith('event:')) {
      eventName = line.slice(6).trim()
      continue
    }
    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trim())
    }
  }
  if (eventName !== 'snapshot' || !dataLines.length) {
    return
  }
  try {
    const payload = JSON.parse(dataLines.join('\n')) as WriterTaskCenterResponse
    queue.value = payload
    loading.value = false
  } catch (error) {
    console.warn('解析任务中心 SSE 数据失败:', error)
  }
}

const startTaskStream = async () => {
  if (!props.projectId) return
  stopTaskStream()

  if (!authStore.token) {
    streamFallbackMode.value = true
    startAutoRefresh()
    return
  }

  loading.value = true
  const controller = new AbortController()
  streamAbortController = controller

  try {
    const streamUrl = NovelAPI.getWriterTaskCenterStreamUrl(props.projectId, {
      limit: 120,
      status_group: statusGroup.value,
      interval_seconds: 3,
    })
    const response = await fetch(streamUrl, {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${authStore.token}`,
        Accept: 'text/event-stream',
      },
      signal: controller.signal,
    })
    if (!response.ok || !response.body) {
      throw new Error(`任务流连接失败，状态码: ${response.status}`)
    }

    streamConnected.value = true
    streamFallbackMode.value = false
    stopAutoRefresh()

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (shouldKeepStreaming()) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let delimiterIndex = buffer.indexOf('\n\n')
      while (delimiterIndex >= 0) {
        const rawEvent = buffer.slice(0, delimiterIndex).trim()
        buffer = buffer.slice(delimiterIndex + 2)
        if (rawEvent) {
          processSseEvent(rawEvent)
        }
        delimiterIndex = buffer.indexOf('\n\n')
      }
    }
  } catch (error) {
    if (!controller.signal.aborted) {
      console.warn('任务中心 SSE 中断，回退轮询:', error)
      streamFallbackMode.value = true
      startAutoRefresh()
      scheduleReconnect()
    }
  } finally {
    const isCurrentController = streamAbortController === controller
    if (isCurrentController) {
      streamAbortController = null
      streamConnected.value = false
      loading.value = false
    }
  }
}

const fetchTasks = async () => {
  if (!props.projectId) return
  loading.value = true
  try {
    queue.value = await NovelAPI.getWriterTaskCenter(props.projectId, {
      limit: 120,
      status_group: statusGroup.value
    })
  } catch (error) {
    globalAlert.showError(`加载任务失败: ${error instanceof Error ? error.message : '未知错误'}`)
  } finally {
    loading.value = false
  }
}

const cancelTask = async (item: WriterTaskCenterItem) => {
  if (!props.projectId || !item.can_cancel) return
  const confirmed = await globalAlert.showConfirm(
    `确认取消第${item.chapter_number}章当前任务？`,
    '取消任务'
  )
  if (!confirmed) return
  actionLoading[item.task_id] = true
  try {
    const result = await NovelAPI.cancelWriterTask(props.projectId, item.chapter_number)
    globalAlert.showSuccess(result.message || '任务取消成功')
    await fetchTasks()
    emit('taskUpdated', item.chapter_number)
  } catch (error) {
    globalAlert.showError(`取消失败: ${error instanceof Error ? error.message : '未知错误'}`)
  } finally {
    actionLoading[item.task_id] = false
  }
}

const retryTask = async (item: WriterTaskCenterItem) => {
  if (!props.projectId || !item.can_retry) return
  actionLoading[item.task_id] = true
  try {
    const result = await NovelAPI.retryWriterTask(props.projectId, item.chapter_number, {
      force: true,
      resume_from_checkpoint: true,
    })
    globalAlert.showSuccess(result.message || '重试任务已提交')
    await fetchTasks()
    emit('taskUpdated', item.chapter_number)
  } catch (error) {
    globalAlert.showError(`重试失败: ${error instanceof Error ? error.message : '未知错误'}`)
  } finally {
    actionLoading[item.task_id] = false
  }
}

watch(
  () => props.show,
  (show) => {
    if (show) {
      void fetchTasks()
      void startTaskStream()
    } else {
      stopTaskStream()
      stopAutoRefresh()
    }
  }
)

watch(
  () => statusGroup.value,
  () => {
    if (!props.show) return
    void fetchTasks()
    void startTaskStream()
  }
)

watch(
  () => props.projectId,
  () => {
    if (!props.show) return
    void fetchTasks()
    void startTaskStream()
  }
)

onUnmounted(() => {
  stopTaskStream()
  stopAutoRefresh()
})
</script>

<style scoped>
.m3-task-center-dialog {
  width: min(960px, calc(100vw - 24px));
  height: min(88vh, 820px);
  border-radius: var(--md-radius-xl);
}

.task-stat {
  display: flex;
  flex-direction: column;
  min-width: 70px;
}

.task-stat-label {
  font-size: 12px;
  color: var(--md-on-surface-variant);
}

.task-stat-value {
  font-size: 16px;
  font-weight: 600;
  color: var(--md-on-surface);
}

.task-filter-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 120px;
}

.md-select {
  min-height: 36px;
  border: 1px solid var(--md-outline-variant);
  border-radius: var(--md-radius-md);
  padding: 0 10px;
  background: var(--md-surface);
  color: var(--md-on-surface);
}

.task-list {
  display: grid;
  gap: 12px;
}

.task-card {
  border: 1px solid var(--md-outline-variant);
  border-radius: var(--md-radius-lg);
  padding: 12px;
  background: var(--md-surface);
}

.task-card-active {
  border-color: var(--md-primary);
  box-shadow: inset 0 0 0 1px rgba(37, 99, 235, 0.12);
}

.task-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.task-title-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}

.task-stage {
  font-size: 12px;
  color: var(--md-on-surface-variant);
}

.task-state-chip {
  font-size: 12px;
  border-radius: 999px;
  padding: 2px 8px;
  font-weight: 600;
}

.task-state-active {
  background: rgba(245, 158, 11, 0.18);
  color: #92400e;
}

.task-state-failed {
  background: rgba(239, 68, 68, 0.18);
  color: #991b1b;
}

.task-state-done {
  background: rgba(16, 185, 129, 0.18);
  color: #065f46;
}

.task-state-other {
  background: rgba(148, 163, 184, 0.18);
  color: #334155;
}

.task-progress {
  margin-top: 8px;
  height: 8px;
  border-radius: 999px;
  background: var(--md-surface-container);
  overflow: hidden;
}

.task-progress-bar {
  height: 100%;
  background: linear-gradient(90deg, #2563eb, #0ea5e9);
  transition: width 260ms ease;
}

.task-error {
  font-size: 12px;
  color: #b91c1c;
  background: rgba(239, 68, 68, 0.12);
  border-radius: var(--md-radius-sm);
  padding: 6px 8px;
  word-break: break-all;
}

.task-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

@media (max-width: 767px) {
  .m3-task-center-dialog {
    width: calc(100vw - 12px);
    height: calc(100vh - 12px);
    height: calc(100dvh - 12px);
  }
}
</style>
