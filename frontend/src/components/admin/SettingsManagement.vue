<!-- AIMETA P=设置管理_系统设置界面|R=系统配置表单|NR=不含用户设置|E=component:SettingsManagement|X=ui|A=设置组件|D=vue|S=dom,net|RD=./README.ai -->
<template>
  <n-space vertical size="large" class="admin-settings">
    <n-tabs v-model:value="activeSection" type="line" animated class="admin-section-tabs">
      <n-tab-pane name="quota" tab="额度与策略">
    <n-card :bordered="false">
      <template #header>
        <div class="card-header">
          <span class="card-title">每日请求额度</span>
          <n-button quaternary size="small" @click="fetchDailyLimit" :loading="dailyLimitLoading">
            刷新
          </n-button>
        </div>
      </template>
      <n-spin :show="dailyLimitLoading">
        <n-alert v-if="dailyLimitError" type="error" closable @close="dailyLimitError = null">
          {{ dailyLimitError }}
        </n-alert>
        <n-form label-placement="top" class="limit-form">
          <n-form-item label="未配置 API Key 的用户每日可用请求次数">
            <n-input-number
              v-model:value="dailyLimit"
              :min="0"
              :step="10"
              placeholder="请输入每日请求上限"
            />
          </n-form-item>
          <n-space justify="end">
            <n-button type="primary" :loading="dailyLimitSaving" @click="saveDailyLimit">
              保存设置
            </n-button>
          </n-space>
        </n-form>
      </n-spin>
    </n-card>

    <n-card :bordered="false">
      <template #header>
        <div class="card-header">
          <span class="card-title">LLM 成本与容错策略</span>
          <n-space :size="8">
            <n-button quaternary size="small" @click="loadPolicyConfigsFromList(configs)">
              从当前配置重载
            </n-button>
            <n-button type="primary" size="small" :loading="policySaving" @click="savePolicyConfigs">
              保存策略
            </n-button>
          </n-space>
        </div>
      </template>
      <n-spin :show="policySaving">
        <n-alert v-if="policyError" type="error" closable @close="policyError = null">
          {{ policyError }}
        </n-alert>
        <n-alert type="info" :bordered="false" class="policy-tip">
          单用户/单项目预算覆盖键可在下方“系统配置”里新增：
          <code>llm.budget.daily_usd.user.{user_id}</code>、
          <code>llm.budget.daily_usd.project.{project_id}</code>
        </n-alert>
        <n-form label-placement="top">
          <n-grid :cols="2" :x-gap="12">
            <n-gi v-for="field in policyFields" :key="field.key">
              <n-form-item :label="field.label">
                <n-select
                  v-if="field.type === 'select'"
                  v-model:value="policyForm[field.key]"
                  :options="field.options || []"
                />
                <n-input
                  v-else
                  v-model:value="policyForm[field.key]"
                  :placeholder="field.placeholder || field.description"
                />
                <div class="field-key">{{ field.key }}</div>
              </n-form-item>
            </n-gi>
          </n-grid>
        </n-form>
      </n-spin>
    </n-card>
      </n-tab-pane>

      <n-tab-pane name="override" tab="预算覆盖">

    <n-card :bordered="false">
      <template #header>
        <div class="card-header">
          <span class="card-title">预算覆盖管理</span>
          <n-space :size="8">
            <n-button quaternary size="small" @click="openCsvImportModal">
              CSV 批量导入
            </n-button>
            <n-button quaternary size="small" :loading="overrideRefLoading" @click="fetchOverrideReferences">
              刷新用户/项目列表
            </n-button>
          </n-space>
        </div>
      </template>
      <n-alert v-if="overrideError" type="error" closable @close="overrideError = null">
        {{ overrideError }}
      </n-alert>
      <n-grid :cols="overrideGridCols" :x-gap="12" :y-gap="12" class="override-grid">
        <n-gi>
          <n-card size="small" embedded class="override-card">
            <template #header>用户预算覆盖</template>
            <n-form label-placement="top" class="override-form">
              <n-form-item label="用户">
                <n-select
                  v-model:value="userOverrideForm.user_id"
                  :options="userOptions"
                  filterable
                  clearable
                  placeholder="选择用户"
                />
              </n-form-item>
              <n-form-item label="每日预算(USD)">
                <n-input
                  v-model:value="userOverrideForm.budget_usd"
                  placeholder="例如：1.5"
                />
              </n-form-item>
              <n-space justify="end">
                <n-button
                  size="small"
                  type="primary"
                  :loading="overrideSaving"
                  @click="saveUserBudgetOverride"
                >
                  保存用户覆盖
                </n-button>
              </n-space>
            </n-form>
            <n-input
              v-model:value="overrideFilter.user_query"
              clearable
              placeholder="搜索用户 ID / 用户名"
              class="override-search"
            />
            <n-data-table
              :columns="userOverrideColumns"
              :data="filteredUserBudgetOverrides"
              :pagination="userOverridePagination"
              :bordered="false"
              size="small"
            />
          </n-card>
        </n-gi>
        <n-gi>
          <n-card size="small" embedded class="override-card">
            <template #header>项目预算覆盖</template>
            <n-form label-placement="top" class="override-form">
              <n-form-item label="项目">
                <n-select
                  v-model:value="projectOverrideForm.project_id"
                  :options="projectOptions"
                  filterable
                  clearable
                  placeholder="选择项目"
                />
              </n-form-item>
              <n-form-item label="每日预算(USD)">
                <n-input
                  v-model:value="projectOverrideForm.budget_usd"
                  placeholder="例如：5"
                />
              </n-form-item>
              <n-space justify="end">
                <n-button
                  size="small"
                  type="primary"
                  :loading="overrideSaving"
                  @click="saveProjectBudgetOverride"
                >
                  保存项目覆盖
                </n-button>
              </n-space>
            </n-form>
            <n-input
              v-model:value="overrideFilter.project_query"
              clearable
              placeholder="搜索项目 ID / 项目名 / 归属"
              class="override-search"
            />
            <n-data-table
              :columns="projectOverrideColumns"
              :data="filteredProjectBudgetOverrides"
              :pagination="projectOverridePagination"
              :bordered="false"
              size="small"
            />
          </n-card>
        </n-gi>
      </n-grid>
    </n-card>
      </n-tab-pane>

      <n-tab-pane name="config" tab="系统配置">

    <n-card :bordered="false">
      <template #header>
        <div class="card-header">
          <span class="card-title">系统配置</span>
          <n-button type="primary" size="small" @click="openCreateModal">
            新增配置
          </n-button>
        </div>
      </template>

      <n-spin :show="configLoading">
        <n-alert v-if="configError" type="error" closable @close="configError = null">
          {{ configError }}
        </n-alert>

        <n-data-table
          :columns="columns"
          :data="configs"
          :loading="configLoading"
          :pagination="configPagination"
          :bordered="false"
          :row-key="rowKey"
          class="config-table"
        />
      </n-spin>
    </n-card>
      </n-tab-pane>
    </n-tabs>
  </n-space>

  <n-modal
    v-model:show="configModalVisible"
    preset="card"
    :title="modalTitle"
    class="config-modal"
    :style="{ width: '520px', maxWidth: '92vw' }"
  >
    <n-form label-placement="top" :model="configForm">
      <n-form-item label="Key">
        <n-input
          v-model:value="configForm.key"
          :disabled="!isCreateMode"
          placeholder="请输入唯一 Key"
        />
      </n-form-item>
      <n-form-item label="值">
        <n-input v-model:value="configForm.value" placeholder="配置的具体值" />
      </n-form-item>
      <n-form-item label="描述">
        <n-input v-model:value="configForm.description" placeholder="配置项的用途说明，可选" />
      </n-form-item>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button quaternary @click="closeConfigModal">取消</n-button>
        <n-button type="primary" :loading="configSaving" @click="submitConfig">
          保存
        </n-button>
      </n-space>
    </template>
  </n-modal>

  <n-modal
    v-model:show="csvImportVisible"
    preset="card"
    title="CSV 批量导入预算覆盖"
    class="csv-modal"
    :style="{ width: '760px', maxWidth: '96vw' }"
  >
    <n-space vertical size="small">
      <n-alert type="info" :bordered="false">
        支持两种格式（含表头）：
        <br />
        1) <code>type,id,budget_usd</code>，其中 type 为 <code>user</code> 或 <code>project</code>
        <br />
        2) <code>key,budget_usd</code>，key 直接写完整配置键
      </n-alert>
      <n-input
        v-model:value="csvImportText"
        type="textarea"
        :autosize="{ minRows: 10, maxRows: 20 }"
        placeholder="type,id,budget_usd&#10;user,2,1.5&#10;project,abc-123,5"
      />
      <n-alert v-if="csvImportError" type="error" closable @close="csvImportError = null">
        {{ csvImportError }}
      </n-alert>
      <n-alert v-if="csvImportSummary" type="success" :bordered="false">
        {{ csvImportSummary }}
      </n-alert>
    </n-space>
    <template #footer>
      <n-space justify="end">
        <n-button quaternary @click="closeCsvImportModal">取消</n-button>
        <n-button type="primary" :loading="csvImportLoading" @click="submitCsvImport">
          开始导入
        </n-button>
      </n-space>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, h, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import {
  NAlert,
  NButton,
  NCard,
  NDataTable,
  NForm,
  NFormItem,
  NGi,
  NGrid,
  NInput,
  NInputNumber,
  NModal,
  NPopconfirm,
  NSelect,
  NSpace,
  NSpin,
  NTabPane,
  NTabs,
  type DataTableColumns,
  type SelectOption
} from 'naive-ui'

import {
  AdminAPI,
  type AdminNovelSummary,
  type AdminUser,
  type DailyRequestLimit,
  type SystemConfig,
  type SystemConfigUpdatePayload,
  type SystemConfigUpsertPayload
} from '@/api/admin'
import { useAlert } from '@/composables/useAlert'

const { showAlert } = useAlert()

const dailyLimit = ref<number | null>(null)
const dailyLimitLoading = ref(false)
const dailyLimitSaving = ref(false)
const dailyLimitError = ref<string | null>(null)

const configs = ref<SystemConfig[]>([])
const configLoading = ref(false)
const configSaving = ref(false)
const configError = ref<string | null>(null)
const activeSection = ref<'quota' | 'override' | 'config'>('quota')

const policySaving = ref(false)
const policyError = ref<string | null>(null)
const overrideSaving = ref(false)
const overrideRefLoading = ref(false)
const overrideError = ref<string | null>(null)
const users = ref<AdminUser[]>([])
const projects = ref<AdminNovelSummary[]>([])
const csvImportVisible = ref(false)
const csvImportLoading = ref(false)
const csvImportText = ref('')
const csvImportError = ref<string | null>(null)
const csvImportSummary = ref<string | null>(null)

const overrideFilter = reactive({
  user_query: '',
  project_query: ''
})

const userOverrideForm = reactive<{ user_id: number | null; budget_usd: string }>({
  user_id: null,
  budget_usd: ''
})

const projectOverrideForm = reactive<{ project_id: string | null; budget_usd: string }>({
  project_id: null,
  budget_usd: ''
})

const USER_BUDGET_OVERRIDE_PREFIX = 'llm.budget.daily_usd.user.'
const PROJECT_BUDGET_OVERRIDE_PREFIX = 'llm.budget.daily_usd.project.'

interface PolicyField {
  key: string
  label: string
  description: string
  defaultValue: string
  type: 'text' | 'number' | 'select'
  placeholder?: string
  min?: number
  max?: number
  integer?: boolean
  options?: SelectOption[]
}

interface UserBudgetOverrideRow {
  key: string
  user_id: number
  username: string
  budget_usd: string
}

interface ProjectBudgetOverrideRow {
  key: string
  project_id: string
  project_title: string
  owner_username: string
  budget_usd: string
}

const policyFields: PolicyField[] = [
  {
    key: 'llm.retry.max_retries',
    label: '失败重试次数',
    description: 'LLM 请求失败后的重试次数（不含首次请求）',
    defaultValue: '1',
    type: 'number',
    min: 0,
    max: 4,
    integer: true,
    placeholder: '0-4'
  },
  {
    key: 'llm.retry.backoff_ms',
    label: '重试退避(ms)',
    description: '重试间隔毫秒数，内部采用指数退避',
    defaultValue: '600',
    type: 'number',
    min: 100,
    max: 10000,
    integer: true,
    placeholder: '100-10000'
  },
  {
    key: 'llm.fallback.models',
    label: '回退模型列表',
    description: '主模型失败后自动尝试的模型列表（逗号分隔）',
    defaultValue: 'gpt-4o-mini,gpt-4.1-mini',
    type: 'text',
    placeholder: '例如：gpt-4o-mini,gpt-4.1-mini'
  },
  {
    key: 'llm.budget.circuit_mode',
    label: '预算熔断模式',
    description: 'degrade=降级模型，block=直接拒绝请求',
    defaultValue: 'degrade',
    type: 'select',
    options: [
      { label: '自动降级 (degrade)', value: 'degrade' },
      { label: '直接阻断 (block)', value: 'block' }
    ]
  },
  {
    key: 'llm.budget.degrade_model',
    label: '降级模型',
    description: '预算熔断为 degrade 时使用的模型',
    defaultValue: 'gpt-4o-mini',
    type: 'text',
    placeholder: '例如：gpt-4o-mini'
  },
  {
    key: 'llm.budget.reserve_output_tokens',
    label: '预算预留输出Token',
    description: '预算预估时预留的输出 token，用于预判本次调用成本',
    defaultValue: '1200',
    type: 'number',
    min: 1,
    max: 32000,
    integer: true,
    placeholder: '1-32000'
  },
  {
    key: 'llm.budget.daily_usd.global',
    label: '全局日预算(USD)',
    description: '全局每日预算，0 表示关闭',
    defaultValue: '0',
    type: 'number',
    min: 0,
    max: 10000000,
    placeholder: '例如：10'
  },
  {
    key: 'llm.budget.daily_usd.user.default',
    label: '默认用户日预算(USD)',
    description: '用户默认每日预算，0 表示关闭',
    defaultValue: '0',
    type: 'number',
    min: 0,
    max: 10000000,
    placeholder: '例如：1'
  },
  {
    key: 'llm.budget.daily_usd.project.default',
    label: '默认项目日预算(USD)',
    description: '项目默认每日预算，0 表示关闭',
    defaultValue: '0',
    type: 'number',
    min: 0,
    max: 10000000,
    placeholder: '例如：5'
  },
  {
    key: 'llm.budget.alert.thresholds',
    label: '预算告警阈值',
    description: '预算告警比例阈值，逗号分隔（例如 0.5,0.8,1.0）',
    defaultValue: '0.5,0.8,1.0',
    type: 'text',
    placeholder: '例如：0.5,0.8,1.0'
  }
]

const policyForm = reactive<Record<string, string>>(
  Object.fromEntries(policyFields.map((field) => [field.key, field.defaultValue]))
)

const configModalVisible = ref(false)
const isCreateMode = ref(true)
const configForm = reactive<SystemConfig>({
  key: '',
  value: '',
  description: ''
})
const userOverridePagination = reactive({
  page: 1,
  pageSize: 8,
  showSizePicker: true,
  pageSizes: [8, 12, 20]
})
const projectOverridePagination = reactive({
  page: 1,
  pageSize: 8,
  showSizePicker: true,
  pageSizes: [8, 12, 20]
})
const configPagination = reactive({
  page: 1,
  pageSize: 10,
  showSizePicker: true,
  pageSizes: [10, 20, 50]
})

const rowKey = (row: SystemConfig) => row.key

const modalTitle = computed(() => (isCreateMode.value ? '新增配置项' : '编辑配置项'))
const isCompact = ref(false)
const overrideGridCols = computed(() => (isCompact.value ? 1 : 2))

const userMap = computed(() => new Map(users.value.map((user) => [user.id, user])))
const projectMap = computed(() => new Map(projects.value.map((project) => [project.id, project])))

const userOptions = computed<SelectOption[]>(() =>
  users.value.map((user) => ({
    label: `${user.id} · ${user.username}`,
    value: user.id
  }))
)

const projectOptions = computed<SelectOption[]>(() =>
  projects.value.map((project) => ({
    label: `${project.title} (${project.id})`,
    value: project.id
  }))
)

const userBudgetOverrides = computed<UserBudgetOverrideRow[]>(() => {
  const rows: UserBudgetOverrideRow[] = []
  for (const config of configs.value) {
    if (!config.key.startsWith(USER_BUDGET_OVERRIDE_PREFIX)) continue
    if (config.key === 'llm.budget.daily_usd.user.default') continue
    const suffix = config.key.slice(USER_BUDGET_OVERRIDE_PREFIX.length).trim()
    if (!/^\d+$/.test(suffix)) continue
    const userId = Number(suffix)
    if (!Number.isInteger(userId) || userId <= 0) continue
    rows.push({
      key: config.key,
      user_id: userId,
      username: userMap.value.get(userId)?.username || '未知用户',
      budget_usd: config.value
    })
  }
  return rows.sort((a, b) => a.user_id - b.user_id)
})

const projectBudgetOverrides = computed<ProjectBudgetOverrideRow[]>(() => {
  const rows: ProjectBudgetOverrideRow[] = []
  for (const config of configs.value) {
    if (!config.key.startsWith(PROJECT_BUDGET_OVERRIDE_PREFIX)) continue
    if (config.key === 'llm.budget.daily_usd.project.default') continue
    const projectId = config.key.slice(PROJECT_BUDGET_OVERRIDE_PREFIX.length).trim()
    if (!projectId) continue
    const project = projectMap.value.get(projectId)
    rows.push({
      key: config.key,
      project_id: projectId,
      project_title: project?.title || '未知项目',
      owner_username: project?.owner_username || '未知',
      budget_usd: config.value
    })
  }
  return rows.sort((a, b) => a.project_id.localeCompare(b.project_id))
})

const filteredUserBudgetOverrides = computed<UserBudgetOverrideRow[]>(() => {
  const query = overrideFilter.user_query.trim().toLowerCase()
  if (!query) return userBudgetOverrides.value
  return userBudgetOverrides.value.filter(
    (row) =>
      String(row.user_id).includes(query) ||
      row.username.toLowerCase().includes(query) ||
      row.key.toLowerCase().includes(query)
  )
})

const filteredProjectBudgetOverrides = computed<ProjectBudgetOverrideRow[]>(() => {
  const query = overrideFilter.project_query.trim().toLowerCase()
  if (!query) return projectBudgetOverrides.value
  return projectBudgetOverrides.value.filter(
    (row) =>
      row.project_id.toLowerCase().includes(query) ||
      row.project_title.toLowerCase().includes(query) ||
      row.owner_username.toLowerCase().includes(query) ||
      row.key.toLowerCase().includes(query)
  )
})

watch(
  () => overrideFilter.user_query,
  () => {
    userOverridePagination.page = 1
  }
)

watch(
  () => overrideFilter.project_query,
  () => {
    projectOverridePagination.page = 1
  }
)

const fetchDailyLimit = async () => {
  dailyLimitLoading.value = true
  dailyLimitError.value = null
  try {
    const result = await AdminAPI.getDailyRequestLimit()
    dailyLimit.value = result.limit
  } catch (err) {
    dailyLimitError.value = err instanceof Error ? err.message : '加载每日限制失败'
  } finally {
    dailyLimitLoading.value = false
  }
}

const saveDailyLimit = async () => {
  if (dailyLimit.value === null || dailyLimit.value < 0) {
    showAlert('请设置有效的每日额度', 'error')
    return
  }
  dailyLimitSaving.value = true
  try {
    await AdminAPI.setDailyRequestLimit(dailyLimit.value)
    showAlert('每日额度已更新', 'success')
  } catch (err) {
    showAlert(err instanceof Error ? err.message : '保存失败', 'error')
  } finally {
    dailyLimitSaving.value = false
  }
}

const updateLayout = () => {
  isCompact.value = window.innerWidth < 1100
}

const normalizeBudgetUsd = (rawValue: string, label: string): string => {
  const value = rawValue.trim()
  if (!value) {
    throw new Error(`${label}不能为空`)
  }
  const parsed = Number(value)
  if (Number.isNaN(parsed)) {
    throw new Error(`${label}必须是数字`)
  }
  if (parsed < 0) {
    throw new Error(`${label}不能小于 0`)
  }
  if (parsed > 10_000_000) {
    throw new Error(`${label}不能大于 10000000`)
  }
  return String(parsed)
}

const upsertConfigLocal = (updated: SystemConfig) => {
  const index = configs.value.findIndex((item) => item.key === updated.key)
  if (index >= 0) {
    configs.value.splice(index, 1, updated)
  } else {
    configs.value.unshift(updated)
  }
  loadPolicyConfigsFromList(configs.value)
}

const removeConfigLocal = (key: string) => {
  configs.value = configs.value.filter((item) => item.key !== key)
  loadPolicyConfigsFromList(configs.value)
}

const fetchOverrideReferences = async () => {
  overrideRefLoading.value = true
  overrideError.value = null
  try {
    const [userList, projectList] = await Promise.all([AdminAPI.listUsers(), AdminAPI.listNovels()])
    users.value = userList
    projects.value = projectList
  } catch (err) {
    overrideError.value = err instanceof Error ? err.message : '加载用户/项目列表失败'
  } finally {
    overrideRefLoading.value = false
  }
}

const saveUserBudgetOverride = async () => {
  if (userOverrideForm.user_id == null) {
    showAlert('请先选择用户', 'error')
    return
  }
  overrideSaving.value = true
  overrideError.value = null
  try {
    const budget = normalizeBudgetUsd(userOverrideForm.budget_usd, '用户预算')
    const userId = userOverrideForm.user_id
    const user = userMap.value.get(userId)
    const key = `${USER_BUDGET_OVERRIDE_PREFIX}${userId}`
    const updated = await AdminAPI.upsertSystemConfig(key, {
      value: budget,
      description: `用户 ${userId}${user ? `(${user.username})` : ''} 每日预算覆盖（USD）`
    })
    upsertConfigLocal(updated)
    showAlert('用户预算覆盖已保存', 'success')
  } catch (err) {
    const message = err instanceof Error ? err.message : '保存用户预算覆盖失败'
    overrideError.value = message
    showAlert(message, 'error')
  } finally {
    overrideSaving.value = false
  }
}

const saveProjectBudgetOverride = async () => {
  if (!projectOverrideForm.project_id) {
    showAlert('请先选择项目', 'error')
    return
  }
  overrideSaving.value = true
  overrideError.value = null
  try {
    const budget = normalizeBudgetUsd(projectOverrideForm.budget_usd, '项目预算')
    const projectId = projectOverrideForm.project_id
    const project = projectMap.value.get(projectId)
    const key = `${PROJECT_BUDGET_OVERRIDE_PREFIX}${projectId}`
    const updated = await AdminAPI.upsertSystemConfig(key, {
      value: budget,
      description: `项目 ${project?.title || projectId} 每日预算覆盖（USD）`
    })
    upsertConfigLocal(updated)
    showAlert('项目预算覆盖已保存', 'success')
  } catch (err) {
    const message = err instanceof Error ? err.message : '保存项目预算覆盖失败'
    overrideError.value = message
    showAlert(message, 'error')
  } finally {
    overrideSaving.value = false
  }
}

const deleteOverrideConfig = async (key: string) => {
  overrideSaving.value = true
  overrideError.value = null
  try {
    await AdminAPI.deleteSystemConfig(key)
    removeConfigLocal(key)
    showAlert('预算覆盖已删除', 'success')
  } catch (err) {
    const message = err instanceof Error ? err.message : '删除预算覆盖失败'
    overrideError.value = message
    showAlert(message, 'error')
  } finally {
    overrideSaving.value = false
  }
}

const openCsvImportModal = () => {
  csvImportVisible.value = true
  csvImportError.value = null
  csvImportSummary.value = null
}

const closeCsvImportModal = () => {
  csvImportVisible.value = false
  csvImportLoading.value = false
}

const parseCsvLine = (line: string): string[] => {
  const cells: string[] = []
  let current = ''
  let inQuotes = false
  for (let i = 0; i < line.length; i += 1) {
    const char = line[i]
    if (char === '"') {
      if (inQuotes && i + 1 < line.length && line[i + 1] === '"') {
        current += '"'
        i += 1
      } else {
        inQuotes = !inQuotes
      }
      continue
    }
    if (char === ',' && !inQuotes) {
      cells.push(current)
      current = ''
      continue
    }
    current += char
  }
  if (inQuotes) {
    throw new Error('CSV 存在未闭合引号')
  }
  cells.push(current)
  return cells
}

const normalizeHeader = (value: string): string => value.replace(/^\uFEFF/, '').trim().toLowerCase()

const resolveCsvOverrideKey = (row: Record<string, string>, lineNumber: number): string => {
  const directKey = (row.key || '').trim()
  if (directKey) {
    if (
      directKey.startsWith(USER_BUDGET_OVERRIDE_PREFIX) ||
      directKey.startsWith(PROJECT_BUDGET_OVERRIDE_PREFIX)
    ) {
      return directKey
    }
    throw new Error(`第 ${lineNumber} 行 key 非预算覆盖键`)
  }

  const type = (row.type || row.scope || row.kind || '').trim().toLowerCase()
  const id = (row.id || row.user_id || row.project_id || '').trim()
  if (!type || !id) {
    throw new Error(`第 ${lineNumber} 行缺少 type/scope 与 id`)
  }

  if (type === 'user') {
    if (!/^\d+$/.test(id)) {
      throw new Error(`第 ${lineNumber} 行 user id 必须是正整数`)
    }
    return `${USER_BUDGET_OVERRIDE_PREFIX}${id}`
  }
  if (type === 'project') {
    return `${PROJECT_BUDGET_OVERRIDE_PREFIX}${id}`
  }
  throw new Error(`第 ${lineNumber} 行 type 仅支持 user / project`)
}

const resolveCsvBudget = (row: Record<string, string>, lineNumber: number): string => {
  const budgetRaw = (row.budget_usd || row.budget || row.value || '').trim()
  if (!budgetRaw) {
    throw new Error(`第 ${lineNumber} 行缺少 budget_usd/budget/value`)
  }
  return normalizeBudgetUsd(budgetRaw, `第 ${lineNumber} 行预算`)
}

const submitCsvImport = async () => {
  csvImportLoading.value = true
  csvImportError.value = null
  csvImportSummary.value = null
  try {
    const raw = csvImportText.value.trim()
    if (!raw) {
      throw new Error('请先粘贴 CSV 内容')
    }
    const lines = raw
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => line.length > 0)

    if (lines.length < 2) {
      throw new Error('CSV 至少需要 1 行表头 + 1 行数据')
    }

    const headers = parseCsvLine(lines[0]).map(normalizeHeader)
    const entries: Array<{ key: string; value: string; line: number }> = []
    const dedup = new Map<string, { key: string; value: string; line: number }>()

    for (let i = 1; i < lines.length; i += 1) {
      const lineNumber = i + 1
      const cells = parseCsvLine(lines[i])
      if (cells.length > headers.length) {
        throw new Error(`第 ${lineNumber} 行字段数量超过表头`)
      }
      const row: Record<string, string> = {}
      for (let col = 0; col < headers.length; col += 1) {
        const key = headers[col]
        row[key] = (cells[col] || '').trim()
      }
      const key = resolveCsvOverrideKey(row, lineNumber)
      const value = resolveCsvBudget(row, lineNumber)
      dedup.set(key, { key, value, line: lineNumber })
    }

    entries.push(...dedup.values())
    let success = 0
    const failures: string[] = []
    for (const item of entries) {
      try {
        const updated = await AdminAPI.upsertSystemConfig(item.key, {
          value: item.value,
          description: `CSV 导入预算覆盖（line ${item.line}）`
        })
        upsertConfigLocal(updated)
        success += 1
      } catch (err) {
        const message = err instanceof Error ? err.message : '未知错误'
        failures.push(`line ${item.line}: ${message}`)
      }
    }

    const failed = failures.length
    csvImportSummary.value = `导入完成：成功 ${success} 条，失败 ${failed} 条`
    if (failed > 0) {
      csvImportError.value = failures.slice(0, 6).join('；')
      showAlert(`CSV 导入完成：成功 ${success}，失败 ${failed}`, 'error')
      return
    }

    showAlert(`CSV 导入成功，共 ${success} 条`, 'success')
  } catch (err) {
    const message = err instanceof Error ? err.message : 'CSV 导入失败'
    csvImportError.value = message
    showAlert(message, 'error')
  } finally {
    csvImportLoading.value = false
  }
}

const fetchConfigs = async () => {
  configLoading.value = true
  configError.value = null
  try {
    configs.value = await AdminAPI.listSystemConfigs()
    configPagination.page = 1
    loadPolicyConfigsFromList(configs.value)
  } catch (err) {
    configError.value = err instanceof Error ? err.message : '加载配置失败'
  } finally {
    configLoading.value = false
  }
}

const loadPolicyConfigsFromList = (list: SystemConfig[]) => {
  const map = new Map(list.map((item) => [item.key, item.value]))
  policyFields.forEach((field) => {
    const value = map.get(field.key)
    policyForm[field.key] = value != null && String(value).trim() !== '' ? String(value) : field.defaultValue
  })
}

const normalizePolicyFieldValue = (field: PolicyField, rawValue: string): string => {
  const value = rawValue.trim()
  if (!value) return field.defaultValue
  if (field.key === 'llm.budget.alert.thresholds') {
    const numbers = value
      .split(',')
      .map((item) => Number(item.trim()))
      .filter((item) => Number.isFinite(item) && item > 0)
      .sort((a, b) => a - b)
    if (numbers.length === 0) {
      throw new Error(`${field.label} 需至少包含 1 个正数`)
    }
    return numbers.join(',')
  }
  if (field.type === 'select') {
    const options = field.options || []
    if (!options.some((option) => option.value === value)) {
      throw new Error(`${field.label} 取值无效`)
    }
    return value
  }
  if (field.type === 'number') {
    const parsed = Number(value)
    if (Number.isNaN(parsed)) {
      throw new Error(`${field.label} 必须是数字`)
    }
    if (field.min != null && parsed < field.min) {
      throw new Error(`${field.label} 不能小于 ${field.min}`)
    }
    if (field.max != null && parsed > field.max) {
      throw new Error(`${field.label} 不能大于 ${field.max}`)
    }
    if (field.integer && !Number.isInteger(parsed)) {
      throw new Error(`${field.label} 必须是整数`)
    }
    return field.integer ? String(Math.trunc(parsed)) : String(parsed)
  }
  return value
}

const savePolicyConfigs = async () => {
  policySaving.value = true
  policyError.value = null
  try {
    const payloads = policyFields.map((field) => ({
      field,
      value: normalizePolicyFieldValue(field, policyForm[field.key] || '')
    }))
    const updated = await Promise.all(
      payloads.map(({ field, value }) =>
        AdminAPI.upsertSystemConfig(field.key, {
          value,
          description: field.description
        } as SystemConfigUpsertPayload)
      )
    )
    for (const item of updated) upsertConfigLocal(item)
    showAlert('LLM 策略配置已保存', 'success')
  } catch (err) {
    const message = err instanceof Error ? err.message : '保存 LLM 策略失败'
    policyError.value = message
    showAlert(message, 'error')
  } finally {
    policySaving.value = false
  }
}

const openCreateModal = () => {
  isCreateMode.value = true
  configForm.key = ''
  configForm.value = ''
  configForm.description = ''
  configModalVisible.value = true
}

const openEditModal = (config: SystemConfig) => {
  isCreateMode.value = false
  configForm.key = config.key
  configForm.value = config.value
  configForm.description = config.description || ''
  configModalVisible.value = true
}

const closeConfigModal = () => {
  configModalVisible.value = false
  configSaving.value = false
}

const submitConfig = async () => {
  if (!configForm.key.trim() || !configForm.value.trim()) {
    showAlert('Key 与 Value 均为必填项', 'error')
    return
  }
  configSaving.value = true
  try {
    let updated: SystemConfig
    if (isCreateMode.value) {
      updated = await AdminAPI.upsertSystemConfig(configForm.key.trim(), {
        value: configForm.value,
        description: configForm.description || undefined
      })
      upsertConfigLocal(updated)
    } else {
      updated = await AdminAPI.patchSystemConfig(configForm.key, {
        value: configForm.value,
        description: configForm.description || undefined
      } as SystemConfigUpdatePayload)
      upsertConfigLocal(updated)
    }
    showAlert('配置已保存', 'success')
    closeConfigModal()
  } catch (err) {
    showAlert(err instanceof Error ? err.message : '保存失败', 'error')
  } finally {
    configSaving.value = false
  }
}

const deleteConfig = async (key: string) => {
  try {
    await AdminAPI.deleteSystemConfig(key)
    removeConfigLocal(key)
    showAlert('配置已删除', 'success')
  } catch (err) {
    showAlert(err instanceof Error ? err.message : '删除失败', 'error')
  }
}

const userOverrideColumns: DataTableColumns<UserBudgetOverrideRow> = [
  {
    title: '用户',
    key: 'user_id',
    width: 140,
    render: (row) => `${row.user_id} · ${row.username}`
  },
  {
    title: '预算(USD)',
    key: 'budget_usd',
    width: 120
  },
  {
    title: '配置键',
    key: 'key',
    ellipsis: { tooltip: true }
  },
  {
    title: '操作',
    key: 'actions',
    width: 86,
    align: 'center',
    render(row) {
      return h(
        NPopconfirm,
        {
          'positive-text': '删除',
          'negative-text': '取消',
          type: 'error',
          onPositiveClick: () => deleteOverrideConfig(row.key)
        },
        {
          default: () => '确认删除该覆盖项？',
          trigger: () =>
            h(
              NButton,
              { size: 'small', type: 'error', quaternary: true, loading: overrideSaving.value },
              { default: () => '删除' }
            )
        }
      )
    }
  }
]

const projectOverrideColumns: DataTableColumns<ProjectBudgetOverrideRow> = [
  {
    title: '项目',
    key: 'project_title',
    width: 220,
    ellipsis: { tooltip: true },
    render: (row) => `${row.project_title} (${row.project_id})`
  },
  {
    title: '归属',
    key: 'owner_username',
    width: 90,
    ellipsis: { tooltip: true }
  },
  {
    title: '预算(USD)',
    key: 'budget_usd',
    width: 120
  },
  {
    title: '配置键',
    key: 'key',
    ellipsis: { tooltip: true }
  },
  {
    title: '操作',
    key: 'actions',
    width: 86,
    align: 'center',
    render(row) {
      return h(
        NPopconfirm,
        {
          'positive-text': '删除',
          'negative-text': '取消',
          type: 'error',
          onPositiveClick: () => deleteOverrideConfig(row.key)
        },
        {
          default: () => '确认删除该覆盖项？',
          trigger: () =>
            h(
              NButton,
              { size: 'small', type: 'error', quaternary: true, loading: overrideSaving.value },
              { default: () => '删除' }
            )
        }
      )
    }
  }
]

const columns: DataTableColumns<SystemConfig> = [
  {
    title: 'Key',
    key: 'key',
    width: 220,
    ellipsis: { tooltip: true }
  },
  {
    title: '值',
    key: 'value',
    ellipsis: { tooltip: true }
  },
  {
    title: '描述',
    key: 'description',
    ellipsis: { tooltip: true },
    render(row) {
      return row.description || '—'
    }
  },
  {
    title: '操作',
    key: 'actions',
    align: 'center',
    width: 160,
    render(row) {
      return h(
        NSpace,
        { justify: 'center', size: 'small' },
        {
          default: () => [
            h(
              NButton,
              {
                size: 'small',
                type: 'primary',
                tertiary: true,
                onClick: () => openEditModal(row)
              },
              { default: () => '编辑' }
            ),
            h(
              NPopconfirm,
              {
                'positive-text': '删除',
                'negative-text': '取消',
                type: 'error',
                placement: 'left',
                onPositiveClick: () => deleteConfig(row.key)
              },
              {
                default: () => '确认删除该配置项？',
                trigger: () =>
                  h(
                    NButton,
                    { size: 'small', type: 'error', quaternary: true },
                    { default: () => '删除' }
                  )
              }
            )
          ]
        }
      )
    }
  }
]

onMounted(() => {
  updateLayout()
  window.addEventListener('resize', updateLayout)
  fetchDailyLimit()
  fetchConfigs()
  fetchOverrideReferences()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', updateLayout)
})
</script>

<style scoped>
.admin-settings {
  width: 100%;
}

.admin-section-tabs {
  width: 100%;
}

:deep(.admin-section-tabs .n-tabs-nav) {
  margin-bottom: 6px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.card-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: #1f2937;
}

.limit-form {
  max-width: 360px;
}

.policy-tip {
  margin-bottom: 12px;
}

.field-key {
  margin-top: 4px;
  font-size: 12px;
  color: #6b7280;
  word-break: break-all;
}

.override-grid {
  margin-top: 8px;
}

.override-card {
  height: 100%;
}

.override-form {
  margin-bottom: 10px;
}

.override-search {
  margin-bottom: 8px;
}

.csv-modal {
  max-width: min(840px, 96vw);
}

.config-modal {
  max-width: min(640px, 92vw);
}

@media (max-width: 767px) {
  .card-title {
    font-size: 1.125rem;
  }
}
</style>
