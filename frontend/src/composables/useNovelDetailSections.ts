import { computed, reactive, ref, watch, type ComputedRef } from 'vue'
import type { RouteLocationNormalizedLoaded, Router } from 'vue-router'

import { AdminAPI } from '@/api/admin'
import { NovelAPI } from '@/api/novel'
import type { NovelSectionResponse, NovelSectionType } from '@/api/novel'
import {
  ANALYSIS_SECTIONS,
  ALL_SECTION_KEYS,
  FILL_SECTIONS,
  buildSections,
  getSectionIcon,
  sectionComponents,
  type SectionKey,
} from '@/components/novel-detail/sectionRegistry'

interface UseNovelDetailSectionsOptions {
  isAdmin: boolean
  projectId: string
  route: RouteLocationNormalizedLoaded
  router: Router
}

const createSectionRecord = <T>(initialValue: T): Record<SectionKey, T> => {
  return ALL_SECTION_KEYS.reduce(
    (acc, key) => {
      acc[key] = initialValue
      return acc
    },
    {} as Record<SectionKey, T>,
  )
}

export const useNovelDetailSections = (options: UseNovelDetailSectionsOptions) => {
  const sections = buildSections(options.isAdmin)
  const sectionData = reactive<Partial<Record<SectionKey, any>>>({})
  const sectionLoading = reactive(createSectionRecord(false))
  const sectionError = reactive(createSectionRecord<string | null>(null))

  const overviewMeta = reactive<{ title: string; updated_at: string | null }>({
    title: '加载中...',
    updated_at: null,
  })

  const activeSection = ref<SectionKey>('overview')
  const focusChapterNumber = ref<number | null>(null)
  const focusTimelineEventId = ref<number | null>(null)
  const focusForeshadowingId = ref<number | null>(null)
  const focusMaterialId = ref<string | null>(null)
  const focusTerm = ref<string | null>(null)
  const focusSearchQuery = ref<string | null>(null)

  const isSectionKey = (value: string): value is SectionKey => {
    return sections.some((section) => section.key === value)
  }

  const parseSectionFromQuery = (): SectionKey | null => {
    const raw = options.route.query.section
    if (typeof raw !== 'string') return null
    return isSectionKey(raw) ? raw : null
  }

  const parseIntQuery = (key: string): number | null => {
    const raw = options.route.query[key]
    if (typeof raw !== 'string') return null
    const value = Number(raw)
    if (!Number.isInteger(value) || value < 1) return null
    return value
  }

  const parseStringQuery = (key: string): string | null => {
    const raw = options.route.query[key]
    if (typeof raw !== 'string') return null
    const value = raw.trim()
    return value || null
  }

  const syncFocusStateFromRoute = () => {
    focusChapterNumber.value = parseIntQuery('chapter')
    focusTimelineEventId.value = parseIntQuery('timeline_event_id')
    focusForeshadowingId.value = parseIntQuery('foreshadowing_id')
    focusMaterialId.value = parseStringQuery('material_id')
    focusTerm.value = parseStringQuery('term')
    focusSearchQuery.value = parseStringQuery('search_q')
  }

  const loadSection = async (section: SectionKey, force = false) => {
    if (!options.projectId) return

    if (section === 'comprehensive_diagnosis') {
      if (!force && sectionData[section]) return
      sectionLoading[section] = true
      sectionError[section] = null
      try {
        sectionData[section] = await NovelAPI.getComprehensiveAnalysis(options.projectId)
      } catch (error) {
        console.error('加载综合诊断失败:', error)
        sectionError[section] = error instanceof Error ? error.message : '加载失败'
      } finally {
        sectionLoading[section] = false
      }
      return
    }

    if (section === 'world_graph') {
      if (!force && sectionData[section]) return
      sectionLoading[section] = true
      sectionError[section] = null
      try {
        sectionData[section] = await NovelAPI.getWorldGraph(options.projectId)
      } catch (error) {
        console.error('加载世界图谱失败:', error)
        sectionError[section] = error instanceof Error ? error.message : '加载失败'
      } finally {
        sectionLoading[section] = false
      }
      return
    }

    if (section === 'quality_dashboard') {
      if (!force && sectionData[section]) return
      sectionLoading[section] = true
      sectionError[section] = null
      try {
        sectionData[section] = await NovelAPI.getProjectQualityDashboard(options.projectId)
      } catch (error) {
        console.error('加载质量看板失败:', error)
        sectionError[section] = error instanceof Error ? error.message : '加载失败'
      } finally {
        sectionLoading[section] = false
      }
      return
    }

    if (section === 'publish_center') {
      if (!force && sectionData[section]) return
      sectionLoading[section] = true
      sectionError[section] = null
      try {
        sectionData[section] = await NovelAPI.getPublishSummary(options.projectId)
      } catch (error) {
        console.error('加载发布中心失败:', error)
        sectionError[section] = error instanceof Error ? error.message : '加载失败'
      } finally {
        sectionLoading[section] = false
      }
      return
    }

    if (ANALYSIS_SECTIONS.includes(section)) {
      return
    }

    if (!force && sectionData[section]) {
      return
    }

    sectionLoading[section] = true
    sectionError[section] = null
    try {
      const response: NovelSectionResponse = options.isAdmin
        ? await AdminAPI.getNovelSection(options.projectId, section as NovelSectionType)
        : await NovelAPI.getSection(options.projectId, section as NovelSectionType)
      sectionData[section] = response.data
      if (section === 'overview') {
        overviewMeta.title = response.data?.title || overviewMeta.title
        overviewMeta.updated_at = response.data?.updated_at || null
      }
    } catch (error) {
      console.error('加载模块失败:', error)
      sectionError[section] = error instanceof Error ? error.message : '加载失败'
    } finally {
      sectionLoading[section] = false
    }
  }

  const reloadSection = (section: SectionKey, force = false) => {
    void loadSection(section, force)
  }

  const switchSection = (section: SectionKey, closeSidebar?: () => void) => {
    activeSection.value = section
    if (closeSidebar && typeof window !== 'undefined' && window.innerWidth < 1024) {
      closeSidebar()
    }
    void loadSection(section)
  }

  const currentComponent = computed(() => sectionComponents[activeSection.value])
  const isSectionLoading = computed(() => sectionLoading[activeSection.value])
  const currentError = computed(() => sectionError[activeSection.value])

  const componentContainerClass = computed(() => {
    return FILL_SECTIONS.includes(activeSection.value)
      ? 'flex-1 min-h-0 h-full flex flex-col overflow-hidden'
      : 'overflow-y-auto'
  })

  const contentCardClass = computed(() => {
    return FILL_SECTIONS.includes(activeSection.value) ? 'overflow-hidden' : 'overflow-visible'
  })

  const componentProps = computed(() => {
    const data = sectionData[activeSection.value]
    const editable = !options.isAdmin

    switch (activeSection.value) {
      case 'overview':
        return { data: data || null, editable }
      case 'comprehensive_diagnosis':
        return {
          data: data || null,
          projectId: options.projectId,
        }
      case 'world_setting':
        return { data: data || null, editable }
      case 'characters':
        return { data: data || null, editable }
      case 'relationships':
        return { data: data || null, editable }
      case 'world_graph':
        return { data: data || null, editable, projectId: options.projectId }
      case 'quality_dashboard':
        return { data: data || null }
      case 'publish_center':
        return { data: data || null, projectId: options.projectId }
      case 'material_library':
        return {
          projectId: options.projectId,
          editable,
          focusMaterialId: activeSection.value === 'material_library' ? focusMaterialId.value : null,
          focusQuery: activeSection.value === 'material_library' ? focusSearchQuery.value : null,
        }
      case 'global_search':
        return {
          projectId: options.projectId,
          initialQuery: activeSection.value === 'global_search' ? focusSearchQuery.value : null,
        }
      case 'project_backup':
        return { projectId: options.projectId }
      case 'timeline':
        return {
          editable,
          projectId: options.projectId,
          focusChapterNumber: activeSection.value === 'timeline' ? focusChapterNumber.value : null,
          focusEventId: activeSection.value === 'timeline' ? focusTimelineEventId.value : null,
        }
      case 'terminology':
        return {
          editable,
          projectId: options.projectId,
          focusTerm: activeSection.value === 'terminology' ? focusTerm.value : null,
          focusQuery: activeSection.value === 'terminology' ? focusSearchQuery.value : null,
        }
      case 'foreshadowing':
        return {
          editable,
          projectId: options.projectId,
          focusChapterNumber: activeSection.value === 'foreshadowing' ? focusChapterNumber.value : null,
          focusForeshadowingId: activeSection.value === 'foreshadowing' ? focusForeshadowingId.value : null,
        }
      case 'chapter_outline':
        return { outline: data?.chapter_outline || [], editable }
      case 'chapters':
        return {
          chapters: data?.chapters || [],
          isAdmin: options.isAdmin,
          focusChapterNumber: activeSection.value === 'chapters' ? focusChapterNumber.value : null,
        }
      default:
        return {}
    }
  })

  const handleWorldGraphRefresh = async () => {
    await loadSection('world_graph', true)
    await loadSection('relationships', true)
    await loadSection('world_setting', true)
  }

  const handleGraphNavigate = async (payload: {
    section: string
    chapterNumber?: number
    eventId?: number
    foreshadowingId?: number
    materialId?: string
    term?: string
    query?: string
  }) => {
    const targetSection: SectionKey = isSectionKey(payload.section) ? payload.section : 'overview'
    activeSection.value = targetSection
    await loadSection(targetSection, true)
    await options.router.replace({
      query: {
        ...options.route.query,
        section: targetSection,
        chapter: payload.chapterNumber ? String(payload.chapterNumber) : undefined,
        timeline_event_id: payload.eventId ? String(payload.eventId) : undefined,
        foreshadowing_id: payload.foreshadowingId ? String(payload.foreshadowingId) : undefined,
        material_id: payload.materialId || undefined,
        term: payload.term || undefined,
        search_q: payload.query || undefined,
      },
    })
  }

  const initializeFromRoute = () => {
    const initialSection = parseSectionFromQuery()
    if (initialSection) {
      activeSection.value = initialSection
    }
    syncFocusStateFromRoute()
    return initialSection
  }

  watch(
    () => [
      options.route.query.section,
      options.route.query.chapter,
      options.route.query.timeline_event_id,
      options.route.query.foreshadowing_id,
      options.route.query.material_id,
      options.route.query.term,
      options.route.query.search_q,
    ],
    () => {
      const targetSection = parseSectionFromQuery()
      if (targetSection && targetSection !== activeSection.value) {
        activeSection.value = targetSection
        void loadSection(targetSection)
      }
      syncFocusStateFromRoute()
    },
  )

  return {
    activeSection,
    componentContainerClass,
    componentProps,
    contentCardClass,
    currentComponent,
    currentError,
    getSectionIcon,
    handleGraphNavigate,
    handleWorldGraphRefresh,
    initializeFromRoute,
    isSectionKey,
    isSectionLoading,
    loadSection,
    overviewMeta,
    reloadSection,
    sectionData,
    sections,
    switchSection,
  }
}
