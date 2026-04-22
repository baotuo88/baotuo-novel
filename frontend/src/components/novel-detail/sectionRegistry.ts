import { h } from 'vue'

import type { AllSectionType } from '@/api/novel'
import OverviewSection from '@/components/novel-detail/OverviewSection.vue'
import ComprehensiveDiagnosisSection from '@/components/novel-detail/ComprehensiveDiagnosisSection.vue'
import WorldSettingSection from '@/components/novel-detail/WorldSettingSection.vue'
import CharactersSection from '@/components/novel-detail/CharactersSection.vue'
import RelationshipsSection from '@/components/novel-detail/RelationshipsSection.vue'
import ChapterOutlineSection from '@/components/novel-detail/ChapterOutlineSection.vue'
import ChaptersSection from '@/components/novel-detail/ChaptersSection.vue'
import EmotionCurveSection from '@/components/novel-detail/EmotionCurveSection.vue'
import ForeshadowingSection from '@/components/novel-detail/ForeshadowingSection.vue'
import TimelineSection from '@/components/novel-detail/TimelineSection.vue'
import TerminologySection from '@/components/novel-detail/TerminologySection.vue'
import WorldGraphSection from '@/components/novel-detail/WorldGraphSection.vue'
import QualityDashboardSection from '@/components/novel-detail/QualityDashboardSection.vue'
import PublishCenterSection from '@/components/novel-detail/PublishCenterSection.vue'
import MaterialLibrarySection from '@/components/novel-detail/MaterialLibrarySection.vue'
import ProjectBackupSection from '@/components/novel-detail/ProjectBackupSection.vue'
import GlobalSearchSection from '@/components/novel-detail/GlobalSearchSection.vue'

export type SectionKey = AllSectionType

export interface SectionDefinition {
  key: SectionKey
  label: string
  description: string
}

export const ALL_SECTION_KEYS: SectionKey[] = [
  'comprehensive_diagnosis',
  'overview',
  'world_setting',
  'characters',
  'relationships',
  'world_graph',
  'quality_dashboard',
  'publish_center',
  'material_library',
  'global_search',
  'project_backup',
  'timeline',
  'terminology',
  'chapter_outline',
  'chapters',
  'emotion_curve',
  'foreshadowing',
]

export const ANALYSIS_SECTIONS: SectionKey[] = [
  'comprehensive_diagnosis',
  'emotion_curve',
  'foreshadowing',
  'timeline',
  'terminology',
  'publish_center',
  'material_library',
  'global_search',
  'project_backup',
]

export const FILL_SECTIONS: SectionKey[] = ['chapters']

export const buildSections = (isAdmin: boolean): SectionDefinition[] => [
  ...(!isAdmin
    ? [{ key: 'comprehensive_diagnosis' as SectionKey, label: '综合诊断', description: '汇总质量、轨迹与行动建议' }]
    : []),
  { key: 'overview', label: '项目概览', description: '定位与整体梗概' },
  { key: 'world_setting', label: '世界设定', description: '规则、地点与阵营' },
  { key: 'characters', label: '主要角色', description: '人物性格与目标' },
  { key: 'relationships', label: '人物关系', description: '角色之间的联系' },
  ...(!isAdmin
    ? [
        { key: 'world_graph' as SectionKey, label: '世界图谱', description: '结构树与关系网' },
        { key: 'quality_dashboard' as SectionKey, label: '质量看板', description: '一致性与闭环质量' },
        { key: 'publish_center' as SectionKey, label: '发布中心', description: '多格式导出与发布' },
        { key: 'material_library' as SectionKey, label: '素材库', description: '灵感与资料统一管理' },
        { key: 'global_search' as SectionKey, label: '全局搜索', description: '跨模块统一检索入口' },
        { key: 'project_backup' as SectionKey, label: '备份恢复', description: '项目导入导出与恢复' },
      ]
    : []),
  { key: 'timeline', label: '故事时间线', description: '章节事件与时间锚点' },
  { key: 'terminology', label: '术语词典', description: '名称统一与生成约束' },
  { key: 'chapter_outline', label: '章节大纲', description: isAdmin ? '故事章节规划' : '故事结构规划' },
  { key: 'chapters', label: '章节内容', description: isAdmin ? '生成章节与正文' : '生成状态与摘要' },
  { key: 'emotion_curve', label: '情感曲线', description: '追踪章节情感变化' },
  { key: 'foreshadowing', label: '伏笔管理', description: '故事线索与回收' },
]

export const sectionComponents: Record<SectionKey, any> = {
  comprehensive_diagnosis: ComprehensiveDiagnosisSection,
  overview: OverviewSection,
  world_setting: WorldSettingSection,
  characters: CharactersSection,
  relationships: RelationshipsSection,
  world_graph: WorldGraphSection,
  quality_dashboard: QualityDashboardSection,
  publish_center: PublishCenterSection,
  material_library: MaterialLibrarySection,
  global_search: GlobalSearchSection,
  project_backup: ProjectBackupSection,
  timeline: TimelineSection,
  terminology: TerminologySection,
  chapter_outline: ChapterOutlineSection,
  chapters: ChaptersSection,
  emotion_curve: EmotionCurveSection,
  foreshadowing: ForeshadowingSection,
}

export const getSectionIcon = (key: SectionKey) => {
  const icons: Record<SectionKey, any> = {
    comprehensive_diagnosis: () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 }, [
      h('path', { d: 'M4 19h16' }),
      h('path', { d: 'M6 16l4-5 3 3 5-7' }),
      h('circle', { cx: 6, cy: 16, r: 1 }),
      h('circle', { cx: 10, cy: 11, r: 1 }),
      h('circle', { cx: 13, cy: 14, r: 1 }),
      h('circle', { cx: 18, cy: 7, r: 1 }),
    ]),
    overview: () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 }, [
      h('rect', { x: 3, y: 3, width: 18, height: 18, rx: 2 }),
      h('line', { x1: 3, y1: 9, x2: 21, y2: 9 }),
      h('line', { x1: 9, y1: 21, x2: 9, y2: 9 }),
    ]),
    world_setting: () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 }, [
      h('circle', { cx: 12, cy: 12, r: 10 }),
      h('path', { d: 'M2 12h20M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z' }),
    ]),
    characters: () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 }, [
      h('path', { d: 'M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2' }),
      h('circle', { cx: 9, cy: 7, r: 4 }),
      h('path', { d: 'M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75' }),
    ]),
    relationships: () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 }, [
      h('path', { d: 'M16 21v-2a4 4 0 00-4-4H6a4 4 0 00-4 4v2' }),
      h('circle', { cx: 9, cy: 7, r: 4 }),
      h('path', { d: 'M22 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75' }),
    ]),
    world_graph: () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 }, [
      h('circle', { cx: 6, cy: 6, r: 2 }),
      h('circle', { cx: 18, cy: 6, r: 2 }),
      h('circle', { cx: 12, cy: 18, r: 2 }),
      h('path', { d: 'M8 6h8M7.5 7.2l3.8 8M16.5 7.2l-3.8 8' }),
    ]),
    quality_dashboard: () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 }, [
      h('path', { d: 'M4 19h16' }),
      h('path', { d: 'M7 19V9m5 10V5m5 14v-7' }),
      h('path', { d: 'M4 5h16' }),
    ]),
    publish_center: () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 }, [
      h('path', { d: 'M12 3v12' }),
      h('path', { d: 'M7 10l5 5 5-5' }),
      h('rect', { x: 4, y: 17, width: 16, height: 4, rx: 1.5 }),
    ]),
    material_library: () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 }, [
      h('path', { d: 'M4 5h16v14H4z' }),
      h('path', { d: 'M8 9h8M8 13h8M8 17h4' }),
    ]),
    global_search: () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 }, [
      h('circle', { cx: 11, cy: 11, r: 7 }),
      h('path', { d: 'M21 21l-4.35-4.35' }),
    ]),
    project_backup: () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 }, [
      h('path', { d: 'M12 3v12' }),
      h('path', { d: 'M8 7l4-4 4 4' }),
      h('path', { d: 'M5 14v5h14v-5' }),
    ]),
    timeline: () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 }, [
      h('circle', { cx: 5, cy: 6, r: 1.5 }),
      h('circle', { cx: 5, cy: 12, r: 1.5 }),
      h('circle', { cx: 5, cy: 18, r: 1.5 }),
      h('path', { d: 'M8 6h12M8 12h12M8 18h12' }),
    ]),
    terminology: () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 }, [
      h('path', { d: 'M4 4h16v16H4z' }),
      h('path', { d: 'M8 8h8M8 12h8M8 16h5' }),
    ]),
    chapter_outline: () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 }, [
      h('line', { x1: 8, y1: 6, x2: 21, y2: 6 }),
      h('line', { x1: 8, y1: 12, x2: 21, y2: 12 }),
      h('line', { x1: 8, y1: 18, x2: 21, y2: 18 }),
      h('line', { x1: 3, y1: 6, x2: 3.01, y2: 6 }),
      h('line', { x1: 3, y1: 12, x2: 3.01, y2: 12 }),
      h('line', { x1: 3, y1: 18, x2: 3.01, y2: 18 }),
    ]),
    chapters: () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 }, [
      h('path', { d: 'M4 19.5A2.5 2.5 0 016.5 17H20' }),
      h('path', { d: 'M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z' }),
    ]),
    emotion_curve: () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 }, [
      h('path', { d: 'M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z' }),
    ]),
    foreshadowing: () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 }, [
      h('path', { d: 'M13 10V3L4 14h7v7l9-11h-7z' }),
    ]),
  }

  return icons[key]
}
