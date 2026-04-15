// AIMETA P=小说API客户端_小说和章节接口|R=小说CRUD_章节管理_生成|NR=不含UI逻辑|E=api:novel|X=internal|A=novelApi对象|D=axios|S=net|RD=./README.ai
import { useAuthStore } from '@/stores/auth'
import router from '@/router'

// API 配置
// 在生产环境中使用相对路径，在开发环境中使用绝对路径
export const API_BASE_URL = import.meta.env.MODE === 'production' ? '' : 'http://127.0.0.1:8000'
export const API_PREFIX = '/api'

// 统一的请求处理函数
const request = async (url: string, options: RequestInit = {}) => {
  const authStore = useAuthStore()
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

  const response = await fetch(url, { ...options, headers })

  if (response.status === 401) {
    // Token 失效或未授权
    authStore.logout()
    router.push('/login')
    throw new Error('会话已过期，请重新登录')
  }

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `请求失败，状态码: ${response.status}`)
  }

  return response.json()
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
export type AnalysisSectionType = 'emotion_curve' | 'foreshadowing' | 'world_graph'

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

export interface ChapterConsistencyReview {
  is_consistent: boolean
  summary: string
  check_time_ms: number
  violations: ConsistencyViolationItem[]
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

// API 函数
const NOVELS_BASE = `${API_BASE_URL}${API_PREFIX}/novels`
const WRITER_PREFIX = '/api/writer'
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

  static async listWriterPresets(): Promise<WritingPresetItem[]> {
    return request(`${API_BASE_URL}${WRITER_PREFIX}/presets`)
  }

  static async setActiveWriterPreset(presetId: string | null): Promise<WritingPresetItem | null> {
    return request(`${API_BASE_URL}${WRITER_PREFIX}/presets/active`, {
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
  ): Promise<{ project_id: string; chapter_number: number; review: ChapterConsistencyReview }> {
    return request(`${WRITER_BASE}/${projectId}/chapters/${chapterNumber}/consistency-check`, {
      method: 'POST'
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
