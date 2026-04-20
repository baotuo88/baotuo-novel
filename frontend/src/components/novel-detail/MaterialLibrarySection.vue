<template>
  <div class="material-library space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h3 class="md-title-medium" style="color: var(--md-on-surface);">素材库</h3>
        <p class="md-body-small" style="color: var(--md-on-surface-variant);">
          管理灵感片段、设定参考、对话样本，支持分页检索。
        </p>
      </div>
      <button v-if="editable" class="md-btn md-btn-filled md-ripple" @click="openCreateForm">新增素材</button>
    </div>

    <div class="md-card md-card-outlined p-3 flex flex-wrap items-center gap-3" style="border-radius: var(--md-radius-md);">
      <input
        v-model.trim="keyword"
        type="text"
        class="field-input flex-1 min-w-[180px]"
        placeholder="搜索标题、标签、内容"
        @keyup.enter="reload"
      />
      <select v-model="materialType" class="field-select w-[160px]">
        <option value="">全部类型</option>
        <option value="note">灵感笔记</option>
        <option value="dialogue">对话片段</option>
        <option value="world">世界设定</option>
        <option value="character">人物设定</option>
        <option value="reference">参考资料</option>
      </select>
      <button class="md-btn md-btn-outlined md-ripple" :disabled="loading" @click="reload">
        {{ loading ? '刷新中...' : '刷新' }}
      </button>
    </div>

    <p v-if="errorMessage" class="md-body-small text-red-500">{{ errorMessage }}</p>

    <div v-if="loading" class="md-body-medium md-on-surface-variant py-12 text-center">素材加载中...</div>
    <div v-else-if="!items.length" class="md-body-medium md-on-surface-variant py-12 text-center">暂无素材</div>
    <div v-else class="material-grid">
      <article
        v-for="item in items"
        :key="item.id"
        :class="[
          'md-card md-card-outlined p-4 material-card',
          item.id === focusedMaterialId ? 'material-card-focused' : ''
        ]"
        style="border-radius: var(--md-radius-md);"
        :data-material-id="item.id"
      >
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <h4 class="md-title-small truncate">{{ item.title }}</h4>
            <p class="md-body-small md-on-surface-variant mt-1">
              {{ item.material_type }} · 更新 {{ formatDate(item.updated_at) }}
            </p>
          </div>
          <div class="flex gap-2">
            <button v-if="editable" class="md-btn md-btn-text md-ripple" @click="openEditForm(item)">编辑</button>
            <button v-if="editable" class="md-btn md-btn-text md-ripple text-red-500" @click="removeItem(item)">删除</button>
          </div>
        </div>
        <p class="md-body-small mt-3 material-content">{{ item.content || '（空内容）' }}</p>
        <div v-if="item.tags.length" class="flex flex-wrap gap-2 mt-3">
          <span v-for="tag in item.tags" :key="`${item.id}-${tag}`" class="tag-chip">{{ tag }}</span>
        </div>
        <div v-if="item.source || item.source_url" class="md-body-small md-on-surface-variant mt-3">
          来源：{{ item.source || '-' }}
          <a
            v-if="item.source_url"
            :href="item.source_url"
            target="_blank"
            rel="noopener noreferrer"
            class="source-link"
          >
            打开链接
          </a>
        </div>
      </article>
    </div>

    <div class="flex items-center justify-between">
      <p class="md-body-small md-on-surface-variant">
        共 {{ total }} 条 · 第 {{ page }} / {{ pageCount }} 页
      </p>
      <div class="flex gap-2">
        <button class="md-btn md-btn-outlined md-ripple" :disabled="page <= 1 || loading" @click="changePage(page - 1)">
          上一页
        </button>
        <button class="md-btn md-btn-outlined md-ripple" :disabled="page >= pageCount || loading" @click="changePage(page + 1)">
          下一页
        </button>
      </div>
    </div>

    <div v-if="formVisible" class="md-dialog-overlay" @click.self="closeForm">
      <div class="md-dialog m3-material-dialog">
        <div class="p-4 border-b" style="border-bottom-color: var(--md-outline-variant);">
          <h3 class="md-title-medium">{{ editingId ? '编辑素材' : '新增素材' }}</h3>
        </div>
        <div class="p-4 space-y-3">
          <input v-model.trim="form.title" type="text" class="field-input w-full" placeholder="标题" />
          <select v-model="form.material_type" class="field-select w-full">
            <option value="note">灵感笔记</option>
            <option value="dialogue">对话片段</option>
            <option value="world">世界设定</option>
            <option value="character">人物设定</option>
            <option value="reference">参考资料</option>
          </select>
          <textarea v-model="form.content" rows="7" class="field-textarea w-full" placeholder="素材正文"></textarea>
          <input v-model.trim="form.tagsText" type="text" class="field-input w-full" placeholder="标签，使用逗号分隔" />
          <input v-model.trim="form.source" type="text" class="field-input w-full" placeholder="来源（可选）" />
          <input v-model.trim="form.source_url" type="text" class="field-input w-full" placeholder="来源链接（可选）" />
          <p v-if="formError" class="md-body-small text-red-500">{{ formError }}</p>
        </div>
        <div class="p-4 border-t flex justify-end gap-3" style="border-top-color: var(--md-outline-variant);">
          <button class="md-btn md-btn-text md-ripple" @click="closeForm">取消</button>
          <button class="md-btn md-btn-filled md-ripple" :disabled="saving" @click="submitForm">
            {{ saving ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { NovelAPI, type ProjectMaterialItem } from '@/api/novel'

const props = defineProps<{
  projectId: string
  editable?: boolean
  focusMaterialId?: string | null
  focusQuery?: string | null
}>()

const loading = ref(false)
const saving = ref(false)
const errorMessage = ref('')
const keyword = ref('')
const materialType = ref('')
const page = ref(1)
const pageSize = ref(8)
const total = ref(0)
const items = ref<ProjectMaterialItem[]>([])
const focusedMaterialId = ref('')

const formVisible = ref(false)
const editingId = ref<string | null>(null)
const formError = ref('')
const form = reactive({
  title: '',
  material_type: 'note',
  content: '',
  tagsText: '',
  source: '',
  source_url: ''
})

const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))

const formatDate = (value: string) => {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

const reload = async () => {
  loading.value = true
  errorMessage.value = ''
  try {
    const response = await NovelAPI.listProjectMaterials(props.projectId, {
      page: page.value,
      page_size: pageSize.value,
      keyword: keyword.value || undefined,
      material_type: materialType.value || undefined
    })
    items.value = response.items || []
    total.value = response.total || 0
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '素材加载失败'
  } finally {
    loading.value = false
  }
}

const findMaterialPage = async (
  materialId: string,
  filters?: { keyword?: string; material_type?: string }
): Promise<number | null> => {
  const scanPageSize = 100
  let scanPage = 1
  let totalCount = 0

  do {
    const response = await NovelAPI.listProjectMaterials(props.projectId, {
      page: scanPage,
      page_size: scanPageSize,
      keyword: filters?.keyword,
      material_type: filters?.material_type
    })
    const list = response.items || []
    const index = list.findIndex((item) => item.id === materialId)
    if (index >= 0) {
      const globalIndex = (scanPage - 1) * scanPageSize + index
      return Math.floor(globalIndex / pageSize.value) + 1
    }
    totalCount = Number(response.total || 0)
    scanPage += 1
  } while ((scanPage - 1) * scanPageSize < totalCount)

  return null
}

const scrollToMaterial = async (materialId: string) => {
  await nextTick()
  const node = document.querySelector(`[data-material-id="${materialId}"]`)
  if (node instanceof HTMLElement) {
    node.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
}

const applyFocus = async () => {
  const targetId = String(props.focusMaterialId || '').trim()
  const queryText = String(props.focusQuery || '').trim()
  focusedMaterialId.value = targetId

  if (queryText && keyword.value !== queryText) {
    keyword.value = queryText
    page.value = 1
    await reload()
  } else if (!items.value.length && !loading.value) {
    await reload()
  }

  if (!targetId) return
  if (items.value.some((item) => item.id === targetId)) {
    await scrollToMaterial(targetId)
    return
  }

  const filteredPage = await findMaterialPage(targetId, {
    keyword: keyword.value || undefined,
    material_type: materialType.value || undefined
  })
  if (filteredPage !== null) {
    page.value = filteredPage
    await reload()
    await scrollToMaterial(targetId)
    return
  }

  keyword.value = ''
  materialType.value = ''
  const fallbackPage = await findMaterialPage(targetId)
  if (fallbackPage !== null) {
    page.value = fallbackPage
    await reload()
    await scrollToMaterial(targetId)
  }
}

const changePage = (target: number) => {
  page.value = Math.max(1, Math.min(pageCount.value, target))
  void reload()
}

const openCreateForm = () => {
  editingId.value = null
  form.title = ''
  form.material_type = 'note'
  form.content = ''
  form.tagsText = ''
  form.source = ''
  form.source_url = ''
  formError.value = ''
  formVisible.value = true
}

const openEditForm = (item: ProjectMaterialItem) => {
  editingId.value = item.id
  form.title = item.title
  form.material_type = item.material_type || 'note'
  form.content = item.content || ''
  form.tagsText = (item.tags || []).join(', ')
  form.source = item.source || ''
  form.source_url = item.source_url || ''
  formError.value = ''
  formVisible.value = true
}

const closeForm = () => {
  formVisible.value = false
}

const submitForm = async () => {
  if (!form.title.trim()) {
    formError.value = '标题不能为空'
    return
  }
  saving.value = true
  formError.value = ''
  const payload = {
    title: form.title.trim(),
    material_type: form.material_type.trim() || 'note',
    content: form.content,
    tags: form.tagsText
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean),
    source: form.source.trim() || null,
    source_url: form.source_url.trim() || null
  }
  try {
    if (editingId.value) {
      await NovelAPI.updateProjectMaterial(props.projectId, editingId.value, payload)
    } else {
      await NovelAPI.createProjectMaterial(props.projectId, payload)
      page.value = 1
    }
    formVisible.value = false
    await reload()
  } catch (error) {
    formError.value = error instanceof Error ? error.message : '保存失败'
  } finally {
    saving.value = false
  }
}

const removeItem = async (item: ProjectMaterialItem) => {
  const confirmed = window.confirm(`确认删除素材「${item.title}」？`)
  if (!confirmed) return
  try {
    await NovelAPI.deleteProjectMaterial(props.projectId, item.id)
    if (items.value.length === 1 && page.value > 1) {
      page.value -= 1
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '删除失败'
  }
}

watch(
  () => props.projectId,
  () => {
    page.value = 1
    keyword.value = ''
    materialType.value = ''
    focusedMaterialId.value = ''
    void reload()
  },
  { immediate: true }
)

watch(
  () => [props.focusMaterialId, props.focusQuery],
  () => {
    void applyFocus()
  },
  { immediate: true }
)
</script>

<style scoped>
.material-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}

.material-card {
  min-height: 220px;
}

.material-card-focused {
  border-color: rgba(37, 99, 235, 0.72);
  box-shadow: 0 0 0 1px rgba(37, 99, 235, 0.26);
}

.material-content {
  display: -webkit-box;
  -webkit-line-clamp: 5;
  -webkit-box-orient: vertical;
  overflow: hidden;
  white-space: pre-wrap;
}

.tag-chip {
  border-radius: 999px;
  padding: 2px 8px;
  font-size: 12px;
  color: #1d4ed8;
  background: rgba(37, 99, 235, 0.12);
}

.field-input,
.field-select,
.field-textarea {
  border: 1px solid var(--md-outline-variant);
  border-radius: 8px;
  background: color-mix(in srgb, var(--md-surface-container-low) 84%, white 16%);
  color: var(--md-on-surface);
  padding: 8px 10px;
}

.field-textarea {
  min-height: 120px;
}

.m3-material-dialog {
  width: min(720px, calc(100vw - 24px));
  max-height: min(88vh, 840px);
  overflow: auto;
  border-radius: var(--md-radius-xl);
}

.source-link {
  margin-left: 8px;
  color: #1d4ed8;
}
</style>
