import { computed, onUnmounted, reactive, ref, watch, type ComputedRef, type Ref } from 'vue'

import { NovelAPI } from '@/api/novel'
import { httpFetchResponse } from '@/api/http'
import { globalAlert } from '@/composables/useAlert'
import type { Chapter, NovelProject, WriterTaskCenterItem, WriterTaskCenterResponse } from '@/api/novel'

interface UseWritingDeskTaskSyncOptions {
  projectId: string
  project: ComputedRef<NovelProject | null>
  selectedChapterNumber: Ref<number | null>
  selectedChapterNeedsPolling: ComputedRef<boolean>
  hasActiveWriterTask: ComputedRef<boolean>
  token: ComputedRef<string | null>
  loadProject: (projectId: string, silent?: boolean) => Promise<void>
  loadChapter: (chapterNumber: number) => Promise<unknown>
  refreshChapterStatuses: (projectId: string) => Promise<void>
  syncGenerationIndicators: () => void
  onUnauthorized: () => Promise<void>
}

const CHAPTER_STATUS_POLL_INTERVAL_MS = 7000
const PROJECT_FULL_SYNC_INTERVAL_TICKS = 18
const TASK_STREAM_RECONNECT_DELAY_MS = 2500
const TASK_STREAM_MAX_RECONNECT_ATTEMPTS = 12
const TASK_STREAM_FAILURE_RECENT_MINUTES = 8
const TASK_STREAM_FAILURE_MESSAGE_MAX_LENGTH = 72

export const useWritingDeskTaskSync = (options: UseWritingDeskTaskSyncOptions) => {
  const taskStreamConnected = ref(false)
  const taskStreamFallback = ref(false)
  const taskStreamReconnectAttempts = ref(0)
  const taskStreamLastError = ref('')
  const taskStreamFailureCount = ref(0)
  const taskStreamLastFailureMessage = ref('')
  const manualReconnectLoading = ref(false)
  const chapterFailureMessageMap = reactive(new Map<number, string>())

  let chapterStatusTimer: number | null = null
  let pollingTick = 0
  let taskStreamReconnectTimer: number | null = null
  let taskStreamAbortController: AbortController | null = null

  const chapterQueueStateCache = new Map<number, string>()
  const taskStreamKnownFailedTaskIds = new Set<string>()

  const showTaskSyncBanner = computed(() => {
    return options.hasActiveWriterTask.value || taskStreamFailureCount.value > 0
  })

  const taskSyncStatusText = computed(() => {
    if (taskStreamFailureCount.value > 0) {
      return `检测到 ${taskStreamFailureCount.value} 个任务失败`
    }
    if (taskStreamConnected.value) {
      return '任务实时同步中'
    }
    if (taskStreamFallback.value) {
      return '实时连接中断，已切换轮询同步'
    }
    return '正在建立任务实时连接'
  })

  const taskSyncDetailText = computed(() => {
    if (taskStreamFailureCount.value > 0) {
      return taskStreamLastFailureMessage.value || '请在任务中心查看失败原因并重试'
    }
    if (taskStreamConnected.value) {
      return '章节状态将即时更新'
    }
    if (taskStreamReconnectAttempts.value > 0) {
      return `自动重连中（第 ${taskStreamReconnectAttempts.value} 次）`
    }
    if (taskStreamLastError.value) {
      return taskStreamLastError.value
    }
    return '当前使用轮询同步'
  })

  const compactTaskMessage = (text: string, maxLength = TASK_STREAM_FAILURE_MESSAGE_MAX_LENGTH) => {
    const normalized = text.replace(/\s+/g, ' ').trim()
    if (!normalized) return ''
    return normalized.length > maxLength ? `${normalized.slice(0, maxLength)}...` : normalized
  }

  const taskFailureCategoryLabel = (category?: string | null) => {
    if (category === 'timeout') return '超时'
    if (category === 'auth') return '鉴权失败'
    if (category === 'rate_limit') return '限流/额度'
    if (category === 'network') return '网络异常'
    if (category === 'upstream') return '上游异常'
    if (category === 'config') return '配置错误'
    if (category === 'canceled') return '已取消'
    return ''
  }

  const resolveTaskFailureMessage = (item: WriterTaskCenterItem) => {
    const raw = item.error_message || item.status_message || item.stage_label || '任务失败，请重试'
    const categoryLabel = taskFailureCategoryLabel(item.failure_category)
    const merged = categoryLabel ? `${categoryLabel}：${raw}` : raw
    return compactTaskMessage(merged)
  }

  const fetchChapterStatus = async () => {
    if (options.selectedChapterNumber.value === null || document.hidden) {
      return
    }
    try {
      await options.loadChapter(options.selectedChapterNumber.value)
      options.syncGenerationIndicators()
    } catch (error) {
      console.error('轮询章节状态失败:', error)
    }
  }

  const stopChapterStatusPolling = () => {
    if (chapterStatusTimer != null) {
      window.clearInterval(chapterStatusTimer)
      chapterStatusTimer = null
    }
    pollingTick = 0
  }

  const pollProjectStatus = async () => {
    if (document.hidden) {
      return
    }
    pollingTick += 1
    try {
      await options.refreshChapterStatuses(options.projectId)

      if (
        options.selectedChapterNumber.value !== null &&
        options.selectedChapterNeedsPolling.value
      ) {
        await options.loadChapter(options.selectedChapterNumber.value)
      }

      if (pollingTick % PROJECT_FULL_SYNC_INTERVAL_TICKS === 0) {
        await options.loadProject(options.projectId, true)
      }
      options.syncGenerationIndicators()
    } catch (error) {
      console.error('轮询项目状态失败:', error)
    }
  }

  const startChapterStatusPolling = () => {
    stopChapterStatusPolling()
    pollingTick = 0
    chapterStatusTimer = window.setInterval(() => {
      void pollProjectStatus()
    }, CHAPTER_STATUS_POLL_INTERVAL_MS)
  }

  const shouldKeepTaskStream = () => {
    return Boolean(options.project.value?.id && options.hasActiveWriterTask.value)
  }

  const stopTaskStreamReconnect = () => {
    if (taskStreamReconnectTimer != null) {
      window.clearTimeout(taskStreamReconnectTimer)
      taskStreamReconnectTimer = null
    }
  }

  const stopTaskStream = (config: { resetMeta?: boolean } = {}) => {
    const resetMeta = config.resetMeta ?? true
    stopTaskStreamReconnect()
    if (taskStreamAbortController) {
      taskStreamAbortController.abort()
      taskStreamAbortController = null
    }
    taskStreamConnected.value = false
    if (resetMeta) {
      taskStreamFallback.value = false
      taskStreamReconnectAttempts.value = 0
      taskStreamLastError.value = ''
      taskStreamFailureCount.value = 0
      taskStreamLastFailureMessage.value = ''
      taskStreamKnownFailedTaskIds.clear()
    }
    chapterQueueStateCache.clear()
    chapterFailureMessageMap.clear()
  }

  const scheduleTaskStreamReconnect = () => {
    if (!shouldKeepTaskStream()) return
    if (taskStreamReconnectAttempts.value >= TASK_STREAM_MAX_RECONNECT_ATTEMPTS) {
      taskStreamLastError.value = `自动重连已达上限（${TASK_STREAM_MAX_RECONNECT_ATTEMPTS} 次）`
      return
    }
    stopTaskStreamReconnect()
    taskStreamReconnectAttempts.value += 1
    taskStreamReconnectTimer = window.setTimeout(() => {
      void startTaskStream()
    }, TASK_STREAM_RECONNECT_DELAY_MS)
  }

  const ensureLocalChapter = (chapterNumber: number): Chapter | null => {
    if (!options.project.value?.chapters) {
      return null
    }
    let chapter = options.project.value.chapters.find((item) => item.chapter_number === chapterNumber)
    if (chapter) {
      return chapter
    }

    const outline = options.project.value.blueprint?.chapter_outline?.find(
      (item) => item.chapter_number === chapterNumber,
    )
    chapter = {
      chapter_number: chapterNumber,
      title: outline?.title || `第${chapterNumber}章`,
      summary: outline?.summary || '',
      content: null,
      versions: null,
      evaluation: null,
      generation_status: 'not_generated',
      word_count: 0,
    } as Chapter

    options.project.value.chapters.push(chapter)
    options.project.value.chapters.sort((a, b) => a.chapter_number - b.chapter_number)
    return chapter
  }

  const parseTaskStreamEvent = (block: string): { eventName: string; data: string } | null => {
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

    return { eventName, data: dataLines.join('\n') }
  }

  const applyTaskSnapshot = async (snapshot: WriterTaskCenterResponse) => {
    if (!options.project.value) return

    const seenChapters = new Set<number>()
    const numbersNeedRefresh = new Set<number>()
    const recentFailedItems = (snapshot.items || []).filter((item) => {
      return item.queue_state === 'failed' && Number(item.age_minutes || 0) <= TASK_STREAM_FAILURE_RECENT_MINUTES
    })

    taskStreamFailureCount.value = recentFailedItems.length
    taskStreamLastFailureMessage.value = recentFailedItems.length > 0
      ? resolveTaskFailureMessage(recentFailedItems[0])
      : ''

    for (const item of snapshot.items || []) {
      const chapterNumber = item.chapter_number
      seenChapters.add(chapterNumber)
      const previousQueueState = chapterQueueStateCache.get(chapterNumber)
      chapterQueueStateCache.set(chapterNumber, item.queue_state)

      const chapter = ensureLocalChapter(chapterNumber)
      if (!chapter) continue

      if (item.queue_state === 'active') {
        chapterFailureMessageMap.delete(chapterNumber)
        if (!['evaluating', 'selecting', 'waiting_for_confirm'].includes(chapter.generation_status)) {
          chapter.generation_status = 'generating'
        }
        continue
      }

      if (item.queue_state === 'failed') {
        chapter.generation_status = 'failed'
        const message = resolveTaskFailureMessage(item)
        if (message) {
          chapterFailureMessageMap.set(chapterNumber, message)
        }
        const isStateTransitionFailed = Boolean(previousQueueState && previousQueueState !== 'failed')
        const isFreshFailure = Number(item.age_minutes || 0) <= 1
        const shouldNotifyFailure =
          (isStateTransitionFailed || isFreshFailure) && !taskStreamKnownFailedTaskIds.has(item.task_id)

        if (shouldNotifyFailure) {
          globalAlert.showError(message || '任务失败，请重试', `第${chapterNumber}章任务失败`)
        }

        taskStreamKnownFailedTaskIds.add(item.task_id)
        if (previousQueueState !== 'failed') {
          numbersNeedRefresh.add(chapterNumber)
        }
        continue
      }

      if (item.queue_state === 'done' && previousQueueState !== 'done') {
        chapterFailureMessageMap.delete(chapterNumber)
        numbersNeedRefresh.add(chapterNumber)
      }
    }

    for (const [chapterNumber, queueState] of Array.from(chapterQueueStateCache.entries())) {
      if (!seenChapters.has(chapterNumber)) {
        if (queueState === 'active') {
          numbersNeedRefresh.add(chapterNumber)
        }
        chapterQueueStateCache.delete(chapterNumber)
      }
    }

    if (numbersNeedRefresh.size > 0) {
      await options.refreshChapterStatuses(options.projectId)
      if (
        options.selectedChapterNumber.value != null &&
        numbersNeedRefresh.has(options.selectedChapterNumber.value)
      ) {
        await options.loadChapter(options.selectedChapterNumber.value)
      }
    }

    options.syncGenerationIndicators()
  }

  const processTaskStreamEvent = async (rawEvent: string) => {
    const parsed = parseTaskStreamEvent(rawEvent)
    if (!parsed || !parsed.data) {
      return
    }

    if (parsed.eventName === 'error') {
      try {
        const payload = JSON.parse(parsed.data) as { message?: string }
        const message = compactTaskMessage(payload?.message || '任务同步异常')
        taskStreamLastError.value = message || '任务同步异常'
      } catch {
        taskStreamLastError.value = compactTaskMessage(parsed.data) || '任务同步异常'
      }
      return
    }

    if (parsed.eventName !== 'snapshot') {
      return
    }

    try {
      const payload = JSON.parse(parsed.data) as WriterTaskCenterResponse
      await applyTaskSnapshot(payload)
    } catch (error) {
      console.warn('解析写作任务 SSE 数据失败:', error)
    }
  }

  const startTaskStream = async () => {
    if (!shouldKeepTaskStream()) return

    stopTaskStream({ resetMeta: false })
    stopChapterStatusPolling()

    if (!options.token.value) {
      taskStreamFallback.value = true
      taskStreamConnected.value = false
      taskStreamLastError.value = '当前会话缺少登录凭证，已切换轮询同步'
      startChapterStatusPolling()
      return
    }

    const streamProjectId = options.project.value?.id || options.projectId
    const controller = new AbortController()
    taskStreamAbortController = controller

    try {
      const streamUrl = NovelAPI.getWriterTaskCenterStreamUrl(streamProjectId, {
        limit: 120,
        status_group: 'all',
        interval_seconds: 3,
      })
      const response = await httpFetchResponse(streamUrl, {
        method: 'GET',
        token: options.token.value,
        headers: {
          Accept: 'text/event-stream',
        },
        signal: controller.signal,
        onUnauthorized: options.onUnauthorized,
      })

      if (!response.body) {
        throw new Error('实时任务流连接失败，响应体为空')
      }

      taskStreamConnected.value = true
      taskStreamFallback.value = false
      taskStreamReconnectAttempts.value = 0
      taskStreamLastError.value = ''

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (shouldKeepTaskStream() && !controller.signal.aborted) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        let delimiterIndex = buffer.indexOf('\n\n')
        while (delimiterIndex >= 0) {
          const rawEvent = buffer.slice(0, delimiterIndex).trim()
          buffer = buffer.slice(delimiterIndex + 2)
          if (rawEvent) {
            await processTaskStreamEvent(rawEvent)
          }
          delimiterIndex = buffer.indexOf('\n\n')
        }
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        console.warn('写作任务实时流中断，回退轮询:', error)
        taskStreamConnected.value = false
        taskStreamFallback.value = true
        taskStreamLastError.value = error instanceof Error ? error.message : '实时连接中断'
        startChapterStatusPolling()
        scheduleTaskStreamReconnect()
      }
    } finally {
      if (taskStreamAbortController === controller) {
        taskStreamAbortController = null
        taskStreamConnected.value = false
      }
    }
  }

  const reconnectTaskStreamManually = async () => {
    if (!options.hasActiveWriterTask.value || manualReconnectLoading.value) {
      return
    }
    manualReconnectLoading.value = true
    taskStreamReconnectAttempts.value = 0
    taskStreamLastError.value = ''
    try {
      await startTaskStream()
    } finally {
      manualReconnectLoading.value = false
    }
  }

  const handleTaskUpdated = async (chapterNumber?: number) => {
    try {
      await options.loadProject(options.projectId, true)
      if (chapterNumber != null) {
        await options.loadChapter(chapterNumber)
      }
      options.syncGenerationIndicators()
    } catch (error) {
      console.error('任务状态刷新失败:', error)
    }
  }

  watch(
    () => options.hasActiveWriterTask.value,
    (active) => {
      if (active) {
        void startTaskStream()
      } else {
        stopTaskStream()
        stopChapterStatusPolling()
      }
    },
    { immediate: true },
  )

  onUnmounted(() => {
    stopTaskStream()
    stopChapterStatusPolling()
  })

  return {
    chapterFailureMessageMap,
    fetchChapterStatus,
    handleTaskUpdated,
    manualReconnectLoading,
    reconnectTaskStreamManually,
    showTaskSyncBanner,
    taskStreamConnected,
    taskSyncDetailText,
    taskSyncStatusText,
  }
}
