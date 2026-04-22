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
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useNovelStore } from '@/stores/novel'
import { useAuthStore } from '@/stores/auth'
import { NovelAPI } from '@/api/novel'
import type { WritingPresetItem } from '@/api/novel'
import { useWritingDeskChapterOps } from '@/composables/useWritingDeskChapterOps'
import { useWritingDeskTaskSync } from '@/composables/useWritingDeskTaskSync'
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
const generatingChapter = ref<number | null>(null)
const sidebarOpen = ref(false)
const showEvaluationDetailModal = ref(false)
const showTaskCenter = ref(false)
const showWorldGraphModal = ref(false)
const writingPresets = ref<WritingPresetItem[]>([])
const selectedPresetId = ref('')
const presetLoading = ref(false)
const presetApplying = ref(false)
const presetCollapseToken = ref(0)

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

const evaluatingChapter = computed(() => {
  if (selectedChapter.value?.generation_status === 'evaluating') {
    return selectedChapter.value.chapter_number
  }
  return null
})

const isSelectingVersion = computed(() => {
  return selectedChapter.value?.generation_status === 'selecting'
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

const {
  chapterFailureMessageMap,
  fetchChapterStatus,
  handleTaskUpdated,
  manualReconnectLoading,
  reconnectTaskStreamManually,
  showTaskSyncBanner,
  taskStreamConnected,
  taskSyncDetailText,
  taskSyncStatusText,
} = useWritingDeskTaskSync({
  projectId: props.id,
  project,
  selectedChapterNumber,
  selectedChapterNeedsPolling,
  hasActiveWriterTask,
  token: computed(() => authStore.token),
  loadProject: async (projectId, silent = false) => {
    await novelStore.loadProject(projectId, silent)
  },
  loadChapter: async (chapterNumber) => {
    await novelStore.loadChapter(chapterNumber)
  },
  refreshChapterStatuses: async (projectId) => {
    await novelStore.refreshChapterStatuses(projectId)
  },
  syncGenerationIndicators,
  onUnauthorized: async () => {
    authStore.logout()
    await router.push('/login')
  },
})

const {
  availableVersions,
  chapterGenerationResult,
  closeVersionDetail,
  confirmVersionSelection,
  deleteChapter,
  detailVersionIndex,
  editChapterContent,
  editingChapter,
  evaluateChapter,
  generateChapter,
  generateOutline,
  handleChapterUpdated,
  handleGenerateOutline,
  handleVersionRolledBack,
  hideVersionSelector,
  isCurrentVersion,
  isGeneratingOutline,
  openEditChapterModal,
  regenerateChapter,
  saveChapterChanges,
  selectChapter,
  selectedVersionIndex,
  selectVersionFromDetail,
  showEditChapterModal,
  showGenerateOutlineModal,
  showVersionDetail,
  showVersionDetailModal,
  showVersionSelector,
} = useWritingDeskChapterOps({
  projectId: props.id,
  project,
  selectedChapter,
  selectedChapterNumber,
  chapterFailureMessageMap,
  closeSidebar,
  syncGenerationIndicators,
  generateChapter: async (chapterNumber) => {
    return await novelStore.generateChapter(chapterNumber)
  },
  evaluateChapter: async (chapterNumber) => {
    return await novelStore.evaluateChapter(chapterNumber)
  },
  selectChapterVersion: async (chapterNumber, versionIndex) => {
    await novelStore.selectChapterVersion(chapterNumber, versionIndex)
  },
  updateChapterOutline: async (chapterOutline) => {
    await novelStore.updateChapterOutline(chapterOutline)
  },
  deleteChapter: async (chapterNumbers) => {
    await novelStore.deleteChapter(chapterNumbers)
  },
  generateChapterOutline: async (startChapter, numChapters) => {
    await novelStore.generateChapterOutline(startChapter, numChapters)
  },
  editChapterContent: async (projectId, chapterNumber, content) => {
    await novelStore.editChapterContent(projectId, chapterNumber, content)
  },
  loadChapter: async (chapterNumber) => {
    await novelStore.loadChapter(chapterNumber)
  },
  loadProject: async (projectId, silent = false) => {
    await novelStore.loadProject(projectId, silent)
  },
})

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

onMounted(() => {
  document.body.classList.add('m3-novel')
  loadProject()
  loadWritingPresets()
})

onUnmounted(() => {
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
