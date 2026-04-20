<!-- AIMETA P=聊天气泡_对话消息展示|R=消息气泡|NR=不含输入功能|E=component:ChatBubble|X=internal|A=气泡组件|D=vue|S=dom|RD=./README.ai -->
<template>
  <div class="chat-row" :class="{ 'is-user': type === 'user' }">
    <div class="chat-bubble" :class="type === 'ai' ? 'chat-bubble-ai' : 'chat-bubble-user'">
      <!-- AI 消息支持 markdown 渲染 -->
      <div 
        v-if="type === 'ai'" 
        class="prose prose-sm max-w-none prose-headings:mt-2 prose-headings:mb-1 prose-p:my-1 prose-ul:my-1 prose-ol:my-1 prose-li:my-0"
        v-html="renderedMessage"
      ></div>
      <!-- 用户消息保持原样 -->
      <div v-else class="chat-user-text">{{ message }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  message: string
  type: 'user' | 'ai'
}

const props = defineProps<Props>()

// 简单的 markdown 解析函数
const parseMarkdown = (text: string): string => {
  if (!text) return ''
  
  // 处理转义字符
  let parsed = text
    .replace(/\\n/g, '\n')
    .replace(/\\\"/g, '"')
    .replace(/\\'/g, "'")
    .replace(/\\\\/g, '\\')
  
  // 处理加粗文本 **text**
  parsed = parsed.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
  
  // 处理斜体文本 *text*
  parsed = parsed.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, '<em>$1</em>')
  
  // 处理选项列表 A) text
  parsed = parsed.replace(/^([A-Z])\)\s*\*\*(.*?)\*\*(.*)/gm, '<div class="chat-option-row"><span class="chat-option-badge">$1</span><strong>$2</strong>$3</div>')
  
  // 处理普通换行
  parsed = parsed.replace(/\n/g, '<br>')
  
  // 处理多个连续的 <br> 标签为段落
  parsed = parsed.replace(/(<br\s*\/?>\s*){2,}/g, '</p><p class="mt-2">')
  
  // 包装在段落标签中
  if (!parsed.includes('<p>')) {
    parsed = `<p>${parsed}</p>`
  }
  
  return parsed
}

const renderedMessage = computed(() => {
  if (props.type === 'ai') {
    return parseMarkdown(props.message)
  }
  return props.message
})
</script>

<style scoped>
.chat-row {
  width: 100%;
  display: flex;
  justify-content: flex-start;
}

.chat-row.is-user {
  justify-content: flex-end;
}

.chat-bubble {
  max-width: min(90%, 760px);
  padding: 14px 16px;
  border-radius: 14px;
  border: 1px solid color-mix(in srgb, var(--md-outline-variant) 80%, transparent);
  box-shadow: var(--md-elevation-1);
  animation: fadeIn 0.35s var(--md-easing-emphasized);
}

.chat-user-text {
  white-space: pre-wrap;
  line-height: 1.7;
}

.chat-bubble-ai :deep(.chat-option-row) {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.chat-bubble-ai :deep(.chat-option-badge) {
  width: 24px;
  height: 24px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--md-primary-container) 78%, #ffffff 22%);
  color: var(--md-primary);
  font-size: 0.75rem;
  font-weight: 700;
}

.chat-bubble-ai :deep(p) {
  line-height: 1.7;
}
</style>
