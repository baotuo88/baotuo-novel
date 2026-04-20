<!-- AIMETA P=全局搜索区_跨模块检索与跳转|R=项目内全文检索_结果定位|NR=不含后端实现|E=component:GlobalSearchSection|X=ui|A=搜索组件|D=vue|S=dom,net|RD=./README.ai -->
<template>
  <div class="global-search-section flex flex-col h-full min-h-0">
    <header class="search-header">
      <h3 class="search-title">全局搜索</h3>
      <p class="search-subtitle">跨章节、素材库、时间线、伏笔、术语和蓝图统一检索。</p>
    </header>

    <div class="search-toolbar">
      <input
        v-model="query"
        class="search-input"
        type="text"
        placeholder="输入关键词，例如：遗迹、主角母亲、时间悖论"
        @keyup.enter="runSearch"
      >
      <button class="search-btn" :disabled="loading" @click="runSearch">
        {{ loading ? '搜索中...' : '搜索' }}
      </button>
    </div>

    <div class="scope-grid">
      <label v-for="scope in scopeOptions" :key="scope.key" class="scope-item">
        <input v-model="scopeState[scope.key]" type="checkbox">
        <span>{{ scope.label }}</span>
      </label>
    </div>

    <div v-if="error" class="search-error">{{ error }}</div>

    <div class="search-meta">
      <span v-if="!loading">结果：{{ resultTotal }} 条（展示 {{ results.length }} 条）</span>
      <span v-else>正在检索，请稍候...</span>
    </div>

    <div class="search-result-list flex-1 min-h-0 overflow-y-auto">
      <div v-if="!loading && results.length === 0" class="search-empty">
        输入关键词后开始搜索。
      </div>
      <article v-for="item in results" :key="item.id" class="result-item">
        <div class="result-head">
          <span class="result-scope">{{ scopeLabel(item.scope) }}</span>
          <span class="result-score">相关度 {{ item.score.toFixed(1) }}</span>
        </div>
        <h4 class="result-title">{{ item.title }}</h4>
        <p class="result-snippet">{{ item.snippet || '无摘要' }}</p>
        <div class="result-actions">
          <button class="locate-btn" @click="locateResult(item)">定位</button>
        </div>
      </article>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'

import { NovelAPI, type GlobalSearchItem } from '@/api/novel'

interface Props {
  projectId: string
  initialQuery?: string | null
}

const props = defineProps<Props>()
const emit = defineEmits<{
  navigate: [payload: {
    section: string
    chapterNumber?: number
    eventId?: number
    foreshadowingId?: number
    materialId?: string
    term?: string
    query?: string
  }]
}>()

const query = ref('')
const loading = ref(false)
const error = ref('')
const results = ref<GlobalSearchItem[]>([])
const resultTotal = ref(0)

const scopeOptions = [
  { key: 'blueprint', label: '蓝图' },
  { key: 'chapter_outline', label: '章节大纲' },
  { key: 'chapters', label: '章节正文' },
  { key: 'materials', label: '素材库' },
  { key: 'timeline', label: '时间线' },
  { key: 'foreshadowing', label: '伏笔' },
  { key: 'terminology', label: '术语' }
] as const

type ScopeKey = typeof scopeOptions[number]['key']
const scopeState = reactive<Record<ScopeKey, boolean>>({
  blueprint: true,
  chapter_outline: true,
  chapters: true,
  materials: true,
  timeline: true,
  foreshadowing: true,
  terminology: true
})

const selectedScopes = computed(() =>
  scopeOptions.filter((item) => scopeState[item.key]).map((item) => item.key)
)

const scopeLabel = (scope: string) => {
  const found = scopeOptions.find((item) => item.key === scope)
  return found?.label || scope
}

const inferSection = (scope: string): string => {
  if (scope === 'materials') return 'material_library'
  if (scope === 'blueprint') return 'overview'
  return scope
}

const runSearch = async () => {
  const keyword = query.value.trim()
  error.value = ''
  if (!keyword) {
    results.value = []
    resultTotal.value = 0
    return
  }
  loading.value = true
  try {
    const response = await NovelAPI.searchProjectGlobal(props.projectId, {
      q: keyword,
      limit: 120,
      scopes: selectedScopes.value
    })
    results.value = response.items || []
    resultTotal.value = Number(response.total || 0)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '搜索失败'
  } finally {
    loading.value = false
  }
}

const locateResult = (item: GlobalSearchItem) => {
  const anchor = item.anchor || ({} as Record<string, any>)
  emit('navigate', {
    section: String(anchor.section || inferSection(item.scope)),
    chapterNumber: anchor.chapter_number ?? item.chapter_number ?? undefined,
    eventId: anchor.timeline_event_id ?? undefined,
    foreshadowingId: anchor.foreshadowing_id ?? undefined,
    materialId: anchor.material_id ?? undefined,
    term: anchor.term ?? undefined,
    query: query.value.trim() || undefined
  })
}

watch(
  () => props.initialQuery,
  (value) => {
    const normalized = String(value || '').trim()
    if (!normalized) return
    if (!query.value.trim()) {
      query.value = normalized
    }
  },
  { immediate: true }
)
</script>

<style scoped>
.search-header {
  margin-bottom: 12px;
}

.search-title {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 700;
  color: #111827;
}

.search-subtitle {
  margin: 6px 0 0;
  color: #4b5563;
  font-size: 0.92rem;
}

.search-toolbar {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 10px;
}

.search-input {
  height: 42px;
  border-radius: 10px;
  border: 1px solid #d1d5db;
  padding: 0 12px;
  font-size: 0.95rem;
}

.search-input:focus {
  outline: none;
  border-color: #2563eb;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.16);
}

.search-btn {
  height: 42px;
  border: none;
  border-radius: 10px;
  padding: 0 14px;
  background: #2563eb;
  color: #fff;
  font-weight: 600;
  cursor: pointer;
}

.search-btn:disabled {
  opacity: 0.66;
  cursor: not-allowed;
}

.scope-grid {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px 16px;
}

.scope-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.86rem;
  color: #374151;
}

.search-error {
  margin-top: 10px;
  color: #b91c1c;
  background: #fee2e2;
  border: 1px solid #fecaca;
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 0.86rem;
}

.search-meta {
  margin-top: 10px;
  color: #6b7280;
  font-size: 0.84rem;
}

.search-result-list {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.search-empty {
  border: 1px dashed #d1d5db;
  border-radius: 10px;
  padding: 20px 12px;
  color: #6b7280;
  text-align: center;
}

.result-item {
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 12px;
  background: #fff;
}

.result-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.result-scope {
  background: #e0e7ff;
  color: #1e3a8a;
  border-radius: 999px;
  padding: 3px 8px;
  font-size: 0.76rem;
  font-weight: 600;
}

.result-score {
  color: #6b7280;
  font-size: 0.78rem;
}

.result-title {
  margin: 8px 0 4px;
  color: #111827;
  font-size: 1rem;
  line-height: 1.4;
}

.result-snippet {
  margin: 0;
  color: #4b5563;
  line-height: 1.52;
  font-size: 0.9rem;
  word-break: break-word;
}

.result-actions {
  margin-top: 8px;
  display: flex;
  justify-content: flex-end;
}

.locate-btn {
  border: 1px solid #c7d2fe;
  border-radius: 8px;
  background: #eef2ff;
  color: #1e3a8a;
  padding: 4px 10px;
  font-size: 0.82rem;
  cursor: pointer;
}

.locate-btn:hover {
  background: #e0e7ff;
}

@media (max-width: 760px) {
  .search-toolbar {
    grid-template-columns: 1fr;
  }

  .search-btn {
    width: 100%;
  }
}
</style>
