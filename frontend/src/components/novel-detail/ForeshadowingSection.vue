<template>
  <div class="space-y-6">
    <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h3 class="md-title-medium" style="color: var(--md-on-surface);">伏笔看板</h3>
        <p class="md-body-small" style="color: var(--md-on-surface-variant);">
          管理伏笔埋设、回收、放弃与提醒，降低剧情遗忘风险
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <button class="md-btn md-btn-outlined md-ripple" :disabled="isLoading || isOperating" @click="loadAllData">
          刷新
        </button>
        <button
          v-if="editable"
          class="md-btn md-btn-tonal md-ripple"
          :disabled="isLoading || isOperating"
          @click="showCreateForm = !showCreateForm"
        >
          {{ showCreateForm ? '收起新增' : '新增伏笔' }}
        </button>
      </div>
    </div>

    <div v-if="analysis" class="grid grid-cols-2 gap-3 md:grid-cols-4">
      <div class="md-card md-card-outlined p-3 text-center" style="border-radius: var(--md-radius-md);">
        <p class="md-body-small" style="color: var(--md-on-surface-variant);">总数</p>
        <p class="md-title-large" style="color: var(--md-primary);">{{ analysis.total_foreshadowings }}</p>
      </div>
      <div class="md-card md-card-outlined p-3 text-center" style="border-radius: var(--md-radius-md);">
        <p class="md-body-small" style="color: var(--md-on-surface-variant);">已回收</p>
        <p class="md-title-large" style="color: #188038;">{{ analysis.resolved_count }}</p>
      </div>
      <div class="md-card md-card-outlined p-3 text-center" style="border-radius: var(--md-radius-md);">
        <p class="md-body-small" style="color: var(--md-on-surface-variant);">未回收</p>
        <p class="md-title-large" style="color: #b06000;">{{ analysis.unresolved_count }}</p>
      </div>
      <div class="md-card md-card-outlined p-3 text-center" style="border-radius: var(--md-radius-md);">
        <p class="md-body-small" style="color: var(--md-on-surface-variant);">已放弃</p>
        <p class="md-title-large" style="color: #b3261e;">{{ analysis.abandoned_count }}</p>
      </div>
    </div>

    <div
      v-if="editable && showCreateForm"
      class="md-card md-card-outlined p-4 space-y-3"
      style="border-radius: var(--md-radius-md);"
    >
      <div class="grid grid-cols-1 gap-3 md:grid-cols-3">
        <label class="md-body-small space-y-1">
          <span>章节号</span>
          <input v-model.number="createDraft.chapter_number" min="1" type="number" class="md-text-field-input">
        </label>
        <label class="md-body-small space-y-1">
          <span>类型</span>
          <input v-model="createDraft.type" type="text" class="md-text-field-input" placeholder="clue / mystery / hint">
        </label>
        <label class="md-body-small space-y-1">
          <span>关键词（逗号分隔）</span>
          <input v-model="createDraft.keywords_text" type="text" class="md-text-field-input">
        </label>
      </div>
      <label class="md-body-small space-y-1 block">
        <span>伏笔内容</span>
        <textarea v-model="createDraft.content" class="md-textarea w-full min-h-[90px]" placeholder="这条伏笔埋了什么信息"></textarea>
      </label>
      <label class="md-body-small space-y-1 block">
        <span>作者备注（可选）</span>
        <input v-model="createDraft.author_note" type="text" class="md-text-field-input">
      </label>
      <div class="flex items-center justify-end gap-2">
        <button class="md-btn md-btn-text md-ripple" @click="showCreateForm = false">取消</button>
        <button class="md-btn md-btn-filled md-ripple" :disabled="isOperating" @click="createForeshadowing">
          {{ isOperating ? '处理中...' : '创建伏笔' }}
        </button>
      </div>
    </div>

    <div class="flex flex-wrap gap-2">
      <button
        v-for="tab in statusTabs"
        :key="tab.key"
        class="md-chip md-chip-filter md-ripple"
        :class="{ selected: activeStatusTab === tab.key }"
        @click="activeStatusTab = tab.key"
      >
        {{ tab.label }}
        <span class="ml-1 opacity-70">({{ tab.count }})</span>
      </button>
    </div>

    <div v-if="isLoading" class="flex items-center justify-center py-14">
      <div class="md-spinner"></div>
    </div>

    <div v-else-if="error" class="md-card md-card-outlined p-4" style="border-radius: var(--md-radius-md);">
      <p class="md-body-medium" style="color: var(--md-error);">{{ error }}</p>
    </div>

    <div v-else class="space-y-3">
      <div
        v-if="!filteredItems.length"
        class="md-card md-card-outlined px-4 py-10 text-center"
        style="border-radius: var(--md-radius-md);"
      >
        <p class="md-body-medium" style="color: var(--md-on-surface);">当前筛选下暂无伏笔</p>
      </div>

      <div
        v-for="item in filteredItems"
        :key="item.id"
        :class="[
          'md-card md-card-outlined p-4 foreshadowing-item',
          item.id === focusedForeshadowingId ? 'foreshadowing-item-focused' : ''
        ]"
        style="border-radius: var(--md-radius-md);"
        :data-foreshadowing-id="item.id"
      >
        <div class="flex flex-wrap items-start justify-between gap-2">
          <div class="flex-1 min-w-0">
            <div class="flex flex-wrap items-center gap-2">
              <span
                class="md-chip md-chip-filter selected px-2 py-1"
                :style="`background-color: ${getStatusColor(item.status)}22; color: ${getStatusColor(item.status)};`"
              >
                {{ getStatusLabel(item.status) }}
              </span>
              <span class="md-chip md-chip-assist px-2 py-1">第{{ item.chapter_number }}章</span>
              <span class="md-chip md-chip-assist px-2 py-1">{{ item.type }}</span>
              <span v-if="item.resolved_chapter_number" class="md-chip md-chip-assist px-2 py-1">
                回收章：{{ item.resolved_chapter_number }}
              </span>
            </div>
            <p class="md-body-medium mt-2 whitespace-pre-line" style="color: var(--md-on-surface);">{{ item.content }}</p>
            <p v-if="item.author_note" class="md-body-small mt-2" style="color: var(--md-on-surface-variant);">
              备注：{{ item.author_note }}
            </p>
          </div>

          <div v-if="editable && isUnresolved(item.status)" class="flex flex-wrap items-center gap-2">
            <button class="md-btn md-btn-text md-ripple" @click="startResolve(item)">标记回收</button>
            <button class="md-btn md-btn-text md-ripple" style="color: var(--md-error);" @click="abandonForeshadowing(item)">
              放弃
            </button>
          </div>
        </div>

        <div
          v-if="editable && resolveTargetId === item.id"
          class="mt-3 border-t pt-3"
          style="border-color: var(--md-outline-variant);"
        >
          <div class="grid grid-cols-1 gap-3 md:grid-cols-3">
            <label class="md-body-small space-y-1">
              <span>回收章节号</span>
              <input v-model.number="resolveDraft.resolved_chapter_number" min="1" type="number" class="md-text-field-input">
            </label>
            <label class="md-body-small space-y-1">
              <span>回收方式</span>
              <input v-model="resolveDraft.resolution_type" type="text" class="md-text-field-input" placeholder="direct / twist">
            </label>
            <label class="md-body-small space-y-1">
              <span>质量评分（可选）</span>
              <input v-model.number="resolveDraft.quality_score" min="1" max="10" type="number" class="md-text-field-input">
            </label>
          </div>
          <label class="md-body-small space-y-1 block mt-3">
            <span>回收说明</span>
            <textarea
              v-model="resolveDraft.resolution_text"
              class="md-textarea w-full min-h-[88px]"
              placeholder="说明这条伏笔如何在该章节被解释/兑现"
            ></textarea>
          </label>
          <div class="flex items-center justify-end gap-2 mt-3">
            <button class="md-btn md-btn-text md-ripple" @click="cancelResolve">取消</button>
            <button class="md-btn md-btn-filled md-ripple" :disabled="isOperating" @click="confirmResolve">
              {{ isOperating ? '处理中...' : '确认回收' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <div class="md-card md-card-outlined p-4 space-y-3" style="border-radius: var(--md-radius-md);">
      <h4 class="md-title-small" style="color: var(--md-on-surface);">伏笔提醒</h4>
      <div v-if="!reminders.length" class="md-body-small" style="color: var(--md-on-surface-variant);">
        当前没有活跃提醒
      </div>
      <div v-else class="space-y-2">
        <div
          v-for="reminder in reminders"
          :key="reminder.id"
          class="rounded-lg border p-3 flex flex-wrap items-start justify-between gap-2"
          style="border-color: var(--md-outline-variant);"
        >
          <div class="flex-1 min-w-0">
            <p class="md-body-medium" style="color: var(--md-on-surface);">{{ reminder.message }}</p>
            <p class="md-body-small mt-1" style="color: var(--md-on-surface-variant);">
              类型：{{ reminder.reminder_type }} · 伏笔 #{{ reminder.foreshadowing_id }}
            </p>
          </div>
          <button
            v-if="editable"
            class="md-btn md-btn-text md-ripple"
            :disabled="isOperating"
            @click="dismissReminder(reminder.id)"
          >
            忽略
          </button>
        </div>
      </div>
    </div>

    <div
      v-if="analysis?.recommendations?.length"
      class="md-card md-card-outlined p-4 space-y-2"
      style="border-radius: var(--md-radius-md);"
    >
      <h4 class="md-title-small" style="color: var(--md-on-surface);">分析建议</h4>
      <p
        v-for="(item, index) in analysis.recommendations"
        :key="`rec-${index}`"
        class="md-body-small"
        style="color: var(--md-on-surface-variant);"
      >
        {{ index + 1 }}. {{ item }}
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  NovelAPI,
  type ForeshadowingAnalysisResponse,
  type ForeshadowingBoardItem,
  type ForeshadowingReminderItem
} from '@/api/novel'

const props = withDefaults(
  defineProps<{
    projectId?: string
    editable?: boolean
    focusChapterNumber?: number | null
    focusForeshadowingId?: number | null
  }>(),
  {
    editable: true
  }
)

const route = useRoute()
const resolvedProjectId = computed(() => props.projectId || String(route.params.id || ''))

const isLoading = ref(false)
const isOperating = ref(false)
const error = ref<string | null>(null)
const showCreateForm = ref(false)
const focusedForeshadowingId = ref<number | null>(null)

const foreshadowings = ref<ForeshadowingBoardItem[]>([])
const analysis = ref<ForeshadowingAnalysisResponse | null>(null)
const reminders = ref<ForeshadowingReminderItem[]>([])

const activeStatusTab = ref<'all' | 'unresolved' | 'resolved' | 'abandoned'>('all')

const createDraft = ref({
  chapter_number: 1,
  content: '',
  type: 'clue',
  keywords_text: '',
  author_note: ''
})

const resolveTargetId = ref<number | null>(null)
const resolveDraft = ref({
  resolved_chapter_number: 1,
  resolution_text: '',
  resolution_type: 'direct',
  quality_score: undefined as number | undefined
})

const resolvedStatuses = new Set(['resolved', 'revealed', 'paid_off'])

const statusGroup = (status: string): 'unresolved' | 'resolved' | 'abandoned' => {
  if (resolvedStatuses.has(status)) return 'resolved'
  if (status === 'abandoned') return 'abandoned'
  return 'unresolved'
}

const isUnresolved = (status: string) => statusGroup(status) === 'unresolved'

const filteredItems = computed(() => {
  if (activeStatusTab.value === 'all') return foreshadowings.value
  return foreshadowings.value.filter((item) => statusGroup(item.status) === activeStatusTab.value)
})

const statusTabs = computed(() => {
  const total = foreshadowings.value.length
  const unresolvedCount = foreshadowings.value.filter((item) => statusGroup(item.status) === 'unresolved').length
  const resolvedCount = foreshadowings.value.filter((item) => statusGroup(item.status) === 'resolved').length
  const abandonedCount = foreshadowings.value.filter((item) => statusGroup(item.status) === 'abandoned').length
  return [
    { key: 'all' as const, label: '全部', count: total },
    { key: 'unresolved' as const, label: '待处理', count: unresolvedCount },
    { key: 'resolved' as const, label: '已回收', count: resolvedCount },
    { key: 'abandoned' as const, label: '已放弃', count: abandonedCount }
  ]
})

const getStatusLabel = (status: string) => {
  const labels: Record<string, string> = {
    open: '待处理',
    planted: '已埋设',
    developing: '推进中',
    partial: '部分回收',
    resolved: '已回收',
    revealed: '已揭示',
    paid_off: '已兑现',
    abandoned: '已放弃'
  }
  return labels[status] || status
}

const getStatusColor = (status: string) => {
  const colors: Record<string, string> = {
    open: '#b06000',
    planted: '#b06000',
    developing: '#7b61ff',
    partial: '#00639b',
    resolved: '#188038',
    revealed: '#188038',
    paid_off: '#188038',
    abandoned: '#b3261e'
  }
  return colors[status] || '#5f6368'
}

const parseCommaItems = (input: string): string[] =>
  input
    .split(/[，,]/)
    .map((item) => item.trim())
    .filter(Boolean)

const loadAllData = async () => {
  const projectId = resolvedProjectId.value
  if (!projectId) return

  isLoading.value = true
  error.value = null
  try {
    const [listRes, analysisRes, remindersRes] = await Promise.all([
      NovelAPI.listForeshadowings(projectId, { limit: 500, offset: 0 }),
      NovelAPI.getForeshadowingAnalysis(projectId),
      NovelAPI.getForeshadowingReminders(projectId, 50)
    ])
    foreshadowings.value = (listRes.data || []).slice().sort((a, b) => a.chapter_number - b.chapter_number)
    analysis.value = analysisRes
    reminders.value = remindersRes.data || []
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载伏笔数据失败'
  } finally {
    isLoading.value = false
  }
}

const createForeshadowing = async () => {
  const projectId = resolvedProjectId.value
  if (!projectId) return
  if (!createDraft.value.content.trim()) {
    error.value = '请填写伏笔内容'
    return
  }
  isOperating.value = true
  error.value = null
  try {
    await NovelAPI.createForeshadowing(projectId, {
      chapter_number: Math.max(1, Number(createDraft.value.chapter_number || 1)),
      content: createDraft.value.content.trim(),
      type: createDraft.value.type.trim() || 'clue',
      keywords: parseCommaItems(createDraft.value.keywords_text),
      author_note: createDraft.value.author_note.trim() || undefined
    })
    createDraft.value = {
      chapter_number: createDraft.value.chapter_number,
      content: '',
      type: 'clue',
      keywords_text: '',
      author_note: ''
    }
    showCreateForm.value = false
    await NovelAPI.invalidateAnalysisCache(projectId).catch(() => undefined)
    await loadAllData()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '创建伏笔失败'
  } finally {
    isOperating.value = false
  }
}

const startResolve = (item: ForeshadowingBoardItem) => {
  resolveTargetId.value = item.id
  resolveDraft.value = {
    resolved_chapter_number: Math.max(item.chapter_number, Number(item.resolved_chapter_number || item.chapter_number)),
    resolution_text: '',
    resolution_type: 'direct',
    quality_score: undefined
  }
}

const cancelResolve = () => {
  resolveTargetId.value = null
}

const confirmResolve = async () => {
  const projectId = resolvedProjectId.value
  const foreshadowingId = resolveTargetId.value
  if (!projectId || !foreshadowingId) return
  if (!resolveDraft.value.resolution_text.trim()) {
    error.value = '请填写回收说明'
    return
  }
  isOperating.value = true
  error.value = null
  try {
    await NovelAPI.resolveForeshadowing(projectId, foreshadowingId, {
      resolved_chapter_number: Math.max(1, Number(resolveDraft.value.resolved_chapter_number || 1)),
      resolution_text: resolveDraft.value.resolution_text.trim(),
      resolution_type: resolveDraft.value.resolution_type.trim() || 'direct',
      quality_score: resolveDraft.value.quality_score
    })
    resolveTargetId.value = null
    await NovelAPI.invalidateAnalysisCache(projectId).catch(() => undefined)
    await loadAllData()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '回收伏笔失败'
  } finally {
    isOperating.value = false
  }
}

const abandonForeshadowing = async (item: ForeshadowingBoardItem) => {
  const projectId = resolvedProjectId.value
  if (!projectId) return
  const reason = window.prompt('请输入放弃原因（可选）', '') ?? ''
  isOperating.value = true
  error.value = null
  try {
    await NovelAPI.abandonForeshadowing(projectId, item.id, {
      reason: reason.trim() || undefined
    })
    await NovelAPI.invalidateAnalysisCache(projectId).catch(() => undefined)
    await loadAllData()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '放弃伏笔失败'
  } finally {
    isOperating.value = false
  }
}

const dismissReminder = async (reminderId: number) => {
  const projectId = resolvedProjectId.value
  if (!projectId) return
  isOperating.value = true
  error.value = null
  try {
    await NovelAPI.dismissForeshadowingReminder(projectId, reminderId)
    await loadAllData()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '忽略提醒失败'
  } finally {
    isOperating.value = false
  }
}

const applyFocus = async () => {
  const byId = props.focusForeshadowingId
    ? foreshadowings.value.find((item) => item.id === Number(props.focusForeshadowingId))
    : null
  const byChapter = !byId && props.focusChapterNumber
    ? foreshadowings.value.find((item) => item.chapter_number === Number(props.focusChapterNumber))
    : null
  const target = byId || byChapter
  if (!target) {
    focusedForeshadowingId.value = null
    return
  }
  focusedForeshadowingId.value = target.id
  activeStatusTab.value = target.status === 'abandoned'
    ? 'abandoned'
    : (resolvedStatuses.has(target.status) ? 'resolved' : 'unresolved')
  await nextTick()
  const element = document.querySelector(`[data-foreshadowing-id="${target.id}"]`)
  if (element instanceof HTMLElement) {
    element.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }
}

watch(
  () => resolvedProjectId.value,
  () => {
    loadAllData()
  },
  { immediate: true }
)

watch(
  () => [props.focusForeshadowingId, props.focusChapterNumber, foreshadowings.value.length],
  () => {
    void applyFocus()
  },
  { immediate: true }
)
</script>

<style scoped>
.foreshadowing-item-focused {
  border-color: rgba(37, 99, 235, 0.7);
  box-shadow: 0 0 0 1px rgba(37, 99, 235, 0.2);
}
</style>
