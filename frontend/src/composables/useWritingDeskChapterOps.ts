import { computed, ref, type ComputedRef, type Ref } from 'vue'

import { globalAlert } from '@/composables/useAlert'
import type { Chapter, ChapterGenerationResponse, ChapterOutline, ChapterVersion, NovelProject } from '@/api/novel'

interface UseWritingDeskChapterOpsOptions {
  projectId: string
  project: ComputedRef<NovelProject | null>
  selectedChapter: ComputedRef<Chapter | null>
  selectedChapterNumber: Ref<number | null>
  chapterFailureMessageMap: Map<number, string>
  closeSidebar: () => void
  syncGenerationIndicators: () => void
  generateChapter: (chapterNumber: number) => Promise<NovelProject>
  evaluateChapter: (chapterNumber: number) => Promise<NovelProject>
  selectChapterVersion: (chapterNumber: number, versionIndex: number) => Promise<void>
  updateChapterOutline: (chapterOutline: ChapterOutline) => Promise<void>
  deleteChapter: (chapterNumbers: number | number[]) => Promise<void>
  generateChapterOutline: (startChapter: number, numChapters: number) => Promise<void>
  editChapterContent: (projectId: string, chapterNumber: number, content: string) => Promise<void>
  loadChapter: (chapterNumber: number) => Promise<unknown>
  loadProject: (projectId: string, silent?: boolean) => Promise<void>
}

const cleanVersionContent = (content: string): string => {
  if (!content) return ''

  try {
    const parsed = JSON.parse(content)
    const extractContent = (value: unknown): string | null => {
      if (!value) return null
      if (typeof value === 'string') return value
      if (Array.isArray(value)) {
        for (const item of value) {
          const nested = extractContent(item)
          if (nested) return nested
        }
        return null
      }
      if (typeof value === 'object') {
        const record = value as Record<string, unknown>
        for (const key of ['content', 'chapter_content', 'chapter_text', 'text', 'body', 'story']) {
          if (record[key]) {
            const nested = extractContent(record[key])
            if (nested) return nested
          }
        }
      }
      return null
    }
    const extracted = extractContent(parsed)
    if (extracted) {
      content = extracted
    }
  } catch {
    // Ignore non-JSON content and continue processing as plain text.
  }

  let cleaned = content.replace(/^"|"$/g, '')
  cleaned = cleaned.replace(/\\n/g, '\n')
  cleaned = cleaned.replace(/\\"/g, '"')
  cleaned = cleaned.replace(/\\t/g, '\t')
  cleaned = cleaned.replace(/\\\\/g, '\\')

  return cleaned
}

export const useWritingDeskChapterOps = (options: UseWritingDeskChapterOpsOptions) => {
  const chapterGenerationResult = ref<ChapterGenerationResponse | null>(null)
  const selectedVersionIndex = ref(0)
  const showVersionDetailModal = ref(false)
  const detailVersionIndex = ref(0)
  const showEditChapterModal = ref(false)
  const editingChapter = ref<ChapterOutline | null>(null)
  const isGeneratingOutline = ref(false)
  const showGenerateOutlineModal = ref(false)

  const showVersionSelector = computed(() => {
    if (!options.selectedChapter.value) return false
    const status = options.selectedChapter.value.generation_status
    return (
      status === 'waiting_for_confirm' ||
      status === 'evaluating' ||
      status === 'evaluation_failed' ||
      status === 'selecting'
    )
  })

  const availableVersions = computed<ChapterVersion[]>(() => {
    if (chapterGenerationResult.value?.versions) {
      return chapterGenerationResult.value.versions
    }

    if (options.selectedChapter.value?.versions && Array.isArray(options.selectedChapter.value.versions)) {
      return options.selectedChapter.value.versions.map((versionString) => {
        try {
          const versionObj = JSON.parse(versionString) as { content?: string }
          return {
            content: versionObj.content || versionString,
            style: '标准',
          }
        } catch {
          return {
            content: versionString,
            style: '标准',
          }
        }
      })
    }

    return []
  })

  const isCurrentVersion = (versionIndex: number) => {
    if (!options.selectedChapter.value?.content || !availableVersions.value[versionIndex]?.content) {
      return false
    }

    const cleanCurrentContent = cleanVersionContent(options.selectedChapter.value.content)
    const cleanVersionContentText = cleanVersionContent(availableVersions.value[versionIndex].content)
    return cleanCurrentContent === cleanVersionContentText
  }

  const canGenerateChapter = (chapterNumber: number) => {
    if (!options.project.value?.blueprint?.chapter_outline) return false

    const outlines = [...options.project.value.blueprint.chapter_outline].sort(
      (a, b) => a.chapter_number - b.chapter_number,
    )

    for (const outline of outlines) {
      if (outline.chapter_number >= chapterNumber) break

      const chapter = options.project.value?.chapters.find((item) => item.chapter_number === outline.chapter_number)
      if (!chapter || chapter.generation_status !== 'successful') {
        return false
      }
    }

    const currentChapter = options.project.value?.chapters.find((item) => item.chapter_number === chapterNumber)
    if (currentChapter && currentChapter.generation_status === 'successful') {
      return true
    }

    return true
  }

  const isChapterFailed = (chapterNumber: number) => {
    if (!options.project.value?.chapters) return false
    const chapter = options.project.value.chapters.find((item) => item.chapter_number === chapterNumber)
    return chapter?.generation_status === 'failed'
  }

  const hasChapterInProgress = (chapterNumber: number) => {
    if (!options.project.value?.chapters) return false
    const chapter = options.project.value.chapters.find((item) => item.chapter_number === chapterNumber)
    return chapter?.generation_status === 'waiting_for_confirm'
  }

  const showVersionDetail = (versionIndex: number) => {
    detailVersionIndex.value = versionIndex
    showVersionDetailModal.value = true
  }

  const closeVersionDetail = () => {
    showVersionDetailModal.value = false
  }

  const hideVersionSelector = () => {
    chapterGenerationResult.value = null
    selectedVersionIndex.value = 0
  }

  const selectChapter = (chapterNumber: number) => {
    options.selectedChapterNumber.value = chapterNumber
    chapterGenerationResult.value = null
    selectedVersionIndex.value = 0
    options.closeSidebar()
  }

  const generateChapter = async (chapterNumber: number) => {
    if (!canGenerateChapter(chapterNumber) && !isChapterFailed(chapterNumber) && !hasChapterInProgress(chapterNumber)) {
      globalAlert.showError('请按顺序生成章节，先完成前面的章节', '生成受限')
      return
    }

    try {
      options.selectedChapterNumber.value = chapterNumber
      options.chapterFailureMessageMap.delete(chapterNumber)

      if (options.project.value?.chapters) {
        const chapter = options.project.value.chapters.find((item) => item.chapter_number === chapterNumber)
        if (chapter) {
          chapter.generation_status = 'generating'
        } else {
          const outline = options.project.value.blueprint?.chapter_outline?.find(
            (item) => item.chapter_number === chapterNumber,
          )
          options.project.value.chapters.push({
            chapter_number: chapterNumber,
            title: outline?.title || '加载中...',
            summary: outline?.summary || '',
            content: '',
            versions: [],
            evaluation: null,
            generation_status: 'generating',
          } as Chapter)
        }
      }

      options.syncGenerationIndicators()
      await options.generateChapter(chapterNumber)
      options.syncGenerationIndicators()
      chapterGenerationResult.value = null
      selectedVersionIndex.value = 0
    } catch (error) {
      console.error('生成章节失败:', error)

      if (options.project.value?.chapters) {
        const chapter = options.project.value.chapters.find((item) => item.chapter_number === chapterNumber)
        if (chapter) {
          chapter.generation_status = 'failed'
        }
      }

      globalAlert.showError(
        `生成章节失败: ${error instanceof Error ? error.message : '未知错误'}`,
        '生成失败',
      )
    } finally {
      options.syncGenerationIndicators()
    }
  }

  const regenerateChapter = async () => {
    if (options.selectedChapterNumber.value !== null) {
      await generateChapter(options.selectedChapterNumber.value)
    }
  }

  const selectVersion = async (versionIndex: number) => {
    if (options.selectedChapterNumber.value === null || !availableVersions.value[versionIndex]?.content) {
      return
    }

    try {
      if (options.project.value?.chapters) {
        const chapter = options.project.value.chapters.find(
          (item) => item.chapter_number === options.selectedChapterNumber.value,
        )
        if (chapter) {
          chapter.generation_status = 'selecting'
        }
      }

      selectedVersionIndex.value = versionIndex
      await options.selectChapterVersion(options.selectedChapterNumber.value, versionIndex)
      chapterGenerationResult.value = null
      globalAlert.showSuccess('版本已确认', '操作成功')
    } catch (error) {
      console.error('选择章节版本失败:', error)
      if (options.project.value?.chapters) {
        const chapter = options.project.value.chapters.find(
          (item) => item.chapter_number === options.selectedChapterNumber.value,
        )
        if (chapter) {
          chapter.generation_status = 'waiting_for_confirm'
        }
      }
      globalAlert.showError(
        `选择章节版本失败: ${error instanceof Error ? error.message : '未知错误'}`,
        '选择失败',
      )
    }
  }

  const selectVersionFromDetail = async () => {
    selectedVersionIndex.value = detailVersionIndex.value
    await selectVersion(detailVersionIndex.value)
    closeVersionDetail()
  }

  const confirmVersionSelection = async () => {
    await selectVersion(selectedVersionIndex.value)
  }

  const openEditChapterModal = (chapter: ChapterOutline) => {
    editingChapter.value = chapter
    showEditChapterModal.value = true
  }

  const saveChapterChanges = async (updatedChapter: ChapterOutline) => {
    try {
      await options.updateChapterOutline(updatedChapter)
      globalAlert.showSuccess('章节大纲已更新', '保存成功')
    } catch (error) {
      console.error('更新章节大纲失败:', error)
      globalAlert.showError(
        `更新章节大纲失败: ${error instanceof Error ? error.message : '未知错误'}`,
        '保存失败',
      )
    } finally {
      showEditChapterModal.value = false
    }
  }

  const evaluateChapter = async () => {
    if (options.selectedChapterNumber.value === null) {
      return
    }

    let previousStatus: Chapter['generation_status'] | undefined
    try {
      if (options.project.value?.chapters) {
        const chapter = options.project.value.chapters.find(
          (item) => item.chapter_number === options.selectedChapterNumber.value,
        )
        if (chapter) {
          previousStatus = chapter.generation_status
          chapter.generation_status = 'evaluating'
        }
      }
      await options.evaluateChapter(options.selectedChapterNumber.value)
      globalAlert.showSuccess('章节评审结果已生成', '评审成功')
    } catch (error) {
      console.error('评审章节失败:', error)
      if (options.project.value?.chapters) {
        const chapter = options.project.value.chapters.find(
          (item) => item.chapter_number === options.selectedChapterNumber.value,
        )
        if (chapter && previousStatus) {
          chapter.generation_status = previousStatus
        }
      }
      globalAlert.showError(
        `评审章节失败: ${error instanceof Error ? error.message : '未知错误'}`,
        '评审失败',
      )
    }
  }

  const deleteChapter = async (chapterNumbers: number | number[]) => {
    const numbersToDelete = Array.isArray(chapterNumbers) ? chapterNumbers : [chapterNumbers]
    const confirmationMessage =
      numbersToDelete.length > 1
        ? `您确定要删除选中的 ${numbersToDelete.length} 个章节吗？这个操作无法撤销。`
        : `您确定要删除第 ${numbersToDelete[0]} 章吗？这个操作无法撤销。`

    if (!window.confirm(confirmationMessage)) {
      return
    }

    try {
      await options.deleteChapter(numbersToDelete)
      globalAlert.showSuccess('章节已删除', '操作成功')
      if (
        options.selectedChapterNumber.value !== null &&
        numbersToDelete.includes(options.selectedChapterNumber.value)
      ) {
        options.selectedChapterNumber.value = null
      }
    } catch (error) {
      console.error('删除章节失败:', error)
      globalAlert.showError(
        `删除章节失败: ${error instanceof Error ? error.message : '未知错误'}`,
        '删除失败',
      )
    }
  }

  const generateOutline = async () => {
    showGenerateOutlineModal.value = true
  }

  const editChapterContent = async (data: { chapterNumber: number; content: string }) => {
    if (!options.project.value) return

    try {
      await options.editChapterContent(options.project.value.id, data.chapterNumber, data.content)
      globalAlert.showSuccess('章节内容已更新', '保存成功')
    } catch (error) {
      console.error('编辑章节内容失败:', error)
      globalAlert.showError(
        `编辑章节内容失败: ${error instanceof Error ? error.message : '未知错误'}`,
        '保存失败',
      )
    }
  }

  const handleGenerateOutline = async (numChapters: number) => {
    if (!options.project.value) return
    isGeneratingOutline.value = true
    try {
      const startChapter = (options.project.value.blueprint?.chapter_outline?.length || 0) + 1
      await options.generateChapterOutline(startChapter, numChapters)
      globalAlert.showSuccess('新的章节大纲已生成', '操作成功')
    } catch (error) {
      console.error('生成大纲失败:', error)
      globalAlert.showError(
        `生成大纲失败: ${error instanceof Error ? error.message : '未知错误'}`,
        '生成失败',
      )
    } finally {
      isGeneratingOutline.value = false
    }
  }

  const handleVersionRolledBack = async (chapterNumber: number) => {
    try {
      await options.loadChapter(chapterNumber)
      await options.loadProject(options.projectId, true)
      globalAlert.showSuccess(`第${chapterNumber}章已完成版本回滚`, '操作成功')
    } catch (error) {
      globalAlert.showError(`回滚后刷新失败: ${error instanceof Error ? error.message : '未知错误'}`)
    }
  }

  const handleChapterUpdated = async (chapterNumber: number) => {
    try {
      await options.loadChapter(chapterNumber)
      await options.loadProject(options.projectId, true)
      options.syncGenerationIndicators()
    } catch (error) {
      console.error('章节更新后刷新失败:', error)
    }
  }

  return {
    availableVersions,
    chapterGenerationResult,
    closeVersionDetail,
    confirmVersionSelection,
    deleteChapter,
    detailVersionIndex,
    editChapterContent,
    editingChapter,
    evaluateChapter,
    generateChapter,
    generateOutline,
    handleChapterUpdated,
    handleGenerateOutline,
    handleVersionRolledBack,
    hideVersionSelector,
    isChapterFailed,
    isCurrentVersion,
    isGeneratingOutline,
    openEditChapterModal,
    regenerateChapter,
    saveChapterChanges,
    selectChapter,
    selectedVersionIndex,
    selectVersionFromDetail,
    showEditChapterModal,
    showGenerateOutlineModal,
    showVersionDetail,
    showVersionDetailModal,
    showVersionSelector,
  }
}
