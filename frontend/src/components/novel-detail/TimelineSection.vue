<template>
  <div class="space-y-6">
    <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h3 class="md-title-medium" style="color: var(--md-on-surface);">故事时间线</h3>
        <p class="md-body-small" style="color: var(--md-on-surface-variant);">
          按章节管理关键事件，生成时会自动参考时间线摘要
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <button class="md-btn md-btn-outlined md-ripple" :disabled="isLoading || isSaving" @click="loadTimeline">
          刷新
        </button>
        <button
          v-if="editable"
          class="md-btn md-btn-tonal md-ripple"
          :disabled="isLoading || isSaving"
          @click="addEvent"
        >
          新增事件
        </button>
        <button
          v-if="editable"
          class="md-btn md-btn-filled md-ripple"
          :disabled="isLoading || isSaving"
          @click="saveTimeline"
        >
          {{ isSaving ? '保存中...' : '保存时间线' }}
        </button>
      </div>
    </div>

    <div v-if="isLoading" class="flex items-center justify-center py-14">
      <div class="md-spinner"></div>
    </div>

    <div v-else-if="error" class="md-card md-card-outlined p-4" style="border-radius: var(--md-radius-md);">
      <p class="md-body-medium" style="color: var(--md-error);">{{ error }}</p>
    </div>

    <div v-else class="space-y-4">
      <div
        v-if="!eventDrafts.length"
        class="md-card md-card-outlined px-4 py-10 text-center"
        style="border-radius: var(--md-radius-md);"
      >
        <p class="md-body-medium" style="color: var(--md-on-surface);">暂无时间线事件</p>
        <p class="md-body-small mt-1" style="color: var(--md-on-surface-variant);">
          可先添加关键事件，例如转折点、冲突升级、真相揭示
        </p>
      </div>

      <div class="space-y-3 max-h-[60vh] overflow-y-auto pr-1">
        <div
          v-for="(item, index) in eventDrafts"
          :key="item.local_id"
          :class="[
            'md-card md-card-outlined p-4 timeline-item',
            item.local_id === focusedLocalId ? 'timeline-item-focused' : ''
          ]"
          style="border-radius: var(--md-radius-md);"
          :data-event-local-id="item.local_id"
        >
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="flex min-w-0 items-center gap-2">
              <span
                class="md-chip md-chip-filter selected px-2 py-1"
                style="background-color: rgba(66, 133, 244, 0.18); color: #1a73e8;"
              >
                第{{ item.chapter_number || '?' }}章
              </span>
              <span class="md-body-medium truncate" style="color: var(--md-on-surface);">
                {{ item.event_title || '未命名事件' }}
              </span>
            </div>
            <div class="flex items-center gap-2">
              <button class="md-btn md-btn-text md-ripple" @click="toggleExpanded(item.local_id)">
                {{ expandedIds.has(item.local_id) ? '收起' : '展开' }}
              </button>
              <button
                v-if="editable"
                class="md-btn md-btn-text md-ripple"
                style="color: var(--md-error);"
                @click="removeEvent(index)"
              >
                删除
              </button>
            </div>
          </div>

          <div v-show="expandedIds.has(item.local_id)" class="mt-4 space-y-4">
            <div class="grid grid-cols-1 gap-3 md:grid-cols-3">
              <label class="md-body-small space-y-1">
                <span>章节号</span>
                <input v-model.number="item.chapter_number" type="number" min="1" class="md-text-field-input" :disabled="!editable">
              </label>
              <label class="md-body-small space-y-1">
                <span>事件类型</span>
                <select v-model="item.event_type" class="md-text-field-input" :disabled="!editable">
                  <option value="major">major</option>
                  <option value="minor">minor</option>
                  <option value="background">background</option>
                </select>
              </label>
              <label class="md-body-small space-y-1">
                <span>重要性 (1-10)</span>
                <input v-model.number="item.importance" type="number" min="1" max="10" class="md-text-field-input" :disabled="!editable">
              </label>
            </div>

            <label class="md-body-small space-y-1 block">
              <span>事件标题</span>
              <input v-model="item.event_title" type="text" class="md-text-field-input" :disabled="!editable">
            </label>

            <div class="grid grid-cols-1 gap-3 md:grid-cols-3">
              <label class="md-body-small space-y-1">
                <span>故事时间</span>
                <input v-model="item.story_time" type="text" class="md-text-field-input" :disabled="!editable" placeholder="如：第三天夜晚">
              </label>
              <label class="md-body-small space-y-1">
                <span>故事日期</span>
                <input v-model="item.story_date" type="text" class="md-text-field-input" :disabled="!editable" placeholder="如：星历 3024-08-17">
              </label>
              <label class="md-body-small space-y-1">
                <span>时间跨度</span>
                <input v-model="item.time_elapsed" type="text" class="md-text-field-input" :disabled="!editable" placeholder="如：距离上事件 2 天">
              </label>
            </div>

            <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
              <label class="md-body-small space-y-1">
                <span>发生地点</span>
                <input v-model="item.location" type="text" class="md-text-field-input" :disabled="!editable">
              </label>
              <label class="md-body-small space-y-1">
                <span>涉及角色（逗号分隔）</span>
                <input
                  v-model="item.involved_characters_text"
                  type="text"
                  class="md-text-field-input"
                  :disabled="!editable"
                  placeholder="主角, 导师, 反派"
                >
              </label>
            </div>

            <label class="md-body-small space-y-1 block">
              <span>事件描述</span>
              <textarea
                v-model="item.event_description"
                class="md-textarea w-full min-h-[88px]"
                :disabled="!editable"
                placeholder="简述这条事件发生了什么"
              ></textarea>
            </label>

            <label class="inline-flex items-center gap-2 md-body-small">
              <input v-model="item.is_turning_point" type="checkbox" :disabled="!editable">
              <span>关键转折点</span>
            </label>
          </div>
        </div>
      </div>

      <p v-if="saveHint" class="md-body-small" style="color: var(--md-on-surface-variant);">
        {{ saveHint }}
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { NovelAPI, type TimelineEventItem } from '@/api/novel'

interface TimelineEventDraft {
  local_id: string
  id?: number
  chapter_number: number
  story_time: string
  story_date: string
  time_elapsed: string
  event_type: string
  event_title: string
  event_description: string
  involved_characters_text: string
  location: string
  importance: number
  is_turning_point: boolean
  extra?: Record<string, any> | null
}

const props = withDefaults(
  defineProps<{
    projectId?: string
    editable?: boolean
    focusChapterNumber?: number | null
    focusEventId?: number | null
  }>(),
  {
    editable: true
  }
)

const route = useRoute()
const resolvedProjectId = computed(() => props.projectId || String(route.params.id || ''))

const isLoading = ref(false)
const isSaving = ref(false)
const error = ref<string | null>(null)
const saveHint = ref('')
const eventDrafts = ref<TimelineEventDraft[]>([])
const expandedIds = ref<Set<string>>(new Set())
const focusedLocalId = ref('')

const toDraft = (event: TimelineEventItem, index: number): TimelineEventDraft => {
  const localId = `evt-${event.id || index}-${event.chapter_number}`
  return {
    local_id: localId,
    id: event.id,
    chapter_number: Number(event.chapter_number || 1),
    story_time: String(event.story_time || ''),
    story_date: String(event.story_date || ''),
    time_elapsed: String(event.time_elapsed || ''),
    event_type: String(event.event_type || 'minor'),
    event_title: String(event.event_title || ''),
    event_description: String(event.event_description || ''),
    involved_characters_text: (event.involved_characters || []).join(', '),
    location: String(event.location || ''),
    importance: Math.max(1, Math.min(10, Number(event.importance || 5))),
    is_turning_point: Boolean(event.is_turning_point),
    extra: event.extra || null
  }
}

const loadTimeline = async () => {
  const projectId = resolvedProjectId.value
  if (!projectId) return
  isLoading.value = true
  error.value = null
  saveHint.value = ''
  try {
    const response = await NovelAPI.getProjectTimeline(projectId)
    const drafts = (response.events || []).map((item, index) => toDraft(item, index))
    eventDrafts.value = drafts
    expandedIds.value = new Set(drafts.slice(0, 3).map((item) => item.local_id))
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载时间线失败'
  } finally {
    isLoading.value = false
  }
}

const parseCharacters = (input: string): string[] => {
  return input
    .split(/[，,]/)
    .map((item) => item.trim())
    .filter(Boolean)
}

const saveTimeline = async () => {
  if (!props.editable) return
  const projectId = resolvedProjectId.value
  if (!projectId) return

  isSaving.value = true
  error.value = null
  saveHint.value = ''
  try {
    const payload: TimelineEventItem[] = eventDrafts.value
      .map((item) => ({
        chapter_number: Math.max(1, Number(item.chapter_number || 1)),
        story_time: item.story_time.trim() || null,
        story_date: item.story_date.trim() || null,
        time_elapsed: item.time_elapsed.trim() || null,
        event_type: item.event_type.trim() || 'minor',
        event_title: item.event_title.trim() || `第${item.chapter_number}章事件`,
        event_description: item.event_description.trim() || null,
        involved_characters: parseCharacters(item.involved_characters_text),
        location: item.location.trim() || null,
        importance: Math.max(1, Math.min(10, Number(item.importance || 5))),
        is_turning_point: Boolean(item.is_turning_point),
        extra: item.extra || null
      }))
      .sort((a, b) => a.chapter_number - b.chapter_number)

    await NovelAPI.saveProjectTimeline(projectId, payload)
    await NovelAPI.invalidateAnalysisCache(projectId).catch(() => undefined)
    await loadTimeline()
    saveHint.value = '时间线已保存，综合诊断缓存已刷新'
  } catch (err) {
    error.value = err instanceof Error ? err.message : '保存失败'
  } finally {
    isSaving.value = false
  }
}

const addEvent = () => {
  const chapterNumber = eventDrafts.value.length
    ? Math.max(...eventDrafts.value.map((item) => Number(item.chapter_number || 1))) + 1
    : 1
  const localId = `evt-new-${Date.now()}`
  const draft: TimelineEventDraft = {
    local_id: localId,
    chapter_number: chapterNumber,
    story_time: '',
    story_date: '',
    time_elapsed: '',
    event_type: 'minor',
    event_title: '',
    event_description: '',
    involved_characters_text: '',
    location: '',
    importance: 5,
    is_turning_point: false,
    extra: null
  }
  eventDrafts.value = [...eventDrafts.value, draft]
  const nextExpanded = new Set(expandedIds.value)
  nextExpanded.add(localId)
  expandedIds.value = nextExpanded
}

const removeEvent = (index: number) => {
  const target = eventDrafts.value[index]
  if (!target) return
  const next = [...eventDrafts.value]
  next.splice(index, 1)
  eventDrafts.value = next
  const nextExpanded = new Set(expandedIds.value)
  nextExpanded.delete(target.local_id)
  expandedIds.value = nextExpanded
}

const toggleExpanded = (localId: string) => {
  const next = new Set(expandedIds.value)
  if (next.has(localId)) next.delete(localId)
  else next.add(localId)
  expandedIds.value = next
}

const applyFocus = async () => {
  const target = props.focusEventId
    ? eventDrafts.value.find((item) => Number(item.id) === Number(props.focusEventId))
    : eventDrafts.value.find((item) => Number(item.chapter_number) === Number(props.focusChapterNumber || 0))
  if (!target) {
    focusedLocalId.value = ''
    return
  }
  focusedLocalId.value = target.local_id
  const nextExpanded = new Set(expandedIds.value)
  nextExpanded.add(target.local_id)
  expandedIds.value = nextExpanded
  await nextTick()
  const element = document.querySelector(`[data-event-local-id="${target.local_id}"]`)
  if (element instanceof HTMLElement) {
    element.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }
}

watch(
  () => resolvedProjectId.value,
  () => {
    loadTimeline()
  },
  { immediate: true }
)

watch(
  () => [props.focusEventId, props.focusChapterNumber, eventDrafts.value.length],
  () => {
    void applyFocus()
  },
  { immediate: true }
)
</script>

<style scoped>
.timeline-item-focused {
  border-color: rgba(37, 99, 235, 0.7);
  box-shadow: 0 0 0 1px rgba(37, 99, 235, 0.2);
}
</style>
