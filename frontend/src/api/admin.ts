// AIMETA P=管理员API客户端_管理接口调用|R=用户管理_系统配置_统计|NR=不含UI逻辑|E=api:admin|X=internal|A=adminApi对象|D=axios|S=net|RD=./README.ai
import { useAuthStore } from '@/stores/auth'
import router from '@/router'
import type { NovelSectionResponse, NovelSectionType } from '@/api/novel'

// API 配置
export const API_BASE_URL = import.meta.env.MODE === 'production' ? '' : 'http://127.0.0.1:8000'
export const ADMIN_API_PREFIX = '/api/admin'

// 统一请求封装
const request = async (url: string, options: RequestInit = {}) => {
  const authStore = useAuthStore()
  const headers = new Headers({
    'Content-Type': 'application/json',
    ...options.headers
  })

  if (authStore.isAuthenticated && authStore.token) {
    headers.set('Authorization', `Bearer ${authStore.token}`)
  }

  const response = await fetch(url, { ...options, headers })

  if (response.status === 401) {
    authStore.logout()
    router.push('/login')
    throw new Error('会话已过期，请重新登录')
  }

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `请求失败，状态码: ${response.status}`)
  }

  if (response.status === 204) {
    return
  }

  return response.json()
}

const adminRequest = (path: string, options: RequestInit = {}) =>
  request(`${API_BASE_URL}${ADMIN_API_PREFIX}${path}`, options)

// 类型定义
export interface Statistics {
  novel_count: number
  user_count: number
  api_request_count: number
}

export interface LLMCallLog {
  id: number
  user_id?: number | null
  project_id?: string | null
  request_type: string
  provider: string
  model?: string | null
  status: string
  latency_ms?: number | null
  input_chars: number
  output_chars: number
  estimated_input_tokens: number
  estimated_output_tokens: number
  estimated_cost_usd?: number | null
  finish_reason?: string | null
  error_type?: string | null
  error_message?: string | null
  created_at: string
}

export interface LLMCallSummary {
  period_hours: number
  total_calls: number
  success_calls: number
  error_calls: number
  success_rate: number
  avg_latency_ms: number
  total_input_tokens: number
  total_output_tokens: number
  total_estimated_cost_usd: number
}

export interface LLMGroupedTrendSeries {
  key: string
  total_calls: number
  points: number[]
}

export interface LLMGroupedTrendResponse {
  period_hours: number
  group_by: 'model' | 'user'
  buckets: string[]
  series: LLMGroupedTrendSeries[]
}

export interface LLMErrorTopItem {
  error_type: string
  sample_message: string
  count: number
  latest_at: string
}

export interface LLMBudgetAlertItem {
  scope_type: 'global' | 'user' | 'project' | string
  scope_key: string
  scope_label: string
  spent_usd: number
  limit_usd: number
  usage_ratio: number
  level: 'ok' | 'warning' | 'critical' | 'exceeded' | string
  is_alerting: boolean
}

export interface LLMBudgetAlertResponse {
  generated_at: string
  warning_threshold: number
  critical_threshold: number
  global_alert?: LLMBudgetAlertItem | null
  users: LLMBudgetAlertItem[]
  projects: LLMBudgetAlertItem[]
}

export interface WriterTaskQueueItem {
  chapter_id: number
  project_id: string
  project_title: string
  chapter_number: number
  status: string
  queue_state: 'active' | 'failed' | 'done' | 'other' | string
  owner_user_id: number
  owner_username?: string | null
  word_count: number
  selected_version_id?: number | null
  updated_at: string
  age_minutes: number
}

export interface WriterTaskQueueResponse {
  total: number
  status_group: 'active' | 'failed' | 'all' | string
  status_counts: Record<string, number>
  items: WriterTaskQueueItem[]
}

export interface WriterTaskRetryPayload {
  chapter_id: number
  retry_mode?: 'auto' | 'generate' | 'evaluate'
  writing_notes?: string
  force?: boolean
}

export interface WriterTaskRetryResponse {
  accepted: boolean
  chapter_id: number
  project_id: string
  chapter_number: number
  previous_status: string
  dispatched_action: 'generate' | 'evaluate' | string
  message: string
}

export interface LLMCallLogQuery {
  limit?: number
  offset?: number
  hours?: number
  status_filter?: string
  request_type?: string
  model?: string
  user_id?: number
  project_id?: string
}

export interface LLMTrendQuery {
  hours?: number
  group_by?: 'model' | 'user'
  limit?: number
  status_filter?: string
  request_type?: string
  model?: string
  user_id?: number
  project_id?: string
}

export interface LLMErrorTopQuery {
  hours?: number
  limit?: number
  request_type?: string
  model?: string
  user_id?: number
  project_id?: string
}

export interface LLMBudgetAlertQuery {
  limit_each?: number
  only_alerting?: boolean
}

export interface WriterTaskQueueQuery {
  limit?: number
  status_group?: 'active' | 'failed' | 'all'
  project_id?: string
  user_id?: number
}

export interface AdminUser {
  id: number
  username: string
  email?: string | null
  is_admin: boolean
  is_active: boolean
}

export interface UserCreatePayload {
  username: string
  email?: string
  password: string
  is_admin?: boolean
  is_active?: boolean
}

export interface UserUpdatePayload {
  username?: string
  email?: string
  password?: string
  is_admin?: boolean
  is_active?: boolean
}

export interface NovelProjectSummary {
  id: string
  title: string
  genre: string
  last_edited: string
  completed_chapters: number
  total_chapters: number
}

export interface AdminNovelSummary extends NovelProjectSummary {
  owner_id: number
  owner_username: string
}

export interface Chapter {
  chapter_number: number
  title: string
  summary: string
  content?: string | null
  status?: string
  version_id?: string | number | null
  versions?: any[]
  word_count?: number
}

export interface NovelProject {
  id: string
  user_id: number
  title: string
  initial_prompt: string
  conversation_history: any[]
  blueprint?: any
  chapters: Chapter[]
}

export interface PromptItem {
  id: number
  name: string
  title?: string | null
  content: string
  tags?: string[] | null
}

export interface PromptCreatePayload {
  name: string
  content: string
  title?: string
  tags?: string[]
}

export type PromptUpdatePayload = Partial<Omit<PromptCreatePayload, 'name'>>

export interface WritingPresetItem {
  preset_id: string
  name: string
  description?: string | null
  prompt_name: string
  temperature: number
  top_p?: number | null
  max_tokens?: number | null
  style_rules: string[]
  writing_notes_prefix?: string | null
  is_builtin: boolean
  is_active: boolean
}

export interface WritingPresetUpsertPayload {
  preset_id: string
  name: string
  description?: string
  prompt_name: string
  temperature: number
  top_p?: number | null
  max_tokens?: number | null
  style_rules?: string[]
  writing_notes_prefix?: string | null
}

export interface UpdateLog {
  id: number
  content: string
  created_at: string
  created_by?: string | null
  is_pinned: boolean
}

export interface UpdateLogPayload {
  content?: string
  is_pinned?: boolean
}

export interface DailyRequestLimit {
  limit: number
}

export interface SystemConfig {
  key: string
  value: string
  description?: string | null
}

export interface SystemConfigUpsertPayload {
  value: string
  description?: string | null
}

export type SystemConfigUpdatePayload = Partial<SystemConfigUpsertPayload>

export class AdminAPI {
  private static request(path: string, options: RequestInit = {}) {
    return adminRequest(path, options)
  }

  // Overview
  static getStatistics(): Promise<Statistics> {
    return this.request('/stats')
  }

  static getLLMCallSummary(
    hours = 24,
    statusFilter?: string,
    requestType?: string,
    model?: string,
    userId?: number,
    projectId?: string
  ): Promise<LLMCallSummary> {
    const params = new URLSearchParams()
    params.set('hours', String(hours))
    if (statusFilter) params.set('status_filter', statusFilter)
    if (requestType) params.set('request_type', requestType)
    if (model) params.set('model', model)
    if (userId != null) params.set('user_id', String(userId))
    if (projectId) params.set('project_id', projectId)
    return this.request(`/llm-call-logs/summary?${params.toString()}`)
  }

  static listLLMCallLogs(query: LLMCallLogQuery = {}): Promise<LLMCallLog[]> {
    const params = new URLSearchParams()
    if (query.limit != null) params.set('limit', String(query.limit))
    if (query.offset != null) params.set('offset', String(query.offset))
    if (query.hours != null) params.set('hours', String(query.hours))
    if (query.status_filter) params.set('status_filter', query.status_filter)
    if (query.request_type) params.set('request_type', query.request_type)
    if (query.model) params.set('model', query.model)
    if (query.user_id != null) params.set('user_id', String(query.user_id))
    if (query.project_id) params.set('project_id', query.project_id)
    const queryString = params.toString()
    return this.request(`/llm-call-logs${queryString ? `?${queryString}` : ''}`)
  }

  static getLLMHourlyGroupedTrend(query: LLMTrendQuery = {}): Promise<LLMGroupedTrendResponse> {
    const params = new URLSearchParams()
    if (query.hours != null) params.set('hours', String(query.hours))
    if (query.group_by) params.set('group_by', query.group_by)
    if (query.limit != null) params.set('limit', String(query.limit))
    if (query.status_filter) params.set('status_filter', query.status_filter)
    if (query.request_type) params.set('request_type', query.request_type)
    if (query.model) params.set('model', query.model)
    if (query.user_id != null) params.set('user_id', String(query.user_id))
    if (query.project_id) params.set('project_id', query.project_id)
    return this.request(`/llm-call-logs/hourly-grouped?${params.toString()}`)
  }

  static getLLMErrorTop(query: LLMErrorTopQuery = {}): Promise<LLMErrorTopItem[]> {
    const params = new URLSearchParams()
    if (query.hours != null) params.set('hours', String(query.hours))
    if (query.limit != null) params.set('limit', String(query.limit))
    if (query.request_type) params.set('request_type', query.request_type)
    if (query.model) params.set('model', query.model)
    if (query.user_id != null) params.set('user_id', String(query.user_id))
    if (query.project_id) params.set('project_id', query.project_id)
    return this.request(`/llm-call-logs/errors-top?${params.toString()}`)
  }

  static getLLMBudgetAlerts(query: LLMBudgetAlertQuery = {}): Promise<LLMBudgetAlertResponse> {
    const params = new URLSearchParams()
    if (query.limit_each != null) params.set('limit_each', String(query.limit_each))
    if (query.only_alerting != null) params.set('only_alerting', String(query.only_alerting))
    const queryString = params.toString()
    return this.request(`/llm-budget-alerts${queryString ? `?${queryString}` : ''}`)
  }

  static getWriterTaskQueue(query: WriterTaskQueueQuery = {}): Promise<WriterTaskQueueResponse> {
    const params = new URLSearchParams()
    if (query.limit != null) params.set('limit', String(query.limit))
    if (query.status_group) params.set('status_group', query.status_group)
    if (query.project_id) params.set('project_id', query.project_id)
    if (query.user_id != null) params.set('user_id', String(query.user_id))
    const queryString = params.toString()
    return this.request(`/writer-task-queue${queryString ? `?${queryString}` : ''}`)
  }

  static retryWriterTask(payload: WriterTaskRetryPayload): Promise<WriterTaskRetryResponse> {
    return this.request('/writer-task-queue/retry', {
      method: 'POST',
      body: JSON.stringify(payload)
    })
  }

  static async exportLLMCallLogsCsv(query: {
    hours?: number
    status_filter?: string
    request_type?: string
    model?: string
    user_id?: number
    project_id?: string
    max_rows?: number
  } = {}): Promise<Blob> {
    const params = new URLSearchParams()
    if (query.hours != null) params.set('hours', String(query.hours))
    if (query.status_filter) params.set('status_filter', query.status_filter)
    if (query.request_type) params.set('request_type', query.request_type)
    if (query.model) params.set('model', query.model)
    if (query.user_id != null) params.set('user_id', String(query.user_id))
    if (query.project_id) params.set('project_id', query.project_id)
    if (query.max_rows != null) params.set('max_rows', String(query.max_rows))

    const authStore = useAuthStore()
    const headers = new Headers()
    if (authStore.isAuthenticated && authStore.token) {
      headers.set('Authorization', `Bearer ${authStore.token}`)
    }
    const response = await fetch(
      `${API_BASE_URL}${ADMIN_API_PREFIX}/llm-call-logs/export.csv?${params.toString()}`,
      { method: 'GET', headers }
    )

    if (response.status === 401) {
      authStore.logout()
      router.push('/login')
      throw new Error('会话已过期，请重新登录')
    }
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.detail || `导出失败，状态码: ${response.status}`)
    }
    return response.blob()
  }

  // Users
  static listUsers(): Promise<AdminUser[]> {
    return this.request('/users')
  }

  static createUser(payload: UserCreatePayload): Promise<AdminUser> {
    return this.request('/users', {
      method: 'POST',
      body: JSON.stringify(payload)
    })
  }

  static getUser(id: number): Promise<AdminUser> {
    return this.request(`/users/${id}`)
  }

  static updateUser(id: number, payload: UserUpdatePayload): Promise<AdminUser> {
    return this.request(`/users/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload)
    })
  }

  static deleteUser(id: number): Promise<void> {
    return this.request(`/users/${id}`, {
      method: 'DELETE'
    })
  }

  // Novels
  static listNovels(): Promise<AdminNovelSummary[]> {
    return this.request('/novel-projects')
  }

  static getNovelDetails(projectId: string): Promise<NovelProject> {
    return this.request(`/novel-projects/${projectId}`)
  }

  static getNovelSection(projectId: string, section: NovelSectionType): Promise<NovelSectionResponse> {
    return this.request(`/novel-projects/${projectId}/sections/${section}`)
  }

  static getNovelChapter(projectId: string, chapterNumber: number): Promise<Chapter> {
    return this.request(`/novel-projects/${projectId}/chapters/${chapterNumber}`)
  }

  // Prompts
  static listPrompts(): Promise<PromptItem[]> {
    return this.request('/prompts')
  }

  static createPrompt(payload: PromptCreatePayload): Promise<PromptItem> {
    return this.request('/prompts', {
      method: 'POST',
      body: JSON.stringify(payload)
    })
  }

  static getPrompt(id: number): Promise<PromptItem> {
    return this.request(`/prompts/${id}`)
  }

  static updatePrompt(id: number, payload: PromptUpdatePayload): Promise<PromptItem> {
    return this.request(`/prompts/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload)
    })
  }

  static deletePrompt(id: number): Promise<void> {
    return this.request(`/prompts/${id}`, {
      method: 'DELETE'
    })
  }

  static listWritingPresets(): Promise<WritingPresetItem[]> {
    return this.request('/prompts/presets')
  }

  static upsertWritingPreset(payload: WritingPresetUpsertPayload): Promise<WritingPresetItem> {
    return this.request('/prompts/presets', {
      method: 'POST',
      body: JSON.stringify(payload)
    })
  }

  static activateWritingPreset(presetId: string | null): Promise<WritingPresetItem | null> {
    return this.request('/prompts/presets/active', {
      method: 'PUT',
      body: JSON.stringify({ preset_id: presetId })
    })
  }

  static deleteWritingPreset(presetId: string): Promise<void> {
    return this.request(`/prompts/presets/${encodeURIComponent(presetId)}`, {
      method: 'DELETE'
    })
  }

  // Update logs
  static listUpdateLogs(): Promise<UpdateLog[]> {
    return this.request('/update-logs')
  }

  static createUpdateLog(payload: UpdateLogPayload & { content: string }): Promise<UpdateLog> {
    return this.request('/update-logs', {
      method: 'POST',
      body: JSON.stringify(payload)
    })
  }

  static updateUpdateLog(id: number, payload: UpdateLogPayload): Promise<UpdateLog> {
    return this.request(`/update-logs/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload)
    })
  }

  static deleteUpdateLog(id: number): Promise<void> {
    return this.request(`/update-logs/${id}`, {
      method: 'DELETE'
    })
  }

  // Settings
  static getDailyRequestLimit(): Promise<DailyRequestLimit> {
    return this.request('/settings/daily-request-limit')
  }

  static setDailyRequestLimit(limit: number): Promise<DailyRequestLimit> {
    return this.request('/settings/daily-request-limit', {
      method: 'PUT',
      body: JSON.stringify({ limit })
    })
  }

  static listSystemConfigs(): Promise<SystemConfig[]> {
    return this.request('/system-configs')
  }

  static upsertSystemConfig(key: string, payload: SystemConfigUpsertPayload): Promise<SystemConfig> {
    return this.request(`/system-configs/${key}`, {
      method: 'PUT',
      body: JSON.stringify({ key, ...payload })
    })
  }

  static patchSystemConfig(key: string, payload: SystemConfigUpdatePayload): Promise<SystemConfig> {
    return this.request(`/system-configs/${key}`, {
      method: 'PATCH',
      body: JSON.stringify(payload)
    })
  }

  static deleteSystemConfig(key: string): Promise<void> {
    return this.request(`/system-configs/${key}`, {
      method: 'DELETE'
    })
  }

  static changePassword(oldPassword: string, newPassword: string): Promise<void> {
    return this.request('/password', {
      method: 'POST',
      body: JSON.stringify({
        old_password: oldPassword,
        new_password: newPassword
      })
    })
  }
}
