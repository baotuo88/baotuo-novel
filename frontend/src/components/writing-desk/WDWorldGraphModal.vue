<template>
  <Teleport to="body">
    <div
      v-if="show"
      class="md-dialog-overlay"
      @click.self="$emit('close')"
    >
      <div class="md-dialog m3-world-graph-dialog flex flex-col">
        <div class="p-5 border-b flex items-start justify-between gap-4" style="border-bottom-color: var(--md-outline-variant);">
          <div>
            <h3 class="md-title-large font-semibold">世界观树 + 人物关系图</h3>
            <p class="md-body-small md-on-surface-variant mt-1">
              可视化查看并编辑世界设定、角色关系与势力结构。
            </p>
          </div>
          <div class="flex items-center gap-2">
            <button
              class="md-btn md-btn-tonal md-ripple"
              :disabled="loading"
              @click="loadWorldGraph"
            >
              {{ loading ? '刷新中...' : '刷新' }}
            </button>
            <button
              class="md-icon-btn md-ripple"
              @click="$emit('close')"
            >
              <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"></path>
              </svg>
            </button>
          </div>
        </div>

        <div class="flex-1 min-h-0 overflow-y-auto p-5">
          <div v-if="loading" class="h-full flex flex-col items-center justify-center gap-3">
            <div class="md-spinner"></div>
            <p class="md-body-small md-on-surface-variant">正在加载图谱数据...</p>
          </div>
          <div v-else-if="errorMessage" class="h-full flex flex-col items-center justify-center gap-3">
            <p class="md-body-medium text-center" style="color: var(--md-error);">{{ errorMessage }}</p>
            <button class="md-btn md-btn-filled md-ripple" @click="loadWorldGraph">重试</button>
          </div>
          <WorldGraphSection
            v-else
            :data="worldGraphData"
            :editable="true"
            :project-id="projectId || undefined"
            @refresh="handleGraphRefresh"
          />
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { NovelAPI, type WorldGraphResponse } from '@/api/novel'
import WorldGraphSection from '@/components/novel-detail/WorldGraphSection.vue'

interface Props {
  show: boolean
  projectId: string | null
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'graphUpdated'): void
}>()

const loading = ref(false)
const errorMessage = ref('')
const worldGraphData = ref<WorldGraphResponse | null>(null)

const loadWorldGraph = async () => {
  if (!props.projectId) return
  loading.value = true
  errorMessage.value = ''
  try {
    worldGraphData.value = await NovelAPI.getWorldGraph(props.projectId)
  } catch (error) {
    errorMessage.value = `图谱加载失败：${error instanceof Error ? error.message : '未知错误'}`
  } finally {
    loading.value = false
  }
}

const handleGraphRefresh = async () => {
  await loadWorldGraph()
  emit('graphUpdated')
}

watch(
  () => [props.show, props.projectId],
  ([show, projectId]) => {
    if (!show || !projectId) return
    void loadWorldGraph()
  },
  { immediate: true }
)
</script>

<style scoped>
.m3-world-graph-dialog {
  width: min(1360px, calc(100vw - 24px));
  height: min(920px, calc(100vh - 24px));
  height: min(920px, calc(100dvh - 24px));
  border-radius: var(--md-radius-xl);
}
</style>
