<!-- AIMETA P=提示词管理_AI提示模板管理|R=提示词CRUD|NR=不含模型调用|E=component:PromptManagement|X=ui|A=管理组件|D=vue|S=dom,net|RD=./README.ai -->
<template>
  <n-card :bordered="false" class="admin-card">
    <template #header>
      <div class="card-header">
        <span class="card-title">提示词管理</span>
        <n-space :size="12">
          <n-button quaternary size="small" @click="fetchPrompts" :loading="loading">
            刷新
          </n-button>
          <n-button type="primary" size="small" @click="openCreateModal">
            新建 Prompt
          </n-button>
        </n-space>
      </div>
    </template>

    <n-space vertical size="large">
      <n-alert v-if="error" type="error" closable @close="error = null">
        {{ error }}
      </n-alert>

      <n-card size="small" embedded class="preset-card">
        <template #header>
          <div class="card-header">
            <span class="preset-title">写作 Preset 中心</span>
            <n-space :size="8">
              <n-button size="small" quaternary @click="fetchPresets" :loading="presetLoading">
                刷新预设
              </n-button>
              <n-button size="small" type="primary" tertiary @click="newPreset">
                新建预设
              </n-button>
            </n-space>
          </div>
        </template>

        <div :class="['preset-layout', { mobile: isMobile }]">
          <div class="preset-sidebar">
            <n-input
              v-model:value="presetQuery"
              clearable
              size="small"
              placeholder="搜索预设名 / ID"
              class="sidebar-search"
            />
            <n-scrollbar class="preset-scroll">
              <n-empty v-if="!filteredPresets.length && !presetLoading" description="暂无预设" />
              <n-space v-else vertical size="small">
                <n-button
                  v-for="preset in pagedPresets"
                  :key="preset.preset_id"
                  block
                  quaternary
                  :ghost="selectedPreset?.preset_id !== preset.preset_id"
                  type="primary"
                  @click="selectPreset(preset)"
                >
                  <div class="preset-item">
                    <span class="preset-name">{{ preset.name }}</span>
                    <n-space :size="4">
                      <n-tag v-if="preset.is_active" size="tiny" type="success">默认</n-tag>
                      <n-tag v-if="preset.is_builtin" size="tiny" type="info">内置</n-tag>
                    </n-space>
                  </div>
                </n-button>
              </n-space>
            </n-scrollbar>
            <n-pagination
              v-if="filteredPresets.length > presetPagination.pageSize"
              v-model:page="presetPagination.page"
              v-model:page-size="presetPagination.pageSize"
              :page-count="presetPageCount"
              :page-sizes="[8, 12, 16]"
              size="small"
              show-size-picker
              class="sidebar-pagination"
            />
          </div>

          <div class="preset-editor">
            <n-form label-placement="top">
              <n-form-item label="Preset ID（英文/数字/_/-）">
                <n-input
                  v-model:value="presetForm.preset_id"
                  :disabled="Boolean(selectedPreset?.is_builtin)"
                  placeholder="例如 fast-action-custom"
                />
              </n-form-item>
              <n-form-item label="显示名称">
                <n-input v-model:value="presetForm.name" placeholder="例如：快节奏爽文（自定义）" />
              </n-form-item>
              <n-form-item label="描述">
                <n-input v-model:value="presetForm.description" placeholder="简述适用场景" />
              </n-form-item>
              <n-form-item label="写作 Prompt">
                <n-select
                  v-model:value="presetForm.prompt_name"
                  :options="promptNameOptions"
                  filterable
                  tag
                  placeholder="选择或输入 Prompt 名称"
                />
              </n-form-item>
              <div class="preset-number-row">
                <n-form-item label="Temperature">
                  <n-input-number v-model:value="presetForm.temperature" :min="0" :max="2" :step="0.05" />
                </n-form-item>
                <n-form-item label="Top P">
                  <n-input-number v-model:value="presetForm.top_p" :min="0" :max="1" :step="0.05" clearable />
                </n-form-item>
                <n-form-item label="Max Tokens">
                  <n-input-number v-model:value="presetForm.max_tokens" :min="64" :max="32000" :step="128" clearable />
                </n-form-item>
              </div>
              <n-form-item label="风格规则">
                <n-dynamic-tags v-model:value="presetForm.style_rules" size="small" placeholder="输入规则后回车" />
              </n-form-item>
              <n-form-item label="写作指令前缀">
                <n-input
                  v-model:value="presetForm.writing_notes_prefix"
                  type="textarea"
                  :autosize="{ minRows: 2, maxRows: 6 }"
                  placeholder="生成时会自动附加在写作指令前"
                />
              </n-form-item>
            </n-form>
            <n-space justify="end">
              <n-button
                quaternary
                :disabled="!selectedPreset"
                @click="duplicatePreset"
              >
                复制预设
              </n-button>
              <n-button
                quaternary
                type="warning"
                :disabled="!selectedPreset || selectedPreset.is_active"
                :loading="presetActivating"
                @click="setActivePreset(selectedPreset?.preset_id || null)"
              >
                设为默认
              </n-button>
              <n-button
                quaternary
                :disabled="!activePreset"
                :loading="presetActivating"
                @click="setActivePreset(null)"
              >
                清空默认
              </n-button>
              <n-popconfirm
                v-if="selectedPreset && !selectedPreset.is_builtin"
                placement="bottom"
                positive-text="删除"
                negative-text="取消"
                type="error"
                @positive-click="removePreset"
              >
                <template #trigger>
                  <n-button type="error" quaternary :loading="presetDeleting">删除预设</n-button>
                </template>
                确认删除该预设？
              </n-popconfirm>
              <n-button type="primary" :loading="presetSaving" @click="savePreset">保存预设</n-button>
            </n-space>
          </div>
        </div>
      </n-card>

      <n-spin :show="loading">
        <div :class="['prompt-layout', { mobile: isMobile }]">
          <div class="prompt-sidebar">
            <n-input
              v-model:value="promptQuery"
              clearable
              size="small"
              placeholder="搜索提示词名称"
              class="sidebar-search"
            />
            <n-scrollbar class="prompt-scroll">
              <n-empty v-if="!filteredPrompts.length && !loading" description="暂无提示词" />
              <n-space v-else vertical size="small">
                <n-button
                  v-for="prompt in pagedPrompts"
                  :key="prompt.id"
                  type="primary"
                  :ghost="selectedPrompt?.id !== prompt.id"
                  quaternary
                  block
                  @click="selectPrompt(prompt)"
                >
                  <div class="prompt-item">
                    <span class="prompt-name">{{ prompt.title || prompt.name }}</span>
                    <n-tag v-if="prompt.tags?.length" size="tiny" type="info">
                      {{ prompt.tags.length }}
                    </n-tag>
                  </div>
                </n-button>
              </n-space>
            </n-scrollbar>
            <n-pagination
              v-if="filteredPrompts.length > promptPagination.pageSize"
              v-model:page="promptPagination.page"
              v-model:page-size="promptPagination.pageSize"
              :page-count="promptPageCount"
              :page-sizes="[8, 12, 16]"
              size="small"
              show-size-picker
              class="sidebar-pagination"
            />
          </div>

          <div class="prompt-editor">
            <div v-if="!selectedPrompt" class="empty-editor">
              <n-empty description="请选择一个提示词以编辑" />
            </div>
            <div v-else class="editor-content">
              <n-form label-placement="top" :model="editForm">
                <n-form-item label="唯一标识">
                  <n-input v-model:value="editForm.name" disabled />
                </n-form-item>
                <n-form-item label="标题">
                  <n-input
                    v-model:value="editForm.title"
                    placeholder="用于后台识别的标题，可为空"
                  />
                </n-form-item>
                <n-form-item label="标签">
                  <n-dynamic-tags
                    v-model:value="editForm.tags"
                    size="small"
                    placeholder="输入标签后回车"
                  />
                </n-form-item>
                <n-form-item label="提示词内容">
                  <n-input
                    v-model:value="editForm.content"
                    type="textarea"
                    :autosize="{ minRows: isMobile ? 8 : 16, maxRows: 40 }"
                    placeholder="请输入完整的提示词内容..."
                    class="prompt-textarea"
                  />
                </n-form-item>
              </n-form>
              <n-space justify="end">
                <n-popconfirm
                  v-if="selectedPrompt"
                  placement="bottom"
                  positive-text="删除"
                  negative-text="取消"
                  type="error"
                  @positive-click="deletePrompt"
                >
                  <template #trigger>
                    <n-button type="error" quaternary :loading="deleting">
                      删除
                    </n-button>
                  </template>
                  确认删除该 Prompt？
                </n-popconfirm>
                <n-button type="primary" :loading="saving" @click="savePrompt">
                  保存修改
                </n-button>
              </n-space>
            </div>
          </div>
        </div>
      </n-spin>
    </n-space>
  </n-card>

  <n-modal v-model:show="createModalVisible" preset="card" title="新建 Prompt" class="prompt-modal">
    <n-form label-placement="top" :model="createForm">
      <n-form-item label="唯一标识（必填）">
        <n-input v-model:value="createForm.name" placeholder="例如 concept / outline" />
      </n-form-item>
      <n-form-item label="标题">
        <n-input v-model:value="createForm.title" placeholder="可选，用于后台展示" />
      </n-form-item>
      <n-form-item label="标签">
        <n-dynamic-tags
          v-model:value="createForm.tags"
          size="small"
          placeholder="输入标签后回车"
        />
      </n-form-item>
      <n-form-item label="内容">
        <n-input
          v-model:value="createForm.content"
          type="textarea"
          :autosize="{ minRows: 10, maxRows: 30 }"
          placeholder="输入提示词内容..."
        />
      </n-form-item>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button quaternary @click="closeCreateModal">取消</n-button>
        <n-button type="primary" :loading="creating" @click="createPrompt">创建</n-button>
      </n-space>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import {
  NAlert,
  NButton,
  NCard,
  NDynamicTags,
  NEmpty,
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  NModal,
  NPagination,
  NPopconfirm,
  NScrollbar,
  NSelect,
  NSpace,
  NSpin,
  NTag
} from 'naive-ui'

import {
  AdminAPI,
  type PromptCreatePayload,
  type PromptItem,
  type WritingPresetItem,
  type WritingPresetUpsertPayload
} from '@/api/admin'
import { useAlert } from '@/composables/useAlert'

const { showAlert } = useAlert()

const prompts = ref<PromptItem[]>([])
const selectedPrompt = ref<PromptItem | null>(null)
const loading = ref(false)
const saving = ref(false)
const deleting = ref(false)
const creating = ref(false)
const error = ref<string | null>(null)
const editForm = reactive({
  name: '',
  title: '',
  content: '',
  tags: [] as string[]
})

const createModalVisible = ref(false)
const createForm = reactive<PromptCreatePayload>({
  name: '',
  title: '',
  content: '',
  tags: []
})

const presets = ref<WritingPresetItem[]>([])
const selectedPreset = ref<WritingPresetItem | null>(null)
const presetLoading = ref(false)
const presetSaving = ref(false)
const presetDeleting = ref(false)
const presetActivating = ref(false)
const presetForm = reactive<WritingPresetUpsertPayload>({
  preset_id: '',
  name: '',
  description: '',
  prompt_name: 'writing_v2',
  temperature: 0.9,
  top_p: null,
  max_tokens: null,
  style_rules: [],
  writing_notes_prefix: ''
})
const activePreset = computed(() => presets.value.find((item) => item.is_active) || null)
const promptNameOptions = computed(() => {
  const options = prompts.value.map((item) => ({
    label: item.name,
    value: item.name
  }))
  if (!options.find((item) => item.value === 'writing_v2')) {
    options.unshift({ label: 'writing_v2', value: 'writing_v2' })
  }
  return options
})

const isMobile = ref(false)
const presetQuery = ref('')
const promptQuery = ref('')
const presetPagination = reactive({
  page: 1,
  pageSize: 10
})
const promptPagination = reactive({
  page: 1,
  pageSize: 10
})

const filteredPresets = computed(() => {
  const query = presetQuery.value.trim().toLowerCase()
  if (!query) return presets.value
  return presets.value.filter((item) =>
    item.name.toLowerCase().includes(query) ||
    item.preset_id.toLowerCase().includes(query) ||
    (item.description || '').toLowerCase().includes(query)
  )
})

const presetPageCount = computed(() =>
  Math.max(1, Math.ceil(filteredPresets.value.length / presetPagination.pageSize))
)

const pagedPresets = computed(() => {
  const start = (presetPagination.page - 1) * presetPagination.pageSize
  return filteredPresets.value.slice(start, start + presetPagination.pageSize)
})

const filteredPrompts = computed(() => {
  const query = promptQuery.value.trim().toLowerCase()
  if (!query) return prompts.value
  return prompts.value.filter((item) =>
    item.name.toLowerCase().includes(query) ||
    (item.title || '').toLowerCase().includes(query) ||
    (item.tags || []).some((tag) => tag.toLowerCase().includes(query))
  )
})

const promptPageCount = computed(() =>
  Math.max(1, Math.ceil(filteredPrompts.value.length / promptPagination.pageSize))
)

const pagedPrompts = computed(() => {
  const start = (promptPagination.page - 1) * promptPagination.pageSize
  return filteredPrompts.value.slice(start, start + promptPagination.pageSize)
})

const updateLayout = () => {
  isMobile.value = window.innerWidth < 920
}

const fetchPrompts = async () => {
  loading.value = true
  error.value = null
  try {
    prompts.value = await AdminAPI.listPrompts()
    promptPagination.page = 1
    if (selectedPrompt.value) {
      const refreshed = prompts.value.find((item) => item.id === selectedPrompt.value?.id)
      if (refreshed) {
        selectPrompt(refreshed)
      } else {
        resetSelection()
      }
    } else if (prompts.value.length) {
      selectPrompt(prompts.value[0])
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '获取提示词列表失败'
  } finally {
    loading.value = false
  }
}

const resetSelection = () => {
  selectedPrompt.value = null
  editForm.name = ''
  editForm.title = ''
  editForm.content = ''
  editForm.tags = []
}

const selectPrompt = (prompt: PromptItem) => {
  selectedPrompt.value = prompt
  editForm.name = prompt.name
  editForm.title = prompt.title || ''
  editForm.content = prompt.content
  editForm.tags = prompt.tags ? [...prompt.tags] : []
}

const savePrompt = async () => {
  if (!selectedPrompt.value) return
  if (!editForm.content.trim()) {
    showAlert('提示词内容不能为空', 'error')
    return
  }
  saving.value = true
  try {
    const updated = await AdminAPI.updatePrompt(selectedPrompt.value.id, {
      title: editForm.title || undefined,
      content: editForm.content,
      tags: editForm.tags
    })
    selectPrompt(updated)
    const index = prompts.value.findIndex((item) => item.id === updated.id)
    if (index !== -1) {
      prompts.value.splice(index, 1, updated)
    }
    showAlert('保存成功', 'success')
  } catch (err) {
    showAlert(err instanceof Error ? err.message : '保存失败', 'error')
  } finally {
    saving.value = false
  }
}

const deletePrompt = async () => {
  if (!selectedPrompt.value) return
  deleting.value = true
  try {
    await AdminAPI.deletePrompt(selectedPrompt.value.id)
    showAlert('删除成功', 'success')
    prompts.value = prompts.value.filter((item) => item.id !== selectedPrompt.value?.id)
    resetSelection()
  } catch (err) {
    showAlert(err instanceof Error ? err.message : '删除失败', 'error')
  } finally {
    deleting.value = false
  }
}

const openCreateModal = () => {
  createModalVisible.value = true
}

const closeCreateModal = () => {
  createModalVisible.value = false
  createForm.name = ''
  createForm.title = ''
  createForm.content = ''
  createForm.tags = []
}

const createPrompt = async () => {
  if (!createForm.name.trim() || !createForm.content.trim()) {
    showAlert('名称与内容均为必填项', 'error')
    return
  }
  creating.value = true
  try {
    const created = await AdminAPI.createPrompt({
      name: createForm.name.trim(),
      title: createForm.title?.trim() || undefined,
      content: createForm.content,
      tags: createForm.tags?.length ? [...createForm.tags] : undefined
    })
    prompts.value.unshift(created)
    selectPrompt(created)
    showAlert('创建成功', 'success')
    closeCreateModal()
  } catch (err) {
    showAlert(err instanceof Error ? err.message : '创建失败', 'error')
  } finally {
    creating.value = false
  }
}

const resetPresetForm = () => {
  presetForm.preset_id = ''
  presetForm.name = ''
  presetForm.description = ''
  presetForm.prompt_name = 'writing_v2'
  presetForm.temperature = 0.9
  presetForm.top_p = null
  presetForm.max_tokens = null
  presetForm.style_rules = []
  presetForm.writing_notes_prefix = ''
}

const selectPreset = (preset: WritingPresetItem) => {
  selectedPreset.value = preset
  presetForm.preset_id = preset.preset_id
  presetForm.name = preset.name
  presetForm.description = preset.description || ''
  presetForm.prompt_name = preset.prompt_name || 'writing_v2'
  presetForm.temperature = preset.temperature
  presetForm.top_p = preset.top_p ?? null
  presetForm.max_tokens = preset.max_tokens ?? null
  presetForm.style_rules = preset.style_rules ? [...preset.style_rules] : []
  presetForm.writing_notes_prefix = preset.writing_notes_prefix || ''
}

const newPreset = () => {
  selectedPreset.value = null
  resetPresetForm()
}

const buildDuplicatePresetId = (sourceId: string): string => {
  const normalized = sourceId
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
  const base = `${normalized || 'preset'}-copy`.slice(0, 28)
  let candidate = base
  let index = 2
  const exists = (presetId: string) => presets.value.some((item) => item.preset_id === presetId)
  while (exists(candidate)) {
    const suffix = `-${index}`
    const head = base.slice(0, Math.max(2, 32 - suffix.length))
    candidate = `${head}${suffix}`
    index += 1
  }
  return candidate
}

const duplicatePreset = () => {
  if (!selectedPreset.value) return
  const source = selectedPreset.value
  const duplicatedId = buildDuplicatePresetId(source.preset_id)
  selectedPreset.value = null
  presetForm.preset_id = duplicatedId
  presetForm.name = `${source.name} 副本`
  presetForm.description = source.description || ''
  presetForm.prompt_name = source.prompt_name || 'writing_v2'
  presetForm.temperature = source.temperature
  presetForm.top_p = source.top_p ?? null
  presetForm.max_tokens = source.max_tokens ?? null
  presetForm.style_rules = source.style_rules ? [...source.style_rules] : []
  presetForm.writing_notes_prefix = source.writing_notes_prefix || ''
  showAlert('已生成预设副本，请确认后保存', 'success')
}

const fetchPresets = async () => {
  presetLoading.value = true
  try {
    presets.value = await AdminAPI.listWritingPresets()
    presetPagination.page = 1
    if (selectedPreset.value) {
      const refreshed = presets.value.find((item) => item.preset_id === selectedPreset.value?.preset_id)
      if (refreshed) {
        selectPreset(refreshed)
      } else {
        selectedPreset.value = null
        resetPresetForm()
      }
    } else if (presets.value.length > 0) {
      selectPreset(presets.value[0])
    }
  } catch (err) {
    showAlert(err instanceof Error ? err.message : '获取预设失败', 'error')
  } finally {
    presetLoading.value = false
  }
}

const savePreset = async () => {
  if (!presetForm.preset_id.trim() || !presetForm.name.trim() || !presetForm.prompt_name.trim()) {
    showAlert('Preset ID、名称、Prompt 名称为必填', 'error')
    return
  }
  if (selectedPreset.value?.is_builtin) {
    showAlert('内置预设不可直接修改，请新建一个自定义预设', 'error')
    return
  }
  presetSaving.value = true
  try {
    await AdminAPI.upsertWritingPreset({
      preset_id: presetForm.preset_id.trim(),
      name: presetForm.name.trim(),
      description: presetForm.description?.trim() || undefined,
      prompt_name: presetForm.prompt_name.trim(),
      temperature: Number(presetForm.temperature),
      top_p: presetForm.top_p == null ? null : Number(presetForm.top_p),
      max_tokens: presetForm.max_tokens == null ? null : Number(presetForm.max_tokens),
      style_rules: (presetForm.style_rules || []).map((item) => item.trim()).filter(Boolean),
      writing_notes_prefix: presetForm.writing_notes_prefix?.trim() || null
    })
    showAlert('预设保存成功', 'success')
    await fetchPresets()
    const updated = presets.value.find((item) => item.preset_id === presetForm.preset_id.trim())
    if (updated) selectPreset(updated)
  } catch (err) {
    showAlert(err instanceof Error ? err.message : '保存预设失败', 'error')
  } finally {
    presetSaving.value = false
  }
}

const setActivePreset = async (presetId: string | null) => {
  presetActivating.value = true
  try {
    await AdminAPI.activateWritingPreset(presetId)
    await fetchPresets()
    showAlert(presetId ? '已设为默认预设' : '已清空默认预设', 'success')
  } catch (err) {
    showAlert(err instanceof Error ? err.message : '切换默认预设失败', 'error')
  } finally {
    presetActivating.value = false
  }
}

const removePreset = async () => {
  if (!selectedPreset.value) return
  if (selectedPreset.value.is_builtin) {
    showAlert('内置预设不可删除', 'error')
    return
  }
  presetDeleting.value = true
  try {
    await AdminAPI.deleteWritingPreset(selectedPreset.value.preset_id)
    showAlert('预设已删除', 'success')
    await fetchPresets()
  } catch (err) {
    showAlert(err instanceof Error ? err.message : '删除预设失败', 'error')
  } finally {
    presetDeleting.value = false
  }
}

watch(
  () => presetQuery.value,
  () => {
    presetPagination.page = 1
  }
)

watch(
  () => promptQuery.value,
  () => {
    promptPagination.page = 1
  }
)

watch(
  () => filteredPresets.value.length,
  () => {
    if (presetPagination.page > presetPageCount.value) {
      presetPagination.page = presetPageCount.value
    }
  }
)

watch(
  () => filteredPrompts.value.length,
  () => {
    if (promptPagination.page > promptPageCount.value) {
      promptPagination.page = promptPageCount.value
    }
  }
)

onMounted(() => {
  updateLayout()
  window.addEventListener('resize', updateLayout)
  fetchPrompts()
  fetchPresets()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', updateLayout)
})
</script>

<style scoped>
.admin-card {
  width: 100%;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
}

.card-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: #1f2937;
}

.preset-card {
  border-radius: 14px;
  background: linear-gradient(180deg, rgba(59, 130, 246, 0.06), rgba(255, 255, 255, 0.96));
}

.preset-title {
  font-size: 1rem;
  font-weight: 600;
  color: #1f2937;
}

.preset-layout {
  display: flex;
  align-items: stretch;
  gap: 18px;
}

.preset-layout.mobile {
  flex-direction: column;
}

.preset-sidebar {
  width: 260px;
  flex-shrink: 0;
}

.sidebar-search {
  margin-bottom: 8px;
}

.preset-layout.mobile .preset-sidebar {
  width: 100%;
  max-height: 210px;
}

.preset-scroll {
  max-height: 360px;
}

.preset-layout.mobile .preset-scroll {
  max-height: 180px;
}

.preset-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.preset-name {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  font-weight: 500;
}

.preset-editor {
  flex: 1;
  min-width: 0;
}

.preset-number-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.prompt-layout {
  display: flex;
  align-items: stretch;
  gap: 20px;
  min-height: 420px;
}

.prompt-layout.mobile {
  flex-direction: column;
}

.prompt-sidebar {
  width: 260px;
  flex-shrink: 0;
}

.prompt-layout.mobile .prompt-sidebar {
  width: 100%;
  max-height: 220px;
}

.sidebar-pagination {
  margin-top: 8px;
  justify-content: center;
}

.prompt-scroll {
  max-height: 520px;
}

.prompt-layout.mobile .prompt-scroll {
  max-height: 200px;
}

.prompt-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  font-weight: 500;
}

.prompt-name {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  margin-right: 8px;
}

.prompt-editor {
  flex: 1;
  min-width: 0;
}

.empty-editor {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px 0;
}

.editor-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.prompt-textarea :deep(textarea) {
  font-family: 'Fira Code', 'JetBrains Mono', 'SFMono-Regular', Menlo, Monaco, Consolas, monospace;
  font-size: 14px;
  line-height: 1.5;
}

.prompt-modal {
  max-width: min(720px, 90vw);
}

@media (max-width: 1023px) {
  .prompt-sidebar {
    width: 220px;
  }

  .preset-sidebar {
    width: 220px;
  }
}

@media (max-width: 767px) {
  .card-title {
    font-size: 1.125rem;
  }

  .preset-number-row {
    grid-template-columns: 1fr;
  }
}
</style>
