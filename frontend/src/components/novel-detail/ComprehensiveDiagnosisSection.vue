<template>
  <div class="space-y-6">
    <div class="flex flex-col gap-2">
      <h3 class="md-title-medium" style="color: var(--md-on-surface);">综合诊断</h3>
      <p class="md-body-small" style="color: var(--md-on-surface-variant);">
        汇总质量看板、故事轨迹、创意建议与重点伏笔，帮助你优先处理最值钱的问题。
      </p>
    </div>

    <div v-if="!data" class="md-card md-card-outlined p-6 text-center" style="border-radius: var(--md-radius-md);">
      <p class="md-body-medium" style="color: var(--md-on-surface-variant);">暂无综合诊断数据</p>
    </div>

    <template v-else>
      <div class="grid grid-cols-2 gap-3 xl:grid-cols-5">
        <div class="md-card md-card-outlined p-3 text-center" style="border-radius: var(--md-radius-md);">
          <p class="md-body-small" style="color: var(--md-on-surface-variant);">综合评分</p>
          <p class="md-title-large" style="color: var(--md-primary);">{{ formatScore(data.quality_dashboard.overall_score) }}</p>
        </div>
        <div class="md-card md-card-outlined p-3 text-center" style="border-radius: var(--md-radius-md);">
          <p class="md-body-small" style="color: var(--md-on-surface-variant);">轨迹形状</p>
          <p class="md-title-medium">{{ trajectoryShapeLabel(data.trajectory.shape) }}</p>
        </div>
        <div class="md-card md-card-outlined p-3 text-center" style="border-radius: var(--md-radius-md);">
          <p class="md-body-small" style="color: var(--md-on-surface-variant);">当前章节</p>
          <p class="md-title-large">{{ data.guidance.current_chapter }}</p>
        </div>
        <div class="md-card md-card-outlined p-3 text-center" style="border-radius: var(--md-radius-md);">
          <p class="md-body-small" style="color: var(--md-on-surface-variant);">重点动作</p>
          <p class="md-title-large">{{ data.focus_actions.length }}</p>
        </div>
        <div class="md-card md-card-outlined p-3 text-center" style="border-radius: var(--md-radius-md);">
          <p class="md-body-small" style="color: var(--md-on-surface-variant);">重点伏笔</p>
          <p class="md-title-large">{{ data.foreshadowings.length }}</p>
        </div>
      </div>

      <div class="grid grid-cols-1 gap-4 xl:grid-cols-[1.3fr,0.9fr]">
        <section class="md-card md-card-outlined p-4 space-y-3" style="border-radius: var(--md-radius-md);">
          <div class="flex items-center justify-between gap-3">
            <h4 class="md-title-small">优先动作</h4>
            <span class="md-body-small" style="color: var(--md-on-surface-variant);">
              先处理影响最大的 {{ Math.min(data.focus_actions.length, 6) }} 项
            </span>
          </div>
          <div v-if="!data.focus_actions.length" class="md-body-small" style="color: var(--md-on-surface-variant);">
            当前没有明确的优先动作，项目状态相对稳定。
          </div>
          <div v-else class="space-y-3">
            <article
              v-for="item in data.focus_actions"
              :key="item.id"
              class="rounded-xl border p-4 space-y-3"
              style="border-color: var(--md-outline-variant);"
            >
              <div class="flex flex-wrap items-center gap-2">
                <span class="diag-chip" :style="severityStyle(item.severity)">{{ severityLabel(item.severity) }}</span>
                <span class="diag-chip diag-chip-neutral">{{ item.category }}</span>
              </div>
              <div>
                <h5 class="md-title-small">{{ item.title }}</h5>
                <p class="md-body-small mt-1" style="color: var(--md-on-surface-variant);">{{ item.summary }}</p>
              </div>
              <div class="flex flex-wrap justify-end gap-2">
                <button
                  v-if="canRunConsistencyCheck(item.anchor)"
                  class="md-btn md-btn-tonal md-ripple"
                  :disabled="actionLoading[item.id]"
                  @click="runConsistencyCheck(item.id, item.anchor)"
                >
                  {{ actionLoading[item.id] ? '检查中...' : '一致性检查' }}
                </button>
                <button
                  v-if="item.anchor.query || item.anchor.term"
                  class="md-btn md-btn-outlined md-ripple"
                  @click="navigateTo({ section: item.anchor.term ? 'terminology' : 'global_search', term: item.anchor.term, query: item.anchor.query })"
                >
                  {{ item.anchor.term ? '查看术语' : '检索线索' }}
                </button>
                <button class="md-btn md-btn-filled md-ripple" @click="navigateTo(item.anchor)">
                  {{ item.category === 'foreshadowing' ? '处理伏笔' : item.category === 'trajectory' ? '检查时间线' : '立即处理' }}
                </button>
              </div>
            </article>
          </div>
        </section>

        <section class="space-y-4">
          <div class="md-card md-card-outlined p-4 space-y-2" style="border-radius: var(--md-radius-md);">
            <h4 class="md-title-small">轨迹摘要</h4>
            <p class="md-body-small" style="color: var(--md-on-surface-variant);">{{ data.trajectory.description }}</p>
            <div class="md-body-small diag-grid-text" style="color: var(--md-on-surface-variant);">
              <div>强度均值：{{ formatScore(data.trajectory.avg_intensity) }}</div>
              <div>波动性：{{ formatScore(data.trajectory.volatility) }}</div>
              <div>高峰章节：{{ joinNumbers(data.trajectory.peak_chapters) }}</div>
              <div>转折章节：{{ joinNumbers(data.trajectory.turning_points) }}</div>
            </div>
          </div>

          <div class="md-card md-card-outlined p-4 space-y-2" style="border-radius: var(--md-radius-md);">
            <h4 class="md-title-small">质量摘要</h4>
            <div class="md-body-small diag-grid-text" style="color: var(--md-on-surface-variant);">
              <div>一致性：{{ formatScore(data.quality_dashboard.metrics.consistency_score) }}</div>
              <div>伏笔闭环：{{ formatScore(data.quality_dashboard.metrics.foreshadowing_score) }}</div>
              <div>完成度：{{ formatScore(data.quality_dashboard.metrics.completion_score) }}</div>
              <div>稳定性：{{ formatScore(data.quality_dashboard.metrics.stability_score) }}</div>
            </div>
          </div>

          <div class="md-card md-card-outlined p-4 space-y-2" style="border-radius: var(--md-radius-md);">
            <h4 class="md-title-small">总体判断</h4>
            <p class="md-body-small" style="color: var(--md-on-surface-variant);">{{ data.guidance.overall_assessment }}</p>
            <ul class="diag-list md-body-small" style="color: var(--md-on-surface-variant);">
              <li v-for="item in data.guidance.next_chapter_suggestions.slice(0, 3)" :key="item">{{ item }}</li>
            </ul>
          </div>
        </section>
      </div>

      <div class="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <section class="md-card md-card-outlined p-4 space-y-3" style="border-radius: var(--md-radius-md);">
          <h4 class="md-title-small">重点伏笔</h4>
          <div v-if="!data.foreshadowings.length" class="md-body-small" style="color: var(--md-on-surface-variant);">
            当前没有重点伏笔项。
          </div>
          <div v-else class="space-y-3">
            <article
              v-for="item in data.foreshadowings.slice(0, 6)"
              :key="item.id"
              class="rounded-xl border p-4 space-y-2"
              style="border-color: var(--md-outline-variant);"
            >
              <div class="flex flex-wrap items-center gap-2">
                <span class="diag-chip diag-chip-neutral">第{{ item.chapter_number }}章</span>
                <span class="diag-chip" :style="foreshadowingStatusStyle(item.status)">{{ foreshadowingStatusLabel(item.status) }}</span>
                <span v-if="item.priority_hint === 'high'" class="diag-chip" style="background: rgba(179, 38, 30, 0.12); color: #b3261e;">
                  高优先级
                </span>
              </div>
              <p class="md-body-small" style="color: var(--md-on-surface);">{{ item.content }}</p>
              <div class="md-body-small" style="color: var(--md-on-surface-variant);">
                <span>类型：{{ item.type }}</span>
                <span v-if="item.related_characters.length"> · 角色：{{ item.related_characters.join('、') }}</span>
              </div>
              <div class="flex flex-wrap justify-end gap-2">
                <button
                  v-if="item.keywords.length"
                  class="md-btn md-btn-text md-ripple"
                  @click="navigateTo({ section: 'global_search', query: item.keywords[0], chapter_number: item.chapter_number })"
                >
                  搜同类线索
                </button>
                <button
                  class="md-btn md-btn-outlined md-ripple"
                  @click="navigateTo({ section: 'foreshadowing', chapter_number: item.chapter_number, foreshadowing_id: item.id })"
                >
                  查看伏笔
                </button>
              </div>
            </article>
          </div>
        </section>

        <section class="md-card md-card-outlined p-4 space-y-3" style="border-radius: var(--md-radius-md);">
          <h4 class="md-title-small">详细建议</h4>
          <div v-if="!data.guidance.guidance_items.length" class="md-body-small" style="color: var(--md-on-surface-variant);">
            当前没有额外的精细建议。
          </div>
          <div v-else class="space-y-3">
            <article
              v-for="item in data.guidance.guidance_items.slice(0, 4)"
              :key="`${item.type}-${item.title}`"
              class="rounded-xl border p-4 space-y-2"
              style="border-color: var(--md-outline-variant);"
            >
              <div class="flex flex-wrap items-center gap-2">
                <span class="diag-chip" :style="severityStyle(item.priority)">{{ severityLabel(item.priority) }}</span>
                <span class="diag-chip diag-chip-neutral">{{ item.type }}</span>
              </div>
              <h5 class="md-title-small">{{ item.title }}</h5>
              <p class="md-body-small" style="color: var(--md-on-surface-variant);">{{ item.description }}</p>
              <ul v-if="item.specific_suggestions?.length" class="diag-list md-body-small" style="color: var(--md-on-surface-variant);">
                <li v-for="suggestion in item.specific_suggestions.slice(0, 3)" :key="suggestion">{{ suggestion }}</li>
              </ul>
            </article>
          </div>
        </section>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { reactive } from 'vue'
import { NovelAPI, type ComprehensiveActionAnchor, type ComprehensiveAnalysisResponse } from '@/api/novel'
import {
  buildNavigatePayload,
  foreshadowingStatusLabel,
  severityLabel,
  trajectoryShapeLabel,
} from '@/components/novel-detail/comprehensiveDiagnosis'
import { globalAlert } from '@/composables/useAlert'

const props = defineProps<{
  data?: ComprehensiveAnalysisResponse | null
  projectId?: string
}>()

const emit = defineEmits<{
  navigate: [payload: {
    section: string
    chapterNumber?: number
    eventId?: number
    foreshadowingId?: number
    materialId?: string
    term?: string
    query?: string
  }]
}>()

const actionLoading = reactive<Record<string, boolean>>({})

const formatScore = (value?: number): string => {
  const numeric = Number(value || 0)
  return Number.isFinite(numeric) ? numeric.toFixed(1) : '0.0'
}

const joinNumbers = (items?: number[]): string => {
  if (!items?.length) return '-'
  return items.join(' / ')
}

const severityStyle = (severity: string): string => {
  const normalized = String(severity || '').trim().toLowerCase()
  if (normalized === 'critical') return 'background: rgba(179, 38, 30, 0.16); color: #b3261e;'
  if (normalized === 'high') return 'background: rgba(176, 96, 0, 0.16); color: #8a5200;'
  if (normalized === 'low') return 'background: rgba(24, 128, 56, 0.14); color: #188038;'
  return 'background: rgba(25, 103, 210, 0.14); color: #1967d2;'
}

const foreshadowingStatusStyle = (status: string): string => {
  if (status === 'resolved') return 'background: rgba(24, 128, 56, 0.14); color: #188038;'
  if (status === 'abandoned') return 'background: rgba(179, 38, 30, 0.12); color: #b3261e;'
  return 'background: rgba(176, 96, 0, 0.14); color: #8a5200;'
}

const navigateTo = (anchor: ComprehensiveActionAnchor) => {
  emit('navigate', buildNavigatePayload(anchor))
}

const canRunConsistencyCheck = (anchor: ComprehensiveActionAnchor): boolean => {
  return String(anchor.section || '') === 'chapters' && Number(anchor.chapter_number || 0) > 0
}

const runConsistencyCheck = async (actionId: string, anchor: ComprehensiveActionAnchor) => {
  if (!props.projectId || !canRunConsistencyCheck(anchor)) return
  const chapterNumber = Number(anchor.chapter_number)
  actionLoading[actionId] = true
  try {
    const response = await NovelAPI.checkChapterConsistency(props.projectId, chapterNumber)
    if (response.review.is_consistent) {
      globalAlert.showSuccess(`第${chapterNumber}章一致性检查通过`, '检查完成')
    } else {
      globalAlert.showError(`第${chapterNumber}章发现 ${response.review.violations.length} 个潜在冲突`, '一致性预警')
    }
    navigateTo(anchor)
  } catch (error) {
    globalAlert.showError(`一致性检查失败: ${error instanceof Error ? error.message : '未知错误'}`)
  } finally {
    actionLoading[actionId] = false
  }
}
</script>

<style scoped>
.diag-chip {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 12px;
  font-weight: 600;
}

.diag-chip-neutral {
  background: color-mix(in srgb, var(--md-surface-container-high) 88%, #ffffff 12%);
  color: var(--md-on-surface-variant);
}

.diag-grid-text {
  display: grid;
  gap: 8px;
}

.diag-list {
  margin: 0;
  padding-left: 18px;
  display: grid;
  gap: 8px;
  line-height: 1.6;
}
</style>
