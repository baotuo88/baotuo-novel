// AIMETA P=小说API客户端_小说和章节接口|R=小说CRUD_章节管理_生成|NR=不含UI逻辑|E=api:novel|X=internal|A=novelApi对象|D=axios|S=net|RD=./README.ai
import { useAuthStore } from '@/stores/auth'
import router from '@/router'
import { API_BASE_URL, API_PREFIX, WRITER_API_PREFIX } from './config'

// 对外保持兼容导出，避免其它模块引用路径变更
export { API_BASE_URL, API_PREFIX } from './config'
const DEFAULT_REQUEST_TIMEOUT_MS = Math.max(
  5000,
  Number(import.meta.env.VITE_API_TIMEOUT_MS || 95000)
)

type RequestOptions = RequestInit & {
  timeoutMs?: number
}

const isLikelyHtml = (value: string): boolean => {
  const trimmed = value.trim().toLowerCase()
  if (!trimmed) return false
  return (
    trimmed.startsWith('<!doctype html') ||
    trimmed.startsWith('<html') ||
    (trimmed.startsWith('<') && trimmed.includes('</'))
  )
}

const extractErrorMessage = async (response: Response): Promise<string> => {
  const rawText = await response.text().catch(() => '')
  if (!rawText) return ''

  try {
    const errorData = JSON.parse(rawText)
    const detail = errorData?.detail || errorData?.message || ''
    return typeof detail === 'string' ? detail.trim() : ''
  } catch {
    const trimmed = rawText.trim()
    if (!trimmed || isLikelyHtml(trimmed)) {
      return ''
    }
    return trimmed.slice(0, 240)
  }
}

const normalizeErrorMessage = (status: number, detail: string): string => {
  if ([502, 503, 504].includes(status)) {
    return '上游 AI 服务响应超时或暂时不可用，请稍后重试'
  }
  if (status === 429) {
    return detail || '请求过于频繁，请稍后再试'
  }
  if (status >= 500) {
    return detail || '服务器内部错误，请稍后重试'
  }
  return detail || `请求失败，状态码: ${status}`
}

const parseResponsePayload = async <T>(response: Response): Promise<T> => {
  if (response.status === 204) {
    return null as T
  }

  const contentType = response.headers.get('content-type') || ''
  if (contentType.includes('application/json')) {
    return (await response.json()) as T
  }

  const text = await response.text()
  if (!text.trim()) {
    return null as T
  }
  try {
    return JSON.parse(text) as T
  } catch {
    return text as T
  }
}

const parseDownloadFilename = (contentDisposition: string | null, fallback: string): string => {
  if (!contentDisposition) return fallback
  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1])
    } catch {
      return utf8Match[1]
    }
  }
  const plainMatch = contentDisposition.match(/filename="?([^";]+)"?/i)
  if (plainMatch?.[1]) {
    return plainMatch[1]
  }
  return fallback
}

// 统一的请求处理函数
const request = async <T = any>(url: string, options: RequestOptions = {}): Promise<T> => {
  const authStore = useAuthStore()
  const timeoutMs = options.timeoutMs ?? DEFAULT_REQUEST_TIMEOUT_MS
  const controller = new AbortController()
  const timeoutId = globalThis.setTimeout(() => {
    controller.abort(new Error('Request timeout'))
  }, timeoutMs)

  const headers = new Headers({
    'Content-Type': 'application/json',
    ...options.headers
  })

  // 如果 body 是 FormData，删除 Content-Type header，让浏览器自动设置（包含 boundary）
  if (options.body instanceof FormData) {
    headers.delete('Content-Type')
  }

  if (authStore.isAuthenticated && authStore.token) {
    headers.set('Authorization', `Bearer ${authStore.token}`)
  }

  if (options.signal) {
    if (options.signal.aborted) {
      controller.abort()
    } else {
      options.signal.addEventListener('abort', () => controller.abort(), { once: true })
    }
  }

  let response: Response
  try {
    response = await fetch(url, { ...options, headers, signal: controller.signal })
  } catch (error) {
    const isAbort = (error as DOMException)?.name === 'AbortError'
    if (isAbort) {
      if (options.signal?.aborted) {
        throw new Error('请求已取消')
      }
      throw new Error(`请求超时（>${Math.ceil(timeoutMs / 1000)}秒），请稍后重试`)
    }
    throw new Error('网络连接失败，请检查网络或服务状态')
  } finally {
    globalThis.clearTimeout(timeoutId)
  }

  if (response.status === 401) {
    // Token 失效或未授权
    authStore.logout()
    router.push('/login')
    throw new Error('会话已过期，请重新登录')
  }

  if (!response.ok) {
    const detail = await extractErrorMessage(response)
    throw new Error(normalizeErrorMessage(response.status, detail))
  }

  return parseResponsePayload<T>(response)
}

// 类型定义
export interface NovelProject {
  id: string
  title: string
  initial_prompt: string
  blueprint?: Blueprint
  chapters: Chapter[]
  conversation_history: ConversationMessage[]
}

export interface NovelProjectSummary {
  id: string
  title: string
  genre: string
  last_edited: string
  completed_chapters: number
  total_chapters: number
}

export interface Blueprint {
  title?: string
  target_audience?: string
  genre?: string
  style?: string
  tone?: string
  one_sentence_summary?: string
  full_synopsis?: string
  world_setting?: any
  characters?: Character[]
  relationships?: any[]
  chapter_outline?: ChapterOutline[]
}

export interface Character {
  name: string
  description: string
  identity?: string
  personality?: string
  goals?: string
  abilities?: string
  relationship_to_protagonist?: string
}

export interface ChapterOutline {
  chapter_number: number
  title: string
  summary: string
}

export interface ChapterVersion {
  content: string
  style?: string
}

export interface Chapter {
  chapter_number: number
  title: string
  summary: string
  content: string | null
  versions: string[] | null  // versions是字符串数组，不是对象数组
  evaluation: string | null
  generation_status: 'not_generated' | 'generating' | 'evaluating' | 'selecting' | 'failed' | 'evaluation_failed' | 'waiting_for_confirm' | 'successful'
  word_count?: number  // 字数统计
}

export interface ConversationMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface ConverseResponse {
  ai_message: string
  ui_control: UIControl
  conversation_state: any
  is_complete: boolean
  ready_for_blueprint?: boolean  // 新增：表示准备生成蓝图
}

export interface BlueprintGenerationResponse {
  blueprint: Blueprint
  ai_message: string
}

export interface BlueprintGenerationAsyncAccepted {
  project_id: string
  status: 'accepted' | 'running'
  message: string
  poll_interval_seconds: number
}

export interface BlueprintGenerationStatusResponse {
  project_id: string
  status: 'not_started' | 'generating' | 'completed' | 'failed'
  blueprint?: Blueprint | null
  ai_message?: string | null
  error_message?: string | null
}

export interface UIControl {
  type: 'single_choice' | 'text_input'
  options?: Array<{ id: string; label: string }>
  placeholder?: string
}

export interface ChapterGenerationResponse {
  versions: ChapterVersion[] // Renamed from chapter_versions for consistency
  evaluation: string | null
  ai_message: string
  chapter_number: number
}

export interface WriterTaskCenterItem {
  task_id: string
  chapter_id: number
  project_id: string
  chapter_number: number
  status: string
  queue_state: 'active' | 'failed' | 'done' | 'other'
  progress_percent: number
  stage_label: string
  status_message: string
  can_cancel: boolean
  can_retry: boolean
  word_count: number
  selected_version_id?: number | null
  updated_at: string
  age_minutes: number
  error_message?: string | null
  failure_category?: string | null
  stalled?: boolean
  stalled_seconds?: number
  self_heal_hint?: string | null
  can_force_retry?: boolean
  consistency_guard_status?: string | null
  consistency_guard_message?: string | null
  consistency_fixed_version_id?: number | null
}

export interface WriterTaskCenterResponse {
  total: number
  active_count: number
  failed_count: number
  done_count: number
  items: WriterTaskCenterItem[]
}

export interface WriterTaskStreamQuery {
  limit?: number
  status_group?: 'active' | 'failed' | 'all'
  interval_seconds?: number
}

export interface WriterTaskRetryPayload {
  writing_notes?: string
  force?: boolean
  resume_from_checkpoint?: boolean
}

export interface WriterTaskRetryResponse {
  accepted: boolean
  task_id: string
  project_id: string
  chapter_number: number
  previous_status: string
  message: string
}

export interface WriterTaskCancelResponse {
  accepted: boolean
  task_id: string
  project_id: string
  chapter_number: number
  message: string
}

export interface ChapterVersionDetail {
  id: number
  version_label?: string | null
  created_at: string
  content: string
  metadata?: Record<string, any> | null
  word_count: number
  is_selected: boolean
}

export interface ChapterVersionListResponse {
  project_id: string
  chapter_number: number
  selected_version_id?: number | null
  total_versions: number
  versions: ChapterVersionDetail[]
}

export interface ChapterVersionDiffResponse {
  project_id: string
  chapter_number: number
  base_version_id: number
  compare_version_id: number
  base_version_label?: string | null
  compare_version_label?: string | null
  base_content: string
  compare_content: string
}

export interface ChapterVersionRollbackPayload {
  version_id: number
  reason?: string
}

export interface ChapterVersionRollbackResponse {
  project_id: string
  chapter_number: number
  selected_version_id: number
  rollback_from_version_id?: number | null
  rollback_to_version_id: number
  message: string
}

export interface DeleteNovelsResponse {
  status: string
  message: string
}

// 内容型Section（对应后端NovelSectionType枚举）
export type NovelSectionType = 'overview' | 'world_setting' | 'characters' | 'relationships' | 'chapter_outline' | 'chapters'

// 分析型Section（不属于NovelSectionType，使用独立的analytics API）
export type AnalysisSectionType =
  | 'emotion_curve'
  | 'foreshadowing'
  | 'world_graph'
  | 'timeline'
  | 'terminology'
  | 'quality_dashboard'
  | 'publish_center'
  | 'material_library'
  | 'project_backup'
  | 'global_search'

// 所有Section的联合类型
export type AllSectionType = NovelSectionType | AnalysisSectionType

export interface NovelSectionResponse {
  section: NovelSectionType
  data: Record<string, any>
}

export interface GraphNode {
  id: string
  label: string
  node_type: string
  group: string
  level?: number | null
  meta: Record<string, any>
}

export interface GraphEdge {
  id: string
  source: string
  target: string
  relation: string
  label?: string | null
  weight: number
}

export interface FactionItem {
  id: number
  name: string
  faction_type?: string | null
  description?: string | null
  power_level?: string | null
  territory?: string | null
  leader?: string | null
  current_status?: string | null
}

export interface FactionRelationshipItem {
  id?: number
  project_id?: string
  faction_from_id: number
  faction_to_id: number
  relationship_type: string
  strength?: number | null
  description?: string | null
  reason?: string | null
}

export type PublishFormat = 'markdown' | 'txt' | 'docx' | 'epub'
export type PublishTocStyle = 'none' | 'compact' | 'detailed'

export interface PublishSummaryResponse {
  project_id: string
  title: string
  chapter_total: number
  outline_total: number
  generated_chapter_total: number
  first_chapter_number?: number | null
  last_chapter_number?: number | null
  latest_generated_chapter?: number | null
  generated_at: string
}

export interface ProjectMaterialItem {
  id: string
  title: string
  material_type: string
  content: string
  tags: string[]
  source?: string | null
  source_url?: string | null
  created_at: string
  updated_at: string
}

export interface ProjectMaterialListResponse {
  project_id: string
  total: number
  page: number
  page_size: number
  items: ProjectMaterialItem[]
}

export interface ProjectMaterialPayload {
  title: string
  material_type?: string
  content?: string
  tags?: string[]
  source?: string | null
  source_url?: string | null
}

export interface ProjectBackupImportPayload {
  backup: Record<string, any>
}

export interface ProjectBackupImportResponse {
  project_id: string
  title: string
  stats: Record<string, number>
  message: string
}

export interface ProjectBackupRestoreResponse {
  project_id: string
  stats: Record<string, number>
  message: string
}

export interface GlobalSearchAnchor {
  section: AllSectionType | string
  chapter_number?: number | null
  timeline_event_id?: number | null
  foreshadowing_id?: number | null
  material_id?: string | null
  term?: string | null
}

export interface GlobalSearchItem {
  id: string
  scope: string
  title: string
  snippet: string
  score: number
  chapter_number?: number | null
  anchor: GlobalSearchAnchor
}

export interface GlobalSearchResponse {
  project_id: string
  query: string
  total: number
  items: GlobalSearchItem[]
}

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

export interface ConsistencyViolationItem {
  severity: string
  category: string
  description: string
  location?: string | null
  suggested_fix?: string | null
  confidence?: number
}

export interface ConsistencyActionSuggestion {
  action_id: string
  severity: string
  category: string
  title: string
  description: string
  suggested_fix?: string | null
  confidence?: number
  auto_fix_recommended: boolean
}

export interface ChapterConsistencyReview {
  is_consistent: boolean
  summary: string
  check_time_ms: number
  violations: ConsistencyViolationItem[]
}

export interface ChapterConsistencyCheckResponse {
  project_id: string
  chapter_number: number
  review: ChapterConsistencyReview
  action_suggestions?: ConsistencyActionSuggestion[]
  auto_fix_available?: boolean
}

export interface ChapterConsistencyFixPayload {
  auto_select?: boolean
  min_severity?: 'critical' | 'major' | 'minor'
  preview_only?: boolean
  fixed_content?: string
}

export interface ChapterConsistencyFixResponse {
  project_id: string
  chapter_number: number
  fixed: boolean
  review: ChapterConsistencyReview
  created_version_id?: number | null
  selected_version_id?: number | null
  message: string
  preview_only?: boolean
  preview_base_content?: string | null
  preview_content?: string | null
}

export interface WorldGraphResponse {
  project_id: string
  generated_at: string
  world_tree: {
    root_id: string
    nodes: GraphNode[]
    edges: GraphEdge[]
  }
  relation_graph: {
    nodes: GraphNode[]
    edges: GraphEdge[]
  }
  stats: {
    world_tree_nodes: number
    world_tree_edges: number
    relation_nodes: number
    relation_edges: number
    character_count: number
    faction_count: number
  }
}

export interface ProjectQualityDashboard {
  project_id: string
  generated_at: string
  overall_score: number
  metrics: {
    consistency_score: number
    foreshadowing_score: number
    completion_score: number
    stability_score: number
  }
  chapter_stats: {
    total_chapters: number
    successful_chapters: number
    failed_chapters: number
    average_word_count: number
  }
  consistency: {
    checked_versions: number
    consistent_versions: number
    violation_count: number
    severity_breakdown: Record<string, number>
  }
  foreshadowing: {
    total: number
    resolved: number
    unresolved: number
    overall_quality_score: number
  }
  timeline: {
    event_count: number
    turning_points: number
  }
  top_risks: string[]
  recommendations: string[]
}

export interface TimelineEventItem {
  id?: number
  project_id?: string
  chapter_number: number
  story_time?: string | null
  story_date?: string | null
  time_elapsed?: string | null
  event_type?: string | null
  event_title: string
  event_description?: string | null
  involved_characters: string[]
  location?: string | null
  importance: number
  is_turning_point: boolean
  extra?: Record<string, any> | null
  created_at?: string | null
}

export interface ProjectTimelineResponse {
  project_id: string
  start_chapter?: number | null
  end_chapter?: number | null
  updated_count?: number
  events: TimelineEventItem[]
}

export interface TerminologyEntryItem {
  term: string
  canonical?: string | null
  aliases: string[]
  category?: string | null
  note?: string | null
  enforce: boolean
}

export interface TerminologyDictionaryResponse {
  project_id: string
  items: TerminologyEntryItem[]
  count?: number
}

export type ForeshadowingStatus = 'open' | 'planted' | 'developing' | 'partial' | 'resolved' | 'revealed' | 'paid_off' | 'abandoned' | string

export interface ForeshadowingBoardItem {
  id: number
  chapter_number: number
  content: string
  type: string
  status: ForeshadowingStatus
  resolved_chapter_number?: number | null
  is_manual: boolean
  ai_confidence?: number | null
  author_note?: string | null
  created_at: string
}

export interface ForeshadowingListResponse {
  total: number
  limit: number
  offset: number
  data: ForeshadowingBoardItem[]
}

export interface ForeshadowingCreatePayload {
  chapter_id?: number
  chapter_number: number
  content: string
  type: string
  keywords?: string[]
  author_note?: string
}

export interface ForeshadowingResolvePayload {
  resolved_chapter_id?: number
  resolved_chapter_number: number
  resolution_text: string
  resolution_type?: string
  quality_score?: number
}

export interface ForeshadowingAbandonPayload {
  reason?: string
}

export interface ForeshadowingReminderItem {
  id: number
  foreshadowing_id: number
  reminder_type: string
  message: string
  status: string
  created_at: string
}

export interface ForeshadowingReminderListResponse {
  total: number
  data: ForeshadowingReminderItem[]
}

export interface ForeshadowingAnalysisResponse {
  total_foreshadowings: number
  resolved_count: number
  unresolved_count: number
  abandoned_count: number
  avg_resolution_distance?: number | null
  unresolved_ratio?: number | null
  overall_quality_score?: number | null
  recommendations: string[]
  pattern_analysis?: Record<string, number>
  analyzed_at?: string
}

// API 函数
const NOVELS_BASE = `${API_BASE_URL}${API_PREFIX}/novels`
const WRITER_PREFIX = WRITER_API_PREFIX
const WRITER_BASE = `${API_BASE_URL}${WRITER_PREFIX}/novels`

export class NovelAPI {
  static async createNovel(title: string, initialPrompt: string): Promise<NovelProject> {
    return request(NOVELS_BASE, {
      method: 'POST',
      body: JSON.stringify({ title, initial_prompt: initialPrompt })
    })
  }

  static async importNovel(file: File): Promise<{ id: string }> {
    const formData = new FormData()
    formData.append('file', file)
    return request(`${NOVELS_BASE}/import`, {
      method: 'POST',
      body: formData,
      headers: {
        // 让 browser 自动设置 Content-Type 为 multipart/form-data，不手动设置
      }
    })
  }

  static async getNovel(projectId: string): Promise<NovelProject> {
    return request(`${NOVELS_BASE}/${projectId}`)
  }

  static async getChapter(projectId: string, chapterNumber: number): Promise<Chapter> {
    return request(`${NOVELS_BASE}/${projectId}/chapters/${chapterNumber}`)
  }

  static async getSection(projectId: string, section: NovelSectionType): Promise<NovelSectionResponse> {
    return request(`${NOVELS_BASE}/${projectId}/sections/${section}`)
  }

  static async getWorldGraph(projectId: string): Promise<WorldGraphResponse> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/world-graph`)
  }

  static async getProjectTimeline(
    projectId: string,
    query: { start_chapter?: number; end_chapter?: number } = {}
  ): Promise<ProjectTimelineResponse> {
    const params = new URLSearchParams()
    if (query.start_chapter != null) params.set('start_chapter', String(query.start_chapter))
    if (query.end_chapter != null) params.set('end_chapter', String(query.end_chapter))
    const queryString = params.toString()
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/timeline${queryString ? `?${queryString}` : ''}`)
  }

  static async getProjectQualityDashboard(projectId: string): Promise<ProjectQualityDashboard> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/quality-dashboard`)
  }

  static async getPublishSummary(projectId: string): Promise<PublishSummaryResponse> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/publish/summary`)
  }

  static async downloadPublishExport(
    projectId: string,
    query: {
      format: PublishFormat
      start_chapter?: number
      end_chapter?: number
      include_outline?: boolean
      include_metadata?: boolean
      toc_style?: PublishTocStyle
      webhook_url?: string
    }
  ): Promise<void> {
    const params = new URLSearchParams()
    params.set('format', query.format)
    if (query.start_chapter != null) params.set('start_chapter', String(query.start_chapter))
    if (query.end_chapter != null) params.set('end_chapter', String(query.end_chapter))
    if (query.include_outline != null) params.set('include_outline', String(query.include_outline))
    if (query.include_metadata != null) params.set('include_metadata', String(query.include_metadata))
    if (query.toc_style) params.set('toc_style', query.toc_style)
    if (query.webhook_url) params.set('webhook_url', query.webhook_url)

    const authStore = useAuthStore()
    const headers = new Headers()
    if (authStore.isAuthenticated && authStore.token) {
      headers.set('Authorization', `Bearer ${authStore.token}`)
    }

    const response = await fetch(
      `${API_BASE_URL}${API_PREFIX}/projects/${projectId}/publish/export?${params.toString()}`,
      {
        method: 'GET',
        headers
      }
    )
    if (response.status === 401) {
      authStore.logout()
      router.push('/login')
      throw new Error('会话已过期，请重新登录')
    }
    if (!response.ok) {
      const detail = await extractErrorMessage(response)
      throw new Error(normalizeErrorMessage(response.status, detail))
    }

    const blob = await response.blob()
    const fallbackName = `novel_export_${Date.now()}.${query.format === 'markdown' ? 'md' : query.format}`
    const filename = parseDownloadFilename(response.headers.get('content-disposition'), fallbackName)
    const href = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = href
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(href)
  }

  static async downloadPublishBatchExport(
    projectId: string,
    query: {
      formats: PublishFormat[]
      start_chapter?: number
      end_chapter?: number
      include_outline?: boolean
      include_metadata?: boolean
      toc_style?: PublishTocStyle
      webhook_url?: string
    }
  ): Promise<void> {
    const params = new URLSearchParams()
    params.set('formats', (query.formats || []).join(','))
    if (query.start_chapter != null) params.set('start_chapter', String(query.start_chapter))
    if (query.end_chapter != null) params.set('end_chapter', String(query.end_chapter))
    if (query.include_outline != null) params.set('include_outline', String(query.include_outline))
    if (query.include_metadata != null) params.set('include_metadata', String(query.include_metadata))
    if (query.toc_style) params.set('toc_style', query.toc_style)
    if (query.webhook_url) params.set('webhook_url', query.webhook_url)

    const authStore = useAuthStore()
    const headers = new Headers()
    if (authStore.isAuthenticated && authStore.token) {
      headers.set('Authorization', `Bearer ${authStore.token}`)
    }
    const response = await fetch(
      `${API_BASE_URL}${API_PREFIX}/projects/${projectId}/publish/export-batch?${params.toString()}`,
      { method: 'GET', headers }
    )
    if (response.status === 401) {
      authStore.logout()
      router.push('/login')
      throw new Error('会话已过期，请重新登录')
    }
    if (!response.ok) {
      const detail = await extractErrorMessage(response)
      throw new Error(normalizeErrorMessage(response.status, detail))
    }
    const blob = await response.blob()
    const fallbackName = `novel_export_bundle_${Date.now()}.zip`
    const filename = parseDownloadFilename(response.headers.get('content-disposition'), fallbackName)
    const href = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = href
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(href)
  }

  static async listProjectMaterials(
    projectId: string,
    query: { page?: number; page_size?: number; keyword?: string; material_type?: string } = {}
  ): Promise<ProjectMaterialListResponse> {
    const params = new URLSearchParams()
    if (query.page != null) params.set('page', String(query.page))
    if (query.page_size != null) params.set('page_size', String(query.page_size))
    if (query.keyword) params.set('keyword', query.keyword)
    if (query.material_type) params.set('material_type', query.material_type)
    const queryString = params.toString()
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/materials${queryString ? `?${queryString}` : ''}`)
  }

  static async createProjectMaterial(projectId: string, payload: ProjectMaterialPayload): Promise<ProjectMaterialItem> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/materials`, {
      method: 'POST',
      body: JSON.stringify(payload)
    })
  }

  static async updateProjectMaterial(
    projectId: string,
    materialId: string,
    payload: ProjectMaterialPayload
  ): Promise<ProjectMaterialItem> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/materials/${encodeURIComponent(materialId)}`, {
      method: 'PUT',
      body: JSON.stringify(payload)
    })
  }

  static async deleteProjectMaterial(projectId: string, materialId: string): Promise<{ project_id: string; deleted: boolean; material_id: string }> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/materials/${encodeURIComponent(materialId)}`, {
      method: 'DELETE'
    })
  }

  static async searchProjectGlobal(
    projectId: string,
    query: { q: string; limit?: number; scopes?: string[] }
  ): Promise<GlobalSearchResponse> {
    const params = new URLSearchParams()
    params.set('q', query.q)
    if (query.limit != null) params.set('limit', String(query.limit))
    if (query.scopes && query.scopes.length > 0) {
      params.set('scopes', query.scopes.join(','))
    }
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/global-search?${params.toString()}`)
  }

  static async downloadProjectBackup(projectId: string): Promise<void> {
    const authStore = useAuthStore()
    const headers = new Headers()
    if (authStore.isAuthenticated && authStore.token) {
      headers.set('Authorization', `Bearer ${authStore.token}`)
    }
    const response = await fetch(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/backup/export`, {
      method: 'GET',
      headers
    })
    if (response.status === 401) {
      authStore.logout()
      router.push('/login')
      throw new Error('会话已过期，请重新登录')
    }
    if (!response.ok) {
      const detail = await extractErrorMessage(response)
      throw new Error(normalizeErrorMessage(response.status, detail))
    }
    const blob = await response.blob()
    const fallbackName = `project_backup_${Date.now()}.json`
    const filename = parseDownloadFilename(response.headers.get('content-disposition'), fallbackName)
    const href = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = href
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(href)
  }

  static async importProjectBackup(payload: ProjectBackupImportPayload): Promise<ProjectBackupImportResponse> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/backup/import`, {
      method: 'POST',
      body: JSON.stringify(payload)
    })
  }

  static async restoreProjectFromBackup(
    projectId: string,
    payload: ProjectBackupImportPayload
  ): Promise<ProjectBackupRestoreResponse> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/backup/restore`, {
      method: 'POST',
      body: JSON.stringify(payload)
    })
  }

  static async saveProjectTimeline(
    projectId: string,
    events: TimelineEventItem[]
  ): Promise<ProjectTimelineResponse> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/timeline`, {
      method: 'PUT',
      body: JSON.stringify(events)
    })
  }

  static async getTerminologyDictionary(projectId: string): Promise<TerminologyDictionaryResponse> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/terminology-dictionary`)
  }

  static async saveTerminologyDictionary(
    projectId: string,
    items: TerminologyEntryItem[]
  ): Promise<TerminologyDictionaryResponse> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/terminology-dictionary`, {
      method: 'PUT',
      body: JSON.stringify(items)
    })
  }

  static async listForeshadowings(
    projectId: string,
    query: {
      status?: string
      foreshadowing_type?: string
      limit?: number
      offset?: number
    } = {}
  ): Promise<ForeshadowingListResponse> {
    const params = new URLSearchParams()
    if (query.status) params.set('status', query.status)
    if (query.foreshadowing_type) params.set('foreshadowing_type', query.foreshadowing_type)
    if (query.limit != null) params.set('limit', String(query.limit))
    if (query.offset != null) params.set('offset', String(query.offset))
    const queryString = params.toString()
    return request(`${API_BASE_URL}${API_PREFIX}/novels/${projectId}/foreshadowings${queryString ? `?${queryString}` : ''}`)
  }

  static async createForeshadowing(
    projectId: string,
    payload: ForeshadowingCreatePayload
  ): Promise<ForeshadowingBoardItem> {
    return request(`${API_BASE_URL}${API_PREFIX}/novels/${projectId}/foreshadowings`, {
      method: 'POST',
      body: JSON.stringify(payload)
    })
  }

  static async resolveForeshadowing(
    projectId: string,
    foreshadowingId: number,
    payload: ForeshadowingResolvePayload
  ): Promise<{ status: string; message: string; resolution_id: number }> {
    return request(`${API_BASE_URL}${API_PREFIX}/novels/${projectId}/foreshadowings/${foreshadowingId}/resolve`, {
      method: 'POST',
      body: JSON.stringify(payload)
    })
  }

  static async abandonForeshadowing(
    projectId: string,
    foreshadowingId: number,
    payload: ForeshadowingAbandonPayload = {}
  ): Promise<{ status: string; message: string; foreshadowing_id: number }> {
    return request(`${API_BASE_URL}${API_PREFIX}/novels/${projectId}/foreshadowings/${foreshadowingId}/abandon`, {
      method: 'POST',
      body: JSON.stringify(payload)
    })
  }

  static async getForeshadowingReminders(
    projectId: string,
    limit?: number
  ): Promise<ForeshadowingReminderListResponse> {
    const queryString = limit != null ? `?limit=${encodeURIComponent(String(limit))}` : ''
    return request(`${API_BASE_URL}${API_PREFIX}/novels/${projectId}/foreshadowings/reminders${queryString}`)
  }

  static async dismissForeshadowingReminder(
    projectId: string,
    reminderId: number,
    reason?: string
  ): Promise<{ status: string; message: string }> {
    const queryString = reason ? `?reason=${encodeURIComponent(reason)}` : ''
    return request(`${API_BASE_URL}${API_PREFIX}/novels/${projectId}/foreshadowings/reminders/${reminderId}/dismiss${queryString}`, {
      method: 'POST'
    })
  }

  static async getForeshadowingAnalysis(projectId: string): Promise<ForeshadowingAnalysisResponse> {
    return request(`${API_BASE_URL}${API_PREFIX}/novels/${projectId}/foreshadowings/analysis`)
  }

  static async getFactions(projectId: string): Promise<{ project_id: string; factions: FactionItem[] }> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/factions`)
  }

  static async saveFactions(projectId: string, factions: Partial<FactionItem>[]): Promise<{ project_id: string; factions: FactionItem[] }> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/factions`, {
      method: 'PUT',
      body: JSON.stringify(factions)
    })
  }

  static async getFactionRelationships(projectId: string): Promise<{ project_id: string; relationships: FactionRelationshipItem[] }> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/faction-relationships`)
  }

  static async saveFactionRelationships(projectId: string, relationships: FactionRelationshipItem[]): Promise<{ project_id: string; relationships: FactionRelationshipItem[] }> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/faction-relationships`, {
      method: 'PUT',
      body: JSON.stringify(relationships)
    })
  }

  static async listWriterPresets(projectId?: string): Promise<WritingPresetItem[]> {
    if (projectId) {
      return request(`${API_BASE_URL}${WRITER_PREFIX}/novels/${projectId}/presets`)
    }
    return request(`${API_BASE_URL}${WRITER_PREFIX}/presets`)
  }

  static async setActiveWriterPreset(presetId: string | null, projectId?: string): Promise<WritingPresetItem | null> {
    const endpoint = projectId
      ? `${API_BASE_URL}${WRITER_PREFIX}/novels/${projectId}/presets/active`
      : `${API_BASE_URL}${WRITER_PREFIX}/presets/active`
    return request(endpoint, {
      method: 'PUT',
      body: JSON.stringify({ preset_id: presetId })
    })
  }

  static async converseConcept(
    projectId: string,
    userInput: any,
    conversationState: any = {}
  ): Promise<ConverseResponse> {
    const formattedUserInput = userInput || { id: null, value: null }
    return request(`${NOVELS_BASE}/${projectId}/concept/converse`, {
      method: 'POST',
      body: JSON.stringify({
        user_input: formattedUserInput,
        conversation_state: conversationState
      })
    })
  }

  static async generateBlueprint(projectId: string): Promise<BlueprintGenerationResponse> {
    return request(`${NOVELS_BASE}/${projectId}/blueprint/generate`, {
      method: 'POST'
    })
  }

  static async startGenerateBlueprint(projectId: string): Promise<BlueprintGenerationAsyncAccepted> {
    return request(`${NOVELS_BASE}/${projectId}/blueprint/generate-async`, {
      method: 'POST'
    })
  }

  static async getBlueprintGenerationStatus(projectId: string): Promise<BlueprintGenerationStatusResponse> {
    return request(`${NOVELS_BASE}/${projectId}/blueprint/status`)
  }

  static async saveBlueprint(projectId: string, blueprint: Blueprint): Promise<NovelProject> {
    return request(`${NOVELS_BASE}/${projectId}/blueprint/save`, {
      method: 'POST',
      body: JSON.stringify(blueprint)
    })
  }

  static async generateChapter(projectId: string, chapterNumber: number): Promise<NovelProject> {
    return request(`${WRITER_BASE}/${projectId}/chapters/generate`, {
      method: 'POST',
      body: JSON.stringify({ chapter_number: chapterNumber })
    })
  }

  static async evaluateChapter(projectId: string, chapterNumber: number): Promise<NovelProject> {
    return request(`${WRITER_BASE}/${projectId}/chapters/evaluate`, {
      method: 'POST',
      body: JSON.stringify({ chapter_number: chapterNumber })
    })
  }

  static async selectChapterVersion(
    projectId: string,
    chapterNumber: number,
    versionIndex: number
  ): Promise<NovelProject> {
    return request(`${WRITER_BASE}/${projectId}/chapters/select`, {
      method: 'POST',
      body: JSON.stringify({
        chapter_number: chapterNumber,
        version_index: versionIndex
      })
    })
  }

  static async getWriterTaskCenter(
    projectId: string,
    query: { limit?: number; status_group?: 'active' | 'failed' | 'all' } = {}
  ): Promise<WriterTaskCenterResponse> {
    const params = new URLSearchParams()
    if (query.limit != null) params.set('limit', String(query.limit))
    if (query.status_group) params.set('status_group', query.status_group)
    const queryString = params.toString()
    return request(`${WRITER_BASE}/${projectId}/tasks${queryString ? `?${queryString}` : ''}`)
  }

  static getWriterTaskCenterStreamUrl(
    projectId: string,
    query: WriterTaskStreamQuery = {}
  ): string {
    const params = new URLSearchParams()
    if (query.limit != null) params.set('limit', String(query.limit))
    if (query.status_group) params.set('status_group', query.status_group)
    if (query.interval_seconds != null) params.set('interval_seconds', String(query.interval_seconds))
    const queryString = params.toString()
    return `${API_BASE_URL}${WRITER_BASE}/${projectId}/tasks/stream${queryString ? `?${queryString}` : ''}`
  }

  static async cancelWriterTask(
    projectId: string,
    chapterNumber: number
  ): Promise<WriterTaskCancelResponse> {
    return request(`${WRITER_BASE}/${projectId}/tasks/${chapterNumber}/cancel`, {
      method: 'POST'
    })
  }

  static async retryWriterTask(
    projectId: string,
    chapterNumber: number,
    payload: WriterTaskRetryPayload = {}
  ): Promise<WriterTaskRetryResponse> {
    return request(`${WRITER_BASE}/${projectId}/tasks/${chapterNumber}/retry`, {
      method: 'POST',
      body: JSON.stringify(payload)
    })
  }

  static async listChapterVersions(
    projectId: string,
    chapterNumber: number
  ): Promise<ChapterVersionListResponse> {
    return request(`${WRITER_BASE}/${projectId}/chapters/${chapterNumber}/versions`)
  }

  static async getChapterVersionDiff(
    projectId: string,
    chapterNumber: number,
    baseVersionId: number,
    compareVersionId: number
  ): Promise<ChapterVersionDiffResponse> {
    const params = new URLSearchParams({
      base_version_id: String(baseVersionId),
      compare_version_id: String(compareVersionId)
    })
    return request(`${WRITER_BASE}/${projectId}/chapters/${chapterNumber}/versions/diff?${params.toString()}`)
  }

  static async rollbackChapterVersion(
    projectId: string,
    chapterNumber: number,
    payload: ChapterVersionRollbackPayload
  ): Promise<ChapterVersionRollbackResponse> {
    return request(`${WRITER_BASE}/${projectId}/chapters/${chapterNumber}/versions/rollback`, {
      method: 'POST',
      body: JSON.stringify(payload)
    })
  }

  static async checkChapterConsistency(
    projectId: string,
    chapterNumber: number
  ): Promise<ChapterConsistencyCheckResponse> {
    return request(`${WRITER_BASE}/${projectId}/chapters/${chapterNumber}/consistency-check`, {
      method: 'POST'
    })
  }

  static async fixChapterConsistency(
    projectId: string,
    chapterNumber: number,
    payload: ChapterConsistencyFixPayload = {}
  ): Promise<ChapterConsistencyFixResponse> {
    return request(`${WRITER_BASE}/${projectId}/chapters/${chapterNumber}/consistency-fix`, {
      method: 'POST',
      body: JSON.stringify(payload)
    })
  }

  static async getAllNovels(): Promise<NovelProjectSummary[]> {
    return request(NOVELS_BASE)
  }

  static async deleteNovels(projectIds: string[]): Promise<DeleteNovelsResponse> {
    return request(NOVELS_BASE, {
      method: 'DELETE',
      body: JSON.stringify(projectIds)
    })
  }

  static async updateChapterOutline(
    projectId: string,
    chapterOutline: ChapterOutline
  ): Promise<NovelProject> {
    return request(`${WRITER_BASE}/${projectId}/chapters/update-outline`, {
      method: 'POST',
      body: JSON.stringify(chapterOutline)
    })
  }

  static async deleteChapter(
    projectId: string,
    chapterNumbers: number[]
  ): Promise<NovelProject> {
    return request(`${WRITER_BASE}/${projectId}/chapters/delete`, {
      method: 'POST',
      body: JSON.stringify({ chapter_numbers: chapterNumbers })
    })
  }

  static async generateChapterOutline(
    projectId: string,
    startChapter: number,
    numChapters: number
  ): Promise<NovelProject> {
    return request(`${WRITER_BASE}/${projectId}/chapters/outline`, {
      method: 'POST',
      body: JSON.stringify({
        start_chapter: startChapter,
        num_chapters: numChapters
      })
    })
  }

  static async updateBlueprint(projectId: string, data: Record<string, any>): Promise<NovelProject> {
    return request(`${NOVELS_BASE}/${projectId}/blueprint`, {
      method: 'PATCH',
      body: JSON.stringify(data)
    })
  }

  static async editChapterContent(
    projectId: string,
    chapterNumber: number,
    content: string
  ): Promise<Chapter> {
    return request(`${WRITER_BASE}/${projectId}/chapters/edit-fast`, {
      method: 'POST',
      body: JSON.stringify({
        chapter_number: chapterNumber,
        content: content
      })
    })
  }
}


// 优化相关类型定义
export interface EmotionBeat {
  primary_emotion: string
  intensity: number
  curve: {
    start: number
    peak: number
    end: number
  }
  turning_point: string
}

export interface OptimizeRequest {
  project_id: string
  chapter_number: number
  dimension: 'dialogue' | 'environment' | 'psychology' | 'rhythm'
  additional_notes?: string
}

export interface OptimizeResponse {
  optimized_content: string
  optimization_notes: string
  dimension: string
}

// 优化API
const OPTIMIZER_BASE = `${API_BASE_URL}${API_PREFIX}/optimizer`

export class OptimizerAPI {
  /**
   * 对章节内容进行分层优化
   */
  static async optimizeChapter(optimizeReq: OptimizeRequest): Promise<OptimizeResponse> {
    return request(`${OPTIMIZER_BASE}/optimize`, {
      method: 'POST',
      body: JSON.stringify(optimizeReq)
    })
  }

  /**
   * 应用优化后的内容到章节
   */
  static async applyOptimization(
    projectId: string,
    chapterNumber: number,
    optimizedContent: string
  ): Promise<{ status: string; message: string }> {
    const params = new URLSearchParams({
      project_id: projectId,
      chapter_number: chapterNumber.toString(),
      optimized_content: optimizedContent
    })
    return request(`${OPTIMIZER_BASE}/apply-optimization?${params}`, {
      method: 'POST'
    })
  }
}
