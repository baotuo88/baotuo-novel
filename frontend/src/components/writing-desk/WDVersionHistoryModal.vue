<template>
  <Teleport to="body">
    <div v-if="show" class="md-dialog-overlay" @click.self="emit('close')">
      <div class="md-dialog m3-version-history-dialog flex flex-col">
        <div class="p-5 border-b flex items-center justify-between" style="border-bottom-color: var(--md-outline-variant);">
          <div>
            <h3 class="md-title-large font-semibold">版本 Diff 与回滚</h3>
            <p class="md-body-small md-on-surface-variant mt-1">第{{ chapterNumber }}章 · 共 {{ versions.length }} 个版本</p>
          </div>
          <button class="md-icon-btn md-ripple" @click="emit('close')">
            <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" />
            </svg>
          </button>
        </div>

        <div class="p-5 border-b flex flex-wrap items-end gap-3" style="border-bottom-color: var(--md-outline-variant);">
          <div class="diff-select-group">
            <label class="md-text-field-label">基准版本</label>
            <select v-model.number="baseVersionId" class="md-select">
              <option v-for="item in versions" :key="item.id" :value="item.id">
                {{ versionOptionLabel(item) }}
              </option>
            </select>
          </div>

          <div class="diff-select-group">
            <label class="md-text-field-label">对比版本</label>
            <select v-model.number="compareVersionId" class="md-select">
              <option v-for="item in compareCandidates" :key="item.id" :value="item.id">
                {{ versionOptionLabel(item) }}
              </option>
            </select>
          </div>

          <button class="md-btn md-btn-tonal md-ripple" :disabled="loading" @click="loadVersions">
            {{ loading ? '刷新中...' : '刷新' }}
          </button>
          <button
            class="md-btn md-btn-filled md-ripple"
            :disabled="rollbackLoading || !compareVersionId"
            @click="rollbackToCompareVersion"
          >
            {{ rollbackLoading ? '回滚中...' : '回滚到对比版本' }}
          </button>
        </div>

        <div class="p-5 border-b flex items-center gap-4 md-body-small md-on-surface-variant" style="border-bottom-color: var(--md-outline-variant);">
          <span>新增 {{ diffResult.added }} 行</span>
          <span>删除 {{ diffResult.removed }} 行</span>
          <span>未变更 {{ diffResult.equal }} 行</span>
          <span v-if="diffResult.truncated" class="diff-truncated">Diff 已截断展示</span>
        </div>

        <div class="flex-1 overflow-auto p-4">
          <div v-if="loading" class="md-body-medium md-on-surface-variant py-6 text-center">正在加载版本数据...</div>
          <div v-else-if="!versions.length" class="md-body-medium md-on-surface-variant py-6 text-center">暂无版本记录</div>
          <div v-else-if="visibleDiffLines.length === 0" class="md-body-medium md-on-surface-variant py-6 text-center">请选择两个不同版本进行对比</div>
          <div v-else class="diff-block">
            <div
              v-for="(line, idx) in visibleDiffLines"
              :key="`${line.type}-${idx}`"
              :class="[
                'diff-line',
                line.type === 'add' ? 'diff-add' : '',
                line.type === 'remove' ? 'diff-remove' : '',
                line.type === 'equal' ? 'diff-equal' : ''
              ]"
            >
              <span class="diff-prefix">{{ line.type === 'add' ? '+' : line.type === 'remove' ? '-' : ' ' }}</span>
              <span class="diff-text">{{ line.text || ' ' }}</span>
            </div>
            <div v-if="hasMoreLines" class="md-body-small md-on-surface-variant text-center py-2">仅展示前 {{ maxVisibleLines }} 行</div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  NovelAPI,
  type ChapterVersionDetail,
  type ChapterVersionDiffResponse
} from '@/api/novel'
import { buildLineDiff } from '@/utils/textDiff'
import { globalAlert } from '@/composables/useAlert'

interface Props {
  show: boolean
  projectId?: string
  chapterNumber: number
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'rolledBack', chapterNumber: number): void
}>()

const loading = ref(false)
const rollbackLoading = ref(false)
const versions = ref<ChapterVersionDetail[]>([])
const baseVersionId = ref<number>(0)
const compareVersionId = ref<number>(0)
const diffPayload = ref<ChapterVersionDiffResponse | null>(null)
const maxVisibleLines = 420

const compareCandidates = computed(() =>
  versions.value.filter((item) => item.id !== baseVersionId.value)
)

const diffResult = computed(() => {
  const payload = diffPayload.value
  if (!payload) {
    return { lines: [], added: 0, removed: 0, equal: 0, truncated: false }
  }
  return buildLineDiff(payload.base_content, payload.compare_content, {
    maxLines: 1400,
    maxMatrixCells: 900_000
  })
})

const visibleDiffLines = computed(() => diffResult.value.lines.slice(0, maxVisibleLines))
const hasMoreLines = computed(() => diffResult.value.lines.length > maxVisibleLines)

const versionOptionLabel = (item: ChapterVersionDetail) => {
  const created = new Date(item.created_at).toLocaleString('zh-CN', { hour12: false })
  const selectedTag = item.is_selected ? '（当前）' : ''
  const label = item.version_label || `v${item.id}`
  return `${label}${selectedTag} · ${item.word_count}字 · ${created}`
}

const loadDiff = async () => {
  if (!props.projectId || !baseVersionId.value || !compareVersionId.value) return
  if (baseVersionId.value === compareVersionId.value) {
    diffPayload.value = null
    return
  }
  diffPayload.value = await NovelAPI.getChapterVersionDiff(
    props.projectId,
    props.chapterNumber,
    baseVersionId.value,
    compareVersionId.value
  )
}

const loadVersions = async () => {
  if (!props.projectId) return
  loading.value = true
  try {
    const response = await NovelAPI.listChapterVersions(props.projectId, props.chapterNumber)
    versions.value = response.versions || []

    const selectedId = response.selected_version_id || versions.value[0]?.id || 0
    baseVersionId.value = selectedId

    const firstCompare = versions.value.find((item) => item.id !== selectedId)?.id || 0
    compareVersionId.value = firstCompare

    await loadDiff()
  } catch (error) {
    globalAlert.showError(`加载版本失败: ${error instanceof Error ? error.message : '未知错误'}`)
  } finally {
    loading.value = false
  }
}

const rollbackToCompareVersion = async () => {
  if (!props.projectId || !compareVersionId.value) return
  const target = versions.value.find((item) => item.id === compareVersionId.value)
  const confirmed = await globalAlert.showConfirm(
    `确认回滚到版本「${target?.version_label || `v${compareVersionId.value}`}」？`,
    '版本回滚确认'
  )
  if (!confirmed) return

  rollbackLoading.value = true
  try {
    const result = await NovelAPI.rollbackChapterVersion(props.projectId, props.chapterNumber, {
      version_id: compareVersionId.value,
      reason: 'ui_rollback'
    })
    globalAlert.showSuccess(result.message || '版本回滚成功')
    await loadVersions()
    emit('rolledBack', props.chapterNumber)
  } catch (error) {
    globalAlert.showError(`回滚失败: ${error instanceof Error ? error.message : '未知错误'}`)
  } finally {
    rollbackLoading.value = false
  }
}

watch(
  () => props.show,
  (show) => {
    if (show) {
      void loadVersions()
    }
  }
)

watch(
  () => [baseVersionId.value, compareVersionId.value],
  () => {
    if (!props.show) return
    void loadDiff()
  }
)
</script>

<style scoped>
.m3-version-history-dialog {
  width: min(1200px, calc(100vw - 32px));
  height: min(88vh, 860px);
  border-radius: var(--md-radius-xl);
}

.diff-select-group {
  min-width: 260px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.md-select {
  width: 100%;
  min-height: 38px;
  border: 1px solid var(--md-outline-variant);
  border-radius: var(--md-radius-md);
  padding: 0 10px;
  background: var(--md-surface);
  color: var(--md-on-surface);
}

.diff-truncated {
  color: #b45309;
}

.diff-block {
  border: 1px solid var(--md-outline-variant);
  border-radius: var(--md-radius-lg);
  overflow: hidden;
}

.diff-line {
  display: grid;
  grid-template-columns: 24px 1fr;
  column-gap: 6px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.45;
  padding: 3px 10px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.12);
}

.diff-prefix {
  user-select: none;
  color: var(--md-on-surface-variant);
}

.diff-text {
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--md-on-surface);
}

.diff-add {
  background: rgba(16, 185, 129, 0.12);
}

.diff-remove {
  background: rgba(239, 68, 68, 0.12);
}

.diff-equal {
  background: var(--md-surface);
}

@media (max-width: 767px) {
  .m3-version-history-dialog {
    width: calc(100vw - 16px);
    height: calc(100vh - 16px);
    height: calc(100dvh - 16px);
  }

  .diff-select-group {
    min-width: 100%;
  }
}
</style>
