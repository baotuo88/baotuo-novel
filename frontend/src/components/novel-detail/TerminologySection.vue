<template>
  <div class="space-y-6">
    <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h3 class="md-title-medium" style="color: var(--md-on-surface);">术语词典</h3>
        <p class="md-body-small" style="color: var(--md-on-surface-variant);">
          统一人名、地名、组织、专有名词；已自动纳入章节生成约束
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <button class="md-btn md-btn-outlined md-ripple" :disabled="isLoading || isSaving" @click="loadDictionary">
          刷新
        </button>
        <button
          v-if="editable"
          class="md-btn md-btn-tonal md-ripple"
          :disabled="isLoading || isSaving"
          @click="addEntry"
        >
          新增词条
        </button>
        <button
          v-if="editable"
          class="md-btn md-btn-filled md-ripple"
          :disabled="isLoading || isSaving"
          @click="saveDictionary"
        >
          {{ isSaving ? '保存中...' : '保存词典' }}
        </button>
      </div>
    </div>

    <div v-if="isLoading" class="flex items-center justify-center py-14">
      <div class="md-spinner"></div>
    </div>

    <div v-else-if="error" class="md-card md-card-outlined p-4" style="border-radius: var(--md-radius-md);">
      <p class="md-body-medium" style="color: var(--md-error);">{{ error }}</p>
    </div>

    <div v-else class="space-y-3">
      <div
        v-if="!entryDrafts.length"
        class="md-card md-card-outlined px-4 py-10 text-center"
        style="border-radius: var(--md-radius-md);"
      >
        <p class="md-body-medium" style="color: var(--md-on-surface);">暂无术语词条</p>
        <p class="md-body-small mt-1" style="color: var(--md-on-surface-variant);">
          先录入常见人名、地名、组织名，可以显著降低写作不一致
        </p>
      </div>

      <div class="space-y-3 max-h-[60vh] overflow-y-auto pr-1">
        <div
          v-for="(item, index) in entryDrafts"
          :key="item.local_id"
          class="md-card md-card-outlined p-4"
          style="border-radius: var(--md-radius-md);"
        >
          <div class="flex flex-wrap items-center justify-between gap-2 mb-3">
            <div class="flex min-w-0 items-center gap-2">
              <span
                class="md-chip md-chip-filter selected px-2 py-1"
                :style="item.enforce
                  ? 'background-color: rgba(52, 168, 83, 0.18); color: #188038;'
                  : 'background-color: rgba(95, 99, 104, 0.16); color: #5f6368;'"
              >
                {{ item.enforce ? '强制统一' : '仅提示' }}
              </span>
              <span class="md-body-medium truncate" style="color: var(--md-on-surface);">
                {{ item.term || '未命名词条' }}
              </span>
            </div>
            <button
              v-if="editable"
              class="md-btn md-btn-text md-ripple"
              style="color: var(--md-error);"
              @click="removeEntry(index)"
            >
              删除
            </button>
          </div>

          <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
            <label class="md-body-small space-y-1">
              <span>术语</span>
              <input v-model="item.term" type="text" class="md-text-field-input" :disabled="!editable" placeholder="如：星海联合体">
            </label>
            <label class="md-body-small space-y-1">
              <span>规范写法</span>
              <input v-model="item.canonical" type="text" class="md-text-field-input" :disabled="!editable" placeholder="不填则默认等于术语">
            </label>
            <label class="md-body-small space-y-1">
              <span>别名（逗号分隔）</span>
              <input v-model="item.aliases_text" type="text" class="md-text-field-input" :disabled="!editable" placeholder="联合体, 星联">
            </label>
            <label class="md-body-small space-y-1">
              <span>分类</span>
              <input v-model="item.category" type="text" class="md-text-field-input" :disabled="!editable" placeholder="角色 / 地名 / 组织">
            </label>
          </div>

          <label class="md-body-small space-y-1 block mt-3">
            <span>备注</span>
            <textarea
              v-model="item.note"
              class="md-textarea w-full min-h-[72px]"
              :disabled="!editable"
              placeholder="可填写使用限制、称谓场景、语气规范等"
            ></textarea>
          </label>

          <label class="inline-flex items-center gap-2 mt-3 md-body-small">
            <input v-model="item.enforce" type="checkbox" :disabled="!editable">
            <span>生成时强制统一到规范写法</span>
          </label>
        </div>
      </div>

      <p v-if="saveHint" class="md-body-small" style="color: var(--md-on-surface-variant);">
        {{ saveHint }}
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { NovelAPI, type TerminologyEntryItem } from '@/api/novel'

interface TerminologyDraft {
  local_id: string
  term: string
  canonical: string
  aliases_text: string
  category: string
  note: string
  enforce: boolean
}

const props = withDefaults(
  defineProps<{
    projectId?: string
    editable?: boolean
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
const entryDrafts = ref<TerminologyDraft[]>([])

const toDraft = (item: TerminologyEntryItem, index: number): TerminologyDraft => ({
  local_id: `term-${index}-${item.term || 'new'}`,
  term: String(item.term || ''),
  canonical: String(item.canonical || ''),
  aliases_text: (item.aliases || []).join(', '),
  category: String(item.category || ''),
  note: String(item.note || ''),
  enforce: Boolean(item.enforce ?? true)
})

const loadDictionary = async () => {
  const projectId = resolvedProjectId.value
  if (!projectId) return
  isLoading.value = true
  error.value = null
  saveHint.value = ''
  try {
    const response = await NovelAPI.getTerminologyDictionary(projectId)
    entryDrafts.value = (response.items || []).map((item, index) => toDraft(item, index))
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载术语词典失败'
  } finally {
    isLoading.value = false
  }
}

const parseAliases = (input: string): string[] =>
  input
    .split(/[，,]/)
    .map((value) => value.trim())
    .filter(Boolean)

const saveDictionary = async () => {
  if (!props.editable) return
  const projectId = resolvedProjectId.value
  if (!projectId) return
  isSaving.value = true
  error.value = null
  saveHint.value = ''
  try {
    const payload: TerminologyEntryItem[] = entryDrafts.value
      .map((item) => ({
        term: item.term.trim(),
        canonical: item.canonical.trim() || item.term.trim(),
        aliases: parseAliases(item.aliases_text),
        category: item.category.trim() || null,
        note: item.note.trim() || null,
        enforce: Boolean(item.enforce)
      }))
      .filter((item) => item.term)

    await NovelAPI.saveTerminologyDictionary(projectId, payload)
    await loadDictionary()
    saveHint.value = '术语词典已保存'
  } catch (err) {
    error.value = err instanceof Error ? err.message : '保存术语词典失败'
  } finally {
    isSaving.value = false
  }
}

const addEntry = () => {
  const localId = `term-new-${Date.now()}`
  entryDrafts.value = [
    ...entryDrafts.value,
    {
      local_id: localId,
      term: '',
      canonical: '',
      aliases_text: '',
      category: '',
      note: '',
      enforce: true
    }
  ]
}

const removeEntry = (index: number) => {
  const next = [...entryDrafts.value]
  next.splice(index, 1)
  entryDrafts.value = next
}

watch(
  () => resolvedProjectId.value,
  () => {
    loadDictionary()
  },
  { immediate: true }
)
</script>
