<template>
  <div class="project-backup space-y-5">
    <div>
      <h3 class="md-title-medium" style="color: var(--md-on-surface);">项目备份与恢复</h3>
      <p class="md-body-small" style="color: var(--md-on-surface-variant);">
        导出完整项目 JSON；可恢复到当前项目，或导入为新项目。
      </p>
    </div>

    <div class="md-card md-card-outlined p-4 space-y-4" style="border-radius: var(--md-radius-md);">
      <div class="flex flex-wrap items-center gap-3">
        <button class="md-btn md-btn-filled md-ripple" :disabled="busy" @click="downloadBackup">
          {{ busy ? '处理中...' : '下载项目备份' }}
        </button>
        <label class="md-btn md-btn-outlined md-ripple cursor-pointer">
          选择备份文件
          <input type="file" class="hidden" accept=".json,application/json" @change="handleFileChange" />
        </label>
        <span class="md-body-small md-on-surface-variant">
          {{ selectedFileName || '未选择文件' }}
        </span>
      </div>

      <div class="flex flex-wrap gap-3">
        <button
          class="md-btn md-btn-outlined md-ripple"
          :disabled="busy || !backupPayload"
          @click="restoreCurrentProject"
        >
          恢复到当前项目
        </button>
        <button
          class="md-btn md-btn-filled md-ripple"
          :disabled="busy || !backupPayload"
          @click="importAsNewProject"
        >
          导入为新项目
        </button>
      </div>

      <p v-if="message" class="md-body-small md-on-surface-variant">{{ message }}</p>
      <p v-if="errorMessage" class="md-body-small text-red-500">{{ errorMessage }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { NovelAPI } from '@/api/novel'

const props = defineProps<{
  projectId: string
}>()

const router = useRouter()
const busy = ref(false)
const selectedFileName = ref('')
const backupPayload = ref<Record<string, any> | null>(null)
const message = ref('')
const errorMessage = ref('')

const downloadBackup = async () => {
  busy.value = true
  errorMessage.value = ''
  message.value = ''
  try {
    await NovelAPI.downloadProjectBackup(props.projectId)
    message.value = '备份下载成功'
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '备份下载失败'
  } finally {
    busy.value = false
  }
}

const handleFileChange = async (event: Event) => {
  errorMessage.value = ''
  message.value = ''
  backupPayload.value = null
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  selectedFileName.value = file?.name || ''
  if (!file) return
  try {
    const text = await file.text()
    const parsed = JSON.parse(text)
    if (!parsed || typeof parsed !== 'object') {
      throw new Error('备份文件格式错误')
    }
    backupPayload.value = parsed as Record<string, any>
    message.value = '备份文件已加载，可执行恢复或导入'
  } catch (error) {
    backupPayload.value = null
    errorMessage.value = error instanceof Error ? error.message : '备份文件解析失败'
  }
}

const restoreCurrentProject = async () => {
  if (!backupPayload.value) return
  const confirmed = window.confirm('恢复会覆盖当前项目已有数据，确认继续？')
  if (!confirmed) return
  busy.value = true
  errorMessage.value = ''
  message.value = ''
  try {
    const result = await NovelAPI.restoreProjectFromBackup(props.projectId, {
      backup: backupPayload.value
    })
    message.value = `${result.message}（章节 ${result.stats.chapter_count || 0}）`
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '恢复失败'
  } finally {
    busy.value = false
  }
}

const importAsNewProject = async () => {
  if (!backupPayload.value) return
  busy.value = true
  errorMessage.value = ''
  message.value = ''
  try {
    const result = await NovelAPI.importProjectBackup({
      backup: backupPayload.value
    })
    message.value = `${result.message}：${result.title}`
    await router.push(`/detail/${result.project_id}`)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '导入失败'
  } finally {
    busy.value = false
  }
}
</script>
