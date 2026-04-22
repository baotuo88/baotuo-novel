<!-- AIMETA P=小说详情壳_详情页布局容器|R=详情页布局_导航|NR=不含具体内容|E=component:NovelDetailShell|X=internal|A=布局组件|D=vue|S=dom|RD=./README.ai -->
<template>
  <div class="novel-detail-shell h-[100dvh] flex flex-col overflow-hidden md-surface">
    <!-- Material 3 Top App Bar -->
    <header class="md-top-app-bar sticky top-0 z-40">
      <div class="detail-frame w-full flex items-center px-4 h-16">
        <!-- Leading: Menu Button (Mobile) -->
        <button
          class="md-icon-btn lg:hidden mr-2"
          @click="toggleSidebar"
          aria-label="Toggle sidebar"
        >
          <svg class="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>

        <!-- Title -->
        <div class="flex-1 min-w-0">
          <h1 class="md-title-large truncate" style="color: var(--md-on-surface);">
            {{ formattedTitle }}
          </h1>
          <p v-if="overviewMeta.updated_at" class="md-body-small" style="color: var(--md-on-surface-variant);">
            最近更新：{{ formatDateTime(overviewMeta.updated_at) }}
          </p>
        </div>

        <!-- Trailing: Actions -->
        <div class="flex items-center gap-2 flex-shrink-0">
          <button
            class="md-btn md-btn-outlined md-ripple"
            @click="goBack"
          >
            <svg class="w-5 h-5 hidden sm:block" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
            <span class="hidden sm:inline">返回列表</span>
            <span class="sm:hidden">返回</span>
          </button>
          <button
            v-if="!isAdmin"
            class="md-btn md-btn-filled md-ripple"
            @click="goToWritingDesk"
          >
            <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
            </svg>
            <span class="hidden sm:inline">开始创作</span>
            <span class="sm:hidden">创作</span>
          </button>
        </div>
      </div>
    </header>

    <!-- Main Content -->
    <div class="detail-frame flex w-full flex-1 min-h-0 overflow-hidden">
      <!-- Material 3 Navigation Drawer -->
      <aside
        class="detail-sidebar fixed left-0 bottom-0 z-30 md-surface transform transition-transform duration-300 lg:translate-x-0"
        :class="isSidebarOpen ? 'translate-x-0' : '-translate-x-full'"
        style="border-right: 1px solid var(--md-outline-variant);"
      >
        <!-- Drawer Header -->
        <div class="flex items-center gap-3 px-6 py-4" style="border-bottom: 1px solid var(--md-outline-variant);">
          <div class="w-10 h-10 rounded-full flex items-center justify-center" style="background-color: var(--md-primary-container);">
            <svg class="w-5 h-5" style="color: var(--md-on-primary-container);" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
            </svg>
          </div>
          <span class="md-title-medium" style="color: var(--md-on-surface);">
            {{ isAdmin ? '内容视图' : '蓝图导航' }}
          </span>
        </div>

        <!-- Navigation Items -->
        <nav class="detail-sidebar-nav px-3 py-4 space-y-1 overflow-y-auto">
          <button
            v-for="section in sections"
            :key="section.key"
            type="button"
            @click="switchSection(section.key)"
            class="md-nav-drawer-item w-full md-ripple"
            :class="{ 'active': activeSection === section.key }"
          >
            <span
              class="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full transition-all duration-200"
              :style="activeSection === section.key
                ? 'background-color: var(--md-primary); color: var(--md-on-primary);'
                : 'background-color: var(--md-surface-container); color: var(--md-on-surface-variant);'"
            >
              <component :is="getSectionIcon(section.key)" class="w-5 h-5" />
            </span>
            <span class="text-left flex-1">
              <span class="block md-label-large">{{ section.label }}</span>
              <span class="md-body-small" style="color: var(--md-on-surface-variant);">{{ section.description }}</span>
            </span>
          </button>
        </nav>
      </aside>

      <!-- Sidebar Overlay (Mobile) -->
      <transition
        enter-active-class="transition-opacity duration-300"
        leave-active-class="transition-opacity duration-300"
        enter-from-class="opacity-0"
        leave-to-class="opacity-0"
      >
        <div
          v-if="isSidebarOpen"
          class="fixed inset-0 z-20 lg:hidden"
          style="background-color: rgba(0, 0, 0, 0.32);"
          @click="toggleSidebar"
        ></div>
      </transition>

      <!-- Main Content Area -->
      <div class="detail-content-wrap flex-1 min-h-0 flex flex-col h-full">
        <div class="detail-content-inner flex-1 min-h-0 h-full p-4 sm:p-6 lg:p-8 flex flex-col overflow-hidden box-border">
          <div class="flex-1 flex flex-col min-h-0 h-full">
            <!-- Material 3 Card -->
            <div 
              class="md-card md-card-elevated flex-1 h-full p-6 sm:p-8 min-h-[20rem] flex flex-col box-border" 
              :class="contentCardClass"
              style="border-radius: var(--md-radius-lg);"
            >
              <!-- Loading State -->
              <div v-if="isSectionLoading" class="flex flex-col items-center justify-center py-20 sm:py-28">
                <div class="md-spinner"></div>
                <p class="mt-4 md-body-medium" style="color: var(--md-on-surface-variant);">加载中...</p>
              </div>

              <!-- Error State -->
              <div v-else-if="currentError" class="flex flex-col items-center justify-center py-20 sm:py-28 space-y-4">
                <div class="w-16 h-16 rounded-full flex items-center justify-center" style="background-color: var(--md-error-container);">
                  <svg class="w-8 h-8" style="color: var(--md-error);" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <p class="md-body-large text-center" style="color: var(--md-on-surface);">{{ currentError }}</p>
                <button
                  class="md-btn md-btn-filled md-ripple"
                  @click="reloadSection(activeSection, true)"
                >
                  重试
                </button>
              </div>

              <!-- Content -->
              <component
                v-else
                :is="currentComponent"
                v-bind="componentProps"
                :class="componentContainerClass"
                @edit="handleSectionEdit"
                @add="startAddChapter"
                @refresh="handleWorldGraphRefresh"
                @navigate="handleGraphNavigate"
              />
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Blueprint Edit Modal -->
    <BlueprintEditModal
      v-if="!isAdmin"
      :show="isModalOpen"
      :title="modalTitle"
      :content="modalContent"
      :field="modalField"
      @close="isModalOpen = false"
      @save="handleSave"
    />

    <!-- Material 3 Add Chapter Modal -->
    <transition
      enter-active-class="md-scale-enter-active"
      leave-active-class="md-scale-leave-active"
      enter-from-class="md-scale-enter-from"
      leave-to-class="md-scale-leave-to"
    >
      <div v-if="isAddChapterModalOpen && !isAdmin" class="md-dialog-overlay">
        <div class="absolute inset-0" @click="cancelNewChapter"></div>
        <div class="md-dialog relative w-full max-w-lg mx-4" @click.stop>
          <div class="md-dialog-header">
            <h3 class="md-dialog-title">新增章节大纲</h3>
          </div>
          <div class="md-dialog-content space-y-6">
            <div class="md-text-field">
              <label for="new-chapter-title" class="md-text-field-label">
                章节标题
              </label>
              <input
                id="new-chapter-title"
                v-model="newChapterTitle"
                type="text"
                class="md-text-field-input"
                placeholder="例如：意外的相遇"
              >
            </div>
            <div class="md-text-field">
              <label for="new-chapter-summary" class="md-text-field-label">
                章节摘要
              </label>
              <textarea
                id="new-chapter-summary"
                v-model="newChapterSummary"
                rows="4"
                class="md-textarea w-full"
                placeholder="简要描述本章发生的主要事件"
              ></textarea>
            </div>
          </div>
          <div class="md-dialog-actions">
            <button
              type="button"
              class="md-btn md-btn-text md-ripple"
              @click="cancelNewChapter"
            >
              取消
            </button>
            <button
              type="button"
              class="md-btn md-btn-filled md-ripple"
              @click="saveNewChapter"
            >
              保存
            </button>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useNovelDetailSections } from '@/composables/useNovelDetailSections'
import { useNovelStore } from '@/stores/novel'
import { NovelAPI } from '@/api/novel'
import type { NovelProject } from '@/api/novel'
import { formatDateTime } from '@/utils/date'
import BlueprintEditModal from '@/components/BlueprintEditModal.vue'
import type { SectionKey } from '@/components/novel-detail/sectionRegistry'

interface Props {
  isAdmin?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  isAdmin: false
})

const route = useRoute()
const router = useRouter()
const novelStore = useNovelStore()

const projectId = route.params.id as string
const isSidebarOpen = ref(typeof window !== 'undefined' ? window.innerWidth >= 1024 : true)

// Modal state (user mode only)
const isModalOpen = ref(false)
const modalTitle = ref('')
const modalContent = ref<any>('')
const modalField = ref('')

// Add chapter modal state (user mode only)
const isAddChapterModalOpen = ref(false)
const newChapterTitle = ref('')
const newChapterSummary = ref('')
const originalBodyOverflow = ref('')

const novel = computed(() => !props.isAdmin ? novelStore.currentProject as NovelProject | null : null)

const formattedTitle = computed(() => {
  const title = overviewMeta.title || '加载中...'
  return title.startsWith('《') && title.endsWith('》') ? title : `《${title}》`
})

const {
  activeSection,
  componentContainerClass,
  componentProps,
  contentCardClass,
  currentComponent,
  currentError,
  getSectionIcon,
  handleGraphNavigate,
  handleWorldGraphRefresh,
  initializeFromRoute,
  isSectionLoading,
  loadSection,
  overviewMeta,
  reloadSection,
  sectionData,
  sections,
  switchSection: switchSectionInternal,
} = useNovelDetailSections({
  isAdmin: props.isAdmin,
  projectId,
  route,
  router,
})

// 懒加载完整项目（仅在需要编辑时）
const ensureProjectLoaded = async () => {
  if (props.isAdmin || !projectId) return
  if (novel.value) return // 已加载
  await novelStore.loadProject(projectId)
}

const toggleSidebar = () => {
  isSidebarOpen.value = !isSidebarOpen.value
}

const handleResize = () => {
  if (typeof window === 'undefined') return
  isSidebarOpen.value = window.innerWidth >= 1024
}

const goBack = () => router.push(props.isAdmin ? '/admin' : '/workspace')

const goToWritingDesk = async () => {
  await ensureProjectLoaded()
  const project = novel.value
  if (!project) return
  const path = project.title === '未命名灵感' ? `/inspiration?project_id=${project.id}` : `/novel/${project.id}`
  router.push(path)
}

const switchSection = (section: SectionKey) => {
  switchSectionInternal(section, () => {
    isSidebarOpen.value = false
  })
}

const handleSectionEdit = (payload: { field: string; title: string; value: any }) => {
  if (props.isAdmin) return
  modalField.value = payload.field
  modalTitle.value = payload.title
  modalContent.value = payload.value
  isModalOpen.value = true
}

const resolveSectionKey = (field: string): SectionKey => {
  if (field.startsWith('world_setting')) return 'world_setting'
  if (field.startsWith('characters')) return 'characters'
  if (field.startsWith('relationships')) return 'relationships'
  if (field.startsWith('chapter_outline')) return 'chapter_outline'
  return 'overview'
}

const handleSave = async (data: { field: string; content: any }) => {
  if (props.isAdmin) return
  await ensureProjectLoaded()
  const project = novel.value
  if (!project) return

  const { field, content } = data
  const payload: Record<string, any> = {}

  if (field.includes('.')) {
    const [parentField, childField] = field.split('.')
    payload[parentField] = {
      ...(project.blueprint?.[parentField as keyof typeof project.blueprint] as Record<string, any> | undefined),
      [childField]: content
    }
  } else {
    payload[field] = content
  }

  try {
    const updatedProject = await NovelAPI.updateBlueprint(project.id, payload)
    novelStore.setCurrentProject(updatedProject)
    const sectionToReload = resolveSectionKey(field)
    await loadSection(sectionToReload, true)
    if (sectionToReload !== 'overview') {
      await loadSection('overview', true)
    }
    isModalOpen.value = false
  } catch (error) {
    console.error('保存变更失败:', error)
  }
}

const startAddChapter = async () => {
  if (props.isAdmin) return
  await ensureProjectLoaded()
  const outline = sectionData.chapter_outline?.chapter_outline || novel.value?.blueprint?.chapter_outline || []
  const nextNumber = outline.length > 0 ? Math.max(...outline.map((item: any) => item.chapter_number)) + 1 : 1
  newChapterTitle.value = `新章节 ${nextNumber}`
  newChapterSummary.value = ''
  isAddChapterModalOpen.value = true
}

const cancelNewChapter = () => {
  isAddChapterModalOpen.value = false
}

const saveNewChapter = async () => {
  if (props.isAdmin) return
  await ensureProjectLoaded()
  const project = novel.value
  if (!project) return
  if (!newChapterTitle.value.trim()) {
    alert('章节标题不能为空')
    return
  }

  const existingOutline = project.blueprint?.chapter_outline || []
  const nextNumber = existingOutline.length > 0 ? Math.max(...existingOutline.map(ch => ch.chapter_number)) + 1 : 1
  const newOutline = [...existingOutline, {
    chapter_number: nextNumber,
    title: newChapterTitle.value,
    summary: newChapterSummary.value
  }]

  try {
    const updatedProject = await NovelAPI.updateBlueprint(project.id, { chapter_outline: newOutline })
    novelStore.setCurrentProject(updatedProject)
    await loadSection('chapter_outline', true)
    isAddChapterModalOpen.value = false
  } catch (error) {
    console.error('新增章节失败:', error)
  }
}

onMounted(async () => {
  if (typeof window !== 'undefined') {
    window.addEventListener('resize', handleResize)
  }
  if (typeof document !== 'undefined') {
    originalBodyOverflow.value = document.body.style.overflow
    document.body.style.overflow = 'hidden'
  }

  const initialSection = initializeFromRoute()

  // 只加载必要的 section 数据，不预加载完整项目
  await loadSection('overview', true)
  if (initialSection && initialSection !== 'overview') {
    await loadSection(initialSection, true)
  } else {
    loadSection('world_setting')
  }
})

onBeforeUnmount(() => {
  if (typeof window !== 'undefined') {
    window.removeEventListener('resize', handleResize)
  }
  if (typeof document !== 'undefined') {
    document.body.style.overflow = originalBodyOverflow.value || ''
  }
})
</script>

<style scoped>
.novel-detail-shell {
  background:
    radial-gradient(880px 280px at -6% -22%, color-mix(in srgb, var(--md-primary-container) 38%, transparent), transparent 72%),
    radial-gradient(760px 260px at 106% -18%, color-mix(in srgb, var(--md-secondary-container) 34%, transparent), transparent 70%),
    color-mix(in srgb, var(--md-surface-dim) 74%, #ffffff 26%);
}

.novel-detail-shell :deep(.md-top-app-bar) {
  background:
    radial-gradient(620px 180px at -12% -48%, color-mix(in srgb, var(--md-primary-container) 52%, transparent), transparent 72%),
    color-mix(in srgb, var(--md-surface) 88%, #ffffff 12%);
  border-bottom: 1px solid color-mix(in srgb, var(--md-outline-variant) 78%, transparent);
  box-shadow: 0 10px 20px rgba(15, 23, 42, 0.08);
}

.detail-frame {
  max-width: var(--app-page-max-wide);
  margin: 0 auto;
}

.detail-sidebar {
  width: 19rem;
  top: 68px;
  background:
    radial-gradient(420px 140px at -18% -24%, color-mix(in srgb, var(--md-primary-container) 36%, transparent), transparent 74%),
    color-mix(in srgb, var(--md-surface) 92%, #ffffff 8%);
  backdrop-filter: blur(8px);
}

.detail-sidebar-nav {
  height: calc(100% - 5rem);
}

.detail-content-wrap {
  margin-left: 0;
}

.detail-content-inner {
  padding-inline: clamp(12px, 2vw, 28px);
  padding-block: clamp(12px, 1.6vw, 24px);
}

@media (min-width: 1024px) {
  .detail-content-wrap {
    margin-left: 19rem;
  }
}

@media (max-width: 1023px) {
  .detail-sidebar {
    width: min(19rem, calc(100vw - 36px));
  }
}

/* Material 3 Transition Classes */
.md-scale-enter-active,
.md-scale-leave-active {
  transition: all 250ms cubic-bezier(0.2, 0, 0, 1);
}

.md-scale-enter-from,
.md-scale-leave-to {
  opacity: 0;
  transform: scale(0.95);
}

/* Smooth scrollbar */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background: var(--md-outline);
  border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
  background: var(--md-on-surface-variant);
}
</style>
