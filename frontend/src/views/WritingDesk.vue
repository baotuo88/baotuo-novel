<!-- AIMETA P=写作台_章节编辑主页面|R=写作界面_章节管理|NR=不含详情展示|E=route:/novel/:id#component:WritingDesk|X=ui|A=写作台|D=vue|S=dom,net|RD=./README.ai -->
<template>
  <div class="m3-shell h-[100dvh] flex flex-col overflow-hidden">
    <WDHeader
      :project="project"
      :progress="progress"
      :completed-chapters="completedChapters"
      :total-chapters="totalChapters"
      :show-task-sync="showTaskSyncBanner"
      :task-sync-connected="taskStreamConnected"
      :task-sync-status-text="taskSyncStatusText"
      :task-sync-detail-text="taskSyncDetailText"
      :task-reconnect-loading="manualReconnectLoading"
      :show-reconnect-action="!taskStreamConnected && hasActiveWriterTask"
      @go-back="goBack"
      @view-project-detail="viewProjectDetail"
      @toggle-sidebar="toggleSidebar"
      @open-task-center="showTaskCenter = true"
      @reconnect-task-sync="reconnectTaskStreamManually"
    />

    <!-- 主要内容区域 -->
    <div class="desk-content-frame flex-1 min-h-0 w-full px-4 sm:px-5 lg:px-6 xl:px-7 2xl:px-8 py-6 overflow-hidden">
      <!-- 加载状态 -->
      <div v-if="novelStore.isLoading" class="h-full flex justify-center items-center">
        <div class="text-center">
          <div class="md-spinner mx-auto mb-4"></div>
          <p class="md-body-medium md-on-surface-variant">正在加载项目数据...</p>
        </div>
      </div>

      <!-- 错误状态 -->
      <div v-else-if="novelStore.error" class="text-center py-20">
        <div class="md-card md-card-outlined p-8 max-w-md mx-auto" style="border-radius: var(--md-radius-xl);">
          <div class="w-12 h-12 rounded-full mx-auto mb-4 flex items-center justify-center" style="background-color: var(--md-error-container);">
            <svg class="w-6 h-6" style="color: var(--md-error);" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path>
            </svg>
          </div>
          <h3 class="md-title-large mb-2" style="color: var(--md-on-surface);">加载失败</h3>
          <p class="md-body-medium mb-4" style="color: var(--md-error);">{{ novelStore.error }}</p>
          <button @click="loadProject" class="md-btn md-btn-tonal md-ripple">重新加载</button>
        </div>
      </div>

      <!-- 主要内容 -->
      <div v-else-if="project" class="h-full min-h-0 flex flex-col gap-3">
        <div class="flex-1 min-h-0 flex gap-4 lg:gap-5 xl:gap-6">
          <WDSidebar
            :project="project"
            :sidebar-open="sidebarOpen"
            :selected-chapter-number="selectedChapterNumber"
            :generating-chapter="generatingChapter"
            :evaluating-chapter="evaluatingChapter"
            :is-generating-outline="isGeneratingOutline"
            :writing-presets="writingPresets"
            :selected-preset-id="selectedPresetId"
            :active-preset-name="activeWritingPreset?.name || null"
            :preset-loading="presetLoading"
            :preset-applying="presetApplying"
            :preset-collapse-token="presetCollapseToken"
            @close-sidebar="closeSidebar"
            @select-chapter="selectChapter"
            @generate-chapter="generateChapter"
            @edit-chapter="openEditChapterModal"
            @delete-chapter="deleteChapter"
            @generate-outline="generateOutline"
            @update:selected-preset-id="selectedPresetId = $event"
            @apply-preset="applyWritingPreset"
            @clear-preset="clearWritingPreset"
          />

          <div class="flex-1 min-w-0 min-h-0">
            <WDWorkspace
              :project="project"
              :selected-chapter-number="selectedChapterNumber"
              :generating-chapter="generatingChapter"
              :evaluating-chapter="evaluatingChapter"
              :chapter-failure-message="selectedChapterNumber !== null ? (chapterFailureMessageMap.get(selectedChapterNumber) || '') : ''"
              :show-version-selector="showVersionSelector"
              :chapter-generation-result="chapterGenerationResult"
              :selected-version-index="selectedVersionIndex"
              :available-versions="availableVersions"
              :is-selecting-version="isSelectingVersion"
              @regenerate-chapter="regenerateChapter"
              @evaluate-chapter="evaluateChapter"
              @hide-version-selector="hideVersionSelector"
              @update:selected-version-index="selectedVersionIndex = $event"
              @show-version-detail="showVersionDetail"
              @confirm-version-selection="confirmVersionSelection"
              @generate-chapter="generateChapter"
              @show-evaluation-detail="showEvaluationDetailModal = true"
              @fetch-chapter-status="fetchChapterStatus"
              @edit-chapter="editChapterContent"
              @version-rolled-back="handleVersionRolledBack"
              @open-world-graph="showWorldGraphModal = true"
              @chapter-updated="handleChapterUpdated"
            />
          </div>
        </div>
      </div>
    </div>
    <WDTaskCenter
      :show="showTaskCenter"
      :project-id="project?.id"
      :selected-chapter-number="selectedChapterNumber"
      @close="showTaskCenter = false"
      @jump-chapter="handleJumpToTaskChapter"
      @task-updated="handleTaskUpdated"
    />
    <WDVersionDetailModal
      :show="showVersionDetailModal"
      :detail-version-index="detailVersionIndex"
      :version="availableVersions[detailVersionIndex]"
      :is-current="isCurrentVersion(detailVersionIndex)"
      @close="closeVersionDetail"
      @select-version="selectVersionFromDetail"
    />
    <WDEvaluationDetailModal
      :show="showEvaluationDetailModal"
      :evaluation="selectedChapter?.evaluation || null"
      @close="showEvaluationDetailModal = false"
    />
    <WDEditChapterModal
      :show="showEditChapterModal"
      :chapter="editingChapter"
      @close="showEditChapterModal = false"
      @save="saveChapterChanges"
    />
    <WDGenerateOutlineModal
      :show="showGenerateOutlineModal"
      @close="showGenerateOutlineModal = false"
      @generate="handleGenerateOutline"
    />
    <WDWorldGraphModal
      :show="showWorldGraphModal"
      :project-id="project?.id || null"
      @close="showWorldGraphModal = false"
      @graph-updated="handleWorldGraphUpdated"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useNovelStore } from '@/stores/novel'
import { useAuthStore } from '@/stores/auth'
import { NovelAPI } from '@/api/novel'
import type {
  Chapter,
  ChapterOutline,
  ChapterGenerationResponse,
  ChapterVersion,
  WriterTaskCenterItem,
  WriterTaskCenterResponse,
  WritingPresetItem,
} from '@/api/novel'
import { globalAlert } from '@/composables/useAlert'
import WDHeader from '@/components/writing-desk/WDHeader.vue'
import WDSidebar from '@/components/writing-desk/WDSidebar.vue'
import WDWorkspace from '@/components/writing-desk/WDWorkspace.vue'
import WDVersionDetailModal from '@/components/writing-desk/WDVersionDetailModal.vue'
import WDEvaluationDetailModal from '@/components/writing-desk/WDEvaluationDetailModal.vue'
import WDEditChapterModal from '@/components/writing-desk/WDEditChapterModal.vue'
import WDGenerateOutlineModal from '@/components/writing-desk/WDGenerateOutlineModal.vue'
import WDTaskCenter from '@/components/writing-desk/WDTaskCenter.vue'
import WDWorldGraphModal from '@/components/writing-desk/WDWorldGraphModal.vue'

interface Props {
  id: string
}

const props = defineProps<Props>()
const router = useRouter()
const novelStore = useNovelStore()
const authStore = useAuthStore()

// 状态管理
const selectedChapterNumber = ref<number | null>(null)
const chapterGenerationResult = ref<ChapterGenerationResponse | null>(null)
const selectedVersionIndex = ref<number>(0)
const generatingChapter = ref<number | null>(null)
const sidebarOpen = ref(false)
const showVersionDetailModal = ref(false)
const detailVersionIndex = ref<number>(0)
const showEvaluationDetailModal = ref(false)
const showEditChapterModal = ref(false)
const editingChapter = ref<ChapterOutline | null>(null)
const isGeneratingOutline = ref(false)
const showGenerateOutlineModal = ref(false)
const showTaskCenter = ref(false)
const showWorldGraphModal = ref(false)
const writingPresets = ref<WritingPresetItem[]>([])
const selectedPresetId = ref('')
const presetLoading = ref(false)
const presetApplying = ref(false)
const presetCollapseToken = ref(0)
let chapterStatusTimer: number | null = null
let pollingTick = 0
let taskStreamReconnectTimer: number | null = null
let taskStreamAbortController: AbortController | null = null
const taskStreamConnected = ref(false)
const taskStreamFallback = ref(false)
const taskStreamReconnectAttempts = ref(0)
const taskStreamLastError = ref('')
const taskStreamFailureCount = ref(0)
const taskStreamLastFailureMessage = ref('')
const manualReconnectLoading = ref(false)
const chapterQueueStateCache = new Map<number, string>()
const chapterFailureMessageMap = new Map<number, string>()
const taskStreamKnownFailedTaskIds = new Set<string>()
const CHAPTER_STATUS_POLL_INTERVAL_MS = 5000
const PROJECT_FULL_SYNC_INTERVAL_TICKS = 6
const TASK_STREAM_RECONNECT_DELAY_MS = 2500
const TASK_STREAM_MAX_RECONNECT_ATTEMPTS = 12
const TASK_STREAM_FAILURE_RECENT_MINUTES = 8
const TASK_STREAM_FAILURE_MESSAGE_MAX_LENGTH = 72

// 计算属性
const project = computed(() => novelStore.currentProject)
const activeWritingPreset = computed(() =>
  writingPresets.value.find((item) => item.is_active) || null
)

const selectedChapter = computed(() => {
  if (!project.value || selectedChapterNumber.value === null) return null
  return project.value.chapters.find(ch => ch.chapter_number === selectedChapterNumber.value) || null
})

const selectedChapterNeedsPolling = computed(() => {
  const status = selectedChapter.value?.generation_status
  if (!status) return false
  return ['generating', 'evaluating', 'selecting', 'waiting_for_confirm'].includes(status)
})

const showVersionSelector = computed(() => {
  if (!selectedChapter.value) return false
  const status = selectedChapter.value.generation_status
  return status === 'waiting_for_confirm' || status === 'evaluating' || status === 'evaluation_failed' || status === 'selecting'
})

const evaluatingChapter = computed(() => {
  if (selectedChapter.value?.generation_status === 'evaluating') {
    return selectedChapter.value.chapter_number
  }
  return null
})

const isSelectingVersion = computed(() => {
  return selectedChapter.value?.generation_status === 'selecting'
})

const selectedChapterOutline = computed(() => {
  if (!project.value?.blueprint?.chapter_outline || selectedChapterNumber.value === null) return null
  return project.value.blueprint.chapter_outline.find(ch => ch.chapter_number === selectedChapterNumber.value) || null
})

const progress = computed(() => {
  if (!project.value?.blueprint?.chapter_outline) return 0
  const totalChapters = project.value.blueprint.chapter_outline.length
  const completedChapters = project.value.chapters.filter(ch => ch.content).length
  return Math.round((completedChapters / totalChapters) * 100)
})

const totalChapters = computed(() => {
  return project.value?.blueprint?.chapter_outline?.length || 0
})

const completedChapters = computed(() => {
  return project.value?.chapters?.filter(ch => ch.content)?.length || 0
})

const hasActiveWriterTask = computed(() => {
  return (project.value?.chapters || []).some((chapter) =>
    ['generating', 'evaluating', 'selecting'].includes(chapter.generation_status)
  )
})

const showTaskSyncBanner = computed(() => hasActiveWriterTask.value || taskStreamFailureCount.value > 0)

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

const isCurrentVersion = (versionIndex: number) => {
  if (!selectedChapter.value?.content || !availableVersions.value?.[versionIndex]?.content) return false

  // 使用cleanVersionContent函数清理内容进行比较
  const cleanCurrentContent = cleanVersionContent(selectedChapter.value.content)
  const cleanVersionContentStr = cleanVersionContent(availableVersions.value[versionIndex].content)

  return cleanCurrentContent === cleanVersionContentStr
}

const cleanVersionContent = (content: string): string => {
  if (!content) return ''

  // 尝试解析JSON，看是否是完整的章节对象
  try {
    const parsed = JSON.parse(content)
    const extractContent = (value: any): string | null => {
      if (!value) return null
      if (typeof value === 'string') return value
      if (Array.isArray(value)) {
        for (const item of value) {
          const nested = extractContent(item)
          if (nested) return nested
        }
        return null
      }
      if (typeof value === 'object') {
        for (const key of ['content', 'chapter_content', 'chapter_text', 'text', 'body', 'story']) {
          if (value[key]) {
            const nested = extractContent(value[key])
            if (nested) return nested
          }
        }
      }
      return null
    }
    const extracted = extractContent(parsed)
    if (extracted) {
      // 如果是章节对象/数组，提取正文
      content = extracted
    }
  } catch (error) {
    // 如果不是JSON，继续处理字符串
  }

  // 去掉开头和结尾的引号
  let cleaned = content.replace(/^"|"$/g, '')

  // 处理转义字符
  cleaned = cleaned.replace(/\\n/g, '\n')  // 换行符
  cleaned = cleaned.replace(/\\"/g, '"')   // 引号
  cleaned = cleaned.replace(/\\t/g, '\t')  // 制表符
  cleaned = cleaned.replace(/\\\\/g, '\\') // 反斜杠

  return cleaned
}

const canGenerateChapter = (chapterNumber: number) => {
  if (!project.value?.blueprint?.chapter_outline) return false

  // 检查前面所有章节是否都已成功生成
  const outlines = [...project.value.blueprint.chapter_outline].sort((a, b) => a.chapter_number - b.chapter_number)
  
  for (const outline of outlines) {
    if (outline.chapter_number >= chapterNumber) break
    
    const chapter = project.value?.chapters.find(ch => ch.chapter_number === outline.chapter_number)
    if (!chapter || chapter.generation_status !== 'successful') {
      return false // 前面有章节未完成
    }
  }

  // 检查当前章节是否已经完成
  const currentChapter = project.value?.chapters.find(ch => ch.chapter_number === chapterNumber)
  if (currentChapter && currentChapter.generation_status === 'successful') {
    return true // 已完成的章节可以重新生成
  }

  return true // 前面章节都完成了，可以生成当前章节
}

const isChapterFailed = (chapterNumber: number) => {
  if (!project.value?.chapters) return false
  const chapter = project.value.chapters.find(ch => ch.chapter_number === chapterNumber)
  return chapter && chapter.generation_status === 'failed'
}

const hasChapterInProgress = (chapterNumber: number) => {
  if (!project.value?.chapters) return false
  const chapter = project.value.chapters.find(ch => ch.chapter_number === chapterNumber)
  // waiting_for_confirm状态表示等待选择版本 = 进行中状态
  return chapter && chapter.generation_status === 'waiting_for_confirm'
}

// 可用版本列表 (合并生成结果和已有版本)
const availableVersions = computed(() => {
  // 优先使用新生成的版本（对象数组格式）
  if (chapterGenerationResult.value?.versions) {
    console.log('使用生成结果版本:', chapterGenerationResult.value.versions)
    return chapterGenerationResult.value.versions
  }

  // 使用章节已有的版本（字符串数组格式，需要转换为对象数组）
  if (selectedChapter.value?.versions && Array.isArray(selectedChapter.value.versions)) {
    console.log('原始章节版本 (字符串数组):', selectedChapter.value.versions)

    // 将字符串数组转换为ChapterVersion对象数组
    const convertedVersions = selectedChapter.value.versions.map((versionString, index) => {
      console.log(`版本 ${index} 原始字符串:`, versionString)

      try {
        // 解析JSON字符串
        const versionObj = JSON.parse(versionString)
        console.log(`版本 ${index} 解析后的对象:`, versionObj)

        // 提取content字段作为实际内容
        const actualContent = versionObj.content || versionString

        console.log(`版本 ${index} 实际内容:`, actualContent.substring(0, 100) + '...')

        return {
          content: actualContent,
          style: '标准' // 默认风格
        }
      } catch (error) {
        // 如果JSON解析失败，直接使用原始字符串
        console.log(`版本 ${index} JSON解析失败，使用原始字符串:`, error)
        return {
          content: versionString,
          style: '标准'
        }
      }
    })

    console.log('转换后的版本对象:', convertedVersions)
    return convertedVersions
  }

  console.log('没有可用版本，selectedChapter:', selectedChapter.value)
  return []
})


// 方法
const loadWritingPresets = async () => {
  presetLoading.value = true
  try {
    writingPresets.value = await NovelAPI.listWriterPresets(props.id)
    selectedPresetId.value = activeWritingPreset.value?.preset_id || ''
  } catch (error) {
    console.error('加载写作预设失败:', error)
  } finally {
    presetLoading.value = false
  }
}

const applyWritingPreset = async () => {
  presetApplying.value = true
  try {
    await NovelAPI.setActiveWriterPreset(selectedPresetId.value || null, props.id)
    await loadWritingPresets()
    presetCollapseToken.value += 1
    globalAlert.showSuccess('写作预设已应用到当前项目', 'Preset')
  } catch (error) {
    globalAlert.showError(`预设应用失败: ${error instanceof Error ? error.message : '未知错误'}`, 'Preset')
  } finally {
    presetApplying.value = false
  }
}

const clearWritingPreset = async () => {
  selectedPresetId.value = ''
  await applyWritingPreset()
}

const goBack = () => {
  router.push('/workspace')
}

const viewProjectDetail = () => {
  if (project.value) {
    router.push(`/detail/${project.value.id}`)
  }
}

const toggleSidebar = () => {
  sidebarOpen.value = !sidebarOpen.value
}

const closeSidebar = () => {
  sidebarOpen.value = false
}

const syncGenerationIndicators = () => {
  const generating = (project.value?.chapters || []).find((ch) => ch.generation_status === 'generating')
  generatingChapter.value = generating ? generating.chapter_number : null
}

const loadProject = async () => {
  try {
    await novelStore.loadProject(props.id)
    syncGenerationIndicators()
  } catch (error) {
    console.error('加载项目失败:', error)
  }
}

const fetchChapterStatus = async () => {
  if (selectedChapterNumber.value === null) {
    return
  }
  try {
    await novelStore.loadChapter(selectedChapterNumber.value)
    syncGenerationIndicators()
    console.log('Chapter status polled and updated.')
  } catch (error) {
    console.error('轮询章节状态失败:', error)
    // 在这里可以决定是否要通知用户轮询失败
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
  pollingTick += 1
  try {
    await novelStore.refreshChapterStatuses(props.id)

    if (selectedChapterNumber.value !== null && selectedChapterNeedsPolling.value) {
      await novelStore.loadChapter(selectedChapterNumber.value)
    }

    if (pollingTick % PROJECT_FULL_SYNC_INTERVAL_TICKS === 0) {
      await novelStore.loadProject(props.id, true)
    }
    syncGenerationIndicators()
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
  return Boolean(project.value?.id && hasActiveWriterTask.value)
}

const stopTaskStreamReconnect = () => {
  if (taskStreamReconnectTimer != null) {
    window.clearTimeout(taskStreamReconnectTimer)
    taskStreamReconnectTimer = null
  }
}

const stopTaskStream = (options: { resetMeta?: boolean } = {}) => {
  const resetMeta = options.resetMeta ?? true
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

const ensureLocalChapter = (chapterNumber: number) => {
  if (!project.value?.chapters) {
    return null
  }
  let chapter = project.value.chapters.find((item) => item.chapter_number === chapterNumber)
  if (chapter) {
    return chapter
  }
  const outline = project.value.blueprint?.chapter_outline?.find((item) => item.chapter_number === chapterNumber)
  chapter = {
    chapter_number: chapterNumber,
    title: outline?.title || `第${chapterNumber}章`,
    summary: outline?.summary || '',
    content: null,
    versions: null,
    evaluation: null,
    generation_status: 'not_generated',
    word_count: 0
  } as Chapter
  project.value.chapters.push(chapter)
  project.value.chapters.sort((a, b) => a.chapter_number - b.chapter_number)
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
  if (!project.value) return

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
      const shouldNotifyFailure = (isStateTransitionFailed || isFreshFailure) && !taskStreamKnownFailedTaskIds.has(item.task_id)
      if (shouldNotifyFailure) {
        const title = `第${chapterNumber}章任务失败`
        globalAlert.showError(message || '任务失败，请重试', title)
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
    await novelStore.refreshChapterStatuses(props.id)
    if (selectedChapterNumber.value != null && numbersNeedRefresh.has(selectedChapterNumber.value)) {
      await novelStore.loadChapter(selectedChapterNumber.value)
    }
  }

  syncGenerationIndicators()
}

const processTaskStreamEvent = async (rawEvent: string) => {
  const parsed = parseTaskStreamEvent(rawEvent)
  if (!parsed) return
  if (!parsed.data) {
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

  if (!authStore.token) {
    taskStreamFallback.value = true
    taskStreamConnected.value = false
    taskStreamLastError.value = '当前会话缺少登录凭证，已切换轮询同步'
    startChapterStatusPolling()
    return
  }

  const streamProjectId = project.value?.id || props.id
  const controller = new AbortController()
  taskStreamAbortController = controller

  try {
    const streamUrl = NovelAPI.getWriterTaskCenterStreamUrl(streamProjectId, {
      limit: 120,
      status_group: 'all',
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
      throw new Error(`实时任务流连接失败，状态码: ${response.status}`)
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
  if (!hasActiveWriterTask.value || manualReconnectLoading.value) {
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


// 显示版本详情
const showVersionDetail = (versionIndex: number) => {
  detailVersionIndex.value = versionIndex
  showVersionDetailModal.value = true
}

// 关闭版本详情弹窗
const closeVersionDetail = () => {
  showVersionDetailModal.value = false
}

// 隐藏版本选择器，返回内容视图
const hideVersionSelector = () => {
  // Now controlled by computed property, but we can clear the generation result
  chapterGenerationResult.value = null
  selectedVersionIndex.value = 0
}

const selectChapter = (chapterNumber: number) => {
  selectedChapterNumber.value = chapterNumber
  chapterGenerationResult.value = null
  selectedVersionIndex.value = 0
  closeSidebar()
}

const generateChapter = async (chapterNumber: number) => {
  // 检查是否可以生成该章节
  if (!canGenerateChapter(chapterNumber) && !isChapterFailed(chapterNumber) && !hasChapterInProgress(chapterNumber)) {
    globalAlert.showError('请按顺序生成章节，先完成前面的章节', '生成受限')
    return
  }

  try {
    generatingChapter.value = chapterNumber
    selectedChapterNumber.value = chapterNumber
    chapterFailureMessageMap.delete(chapterNumber)

    // 在本地更新章节状态为generating
    if (project.value?.chapters) {
      const chapter = project.value.chapters.find(ch => ch.chapter_number === chapterNumber)
      if (chapter) {
        chapter.generation_status = 'generating'
      } else {
        // If chapter does not exist, create a temporary one to show generating state
        const outline = project.value.blueprint?.chapter_outline?.find(o => o.chapter_number === chapterNumber)
        project.value.chapters.push({
          chapter_number: chapterNumber,
          title: outline?.title || '加载中...',
          summary: outline?.summary || '',
          content: '',
          versions: [],
          evaluation: null,
          generation_status: 'generating'
        } as Chapter)
      }
    }

    await novelStore.generateChapter(chapterNumber)
    syncGenerationIndicators()
    
    // store 中的 project 已经被更新，所以我们不需要手动修改本地状态
    // chapterGenerationResult 也不再需要，因为 availableVersions 会从更新后的 project.chapters 中获取数据
    // showVersionSelector is now a computed property and will update automatically.
    chapterGenerationResult.value = null 
    selectedVersionIndex.value = 0
  } catch (error) {
    console.error('生成章节失败:', error)

    // 错误状态的本地更新仍然是必要的，以立即反映UI
    if (project.value?.chapters) {
      const chapter = project.value.chapters.find(ch => ch.chapter_number === chapterNumber)
      if (chapter) {
        chapter.generation_status = 'failed'
      }
    }

    globalAlert.showError(`生成章节失败: ${error instanceof Error ? error.message : '未知错误'}`, '生成失败')
  } finally {
    syncGenerationIndicators()
  }
}

const regenerateChapter = async () => {
  if (selectedChapterNumber.value !== null) {
    await generateChapter(selectedChapterNumber.value)
  }
}

const selectVersion = async (versionIndex: number) => {
  if (selectedChapterNumber.value === null || !availableVersions.value?.[versionIndex]?.content) {
    return
  }

  try {
    // 在本地立即更新状态以反映UI
    if (project.value?.chapters) {
      const chapter = project.value.chapters.find(ch => ch.chapter_number === selectedChapterNumber.value)
      if (chapter) {
        chapter.generation_status = 'selecting'
      }
    }

    selectedVersionIndex.value = versionIndex
    await novelStore.selectChapterVersion(selectedChapterNumber.value, versionIndex)

    // 状态更新将由 store 自动触发，本地无需手动更新
    // 轮询机制会处理状态变更，成功后会自动隐藏选择器
    // showVersionSelector.value = false
    chapterGenerationResult.value = null
    globalAlert.showSuccess('版本已确认', '操作成功')
  } catch (error) {
    console.error('选择章节版本失败:', error)
    // 错误状态下恢复章节状态
    if (project.value?.chapters) {
      const chapter = project.value.chapters.find(ch => ch.chapter_number === selectedChapterNumber.value)
      if (chapter) {
        chapter.generation_status = 'waiting_for_confirm' // Or the previous state
      }
    }
    globalAlert.showError(`选择章节版本失败: ${error instanceof Error ? error.message : '未知错误'}`, '选择失败')
  }
}

// 从详情弹窗中选择版本
const selectVersionFromDetail = async () => {
  selectedVersionIndex.value = detailVersionIndex.value
  await selectVersion(detailVersionIndex.value)
  closeVersionDetail()
}

const confirmVersionSelection = async () => {
  await selectVersion(selectedVersionIndex.value)
}

const openEditChapterModal = (chapter: ChapterOutline) => {
  editingChapter.value = chapter
  showEditChapterModal.value = true
}

const saveChapterChanges = async (updatedChapter: ChapterOutline) => {
  try {
    await novelStore.updateChapterOutline(updatedChapter)
    globalAlert.showSuccess('章节大纲已更新', '保存成功')
  } catch (error) {
    console.error('更新章节大纲失败:', error)
    globalAlert.showError(`更新章节大纲失败: ${error instanceof Error ? error.message : '未知错误'}`, '保存失败')
  } finally {
    showEditChapterModal.value = false
  }
}

const evaluateChapter = async () => {
  if (selectedChapterNumber.value !== null) {
    // 保存原始状态，用于失败时恢复
    let previousStatus: "not_generated" | "generating" | "evaluating" | "selecting" | "failed" | "evaluation_failed" | "waiting_for_confirm" | "successful" | undefined
    
    try {
      // 在本地更新章节状态为evaluating以立即反映在UI上
      if (project.value?.chapters) {
        const chapter = project.value.chapters.find(ch => ch.chapter_number === selectedChapterNumber.value)
        if (chapter) {
          previousStatus = chapter.generation_status // 保存原状态
          chapter.generation_status = 'evaluating'
        }
      }
      await novelStore.evaluateChapter(selectedChapterNumber.value)
      
      // 评审完成后，状态会通过store和轮询更新，这里不需要额外操作
      globalAlert.showSuccess('章节评审结果已生成', '评审成功')
    } catch (error) {
      console.error('评审章节失败:', error)
      
      // 错误状态下恢复章节状态为原始状态
      if (project.value?.chapters) {
        const chapter = project.value.chapters.find(ch => ch.chapter_number === selectedChapterNumber.value)
        if (chapter && previousStatus) {
          chapter.generation_status = previousStatus // 恢复为原状态
        }
      }
      
      globalAlert.showError(`评审章节失败: ${error instanceof Error ? error.message : '未知错误'}`, '评审失败')
    }
  }
}

const deleteChapter = async (chapterNumbers: number | number[]) => {
  const numbersToDelete = Array.isArray(chapterNumbers) ? chapterNumbers : [chapterNumbers]
  const confirmationMessage = numbersToDelete.length > 1
    ? `您确定要删除选中的 ${numbersToDelete.length} 个章节吗？这个操作无法撤销。`
    : `您确定要删除第 ${numbersToDelete[0]} 章吗？这个操作无法撤销。`

  if (window.confirm(confirmationMessage)) {
    try {
      await novelStore.deleteChapter(numbersToDelete)
      globalAlert.showSuccess('章节已删除', '操作成功')
      // If the currently selected chapter was deleted, unselect it
      if (selectedChapterNumber.value && numbersToDelete.includes(selectedChapterNumber.value)) {
        selectedChapterNumber.value = null
      }
    } catch (error) {
      console.error('删除章节失败:', error)
      globalAlert.showError(`删除章节失败: ${error instanceof Error ? error.message : '未知错误'}`, '删除失败')
    }
  }
}

const generateOutline = async () => {
  showGenerateOutlineModal.value = true
}

const editChapterContent = async (data: { chapterNumber: number, content: string }) => {
  if (!project.value) return

  try {
    await novelStore.editChapterContent(project.value.id, data.chapterNumber, data.content)
    globalAlert.showSuccess('章节内容已更新', '保存成功')
  } catch (error) {
    console.error('编辑章节内容失败:', error)
    globalAlert.showError(`编辑章节内容失败: ${error instanceof Error ? error.message : '未知错误'}`, '保存失败')
  }
}

const handleGenerateOutline = async (numChapters: number) => {
  if (!project.value) return
  isGeneratingOutline.value = true
  try {
    const startChapter = (project.value.blueprint?.chapter_outline?.length || 0) + 1
    await novelStore.generateChapterOutline(startChapter, numChapters)
    globalAlert.showSuccess('新的章节大纲已生成', '操作成功')
  } catch (error) {
    console.error('生成大纲失败:', error)
    globalAlert.showError(`生成大纲失败: ${error instanceof Error ? error.message : '未知错误'}`, '生成失败')
  } finally {
    isGeneratingOutline.value = false
  }
}

const handleVersionRolledBack = async (chapterNumber: number) => {
  try {
    await novelStore.loadChapter(chapterNumber)
    await novelStore.loadProject(props.id, true)
    globalAlert.showSuccess(`第${chapterNumber}章已完成版本回滚`, '操作成功')
  } catch (error) {
    globalAlert.showError(`回滚后刷新失败: ${error instanceof Error ? error.message : '未知错误'}`)
  }
}

const handleChapterUpdated = async (chapterNumber: number) => {
  try {
    await novelStore.loadChapter(chapterNumber)
    await novelStore.loadProject(props.id, true)
    syncGenerationIndicators()
  } catch (error) {
    console.error('章节更新后刷新失败:', error)
  }
}

const handleWorldGraphUpdated = async () => {
  try {
    await novelStore.loadProject(props.id, true)
  } catch (error) {
    console.error('图谱更新后刷新项目失败:', error)
  }
}

const handleJumpToTaskChapter = (chapterNumber: number) => {
  selectChapter(chapterNumber)
  showTaskCenter.value = false
}

const handleTaskUpdated = async (chapterNumber?: number) => {
  try {
    await novelStore.loadProject(props.id, true)
    if (chapterNumber != null) {
      await novelStore.loadChapter(chapterNumber)
    }
    syncGenerationIndicators()
  } catch (error) {
    console.error('任务状态刷新失败:', error)
  }
}

onMounted(() => {
  document.body.classList.add('m3-novel')
  loadProject()
  loadWritingPresets()
})

watch(
  () => hasActiveWriterTask.value,
  (active) => {
    if (active) {
      void startTaskStream()
    } else {
      stopTaskStream()
      stopChapterStatusPolling()
    }
  },
  { immediate: true }
)

onUnmounted(() => {
  stopTaskStream()
  stopChapterStatusPolling()
  document.body.classList.remove('m3-novel')
})
</script>

<style scoped>
:global(body.m3-novel) {
  --md-font-family: 'Plus Jakarta Sans', 'Noto Sans SC', 'Noto Sans', 'PingFang SC', sans-serif;
  --md-primary: #2563eb;
  --md-primary-light: #4f7bf2;
  --md-primary-dark: #1d4ed8;
  --md-on-primary: #ffffff;
  --md-primary-container: #dbeafe;
  --md-on-primary-container: #0f172a;
  --md-secondary: #0f766e;
  --md-secondary-light: #2dd4bf;
  --md-secondary-dark: #0f766e;
  --md-on-secondary: #ffffff;
  --md-secondary-container: #ccfbf1;
  --md-on-secondary-container: #0f172a;
  --md-surface: #ffffff;
  --md-surface-dim: #f1f5f9;
  --md-surface-container-lowest: #ffffff;
  --md-surface-container-low: #f8fafc;
  --md-surface-container: #f1f5f9;
  --md-surface-container-high: #e2e8f0;
  --md-surface-container-highest: #dbe3ef;
  --md-on-surface: #0f172a;
  --md-on-surface-variant: #475569;
  --md-outline: #d7dde5;
  --md-outline-variant: #e2e8f0;
  --md-error: #dc2626;
  --md-error-container: #fee2e2;
  --md-on-error: #ffffff;
  --md-on-error-container: #7f1d1d;
  color: var(--md-on-surface);
  font-family: var(--md-font-family);
}

.desk-content-frame {
  max-width: var(--app-page-max-wide);
  margin: 0 auto;
}

.m3-shell {
  position: relative;
  background:
    radial-gradient(1200px 600px at 15% -20%, rgba(37, 99, 235, 0.14), transparent 62%),
    radial-gradient(900px 420px at 85% 0%, rgba(45, 212, 191, 0.1), transparent 58%),
    linear-gradient(140deg, #f8fafc 0%, #eef2ff 45%, #edf8ff 100%);
  color: var(--md-on-surface);
  font-family: var(--md-font-family);
  animation: m3-fade 0.6s ease-out both;
}

@media (prefers-reduced-motion: reduce) {
  .m3-shell {
    animation: none;
  }
}

/* 自定义样式 */
.line-clamp-1 {
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.line-clamp-3 {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* 自定义滚动条 */
::-webkit-scrollbar {
  width: 6px;
}

::-webkit-scrollbar-track {
  background: var(--md-surface-container);
  border-radius: 3px;
}

::-webkit-scrollbar-thumb {
  background: var(--md-outline);
  border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
  background: var(--md-on-surface-variant);
}

/* 动画效果 */
@keyframes m3-fade {
  from {
    opacity: 0;
    transform: translateY(18px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
