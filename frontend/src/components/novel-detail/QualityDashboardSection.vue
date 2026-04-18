<template>
  <div class="quality-dashboard space-y-6">
    <div class="flex flex-col gap-2">
      <h3 class="md-title-medium" style="color: var(--md-on-surface);">质量看板</h3>
      <p class="md-body-small" style="color: var(--md-on-surface-variant);">
        聚合一致性、伏笔闭环、章节完成度与稳定性，快速定位高风险点。
      </p>
    </div>

    <div v-if="!data" class="md-card md-card-outlined p-6 text-center" style="border-radius: var(--md-radius-md);">
      <p class="md-body-medium" style="color: var(--md-on-surface-variant);">暂无质量数据</p>
    </div>

    <template v-else>
      <div class="md-body-small" style="color: var(--md-on-surface-variant);">
        数据更新时间：{{ formatDateTime(data.generated_at) }}
      </div>

      <div class="grid grid-cols-2 gap-3 md:grid-cols-5">
        <div class="md-card md-card-outlined p-3 text-center" style="border-radius: var(--md-radius-md);">
          <p class="md-body-small" style="color: var(--md-on-surface-variant);">综合评分</p>
          <p class="md-title-large" style="color: var(--md-primary);">{{ formatScore(data.overall_score) }}</p>
        </div>
        <div class="md-card md-card-outlined p-3 text-center" style="border-radius: var(--md-radius-md);">
          <p class="md-body-small" style="color: var(--md-on-surface-variant);">一致性</p>
          <p class="md-title-large">{{ formatScore(data.metrics.consistency_score) }}</p>
        </div>
        <div class="md-card md-card-outlined p-3 text-center" style="border-radius: var(--md-radius-md);">
          <p class="md-body-small" style="color: var(--md-on-surface-variant);">伏笔闭环</p>
          <p class="md-title-large">{{ formatScore(data.metrics.foreshadowing_score) }}</p>
        </div>
        <div class="md-card md-card-outlined p-3 text-center" style="border-radius: var(--md-radius-md);">
          <p class="md-body-small" style="color: var(--md-on-surface-variant);">完成度</p>
          <p class="md-title-large">{{ formatScore(data.metrics.completion_score) }}</p>
        </div>
        <div class="md-card md-card-outlined p-3 text-center" style="border-radius: var(--md-radius-md);">
          <p class="md-body-small" style="color: var(--md-on-surface-variant);">稳定性</p>
          <p class="md-title-large">{{ formatScore(data.metrics.stability_score) }}</p>
        </div>
      </div>

      <div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div class="md-card md-card-outlined p-4" style="border-radius: var(--md-radius-md);">
          <h4 class="md-title-small mb-3">章节状态</h4>
          <div class="space-y-1 md-body-small" style="color: var(--md-on-surface-variant);">
            <div>总章节：{{ data.chapter_stats.total_chapters }}</div>
            <div>完成章节：{{ data.chapter_stats.successful_chapters }}</div>
            <div>失败章节：{{ data.chapter_stats.failed_chapters }}</div>
            <div>平均字数：{{ Number(data.chapter_stats.average_word_count || 0).toFixed(0) }}</div>
          </div>
        </div>

        <div class="md-card md-card-outlined p-4" style="border-radius: var(--md-radius-md);">
          <h4 class="md-title-small mb-3">伏笔与时间线</h4>
          <div class="space-y-1 md-body-small" style="color: var(--md-on-surface-variant);">
            <div>伏笔总数：{{ data.foreshadowing.total }}</div>
            <div>已回收：{{ data.foreshadowing.resolved }}</div>
            <div>未回收：{{ data.foreshadowing.unresolved }}</div>
            <div>时间线事件：{{ data.timeline.event_count }}</div>
            <div>关键转折：{{ data.timeline.turning_points }}</div>
          </div>
        </div>

        <div class="md-card md-card-outlined p-4" style="border-radius: var(--md-radius-md);">
          <h4 class="md-title-small mb-3">一致性统计</h4>
          <div class="space-y-1 md-body-small" style="color: var(--md-on-surface-variant);">
            <div>已检查版本：{{ data.consistency.checked_versions }}</div>
            <div>一致版本：{{ data.consistency.consistent_versions }}</div>
            <div>冲突总数：{{ data.consistency.violation_count }}</div>
            <div>
              严重度分布：
              critical {{ data.consistency.severity_breakdown.critical || 0 }} /
              major {{ data.consistency.severity_breakdown.major || 0 }} /
              minor {{ data.consistency.severity_breakdown.minor || 0 }}
            </div>
          </div>
        </div>
      </div>

      <div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div class="md-card md-card-outlined p-4" style="border-radius: var(--md-radius-md);">
          <h4 class="md-title-small mb-3">Top 风险</h4>
          <div v-if="!data.top_risks.length" class="md-body-small" style="color: var(--md-on-surface-variant);">
            当前未发现明显高风险项。
          </div>
          <ul v-else class="md-body-small quality-list" style="color: var(--md-on-surface-variant);">
            <li v-for="(item, index) in data.top_risks" :key="`risk-${index}`">{{ item }}</li>
          </ul>
        </div>

        <div class="md-card md-card-outlined p-4" style="border-radius: var(--md-radius-md);">
          <h4 class="md-title-small mb-3">修复建议</h4>
          <ul class="md-body-small quality-list" style="color: var(--md-on-surface-variant);">
            <li v-for="(item, index) in data.recommendations" :key="`rec-${index}`">{{ item }}</li>
          </ul>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import type { ProjectQualityDashboard } from '@/api/novel'

defineProps<{
  data?: ProjectQualityDashboard | null
}>()

const formatScore = (value: number): string => {
  const number = Number(value || 0)
  return Number.isFinite(number) ? number.toFixed(1) : '0.0'
}

const formatDateTime = (value?: string): string => {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleString('zh-CN', { hour12: false })
}
</script>

<style scoped>
.quality-list {
  margin: 0;
  padding-left: 18px;
  display: grid;
  gap: 8px;
  line-height: 1.6;
}
</style>
