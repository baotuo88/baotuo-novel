// AIMETA P=小说状态_当前小说数据管理|R=currentNovel_chapters_fetch|NR=不含API调用|E=store:novel|X=internal|A=useNovelStore|D=pinia|S=none|RD=./README.ai
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  Chapter,
  NovelProject,
  NovelProjectSummary,
  ConverseResponse,
  BlueprintGenerationResponse,
  Blueprint,
  DeleteNovelsResponse,
  ChapterOutline
} from '@/api/novel'
import { NovelAPI } from '@/api/novel'

export const useNovelStore = defineStore('novel', () => {
  // State
  const projects = ref<NovelProjectSummary[]>([])
  const currentProject = ref<NovelProject | null>(null)
  const currentConversationState = ref<any>({})
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const pendingChapterEdits = new Map<string, string>()

  const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

  // Getters
  const projectsCount = computed(() => projects.value.length)
  const hasCurrentProject = computed(() => currentProject.value !== null)

  // Actions
  async function loadProjects() {
    isLoading.value = true
    error.value = null
    try {
      projects.value = await NovelAPI.getAllNovels()
    } catch (err) {
      error.value = err instanceof Error ? err.message : '加载项目失败'
    } finally {
      isLoading.value = false
    }
  }

  async function createProject(title: string, initialPrompt: string) {
    isLoading.value = true
    error.value = null
    try {
      const project = await NovelAPI.createNovel(title, initialPrompt)
      currentProject.value = project
      currentConversationState.value = {}
      return project
    } catch (err) {
      error.value = err instanceof Error ? err.message : '创建项目失败'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function loadProject(projectId: string, silent: boolean = false) {
    if (!silent) {
      isLoading.value = true
    }
    error.value = null
    try {
      currentProject.value = await NovelAPI.getNovel(projectId)
    } catch (err) {
      error.value = err instanceof Error ? err.message : '加载项目失败'
    } finally {
      if (!silent) {
        isLoading.value = false
      }
    }
  }

  async function loadChapter(chapterNumber: number) {
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error('没有当前项目')
      }
      const chapter = await NovelAPI.getChapter(currentProject.value.id, chapterNumber)
      const project = currentProject.value
      if (!Array.isArray(project.chapters)) {
        project.chapters = []
      }
      const index = project.chapters.findIndex(ch => ch.chapter_number === chapterNumber)
      if (index >= 0) {
        project.chapters.splice(index, 1, chapter)
      } else {
        project.chapters.push(chapter)
      }
      project.chapters.sort((a, b) => a.chapter_number - b.chapter_number)
      return chapter
    } catch (err) {
      error.value = err instanceof Error ? err.message : '加载章节失败'
      throw err
    }
  }

  const mergeChapterMeta = (oldChapter: Chapter | undefined, incoming: Chapter): Chapter => {
    if (!oldChapter) {
      return incoming
    }
    return {
      ...oldChapter,
      ...incoming,
      // section=chapters 时后端会返回 null，不能把已加载内容覆盖掉
      content: incoming.content ?? oldChapter.content,
      versions: incoming.versions ?? oldChapter.versions,
      evaluation: incoming.evaluation ?? oldChapter.evaluation,
      word_count: incoming.word_count ?? oldChapter.word_count
    }
  }

  async function refreshChapterStatuses(projectId: string) {
    error.value = null
    try {
      if (!currentProject.value || currentProject.value.id !== projectId) {
        return
      }
      const section = await NovelAPI.getSection(projectId, 'chapters')
      const incomingList = Array.isArray(section.data?.chapters)
        ? (section.data.chapters as Chapter[])
        : []

      const oldMap = new Map(
        (currentProject.value.chapters || []).map((chapter) => [chapter.chapter_number, chapter])
      )

      const merged: Chapter[] = incomingList.map((incoming) =>
        mergeChapterMeta(oldMap.get(incoming.chapter_number), incoming)
      )
      const mergedNumbers = new Set(merged.map((item) => item.chapter_number))

      for (const oldChapter of currentProject.value.chapters || []) {
        if (!mergedNumbers.has(oldChapter.chapter_number)) {
          merged.push(oldChapter)
        }
      }

      merged.sort((a, b) => a.chapter_number - b.chapter_number)
      currentProject.value.chapters = merged
    } catch (err) {
      error.value = err instanceof Error ? err.message : '刷新章节状态失败'
      throw err
    }
  }

  async function sendConversation(userInput: any): Promise<ConverseResponse> {
    isLoading.value = true
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error('没有当前项目')
      }
      const response = await NovelAPI.converseConcept(
        currentProject.value.id,
        userInput,
        currentConversationState.value
      )
      currentConversationState.value = response.conversation_state
      return response
    } catch (err) {
      error.value = err instanceof Error ? err.message : '对话失败'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function generateBlueprint(): Promise<BlueprintGenerationResponse> {
    // Generate blueprint from conversation history
    isLoading.value = true
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error('没有当前项目')
      }
      const projectId = currentProject.value.id

      // 优先走异步任务，避免网关/代理层长请求超时（504）
      try {
        const accepted = await NovelAPI.startGenerateBlueprint(projectId)
        const pollIntervalSeconds = Math.max(2, accepted.poll_interval_seconds || 5)
        const maxWaitMs = 10 * 60 * 1000 // 最长等待 10 分钟
        const deadline = Date.now() + maxWaitMs

        while (Date.now() < deadline) {
          await sleep(pollIntervalSeconds * 1000)
          const status = await NovelAPI.getBlueprintGenerationStatus(projectId)

          if (status.status === 'generating' || status.status === 'not_started') {
            continue
          }

          if (status.status === 'completed' && status.blueprint) {
            return {
              blueprint: status.blueprint,
              ai_message: status.ai_message || '蓝图生成完成。'
            }
          }

          if (status.status === 'failed') {
            throw new Error(status.error_message || '蓝图生成失败，请稍后重试')
          }
        }

        throw new Error('蓝图生成超时，请稍后再试')
      } catch (asyncErr) {
        // 兼容旧后端（未部署新接口）时回退到同步接口
        const msg = asyncErr instanceof Error ? asyncErr.message : String(asyncErr)
        if (msg.includes('状态码: 404') || msg.includes('404') || msg.includes('Not Found')) {
          return await NovelAPI.generateBlueprint(projectId)
        }
        throw asyncErr
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : '生成蓝图失败'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function saveBlueprint(blueprint: Blueprint) {
    isLoading.value = true
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error('没有当前项目')
      }
      if (!blueprint) {
        throw new Error('缺少蓝图数据')
      }
      currentProject.value = await NovelAPI.saveBlueprint(currentProject.value.id, blueprint)
    } catch (err) {
      error.value = err instanceof Error ? err.message : '保存蓝图失败'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function generateChapter(chapterNumber: number): Promise<NovelProject> {
    // 注意：这里不设置全局 isLoading，因为 WritingDesk.vue 有自己的局部加载状态
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error('没有当前项目')
      }
      const updatedProject = await NovelAPI.generateChapter(currentProject.value.id, chapterNumber)
      currentProject.value = updatedProject // 更新 store 中的当前项目
      return updatedProject
    } catch (err) {
      error.value = err instanceof Error ? err.message : '生成章节失败'
      throw err
    }
  }

  async function evaluateChapter(chapterNumber: number): Promise<NovelProject> {
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error('没有当前项目')
      }
      const updatedProject = await NovelAPI.evaluateChapter(currentProject.value.id, chapterNumber)
      currentProject.value = updatedProject
      return updatedProject
    } catch (err) {
      error.value = err instanceof Error ? err.message : '评估章节失败'
      throw err
    }
  }

  async function selectChapterVersion(chapterNumber: number, versionIndex: number) {
    // 不设置全局 isLoading，让调用方处理局部加载状态
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error('没有当前项目')
      }
      const updatedProject = await NovelAPI.selectChapterVersion(
        currentProject.value.id,
        chapterNumber,
        versionIndex
      )
      await NovelAPI.invalidateAnalysisCache(currentProject.value.id).catch(() => undefined)
      currentProject.value = updatedProject // 更新 store
    } catch (err) {
      error.value = err instanceof Error ? err.message : '选择章节版本失败'
      throw err
    }
  }

  async function deleteProjects(projectIds: string[]): Promise<DeleteNovelsResponse> {
    isLoading.value = true
    error.value = null
    try {
      const response = await NovelAPI.deleteNovels(projectIds)
      
      // 从本地项目列表中移除已删除的项目
      projects.value = projects.value.filter(project => !projectIds.includes(project.id))
      
      // 如果当前项目被删除，清空当前项目
      if (currentProject.value && projectIds.includes(currentProject.value.id)) {
        currentProject.value = null
        currentConversationState.value = {}
      }
      
      return response
    } catch (err) {
      error.value = err instanceof Error ? err.message : '删除项目失败'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function updateChapterOutline(chapterOutline: ChapterOutline) {
    // 不设置全局 isLoading，让调用方处理局部加载状态
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error('没有当前项目')
      }
      const updatedProject = await NovelAPI.updateChapterOutline(
        currentProject.value.id,
        chapterOutline
      )
      currentProject.value = updatedProject // 更新 store
    } catch (err) {
      error.value = err instanceof Error ? err.message : '更新章节大纲失败'
      throw err
    }
  }

  async function deleteChapter(chapterNumbers: number | number[]) {
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error('没有当前项目')
      }
      const numbersToDelete = Array.isArray(chapterNumbers) ? chapterNumbers : [chapterNumbers]
      const updatedProject = await NovelAPI.deleteChapter(
        currentProject.value.id,
        numbersToDelete
      )
      currentProject.value = updatedProject // 更新 store
    } catch (err) {
      error.value = err instanceof Error ? err.message : '删除章节失败'
      throw err
    }
  }

  async function generateChapterOutline(startChapter: number, numChapters: number) {
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error('没有当前项目')
      }
      const updatedProject = await NovelAPI.generateChapterOutline(
        currentProject.value.id,
        startChapter,
        numChapters
      )
      currentProject.value = updatedProject // 更新 store
    } catch (err) {
      error.value = err instanceof Error ? err.message : '生成大纲失败'
      throw err
    }
  }

  async function editChapterContent(projectId: string, chapterNumber: number, content: string) {
    error.value = null
    const requestKey = `${projectId}:${chapterNumber}`
    pendingChapterEdits.set(requestKey, content)
    const project = currentProject.value
    let previousContent: string | null = null
    let previousWordCount: number | undefined
    let versionIndex = -1
    if (project) {
      const chapter = project.chapters.find(ch => ch.chapter_number === chapterNumber)
      if (chapter) {
        previousContent = chapter.content ?? null
        previousWordCount = chapter.word_count
        chapter.content = content
        chapter.generation_status = 'successful'
        chapter.word_count = content.length
        if (Array.isArray(chapter.versions) && previousContent !== null) {
          versionIndex = chapter.versions.findIndex(v => v === previousContent)
          if (versionIndex >= 0) {
            chapter.versions.splice(versionIndex, 1, content)
          }
        }
      }
    }
    try {
      const updatedChapter = await NovelAPI.editChapterContent(projectId, chapterNumber, content)
      await NovelAPI.invalidateAnalysisCache(projectId).catch(() => undefined)
      if (pendingChapterEdits.get(requestKey) !== content) {
        return
      }
      if (project) {
        const chapters = project.chapters
        const index = chapters.findIndex(ch => ch.chapter_number === chapterNumber)
        if (index >= 0) {
          chapters.splice(index, 1, updatedChapter)
        } else {
          chapters.push(updatedChapter)
          chapters.sort((a, b) => a.chapter_number - b.chapter_number)
        }
      }
      pendingChapterEdits.delete(requestKey)
    } catch (err) {
      if (pendingChapterEdits.get(requestKey) === content) {
        pendingChapterEdits.delete(requestKey)
        if (project) {
          const chapter = project.chapters.find(ch => ch.chapter_number === chapterNumber)
          if (chapter) {
            chapter.content = previousContent
            chapter.word_count = previousWordCount
            if (Array.isArray(chapter.versions) && versionIndex >= 0 && previousContent !== null) {
              chapter.versions.splice(versionIndex, 1, previousContent)
            }
          }
        }
      }
      error.value = err instanceof Error ? err.message : '编辑章节内容失败'
      throw err
    }
  }

  function clearError() {
    error.value = null
  }

  function setCurrentProject(project: NovelProject | null) {
    currentProject.value = project
  }

  return {
    // State
    projects,
    currentProject,
    currentConversationState,
    isLoading,
    error,
    // Getters
    projectsCount,
    hasCurrentProject,
    // Actions
    loadProjects,
    createProject,
    loadProject,
    loadChapter,
    refreshChapterStatuses,
    sendConversation,
    generateBlueprint,
    saveBlueprint,
    generateChapter,
    evaluateChapter,
    selectChapterVersion,
    deleteProjects,
    updateChapterOutline,
    deleteChapter,
    generateChapterOutline,
    editChapterContent,
    clearError,
    setCurrentProject
  }
})
