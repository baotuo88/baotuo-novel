<!-- AIMETA P=指标卡组件_统一KPI展示|R=标签_数值_说明|NR=不含业务逻辑|E=component:MetricCard|X=internal|A=展示组件|D=vue|S=dom|RD=./README.ai -->
<template>
  <div class="platform-stat-card">
    <p class="platform-stat-label">{{ label }}</p>
    <p class="platform-stat-value" :style="valueStyle">{{ value }}</p>
    <p v-if="hint" class="platform-stat-hint">{{ hint }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  label: string
  value: string | number
  hint?: string
  compact?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  hint: '',
  compact: false
})

const valueStyle = computed(() => {
  return props.compact ? 'font-size: 20px;' : ''
})
</script>
