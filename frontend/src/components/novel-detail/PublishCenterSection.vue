<template>
  <div class="publish-center space-y-5">
    <div class="flex flex-col gap-1">
      <h3 class="md-title-medium" style="color: var(--md-on-surface);">发布中心</h3>
      <p class="md-body-small" style="color: var(--md-on-surface-variant);">
        导出单格式或批量打包（ZIP），支持目录模板与回调通知。
      </p>
    </div>

    <div v-if="data" class="grid grid-cols-2 gap-3 md:grid-cols-4">
      <div class="md-card md-card-outlined p-3" style="border-radius: var(--md-radius-md);">
        <p class="md-body-small stat-label">章节总数</p>
        <p class="md-title-large">{{ data.chapter_total }}</p>
      </div>
      <div class="md-card md-card-outlined p-3" style="border-radius: var(--md-radius-md);">
        <p class="md-body-small stat-label">已生成章节</p>
        <p class="md-title-large">{{ data.generated_chapter_total }}</p>
      </div>
      <div class="md-card md-card-outlined p-3" style="border-radius: var(--md-radius-md);">
        <p class="md-body-small stat-label">章节范围</p>
        <p class="md-title-small">
          <template v-if="data.first_chapter_number && data.last_chapter_number">
            {{ data.first_chapter_number }} - {{ data.last_chapter_number }}
          </template>
          <template v-else>-</template>
        </p>
      </div>
      <div class="md-card md-card-outlined p-3" style="border-radius: var(--md-radius-md);">
        <p class="md-body-small stat-label">最近生成</p>
        <p class="md-title-small">{{ data.latest_generated_chapter || '-' }}</p>
      </div>
    </div>

    <div class="md-card md-card-outlined p-4 md:p-5 space-y-5" style="border-radius: var(--md-radius-md);">
      <div>
        <div class="md-label-large mb-2">单格式导出</div>
        <div class="flex flex-wrap gap-2">
          <button
            v-for="item in formatOptions"
            :key="item.value"
            class="format-chip md-ripple"
            :class="{ active: selectedFormat === item.value }"
            @click="selectedFormat = item.value"
          >
            {{ item.label }}
          </button>
        </div>
      </div>

      <div>
        <div class="md-label-large mb-2">批量导出（ZIP）</div>
        <div class="flex flex-wrap gap-2">
          <label
            v-for="item in formatOptions"
            :key="`batch-${item.value}`"
            class="batch-chip"
            :class="{ active: batchFormats.includes(item.value) }"
          >
            <input
              type="checkbox"
              :checked="batchFormats.includes(item.value)"
              @change="toggleBatchFormat(item.value)"
            />
            <span>{{ item.label }}</span>
          </label>
        </div>
      </div>

      <div>
        <div class="md-label-large mb-2">导出范围</div>
        <div class="flex flex-wrap gap-3 items-center">
          <label class="scope-radio">
            <input v-model="scope" type="radio" value="all" />
            <span>全部章节</span>
          </label>
          <label class="scope-radio">
            <input v-model="scope" type="radio" value="range" />
            <span>指定范围</span>
          </label>
          <div v-if="scope === 'range'" class="range-inputs">
            <input v-model.number="startChapter" type="number" min="1" class="range-input" placeholder="开始章" />
            <span>至</span>
            <input v-model.number="endChapter" type="number" min="1" class="range-input" placeholder="结束章" />
          </div>
        </div>
      </div>

      <div class="grid gap-3 md:grid-cols-2">
        <div>
          <div class="md-label-large mb-2">目录样式</div>
          <select v-model="tocStyle" class="field-select">
            <option value="compact">简洁目录</option>
            <option value="detailed">详细目录</option>
            <option value="none">不生成目录</option>
          </select>
        </div>
        <div>
          <div class="md-label-large mb-2">导出回调（可选）</div>
          <input
            v-model.trim="webhookUrl"
            type="text"
            class="field-input"
            placeholder="https://example.com/webhook"
          />
        </div>
      </div>

      <div class="flex flex-wrap gap-4">
        <label class="toggle-item">
          <input v-model="includeOutline" type="checkbox" />
          <span>包含章节摘要</span>
        </label>
        <label class="toggle-item">
          <input v-model="includeMetadata" type="checkbox" />
          <span>包含导出元信息</span>
        </label>
      </div>

      <p v-if="errorMessage" class="md-body-small text-red-500">{{ errorMessage }}</p>

      <div class="flex flex-wrap justify-end gap-3">
        <button
          class="md-btn md-btn-outlined md-ripple"
          :disabled="batchExporting || exporting || !canBatchExport || !canExport"
          @click="downloadBatchExport"
        >
          {{ batchExporting ? '打包中...' : '批量导出 ZIP' }}
        </button>
        <button
          class="md-btn md-btn-filled md-ripple"
          :disabled="exporting || batchExporting || !canExport"
          @click="downloadExport"
        >
          {{ exporting ? '导出中...' : '单格式导出' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NovelAPI, type PublishFormat, type PublishSummaryResponse, type PublishTocStyle } from '@/api/novel'

const props = defineProps<{
  projectId: string
  data?: PublishSummaryResponse | null
}>()

const formatOptions: Array<{ label: string; value: PublishFormat }> = [
  { label: 'Markdown', value: 'markdown' },
  { label: 'TXT', value: 'txt' },
  { label: 'DOCX', value: 'docx' },
  { label: 'EPUB', value: 'epub' }
]

const selectedFormat = ref<PublishFormat>('markdown')
const batchFormats = ref<PublishFormat[]>(['markdown', 'txt'])
const scope = ref<'all' | 'range'>('all')
const startChapter = ref<number | null>(null)
const endChapter = ref<number | null>(null)
const includeOutline = ref(true)
const includeMetadata = ref(true)
const tocStyle = ref<PublishTocStyle>('compact')
const webhookUrl = ref('')
const exporting = ref(false)
const batchExporting = ref(false)
const errorMessage = ref('')

watch(
  () => props.data,
  (value) => {
    if (!value) return
    startChapter.value = value.first_chapter_number ?? null
    endChapter.value = value.last_chapter_number ?? null
  },
  { immediate: true }
)

const canExport = computed(() => {
  if (scope.value !== 'range') return true
  if (!startChapter.value || !endChapter.value) return false
  return startChapter.value > 0 && endChapter.value >= startChapter.value
})

const canBatchExport = computed(() => batchFormats.value.length > 0)

const toggleBatchFormat = (format: PublishFormat) => {
  if (batchFormats.value.includes(format)) {
    batchFormats.value = batchFormats.value.filter((item) => item !== format)
    return
  }
  batchFormats.value = [...batchFormats.value, format]
}

const buildQuery = () => ({
  start_chapter: scope.value === 'range' ? startChapter.value || undefined : undefined,
  end_chapter: scope.value === 'range' ? endChapter.value || undefined : undefined,
  include_outline: includeOutline.value,
  include_metadata: includeMetadata.value,
  toc_style: tocStyle.value,
  webhook_url: webhookUrl.value || undefined
})

const downloadExport = async () => {
  errorMessage.value = ''
  if (!canExport.value) {
    errorMessage.value = '指定范围无效，请检查开始章和结束章'
    return
  }
  exporting.value = true
  try {
    await NovelAPI.downloadPublishExport(props.projectId, {
      format: selectedFormat.value,
      ...buildQuery()
    })
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '导出失败，请稍后重试'
  } finally {
    exporting.value = false
  }
}

const downloadBatchExport = async () => {
  errorMessage.value = ''
  if (!canExport.value) {
    errorMessage.value = '指定范围无效，请检查开始章和结束章'
    return
  }
  if (!canBatchExport.value) {
    errorMessage.value = '请至少选择一个导出格式'
    return
  }
  batchExporting.value = true
  try {
    await NovelAPI.downloadPublishBatchExport(props.projectId, {
      formats: batchFormats.value,
      ...buildQuery()
    })
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '批量导出失败，请稍后重试'
  } finally {
    batchExporting.value = false
  }
}
</script>

<style scoped>
.stat-label {
  color: var(--md-on-surface-variant);
}

.format-chip,
.batch-chip {
  border: 1px solid var(--md-outline-variant);
  background: color-mix(in srgb, var(--md-surface-container) 88%, white 12%);
  color: var(--md-on-surface);
  border-radius: 999px;
  padding: 6px 14px;
  font-size: 13px;
  transition: all .2s ease;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.batch-chip input {
  accent-color: var(--md-primary);
}

.format-chip.active,
.batch-chip.active {
  border-color: color-mix(in srgb, var(--md-primary) 68%, transparent);
  background: color-mix(in srgb, var(--md-primary-container) 72%, white 28%);
  color: var(--md-on-primary-container);
}

.scope-radio {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--md-on-surface);
}

.range-inputs {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--md-on-surface-variant);
}

.range-input,
.field-select,
.field-input {
  height: 34px;
  border: 1px solid var(--md-outline-variant);
  border-radius: 8px;
  padding: 0 10px;
  background: color-mix(in srgb, var(--md-surface-container-low) 84%, white 16%);
  color: var(--md-on-surface);
}

.range-input {
  width: 88px;
}

.field-select,
.field-input {
  width: 100%;
}

.toggle-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--md-on-surface);
}
</style>
