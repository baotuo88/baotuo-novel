<!-- AIMETA P=对话输入_用户输入组件|R=输入框_发送|NR=不含消息展示|E=component:ConversationInput|X=internal|A=输入组件|D=vue|S=dom|RD=./README.ai -->
<template>
  <div class="inspiration-input-shell fade-in">
    <!-- 加载状态 -->
    <div v-if="loading || !uiControl" class="inspiration-loading-state">
      <div class="md-spinner inspiration-loading-spinner"></div>
    </div>

    <!-- 单选题 -->
    <div v-else-if="uiControl.type === 'single_choice'" class="inspiration-input-body">
      <div class="inspiration-option-grid">
        <button
          v-for="option in uiControl.options"
          :key="option.id"
          @click="handleOptionSelect(option.id, option.label)"
          class="inspiration-option-btn"
        >
          {{ option.label }}
        </button>
        <button
          @click="isManualInput = true"
          class="inspiration-option-btn inspiration-option-manual"
          :class="{ 'is-active': isManualInput }"
        >
          我要输入
        </button>
      </div>
      <form @submit.prevent="handleTextSubmit" class="inspiration-input-form">
        <textarea
          v-model="textInput"
          :placeholder="isManualInput ? '请输入您的想法...' : '选择上方选项或点击“我要输入”'"
          class="inspiration-textarea"
          :disabled="!isManualInput"
          rows="5"
          ref="textInputRef"
          @input="handleTextareaInput"
        ></textarea>
        <button
          type="submit"
          class="md-btn md-btn-filled md-ripple inspiration-send-btn"
          :disabled="!isManualInput"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <line x1="22" y1="2" x2="11" y2="13"></line>
            <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
          </svg>
        </button>
      </form>
    </div>

    <!-- 文本输入 -->
    <form v-else-if="uiControl.type === 'text_input'" @submit.prevent="handleTextSubmit" class="inspiration-input-form">
      <textarea
        v-model="textInput"
        :placeholder="uiControl.placeholder || '请输入...'"
        class="inspiration-textarea"
        required
        ref="textInputRef"
        rows="5"
        @input="handleTextareaInput"
      ></textarea>
      <button
        type="submit"
        class="md-btn md-btn-filled md-ripple inspiration-send-btn"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <line x1="22" y1="2" x2="11" y2="13"></line>
          <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
        </svg>
      </button>
    </form>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, watch } from 'vue'
import type { UIControl } from '@/api/novel'

interface Props {
  uiControl: UIControl | null
  loading: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  submit: [userInput: { id: string; value: string } | null]
}>()

const textInput = ref('')
const textInputRef = ref<HTMLTextAreaElement>()
const isManualInput = ref(false)

const MIN_ROWS = 5
const MAX_ROWS = 5

const adjustTextareaHeight = () => {
  const textarea = textInputRef.value
  if (!textarea) {
    return
  }
  if (typeof window === 'undefined') {
    return
  }

  const lineHeight = parseFloat(window.getComputedStyle(textarea).lineHeight || '0') || 20
  const minHeight = lineHeight * MIN_ROWS
  const maxHeight = lineHeight * MAX_ROWS

  textarea.style.height = 'auto'
  const targetHeight = Math.min(maxHeight, Math.max(minHeight, textarea.scrollHeight))
  textarea.style.height = `${targetHeight}px`
}

const handleTextareaInput = () => {
  adjustTextareaHeight()
}

const handleOptionSelect = (id: string, label: string) => {
  emit('submit', { id, value: label })
}

const handleTextSubmit = () => {
  if (textInput.value.trim()) {
    emit('submit', { id: 'text_input', value: textInput.value.trim() })
    textInput.value = ''
    nextTick(() => adjustTextareaHeight())
  }
}

// 当输入控件变为文本输入时，自动聚焦
watch(
  () => props.uiControl,
  async (newControl) => {
    // 每次控件更新时，都重置手动输入状态和文本内容
    isManualInput.value = false
    textInput.value = ''

    await nextTick()
    adjustTextareaHeight()

    if (newControl?.type === 'text_input') {
      textInputRef.value?.focus()
    }
  },
  { deep: true } // 使用 deep watch 确保即使是相同类型的控件也能触发
)

// 监听手动输入状态的变化，以聚焦输入框
watch(isManualInput, async (newValue) => {
  if (newValue) {
    await nextTick()
    adjustTextareaHeight()
    textInputRef.value?.focus()
  }
})

</script>

<style scoped>
.inspiration-input-shell {
  width: 100%;
}

.inspiration-loading-state {
  min-height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.inspiration-loading-spinner {
  width: 36px;
  height: 36px;
  border-width: 3px;
}

.inspiration-input-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.inspiration-option-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 8px;
}

.inspiration-option-btn {
  min-height: 42px;
  padding: 8px 12px;
  border-radius: 12px;
  border: 1px solid color-mix(in srgb, var(--md-primary) 22%, var(--md-outline) 78%);
  background: color-mix(in srgb, var(--md-primary-container) 66%, #ffffff 34%);
  color: var(--md-on-primary-container);
  font-size: var(--md-label-medium);
  font-weight: 700;
  transition: all var(--md-duration-short) var(--md-easing-standard);
}

.inspiration-option-btn:hover {
  transform: translateY(-1px);
  box-shadow: var(--md-elevation-1);
}

.inspiration-option-manual {
  background: color-mix(in srgb, var(--md-surface-container-low) 84%, #ffffff 16%);
  border-color: color-mix(in srgb, var(--md-outline) 92%, transparent);
  color: var(--md-on-surface-variant);
}

.inspiration-option-manual.is-active {
  border-color: color-mix(in srgb, var(--md-secondary) 30%, var(--md-outline) 70%);
  background: color-mix(in srgb, var(--md-secondary-container) 72%, #ffffff 28%);
  color: var(--md-on-secondary-container);
}

.inspiration-input-form {
  display: flex;
  align-items: flex-end;
  gap: 10px;
}

.inspiration-textarea {
  width: 100%;
  resize: none;
  overflow-y: auto;
  line-height: 1.65;
  min-height: 120px;
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid color-mix(in srgb, var(--md-outline) 92%, transparent);
  background: color-mix(in srgb, var(--md-surface) 90%, #ffffff 10%);
  color: var(--md-on-surface);
  font-size: var(--md-body-medium);
  transition:
    border-color var(--md-duration-short) var(--md-easing-standard),
    box-shadow var(--md-duration-short) var(--md-easing-standard),
    background-color var(--md-duration-short) var(--md-easing-standard);
  outline: none;
}

.inspiration-textarea:hover:not(:disabled) {
  border-color: color-mix(in srgb, var(--md-primary) 28%, var(--md-outline) 72%);
}

.inspiration-textarea:focus {
  border-color: color-mix(in srgb, var(--md-primary) 76%, #ffffff 24%);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--md-primary) 16%, transparent);
  background: var(--md-surface);
}

.inspiration-textarea:disabled {
  opacity: 0.78;
  cursor: not-allowed;
  background: color-mix(in srgb, var(--md-surface-container) 90%, #ffffff 10%);
}

.inspiration-send-btn {
  width: 44px;
  min-height: 44px;
  height: 44px;
  border-radius: 12px;
  padding: 0;
  flex-shrink: 0;
}

@media (max-width: 640px) {
  .inspiration-input-form {
    flex-direction: column;
    align-items: stretch;
  }

  .inspiration-send-btn {
    width: 100%;
  }
}
</style>
